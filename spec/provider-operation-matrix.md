# DDX backend operation matrix and typed interface contract

**Status:** Normative supplement to Sections 4, 4.1, 4.1.1, and 7 of [device-registry-architecture.md](device-registry-architecture.md). This document closes the abstract DDX backend-table declarations. It does not define a client ABI and changes no request subopcode, wire field, event ID, or Vulkan capability.

If a summary table in Section 4.1 differs from this matrix, this document governs the DDX backend/server boundary. The request chapters remain authoritative for validation order, observable state, and client-visible error/status behavior.

## 1. Common operation contract

Every backend operation MUST be reached only after the server has completed the request-specific validation required by the normative request chapter. DDX backend functions MUST NOT parse XAverius wire data, resolve client XIDs, select a PhysicalDevice, choose a queue family, or make client-visible state transitions.

Every synchronous backend operation returns a fully initialized `XaveriusBackendResult`. Every output parameter MUST be initialized to its failure sentinel before any backend call. On any non-success result, object outputs are NULL, scalar outputs are zero, and output arrays are empty unless that operation explicitly defines a non-error STATUS result. The DDX binding MUST NOT expose a partially created object. It MUST roll back partial backend creation or retain it privately for safe cleanup.

For synchronous operations, `XAVERIUS_BACKEND_SUCCESS` means the requested backend action completed sufficiently for the request handler to commit its server-side state transition. It does not mean that unrelated queued GPU work completed.

For the six asynchronous operations (WriteBuffer, ReadBuffer, host SignalSemaphore, QueueSubmit, AcquireNextImage, QueuePresent), `XAVERIUS_BACKEND_SUCCESS` means **accepted** and requires exactly one eventual completion for the prepared token. It does not mean completion. Any other immediate result means not accepted and requires the matching token rejection path; the DDX binding MUST NOT later access resources or emit a completion for it. A DDX backend that has performed backend access or emitted a completion and then returns non-success violates the contract and is quarantined.

`XAVERIUS_BACKEND_UNSUPPORTED` is legal only for an operation/profile capability not advertised by the selected DDX binding, or for the pair-specific absence of a DDX-native WSI path reported by `create_surface`/`create_presentation_route` before support has been advertised for the unchanged Device/Surface/binding/Window generations. That pair-specific result is cached and mapped through the presentation request contract; it does not mark the PhysicalDevice unavailable. If `query_surface_support` has already reported support for that unchanged pair, a later `UNSUPPORTED` from route/swapchain creation is a DDX contract violation and is handled as FATAL/INTERNAL_SERVER_ERROR, not client BadMatch. An `UNSUPPORTED` result for any other previously advertised capability is likewise FATAL.

The registry owns all resource validation, generation checks, dependency pinning, operation-token allocation, public XID state, and request ordering. DDX backend-local handles MUST remain private behind typed opaque wrappers. The DDX binding MUST validate the exact binding generation whenever an operation resolves a PhysicalDevice binding.

## 1.1 DDX binding is the direct dispatch target

In the Xlibre/Xorg integration profile, the DDX registers each PhysicalDevice it serves and binds the applicable immutable operation tables, per-device context, and native physical-device handle to that device's registry binding. The selected PhysicalDevice binding is the direct dispatch target for every operation in this matrix. The server MUST NOT perform an additional XaveriusModuleRole-object lookup between resolving the PhysicalDevice/logical Device and invoking the typed operation.

The former DDX backend-generation terminology in earlier API drafts is superseded by the per-PhysicalDevice DDX binding and shared `XaveriusModuleRole` lifetime record described in the current architecture. A module role is not a per-device backend instance or dispatch proxy. Operation arguments MUST identify the exact device binding and binding generation; the DDX backend/module-role generation is additional lifetime provenance only. Per-device native handles and context remain on the binding. See [ddx-device-registration.md](../implementation-notes/ddx-device-registration.md).

## 2. Complete request-to-DDX backend mapping

