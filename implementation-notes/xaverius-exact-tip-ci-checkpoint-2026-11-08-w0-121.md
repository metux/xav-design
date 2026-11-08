# W0-121 — Exact-tip CI checkpoint after Defiant commit

**Existing assignments:** exact-tip build repair and W0-117 CI regression follow-up. This is a checkpoint/correction, not a new implementation stream.
**Implementation branch:** `X11Libre/xserver:wip/xaverius`
**New observed HEAD:** `7acb77642e6bcbd13bed6767a452072fd52d6c3b` (parent `27bbfe10efe752d5d503e42bdfdbdab215426e48`).
**Exact-head Actions run:** [42427837938](https://github.com/X11Libre/xserver/actions/runs/42427837938), conclusion **failure**.

The new commit changes only the `query_physical_snapshot` callback ABI from two arguments to three and passes `&dev->snapshot_size`. That addresses the snapshot-size callback mismatch noted in the prior audit, but it does not modify `test/meson.build` or `test/xaverius-registry-test.c`; the W0-117 Meson/test-coverage correction remains outstanding.

Exact run 42427837938:
- Passed: Ubuntu normal, Ubuntu debug, Ubuntu no-GBM, Cygwin, MinGW, NetBSD, DragonFlyBSD, RHEL 9/10, Alpine, Gentoo, Arch, Hurd, SDK image and listed Ubuntu driver jobs.
- Failed: Ubuntu Valgrind, OpenBSD, FreeBSD, macOS, Solaris.
- Valgrind, OpenBSD, macOS and Solaris still fail Meson configuration at `test/meson.build:268` with `Unknown variable name "xorg_inc"` (OpenBSD/macOS/Solaris explicitly show the same error; Valgrind log also reaches it).
- FreeBSD gets past Meson and fails later while linking `libxorgserver.so` with unresolved Xserver/DDX symbols (e.g. `SetDeviceValuators`, `XkbDDXTerminateServer`, `XkbDDXSwitchScreen`, `InitOutput`). This is distinct from the W0-117 `xorg_inc` regression and needs baseline comparison before attribution.
- The exact-head workflow is not green. Passing Ubuntu core jobs do show the earlier source compile blockers are cleared in those configurations.

Please continue the existing W0-117 correction on this same branch:
1. Fix the `xorg_inc` reference for `-Dxorg=false` and all affected configurations.
2. Make the test exercise the production comparator, or remove the misleading synthetic test; do not claim coverage from a local `strcmp` duplicate.
3. Re-run the affected configurations and report exact-head CI results, including the FreeBSD failure's baseline/regression attribution.
4. Separately confirm whether the callback signature change matches the current normative backend ABI and update all affected declarations/call sites/tests consistently.

Before further edits, report branch, HEAD, merge-base and dirty status. Preserve existing work and use focused commits. No reset, force-push, stash, broad staging, unrelated lifecycle/DDX/modesetting/protocol work, or session restart.