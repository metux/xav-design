"""QueueSubmit callbacks must remain bound to the Device generation they captured."""
from __future__ import annotations

import unittest

from xa_state_model import (
    BinarySignalState, CommandBufferLifecycle, CommandBufferModel,
    SemaphoreKind, SharedBinarySemaphore, SubmissionModel, SubmitRequest,
    WaitState, destroy_submission_device, finish_submission, queue_submit,
)


def make_device(generation: int):
    wait_sem = SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED)
    signal_sem = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)
    state = SubmissionModel(
        device_generation=generation,
        command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
        wait_states=[WaitState.READY, WaitState.READY],
        binary_signal_states=[
            BinarySignalState.SIGNALED, BinarySignalState.UNSIGNALED,
        ],
        signal_slots=[None, None],
        semaphore_kinds=[SemaphoreKind.BINARY, SemaphoreKind.BINARY],
        shared_semaphores=[wait_sem, signal_sem],
    )
    return state, wait_sem, signal_sem


class QueueSubmitDeviceGenerationTests(unittest.TestCase):
    def test_late_callback_cannot_release_replacement_device_reservations(self):
        old, old_wait, old_signal = make_device(31)
        request = SubmitRequest(
            token=501, command_buffer_indices=(0,),
            wait_indices=(0,), signal_indices=(1,), signal_values=(0,),
        )
        self.assertEqual(queue_submit(old, request), "SUCCESS")
        self.assertEqual(old_wait.wait_reservation, ("submit", 501))
        self.assertEqual(old_signal.signal_reservation, ("submit", 501))
        self.assertEqual(old_signal.signal_state, BinarySignalState.SIGNAL_PENDING)

        self.assertEqual(destroy_submission_device(old), "SUCCESS")
        self.assertFalse(old.device_live)
        # Accepted work and its old semaphore references remain until callback.
        self.assertEqual(old.pending_submissions, [501])

        new, new_wait, new_signal = make_device(32)
        self.assertEqual(queue_submit(new, request), "SUCCESS")
        self.assertEqual(new_wait.wait_reservation, ("submit", 501))
        self.assertEqual(new_signal.signal_reservation, ("submit", 501))

        snapshot = (
            list(new.pending_submissions), list(new.pending_binary_waits),
            list(new.pending_binary_signals), list(new.pending_command_buffers),
            list(new.binary_signal_states), list(new.wait_states),
            new_wait.wait_reservation, new_wait.signal_state,
            new_signal.signal_reservation, new_signal.signal_state,
            new.command_buffers[0].lifecycle,
        )
        self.assertEqual(
            finish_submission(new, 501, True, device_generation=31), "BadValue",
        )
        self.assertEqual(
            (
                list(new.pending_submissions), list(new.pending_binary_waits),
                list(new.pending_binary_signals), list(new.pending_command_buffers),
                list(new.binary_signal_states), list(new.wait_states),
                new_wait.wait_reservation, new_wait.signal_state,
                new_signal.signal_reservation, new_signal.signal_state,
                new.command_buffers[0].lifecycle,
            ),
            snapshot,
        )

        # The genuine callback still retires the old operation, not the new one.
        self.assertEqual(
            finish_submission(old, 501, True, device_generation=31), "SUCCESS",
        )
        self.assertEqual(old.pending_submissions, [])
        self.assertIsNone(old_wait.wait_reservation)
        self.assertIsNone(old_signal.signal_reservation)
        self.assertEqual(new_wait.wait_reservation, ("submit", 501))
        self.assertEqual(new_signal.signal_reservation, ("submit", 501))
        self.assertEqual(new_signal.signal_state, BinarySignalState.SIGNAL_PENDING)

    def test_old_device_loss_callback_cannot_poison_replacement_semaphores(self):
        old, old_wait, old_signal = make_device(41)
        request = SubmitRequest(
            token=601, command_buffer_indices=(0,),
            wait_indices=(0,), signal_indices=(1,), signal_values=(0,),
        )
        self.assertEqual(queue_submit(old, request), "SUCCESS")
        self.assertEqual(destroy_submission_device(old), "SUCCESS")

        new, new_wait, new_signal = make_device(42)
        self.assertEqual(queue_submit(new, request), "SUCCESS")
        self.assertEqual(
            finish_submission(new, 601, False, device_generation=41), "BadValue",
        )
        self.assertFalse(new.device_lost)
        self.assertFalse(new_wait.device_lost)
        self.assertFalse(new_signal.device_lost)
        self.assertEqual(new_wait.wait_reservation, ("submit", 601))
        self.assertEqual(new_signal.signal_reservation, ("submit", 601))

        # Loss belongs to the captured old Device/semaphore graph only.
        from xa_state_model import mark_device_lost
        self.assertEqual(mark_device_lost(old), "SUCCESS")
        self.assertTrue(old.device_lost)
        self.assertTrue(old_wait.device_lost)
        self.assertTrue(old_signal.device_lost)
        self.assertFalse(new.device_lost)
        self.assertFalse(new_wait.device_lost)
        self.assertFalse(new_signal.device_lost)


if __name__ == "__main__":
    unittest.main()
