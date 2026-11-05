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

One `GpuDeviceBackendBinding` (or equivalent internal record) is the direct dispatch target for the exact PhysicalDevice. It contains:

- exact DDX-native PhysicalDevice handle;
- exact per-device backend context;
- an immutable, server-owned copy of the supplied `GpuDeviceBackendOps` descriptor and its four typed sub-tables;
- a non-reusable binding generation;
- a retained reference to the owning `GpuModuleRole` generation;
- binding state, call admission, in-flight synchronous-call count and async-token references.

The PhysicalDevice has one selected binding for v0.1 dispatch. Other complete eligible registrations may remain unselected while deterministic selection is unresolved; their operation tables, contexts and snapshots are never merged. No dispatch proxy, Provider layer, candidate-ranking object, generic ModuleRole context accessor, or Screen-private dispatch route is permitted.

### 2.4 DDX operation descriptor — mandatory registration input

The DDX MUST pass a matching `const GpuDeviceBackendOps *` through `GpuDeviceBackendRegistration` for **each** registered PhysicalDevice. This is not optional and cannot be deferred to a later phase. The authoritative descriptor and callback signatures are defined by `spec/device-registry-architecture.md` and the four typed tables in `spec/provider-operation-matrix.md`; this plan MUST NOT define a competing callback structure or signature sketch.

The top-level descriptor begins with `struct_size` and `abi_version`. For v0.1, `struct_size` MUST equal `sizeof(GpuDeviceBackendOps)` and `abi_version` MUST equal `GPU_DEVICE_BACKEND_OPS_ABI_VERSION`. The ABI version governs the layouts of all four nested typed tables and all DDX-facing callback signatures and parameter/result structures; the nested tables do not have independent version fields. The registry validates this header before reading any callback field, then validates and copies the complete top-level and nested descriptors by value into immutable binding-owned storage. A size mismatch is `INVALID_ARGUMENT`; an unknown ABI version is `UNSUPPORTED`. Neither failure may invoke a callback or retain the supplied handle, context, or module-role reference.

Every callback target MUST remain executable while the exact owning ModuleRole lease is pinned. Module-wide lifecycle callbacks are not per-device operations: registration, callback admission, quiescence and module lifetime release belong to the separate `GpuModuleRoleDescriptor`/ModuleRole control record. Do not duplicate module-wide quiescence callbacks in `GpuDeviceBackendOps`.

### 2.5 Registration descriptor and ownership

The normative entry point is:

```c
GpuRegistryResult GpuRegistryRegisterDdxDevice(
    GpuRegistry *registry,
    const GpuDeviceBackendRegistration *registration,
    GpuPhysicalDevice **out_device,
    uint64_t *out_device_generation,
    uint64_t *out_binding_generation);
```

The v1 `GpuDeviceBackendRegistration` begins with exact `struct_size` and `abi_version` fields, followed by structured `GpuDeviceIdentity` evidence, the exact native PhysicalDevice handle, the exact per-device context, the versioned `const GpuDeviceBackendOps *`, the owning `GpuModuleRole *`, and its exact generation. The `GpuModuleRoleDescriptor` passed during role registration is independently size/version checked before the registry retains the supplied module-lease reference. The registry canonicalizes identity, reserves a non-reusable provisional binding generation, validates the descriptor and operation tables, obtains the complete immutable snapshot through that exact binding, and installs the binding atomically.

On `SUCCESS`, the API returns one caller-owned canonical PhysicalDevice reference and the exact PhysicalDevice/binding generations. This does **not** guarantee publication or an XID: publication is a separate `XaPhysicalDevicePublish` operation after identity resolution, eligible-binding selection and opening of the startup publication gate. The DDX MUST release the immediate caller-owned PhysicalDevice reference through `GpuPhysicalDeviceRelease` and MUST NOT retain or later dereference the bare pointer. Exact idempotent replay of the same live registration returns the same binding generation and one additional caller-owned PhysicalDevice reference; conflicting registration data returns a classified failure and never merges bindings or snapshots.

The native handle and per-device context are borrowed DDX-owned opaque values, not transferred or freed by the registry. The DDX MUST keep them valid and immutable until exact binding removal has completed and all dependent calls, logical Devices, backend objects, operation tokens and callbacks have retired. The registry retains the owning ModuleRole reference and its module lease according to the normative lifetime contract. There are no context retain/release callbacks in this API. On every failed registration, no binding or caller-owned PhysicalDevice reference is returned, no XID is published, and all references acquired by the registry are rolled back; explicitly reserved non-reusable generations remain consumed.

## 2.6 Source-tree discipline and atomic commit rules

These rules apply to every implementation phase and are mandatory review criteria, not style suggestions.

### Commit boundaries

