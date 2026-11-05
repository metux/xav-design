# Server-Side Physical-Device Registry Architecture

**Status:** Implementation architecture contract for XAverius v0.1. This document does not define wire fields or Vulkan backend implementation details. The protocol requirements in `devices.md` remain authoritative if a conflict is found.

## 1. Object model and ownership

The server MUST maintain one process-wide Physical-Device registry. It MUST NOT be owned by an X11 Screen, Xorg Entity, DDX instance, DRM node, Vulkan instance, or XAverius client connection.

The model has four distinct object classes:

1. **PhysicalDevice** — one canonical physical-device incarnation exposed by the server. It owns the server-lifetime identity, immutable published metadata snapshot, current discovery status, and one selected executable DDX binding. It is the sole source for XAverius Physical-Device enumeration and properties.
2. **Device backend binding** — the per-PhysicalDevice association containing the typed operation vectors, opaque backend context, and native/DDX-local physical-device handle supplied by the responsible DDX. It is the direct dispatch target for requests; it is not a separately selected backend object.
3. **ScreenAttachment** — a relationship between one live X11 Screen generation and one PhysicalDevice. It records that a Screen/DDX path uses or can access a device for a particular role. It does not own either endpoint and does not establish Vulkan presentation support.
4. **PresentationRoute** — an internal, generation-checked route for one exact logical-Device/Surface pair. It identifies the selected PhysicalDevice binding, the retained Window/Screen generation, and any explicit scanout/bridge path needed to present images produced by that logical Device. It is not a PhysicalDevice, Screen, Vulkan Device, or client-visible XAverius resource; it owns no endpoint and allocates no XID.

The relationships are:

- One PhysicalDevice has exactly one selected executable DDX device binding in v0.1.
- One PhysicalDevice MAY have zero or more ScreenAttachments.
- One Screen MAY have zero or more ScreenAttachments; a Screen is not required to map to exactly one GPU.
- One Surface MAY have distinct PresentationRoutes for different logical Devices; a route is scoped to one exact logical-Device generation and Surface/Window/Screen generation.
- A PresentationRoute MAY reference a scanout PhysicalDevice/ScreenAttachment and a private bridge adapter, but it MUST NOT change the logical Device's render PhysicalDevice or selected DDX device binding.
- A DDX device binding MUST NOT be implicitly created or destroyed with a ScreenAttachment.
- Destroying a Screen or detaching a DDX device binding MUST NOT destroy the PhysicalDevice identity.
- A PhysicalDevice MUST NOT be destroyed while its tombstone or any logical-device/backend reference remains live.

The registry owns PhysicalDevice records, canonical identity, and selected-binding references. The DDX owns the device-specific backend context and implements the registered operation vectors; a small server-side DDX/module-role control record may retain shared code/module and callback lifetime, but is not an additional dispatch layer. The Screen/DDX layer owns ScreenAttachment lifetimes. The XAverius presentation subsystem owns PresentationRoute records and their generation/lifetime arbitration; the selected device binding's operations own route-specific backend objects. XAverius owns the protocol resource/XID wrapper for each published PhysicalDevice. These ownership boundaries MUST remain explicit.

## 2. PhysicalDevice identity and publication

The registry MUST canonicalize identity evidence before the corresponding PhysicalDevice is published or assigned a Physical-Device XID. All identity and lifecycle evidence sources MUST submit observations to the same registry, including Xorg platform probing, udev hotplug, DDX-supplied device identity, and any future non-Xorg platform source. Executable PhysicalDevice enumeration and registration remain the responsibility of the DDX that serves each device; Vulkan-loader enumeration MUST NOT create an independent registry inventory or registration source.

A candidate MUST carry structured identity evidence, not just a string name or a backend pointer. The evidence SHOULD include:

- bus type and canonical bus identity (for PCI, full domain:bus:device.function);
- resolved canonical kernel/sysfs device path where available;
- DRM device identity sufficient to equate primary and render nodes;
- Vulkan deviceUUID when valid;
- an instance discriminator for mediated, virtual, partitioned, or derived devices;
- an incarnation token/generation that changes after confirmed removal and re-addition;
- descriptive vendor/device IDs and names as metadata, not as unique identity.

The registry applies the identity rules in `devices.md`. In particular, node path, `dev_t`, DRM minor, Screen index, Vulkan handle/pointer, and model name MUST NOT independently key a PhysicalDevice.

A PhysicalDevice has an internal, non-reusable server identity (for example, an opaque pointer paired with a generation or a monotonically allocated 64-bit registry ID). That internal identity is distinct from the protocol XID. The XAverius layer allocates exactly one server-owned Physical-Device XID when the canonical record is published, and retains the mapping until server shutdown. The registry MUST NOT expose a mechanism for a DDX/DDX backend to choose or allocate that XID.

The internal PhysicalDevice record is the single canonical object and owns its immutable metadata/capability snapshot as a member/value; implementations MUST NOT create a second independently registered DeviceCaps/PhysicalDeviceInfo object for the same device. Its DIX resource wrapper and protocol XID are server-private implementation state. A DDX-facing declaration, if any, MUST keep the PhysicalDevice opaque/incomplete and MUST NOT expose the XID or the private resource layout. The DDX MUST NOT allocate, inspect, store, free, or otherwise manage a PhysicalDevice XID. The registration call may return an opaque non-NULL PhysicalDevice pointer as an immediate success result and NULL on any failure (including duplicate/conflicting identity); this pointer is not a retained DDX handle and MUST NOT be stored or dereferenced after the registration call returns. Later operations use generation-checked server-owned references/tokens, never a bare DDX-retained PhysicalDevice pointer.

DDX device registration MUST have a defined completion point before first publication. Each DDX is responsible for registering every PhysicalDevice that it actually serves or exposes to XAverius; it MUST NOT register only the first Screen GPU or infer the server-wide inventory from Screen zero. The registry canonicalizes registrations from all DDX instances into one server-wide inventory. Platform/udev observation may supply identity and removal evidence, but it does not independently publish executable PhysicalDevices. A device registration arriving after publication follows the late-device path and MUST NOT replace the selected operations/context or mutate the published snapshot.

## 2.1 Discovery-source and driver-registration contract

PhysicalDevice registration, Screen topology attachment, and XAverius publication are distinct operations. In the Xlibre integration profile, the DDX is the sole producer of executable PhysicalDevice registrations for devices it serves. The registry, not the DDX, performs canonicalization and publication.

A discovery source is a producer of identity/lifecycle evidence, not an executable-device registrar. Platform bus and udev sources may report canonical hardware identity and authoritative add/remove evidence. The DDX reports the actual devices it can serve and supplies the backend operations/context for each registration. A source has a stable source key and non-reusable generation; its observations do not themselves create a PhysicalDevice XID or provide executable call vectors.

The registration paths are:

1. **Observe platform identity.** Platform/udev sources may submit identity and hotplug evidence. The registry canonicalizes it but does not publish an executable device from this evidence alone.
2. **Register each served PhysicalDevice.** The responsible DDX submits the canonical identity evidence, DDX-local device handle, per-device backend context where needed, and the call-vector binding. It MUST enumerate/register all devices it serves, not just the GPU associated with the first Screen.
3. **Validate and snapshot.** The registry validates the registration and obtains the complete immutable snapshot through that device's bound operations. It then publishes the canonical PhysicalDevice and allocates its server-owned XID. No Screen initialization order participates.
4. **Attach Screen topology.** A DDX/Screen path separately attaches the live Screen generation to one or more registered PhysicalDevices with explicit roles. This does not create a second PhysicalDevice or change its selected call vectors.
5. **Report lifecycle observations.** The DDX and platform sources report binding/device loss, recovery, Screen detach, and confirmed physical removal as distinct generation-checked events.

The DDX is the owner of the executable registration for each device it serves. The registration binds that device directly to its operations and backend context; there is no separately discoverable Vulkan-ICD DDX backend whose candidates compete to populate the XAverius inventory. A DDX that cannot implement the required XAverius operation contract MUST NOT register that device as executable for the corresponding capability. Screen attachment remains a separate topology operation.

### Registration semantics

The internal registration API SHOULD expose distinct operations equivalent to:

- `GpuRegistryObserveDevice(source, source_generation, identity_evidence)`: submit or update an observation. Returns a generation-checked canonical record reference only when identity matching is unambiguous; it never allocates a protocol XID.
- `GpuRegistryRegisterDdxDevice(registry, registration, out_device_generation, out_binding_generation)`: bind the exact canonical identity to the DDX-owned per-device call vectors, context, and native device handle. It does not publish the PhysicalDevice until the snapshot is complete. Its immediate result MAY be an opaque `PhysicalDevice *` (non-NULL only on success, NULL on every failure); the DDX MUST NOT retain or dereference that bare pointer after the call. Generation-checked server-owned references are used for all later work.
- `GpuRegistryRemoveDeviceBackend(device_ref, ddx_generation, binding_generation)`: stop new calls through that exact DDX/device binding and apply the selected-binding unavailability rules; it is not physical removal.
- `GpuRegistryRemoveObservation(source_generation, observation_id)`: withdraw only that source's evidence. It MUST NOT mark hardware REMOVED while other authoritative evidence still establishes the same incarnation.
- `GpuRegistryConfirmDeviceRemoved(device_ref, device_generation, removal_evidence)`: commit terminal REMOVED only on authoritative evidence that the physical incarnation was removed.
- `GpuRegistryAttachScreen(device_ref, screen_generation, roles)` and `GpuRegistryDetachScreen(attachment_generation)`: manage only the non-owning topology relation.

These names are semantic API guidance, not required exported symbols. Registration and removal calls from worker threads MUST enqueue immutable observations into the server serialization domain; they MUST NOT mutate registry state directly. All returned references and handles MUST be opaque and generation checked. A DDX/source MUST NOT retain or resolve a record by a bare pointer, XID, array index, DRM minor, or Screen number after the call returns.

An ambiguous identity match is not a license to merge or publish. The registry MUST keep the candidate unpublished and report the ambiguity to the registering source/server log until stronger evidence resolves it. If evidence proves that two published identities were duplicates, the implementation MUST NOT silently reassign or reuse a client-visible XID; this is a server consistency fault requiring controlled recovery, not an ordinary hotplug merge.

### 2.2 Identity-evidence hierarchy and backend correlation

Identity matching MUST be based on the underlying device incarnation, not on whichever identifier is easiest for a discovery adapter to obtain. The registry MUST retain the provenance and generation of each evidence item so that a stale observation cannot strengthen or override current evidence.

The following evidence classes define the v0.1 matching policy:

1. **Authoritative platform identity.** A resolved kernel device object and its bus identity are the primary platform correlation evidence. For PCI, use the complete domain:bus:device.function address together with the resolved canonical sysfs device path and the current device incarnation. For other buses, use the equivalent bus/subsystem identity and canonical parent/device relationship. A pathname alone is not authoritative if it can be replaced or reused.
2. **DRM-device equivalence.** Primary and render nodes MUST be correlated through the kernel's underlying DRM device identity (for example, `drmGetDevice2`/`drmDevicesEqual`, or equivalent bus information and canonical sysfs ancestry). Both nodes are access interfaces for one device, not separate devices. A node's basename, major/minor, `dev_t`, or DRM minor is only an observation locator and MUST NOT be the canonical key. Different DRM nodes MUST NOT be merged merely because they have the same vendor/device IDs.
3. **Backend-handle correlation.** A valid nonzero Vulkan `deviceUUID`, when the DDX uses Vulkan internally, is strong corroborating evidence for joining a DDX-local `VkPhysicalDevice` handle to a platform identity. It MUST be checked against authoritative platform evidence when both are available. Equal UUIDs with incompatible authoritative platform identities are a conflict, not permission to merge; differing UUIDs for handles claimed to represent the same authoritative platform identity are also a conflict that MUST be resolved before registration or publication.
4. **Derived-device identity.** A mediated, SR-IOV virtual function, partition, MIG instance, or other derived device MUST be distinguished from its parent and from sibling instances by an authoritative instance-specific identity. Parent identity alone MUST NOT merge children. A parent/child relation MAY be retained as descriptive topology, but it is not identity equality.
5. **DDX-scoped fallback identity.** A software, virtual, or non-enumerable device without a usable platform identity MAY be represented only when the registering DDX supplies a stable namespace and instance identity that distinguishes it from every other concurrently exposed instance. That key is scoped to that DDX registration domain and MUST NOT be treated as proof that another DDX's registration refers to the same device. Cross-DDX identity correlation requires independent corroboration.
6. **Descriptive metadata.** Vendor/device/subsystem IDs, names, driver strings, API versions, and marketing descriptions MAY reject an obviously inconsistent candidate but MUST NOT establish identity or incarnation equality by themselves.

The registry MUST apply these outcomes:

- Matching authoritative platform identity and compatible incarnation evidence joins observations into one canonical identity, even if DDX-native handles or Vulkan UUIDs differ; a conflicting UUID is recorded and must be resolved before that DDX device binding is eligible.
- Matching valid `deviceUUID` without conflicting platform evidence MAY corroborate two DDX registrations as the same physical-device identity. If either registration later gains contradictory authoritative platform evidence, the registry MUST quarantine the conflicting observation/binding and MUST NOT merge the platform devices.
- Equal UUIDs without enough evidence to distinguish two simultaneously present devices are ambiguous. The candidates remain unpublished until resolved; the registry MUST NOT collapse them solely to avoid duplicate enumeration.
- Different UUIDs with no authoritative platform correlation do not establish either sameness or difference. The candidates remain distinct pending stronger evidence; the registry MUST NOT infer sameness from names or model IDs.
- A DDX registration that cannot be correlated to a canonical platform identity MAY use the DDX-registration-scoped fallback only for a device class whose identity contract guarantees stable per-instance uniqueness. Otherwise it remains unpublished and cannot be selected for execution.
- Any conflict involving two already published identities MUST NOT be repaired by merging, changing an XID's referent, or silently rewriting the immutable snapshot. It is a registry consistency fault requiring controlled server recovery.

Incarnation is separate from identity correlation. A confirmed remove event closes the current incarnation. An add event after that boundary creates a new incarnation even when the BDF, sysfs path, DRM identity fields, DDX backend-scoped key, and `deviceUUID` are unchanged. If removal is uncertain, the registry MUST prefer an UNAVAILABLE or unresolved state over either falsely declaring REMOVED or resurrecting a tombstone. Source generations and event ordering MUST be used to reject delayed remove events from an earlier incarnation.

`GpuDeviceRemovalEvidence` contains no caller-selectable authority field. The registry MUST resolve `source_key` to a currently registered discovery source, validate the exact `source_generation` and `observation_id`, and derive the permitted authority class solely from that source's registered capabilities and server trust policy. The caller MUST NOT be able to elevate a source's authority by supplying additional fields or choosing an authority value. The evidence's `source_event_sequence` MUST match the referenced observation exactly; its `physical_device_generation` MUST identify the current incarnation, and the referenced observation MUST contain a removal indication sufficient for that authority class. Missing, contradictory, stale, or insufficient evidence returns a classified non-success result and leaves status unchanged. Only a validated authoritative removal commits terminal REMOVED, exactly once.

A DDX device binding MUST identify the exact native physical-device instance it will use and carry the identity evidence used to correlate it. If the DDX obtains handles through multiple Vulkan instances, it MUST deduplicate aliases before registration. A DDX MUST NOT claim a binding merely because a candidate has matching vendor/device IDs or a matching display name.

### 2.3 Canonical ordering key

Every unambiguous, publishable PhysicalDevice MUST have one canonical ordering key derived from the same canonical identity record used for deduplication. The key is an internal comparison value; it is not a wire property, a persistent identifier, or a client-visible sort guarantee.

The key MUST be a typed, normalized tuple and MUST NOT contain DDX module-role registration order, Vulkan enumeration index, pointer value, DRM minor, node pathname without its canonical device relationship, Screen index, or mutable descriptive metadata. The v0.1 tuple is ordered first by identity class, then by that class's canonical identity components:

1. Platform-backed devices: bus-type tag, normalized bus identity (for PCI, the complete domain:bus:device.function; for other buses, the canonical bus/subsystem identity), and the normalized instance discriminator when required.
2. Derived devices: derived-device class tag, canonical parent identity key, and authoritative child-instance discriminator.
3. DDX-scoped software/virtual devices: software/virtual class tag, stable DDX/backend namespace key, and DDX-supplied stable instance key.
4. Devices with no platform identity but a valid, unambiguous cross-instance `deviceUUID`: UUID-only class tag and the exact 16 UUID bytes.

Comparison is bytewise lexicographic over the canonical tuple encoding, with fixed-width numeric fields encoded in a documented normalized order and variable strings length-delimited. Implementations MUST use one canonical encoding and comparison function throughout the registry; locale-sensitive string collation is forbidden. A collision between two distinct live canonical records is an identity ambiguity and MUST be resolved before either record is published. An incarnation token distinguishes removal/re-addition for lifecycle and stale-event rejection, but MUST NOT make a replacement device sort as the old published incarnation or permit tombstone resurrection.

This key defines the default ordering used by `CreateDefaultDevice` when no explicit default-device preference is configured. An explicit preference list MUST use stable canonical identity selectors, not XIDs, BDF enumeration positions, DRM node numbers, or Screen indices. A selector MUST resolve to at most one canonical identity; duplicate or ambiguous selectors are configuration errors. The server filters for AVAILABLE devices and queue-family suitability before applying the preference list or canonical-key ordering. If a preferred device is unsuitable, it proceeds to the next preference; if no preference matches a suitable device, it uses the lowest canonical key among all suitable devices. This selection never changes an already-created logical Device or the selected DDX device binding of any PhysicalDevice.

### Startup, late registration, and removal

Initial publication has a server-wide discovery barrier: all configured DDX device-registration passes and platform identity sources complete their initial pass, identity canonicalization, DDX-binding eligibility evaluation, configured binding-preference resolution, and snapshot query before the XAverius inventory is exposed. Enumeration order and Screen initialization order MUST NOT affect the resulting inventory or selected binding.

A late DDX registration or platform observation MAY add corroborating identity evidence. It MUST NOT replace the selected DDX binding, mutate the published snapshot, or cause a second XID. A newly hotplugged physical-device incarnation follows the same canonicalize/eligibility/preference/snapshot/publish sequence independently before it becomes visible to clients. v0.1 does not support transparent DDX-binding failover. If the selected binding is withdrawn or its DDX registration is permanently deregistered, the PhysicalDevice becomes UNAVAILABLE and remains so until the same registration generation can recover; a new DDX registration is not transparent recovery. The PhysicalDevice becomes REMOVED only after confirmed removal of that hardware incarnation.

A DDX unload or Screen teardown MUST detach every ScreenAttachment owned by that exact Screen generation before its Screen-private state is freed. A DDX unload MUST also withdraw its device registrations and discovery observations through their distinct lifecycle operations. Detaching the last Screen does not remove a PhysicalDevice: headless, off-screen, render-only, or temporarily unbound devices remain in the server-wide inventory if their physical/DDX device registration remains valid. Similarly, removing one DRM access node does not prove physical removal if another node or authoritative source still identifies the same device.

A confirmed physical removal is server-wide and independent of Screen membership. It invalidates future logical-device creation for that incarnation and leaves its PhysicalDevice tombstone/XID in the inventory. A stale remove or detach observation carrying an older source, DDX backend, Screen, or device generation MUST NOT affect a replacement incarnation.

### Driver-facing responsibilities

| Component | May report/register | MUST NOT decide |
|---|---|---|
| Xorg platform bus / udev adapter | Bus identity, DRM node observations, authoritative add/remove evidence | PhysicalDevice XID, Vulkan DDX-binding selection, published capabilities |
| DDX driver | Enumerate and register every PhysicalDevice it serves; provide per-device identity evidence, native handle, backend context/call vectors, complete snapshot, loss/removal events, and ScreenAttachment roles | Server-wide identity deduplication, XID allocation, global publication/default-device policy, request validation |
| Platform/udev adapter | Canonical bus/sysfs identity and authoritative add/remove evidence | Executable device registration, backend call vectors, XAverius XIDs |
| XAverius registry/resource layer | Canonical identity, DDX-binding selection, snapshot publication, PhysicalDevice XID, status/event serialization | Direct dereference of DDX backend-private Vulkan handles |
| WSI/presentation path | Exact DDX-local Surface and Device/Surface capability operations | Infer presentation support from ScreenAttachment or Screen number |

On Xlibre/Xorg, the required arrangement is one XAverius-owned registry service. Each DDX registers all PhysicalDevices it serves, including headless/render-only devices and GPUs not selected by its first Screen. Platform/udev integration supplies identity and hotplug evidence only. Screen initialization attaches topology to already registered devices. The registry merges identity observations across DDX/platform sources, but does not merge executable bindings. If multiple DDX roles register complete bindings for the same canonical incarnation, the registry selects exactly one using the configured DDX device-registration role preference described below; it does not merge operation tables, contexts, or snapshots, and it does not enumerate Vulkan ICDs independently to invent another device inventory.


### 2.4 Xlibre/Xorg discovery and DDX integration profile

This subsection defines the required integration behavior for an Xlibre/Xorg server. It deliberately does not prescribe private Xserver hook names or a particular DDX module layout: those vary between server versions and drivers. An implementation MUST provide equivalent lifecycle points and preserve the ownership and ordering rules below.

#### Registry service and adapter roles

The XAverius registry MUST be one server-process service, initialized independently of individual Screen creation. It MUST NOT be instantiated per Screen, per Xorg Entity, per DDX module, per DRM file descriptor, or per Vulkan instance. All adapters MUST register with that same service and use its generation-checked registration operations.

DDX binding preference is server configuration, not a DDX-provided priority and not a separate provider API. Each DDX backend GpuModuleRole (role kind `GPU_MODULE_ROLE_DDX_BACKEND`) MUST have a stable, non-empty owner_key identifying that role across reloads; the key is copied at registration and is case-sensitive. The server MAY configure an ordered list of these DDX-backend owner_key values. Duplicate keys in the preference list are configuration errors. The registry applies this list only before initial publication or before publication of a newly hotplugged incarnation. A published binding is immutable for that incarnation: later registration of a higher-preference binding MUST NOT replace it, and loss/removal of the selected binding MUST NOT trigger fallback to a non-selected binding. Non-selected complete bindings remain independently registered and may be selected only for a new, not-yet-published incarnation or after the old incarnation is confirmed REMOVED and a new incarnation is discovered.

The Xlibre integration SHOULD expose three adapter roles:

- **Platform identity/hotplug adapter:** observes kernel/DRM devices and add/remove events, supplying canonical bus/sysfs identity and DRM-node equivalence evidence. It is not an executable-device inventory.
- **DDX device-registration adapter:** enumerates and registers every PhysicalDevice served by that DDX, with its per-device backend operations/context and identity evidence. It separately creates ScreenAttachments for actual Screens. It MUST NOT choose the server-wide default device or allocate XIDs.
- There is no independent Vulkan-ICD inventory adapter in this profile. A DDX may use Vulkan internally, but the resulting physical-device handles and call vectors are registered through that DDX's device-registration path.

