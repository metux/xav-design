"""Cross-check timeline signal transitions against the shared XA state model.

The Host-Wait model and SubmissionModel cover different request surfaces, but
their canonical timeline counter and GPU signal reservations must agree for the
same signal/host-signal interleavings.
"""
from __future__ import annotations

import copy
import unittest

from timeline_host_wait_model import Timeline
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


def submission_state() -> SubmissionModel:
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


def reserve(state: SubmissionModel, token: int, value: int) -> None:
    index = 0 if token == 101 else 1
    assert queue_submit(
        state,
        SubmitRequest(
            token=token,
            command_buffer_indices=(index,),
            signal_indices=(0,),
            signal_values=(value,),
        ),
    ) == "SUCCESS"


class TimelineModelConsistencyTests(unittest.TestCase):
    def assert_counters_match(self, host: Timeline, submit: SubmissionModel) -> None:
        self.assertEqual(host.counter, submit.signal_counters[0])
        self.assertEqual(
            sorted(host.pending_gpu_signals.values()),
            sorted(value for _token, index, value in submit.pending_timeline_signals if index == 0),
        )

    def test_host_signal_below_reservation_then_gpu_completion(self) -> None:
        host = Timeline(counter=2)
        submit = submission_state()
        self.assertEqual(host.reserve_gpu_signal(101, 9), "SUCCESS")
        reserve(submit, 101, 9)

        self.assertEqual(host.signal_host(6), "SUCCESS")
        self.assertEqual(signal_timeline_host(submit, 0, 6), "SUCCESS")
        self.assert_counters_match(host, submit)

        self.assertEqual(host.finish_gpu_signal(101, success=True), "SUCCESS")
        self.assertEqual(finish_submission(submit, 101, success=True), "SUCCESS")
        self.assert_counters_match(host, submit)
        self.assertEqual(host.counter, 9)

    def test_rejected_host_signal_is_atomic_in_both_models(self) -> None:
        host = Timeline(counter=2)
        submit = submission_state()
        self.assertEqual(host.reserve_gpu_signal(101, 9), "SUCCESS")
        reserve(submit, 101, 9)
        host_before = copy.deepcopy(host)
        submit_before = copy.deepcopy(submit)

        self.assertEqual(host.signal_host(9), "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual(signal_timeline_host(submit, 0, 9), "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual(host, host_before)
        self.assertEqual(submit, submit_before)
        self.assert_counters_match(host, submit)

    def test_out_of_order_gpu_success_keeps_counter_monotonic(self) -> None:
        host = Timeline(counter=2)
        submit = submission_state()
        for token, value in ((101, 9), (102, 12)):
            self.assertEqual(host.reserve_gpu_signal(token, value), "SUCCESS")
            reserve(submit, token, value)

        self.assertEqual(host.signal_host(6), "SUCCESS")
        self.assertEqual(signal_timeline_host(submit, 0, 6), "SUCCESS")
        self.assertEqual(host.finish_gpu_signal(102, success=True), "SUCCESS")
        self.assertEqual(finish_submission(submit, 102, success=True), "SUCCESS")
        self.assert_counters_match(host, submit)
        self.assertEqual(host.counter, 12)

        self.assertEqual(host.finish_gpu_signal(101, success=True), "SUCCESS")
        self.assertEqual(finish_submission(submit, 101, success=True), "SUCCESS")
        self.assert_counters_match(host, submit)
        self.assertEqual(host.counter, 12)
        self.assertEqual(submit.signal_slots, [None])

    def test_failed_high_signal_releases_only_its_reservation(self) -> None:
        host = Timeline(counter=2)
        submit = submission_state()
        for token, value in ((101, 9), (102, 12)):
            self.assertEqual(host.reserve_gpu_signal(token, value), "SUCCESS")
            reserve(submit, token, value)

        self.assertEqual(host.signal_host(6), "SUCCESS")
        self.assertEqual(signal_timeline_host(submit, 0, 6), "SUCCESS")
        self.assertEqual(host.finish_gpu_signal(102, success=False), "SUCCESS")
        self.assertEqual(finish_submission(submit, 102, success=False), "SUCCESS")
        self.assert_counters_match(host, submit)
        self.assertEqual(host.counter, 6)
        self.assertEqual(submit.signal_slots, [9])

        self.assertEqual(host.finish_gpu_signal(101, success=True), "SUCCESS")
        self.assertEqual(finish_submission(submit, 101, success=True), "SUCCESS")
        self.assert_counters_match(host, submit)
        self.assertEqual(host.counter, 9)
        self.assertEqual(submit.signal_slots, [None])

    def test_device_loss_blocks_late_success_from_advancing_counter(self) -> None:
        host = Timeline(counter=2)
        submit = submission_state()
        self.assertEqual(host.reserve_gpu_signal(101, 9), "SUCCESS")
        reserve(submit, 101, 9)

        self.assertEqual(host.mark_device_lost(), "SUCCESS")
        submit.device_lost = True
        self.assertEqual(host.finish_gpu_signal(101, success=True), "SUCCESS")
        self.assertEqual(finish_submission(submit, 101, success=True), "SUCCESS")
        self.assert_counters_match(host, submit)
        self.assertEqual(host.counter, 2)
        self.assertEqual(host.terminal_waits, {})
        self.assertEqual(submit.pending_timeline_signals, [])
        self.assertEqual(submit.signal_slots, [None])


if __name__ == "__main__":
    unittest.main()
