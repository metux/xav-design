#!/usr/bin/env python3
"""Golden-byte and structural checks for selected XAverius X11 replies."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "reply-vectors.json"


def validate_reply_wire(wire: bytes, byte_order: str) -> None:
    if len(wire) < 32:
        raise ValueError("truncated X11 reply header")
    if len(wire) % 4:
        raise ValueError("reply size must be divisible by four")
    if byte_order not in ("little", "big"):
        raise ValueError("unknown byte order")
    if wire[0] != 1:
        raise ValueError("response_type must be 1 for a reply")
    declared = int.from_bytes(wire[4:8], byte_order)
    if 32 + declared * 4 != len(wire):
        raise ValueError("reply.length does not match wire size")


class GoldenReplyVectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = json.loads(FIXTURES.read_text(encoding="utf-8"))
        if fixture.get("schema_version") != 1:
            raise ValueError("unsupported reply vector schema version")
        cls.vectors = fixture["vectors"]

    def test_golden_reply_bytes_and_framing(self):
        self.assertEqual(len(self.vectors), 16)
        names = set()
        for vector in self.vectors:
            with self.subTest(vector=vector["name"]):
                self.assertNotIn(vector["name"], names)
                names.add(vector["name"])
                wire = bytes.fromhex(vector["wire_hex"])
                self.assertEqual(len(wire), vector["total_bytes"])
                self.assertEqual(wire[1], vector["data_byte"])
                self.assertEqual(int.from_bytes(wire[2:4], vector["byte_order"]), vector["sequence"])
                self.assertEqual(int.from_bytes(wire[4:8], vector["byte_order"]), vector["reply_length"])
                self.assertEqual(wire[32:].hex(), vector["payload_hex"])
                validate_reply_wire(wire, vector["byte_order"])

    def test_both_byte_orders_cover_each_reply_kind(self):
        seen = {}
        for vector in self.vectors:
            kind = vector["event"].removesuffix("-empty").removesuffix("-one-record").removesuffix("-two-records")
            seen.setdefault(kind, set()).add(vector["byte_order"])
        self.assertTrue(all(orders == {"little", "big"} for orders in seen.values()))

    def test_fixed_reply_fields_are_at_documented_offsets(self):
        for vector in self.vectors:
            wire = bytes.fromhex(vector["wire_hex"])
            order = vector["byte_order"]
            if vector["event"] == "GetFenceStatus":
                self.assertEqual(wire[1], 2)  # SIGNALED
                self.assertEqual(wire[8:32], bytes(24))
            elif vector["event"] == "WaitForFence":
                self.assertEqual(int.from_bytes(wire[8:12], order), 0)  # SUCCESS
                self.assertEqual(wire[12:32], bytes(20))
            elif vector["event"] == "GetSemaphoreCounterValue":
                self.assertEqual(int.from_bytes(wire[8:16], order), 72623859790382856)
                self.assertEqual(wire[16:32], bytes(16))

    def test_read_buffer_payload_is_padded_and_length_counts_words(self):
        for vector in self.vectors:
            if vector["event"] != "ReadBuffer-5-bytes":
                continue
            wire = bytes.fromhex(vector["wire_hex"])
            self.assertEqual(wire[32:37], bytes([1, 2, 3, 4, 5]))
            self.assertEqual(wire[37:40], bytes(3))
            self.assertEqual(int.from_bytes(wire[4:8], vector["byte_order"]), 2)

    def test_enumeration_record_lengths_and_padding(self):
        for vector in self.vectors:
            if vector["event"] != "EnumeratePhysicalDevices-one-record":
                continue
            payload = bytes.fromhex(vector["payload_hex"])
            self.assertEqual(len(payload), 36)
            name_length = int.from_bytes(payload[28:30], vector["byte_order"])
            self.assertEqual(name_length, 4)
            self.assertEqual(payload[32:36], b"GPU0")

    def test_queue_family_enumeration_record_lengths(self):
        for vector in self.vectors:
            if vector["event"] != "GetPhysicalDeviceQueueFamilyProperties-two-records":
                continue
            payload = bytes.fromhex(vector["payload_hex"])
            self.assertEqual(len(payload), 24)
            self.assertEqual(len(payload) % 12, 0)
            self.assertEqual(int.from_bytes(payload[0:4], vector["byte_order"]), 3)
            self.assertEqual(int.from_bytes(payload[12:16], vector["byte_order"]), 1)

    def test_rejects_wrong_reply_length(self):
        vector = self.vectors[0]
        wire = bytearray.fromhex(vector["wire_hex"])
        wire[4:8] = (1).to_bytes(4, vector["byte_order"])
        with self.assertRaisesRegex(ValueError, "reply.length"):
            validate_reply_wire(bytes(wire), vector["byte_order"])

    def test_rejects_truncated_header(self):
        with self.assertRaisesRegex(ValueError, "truncated"):
            validate_reply_wire(bytes(28), "little")


if __name__ == "__main__":
    unittest.main(verbosity=2)