One module MAY implement more than one role, but it MUST register and retire each role independently. In particular, unloading a DDX module MUST NOT implicitly deregister a DDX module-role record owned by another module, and closing a Screen MUST NOT imply removal of the underlying GPU.

#### Startup discovery barrier

The server MUST establish the platform hotplug observation path before beginning the corresponding initial enumeration, so that add/remove events racing with enumeration are not lost. The implementation MUST reconcile the initial scan with queued events using source generations and observation ordering; it MUST NOT publish two incarnations or accept an old remove event against a newly observed incarnation.

Before XAverius exposes its initial PhysicalDevice inventory, each configured DDX device-registration pass and the platform identity/hotplug pass MUST report complete or unavailable/failed. The barrier MUST NOT wait for Screen creation, RandR initialization, a DDX ScreenAttachment, or a window to exist. A DDX pass is complete only after it has reported every PhysicalDevice it serves, including devices not attached to a Screen.

A failed or unavailable DDX registration pass is not evidence that a device was removed. The registry MUST NOT fabricate a backend binding or publish a PhysicalDevice without a complete snapshot from its registered DDX call vectors. A later successful DDX pass MAY register and publish a device that remained unpublished because no complete binding/snapshot was available. It MUST NOT replace an already published selected binding or recover a withdrawn binding through a different registration generation.

An adapter registered after the initial barrier has closed MUST use the late-registration path. It MUST NOT reopen the barrier, reorder existing inventory, replace a selected DDX binding, or mutate an already published snapshot. A newly discovered physical-device incarnation follows the same per-device publication sequence without blocking unrelated existing devices.

#### Xorg/DRM identity hand-off

A platform adapter SHOULD use the canonical kernel device relationship as the identity anchor. For DRM devices, primary and render nodes MUST be correlated using the underlying DRM device identity (for example, libdrm device information/equivalence and canonical sysfs ancestry), not by node basename, minor number, open-file-description identity, or which node a DDX happened to open first.

A DDX reporting a ScreenAttachment MUST resolve its DRM/platform device to the registry's canonical PhysicalDevice reference using structured identity evidence. If it has only a Screen number, Entity index, driver-private pointer, or DRM node pathname without a verified canonical relationship, the attachment MUST remain unresolved; it MUST NOT create a new PhysicalDevice or attach to an arbitrary matching vendor/device ID. A Screen may report multiple attachments, including distinct render-access and scanout/display-control roles. The same PhysicalDevice may be attached to multiple Screens.

The platform adapter's source key and source generation identify the adapter instance and its observation stream, not the device. A DDX Screen generation is separate from both. Recreating a Screen or reloading a DDX creates a new Screen/source generation as applicable; it does not create a new PhysicalDevice incarnation unless authoritative physical-removal evidence closed the previous incarnation.

#### Hotplug, Screen lifecycle, and teardown

The hotplug path MUST follow the same per-device order as startup: collect identity evidence; canonicalize or leave ambiguous; accept the responsible DDX's complete device binding; validate its call vectors; obtain a complete snapshot; publish one server-owned XID; then allow the DDX to attach any live Screens. The implementation MAY perform these steps asynchronously, but no client-visible partial PhysicalDevice is permitted.

A kernel/udev remove event MUST first be correlated to the exact current source observation and PhysicalDevice incarnation. Loss of one DRM node, closing a DRM file descriptor, DDX unload, Screen close, or loss of display ownership MUST NOT alone be treated as physical removal. If the event proves only that one access path disappeared, withdraw that observation and recompute availability from remaining evidence. Only the validated authoritative removal operation may transition the PhysicalDevice to terminal REMOVED.

On Screen close or replacement, the DDX topology adapter MUST detach every ScreenAttachment for that exact Screen generation before releasing Screen-private data. Any asynchronous work referring to the Screen MUST retain a generation-checked reference and MUST be retired or cancelled before the Screen-private data is freed. A late callback or detach for the old generation MUST be ignored with a stale-generation result; it MUST NOT affect a replacement Screen that reuses an Xorg index or address.

On DDX module unload, the module MUST first stop new adapter callbacks, withdraw its own observations and ScreenAttachments, and retire its DDX module-role registrations independently. Module code and callback userdata MUST remain pinned until all callbacks, operation tokens, and retained references that can reach them have retired. If quiescence cannot be proven, the module/DDX backend state MUST be quarantined rather than unloaded. This is in addition to, not a replacement for, the DDX device-binding/module lifetime contract.


#### Screen-close and module-unload ownership boundary

The Xserver Screen lifecycle MUST be treated as a topology lifetime only. In the current XLibre implementation, GPU-screen removal calls the Screen close path, removes the GPU Screen, and then deletes its `ScrnInfo`; `xf86DeleteScreen()` invokes the DDX `FreeScreen()` hook, releases the Screen's module reference, and decrements the driver's Screen reference count. These operations do not establish that asynchronous work previously submitted by the DDX/DDX backend has stopped executing.

Accordingly:

- `CloseScreen`, `FreeScreen`, `RemoveGPUScreen`, `xf86DeleteScreen`, or a zero `DriverPtr.refCount` MUST NOT be treated as proof of backend-operation completion, callback quiescence, or permission to release DDX backend userdata.
- The DDX MUST detach the ScreenAttachment for the exact Screen generation before releasing Screen-private data. The ScreenAttachment MUST NOT own the DDX module-role record or DDX module lease.
- A Screen close MUST NOT unregister a shared GpuModuleRole merely because the DDX binding was first discovered or opened through that Screen. DDX module-role lifetime is independent of every ScreenAttachment lifetime. If a DDX adapter truly has per-Screen state, that state MUST be a separately retained child record keyed by the exact ScreenAttachment generation and owning module-role generation; it MUST retire only after its own Screen-generation work is quiescent. It MUST NOT become a generic per-device module-role context or dispatch layer.
- A DDX module that supplies backend operation functions, completion callback functions, callback trampolines, or callback userdata MUST acquire a DDX backend/module lease independent of Xorg's Screen-held module reference and driver Screen reference count. The lease MUST cover every function pointer and data object that can be reached by an accepted operation or a callback, including deferred cleanup and retirement paths.

- No asynchronous backend operation, worker, or callback may retain or later dereference a raw `ScreenPtr`, `ScrnInfoPtr`, `pScreen`, `pScrn`, or pointer into storage owned by `FreeScreen()`. Before crossing an asynchronous boundary, the DDX MUST copy the required immutable values or create a separately reference-counted ScreenAttachment context that contains no borrowed Xserver Screen/`ScrnInfo` pointers. Closing the Screen marks that context detached and prevents new Screen-facing work; the detached context may remain alive solely for callback bookkeeping until its own references retire. A callback after `CloseScreen` may complete backend cleanup using that detached context, but MUST NOT call Screen hooks, access RandR objects, or re-enter the deleted Screen.
- A DDX backend callback that has entered module code MUST hold a callback-execution reference until it has returned to the server-owned completion sink. The sink MUST copy/enqueue the immutable completion before returning; the DDX backend callback MUST NOT retain server-owned transient payload pointers after that return.

DDX module-role shutdown is a two-phase operation, not an ordinary Screen cleanup:

1. **Close admission.** Atomically mark the exact DDX module-role generation as QUIESCING. Reject new operations and new DDX device bindings for that generation. Stop new discovery callbacks from that module and unregister its callback/event sources. This does not cancel accepted operations or release any existing reference.
2. **Withdraw topology and observations.** Detach every ScreenAttachment owned by the module for its exact Screen generations and withdraw its discovery observations. These operations do not imply physical removal and do not implicitly retire a DDX backend owned by another module.
3. **Drain accepted work.** Obtain exactly one terminal outcome for every accepted DDX backend-operation token. Then retire each exact token. A token is retired only when the DDX backend confirms both that no backend access can remain and that the token's completion callback has returned; a queued server-side immutable completion record may still be processed because it no longer references DDX backend code or callback userdata.
4. **Quiesce DDX backend callbacks.** An explicit module-role-wide quiescence operation (or equivalent contract) MUST confirm that no callback is executing, queued for invocation, or can begin for this DDX module-role generation, and that no new operation can be accepted. It MUST also confirm that every DDX-owned worker/task capable of entering module code has stopped or no longer holds such a path. Merely observing zero outstanding tokens in the server is insufficient.
5. **Release DDX backend and module.** Only after all selected PhysicalDevice, logical-Device, route, DDX backend-object, callback-execution, and operation-token references have retired MAY the final DDX backend reference be released and the module lease dropped. Xorg may then unload the DDX module through its ordinary module-reference mechanism.

The module-role-wide `quiesce_module_role` hook is mandatory for any DDX backend whose code or callback path can be unloaded independently of server shutdown. It MUST be idempotent and generation-scoped. The first call closes DDX backend-internal admission and callback dispatch; subsequent calls poll the same quiescence attempt. It MAY report PENDING while workers or callbacks are draining. SUCCESS has the strong meaning in step 4; FAILURE leaves the module pinned. The server MUST stop calling ordinary backend operations before invoking this hook. `release_module_role` MUST NOT be the mechanism that initiates quiescence, because it is an infallible reference-count operation and MUST NOT block or invoke backend work. If a callback/worker cannot be stopped or its reachability cannot be disproved, the DDX module-role record, module lease, callback code, and userdata MUST be quarantined until server shutdown or a later proven-safe retirement. The server MUST NOT block Xorg's Screen close indefinitely waiting for GPU progress: Screen topology can be detached while the independent DDX backend/module lease remains retained.

If one DDX module implements both the topology adapter and DDX backend, it MUST still maintain these independent references. If the DDX backend implementation is in a separate module/library, the DDX Screen may close and unload without affecting that DDX backend, provided no callback path from the DDX backend retains DDX Screen-private data. Any bridge callback crossing those module boundaries MUST retain both sides' exact-generation leases until the bridge callback has returned and its associated backend operation is retired.

#### XLibre lifecycle mapping (source-level observation)

At XLibre source commit `ee4bb3f96eec3b21c1961d54fe45cb33dc402d00`, `xf86platformRemoveDevice()` calls `dixScreenRaiseClose()`, then `RemoveGPUScreen()`, then `xf86DeleteScreen()`. `xf86DeleteScreen()` calls the DDX `FreeScreen()` hook before `UnloadModule(pScrn->module)` and decrementing `pScrn->drv->refCount`. This sequence is the Screen/DDX cleanup boundary; XAverius MUST complete ScreenAttachment detachment before Screen-private release, but DDX backend/module quiescence is governed by the independent lease protocol above. Implementations MUST NOT assume that the Xorg module reference held by a particular `ScrnInfo` is sufficient for DDX backend callbacks that outlive that Screen.


The loader implementation reinforces this separation. In the same source revision, `DuplicateModule()` copies the module handle into a per-`ScrnInfo` descriptor and marks that descriptor as duplicated; `UnloadModule()` skips `LoaderUnload()` for such duplicates. The original module descriptor eventually reaches `LoaderUnload()`, which calls `dlclose()`. The `DriverPtr.refCount` is a count of Xorg Screen/driver use, not a count of backend operations or callbacks. Therefore neither a duplicated `ModuleDesc` nor a positive/zero driver Screen reference count is a DDX backend-lifetime pin. A DDX that exports DDX backend callbacks MUST use a distinct loader/module pin whose acquisition and final release are tied to the DDX backend reference/quiescence contract. The pin MUST remain effective even after the last `ScrnInfo` and GPU Screen have been deleted.

#### Xlibre-specific conformance requirements

An Xlibre/Xorg integration MUST demonstrate at least the following:

1. Two Screens initialized in either order produce the same canonical PhysicalDevice inventory and selected DDX bindings.
2. A single Screen attached to two GPUs creates two ScreenAttachments without duplicating either PhysicalDevice; two Screens using one GPU share one PhysicalDevice identity.
3. Primary and render DRM nodes for one device produce one PhysicalDevice; removing one node does not remove the device while authoritative evidence for the same incarnation remains.
4. A Screen close/recreate cycle changes only ScreenAttachment generations and cannot change PhysicalDevice identity, XID, DDX-binding selection, or published snapshot.
5. A DDX that only supplies topology cannot become the selected DDX binding or publish a device; a DDX registered as a DDX backend must satisfy the full DDX backend contract.
6. A failed or late discovery adapter does not block already completed devices, fabricate removal, reopen the startup barrier, or mutate published records.
7. Hotplug add/remove events racing with initial enumeration cannot lose an event, resurrect a tombstone, or apply a stale removal to a replacement incarnation.
8. DDX unload with pending callbacks/operations cannot unload reachable callback code or release userdata before DDX binding, module-role, and operation retirement.

These requirements are server-integration conformance tests. They do not add wire requests, XIDs, properties, or status values.

## 3. DDX device backend binding contract

In the Xlibre/Xorg integration profile, the DDX is the sole component that registers executable PhysicalDevices for the hardware it serves. A DDX MUST enumerate and register every such device, not merely the device associated with the first Screen. This includes headless, render-only, compute-only, and otherwise Screen-unattached devices that the DDX can serve.

The executable backend is bound directly to each canonical PhysicalDevice registration. The binding contains (or references) the typed operation vectors, opaque backend context, and DDX-local/native physical-device handle required to execute that device. Request dispatch resolves the PhysicalDevice's selected binding and calls its operation vector directly. It MUST NOT perform a second lookup through a separately selected GpuModuleRole object on every operation.

The term **GpuModuleRole** remains useful only as a registration/lifetime identity for the implementation code and shared module resources. It is not an additional per-device execution object and MUST NOT obscure the direct binding. A DDX module-role registration/control block MAY own shared module lease, callback sink, admission/quiescence state, and references to immutable operation-table storage. The per-device binding owns the device-specific context/handle and points directly to the applicable operation tables. If the DDX uses one shared backend context for several devices, the binding MAY reference that shared context with explicit references; it MUST NOT create a duplicate DDX backend wrapper solely to dispatch calls.

A DDX device registration MUST identify its already-registered owning module role by the exact non-reusable module-role generation and MUST include:
- canonical PhysicalDevice identity evidence and exact device-incarnation reference;
- immutable typed operation-vector pointers covering the capabilities advertised for this device;
- opaque per-device backend context and DDX-local physical-device handle;
- binding generation and availability/lifecycle state;
- references that keep all reachable code, operation-table storage, context, and callback userdata alive through operation retirement and quiescence.

The registry validates the complete operation tables before publication. Missing operations for an advertised capability make the registration ineligible; the registry MUST NOT discover this only when a client first invokes the operation. Operation vectors and nested tables are immutable for the lifetime of the binding. Backend/native handles remain opaque; request handlers and other DDX modules MUST NOT dereference them.

For v0.1, each published PhysicalDevice has exactly one selected executable DDX binding. If multiple DDX registrations resolve to the same canonical hardware incarnation, the registry MUST deduplicate the identity and apply a deterministic server policy to select one complete executable binding before publication. It MUST NOT merge operation tables, contexts, or snapshots from different DDX registrations. Registration order, Screen order, pointer values, DRM node numbers, and module load order MUST NOT determine the selection. A later DDX registration MUST NOT silently replace the selected binding or mutate the published snapshot.

The selected binding supplies one coherent immutable published metadata snapshot: device properties, queue-family properties, memory properties, limits, and advertised XAverius properties. The registry MUST NOT synthesize a snapshot by mixing fields from different registrations. After publication, property requests are answered from that snapshot; they MUST NOT re-query a different DDX or silently refresh fields in place.

A selected binding becoming temporarily unavailable makes the PhysicalDevice UNAVAILABLE; it does not establish physical removal. Recovery of the same DDX registration generation and same hardware incarnation MAY restore AVAILABLE if it can still honor the published snapshot. A different DDX binding MUST NOT transparently take over an existing published identity in v0.1. Confirmed physical removal transitions the PhysicalDevice to REMOVED.

Logical-device creation pins the exact selected binding, DDX registration generation, and PhysicalDevice incarnation. Every logical Device and asynchronous backend operation MUST retain the relevant binding, context, code/module, and resource references until all backend accesses and callbacks have quiesced. Unloading the DDX module or destroying its context while any such reference exists is forbidden. If quiescence cannot be proven, the backend objects and module references MUST be retained or quarantined.

### 3.1 DDX module-role and per-device binding lifetimes

A DDX registers one module-role control record when it has unloadable code, callbacks, or shared resources whose lifetime spans multiple PhysicalDevices. This record is not an execution backend and is never selected by a PhysicalDevice. Its sole purposes are module pinning, callback admission, shared-resource lifetime, and module-wide quiescence.

Each served PhysicalDevice has its own **DeviceBackendBinding**. That binding directly contains or references:
- the immutable typed `GpuDeviceBackendOps` table(s);
- the exact opaque native PhysicalDevice handle;
- the per-device backend context, or an explicitly retained shared context;
- the DDX module-role generation that pins the code and shared resources;
- the binding generation, availability state, and retained lifetime references.

The PhysicalDevice's selected binding is the direct dispatch target. A request resolves the PhysicalDevice/logical Device and calls the operation vector in that binding. No separately selected DDX binding/backend object, DDX-local numeric handle lookup, or second dispatch indirection exists.

The DDX module-role record MAY be shared by many bindings. It MUST NOT contain a mutable "current device" selector or require callers to look up a device by Screen, enumeration index, or DDX-local ID. Device-specific state remains in the binding. A DDX with no shared module state may use a minimal role token for generation/lifetime accounting; it need not allocate a heavyweight backend object.

In v0.1, one canonical PhysicalDevice has exactly one executable DDX binding. The responsible DDX is the authority for enumerating and registering all devices it serves. Platform/udev sources contribute identity and hotplug evidence only; they do not register executable candidates. If duplicate DDX claims resolve to the same canonical hardware incarnation, the registry applies deterministic policy before publication and selects one complete binding. It MUST NOT merge operation tables, contexts, handles, or snapshots. After publication, another DDX registration cannot silently replace the selected binding. There is no transparent binding failover in v0.1.

A DDX module-role generation MAY own bindings for many PhysicalDevices. A device-binding failure affects only that PhysicalDevice; a module-role failure affects every binding whose code/context depends on that role. Closing a Screen detaches its ScreenAttachment only; it does not remove a shared binding or module role. DDX unload closes admission, withdraws that DDX's registrations and observations, drains operations/callbacks, quiesces the module role, and releases the module lease only after all reachable code and data have retired.

The server assigns nonzero, non-reusable module-role and binding generations. A failed registration consumes its reserved generation. Every binding retains its module role and any shared context it uses. For unloadable code, the module-role lease covers operation tables, callbacks, callback userdata, shared contexts, and all trampolines reachable by accepted work. A permanent role has no loader lease because its code remains resident through process shutdown. A binding separately retains its device context and native handle until all logical Devices, backend objects, operations, and callbacks that can access them have retired. If quiescence cannot be proven, the affected binding/context and module lease MUST be retained or quarantined rather than unloaded.



## 4. DDX backend operation interface

The device backend operation interface is a server-internal contract. It is not a Vulkan ABI, a client ABI, or a requirement to expose raw Vulkan entry points to XAverius request handlers. The server owns protocol validation, resource/XID ownership, request ordering, error precedence, and public state transitions. The DDX binding owns the actual backend calls and every device-local handle. Request handlers MUST call the operation vector stored in the exact selected PhysicalDevice binding; they MUST NOT resolve a second GpuModuleRole dispatch object.

### 4.1 Operation groups

The selected DDX device binding MUST implement the following operation groups for every capability it advertises. An operation that is not applicable to the selected backend MAY be absent only when the corresponding XAverius capability is not advertised.

| Group | Required operations | Contract |
|---|---|---|
| Physical-device query | `query_physical_snapshot` | Query one complete, immutable snapshot through the exact newly registered device binding. Hardware enumeration belongs to the DDX and is not an operation in the XAverius backend vector. |
| Logical-device lifecycle | `create_logical_device`, `get_queue`, `destroy_logical_device` | Create the Vulkan logical device with the exact validated queues/features/extensions; obtain queues for the requested family/index; destroy the logical device after its dependent work is quiescent. |
| Buffer and memory | `create_buffer`, `get_buffer_memory_requirements`, `allocate_memory`, `free_memory`, `bind_buffer_memory`, `write_buffer`, `read_buffer` | Implement the Buffer/Memory semantics, alignment and range rules, upload/readback snapshot barriers, and transfer completion contracts in `memory-buffers.md`. |
| Shader, descriptor, and pipeline objects | create/destroy ShaderModule, DescriptorSetLayout, DescriptorPool, DescriptorSet, PipelineLayout, and ComputePipeline operations; descriptor updates | Implement the exact validated object descriptions and Vulkan dependency/lifetime ordering in `shaders-pipelines.md`. |
| Command recording | create/destroy/reset command pools and command buffers; begin/end recording; encode every v0.1 command opcode | Implement the validated command stream and command-buffer state machine in `command-recording.md`. The DDX binding MUST NOT reinterpret or reorder XAverius request ordering. |
| Synchronization | create/destroy semaphores and fences; host timeline signal; queue signal/wait integration; fence reset and completion publication | Implement binary/timeline semaphore and fence behavior in `synchronization.md`, including the specified WAIT_ANY/WAIT_ALL and timeout semantics. |
| Queue execution | `queue_submit` and any backend completion/retirement operation | Submit the already validated dependency graph to the exact queue. Accepted submissions complete asynchronously and report one terminal outcome through the server's serialized completion path. |
| Presentation | DDX backend-scoped surface create/destroy; exact Device/Surface route and queue-family support query; route create/retire; surface-format and present-mode query; swapchain create/destroy; image acquire; queue present | Implement the presentation profile only when enabled. The selected DDX device binding owns the route for its logical Device; it may implement a direct or explicitly bridged scanout path, but MUST NOT migrate execution to another PhysicalDevice/DDX backend. ScreenAttachment MUST NOT substitute for the exact route query. |

Synchronization ownership is split deliberately: the DDX backend implements Semaphore/Fence backend creation/destruction, host `SignalSemaphore` backend signaling, queue-side signal/wait dependencies, fence reset, and completion reporting. The server owns the observable Timeline counter and Fence state. `GetSemaphoreCounterValue`, `GetFenceStatus`, `WaitSemaphores`, and `WaitForFence` read/register against that server state; they MUST NOT issue a second DDX backend counter query or blocking host wait. Successful queue/host signal and fence-completion results are published into server state through the serialized completion path before affected host-wait registrations are reevaluated.

### 4.1.1 Request ownership map

The following map closes the DDX backend boundary against the complete request registry. "Server-owned" means the request is implemented from XAverius state/metadata and does not invoke a backend operation for that request itself; it does not mean that earlier backend operations are irrelevant to its state.