| Subopcode | Request | DDX backend operation(s) | DDX backend involvement |
|---:|---|---|---|
| 0 | QueryVersion | None | Entirely server-side |
| 1 | EnumeratePhysicalDevices | DDX enumerates devices itself and registers each served device | No per-request DDX backend call; reply from registry snapshot |
| 2 | GetPhysicalDeviceProperty | None | Snapshot lookup |
| 3 | GetPhysicalDeviceQueueFamilyProperties | None | Snapshot lookup |
| 4 | CreateDevice | `create_logical_device`, `get_queue` for each requested queue | Synchronous create; rollback all queues/device if any step fails |
| 5 | CreateDefaultDevice | Same as CreateDevice | Server selects exact PhysicalDevice/DDX backend first |
| 6 | DestroyDevice | `destroy_logical_device` after dependent backend objects/work retire | Server validates and cascades; backend teardown may be deferred |
| 7 | GetPhysicalDeviceMemoryProperties | None | Snapshot lookup |
| 8 | CreateBuffer | `buffer_memory.create_buffer` | Synchronous create |
| 9 | GetBufferMemoryRequirements | `buffer_memory.get_buffer_memory_requirements` | Synchronous query; no persistent backend object |
| 10 | AllocateMemory | `buffer_memory.allocate_memory` | Synchronous create |
| 11 | FreeMemory | `buffer_memory.free_memory` | Synchronous backend free after server proves no binding/work references |
| 12 | BindBufferMemory | `buffer_memory.bind_buffer_memory` | Synchronous bind; server commits binding only after success |
| 13 | WriteBuffer | `buffer_memory.write_buffer` | Async token; reply after completion/visibility boundary |
| 14 | ReadBuffer | `buffer_memory.read_buffer` | Async token; completion payload copied by sink for reply |
| 15 | ShaderModuleData | `shader_pipeline.create_shader_module` only on validated final-chunk commit; abort/chunk append have no DDX backend call | Server owns assembly |
| 16 | CreateDescriptorSetLayout | `shader_pipeline.create_descriptor_set_layout` | Synchronous create |
| 17 | CreateDescriptorPool | `shader_pipeline.create_descriptor_pool` | Synchronous create |
| 18 | DestroyDescriptorPool | `shader_pipeline.destroy_descriptor_pool` | Synchronous backend destroy after server proves children/dependencies can be invalidated |
| 19 | AllocateDescriptorSets | `shader_pipeline.allocate_descriptor_sets` | Atomic batch create; no partial set publication |
| 20 | UpdateDescriptorSets | `shader_pipeline.update_descriptor_sets` | Atomic batch update; DDX backend receives validated immutable update list |
| 21 | FreeDescriptorSets | `shader_pipeline.free_descriptor_sets` | Synchronous free after server lifetime checks |
| 22 | CreatePipelineLayout | `shader_pipeline.create_pipeline_layout` | Synchronous create |
| 23 | CreateComputePipeline | `shader_pipeline.create_compute_pipeline` | Synchronous create |
| 24 | CreateCommandPool | `commands.create_command_pool` | Synchronous create |
| 25 | DestroyCommandPool | `commands.destroy_command_pool` | Synchronous destroy after server has validated/inactivated children |
| 26 | ResetCommandBuffer | `commands.reset_command_buffer` | Synchronous reset |
| 27 | CommandBufferData | `commands.begin_command_buffer`, `commands.record_commands`, `commands.end_command_buffer` at the validated commit boundary; abort/chunk transport is server-only | Server assembles and validates stream before backend recording |
| 28 | QueueSubmit | top-level `queue_submit` | Async token; DDX backend receives complete validated dependency graph |
| 29 | CreateSemaphore | `synchronization.create_semaphore` | Synchronous create |
| 30 | GetSemaphoreCounterValue | None | Server-owned counter lookup |
| 31 | WaitSemaphores | None | Server-owned wait registration/timeout arbitration |
| 32 | SignalSemaphore | `synchronization.host_signal_semaphore` | Async token; server publishes counter only after completion |
| 33 | DestroySemaphore | `synchronization.destroy_semaphore` | Synchronous backend destroy after server proves no pending references |
| 34 | CreateFence | `synchronization.create_fence` | Synchronous create |
| 35 | GetFenceStatus | None | Server-owned fence-state lookup |
| 36 | WaitForFence | None | Server-owned wait registration/timeout arbitration |
| 37 | ResetFence | `synchronization.reset_fence` | Synchronous reset after server validates state |
| 38 | DestroyFence | `synchronization.destroy_fence` | Synchronous backend destroy after server proves no pending references |
| 39 | DestroyResource | One typed destroy operation selected by validated resource type: buffer, shader module, descriptor-set layout, pipeline layout, compute pipeline | Server owns type/ownership/dependency validation and XID invalidation; DDX backend performs only the typed backend destroy |
| 40 | SelectEvents | None | Entirely server-side |
| 41 | CreateSurface | None | Creates only the connection-owned logical Surface and retains the exact Window/Screen identity; no Device/DDX backend is selected by this request |
| 42 | DestroySurface | `destroy_surface` once for each successfully materialized DDX-native Surface associated with this exact logical Surface generation | Server invalidates the logical XID atomically; native cleanup follows after all Swapchain/route/query references drain |
| 43 | GetSurfaceCapabilities | Ensure/create the DDX-native Surface for the exact selected binding generation if not already materialized, then `query_surface_support` | Synchronous one-call aggregate query for the exact binding, logical Surface and selected logical Device; returns formats, present modes, limits and support for every queue family in that Device |
| 44 | CreateSwapchain | Ensure/create the DDX-native Surface for the exact selected binding generation if not already materialized, then `create_presentation_route`, `create_swapchain` | Synchronous create; route is exact logical-Device/Surface/Screen generation |
| 45 | DestroySwapchain | `destroy_swapchain` | Synchronous backend retirement after server proves all blockers drained |
| 46 | AcquireNextImage | `acquire_next_image`; `cancel_acquire` and `release_late_acquired_image` only for the specified timeout/cancellation race | Async token; server arbitrates timeout and late acquisition |
| 47 | QueuePresent | `queue_present` | Async token; server arbitrates accepted completion and presentation events |

A server-side request may still depend on state published by earlier DDX backend completions. "None" above means no DDX backend entry point is called by that request itself.

### 2.1 Command entries

Command-buffer entries are not X11 requests and MUST NOT become independent DDX backend entry points unless a future architecture revision explicitly requires it. The v0.1 validated command stream is passed to `record_commands` as typed, host-endian server structures:

- `CMD_BIND_PIPELINE`
- `CMD_BIND_DESCRIPTOR_SETS`
- `CMD_DISPATCH`
- `CMD_PUSH_CONSTANTS`
- `CMD_COPY_BUFFER_TO_SWAPCHAIN_IMAGE` (presentation profile only)

The DDX binding MUST receive no unvalidated wire bytes, client pointers, XIDs, or unpinned resource references. The server has already resolved every referenced object to a retained backend object and generation. Recording order MUST match the validated command stream exactly.

