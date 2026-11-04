# Server-Side Physical-Device Registry Architecture

**Status:** Implementation architecture contract for XAverius v0.1. This document does not define wire fields or Vulkan backend implementation details. The protocol requirements in `devices.md` remain authoritative if a conflict is found.

## 1. Object model and ownership

The server MUST maintain one process-wide Physical-Device registry. It MUST NOT be owned by an X11 Screen, Xorg Entity, DDX instance, DRM node, Vulkan instance, or XAverius client connection.

The model has four distinct object classes:

1. **PhysicalDevice** — one canonical physical-device incarnation exposed by the server. It owns the server-lifetime identity, immutable published metadata snapshot, current discovery status, and references to registered providers. It is the sole source for XAverius Physical-Device enumeration and properties.
2. **BackendProvider** — one concrete backend execution/discovery context capable of querying and operating on a PhysicalDevice. It owns provider-specific handles, dispatch tables, backend objects, and module/library references. A provider is attached to one or more PhysicalDevices only through explicit canonical matching; it is never itself a PhysicalDevice identity.
3. **ScreenAttachment** — a relationship between one live X11 Screen generation and one PhysicalDevice. It records that a Screen/DDX path uses or can access a device for a particular role. It does not own either endpoint and does not establish Vulkan presentation support.
4. **PresentationRoute** — an internal, generation-checked route for one exact logical-Device/Surface pair. It identifies the selected execution provider, the retained Window/Screen generation, and any explicit scanout/bridge path needed to present images produced by that logical Device. It is not a PhysicalDevice, Screen, Vulkan Device, or client-visible XAverius resource; it owns no endpoint and allocates no XID.

The relationships are:

- One PhysicalDevice MAY have zero or more BackendProviders.
- One PhysicalDevice MAY have zero or more ScreenAttachments.
- One Screen MAY have zero or more ScreenAttachments; a Screen is not required to map to exactly one GPU.
- One Surface MAY have distinct PresentationRoutes for different logical Devices; a route is scoped to one exact logical-Device generation and Surface/Window/Screen generation.
- A PresentationRoute MAY reference a scanout PhysicalDevice/ScreenAttachment and a private bridge adapter, but it MUST NOT change the logical Device's render PhysicalDevice or selected execution provider.
- A BackendProvider MUST NOT be implicitly created or destroyed with a ScreenAttachment.
- Destroying a Screen or detaching a provider MUST NOT destroy the PhysicalDevice identity.
- A PhysicalDevice MUST NOT be destroyed while its tombstone or any logical-device/backend reference remains live.

The registry owns PhysicalDevice records and their canonical identity. The backend/provider manager owns BackendProvider lifetimes. The Screen/DDX layer owns ScreenAttachment lifetimes. The XAverius presentation subsystem owns PresentationRoute records and their generation/lifetime arbitration; the selected provider owns each route's private backend objects. XAverius owns the protocol resource/XID wrapper for each published PhysicalDevice. These ownership boundaries MUST remain explicit.

## 2. PhysicalDevice identity and publication

The registry MUST canonicalize a discovery candidate before the corresponding PhysicalDevice is published or assigned a Physical-Device XID. All discovery sources MUST submit candidates to the same registry, including Xorg platform probing, udev hotplug, DDX-specific discovery, Vulkan-loader enumeration, and any future non-Xorg backend.

A candidate MUST carry structured identity evidence, not just a string name or a backend pointer. The evidence SHOULD include:

- bus type and canonical bus identity (for PCI, full domain:bus:device.function);
- resolved canonical kernel/sysfs device path where available;
- DRM device identity sufficient to equate primary and render nodes;
- Vulkan deviceUUID when valid;
- an instance discriminator for mediated, virtual, partitioned, or derived devices;
- an incarnation token/generation that changes after confirmed removal and re-addition;
- descriptive vendor/device IDs and names as metadata, not as unique identity.

The registry applies the identity rules in `devices.md`. In particular, node path, `dev_t`, DRM minor, Screen index, Vulkan handle/pointer, and model name MUST NOT independently key a PhysicalDevice.

A PhysicalDevice has an internal, non-reusable server identity (for example, an opaque pointer paired with a generation or a monotonically allocated 64-bit registry ID). That internal identity is distinct from the protocol XID. The XAverius layer allocates exactly one server-owned Physical-Device XID when the canonical record is published, and retains the mapping until server shutdown. The registry MUST NOT expose a mechanism for a DDX/provider to choose or allocate that XID.

Provider discovery MUST have a defined completion point before first publication. For initial server startup, implementations SHOULD complete the configured discovery pass and deterministic provider selection before XAverius makes the inventory visible to clients. A provider discovered later MAY be attached to an already published PhysicalDevice, but MUST NOT silently replace its selected execution provider or mutate its published metadata snapshot. This avoids making identity, capabilities, or default-device selection depend on whichever ICD or Screen happened to initialize first.

## 2.1 Discovery-source and driver-registration contract

Discovery, execution-provider registration, Screen topology, and XAverius publication are separate operations. A driver or discovery adapter MUST NOT perform all four implicitly.

A discovery source is a producer of observations, not a fourth persistent registry object. It may be the Xorg platform bus, udev, a DDX driver, a Vulkan ICD/provider, or another server backend. A source has a stable source key and a non-reusable source generation. Its observations are immutable identity evidence plus source-local metadata; they do not themselves create a PhysicalDevice XID or select an execution provider.

The registration paths are:

1. **Observe hardware identity.** A discovery source submits a candidate identity to the process-wide registry. The registry canonicalizes it and returns an internal generation-checked PhysicalDevice reference, or leaves it unpublished while identity evidence is incomplete or ambiguous. An observation may enrich identity evidence but MUST NOT overwrite an already published immutable property snapshot.
2. **Register an execution provider binding.** A Vulkan-capable provider registers its private provider context and the provider-local physical-device binding against the canonical PhysicalDevice reference. This is a separate operation from observing the hardware. A provider may register bindings for many PhysicalDevices; one PhysicalDevice may have bindings from multiple providers.
3. **Select and snapshot.** During the initial discovery pass, the server selects exactly one eligible execution provider per PhysicalDevice according to Section 3, queries the complete snapshot through that provider, and only then publishes the PhysicalDevice and allocates its server-owned XID. No Screen or DDX initialization order participates.
4. **Attach Screen topology.** A DDX/Screen path attaches the live Screen generation to one or more already canonicalized PhysicalDevices with explicit roles. This does not create an identity, register a Vulkan provider, select the execution provider, or prove WSI support.
5. **Report lifecycle observations.** Sources report provider-context loss/recovery, provider-local binding loss/recovery, Screen detach, and confirmed physical removal as distinct observations. The registry serializes them and applies the lifecycle rules in Sections 5–6.

A component MAY implement more than one role, but it MUST register each role explicitly and MUST obey each role's ownership boundary. In particular, a DDX that only discovers or drives scanout MUST report identity/topology observations; it MUST NOT be registered as a BackendProvider unless it actually implements the complete provider operation contract required by the capabilities it advertises. Conversely, a Vulkan provider MUST NOT create ScreenAttachments merely because it enumerated a PhysicalDevice.

### Registration semantics

The internal registration API SHOULD expose distinct operations equivalent to:

- `GpuRegistryObserveDevice(source, source_generation, identity_evidence)`: submit or update an observation. Returns a generation-checked canonical record reference only when identity matching is unambiguous; it never allocates a protocol XID.
- `GpuRegistryRegisterProviderBinding(device_ref, provider_descriptor, provider_local_binding)`: attach a provider-local handle to the exact canonical identity. It does not publish the PhysicalDevice or select the provider by registration order.
- `GpuRegistryRemoveProviderBinding(device_ref, provider_generation, binding_generation)`: stop new calls through that binding and apply the selected-provider unavailability rules; it is not physical removal.
- `GpuRegistryRemoveObservation(source_generation, observation_id)`: withdraw only that source's evidence. It MUST NOT mark hardware REMOVED while other authoritative evidence still establishes the same incarnation.
- `GpuRegistryConfirmDeviceRemoved(device_ref, device_generation, removal_evidence)`: commit terminal REMOVED only on authoritative evidence that the physical incarnation was removed.
- `GpuRegistryAttachScreen(device_ref, screen_generation, roles)` and `GpuRegistryDetachScreen(attachment_generation)`: manage only the non-owning topology relation.

These names are semantic API guidance, not required exported symbols. Registration and removal calls from worker threads MUST enqueue immutable observations into the server serialization domain; they MUST NOT mutate registry state directly. All returned references and handles MUST be opaque and generation checked. A source/provider MUST NOT retain or resolve a record by a bare pointer, XID, array index, DRM minor, or Screen number after the call returns.

An ambiguous identity match is not a license to merge or publish. The registry MUST keep the candidate unpublished and report the ambiguity to the registering source/server log until stronger evidence resolves it. If evidence proves that two published identities were duplicates, the implementation MUST NOT silently reassign or reuse a client-visible XID; this is a server consistency fault requiring controlled recovery, not an ordinary hotplug merge.

### 2.2 Identity-evidence hierarchy and provider correlation

Identity matching MUST be based on the underlying device incarnation, not on whichever identifier is easiest for a discovery adapter to obtain. The registry MUST retain the provenance and generation of each evidence item so that a stale observation cannot strengthen or override current evidence.

The following evidence classes define the v0.1 matching policy:

1. **Authoritative platform identity.** A resolved kernel device object and its bus identity are the primary platform correlation evidence. For PCI, use the complete domain:bus:device.function address together with the resolved canonical sysfs device path and the current device incarnation. For other buses, use the equivalent bus/subsystem identity and canonical parent/device relationship. A pathname alone is not authoritative if it can be replaced or reused.
2. **DRM-device equivalence.** Primary and render nodes MUST be correlated through the kernel's underlying DRM device identity (for example, `drmGetDevice2`/`drmDevicesEqual`, or equivalent bus information and canonical sysfs ancestry). Both nodes are access interfaces for one device, not separate devices. A node's basename, major/minor, `dev_t`, or DRM minor is only an observation locator and MUST NOT be the canonical key. Different DRM nodes MUST NOT be merged merely because they have the same vendor/device IDs.
3. **Vulkan cross-instance correlation.** A valid nonzero `deviceUUID` is strong corroborating evidence for joining provider-local `VkPhysicalDevice` observations to a platform identity and to one another. It MUST be checked against authoritative platform evidence when both are available. Equal UUIDs with incompatible authoritative platform identities are a conflict, not permission to merge; differing UUIDs for observations with the same authoritative platform identity are also a conflict that MUST be resolved before provider binding or publication.
4. **Derived-device identity.** A mediated, SR-IOV virtual function, partition, MIG instance, or other derived device MUST be distinguished from its parent and from sibling instances by an authoritative instance-specific identity. Parent identity alone MUST NOT merge children. A parent/child relation MAY be retained as descriptive topology, but it is not identity equality.
5. **Provider-scoped fallback identity.** A software, virtual, or non-enumerable device without a usable platform identity MAY be represented only when its discovery provider supplies a stable namespace and instance identity that distinguishes it from every other concurrently exposed instance. That key is provider-scoped and MUST NOT be treated as proof that another provider's candidate is the same device. Cross-provider merging requires independent corroboration.
6. **Descriptive metadata.** Vendor/device/subsystem IDs, names, driver strings, API versions, and marketing descriptions MAY reject an obviously inconsistent candidate but MUST NOT establish identity or incarnation equality by themselves.

The registry MUST apply these outcomes:

- Matching authoritative platform identity and compatible incarnation evidence joins observations into one canonical identity, even if provider handles or Vulkan UUIDs differ; a conflicting UUID is recorded and must be resolved before that provider binding is eligible.
- Matching valid `deviceUUID` without conflicting platform evidence MAY join provider observations. If either observation later gains contradictory authoritative platform evidence, the registry MUST quarantine the conflicting observation/binding and MUST NOT merge the platform devices.
- Equal UUIDs without enough evidence to distinguish two simultaneously present devices are ambiguous. The candidates remain unpublished until resolved; the registry MUST NOT collapse them solely to avoid duplicate enumeration.
- Different UUIDs with no authoritative platform correlation do not establish either sameness or difference. The candidates remain distinct pending stronger evidence; the registry MUST NOT infer sameness from names or model IDs.
- A provider candidate that cannot be correlated to a canonical platform identity MAY use the provider-scoped fallback only for a device class whose identity contract guarantees stable per-instance uniqueness. Otherwise it remains unpublished and cannot be selected for execution.
- Any conflict involving two already published identities MUST NOT be repaired by merging, changing an XID's referent, or silently rewriting the immutable snapshot. It is a registry consistency fault requiring controlled server recovery.

Incarnation is separate from identity correlation. A confirmed remove event closes the current incarnation. An add event after that boundary creates a new incarnation even when the BDF, sysfs path, DRM identity fields, provider-scoped key, and `deviceUUID` are unchanged. If removal is uncertain, the registry MUST prefer an UNAVAILABLE or unresolved state over either falsely declaring REMOVED or resurrecting a tombstone. Source generations and event ordering MUST be used to reject delayed remove events from an earlier incarnation.

A caller-supplied `GpuDeviceRemovalEvidence` is not authoritative merely because it sets a nonzero `authority` value. The registry MUST resolve `source_key` to a currently registered discovery source, validate the exact `source_generation` and `observation_id`, and derive or verify the permitted authority class from that source's registered capabilities and trust policy. The caller MUST NOT be able to elevate a source's authority by choosing the field value. The evidence's `physical_device_generation` MUST identify the current incarnation, and the referenced observation MUST contain a removal indication sufficient for that authority class. Missing, contradictory, stale, or insufficient evidence returns a classified non-success result and leaves status unchanged. Only a validated authoritative removal commits terminal REMOVED, exactly once.

A Vulkan provider binding MUST identify the exact provider-local physical-device instance and carry the identity evidence used to correlate it. One provider may expose the same hardware through more than one Vulkan instance; those handles may map to one canonical PhysicalDevice only after the above correlation succeeds. A provider MUST NOT claim a binding merely because its candidate has matching vendor/device IDs or a matching display name.

### 2.3 Canonical ordering key

Every unambiguous, publishable PhysicalDevice MUST have one canonical ordering key derived from the same canonical identity record used for deduplication. The key is an internal comparison value; it is not a wire property, a persistent identifier, or a client-visible sort guarantee.

The key MUST be a typed, normalized tuple and MUST NOT contain provider registration order, Vulkan enumeration index, pointer value, DRM minor, node pathname without its canonical device relationship, Screen index, or mutable descriptive metadata. The v0.1 tuple is ordered first by identity class, then by that class's canonical identity components:

1. Platform-backed devices: bus-type tag, normalized bus identity (for PCI, the complete domain:bus:device.function; for other buses, the canonical bus/subsystem identity), and the normalized instance discriminator when required.
2. Derived devices: derived-device class tag, canonical parent identity key, and authoritative child-instance discriminator.
3. Provider-scoped software/virtual devices: software/virtual class tag, stable provider namespace key, and provider-supplied stable instance key.
4. Devices with no platform identity but a valid, unambiguous cross-instance `deviceUUID`: UUID-only class tag and the exact 16 UUID bytes.

