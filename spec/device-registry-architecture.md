# Server-Side Physical-Device Registry Architecture

**Status:** Implementation architecture contract for XAverius v0.1. This document does not define wire fields or Vulkan backend implementation details. The protocol requirements in `devices.md` remain authoritative if a conflict is found.

## 1. Object model and ownership

The server MUST maintain one process-wide Physical-Device registry. It MUST NOT be owned by an X11 Screen, Xorg Entity, DDX instance, DRM node, Vulkan instance, or XAverius client connection.

The model has three distinct object classes:

1. **PhysicalDevice** — one canonical physical-device incarnation exposed by the server. It owns the server-lifetime identity, immutable published metadata snapshot, current discovery status, and references to registered providers. It is the sole source for XAverius Physical-Device enumeration and properties.
2. **BackendProvider** — one concrete backend execution/discovery context capable of querying and operating on a PhysicalDevice. It owns provider-specific handles, dispatch tables, backend objects, and module/library references. A provider is attached to one or more PhysicalDevices only through explicit canonical matching; it is never itself a PhysicalDevice identity.
3. **ScreenAttachment** — a relationship between one live X11 Screen generation and one PhysicalDevice. It records that a Screen/DDX path uses or can access a device for a particular role. It does not own either endpoint and does not establish Vulkan presentation support.

The relationships are:

- One PhysicalDevice MAY have zero or more BackendProviders.
- One PhysicalDevice MAY have zero or more ScreenAttachments.
- One Screen MAY have zero or more ScreenAttachments; a Screen is not required to map to exactly one GPU.
- A BackendProvider MUST NOT be implicitly created or destroyed with a ScreenAttachment.
- Destroying a Screen or detaching a provider MUST NOT destroy the PhysicalDevice identity.
- A PhysicalDevice MUST NOT be destroyed while its tombstone or any logical-device/backend reference remains live.

The registry owns PhysicalDevice records and their canonical identity. The backend/provider manager owns BackendProvider lifetimes. The Screen/DDX layer owns ScreenAttachment lifetimes. XAverius owns the protocol resource/XID wrapper for each published PhysicalDevice. These ownership boundaries MUST remain explicit.

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

## 3. BackendProvider contract

Provider selection MUST use the following v0.1 policy:

1. The server MAY configure an ordered provider-preference list using stable provider identifiers. A configured provider that is not discovered or cannot successfully query the candidate is skipped during initial selection.
2. If no explicit preference selects a usable provider, the server MUST select the usable provider with the lexicographically lowest canonical provider key. The key MUST be derived from stable provider identity/configuration (for example, ICD manifest identity plus configured instance slot), never from pointer values, load order, discovery order, or transient handles.
3. The chosen provider is fixed before PhysicalDevice publication. The server MUST NOT publish a record and later change its selected provider because a higher-priority provider appeared.
4. The selected provider supplies the complete published metadata snapshot. A provider that cannot supply a complete, internally consistent snapshot is not eligible for selection.

The configuration syntax is implementation-specific; it MUST express an ordered list of stable provider identifiers and MUST NOT depend on DRM node numbers or Screen indices. An implementation MAY initially expose this as an Xorg `Option` or server command-line setting. With no explicit setting, the canonical-key ordering above is mandatory and reproducible.


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

## 4. ScreenAttachment contract

A ScreenAttachment is a non-owning, generation-checked relation between a live Screen and a PhysicalDevice. It MAY record roles such as rendering, scanout/display control, or backend discovery association. The role vocabulary is implementation-internal in v0.1; it does not change the PhysicalDevice identity or its XAverius properties.

A ScreenAttachment MUST NOT:

- create, publish, or destroy a PhysicalDevice;
- choose the PhysicalDevice's selected Vulkan provider;
- imply that every window on the Screen can be presented by that device;
- imply that a compute-capable device is scanout-capable;
- imply that two devices attached to the same Screen can share resources;
- imply that a device attached to Screen 0 is preferred by CreateDefaultDevice.

Surface presentation support MUST continue to be evaluated for the exact logical Device/Surface pair by the presentation capability path. ScreenAttachment is discovery/topology information, not a substitute for a Vulkan surface-support query.

