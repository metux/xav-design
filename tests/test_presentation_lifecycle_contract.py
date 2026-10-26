#!/usr/bin/env python3
"""Cross-check presentation lifecycle race requirements against normative contracts.

These are specification-contract tests, not tests of a running XAverius server.
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFORMANCE = ROOT / "spec" / "conformance.md"
PRESENTATION = ROOT / "spec" / "presentation.md"
LIFETIME = ROOT / "spec" / "resource-lifetime.md"


class PresentationLifecycleContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.conformance = CONFORMANCE.read_text(encoding="utf-8")
        cls.presentation = PRESENTATION.read_text(encoding="utf-8")
        cls.lifetime = LIFETIME.read_text(encoding="utf-8")
        start = cls.conformance.index("## Presentation lifecycle race and atomicity vectors")
        end = cls.conformance.find("\n## ", start + 4)
        cls.races = cls.conformance[start:end if end >= 0 else None]

    def test_all_required_serialized_race_pairs_are_present(self) -> None:
        labels = (
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
        for label in labels:
            with self.subTest(race=label):
                self.assertIn(label, self.races)

    def test_races_have_a_deterministic_oracle_and_both_wire_orders(self) -> None:
        self.assertIn("A test controls the serialization order explicitly; wall-clock timing alone is not a valid oracle.", self.races)
        self.assertIn("Every vector must assert both externally observable result", self.races)
        self.assertIn("public XID visibility, image state, token reservation, semaphore state, pending-reference count", self.races)
        self.assertIn("Include at least one case per vector with presentation event masks disabled", self.races)
        self.assertIn("Run the vectors in both request byte orders wherever wire parsing is involved.", self.races)

    def test_acquire_terminalization_is_first_wins_and_cleanup_is_exactly_once(self) -> None:
        self.assertIn("first terminal result serialized by the server wins", self.presentation)
        self.assertIn("terminalizes each still-open acquire with reply status `DEVICE_DESTROYED`", self.presentation)
        self.assertIn("Registration-only references are released exactly once", self.races)
        self.assertIn("signals neither object", self.presentation)
        self.assertIn("before polling for an image or registering a wait", self.presentation)
        self.assertIn("INVALID_SYNCHRONIZATION_STATE` before `NOT_READY`/`TIMEOUT`", self.races)

    def test_surface_and_swapchain_lifetimes_are_atomic(self) -> None:
        self.assertIn("A Surface must not be destroyed while a live Swapchain references it.", self.presentation)
        self.assertIn("The destroy request is rejected atomically; the Surface remains live.", self.presentation)
        self.assertIn("A Swapchain must not be destroyed while any recording command buffer", self.presentation)
        self.assertIn("An image being ACQUIRED by itself does not prevent destruction", self.presentation)
        self.assertIn("commit-time revalidation", self.races)
        self.assertIn("publishes no target XID or backing resource", self.races)

    def test_rejected_present_does_not_reserve_or_consume_state(self) -> None:
        rejected = self.races.split("**QueuePresent rejection versus accepted state:**", 1)[1].split("\n-", 1)[0]
        self.assertIn("leaves the image ACQUIRED", rejected)
        self.assertIn("reserves neither presentation_token nor wait slots", rejected)
        self.assertIn("consumes no semaphore payload", rejected)
        self.assertIn("Acceptance atomically reserves the token and all wait slots", self.conformance)

    def test_uncertain_semaphore_consumption_is_never_guessed(self) -> None:
        self.assertIn("It must never silently reset a semaphore to `UNSIGNALED`", self.presentation)
        self.assertIn("marks that binary semaphore `UNTRUSTED`", self.presentation)
        self.assertIn("Semaphore uncertainty after accepted presentation failure", self.races)

    def test_image_release_requires_quiescent_reusable_image(self) -> None:
        accepted = self.races.split("**Accepted presentation versus resize/Surface loss/Device loss:**", 1)[1].split("\n-", 1)[0]
        self.assertIn("exactly one terminal status wins", accepted)
        self.assertIn("IMAGE_RELEASED is permitted only when backend access has ended", accepted)
        self.assertIn("image remains reusable in a usable Swapchain", accepted)
        self.assertIn("otherwise the image is invalidated and no release event is emitted", accepted)
        self.assertIn("PRESENTATION_FAILED permits IMAGE_RELEASED only after backend quiescence", self.lifetime)


if __name__ == "__main__":
    unittest.main()
