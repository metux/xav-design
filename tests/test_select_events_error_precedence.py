#!/usr/bin/env python3
"""Conformance tests for SelectEvents error classes and validation precedence.

These tests exercise the normative contract and a small executable decision
model. They are not a substitute for requests sent to a running X server.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def select_events_result(request, *, xge_ready, resources, queues):
    """Return the first normative error, or None for an accepted request.

    resources maps XID to (resource_type, owner_client). queues contains
    (device_xid, family_index, queue_index) tuples.
    """
    if request.get("length_bytes") != 32:
        return "BadLength"
    if not xge_ready:
        return "BadMatch"

    scope = request.get("scope")
    device = request.get("device_xid", 0)
    family = request.get("queue_family_index", 0)
    queue = request.get("queue_index", 0)
    mask = request.get("event_mask", 0)

    if request.get("flags", 0) != 0 or request.get("header_reserved", 0) != 0:
        return "BadValue"
    if request.get("reserved", 0) != 0:
        return "BadValue"
    masks = {0: 0x01, 1: 0x03, 2: 0x03}
    if scope not in masks or mask & ~masks[scope]:
        return "BadValue"
    if scope == 0 and (device or family or queue):
        return "BadValue"
    if scope == 1 and (not device or family or queue):
        return "BadValue"
    if scope == 2 and not device:
        return "BadValue"

    if scope in (1, 2):
        resource = resources.get(device)
        if resource is None:
            return "BadValue"
        resource_type, owner = resource
        if resource_type != "Device" or owner != request.get("client"):
            return "BadMatch"
        if scope == 2 and (device, family, queue) not in queues:
            return "BadValue"
    return None


class SelectEventsErrorPrecedenceTests(unittest.TestCase):
    def setUp(self):
        self.request = {
            "length_bytes": 32, "flags": 0, "header_reserved": 0,
            "scope": 1, "device_xid": 0x100, "queue_family_index": 0,
            "queue_index": 0, "event_mask": 1, "reserved": 0,
            "client": "client-A",
        }
        self.resources = {0x100: ("Device", "client-A")}
        self.queues = {(0x100, 0, 0)}

    def result(self, **changes):
        request = dict(self.request)
        request.update(changes)
        return select_events_result(
            request, xge_ready=True, resources=self.resources,
            queues=self.queues,
        )

    def test_request_length_precedes_xge_and_field_validation(self):
        request = dict(self.request, length_bytes=28, scope=99, flags=1)
        self.assertEqual(
            select_events_result(request, xge_ready=False,
                                 resources=self.resources, queues=self.queues),
            "BadLength",
        )

    def test_xge_negotiation_precedes_scope_and_resource_validation(self):
        request = dict(self.request, scope=99, device_xid=0xdead)
        self.assertEqual(
            select_events_result(request, xge_ready=False,
                                 resources=self.resources, queues=self.queues),
            "BadMatch",
        )

    def test_structural_errors_precede_resource_lookup(self):
        self.assertEqual(self.result(scope=99, device_xid=0xdead), "BadValue")
        self.assertEqual(self.result(flags=1, device_xid=0xdead), "BadValue")
        self.assertEqual(self.result(reserved=1, device_xid=0xdead), "BadValue")
        self.assertEqual(self.result(event_mask=0x80, device_xid=0xdead), "BadValue")
        self.assertEqual(self.result(scope=0, device_xid=0xdead), "BadValue")

    def test_unknown_or_nonlive_device_xid_is_badvalue(self):
        self.assertEqual(self.result(device_xid=0xdead), "BadValue")
        self.assertEqual(self.result(device_xid=0), "BadValue")

    def test_wrong_live_resource_type_and_foreign_owner_are_badmatch(self):
        self.resources[0x200] = ("Buffer", "client-A")
        self.resources[0x300] = ("Device", "client-B")
        self.assertEqual(self.result(device_xid=0x200), "BadMatch")
        self.assertEqual(self.result(device_xid=0x300), "BadMatch")

    def test_queue_indices_are_checked_only_after_device_identity(self):
        request = dict(self.request, scope=2, queue_family_index=4, queue_index=9)
        self.assertEqual(
            select_events_result(request, xge_ready=True,
                                 resources=self.resources, queues=self.queues),
            "BadValue",
        )
        request["device_xid"] = 0xdead
        self.assertEqual(
            select_events_result(request, xge_ready=True,
                                 resources=self.resources, queues=self.queues),
            "BadValue",
        )
        self.resources[0x200] = ("Buffer", "client-A")
        request["device_xid"] = 0x200
        self.assertEqual(
            select_events_result(request, xge_ready=True,
                                 resources=self.resources, queues=self.queues),
            "BadMatch",
        )

    def test_each_scope_accepts_only_its_registered_mask(self):
        cases = ((0, 0x01, True), (0, 0x02, False),
                 (1, 0x03, True), (1, 0x04, False),
                 (2, 0x03, True), (2, 0x04, False))
        for scope, mask, valid in cases:
            request = dict(self.request, scope=scope, event_mask=mask)
            if scope == 0:
                request.update(device_xid=0, queue_family_index=0, queue_index=0)
            elif scope == 1:
                request.update(device_xid=0x100, queue_family_index=0, queue_index=0)
            else:
                request.update(device_xid=0x100, queue_family_index=0, queue_index=0)
            actual = select_events_result(
                request, xge_ready=True, resources=self.resources,
                queues=self.queues,
            )
            with self.subTest(scope=scope, mask=mask):
                self.assertEqual(actual is None, valid)

    def test_spec_and_central_error_map_preserve_same_contract(self):
        events = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
        errors = (ROOT / "spec" / "errors.md").read_text(encoding="utf-8")
        lifetime = (ROOT / "spec" / "resource-lifetime.md").read_text(encoding="utf-8")
        section = re.search(
            r"^### `SelectEvents`\s*$([\s\S]*?)(?=^### |\Z)", errors, re.M
        )
        self.assertIsNotNone(section)
        body = section.group(1)
        required = (
            "Falsche Request-Länge: `BadLength`.",
            "Erfolgreicher `GEQueryVersion`-Austausch mindestens mit XGE 1.0 fehlt: `BadMatch`.",
            "Unbekannter Scope, nicht-null Flags/reservierte Felder, ungültige Maskenbits oder nicht-null Felder außerhalb des ausgewählten Scopes: `BadValue`.",
            "Unbekannte/nicht-live Device-XID oder ungültiger Queue-Family-/Queue-Index: `BadValue`; falscher live Ressourcentyp oder fremde Client-Ownership: `BadMatch`.",
            "Ein Fehler muss die bisherige Event-Auswahl unverändert lassen; eine erfolgreiche Anfrage ersetzt atomar nur die Auswahl für den angegebenen Scope.",
        )
        for phrase in required:
            self.assertIn(phrase, body)
        self.assertIn("Eine nicht existierende Queue innerhalb eines gültigen Devices ergibt `BadValue`.", events)
        self.assertIn("Bei jedem Fehler bleibt die vorherige Auswahl unverändert.", events)
        self.assertIn("Eine live Ressource, die einem anderen Client gehört", errors)
        self.assertIn("Ownership", lifetime)


if __name__ == "__main__":
    unittest.main(verbosity=2)
