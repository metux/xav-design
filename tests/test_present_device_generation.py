"""QueuePresent callbacks must not cross a destroyed/recreated Device identity."""
from __future__ import annotations

import unittest

from xa_state_model import (
    BinarySignalState, ImageState, PresentRequest, PresentState,
    SharedBinarySemaphore, WaitState, queue_present,
    finish_present_terminal, finish_present_image_release,
    finish_present_wait, destroy_present_device,
    destroy_present_swapchain, recreate_present_swapchain,
)


class QueuePresentDeviceGenerationTests(unittest.TestCase):
    def test_old_callbacks_cannot_mutate_replacement_device_or_semaphores(self):
        old_sem = SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED)
        old = PresentState(
            valid_wait_xids=(True,), wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNALED],
            shared_semaphores=[old_sem], device_generation=11,
        )
        self.assertEqual(
            queue_present(old, PresentRequest(token=77, wait_indices=(0,))).result,
            "SUCCESS",
        )
        self.assertEqual(old_sem.wait_reservation, ("present", 77))
        self.assertEqual(destroy_present_device(old), "SUCCESS")

        # Same public Device/Swapchain/Semaphore XIDs, but new internal objects
        # and a new Device generation. The presentation token is reused too.
        new_sem = SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED)
        new = PresentState(
            valid_wait_xids=(True,), wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNALED],
            shared_semaphores=[new_sem], device_generation=12,
            swapchain_generation=2,
        )
        self.assertEqual(
            queue_present(new, PresentRequest(token=77, wait_indices=(0,))).result,
            "SUCCESS",
        )
        self.assertEqual(new_sem.wait_reservation, ("present", 77))

        # Even a matching Swapchain generation and reused token cannot make
        # an old Device callback valid against the replacement Device.
        snapshot = (
            new.image_state, set(new.pending_present_tokens),
            dict(new.terminal_present_status), set(new.image_release_tokens),
            list(new.pending_present_waits), new_sem.wait_reservation,
            new_sem.signal_state, new_sem.device_lost,
        )
        self.assertEqual(
            finish_present_wait(
                new, 77, 0, consumed=True, generation=2, device_generation=11,
            ), "BadValue",
        )
        self.assertEqual(
            finish_present_terminal(
                new, 77, "DEVICE_LOST", generation=2, device_generation=11,
            ), "BadValue",
        )
        self.assertEqual(
            finish_present_image_release(
                new, 77, generation=2, device_generation=11,
            ), "BadValue",
        )
        self.assertEqual(
            (
                new.image_state, set(new.pending_present_tokens),
                dict(new.terminal_present_status), set(new.image_release_tokens),
                list(new.pending_present_waits), new_sem.wait_reservation,
                new_sem.signal_state, new_sem.device_lost,
            ),
            snapshot,
        )

        # The genuine old callback still retires only the old reservation.
        self.assertEqual(
            finish_present_wait(
                old, 77, 0, consumed=True, generation=1, device_generation=11,
            ), "SUCCESS",
        )
        self.assertIsNone(old_sem.wait_reservation)
        self.assertEqual(new_sem.wait_reservation, ("present", 77))
        self.assertFalse(new.device_lost)

    def test_accepted_presentation_token_cannot_be_reused_after_swapchain_recreation(self):
        state = PresentState(valid_wait_xids=(), wait_states=(), device_generation=31)
        self.assertEqual(queue_present(state, PresentRequest(token=901)).result, "SUCCESS")
        self.assertEqual(finish_present_terminal(state, 901, "SUCCESS", generation=1, device_generation=31), "SUCCESS")
        self.assertEqual(finish_present_image_release(state, 901, generation=1, device_generation=31), "SUCCESS")
        self.assertEqual(destroy_present_swapchain(state), "SUCCESS")
        self.assertEqual(recreate_present_swapchain(state), "SUCCESS")
        snapshot = (state.image_state, set(state.accepted_tokens), set(state.pending_present_tokens))
        self.assertEqual(queue_present(state, PresentRequest(token=901)).result, "BadValue")
        self.assertEqual((state.image_state, state.accepted_tokens, state.pending_present_tokens), snapshot)
        self.assertEqual(queue_present(state, PresentRequest(token=902)).result, "SUCCESS")

    def test_late_old_device_loss_does_not_propagate_to_new_device(self):
        old_sem = SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED)
        old = PresentState(
            valid_wait_xids=(True,), wait_states=[WaitState.READY],
            shared_semaphores=[old_sem], device_generation=21,
        )
        self.assertEqual(queue_present(old, PresentRequest(token=88)).result, "SUCCESS")
        self.assertEqual(destroy_present_device(old), "SUCCESS")

        new_sem = SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED)
        new = PresentState(
            valid_wait_xids=(True,), wait_states=[WaitState.READY],
            shared_semaphores=[new_sem], device_generation=22,
            swapchain_generation=2,
        )
        self.assertEqual(queue_present(new, PresentRequest(token=88)).result, "SUCCESS")

        self.assertEqual(
            finish_present_terminal(
                old, 88, "DEVICE_LOST", generation=1, device_generation=21,
            ), "SUCCESS",
        )
        self.assertTrue(old.device_lost)
        self.assertTrue(old_sem.device_lost)
        self.assertFalse(new.device_lost)
        self.assertFalse(new_sem.device_lost)
        self.assertEqual(new.image_state, ImageState.PRESENT_PENDING)
        self.assertEqual(new.pending_present_tokens, {88})


if __name__ == "__main__":
    unittest.main()
