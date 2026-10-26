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


def decode_select_events(wire: bytes, byte_order: str, *, extension_opcode: int = 200):
    """Validate and decode an actual SelectEvents wire packet, not just arguments."""
    if byte_order not in ("little", "big"):
        raise ValueError("unknown byte order")
    if len(wire) != 32:
        raise ValueError("wrong packet size")
    endian = "<" if byte_order == "little" else ">"
    major, minor, words = struct.unpack_from(endian + "BBH", wire, 0)
    if major != extension_opcode or not 128 <= major <= 255:
        raise ValueError("wrong extension opcode")
    if minor != 0 or words != 8:
        raise ValueError("wrong X11 request framing")
    subopcode, flags, reserved_header = struct.unpack_from(endian + "BBH", wire, 4)
    if subopcode != SUBOPCODE:
        raise ValueError("wrong subopcode")
    if flags or reserved_header:
        raise ValueError("reserved header field must be zero")
    scope, device_xid, family, queue, mask, reserved_payload = struct.unpack_from(
        endian + "IIIIII", wire, 8
    )
    if reserved_payload:
        raise ValueError("reserved payload field must be zero")
    # Reuse the canonical field constraints after parsing the bytes. Encoding
    # also rejects invalid scope-specific fields and masks.
    encode_select_events(
        byte_order, extension_opcode=major, scope=scope, device_xid=device_xid,
        queue_family_index=family, queue_index=queue, event_mask=mask,
        flags=flags, reserved_header=reserved_header, reserved_payload=reserved_payload,
    )
    return {
        "scope": scope, "device_xid": device_xid,
        "queue_family_index": family, "queue_index": queue, "event_mask": mask,
    }


class SelectionRaceModel:
    """Small executable model of the normative event-selection linearization rules."""

    def __init__(self):
        self.connection_mask = 0
        self.device_masks = {}
        self.queue_masks = {}
        self.destroyed_devices = set()
        self.queued_events = []
        self.terminal_tokens = set()

    def select_queue(self, device, family, queue, mask):
        if device in self.destroyed_devices:
            raise ValueError("device is destroyed")
        key = (device, family, queue)
        if mask:
            self.queue_masks[key] = mask
        else:
            self.queue_masks.pop(key, None)

    def destroy_device(self, device):
        self.destroyed_devices.add(device)
        self.device_masks.pop(device, None)
        self.queue_masks = {key: value for key, value in self.queue_masks.items()
                            if key[0] != device}

    def terminal(self, device, family, queue, token, outcome):
        if token in self.terminal_tokens:
            raise ValueError("submission already terminal")
        self.terminal_tokens.add(token)
        if device in self.destroyed_devices:
            return
        mask = self.queue_masks.get((device, family, queue), 0)
        bit = 1 if outcome == "complete" else 2
        if mask & bit:
            self.queued_events.append((device, token, outcome))