Comparison is bytewise lexicographic over the canonical tuple encoding, with fixed-width numeric fields encoded in a documented normalized order and variable strings length-delimited. Implementations MUST use one canonical encoding and comparison function throughout the registry; locale-sensitive string collation is forbidden. A collision between two distinct live canonical records is an identity ambiguity and MUST be resolved before either record is published. An incarnation token distinguishes removal/re-addition for lifecycle and stale-event rejection, but MUST NOT make a replacement device sort as the old published incarnation or permit tombstone resurrection.

This key defines the default ordering used by `CreateDefaultDevice` when no explicit default-device preference is configured. An explicit preference list MUST use stable canonical identity selectors, not XIDs, BDF enumeration positions, DRM node numbers, or Screen indices. A selector MUST resolve to at most one canonical identity; duplicate or ambiguous selectors are configuration errors. The server filters for AVAILABLE devices and queue-family suitability before applying the preference list or canonical-key ordering. If a preferred device is unsuitable, it proceeds to the next preference; if no preference matches a suitable device, it uses the lowest canonical key among all suitable devices. This selection never changes an already-created logical Device or the selected execution provider of any PhysicalDevice.

### Startup, late registration, and removal

Initial publication has a server-wide discovery barrier: all configured discovery sources and providers complete their initial candidate pass, identity canonicalization, deterministic provider selection, and snapshot query before the XAverius inventory is exposed. Enumeration order and Screen initialization order MUST NOT affect the resulting inventory or selected provider.

A provider or source discovered after publication MAY add corroborating evidence or a non-selected provider binding to an existing identity. It MUST NOT replace the selected provider, mutate the published snapshot, or cause a second XID. A newly hotplugged physical-device incarnation discovered after the startup barrier follows the same canonicalize/select/snapshot/publish sequence independently before it becomes visible to clients. v0.1 does not support transparent execution-provider failover. If the selected provider binding is withdrawn or its provider context is permanently deregistered, the PhysicalDevice becomes UNAVAILABLE and remains so until the same selected provider generation can recover; a new provider generation is not transparent recovery. The PhysicalDevice becomes REMOVED only after confirmed removal of that hardware incarnation.

A DDX unload or Screen teardown MUST detach every ScreenAttachment owned by that exact Screen generation before its Screen-private state is freed. It MUST also withdraw any discovery observations and provider registrations that it owns, each through their distinct lifecycle operations. Detaching the last Screen does not remove a PhysicalDevice: headless, off-screen, render-only, or temporarily unbound devices remain in the server-wide inventory if their physical/provider discovery remains valid. Similarly, removing one DRM access node does not prove physical removal if another node or authoritative source still identifies the same device.

A confirmed physical removal is server-wide and independent of Screen membership. It invalidates future logical-device creation for that incarnation and leaves its PhysicalDevice tombstone/XID in the inventory. A stale remove or detach observation carrying an older source, provider, Screen, or device generation MUST NOT affect a replacement incarnation.

### Driver-facing responsibilities

| Component | May report/register | MUST NOT decide |
|---|---|---|
| Xorg platform bus / udev adapter | Bus identity, DRM node observations, authoritative add/remove evidence | PhysicalDevice XID, Vulkan provider selection, published capabilities |
| DDX driver | Screen-to-device identity mapping, ScreenAttachment roles, driver-owned provider context if it implements the full provider contract | Server-wide identity deduplication, global inventory membership, default-device choice |
| Vulkan ICD/provider adapter | Provider identity, provider-local physical binding, complete snapshot, classified availability/loss results, backend operations | XAverius XIDs, Screen ownership, request validation, public state/event mutation |
| XAverius registry/resource layer | Canonical identity, provider selection, snapshot publication, PhysicalDevice XID, status/event serialization | Direct dereference of provider-private Vulkan handles |
| WSI/presentation path | Exact provider-local Surface and Device/Surface capability operations | Infer presentation support from ScreenAttachment or Screen number |

On Xlibre/Xorg, the recommended arrangement is one XAverius-owned registry service with thin adapters: platform/udev discovery feeds identity observations; DDX Screen initialization feeds attachments; Vulkan ICD/provider adapters register executable bindings. This keeps the registry independent of any one DDX and prevents the first XAverius-capable Screen from becoming an accidental global GPU selector.


### 2.4 Xlibre/Xorg discovery and DDX integration profile

This subsection defines the required integration behavior for an Xlibre/Xorg server. It deliberately does not prescribe private Xserver hook names or a particular DDX module layout: those vary between server versions and drivers. An implementation MUST provide equivalent lifecycle points and preserve the ownership and ordering rules below.

#### Registry service and adapter roles

The XAverius registry MUST be one server-process service, initialized independently of individual Screen creation. It MUST NOT be instantiated per Screen, per Xorg Entity, per DDX module, per DRM file descriptor, or per Vulkan instance. All adapters MUST register with that same service and use its generation-checked registration operations.

The Xlibre integration SHOULD expose three adapter roles:

- **Platform discovery adapter:** enumerates platform devices and observes kernel/DRM add, change, and remove events. It supplies canonical bus/sysfs identity and DRM-node equivalence evidence where available. A udev monitor is an event source, not a separate device inventory.
- **DDX topology adapter:** reports which canonical PhysicalDevice identities a Screen can access and the roles of those relationships. It MUST NOT select a global device, provider, or default device. A DDX MAY additionally register as a BackendProvider only if it implements the complete provider operation and lifetime contract for every capability it advertises.
- **Vulkan provider adapter:** enumerates provider-local physical-device candidates, correlates them with canonical platform identities, queries the complete immutable snapshot, and registers executable bindings. It MUST NOT create ScreenAttachments or infer presentation support from Xorg Screen state.

One module MAY implement more than one role, but it MUST register and retire each role independently. In particular, unloading a DDX module MUST NOT implicitly deregister a provider context owned by another module, and closing a Screen MUST NOT imply removal of the underlying GPU.

#### Startup discovery barrier

The server MUST establish the platform hotplug observation path before beginning the corresponding initial enumeration, so that add/remove events racing with enumeration are not lost. The implementation MUST reconcile the initial scan with queued events using source generations and observation ordering; it MUST NOT publish two incarnations or accept an old remove event against a newly observed incarnation.

Before XAverius exposes its initial PhysicalDevice inventory, each configured platform-discovery and provider-discovery adapter MUST report one of: initial pass complete, or initial pass unavailable/failed. The barrier waits only for these declared discovery participants. It MUST NOT wait for Screen creation, RandR initialization, a DDX ScreenAttachment, or a window to exist.

A failed or unavailable discovery participant is not evidence that a device was removed. Its candidates are simply unavailable for that pass; unresolved candidates remain unpublished. The server MUST NOT fabricate a provider binding, synthesize a partial snapshot, or publish a PhysicalDevice without the selected provider and complete snapshot required by Sections 2 and 3. A later successful discovery pass MAY publish a previously unresolved or unserved candidate through the ordinary canonicalize/select/snapshot/publish sequence.

An adapter registered after the initial barrier has closed MUST use the late-registration path. It MUST NOT reopen the barrier, reorder existing inventory, replace a selected provider, or mutate an already published snapshot. A newly discovered physical-device incarnation follows the same per-device publication sequence without blocking unrelated existing devices.

#### Xorg/DRM identity hand-off

A platform adapter SHOULD use the canonical kernel device relationship as the identity anchor. For DRM devices, primary and render nodes MUST be correlated using the underlying DRM device identity (for example, libdrm device information/equivalence and canonical sysfs ancestry), not by node basename, minor number, open-file-description identity, or which node a DDX happened to open first.

A DDX reporting a ScreenAttachment MUST resolve its DRM/platform device to the registry's canonical PhysicalDevice reference using structured identity evidence. If it has only a Screen number, Entity index, driver-private pointer, or DRM node pathname without a verified canonical relationship, the attachment MUST remain unresolved; it MUST NOT create a new PhysicalDevice or attach to an arbitrary matching vendor/device ID. A Screen may report multiple attachments, including distinct render-access and scanout/display-control roles. The same PhysicalDevice may be attached to multiple Screens.

The platform adapter's source key and source generation identify the adapter instance and its observation stream, not the device. A DDX Screen generation is separate from both. Recreating a Screen or reloading a DDX creates a new Screen/source generation as applicable; it does not create a new PhysicalDevice incarnation unless authoritative physical-removal evidence closed the previous incarnation.

#### Hotplug, Screen lifecycle, and teardown

The hotplug path MUST follow the same per-device order as startup: collect identity evidence; canonicalize or leave ambiguous; correlate provider-local bindings; select an eligible provider; obtain a complete snapshot; publish one server-owned XID; then allow DDX adapters to attach any live Screens. The implementation MAY perform these steps asynchronously, but no client-visible partial PhysicalDevice is permitted.

A kernel/udev remove event MUST first be correlated to the exact current source observation and PhysicalDevice incarnation. Loss of one DRM node, closing a DRM file descriptor, DDX unload, Screen close, or loss of display ownership MUST NOT alone be treated as physical removal. If the event proves only that one access path disappeared, withdraw that observation and recompute availability from remaining evidence. Only the validated authoritative removal operation may transition the PhysicalDevice to terminal REMOVED.

On Screen close or replacement, the DDX topology adapter MUST detach every ScreenAttachment for that exact Screen generation before releasing Screen-private data. Any asynchronous work referring to the Screen MUST retain a generation-checked reference and MUST be retired or cancelled before the Screen-private data is freed. A late callback or detach for the old generation MUST be ignored with a stale-generation result; it MUST NOT affect a replacement Screen that reuses an Xorg index or address.

On DDX module unload, the module MUST first stop new adapter callbacks, withdraw its own observations and ScreenAttachments, and retire its provider registrations independently. Module code and callback userdata MUST remain pinned until all callbacks, operation tokens, and retained references that can reach them have retired. If quiescence cannot be proven, the module/provider state MUST be quarantined rather than unloaded. This is in addition to, not a replacement for, the BackendProvider lifetime contract.


#### Screen-close and module-unload ownership boundary

The Xserver Screen lifecycle MUST be treated as a topology lifetime only. In the current XLibre implementation, GPU-screen removal calls the Screen close path, removes the GPU Screen, and then deletes its `ScrnInfo`; `xf86DeleteScreen()` invokes the DDX `FreeScreen()` hook, releases the Screen's module reference, and decrements the driver's Screen reference count. These operations do not establish that asynchronous work previously submitted by the DDX/provider has stopped executing.

Accordingly:

- `CloseScreen`, `FreeScreen`, `RemoveGPUScreen`, `xf86DeleteScreen`, or a zero `DriverPtr.refCount` MUST NOT be treated as proof of provider-operation completion, callback quiescence, or permission to release provider userdata.
- The DDX MUST detach the ScreenAttachment for the exact Screen generation before releasing Screen-private data. The ScreenAttachment MUST NOT own the provider context or provider module lease.
- A Screen close MUST NOT unregister a shared BackendProvider merely because the provider was first discovered or opened through that Screen. Provider registration lifetime is independent of every ScreenAttachment lifetime. If a provider truly has per-Screen backend state, that state MUST be a separately retained child of the provider context and MUST retire only after its own Screen-generation work is quiescent.
- A DDX module that supplies provider operation functions, completion callback functions, callback trampolines, or callback userdata MUST acquire a provider/module lease independent of Xorg's Screen-held module reference and driver Screen reference count. The lease MUST cover every function pointer and data object that can be reached by an accepted operation or a callback, including deferred cleanup and retirement paths.

- No asynchronous provider operation, worker, or callback may retain or later dereference a raw `ScreenPtr`, `ScrnInfoPtr`, `pScreen`, `pScrn`, or pointer into storage owned by `FreeScreen()`. Before crossing an asynchronous boundary, the DDX MUST copy the required immutable values or create a separately reference-counted ScreenAttachment context that contains no borrowed Xserver Screen/`ScrnInfo` pointers. Closing the Screen marks that context detached and prevents new Screen-facing work; the detached context may remain alive solely for callback bookkeeping until its own references retire. A callback after `CloseScreen` may complete backend cleanup using that detached context, but MUST NOT call Screen hooks, access RandR objects, or re-enter the deleted Screen.
- A provider callback that has entered module code MUST hold a callback-execution reference until it has returned to the server-owned completion sink. The sink MUST copy/enqueue the immutable completion before returning; the provider callback MUST NOT retain server-owned transient payload pointers after that return.

Provider/module shutdown is a two-phase operation, not an ordinary Screen cleanup:

1. **Close admission.** Atomically mark the exact provider generation as QUIESCING. Reject new operations and new provider bindings for that generation. Stop new discovery callbacks from that module and unregister its callback/event sources. This does not cancel accepted operations or release any existing reference.
2. **Withdraw topology and observations.** Detach every ScreenAttachment owned by the module for its exact Screen generations and withdraw its discovery observations. These operations do not imply physical removal and do not implicitly retire a provider owned by another module.
3. **Drain accepted work.** Obtain exactly one terminal outcome for every accepted provider-operation token. Then retire each exact token. A token is retired only when the provider confirms both that no backend access can remain and that the token's completion callback has returned; a queued server-side immutable completion record may still be processed because it no longer references provider code or callback userdata.
4. **Quiesce provider callbacks.** An explicit provider-wide quiescence operation (or equivalent contract) MUST confirm that no callback is executing, queued for invocation, or can begin for this provider generation, and that no new operation can be accepted. It MUST also confirm that every provider-owned worker/task capable of entering module code has stopped or no longer holds such a path. Merely observing zero outstanding tokens in the server is insufficient.
5. **Release provider and module.** Only after all selected PhysicalDevice, logical-Device, route, provider-object, callback-execution, and operation-token references have retired MAY the final provider reference be released and the module lease dropped. Xorg may then unload the DDX module through its ordinary module-reference mechanism.

The provider-wide `quiesce_provider` hook is mandatory for any provider whose code or callback path can be unloaded independently of server shutdown. It MUST be idempotent and generation-scoped. The first call closes provider-internal admission and callback dispatch; subsequent calls poll the same quiescence attempt. It MAY report PENDING while workers or callbacks are draining. SUCCESS has the strong meaning in step 4; FAILURE leaves the module pinned. The server MUST stop calling ordinary provider operations before invoking this hook. `release_provider` MUST NOT be the mechanism that initiates quiescence, because it is an infallible reference-count operation and MUST NOT block or invoke backend work. If a callback/worker cannot be stopped or its reachability cannot be disproved, the provider context, module lease, callback code, and userdata MUST be quarantined until server shutdown or a later proven-safe retirement. The server MUST NOT block Xorg's Screen close indefinitely waiting for GPU progress: Screen topology can be detached while the independent provider/module lease remains retained.

If one DDX module implements both the topology adapter and provider, it MUST still maintain these independent references. If the provider implementation is in a separate module/library, the DDX Screen may close and unload without affecting that provider, provided no callback path from the provider retains DDX Screen-private data. Any bridge callback crossing those module boundaries MUST retain both sides' exact-generation leases until the bridge callback has returned and its associated backend operation is retired.

#### XLibre lifecycle mapping (source-level observation)

