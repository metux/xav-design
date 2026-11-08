---
id: W0-20261108-118
kind: progress-checkpoint
from: owner-coordination
to: Defiant
created: 2026-11-08T19:30:00Z
in_reply_to: W0-117
task_ref: xaverius-exact-tip-build-repair-2026-11-08
correlation_id: defiant-meson-ci-fix-checkpoint-118
workspace: X11Libre/xserver@wip/xaverius
---

# W0-117 checkpoint — fix the exact-head Meson regression

The current branch remains at `27bbfe10efe752d5d503e42bdfdbdab215426e48`; exact-head Actions run `42426714335` is still failed. The previous review identified the concrete `xorg_inc` undefined-variable regression in `test/meson.build:268` under `-Dxorg=false`, and the test source duplicates `strcmp` rather than exercising the production comparator.

Please provide a brief checkpoint before further edits:
1. Current branch, HEAD, merge-base, and dirty status.
2. Whether you have corrected the Meson failure; if yes, exact commit SHA and changed paths.
3. How the comparator test now calls the production implementation, or confirmation that the synthetic test was removed.
4. Exact new Actions run ID and results for Ubuntu normal, no-GBM, Valgrind/`-Dxorg=false`, OpenBSD, macOS, and Solaris as available.
5. If not yet changed, state the immediate next action and blocker.

Continue only the narrow W0-117 repair. Exact-path commits, no destructive Git operations, no broad globs, and do not report CI green unless the exact-head run is green.
