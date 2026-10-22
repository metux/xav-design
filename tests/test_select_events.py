#!/usr/bin/env python3
"""SelectEvents wire, registry, validation, and lifecycle contract tests."""
from __future__ import annotations

import re
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVENTS = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
LIFETIME = (ROOT / "spec" / "resource-lifetime.md").read_text(encoding="utf-8")
SUBMISSIONS = (ROOT / "spec" / "queue-submission.md").read_text(encoding="utf-8")
REGISTRY = (ROOT / "registries" / "event-types.md").read_text(encoding="utf-8")
REQUESTS = (ROOT / "registries" / "request-subopcodes.md").read_text(encoding="utf-8")

SUBOPCODE = 40
SCOPE_CONNECTION, SCOPE_DEVICE, SCOPE_QUEUE = range(3)
CONNECTION_MASK = 0x1
DEVICE_MASK = 0x3
QUEUE_MASK = 0x3
EVENT_IDS = {
    "DEVICE_STATUS_CHANGED": 2,
    "DEVICE_MEMORY_PRESSURE": 3,
    "DEVICE_IDLE": 4,
    "SUBMISSION_COMPLETE": 5,
    "SUBMISSION_FAILED": 6,
}


def encode_select_events(byte_order: str, *, extension_opcode: int = 200,
                         scope: int = 0, device_xid: int = 0,
                         queue_family_index: int = 0, queue_index: int = 0,
                         event_mask: int = 0, flags: int = 0,
                         reserved_header: int = 0, reserved_payload: int = 0) -> bytes:
    """Encode the fixed 32-byte SelectEvents request, including X11 framing."""
    if byte_order not in ("little", "big"):
        raise ValueError("unknown byte order")
    if extension_opcode not in range(128, 256):
        raise ValueError("invalid extension opcode")
    if flags != 0 or reserved_header != 0 or reserved_payload != 0:
        raise ValueError("reserved field must be zero")
    allowed = {0: CONNECTION_MASK, 1: DEVICE_MASK, 2: QUEUE_MASK}.get(scope)
    if allowed is None:
        raise ValueError("unknown scope")
    if event_mask & ~allowed:
        raise ValueError("invalid event mask bits")
    if scope == SCOPE_CONNECTION and (device_xid or queue_family_index or queue_index):
        raise ValueError("invalid CONNECTION scope fields")
    if scope == SCOPE_DEVICE and (not device_xid or queue_family_index or queue_index):
        raise ValueError("invalid DEVICE scope fields")
    if scope == SCOPE_QUEUE and not device_xid:
        raise ValueError("invalid QUEUE scope fields")
    endian = "<" if byte_order == "little" else ">"
    wire = bytearray(32)
    struct.pack_into(endian + "BBH", wire, 0, extension_opcode, 0, 8)
    struct.pack_into(endian + "BBH", wire, 4, SUBOPCODE, flags, reserved_header)
    struct.pack_into(endian + "IIIII", wire, 8, scope, device_xid,
                     queue_family_index, queue_index, event_mask)
    struct.pack_into(endian + "I", wire, 28, reserved_payload)
    return bytes(wire)


