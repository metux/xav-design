"""Regression tests for delayed callbacks and public XID reuse."""
from __future__ import annotations

import unittest

from xa_state_model import (
    AsyncCallbackRegistry,
    AsyncDeviceIdentity,
    AsyncResourceIdentity,
)


class DelayedCallbackXidReuseTests(unittest.TestCase):
    def test_destroy_resource_then_reuse_xid_does_not_touch_replacement(self):
        registry = AsyncCallbackRegistry(connections_live={"client-A"})
        device = AsyncDeviceIdentity("device-generation-1", 7)
        old = AsyncResourceIdentity("resource-generation-1", 42, device.identity)
        registry.register_device(device)
        registry.register_resource(old)
        self.assertEqual(registry.destroy_resource(old), "SUCCESS")

        replacement = AsyncResourceIdentity("resource-generation-2", 42, device.identity)
        registry.register_resource(replacement)
        self.assertEqual(
            registry.complete_backend_callback(old, device, "client-A", token="submit-1"),
            "SUCCESS",
        )
        self.assertEqual(old.callback_count, 1)
        self.assertEqual(old.backend_refs, 0)
        self.assertEqual(replacement.callback_count, 0)
        self.assertEqual(replacement.backend_refs, 1)
        self.assertEqual(registry.emitted_events, [("submit-1", 7, 0)])

    def test_destroy_device_then_reuse_device_and_resource_xids_suppresses_event(self):
        registry = AsyncCallbackRegistry(connections_live={"client-A"})
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
                old_resource, old_device, "client-A", token="late-submit",
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
            registry.complete_backend_callback(resource, device, "closed-client", token="submit-3"),
            "SUCCESS",
        )
        self.assertEqual(resource.backend_refs, 0)
        self.assertEqual(resource.callback_count, 1)
        self.assertEqual(registry.emitted_events, [])

    def test_duplicate_callback_cannot_release_internal_reference_twice(self):
        registry = AsyncCallbackRegistry(connections_live={"client-A"})
        device = AsyncDeviceIdentity("device-generation-1", 7)
        resource = AsyncResourceIdentity("resource-generation-1", 42, device.identity)
        registry.register_device(device)
        registry.register_resource(resource)
        self.assertEqual(
            registry.complete_backend_callback(resource, device, "client-A", token="submit-4"),
            "SUCCESS",
        )
        snapshot = (resource.backend_refs, resource.callback_count, list(registry.emitted_events))
        self.assertEqual(
            registry.complete_backend_callback(resource, device, "client-A", token="submit-4"),
            "BadValue",
        )
        self.assertEqual(
            (resource.backend_refs, resource.callback_count, registry.emitted_events),
            snapshot,
        )


if __name__ == "__main__":
    unittest.main()
