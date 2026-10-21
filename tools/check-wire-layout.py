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
    event_type_table = registry.split("## Event type IDs", 1)[1].split("\n## ", 1)[0]
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
        c.require(f"`{symbol}`" in error_doc,
                  f"error registry symbol {symbol} is missing from error guidance")


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
    c.require(len(registry_rows) == 40,
              f"request registry: expected 40 table rows, found {len(registry_rows)}")
    c.require(len(set(opcodes)) == len(opcodes), "request registry contains duplicate subopcode values")
    c.require(len(set(names)) == len(names), "request registry contains duplicate request names")
    c.require(set(opcodes) == set(range(1, 41)),
              "request registry must assign each subopcode 1 through 40 exactly once; 0 is reserved")
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
    c.require(reply_names == expected_names,
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
            (r"Gesamtlänge:\s*\n+\x60?28 \+ \(\(data_length \+ 3\) & ~3\)", "request payload length formula"),
            (r"Byte-Payload", "byte payload"),
            (r"Null-Padding bis zur nächsten Vierbytegrenze", "request zero padding"),
            (r"Reply von 32 Bytes", "empty standard reply on success"),
            (r"Bei einem fehlgeschlagenen \x60WriteBuffer\x60", "failure does not claim successful upload"),
        ]),
        "ReadBuffer": ("memory", [
            (r"Gesamtlänge: 28 Bytes", "fixed 28-byte request"),
            (r"Reply enthält nach dem 32-Byte-Header.*?ab Offset 32", "payload begins at reply offset 32"),
            (r"reply\.length = ceil\(data_length / 4\)", "readback reply.length formula"),
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
            elif kind == "WaitForFence":
                status = int.from_bytes(wire[8:12], order)
                c.require(status in (0, 1, 2, 3), f"{name}: invalid WaitForFence status")
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
                elif rule == "wait-for-fence-status": invalid = kind == "WaitForFence" and int.from_bytes(wire[8:12], order) not in (0, 1, 2, 3)
                elif rule == "property-padding-zero":
                    value_length = int.from_bytes(wire[16:20], order)
                    invalid = kind == "GetPhysicalDeviceProperty-success" and len(wire) >= 32 + value_length and wire[32 + value_length:] != bytes(len(wire) - 32 - value_length)
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
                elif rule == "memory-reserved-zero":
                    invalid = kind == "GetPhysicalDeviceMemoryProperties" and len(wire) >= 48 and wire[40:48] != bytes(8)
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
                elif rule == "property-failure-zero": invalid = kind == "GetPhysicalDeviceProperty-not-supported" and (wire[12:20] != bytes(8) or wire[32:] or declared != 0)
                elif rule == "queue-record-reserved": invalid = kind == "GetPhysicalDeviceQueueFamilyProperties-two-records" and any(wire[o+8:o+12] != bytes(4) for o in range(32, len(wire), 12))
                elif rule == "memory-heap-reserved": invalid = kind == "GetPhysicalDeviceMemoryProperties-one-type-one-heap" and wire[68:72] != bytes(4)
                elif rule == "reserved-zero": invalid = ((kind == "GetPhysicalDeviceProperty-success" and wire[20:32] != bytes(12)) or (kind == "GetBufferMemoryRequirements" and wire[28:32] != bytes(4)) or (kind == "GetSemaphoreCounterValue" and wire[16:32] != bytes(16)) or (kind == "GetFenceStatus" and wire[8:32] != bytes(24)))
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


def main() -> int:
    c = Check()
    check_events(c)
    check_error_registry(c)
    check_request_document_coverage(c)
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
