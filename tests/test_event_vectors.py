#!/usr/bin/env python3
"""Golden-byte tests for XAverius XGE event layouts."""
from __future__ import annotations

import json
import struct
import unittest
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "event-vectors.json"


def validate_event_wire(
    wire: bytes,
    byte_order: str,
    *,
    expected_extension_opcode: int | None = None,
    memory_heap_count: int | None = None,
) -> None:
    """Validate XGE framing and fields; validate heap index when device properties are known."""

    if len(wire) < 32:
        raise ValueError("truncated XGE header")
    if len(wire) % 4:
        raise ValueError("XGE event length must be divisible by four")
    if byte_order not in ("little", "big"):
        raise ValueError("unknown byte order")
    if wire[0] != 35:
        raise ValueError("response_type must be GenericEvent (35)")
    if wire[1] < 128:
        raise ValueError("extension major opcode must be in 128..255")
    if expected_extension_opcode is not None and wire[1] != expected_extension_opcode:
        raise ValueError("XGE extension opcode does not match negotiated XAverius opcode")
    declared = int.from_bytes(wire[4:8], byte_order)
    if 32 + declared * 4 != len(wire):
        raise ValueError("XGE length does not match wire bytes")
    if any(wire[10:32]):
        raise ValueError("XGE reserved header bytes must be zero")
    event_type = int.from_bytes(wire[8:10], byte_order)
    if event_type not in range(7):
        raise ValueError("unknown XAverius event type")
    expected_lengths = {0: 60, 1: 48, 2: 48, 3: 48, 4: 48, 5: 56, 6: 56}
    if len(wire) != expected_lengths[event_type]:
        raise ValueError("event total length does not match event type")
    value_ranges = []
    if event_type in EVENT_VALUE_RANGES:
        value_ranges.append(EVENT_VALUE_RANGES[event_type])
    if event_type in EVENT_SECONDARY_VALUE_RANGES:
        value_ranges.extend(EVENT_SECONDARY_VALUE_RANGES[event_type])
    for offset, allowed in value_ranges:
        if int.from_bytes(wire[offset:offset + 4], byte_order) not in allowed:
            raise ValueError("event-local value is outside its registered range")
    # ASYNC_ERROR permits zero for a non-device-related error and absent resource.
    for offset in (32,) if event_type in (1, 2, 3, 4, 5, 6) else ():
        if int.from_bytes(wire[offset:offset + 4], byte_order) == 0:
            raise ValueError("required event XID must be nonzero")
    if event_type == 0 and int.from_bytes(wire[36:40], byte_order) not in range(9):
        raise ValueError("XAverius error offset is outside the error registry")
    if event_type == 0:
        origin = int.from_bytes(wire[40:44], byte_order)
        submission_token = int.from_bytes(wire[44:52], byte_order)
        if origin == 1 and submission_token == 0:
            raise ValueError("ORIGIN_QUEUE_SUBMIT requires a nonzero submission_token")
    if event_type == 3 and memory_heap_count is not None:
        if not 0 <= memory_heap_count <= 0xFFFFFFFF:
            raise ValueError("memory_heap_count must be a CARD32")
        heap_index = int.from_bytes(wire[36:40], byte_order)
        if heap_index != 0xFFFFFFFF and heap_index >= memory_heap_count:
            raise ValueError("heap_index is outside the device memory heap registry")
    if event_type in (5, 6) and int.from_bytes(wire[48:56], byte_order) == 0:
        raise ValueError("terminal submission event token must be nonzero")
    for offset in EVENT_RESERVED_OFFSETS.get(event_type, ()):
        if wire[offset:offset + 4] != bytes(4):
            raise ValueError("reserved event field must be zero")


