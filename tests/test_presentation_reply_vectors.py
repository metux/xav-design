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


def validate_presentation_reply(
    kind: str,
    wire: bytes,
    order: str,
    *,
    expected_image_count: int | None = None,
) -> None:
    if order not in ("little", "big"):
        raise ValueError("unknown byte order")
    if kind not in ("capabilities", "create_swapchain", "acquire", "queue_present"):
        raise ValueError("unknown presentation reply kind")
    if len(wire) < 32 or len(wire) % 4 or wire[0] != 1 or wire[1] != 0:
        raise ValueError("invalid X11 reply framing")
    endian = "<" if order == "little" else ">"
    declared = struct.unpack_from(endian + "I", wire, 4)[0]
    if 32 + 4 * declared != len(wire):
        raise ValueError("reply length does not match packet size")
    if kind == "capabilities":
        if len(wire) < 64:
            raise ValueError("capabilities reply shorter than fixed fields")
        status = u32(wire, 8, order)
        if status not in range(4):
            raise ValueError("invalid capabilities status")
        if status:
            if len(wire) != 64 or declared != 8 or any(wire[12:64]):
                raise ValueError("invalid capabilities failure payload")
        else:
            formats, modes, families = (u32(wire, off, order) for off in (48, 52, 60))
            expected = 64 + 8 * formats + 4 * modes + 8 * families
            if len(wire) != expected or declared != 8 + 2 * formats + modes + 2 * families:
                raise ValueError("capabilities record counts do not match reply length")
            if u32(wire, 12, order) not in (0, 1):
                raise ValueError("invalid present_supported value")
            current_width, current_height = u32(wire, 16, order), u32(wire, 20, order)
            min_width, min_height = u32(wire, 32, order), u32(wire, 36, order)
            max_width, max_height = u32(wire, 40, order), u32(wire, 44, order)
            if current_width == 0 or current_height == 0:
                raise ValueError("successful capabilities reply has zero current extent")
            if (min_width == 0 or min_height == 0 or
                    max_width < min_width or max_height < min_height):
                raise ValueError("successful capabilities reply has invalid extent bounds")
            min_images, max_images = u32(wire, 24, order), u32(wire, 28, order)
            if min_images == 0 or (max_images != 0 and max_images < min_images):
                raise ValueError("successful capabilities reply has invalid image-count bounds")
            if families == 0:
                raise ValueError("successful capabilities reply has zero queue families")
            start = 64 + 8 * formats + 4 * modes
            family_indices = []
            family_support = []
            for off in range(start, len(wire), 8):
                family_index = u32(wire, off, order)
                supported = u32(wire, off + 4, order)
                if supported not in (0, 1):
                    raise ValueError("invalid queue-family present_supported value")
                family_indices.append(family_index)
                family_support.append(supported)
            if family_indices != list(range(families)):
                raise ValueError("queue-family indices must cover every family in ascending order")
            if u32(wire, 12, order) != int(any(family_support)):
                raise ValueError("aggregate present_supported does not match queue-family records")
    else:
        size, words, statuses = {
            "create_swapchain": (40, 2, 6),
            "acquire": (44, 3, 7),
            "queue_present": (36, 1, 4),
        }[kind]
        if len(wire) != size or declared != words:
            raise ValueError("invalid fixed presentation reply size")
        status = u32(wire, 32, order)
        if status not in range(statuses):
            raise ValueError("invalid presentation status")
        if kind == "create_swapchain" and status == 0 and u32(wire, 36, order) == 0:
            raise ValueError("successful CreateSwapchain has zero image count")
        if (kind == "create_swapchain" and status == 0 and
                expected_image_count is not None and
                u32(wire, 36, order) != expected_image_count):
            raise ValueError("CreateSwapchain image count does not match request")
        if kind == "create_swapchain" and status and u32(wire, 36, order):
            raise ValueError("failed CreateSwapchain has nonzero image count")
        if kind == "acquire":
            if u32(wire, 40, order):
                raise ValueError("AcquireNextImage reserved word is nonzero")
            if status and u32(wire, 36, order):
                raise ValueError("failed AcquireNextImage has nonzero image index")


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

    def test_create_swapchain_success_count_matches_request(self) -> None:
        for order in ("little", "big"):
            with self.subTest(order=order):
                wire = encode_create_swapchain_reply(order, 0, 3)
                validate_presentation_reply(
                    "create_swapchain", wire, order, expected_image_count=3
                )
                with self.assertRaisesRegex(
                    ValueError, "CreateSwapchain image count does not match request"
                ):
                    validate_presentation_reply(
                        "create_swapchain", wire, order, expected_image_count=2
                    )

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


    def test_all_documented_presentation_reply_statuses_have_valid_wire_shapes(self) -> None:
        # Status values are separate per-reply namespaces. Exercise every
        # normative value, not only representative failure codes.
        cases = (
            ("capabilities", range(4), 64, 8),
            ("create_swapchain", range(6), 40, 2),
            ("acquire", range(7), 44, 3),
            ("queue_present", range(4), 36, 1),
        )
        for order in ("little", "big"):
            for kind, statuses, total, reply_words in cases:
                for status in statuses:
                    with self.subTest(order=order, kind=kind, status=status):
                        if kind == "capabilities":
                            wire = encode_capabilities(order, status=status)
                            # Capabilities status 0 has variable records; the
                            # failure statuses must carry only the zeroed base.
                            if status == 0:
                                self.assertEqual(len(wire), 92)
                            else:
                                self.assertEqual(len(wire), total)
                                self.assertEqual(u32(wire, 8, order), status)
                                self.assertEqual(wire[12:64], bytes(52))
                        elif kind == "create_swapchain":
                            wire = encode_create_swapchain_reply(
                                order, status, 2 if status == 0 else 0
                            )
                            self.assertEqual(len(wire), total)
                            self.assertEqual(u32(wire, 32, order), status)
                            self.assertEqual(u32(wire, 36, order), 2 if status == 0 else 0)
                        elif kind == "acquire":
                            wire = encode_acquire_reply(order, status, 1 if status == 0 else 0)
                            self.assertEqual(len(wire), total)
                            self.assertEqual(u32(wire, 32, order), status)
                            self.assertEqual(u32(wire, 36, order), 1 if status == 0 else 0)
                            self.assertEqual(u32(wire, 40, order), 0)
                        else:
                            wire = encode_queue_present_reply(order, status)
                            self.assertEqual(len(wire), total)
                        expected_words = 15 if kind == "capabilities" and status == 0 else reply_words
                        self.assertEqual(u32(wire, 4, order), expected_words)
                        self.assertEqual(32 + 4 * u32(wire, 4, order), len(wire))


    def test_malformed_reply_wire_bytes_are_rejected(self) -> None:
        for order in ("little", "big"):
            endian = "<" if order == "little" else ">"
            valid = {
                "capabilities": encode_capabilities(order),
                "create_swapchain": encode_create_swapchain_reply(order, 0, 3),
                "acquire": encode_acquire_reply(order, 0, 2),
                "queue_present": encode_queue_present_reply(order, 0),
            }
            for kind, wire in valid.items():
                with self.subTest(order=order, kind=kind):
                    validate_presentation_reply(kind, wire, order)
            cases = (
                ("capabilities", 4, "I", 99, "reply length does not match packet size"),
                ("capabilities", 8, "I", 9, "invalid capabilities status"),
                ("capabilities", 48, "I", 99, "capabilities record counts do not match reply length"),
                ("capabilities", 12, "I", 7, "invalid present_supported value"),
                ("capabilities", 16, "I", 0, "successful capabilities reply has zero current extent"),
                ("capabilities", 32, "I", 0, "successful capabilities reply has invalid extent bounds"),
                ("capabilities", 40, "I", 0, "successful capabilities reply has invalid extent bounds"),
                ("capabilities", 24, "I", 0, "successful capabilities reply has invalid image-count bounds"),
                ("capabilities", 28, "I", 1, "successful capabilities reply has invalid image-count bounds"),
                ("capabilities", 80, "I", 7, "invalid queue-family present_supported value"),
                ("capabilities", 12, "I", 0, "aggregate present_supported does not match queue-family records"),
                ("capabilities", 76, "I", 1, "queue-family indices must cover every family in ascending order"),
                ("capabilities", 84, "I", 0, "queue-family indices must cover every family in ascending order"),
                ("create_swapchain", 4, "I", 1, "reply length does not match packet size"),
                ("create_swapchain", 32, "I", 6, "invalid presentation status"),
                ("create_swapchain", 36, "I", 0, "successful CreateSwapchain has zero image count"),
                ("create_swapchain", 36, "I", 1, "failed CreateSwapchain has nonzero image count"),
                ("acquire", 32, "I", 7, "invalid presentation status"),
                ("acquire", 36, "I", 1, "failed AcquireNextImage has nonzero image index"),
                ("acquire", 40, "I", 1, "AcquireNextImage reserved word is nonzero"),
                ("queue_present", 32, "I", 4, "invalid presentation status"),
            )
            for kind, offset, fmt, value, message in cases:
                with self.subTest(order=order, kind=kind, offset=offset):
                    wire = bytearray(valid[kind])
                    # Status-dependent payload checks need a failure reply as
                    # their baseline; mutating a SUCCESS payload alone cannot
                    # exercise a failed-operation invariant.
                    if kind == "create_swapchain" and message == "failed CreateSwapchain has nonzero image count":
                        struct.pack_into(endian + "I", wire, 32, 4)
                    if kind == "acquire" and message == "failed AcquireNextImage has nonzero image index":
                        struct.pack_into(endian + "I", wire, 32, 3)
                    struct.pack_into(endian + fmt, wire, offset, value)
                    with self.assertRaisesRegex(ValueError, message):
                        validate_presentation_reply(kind, bytes(wire), order)

    def test_successful_capabilities_rejects_zero_queue_families(self) -> None:
        for order in ("little", "big"):
            with self.subTest(order=order):
                wire = bytearray(encode_capabilities(order))
                # Drop the two queue-family records and update both the
                # declared length and count, keeping the packet well-framed.
                del wire[-16:]
                endian = "<" if order == "little" else ">"
                struct.pack_into(endian + "I", wire, 4, 11)
                struct.pack_into(endian + "I", wire, 12, 0)
                struct.pack_into(endian + "I", wire, 60, 0)
                with self.assertRaisesRegex(ValueError, "successful capabilities reply has zero queue families"):
                    validate_presentation_reply("capabilities", bytes(wire), order)

    def test_capability_failure_rejects_nonzero_payload(self) -> None:
        for order in ("little", "big"):
            with self.subTest(order=order):
                wire = bytearray(encode_capabilities(order, status=1))
                struct.pack_into("<I" if order == "little" else ">I", wire, 12, 1)
                with self.assertRaisesRegex(ValueError, "invalid capabilities failure payload"):
                    validate_presentation_reply("capabilities", bytes(wire), order)

    def test_reply_validator_rejects_unknown_kind_and_byte_order(self) -> None:
        wire = encode_queue_present_reply("little", 0)
        with self.assertRaisesRegex(ValueError, "unknown byte order"):
            validate_presentation_reply("queue_present", wire, "middle")
        with self.assertRaisesRegex(ValueError, "unknown presentation reply kind"):
            validate_presentation_reply("future_reply", wire, "little")


if __name__ == "__main__":
    unittest.main()
