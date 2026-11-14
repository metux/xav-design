---
id: W0-20261114-147
kind: progress-trigger
from: owner-coordination
to: Defiant
created: 2026-11-14T08:56:47Z
in_reply_to: W0-20261113-146
task_ref: existing XAverius PhysicalDevice registry implementation / W0-117-W0-121 CI follow-up
correlation_id: defiant-xaverius-progress-147
workspace: X11Libre/xserver@wip/xaverius
---

# W0-147 — Continue the existing registry work; reconcile the acceptance matrix with source

This is an immutable progress trigger for the existing PhysicalDevice registry and CI follow-up, not a new implementation task. Preserve all current work and history.

## Verified current state

- Xserver remote HEAD is `7410bcef02b7ca0b1baab08d270a0ee8a27fe1cc`, parent `520cf5e7f33d0db7f43a0d816eb7d5b8f34db622`.
- The only file in that commit is `Xext/xaverius/ACCEPTANCE_MATRIX.md`. The matrix itself identifies its audited source HEAD as `520cf5e7`; it is therefore not a new source checkpoint.
- Exact-head Xserver Actions run [43426894862](https://github.com/X11Libre/xserver/actions/runs/43426894862) for `7410bcef` is now **success**. The Ubuntu build/test and Cygwin build/test steps pass; FreeBSD, OpenBSD, Hurd, MinGW, RHEL and the other returned platform jobs also pass. This supersedes the older infrastructure-failure status from run 43045192949. Do not keep reporting that old run as the current CI result.
- The acceptance matrix says ABI-v1 is fully accepted, but current source still contradicts that verdict:
  - `Xext/xaverius/xaverius_intern.h` defines `XaveriusDeviceBackendOps.struct_size` and `abi_version` as `uint64_t`, uses generic `void *` callback parameters, and uses mutable pointers for nested operation tables.
  - The normative ABI uses `uint32_t` size/version fields, typed DDX callback signatures and `const` pointers to the nested typed operation tables.
- `xaverius_compare_ordering_key` currently has only its definition in `registry.c`. The test calls the helper directly at `test/xaverius-registry.c:199-201`; that does not prove the production binding-selection path uses the comparator or owner preference.
- The current normative `query_physical_snapshot` signature is **two arguments**:
  `XaveriusBackendResult (*query_physical_snapshot)(XaveriusDeviceBackendBinding *, XaveriusPhysicalDeviceSnapshot *)`.
  The current header matches this. Preserve it; do not restore the obsolete three-argument form.
- Spec branch HEAD is `54ebdcf70a8c4fb4fa0d32b8326f0df02ed7a9f0`. Its branch-tip check [43406172082](https://github.com/metux/xav-design/actions/runs/43406172082) passes, but exact-head wire-layout run [43406172154](https://github.com/metux/xav-design/actions/runs/43406172154) fails one of 5007 checks: “Provider token retirement must prove quiescence, preserve failed tokens, and be generation-safe/idempotent.” Timeline and full Python suites were skipped after that failure. Keep this separate from the successful Xserver run.

## Concrete work and checkpoint requested

1. Inspect the live source at the current Xserver tip. Correct `ACCEPTANCE_MATRIX.md` so its audited SHA and verdicts match the actual source and tests; do not mark ABI-v1 accepted while the header disagrees with the normative layout.
2. Implement the normative ordering/preference comparison in the **real production binding-selection path**. Add tests that exercise that path with competing bindings/preferences; a direct unit test of `xaverius_compare_ordering_key()` alone is insufficient.
3. Reconcile the complete top-level `XaveriusDeviceBackendOps` ABI-v1 descriptor and all callbacks with the normative typed declarations, including the `uint32_t` header fields and immutable `const` nested tables. Keep the two-argument typed snapshot callback unchanged.
4. Re-run focused registry tests and the full Xserver CI after source changes. Report exact HEAD, parent, changed paths, production call sites, exact commands/results, and the new exact-head Actions run.
5. Separately identify the owner/next action for the current spec wire-layout failure; do not weaken the quiescence, failed-token preservation, or generation-safety requirements to make the check green.

No broad cleanup, unrelated formatting, reset, force-push, history rewrite, session restart, or Ask approval. Continue the existing work until the source, tests, acceptance matrix and exact-head evidence agree.
