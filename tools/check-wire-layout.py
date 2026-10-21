#!/usr/bin/env python3
"""Static consistency checks for XAverius request/reply and XGE wire layouts.

Run from the repository root: python3 tools/check-wire-layout.py
Uses only the Python standard library and parses the normative Markdown sources.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

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
    reg_ids = {
        name: int(value)
        for value, name in re.findall(r"^\|\s*(\d+)\s*\|\s*`([A-Z_]+)`\s*\|\s*$", registry, re.M)
    }
    doc_sections = dict(sections(event_doc))
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


def parse_request_registry(markdown: str) -> dict[int, tuple[str, str]]:
    result: dict[int, tuple[str, str]] = {}
    for line in markdown.splitlines():
        row = re.match(r"^\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|", line)
        if row:
            name, opcode, kind = row.group(1), int(row.group(2)), row.group(3).strip()
            result[opcode] = (name, kind)
    return result

def check_reply_matrix(c: Check) -> None:
    registry = parse_request_registry(read("registries/request-subopcodes.md"))
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
    c.require(len(registry) == 40, f"request registry: expected 40 registered requests, found {len(registry)}")
    c.require(len(matrix_rows) == len(registry), f"request audit matrix has {len(matrix_rows)} rows, registry has {len(registry)}")
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


def check_reply_layouts(c: Check) -> None:
    devices = read("spec/devices.md")
    memory = read("spec/memory-buffers.md")
    sync = read("spec/synchronization.md")
    wire = read("spec/wire-protocol.md")
    checks = [
        (devices, r"\| 8 \| CARD32 \| `status` \|", "GetPhysicalDeviceProperty status at reply offset 8"),
        (devices, r"\| 12 \| CARD32 \| `property_type` \|", "property_type at offset 12"),
        (devices, r"\| 16 \| CARD32 \| `value_length` in Bytes \|", "value_length at offset 16"),
        (devices, r"\| 20–31 \| BYTE\[12\] \| reserviert, null \|", "property reply reserved bytes 20–31"),
        (devices, r"reply\.length = ceil\(value_length / 4\)", "property reply length formula"),
        (devices, r"reply\.length = 3 \* queue_family_count", "queue-family reply length formula"),
        (memory, r"\| 8 \| CARD64 \| `size` \|", "buffer-memory-requirements size at offset 8"),
        (memory, r"\| 16 \| CARD64 \| `alignment` \|", "buffer-memory-requirements alignment at offset 16"),
        (memory, r"\| 24 \| CARD32 \| `memory_type_bits` \|", "buffer-memory-requirements memory type bits at offset 24"),
        (memory, r"reply\.length = 4 \+ 2 \* memory_type_count \+ 4 \* memory_heap_count", "memory-properties reply length formula"),
        (sync, r"Byte 0: standardmäßiges X11-Reply", "GetFenceStatus standard response_type byte"),
        (sync, r"Byte 1: Fence-Status", "GetFenceStatus status byte"),
        (sync, r"Offsets 2–3: standardmäßige X11-Reply-Sequenznummer", "GetFenceStatus sequence field"),
        (sync, r"Offsets 4–7: standardmäßiges `reply\.length = 0`", "GetFenceStatus zero reply.length"),
        (sync, r"Offsets 8–31: XAverius-reserviert, null", "GetFenceStatus reserved bytes"),
        (sync, r"Offset 8 enthält einen `CARD32 status`; Offsets 12–31 sind null und `reply\.length = 0`", "WaitForFence status and reserved fields"),
        (wire, r"Replies verwenden den Standard-X11-Reply-Header von 32 Bytes", "standard 32-byte X11 reply header"),
        (wire, r"`reply\.length` gibt die Anzahl der Vierbyteeinheiten nach diesem Header an", "reply.length unit definition"),
    ]
    for source, pattern, label in checks:
        c.require(re.search(pattern, source, re.I) is not None, f"reply layout: missing or changed: {label}")

def main() -> int:
    c = Check()
    check_events(c)
    check_reply_matrix(c)
    check_reply_layouts(c)
    if c.errors:
        print(f"wire-layout check FAILED: {len(c.errors)} of {c.checks} checks failed", file=sys.stderr)
        for error in c.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"wire-layout check passed: {c.checks} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
