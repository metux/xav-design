# Defiant progress trigger — 2026-11-13 (W0-145)

This continues the existing XAverius registry implementation and W0-117/W0-121 CI follow-up. It is a progress trigger, not a new implementation task.

## Authoritative refs checked

- Xserver: `X11Libre/xserver:wip/xaverius` at `520cf5e7f33d0db7f43a0d816eb7d5b8f34db622`.
- Spec: `metux/xav-design:docs/restructure-2026-10-21` at `201fb06c1c0df1b3815d79b8fe812d5b156cb439`.
- The 2026-11-11 owner-verification note records the older Xserver tip `18499fad39d2084e2a1f14a846200432f978649d`; it is stale for the current source tip.

## Verified corrections to the old run 42427837938

The old Meson and FreeBSD failures are no longer reproduced in the current source/CI:

- `test/meson.build` now adds `xaverius-registry.c` to the existing `test/tests` executable when `get_option('xaverius')` is enabled. `xorg_inc` is added only inside `if build_xorg`; the old standalone target is gone.
- `test/tests.c` registers `xaverius_registry_test` under `XAVERIUS_TESTS`. The new source exercises real registry registration/lifecycle functions and calls the production helper functions; the former `test/xaverius-registry-test.c` was removed.
- Exact-head run [43045192949](https://github.com/X11Libre/xserver/actions/runs/43045192949) has successful Cygwin build/test, FreeBSD, and OpenBSD jobs. Thus the former FreeBSD synthetic-target link failure is not present on this tip.
- `query_physical_snapshot` is the typed two-argument callback `(XaveriusDeviceBackendBinding *, XaveriusPhysicalDeviceSnapshot *)` in both current source and normative ABI v1. Do not restore or treat the old three-argument callback as ABI v1.

## Concrete remaining work

1. **Exercise the actual production ordering path.** `registry.c` defines `xaverius_compare_ordering_key()` (around line 598), and the test directly tests that helper. However, no production call site uses it in the current `registry.c`; registration calls `xaverius_create_ordering_key()` to store a key, but does not compare keys. Therefore the test still does not prove that the registry's actual ordering/selection behavior uses the comparator. Search the whole current branch, identify the real production ordering path, wire the normative comparator into it if required, and add a test that drives the real registry behavior. If there is intentionally no production comparison path, explain that against the normative spec and remove misleading comparator-coverage claims.

2. **Finish top-level backend ABI-v1 conformance.** Current `XaveriusDeviceBackendOps` in `Xext/xaverius/xaverius_intern.h` still uses `uint64_t` for `struct_size` and `abi_version`; the normative descriptor uses `uint32_t`. Many callbacks still use generic `void *` parameters/results, and nested operation-table pointers are mutable; ABI v1 specifies typed callback signatures and const nested operation-table pointers. The ModuleRole and registration descriptors are already typed; do not regress them. Keep the two-argument typed snapshot callback.

3. **Resolve exact-head CI honestly.** Run 43045192949 targets exactly `520cf5e7...` and ends in failure because five Ubuntu jobs cannot resolve/fetch packages from Ubuntu repositories and the Hurd job cannot install QEMU. The Cygwin, FreeBSD, OpenBSD, and other completed source jobs pass. This is not evidence of a source failure in those six jobs, but the overall exact-head workflow is not green. Obtain a fresh exact-head source-build run when infrastructure is available; do not claim full CI success from the partial green job set.

4. **Track the separate Spec validator failure accurately.** Spec run [42985291808](https://github.com/metux/xav-design/actions/runs/42985291808) on `201fb06c...` fails one of 5005 wire-layout checks: “Provider token retirement must prove quiescence, preserve failed tokens, and be generation-safe/idempotent.” Timeline and Python suites are skipped after that failure. The separate branch-tip check [42985291847](https://github.com/metux/xav-design/actions/runs/42985291847) succeeds. Diagnose/coordinate this exact failure without misattributing it to the Xserver source build.

## Required checkpoint

Continue the existing work; do not create a replacement task. Report the exact current Xserver/spec SHAs, parent and merge-base/ancestry facts, changed paths, the actual production ordering call path, the ABI-v1 header diff, and focused test results. Include exact-head CI links and distinguish source failures from infrastructure failures. Do not infer local working-tree state from GitHub commits. Preserve all histories and work: no reset, force-push, stash, overwrite, or broad staging. Keep changes narrow and continue until the production behavior, ABI, and exact-head evidence are demonstrated.
