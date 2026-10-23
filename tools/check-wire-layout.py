#!/usr/bin/env python3
"""Static consistency checks for XAverius request/reply and XGE wire layouts.

Run from the repository root: python3 tools/check-wire-layout.py
Uses only the Python standard library and parses the normative Markdown sources.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent


class Check:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.checks = 0

    def require(self, condition: bool, message: str) -> None:
        self.checks += 1
        if not condition:
            self.errors.append(message)


def read(path: str) -> str:
    try:
        return (ROOT / path).read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"cannot read {path}: {exc}") from exc


def sections(markdown: str) -> list[tuple[str, str]]:
    # Bound every section by the next H2 heading, not only event headings.
    headers = list(re.finditer(r"^## (.+?)\s*$", markdown, re.M))
    result: list[tuple[str, str]] = []
    for i, match in enumerate(headers):
        name = re.fullmatch(r"`([^`]+)`", match.group(1).strip())
        if name:
            end = headers[i + 1].start() if i + 1 < len(headers) else len(markdown)
            result.append((name.group(1), markdown[match.end():end]))
    return result

def event_field_records(body: str) -> list[tuple[int, int, str, str]]:
    """Return (offset, size, type, field) records from tables and compact bullets."""
    records: list[tuple[int, int, str, str]] = []
    sizes = {"BYTE": 1, "CARD8": 1, "CARD16": 2, "CARD32": 4, "CARD64": 8, "XID": 4, "ATOM": 4}
    for line in body.splitlines():
        row = re.match(r"^\|\s*(\d+)\s*\|\s*([A-Z][A-Z0-9]*)\s*\|\s*([^|]+?)\s*\|\s*$", line)
        if row and row.group(2) in sizes:
            records.append((int(row.group(1)), sizes[row.group(2)], row.group(2), row.group(3).strip()))
            continue
        bullet = re.match(r"^\s*(?:[-*]\s*)?Offset\s+(\d+)\s*:\s*(?:`([A-Z][A-Z0-9]*)`\s+)?(.+)$", line)
        if bullet:
            typ = bullet.group(2)
            tail = bullet.group(3)
            if not typ:
                tm = re.search(r"`(CARD8|CARD16|CARD32|CARD64|XID|ATOM|BYTE)(?:\s+[^`]*)?`", tail)
                typ = tm.group(1) if tm else None
            if typ in sizes:
                records.append((int(bullet.group(1)), sizes[typ], typ, tail.strip()))
                continue
            # Compact event bullets commonly omit the type but start with an XID or CARD type.
            tm = re.match(r"(XID|CARD8|CARD16|CARD32|CARD64|ATOM|BYTE)\b", tail)
            if not tm and re.search(r"(?:Device|Resource)-XID", tail, re.I):
                records.append((int(bullet.group(1)), 4, "XID", tail.strip()))
                continue
            if tm:
                records.append((int(bullet.group(1)), sizes[tm.group(1)], tm.group(1), tail.strip()))
    return records


def check_events(c: Check) -> None:
    event_doc = read("spec/events.md")
    registry = read("registries/event-types.md")
    expected = {
        "ASYNC_ERROR": (0, 60, 7),
        "DEVICE_LOST": (1, 48, 4),
        "DEVICE_STATUS_CHANGED": (2, 48, 4),
        "DEVICE_MEMORY_PRESSURE": (3, 48, 4),
        "DEVICE_IDLE": (4, 48, 4),
        "SUBMISSION_COMPLETE": (5, 56, 6),
        "SUBMISSION_FAILED": (6, 56, 6),
    }
    event_type_parts = registry.split("## Event type IDs", 1)
    c.require(len(event_type_parts) == 2, "event registry: missing Event type IDs section")
    event_type_table = event_type_parts[1].split("\n## ", 1)[0] if len(event_type_parts) == 2 else ""
    event_rows = [
        (int(value), name)
        for value, name in re.findall(r"^\|\s*(\d+)\s*\|\s*`([A-Z_]+)`\s*\|\s*$", event_type_table, re.M)
    ]
    c.require(len(event_rows) == 7, f"event registry: expected 7 rows, found {len(event_rows)}")
    c.require(len({value for value, _name in event_rows}) == len(event_rows),
              "event registry contains duplicate event type IDs")
    c.require(len({name for _value, name in event_rows}) == len(event_rows),
              "event registry contains duplicate event names")
    c.require({value for value, _name in event_rows} == set(range(7)),
              "event registry must assign event type IDs 0 through 6 exactly once")
    reg_ids = {name: value for value, name in event_rows}
    local_sections = re.findall(r"^## \x60([^\x60]+)\x60\s*$([\s\S]*?)(?=^## |\Z)", registry, re.M)
    for heading, body in local_sections:
        if heading == "Event type IDs":
            continue
        local_rows = [
            (int(value), symbol)
            for value, symbol in re.findall(
                r"^\|\s*(\d+)\s*\|\s*\x60([A-Z_]+)\x60\s*\|\s*$", body, re.M,
            )
        ]
        if not local_rows:
            continue
        local_values = [value for value, _symbol in local_rows]
        local_symbols = [symbol for _value, symbol in local_rows]
        c.require(len(set(local_values)) == len(local_values),
                  f"event-local registry {heading} contains duplicate values")
        c.require(len(set(local_symbols)) == len(local_symbols),
                  f"event-local registry {heading} contains duplicate symbols")
        c.require(sorted(local_values) == list(range(len(local_values))),
                  f"event-local registry {heading} must assign values contiguously from zero")
    doc_sections = dict(sections(event_doc))
    c.require(re.search(r"Nach einem Event.*new_status = REMOVED.*kein weiteres.*DEVICE_STATUS_CHANGED", doc_sections.get("DEVICE_STATUS_CHANGED", ""), re.I) is not None,
              "DEVICE_STATUS_CHANGED: REMOVED must prohibit subsequent status events for that XID")
    c.require(re.search(r"After emitting.*new_status = REMOVED.*MUST NOT emit another.*DEVICE_STATUS_CHANGED", registry, re.I) is not None,
              "event registry: REMOVED must prohibit subsequent status events for that XID")
    c.require(re.search(r"heap_index.*UINT32_MAX.*kleiner als.*memory_heap_count", doc_sections.get("DEVICE_MEMORY_PRESSURE", ""), re.I) is not None,
              "DEVICE_MEMORY_PRESSURE: heap_index must be a valid heap index or UINT32_MAX")
    lifetime = read("spec/resource-lifetime.md")
    c.require(re.search(r"Nach erfolgreicher Verarbeitung von `DestroyDevice`.*keine neuen XAverius-Events mehr erzeugen oder zustellen", lifetime, re.S) is not None,
              "DestroyDevice: must suppress later events for the destroyed logical device")
    c.require(re.search(r"Die Unterdrückung der Zustellung.*internen terminalen Ausgang.*Backend-Referenzen", lifetime, re.S) is not None,
              "DestroyDevice: event suppression must preserve terminal submission and backend lifetime rules")
    c.require(re.search(r"Wird der Verlust dagegen erst während oder nach der Verarbeitung von `DestroyDevice` festgestellt, wird kein neues Event.*internen Fehler- und Submission-Zustände werden dennoch korrekt terminalisiert", lifetime, re.S) is not None,
              "Device loss first detected during DestroyDevice must not emit an event for the destroyed device")
    c.require(re.search(r"Ein Client-Disconnect beendet die Event-Zustellung.*genau diese X11-Verbindung", lifetime, re.S) is not None,
              "Client disconnect: event delivery must stop for that exact X11 connection")
    c.require(re.search(r"weder Events in eine geschlossene Verbindung einreihen noch über eine andere Verbindung zugestellt", lifetime, re.S) is not None,
              "Client disconnect: late backend events must not target a closed or different connection")
    c.require(re.search(r"Bereits angenommene Arbeit.*tatsächlichen terminalen Ausgang", lifetime, re.S) is not None,
              "Client disconnect: accepted submissions must retain their internal terminal outcome")
    c.require(re.search(r"interne Vulkan-Objekte bleiben bis zum Ende aller Backend-Zugriffe", lifetime, re.S) is not None,
              "Client disconnect/device loss: backend resources must remain alive while accesses are possible")
    c.require(re.search(r"`ASYNC_ERROR` und `DEVICE_LOST` sind nicht maskierbar.*unabhängig von `SelectEvents`", event_doc, re.S) is not None,
              "XGE delivery: ASYNC_ERROR and DEVICE_LOST must be unmaskable")
    c.require(re.search(r"`DEVICE_STATUS_CHANGED` wird nur über die Connection-Maske zugestellt", event_doc) is not None,
              "XGE delivery: DEVICE_STATUS_CHANGED must use the connection mask only")
    c.require(re.search(r"Submission-Events werden nur zugestellt, wenn das jeweilige Queue-Maskenbit bei Eintritt des terminalen Submission-Ergebnisses gesetzt ist", event_doc) is not None,
              "XGE delivery: submission event mask must be sampled at terminal outcome")
    c.require(re.search(r"Pro angenommener Submission darf niemals sowohl `SUBMISSION_COMPLETE` als auch `SUBMISSION_FAILED` als terminales Event ausgeliefert werden", event_doc) is not None,
              "XGE delivery: a submission cannot deliver both terminal events")
    c.require(re.search(r"Ein fehlgeschlagenes Event-Senden darf weder die GPU-/Backend-Abwicklung blockieren noch eine zweite terminale Zustellung auslösen", event_doc) is not None,
              "XGE delivery: send failure must not block backend work or duplicate terminal events")
    c.require(re.search(r"Bei jedem Fehler bleibt die vorherige Auswahl unverändert", event_doc) is not None,
              "SelectEvents: failed validation must preserve the previous event selection")
    c.require(re.search(r"Unbekannte/nicht-live XIDs ergeben `BadValue`.*falscher Ressourcentyp oder fremde Client-Ownership ergeben `BadMatch`", event_doc, re.S) is not None,
              "SelectEvents: unknown XIDs must map to BadValue, wrong type/foreign ownership to BadMatch")
    c.require(re.search(r"nicht existierende Queue innerhalb eines gültigen Devices ergibt `BadValue`", event_doc) is not None,
              "SelectEvents: nonexistent queue on a valid device must map to BadValue")
    c.require(re.search(r"ohne ausgehandelte XGE-Unterst(?:ützung|uetzung) werden `CreateDevice`, `CreateDefaultDevice` und `SelectEvents` mit `BadMatch` abgewiesen; bei `SelectEvents` bleibt die vorherige Auswahl unver(?:ändert|aendert)", event_doc, re.I) is not None,
              "SelectEvents: missing XGE negotiation must return BadMatch without changing prior selection")
    c.require(re.search(r"Der Request ersetzt atomar die bisherige Maske für genau einen Scope", event_doc) is not None,
              "SelectEvents: successful replacement must be atomic and scoped")
    errors = read("spec/errors.md")
    c.require(re.search(r"Eine erforderliche XAverius-XID, die keine live Ressource.*ergibt `BadValue`", errors, re.S) is not None and
              re.search(r"Eine XID, die eine live Ressource bezeichnet, aber nicht den erwarteten Ressourcentyp hat, ergibt `BadMatch`", errors) is not None,
              "error mapping: unknown XIDs and live wrong-type XIDs must remain distinct")
    c.require(re.search(r"Bei erfolgreicher Zerstörung eines logischen Devices werden seine Device- und Queue-Auswahlen entfernt; eine Connection-Auswahl bleibt bestehen", event_doc) is not None,
              "SelectEvents: device destruction must clear only device and queue selections")
    submissions = read("spec/queue-submission.md")
    c.require(re.search(r"Submission erhält intern genau einen terminalen Ausgang.*DestroyDevice.*unterdrückt", submissions, re.S) is not None,
              "QueueSubmit: terminal event delivery must respect DestroyDevice lifecycle suppression")
    c.require(re.search(r"terminales Event vorgesehen.*Lifecycle-Regeln für `DestroyDevice` unterdrückt", submissions, re.S) is not None,
              "QueueSubmit/device loss: terminal event requirement must not contradict DestroyDevice suppression")
    sync = read("spec/synchronization.md")
    c.require(re.search(r"GetFenceStatus.*nach Device Loss.*gespeicherten Zustand", sync, re.S) is not None,
              "synchronization: GetFenceStatus must remain a state query after device loss")
    c.require(re.search(r"`GetFenceStatus`.*Request: exakt 16 Bytes.*Unbekannte/nicht-live Device- oder Fence-XIDs ergeben `BadValue`.*gespeicherten Fence-Zustand zurück", sync, re.S) is not None and
              re.search(r"`GetFenceStatus`: falsche Länge `BadLength`.*nach Device Loss", errors, re.S) is not None,
              "GetFenceStatus: exact length, XID/ownership errors, and post-loss state query must be explicit")
    c.require(re.search(r"`ResetFence`.*Request: exakt 16 Bytes.*Unbekannte/nicht-live Device- oder Fence-XIDs ergeben `BadValue`.*`DEVICE_LOST`", sync, re.S) is not None and
              re.search(r"`ResetFence`: falsche Länge `BadLength`.*Cross-Device-Verwendung `BadMatch`.*`INVALID_SYNCHRONIZATION_STATE`", errors, re.S) is not None,
              "ResetFence: request length, XID/ownership, state, and device-loss errors must be explicit")
    c.require(re.search(r"WaitForFence.*liefert dagegen `DEVICE_LOST`.*sobald das Device als verloren erkannt wurde", sync, re.S) is not None,
              "synchronization: WaitForFence must terminate with DEVICE_LOST")
    c.require(re.search(r"keine offene `WaitForFence`-Registrierung.*`INVALID_SYNCHRONIZATION_STATE` abgewiesen", sync, re.S) is not None,
              "DestroyFence: must reject while a host wait registration is still open")
    c.require(re.search(r"terminales Ergebnis.*serialisiert festgestellt.*Reply noch im Ausgabepuffer.*verhindert die Zerstörung nicht", sync, re.S) is not None,
              "DestroyFence: a completed wait must stop blocking destruction before reply delivery")
    c.require(re.search(r"offene `WaitSemaphores`-Registrierung.*exakte interne Semaphore-Identität", sync, re.S) is not None,
              "DestroySemaphore: must reject while a host wait registration references the semaphore")
    c.require(re.search(r"terminales Ergebnis serverseitig serialisiert festgestellt.*Reply blockiert die Zerstörung dann nicht", sync, re.S) is not None,
              "DestroySemaphore: a completed wait must stop blocking destruction before reply delivery")
    c.require(re.search(r"GetSemaphoreCounterValue.*mit `DEVICE_LOST` abgewiesen", sync, re.S) is not None,
              "synchronization: counter query must not return an apparently successful value after device loss")
    c.require(re.search(r"`GetSemaphoreCounterValue`.*Request: exakt 16 Bytes.*Unbekannte/nicht-live Device- oder Semaphore-XIDs ergeben `BadValue`.*`DEVICE_LOST` abgewiesen", sync, re.S) is not None and
              re.search(r"`GetSemaphoreCounterValue`: falsche Länge `BadLength`.*Cross-Device-Verwendung `BadMatch`.*`DEVICE_LOST`", errors, re.S) is not None,
              "GetSemaphoreCounterValue: request length, XID/ownership, and device-loss errors must be explicit")
    c.require(re.search(r"WaitSemaphores.*wird mit `DEVICE_LOST` beendet", sync, re.S) is not None,
              "synchronization: semaphore waits must terminate on device loss")
    c.require(re.search(r"Semaphore- und Fence-Objekte bleiben intern erhalten.*solange Backend-Zugriffe", sync, re.S) is not None,
              "synchronization: backend references must outlive device-loss public invalidation")
    c.require(re.search(r"Erst nach dieser Konsumption darf ein neuer Signalzyklus beginnen", sync, re.S) is not None,
              "synchronization: binary semaphore reuse must follow actual wait consumption")
    c.require(re.search(r"Counter steigt erst, wenn die jeweilige Signaloperation tatsächlich erfolgreich ausgeführt wurde", sync, re.S) is not None,
              "synchronization: timeline counter must not advance at submission acceptance")
    c.require(re.search(r"größer als alle bereits reservierten pending Signalwerte", sync) is not None,
              "synchronization: pending timeline signal values must be reserved monotonically")
    c.require(re.search(r"kleiner als jeder bereits reservierte, noch nicht terminale GPU-Signalwert", sync) is not None,
              "synchronization: host timeline signals must not jump over pending GPU signal reservations")
    c.require(re.search(r"`SignalSemaphore`.*Gesamtlänge muss exakt 24 Bytes.*`DEVICE_UNAVAILABLE`.*`DEVICE_LOST`", sync, re.S) is not None and
              re.search(r"`SignalSemaphore`: falsche Länge `BadLength`.*`DEVICE_UNAVAILABLE` / `DEVICE_LOST`", errors, re.S) is not None,
              "SignalSemaphore: request length, XID/ownership, and device-state errors must be explicit")
    c.require(re.search(r"`WaitSemaphores`.*Request-Länge muss exakt `28 \+ 12 \* semaphore_count` Bytes.*doppelte XIDs und ungültige `wait_mode`-Werte ergeben `BadValue`", sync, re.S) is not None and
              re.search(r"`WaitSemaphores`: falsche Länge oder Überlauf.*`DEVICE_LOST`.*`DEVICE_DESTROYED`", errors, re.S) is not None,
              "WaitSemaphores: exact length, XID/ownership errors, and terminal device outcomes must be explicit")
    c.require(re.search(r"`WaitForFence`.*Request: 24 Bytes exakt.*Unbekannte/nicht-live Device- oder Fence-XIDs ergeben `BadValue`.*Cross-Device-Verwendung ergeben `BadMatch`", sync, re.S) is not None and
              re.search(r"`WaitForFence`: falsche Länge `BadLength`.*Device Loss und `DestroyDevice`.*Reply-Statuswerte", errors, re.S) is not None,
              "WaitForFence: request length, XID/ownership errors, and reply terminal states must be explicit")
    c.require(re.search(r"WaitSemaphores` darf den X11-Request-Dispatcher nicht synchron blockieren", sync) is not None,
              "synchronization: host waits must not block later signals or submissions on the same connection")
    c.require(re.search(r"Timeout-Frist beginnt bei der Übernahme des Wait-Requests und läuft auch dann weiter", sync) is not None,
              "synchronization: wait timeout must continue while later requests are processed")
    memory = read("spec/memory-buffers.md")
    c.require(re.search(r"Signal-Entries zurückgestellter `QueueSubmit`-Requests", memory) is not None and
              "`DEPENDENCY_FAILED`" in memory,
              "WriteBuffer: deferred signal dependency cycles must fail rather than deadlock")
    queue_order = read("spec/queue-submission.md")
    c.require(re.search(r"zurückgestellten Requests.*Timeline-Signal-Entry.*`DEPENDENCY_FAILED`", queue_order, re.S) is not None,
              "QueueSubmit: dependency-cycle handling must be consistent with WriteBuffer ordering")
    conformance = read("spec/conformance.md")
    errors = read("spec/errors.md")
    c.require(
        "`DestroyFence` und `DestroySemaphore` prüfen die feste Request-Länge vor XID-Auflösung" in conformance
        and "nicht-terminalen Submission zugeordnet" in conformance
        and "Queue-Wait/-Signal" in conformance
        and "Nach terminal festgestelltem Wait-Ergebnis blockiert ein noch ausstehender Reply die Zerstörung nicht" in conformance,
        "conformance: specialized destroy tests must cover error precedence and terminal wait release",
    )
    c.require(re.search(r"`WriteBuffer`.*zurückgestellter `QueueSubmit`.*`DEPENDENCY_FAILED`", conformance, re.S) is not None,
              "conformance: WriteBuffer dependency-cycle case must be covered")
    submissions = read("spec/queue-submission.md")
    c.require(re.search(r"all semaphore wait/signal reservations and internal references are committed atomically", submissions, re.S) is not None,
              "QueueSubmit: semaphore reservations and references must commit atomically")
    c.require(re.search(r"exact internal semaphore identity.*numeric XID.*reuses the same XID", submissions, re.S) is not None,
              "QueueSubmit: semaphore references must not follow a reused XID")
    c.require(re.search(r"backend can no longer access the semaphore", submissions, re.S) is not None,
              "QueueSubmit: semaphore backend references must survive until safe release")
    c.require("Doppelte Wait- oder Signal-Einträge sind in v0.1 ungültig" in submissions and
              "Dieselbe Semaphore darf in einer Submission nicht gleichzeitig im Wait- und Signal-Array stehen" in submissions,
              "QueueSubmit: duplicate semaphore entries and wait/signal aliasing must be rejected")
    c.require("Binary-Wait-/Signalwerte müssen null sein" in conformance and
              "doppelte Timeline-Signal-Entries derselben Semaphore" in conformance and
              "reserviert weder `submission_token` noch Semaphore-Wait-/Signal-Slots" in conformance,
              "QueueSubmit: semaphore value checks and rejected-submit atomicity must be covered")
    c.require("Die `EXECUTABLE`-zu-`PENDING`-Übergänge und die Synchronisationsreservierungen sind somit ein gemeinsamer Commit" in submissions and
              "der Token bleibt unbenutzt" in submissions and
              "Semaphore-Counter, Signalverfügbarkeit, Pending-Slots und Timeline-Reservierungen bleiben unverändert" in submissions,
              "QueueSubmit: all state changes and token reservation must share the acceptance commit")
    c.require("Ein FINAL-Chunk führt den Übergang `RECORDING` → `EXECUTABLE` erst nach erfolgreicher Validierung" in read("spec/command-recording.md") and
              "der Buffer bleibt `RECORDING`, alle vorher akzeptierten Entries und ihre Referenzen bleiben unverändert" in read("spec/command-recording.md"),
              "CommandBufferData: failed FINAL must preserve recording state and prior references")
    c.require("Ein fehlerhafter FINAL-Chunk von `CommandBufferData` lässt den Buffer `RECORDING`" in conformance and
              "Bei abgewiesenem `QueueSubmit` bleibt jeder Command Buffer `EXECUTABLE`" in conformance and
              "kann derselbe Token in einem korrigierten Request verwendet werden" in conformance and
              "weder `SUBMISSION_COMPLETE`/`SUBMISSION_FAILED` noch `ASYNC_ERROR`" in conformance,
              "conformance: finalization and rejected-submit state transitions must be atomic")
    c.require("synchroner Fehler vor Annahme | keinerlei Zustandsänderung" in errors,
              "QueueSubmit: error map must state non-mutating synchronous rejection")
    c.require("Fehlerpräzedenz (erste zutreffende Phase gewinnt)" in submissions and
              "erforderliche XIDs werden in Wire-Reihenfolge aufgelöst: Device, optionale Fence, Command-Buffer-XIDs in Array-Reihenfolge" in submissions and
              "Vorrang vor veränderlichen Submit-Zuständen" in submissions and
              "Typabhängige Werte wie Binary-Wait-/Signalwerte werden erst nach Typauflösung geprüft" in submissions and
              "zuerst der Zustand der optionalen Fence, dann die Command Buffer in Array-Reihenfolge, danach die Wait-Entries in Array-Reihenfolge" in submissions and
              "prüft `QueueSubmit` nach Device-Zustand zuerst die optionale Fence" in conformance,
              "QueueSubmit: deterministic syntax/XID/ownership/device/state precedence must be normative")
    c.require(re.search(r"\| `QueueSubmit`: Device nicht verfügbar/verloren.*?\n\| `QueueSubmit`: Command Buffer nicht `EXECUTABLE`", errors, re.S) is not None and
              "typabhängiger Binary-/Timeline-Semaphore-Wert ist ungültig" in errors and
              "Bei CREATE/Append/FINAL auf einem verlorenen Device gewinnt `DEVICE_LOST`" in conformance,
              "QueueSubmit: error table and conformance must follow device-before-state precedence")
    for name, (event_id, total, length) in expected.items():
        c.require(reg_ids.get(name) == event_id, f"event registry: {name} must have stable ID {event_id}")
        c.require(name in doc_sections, f"events.md: missing layout section {name}")
        if name not in doc_sections:
            continue
        body = doc_sections[name]
        total_match = re.search(r"Gesamtlänge:\s*(\d+)\s*Bytes;\s*XGE `length\s*=\s*(\d+)`", body)
        c.require(bool(total_match), f"{name}: total length and XGE length declaration missing")
        if total_match:
            declared_total, declared_length = map(int, total_match.groups())
            c.require(declared_total == total, f"{name}: declared total {declared_total}, expected {total}")
            c.require(declared_length == length, f"{name}: declared XGE length {declared_length}, expected {length}")
            c.require(declared_total == 32 + 4 * declared_length, f"{name}: total must equal 32 + 4 * XGE length")
        records = event_field_records(body)
        c.require(bool(records), f"{name}: no parseable event fields found")
        occupied: dict[int, str] = {}
        for offset, size, typ, field in records:
            c.require(offset >= 32, f"{name}.{field}: event payload field starts before offset 32")
            c.require(offset % min(size, 4) == 0, f"{name}.{field}: offset {offset} is not aligned for {typ}")
            for byte in range(offset, offset + size):
                c.require(byte not in occupied, f"{name}.{field}: overlaps {occupied.get(byte, 'another field')} at byte {byte}")
                occupied[byte] = field
            c.require(offset + size <= total, f"{name}.{field}: ends at {offset + size}, beyond event size {total}")
            if "reserved" in field.lower():
                c.require(re.search(r"(?:=|must be|is)\s*`?0`?", field, re.I) is not None,
                          f"{name}.{field}: reserved field must explicitly require zero")
        # Every byte in the event payload must be accounted for; this catches silent holes.
        missing = [i for i in range(32, total) if i not in occupied]
        c.require(not missing, f"{name}: unaccounted payload byte(s): {missing[:8]}")
    for name in expected:
        c.require(name in reg_ids, f"event registry: missing {name}")
    header_checks = [
        (r"response_type\s*=\s*GenericEvent\s*\(35\)", "GenericEvent response_type 35"),
        (r"\|\s*2\s*\|\s*CARD16\s*\|[^\n]*Sequenznummer", "16-bit X11 event sequence at offset 2"),
        (r"\|\s*1\s*\|[^\n]*dynamisch zugewiesener XAverius-Major-Opcode", "dynamic extension opcode at offset 1"),
        (r"\|\s*4\s*\|[^\n]*XGE `length`", "XGE length at offset 4"),
        (r"\|\s*10–31\s*\|[^\n]*null", "zeroed reserved common-header bytes"),
        (r"\|\s*8\s*\|[^\n]*`evtype`", "evtype at offset 8"),
        (r"32 \+ 4 \* length", "XGE total-length formula"),
    ]
    for pattern, label in header_checks:
        c.require(re.search(pattern, event_doc, re.I) is not None, f"events.md: missing {label}")
    wire_protocol = read("spec/wire-protocol.md")
    protocol_checks = [
        (r"QueryExtension", "dynamic major opcode discovery via QueryExtension"),
        (r"128–255", "X11 extension major opcode range 128–255"),
    ]
    for pattern, label in protocol_checks:
        c.require(re.search(pattern, wire_protocol, re.I) is not None, f"wire-protocol.md: missing {label}")


def parse_request_registry(markdown: str) -> dict[int, tuple[str, str]]:
    result: dict[int, tuple[str, str]] = {}
    for line in markdown.splitlines():
        row = re.match(r"^\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|", line)
        if row:
            name, opcode, kind = row.group(1), int(row.group(2)), row.group(3).strip()
            result[opcode] = (name, kind)
    return result


def check_reason_code_registry(c: Check) -> None:
    registry = read("registries/reason-codes.md")
    rows = [
        (int(value), symbol)
        for value, symbol in re.findall(
            r"^\|\s*(\d+)\s*\|\s*`([A-Z_]+)`\s*\|\s*$",
            registry, re.M,
        )
    ]
    expected = [
        (0, "REASON_UNSPECIFIED"),
        (1, "HOTPLUG_REMOVAL"),
        (2, "DRIVER_FAILURE"),
        (3, "VULKAN_DEVICE_LOST"),
        (4, "SERVER_POLICY"),
        (5, "SERVER_SHUTDOWN"),
    ]
    c.require(rows == expected,
              "device reason-code registry must assign shared values 0 through 5 exactly as specified")
    c.require("append-only" in registry.lower() and "MUST NOT be renumbered" in registry,
              "device reason-code registry must explicitly be append-only and prohibit renumbering")
    events = read("spec/events.md")
    event_registry = read("registries/event-types.md")
    for source_name, source in (("spec/events.md", events),
                                ("registries/event-types.md", event_registry)):
        c.require("reason-codes.md" in source,
                  f"{source_name}: must reference the shared device reason-code registry")
    c.require("DEVICE_LOST.reason_code" in event_registry and
              "DEVICE_STATUS_CHANGED.reason_code" in event_registry,
              "event registry must declare shared reason-code namespace for both events")
    issues = read("spec/open-issues.md")
    closed_section = issues.split("## Closed items", 1)[1] if "## Closed items" in issues else ""
    c.require("**Shared device reason codes:**" in closed_section and
              "DEVICE_LOST.reason_code" in closed_section and
              "DEVICE_STATUS_CHANGED.reason_code" in closed_section and
              "reason-codes.md" in closed_section,
              "shared device reason codes must remain documented as closed in the issue ledger")


def check_error_registry(c: Check) -> None:
    """Check that centrally assigned XAverius error offsets are unique and used."""
    registry = read("registries/errors.md")
    error_doc = read("spec/errors.md")
    rows = [
        (int(offset), symbol)
        for offset, symbol in re.findall(
            r"^\|\s*(\d+)\s*\|\s*`([A-Z][A-Z0-9_]+)`\s*\|\s*$",
            registry, re.M,
        )
    ]
    c.require(bool(rows), "error registry: no numeric error assignments found")
    c.require(len({offset for offset, _symbol in rows}) == len(rows),
              "error registry contains duplicate offsets")
    c.require(len({symbol for _offset, symbol in rows}) == len(rows),
              "error registry contains duplicate symbols")
    c.require([offset for offset, _symbol in rows] == list(range(len(rows))),
              "error registry offsets must be contiguous from zero")
    c.require("first_error + offset" in error_doc,
              "error chapter must define absolute code as first_error + offset")
    for _offset, symbol in rows:
        c.require(chr(96) + symbol + chr(96) in error_doc,
                  f"error registry symbol {symbol} is missing from error guidance")

    # Tie error semantics to the full request registry and conformance corpus.
    matrix_parts = read("spec/request-audit.md").split("## Per-request contract matrix", 1)
    conformance = read("spec/conformance.md")
    request_registry = read("registries/request-subopcodes.md")
    c.require(len(matrix_parts) == 2, "error coverage: request audit matrix is missing")
    if len(matrix_parts) == 2:
        matrix_body = matrix_parts[1].split("\n## ", 1)[0]
        tick = chr(96)
        requests = re.findall(r"^\|\s*\d+\s*\|\s*" + tick + r"([^" + tick + r"]+)" + tick + r"\s*\|", matrix_body, re.M)
        registered = set(re.findall(
            r"^\|\s*" + tick + r"([^" + tick + r"]+)" + tick + r"\s*\|\s*\d+\s*\|", request_registry, re.M
        ))
        c.require(len(requests) in (40, 47),
                  f"error coverage: expected 40 baseline or 47 audited request matrix entries, found {len(requests)}")
        presentation_names = {
            "CreateSurface", "DestroySurface", "GetSurfaceCapabilities", "CreateSwapchain",
            "DestroySwapchain", "AcquireNextImage", "QueuePresent",
        }
        c.require((set(requests) - registered) <= presentation_names and
                  (registered - set(requests)) <= presentation_names,
                  "error coverage: request matrix and registry differ beyond the provisional presentation set")
        for name in requests:
            c.require(tick + name + tick in error_doc,
                      f"error coverage: {name} is absent from spec/errors.md")
            c.require(tick + name + tick in conformance,
                      f"error coverage: {name} is absent from spec/conformance.md")
    for phrase in (
        "Die erste fehlerhafte XID bestimmt den gemeldeten Ressourcenfehler",
        "Der Request bleibt atomar",
        "Wire-Länge und strukturelle Integrität",
        "Feldwerte und reservierte Felder",
        "Auflösung jeder erforderlichen XID",
        "Ressourcentyp und Ownership",
    ):
        c.require(phrase in error_doc,
                  f"error coverage: missing normative validation-order/atomicity rule {phrase!r}")
    c.require(
        "request-spezifischen Zustands- und Backend-Prüfungen" in error_doc or
        "request-spezifische Zustands- und Backend-Prüfungen" in error_doc,
        "error coverage: missing normative request-specific state/backend validation phase",
    )



def check_other_numeric_registries(c: Check) -> None:
    """Guard the small numeric registries against duplicate or drifting assignments."""
    command_rows = [
        (int(value), symbol)
        for value, symbol in re.findall(
            r"^\|\s*(\d+)\s*\|\s*(CMD_[A-Z_]+)\s*\|",
            read("registries/command-entries.md"), re.M,
        )
    ]
    c.require([value for value, _symbol in command_rows] in ([1, 2, 3, 4], [1, 2, 3, 4, 5]),
              "command-entry registry must preserve IDs 1–4 and append only optional presentation ID 5")
    c.require(len({symbol for _value, symbol in command_rows}) == len(command_rows),
              "command-entry registry contains duplicate symbols")

    descriptor_rows = [
        (int(value), symbol)
        for value, symbol in re.findall(
            r"^\|\s*(\d+)\s*\|\s*`([A-Z_]+)`\s*\|",
            read("registries/descriptor-types.md"), re.M,
        )
    ]
    c.require([value for value, _symbol in descriptor_rows] == [0, 1],
              "descriptor-type registry must define reserved 0 and STORAGE_BUFFER 1")
    c.require(len({symbol for _value, symbol in descriptor_rows}) == len(descriptor_rows),
              "descriptor-type registry contains duplicate symbols")
    descriptor_updates = read("spec/shaders-pipelines.md")
    descriptor_errors = read("spec/errors.md")
    descriptor_conformance = read("spec/conformance.md")
    c.require(
        "nicht zugewiesene Werte ergeben `BadValue`" in descriptor_updates
        and "registrierter Descriptor-Typ" in descriptor_updates
        and "Mehrere Writes desselben Descriptor-Slots" in descriptor_updates,
        "UpdateDescriptorSets: normative text must distinguish invalid types, incompatible registered types, and duplicate slots",
    )
    c.require(
        "nicht zugewiesener `descriptor_type`" in descriptor_errors
        and "registrierter Descriptor-Typ inkompatibel" in descriptor_errors
        and "doppelte Writes desselben Slots" in descriptor_errors
        and "`descriptor_type = 0` und nicht zugewiesene Descriptor-Typ-Werte ergeben `BadValue`" in descriptor_conformance,
        "UpdateDescriptorSets: error map and conformance cases must agree on descriptor type validation",
    )
    lifetime = read("spec/resource-lifetime.md")
    c.require(
        "`ResetCommandBuffer` mit falscher Request-Länge ergibt `BadLength`" in descriptor_errors
        and "ein nicht verfügbares oder verlorenes logisches Device `DEVICE_UNAVAILABLE` beziehungsweise `DEVICE_LOST`" in descriptor_errors
        and "Nach erfolgreicher XID-/Ownership-Prüfung ergibt ein nicht verfügbares Device `DEVICE_UNAVAILABLE`" in read("spec/command-recording.md")
        and "DEVICE_UNAVAILABLE` / `DEVICE_LOST" in descriptor_conformance,
        "ResetCommandBuffer: device-state errors must be specified consistently across normative, error, and conformance chapters",
    )
    c.require(
        "Queue-Family-Index außerhalb des Device-Profils oder Queue Family ohne Command-Buffer-Unterstützung: `BadValue`" in descriptor_errors
        and "Queue-Family-Index außerhalb des Device-Profils oder ohne Command-Buffer-Unterstützung `BadValue`" in descriptor_errors
        and "Der Queue-Family-Index muss zu einer Queue-Family des logischen Devices gehören, die Command Buffers unterstützt" in read("spec/command-recording.md"),
        "error mapping: CreateCommandPool must consistently reject invalid or command-buffer-incompatible queue families with BadValue",
    )
    command_recording = read("spec/command-recording.md")
    decisions = read("DECISIONS.md")
    c.require(
        "nicht als unveränderlicher Snapshot" in command_recording
        and "aktualisiert atomar die abgeleiteten Buffer-Referenzen" in command_recording
        and "bei der späteren Submission die dann aktuellen Descriptor-Inhalte" in descriptor_updates,
        "descriptor updates: command buffers must observe current set contents and refresh indirect references",
    )
    c.require(
        "aktualisiert die daraus abgeleiteten internen Buffer-Referenzen" in lifetime
        and "nicht mehr referenzierten alten Ressource" in lifetime
        and "not invalidated solely by the update" in decisions,
        "descriptor update lifetime: stale references must be removed without invalidating executable command buffers",
    )

    device_rows = [
        (int(value), symbol)
        for value, symbol in re.findall(
            r"^\|\s*(\d+)\s*\|\s*`([A-Z_]+)`\s*\|",
            read("registries/device-types.md"), re.M,
        )
    ]
    c.require([value for value, _symbol in device_rows] == list(range(5)),
              "device-type registry must define values 0 through 4 exactly once")
    c.require(len({symbol for _value, symbol in device_rows}) == len(device_rows),
              "device-type registry contains duplicate symbols")

    queue_rows = [
        (int(bit), int(mask, 16), symbol)
        for bit, mask, symbol in re.findall(
            r"^\|\s*(\d+)\s*\|\s*`0x([0-9A-Fa-f]+)`\s*\|\s*`([A-Z_]+)`\s*\|",
            read("registries/queue-flags.md"), re.M,
        )
    ]
    c.require([bit for bit, _mask, _symbol in queue_rows] == list(range(5)),
              "queue-flag registry must define bits 0 through 4 exactly once")
    c.require(all(mask == 1 << bit for bit, mask, _symbol in queue_rows),
              "queue-flag masks must equal 1 shifted by their registered bit")
    c.require(len({symbol for _bit, _mask, symbol in queue_rows}) == len(queue_rows),
              "queue-flag registry contains duplicate symbols")

    stage_rows = [
        (int(bit), int(mask, 16), symbol)
        for bit, mask, symbol in re.findall(
            r"^\|\s*(\d+)\s*\|\s*`0x([0-9A-Fa-f]+)`\s*\|\s*`([A-Z_]+)`\s*\|",
            read("registries/shader-stages.md"), re.M,
        )
    ]
    c.require(stage_rows == [(0, 1, "COMPUTE")],
              "v0.1 shader-stage registry must assign only COMPUTE at bit 0")

    devices = read("spec/devices.md")
    property_parts = devices.split("Normative XAverius-Property-Type-IDs:", 1)
    c.require(len(property_parts) == 2, "devices.md: missing normative physical-property type table")
    property_table = property_parts[1].split("\n## ", 1)[0] if len(property_parts) == 2 else ""
    property_rows = [
        (int(value), symbol)
        for value, symbol in re.findall(
            r"^\|\s*(\d+)\s*\|\s*`([A-Z0-9_]+)`\s*\|",
            property_table, re.M,
        )
    ]
    c.require([value for value, _symbol in property_rows] == list(range(8)),
              "physical-property type IDs must be assigned 0 through 7 exactly once")
    c.require(len({symbol for _value, symbol in property_rows}) == len(property_rows),
              "physical-property type table contains duplicate symbols")
    property_registry = read("registries/physical-device-properties.md")
    for fragment in ("`BYTE_ARRAY` (5)", "`CARD32` (1)", "`CARD32_ARRAY` (6)"):
        c.require(fragment in property_registry,
                  f"physical-device property registry missing type mapping {fragment}")

    feature_registry = read("registries/feature-ids.md")
    extension_registry = read("registries/device-extensions.md")
    c.require("No optional device feature IDs are assigned in v0.1" in feature_registry,
              "feature-ID registry must explicitly preserve the empty v0.1 set")
    c.require("No optional device extensions are assigned in v0.1" in extension_registry,
              "device-extension registry must explicitly preserve the empty v0.1 set")


def check_request_document_coverage(c: Check) -> None:
    """Keep every registered request represented in error and conformance guidance."""
    registry = parse_request_registry(read("registries/request-subopcodes.md"))
    errors = read("spec/errors.md")
    conformance = read("spec/conformance.md")
    for opcode, (name, _kind) in sorted(registry.items()):
        c.require(f"`{name}`" in errors,
                  f"request {opcode} ({name}): missing from request-specific/central error guidance")
        c.require(f"`{name}`" in conformance,
                  f"request {opcode} ({name}): missing from conformance checklist")

    c.require(
        "`EnumeratePhysicalDevices`: falsche Request-Länge (`!= 8` Bytes) ergibt `BadLength`" in errors
        and "wenn keine Physical Devices verfügbar sind, ist eine leere erfolgreiche Reply mit `reply.length = 0` zulässig" in errors,
        "error mapping: EnumeratePhysicalDevices must define length failure and empty-result behavior",
    )
    c.require(
        "`CreateBuffer`: falsche feste Länge `BadLength`" in errors
        and "nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`" in errors
        and "fehlgeschlagene Backend-Erstellung wegen Speicherknappheit `ALLOCATION_FAILED`" in errors,
        "error mapping: CreateBuffer must distinguish device state from backend allocation failure",
    )
    c.require(
        "`AllocateMemory`: falsche Länge `BadLength`" in errors
        and "falscher live Ressourcentyp oder fremde Device-Ownership `BadMatch`" in errors
        and "nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`" in errors
        and "bei Ablehnung bleibt die Ziel-XID unangelegt" in errors
        and "die `memory_xid` bleibt unangelegt" in read("spec/memory-buffers.md"),
        "error mapping: AllocateMemory must define device-state errors and atomic create-XID behavior",
    )
    c.require(
        "`CreateDescriptorPool`: falsche Länge" in errors
        and "falscher live Ressourcentyp oder fremde Device-Ownership `BadMatch`" in errors
        and "nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`" in errors
        and "bei Ablehnung bleibt die Pool-XID unangelegt" in errors
        and "bei jedem Fehler bleibt die Pool-XID unangelegt" in read("spec/shaders-pipelines.md"),
        "error mapping: CreateDescriptorPool must define device-state errors and atomic create-XID behavior",
    )
    c.require(
        "`CreateSemaphore` und `CreateFence`:" in errors
        and "falscher live Ressourcentyp oder fremde Device-Ownership `BadMatch`" in errors
        and "nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`" in errors
        and "bei Ablehnung bleibt die jeweilige Ziel-XID unangelegt" in errors
        and "bei jedem Fehler bleibt die Semaphore-XID unangelegt" in read("spec/synchronization.md")
        and "bei jedem Fehler bleibt die Fence-XID unangelegt" in read("spec/synchronization.md"),
        "error mapping: CreateSemaphore/CreateFence must define device-state errors and atomic XID behavior",
    )
    c.require(
        "Nicht verfügbares/verlorenes Device: `DEVICE_UNAVAILABLE` / `DEVICE_LOST`" in errors
        and "synchroner Backend-Allokationsfehler: `ALLOCATION_FAILED`" in errors
        and "falscher live Ressourcentyp, fremde Device-Ownership oder Cross-Device-Ressource: `BadMatch`" in errors,
        "error mapping: CreateDescriptorSetLayout must distinguish device, ownership and allocation errors",
    )
    c.require(
        "`CreatePipelineLayout`:" in errors
        and "nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`" in errors
        and "Backend-Allokationsfehler `ALLOCATION_FAILED`" in errors
        and "Kein Pipeline Layout bleibt bei Ablehnung live" in errors
        and "Bei jedem Fehler bleibt die Pipeline-Layout-XID unangelegt" in read("spec/shaders-pipelines.md"),
        "error mapping: CreatePipelineLayout must define device-state and atomic creation behavior",
    )
    c.require(
        "`CreateComputePipeline`:" in errors
        and "nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`" in errors
        and "Backend-Allokationsfehler `ALLOCATION_FAILED`" in errors
        and "Kein Pipeline-Objekt bleibt bei Ablehnung live" in errors
        and "bei Fehlern wird kein Pipeline-Objekt öffentlich angelegt" in read("spec/shaders-pipelines.md"),
        "error mapping: CreateComputePipeline must define device-state and atomic creation behavior",
    )
    c.require(
        "### `CreateCommandPool`" in errors
        and "Nicht verfügbares/verlorenes Device: `DEVICE_UNAVAILABLE` / `DEVICE_LOST`" in errors
        and "Backend-Allokationsfehler: `ALLOCATION_FAILED`" in errors
        and "Bei Ablehnung bleibt die Pool-XID unangelegt" in errors
        and "bei jedem Fehler bleibt die Pool-XID unangelegt" in read("spec/command-recording.md"),
        "error mapping: CreateCommandPool must define device-state and atomic creation behavior",
    )
    command_recording = read("spec/command-recording.md")
    c.require(
        all(token in command_recording for token in (
            "| 0 | 0 | 0 | Entries an einen bereits aufzeichnenden Buffer anhängen |",
            "| 0 | 1 | 0 | Letzte Entries anhängen und Recording beenden |",
            "| 1 | 0 | 0 | Command Buffer erstellen, Recording beginnen, ersten Chunk aufzeichnen |",
            "| 1 | 1 | 0 | Command Buffer erstellen, kompletten Stream aufzeichnen und beenden |",
            "| 0 | 0 | 1 | Recording abbrechen; keine Entries erlaubt |",
        )),
        "CommandBufferData: the five permitted CREATE/FINAL/ABORT combinations must remain explicit",
    )
    c.require(
        "muss auch bei" in command_recording and "ABORT" in command_recording
        and "exakt der Eltern-Pool" in errors,
        "CommandBufferData: ABORT must validate exact command-pool ownership",
    )
    c.require(
        "zuerst die Ziel-XID und danach die Pool-XID" in errors
        and "ungültige oder bereits belegte Ziel-XID" in errors
        and "unbekannte/nicht-live Buffer-XIDs" in errors,
        "CommandBufferData: target-XID error precedence must distinguish CREATE from input lookup",
    )
    c.require("### Fehlerpräzedenz für `CommandBufferData`" in command_recording and
              "Feldfehler schlagen Ziel-/Pool-XID-Fehler" in command_recording and
              "Device Loss" in command_recording and
              "ABORT" in command_recording and
              "hat damit Vorrang vor einem nicht passenden Buffer-Zustand" in errors,
              "CommandBufferData: syntax/XID/ownership/device/state precedence and ABORT exception must agree")
    c.require("CommandBufferData`-Fehlerpräzedenz: fehlerhafte Request-/Entry-Struktur" in conformance and
              "ungültiger Flag-Kombination und ungültiger Ziel-XID gewinnt `BadValue`" in conformance and
              "ist die definierte Ausnahme von Phase 5" in command_recording,
              "CommandBufferData: error precedence edge cases must be covered by conformance")
    c.require(
        "dessen deklarierte Länge über das Request-Ende hinausreicht" in errors
        and "insbesondere null oder kleiner als der Entry-Header" in errors
        and "unbekannte Command-ID" in errors,
        "CommandBufferData: malformed entry length and unknown command ID errors must be explicit",
    )
    c.require(
        "Ein fehlgeschlagener FINAL-Chunk lässt den Buffer" in errors
        and "Fehlgeschlagenes CREATE hinterlässt keinen Command Buffer" in conformance
        and "prüft Request-Länge, XIDs, Typ, Ownership und Cross-Device-Zuordnung vor Zustandsänderungen" in conformance,
        "command-buffer recovery: failed CREATE/FINAL and reset atomicity must be covered",
    )
    shader_upload = read("spec/shaders-pipelines.md")
    event_doc = read("spec/events.md")
    c.require(
        "A later chunk or ABORT for a discarded assembly" in shader_upload
        and "They do not emit `ASYNC_ERROR`" in shader_upload
        and "Fehler bei `ShaderModuleData` erzeugen kein `ASYNC_ERROR`" in errors
        and "`ShaderModuleData`-Upload und bei `CommandBufferData`-Recording-Chunks sind immer synchron" in event_doc,
        "chunked shader upload: failed/interrupted assemblies must be discarded and chunk errors must stay synchronous",
    )
    c.require(
        "CREATE-, Append- und FINAL-Requests bei nicht verfügbarem/verlorenem Device" in command_recording
        and "`ABORT` bleibt als rein logische Recovery-/Cleanup-Operation auch nach Device Loss zulässig" in command_recording
        and "`ABORT` ist die ausdrücklich logische Ausnahme" in errors
        and "Nach Device Loss werden CREATE-/Append-/FINAL-Chunks von `CommandBufferData` mit `DEVICE_LOST` abgewiesen" in conformance,
        "CommandBufferData: device-loss failures must preserve accepted chunks while ABORT remains logical cleanup",
    )
    c.require(
        "Chunk-Fehler sind synchron dem jeweiligen `CommandBufferData`-Request zugeordnet und erzeugen kein `ASYNC_ERROR`" in command_recording
        and "Fehler beim `ShaderModuleData`-Upload und bei `CommandBufferData`-Recording-Chunks sind immer synchron" in event_doc
        and "erzeugen kein `ASYNC_ERROR`" in conformance,
        "chunked shader/command-buffer operations must not emit async errors before submission acceptance",
    )
    c.require(
        "`AllocateDescriptorSets`:" in errors
        and "nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`" in errors
        and "Backend-Allokationsfehler `ALLOCATION_FAILED`" in errors
        and "keine Teilmenge der angeforderten Sets live" in errors
        and "keine Teilmenge der Sets öffentlich angelegt bleiben" in read("spec/shaders-pipelines.md"),
        "error mapping: AllocateDescriptorSets must define device-state and atomic batch behavior",
    )
    c.require(
        "`FreeDescriptorSets`:" in errors
        and "pending oder RECORDING-Referenz `INVALID_SYNCHRONIZATION_STATE`" in errors
        and "Nach Device Loss bleibt die logische Freigabe zulässig" in errors
        and "Keine Teilfreigabe bei Ablehnung" in errors
        and "Die Freigabe ist atomar" in read("spec/shaders-pipelines.md")
        and "FreeDescriptorSets` ist eine logische Freigabe und bleibt nach Device Loss zulässig" in read("spec/shaders-pipelines.md"),
        "error mapping: FreeDescriptorSets must allow logical cleanup after device loss and preserve atomic batch behavior",
    )


    # Keep generic and resource-specific destruction paths aligned across chapters.
    lifetime = read("spec/resource-lifetime.md")
    destroy_section = re.search(
        r"^## `DestroyResource`\n(.*?)(?=^## )",
        lifetime, re.M | re.S,
    )
    c.require(destroy_section is not None,
              "resource lifetime: missing normative DestroyResource section")
    if destroy_section:
        generic = destroy_section.group(1)
        c.require(
            "ausschließlich für Buffer, Shader Module, Descriptor Set Layout, Pipeline Layout und Pipeline" in generic,
            "DestroyResource: eligible generic resource types changed or are incomplete",
        )
        c.require(
            "Physical Devices, logische Devices, Command Pools, Descriptor Pools, Command Buffers, Descriptor Sets, Memory, Fences oder Semaphores" in generic,
            "DestroyResource: excluded resource types must remain explicit",
        )
        c.require(
            "`DestroyDescriptorPool`, `FreeDescriptorSets`, `FreeMemory`, `DestroyFence` oder `DestroySemaphore`" in generic,
            "DestroyResource: specialized destruction paths must be named",
        )

    registry_text = read("registries/request-subopcodes.md")
    c.require(
        re.search(
            r"\| `DestroyResource` \| 39 \| Void \| Generic destroy for Buffer, Shader Module, Descriptor Set Layout, Pipeline Layout, and Pipeline; synchronization objects use dedicated destroy requests\.",
            registry_text,
        ) is not None,
        "request registry: DestroyResource scope must match normative eligible types",
    )
    c.require(
        re.search(
            r"`DestroyResource` akzeptiert nur Buffer, Shader Module, Descriptor Set Layout, Pipeline Layout und Pipeline;.*?Fence und Semaphore werden ausschließlich über `DestroyFence` beziehungsweise `DestroySemaphore` zerstört",
            conformance, re.S,
        ) is not None,
        "conformance: generic and specialized destruction paths must be explicit",
    )
    c.require(
        "Descriptor Sets, die den Buffer enthalten, bleiben als Objekte bestehen" in lifetime
        and "bis alle betroffenen Descriptor-Slots mit gültigen Buffer-Referenzen aktualisiert wurden oder die Sets freigegeben wurden" in lifetime
        and "interne Bindungsreferenz auf die Memory-Allokation bleibt während dieser gesamten Zeit bestehen" in lifetime,
        "resource lifetime: stale descriptor slots must retain Buffer and bound Memory",
    )
    c.require(
        re.search(
            r"\|\s*`DestroyResource`: Ressourcentyp ist nicht für den generischen Request zugelassen oder Ressource gehört einem anderen Client\s*\|\s*`BadMatch`\s*\|",
            errors,
        ) is not None,
        "error mapping: disallowed DestroyResource types and foreign ownership must map to BadMatch",
    )
    c.require(
        "`FreeDescriptorSets`: falsche Länge `BadLength`" in errors
        and "pending oder RECORDING-Referenz `INVALID_SYNCHRONIZATION_STATE`" in errors,
        "error mapping: FreeDescriptorSets must retain atomic pending/recording rejection",
    )

    c.require(
        re.search(
            r"`DestroyDescriptorPool` ist atomar.*?wenn ein enthaltenes Set pending verwendet wird oder von einem `RECORDING`-Command-Buffer referenziert wird.*?Bei Ablehnung bleiben Pool, Sets und Command-Buffer-Zustände unverändert",
            lifetime, re.S,
        ) is not None,
        "resource lifetime: DestroyDescriptorPool must reject pending/recording children atomically",
    )

    c.require(
        "`DestroyCommandPool`: falsche Länge `BadLength`" in errors
        and "mindestens ein pending Kind-Command-Buffer `INVALID_SYNCHRONIZATION_STATE`" in errors
        and "Ablehnung ist atomar" in errors,
        "error mapping: DestroyCommandPool must define length, pending-child, and atomicity outcomes",
    )
    c.require(
        "Device Loss allein verhindert `DestroyCommandPool` nicht" in read("spec/command-recording.md")
        and "Device Loss allein verhindert `DestroyDescriptorPool` nicht" in read("spec/shaders-pipelines.md")
        and "Device Loss allein ist kein Ablehnungsgrund" in errors
        and "Device Loss allein blockiert `DestroyCommandPool` und `DestroyDescriptorPool` nicht" in conformance,
        "device loss: logical command/descriptor pool destruction must remain available subject to lifetime guards",
    )

    # The summary matrix must not contradict the normative recorded-reference
    # rules for descriptor sets and pipeline objects.
    c.require(
        "| DescriptorSet | XID wird ungültig | Abweisen, solange pending oder von einem `RECORDING`-Command-Buffer referenziert; bei Erfolg werden referenzierende nicht-pending `EXECUTABLE`-Command-Buffer `INVALID` |" in lifetime
        and "| Pipeline | XID wird ungültig | Abweisen, solange ein `RECORDING`-Command-Buffer sie referenziert oder angenommene Arbeit sie verwendet; bei Erfolg werden referenzierende nicht-pending `EXECUTABLE`-Command-Buffer `INVALID` |" in lifetime
        and "| PipelineLayout | XID wird ungültig | Abweisen, solange ein `RECORDING`-Command-Buffer es referenziert oder angenommene Arbeit es verwendet; bei Erfolg werden referenzierende nicht-pending `EXECUTABLE`-Command-Buffer `INVALID` |" in lifetime,
        "resource lifetime: DescriptorSet, Pipeline, and PipelineLayout matrix rows must match recording/pending and executable-invalidation rules",
    )
    c.require(
        "`FreeDescriptorSets` weist die Freigabe atomar mit `INVALID_SYNCHRONIZATION_STATE` ab, wenn ein ausgewähltes Set pending verwendet oder von einem `RECORDING`-Command-Buffer referenziert wird" in conformance
        and "`DestroyResource` auf Pipeline oder Pipeline Layout weist Recording-Referenzen und angenommene Pending-Use atomar ab" in conformance,
        "conformance: descriptor-set and pipeline recorded-reference lifetime rules must be explicit",
    )
    c.require(
        "`DestroyFence`: `INVALID_SYNCHRONIZATION_STATE`" in errors
        and "`DestroySemaphore`: `INVALID_SYNCHRONIZATION_STATE`" in errors
        and "solange die Fence einer nicht-terminalen Submission zugeordnet ist oder eine offene" in errors
        and "angenommener Queue-Wait/-Signal" in errors
        and "eine andere laufende Host-Operation die Semaphore verwendet" in errors,
        "error mapping: fence/semaphore destruction must preserve pending-use guards",
    )

    c.require(
        "`DestroyDescriptorPool`: falsche Request-Länge `BadLength`" in errors
        and "unbekannte/nicht-live Pool-XID `BadValue`" in errors
        and "falscher live Ressourcentyp oder fremde Client-/Device-Ownership `BadMatch`" in errors
        and "wenn ein Kind-Set pending verwendet oder von einem `RECORDING`-Command-Buffer referenziert wird, `INVALID_SYNCHRONIZATION_STATE`" in errors
        and "Pool, Sets und Referenzen bleiben unverändert" in errors,
        "error mapping: DestroyDescriptorPool must define XID, ownership, pending-use, and atomicity outcomes",
    )


    lifetime = read("spec/resource-lifetime.md")
    c.require(
        "Device Loss allein invalidiert keine öffentlichen XIDs" in lifetime
        and "`GetFenceStatus` und `DestroyDevice` nach Device Loss nutzbar" in lifetime
        and "Device Loss allein invalidiert keine öffentlichen Device-/Ressourcen-XIDs" in read("spec/conformance.md"),
        "device loss: public XIDs must remain available for permitted status queries and explicit cleanup",
    )
    c.require(
        "Einzelne ressourcenspezifische Destroy-/Free-Requests sind nach Device Loss nicht pauschal verboten" in lifetime
        and "`FreeMemory` bleibt gesperrt, solange intern noch ein Buffer gebunden ist" in lifetime
        and "Einzelne Destroy-/Free-Requests werden nach Device Loss nicht pauschal mit `DEVICE_LOST` abgewiesen" in read("spec/conformance.md"),
        "device loss: resource-specific cleanup must preserve ordinary lifetime guards and memory safety",
    )
    c.require(
        "offene `WaitForFence`-Registrierung" in lifetime
        and "offene `WaitSemaphores`-Registrierung" in lifetime
        and "terminal festgestellte Waits blockieren nicht nur wegen eines noch ausstehenden Reply" in lifetime,
        "lifetime: fence/semaphore destroy matrix must include open waits and terminal release",
    )
    c.require(
        "offene `WaitForFence`-Registrierung" in errors
        and "offene `WaitSemaphores`-Registrierung" in errors
        and "ein noch nicht versendeter Reply ist kein Hindernis" in errors,
        "error mapping: summary must agree with specialized fence/semaphore destroy rules",
    )
    c.require(
        "`DestroyFence`: falsche Länge `BadLength`" in errors
        and "offene `WaitForFence`-Registrierung genau diese interne Fence-Identität referenziert" in errors
        and "terminal festgestellte Wait-Registrierung blockiert die Zerstörung nicht" in errors,
        "error mapping: DestroyFence must cover length, open waits, and terminal wait release",
    )
    c.require(
        "`DestroySemaphore`: falsche Länge `BadLength`" in errors
        and "offene `WaitSemaphores`-Registrierung für genau diese interne Semaphore-Identität" in errors
        and "andere laufende Host-Operation" in errors
        and "Device Loss allein invalidiert keine öffentlichen XIDs" in errors
        and "wenn anschließend `DestroyDevice` verarbeitet wird" in errors,
        "error mapping: DestroySemaphore must cover length, host waits, identity, and device-loss teardown",
    )

def normalize_length_formula(value: str) -> str:
    """Normalize insignificant whitespace and the audit's pad4 shorthand."""
    value = value.replace("`", "")
    value = value.replace("~uint64(3)", "~3")
    value = re.sub(r"uint64\(([^()]*)\)", r"\1", value)
    value = re.sub(r"pad4\(([^()]*)\)", r"((\1+3)&~3)", value)
    return re.sub(r"\s+", "", value)


