# W0-20261108-122 — 15-minute progress trigger

**Existing assignments:** W0-117 exact-tip CI correction and W0-121 checkpoint. This is a trigger/checkpoint only, not a new implementation task.
**Target:** `X11Libre/xserver:wip/xaverius`
**Last observed HEAD:** `7acb77642e6bcbd13bed6767a452072fd52d6c3b`
**Last exact-head CI:** run `42427837938`, conclusion `failure`.
**In reply to:** W0-121
**Correlation-ID:** `defiant-15m-trigger-122`

The existing checkpoint has been outstanding for more than 15 minutes without a newer verifiable source commit or checkpoint.

Please acknowledge receipt and send a concise status now:
1. Current branch, full HEAD, merge-base and dirty status.
2. Whether the `xorg_inc` Meson failure is fixed; if not, the exact next edit.
3. Whether the test now calls the production comparator or has been removed.
4. Exact-head CI run/result and FreeBSD baseline attribution, or the concrete blocker and next action.
5. Confirm the 3-argument `query_physical_snapshot` ABI against the normative spec, or identify the unresolved spec location.

Continue only the existing bounded repair. Preserve all work; no reset, force-push, stash, broad staging, unrelated changes, or session restart. Commit only focused changes and report exact evidence.
