# Xserver registry rebuild plan — clean pre-registry rollback

**Date:** 2026-11-05  
**Target:** `X11Libre/xserver:wip/xaverius`  
**Required rollback target:** `f6f3e87aa81724208496d539e40d2eee2c3d2641`  
**Current audited tip before rollback:** `deb0e445001389be031fa7e006e3e2e216616b50`  
**Normative authority:** `metux/xav-design:docs/restructure-2026-10-21`  
**Status:** rollback complete and independently verified at the remote branch ref; implementation plan ready. The first ref-update attempt returned HTTP 403, but a subsequent independent read confirmed the branch now resolves exactly to the target SHA.

## 1. Decision and rollback boundary

The current registry/inventory implementation is to be discarded as a unit. Do not repair it incrementally and do not cherry-pick its registry commits back.

The history establishes this boundary:

- `f6f3e87aa81724208496d539e40d2eee2c3d2641` is the parent of the first inventory/registry introduction `00fcd15955a0c2bd810034cc8b5b3bf1731d996a`.
- The complete `Xext/xaverius/` tree at `f6f3e87` contains only `dispatch.c`, `init.c`, `meson.build`, `screen.c`, `xaverius_intern.h`, `xaverius_priv.h`, and `xaverius_proto.h`. It has no registry implementation, no inventory implementation, and no PhysicalDevice inventory types.
- The first inventory commit `00fcd159` added `registry.c`; `7eb8b738` then added another PhysicalDevice inventory record; `6b36065e` further rewrote the inventory; `6deb8aec` introduced the later DDX-wide registry/Screen split. The subsequent current-tip commits did not produce a coherent replacement.
- The separate earlier `ba88b494` baseline is **not** the pre-registry baseline: its commit message is “replace device inventory with global registry”, and it already contains registry API/state in `xaverius_intern.h` and `xaverius_registry.c`.

The target `f6f3e87` is therefore the clean pre-inventory/pre-registry point. It preserves the pre-existing extension, protocol declarations, and Screen integration. New registry work starts from this exact tree.

### Rollback command for the branch maintainer

The initial force-with-lease update attempt returned HTTP 403. A subsequent independent read of the remote ref confirmed that the rollback has since been completed. Current verified `refs/heads/wip/xaverius` is exactly `f6f3e87aa81724208496d539e40d2eee2c3d2641`. Do not repeat the reset/push. The command below is retained only as an auditable recovery procedure if the branch is moved again:

```sh
git fetch origin
git switch wip/xaverius
git reset --hard f6f3e87aa81724208496d539e40d2eee2c3d2641
git push --force-with-lease=refs/heads/wip/xaverius:deb0e445001389be031fa7e006e3e2e216616b50 \
    origin HEAD:refs/heads/wip/xaverius
```

If the remote branch has advanced, stop and inspect the new commits; do not overwrite them blindly. After the push, verify that `refs/heads/wip/xaverius` resolves exactly to `f6f3e87...` and that the seven-file Xaverius directory listing above matches. The discarded history remains reachable by its commit SHAs; do not merge it back into the rebuilt branch.

## 2. Non-negotiable object model

There must be exactly one internal representation for each responsibility. Do not reuse a snapshot as an ops table or make a wire structure double as an internal object.

### 2.1 PhysicalDevice

One server-owned, process-wide registry record per canonical physical-device incarnation. This is the single internal PhysicalDevice object; do not introduce a second DeviceCaps or PhysicalDeviceInfo object for the same device. It contains:

- canonical identity and incarnation evidence;
- one immutable capability/property snapshot as a member of this object;
- one reference to the selected exact per-device backend binding;
- server-private DIX resource/XID state and non-reusable PhysicalDevice generation;
- lifecycle/status, publication and reference/lifetime bookkeeping.

The snapshot is a subordinate value owned by PhysicalDevice, not a separately registered or independently identified device object. The server-private XID/resource fields MUST NOT be present in the DDX-facing ABI or exposed through a driver-visible structure. If common PhysicalDevice declarations are visible to DDX code, the server object remains opaque/incomplete there; the DDX cannot inspect or manipulate its XID. Do not add duplicated capability fields, Screen pointers, DRM file descriptors masquerading as identity, or a second provider object.

