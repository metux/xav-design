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
        self.assertIn("leaves the allocation unchanged", self.errors)
        self.assertIn("no partial free", section)

    def test_memory_free_checks_internal_buffer_liveness(self):
        self.assertIn(
            "internally live, bound Buffer", self.errors
        )
        self.assertIn(
            "internally live Buffer remains bound", self.conformance
        )
        self.assertIn("FreeMemory", self.lifetime)

    def test_fence_destroy_boundary_is_serialized_wait_result(self):
        self.assertIn("terminal result has been serialized", self.conformance)
        self.assertIn("an unsent reply alone does not keep destruction blocked", self.conformance)
        self.assertIn("open `WaitForFence` registration", self.errors)


if __name__ == "__main__":
    unittest.main()