def request_normative_section(document: str, request: str) -> str:
    """Return the defining H2 section for a request, including numbered headings."""
    lines = document.splitlines()
    heading_indexes = [
        i for i, line in enumerate(lines)
        if re.match(r"^##\s+", line) and request in line
    ]
    if heading_indexes:
        start = heading_indexes[0]
    else:
        # A few chapters use a descriptive heading (e.g. Compute Pipeline); find
        # the first request declaration and anchor it to its containing H2.
        occurrences = [i for i, line in enumerate(lines) if request in line]
        if not occurrences:
            return ""
        occurrence = occurrences[0]
        prior = [i for i in range(occurrence + 1) if re.match(r"^##\s+", lines[i])]
        if not prior:
            return ""
        start = prior[-1]
    end = next((i for i in range(start + 1, len(lines))
                if re.match(r"^##\s+", lines[i])), len(lines))
    return "\n".join(lines[start:end])


def check_request_matrix_normative_lengths(c: Check) -> None:
    """Cross-check every variable-length matrix formula against its defining chapter."""
    audit = read("spec/request-audit.md")
    registry_text = read("registries/request-subopcodes.md")
    registry_rows = {
        name: responsibility
        for name, _opcode, _kind, responsibility in re.findall(
            r"^\|\s*\`([^\`]+)\`\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|",
            registry_text, re.M,
        )
    }
    matrix = audit.split("## Per-request contract matrix", 1)
    c.require(len(matrix) == 2, "request matrix: missing normative cross-check matrix")
    if len(matrix) != 2:
        return
    matrix_body = matrix[1].split("\n## ", 1)[0]
    rows = re.findall(
        r"^\|\s*(\d+)\s*\|\s*\`([^\`]+)\`\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|",
        matrix_body, re.M,
    )
    fixed_lengths = {
        "EnumeratePhysicalDevices": 8,
        "GetPhysicalDeviceProperty": 16,
        "GetPhysicalDeviceQueueFamilyProperties": 12,
        "DestroyDevice": 12,
        "GetPhysicalDeviceMemoryProperties": 12,
        "CreateBuffer": 32,
        "GetBufferMemoryRequirements": 16,
        "AllocateMemory": 32,
        "FreeMemory": 16,
        "BindBufferMemory": 28,
        "ReadBuffer": 28,
        "DestroyDescriptorPool": 16,
        "CreateCommandPool": 24,
        "DestroyCommandPool": 16,
        "ResetCommandBuffer": 16,
        "CreateSemaphore": 28,
        "GetSemaphoreCounterValue": 16,
        "SignalSemaphore": 24,
        "DestroySemaphore": 16,
        "CreateFence": 24,
        "GetFenceStatus": 16,
        "WaitForFence": 24,
        "ResetFence": 16,
        "DestroyFence": 16,
        "DestroyResource": 12,
        "SelectEvents": 32,
    }
    formula_overrides = {
        "CreateDevice": "24 + Σ(8 + 4 * queue_count_i) + 8 * feature_request_count + Σ(4 + ((name_length_j + 3) & ~3))",
        "CreateDefaultDevice": "16 + 4 * queue_count",
        "WriteBuffer": "28 + ((uint64(data_length) + 3) & ~uint64(3))",
        "ShaderModuleData": "20 + ((data_length + 3) & ~3)",
        "CreateDescriptorSetLayout": "24 + 16 * binding_count",
        "CreateDescriptorPool": "24 + 8 * pool_size_count",
        "AllocateDescriptorSets": "20 + 8 * descriptor_set_count",
        "UpdateDescriptorSets": "20 + 36 * write_count",
        "FreeDescriptorSets": "20 + 4 * descriptor_set_count",
        "CreatePipelineLayout": "20 + 4 * set_layout_count + 12 * push_constant_range_count",
        "CreateComputePipeline": "28 + ((entry_point_length + 3) & ~3)",
        "QueueSubmit": "40 + 4*C + 16*W + 12*S",
        "WaitSemaphores": "28 + 12 * semaphore_count",
    }
    c.require(len(rows) in (40, 47),
              f"request matrix: expected 40 baseline or 47 audited rows, found {len(rows)}")
    for _opcode, request, _kind, matrix_length in rows:
        if request not in formula_overrides and request not in fixed_lengths and request != "CommandBufferData":
            continue
        responsibility = registry_rows.get(request, "")
        link = re.search(r"\.\./spec/([^)]*\.md)", responsibility)
        c.require(link is not None, f"{request}: registry lacks a defining normative chapter link")
        if not link:
            continue
        chapter = read("spec/" + link.group(1))
        section = request_normative_section(chapter, request)
        c.require(bool(section), f"{request}: cannot locate defining normative section")
        if request in formula_overrides:
            expected = normalize_length_formula(formula_overrides[request])
            normative = normalize_length_formula(section)
            c.require(expected in normative,
                      f"{request}: normative section does not state the expected request-length formula")
            matrix_formula = matrix_length.split(";", 1)[0].strip()
            c.require(normalize_length_formula(matrix_formula) == expected,
                      f"{request}: audit matrix length {matrix_length!r} disagrees with the canonical formula")
        elif request in fixed_lengths:
            expected_bytes = fixed_lengths[request]
            length_evidence = re.search(
                rf"(?:Gesamtlänge|Request(?:-Länge| length)?|Request-Größe|Request size|hat|ist|beträgt)[^\n]{{0,100}}\b{expected_bytes}\s*Bytes?\b|"
                rf"\b{expected_bytes}\s*Bytes?\b[^\n]{{0,80}}(?:Gesamtlänge|Request)",
                section, re.I,
            )
            c.require(length_evidence is not None,
                      f"{request}: normative section does not explicitly state the matrix's {expected_bytes}-byte request length")
            c.require(normalize_length_formula(matrix_length).strip("\`") == str(expected_bytes),
                      f"{request}: audit matrix fixed length {matrix_length!r} disagrees with normative {expected_bytes} bytes")
        else:
            c.require("mindestens 16 Bytes" in section and "exakt 16 Bytes" in section,
                      "CommandBufferData: normative variable length must define 16-byte minimum and exact 16-byte ABORT")


