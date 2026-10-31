#!/usr/bin/env python3
"""Static consistency checks for XAverius request/reply and XGE wire layouts.

Run from the repository root: python3 tools/check-wire-layout.py
Uses only the Python standard library and parses the normative Markdown sources.
"""
from __future__ import annotations

import re
import sys
import unicodedata
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
    c.require(re.search(r"After an event.*new_status = REMOVED.*MUST NOT send another.*DEVICE_STATUS_CHANGED", doc_sections.get("DEVICE_STATUS_CHANGED", ""), re.I) is not None,
              "DEVICE_STATUS_CHANGED: REMOVED must prohibit subsequent status events for that XID")
    c.require(re.search(r"After emitting.*new_status = REMOVED.*MUST NOT emit another.*DEVICE_STATUS_CHANGED", registry, re.I) is not None,
              "event registry: REMOVED must prohibit subsequent status events for that XID")
    c.require(re.search(r"heap_index.*UINT32_MAX.*less than.*memory_heap_count", doc_sections.get("DEVICE_MEMORY_PRESSURE", ""), re.I) is not None,
              "DEVICE_MEMORY_PRESSURE: heap_index must be a valid heap index or UINT32_MAX")
    lifetime = read("spec/resource-lifetime.md")
    c.require(re.search(r"(?:After successful processing of `DestroyDevice`.*MUST NOT generate or deliver new XAverius events|Nach erfolgreicher Verarbeitung von `DestroyDevice` darf der Server keine neuen XAverius-Events mehr erzeugen oder zustellen)", lifetime, re.S) is not None,
              "DestroyDevice: must suppress later events for the destroyed logical device")
    c.require(
        "`DestroyDevice` cascade linearization" in lifetime
        and "as one indivisible public-state transition" in lifetime
        and "callbacks may finish internal state and release references exactly once" in lifetime
        and "after the destroy linearization point they MUST NOT enqueue or deliver a new event" in lifetime,
        "DestroyDevice: cascade, open-wait outcomes, and callback terminalization must share a linearization point",
    )
    c.require(
        "MUST be keyed by the immutable internal Device/resource/submission identity" in lifetime
        and "MUST NOT mutate the new resource" in lifetime
        and "remain retained or quarantined until backend access is known to be impossible" in lifetime,
        "DestroyDevice: late callbacks and cleanup must not be redirected by XID reuse or free active backend storage",
    )
    c.require(re.search(r"(?:Suppressing delivery does not change the internal terminal outcome of accepted submissions or the requirement to retain backend references until possible accesses have ended|Die Unterdrückung der Zustellung ändert weder den internen terminalen Ausgang angenommener Submissions noch die Pflicht, Backend-Referenzen bis zum Ende möglicher Zugriffe zu halten)", lifetime, re.S) is not None,
              "DestroyDevice: event suppression must preserve terminal submission and backend lifetime rules")
    c.require(
        "Cross-resource teardown and backing-memory release" in lifetime
        and "MUST retire each edge exactly once" in lifetime
        and "MUST NOT release a bound Memory allocation before the old Buffer identity" in lifetime
        and "Invalidating a DescriptorSet XID does not by itself prove" in lifetime,
        "DestroyDevice: teardown must drain descriptor, command, buffer, and memory edges in identity-safe order",
    )
    c.require(re.search(r"(?:If loss is detected only during or after processing `DestroyDevice`, no new event.*internal error and submission states are still terminalized correctly|Wird der Verlust dagegen erst während oder nach der Verarbeitung von `DestroyDevice` festgestellt, wird kein neues Event.*die internen Fehler- und Submission-Zustände werden dennoch korrekt terminalisiert)", lifetime, re.S) is not None,
              "Device loss first detected during DestroyDevice must not emit an event for the destroyed device")
    c.require(re.search(r"(?:A client disconnect ends event delivery for that X11 connection only|Ein Client-Disconnect beendet die Event-Zustellung für genau diese X11-Verbindung)", lifetime, re.S) is not None,
              "Client disconnect: event delivery must stop for that exact X11 connection")
    c.require(re.search(r"(?:MUST NOT enqueue events to a closed connection or deliver them through another connection|dürfen weder Events in eine geschlossene Verbindung einreihen noch über eine andere Verbindung zugestellt werden)", lifetime, re.S) is not None,
              "Client disconnect: late backend events must not target a closed or different connection")
    c.require(re.search(r"(?:Accepted work still reaches its actual internal terminal outcome|Bereits angenommene Arbeit wird unabhängig davon intern bis zu ihrem tatsächlichen terminalen Ausgang abgewickelt)", lifetime, re.S) is not None,
              "Client disconnect: accepted submissions must retain their internal terminal outcome")
    c.require(re.search(r"(?:Resources that the backend may still access remain alive until those accesses are proven to have ended|interne Vulkan-Objekte bleiben bis zum Ende aller Backend-Zugriffe erhalten)", lifetime, re.S) is not None,
              "Client disconnect/device loss: backend resources must remain alive while accesses are possible")
    memory = read("spec/memory-buffers.md")
    devices = read("spec/devices.md")
    conformance = read("spec/conformance.md")
    c.require(
        "If destruction wins while the write is still open, the write is terminalized with the X11 error `DEVICE_DESTROYED`" in lifetime
        and "A `WriteBuffer` operation belonging to a disconnected connection is cancelled" in lifetime
        and "A successful `DestroyDevice` is a lifecycle-control request and MUST remain processable while `WriteBuffer` is waiting" in memory
        and "Any open `WriteBuffer` operation for this Device is also terminalized" in devices,
        "WriteBuffer: Device destruction and disconnect must terminalize an open write without losing backend references",
    )
    c.require(
        "Rennen zwischen erfolgreichem `WriteBuffer`-Commit, Device Loss und `DestroyDevice`" in conformance
        and "Client-Disconnect während des Upload-Wartezustands" in conformance
        and "Disconnect vor einem späteren `SignalSemaphore`" in conformance
        and "Während `WriteBuffer` offen ist, konkurrieren ein gültiges `SignalSemaphore`, Device Loss und `DestroyDevice`" in conformance
        and "Gleichzeitig offene `WriteBuffer`- und `WaitSemaphores`-Operationen" in conformance
        and "Ein bereits vor Device Loss oder `DestroyDevice` terminalisierter `WriteBuffer`-Fehler" in conformance,
        "WriteBuffer: conformance must cover Device Loss, DestroyDevice, disconnect, and concurrent host-signal/wait terminalization",
    )
    c.require(re.search(r"(?:`ASYNC_ERROR` and `DEVICE_LOST` are unmaskable.*independently of `SelectEvents`|`ASYNC_ERROR` und `DEVICE_LOST` sind nicht maskierbar und werden unabhängig von `SelectEvents` zugestellt)", event_doc, re.S) is not None,
              "XGE delivery: ASYNC_ERROR and DEVICE_LOST must be unmaskable")
    c.require(re.search(r"(?:`DEVICE_STATUS_CHANGED` is delivered only through the Connection mask|`DEVICE_STATUS_CHANGED` wird nur über die Connection-Maske zugestellt)", event_doc) is not None,
              "XGE delivery: DEVICE_STATUS_CHANGED must use the connection mask only")
    c.require(re.search(r"(?:The two submission events are delivered only if the corresponding Queue mask bit is set when the terminal submission outcome occurs|Die beiden Submission-Events werden nur zugestellt, wenn das jeweilige Queue-Maskenbit bei Eintritt des terminalen Submission-Ergebnisses gesetzt ist)", event_doc) is not None,
              "XGE delivery: submission event mask must be sampled at terminal outcome")
    c.require(re.search(r"(?:For each accepted submission, `SUBMISSION_COMPLETE` and `SUBMISSION_FAILED` must never both be delivered as terminal events|Pro angenommener Submission darf niemals sowohl `SUBMISSION_COMPLETE` als auch `SUBMISSION_FAILED` als terminales Event ausgeliefert werden)", event_doc) is not None,
              "XGE delivery: a submission cannot deliver both terminal events")
    c.require(re.search(r"(?:A failed event send MUST NOT block GPU/backend processing or trigger a second terminal delivery|Ein fehlgeschlagenes Event-Senden darf weder die GPU-/Backend-Abwicklung blockieren noch eine zweite terminale Zustellung auslösen)", event_doc) is not None,
              "XGE delivery: send failure must not block backend work or duplicate terminal events")
    c.require(re.search(r"(?:On any error, the previous selection remains unchanged|Bei jedem Fehler bleibt die vorherige Auswahl unverändert|On any error, the previous selection remains unchanged)", event_doc) is not None,
              "SelectEvents: failed validation must preserve the previous event selection")
    c.require(re.search(r"(?:Unknown or non-live XIDs result in `BadValue`.*a wrong resource type or foreign client ownership results in `BadMatch`|Unknown or non-live XIDs result in `BadValue`; an incorrect resource type or foreign client ownership results in `BadMatch`)", event_doc, re.S) is not None,
              "SelectEvents: unknown XIDs must map to BadValue, wrong type/foreign ownership to BadMatch")
    c.require(re.search(r"(?:A queue that does not exist within a valid device results in `BadValue`|A nonexistent queue within a valid device results in `BadValue`)", event_doc) is not None,
              "SelectEvents: nonexistent queue on a valid device must map to BadValue")
    c.require(re.search(r"Without negotiated XGE support, `CreateDevice`, `CreateDefaultDevice`, and `SelectEvents` are rejected with `BadMatch`; for `SelectEvents`, the previous selection remains unchanged", event_doc, re.I) is not None,
              "SelectEvents: missing XGE negotiation must return BadMatch without changing prior selection")
    c.require(re.search(r"(?:The request atomically replaces the previous mask for exactly one scope|request atomically replaces the existing mask for exactly one scope)", event_doc) is not None,
              "SelectEvents: successful replacement must be atomic and scoped")
    errors = read("spec/errors.md")
    c.require(re.search(r"A required XAverius XID that does not identify a live resource.*results in `BadValue`", errors, re.S) is not None and
              re.search(r"An XID that identifies a live resource but not the expected resource type results in `BadMatch`", errors) is not None,
              "error mapping: unknown XIDs and live wrong-type XIDs must remain distinct")
    c.require(re.search(r"(?:When a logical Device is successfully destroyed, its Device and Queue selections are removed; the Connection selection remains|Bei erfolgreicher Zerstörung eines logischen Devices werden seine Device- und Queue-Auswahlen entfernt; eine Connection-Auswahl bleibt bestehen)", event_doc) is not None,
              "SelectEvents: device destruction must clear only device and queue selections")
    submissions = read("spec/queue-submission.md")
    c.require(re.search(r"Each accepted submission receives exactly one internal terminal outcome.*delivery is suppressed by a previously processed `DestroyDevice`", submissions, re.S) is not None,
              "QueueSubmit: terminal event delivery must respect DestroyDevice lifecycle suppression")
    c.require(re.search(r"Exactly one terminal event remains designated.*delivery is not suppressed by the `DestroyDevice` lifecycle rules", submissions, re.S) is not None,
              "QueueSubmit/device loss: terminal event requirement must not contradict DestroyDevice suppression")
    sync = read("spec/synchronization.md")
    c.require(re.search(r"After device loss, `GetFenceStatus` remains available.*returns the stored state", sync, re.S | re.I) is not None,
              "synchronization: GetFenceStatus must remain a state query after device loss")
    c.require(re.search(r"`GetFenceStatus`.*Request: exactly 16 bytes.*`BadValue`.*Device Loss is not an error.*stored state", sync, re.S | re.I) is not None and
              re.search(r"`GetFenceStatus`: normative precedence: exact 16-byte length.*`BadMatch`.*Device Loss is not an error", errors, re.S | re.I) is not None,
              "GetFenceStatus: exact length, XID/ownership errors, and post-loss state query must be explicit")
    c.require(re.search(r"`ResetFence`.*Request: exactly 16 bytes.*`BadValue`.*`DEVICE_LOST`", sync, re.S | re.I) is not None and
              re.search(r"`ResetFence`: incorrect length `BadLength`.*cross-device use `BadMatch`.*`DEVICE_LOST` takes precedence over the Fence state.*`INVALID_SYNCHRONIZATION_STATE`", errors, re.S | re.I) is not None,
              "ResetFence: request length, XID/ownership, state, and device-loss errors must be explicit")
    c.require(re.search(r"`WaitForFence`.*Device loss (?:returns|yields) `DEVICE_LOST`", sync, re.S | re.I) is not None,
              "synchronization: WaitForFence must terminate with DEVICE_LOST")
    c.require(re.search(r"open `WaitForFence` registration is waiting on that exact internal fence identity", sync, re.S | re.I) is not None,
              "DestroyFence: must reject while a host wait registration is still open")
    c.require(re.search(r"terminal result.*serialized by the server.*reply not yet sent does not block destruction", sync, re.S) is not None,
              "DestroyFence: a completed wait must stop blocking destruction before reply delivery")
    c.require(re.search(r"open `WaitSemaphores` registration.*references the exact internal semaphore identity", sync, re.S | re.I) is not None,
              "DestroySemaphore: must reject while a host wait registration references the semaphore")
    c.require(re.search(r"terminal result.*serialized by the server.*reply not yet sent does not block destruction", sync, re.S) is not None,
              "DestroySemaphore: a completed wait must stop blocking destruction before reply delivery")
    c.require(re.search(r"`DestroySemaphore`.*exact 16-byte request length.*resolve the Device XID, then the Semaphore XID.*validate live resource types.*check lifetime blockers", sync, re.S | re.I) is not None
              and re.search(r"`DestroySemaphore`: normative precedence is exact 16-byte length.*resolve Device XID, then Semaphore XID.*lifetime blockers", errors, re.S | re.I) is not None
              and "require the Device XID's `BadValue` first" in conformance,
              "DestroySemaphore: Device/object XID order and lifetime-check precedence must be normative and tested")
    c.require(re.search(r"`GetSemaphoreCounterValue`.*request fails with `DEVICE_LOST`", sync, re.S | re.I) is not None,
              "synchronization: counter query must not return an apparently successful value after device loss")
    c.require(re.search(r"`GetSemaphoreCounterValue`.*Request: exactly 16 bytes.*`BadValue`.*request fails with `DEVICE_LOST`", sync, re.S | re.I) is not None and
              re.search(r"`GetSemaphoreCounterValue`: normative precedence: exact 16-byte length.*`BadMatch`.*`DEVICE_LOST`", errors, re.S | re.I) is not None,
              "GetSemaphoreCounterValue: request length, XID/ownership, and device-loss errors must be explicit")
    c.require(re.search(r"WaitSemaphores.*terminates with `DEVICE_LOST`", sync, re.S) is not None,
              "synchronization: semaphore waits must terminate on device loss")
    c.require(re.search(r"(?:Semaphore and Fence objects remain internally alive.*while backend accesses|Semaphore and fence objects remain internally allocated while backend accesses or server-side operations still reference them)", sync, re.S) is not None,
              "synchronization: backend references must outlive device-loss public invalidation")
    c.require(re.search(r"(?:Only after this consumption may a new signal cycle begin|A new signal cycle may begin only after that consumption)", sync, re.S) is not None,
              "synchronization: binary semaphore reuse must follow actual wait consumption")
    c.require(re.search(r"The observable counter advances only when the corresponding signal operation has actually completed successfully", sync, re.S) is not None,
              "synchronization: timeline counter must not advance at submission acceptance")
    c.require(re.search(r"(?:greater than all already reserved pending signal values|not greater than every already-reserved pending GPU signal value)", sync) is not None,
              "synchronization: pending timeline signal values must be reserved monotonically")
    c.require(re.search(r"(?:less than every already reserved, non-terminal GPU signal value|not greater than every already-reserved pending GPU signal value)", sync) is not None,
              "synchronization: host timeline signals must not jump over pending GPU signal reservations")
    c.require("Synchronous validation MUST follow this order" in sync and
              "normative precedence: incorrect length `BadLength`" in errors and
              re.search(r"In mixed-error cases, the earlier phase wins", read("spec/conformance.md")) is not None and
              "counters and reservations unchanged" in errors,
              "SignalSemaphore: validation precedence and atomic rejection must be explicit")
    c.require("total length: `28 + 12 * semaphore_count` bytes" in sync and
              "no duplicate semaphore XIDs (`BadValue`)" in sync and
              "WaitSemaphores`: normative precedence" in errors and "`DEVICE_DESTROYED`" in errors,
              "WaitSemaphores: exact length, XID/ownership errors, and terminal device outcomes must be explicit")
    c.require("Synchronous validation MUST follow this order" in sync and
              "finally require every Semaphore to be `TIMELINE` (`BadMatch`)" in errors and
              re.search(r"In mixed-error cases, the earlier phase wins", read("spec/conformance.md")) is not None and
              "All synchronous rejections occur without registering a wait" in read("spec/conformance.md"),
              "WaitSemaphores: precedence must distinguish pre-registration validation from terminal wait outcomes")
    c.require(re.search(r"`WaitForFence`.*Request: exactly 24 bytes.*`BadValue`.*`BadMatch`.*Device loss yields the normal reply status", sync, re.S | re.I) is not None and
              re.search(r"`WaitForFence`: normative precedence: exact 24-byte length.*Device loss.*`DestroyDevice`.*normal reply statuses", errors, re.S | re.I) is not None,
              "WaitForFence: request length, XID/ownership errors, and reply terminal states must be explicit")
    c.require(re.search(r"WaitSemaphores` MUST NOT synchronously block the X11 request dispatcher", sync) is not None,
              "synchronization: host waits must not block later signals or submissions on the same connection")
    c.require(re.search(r"The timeout deadline starts when the wait request is taken for execution and continues to run", sync) is not None,
              "synchronization: wait timeout must continue while later requests are processed")
    memory = read("spec/memory-buffers.md")
    c.require(re.search(r"signal entries in deferred `QueueSubmit` requests", memory) is not None and
              "`DEPENDENCY_FAILED`" in memory,
              "WriteBuffer: deferred signal dependency cycles must fail rather than deadlock")
    queue_order = read("spec/queue-submission.md")
    c.require(re.search(r"Any other dependency that prevents acceptance results in `DEPENDENCY_FAILED`", queue_order, re.I) is not None and
              re.search(r"Signal entries in deferred submissions do not count as accepted or available signals", memory, re.I) is not None,
              "QueueSubmit/WriteBuffer: deferred signals must not satisfy earlier waits and dependency rejection must be explicit")
    conformance = read("spec/conformance.md")
    errors = read("spec/errors.md")
    c.require(
        "`DestroyFence` and `DestroySemaphore` validate the fixed request length before resolving XIDs" in conformance
        and "non-terminal submission" in conformance
        and "queue wait/signal" in conformance
        and "Once a terminal wait result has been observed in serialized order, a reply that is still pending does not block destruction" in conformance,
        "conformance: specialized destroy tests must cover error precedence and terminal wait release",
    )
    c.require(re.search(r"`WriteBuffer`.*deferred `QueueSubmit`.*`DEPENDENCY_FAILED`", conformance, re.S) is not None,
              "conformance: WriteBuffer dependency-cycle case must be covered")
    submissions = read("spec/queue-submission.md")
    c.require(re.search(r"all semaphore wait/signal reservations and internal references are committed atomically", submissions, re.S) is not None,
              "QueueSubmit: semaphore reservations and references must commit atomically")
    c.require(re.search(r"exact internal semaphore identity.*numeric XID.*reuses the same XID", submissions, re.S) is not None,
              "QueueSubmit: semaphore references must not follow a reused XID")
    c.require(re.search(r"backend can no longer access the semaphore", submissions, re.S) is not None,
              "QueueSubmit: semaphore backend references must survive until safe release")
    c.require("Duplicate wait or signal entries are invalid in v0.1" in submissions and
              "The same semaphore MUST NOT appear in both the wait and signal arrays of one submission" in submissions,
              "QueueSubmit: duplicate semaphore entries and wait/signal aliasing must be rejected")
    c.require("Binary wait/signal values MUST be zero" in conformance and
              re.search(r"duplicate Timeline signal entries for the same semaphore", conformance, re.I) is not None and
              "reserves neither `submission_token` nor semaphore wait/signal slots" in conformance,
              "QueueSubmit: semaphore value checks and rejected-submit atomicity must be covered")
    c.require("The `EXECUTABLE`-to-`PENDING` transitions and synchronization reservations therefore form one shared commit" in submissions and
              "the token remains unused" in submissions and
              "semaphore counters, signal availability, pending slots, and timeline reservations remain unchanged" in submissions,
              "QueueSubmit: all state changes and token reservation must share the acceptance commit")
    c.require("A FINAL chunk transitions `RECORDING` to `EXECUTABLE` only after the entire chunk" in read("spec/command-recording.md") and
              re.search(r"the buffer remains `RECORDING`, all previously accepted entries and references remain unchanged", read("spec/command-recording.md")) is not None,
              "CommandBufferData: failed FINAL must preserve recording state and prior references")
    c.require("A failed FINAL chunk of `CommandBufferData` leaves the buffer `RECORDING`" in conformance and
              "On rejected `QueueSubmit`, every command buffer remains `EXECUTABLE`" in conformance and
              "the token remains unused and may be reused in a corrected request" in submissions and
              "neither `SUBMISSION_COMPLETE`/`SUBMISSION_FAILED` nor `ASYNC_ERROR`" in conformance,
              "conformance: finalization and rejected-submit state transitions must be atomic")
    c.require("synchronous error before acceptance | no state changes" in errors,
              "QueueSubmit: error map must state non-mutating synchronous rejection")
    c.require("Error precedence (the first applicable phase wins)" in submissions and
              "required XIDs are resolved in wire order: device, optional fence, command-buffer XIDs in array order" in submissions and
              "takes precedence over mutable submission state" in submissions and
              "Type-dependent values such as binary wait/signal values are checked only after type resolution" in submissions and
              "first the optional fence state, then command buffers in array order, wait entries in array order, and finally signal entries in array order" in submissions,
              "QueueSubmit: deterministic syntax/XID/ownership/device/state precedence must be normative")
    c.require(re.search(r"\| `QueueSubmit`: Device unavailable/lost.*?\n\| `QueueSubmit`: a Command Buffer is not `EXECUTABLE`", errors, re.S) is not None and
              re.search(r"type-dependent Binary value is nonzero or Timeline signal value is not greater than the observable counter", errors) is not None and
              re.search(r"for CREATE/Append/FINAL on a lost Device, `DEVICE_LOST` takes precedence", conformance, re.I) is not None,
              "QueueSubmit: error table and conformance must follow device-before-state precedence")
    c.require(
        re.search(r"not greater than the observable counter results in `BadValue`", submissions) is not None
        and "conflicts with an existing pending GPU signal reservation" in conformance
        and "`INVALID_SYNCHRONIZATION_STATE`" in conformance
        and "conflicts with an already reserved pending GPU signal value" in errors
        and "`BadValue`" in errors,
        "QueueSubmit: distinguish invalid timeline counter values from pending reservation conflicts",
    )
    c.require(
        "Device loss takes precedence over these binding-specific state/backend checks" in read("spec/memory-buffers.md")
        and "Device Loss gewinnt daher gegen jeden solchen späteren Fehler" in read("spec/shaders-pipelines.md")
        and "pending-set conflict" in conformance,
        "BindBufferMemory/UpdateDescriptorSets: device-loss precedence must follow valid XID/type/ownership checks and precede mutable/backend checks")
    for name, (event_id, total, length) in expected.items():
        c.require(reg_ids.get(name) == event_id, f"event registry: {name} must have stable ID {event_id}")
        c.require(name in doc_sections, f"events.md: missing layout section {name}")
        if name not in doc_sections:
            continue
        body = doc_sections[name]
        total_match = re.search(r"(?:Total length|Gesamtlänge):\s*(\d+)\s*bytes?;\s*XGE `length\s*=\s*(\d+)`", body)
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
        (r"\|\s*2\s*\|\s*CARD16\s*\|[^\n]*(?:event sequence number|Sequenznummer)", "16-bit X11 event sequence at offset 2"),
        (r"\|\s*1\s*\|[^\n]*(?:dynamically assigned XAverius major opcode|dynamisch zugewiesener XAverius-Major-Opcode)", "dynamic extension opcode at offset 1"),
        (r"\|\s*4\s*\|[^\n]*XGE `length`", "XGE length at offset 4"),
        (r"\|\s*10–31\s*\|[^\n]*(?:zero|null)", "zeroed reserved common-header bytes"),
        (r"\|\s*8\s*\|[^\n]*`evtype`", "evtype at offset 8"),
        (r"32 \+ 4 \* length", "XGE total-length formula"),
    ]
    for pattern, label in header_checks:
        c.require(re.search(pattern, event_doc, re.I) is not None, f"events.md: missing {label}")
    wire_protocol = read("spec/wire-protocol.md")
    protocol_checks = [
        (r"QueryExtension", "dynamic major opcode discovery via QueryExtension"),
        (r"128–255", "X11 extension major opcode range 128–255"),
        (r"non-zero value MUST result in `BadValue` before subopcode dispatch", "nonzero X11 data byte rejection before request dispatch"),
        (r"common-header `flags` byte at offset 5 and `reserved` CARD16 at offset 6", "common-header flags and reserved-field zero rule"),
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
    conformance = read("spec/conformance.md")
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
        "The first invalid XID determines the reported resource error",
        "The request remains atomic",
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
        and "`descriptor_type = 0` and unassigned descriptor-type values return `BadValue`" in descriptor_conformance,
        "UpdateDescriptorSets: error map and conformance cases must agree on descriptor type validation",
    )
    lifetime = read("spec/resource-lifetime.md")
    c.require(
        "`ResetCommandBuffer` with an incorrect request length results in `BadLength`" in descriptor_errors
        and "an unavailable or lost logical Device returns `DEVICE_UNAVAILABLE` or `DEVICE_LOST`" in descriptor_errors
        and "After successful XID and ownership validation, an unavailable device results in `DEVICE_UNAVAILABLE`" in read("spec/command-recording.md")
        and re.search(r"`DEVICE_UNAVAILABLE`.*`DEVICE_LOST`", descriptor_conformance) is not None,
        "ResetCommandBuffer: device-state errors must be specified consistently across normative, error, and conformance chapters",
    )
    command_pool_contract = read("spec/command-recording.md")
    queue_submit_contract = read("spec/queue-submission.md")
    c.require(
        "queue_family_index` that is not configured for the logical Device with a positive requested queue count results in `BadValue`" in descriptor_errors
        and "Every queue family exposed by Vulkan supports command-buffer submission" in command_pool_contract
        and "v0.1 defines no separate command-buffer-support flag" in command_pool_contract
        and "`COMPUTE` bit in the Queue Flag Registry" in command_pool_contract
        and "parent Command Pool's `queue_family_index` MUST equal" in queue_submit_contract
        and "A command buffer created from one queue family MUST NOT be submitted to a queue from another family" in queue_submit_contract
        and "ein Command Buffer stammt aus einem Command Pool einer anderen Queue-Family" in descriptor_errors
        and "CMD_DISPATCH" in descriptor_errors
        and "family lacks the `COMPUTE` flag" in descriptor_errors
        and "Command-entry queue capability" in descriptor_conformance
        and "two queue families on one Device" in descriptor_conformance,
        "command pools/submission: queue-family identity and per-entry capability rules must be explicit and cross-checked",
    )
    synchronization = read("spec/synchronization.md")
    c.require(
        "validate `semaphore_type` and the type-dependent `initial_value` (`BadValue`" in synchronization
        and "unknown `semaphore_type` and, separately, `BINARY` with nonzero `initial_value` with an occupied target XID" in descriptor_conformance
        and "unknown `semaphore_type`" in descriptor_conformance
        and "BINARY` with nonzero `initial_value`" in descriptor_conformance
        and "backend allocation failure only after Device identity/ownership and Device-state checks pass" in descriptor_conformance,
        "CreateSemaphore: type-dependent syntax, target-XID precedence, and allocation rollback need conformance coverage",
    )
    c.require(
        "Device-state check and counter snapshot are serialized against Device Loss" in synchronization
        and "complete counter value before publication or the complete value after publication" in descriptor_conformance
        and "no normal reply" in descriptor_conformance,
        "GetSemaphoreCounterValue: snapshot linearization and Device-loss reply suppression must remain explicit",
    )
    presentation = read("spec/presentation.md")
    lifetime = read("spec/resource-lifetime.md")
    c.require("open `AcquireNextImage` registration with a supplied Fence → `PENDING`" in synchronization
              and "A pending acquire that succeeds commits `PENDING` → `SIGNALED`" in synchronization
              and "if it terminates without acquiring an image, its reservation is released" in synchronization
              and "the Fence becomes `PENDING` atomically with the registration" in presentation
              and "pending `AcquireNextImage` signal reservation" in descriptor_errors
              and "durch eine offene `AcquireNextImage`-Registrierung als `PENDING`-Signalziel reserviert ist" in lifetime
              and "AcquireNextImage Fence reservation" in descriptor_conformance,
              "AcquireNextImage Fence reservation must share Fence pending state, WaitForFence, QueueSubmit, and destroy blockers")
    command_recording = read("spec/command-recording.md")
    decisions = read("DECISIONS.md")
    c.require(
        "descriptor-slot contents are not copied into the command buffer as an immutable snapshot" in command_recording
        and "atomically updates the derived buffer references" in command_recording
        and "uses the set's current descriptor contents at later submission time" in descriptor_updates,
        "descriptor updates: command buffers must observe current set contents and refresh indirect references",
    )
    c.require(
        "A successful `UpdateDescriptorSets` therefore atomically replaces the affected slot contents and updates the derived internal Buffer references" in lifetime
        and "old resource that is no longer referenced" in lifetime
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
    property_parts = devices.split("Normative XAverius property type IDs:", 1)
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
    property_contracts = (
        "`XAverius.deviceUUID` | `BYTE_ARRAY` (5) | Exactly 16 raw bytes",
        "`XAverius.driverUUID` | `BYTE_ARRAY` (5) | Exactly 16 raw bytes",
        "`XAverius.compute.maxWorkGroupInvocations` | `CARD32` (1) | One unsigned 32-bit integer",
        "`XAverius.compute.maxWorkGroupSize` | `CARD32_ARRAY` (6) | Exactly three unsigned 32-bit integers",
        "`XAverius.timelineSemaphore` | `CARD32` (1) | `1` if the Physical Device supports",
        "For `SUCCESS`, the reply's `property_type` MUST match the registered type",
        "`value_length` MUST equal the exact size specified above",
        "padding bytes MUST be zero",
        "MUST NOT fabricate a UUID",
    )
    for contract in property_contracts:
        c.require(contract in property_registry,
                  f"physical-device property registry missing exact value/reply contract: {contract}")
    c.require(
        len(re.findall(r"^\| `XAverius\.[^|]+` \|", property_registry, re.M)) == 5,
        "physical-device property registry must contain exactly five v0.1 properties",
    )
    c.require(
        "For a status other than `SUCCESS`, `property_type` and `value_length` MUST be zero" in devices
        and "`reply.length = 0`" in devices
        and "Reserved; MUST be zero" in devices,
        "GetPhysicalDeviceProperty: error statuses, reserved bytes, and empty reply encoding must be normative",
    )

    feature_registry = read("registries/feature-ids.md")
    extension_registry = read("registries/device-extensions.md")
    c.require("No optional device feature IDs are assigned in v0.1" in feature_registry,
              "feature-ID registry must explicitly preserve the empty v0.1 set")
    c.require("No optional device extensions are assigned in v0.1" in extension_registry,
              "device-extension registry must explicitly preserve the empty v0.1 set")


def check_request_field_offsets_and_widths(c: Check) -> None:
    """Check explicit request-field offsets and widths in every normative request section."""
    registry_text = read("registries/request-subopcodes.md")
    registry_rows = re.findall(
        r"^\|\s*\x60([^\x60]+)\x60\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|",
        registry_text, re.M,
    )
    sizes = {
        "CARD8": 1, "CARD16": 2, "CARD32": 4, "CARD64": 8,
        "XID": 4, "ATOM": 4, "FLOAT32": 4,
    }
    checked = 0
    field_layout_names: set[str] = set()
    for name, _opcode, _kind, responsibility in registry_rows:
        link = re.search(r"\.\./spec/([^)]*\.md)", responsibility)
        c.require(link is not None,
                  f"{name}: central registry responsibility must link to a normative spec chapter")
        if not link:
            continue
        chapter = read("spec/" + link.group(1))
        # Bound the scan to this request heading, not sibling requests or
        # reply fields that happen to share the same normative section.
        chapter_lines = chapter.splitlines()
        headings = []
        for i, heading_line in enumerate(chapter_lines):
            heading_match = re.match(r"^(#{2,4})\s+(.+?)\s*$", heading_line)
            if heading_match:
                headings.append((i, len(heading_match.group(1)), heading_match.group(2)))
        heading_index = next(
            (i for i, (_line, _level, title) in enumerate(headings)
             if (chr(96) + name + chr(96) in title)
             or re.fullmatch(r"(?:\d+(?:\.\d+)*\s+)?"+re.escape(name), title.strip())),
            None,
        )
        if heading_index is None:
            section = request_normative_section(chapter, name)
        else:
            start_line, level, _title = headings[heading_index]
            end_line = next(
                (line_index for line_index, heading_level, _title2 in headings[heading_index + 1:]
                 if heading_level <= level),
                len(chapter_lines),
            )
            section = "\n".join(chapter_lines[start_line + 1:end_line])
        c.require(bool(section),
                  f"{name}: normative request section could not be resolved from its registry chapter")
        if not section:
            continue
        request_lines = []
        for line in section.splitlines():
            if re.match(r"^\s*(?:Reply(?: layout| fields)?|Reply:|The reply contains|Reply payload)\b", line, re.I):
                break
            request_lines.append(line)
        # Reserved fields and alignment bytes are protocol invariants, not
        # implementation-defined slack. Check each request's own contract in
        # addition to the shared common-header rule in wire-protocol.md.
        request_text = "\n".join(request_lines)
        if re.search(r"\breserved(?:\s+(?:field|word|bytes?|bits?|CARD\d+)|\s*=)|\b(?:bits?|bytes?|CARD\d+|offset\s+\d+)[^\n.;]{0,80}\breserved\b", request_text, re.I):
            c.require(bool(re.search(
                r"reserved.{0,100}(?:MUST|must|shall|SHALL|=|is)\s*(?:be\s+)?(?:zero|0)\b|"
                r"(?:MUST|must|shall|SHALL)\s+be\s+zero.{0,100}reserved|"
                r"non.?zero.{0,100}reserved.{0,100}(?:BadValue|reject|invalid)|"
                r"reserved.{0,100}non.?zero.{0,100}(?:BadValue|reject|invalid)",
                request_text, re.I | re.S,
            )), f"{name}: request-local reserved field/bit must explicitly require zero")
            c.require(not bool(re.search(
                r"reserved.{0,100}(?:may|can|is allowed to)\s+be\s+non.?zero|"
                r"non.?zero.{0,100}reserved.{0,80}(?:accepted|ignored)",
                request_text, re.I | re.S,
            )), f"{name}: request-local reserved field contradicts the zero requirement")
        if re.search(r"\bpadding\b|\bpadded\b", request_text, re.I):
            # The shared wire-protocol chapter supplies the zero-byte rule;
            # request-local variable BYTE[] fields are separately required to
            # name their padding contract below. Here reject contradictions.
            c.require(not bool(re.search(
                r"(?:padding|padded).{0,100}(?:may|can|is allowed to)\s+be\s+non.?zero|"
                r"non.?zero.{0,100}padding.{0,80}(?:accepted|ignored)",
                request_text, re.I | re.S,
            )), f"{name}: request-local padding contradicts the zero-padding rule")
        records: list[tuple[int, int, str, str, int]] = []
        absolute_table_rows: list[tuple[int, str, int]] = []
        absolute_table_groups: list[list[tuple[int, str, int]]] = []
        in_absolute_table = False
        saw_variable_field = False
        absolute_table_start_line = 0
        for line_no, line in enumerate(request_lines, 1):
            if re.search(r"^\|\s*Relative Offset\s*\|", line, re.I):
                in_absolute_table = False
                saw_variable_field = False
                continue
            if re.search(r"^\|\s*Offset\s*\|\s*Type\s*\|\s*Field\s*\|", line, re.I):
                if in_absolute_table and absolute_table_rows:
                    absolute_table_groups.append(absolute_table_rows)
                absolute_table_rows = []
                in_absolute_table = True
                saw_variable_field = False
                absolute_table_start_line = line_no
                continue
            if not line.lstrip().startswith("|") and in_absolute_table:
                if absolute_table_rows:
                    absolute_table_groups.append(absolute_table_rows)
                    absolute_table_rows = []
                in_absolute_table = False
            if line.lstrip().startswith("|") and in_absolute_table:
                row = re.match(r"^\|\s*(\d+)\s*\|\s*([A-Za-z][A-Za-z0-9_\[\]]*)\s*\|\s*([^|]+?)\s*\|", line)
                if re.match(r"^\|\s*-+", line):
                    continue
                if row:
                    offset, typ, field = int(row.group(1)), row.group(2), row.group(3).strip()
                    # These are legitimate variable-width payload descriptions,
                    # not scalar fields whose width can be checked here.
                    if typ.endswith("[]") or typ == "variable":
                        # A variable payload has no scalar width, but its start
                        # and position relative to fixed fields are still part
                        # of the wire contract. It must be the final field in
                        # its layout table; otherwise the table cannot define
                        # an unambiguous payload boundary.
                        c.require(not saw_variable_field,
                                  f"{name}: multiple variable-width fields in one absolute request-field table (spec line {line_no})")
                        saw_variable_field = True
                        c.require(offset >= 8,
                                  f"{name}: variable field {field!r} at offset {offset} overlaps the common 8-byte header (spec line {line_no})")
                        c.require(offset % 4 == 0,
                                  f"{name}: variable field {field!r} at offset {offset} is not four-byte aligned (spec line {line_no})")
                        c.require(offset < 262140,
                                  f"{name}: variable field {field!r} at offset {offset} exceeds the ordinary X11 request limit (spec line {line_no})")
                        prior_scalars = [
                            (old_offset, old_width, old_field, old_line)
                            for old_offset, old_width, _old_type, old_field, old_line in records
                            if absolute_table_start_line < old_line < line_no
                        ]
                        for old_offset, old_width, old_field, old_line in prior_scalars:
                            c.require(old_offset + old_width <= offset,
                                      f"{name}: variable field {field!r} at offset {offset} overlaps fixed field {old_field!r} ending at {old_offset + old_width} (spec line {line_no})")
                        if typ == "BYTE[]":
                            c.require(bool(re.search(r"padding|padded", field, re.I)),
                                      f"{name}: byte payload {field!r} must explicitly describe its padding rule (spec line {line_no})")
                        # Keep variable-width fields in table-level uniqueness
                        # checks even though their scalar width is not known.
                        absolute_table_rows.append((offset, field, line_no))
                        continue
                    c.require(not saw_variable_field,
                              f"{name}: fixed field {field!r} follows a variable-width field in the absolute request-field table (spec line {line_no})")
                    c.require(typ in sizes, f"{name}: unknown wire type {typ!r} in absolute request-field table (spec line {line_no})")
                    if typ in sizes:
                        c.require(offset >= 8,
                                  f"{name}: field {field!r} at offset {offset} overlaps the common 8-byte header (spec line {line_no})")
                        records.append((offset, sizes[typ], typ, field, line_no))
                        absolute_table_rows.append((offset, field, line_no))
                else:
                    # A different table (for example flags or enum values) can
                    # immediately follow the request layout. Its non-numeric
                    # first cell marks a table boundary; numeric rows, however,
                    # are attempts at absolute field entries and must be valid.
                    first_cell = line.split("|")[1].strip() if "|" in line else ""
                    if first_cell.isdecimal():
                        c.require(False,
                                  f"{name}: malformed row in absolute request-field table (spec line {line_no})")
                    if absolute_table_rows:
                        absolute_table_groups.append(absolute_table_rows)
                        absolute_table_rows = []
                    in_absolute_table = False
                continue
            bullet = re.match(r"^\s*(?:[-*]\s*)?Offset\s+(\d+)\s*:\s*(.+)$", line, re.I)
            if bullet:
                offset, tail = int(bullet.group(1)), bullet.group(2).strip()
                tm = re.search(r"\b(CARD8|CARD16|CARD32|CARD64|XID|ATOM|FLOAT32)\b", tail)
                typ = tm.group(1) if tm else None
                if typ is None and re.search(r"\bXID\b|(?:Device|Buffer|Memory|Fence|Semaphore|Surface|Swapchain|Window|Pool|Pipeline|Layout|Module|Set)-XID", tail, re.I):
                    typ = "XID"
                if typ in sizes and offset >= 8:
                    records.append((offset, sizes[typ], typ, tail, line_no))
        if in_absolute_table and absolute_table_rows:
            absolute_table_groups.append(absolute_table_rows)
        # Validate each table independently: separate request variants can use
        # the same offsets and field names in nested normative subsections.
        for table_rows in absolute_table_groups:
            table_offsets = [offset for offset, _field, _line_no in table_rows]
            table_fields = [field for _offset, field, _line_no in table_rows]
            c.require(len(table_offsets) == len(set(table_offsets)),
                      f"{name}: duplicate offsets in absolute request-field table")
            c.require(len(table_fields) == len(set(table_fields)),
                      f"{name}: duplicate field names in absolute request-field table")
            table_layout = sorted(
                (offset, sizes[typ], field, line_no)
                for off, width, typ, field, line_no in records
                for offset in [off]
                if any(offset == table_off and field == table_field and line_no == table_line
                       for table_off, table_field, table_line in table_rows)
            )
            for index, (offset, width, field, line_no) in enumerate(table_layout):
                if index:
                    previous_offset, previous_width, previous_field, _previous_line = table_layout[index - 1]
                    c.require(previous_offset + previous_width <= offset,
                              f"{name}: field {field!r} at offset {offset} overlaps {previous_field!r} ending at {previous_offset + previous_width} (spec line {line_no})")
        # Some normative request summaries state XID positions inline (for
        # example, "device XID at offset 8") rather than in a typed table or
        # Offset bullet. Capture those explicit declarations too; reply prose
        # has already been excluded above.
        for line_no, line in enumerate(request_lines, 1):
            for inline_xid in re.finditer(
                r"\b([A-Za-z][A-Za-z0-9 -]*?\s+)?XID(?:\s+is)?\s+at offset\s+(\d+)\b",
                line, re.I,
            ):
                offset = int(inline_xid.group(2))
                field = ((inline_xid.group(1) or "") + "XID").strip()
                if offset >= 8:
                    records.append((offset, sizes["XID"], "XID", field, line_no))
        # Avoid duplicate prose/table mentions while preserving distinct fields.
        unique = {}
        for offset, width, typ, field, line_no in records:
            key = (offset, width, typ, field)
            unique.setdefault(key, line_no)
        ordered = sorted((off, width, typ, field, ln) for (off, width, typ, field), ln in unique.items())
        if not ordered:
            # A request with no machine-readable field offsets is accepted only
            # when its compact layout is covered by a dedicated exact-contract
            # assertion below. This prevents silent gaps in the per-request audit.
            # Compact prose layouts are not exempt from auditing: require a
            # per-request contract with exact fixed length and every field offset/type.
            compact_contracts = {
                "EnumeratePhysicalDevices": (8, ()),
                "GetPhysicalDeviceMemoryProperties": (12, ((8, "XID"),)),
                "GetBufferMemoryRequirements": (16, ((8, "XID"), (12, "XID"))),
                "FreeMemory": (16, ((8, "XID"), (12, "XID"))),
                "BindBufferMemory": (28, ((8, "XID"), (12, "XID"), (16, "XID"), (20, "CARD64"))),
                "GetSemaphoreCounterValue": (16, ((8, "XID"), (12, "XID"))),
                "GetFenceStatus": (16, ((8, "XID"), (12, "XID"))),
                "ResetFence": (16, ((8, "XID"), (12, "XID"))),
                "DestroyFence": (16, ((8, "XID"), (12, "XID"))),
                "DestroySemaphore": (16, ((8, "XID"), (12, "XID"))),
            }
            compact = compact_contracts.get(name)
            if compact is not None:
                expected_length, expected_fields = compact
                length_declared = bool(re.search(
                    rf"\b(?:total length|fixed total length|exactly)\s*(?:of|is|:)?\s*{expected_length}\s*bytes\b|request\s*:\s*exactly\s*{expected_length}\s*bytes\b",
                    section, re.I,
                )) or (expected_length == 8 and bool(re.search(
                    r"no request-specific payload.{0,80}8 bytes in total", section, re.I | re.S
                )))
                c.require(length_declared,
                          f"{name}: compact layout must explicitly assert exact total length {expected_length} bytes")
                for offset, typ in expected_fields:
                    field_declared = bool(re.search(
                        rf"(?:Offset\s+{offset}\s*:\s*(?:`?{typ}`?\b|[^\n]*\b{typ}\b)|"
                        rf"\|\s*{offset}\s*\|\s*{typ}\s*\|)",
                        section, re.I,
                    ))
                    if typ == "XID":
                        field_declared = field_declared or bool(re.search(
                            rf"\b(?:[A-Za-z][A-Za-z -]* )?XID\s+at offset\s+{offset}\b",
                            section, re.I,
                        ))
                    c.require(field_declared,
                              f"{name}: compact layout missing explicit {typ} field at offset {offset}")
            else:
                # Presentation layouts live in their dedicated normative chapter,
                # not in the compute request section used by this generic audit.
                # Their seven exact request/reply contracts are checked below by
                # check_presentation_profile() and the presentation wire audit.
                pass
            c.require(name in compact_contracts if name in compact_contracts else name in {
                "CreateSurface", "DestroySurface", "GetSurfaceCapabilities",
                "CreateSwapchain", "DestroySwapchain", "AcquireNextImage", "QueuePresent",
            }, f"{name}: no explicit compact-layout assertion is registered")
            field_layout_names.add(name)
            continue
        checked += 1
        field_layout_names.add(name)
        # If the request section declares an exact fixed total length, every
        # explicitly located request field must fit inside it. Ignore minimum
        # and variable-length contracts such as chunked uploads.
        fixed_length = None
        for line in request_lines:
            if re.search(r"\b(?:at least|minimum|variable|variable-length)\b", line, re.I):
                continue
            match = re.search(
                r"\b(?:fixed total length of|total length(?: is|:)?|exactly)\s+(\d+)\s+bytes\b",
                line, re.I,
            )
            if match:
                fixed_length = int(match.group(1))
                break
        if fixed_length is not None and heading_index is not None:
            for offset, width, typ, field, line_no in ordered:
                c.require(offset + width <= fixed_length,
                          f"{name}: field {field!r} at offset {offset} (width {width}) exceeds fixed request length {fixed_length} (spec line {line_no})")
        # Do not infer overlap from independent prose fragments: some normative
        # request sections define several payload variants in one subsection.
        # Widths are used to check scalar alignment. Overlap is not inferred
        # across mixed prose/table declarations because some request sections
        # also describe reply fields in the same subsection.
        for offset, width, typ, field, line_no in ordered:
            c.require(offset + width <= 262140,
                      f"{name}: field {field!r} at offset {offset} exceeds the ordinary X11 request limit (spec line {line_no})")
        # Each explicit field must be aligned to its wire scalar width, except
        # CARD8, which is byte-addressable. X11 request payloads remain word-framed.
        for offset, width, typ, field, line_no in ordered:
            if width > 1:
                c.require(offset % min(width, 4) == 0,
                          f"{name}: {typ} field {field!r} at offset {offset} is misaligned (spec line {line_no})")
    expected_request_names = {name for name, _opcode, _kind, _responsibility in registry_rows}
    c.require(len(expected_request_names) == len(registry_rows),
              "request field audit: duplicate request names in the central registry")
    c.require(field_layout_names == expected_request_names,
              "request field audit: layout coverage mismatch; "
              f"missing={sorted(expected_request_names - field_layout_names)}, "
              f"unexpected={sorted(field_layout_names - expected_request_names)}")
    c.require(checked >= 25,
              f"request field audit: expected typed offsets in at least 25 registered request sections, found {checked}")


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
        "`EnumeratePhysicalDevices`: an incorrect request length (`!= 8` bytes) results in `BadLength`" in errors
        and "If no Physical Devices are available, an empty successful reply with `reply.length = 0` is permitted" in errors,
        "error mapping: EnumeratePhysicalDevices must define length failure and empty-result behavior",
    )
    c.require(
        "`CreateBuffer`: falsche feste Länge `BadLength`" in errors
        and "nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`" in errors
        and "fehlgeschlagene Backend-Erstellung wegen Speicherknappheit `ALLOCATION_FAILED`" in errors,
        "error mapping: CreateBuffer must distinguish device state from backend allocation failure",
    )
    c.require(
        "`AllocateMemory`: incorrect length `BadLength`" in errors
        and "live resource of the wrong type or foreign Device ownership `BadMatch`" in errors
        and "unavailable or lost Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`" in errors
        and "on rejection, the target XID remains unallocated" in errors
        and "`memory_xid` remains unallocated" in read("spec/memory-buffers.md"),
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
        "MUSS der Server jeden Backend-`VkDescriptorPool` mit `VK_DESCRIPTOR_POOL_CREATE_FREE_DESCRIPTOR_SET_BIT` erzeugen" in read("spec/shaders-pipelines.md")
        and "verify that the server creates every backend descriptor pool with `VK_DESCRIPTOR_POOL_CREATE_FREE_DESCRIPTOR_SET_BIT` set" in conformance
        and "successful `FreeDescriptorSets` frees only the selected Sets" in conformance,
        "descriptor pools: backend must enable individual descriptor-set freeing because v0.1 exposes FreeDescriptorSets",
    )
    c.require(
        "`CreateSemaphore`:" in errors and "`CreateFence`:" in errors
        and "wrong live resource type or foreign Device ownership `BadMatch`" in errors
        and "unavailable or lost Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`" in errors
        and "On rejection, the target XID remains unallocated" in errors
        and "Creation is atomic: on any failure, the semaphore XID remains unallocated" in read("spec/synchronization.md")
        and "Creation is atomic: on any failure, the fence XID remains unallocated" in read("spec/synchronization.md"),
        "error mapping: CreateSemaphore/CreateFence must define device-state errors and atomic XID behavior",
    )
    c.require(
        "An unavailable/lost Device returns `DEVICE_UNAVAILABLE` / `DEVICE_LOST`" in errors
        and "a synchronous backend allocation failure returns `ALLOCATION_FAILED`" in errors
        and "foreign Device ownership, or a cross-Device resource returns `BadMatch`" in errors,
        "error mapping: CreateDescriptorSetLayout must distinguish device, ownership and allocation errors",
    )
    c.require(
        "`CreatePipelineLayout`:" in errors
        and "nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`" in errors
        and "Backend-Allokationsfehler `ALLOCATION_FAILED`" in errors
        and "Kein Pipeline Layout bleibt bei Ablehnung live" in errors
        and "Bei jedem Fehler bleibt die Pipeline-Layout-XID unangelegt" in read("spec/shaders-pipelines.md")
        and "Ziel-XID (`BadIDChoice`)" in read("spec/shaders-pipelines.md"),
        "error mapping: CreatePipelineLayout must define device-state and atomic creation behavior",
    )
    c.require(
        "`CreateComputePipeline`:" in errors
        and "nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`" in errors
        and "Backend-Allokationsfehler `ALLOCATION_FAILED`" in errors
        and "Kein Pipeline-Objekt bleibt bei Ablehnung live" in errors
        and "bei Fehlern wird kein Pipeline-Objekt öffentlich angelegt" in read("spec/shaders-pipelines.md")
        and "Ziel-Pipeline-XID (`BadIDChoice`)" in read("spec/shaders-pipelines.md"),
        "error mapping: CreateComputePipeline must define device-state and atomic creation behavior",
    )
    c.require(
        "### `CreateCommandPool`" in errors
        and "An unavailable or lost Device results in `DEVICE_UNAVAILABLE` or `DEVICE_LOST`" in errors
        and "backend allocation failure results in `ALLOCATION_FAILED`" in errors
        and "On rejection, the pool XID remains unallocated" in errors
        and "Creation is atomic: on any failure, the pool XID remains unallocated" in read("spec/command-recording.md"),
        "error mapping: CreateCommandPool must define device-state and atomic creation behavior",
    )
    command_recording = read("spec/command-recording.md")
    c.require(
        all(token in command_recording for token in (
            "| 0 | 0 | 0 | Append entries to a buffer that is already recording |",
            "| 0 | 1 | 0 | Append final entries and end recording |",
            "| 1 | 0 | 0 | Create a command buffer, begin recording, and record the first chunk |",
            "| 1 | 1 | 0 | Create a command buffer, record the complete stream, and finish recording |",
            "| 0 | 0 | 1 | Abort recording; no entries are allowed |",
        )),
        "CommandBufferData: the five permitted CREATE/FINAL/ABORT combinations must remain explicit",
    )
    c.require(
        "`command_pool_xid` MUST match the buffer's pool even for ABORT" in command_recording
        and "The specified pool MUST match the Buffer's parent pool even for `ABORT`" in errors,
        "CommandBufferData: ABORT must validate exact command-pool ownership",
    )
    c.require(
        "resolves XIDs in wire order: target command-buffer XID, pool XID, then embedded command-entry XIDs" in errors
        and "an invalid or already allocated target XID results in `BadIDChoice`" in errors
        and "an unknown or non-live Buffer XID results in `BadValue`" in errors,
        "CommandBufferData: target-XID error precedence must distinguish CREATE from input lookup",
    )
    c.require("### Error Precedence for `CommandBufferData`" in command_recording and
              "field errors take precedence over target/pool/entry XID errors" in command_recording and
              "takes precedence over command-buffer state and entry/resource compatibility checks" in command_recording and
              "ABORT" in command_recording and
              "before Buffer state or resource-dependent command-entry compatibility" in errors,
              "CommandBufferData: syntax/XID/ownership/device/state precedence and ABORT exception must agree")
    c.require("`CommandBufferData` error precedence: malformed request/entry structure" in conformance and
              "an invalid flag combination combined with an invalid target XID returns `BadValue`" in conformance and
              "`ABORT` is the defined exception to phases 5–7" in command_recording,
              "CommandBufferData: error precedence edge cases must be covered by conformance")
    c.require(
        "an entry whose declared length exceeds the request boundary" in errors
        and "invalid entry lengths (especially zero or less than the entry header)" in errors
        and "unknown command IDs" in errors,
        "CommandBufferData: malformed entry length and unknown command ID errors must be explicit",
    )
    c.require(
        "entry-local scalar/field syntax are checked next (`BadValue`), before any XID lookup" in conformance
        and "resource-dependent semantics (after XID, ownership, and Device checks)" in conformance
        and "semantic entry values, and Device/Buffer state" not in conformance,
        "CommandBufferData: conformance must distinguish pre-XID entry syntax from post-XID resource semantics",
    )
    c.require(
        "Maximum entry size: 65531 words (262124 bytes)" in command_recording
        and "16-byte fixed request header (four 32-bit words)" in command_recording
        and "maximum ordinary X11 request is 65535 words (262140 bytes)" in command_recording
        and "65531 words (262124 bytes)" in read("registries/command-entries.md")
        and "entry_length = 65531" in conformance
        and "entry_length = 65532" in conformance
        and "aggregate exceeds 65531 words" in conformance
        and 65531 + 4 == 65535
        and 65531 * 4 + 16 == 262140
        and 65532 * 4 + 16 > 262140,
        "CommandBufferData: entry and aggregate limits must account for the fixed X11/XAverius request header",
    )
    c.require(
        "A failed FINAL chunk leaves the buffer in `RECORDING`" in read("spec/command-recording.md")
        and "A failed CREATE request leaves neither a command buffer nor a pool-child entry" in read("spec/command-recording.md")
        and "Every rejection leaves previously accepted entries and references unchanged; the current chunk is never partially accepted" in read("spec/command-recording.md"),
        "command-buffer recovery: failed CREATE/FINAL and reset atomicity must be covered",
    )
    shader_upload = read("spec/shaders-pipelines.md")
    event_doc = read("spec/events.md")
    c.require(
        "A later chunk or ABORT for a discarded assembly" in shader_upload
        and "They do not emit `ASYNC_ERROR`" in shader_upload
        and "Errors during `ShaderModuleData` upload MUST NOT generate `ASYNC_ERROR`" in errors
        and "Errors during `ShaderModuleData` upload and `CommandBufferData` recording chunks are always synchronous" in event_doc,
        "chunked shader upload: failed/interrupted assemblies must be discarded and chunk errors must stay synchronous",
    )
    c.require(
        "For CREATE, append, and FINAL, check the associated device state" in command_recording
        and "`ABORT` is the defined exception to phases 5–7" in command_recording
        and "`ABORT` is the explicit logical exception" in errors
        and "For CREATE/Append/FINAL on a lost Device, `DEVICE_LOST` takes precedence" in conformance,
        "CommandBufferData: device-loss failures must preserve accepted chunks while ABORT remains logical cleanup",
    )
    c.require(
        "Chunk errors are synchronous errors associated with the corresponding `CommandBufferData` request and do not generate `ASYNC_ERROR`" in command_recording
        and "Errors during `ShaderModuleData` upload and `CommandBufferData` recording chunks are always synchronous" in event_doc
        and "do not generate `ASYNC_ERROR`" in conformance,
        "chunked shader/command-buffer operations must not emit async errors before submission acceptance",
    )
    c.require(
        "`AllocateDescriptorSets`:" in errors
        and "nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`" in errors
        and "Backend-Allokationsfehler `ALLOCATION_FAILED`" in errors
        and "keine Teilmenge bleibt live" in errors
        and "keine Teilmenge der Sets öffentlich angelegt bleiben" in read("spec/shaders-pipelines.md")
        and "Ziel-Set-XID in Array-Reihenfolge" in read("spec/shaders-pipelines.md"),
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
            "defined only for buffers, shader modules, descriptor set layouts, pipeline layouts, and pipelines" in generic,
            "DestroyResource: eligible generic resource types changed or are incomplete",
        )
        c.require(
            "not valid for physical devices, logical devices, command pools, descriptor pools, command buffers, descriptor sets, memory, fences, or semaphores" in generic,
            "DestroyResource: excluded resource types must remain explicit",
        )
        c.require(
            "handled through `DestroyDevice`, `DestroyCommandPool`, `DestroyDescriptorPool`, `FreeDescriptorSets`, `FreeMemory`, `DestroyFence`, or `DestroySemaphore`" in generic,
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
        "DescriptorSet-to-DescriptorSetLayout associations" in lifetime
        and "immutable layout definition and the backend layout identity" in lifetime
        and "Existing sets remain valid and updateable" in lifetime
        and "no new PipelineLayout or Set may be created through the destroyed XID" in lifetime
        and "existing Set remains valid and can still be updated" in conformance
        and "`AllocateDescriptorSets` request or a `CreatePipelineLayout` request using the destroyed layout XID returns `BadValue`" in conformance
        and "spätere `UpdateDescriptorSets`-Requests für diese Sets allein wegen der ungültigen Layout-XID ablehnen" in read("spec/shaders-pipelines.md"),
        "DescriptorSetLayout lifetime: public XID destruction must preserve existing allocated sets and their update metadata",
    )
    c.require(
        "Pipeline-to-PipelineLayout dependencies" in lifetime
        and "retain its internal definition/backend identity while any live Pipeline depends on it" in lifetime
        and "Existing Pipelines remain live; no new Pipeline may be created through the destroyed XID" in lifetime
        and "Eine erfolgreich erstellte Pipeline behält eine interne Referenz" in read("spec/shaders-pipelines.md")
        and "After creating a Pipeline, destroy its ShaderModule XID" in conformance
        and "A later `CreateComputePipeline` using that destroyed ShaderModule XID returns `BadValue`" in conformance
        and "Then destroy the PipelineLayout XID while the Pipeline is live and while a submission uses only that Pipeline" in conformance
        and "public XID destruction succeeds, the Pipeline/submission remain live" in conformance
        and "direct accepted pending use blocks destruction" in conformance
        and "A later `CreateComputePipeline` using that destroyed layout XID returns `BadValue`" in conformance,
        "PipelineLayout lifetime: existing Pipelines retain their layout dependency after public XID destruction",
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
        "`DestroyCommandPool`: normative Präzedenz: exakte 16-Byte-Länge (`BadLength`)" in errors
        and "alle Kind-Command-Buffer auf `PENDING` prüfen (`INVALID_SYNCHRONIZATION_STATE`)" in errors
        and "Ablehnung ist atomar" in errors,
        "error mapping: DestroyCommandPool must define length, pending-child, and atomicity outcomes",
    )
    c.require(
        re.search(r"Device loss alone does not prevent `DestroyCommandPool`", read("spec/command-recording.md"), re.I) is not None
        and re.search(r"Device loss alone does not prevent `DestroyDescriptorPool`", read("spec/shaders-pipelines.md"), re.I) is not None
        and re.search(r"Device loss alone does not invalidate public XIDs", errors, re.I) is not None
        and re.search(r"Device loss alone does not block `DestroyCommandPool` or `DestroyDescriptorPool`", conformance, re.I) is not None,
        "device loss: logical command/descriptor pool destruction must remain available subject to lifetime guards",
    )

    # The summary matrix must not contradict the normative recorded-reference
    # rules for descriptor sets and pipeline objects.
    c.require(
        "| DescriptorPool | Atomically invalidates the pool and all child sets; non-pending `EXECUTABLE` command buffers referencing any child set become `INVALID` |" in lifetime
        and "| DescriptorSet | XID becomes invalid | Reject while pending or referenced by a `RECORDING` command buffer; on success, referencing non-pending `EXECUTABLE` command buffers become `INVALID` |" in lifetime
        and "| Pipeline | XID becomes invalid | Reject while referenced by a `RECORDING` command buffer or used by accepted work; on success, referencing non-pending `EXECUTABLE` command buffers become `INVALID` |" in lifetime
        and "| PipelineLayout | Public XID becomes invalid; retain its internal definition/backend identity while any live Pipeline depends on it | Reject while referenced by a `RECORDING` command buffer or directly used by accepted work; on success, referencing non-pending `EXECUTABLE` command buffers become `INVALID`. Existing Pipelines remain live; no new Pipeline may be created through the destroyed XID |" in lifetime,
        "resource lifetime: DescriptorPool, DescriptorSet, Pipeline, and PipelineLayout matrix rows must match recording/pending and executable-invalidation rules",
    )
    c.require(
        "`FreeDescriptorSets` atomically rejects the operation with `INVALID_SYNCHRONIZATION_STATE` if a selected Set is pending or referenced by a `RECORDING` command buffer" in conformance
        and "`DestroyResource` on a Pipeline atomically rejects recording references and accepted pending use" in conformance
        and "For a PipelineLayout, direct recording references and direct accepted pending use reject public XID destruction" in conformance
        and "a Pipeline-held internal dependency does not block public invalidation" in conformance
        and "eine Pipeline-interne Layout-Abhängigkeit blockiert die öffentliche XID-Invalidierung nicht" in errors,
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
        re.search(r"Device loss alone does not invalidate public XIDs", lifetime, re.I) is not None
        and re.search(r"`GetFenceStatus` and `DestroyDevice` remain usable after device loss", lifetime, re.I) is not None
        and re.search(r"Device loss alone does not invalidate public Device/resource XIDs", read("spec/conformance.md"), re.I) is not None,
        "device loss: public XIDs must remain available for permitted status queries and explicit cleanup",
    )
    c.require(
        re.search(r"Individual resource-specific Destroy/Free requests are not categorically forbidden after Device loss", lifetime, re.I) is not None
        and re.search(r"`FreeMemory` remains blocked while an internally live Buffer is (?:still )?bound", lifetime, re.I) is not None
        and "Individual Destroy/Free requests are not categorically rejected with `DEVICE_LOST` after Device loss" in read("spec/conformance.md"),
        "device loss: resource-specific cleanup must preserve ordinary lifetime guards and memory safety",
    )
    c.require(
        "an open `WaitForFence` registration references that exact internal fence identity" in lifetime
        and "an open `WaitSemaphores` registration for that exact internal semaphore identity" in lifetime
        and "a wait already determined to be terminal does not block destruction merely because its reply is still pending" in lifetime,
        "lifetime: fence/semaphore destroy matrix must include open waits and terminal release",
    )
    c.require(
        re.search(r"an open `WaitForFence` registration references that exact internal Fence identity", errors, re.I) is not None
        and re.search(r"an open `WaitSemaphores` registration for that exact internal Semaphore identity", errors, re.I) is not None
        and re.search(r"even if its reply has not yet been sent", errors, re.I) is not None,
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
    registry_by_opcode = {
        int(opcode): (name, kind.strip())
        for name, opcode, kind, _responsibility in re.findall(
            r"^\|\s*\x60([^\x60]+)\x60\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|",
            registry_text, re.M,
        )
    }
    matrix_by_opcode = {}
    for opcode_text, request, kind, matrix_length in rows:
        opcode = int(opcode_text)
        c.require(opcode not in matrix_by_opcode,
                  f"request matrix: duplicate subopcode {opcode}")
        matrix_by_opcode[opcode] = (request, kind.strip(), matrix_length.strip())
    c.require(len(registry_by_opcode) == 47,
              f"request registry: expected 47 assigned requests, found {len(registry_by_opcode)}")
    c.require(len(rows) == 47,
              f"request matrix: expected all 47 assigned requests, found {len(rows)}")
    c.require(set(matrix_by_opcode) == set(registry_by_opcode),
              "request matrix: subopcode set must exactly match the central request registry")
    for opcode, (request, kind, _matrix_length) in matrix_by_opcode.items():
        registered = registry_by_opcode.get(opcode)
        c.require(registered is not None and registered[0] == request,
                  f"request matrix: subopcode {opcode} name {request!r} disagrees with central registry")
        if registered is not None:
            c.require(registered[1] == kind,
                      f"request matrix: {request} kind {kind!r} disagrees with registry kind {registered[1]!r}")
    presentation_profile_requests = {
        "CreateSurface", "DestroySurface", "GetSurfaceCapabilities",
        "CreateSwapchain", "DestroySwapchain", "AcquireNextImage", "QueuePresent",
    }
    c.require(
        presentation_profile_requests <= set(registry_rows),
        "request matrix: presentation-profile layout checks must cover all seven registered presentation requests",
    )
    for _opcode, request, _kind, matrix_length in rows:
        if request in presentation_profile_requests:
            # These seven requests are checked against the presentation chapter's
            # independent profile matrix and exact request/reply layout contracts.
            continue
        if request not in formula_overrides and request not in fixed_lengths and request != "CommandBufferData":
            c.require(False,
                      f"{request}: request matrix has no fixed-length, variable-formula, or chunked-layout verifier")
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
                rf"(?:Gesamtlänge|Total length|Request(?:-Länge| length)?|Request-Größe|Request size|hat|ist|beträgt)[^\n]{{0,100}}\b{expected_bytes}\s*Bytes?\b|"
                rf"\b{expected_bytes}\s*Bytes?\b[^\n]{{0,80}}(?:Gesamtlänge|Request)",
                section, re.I,
            )
            c.require(length_evidence is not None,
                      f"{request}: normative section does not explicitly state the matrix's {expected_bytes}-byte request length")
            c.require(normalize_length_formula(matrix_length).strip("`") == str(expected_bytes),
                      f"{request}: audit matrix fixed length {matrix_length!r} disagrees with normative {expected_bytes} bytes")
        else:
            c.require(("at least 16 bytes" in section.lower() or "mindestens 16 Bytes" in section) and ("exactly 16 bytes" in section.lower() or "exakt 16 Bytes" in section),
                      "CommandBufferData: normative variable length must define 16-byte minimum and exact 16-byte ABORT")


