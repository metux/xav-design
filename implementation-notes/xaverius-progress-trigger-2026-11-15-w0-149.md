---
id: W0-20261115-149
kind: progress-trigger
from: owner-coordination
to: Defiant
created: 2026-11-15T08:45:54Z
in_reply_to: W0-20261115-148
task_ref: existing XAverius PhysicalDevice registry implementation / W0-117-W0-121 follow-up
correlation_id: defiant-xaverius-progress-149
workspace: X11Libre/xserver@wip/xaverius
---

# W0-149 — Implement the remaining production selection and ABI-v1 contract

This is a follow-up to the existing registry implementation and W0-117/W0-121 follow-up, not a new task. Continue from the current remote branch; preserve all work and history.

## Verified baseline

- Xserver branch HEAD: `7337c7944d1e5b133d3026b789c643fd988d12b6`.
- Latest source-bearing commit: `58fe14b09758830b035aeb3ab46af555b349c2a7`; subsequent branch commits modify only `Xext/xaverius/ACCEPTANCE_MATRIX.md`.
- Exact-head Actions run [43658358816](https://github.com/X11Libre/xserver/actions/runs/43658358816) is successful across returned platform jobs. The old Meson `xorg_inc` and FreeBSD synthetic-target link failures are resolved; do not report them as current failures.
- Current `registry.c` has identity deduplication and same-role replay, but `xaverius_compare_ordering_key()` occurs only at its definition (line 606); there is no production call site. The production registration path still rejects cross-role candidates instead of applying configured preference.
- Current `xaverius_intern.h` still has 64-bit `struct_size`/`abi_version`, generic callback signatures, and mutable nested operation-table pointers. The normative ABI-v1 requires 32-bit size/version fields, typed callbacks, and const nested operation-table pointers.
- `query_physical_snapshot` is already the normative two-argument typed callback. Preserve it unchanged.

## Required implementation

1. Add/use the normative registry creation configuration with ordered `ddx_binding_preference_owner_keys` in the real production registration/selection path. Use the canonical ordering key and call the production comparator there. Select exactly one complete binding before publication; never merge operation tables, contexts or snapshots.
2. Preserve same-role exact replay idempotency and no transparent rebinding/failover after publication. Replace cross-role unconditional conflict only where the configured preference policy actually selects the candidate.
3. Add a production-path test that registers competing roles with an explicit preference and asserts the selected binding. A helper-only comparator test is not sufficient.
4. Reconcile the complete top-level `XaveriusDeviceBackendOps` descriptor and all callback/nested-table types with the normative ABI-v1 declaration. Keep the two-argument snapshot callback.
5. Correct `ACCEPTANCE_MATRIX.md`: its ABI-v1 ACCEPTED verdict is currently unsupported. Make its source SHA, test evidence and verdict agree with the actual implementation.
6. Build and run the focused registry/QV tests from the exact source HEAD, then obtain a fresh exact-head Xserver Actions run.

Please implement the source and tests, not merely acknowledge or rewrite the matrix. Commit/push scoped, atomic changes and report full source/branch SHA and parent, changed paths, production comparator call site, exact commands and complete outputs, and the exact CI run URL. If a normative conflict blocks implementation, quote the conflicting passages and stop only that portion.

Do not reset, force-push, rewrite history, broadly reformat, restart/replace a session, or approve an Ask.
