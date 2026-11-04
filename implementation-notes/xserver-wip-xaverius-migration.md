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

### 1. Phase A — DDX-wide discovery, independent of ScreenInit

**Agent task: implement Phase A only.** Do not start the typed binding, ModuleRole, DIX-resource, request-status, or unload redesign in this phase. Those are later phases with separate interfaces and acceptance gates.

**Audited source baseline:** `X11Libre/xserver:wip/xaverius`, current reviewed files:
- `Xext/xaverius/xaverius_priv.h`: `XaveriusDDXOps` still mixes `ScreenInit`/`ScreenFini` with three PhysicalDevice enumeration/property callbacks.
- `Xext/xaverius/xaverius_screen.c`: `XaveriusScreenInit()` allocates a per-Screen record and installs a close hook; this is the correct place for Screen-local setup/cleanup only.
- `Xext/xaverius/xaverius_device.c`: client requests still rely on Screen callbacks / screen-local discovery semantics. They must no longer trigger device discovery.
- `Xext/xaverius/xaverius_registry.c`: process-wide registry exists, but currently receives devices through the old callback path.
- `hw/xfree86/drivers/video/modesetting/driver.c`: driver lifecycle has distinct `Probe()`, `ms_platform_probe()`/`ms_pci_probe()`, `PreInit()`, `ScreenInit()`, and `FreeScreen()` stages. `PreInit()` obtains the DRM fd; `ScreenInit()` is too late and too Screen-specific for inventory ownership. The correct registration hook must be chosen after inspecting the actual DDX device enumeration and backend-handle readiness, not by assuming one hook fits every DDX.

**Required code changes:**

1. Reduce `XaveriusDDXOps` to Screen-local callbacks only (`ScreenInit`, `ScreenFini`, and any strictly Screen-local hooks already needed). Remove `EnumeratePhysicalDevices`, `GetPhysicalDeviceProperty`, and `GetPhysicalDeviceQueueFamilyProperties` from this structure. Do not replace them with differently named Screen callbacks.
2. Introduce a distinct DDX-wide discovery/registration lifecycle entry point. It must be callable by the DDX without a `ScreenPtr`, `ScrnInfoPtr`, or an existing XAverius Screen-private record. Its contract is to enumerate the complete set of PhysicalDevices served by that DDX instance and submit each device to the server-wide registry. The exact function signature may be coordinated with Phase B's direct-binding API, but it must not reintroduce a Provider object or a registry-side candidate/ranking list.
3. Invoke that entry point from the DDX's device/backend initialization path once the exact device handle and context required for registration exist, and before any dependency on XAverius ScreenInit. The call must also cover devices that do not produce an X screen. If a DDX cannot enumerate until a later stage, document that stage and ensure it is still independent of Screen creation; do not silently fall back to ScreenInit.
4. Registration must be idempotent for the same DDX/device incarnation. Repeated calls caused by multiple ScrnInfo records, primary/render-node aliases, or multi-screen configuration must not create duplicate published devices or overwrite an existing binding. Identity resolution and duplicate-claim policy remain governed by the normative registry spec; Phase A must not invent a local alternative.
5. Remove all lazy discovery from `ProcXaveriusEnumeratePhysicalDevices`. The request handler must only serialize the already-published global inventory. It must not walk `screenInfo.screens`, call DDX enumeration callbacks, or cause registration side effects.
6. Keep `XaveriusScreenInit()` and its close hook strictly Screen-local. Screen close may clean up its Screen private and later detach its exact ScreenAttachment; it must not unregister a PhysicalDevice or release a DDX-wide discovery context.
7. Add a minimal DDX integration for the existing modesetting driver as a concrete exercise of the interface, if that driver is the intended XAverius-capable DDX in this branch. The integration must distinguish DRM device discovery from Screen allocation: a render-only/compute-only device must still be eligible even if it has no connectors and no GPU Screen. Do not make XAverius registration conditional on `check_outputs()`, `xf86AllocateScreen()`, or successful ScreenInit.
8. Document the DDX-instance lifetime and the event that ends its discovery admission. Do not implement the full asynchronous unload/quiescence protocol here; preserve the later Phase G requirement and avoid freeing any context that registration currently borrows.

**Required deliverables from the agent:**
- code implementing the new DDX-wide entry point and removing the three callbacks from `XaveriusDDXOps`;
- one concrete DDX call site, with a short source comment explaining why it is independent of Screen creation;
- updated headers/call sites and removal of obsolete lazy Screen enumeration;
- focused tests or a test harness proving discovery with zero Screens, one DDX with multiple devices, and repeated invocation without duplicate publication;
- a short report in `IMPLEMENTATION_COORDINATION.md` giving repository, branch, commit, touched files, exact build/test commands, results, and unresolved lifecycle assumptions.

**Phase A acceptance criteria:**
- A DDX can register zero, one, or multiple PhysicalDevices without creating any Screen.
- A headless/render-only/compute-only PhysicalDevice is not omitted merely because no Screen is allocated.
- Multiple Screens for one device do not cause multiple device registrations; one Screen does not define the inventory.
- PhysicalDevice enumeration requests have no discovery side effects and read only the process-wide registry.
- ScreenInit/ScreenFini are exclusively Screen-local and Screen close cannot unregister a shared PhysicalDevice.
- No Provider object, provider ranking, or alternate inventory is introduced.

**Important integration note:** Xorg's generic `xf86BusProbe()` / platform probing is not itself proof that a DDX backend binding is ready. Likewise, modesetting `Probe()` can be about allocating display Screens, while `PreInit()` is per-`ScrnInfo`. The implementation agent must inspect the actual target DDX path and choose a call site that meets both requirements: exact backend handle/context available, and no dependence on Screen creation. If the current Xserver lifecycle offers no such generic hook, add the narrowest DDX-owned server-wide registration hook needed; do not overload ScreenInit.



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
