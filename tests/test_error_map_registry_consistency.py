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

    def test_request_and_error_registries_are_complete_and_referenced(self):
        table = self.registry.split("| Request | Subopcode | Kind | Responsibility |", 1)[1].split(
            "## Allocation policy", 1
        )[0]
        rows = re.findall(
            r"^\| `([^`]+)` \| (\d+) \| (Void(?: \+ async events)?|Reply) \| (.*?) \|$",
            table,
            re.M,
        )
        self.assertEqual(len(rows), 47, "every assigned request must have one registry row")
        names = [name for name, _value, _kind, _details in rows]
        values = [int(value) for _name, value, _kind, _details in rows]
        self.assertEqual(len(names), len(set(names)), "request names must be unique")
        self.assertEqual(values, list(range(1, 48)), "request subopcodes must be unique and append-only")

        for name, _value, kind, details in rows:
            chapters = re.findall(r"\]\(\.\./spec/([^)]+)\)", details)
            self.assertTrue(chapters, f"{name} must point to its normative chapter")
            found = False
            for chapter in chapters:
                document = (ROOT / "spec" / chapter).read_text(encoding="utf-8")
                if f"`{name}`" in document:
                    found = True
                    if kind == "Reply":
                        self.assertRegex(document, r"(?i)reply")
                    break
            self.assertTrue(found, f"{name} is absent from every normative chapter linked by its registry row")

        error_rows = re.findall(
            r"^\|\s*(\d+)\s*\|\s*`([A-Z_]+)`\s*\|$",
            (ROOT / "registries" / "errors.md").read_text(encoding="utf-8"),
            re.M,
        )
        self.assertEqual([int(value) for value, _symbol in error_rows], list(range(9)))
        error_names = [symbol for _value, symbol in error_rows]
        self.assertEqual(len(error_names), len(set(error_names)))
        for symbol in error_names:
            with self.subTest(error=symbol):
                self.assertIn(f"`{symbol}`", self.errors)

    def test_conformance_keeps_profile_dispatch_boundary_explicit(self):
        self.assertIn(
            "requests 41–47 with core X11 `BadRequest` before parsing presentation payloads or resolving their XIDs",
            self.conformance,
        )


if __name__ == "__main__":
    unittest.main()
