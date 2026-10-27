#!/usr/bin/env python3
"""Cross-check reply fixture coverage against normative Markdown contracts."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def section(document: str, name: str) -> str:
    match = re.search(r"^## .*?`" + re.escape(name) + r"`\s*$", document, re.M)
    if not match:
        raise AssertionError(f"missing normative section: {name}")
    next_heading = re.search(r"^## ", document[match.end():], re.M)
    end = match.end() + next_heading.start() if next_heading else len(document)
    return document[match.end():end]


def assignments(text: str, names: set[str]) -> dict[str, int]:
    result = {}
    for name, value in re.findall(r"`?([A-Z_]+)`?\s*=\s*(\d+)", text):
        if name in names:
            result[name] = int(value)
    return result


class ReplySpecCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.devices = (ROOT / "spec/devices.md").read_text(encoding="utf-8")
        cls.sync = (ROOT / "spec/synchronization.md").read_text(encoding="utf-8")
        cls.memory = (ROOT / "spec/memory-buffers.md").read_text(encoding="utf-8")
        fixture = json.loads((ROOT / "tests/reply-vectors.json").read_text(encoding="utf-8"))
        cls.vectors = fixture["vectors"]

    def assert_values_covered_in_both_orders(self, kind: str, values: set[int], read_value):
        for value in sorted(values):
            for order in ("little", "big"):
                matching = [
                    vector for vector in self.vectors
                    if vector["event"] == kind and vector["byte_order"] == order
                    and read_value(vector, order) == value
                ]
                self.assertTrue(matching, f"{kind} value {value} missing for {order}-endian")

    def test_fence_statuses_follow_normative_table(self):
        body = section(self.sync, "GetFenceStatus")
        statuses = assignments(body, {"UNSIGNALED", "PENDING", "SIGNALED", "FAILED"})
        self.assertEqual(statuses, {"UNSIGNALED": 0, "PENDING": 1, "SIGNALED": 2, "FAILED": 3})
        self.assert_values_covered_in_both_orders(
            "GetFenceStatus", set(statuses.values()),
            lambda vector, _order: bytes.fromhex(vector["wire_hex"])[1],
        )

    def test_wait_for_fence_statuses_follow_normative_table(self):
        body = section(self.sync, "WaitForFence")
        status_part = body.split("Reply status:", 1)[-1]
        statuses = assignments(status_part, {"SUCCESS", "TIMEOUT", "EXECUTION_FAILED", "DEVICE_LOST", "DEVICE_DESTROYED"})
        self.assertEqual(statuses, {"SUCCESS": 0, "TIMEOUT": 1, "EXECUTION_FAILED": 2, "DEVICE_LOST": 3, "DEVICE_DESTROYED": 4})
        self.assert_values_covered_in_both_orders(
            "WaitForFence", set(statuses.values()),
            lambda vector, order: int.from_bytes(bytes.fromhex(vector["wire_hex"])[8:12], order),
        )

    def test_semaphore_wait_statuses_follow_normative_contract(self):
        body = section(self.sync, "WaitSemaphores")
        match = re.search(r"status.*?SUCCESS\s*=\s*(\d+).*?TIMEOUT\s*=\s*(\d+)", body, re.S)
        self.assertIsNotNone(match, "WaitSemaphores status contract missing")
        statuses = {int(match.group(1)), int(match.group(2))}
        for value in statuses:
            suffix = "success" if value == 0 else "timeout" if value == 1 else f"status-{value}"
            for order in ("little", "big"):
                self.assertTrue(any(
                    v["event"] == f"WaitSemaphores-{suffix}" and v["byte_order"] == order
                    and int.from_bytes(bytes.fromhex(v["wire_hex"])[8:12], order) == value
                    for v in self.vectors
                ), f"WaitSemaphores status {value} missing for {order}-endian")

    def test_property_statuses_follow_normative_table(self):
        body = section(self.devices, "GetPhysicalDeviceProperty")
        statuses = assignments(body, {"SUCCESS", "NOT_SUPPORTED", "NOT_AVAILABLE"})
        self.assertEqual(statuses, {"SUCCESS": 0, "NOT_SUPPORTED": 1, "NOT_AVAILABLE": 2})
        event_for_status = {0: "GetPhysicalDeviceProperty-success",
                            1: "GetPhysicalDeviceProperty-not-supported",
                            2: "GetPhysicalDeviceProperty-not-available"}
        for value, event in event_for_status.items():
            for order in ("little", "big"):
                self.assertTrue(any(
                    v["event"] == event and v["byte_order"] == order
                    and int.from_bytes(bytes.fromhex(v["wire_hex"])[8:12], order) == value
                    for v in self.vectors
                ), f"property status {value} missing for {order}-endian")

    def test_memory_count_limits_and_formula_match_maximum_fixture(self):
        body = section(self.memory, "GetPhysicalDeviceMemoryProperties")
        limits = re.search(r"at most\s+(\d+)\s+memory types and\s+(\d+)\s+memory heaps", body, re.I)
        self.assertIsNotNone(limits, "normative memory type/heap limits missing")
        type_limit, heap_limit = map(int, limits.groups())
        formula = re.search(r"reply payload length is\s+`(\d+)\s*\+\s*(\d+)\s*\*\s*memory_type_count\s*\+\s*(\d+)\s*\*\s*memory_heap_count`", body)
        self.assertIsNotNone(formula, "normative memory payload formula missing")
        base, type_size, heap_size = map(int, formula.groups())
        expected_size = base + type_size * type_limit + heap_size * heap_limit
        expected_words = expected_size // 4
        for order in ("little", "big"):
            matches = [v for v in self.vectors if v["event"] == "GetPhysicalDeviceMemoryProperties-max-counts" and v["byte_order"] == order]
            self.assertTrue(matches, f"maximum memory-count fixture missing for {order}-endian")
            wire = bytes.fromhex(matches[0]["wire_hex"])
            payload = wire[32:]
            self.assertEqual(int.from_bytes(payload[0:4], order), type_limit)
            self.assertEqual(int.from_bytes(payload[4:8], order), heap_limit)
            self.assertEqual(len(payload), expected_size)
            self.assertEqual(int.from_bytes(wire[4:8], order), expected_words)
            self.assertEqual(len(wire), 32 + expected_words * 4)


    def test_negative_fixtures_cover_normative_boundaries_in_both_orders(self):
        fixture = json.loads((ROOT / "tests/reply-negative-vectors.json").read_text(encoding="utf-8"))
        vectors = fixture["vectors"]
        required_rules = {
            "standard-header", "fixed-reply-size", "fence-status", "wait-status", "wait-status-match", "wait-for-fence-status", "property-success-status", "property-failure-status",
            "property-failure-zero", "property-padding-zero", "queue-record-reserved",
            "memory-heap-reserved", "memory-type-count-range", "memory-heap-count-range",
            "device-name-padding-zero", "device-record-length", "memory-type-heap-index-range",
            "queue-record-length", "queue-flags-reserved", "read-buffer-padding-zero",
            "device-record-reserved", "memory-payload-length", "memory-reserved-zero",
            "memory-type-flags-range", "memory-heap-flags-range", "memory-properties-flags-zero",
            "read-buffer-payload-length", "reserved-zero", "buffer-requirements-size-positive", "buffer-requirements-alignment-positive",
        }
        for rule in sorted(required_rules):
            for order in ("little", "big"):
                self.assertTrue(any(v["violates"] == rule and v["byte_order"] == order for v in vectors),
                                f"negative fixture for {rule} missing in {order}-endian")

        sync = section(self.sync, "GetFenceStatus")
        fence_statuses = assignments(sync, {"UNSIGNALED", "PENDING", "SIGNALED", "FAILED"})
        self.assertEqual(set(fence_statuses.values()), {0, 1, 2, 3})
        memory = section(self.memory, "GetPhysicalDeviceMemoryProperties")
        limits = re.search(r"at most\s+(\d+)\s+memory types and\s+(\d+)\s+memory heaps", memory, re.I)
        self.assertIsNotNone(limits)
        max_types, max_heaps = map(int, limits.groups())
        for rule, offset, limit in (("memory-type-count-range", 32, max_types),
                                    ("memory-heap-count-range", 36, max_heaps)):
            for order in ("little", "big"):
                cases = [v for v in vectors if v["violates"] == rule and v["byte_order"] == order]
                self.assertTrue(cases)
                for case in cases:
                    wire = bytes.fromhex(case["wire_hex"])
                    count = int.from_bytes(wire[offset:offset + 4], order)
                    self.assertGreater(count, limit, f"{case['name']} does not exceed normative limit {limit}")

    def test_fixed_reply_reserved_fields_are_covered_per_kind(self):
        fixture = json.loads((ROOT / "tests/reply-negative-vectors.json").read_text(encoding="utf-8"))
        vectors = fixture["vectors"]
        for kind in ("GetFenceStatus", "WaitForFence", "WaitSemaphores-timeout", "WaitSemaphores-success"):
            for order in ("little", "big"):
                self.assertTrue(any(v["kind"] == kind and v["byte_order"] == order
                                    and v["violates"] == "reserved-zero" for v in vectors),
                                f"{kind} reserved-field negative vector missing in {order}-endian")

    def test_registered_property_shapes_match_registry(self):
        registry = (ROOT / "registries/physical-device-properties.md").read_text(encoding="utf-8")
        self.assertIn("Exactly 16 raw bytes", registry)
        self.assertIn("Exactly three unsigned 32-bit integers in X, Y, Z order", registry)
        for order in ("little", "big"):
            for kind, type_id, size in (("byte-array-16", 5, 16), ("card32-array-3", 6, 12)):
                event = "GetPhysicalDeviceProperty-success-" + kind
                matches = [v for v in self.vectors if v["event"] == event and v["byte_order"] == order]
                self.assertEqual(len(matches), 1, f"{event} missing in {order}-endian")
                wire = bytes.fromhex(matches[0]["wire_hex"])
                self.assertEqual(int.from_bytes(wire[12:16], order), type_id)
                self.assertEqual(int.from_bytes(wire[16:20], order), size)
                self.assertEqual(int.from_bytes(wire[4:8], order), size // 4)

    def test_multiple_device_records_follow_record_length_formula(self):
        body = section(self.devices, "EnumeratePhysicalDevices")
        self.assertIn("32 + ((device_name_length + 3) & ~3)", body)
        for order in ("little", "big"):
            vector = next(v for v in self.vectors if v["event"] == "EnumeratePhysicalDevices-two-records" and v["byte_order"] == order)
            wire = bytes.fromhex(vector["wire_hex"])
            payload = wire[32:]
            pos = 0
            lengths = []
            while pos < len(payload):
                name_length = int.from_bytes(payload[pos + 28:pos + 30], order)
                record_length = 32 + ((name_length + 3) & ~3)
                self.assertLessEqual(pos + record_length, len(payload))
                self.assertEqual(payload[pos + 30:pos + 32], bytes(2))
                self.assertEqual(payload[pos + 32 + name_length:pos + record_length], bytes(record_length - 32 - name_length))
                lengths.append(name_length)
                pos += record_length
            self.assertEqual(lengths, [1, 5])
            self.assertEqual(pos, len(payload))
            self.assertEqual(int.from_bytes(wire[4:8], order), len(payload) // 4)

    def test_property_payload_boundaries_follow_normative_formula(self):
        body = section(self.devices, "GetPhysicalDeviceProperty")
        self.assertIn("ceil(value_length / 4)", body)
        for size in (1, 5):
            for order in ("little", "big"):
                matches = [v for v in self.vectors
                           if v["event"] == "GetPhysicalDeviceProperty-success-byte-array-" + str(size)
                           and v["byte_order"] == order]
                self.assertEqual(len(matches), 1, f"property size {size} missing in {order}-endian")
                wire = bytes.fromhex(matches[0]["wire_hex"])
                padded = (size + 3) & ~3
                self.assertEqual(len(wire), 32 + padded)
                self.assertEqual(int.from_bytes(wire[4:8], order), padded // 4)
                self.assertEqual(wire[32 + size:], bytes(padded - size))

    def test_read_buffer_boundary_fixtures_follow_wire_formula(self):
        body = section(self.memory, "ReadBuffer")
        self.assertRegex(body, r"reply\.length\s*=\s*floor\(\(uint64\(data_length\)\s*\+\s*3\)\s*/\s*4\)")
        sizes = set()
        for vector in self.vectors:
            match = re.fullmatch(r"ReadBuffer-(\d+)-bytes", vector["event"])
            if not match:
                continue
            size = int(match.group(1))
            sizes.add(size)
            wire = bytes.fromhex(vector["wire_hex"])
            padded = (size + 3) & ~3
            self.assertEqual(len(wire[32:]), padded)
            self.assertEqual(int.from_bytes(wire[4:8], vector["byte_order"]), padded // 4)
            self.assertEqual(wire[32 + size:], bytes(padded - size))
        self.assertTrue({1, 4, 5, 8}.issubset(sizes), "ReadBuffer alignment boundary samples missing")


    def test_property_type_width_negative_vectors_cover_both_byte_orders(self):
        fixture = json.loads((ROOT / "tests/reply-negative-vectors.json").read_text(encoding="utf-8"))
        vectors = fixture["vectors"]
        for order in ("little", "big"):
            cases = [v for v in vectors if v["violates"] == "property-type-length" and v["byte_order"] == order]
            self.assertTrue(cases, f"property type/length mismatch vector missing in {order}-endian")
            for case in cases:
                wire = bytes.fromhex(case["wire_hex"])
                self.assertEqual(int.from_bytes(wire[12:16], order), 1)
                self.assertNotEqual(int.from_bytes(wire[16:20], order), 4)


    def test_device_type_registry_rejects_unassigned_values(self):
        registry = (ROOT / "registries/device-types.md").read_text(encoding="utf-8")
        self.assertIn("Values 5 and above are unassigned in v0.1", registry)
        fixture = json.loads((ROOT / "tests/reply-negative-vectors.json").read_text(encoding="utf-8"))
        for order in ("little", "big"):
            cases = [v for v in fixture["vectors"] if v["violates"] == "device-type-range" and v["byte_order"] == order]
            self.assertTrue(cases, f"unassigned device-type negative vector missing in {order}-endian")
            for case in cases:
                wire = bytes.fromhex(case["wire_hex"])
                self.assertGreaterEqual(int.from_bytes(wire[36:40], order), 5)

    def test_device_name_encoding_negative_vectors_cover_both_byte_orders(self):
        fixture = json.loads((ROOT / "tests/reply-negative-vectors.json").read_text(encoding="utf-8"))
        vectors = fixture["vectors"]
        for rule in ("device-name-utf8", "device-name-no-nul"):
            for order in ("little", "big"):
                cases = [v for v in vectors if v["violates"] == rule and v["byte_order"] == order]
                self.assertTrue(cases, f"{rule} negative vector missing in {order}-endian")
                for case in cases:
                    wire = bytes.fromhex(case["wire_hex"])
                    name_length = int.from_bytes(wire[60:62], order)
                    name = wire[64:64 + name_length]
                    if rule == "device-name-utf8":
                        with self.assertRaises(UnicodeDecodeError):
                            name.decode("utf-8", errors="strict")
                    else:
                        self.assertIn(0, name)

    def test_physical_device_xid_must_be_nonzero(self):
        fixture = json.loads((ROOT / "tests/reply-negative-vectors.json").read_text(encoding="utf-8"))
        for order in ("little", "big"):
            cases = [v for v in fixture["vectors"] if v["violates"] == "device-xid-nonzero" and v["byte_order"] == order]
            self.assertTrue(cases, f"zero physical-device XID vector missing in {order}-endian")
            for case in cases:
                wire = bytes.fromhex(case["wire_hex"])
                self.assertEqual(int.from_bytes(wire[32:36], order), 0)

if __name__ == "__main__":
    unittest.main()
