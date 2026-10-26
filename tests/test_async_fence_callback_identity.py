"""Regression tests for delayed fence callbacks across reset and XID reuse."""
from __future__ import annotations

import unittest

from xa_state_model import AsyncFenceCallbackModel, AsyncFenceIdentity


class AsyncFenceCallbackIdentityTests(unittest.TestCase):
    def setUp(self):
        self.model = AsyncFenceCallbackModel()
        self.model.register_device("device-1")
        self.old = AsyncFenceIdentity("fence-generation-1", 44, "device-1")
        self.assertEqual(self.model.register_fence(self.old), "SUCCESS")

    def test_fence_cannot_be_destroyed_while_callback_is_pending(self):
        self.assertEqual(self.model.accept(self.old, 1001), "SUCCESS")
        self.assertEqual(self.model.destroy(self.old), "INVALID_SYNCHRONIZATION_STATE")
        self.assertTrue(self.old.live)
        self.assertEqual(self.old.status, "PENDING")

    def test_completed_fence_may_reset_and_start_new_operation(self):
        self.assertEqual(self.model.accept(self.old, 1001), "SUCCESS")
        self.assertEqual(self.model.callback(self.old, 1001, True), "SUCCESS")
        self.assertEqual(self.model.reset(self.old), "SUCCESS")
        self.assertEqual(self.old.generation, 1)
        self.assertEqual(self.model.accept(self.old, 1002), "SUCCESS")
        self.assertEqual(self.model.callback(self.old, 1001, False), "BadValue")
        self.assertEqual(self.old.status, "PENDING")
        self.assertEqual(self.model.callback(self.old, 1002, False), "SUCCESS")
        self.assertEqual(self.old.status, "FAILED")

    def test_stale_callback_after_fence_xid_reuse_cannot_signal_replacement(self):
        self.assertEqual(self.model.accept(self.old, 1001), "SUCCESS")
        self.assertEqual(self.model.callback(self.old, 1001, True), "SUCCESS")
        self.assertEqual(self.model.destroy(self.old), "SUCCESS")
        replacement = AsyncFenceIdentity("fence-generation-2", 44, "device-1")
        self.assertEqual(self.model.register_fence(replacement), "SUCCESS")
        self.assertEqual(self.model.callback(self.old, 1001, False), "BadValue")
        self.assertEqual(replacement.status, "UNSIGNALED")
        self.assertIs(self.model.fences[44], replacement)

    def test_device_loss_turns_late_success_into_failed_fence(self):
        self.assertEqual(self.model.accept(self.old, 1001), "SUCCESS")
        self.model.devices["device-1"] = False
        self.assertEqual(self.model.callback(self.old, 1001, True), "SUCCESS")
        self.assertEqual(self.old.status, "FAILED")
        self.assertEqual(self.model.accept(self.old, 1002), "DEVICE_LOST")
        self.assertEqual(self.model.reset(self.old), "DEVICE_LOST")


if __name__ == "__main__":
    unittest.main()
