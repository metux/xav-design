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


def reply_contract_errors(kind: str, wire: bytes, byte_order: str) -> list[str]:
    errors = []
    if len(wire) < 32 or len(wire) % 4 or wire[0] != 1:
        return ["standard-header"]
    declared = int.from_bytes(wire[4:8], byte_order)
    if 32 + declared * 4 != len(wire):
        errors.append("standard-header")
    if kind == "GetFenceStatus":
        if wire[1] not in (0, 1, 2, 3): errors.append("fence-status")
        if wire[8:32] != bytes(24): errors.append("reserved-zero")
    elif kind == "WaitSemaphores-timeout":
        if int.from_bytes(wire[8:12], byte_order) not in (0, 1): errors.append("wait-status")
        if wire[12:32] != bytes(20): errors.append("reserved-zero")
    elif kind == "WaitForFence":
        if int.from_bytes(wire[8:12], byte_order) not in (0, 1, 2, 3): errors.append("wait-for-fence-status")
        if wire[12:32] != bytes(20): errors.append("reserved-zero")
    elif kind == "GetPhysicalDeviceProperty-success":
        if wire[20:32] != bytes(12): errors.append("reserved-zero")
        value_length = int.from_bytes(wire[16:20], byte_order)
        expected_words = (value_length + 3) // 4
        if declared != expected_words or len(wire) != 32 + expected_words * 4: errors.append("property-payload-length")
        if len(wire) >= 32 + value_length and wire[32 + value_length:] != bytes(len(wire) - 32 - value_length): errors.append("property-padding-zero")
    elif kind == "GetPhysicalDeviceProperty-not-supported":
        if wire[12:20] != bytes(8) or wire[32:] or declared: errors.append("property-failure-zero")
        if wire[20:32] != bytes(12): errors.append("reserved-zero")
    elif kind.startswith("ReadBuffer-") and kind.endswith("-bytes"):
        try:
            data_length = int(kind.split("-")[1])
            padded_length = (data_length + 3) & ~3
            if len(wire) != 32 + padded_length or declared != padded_length // 4:
                errors.append("read-buffer-payload-length")
            elif wire[32 + data_length:] != bytes(padded_length - data_length):
                errors.append("read-buffer-padding-zero")
        except (ValueError, IndexError):
            errors.append("read-buffer-payload-length")
    elif kind == "EnumeratePhysicalDevices":
        pos = 32
        while pos < len(wire):
            if len(wire) - pos < 32:
                errors.append("device-record-length")
                break
            name_length = int.from_bytes(wire[pos + 28:pos + 30], byte_order)
            record_length = 32 + ((name_length + 3) & ~3)
            if pos + record_length > len(wire):
                errors.append("device-record-length")
                break
            if wire[pos + 30:pos + 32] != bytes(2):
                errors.append("device-record-reserved")
            pad_start = pos + 32 + name_length
            if wire[pad_start:pos + record_length] != bytes(pos + record_length - pad_start):
                errors.append("device-name-padding-zero")
            pos += record_length
        if pos != len(wire) and "device-record-length" not in errors:
            errors.append("device-record-length")
    elif kind == "GetPhysicalDeviceQueueFamilyProperties-two-records":
        if (len(wire) - 32) % 12: errors.append("queue-record-length")
        if any(wire[o+8:o+12] != bytes(4) for o in range(32, len(wire) - ((len(wire) - 32) % 12), 12)): errors.append("queue-record-reserved")
    elif kind in ("GetPhysicalDeviceMemoryProperties-one-type-one-heap", "GetPhysicalDeviceMemoryProperties"):
        payload = wire[32:]
        if len(payload) >= 8:
            type_count = int.from_bytes(payload[0:4], byte_order)
            heap_count = int.from_bytes(payload[4:8], byte_order)
            if type_count > 32: errors.append("memory-type-count-range")
            if heap_count > 16: errors.append("memory-heap-count-range")
            if kind == "GetPhysicalDeviceMemoryProperties-one-type-one-heap" and wire[68:72] != bytes(4): errors.append("memory-heap-reserved")
            if len(payload) >= 16 + type_count * 8:
                for index in range(type_count):
                    heap_index = int.from_bytes(payload[20 + index * 8:24 + index * 8], byte_order)
                    if heap_index >= heap_count: errors.append("memory-type-heap-index-range"); break
    elif kind == "GetBufferMemoryRequirements":
        if wire[28:32] != bytes(4): errors.append("reserved-zero")
    elif kind == "GetSemaphoreCounterValue":
        if wire[16:32] != bytes(16): errors.append("reserved-zero")
    return errors

class GoldenReplyVectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = json.loads(FIXTURES.read_text(encoding="utf-8"))
        if fixture.get("schema_version") != 1:
            raise ValueError("unsupported reply vector schema version")
        cls.vectors = fixture["vectors"]

    def test_golden_reply_bytes_and_framing(self):
        self.assertEqual(len(self.vectors), 52)
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
                expected = 2 if vector["name"] == f"GetFenceStatus-{order}" else (
                    0 if "-unsignaled-" in vector["name"] else 1 if "-pending-" in vector["name"] else 3
                )
                self.assertEqual(wire[1], expected)
                self.assertEqual(wire[8:32], bytes(24))
            elif vector["event"] == "WaitForFence":
                expected = 0 if vector["name"] == f"WaitForFence-{order}" else (
                    1 if "-timeout-" in vector["name"] else 2 if "-execution-failed-" in vector["name"] else 3
                )
                self.assertEqual(int.from_bytes(wire[8:12], order), expected)
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
            self.assertEqual(int.from_bytes(payload[0:4], vector["byte_order"]), 0x10203040)
            self.assertEqual(int.from_bytes(payload[4:8], vector["byte_order"]), 2)
            self.assertEqual(int.from_bytes(payload[8:12], vector["byte_order"]), 0x1002)
            self.assertEqual(int.from_bytes(payload[12:16], vector["byte_order"]), 0x2003)
            self.assertEqual(int.from_bytes(payload[16:20], vector["byte_order"]), 0x403000)
            self.assertEqual(int.from_bytes(payload[20:24], vector["byte_order"]), 0x10002)
            self.assertEqual(int.from_bytes(payload[24:28], vector["byte_order"]), 1)
            self.assertEqual(payload[30:32], bytes(2))

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


    def test_property_reply_fields_and_failure_encoding(self):
        for vector in self.vectors:
            if vector["event"] not in ("GetPhysicalDeviceProperty-success", "GetPhysicalDeviceProperty-not-supported", "GetPhysicalDeviceProperty-not-available"):
                continue
            wire = bytes.fromhex(vector["wire_hex"])
            order = vector["byte_order"]
            if vector["event"].endswith("-success"):
                self.assertEqual(int.from_bytes(wire[8:12], order), 0)
                self.assertEqual(int.from_bytes(wire[12:16], order), 1)
                self.assertEqual(int.from_bytes(wire[16:20], order), 4)
                self.assertEqual(wire[20:32], bytes(12))
                self.assertEqual(wire[32:36], bytes.fromhex("78563412") if order == "little" else bytes.fromhex("12345678"))
            else:
                self.assertEqual(int.from_bytes(wire[8:12], order), 1 if vector["event"].endswith("not-supported") else 2)
                self.assertEqual(wire[12:20], bytes(8))
                self.assertEqual(wire[20:32], bytes(12))
                self.assertEqual(len(wire), 32)

    def test_memory_properties_record_layout(self):
        for vector in self.vectors:
            if vector["event"] != "GetPhysicalDeviceMemoryProperties-one-type-one-heap":
                continue
            wire = bytes.fromhex(vector["wire_hex"])
            order = vector["byte_order"]
            payload = wire[32:]
            self.assertEqual(len(payload), 40)
            self.assertEqual([int.from_bytes(payload[i:i+4], order) for i in (0, 4, 8, 12)], [1, 1, 0, 0])
            self.assertEqual(int.from_bytes(payload[16:20], order), 3)
            self.assertEqual(int.from_bytes(payload[20:24], order), 0)
            self.assertEqual(int.from_bytes(payload[24:32], order), 0x0102030405060708)
            self.assertEqual(int.from_bytes(payload[32:36], order), 1)
            self.assertEqual(payload[36:40], bytes(4))

    def test_buffer_requirements_write_and_wait_reply_fields(self):
        for vector in self.vectors:
            wire = bytes.fromhex(vector["wire_hex"])
            order = vector["byte_order"]
            if vector["event"] == "GetBufferMemoryRequirements":
                self.assertEqual(len(wire), 32)
                self.assertEqual(int.from_bytes(wire[8:16], order), 0x1000)
                self.assertEqual(int.from_bytes(wire[16:24], order), 256)
                self.assertEqual(int.from_bytes(wire[24:28], order), 3)
                self.assertEqual(wire[28:32], bytes(4))
            elif vector["event"] == "WriteBuffer-success":
                self.assertEqual(len(wire), 32)
                self.assertEqual(wire[8:32], bytes(24))
            elif vector["event"] == "WaitSemaphores-timeout":
                self.assertEqual(int.from_bytes(wire[8:12], order), 1)
                self.assertEqual(wire[12:32], bytes(20))

    def test_negative_golden_vectors_are_rejected(self):
        path = ROOT / "tests" / "reply-negative-vectors.json"
        fixture = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(fixture.get("schema_version"), 1)
        self.assertGreaterEqual(len(fixture["vectors"]), 28)
        for vector in fixture["vectors"]:
            with self.subTest(vector=vector["name"]):
                errors = reply_contract_errors(vector["kind"], bytes.fromhex(vector["wire_hex"]), vector["byte_order"])
                self.assertIn(vector["violates"], errors)


    def test_read_buffer_alignment_boundaries(self):
        expected = {1: (1, 3), 4: (1, 0), 8: (2, 0)}
        for vector in self.vectors:
            if not vector["event"].startswith("ReadBuffer-") or vector["event"] == "ReadBuffer-5-bytes":
                continue
            size = int(vector["event"].split("-")[1])
            wire = bytes.fromhex(vector["wire_hex"])
            words, padding = expected[size]
            self.assertEqual(int.from_bytes(wire[4:8], vector["byte_order"]), words)
            self.assertEqual(len(wire[32:]), words * 4)
            self.assertEqual(wire[32+size:], bytes(padding))

    def test_all_fence_wait_status_values(self):
        for vector in self.vectors:
            wire = bytes.fromhex(vector["wire_hex"])
            order = vector["byte_order"]
            if vector["event"] == "GetFenceStatus":
                self.assertIn(wire[1], (0, 1, 2, 3))
            elif vector["event"] == "WaitForFence":
                self.assertIn(int.from_bytes(wire[8:12], order), (0, 1, 2, 3))
            elif vector["event"] in ("WaitSemaphores-timeout", "WaitSemaphores-success"):
                self.assertIn(int.from_bytes(wire[8:12], order), (0, 1))

    def test_maximum_memory_type_and_heap_counts(self):
        for vector in self.vectors:
            if vector["event"] != "GetPhysicalDeviceMemoryProperties-max-counts":
                continue
            wire = bytes.fromhex(vector["wire_hex"])
            order = vector["byte_order"]
            payload = wire[32:]
            self.assertEqual(len(payload), 528)
            self.assertEqual(int.from_bytes(wire[4:8], order), 132)
            self.assertEqual([int.from_bytes(payload[i:i+4], order) for i in (0, 4, 8, 12)], [32, 16, 0, 0])
            heaps_start = 16 + 32 * 8
            for i in range(32):
                entry = payload[16+i*8:24+i*8]
                self.assertEqual(int.from_bytes(entry[4:8], order), i % 16)
            for i in range(16):
                entry = payload[heaps_start+i*16:heaps_start+(i+1)*16]
                self.assertEqual(int.from_bytes(entry[12:16], order), 0)

if __name__ == "__main__":
    unittest.main(verbosity=2)