### 2.2 Snapshot

One immutable snapshot value (suggested type name `XaveriusPhysicalDeviceSnapshot`) is owned directly by PhysicalDevice; it is not a separate registry object or X11 resource. It contains queried metadata only: device properties, UUIDs, queue-family properties, memory types/heaps, and every other server-published PhysicalDevice property.

It owns deep-copied server memory. It contains no callbacks, native handles, backend context, ModuleRole pointer, Provider pointer, or ownership hooks. Pointer/count pairs are validated before copying. A successful snapshot is complete for the advertised capability profile.

### 2.3 Per-device binding

One `XaveriusPhysicalDeviceBinding` (or equivalent) is the direct dispatch target for the exact PhysicalDevice. It contains:

- exact DDX-native PhysicalDevice handle;
- exact per-device backend context;
- an immutable, server-owned copy of the supplied `XaveriusPhysicalDeviceOps` table and its typed sub-tables;
- a non-reusable binding generation;
- a retained reference to the owning `GpuModuleRole` generation;
- binding state, call admission, in-flight synchronous-call count and async-token references.

The PhysicalDevice holds exactly one selected binding in v0.1. No dispatch proxy, Provider layer, candidate ranking object, generic ModuleRole context accessor, or Screen-private dispatch route is permitted.

### 2.4 PhysicalDeviceOps — mandatory DDX registration input

The DDX MUST pass a matching `XaveriusPhysicalDeviceOps` structure for **each** registered PhysicalDevice. This is not optional and cannot be deferred to Phase B.

The DDX supplies a pointer to a `const XaveriusPhysicalDeviceOps` structure for each registration. The structure is immutable for the duration of the call; the registry validates and copies it into server-owned immutable storage before publication. The structure is an implementation-facing C interface, not wire ABI. It MUST have an explicit `struct_size` and `abi_version` (or an equivalent validated versioned registration descriptor); never read optional trailing fields from an older, smaller structure without a size/version gate.

Conceptual shape:

```c
typedef struct XaveriusPhysicalDeviceOps {
    uint32_t struct_size;
    uint32_t abi_version;

    /* Queries the complete immutable snapshot for this exact device. */
    GpuBackendResult (*query_physical_snapshot)(
        XaveriusPhysicalDeviceBinding *,
        XaveriusPhysicalDeviceSnapshot *);

    /* Logical Device lifecycle and queue acquisition. */
    GpuBackendResult (*create_logical_device)(
        XaveriusPhysicalDeviceBinding *,
        const GpuDeviceCreateInfo *, GpuBackendDevice **);
    GpuBackendResult (*get_queue)(
        GpuBackendDevice *, uint32_t family, uint32_t index,
        GpuBackendQueue **);
    GpuBackendResult (*destroy_logical_device)(GpuBackendDevice *);

    /* Typed per-device operation tables; no generic opcode dispatcher. */
    const GpuBackendBufferMemoryOps *buffer_memory;
    const GpuBackendShaderPipelineOps *shader_pipeline;
    const GpuBackendCommandOps *commands;
    const GpuBackendSynchronizationOps *synchronization;

    /* Queue submission and presentation operations for this binding. */
    GpuBackendResult (*queue_submit)(
        GpuBackendQueue *, const GpuBackendSubmitInfo *,
        GpuBackendOperationToken *);
    GpuBackendResult (*create_surface)(
        XaveriusPhysicalDeviceBinding *, const GpuBackendSurfaceInfo *,
        GpuBackendSurface **);
    GpuBackendResult (*destroy_surface)(GpuBackendSurface *);
    GpuBackendResult (*query_surface_support)(
        XaveriusPhysicalDeviceBinding *, GpuBackendSurface *,
        GpuBackendSurfaceSupport *);
    GpuBackendResult (*create_presentation_route)(
        XaveriusPhysicalDeviceBinding *,
        const GpuBackendPresentationRouteInfo *,
        GpuBackendPresentationRoute **);
    GpuBackendResult (*destroy_presentation_route)(
        GpuBackendPresentationRoute *);
    GpuBackendResult (*create_swapchain)(
        XaveriusPhysicalDeviceBinding *,
        const GpuBackendSwapchainInfo *, GpuBackendSwapchain **);
    GpuBackendResult (*destroy_swapchain)(GpuBackendSwapchain *);
    GpuBackendResult (*acquire_next_image)(
        GpuBackendSwapchain *, const GpuBackendAcquireInfo *,
        GpuBackendOperationToken *);
    GpuBackendResult (*queue_present)(
        GpuBackendQueue *, const GpuBackendPresentInfo *,
        GpuBackendOperationToken *);
    GpuBackendResult (*cancel_acquire)(GpuBackendOperationToken *);
    GpuBackendResult (*release_late_acquired_image)(
        GpuBackendSwapchain *, uint32_t image_index);
} XaveriusPhysicalDeviceOps;
```

