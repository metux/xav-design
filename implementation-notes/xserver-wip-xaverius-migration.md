# Xlibre Xserver migration plan: direct DDX PhysicalDevice bindings

**Target implementation:** `X11Libre/xserver:wip/xaverius`  
**Source baseline audited:** `ba88b49433de7c202d6a977887729b4aebb4163c`  
**Normative authority:** `spec/device-registry-architecture.md`, `spec/registry-api-lifetime-addendum.md`, and `spec/provider-operation-matrix.md` on `metux/xav-design:docs/restructure-2026-10-21`.

This is a staged migration plan, not a replacement for the normative spec. Exact Xserver DIX resource and driver-lifecycle API signatures must be checked against the target tree before coding; the semantic contracts below are mandatory.

## Target model

Keep the process-wide registry introduced in the latest push. Each published PhysicalDevice owns canonical identity/incarnation, immutable property/memory/queue-family snapshot, status, server-owned XID/resource, and exactly one selected DDX binding in v0.1.

The selected binding is the only dispatch target and directly contains:
- exact native/DDX-local physical-device handle;
- retained per-device context (or explicitly retained shared DDX context);
- immutable typed operation-vector pointers;
- registry-assigned, non-reusable binding generation;
- retained ModuleRole generation/reference and binding lifetime state.

A shared ModuleRole is only a code/module lease, callback-admission and quiescence control record. It is not a provider object, per-device context, or dispatch proxy. ScreenAttachment is a separate, non-owning Screen-generation ↔ PhysicalDevice-generation relation.

## Ordered migration

### 1. Split DDX-wide discovery from Screen setup

Files: `xaverius_priv.h`, `xaverius_screen.c`, DDX integration call sites.

- Keep `XaveriusScreenInit` for Screen-local setup only.
- Remove `EnumeratePhysicalDevices`, `GetPhysicalDeviceProperty`, and `GetPhysicalDeviceQueueFamilyProperties` from `XaveriusDDXOps`; these are not Screen callbacks.
- Add a DDX registration entry point invoked once the DDX backend is initialized, independently of Screen creation. The DDX must register every served device, including headless, render-only, compute-only, and Screen-unattached devices.
- Do not invoke discovery from client requests or iterate `screenInfo.screens` to construct the device inventory.
- Add separate attach/detach operations for exact Screen and PhysicalDevice generations plus roles. One Screen may attach to several devices; several Screens may attach to one device.

The exact Xorg hook must be chosen from the actual DDX probe/init/unload path. Extension initialization alone cannot enumerate a DDX's devices before that DDX supplies its backend.

### 2. Separate immutable snapshot from executable binding

Files: `xaverius_priv.h`, `xaverius_intern.h`, registry implementation.

- Rename `XaveriusProviderCapabilities` to a snapshot-only type (e.g. `XaveriusPhysicalDeviceSnapshot`). Remove the opaque provider handle from it.
- Delete `XaveriusProviderCallbacks`; it is currently only a typedef alias of the snapshot and is not an operation table.
- Define immutable typed operation tables grouped according to the spec matrix: logical-device, buffer/memory, shader/pipeline, descriptors, commands, synchronization, and presentation.
- Define a per-device binding carrying the native handle, device context, operation tables, binding generation, and retained ModuleRole generation/reference.
- Do not add a generic ModuleRole context getter. Every operation must dispatch with the exact binding's context and handle.

### 3. Replace registration with an atomic per-device transaction

Files: `xaverius_registry.h`, `xaverius_registry.c`, `xaverius_intern.h`.

Replace `XaveriusRegisterDevice(identity, callbacks)` with a complete registration semantic equivalent to `GpuRegistryRegisterDdxDevice`. Input: structured identity evidence, exact native handle, per-device context, immutable typed operations, and owning ModuleRole generation.

Transaction order:
1. validate arguments and retain context/module/table lifetime;
2. canonicalize identity and resolve the exact incarnation;
3. reserve a non-reusable binding generation;
4. validate all operations required by advertised capabilities;
5. obtain the complete immutable snapshot through this exact binding;
6. allocate server XID and insert the typed DIX resource;
7. publish atomically and return one caller-owned reference plus device/binding generations.

Every failure unwinds exactly the references acquired by the transaction and leaves no published entry or XID. Duplicate identity is not an update: never overwrite a published binding or snapshot. Ambiguous/conflicting claims remain unpublished; v0.1 has no post-publication transparent failover.

Identity matching must follow the spec evidence hierarchy (canonical platform/sysfs identity, DRM primary/render equivalence, corroborating UUIDs, derived-device instance identity, DDX-scoped fallback). A simple PCI+UUID equality test is insufficient.

### 4. Make PhysicalDevice XIDs real DIX resources

