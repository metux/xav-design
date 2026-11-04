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
| Presentation | provider-scoped surface create/destroy (from the XAverius Surface's retained Window identity); surface support/capability query for an exact Device/Surface pair; surface-format and present-mode query; swapchain create/destroy; image acquire; queue present | Implement the presentation profile only when enabled. ScreenAttachment MUST NOT substitute for the exact Device/Surface support query. |

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
| `UNAVAILABLE` | Provider context or physical-device access is temporarily unavailable; no logical-Device-loss result has been established | Mark the selected PhysicalDevice UNAVAILABLE through the registry serialization domain. Any request that requires the unavailable provider fails through its request-defined `DEVICE_UNAVAILABLE` error/status channel. Existing logical Devices are not automatically declared lost solely by this result. |
| `DEVICE_LOST` | The backend has positively reported loss of this exact logical Vulkan Device (for example, `VK_ERROR_DEVICE_LOST`) | Commit the logical Device's DEVICE_LOST transition exactly once. Reply-pending requests use their request-defined final reply/status or X11 error; protocol-accepted operations use their defined terminal status/events. |
| `OUT_OF_HOST_MEMORY` / `OUT_OF_DEVICE_MEMORY` | Backend allocation failed for lack of host/device memory | Map to `ALLOCATION_FAILED` where the request contract exposes a synchronous allocation error; otherwise use that operation's specified asynchronous failure result. |
| `TRANSFER_FAILURE` | A buffer upload/readback or other defined transfer operation failed without Device Loss | Map to `TRANSFER_FAILED` for reply-bearing transfer requests such as WriteBuffer/ReadBuffer; operations whose protocol contract is event-terminal use their defined asynchronous failure path. |
| `EXECUTION_FAILURE` | Accepted GPU execution failed without a Device-Loss classification | Use the request-defined terminal channel: for example, QueueSubmit uses submission events and Fence state, while WaitForFence returns `EXECUTION_FAILED`. Never emit a delayed X11 error for an operation that has already crossed its protocol acceptance point. |
| `CANCELLED` | Operation was prevented from starting because its captured Device/resource generation was destroyed or terminalized | Complete it with the lifecycle result already committed by the server (for example `DEVICE_DESTROYED`); never invoke backend work after cancellation wins. |
| `FATAL` | Unclassified backend/provider failure or violated provider contract | Fail with `INTERNAL_SERVER_ERROR` if a synchronous request is still awaiting a result; mark the provider unavailable if its continued correctness cannot be trusted. Preserve all references until safe retirement. |

All provider operations that can fail, including backend destroy/retire operations, MUST return a classified `GpuProviderResult`. A destroy operation is best-effort with respect to an already committed public destroy: its failure MUST NOT resurrect an XID or create a delayed X11 error. The server retains/quarantines the backend object and provider context until safe retirement. The `retain_*`/`release_*` reference hooks are local lifetime primitives rather than backend operations; they MUST be infallible and MUST NOT invoke Vulkan or block. `retire_operation` MUST be idempotent, MUST return a classified result, and MUST release only the exact operation-token generation supplied to it. If retirement fails, the server MUST retain/quarantine the token and provider context rather than assuming quiescence.

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

A ScreenAttachment is a non-owning, generation-checked relation between a live Screen and a PhysicalDevice. It MAY record roles such as rendering, scanout/display control, or backend discovery association. The role vocabulary is implementation-internal in v0.1; it does not change the PhysicalDevice identity or its XAverius properties.

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

## 6. Lifecycle and event serialization

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

## 7. Suggested internal API boundary

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
} GpuProviderResult;

typedef struct {
    uint64_t provider_generation;
    uint64_t operation_generation;
    uint64_t operation_token_id;
    GpuProviderResult result;
    /* Operation-specific immutable result payload follows. */
} GpuProviderCompletion;

typedef void (*GpuProviderCompletionFn)(
    void *completion_userdata,
    const GpuProviderCompletion *completion);

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
    GpuProviderResult (*create_swapchain)(
        GpuProviderDevice *, GpuProviderSurface *,
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
} GpuProviderOps;

