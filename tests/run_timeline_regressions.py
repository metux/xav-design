#!/usr/bin/env python3
"""Run Timeline semaphore regressions with Python's stdlib.

Invoke from any working directory:
    python3 tests/run_timeline_regressions.py
No third-party packages or X server are required.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))

import test_state_model  # noqa: E402


def main() -> int:
    loader = unittest.defaultTestLoader

    # Keep the timeline-specific QueueSubmit precedence/atomicity tests that
    # live alongside the broader state-model tests.
    case = test_state_model.QueueSubmitAtomicityTests
    names = sorted(
        name for name in loader.getTestCaseNames(case)
        if "timeline" in name.lower()
    )
    model_suite = unittest.TestSuite(case(name) for name in names)

    # Also run the dedicated timeline suites. Restricting this runner to the
    # QueueSubmit class silently skipped host-wait, signal-lifecycle, and
    # cross-model race regressions despite their test_timeline_* filenames.
    timeline_suite = loader.discover(
        start_dir=str(TESTS_DIR),
        pattern="test_timeline_*.py",
        top_level_dir=str(TESTS_DIR),
    )
    suite = unittest.TestSuite((model_suite, timeline_suite))
    if suite.countTestCases() == 0:
        print("No Timeline regression tests found.", file=sys.stderr)
        return 2

    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
