---
id: W0-20261118-153
kind: progress-trigger
from: owner-coordination
to: Defiant
created: 2026-11-18T08:04:00Z
in_reply_to: W0-20261117-152
task_ref: existing XAverius PhysicalDevice registry implementation / W0-149-W0-152 follow-up
correlation_id: defiant-xaverius-progress-153
workspace: X11Libre/xserver@wip/xaverius
---

# W0-153 — Repair the exact-tip registration failure, then finish the real selection path

This continues the existing PhysicalDevice registry assignment and W0-149 through W0-152. It is not a new implementation task. Continue in the existing Defiant session only. Do not restart, detach, replace, duplicate, or approve any session or Ask.

## Current verified remote evidence

- Authoritative Xserver branch: `wip/xaverius`.
- Exact remote HEAD: `2177a0779b582820624b80947f4e63231df29578`; parent: `e9e7fce0b96f55bb508fa8548d325fd1b4009ac4`.
- The latest commit changes only `Xext/xaverius/ACCEPTANCE_MATRIX.md`; there has been no newer source-bearing commit after `e9e7fce0`.
- Exact-head Actions run [43901444033](https://github.com/X11Libre/xserver/actions/runs/43901444033) fails six platform jobs: MinGW32, DragonFly BSD, NetBSD, Solaris, RHEL 9 and RHEL 10. The MinGW32 and DragonFly logs identify `Xext/xaverius/registry.c:720:8`: `dev may be used uninitialized [-Werror=maybe-uninitialized]`. FreeBSD passes in this run. This is not the earlier FreeBSD link failure or the old Meson `xorg_inc` regression.
- The source declares `dev` without initialization, sets it only in the `existing != NULL && existing->binding == NULL` path, then tests `if (dev != existing)`. For a genuinely new identity (`existing == NULL`), that comparison reads an uninitialized pointer.
- The re-registration path mutates the existing record (`caller_refcount`, `device_generation`, `binding`) before calling `query_physical_snapshot`. On callback or snapshot-validation failure it frees the provisional binding but does not restore the previous record; the existing device can retain a dangling `dev->binding` and partially changed generation/refcount/snapshot state.
- `xaverius_compare_ordering_key` is still only defined in `registry.c`; there is no production call site. `test/xaverius-registry.c` only compares synthetic keys created directly by the helper. Registration still does not select a complete binding through a configured `ddx_binding_preference_owner_keys` policy.
- The current `XaveriusDeviceBackendOps` header remains non-conformant to ABI v1: 64-bit `struct_size`/`abi_version`, generic callback signatures, and mutable nested operation-table pointers.
- The normative `query_physical_snapshot` callback remains exactly the two-argument typed form in [device-registry-architecture.md lines 698–699](https://github.com/metux/xav-design/blob/docs/restructure-2026-10-21/spec/device-registry-architecture.md#L698-L699). Preserve it; do not reintroduce a three-argument variant.

## Required continuation, in order

1. Send `task_progress` from the existing session with observed session/turn identity, worktree, branch, local HEAD, origin HEAD and dirty state. Report only what is actually observable; do not infer process liveness from Git.
2. Fix the uninitialized new-device path narrowly and add a real new-device registration test. Prefer explicit `existing == NULL` branching over comparing an uninitialized `dev`.
3. Make re-registration failure-atomic. Build/query/validate the provisional binding and snapshot without mutating the published record; only install it after every step succeeds, or fully restore the prior binding, generation, refcount and snapshot on every failure. Add focused tests for callback failure and invalid/empty snapshot after re-registration, proving the old binding remains valid and no reference/generation leak occurs.
4. Implement the normative owner-key preference in the production registration/selection path. Call the canonical comparator there and choose one complete binding before publication; never merge operation tables, contexts, or snapshots.
5. Add a production-path test with competing roles and an explicit configured preference that proves which complete binding is selected. The synthetic helper-only comparator test is not sufficient.
6. Reconcile the entire top-level `XaveriusDeviceBackendOps` descriptor, all typed callback signatures and immutable/const nested operation-table pointers against the current ABI-v1 normative spec. Keep the two-argument `query_physical_snapshot` unchanged.
7. Correct `ACCEPTANCE_MATRIX.md` only after the source and production-path tests conform. Do not claim ABI-v1 acceptance before the header and tests prove it.
8. Run focused registry/QV tests and a fresh exact-head Xserver Actions run. Report exact source SHA, parent, changed paths, test commands/results, CI URL and any remaining blockers.

Keep fixes in small, independently reviewable commits. No broad formatting or unrelated refactor. Preserve all work; no reset, force-push, stash, overwrite, or discard. Do not stage broad globs. Do not answer or approve pending Asks.