| Requests | DDX backend responsibility | Server responsibility |
|---|---|---|
| `QueryVersion` (0) | None | Protocol version/profile reply. |
| `EnumeratePhysicalDevices`, `GetPhysicalDeviceProperty`, `GetPhysicalDeviceQueueFamilyProperties`, `GetPhysicalDeviceMemoryProperties` (1–3, 7) | Discovery and pre-publication snapshot only | Registry enumeration and all post-publication replies from the immutable snapshot. |
| `CreateDevice`, `CreateDefaultDevice`, `DestroyDevice` (4–6) | Logical Device/Queue create, queue acquisition, backend teardown | Selection, validation, XID publication/invalidation, Device state, cascading resource invalidation. |
| `CreateBuffer`, `GetBufferMemoryRequirements`, `AllocateMemory`, `FreeMemory`, `BindBufferMemory`, `WriteBuffer`, `ReadBuffer` (8–14) | Buffer/Memory backend operations and transfer completion | Wire validation, memory/resource accounting, ordering barriers, reply/error and lifetime arbitration. |
| `ShaderModuleData`, Descriptor, Pipeline Layout, and Compute Pipeline requests (15–23) | Create/destroy ShaderModule, DescriptorSetLayout, DescriptorPool/Set, PipelineLayout, ComputePipeline; atomic descriptor updates | Chunk assembly/abort, XID/ownership/limit validation, descriptor reference graph and public state transitions. ShaderModuleData reaches the DDX backend only when the validated final chunk commits module creation. |
| Command Pool/Buffer requests and `QueueSubmit` (24–28) | Command pool/buffer backend lifecycle, validated command encoding, queue submission and completion | Command stream framing/validation, command-buffer state machine, dependency graph, acceptance point, token/event delivery. |
| `CreateSemaphore`, `SignalSemaphore`, `DestroySemaphore`, `CreateFence`, `ResetFence`, `DestroyFence` (29, 32–34, 37–38) | Semaphore/Fence backend lifecycle, host timeline signal, queue-side synchronization integration, reset, completion reporting | XID/ownership/state validation, observable counters/states, synchronization reservations and retirement. |
| `GetSemaphoreCounterValue`, `WaitSemaphores`, `GetFenceStatus`, `WaitForFence` (30–31, 35–36) | No direct DDX backend query/wait operation; DDX backend completion callbacks update the state being observed | Server-owned state queries, wait predicates/registrations, timeout and terminal arbitration. |
| `DestroyResource` (39) | Typed backend destroy for the resource family | Type/ownership/lifetime validation, public XID invalidation, dependency invalidation and deferred retirement. |
| `SelectEvents` (40) | None | Connection/device/queue event-mask replacement and event routing. |
| Presentation requests (41–47) | DDX backend-scoped Surface; exact physical-device Surface support; Swapchain; acquire/cancel/late-image retirement; queue present | X11 Window identity, Surface/Swapchain XIDs, validation/status precedence, image/token/synchronization state, timeout and event arbitration. |

Command entries (`CMD_*`) are not request subopcodes. The server validates their wire encoding and state effects; the DDX backend receives only the validated command representation for backend recording. Likewise, chunk transport for ShaderModuleData and CommandBufferData is server-owned; backend object creation/recording occurs only at the specified validated commit/finalization point. SelectEvents and QueryVersion are entirely server-side.

The names above describe semantic operations, not mandatory C symbol names. A DDX binding MAY implement several rows through shared internal helpers, but it MUST preserve each operation's validation boundary, result classification, ordering, and lifetime semantics. All create operations MUST either return a complete backend object or fail without exposing a partially initialized object. If the backend partially creates objects before failure, the DDX binding MUST roll them back or retain them privately until safe cleanup; the server MUST NOT publish the corresponding XAverius resource.

The DDX device-registration descriptor MUST install a completion sink equivalent to `GpuBackendCompletionFn` plus an opaque server-owned binding-userdata pointer before any asynchronous operation can be accepted. The userdata points to a server-owned binding record, is borrowed by the DDX, and remains valid and immutable until that exact binding has been removed and every callback frame has returned. The DDX MAY store the pointer in its private binding record solely to pass it back to the sink; it MUST NOT dereference, mutate, free, or use it after binding retirement. Operation-table entry points receive the exact device-binding context and opaque device handle directly. A shared DDX/module-role control record may be retained for code lifetime and quiescence, but it is not resolved as an extra dispatch object. Each completion MUST carry the exact DDX module-role generation, operation generation, and non-reusable operation-token identity captured at submission. The server-side token record MUST retain the exact logical-Device generation (if any) and the complete resource-generation set. The DDX binding MUST invoke the sink exactly once for each accepted operation token; it MUST NOT invoke it for an operation rejected synchronously. The completion payload MUST be self-contained and immutable; any variable payload storage MUST remain valid until the sink has copied it, and the sink MUST copy it before returning. The sink is enqueue-only and MUST NOT call back into backend operations synchronously. The callback identifies the token by its non-reusable `operation_token_id` plus `operation_generation`, never by a raw module-role pointer or public XID. The backend interface MUST also expose lifecycle hooks equivalent to `retain_module_role`, `release_module_role`, `retain_device`, `release_device`, and a quiescence/retirement notification. Exact names are implementation-defined. A raw backend handle MUST never escape the DDX backend boundary; the server stores opaque, generation-tagged backend object references.

### 4.2 Physical snapshot operation

`query_physical_snapshot` MUST run before publication and return a single internally consistent snapshot. The snapshot MUST include every value needed by all v0.1 physical-device enumeration and query requests and every device limit/capability used to validate later creation requests. It MUST be tied to the same DDX-local physical-device handle that will be passed to `create_logical_device`.

The operation MUST distinguish an unsupported optional property from a transient query failure. A missing optional property is recorded as unavailable/not supported according to the property registry; it MUST NOT be fabricated. A failure to obtain a mandatory baseline property, queue-family data, memory properties, or a coherent limit set makes that DDX backend ineligible for selection. The server MUST NOT publish a partial snapshot and MUST NOT fill missing fields from another DDX backend.

After publication, request handlers MUST answer physical-device property and queue/memory-property queries from the stored snapshot. They MUST NOT re-query a different DDX backend or silently refresh fields in place. DDX backend recovery MUST prove that the same DDX backend and same physical-device incarnation still honor the published snapshot before restoring AVAILABLE.

### 4.3 Logical-device creation and queue binding

Before calling `create_logical_device`, the server MUST complete all XAverius wire, XID, ownership, queue, feature, extension, and physical-device-state validation in the normative order in `devices.md` and `errors.md`. The DDX backend receives a fully validated immutable create description; it MUST include the exact native handle stored directly in the binding and registry binding generation, and the DDX binding MUST resolve that pair to the native physical-device handle retained for that binding. It MUST NOT independently choose a different PhysicalDevice, queue family, queue count, feature set, or extension set.

The DDX binding MUST create the logical device with the mandatory v0.1 `timelineSemaphore` feature enabled and exactly the validated queue requests and enabled optional features/extensions. It MUST return an opaque logical-device handle plus a queue handle for every requested (family,index) tuple, or fail atomically. Queue handles remain private to the DDX backend and are reachable only through the logical-device context.

The server publishes the logical Device XID only after DDX backend creation and all required queue acquisition succeed. If any stage fails, the server MUST destroy or quarantine every partial backend object, release temporary references when safe, leave the requested XID unallocated, and return the mapped error. The DDX binding MUST NOT retain a live logical device after reporting a failed create unless it is explicitly quarantined and inaccessible to all later XAverius operations.

### 4.4 DDX backend result and error contract

Every backend operation MUST return a classified result. A DDX binding MAY additionally retain the native backend/Vulkan result for diagnostics, but the native result MUST NOT bypass the classification or change the protocol mapping. At minimum, the internal result classes are:

| DDX backend result | Meaning | Required server treatment |
|---|---|---|
| `SUCCESS` | Operation completed successfully | Commit the request's specified success transition. |
| `STATUS` | A defined non-error operation outcome (for example acquire NOT_READY or presentation OUT_OF_DATE/SURFACE_LOST) | Return the operation-specific status exactly as defined by its request chapter; do not convert it to a generic DDX backend failure. |
| `UNSUPPORTED` | Operation/feature is genuinely unsupported by this DDX backend | During initial capability discovery, omit the optional capability or reject DDX-binding selection. After publication, treat as a DDX backend contract violation: fail the operation with `INTERNAL_SERVER_ERROR` and mark the DDX backend unavailable pending diagnosis; do not silently alter the published snapshot. |
| `UNAVAILABLE` | The shared module role cannot safely serve its bindings, or one exact PhysicalDevice binding is temporarily unavailable; no logical-Device-loss result has been established. The result MUST carry an explicit scope: `MODULE_ROLE` or `PHYSICAL_DEVICE`. | For `MODULE_ROLE`, mark every PhysicalDevice for which this exact DDX module-role generation is the selected DDX device binding UNAVAILABLE. For `PHYSICAL_DEVICE`, mark only the named PhysicalDevice binding UNAVAILABLE. Do not affect devices merely discovered by or attached to the another DDX or identity source. A request rejected before its protocol acceptance point uses its request-defined `DEVICE_UNAVAILABLE` error/reply status where defined. An already accepted asynchronous operation uses its operation-specific terminal channel (for example `EXECUTION_FAILED`, `TRANSFER_FAILED`, or `PRESENTATION_FAILED`), never a delayed X11 error. Existing logical Devices are not automatically declared lost solely by this result. |
| `DEVICE_LOST` | The backend has positively reported loss of this exact already-created logical Vulkan Device (for example, `VK_ERROR_DEVICE_LOST`); this result is invalid before a logical Device exists | Commit the logical Device's DEVICE_LOST transition exactly once. Reply-pending requests use their request-defined final reply/status or X11 error; protocol-accepted operations use their defined terminal status/events. |
| `OUT_OF_HOST_MEMORY` / `OUT_OF_DEVICE_MEMORY` | Backend allocation failed for lack of host/device memory | Map to `ALLOCATION_FAILED` where the request contract exposes a synchronous allocation error; otherwise use that operation's specified asynchronous failure result. |
| `TRANSFER_FAILURE` | A buffer upload/readback or other defined transfer operation failed without Device Loss | Map to `TRANSFER_FAILED` for reply-bearing transfer requests such as WriteBuffer/ReadBuffer; operations whose protocol contract is event-terminal use their defined asynchronous failure path. |
| `EXECUTION_FAILURE` | Accepted GPU execution failed without a Device-Loss classification | Use the request-defined terminal channel: for example, QueueSubmit uses submission events and Fence state, while WaitForFence returns `EXECUTION_FAILED`. Never emit a delayed X11 error for an operation that has already crossed its protocol acceptance point. |
| `CANCELLED` | Operation was prevented from starting because its captured Device/resource generation was destroyed or terminalized | Complete it with the lifecycle result already committed by the server (for example `DEVICE_DESTROYED`); never invoke backend work after cancellation wins. |
| `FATAL` | Unclassified backend/DDX backend failure or violated DDX backend contract | Fail with `INTERNAL_SERVER_ERROR` if a synchronous request is still awaiting a result; mark the DDX backend unavailable if its continued correctness cannot be trusted. Preserve all references until safe retirement. |

All fallible DDX device operations, including typed native-object destroy operations, MUST return a classified `GpuBackendResult`. The two lifecycle hooks use their dedicated result types: `retire_operation` returns `GpuBackendRetirementResult` (PENDING/SUCCESS/FAILURE), and `quiesce_module_role` returns `GpuModuleQuiescenceResult` (PENDING/SUCCESS/FAILURE). A destroy operation is best-effort with respect to an already committed public destroy: its failure MUST NOT resurrect an XID or create a delayed X11 error. The server retains/quarantines the backend object, exact binding, and owning module-role references until safe retirement. The `retain_*`/`release_*` reference hooks are local lifetime primitives rather than backend operations; they MUST be infallible and MUST NOT invoke Vulkan or block. `retire_operation` MUST be idempotent, MUST return a classified result, and MUST release only the exact operation-token generation supplied to it. If retirement fails, the server MUST retain/quarantine the token, exact binding, and owning module-role references rather than assuming quiescence.

`retire_operation` has one normative success meaning: `SUCCESS` confirms that the exact accepted operation token has no remaining or possible backend access, that the DDX backend will perform no further access through that token, that the token's completion callback has returned from module code, that no further callback for that token can begin, and that the token's backend-side retirement is complete. Only this result authorizes the server to release the token's retained DDX backend/device/resource references and retire the token record. Any non-`SUCCESS` result is not evidence of quiescence; the server MUST preserve the token record and quarantine all affected references. The server MAY retry retirement using the same exact token generation. Repeated retirement after `SUCCESS` MUST be an idempotent no-op returning `SUCCESS`; a stale token generation MUST NOT retire or release a newer token that reuses an internal slot. Retirement MUST NOT emit a second terminal outcome callback.

The abstract result type below carries this scope explicitly for both synchronous operation returns and asynchronous completion records. `PHYSICAL_DEVICE` results MUST identify the exact canonical PhysicalDevice and its generation in the operation's immutable result payload; `MODULE_ROLE` results MUST identify the exact DDX module-role generation. `NONE` is required for every result code other than `UNAVAILABLE`.

The scope of `UNAVAILABLE` is mandatory DDX backend-result metadata, not something the registry may guess from the module-role pointer. `MODULE_ROLE` means that the shared DDX module-role generation cannot safely serve any of its selected PhysicalDevice bindings; it affects only PhysicalDevices whose selected binding retains that exact module-role generation. `PHYSICAL_DEVICE` means that the shared module role remains usable but the named exact DDX PhysicalDevice binding cannot be used; it affects only that canonical PhysicalDevice. An observation for a non-selected DDX binding MUST NOT change the published PhysicalDevice status. A module-role recovery MAY restore each affected PhysicalDevice to AVAILABLE only if that same module-role generation and exact binding generation again satisfy the published immutable snapshot. A PhysicalDevice-scoped recovery restores only that exact binding generation. Recovery MUST NOT revive REMOVED identities or switch DDX-binding selection.

The DDX binding MUST NOT return X11 errors, XIDs, Atom errors, ownership errors, or request-validation errors. Those are server/protocol responsibilities and MUST be detected before invoking the DDX backend. A DDX binding MUST NOT map a malformed request to a Vulkan/backend error.

For `create_logical_device`, no logical Device exists yet, so `GPU_BACKEND_DEVICE_LOST` is an invalid result and MUST be treated as a DDX backend-contract violation (FATAL); it MUST NOT create a phantom logical Device or emit a Device-Loss event for the requested XID. If the DDX can no longer create a Device because the selected PhysicalDevice binding is unavailable, it MUST return `GPU_BACKEND_UNAVAILABLE` with `PHYSICAL_DEVICE` scope and the exact binding/device generations (or `MODULE_ROLE` scope for a role-wide failure); the server fails creation with `DEVICE_UNAVAILABLE` and leaves the target XID unallocated. Allocation failures map to `ALLOCATION_FAILED`; other classified creation failures map to `INTERNAL_SERVER_ERROR`. A native unsupported-feature result after the server has validated the published snapshot is a DDX backend contract violation, not a client `BadMatch`.

For operations on an already-created logical Device, a positive backend Device-Loss result applies to that exact logical Device. It MUST NOT automatically mark the PhysicalDevice REMOVED. Module-role-wide or exact-binding unavailability without proof that the logical Vulkan Device is lost instead makes the PhysicalDevice unavailable; existing logical Devices remain pinned and their operations fail according to their own subsequent backend results or safe-abort rules. DDX backend unavailability alone does not automatically declare an existing logical Device lost. A request that needs the unavailable DDX backend returns `DEVICE_UNAVAILABLE` while the selected binding or its owning module role remains unavailable; the logical Device retains its identity and may become usable again only if the same exact scope recovers. An accepted asynchronous operation that can no longer make progress because of DDX backend unavailability MUST terminalize through that operation's existing failure channel (for example, `EXECUTION_FAILED` for QueueSubmit or `TRANSFER_FAILED` for a buffer transfer), unless a positive loss result for that exact logical Device establishes `DEVICE_LOST`.

The server MUST preserve the first terminal outcome committed for each request, wait, submission, transfer, or resource operation. Later DDX backend callbacks MUST NOT replace success, timeout, Device Loss, destruction, disconnect, or an earlier failure. A DDX binding MUST NOT report success after it has reported a terminal failure for the same operation. For reply-pending requests, the winning DDX backend outcome is translated through that request's reply/status/error contract. For protocol-accepted QueueSubmit and QueuePresent operations, the winning outcome is translated through their asynchronous event and synchronization/image-state contracts.

### 4.5 Synchronous and asynchronous operations

An operation is synchronous when the XAverius request can be completed from the DDX binding's immediate result. Its DDX backend call MUST either complete or return a classified result; it MUST NOT retain request-owned input pointers after return. The server MUST hold the relevant DDX backend/device/resource references for the entire call.

An operation is deferred/asynchronous when its request remains pending while backend work or a wait registration progresses. This includes QueueSubmit, WriteBuffer, ReadBuffer, AcquireNextImage, and the deferred completion portion of QueuePresent. WaitSemaphores and WaitForFence are server-owned registrations over the server's published Timeline-counter/Fence state; they MUST NOT require a blocking DDX backend wait operation or a backend operation token. For each DDX backend-backed deferred operation, the DDX binding MUST return either an immediate classified rejection/status or an accepted DDX backend-operation token. DDX backend-token acceptance is an internal backend fact; it is NOT by itself XAverius protocol acceptance. For every accepted DDX backend-operation token, the DDX binding MUST eventually deliver exactly one terminal outcome notification to the server, including when backend execution or quiescence cannot be established. If the DDX backend cannot establish a successful outcome, it MUST report a classified terminal failure through that one notification; it MUST NOT silently omit the callback or wait indefinitely. A terminal outcome notification does not by itself prove backend quiescence. If the DDX backend cannot prove that no further backend access can occur, it MUST withhold the quiescence/retirement confirmation and the server MUST retain or quarantine all affected objects and DDX backend references until backend access is impossible. Server-owned WaitSemaphores/WaitForFence registrations do not call the DDX backend, do not create DDX backend-operation tokens, and do not receive DDX backend completion callbacks as registrations; they are reevaluated when the underlying queue/host-signal operation publishes updated server-visible synchronization state.

The protocol acceptance point is request-specific. QueueSubmit crosses it when the server accepts the void request; QueuePresent crosses it when the request returns SUCCESS. After either point, later execution/presentation failures use the defined events and synchronization/image state and MUST NOT become delayed X11 request errors. WriteBuffer, ReadBuffer, and AcquireNextImage remain reply-pending until their defined reply or error is committed; DDX backend-token acceptance for these requests does not suppress the request chapter's final reply, normal status, or permitted X11 error. WaitSemaphores and WaitForFence are also reply-pending, but are entirely server-owned registrations and have no DDX backend token. Disconnect suppresses delivery but does not bypass terminalization and safe retirement. Completion callbacks MUST carry immutable operation/DDX module-role generations and MUST resolve only through the server's internal operation-token record, never by public XID lookup.

Cancellation of a server-owned WaitSemaphores/WaitForFence registration is a server-side registration transition. It does not call the DDX backend, cancel or retire the underlying QueueSubmit or host SignalSemaphore operation, or release references held by that underlying operation. Those references remain governed by the operation's own completion and quiescence contract. For `AcquireNextImage`, `cancel_acquire` requests cancellation of the exact DDX backend-operation token generation; successful cancellation is not itself proof of quiescence and does not replace the one terminal completion/retirement notification. The DDX binding MUST guarantee that no later backend access can occur before the server releases references. A cancellation result indicating that acquisition already completed does not alter the server's first-terminal-outcome rule.

`AcquireNextImage` timeout arbitration remains server-owned. The DDX binding MUST NOT send a reply or independently commit the XAverius timeout result. If cancellation races a backend acquisition that has already acquired an image, the DDX binding MUST return that image to a reusable swapchain state through a safe backend release mechanism, or retain/quarantine the affected swapchain and its DDX backend resources until the acquired image can be safely retired. A presentation DDX backend that cannot guarantee safe retirement of a late acquired image MUST NOT advertise the presentation profile. This requirement applies even when the public acquire registration has already timed out, been destroyed, or been cancelled by disconnect.

The server owns WaitSemaphores and WaitForFence registrations, predicates, deadlines, and timeout arbitration. DDX backend completion callbacks publish the successful Timeline-counter/Fence state changes that reevaluate those registrations; the DDX binding MUST NOT implement a second competing host-wait registry or block waiting for those predicates. AcquireNextImage is different: it is a DDX backend-backed WSI operation, but the server still owns its XAverius timeout deadline and arbitration. The DDX binding MUST NOT return a final TIMEOUT status for the server-owned `AcquireNextImage` deadline. `WaitSemaphores` and `WaitForFence` have no DDX backend-side wait operation or DDX backend timeout. An AcquireNextImage backend operation may report STATUS/NOT_READY for a nonblocking poll that found no image, but only the server decides whether the XAverius result is NOT_READY (zero timeout) or TIMEOUT (finite deadline expiry). Backend OUT_OF_DATE and SURFACE_LOST remain DDX backend-reported lifecycle statuses. The server's serialized domain decides whether completion, timeout, Device Loss, DestroyDevice, or disconnect wins. A DDX backend acquire MUST NOT block the X11 request dispatcher.

DDX backend callbacks MAY run on arbitrary backend threads, but MUST only enqueue immutable completion records. They MUST NOT mutate XAverius state, release server resources directly, or write X11 events. The server's serialized event domain arbitrates the callback against Device Loss, DestroyDevice, disconnect, timeout, and other terminal events. Internal cleanup and public event delivery are separate: after public invalidation, callbacks may retire old internal state but MUST NOT emit events for the destroyed Device.

The server MUST retain a DDX backend/context reference, the exact logical Device generation, all backend object references used by the operation, and any dependent resource references from before DDX backend submission until callback retirement proves no backend access remains. A completion notification alone is sufficient to release these references only if the DDX backend contract guarantees that the backend no longer accesses them when the callback is delivered.

### 4.6 Lifetime, pinning, and teardown

A selected DDX binding is pinned by each published PhysicalDevice that names it. Each live logical Device takes an additional DDX backend reference and pins the exact PhysicalDevice incarnation and DDX module-role generation used at creation. Each asynchronous operation takes its own references to the DDX backend, logical Device, queue, and every resource/semaphore/fence/memory object the backend may access. A child resource MUST NOT outlive its owning logical Device publicly, but its internal backend object MAY remain retained after public invalidation.

DDX backend unload/context destruction is permitted only after all of the following are true:

1. No PhysicalDevice publication or registry callback can call into the DDX backend.
2. No live logical Device references the DDX backend.
3. Every DDX backend call currently executing has returned.
4. Every accepted asynchronous operation has reached a terminal state and the DDX backend has guaranteed no further access to its objects.
5. Every completion callback and deferred cleanup item carrying the DDX module-role generation has retired.
6. All DDX-owned logical Devices, queues, resources, and loader/dispatch references have been destroyed or placed in a DDX-owned quarantine that no longer requires executable DDX backend code.

A DDX binding MUST NOT wait indefinitely for a lost or wedged GPU as the only teardown strategy. It MAY retain/quarantine backend objects and the DDX module/context until the server exits or a backend-specific safe retirement condition is met. If quiescence cannot be proven, leaking/quarantining is required over use-after-free, stale callback execution, or unloading code still reachable by a callback.

