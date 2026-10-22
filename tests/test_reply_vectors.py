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
    elif kind in ("WaitSemaphores-timeout", "WaitSemaphores-success"):
        status = int.from_bytes(wire[8:12], byte_order)
        if status not in (0, 1): errors.append("wait-status")
        if status in (0, 1) and status != (1 if kind.endswith("timeout") else 0): errors.append("wait-status-match")
        if wire[12:32] != bytes(20): errors.append("reserved-zero")
    elif kind.startswith("WaitForFence"):
        if int.from_bytes(wire[8:12], byte_order) not in (0, 1, 2, 3, 4): errors.append("wait-for-fence-status")
        if wire[12:32] != bytes(20): errors.append("reserved-zero")
    elif kind.startswith("GetPhysicalDeviceProperty-success"):
        if int.from_bytes(wire[8:12], byte_order) != 0: errors.append("property-success-status")
        if wire[20:32] != bytes(12): errors.append("reserved-zero")
        property_type = int.from_bytes(wire[12:16], byte_order)
        value_length = int.from_bytes(wire[16:20], byte_order)
        fixed_widths = {1: 4, 2: 8, 3: 4}
        if property_type not in range(1, 8) or (property_type in fixed_widths and value_length != fixed_widths[property_type]) or (property_type == 6 and value_length % 4) or (property_type == 7 and value_length % 8):
            errors.append("property-type-length")
        expected_words = (value_length + 3) // 4
        if declared != expected_words or len(wire) != 32 + expected_words * 4: errors.append("property-payload-length")
        if len(wire) >= 32 + value_length and wire[32 + value_length:] != bytes(len(wire) - 32 - value_length): errors.append("property-padding-zero")
    elif kind in ("GetPhysicalDeviceProperty-not-supported", "GetPhysicalDeviceProperty-not-available"):
        expected_status = 1 if kind.endswith("not-supported") else 2
        if int.from_bytes(wire[8:12], byte_order) != expected_status: errors.append("property-failure-status")
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
            if int.from_bytes(wire[pos:pos + 4], byte_order) == 0:
                errors.append("device-xid-nonzero")
            if int.from_bytes(wire[pos + 4:pos + 8], byte_order) not in range(5):
                errors.append("device-type-range")
            name_bytes = wire[pos + 32:pos + 32 + name_length]
            try:
                decoded_name = name_bytes.decode("utf-8", errors="strict")
                if chr(0) in decoded_name:
                    errors.append("device-name-no-nul")
            except UnicodeDecodeError:
                errors.append("device-name-utf8")
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
        valid_end = len(wire) - ((len(wire) - 32) % 12)
        for offset in range(32, valid_end, 12):
            flags = int.from_bytes(wire[offset:offset + 4], byte_order)
            if flags & ~0x1F: errors.append("queue-flags-reserved")
            if wire[offset + 8:offset + 12] != bytes(4): errors.append("queue-record-reserved")
    elif kind in ("GetPhysicalDeviceMemoryProperties-one-type-one-heap", "GetPhysicalDeviceMemoryProperties"):
        payload = wire[32:]
        if len(payload) < 16:
            errors.append("memory-payload-length")
        else:
            type_count = int.from_bytes(payload[0:4], byte_order)
            heap_count = int.from_bytes(payload[4:8], byte_order)
            if type_count > 32: errors.append("memory-type-count-range")
            if heap_count > 16: errors.append("memory-heap-count-range")
            expected_length = 16 + type_count * 8 + heap_count * 16
            if len(payload) != expected_length: errors.append("memory-payload-length")
            if payload[8:12] != bytes(4): errors.append("memory-properties-flags-zero")
            if payload[12:16] != bytes(4): errors.append("memory-reserved-zero")
            if len(payload) >= 16 + type_count * 8:
                for index in range(type_count):
                    entry = payload[16 + index * 8:24 + index * 8]
                    flags = int.from_bytes(entry[0:4], byte_order)
                    heap_index = int.from_bytes(entry[4:8], byte_order)
                    if flags & ~0x3F: errors.append("memory-type-flags-range")
                    if heap_index >= heap_count: errors.append("memory-type-heap-index-range")
            heap_start = 16 + type_count * 8
            if len(payload) >= heap_start + heap_count * 16:
                for index in range(heap_count):
                    entry = payload[heap_start + index * 16:heap_start + (index + 1) * 16]
                    heap_flags = int.from_bytes(entry[8:12], byte_order)
                    if heap_flags & ~0x1: errors.append("memory-heap-flags-range")
                    if entry[12:16] != bytes(4): errors.append("memory-heap-reserved")
    elif kind == "GetBufferMemoryRequirements":
        if int.from_bytes(wire[8:16], byte_order) == 0: errors.append("buffer-requirements-size-positive")
        if int.from_bytes(wire[16:24], byte_order) == 0: errors.append("buffer-requirements-alignment-positive")
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
        self.assertEqual(len(self.vectors), 64)
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
            elif vector["event"].startswith("WaitForFence"):
                expected = 4 if "-device-destroyed-" in vector["name"] else (0 if vector["name"] == f"WaitForFence-{order}" else (
                    1 if "-timeout-" in vector["name"] else 2 if "-execution-failed-" in vector["name"] else 3
                ))
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

    def test_enumeration_multiple_records_variable_name_lengths(self):
        for order in ("little", "big"):
            vector = next(v for v in self.vectors if v["event"] == "EnumeratePhysicalDevices-two-records" and v["byte_order"] == order)
            wire = bytes.fromhex(vector["wire_hex"])
            payload = wire[32:]
            records = []
            pos = 0
            while pos < len(payload):
                self.assertGreaterEqual(len(payload) - pos, 32)
                name_length = int.from_bytes(payload[pos + 28:pos + 30], order)
                record_length = 32 + ((name_length + 3) & ~3)
                self.assertLessEqual(pos + record_length, len(payload))
                self.assertEqual(payload[pos + 30:pos + 32], bytes(2))
                self.assertEqual(payload[pos + 32 + name_length:pos + record_length], bytes(record_length - 32 - name_length))
                records.append((name_length, payload[pos + 32:pos + 32 + name_length]))
                pos += record_length
            self.assertEqual(records, [(1, b"A"), (5, b"GPU-0")])
            self.assertEqual(pos, len(payload))
            self.assertEqual(int.from_bytes(wire[4:8], order), len(payload) // 4)

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


    def test_property_variable_payload_boundaries(self):
        expected = {1: bytes([0xA5]), 5: bytes([1, 2, 3, 4, 5])}
        for size, value in expected.items():
            kind = "GetPhysicalDeviceProperty-success-byte-array-" + str(size)
            for order in ("little", "big"):
                matching = [v for v in self.vectors if v["event"] == kind and v["byte_order"] == order]
                self.assertEqual(len(matching), 1, f"{kind} missing in {order}-endian")
                wire = bytes.fromhex(matching[0]["wire_hex"])
                padded = (size + 3) & ~3
                self.assertEqual(int.from_bytes(wire[12:16], order), 5)
                self.assertEqual(int.from_bytes(wire[16:20], order), size)
                self.assertEqual(wire[32:32 + size], value)
                self.assertEqual(wire[32 + size:], bytes(padded - size))
                self.assertEqual(int.from_bytes(wire[4:8], order), padded // 4)

    def test_registered_uuid_and_workgroup_size_property_shapes(self):
        uuid = bytes.fromhex("00112233445566778899aabbccddeeff")
        for order in ("little", "big"):
            uuid_kind = "GetPhysicalDeviceProperty-success-byte-array-16"
            uuid_vector = next(v for v in self.vectors if v["event"] == uuid_kind and v["byte_order"] == order)
            uuid_wire = bytes.fromhex(uuid_vector["wire_hex"])
            self.assertEqual(int.from_bytes(uuid_wire[12:16], order), 5)
            self.assertEqual(int.from_bytes(uuid_wire[16:20], order), 16)
            self.assertEqual(uuid_wire[32:48], uuid)
            self.assertEqual(int.from_bytes(uuid_wire[4:8], order), 4)
            array_kind = "GetPhysicalDeviceProperty-success-card32-array-3"
            array_vector = next(v for v in self.vectors if v["event"] == array_kind and v["byte_order"] == order)
            array_wire = bytes.fromhex(array_vector["wire_hex"])
            self.assertEqual(int.from_bytes(array_wire[12:16], order), 6)
            self.assertEqual(int.from_bytes(array_wire[16:20], order), 12)
            self.assertEqual([int.from_bytes(array_wire[i:i+4], order) for i in (32, 36, 40)], [64, 32, 16])
            self.assertEqual(int.from_bytes(array_wire[4:8], order), 3)

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
                self.assertEqual(errors, [vector["violates"]],
                                 "each negative vector must isolate exactly one normative violation")


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
            elif vector["event"].startswith("WaitForFence"):
                self.assertIn(int.from_bytes(wire[8:12], order), (0, 1, 2, 3, 4))
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