This sketch mirrors the normative `GpuDeviceBackendOps` plus the four typed tables in `spec/provider-operation-matrix.md`. The implementation MUST use the current normative signatures and result types rather than copying this sketch mechanically. The table is copied/validated into server-owned immutable storage before publication; its function pointers remain callable only while the exact owning ModuleRole lease is pinned.

Module-wide lifecycle callbacks are **not** per-device operations. They belong to a separate `XaveriusModuleRoleOps`/ModuleRole control record (registration, callback admission, `quiesce_module_role`, and lifetime release). Do not duplicate module-wide quiescence callbacks in every PhysicalDeviceOps table.

### 2.5 Registration descriptor and ownership

Conceptual API (the concrete name may follow existing XAverius naming):

```c
XaveriusPhysicalDevice *
XaveriusRegisterPhysicalDevice(
    const XaveriusPhysicalDeviceRegistration *registration);
```

The return value is non-NULL only after successful publication; every failure, including duplicate/conflicting identity, returns NULL. A duplicate must never return the already-published device as if the new registration had succeeded. The returned pointer is opaque and is only a success/result reference for the immediate registration call: the DDX MUST NOT retain or later dereference a bare PhysicalDevice pointer. Later asynchronous or lifecycle work uses generation-checked server-issued references/tokens. The pointer exposes no XID and the DDX must not inspect the server-private PhysicalDevice layout. Detailed failure diagnostics belong in the server log/diagnostic path; callers must not infer a specific error from NULL.

The registration descriptor contains:

- structured `XaveriusDeviceIdentity` evidence (not vendor/device IDs alone);
- exact native PhysicalDevice handle;
- exact per-device context;
- pointer to the versioned `XaveriusPhysicalDeviceOps`;
- owning ModuleRole reference and exact ModuleRole generation;
- explicit context retain/release ownership callbacks or a documented transfer-of-one-reference rule;
- any DDX-local stable instance discriminator required for non-platform devices.

The native handle is valid for the entire retained context/binding lifetime. It is not copied as an integer and is not inferred from a Screen or global singleton. If several bindings share a DDX context, each binding acquires/releases one context reference. Operation-table storage is copied by value; the module lease pins the code behind function pointers.

**Ownership rule:** on SUCCESS the registry owns one binding/context/module-role reference; on any failure the caller retains ownership and the registry releases only references it explicitly acquired. This must be unambiguous for duplicate, conflict, retry, asynchronous completion, withdrawal, shutdown and quarantine paths.

## 3. Registration transaction

Registration is one failure-atomic operation:

1. Validate descriptor size/version, mandatory identity fields, native handle, context and ModuleRole generation.
2. Acquire exact ModuleRole admission/reference and context reference. Reject if the role is QUIESCING/retired.
3. Copy the ops structure and each typed sub-table into server-owned immutable storage. Validate all required function pointers and all capability-to-operation consistency. No partial table is publishable.
4. Canonicalize identity using authoritative bus/sysfs/DRM evidence, primary/render-node correlation, UUID corroboration and stable DDX-scoped instance identity as specified. Never derive BDF from vendor ID, device ID, API version or driver version.
5. Resolve duplicate/ambiguous identity. Exact duplicate evidence may be idempotent only if it resolves to the same physical incarnation and compatible exact binding ownership. Conflicting contexts/handles/ops/snapshots are never merged and never treated as unconditional success. Ambiguous identity stays unpublished.
6. Allocate a provisional binding generation and call `query_physical_snapshot` through this exact binding. Initialize outputs to failure sentinels; validate all returned fields, pointer/count pairs, ranges, UUID presence, queue/memory consistency and advertised features. Deep-copy into server-owned snapshot storage.
7. Allocate a server-owned XID and prepare the DIX resource wrapper. No XID is visible to enumeration/request lookup yet.
8. Call `AddResource()` exactly once. Only after success link/publish the PhysicalDevice in the registry and make its snapshot/binding visible atomically in the server serialization domain.
9. Return the opaque PhysicalDevice pointer as the non-NULL success result. Do not transfer a long-lived bare-pointer reference to the DDX.

Any failure before publication unwinds all provisional state and references. There is no published object for a partially copied snapshot, missing operation, invalid identity, failed AddResource, or failed callback. The DIX resource destructor is the single canonical published-object destruction path and unlinks the registry entry itself.

## 4. ModuleRole and ScreenAttachment are separate

- `GpuModuleRole`/ModuleRole is a shared lifetime/admission/quiescence control record only. It pins module code and shared module resources. It is not a per-device context or dispatch proxy.
- A ModuleRole may be shared by many PhysicalDevice bindings. Each binding separately stores its native handle and per-device context.
- A `ScreenAttachment` is a separate, non-owning, generation-checked relation between an Xorg Screen generation and a PhysicalDevice generation.
- Screen close detaches only its exact ScreenAttachment. It MUST NOT unregister or destroy a PhysicalDevice binding merely because the binding was discovered through that Screen.
- DDX-wide discovery/registration happens before Screen creation and is independent of Screen, ScrnInfo, RandR, outputs and connectors.

## 5. Implementation phases and gates

### Phase 0 — rollback and clean baseline
- Reset `wip/xaverius` to `f6f3e87...` using force-with-lease.
- Verify the exact branch tip and seven-file Xaverius source list.
- Build the untouched baseline in the existing CI matrix and save the baseline result.
- Do not cherry-pick any registry/inventory implementation commits.

**Gate:** exact branch SHA and clean baseline build recorded.

### Phase 1 — freeze types and DDX-facing API (no registry implementation yet)
- Add only the type/API declarations needed for identity, the snapshot member of PhysicalDevice, const PhysicalDeviceOps, binding, ModuleRole and registration descriptor. Keep one canonical PhysicalDevice representation; do not add a parallel DeviceCaps/PhysicalDeviceInfo object.
- Keep `XaveriusDDXOps` limited to Screen-local `ScreenInit/ScreenFini`; do not re-add physical-device enumeration/property callbacks there.
- Define all forward declarations and ownership contracts in one canonical header. Avoid duplicate internal PhysicalDevice or info records.
- Add ABI size/version checks and compile-time layout checks where appropriate.
- Do not add a registry list, DIX resource, request path or modesetting callback in this phase.

**Gate:** type diagram, header dependency graph, ABI/version behavior, and API review approved before implementation.

### Phase 2 — ModuleRole and callback lifetime substrate
- Implement one ModuleRole per loaded DDX role/generation with real module lease, callback admission, reference counting and quiescence.
- Do not use `DriverPtr.refCount`, Screen lifetime or a raw ModuleDesc pointer as the only module pin.
- Provide idempotent, generation-scoped `quiesce_module_role` with PENDING/SUCCESS/FAILURE semantics.
- Keep module-wide operations separate from PhysicalDeviceOps.
- Add unload tests before any driver callback is registered.

**Gate:** module cannot unload while any registered operation pointer, context callback, worker or async completion can reach it; uncertain quiescence quarantines.

