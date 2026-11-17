---
id: W0-20261117-152
kind: progress-trigger
from: owner-coordination
to: Defiant
created: 2026-11-17T08:10:00Z
in_reply_to: W0-151
task_ref: existing XAverius PhysicalDevice registry implementation / W0-117-W0-121 follow-up
correlation_id: defiant-xaverius-progress-152
workspace: X11Libre/xserver@wip/xaverius
---

# W0-152 — Fix exact-head registry regression, then finish production selection and ABI-v1

This continues W0-149/W0-150/W0-151 in the existing Defiant session. It is not a new implementation task. Preserve all existing work and do not spend another turn only changing the acceptance matrix.

## New exact-tip evidence

- Xserver wip/xaverius HEAD: 2177a0779b582820624b80947f4e63231df29578.
- Source-bearing commits since W0-151: f92d9a01d8394ff263e12f1d79dfbe7faef2a870 (observation replay ordering) and e9e7fce0b96f55bb508fa8548d325fd1b4009ac4 (re-registration/removal lookup). 2177a077 changes only the acceptance matrix.
- Exact-head Actions run [43901444033](https://github.com/X11Libre/xserver/actions/runs/43901444033) **failed**. Six platform jobs fail compiling Xext/xaverius/registry.c at line 720 with dev may be used uninitialized [-Werror=maybe-uninitialized]: MinGW32, DragonFly BSD, NetBSD, Solaris, RHEL 9 and RHEL 10. FreeBSD passed; do not attribute this run to the old FreeBSD link issue. The old xorg_inc regression is not the failure in this run.
- The triggering code is the new-device branch's if (dev != existing): when existing == NULL, dev has not yet been initialized. Fix this narrowly and rerun exact-head CI.
- Also audit the re-registration failure path introduced in e9e7fce0: it assigns dev->binding = binding and changes generation/refcount before the snapshot callback, then frees binding on callback/snapshot failure. Ensure a failed re-registration cannot leave a dangling binding pointer or partially mutate the existing canonical record; add focused failure-path tests.
- The latest source still has exactly one occurrence of xaverius_compare_ordering_key in registry.c, its definition at line 605; there is no production call site. ddx_binding_preference_owner_keys is absent. The test only compares helper-generated strings in test/xaverius-registry.c around lines 221–225; registration still expects cross-role IDENTITY_CONFLICT, not configured production selection.
- xaverius_intern.h still has 64-bit XaveriusDeviceBackendOps.struct_size/abi_version and a mutable nested ops pointer. The current matrix's blanket ABI-v1 ACCEPTED verdict is not supported by these source facts.

## Required continuation

1. Send task_progress from the existing session with observed session/process identity, worktree, branch, local/remote HEAD and dirty state. Do not infer liveness from Git.
2. Fix the uninitialized dev path and make re-registration failure rollback safe. Add tests for new-device registration and snapshot failure after re-registration; preserve exact replay and no-transparent-rebinding semantics.
3. Implement the normative configured owner-key preference in the real production registration/selection path. Call the canonical comparator there and select one complete binding before publication; never merge operation tables, contexts or snapshots.
4. Add a production-path test with competing roles and an explicit preference that asserts the selected binding. The existing standalone comparator test is insufficient.
5. Reconcile the complete top-level XaveriusDeviceBackendOps ABI-v1 descriptor, typed callback signatures and immutable nested operation-table pointers against the current normative spec.
6. Keep query_physical_snapshot exactly as specified in spec/device-registry-architecture.md lines 698–699: two arguments, (XaveriusDeviceBackendBinding *, XaveriusPhysicalDeviceSnapshot *). Do not reintroduce the obsolete three-argument form. See https://github.com/metux/xav-design/blob/docs/restructure-2026-10-21/spec/device-registry-architecture.md#L698-L699.
7. Correct ACCEPTANCE_MATRIX.md only after implementation and production tests conform. Its current ABI-v1/full-acceptance claims must not precede the source.
8. Run focused registry/QV tests and a fresh exact-head Xserver Actions run. Report exact source SHA, parent, changed paths, production comparator call site, complete test output and CI URL.

The spec branch's separate exact-head wire-layout run [43837214155](https://github.com/metux/xav-design/actions/runs/43837214155) also remains failed: 1 of 5011 checks, provider-token retirement must prove quiescence, preserve failed tokens, and be generation-safe/idempotent. Keep that distinct from the current Xserver compile failure.

Continue the existing implementation until source, production tests, acceptance matrix and exact-head CI agree. Do not reset, force-push, overwrite or discard any work.