def check_request_limit_contract(c: Check) -> None:
    """Guard ordinary X11 request limits and the incompatible BIG-REQUESTS header."""
    wire = read("spec/wire-protocol.md")
    conformance = read("spec/conformance.md")
    c.require(
        "BIG-REQUESTS wird in v0.1 nicht unterstützt" in wire
        and "length = 0" in wire
        and "`BadLength` zurückweisen" in wire
        and "bevor er Bytes ab Offset 4 als XAverius-Subopcode" in wire,
        "request framing: BIG-REQUESTS length must be rejected before common-header parsing",
    )
    c.require(
        "eine erwartete Länge über 262140 Bytes" in wire
        and "vor Payload-Allokation, XID-Auflösung und Zustandsänderungen" in wire
        and "die maximale Länge gilt pro Request" in wire,
        "request framing: checked arithmetic, maximum ordinary request size, and validation order must be normative",
    )
    matrix = read("spec/request-audit.md").split("## Per-request contract matrix", 1)
    c.require(len(matrix) == 2, "request limit: missing request audit matrix")
    if len(matrix) != 2:
        return
    matrix_body = matrix[1].split("\n## ", 1)[0]
    rows = re.findall(
        r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|",
        matrix_body, re.M,
    )
    variable = {
        name.strip(chr(96) + " ") for _opcode, name, _kind, length in rows
        if not re.fullmatch(r"\d+", length.strip(chr(96) + " "))
    }
    expected_variable = {
        "CreateDevice", "CreateDefaultDevice", "WriteBuffer", "ShaderModuleData",
        "CreateDescriptorSetLayout", "CreateDescriptorPool", "AllocateDescriptorSets",
        "UpdateDescriptorSets", "FreeDescriptorSets", "CreatePipelineLayout",
        "CreateComputePipeline", "CommandBufferData", "QueueSubmit", "WaitSemaphores",
    }
    if len(rows) == 47:
        expected_variable = expected_variable | {"QueuePresent"}
    c.require(len(rows) in (40, 47),
              f"request limit: expected 40 baseline or 47 audited matrix rows, found {len(rows)}")
    c.require(variable == expected_variable,
              f"request limit: variable-length request set changed unexpectedly: {sorted(variable)}")
    required_cases = (
        "whose original X11 16-bit",
        "exactly 262140 bytes is the maximum permitted size",
        "evaluated with checked arithmetic",
        "before payload allocation, XID lookup, or state mutation",
        "enforce the limit per wire request",
        "no partial resource creation",
    )
    for phrase in required_cases:
        c.require(phrase in conformance,
                  f"request limit: missing conformance case {phrase!r}")