### 2.2 Logical Surface and DDX-native Surface lifetime

The XAverius Surface created by request 41 is a server-owned, connection-owned logical resource. It captures the exact Window and Screen generations but has no Device, PhysicalDevice, DDX backend, or Vulkan-instance association. Request 41 MUST NOT call any backend operation. A valid drawable Window therefore remains a valid XAverius Surface even when no currently registered DDX backend can present to it.

A DDX-native Surface is a separate DDX backend-owned object. It is materialized lazily when a Device-specific operation first needs it: GetSurfaceCapabilities, or CreateSwapchain when the client did not query capabilities first. The server resolves the exact logical Device to its already selected PhysicalDevice binding and asks that binding's DDX operations/context to create the native Surface from the captured Window/Screen identity. It MUST NOT select a DDX backend from the Screen, from registration order, or from another Device.

The server maintains at most one live DDX-native Surface wrapper for each pair (selected PhysicalDevice binding generation, logical Surface resource generation). The wrapper is scoped to that exact binding's native instance/context, not merely to its module role, and may be reused by logical Devices that use the same binding. It MUST NOT be shared across different binding generations, even when those bindings belong to the same module role. A DDX binding that internally requires more than one native object may keep those objects behind the one opaque wrapper. The wrapper retains the exact logical Window/Screen identity and the binding/module-role references for its lifetime.

DDX-native Surface creation and publication are serialized per logical Surface/binding-generation pair. Concurrent first-use queries MUST NOT create duplicate wrappers. A failed create publishes no wrapper. If create_surface returns UNSUPPORTED, the server may cache an explicit unsupported result for that pair; it MUST NOT create a fake native handle or repeatedly call the DDX backend for the same unchanged binding and Surface generations. For GetSurfaceCapabilities, this condition produces SUCCESS with present_supported = 0, empty format and present-mode lists, zero non-queue-family capability fields, and one queue-family record per Device queue family with present_supported = 0. This is a valid Device/Surface pair, not DEVICE_UNAVAILABLE or SURFACE_LOST. For CreateSwapchain, the same condition produces UNSUPPORTED_CONFIGURATION and leaves the target Swapchain XID unallocated; no route or swapchain backend operation is called. A cached unsupported result is reused for both requests. A later new binding generation or new Surface generation is evaluated independently.

DestroySurface invalidates the logical Surface XID only after its ordinary type/ownership/Swapchain checks succeed. It then retires every successfully materialized DDX-native Surface wrapper for that exact Surface generation. No wrapper may be destroyed twice or used by a later Surface generation that reuses the XID. Native destruction may be deferred until in-flight capability queries and other DDX backend calls release their temporary references; Removal/quiescence of the owning binding MUST wait for these wrappers to be destroyed or safely quarantined. An unsupported-result cache entry contains no backend object and needs no native destroy call. Removal of a selected binding MUST retire every DDX-native Surface wrapper owned by that exact binding generation once its Swapchain/route/query users have drained, even if the logical Surface remains live. This removes only that binding-generation cache entry; it MUST NOT invalidate the logical Surface or trigger binding failover for an existing logical Device. A new logical Device created later through a different eligible binding may materialize its own wrapper for the same logical Surface.

The backend operation matrix in [DDX backend operation matrix](provider-operation-matrix.md) defines the corresponding request mapping. This rule does not change the wire layout or the logical Surface ownership model.

## 3. Required typed operation-table declarations

The following declarations are semantic C-interface guidance. Exact C type names may be adapted, but every listed operation and its sync/async classification is mandatory. The currently forward-declared four table types MUST NOT remain opaque in an implementation-facing API specification.

All `*_INFO` inputs are immutable, fully validated server-owned descriptions. All returned backend objects are opaque DDX backend wrappers with exactly one owned reference transferred to the server on SUCCESS. The server MUST consume that reference exactly once through the corresponding typed destroy/free operation, or through the explicitly defined successful parent-pool cascade for a CommandBuffer or DescriptorSet.

The four typed operation-table layouts below are subordinate to the top-level `XaveriusDeviceBackendOps` ABI version. `XAVERIUS_DEVICE_BACKEND_OPS_ABI_VERSION` governs the top-level descriptor, all four nested table layouts, and every DDX-facing callback signature plus parameter/result structure they reference (including token/completion types); the nested tables do not carry independent version fields. The registry validates the top-level size/version before reading any nested callback field, then validates the required entries for the enabled v0.1 profile.

