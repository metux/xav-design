"""Regression tests for terminal submission callbacks and event selection."""
from __future__ import annotations

import unittest

from xa_state_model import (
    AsyncDeviceIdentity,
    AsyncSubmissionEventRegistry,
    AsyncSubmissionIdentity,
)


class SubmissionEventCallbackIdentityTests(unittest.TestCase):
    def setup_registry(self):
        registry = AsyncSubmissionEventRegistry(live_connections={"client-old", "client-new"})
        device = AsyncDeviceIdentity("device-generation-1", 7)
        registry.register_device("client-old", device)
        submission = AsyncSubmissionIdentity(
            token=99, connection_identity="client-old",
            device_identity=device.identity, device_xid=7, queue_key=(0, 0),
        )
        self.assertEqual(registry.accept_submission(submission), "SUCCESS")
        return registry, device, submission

    def test_terminal_event_uses_mask_at_callback_linearization(self):
        registry, device, submission = self.setup_registry()
        self.assertEqual(registry.select_queue_events("client-old", device.identity, (0, 0), 1), "SUCCESS")
        self.assertEqual(registry.terminal_callback("client-old", 99, "COMPLETE"), "SUCCESS")
        self.assertEqual(registry.emitted_events, [("COMPLETE", "client-old", 7, 99)])
        self.assertEqual(registry.select_queue_events("client-old", device.identity, (0, 0), 0), "SUCCESS")
        self.assertEqual(registry.terminal_callback("client-old", 99, "FAILED"), "BadValue")
        self.assertEqual(len(registry.emitted_events), 1)

    def test_destroy_device_before_callback_suppresses_event_and_old_xid_reuse_isolated(self):
        registry, old_device, old_submission = self.setup_registry()
        self.assertEqual(registry.select_queue_events("client-old", old_device.identity, (0, 0), 3), "SUCCESS")
        self.assertEqual(registry.destroy_device(old_device.identity), "SUCCESS")
        new_device = AsyncDeviceIdentity("device-generation-2", 7)
        registry.register_device("client-new", new_device)
        replacement = AsyncSubmissionIdentity(
            token=99, connection_identity="client-new",
            device_identity=new_device.identity, device_xid=7, queue_key=(0, 0),
        )
        self.assertEqual(registry.accept_submission(replacement), "SUCCESS")
        self.assertEqual(registry.terminal_callback("client-old", 99, "COMPLETE"), "SUCCESS")
        self.assertEqual(registry.emitted_events, [])
        self.assertEqual(old_submission.terminal, "COMPLETE")
        self.assertNotIn(("client-old", 99), registry.submissions)
        self.assertIs(registry.submissions[("client-new", 99)], replacement)
        self.assertEqual(registry.terminal_callback("client-new", 99, "FAILED"), "SUCCESS")
        self.assertNotIn(("client-new", 99), registry.submissions)
        self.assertEqual(registry.emitted_events, [])

    def test_disconnect_suppresses_terminal_and_async_error_delivery(self):
        registry, device, _ = self.setup_registry()
        self.assertEqual(registry.select_queue_events("client-old", device.identity, (0, 0), 3), "SUCCESS")
        registry.disconnect("client-old")
        self.assertEqual(registry.terminal_callback("client-old", 99, "FAILED"), "SUCCESS")
        self.assertEqual(registry.async_error("client-old", device, 99), "SUCCESS")
        self.assertEqual(registry.emitted_events, [])
        self.assertNotIn(("client-old", 99), registry.submissions)

    def test_async_error_ignores_select_events_mask_but_not_destroyed_device(self):
        registry, device, _ = self.setup_registry()
        self.assertEqual(registry.async_error("client-old", device, 99), "SUCCESS")
        self.assertEqual(registry.emitted_events, [("ASYNC_ERROR", "client-old", 7, 99)])
        self.assertEqual(registry.destroy_device(device.identity), "SUCCESS")
        self.assertEqual(registry.async_error("client-old", device, 99), "SUCCESS")
        self.assertEqual(len(registry.emitted_events), 1)


if __name__ == "__main__":
    unittest.main()