- Every commit MUST represent one coherent, independently reviewable change with one purpose. Keep commits small and atomic; do not mix unrelated subsystems or lifecycle topics.
- PhysicalDevice type/API declaration, PhysicalDevice registration/publication, ScreenAttachment relationships, DDX discovery, modesetting integration, protocol request handlers, and backend operation implementations are separate topics and MUST be committed separately when they can be separated without breaking the build.
- In particular, any change under `hw/xfree86/drivers/modesetting/` MUST be a separate commit from the generic Xaverius registry/core change. A modesetting commit must explain why the change is needed, its DDX-specific behavior, and its dependencies.
- Changes to Xserver core lifecycle files (for example `xf86Bus.c`, `xf86Init.c`, config/udev, or public headers) require their own narrowly scoped commit with a concrete rationale and explicit ABI/lifecycle impact. Do not sneak such changes into a registry commit.
- If a topic needs a prerequisite, commit the prerequisite separately first. Each commit must build and pass the relevant tests at its own boundary; if an intermediate state cannot build, explain why and keep the indivisible series as short as possible.
- Do not squash unrelated work into a large “Phase 1/2 implementation” commit. Commit messages state the subsystem/topic and behavioral intent, not merely “fix”, “cleanup” or “implementation”.

### Preserve existing source style and structure

- Do not reformat untouched code. No gratuitous line wrapping, moving return types/function names onto separate lines, whitespace churn, header blank-line changes, or unrelated comment edits.
- Preserve existing license headers exactly, including copyright/license text and placement. Every new source/header file must use the repository's correct license header and end with a newline.
- Preserve the existing two header scopes and their include guards/contracts. Do not move declarations between the server-internal and extension-private headers merely for convenience; add declarations to the correct existing scope. Do not create extra headers unless a genuinely separate public/internal interface requires one and the need is documented.
- Do not add an `xaverius_` prefix to extension-internal source filenames. Existing externally includable header names are the exception and must retain their established names.
- Follow the naming convention already used in the relevant scope. Do not mix camel/Pascal case and underscore naming styles or rename existing symbols without a necessary API reason and a separate explanation.
- Do not duplicate existing initialization, protocol definitions, request/reply structures, or dispatch registration. Extend the existing init path and existing protocol declarations. No new monolithic `xaverius.c` or equivalent aggregation file that duplicates `init.c` responsibilities.
- Do not introduce X11 Proc/SProc handlers, protocol opcodes, or request/reply implementations before their assigned phase/request group. When request handlers are added, follow the current dispatch architecture: do not resurrect legacy per-request SProc/rpcbuf patterns; use the repository's current request/reply macros and byte-order handling.
- Do not add speculative or convenience `#include` directives. Include only what the translation unit actually needs.

### Include ordering and path rules

For each source/header, preserve this order, with no unnecessary additions:
1. `dix-config.h` first where required by the Xserver build;
2. system headers;
3. Xserver-wide headers, using canonical include paths (for example `include/resource.h`, not a shortened or accidental local path);
4. the existing Xaverius extension headers.

Keep groups sorted consistently with surrounding repository convention. Do not reorder unrelated includes.

### Public SDK and ABI protection

- Treat every header under `include/` as public SDK/driver ABI unless proven otherwise. Do not add fields to public structs, change layout, alter function signatures, or expose internal PhysicalDevice/XID details without an explicit ABI review.
- Prefer extension-private declarations and opaque handles. If a public ABI change is unavoidable, isolate it in its own commit, document compatibility/versioning and loader behavior, and provide old-binary compatibility tests. Never append a callback to a public struct and read it from old binaries without a validated size/version gate.
- No driver-visible declaration may expose the PhysicalDevice XID or DIX resource wrapper.

### Review checklist for every commit

The commit description/review must state: (1) its single topic and why it is independently scoped; (2) exact files/subsystems touched; (3) dependencies on earlier commits; (4) build/test commands and results; (5) any intentional ABI or lifecycle effect. Reject commits with unrelated formatting, speculative headers/includes, premature request handlers, duplicate init/protocol definitions, or unreviewed public SDK changes.

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
- Implement `GpuRegistryRegisterDdxDevice` with the mandatory versioned `const GpuDeviceBackendOps *` in `GpuDeviceBackendRegistration`; on SUCCESS return the immediate caller-owned PhysicalDevice reference and exact generations, but do not equate registration success with publication. Keep the XID entirely server-private.
- Validate the top-level size/ABI version before reading callback fields, then validate and copy all operation tables before installing the binding.
- Obtain the snapshot only through the exact binding's `query_physical_snapshot`; snapshot/binding installation is separate from publication.
- After identity resolution, eligible-binding selection and opening the startup publication gate, publish through `XaPhysicalDevicePublish`: XID allocation and one DIX AddResource insertion are one transaction; expose no published state if insertion fails.
- The DIX destructor retires public XID/resource membership; internal snapshot, binding, context and role references are released only after all dependent internal references have retired.
- Shutdown removes published resources through the DIX path; never directly frees still-published records.
- Register all devices in one transaction per device, including headless/render-only/compute-only/no-Screen devices.

