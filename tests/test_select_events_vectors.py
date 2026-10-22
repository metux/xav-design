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


def encode_select_events(vector: dict) -> bytes:
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
    if fields["event_mask"] & ~SCOPES[scope]["mask"]:
        raise ValueError("event mask contains bits not valid for scope")
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


def validate_select_events_wire(wire: bytes, byte_order: str) -> None:
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
    if mask & ~SCOPES[scope]["mask"]:
        raise ValueError("event mask contains bits not valid for scope")
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
        section = re.search(r"^## Event-Auswahl: `SelectEvents`\s*$([\s\S]*?)(?=^## |\Z)", document, re.M)
        self.assertIsNotNone(section)
        body = section.group(1)
        self.assertRegex(body, r"fest(?:e|er) Gesamtlänge von 32 Bytes")
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
        ])
        registry = (ROOT / "registries" / "request-subopcodes.md").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"^\| `SelectEvents` \| 40 \| Void \|", registry, re.M)), 1)

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
        self.assertRegex(events, r"Unbekannte Scope-Werte.*ungültige Maskenbits.*BadValue")
        self.assertRegex(events, r"Unbekannte/nicht-live XIDs ergeben `BadValue`")
        self.assertRegex(events, r"falscher Ressourcentyp oder fremde Client-Ownership ergeben `BadMatch`")
        self.assertRegex(events, r"nicht existierende Queue innerhalb eines gültigen Devices ergibt `BadValue`")
        self.assertRegex(events, r"(?i)ohne ausgehandelte XGE-Unterst(?:ützung|uetzung) werden `CreateDevice`, `CreateDefaultDevice` und `SelectEvents` mit `BadMatch` abgewiesen")
        self.assertRegex(events, r"(?i)Bei jedem Fehler bleibt die vorherige Auswahl unver(?:ändert|aendert)")
        self.assertRegex(events, r"Der Request ersetzt atomar die bisherige Maske für genau einen Scope")
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
            r"tatsächlich angeforderte Queue dieses Devices identifizieren",
        )
        self.assertRegex(
            events,
            r"Bei erfolgreicher Zerstörung eines logischen Devices werden seine Device- und Queue-Auswahlen entfernt; eine Connection-Auswahl bleibt bestehen",
        )
        self.assertRegex(
            events,
            r"`ASYNC_ERROR` und `DEVICE_LOST` sind nicht maskierbar und werden unabhängig von `SelectEvents` zugestellt",
        )
        self.assertRegex(
            events,
            r"Nach erfolgreicher Verarbeitung von `DestroyDevice` dürfen keine neuen Events mit der zerstörten `device_xid` erzeugt oder zugestellt werden; bereits vorher in den X11-Ausgabestrom eingereihte Events bleiben unberührt",
        )
        self.assertRegex(
            events,
            r"Die beiden Submission-Events werden nur zugestellt, wenn das jeweilige Queue-Maskenbit bei Eintritt des terminalen Submission-Ergebnisses gesetzt ist",
        )
        self.assertRegex(
            events,
            r"Die Auswahl beeinflusst niemals die Ausführung, den internen terminalen Zustand oder die Fence-/Semaphore-Zustände",
        )
        self.assertRegex(
            events,
            r"Pro angenommener Submission darf niemals sowohl `SUBMISSION_COMPLETE` als auch `SUBMISSION_FAILED` als terminales Event ausgeliefert werden",
        )


    def test_select_events_error_mapping_matches_error_registry(self):
        events = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
        errors = (ROOT / "spec" / "errors.md").read_text(encoding="utf-8")
        section = re.search(r"^### `SelectEvents`\s*$([\s\S]*?)(?=^### |\Z)", errors, re.M)
        self.assertIsNotNone(section)
        error_body = section.group(1)
        for text in (
            "Falsche Request-Länge: `BadLength`.",
            "Erfolgreicher `GEQueryVersion`-Austausch mindestens mit XGE 1.0 fehlt: `BadMatch`.",
            "Unbekannter Scope, nicht-null Flags/reservierte Felder, ungültige Maskenbits oder nicht-null Felder außerhalb des ausgewählten Scopes: `BadValue`.",
            "Unbekannte/nicht-live Device-XID oder ungültiger Queue-Family-/Queue-Index: `BadValue`; falscher live Ressourcentyp oder fremde Client-Ownership: `BadMatch`.",
            "Ein Fehler muss die bisherige Event-Auswahl unverändert lassen; eine erfolgreiche Anfrage ersetzt atomar nur die Auswahl für den angegebenen Scope.",
        ):
            self.assertIn(text, error_body)
        self.assertIn("Eine nicht existierende Queue innerhalb eines gültigen Devices ergibt `BadValue`.", events)
        self.assertIn("Bei jedem Fehler bleibt die vorherige Auswahl unverändert.", events)

    def test_event_mask_mapping_and_scope_reset_are_exhaustive(self):
        events = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
        section = re.search(r"^## Event-Auswahl: `SelectEvents`\s*$([\s\S]*?)(?=^## |\Z)", events, re.M)
        self.assertIsNotNone(section)
        body = section.group(1)
        expected = [
            ("CONNECTION", 0, "DEVICE_STATUS_CHANGED"),
            ("DEVICE", 0, "DEVICE_MEMORY_PRESSURE"),
            ("DEVICE", 1, "DEVICE_IDLE"),
            ("QUEUE", 0, "SUBMISSION_COMPLETE"),
            ("QUEUE", 1, "SUBMISSION_FAILED"),
        ]
        actual = [
            (scope, int(bit), event)
            for scope, bit, event in re.findall(
                r"^\| `(CONNECTION|DEVICE|QUEUE)` \| (\d+) \| `([A-Z_]+)` \|$",
                body, re.M,
            )
        ]
        self.assertEqual(actual, expected)
        self.assertIn("`event_mask = 0` hebt die Auswahl für den angegebenen Scope auf.", body)
        self.assertIn("Das Aufheben einer Device- oder Queue-Maske entfernt keine Auswahl anderer Scopes.", body)
        self.assertIn("eine Connection-Auswahl bleibt bestehen", body)
        self.assertIn("Alle anderen Bits sind reserviert und müssen abgewiesen werden.", body)

    def test_disconnect_cleans_selections_and_prevents_cross_connection_delivery(self):
        events = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
        lifetime = (ROOT / "spec" / "resource-lifetime.md").read_text(encoding="utf-8")
        self.assertIn(
            "Ein Client-Disconnect beendet die Event-Zustellung für genau diese X11-Verbindung.",
            lifetime,
        )
        self.assertIn(
            "ihre Event-Auswahlen sowie die öffentlichen XID-Zuordnungen aus dem aktiven Verbindungszustand entfernen",
            lifetime,
        )
        self.assertIn(
            "Asynchrone Backend-Abschlüsse dürfen weder Events in eine geschlossene Verbindung einreihen noch über eine andere Verbindung zugestellt werden.",
            lifetime,
        )
        self.assertIn(
            "Die Event-Zuordnung muss an die konkrete X11-Verbindung und interne Ressourcenidentität gebunden bleiben, nicht nur an eine numerische XID.",
            lifetime,
        )
        self.assertIn(
            "Wenn die Verbindung geschlossen ist oder der X11-Server Events für diese Verbindung nicht mehr zustellen kann, ist keine Eventzustellung garantiert.",
            events,
        )

    def test_unmaskable_events_obey_destroy_device_lifetime_and_scrub_async_error_xids(self):
        events = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
        lifetime = (ROOT / "spec" / "resource-lifetime.md").read_text(encoding="utf-8")
        self.assertIn(
            "`ASYNC_ERROR` und `DEVICE_LOST` sind nicht maskierbar und werden unabhängig von `SelectEvents` zugestellt",
            events,
        )
        self.assertIn(
            "Nach erfolgreicher Verarbeitung von `DestroyDevice` dürfen keine neuen Events mit der zerstörten `device_xid` erzeugt oder zugestellt werden",
            events,
        )
        self.assertIn(
            "bei `ASYNC_ERROR` darf die zerstörte Device-XID nicht als `device_xid` oder `resource_xid` ausgegeben werden",
            lifetime,
        )
        self.assertIn(
            "Wird der Verlust dagegen erst während oder nach der Verarbeitung von `DestroyDevice` festgestellt, wird kein neues Event für die bereits zerstörte `device_xid` erzeugt oder zugestellt",
            lifetime,
        )

    def test_submission_event_delivery_failure_does_not_change_terminal_state(self):
        events = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
        lifetime = (ROOT / "spec" / "resource-lifetime.md").read_text(encoding="utf-8")
        self.assertIn(
            "Pro angenommener Submission darf niemals sowohl `SUBMISSION_COMPLETE` als auch `SUBMISSION_FAILED` als terminales Event ausgeliefert werden.",
            events,
        )
        self.assertIn(
            "Ein fehlgeschlagenes Event-Senden darf weder die GPU-/Backend-Abwicklung blockieren noch eine zweite terminale Zustellung auslösen.",
            events,
        )
        self.assertIn(
            "Bereits angenommene Arbeit wird unabhängig davon intern bis zu ihrem tatsächlichen terminalen Ausgang abgewickelt",
            lifetime,
        )
        self.assertIn(
            "Die Unterdrückung der Zustellung ändert weder den internen terminalen Ausgang angenommener Submissions",
            lifetime,
        )


    def test_async_event_decision_is_linearized_with_mask_changes_and_destroy(self):
        events = (ROOT / "spec" / "events.md").read_text(encoding="utf-8")
        lifetime = (ROOT / "spec" / "resource-lifetime.md").read_text(encoding="utf-8")
        self.assertIn(
            "die Verarbeitung eines erfolgreichen `SelectEvents`, die erfolgreiche Verarbeitung von `DestroyDevice` und der terminale Übergang einer Submission einschließlich Entscheidung über das zugehörige terminale Event",
            events,
        )
        self.assertIn(
            "Der erfolgreiche `SelectEvents`-Request wirkt ab seinem Linearisierungspunkt; ein Submission-Abschluss wertet die dann geltende Queue-Maske aus.",
            events,
        )
        self.assertIn(
            "Wird der Submission-Abschluss zuerst linearisiert und das Event eingereiht, bleibt dieses bereits eingereihte Event unberührt; wird `DestroyDevice` zuerst erfolgreich linearisiert, wird kein neues Event für dessen zerstörte Device-XID eingereiht.",
            events,
        )
        self.assertIn(
            "Ein späterer Backend-Callback darf diese Entscheidung nicht nachträglich ändern oder ein unterdrücktes Event erneut einreihen.",
            events,
        )
        self.assertIn(
            "Die Event-Zuordnung muss an die konkrete X11-Verbindung und interne Ressourcenidentität gebunden bleiben, nicht nur an eine numerische XID.",
            lifetime,
        )


    def test_backend_completion_keeps_original_connection_and_resource_identity(self):
        lifetime = (ROOT / "spec" / "resource-lifetime.md").read_text(encoding="utf-8")
        self.assertIn(
            "Jeder beim Backend registrierte Callback oder Completion-Datensatz muss die unveränderliche interne Identität der konkreten Submission beziehungsweise Ressource und die Identität der ursprünglichen X11-Verbindung mitführen.",
            lifetime,
        )
        self.assertIn(
            "Beim Abschluss darf der Server die Zielressource nicht anhand einer numerischen XID erneut aus der aktuellen XID-Tabelle auflösen.",
            lifetime,
        )
        self.assertIn(
            "Vor einer Event-Einreihung muss er prüfen, dass genau die ursprüngliche Verbindung noch aktiv und zustellbar ist",
            lifetime,
        )
        self.assertIn(
            "Eine geschlossene Verbindung, eine zerstörte Device-Identität oder eine inzwischen wiederverwendete XID darf niemals auf ein neues Objekt oder eine andere Verbindung umgebogen werden.",
            lifetime,
        )
        self.assertIn(
            "interne Submission-, Fence-/Semaphore- und Backend-Aufräumzustände müssen trotzdem genau einmal terminalisiert werden.",
            lifetime,
        )


    def test_submission_terminalization_is_single_winner_and_cleanup_is_idempotent(self):
        submission = (ROOT / "spec" / "queue-submission.md").read_text(encoding="utf-8")
        self.assertIn(
            "Der Wechsel einer angenommenen Submission von nicht-terminal zu genau einem terminalen Ergebnis (`COMPLETE` oder `FAILED`) ist ein einmaliger, serialisierter Zustandsübergang.",
            submission,
        )
        self.assertIn(
            "Erfolgs-Callbacks, Fehler-Callbacks und Device-Loss-Verarbeitung konkurrieren um denselben Übergang; der erste vom Server serialisiert festgestellte gültige Ausgang gewinnt.",
            submission,
        )
        self.assertIn(
            "Ein Callback, der nach einem bereits festgestellten terminalen Zustand eintrifft, darf weder das Ergebnis, Fence-/Semaphore-Zustände noch Event-Entscheidungen verändern.",
            submission,
        )
        self.assertIn(
            "darf ein späterer Erfolg weder `SIGNALED` setzen noch den Timeline-Counter erhöhen oder ein Signal als erfolgreich verbraucht markieren.",
            submission,
        )
        self.assertIn(
            "Jede Wait-/Signal-Reservierung, Fence-Zuordnung, Pending-Referenz und Pending-Markierung des Command Buffers wird höchstens einmal freigegeben beziehungsweise abgeschlossen.",
            submission,
        )
        self.assertIn(
            "Event-Zustellung ist ein nachgelagerter Effekt der terminalen Entscheidung und kann diese weder zurückrollen noch wiederholen.",
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
        self.assertIn("danach werden zurückgestellte Requests in normaler Request-Reihenfolge verarbeitet", memory.lower())


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
        self.assertIn("Der Inhalt des Zielbereichs ist dann nicht garantiert", memory)
        self.assertIn("`DEVICE_LOST`", errors)
        self.assertIn("Quarantäne gehalten", lifetime)

if __name__ == "__main__":
    unittest.main(verbosity=2)