At XLibre source commit `ee4bb3f96eec3b21c1961d54fe45cb33dc402d00`, `xf86platformRemoveDevice()` calls `dixScreenRaiseClose()`, then `RemoveGPUScreen()`, then `xf86DeleteScreen()`. `xf86DeleteScreen()` calls the DDX `FreeScreen()` hook before `UnloadModule(pScrn->module)` and decrementing `pScrn->drv->refCount`. This sequence is the Screen/DDX cleanup boundary; XAverius MUST complete ScreenAttachment detachment before Screen-private release, but provider/module quiescence is governed by the independent lease protocol above. Implementations MUST NOT assume that the Xorg module reference held by a particular `ScrnInfo` is sufficient for provider callbacks that outlive that Screen.


The loader implementation reinforces this separation. In the same source revision, `DuplicateModule()` copies the module handle into a per-`ScrnInfo` descriptor and marks that descriptor as duplicated; `UnloadModule()` skips `LoaderUnload()` for such duplicates. The original module descriptor eventually reaches `LoaderUnload()`, which calls `dlclose()`. The `DriverPtr.refCount` is a count of Xorg Screen/driver use, not a count of provider operations or callbacks. Therefore neither a duplicated `ModuleDesc` nor a positive/zero driver Screen reference count is a provider-lifetime pin. A DDX that exports provider callbacks MUST use a distinct loader/module pin whose acquisition and final release are tied to the provider reference/quiescence contract. The pin MUST remain effective even after the last `ScrnInfo` and GPU Screen have been deleted.

#### Xlibre-specific conformance requirements

An Xlibre/Xorg integration MUST demonstrate at least the following:

1. Two Screens initialized in either order produce the same canonical PhysicalDevice inventory and selected providers.
2. A single Screen attached to two GPUs creates two ScreenAttachments without duplicating either PhysicalDevice; two Screens using one GPU share one PhysicalDevice identity.
3. Primary and render DRM nodes for one device produce one PhysicalDevice; removing one node does not remove the device while authoritative evidence for the same incarnation remains.
4. A Screen close/recreate cycle changes only ScreenAttachment generations and cannot change PhysicalDevice identity, XID, provider selection, or published snapshot.
5. A DDX that only supplies topology cannot become the selected provider or publish a device; a DDX registered as a provider must satisfy the full provider contract.
6. A failed or late discovery adapter does not block already completed devices, fabricate removal, reopen the startup barrier, or mutate published records.
7. Hotplug add/remove events racing with initial enumeration cannot lose an event, resurrect a tombstone, or apply a stale removal to a replacement incarnation.
8. DDX unload with pending callbacks/operations cannot unload reachable callback code or release userdata before provider/operation retirement.

These requirements are server-integration conformance tests. They do not add wire requests, XIDs, properties, or status values.

## 3. BackendProvider contract

Provider selection MUST use the following v0.1 policy:

1. The server MAY configure an ordered provider-preference list using stable provider identifiers. A configured provider that is not discovered or cannot successfully query the candidate is skipped during initial selection.
2. If no explicit preference selects a usable provider, the server MUST select the usable provider with the lexicographically lowest canonical provider key. The key MUST be derived from stable provider identity/configuration (for example, canonical ICD manifest identity plus configured instance slot), never from pointer values, load order, discovery order, or transient handles. Provider keys MUST be unique within the server configuration; duplicate keys are a configuration error and MUST NOT be broken by registration order. A provider key MUST identify a provider implementation/configuration, not a PhysicalDevice or DRM access node.
3. The chosen provider is fixed before PhysicalDevice publication. The server MUST NOT publish a record and later change its selected provider because a higher-priority provider appeared.
4. The selected provider supplies the complete published metadata snapshot. A provider that cannot supply a complete, internally consistent snapshot is not eligible for selection.

The configuration syntax is implementation-specific; it MUST express an ordered list of stable provider identifiers and MUST NOT depend on DRM node numbers or Screen indices. An implementation MAY initially expose this as an Xorg `Option` or server command-line setting. With no explicit setting, the canonical-key ordering above is mandatory and reproducible.

An explicit preference list is evaluated by stable provider identifier, in configured order, after identity correlation has established the candidate bindings. A preference entry that matches multiple distinct provider instances is ambiguous and MUST be rejected as a configuration error rather than resolved by load order. Eligibility is evaluated before ranking: a provider MUST have an unambiguous binding to the candidate incarnation and MUST successfully return a complete, internally consistent snapshot. A preferred but ineligible provider is skipped only during initial selection; it does not cause a later provider to inherit or modify an already published PhysicalDevice.


A BackendProvider registration MUST include:

- provider type and stable configuration identity (for example, ICD/library identity plus server configuration slot);
- opaque provider context and operations for querying properties and creating/destroying logical Vulkan devices;
- the candidate PhysicalDevice identity evidence;
- provider-specific PhysicalDevice handle, valid only within that provider context;
- provider availability and a lifecycle generation;
- ownership hooks or references that keep provider code, loader dispatch, and context alive while dependent objects exist.

Provider handles and Vulkan dispatchable handles MUST remain private to the provider. Other providers, the registry, XAverius request handlers, and Screen attachments MUST NOT dereference them directly.

Each published PhysicalDevice has exactly one selected execution provider in v0.1. Selection MUST use an explicit server policy (configuration and stable provider identity/rank), not registration order, ICD enumeration order, Screen order, or pointer values. If several providers are discovered for one physical device, selection MUST occur after the discovery set for that startup pass is known. A server MAY retain non-selected providers as discovery/correlation providers, but MUST NOT use them as transparent execution failover in v0.1.

The selected provider supplies one coherent immutable published metadata snapshot: device properties, queue-family properties, memory properties, limits, and advertised XAverius properties. The registry MUST NOT synthesize a snapshot by mixing fields from different providers. A provider discovered after publication can be recorded as an alternate/correlation provider, but cannot alter that snapshot.

A selected provider becoming temporarily unavailable makes the PhysicalDevice UNAVAILABLE. It does not establish that the underlying hardware was removed. Recovery of the same provider for the same hardware incarnation MAY restore AVAILABLE if it can still honor the published snapshot. A confirmed physical-device removal transitions the PhysicalDevice to REMOVED, regardless of whether other providers still hold stale handles. A different provider MUST NOT transparently take over an existing published identity in v0.1.

Logical-device creation pins the exact selected provider and its PhysicalDevice incarnation. Every logical Device and asynchronous backend operation MUST retain a reference to the provider context and relevant internal generations until all backend accesses and callbacks have quiesced. Unloading a provider module or destroying its context while any such reference exists is forbidden. If quiescence cannot be proven, the backend objects and provider references MUST be retained or quarantined.


### 3.1 Provider, binding, and module multiplicity

Provider identity, provider-local device bindings, discovery observations, and module ownership are separate lifetimes. The following cardinalities and rules are normative:

- One BackendProvider generation MAY register bindings for many canonical PhysicalDevices. Each binding identifies exactly one PhysicalDevice incarnation and one provider-local physical-device instance.
- One PhysicalDevice MAY have bindings from multiple BackendProvider generations, including providers implemented by different DDX modules or ICDs. All such bindings MUST resolve to the same canonical PhysicalDevice identity before they can be associated with that record.
- For a given pair of (BackendProvider generation, PhysicalDevice incarnation), there MUST be at most one active executable binding. If one provider enumerates multiple Vulkan handles for the same canonical device through different Vulkan instances, it MUST correlate and deduplicate those aliases inside its provider context and choose one provider-local binding before registration. If it cannot prove that the handles are aliases of the same incarnation, it MUST keep the candidates unresolved rather than register competing bindings.
- A provider generation MAY be the selected execution provider for multiple PhysicalDevices. Its context-wide failure therefore affects every PhysicalDevice selected through that exact provider generation; a binding-scoped failure affects only the named binding. A failure of a non-selected provider or binding MUST NOT change the public status of the PhysicalDevice.
- A provider module MAY own multiple independent BackendProvider generations and may also implement discovery or DDX topology adapters. Each registration role MUST have its own generation, admission state, retained references, and teardown result. A shared module-owner lease MAY aggregate the loader pin for those roles, but it MUST NOT collapse their provider contexts, bindings, or lifecycle state into one provider.
- Every unloadable provider generation MUST retain a module lease covering its operation table, completion callback code, callback userdata, provider context, and every trampoline reachable from accepted work. Each independently registered provider generation acquires its own reference to the shared module-owner lease. A DDX topology/discovery adapter that can receive callbacks after Screen close MUST likewise retain a role-specific module lease until its callbacks and detached contexts have retired. Xorg ModuleDesc duplication and DriverPtr.refCount are not substitutes for these leases.


Provider registration is a distinct operation from provider-binding registration. The server assigns a fresh, nonzero provider generation before constructing the descriptor; the provider MUST NOT choose or reuse this value. The registry MUST create exactly one BackendProvider object for each registered provider generation, copy its stable provider key, retain its provider context, and retain its module lease exactly once for that provider generation. The descriptor's provider_generation is the server-assigned value returned unchanged in completion/token identity. Registering additional PhysicalDevice bindings MUST reference that existing provider object and MUST NOT repeat descriptor installation, acquire duplicate generation identity, or independently retain/release the module lease. A provider key identifies the provider implementation/configuration namespace; the provider generation distinguishes successive registrations and MUST never be reused while any stale reference or callback can exist.

A provider generation MUST be registered before any of its bindings or operations can be accepted. It MUST remain ACTIVE until BeginProviderShutdown serializes. The registry MUST reject duplicate active registration of the same provider generation and reject binding registration against an unknown, stale, QUIESCING, or QUIESCED provider generation. Binding registration is atomic: failure MUST leave no partial binding, observation ownership, or extra provider/module reference. A provider generation with zero bindings MAY remain registered during discovery or while it owns provider-scoped resources, but it MUST NOT be selected for a PhysicalDevice until an eligible binding and complete snapshot have been validated.

The module lease is a server-owned loader pin, not a provider callback and not a substitute for provider reference counting. The Xlibre/Xorg loader adapter creates one lease object for a loaded module-owner identity. The same lease object MAY be shared by several provider generations and adapter roles from that module. Each registered provider generation retains one lease reference; each independently registered adapter/callback role that can enter module code retains its own reference. The server-owned lease retain/release operations MUST be safe while the module is pinned and MUST NOT call into the module being pinned. A module-owner identity MUST resolve to one shared lease object for that loaded module instance; creating independent lease objects for aliases of the same unloadable handle is forbidden because it would split the final-unload count. A lease release MUST NOT unload the module while any lease reference remains. For a provider generation, the registry first performs its final provider-context release while the lease is still held, then releases that generation's lease reference as its final action; no provider function pointer or provider-owned userdata may be touched afterward.

TryQuiesceProvider is permitted only after shutdown admission is closed, all bindings owned by the provider generation have been removed from selection/publication, all accepted operation tokens have terminalized and retired, and all externally initiated provider calls and cross-module callback bridges have returned. Provider-internal workers are deliberately stopped and joined by the quiesce_provider hook itself; they MUST NOT be assumed stopped before that hook runs. It invokes the provider's quiesce_provider hook for that exact generation. PENDING leaves the generation and module lease pinned and may be retried; FAILURE places the generation in quarantine and MUST NOT release its module lease. A stale/unknown provider generation is returned as GPU_REGISTRY_STALE_GENERATION without invoking the hook; unmet server-side preconditions return GPU_REGISTRY_PENDING with out_quiescence set to PENDING; SUCCESS records provider-generation quiescence but does not by itself release the provider object or module lease while logical-device/provider-object references or adapter roles remain. Finalization is a separate step and is allowed only when the registry's provider reference count has reached its final registry-owned reference and all provider-owned objects have been destroyed or quarantined without requiring provider code. The finalization operation calls release_provider while the module lease remains held, then releases the module lease exactly once.


Discovery observations remain source-owned. Multiple DDX, platform, and provider sources MAY contribute independent observations for one canonical PhysicalDevice. The registry MUST retain each observation's exact source key, source generation, and observation ID. Withdrawing or replacing one source's observation MUST affect only that observation; it MUST NOT withdraw another source's evidence, another provider's binding, a ScreenAttachment owned by another DDX, or the PhysicalDevice identity while other valid evidence remains. A provider binding is not itself ownership of the canonical identity. Removing a provider binding MUST NOT implicitly remove the provider's discovery observation unless the same registration explicitly owns that exact observation and withdraws it through the source-observation operation.

Provider selection remains exactly one execution provider per published PhysicalDevice in v0.1. The selected provider supplies the complete immutable snapshot. Other providers MAY remain registered as discovery/correlation providers, but their metadata, queue capabilities, features, and properties MUST NOT be unioned with the selected snapshot. A provider registered after publication remains non-selected for that PhysicalDevice's lifetime. It MUST NOT become an implicit replacement when the selected provider is removed, unavailable, or quiescing. In particular, removing the selected binding makes that PhysicalDevice UNAVAILABLE under the existing status contract; the presence of another registered binding does not authorize failover, snapshot replacement, or XID replacement. Removing a non-selected binding has no public status effect.

Provider-generation shutdown and binding removal are distinct operations:

1. **Begin shutdown.** Atomically change the exact provider generation from ACTIVE to QUIESCING. Close admission for new operations and new bindings across that provider generation. This transition is idempotent for the same generation; a stale generation is rejected. A concurrent operation or registration is accepted only if its admission point serialized before this transition.
2. **Remove bindings.** Remove each binding owned by that provider generation using its exact PhysicalDevice, provider, and binding generations. Removing one binding MUST NOT remove any other binding or discovery observation. If the removed binding was selected, the PhysicalDevice becomes UNAVAILABLE and stays bound to that selected-provider identity; another provider is not promoted.
3. **Withdraw owned observations and topology.** Withdraw only discovery observations and ScreenAttachments owned by the unloading adapter/module and exact generations. Do not withdraw observations or attachments owned by another source/module merely because they refer to the same PhysicalDevice.
4. **Drain and quiesce.** Drain accepted operations, obtain exactly one terminal outcome for each token, retire each exact token, and invoke provider-wide quiescence for that provider generation as specified in Sections 2.4 and 4. A provider generation with several PhysicalDevice bindings is quiesced as one provider context; a binding-local loss is not a provider-wide shutdown.
5. **Release the provider lease.** Release that provider generation's module-lease reference only after its bindings, logical-device/provider-object references, callback executions, operation tokens, and provider context have retired. The shared module owner remains pinned while any other provider generation, adapter role, or callback bridge from that module retains a lease.

The lifecycle serializer MUST arbitrate competing Screen close, source withdrawal, provider-binding removal, provider-generation shutdown, provider quiescence, and physical-removal transitions by exact generations. Each operation is idempotent for its own generation and MUST NOT broaden its scope when another teardown has already started. A Screen close detaches only the exact ScreenAttachment. A source withdrawal removes only the exact observation. Provider shutdown closes only the exact provider generation. Physical removal terminalizes only the exact PhysicalDevice incarnation and does not itself unload providers. If physical removal wins before provider shutdown, the tombstone remains while provider references retire; if provider shutdown wins first, the PhysicalDevice follows the ordinary selected-provider UNAVAILABLE rule unless and until authoritative physical-removal evidence commits REMOVED. Neither ordering permits resurrection, provider promotion, or mutation of a replacement generation.