Destroying a logical Device first invalidates its public XIDs according to `devices.md` and `resource-lifetime.md`; backend destruction is deferred until dependent operations and Vulkan object dependencies permit it. The DDX binding's `destroy_logical_device` operation is best-effort and MUST be safe after Device Loss. It MUST NOT turn successful public DestroyDevice into a protocol error, resurrect public resources, or emit new events. The DDX backend and its dispatch/module references remain pinned until the destroy operation and all earlier backend accesses have safely retired.

Disconnect follows the same internal reference and quiescence rules as DestroyDevice, but does not send replies/events to the disconnected client. Physical-device removal prevents new logical-device creation; it does not authorize premature destruction of backend objects still referenced by existing logical Devices or operations.

## 5. ScreenAttachment contract

A ScreenAttachment is a non-owning, generation-checked relation between a live Screen and a PhysicalDevice. It MAY record roles such as rendering, scanout/display control, or backend discovery association. Implementations SHOULD distinguish at least render-access, scanout/display-control, and discovery-only roles when the information is available. These roles describe topology only; they are not capability bits and do not change the PhysicalDevice identity or its XAverius properties.

A ScreenAttachment MUST NOT:

- create, publish, or destroy a PhysicalDevice;
- choose the PhysicalDevice's selected Vulkan DDX backend;
- imply that every window on the Screen can be presented by that device;
- imply that a compute-capable device is scanout-capable;
- imply that two devices attached to the same Screen can share resources;
- imply that a device attached to Screen 0 is preferred by CreateDefaultDevice.

Surface presentation support MUST continue to be evaluated for the exact logical Device/Surface pair by the presentation capability path. ScreenAttachment is discovery/topology information, not a substitute for a Vulkan surface-support query.

A DDX-native Surface object is scoped to the exact selected PhysicalDevice binding's native instance/context, not to one logical Device and not merely to the shared module role. A single XAverius Surface may therefore have separate DDX-native Surface objects when queried against Devices created through different binding generations, including different bindings owned by the same module role. Such objects MUST be keyed by the exact binding generation and retained Window/Screen generation; they MUST NOT be shared across binding generations or treated as proof that another binding supports presentation. Creation MAY be lazy at the first exact Device/Surface capability query. DestroySurface retires every DDX-native Surface object for that logical Surface only after no swapchain or in-flight WSI operation can reference it. Each object pins its exact binding and owning module role until destruction is safe.

A ScreenAttachment MUST be detached when its exact Screen generation is destroyed or replaced. A late detach event from an old Screen generation MUST NOT detach a newer Screen that reuses the same numeric server-side index or pointer slot.

### 5.1 Presentation target routing and cross-GPU boundary

A presentation target is the exact retained Window identity and its owning Screen generation. The server MUST NOT infer a presentation target from the first Screen, a default Screen, a RandR output number, or the first ScreenAttachment found for a PhysicalDevice. RandR outputs/monitors are not XAverius presentation targets in v0.1; the target is the X11 Window as a whole.

ScreenAttachment roles MUST distinguish at least the following topology facts when known: render access, scanout/display control, and discovery-only association. These roles describe which server path observes or services a PhysicalDevice; they are not capability bits and MUST NOT be used as a substitute for an exact Device/Surface query. A Screen may have separate render and scanout PhysicalDevices, and either may be absent from the XAverius inventory if it has no eligible execution DDX backend. The same PhysicalDevice may have different roles on different Screens.

The selected DDX device binding of the PhysicalDevice from which a logical Device was created remains the sole owner of that logical Device, its queues, and its swapchain-facing backend objects. A presentation route for a particular (logical Device, Surface) pair MUST be established through that selected DDX binding. The route MAY be implemented as native WSI on the render PhysicalDevice, or as an explicit DDX backend-managed bridge to the scanout/display path (for example, a PRIME/DRI3 import, copy, or composition path). Such a bridge is an implementation detail of the selected DDX binding's presentation operation; it MUST NOT create a synthetic PhysicalDevice, change the logical Device's PhysicalDevice, combine metadata snapshots, transfer Vulkan handles between DDX backends, or select another execution DDX backend as a fallback.

If the render PhysicalDevice and the Screen's scanout PhysicalDevice differ, the DDX binding MUST report presentation support only if it can establish and operate a complete route for the exact Window/Screen generation and the exact logical Device. The route must cover the advertised formats/color spaces, image usage, extent constraints, queue-family support, synchronization, image ownership/transfer, and completion/release guarantees. Merely finding a PRIME-capable DRM node, a scanout ScreenAttachment, a matching vendor/device ID, or another GPU on the same Screen is insufficient. A route that requires unsupported cross-device import/export or synchronization MUST be reported as unsupported.

The DDX binding's `query_surface_support` and capability operations MUST evaluate the actual route for every queue family. `present_supported = 1` means that the selected DDX binding can accept presentation from that queue family through the exact route and meet the full presentation lifetime contract. If no such route exists, the query returns a successful capability result with no present-capable queue family, and swapchain creation fails with `UNSUPPORTED_CONFIGURATION`; it MUST NOT silently migrate the logical Device to the scanout GPU or another Screen.

A successful `CreateSwapchain` binds the Swapchain to the exact presentation route generation selected for that Device/Surface pair. All images and accepted presentation operations for that Swapchain use that route. The route and its backend references remain pinned until the Swapchain and all in-flight presentation operations have safely retired. A later topology, bridge, or route-generation change MUST NOT silently reroute an existing Swapchain. It makes that Swapchain `OUT_OF_DATE` for new acquire/present operations; the client must query again and create a replacement Swapchain. A stale route callback MUST be rejected by its captured route, DDX backend, Surface, Screen, and Swapchain generations.

The server presentation subsystem allocates a fresh nonzero, non-reusable route generation before invoking the selected DDX binding's route-creation operation. It passes that generation to the DDX binding, which MUST store it in the opaque route wrapper and use it to reject stale route callbacks. The selected DDX binding is the route coordinator and MUST retain references to the exact target Screen, scanout binding, and any bridge resources. A server-side DDX/display adapter MAY participate through an explicit private bridge interface (for example, import/export of an OS shared-resource handle and a defined synchronization handoff); it MUST NOT receive or dereference another DDX binding's Vulkan dispatchable handles. Any cross-device resource transfer MUST have explicit importability, format/modifier, ownership, cache-coherency, and completion guarantees. If those guarantees cannot be established, the route is unsupported. The route coordinator remains responsible for ensuring that QueuePresent acceptance and terminal/image-release milestones cover the complete bridge path, not merely completion of the render-GPU copy submission.

A route that is temporarily unavailable is reported for the exact Device/Surface pair as `DEVICE_UNAVAILABLE`; this status does not by itself transition the render PhysicalDevice or logical Device to UNAVAILABLE/DEVICE_LOST. A route that is permanently unsupported returns `SUCCESS` with no present-capable queue from GetSurfaceCapabilities and `UNSUPPORTED_CONFIGURATION` from CreateSwapchain. If a pinned route generation changes, the associated live Swapchain becomes `OUT_OF_DATE`. If a route operation fails after QueuePresent acceptance without a more specific lifecycle cause, the accepted presentation terminates as `PRESENTATION_FAILED`. These mappings do not weaken the independent module-role/binding availability and exact logical-Device loss rules.

A route may be direct even when the ScreenAttachment topology names a different scanout GPU, provided the selected DDX binding proves a valid backend path. Conversely, a ScreenAttachment naming the same PhysicalDevice as the logical Device does not guarantee native WSI support. Compute availability and PhysicalDevice status remain independent of presentation-route availability: loss of a display/bridge path MUST NOT by itself mark the render PhysicalDevice `REMOVED` or the logical Device `DEVICE_LOST`. A route failure is reported through the presentation operation's defined status/error contract and invalidates only the affected Surface/Swapchain route state unless the DDX backend separately reports an exact logical-Device loss or PhysicalDevice/DDX backend unavailability.



## 6. Lifecycle and event serialization

All registry mutations that can affect PhysicalDevice status, publication, DDX-binding selection, ScreenAttachment membership, or XAverius events MUST be serialized through the X server's main/event thread or an equivalent server-owned serialization domain. Backend worker threads MAY detect conditions, but MUST enqueue immutable observations to that domain; they MUST NOT mutate registry objects or send X11 events directly.

The registry/presentation subsystem distinguishes at least these operations:

- register or update a complete DDX device binding for a canonical PhysicalDevice;
- mark the exact DDX binding or owning module role unavailable or recovered;
- confirm physical-device removal;
- attach or detach a Screen generation;
- create, pin, invalidate, or retire a PresentationRoute generation;
- publish a canonical PhysicalDevice to XAverius;
- retire DDX binding and route references after the required operation and module-role quiescence barriers.

DDX binding/module-role loss and physical-device removal are different events. A lost per-device context, failed Vulkan instance, or DDX module-role unload MUST NOT by itself mark hardware REMOVED. Conversely, a confirmed kernel/device removal MUST NOT be suppressed merely because another DDX registration still has a stale native handle.

The existing PhysicalDevice status state machine remains authoritative: AVAILABLE and UNAVAILABLE may recover between each other; either may transition to terminal REMOVED. REMOVED records remain tombstones until server shutdown. Registry state transitions and the corresponding `XAverius.deviceStatus` value/event MUST have one serialization point.

The registry/presentation subsystem MUST use generation-checked internal references for PhysicalDevice, GpuModuleRole, ScreenAttachment, PresentationRoute, Surface, and Swapchain lifetimes. Numeric XIDs, DRM node numbers, array indices, and raw pointers without a lifetime generation MUST NOT be used to resolve delayed callbacks. A callback captured for an old DDX backend/device/screen generation MUST NOT mutate a replacement object that reuses an address, index, node number, or public XID.

## 7. Suggested internal API boundary

The following is an abstract C interface sketch, not a public ABI and not a wire definition. Names and exact types MAY be adapted to Xserver conventions, but the ownership and semantic boundaries MUST be preserved.

