"""Regression tests for delayed callbacks and public XID reuse."""
from __future__ import annotations

import unittest

from xa_state_model import (
    AsyncCallbackRegistry,
    AsyncDeviceIdentity,
    AsyncResourceIdentity,
    ConnectionInstance,
)


class DelayedCallbackXidReuseTests(unittest.TestCase):
    def test_destroy_resource_then_reuse_xid_does_not_touch_replacement(self):
        registry = AsyncCallbackRegistry()
        client_a = registry.connect("client-A")
        device = AsyncDeviceIdentity("device-generation-1", 7)
        old = AsyncResourceIdentity("resource-generation-1", 42, device.identity)
        registry.register_device(device)
        registry.register_resource(old)
        self.assertEqual(registry.destroy_resource(old), "SUCCESS")

        replacement = AsyncResourceIdentity("resource-generation-2", 42, device.identity)
        registry.register_resource(replacement)
        self.assertEqual(
            registry.complete_backend_callback(old, device, client_a, token="submit-1"),
            "SUCCESS",
        )
        self.assertEqual(old.callback_count, 1)
        self.assertEqual(old.backend_refs, 0)
        self.assertEqual(replacement.callback_count, 0)
        self.assertEqual(replacement.backend_refs, 1)
        self.assertEqual(registry.emitted_events, [("submit-1", 7, 0)])

    def test_destroy_device_then_reuse_device_and_resource_xids_suppresses_event(self):
        registry = AsyncCallbackRegistry()
        client_a = registry.connect("client-A")
        old_device = AsyncDeviceIdentity("device-generation-1", 7)
        old_resource = AsyncResourceIdentity("resource-generation-1", 42, old_device.identity)
        registry.register_device(old_device)
        registry.register_resource(old_resource)
        self.assertEqual(registry.destroy_device(old_device), "SUCCESS")

        new_device = AsyncDeviceIdentity("device-generation-2", 7)
        new_resource = AsyncResourceIdentity("resource-generation-2", 42, new_device.identity)
        registry.register_device(new_device)
        registry.register_resource(new_resource)
        self.assertEqual(
            registry.complete_backend_callback(
                old_resource, old_device, client_a, token="late-submit",
            ),
            "SUCCESS",
        )
        self.assertEqual(old_resource.backend_refs, 0)
        self.assertEqual(old_resource.callback_count, 1)
        self.assertEqual(new_resource.backend_refs, 1)
        self.assertEqual(new_resource.callback_count, 0)
        self.assertEqual(registry.emitted_events, [])

    def test_disconnect_suppresses_event_but_still_releases_captured_reference(self):
        registry = AsyncCallbackRegistry()
        device = AsyncDeviceIdentity("device-generation-1", 7)
        resource = AsyncResourceIdentity("resource-generation-1", 42, device.identity)
        registry.register_device(device)
        registry.register_resource(resource)
        self.assertEqual(
            registry.complete_backend_callback(resource, device, ConnectionInstance("closed-client"), token="submit-3"),
            "SUCCESS",
        )
        self.assertEqual(resource.backend_refs, 0)
        self.assertEqual(resource.callback_count, 1)
        self.assertEqual(registry.emitted_events, [])

    def test_callback_cannot_pair_resource_with_another_devices_identity(self):
        registry = AsyncCallbackRegistry()
        client_a = registry.connect("client-A")
        device_a = AsyncDeviceIdentity("device-A", 7)
        device_b = AsyncDeviceIdentity("device-B", 8)
        resource_a = AsyncResourceIdentity("resource-A", 42, device_a.identity)
        registry.register_device(device_a)
        registry.register_device(device_b)
        registry.register_resource(resource_a)

        # The captured reference still retires exactly once, but a mismatched
        # device/resource pair must never emit an event for the wrong device.
        self.assertEqual(
            registry.complete_backend_callback(
                resource_a, device_b, client_a, token="cross-device",
            ),
            "SUCCESS",
        )
        self.assertEqual(resource_a.backend_refs, 0)
        self.assertEqual(resource_a.callback_count, 1)
        self.assertEqual(registry.emitted_events, [])

    def test_duplicate_callback_cannot_release_internal_reference_twice(self):
        registry = AsyncCallbackRegistry()
        client_a = registry.connect("client-A")
        device = AsyncDeviceIdentity("device-generation-1", 7)
        resource = AsyncResourceIdentity(
            "resource-generation-1", 42, device.identity, backend_refs=2,
        )
        registry.register_device(device)
        registry.register_resource(resource)
        self.assertEqual(
            registry.complete_backend_callback(resource, device, client_a, token="submit-4"),
            "SUCCESS",
        )
        snapshot = (resource.backend_refs, resource.callback_count, list(registry.emitted_events))
        self.assertEqual(
            registry.complete_backend_callback(resource, device, client_a, token="submit-4"),
            "BadValue",
        )
        self.assertEqual(
            (resource.backend_refs, resource.callback_count, registry.emitted_events),
            snapshot,
        )
        self.assertEqual(resource.backend_refs, 1)


    def test_reconnect_uses_fresh_connection_handle_for_delayed_resource_callback(self):
        # The human-readable peer label is deliberately the same. The callback
        # captures an opaque handle for the old X11 connection instance.
        registry = AsyncCallbackRegistry()
        old_connection = registry.connect("same-peer")
        device = AsyncDeviceIdentity("device-generation-1", 7)
        resource = AsyncResourceIdentity("resource-generation-1", 42, device.identity)
        registry.register_device(device)
        registry.register_resource(resource)

        registry.disconnect(old_connection)
        new_connection = registry.connect("same-peer")

        self.assertEqual(
            registry.complete_backend_callback(
                resource, device, old_connection, token="old-connection-submit",
            ),
            "SUCCESS",
        )
        self.assertEqual(registry.emitted_events, [])
        self.assertEqual(resource.backend_refs, 0)

        # A fresh operation on the new connection can deliver, but the old
        # callback cannot be retargeted by a reused client name.
        replacement = AsyncResourceIdentity("resource-generation-2", 43, device.identity)
        registry.register_resource(replacement)
        self.assertEqual(
            registry.complete_backend_callback(
                replacement, device, new_connection, token="new-connection-submit",
            ),
            "SUCCESS",
        )
        self.assertEqual(
            registry.emitted_events, [("new-connection-submit", 7, 43)]
        )


    def test_reusable_string_label_is_not_a_connection_identity(self):
        registry = AsyncCallbackRegistry()
        connection = registry.connect("reused-label")
        device = AsyncDeviceIdentity("device-generation-1", 7)
        resource = AsyncResourceIdentity("resource-generation-1", 42, device.identity)
        registry.register_device(device)
        registry.register_resource(resource)
        self.assertEqual(
            registry.complete_backend_callback(
                resource, device, "reused-label", token="string-label-only",
            ),
            "SUCCESS",
        )
        self.assertEqual(registry.emitted_events, [])
        self.assertEqual(resource.backend_refs, 0)
        with self.assertRaises(TypeError):
            registry.disconnect("reused-label")
        self.assertIn(connection, registry.connections_live)


if __name__ == "__main__":
    unittest.main()