def check_common_request_error_precedence(c: Check) -> None:
    """Cross-check shared validation order against the complete request registry."""
    wire = read("spec/wire-protocol.md")
    errors = read("spec/errors.md")
    conformance = read("spec/conformance.md")
    registry = read("registries/request-subopcodes.md")
    ordered_phases = (
        "1. Validate the X11 envelope independently of XAverius fields",
        "2. Validate the common-header fields that have invariant meanings",
        "3. Dispatch the subopcode and apply the profile gate",
        "4. For a supported request, validate its exact layout",
        "5. No rejected request may allocate variable payload storage",
    )
    positions = [wire.find(phase) for phase in ordered_phases]
    c.require(all(position >= 0 for position in positions)
              and positions == sorted(positions)
              and len(set(positions)) == len(positions),
              "common request precedence: envelope/header/dispatch/request/state phases must be explicit and ordered")
    for phrase in (
        "These checks precede subopcode dispatch, profile gating, request-specific parsing",
        "The `flags` byte at offset 5 is request-specific",
        "any bits reserved by that request must be zero",
        "a nonzero `data` or common `reserved` field takes precedence over an unsupported presentation subopcode",
        "the zero-length/envelope `BadLength` checks above still take precedence",
        "a request chapter MAY explicitly reorder checks within these later phases",
        "Such an exception MUST state the affected checks and their precedence",
        "do not bypass the common envelope/header checks",
    ):
        c.require(phrase in wire,
                  f"common request precedence: wire protocol missing {phrase!r}")
    c.require(
        "wire structure first, then field values, then XIDs in the field order" in errors
        and "framing before scalar syntax" in conformance
        and "scalar syntax before XID resolution" in conformance
        and "XID/type/ownership checks before lifecycle" in conformance,
        "common request precedence: error map and conformance matrix must preserve phase order",
    )

    rows = []
    for line in registry.splitlines():
        cells = line.split("|")
        if len(cells) < 5:
            continue
        name = cells[1].strip().strip("`")
        opcode = cells[2].strip()
        if name and opcode.isdecimal():
            rows.append((name, cells[4].strip()))
    c.require(len(rows) == 47,
              f"common request precedence: expected 47 registered requests, found {len(rows)}")
    seen: set[str] = set()
    for name, responsibility in rows:
        if name in seen:
            c.require(False, f"common request precedence: duplicate registry entry {name}")
            continue
        seen.add(name)
        link = re.search(r"\.\./spec/([^)]*\.md)", responsibility)
        c.require(link is not None,
                  f"{name}: common precedence cannot be applied without a normative chapter")
        if link:
            chapter = read("spec/" + link.group(1))
            c.require(bool(request_normative_section(chapter, name)),
                      f"{name}: common precedence registry link has no defining request section")