Quiescence is scoped. quiesce_provider SUCCESS proves that no callback, worker, or operation belonging to that exact provider generation can enter its module code again; it does not prove that another provider generation from the same module is quiescent. The module may be unloaded only after every provider and adapter role backed by that module has independently stopped admission, drained its accepted work/callbacks, and released its lease. A module-global callback or worker that can enter more than one provider generation MUST be accounted for by every affected role and MUST keep the common module lease pinned until it is no longer reachable. Quiescing one provider MUST NOT release the module pin while another provider generation or adapter role remains live.

## 4. Provider operation interface

The provider interface is a server-internal contract. It is not a Vulkan ABI, a client ABI, or a requirement to expose raw Vulkan entry points to XAverius request handlers. The server owns protocol validation, resource/XID ownership, request ordering, error precedence, and public state transitions. The provider owns the actual backend calls and every provider-local handle. Request handlers MUST call the selected provider only through the operation interface bound to the exact PhysicalDevice and logical-Device generations.

### 4.1 Operation groups

A selected provider MUST implement the following operation groups for every capability it advertises. An operation that is not applicable to the selected backend MAY be absent only when the corresponding XAverius capability is not advertised.

| Group | Required operations | Contract |
|---|---|---|
| Physical-device query | `enumerate_candidates`, `query_physical_snapshot` | Return one complete, immutable snapshot containing all fields used by enumeration, property queries, queue-family queries, memory-property queries, and device-limit validation. |
| Logical-device lifecycle | `create_logical_device`, `get_queue`, `destroy_logical_device` | Create the Vulkan logical device with the exact validated queues/features/extensions; obtain queues for the requested family/index; destroy the logical device after its dependent work is quiescent. |
| Buffer and memory | `create_buffer`, `get_buffer_memory_requirements`, `allocate_memory`, `free_memory`, `bind_buffer_memory`, `write_buffer`, `read_buffer` | Implement the Buffer/Memory semantics, alignment and range rules, upload/readback snapshot barriers, and transfer completion contracts in `memory-buffers.md`. |
| Shader, descriptor, and pipeline objects | create/destroy ShaderModule, DescriptorSetLayout, DescriptorPool, DescriptorSet, PipelineLayout, and ComputePipeline operations; descriptor updates | Implement the exact validated object descriptions and Vulkan dependency/lifetime ordering in `shaders-pipelines.md`. |
| Command recording | create/destroy/reset command pools and command buffers; begin/end recording; encode every v0.1 command opcode | Implement the validated command stream and command-buffer state machine in `command-recording.md`. The provider MUST NOT reinterpret or reorder XAverius request ordering. |
| Synchronization | create/destroy semaphores and fences; host timeline signal; queue signal/wait integration; fence reset and completion publication | Implement binary/timeline semaphore and fence behavior in `synchronization.md`, including the specified WAIT_ANY/WAIT_ALL and timeout semantics. |
| Queue execution | `queue_submit` and any backend completion/retirement operation | Submit the already validated dependency graph to the exact queue. Accepted submissions complete asynchronously and report one terminal outcome through the server's serialized completion path. |
| Presentation | provider-scoped surface create/destroy; exact Device/Surface route and queue-family support query; route create/retire; surface-format and present-mode query; swapchain create/destroy; image acquire; queue present | Implement the presentation profile only when enabled. The selected execution provider owns the route for its logical Device; it may implement a direct or explicitly bridged scanout path, but MUST NOT migrate execution to another PhysicalDevice/provider. ScreenAttachment MUST NOT substitute for the exact route query. |

Synchronization ownership is split deliberately: the provider implements Semaphore/Fence backend creation/destruction, host `SignalSemaphore` backend signaling, queue-side signal/wait dependencies, fence reset, and completion reporting. The server owns the observable Timeline counter and Fence state. `GetSemaphoreCounterValue`, `GetFenceStatus`, `WaitSemaphores`, and `WaitForFence` read/register against that server state; they MUST NOT issue a second provider counter query or blocking host wait. Successful queue/host signal and fence-completion results are published into server state through the serialized completion path before affected host-wait registrations are reevaluated.

### 4.1.1 Request ownership map

The following map closes the provider boundary against the complete request registry. "Server-owned" means the request is implemented from XAverius state/metadata and does not invoke a provider operation for that request itself; it does not mean that earlier backend operations are irrelevant to its state.

| Requests | Provider responsibility | Server responsibility |
|---|---|---|
| `QueryVersion` (0) | None | Protocol version/profile reply. |
| `EnumeratePhysicalDevices`, `GetPhysicalDeviceProperty`, `GetPhysicalDeviceQueueFamilyProperties`, `GetPhysicalDeviceMemoryProperties` (1–3, 7) | Discovery and pre-publication snapshot only | Registry enumeration and all post-publication replies from the immutable snapshot. |
| `CreateDevice`, `CreateDefaultDevice`, `DestroyDevice` (4–6) | Logical Device/Queue create, queue acquisition, backend teardown | Selection, validation, XID publication/invalidation, Device state, cascading resource invalidation. |
| `CreateBuffer`, `GetBufferMemoryRequirements`, `AllocateMemory`, `FreeMemory`, `BindBufferMemory`, `WriteBuffer`, `ReadBuffer` (8–14) | Buffer/Memory backend operations and transfer completion | Wire validation, memory/resource accounting, ordering barriers, reply/error and lifetime arbitration. |
| `ShaderModuleData`, Descriptor, Pipeline Layout, and Compute Pipeline requests (15–23) | Create/destroy ShaderModule, DescriptorSetLayout, DescriptorPool/Set, PipelineLayout, ComputePipeline; atomic descriptor updates | Chunk assembly/abort, XID/ownership/limit validation, descriptor reference graph and public state transitions. ShaderModuleData reaches the provider only when the validated final chunk commits module creation. |
| Command Pool/Buffer requests and `QueueSubmit` (24–28) | Command pool/buffer backend lifecycle, validated command encoding, queue submission and completion | Command stream framing/validation, command-buffer state machine, dependency graph, acceptance point, token/event delivery. |
| `CreateSemaphore`, `SignalSemaphore`, `DestroySemaphore`, `CreateFence`, `ResetFence`, `DestroyFence` (29, 32–34, 37–38) | Semaphore/Fence backend lifecycle, host timeline signal, queue-side synchronization integration, reset, completion reporting | XID/ownership/state validation, observable counters/states, synchronization reservations and retirement. |
| `GetSemaphoreCounterValue`, `WaitSemaphores`, `GetFenceStatus`, `WaitForFence` (30–31, 35–36) | No direct provider query/wait operation; provider completion callbacks update the state being observed | Server-owned state queries, wait predicates/registrations, timeout and terminal arbitration. |
| `DestroyResource` (39) | Typed backend destroy for the resource family | Type/ownership/lifetime validation, public XID invalidation, dependency invalidation and deferred retirement. |
| `SelectEvents` (40) | None | Connection/device/queue event-mask replacement and event routing. |
| Presentation requests (41–47) | Provider-scoped Surface; exact physical-device Surface support; Swapchain; acquire/cancel/late-image retirement; queue present | X11 Window identity, Surface/Swapchain XIDs, validation/status precedence, image/token/synchronization state, timeout and event arbitration. |

Command entries (`CMD_*`) are not request subopcodes. The server validates their wire encoding and state effects; the provider receives only the validated command representation for backend recording. Likewise, chunk transport for ShaderModuleData and CommandBufferData is server-owned; provider object creation/recording occurs only at the specified validated commit/finalization point. SelectEvents and QueryVersion are entirely server-side.

The names above describe semantic operations, not mandatory C symbol names. A provider MAY implement several rows through shared internal helpers, but it MUST preserve each operation's validation boundary, result classification, ordering, and lifetime semantics. All create operations MUST either return a complete provider object or fail without exposing a partially initialized object. If the backend partially creates objects before failure, the provider MUST roll them back or retain them privately until safe cleanup; the server MUST NOT publish the corresponding XAverius resource.

The provider descriptor MUST install a completion sink equivalent to `GpuProviderCompletionFn` plus an opaque server-owned userdata pointer before any asynchronous operation can be accepted. Each completion MUST carry the exact provider generation, operation generation, and non-reusable operation-token identity captured at submission. The server-side token record MUST retain the exact logical-Device generation (if any) and the complete resource-generation set. The provider MUST invoke the sink exactly once for each accepted operation token; it MUST NOT invoke it for an operation rejected synchronously. The completion payload MUST be self-contained and immutable; any variable payload storage MUST remain valid until the sink has copied it, and the sink MUST copy it before returning. The sink is enqueue-only and MUST NOT call back into provider operations synchronously. The callback identifies the token by its non-reusable `operation_token_id` plus `operation_generation`, never by a raw provider pointer or public XID. The provider interface MUST also expose lifecycle hooks equivalent to `retain_provider`, `release_provider`, `retain_device`, `release_device`, and a quiescence/retirement notification. Exact names are implementation-defined. A raw backend handle MUST never escape the provider boundary; the server stores opaque, generation-tagged provider object references.

### 4.2 Physical snapshot operation

`query_physical_snapshot` MUST run before publication and return a single internally consistent snapshot. The snapshot MUST include every value needed by all v0.1 physical-device enumeration and query requests and every device limit/capability used to validate later creation requests. It MUST be tied to the same provider-local physical-device handle that will be passed to `create_logical_device`.

The operation MUST distinguish an unsupported optional property from a transient query failure. A missing optional property is recorded as unavailable/not supported according to the property registry; it MUST NOT be fabricated. A failure to obtain a mandatory baseline property, queue-family data, memory properties, or a coherent limit set makes that provider ineligible for selection. The server MUST NOT publish a partial snapshot and MUST NOT fill missing fields from another provider.

After publication, request handlers MUST answer physical-device property and queue/memory-property queries from the stored snapshot. They MUST NOT re-query a different provider or silently refresh fields in place. Provider recovery MUST prove that the same provider and same physical-device incarnation still honor the published snapshot before restoring AVAILABLE.

### 4.3 Logical-device creation and queue binding

Before calling `create_logical_device`, the server MUST complete all XAverius wire, XID, ownership, queue, feature, extension, and physical-device-state validation in the normative order in `devices.md` and `errors.md`. The provider receives a fully validated immutable create description; it MUST NOT independently choose a different PhysicalDevice, queue family, queue count, feature set, or extension set.

The provider MUST create the logical device with the mandatory v0.1 `timelineSemaphore` feature enabled and exactly the validated queue requests and enabled optional features/extensions. It MUST return an opaque logical-device handle plus a queue handle for every requested (family,index) tuple, or fail atomically. Queue handles remain private to the provider and are reachable only through the logical-device context.

The server publishes the logical Device XID only after provider creation and all required queue acquisition succeed. If any stage fails, the server MUST destroy or quarantine every partial backend object, release temporary references when safe, leave the requested XID unallocated, and return the mapped error. The provider MUST NOT retain a live logical device after reporting a failed create unless it is explicitly quarantined and inaccessible to all later XAverius operations.

### 4.4 Provider result and error contract

Every provider operation MUST return a classified result. A provider MAY additionally retain the native backend/Vulkan result for diagnostics, but the native result MUST NOT bypass the classification or change the protocol mapping. At minimum, the internal result classes are:

| Provider result | Meaning | Required server treatment |
|---|---|---|
| `SUCCESS` | Operation completed successfully | Commit the request's specified success transition. |
| `STATUS` | A defined non-error operation outcome (for example out-of-date, surface-lost, suboptimal, or unsupported swapchain configuration) | Return the operation-specific status exactly as defined by its request chapter; do not convert it to a generic provider failure. |
| `UNSUPPORTED` | Operation/feature is genuinely unsupported by this provider | During initial capability discovery, omit the optional capability or reject provider selection. After publication, treat as a provider contract violation: fail the operation with `INTERNAL_SERVER_ERROR` and mark the provider unavailable pending diagnosis; do not silently alter the published snapshot. |
| `UNAVAILABLE` | Provider context or access to one specific physical-device binding is temporarily unavailable; no logical-Device-loss result has been established. The result MUST carry an explicit scope: `PROVIDER_CONTEXT` or `PHYSICAL_DEVICE`. | For `PROVIDER_CONTEXT`, mark every PhysicalDevice for which this exact provider generation is the selected execution provider UNAVAILABLE. For `PHYSICAL_DEVICE`, mark only the named PhysicalDevice binding UNAVAILABLE. Do not affect devices merely discovered by or attached to the provider as a non-selected/correlation provider. A request rejected before its protocol acceptance point uses its request-defined `DEVICE_UNAVAILABLE` error/reply status where defined. An already accepted asynchronous operation uses its operation-specific terminal channel (for example `EXECUTION_FAILED`, `TRANSFER_FAILED`, or `PRESENTATION_FAILED`), never a delayed X11 error. Existing logical Devices are not automatically declared lost solely by this result. |
| `DEVICE_LOST` | The backend has positively reported loss of this exact logical Vulkan Device (for example, `VK_ERROR_DEVICE_LOST`) | Commit the logical Device's DEVICE_LOST transition exactly once. Reply-pending requests use their request-defined final reply/status or X11 error; protocol-accepted operations use their defined terminal status/events. |
| `OUT_OF_HOST_MEMORY` / `OUT_OF_DEVICE_MEMORY` | Backend allocation failed for lack of host/device memory | Map to `ALLOCATION_FAILED` where the request contract exposes a synchronous allocation error; otherwise use that operation's specified asynchronous failure result. |
| `TRANSFER_FAILURE` | A buffer upload/readback or other defined transfer operation failed without Device Loss | Map to `TRANSFER_FAILED` for reply-bearing transfer requests such as WriteBuffer/ReadBuffer; operations whose protocol contract is event-terminal use their defined asynchronous failure path. |
| `EXECUTION_FAILURE` | Accepted GPU execution failed without a Device-Loss classification | Use the request-defined terminal channel: for example, QueueSubmit uses submission events and Fence state, while WaitForFence returns `EXECUTION_FAILED`. Never emit a delayed X11 error for an operation that has already crossed its protocol acceptance point. |
| `CANCELLED` | Operation was prevented from starting because its captured Device/resource generation was destroyed or terminalized | Complete it with the lifecycle result already committed by the server (for example `DEVICE_DESTROYED`); never invoke backend work after cancellation wins. |
| `FATAL` | Unclassified backend/provider failure or violated provider contract | Fail with `INTERNAL_SERVER_ERROR` if a synchronous request is still awaiting a result; mark the provider unavailable if its continued correctness cannot be trusted. Preserve all references until safe retirement. |

All provider operations that can fail, including backend destroy/retire operations, MUST return a classified `GpuProviderResult`. A destroy operation is best-effort with respect to an already committed public destroy: its failure MUST NOT resurrect an XID or create a delayed X11 error. The server retains/quarantines the backend object and provider context until safe retirement. The `retain_*`/`release_*` reference hooks are local lifetime primitives rather than backend operations; they MUST be infallible and MUST NOT invoke Vulkan or block. `retire_operation` MUST be idempotent, MUST return a classified result, and MUST release only the exact operation-token generation supplied to it. If retirement fails, the server MUST retain/quarantine the token and provider context rather than assuming quiescence.

