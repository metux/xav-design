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


    def test_presentation_request_error_paths_match_registry(self):
        presentation = (ROOT / "spec/presentation.md").read_text(encoding="utf-8")
        synchronization = (ROOT / "spec/synchronization.md").read_text(encoding="utf-8")
        registry = (ROOT / "registries/request-subopcodes.md").read_text(encoding="utf-8")
        cases = {
            "CreateSurface": ("BadIDChoice", "BadWindow", "BadMatch"),
            "DestroySurface": ("BadValue", "BadMatch", "INVALID_SYNCHRONIZATION_STATE"),
            "GetSurfaceCapabilities": ("BadValue", "BadMatch", "SURFACE_LOST", "DEVICE_LOST"),
            "CreateSwapchain": ("BadIDChoice", "BadValue", "BadMatch", "OUT_OF_DATE", "SURFACE_LOST", "DEVICE_LOST", "ALLOCATION_FAILED", "UNSUPPORTED_CONFIGURATION"),
            "DestroySwapchain": ("BadValue", "BadMatch", "INVALID_SYNCHRONIZATION_STATE"),
            "AcquireNextImage": ("BadValue", "BadMatch", "INVALID_SYNCHRONIZATION_STATE", "NOT_READY", "TIMEOUT", "OUT_OF_DATE", "SURFACE_LOST", "DEVICE_LOST", "DEVICE_DESTROYED"),
            "QueuePresent": ("BadValue", "BadMatch", "INVALID_SYNCHRONIZATION_STATE", "DEPENDENCY_FAILED", "OUT_OF_DATE", "SURFACE_LOST", "DEVICE_LOST"),
        }
        for subopcode, (request, outcomes) in enumerate(cases.items(), start=41):
            with self.subTest(request=request):
                self.assertIn("`" + request + "`", registry)
                self.assertIn("`" + request + "`", presentation)
                self.assertIn("`" + request + "`", self.errors)
                self.assertIn(f"`{request}` | {subopcode} |", registry)
                for outcome in outcomes:
                    self.assertIn(outcome, self.errors)
                    self.assertTrue(
                        outcome in presentation or outcome in synchronization,
                        f"{outcome} has no presentation/synchronization contract",
                    )

    def test_presentation_rejections_preserve_state_and_status_is_not_x11_error(self):
        presentation = (ROOT / "spec/presentation.md").read_text(encoding="utf-8")
        self.assertIn("leaves the target XID unallocated", presentation)
        self.assertIn("no partial object, reference, image-state, synchronization-state, or token change", self.errors)
        self.assertIn("Token uniqueness is checked against previously accepted presentations", self.errors)
        self.assertIn("first terminal result serialized", self.errors)
        self.assertIn("QueuePresent reply status values are 0 SUCCESS", presentation)
        self.assertIn("normal reply statuses", self.errors)


    def test_synchronization_request_rejection_matrix_matches_registry(self):
        registry = (ROOT / "registries/request-subopcodes.md").read_text(encoding="utf-8")
        synchronization = (ROOT / "spec/synchronization.md").read_text(encoding="utf-8")
        section = self.conformance.split(
            "## Synchronization request rejection matrix", 1
        )[1]
        cases = {
            "CreateSemaphore": ("BadLength", "BadValue", "BadIDChoice", "ALLOCATION_FAILED"),
            "CreateFence": ("BadLength", "BadValue", "BadIDChoice", "ALLOCATION_FAILED"),
            "SignalSemaphore": ("BadMatch", "DEVICE_LOST", "INVALID_SYNCHRONIZATION_STATE"),
            "WaitSemaphores": ("BadLength", "BadValue", "BadMatch", "DEVICE_LOST"),
            "WaitForFence": ("BadLength", "BadValue", "BadMatch", "TIMEOUT", "DEVICE_LOST", "DEVICE_DESTROYED"),
            "GetFenceStatus": ("BadLength", "BadValue", "BadMatch"),
            "GetSemaphoreCounterValue": ("BadLength", "BadValue", "BadMatch", "DEVICE_LOST"),
            "ResetFence": ("BadLength", "BadValue", "BadMatch", "DEVICE_LOST", "INVALID_SYNCHRONIZATION_STATE"),
            "DestroyFence": ("BadLength", "BadValue", "BadMatch", "INVALID_SYNCHRONIZATION_STATE"),
            "DestroySemaphore": ("BadLength", "BadValue", "BadMatch", "INVALID_SYNCHRONIZATION_STATE"),
        }
        for request, outcomes in cases.items():
            with self.subTest(request=request):
                self.assertIn("`" + request + "`", registry)
                self.assertIn("`" + request + "`", synchronization)
                self.assertIn("`" + request + "`", section)
                self.assertIn("`" + request + "`", self.errors)
                for outcome in outcomes:
                    self.assertIn(outcome, section)
                    self.assertIn(outcome, self.errors)

    def test_synchronization_rejections_preserve_wait_and_signal_state(self):
        section = self.conformance.split(
            "## Synchronization request rejection matrix", 1
        )[1]
        for phrase in (
            "Every rejection leaves the target XID unallocated",
            "counter and all reservations remain unchanged",
            "No synchronous rejection may install a wait registration",
            "all rejections preserve the stored state",
            "an unsent reply alone must not block destruction",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, section)

if __name__ == "__main__":
    unittest.main()
