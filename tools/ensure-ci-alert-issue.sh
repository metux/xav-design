#!/usr/bin/env bash
# Create one open issue for a missing CI run, reusing an existing exact-title alert.
set -euo pipefail

title="[CI monitor] Missing wire-layout run on docs/restructure-2026-10-21"
: "${GH_REPO:?GH_REPO must identify owner/repository}"
: "${RUN_URL:?RUN_URL must identify the monitor run}"

# flock handles same-host invocations. A fixed Git ref provides a distributed
# compare-and-create lock: GitHub accepts only one POST that creates this ref.
lock_ref="refs/heads/xav-ci-alert-issue-lock"
lock_api_ref="heads/xav-ci-alert-issue-lock"
lock_acquired=0
lock_attempt=0
head_sha="$(gh api "repos/$GH_REPO/git/ref/heads/docs/restructure-2026-10-21" --jq '.object.sha')"
while (( lock_attempt < 60 )); do
  if gh api --method POST "repos/$GH_REPO/git/refs" -f "ref=$lock_ref" -f "sha=$head_sha" >/dev/null 2>&1; then
    lock_acquired=1
    break
  fi
  # Retry only when another invocation owns the ref; surface auth/API errors.
  if ! gh api "repos/$GH_REPO/git/ref/$lock_api_ref" >/dev/null 2>&1; then
    echo "Unable to acquire CI alert lock through GitHub API" >&2
    exit 1
  fi
  sleep 2
  lock_attempt=$((lock_attempt + 1))
done
if (( lock_acquired == 0 )); then
  echo "Timed out waiting for CI alert lock; inspect and remove stale ref $lock_ref if no helper is running" >&2
  exit 1
fi
release_lock() {
  gh api --method DELETE "repos/$GH_REPO/git/ref/$lock_api_ref" >/dev/null 2>&1 || {
    echo "Warning: could not release CI alert lock ref $lock_ref" >&2
  }
}
trap release_lock EXIT

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
