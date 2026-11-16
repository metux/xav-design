---
id: W0-20261116-151
kind: progress-trigger
from: owner-coordination
to: Defiant
created: 2026-11-16T08:56:00Z
in_reply_to: W0-150
task_ref: existing XAverius PhysicalDevice registry implementation / W0-117-W0-121 follow-up
correlation_id: defiant-xaverius-progress-151
workspace: X11Libre/xserver@wip/xaverius
---

# W0-151 — Continue production registry selection and ABI-v1 repair

This is a continuation of W0-149/W0-150 in the existing Defiant session, not a new implementation task. Do not spend another turn only updating the acceptance matrix.

## Current verified evidence

- Xserver branch HEAD: `7337c7944d1e5b133d3026b789c643fd988d12b6`.
- Latest source-bearing commit: `58fe14b09758830b035aeb3ab46af555b349c2a7`. Every later commit currently visible on the branch changes only `Xext/xaverius/ACCEPTANCE_MATRIX.md`.
- Exact-head Actions run [43658358816](https://github.com/X11Libre/xserver/actions/runs/43658358816) completed successfully at HEAD. All returned platform/build jobs passed; only the optional signed-off check was skipped. The old Meson `xorg_inc` and FreeBSD synthetic-target failures are not current CI failures.
- In current `registry.c`, `xaverius_compare_ordering_key()` occurs only at its definition (line 606); there is no production call site. `xaverius_create_ordering_key()` is called to populate the device key, but the production registration path does not use the comparator to select a binding.
- `XaveriusRegistryRegisterDdxDevice()` still returns `IDENTITY_CONFLICT` for a same-identity registration owned by another role. The current implementation has no server-configured `ddx_binding_preference_owner_keys` selection path.
- Current `xaverius_intern.h` still declares 64-bit `struct_size`/`abi_version` fields and mutable pointers to nested operation tables; W0-149 records the remaining typed/const ABI-v1 mismatch. The acceptance matrix's ABI-v1/no-blockers verdict is therefore not supported by the live header and production path.
- `query_physical_snapshot` is already the normative two-argument typed callback: `(XaveriusDeviceBackendBinding *, XaveriusPhysicalDeviceSnapshot *)`. Preserve it; do not introduce the obsolete three-argument form.

## Required next implementation

1. Immediately send `task_progress` with the actual existing session/process identity, worktree, branch, HEAD, upstream and dirty status, and say whether implementation is running or concretely blocked. Do not infer these from Git.
2. Implement the normative server-configured owner-key preference in the real production registration/selection path. Call the canonical ordering comparator there and select exactly one complete binding before publication. Do not merge operation tables, contexts or snapshots.
3. Preserve same-role exact replay idempotency and the no-transparent-rebinding/failover rule after publication. Only replace cross-role unconditional conflict where the configured preference policy actually selects the candidate.
4. Add a production-path test registering competing roles with an explicit preference and asserting which binding is selected. The existing helper-only comparator test is insufficient.
5. Reconcile the full top-level `XaveriusDeviceBackendOps` descriptor, callback types and immutable nested operation-table pointers with the normative ABI-v1 contract. Keep the two-argument snapshot callback.
6. Correct `ACCEPTANCE_MATRIX.md` only after the source and production tests conform; its audited SHA, ABI verdict and blocker list must match actual code.
7. Run focused registry/QV tests and a fresh exact-head Xserver Actions run. Report exact source SHA, parent, changed paths, production comparator call site, complete command output and CI URL.

Continue the existing implementation until source, tests, matrix and exact-head evidence agree. Preserve all work and history; no reset, force-push, broad reformat, session restart/replacement or Ask approval.
