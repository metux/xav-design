#!/usr/bin/env bash
# Create one open issue for a missing CI run, reusing an existing exact-title alert.
set -euo pipefail

title="[CI monitor] Missing wire-layout run on docs/restructure-2026-10-21"
: "${GH_REPO:?GH_REPO must identify owner/repository}"
: "${RUN_URL:?RUN_URL must identify the monitor run}"

# Workflow-level concurrency covers separate GitHub-hosted runners. flock also
# serializes direct/duplicate invocations sharing this runner, closing the
# check-then-create race between processes on the same host.
lock_key="$(printf '%s' "$GH_REPO" | sha256sum | cut -d ' ' -f 1)"
exec 9>"/tmp/xav-ci-alert-${lock_key}.lock"
flock -x 9

export ALERT_TITLE="$title"
existing="$(
  gh issue list --state open --limit 1000 --json number,title |
    python3 -c 'import json, os, sys; title = os.environ["ALERT_TITLE"]; print(next((str(issue["number"]) for issue in json.load(sys.stdin) if issue.get("title") == title), ""))'
)"

if [[ -n "$existing" ]]; then
  echo "Existing alert issue #$existing remains open: $GH_REPO/issues/$existing"
  exit 0
fi

body="$(printf 'The CI monitor found that branch tip docs/restructure-2026-10-21 has no matching push-triggered run of wire-layout.yml after the 20-minute grace period.\n\nMonitor run: %s\n\nCheck workflow triggers, branch filters, and GitHub Actions availability.' "$RUN_URL")"
created_url="$(gh issue create --title "$title" --body "$body")"
echo "Created alert issue: $created_url"
