#!/usr/bin/env python3
"""Regression tests for required GitHub Actions triggers and check coverage."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "wire-layout.yml"

REQUIRED_CHECKS = {
    "checkout": "actions/checkout@",
    "setup_python": 'python-version: "3.12"',
    "shell_syntax": "sh -n tools/find-xav-backend.sh tests/test_find_xav_backend.sh",
    "backend_tests": "sh tests/test_find_xav_backend.sh",
    "handler_signatures": "python tests/test_handler_signatures.py",
    "handler_gate": "python tools/check-handler-ci-gate.py .",
    "handler_gate_tests": "python tests/test_handler_ci_gate.py",
    "py_compile": "python -m py_compile",
    "wire_layout": "python tools/check-wire-layout.py",
    "timeline": "python tests/run_timeline_regressions.py",
    "python_suite": "python -m unittest discover -s tests -p 'test_*.py' -v",
}

class RequiredCiWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_has_push_pr_and_manual_triggers(self):
        self.assertRegex(self.text, r"(?m)^on:\s*$")
        self.assertIn("  push:", self.text)
        self.assertIn("      - docs/restructure-2026-10-21", self.text)
        self.assertIn("  pull_request:", self.text)
        self.assertIn("  workflow_dispatch:", self.text)

    def test_every_required_check_has_a_stable_id_and_expected_command(self):
        for check_id, command in REQUIRED_CHECKS.items():
            with self.subTest(check=check_id):
                self.assertRegex(self.text, rf"(?m)^        id: {re.escape(check_id)}$")
                self.assertIn(command, self.text)
                block = self._step_block(check_id)
                self.assertNotRegex(block, r"(?m)^        continue-on-error:\s*true\s*$")
                self.assertNotRegex(block, r"(?m)^        if:\s*(?:false|0)\s*$")

    def test_final_audit_runs_even_after_failure_and_checks_every_outcome(self):
        block = self._step_block("required_check_audit")
        self.assertRegex(block, r"(?m)^        if: always\(\)$")
        for check_id in REQUIRED_CHECKS:
            self.assertIn(f"steps.{check_id}.outcome", block)
        self.assertIn('if [ "$outcome" != success ]', block)
        self.assertIn('exit "$failed"', block)

    def _step_block(self, step_id):
        lines = self.text.splitlines()
        start = next((i for i, line in enumerate(lines)
                      if line == "        id: " + step_id), None)
        self.assertIsNotNone(start, f"missing workflow step {step_id}")
        while start > 0 and not lines[start].startswith("      - name: "):
            start -= 1
        end = start + 1
        while end < len(lines) and not lines[end].startswith("      - name: "):
            end += 1
        return "\n".join(lines[start:end])

if __name__ == "__main__":
    unittest.main()