```c
struct XaveriusBackendBufferMemoryOps {
    XaveriusBackendResult (*create_buffer)(
        XaveriusBackendDevice *, const XaveriusBufferCreateInfo *,
        XaveriusBackendBuffer **out_buffer);
    XaveriusBackendResult (*free_buffer)(
        XaveriusBackendDevice *, XaveriusBackendBuffer *);
    XaveriusBackendResult (*get_buffer_memory_requirements)(
        XaveriusBackendDevice *, XaveriusBackendBuffer *,
        XaveriusBufferMemoryRequirements *out_requirements);
    XaveriusBackendResult (*allocate_memory)(
        XaveriusBackendDevice *, const XaveriusMemoryAllocateInfo *,
        XaveriusBackendMemory **out_memory);
    XaveriusBackendResult (*free_memory)(
        XaveriusBackendDevice *, XaveriusBackendMemory *);
    XaveriusBackendResult (*bind_buffer_memory)(
        XaveriusBackendDevice *, XaveriusBackendBuffer *,
        XaveriusBackendMemory *, uint64_t offset);
    XaveriusBackendResult (*write_buffer)(
        XaveriusBackendDevice *, XaveriusBackendBuffer *, XaveriusBackendMemory *,
        const XaveriusBufferTransferInfo *, XaveriusBackendOperationToken *);
    XaveriusBackendResult (*read_buffer)(
        XaveriusBackendDevice *, XaveriusBackendBuffer *, XaveriusBackendMemory *,
        const XaveriusBufferTransferInfo *, XaveriusBackendOperationToken *);
};

struct XaveriusBackendShaderPipelineOps {
    XaveriusBackendResult (*create_shader_module)(
        XaveriusBackendDevice *, const XaveriusShaderModuleCreateInfo *,
        XaveriusBackendShaderModule **out_shader);
    XaveriusBackendResult (*create_descriptor_set_layout)(
        XaveriusBackendDevice *, const XaveriusDescriptorSetLayoutCreateInfo *,
        XaveriusBackendDescriptorSetLayout **out_layout);
    XaveriusBackendResult (*create_descriptor_pool)(
        XaveriusBackendDevice *, const XaveriusDescriptorPoolCreateInfo *,
        XaveriusBackendDescriptorPool **out_pool);
    XaveriusBackendResult (*allocate_descriptor_sets)(
        XaveriusBackendDevice *, XaveriusBackendDescriptorPool *,
        const XaveriusDescriptorSetAllocateInfo *, uint32_t set_count,
        XaveriusBackendDescriptorSet **out_sets);
    XaveriusBackendResult (*update_descriptor_sets)(
        XaveriusBackendDevice *, const XaveriusDescriptorUpdateInfo *,
        uint32_t update_count);
    XaveriusBackendResult (*free_descriptor_sets)(
        XaveriusBackendDevice *, XaveriusBackendDescriptorPool *,
        XaveriusBackendDescriptorSet *const *sets, uint32_t set_count);
    XaveriusBackendResult (*create_pipeline_layout)(
        XaveriusBackendDevice *, const XaveriusPipelineLayoutCreateInfo *,
        XaveriusBackendPipelineLayout **out_layout);
    XaveriusBackendResult (*create_compute_pipeline)(
        XaveriusBackendDevice *, const XaveriusComputePipelineCreateInfo *,
        XaveriusBackendPipeline **out_pipeline);
    XaveriusBackendResult (*destroy_shader_module)(XaveriusBackendDevice *, XaveriusBackendShaderModule *);
    XaveriusBackendResult (*destroy_descriptor_set_layout)(XaveriusBackendDevice *, XaveriusBackendDescriptorSetLayout *);
    XaveriusBackendResult (*destroy_descriptor_pool)(XaveriusBackendDevice *, XaveriusBackendDescriptorPool *);
    XaveriusBackendResult (*destroy_pipeline_layout)(XaveriusBackendDevice *, XaveriusBackendPipelineLayout *);
    XaveriusBackendResult (*destroy_compute_pipeline)(XaveriusBackendDevice *, XaveriusBackendPipeline *);
};

struct XaveriusBackendCommandOps {
    XaveriusBackendResult (*create_command_pool)(
        XaveriusBackendDevice *, const XaveriusCommandPoolCreateInfo *,
        XaveriusBackendCommandPool **out_pool);
    XaveriusBackendResult (*destroy_command_pool)(
        XaveriusBackendDevice *, XaveriusBackendCommandPool *);
    XaveriusBackendResult (*allocate_command_buffer)(
        XaveriusBackendDevice *, XaveriusBackendCommandPool *,
        const XaveriusCommandBufferAllocateInfo *,
        XaveriusBackendCommandBuffer **out_command_buffer);
    XaveriusBackendResult (*free_command_buffer)(
        XaveriusBackendDevice *, XaveriusBackendCommandPool *,
        XaveriusBackendCommandBuffer *);
    XaveriusBackendResult (*reset_command_buffer)(
        XaveriusBackendDevice *, XaveriusBackendCommandBuffer *);
    XaveriusBackendResult (*begin_command_buffer)(
        XaveriusBackendDevice *, XaveriusBackendCommandBuffer *,
        const XaveriusCommandBufferBeginInfo *);
    XaveriusBackendResult (*record_commands)(
        XaveriusBackendDevice *, XaveriusBackendCommandBuffer *,
        const XaveriusValidatedCommand *, uint32_t command_count);
    XaveriusBackendResult (*end_command_buffer)(
        XaveriusBackendDevice *, XaveriusBackendCommandBuffer *);
};

struct XaveriusBackendSynchronizationOps {
    XaveriusBackendResult (*create_semaphore)(
        XaveriusBackendDevice *, const XaveriusSemaphoreCreateInfo *,
        XaveriusBackendSemaphore **out_semaphore);
    XaveriusBackendResult (*host_signal_semaphore)(
        XaveriusBackendDevice *, XaveriusBackendSemaphore *, uint64_t value,
        XaveriusBackendOperationToken *);
    XaveriusBackendResult (*destroy_semaphore)(
        XaveriusBackendDevice *, XaveriusBackendSemaphore *);
    XaveriusBackendResult (*create_fence)(
        XaveriusBackendDevice *, const XaveriusFenceCreateInfo *,
        XaveriusBackendFence **out_fence);
    XaveriusBackendResult (*reset_fence)(
        XaveriusBackendDevice *, XaveriusBackendFence *);
    XaveriusBackendResult (*destroy_fence)(
        XaveriusBackendDevice *, XaveriusBackendFence *);
};
```