class SelectEventsContractTests(unittest.TestCase):
    def test_wire_layout_and_length_in_both_byte_orders(self):
        for order in ("little", "big"):
            with self.subTest(byte_order=order):
                wire = encode_select_events(
                    order, scope=SCOPE_QUEUE, device_xid=0x10203040,
                    queue_family_index=2, queue_index=1, event_mask=3,
                )
                endian = "<" if order == "little" else ">"
                self.assertEqual(len(wire), 32)
                self.assertEqual(struct.unpack_from(endian + "BBH", wire, 0),
                                 (200, 0, 8))
                self.assertEqual(struct.unpack_from(endian + "BBH", wire, 4),
                                 (SUBOPCODE, 0, 0))
                self.assertEqual(struct.unpack_from(endian + "IIIII", wire, 8),
                                 (2, 0x10203040, 2, 1, 3))
                self.assertEqual(wire[28:32], bytes(4))

    def test_rejects_reserved_fields_invalid_scope_and_mask_bits(self):
        bad = (
            {"flags": 1},
            {"reserved_header": 1},
            {"reserved_payload": 1},
            {"scope": 3},
            {"scope": SCOPE_CONNECTION, "device_xid": 1},
            {"scope": SCOPE_CONNECTION, "queue_index": 1},
            {"scope": SCOPE_DEVICE, "device_xid": 9, "queue_family_index": 1},
            {"scope": SCOPE_DEVICE, "device_xid": 9, "event_mask": 4},
            {"scope": SCOPE_QUEUE, "device_xid": 9, "event_mask": 4},
            {"scope": SCOPE_QUEUE, "device_xid": 0},
        )
        for kwargs in bad:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                encode_select_events("little", **kwargs)

    def test_scope_masks_and_event_ids_match_normative_registry(self):
        block = re.search(
            r"\| Scope \| Bit \| Event \|\s*\n\|[^\n]+\n((?:\|.*\n)+)",
            EVENTS,
        )
        self.assertIsNotNone(block, "missing normative SelectEvents mask table")
        rows = re.findall(r"^\| `(CONNECTION|DEVICE|QUEUE)` \| (\d+) \| `([A-Z_]+)` \|$",
                          block.group(1), re.M)
        actual = {(scope, int(bit), event) for scope, bit, event in rows}
        expected = {
            ("CONNECTION", 0, "DEVICE_STATUS_CHANGED"),
            ("DEVICE", 0, "DEVICE_MEMORY_PRESSURE"),
            ("DEVICE", 1, "DEVICE_IDLE"),
            ("QUEUE", 0, "SUBMISSION_COMPLETE"),
            ("QUEUE", 1, "SUBMISSION_FAILED"),
        }
        self.assertEqual(actual, expected)
        registry_section = re.search(
            r"^## Event type IDs\s*$([\s\S]*?)(?=^## |\Z)", REGISTRY, re.M
        )
        self.assertIsNotNone(registry_section)
        registered = {
            name: int(value) for value, name in re.findall(
                r"^\|\s*(\d+)\s*\|\s*`([A-Z_]+)`\s*\|$",
                registry_section.group(1), re.M
            )
        }
        for event, value in EVENT_IDS.items():
            self.assertEqual(registered.get(event), value, event)

    def test_request_registry_assigns_select_events_subopcode_40(self):
        row = re.search(r"^\| `SelectEvents` \| (\d+) \| Void \|", REQUESTS, re.M)
        self.assertIsNotNone(row)
        self.assertEqual(int(row.group(1)), SUBOPCODE)
        self.assertIn("32 Bytes", EVENTS)
        self.assertIn("ersetzt atomar die bisherige Maske", EVENTS)

    def test_mask_replacement_and_destroy_device_scope_cleanup_are_normative(self):
        self.assertIn("event_mask = 0", EVENTS)
        self.assertIn("entfernt keine Auswahl anderer Scopes", EVENTS)
        self.assertIn("werden seine Device- und Queue-Auswahlen entfernt", EVENTS)
        self.assertIn("Bei jedem Fehler bleibt die vorherige Auswahl unverändert", EVENTS)
        self.assertIn("keine neuen Events mit der zerstörten `device_xid`", EVENTS)

    def test_submission_terminal_event_is_selected_at_linearization_point(self):
        required = (
            "bei Eintritt des terminalen Submission-Ergebnisses",
            "gemeinsamen serialisierten Serverzustand",
            "Der erfolgreiche `SelectEvents`-Request wirkt ab seinem Linearisierungspunkt",
            "der dann geltende Queue-Maske",
            "bilden gegenüber `DestroyDevice` eine unteilbare Entscheidung",
            "kein neues Event für dessen zerstörte Device-XID eingereiht",
            "darf diese Entscheidung nicht nachträglich ändern",
            "Pro angenommener Submission darf niemals sowohl `SUBMISSION_COMPLETE` als auch `SUBMISSION_FAILED`",
        )
        for clause in required:
            with self.subTest(clause=clause):
                self.assertIn(clause, EVENTS)

    def test_lifetime_and_submission_specs_preserve_terminal_state_independently_of_delivery(self):
        self.assertIn("Nach erfolgreicher Verarbeitung von `DestroyDevice`", EVENTS)
        self.assertIn("bereits vorher in den X11-Ausgabestrom eingereihte Events bleiben unberührt", EVENTS)
        self.assertIn("ändert nicht den internen terminalen Ausgang der Submission", EVENTS)
        self.assertIn("Jeder synchron abgewiesene Request bleibt atomar und erzeugt kein Submission-Event", SUBMISSIONS)
        self.assertIn("Ein angenommener `QueueSubmit` ist nicht automatisch abgeschlossen", SUBMISSIONS)
        self.assertIn("keine neuen Events mit der zerstörten", LIFETIME)


if __name__ == "__main__":
    unittest.main()
