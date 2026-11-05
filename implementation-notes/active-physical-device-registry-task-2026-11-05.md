# Active task — implement the PhysicalDevice registry

**Priority:** HIGH — primary XAverius implementation work  
**Target:** `X11Libre/xserver:wip/xaverius`  
**Starting point:** the verified live remote tip of `X11Libre/xserver:wip/xaverius`; at the 2026-11-05 audit it was `5f018603755f0c6b2342ea175d0826a9b8f912f7`. Do not reset to `f6f3e87aa81724208496d539e40d2eee2c3d2641`.  
**Specification authority:** `metux/xav-design:docs/restructure-2026-10-21`  
**Status:** ACTIVE — replaces the old “Phase 0 only / Phase A-B paused” instruction. CI repair tasks continue independently at LOW priority and do not gate registry implementation.

**Branch safety correction (2026-11-05):** `f6f3e87aa81724208496d539e40d2eee2c3d2641` is not a clean-slate rollback boundary: it is a normal commit whose parent is `ce7f5eed79af22106f6d202f2bae8aa11274e214`. The current observed tip `5f018603755f0c6b2342ea175d0826a9b8f912f7` is four commits beyond it. Do not reset, force-push, or merge historical branches. Fetch and inspect the live remote tip; preserve valid non-registry commits already on the branch. If ancestry diverges or unexpected registry code appears, stop and report exact SHAs before writing. Only the owner may authorize an exact reset target.

This task authorizes actual PhysicalDevice registry implementation. It does NOT authorize protocol request handlers, backend operation implementations, or premature modesetting/discovery integration.

## 1. Read first; resolve authority

Before editing, sync and read these exact files from the authoritative spec branch:

- `spec/device-registry-architecture.md`
- `spec/registry-api-lifetime-addendum.md`
- `spec/provider-operation-matrix.md`
- `implementation-notes/xserver-registry-rebuild-plan-2026-11-05.md`
- `implementation-notes/phase-a-registry-audit-2026-11-05.md`
- `implementation-notes/phase-a-ddx-corrections.md`
- `implementation-notes/ddx-device-registration.md`

The current spec API names are `GpuRegistryRegisterDdxDevice`, `GpuDeviceBackendRegistration`, `GpuDeviceBackendOps`, `GpuPhysicalDevice`, `GpuDeviceBackendBinding`, and `GpuModuleRole`. Older `XaveriusRegisterDevice`, `XaveriusPhysicalDeviceOps`, `provider_handle`, capabilities-only registration, and earlier rollback-era API sketches are not authority. Do not revive them.

If two normative sources disagree, STOP at that point, record the exact conflicting passages in the coordination board, and ask for resolution. Do not silently choose a convenient interpretation. In particular, the registration descriptor says native handle and per-device context are borrowed DDX-owned values: the registry must not free them and there are no context retain/release callbacks. The DDX keeps them valid through exact binding removal and retirement of all dependent users. Do not implement a contradictory registry-owned context refcount.

The earlier Phase-A/C1–C10 findings remain useful defect checklists, but their obsolete API names and sequencing do not override the current normative API and this task.

## 2. Scope and order

Implement in the following independently reviewable stages. Keep each commit atomic and buildable. Do not create one giant registry commit.

### Stage 1 — canonical types and API declarations

- Inspect the seven-file clean Xaverius baseline and the existing init/meson/header structure before adding anything.
- Establish one canonical internal `GpuPhysicalDevice` representation. Its immutable physical-property snapshot is a member/value of that object. Do not add parallel DeviceCaps/PhysicalDeviceInfo objects.
- Establish one direct `GpuDeviceBackendBinding` per exact DDX registration, containing the borrowed native handle/context, immutable server-owned copy of the versioned `const GpuDeviceBackendOps` tables, exact binding generation, and retained owning ModuleRole generation.
- Keep the PhysicalDevice XID and DIX resource wrapper entirely server-private. No DDX-visible declaration may expose either.
- Declare the normative registration API and its exact result/out-parameter contract. On SUCCESS return one immediate caller-owned opaque PhysicalDevice reference and exact device/binding generations; caller releases it with `GpuPhysicalDeviceRelease`. The caller must not retain/dereference the bare pointer later.
- Preserve the established two header scopes. Put declarations in the correct existing header; add no convenience/duplicate headers without a demonstrated interface need.
- Keep the top-level ops, registration descriptor, and ModuleRole descriptor size/version validation exactly as specified. Validate headers before reading later fields or retaining anything.
- Do not add registry lists, DIX resources, request handlers, or DDX discovery in this stage.

**Stage 1 tests:** compile-time type/layout checks where appropriate; ABI header tests for NULL, undersized/oversized v1, unknown version; no callback or retain hook entered on invalid descriptor. Document the ownership table in comments or the implementation note, not by inventing extra fields.

### Stage 2 — ModuleRole lifetime substrate