The types shown above are opaque server/DDX backend boundary types. Their payload fields MUST be defined by the corresponding request chapter's validated semantic data, not copied wire structs. Implementations MUST NOT cast raw wire buffers to these structures.

### 3.1 Top-level operation table completion

The top-level `XaveriusDeviceBackendOps` retains the following operations in addition to the four typed tables:

- `query_physical_snapshot`;
- `create_logical_device`, `get_queue`, `destroy_logical_device`;
- `queue_submit`;
- `create_surface`, `destroy_surface`, `query_surface_support`;
- `create_presentation_route`, `destroy_presentation_route`;
- `create_swapchain`, `destroy_swapchain`, `acquire_next_image`, `queue_present`, `cancel_acquire`, `release_late_acquired_image`;
- operation retirement (`retire_operation`); DDX module-role retain/release/quiescence hooks are supplied only by the separate `XaveriusModuleRoleDescriptor`, not by the per-device operation table.

Surface capability query MUST be one call for the exact logical Device and DDX-native Surface and MUST return one internally consistent immutable result containing every v0.1 capability exposed by the reply or used to validate the client-selected Swapchain fields: supported format/color-space pairs, present modes, image-count/range constraints, image-usage bits, extent constraints, and one support entry for every queue family in that logical Device's PhysicalDevice snapshot. The operation therefore receives XaveriusBackendDevice, not merely XaveriusDeviceBackendBinding, and MUST NOT be called once per queue family to assemble a potentially inconsistent aggregate. XaveriusBackendSurfaceSupport is a server-owned output value: any variable-length list storage and queue-family array are allocated/provided by the server with explicit capacities; the DDX fills the values and counts in one call and MUST NOT return or retain pointers to DDX-owned storage. A count exceeding a supplied capacity is a FATAL DDX contract violation. It MUST NOT return only a boolean support flag when the wire reply exposes these details. v0.1 has no wire fields or client selectors for image transforms or composite-alpha modes; these are not required fields of the DDX backend/server capability result. If the native backend requires them, the DDX binding MUST select compatible supported values internally during Swapchain creation and MUST NOT expose native enum values or invent client-visible capability fields. If no compatible internal choice exists, the exact Device/Surface pair is not presentable.

Presentation route create/destroy and swapchain create/destroy are separate operations. A route is keyed by exact logical Device, Surface, Window and Screen generations. A swapchain retains its route; destroying the route while a swapchain or accepted acquire/present operation references it is BUSY. A DDX backend may use one internal helper for route and swapchain construction, but it MUST preserve the separate ownership and rollback boundaries.

Before calling `create_presentation_route`, the server presentation subsystem reserves a fresh nonzero route generation that is never reused, including when route creation later fails. The server passes that generation as `server_route_generation`; the DDX MUST store it in the returned opaque route wrapper and MUST NOT allocate, replace, or recycle it. The route metadata output contains the exact retained Screen generation, selected scanout-device generation (zero when none), and private route kind; it does not assign route identity. A successful `create_presentation_route` binds the returned route wrapper to the exact `XaveriusBackendDevice`, server-assigned route generation, and binding generation passed/resolved for that call. The route wrapper MUST retain one `XaveriusBackendDevice` wrapper reference using `retain_device` until `destroy_presentation_route` has completed native route destruction; it MUST release that reference exactly once afterward. `destroy_presentation_route(binding, route)` MUST use only the owner Device stored in that route wrapper and MUST reject/quarantine any binding-generation mismatch; it MUST NOT accept a route created for another logical Device. The server MUST keep the exact logical Device and binding alive until route destruction completes. A successful `create_swapchain` similarly binds the returned swapchain wrapper to its exact Device and route; the wrapper MUST retain whatever Device/route references are required for `destroy_swapchain` to complete safely, and release them exactly once after native swapchain destruction. `destroy_swapchain` MUST complete before `destroy_presentation_route` is invoked. A failed create rolls back only objects/references created by that attempt, in reverse dependency order.

### 3.2 Input, output, and object-reference rules

These rules apply to all four typed tables and to the top-level operations listed in Section 3.1.