### Phase 3 — registry core and identity
- Implement one process-wide registry service, independent of Screen and DDX instance.
- Implement canonical identity and incarnation logic from the normative evidence hierarchy.
- Distinguish platform identity observations from executable DDX registrations; platform/udev alone never publishes a device.
- Implement duplicate/ambiguous/conflicting identity behavior and deterministic selected-binding policy for v0.1.
- Serialize all mutations in the server event/main-thread domain.
- No protocol request integration yet.

**Gate:** unit tests for PCI/non-PCI identity, primary/render aliases, multiple DDX observations, conflicting UUIDs, stable virtual identity, removal/re-add incarnation and stale generations.

### Phase 4 — complete registration and snapshot publication
- Implement `XaveriusRegisterPhysicalDevice` with mandatory `const XaveriusPhysicalDeviceOps *` in the registration descriptor and an opaque `PhysicalDevice *` success / NULL failure result. Keep the XID entirely server-private.
- Validate and copy all operation tables before publication.
- Obtain snapshot only through the exact binding's `query_physical_snapshot`.
- Publish via one DIX AddResource after every fallible preparation step; link registry only after AddResource success.
- Destructor removes registry membership and releases snapshot, binding, context and role references exactly once.
- Shutdown removes published resources through the DIX path; never directly frees still-published records.
- Register all devices in one transaction per device, including headless/render-only/compute-only/no-Screen devices.

**Gate:** allocation/failure injection at every step, duplicate ownership tests, DIX destructor/shutdown tests, no leaks/dangling refs/double-free, exact AddResource count one.

### Phase 5 — DDX-wide discovery integration
- Add a safe DriverRec-level callback seam or equivalent core-owned registration API. Do not append an unchecked function pointer to DriverRec; use a validated size/version ABI or explicit ABI bump with loader rejection.
- Invoke each configured DDX enumeration pass exactly once per ModuleRole generation; callback result must distinguish COMPLETE, PENDING, UNAVAILABLE and FAILED.
- Subscribe to hotplug observation before initial DDX scans; reconcile queued events and generations before opening the initial discovery barrier.
- Modesetting enumerates only devices actually served by its DDX context. Use canonical DRM/sysfs enumeration and primary/render correlation; never scan hard-coded `renderD0..31` or invent node numbers.
- No registration from `PreInit`, `ScreenInit`, connector checks, first Screen, or first GPU. No global `/dev/dri` candidate scan as a substitute for DDX ownership.
- The DDX calls RegisterPhysicalDevice once per candidate and passes the matching PhysicalDeviceOps, handle, context, identity and ModuleRole.
- If modesetting cannot produce a no-Screen executable binding, report UNAVAILABLE/BLOCKED and publish nothing; do not fake a binding or defer Phase-A registration to Phase B.

**Gate:** tests for zero/one/multiple devices per DDX, two DDX modules, no Screen, headless, render-only, non-contiguous render node IDs, primary/render aliases, PENDING completion, hotplug race and once-only callback.

### Phase 6 — query/request integration
- PhysicalDevice enumeration and static property queries read the immutable registry snapshot only.
- Resolve XIDs through typed DIX resource lookup; preserve normative error precedence for unknown XID, wrong type, unavailable, removed and unsupported property.
- No client request may trigger discovery, call the DDX for static properties, or lazily materialize the registry.
- Logical Device creation resolves and pins the exact PhysicalDevice/binding generation.
- Remove all fabricated capability defaults and placeholder UUIDs.
- Keep server-only requests separate from backend operations.

**Gate:** wire/conformance tests across AVAILABLE/UNAVAILABLE/REMOVED, wrong resource types, XID reuse, status transitions and no-backend-call assertions for snapshot queries.

### Phase 7 — ScreenAttachment and teardown
- Attach each Screen generation explicitly to all relevant already-registered PhysicalDevices with roles.
- Screen close detaches only that ScreenAttachment generation.
- DDX unload closes admission, detaches topology, withdraws exact binding, drains async operations, waits for callback/worker quiescence, then releases context and module lease.
- If quiescence cannot be proven, quarantine and retain code/context.
- Server shutdown uses one canonical registry/DIX destruction order.