def check_request_specific_precedence_exceptions(c: Check) -> None:
    """Guard documented request-local orderings that refine the common baseline."""
    wire = read("spec/wire-protocol.md")
    errors = read("spec/errors.md")
    devices = read("spec/devices.md")
    memory = read("spec/memory-buffers.md")
    shaders = read("spec/shaders-pipelines.md")
    command = read("spec/command-recording.md")
    queue = read("spec/queue-submission.md")
    sync = read("spec/synchronization.md")
    presentation = read("spec/presentation.md")

    c.require(
        "The default is scalar/reserved/padding validation before XID resolution" in wire
        and "a request chapter MAY explicitly reorder checks within these later phases" in wire
        and "Such an exception MUST state the affected checks and their precedence" in wire,
        "request-specific precedence: common rule must permit only explicit later-phase refinements",
    )

    def request_section(document: str, name: str) -> str:
        match = re.search(rf"^## (?:[0-9]+(?:\.[0-9]+)* )?`{re.escape(name)}`\s*$([\s\S]*?)(?=^## |\Z)", document, re.M)
        return match.group(1) if match else ""

    # Each tuple is an intentional request-local order, not an alternate common-header rule.
    contracts = (
        ("DestroyResource", errors.split("### `DestroyResource`", 1)[1].split("\n### ", 1)[0] if "### `DestroyResource`" in errors else "",
         ("Falsche Request-Länge", "Ungültige oder nicht mehr live XID", "Ressourcentyp, der nicht für den generischen Request zugelassen ist", "Verstoß gegen die typabhängigen Recording-/Pending-Lebensdauerregeln", "Device Loss allein ist kein zusätzlicher Ablehnungsgrund", "Interne Objekte und Backend-Referenzen werden bis zur sicheren Quieszenz erhalten oder quarantänisiert")),
        ("FreeMemory", request_section(memory, "FreeMemory"),
         ("exact 16-byte request length", "resolve `device_xid`, then `memory_xid`", "validate live resource types, client ownership, and device association", "internally live Buffer remains bound", "accepted GPU access that has not reached a terminal outcome", "Device loss alone is not a blanket rejection", "retaining/quarantining the internal allocation")),
        ("CreateBuffer", request_section(memory, "CreateBuffer"),
         ("exact request length", "`size`, `usage_flags`, and `reserved", "target `buffer_xid` as a create-XID", "`device_xid` lookup", "resource type and client/device ownership", "logical-device state", "backend buffer creation")),
        ("AllocateMemory", request_section(memory, "AllocateMemory"),
         ("exact request length", "`allocation_size`, `memory_type_index`, and `reserved", "target `memory_xid` as a create-XID", "`device_xid` lookup", "resource type and client/device ownership", "logical-device state", "backend allocation")),
        ("CreateDescriptorSetLayout", shaders.split("## 6.2 Descriptor Set Layout", 1)[1].split(chr(10) + "## ", 1)[0] if "## 6.2 Descriptor Set Layout" in shaders else "",
         ("exact count-consistent request length", "flags, binding records, counts, unique binding numbers", "target `descriptor_set_layout_xid` as a create-XID", "`device_xid` lookup", "resource type and client/device ownership", "logical-device state", "descriptor-count/device-limit checks", "backend allocation")),
        ("CreateDescriptorPool", shaders.split("## 6.3 Descriptor Pool", 1)[1].split(chr(10) + "## ", 1)[0] if "## 6.3 Descriptor Pool" in shaders else "",
         ("exakte count-konsistente Request-Länge", "positive Counts, doppelte Pool-Size-Typen", "Ziel-Pool-XID als Create-XID", "Device-XID (`BadValue` bei unbekannter/nicht-live XID)", "Ressourcentyp und Client-/Device-Ownership", "Device-Zustand", "Backend-Allokation")),
        ("ShaderModuleData", shaders.split("## 6.1 Shader Modules", 1)[1].split(chr(10) + "## ", 1)[0] if "## 6.1 Shader Modules" in shaders else "",
         ("exact total length `20 + pad4(data_length)`", "request-specific flag combination", "for `CREATE`, validate `shader_module_xid` as a create-XID", "resolve `device_xid`", "resource type and client/device ownership", "logical-device state", "upload-assembly state and chunk-size/aggregate-size limits", "on `FINAL`, validate the assembled SPIR-V")), 
        ("CreatePipelineLayout", request_section(shaders, "CreatePipelineLayout"),
         ("exakte, count-konsistente Wire-Länge", "feldlokale Range-Syntax", "Ziel-XID (`BadIDChoice`)", "Device- und Set-Layout-XIDs in Wire-Reihenfolge", "Ressourcentyp, Ownership und Cross-Device-Zuordnung", "Device-Zustand", "geräteabhängige Limits und Vulkan-Kompatibilität", "Backend-Erstellung")), 
        ("CreateComputePipeline", shaders.split("## 6.8 Compute Pipeline", 1)[1].split(chr(10) + "## ", 1)[0] if "## 6.8 Compute Pipeline" in shaders else "",
         ("exakte Wire-Länge", "`entry_point_length > 0`", "Ziel-Pipeline-XID (`BadIDChoice`)", "Device-, Pipeline-Layout- und Shader-Module-XIDs in Wire-Reihenfolge", "Ressourcentyp, Ownership und Cross-Device-Zuordnung", "Device-Zustand", "Backend-Pipeline-Erstellung")),
        ("CreateDefaultDevice", request_section(read("spec/devices.md"), "CreateDefaultDevice"),
         ("validate the exact/formula-based request length using checked arithmetic",
          "validate `queue_count`, the reserved field, and every priority",
          "validate the target `device_xid` as a create-XID",
          "require successful XGE 1.0-or-later negotiation",
          "select a suitable physical device and compute-capable queue family")),
        ("GetPhysicalDeviceProperty", request_section(devices, "GetPhysicalDeviceProperty"),
         ("exact 16-byte request length (`BadLength`)",
          "resolve the Physical-Device XID (`BadValue` if unknown or non-live)",
          "validate that the live resource is a Physical Device (`BadMatch` otherwise)",
          "validate `property_atom` as a server-known X11 Atom (`BadAtom` if invalid)",
          "look up the Atom name in the XAverius property registry")),
        ("BindBufferMemory", request_section(memory, "BindBufferMemory"),
         ("exact wire length", "resolve device, buffer, and memory XIDs in wire order",
          "resource type, client/device ownership", "device state", "binding-specific checks")),
        ("UpdateDescriptorSets", request_section(shaders, "UpdateDescriptorSets"),
         ("Exakte Gesamtlänge `20 + 36 * write_count`", "Feldlokale Syntaxprüfung aller Writes",
          "Auflösung aller XIDs in Wire-Reihenfolge", "Validierung der aufgelösten Ressourcen",
          "Device-Verfügbarkeit", "Prüfung aller Writes auf Layout-/Binding-/Array-Slot-/Descriptor-Typ-Kompatibilität",
          "Prüfung aller betroffenen Sets auf bereits angenommene GPU-Arbeit",
          "Atomarer Commit und Rollback")),
        ("CommandBufferData", request_section(command, "CommandBufferData"),
         ("wire-structure errors take precedence over field errors",
          "field errors take precedence over target/pool/entry XID errors",
          "target XID is checked before the pool XID")),
        ("QueueSubmit", request_section(queue, "QueueSubmit"),
         ("incorrect total length", "syntactic fields are checked",
          "required XIDs are resolved in wire order", "resource type, client/device ownership",
          "unavailable or lost device takes precedence over mutable submission state")),
        ("WaitSemaphores", request_section(sync, "WaitSemaphores"),
         ("length and checked arithmetic", "semaphore_count != 0",
          "resolve the device XID and then semaphore XIDs", "check device state",
          "verify that all semaphores are timeline semaphores")),
        ("SignalSemaphore", request_section(sync, "SignalSemaphore"),
         ("exact total length of 24 bytes", "resolve the device XID, then the semaphore XID",
          "check resource type, client/device ownership", "check device state",
          "check timeline type and signal-value/reservation consistency")),
        ("presentation requests", presentation.split("## 5.3 Request validation, status precedence, and atomic acceptance", 1)[-1].split("\n## ", 1)[0],
         ("wire length and checked arithmetic", "scalar/reserved-field validation",
          "XID resolution in the defined order", "type and ownership validation",
          "Device availability", "immutable request constraints",
          "lifecycle/capability status", "mutable state and synchronization eligibility")),
    )
    for name, document, phrases in contracts:
        positions = [document.find(phrase) for phrase in phrases]
        c.require(all(position >= 0 for position in positions)
                  and positions == sorted(positions)
                  and len(set(positions)) == len(positions),
                  f"{name}: documented validation phases must be present and ordered")

    # Global create-XID precedence is distinct from input-XID lookup.
    create_rules = (
        "The target XID of a create request is not an input XID",
        "An invalid or occupied target XID therefore results in `BadIDChoice`",
        "The first invalid XID determines the reported resource error",
    )
    for phrase in create_rules:
        c.require(phrase in errors,
                  f"create-XID precedence: missing central rule {phrase!r}")


