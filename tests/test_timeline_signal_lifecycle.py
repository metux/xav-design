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


    def test_same_semaphore_reverse_completion_keeps_counter_monotonic(self) -> None:
        state = self.state()
        self.submit_signal(state, token=80, value=12, command_buffer=0)
        self.submit_signal(state, token=81, value=18, command_buffer=1)

        # Both values remain reserved until their own operations are terminal.
        self.assertEqual(
            state.pending_timeline_signals, [(80, 0, 12), (81, 0, 18)]
        )
        # The higher-valued callback arrives first. The visible counter may
        # advance to 18, but the lower reservation must remain tracked.
        self.assertEqual(finish_submission(state, 81, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [18])
        self.assertEqual(state.pending_timeline_signals, [(80, 0, 12)])
        self.assertEqual(state.pending_submissions, [80])
        # Host signaling may not bypass the still-pending lower reservation,
        # even though the higher value has already become observable.
        before = copy.deepcopy(state)
        self.assertEqual(
            signal_timeline_host(state, 0, 19),
            "INVALID_SYNCHRONIZATION_STATE",
        )
        self.assertEqual(state, before)

        # Late completion of the lower signal must never move the counter back.
        self.assertEqual(finish_submission(state, 80, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [18])
        self.assertEqual(state.pending_timeline_signals, [])
        self.assertEqual(state.pending_submissions, [])
        self.assertEqual(state.signal_slots, [None])
        self.assertEqual(signal_timeline_host(state, 0, 19), "SUCCESS")
        self.assertEqual(state.signal_counters, [19])

    def test_reverse_completion_with_lower_signal_failure_preserves_higher_value(self) -> None:
        state = self.state()
        self.submit_signal(state, token=90, value=12, command_buffer=0)
        self.submit_signal(state, token=91, value=18, command_buffer=1)
        self.assertEqual(finish_submission(state, 91, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [18])
        self.assertEqual(finish_submission(state, 90, success=False), "SUCCESS")
        self.assertEqual(state.signal_counters, [18])
        self.assertEqual(state.pending_timeline_signals, [])
        self.assertEqual(state.pending_submissions, [])
        self.assertEqual(state.signal_slots, [None])
        self.assertEqual(
            [cb.lifecycle for cb in state.command_buffers],
            [CommandBufferLifecycle.INVALID, CommandBufferLifecycle.EXECUTABLE],
        )

    def test_device_loss_wins_over_late_backend_success_callback(self) -> None:
        state = self.state()
        self.submit_signal(state, token=50, value=12)
        state.device_lost = True
        before_counter = list(state.signal_counters)
        self.assertEqual(finish_submission(state, 50, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, before_counter)
        self.assertEqual(state.signal_slots, [None])
        self.assertEqual(state.pending_timeline_signals, [])
        self.assertEqual(state.pending_submissions, [])
        self.assertEqual(
            state.command_buffers[0].lifecycle, CommandBufferLifecycle.INVALID
        )
        before_host_signal = copy.deepcopy(state)
        self.assertEqual(signal_timeline_host(state, 0, 13), "DEVICE_LOST")
        self.assertEqual(state, before_host_signal)

    def test_concurrent_submission_callbacks_only_finalize_their_own_state(self) -> None:
        state = self.state()
        self.submit_signal(state, token=60, value=12, command_buffer=0)
        # A second timeline signal on the same semaphore cannot be reserved
        # until the first one is terminal; use a second semaphore to model two
        # independently completing submissions.
        state.signal_slots.append(None)
        state.signal_counters.append(4)
        state.semaphore_kinds.append(SemaphoreKind.TIMELINE)
        state.signal_counters[1] = 4
        self.assertEqual(
            queue_submit(
                state,
                SubmitRequest(
                    token=61,
                    command_buffer_indices=(1,),
                    signal_indices=(1,),
                    signal_values=(8,),
                ),
            ),
            "SUCCESS",
        )
        self.assertEqual(finish_submission(state, 60, success=False), "SUCCESS")
        self.assertEqual(state.signal_counters, [2, 4])
        self.assertEqual(state.signal_slots, [None, 8])
        self.assertEqual(state.pending_timeline_signals, [(61, 1, 8)])
        self.assertEqual(state.pending_submissions, [61])
        self.assertEqual(
            [cb.lifecycle for cb in state.command_buffers],
            [CommandBufferLifecycle.INVALID, CommandBufferLifecycle.PENDING],
        )
        self.assertEqual(finish_submission(state, 61, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [2, 8])
        self.assertEqual(
            [cb.lifecycle for cb in state.command_buffers],
            [CommandBufferLifecycle.INVALID, CommandBufferLifecycle.EXECUTABLE],
        )

    def test_device_loss_callback_race_does_not_double_finalize(self) -> None:
        state = self.state()
        self.submit_signal(state, token=70, value=12)
        state.device_lost = True
        self.assertEqual(finish_submission(state, 70, success=False), "SUCCESS")
        after_terminal = copy.deepcopy(state)
        self.assertEqual(finish_submission(state, 70, success=True), "BadValue")
        self.assertEqual(state, after_terminal)

    def test_duplicate_terminal_callback_cannot_release_or_advance_again(self) -> None:
        state = self.state()
        self.submit_signal(state, token=40, value=12)
        self.assertEqual(finish_submission(state, 40, success=True), "SUCCESS")
        after_terminal = copy.deepcopy(state)
        self.assertEqual(finish_submission(state, 40, success=False), "BadValue")
        self.assertEqual(state, after_terminal)


if __name__ == "__main__":
    unittest.main(verbosity=2)