def check_local_markdown_links(c: Check) -> None:
    """Reject broken relative links in repository Markdown documents."""
    link_pattern = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
    documents = sorted(
        path for path in ROOT.rglob("*.md")
        if ".git" not in path.parts and "node_modules" not in path.parts
    )
    for source in documents:
        text = source.read_text(encoding="utf-8")
        for match in link_pattern.finditer(text):
            target = match.group(1)
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            decoded_path = unquote(parsed.path)
            candidate = (source.parent / decoded_path).resolve()
            try:
                candidate.relative_to(ROOT.resolve())
            except ValueError:
                c.require(False, f"markdown link escapes repository: {source.relative_to(ROOT)} -> {target}")
                continue
            line = text.count("\n", 0, match.start()) + 1
            c.require(
                candidate.exists(),
                f"broken local Markdown link: {source.relative_to(ROOT)}:{line} -> {target}",
            )


def check_reply_matrix(c: Check) -> None:
    registry_text = read("registries/request-subopcodes.md")
    registry_rows = [
        (name, int(opcode), kind.strip())
        for name, opcode, kind in re.findall(
            r"^\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|",
            registry_text, re.M,
        )
    ]
    registry = parse_request_registry(registry_text)
    opcodes = [opcode for _name, opcode, _kind in registry_rows]
    names = [name for name, _opcode, _kind in registry_rows]
    c.require(len(registry_rows) in (40, 47),
              f"request registry: expected 40 baseline or 47 audited table rows, found {len(registry_rows)}")
    c.require(len(set(opcodes)) == len(opcodes), "request registry contains duplicate subopcode values")
    c.require(len(set(names)) == len(names), "request registry contains duplicate request names")
    c.require(set(opcodes) in (set(range(1, 41)), set(range(1, 48))),
              "request registry must preserve IDs 1–40 and append presentation IDs 41–47; 0 is reserved")
    audit = read("spec/request-audit.md")
    matrix = audit.split("## Per-request contract matrix", 1)
    c.require(len(matrix) == 2, "request-audit.md: missing per-request contract matrix")
    if len(matrix) != 2:
        return
    matrix_rows: dict[int, tuple[str, str, str]] = {}
    for line in matrix[1].splitlines():
        row = re.match(r"^\|\s*(\d+)\s*\|\s*`([^\x60]+)`\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", line)
        if row:
            opcode, name, kind, length = int(row.group(1)), row.group(2), row.group(3).strip(), row.group(4).strip()
            matrix_rows[opcode] = (name, kind, length)
    c.require(len(registry) in (40, 47),
              f"request registry: expected 40 baseline or 47 audited requests, found {len(registry)}")
    c.require(len(matrix_rows) in (40, 47),
              f"request audit matrix: expected 40 baseline or 47 audited rows, found {len(matrix_rows)}")
    c.require(set(matrix_rows) - set(registry) <= set(range(41, 48)) and
              set(registry) - set(matrix_rows) <= set(range(41, 48)),
              "request audit matrix and registry may differ only by presentation IDs 41–47 during staged updates")
    for opcode, (name, kind) in registry.items():
        c.require(opcode in matrix_rows, f"request audit matrix: missing subopcode {opcode} ({name})")
        if opcode not in matrix_rows:
            continue
        audit_name, audit_kind, length = matrix_rows[opcode]
        c.require(audit_name == name, f"subopcode {opcode}: audit names {audit_name}, registry names {name}")
        # Registry classifications use concise tokens; the audit may spell out the async-event case.
        normalized_kind = "Void + async events" if "async" in kind.lower() else kind
        c.require(audit_kind.lower() == normalized_kind.lower(),
                  f"subopcode {opcode} ({name}): kind mismatch audit={audit_kind!r}, registry={kind!r}")
        c.require(bool(length) and length != "—", f"subopcode {opcode} ({name}): missing request length contract")
        if "Reply" in kind:
            c.require(bool(re.search(r"\b(?:Reply|reply)\b", kind, re.I)),
                      f"subopcode {opcode} ({name}): reply classification missing")
    # High-value reply ABI invariants that are explicit and normative in the audit/conformance docs.
    invariants = [
        (r"`EnumeratePhysicalDevices`.*?\| Reply \| 8 \|", "EnumeratePhysicalDevices is an 8-byte Reply request"),
        (r"`GetPhysicalDeviceQueueFamilyProperties`.*?\| Reply \| 12 \|", "queue-family query is a 12-byte Reply request"),
        (r"`GetFenceStatus`.*?\| Reply \| 16 \|", "GetFenceStatus is a 16-byte Reply request"),
        (r"`WaitForFence`.*?\| Reply \| 24 \|", "WaitForFence is a 24-byte Reply request"),
        (r"`ReadBuffer`.*?\| Reply \| 28 \|", "ReadBuffer is a 28-byte Reply request"),
        (r"reply\.length.*?3 \* queue_family_count", "queue-family reply length formula is documented"),
        (r"reply\.length.*?PHYSICALDEVICEINFO", "physical-device enumeration reply length formula is documented"),
        (r"GetFenceStatus.*?Reply-Byte 1|GetFenceStatus.*?Reply-Byte 1", "fence status reply byte is documented"),
    ]
    combined = audit + "\n" + read("spec/conformance.md") + "\n" + read("spec/synchronization.md")
    for pattern, label in invariants:
        c.require(re.search(pattern, combined, re.I | re.S) is not None, f"reply ABI: missing invariant: {label}")