- Implement the separate ModuleRole control record needed to pin module code/shared resources and control callback admission/quiescence. It is not a per-device dispatch proxy and has no generic context getter.
- Implement generation checks, admission close, callback-execution references, quiesce PENDING/SUCCESS/FAILURE, finalization, and quarantine on uncertain quiescence.
- All roles, including permanent roles, provide non-NULL retain/release/quiesce hooks. Permanent roles have no loader lease and can enter shutdown only after registry shutdown begins.
- Follow the lease ownership rules exactly: module owner owns its initial lease reference; each unloadable role owns one additional retained reference; role finalization drops only its role-owned reference; owner releases its own reference only after every role for that module instance is finalized.
- Successful role registration calls retain exactly once after fallible validation/allocation; failed registration calls no role hook. Finalization calls release exactly once after quiescence. Hooks are infallible, non-blocking lifetime primitives.
- Do not use Screen lifetime, DriverPtr.refCount, a raw ModuleDesc pointer, or a per-Screen duplicate ModuleDesc as the backend module pin.

**Stage 2 tests:** role registration failures; multiple roles sharing one module lease; permanent role shutdown; callback admission racing shutdown; PENDING then SUCCESS; FAILURE/quarantine; final unpin retry; exact retain/release pairing.

### Stage 3 — registry core and identity

- Implement one process-wide registry service with serialized mutations in the server event/main-thread domain.
- Implement canonical identity and incarnation handling from the normative identity evidence hierarchy. Do not synthesize identity from vendor/device/API/driver versions. Platform/udev observations are evidence only; they are not executable registrations and cannot publish a device.
- Distinguish same-incarnation duplicate observations, exact idempotent registration replay, conflicting DDX bindings, ambiguous identity, removal, and remove/re-add incarnation. Never merge snapshots, operation tables, native handles, or contexts.
- v0.1 has one selected executable binding per published PhysicalDevice. Selection follows the stable configured DDX-role preference, never registration order, Screen order, pointer value, DRM node number, or module load order. No transparent failover.
- Keep ScreenAttachment out of PhysicalDevice ownership. No Screen, ScrnInfo, Entity, RandR output, connector, or first-GPU pointer may own the registry.
- Do not implement a second platform inventory or global `/dev/dri` scan.

**Stage 3 tests:** PCI and supported non-PCI identity cases; primary/render aliases; missing/contradictory evidence; same UUID with conflicting bus evidence; two DDX observations; deterministic role preference; duplicate replay; remove/re-add incarnation; stale generation rejection.

### Stage 4 — registration, snapshot, and DIX publication

Implement the real failure-atomic registration/publication path. Keep registration/snapshot installation separate from publication:

1. Validate the complete registration descriptor header before reading subsequent fields. Validate identity evidence, non-NULL exact native handle/context as required by the profile, exact live ModuleRole pointer/generation, and the versioned ops descriptor header.
2. Acquire the exact ModuleRole admission/reference. Reject a quiescing/retired generation. Treat native handle/context as borrowed DDX-owned values; do not free them or invent context retain/release callbacks.
3. Validate every required top-level callback and all four typed operation tables for the enabled v0.1 profile. Copy the complete descriptor/tables by value into immutable server-owned binding storage. No partial binding can become visible.
4. Canonicalize/resolve identity and reserve a fresh non-reusable binding generation. Exact replay is idempotent only when it is the same live registration/binding ownership; return one additional caller-owned PhysicalDevice ref. Conflicting data returns a classified failure and no ref.
5. Query the physical snapshot through the exact provisional binding's `query_physical_snapshot`. Initialize output fields to failure sentinels; validate all counts, pointer/count pairs, ranges, UUIDs, queue/memory consistency and advertised features; deep-copy into the PhysicalDevice-owned snapshot value.
6. Install the complete binding and snapshot atomically as an internal, possibly not-yet-published PhysicalDevice. Registration SUCCESS does not imply an XID.
7. Only after canonical identity resolution, eligible-binding selection, and the startup publication gate opens, call the separate `XaPhysicalDevicePublish` path. Allocate a server-private XID and prepare its DIX wrapper while still provisional.
8. Call `AddResource()` exactly once. Only after success expose the XID/resource and registry publication state atomically in the server serialization domain.
9. The DIX resource destructor is the one canonical path that retires published resource membership and unlinks the registry entry. It must not race a direct free or leave a stale list pointer.

Every failure unwinds provisional state and all acquired references. No partially copied snapshot, invalid identity, missing operation, failed callback, failed resource insertion, or descriptor error may leave a binding, published list entry, visible XID, or caller-owned reference. Reserved non-reusable generations remain consumed.

**Stage 4 tests:** failure injection at every allocation/callback/identity/resource step; AddResource call count exactly one; AddResource failure leaves no XID/list/resource; destructor exactly once; RegistryFini cannot double-free or traverse stale entries; registration success before publication; publication barrier; exact replay; conflicting replay; borrowed context/handle never freed by registry; no leaks under ASan/Valgrind where available.

## 3. Required reference/ownership table

The implementation report MUST provide a table with one row per reference class and columns: owner, acquire point, release point, what it protects, and behavior on failure/quarantine.

At minimum cover:

