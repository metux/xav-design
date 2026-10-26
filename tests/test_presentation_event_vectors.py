#!/usr/bin/env python3
"""Golden wire checks for the presentation-only XGE events."""
from __future__ import annotations

import json
import re
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "registries" / "presentation-events.md"
SPEC = ROOT / "spec" / "events.md"
FIXTURE = ROOT / "tests" / "presentation-event-vectors.json"

EVENTS = {
    "IMAGE_RELEASED": 7,
    "PRESENTATION_COMPLETE": 8,
}
STATUS = {
    "SUCCESS": 0,
    "OUT_OF_DATE": 1,
    "SURFACE_LOST": 2,
    "DEVICE_LOST": 3,
    "PRESENTATION_FAILED": 4,
}


def encode_event(name: str, byte_order: str, *, status: int = 0) -> bytes:
    if name not in EVENTS:
        raise ValueError("unknown presentation event")
    if byte_order not in ("little", "big"):
        raise ValueError("unknown byte order")
    if name == "PRESENTATION_COMPLETE" and status not in STATUS.values():
        raise ValueError("invalid presentation status")
    endian = "<" if byte_order == "little" else ">"
    data = bytearray(64)
    struct.pack_into(endian + "BBH I H", data, 0, 35, 200, 0x1234, 8, EVENTS[name])
    struct.pack_into(endian + "IIIII", data, 32, 0x01020304, 1, 2, 0x11223344, 3)
    if name == "PRESENTATION_COMPLETE":
        struct.pack_into(endian + "I", data, 52, status)
    else:
        struct.pack_into(endian + "I", data, 52, 0)
    struct.pack_into(endian + "Q", data, 56, 0x0102030405060708)
    return bytes(data)


def validate_event(wire: bytes, byte_order: str, name: str) -> None:
    if byte_order not in ("little", "big"):
        raise ValueError("unknown byte order")
    if name not in EVENTS:
        raise ValueError("unknown presentation event")
    if len(wire) != 64:
        raise ValueError("presentation event must be 64 bytes")
    if len(wire) % 4:
        raise ValueError("event size must be divisible by four")
    if wire[0] != 35:
        raise ValueError("response_type must be GenericEvent")
    endian = "<" if byte_order == "little" else ">"
    if struct.unpack_from(endian + "I", wire, 4)[0] != 8:
        raise ValueError("XGE length must be 8")
    if struct.unpack_from(endian + "H", wire, 8)[0] != EVENTS[name]:
        raise ValueError("event type ID mismatch")
    if any(wire[10:32]):
        raise ValueError("XGE reserved header bytes must be zero")
    if struct.unpack_from(endian + "I", wire, 52)[0] not in (
        STATUS.values() if name == "PRESENTATION_COMPLETE" else (0,)
    ):
        raise ValueError("invalid event status or reserved field")
    if struct.unpack_from(endian + "Q", wire, 56)[0] == 0:
        raise ValueError("presentation token must be nonzero")


