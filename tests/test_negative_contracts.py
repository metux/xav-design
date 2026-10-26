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
            "jeder Fehler lässt die Create-XID unangelegt",
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
        self.assertIn("Alle abgewiesenen Requests bleiben atomar", self.conformance)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
