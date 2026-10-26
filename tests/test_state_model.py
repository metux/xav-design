"""Executable precedence and atomicity tests for the XAverius state model."""
from __future__ import annotations

import copy
import unittest

from xa_state_model import (
    ImageState,
    PresentRequest,
    PresentState,
    WaitState,
    queue_present,
)


class QueuePresentStateModelTests(unittest.TestCase):
    def state(self, **changes) -> PresentState:
        state = PresentState(
            valid_wait_xids=(True, True),
            wait_states=[WaitState.READY, WaitState.READY],
        )
        for name, value in changes.items():
            setattr(state, name, value)
        return state

    def assert_rejected_atomically(
        self, state: PresentState, request: PresentRequest, expected: str
    ) -> None:
        before = copy.deepcopy(state)
        result = queue_present(state, request)
        self.assertEqual((result.result, result.accepted), (expected, False))
        self.assertEqual(state, before, "rejected request mutated model state")

    def test_wire_length_beats_every_other_failure(self) -> None:
        state = self.state(
            device_lost=True,
            valid_device_xid=False,
            surface_lost=True,
        )
        self.assert_rejected_atomically(
            state, PresentRequest(wire_length_valid=False), "BadLength"
        )

    def test_scalar_syntax_beats_xids_and_device_loss(self) -> None:
        state = self.state(device_lost=True, valid_device_xid=False)
        self.assert_rejected_atomically(
            state, PresentRequest(token=0), "BadValue"
        )

    def test_unknown_xid_beats_device_loss(self) -> None:
        state = self.state(device_lost=True, valid_swapchain_xid=False)
        self.assert_rejected_atomically(state, PresentRequest(), "BadValue")

    def test_type_ownership_beats_device_loss(self) -> None:
        state = self.state(device_lost=True, correct_types_and_ownership=False)
        self.assert_rejected_atomically(state, PresentRequest(), "BadMatch")

    def test_device_loss_beats_queue_and_lifecycle(self) -> None:
        state = self.state(
            device_lost=True,
            valid_queue=False,
            surface_lost=True,
            out_of_date=True,
        )
        self.assert_rejected_atomically(state, PresentRequest(), "DEVICE_LOST")

    def test_queue_index_error_beats_surface_lifecycle(self) -> None:
        state = self.state(valid_image_index=False, surface_lost=True)
        self.assert_rejected_atomically(state, PresentRequest(), "BadValue")

    def test_surface_loss_beats_out_of_date_and_token_reuse(self) -> None:
        state = self.state(
            surface_lost=True,
            out_of_date=True,
            accepted_tokens={1},
        )
        self.assert_rejected_atomically(state, PresentRequest(token=1), "SURFACE_LOST")

    def test_out_of_date_beats_token_reuse(self) -> None:
        state = self.state(out_of_date=True, accepted_tokens={1})
        self.assert_rejected_atomically(state, PresentRequest(token=1), "OUT_OF_DATE")

    def test_no_present_support_beats_token_reuse(self) -> None:
        state = self.state(present_supported=False, accepted_tokens={1})
        self.assert_rejected_atomically(state, PresentRequest(token=1), "BadMatch")

    def test_token_reuse_beats_image_and_wait_state(self) -> None:
        state = self.state(
            accepted_tokens={1},
            image_state=ImageState.AVAILABLE,
            wait_states=[WaitState.INCOMPATIBLE, WaitState.READY],
        )
        self.assert_rejected_atomically(
            state, PresentRequest(token=1, wait_indices=(0,)), "BadValue"
        )

    def test_image_state_beats_wait_eligibility(self) -> None:
        state = self.state(
            image_state=ImageState.AVAILABLE,
            wait_states=[WaitState.INCOMPATIBLE, WaitState.READY],
        )
        self.assert_rejected_atomically(
            state, PresentRequest(wait_indices=(0,)), "INVALID_SYNCHRONIZATION_STATE"
        )

    def test_untrusted_wait_fails_without_reserving_anything(self) -> None:
        state = self.state(wait_states=[WaitState.READY, WaitState.UNTRUSTED])
        self.assert_rejected_atomically(
            state, PresentRequest(wait_indices=(0, 1)), "DEPENDENCY_FAILED"
        )

    def test_rejected_token_can_be_retried_and_is_not_reserved(self) -> None:
        state = self.state(image_state=ImageState.AVAILABLE)
        first = queue_present(state, PresentRequest(token=7))
        self.assertEqual(first.result, "INVALID_SYNCHRONIZATION_STATE")
        self.assertNotIn(7, state.accepted_tokens)
        state.image_state = ImageState.ACQUIRED
        second = queue_present(state, PresentRequest(token=7))
        self.assertEqual(second.result, "SUCCESS")
        self.assertIn(7, state.accepted_tokens)

    def test_success_commits_token_waits_and_image_together(self) -> None:
        state = self.state()
        before = copy.deepcopy(state)
        result = queue_present(state, PresentRequest(token=9, wait_indices=(0, 1)))
        self.assertEqual((result.result, result.accepted), ("SUCCESS", True))
        self.assertEqual(state.image_state, ImageState.PRESENT_PENDING)
        self.assertIn(9, state.accepted_tokens)
        self.assertEqual(state.wait_states, [WaitState.RESERVED, WaitState.RESERVED])
        self.assertEqual(len(state.accepted_tokens - before.accepted_tokens), 1)

    def test_independent_lifecycle_change_is_not_rolled_back(self) -> None:
        # The lifecycle change is already serialized before request validation.
        state = self.state(surface_lost=True, image_state=ImageState.INVALID)
        before = copy.deepcopy(state)
        self.assert_rejected_atomically(
            state, PresentRequest(), "SURFACE_LOST"
        )
        self.assertEqual(state, before)
        self.assertEqual(state.image_state, ImageState.INVALID)


if __name__ == "__main__":
    unittest.main(verbosity=2)
