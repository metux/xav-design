#!/usr/bin/env python3
"""Golden-byte tests for XAverius XGE event layouts."""
from __future__ import annotations

import json
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "event-vectors.json"


def encode_event(vector: dict) -> bytes:
    order = vector["byte_order"]
    if order not in ("little", "big"):
        raise ValueError("unknown byte order")
    endian = "<" if order == "little" else ">"
    total = vector["total_bytes"]
    if total < 32 or total % 4:
        raise ValueError("XGE event length must be >= 32 and divisible by four")
    if vector["xge_length"] != (total - 32) // 4:
        raise ValueError("XGE length does not match total bytes")
    data = bytearray(total)
    struct.pack_into(endian + "BBH I H", data, 0,
                     35, vector["extension_opcode"], vector["sequence"],
                     vector["xge_length"], vector["event_type"])
    if vector["event_type"] not in range(7):
        raise ValueError("unknown XAverius event type")
    if vector["event_type"] != EVENT_IDS.get(vector["event"]):
        raise ValueError("event name and type ID disagree")
    offsets = EVENT_FIELDS[vector["event"]]
    for name, (offset, size) in offsets.items():
        value = vector["fields"][name]
        if name == "reserved" and int(value) != 0:
            raise ValueError("reserved event field must be zero")
        fmt = {4: "I", 8: "Q"}[size]
        struct.pack_into(endian + fmt, data, offset, int(value))
    if len(data) != total:
        raise ValueError("event fields exceed declared total length")
    if any(data[10:32]):
        raise ValueError("XGE reserved header bytes must be zero")
    return bytes(data)


EVENT_IDS = {
    "ASYNC_ERROR": 0, "DEVICE_LOST": 1, "DEVICE_STATUS_CHANGED": 2,
    "DEVICE_MEMORY_PRESSURE": 3, "DEVICE_IDLE": 4,
    "SUBMISSION_COMPLETE": 5, "SUBMISSION_FAILED": 6,
}
EVENT_FIELDS = {
    "ASYNC_ERROR": {
        "device_xid": (32, 4), "error_code": (36, 4), "origin": (40, 4),
        "submission_token": (44, 8), "resource_xid": (52, 4), "reserved": (56, 4),
    },
    "DEVICE_LOST": {
        "device_xid": (32, 4), "reason_code": (36, 4), "device_generation": (40, 8),
    },
    "DEVICE_STATUS_CHANGED": {
        "physical_device_xid": (32, 4), "new_status": (36, 4),
        "reason_code": (40, 4), "reserved": (44, 4),
    },
    "DEVICE_MEMORY_PRESSURE": {
        "device_xid": (32, 4), "heap_index": (36, 4),
        "pressure_level": (40, 4), "reserved": (44, 4),
    },
    "DEVICE_IDLE": {
        "device_xid": (32, 4), "idle_reason": (36, 4), "device_generation": (40, 8),
    },
    "SUBMISSION_COMPLETE": {
        "device_xid": (32, 4), "queue_family_index": (36, 4),
        "queue_index": (40, 4), "reserved": (44, 4), "submission_token": (48, 8),
    },
    "SUBMISSION_FAILED": {
        "device_xid": (32, 4), "queue_family_index": (36, 4),
        "queue_index": (40, 4), "failure_class": (44, 4), "submission_token": (48, 8),
    },
}


class GoldenXGEEventTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = json.loads(FIXTURES.read_text(encoding="utf-8"))
        if fixture.get("schema_version") != 1:
            raise ValueError("unsupported event vector schema version")
        cls.vectors = fixture["vectors"]

    def test_golden_event_bytes(self):
        self.assertEqual(len(self.vectors), 14)
        names = set()
        for vector in self.vectors:
            with self.subTest(vector=vector["name"]):
                self.assertNotIn(vector["name"], names)
                names.add(vector["name"])
                actual = encode_event(vector)
                self.assertEqual(actual.hex(), vector["wire_hex"])
                self.assertEqual(len(actual), vector["total_bytes"])
                self.assertEqual(actual[0], 35)
                self.assertEqual(actual[1], vector["extension_opcode"])
                self.assertEqual(int.from_bytes(actual[2:4], vector["byte_order"]), vector["sequence"])
                self.assertEqual(int.from_bytes(actual[4:8], vector["byte_order"]), vector["xge_length"])
                self.assertEqual(int.from_bytes(actual[8:10], vector["byte_order"]), vector["event_type"])
                self.assertEqual(actual[10:32], bytes(22))

    def test_each_event_has_both_byte_orders(self):
        seen = {}
        for vector in self.vectors:
            seen.setdefault(vector["event"], set()).add(vector["byte_order"])
        self.assertEqual(set(seen), set(EVENT_IDS))
        self.assertTrue(all(orders == {"little", "big"} for orders in seen.values()))

    def test_rejects_inconsistent_xge_length(self):
        import copy
        vector = copy.deepcopy(self.vectors[0])
        vector["xge_length"] += 1
        with self.assertRaisesRegex(ValueError, "XGE length"):
            encode_event(vector)

    def test_rejects_nonzero_reserved_field(self):
        import copy
        vector = copy.deepcopy(next(v for v in self.vectors if v["event"] == "SUBMISSION_COMPLETE"))
        vector["fields"]["reserved"] = 1
        with self.assertRaisesRegex(ValueError, "reserved"):
            encode_event(vector)


if __name__ == "__main__":
    unittest.main(verbosity=2)
