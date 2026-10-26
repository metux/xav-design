#!/usr/bin/env python3
"""Run only the Timeline semaphore regression tests with Python's stdlib.

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
    case = test_state_model.QueueSubmitAtomicityTests
    names = sorted(
        name for name in unittest.defaultTestLoader.getTestCaseNames(case)
        if "timeline" in name.lower()
    )
    if not names:
        print("No Timeline regression tests found in QueueSubmitAtomicityTests.", file=sys.stderr)
        return 2

    suite = unittest.TestSuite(case(name) for name in names)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
