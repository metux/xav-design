#!/usr/bin/env python3
"""Verify golden XAverius wire vectors with a small reference encoder.

These tests validate the fixtures and framing rules. They do not test a live
XAverius client/server implementation; a future implementation should consume
wire-vectors.json as its interoperability oracle.
"""
from __future__ import annotations

import json
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "wire-vectors.json"
REQUEST_REGISTRY = ROOT / "registries" / "request-subopcodes.md"


def encode_request(vector: dict) -> bytes:
    """Encode the currently covered request layouts using the X11 byte order."""
    fields = vector["fields"]
    if vector["byte_order"] not in ("little", "big"):
        raise ValueError("unknown byte order")
    if not 128 <= vector["major_opcode"] <= 255:
        raise ValueError("extension major opcode must be in 128..255")
    endian = "<" if vector["byte_order"] == "little" else ">"
    length_bytes = vector["length_bytes"]
    if length_bytes < 8 or length_bytes % 4:
        raise ValueError("request length must be >= 8 and divisible by four")
    length_words = length_bytes // 4
    if length_words > 0xFFFF:
        raise ValueError("BIG-REQUESTS is unsupported; ordinary length overflow")
    if vector["flags"] != 0:
        raise ValueError("these v0.1 golden vectors require zero flags")

    data = bytearray(struct.pack(
        endian + "BBHBBH",
        vector["major_opcode"],
        0,  # X11 data is reserved as zero by XAverius v0.1.
        length_words,
        vector["subopcode"],
        vector["flags"],
        0,  # XAverius common-header reserved field.
    ))

    request = vector["request"]
    if request == "CreateBuffer":
        if fields["reserved"] != 0:
            raise ValueError("CreateBuffer reserved field must be zero")
        data.extend(struct.pack(
            endian + "IIQII",
            fields["device_xid"],
            fields["buffer_xid"],
            fields["size"],
            fields["usage_flags"],
            fields["reserved"],
        ))
    elif request in ("WriteBuffer", "ReadBuffer"):
        data.extend(struct.pack(
            endian + "IIQI",
            fields["device_xid"],
            fields["buffer_xid"],
            fields["buffer_offset"],
            fields["data_length"],
        ))
        if request == "WriteBuffer":
            payload = bytes.fromhex(fields["payload_hex"])
            padding = bytes.fromhex(fields["padding_hex"])
            if fields["data_length"] <= 0 or len(payload) != fields["data_length"]:
                raise ValueError("WriteBuffer data_length must match a nonempty payload")
            expected_padding = (-len(payload)) % 4
            if len(padding) != expected_padding or any(padding):
                raise ValueError("WriteBuffer padding must be the required number of zero bytes")
            data.extend(payload)
            data.extend(padding)
    elif request == "AllocateMemory":
        if fields["reserved"] != 0:
            raise ValueError("AllocateMemory reserved field must be zero")
        data.extend(struct.pack(
            endian + "IIQII",
            fields["device_xid"], fields["memory_xid"],
            fields["allocation_size"], fields["memory_type_index"], fields["reserved"],
        ))
    elif request == "FreeMemory":
        data.extend(struct.pack(endian + "II", fields["device_xid"], fields["memory_xid"]))
    elif request == "CreateCommandPool":
        if fields["flags"] & ~0x3:
            raise ValueError("CreateCommandPool reserved flag bits must be zero")
        data.extend(struct.pack(
            endian + "IIII", fields["device_xid"], fields["command_pool_xid"],
            fields["queue_family_index"], fields["flags"],
        ))
    elif request == "CreateSemaphore":
        if fields["semaphore_type"] not in (0, 1):
            raise ValueError("unknown semaphore type")
        if fields["semaphore_type"] == 0 and fields["initial_value"] != 0:
            raise ValueError("binary semaphore initial_value must be zero")
        data.extend(struct.pack(
            endian + "II IQ".replace(" ", ""), fields["device_xid"], fields["semaphore_xid"],
            fields["semaphore_type"], fields["initial_value"],
        ))
    elif request == "DestroySemaphore":
        data.extend(struct.pack(endian + "II", fields["device_xid"], fields["semaphore_xid"]))
    elif request == "DestroyCommandPool":
        data.extend(struct.pack(endian + "II", fields["device_xid"], fields["command_pool_xid"]))
    elif request == "ResetCommandBuffer":
        data.extend(struct.pack(endian + "II", fields["device_xid"], fields["command_buffer_xid"]))
    elif request == "DestroyFence":
        data.extend(struct.pack(endian + "II", fields["device_xid"], fields["fence_xid"]))
    elif request == "CreateFence":
        if fields["create_flags"] != 0 or fields["reserved"] != 0:
            raise ValueError("CreateFence flags and reserved field must be zero")
        data.extend(struct.pack(
            endian + "IIII", fields["device_xid"], fields["fence_xid"],
            fields["create_flags"], fields["reserved"],
        ))
    elif request == "ResetFence":
        data.extend(struct.pack(endian + "II", fields["device_xid"], fields["fence_xid"]))
    elif request == "SignalSemaphore":
        data.extend(struct.pack(
            endian + "IIQ", fields["device_xid"], fields["semaphore_xid"], fields["signal_value"],
        ))
    elif request in ("GetSemaphoreCounterValue", "GetFenceStatus"):
        resource_field = "semaphore_xid" if request == "GetSemaphoreCounterValue" else "fence_xid"
        data.extend(struct.pack(endian + "II", fields["device_xid"], fields[resource_field]))
    elif request == "WaitForFence":
        data.extend(struct.pack(
            endian + "IIQ", fields["device_xid"], fields["fence_xid"], fields["timeout_ns"],
        ))
    elif request == "BindBufferMemory":
        data.extend(struct.pack(
            endian + "IIIQ",
            fields["device_xid"], fields["buffer_xid"], fields["memory_xid"],
            fields["memory_offset"],
        ))
    else:
        raise ValueError(f"no reference encoder for {request}")

    if len(data) != length_bytes:
        raise ValueError(
            f"{request}: declared {length_bytes} bytes but encoded {len(data)}"
        )
    return bytes(data)