- The server initializes every output before calling the DDX: pointer outputs to NULL, scalar outputs and value structures to zero, and every caller-provided output-array slot to NULL. The DDX MUST NOT read an output parameter before writing it.
- On SUCCESS, each object-producing operation returns a complete object and transfers exactly one owned wrapper reference to the server. The server records that reference before publishing the corresponding XAverius resource. For `allocate_descriptor_sets`, the caller supplies an array of exactly `set_count` writable slots; success fills every slot with one distinct non-NULL owned set reference. There is no partial-success count. On any non-success result, every slot remains NULL and no set from the batch remains allocated or externally reachable.
- `get_queue` is the exception to object-reference transfer: each returned queue handle is borrowed from the successful logical Device and remains valid only while that exact logical Device wrapper is retained and not yet destroyed. It MUST NOT be independently released or destroyed.
- A successful typed destroy/free operation consumes the server's one owned wrapper reference only after the native destruction has completed successfully. A non-success destroy/free result MUST NOT be treated as consumption or permit reference release. Because the v0.1 destroy contract has no BUSY/PENDING retry result, the server MUST quarantine the object and retain its binding/module references after a failed or uncertain destroy; it MUST NOT call the same destroy hook again unless a later version explicitly defines idempotent retry semantics.
- `free_descriptor_sets` is one atomic batch operation over the supplied exact pool and set wrappers: SUCCESS consumes every listed set exactly once; failure consumes none. The server validates pool ownership and set uniqueness before entry. `update_descriptor_sets` likewise commits the complete validated update list or none of it.
- `destroy_descriptor_pool` and `destroy_command_pool` are parent-cascade operations. On SUCCESS, each consumes the parent wrapper and every still-live child wrapper owned by that pool (DescriptorSet or CommandBuffer, respectively); the server invalidates the corresponding child XIDs in the same cascade and MUST NOT call the child free hook again for those children. Children explicitly freed earlier are not consumed twice. The server MUST drain pending/recording references before invoking the parent destroy. On non-success, neither the parent nor any child wrapper is considered consumed; uncertain partial native destruction requires quarantine of the entire affected parent/child family.
- Value outputs such as memory requirements, physical snapshots, route metadata, and surface support contain no DDX-owned pointers. The DDX MUST fully initialize them on SUCCESS. On non-success they remain zeroed and contain no partial capability/snapshot data.
- All input descriptions and arrays are borrowed and immutable for the duration of a synchronous call. The DDX MUST copy any data it needs after return. For an asynchronous operation, the DDX MUST copy every needed input value and retain its backend-object references before returning SUCCESS; it MUST NOT retain pointers to request descriptions, caller arrays, output storage, or the call-scoped operation-token pointer. It copies only the token ID/generation into callback state.
- A failed create operation leaves no partially initialized object visible to the server. The DDX rolls back partial native creation before returning, or—if rollback itself cannot be proven safe—returns FATAL so the server quarantines the owning module role. The server never publishes an XID or wrapper for a failed create.

## 4. Operation classification and completion

Exactly these six operations use the asynchronous operation-token protocol:

1. `write_buffer`
2. `read_buffer`
3. `host_signal_semaphore`
4. `queue_submit`
5. `acquire_next_image`
6. `queue_present`

All other backend operations in this document are synchronous from the request handler's perspective. A synchronous operation MUST NOT retain its input description or output pointer after return, except for ownership explicitly transferred by a successful create operation. A synchronous operation MUST NOT emit a completion callback.

For asynchronous operations, the prepared token pins the exact DDX module-role generation, binding generation, PhysicalDevice incarnation, logical Device generation, and complete resource-generation set. The DDX backend copies only token ID and generation into its own asynchronous callback state; it MUST NOT retain the temporary token pointer. The DDX binding MUST call the server-exported `XaveriusBackendCompletionDispatch` exactly once after accepted work reaches a terminal backend outcome. Dispatch copies the payload into the per-token capacity reserved during preparation before returning and serializes state publication through the server queue. For v0.1, `READ_BUFFER` has a completion payload capacity exactly equal to the validated requested byte count, and `ACQUIRE_NEXT_IMAGE` has a fixed four-byte CARD32 image-index payload capacity. A successful completion MUST return exactly the corresponding payload; the acquired image index MUST be within the Swapchain's image_count. The other four asynchronous operation kinds have zero payload capacity and MUST return NULL/zero payload. Any non-success completion MUST have NULL/zero payload. A size/pointer/capacity mismatch is a FATAL DDX contract violation; dispatch MUST NOT partially copy the payload.

The token resource sets are minimum requirements:

| Operation | Required pinned resources |
|---|---|
| WriteBuffer / ReadBuffer | Buffer and its bound Memory, plus exact logical Device and DDX backend binding |
| Host SignalSemaphore | Semaphore, exact logical Device and DDX backend binding |
| QueueSubmit | Queue and every validated CommandBuffer, Pipeline, PipelineLayout, DescriptorPool/Set/Layout, Buffer, Memory, Semaphore, Fence and other backend object reachable from the validated submission graph |
| AcquireNextImage | Swapchain, Surface/route objects, image-state storage, acquire semaphore/fence if supplied, and every backend object touched by backend acquisition |
| QueuePresent | Queue, Swapchain/image, Surface/route, wait semaphores and every backend object touched by presentation |

If the server cannot build and pin the complete resource set atomically, it MUST reject before DDX backend entry. Duplicate resource identities in one token are invalid in the internal pin set and MUST be deduplicated before refcount changes; conflicting generations for the same identity reject atomically.

## 5. Destroy and deferred-retirement coverage

Every DDX backend-created persistent object has exactly one typed destruction operation:

| DDX backend object | Matching destroy operation |
|---|---|
| Logical Device | `destroy_logical_device` |
| Buffer | `buffer_memory.free_buffer` |
| Memory | `buffer_memory.free_memory` |
| Shader Module | `shader_pipeline.destroy_shader_module` |
| Descriptor Set Layout | `shader_pipeline.destroy_descriptor_set_layout` |
| Descriptor Pool | `shader_pipeline.destroy_descriptor_pool` |
| Descriptor Set | `shader_pipeline.free_descriptor_sets` (pool-owned; no independent native destroy) |
| Pipeline Layout | `shader_pipeline.destroy_pipeline_layout` |
| Compute Pipeline | `shader_pipeline.destroy_compute_pipeline` |
| Command Pool | `commands.destroy_command_pool` |
| Command Buffer | `commands.free_command_buffer`; allocated by `commands.allocate_command_buffer` and owned by its pool |
| Semaphore | `synchronization.destroy_semaphore` |
| Fence | `synchronization.destroy_fence` |
| DDX backend Surface | `destroy_surface` |
| Presentation Route | `destroy_presentation_route` |
| Swapchain | `destroy_swapchain` |