`retire_operation` has one normative success meaning: `SUCCESS` confirms that the exact accepted operation token has no remaining or possible backend access, that the provider will perform no further access through that token, that the token's completion callback has returned from module code, that no further callback for that token can begin, and that the token's backend-side retirement is complete. Only this result authorizes the server to release the token's retained provider/device/resource references and retire the token record. Any non-`SUCCESS` result is not evidence of quiescence; the server MUST preserve the token record and quarantine all affected references. The server MAY retry retirement using the same exact token generation. Repeated retirement after `SUCCESS` MUST be an idempotent no-op returning `SUCCESS`; a stale token generation MUST NOT retire or release a newer token that reuses an internal slot. Retirement MUST NOT emit a second terminal outcome callback.

The abstract result type below carries this scope explicitly for both synchronous operation returns and asynchronous completion records. `PHYSICAL_DEVICE` results MUST identify the exact canonical PhysicalDevice and its generation in the operation's immutable result payload; `PROVIDER_CONTEXT` results MUST identify the exact provider generation. `NONE` is required for every result code other than `UNAVAILABLE`.

The scope of `UNAVAILABLE` is mandatory provider-result metadata, not something the registry may guess from the provider pointer. `PROVIDER_CONTEXT` means that the provider context/generation cannot safely serve any of its PhysicalDevice bindings; it affects only PhysicalDevices whose selected execution provider is that exact provider generation. `PHYSICAL_DEVICE` means that the provider context remains usable but the named provider-local PhysicalDevice binding cannot be used; it affects only that canonical PhysicalDevice. An observation for a non-selected provider MUST NOT change the published PhysicalDevice status. A provider-context recovery MAY restore each affected PhysicalDevice to AVAILABLE only if that same provider generation and exact physical-device incarnation again satisfy the published immutable snapshot. A physical-device-scoped recovery restores only that binding. Recovery MUST NOT revive REMOVED identities or switch provider selection.

The provider MUST NOT return X11 errors, XIDs, Atom errors, ownership errors, or request-validation errors. Those are server/protocol responsibilities and MUST be detected before invoking the provider. A provider MUST NOT map a malformed request to a Vulkan/backend error.

For `create_logical_device`, `DEVICE_LOST` occurs before a logical Device exists and therefore MUST NOT create a phantom logical Device or emit a Device-Loss event for the requested XID. The server MUST mark the selected PhysicalDevice UNAVAILABLE, fail creation with `DEVICE_UNAVAILABLE`, and leave the target XID unallocated. Allocation failures map to `ALLOCATION_FAILED`; other unclassified creation failures map to `INTERNAL_SERVER_ERROR`. A native unsupported-feature result after the server has validated the published snapshot is a provider contract violation, not a client `BadMatch`.

For operations on an already-created logical Device, a positive backend Device-Loss result applies to that exact logical Device. It MUST NOT automatically mark the PhysicalDevice REMOVED. Provider-context loss without proof that the logical Vulkan Device is lost instead makes the PhysicalDevice/provider unavailable; existing logical Devices remain pinned and their operations fail according to their own subsequent backend results or safe-abort rules. Provider unavailability alone does not automatically declare an existing logical Device lost. A request that needs the unavailable provider returns `DEVICE_UNAVAILABLE` while the provider remains unavailable; the logical Device retains its identity and may become usable again if the same provider recovers. An accepted asynchronous operation that can no longer make progress because of provider unavailability MUST terminalize through that operation's existing failure channel (for example, `EXECUTION_FAILED` for QueueSubmit or `TRANSFER_FAILED` for a buffer transfer), unless a positive loss result for that exact logical Device establishes `DEVICE_LOST`.

The server MUST preserve the first terminal outcome committed for each request, wait, submission, transfer, or resource operation. Later provider callbacks MUST NOT replace success, timeout, Device Loss, destruction, disconnect, or an earlier failure. A provider MUST NOT report success after it has reported a terminal failure for the same operation. For reply-pending requests, the winning provider outcome is translated through that request's reply/status/error contract. For protocol-accepted QueueSubmit and QueuePresent operations, the winning outcome is translated through their asynchronous event and synchronization/image-state contracts.

### 4.5 Synchronous and asynchronous operations

An operation is synchronous when the XAverius request can be completed from the provider's immediate result. Its provider call MUST either complete or return a classified result; it MUST NOT retain request-owned input pointers after return. The server MUST hold the relevant provider/device/resource references for the entire call.

An operation is deferred/asynchronous when its request remains pending while backend work or a wait registration progresses. This includes QueueSubmit, WriteBuffer, ReadBuffer, AcquireNextImage, and the deferred completion portion of QueuePresent. WaitSemaphores and WaitForFence are server-owned registrations over the server's published Timeline-counter/Fence state; they MUST NOT require a blocking provider wait operation or a provider operation token. For each provider-backed deferred operation, the provider MUST return either an immediate classified rejection/status or an accepted provider-operation token. Provider-token acceptance is an internal backend fact; it is NOT by itself XAverius protocol acceptance. For every accepted provider-operation token, the provider MUST eventually deliver exactly one terminal outcome notification to the server, including when backend execution or quiescence cannot be established. If the provider cannot establish a successful outcome, it MUST report a classified terminal failure through that one notification; it MUST NOT silently omit the callback or wait indefinitely. A terminal outcome notification does not by itself prove backend quiescence. If the provider cannot prove that no further backend access can occur, it MUST withhold the quiescence/retirement confirmation and the server MUST retain or quarantine all affected objects and provider references until backend access is impossible. Server-owned WaitSemaphores/WaitForFence registrations do not call the provider, do not create provider-operation tokens, and do not receive provider completion callbacks as registrations; they are reevaluated when the underlying queue/host-signal operation publishes updated server-visible synchronization state.

The protocol acceptance point is request-specific. QueueSubmit crosses it when the server accepts the void request; QueuePresent crosses it when the request returns SUCCESS. After either point, later execution/presentation failures use the defined events and synchronization/image state and MUST NOT become delayed X11 request errors. WriteBuffer, ReadBuffer, and AcquireNextImage remain reply-pending until their defined reply or error is committed; provider-token acceptance for these requests does not suppress the request chapter's final reply, normal status, or permitted X11 error. WaitSemaphores and WaitForFence are also reply-pending, but are entirely server-owned registrations and have no provider token. Disconnect suppresses delivery but does not bypass terminalization and safe retirement. Completion callbacks MUST carry immutable operation/provider generations and MUST resolve only through the server's internal operation-token record, never by public XID lookup.

Cancellation of a server-owned WaitSemaphores/WaitForFence registration is a server-side registration transition. It does not call the provider, cancel or retire the underlying QueueSubmit or host SignalSemaphore operation, or release references held by that underlying operation. Those references remain governed by the operation's own completion and quiescence contract. For `AcquireNextImage`, `cancel_acquire` requests cancellation of the exact provider-operation token generation; successful cancellation is not itself proof of quiescence and does not replace the one terminal completion/retirement notification. The provider MUST guarantee that no later backend access can occur before the server releases references. A cancellation result indicating that acquisition already completed does not alter the server's first-terminal-outcome rule.

`AcquireNextImage` timeout arbitration remains server-owned. The provider MUST NOT send a reply or independently commit the XAverius timeout result. If cancellation races a backend acquisition that has already acquired an image, the provider MUST return that image to a reusable swapchain state through a safe backend release mechanism, or retain/quarantine the affected swapchain and its provider resources until the acquired image can be safely retired. A presentation provider that cannot guarantee safe retirement of a late acquired image MUST NOT advertise the presentation profile. This requirement applies even when the public acquire registration has already timed out, been destroyed, or been cancelled by disconnect.

The server owns WaitSemaphores and WaitForFence registrations, predicates, deadlines, and timeout arbitration. Provider completion callbacks publish the successful Timeline-counter/Fence state changes that reevaluate those registrations; the provider MUST NOT implement a second competing host-wait registry or block waiting for those predicates. AcquireNextImage is different: it is a provider-backed WSI operation, but the server still owns its XAverius timeout deadline and arbitration. The provider MUST NOT return a final TIMEOUT status for the server-owned `AcquireNextImage` deadline. `WaitSemaphores` and `WaitForFence` have no provider-side wait operation or provider timeout. An AcquireNextImage provider operation may report STATUS/NOT_READY for a nonblocking poll that found no image, but only the server decides whether the XAverius result is NOT_READY (zero timeout) or TIMEOUT (finite deadline expiry). Backend OUT_OF_DATE and SURFACE_LOST remain provider-reported lifecycle statuses. The server's serialized domain decides whether completion, timeout, Device Loss, DestroyDevice, or disconnect wins. A provider acquire MUST NOT block the X11 request dispatcher.

Provider callbacks MAY run on arbitrary backend threads, but MUST only enqueue immutable completion records. They MUST NOT mutate XAverius state, release server resources directly, or write X11 events. The server's serialized event domain arbitrates the callback against Device Loss, DestroyDevice, disconnect, timeout, and other terminal events. Internal cleanup and public event delivery are separate: after public invalidation, callbacks may retire old internal state but MUST NOT emit events for the destroyed Device.

The server MUST retain a provider/context reference, the exact logical Device generation, all provider object references used by the operation, and any dependent resource references from before provider submission until callback retirement proves no backend access remains. A completion notification alone is sufficient to release these references only if the provider contract guarantees that the backend no longer accesses them when the callback is delivered.

### 4.6 Lifetime, pinning, and teardown

A selected provider is pinned by each published PhysicalDevice that names it. Each live logical Device takes an additional provider reference and pins the exact PhysicalDevice incarnation and provider generation used at creation. Each asynchronous operation takes its own references to the provider, logical Device, queue, and every resource/semaphore/fence/memory object the backend may access. A child resource MUST NOT outlive its owning logical Device publicly, but its internal provider object MAY remain retained after public invalidation.

Provider unload/context destruction is permitted only after all of the following are true:

1. No PhysicalDevice publication or registry callback can call into the provider.
2. No live logical Device references the provider.
3. Every provider call currently executing has returned.
4. Every accepted asynchronous operation has reached a terminal state and the provider has guaranteed no further access to its objects.
5. Every completion callback and deferred cleanup item carrying the provider generation has retired.
6. All provider-owned logical Devices, queues, resources, and loader/dispatch references have been destroyed or placed in a provider-owned quarantine that no longer requires executable provider code.

A provider MUST NOT wait indefinitely for a lost or wedged GPU as the only teardown strategy. It MAY retain/quarantine provider objects and the provider module/context until the server exits or a backend-specific safe retirement condition is met. If quiescence cannot be proven, leaking/quarantining is required over use-after-free, stale callback execution, or unloading code still reachable by a callback.

Destroying a logical Device first invalidates its public XIDs according to `devices.md` and `resource-lifetime.md`; backend destruction is deferred until dependent operations and Vulkan object dependencies permit it. The provider's `destroy_logical_device` operation is best-effort and MUST be safe after Device Loss. It MUST NOT turn successful public DestroyDevice into a protocol error, resurrect public resources, or emit new events. The provider and its dispatch/module references remain pinned until the destroy operation and all earlier backend accesses have safely retired.

Disconnect follows the same internal reference and quiescence rules as DestroyDevice, but does not send replies/events to the disconnected client. Physical-device removal prevents new logical-device creation; it does not authorize premature destruction of provider objects still referenced by existing logical Devices or operations.

## 5. ScreenAttachment contract

A ScreenAttachment is a non-owning, generation-checked relation between a live Screen and a PhysicalDevice. It MAY record roles such as rendering, scanout/display control, or backend discovery association. Implementations SHOULD distinguish at least render-access, scanout/display-control, and discovery-only roles when the information is available. These roles describe topology only; they are not capability bits and do not change the PhysicalDevice identity or its XAverius properties.

A ScreenAttachment MUST NOT:

- create, publish, or destroy a PhysicalDevice;
- choose the PhysicalDevice's selected Vulkan provider;
- imply that every window on the Screen can be presented by that device;
- imply that a compute-capable device is scanout-capable;
- imply that two devices attached to the same Screen can share resources;
- imply that a device attached to Screen 0 is preferred by CreateDefaultDevice.

Surface presentation support MUST continue to be evaluated for the exact logical Device/Surface pair by the presentation capability path. ScreenAttachment is discovery/topology information, not a substitute for a Vulkan surface-support query.

A provider surface object is scoped to the provider's Vulkan instance/context, not to one logical Device. A single XAverius Surface may therefore have separate provider-local surface objects when queried against Devices created by different providers. Such objects MUST be keyed by the exact provider generation and retained Window/Screen generation; they MUST NOT be shared across provider instances or treated as proof that another provider supports presentation. Creation MAY be lazy at the first exact Device/Surface capability query. DestroySurface retires every provider-local surface object for that Surface only after no swapchain or in-flight WSI operation can reference it. Each provider-local surface object pins its provider context until destruction is safe.

A ScreenAttachment MUST be detached when its exact Screen generation is destroyed or replaced. A late detach event from an old Screen generation MUST NOT detach a newer Screen that reuses the same numeric server-side index or pointer slot.

### 5.1 Presentation target routing and cross-GPU boundary

A presentation target is the exact retained Window identity and its owning Screen generation. The server MUST NOT infer a presentation target from the first Screen, a default Screen, a RandR output number, or the first ScreenAttachment found for a PhysicalDevice. RandR outputs/monitors are not XAverius presentation targets in v0.1; the target is the X11 Window as a whole.

ScreenAttachment roles MUST distinguish at least the following topology facts when known: render access, scanout/display control, and discovery-only association. These roles describe which server path observes or services a PhysicalDevice; they are not capability bits and MUST NOT be used as a substitute for an exact Device/Surface query. A Screen may have separate render and scanout PhysicalDevices, and either may be absent from the XAverius inventory if it has no eligible execution provider. The same PhysicalDevice may have different roles on different Screens.

The selected execution provider of the PhysicalDevice from which a logical Device was created remains the sole owner of that logical Device, its queues, and its swapchain-facing provider objects. A presentation route for a particular (logical Device, Surface) pair MUST be established through that selected provider. The route MAY be implemented as native WSI on the render PhysicalDevice, or as an explicit provider-managed bridge to the scanout/display path (for example, a PRIME/DRI3 import, copy, or composition path). Such a bridge is an implementation detail of the selected provider's presentation operation; it MUST NOT create a synthetic PhysicalDevice, change the logical Device's PhysicalDevice, combine metadata snapshots, transfer Vulkan handles between providers, or select another execution provider as a fallback.

If the render PhysicalDevice and the Screen's scanout PhysicalDevice differ, the provider MUST report presentation support only if it can establish and operate a complete route for the exact Window/Screen generation and the exact logical Device. The route must cover the advertised formats/color spaces, image usage, extent constraints, queue-family support, synchronization, image ownership/transfer, and completion/release guarantees. Merely finding a PRIME-capable DRM node, a scanout ScreenAttachment, a matching vendor/device ID, or another GPU on the same Screen is insufficient. A route that requires unsupported cross-device import/export or synchronization MUST be reported as unsupported.

The provider's `query_surface_support` and capability operations MUST evaluate the actual route for every queue family. `present_supported = 1` means that the selected provider can accept presentation from that queue family through the exact route and meet the full presentation lifetime contract. If no such route exists, the query returns a successful capability result with no present-capable queue family, and swapchain creation fails with `UNSUPPORTED_CONFIGURATION`; it MUST NOT silently migrate the logical Device to the scanout GPU or another Screen.

