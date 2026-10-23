#!/usr/bin/env python3
"""Wire-size and field checks for provisional presentation replies."""
from __future__ import annotations

import struct
import unittest


def pack32(order: str, *values: int) -> bytes:
    endian = "<" if order == "little" else ">"
    return struct.pack(endian + "I" * len(values), *values)


def reply_header(order: str, total: int, reply_length: int) -> bytearray:
    endian = "<" if order == "little" else ">"
    data = bytearray(total)
    struct.pack_into(endian + "BBH I", data, 0, 1, 0, 0x1234, reply_length)
    return data


def encode_capabilities(order: str, *, status: int = 0) -> bytes:
    if status == 0:
        fields = (0, 1, 640, 480, 2, 4, 64, 64, 1920, 1080, 1, 1, 1, 2)
        formats = ((1, 1),)
        modes = (1,)
        families = ((0, 1), (1, 0))
    else:
        fields = (status, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        formats = ()
        modes = ()
        families = ()
    reply_length = 8 + 2 * len(formats) + len(modes) + 2 * len(families)
    total = 64 + 8 * len(formats) + 4 * len(modes) + 8 * len(families)
    data = reply_header(order, total, reply_length)
    data[8:64] = pack32(order, *fields)
    cursor = 64
    for format_id, color_space_id in formats:
        data[cursor:cursor + 8] = pack32(order, format_id, color_space_id)
        cursor += 8
    for mode in modes:
        data[cursor:cursor + 4] = pack32(order, mode)
        cursor += 4
    for family_index, present_supported in families:
        data[cursor:cursor + 8] = pack32(order, family_index, present_supported)
        cursor += 8
    return bytes(data)


def encode_create_swapchain_reply(order: str, status: int, actual_count: int) -> bytes:
    data = reply_header(order, 40, 2)
    data[32:40] = pack32(order, status, actual_count)
    return bytes(data)


def encode_acquire_reply(order: str, status: int, image_index: int) -> bytes:
    data = reply_header(order, 44, 3)
    data[32:44] = pack32(order, status, image_index, 0)
    return bytes(data)


def encode_queue_present_reply(order: str, status: int) -> bytes:
    data = reply_header(order, 36, 1)
    data[32:36] = pack32(order, status)
    return bytes(data)


def u32(wire: bytes, offset: int, order: str) -> int:
    return int.from_bytes(wire[offset:offset + 4], order)


class PresentationReplyWireTests(unittest.TestCase):
    def test_capabilities_reply_formula_and_queue_family_records(self) -> None:
        for order in ("little", "big"):
            with self.subTest(order=order):
                wire = encode_capabilities(order)
                self.assertEqual(len(wire), 92)
                self.assertEqual(u32(wire, 4, order), 15)
                self.assertEqual(u32(wire, 48, order), 1)  # format_pair_count
                self.assertEqual(u32(wire, 52, order), 1)  # present_mode_count
                self.assertEqual(u32(wire, 60, order), 2)  # queue_family_count
                self.assertEqual(wire[64:72], pack32(order, 1, 1))
                self.assertEqual(wire[72:76], pack32(order, 1))
                self.assertEqual(wire[76:84], pack32(order, 0, 1))
                self.assertEqual(wire[84:92], pack32(order, 1, 0))
                self.assertEqual(32 + 4 * u32(wire, 4, order), len(wire))

    def test_capability_failure_reply_has_zeroed_payload_and_no_records(self) -> None:
        for order in ("little", "big"):
            with self.subTest(order=order):
                wire = encode_capabilities(order, status=1)
                self.assertEqual(len(wire), 64)
                self.assertEqual(u32(wire, 4, order), 8)
                self.assertEqual(u32(wire, 8, order), 1)
                self.assertEqual(wire[12:64], bytes(52))

    def test_create_swapchain_success_and_failure_counts(self) -> None:
        for order in ("little", "big"):
            with self.subTest(order=order):
                success = encode_create_swapchain_reply(order, 0, 3)
                failure = encode_create_swapchain_reply(order, 4, 0)
                self.assertEqual(len(success), 40)
                self.assertEqual(u32(success, 4, order), 2)
                self.assertEqual(u32(success, 32, order), 0)
                self.assertEqual(u32(success, 36, order), 3)
                self.assertEqual(u32(failure, 32, order), 4)
                self.assertEqual(u32(failure, 36, order), 0)

    def test_acquire_failure_has_zero_image_index_and_reserved_word(self) -> None:
        for order in ("little", "big"):
            with self.subTest(order=order):
                success = encode_acquire_reply(order, 0, 2)
                failure = encode_acquire_reply(order, 3, 0)
                self.assertEqual(len(success), 44)
                self.assertEqual(u32(success, 4, order), 3)
                self.assertEqual(u32(success, 36, order), 2)
                self.assertEqual(u32(success, 40, order), 0)
                self.assertEqual(u32(failure, 36, order), 0)
                self.assertEqual(u32(failure, 40, order), 0)

    def test_queue_present_reply_size_and_status(self) -> None:
        for order in ("little", "big"):
            with self.subTest(order=order):
                for status in range(4):
                    wire = encode_queue_present_reply(order, status)
                    self.assertEqual(len(wire), 36)
                    self.assertEqual(u32(wire, 4, order), 1)
                    self.assertEqual(u32(wire, 32, order), status)


if __name__ == "__main__":
    unittest.main()
