#!/usr/bin/env python3
"""Golden Phase-1 request vectors and malformed raw-wire rejection tests.

These are offline ABI fixtures. They validate the reference wire contract,
not a live X server implementation.
"""
from __future__ import annotations

import json
import math
import re
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "phase1-request-vectors.json"
DEVICES = (ROOT / "spec" / "devices.md").read_text(encoding="utf-8")
MEMORY = (ROOT / "spec" / "memory-buffers.md").read_text(encoding="utf-8")
WIRE = (ROOT / "spec" / "wire-protocol.md").read_text(encoding="utf-8")
REGISTRY = (ROOT / "registries" / "request-subopcodes.md").read_text(encoding="utf-8")

SUBOPCODES = {
    "EnumeratePhysicalDevices": 1,
    "GetPhysicalDeviceProperty": 2,
    "GetPhysicalDeviceQueueFamilyProperties": 3,
    "CreateDevice": 4,
    "CreateDefaultDevice": 5,
    "DestroyDevice": 6,
    "GetPhysicalDeviceMemoryProperties": 7,
}
FIXED_LENGTHS = {
    "EnumeratePhysicalDevices": 8,
    "GetPhysicalDeviceProperty": 16,
    "GetPhysicalDeviceQueueFamilyProperties": 12,
    "DestroyDevice": 12,
    "GetPhysicalDeviceMemoryProperties": 12,
}


def endian(order: str) -> str:
    if order not in ("little", "big"):
        raise ValueError("unknown byte order")
    return "<" if order == "little" else ">"


def u16(wire: bytes, offset: int, order: str) -> int:
    return struct.unpack_from(endian(order) + "H", wire, offset)[0]


def u32(wire: bytes, offset: int, order: str) -> int:
    return struct.unpack_from(endian(order) + "I", wire, offset)[0]


def validate_common(wire: bytes, order: str) -> int:
    if len(wire) < 8:
        raise ValueError("truncated common header")
    if len(wire) % 4:
        raise ValueError("request length must be divisible by four")
    if wire[0] < 128:
        raise ValueError("extension major opcode")
    words = u16(wire, 2, order)
    if words == 0:
        raise ValueError("zero request length")
    if words * 4 != len(wire):
        raise ValueError("declared length mismatch")
    if wire[1] != 0:
        raise ValueError("X11 data")
    if wire[5] != 0:
        raise ValueError("flags")
    if wire[6:8] != b"\x00\x00":
        raise ValueError("common reserved")
    if wire[4] == 0:
        raise ValueError("subopcode zero")
    return wire[4]


def validate_phase1(wire: bytes, order: str) -> None:
    sub = validate_common(wire, order)
    request = next((name for name, value in SUBOPCODES.items() if value == sub), None)
    if request is None:
        raise ValueError("unknown subopcode")
    if request in FIXED_LENGTHS:
        if len(wire) != FIXED_LENGTHS[request]:
            raise ValueError("request exact length")
        if request == "GetPhysicalDeviceProperty":
            return
        return
    if request == "CreateDefaultDevice":
        if len(wire) < 20:
            raise ValueError("CreateDefaultDevice length")
        count = u16(wire, 12, order)
        if count < 1 or len(wire) != 16 + 4 * count:
            raise ValueError("CreateDefaultDevice length")
        if u16(wire, 14, order) != 0:
            raise ValueError("CreateDefaultDevice reserved")
        for i in range(count):
            p = struct.unpack_from(endian(order) + "f", wire, 16 + 4 * i)[0]
            if not math.isfinite(p) or not 0.0 <= p <= 1.0:
                raise ValueError("CreateDefaultDevice priority")
        return
    if request == "CreateDevice":
        if len(wire) < 24:
            raise ValueError("CreateDevice length")
        qcount, fcount, ecount = (u16(wire, off, order) for off in (16, 18, 20))
        if u16(wire, 22, order) != 0:
            raise ValueError("CreateDevice reserved")
        off = 24
        seen_families = set()
        for _ in range(qcount):
            if off + 8 > len(wire):
                raise ValueError("CreateDevice length")
            family, count, reserved = u32(wire, off, order), u16(wire, off + 4, order), u16(wire, off + 6, order)
            if count < 1 or reserved != 0 or family in seen_families:
                raise ValueError("CreateDevice queue reserved/scalar")
            seen_families.add(family)
            off += 8 + 4 * count
            if off > len(wire):
                raise ValueError("CreateDevice length")
            for i in range(count):
                p = struct.unpack_from(endian(order) + "f", wire, off - 4 * count + 4 * i)[0]
                if not math.isfinite(p) or not 0.0 <= p <= 1.0:
                    raise ValueError("CreateDevice priority")
        seen_features = set()
        for _ in range(fcount):
            if off + 8 > len(wire):
                raise ValueError("CreateDevice length")
            feature, enabled = u32(wire, off, order), u32(wire, off + 4, order)
            if feature in seen_features or enabled != 1:
                raise ValueError("CreateDevice feature")
            seen_features.add(feature)
            off += 8
        seen_extensions = set()
        for _ in range(ecount):
            if off + 4 > len(wire):
                raise ValueError("CreateDevice length")
            n, reserved = u16(wire, off, order), u16(wire, off + 2, order)
            padded = (n + 3) & ~3
            if n < 1 or n > 255 or reserved != 0 or off + 4 + padded > len(wire):
                raise ValueError("CreateDevice extension reserved/length")
            name = wire[off + 4:off + 4 + n]
            padding = wire[off + 4 + n:off + 4 + padded]
            if any(padding) or b"\x00" in name or name in seen_extensions:
                raise ValueError("CreateDevice extension padding/value")
            if not re.fullmatch(rb"VK_[A-Za-z0-9_]+_[A-Za-z0-9_]+", name):
                raise ValueError("CreateDevice extension syntax")
            seen_extensions.add(name)
            off += 4 + padded
        if qcount < 1 or off != len(wire):
            raise ValueError("CreateDevice exact length")
        return
    raise ValueError("unhandled Phase-1 request")