A successful `CreateSwapchain` binds the Swapchain to the exact presentation route generation selected for that Device/Surface pair. All images and accepted presentation operations for that Swapchain use that route. The route and its backend references remain pinned until the Swapchain and all in-flight presentation operations have safely retired. A later topology, bridge, or route-generation change MUST NOT silently reroute an existing Swapchain. It makes that Swapchain `OUT_OF_DATE` for new acquire/present operations; the client must query again and create a replacement Swapchain. A stale route callback MUST be rejected by its captured route, provider, Surface, Screen, and Swapchain generations.

The selected provider is the route coordinator and MUST retain a non-reusable route generation plus references to the exact target Screen, scanout binding, and any bridge resources. A server-side DDX/display adapter MAY participate through an explicit private bridge interface (for example, import/export of an OS shared-resource handle and a defined synchronization handoff); it MUST NOT receive or dereference another provider's Vulkan dispatchable handles. Any cross-device resource transfer MUST have explicit importability, format/modifier, ownership, cache-coherency, and completion guarantees. If those guarantees cannot be established, the route is unsupported. The route coordinator remains responsible for ensuring that QueuePresent acceptance and terminal/image-release milestones cover the complete bridge path, not merely completion of the render-GPU copy submission.

A route that is temporarily unavailable is reported for the exact Device/Surface pair as `DEVICE_UNAVAILABLE`; this status does not by itself transition the render PhysicalDevice or logical Device to UNAVAILABLE/DEVICE_LOST. A route that is permanently unsupported returns `SUCCESS` with no present-capable queue from GetSurfaceCapabilities and `UNSUPPORTED_CONFIGURATION` from CreateSwapchain. If a pinned route generation changes, the associated live Swapchain becomes `OUT_OF_DATE`. If a route operation fails after QueuePresent acceptance without a more specific lifecycle cause, the accepted presentation terminates as `PRESENTATION_FAILED`. These mappings do not weaken the independent provider-context and exact logical-Device loss rules.

A route may be direct even when the ScreenAttachment topology names a different scanout GPU, provided the selected provider proves a valid backend path. Conversely, a ScreenAttachment naming the same PhysicalDevice as the logical Device does not guarantee native WSI support. Compute availability and PhysicalDevice status remain independent of presentation-route availability: loss of a display/bridge path MUST NOT by itself mark the render PhysicalDevice `REMOVED` or the logical Device `DEVICE_LOST`. A route failure is reported through the presentation operation's defined status/error contract and invalidates only the affected Surface/Swapchain route state unless the provider separately reports an exact logical-Device loss or PhysicalDevice/provider unavailability.



## 6. Lifecycle and event serialization

All registry mutations that can affect PhysicalDevice status, publication, provider selection, ScreenAttachment membership, or XAverius events MUST be serialized through the X server's main/event thread or an equivalent server-owned serialization domain. Backend worker threads MAY detect conditions, but MUST enqueue immutable observations to that domain; they MUST NOT mutate registry objects or send X11 events directly.

The registry/presentation subsystem distinguishes at least these operations:

- register a provider observation for a candidate;
- mark a provider unavailable or recovered;
- confirm physical-device removal;
- attach or detach a Screen generation;
- create, pin, invalidate, or retire a PresentationRoute generation;
- publish a canonical PhysicalDevice to XAverius;
- retire provider and route references after backend quiescence.

Provider loss and physical-device removal are different events. A lost ICD context, failed Vulkan instance, or provider unload MUST NOT by itself mark hardware REMOVED. Conversely, a confirmed kernel/device removal MUST NOT be suppressed merely because an alternate provider still has a stale Vulkan handle.

The existing PhysicalDevice status state machine remains authoritative: AVAILABLE and UNAVAILABLE may recover between each other; either may transition to terminal REMOVED. REMOVED records remain tombstones until server shutdown. Registry state transitions and the corresponding `XAverius.deviceStatus` value/event MUST have one serialization point.

The registry/presentation subsystem MUST use generation-checked internal references for PhysicalDevice, BackendProvider, ScreenAttachment, PresentationRoute, Surface, and Swapchain lifetimes. Numeric XIDs, DRM node numbers, array indices, and raw pointers without a lifetime generation MUST NOT be used to resolve delayed callbacks. A callback captured for an old provider/device/screen generation MUST NOT mutate a replacement object that reuses an address, index, node number, or public XID.

## 7. Suggested internal API boundary

The following is an abstract C interface sketch, not a public ABI and not a wire definition. Names and exact types MAY be adapted to Xserver conventions, but the ownership and semantic boundaries MUST be preserved.

```c
typedef struct GpuRegistry GpuRegistry;
typedef struct GpuPhysicalDevice GpuPhysicalDevice;
typedef struct GpuBackendProvider GpuBackendProvider;
typedef struct GpuProviderModuleLease GpuProviderModuleLease;
/* Server-owned loader pin shared by all roles in one loaded module.
   Create binds it to the Xserver loader's module-owner reference; retain and
   release never call code in the pinned module. */
GpuProviderModuleLease *GpuProviderModuleLeaseCreate(void *module_owner);
void GpuProviderModuleLeaseRetain(GpuProviderModuleLease *lease);
void GpuProviderModuleLeaseRelease(GpuProviderModuleLease *lease);
typedef struct GpuScreenAttachment GpuScreenAttachment;
typedef struct GpuProviderPresentationRoute GpuProviderPresentationRoute;

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
    GPU_REGISTRY_INTERNAL_ERROR
} GpuRegistryResult;

enum {
    GPU_SCREEN_ROLE_RENDER_ACCESS = 1u << 0,
    GPU_SCREEN_ROLE_SCANOUT = 1u << 1,
    GPU_SCREEN_ROLE_DISPLAY_CONTROL = 1u << 2,
    GPU_SCREEN_ROLE_DISCOVERY_ONLY = 1u << 3
};

typedef struct {
    /* Structured bus/sysfs/DRM identity, optional valid deviceUUID,
       virtual-instance discriminator, and incarnation evidence. */
} GpuDeviceIdentity;

typedef struct {
    /* Provenance of the authoritative removal observation. source_key is
       borrowed for this call only; the registry resolves it to its registered
       source identity before returning. The evidence must identify the exact
       source observation and PhysicalDevice incarnation. */
    const char *source_key;
    uint64_t source_generation;
    uint64_t observation_id;
    uint64_t physical_device_generation;
    uint32_t authority; /* private registry-defined evidence class */
} GpuDeviceRemovalEvidence;

typedef struct {
    uint64_t route_generation;
    uint64_t screen_generation;
    uint64_t scanout_device_generation; /* zero when no separate scanout device is used */
    uint32_t route_kind; /* direct WSI or provider-managed bridge; private enum */
} GpuProviderPresentationRouteInfo;

/* Classified provider result. Native VkResult may be retained for diagnostics. */
typedef enum {
    GPU_PROVIDER_SUCCESS,
    GPU_PROVIDER_UNSUPPORTED,
    GPU_PROVIDER_STATUS,
    GPU_PROVIDER_UNAVAILABLE,
    GPU_PROVIDER_DEVICE_LOST,
    GPU_PROVIDER_OUT_OF_HOST_MEMORY,
    GPU_PROVIDER_OUT_OF_DEVICE_MEMORY,
    GPU_PROVIDER_TRANSFER_FAILURE,
    GPU_PROVIDER_EXECUTION_FAILURE,
    GPU_PROVIDER_CANCELLED,
    GPU_PROVIDER_FATAL
} GpuProviderResultCode;

typedef enum {
    GPU_PROVIDER_UNAVAILABLE_SCOPE_NONE = 0,
    GPU_PROVIDER_UNAVAILABLE_SCOPE_PROVIDER_CONTEXT = 1,
    GPU_PROVIDER_UNAVAILABLE_SCOPE_PHYSICAL_DEVICE = 2
} GpuProviderUnavailableScope;

typedef struct {
    GpuProviderResultCode code;
    /* MUST be NONE except when code is UNAVAILABLE. */
    GpuProviderUnavailableScope unavailable_scope;
    /* Required for PHYSICAL_DEVICE scope; identifies the exact provider-local
       binding within this provider generation. Zero for other scopes. */
    uint64_t physical_device_binding_id;
    uint64_t physical_device_generation;
} GpuProviderResult;

typedef struct {
    uint64_t provider_generation;
    uint64_t operation_generation;
    uint64_t operation_token_id;
    GpuProviderResult result;
    /* Required for PHYSICAL_DEVICE scope: exact canonical PhysicalDevice
       reference and generation corresponding to result's binding identity.
       Operation-specific immutable result payload follows. */
} GpuProviderCompletion;

typedef void (*GpuProviderCompletionFn)(
    void *completion_userdata,
    const GpuProviderCompletion *completion);

typedef enum {
    GPU_PROVIDER_QUIESCENCE_PENDING,
    GPU_PROVIDER_QUIESCENCE_SUCCESS,
    GPU_PROVIDER_QUIESCENCE_FAILURE
} GpuProviderQuiescenceResult;

typedef struct GpuProviderOps {
    GpuProviderResult (*enumerate_candidates)(
        GpuBackendProvider *, GpuPhysicalDeviceCandidateList *);
    GpuProviderResult (*query_physical_snapshot)(
        GpuBackendProvider *, GpuPhysicalDeviceCandidate *,
        GpuPhysicalDeviceSnapshot *);

    GpuProviderResult (*create_logical_device)(
        GpuBackendProvider *, const GpuDeviceCreateInfo *,
        GpuProviderDevice **);
    GpuProviderResult (*get_queue)(
        GpuProviderDevice *, uint32_t family, uint32_t index,
        GpuProviderQueue **);
    GpuProviderResult (*destroy_logical_device)(GpuProviderDevice *);

    /* Separate typed operation tables, not a generic wire-payload dispatcher:
       buffer_memory: create/query/allocate/free/bind/read/write Buffer and Memory;
       shader_pipeline: Shader, Descriptor, Pipeline create/update/destroy;
       commands: CommandPool/CommandBuffer lifecycle and command recording;
       synchronization: Semaphore/Fence lifecycle, host timeline signal,
       queue signal/wait integration, fence reset, and completion publication.
       Each table implements the corresponding operations listed in Section 4.1. */
    const GpuProviderBufferMemoryOps *buffer_memory;
    const GpuProviderShaderPipelineOps *shader_pipeline;
    const GpuProviderCommandOps *commands;
    const GpuProviderSynchronizationOps *synchronization;

    GpuProviderResult (*queue_submit)(
        GpuProviderQueue *, const GpuProviderSubmitInfo *,
        GpuProviderOperationToken *);
    GpuProviderResult (*create_surface)(
        GpuBackendProvider *, const GpuProviderSurfaceInfo *,
        GpuProviderSurface **);
    GpuProviderResult (*destroy_surface)(GpuBackendProvider *, GpuProviderSurface *);
    GpuProviderResult (*query_surface_support)(
        GpuBackendProvider *, GpuProviderPhysicalDevice *,
        uint32_t queue_family, GpuProviderSurface *,
        GpuProviderSurfaceSupport *);
    /* Create/release an exact route for this logical Device generation and
       Surface/Window/Screen generation after physical-device capability
       probing. The route MUST be distinct per logical Device, even when two
       Devices share one PhysicalDevice and Surface. create_swapchain pins
       this route until swapchain retirement. */
    GpuProviderResult (*create_presentation_route)(
        GpuProviderDevice *, GpuProviderSurface *,
        GpuProviderPresentationRoute **,
        GpuProviderPresentationRouteInfo *);
    GpuProviderResult (*destroy_presentation_route)(
        GpuBackendProvider *, GpuProviderPresentationRoute *);
    GpuProviderResult (*create_swapchain)(
        GpuProviderDevice *, GpuProviderSurface *,
        GpuProviderPresentationRoute *,
        const GpuProviderSwapchainInfo *, GpuProviderSwapchain **);
    GpuProviderResult (*destroy_swapchain)(GpuProviderSwapchain *);
    GpuProviderResult (*acquire_next_image)(
        GpuProviderDevice *, GpuProviderSwapchain *,
        const GpuProviderAcquireInfo *, GpuProviderOperationToken *);
    GpuProviderResult (*queue_present)(
        GpuProviderQueue *, const GpuProviderPresentInfo *,
        GpuProviderOperationToken *);
    GpuProviderResult (*cancel_acquire)(GpuProviderOperationToken *);
    GpuProviderResult (*release_late_acquired_image)(
        GpuProviderSwapchain *, uint32_t image_index);

    /* Completion sink is installed when the provider context is created.
       Provider callbacks invoke it only to enqueue immutable records. */
    void (*retain_provider)(GpuBackendProvider *);
    void (*release_provider)(GpuBackendProvider *);
    void (*retain_device)(GpuProviderDevice *);
    void (*release_device)(GpuProviderDevice *);
    GpuProviderResult (*retire_operation)(GpuProviderOperationToken *);
    /* Idempotently stop provider-internal workers/callback dispatch for this
       generation. PENDING keeps every module/context reference pinned;
       SUCCESS proves no callback is executing or can begin and no worker can
       enter provider module code again. */
    GpuProviderQuiescenceResult (*quiesce_provider)(GpuBackendProvider *);
} GpuProviderOps;

typedef struct {
    /* Stable provider identity/configuration, opaque provider context,
       provider-local physical-device handle, and operation table. */
    const char *canonical_provider_key;
    void *provider_context;
    GpuProviderModuleLease *module_lease; /* required for unloadable provider code */
    const GpuProviderOps *ops;
    GpuProviderCompletionFn completion_sink;
    void *completion_userdata;
    uint64_t provider_generation;
} GpuProviderDescriptor;

/* Descriptor and callback lifetime contract:
   - RegisterProvider installs this descriptor exactly once for the exact
     provider generation. RegisterProviderBinding refers to the resulting
     GpuBackendProvider and MUST NOT reinstall or recopy this descriptor.
   - canonical_provider_key is borrowed for registration only; the registry
     copies its canonical bytes before returning.
   - module_lease is retained once for this provider generation and remains
     effective until that generation's final provider reference is released
     after successful quiescence; it may be shared by other provider/adapter
     registrations from the same loaded module.
   - ops, completion_sink, and completion_userdata remain valid and immutable
     for this provider generation until release_provider has been called for
     the final retained reference and all operation tokens are retired.
   - provider_context is managed only through the provider retain/release
     contract; the registry MUST NOT retain an unowned raw context pointer.
   - All other pointer arguments to registry entry points are borrowed for the
     duration of that call unless a specific operation explicitly transfers
     ownership. Any data retained after return MUST be copied or separately
     reference-counted before the call returns. */

/* Server startup/shutdown; one registry per X server process. */
GpuRegistry *GpuRegistryCreate(void);
void GpuRegistryDestroy(GpuRegistry *registry);

/* Discovery-source observation. Returns a canonical, generation-checked
   record only when identity matching is unambiguous; pending/ambiguous
   candidates remain unpublished and receive no protocol XID. */
GpuRegistryResult GpuRegistryObserveDevice(
    GpuRegistry *registry, const char *source_key,
    uint64_t source_generation, const GpuDeviceIdentity *identity,
    GpuPhysicalDevice **out_device, uint64_t *out_device_generation,
    uint64_t *out_observation_id);

/* Provider execution binding is registered separately from observation.
   The provider-local handle remains private to this provider generation. */
GpuRegistryResult GpuRegistryRegisterProvider(
    GpuRegistry *registry, const GpuProviderDescriptor *descriptor,
    GpuBackendProvider **out_provider);

GpuRegistryResult GpuRegistryRegisterProviderBinding(
    GpuRegistry *registry, GpuPhysicalDevice *device,
    uint64_t device_generation, GpuBackendProvider *provider,
    uint64_t provider_generation, uint64_t provider_local_binding_id,
    uint64_t binding_generation);

/* Close admission for this exact provider generation. This does not
   remove bindings, retire accepted operations, or prove quiescence. */
GpuRegistryResult GpuRegistryBeginProviderShutdown(
    GpuRegistry *registry, GpuBackendProvider *provider,
    uint64_t provider_generation);

/* Drives provider-wide quiescence after the registry has verified the
   shutdown/drain preconditions. PENDING/FAILURE retain the module lease. */
GpuRegistryResult GpuRegistryTryQuiesceProvider(
    GpuRegistry *registry, GpuBackendProvider *provider,
    uint64_t provider_generation,
    GpuProviderQuiescenceResult *out_quiescence);

/* Final provider-context release followed by exactly one module-lease
   release. Returns PENDING until all non-registry provider references retire. */
GpuRegistryResult GpuRegistryFinalizeProviderShutdown(
    GpuRegistry *registry, GpuBackendProvider *provider,
    uint64_t provider_generation);

GpuRegistryResult GpuRegistryRemoveProviderBinding(
    GpuRegistry *registry, GpuPhysicalDevice *device,
    uint64_t device_generation, GpuBackendProvider *provider,
    uint64_t provider_generation, uint64_t binding_generation);

GpuRegistryResult GpuRegistryRemoveObservation(
    GpuRegistry *registry, const char *source_key,
    uint64_t source_generation, uint64_t observation_id);

/* Provider availability is distinct from physical removal. All state-
   changing calls return a classified result; stale generations and unknown
   bindings are observable rejections, never silent no-ops.
   Context-wide failure/recovery affects all PhysicalDevices for which this
   exact provider generation is the selected execution provider. */
GpuRegistryResult GpuRegistryProviderContextUnavailable(
    GpuRegistry *registry, GpuBackendProvider *provider,
    uint64_t provider_generation);
GpuRegistryResult GpuRegistryProviderContextRecovered(
    GpuRegistry *registry, GpuBackendProvider *provider,
    uint64_t provider_generation);

/* Device-scoped failure/recovery affects only this canonical binding. */
GpuRegistryResult GpuRegistryProviderDeviceUnavailable(
    GpuRegistry *registry, GpuBackendProvider *provider,
    uint64_t provider_generation, GpuPhysicalDevice *device,
    uint64_t device_generation);
GpuRegistryResult GpuRegistryProviderDeviceRecovered(
    GpuRegistry *registry, GpuBackendProvider *provider,
    uint64_t provider_generation, GpuPhysicalDevice *device,
    uint64_t device_generation);
GpuRegistryResult GpuRegistryConfirmDeviceRemoved(
    GpuRegistry *registry, GpuPhysicalDevice *device,
    uint64_t device_generation,
    const GpuDeviceRemovalEvidence *removal_evidence);

/* Screen relationships are non-owning and generation checked. Roles use
   GPU_SCREEN_ROLE_*; they describe topology, not presentation capability. */
GpuScreenAttachment *GpuRegistryAttachScreen(
    GpuRegistry *registry, GpuPhysicalDevice *device,
    ScreenPtr screen, uint64_t screen_generation, unsigned int roles);
void GpuRegistryDetachScreen(
    GpuRegistry *registry, GpuScreenAttachment *attachment,
    uint64_t attachment_generation);

/* XAverius publishes and maps canonical records to server-owned XIDs. */
void XaPhysicalDevicePublish(GpuPhysicalDevice *device);
XID XaPhysicalDeviceXid(const GpuPhysicalDevice *device);

/* A route is scoped to the exact Device/Surface/Window/Screen generations.
   A successful Swapchain pins it until all presentation and image-release
   milestones have retired; stale route callbacks are generation-rejected. */

/* Logical-device creation pins the selected provider and generations. */
GpuBackendProvider *GpuPhysicalDeviceAcquireExecutionProvider(
    GpuPhysicalDevice *device);
void GpuBackendProviderRelease(GpuBackendProvider *provider);
```

