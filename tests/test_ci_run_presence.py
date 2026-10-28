#!/usr/bin/env python3
"""Regression tests for missing GitHub Actions run detection."""
import importlib.util
import io
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_ci_run_presence", ROOT / "tools" / "check-ci-run-presence.py"
)
MONITOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MONITOR)

NOW = datetime(2026, 10, 28, 20, 0, tzinfo=timezone.utc)
HEAD = "a" * 40
BRANCH_RESPONSE = {
    "commit": {
        "sha": HEAD,
        "commit": {"committer": {"date": "2026-10-28T19:00:00Z"}},
    }
}


class MissingCiRunTests(unittest.TestCase):
    def test_recent_tip_gets_grace_period_before_reporting_missing_run(self):
        recent = {
            "commit": {
                "sha": HEAD,
                "commit": {"committer": {"date": "2026-10-28T19:50:00Z"}},
            }
        }
        with patch.object(MONITOR, "api_get", return_value=recent) as api:
            code, message = MONITOR.check_presence(now=NOW)
        self.assertEqual(code, 0)
        self.assertIn("waiting", message)
        api.assert_called_once()

    def test_exact_head_sha_run_counts_even_when_still_in_progress(self):
        with patch.object(MONITOR, "api_get", side_effect=[
            BRANCH_RESPONSE,
            {"workflow_runs": [{
                "head_sha": HEAD, "run_number": 17, "status": "in_progress",
                "conclusion": None, "html_url": "https://example.invalid/run/17",
            }]},
        ]):
            code, message = MONITOR.check_presence(now=NOW)
        self.assertEqual(code, 0)
        self.assertIn("found wire-layout run", message)
        self.assertIn("in_progress", message)

    def test_run_for_another_commit_does_not_hide_missing_tip_run(self):
        with patch.object(MONITOR, "api_get", side_effect=[
            BRANCH_RESPONSE,
            {"workflow_runs": [{
                "head_sha": "b" * 40, "run_number": 16, "status": "completed",
                "conclusion": "success", "html_url": "https://example.invalid/run/16",
            }]},
        ]):
            code, message = MONITOR.check_presence(now=NOW)
        self.assertEqual(code, 1)
        self.assertIn("Missing CI run", message)
        self.assertIn(HEAD, message)
        self.assertIn("wire-layout.yml", message)

    def test_api_errors_are_not_misreported_as_missing_runs(self):
        with patch.object(MONITOR, "api_get", side_effect=RuntimeError("API unavailable")):
            with self.assertRaisesRegex(RuntimeError, "API unavailable"):
                MONITOR.check_presence(now=NOW)


class VisibleAlertTests(unittest.TestCase):
    def test_missing_result_is_exported_for_workflow_notification_step(self):
        with tempfile.NamedTemporaryFile(mode="r+", encoding="utf-8") as output:
            with patch.dict(os.environ, {"GITHUB_OUTPUT": output.name}):
                with patch.object(MONITOR, "check_presence", return_value=(1, "Missing CI run: test")):
                    with patch("sys.stderr", new_callable=io.StringIO):
                        code = MONITOR.main()
            output.seek(0)
            self.assertEqual(code, 1)
            self.assertEqual(output.read(), "result=missing\n")

    def test_api_error_is_not_classified_as_missing_run(self):
        with tempfile.NamedTemporaryFile(mode="r+", encoding="utf-8") as output:
            with patch.dict(os.environ, {"GITHUB_OUTPUT": output.name}):
                with patch.object(MONITOR, "check_presence", side_effect=RuntimeError("API unavailable")):
                    with patch("sys.stderr", new_callable=io.StringIO):
                        code = MONITOR.main()
            output.seek(0)
            self.assertEqual(code, 2)
            self.assertEqual(output.read(), "result=error\n")

    def test_workflow_has_visible_issue_notification_and_required_permission(self):
        workflow = (ROOT / ".github" / "workflows" / "ci-run-monitor.yml").read_text(encoding="utf-8")
        self.assertIn("  issues: write", workflow)
        self.assertRegex(workflow, r"(?ms)^concurrency:\n  group: xav-ci-run-monitor\n  cancel-in-progress: false\n  queue: max\n.*?^jobs:")
        self.assertIn("if: steps.monitor.outputs.result == 'missing'", workflow)
        self.assertIn("bash tools/ensure-ci-alert-issue.sh", workflow)
        helper = (ROOT / "tools" / "ensure-ci-alert-issue.sh").read_text(encoding="utf-8")
        self.assertIn("gh issue create", helper)
        self.assertIn("gh issue list --state open --limit 1000 --json number,title", helper)
        self.assertIn("git/refs", helper)\n        self.assertIn("git/ref/heads/xav-ci-alert-issue-lock", helper)\n        self.assertIn("method DELETE", helper)
        self.assertIn("continue-on-error: true", workflow)
        self.assertIn("Fail visibly if the monitor itself could not complete", workflow)
        self.assertIn("outputs.result", workflow)


class AlertIssueDeduplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.gh = self.root / "gh"
        self.created_marker = self.root / "created"
        self.remote_lock = self.root / "remote-lock"
        self.gh.write_text(
            '#!/usr/bin/env bash\\n'
            'set -eu\\n'
            'if [ "$1" = "api" ]; then\\n'
            '  shift\\n'
            '  case "$*" in\\n'
            '    *"--method POST"*"git/refs"*)\\n'
            '      if mkdir "$REMOTE_LOCK_DIR" 2>/dev/null; then printf \'{"ref":"refs/heads/xav-ci-alert-issue-lock"}\\n\'; else exit 1; fi ;;\\n'
            '    *"--method DELETE"*"git/ref/heads/xav-ci-alert-issue-lock"*) rmdir "$REMOTE_LOCK_DIR"; printf "{}\\n" ;;\\n'
            '    *"git/ref/heads/docs/restructure-2026-10-21"*) printf \'{"object":{"sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}\\n\' ;;\\n'
            '    *"git/ref/heads/xav-ci-alert-issue-lock"*) [ -d "$REMOTE_LOCK_DIR" ] && printf \'{"ref":"refs/heads/xav-ci-alert-issue-lock"}\\n\' || exit 1 ;;\\n'
            '    *) exit 91 ;;\\n'
            '  esac\\n'
            'elif [ "$1 $2" = "issue list" ]; then\\n'
            '  if [ -f "$CREATED_MARKER" ]; then\\n'
            '    printf \'%s\' \'[{"number":123,"title":"[CI monitor] Missing wire-layout run on docs/restructure-2026-10-21"}]\'\\n'
            '  else printf "%s" "$MOCK_ISSUES"; fi\\n'
            'elif [ "$1 $2" = "issue create" ]; then\\n'
            '  sleep "${MOCK_CREATE_DELAY:-0}"\\n'
            '  printf created > "$CREATED_MARKER"\\n'
            '  printf "%s\\\\n" "https://github.com/metux/xav-design/issues/123"\\n'
            'else exit 90; fi\\n',
            encoding="utf-8",
        )
        self.gh.chmod(0o755)
        self.env = os.environ.copy()
        self.env.update({
            "PATH": f"{self.root}:{self.env.get('PATH', '')}",
            "GH_REPO": "metux/xav-design",
            "RUN_URL": "https://github.com/metux/xav-design/actions/runs/1",
            "CREATED_MARKER": str(self.created_marker),
        })

    def run_helper(self, issues):
        import json
        self.env["MOCK_ISSUES"] = json.dumps(issues)
        return subprocess.run(
            ["bash", str(ROOT / "tools" / "ensure-ci-alert-issue.sh")],
            env=self.env, text=True, capture_output=True, check=False,
        )


    def test_workflow_serializes_parallel_monitor_runs_before_issue_check(self):
        workflow = (ROOT / ".github" / "workflows" / "ci-run-monitor.yml").read_text(encoding="utf-8")
        concurrency = workflow.split("jobs:", 1)[0]
        self.assertIn("concurrency:", concurrency)
        self.assertIn("group: xav-ci-run-monitor", concurrency)
        self.assertIn("cancel-in-progress: false", concurrency)
        self.assertIn("queue: max", concurrency)
        self.assertLess(concurrency.index("concurrency:"), workflow.index("jobs:"))

    def test_existing_exact_title_open_issue_prevents_duplicate(self):
        title = "[CI monitor] Missing wire-layout run on docs/restructure-2026-10-21"
        result = self.run_helper([{"number": 42, "title": title}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Existing alert issue #42 remains open", result.stdout)
        self.assertFalse(self.created_marker.exists())

    def test_similar_but_different_title_does_not_hide_missing_alert(self):
        result = self.run_helper([
            {"number": 41, "title": "[CI monitor] Missing wire-layout run"},
            {"number": 42, "title": "[CI monitor] Missing wire-layout run on docs/restructure-2026-10-21 (resolved)"},
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Created alert issue:", result.stdout)
        self.assertTrue(self.created_marker.exists())

    def test_empty_open_issue_list_creates_alert(self):
        result = self.run_helper([])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.created_marker.exists())

    def test_parallel_helper_invocations_create_only_one_alert(self):
        import json
        self.env["MOCK_ISSUES"] = json.dumps([])
        self.env["MOCK_CREATE_DELAY"] = "0.2"
        command = ["bash", str(ROOT / "tools" / "ensure-ci-alert-issue.sh")]
        first = subprocess.Popen(command, env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        second = subprocess.Popen(command, env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        first_out, first_err = first.communicate(timeout=10)
        second_out, second_err = second.communicate(timeout=10)
        self.assertEqual(first.returncode, 0, first_err)
        self.assertEqual(second.returncode, 0, second_err)
        combined = first_out + second_out
        self.assertEqual(combined.count("Created alert issue:"), 1, combined)
        self.assertEqual(combined.count("Existing alert issue #123 remains open"), 1, combined)\n        self.assertFalse(self.remote_lock.exists(), "distributed lock must be released")

if __name__ == "__main__":
    unittest.main()