typedef struct {
    /* Stable provider identity/configuration, opaque provider context,
       provider-local physical-device handle, and operation table. */
    const char *canonical_provider_key;
    void *provider_context;
    const GpuProviderOps *ops;
    GpuProviderCompletionFn completion_sink;
    void *completion_userdata;
    uint64_t provider_generation;
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

## 8. Xlibre/Xorg integration guidance

For the current XAverius scope, the recommended ownership location is the XAverius server subsystem itself (for example, `Xext/xaverius/registry.c`), with a private server-internal interface declared in an exported header such as `include/xaverius_registry.h`. This keeps Vulkan-specific identity, provider selection, metadata snapshots, and XAverius XID publication together without making generic DIX depend on Vulkan or DRM. The interface is an internal server/module interface, not a stable client ABI or a promise of compatibility for independently built third-party modules.


The existing Xorg platform-device list (`xf86_platform_devices` in `hw/xfree86/common/xf86platformBus.c`) and udev DRM discovery (`config/udev.c`) are useful discovery inputs, not the canonical XAverius registry. The platform list is organized around device-node attributes and Xorg ownership/claiming; the current DRM udev path filters `card*` nodes and deduplicates those observations by major/minor. These are appropriate for Xorg device management but do not represent identity across DRM primary/render nodes, multiple Vulkan instances/ICDs, or hotplug generations.

Recommended layering:

- Xorg platform/udev code reports discovery and removal observations to the registry.
- DDX drivers register provider contexts after they have a usable backend device.
- The server-wide registry canonicalizes candidates and owns PhysicalDevice records.
- XAverius enumerates only published registry records and owns their protocol XID resources.
- Screen initialization creates/destroys ScreenAttachments only.
- Surface/WSI code performs the actual Device/Surface presentation-support query; it must not infer support from a ScreenAttachment.

The registry implementation SHOULD remain in the XAverius subsystem even when the first deployment is Xorg-only; Xorg-specific discovery adapters belong beside the platform bus code. This avoids coupling the registry to Xorg-only data structures and permits the same XAverius registry to serve Xvfb or another DDX. Moving the registry into generic DIX is not required unless a separate non-XAverius server service later needs the same device inventory.

## 9. Required architecture tests

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

13. A provider reports `DEVICE_LOST` while `create_logical_device` is running: no logical Device/XID is published, the PhysicalDevice becomes UNAVAILABLE, and the request returns DEVICE_UNAVAILABLE.
14. A provider returns host/device allocation failure during logical-device creation: all partial objects are rolled back or quarantined, the target XID remains free, and ALLOCATION_FAILED is returned.
15. A provider context becomes UNAVAILABLE while a logical Device exists: the PhysicalDevice status changes, but the logical Device is not declared DEVICE_LOST without a positive loss result for that exact VkDevice.
16. A provider operation on an existing logical Device reports DEVICE_LOST concurrently with submission completion, wait satisfaction, timeout, or DestroyDevice: the first serialized terminal outcome wins exactly once.
17. A provider reports UNSUPPORTED for a capability already included in the published snapshot: the request fails as a provider contract violation, the capability snapshot is not mutated, and no client BadMatch is fabricated.
18. An asynchronous provider operation reports completion and then attempts a duplicate/late callback: only one terminal transition is committed and all retained references are released at most once.
19. DestroyDevice or disconnect races with an in-flight provider call or accepted asynchronous operation: public invalidation occurs at its defined linearization point, but provider code/context and backend objects remain pinned until the provider proves no further access.
20. A provider callback arrives after provider generation replacement or module-unload request: it is ignored for public state, cannot resolve a reused XID, and cannot execute unloaded provider code.
21. A provider reports TRANSFER_FAILURE or EXECUTION_FAILURE after asynchronous acceptance: the operation uses its defined terminal status/event and never generates a delayed X11 request error.
22. A surface-support or presentation operation is attempted for a Device/Surface pair not supported by a ScreenAttachment: the provider's exact Device/Surface result controls the outcome; attachment membership does not imply support.

23. The same XAverius Surface is queried with logical Devices from two different providers: each provider creates/owns its own provider-scoped WSI surface object, and no VkSurfaceKHR or WSI handle crosses provider instances.
24. WaitSemaphores/WaitForFence completion races with the server timeout while the selected provider becomes UNAVAILABLE: provider unavailability alone MUST NOT terminalize either server-owned wait or produce DEVICE_UNAVAILABLE. The wait remains governed by its server-visible predicate, timeout, exact logical-Device Loss, DestroyDevice, and disconnect. If an underlying provider operation subsequently fails, only the synchronization state transition actually published by that operation may affect the wait; no provider wait blocks the X11 dispatcher.
25. An accepted provider-operation token cannot establish successful completion or backend quiescence: require exactly one terminal outcome callback with a classified failure, but no quiescence/retirement confirmation. The server MUST preserve the terminal protocol outcome while quarantining the token, affected resources, and provider context; duplicate callbacks are ignored, and no provider module/context is unloaded while backend access remains possible.

These tests validate the server architecture; they do not replace the wire-level conformance vectors in `conformance.md`.