The API MUST NOT expose a public function such as `RegisterPhysicalDeviceWithXid()` to DDX drivers. XID allocation and protocol resource publication belong exclusively to the XAverius/server resource layer. A provider registration may return an existing canonical record or create an unpublished candidate; it MUST NOT publish a duplicate identity.

The registration API SHOULD be split into candidate discovery and provider attachment internally if that is needed to finish startup-wide provider selection before publication. The simplified sketch above does not permit immediate publication during arbitrary driver probe order.

## 8. Xlibre/Xorg integration guidance

For the current XAverius scope, the recommended ownership location is the XAverius server subsystem itself (for example, `Xext/xaverius/registry.c`), with a private server-internal interface declared in an exported header such as `include/xaverius_registry.h`. This keeps Vulkan-specific identity, provider selection, metadata snapshots, and XAverius XID publication together without making generic DIX depend on Vulkan or DRM. The interface is an internal server/module interface, not a stable client ABI or a promise of compatibility for independently built third-party modules.


The existing Xorg platform-device list (`xf86_platform_devices` in `hw/xfree86/common/xf86platformBus.c`) and udev DRM discovery (`config/udev.c`) are useful discovery inputs, not the canonical XAverius registry. The platform list is organized around device-node attributes and Xorg ownership/claiming; the current DRM udev path filters `card*` nodes and deduplicates those observations by major/minor. These are appropriate for Xorg device management but do not represent identity across DRM primary/render nodes, multiple Vulkan instances/ICDs, or hotplug generations.

Recommended layering:

- Xorg platform/udev code reports identity and authoritative hotplug observations to the registry.
- DDX drivers report Screen-to-device relationships as ScreenAttachments; they register a BackendProvider only if they implement its complete Vulkan/backend operation contract.
- Vulkan ICD/provider adapters register provider-local execution bindings separately from hardware observations.
- The server-wide registry canonicalizes candidates, selects the execution provider, and owns PhysicalDevice records.
- XAverius enumerates only published registry records and owns their protocol XID resources.
- Screen initialization creates/destroys ScreenAttachments only; detaching a Screen does not remove a still-discovered device.
- Surface/WSI code performs the actual Device/Surface presentation-support query; it must not infer support from a ScreenAttachment.

### 8.1 Practical mapping to the current XLibre Xserver tree (non-normative)

The following mapping was checked against X11Libre/xserver commit `ee4bb3f96eec3b21c1961d54fe45cb33dc402d00`. It is an integration guide, not a promise that these private interfaces remain stable across XLibre revisions.

- `InitOutput()` in `hw/xfree86/common/xf86Init.c` calls `xf86BusProbe()` before `xf86ExtensionInit()`, driver-module loading, `xf86BusConfig()`, and DDX `PreInit()`. This means a registry/hotplug bootstrap that must observe the initial platform scan cannot be deferred solely to the normal XAverius extension setup. The integration SHOULD split early registry/event-source bootstrap from later protocol-extension registration.
- `xf86BusProbe()` in `hw/xfree86/common/xf86Bus.c` calls `xf86platformProbe()`. The latter calls `config_odev_probe(xf86PlatformDeviceProbe)` and populates `xf86_platform_devices`. This is a useful place to feed platform observations into the registry, or to snapshot the completed platform list immediately after the probe. The platform list remains an Xorg discovery/ownership structure, not the canonical XAverius inventory.
- `config_udev_odev_probe()` in `config/udev.c` enumerates DRM subsystem nodes matching `card[0-9]*`; the event path similarly filters for `card*` and checks existing entries by major/minor. Therefore this path MUST NOT be treated as a complete primary-plus-render-node identity source. XAverius discovery must independently obtain or correlate render-node evidence (for example through libdrm/sysfs) and must use the underlying DRM device relationship rather than major/minor as identity.
- DDX provider bindings, when a DDX genuinely implements the BackendProvider contract, can be registered during its driver probe/PreInit phase before the X11 Screen object is created. ScreenAttachments are later created only after the corresponding Screen generation exists. A DDX that does not implement the full provider contract contributes topology only.
- `xf86platformAddDevice()` performs a GPU-screen probe/PreInit, creates a GPU Screen, attaches it to a configured protocol Screen, and updates RandR. `xf86platformRemoveDevice()` closes/removes that GPU Screen and removes the Xorg platform-device entry. XAverius MUST map these operations to ScreenAttachment attach/detach and source-observation withdrawal as appropriate; the screen-removal path alone is not proof of physical removal.
- `xf86platformPrimary()` may fall back to the first platform device when no primary bus is configured. That fallback is an Xorg primary-device convention and MUST NOT feed XAverius PhysicalDevice ordering, provider selection, or `CreateDefaultDevice`.

A practical initial sequence is therefore: bootstrap the XAverius registry and hotplug observation before `xf86BusProbe()`; ingest platform observations during/after `xf86platformProbe()`; accept provider bindings during provider discovery and DDX probe/PreInit; close the initial discovery barrier and publish complete records before client requests are dispatched; then attach Screen generations as Xorg creates them. The exact hook placement is an XLibre integration decision, but the ordering and separation are mandatory.


The registry implementation SHOULD remain in the XAverius subsystem even when the first deployment is Xorg-only; Xorg-specific discovery adapters belong beside the platform bus code. This avoids coupling the registry to Xorg-only data structures and permits the same XAverius registry to serve Xvfb or another DDX. Moving the registry into generic DIX is not required unless a separate non-XAverius server service later needs the same device inventory.

## 9. Required architecture tests

The implementation test suite SHOULD include at least:

1. Two Screens and two DDX discovery paths report the same GPU: one PhysicalDevice record and one XAverius XID.
2. DRM primary and render nodes report the same GPU: one record; removing one access node does not mark the hardware REMOVED while the physical device remains.
3. Two ICDs report the same GPU with different provider handles: one record, deterministic selected provider, one coherent metadata snapshot.
4. Reordering Screen, DDX, provider, and ICD initialization does not change canonical identity, selected provider, or CreateDefaultDevice result under a fixed configuration.
5. The selected provider becomes unavailable while hardware remains: status becomes UNAVAILABLE, not REMOVED; a different provider is not silently substituted.
6. A provider context shared by two selected PhysicalDevices becomes unavailable: both affected PhysicalDevices become UNAVAILABLE; a third PhysicalDevice merely discovered by that provider but selected through another provider remains AVAILABLE. Recover the same provider generation and verify only its selected bindings recover, with unchanged XIDs and snapshots.
7. A single provider-local PhysicalDevice binding becomes unavailable while the shared provider context remains usable: only that PhysicalDevice becomes UNAVAILABLE; another PhysicalDevice selected through the same provider remains AVAILABLE. Recover the exact binding and verify only it recovers. A stale provider/device generation MUST NOT change either status.
8. The selected provider recovers for the same incarnation: the same XID and metadata snapshot become AVAILABLE again.
9. A physical remove followed by re-add at the same BDF/path/node number creates a new PhysicalDevice and XID; the old record remains REMOVED.
10. A Screen is destroyed and recreated while the same GPU remains: the attachment generation changes; the PhysicalDevice and XID do not.
11. A Screen is attached to more than one GPU, and one GPU is attached to more than one Screen: no identities are created, merged, or destroyed by attachment changes.
12. A late callback from an old provider, PhysicalDevice, or Screen generation cannot mutate a replacement object.
13. CreateDefaultDevice selection does not depend on the first Screen with XAverius support and never combines GPUs.
14. Provider module/context teardown is delayed until every logical Device, submission, callback, and backend operation referencing it has quiesced.

15. A provider reports `DEVICE_LOST` while `create_logical_device` is running: no logical Device/XID is published, the PhysicalDevice becomes UNAVAILABLE, and the request returns DEVICE_UNAVAILABLE.
16. A provider returns host/device allocation failure during logical-device creation: all partial objects are rolled back or quarantined, the target XID remains free, and ALLOCATION_FAILED is returned.
17. A provider context becomes UNAVAILABLE while a logical Device exists: the PhysicalDevice status changes, but the logical Device is not declared DEVICE_LOST without a positive loss result for that exact VkDevice.
18. A provider operation on an existing logical Device reports DEVICE_LOST concurrently with submission completion, wait satisfaction, timeout, or DestroyDevice: the first serialized terminal outcome wins exactly once.
19. A provider reports UNSUPPORTED for a capability already included in the published snapshot: the request fails as a provider contract violation, the capability snapshot is not mutated, and no client BadMatch is fabricated.
20. An asynchronous provider operation reports completion and then attempts a duplicate/late callback: only one terminal transition is committed and all retained references are released at most once.
21. DestroyDevice or disconnect races with an in-flight provider call or accepted asynchronous operation: public invalidation occurs at its defined linearization point, but provider code/context and backend objects remain pinned until the provider proves no further access.
22. A provider callback arrives after provider generation replacement or module-unload request: it is ignored for public state, cannot resolve a reused XID, and cannot execute unloaded provider code.
23. A provider reports TRANSFER_FAILURE or EXECUTION_FAILURE after asynchronous acceptance: the operation uses its defined terminal status/event and never generates a delayed X11 request error.
24. A surface-support or presentation operation is attempted for a Device/Surface pair not supported by a ScreenAttachment: the provider's exact Device/Surface result controls the outcome; attachment membership does not imply support.

25. The same XAverius Surface is queried with logical Devices from two different providers: each provider creates/owns its own provider-scoped WSI surface object, and no VkSurfaceKHR or WSI handle crosses provider instances.
26. WaitSemaphores/WaitForFence completion races with the server timeout while the selected provider becomes UNAVAILABLE: provider unavailability alone MUST NOT terminalize either server-owned wait or produce DEVICE_UNAVAILABLE. The wait remains governed by its server-visible predicate, timeout, exact logical-Device Loss, DestroyDevice, and disconnect. If an underlying provider operation subsequently fails, only the synchronization state transition actually published by that operation may affect the wait; no provider wait blocks the X11 dispatcher.
27. An accepted provider-operation token cannot establish successful completion or backend quiescence: require exactly one terminal outcome callback with a classified failure, but no quiescence/retirement confirmation. The server MUST preserve the terminal protocol outcome while quarantining the token, affected resources, and provider context; duplicate callbacks are ignored, and no provider module/context is unloaded while backend access remains possible.

28. Race positive logical-Device `DEVICE_LOST`, provider-scoped `UNAVAILABLE`, ordinary resource destroy, `DestroyDevice`, and client disconnect in every relevant pairwise serialization order. Require one public invalidation owner, first-terminal-outcome preservation, request-specific result mapping, event/reply suppression at the correct connection/Device boundary, and exactly-once reference retirement. Ordinary resource destroy is not rejected solely by provider unavailability or Device Loss; its own pending/recording blockers remain normative.

29. Withhold provider quiescence after a classified terminal failure and verify that the failure is not reclassified as `DEVICE_LOST` solely because quiescence is unknown. Quarantine every potentially accessed backend object and provider reference. Separately inject a positive `DEVICE_LOST` for one exact logical Device and verify only operations still open at that serialized point are terminalized as Device Loss.

