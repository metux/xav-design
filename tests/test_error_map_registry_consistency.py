#!/usr/bin/env python3
"""Guard against stale error-map claims about presentation request allocation."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ErrorMapRegistryConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.errors = (ROOT / "spec/errors.md").read_text(encoding="utf-8")
        cls.registry = (ROOT / "registries/request-subopcodes.md").read_text(encoding="utf-8")
        cls.conformance = (ROOT / "spec/conformance.md").read_text(encoding="utf-8")

    def test_presentation_error_map_acknowledges_assigned_request_ids(self):
        section = self.errors.split("### Presentation requests", 1)[1].split(
            "### Normative validation precedence", 1
        )[0]
        self.assertIn("subopcodes 41–47", section)
        self.assertNotRegex(
            section,
            r"(?i)(do not allocate request subopcodes|subopcodes remain unassigned)",
        )
        expected = {
            "CreateSurface": 41,
            "DestroySurface": 42,
            "GetSurfaceCapabilities": 43,
            "CreateSwapchain": 44,
            "DestroySwapchain": 45,
            "AcquireNextImage": 46,
            "QueuePresent": 47,
        }
        for name, opcode in expected.items():
            self.assertRegex(
                self.registry,
                rf"\| `{name}` \| {opcode} \|",
                f"request registry assignment drifted for {name}",
            )
            self.assertIn(f"`{name}`", section, f"error map omits {name}")

    def test_conformance_keeps_profile_dispatch_boundary_explicit(self):
        self.assertIn(
            "requests 41–47 with core X11 `BadRequest` before parsing presentation payloads or resolving their XIDs",
            self.conformance,
        )


if __name__ == "__main__":
    unittest.main()