def chapter_section(markdown: str, request: str) -> str:
    """Extract a request's normative H2 section, including numbered headings."""
    heading = re.search(
        r"^## [^\n]*\x60" + re.escape(request) + r"\x60[^\n]*$",
        markdown, re.M,
    )
    if not heading:
        return ""
    following = re.search(r"^## ", markdown[heading.end():], re.M)
    end = heading.end() + following.start() if following else len(markdown)
    return markdown[heading.end():end]


def check_reply_layouts(c: Check) -> None:
    # Each registered Reply request must have a chapter-level ABI contract.
    # These checks intentionally match normative text, not a shadow copy of offsets.
    registry = parse_request_registry(read("registries/request-subopcodes.md"))
    reply_names = {name for _, (name, kind) in registry.items() if kind == "Reply"}
    expected_names = {
        "EnumeratePhysicalDevices", "GetPhysicalDeviceProperty",
        "GetPhysicalDeviceQueueFamilyProperties", "GetPhysicalDeviceMemoryProperties",
        "GetBufferMemoryRequirements", "WriteBuffer", "ReadBuffer",
        "GetSemaphoreCounterValue", "WaitSemaphores", "GetFenceStatus", "WaitForFence",
    }
    presentation_reply_names = {
        "GetSurfaceCapabilities", "CreateSwapchain", "AcquireNextImage", "QueuePresent",
    }
    c.require(reply_names - presentation_reply_names == expected_names and
              (reply_names & presentation_reply_names) in (set(), presentation_reply_names),
              f"reply contract inventory mismatch: registry={sorted(reply_names)}, checker={sorted(expected_names)}")

    sources = {
        "devices": read("spec/devices.md"),
        "memory": read("spec/memory-buffers.md"),
        "sync": read("spec/synchronization.md"),
        "wire": read("spec/wire-protocol.md"),
    }
    contracts = {
        "EnumeratePhysicalDevices": ("devices", [
            (r"null oder mehr \x60PHYSICALDEVICEINFO\x60-Records", "variable PHYSICALDEVICEINFO records"),
            (r"reply\.length = Summe aller Record-Längen / 4", "record-sum reply.length formula"),
            (r"Fester Record-Anteil: 32 Bytes", "32-byte fixed record prefix"),
            (r"32 \+ \(\(device_name_length \+ 3\) & ~3\)", "padded device-name record formula"),
            (r"\|\s*28\s*\|\s*CARD16\s*\|\s*\x60device_name_length\x60\s*\|", "device-name length field"),
            (r"\|\s*30\s*\|\s*CARD16\s*\|\s*\x60reserved = 0\x60\s*\|", "record reserved field"),
            (r"Padding muss null sein", "zero record padding"),
            (r"\|\s*0\s*\|\s*XID\s*\|\s*\x60physical_device_xid\x60\s*\|", "physical-device XID at record offset 0"),
            (r"\|\s*4\s*\|\s*CARD32\s*\|\s*\x60device_type\x60\s*\|", "device type at record offset 4"),
            (r"\|\s*8\s*\|\s*CARD32\s*\|\s*\x60vendor_id\x60\s*\|", "vendor ID at record offset 8"),
            (r"\|\s*12\s*\|\s*CARD32\s*\|\s*\x60device_id\x60\s*\|", "device ID at record offset 12"),
            (r"\|\s*16\s*\|\s*CARD32\s*\|\s*\x60api_version\x60\s*\|", "API version at record offset 16"),
            (r"\|\s*20\s*\|\s*CARD32\s*\|\s*\x60driver_version\x60\s*\|", "driver version at record offset 20"),
            (r"\|\s*24\s*\|\s*CARD32\s*\|\s*\x60compute_queue_family_count\x60\s*\|", "compute queue count at record offset 24"),
            (r"\|\s*32\s*\|\s*BYTE\[\]\s*\|\s*UTF-8-Gerätename", "device name payload at record offset 32"),
        ]),
        "GetPhysicalDeviceProperty": ("devices", [
            (r"\|\s*8\s*\|\s*CARD32\s*\|\s*\x60status\x60\s*\|", "status at offset 8"),
            (r"\|\s*12\s*\|\s*CARD32\s*\|\s*\x60property_type\x60\s*\|", "property type at offset 12"),
            (r"\|\s*16\s*\|\s*CARD32\s*\|\s*\x60value_length\x60 in Bytes\s*\|", "value length at offset 16"),
            (r"\|\s*20–31\s*\|\s*BYTE\[12\]\s*\|\s*reserviert, null\s*\|", "reserved bytes 20–31"),
            (r"reply\.length = ceil\(value_length / 4\)", "variable value payload formula"),
            (r"Status ungleich \x60SUCCESS\x60.*?reply\.length = 0", "empty failure-status reply"),
            (r"Bei einem Status ungleich \x60SUCCESS\x60 müssen \x60property_type\x60 und \x60value_length\x60 null sein", "property failure fields zero"),
            (r"Bei Erfolg gilt", "property success payload rule"),
        ]),
        "GetPhysicalDeviceQueueFamilyProperties": ("devices", [
            (r"\x60QUEUEFAMILYINFO\x60-Records mit je 12 Bytes", "12-byte queue-family records"),
            (r"reply\.length = 3 \* queue_family_count", "queue-family reply.length formula"),
            (r"\|\s*0\s*\|\s*CARD32\s*\|\s*\x60queue_flags\x60\s*\|", "queue flags at record offset 0"),
            (r"\|\s*4\s*\|\s*CARD32\s*\|\s*\x60queue_count\x60\s*\|", "queue count at record offset 4"),
            (r"\|\s*8\s*\|\s*CARD32\s*\|\s*\x60reserved = 0\x60\s*\|", "record reserved field"),
            (r"Payload-Länge muss durch 12 teilbar sein", "payload divisible by record size"),
        ]),
        "GetPhysicalDeviceMemoryProperties": ("memory", [
            (r"\x60CARD32 memory_type_count\x60", "memory-type count"),
            (r"\x60CARD32 memory_heap_count\x60", "memory-heap count"),
            (r"\x60MEMORYTYPEINFO\x60 ist 8 Bytes groß", "8-byte memory-type records"),
            (r"\x60MEMORYHEAPINFO\x60 ist 16 Bytes groß", "16-byte memory-heap records"),
            (r"reply\.length = 4 \+ 2 \* memory_type_count \+ 4 \* memory_heap_count", "memory-properties reply.length formula"),
            (r"\x60CARD32 reserved = 0\x60", "reserved count/record fields"),
            (r"\x60CARD32 property_flags\x60.*?\x60CARD32 heap_index\x60", "memory-type record fields"),
            (r"\x60CARD64 size\x60.*?\x60CARD32 heap_flags\x60.*?\x60CARD32 reserved = 0\x60", "memory-heap record fields"),
            (r"maximal 32 Memory Types und 16 Memory Heaps", "bounded record counts"),
        ]),
        "GetBufferMemoryRequirements": ("memory", [
            (r"\|\s*8\s*\|\s*CARD64\s*\|\s*\x60size\x60\s*\|", "size at reply offset 8"),
            (r"\|\s*16\s*\|\s*CARD64\s*\|\s*\x60alignment\x60\s*\|", "alignment at reply offset 16"),
            (r"\|\s*24\s*\|\s*CARD32\s*\|\s*\x60memory_type_bits\x60\s*\|", "memory type bits at reply offset 24"),
            (r"\|\s*28\s*\|\s*CARD32\s*\|\s*\x60reserved = 0\x60\s*\|", "reserved word at reply offset 28"),
            (r"Reply-Payload-Länge ist null", "fixed 32-byte reply"),
        ]),
        "WriteBuffer": ("memory", [
            (r"Gesamtlänge:\s*\n+\x60?28 \+ \(\(uint64\(data_length\) \+ 3\) & ~uint64\(3\)\)", "request payload length formula"),
            (r"Byte-Payload", "byte payload"),
            (r"Null-Padding bis zur nächsten Vierbytegrenze", "request zero padding"),
            (r"Reply von 32 Bytes", "empty standard reply on success"),
            (r"Bei einem fehlgeschlagenen \x60WriteBuffer\x60", "failure does not claim successful upload"),
        ]),
        "ReadBuffer": ("memory", [
            (r"Gesamtlänge: 28 Bytes", "fixed 28-byte request"),
            (r"Reply enthält nach dem 32-Byte-Header.*?ab Offset 32", "payload begins at reply offset 32"),
            (r"reply\.length = floor\(\(uint64\(data_length\) \+ 3\) / 4\)", "readback reply.length formula"),
            (r"Null-Padding auf vier Bytes", "readback zero padding"),
        ]),
        "GetSemaphoreCounterValue": ("sync", [
            (r"Offset 8: \x60CARD64 counter_value\x60", "counter value at offset 8"),
            (r"Offset 16–31: reserviert, null", "reserved reply bytes"),
            (r"Reply-Payload-Länge: null", "fixed 32-byte reply"),
        ]),
        "WaitSemaphores": ("sync", [
            (r"Gesamtlänge: \x6028 \+ 12 \* semaphore_count\x60 Bytes", "variable request length formula"),
            (r"Array aus 12-Byte-Entries", "12-byte wait entries"),
            (r"Jeder Entry enthält Semaphore-XID und \x60CARD64 wait_value\x60", "wait entry fields"),
            (r"Der Reply ist genau 32 Bytes lang", "fixed 32-byte reply"),
            (r"Offset 8 enthält einen \x60CARD32 status\x60", "wait status field"),
            (r"Offsets 12–31 sind null und \x60reply\.length = 0\x60", "reserved bytes and zero payload"),
            (r"\x60SUCCESS = 0\x60 oder \x60TIMEOUT = 1\x60", "wait reply status values"),
        ]),
        "GetFenceStatus": ("sync", [
            (r"Reply: 32 Bytes", "fixed 32-byte reply"),
            (r"Byte 0: standardmäßiges X11-Reply", "response_type byte"),
            (r"Byte 1: Fence-Status", "status byte"),
            (r"Offsets 2–3: standardmäßige X11-Reply-Sequenznummer", "sequence field"),
            (r"Offsets 4–7: standardmäßiges \x60reply\.length = 0\x60", "zero reply.length"),
            (r"Offsets 8–31: XAverius-reserviert, null", "reserved reply bytes"),
        ]),
        "WaitForFence": ("sync", [
            (r"Request: 24 Bytes", "fixed request length"),
            (r"Offset 8 enthält einen \x60CARD32 status\x60", "wait status field"),
            (r"Offsets 12–31 sind null und \x60reply\.length = 0\x60", "reserved bytes and zero payload"),
            (r"\x60SUCCESS = 0\x60", "reply status values"),
            (r"\x60TIMEOUT = 1\x60", "timeout status"),
            (r"\x60EXECUTION_FAILED = 2\x60", "execution failure status"),
            (r"\x60DEVICE_LOST = 3\x60", "device loss status"),
        ]),
    }

    for name in sorted(expected_names):
        source_key, patterns = contracts[name]
        section = chapter_section(sources[source_key], name)
        c.require(bool(section), f"{name}: missing normative chapter section")
        if not section:
            continue
        for pattern, label in patterns:
            c.require(re.search(pattern, section, re.I | re.S) is not None,
                      f"{name}: missing or changed reply contract: {label}")

    wire = sources["wire"]
    c.require(re.search(r"Replies verwenden den Standard-X11-Reply-Header von 32 Bytes", wire, re.I) is not None,
              "reply layout: standard 32-byte X11 reply header")
    c.require(re.search(r"\x60reply\.length\x60 gibt die Anzahl der Vierbyteeinheiten nach diesem Header an", wire, re.I) is not None,
              "reply layout: reply.length unit definition")




