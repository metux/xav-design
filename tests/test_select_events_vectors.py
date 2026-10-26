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


def encode_select_events(vector: dict, *, presentation_capable: bool = False) -> bytes:
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
    allowed_mask = SCOPES[scope]["mask"]
    if presentation_capable and scope == 2:
        allowed_mask |= 0x0C  # IMAGE_RELEASED and PRESENTATION_COMPLETE
    if fields["event_mask"] & ~allowed_mask:
        raise ValueError("event mask contains bits not valid for scope/profile")
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


def validate_select_events_wire(wire: bytes, byte_order: str, *, presentation_capable: bool = False) -> None:
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
    allowed_mask = SCOPES[scope]["mask"]
    if presentation_capable and scope == 2:
        allowed_mask |= 0x0C  # IMAGE_RELEASED and PRESENTATION_COMPLETE
    if mask & ~allowed_mask:
        raise ValueError("event mask contains bits not valid for scope/profile")
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
        section = re.search(r"^## Event Selection: `SelectEvents`\s*$([\s\S]*?)(?=^## |\Z)", document, re.M)
        self.assertIsNotNone(section)
        body = section.group(1)
        self.assertRegex(body, r"fixed total length of 32 bytes")
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
            ("QUEUE", 2, "IMAGE_RELEASED"),
            ("QUEUE", 3, "PRESENTATION_COMPLETE"),
        ])
        registry = (ROOT / "registries" / "request-subopcodes.md").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"^\| `SelectEvents` \| 40 \| Void \|", registry, re.M)), 1)

    def test_presentation_queue_mask_bits_are_profile_gated_by_registry(self):
        registry = (ROOT / "registries" / "presentation-events.md").read_text(encoding="utf-8")
        ids = {
            symbol: int(value)
            for value, symbol in re.findall(
                r"^\|\s*(\d+)\s*\|\s*`([A-Z_]+)`\s*\|", registry, re.M
            )
        }
        self.assertEqual(ids, {"IMAGE_RELEASED": 7, "PRESENTATION_COMPLETE": 8})
        self.assertIn("not part of compute-only v0.1", registry)
        for order in ("little", "big"):
            vector = next(v for v in self.vectors
                          if v["fields"]["scope"] == 2 and v["byte_order"] == order)
            for bit in (2, 3):
                vector_copy = json.loads(json.dumps(vector))
                vector_copy["fields"]["event_mask"] = 1 << bit
                with self.subTest(order=order, bit=bit, profile="compute-only"):
                    with self.assertRaisesRegex(ValueError, "scope/profile"):
                        encode_select_events(vector_copy)
                wire = encode_select_events(vector_copy, presentation_capable=True)
                validate_select_events_wire(wire, order, presentation_capable=True)
                with self.subTest(order=order, bit=bit, profile="compute-only-raw"):
                    with self.assertRaisesRegex(ValueError, "scope/profile"):
                        validate_select_events_wire(wire, order)
        self.assertIn("Presentation bits are valid only in the presentation-capable profile",
                      (ROOT / "spec" / "events.md").read_text(encoding="utf-8"))
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


    def test_semantic_error_matrix_and_atomic_selection_contract(self):
        events = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
        errors = (ROOT / "spec" / "errors.md").read_text(encoding="utf-8")
        # Wire-level failures and runtime resource failures are distinct.
        self.assertRegex(events, r"Unknown scope values.*invalid mask bits.*BadValue")
        self.assertRegex(events, r"Unknown or non-live XIDs result in `BadValue`")
        self.assertRegex(events, r"falscher Ressourcentyp oder fremde Client-Ownership ergeben `BadMatch`")
        self.assertRegex(events, r"A nonexistent queue within a valid device results in `BadValue`")
        self.assertRegex(events, r"(?i)Without negotiated XGE support.*`CreateDevice`, `CreateDefaultDevice`, and `SelectEvents`.*`BadMatch`")
        self.assertRegex(events, r"(?i)On any error, the previous selection remains unchanged")
        self.assertRegex(events, r"The request atomically replaces the existing mask for exactly one scope")
        self.assertRegex(errors, r"Eine erforderliche XAverius-XID, die keine live Ressource.*ergibt `BadValue`")
        self.assertRegex(errors, r"Eine XID, die eine live Ressource bezeichnet, aber nicht den erwarteten Ressourcentyp hat, ergibt `BadMatch`")

    def test_negative_golden_vectors_cover_each_structural_error_class(self):
        # Mutate valid golden packets instead of testing only hand-built invalid packets.
        for order in ("little", "big"):
            vector = next(v for v in self.vectors
                          if v["fields"]["scope"] == 0 and v["byte_order"] == order)
            endian = "<" if order == "little" else ">"
            cases = (
                (8, struct.pack(endian + "I", 99), "unknown SelectEvents scope"),
                (24, struct.pack(endian + "I", 0x80000000), "event mask"),
                (28, struct.pack(endian + "I", 1), "reserved field"),
                (12, struct.pack(endian + "I", 0x1234), "connection scope"),
            )
            valid = encode_select_events(vector)
            for offset, replacement, expected_error in cases:
                candidate = bytearray(valid)
                candidate[offset:offset + len(replacement)] = replacement
                with self.subTest(order=order, offset=offset):
                    with self.assertRaisesRegex(ValueError, expected_error):
                        validate_select_events_wire(bytes(candidate), order)


    def test_scope_cleanup_and_event_lifetime_contract(self):
        events = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
        queue_scope = re.search(
            r"- `QUEUE = 2`:.*",
            events,
        )
        self.assertIsNotNone(queue_scope)
        self.assertRegex(
            queue_scope.group(0),
            r"must identify a queue actually requested from that Device",
        )
        self.assertRegex(
            events,
            r"When a logical Device is successfully destroyed, its Device and Queue selections are removed; the Connection selection remains",
        )
        self.assertRegex(
            events,
            r"`ASYNC_ERROR` and `DEVICE_LOST` are unmaskable and are delivered independently of `SelectEvents`",
        )
        self.assertRegex(
            events,
            r"after successful processing of `DestroyDevice`, no new events using the destroyed `device_xid` may be generated or delivered; events already queued in the X11 output stream remain unaffected",
        )
        self.assertRegex(
            events,
            r"The two submission events are delivered only if the corresponding Queue mask bit is set when the terminal submission outcome occurs",
        )
        self.assertRegex(
            events,
            r"Event selection never affects execution, internal terminal state, or Fence/Semaphore state",
        )
        self.assertRegex(
            events,
            r"For each accepted submission, `SUBMISSION_COMPLETE` and `SUBMISSION_FAILED` must never both be delivered as terminal events",
        )


    def test_select_events_error_mapping_matches_error_registry(self):
        events = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
        errors = (ROOT / "spec" / "errors.md").read_text(encoding="utf-8")
        section = re.search(r"^### `SelectEvents`\s*$([\s\S]*?)(?=^### |\Z)", errors, re.M)
        self.assertIsNotNone(section)
        error_body = section.group(1)
        for text in (
            "An incorrect request length results in `BadLength`.",
            "If the client has not successfully negotiated at least XGE 1.0 with `GEQueryVersion`, the request results in `BadMatch`.",
            "An unknown scope, nonzero flags/reserved fields, invalid mask bits, or nonzero fields outside the selected scope results in `BadValue`.",
            "An unknown or non-live Device XID, or an invalid queue-family/queue index, results in `BadValue`; a live resource of the wrong type or foreign client ownership results in `BadMatch`.",
            "An error leaves the previous event selection unchanged; a successful request atomically replaces only the selection for the specified scope.",
        ):
            self.assertIn(text, error_body)
        self.assertIn("A nonexistent queue within a valid device results in `BadValue`.", events)
        self.assertIn("On any error, the previous selection remains unchanged.", events)

    def test_event_mask_mapping_and_scope_reset_are_exhaustive(self):
        events = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
        section = re.search(r"^## Event Selection: `SelectEvents`\s*$([\s\S]*?)(?=^## |\Z)", events, re.M)
        self.assertIsNotNone(section)
        body = section.group(1)
        expected = [
            ("CONNECTION", 0, "DEVICE_STATUS_CHANGED"),
            ("DEVICE", 0, "DEVICE_MEMORY_PRESSURE"),
            ("DEVICE", 1, "DEVICE_IDLE"),
            ("QUEUE", 0, "SUBMISSION_COMPLETE"),
            ("QUEUE", 1, "SUBMISSION_FAILED"),
            ("QUEUE", 2, "IMAGE_RELEASED"),
            ("QUEUE", 3, "PRESENTATION_COMPLETE"),
        ]
        actual = [
            (scope, int(bit), event)
            for scope, bit, event in re.findall(
                r"^\| `(CONNECTION|DEVICE|QUEUE)` \| (\d+) \| `([A-Z_]+)` \|$",
                body, re.M,
            )
        ]
        self.assertEqual(actual, expected)
        self.assertIn("`event_mask = 0` clears the selection for the specified scope.", body)
        self.assertIn("Clearing a Device or Queue mask does not remove selections for other scopes.", body)
        self.assertIn("the Connection selection remains", body)
        self.assertIn("All other bits are reserved and must be rejected.", body)

    def test_disconnect_cleans_selections_and_prevents_cross_connection_delivery(self):
        events = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
        lifetime = (ROOT / "spec" / "resource-lifetime.md").read_text(encoding="utf-8")
        self.assertIn(
            "A client disconnect ends event delivery for that X11 connection only.",
            lifetime,
        )
        self.assertIn(
            "remove its event selections and public XID mappings from active connection state.",
            lifetime,
        )
        self.assertIn(
            "Asynchronous backend completions MUST NOT enqueue events to a closed connection or deliver them through another connection.",
            lifetime,
        )
        self.assertIn(
            "Event associations MUST be bound to the specific X11 connection and internal resource identity, not only to a numeric XID.",
            lifetime,
        )
        self.assertIn(
            "If the connection is closed or the X11 server can no longer deliver events to it, event delivery is not guaranteed.",
            events,
        )

    def test_unmaskable_events_obey_destroy_device_lifetime_and_scrub_async_error_xids(self):
        events = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
        lifetime = (ROOT / "spec" / "resource-lifetime.md").read_text(encoding="utf-8")
        self.assertIn(
            "`ASYNC_ERROR` and `DEVICE_LOST` are unmaskable and are delivered independently of `SelectEvents`",
            events,
        )
        self.assertIn(
            "after successful processing of `DestroyDevice`, no new events using the destroyed `device_xid` may be generated or delivered",
            events,
        )
        self.assertIn(
            "for `ASYNC_ERROR`, the destroyed Device XID MUST NOT be emitted as `device_xid` or `resource_xid`",
            lifetime,
        )
        self.assertIn(
            "If device loss is first detected during or after processing of `DestroyDevice`, no new event for the already destroyed `device_xid` is generated or delivered",
            lifetime,
        )

    def test_async_error_scrubs_destroyed_or_reused_resource_xids(self):
        events = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
        lifetime = (ROOT / "spec" / "resource-lifetime.md").read_text(encoding="utf-8")
        conformance = (ROOT / "spec" / "conformance.md").read_text(encoding="utf-8")

        self.assertIn(
            "If the affected resource XID is no longer publicly live at the event-enqueue linearization point, `resource_xid` MUST be zero.",
            events,
        )
        self.assertIn(
            "For `ASYNC_ERROR`, a resource XID that has since been destroyed or reused MUST NOT be emitted as `resource_xid`",
            lifetime,
        )
        self.assertIn(
            "if the public resource XID is no longer live at the linearization point, `resource_xid = 0` is serialized",
            lifetime,
        )
        self.assertIn(
            "the event MUST have `resource_xid = 0`; a later callback MUST NOT retarget the numeric XID to the new object",
            conformance,
        )

    def test_submission_event_delivery_failure_does_not_change_terminal_state(self):
        events = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
        lifetime = (ROOT / "spec" / "resource-lifetime.md").read_text(encoding="utf-8")
        self.assertIn(
            "For each accepted submission, `SUBMISSION_COMPLETE` and `SUBMISSION_FAILED` must never both be delivered as terminal events.",
            events,
        )
        self.assertIn(
            "A failed event send MUST NOT block GPU/backend processing or trigger a second terminal delivery.",
            events,
        )
        self.assertIn(
            "Accepted work still reaches its actual internal terminal outcome",
            lifetime,
        )
        self.assertIn(
            "Suppressing delivery does not change the internal terminal outcome of accepted submissions",
            lifetime,
        )


    def test_async_event_decision_is_linearized_with_mask_changes_and_destroy(self):
        events = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
        lifetime = (ROOT / "spec" / "resource-lifetime.md").read_text(encoding="utf-8")
        self.assertIn(
            "Processing a successful `SelectEvents`, successful processing of `DestroyDevice`, and a Submission's terminal transition—including the decision about its terminal event—MUST be ordered by one shared serialized server state",
            events,
        )
        self.assertIn(
            "A successful `SelectEvents` request takes effect at its linearization point; submission completion evaluates the Queue mask then in effect.",
            events,
        )
        self.assertIn(
            "if submission completion linearizes first and queues the event, that queued event remains unaffected; if `DestroyDevice` successfully linearizes first, no new event for its destroyed Device XID is queued.",
            events,
        )
        self.assertIn(
            "A later backend callback MUST NOT retroactively change this decision or requeue a suppressed event.",
            events,
        )
        self.assertIn(
            "Event associations MUST be bound to the specific X11 connection and internal resource identity, not only to a numeric XID.",
            lifetime,
        )


    def test_conformance_covers_event_negative_cases_and_lifecycle_ordering(self):
        events = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
        conformance = (ROOT / "spec" / "conformance.md").read_text(encoding="utf-8")
        lifetime = (ROOT / "spec" / "resource-lifetime.md").read_text(encoding="utf-8")

        required_cases = (
            "unknown mask bits",
            "invalid zero values",
            "unrequested queue combination",
            "unmaskable `DEVICE_LOST` and `ASYNC_ERROR` events",
            "shared serialized linearization point",
            "at most one of `SUBMISSION_COMPLETE` and `SUBMISSION_FAILED`",
        )
        for phrase in required_cases:
            with self.subTest(case=phrase):
                self.assertIn(phrase, conformance)

        # Conformance examples must be backed by the normative delivery and
        # lifetime rules, not just repeat the intended behavior as checklist text.
        self.assertIn(
            "All other bits are reserved and must be rejected.",
            events,
        )
        self.assertIn(
            "A later backend callback MUST NOT retroactively change this decision or requeue a suppressed event.",
            events,
        )
        self.assertIn(
            "for `ASYNC_ERROR`, the destroyed Device XID MUST NOT be emitted as `device_xid` or `resource_xid`",
            lifetime,
        )
        self.assertIn(
            "Suppressing delivery does not change the internal terminal outcome of accepted submissions",
            lifetime,
        )

    def test_backend_completion_keeps_original_connection_and_resource_identity(self):
        lifetime = (ROOT / "spec" / "resource-lifetime.md").read_text(encoding="utf-8")
        self.assertIn(
            "Backend callbacks and completion records MUST carry the immutable internal identity of the specific submission or resource and the identity of the original X11 connection.",
            lifetime,
        )
        self.assertIn(
            "The server MUST NOT resolve an XID again from the current table to construct a delayed event.",
            lifetime,
        )
        self.assertIn(
            "Before queueing an event, the server MUST verify that the original connection remains active and able to receive events",
            lifetime,
        )
        self.assertIn(
            "A closed connection, destroyed Device identity, or reused XID MUST NOT be redirected to a new object or another connection.",
            lifetime,
        )
        self.assertIn(
            "internal submission, Fence/Semaphore, and backend cleanup states must still be terminalized exactly once.",
            lifetime,
        )


    def test_submission_terminalization_is_single_winner_and_cleanup_is_idempotent(self):
        submission = (ROOT / "spec" / "queue-submission.md").read_text(encoding="utf-8")
        self.assertIn(
            "The transition of an accepted submission from non-terminal to exactly one terminal result (`COMPLETE` or `FAILED`) is a one-time serialized state transition.",
            submission,
        )
        self.assertIn(
            "Success callbacks, failure callbacks, and Device-loss processing compete for the same transition; the first valid outcome serialized by the server wins.",
            submission,
        )
        self.assertIn(
            "A callback arriving after a terminal state has been established MUST NOT change the result, Fence/Semaphore state, or event decisions.",
            submission,
        )
        self.assertIn(
            "a later success MUST NOT set `SIGNALED`, increment the Timeline counter, or mark a signal as successfully consumed.",
            submission,
        )
        self.assertIn(
            "Each wait/signal reservation, Fence assignment, pending reference, and command-buffer pending marker is released or completed at most once.",
            submission,
        )
        self.assertIn(
            "Event delivery is a downstream effect of the terminal decision and cannot roll it back or repeat it.",
            submission,
        )


    def test_uncertain_binary_semaphore_failure_poisoning_is_explicit(self):
        synchronization = (ROOT / "spec" / "synchronization.md").read_text(encoding="utf-8")
        self.assertIn(
            "muss er die Binary-Semaphore als `UNTRUSTED` markieren.",
            synchronization,
        )
        self.assertIn(
            "weitere Queue-Waits und Queue-Signals auf dieser Semaphore werden vor Annahme mit `DEPENDENCY_FAILED` abgewiesen.",
            synchronization,
        )
        self.assertIn(
            "Der Server darf die Semaphore nicht als signalverfügbar oder unsignaled behandeln",
            synchronization,
        )
        self.assertIn(
            "Ist dagegen nachweisbar, dass die fehlgeschlagene Operation das Semaphore-Payload nicht verändert hat, bleibt der vorherige bestätigte Signalzustand erhalten.",
            synchronization,
        )
        self.assertIn(
            "Der beobachtbare Counter steigt erst, wenn die jeweilige Signaloperation tatsächlich erfolgreich ausgeführt wurde.",
            synchronization,
        )


    def test_write_buffer_detects_deferred_binary_and_timeline_signal_cycles(self):
        queue = (ROOT / "spec" / "queue-submission.md").read_text(encoding="utf-8")
        memory = (ROOT / "spec" / "memory-buffers.md").read_text(encoding="utf-8")
        self.assertIn("einen Binary- oder Timeline-Signal-Entry", queue)
        self.assertIn("bei Binary-Semaphoren muss es sich um dieselbe Semaphore handeln", queue)
        self.assertIn("Signal-Entries aus zurückgestellten Submissions nicht als angenommene oder verfügbare Signale", memory)
        self.assertIn("`WriteBuffer` mit `DEPENDENCY_FAILED` beenden", memory)
        self.assertIn("Der zurückgestellte `QueueSubmit` wird danach normal verarbeitet", queue)
        self.assertIn("Solange er zurückgestellt ist, gilt er nicht als angenommen", queue)
        self.assertIn("vollständige Validierung und atomare Zustandsübernahme erfolgen erst nach Abschluss des `WriteBuffer`", memory)

    def test_device_loss_terminalization_preserves_sync_and_backend_lifetime(self):
        queue = (ROOT / "spec" / "queue-submission.md").read_text(encoding="utf-8")
        sync = (ROOT / "spec" / "synchronization.md").read_text(encoding="utf-8")
        lifetime = (ROOT / "spec" / "resource-lifetime.md").read_text(encoding="utf-8")
        self.assertIn("Ein Device-Loss-Übergang muss alle zu diesem Zeitpunkt noch nicht-terminalen Submissions auf `FAILED/DEVICE_LOST` setzen", queue)
        self.assertIn("darf ein späterer Erfolg weder `SIGNALED` setzen noch den Timeline-Counter erhöhen", queue)
        self.assertIn("Kann der Server nach einem angenommenen, fehlgeschlagenen Backend-Vorgang nicht sicher nachweisen, ob eine Binary-Semaphore-Signal- oder Wait-Operation wirksam wurde, muss er die Binary-Semaphore als `UNTRUSTED` markieren.", sync)
        self.assertIn("Interne Ressourcen und zugehörige Speicher werden in Quarantäne gehalten", lifetime)
        self.assertIn("müssen trotzdem genau einmal terminalisiert werden", lifetime)

    def test_write_buffer_device_loss_never_claims_upload_visibility(self):
        memory = (ROOT / "spec" / "memory-buffers.md").read_text(encoding="utf-8")
        queue = (ROOT / "spec" / "queue-submission.md").read_text(encoding="utf-8")
        self.assertIn("Ist das Device verloren, schlägt `WriteBuffer` mit `DEVICE_LOST` fehl und darf keinen erfolgreichen Reply senden.", memory)
        self.assertIn("Bei einem fehlgeschlagenen Upload wird ebenfalls kein erfolgreicher Reply gesendet; der Inhalt des Zielbereichs ist dann nicht garantiert.", memory)
        self.assertIn("Bei einem fehlgeschlagenen `WriteBuffer` gilt die erfolgreiche Upload-Garantie nicht", memory)
        self.assertIn("danach werden zurückgestellte requests in normaler request-reihenfolge verarbeitet", memory.lower())


    def test_read_buffer_has_ordered_snapshot_and_explicit_failure_semantics(self):
        memory = (ROOT / "spec" / "memory-buffers.md").read_text(encoding="utf-8")
        errors = (ROOT / "spec" / "errors.md").read_text(encoding="utf-8")
        lifetime = (ROOT / "spec" / "resource-lifetime.md").read_text(encoding="utf-8")
        read = memory.split("## 5.8 `ReadBuffer`", 1)[1]
        self.assertIn("vor diesem Request angenommenen `QueueSubmit`-Submissions", read)
        self.assertIn("vor diesem Request eingereihten `WriteBuffer`-Transfers", read)
        self.assertIn("Eine bloße logische Terminalisierung reicht nicht aus", read)
        self.assertIn("späteren `QueueSubmit`-Requests", read)
        self.assertIn("Daten-Snapshot", read)
        self.assertIn("`DEVICE_LOST` fehlschlagen und darf keinen erfolgreichen Daten-Reply senden", read)
        self.assertIn("Ein fehlgeschlagener `ReadBuffer` verspricht keinen Snapshot", read)
        self.assertIn("`DEVICE_LOST`", errors)
        self.assertIn("Erkannter Abhängigkeitszyklus beim Warten auf frühere GPU-Arbeit: `DEPENDENCY_FAILED`", errors)
        self.assertIn("Erkannter Abhängigkeitszyklus vor Erfassung des Daten-Snapshots: `DEPENDENCY_FAILED`", errors)
        self.assertIn("Quarantäne gehalten", lifetime)


    def test_buffer_wire_lengths_padding_and_bounds_are_overflow_safe(self):
        memory = (ROOT / "spec" / "memory-buffers.md").read_text(encoding="utf-8")
        errors = (ROOT / "spec" / "errors.md").read_text(encoding="utf-8")
        write = memory.split("## 5.7 `WriteBuffer`", 1)[1].split("## 5.8 `ReadBuffer`", 1)[0]
        read = memory.split("## 5.8 `ReadBuffer`", 1)[1]
        self.assertIn("uint64(data_length)", write)
        self.assertIn("maximale X11-Request-Länge", write)
        self.assertIn("nicht-null Padding ergibt `BadValue`", write)
        self.assertIn("buffer_offset <= buffer_size", write)
        self.assertIn("data_length <= buffer_size - buffer_offset", write)
        self.assertIn("floor((uint64(data_length) + 3) / 4)", read)
        self.assertIn("Das Padding ist Teil des X11-Reply-Transports", read)
        self.assertIn("Request-Gesamtlänge mit Überlauf oder oberhalb des für die Verbindung geltenden X11-Limits: `BadLength`", errors)


    def test_buffer_memory_requirements_and_binding_contract(self):
        memory = (ROOT / "spec" / "memory-buffers.md").read_text(encoding="utf-8")
        errors = (ROOT / "spec" / "errors.md").read_text(encoding="utf-8")
        props = memory.split("## 5.2 `GetPhysicalDeviceMemoryProperties`", 1)[1].split("## 5.3 ", 1)[0]
        reqs = memory.split("## 5.3 `GetBufferMemoryRequirements`", 1)[1].split("## 5.4 ", 1)[0]
        alloc = memory.split("## 5.4 `AllocateMemory`", 1)[1].split("## 5.5 ", 1)[0]
        bind = memory.split("## 5.6 `BindBufferMemory`", 1)[1].split("## 5.7 ", 1)[0]
        self.assertIn("memory_type_count", props)
        self.assertIn("kleiner als `memory_heap_count`", props)
        self.assertIn("Bits außerhalb von `memory_type_count` müssen null sein", reqs)
        self.assertIn("mindestens ein unterstützter Memory-Type-Bit gesetzt sein", reqs)
        self.assertIn("Memory-Type-Index muss für das Physical Device", alloc)
        self.assertIn("die `memory_xid` bleibt unangelegt", alloc)
        self.assertIn("(memory_type_bits & (1u << memory_type_index)) != 0", bind)
        self.assertIn("Vielfaches des gemeldeten `alignment`", bind)
        self.assertIn("`requirements.size` maßgeblich", bind)
        self.assertIn("Der Request ist atomar: bei Ablehnung bleibt der Buffer ungebunden.", bind)
        self.assertIn("`ALLOCATION_FAILED`", errors)
        self.assertIn("`BindBufferMemory`", errors)


    def test_freememory_respects_internal_buffer_lifetime(self):
        lifetime = (ROOT / "spec" / "resource-lifetime.md").read_text(encoding="utf-8")
        memory = (ROOT / "spec" / "memory-buffers.md").read_text(encoding="utf-8")
        errors = (ROOT / "spec" / "errors.md").read_text(encoding="utf-8")
        free = memory.split("## 5.5 `FreeMemory`", 1)[1].split("## 5.6 ", 1)[0]
        self.assertIn("Seine interne Bindungsreferenz auf die Memory-Allokation bleibt während dieser gesamten Zeit bestehen", lifetime)
        self.assertIn("auch dann mit `BadMatch` abgewiesen werden", lifetime)
        self.assertIn("irgendein intern noch lebender Buffer", free)
        self.assertIn("öffentliche XID bereits durch `DestroyResource` invalidiert", free)
        self.assertIn("auch bei bereits invalidierter Buffer-XID", errors)

    def test_destroyed_buffer_descriptor_slot_release_chain(self):
        lifetime = (ROOT / "spec" / "resource-lifetime.md").read_text(encoding="utf-8")
        errors = (ROOT / "spec" / "errors.md").read_text(encoding="utf-8")
        memory = (ROOT / "spec" / "memory-buffers.md").read_text(encoding="utf-8")

        # Destroying the public Buffer XID does not silently repair stale sets.
        buffer_rules = lifetime.split("## Buffer und Memory", 1)[1].split("## Fehler bei ungültigen Lebenszyklusoperationen", 1)[0]
        self.assertIn("Descriptor Sets, die den Buffer enthalten, bleiben als Objekte bestehen", buffer_rules)
        self.assertIn("bis alle betroffenen Descriptor-Slots mit gültigen Buffer-Referenzen aktualisiert wurden oder die Sets freigegeben wurden", buffer_rules)
        self.assertIn("interne Bindungsreferenz auf die Memory-Allokation bleibt während dieser gesamten Zeit bestehen", buffer_rules)

        # Both release paths are atomic and invalidate executable command buffers.
        self.assertIn("nicht-pending `EXECUTABLE`-Command-Buffer, die eines dieser Sets referenzieren, werden `INVALID`", lifetime)
        self.assertIn("nicht-pending `EXECUTABLE`-Command-Buffer, die sie referenzieren, `INVALID`", lifetime)
        self.assertIn("`DestroyDescriptorPool` oder `FreeDescriptorSets`", errors)
        self.assertIn("irgendein intern noch lebender Buffer", memory)
        self.assertIn("Bei Ablehnung bleiben Memory-XID und Allokation unverändert", memory)

if __name__ == "__main__":
    unittest.main(verbosity=2)
