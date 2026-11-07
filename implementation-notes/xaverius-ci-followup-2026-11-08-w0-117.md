# W0-117 — Exact-head CI regression follow-up

**Existing assignment:** `implementation-notes/xaverius-exact-tip-build-repair-2026-11-08.md`  
**Implementation branch:** `X11Libre/xserver:wip/xaverius`  
**Observed HEAD:** `27bbfe10efe752d5d503e42bdfdbdab215426e48` (parent `79e59e48b903655586e50bd93617dede382e6aa6`)

The registry compile repair is a useful step: the exact-head Actions run `42426714335` shows `xserver-build-ubuntu`, `xserver-build-ubuntu-debug`, and `xserver-build-ubuntu-no-gbm` passing. However, the overall run failed, and log inspection identifies a regression introduced by the new `test/meson.build` entry:

- Ubuntu Valgrind (configured with `-Dxorg=false`), OpenBSD, macOS, and Solaris fail during Meson configuration at `test/meson.build:268`: `Unknown variable name "xorg_inc"`.
- This is not an unrelated platform/toolchain failure: the new test target references `xorg_inc` in a configuration where that variable is not defined.
- The added `test/xaverius-registry-test.c` currently reimplements the comparator as a local wrapper around `strcmp`; it does not call the production `xaverius_compare_ordering_key`. Consequently, its green test result would not catch a regression in the implementation it claims to test.
- The new target also links `libxserver_xaverius` and `libxserver` despite the test source not including or calling production symbols.

Please make one focused follow-up on the same branch:

1. Fix the Meson regression so configurations with `-Dxorg=false` work. Use only include variables that are defined in all relevant configurations; the test source currently uses only standard C headers.
2. Ensure the test actually exercises the production comparator. If the current target cannot do that cleanly, remove the synthetic duplicate test rather than presenting a local `strcmp` wrapper as coverage.
3. Run at least the Ubuntu normal, Ubuntu no-GBM, Ubuntu Valgrind/`-Dxorg=false`, and relevant non-Xorg Meson configurations (OpenBSD/macOS/Solaris CI where available). Report exact run IDs and job results.
4. Keep the registry repair narrow. Do not mix unrelated Xaverius lifecycle, DDX, modesetting, or protocol work into this correction.

Before editing, report branch, HEAD, merge-base, and dirty status. Commit only exact intended paths; report full SHA, parent, test/build commands, and results. No reset, force-push, stash, broad globs, or discarded work. This follow-up refines the existing exact-tip build-repair task; it is not a new implementation stream.
