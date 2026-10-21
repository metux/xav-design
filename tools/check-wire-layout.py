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
    check_reply_matrix(c)
    check_reply_layouts(c)
    check_reply_formula_vectors(c)
    if c.errors:
        print(f"wire-layout check FAILED: {len(c.errors)} of {c.checks} checks failed", file=sys.stderr)
        for error in c.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"wire-layout check passed: {c.checks} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