```c
#include <stddef.h>

typedef struct GpuRegistry GpuRegistry;
typedef struct GpuPhysicalDevice GpuPhysicalDevice;
typedef struct GpuDeviceBackendBinding GpuDeviceBackendBinding;
typedef struct GpuModuleLease GpuModuleLease;
typedef struct GpuBackendOperationToken GpuBackendOperationToken;
typedef struct GpuPhysicalDeviceSnapshot GpuPhysicalDeviceSnapshot;
typedef struct GpuBackendDevice GpuBackendDevice;
typedef struct GpuBackendQueue GpuBackendQueue;
typedef struct GpuBackendSurface GpuBackendSurface;
typedef struct GpuBackendSwapchain GpuBackendSwapchain;
typedef struct GpuBackendBufferMemoryOps GpuBackendBufferMemoryOps;
typedef struct GpuBackendShaderPipelineOps GpuBackendShaderPipelineOps;
typedef struct GpuBackendCommandOps GpuBackendCommandOps;
typedef struct GpuBackendSynchronizationOps GpuBackendSynchronizationOps;
typedef struct GpuDeviceCreateInfo GpuDeviceCreateInfo;
typedef struct GpuBackendSubmitInfo GpuBackendSubmitInfo;
typedef struct GpuBackendSurfaceInfo GpuBackendSurfaceInfo;
typedef struct GpuBackendSurfaceSupport GpuBackendSurfaceSupport;
typedef struct GpuBackendSwapchainInfo GpuBackendSwapchainInfo;
typedef struct GpuBackendAcquireInfo GpuBackendAcquireInfo;
typedef struct GpuBackendPresentInfo GpuBackendPresentInfo;
typedef struct GpuModuleRole GpuModuleRole;
typedef struct GpuScreenAttachment GpuScreenAttachment;
typedef struct GpuBackendPresentationRoute GpuBackendPresentationRoute;

/* Registry API outcomes. PENDING/AMBIGUOUS retain an unpublished observation;
   neither outcome allocates an XID. Stale or invalid removal evidence is
   rejected without changing the current PhysicalDevice incarnation. */
typedef enum {
    GPU_REGISTRY_SUCCESS,
    GPU_REGISTRY_PENDING,
    GPU_REGISTRY_AMBIGUOUS,
    GPU_REGISTRY_STALE_GENERATION,
    GPU_REGISTRY_INVALID_EVIDENCE,
    GPU_REGISTRY_IDENTITY_CONFLICT,
    GPU_REGISTRY_OUT_OF_MEMORY,
    GPU_REGISTRY_INVALID_ARGUMENT,
    GPU_REGISTRY_NOT_FOUND,
    GPU_REGISTRY_ALREADY_EXISTS,
    GPU_REGISTRY_NOT_REGISTERED,
    GPU_REGISTRY_SHUTTING_DOWN,
    GPU_REGISTRY_BUSY,
    GPU_REGISTRY_UNAVAILABLE,
    GPU_REGISTRY_UNSUPPORTED,
    GPU_REGISTRY_QUARANTINED,
    GPU_REGISTRY_STALE_EVENT,
    GPU_REGISTRY_INTERNAL_ERROR
} GpuRegistryResult;

/* Server-owned loader pin shared by all roles in one loaded module.
   module_owner is a stable server-owned loader-owner record, never a
   ScrnInfo/DriverPtr/ModuleDesc. Creation acquires a real independent loader
   pin and returns one owned ref. NULL means no lease/pin was acquired;
   retain/release never enter module code. */
GpuModuleLease *GpuModuleLeaseCreate(
    void *module_owner, GpuRegistryResult *out_result);
GpuRegistryResult GpuModuleLeaseRetain(GpuModuleLease *lease);
GpuRegistryResult GpuModuleLeaseRelease(GpuModuleLease *lease);

typedef enum {
    GPU_MODULE_ROLE_DISCOVERY_SOURCE,
    GPU_MODULE_ROLE_DDX_TOPOLOGY,
    GPU_MODULE_ROLE_CALLBACK_BRIDGE,
    GPU_MODULE_ROLE_DDX_BACKEND
} GpuModuleRoleKind;

enum {
    GPU_DISCOVERY_SOURCE_PLATFORM_IDENTITY = 1u << 0,
    GPU_DISCOVERY_SOURCE_HOTPLUG_EVENTS = 1u << 1,
    GPU_DISCOVERY_SOURCE_REMOVAL_EVIDENCE = 1u << 2,
    GPU_DISCOVERY_SOURCE_VULKAN_CORRELATION = 1u << 3
};

enum {
    GPU_SCREEN_ROLE_RENDER_ACCESS = 1u << 0,
    GPU_SCREEN_ROLE_SCANOUT = 1u << 1,
    GPU_SCREEN_ROLE_DISPLAY_CONTROL = 1u << 2,
    GPU_SCREEN_ROLE_DISCOVERY_ONLY = 1u << 3
};

/* Opaque internal identity descriptor, not a wire structure. Its concrete
   versioned definition is implementation-private but MUST represent the
   evidence classes and provenance rules in Sections 2.2 and 2.3. */
typedef struct GpuDeviceIdentity GpuDeviceIdentity;


typedef struct {
    /* Provenance of the authoritative removal observation. source_key is
       borrowed for this call only; the registry resolves it to its registered
       source identity before returning. The evidence must identify the exact
       source observation and PhysicalDevice incarnation. */
    const char *source_key;
    uint64_t source_generation;
    uint64_t observation_id;
    uint64_t source_event_sequence;
    uint64_t physical_device_generation;
} GpuDeviceRemovalEvidence;

typedef struct {
    uint64_t screen_generation;
    uint64_t scanout_device_generation; /* zero when no separate scanout device is used */
    uint32_t route_kind; /* direct WSI or DDX backend-managed bridge; private enum */
} GpuBackendPresentationRouteInfo;

/* Classified DDX backend result. Native VkResult may be retained for diagnostics. */
/* STATUS is a non-error, operation-specific status only where the
   corresponding operation contract defines its meaning; it never means an
   asynchronous operation was accepted. CANCELLED is terminal. FATAL denotes
   a DDX backend-contract violation or unrecoverable DDX backend failure. */
typedef enum {
    GPU_BACKEND_SUCCESS,
    GPU_BACKEND_UNSUPPORTED,
    GPU_BACKEND_STATUS,
    GPU_BACKEND_UNAVAILABLE,
    GPU_BACKEND_DEVICE_LOST,
    GPU_BACKEND_OUT_OF_HOST_MEMORY,
    GPU_BACKEND_OUT_OF_DEVICE_MEMORY,
    GPU_BACKEND_TRANSFER_FAILURE,
    GPU_BACKEND_EXECUTION_FAILURE,
    GPU_BACKEND_CANCELLED,
    GPU_BACKEND_FATAL
} GpuBackendResultCode;

typedef enum {
    GPU_BACKEND_UNAVAILABLE_SCOPE_NONE = 0,
    GPU_BACKEND_UNAVAILABLE_SCOPE_MODULE_ROLE = 1,
    GPU_BACKEND_UNAVAILABLE_SCOPE_PHYSICAL_DEVICE = 2
} GpuBackendUnavailableScope;

typedef enum {
    GPU_BACKEND_STATUS_NOT_READY = 1,
    GPU_BACKEND_STATUS_OUT_OF_DATE = 2,
    GPU_BACKEND_STATUS_SURFACE_LOST = 3,
    GPU_BACKEND_STATUS_ALREADY_COMPLETED = 4
} GpuBackendStatusCode;

typedef struct {
    GpuBackendResultCode code;
    /* Nonzero only when code is STATUS; values are operation-specific. */
    uint32_t status_code;
    /* Nonzero only for UNAVAILABLE; monotonic within its exact context or
       binding availability scope. */
    uint64_t availability_sequence;
    /* Diagnostic only; MUST NOT override the classified code/status. */
    int32_t native_result;
    /* MUST be NONE except when code is UNAVAILABLE. */
    GpuBackendUnavailableScope unavailable_scope;
    /* Required for PHYSICAL_DEVICE scope; identifies the exact DDX-local
       binding within this DDX module-role generation. Zero for other scopes. */
    uint64_t binding_generation;
    uint64_t physical_device_generation;
} GpuBackendResult;

typedef enum {
    GPU_BACKEND_OP_WRITE_BUFFER = 1,
    GPU_BACKEND_OP_READ_BUFFER,
    GPU_BACKEND_OP_HOST_SIGNAL_SEMAPHORE,
    GPU_BACKEND_OP_QUEUE_SUBMIT,
    GPU_BACKEND_OP_ACQUIRE_NEXT_IMAGE,
    GPU_BACKEND_OP_QUEUE_PRESENT
} GpuBackendOperationKind;

typedef struct {
    uint64_t module_role_generation;
    uint64_t operation_generation;
    uint64_t operation_token_id;
    GpuBackendOperationKind operation_kind;
    uint64_t binding_generation;
    uint64_t physical_device_generation;
    uint64_t logical_device_id;         /* server-assigned; zero for non-Device operations */
    uint64_t logical_device_generation;
    uint64_t resource_id;               /* server-assigned; zero when no resource is targeted */
    uint64_t resource_generation;
    GpuBackendResult result;
    /* Borrowed immutable bytes; valid only until completion_sink returns.
       NULL/zero when the operation has no payload. */
    const void *payload;
    uint32_t payload_size;
} GpuBackendCompletion;

typedef void (*GpuBackendCompletionFn)(
    void *completion_userdata,
    const GpuBackendCompletion *completion);

typedef enum {
    GPU_BACKEND_QUIESCENCE_PENDING,
    GPU_BACKEND_QUIESCENCE_SUCCESS,
    GPU_BACKEND_QUIESCENCE_FAILURE
} GpuModuleQuiescenceResult;

typedef enum {
    GPU_BACKEND_RETIREMENT_PENDING,
    GPU_BACKEND_RETIREMENT_SUCCESS,
    GPU_BACKEND_RETIREMENT_FAILURE
} GpuBackendRetirementResult;

typedef struct GpuDeviceBackendOps {

    GpuBackendResult (*query_physical_snapshot)(
        GpuDeviceBackendBinding *, GpuPhysicalDeviceSnapshot *);
    GpuBackendResult (*create_logical_device)(
        GpuDeviceBackendBinding *, const GpuDeviceCreateInfo *,
        GpuBackendDevice **);
    GpuBackendResult (*get_queue)(
        GpuBackendDevice *, uint32_t family, uint32_t index,
        GpuBackendQueue **);
    GpuBackendResult (*destroy_logical_device)(GpuBackendDevice *);

    /* Separate typed operation tables, not a generic wire-payload dispatcher:
       buffer_memory: create/query/allocate/free/bind/read/write Buffer and Memory;
       shader_pipeline: Shader, Descriptor, Pipeline create/update/destroy;
       commands: CommandPool/CommandBuffer lifecycle and command recording;
       synchronization: Semaphore/Fence lifecycle, host timeline signal,
       queue signal/wait integration, fence reset, and completion publication.
       Each table implements the corresponding operations listed in Section 4.1. */
    const GpuBackendBufferMemoryOps *buffer_memory;
    const GpuBackendShaderPipelineOps *shader_pipeline;
    const GpuBackendCommandOps *commands;
    const GpuBackendSynchronizationOps *synchronization;

    GpuBackendResult (*queue_submit)(
        GpuBackendQueue *, const GpuBackendSubmitInfo *,
        GpuBackendOperationToken *);
    GpuBackendResult (*create_surface)(
        GpuDeviceBackendBinding *, const GpuBackendSurfaceInfo *,
        GpuBackendSurface **);
    GpuBackendResult (*destroy_surface)(GpuDeviceBackendBinding *, GpuBackendSurface *);
    GpuBackendResult (*query_surface_support)(
        GpuDeviceBackendBinding *, uint32_t queue_family,
        GpuBackendSurface *, GpuBackendSurfaceSupport *);
    /* Create/release an exact route for this logical Device generation and
       Surface/Window/Screen generation after physical-device capability
       probing. The route MUST be distinct per logical Device, even when two
       Devices share one PhysicalDevice and Surface. create_swapchain pins
       this route until swapchain retirement. */
    GpuBackendResult (*create_presentation_route)(
        GpuBackendDevice *, GpuBackendSurface *,
        uint64_t server_route_generation,
        GpuBackendPresentationRoute **,
        GpuBackendPresentationRouteInfo *);
    GpuBackendResult (*destroy_presentation_route)(
        GpuDeviceBackendBinding *, GpuBackendPresentationRoute *);
    GpuBackendResult (*create_swapchain)(
        GpuBackendDevice *, GpuBackendSurface *,
        GpuBackendPresentationRoute *,
        const GpuBackendSwapchainInfo *, GpuBackendSwapchain **);
    GpuBackendResult (*destroy_swapchain)(GpuBackendSwapchain *);
    GpuBackendResult (*acquire_next_image)(
        GpuBackendDevice *, GpuBackendSwapchain *,
        const GpuBackendAcquireInfo *, GpuBackendOperationToken *);
    GpuBackendResult (*queue_present)(
        GpuBackendQueue *, const GpuBackendPresentInfo *,
        GpuBackendOperationToken *);
    GpuBackendResult (*cancel_acquire)(GpuBackendOperationToken *);
    GpuBackendResult (*release_late_acquired_image)(
        GpuBackendSwapchain *, uint32_t image_index);

    /* Logical-device wrapper references are infallible lifetime primitives. */
    void (*retain_device)(GpuBackendDevice *);
    void (*release_device)(GpuBackendDevice *);
    GpuBackendRetirementResult (*retire_operation)(GpuBackendOperationToken *);
} GpuDeviceBackendOps;

typedef struct {
    const char *owner_key;
    GpuModuleLease *module_lease;
    void (*retain_module_role)(GpuModuleRole *);
    void (*release_module_role)(GpuModuleRole *);
    GpuModuleQuiescenceResult (*quiesce_module_role)(GpuModuleRole *);
} GpuModuleRoleDescriptor;

typedef struct {
    const GpuDeviceIdentity *identity;
    const GpuDeviceBackendOps *ops;
    void *device_context;
    void *native_physical_device;
    GpuModuleRole *owner_role;
    uint64_t owner_role_generation;
    GpuBackendCompletionFn completion_sink; /* server-owned sink code; valid for the binding lifetime */
    void *completion_userdata; /* borrowed server-owned binding record; DDX only passes it back to the sink */
} GpuDeviceBackendRegistration;

/* The DDX enumerates its own devices and calls RegisterDdxDevice once per
   served PhysicalDevice. The registry does not enumerate ICD candidates and
   does not resolve a DDX-local integer ID to a native handle. */

/* Server startup/shutdown; one registry per X server process. */
/* No generic role-context accessor exists: device context is supplied directly by the binding. */
typedef struct {
    /* Ordered server-configured preference; strings are stable owner_key
       values of GPU_MODULE_ROLE_DDX_BACKEND roles. NULL/zero means no list. */
    const char *const *ddx_binding_preference_owner_keys;
    uint32_t ddx_binding_preference_count;
} GpuRegistryCreateInfo;

GpuRegistry *GpuRegistryCreate(
    const GpuRegistryCreateInfo *create_info,
    GpuRegistryResult *out_result);
GpuRegistryResult GpuRegistryBeginShutdown(GpuRegistry *registry);
GpuRegistryResult GpuRegistryDestroy(GpuRegistry *registry);

/* A module role pins callback-capable adapter code independently of Screen
   and DriverPtr references. owner_key is copied; role_generation is assigned
   by the registry. The lease is retained once for this role; NULL is permitted only for permanently resident code. */
GpuRegistryResult GpuRegistryRegisterModuleRole(
    GpuRegistry *registry, const GpuModuleRoleDescriptor *descriptor,
    GpuModuleRoleKind role_kind,
    GpuModuleRole **out_role, uint64_t *out_role_generation);
GpuRegistryResult GpuModuleRoleRetain(
    GpuModuleRole *role, uint64_t role_generation);
GpuRegistryResult GpuModuleRoleRelease(
    GpuModuleRole *role, uint64_t role_generation);

/* Discovery sources are explicit registrations; generations are server-assigned.
   An unloadable source MUST be associated with its owning module role. */
GpuRegistryResult GpuRegistryRegisterDiscoverySource(
    GpuRegistry *registry, const char *source_key,
    uint32_t source_capabilities, GpuModuleRole *owner_role,
    uint64_t owner_role_generation, uint64_t *out_source_generation);
GpuRegistryResult GpuRegistryUnregisterDiscoverySource(
    GpuRegistry *registry, const char *source_key,
    uint64_t source_generation);

/* Discovery-source observation. Returns a canonical, generation-checked
   record only when identity matching is unambiguous; pending/ambiguous
   candidates remain unpublished and receive no protocol XID. */
GpuRegistryResult GpuRegistryObserveDevice(
    GpuRegistry *registry, const char *source_key,
    uint64_t source_generation, uint64_t source_event_sequence,
    const GpuDeviceIdentity *identity,
    GpuPhysicalDevice **out_device, uint64_t *out_device_generation,
    uint64_t *out_observation_id);
GpuRegistryResult GpuPhysicalDeviceRetain(
    GpuPhysicalDevice *device, uint64_t device_generation);
GpuRegistryResult GpuPhysicalDeviceRelease(
    GpuPhysicalDevice *device, uint64_t device_generation);

/* Module-role generation is assigned by RegisterModuleRole and is never reused. */

GpuRegistryResult GpuRegistryRegisterDdxDevice(
    GpuRegistry *registry, const GpuDeviceBackendRegistration *registration,
    GpuPhysicalDevice **out_device, uint64_t *out_device_generation,
    uint64_t *out_binding_generation);



enum {
    GPU_BACKEND_RESOURCE_ACCESS_READ = 1u << 0,
    GPU_BACKEND_RESOURCE_ACCESS_WRITE = 1u << 1,
    GPU_BACKEND_RESOURCE_ACCESS_EXECUTE = 1u << 2,
    GPU_BACKEND_RESOURCE_ACCESS_WAIT = 1u << 3,
    GPU_BACKEND_RESOURCE_ACCESS_SIGNAL = 1u << 4
};

typedef struct {
    uint64_t resource_id;
    uint64_t resource_generation;
    uint32_t access_flags; /* GPU_BACKEND_RESOURCE_ACCESS_* bitmask */
} GpuBackendOperationResourceRef;

/* Prepare a server-owned operation token before entering DDX backend code.
   out_token is a borrowed, call-scoped opaque pointer; DDX backend code MUST NOT
   retain or dereference it after the operation entry point returns. The
   DDX backend copies token ID/generation through GpuBackendOperationTokenGetId()
   and GpuBackendOperationTokenGetGeneration() for backend callback userdata.
   The server-owned token itself remains alive until successful retirement.
   On failure all outputs are zero. The complete resource set is copied and
   retained by the registry before return. Each entry's access_flags MUST
   contain only declared GPU_BACKEND_RESOURCE_ACCESS_* bits and MUST be
   nonzero. resources is non-NULL iff resource_count is nonzero; duplicate resource IDs (including the same ID with a different
   generation), zero IDs/generations, invalid access flags, and resources
   owned by another logical Device are INVALID_ARGUMENT/IDENTITY_CONFLICT. The server enforces
   a documented implementation maximum before copying the array. Every
   currently defined operation kind requires a nonzero logical-Device
   ID/generation pair and at least one resource reference. WRITE_BUFFER and
   READ_BUFFER pin the Buffer and backing Memory; HOST_SIGNAL_SEMAPHORE pins
   the target Semaphore; QUEUE_SUBMIT pins the Queue and the complete validated
   command/dependency graph; ACQUIRE_NEXT_IMAGE and QUEUE_PRESENT pin the exact
   Swapchain and all image/synchronization/route objects that backend access
   may touch. A resource ID MUST NOT appear more than once even with different
   generations. */
GpuRegistryResult GpuRegistryPrepareOperation(
    GpuRegistry *registry, uint64_t module_role_generation,
    GpuPhysicalDevice *device, uint64_t device_generation,
    uint64_t binding_generation,
    uint64_t logical_device_id, uint64_t logical_device_generation,
    const GpuBackendOperationResourceRef *resources,
    size_t resource_count, GpuBackendOperationKind operation_kind,
    GpuBackendOperationToken **out_token,
    uint64_t *out_operation_token_id,
    uint64_t *out_operation_generation);
GpuRegistryResult GpuBackendOperationTokenGetId(
    const GpuBackendOperationToken *token, uint64_t *out_token_id);
GpuRegistryResult GpuBackendOperationTokenGetGeneration(
    const GpuBackendOperationToken *token, uint64_t *out_generation);
/* Commit is idempotent for the exact already-accepted token. */
GpuRegistryResult GpuRegistryCommitOperationSubmission(
    GpuRegistry *registry, uint64_t module_role_generation,
    uint64_t operation_token_id, uint64_t operation_generation);
/* Reject is legal only before acceptance and only if no callback/backend
   access occurred. Otherwise the token is quarantined. */
GpuRegistryResult GpuRegistryRejectOperationSubmission(
    GpuRegistry *registry, uint64_t module_role_generation,
    uint64_t operation_token_id, uint64_t operation_generation);
/* SUCCESS maps retirement SUCCESS; PENDING maps retirement PENDING;
   QUARANTINED maps retirement FAILURE. */
GpuRegistryResult GpuRegistryRetireOperationToken(
    GpuRegistry *registry, uint64_t module_role_generation,
    uint64_t operation_token_id, uint64_t operation_generation);

/* Close admission for this exact DDX module-role generation. This does not
   remove bindings, retire accepted operations, or prove quiescence. */
GpuRegistryResult GpuRegistryBeginModuleRoleShutdown(
    GpuRegistry *registry, uint64_t module_role_generation);

/* Drives module-role-wide quiescence after the registry has verified the
   shutdown/drain preconditions. PENDING/FAILURE retain the module lease. */
GpuRegistryResult GpuRegistryTryQuiesceModuleRole(
    GpuRegistry *registry, uint64_t module_role_generation,
    GpuModuleQuiescenceResult *out_quiescence);

/* Final module-role release hook followed by exactly one module-lease
   release. Returns PENDING until all non-registry DDX backend references retire. */
GpuRegistryResult GpuRegistryFinalizeModuleRoleShutdown(
    GpuRegistry *registry, uint64_t module_role_generation);

GpuRegistryResult GpuRegistryRemoveDeviceBackendBinding(
    GpuRegistry *registry, GpuPhysicalDevice *device,
    uint64_t device_generation, uint64_t module_role_generation,
    uint64_t binding_generation);
GpuRegistryResult GpuDeviceBackendBindingRetain(
    GpuDeviceBackendBinding *binding, uint64_t binding_generation);
GpuRegistryResult GpuDeviceBackendBindingRelease(
    GpuDeviceBackendBinding *binding, uint64_t binding_generation);

GpuRegistryResult GpuRegistryRemoveObservation(
    GpuRegistry *registry, const char *source_key,
    uint64_t source_generation, uint64_t observation_id);

/* DDX module-role availability is distinct from physical removal. All state-
   changing calls return a classified result; stale generations and unknown
   bindings are observable rejections, never silent no-ops.
   Context-wide failure/recovery affects all PhysicalDevices for which this
   exact DDX module-role generation is the selected DDX device binding. */
GpuRegistryResult GpuRegistryModuleRoleUnavailable(
    GpuRegistry *registry, uint64_t module_role_generation,
    uint64_t availability_sequence);
GpuRegistryResult GpuRegistryModuleRoleRecovered(
    GpuRegistry *registry, uint64_t module_role_generation,
    uint64_t availability_sequence);

/* Device-scoped failure/recovery affects only this exact binding generation. */
GpuRegistryResult GpuRegistryDeviceBackendUnavailable(
    GpuRegistry *registry, uint64_t module_role_generation,
    GpuPhysicalDevice *device, uint64_t device_generation,
    uint64_t binding_generation, uint64_t availability_sequence);
GpuRegistryResult GpuRegistryDeviceBackendRecovered(
    GpuRegistry *registry, uint64_t module_role_generation,
    GpuPhysicalDevice *device, uint64_t device_generation,
    uint64_t binding_generation, uint64_t availability_sequence);
GpuRegistryResult GpuRegistryConfirmDeviceRemoved(
    GpuRegistry *registry, GpuPhysicalDevice *device,
    uint64_t device_generation,
    const GpuDeviceRemovalEvidence *removal_evidence);

/* Screen relationships are non-owning and generation checked. Roles use
   GPU_SCREEN_ROLE_*; they describe topology, not presentation capability.
   screen is borrowed for this call only to validate/associate the live Screen;
   the registry MUST NOT retain ScreenPtr or any Screen-private pointer.
   The returned attachment retains only server-owned identity and generation
   data. Any DDX-side Screen lookup must remain in a separate adapter map and
   must be invalidated before FreeScreen() releases the Screen storage. */
GpuRegistryResult GpuRegistryAttachScreen(
    GpuRegistry *registry, GpuPhysicalDevice *device,
    uint64_t device_generation, ScreenPtr screen,
    uint64_t screen_generation, unsigned int roles,
    GpuModuleRole *owner_role, uint64_t owner_role_generation,
    GpuScreenAttachment **out_attachment,
    uint64_t *out_attachment_generation);
GpuRegistryResult GpuRegistryDetachScreen(
    GpuRegistry *registry, uint64_t attachment_generation);
GpuRegistryResult GpuScreenAttachmentRetain(
    GpuScreenAttachment *attachment, uint64_t attachment_generation);
GpuRegistryResult GpuScreenAttachmentRelease(
    GpuScreenAttachment *attachment, uint64_t attachment_generation);

/* Publication atomically inserts the server resource and returns its stable XID. */
GpuRegistryResult XaPhysicalDevicePublish(
    GpuPhysicalDevice *device, uint64_t device_generation, XID *out_xid);
GpuRegistryResult XaPhysicalDeviceGetXid(
    GpuPhysicalDevice *device, uint64_t device_generation, XID *out_xid);

/* A route is scoped to the exact Device/Surface/Window/Screen generations.
   A successful Swapchain pins it until all presentation and image-release
   milestones have retired; stale route callbacks are generation-rejected. */

/* Logical-device creation pins the selected DDX binding and generations. */
GpuRegistryResult GpuPhysicalDeviceAcquireBackendBinding(
    GpuPhysicalDevice *device, uint64_t device_generation,
    GpuDeviceBackendBinding **out_binding, uint64_t *out_binding_generation);
```



### 7.1 Common API result, reference, and transaction rules

The declarations above define ownership and failure semantics, not merely illustrative return types. These rules apply to every registry and XAverius-internal API entry point:

- Every output parameter MUST be initialized to its documented failure sentinel before validation. On non-`SUCCESS`, pointer outputs are NULL, generations/IDs are zero, and XID outputs are `None`/zero, except where `PENDING` or `AMBIGUOUS` explicitly means a valid observation was retained. Callers MUST NOT inspect outputs not authorized by the returned result.
- `SUCCESS` means the state transition committed in the registry serialization domain; it does not mean asynchronous GPU work completed. `PENDING` means a valid request/observation was retained but its condition is unresolved. `AMBIGUOUS` means canonical identity resolution or pre-publication DDX-binding selection is not unique; no XID is published. Only state explicitly documented by the specific operation is retained (for example, `ObserveDevice` retains an observation ID, while an ambiguous `RegisterDdxDevice` installs no binding). Other errors leave requested state unchanged, except non-reusable generation reservations and explicitly retained pending/ambiguous observations.
- `INVALID_ARGUMENT` covers null required pointers, zero/invalid generations, malformed keys, unknown role bits, and inconsistent input/output combinations. The discovery-source capability bits are limited to the declared `GPU_DISCOVERY_SOURCE_*` values; unknown bits are invalid. `NOT_FOUND` means a well-formed object/key does not exist; `NOT_REGISTERED` means a required source/DDX module-role registration is absent; `ALREADY_EXISTS` means a conflicting live registration owns a unique key; `STALE_GENERATION` means only a different generation exists; `BUSY` means a live dependency prevents the requested transition; `UNAVAILABLE` means the requested PhysicalDevice/binding is temporarily unusable, including a registration attempt whose snapshot query could not complete, or an existing canonical device/selected binding that has entered an unavailable state; `SHUTTING_DOWN` means admission is closed; `UNSUPPORTED` means the requested role/operation is not implemented or a complete device snapshot cannot satisfy mandatory v0.1 baseline requirements; `QUARANTINED` means a DDX backend explicitly failed quiescence and cannot be finalized; `STALE_EVENT` means an older availability notification was superseded within the same scope; `OUT_OF_MEMORY` means allocation failed. Implementations MUST preserve these distinctions rather than silently ignore errors.
- All mutations are linearized in the server serialization domain. Calls from other threads MUST NOT mutate registry state directly. A synchronous caller may wait for serialization only where that cannot deadlock; otherwise the API MUST use an explicitly asynchronous completion form and MUST NOT report `SUCCESS` before commit. No structural registry lock may be held while invoking DDX backend code, Xorg hooks, loader operations, or completion callbacks.
- Every object pointer returned by an API is a retained caller-owned reference unless explicitly documented otherwise. The caller MUST release it exactly once through its matching release function, passing the same generation returned with the reference; registry-owned references are separate. Retain/release functions validate that generation. Every delayed use MUST carry the associated generation. A pointer alone is never a stable identity. Stale/double release MUST be diagnosed and MUST NOT decrement another generation's count. New retains are accepted only while the referenced object is in a state that admits new work: Device-binding retain is rejected after exact binding removal or owning module-role shutdown/quarantine begins; ScreenAttachment retain is rejected after detach begins; ModuleRole retain is rejected after role unregister begins. Releases of already-held references remain permitted during teardown. PhysicalDevice tombstones remain retainable while their exact generation remains registry-addressable, but cannot be used to acquire execution DDX backends or create new bindings/devices.
- Input pointers and strings are borrowed only for the call unless explicitly transferred. Every retained key, identity field, role descriptor, and variable-length input MUST be copied or separately retained before return. The registry copies the complete top-level and nested operation-table descriptors by value into immutable binding-owned storage; the DDX MUST keep every referenced function target executable through the owning module-role lease. Callback code, callback userdata, per-device context, and native handles MUST remain valid and immutable until the exact binding and module-role references retire. The registry MUST NOT free DDX-owned context or native handles.
- Mutations are atomic. Validation/allocation failure MUST roll back all partial entries, reference increments, module-lease retains, observations, bindings, XID/resource allocation, and callback registration. Only reserved non-reusable generations and explicitly retained `PENDING`/`AMBIGUOUS` observations survive a non-success return.
- Repeated calls are idempotent only where specified. Same-generation/same-payload repetition MUST NOT duplicate objects or ownership references, except where the specific operation contract explicitly grants one additional caller-owned reference for the repeated successful call; conflicting payload returns `ALREADY_EXISTS` or `IDENTITY_CONFLICT`. A stale generation is never idempotent success for a replacement.
- `GpuRegistryBeginShutdown` closes admission for new module roles, discovery sources, observations, DDX device bindings, ScreenAttachments, backend-binding acquisitions, and operation-token preparation. It does not implicitly remove existing objects or skip DDX backend quiescence. Module-role shutdown, quiescence, and finalization remain explicit; shutdown MUST NOT drop a lease on behalf of an adapter or DDX binding. `GpuRegistryDestroy` succeeds only after shutdown and full retirement; otherwise it returns `BUSY` and leaves the registry intact. Process exit may be the final reclamation boundary, but MUST NOT invoke unloaded DDX backend code.

Specific operation contracts:

- `GpuRegistryCreate` returns one owner reference or NULL plus a classified result; only one process-wide registry may be active. A second create while one is active returns `ALREADY_EXISTS` and no pointer. The create_info preference list is copied before return. A NULL create_info or zero count means an empty list; a nonzero count requires a non-NULL array of non-empty, unique owner_key strings. Malformed/duplicate entries return `INVALID_ARGUMENT`, allocation failure returns `OUT_OF_MEMORY`, and no partial registry is returned. Unknown keys are permitted so configuration may name an optional/unloaded DDX role; they simply do not match any binding. The list is immutable for the registry lifetime and applies to initial and later hotplugged incarnations; changing it requires registry recreation after full shutdown.
- Module-role registration assigns a fresh nonzero role generation; an unknown role kind or malformed/empty owner_key returns `INVALID_ARGUMENT`, while a duplicate active owner_key returns `ALREADY_EXISTS`. A DDX backend role owner_key MUST be a stable, non-empty, case-sensitive identifier; the server copies it and uses it only for explicit pre-publication DDX binding preference matching. For unloadable code, the descriptor MUST provide a valid independent module lease and the required retain/release/quiesce hooks; the registry retains exactly one lease reference. A NULL lease is permitted only for code guaranteed to remain resident until server shutdown, and that role is marked permanent and is never dynamically quiesced or unloaded. It returns one retained caller-owned role reference; the caller releases it through `GpuModuleRoleRelease`. Discovery-source and DDX-topology roles MUST be associated with the module role that owns their callback code; server-resident code MAY use a null role. Shutdown is initiated only through `GpuRegistryBeginModuleRoleShutdown`, addressed by the exact role generation; at its serialized commit it closes callback/operation/binding admission and marks the module role unavailable, transitioning every PhysicalDevice whose selected binding retains that exact role generation to `UNAVAILABLE`. Non-selected bindings and their PhysicalDevices are unaffected; no device is marked `REMOVED` and no fallback binding is selected. The operation does not release the module lease. Repeating BeginModuleRoleShutdown for the same generation returns idempotent `SUCCESS`; a stale generation returns `STALE_GENERATION`, an unknown generation returns `NOT_FOUND`, and an already quarantined role returns `QUARANTINED` without attempting recovery. The caller separately unregisters every discovery source, withdraws its observations, detaches its ScreenAttachments, removes its device bindings after dependent work drains, and releases its caller-owned role reference. `GpuRegistryTryQuiesceModuleRole` then establishes module-wide callback/worker quiescence. Only `GpuRegistryFinalizeModuleRoleShutdown` may call `release_module_role` and drop the role's lease reference, exactly once. Finalization returns PENDING while any binding, source, ScreenAttachment, logical Device, DDX-owned object, operation token, callback bridge, adapter role, or caller-owned role reference still depends on the generation; retry uses the same generation. There is no separate `GpuRegistryUnregisterModuleRole` operation. `GpuModuleRoleRetain` is accepted only while the role is active; a permanent role remains active until registry shutdown; after unloadable-role shutdown begins, no new callback/role references may be acquired, but existing references may be released. The caller's retained role handle keeps only the inert server-owned role record alive and does not keep module code pinned after successful finalization.
- Source registration assigns a fresh nonzero generation and copies the key. Duplicate active keys return `ALREADY_EXISTS`. An unloadable source MUST supply a live owner role of kind `GPU_MODULE_ROLE_DISCOVERY_SOURCE` and its exact generation; server-resident source code MAY pass NULL/zero. A wrong role kind or mismatched pointer/generation returns `INVALID_ARGUMENT` without installing a source. A non-NULL owner role is retained exactly once by the source registration. Unregister closes source admission and withdraws only its observations after callbacks drain; it returns `PENDING` while callbacks remain, and the caller retries with the same key/generation until terminal success. Source generations are never reused.
- Each source generation has its own monotonically increasing event sequence. `ObserveDevice` requires a nonzero source_event_sequence captured when the source event was observed, not when its callback is eventually dispatched. A lower sequence returns `STALE_EVENT`; replaying the same sequence with the same semantic payload is idempotent and returns the existing observation ID, while a different payload for the same sequence returns `IDENTITY_CONFLICT`. Sequences start at one and MUST NOT wrap or be reused within a source generation; on exhaustion, the source generation is retired and replaced. Removal evidence MUST carry the sequence of its exact observation; a delayed removal from an older source event is rejected even if its callback arrives after a newer add/update event.
- `ObserveDevice` assigns a unique nonzero observation ID per new observation. Repeating the same source/generation, source-event sequence, and same semantic payload returns the same observation ID and, when the result is SUCCESS, one additional caller-owned PhysicalDevice reference for that successful call; it does not create a duplicate source observation. Changed evidence is a new observation/replacement, never an in-place mutation of the prior observation. `PENDING`/`AMBIGUOUS` retain the observation, return no device reference, but DO return the nonzero observation ID so the source can later withdraw or reconcile it. Invalid source/generation creates no observation and leaves all outputs at their failure sentinels.
- `GpuRegistryRegisterModuleRole` installs the shared module-lifetime record once. `GpuRegistryRegisterDdxDevice` installs one per-device binding and validates its identity, native handle, context, and operation table atomically. Its owner role MUST be of kind `GPU_MODULE_ROLE_DDX_BACKEND`; a role of any other kind or a NULL role returns `INVALID_ARGUMENT`. The binding retains that module role exactly once; native handles and per-device context remain DDX-owned borrowed values. A NULL mandatory operation table/hook, missing hook for any advertised capability, missing completion sink/userdata required by the compute-baseline asynchronous operations, NULL native PhysicalDevice handle, or inconsistent descriptor pointer/generation pair returns `INVALID_ARGUMENT`; presentation-only hooks may be absent only when the binding does not advertise the presentation profile. Failure rolls back all registry-acquired references and publishes no XID. `device_context` MAY be NULL only when the DDX declares that all operations for this binding are context-independent.
- The DDX enumerates its own hardware and submits one complete registration per served PhysicalDevice. The registry copies identity evidence and stores the exact native handle and per-device context as borrowed opaque pointer values directly in the binding; the DDX remains their owner and MUST keep them valid and immutable until exact binding removal has completed and all in-flight calls, objects, tokens, and callbacks have retired. The registry MUST NOT free these DDX-owned values. No candidate list or DDX-local ID-to-handle map is exposed to the registry.
- `GpuRegistryRegisterDdxDevice` validates the DDX-supplied identity, native handle, device context, operation vectors, and owning `GPU_MODULE_ROLE_DDX_BACKEND` generation as one atomic registration. An unknown owner role returns `NOT_REGISTERED`, a stale role generation returns `STALE_GENERATION`, a role whose admission is closed returns `SHUTTING_DOWN`, and a quarantined role returns `QUARANTINED`; none installs a binding. It returns one caller-owned canonical PhysicalDevice reference and the binding generation only on `SUCCESS`. The first successful registration allocates a fresh binding generation; an identical replay from the same owner-role generation returns the same live binding generation and one additional caller-owned PhysicalDevice reference without creating another binding. At most one live binding may exist for a given canonical PhysicalDevice incarnation and owner-role generation; a second non-identical registration from that same role returns `ALREADY_EXISTS` or `IDENTITY_CONFLICT`. The DDX MUST release the returned PhysicalDevice reference before leaving the registration call path and MUST NOT retain or dereference that pointer afterward. The native handle and per-device context are stored directly as borrowed opaque values in the binding; the DDX owns them and MUST keep them valid until binding removal and all dependent references retire. No DDX-local numeric ID or candidate-list map is part of the registry API. The registry obtains the complete immutable snapshot by calling `query_physical_snapshot` through that exact binding. If the query returns backend `UNAVAILABLE`, registration returns `GPU_REGISTRY_UNAVAILABLE` and installs no binding; the DDX may retry with a new binding generation after recovery and MUST report any persistent module-role-wide failure through the separate module-role availability API. `OUT_OF_HOST_MEMORY`/`OUT_OF_DEVICE_MEMORY` maps to `GPU_REGISTRY_OUT_OF_MEMORY`. A structurally invalid snapshot, `GPU_BACKEND_UNSUPPORTED` from this mandatory query operation, `DEVICE_LOST` before any logical Device exists, an operation-inapplicable STATUS/CANCELLED/TRANSFER_FAILURE result, or a malformed result scope is a DDX contract violation: quarantine the module role and return `GPU_REGISTRY_QUARANTINED`. A classified `EXECUTION_FAILURE` or other non-contract internal query failure maps to `GPU_REGISTRY_INTERNAL_ERROR`. A complete snapshot that truthfully reports the device lacks a mandatory v0.1 baseline feature, or explicitly marks a mandatory baseline property/queue/memory/limit unavailable, is not malformed but makes that DDX binding ineligible; `GpuRegistryRegisterDdxDevice` returns `GPU_REGISTRY_UNSUPPORTED` and installs no binding, allowing a later eligible DDX preference to win. In every failed registration case, no binding or caller-owned PhysicalDevice reference is returned, no XID is published, and all registry-acquired references are rolled back. Conflicting registration data returns `ALREADY_EXISTS` or `IDENTITY_CONFLICT`. If identity evidence cannot be unambiguously canonicalized, registration returns `AMBIGUOUS` and installs no binding: all pointer/generation outputs remain at failure sentinels, no DDX-owned context/handle or module-role reference is retained, and no XID is allocated. The registration call itself retains no observation; the DDX may submit stronger identity evidence through `GpuRegistryObserveDevice` (which returns its own observation ID) and retry registration. `PENDING`/`AMBIGUOUS` retention semantics for `GpuRegistryObserveDevice` do not imply that an incomplete DDX binding was installed. A successful registration may remain unpublished while the startup publication barrier or deterministic complete-binding selection is unresolved; SUCCESS means the complete binding was atomically installed, not that an XID was necessarily published. Removal releases binding references only after in-flight calls through that binding drain.
- Removal of a binding, observation, or ScreenAttachment requires the exact generation. Removing a DDX binding first closes admission for that exact binding; if it is the selected binding, the PhysicalDevice transitions atomically to `UNAVAILABLE` and MUST NOT fail over to another registered binding. Removing a non-selected binding does not change PhysicalDevice status. The binding and its DDX-owned native handle/context remain retained until all in-flight calls, objects, tokens, and callbacks drain. A completed repeated removal returns `NOT_FOUND`; a concurrent removal still draining returns `PENDING`, and the caller retries the same exact operation until terminal success. Screen detach is addressed by attachment generation so the caller may release its attachment handle while callback retirement is pending. No removal broadens to another source, binding, Screen, or incarnation.
- Unavailable/recovered transitions are scoped and sequenced. Module-role availability/recovery calls MUST name a role of kind `GPU_MODULE_ROLE_DDX_BACKEND`; a different role kind or mismatched generation returns `INVALID_ARGUMENT` without changing availability. Module-role sequence numbers are strictly increasing per DDX backend role generation. Device-scoped sequence numbers are strictly increasing per exact (DDX backend role generation, binding generation). An unavailable/recovered transition for a non-selected binding changes only that binding's eligibility and MUST NOT change the published PhysicalDevice status or selected binding; only the selected binding's availability contributes to that PhysicalDevice's effective status. Sequences start at one and MUST NOT wrap or be reused; exhaustion requires retiring the affected DDX module-role generation or binding and allocating a new generation. A lower sequence returns `STALE_EVENT`; reusing the same sequence with the same state is idempotent `SUCCESS`, while reusing it with a different state is `IDENTITY_CONFLICT`. Device-scoped calls MUST include the exact registry binding generation. Effective availability is the conjunction of module-role availability, exact-binding availability, and non-REMOVED PhysicalDevice state: recovery at one scope MUST NOT clear unavailability at another scope. Recovery after binding removal, DDX backend shutdown, or physical `REMOVED` returns `STALE_GENERATION` or `SHUTTING_DOWN`; it never resurrects state.
- `AttachScreen` validates the live Screen only during the call, the exact PhysicalDevice generation, nonzero Screen generation, and known non-conflicting role bits. An unloadable DDX MUST pass a live owner role of kind `GPU_MODULE_ROLE_DDX_TOPOLOGY` and its exact generation; server-resident topology code MAY pass NULL/zero. A wrong role kind or mismatched pointer/generation returns `INVALID_ARGUMENT` without attaching the Screen. The attachment retains a non-NULL owner role once. `GpuScreenAttachmentRetain` is accepted only before detach begins; after detach, existing holders may release but no new attachment references are admitted. If the DDX callback code is unloadable, the attachment MUST retain the supplied live owner role and generation; the role remains pinned until detach and all attachment callbacks have retired. At least one role MUST be set; DISCOVERY_ONLY is mutually exclusive with RENDER_ACCESS, SCANOUT, and DISPLAY_CONTROL, while RENDER_ACCESS and SCANOUT MAY coexist. It returns a retained attachment plus a registry-assigned attachment generation. An exact duplicate returns the existing attachment with one caller reference; conflicting roles return `ALREADY_EXISTS`. The registry stores no Xserver Screen pointer. Detach closes the exact attachment immediately to new work; storage remains until references/callbacks retire.
- `XaPhysicalDevicePublish` requires resolved identity, one selected eligible DDX binding, a complete immutable snapshot, and an open publication gate. It returns `PENDING` while the startup barrier is open, `AMBIGUOUS` when multiple eligible bindings remain without a matching configured preference, `UNSUPPORTED` when no complete binding meets mandatory baseline requirements, and `UNAVAILABLE` when the selected binding is temporarily unavailable. XID allocation and DIX resource insertion are one transaction. On insertion failure the provisional XID is freed and no published state is visible. Repeated publication returns the same XID. Stale or removed incarnations cannot be newly published. `GetXid` returns `NOT_FOUND` before publication and `STALE_GENERATION` for an old incarnation.
- `GpuPhysicalDeviceAcquireBackendBinding` returns a retained reference only while the PhysicalDevice is `AVAILABLE` and its selected binding is active. It returns `NOT_FOUND` if no registration exists, `PENDING` while initial selection is unresolved, `AMBIGUOUS` if multiple eligible bindings remain without a matching configured preference, `UNSUPPORTED` if no registered binding meets mandatory baseline requirements, `UNAVAILABLE` if the selected binding/PhysicalDevice is unavailable, and `SHUTTING_DOWN` if the binding or owning module role has closed admission. `BUSY` is reserved for an active teardown/dependency transition that has not yet reached a terminal state. The returned binding generation MUST equal the pinned selection and is released exactly once.
- Registry shutdown is idempotent and does not silently destroy live objects. `BUSY` reports outstanding ownership; callers retry after teardown. A failed `Destroy` does not invalidate existing references.
- `TryQuiesceModuleRole` initializes `out_quiescence` to PENDING. A successful hook returns registry SUCCESS/quiescence SUCCESS; an unmet precondition or hook PENDING returns registry PENDING/quiescence PENDING; hook FAILURE returns `GPU_REGISTRY_QUARANTINED`/quiescence FAILURE and permanently forbids finalization unless a separate server-controlled recovery proves safety. Stale/unknown DDX module-role generations return STALE_GENERATION without calling the hook.
- `GpuRegistryFinalizeModuleRoleShutdown` returns PENDING while any caller reference, device binding, discovery source, ScreenAttachment, logical Device, DDX-owned object, operation token, callback bridge, or adapter role still depends on the DDX module-role generation. The registration caller MUST release its caller-owned ModuleRole reference before expecting finalization to succeed; the finalization API uses only the server-assigned generation and the registry-owned record. It calls the `release_module_role` hook exactly once while the module lease is held, then drops exactly that generation's lease reference. Repeated finalization after success returns NOT_FOUND and MUST NOT release either reference again. `TryQuiesceModuleRole` repeated after recorded quiescence SUCCESS returns SUCCESS/ SUCCESS without re-entering the hook; after finalization it returns NOT_FOUND.

DDX backend operation-table functions have a common rule: each synchronous function returns a classified `GpuBackendResult` and either commits its output object completely or leaves outputs NULL/zero with no externally visible partial object. The four typed operation-table structures are defined normatively in [the DDX backend operation matrix](provider-operation-matrix.md). Every fallible operation uses `GpuBackendResult`, initializes every output before validation, and uses `GpuBackendOperationToken` for each of the six asynchronous operations listed below. No operation may use an undocumented `void` return to hide failure; only infallible reference hooks are void. The server MUST validate that result code and unavailable-scope fields form one of the documented combinations; `UNAVAILABLE` with `NONE`, or any non-UNAVAILABLE code with a non-NONE scope, is a DDX backend-contract violation. For `PHYSICAL_DEVICE` scope, the binding generation and PhysicalDevice generation MUST identify one active binding of that DDX module-role generation, and availability_sequence MUST be monotonic within that exact binding generation. For `MODULE_ROLE` scope, both binding/device fields MUST be zero, and availability_sequence MUST be monotonic within that DDX module-role generation. DDX backend result validation requires `status_code == 0` unless code is STATUS, and `status_code` MUST be a value defined for that exact operation when STATUS is returned. `availability_sequence` MUST be nonzero exactly when code is UNAVAILABLE and zero for all other codes. `GPU_BACKEND_STATUS_NOT_READY` is valid only for `acquire_next_image`; `GPU_BACKEND_STATUS_OUT_OF_DATE` and `GPU_BACKEND_STATUS_SURFACE_LOST` are valid only for presentation operations that define those outcomes; `GPU_BACKEND_STATUS_ALREADY_COMPLETED` is valid only as the result of `cancel_acquire`. Unknown or operation-inapplicable status values are FATAL DDX backend-contract violations. `native_result` is diagnostic only. `unavailable_scope == NONE` and zero binding/device fields are required unless code is UNAVAILABLE; MODULE_ROLE scope requires zero binding/device fields; PHYSICAL_DEVICE scope requires a nonzero binding generation and exact nonzero PhysicalDevice generation. Unknown enum values or inconsistent combinations are FATAL DDX backend-contract violations. A `GPU_BACKEND_FATAL` result, whether returned directly or detected by server validation, immediately quarantines that DDX module-role generation: close its operation/binding admission, mark selected PhysicalDevices UNAVAILABLE without declaring physical removal, retain DDX module-role record/module leases and dependent objects, and forbid normal finalization. Recovery requires a separate server-controlled proof-of-safety path; absent such a path, quarantine lasts until process exit. Once quarantined, `GpuRegistryTryQuiesceModuleRole` returns `GPU_REGISTRY_QUARANTINED` with FAILURE output without invoking `quiesce_module_role`; `GpuRegistryFinalizeModuleRoleShutdown` likewise returns QUARANTINED without calling `release_module_role`. Only an explicitly specified server-controlled recovery path may make either hook callable again. `GPU_BACKEND_CANCELLED` is valid only as the terminal completion of an already accepted cancellable operation; it is not a synchronous submission-acceptance result. `GPU_BACKEND_DEVICE_LOST` is scoped to the exact logical Device/operation and MUST NOT by itself mark the PhysicalDevice, binding, or module role unavailable. Plain query outputs (snapshot/support structures) contain no DDX-owned pointers; the DDX owns its enumeration storage and releases it independently of the registry. Successful create operations transfer one DDX-owned object handle to the server, which MUST destroy it exactly once through the matching operation before DDX backend quiescence. A successful `create_logical_device` transfers one owned DDX backend-device reference to the server. `retain_device` and `release_device` manage additional DDX backend-device wrapper references held by asynchronous operations or deferred cleanup; every retain is paired exactly once. `destroy_logical_device` destroys the native logical device exactly once after backend dependencies drain, but wrapper storage remains until all DDX backend-device references have been released. The server calls the final `release_device` only after destroy completion or safe quarantine. These hooks are infallible and MUST NOT be called under the registry lock. Queue handles returned by `get_queue` are borrowed from and bounded by their logical Device lifetime. For asynchronous functions, the server calls `GpuRegistryPrepareOperation` and registers the token before entering DDX backend code. The token pointer is call-scoped and MUST NOT be retained, dereferenced after return, assigned, altered, or recycled. The DDX backend copies its ID and generation through the two token accessors for later callback userdata. The asynchronous backend operations are exactly `write_buffer`, `read_buffer`, host `signal_semaphore`, `queue_submit`, `acquire_next_image`, and `queue_present`; each receives one prepared token and uses the matching `GpuBackendOperationKind`. The typed operation-table declarations MUST expose that token parameter for every listed operation. All other backend operations are synchronous unless a later version explicitly adds an operation kind and conformance coverage. If the DDX backend entry point returns `GPU_BACKEND_SUCCESS`, the server MUST call `CommitOperationSubmission`; callbacks arriving before commit are buffered until acceptance commits. If the DDX backend returns non-success, the server MUST call `RejectOperationSubmission`; the DDX backend contract guarantees no callback or backend access can follow. If a callback was already observed or backend access cannot be excluded, rejection returns QUARANTINED. Exactly one terminal completion is permitted for each accepted token. Token IDs and operation generations are server-assigned, non-reusable, and scoped to the DDX module-role generation. The registry calls `retire_operation` through `GpuRegistryRetireOperationToken` after terminalization and after the server completion sink has returned from the DDX backend callback. The hook MUST be idempotent: PENDING may be retried, SUCCESS remains successful, and FAILURE is terminal quarantine. Registry results map one-to-one to `GPU_REGISTRY_PENDING`, `GPU_REGISTRY_SUCCESS`, and `GPU_REGISTRY_QUARANTINED`. PENDING keeps token, resource, logical-Device, binding, DDX backend, and module references; FAILURE quarantines them and blocks DDX backend quiescence; SUCCESS is permitted only after backend access is impossible and all callback frames for that token have returned, then releases the token's retained references exactly once. If DDX backend code cannot guarantee the no-callback-after-failure rule, the attempted token is quarantined and the DDX module-role generation cannot be quiesced. Repeated Commit of an already accepted exact token returns SUCCESS; Commit after REJECTED and Reject after ACCEPTED return IDENTITY_CONFLICT. Repeated Reject of the exact already rejected token returns SUCCESS without releasing references twice. Retire before a terminal outcome returns BUSY; PENDING is retried through the DDX backend hook; after successful retirement, a repeated Retire for the same exact token ID/generation returns SUCCESS as an idempotent no-op and never calls the hook or releases references again.

The completion sink copies and validates each completion and its bounded payload into server-owned storage and enqueues it; payload MUST be NULL iff payload_size is zero, and payload_size MUST NOT exceed a server-defined hard maximum checked before allocation; it MUST NOT process protocol requests or invoke DDX backend code inline. Completion identity includes exact module-role generation, operation kind, token, binding generation, and PhysicalDevice generation, logical-Device ID/generation, and any operation-specific primary resource ID/generation. The complete resource-generation set is retained by the server-side token record; it is not reconstructed from the completion payload. For device-scoped results, the completion binding/device generations MUST exactly equal the embedded `GpuBackendResult` binding/device generations. Logical-Device and resource IDs/generations MUST each be zero-paired or nonzero-paired according to the operation kind. The completion record carries no raw registry, Xserver, or Vulkan object pointer; the server resolves the IDs through the retained operation token. For a PHYSICAL_DEVICE-scoped unavailable result, binding generation and PhysicalDevice generation MUST match the registered binding; for other scopes, unavailable-scope-specific fields MUST be zero. The serialized server domain MUST translate an UNAVAILABLE result into the matching module-role-wide or exact-binding registry transition using the same availability_sequence and exact binding generation from the call/token record; DDX backend callbacks MUST NOT mutate availability state directly. A completion's operation kind, DDX backend/token generations, native handle stored directly in the binding, registry binding generation, and PhysicalDevice generation MUST exactly match the prepared token; primary resource fields MUST match the operation's declared primary resource, or be zero when the operation has no single primary resource. Stale/duplicate completions are discarded and diagnosed. DDX backend-owned completion payload is copied before callback return or held by a separately retained object whose release callback executes while the module lease remains pinned.

Module-role lifecycle APIs identify module-role records by the registry-assigned module-role generation, not by a caller-held module-role pointer. This allows the registration caller to release its own module-role reference before final quiescence/finalization; the registry-owned module-role record remains addressable by generation until finalization completes.

The API MUST NOT expose a public function such as `RegisterPhysicalDeviceWithXid()` to DDX drivers. XID allocation and protocol resource publication belong exclusively to the XAverius/server resource layer. A DDX device registration may return an existing canonical PhysicalDevice record or create an unpublished record; it MUST NOT publish a duplicate identity.

The registry MUST stage DDX registrations and identity observations as needed until the startup publication barrier has completed deterministic binding selection and snapshot validation. This staging is an internal publication-order mechanism only: it MUST NOT introduce a separate Vulkan-ICD candidate inventory, candidate-list callback API, or a second DDX-backend attachment/dispatch lookup. Each DDX registration remains a complete per-device binding containing its identity evidence, native handle, per-device context, and typed operation vectors. The registry MUST NOT publish a PhysicalDevice merely because an individual DDX probe completed; publication occurs only after the selected complete binding has produced the immutable snapshot.

## 8. Xlibre/Xorg integration guidance

For the current XAverius scope, the recommended ownership location is the XAverius server subsystem itself (for example, `Xext/xaverius/registry.c`), with a private server-internal interface declared in an exported header such as `include/xaverius_registry.h`. This keeps Vulkan-specific identity, DDX-binding selection, metadata snapshots, and XAverius XID publication together without making generic DIX depend on Vulkan or DRM. The interface is an internal server/module interface, not a stable client ABI or a promise of compatibility for independently built third-party modules.


The existing Xorg platform-device list (`xf86_platform_devices` in `hw/xfree86/common/xf86platformBus.c`) and udev DRM discovery (`config/udev.c`) are useful discovery inputs, not the canonical XAverius registry. The platform list is organized around device-node attributes and Xorg ownership/claiming; the current DRM udev path filters `card*` nodes and deduplicates those observations by major/minor. These are appropriate for Xorg device management but do not represent identity across DRM primary/render nodes, multiple Vulkan instances/ICDs, or hotplug generations.

Recommended layering:

- Xorg platform/udev code reports identity and authoritative hotplug observations to the registry.
- DDX drivers report Screen-to-device relationships as ScreenAttachments; they register a GpuModuleRole only if they implement its complete Vulkan/backend operation contract.
- The DDX registers each executable device binding directly; platform/udev sources contribute identity and hotplug observations only.
- The server-wide registry canonicalizes identity, validates the DDX binding, obtains its snapshot, and owns PhysicalDevice records.
- XAverius enumerates only published registry records and owns their protocol XID resources.
- Screen initialization creates/destroys ScreenAttachments only; detaching a Screen does not remove a still-discovered device.
- Surface/WSI code performs the actual Device/Surface presentation-support query; it must not infer support from a ScreenAttachment.

### 8.1 Practical mapping to the current XLibre Xserver tree (non-normative)

The following mapping was checked against X11Libre/xserver commit `ee4bb3f96eec3b21c1961d54fe45cb33dc402d00`. It is an integration guide, not a promise that these private interfaces remain stable across XLibre revisions.

