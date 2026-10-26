"""Host timeline signals and pending GPU signal reservation lifecycle tests."""
from __future__ import annotations

import copy
import unittest

from xa_state_model import (
    CommandBufferLifecycle,
    CommandBufferModel,
    SemaphoreKind,
    SubmissionModel,
    SubmitRequest,
    WaitState,
    finish_submission,
    queue_submit,
    signal_timeline_host,
)


class TimelineSignalLifecycleTests(unittest.TestCase):
    def state(self) -> SubmissionModel:
        return SubmissionModel(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE),
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE),
            ],
            wait_states=[WaitState.READY],
            signal_slots=[None],
            signal_counters=[2],
            semaphore_kinds=[SemaphoreKind.TIMELINE],
        )

    def submit_signal(self, state: SubmissionModel, token: int, value: int,
                      command_buffer: int = 0) -> None:
        self.assertEqual(
            queue_submit(
                state,
                SubmitRequest(
                    token=token,
                    command_buffer_indices=(command_buffer,),
                    signal_indices=(0,),
                    signal_values=(value,),
                ),
            ),
            "SUCCESS",
        )

    def test_host_signal_can_advance_below_pending_gpu_signal(self) -> None:
        state = self.state()
        self.submit_signal(state, token=10, value=12)
        self.assertEqual(signal_timeline_host(state, 0, 9), "SUCCESS")
        self.assertEqual(state.signal_counters, [9])
        self.assertEqual(state.signal_slots, [12])
        self.assertEqual(state.pending_timeline_signals, [(10, 0, 12)])

    def test_host_signal_cannot_equal_or_jump_over_pending_gpu_signal(self) -> None:
        for host_value in (12, 13):
            with self.subTest(host_value=host_value):
                state = self.state()
                self.submit_signal(state, token=11, value=12)
                before = copy.deepcopy(state)
                self.assertEqual(
                    signal_timeline_host(state, 0, host_value),
                    "INVALID_SYNCHRONIZATION_STATE",
                )
                self.assertEqual(state, before)

    def test_successful_gpu_signal_advances_counter_and_releases_reservation(self) -> None:
        state = self.state()
        self.submit_signal(state, token=20, value=12)
        self.assertEqual(finish_submission(state, 20, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [12])
        self.assertEqual(state.signal_slots, [None])
        self.assertEqual(state.pending_timeline_signals, [])
        self.assertEqual(state.pending_submissions, [])
        self.assertEqual(signal_timeline_host(state, 0, 13), "SUCCESS")

    def test_failed_submission_releases_reservation_without_advancing_counter(self) -> None:
        state = self.state()
        self.submit_signal(state, token=30, value=12)
        self.assertEqual(finish_submission(state, 30, success=False), "SUCCESS")
        self.assertEqual(state.signal_counters, [2])
        self.assertEqual(state.signal_slots, [None])
        self.assertEqual(state.pending_timeline_signals, [])
        self.assertEqual(state.pending_submissions, [])
        # Once failure is terminal, the abandoned GPU reservation no longer
        # blocks a host signal; the unachieved GPU value remains unobserved.
        self.assertEqual(signal_timeline_host(state, 0, 7), "SUCCESS")
        self.assertEqual(state.signal_counters, [7])

    def test_duplicate_terminal_callback_cannot_release_or_advance_again(self) -> None:
        state = self.state()
        self.submit_signal(state, token=40, value=12)
        self.assertEqual(finish_submission(state, 40, success=True), "SUCCESS")
        after_terminal = copy.deepcopy(state)
        self.assertEqual(finish_submission(state, 40, success=False), "BadValue")
        self.assertEqual(state, after_terminal)


if __name__ == "__main__":
    unittest.main(verbosity=2)
