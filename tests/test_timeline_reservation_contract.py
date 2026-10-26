"""Regression tests for timeline waits and competing QueueSubmit reservations."""
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
    queue_submit,
)


class TimelineReservationRegressionTests(unittest.TestCase):
    def state(self, **changes) -> SubmissionModel:
        state = SubmissionModel(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE),
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE),
            ],
            wait_states=[WaitState.READY, WaitState.READY],
            signal_slots=[None, None],
            signal_counters=[2, 0],
            semaphore_kinds=[SemaphoreKind.TIMELINE, SemaphoreKind.TIMELINE],
        )
        for name, value in changes.items():
            setattr(state, name, value)
        return state

    def test_future_wait_survives_rejected_competing_signal_reservation(self) -> None:
        state = self.state()
        self.assertEqual(
            queue_submit(
                state,
                SubmitRequest(token=21, command_buffer_indices=(0,),
                              wait_indices=(0,), wait_values=(9,)),
            ),
            "SUCCESS",
        )
        before = copy.deepcopy(state)
        # A timeline signal must exceed the current counter and all outstanding
        # pending signal reservations. This request's value is invalid because
        # it does not exceed the visible counter.
        result = queue_submit(
            state,
            SubmitRequest(token=22, command_buffer_indices=(1,),
                          signal_indices=(0,), signal_values=(2,)),
        )
        self.assertEqual(result, "BadValue")
        self.assertEqual(state, before)
        self.assertEqual(state.pending_timeline_waits, [(21, 0, 9)])

    def test_higher_timeline_signal_reservation_does_not_erase_future_wait(self) -> None:
        state = self.state()
        self.assertEqual(
            queue_submit(
                state,
                SubmitRequest(token=31, command_buffer_indices=(0,),
                              wait_indices=(0,), wait_values=(9,)),
            ),
            "SUCCESS",
        )
        self.assertEqual(
            queue_submit(
                state,
                SubmitRequest(token=32, command_buffer_indices=(1,),
                              signal_indices=(0,), signal_values=(12,)),
            ),
            "SUCCESS",
        )
        self.assertEqual(state.pending_timeline_waits, [(31, 0, 9)])
        self.assertEqual(state.signal_slots[0], 12)
        self.assertEqual(state.accepted_tokens, {31, 32})

    def test_late_invalid_signal_preserves_existing_wait_and_signal_reservations(self) -> None:
        state = self.state(
            pending_timeline_waits=[(41, 0, 10)],
            signal_slots=[None, 15],
        )
        before = copy.deepcopy(state)
        result = queue_submit(
            state,
            SubmitRequest(token=42, command_buffer_indices=(0,),
                          signal_indices=(0, 1), signal_values=(8, 14)),
        )
        self.assertEqual(result, "BadValue")
        self.assertEqual(state, before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
