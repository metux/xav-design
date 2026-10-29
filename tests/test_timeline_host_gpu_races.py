"""Regression tests for host/GPU races on timeline semaphore counters."""
from __future__ import annotations

import copy
import unittest

from xa_state_model import (
    CommandBufferLifecycle,
    CommandBufferModel,
    SemaphoreKind,
    SubmissionModel,
    SubmitRequest,
    finish_submission,
    queue_submit,
    signal_timeline_host,
)


class TimelineHostGpuRaceTests(unittest.TestCase):
    def state(self) -> SubmissionModel:
        return SubmissionModel(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE),
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE),
            ],
            wait_states=[],
            signal_slots=[None],
            signal_counters=[2],
            semaphore_kinds=[SemaphoreKind.TIMELINE],
        )

    def reserve_gpu_signal(self, state: SubmissionModel, token: int, value: int) -> None:
        self.assertEqual(
            queue_submit(
                state,
                SubmitRequest(
                    token=token,
                    command_buffer_indices=(0 if token == 101 else 1,),
                    signal_indices=(0,),
                    signal_values=(value,),
                ),
            ),
            "SUCCESS",
        )

    def test_host_signal_below_pending_gpu_value_then_gpu_callback(self) -> None:
        state = self.state()
        self.reserve_gpu_signal(state, 101, 9)

        # Host signaling may advance the counter only up to (not through) a
        # pending GPU reservation. The reservation remains authoritative.
        self.assertEqual(signal_timeline_host(state, 0, 6), "SUCCESS")
        self.assertEqual(state.signal_counters, [6])
        self.assertEqual(state.signal_slots, [9])
        self.assertEqual(state.pending_timeline_signals, [(101, 0, 9)])

        self.assertEqual(finish_submission(state, 101, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [9])
        self.assertEqual(state.signal_slots, [None])
        self.assertEqual(state.pending_timeline_signals, [])

    def test_host_signal_cannot_jump_over_gpu_reservation_atomically(self) -> None:
        state = self.state()
        self.reserve_gpu_signal(state, 101, 9)
        before = copy.deepcopy(state)

        # Equaling or jumping past a pending signal would make its later
        # completion stale, so the host operation must not mutate anything.
        for value in (9, 10):
            with self.subTest(value=value):
                self.assertEqual(
                    signal_timeline_host(state, 0, value),
                    "INVALID_SYNCHRONIZATION_STATE",
                )
                self.assertEqual(state, before)

        self.assertEqual(finish_submission(state, 101, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [9])

    def test_gpu_callback_first_makes_host_signal_validate_against_new_counter(self) -> None:
        state = self.state()
        self.reserve_gpu_signal(state, 101, 9)
        self.assertEqual(finish_submission(state, 101, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [9])

        before = copy.deepcopy(state)
        self.assertEqual(
            signal_timeline_host(state, 0, 9),
            "BadValue",
        )
        self.assertEqual(state, before)
        self.assertEqual(signal_timeline_host(state, 0, 12), "SUCCESS")
        self.assertEqual(state.signal_counters, [12])

    def test_host_signal_equal_to_counter_is_bad_value_without_reservations(self) -> None:
        state = self.state()
        before = copy.deepcopy(state)
        self.assertEqual(signal_timeline_host(state, 0, 2), "BadValue")
        self.assertEqual(state, before)

    def test_late_gpu_callback_cannot_decrease_counter_after_host_progress(self) -> None:
        state = self.state()
        self.reserve_gpu_signal(state, 101, 9)
        self.assertEqual(signal_timeline_host(state, 0, 6), "SUCCESS")
        # A different still-pending, higher reservation prevents host signal
        # from advancing across either reservation.
        self.reserve_gpu_signal(state, 102, 12)
        self.assertEqual(finish_submission(state, 102, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [12])

        # The lower callback arrives last; max(current, value) preserves the
        # monotonic counter while removing only its own reservation.
        self.assertEqual(finish_submission(state, 101, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [12])
        self.assertEqual(state.signal_slots, [None])
        self.assertEqual(state.pending_timeline_signals, [])

    def test_failed_gpu_callback_releases_only_its_reservation_after_host_signal(self) -> None:
        state = self.state()
        self.reserve_gpu_signal(state, 101, 9)
        self.reserve_gpu_signal(state, 102, 12)
        self.assertEqual(signal_timeline_host(state, 0, 6), "SUCCESS")

        self.assertEqual(finish_submission(state, 102, success=False), "SUCCESS")
        self.assertEqual(state.signal_counters, [6])
        self.assertEqual(state.signal_slots, [9])
        self.assertEqual(state.pending_timeline_signals, [(101, 0, 9)])

        self.assertEqual(finish_submission(state, 101, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [9])
        self.assertEqual(state.signal_slots, [None])


if __name__ == "__main__":
    unittest.main()