def check_reply_golden_vectors(c: Check) -> None:
    """Validate committed reply bytes against framing and normative reply formulas."""
    try:
        fixture = __import__("json").loads(read("tests/reply-vectors.json"))
    except (ValueError, KeyError) as exc:
        c.require(False, f"reply golden vectors: invalid JSON fixture: {exc}")
        return
    c.require(fixture.get("schema_version") == 1, "reply golden vectors: schema_version must be 1")
    vectors = fixture.get("vectors")
    c.require(isinstance(vectors, list) and bool(vectors), "reply golden vectors: vectors must be a non-empty list")
    if not isinstance(vectors, list):
        return

    seen_names: set[str] = set()
    coverage: dict[str, set[str]] = {}
    by_name: dict[str, dict] = {}
    for vector in vectors:
        if not isinstance(vector, dict):
            c.require(False, "reply golden vectors: each vector must be an object")
            continue
        name = vector.get("name")
        order = vector.get("byte_order")
        c.require(isinstance(name, str) and bool(name), "reply golden vectors: missing name")
        if not isinstance(name, str) or not name:
            continue
        c.require(name not in seen_names, f"reply golden vectors: duplicate name {name}")
        seen_names.add(name)
        by_name[name] = vector
        c.require(order in ("little", "big"), f"{name}: byte_order must be little or big")
        if order not in ("little", "big"):
            continue
        kind = vector.get("event")
        c.require(isinstance(kind, str) and bool(kind), f"{name}: missing reply kind")
        if isinstance(kind, str):
            coverage.setdefault(kind, set()).add(order)
        try:
            wire = bytes.fromhex(vector["wire_hex"])
            payload = bytes.fromhex(vector["payload_hex"])
        except (KeyError, TypeError, ValueError) as exc:
            c.require(False, f"{name}: invalid wire_hex/payload_hex: {exc}")
            continue
        c.require(len(wire) >= 32, f"{name}: reply shorter than standard 32-byte header")
        c.require(len(wire) % 4 == 0, f"{name}: reply size is not four-byte aligned")
        if len(wire) < 32:
            continue
        c.require(wire[0] == 1, f"{name}: response_type must be 1")
        c.require(wire[1] == vector.get("data_byte"), f"{name}: data byte mismatch")
        c.require(int.from_bytes(wire[2:4], order) == vector.get("sequence"),
                  f"{name}: sequence field mismatch")
        declared = int.from_bytes(wire[4:8], order)
        c.require(declared == vector.get("reply_length"), f"{name}: reply.length metadata mismatch")
        c.require(32 + declared * 4 == len(wire), f"{name}: reply.length disagrees with total size")
        c.require(wire[32:] == payload, f"{name}: payload_hex disagrees with wire bytes")
        c.require(len(wire) == vector.get("total_bytes"), f"{name}: total_bytes metadata mismatch")

        if kind in ("EnumeratePhysicalDevices-empty", "GetPhysicalDeviceQueueFamilyProperties-empty"):
            c.require(declared == 0 and len(payload) == 0, f"{name}: empty enumeration must have zero payload")
        elif kind == "EnumeratePhysicalDevices-one-record":
            c.require(len(payload) >= 32, f"{name}: PHYSICALDEVICEINFO shorter than 32-byte fixed prefix")
            if len(payload) >= 32:
                name_len = int.from_bytes(payload[28:30], order)
                record_len = 32 + ((name_len + 3) & ~3)
                c.require(len(payload) == record_len, f"{name}: PHYSICALDEVICEINFO record length mismatch")
                c.require(payload[30:32] == bytes(2), f"{name}: PHYSICALDEVICEINFO reserved field must be zero")
                c.require(payload[32 + name_len:record_len] == bytes(record_len - 32 - name_len),
                          f"{name}: PHYSICALDEVICEINFO name padding must be zero")
        elif kind == "EnumeratePhysicalDevices-two-records":
            pos = 0
            record_count = 0
            while pos < len(payload):
                c.require(len(payload) - pos >= 32, f"{name}: truncated PHYSICALDEVICEINFO fixed prefix")
                if len(payload) - pos < 32:
                    break
                name_len = int.from_bytes(payload[pos + 28:pos + 30], order)
                record_len = 32 + ((name_len + 3) & ~3)
                c.require(pos + record_len <= len(payload), f"{name}: PHYSICALDEVICEINFO record overruns payload")
                if pos + record_len > len(payload):
                    break
                c.require(payload[pos + 30:pos + 32] == bytes(2),
                          f"{name}: PHYSICALDEVICEINFO reserved field must be zero")
                c.require(payload[pos + 32 + name_len:pos + record_len] == bytes(record_len - 32 - name_len),
                          f"{name}: PHYSICALDEVICEINFO name padding must be zero")
                pos += record_len
                record_count += 1
            c.require(pos == len(payload) and record_count == 2,
                      f"{name}: expected exactly two complete PHYSICALDEVICEINFO records")
            c.require(declared == len(payload) // 4,
                      f"{name}: enumeration reply.length must count all record words")
        elif kind == "GetPhysicalDeviceQueueFamilyProperties-two-records":
            c.require(len(payload) % 12 == 0, f"{name}: queue-family payload must be a multiple of 12")
            c.require(declared == 3 * (len(payload) // 12), f"{name}: queue-family reply.length formula mismatch")
            for offset in range(0, len(payload), 12):
                c.require(payload[offset + 8:offset + 12] == bytes(4),
                          f"{name}: queue-family reserved field must be zero at payload offset {offset + 8}")
        elif isinstance(kind, str) and kind.startswith("ReadBuffer-") and kind.endswith("-bytes"):
            try:
                data_size = int(kind.split("-")[1])
                padded_size = (data_size + 3) & ~3
                c.require(len(payload) == padded_size and declared == padded_size // 4,
                          f"{name}: ReadBuffer payload size/word count mismatch")
                c.require(payload[data_size:] == bytes(padded_size - data_size),
                          f"{name}: ReadBuffer padding must be zero")
            except (ValueError, IndexError):
                c.require(False, f"{name}: malformed ReadBuffer vector kind")
        elif kind in ("GetFenceStatus", "WaitForFence", "GetSemaphoreCounterValue", "WaitSemaphores-success"):
            c.require(len(wire) == 32 and declared == 0, f"{name}: fixed reply must be exactly 32 bytes with length zero")
            if kind == "GetFenceStatus":
                c.require(wire[1] in (0, 1, 2, 3), f"{name}: invalid fence status")
            elif kind.startswith("WaitForFence"):
                status = int.from_bytes(wire[8:12], order)
                c.require(status in (0, 1, 2, 3, 4), f"{name}: invalid WaitForFence status")
                c.require(wire[12:32] == bytes(20), f"{name}: reserved bytes must be zero")
            elif kind == "WaitSemaphores-success":
                c.require(int.from_bytes(wire[8:12], order) == 0, f"{name}: status must be SUCCESS")
                c.require(wire[12:32] == bytes(20), f"{name}: reserved bytes must be zero")
        elif isinstance(kind, str) and kind.startswith("GetPhysicalDeviceProperty-success"):
            value_length = int.from_bytes(wire[16:20], order)
            expected_words = (value_length + 3) // 4
            c.require(len(wire) == 32 + expected_words * 4 and declared == expected_words,
                      f"{name}: successful property payload size/word count mismatch")
            c.require(int.from_bytes(wire[8:12], order) == 0, f"{name}: property status must be SUCCESS")
            c.require(wire[20:32] == bytes(12), f"{name}: property reserved bytes must be zero")
            c.require(payload[value_length:] == bytes(expected_words * 4 - value_length),
                      f"{name}: property payload padding must be zero")
            if kind == "GetPhysicalDeviceProperty-success":
                c.require(len(wire) == 36 and int.from_bytes(wire[12:16], order) == 1 and value_length == 4,
                          f"{name}: CARD32 property must have a four-byte value")
            elif kind.endswith("byte-array-1"):
                c.require(int.from_bytes(wire[12:16], order) == 5 and value_length == 1,
                          f"{name}: one-byte array property metadata mismatch")
            elif kind.endswith("byte-array-5"):
                c.require(int.from_bytes(wire[12:16], order) == 5 and value_length == 5,
                          f"{name}: five-byte array property metadata mismatch")
            elif kind.endswith("byte-array-16"):
                c.require(int.from_bytes(wire[12:16], order) == 5 and value_length == 16,
                          f"{name}: UUID array property metadata mismatch")
            elif kind.endswith("card32-array-3"):
                c.require(int.from_bytes(wire[12:16], order) == 6 and value_length == 12,
                          f"{name}: workgroup-size property metadata mismatch")
                c.require([int.from_bytes(payload[i:i+4], order) for i in (0, 4, 8)] == [64, 32, 16],
                          f"{name}: workgroup-size array values/order mismatch")
        elif kind in ("GetPhysicalDeviceProperty-not-supported", "GetPhysicalDeviceProperty-not-available"):
            expected_status = 1 if kind.endswith("not-supported") else 2
            c.require(len(wire) == 32 and declared == 0, f"{name}: failed property reply must have no payload")
            c.require(int.from_bytes(wire[8:12], order) == expected_status, f"{name}: property failure status mismatch")
            c.require(wire[12:32] == bytes(20), f"{name}: failed property fields/reserved bytes must be zero")
        elif kind == "GetPhysicalDeviceMemoryProperties-one-type-one-heap":
            c.require(len(payload) == 40 and declared == 10, f"{name}: one type and one heap require 40 payload bytes")
            if len(payload) == 40:
                types = int.from_bytes(payload[0:4], order)
                heaps = int.from_bytes(payload[4:8], order)
                c.require((types, heaps) == (1, 1), f"{name}: memory type/heap counts must be one")
                c.require(payload[12:16] == bytes(4), f"{name}: memory_properties_flags/reserved must be zero")
                c.require(payload[20:24] == bytes(4), f"{name}: memory type heap_index must be zero")
                c.require(payload[36:40] == bytes(4), f"{name}: memory heap reserved must be zero")
        elif kind == "GetPhysicalDeviceMemoryProperties-max-counts":
            c.require(len(payload) == 528 and declared == 132,
                      f"{name}: maximum memory counts require 528 payload bytes")
            if len(payload) == 528:
                type_count = int.from_bytes(payload[0:4], order)
                heap_count = int.from_bytes(payload[4:8], order)
                c.require((type_count, heap_count) == (32, 16), f"{name}: maximum memory counts mismatch")
                c.require(payload[8:16] == bytes(8), f"{name}: memory property flags/reserved must be zero")
                for i in range(type_count):
                    entry = payload[16+i*8:24+i*8]
                    c.require(int.from_bytes(entry[4:8], order) < heap_count,
                              f"{name}: memory type {i} has invalid heap index")
                heap_start = 16 + type_count * 8
                for i in range(heap_count):
                    entry = payload[heap_start+i*16:heap_start+(i+1)*16]
                    c.require(entry[12:16] == bytes(4), f"{name}: heap {i} reserved field must be zero")
        elif kind == "GetBufferMemoryRequirements":
            c.require(len(wire) == 32 and declared == 0, f"{name}: buffer requirements reply must be fixed 32 bytes")
            c.require(int.from_bytes(wire[8:16], order) == 0x1000, f"{name}: size field mismatch")
            c.require(int.from_bytes(wire[16:24], order) == 256, f"{name}: alignment field mismatch")
            c.require(int.from_bytes(wire[24:28], order) == 3, f"{name}: memory_type_bits field mismatch")
            c.require(wire[28:32] == bytes(4), f"{name}: buffer requirements reserved field must be zero")
        elif kind == "WriteBuffer-success":
            c.require(len(wire) == 32 and declared == 0 and wire[8:32] == bytes(24),
                      f"{name}: successful WriteBuffer reply must be an empty standard reply")
        elif kind == "WaitSemaphores-timeout":
            c.require(len(wire) == 32 and declared == 0, f"{name}: WaitSemaphores reply must be fixed 32 bytes")
            c.require(int.from_bytes(wire[8:12], order) == 1, f"{name}: WaitSemaphores status must be TIMEOUT")
            c.require(wire[12:32] == bytes(20), f"{name}: WaitSemaphores reserved bytes must be zero")

    for kind, orders in coverage.items():
        c.require(orders == {"little", "big"}, f"reply golden vectors: {kind} must cover both byte orders")
    required = {
        "GetFenceStatus", "WaitForFence", "GetSemaphoreCounterValue",
        "ReadBuffer-5-bytes", "EnumeratePhysicalDevices-empty",
        "EnumeratePhysicalDevices-one-record",
        "GetPhysicalDeviceQueueFamilyProperties-empty",
        "GetPhysicalDeviceQueueFamilyProperties-two-records",
        "GetPhysicalDeviceProperty-success", "GetPhysicalDeviceProperty-not-supported", "GetPhysicalDeviceProperty-not-available",
        "GetPhysicalDeviceMemoryProperties-one-type-one-heap", "GetPhysicalDeviceMemoryProperties-max-counts", "GetBufferMemoryRequirements",
        "WriteBuffer-success", "WaitSemaphores-timeout",
    }
    present = {v.get("event") for v in vectors if isinstance(v, dict)}
    for kind in sorted(required):
        c.require(kind in present, f"reply golden vectors: missing required sample {kind}")

    # Negative vectors must demonstrably violate the named ABI invariant.
    try:
        negative = __import__("json").loads(read("tests/reply-negative-vectors.json"))
        c.require(negative.get("schema_version") == 1, "negative reply vectors: schema_version must be 1")
        items = negative.get("vectors", [])
        c.require(len(items) >= 28, "negative reply vectors: expected at least 28 cases")
        for item in items:
            try:
                wire = bytes.fromhex(item["wire_hex"])
                order = item["byte_order"]
                kind = item["kind"]
                rule = item["violates"]
                declared = int.from_bytes(wire[4:8], order) if len(wire) >= 8 else 0
                invalid = False
                if rule == "standard-header": invalid = len(wire) < 32 or len(wire) % 4 != 0 or wire[0] != 1 or 32 + declared * 4 != len(wire)
                elif rule == "fence-status": invalid = kind == "GetFenceStatus" and wire[1] not in (0, 1, 2, 3)
                elif rule == "wait-status": invalid = kind == "WaitSemaphores-timeout" and int.from_bytes(wire[8:12], order) not in (0, 1)
                elif rule == "wait-status-match": invalid = kind in ("WaitSemaphores-timeout", "WaitSemaphores-success") and int.from_bytes(wire[8:12], order) != (1 if kind.endswith("timeout") else 0)
                elif rule == "wait-for-fence-status": invalid = kind == "WaitForFence" and int.from_bytes(wire[8:12], order) not in (0, 1, 2, 3, 4)
                elif rule == "property-success-status": invalid = kind == "GetPhysicalDeviceProperty-success" and int.from_bytes(wire[8:12], order) != 0
                elif rule == "property-failure-status": invalid = kind in ("GetPhysicalDeviceProperty-not-supported", "GetPhysicalDeviceProperty-not-available") and int.from_bytes(wire[8:12], order) != (1 if kind.endswith("not-supported") else 2)
                elif rule == "buffer-requirements-size-positive": invalid = kind == "GetBufferMemoryRequirements" and int.from_bytes(wire[8:16], order) == 0
                elif rule == "buffer-requirements-alignment-positive": invalid = kind == "GetBufferMemoryRequirements" and int.from_bytes(wire[16:24], order) == 0
                elif rule == "property-padding-zero":
                    value_length = int.from_bytes(wire[16:20], order)
                    invalid = kind == "GetPhysicalDeviceProperty-success" and len(wire) >= 32 + value_length and wire[32 + value_length:] != bytes(len(wire) - 32 - value_length)
                elif rule == "device-xid-nonzero":
                    invalid = kind == "EnumeratePhysicalDevices" and len(wire) >= 64 and int.from_bytes(wire[32:36], order) == 0
                elif rule == "device-type-range":
                    invalid = kind == "EnumeratePhysicalDevices" and len(wire) >= 64 and int.from_bytes(wire[36:40], order) not in range(5)
                elif rule == "device-name-utf8":
                    name_length = int.from_bytes(wire[60:62], order) if len(wire) >= 64 else 0
                    name_bytes = wire[64:64 + name_length]
                    try:
                        name_bytes.decode("utf-8", errors="strict")
                        invalid = False
                    except UnicodeDecodeError:
                        invalid = kind == "EnumeratePhysicalDevices" and len(wire) >= 64 + name_length
                elif rule == "device-name-no-nul":
                    name_length = int.from_bytes(wire[60:62], order) if len(wire) >= 64 else 0
                    invalid = kind == "EnumeratePhysicalDevices" and len(wire) >= 64 + name_length and bytes([0]) in wire[64:64 + name_length]
                elif rule == "device-record-reserved":
                    invalid = kind == "EnumeratePhysicalDevices" and len(wire) >= 64 and wire[62:64] != bytes(2)
                elif rule == "device-name-padding-zero":
                    name_length = int.from_bytes(wire[60:62], order) if len(wire) >= 64 else 0
                    padded = (name_length + 3) & ~3
                    invalid = kind == "EnumeratePhysicalDevices" and len(wire) >= 64 + padded and wire[64 + name_length:64 + padded] != bytes(padded - name_length)
                elif rule == "device-record-length":
                    invalid = kind == "EnumeratePhysicalDevices" and len(wire) >= 32
                    pos = 32
                    while invalid and pos < len(wire):
                        if len(wire) - pos < 32:
                            break
                        name_length = int.from_bytes(wire[pos + 28:pos + 30], order)
                        record_length = 32 + ((name_length + 3) & ~3)
                        if pos + record_length > len(wire):
                            break
                        pos += record_length
                    if invalid:
                        invalid = pos != len(wire)
                elif rule == "memory-type-count-range": invalid = kind == "GetPhysicalDeviceMemoryProperties" and len(wire) >= 40 and int.from_bytes(wire[32:36], order) > 32
                elif rule == "memory-heap-count-range": invalid = kind == "GetPhysicalDeviceMemoryProperties" and len(wire) >= 40 and int.from_bytes(wire[36:40], order) > 16
                elif rule == "queue-flags-reserved":
                    invalid = kind == "GetPhysicalDeviceQueueFamilyProperties-two-records" and len(wire) >= 36 and bool(int.from_bytes(wire[32:36], order) & ~0x1F)
                elif rule == "queue-record-length":
                    invalid = kind == "GetPhysicalDeviceQueueFamilyProperties-two-records" and len(wire) >= 32 and (len(wire) - 32) % 12 != 0
                elif rule == "read-buffer-payload-length":
                    try:
                        data_length = int(kind.split("-")[1])
                        padded = (data_length + 3) & ~3
                        invalid = kind.startswith("ReadBuffer-") and (len(wire) != 32 + padded or declared != padded // 4)
                    except (ValueError, IndexError):
                        invalid = False
                elif rule == "read-buffer-padding-zero":
                    try:
                        data_length = int(kind.split("-")[1])
                        padded = (data_length + 3) & ~3
                        invalid = kind.startswith("ReadBuffer-") and len(wire) == 32 + padded and wire[32 + data_length:] != bytes(padded - data_length)
                    except (ValueError, IndexError):
                        invalid = False
                elif rule == "memory-payload-length":
                    type_count = int.from_bytes(wire[32:36], order) if len(wire) >= 36 else 0
                    heap_count = int.from_bytes(wire[36:40], order) if len(wire) >= 40 else 0
                    expected = 16 + type_count * 8 + heap_count * 16
                    invalid = kind == "GetPhysicalDeviceMemoryProperties" and (len(wire) < 48 or len(wire) - 32 != expected)
                elif rule == "memory-properties-flags-zero":
                    invalid = kind == "GetPhysicalDeviceMemoryProperties" and len(wire) >= 44 and wire[40:44] != bytes(4)
                elif rule == "memory-reserved-zero":
                    invalid = kind == "GetPhysicalDeviceMemoryProperties" and len(wire) >= 48 and wire[44:48] != bytes(4)
                elif rule == "memory-type-flags-range":
                    invalid = kind == "GetPhysicalDeviceMemoryProperties" and len(wire) >= 56 and bool(int.from_bytes(wire[48:52], order) & ~0x3F)
                elif rule == "memory-heap-flags-range":
                    type_count = int.from_bytes(wire[32:36], order) if len(wire) >= 36 else 0
                    heap_offset = 48 + type_count * 8
                    invalid = kind == "GetPhysicalDeviceMemoryProperties" and len(wire) >= heap_offset + 12 and bool(int.from_bytes(wire[heap_offset + 8:heap_offset + 12], order) & ~0x1)
                elif rule == "memory-type-heap-index-range":
                    type_count = int.from_bytes(wire[32:36], order) if len(wire) >= 36 else 0
                    heap_count = int.from_bytes(wire[36:40], order) if len(wire) >= 40 else 0
                    invalid = kind == "GetPhysicalDeviceMemoryProperties" and type_count > 0 and len(wire) >= 56 and int.from_bytes(wire[52:56], order) >= heap_count
                elif rule == "property-type-length":
                    property_type = int.from_bytes(wire[12:16], order) if len(wire) >= 16 else 0
                    value_length = int.from_bytes(wire[16:20], order) if len(wire) >= 20 else 0
                    widths = {1: 4, 2: 8, 3: 4}
                    invalid = kind == "GetPhysicalDeviceProperty-success" and (
                        property_type not in range(1, 8)
                        or (property_type in widths and value_length != widths[property_type])
                        or (property_type == 6 and value_length % 4 != 0)
                        or (property_type == 7 and value_length % 8 != 0)
                    )
                elif rule == "property-failure-zero": invalid = kind in ("GetPhysicalDeviceProperty-not-supported", "GetPhysicalDeviceProperty-not-available") and (wire[12:20] != bytes(8) or wire[32:] or declared != 0)
                elif rule == "queue-record-reserved": invalid = kind == "GetPhysicalDeviceQueueFamilyProperties-two-records" and any(wire[o+8:o+12] != bytes(4) for o in range(32, len(wire), 12))
                elif rule == "memory-heap-reserved": invalid = kind == "GetPhysicalDeviceMemoryProperties-one-type-one-heap" and wire[68:72] != bytes(4)
                elif rule == "reserved-zero": invalid = ((kind == "GetPhysicalDeviceProperty-success" and wire[20:32] != bytes(12)) or (kind == "GetBufferMemoryRequirements" and wire[28:32] != bytes(4)) or (kind == "GetSemaphoreCounterValue" and wire[16:32] != bytes(16)) or (kind == "GetFenceStatus" and wire[8:32] != bytes(24)) or (kind == "WaitForFence" and wire[12:32] != bytes(20)) or (kind in ("WaitSemaphores-timeout", "WaitSemaphores-success") and wire[12:32] != bytes(20)))
                c.require(invalid, f"{item.get('name')}: negative vector does not violate {rule}")
            except (KeyError, TypeError, ValueError, IndexError) as exc:
                c.require(False, f"negative reply vector malformed: {exc}")
    except (ValueError, KeyError) as exc:
        c.require(False, f"negative reply vectors: invalid JSON fixture: {exc}")

def check_reply_formula_vectors(c: Check) -> None:
    """Exercise boundary values for every documented variable reply/request formula."""
    pad4 = lambda n: (n + 3) & ~3
    words4 = lambda n: (n + 3) // 4
    record_size = lambda name_length: 32 + pad4(name_length)
    memory_reply_words = lambda type_count, heap_count: 4 + 2 * type_count + 4 * heap_count

    for n, expected in [(0, 0), (1, 4), (3, 4), (4, 4), (5, 8)]:
        c.require(pad4(n) == expected, f"pad4({n}) must be {expected}")
        c.require(words4(n) == expected // 4, f"ceil({n}/4) must be {expected // 4}")
    for n, expected in [(0, 32), (1, 36), (4, 36), (5, 40)]:
        c.require(record_size(n) == expected,
                  f"PHYSICALDEVICEINFO name length {n} must yield {expected}-byte record")
    for count, expected in [(0, 0), (1, 3), (4, 12)]:
        c.require(3 * count == expected,
                  f"QUEUEFAMILYINFO count {count} must yield reply.length {expected}")
    for types, heaps, expected in [(0, 0, 4), (1, 1, 10), (32, 16, 132)]:
        c.require(memory_reply_words(types, heaps) == expected,
                  f"memory reply counts ({types}, {heaps}) must yield reply.length {expected}")
    for n, expected in [(1, 1), (3, 1), (4, 1), (5, 2)]:
        c.require(words4(n) == expected, f"variable byte payload {n} must use {expected} reply word(s)")
        c.require(28 + pad4(n) == 28 + expected * 4,
                  f"WriteBuffer {n}-byte payload must yield {28 + expected * 4}-byte request")
    for count, expected in [(1, 40), (2, 52), (16, 220)]:
        c.require(28 + 12 * count == expected,
                  f"WaitSemaphores count {count} must yield {expected}-byte request")



def check_xge_abi(c: Check) -> None:
    """Check XGE framing, event-specific ABI, registries, and SelectEvents."""
    events = read("spec/events.md")
    wire = read("spec/wire-protocol.md")
    registry = read("registries/event-types.md")
    requests = read("registries/request-subopcodes.md")
    devices = read("spec/devices.md")
    conformance = read("spec/conformance.md")

    header = events.split("## " + chr(96) + "ASYNC_ERROR" + chr(96), 1)[0]
    header_fields = [
        (0, "CARD8", r"response_type\s*=\s*GenericEvent\s*\(35\)"),
        (1, "CARD8", r"extension.*dynamisch zugewiesener XAverius-Major-Opcode"),
        (2, "CARD16", r"X11-Event-Sequenznummer"),
        (4, "CARD32", r"XGE.*length"),
        (8, "CARD16", r"evtype.*Event-Type-ID"),
    ]
    for offset, typ, pattern in header_fields:
        c.require(re.search(rf"^\|\s*{offset}\s*\|\s*{typ}\s*\|[^\n]*{pattern}", header, re.M | re.I) is not None,
                  f"XGE header: missing or changed {typ} field at offset {offset}")
    c.require(re.search(r"^\|\s*10–31\s*\|\s*—\s*\|[^|]*null", header, re.M | re.I) is not None,
              "XGE header: reserved bytes 10–31 must be zero")
    c.require(re.search(r"Gesamtlänge ist exakt.*32.*4.*length", header, re.I) is not None,
              "XGE header: exact total-size formula missing")
    c.require(re.search(r"Verbindung-byte-order gilt auch für Header und Payload", header, re.I) is not None,
              "XGE header: connection byte order must apply to header and payload")
    c.require(re.search(r"GenericEvent\s*=\s*35", wire) is not None and
              re.search(r"kein eigenes serverseitig zugewiesenes XGE-Event-Base", wire, re.I) is not None,
              "wire protocol: GenericEvent code and no separate XAverius event base must be explicit")

    expected = {
        "ASYNC_ERROR": (0, 60, 7, [(32, "XID"), (36, "CARD32"), (40, "CARD32"), (44, "CARD64"), (52, "XID"), (56, "CARD32")]),
        "DEVICE_LOST": (1, 48, 4, [(32, "XID"), (36, "CARD32"), (40, "CARD64")]),
        "DEVICE_STATUS_CHANGED": (2, 48, 4, [(32, "XID"), (36, "CARD32"), (40, "CARD32"), (44, "CARD32")]),
        "DEVICE_MEMORY_PRESSURE": (3, 48, 4, [(32, "XID"), (36, "CARD32"), (40, "CARD32"), (44, "CARD32")]),
        "DEVICE_IDLE": (4, 48, 4, [(32, "XID"), (36, "CARD32"), (40, "CARD64")]),
        "SUBMISSION_COMPLETE": (5, 56, 6, [(32, "XID"), (36, "CARD32"), (40, "CARD32"), (44, "CARD32"), (48, "CARD64")]),
        "SUBMISSION_FAILED": (6, 56, 6, [(32, "XID"), (36, "CARD32"), (40, "CARD32"), (44, "CARD32"), (48, "CARD64")]),
    }
    type_section_parts = registry.split("## Event type IDs", 1)
    type_section = type_section_parts[1].split("\n## ", 1)[0] if len(type_section_parts) == 2 else ""
    type_rows = [(int(v), n) for v, n in re.findall(r"^\|\s*(\d+)\s*\|\s*" + chr(96) + r"([A-Z_]+)" + chr(96) + r"\s*\|", type_section, re.M)]
    c.require(len(type_rows) == 7, f"XGE registry: expected 7 event IDs, found {len(type_rows)}")
    c.require(len({v for v, _ in type_rows}) == len(type_rows), "XGE registry: duplicate event type IDs")
    c.require(len({n for _, n in type_rows}) == len(type_rows), "XGE registry: duplicate event names")
    c.require(dict((n, v) for v, n in type_rows) == {n: spec[0] for n, spec in expected.items()},
              "XGE registry: event IDs differ from the seven ABI assignments")
    c.require("Event type IDs are stable and MUST NOT be renumbered" in registry,
              "XGE registry: stable event IDs must be documented")
    request_rows = parse_request_registry(requests)
    c.require(request_rows.get(40, (None, None))[0] == "SelectEvents",
              "XGE ABI: SelectEvents must remain assigned subopcode 40")

    doc_sections = dict(sections(events))
    field_sizes = {"XID": 4, "CARD32": 4, "CARD64": 8}
    for name, (event_id, total, xge_length, fields) in expected.items():
        body = doc_sections.get(name, "")
        c.require(bool(body), f"{name}: missing event ABI section")
        if not body:
            continue
        declaration = re.search(r"Gesamtlänge:\s*(\d+)\s*Bytes;\s*XGE.*length\s*=\s*(\d+)", body)
        c.require(bool(declaration), f"{name}: missing total/XGE length declaration")
        if declaration:
            actual_total, actual_length = map(int, declaration.groups())
            c.require((actual_total, actual_length) == (total, xge_length),
                      f"{name}: expected total/length {(total, xge_length)}, got {(actual_total, actual_length)}")
            c.require(actual_total == 32 + 4 * actual_length, f"{name}: total does not match XGE length")
        parsed = event_field_records(body)
        actual_layout = [(off, typ) for off, _size, typ, _field in parsed]
        c.require(actual_layout == fields,
                  f"{name}: payload field offsets/types changed: {actual_layout!r}")
        c.require(all(off + field_sizes[typ] <= total for off, typ in fields),
                  f"{name}: payload field extends past event size")
        c.require(all(off % min(field_sizes[typ], 4) == 0 for off, typ in fields),
                  f"{name}: payload field is misaligned")

    local_expected = {
        "ASYNC_ERROR.origin": [(0, "ORIGIN_UNSPECIFIED"), (1, "ORIGIN_QUEUE_SUBMIT"),
                               (2, "ORIGIN_WRITE_BUFFER"), (3, "ORIGIN_READ_BUFFER"),
                               (4, "ORIGIN_SEMAPHORE"), (5, "ORIGIN_FENCE"), (6, "ORIGIN_DEVICE")],
        "DEVICE_STATUS_CHANGED.new_status": [(0, "AVAILABLE"), (1, "UNAVAILABLE"), (2, "REMOVED")],
        "DEVICE_MEMORY_PRESSURE.pressure_level": [(0, "NORMAL"), (1, "LOW"), (2, "MEDIUM"), (3, "HIGH")],
        "DEVICE_IDLE.idle_reason": [(0, "IDLE_REASON_UNSPECIFIED"), (1, "NO_PENDING_WORK"), (2, "WORK_COMPLETED")],
        "SUBMISSION_FAILED.failure_class": [(0, "EXECUTION_FAILED"), (1, "DEVICE_LOST")],
    }
    for section_name, wanted in local_expected.items():
        heading = "## " + chr(96) + section_name + chr(96)
        section_match = re.search(r"^" + re.escape(heading) + r"\s*$([\s\S]*?)(?=^## |\Z)", registry, re.M)
        c.require(bool(section_match), f"event registry: missing local value registry {section_name}")
        if section_match:
            found = [(int(v), s) for v, s in re.findall(
                r"^\|\s*(\d+)\s*\|\s*" + chr(96) + r"([A-Z_]+)" + chr(96) + r"\s*\|",
                section_match.group(1), re.M)]
            c.require(found == wanted, f"event registry: {section_name} values changed: {found!r}")
    c.require("reason-codes.md" in registry and "DEVICE_LOST.reason_code" in registry and
              "DEVICE_STATUS_CHANGED.reason_code" in registry,
              "event registry: device reason_code fields must use shared reason-code registry")

    # Keep the event-side error-code range tied to the central v0.1 registry.
    error_registry = read("registries/errors.md")
    c.require("in the range 0–8 for v0.1" in registry,
              "ASYNC_ERROR.error_code: event registry range must remain 0 through 8")
    c.require("first_error + offset" in error_registry and
              "not the absolute X11 error code" in registry,
              "ASYNC_ERROR.error_code: registry offsets must not be confused with absolute X11 codes")
    c.require(all(f"| {offset} |" in error_registry for offset in range(9)) and
              "| 9 |" not in error_registry,
              "ASYNC_ERROR.error_code: v0.1 range must match the central error registry offsets 0 through 8")

    request_registry = parse_request_registry(requests)
    c.require(request_registry.get(40) == ("SelectEvents", "Void"),
              "request registry: SelectEvents must remain Void subopcode 40")
    c.require(sum(1 for name, _kind in request_registry.values() if name == "SelectEvents") == 1,
              "request registry: SelectEvents must be registered exactly once")

    select_marker = "## Event-Auswahl: " + chr(96) + "SelectEvents" + chr(96)
    select_start = events.find(select_marker)
    c.require(select_start >= 0, "events.md: missing SelectEvents ABI section")
    select_body = events[select_start + len(select_marker):] if select_start >= 0 else ""
    c.require(re.search(r"fest(?:e|er) Gesamtlänge von 32 Bytes", select_body, re.I) is not None,
              "SelectEvents: request must be exactly 32 bytes")
    c.require(re.search(r"Common-Header-Feld `flags` bei Offset 5 muss 0 sein", select_body, re.I) is not None,
              "SelectEvents: common request flags at offset 5 must be zero")
    c.require(re.search(r"Common-Header-Feld bei Offset 6 muss ebenfalls 0 sein", select_body, re.I) is not None,
              "SelectEvents: common request reserved field at offset 6 must be zero")
    expected_select = [
        (8, "CARD32", "scope"), (12, "XID", "device_xid"),
        (16, "CARD32", "queue_family_index"), (20, "CARD32", "queue_index"),
        (24, "CARD32", "event_mask"), (28, "CARD32", "reserved = 0"),
    ]
    actual_select = [(int(off), typ, field.strip().replace(chr(96), "")) for off, typ, field in re.findall(
        r"^\|\s*(\d+)\s*\|\s*([A-Z0-9]+)\s*\|\s*([^|]+?)\s*\|", select_body, re.M)]
    c.require(actual_select == expected_select, f"SelectEvents: fixed request layout changed: {actual_select!r}")
    for value in ("CONNECTION = 0", "DEVICE = 1", "QUEUE = 2"):
        c.require(value in select_body, f"SelectEvents: missing scope value {value}")
    expected_masks = [
        (r"CONNECTION" + chr(96) + r"\s*\|\s*0\s*\|\s*" + chr(96) + r"DEVICE_STATUS_CHANGED", "CONNECTION bit 0"),
        (r"DEVICE" + chr(96) + r"\s*\|\s*0\s*\|\s*" + chr(96) + r"DEVICE_MEMORY_PRESSURE", "DEVICE bit 0"),
        (r"DEVICE" + chr(96) + r"\s*\|\s*1\s*\|\s*" + chr(96) + r"DEVICE_IDLE", "DEVICE bit 1"),
        (r"QUEUE" + chr(96) + r"\s*\|\s*0\s*\|\s*" + chr(96) + r"SUBMISSION_COMPLETE", "QUEUE bit 0"),
        (r"QUEUE" + chr(96) + r"\s*\|\s*1\s*\|\s*" + chr(96) + r"SUBMISSION_FAILED", "QUEUE bit 1"),
    ]
    for pattern, label in expected_masks:
        c.require(re.search(pattern, select_body) is not None, f"SelectEvents: missing {label}")
    for pattern, label in [
        (r"atomar die bisherige Maske", "atomic mask replacement"),
        (r"Bei jedem Fehler bleibt die vorherige Auswahl unverändert", "failed request preserves prior mask"),
        (r"ASYNC_ERROR.*DEVICE_LOST.*nicht maskierbar", "unmaskable events"),
        (r"erfolgreich\s+" + chr(96) + r"?GEQueryVersion" + chr(96) + r"?", "XGE version negotiation prerequisite"),
        (r"ohne ausgehandelte XGE-Unterst(?:ü|ue)tzung.*BadMatch", "pre-negotiation rejection"),
    ]:
        c.require(re.search(pattern, select_body + "\n" + events, re.I | re.S) is not None,
                  f"SelectEvents/XGE: missing {label}")
    c.require(re.search(r"CreateDevice.*CreateDefaultDevice.*BadMatch", devices, re.S) is not None,
              "device creation: XGE negotiation prerequisite and BadMatch must be explicit")
    c.require(re.search(r"SelectEvents.*XGE.*framed|XGE.*SelectEvents", conformance, re.I | re.S) is not None,
              "conformance checklist: must cover SelectEvents/XGE ABI")

    # Semantic negative cases that cannot be inferred from field offsets alone.
    c.require("`origin = ORIGIN_QUEUE_SUBMIT` erfordert einen nicht-null Token" in conformance and
              "`ASYNC_ERROR`" in events and
              re.search(r"Bei `origin = ORIGIN_QUEUE_SUBMIT` MUSS `submission_token` daher ungleich null sein", events) is not None and
              re.search(r"ein nicht-null Token darf niemals eine abgewiesene `QueueSubmit`-Anforderung bezeichnen", events) is not None,
              "XGE ASYNC_ERROR: origin/token relationship and rejected-submit exclusion must be normative and tested")
    c.require("unbekannte `origin`-Werte" in conformance and
              "`reserved = 0`" in doc_sections.get("ASYNC_ERROR", "") and
              re.search(r"reserved = 0", doc_sections.get("ASYNC_ERROR", "")) is not None,
              "XGE ASYNC_ERROR: invalid origin and reserved-field negative cases must be covered")
    c.require("muss `resource_xid = 0` sein" in conformance and
              "muss `resource_xid = 0` gesetzt werden" in read("spec/events.md").lower() and
              "resource_xid = 0` serialisiert" in read("spec/resource-lifetime.md").lower() and
              "wiederverwendete ressourcen-xid nicht als `resource_xid` ausgegeben werden" in read("spec/resource-lifetime.md").lower(),
              "XGE ASYNC_ERROR: destroyed/reused resource XIDs must be scrubbed instead of retargeted")
    c.require("unbekannte Maskenbits" in conformance and
              "falschen Nullwerten" in conformance and
              "Jeder solche Fehler lässt die bisherige Maske unverändert" in conformance and
              "Unbekannte Scope-Werte" in select_body and
              "Bei jedem Fehler bleibt die vorherige Auswahl unverändert" in select_body,
              "SelectEvents: malformed scope/mask/unused fields must reject atomically")
    c.require("nicht angeforderter Queue-Kombination" in conformance and
              "fremder Ownership" in conformance and
              "Eine nicht existierende Queue innerhalb eines gültigen Devices ergibt `BadValue`" in select_body,
              "SelectEvents: queue lookup and ownership failures must be distinguished")
    c.require("nicht maskierbare `DEVICE_LOST`- und `ASYNC_ERROR`-Events" in conformance and
              "resource_xid" in conformance and
              "Nach erfolgreicher Verarbeitung von `DestroyDevice` darf der Server keine neuen XAverius-Events" in read("spec/resource-lifetime.md"),
              "XGE event delivery: DestroyDevice suppression must cover all event XID fields")
    c.require("gemeinsamer serialisierter Linearisierungspunkt" in conformance and
              "gemeinsamen serialisierten Serverzustand" in events and
              "Ein späterer Backend-Callback darf diese Entscheidung nicht nachträglich ändern" in events,
              "XGE event delivery: SelectEvents/DestroyDevice/completion race must be serialized")
    c.require("höchstens eines von `SUBMISSION_COMPLETE` und `SUBMISSION_FAILED`" in conformance and
              "Pro angenommener Submission darf niemals sowohl `SUBMISSION_COMPLETE` als auch `SUBMISSION_FAILED`" in events,
              "XGE submission events: exactly one terminal event per accepted submission")

    # Exercise the XGE length and reserved-header rules in both byte orders.
    import struct
    for order_name, endian in (("little", "<"), ("big", ">")):
        for name, (event_id, total, xge_length, _fields) in expected.items():
            frame = bytearray(total)
            frame[0], frame[1] = 35, 0xA7  # fixture-only dynamic major opcode
            struct.pack_into(endian + "H", frame, 2, 0x1234)
            struct.pack_into(endian + "I", frame, 4, xge_length)
            struct.pack_into(endian + "H", frame, 8, event_id)
            def valid_xge(candidate: bytes) -> bool:
                return (len(candidate) >= 32 and len(candidate) % 4 == 0 and
                        candidate[0] == 35 and
                        len(candidate) == 32 + 4 * struct.unpack_from(endian + "I", candidate, 4)[0] and
                        candidate[10:32] == bytes(22))
            c.require(valid_xge(bytes(frame)), f"XGE frame ({name}/{order_name}): valid frame rejected")
            bad_length = bytearray(frame)
            struct.pack_into(endian + "I", bad_length, 4, xge_length + 1)
            c.require(not valid_xge(bytes(bad_length)), f"XGE negative ({name}/{order_name}): bad length accepted")
            bad_reserved = bytearray(frame)
            bad_reserved[31] = 1
            c.require(not valid_xge(bytes(bad_reserved)), f"XGE negative ({name}/{order_name}): nonzero reserved byte accepted")
            bad_response = bytearray(frame)
            bad_response[0] = 2
            c.require(not valid_xge(bytes(bad_response)), f"XGE negative ({name}/{order_name}): wrong response type accepted")



def check_presentation_profile(c: Check) -> None:
    """Check future presentation-profile wire layouts without expanding v0.1 registries."""
    presentation = read("spec/presentation.md")
    events = read("spec/events.md")
    event_registry = read("registries/presentation-events.md")
    command_recording = read("spec/command-recording.md")
    formats = read("registries/presentation-formats.md")
    request_registry = read("registries/request-subopcodes.md")
    command_registry = read("registries/command-entries.md")

    # Presentation event IDs live in a separate, profile-gated registry.
    event_rows = [
        (int(value), name)
        for value, name in re.findall(
            r"^\|\s*(\d+)\s*\|\s*`([A-Z_]+)`\s*\|\s*$",
            event_registry, re.M,
        )
    ]
    c.require(event_rows == [(7, "IMAGE_RELEASED"), (8, "PRESENTATION_COMPLETE")],
              "presentation event registry must assign IDs 7 and 8 without changing the compute baseline")
    status_rows = [
        (int(value), symbol)
        for value, symbol in re.findall(
            r"^\|\s*(\d+)\s*\|\s*([A-Z_]+)\s*\|\s*$",
            event_registry.split("## Presentation event status values", 1)[-1], re.M,
        )
    ]
    c.require(status_rows == [
        (0, "SUCCESS"), (1, "OUT_OF_DATE"), (2, "SURFACE_LOST"),
        (3, "DEVICE_LOST"), (4, "PRESENTATION_FAILED"),
    ], "presentation event status registry must remain contiguous and stable")
    c.require(re.search(r"\|\s*`QUEUE`\s*\|\s*2\s*\|\s*`IMAGE_RELEASED`\s*\|", events) is not None and
              re.search(r"\|\s*`QUEUE`\s*\|\s*3\s*\|\s*`PRESENTATION_COMPLETE`\s*\|", events) is not None,
              "presentation events: queue mask bits 2 and 3 must map to the corresponding events")
    c.require("Compute-only Server muss sie als unbekannte Maskenbits mit `BadValue` zurückweisen" in events,
              "presentation events: compute-only profile must reject presentation queue mask bits")
    event_docs = dict(sections(events))
    presentation_spec = read("spec/presentation.md")
    lifetime = read("spec/resource-lifetime.md")
    c.require("It is emitted exactly once when the image becomes reusable" in event_docs.get("IMAGE_RELEASED", "") or
              "Es wird genau einmal ausgegeben, wenn das Image nach dem terminalen Ausgang wiederverwendbar ist." in event_docs.get("IMAGE_RELEASED", ""),
              "IMAGE_RELEASED: event cardinality must depend on image becoming reusable")
    c.require("terminalen Ausgang jeder akzeptierten Präsentationsoperation" in event_docs.get("PRESENTATION_COMPLETE", "") and
              "Nach `DestroyDevice` dürfen keine neuen Events" in event_docs.get("PRESENTATION_COMPLETE", ""),
              "PRESENTATION_COMPLETE: terminal outcome and DestroyDevice suppression must be explicit")
    c.require("Queue-Maske wird zu dem Zeitpunkt ausgewertet" in event_docs.get("IMAGE_RELEASED", "") and
              "Queue-Maske wird beim Serialisieren des terminalen Präsentationsergebnisses ausgewertet" in event_docs.get("PRESENTATION_COMPLETE", ""),
              "presentation events: queue mask must be sampled independently at each event milestone")
    c.require("Accepted presentation failures are reported through `PRESENTATION_COMPLETE`" in presentation_spec and
              "invalidates that image and the Swapchain instead" in presentation_spec,
              "presentation: accepted failure must terminate and either release or invalidate the image")
    c.require("interne Terminalzustände und sichere Backend-Bereinigung" in lifetime,
              "presentation: device teardown must preserve internal terminal cleanup when events are suppressed")
    for name in ("IMAGE_RELEASED", "PRESENTATION_COMPLETE"):
        c.require(name in event_docs, f"presentation events: missing {name} layout")
        body = event_docs.get(name, "")
        match = re.search(r"Gesamtlänge:\s*(\d+)\s*Bytes;\s*XGE `length\s*=\s*(\d+)`", body)
        c.require(match is not None, f"{name}: missing total/XGE length declaration")
        if match:
            total, length = map(int, match.groups())
            c.require((total, length) == (64, 8), f"{name}: expected 64-byte event and XGE length 8")
            c.require(total == 32 + 4 * length, f"{name}: total length must equal 32 + 4 * XGE length")
        records = event_field_records(body)
        expected_layout = [
            (32, "XID"), (36, "CARD32"), (40, "CARD32"),
            (44, "XID"), (48, "CARD32"), (52, "CARD32"), (56, "CARD64"),
        ]
        c.require([(offset, typ) for offset, _size, typ, _field in records] == expected_layout,
                  f"{name}: event payload offsets/types differ from the presentation ABI")
        occupied: set[int] = set()
        for offset, size, typ, field in records:
            c.require(offset >= 32 and offset % min(size, 4) == 0,
                      f"{name}.{field}: invalid payload offset/alignment")
            for byte in range(offset, offset + size):
                c.require(byte not in occupied, f"{name}.{field}: overlapping event fields")
                occupied.add(byte)
            c.require(offset + size <= 64, f"{name}.{field}: field exceeds 64-byte event")
        c.require(occupied == set(range(32, 64)),
                  f"{name}: event payload must cover bytes 32 through 63 exactly")

    # Request layouts are specified but not assigned subopcodes yet.
    expected_headings = (
        "### CreateSurface — Void, 16 bytes",
        "### DestroySurface — Void, 12 bytes",
        "### GetSurfaceCapabilities — Reply, 16 bytes",
        "### CreateSwapchain — Reply, 48 bytes",
        "### DestroySwapchain — Void, 12 bytes",
        "### AcquireNextImage — Reply, 32 bytes",
        "### QueuePresent — Reply, variable length",
    )
    for heading in expected_headings:
        c.require(heading in presentation,
                  f"presentation requests: missing or changed wire-layout heading {heading}")
    request_offsets = {
        "CreateSurface": [8, 12],
        "DestroySurface": [8],
        "GetSurfaceCapabilities": [8, 12],
        "CreateSwapchain": list(range(8, 48, 4)),
        "DestroySwapchain": [8],
        "AcquireNextImage": [8, 12, 16, 24, 28],
        "QueuePresent": [8, 12, 16, 20, 24, 28, 32, 40],
    }
    def presentation_request_section(request_name: str) -> str:
        marker = f"### {request_name} —"
        if marker not in presentation:
            return ""
        return presentation.split(marker, 1)[1].split("\n### ", 1)[0]

    for request_name, expected_offsets in request_offsets.items():
        body = presentation_request_section(request_name)
        actual_offsets = [int(value) for value in re.findall(
            r"^- Offset (\d+):", body, re.M
        )]
        if request_name == "QueuePresent":
            actual_offsets = [int(value) for value in re.findall(
                r"^- Offset (\d+):", body.split("Total request size", 1)[0], re.M
            )]
        c.require(actual_offsets == expected_offsets,
                  f"{request_name}: request-field offsets missing, duplicated, or out of order")
    caps = presentation_request_section("GetSurfaceCapabilities")
    capability_offsets = [int(value) for value in re.findall(
        r"^\|\s*(\d+)\s*\|\s*CARD32\s*\|", caps, re.M
    )]
    c.require(capability_offsets == list(range(8, 64, 4)),
              "GetSurfaceCapabilities: fixed reply fields must occupy offsets 8 through 60")
    c.require("40 + 4 * wait_semaphore_count" in presentation,
              "QueuePresent: variable request length formula missing")
    c.require("same per-Semaphore pending-wait accounting as `QueueSubmit` waits" in presentation and
              "marks that binary semaphore `UNTRUSTED`" in presentation,
              "QueuePresent: accepted wait reservations and uncertain-consumption handling must be explicit")
    c.require("`QueuePresent` verwendet dieselbe globale Zustandsmaschine" in read("spec/synchronization.md") and
              "bei unklarem Payload-Ergebnis wird die Semaphore `UNTRUSTED`" in read("spec/synchronization.md"),
              "synchronization: presentation waits must follow binary semaphore state rules")
    c.require("already marked `UNTRUSTED` is rejected with `DEPENDENCY_FAILED`" in read("spec/errors.md"),
              "QueuePresent: untrusted binary wait must fail with DEPENDENCY_FAILED")
    c.require("8 + 2 * format_pair_count + present_mode_count + 2 * queue_family_count" in presentation,
              "GetSurfaceCapabilities: reply.length formula missing")
    c.require("CreateSwapchain" in presentation and "actual_image_count" in presentation,
              "CreateSwapchain: exact image-count reply contract missing")
    for contract in (
        "total reply size is 40 bytes and `reply.length = 2`",
        "total reply size is 44 bytes and `reply.length = 3`",
        "total reply size is 36 bytes and `reply.length = 1`",
    ):
        c.require(contract in presentation,
                  f"presentation reply ABI: missing fixed reply size/length contract: {contract}")
    command_copy_id_assigned = "The presentation-only command-entry ID is 5." in presentation
    if command_copy_id_assigned:
        c.require("The command-entry numeric ID is not allocated yet" not in presentation,
                  "presentation command entry: assigned ID must not still be described as unallocated")
    else:
        c.require("The command-entry numeric ID is not allocated yet" in presentation,
                  "presentation command entry must remain explicitly unassigned until checked")
    presentation_requests = {
        "CreateSurface", "DestroySurface", "GetSurfaceCapabilities", "CreateSwapchain",
        "DestroySwapchain", "AcquireNextImage", "QueuePresent",
    }
    request_rows = parse_request_registry(request_registry)
    assigned_presentation_requests = {
        name: opcode for opcode, (name, _kind) in request_rows.items()
        if name in presentation_requests
    }
    expected_presentation_assignments = {
        "CreateSurface": 41, "DestroySurface": 42, "GetSurfaceCapabilities": 43,
        "CreateSwapchain": 44, "DestroySwapchain": 45, "AcquireNextImage": 46,
        "QueuePresent": 47,
    }
    if assigned_presentation_requests:
        c.require(set(request_rows) == set(range(1, 48)),
                  "presentation audit: assigned registry must contain contiguous subopcodes 1–47")
        c.require(assigned_presentation_requests == expected_presentation_assignments,
                  "presentation audit: presentation requests must use append-only subopcodes 41–47")
    else:
        c.require(set(request_rows) == set(range(1, 41)),
                  "presentation audit: baseline request registry must remain contiguous at IDs 1–40")
    command_rows = re.findall(r"^\|\s*(\d+)\s*\|\s*([A-Z_]+)\s*\|", command_registry, re.M)
    compute_command_rows = [
        (1, "CMD_BIND_PIPELINE"), (2, "CMD_BIND_DESCRIPTOR_SETS"),
        (3, "CMD_DISPATCH"), (4, "CMD_PUSH_CONSTANTS"),
    ]
    assigned_command_rows = compute_command_rows + [(5, "CMD_COPY_BUFFER_TO_SWAPCHAIN_IMAGE")]
    actual_command_rows = [(int(value), name) for value, name in command_rows]
    if command_copy_id_assigned:
        c.require(actual_command_rows == assigned_command_rows,
                  "presentation audit: assigned command-entry registry must append copy entry as ID 5")
        c.require("Assigned command ID: 5" in command_recording,
                  "presentation copy command: assigned ID 5 must be stated in the normative chapter")
    else:
        c.require(actual_command_rows in (compute_command_rows, assigned_command_rows),
                  "presentation audit: command-entry registry has an invalid or non-append-only assignment")
    c.require("both may be supplied together" in presentation and
              "each supplied synchronization object is signaled exactly once" in presentation,
              "AcquireNextImage: optional semaphore/fence combination and success signaling must be explicit")
    lifetime = read("spec/resource-lifetime.md")
    conformance = read("spec/conformance.md")
    errors = read("spec/errors.md")

    # Keep the provisional presentation error map cross-checked against the
    # request ABI rather than validating only the request sizes and offsets.
    presentation_error_contracts = (
        "`CreateSurface`: invalid/already allocated target `surface_xid` is `BadIDChoice`",
        "`DestroySurface`: unknown/non-live Surface XID is `BadValue`",
        "`GetSurfaceCapabilities`: unknown/non-live Device or Surface XID is `BadValue`",
        "`CreateSwapchain`: invalid/already allocated target `swapchain_xid` is `BadIDChoice`",
        "`DestroySwapchain`: unknown/non-live Swapchain XID is `BadValue`",
        "`AcquireNextImage`: unknown/non-live Device or Swapchain XID is `BadValue`",
        "`QueuePresent`: unknown/non-live Device, Swapchain, or wait-semaphore XID is `BadValue`",
        "An acquired-but-idle image alone does not block destruction.",
        "Any rejected request leaves the image `ACQUIRED`, leaves wait-semaphore state unchanged, and does not reserve its presentation token.",
        "Token uniqueness is checked against previously accepted presentations and recorded atomically with acceptance.",
    )
    for contract in presentation_error_contracts:
        c.require(contract in errors,
                  f"presentation request error map: missing invariant: {contract}")
    c.require("For all seven requests, validation is atomic" in errors,
              "presentation request error map: all seven requests must share atomic failure semantics")
    c.require("On every non-success status the target XID remains unallocated" in errors,
              "CreateSwapchain: every non-success reply status must preserve the target XID")
    capability_failure_contract = (
        "TEMPORARILY_NOT_PRESENTABLE means the window has zero extent; it must set "
        "present_supported to 0 and all extent/count/format/mode/usage fields to zero. "
        "SURFACE_LOST and DEVICE_LOST likewise return zero capability fields."
    )
    c.require(capability_failure_contract in presentation,
              "GetSurfaceCapabilities: non-success statuses must define zeroed capability fields")
    c.require("Temporary-not-presentable, surface-lost, and device-lost statuses return zeroed capability fields as specified." in conformance,
              "presentation conformance: capability failure statuses must cover zeroed fields")
    c.require("TIMEOUT/NOT_READY/OUT_OF_DATE/SURFACE_LOST/DEVICE_LOST/DEVICE_DESTROYED are not X11 framing errors" in presentation and
              "DEVICE_DESTROYED=6" in presentation,
              "AcquireNextImage: device destruction must have a distinct terminal reply status")
    c.require("terminalizes each still-open acquire with reply status `DEVICE_DESTROYED`" in presentation and
              "first terminal result serialized by the server wins" in presentation,
              "AcquireNextImage: pending registration must terminate on DestroyDevice without overriding prior terminal outcomes")
    c.require("DEVICE_DESTROYED" in errors.split("`AcquireNextImage`:", 1)[-1].split("\n", 1)[0],
              "AcquireNextImage: error map must include device-destroyed reply outcome")
    # previous baseline status guard intentionally replaced below
    c.require("TIMEOUT/NOT_READY/OUT_OF_DATE/SURFACE_LOST/DEVICE_LOST/DEVICE_DESTROYED are not X11 framing errors" in presentation,
              "AcquireNextImage: all non-success operation statuses must be distinguished from X11 errors")
    c.require("A failed or timed-out acquire signals neither object and changes no image state." in presentation,
              "AcquireNextImage: failure/timeout must not signal semaphore or fence")
    c.require("acquired-but-idle Image allein blockiert nicht" in lifetime and
              "acquired-but-idle images alone do not block destruction" in conformance,
              "DestroySwapchain: lifetime matrix and conformance must agree that idle acquired images alone do not block destruction")
    copy_command = command_recording.split(
        "### `CMD_COPY_BUFFER_TO_SWAPCHAIN_IMAGE`", 1
    )[-1].split("\n## ", 1)[0]
    c.require("CMD_COPY_BUFFER_TO_SWAPCHAIN_IMAGE" in command_recording and
              "36 bytes" in copy_command and "entry_length = 9" in copy_command,
              "presentation copy command: fixed 36-byte/9-word layout missing")
    copy_fields = (
        (0, "`CARD16 command_id`"),
        (2, "`CARD16 entry_length = 9`"),
        (4, "Buffer-XID"),
        (8, "Swapchain-XID"),
        (12, "`CARD32 image_index`"),
        (16, "`CARD64 buffer_offset`"),
        (24, "`CARD32 row_length` in texels; zero means the Swapchain width"),
        (28, "`CARD32 image_height` in texels; zero means the Swapchain height"),
        (32, "`CARD32 reserved = 0`"),
    )
    copy_offsets = re.findall(
        r"^- Relative offset (\d+): (.+)$", copy_command, re.M
    )
    c.require([(int(offset), field) for offset, field in copy_offsets] ==
              list(copy_fields),
              "presentation copy command: field offsets, types, order, or reserved value changed")
    for contract in (
        "The effective row length and image height must be at least the image width and height",
        "overflow-safe wide arithmetic",
        "4 * (effective_row_length * (height - 1) + width)",
        "buffer_offset` must be four-byte aligned",
        "The complete span must lie within the source Buffer",
        "numeric ID must be allocated append-only",
        "It is not part of the current compute-only v0.1 entry set.",
    ):
        c.require(contract in copy_command,
                  f"presentation copy command: missing bounds/alignment/ID contract: {contract}")
    c.require("TRANSFER_DST" in formats and "TRANSFER_SRC" in copy_command,
              "presentation copy path must specify destination and source usage")
    copy_errors = read("spec/errors.md")
    c.require("Presentation-only `CMD_COPY_BUFFER_TO_SWAPCHAIN_IMAGE`" in copy_errors and
              "image_index` außerhalb der Swapchain" in copy_errors and
              "konkurriert der Submit mit einer Present-Transition" in copy_errors,
              "presentation copy command: error mapping must cover resource, bounds, and image-state validation")
    c.require("incompatible transfer usage with `BadMatch`" in read("spec/conformance.md") and
              "non-`ACQUIRED` image at submission acceptance with `INVALID_SYNCHRONIZATION_STATE`" in read("spec/conformance.md"),
              "presentation copy command: conformance must cover usage and acquired-image validation")
    c.require("later copy submission processed after the image has transitioned to `PRESENT_PENDING` is rejected atomically with `INVALID_SYNCHRONIZATION_STATE`" in copy_command and
              "Request order alone creates no GPU memory dependency" in copy_command and
              "Request order alone is not a GPU dependency" in read("spec/conformance.md"),
              "presentation copy command: submit/present ordering must be explicit and request order must not imply GPU synchronization")
    c.require("`RECORDING`-Command-Buffer ihn referenziert oder angenommene Arbeit ihn direkt/indirekt verwendet" in lifetime and
              "ein `RECORDING`-Command-Buffer den Buffer direkt oder indirekt (einschließlich über ein referenziertes Descriptor Set) referenziert" in lifetime and
              "Destroying a Buffer referenced by a `RECORDING` command buffer is atomically rejected" in read("spec/conformance.md"),
              "Buffer lifetime: recording references must block destruction and executable references must be invalidated")
    c.require("Values 7–65535 are unassigned" in read("registries/event-types.md"),
              "compute-only event registry must remain unchanged by presentation event assignments")

def main() -> int:
    c = Check()
    check_events(c)
    check_presentation_profile(c)
    check_xge_abi(c)
    check_reason_code_registry(c)
    check_error_registry(c)
    check_other_numeric_registries(c)
    check_request_document_coverage(c)
    check_request_matrix_normative_lengths(c)
    check_request_limit_contract(c)
    check_local_markdown_links(c)
    check_reply_matrix(c)
    check_reply_layouts(c)
    check_reply_formula_vectors(c)
    check_reply_golden_vectors(c)
    if c.errors:
        print(f"wire-layout check FAILED: {len(c.errors)} of {c.checks} checks failed", file=sys.stderr)
        for error in c.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"wire-layout check passed: {c.checks} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