class PresentationEventWireTests(unittest.TestCase):
    def test_registry_ids_and_statuses_match_spec(self) -> None:
        registry = REGISTRY.read_text(encoding="utf-8")
        spec = SPEC.read_text(encoding="utf-8")
        rows = {
            symbol: int(value)
            for value, symbol in re.findall(
                r"^\|\s*(\d+)\s*\|\s*`([A-Z_]+)`\s*\|\s*$",
                registry, re.M,
            )
        }
        self.assertEqual({name: rows[name] for name in EVENTS}, EVENTS)
        for symbol, value in STATUS.items():
            self.assertRegex(registry, rf"\|\s*{value}\s*\|\s*{symbol}\s*\|")
        for name in EVENTS:
            section = re.search(
                rf"^## `{name}`\s*$([\s\S]*?)(?=^## |\Z)", spec, re.M
            )
            self.assertIsNotNone(section)
            self.assertRegex(section.group(1), r"Total length:\s*64 bytes; XGE `length\s*=\s*8`")

    def test_golden_bytes_both_byte_orders(self) -> None:
        for order in ("little", "big"):
            for name in EVENTS:
                with self.subTest(order=order, event=name):
                    wire = encode_event(name, order, status=STATUS["PRESENTATION_FAILED"])
                    self.assertEqual(len(wire), 64)
                    self.assertEqual(wire[0], 35)
                    self.assertEqual(wire[1], 200)
                    self.assertEqual(wire[8:10], EVENTS[name].to_bytes(2, order))
                    self.assertEqual(wire[56:64], (0x0102030405060708).to_bytes(8, order))
                    validate_event(wire, order, name)

    def test_image_released_reserved_field_is_zero(self) -> None:
        for order in ("little", "big"):
            wire = encode_event("IMAGE_RELEASED", order)
            self.assertEqual(wire[52:56], bytes(4))
            validate_event(wire, order, "IMAGE_RELEASED")

    def test_presentation_payload_fields_match_event_contract(self) -> None:
        """Check every event-specific field, not only framing and token."""
        values = {
            32: (0x01020304, 4),
            36: (1, 4),
            40: (2, 4),
            44: (0x11223344, 4),
            48: (3, 4),
            56: (0x0102030405060708, 8),
        }
        for order in ("little", "big"):
            with self.subTest(order=order):
                released = encode_event("IMAGE_RELEASED", order)
                complete = encode_event(
                    "PRESENTATION_COMPLETE", order,
                    status=STATUS["SURFACE_LOST"],
                )
                for offset, (value, width) in values.items():
                    expected = value.to_bytes(width, order)
                    self.assertEqual(released[offset:offset + width], expected)
                    self.assertEqual(complete[offset:offset + width], expected)
                self.assertEqual(released[52:56], bytes(4))
                self.assertEqual(
                    complete[52:56],
                    STATUS["SURFACE_LOST"].to_bytes(4, order),
                )
                validate_event(released, order, "IMAGE_RELEASED")
                validate_event(complete, order, "PRESENTATION_COMPLETE")

    def test_all_terminal_statuses_are_encoded_in_both_byte_orders(self) -> None:
        for order in ("little", "big"):
            for name, status in STATUS.items():
                with self.subTest(order=order, status=name):
                    wire = encode_event("PRESENTATION_COMPLETE", order, status=status)
                    self.assertEqual(wire[52:56], status.to_bytes(4, order))
                    validate_event(wire, order, "PRESENTATION_COMPLETE")

    def test_committed_golden_vectors_match_every_payload_field(self) -> None:
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(fixture.get("schema_version"), 1)
        vectors = fixture["vectors"]
        self.assertEqual(len(vectors), 4)
        self.assertEqual({v["byte_order"] for v in vectors}, {"little", "big"})
        self.assertEqual({v["event"] for v in vectors}, set(EVENTS))
        seen = set()
        for vector in vectors:
            with self.subTest(vector=vector["name"]):
                self.assertNotIn(vector["name"], seen)
                seen.add(vector["name"])
                wire = bytes.fromhex(vector["wire_hex"])
                order = vector["byte_order"]
                endian = "<" if order == "little" else ">"
                fields = vector["fields"]
                validate_event(wire, order, vector["event"])
                self.assertEqual(len(wire), vector["total_bytes"])
                self.assertEqual(wire[1], vector["extension_opcode"])
                self.assertEqual(struct.unpack_from(endian + "H", wire, 2)[0], vector["sequence"])
                self.assertEqual(struct.unpack_from(endian + "I", wire, 4)[0], vector["length"])
                self.assertEqual(struct.unpack_from(endian + "H", wire, 8)[0], vector["event_id"])
                self.assertEqual(vector["event_id"], EVENTS[vector["event"]])
                for field, offset in (("device_xid",32),("queue_family_index",36),("queue_index",40),("swapchain_xid",44),("image_index",48)):
                    self.assertEqual(struct.unpack_from(endian + "I", wire, offset)[0], fields[field])
                payload_word = struct.unpack_from(endian + "I", wire, 52)[0]
                if vector["event"] == "IMAGE_RELEASED":
                    self.assertEqual(payload_word, fields["reserved"])
                else:
                    self.assertEqual(payload_word, fields["status"])
                token = int(fields["presentation_token_hex"], 16)
                self.assertEqual(struct.unpack_from(endian + "Q", wire, 56)[0], token)

    def test_invalid_presentation_status_is_rejected(self) -> None:
        for order in ("little", "big"):
            for status in (-1, 5, 0xFFFFFFFF):
                with self.subTest(order=order, status=status):
                    with self.assertRaisesRegex(ValueError, "invalid presentation status"):
                        encode_event("PRESENTATION_COMPLETE", order, status=status)


    def test_malformed_serialized_events_are_rejected(self) -> None:
        """Reject invalid wire bytes, not just invalid encoder arguments."""
        for order in ("little", "big"):
            endian = "<" if order == "little" else ">"
            cases = (
                ("xge_length", "PRESENTATION_COMPLETE", 4, "I", 7,
                 "XGE length must be 8"),
                ("wrong_event_type", "PRESENTATION_COMPLETE", 8, "H", 7,
                 "event type ID mismatch"),
                ("nonzero_header_reserved", "PRESENTATION_COMPLETE", 10, "H", 1,
                 "XGE reserved header bytes must be zero"),
                ("invalid_completion_status", "PRESENTATION_COMPLETE", 52, "I", 5,
                 "invalid event status or reserved field"),
                ("nonzero_release_reserved", "IMAGE_RELEASED", 52, "I", 1,
                 "invalid event status or reserved field"),
                ("zero_presentation_token", "PRESENTATION_COMPLETE", 56, "Q", 0,
                 "presentation token must be nonzero"),
            )
            for label, name, offset, fmt, value, message in cases:
                with self.subTest(order=order, case=label):
                    wire = bytearray(encode_event(
                        name, order, status=STATUS["SUCCESS"]
                    ))
                    struct.pack_into(endian + fmt, wire, offset, value)
                    with self.assertRaisesRegex(ValueError, message):
                        validate_event(bytes(wire), order, name)

    def test_validator_rejects_unknown_byte_order(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown byte order"):
            validate_event(encode_event("IMAGE_RELEASED", "little"),
                           "middle", "IMAGE_RELEASED")


if __name__ == "__main__":
    unittest.main()
