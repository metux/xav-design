# W0-138 — Defiant progress trigger: current W0-117/W0-121 CI follow-up

**Existing work only:** this trigger references the current exact-tip follow-up in [W0-117](xaverius-ci-followup-2026-11-08-w0-117.md) and the latest checkpoint [W0-121](xaverius-exact-tip-ci-checkpoint-2026-11-08-w0-121.md). It does not create a new implementation task or supersede the normative spec.

## Verified current state

- Target: `X11Libre/xserver:wip/xaverius`
- Current remote HEAD: `7acb77642e6bcbd13bed6767a452072fd52d6c3b`, parent `27bbfe10efe752d5d503e42bdfdbdab215426e48`.
- Exact-head Actions run: [42427837938](https://github.com/X11Libre/xserver/actions/runs/42427837938), completed **failure**.
- The source diff from `27bbfe10` to `7acb7764` changes only `Xext/xaverius/registry.c` and `Xext/xaverius/xaverius_intern.h`; it does not change `test/meson.build` or `test/xaverius-registry-test.c`. The W0-117 regression therefore remains.
- Ubuntu normal/debug/no-GBM source-build jobs pass. Ubuntu Valgrind, OpenBSD, macOS and Solaris fail Meson configuration at `test/meson.build:268` with `Unknown variable name "xorg_inc"`. The test target references `xorg_inc` in configurations where `build_xorg=false` and that variable is not defined.
- FreeBSD fails linking `test/xaverius-registry-test` with unresolved Xserver/DDX symbols. The target links `libxserver_xaverius` and `libxserver` although its test source only uses standard C headers. The same test-target link failure was present in run `42426714335`. The FreeBSD log also shows a separate `libxorgserver.so` unresolved-symbol failure; run `42409419430` failed earlier during registry compilation, so that separate link failure has not yet been compared against a baseline and must not be labelled pre-existing without evidence.
- The test source still defines its own static `xaverius_compare_ordering_key()` as a wrapper around `strcmp`; it does not call the production comparator in `registry.c`. Its green result cannot validate production ordering. The unnecessary server-library link is also the direct source of the test target's FreeBSD unresolved-symbol failure.
- Other listed platform/driver jobs pass, but the workflow is not green. The SDK image job is not a separate SDK source-build result.

## Normative callback ABI — not settled at three arguments

The authoritative `spec/device-registry-architecture.md` still declares ABI-v1:

```c
XaveriusBackendResult (*query_physical_snapshot)(
    XaveriusDeviceBackendBinding *, XaveriusPhysicalDeviceSnapshot *);
```

That is **two typed arguments**, with no `snapshot_size` output argument. The same spec says ABI v1 covers every DDX callback signature and that an incompatible signature requires a new ABI version. The current implementation instead declares `query_physical_snapshot(void *, void *, uint64_t *)` in `xaverius_intern.h` and passes `&dev->snapshot_size` from `registry.c`. This is not the normative ABI-v1 contract. Do not treat the three-argument form as settled or silently change ABI v1. Align the implementation with the current two-argument typed contract; if you believe the normative contract must change, stop and request an explicit owner-authorized spec/ABI-version decision before changing it.

## Required next work

1. Before editing, report the observed branch, HEAD, merge-base and dirty status; preserve any pre-existing work.
2. Complete W0-117 on the same branch: fix the `xorg_inc` Meson configuration for `-Dxorg=false`; make the test call the actual production comparator through an appropriate minimal test seam, or remove the misleading synthetic test. Do not link the full Xserver libraries merely to test a local `strcmp` wrapper.
3. Reconcile the callback declaration, call site, snapshot representation and tests with the normative two-argument ABI-v1 contract. Do not add a third argument without an explicit spec/ABI-version change.
4. Attribute the FreeBSD failures precisely. Fix the test-target link regression; separately compare the `libxorgserver.so` failure with a valid baseline before calling it unrelated.
5. Commit only focused intended paths, then rerun Ubuntu normal/no-GBM/Valgrind and the affected OpenBSD/macOS/Solaris/FreeBSD configurations. Report exact run IDs, job conclusions and relevant log excerpts for the new exact branch tip.

The earlier missing-prototype/unused-local/comment diagnostics are cleared on the Ubuntu core source-build jobs; do not repeat that old repair or follow stale `79e59e48`-only instructions. Continue this existing follow-up until the current Meson/test/ABI issues are resolved. No reset, force-push, stash, broad staging, unrelated DDX/modesetting/protocol work, session restart, Ask approval, or destructive cleanup.