**Gate:** allocation/failure injection at every step, duplicate ownership tests, DIX destructor/shutdown tests, no leaks/dangling refs/double-free, exact AddResource count one.

### Phase 5 — DDX-wide discovery integration
- Add a safe DriverRec-level callback seam or equivalent core-owned registration API. Do not append an unchecked function pointer to DriverRec; use a validated size/version ABI or explicit ABI bump with loader rejection.
- Invoke each configured DDX enumeration pass exactly once per ModuleRole generation; callback result must distinguish COMPLETE, PENDING, UNAVAILABLE and FAILED.
- Subscribe to hotplug observation before initial DDX scans; reconcile queued events and generations before opening the initial discovery barrier.
- Modesetting enumerates only devices actually served by its DDX context. Use canonical DRM/sysfs enumeration and primary/render correlation; never scan hard-coded `renderD0..31` or invent node numbers.
- No registration from `PreInit`, `ScreenInit`, connector checks, first Screen, or first GPU. No global `/dev/dri` candidate scan as a substitute for DDX ownership.
- The DDX calls `GpuRegistryRegisterDdxDevice` once per served candidate and passes the matching `GpuDeviceBackendRegistration`, versioned `GpuDeviceBackendOps`, native handle, context, identity and ModuleRole.
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
- Implement the four typed operation tables and top-level `GpuDeviceBackendOps` callbacks according to `spec/provider-operation-matrix.md`.
- Exactly six asynchronous operations use operation tokens: WriteBuffer, ReadBuffer, host SignalSemaphore, QueueSubmit, AcquireNextImage and QueuePresent.
- Every persistent backend object has matching typed destruction.
- No handler may return SUCCESS without actual backend work.
- Do not start this phase until Phases 0–7 pass independent review and the registry/discovery phase is explicitly accepted.

**Gate:** full operation-matrix conformance and exact-tip Xserver CI.

## 6. Required tests and evidence

Every phase report must include repository, branch, full commit and parent SHA; files changed; exact symbols/call sites; exact commands and exit codes; PASS/FAIL/BLOCKED per test; and remaining blockers.

Mandatory tests include:

- versioned `const GpuDeviceBackendOps` descriptor: NULL pointer, undersized/oversized v1 structure, unknown ABI version, and NULL required callback; verify no callback is entered and no binding/reference/XID is published on failure;
- operation-table immutability after registration and module code pinning; verify the returned PhysicalDevice pointer is opaque and only immediately caller-owned, exact idempotent registration replay returns one additional reference, and conflicting registration is rejected;
- multiple devices sharing one ModuleRole but distinct native handles and contexts;
- DDX-owned handle/context validity through exact binding removal and all dependent-reference retirement; verify the registry never frees those borrowed values;
- snapshot query callback receives the exact provisional binding; failed registration leaves no binding or XID, and successful registration remains unpublished until the separate publication gate opens;
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
- No `GpuDeviceBackendOps` omitted from registration or deferred to a later phase.
- No identity synthesized from vendor/device/API/driver versions.
- No Screen/ScrnInfo/Entity as registry ownership root.
- No first-Screen/first-GPU selection or output/connector-gated inventory.
- No global `/dev/dri` scan or guessed render-node number range.
- No generic void-pointer operation dispatcher or raw wire buffer callback.
- No unchecked DriverRec tail-member access.
- No second AddResource, pre-publication DIX visibility, or direct free of published resources.
- No direct ModuleRole context getter or ModuleRole dispatch proxy.
- No request/backend handler that returns success without a real typed backend operation.
- No cosmetic renames, broad reformatting or unrelated source cleanup.

## 8. Normative references

- `spec/device-registry-architecture.md` — PhysicalDevice, binding, identity, DDX registration, ModuleRole, ScreenAttachment, publication barrier and lifetime.
- `spec/registry-api-lifetime-addendum.md` — direct DDX binding and lifetime semantics.
- `spec/provider-operation-matrix.md` — exact typed operation tables, sync/async classification, completion and destroy contracts.
- `implementation-notes/ddx-device-registration.md` — Xlibre/Xorg integration and per-device binding ownership.
- `implementation-notes/phase-a-ddx-discovery.md` and `phase-a-ddx-corrections.md` — existing detailed DDX discovery requirements; this rebuild plan supersedes their assumption that the current registry implementation is reusable.
