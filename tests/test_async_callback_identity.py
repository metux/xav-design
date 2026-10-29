"""Regression tests for delayed callbacks and public XID reuse."""
from __future__ import annotations

import unittest

from xa_state_model import (
    AsyncCallbackRegistry,
    AsyncDeviceIdentity,
    AsyncResourceIdentity,
    ConnectionInstance,
)


CLIENT_A = ConnectionInstance("client-A")
CLOSED_CLIENT = ConnectionInstance("closed-client")


class DelayedCallbackXidReuseTests(unittest.TestCase):
    def test_destroy_resource_then_reuse_xid_does_not_touch_replacement(self):
        registry = AsyncCallbackRegistry(connections_live={CLIENT_A})
        device = AsyncDeviceIdentity("device-generation-1", 7)
        old = AsyncResourceIdentity("resource-generation-1", 42, device.identity)
        registry.register_device(device)
        registry.register_resource(old)
        self.assertEqual(registry.destroy_resource(old), "SUCCESS")

        replacement = AsyncResourceIdentity("resource-generation-2", 42, device.identity)
        registry.register_resource(replacement)
        self.assertEqual(
            registry.complete_backend_callback(old, device, CLIENT_A, token="submit-1"),
            "SUCCESS",
        )
        self.assertEqual(old.callback_count, 1)
        self.assertEqual(old.backend_refs, 0)
        self.assertEqual(replacement.callback_count, 0)
        self.assertEqual(replacement.backend_refs, 1)
        self.assertEqual(registry.emitted_events, [("submit-1", 7, 0)])

    def test_destroy_device_then_reuse_device_and_resource_xids_suppresses_event(self):
        registry = AsyncCallbackRegistry(connections_live={CLIENT_A})
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
                old_resource, old_device, CLIENT_A, token="late-submit",
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
            registry.complete_backend_callback(resource, device, CLOSED_CLIENT, token="submit-3"),
            "SUCCESS",
        )
        self.assertEqual(resource.backend_refs, 0)
        self.assertEqual(resource.callback_count, 1)
        self.assertEqual(registry.emitted_events, [])

    def test_callback_cannot_pair_resource_with_another_devices_identity(self):
        registry = AsyncCallbackRegistry(connections_live={CLIENT_A})
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
                resource_a, device_b, CLIENT_A, token="cross-device",
            ),
            "SUCCESS",
        )
        self.assertEqual(resource_a.backend_refs, 0)
        self.assertEqual(resource_a.callback_count, 1)
        self.assertEqual(registry.emitted_events, [])

    def test_duplicate_callback_cannot_release_internal_reference_twice(self):
        registry = AsyncCallbackRegistry(connections_live={CLIENT_A})
        device = AsyncDeviceIdentity("device-generation-1", 7)
        resource = AsyncResourceIdentity(
            "resource-generation-1", 42, device.identity, backend_refs=2,
        )
        registry.register_device(device)
        registry.register_resource(resource)
        self.assertEqual(
            registry.complete_backend_callback(resource, device, CLIENT_A, token="submit-4"),
            "SUCCESS",
        )
        snapshot = (resource.backend_refs, resource.callback_count, list(registry.emitted_events))
        self.assertEqual(
            registry.complete_backend_callback(resource, device, CLIENT_A, token="submit-4"),
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
        old_connection = ConnectionInstance("same-peer")
        registry = AsyncCallbackRegistry(connections_live={old_connection})
        device = AsyncDeviceIdentity("device-generation-1", 7)
        resource = AsyncResourceIdentity("resource-generation-1", 42, device.identity)
        registry.register_device(device)
        registry.register_resource(resource)

        registry.disconnect(old_connection)
        new_connection = ConnectionInstance("same-peer")
        registry.connections_live.add(new_connection)

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


if __name__ == "__main__":
    unittest.main()