A ScreenAttachment MUST be detached when its exact Screen generation is destroyed or replaced. A late detach event from an old Screen generation MUST NOT detach a newer Screen that reuses the same numeric server-side index or pointer slot.

## 5. Lifecycle and event serialization

All registry mutations that can affect PhysicalDevice status, publication, provider selection, ScreenAttachment membership, or XAverius events MUST be serialized through the X server's main/event thread or an equivalent server-owned serialization domain. Backend worker threads MAY detect conditions, but MUST enqueue immutable observations to that domain; they MUST NOT mutate registry objects or send X11 events directly.

The registry distinguishes at least these operations:

- register a provider observation for a candidate;
- mark a provider unavailable or recovered;
- confirm physical-device removal;
- attach or detach a Screen generation;
- publish a canonical PhysicalDevice to XAverius;
- retire provider references after backend quiescence.

Provider loss and physical-device removal are different events. A lost ICD context, failed Vulkan instance, or provider unload MUST NOT by itself mark hardware REMOVED. Conversely, a confirmed kernel/device removal MUST NOT be suppressed merely because an alternate provider still has a stale Vulkan handle.

The existing PhysicalDevice status state machine remains authoritative: AVAILABLE and UNAVAILABLE may recover between each other; either may transition to terminal REMOVED. REMOVED records remain tombstones until server shutdown. Registry state transitions and the corresponding `XAverius.deviceStatus` value/event MUST have one serialization point.

The registry MUST use generation-checked internal references for PhysicalDevice, BackendProvider, and ScreenAttachment lifetimes. Numeric XIDs, DRM node numbers, array indices, and raw pointers without a lifetime generation MUST NOT be used to resolve delayed callbacks. A callback captured for an old provider/device/screen generation MUST NOT mutate a replacement object that reuses an address, index, node number, or public XID.

## 6. Suggested internal API boundary

The following is an abstract C interface sketch, not a public ABI and not a wire definition. Names and exact types MAY be adapted to Xserver conventions, but the ownership and semantic boundaries MUST be preserved.

```c
typedef struct GpuRegistry GpuRegistry;
typedef struct GpuPhysicalDevice GpuPhysicalDevice;
typedef struct GpuBackendProvider GpuBackendProvider;
typedef struct GpuScreenAttachment GpuScreenAttachment;

typedef struct {
    /* Structured bus/sysfs/DRM identity, optional valid deviceUUID,
       virtual-instance discriminator, and incarnation evidence. */
} GpuDeviceIdentity;

typedef struct {
    /* Provider type/configuration identity, opaque context, ops,
       provider-local device handle, and lifetime hooks. */
} GpuProviderDescriptor;

/* Server startup/shutdown; one registry per X server process. */
GpuRegistry *GpuRegistryCreate(void);
void GpuRegistryDestroy(GpuRegistry *registry);

/* Discovery/provider registration. Returns the canonical record to which
   this observation belongs; it does not allocate a protocol XID. */
GpuPhysicalDevice *GpuRegistryRegisterProvider(
    GpuRegistry *registry,
    const GpuDeviceIdentity *identity,
    const GpuProviderDescriptor *provider);

/* Provider availability is distinct from physical removal. */
void GpuRegistryProviderUnavailable(
    GpuRegistry *registry, GpuBackendProvider *provider,
    uint64_t provider_generation);
void GpuRegistryProviderRecovered(
    GpuRegistry *registry, GpuBackendProvider *provider,
    uint64_t provider_generation);
void GpuRegistryConfirmDeviceRemoved(
    GpuRegistry *registry, GpuPhysicalDevice *device,
    uint64_t device_generation);

/* Screen relationships are non-owning and generation checked. */
GpuScreenAttachment *GpuRegistryAttachScreen(
    GpuRegistry *registry, GpuPhysicalDevice *device,
    ScreenPtr screen, uint64_t screen_generation, unsigned int roles);
void GpuRegistryDetachScreen(
    GpuRegistry *registry, GpuScreenAttachment *attachment,
    uint64_t attachment_generation);

/* XAverius publishes and maps canonical records to server-owned XIDs. */
void XaPhysicalDevicePublish(GpuPhysicalDevice *device);
XID XaPhysicalDeviceXid(const GpuPhysicalDevice *device);

/* Logical-device creation pins the selected provider and generations. */
GpuBackendProvider *GpuPhysicalDeviceAcquireExecutionProvider(
    GpuPhysicalDevice *device);
void GpuBackendProviderRelease(GpuBackendProvider *provider);
```