class Phase1GoldenRequestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vectors = json.loads(FIXTURE.read_text(encoding="utf-8"))["vectors"]

    def test_golden_frames_and_subopcodes(self):
        self.assertEqual({v["byte_order"] for v in self.vectors}, {"little", "big"})
        self.assertEqual({v["request"] for v in self.vectors}, set(SUBOPCODES))
        self.assertEqual(len(self.vectors), 14)
        for v in self.vectors:
            with self.subTest(vector=v["name"]):
                wire = bytes.fromhex(v["wire_hex"])
                self.assertEqual(len(wire), v["length_bytes"])
                self.assertEqual(wire[0], 0x90)  # fixture-only major opcode
                self.assertEqual(wire[4], SUBOPCODES[v["request"]])
                self.assertEqual(v["subopcode"], SUBOPCODES[v["request"]])
                self.assertEqual(validate_common(wire, v["byte_order"]), SUBOPCODES[v["request"]])
                validate_phase1(wire, v["byte_order"])
                fields = v["fields"]
                order = v["byte_order"]
                if v["request"] == "GetPhysicalDeviceProperty":
                    self.assertEqual(u32(wire, 8, order), fields["physical_device_xid"])
                    self.assertEqual(u32(wire, 12, order), fields["property_atom"])
                elif v["request"] in ("GetPhysicalDeviceQueueFamilyProperties", "GetPhysicalDeviceMemoryProperties"):
                    self.assertEqual(u32(wire, 8, order), fields["physical_device_xid"])
                elif v["request"] == "DestroyDevice":
                    self.assertEqual(u32(wire, 8, order), fields["device_xid"])
                elif v["request"] == "CreateDefaultDevice":
                    self.assertEqual(u32(wire, 8, order), fields["device_xid"])
                    self.assertEqual(u16(wire, 12, order), fields["queue_count"])
                    self.assertEqual(u16(wire, 14, order), fields["reserved"])
                    self.assertEqual([struct.unpack_from(endian(order) + "f", wire, 16 + 4*i)[0] for i in range(fields["queue_count"])], fields["priorities"])
                elif v["request"] == "CreateDevice":
                    for offset, field in ((8, "device_xid"), (12, "physical_device_xid")):
                        self.assertEqual(u32(wire, offset, order), fields[field])
                    for offset, field in ((16, "queue_family_request_count"), (18, "feature_request_count"), (20, "device_extension_count"), (22, "reserved")):
                        self.assertEqual(u16(wire, offset, order), fields[field])
                    self.assertEqual(u32(wire, 24, order), fields["queue_family_index"])
                    self.assertEqual(u16(wire, 28, order), fields["queue_count"])
                    self.assertEqual(u16(wire, 30, order), fields["queue_reserved"])
                    self.assertEqual(struct.unpack_from(endian(order) + "f", wire, 32)[0], fields["queue_priority"])
                    self.assertEqual(u16(wire, 36, order), fields["extension_name_length"])
                    self.assertEqual(u16(wire, 38, order), fields["extension_reserved"])
                    self.assertEqual(wire[40:46].decode("ascii"), fields["extension_name"])
                    self.assertEqual(wire[46:48].hex(), fields["extension_padding_hex"])
                self.assertEqual(u16(wire, 2, v["byte_order"]), len(wire) // 4)

    def test_layouts_match_registry_and_normative_documents(self):
        for request, opcode in SUBOPCODES.items():
            with self.subTest(request=request):
                self.assertRegex(REGISTRY, rf"(?m)^\|\s*`{request}`\s*\|\s*{opcode}\s*\|")
        expected = {
            "EnumeratePhysicalDevices": (8, "no request-specific payload"),
            "GetPhysicalDeviceProperty": (16, "property_atom"),
            "GetPhysicalDeviceQueueFamilyProperties": (12, "physical-device XID at offset 8"),
            "CreateDevice": (24, "queue_family_request_count"),
            "CreateDefaultDevice": (16, "queue_count"),
            "DestroyDevice": (12, "device XID"),
            "GetPhysicalDeviceMemoryProperties": (12, "physical-device XID at offset 8"),
        }
        for request, (base, marker) in expected.items():
            source = MEMORY if request == "GetPhysicalDeviceMemoryProperties" else DEVICES
            with self.subTest(request=request):
                self.assertIn(marker, source)
                if request in FIXED_LENGTHS:
                    self.assertEqual(FIXED_LENGTHS[request], base)
        self.assertIn("24 + Σ(8 + 4 * queue_count_i)", DEVICES)
        self.assertIn("16 + 4 * queue_count", DEVICES)
        self.assertIn("X11 `data`", WIRE)
        self.assertIn("CARD8  subopcode;", WIRE)
        self.assertIn("CARD8  flags;", WIRE)
        self.assertIn("CARD16 reserved;", WIRE)

    def test_each_request_rejects_wrong_exact_length(self):
        for v in self.vectors:
            wire = bytes.fromhex(v["wire_hex"])
            order = v["byte_order"]
            with self.subTest(request=v["request"], order=order, mutation="truncate"):
                bad = wire[:-4]
                with self.assertRaises(ValueError):
                    validate_phase1(bad, order)
            with self.subTest(request=v["request"], order=order, mutation="trailing"):
                bad = wire + b"\x00" * 4
                bad = bytearray(bad)
                bad[2:4] = (len(bad) // 4).to_bytes(2, order)
                with self.assertRaises(ValueError):
                    validate_phase1(bytes(bad), order)

    def test_rejects_invalid_common_header_fields_for_every_request(self):
        mutations = ((1, 1, "data"), (5, 1, "flags"), (6, 1, "reserved"))
        for v in self.vectors:
            original = bytes.fromhex(v["wire_hex"])
            for offset, value, label in mutations:
                bad = bytearray(original)
                bad[offset] = value
                with self.subTest(request=v["request"], order=v["byte_order"], field=label):
                    with self.assertRaisesRegex(ValueError, label):
                        validate_phase1(bytes(bad), v["byte_order"])
            bad = bytearray(original)
            bad[2:4] = b"\x00\x00"
            with self.subTest(request=v["request"], order=v["byte_order"], field="zero length"):
                with self.assertRaisesRegex(ValueError, "zero request length"):
                    validate_phase1(bytes(bad), v["byte_order"])

    def test_rejects_request_specific_reserved_fields(self):
        for v in self.vectors:
            order = v["byte_order"]
            be = order == "big"
            wire = bytearray.fromhex(v["wire_hex"])
            if v["request"] == "CreateDefaultDevice":
                wire[14:16] = (1).to_bytes(2, order)
            elif v["request"] == "CreateDevice":
                # Fixed request reserved field and queue-family reserved field.
                wire[22:24] = (1).to_bytes(2, order)
                with self.subTest(request=v["request"], order=order, field="top-level reserved"):
                    with self.assertRaisesRegex(ValueError, "CreateDevice reserved"):
                        validate_phase1(bytes(wire), order)
                wire = bytearray.fromhex(v["wire_hex"])
                wire[30:32] = (1).to_bytes(2, order)
            else:
                continue
            with self.subTest(request=v["request"], order=order):
                with self.assertRaisesRegex(ValueError, "reserved"):
                    validate_phase1(bytes(wire), order)
        # Extension-record reserved field is offset 38 in the positive fixture.
        for v in (x for x in self.vectors if x["request"] == "CreateDevice"):
            wire = bytearray.fromhex(v["wire_hex"])
            wire[38:40] = (1).to_bytes(2, v["byte_order"])
            with self.subTest(request=v["request"], order=v["byte_order"], field="extension reserved"):
                with self.assertRaisesRegex(ValueError, "extension reserved"):
                    validate_phase1(bytes(wire), v["byte_order"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