- `InitOutput()` in `hw/xfree86/common/xf86Init.c` calls `xf86BusProbe()` before `xf86ExtensionInit()`, driver-module loading, `xf86BusConfig()`, and DDX `PreInit()`. This means a registry/hotplug bootstrap that must observe the initial platform scan cannot be deferred solely to the normal XAverius extension setup. The integration SHOULD split early registry/event-source bootstrap from later protocol-extension registration.
- `xf86BusProbe()` in `hw/xfree86/common/xf86Bus.c` calls `xf86platformProbe()`. The latter calls `config_odev_probe(xf86PlatformDeviceProbe)` and populates `xf86_platform_devices`. This is a useful place to feed platform observations into the registry, or to snapshot the completed platform list immediately after the probe. The platform list remains an Xorg discovery/ownership structure, not the canonical XAverius inventory.
- `config_udev_odev_probe()` in `config/udev.c` enumerates DRM subsystem nodes matching `card[0-9]*`; the event path similarly filters for `card*` and checks existing entries by major/minor. Therefore this path MUST NOT be treated as a complete primary-plus-render-node identity source. XAverius discovery must independently obtain or correlate render-node evidence (for example through libdrm/sysfs) and must use the underlying DRM device relationship rather than major/minor as identity.
- A DDX registers every PhysicalDevice it serves during its device-enumeration/probe phase, before the corresponding X11 Screen object needs to exist. Registration requires the complete `GpuDeviceBackendOps` contract for the capabilities advertised by that device. ScreenAttachments are created separately, only after the corresponding Screen generation exists. A DDX that does not provide executable XAverius operations may report Screen topology against an already canonicalized device, but it cannot create an executable PhysicalDevice registration.
- `xf86platformAddDevice()` performs a GPU-screen probe/PreInit, creates a GPU Screen, attaches it to a configured protocol Screen, and updates RandR. `xf86platformRemoveDevice()` closes/removes that GPU Screen and removes the Xorg platform-device entry. XAverius MUST map these operations to ScreenAttachment attach/detach and source-observation withdrawal as appropriate; the screen-removal path alone is not proof of physical removal.
- `xf86platformPrimary()` may fall back to the first platform device when no primary bus is configured. That fallback is an Xorg primary-device convention and MUST NOT feed XAverius PhysicalDevice ordering, DDX-binding selection, or `CreateDefaultDevice`.

A practical initial sequence is therefore: bootstrap the XAverius registry and hotplug observation before `xf86BusProbe()`; ingest platform observations during/after `xf86platformProbe()`; accept DDX device bindings during DDX device registration and DDX probe/PreInit; close the initial discovery barrier and publish complete records before client requests are dispatched; then attach Screen generations as Xorg creates them. The exact hook placement is an XLibre integration decision, but the ordering and separation are mandatory.


The registry implementation SHOULD remain in the XAverius subsystem even when the first deployment is Xorg-only; Xorg-specific discovery adapters belong beside the platform bus code. This avoids coupling the registry to Xorg-only data structures and permits the same XAverius registry to serve Xvfb or another DDX. Moving the registry into generic DIX is not required unless a separate non-XAverius server service later needs the same device inventory.


### 8.2 Suggested implementation decomposition (non-normative)

The following decomposition is intended to make the ownership rules practical in an Xlibre server. It is guidance, not a requirement to use these exact files or data structures.

**Keep the registry as the authority, not as a hardware driver.** A reasonable initial split is:

- `registry.c`: canonical PhysicalDevice records, identity-key construction, publication state, and generation allocation.
- `discovery.c`: source registration, observation storage, scan/event reconciliation, and startup barrier.
- `DDX backend.c`: DDX binding descriptors, DDX-local bindings, deterministic DDX-binding selection, and backend operation admission.
- `DDX backend-lifetime.c`: operation-token accounting, DDX backend references, quiescence, quarantine, and module leases.
- `screen-attachments.c`: Screen-generation attachment records and topology-only notifications.
- `presentation-route.c`: exact Device/Surface route generations and bridge lifetime.
- `xorg-adapter.c`: translation from Xorg platform/udev/DDX lifecycle into registry observations. This adapter should be replaceable without changing the canonical registry model.

These may initially live in fewer source files. The important boundary is ownership: Xorg discovery structures and DDX private objects are inputs, never the registry's canonical storage.

**Use server-owned IDs for retained relationships.** Internally, keep explicit records for discovery sources, observations, DDX module-role generations, DDX device bindings, PhysicalDevice incarnations, ScreenAttachments, operation tokens, and module leases. Index them by typed canonical keys and non-reusable generations. A PhysicalDevice binding stores its direct operations, device context, native handle, and a retained module-role reference; it does not resolve a separate backend object for dispatch. A ScreenAttachment should refer to a PhysicalDevice generation and a Screen generation, not own either object. Avoid using raw pointers as map keys or as asynchronous identity.

**Separate lookup from mutation.** Registry APIs called from DDX probe, hotplug, or worker contexts should validate/copy their input and enqueue an immutable command. One server serialization domain should commit identity joins, status transitions, DDX-binding selection, publication, and teardown. A worker callback must not directly mutate registry lists, X resources, RandR state, or client-visible status. Do not call DDX backend code, Xorg callbacks, or module-loader operations while holding the registry's structural lock; take a retained reference, drop the lock, call out, then revalidate the exact generation before committing the result.

**Make initial discovery race-free.** Subscribe to hotplug notifications before starting the initial enumeration. Record a source generation and monotonically ordered observation/event sequence for each source. Reconcile events received during the scan against the scan result before closing the startup barrier. The barrier waits for configured DDX device-registration passes and platform identity/hotplug sources, not for Screen creation, RandR initialization, or a particular DDX's PreInit order. A failed adapter completes as unavailable/failed; it must not fabricate physical removal. After the barrier closes, late discovery uses the per-device publication path and cannot reopen or reorder the initial inventory.

**Treat DDX binding publication as one atomic commit.** Each DDX enumerates its own served devices and submits a complete `GpuRegistryRegisterDdxDevice` registration for each one. The registry canonicalizes the supplied identity evidence, validates that exact binding's operation vectors/context/native handle, obtains its complete snapshot through that binding, and only then publishes the PhysicalDevice/XID. If multiple DDX registrations claim one canonical incarnation, the registry applies the configured preference over stable DDX device-registration module-role owner keys. The preference is an ordered server configuration list; the first eligible registered binding whose owner key appears in that list is selected. If no configured key matches, a sole eligible binding is selected; multiple eligible unlisted bindings leave the PhysicalDevice unpublished as ambiguous. A binding with incomplete operation vectors, invalid native handle/context, failed mandatory snapshot query, or unsupported baseline requirements is ineligible and MUST NOT block selection of a later eligible preference. The registry MUST NOT rank a separate candidate inventory, merge operation vectors/contexts/snapshots, or use registration, Screen, pointer, DRM-node, or module-load order as a tie-breaker. An ambiguous or incomplete claim remains unpublished. A later DDX registration MUST NOT silently replace the published binding or snapshot.

**Keep OS discovery handles separate from DDX device handles.** A DRM node path, `dev_t`, or file descriptor is an access locator, not a PhysicalDevice identity. Resolve primary/render nodes through the underlying DRM device relationship and canonical platform identity. Define who opens, duplicates, and closes every DRM file descriptor; do not let the registry close a descriptor still owned by Xorg or a DDX. Native Vulkan handles remain private to the DDX and are supplied directly in each device registration. If one DDX sees aliases for the same device through multiple ICD instances, it deduplicates them internally before registering one binding.

**Do not make Screen lifetime a shortcut for device lifetime.** Attach a Screen only after its generation exists and the DDX can provide a resolved canonical PhysicalDevice reference. If identity is not yet resolvable, retain a pending topology observation and retry when stronger evidence arrives; do not guess from Screen number, Entity index, or the first GPU. On close, invalidate the attachment generation before freeing Screen-private storage. Any asynchronous work must use a detached copied context and must not call back into Screen or RandR after close.

**Make module-role teardown observable and retryable.** Track separate references for device bindings, logical Devices, DDX-owned objects, accepted operations, callback bridges, adapter roles, and module leases. A single generic refcount is insufficient for diagnosing why unload is blocked. Expose diagnostic state (module-role owner key/generation, affected binding generations, shutdown phase, outstanding token/object/bridge counts, quiescence result, and quarantine reason) through server logging or a debug dump; do not expose private pointers or mutable internals to clients. PENDING must identify what remains outstanding. FAILURE must preserve the module and context in quarantine. Do not wait synchronously for GPU progress in Screen close or hotplug handlers.

**Verify the loader pin independently of Screen references.** Before relying on unloadable DDX DDX backends, prototype the loader-owner abstraction against the actual Xlibre loader. Demonstrate that it prevents the final `dlclose()` after the last Screen's `FreeScreen()`, including duplicated `ModuleDesc` cases. If no supported independent pin exists, make the DDX module permanently resident for that server lifetime rather than pretending a Screen or `DriverPtr` reference is sufficient. The lease object itself must be server-owned and shared by every DDX module-role generation and callback role from that loaded module instance.

**Integrate in small, testable stages.** First land the registry and identity tests without Vulkan execution; then connect platform/udev observations; then DDX per-device registration and immutable snapshots; then ScreenAttachments; then backend operation tokens and module-role quiescence; finally presentation routes and cross-GPU bridges. At each stage, test reordered initialization, hotplug during scan, duplicate primary/render observations, two Screens on one GPU, one Screen on multiple GPUs, binding- and module-role-scoped failure, and teardown with delayed callbacks. Keep Xorg-specific adapter tests separate from registry model tests so the latter can run under a headless test harness.



### 8.3 Registry API implementation notes (non-normative)

**DDX owns enumeration.** Each DDX enumerates every PhysicalDevice it serves through its own native backend. For each device it calls `GpuRegistryRegisterDdxDevice` with structured identity evidence, the exact native physical-device handle, per-device context, immutable operation vectors, and its owning module-role generation. The registry does not enumerate Vulkan ICDs, consume candidate lists, or translate DDX-local numeric IDs into native handles.

**Binding is the dispatch record.** The registry's DeviceBackendBinding stores/references the operation vectors, device context, native handle, binding generation, availability state, and retained module-role reference. Request handlers dispatch through that exact binding. The DDX module-role record is shared lifetime state only; it is not a device selector or an intermediate call target.

**Module role is optional lifetime bookkeeping.** Every device binding references a generation-checked module role. Unloadable code uses a leased role; permanently resident code uses a server-owned permanent role with no loader lease. A role can own many device bindings. Its module lease pins code and shared callback resources; each binding separately retains its device context and native handle.

**Snapshot and publication.** The registry validates the complete operation table for the advertised capabilities, calls `query_physical_snapshot` through the exact binding, and publishes the canonical PhysicalDevice/XID only after the complete snapshot succeeds. The DDX performs identity-alias deduplication within its own enumeration before registration. Duplicate claims from different DDX instances are canonicalized by the registry but never have their operation tables, contexts, or snapshots merged.

**Operation tokens.** Each asynchronous token records the exact PhysicalDevice incarnation, binding generation, module-role generation, operation kind, logical-Device generation, and complete retained resource set. The callback receives only copied token identity, not a raw registry pointer or public XID. Token terminalization and backend quiescence are separate milestones.

**Teardown.** Screen close detaches only the exact ScreenAttachment. Device-binding removal drains operations and backend objects using that native handle. Module-role shutdown closes admission across its bindings, drains callback frames and workers, quiesces the role, releases its shared module lease, and only then permits module unload. If quiescence is uncertain, retain or quarantine the affected binding and module.

## 9. Required architecture tests

The implementation test suite SHOULD include at least:

1. Two Screens and two DDX discovery paths report the same GPU: one PhysicalDevice record and one XAverius XID.
2. DRM primary and render nodes report the same GPU: one record; removing one access node does not mark the hardware REMOVED while the physical device remains.
3. Two ICDs report the same GPU with different DDX backend handles: one record, deterministic selected DDX binding, one coherent metadata snapshot.
4. Reordering Screen, DDX, DDX backend, and ICD initialization does not change canonical identity, selected DDX binding, or CreateDefaultDevice result under a fixed configuration.
5. The selected DDX binding becomes unavailable while hardware remains: status becomes UNAVAILABLE, not REMOVED; a different DDX backend is not silently substituted.
6. A shared DDX module-role generation serving two selected PhysicalDevices becomes unavailable: both affected PhysicalDevices become UNAVAILABLE; a third PhysicalDevice merely discovered by that DDX backend but selected through another DDX backend remains AVAILABLE. Recover the same DDX module-role generation and verify only its selected bindings recover, with unchanged XIDs and snapshots.
7. A single DDX PhysicalDevice binding becomes unavailable while the shared module-role generation remains usable: only that PhysicalDevice becomes UNAVAILABLE; another PhysicalDevice selected through the same DDX backend remains AVAILABLE. Recover the exact binding and verify only it recovers. A stale DDX backend/device generation MUST NOT change either status.
8. The selected DDX binding recovers for the same incarnation: the same XID and metadata snapshot become AVAILABLE again.
9. A physical remove followed by re-add at the same BDF/path/node number creates a new PhysicalDevice and XID; the old record remains REMOVED.
10. A Screen is destroyed and recreated while the same GPU remains: the attachment generation changes; the PhysicalDevice and XID do not.
11. A Screen is attached to more than one GPU, and one GPU is attached to more than one Screen: no identities are created, merged, or destroyed by attachment changes.
12. A late callback from an old DDX backend, PhysicalDevice, or Screen generation cannot mutate a replacement object.
13. CreateDefaultDevice selection does not depend on the first Screen with XAverius support and never combines GPUs.
14. DDX backend module/context teardown is delayed until every logical Device, submission, callback, and backend operation referencing it has quiesced.

15. While `create_logical_device` is running, a DDX backend that can no longer serve the selected device returns `UNAVAILABLE` with exact `PHYSICAL_DEVICE` scope (or `MODULE_ROLE` scope for a role-wide failure): the PhysicalDevice becomes UNAVAILABLE, no logical Device/XID is published, and the request returns DEVICE_UNAVAILABLE. If the DDX instead returns `DEVICE_LOST` before a logical Device exists, treat it as a FATAL contract violation and quarantine the owning module role; do not synthesize a Device-Loss event or misclassify it as ordinary unavailability.
16. A DDX backend returns host/device allocation failure during logical-device creation: all partial objects are rolled back or quarantined, the target XID remains free, and ALLOCATION_FAILED is returned.
17. A DDX module-role generation becomes UNAVAILABLE while a logical Device exists: the PhysicalDevice status changes, but the logical Device is not declared DEVICE_LOST without a positive loss result for that exact VkDevice.
18. A backend operation on an existing logical Device reports DEVICE_LOST concurrently with submission completion, wait satisfaction, timeout, or DestroyDevice: the first serialized terminal outcome wins exactly once.
19. A DDX backend reports UNSUPPORTED for a capability already included in the published snapshot: the request fails as a DDX backend contract violation, the capability snapshot is not mutated, and no client BadMatch is fabricated.
20. An asynchronous backend operation reports completion and then attempts a duplicate/late callback: only one terminal transition is committed and all retained references are released at most once.
21. DestroyDevice or disconnect races with an in-flight DDX backend call or accepted asynchronous operation: public invalidation occurs at its defined linearization point, but DDX backend code/context and backend objects remain pinned until the DDX backend proves no further access.
22. A DDX backend callback arrives after DDX module-role generation replacement or module-unload request: it is ignored for public state, cannot resolve a reused XID, and cannot execute unloaded DDX backend code.
23. A DDX backend reports TRANSFER_FAILURE or EXECUTION_FAILURE after asynchronous acceptance: the operation uses its defined terminal status/event and never generates a delayed X11 request error.
24. A surface-support or presentation operation is attempted for a Device/Surface pair not supported by a ScreenAttachment: the DDX binding's exact Device/Surface result controls the outcome; attachment membership does not imply support.

25. The same XAverius Surface is queried with logical Devices from two different DDX backends: each DDX backend creates/owns its own DDX backend-scoped WSI surface object, and no VkSurfaceKHR or WSI handle crosses DDX backend instances.
26. WaitSemaphores/WaitForFence completion races with the server timeout while the selected DDX binding becomes UNAVAILABLE: DDX backend unavailability alone MUST NOT terminalize either server-owned wait or produce DEVICE_UNAVAILABLE. The wait remains governed by its server-visible predicate, timeout, exact logical-Device Loss, DestroyDevice, and disconnect. If an underlying backend operation subsequently fails, only the synchronization state transition actually published by that operation may affect the wait; no DDX backend wait blocks the X11 dispatcher.
27. An accepted DDX backend-operation token cannot establish successful completion or backend quiescence: require exactly one terminal outcome callback with a classified failure, but no quiescence/retirement confirmation. The server MUST preserve the terminal protocol outcome while quarantining the token, affected resources, exact binding, and owning module-role record; duplicate callbacks are ignored, and no DDX module/context is unloaded while backend access remains possible.

28. Race positive logical-Device `DEVICE_LOST`, DDX backend-scoped `UNAVAILABLE`, ordinary resource destroy, `DestroyDevice`, and client disconnect in every relevant pairwise serialization order. Require one public invalidation owner, first-terminal-outcome preservation, request-specific result mapping, event/reply suppression at the correct connection/Device boundary, and exactly-once reference retirement. Ordinary resource destroy is not rejected solely by DDX backend unavailability or Device Loss; its own pending/recording blockers remain normative.

29. Withhold DDX backend quiescence after a classified terminal failure and verify that the failure is not reclassified as `DEVICE_LOST` solely because quiescence is unknown. Quarantine every potentially accessed backend object and DDX backend reference. Separately inject a positive `DEVICE_LOST` for one exact logical Device and verify only operations still open at that serialized point are terminalized as Device Loss.

30. A DDX reports a Screen-to-device observation without implementing Vulkan backend operations: it creates only a ScreenAttachment, not a GpuModuleRole or PhysicalDevice XID. A Vulkan DDX backend reports the same GPU independently: both observations converge on one canonical PhysicalDevice.
31. A single DDX Screen maps to two GPUs and two Screens map to one GPU: all attachments are represented independently; neither attachment order nor the first Screen changes DDX-binding selection, inventory order, or PhysicalDevice identity.
32. A discovery source withdraws one observation or one DRM access node while another authoritative source still reports the same incarnation: the PhysicalDevice remains present and is not marked REMOVED. Detaching the final Screen also does not remove a still-discovered headless/render-only device.
33. Two candidates cannot be unambiguously correlated: neither is silently merged nor published as a duplicate; both remain pending until stronger identity evidence resolves the match.
34. A selected DDX binding binding is deregistered while the physical device remains: the PhysicalDevice becomes UNAVAILABLE, no new DDX module-role generation takes over, and outstanding logical-device/operation references keep the old DDX backend code/context pinned until safe retirement.
35. A stale source removal, DDX backend deregistration, or Screen detach from an earlier generation arrives after replacement: it cannot mutate the new observation, DDX device binding, attachment, or PhysicalDevice incarnation.
36. The DRM primary and render nodes are observed in either order and through different discovery sources: both resolve to one canonical identity using the underlying DRM device relationship; withdrawing either node alone does not remove the identity.
37. Two Vulkan instances/ICDs report different handles for the same platform device and compatible valid `deviceUUID`: the observations join one PhysicalDevice, while DDX device bindings remain distinct and DDX-binding selection follows the configured stable policy.
38. Two simultaneously present devices report the same `deviceUUID` but have incompatible authoritative platform identities: they are not merged; the conflict is surfaced and each candidate remains independently represented only when its platform identity is unambiguous.
39. Two observations have the same BDF but belong to different confirmed hotplug incarnations: the later incarnation receives a new PhysicalDevice/XID and a delayed removal from the earlier source generation cannot remove it.
40. A mediated, SR-IOV, partitioned, or MIG-like child reports its parent identity but lacks a unique instance discriminator: it is not merged with the parent or a sibling and remains unpublished until its instance identity is resolved.
41. A software/virtual DDX backend supplies a stable DDX backend-scoped instance key: it may publish as a distinct device, but a second DDX binding's matching display name or vendor/device IDs do not merge with it.
42. Two DDX modules attempt to register the same active module-role owner key: the duplicate role registration is rejected. If independent DDX registrations claim the same canonical PhysicalDevice, selection is resolved only by the deterministic pre-publication policy; ambiguous claims remain unpublished, and registration/enumeration order cannot break the tie.
43. A DDX device registration has conflicting UUID/platform evidence or cannot produce a complete snapshot: that binding is ineligible for publication; the registry does not publish a partial snapshot or silently substitute another binding after publication.
44. Reordering DDX enumeration, module-role registration, DRM-node discovery, and Screen creation while holding source evidence and server policy constant produces the same canonical identities and selected bindings.
45. With no explicit default-device preference, permuting discovery/DDX backend/Screen order while keeping the same set of canonical identities and queue capabilities yields the same `CreateDefaultDevice` target according to the canonical ordering key.
46. An explicit default-device selector resolves to exactly one canonical PhysicalDevice; a selector matching zero or multiple identities is handled as a configuration error and never falls back based on XID, Screen, or enumeration order.
47. A preferred PhysicalDevice that is UNAVAILABLE, lacks timelineSemaphore support, or cannot supply the requested compute queue count is filtered before ranking; the next suitable preference is selected, or DEVICE_UNAVAILABLE is returned if none remains.
48. A logical Device created from render GPU A is queried against a Surface whose Screen has scanout GPU B: support is true only if A's selected DDX binding establishes a complete direct or explicit bridge route; B's ScreenAttachment alone does not imply support.
49. A PRIME/DRI3-capable topology exists but the selected DDX binding cannot import/export the required format or synchronize the transfer: the exact Device/Surface query reports no present-capable queue and CreateSwapchain returns UNSUPPORTED_CONFIGURATION.
50. The selected DDX binding establishes a cross-GPU bridge route and reports supported queue families/formats/usages: QueuePresent uses that route, preserves the required source/destination synchronization, and never passes DDX-local Vulkan handles across DDX backend boundaries.
51. A Surface belongs to Screen S1 while a different Screen S2 has an available scanout GPU: capability queries and presentation remain bound to S1; the server never redirects to S2 based on enumeration or attachment order.
52. A route generation changes after Swapchain creation: the old Swapchain becomes OUT_OF_DATE, no new operation is accepted on it, and a replacement query/create may select the new route; old callbacks cannot mutate the new route or Swapchain generation.
53. A scanout/bridge route fails while the render PhysicalDevice and logical Device remain healthy: presentation is failed/invalidated under its own status contract, but the render PhysicalDevice is not marked REMOVED and the logical Device is not declared DEVICE_LOST without an exact positive backend loss result.
54. Two Screens attach the same render GPU but have different scanout GPUs: each (Device, Surface) query independently reports its actual route and capability set; no global per-PhysicalDevice present-support bit is inferred.
55. A temporary bridge-route outage occurs without a route-generation change: GetSurfaceCapabilities and new/pre-acceptance operations report DEVICE_UNAVAILABLE, but the render PhysicalDevice and logical Device remain AVAILABLE; a pending acquire and accepted QueuePresent use their respective first-terminal mappings.
56. Route invalidation races with acquire timeout, accepted presentation terminalization, and image release in both serialization orders: OUT_OF_DATE is committed only when route invalidation wins the relevant gate; an earlier terminal result or image-release milestone is never rewritten or retracted.