The API MUST NOT expose a public function such as `RegisterPhysicalDeviceWithXid()` to DDX drivers. XID allocation and protocol resource publication belong exclusively to the XAverius/server resource layer. A provider registration may return an existing canonical record or create an unpublished candidate; it MUST NOT publish a duplicate identity.

The registration API SHOULD be split into candidate discovery and provider attachment internally if that is needed to finish startup-wide provider selection before publication. The simplified sketch above does not permit immediate publication during arbitrary driver probe order.

## 7. Xlibre/Xorg integration guidance

For the current XAverius scope, the recommended ownership location is the XAverius server subsystem itself (for example, `Xext/xaverius/registry.c`), with a private server-internal interface declared in an exported header such as `include/xaverius_registry.h`. This keeps Vulkan-specific identity, provider selection, metadata snapshots, and XAverius XID publication together without making generic DIX depend on Vulkan or DRM. The interface is an internal server/module interface, not a stable client ABI or a promise of compatibility for independently built third-party modules.


The existing Xorg platform-device list (`xf86_platform_devices` in `hw/xfree86/common/xf86platformBus.c`) and udev DRM discovery (`config/udev.c`) are useful discovery inputs, not the canonical XAverius registry. The platform list is organized around device-node attributes and Xorg ownership/claiming; the current DRM udev path filters `card*` nodes and deduplicates those observations by major/minor. These are appropriate for Xorg device management but do not represent identity across DRM primary/render nodes, multiple Vulkan instances/ICDs, or hotplug generations.

Recommended layering:

- Xorg platform/udev code reports discovery and removal observations to the registry.
- DDX drivers register provider contexts after they have a usable backend device.
- The server-wide registry canonicalizes candidates and owns PhysicalDevice records.
- XAverius enumerates only published registry records and owns their protocol XID resources.
- Screen initialization creates/destroys ScreenAttachments only.
- Surface/WSI code performs the actual Device/Surface presentation-support query; it must not infer support from a ScreenAttachment.

For an Xorg-only prototype, the registry implementation MAY initially live beside the Xorg platform bus code, but its API MUST remain Screen-independent. If the service is intended for multiple DDX families or non-Xorg server configurations, its ownership should move to a DIX/server-core layer, with Xorg platform discovery as one provider of observations.

## 8. Required architecture tests

The implementation test suite SHOULD include at least:

1. Two Screens and two DDX discovery paths report the same GPU: one PhysicalDevice record and one XAverius XID.
2. DRM primary and render nodes report the same GPU: one record; removing one access node does not mark the hardware REMOVED while the physical device remains.
3. Two ICDs report the same GPU with different provider handles: one record, deterministic selected provider, one coherent metadata snapshot.
4. Reordering Screen, DDX, provider, and ICD initialization does not change canonical identity, selected provider, or CreateDefaultDevice result under a fixed configuration.
5. The selected provider becomes unavailable while hardware remains: status becomes UNAVAILABLE, not REMOVED; a different provider is not silently substituted.
6. The selected provider recovers for the same incarnation: the same XID and metadata snapshot become AVAILABLE again.
7. A physical remove followed by re-add at the same BDF/path/node number creates a new PhysicalDevice and XID; the old record remains REMOVED.
8. A Screen is destroyed and recreated while the same GPU remains: the attachment generation changes; the PhysicalDevice and XID do not.
9. A Screen is attached to more than one GPU, and one GPU is attached to more than one Screen: no identities are created, merged, or destroyed by attachment changes.
10. A late callback from an old provider, PhysicalDevice, or Screen generation cannot mutate a replacement object.
11. CreateDefaultDevice selection does not depend on the first Screen with XAverius support and never combines GPUs.
12. Provider module/context teardown is delayed until every logical Device, submission, callback, and backend operation referencing it has quiesced.

These tests validate the server architecture; they do not replace the wire-level conformance vectors in `conformance.md`.