def check_request_limit_contract(c: Check) -> None:
    """Guard ordinary X11 request limits and the incompatible BIG-REQUESTS header."""
    wire = read("spec/wire-protocol.md")
    conformance = read("spec/conformance.md")
    c.require(
        "BIG-REQUESTS is not supported in v0.1" in wire
        and "X11 header `length` field is zero" in wire
        and "reject a XAverius request" in wire
        and "before interpreting bytes at offset 4 as the XAverius subopcode" in wire,
        "request framing: BIG-REQUESTS length must be rejected before common-header parsing",
    )
    c.require(
        "an expected length greater than 262140 bytes" in wire
        and "before payload allocation, XID resolution, or state changes" in wire
        and "the maximum length applies per request" in wire,
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


def _github_heading_slug(heading: str) -> str:
    """Approximate GitHub's heading slug rules using only the standard library."""
    heading = re.sub(r"!?(\[([^\]]*)\])\([^)]*\)", r"\2", heading)
    heading = re.sub(r"<[^>]+>", "", heading)
    heading = re.sub(r"[\x60*~]", "", heading).casefold()
    chars = []
    for char in heading:
        category = unicodedata.category(char)
        if char.isspace():
            chars.append("-")
        elif char in ("-", "_") or category[0] in ("L", "N"):
            chars.append(char)
    slug = re.sub(r"-+", "-", "".join(chars)).strip("-")
    return slug


def check_local_markdown_links(c: Check) -> None:
    """Reject broken relative Markdown paths and heading fragments."""
    link_pattern = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
    heading_pattern = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.M)
    explicit_id_pattern = re.compile(r"<(?:a|[^>]+)\b[^>]*\bid=[\"']([^\"']+)[\"']", re.I)
    documents = sorted(
        path for path in ROOT.rglob("*.md")
        if ".git" not in path.parts and "node_modules" not in path.parts
    )
    root = ROOT.resolve()
    for source in documents:
        text = source.read_text(encoding="utf-8")
        anchors: set[str] = set(explicit_id_pattern.findall(text))
        slug_counts: dict[str, int] = {}
        for heading in heading_pattern.findall(text):
            base = _github_heading_slug(heading)
            if not base:
                continue
            count = slug_counts.get(base, 0)
            anchors.add(base if count == 0 else f"{base}-{count}")
            slug_counts[base] = count + 1
        for match in link_pattern.finditer(text):
            target = match.group(1)
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc:
                continue
            decoded_path = unquote(parsed.path)
            candidate = (source.parent / decoded_path).resolve() if decoded_path else source.resolve()
            line = text.count("\n", 0, match.start()) + 1
            try:
                candidate.relative_to(root)
            except ValueError:
                c.require(False, f"markdown link escapes repository: {source.relative_to(ROOT)} -> {target}")
                continue
            c.require(
                candidate.exists(),
                f"broken local Markdown link: {source.relative_to(ROOT)}:{line} -> {target}",
            )
            if candidate.exists() and parsed.fragment and candidate.suffix.lower() == ".md":
                target_text = candidate.read_text(encoding="utf-8")
                target_anchors: set[str] = set(explicit_id_pattern.findall(target_text))
                target_slug_counts: dict[str, int] = {}
                for heading in heading_pattern.findall(target_text):
                    base = _github_heading_slug(heading)
                    if not base:
                        continue
                    count = target_slug_counts.get(base, 0)
                    target_anchors.add(base if count == 0 else f"{base}-{count}")
                    target_slug_counts[base] = count + 1
                fragment = unquote(parsed.fragment)
                c.require(
                    fragment in target_anchors,
                    f"broken Markdown anchor: {source.relative_to(ROOT)}:{line} -> {target}",
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
    # Keep user-facing inventory summaries in sync with the actual registry. These
    # labels are easy to overlook when a profile adds append-only request IDs.
    readme = read("README.md")
    c.require("47 assigned request subopcodes" in readme and "compute baseline 1–40 and presentation-profile-only 41–47" in readme,
              "README: request registry summary must describe all 47 assignments and the profile boundary")
    registry_readme = read("registries/README.md")
    c.require("47 requests assigned: compute baseline 1–40; presentation-profile-only 41–47" in registry_readme,
              "registries/README.md: request inventory summary must match the central 47-request registry")
    c.require("Values 1–4 are assigned for the compute baseline; value 5 is presentation-profile-only" in registry_readme,
              "registries/README.md: command-entry summary must include presentation-only entry 5")
    audit_text = read("spec/request-audit.md")
    c.require("all 47 assigned request contracts" in audit_text and
              "compute baseline 1–40 and presentation-profile-only 41–47" in audit_text,
              "request audit: checker summary must describe the full 47-request inventory")
    c.require("matrix remains 40 rows" not in audit_text and
              "central 40-request registry" not in audit_text and
              "cross-checks the 40-entry request matrix" not in audit_text,
              "request audit: obsolete 40-request inventory summaries must be removed")
    opcodes = [opcode for _name, opcode, _kind in registry_rows]
    names = [name for name, _opcode, _kind in registry_rows]
    c.require(len(registry_rows) == 47,
              f"request registry: expected all 47 assigned requests, found {len(registry_rows)}")
    c.require(len(set(opcodes)) == len(opcodes), "request registry contains duplicate subopcode values")
    c.require(len(set(names)) == len(names), "request registry contains duplicate request names")
    c.require(set(opcodes) == set(range(1, 48)),
              "request registry must contain every assigned ID 1–47 exactly once; 0 is reserved")
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
    c.require(len(registry) == 47,
              f"request registry: expected all 47 assigned requests, found {len(registry)}")
    c.require(len(matrix_rows) == 47,
              f"request audit matrix: expected all 47 assigned rows, found {len(matrix_rows)}")
    c.require(set(matrix_rows) == set(registry),
              "request audit matrix and central registry must contain exactly the same assigned subopcodes")
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
            (r"zero or more \x60PHYSICALDEVICEINFO\x60 records", "variable PHYSICALDEVICEINFO records"),
            (r"reply\.length = sum of all record lengths / 4", "record-sum reply.length formula"),
            (r"Fixed record portion: 32 bytes", "32-byte fixed record prefix"),
            (r"32 \+ \(\(device_name_length \+ 3\) & ~3\)", "padded device-name record formula"),
            (r"\|\s*28\s*\|\s*CARD16\s*\|\s*\x60device_name_length\x60\s*\|", "device-name length field"),
            (r"\|\s*30\s*\|\s*CARD16\s*\|\s*\x60reserved = 0\x60\s*\|", "record reserved field"),
            (r"Padding MUST be zero", "zero record padding"),
            (r"\|\s*0\s*\|\s*XID\s*\|\s*\x60physical_device_xid\x60\s*\|", "physical-device XID at record offset 0"),
            (r"\|\s*4\s*\|\s*CARD32\s*\|\s*\x60device_type\x60\s*\|", "device type at record offset 4"),
            (r"\|\s*8\s*\|\s*CARD32\s*\|\s*\x60vendor_id\x60\s*\|", "vendor ID at record offset 8"),
            (r"\|\s*12\s*\|\s*CARD32\s*\|\s*\x60device_id\x60\s*\|", "device ID at record offset 12"),
            (r"\|\s*16\s*\|\s*CARD32\s*\|\s*\x60api_version\x60\s*\|", "API version at record offset 16"),
            (r"\|\s*20\s*\|\s*CARD32\s*\|\s*\x60driver_version\x60\s*\|", "driver version at record offset 20"),
            (r"\|\s*24\s*\|\s*CARD32\s*\|\s*\x60compute_queue_family_count\x60\s*\|", "compute queue count at record offset 24"),
            (r"\|\s*32\s*\|\s*BYTE\[\]\s*\|\s*UTF-8 device name", "device name payload at record offset 32"),
        ]),
        "GetPhysicalDeviceProperty": ("devices", [
            (r"\|\s*8\s*\|\s*CARD32\s*\|\s*\x60status\x60\s*\|", "status at offset 8"),
            (r"\|\s*12\s*\|\s*CARD32\s*\|\s*\x60property_type\x60\s*\|", "property type at offset 12"),
            (r"\|\s*16\s*\|\s*CARD32\s*\|\s*\x60value_length\x60 in Bytes\s*\|", "value length at offset 16"),
            (r"\|\s*20–31\s*\|\s*BYTE\[12\]\s*\|\s*Reserved; MUST be zero\s*\|", "reserved bytes 20–31"),
            (r"reply\.length = ceil\(value_length / 4\)", "variable value payload formula"),
            (r"status other than \x60SUCCESS\x60.*?reply\.length = 0", "empty failure-status reply"),
            (r"For a status other than \x60SUCCESS\x60, \x60property_type\x60 and \x60value_length\x60 MUST be zero", "property failure fields zero"),
            (r"On success", "property success payload rule"),
        ]),
        "GetPhysicalDeviceQueueFamilyProperties": ("devices", [
            (r"12-byte \x60QUEUEFAMILYINFO\x60 records", "12-byte queue-family records"),
            (r"reply\.length = 3 \* queue_family_count", "queue-family reply.length formula"),
            (r"\|\s*0\s*\|\s*CARD32\s*\|\s*\x60queue_flags\x60\s*\|", "queue flags at record offset 0"),
            (r"\|\s*4\s*\|\s*CARD32\s*\|\s*\x60queue_count\x60\s*\|", "queue count at record offset 4"),
            (r"\|\s*8\s*\|\s*CARD32\s*\|\s*\x60reserved = 0\x60\s*\|", "record reserved field"),
            (r"payload length MUST be divisible by 12", "payload divisible by record size"),
        ]),
        "GetPhysicalDeviceMemoryProperties": ("memory", [
            (r"\x60CARD32 memory_type_count\x60", "memory-type count"),
            (r"\x60CARD32 memory_heap_count\x60", "memory-heap count"),
            (r"\x60MEMORYTYPEINFO\x60 is 8 bytes", "8-byte memory-type records"),
            (r"\x60MEMORYHEAPINFO\x60 is 16 bytes", "16-byte memory-heap records"),
            (r"reply\.length = 4 \+ 2 \* memory_type_count \+ 4 \* memory_heap_count", "memory-properties reply.length formula"),
            (r"\x60CARD32 reserved = 0\x60", "reserved count/record fields"),
            (r"\x60CARD32 property_flags\x60.*?\x60CARD32 heap_index\x60", "memory-type record fields"),
            (r"\x60CARD64 size\x60.*?\x60CARD32 heap_flags\x60.*?\x60CARD32 reserved = 0\x60", "memory-heap record fields"),
            (r"At most 32 memory types and 16 memory heaps are supported", "bounded record counts"),
        ]),
        "GetBufferMemoryRequirements": ("memory", [
            (r"\|\s*8\s*\|\s*CARD64\s*\|\s*\x60size\x60\s*\|", "size at reply offset 8"),
            (r"\|\s*16\s*\|\s*CARD64\s*\|\s*\x60alignment\x60\s*\|", "alignment at reply offset 16"),
            (r"\|\s*24\s*\|\s*CARD32\s*\|\s*\x60memory_type_bits\x60\s*\|", "memory type bits at reply offset 24"),
            (r"\|\s*28\s*\|\s*CARD32\s*\|\s*\x60reserved = 0\x60\s*\|", "reserved word at reply offset 28"),
            (r"reply payload length is zero", "fixed 32-byte reply"),
            (r"Size and alignment MUST be positive", "positive size and alignment"),
            (r"bits beyond `memory_type_count` MUST be zero", "memory-type mask bounded by type count"),
            (r"MUST return at least one supported memory-type bit", "nonzero supported memory-type mask"),
        ]),
        "WriteBuffer": ("memory", [
            (r"Total length:\s*\n+\x60?28 \+ \(\(uint64\(data_length\) \+ 3\) & ~uint64\(3\)\)", "request payload length formula"),
            (r"Byte-Payload", "byte payload"),
            (r"zero padding through the next four-byte boundary", "request zero padding"),
            (r"empty standard 32-byte X11 reply", "empty standard reply on success"),
            (r"A failed upload", "failure does not claim successful upload"),
        ]),
        "ReadBuffer": ("memory", [
            (r"Total length: 28 bytes", "fixed 28-byte request"),
            (r"After the 32-byte header, the reply contains exactly .*? from offset 32", "payload begins at reply offset 32"),
            (r"reply\.length = floor\(\(uint64\(data_length\) \+ 3\) / 4\)", "readback reply.length formula"),
            (r"zero padding to a four-byte boundary", "readback zero padding"),
        ]),
        "GetSemaphoreCounterValue": ("sync", [
            (r"Offset 8: \x60CARD64 counter_value\x60", "counter value at offset 8"),
            (r"(?:Offset 16–31: reserved, zero|Offset 16–31: reserviert, null)", "reserved reply bytes"),
            (r"Reply payload length: zero", "fixed 32-byte reply"),
        ]),
        "WaitSemaphores": ("sync", [
            (r"total length: \x6028 \+ 12 \* semaphore_count\x60 bytes", "variable request length formula"),
            (r"(?:Array aus 12-Byte-Entries|array of 12-byte entries)", "12-byte wait entries"),
            (r"(?:Jeder Entry enthält Semaphore-XID und \x60CARD64 wait_value\x60|Each entry contains a semaphore XID and \x60CARD64 wait_value\x60)", "wait entry fields"),
            (r"(?:Der Reply ist genau 32 Bytes lang|The reply is exactly 32 bytes long)", "fixed 32-byte reply"),
            (r"(?:Offset 8 enthält einen \x60CARD32 status\x60|Offset 8 contains a \x60CARD32 status\x60)", "wait status field"),
            (r"Offsets 12–31 are zero and \x60reply\.length = 0\x60", "reserved bytes and zero payload"),
            (r"(?:\x60SUCCESS = 0\x60 oder \x60TIMEOUT = 1\x60|\x60SUCCESS = 0\x60 or \x60TIMEOUT = 1\x60)", "wait reply status values"),
        ]),
        "GetFenceStatus": ("sync", [
            (r"Reply: 32 bytes", "fixed 32-byte reply"),
            (r"Byte 0: standard X11 reply", "response_type byte"),
            (r"(?:Byte 1: Fence-Status|Byte 1: fence status)", "status byte"),
            (r"Offsets 2–3: standard X11 reply sequence number", "sequence field"),
            (r"Offsets 4–7: standard \x60reply\.length = 0\x60", "zero reply.length"),
            (r"(?:Offsets 8–31: reserved for XAverius, zero|Offsets 8–31: XAverius-reserviert, null)", "reserved reply bytes"),
        ]),
        "WaitForFence": ("sync", [
            (r"Request: exactly 24 bytes", "fixed request length"),
            (r"Offset 8 (?:contains a|enthält einen) \x60CARD32 status\x60", "wait status field"),
            (r"(?:Offsets 12–31 sind null und \x60reply\.length = 0\x60|offsets 12–31 are zero and \x60reply\.length = 0\x60)", "reserved bytes and zero payload"),
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
    c.require(re.search(r"Replies use the standard 32-byte X11 reply header", wire, re.I) is not None,
              "reply layout: standard 32-byte X11 reply header")
    c.require(re.search(r"\x60reply\.length\x60 gives the number of four-byte units following this header", wire, re.I) is not None,
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
        elif kind in ("GetFenceStatus", "WaitForFence", "WaitForFence-success", "WaitForFence-timeout", "WaitForFence-execution-failed", "WaitForFence-device-lost", "WaitForFence-device-destroyed", "GetSemaphoreCounterValue", "WaitSemaphores-success"):
            c.require(len(wire) == 32 and declared == 0, f"{name}: fixed reply must be exactly 32 bytes with length zero")
            if kind == "GetFenceStatus":
                c.require(wire[1] in (0, 1, 2, 3), f"{name}: invalid fence status")
            elif kind.startswith("WaitForFence"):
                status = int.from_bytes(wire[8:12], order)
                c.require(status in (0, 1, 2, 3, 4), f"{name}: invalid WaitForFence status")
                expected_status = {
                    "WaitForFence-success": 0,
                    "WaitForFence-timeout": 1,
                    "WaitForFence-execution-failed": 2,
                    "WaitForFence-device-lost": 3,
                    "WaitForFence-device-destroyed": 4,
                }.get(kind)
                if expected_status is not None:
                    c.require(status == expected_status, f"{name}: status does not match vector kind")
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
                elif rule == "fixed-reply-size": invalid = kind in ("GetFenceStatus", "WaitSemaphores-timeout", "WaitForFence", "GetSemaphoreCounterValue", "GetBufferMemoryRequirements") and (len(wire) != 32 or declared != 0)
                elif rule == "fence-status": invalid = kind == "GetFenceStatus" and wire[1] not in (0, 1, 2, 3)
                elif rule == "wait-status": invalid = kind == "WaitSemaphores-timeout" and int.from_bytes(wire[8:12], order) not in (0, 1)
                elif rule == "wait-status-match": invalid = kind in ("WaitSemaphores-timeout", "WaitSemaphores-success") and int.from_bytes(wire[8:12], order) != (1 if kind.endswith("timeout") else 0)
                elif rule == "wait-for-fence-status": invalid = kind == "WaitForFence" and int.from_bytes(wire[8:12], order) not in (0, 1, 2, 3, 4)
                elif rule == "wait-for-fence-status-match":
                    expected_status = {
                        "WaitForFence-success": 0,
                        "WaitForFence-timeout": 1,
                        "WaitForFence-execution-failed": 2,
                        "WaitForFence-device-lost": 3,
                        "WaitForFence-device-destroyed": 4,
                    }.get(kind)
                    invalid = expected_status is not None and int.from_bytes(wire[8:12], order) != expected_status
                elif rule == "property-success-status": invalid = kind == "GetPhysicalDeviceProperty-success" and int.from_bytes(wire[8:12], order) != 0
                elif rule == "property-failure-status": invalid = kind in ("GetPhysicalDeviceProperty-not-supported", "GetPhysicalDeviceProperty-not-available") and int.from_bytes(wire[8:12], order) != (1 if kind.endswith("not-supported") else 2)
                elif rule == "buffer-requirements-size-positive": invalid = kind == "GetBufferMemoryRequirements" and int.from_bytes(wire[8:16], order) == 0
                elif rule == "buffer-requirements-alignment-positive": invalid = kind == "GetBufferMemoryRequirements" and int.from_bytes(wire[16:24], order) == 0
                elif rule == "buffer-requirements-memory-type-bits-nonzero": invalid = kind == "GetBufferMemoryRequirements" and int.from_bytes(wire[24:28], order) == 0
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
        (1, "CARD8", r"extension.*(?:dynamically assigned XAverius major opcode|dynamisch zugewiesener XAverius-Major-Opcode)"),
        (2, "CARD16", r"(?:X11 event sequence number|X11-Event-Sequenznummer)"),
        (4, "CARD32", r"XGE.*length"),
        (8, "CARD16", r"evtype.*(?:Event-Type-ID|event type ID)"),
    ]
    for offset, typ, pattern in header_fields:
        c.require(re.search(rf"^\|\s*{offset}\s*\|\s*{typ}\s*\|[^\n]*{pattern}", header, re.M | re.I) is not None,
                  f"XGE header: missing or changed {typ} field at offset {offset}")
    c.require(re.search(r"^\|\s*10–31\s*\|\s*—\s*\|[^|]*(?:zero|null)", header, re.M | re.I) is not None,
              "XGE header: reserved bytes 10–31 must be zero")
    c.require(re.search(r"The total length is exactly.*32.*4.*length", header, re.I) is not None,
              "XGE header: exact total-size formula missing")
    c.require(re.search(r"connection byte order applies to both header and payload", header, re.I) is not None,
              "XGE header: connection byte order must apply to header and payload")
    c.require(re.search(r"GenericEvent\s*(?:=\s*35|\(35\))", wire) is not None and
              re.search(r"XAverius has no separately assigned server-side XGE event base", wire, re.I) is not None,
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
        declaration = re.search(r"(?:Total length|Gesamtlänge):\s*(\d+)\s*(?:bytes|Bytes);\s*XGE.*length\s*=\s*(\d+)", body)
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
        # Check semantic field names at their exact offsets, not merely that
        # the names occur somewhere in the section.
        field_names = {
            "ASYNC_ERROR": [(32, r"Device XID|Device-XID"), (36, r"error_code"),
                            (40, r"origin"), (44, r"submission_token"),
                            (52, r"affected resource XID"), (56, r"reserved")],
            "DEVICE_LOST": [(32, r"Device-XID"), (36, r"reason_code"),
                            (40, r"device_generation")],
            "DEVICE_STATUS_CHANGED": [(32, r"Physical-Device XID|Physical-Device-XID"),
                                      (36, r"new_status"), (40, r"reason_code"),
                                      (44, r"reserved")],
            "DEVICE_MEMORY_PRESSURE": [(32, r"Device-XID"), (36, r"heap_index"),
                                       (40, r"pressure_level"), (44, r"reserved")],
            "DEVICE_IDLE": [(32, r"Device-XID"), (36, r"idle_reason"),
                            (40, r"device_generation")],
            "SUBMISSION_COMPLETE": [(32, r"Device-XID"), (36, r"queue_family_index"),
                                    (40, r"queue_index"), (44, r"reserved"),
                                    (48, r"submission_token")],
            "SUBMISSION_FAILED": [(32, r"Device-XID"), (36, r"queue_family_index"),
                                  (40, r"queue_index"), (44, r"failure_class"),
                                  (48, r"submission_token")],
        }[name]
        c.require(len(parsed) == len(field_names),
                  f"{name}: field count differs from the named ABI")
        for (offset, pattern), record in zip(field_names, parsed):
            actual_offset, _size, _typ, label = record
            c.require(actual_offset == offset and re.search(pattern, label, re.I) is not None,
                      f"{name}: field at offset {offset} must be named as {pattern!r}, got offset {actual_offset} label {label!r}")
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

    select_marker = "## Event Selection: " + chr(96) + "SelectEvents" + chr(96)
    select_start = events.find(select_marker)
    c.require(select_start >= 0, "events.md: missing SelectEvents ABI section")
    select_body = events[select_start + len(select_marker):] if select_start >= 0 else ""
    c.require(re.search(r"fixed total length of 32 bytes", select_body, re.I) is not None,
              "SelectEvents: request must be exactly 32 bytes")
    c.require(re.search(r"Common-header `flags` field at offset 5 MUST be zero", select_body, re.I) is not None,
              "SelectEvents: common request flags at offset 5 must be zero")
    c.require(re.search(r"Common-header field at offset 6 MUST also be zero", select_body, re.I) is not None,
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
        (r"atomically replaces the existing mask", "atomic mask replacement"),
        (r"On any error, the previous selection remains unchanged", "failed request preserves prior mask"),
        (r"`ASYNC_ERROR`.*`DEVICE_LOST`.*unmaskable", "unmaskable events"),
        (r"successfully execute\s+" + chr(96) + r"?GEQueryVersion" + chr(96) + r"?", "XGE version negotiation prerequisite"),
        (r"Without negotiated XGE support.*BadMatch", "pre-negotiation rejection"),
    ]:
        c.require(re.search(pattern, select_body + "\n" + events, re.I | re.S) is not None,
                  f"SelectEvents/XGE: missing {label}")
    c.require(re.search(r"CreateDevice.*CreateDefaultDevice.*BadMatch", devices, re.S) is not None,
              "device creation: XGE negotiation prerequisite and BadMatch must be explicit")
    c.require(
        "`XAverius.timelineSemaphore`" in read("registries/physical-device-properties.md")
        and "`XAverius.timelineSemaphore = 1`" in devices
        and "MUST enable this feature on every successfully created logical Device" in devices
        and "Vulkan `timelineSemaphore` is a mandatory v0.1 baseline capability" in read("registries/feature-ids.md")
        and "VK_KHR_timeline_semaphore` internally" in read("registries/device-extensions.md")
        and "except for protocol-required backend dependencies expressly identified by the v0.1 baseline" in read("registries/device-extensions.md")
        and "XAverius.timelineSemaphore = 0" in read("spec/errors.md")
        and "`CreateDevice` with value 0 returns `BadMatch`" in conformance
        and "every successful logical Device enables the feature" in conformance,
        "device creation: mandatory timeline semaphore baseline, property query, and feature enablement must agree",
    )
    c.require(re.search(r"SelectEvents.*XGE.*framed|XGE.*SelectEvents", conformance, re.I | re.S) is not None,
              "conformance checklist: must cover SelectEvents/XGE ABI")

    # Semantic negative cases that cannot be inferred from field offsets alone.
    c.require("For `origin = ORIGIN_QUEUE_SUBMIT`, `submission_token` MUST be nonzero" in conformance and
              "`ASYNC_ERROR`" in events and
              re.search(r"For `origin = ORIGIN_QUEUE_SUBMIT`, `submission_token` MUST therefore be non-zero", events) is not None and
              re.search(r"a non-zero token MUST never identify a rejected `QueueSubmit` request", events) is not None,
              "XGE ASYNC_ERROR: origin/token relationship and rejected-submit exclusion must be normative and tested")
    c.require("Unknown `origin` values" in conformance and
              "`reserved = 0`" in doc_sections.get("ASYNC_ERROR", "") and
              re.search(r"reserved = 0", doc_sections.get("ASYNC_ERROR", "")) is not None,
              "XGE ASYNC_ERROR: invalid origin and reserved-field negative cases must be covered")
    c.require("MUST have `resource_xid = 0`" in conformance and
              "`resource_xid` MUST be zero" in read("spec/events.md") and
              "`resource_xid = 0` is serialized" in read("spec/resource-lifetime.md") and
              re.search(r"resource XID that has since been destroyed or reused MUST NOT be emitted as `resource_xid`", read("spec/resource-lifetime.md")) is not None,
              "XGE ASYNC_ERROR: destroyed/reused resource XIDs must be scrubbed instead of retargeted")
    c.require("unknown mask bits" in conformance and
              "incorrect zero values" in conformance and
              "Every such error leaves the previous mask unchanged" in conformance and
              "Unknown scope values" in select_body and
              "On any error, the previous selection remains unchanged" in select_body,
              "SelectEvents: malformed scope/mask/unused fields must reject atomically")
    c.require("unrequested queue combination" in conformance and
              "foreign ownership" in conformance and
              "A nonexistent queue within a valid device results in `BadValue`" in select_body,
              "SelectEvents: queue lookup and ownership failures must be distinguished")
    c.require("unmaskable `DEVICE_LOST` and `ASYNC_ERROR` events" in conformance and
              "resource_xid" in conformance and
              "After successful processing of `DestroyDevice`, the server MUST NOT generate or deliver new XAverius events" in read("spec/resource-lifetime.md"),
              "XGE event delivery: DestroyDevice suppression must cover all event XID fields")
    c.require("shared serialized linearization point" in conformance and
              "one shared serialized server state" in events and
              "A later backend callback MUST NOT retroactively change this decision" in events,
              "XGE event delivery: SelectEvents/DestroyDevice/completion race must be serialized")
    c.require("at most one of `SUBMISSION_COMPLETE` and `SUBMISSION_FAILED`" in conformance and
              "For each accepted submission, `SUBMISSION_COMPLETE` and `SUBMISSION_FAILED` must never both be delivered" in events,
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
                        candidate[0] == 35 and 128 <= candidate[1] <= 255 and
                        len(candidate) == 32 + 4 * struct.unpack_from(endian + "I", candidate, 4)[0] and
                        struct.unpack_from(endian + "H", candidate, 8)[0] == event_id and
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
            bad_extension = bytearray(frame)
            bad_extension[1] = 0x7f
            c.require(not valid_xge(bytes(bad_extension)), f"XGE negative ({name}/{order_name}): invalid extension opcode accepted")
            bad_event_type = bytearray(frame)
            struct.pack_into(endian + "H", bad_event_type, 8, (event_id + 1) % 7)
            c.require(not valid_xge(bytes(bad_event_type)), f"XGE negative ({name}/{order_name}): mismatched event type accepted")



def check_presentation_profile(c: Check) -> None:
    """Check future presentation-profile wire layouts without expanding v0.1 registries."""
    presentation = read("spec/presentation.md")
    events = read("spec/events.md")
    event_registry = read("registries/presentation-events.md")
    command_recording = read("spec/command-recording.md")
    formats = read("registries/presentation-formats.md")
    request_registry = read("registries/request-subopcodes.md")
    request_audit = read("spec/request-audit.md")
    command_registry = read("registries/command-entries.md")

    # Keep the normative presentation chapter represented in a separate profile matrix.
    # Its request IDs are assigned centrally but remain unavailable to compute-only servers.
    presentation_audit_rows = (
        "| `CreateSurface` | Void | 16 | — |",
        "| `DestroySurface` | Void | 12 | — |",
        "| `GetSurfaceCapabilities` | Reply | 16 | `64 + 8*format_pair_count + 4*present_mode_count + 8*queue_family_count` |",
        "| `CreateSwapchain` | Reply | 48 | 40 |",
        "| `DestroySwapchain` | Void | 12 | — |",
        "| `AcquireNextImage` | Reply | 32 | 44 |",
        "| `QueuePresent` | Reply | `40 + 4*wait_semaphore_count` | 36 |",
    )
    c.require("### Presentation-capable profile request/reply matrix" in request_audit,
              "request audit: presentation-capable normative chapter must have a separate profile matrix")
    for row in presentation_audit_rows:
        c.require(row in request_audit,
                  f"request audit: presentation request kind/length row missing or inconsistent: {row}")
    c.require("This profile matrix is intentionally separate from the assigned 1–40 request matrix." in request_audit,
              "request audit: profile-gated presentation rows must remain separate from compute-baseline assignments")

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
    c.require("must reject the presentation-only queue event-mask bits" in event_registry,
              "presentation events: compute-only profile must reject presentation queue mask bits")
    event_docs = dict(sections(events))
    presentation_spec = read("spec/presentation.md")
    lifetime = read("spec/resource-lifetime.md")
    c.require("This release transition may occur at most once per accepted presentation operation" in event_docs.get("IMAGE_RELEASED", "") and
              "An `IMAGE_RELEASED` event is queued exactly when" in event_docs.get("IMAGE_RELEASED", "") and
              "queue mask bit 2" in event_docs.get("IMAGE_RELEASED", ""),
              "IMAGE_RELEASED: internal release cardinality and conditional event delivery must be explicit")
    c.require("unique internal terminal outcome of each accepted presentation operation" in event_docs.get("PRESENTATION_COMPLETE", "") and
              "After `DestroyDevice` has been processed successfully, no new events" in event_docs.get("PRESENTATION_COMPLETE", "") and
              "queue mask bit 3" in event_docs.get("PRESENTATION_COMPLETE", ""),
              "PRESENTATION_COMPLETE: terminal outcome, queue mask, and DestroyDevice suppression must be explicit")
    c.require("queue mask bit 2" in event_docs.get("IMAGE_RELEASED", "") and
              "queue mask bit 3" in event_docs.get("PRESENTATION_COMPLETE", ""),
              "presentation events: queue mask must be sampled independently at each event milestone")
    c.require("both presentation milestones (presentation terminalization and image release) MUST be ordered by one shared serialized server state" in events
              and "if `SelectEvents` linearizes first, the new mask governs the later milestone" in events
              and "if `DestroyDevice` successfully linearizes first, no new event for its destroyed Device XID is queued" in events
              and "Race a successful `SelectEvents` mask replacement against each milestone in both serialized orders" in conformance,
              "presentation event delivery: SelectEvents and DestroyDevice must serialize with both independent presentation milestones")
    c.require("Accepted presentation failures set the internal terminal status" in presentation_spec and
              "Queue mask bit 3" in presentation_spec and "Queue mask bit 2" in presentation_spec,
              "presentation: internal terminal cleanup and independently masked event delivery must be explicit")
    c.require("internal terminal states and safe backend cleanup" in lifetime,
              "presentation: device teardown must preserve internal terminal cleanup when events are suppressed")
    for name in ("IMAGE_RELEASED", "PRESENTATION_COMPLETE"):
        c.require(name in event_docs, f"presentation events: missing {name} layout")
        body = event_docs.get(name, "")
        match = re.search(r"(?:Total length|Gesamtlänge):\s*(\d+)\s*bytes?;\s*XGE `length\s*=\s*(\d+)`", body)
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
        expected_names = [
            (32, r"Device-XID"), (36, r"queue_family_index"),
            (40, r"queue_index"), (44, r"Swapchain-XID"),
            (48, r"image_index"),
            (52, r"reserved" if name == "IMAGE_RELEASED" else r"status"),
            (56, r"presentation_token"),
        ]
        c.require(len(records) == len(expected_names),
                  f"{name}: field count differs from the presentation ABI")
        for (offset, pattern), record in zip(expected_names, records):
            actual_offset, _size, _typ, label = record
            c.require(actual_offset == offset and re.search(pattern, label, re.I) is not None,
                      f"{name}: field at offset {offset} must be named as {pattern!r}, got offset {actual_offset} label {label!r}")
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
        "### GetSurfaceCapabilities — Request 16 bytes; variable-length Reply",
        "### CreateSwapchain — Request 48 bytes; Reply 40 bytes",
        "### DestroySwapchain — Void, 12 bytes",
        "### AcquireNextImage — Request 32 bytes; Reply 44 bytes",
        "### QueuePresent — Request variable length; Reply 36 bytes",
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
    c.require("`QueuePresent` uses the same global state machine" in read("spec/synchronization.md") and
              "each affected semaphore is handled independently" in read("spec/synchronization.md"),
              "synchronization: presentation waits must follow binary semaphore state rules")
    c.require("already marked `UNTRUSTED` is rejected with `DEPENDENCY_FAILED`" in read("spec/errors.md"),
              "QueuePresent: untrusted binary wait must fail with DEPENDENCY_FAILED")
    c.require("8 + 2 * format_pair_count + present_mode_count + 2 * queue_family_count" in presentation,
              "GetSurfaceCapabilities: reply.length formula missing")
    c.require("exactly one record for every family returned by `GetPhysicalDeviceQueueFamilyProperties`" in presentation and
              "ordered by ascending index with no duplicates" in presentation and
              "`CARD32 queue_family_index`, `CARD32 present_supported`" in presentation,
              "GetSurfaceCapabilities: queue-family support records must have a defined, complete, ordered layout")
    c.require("Every physical queue family has exactly one ordered support record." in read("spec/conformance.md"),
              "presentation conformance: queue-family capability records must cover every family exactly once")
    c.require("Status values: 0 SUCCESS; 1 TEMPORARILY_NOT_PRESENTABLE; 2 SURFACE_LOST; 3 DEVICE_LOST" in presentation,
              "GetSurfaceCapabilities: reply status values must be explicit")
    c.require("CreateSwapchain status values are 0 SUCCESS; 1 OUT_OF_DATE; 2 SURFACE_LOST; 3 DEVICE_LOST; 4 UNSUPPORTED_CONFIGURATION; 5 ALLOCATION_FAILED" in presentation,
              "CreateSwapchain: reply status values must be explicit")
    c.require("Acquire status values are SUCCESS=0, TIMEOUT=1, NOT_READY=2, OUT_OF_DATE=3, SURFACE_LOST=4, DEVICE_LOST=5, and DEVICE_DESTROYED=6" in presentation,
              "AcquireNextImage: reply status values must be explicit")
    c.require("QueuePresent reply status values are 0 SUCCESS, 1 OUT_OF_DATE, 2 SURFACE_LOST, and 3 DEVICE_LOST" in presentation,
              "QueuePresent: reply status values must be explicit and local to the reply field")
    c.require("CreateSwapchain" in presentation and "actual_image_count" in presentation,
              "CreateSwapchain: exact image-count reply contract missing")
    c.require("actual_image_count = 0" in presentation and
              "format/color-space pair and present mode must be reported" in presentation and
              "`present_supported` is 1 if and only if at least one queue-family record" in presentation,
              "CreateSwapchain/GetSurfaceCapabilities: capability validation and failure reply fields must be explicit")
    presentation_reply_tests = read("tests/test_presentation_reply_vectors.py")
    c.require('validate_presentation_reply(kind, wire, order)' in presentation_reply_tests and
              'for kind, statuses, total, reply_words in cases:' in presentation_reply_tests,
              "presentation reply tests must pass every documented status through the validator in both byte orders")
    c.require("family_indices != list(range(families))" in presentation_reply_tests and
              "successful capabilities reply has zero queue families" in presentation_reply_tests and
              "aggregate present_supported does not match queue-family records" in presentation_reply_tests and
              "successful capabilities reply has zero current extent" in presentation_reply_tests and
              "successful capabilities reply has invalid extent bounds" in presentation_reply_tests and
              "successful capabilities reply has invalid image-count bounds" in presentation_reply_tests and
              "successful CreateSwapchain has zero image count" in presentation_reply_tests and
              "CreateSwapchain image count does not match request" in presentation_reply_tests and
              "expected_image_count=2" in presentation_reply_tests,
              "presentation reply tests must check family ordering, aggregate support, and request-matched success payloads")

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
        "resolve `device_xid` and then `surface_xid` in request-field order; an unknown/non-live XID is `BadValue`",
        "resolve `device_xid` and then `surface_xid` in request-field order",
        "resolve `device_xid`, then `swapchain_xid`, then each wait-semaphore XID in array order",
        "A Surface is not Device-owned, so querying the same live Surface with different owned Devices is valid",
        "nonexistent queue-family/index or image index outside the Swapchain is `BadValue`",
        "`CreateSwapchain`: invalid/already allocated target `swapchain_xid` is `BadIDChoice`",
        "`DestroySwapchain`: unknown/non-live Swapchain XID is `BadValue`",
        "`AcquireNextImage`: unknown/non-live Device or Swapchain XID is `BadValue`",
        "resolve `device_xid`, then `swapchain_xid`, then each wait-semaphore XID in array order; an unknown/non-live XID is `BadValue`",
        "An acquired-but-idle image alone does not block destruction.",
        "Any rejected `QueuePresent` leaves the image state as it was immediately before that request, leaves wait-semaphore state unchanged, and does not reserve its presentation token.",
        "Token uniqueness is checked against previously accepted presentations and recorded atomically with acceptance.",
    )
    for contract in presentation_error_contracts:
        c.require(contract in errors,
                  f"presentation request error map: missing invariant: {contract}")
    c.require("a live `InputOnly`/otherwise non-drawable Window, is `BadMatch`" in errors
              and "live `InputOnly`/otherwise non-drawable Window with `BadMatch`" in conformance
              and "this 16-byte request has no request-specific scalar or reserved fields" in conformance
              and "`CreateSurface`, `DestroySurface`, and `DestroySwapchain` have no request-specific scalar or reserved fields" in errors,
              "CreateSurface: map live non-drawable Windows and do not invent scalar fields absent from its wire layout")
    c.require("Device Loss alone does not reject this logical cleanup request" in errors
              and "Device Loss alone does not invalidate the public Swapchain XID" in presentation
              and "with all blockers absent and require logical destruction to succeed" in conformance
              and "successful `DestroyDevice`: its cascade invalidates the Swapchain XID" in conformance,
              "DestroySwapchain: distinguish Device Loss cleanup from DestroyDevice cascade and preserve backend blockers")
    c.require("a queue not belonging to the Device is `BadMatch`" not in errors and
              "same live Surface may be queried with two different owned Devices" in conformance,
              "presentation error map: preserve Device-independent Surface ownership and BadValue queue-index mapping")
    c.require("a valid Device/Surface pair that cannot present returns `UNSUPPORTED_CONFIGURATION` rather than `BadMatch`" in errors
              and "valid but non-present-capable Device/Surface pair and require `UNSUPPORTED_CONFIGURATION`, not `BadMatch`" in conformance
              and "Surface is owned by the X11 connection, not by a logical Device" in presentation,
              "CreateSwapchain: a valid non-presentable Device/Surface pair is unsupported configuration, not cross-device BadMatch")
    c.require("require the Device `BadValue` first" in conformance
              and "require the Swapchain `BadValue`" in conformance
              and "require the first unknown wait in array order" in conformance,
              "presentation conformance: GetSurfaceCapabilities and QueuePresent must pin XID resolution order")
    c.require("owned by the requesting X11 client connection" in presentation and
              "a live Window owned by another X11 client, or a live `InputOnly`/otherwise non-drawable Window, is `BadMatch`" in errors and
              "a live Window owned by another X11 client or a live `InputOnly`/otherwise non-drawable Window with `BadMatch`" in conformance,
              "CreateSurface: Window identity must be client-owned and cross-client references rejected")
    c.require("resolve `device_xid`, validate the target `swapchain_xid` as a create-XID, then resolve `surface_xid`" in errors and
              "Mixed-failure `CreateSwapchain` requests validate scalar fields first" in conformance,
              "CreateSwapchain: mixed XID and capability error precedence must be explicit")
    c.require("For all seven requests, validation is atomic" in errors,
              "presentation request error map: all seven requests must share atomic failure semantics")

    c.require("For `QueuePresent`, after higher-priority XID, Device, queue/index, lifecycle, and presentation-support checks, reject reuse of a token from an earlier accepted presentation with `BadValue`; then check image state, and if it is `ACQUIRED`, validate wait semaphores in array order." in errors and
              "For each wait, `UNTRUSTED` yields `DEPENDENCY_FAILED`" in errors,
              "QueuePresent: image-state and wait-semaphore error precedence must be deterministic")


    # Cross-check deterministic mixed-failure precedence and atomic status paths
    # across the normative error map, presentation chapter, and conformance cases.
    precedence_contracts = (
        "### Normative validation precedence for the seven presentation requests",
        "Validate exact/fixed or formula-derived wire length using checked wide arithmetic.",
        "`CreateSurface` checks `surface_xid` before resolving `window_xid`",
        "`CreateSwapchain` checks `device_xid`, then target `swapchain_xid`, then `surface_xid`",
        "Device loss takes precedence over Surface loss and all later mutable-state checks.",
        "A zero token is always `BadValue`.",
        "Do not test whether a nonzero presentation token was previously accepted at this stage",
        "after higher-priority XID, Device, queue/index, lifecycle, and presentation-support checks, reject reuse of a token",
        "For a new `AcquireNextImage` evaluation, after the preceding validation stages, `DEVICE_LOST` takes precedence over `SURFACE_LOST`, which takes precedence over `OUT_OF_DATE`;",
        "validate every supplied semaphore/fence for acquisition-signal eligibility and absence of a conflicting pending acquire before polling or registering the wait",
    )
    for contract in precedence_contracts:
        c.require(contract in errors,
                  f"presentation error precedence: missing normative contract: {contract}")
    presentation_precedence_contracts = (
        "## 5.3 Request validation, status precedence, and atomic acceptance",
        "`DEVICE_LOST` takes precedence over `SURFACE_LOST`",
        "`SURFACE_LOST` takes precedence over `OUT_OF_DATE`",
        "A valid queue tuple with no presentation support is a synchronous `BadMatch` before token-reuse and image-state checks.",
        "`OUT_OF_DATE` takes precedence over `UNSUPPORTED_CONFIGURATION`",
        "Every non-success reply has `actual_image_count = 0` and leaves `swapchain_xid` unallocated.",
        "A token mentioned only in a rejected request is not reserved and may be retried.",
        "after higher-priority XID, Device, queue/index, lifecycle, and presentation-support checks, it returns `BadValue`",
        "reserve the token and every wait slot, retain all required resources, and transition the image from `ACQUIRED` to `PRESENT_PENDING`",
    )
    for contract in presentation_precedence_contracts:
        c.require(contract in presentation,
                  f"presentation status/atomicity: missing normative contract: {contract}")
    conformance_precedence_contracts = (
        "Presentation error precedence is tested with mixed-failure requests",
        "returns `DEVICE_LOST` rather than `SURFACE_LOST`",
        "returns `DEVICE_LOST` before `SURFACE_LOST`, `SURFACE_LOST` before `OUT_OF_DATE`",
        "lifecycle outcomes precede timeout polling",
        "Zero token, duplicate wait XIDs, and accepted-token reuse are `BadValue`",
        "Device loss beats Surface loss and accepted-token reuse",
        "unsupported queue presentation capability is `BadMatch` before token reuse",
        "accepted-token reuse returns `BadValue` before image-state and semaphore-eligibility checks",
        "Acceptance atomically reserves the token and all wait slots",
    )
    for contract in conformance_precedence_contracts:
        c.require(contract in conformance,
                  f"presentation conformance: missing mixed-failure case: {contract}")

    c.require("On every non-success status the target XID remains unallocated" in errors,
              "CreateSwapchain: every non-success reply status must preserve the target XID")
    capability_failure_contract = (
        "TEMPORARILY_NOT_PRESENTABLE means the window has zero extent; it must set "
        "present_supported to 0 and all extent/count/format/mode/usage/queue-family fields to zero. "
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
    c.require("image index is meaningful only for SUCCESS and must be zero on every non-success result" in presentation,
              "AcquireNextImage: failure reply must use image_index = 0")
    c.require("A failed or timed-out acquire signals neither object and changes no image state." in presentation,
              "AcquireNextImage: failure/timeout must not signal semaphore or fence")
    c.require("an acquired-but-idle image alone does not block destruction" in lifetime and
              "An acquired-but-idle image alone does not" in conformance,
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
    queue_flags_registry = read("registries/queue-flags.md")
    c.require("at least one of `GRAPHICS`, `COMPUTE`, or `TRANSFER` MUST be set" in copy_command
              and "A family with none of these three capabilities is incompatible" in copy_command
              and "effective transfer-command support is present when any of `GRAPHICS`, `COMPUTE`, or `TRANSFER` is set" in queue_flags_registry,
              "presentation copy command: transfer capability must include Vulkan implicit graphics/compute support")
    c.require("lacking all of `GRAPHICS`, `COMPUTE`, and `TRANSFER` returns `BadMatch`" in copy_errors
              and "graphics-only, compute-only, and transfer-only families accept the entry" in conformance
              and "only `SPARSE_BINDING` and/or `PROTECTED` rejects it with `BadMatch`" in conformance,
              "presentation copy command: queue-family capability error mapping and mixed-failure vectors must agree")
    copy_errors = read("spec/errors.md")
    copy_error_order = (
        "Error precedence follows the enclosing `CommandBufferData` phases:",
        "(5) for CREATE, append, and FINAL, check Device state",
        "(6) check resource-dependent static values",
        "(7) check the image's mutable state atomically at `QueueSubmit` acceptance",
    )
    c.require("Presentation-only `CMD_COPY_BUFFER_TO_SWAPCHAIN_IMAGE`" in copy_errors and
              "an `image_index` outside the Swapchain" in copy_errors and
              "konkurriert der Submit mit einer Present-Transition" in copy_errors and
              all(term in copy_errors for term in copy_error_order) and
              [copy_errors.index(term) for term in copy_error_order] == sorted(
                  copy_errors.index(term) for term in copy_error_order
              ),
              "presentation copy command: error mapping must preserve Device-before-compatibility and submission-time image-state precedence")
    c.require("incompatible transfer usage with `BadMatch`" in read("spec/conformance.md") and
              "non-`ACQUIRED` image at submission acceptance with `INVALID_SYNCHRONIZATION_STATE`" in read("spec/conformance.md"),
              "presentation copy command: conformance must cover usage and acquired-image validation")
    c.require("later copy submission processed after the image has transitioned to `PRESENT_PENDING` is rejected atomically with `INVALID_SYNCHRONIZATION_STATE`" in copy_command and
              "Request order alone creates no GPU memory dependency" in copy_command and
              "Request order alone is not a GPU dependency" in read("spec/conformance.md"),
              "presentation copy command: submit/present ordering must be explicit and request order must not imply GPU synchronization")
    c.require("If a resource referenced by a `RECORDING` command buffer is destroyed" in lifetime and
              "If a resource referenced by an `EXECUTABLE` command buffer is destroyed" in lifetime and
              "Destroying a Buffer referenced by a `RECORDING` command buffer is atomically rejected" in read("spec/conformance.md"),
              "Buffer lifetime: recording references must block destruction and executable references must be invalidated")
    c.require("Values 7–65535 are unassigned" in read("registries/event-types.md"),
              "compute-only event registry must remain unchanged by presentation event assignments")

    # The lifecycle race catalogue is normative conformance coverage, not a
    # claim that a server/runtime test harness already exists. Keep its race
    # classes and the test oracle synchronized with the presentation rules.
    lifecycle_vectors = (
        "**Acquire timeout versus lifecycle:**",
        "**Acquire synchronization eligibility versus timeout:**",
        "**DestroyDevice versus pending acquire:**",
        "**DestroySurface versus CreateSwapchain:**",
        "**DestroyDevice versus CreateSwapchain:**",
        "**Resize/window destruction versus CreateSwapchain preparation:**",
        "**QueuePresent rejection versus accepted state:**",
        "**Accepted presentation versus resize/Surface loss/Device loss:**",
        "**DestroySwapchain versus pending references:**",
        "**Semaphore uncertainty after accepted presentation failure:**",
    )
    for vector in lifecycle_vectors:
        c.require(vector in conformance,
                  f"presentation lifecycle conformance: missing race vector {vector}")
    c.require(
        "A test controls the serialization order explicitly; wall-clock timing alone is not a valid oracle." in conformance,
        "presentation lifecycle conformance: race ordering must be controlled, not inferred from wall-clock timing",
    )
    c.require(
        "Every vector must assert both externally observable result" in conformance and
        "public XID visibility, image state, token reservation, semaphore state, pending-reference count" in conformance,
        "presentation lifecycle conformance: every race needs external and internal state assertions",
    )
    c.require(
        "Include at least one case per vector with presentation event masks disabled" in conformance and
        "Run the vectors in both request byte orders wherever wire parsing is involved." in conformance,
        "presentation lifecycle conformance: masked-event and both-endian coverage must be explicit",
    )
    lifecycle_normative_contracts = (
        "first terminal result serialized by the server wins",
        "terminalizes each still-open acquire with reply status `DEVICE_DESTROYED`",
        "A Surface must not be destroyed while a live Swapchain references it. The destroy request is rejected atomically; the Surface remains live.",
        "DestroySwapchain",
        "UNTRUSTED",
        "pending acquire registration",
    )
    for contract in lifecycle_normative_contracts:
        c.require(contract in presentation or contract in lifetime,
                  f"presentation lifecycle: normative lifecycle contract missing: {contract}")
    c.require(
        "IMAGE_RELEASED is permitted only when backend access has ended" in conformance and
        "otherwise the image is invalidated and no release event is emitted" in conformance,
        "presentation lifecycle conformance: image release must be gated on backend quiescence and reusability",
    )
    c.require(
        "It must never silently reset a semaphore to `UNSIGNALED`" in presentation and
        "marks that binary semaphore `UNTRUSTED`" in presentation,
        "presentation lifecycle: uncertain semaphore consumption must not be guessed or silently reset",
    )


def check_compact_request_layouts(c: Check) -> None:
    """Assert compact request layouts whose prose contracts are easy to miss in typed tables."""
    devices = read("spec/devices.md")
    memory = read("spec/memory-buffers.md")
    sync = read("spec/synchronization.md")
    presentation = read("spec/presentation.md")
    exact_contracts = (
        (devices, "EnumeratePhysicalDevices",
         "The request has no request-specific payload and is 8 bytes in total."),
        (memory, "GetPhysicalDeviceMemoryProperties",
         "Request: physical-device XID at offset 8; total length 12 bytes."),
        (memory, "GetBufferMemoryRequirements",
         "Offset 8: Device-XID\n- Offset 12: Buffer-XID\n- Total length: 16 bytes"),
        (memory, "FreeMemory",
         "Total length: 16 bytes.\n\n- Offset 8: Device-XID\n- Offset 12: Memory-XID"),
        (memory, "BindBufferMemory",
         "Total length: 28 bytes.\n\n- Offset 8: Device-XID\n- Offset 12: Buffer-XID\n- Offset 16: Memory-XID\n- Offset 20: `CARD64 memory_offset`"),
        (sync, "GetSemaphoreCounterValue",
         "Request: exactly 16 bytes; device XID at offset 8 and semaphore XID at offset 12."),
        (sync, "GetFenceStatus",
         "Request: exactly 16 bytes; device XID at offset 8 and fence XID at offset 12."),
        (sync, "ResetFence",
         "Request: exactly 16 bytes; device XID at offset 8 and fence XID at offset 12."),
        (sync, "DestroyFence",
         "`DestroyFence` is a void request with a fixed total length of 16 bytes: device XID at offset 8 and fence XID at offset 12."),
        (sync, "DestroySemaphore",
         "`DestroySemaphore` is a void request with a fixed total length of 16 bytes: device XID at offset 8 and semaphore XID at offset 12."),
    )
    for document, request_name, contract in exact_contracts:
        c.require(contract in document,
                  f"{request_name}: compact request wire layout/length contract is missing or has drifted")

    c.require(
        "The request MUST have exactly this length; extra or missing bytes result in `BadLength`." in devices
        and "The request has no request-specific payload and is 8 bytes in total." in devices,
        "EnumeratePhysicalDevices: empty payload and exact 8-byte request framing must remain explicit",
    )
    c.require(
        "Request: exactly 16 bytes; device XID at offset 8 and semaphore XID at offset 12." in sync
        and "Request: exactly 16 bytes; device XID at offset 8 and fence XID at offset 12." in sync,
        "synchronization query requests: both XID slots must stay at offsets 8 and 12 in 16-byte requests",
    )
    shaders = read("spec/shaders-pipelines.md")
    recording = read("spec/command-recording.md")
    queue = read("spec/queue-submission.md")
    events = read("spec/events.md")
    c.require(
        "| 8 | XID | `device_xid` |" in shaders
        and "| 12 | XID | `shader_module_xid` |" in shaders
        and "| 16 | CARD32 | `data_length`" in shaders
        and "| 20 | BYTE[] | SPIR-V bytes" in shaders
        and "`20 + ((data_length + 3) & ~3)` bytes" in shaders,
        "ShaderModuleData: chunk header offsets and padded variable payload formula must be explicit",
    )
    c.require(
        "Offset 8: Device-XID\n- Offset 12: Buffer-XID\n- Offset 16: `CARD64 buffer_offset`\n- Offset 24: `CARD32 data_length`\n- Offset 28: Byte-Payload" in memory
        and "`28 + ((uint64(data_length) + 3) & ~uint64(3))`" in memory
        and "Total length: 28 bytes." in memory,
        "WriteBuffer/ReadBuffer: fixed prefixes, data length field, and upload padding formula must remain exact",
    )
    c.require(
        "| 8 | XID | Device-XID |" in queue
        and "| 32 | CARD64 | `submission_token` |" in queue
        and "| 40 | variable | Command-Buffer-XIDs, Wait-Entries, Signal-Entries |" in queue
        and "Each wait entry is 16 bytes" in queue
        and "Each signal entry is 12 bytes" in queue,
        "QueueSubmit: fixed header offsets and variable entry widths must be explicit",
    )
    c.require(
        "followed by zero padding to a four-byte boundary" in shaders
        and re.search(r"server checks request length, padding, flag combinations", shaders, re.I) is not None
        and "invalid padding" in shaders.lower()
        and re.search(r"padding must consist entirely of zero bytes; non-zero padding results in `BadValue`", memory, re.I) is not None,
        "variable byte payloads: shader chunks and WriteBuffer must specify zero-padding validation and failure behavior",
    )
    c.require(
        re.search(r"padding-Bytes müssen null sein", shaders, re.I) is not None
        and "`28 + ((entry_point_length + 3) & ~3)`" in shaders
        and "`24 + 16 * binding_count`" in shaders
        and "Each binding record is 16 bytes" in shaders
        and "`20 + 36 * write_count`" in shaders
        and "Jeder Write ist 36 Bytes groß." in shaders,
        "variable/count-based request contracts must keep exact formulas, entry widths, and zero-padding rules",
    )
    c.require(
        re.search(r"\|\s*20\s*\|\s*CARD32\s*\|\s*`binding_count`\s*\|", shaders) is not None
        and re.search(r"\|\s*24\s*\|\s*BINDING\[\]\s*\|\s*`binding_count` Binding-Records\s*\|", shaders) is not None
        and "The request MUST have exactly the length determined by `binding_count`" in shaders
        and re.search(r"(?:\|\s*20\s*\|\s*CARD16\s*\|\s*`pool_size_count`\s*\||Offset\s+20:\s*`CARD16 pool_size_count`)", shaders, re.I) is not None
        and "`24 + 8 * pool_size_count`" in shaders,
        "descriptor variable arrays: each count field must match its record array and canonical length formula",
    )
    c.require(
        re.search(r"(?:\|\s*24\s*\|\s*CARD16\s*\|\s*`entry_point_length`\s*\||Offset\s+24:\s*`CARD16 entry_point_length`)", shaders, re.I) is not None
        and "Padding-Bytes müssen null sein" in shaders
        and "Die Gesamtlänge muss exakt `28 + ((entry_point_length + 3) & ~3)` Bytes betragen" in shaders,
        "CreateComputePipeline: byte count, four-byte padding, and total length must agree",
    )
    c.require(
        "| 24 | CARD16 | Command-Buffer-Count |" in queue
        and "| 26 | CARD16 | Wait-Semaphore-Count |" in queue
        and "| 28 | CARD16 | Signal-Semaphore-Count |" in queue
        and "| 30 | CARD16 | `reserved = 0` |" in queue
        and "`40 + 4*C + 16*W + 12*S`" in queue
        and re.search(r"(?is)(?:C\s*=\s*Command-Buffer-Count|Command-Buffer-Count\s*\(C\)|`C`\s+for\s+Command-Buffer-Count).{0,160}(?:W\s*=\s*Wait-Semaphore-Count|Wait-Semaphore-Count\s*\(W\)|`W`\s+for\s+Wait-Semaphore-Count).{0,160}(?:S\s*=\s*Signal-Semaphore-Count|Signal-Semaphore-Count\s*\(S\)|`S`\s+for\s+Signal-Semaphore-Count)", queue) is not None,
        "QueueSubmit: each 16-bit count must map to its own array term and the complete variable length formula",
    )
    c.require(
        "`SelectEvents` is a void request with a fixed total length of 32 bytes" in events
        and "common-header `flags` field at offset 5" in events
        and "reserved common-header field at offset 6" in events,
        "SelectEvents: fixed length and common-header reserved-field offsets must remain explicit",
    )
    c.require(
        "The final layouts include the common 8-byte header" in presentation
        and "a 16-byte CreateSurface (target Surface XID plus X11 Window XID)" in presentation
        and "a 12-byte DestroySurface" in presentation
        and "a 12-byte DestroySwapchain" in presentation,
        "presentation compact request layouts must include the common header and exact create/destroy lengths",
    )

def check_command_buffer_reference_retirement(c: Check) -> None:
    """Assert reset/invalidation/rerecording ownership and deferred-release contracts."""
    command = read("spec/command-recording.md")
    lifetime = read("spec/resource-lifetime.md")
    queue = read("spec/queue-submission.md")
    contracts = (
        "A successful ResetCommandBuffer is a single state transition from the prior non-pending state to INITIAL.",
        "retires the command buffer's recorded-resource reference edges exactly once",
        "A rejected reset, including reset of a PENDING buffer",
        "A subsequent successful rerecording begins from INITIAL and builds a fresh reference set",
        "If submission acceptance wins, reset is rejected while the command buffer is PENDING.",
        "If reset wins, the buffer is INITIAL and cannot be submitted",
    )
    for contract in contracts:
        c.require(contract in command,
                  f"command-buffer reference retirement: missing command-recording contract: {contract}")
    for contract in (
        "Successful reset detaches its recorded entries and retires those edges exactly once",
        "reset MUST NOT retire those same edges again",
        "All delayed callbacks use immutable internal identities, not re-resolved XIDs",
    ):
        c.require(contract in lifetime,
                  f"command-buffer reference retirement: missing lifetime contract: {contract}")
    c.require(
        "Command-buffer reference retirement is separate from submission terminalization" in queue
        and "backend hold still needed to protect a possible in-flight access remains retained" in queue,
        "command-buffer reference retirement: submission terminalization must not release backend holds early",
    )
    # The transition matrix must cover both invalidation paths and the only legal
    # recovery path; checking only reset would miss stale executable recordings.
    for contract in (
        "Asynchronous execution failure or device loss → `INVALID` after the pending phase ends",
        "A failed submission makes every affected command buffer `INVALID` after the pending phase ends",
        "must be reset and recorded again",
        "A FINAL chunk transitions `RECORDING` to `EXECUTABLE` only after the entire chunk",
        "no partially finalized executable recording is published",
        "A failed FINAL chunk leaves the buffer in `RECORDING`",
        "A later chunk MUST NOT revive a recording interrupted by device loss",
    ):
        c.require(contract in command or contract in queue,
                  f"command-buffer transition matrix: missing failure/recovery contract: {contract}")
    for contract in (
        "If invalidation only marks the buffer invalid while an internal edge is still required for backend safety",
        "All delayed callbacks use immutable internal identities, not re-resolved XIDs",
        "Submission references are independent from recorded references",
    ):
        c.require(contract in lifetime,
                  f"command-buffer invalidation: missing deferred-lifetime contract: {contract}")
    c.require(
        "A `PENDING` command buffer MUST NOT be modified, reset, freed, or submitted again." in command
        and "If submission acceptance wins, reset is rejected while the command buffer is PENDING." in command
        and "If reset wins, the buffer is INITIAL and cannot be submitted" in command,
        "command-buffer reset/submit race: pending exclusion and serialized winner must be explicit",
    )

def check_create_device_precedence(c: Check) -> None:
    """Keep CreateDevice's framing, scalar, XID, capability, and publication order explicit."""
    devices = read("spec/devices.md")
    section_match = re.search(
        r"^## `CreateDevice`[\s\S]*?(?=^## |\Z)", devices, re.M
    )
    section = section_match.group(0) if section_match else ""
    phases = (
        "1. Validate the complete variable-length request framing",
        "2. Validate wire-level and scalar fields",
        "An unknown feature ID, because no optional feature IDs are assigned in v0.1",
        "3. Validate `device_xid` as a create-XID",
        "4. Resolve `physical_device_xid`",
        "5. Validate that the XID is a Physical-Device resource",
        "6. Require successful XGE 1.0-or-later negotiation",
        "7. Check physical-device availability",
        "8. Validate every requested queue-family index and queue count",
        "9. Check the mandatory v0.1 baseline capability",
        "10. Only after all prior checks succeed may backend device creation begin",
    )
    positions = [section.find(phase) for phase in phases]
    c.require(
        bool(section) and all(position >= 0 for position in positions)
        and positions == sorted(positions)
        and len(set(positions)) == len(positions),
        "CreateDevice precedence: framing, scalar syntax, create-XID, input-XID, ownership, XGE, availability, queue support, feature support, and publication must be ordered",
    )
    c.require(
        "unknown feature ID takes precedence over target-XID occupancy" in section
        and "target-XID validation precedes physical-device lookup" in section
        and "every syntactically valid client extension name is unregistered" in section,
        "CreateDevice precedence: empty v0.1 registries and create/input XID ordering must remain explicit",
    )


def check_create_default_device_precedence(c: Check) -> None:
    devices = read("spec/devices.md")
    section_match = re.search(r"^## `CreateDefaultDevice`[\s\S]*?(?=^## |\Z)", devices, re.M)
    section = section_match.group(0) if section_match else ""
    phases = ("(1) validate the exact/formula-based request length", "(2) validate `queue_count`, the reserved field, and every priority", "(3) validate the target `device_xid` as a create-XID", "(4) require successful XGE 1.0-or-later negotiation", "(5) select a suitable physical device and compute-capable queue family")
    positions = [section.find(phase) for phase in phases]
    c.require(bool(section) and all(p >= 0 for p in positions) and positions == sorted(positions), "CreateDefaultDevice precedence must be explicit and ordered")
    c.require("that can supply the requested `queue_count`" in section and "if no such combination is available, it reports `DEVICE_UNAVAILABLE`" in section, "CreateDefaultDevice must require a supported queue count")


def check_wait_semaphore_semantics(c: Check) -> None:
    """Keep WAIT_ANY/WAIT_ALL predicates, partial progress, and lifecycle races normative."""
    sync = read("spec/synchronization.md")
    conformance = read("spec/conformance.md")
    devices = read("spec/devices.md")
    lifetime = read("spec/resource-lifetime.md")
    errors = read("spec/errors.md")
    contracts = (
        "`WAIT_ANY` is satisfied when at least one entry is satisfied.",
        "`WAIT_ALL` is satisfied only when every entry is satisfied.",
        "one coherent snapshot of all listed counters",
        "If the complete predicate is already satisfied, the request commits `SUCCESS` without installing a registration",
        "The Device-state check in step 5, Timeline-type check in step 6, coherent initial counter snapshot",
        "A `WAIT_ALL` registration that has only some entries satisfied remains open",
        "does not consume, reset, reserve, or otherwise modify any Timeline counter",
        "signal publication and reevaluation of affected waits are one serialized transition",
        "the complete selected predicate already committed as satisfied returns `SUCCESS`",
    )
    for contract in contracts:
        c.require(contract in sync, f"WaitSemaphores normative predicate missing: {contract}")
    c.require(
        "partial counter satisfaction is still open" in lifetime
        and "Partial `WAIT_ALL` progress is not a successful or terminal result" in devices,
        "WaitSemaphores lifecycle: partial WAIT_ALL must remain open for DestroyDevice terminalization",
    )
    c.require(
        "partial `WAIT_ALL` progress remains open" in errors
        and "including partially satisfied `WAIT_ALL` registrations" in conformance,
        "WaitSemaphores cross-chapter summary must preserve partial-ALL lifecycle semantics",
    )
    for vector in (
        "**`WAIT_ANY` predicate:**",
        "**`WAIT_ALL` partial progress:**",
        "**Concurrent Timeline signals and wait reevaluation:**",
        "**Partial `WAIT_ALL` versus lifecycle:**",
        "**Zero-timeout predicate snapshot:**",
    ):
        c.require(vector in conformance, f"WaitSemaphores conformance matrix missing race vector {vector}")
    c.require(
        "one status-only success with no winning index" in conformance
        and "Reverse callback delivery for strictly ordered increasing signal operations" in conformance,
        "WaitSemaphores conformance: ANY result and signal callback-order independence must be explicit",
    )


def check_read_buffer_ordering_and_lifecycle(c: Check) -> None:
    """Keep the readback snapshot boundary ahead of every later writer and lifecycle transition."""
    memory = read("spec/memory-buffers.md")
    devices = read("spec/devices.md")
    lifetime = read("spec/resource-lifetime.md")
    errors = read("spec/errors.md")
    conformance = read("spec/conformance.md")
    c.require(
        "both later `QueueSubmit` requests and later `WriteBuffer` requests" in memory
        and "MUST be deferred until the snapshot has been captured" in memory
        and "begin a transfer" in memory
        and "processed in their original request order" in memory,
        "ReadBuffer: all later write paths must remain behind the stable snapshot boundary",
    )
    c.require(
        "successful stable-snapshot capture and completion of required host-visibility/cache operations" in memory
        and "If Device Loss commits first" in memory
        and "if `DestroyDevice` commits first" in memory
        and "A later Device Loss or `DestroyDevice` MUST NOT rewrite a success already committed" in memory,
        "ReadBuffer: snapshot commit and Device lifecycle terminalization must have one deterministic winner",
    )
    c.require(
        "Any open `ReadBuffer` operation for this Device is likewise terminalized" in devices
        and "A `ReadBuffer` operation belonging to a disconnected connection is cancelled" in lifetime
        and "if its stable snapshot has not already been committed" in lifetime,
        "ReadBuffer: Device destruction and disconnect must preserve snapshot terminalization and backend references",
    )
    c.require(
        "If Device Loss or `DestroyDevice` terminalizes an open read before snapshot commit" in errors
        and "Client disconnect before snapshot commit cancels the read without a reply" in errors,
        "ReadBuffer: error mapping must include lifecycle and disconnect outcomes",
    )
    c.require(
        "stabilisiert seinen Snapshot vor späteren `QueueSubmit`- und `WriteBuffer`-Schreibzugriffen" in conformance
        and "Rennen zwischen Snapshot-Commit, Device Loss und `DestroyDevice`" in conformance
        and "Client-Disconnect vor Snapshot-Commit" in conformance,
        "ReadBuffer: conformance must cover later writers, lifecycle races, and disconnect",
    )


def check_shader_descriptor_pipeline_contract(c: Check) -> None:
    """Keep subopcodes 15–23 capacity, range, and entry-point rules cross-document consistent."""
    shaders = read("spec/shaders-pipelines.md")
    command = read("spec/command-recording.md")
    errors = read("spec/errors.md")
    conformance = read("spec/conformance.md")
    c.require(
        "Normative Pool-Kapazität" in shaders
        and "max_sets" in shaders
        and "sämtliche Typ-Kapazitäten" in shaders
        and "unzureichende Set-/Typ-Kapazität" in shaders
        and "ALLOCATION_FAILED" in shaders
        and "Erfolgreiches `FreeDescriptorSets` gibt die Kapazität" in shaders,
        "Descriptor pools: set and per-type capacities must be accounted atomically and returned on free",
    )
    c.require(
        "stage_flags` value is exactly `0x00000001`" in shaders
        and "descriptor-count/device-limit checks (`BadMatch`" in shaders
        and "A syntactically valid binding count that exceeds the selected Device's descriptor limits returns `BadMatch`" in errors,
        "CreateDescriptorSetLayout: compute stage and Device descriptor-limit classification must be normative",
    )
    c.require(
        "`stage_flags` MUSS exakt `COMPUTE` sein" in shaders
        and "Ranges mit überlappenden Byte-Intervallen sind unzulässig" in shaders
        and "offset` und `size` MÜSSEN Vielfache von vier sein" in shaders
        and "maxPushConstantsSize` überschreitet" in shaders
        and "maxBoundDescriptorSets`" in shaders
        and "The complete half-open byte interval" in command
        and "arithmetic overflow of `offset + data_length` returns `BadValue`" in errors
        and "not contained in one declared COMPUTE range" in errors
        and "covered only by the union of two adjacent declared ranges" in conformance,
        "CreatePipelineLayout/CMD_PUSH_CONSTANTS: range alignment, overlap, limits, single-range coverage, and errors must agree",
    )
    c.require(
        "Ein fehlender Entry-Point oder ein Entry-Point mit anderem Execution Model" in shaders
        and "Execution Model ungleich `GLCompute` `BadMatch`" in errors
        and "CreateComputePipeline entry point" in conformance,
        "CreateComputePipeline: selected entry point must exist and use GLCompute",
    )
    c.require(
        "Shader, Descriptor, and Pipeline request vectors (subopcodes 15–23)" in conformance
        and "Descriptor Pool capacity accounting" in conformance
        and "UpdateDescriptorSets versus submission/release" in conformance
        and "CreatePipelineLayout push-constant ranges" in conformance
        and "Create/allocate atomicity under backend failure" in conformance,
        "Conformance: shader, descriptor, and pipeline requests need explicit capacity, race, range, and failure vectors",
    )

def main() -> int:
    c = Check()
    check_events(c)
    check_presentation_profile(c)
    check_xge_abi(c)
    check_reason_code_registry(c)
    check_error_registry(c)
    check_other_numeric_registries(c)
    check_request_field_offsets_and_widths(c)
    check_compact_request_layouts(c)
    check_command_buffer_reference_retirement(c)
    check_request_document_coverage(c)
    check_request_matrix_normative_lengths(c)
    check_common_request_error_precedence(c)
    check_create_device_precedence(c)
    check_create_default_device_precedence(c)
    check_wait_semaphore_semantics(c)
    check_read_buffer_ordering_and_lifecycle(c)
    check_shader_descriptor_pipeline_contract(c)
    check_request_specific_precedence_exceptions(c)
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