#!/usr/bin/env python3
"""Guard the remaining resource-lifetime negative-test matrix against error-map drift."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RequestErrorPathCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.errors = (ROOT / "spec/errors.md").read_text(encoding="utf-8")
        cls.conformance = (ROOT / "spec/conformance.md").read_text(encoding="utf-8")
        cls.lifetime = (ROOT / "spec/resource-lifetime.md").read_text(encoding="utf-8")

    def test_each_added_negative_path_is_present_and_mapped(self):
        cases = {
            "FreeMemory": ("BadMatch", "INVALID_SYNCHRONIZATION_STATE"),
            "BindBufferMemory": ("BadLength", "BadValue", "BadMatch", "DEVICE_LOST"),
            "DestroyResource": ("BadValue", "BadMatch", "INVALID_SYNCHRONIZATION_STATE"),
            "FreeDescriptorSets": ("BadMatch", "INVALID_SYNCHRONIZATION_STATE"),
            "DestroyDescriptorPool": ("INVALID_SYNCHRONIZATION_STATE",),
            "ResetFence": ("INVALID_SYNCHRONIZATION_STATE",),
            "DestroyFence": ("INVALID_SYNCHRONIZATION_STATE",),
        }
        section = self.conformance.split(
            "## Remaining request error-path negative tests", 1
        )[1]
        for request, outcomes in cases.items():
            with self.subTest(request=request):
                self.assertIn("`" + request + "`", section)
                self.assertIn("`" + request + "`", self.errors)
                for outcome in outcomes:
                    self.assertIn(outcome, section)
                    self.assertIn(outcome, self.errors)

    def test_batch_and_lifetime_failures_require_atomic_rejection(self):
        section = self.conformance.split(
            "## Remaining request error-path negative tests", 1
        )[1]
        self.assertIn("no earlier Set freed", section)
        self.assertIn("Pool, all child Sets, and all Pool capacity accounting remain unchanged", section)
        self.assertIn("Bei Ablehnung bleibt die Allokation unverändert", self.errors)
        self.assertIn("no partial free", section)

    def test_memory_free_checks_internal_buffer_liveness(self):
        self.assertIn(
            "intern noch lebender, gebundener Buffer", self.errors
        )
        self.assertIn(
            "internally live Buffer remains bound", self.conformance
        )
        self.assertIn("FreeMemory", self.lifetime)

    def test_fence_destroy_boundary_is_serialized_wait_result(self):
        self.assertIn("terminal result has been serialized", self.conformance)
        self.assertIn("an unsent reply alone does not keep destruction blocked", self.conformance)
        self.assertIn("offene `WaitForFence`-Registrierung", self.errors)

    def test_discovery_allocation_and_transfer_negative_matrix(self):
        section = self.conformance.split(
            "## Discovery, allocation, and transfer rejection matrix", 1
        )[1]
        cases = {
            "EnumeratePhysicalDevices": ("UTF-8", "empty reply"),
            "GetPhysicalDeviceProperty": ("BadAtom", "NOT_SUPPORTED", "NOT_AVAILABLE"),
            "GetPhysicalDeviceQueueFamilyProperties": ("BadLength", "BadValue", "BadMatch"),
            "GetPhysicalDeviceMemoryProperties": ("BadLength", "BadValue", "BadMatch"),
            "CreateDefaultDevice": ("BadValue", "BadIDChoice", "DEVICE_UNAVAILABLE"),
            "CreateBuffer": ("BadLength", "BadValue", "BadIDChoice", "DEVICE_LOST", "ALLOCATION_FAILED"),
            "AllocateMemory": ("BadLength", "BadValue", "BadIDChoice", "DEVICE_LOST", "ALLOCATION_FAILED"),
            "GetBufferMemoryRequirements": ("BadLength", "BadValue", "BadMatch"),
            "ReadBuffer": ("BadLength", "BadValue", "BadMatch", "DEVICE_LOST", "TRANSFER_FAILED", "ALLOCATION_FAILED", "DEPENDENCY_FAILED"),
            "UpdateDescriptorSets": ("DEVICE_LOST", "INVALID_SYNCHRONIZATION_STATE"),
        }
        for request, outcomes in cases.items():
            with self.subTest(request=request):
                self.assertIn("`" + request + "`", section)
                self.assertIn("`" + request + "`", self.errors)
                for outcome in outcomes:
                    self.assertIn(outcome, section)

    def test_discovery_and_memory_request_names_match_registry(self):
        registry = (ROOT / "registries/request-subopcodes.md").read_text(encoding="utf-8")
        names = (
            "EnumeratePhysicalDevices", "GetPhysicalDeviceProperty",
            "GetPhysicalDeviceQueueFamilyProperties", "GetPhysicalDeviceMemoryProperties",
            "CreateDefaultDevice", "CreateBuffer", "AllocateMemory",
            "GetBufferMemoryRequirements", "ReadBuffer", "UpdateDescriptorSets",
        )
        for name in names:
            with self.subTest(request=name):
                self.assertIn("`" + name + "`", registry)
                self.assertIn("`" + name + "`", self.conformance)


if __name__ == "__main__":
    unittest.main()
