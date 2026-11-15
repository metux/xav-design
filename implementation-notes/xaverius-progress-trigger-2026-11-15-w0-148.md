---
id: W0-20261115-148
kind: progress-trigger
from: owner-coordination
to: Defiant
created: 2026-11-15T08:06:33Z
in_reply_to: W0-20261114-147
task_ref: existing XAverius PhysicalDevice registry implementation / W0-117-W0-121 CI follow-up
correlation_id: defiant-xaverius-progress-148
workspace: X11Libre/xserver@wip/xaverius
---

# W0-148 — Finish the production binding-preference path and ABI-v1 reconciliation

This is an immutable progress trigger for the existing registry implementation and CI follow-up. It does not create or replace an implementation task. Preserve all current work and both repository histories.

## Verified current state

- Xserver `wip/xaverius` remote HEAD: `7337c7944d1e5b133d3026b789c643fd988d12b6`.
- The latest source-bearing commit is `58fe14b09758830b035aeb3ab46af555b349c2a7`. Comparing it with current HEAD shows 21 later commits changing only `Xext/xaverius/ACCEPTANCE_MATRIX.md`; no source or test file changed after that source-bearing commit.
- Exact-head Xserver Actions run [43658358816](https://github.com/X11Libre/xserver/actions/runs/43658358816) for `7337c794` completed **success**. All returned platform jobs are green, including FreeBSD, OpenBSD and Cygwin. This supersedes the old Meson/FreeBSD failures from run 42427837938; do not keep reporting those as current CI failures.
- The Xaverius tests are now integrated into the existing `test/tests` harness. `test/meson.build` adds `xorg_inc` only in the Xorg build path and adds the registry/QV tests to the existing test binary when Xaverius is enabled. The old separate synthetic executable is not the current target.
- `test/xaverius-registry.c` directly tests `xaverius_compare_ordering_key()`, and `xaverius_registry_registration_contract()` does exercise the production registration API for same-role replay and cross-role identity conflict.
- Production identity deduplication is now present: `XaveriusRegistryRegisterDdxDevice()` calls `xaverius_find_device_by_identity()`; same-role replay returns the canonical record and a different role currently returns `IDENTITY_CONFLICT`.
- The remaining ordering gap is **selection**, not identity deduplication. `XaveriusRegistryRegisterDdxDevice()` computes an ordering key, but `xaverius_compare_ordering_key()` has no production call site. The registration test currently expects every different-role claim to return `IDENTITY_CONFLICT`. The current implementation has no `XaveriusRegistryCreateInfo` / `ddx_binding_preference_owner_keys` path, whereas the normative spec requires ordered server-configured owner-key preference and selection of one complete binding before publication. Rejecting all competing roles does not implement that policy.
- The top-level `XaveriusDeviceBackendOps` in `xaverius_intern.h` still differs from normative ABI v1: its `struct_size` and `abi_version` are `uint64_t`, callback signatures remain generic/opaque rather than the normative typed signatures, and nested operation-table pointers are mutable rather than `const`.
- The `query_physical_snapshot` callback is correctly the normative **two-argument typed signature**: `(XaveriusDeviceBackendBinding *, XaveriusPhysicalDeviceSnapshot *)`. Preserve it; do not restore the obsolete three-argument form.
- The current acceptance matrix still declares ABI-v1 fully accepted. That verdict is not supported by the live header or production selection path and must be reconciled with the actual implementation.

## Concrete continuation requested

1. Implement the normative owner-key preference in the **real production registration/selection path**. Add/use the server-configured preference data, compare candidate ordering keys there, and select exactly one complete binding before publication. Do not merge operation tables, contexts or snapshots. Preserve same-role replay idempotency and the no-transparent-failover rule after publication.
2. Replace the current “different role always means IDENTITY_CONFLICT” behavior only where the normative preference policy selects the competing candidate. Add tests that register competing roles with an explicit preference and assert the actual selected production binding. A direct helper-only comparator test is insufficient.
3. Reconcile the complete top-level `XaveriusDeviceBackendOps` descriptor and callbacks with the current normative ABI-v1 declaration: 32-bit size/version fields, typed callback signatures and immutable `const` nested operation tables. Keep the two-argument snapshot callback unchanged.
4. Correct `ACCEPTANCE_MATRIX.md` so its audited source SHA, implementation verdicts and ABI verdict match the real code and executed tests. Do not claim full ABI-v1 acceptance before the header and selection path conform.
5. Rebuild and run the focused registry and QV tests from the exact source HEAD, then obtain a new exact-head Xserver CI run. Report the full SHA, parent, changed paths, production comparator call sites, test command/output and CI run URL.

No broad cleanup, unrelated formatting, reset, force-push, history rewrite, session restart, Ask approval or discarded work. Continue the existing task until source, tests, matrix and exact-head evidence agree.
