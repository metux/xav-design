"""Regression tests for terminal submission callbacks and event selection."""
from __future__ import annotations

import unittest

from xa_state_model import (
    AsyncDeviceIdentity,
    AsyncSubmissionEventRegistry,
    AsyncSubmissionIdentity,
    ConnectionInstance,
)


class SubmissionEventCallbackIdentityTests(unittest.TestCase):
    def setup_registry(self):
        registry = AsyncSubmissionEventRegistry()
        old_connection = registry.connect("client-old")
        new_connection = registry.connect("client-new")
        device = AsyncDeviceIdentity("device-generation-1", 7)
        registry.register_device(old_connection, device)
        submission = AsyncSubmissionIdentity(
            token=99, connection_identity=old_connection,
            device_identity=device.identity, device_xid=7, queue_key=(0, 0),
        )
        self.assertEqual(registry.accept_submission(submission), "SUCCESS")
        return registry, old_connection, new_connection, device, submission

    def test_terminal_event_uses_mask_at_callback_linearization(self):
        registry, old_connection, _, device, _ = self.setup_registry()
        self.assertEqual(registry.select_queue_events(old_connection, device.identity, (0, 0), 1), "SUCCESS")
        self.assertEqual(registry.terminal_callback(old_connection, 99, "COMPLETE"), "SUCCESS")
        self.assertEqual(registry.emitted_events, [("COMPLETE", "client-old", 7, 99)])
        self.assertEqual(registry.select_queue_events(old_connection, device.identity, (0, 0), 0), "SUCCESS")
        self.assertEqual(registry.terminal_callback(old_connection, 99, "FAILED"), "BadValue")
        self.assertEqual(len(registry.emitted_events), 1)

    def test_destroy_device_before_callback_suppresses_event_and_old_xid_reuse_isolated(self):
        registry, old_connection, new_connection, old_device, old_submission = self.setup_registry()
        self.assertEqual(registry.select_queue_events(old_connection, old_device.identity, (0, 0), 3), "SUCCESS")
        self.assertEqual(registry.destroy_device(old_device.identity), "SUCCESS")
        new_device = AsyncDeviceIdentity("device-generation-2", 7)
        registry.register_device(new_connection, new_device)
        replacement = AsyncSubmissionIdentity(
            token=99, connection_identity=new_connection,
            device_identity=new_device.identity, device_xid=7, queue_key=(0, 0),
        )
        self.assertEqual(registry.accept_submission(replacement), "SUCCESS")
        self.assertEqual(registry.terminal_callback(old_connection, 99, "COMPLETE"), "SUCCESS")
        self.assertEqual(registry.emitted_events, [])
        self.assertEqual(old_submission.terminal, "COMPLETE")
        self.assertNotIn((old_connection, 99), registry.submissions)
        self.assertIs(registry.submissions[(new_connection, 99)], replacement)
        self.assertEqual(registry.terminal_callback(new_connection, 99, "FAILED"), "SUCCESS")
        self.assertNotIn((new_connection, 99), registry.submissions)
        self.assertEqual(registry.emitted_events, [])

    def test_disconnect_suppresses_terminal_and_async_error_delivery(self):
        registry, old_connection, _, device, _ = self.setup_registry()
        self.assertEqual(registry.select_queue_events(old_connection, device.identity, (0, 0), 3), "SUCCESS")
        registry.disconnect(old_connection)
        self.assertEqual(registry.terminal_callback(old_connection, 99, "FAILED"), "SUCCESS")
        self.assertEqual(registry.async_error(old_connection, device, 99), "SUCCESS")
        self.assertEqual(registry.emitted_events, [])
        self.assertNotIn((old_connection, 99), registry.submissions)

    def test_async_error_ignores_select_events_mask_but_not_destroyed_device(self):
        registry, old_connection, _, device, _ = self.setup_registry()
        self.assertEqual(registry.async_error(old_connection, device, 99), "SUCCESS")
        self.assertEqual(registry.emitted_events, [("ASYNC_ERROR", "client-old", 7, 99)])
        self.assertEqual(registry.destroy_device(device.identity), "SUCCESS")
        self.assertEqual(registry.async_error(old_connection, device, 99), "SUCCESS")
        self.assertEqual(len(registry.emitted_events), 1)

    def test_token_scope_is_connection_instance_and_old_callback_cannot_cross_reconnect(self):
        registry = AsyncSubmissionEventRegistry()
        old_connection = registry.connect("client-A")
        old_device = AsyncDeviceIdentity("device-generation-1", 7)
        registry.register_device(old_connection, old_device)
        old = AsyncSubmissionIdentity(
            token=1201, connection_identity=old_connection,
            device_identity=old_device.identity, device_xid=7, queue_key=(0, 0),
        )
        self.assertEqual(registry.accept_submission(old), "SUCCESS")
        registry.disconnect(old_connection)

        # A reconnect gets a new opaque key even for the same peer label.
        new_connection = registry.connect("client-A")
        new_device = AsyncDeviceIdentity("device-generation-2", 7)
        registry.register_device(new_connection, new_device)
        replacement = AsyncSubmissionIdentity(
            token=1201, connection_identity=new_connection,
            device_identity=new_device.identity, device_xid=7, queue_key=(0, 0),
        )
        self.assertEqual(registry.accept_submission(replacement), "SUCCESS")
        self.assertEqual(registry.terminal_callback(old_connection, 1201, "COMPLETE"), "SUCCESS")
        self.assertIsNone(replacement.terminal)
        self.assertIs(registry.submissions[(new_connection, 1201)], replacement)
        self.assertEqual(registry.terminal_callback(new_connection, 1201, "COMPLETE"), "SUCCESS")
        self.assertEqual(replacement.terminal, "COMPLETE")

    def test_delayed_async_error_cannot_target_reconnected_client_instance(self):
        registry = AsyncSubmissionEventRegistry()
        old_connection = registry.connect("client-A")
        old_device = AsyncDeviceIdentity("device-still-live", 7)
        registry.register_device(old_connection, old_device)
        registry.disconnect(old_connection)
        new_connection = registry.connect("client-A")
        new_device = AsyncDeviceIdentity("new-device-generation", 7)
        registry.register_device(new_connection, new_device)

        self.assertEqual(registry.async_error(old_connection, old_device, 1202), "SUCCESS")
        self.assertEqual(registry.emitted_events, [])
        self.assertEqual(registry.async_error(new_connection, new_device, 1202), "SUCCESS")
        self.assertEqual(registry.emitted_events, [("ASYNC_ERROR", "client-A", 7, 1202)])

    def test_connection_handles_are_distinct_and_retired_handle_cannot_reactivate(self):
        registry = AsyncSubmissionEventRegistry()
        old_connection = registry.connect("same-client")
        old_device = AsyncDeviceIdentity("device-old-connection", 71)
        registry.register_device(old_connection, old_device)
        old_submission = AsyncSubmissionIdentity(
            token=1301, connection_identity=old_connection,
            device_identity=old_device.identity, device_xid=71, queue_key=(0, 0),
        )
        self.assertEqual(registry.accept_submission(old_submission), "SUCCESS")
        registry.disconnect(old_connection)

        new_connection = registry.connect("same-client")
        self.assertIsInstance(old_connection, ConnectionInstance)
        self.assertIsNot(old_connection, new_connection)
        self.assertNotEqual(old_connection, new_connection)
        new_device = AsyncDeviceIdentity("device-new-connection", 72)
        registry.register_device(new_connection, new_device)
        replacement = AsyncSubmissionIdentity(
            token=1301, connection_identity=new_connection,
            device_identity=new_device.identity, device_xid=72, queue_key=(0, 0),
        )
        self.assertEqual(registry.accept_submission(replacement), "SUCCESS")
        self.assertEqual(registry.terminal_callback(old_connection, 1301, "COMPLETE"), "SUCCESS")
        self.assertIsNone(replacement.terminal)
        self.assertIn((new_connection, 1301), registry.submissions)
        self.assertEqual(registry.terminal_callback(new_connection, 1301, "COMPLETE"), "SUCCESS")
        self.assertEqual(replacement.terminal, "COMPLETE")
        self.assertEqual(registry.terminal_callback(old_connection, 1302, "COMPLETE"), "BadValue")

    def test_string_labels_are_rejected_by_every_connection_scoped_entrypoint(self):
        registry = AsyncSubmissionEventRegistry()
        connection = registry.connect("client-A")
        device = AsyncDeviceIdentity("device-A", 7)
        registry.register_device(connection, device)
        submission = AsyncSubmissionIdentity(
            token=1401, connection_identity=connection,
            device_identity=device.identity, device_xid=7, queue_key=(0, 0),
        )
        self.assertEqual(registry.accept_submission(submission), "SUCCESS")
        with self.assertRaises(ValueError):
            registry.register_device("client-A", AsyncDeviceIdentity("other", 8))
        self.assertEqual(registry.select_queue_events("client-A", device.identity, (0, 0), 1), "BadValue")
        self.assertEqual(registry.register_wait("client-A", 1402, "WaitForFence", ("fence-A",)), "BadValue")
        self.assertEqual(registry.terminal_callback("client-A", 1401, "COMPLETE"), "BadValue")
        self.assertEqual(registry.async_error("client-A", device, 1401), "SUCCESS")
        string_submission = AsyncSubmissionIdentity(
            token=1403, connection_identity="client-A",
            device_identity=device.identity, device_xid=7, queue_key=(0, 0),
        )
        self.assertEqual(registry.accept_submission(string_submission), "BadValue")
        with self.assertRaises(TypeError):
            registry.disconnect("client-A")
        with self.assertRaises(TypeError):
            AsyncSubmissionEventRegistry(live_connections={"client-A"})
        self.assertEqual(registry.terminal_callback(connection, 1401, "COMPLETE"), "SUCCESS")


if __name__ == "__main__":
    unittest.main()