def encode_event(vector: dict) -> bytes:
    order = vector["byte_order"]
    if order not in ("little", "big"):
        raise ValueError("unknown byte order")
    endian = "<" if order == "little" else ">"
    total = vector["total_bytes"]
    if total < 32 or total % 4:
        raise ValueError("XGE event length must be >= 32 and divisible by four")
    if vector["extension_opcode"] not in range(128, 256):
        raise ValueError("extension major opcode must be in 128..255")
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
    wire = bytes(data)
    validate_event_wire(wire, order)
    return wire


EVENT_IDS = {
    "ASYNC_ERROR": 0, "DEVICE_LOST": 1, "DEVICE_STATUS_CHANGED": 2,
    "DEVICE_MEMORY_PRESSURE": 3, "DEVICE_IDLE": 4,
    "SUBMISSION_COMPLETE": 5, "SUBMISSION_FAILED": 6,
}
EVENT_VALUE_RANGES = {
    0: (40, (0, 1, 2, 3, 4, 5, 6)),  # ASYNC_ERROR.origin
    1: (36, (0, 1, 2, 3, 4, 5)),     # DEVICE_LOST.reason_code
    2: (36, (0, 1, 2)),              # DEVICE_STATUS_CHANGED.new_status
    # DEVICE_STATUS_CHANGED.reason_code uses the shared reason-code registry.
    3: (40, (0, 1, 2, 3)),            # DEVICE_MEMORY_PRESSURE.pressure_level
    4: (36, (0, 1, 2)),              # DEVICE_IDLE.idle_reason
    6: (44, (0, 1)),                 # SUBMISSION_FAILED.failure_class
}
EVENT_SECONDARY_VALUE_RANGES = {
    2: ((40, tuple(range(6))),),  # DEVICE_STATUS_CHANGED.reason_code
}
EVENT_RESERVED_OFFSETS = {0: (56,), 2: (44,), 3: (44,), 5: (44,)}


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

    def test_presentation_registry_ids_and_status_values_are_stable(self):
        compute = (ROOT / "registries" / "event-types.md").read_text(encoding="utf-8")
        presentation = (ROOT / "registries" / "presentation-events.md").read_text(encoding="utf-8")
        compute_section = re.search(
            r"^## Event type IDs\s*$([\s\S]*?)(?=^## |\Z)", compute, re.M
        )
        presentation_section = re.search(
            r"^## Event type IDs\s*$([\s\S]*?)(?=^## |\Z)", presentation, re.M
        )
        status_section = re.search(
            r"^## Presentation event status values\s*$([\s\S]*?)(?=^## |\Z)", presentation, re.M
        )
        self.assertIsNotNone(compute_section)
        self.assertIsNotNone(presentation_section)
        self.assertIsNotNone(status_section)
        row_pattern = r"^\|\s*(\d+)\s*\|\s*`?([A-Z_]+)`?\s*\|"
        compute_ids = {
            int(value): symbol for value, symbol in re.findall(row_pattern, compute_section.group(1), re.M)
        }
        presentation_ids = {
            int(value): symbol for value, symbol in re.findall(row_pattern, presentation_section.group(1), re.M)
        }
        status_values = {
            int(value): symbol for value, symbol in re.findall(row_pattern, status_section.group(1), re.M)
        }
        self.assertEqual(compute_ids, {value: name for name, value in EVENT_IDS.items()})
        self.assertEqual(presentation_ids, {7: "IMAGE_RELEASED", 8: "PRESENTATION_COMPLETE"})
        self.assertEqual(set(compute_ids).intersection(presentation_ids), set())
        self.assertEqual(set(compute_ids) | set(presentation_ids), set(range(9)))
        self.assertEqual(status_values, {
            0: "SUCCESS", 1: "OUT_OF_DATE", 2: "SURFACE_LOST",
            3: "DEVICE_LOST", 4: "PRESENTATION_FAILED",
        })
        self.assertIn("not part of compute-only v0.1", presentation)
        self.assertIn("must reject the presentation-only queue event-mask bits", presentation)

    def test_golden_event_bytes(self):
        self.assertEqual(len(self.vectors), 14)
        names = set()
        for vector in self.vectors:
            with self.subTest(vector=vector["name"]):
                self.assertNotIn(vector["name"], names)
                names.add(vector["name"])
                actual = encode_event(vector)
                self.assertEqual(actual.hex(), vector["wire_hex"])
                validate_event_wire(actual, vector["byte_order"])
                self.assertEqual(len(actual), vector["total_bytes"])
                self.assertEqual(actual[0], 35)
                self.assertEqual(actual[1], vector["extension_opcode"])
                self.assertEqual(int.from_bytes(actual[2:4], vector["byte_order"]), vector["sequence"])
                self.assertEqual(int.from_bytes(actual[4:8], vector["byte_order"]), vector["xge_length"])
                self.assertEqual(int.from_bytes(actual[8:10], vector["byte_order"]), vector["event_type"])
                self.assertEqual(actual[10:32], bytes(22))

    def test_golden_field_layouts_match_normative_event_chapters(self):
        document = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
        sizes = {"XID": 4, "CARD32": 4, "CARD64": 8}
        for event, fields in EVENT_FIELDS.items():
            match = re.search(
                r"^## `" + re.escape(event) + r"`\s*$([\s\S]*?)(?=^## |\Z)",
                document, re.M,
            )
            self.assertIsNotNone(match, f"missing normative event section {event}")
            body = match.group(1)
            expected = sorted((offset, size) for offset, size in fields.values())
            actual = []
            for line in body.splitlines():
                row = re.match(r"^\|\s*(\d+)\s*\|\s*(XID|CARD32|CARD64)\s*\|", line)
                if row:
                    actual.append((int(row.group(1)), sizes[row.group(2)]))
                    continue
                bullet = re.match(r"^\s*- Offset (\d+):\s*(.*)$", line)
                if bullet:
                    offset, tail = int(bullet.group(1)), bullet.group(2)
                    if re.search(r"\bCARD64\b", tail):
                        size = 8
                    elif re.search(r"\bCARD32\b|\bXID\b|Device-XID|Physical-Device-XID", tail):
                        size = 4
                    else:
                        continue
                    actual.append((offset, size))
            self.assertEqual(sorted(actual), expected, f"{event} offsets/sizes differ from EVENT_FIELDS")
            field_labels = {
                "device_xid": "Device-XID",
                "error_code": "`error_code`",
                "origin": "Origin-Werte",
                "submission_token": "`submission_token`",
                "resource_xid": "Ressourcen-XID",
                "reserved": "reserved",
                "reason_code": "`reason_code`",
                "device_generation": "`device_generation`",
                "physical_device_xid": "Physical-Device-XID",
                "new_status": "`new_status`",
                "heap_index": "`heap_index`",
                "pressure_level": "`pressure_level`",
                "idle_reason": "`idle_reason`",
                "queue_family_index": "`queue_family_index`",
                "queue_index": "`queue_index`",
                "failure_class": "`failure_class`",
            }
            for field in fields:
                label = field_labels[field]
                with self.subTest(event=event, field=field):
                    self.assertRegex(body, r"(?<![A-Za-z0-9_])" + re.escape(label.strip("`")) + r"(?![A-Za-z0-9_])",
                                 f"{event}.{field} missing from normative event chapter")
            length = re.search(r"Gesamtlänge:\s*(\d+) Bytes; XGE `length = (\d+)`", body)
            if not length:
                length = re.search(r"Gesamtlänge:\s*(\d+) Bytes; XGE `length = (\d+)`", body)
            self.assertIsNotNone(length, f"{event} is missing its normative total-length declaration")
            self.assertEqual(int(length.group(1)), max(offset + size for offset, size in expected))
            self.assertEqual(int(length.group(2)), (int(length.group(1)) - 32) // 4)

    def test_event_ids_and_vector_field_sets_match_registry(self):
        registry = (ROOT / "registries" / "event-types.md").read_text(encoding="utf-8")
        section = re.search(r"^## Event type IDs\s*$([\s\S]*?)(?=^## |\Z)", registry, re.M)
        self.assertIsNotNone(section)
        rows = {
            name: int(value)
            for value, name in re.findall(r"^\|\s*(\d+)\s*\|\s*`([A-Z_]+)`\s*\|", section.group(1), re.M)
        }
        self.assertEqual(rows, EVENT_IDS)
        for vector in self.vectors:
            with self.subTest(vector=vector["name"]):
                event = vector["event"]
                self.assertEqual(vector["event_type"], EVENT_IDS[event])
                self.assertEqual(set(vector["fields"]), set(EVENT_FIELDS[event]))
                self.assertEqual(vector["total_bytes"], max(
                    offset + size for offset, size in EVENT_FIELDS[event].values()
                ))
                self.assertEqual(vector["xge_length"], (vector["total_bytes"] - 32) // 4)

    def test_each_event_has_both_byte_orders(self):
        seen = {}
        for vector in self.vectors:
            seen.setdefault(vector["event"], set()).add(vector["byte_order"])
        self.assertEqual(set(seen), set(EVENT_IDS))
        self.assertTrue(all(orders == {"little", "big"} for orders in seen.values()))

    def test_rejects_invalid_raw_xge_common_header(self):
        vector = self.vectors[0]
        wire = bytearray(encode_event(vector))
        wire[0] = 34
        with self.assertRaisesRegex(ValueError, "GenericEvent"):
            validate_event_wire(bytes(wire), vector["byte_order"])

        wire = bytearray(encode_event(vector))
        wire[8:10] = (7).to_bytes(2, vector["byte_order"])
        with self.assertRaisesRegex(ValueError, "unknown XAverius event type"):
            validate_event_wire(bytes(wire), vector["byte_order"])

        with self.assertRaisesRegex(ValueError, "truncated XGE header"):
            validate_event_wire(bytes(31), "little")
        with self.assertRaisesRegex(ValueError, "divisible by four"):
            validate_event_wire(bytes(33), "little")
        with self.assertRaisesRegex(ValueError, "unknown byte order"):
            validate_event_wire(encode_event(vector), "native")

    def test_rejects_raw_reserved_header_byte(self):
        wire = bytearray(encode_event(self.vectors[0]))
        wire[31] = 1
        with self.assertRaisesRegex(ValueError, "reserved header"):
            validate_event_wire(bytes(wire), self.vectors[0]["byte_order"])

    def test_rejects_raw_xge_length_mismatch(self):
        vector = self.vectors[0]
        wire = bytearray(encode_event(vector))
        order = vector["byte_order"]
        wire[4:8] = (vector["xge_length"] + 1).to_bytes(4, order)
        with self.assertRaisesRegex(ValueError, "XGE length"):
            validate_event_wire(bytes(wire), order)

    def test_rejects_inconsistent_xge_length(self):
        import copy
        vector = copy.deepcopy(self.vectors[0])
        vector["xge_length"] += 1
        with self.assertRaisesRegex(ValueError, "XGE length"):
            encode_event(vector)

    def test_event_value_ranges_match_normative_registry(self):
        event_registry = (ROOT / "registries" / "event-types.md").read_text(encoding="utf-8")
        reason_registry = (ROOT / "registries" / "reason-codes.md").read_text(encoding="utf-8")
        sections = (
            ("ASYNC_ERROR.origin", 0, event_registry),
            ("DEVICE_LOST.reason_code", 1, reason_registry),
            ("DEVICE_STATUS_CHANGED.new_status", 2, event_registry),
            ("DEVICE_STATUS_CHANGED.reason_code", 2, reason_registry),
            ("DEVICE_MEMORY_PRESSURE.pressure_level", 3, event_registry),
            ("DEVICE_IDLE.idle_reason", 4, event_registry),
            ("SUBMISSION_FAILED.failure_class", 6, event_registry),
        )
        for heading, event_type, registry in sections:
            match = re.search(r"^## \x60" + re.escape(heading) + r"\x60\s*$([\s\S]*?)(?=^## |\Z)", registry, re.M)
            is_reason_code = heading.endswith(".reason_code")
            self.assertIsNotNone(match, f"missing registry section {heading}") if not is_reason_code else None
            source = registry if is_reason_code else match.group(1)
            values = {int(value) for value in re.findall(r"^\|\s*(\d+)\s*\|", source, re.M)}
            if heading == "DEVICE_LOST.reason_code":
                self.assertEqual(values, set(EVENT_VALUE_RANGES[event_type][1]), heading)
            elif heading == "DEVICE_STATUS_CHANGED.reason_code":
                self.assertEqual(values, set(EVENT_SECONDARY_VALUE_RANGES[event_type][0][1]), heading)
            else:
                self.assertEqual(values, set(EVENT_VALUE_RANGES[event_type][1]), heading)

    def test_event_local_enum_values_match_normative_chapters(self):
        events = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
        registry = (ROOT / "registries" / "event-types.md").read_text(encoding="utf-8")

        cases = (
            ("ASYNC_ERROR", "ASYNC_ERROR.origin"),
            ("DEVICE_STATUS_CHANGED", "DEVICE_STATUS_CHANGED.new_status"),
            ("DEVICE_MEMORY_PRESSURE", "DEVICE_MEMORY_PRESSURE.pressure_level"),
            ("DEVICE_IDLE", "DEVICE_IDLE.idle_reason"),
            ("SUBMISSION_FAILED", "SUBMISSION_FAILED.failure_class"),
        )
        for event, registry_heading in cases:
            registry_match = re.search(
                r"^## \x60" + re.escape(registry_heading)
                + r"\x60\s*$([\s\S]*?)(?=^## |\Z)",
                registry, re.M,
            )
            self.assertIsNotNone(registry_match, f"missing registry section {registry_heading}")
            expected = [
                (int(value), symbol)
                for value, symbol in re.findall(
                    r"^\|\s*(\d+)\s*\|\s*\x60([A-Z_]+)\x60\s*\|",
                    registry_match.group(1), re.M,
                )
            ]

            event_match = re.search(
                r"^## \x60" + re.escape(event) + r"\x60\s*$"
                + r"([\s\S]*?)(?=^## |\Z)",
                events, re.M,
            )
            self.assertIsNotNone(event_match, f"missing event chapter {event}")
            actual = [
                (int(value), symbol)
                for value, symbol in re.findall(
                    r"^\s*-\s*(\d+):\s*\x60([A-Z_]+)\x60\s*$",
                    event_match.group(1), re.M,
                )
            ]
            with self.subTest(event=event):
                self.assertEqual(actual, expected, f"{event} enum differs from central registry")

        # Both events deliberately share the same reason-code namespace rather
        # than defining a second, potentially divergent local enumeration.
        for event in ("DEVICE_LOST", "DEVICE_STATUS_CHANGED"):
            event_match = re.search(
                r"^## \x60" + re.escape(event) + r"\x60\s*$"
                + r"([\s\S]*?)(?=^## |\Z)",
                events, re.M,
            )
            self.assertIsNotNone(event_match)
            self.assertIn("shared", event_match.group(1).lower())
            self.assertIn("reason-code registry", event_match.group(1).lower())

    def test_memory_pressure_heap_index_uses_physical_device_heap_count(self):
        for order in ("little", "big"):
            vector = next(v for v in self.vectors
                          if v["event"] == "DEVICE_MEMORY_PRESSURE" and v["byte_order"] == order)
            wire = bytearray(encode_event(vector))
            # UINT32_MAX is the normative sentinel for an unspecified heap.
            validate_event_wire(bytes(wire), order, memory_heap_count=1)
            # A concrete index is valid only if it is below memory_heap_count.
            wire[36:40] = (0).to_bytes(4, order)
            validate_event_wire(bytes(wire), order, memory_heap_count=1)
            wire[36:40] = (1).to_bytes(4, order)
            with self.subTest(order=order):
                with self.assertRaisesRegex(ValueError, "heap_index"):
                    validate_event_wire(bytes(wire), order, memory_heap_count=1)
            # Without device properties the structural validator cannot reject
            # an index based on a heap count it does not know.
            validate_event_wire(bytes(wire), order)

    def test_async_error_queue_submit_origin_requires_token(self):
        for order in ("little", "big"):
            vector = next(v for v in self.vectors
                          if v["event"] == "ASYNC_ERROR" and v["byte_order"] == order)
            wire = bytearray(encode_event(vector))
            wire[40:44] = (1).to_bytes(4, order)  # ORIGIN_QUEUE_SUBMIT
            # A QueueSubmit-origin diagnostic with the accepted submission's
            # token is valid; the same event with token zero is not.
            validate_event_wire(bytes(wire), order)
            wire[44:52] = bytes(8)
            with self.subTest(order=order):
                with self.assertRaisesRegex(ValueError, "ORIGIN_QUEUE_SUBMIT"):
                    validate_event_wire(bytes(wire), order)

    def test_async_error_token_rules_match_acceptance_contract(self):
        events = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
        conformance = (ROOT / "spec" / "conformance.md").read_text(encoding="utf-8")
        queue = (ROOT / "spec" / "queue-submission.md").read_text(encoding="utf-8")

        # The wire validator can check the structural origin/token relation;
        # whether a token refers to an actually accepted submission is a
        # server-state invariant and must remain explicit in the normative spec.
        self.assertIn(
            "Bei \x60origin = ORIGIN_QUEUE_SUBMIT\x60 MUSS \x60submission_token\x60 daher ungleich null sein",
            events,
        )
        self.assertIn(
            "ein nicht-null Token darf niemals eine abgewiesene \x60QueueSubmit\x60-Anforderung bezeichnen",
            events,
        )
        self.assertIn(
            "ein abgewiesener \x60QueueSubmit\x60 darf nie als Token-Ziel eines \x60ASYNC_ERROR\x60 erscheinen",
            conformance,
        )
        self.assertIn("Jeder synchron abgewiesene Request bleibt atomar und erzeugt kein Submission-Event.", queue)
        self.assertIn("Ein synchroner Fehler darf kein `ASYNC_ERROR` für eine nicht angenommene Submission erzeugen.", queue)

        for order in ("little", "big"):
            vector = next(v for v in self.vectors
                          if v["event"] == "ASYNC_ERROR" and v["byte_order"] == order)
            for origin in (0, 2, 3, 4, 5, 6):
                wire = bytearray(encode_event(vector))
                wire[40:44] = origin.to_bytes(4, order)
                wire[44:52] = bytes(8)
                with self.subTest(order=order, origin=origin, token=0):
                    validate_event_wire(bytes(wire), order)

            wire = bytearray(encode_event(vector))
            wire[40:44] = (1).to_bytes(4, order)
            wire[44:52] = (0x1122334455667788).to_bytes(8, order)
            validate_event_wire(bytes(wire), order)
            wire[44:52] = bytes(8)
            with self.subTest(order=order, origin=1, token=0):
                with self.assertRaisesRegex(ValueError, "ORIGIN_QUEUE_SUBMIT"):
                    validate_event_wire(bytes(wire), order)

    def test_rejects_invalid_event_local_values(self):
        cases = (
            ("ASYNC_ERROR", 40, 7),
            ("DEVICE_LOST", 36, 6),
            ("DEVICE_STATUS_CHANGED", 36, 3),
            ("DEVICE_STATUS_CHANGED", 40, 6),
            ("DEVICE_MEMORY_PRESSURE", 40, 4),
            ("DEVICE_IDLE", 36, 3),
            ("SUBMISSION_FAILED", 44, 2),
        )
        for event, offset, invalid in cases:
            for order in ("little", "big"):
                vector = next(v for v in self.vectors if v["event"] == event and v["byte_order"] == order)
                wire = bytearray(encode_event(vector))
                wire[offset:offset + 4] = invalid.to_bytes(4, order)
                with self.subTest(event=event, order=order):
                    with self.assertRaisesRegex(ValueError, "event-local value"):
                        validate_event_wire(bytes(wire), order)

    def test_rejects_event_specific_length_mismatch(self):
        vector = next(v for v in self.vectors if v["event"] == "ASYNC_ERROR")
        wire = bytearray(encode_event(vector))
        del wire[-4:]
        order = vector["byte_order"]
        wire[4:8] = (6).to_bytes(4, order)
        with self.assertRaisesRegex(ValueError, "total length does not match event type"):
            validate_event_wire(bytes(wire), order)

    def test_rejects_invalid_extension_major_opcode(self):
        vector = self.vectors[0]
        wire = bytearray(encode_event(vector))
        wire[1] = 127
        with self.assertRaisesRegex(ValueError, "extension major opcode"):
            validate_event_wire(bytes(wire), vector["byte_order"])

    def test_raw_event_must_use_the_connection_xa_verius_opcode(self):
        for vector in self.vectors:
            order = vector["byte_order"]
            wire = bytearray(encode_event(vector))
            validate_event_wire(bytes(wire), order, expected_extension_opcode=vector["extension_opcode"])
            wire[1] = 255 if vector["extension_opcode"] != 255 else 254
            with self.subTest(event=vector["event"], order=order):
                with self.assertRaisesRegex(ValueError, "does not match negotiated XAverius opcode"):
                    validate_event_wire(bytes(wire), order, expected_extension_opcode=vector["extension_opcode"])

    def test_every_event_type_rejects_a_wrong_total_length(self):
        for event in EVENT_IDS:
            for order in ("little", "big"):
                vector = next(v for v in self.vectors if v["event"] == event and v["byte_order"] == order)
                wire = bytearray(encode_event(vector))
                del wire[-4:]
                wire[4:8] = ((len(wire) - 32) // 4).to_bytes(4, order)
                with self.subTest(event=event, order=order):
                    with self.assertRaisesRegex(ValueError, "total length does not match event type"):
                        validate_event_wire(bytes(wire), order)

    def test_rejects_raw_event_reserved_payload_fields(self):
        cases = (("ASYNC_ERROR", 56), ("DEVICE_STATUS_CHANGED", 44),
                 ("DEVICE_MEMORY_PRESSURE", 44), ("SUBMISSION_COMPLETE", 44))
        for event, offset in cases:
            for order in ("little", "big"):
                vector = next(v for v in self.vectors if v["event"] == event and v["byte_order"] == order)
                wire = bytearray(encode_event(vector))
                wire[offset:offset + 4] = (1).to_bytes(4, order)
                with self.subTest(event=event, order=order):
                    with self.assertRaisesRegex(ValueError, "reserved event field"):
                        validate_event_wire(bytes(wire), order)

    def test_required_event_xids_are_nonzero(self):
        for event in ("DEVICE_LOST", "DEVICE_STATUS_CHANGED", "DEVICE_MEMORY_PRESSURE",
                      "DEVICE_IDLE", "SUBMISSION_COMPLETE", "SUBMISSION_FAILED"):
            for order in ("little", "big"):
                vector = next(v for v in self.vectors if v["event"] == event and v["byte_order"] == order)
                wire = bytearray(encode_event(vector))
                wire[32:36] = bytes(4)
                with self.subTest(event=event, order=order):
                    with self.assertRaisesRegex(ValueError, "required event XID"):
                        validate_event_wire(bytes(wire), order)

    def test_terminal_submission_events_require_nonzero_tokens(self):
        for event in ("SUBMISSION_COMPLETE", "SUBMISSION_FAILED"):
            for order in ("little", "big"):
                vector = next(v for v in self.vectors if v["event"] == event and v["byte_order"] == order)
                wire = bytearray(encode_event(vector))
                wire[48:56] = bytes(8)
                with self.subTest(event=event, order=order):
                    with self.assertRaisesRegex(ValueError, "token must be nonzero"):
                        validate_event_wire(bytes(wire), order)

    def test_async_error_xids_are_optional_but_invalid_error_offset_is_rejected(self):
        for order in ("little", "big"):
            vector = next(v for v in self.vectors if v["event"] == "ASYNC_ERROR" and v["byte_order"] == order)
            wire = bytearray(encode_event(vector))
            wire[32:36] = bytes(4)
            wire[52:56] = bytes(4)
            validate_event_wire(bytes(wire), order)
            wire[36:40] = (9).to_bytes(4, order)
            with self.subTest(order=order):
                with self.assertRaisesRegex(ValueError, "error offset"):
                    validate_event_wire(bytes(wire), order)

    def test_async_error_accepts_last_registered_error_offset(self):
        for order in ("little", "big"):
            vector = next(v for v in self.vectors if v["event"] == "ASYNC_ERROR" and v["byte_order"] == order)
            wire = bytearray(encode_event(vector))
            wire[36:40] = (8).to_bytes(4, order)
            validate_event_wire(bytes(wire), order)
            wire[36:40] = (9).to_bytes(4, order)
            with self.assertRaisesRegex(ValueError, "error offset"):
                validate_event_wire(bytes(wire), order)

    def test_async_error_semantics_match_event_chapter_and_registries(self):
        events = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
        event_registry = (ROOT / "registries" / "event-types.md").read_text(encoding="utf-8")
        error_registry = (ROOT / "registries" / "errors.md").read_text(encoding="utf-8")
        error_spec = (ROOT / "spec" / "errors.md").read_text(encoding="utf-8")

        for document, label in ((events, "event chapter"), (event_registry, "event registry")):
            with self.subTest(document=label):
                self.assertIn("first_error + offset", document)
                self.assertIn("QueueSubmit", document)
                self.assertIn("SUBMISSION_FAILED", document)
                self.assertIn("ASYNC_ERROR", document)

        offsets = {
            int(value)
            for value in re.findall(r"^\|\s*(\d+)\s*\|\s*`[A-Z_]+`\s*\|", error_registry, re.M)
        }
        self.assertEqual(offsets, set(range(9)))
        self.assertIn("For an accepted `QueueSubmit`", error_spec)
        self.assertIn("MUST NOT be reported as a delayed X11 request error", error_spec)
        self.assertIn("nicht den absoluten X11-Fehlercode", events)
        self.assertIn("not the absolute X11 error code", event_registry)

    def test_async_error_codes_match_central_error_registry(self):
        registry = (ROOT / "registries" / "errors.md").read_text(encoding="utf-8")
        offsets = {
            int(value)
            for value in re.findall(r"^\|\s*(\d+)\s*\|\s*\x60[A-Z_]+\x60\s*\|\s*$", registry, re.M)
        }
        self.assertEqual(offsets, set(range(9)))
        for vector in self.vectors:
            if vector["event"] == "ASYNC_ERROR":
                with self.subTest(vector=vector["name"]):
                    self.assertIn(vector["fields"]["error_code"], offsets)

    def test_rejects_nonzero_reserved_field(self):
        import copy
        vector = copy.deepcopy(next(v for v in self.vectors if v["event"] == "SUBMISSION_COMPLETE"))
        vector["fields"]["reserved"] = 1
        with self.assertRaisesRegex(ValueError, "reserved"):
            encode_event(vector)


if __name__ == "__main__":
    unittest.main(verbosity=2)