def validate_request_wire(wire: bytes, byte_order: str) -> None:
    """Validate generic X11/XAverius request framing from raw bytes."""
    if len(wire) < 8:
        raise ValueError("truncated common request header")
    if len(wire) % 4:
        raise ValueError("request byte length must be divisible by four")
    if byte_order not in ("little", "big"):
        raise ValueError("unknown byte order")
    if wire[0] < 128:
        raise ValueError("extension major opcode must be in 128..255")
    if wire[4] == 0:
        raise ValueError("subopcode zero is reserved")
    declared_words = int.from_bytes(wire[2:4], byte_order)
    if declared_words == 0:
        raise ValueError("zero request length is invalid; BIG-REQUESTS is unsupported")
    if declared_words * 4 != len(wire):
        raise ValueError("declared request length does not match wire bytes")
    if wire[1] != 0:
        raise ValueError("X11 data byte must be zero")
    if wire[5] != 0:
        raise ValueError("reserved flags must be zero")
    if wire[6:8] != bytes(2):
        raise ValueError("reserved common-header field must be zero")


class GoldenWireVectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        fixture = json.loads(FIXTURES.read_text(encoding="utf-8"))
        if fixture.get("schema_version") != 1:
            raise ValueError("unsupported wire vector schema version")
        cls.vectors = fixture["vectors"]
        registry_text = REQUEST_REGISTRY.read_text(encoding="utf-8")
        import re
        cls.request_opcodes = {
            name: int(opcode)
            for name, opcode in re.findall(
                r"^\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|",
                registry_text, re.M,
            )
        }

    def test_golden_bytes(self) -> None:
        self.assertGreaterEqual(len(self.vectors), 1)
        names = set()
        for vector in self.vectors:
            with self.subTest(vector=vector["name"]):
                self.assertNotIn(vector["name"], names)
                names.add(vector["name"])
                actual = encode_request(vector)
                self.assertEqual(actual.hex(), vector["wire_hex"])
                self.assertEqual(len(actual), vector["length_bytes"])
                self.assertEqual(actual[1], 0, "X11 data byte must be zero")
                self.assertEqual(actual[5], 0, "v0.1 flags must be zero in these vectors")
                self.assertEqual(actual[6:8], b"\x00\x00", "reserved header must be zero")
                self.assertEqual(
                    int.from_bytes(actual[2:4], vector["byte_order"]),
                    len(actual) // 4,
                )

    def test_golden_vectors_match_normative_request_layouts_and_lengths(self) -> None:
        # Prevent the encoder and golden hex from drifting together away from the spec.
        import re
        spec_by_request = {
            "CreateCommandPool": "command-recording.md",
            "CreateSemaphore": "synchronization.md",
            "DestroySemaphore": "synchronization.md",
            "DestroyCommandPool": "command-recording.md",
            "ResetCommandBuffer": "command-recording.md",
            "DestroyFence": "synchronization.md",
            "CreateFence": "synchronization.md",
            "ResetFence": "synchronization.md",
            "SignalSemaphore": "synchronization.md",
            "GetSemaphoreCounterValue": "synchronization.md",
            "GetFenceStatus": "synchronization.md",
            "WaitForFence": "synchronization.md",
        }
        spec_text = {
            name: (ROOT / "spec" / path).read_text(encoding="utf-8")
            for name, path in spec_by_request.items()
        }
        memory = (ROOT / "spec" / "memory-buffers.md").read_text(encoding="utf-8")
        contracts = {
            "CreateBuffer": {
                "fields": [(8, "XID", "device_xid"), (12, "XID", "buffer_xid"),
                           (16, "CARD64", "size"), (24, "CARD32", "usage_flags"),
                           (28, "CARD32", "reserved")],
                "length": 32,
            },
            "WriteBuffer": {
                "fields": [(8, "XID", "device_xid"), (12, "XID", "buffer_xid"),
                           (16, "CARD64", "buffer_offset"), (24, "CARD32", "data_length")],
                "length": "28 + ((uint64(data_length) + 3) & ~uint64(3))",
            },
            "ReadBuffer": {
                "fields": [(8, "XID", "device_xid"), (12, "XID", "buffer_xid"),
                           (16, "CARD64", "buffer_offset"), (24, "CARD32", "data_length")],
                "length": 28,
            },
            "AllocateMemory": {
                "fields": [(8, "XID", "device_xid"), (12, "XID", "memory_xid"),
                           (16, "CARD64", "allocation_size"), (24, "CARD32", "memory_type_index"),
                           (28, "CARD32", "reserved")],
                "length": 32,
            },
            "FreeMemory": {
                "fields": [(8, "XID", "device_xid"), (12, "XID", "memory_xid")],
                "length": 16,
            },
            "BindBufferMemory": {
                "fields": [(8, "XID", "device_xid"), (12, "XID", "buffer_xid"),
                           (16, "XID", "memory_xid"), (20, "CARD64", "memory_offset")],
                "length": 28,
            },
            "CreateCommandPool": {
                "fields": [(8, "XID", "device_xid"), (12, "XID", "command_pool_xid"),
                           (16, "CARD32", "queue_family_index"), (20, "CARD32", "flags")],
                "length": 24,
            },
            "CreateSemaphore": {
                "fields": [(8, "XID", "device_xid"), (12, "XID", "semaphore_xid"),
                           (16, "CARD32", "semaphore_type"), (20, "CARD64", "initial_value")],
                "length": 28,
            },
            "DestroySemaphore": {
                "fields": [(8, "XID", "device_xid"), (12, "XID", "semaphore_xid")],
                "length": 16,
            },
            "DestroyCommandPool": {
                "fields": [(8, "XID", "device_xid"), (12, "XID", "command_pool_xid")],
                "length": 16,
            },
            "ResetCommandBuffer": {
                "fields": [(8, "XID", "device_xid"), (12, "XID", "command_buffer_xid")],
                "length": 16,
            },
            "DestroyFence": {
                "fields": [(8, "XID", "device_xid"), (12, "XID", "fence_xid")],
                "length": 16,
            },
            "CreateFence": {
                "fields": [(8, "XID", "device_xid"), (12, "XID", "fence_xid"),
                           (16, "CARD32", "create_flags"), (20, "CARD32", "reserved")],
                "length": 24,
            },
            "ResetFence": {
                "fields": [(8, "XID", "device_xid"), (12, "XID", "fence_xid")],
                "length": 16,
            },
            "SignalSemaphore": {
                "fields": [(8, "XID", "device_xid"), (12, "XID", "semaphore_xid"),
                           (16, "CARD64", "signal_value")],
                "length": 24,
            },
            "GetSemaphoreCounterValue": {
                "fields": [(8, "XID", "device_xid"), (12, "XID", "semaphore_xid")],
                "length": 16,
            },
            "GetFenceStatus": {
                "fields": [(8, "XID", "device_xid"), (12, "XID", "fence_xid")],
                "length": 16,
            },
            "WaitForFence": {
                "fields": [(8, "XID", "device_xid"), (12, "XID", "fence_xid"),
                           (16, "CARD64", "timeout_ns")],
                "length": 24,
            },
        }
        for request, contract in contracts.items():
            with self.subTest(request=request):
                if request in spec_by_request:
                    section = spec_text[request]
                else:
                    heading = re.search(r"^##\s+\d+(?:\.\d+)*\s+`" + re.escape(request) + r"`\s*$", memory, re.M)
                    self.assertIsNotNone(heading, f"{request}: normative section heading missing")
                    next_heading = re.search(r"^##\s+", memory[heading.end():], re.M)
                    section = memory[heading.start():heading.end() + next_heading.start()] if next_heading else memory[heading.start():]
                for offset, wire_type, field in contract["fields"]:
                    table_row = (
                        r"(?m)^\|\s*" + str(offset) + r"\s*\|\s*" +
                        wire_type + r"\s*\|\s*`?" + re.escape(field) +
                        r"`?[^|]*\|"
                    )
                    if re.search(table_row, section):
                        continue
                    # Some normative request sections use prose offset entries
                    # rather than a Markdown field table. Validate the same
                    # offset/type/name contract in either representation.
                    if wire_type == "XID":
                        label = {
                            "device_xid": "Device-XID",
                            "buffer_xid": "Buffer-XID",
                            "memory_xid": "Memory-XID",
                            "command_pool_xid": "Command-Pool-XID",
                            "semaphore_xid": "Semaphore-XID",
                            "command_buffer_xid": "Command-Buffer-XID",
                            "fence_xid": "Fence-XID",
                        }[field]
                        prose_row = r"(?m)^- Offset " + str(offset) + r": " + re.escape(label) + r"\s*$"
                    else:
                        prose_row = (
                            r"(?m)^- Offset " + str(offset) + r": `" +
                            wire_type + r" " + re.escape(field) + r"(?:\s*=\s*0)?`\s*$"
                        )
                    self.assertTrue(
                        re.search(table_row, section) or re.search(prose_row, section),
                        f"{request}: {field} must be {wire_type} at offset {offset}",
                    )
                if isinstance(contract["length"], int):
                    self.assertRegex(section, r"(?i)(?:has a\s+)?(?:fixed\s+)?total length(?: of)?:?\s*" + str(contract["length"]) + r"\s*bytes?\b",
                                     f"{request}: normative fixed length changed")
                else:
                    self.assertIn(contract["length"], section, f"{request}: normative variable-length formula changed")
                vectors = [v for v in self.vectors if v["request"] == request]
                self.assertTrue(vectors, f"{request}: missing golden vectors")
                for vector in vectors:
                    if isinstance(contract["length"], int):
                        expected_length = contract["length"]
                    else:
                        n = vector["fields"]["data_length"]
                        expected_length = 28 + ((n + 3) & ~3)
                    self.assertEqual(vector["length_bytes"], expected_length,
                                     f"{vector['name']}: fixture length disagrees with normative length contract")

    def test_golden_scalar_values_decode_against_normative_fields(self) -> None:
        """Decode every scalar in every fixture using normative offsets and types."""
        import re
        spec_by_request = {
            "CreateCommandPool": "command-recording.md",
            "CreateSemaphore": "synchronization.md",
            "DestroySemaphore": "synchronization.md",
            "DestroyCommandPool": "command-recording.md",
            "ResetCommandBuffer": "command-recording.md",
            "DestroyFence": "synchronization.md",
            "CreateFence": "synchronization.md",
            "ResetFence": "synchronization.md",
            "SignalSemaphore": "synchronization.md",
            "GetSemaphoreCounterValue": "synchronization.md",
            "GetFenceStatus": "synchronization.md",
            "WaitForFence": "synchronization.md",
        }
        spec_text = {
            name: (ROOT / "spec" / path).read_text(encoding="utf-8")
            for name, path in spec_by_request.items()
        }
        memory = (ROOT / "spec" / "memory-buffers.md").read_text(encoding="utf-8")
        contracts = {
            "CreateBuffer": [
                (8, "XID", "device_xid", "I"),
                (12, "XID", "buffer_xid", "I"),
                (16, "CARD64", "size", "Q"),
                (24, "CARD32", "usage_flags", "I"),
                (28, "CARD32", "reserved", "I"),
            ],
            "WriteBuffer": [
                (8, "XID", "device_xid", "I"),
                (12, "XID", "buffer_xid", "I"),
                (16, "CARD64", "buffer_offset", "Q"),
                (24, "CARD32", "data_length", "I"),
            ],
            "ReadBuffer": [
                (8, "XID", "device_xid", "I"),
                (12, "XID", "buffer_xid", "I"),
                (16, "CARD64", "buffer_offset", "Q"),
                (24, "CARD32", "data_length", "I"),
            ],
            "AllocateMemory": [
                (8, "XID", "device_xid", "I"),
                (12, "XID", "memory_xid", "I"),
                (16, "CARD64", "allocation_size", "Q"),
                (24, "CARD32", "memory_type_index", "I"),
                (28, "CARD32", "reserved", "I"),
            ],
            "FreeMemory": [
                (8, "XID", "device_xid", "I"),
                (12, "XID", "memory_xid", "I"),
            ],
            "BindBufferMemory": [
                (8, "XID", "device_xid", "I"),
                (12, "XID", "buffer_xid", "I"),
                (16, "XID", "memory_xid", "I"),
                (20, "CARD64", "memory_offset", "Q"),
            ],
            "CreateCommandPool": [
                (8, "XID", "device_xid", "I"),
                (12, "XID", "command_pool_xid", "I"),
                (16, "CARD32", "queue_family_index", "I"),
                (20, "CARD32", "flags", "I"),
            ],
            "CreateSemaphore": [
                (8, "XID", "device_xid", "I"),
                (12, "XID", "semaphore_xid", "I"),
                (16, "CARD32", "semaphore_type", "I"),
                (20, "CARD64", "initial_value", "Q"),
            ],
            "DestroySemaphore": [
                (8, "XID", "device_xid", "I"),
                (12, "XID", "semaphore_xid", "I"),
            ],
            "DestroyCommandPool": [
                (8, "XID", "device_xid", "I"),
                (12, "XID", "command_pool_xid", "I"),
            ],
            "ResetCommandBuffer": [
                (8, "XID", "device_xid", "I"),
                (12, "XID", "command_buffer_xid", "I"),
            ],
            "DestroyFence": [
                (8, "XID", "device_xid", "I"),
                (12, "XID", "fence_xid", "I"),
            ],
            "CreateFence": [
                (8, "XID", "device_xid", "I"),
                (12, "XID", "fence_xid", "I"),
                (16, "CARD32", "create_flags", "I"),
                (20, "CARD32", "reserved", "I"),
            ],
            "ResetFence": [
                (8, "XID", "device_xid", "I"),
                (12, "XID", "fence_xid", "I"),
            ],
            "SignalSemaphore": [
                (8, "XID", "device_xid", "I"),
                (12, "XID", "semaphore_xid", "I"),
                (16, "CARD64", "signal_value", "Q"),
            ],
            "GetSemaphoreCounterValue": [
                (8, "XID", "device_xid", "I"),
                (12, "XID", "semaphore_xid", "I"),
            ],
            "GetFenceStatus": [
                (8, "XID", "device_xid", "I"),
                (12, "XID", "fence_xid", "I"),
            ],
            "WaitForFence": [
                (8, "XID", "device_xid", "I"),
                (12, "XID", "fence_xid", "I"),
                (16, "CARD64", "timeout_ns", "Q"),
            ],
        }
        sizes = {"XID": 4, "CARD32": 4, "CARD64": 8}
        for vector in self.vectors:
            request = vector["request"]
            if request in spec_by_request:
                section = spec_text[request]
            else:
                section_match = re.search(
                    r"^##\s+\d+(?:\.\d+)*\s+`" + re.escape(request) + r"`\s*$",
                    memory, re.M,
                )
                self.assertIsNotNone(section_match, f"{request}: normative section missing")
                next_heading = re.search(r"^##\s+", memory[section_match.end():], re.M)
                section = memory[section_match.start():section_match.end() + next_heading.start()] if next_heading else memory[section_match.start():]
            wire = bytes.fromhex(vector["wire_hex"])
            endian = "<" if vector["byte_order"] == "little" else ">"
            with self.subTest(vector=vector["name"]):
                # The common header also contains normative scalar values.
                self.assertEqual(wire[0], vector["major_opcode"])
                self.assertEqual(wire[1], 0, "X11 data byte is reserved zero")
                self.assertEqual(struct.unpack_from(endian + "H", wire, 2)[0], vector["length_bytes"] // 4)
                self.assertEqual(wire[4], vector["subopcode"])
                self.assertEqual(wire[5], vector["flags"])
                self.assertEqual(struct.unpack_from(endian + "H", wire, 6)[0], 0, "common-header reserved field")
                for offset, wire_type, field, fmt in contracts[request]:
                    # Ensure the normative document still names the same field/type/offset.
                    table_row = (
                        r"(?m)^\|\s*" + str(offset) + r"\s*\|\s*" + wire_type +
                        r"\s*\|\s*`?" + re.escape(field) + r"`?[^|]*\|"
                    )
                    prose_row = (
                        r"(?m)^- Offset " + str(offset) + r": `?" + wire_type +
                        r"\s+" + re.escape(field) + r"(?:\s*=\s*0)?`?\s*$"
                    )
                    if wire_type == "XID":
                        label = {
                            "device_xid": "Device-XID",
                            "buffer_xid": "Buffer-XID",
                            "memory_xid": "Memory-XID",
                            "command_pool_xid": "Command-Pool-XID",
                            "semaphore_xid": "Semaphore-XID",
                            "command_buffer_xid": "Command-Buffer-XID",
                            "fence_xid": "Fence-XID",
                        }[field]
                        prose_row = r"(?m)^- Offset " + str(offset) + r": " + re.escape(label) + r"\s*$"
                    self.assertTrue(
                        re.search(table_row, section) or re.search(prose_row, section),
                        f"{request}: normative spec must define {wire_type} {field} at offset {offset}",
                    )
                    value = struct.unpack_from(endian + fmt, wire, offset)[0]
                    self.assertEqual(value, vector["fields"][field], f"{field}: decoded wire value differs from fixture")
                    self.assertEqual(sizes[wire_type], struct.calcsize(fmt))
                fields = vector["fields"]
                if request == "CreateBuffer":
                    self.assertGreater(fields["size"], 0, "size MUST be positive")
                    self.assertNotEqual(fields["usage_flags"], 0, "usage_flags MUST select at least one usage bit")
                    self.assertEqual(fields["usage_flags"] & ~0x7F, 0, "usage_flags bits 7..31 are reserved")
                    self.assertEqual(fields["reserved"], 0, "reserved MUST be zero")
                elif request in ("WriteBuffer", "ReadBuffer"):
                    self.assertGreater(fields["data_length"], 0, "data_length MUST be positive")
                    if request == "WriteBuffer":
                        payload = bytes.fromhex(fields["payload_hex"])
                        self.assertEqual(len(payload), fields["data_length"])
                        self.assertEqual(wire[28:28 + fields["data_length"]], payload)
                        padding = wire[28 + fields["data_length"]:]
                        self.assertEqual(padding, bytes((-fields["data_length"]) % 4))
                        self.assertEqual(padding, bytes.fromhex(fields["padding_hex"]))
                elif request == "AllocateMemory":
                    self.assertGreater(fields["allocation_size"], 0, "allocation_size MUST be positive")
                    self.assertEqual(fields["reserved"], 0, "reserved MUST be zero")
                elif request == "CreateCommandPool":
                    self.assertEqual(fields["flags"] & ~0x3, 0, "reserved command-pool flag bits MUST be zero")
                elif request == "CreateSemaphore":
                    self.assertIn(fields["semaphore_type"], (0, 1))
                    if fields["semaphore_type"] == 0:
                        self.assertEqual(fields["initial_value"], 0, "binary semaphore initial_value MUST be zero")
    def test_golden_vectors_match_central_request_registry(self) -> None:
        # Golden bytes can otherwise remain internally consistent while the
        # normative subopcode assignment changes underneath them.
        self.assertTrue(self.request_opcodes)
        values = list(self.request_opcodes.values())
        self.assertEqual(len(values), len(set(values)), "registry subopcodes must be unique")
        self.assertNotIn(0, values, "subopcode zero is reserved")
        for vector in self.vectors:
            with self.subTest(vector=vector["name"]):
                self.assertIn(vector["request"], self.request_opcodes)
                self.assertEqual(
                    vector["subopcode"], self.request_opcodes[vector["request"]],
                    "golden vector subopcode must match registries/request-subopcodes.md",
                )
                self.assertEqual(
                    vector["subopcode"], bytes.fromhex(vector["wire_hex"])[4],
                    "wire byte 4 must encode the registry subopcode",
                )

    def test_both_byte_orders_are_present(self) -> None:
        self.assertEqual(
            {vector["byte_order"] for vector in self.vectors},
            {"little", "big"},
        )

    def test_variable_payload_padding_is_zero(self) -> None:
        writes = [v for v in self.vectors if v["request"] == "WriteBuffer"]
        self.assertTrue(writes)
        for vector in writes:
            with self.subTest(vector=vector["name"]):
                wire = encode_request(vector)
                self.assertEqual(wire[28 + vector["fields"]["data_length"]:], bytes.fromhex(vector["fields"]["padding_hex"]))


    def test_variable_payload_boundary_vectors(self) -> None:
        writes = [v for v in self.vectors if v["request"] == "WriteBuffer"]
        observed = {(v["fields"]["data_length"], v["byte_order"]) for v in writes}
        for size in (1, 3, 4, 5):
            for order in ("little", "big"):
                self.assertIn((size, order), observed)
        for vector in writes:
            with self.subTest(vector=vector["name"]):
                wire = encode_request(vector)
                validate_request_wire(wire, vector["byte_order"])
                self.assertEqual(len(wire), 28 + ((vector["fields"]["data_length"] + 3) & ~3))

    def test_rejects_unknown_byte_order_in_encoder_and_validator(self) -> None:
        vector = next(v for v in self.vectors if v["request"] == "ReadBuffer")
        import copy
        invalid = copy.deepcopy(vector)
        invalid["byte_order"] = "middle"
        with self.assertRaisesRegex(ValueError, "byte order"):
            encode_request(invalid)
        with self.assertRaisesRegex(ValueError, "byte order"):
            validate_request_wire(encode_request(vector), "middle")

    def test_rejects_reserved_zero_subopcode(self) -> None:
        vector = next(v for v in self.vectors if v["request"] == "ReadBuffer")
        wire = bytearray(encode_request(vector))
        wire[4] = 0
        with self.assertRaisesRegex(ValueError, "subopcode zero is reserved"):
            validate_request_wire(bytes(wire), vector["byte_order"])

    def test_rejects_non_extension_major_opcode(self) -> None:
        vector = next(v for v in self.vectors if v["request"] == "ReadBuffer")
        for opcode in (0, 127, 256):
            invalid = vector.copy()
            invalid["major_opcode"] = opcode
            with self.subTest(opcode=opcode):
                with self.assertRaisesRegex(ValueError, "extension major opcode"):
                    encode_request(invalid)

        wire = bytearray(encode_request(vector))
        wire[0] = 127
        with self.assertRaisesRegex(ValueError, "extension major opcode"):
            validate_request_wire(bytes(wire), vector["byte_order"])

    def test_rejects_truncated_common_header(self) -> None:
        for size in range(8):
            with self.subTest(size=size):
                with self.assertRaisesRegex(ValueError, "truncated"):
                    validate_request_wire(bytes(size), "little")

    def test_rejects_raw_declared_length_mismatch(self) -> None:
        vector = next(v for v in self.vectors if v["request"] == "ReadBuffer")
        wire = bytearray(encode_request(vector))
        wire[2:4] = (len(wire) // 4 + 1).to_bytes(2, vector["byte_order"])
        with self.assertRaisesRegex(ValueError, "declared request length"):
            validate_request_wire(bytes(wire), vector["byte_order"])

    def test_rejects_nonzero_raw_header_reserved_fields(self) -> None:
        vector = next(v for v in self.vectors if v["request"] == "ReadBuffer")
        wire = bytearray(encode_request(vector))
        wire[6] = 1
        with self.assertRaisesRegex(ValueError, "reserved common-header"):
            validate_request_wire(bytes(wire), vector["byte_order"])

    def test_rejects_nonzero_raw_x11_data_and_xaverius_flags(self) -> None:
        vector = next(v for v in self.vectors if v["request"] == "ReadBuffer")
        for offset, value, message in (
            (1, 1, "X11 data byte"),
            (5, 1, "reserved flags"),
        ):
            with self.subTest(offset=offset):
                wire = bytearray(encode_request(vector))
                wire[offset] = value
                with self.assertRaisesRegex(ValueError, message):
                    validate_request_wire(bytes(wire), vector["byte_order"])

    def test_rejects_zero_length_raw_request_before_common_header(self) -> None:
        # The normative framing rule reserves length=0 for BIG-REQUESTS,
        # whose extended length would overlap the XAverius common header.
        vector = next(v for v in self.vectors if v["request"] == "ReadBuffer")
        wire = bytearray(encode_request(vector))
        wire[2:4] = bytes(2)
        with self.assertRaisesRegex(ValueError, "zero request length"):
            validate_request_wire(bytes(wire), vector["byte_order"])

    def test_rejects_non_word_aligned_raw_request(self) -> None:
        vector = next(v for v in self.vectors if v["request"] == "ReadBuffer")
        wire = encode_request(vector) + bytes(1)
        with self.assertRaisesRegex(ValueError, "divisible by four"):
            validate_request_wire(wire, vector["byte_order"])

    def test_rejects_declared_length_mismatch(self) -> None:
        vector = next(v.copy() for v in self.vectors if v["request"] == "ReadBuffer")
        vector["length_bytes"] += 4
        with self.assertRaisesRegex(ValueError, "declared"):
            encode_request(vector)

    def test_rejects_nonzero_write_padding(self) -> None:
        import copy
        vector = copy.deepcopy(next(v for v in self.vectors if v["request"] == "WriteBuffer"))
        vector["fields"]["padding_hex"] = "7f"
        with self.assertRaisesRegex(ValueError, "padding"):
            encode_request(vector)

    def test_rejects_write_payload_length_mismatch(self) -> None:
        import copy
        vector = copy.deepcopy(next(v for v in self.vectors if v["request"] == "WriteBuffer"))
        vector["fields"]["data_length"] = 4
        with self.assertRaisesRegex(ValueError, "data_length"):
            encode_request(vector)

    def test_rejects_nonzero_create_buffer_reserved_field(self) -> None:
        import copy
        vector = copy.deepcopy(next(v for v in self.vectors if v["request"] == "CreateBuffer"))
        vector["fields"]["reserved"] = 1
        with self.assertRaisesRegex(ValueError, "reserved"):
            encode_request(vector)


if __name__ == "__main__":
    unittest.main(verbosity=2)
