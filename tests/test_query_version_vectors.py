#!/usr/bin/env python3
"""Golden QueryVersion request/reply ABI and malformed-wire conformance tests."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "query-version-vectors.json"
WIRE_SPEC = (ROOT / "spec" / "wire-protocol.md").read_text(encoding="utf-8")
REGISTRY = (ROOT / "registries" / "request-subopcodes.md").read_text(encoding="utf-8")
ERRORS = (ROOT / "spec" / "errors.md").read_text(encoding="utf-8")
CONFORMANCE = (ROOT / "spec" / "conformance.md").read_text(encoding="utf-8")


def validate_request(wire: bytes, order: str) -> None:
    if order not in ("little", "big"):
        raise ValueError("byte order")
    if len(wire) < 8 or len(wire) % 4:
        raise ValueError("request framing")
    words = int.from_bytes(wire[2:4], order)
    if words == 0 or words * 4 != len(wire):
        raise ValueError("request length")
    if wire[1] != 0:
        raise ValueError("data")
    if wire[4] != 48:
        raise ValueError("subopcode")
    if wire[5] != 0:
        raise ValueError("flags")
    if wire[6:8] != bytes(2):
        raise ValueError("reserved")
    if len(wire) != 8:
        raise ValueError("exact request length")


def validate_reply(wire: bytes, order: str) -> None:
    if order not in ("little", "big"):
        raise ValueError("byte order")
    if len(wire) != 32 or wire[0] != 1:
        raise ValueError("reply framing")
    if int.from_bytes(wire[4:8], order) != 0:
        raise ValueError("reply length")
    if int.from_bytes(wire[8:10], order) != 0:
        raise ValueError("major version")
    if int.from_bytes(wire[10:12], order) != 1:
        raise ValueError("minor version")
    if wire[12:32] != bytes(20):
        raise ValueError("reply reserved")


class QueryVersionVectors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_request_golden_frames_both_byte_orders(self):
        vectors = self.fixture["request_vectors"]
        self.assertEqual({v["byte_order"] for v in vectors}, {"little", "big"})
        self.assertEqual(len(vectors), 2)
        for v in vectors:
            with self.subTest(vector=v["name"]):
                wire = bytes.fromhex(v["wire_hex"])
                self.assertEqual(len(wire), v["total_bytes"])
                self.assertEqual(v["subopcode"], 48)
                self.assertEqual(wire[0], 0x90)  # fixture-only major opcode
                self.assertEqual(wire[4], 48)
                validate_request(wire, v["byte_order"])

    def test_reply_golden_frames_both_byte_orders(self):
        vectors = self.fixture["reply_vectors"]
        self.assertEqual({v["byte_order"] for v in vectors}, {"little", "big"})
        self.assertEqual(len(vectors), 2)
        for v in vectors:
            with self.subTest(vector=v["name"]):
                wire = bytes.fromhex(v["wire_hex"])
                self.assertEqual(len(wire), v["total_bytes"])
                self.assertEqual(int.from_bytes(wire[2:4], v["byte_order"]), v["sequence"])
                self.assertEqual(int.from_bytes(wire[4:8], v["byte_order"]), v["reply_length"])
                self.assertEqual(int.from_bytes(wire[8:10], v["byte_order"]), v["major_version"])
                self.assertEqual(int.from_bytes(wire[10:12], v["byte_order"]), v["minor_version"])
                validate_reply(wire, v["byte_order"])

    def test_request_rejects_bad_header_length_and_payload(self):
        base = bytes.fromhex(self.fixture["request_vectors"][0]["wire_hex"])
        mutations = [
            (bytes([base[0], 1]) + base[2:], "data"),
            (base[:5] + b"\x01" + base[6:], "flags"),
            (base[:6] + b"\x01\x00", "reserved"),
            (base[:2] + b"\x00\x00" + base[4:], "request length"),
            (base + bytes(4), "request length"),
            (base[:4] + bytes([49]) + base[5:], "subopcode"),
            (base[:-4], "request framing"),
        ]
        for wire, expected in mutations:
            with self.subTest(expected=expected, wire=wire.hex()):
                with self.assertRaisesRegex(ValueError, expected):
                    validate_request(wire, "little")

    def test_reply_rejects_wrong_version_length_and_reserved(self):
        base = bytes.fromhex(self.fixture["reply_vectors"][0]["wire_hex"])
        mutations = [
            (base[:8] + b"\x01\x00" + base[10:], "major version"),
            (base[:10] + b"\x02\x00" + base[12:], "minor version"),
            (base[:12] + b"\x01" + base[13:], "reply reserved"),
            (base[:4] + b"\x01\x00\x00\x00" + base[8:], "reply length"),
            (base[:31], "reply framing"),
        ]
        for wire, expected in mutations:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(ValueError, expected):
                    validate_reply(wire, "little")

    def test_spec_registry_and_error_contract_agree(self):
        self.assertIn("`QueryVersion` is XAverius subopcode 48", WIRE_SPEC)
        self.assertIn("`major_version`", WIRE_SPEC)
        self.assertIn("MUST report exactly version 0.1", WIRE_SPEC)
        self.assertIn("`QueryVersion` | 48 | Reply", REGISTRY)
        self.assertIn("`QueryVersion` (subopcode 48)", ERRORS)
        self.assertIn("`QueryVersion`", CONFORMANCE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
