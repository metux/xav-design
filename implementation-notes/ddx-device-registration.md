# Implementation notes: DDX-owned PhysicalDevice registration

**Scope:** Xlibre/Xorg implementation guidance for the normative registry architecture. This document does not define protocol ABI and does not authorize Xserver/backend implementation changes in the spec-only workstream.

## Core design

The DDX is the authoritative executable-device enumerator for the hardware it serves. Each DDX must register **all** PhysicalDevices it can serve, not merely the GPU associated with the first Screen. This includes render-only, compute-only, headless, and currently Screen-unattached devices.

The XAverius registry remains process-wide and server-owned. It canonicalizes identity, merges duplicate evidence, allocates PhysicalDevice XIDs, publishes immutable snapshots, and serializes lifecycle changes. The DDX does not allocate XIDs and does not choose the server-wide default device.

Platform/udev discovery is supporting identity and hotplug evidence. It is not a competing executable-device inventory and must not independently create publishable PhysicalDevices. Likewise, this Xlibre integration profile does not need an independent Vulkan-ICD enumerator that discovers a second set of candidate devices. A DDX may use Vulkan internally, but registers the resulting handles through its own device-registration path.

## Dispatch model: operation vectors live on the device binding

The selected PhysicalDevice binding is the dispatch object:

- immutable typed operation-vector pointers;
- opaque per-device backend context (or an explicitly retained shared DDX context);
- exact native/DDX-local physical-device handle;
- module-role generation and binding generation;
- references to code, operation-table storage, context, and callback userdata.

Request handling resolves the PhysicalDevice once, validates its selected binding/generation, and calls the operation vector directly. It must not resolve a separate XaveriusModuleRole object as an intermediate dispatch step.

The historical term `XaveriusModuleRole` may remain for the shared implementation/module lifetime control record: registration identity, shared loader lease, callback admission, quiescence, and shared immutable table storage. That control record is not a second per-device execution object. It may be shared by many device bindings, but per-device context/handle and dispatch selection remain on the binding.

Suggested conceptual layout (not a required C ABI):

```c
struct XaveriusDeviceBackendBinding {
    uint64_t ddx_generation;
    uint64_t binding_generation;
    const XaveriusBackendOps *ops;
    void *device_context;
    void *native_physical_device;
    struct XaveriusModuleRole *module_role; /* lifetime only, not dispatch */
};

struct XaveriusPhysicalDevice {
    /* canonical identity, XID, snapshot, status */
    struct XaveriusDeviceBackendBinding *selected_backend;
};
```

If several devices share one DDX/Vulkan instance context, each binding may hold a retained reference to that shared context. Do not duplicate the context or module lease unnecessarily. Conversely, a per-device native handle must not be stored in a global singleton or inferred from whichever Screen initialized first.

## Enumeration and registration sequence

1. The DDX enumerates every device it serves using its actual backend discovery path.
2. For each served PhysicalDevice, it supplies authoritative identity evidence (bus/sysfs/DRM identity where available; Vulkan UUID only as corroboration), a stable DDX-local instance key where necessary, the native handle, operations, and context.
3. The registry canonicalizes the identity. Ambiguous identities remain unpublished; vendor/device IDs or marketing names alone are insufficient.
4. The registry validates the complete operation tables required by advertised capabilities and obtains one complete immutable physical snapshot through that exact binding.
5. The registry publishes the canonical PhysicalDevice and allocates its XID only after all required state is complete.
6. Separately, each actual Xorg Screen creates a ScreenAttachment to the relevant already-registered PhysicalDevice(s).

The initial publication barrier waits for the configured DDX registration passes and identity/hotplug setup, not for Screen creation. Hotplug follows the same per-device sequence without reordering existing inventory.

If two DDX registrations claim the same canonical hardware, the registry deduplicates identity and selects at most one complete executable binding for v0.1 using a deterministic server policy. It must not merge operation tables, contexts, or snapshots. There is no transparent binding failover after publication.

## Lifetime and teardown

- ScreenAttachment lifetime is independent of device-binding lifetime. Closing a GPU Screen detaches topology; it does not automatically unregister a shared device backend or remove the PhysicalDevice.
- DDX unload closes registration admission, detaches its ScreenAttachments, withdraws its observations/device bindings, drains accepted asynchronous tokens, waits for callback quiescence, and only then releases contexts and the module lease.
- Xorg Screen references and DriverPtr.refCount are not sufficient pins for asynchronous callbacks or operation vectors.
- Every callback path that can enter DDX code retains the module-role lease and callback-execution reference until `XaveriusBackendCompletionDispatch` has copied/enqueued the completion and returned.
- A DDX backend/module control record may be shared across several PhysicalDevices, so module-wide shutdown drains all bindings owned by that role. A binding-local device loss affects only that PhysicalDevice.
- If quiescence cannot be proven, retain/quarantine the binding context and module; never unload reachable callback or operation code.

## Implementation review checklist

- [ ] Does the DDX enumerate/register all devices it serves, including non-Screen GPUs?
- [ ] Is there exactly one process-wide XAverius registry?
- [ ] Are PhysicalDevice identity and ScreenAttachment topology separate?
- [ ] Are call vectors and per-device context directly reachable from the selected PhysicalDevice binding?
- [ ] Is there no second XaveriusModuleRole lookup on each request?
- [ ] Are shared DDX/module lifetime references distinct from per-device native handles?
- [ ] Are complete snapshots obtained from one binding only?
- [ ] Are duplicate claims canonicalized without merging backend state?
- [ ] Are hotplug and teardown generation-checked and serialized?
- [ ] Can Screen close complete without waiting indefinitely for GPU progress while module code remains pinned safely?


## Current Xserver migration task

The active Phase A implementation instructions and acceptance tests are maintained in
[`phase-a-ddx-discovery.md`](phase-a-ddx-discovery.md). This architecture note
remains the durable design summary; old source-specific audit snapshots are
preserved in `IMPLEMENTATION_COORDINATION_HISTORY_2026-11-04.md` and must not be
treated as the current branch state. Re-audit `X11Libre/xserver:wip/xaverius`
at its live tip before making implementation claims.