30. A DDX reports a Screen-to-device observation without implementing Vulkan provider operations: it creates only a ScreenAttachment, not a BackendProvider or PhysicalDevice XID. A Vulkan provider reports the same GPU independently: both observations converge on one canonical PhysicalDevice.
31. A single DDX Screen maps to two GPUs and two Screens map to one GPU: all attachments are represented independently; neither attachment order nor the first Screen changes provider selection, inventory order, or PhysicalDevice identity.
32. A discovery source withdraws one observation or one DRM access node while another authoritative source still reports the same incarnation: the PhysicalDevice remains present and is not marked REMOVED. Detaching the final Screen also does not remove a still-discovered headless/render-only device.
33. Two candidates cannot be unambiguously correlated: neither is silently merged nor published as a duplicate; both remain pending until stronger identity evidence resolves the match.
34. A selected provider binding is deregistered while the physical device remains: the PhysicalDevice becomes UNAVAILABLE, no new provider generation takes over, and outstanding logical-device/operation references keep the old provider code/context pinned until safe retirement.
35. A stale source removal, provider deregistration, or Screen detach from an earlier generation arrives after replacement: it cannot mutate the new observation, provider binding, attachment, or PhysicalDevice incarnation.
36. The DRM primary and render nodes are observed in either order and through different discovery sources: both resolve to one canonical identity using the underlying DRM device relationship; withdrawing either node alone does not remove the identity.
37. Two Vulkan instances/ICDs report different handles for the same platform device and compatible valid `deviceUUID`: the observations join one PhysicalDevice, while provider bindings remain distinct and provider selection follows the configured stable policy.
38. Two simultaneously present devices report the same `deviceUUID` but have incompatible authoritative platform identities: they are not merged; the conflict is surfaced and each candidate remains independently represented only when its platform identity is unambiguous.
39. Two observations have the same BDF but belong to different confirmed hotplug incarnations: the later incarnation receives a new PhysicalDevice/XID and a delayed removal from the earlier source generation cannot remove it.
40. A mediated, SR-IOV, partitioned, or MIG-like child reports its parent identity but lacks a unique instance discriminator: it is not merged with the parent or a sibling and remains unpublished until its instance identity is resolved.
41. A software/virtual provider supplies a stable provider-scoped instance key: it may publish as a distinct device, but a second provider's matching display name or vendor/device IDs do not merge with it.
42. Two providers have duplicate stable provider keys, or one configured preference identifier matches multiple provider instances: startup reports a configuration error; registration order and enumeration order cannot break the tie.
43. A preferred provider has a binding with conflicting UUID/platform evidence or cannot produce a complete snapshot: it is ineligible before publication and the next eligible provider in configured order is considered.
44. Reordering ICD enumeration, provider registration, DRM node discovery, and Screen creation while holding source evidence and server configuration constant produces the same canonical identities and selected providers.
45. With no explicit default-device preference, permuting discovery/provider/Screen order while keeping the same set of canonical identities and queue capabilities yields the same `CreateDefaultDevice` target according to the canonical ordering key.
46. An explicit default-device selector resolves to exactly one canonical PhysicalDevice; a selector matching zero or multiple identities is handled as a configuration error and never falls back based on XID, Screen, or enumeration order.
47. A preferred PhysicalDevice that is UNAVAILABLE, lacks timelineSemaphore support, or cannot supply the requested compute queue count is filtered before ranking; the next suitable preference is selected, or DEVICE_UNAVAILABLE is returned if none remains.
48. A logical Device created from render GPU A is queried against a Surface whose Screen has scanout GPU B: support is true only if A's selected provider establishes a complete direct or explicit bridge route; B's ScreenAttachment alone does not imply support.
49. A PRIME/DRI3-capable topology exists but the selected provider cannot import/export the required format or synchronize the transfer: the exact Device/Surface query reports no present-capable queue and CreateSwapchain returns UNSUPPORTED_CONFIGURATION.
50. The selected provider establishes a cross-GPU bridge route and reports supported queue families/formats/usages: QueuePresent uses that route, preserves the required source/destination synchronization, and never passes provider-local Vulkan handles across provider boundaries.
51. A Surface belongs to Screen S1 while a different Screen S2 has an available scanout GPU: capability queries and presentation remain bound to S1; the server never redirects to S2 based on enumeration or attachment order.
52. A route generation changes after Swapchain creation: the old Swapchain becomes OUT_OF_DATE, no new operation is accepted on it, and a replacement query/create may select the new route; old callbacks cannot mutate the new route or Swapchain generation.
53. A scanout/bridge route fails while the render PhysicalDevice and logical Device remain healthy: presentation is failed/invalidated under its own status contract, but the render PhysicalDevice is not marked REMOVED and the logical Device is not declared DEVICE_LOST without an exact positive backend loss result.
54. Two Screens attach the same render GPU but have different scanout GPUs: each (Device, Surface) query independently reports its actual route and capability set; no global per-PhysicalDevice present-support bit is inferred.
55. A temporary bridge-route outage occurs without a route-generation change: GetSurfaceCapabilities and new/pre-acceptance operations report DEVICE_UNAVAILABLE, but the render PhysicalDevice and logical Device remain AVAILABLE; a pending acquire and accepted QueuePresent use their respective first-terminal mappings.
56. Route invalidation races with acquire timeout, accepted presentation terminalization, and image release in both serialization orders: OUT_OF_DATE is committed only when route invalidation wins the relevant gate; an earlier terminal result or image-release milestone is never rewritten or retracted.

57. Two logical Devices created from the same PhysicalDevice query and create swapchains for the same Surface: each PresentationRoute is scoped to its exact logical-Device generation, even if both use the same provider, PhysicalDevice, Window, and Screen. Destroying or invalidating one Device/route MUST NOT retire, invalidate, or redirect the other Device's route or Swapchain; stale callbacks from the first route generation MUST NOT affect the second.

58. A discovery source attempts to confirm physical removal without authoritative evidence for the exact current incarnation, or submits evidence from a stale source/device generation: the registry rejects the transition and MUST NOT mark the PhysicalDevice REMOVED. A later valid removal observation for the current incarnation commits REMOVED exactly once.

59. Provider context/device unavailable or recovery is submitted with an unknown provider, stale provider generation, stale PhysicalDevice generation, or absent selected binding: the registry returns a classified non-success result and leaves all statuses unchanged. A valid transition returns SUCCESS and affects only the exact selected provider context/binding scope.

60. A caller releases or mutates a temporary source/provider key or descriptor immediately after a registry call returns: the registry's canonical keys and retained state remain valid because retained input bytes were copied or explicitly reference-counted before return. Conversely, provider operation tables, callback code, callback userdata, and provider context remain pinned until the final provider reference and every operation token are safely retired; module/context teardown before that point is forbidden.



61. The platform hotplug subscription is active before initial enumeration; inject add/remove events during the scan and verify reconciliation produces exactly the current incarnation, with no lost event, duplicate publication, or stale removal.
62. Delay Screen creation and RandR initialization after all configured discovery adapters complete: the startup barrier closes and the same initial PhysicalDevice inventory is published without waiting for a ScreenAttachment.
63. Make one configured discovery adapter fail or report unavailable during startup: the barrier completes with that source unavailable, no candidate from it is falsely marked REMOVED, no incomplete snapshot is published, and unrelated fully discovered devices remain publishable.
64. Register a discovery adapter after the startup barrier closes: it cannot reopen the barrier or reorder/mutate existing PhysicalDevices; a newly discovered candidate follows the independent per-device publication path.
65. Have a DDX report a Screen mapping using only a Screen index, Entity index, private pointer, or unverified DRM pathname: the mapping remains unresolved and cannot create, merge, or attach a PhysicalDevice.
66. Unload a DDX/provider module while an old Screen-generation callback or provider operation remains outstanding: new callbacks are stopped, old references remain pinned or quarantined, and neither module code nor callback userdata is released until exact-generation retirement proves quiescence.


67. On an XLibre build whose udev DRM discovery enumerates only `card[0-9]*` and deduplicates by major/minor, independently discover/correlate the render node for the same DRM device. Verify one canonical PhysicalDevice and prove that neither major/minor equality nor node name is used as its identity key.
68. Invoke the Xorg GPU-screen removal path for a device whose underlying hardware remains present: the exact ScreenAttachment and Xorg discovery observation are retired, but the PhysicalDevice is not marked REMOVED while authoritative platform/provider evidence for the same incarnation remains.
69. Configure no Xorg primary bus so `xf86platformPrimary()` uses its first-platform-device fallback, then permute platform/Screen enumeration: XAverius canonical inventory order, provider selection, and `CreateDefaultDevice` remain unchanged.


70. Close a GPU Screen through the XLibre sequence `dixScreenRaiseClose()` → `RemoveGPUScreen()` → `xf86DeleteScreen()`. Verify that the exact ScreenAttachment is detached before Screen-private data is freed, while the shared provider registration, selected PhysicalDevice, and provider module lease remain live if any other Screen, logical Device, route, or provider operation still references them.
71. In `FreeScreen()`, drop the ordinary Xorg Screen/module reference while an accepted provider operation is still pending. Verify that the independent provider/module lease prevents unloading every provider operation, callback, trampoline, and userdata address reachable by that operation.
72. Race a provider terminal callback with `retire_operation`. SUCCESS MUST NOT be returned until the callback has returned to the server-owned sink and no further callback for that exact token can begin. The server may process its copied completion record after provider callback code has returned and the provider module remains otherwise pinned.
73. Begin provider-wide quiescence while callbacks, worker tasks, and operation tokens are outstanding. PENDING MUST retain the module/context and reject new operations; SUCCESS is permitted only after all callbacks/workers are unreachable and all operation tokens are retired. Inject an unquiesceable worker and verify quarantine rather than module unload.
74. Unload a DDX module that implements topology and provider roles while a second Screen still uses the same PhysicalDevice through a different DDX. Verify that topology-role withdrawal detaches only the unloading DDX's ScreenAttachments, while the shared PhysicalDevice and separately owned provider remain available.
75. Use a provider callback bridge that enters DDX code and then queues a server-owned completion. Verify that both provider and DDX module leases remain held until the bridge returns; retirement of the backend token alone cannot release the DDX module while bridge callback code is still executing.


76. Duplicate a DDX `ModuleDesc` for a GPU Screen, then remove that Screen and drop its `DriverPtr.refCount` while a provider token remains live. Verify that the provider's independent loader/module pin prevents `dlclose()` and keeps operation/callback code executable until exact provider quiescence.
77. Delete the final Xorg Screen using a DDX that also implements a provider. Verify that Xorg's normal driver/module cleanup cannot unload the provider while a PhysicalDevice, logical Device, accepted operation, callback, or deferred backend destroy still retains the provider generation; after successful provider-wide quiescence and final release, the loader pin is dropped exactly once.


78. Close and delete a GPU Screen while a provider callback still holds attachment-scoped state. Verify that the callback has no raw `ScreenPtr`/`ScrnInfoPtr` or `FreeScreen()`-owned pointer to dereference; it uses only a detached, generation-checked retained context, performs no Screen/RandR callback after close, and releases that context only after callback return and operation retirement.



79. Register two providers from different modules against the same canonical PhysicalDevice. Verify that both bindings remain independently owned, exactly one is selected before publication, and the published snapshot comes wholly from that provider. Removing or quiescing the non-selected provider MUST NOT change PhysicalDevice status, XID, snapshot, or selected-provider identity.

80. Register one provider generation against several PhysicalDevices, then report a binding-scoped unavailable/removal transition for one device. Verify that only that exact binding/device is affected. A provider-context-wide failure affects every PhysicalDevice selected through that exact provider generation, but does not affect devices for which it is only a non-selected discovery provider.

81. Have two DDX/platform sources independently observe the same canonical PhysicalDevice. Withdraw or unload one source while the other remains authoritative. Verify that only the first source's observation and its owned ScreenAttachments disappear; the PhysicalDevice identity, other source observation, and unrelated provider binding remain.

82. Have one DDX module register two independent BackendProvider generations with distinct contexts and provider keys. Quiesce and unregister one generation while the other still serves a PhysicalDevice. Verify that the first generation rejects new operations and eventually releases only its own references, while the common module lease remains pinned and the second provider continues operating unchanged.

83. Race Screen close, source withdrawal, selected/non-selected binding removal, provider-generation shutdown, and authoritative physical removal in both serialization orders. Verify that each transition affects only its exact generation and ownership scope; REMOVED is terminal, stale callbacks are rejected, and no operation implicitly performs another transition's broader cleanup.

84. Remove or quiesce the selected provider while another provider binding for the same PhysicalDevice remains available. Verify that the PhysicalDevice becomes UNAVAILABLE and is not transparently rebound, that the published snapshot is unchanged, and that no existing logical Device silently migrates to the other provider.

85. Register multiple provider-local Vulkan aliases for one canonical PhysicalDevice through one provider generation. Verify that the provider deduplicates them and registers exactly one executable binding; if alias identity is ambiguous, no competing binding or PhysicalDevice publication is permitted.

86. Attach two Screens through different DDX modules to one PhysicalDevice and one shared provider. Close/unload one DDX module. Verify that only its ScreenAttachment and adapter role retire; the other ScreenAttachment, selected provider, PhysicalDevice, and provider module lease remain live.

87. Quiesce one of several provider generations backed by the same module while another generation still has a pending callback. Verify that SUCCESS for the first provider does not release the common module pin or make the second provider's callback unreachable; final module unload occurs only after all role-specific leases and callback bridges have retired.

88. Race BeginProviderShutdown against a new operation and a new provider-binding registration for the same generation. If shutdown serializes first, both are rejected without partial state; if either admission serializes first, it is retained and drained before quiescence. Repeated shutdown calls are idempotent, while a stale provider generation is rejected without affecting its replacement.



89. Register one provider descriptor and then register bindings for several PhysicalDevices. Verify that descriptor installation, provider-context retention, and module-lease retention occur exactly once for the provider generation; removing one binding does not release the provider or module lease while another binding or reference remains.

90. Attempt to register a binding before provider registration, against a stale generation, and after BeginProviderShutdown. Verify each attempt is rejected atomically and creates no binding, callback path, or extra provider/module reference. Registering the same provider generation twice is rejected; a new generation may register only after the old generation is no longer addressable by stale callbacks.

91. Register two provider generations and one DDX adapter role sharing a single module lease. Quiesce/finalize one provider while the other provider has an outstanding operation and the adapter role remains active. Verify the first provider context is released while the shared module remains pinned; only after all provider and adapter role references are released may the loader perform final module unload.

92. Make quiesce_provider return PENDING, then FAILURE, then SUCCESS in separate runs. Verify PENDING retains the provider/module lease and permits retry; FAILURE quarantines without finalization; SUCCESS records quiescence but still does not release the module lease while logical-device/provider-object references remain. Verify finalization calls release_provider before the final lease release, exactly once.

93. Attempt provider finalization while a logical Device, deferred backend destroy, callback bridge, or provider-owned object still retains the provider generation. Verify the operation remains pending and no provider context, operation table, callback userdata, or module lease is released.


These tests validate the server architecture; they do not replace the wire-level conformance vectors in `conformance.md`.