**Corrections required for the API sketch:** add `free_buffer` to `XaveriusBackendBufferMemoryOps`; the earlier sketch listed `create_buffer` but omitted matching destruction. Also add `allocate_command_buffer` and `free_command_buffer` to `XaveriusBackendCommandOps`: the first `CommandBufferData` chunk creates a command-buffer object in the server model, but the previous DDX backend table had no operation to allocate its native counterpart. `DestroyResource` for a Buffer MUST dispatch to `free_buffer`; it MUST NOT call memory-free or infer destruction from unbinding. Command-buffer native allocation MUST occur exactly once when the server allocates the logical command-buffer object, and native free MUST occur only after it is no longer pending and all backend references have retired.

DDX backend object destruction is synchronous only with respect to the DDX binding's native destroy call. If native destruction cannot yet occur because accepted work or callbacks retain the object, the server MUST defer the call until those references retire. A destroy hook MUST NOT silently queue untracked destruction and return SUCCESS. For this v0.1 interface, the server MUST invoke a typed destroy hook only after all server-known dependencies and backend accesses have drained. The hook MUST perform the native destruction before returning SUCCESS. `XaveriusBackendResult` defines no generic BUSY or PENDING result for destroy hooks; if destruction fails or safe completion cannot be established, the server MUST quarantine the object and retain its binding/module-role references. It MUST NOT invent a retry status or release the wrapper/module references.

## 6. Errors and result mapping

| DDX backend result | Synchronous request behavior | Asynchronous acceptance/completion behavior |
|---|---|---|
| SUCCESS | Commit server state/output | On entry: accept token; on completion: publish terminal success |
| UNSUPPORTED | Legal only if capability was not advertised; otherwise DDX backend contract violation | Same; after acceptance, cannot retroactively reject |
| STATUS | NOT_READY: acquire_next_image only; OUT_OF_DATE: create_presentation_route, create_swapchain, acquire_next_image, queue_present; SURFACE_LOST: create_surface, query_surface_support, create_presentation_route, create_swapchain, acquire_next_image, queue_present; DEVICE_UNAVAILABLE: create_surface, query_surface_support, create_presentation_route, create_swapchain, acquire_next_image, and immediate pre-acceptance queue_present; ALREADY_COMPLETED: cancel_acquire only | Completion status is terminal and mapped by that operation's chapter. DEVICE_UNAVAILABLE is allowed only before protocol acceptance and does not change PhysicalDevice/module-role availability |
| UNAVAILABLE | Map using exact module-role-wide or PhysicalDevice-binding scope and request-specific error/status | If before acceptance, reject; if accepted, terminal completion/state path |
| DEVICE_LOST | Request-specific DEVICE_LOST error/status; does not imply PhysicalDevice removal | Terminal completion marks exact logical Device lost per queue/presentation rules |
| OUT_OF_HOST_MEMORY / OUT_OF_DEVICE_MEMORY | ALLOCATION_FAILED for allocation/create requests; otherwise INTERNAL_SERVER_ERROR unless chapter defines another mapping | Completion failure uses operation-specific terminal event/state |
| TRANSFER_FAILURE | TRANSFER_FAILED where request defines synchronous transfer failure | Terminal transfer reply outcome |
| EXECUTION_FAILURE | INTERNAL_SERVER_ERROR for a synchronous operation not defined to execute work | Accepted queue/present work uses terminal event/status, never delayed X11 error |
| CANCELLED | Invalid as a generic synchronous result unless operation explicitly defines it | Valid only as terminal outcome of an accepted cancellable operation |
| FATAL | Quarantine DDX module-role generation; no normal quiesce/finalize hooks | Quarantine; preserve token/resource/module pins and suppress unsafe callback-driven re-entry |

Every DDX backend result structure MUST obey its field invariants from Section 7.1. An operation-specific STATUS value not defined for that operation is FATAL. A result with contradictory fields (for example, nonzero status_code when code is not STATUS, or a non-NONE unavailable_scope for another code) is FATAL.

## 7. Conformance additions

The architecture conformance suite MUST cover:

- **151 — Table completeness:** all four typed tables have every operation required by the enabled v0.1 profile; missing advertised entries reject DDX backend registration.
- **152 — Request mapping completeness:** every assigned request 0–47 maps to DDX backend work or explicitly server-only work; no request handler invents an unlisted DDX backend entry.
- **153 — Create/destroy symmetry:** every persistent backend object has exactly one matching typed destruction path; Buffer creation cannot register without `free_buffer`; command-buffer creation cannot register without `allocate_command_buffer` and `free_command_buffer`.
- **154 — Async classification:** exactly six operations use tokens; all other operations reject/forbid completion callbacks.
- **155 — Output initialization and rollback:** every synchronous failure leaves outputs initialized and no partially published backend object.
- **156 — Descriptor and batch atomicity:** descriptor allocation/update either commits the whole validated batch or exposes no partial result.
- **157 — Command-stream boundary:** DDX backend sees only validated typed command entries in order, never raw wire bytes or client XIDs.
- **158 — Surface capability completeness:** returned support data covers every capability field exposed in the reply and used for Swapchain validation.
- **159 — Full resource pin set:** QueueSubmit and presentation tokens retain every backend-accessible resource generation.
- **160 — Result-field invariants:** malformed combinations of DDX backend result code/status/availability fields quarantine the DDX backend.
- **161 — DestroyResource dispatch:** resource type selects exactly the matching typed destroy operation; no generic untyped destroy fallback.
- **162 — Server-only request isolation:** QueryVersion, snapshot queries, host waits, status queries and SelectEvents do not call DDX backend code directly.