Files: `xaverius_registry.c`, `xaverius_device.c`, `init.c`.

- Register a server-owned resource wrapper for each published PhysicalDevice using the established DIX resource APIs in this tree.
- Replace request-path private-list XID scans with typed resource lookup and normative error precedence.
- PhysicalDevice XIDs survive client disconnect. The resource destroy callback invalidates lookup at the required point but defers object/binding reclamation while logical Devices, backend objects, synchronous calls, operations, or callbacks retain references.
- Resource insertion/XID allocation failure must roll back publication atomically.

Do not guess DIX function signatures; inspect the Xserver's existing resource patterns and mirror their ownership/error handling.

### 5. Convert current requests to snapshot semantics

Files: `xaverius_device.c`, `dispatch.c`.

- Enumerate the registry inventory in stable order, including retained UNAVAILABLE entries and REMOVED tombstones. Do not filter to AVAILABLE only.
- Property and queue-family queries use the immutable snapshot; no DDX or Screen callback is called for these static queries.
- Keep identity existence separate from availability. An unavailable/removed retained device is not an unknown XID.
- Apply property-specific status mapping; do not collapse all non-AVAILABLE cases into `BadMatch`.
- Remove placeholder UUID zero-fill and fabricated defaults (e.g. 256). Return validated snapshot values or the normative status.
- Distinguish unknown XID, wrong resource type, unavailable device, unsupported property, and backend contract failure per request chapters/error map.

### 6. Make ScreenAttachment independent

Files: `xaverius_screen.c` and DDX Screen integration.

- Screen init attaches to already registered PhysicalDevices explicitly identified by the DDX.
- Screen close detaches only the exact attachment generation.
- Screen close never unregisters a PhysicalDevice or releases its shared DDX/module context.
- Failed Screen initialization unwinds only attachments created by that attempt.

### 7. Integrate hotplug, unload, and shutdown

Files: `xaverius_registry.c`, `xaverius_screen.c`, `init.c`, DDX lifecycle integration.

- Wire registry shutdown into the real server shutdown path; `XaveriusExtensionFini` must not remain empty if it owns initialization.
- DDX unload closes registration/callback admission, detaches its ScreenAttachments, withdraws exact bindings/observations, drains accepted operations and backend objects, waits for callback quiescence, and releases context/module lease last.
- Binding removal affects one PhysicalDevice; ModuleRole shutdown drains all bindings owned by that role.
- Async callbacks use server-owned token ID/generation plus binding/module-role generations. No raw Xserver object pointer or retained opaque token pointer crosses the async boundary.
- If future backend access cannot be excluded, quarantine and retain the binding/context/module rather than freeing reachable code or handles.

## Current source map and disposition

| Current construct at baseline | Migration |
|---|---|
| `XaveriusProviderCapabilities` | Snapshot-only type; remove provider handle |
| `XaveriusProviderCallbacks` alias | Delete |
| `XaveriusDevice.callbacks` | Replace with direct selected binding + immutable snapshot |
| `XaveriusRegisterDevice(identity, callbacks)` | Complete per-device DDX registration transaction |
| Screen-scoped enumerate/property/queue callbacks | Remove from Screen ops |
| `XaveriusScreenInit` | Screen setup + ScreenAttachment only |
| process-global device list | Keep as registry implementation detail |
| `XaveriusFindDeviceByXid` scan | Replace in request paths with typed DIX resource lookup |
| `XaveriusRegistryFini` | Integrate into ordered server shutdown |
| empty `XaveriusExtensionFini` | Wire correct teardown path |

## Acceptance gates

Test at least:
- one DDX registers zero/one/multiple devices without any Screen;
- one Screen ↔ multiple devices and multiple Screens ↔ one device;
- distinct handle/context dispatch for multiple devices sharing one ModuleRole;
- duplicate, ambiguous, conflicting, and late duplicate identity (no rebinding);
- incomplete operation table/snapshot failure (no partial XID/publication/leak);
- XID/resource insertion failure at every publication stage;
- enumeration and static property queries for AVAILABLE, UNAVAILABLE, REMOVED;
- wrong DIX resource type versus unknown XID;
- Screen close while Device/operation references remain;
- DDX unload with pending callbacks and quarantine on uncertain quiescence;
- stale device/binding/module-role generations and XID reuse;
- server shutdown with pending registration, attachment, and operation retirement.

A successful wire-layout CI run in xav-design does not validate this Xserver implementation; run the Xserver build and relevant runtime/conformance tests after each source phase.

## Out of scope

Do not add an independent Vulkan-ICD candidate inventory, provider ranking layer, per-Screen PhysicalDevice inventory, first-Screen default selection, or weaken operation-token/module-lease requirements. Do not change wire ABI as part of this internal migration without a separate spec review.