57. Two logical Devices created from the same PhysicalDevice query and create swapchains for the same Surface: each PresentationRoute is scoped to its exact logical-Device generation, even if both use the same DDX backend, PhysicalDevice, Window, and Screen. Destroying or invalidating one Device/route MUST NOT retire, invalidate, or redirect the other Device's route or Swapchain; stale callbacks from the first route generation MUST NOT affect the second.

58. A discovery source attempts to confirm physical removal without authoritative evidence for the exact current incarnation, or submits evidence from a stale source/device generation: the registry rejects the transition and MUST NOT mark the PhysicalDevice REMOVED. A later valid removal observation for the current incarnation commits REMOVED exactly once.

59. DDX backend context/device unavailable or recovery is submitted with an unknown DDX backend, stale DDX module-role generation, stale PhysicalDevice generation, or absent selected binding: the registry returns a classified non-success result and leaves all statuses unchanged. A valid transition returns SUCCESS and affects only the exact selected DDX binding context/binding scope.

60. A caller releases or mutates a temporary source/DDX backend key or descriptor immediately after a registry call returns: the registry's canonical keys and retained state remain valid because retained input bytes were copied or explicitly reference-counted before return. Conversely, backend operation tables, callback code, callback userdata, and DDX module-role record remain pinned until the final DDX backend reference and every operation token are safely retired; module/context teardown before that point is forbidden.



61. The platform hotplug subscription is active before initial enumeration; inject add/remove events during the scan and verify reconciliation produces exactly the current incarnation, with no lost event, duplicate publication, or stale removal.
62. Delay Screen creation and RandR initialization after all configured discovery adapters complete: the startup barrier closes and the same initial PhysicalDevice inventory is published without waiting for a ScreenAttachment.
63. Make one configured discovery adapter fail or report unavailable during startup: the barrier completes with that source unavailable, no candidate from it is falsely marked REMOVED, no incomplete snapshot is published, and unrelated fully discovered devices remain publishable.
64. Register a discovery adapter after the startup barrier closes: it cannot reopen the barrier or reorder/mutate existing PhysicalDevices; a newly discovered candidate follows the independent per-device publication path.
65. Have a DDX report a Screen mapping using only a Screen index, Entity index, private pointer, or unverified DRM pathname: the mapping remains unresolved and cannot create, merge, or attach a PhysicalDevice.
66. Unload a DDX/DDX module while an old Screen-generation callback or backend operation remains outstanding: new callbacks are stopped, old references remain pinned or quarantined, and neither module code nor callback userdata is released until exact-generation retirement proves quiescence.


67. On an XLibre build whose udev DRM discovery enumerates only `card[0-9]*` and deduplicates by major/minor, independently discover/correlate the render node for the same DRM device. Verify one canonical PhysicalDevice and prove that neither major/minor equality nor node name is used as its identity key.
68. Invoke the Xorg GPU-screen removal path for a device whose underlying hardware remains present: the exact ScreenAttachment and Xorg discovery observation are retired, but the PhysicalDevice is not marked REMOVED while authoritative platform/DDX backend evidence for the same incarnation remains.
69. Configure no Xorg primary bus so `xf86platformPrimary()` uses its first-platform-device fallback, then permute platform/Screen enumeration: XAverius canonical inventory order, DDX-binding selection, and `CreateDefaultDevice` remain unchanged.


70. Close a GPU Screen through the XLibre sequence `dixScreenRaiseClose()` → `RemoveGPUScreen()` → `xf86DeleteScreen()`. Verify that the exact ScreenAttachment is detached before Screen-private data is freed, while the shared DDX module-role registration, selected PhysicalDevice, and DDX module lease remain live if any other Screen, logical Device, route, or backend operation still references them.
71. In `FreeScreen()`, drop the ordinary Xorg Screen/module reference while an accepted backend operation is still pending. Verify that the independent DDX backend/module lease prevents unloading every backend operation, callback, trampoline, and userdata address reachable by that operation.
72. Race a DDX backend terminal callback with `retire_operation`. SUCCESS MUST NOT be returned until the callback has returned to the server-owned sink and no further callback for that exact token can begin. The server may process its copied completion record after DDX backend callback code has returned and the DDX module remains otherwise pinned.
73. Begin module-role-wide quiescence while callbacks, worker tasks, and operation tokens are outstanding. PENDING MUST retain the module/context and reject new operations; SUCCESS is permitted only after all callbacks/workers are unreachable and all operation tokens are retired. Inject an unquiesceable worker and verify quarantine rather than module unload.
74. Unload a DDX module that implements topology and DDX backend roles while a second Screen still uses the same PhysicalDevice through a different DDX. Verify that topology-role withdrawal detaches only the unloading DDX's ScreenAttachments, while the shared PhysicalDevice and separately owned DDX backend remain available.
75. Use a DDX backend callback bridge that enters DDX code and then queues a server-owned completion. Verify that both DDX backend and DDX module leases remain held until the bridge returns; retirement of the backend token alone cannot release the DDX module while bridge callback code is still executing.


76. Duplicate a DDX `ModuleDesc` for a GPU Screen, then remove that Screen and drop its `DriverPtr.refCount` while a DDX backend token remains live. Verify that the DDX binding's independent loader/module pin prevents `dlclose()` and keeps operation/callback code executable until exact DDX backend quiescence.
77. Delete the final Xorg Screen using a DDX that also implements a DDX backend. Verify that Xorg's normal driver/module cleanup cannot unload the DDX backend while a PhysicalDevice, logical Device, accepted operation, callback, or deferred backend destroy still retains the DDX module-role generation; after successful module-role-wide quiescence and final release, the loader pin is dropped exactly once.


78. Close and delete a GPU Screen while a DDX backend callback still holds attachment-scoped state. Verify that the callback has no raw `ScreenPtr`/`ScrnInfoPtr` or `FreeScreen()`-owned pointer to dereference; it uses only a detached, generation-checked retained context, performs no Screen/RandR callback after close, and releases that context only after callback return and operation retirement.



79. Register two complete DDX bindings from different module roles against the same canonical PhysicalDevice. Configure the role owner-key preference in the opposite order from registration and verify that the first eligible configured key is selected before publication, with the complete snapshot and operation vectors taken wholly from that binding. Repeat with no matching preference and two eligible bindings: the PhysicalDevice MUST remain unpublished as ambiguous. Make the preferred binding ineligible through a failed mandatory snapshot query and verify that the next eligible configured binding is selected. Removing or quiescing the non-selected binding MUST NOT change PhysicalDevice status, XID, snapshot, or selected-binding identity. After publication, register a newly higher-preference binding and verify that it MUST NOT replace the selected binding or snapshot.

80. Register one DDX module-role generation against several PhysicalDevices, then report a binding-scoped unavailable/removal transition for one device. Verify that only that exact binding/device is affected. A module-role-wide failure affects every PhysicalDevice selected through that exact DDX module-role generation, but does not affect a canonical PhysicalDevice whose selected binding belongs to another module role, even if the failing role also has a non-selected complete binding registered for that identity.

81. Have two DDX/platform sources independently observe the same canonical PhysicalDevice. Withdraw or unload one source while the other remains authoritative. Verify that only the first source's observation and its owned ScreenAttachments disappear; the PhysicalDevice identity, other source observation, and unrelated DDX device binding remain.

82. Have one DDX module register two independent GpuModuleRole generations with distinct contexts and DDX backend keys. Quiesce and unregister one generation while the other still serves a PhysicalDevice. Verify that the first generation rejects new operations and eventually releases only its own references, while the common module lease remains pinned and the second DDX backend continues operating unchanged.

83. Race Screen close, source withdrawal, selected/non-selected binding removal, DDX module-role shutdown, and authoritative physical removal in both serialization orders. Verify that each transition affects only its exact generation and ownership scope; REMOVED is terminal, stale callbacks are rejected, and no operation implicitly performs another transition's broader cleanup.

84. Remove or quiesce the selected DDX binding while another DDX device binding for the same PhysicalDevice remains available. Verify that the PhysicalDevice becomes UNAVAILABLE and is not transparently rebound, that the published snapshot is unchanged, and that no existing logical Device silently migrates to the other DDX backend.

85. Register multiple DDX-local Vulkan aliases for one canonical PhysicalDevice through one DDX module-role generation. Verify that the DDX backend deduplicates them and registers exactly one executable binding; if alias identity is ambiguous, no competing binding or PhysicalDevice publication is permitted.

86. Attach two Screens through different DDX modules to one PhysicalDevice and one shared DDX backend. Close/unload one DDX module. Verify that only its ScreenAttachment and adapter role retire; the other ScreenAttachment, selected DDX binding, PhysicalDevice, and DDX module lease remain live.

87. Quiesce one of several DDX module-role generations backed by the same module while another generation still has a pending callback. Verify that SUCCESS for the first DDX backend does not release the common module pin or make the second DDX binding's callback unreachable; final module unload occurs only after all role-specific leases and callback bridges have retired.

88. Race `GpuRegistryBeginModuleRoleShutdown` against a new operation and a new DDX device registration owned by that module-role generation. If shutdown serializes first, both are rejected without partial state; if either admission serializes first, it is retained and drained before quiescence. Repeated shutdown calls are idempotent, while a stale module-role generation is rejected without affecting its replacement.



89. Register one module-role control record, then have the DDX independently register several served PhysicalDevices through `GpuRegistryRegisterDdxDevice`. Verify that each binding retains its own native handle, per-device context, and immutable operation vectors, while all bindings retain the shared module role exactly once each. Removing one binding releases only that binding's device resources and role reference; other bindings and the shared module lease remain live.

90. Attempt `GpuRegistryRegisterDdxDevice` before its owning module role is registered, with a stale role generation, or after `GpuRegistryBeginModuleRoleShutdown`. Verify each attempt is rejected atomically and creates no binding, callback path, or leaked reference. A role generation is never reused, including after failed registration; a replacement role receives a distinct generation.

91. Register two DDX module-role generations and one DDX adapter role sharing a single module lease. Quiesce/finalize one DDX backend while the other DDX backend has an outstanding operation and the adapter role remains active. Verify the first DDX module-role state is finalized while the shared module remains pinned; only after all DDX backend and adapter role references are released may the loader perform final module unload.

92. Make quiesce_module_role return PENDING, then FAILURE, then SUCCESS in separate runs. Verify PENDING retains the DDX backend/module lease and permits retry; FAILURE quarantines without finalization; SUCCESS records quiescence but still does not release the module lease while logical-device/DDX backend-object references remain. Verify finalization calls release_module_role before the final lease release, exactly once.

93. Attempt module-role finalization while a logical Device, deferred backend destroy, callback bridge, or DDX-owned object still retains that module-role generation. Verify the operation remains pending and no DDX module-role state, operation table, callback userdata, or module lease is released.



94. Begin module-role shutdown while a deferred backend destroy and a live DDX-owned object remain. Verify that quiescence is not invoked until the destroy has completed or the object is quarantined without further DDX backend-code requirements. After quiescence SUCCESS, attempt a backend destroy and verify that it is rejected; only the single registry-controlled final release_module_role call may enter DDX module code before the module-lease reference is dropped.

95. Create a module lease using a duplicated Xorg ModuleDesc, a ScrnInfo pointer, or a DriverPtr reference without an independent loader pin. Verify that lease creation/registration is rejected or the module is marked permanently resident; none of these Screen-scoped references may be accepted as proof against final dlclose(). Verify that a valid server-owned loader-owner record yields one shared lease for all DDX backend and adapter roles in that loaded module instance.



96. Reserve a module-role generation, fail module-role registration after descriptor validation/allocation, and then register a replacement module role. Verify that the failed generation is never reused, stale completion records carrying it are rejected, and the replacement receives a distinct generation before any binding or operation is accepted.

97. Call registry APIs with required pointers omitted, zero generations, unknown role bits, malformed keys, and inconsistent input/output pairs. Verify `INVALID_ARGUMENT`, initialized output sentinels, no mutation, and no leaked references.

98. Obtain PhysicalDevice, GpuModuleRole, ModuleRole, and ScreenAttachment references from successful APIs, then race release against detach, binding removal, DDX backend shutdown, and registry shutdown. Verify each acquired reference is consumed exactly once and storage is not reclaimed while any reference or callback remains.

99. Register and unregister a discovery source while observations and delayed callbacks exist. Verify source generations are server-assigned/non-reusable, unregister returns PENDING while callbacks remain, and late observations from the closed generation are rejected without affecting a replacement source.

100. Register a DDX backend with an incomplete operation table, invalid module lease, or failing descriptor validation. Verify no DDX backend is installed and every acquired lease/context reference is unwound exactly once; successful registration returns exactly one caller-owned DDX backend reference.

101. Register a binding with a stale PhysicalDevice/DDX module-role generation, duplicate DDX-local binding, or conflicting identity. Verify the registry assigns the binding generation, rejects invalid cases atomically, and never creates duplicate references or active bindings.

102. Attach a Screen with stale device generation, zero Screen generation, unknown role bits, or a Screen already closing. Verify a classified failure and no retained Screen pointer; exact duplicate attachment returns the same attachment generation without duplicate registry state.

103. Force XID allocation and DIX resource insertion to fail at each publication step. Verify no partial client-visible resource, no leaked provisional XID, and no published flag; retry succeeds with one stable XID. Repeated publication returns that same XID.

104. Acquire the selected DDX binding while the PhysicalDevice is pending, unavailable, removed, or its DDX backend is shutting down. Verify no DDX backend reference leaks and no stale DDX module-role generation is returned; success pins the exact selected DDX binding until release.

105. Call BeginShutdown while source unregister, DDX backend quiescence, Screen detach, and publication are pending. Verify admission closes, Destroy returns BUSY without invalidating existing references, and final Destroy succeeds only after every object/callback/module lease is retired.

106. Submit duplicate, late, malformed, and conflicting completion records, including a DDX backend that returns synchronous failure and later calls back. Verify only accepted tokens terminalize once, payload is copied/retained safely, stale generations are ignored, and callback/token/module references are not released early.

107. Return PENDING and AMBIGUOUS from ObserveDevice and verify a nonzero observation ID is returned while device pointer/generation remain NULL/zero; withdraw that exact observation and verify no other source evidence is affected.

108. Return FAILURE from quiesce_module_role. Verify TryQuiesceModuleRole returns QUARANTINED with FAILURE output, does not call final release_module_role, and retains the DDX module-role record and module lease permanently unless an explicit safe-recovery contract is added.

109. Return PENDING from UnregisterDiscoverySource and DetachScreen while callbacks still run. Retry with the same exact generation after callback return and verify one final retirement, no duplicate detach, and no premature object reclamation.

110. Verify completion records identify the exact DDX module-role generation, operation token, DDX-local binding, PhysicalDevice generation, logical-Device ID/generation, and resource ID/generation without carrying a raw Xserver or registry object pointer. Reused addresses/XIDs cannot redirect a completion.

111. Race GpuModuleLeaseCreate/Retain/Release with DDX module-role registration/finalization and adapter-role teardown. Verify one shared lease per loaded module-owner identity, no underflow/double unpin, and no final loader release before every role has released its reference.

112. Force DDX backend retain/context initialization and module-pin acquisition failures at each registration stage. Verify registration is atomic, the caller's original lease remains owned by the caller, registry-acquired references are unwound exactly once, and DDX backend code is never called after its lease is released.

113. Register a DDX module role, attach a discovery source and multiple ScreenAttachments to it, then request role unregister. Verify admission closes immediately, unregister remains PENDING until the source, attachments, and callback bridges retire, and the shared module lease is released exactly once afterward. A caller-held role reference may keep only the inert server-owned role record alive and does not delay module unpin. A second DDX role sharing the same lease remains active.
114. Attempt to retain or register new callbacks against a module role after unregister begins. Verify SHUTTING_DOWN and no new reference/callback admission; releasing already-held references remains permitted until the role retires.

115. Prepare an operation token against an unknown/stale DDX module-role generation, removed binding, unavailable PhysicalDevice, or stale logical-Device/resource generation. Verify a classified rejection, zeroed outputs, and no DDX backend entry or retained reference.

116. Complete an operation callback before CommitOperationSubmission returns. Verify the completion is buffered and cannot affect public state until the DDX backend entry point returns SUCCESS and commit is serialized. If the DDX backend returns failure after callback/backend acceptance, verify QUARANTINED rather than token release.

117. Have a DDX backend return synchronous failure and then attempt a late callback, or return SUCCESS but never provide a terminal outcome. Verify the first case quarantines the token/DDX backend and the second retains all references indefinitely until a terminal outcome or server shutdown quarantine policy.

118. Make retire_operation return PENDING, FAILURE, and SUCCESS. Verify PENDING is retryable, FAILURE quarantines all dependent objects and prevents DDX backend quiescence, and SUCCESS releases token-held references exactly once only after callback return and backend-access cessation.

119. Race token preparation/commit/rejection/retirement against `GpuRegistryBeginModuleRoleShutdown`, DestroyDevice, resource destroy, and disconnect. Verify the registry serialization point determines admission; accepted tokens drain, rejected tokens cannot callback, and stale terminal records cannot affect replacement generations.

120. Verify every asynchronous DDX backend entry point in the typed tables receives exactly one prepared token and the matching operation kind: WriteBuffer, ReadBuffer, host SignalSemaphore, QueueSubmit, AcquireNextImage, and QueuePresent. Reject missing, mismatched, or reused tokens before DDX backend entry.

121. Return STATUS with NOT_READY from AcquireNextImage and OUT_OF_DATE/SURFACE_LOST from valid presentation operations. Verify each status is accepted only for its defined operation and all other operation/status combinations are FATAL DDX backend-contract violations.

122. Submit an operation with multiple referenced resources (including QueueSubmit command buffers, buffers, semaphores, and fences). Verify the registry copies and retains the complete unique resource-generation set before DDX backend entry, rejects duplicates/cross-Device resources, and releases every retained reference exactly once at retirement.

123. Attempt to retain the opaque operation-token pointer in DDX backend callback userdata and dereference it after the entry point returns. Verify the DDX backend-facing contract forbids this; only copied token ID/generation may cross the asynchronous boundary, and stale IDs cannot resolve a replacement token.

124. Return malformed completion records with mismatched operation kind, primary resource, DDX backend/token generation, or oversized payload. Verify the sink rejects them without state mutation, copies bounded payloads before callback return, and preserves the token's complete server-owned resource set.

125. Attempt to set removal-evidence authority from caller-controlled input. Verify no such field is accepted: the registry derives authority solely from the registered source capabilities, source generation, observation provenance, and server trust policy.

126. Call BeginShutdown while PrepareOperation races new submissions. Verify shutdown serialization closes operation-token admission, while already prepared/accepted tokens remain pinned and drain under their DDX module-role generation.

127. Return STATUS/ALREADY_COMPLETED from cancel_acquire after the backend image acquisition has already terminalized. Verify cancellation does not create a second completion or change the first terminal outcome; the server still performs late-image release/retention as required.

128. Have a DDX enumerate zero, one, and multiple devices and call `GpuRegistryRegisterDdxDevice` once for each served device. Verify there is no candidate-list API, every native handle and per-device context is stored as a borrowed opaque value in its binding and remains DDX-owned until binding removal, and partial registration failure leaves no published XID or leaked reference.

129. Remove a DDX device binding while an operation or deferred object still references its native handle. Verify the binding and handle remain alive until all operation/object references retire, and a stale binding generation cannot resolve a replacement binding.

130. Have one DDX module role register several PhysicalDevices with distinct native handles and per-device contexts. Verify each binding dispatches to its own handle/context while sharing only the module-role lifetime record and module lease.

131. Verify no generic module-role context accessor exists. Every device operation receives the exact binding context/native handle, while module-role APIs expose only generation-checked lifetime retain/release and quiescence.

132. Deliver a completion with the correct native handle stored directly in the binding and PhysicalDevice generation but a stale or mismatched registry binding generation. Verify it is rejected and cannot affect a replacement binding for the same PhysicalDevice/DDX module-role generation.

133. Deliver module-role-wide unavailable/recovered notifications out of order, with lower, duplicate-same-state, and duplicate-conflicting availability sequences. Verify stale events return STALE_EVENT, exact duplicates are idempotent, conflicting reuse is rejected, and an old loss cannot overwrite a newer recovery.

134. Remove and re-register a DDX device binding for the same DDX module-role generation/PhysicalDevice incarnation, then deliver an availability notification from the old binding generation. Verify it is rejected without changing the replacement binding.

135. Make the DDX module role unavailable while one binding is independently unavailable, then recover the context only. Verify the PhysicalDevice remains UNAVAILABLE until the exact binding also recovers; recovery at one scope never clears the other scope's failure.

136. Deliver discovery-source events out of order across concurrent scan/hotplug callbacks. Verify the per-source event sequence rejects older observations, exact replay is idempotent, and the same sequence with conflicting payload returns IDENTITY_CONFLICT.

137. Deliver a removal observation captured before a later add/update but dispatched afterward. Verify source_event_sequence and PhysicalDevice generation reject the stale removal and leave the current incarnation unchanged.

138. Prepare each defined operation kind with missing logical-Device identity, an empty resource set, incomplete WriteBuffer/ReadBuffer memory pins, a QueueSubmit dependency set missing one referenced object, or an Acquire/Present token missing its Swapchain/route/synchronization references. Verify rejection before DDX backend entry and no partial reference retention.

139. Return GPU_BACKEND_FATAL from a backend operation and separately trigger a server-detected contract violation. Verify immediate DDX module-role-generation quarantine, closed admission, UNAVAILABLE status for its selected devices without REMOVED, retained module-role/binding/object references, and no normal finalization. Return DEVICE_LOST from one logical Device and verify other Devices/PhysicalDevices remain available; return CANCELLED only through an accepted operation's terminal completion.

140. Race new DDX binding, ModuleRole, and ScreenAttachment Retain calls against shutdown/detach. Verify admission closes at the serialized transition, new retains fail with SHUTTING_DOWN, and existing references can still be released. Repeat Commit/Reject/Retire/Quiesce/Finalize calls in every terminal state: Commit of the exact accepted token, Reject of the exact rejected token, and Retire of the exact successfully retired token return idempotent SUCCESS; Commit after rejection and Reject after acceptance return IDENTITY_CONFLICT; Retire before terminalization returns BUSY; Quiesce after successful quiescence but before finalization returns SUCCESS; Quiesce/Finalize after finalization and unknown token/role generations return NOT_FOUND as specified.

141. Replay a successful ObserveDevice call with the same source event sequence and payload while the caller still holds the previous PhysicalDevice reference. Verify the observation ID is unchanged, the source observation is not duplicated, and the repeated SUCCESS returns exactly one additional caller-owned reference that must be released independently.

142. Quarantine a DDX module-role generation through `GPU_BACKEND_FATAL`, then call `GpuRegistryTryQuiesceModuleRole` and `GpuRegistryFinalizeModuleRoleShutdown`. Verify both return QUARANTINED without entering DDX module code or dropping DDX binding/context/module/object references.


These tests validate the server architecture; they do not replace the wire-level conformance vectors in `conformance.md`.
