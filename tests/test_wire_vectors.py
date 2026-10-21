#!/usr/bin/env python3
"""Verify golden XAverius wire vectors with a small reference encoder.

These tests validate the fixtures and framing rules. They do not test a live
XAverius client/server implementation; a future implementation should consume
wire-vectors.json as its interoperability oracle.
"""
from __future__ import annotations

import json
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "wire-vectors.json"


def encode_request(vector: dict) -> bytes:
    """Encode the currently covered request layouts using the X11 byte order."""
    fields = vector["fields"]
    endian = "<" if vector["byte_order"] == "little" else ">"
    length_bytes = vector["length_bytes"]
    if length_bytes < 8 or length_bytes % 4:
        raise ValueError("request length must be >= 8 and divisible by four")
    length_words = length_bytes // 4
    if length_words > 0xFFFF:
        raise ValueError("BIG-REQUESTS is unsupported; ordinary length overflow")
    if vector["flags"] != 0:
        raise ValueError("these v0.1 golden vectors require zero flags")

    data = bytearray(struct.pack(
        endian + "BBHBBH",
        vector["major_opcode"],
        0,  # X11 data is reserved as zero by XAverius v0.1.
        length_words,
        vector["subopcode"],
        vector["flags"],
        0,  # XAverius common-header reserved field.
    ))

    request = vector["request"]
    if request == "CreateBuffer":
        if fields["reserved"] != 0:
            raise ValueError("CreateBuffer reserved field must be zero")
        data.extend(struct.pack(
            endian + "IIQII",
            fields["device_xid"],
            fields["buffer_xid"],
            fields["size"],
            fields["usage_flags"],
            fields["reserved"],
        ))
    elif request in ("WriteBuffer", "ReadBuffer"):
        data.extend(struct.pack(
            endian + "IIQI",
            fields["device_xid"],
            fields["buffer_xid"],
            fields["buffer_offset"],
            fields["data_length"],
        ))
        if request == "WriteBuffer":
            payload = bytes.fromhex(fields["payload_hex"])
            padding = bytes.fromhex(fields["padding_hex"])
            if fields["data_length"] <= 0 or len(payload) != fields["data_length"]:
                raise ValueError("WriteBuffer data_length must match a nonempty payload")
            expected_padding = (-len(payload)) % 4
            if len(padding) != expected_padding or any(padding):
                raise ValueError("WriteBuffer padding must be the required number of zero bytes")
            data.extend(payload)
            data.extend(padding)
    else:
        raise ValueError(f"no reference encoder for {request}")

    if len(data) != length_bytes:
        raise ValueError(
            f"{request}: declared {length_bytes} bytes but encoded {len(data)}"
        )
    return bytes(data)


def validate_request_wire(wire: bytes, byte_order: str) -> None:
    """Validate generic X11/XAverius request framing from raw bytes."""
    if len(wire) < 8:
        raise ValueError("truncated common request header")
    if len(wire) % 4:
        raise ValueError("request byte length must be divisible by four")
    if byte_order not in ("little", "big"):
        raise ValueError("unknown byte order")
    declared_words = int.from_bytes(wire[2:4], byte_order)
    if declared_words == 0:
        raise ValueError("zero request length is invalid; BIG-REQUESTS is unsupported")
    if declared_words * 4 != len(wire):
        raise ValueError("declared request length does not match wire bytes")
    if wire[1] != 0:
        raise ValueError("X11 data byte must be zero")
    if wire[5] != 0:
        raise ValueError("reserved flags must be zero")
    if wire[6:8] != b"\\x00\\x00":
        raise ValueError("reserved common-header field must be zero")


class GoldenWireVectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        fixture = json.loads(FIXTURES.read_text(encoding="utf-8"))
        if fixture.get("schema_version") != 1:
            raise ValueError("unsupported wire vector schema version")
        cls.vectors = fixture["vectors"]

    def test_golden_bytes(self) -> None:
        self.assertGreaterEqual(len(self.vectors), 1)
        names = set()
        for vector in self.vectors:
            with self.subTest(vector=vector["name"]):
                self.assertNotIn(vector["name"], names)
                names.add(vector["name"])
                actual = encode_request(vector)
                self.assertEqual(actual.hex(), vector["wire_hex"])
                self.assertEqual(len(actual), vector["length_bytes"])
                self.assertEqual(actual[1], 0, "X11 data byte must be zero")
                self.assertEqual(actual[5], 0, "v0.1 flags must be zero in these vectors")
                self.assertEqual(actual[6:8], b"\x00\x00", "reserved header must be zero")
                self.assertEqual(
                    int.from_bytes(actual[2:4], vector["byte_order"]),
                    len(actual) // 4,
                )

    def test_both_byte_orders_are_present(self) -> None:
        self.assertEqual(
            {vector["byte_order"] for vector in self.vectors},
            {"little", "big"},
        )

    def test_variable_payload_padding_is_zero(self) -> None:
        writes = [v for v in self.vectors if v["request"] == "WriteBuffer"]
        self.assertTrue(writes)
        for vector in writes:
            with self.subTest(vector=vector["name"]):
                wire = encode_request(vector)
                self.assertEqual(wire[28 + vector["fields"]["data_length"]:], b"\x00")


    def test_variable_payload_boundary_vectors(self) -> None:
        writes = [v for v in self.vectors if v["request"] == "WriteBuffer"]
        observed = {(v["fields"]["data_length"], v["byte_order"]) for v in writes}
        for size in (1, 3, 4, 5):
            for order in ("little", "big"):
                self.assertIn((size, order), observed)
        for vector in writes:
            with self.subTest(vector=vector["name"]):
                wire = encode_request(vector)
                validate_request_wire(wire, vector["byte_order"])
                self.assertEqual(len(wire), 32 + ((vector["fields"]["data_length"] + 3) & ~3))

    def test_rejects_truncated_common_header(self) -> None:
        for size in range(8):
            with self.subTest(size=size):
                with self.assertRaisesRegex(ValueError, "truncated"):
                    validate_request_wire(b"\\x00" * size, "little")

    def test_rejects_raw_declared_length_mismatch(self) -> None:
        vector = next(v for v in self.vectors if v["request"] == "ReadBuffer")
        wire = bytearray(encode_request(vector))
        wire[2:4] = (len(wire) // 4 + 1).to_bytes(2, vector["byte_order"])
        with self.assertRaisesRegex(ValueError, "declared request length"):
            validate_request_wire(bytes(wire), vector["byte_order"])

    def test_rejects_nonzero_raw_header_reserved_fields(self) -> None:
        vector = next(v for v in self.vectors if v["request"] == "ReadBuffer")
        wire = bytearray(encode_request(vector))
        wire[6] = 1
        with self.assertRaisesRegex(ValueError, "reserved common-header"):
            validate_request_wire(bytes(wire), vector["byte_order"])

    def test_rejects_declared_length_mismatch(self) -> None:
        vector = next(v.copy() for v in self.vectors if v["request"] == "ReadBuffer")
        vector["length_bytes"] += 4
        with self.assertRaisesRegex(ValueError, "declared"):
            encode_request(vector)

    def test_rejects_nonzero_write_padding(self) -> None:
        import copy
        vector = copy.deepcopy(next(v for v in self.vectors if v["request"] == "WriteBuffer"))
        vector["fields"]["padding_hex"] = "7f"
        with self.assertRaisesRegex(ValueError, "padding"):
            encode_request(vector)

    def test_rejects_write_payload_length_mismatch(self) -> None:
        import copy
        vector = copy.deepcopy(next(v for v in self.vectors if v["request"] == "WriteBuffer"))
        vector["fields"]["data_length"] = 4
        with self.assertRaisesRegex(ValueError, "data_length"):
            encode_request(vector)

    def test_rejects_nonzero_create_buffer_reserved_field(self) -> None:
        import copy
        vector = copy.deepcopy(next(v for v in self.vectors if v["request"] == "CreateBuffer"))
        vector["fields"]["reserved"] = 1
        with self.assertRaisesRegex(ValueError, "reserved"):
            encode_request(vector)


if __name__ == "__main__":
    unittest.main(verbosity=2)
