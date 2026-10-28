#!/usr/bin/env python3
"""Fail if the working branch tip has no corresponding wire-layout Actions run."""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


API = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "metux/xav-design")
BRANCH = os.environ.get("CI_MONITOR_BRANCH", "docs/restructure-2026-10-21")
WORKFLOW = os.environ.get("CI_MONITOR_WORKFLOW", "wire-layout.yml")
GRACE_MINUTES = int(os.environ.get("CI_MONITOR_GRACE_MINUTES", "20"))


def api_get(path):
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GH_TOKEN or GITHUB_TOKEN is required")
    request = urllib.request.Request(
        API + path,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "xav-ci-run-presence-monitor",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def check_presence(now=None):
    now = now or datetime.now(timezone.utc)
    repo_path = urllib.parse.quote(REPOSITORY, safe="/")
    branch_path = urllib.parse.quote(BRANCH, safe="")
    branch = api_get(f"/repos/{repo_path}/branches/{branch_path}")
    head_sha = branch["commit"]["sha"]
    commit_time = parse_time(branch["commit"]["commit"]["committer"]["date"])
    age_minutes = (now - commit_time).total_seconds() / 60

    if age_minutes < GRACE_MINUTES:
        return 0, (
            f"CI run monitor: branch tip {head_sha[:12]} is only "
            f"{age_minutes:.1f} minutes old; waiting for the {GRACE_MINUTES}-minute grace period."
        )

    workflow_path = urllib.parse.quote(WORKFLOW, safe="")
    query = urllib.parse.urlencode({"branch": BRANCH, "per_page": 100})
    result = api_get(f"/repos/{repo_path}/actions/workflows/{workflow_path}/runs?{query}")
    runs = result.get("workflow_runs", [])
    matches = [run for run in runs if run.get("head_sha") == head_sha]

    if matches:
        latest = max(matches, key=lambda run: run.get("run_number", 0))
        status = latest.get("status", "unknown")
        conclusion = latest.get("conclusion") or "not completed"
        return 0, (
            f"CI run monitor: found wire-layout run {latest.get('html_url', '')} "
            f"for branch tip {head_sha[:12]} (status={status}, conclusion={conclusion})."
        )

    message = (
        f"Missing CI run: branch {BRANCH} tip {head_sha} is {age_minutes:.1f} minutes old, "
        f"but workflow {WORKFLOW} has no run for that exact commit. "
        "Check workflow triggers, Actions availability, and branch filters."
    )
    return 1, message


def main():
    try:
        code, message = check_presence()
    except (RuntimeError, KeyError, ValueError, urllib.error.URLError, TimeoutError) as error:
        print(f"CI run monitor: ERROR: {error}", file=sys.stderr)
        return 2
    stream = sys.stdout if code == 0 else sys.stderr
    print(message, file=stream)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
            summary.write(("## CI run monitor\n\n" if code == 0 else "## Missing CI run\n\n")
                          + message + "\n")
    if code:
        print(f"::error title=Missing GitHub Actions run::{message}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