**Gate:** multi-screen/multi-GPU tests, Screen close with live logical Device, DDX unload with callbacks pending, stale generation callbacks, module quarantine and server shutdown.

### Phase 8 — later backend operations (only after registry acceptance)
- Implement the four typed operation tables and top-level PhysicalDeviceOps callbacks according to `spec/provider-operation-matrix.md`.
- Exactly six asynchronous operations use operation tokens: WriteBuffer, ReadBuffer, host SignalSemaphore, QueueSubmit, AcquireNextImage and QueuePresent.
- Every persistent backend object has matching typed destruction.
- No handler may return SUCCESS without actual backend work.
- Do not start this phase until Phases 0–7 pass independent review and the registry/discovery phase is explicitly accepted.

**Gate:** full operation-matrix conformance and exact-tip Xserver CI.

## 6. Required tests and evidence

Every phase report must include repository, branch, full commit and parent SHA; files changed; exact symbols/call sites; exact commands and exit codes; PASS/FAIL/BLOCKED per test; and remaining blockers.

Mandatory tests include:

- versioned `const PhysicalDeviceOps` descriptor: old/small struct, wrong ABI, truncated typed table, NULL required callback; verify the DDX cannot access or allocate the PhysicalDevice XID;
- const operation-table immutability after registration and module code pinning; verify returned PhysicalDevice pointer is opaque, non-retainable by DDX contract, and NULL for duplicate/conflicting identity;
- multiple devices sharing one ModuleRole but distinct native handles and contexts;
- context retain/release balance for success, every failure, exact duplicate, conflict, withdrawal and shutdown;
- snapshot query callback receives the exact binding; snapshot failure leaves no XID;
- duplicate/ambiguous identity never merges operations/context/snapshot;
- AddResource called once; injected failure leaves no list/resource/XID publication;
- destructor and RegistryFini cannot double-free or leave stale list pointers;
- module quiescence PENDING/SUCCESS/FAILURE and quarantine;
- subscribe-before-scan event ordering, queued event reconciliation and initial barrier;
- modesetting primary/render correlation with non-contiguous node numbers;
- no-Screen and no-output devices are registered independently of Screen creation;
- Screen close does not unregister a PhysicalDevice;
- all server-only queries avoid DDX backend entry;
- all async callbacks carry token ID/generation and exact binding/ModuleRole generations.

A green spec CI is not evidence that Xserver code compiles or works. Run the full Xserver portability/SDK build matrix against the exact final commit.

## 7. Explicitly forbidden shortcuts

- No Provider object, Provider candidate list, Provider ranking or Provider callback alias.
- No capabilities-only registration API.
- No PhysicalDeviceOps omitted from registration or deferred to Phase B.
- No identity synthesized from vendor/device/API/driver versions.
- No Screen/ScrnInfo/Entity as registry ownership root.
- No first-Screen/first-GPU selection or output/connector-gated inventory.
- No global `/dev/dri` scan or guessed render-node number range.
- No generic void-pointer operation dispatcher or raw wire buffer callback.
- No unchecked DriverRec tail-member access.
- No second AddResource, pre-publication DIX visibility, or direct free of published resources.
- No direct ModuleRole context getter or ModuleRole dispatch proxy.
- No Phase-B handler that returns success without a real typed backend operation.
- No cosmetic renames, broad reformatting or unrelated source cleanup.

## 8. Normative references

- `spec/device-registry-architecture.md` — PhysicalDevice, binding, identity, DDX registration, ModuleRole, ScreenAttachment, publication barrier and lifetime.
- `spec/registry-api-lifetime-addendum.md` — direct DDX binding and lifetime semantics.
- `spec/provider-operation-matrix.md` — exact typed operation tables, sync/async classification, completion and destroy contracts.
- `implementation-notes/ddx-device-registration.md` — Xlibre/Xorg integration and per-device binding ownership.
- `implementation-notes/phase-a-ddx-discovery.md` and `phase-a-ddx-corrections.md` — existing detailed DDX discovery requirements; this rebuild plan supersedes their assumption that the current registry implementation is reusable.
