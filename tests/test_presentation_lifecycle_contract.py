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

    def test_status_precedence_is_consistent_across_normative_chapters(self) -> None:
        errors = (ROOT / "spec" / "errors.md").read_text(encoding="utf-8")
        presentation_status = self.presentation.split(
            "The status precedence for requests with status replies is deterministic:", 1
        )[1].split("\nFor `CreateSurface`", 1)[0]
        errors_precedence = errors.split(
            "### Normative validation precedence for the seven presentation requests", 1
        )[1].split("\n## Synchron versus asynchron", 1)[0]

        # Device loss wins before queue/index checks; once the Device is usable,
        # immutable index errors precede Surface/extent status replies.
        queue = presentation_status.split("- `QueuePresent`:", 1)[1]
        self.assertLess(queue.index("`DEVICE_LOST`"), queue.index("out-of-range image index is `BadValue`"))
        self.assertLess(queue.index("out-of-range image index is `BadValue`"), queue.index("`SURFACE_LOST` takes precedence over `OUT_OF_DATE`"))
        self.assertLess(errors_precedence.index("check Device availability"), errors_precedence.index("Validate request-specific indices"))
        self.assertLess(errors_precedence.index("Validate request-specific indices"), errors_precedence.index("Resolve lifecycle/capability outcomes"))
        self.assertIn("Device loss takes precedence over Surface loss and all later mutable-state checks.", errors_precedence)

    def test_acquire_sync_eligibility_precedes_timeout_and_never_signals_on_failure(self) -> None:
        errors = (ROOT / "spec" / "errors.md").read_text(encoding="utf-8")
        acquire = errors.split("For a new `AcquireNextImage` evaluation", 1)[1].split("\nFor `QueuePresent`", 1)[0]
        self.assertLess(acquire.index("DEVICE_LOST"), acquire.index("SURFACE_LOST"))
        self.assertLess(acquire.index("SURFACE_LOST"), acquire.index("OUT_OF_DATE"))
        self.assertLess(acquire.index("validate every supplied semaphore/fence"), acquire.index("before polling or registering the wait"))
        self.assertIn("even if no image is available or the timeout is zero", acquire)
        self.assertIn("neither optional synchronization object", self.presentation)

    def test_present_rejection_and_async_terminalization_are_distinct(self) -> None:
        errors = (ROOT / "spec" / "errors.md").read_text(encoding="utf-8")
        queue = errors.split("For `QueuePresent`, status replies", 1)[1].split("\n## Synchron versus asynchron", 1)[0]
        self.assertIn("pre-acceptance outcomes", queue)
        self.assertIn("consumes no semaphore", queue)
        self.assertIn("reserves no token", queue)
        self.assertIn("token used only by a rejected attempt remains available", queue)
        self.assertIn("After acceptance, the request cannot produce a synchronous X11 error", self.presentation)
        self.assertIn("exactly one terminal status wins by serialization order", self.races)
        self.assertIn("internal terminal transition, image-state update, and release of backend references occur exactly once", self.presentation)


    def test_terminal_event_does_not_imply_image_release_or_reacquisition(self) -> None:
        event_contract = self.presentation.split(
            "## 6. Completion is three different things", 1
        )[1].split("\n## ", 1)[0]
        race_contract = self.races.split(
            "- Presentation event race vectors MUST exercise", 1
        )[1].split("\n- ", 1)[0]
        self.assertIn("Image release / reacquisition eligibility", event_contract)
        self.assertIn("Presentation completion", event_contract)
        self.assertIn("These milestones may occur at different times", event_contract)
        self.assertIn("An image is reacquirable only after internal release", race_contract)
        self.assertIn("both milestone orders", race_contract)

    def test_event_masks_are_sampled_independently_at_each_milestone(self) -> None:
        race_contract = self.races.split(
            "- Presentation event race vectors MUST exercise", 1
        )[1].split("\n- ", 1)[0]
        self.assertIn("image release before presentation completion", race_contract)
        self.assertIn("presentation completion before image release", race_contract)
        self.assertIn("samples the mask at its own milestone", race_contract)
        self.assertIn("no later mask change retroactively adds or removes", race_contract)
        self.assertIn("regardless of event masking or delivery suppression", race_contract)

    def test_invalidated_images_never_emit_release_event(self) -> None:
        event_contract = self.presentation.split(
            "## 6. Completion is three different things", 1
        )[1].split("\n## ", 1)[0]
        lifecycle_contract = self.presentation.split(
            "A window resize or zero extent marks the Swapchain", 1
        )[1].split("\n## ", 1)[0]
        race_contract = self.races.split(
            "**Accepted presentation versus resize/Surface loss/Device loss:**", 1
        )[1].split("\n-", 1)[0]
        self.assertIn("if not, it invalidates that image and the Swapchain instead", event_contract)
        self.assertIn("no `IMAGE_RELEASED` is emitted", lifecycle_contract)
        self.assertIn("otherwise the image is invalidated and no release event is emitted", race_contract)
        self.assertIn("terminal failure that invalidates the image MUST NOT emit `IMAGE_RELEASED`", self.races)

    def test_reacquisition_requires_internal_release_not_event_delivery(self) -> None:
        race_contract = self.races.split(
            "- Presentation event race vectors MUST exercise", 1
        )[1].split("\n- ", 1)[0]
        self.assertIn("Masking or suppressed delivery never skips internal cleanup", race_contract)
        self.assertIn("An image is reacquirable only after internal release", race_contract)
        self.assertIn("event is visible only under its delivery conditions", race_contract)
        self.assertIn("exactly one image-release-or-invalidation transition", race_contract)


if __name__ == "__main__":
    unittest.main()
