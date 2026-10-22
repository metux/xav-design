#!/usr/bin/env python3
"""Golden-byte tests for XAverius SelectEvents requests."""
from __future__ import annotations

import json
import re
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "select-events-vectors.json"
MAJOR_OPCODE = 0x90  # Fixture-only; the X server assigns the real opcode.
SUBOPCODE = 40
SCOPES = {
    0: {"mask": 0x01, "name": "CONNECTION"},
    1: {"mask": 0x03, "name": "DEVICE"},
    2: {"mask": 0x03, "name": "QUEUE"},
}


def encode_select_events(vector: dict) -> bytes:
    order = vector["byte_order"]
    if order not in ("little", "big"):
        raise ValueError("unknown byte order")
    endian = "<" if order == "little" else ">"
    fields = vector["fields"]
    if vector["major_opcode"] not in range(128, 256):
        raise ValueError("extension major opcode must be in 128..255")
    if vector["subopcode"] != SUBOPCODE:
        raise ValueError("SelectEvents subopcode must be 40")
    if vector["flags"] != 0:
        raise ValueError("SelectEvents flags must be zero")
    if vector["length_bytes"] != 32:
        raise ValueError("SelectEvents must be exactly 32 bytes")
    if fields["reserved"] != 0:
        raise ValueError("SelectEvents reserved field must be zero")
    scope = fields["scope"]
    if scope not in SCOPES:
        raise ValueError("unknown SelectEvents scope")
    if fields["event_mask"] & ~SCOPES[scope]["mask"]:
        raise ValueError("event mask contains bits not valid for scope")
    if scope == 0 and any(fields[k] != 0 for k in ("device_xid", "queue_family_index", "queue_index")):
        raise ValueError("connection scope requires zero device and queue fields")
    if scope == 1 and (fields["device_xid"] == 0 or fields["queue_family_index"] != 0 or fields["queue_index"] != 0):
        raise ValueError("device scope requires device XID and zero queue fields")
    if scope == 2 and fields["device_xid"] == 0:
        raise ValueError("queue scope requires device XID and concrete queue indices")

    data = bytearray(32)
    data[0] = vector["major_opcode"]
    data[1] = 0
    struct.pack_into(endian + "H", data, 2, 8)
    data[4] = SUBOPCODE
    data[5] = vector["flags"]
    struct.pack_into(endian + "H", data, 6, 0)
    struct.pack_into(
        endian + "IIIII I", data, 8,
        fields["scope"], fields["device_xid"], fields["queue_family_index"],
        fields["queue_index"], fields["event_mask"], fields["reserved"],
    )
    return bytes(data)


def validate_select_events_wire(wire: bytes, byte_order: str) -> None:
    if byte_order not in ("little", "big"):
        raise ValueError("unknown byte order")
    if len(wire) != 32:
        raise ValueError("SelectEvents must be exactly 32 bytes")
    endian = "<" if byte_order == "little" else ">"
    if wire[0] not in range(128, 256):
        raise ValueError("extension major opcode must be in 128..255")
    if wire[1] != 0:
        raise ValueError("X11 data byte must be zero")
    if struct.unpack_from(endian + "H", wire, 2)[0] != 8:
        raise ValueError("SelectEvents length words must equal 8")
    if wire[4] != SUBOPCODE:
        raise ValueError("SelectEvents subopcode must be 40")
    if wire[5] != 0:
        raise ValueError("SelectEvents flags must be zero")
    if wire[6:8] != bytes(2):
        raise ValueError("common-header reserved field must be zero")
    if struct.unpack_from(endian + "I", wire, 28)[0] != 0:
        raise ValueError("SelectEvents reserved field must be zero")
    scope, device, family, queue, mask, _reserved = struct.unpack_from(endian + "IIIIII", wire, 8)
    if scope not in SCOPES:
        raise ValueError("unknown SelectEvents scope")
    if mask & ~SCOPES[scope]["mask"]:
        raise ValueError("event mask contains bits not valid for scope")
    if scope == 0 and (device or family or queue):
        raise ValueError("connection scope requires zero device and queue fields")
    if scope == 1 and (not device or family or queue):
        raise ValueError("device scope requires device XID and zero queue fields")
    if scope == 2 and not device:
        raise ValueError("queue scope requires device XID")


class GoldenSelectEventsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = json.loads(FIXTURES.read_text(encoding="utf-8"))
        if fixture.get("schema_version") != 1:
            raise ValueError("unsupported SelectEvents vector schema version")
        cls.vectors = fixture["vectors"]

    def test_golden_bytes_and_both_byte_orders(self):
        self.assertEqual(len(self.vectors), 6)
        seen = set()
        for vector in self.vectors:
            with self.subTest(vector=vector["name"]):
                self.assertNotIn(vector["name"], seen)
                seen.add(vector["name"])
                wire = encode_select_events(vector)
                self.assertEqual(wire.hex(), vector["wire_hex"])
                self.assertEqual(len(wire), 32)
                validate_select_events_wire(wire, vector["byte_order"])
        for scope in SCOPES:
            self.assertEqual(
                {v["byte_order"] for v in self.vectors if v["fields"]["scope"] == scope},
                {"little", "big"},
            )

    def test_layout_and_registry_match_normative_spec(self):
        document = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
        section = re.search(r"^## Event-Auswahl: `SelectEvents`\s*$([\s\S]*?)(?=^## |\Z)", document, re.M)
        self.assertIsNotNone(section)
        body = section.group(1)
        self.assertRegex(body, r"fest(?:e|er) Gesamtlänge von 32 Bytes")
        expected = [
            (8, "CARD32", "scope"), (12, "XID", "device_xid"),
            (16, "CARD32", "queue_family_index"), (20, "CARD32", "queue_index"),
            (24, "CARD32", "event_mask"), (28, "CARD32", "reserved = 0"),
        ]
        actual = [
            (int(offset), typ, field.strip().replace("`", ""))
            for offset, typ, field in re.findall(
                r"^\|\s*(\d+)\s*\|\s*([A-Z0-9]+)\s*\|\s*([^|]+?)\s*\|", body, re.M
            )
        ]
        self.assertEqual(actual, expected)
        for scope, value in (("CONNECTION", 0), ("DEVICE", 1), ("QUEUE", 2)):
            self.assertRegex(body, rf"`{scope} = {value}`")
        mask_rows = [
            (scope, int(bit), event)
            for scope, bit, event in re.findall(
                r"^\|\s*`(CONNECTION|DEVICE|QUEUE)`\s*\|\s*(\d+)\s*\|\s*`([A-Z_]+)`\s*\|",
                body, re.M,
            )
        ]
        self.assertEqual(mask_rows, [
            ("CONNECTION", 0, "DEVICE_STATUS_CHANGED"),
            ("DEVICE", 0, "DEVICE_MEMORY_PRESSURE"),
            ("DEVICE", 1, "DEVICE_IDLE"),
            ("QUEUE", 0, "SUBMISSION_COMPLETE"),
            ("QUEUE", 1, "SUBMISSION_FAILED"),
        ])
        registry = (ROOT / "registries" / "request-subopcodes.md").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"^\| `SelectEvents` \| 40 \| Void \|", registry, re.M)), 1)

    def test_zero_mask_is_valid_for_each_scope_and_byte_order(self):
        import copy
        for order in ("little", "big"):
            for scope in SCOPES:
                vector = copy.deepcopy(next(
                    v for v in self.vectors
                    if v["fields"]["scope"] == scope and v["byte_order"] == order
                ))
                vector["fields"]["event_mask"] = 0
                wire = encode_select_events(vector)
                validate_select_events_wire(wire, order)
                self.assertEqual(wire[24:28], bytes(4))
        document = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
        self.assertIn("event_mask = 0", document)

    def test_rejects_invalid_scope_masks_and_reserved_bytes(self):
        vector = self.vectors[0]
        wire = bytearray(encode_select_events(vector))
        wire[5] = 1
        with self.assertRaisesRegex(ValueError, "flags"):
            validate_select_events_wire(bytes(wire), vector["byte_order"])
        wire = bytearray(encode_select_events(vector))
        wire[31] = 1
        with self.assertRaisesRegex(ValueError, "reserved field"):
            validate_select_events_wire(bytes(wire), vector["byte_order"])
        wire = bytearray(encode_select_events(vector))
        wire[8:12] = (3).to_bytes(4, vector["byte_order"])
        with self.assertRaisesRegex(ValueError, "unknown SelectEvents scope"):
            validate_select_events_wire(bytes(wire), vector["byte_order"])
        wire = bytearray(encode_select_events(vector))
        wire[24:28] = (2).to_bytes(4, vector["byte_order"])
        with self.assertRaisesRegex(ValueError, "event mask"):
            validate_select_events_wire(bytes(wire), vector["byte_order"])

    def test_raw_wire_rejects_invalid_scope_field_combinations(self):
        cases = (
            ("connection scope", 8, 0, 12, 1),
            ("device scope", 8, 1, 12, 0),
            ("queue scope", 8, 2, 12, 0),
        )
        for order in ("little", "big"):
            endian = "little" if order == "little" else "big"
            for message, scope_offset, scope, device_offset, device in cases:
                vector = next(v for v in self.vectors if v["fields"]["scope"] == scope and v["byte_order"] == order)
                wire = bytearray(encode_select_events(vector))
                wire[scope_offset:scope_offset + 4] = scope.to_bytes(4, endian)
                wire[device_offset:device_offset + 4] = device.to_bytes(4, endian)
                if scope == 0:
                    wire[12:16] = (1).to_bytes(4, endian)
                elif scope == 1:
                    wire[16:20] = (1).to_bytes(4, endian)
                with self.subTest(order=order, scope=scope):
                    with self.assertRaisesRegex(ValueError, message):
                        validate_select_events_wire(bytes(wire), order)

    def test_raw_wire_rejects_invalid_common_header_fields(self):
        vector = next(v for v in self.vectors if v["byte_order"] == "little")
        cases = (
            (1, bytes([1]), "X11 data byte"),
            (6, bytes([1, 0]), "common-header reserved"),
            (4, bytes([0x29]), "subopcode"),
            (5, bytes([1]), "flags"),
            (0, bytes([0x7f]), "major opcode"),
            (2, bytes([7, 0]), "length words"),
        )
        for offset, replacement, message in cases:
            wire = bytearray(encode_select_events(vector))
            wire[offset:offset + len(replacement)] = replacement
            with self.subTest(offset=offset):
                with self.assertRaisesRegex(ValueError, message):
                    validate_select_events_wire(bytes(wire), "little")

    def test_encoder_rejects_invalid_scope_field_combinations(self):
        import copy
        vector = copy.deepcopy(next(v for v in self.vectors if v["fields"]["scope"] == 0))
        vector["fields"]["device_xid"] = 1
        with self.assertRaisesRegex(ValueError, "connection scope"):
            encode_select_events(vector)
        vector = copy.deepcopy(next(v for v in self.vectors if v["fields"]["scope"] == 1))
        vector["fields"]["queue_index"] = 1
        with self.assertRaisesRegex(ValueError, "device scope"):
            encode_select_events(vector)
        vector = copy.deepcopy(next(v for v in self.vectors if v["fields"]["scope"] == 2))
        vector["fields"]["event_mask"] = 4
        with self.assertRaisesRegex(ValueError, "event mask"):
            encode_select_events(vector)


if __name__ == "__main__":
    unittest.main(verbosity=2)