class IdentityBoundCompletionModel:
    """Model the ABA guard required when a public device XID is reused."""

    def __init__(self):
        self.next_identity = 1
        self.live_devices = {}
        self.queued_events = []

    def create_device(self, xid):
        identity = self.next_identity
        self.next_identity += 1
        self.live_devices[xid] = identity
        return identity

    def destroy_device(self, xid):
        self.live_devices.pop(xid, None)

    def completion(self, xid, captured_identity, token):
        # The callback must carry the original internal identity; it must not
        # resolve the XID again and accidentally target a replacement device.
        if self.live_devices.get(xid) != captured_identity:
            return
        self.queued_events.append((xid, captured_identity, token))


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

    def test_raw_wire_decoder_rejects_malformed_framing_and_payload(self):
        valid = bytearray(encode_select_events(
            "little", scope=SCOPE_QUEUE, device_xid=9,
            queue_family_index=1, queue_index=2, event_mask=3,
        ))
        malformed = []
        packet = bytearray(valid); packet[0] = 127; malformed.append(("major", packet))
        packet = bytearray(valid); packet[1] = 1; malformed.append(("minor", packet))
        packet = bytearray(valid); struct.pack_into("<H", packet, 2, 7); malformed.append(("length", packet))
        packet = bytearray(valid); packet[4] = 39; malformed.append(("subopcode", packet))
        packet = bytearray(valid); packet[5] = 1; malformed.append(("flags", packet))
        packet = bytearray(valid); packet[6] = 1; malformed.append(("reserved header", packet))
        packet = bytearray(valid); struct.pack_into("<I", packet, 28, 1); malformed.append(("reserved payload", packet))
        for label, packet in malformed:
            with self.subTest(label=label), self.assertRaises(ValueError):
                decode_select_events(bytes(packet), "little")
        with self.assertRaisesRegex(ValueError, "packet size"):
            decode_select_events(bytes(valid[:-4]), "little")
        with self.assertRaisesRegex(ValueError, "packet size"):
            decode_select_events(bytes(valid) + bytes(4), "little")

        semantic_bad = []
        packet = bytearray(valid); struct.pack_into("<I", packet, 8, 3); semantic_bad.append(("scope", packet))
        packet = bytearray(valid); struct.pack_into("<I", packet, 24, 4); semantic_bad.append(("mask", packet))
        packet = bytearray(valid); struct.pack_into("<I", packet, 12, 0); semantic_bad.append(("device XID", packet))
        for label, packet in semantic_bad:
            with self.subTest(label=label), self.assertRaises(ValueError):
                decode_select_events(bytes(packet), "little")

    def test_raw_wire_decoder_accepts_both_byte_orders_and_zero_mask(self):
        for order in ("little", "big"):
            with self.subTest(byte_order=order):
                wire = encode_select_events(
                    order, scope=SCOPE_DEVICE, device_xid=0x10203040, event_mask=0,
                )
                self.assertEqual(decode_select_events(wire, order), {
                    "scope": SCOPE_DEVICE, "device_xid": 0x10203040,
                    "queue_family_index": 0, "queue_index": 0, "event_mask": 0,
                })

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
            ("QUEUE", 2, "IMAGE_RELEASED"),
            ("QUEUE", 3, "PRESENTATION_COMPLETE"),
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
        self.assertIn("fixed total length of 32 bytes", EVENTS)
        self.assertIn("atomically replaces the existing mask for exactly one scope", EVENTS)

    def test_mask_replacement_and_destroy_device_scope_cleanup_are_normative(self):
        self.assertIn("event_mask = 0", EVENTS)
        self.assertIn("does not remove selections for other scopes", EVENTS)
        self.assertIn("its Device and Queue selections are removed", EVENTS)
        self.assertIn("On any error, the previous selection remains unchanged", EVENTS)
        self.assertIn("no new events using the destroyed `device_xid` may be generated or delivered", EVENTS)

    def test_submission_terminal_event_is_selected_at_linearization_point(self):
        required = (
            "when the terminal submission outcome occurs",
            "one shared serialized server state",
            "A successful `SelectEvents` request takes effect at its linearization point",
            "the Queue mask then in effect",
            "are atomic with respect to `DestroyDevice`",
            "no new event for its destroyed Device XID is queued",
            "MUST NOT retroactively change this decision",
            "For each accepted submission, `SUBMISSION_COMPLETE` and `SUBMISSION_FAILED` must never both be delivered",
        )
        for clause in required:
            with self.subTest(clause=clause):
                self.assertIn(clause, EVENTS)

    def test_race_destroy_before_terminal_suppresses_event_and_clears_scopes(self):
        state = SelectionRaceModel()
        state.device_masks[11] = 3
        state.select_queue(11, 0, 0, 3)
        state.destroy_device(11)
        state.terminal(11, 0, 0, 101, "complete")
        self.assertEqual(state.queued_events, [])
        self.assertNotIn(11, state.device_masks)
        self.assertFalse(any(key[0] == 11 for key in state.queue_masks))

    def test_race_terminal_before_destroy_preserves_already_queued_event(self):
        state = SelectionRaceModel()
        state.select_queue(11, 0, 0, 3)
        state.terminal(11, 0, 0, 102, "complete")
        state.destroy_device(11)
        self.assertEqual(state.queued_events, [(11, 102, "complete")])

    def test_mask_update_before_terminal_uses_new_mask_and_zero_disables(self):
        state = SelectionRaceModel()
        state.select_queue(11, 0, 0, 1)
        state.select_queue(11, 0, 0, 2)
        state.terminal(11, 0, 0, 103, "complete")
        state.terminal(11, 0, 0, 104, "failed")
        self.assertEqual(state.queued_events, [(11, 104, "failed")])
        state.select_queue(11, 0, 0, 0)
        state.terminal(11, 0, 0, 105, "failed")
        self.assertEqual(len(state.queued_events), 1)

    def test_one_submission_cannot_emit_two_terminal_events(self):
        state = SelectionRaceModel()
        state.select_queue(11, 0, 0, 3)
        state.terminal(11, 0, 0, 106, "complete")
        with self.assertRaisesRegex(ValueError, "already terminal"):
            state.terminal(11, 0, 0, 106, "failed")
        self.assertEqual(state.queued_events, [(11, 106, "complete")])

    def test_old_completion_cannot_be_redirected_to_reused_device_xid(self):
        state = IdentityBoundCompletionModel()
        old_identity = state.create_device(11)
        state.destroy_device(11)
        new_identity = state.create_device(11)
        self.assertNotEqual(old_identity, new_identity)
        state.completion(11, old_identity, 107)
        self.assertEqual(state.queued_events, [])
        state.completion(11, new_identity, 108)
        self.assertEqual(state.queued_events, [(11, new_identity, 108)])

    def test_resource_lifetime_spec_requires_identity_bound_callbacks(self):
        self.assertIn("MUST NOT resolve the target resource again from the current XID table using only a numeric XID",
                      LIFETIME)
        self.assertIn("reused XID", LIFETIME)
        self.assertIn("MUST NOT be redirected to a new object", LIFETIME)

    def test_lifetime_and_submission_specs_preserve_terminal_state_independently_of_delivery(self):
        self.assertIn("after successful processing of `DestroyDevice`", EVENTS)
        self.assertIn("events already queued in the X11 output stream remain unaffected", EVENTS)
        self.assertIn("Suppressing delivery does not change the internal terminal outcome", EVENTS)
        self.assertIn("Every synchronously rejected request is atomic and generates no submission event", SUBMISSIONS)
        self.assertIn("Every accepted submission has exactly one terminal outcome", SUBMISSIONS)
        self.assertIn("DestroyDevice", LIFETIME)
        self.assertIn("Device loss alone does not invalidate public XIDs", LIFETIME)


if __name__ == "__main__":
    unittest.main()
