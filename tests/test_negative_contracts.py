#!/usr/bin/env python3
"""Regression guards for XAverius negative-test contracts.

These tests ensure the normative conformance matrix continues to specify the
high-risk precedence and atomic-rejection cases. They are contract/document
regression tests, not a substitute for tests against a live server/backend.
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class NegativeContractRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.conformance = read("spec/conformance.md")
        cls.errors = read("spec/errors.md")
        cls.presentation = read("spec/presentation.md")

    def test_common_validation_stage_order_is_normative(self) -> None:
        for phrase in ("wire structure first", "field values", "field order"):
            with self.subTest(document="error mapping", contract=phrase):
                self.assertIn(phrase, self.errors)
        self.assertIn("framing before scalar syntax", self.conformance)
        self.assertIn("scalar syntax before XID resolution", self.conformance)
        self.assertIn("XID/type/ownership checks before lifecycle", self.conformance)

    def test_create_and_batch_rejection_preserves_public_xids(self) -> None:
        required = (
            "Failed creates leave target XIDs unallocated",
            "a failed create leaves the target XID unallocated",
        )
        joined = self.conformance + self.errors
        for phrase in required:
            with self.subTest(contract=phrase):
                self.assertIn(phrase, joined)

    def test_buffer_and_descriptor_mixed_failures_are_atomic(self) -> None:
        self.assertIn("BindBufferMemory", self.conformance)
        self.assertIn("UpdateDescriptorSets", self.conformance)
        self.assertIn("All rejected requests remain atomic and change no binding, descriptor slots, or internal references", self.conformance)

    def test_queue_present_precedence_and_atomicity_matrix_is_complete(self) -> None:
        required = (
            "Device loss beats Surface loss and accepted-token reuse",
            "Surface loss and OUT_OF_DATE beat accepted-token reuse",
            "unsupported queue presentation capability is `BadMatch` before token reuse",
            "accepted-token reuse returns `BadValue` before image-state",
            "no request-attributable token reservation, wait reservation/consumption, or image transition",
            "A rejected request causes no partial state mutation attributable to that request",
        )
        for phrase in required:
            with self.subTest(contract=phrase):
                self.assertIn(phrase, self.conformance)

    def test_present_lifecycle_tests_cover_both_serialized_orders(self) -> None:
        required = (
            "If the lifecycle transition is serialized before acceptance",
            "if acceptance is serialized first",
            "first serialized terminal outcome",
            "exactly one terminal status",
            "independent lifecycle transitions that race with it are not rolled back",
        )
        for phrase in required:
            with self.subTest(contract=phrase):
                self.assertIn(phrase, self.conformance)

    def test_acquire_failures_do_not_signal_or_acquire(self) -> None:
        required = (
            "Every non-success result has zero `image_index`",
            "signals neither optional synchronization object",
            "must not acquire an image",
            "both synchronization objects unchanged and unsignaled",
        )
        for phrase in required:
            with self.subTest(contract=phrase):
                self.assertIn(phrase, self.conformance)

    def test_presentation_profile_is_explicitly_gated(self) -> None:
        self.assertIn("presentation-capable profile", self.presentation)
        self.assertIn("remain gated on the presentation-capable profile", self.presentation)
        self.assertIn("compute-only implementations", self.conformance)

    def test_rejected_wire_framing_has_no_side_effects(self) -> None:
        required = (
            "declared-length mismatch",
            "before payload allocation, XID lookup, or state mutation",
            "no partial resource creation, upload commit, command-buffer append/finalization",
        )
        for phrase in required:
            with self.subTest(contract=phrase):
                self.assertIn(phrase, self.conformance)


def first_common_request_error(
    *,
    envelope_valid=True,
    data=0,
    common_reserved=0,
    subopcode=1,
    presentation_supported=True,
    expected_request_bytes=16,
    actual_request_bytes=16,
    scalar_valid=True,
    xid_valid=True,
):
    """Small decision oracle for the shared precedence phases, not a server test."""
    if not envelope_valid:
        return "BadLength"
    if data != 0 or common_reserved != 0:
        return "BadValue"
    if 41 <= subopcode <= 47 and not presentation_supported:
        return "BadRequest"
    if actual_request_bytes != expected_request_bytes:
        return "BadLength"
    if not scalar_valid:
        return "BadValue"
    if not xid_valid:
        return "BadValue"
    return None


class CommonRequestErrorPrecedenceTests(unittest.TestCase):
    def test_envelope_bad_length_precedes_common_header_errors(self):
        self.assertEqual(
            first_common_request_error(
                envelope_valid=False, data=1, common_reserved=1,
                subopcode=41, presentation_supported=False,
            ),
            "BadLength",
        )

    def test_common_invariant_fields_precede_profile_gate_and_xid_lookup(self):
        self.assertEqual(
            first_common_request_error(
                data=1, subopcode=41, presentation_supported=False,
                xid_valid=False,
            ),
            "BadValue",
        )
        self.assertEqual(
            first_common_request_error(
                common_reserved=1, subopcode=41, presentation_supported=False,
                xid_valid=False,
            ),
            "BadValue",
        )

    def test_profile_gate_precedes_request_specific_payload_validation(self):
        self.assertEqual(
            first_common_request_error(
                subopcode=41, presentation_supported=False,
                expected_request_bytes=32, actual_request_bytes=8,
                scalar_valid=False, xid_valid=False,
            ),
            "BadRequest",
        )

    def test_supported_request_length_precedes_scalar_and_xid_errors(self):
        self.assertEqual(
            first_common_request_error(
                expected_request_bytes=32, actual_request_bytes=28,
                scalar_valid=False, xid_valid=False,
            ),
            "BadLength",
        )

    def test_request_scalar_errors_precede_xid_lookup(self):
        self.assertEqual(
            first_common_request_error(scalar_valid=False, xid_valid=False),
            "BadValue",
        )

    def test_checker_and_spec_define_same_common_phase_order(self):
        wire = read("spec/wire-protocol.md")
        checker = read("tools/check-wire-layout.py")
        errors = read("spec/errors.md")
        for phrase in (
            "## Common Request Validation Precedence",
            "Validate the X11 envelope independently of XAverius fields",
            "Validate the common-header fields that have invariant meanings",
            "These checks precede subopcode dispatch, profile gating, request-specific parsing",
            "The `flags` byte at offset 5 is request-specific",
            "An unsupported presentation request returns `BadRequest` before parsing",
            "validate its exact layout, request-specific lengths/counts and checked arithmetic",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, wire)
        self.assertIn("def check_common_request_error_precedence", checker)
        self.assertIn("check_common_request_error_precedence(c)", checker)
        self.assertIn("wire structure first, then field values, then XIDs in the field order", errors)




class RequestSpecificPrecedenceExceptionTests(unittest.TestCase):
    def test_create_default_device_has_total_validation_precedence(self):
        devices = read("spec/devices.md")
        errors = read("spec/errors.md")
        section = devices.split("## `CreateDefaultDevice`", 1)[1].split("\n## ", 1)[0]
        phrases = (
            "validate the exact/formula-based request length using checked arithmetic",
            "validate `queue_count`, the reserved field, and every priority",
            "validate the target `device_xid` as a create-XID",
            "require successful XGE 1.0-or-later negotiation",
            "select a suitable physical device and compute-capable queue family",
        )
        positions = [section.find(phrase) for phrase in phrases]
        self.assertTrue(all(p >= 0 for p in positions))
        self.assertEqual(positions, sorted(positions))
        self.assertIn("ungültige/belegte `device_xid` `BadIDChoice`", errors)
        self.assertIn("fehlende XGE-Aushandlung `BadMatch`", errors)
        self.assertIn("kein geeignetes Gerät `DEVICE_UNAVAILABLE`", errors)

    def test_signal_semaphore_keeps_xid_checks_before_value_reservation_checks(self):
        sync = read("spec/synchronization.md")
        section = sync.split("## `SignalSemaphore`", 1)[1].split("\n## ", 1)[0]
        phrases = (
            "exact total length of 24 bytes",
            "resolve the device XID, then the semaphore XID",
            "check resource type, client/device ownership",
            "check device state",
            "check timeline type and signal-value/reservation consistency",
        )
        positions = [section.find(phrase) for phrase in phrases]
        self.assertTrue(all(p >= 0 for p in positions), positions)
        self.assertEqual(positions, sorted(positions))

    def test_wait_semaphores_keeps_scalar_checks_before_xid_resolution(self):
        sync = read("spec/synchronization.md")
        section = sync.split("## `WaitSemaphores`", 1)[1].split("\n## ", 1)[0]
        phrases = (
            "length and checked arithmetic",
            "semaphore_count != 0",
            "resolve the device XID and then semaphore XIDs in array order",
            "check resource type, client/device ownership",
            "check device state",
            "verify that all semaphores are timeline semaphores",
        )
        positions = [section.find(phrase) for phrase in phrases]
        self.assertTrue(all(p >= 0 for p in positions), positions)
        self.assertEqual(positions, sorted(positions))

    def test_queue_submit_and_command_buffer_exceptions_are_explicit(self):
        queue = read("spec/queue-submission.md")
        command = read("spec/command-recording.md")
        self.assertIn("syntactic fields are checked", queue)
        self.assertIn("required XIDs are resolved in wire order", queue)
        self.assertIn("wire-structure errors take precedence over field errors", command)
        self.assertIn("target XID is checked before the pool XID", command)

    def test_presentation_statuses_follow_synchronous_validation(self):
        presentation = read("spec/presentation.md")
        section = presentation.split("## 5.3 Request validation, status precedence, and atomic acceptance", 1)[1].split("\n## ", 1)[0]
        phrases = (
            "wire length and checked arithmetic",
            "scalar/reserved-field validation",
            "XID resolution in the defined order",
            "type and ownership validation",
            "Device availability",
            "immutable request constraints",
            "lifecycle/capability status",
            "mutable state and synchronization eligibility",
        )
        positions = [section.find(phrase) for phrase in phrases]
        self.assertTrue(all(p >= 0 for p in positions), positions)
        self.assertEqual(positions, sorted(positions))

    def test_checker_audits_request_specific_precedence_exceptions(self):
        checker = read("tools/check-wire-layout.py")
        self.assertIn("def check_request_specific_precedence_exceptions", checker)
        self.assertIn("check_request_specific_precedence_exceptions(c)", checker)




if __name__ == "__main__":
    unittest.main(verbosity=2)
