# Defiant progress trigger — 2026-11-13 (W0-146)

This is an immutable progress trigger for the existing XAverius registry implementation and W0-117/W0-121 CI follow-up. It is not a replacement task or a new implementation assignment.

## Authoritative state at this inspection

- Xserver branch: `X11Libre/xserver:wip/xaverius@520cf5e7f33d0db7f43a0d816eb7d5b8f34db622`. No newer Xserver source commit has appeared since W0-145.
- Spec branch before this trigger: `metux/xav-design:docs/restructure-2026-10-21@fc75b98287c69117715b749167a26695c7d3665d`.
- Exact-head Xserver run [43045192949](https://github.com/X11Libre/xserver/actions/runs/43045192949) targets the current Xserver SHA and is overall **failure**. Six jobs (Ubuntu normal, no-GBM, debug, Valgrind, MinGW-on-Ubuntu, and Hurd) fail while installing packages because `security.ubuntu.com` cannot be resolved. The source build is not reached in those jobs. Cygwin, FreeBSD, OpenBSD and the other completed platform/source jobs pass.
- The previous run-42427837938 Meson `xorg_inc` configuration failure and FreeBSD synthetic-target link failure are no longer reproduced: the registry test is integrated into `test/tests`, and `xorg_inc` is only added inside `if build_xorg`.
- Spec branch-tip check [43405496053](https://github.com/metux/xav-design/actions/runs/43405496053) passes for `fc75b982`. Exact-head wire-layout run [43405495899](https://github.com/metux/xav-design/actions/runs/43405495899) is still in progress at this inspection.

## Concrete remaining work

1. **Production ordering is still unproven.** In current `Xext/xaverius/registry.c`, `xaverius_compare_ordering_key()` is defined around line 598 but has no production call site. Registration calls `xaverius_create_ordering_key()` around line 737; it does not compare keys or select a DDX binding using the normative configured owner-key preference. The integrated test `test/xaverius-registry.c:xaverius_ordering_key()` directly calls the helper at lines 199–201, which tests the helper but not actual registry selection. Trace the real registration/selection path, implement the normative deterministic selection if required, and add a test that drives the real registry behavior. If no production comparison path is intended, justify that against the normative spec and remove misleading production-comparator coverage claims.

2. **Top-level backend ABI v1 remains incompatible.** Current `Xext/xaverius/xaverius_intern.h:XaveriusDeviceBackendOps` (around lines 221–257) still uses `uint64_t` for `struct_size` and `abi_version`, generic `void *` callback parameters/results for most operations, and mutable nested operation-table pointers. Normative `spec/device-registry-architecture.md` lines 694–761 requires `uint32_t` size/version fields, typed callback signatures, and const nested operation-table pointers. Reconcile the descriptor and all nested tables with ABI v1. Keep the already-correct typed two-argument `query_physical_snapshot(XaveriusDeviceBackendBinding *, XaveriusPhysicalDeviceSnapshot *)`; do not restore the former three-argument form. Do not regress the already typed ModuleRole and registration descriptors.

3. **Obtain current exact-head CI evidence.** The six package-install failures in run 43045192949 are infrastructure/DNS failures, not demonstrated source failures, but the workflow is not green. Re-run the exact Xserver tip when package resolution is available, or provide a new exact-head run that completes the source-build jobs. Check the current spec wire-layout run 43405495899 before claiming the spec validator is green.

## Required checkpoint

Continue the existing implementation until these items are resolved. Return the exact branch/HEAD, merge-base if relevant, changed paths, source-level explanation of the production selection path, ABI-v1 conformance result, focused test commands and complete output, exact-head CI links/results, and remaining blockers. Do not stop after acknowledgement, a plan, a helper-only test, or a commit message. Preserve existing work and histories; do not reset, force-push, stash, overwrite, or stage broad globs.