- **163 — Command-buffer native allocation:** first logical CommandBuffer allocation creates exactly one DDX backend command buffer from the exact pool; failure rolls back XID and pool child-list insertion.
- **164 — Command-buffer native free:** pool destruction and command-buffer invalidation free each native command buffer exactly once, only after pending submissions and all backend references retire; no free occurs for a reused XID's replacement generation.
- **165 — Logical Surface independence:** CreateSurface performs no DDX backend call and succeeds for a valid drawable Window even when no DDX backend can present to it; it captures the exact Window/Screen generation without selecting a Device or DDX backend.
- **166 — DDX-native Surface scope:** one DDX-native Surface wrapper is associated with the exact (selected binding generation, logical Surface generation) pair, is reusable across logical Devices using that same binding, and is never shared across binding generations, even when they belong to the same module role.
- **167 — Lazy materialization and unsupported mapping:** the first Device-specific capability query or swapchain creation materializes the DDX-native Surface once; concurrent first use cannot duplicate it; UNSUPPORTED produces a valid no-present-support capability result with every queue-family support bit clear, while direct CreateSwapchain returns UNSUPPORTED_CONFIGURATION without publishing its target XID.
- **168 — Surface retirement:** DestroySurface retires every materialized DDX-native Surface for the exact logical generation after in-flight queries/routes/swapchains drain; deferred or failed destruction keeps DDX backend/module references pinned and blocks quiescence.
- **169 — Capability ABI exactness:** the DDX backend result covers every v0.1 wire capability and every client-selected Swapchain constraint; it does not require nonexistent transform/composite-alpha wire fields, and any backend-required values are selected internally without exposing native enums.
- **170 — Binding-generation Surface teardown:** removal of one selected binding retires only that binding generation's native Surface wrappers after their users drain, leaves the connection-owned logical Surface live, and never transfers an existing Device or wrapper to another binding generation.

- **171 — Presentation wrapper parent lifetime:** create a route for logical Device A and a Surface, then create a Swapchain from it. Verify the server allocates and passes a fresh non-reusable route generation, the DDX stores but does not choose that generation, and the route retains the exact backend Device wrapper and binding generation until route destruction, the Swapchain retains its exact route/Device dependencies until swapchain destruction, and destruction order is Swapchain before route before logical Device. Attempt to destroy the route while a Swapchain or accepted acquire/present token still references it and require BUSY at the server lifecycle layer without invoking native route destruction. Attempt cross-Device or cross-binding route destruction and require rejection without releasing the original references.
- **172 — Route-scoped temporary unavailability:** Make the exact Device/Surface route temporarily unavailable during create_surface, query_surface_support, create_presentation_route, create_swapchain, and pre-acceptance acquire/present. The DDX returns STATUS/DEVICE_UNAVAILABLE; the server maps the request status without changing the PhysicalDevice or module-role availability. Then make an already accepted QueuePresent lose its route and verify it terminalizes through the accepted presentation failure channel, not a retroactive request status or a PhysicalDevice-unavailable transition.
- **173 — Provisional registration snapshot failure scope:** During XaveriusRegistryRegisterDdxDevice, make query_physical_snapshot return UNAVAILABLE/PHYSICAL_DEVICE for the exact provisional binding generation. Verify that generation was reserved before the query, the registration fails without installing a binding or publishing an XID, and no existing selected binding/PhysicalDevice status changes. Separately return UNAVAILABLE/MODULE_ROLE and verify that only already-selected bindings retaining that exact role generation transition to UNAVAILABLE.
- **174 — Four-table output and ownership contract:** Exercise every object-producing table operation with success and injected failure. Verify pointer/scalar/value outputs are initialized, descriptor-set arrays are all-or-nothing, queue handles are borrowed from the logical Device, every successful create transfers exactly one wrapper reference, and every successful typed destroy/free consumes it exactly once. Inject partial native batch failure and require rollback or module-role quarantine without partial publication.
- **175 — Pool cascade ownership:** Create multiple native CommandBuffers and DescriptorSets under their exact pools, free a subset individually, then destroy each pool. Verify the parent destroy consumes the pool and every remaining child wrapper exactly once, the server invalidates all corresponding child XIDs atomically, already-freed children are not freed twice, and a pending/recording dependency rejects the destroy before backend entry. Inject uncertain partial native pool destruction and require quarantine of the entire affected family.
- **176 — Exact logical-Device surface query:** Create two logical Devices through the same selected PhysicalDevice binding, with different logical queue selections. For each GetSurfaceCapabilities call, verify exactly one query_surface_support invocation receives that request's exact XaveriusBackendDevice wrapper and returns a single coherent result covering every queue family. No per-family repeated query may assemble the result, and no route or support result from the other logical Device may be reused.
- **177 — Operation-specific status applicability:** For every top-level presentation operation, inject each defined STATUS code and verify only the documented operation/status pairs are accepted: NOT_READY only for acquire; OUT_OF_DATE only for route/swapchain creation, acquire, and present; SURFACE_LOST only for surface creation/query, route/swapchain creation, acquire, and present; DEVICE_UNAVAILABLE only for route/surface operations and pre-acceptance acquire/present; ALREADY_COMPLETED only for cancel_acquire. Every operation-inapplicable status is FATAL and quarantines the owning module role.
