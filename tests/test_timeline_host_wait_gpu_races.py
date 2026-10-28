"""Regression tests for Host WaitSemaphores vs GPU timeline signal races."""
from __future__ import annotations

import copy
import unittest

from timeline_host_wait_model import Timeline


class HostWaitGpuSignalRaceTests(unittest.TestCase):
    def test_gpu_signal_resolves_all_host_waits_at_or_below_value(self) -> None:
        timeline = Timeline(counter=2)
        self.assertEqual(timeline.begin_host_wait(1, 5), "PENDING")
        self.assertEqual(timeline.begin_host_wait(2, 9), "PENDING")
        self.assertEqual(timeline.begin_host_wait(3, 9), "PENDING")
        self.assertEqual(timeline.reserve_gpu_signal(40, 9), "SUCCESS")

        self.assertEqual(timeline.finish_gpu_signal(40, success=True), "SUCCESS")
        self.assertEqual(timeline.counter, 9)
        self.assertEqual(timeline.terminal_waits, {1: "SUCCESS", 2: "SUCCESS", 3: "SUCCESS"})
        self.assertEqual(timeline.pending_host_waits, {})

    def test_host_signal_resolves_wait_without_stealing_gpu_reservation(self) -> None:
        timeline = Timeline(counter=2)
        self.assertEqual(timeline.begin_host_wait(10, 6), "PENDING")
        self.assertEqual(timeline.begin_host_wait(11, 9), "PENDING")
        self.assertEqual(timeline.reserve_gpu_signal(41, 9), "SUCCESS")

        self.assertEqual(timeline.signal_host(6), "SUCCESS")
        self.assertEqual(timeline.terminal_waits, {10: "SUCCESS"})
        self.assertEqual(timeline.pending_host_waits, {11: 9})
        self.assertEqual(timeline.pending_gpu_signals, {41: 9})

        self.assertEqual(timeline.finish_gpu_signal(41, success=True), "SUCCESS")
        self.assertEqual(timeline.terminal_waits, {10: "SUCCESS", 11: "SUCCESS"})
        self.assertEqual(timeline.counter, 9)

    def test_failed_gpu_signal_leaves_wait_pending_until_another_signal(self) -> None:
        timeline = Timeline(counter=2)
        self.assertEqual(timeline.begin_host_wait(20, 8), "PENDING")
        self.assertEqual(timeline.reserve_gpu_signal(42, 8), "SUCCESS")
        self.assertEqual(timeline.finish_gpu_signal(42, success=False), "SUCCESS")
        self.assertEqual(timeline.counter, 2)
        self.assertEqual(timeline.pending_host_waits, {20: 8})
        self.assertEqual(timeline.terminal_waits, {})

        self.assertEqual(timeline.signal_host(8), "SUCCESS")
        self.assertEqual(timeline.terminal_waits, {20: "SUCCESS"})

    def test_timeout_final_check_prefers_already_satisfied_wait(self) -> None:
        timeline = Timeline(counter=2)
        self.assertEqual(timeline.begin_host_wait(25, 8), "PENDING")

        # Model the counter becoming observable before the timeout path runs
        # its final predicate check. The final check must prefer satisfaction
        # and consume the pending registration exactly once.
        timeline.counter = 8
        self.assertEqual(timeline.finish_host_wait(25, "TIMEOUT"), "SUCCESS")
        self.assertEqual(timeline.terminal_waits, {25: "SUCCESS"})
        self.assertEqual(timeline.pending_host_waits, {})

    def test_timeout_terminal_result_cannot_be_overwritten_by_late_gpu_signal(self) -> None:
        timeline = Timeline(counter=2)
        self.assertEqual(timeline.begin_host_wait(30, 8), "PENDING")
        self.assertEqual(timeline.reserve_gpu_signal(43, 8), "SUCCESS")
        self.assertEqual(timeline.finish_host_wait(30, "TIMEOUT"), "SUCCESS")
        self.assertEqual(timeline.finish_gpu_signal(43, success=True), "SUCCESS")
        self.assertEqual(timeline.terminal_waits, {30: "TIMEOUT"})
        self.assertEqual(timeline.pending_host_waits, {})
        self.assertEqual(timeline.counter, 8)
        self.assertEqual(timeline.finish_host_wait(30, "SUCCESS"), "BadValue")
        self.assertEqual(timeline.terminal_waits, {30: "TIMEOUT"})

    def test_already_satisfied_host_wait_completes_immediately_and_is_one_shot(self) -> None:
        timeline = Timeline(counter=8)
        self.assertEqual(timeline.begin_host_wait(50, 8), "SUCCESS")
        before = copy.deepcopy(timeline)
        self.assertEqual(timeline.finish_host_wait(50, "TIMEOUT"), "BadValue")
        self.assertEqual(timeline, before)

    def test_rejected_host_signal_does_not_wake_wait_or_change_reservations(self) -> None:
        timeline = Timeline(counter=2)
        self.assertEqual(timeline.begin_host_wait(60, 8), "PENDING")
        self.assertEqual(timeline.reserve_gpu_signal(44, 8), "SUCCESS")
        before = copy.deepcopy(timeline)

        self.assertEqual(timeline.signal_host(8), "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual(timeline, before)

    def test_device_loss_terminates_open_wait_but_late_gpu_callback_cannot_rewrite_it(self) -> None:
        timeline = Timeline(counter=2)
        self.assertEqual(timeline.begin_host_wait(70, 8), "PENDING")
        self.assertEqual(timeline.reserve_gpu_signal(47, 8), "SUCCESS")
        self.assertEqual(timeline.mark_device_lost(), "SUCCESS")
        self.assertEqual(timeline.pending_host_waits, {})
        self.assertEqual(timeline.terminal_waits, {70: "DEVICE_LOST"})
        self.assertEqual(timeline.finish_gpu_signal(47, success=True), "SUCCESS")
        self.assertEqual(timeline.counter, 2)
        self.assertEqual(timeline.terminal_waits, {70: "DEVICE_LOST"})
        self.assertEqual(timeline.signal_host(9), "DEVICE_LOST")

    def test_destroy_device_terminates_wait_and_late_loss_does_not_override_it(self) -> None:
        timeline = Timeline(counter=2)
        self.assertEqual(timeline.begin_host_wait(80, 8), "PENDING")
        self.assertEqual(timeline.destroy_device(), "SUCCESS")
        self.assertEqual(timeline.terminal_waits, {80: "DEVICE_DESTROYED"})
        self.assertEqual(timeline.mark_device_lost(), "SUCCESS")
        self.assertEqual(timeline.terminal_waits, {80: "DEVICE_DESTROYED"})
        self.assertEqual(timeline.begin_host_wait(81, 9), "DEVICE_DESTROYED")