- caller-owned immediate PhysicalDevice reference returned by registration;
- registry's internal PhysicalDevice membership reference;
- DIX resource ownership/reference and destructor path;
- PhysicalDevice-to-selected-binding reference;
- binding-to-ModuleRole-generation reference;
- ModuleRole-to-module-lease reference and module owner's original lease reference;
- synchronous callback-execution reference;
- every dependent logical Device/backend object/operation-token reference when those later phases are reached.

Do not add context ref callbacks: context lifetime is a DDX-side obligation protected by the binding/role lifecycle contract. Make this explicit in code comments and tests.

## 4. Initialization and teardown

- There must be one canonical extension init/fini path. Verify the existing extension registration table and exported init symbol; do not add competing init/fini implementations.
- Initialize the PhysicalDevice DIX resource type exactly once before it can be used.
- Define one registry shutdown order: close registry/role admission; stop discovery sources; detach ScreenAttachments (when implemented); withdraw/retire bindings; drain accepted operations/callbacks; destroy/quarantine backend-dependent state; remove published resources through the DIX destructor path; finalize ModuleRoles; release registry storage last.
- No direct free of a still-published DIX resource. No double ownership between RegistryFini, DevicesFini, extension fini, or DIX destructor.
- Implement the subset required by current stages now; do not stub later stages as success. Record deferred ScreenAttachment/discovery/backend-object teardown explicitly.

## 5. Explicitly out of scope for this assignment

- OpenBSD and Cygwin CI repair: separate low-priority fleet tasks continue. Do not spend registry time on them.
- DDX-wide discovery, udev subscribe-before-scan, modesetting enumeration/call site, and ScreenAttachment integration: separate follow-up task after the registry core is reviewed. Do not invent a fake DDX discovery API to make a demo pass.
- Protocol requests/replies, opcodes, XID enumeration/query handlers, Compute Memory handlers, Vulkan object/backend operations: later phases only. Do not revive the premature Compute Memory handler work from the discarded branch.
- Do not cherry-pick registry/inventory implementation commits from `wip/xaverius_old_1` or any discarded branch. The old branch is forensic reference only.

## 6. Small concrete reference example

This is semantic pseudocode, not a competing public declaration. Adapt names only where the current normative headers require it:

```c
GpuPhysicalDevice *device = NULL;
uint64_t device_generation = 0;
uint64_t binding_generation = 0;

GpuRegistryResult result =
    GpuRegistryRegisterDdxDevice(registry, &registration,
                                 &device,
                                 &device_generation,
                                 &binding_generation);

if (result == GPU_REGISTRY_SUCCESS) {
    /* Immediate reference only; registration does not promise an XID. */
    GpuPhysicalDeviceRelease(device);
    device = NULL;
} else {
    /* No device reference, binding, or XID was returned/published. */
    assert(device == NULL);
}
```

Registration descriptor construction must pass the exact per-device context/handle, structured identity, live ModuleRole generation, and `const GpuDeviceBackendOps *`. Do not pass only capabilities or a vendor/device tuple.

Publication is a distinct server-internal action after the startup barrier and deterministic binding selection; it is not performed by the DDX caller and is not implied by the successful registration result.

## 7. Commit and source hygiene

- Work only on `X11Libre/xserver:wip/xaverius`; verify remote tip before each work session. Never use blind `git pull`, `git reset --hard`, `git clean -fdx`, force-push, or merge from `master`/`wip/xaverius_old_1`. Fetch and inspect ancestry first; only fast-forward when the local branch is strictly behind and has no unique commits. If divergent, stop and report. Do not edit Xserver source in this spec repository.
- Use intermediate commits. One topic per commit: type/API, ModuleRole substrate, identity/registry core, registration/snapshot, DIX publication, shutdown integration.
- Any `hw/xfree86/drivers/modesetting/` changes are a separate later commit and are not part of this task.
- Any `include/*` public SDK ABI change requires a separate commit, explicit ABI rationale, size/version or compatibility strategy, and old-binary tests. Prefer private headers.
- Preserve names, formatting, include ordering, license headers, existing init/protocol layout. No gratuitous renames, reformatting, broad refactors, extra headers/includes, duplicate init paths, or monolithic `xaverius.c`.
- Every commit must build at its boundary or clearly document why a short indivisible series is required. Run focused unit/failure-injection tests before the full matrix.
- Do not report CI as green unless the exact commit has a completed successful workflow. OpenBSD/Cygwin failures are tracked separately and must not be used to hide other failures.

## 8. Required agent report and acceptance gates

For each commit/report include:
- agent, repository, branch, full commit SHA and parent SHA;
- exact changed files and one-sentence purpose per file;
- exact symbols, declarations, init registration and call sites;
- reference/ownership table updates;
- exact test commands, exit codes, PASS/FAIL/BLOCKED individually;
- remaining blockers and next independently reviewable commit.

**Do not proceed to DDX discovery or protocol/backend work until Stages 1–4 are reviewed and accepted.** The registry core itself must be functional and testable with a synthetic/mock DDX registration; it must not depend on modesetting or a real GPU to prove its transaction and lifetime behavior.
