# DDX backend operation matrix and typed interface contract

**Status:** Normative supplement to Sections 4, 4.1, 4.1.1, and 7 of [device-registry-architecture.md](device-registry-architecture.md). This document closes the abstract DDX backend-table declarations. It does not define a client ABI and changes no request subopcode, wire field, event ID, or Vulkan capability.

If a summary table in Section 4.1 differs from this matrix, this document governs the DDX backend/server boundary. The request chapters remain authoritative for validation order, observable state, and client-visible error/status behavior.

## 1. Common operation contract

Every backend operation MUST be reached only after the server has completed the request-specific validation required by the normative request chapter. DDX backend functions MUST NOT parse XAverius wire data, resolve client XIDs, select a PhysicalDevice, choose a queue family, or make client-visible state transitions.

Every synchronous backend operation returns a fully initialized `GpuBackendResult`. Every output parameter MUST be initialized to its failure sentinel before any backend call. On any non-success result, object outputs are NULL, scalar outputs are zero, and output arrays are empty unless that operation explicitly defines a non-error STATUS result. The DDX binding MUST NOT expose a partially created object. It MUST roll back partial backend creation or retain it privately for safe cleanup.

For synchronous operations, `GPU_BACKEND_SUCCESS` means the requested backend action completed sufficiently for the request handler to commit its server-side state transition. It does not mean that unrelated queued GPU work completed.

For the six asynchronous operations (WriteBuffer, ReadBuffer, host SignalSemaphore, QueueSubmit, AcquireNextImage, QueuePresent), `GPU_BACKEND_SUCCESS` means **accepted** and requires exactly one eventual completion for the prepared token. It does not mean completion. Any other immediate result means not accepted and requires the matching token rejection path; the DDX binding MUST NOT later access resources or emit a completion for it. A DDX backend that has performed backend access or emitted a completion and then returns non-success violates the contract and is quarantined.

`GPU_BACKEND_UNSUPPORTED` is legal only for an operation/capability not advertised by the selected DDX binding. If a previously advertised operation returns UNSUPPORTED, this is a DDX backend-contract violation and is handled as FATAL/INTERNAL_SERVER_ERROR, not client BadMatch.

The registry owns all resource validation, generation checks, dependency pinning, operation-token allocation, public XID state, and request ordering. DDX backend-local handles MUST remain private behind typed opaque wrappers. The DDX binding MUST validate exact DDX-local binding ID plus registry binding generation whenever an operation resolves a PhysicalDevice binding.

## 1.1 DDX binding is the direct dispatch target

In the Xlibre/Xorg integration profile, the DDX registers each PhysicalDevice it serves and binds the applicable immutable operation tables, per-device context, and native physical-device handle to that device's registry binding. The selected PhysicalDevice binding is the direct dispatch target for every operation in this matrix. The server MUST NOT perform an additional GpuModuleRole-object lookup between resolving the PhysicalDevice/logical Device and invoking the typed operation.

The legacy `GpuGpuModuleRole`/DDX backend-generation terminology in the internal API sketch refers only to a shared DDX module-role lifetime/control record (module lease, callback admission, and quiescence). It is not a per-device backend instance and is not a dispatch proxy. Operation arguments MUST identify the exact device binding and binding generation; the DDX backend/module-role generation is additional lifetime provenance only. Per-device native handles and context remain on the binding. See [ddx-device-registration.md](../implementation-notes/ddx-device-registration.md).

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
| 43 | GetSurfaceCapabilities | Ensure/create the DDX-native Surface for the exact DDX module-role generation if not already materialized, then `query_surface_support` | Synchronous query for exact binding, queue family, logical Surface and selected logical Device; returns formats, present modes, limits and support |
| 44 | CreateSwapchain | Ensure/create the DDX-native Surface for the exact DDX module-role generation if not already materialized, then `create_presentation_route`, `create_swapchain` | Synchronous create; route is exact logical-Device/Surface/Screen generation |
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

A DDX-native Surface is a separate DDX backend-owned object. It is materialized lazily when a Device-specific operation first needs it: GetSurfaceCapabilities, or CreateSwapchain when the client did not query capabilities first. The server resolves the exact logical Device to its already selected DDX module-role generation and asks that DDX backend to create the native Surface from the captured Window/Screen identity. It MUST NOT select a DDX backend from the Screen, from registration order, or from another Device.

The server maintains at most one live DDX-native Surface wrapper for each pair (DDX module-role generation, logical Surface resource generation). The wrapper is DDX backend-context scoped, not PhysicalDevice-binding or logical-Device scoped, and may be reused by different Devices/bindings served by that same DDX module-role generation. It MUST NOT be shared across DDX module-role generations. A DDX backend that internally requires more than one native object may keep those objects behind the one opaque wrapper. The wrapper retains the exact logical Window/Screen identity and DDX backend/module references for its lifetime.

DDX backend-native Surface creation and publication are serialized per logical Surface/DDX backend-generation pair. Concurrent first-use queries MUST NOT create duplicate wrappers. A failed create publishes no wrapper. If create_surface returns UNSUPPORTED, the server may cache an explicit unsupported result for that pair; it MUST NOT create a fake native handle or repeatedly call the DDX backend for the same unchanged generations. For GetSurfaceCapabilities, this condition produces SUCCESS with present_supported = 0, empty format and present-mode lists, zero non-queue-family capability fields, and one queue-family record per Device queue family with present_supported = 0. This is a valid Device/Surface pair, not DEVICE_UNAVAILABLE or SURFACE_LOST. For CreateSwapchain, the same condition produces UNSUPPORTED_CONFIGURATION and leaves the target Swapchain XID unallocated; no route or swapchain backend operation is called. A cached unsupported result is reused for both requests. A later new DDX module-role generation or new Surface generation is evaluated independently.

DestroySurface invalidates the logical Surface XID only after its ordinary type/ownership/Swapchain checks succeed. It then retires every successfully materialized DDX-native Surface wrapper for that exact Surface generation. No wrapper may be destroyed twice or used by a later Surface generation that reuses the XID. Native destruction may be deferred until in-flight capability queries and other DDX backend calls release their temporary references; DDX backend shutdown/quiescence MUST wait for these wrappers to be destroyed or safely quarantined. An unsupported-result cache entry contains no backend object and needs no native destroy call. DDX backend-generation shutdown MUST also retire every DDX-native Surface wrapper owned by that generation once its Swapchain/route/query users have drained, even if the logical Surface remains live. This removes only that DDX backend-generation cache entry; it MUST NOT invalidate the logical Surface or trigger DDX backend failover for an existing logical Device. A later Device using another eligible DDX module-role generation may materialize its own wrapper for the same logical Surface.

The backend operation matrix in [DDX backend-operation-matrix.md](DDX backend-operation-matrix.md) defines the corresponding request mapping. This rule does not change the wire layout or the logical Surface ownership model.

## 3. Required typed operation-table declarations

The following declarations are semantic C-interface guidance. Exact C type names may be adapted, but every listed operation and its sync/async classification is mandatory. The currently forward-declared four table types MUST NOT remain opaque in an implementation-facing API specification.

All `*_INFO` inputs are immutable, fully validated server-owned descriptions. All returned backend objects are opaque DDX backend wrappers with one owned reference transferred to the caller on SUCCESS. The server MUST release that reference through the corresponding typed destroy/release path exactly once.

```c
struct GpuBackendBufferMemoryOps {
    GpuBackendResult (*create_buffer)(
        GpuBackendDevice *, const GpuBufferCreateInfo *,
        GpuBackendBuffer **out_buffer);
    GpuBackendResult (*free_buffer)(
        GpuBackendDevice *, GpuBackendBuffer *);
    GpuBackendResult (*get_buffer_memory_requirements)(
        GpuBackendDevice *, GpuBackendBuffer *,
        GpuBufferMemoryRequirements *out_requirements);
    GpuBackendResult (*allocate_memory)(
        GpuBackendDevice *, const GpuMemoryAllocateInfo *,
        GpuBackendMemory **out_memory);
    GpuBackendResult (*free_memory)(
        GpuBackendDevice *, GpuBackendMemory *);
    GpuBackendResult (*bind_buffer_memory)(
        GpuBackendDevice *, GpuBackendBuffer *,
        GpuBackendMemory *, uint64_t offset);
    GpuBackendResult (*write_buffer)(
        GpuBackendDevice *, GpuBackendBuffer *, GpuBackendMemory *,
        const GpuBufferTransferInfo *, GpuBackendOperationToken *);
    GpuBackendResult (*read_buffer)(
        GpuBackendDevice *, GpuBackendBuffer *, GpuBackendMemory *,
        const GpuBufferTransferInfo *, GpuBackendOperationToken *);
};

struct GpuBackendShaderPipelineOps {
    GpuBackendResult (*create_shader_module)(
        GpuBackendDevice *, const GpuShaderModuleCreateInfo *,
        GpuBackendShaderModule **out_shader);
    GpuBackendResult (*create_descriptor_set_layout)(
        GpuBackendDevice *, const GpuDescriptorSetLayoutCreateInfo *,
        GpuBackendDescriptorSetLayout **out_layout);
    GpuBackendResult (*create_descriptor_pool)(
        GpuBackendDevice *, const GpuDescriptorPoolCreateInfo *,
        GpuBackendDescriptorPool **out_pool);
    GpuBackendResult (*allocate_descriptor_sets)(
        GpuBackendDevice *, GpuBackendDescriptorPool *,
        const GpuDescriptorSetAllocateInfo *, uint32_t set_count,
        GpuBackendDescriptorSet **out_sets);
    GpuBackendResult (*update_descriptor_sets)(
        GpuBackendDevice *, const GpuDescriptorUpdateInfo *,
        uint32_t update_count);
    GpuBackendResult (*free_descriptor_sets)(
        GpuBackendDevice *, GpuBackendDescriptorPool *,
        GpuBackendDescriptorSet *const *sets, uint32_t set_count);
    GpuBackendResult (*create_pipeline_layout)(
        GpuBackendDevice *, const GpuPipelineLayoutCreateInfo *,
        GpuBackendPipelineLayout **out_layout);
    GpuBackendResult (*create_compute_pipeline)(
        GpuBackendDevice *, const GpuComputePipelineCreateInfo *,
        GpuBackendPipeline **out_pipeline);
    GpuBackendResult (*destroy_shader_module)(GpuBackendDevice *, GpuBackendShaderModule *);
    GpuBackendResult (*destroy_descriptor_set_layout)(GpuBackendDevice *, GpuBackendDescriptorSetLayout *);
    GpuBackendResult (*destroy_descriptor_pool)(GpuBackendDevice *, GpuBackendDescriptorPool *);
    GpuBackendResult (*destroy_pipeline_layout)(GpuBackendDevice *, GpuBackendPipelineLayout *);
    GpuBackendResult (*destroy_compute_pipeline)(GpuBackendDevice *, GpuBackendPipeline *);
};

struct GpuBackendCommandOps {
    GpuBackendResult (*create_command_pool)(
        GpuBackendDevice *, const GpuCommandPoolCreateInfo *,
        GpuBackendCommandPool **out_pool);
    GpuBackendResult (*destroy_command_pool)(
        GpuBackendDevice *, GpuBackendCommandPool *);
    GpuBackendResult (*allocate_command_buffer)(
        GpuBackendDevice *, GpuBackendCommandPool *,
        const GpuCommandBufferAllocateInfo *,
        GpuBackendCommandBuffer **out_command_buffer);
    GpuBackendResult (*free_command_buffer)(
        GpuBackendDevice *, GpuBackendCommandPool *,
        GpuBackendCommandBuffer *);
    GpuBackendResult (*reset_command_buffer)(
        GpuBackendDevice *, GpuBackendCommandBuffer *);
    GpuBackendResult (*begin_command_buffer)(
        GpuBackendDevice *, GpuBackendCommandBuffer *,
        const GpuCommandBufferBeginInfo *);
    GpuBackendResult (*record_commands)(
        GpuBackendDevice *, GpuBackendCommandBuffer *,
        const GpuValidatedCommand *, uint32_t command_count);
    GpuBackendResult (*end_command_buffer)(
        GpuBackendDevice *, GpuBackendCommandBuffer *);
};

struct GpuBackendSynchronizationOps {
    GpuBackendResult (*create_semaphore)(
        GpuBackendDevice *, const GpuSemaphoreCreateInfo *,
        GpuBackendSemaphore **out_semaphore);
    GpuBackendResult (*host_signal_semaphore)(
        GpuBackendDevice *, GpuBackendSemaphore *, uint64_t value,
        GpuBackendOperationToken *);
    GpuBackendResult (*destroy_semaphore)(
        GpuBackendDevice *, GpuBackendSemaphore *);
    GpuBackendResult (*create_fence)(
        GpuBackendDevice *, const GpuFenceCreateInfo *,
        GpuBackendFence **out_fence);
    GpuBackendResult (*reset_fence)(
        GpuBackendDevice *, GpuBackendFence *);
    GpuBackendResult (*destroy_fence)(
        GpuBackendDevice *, GpuBackendFence *);
};
```

The types shown above are opaque server/DDX backend boundary types. Their payload fields MUST be defined by the corresponding request chapter's validated semantic data, not copied wire structs. Implementations MUST NOT cast raw wire buffers to these structures.

### 3.1 Top-level operation table completion

The top-level `GpuBackendOps` retains the following operations in addition to the four typed tables:

- `query_physical_snapshot`;
- `create_logical_device`, `get_queue`, `destroy_logical_device`;
- `queue_submit`;
- `create_surface`, `destroy_surface`, `query_surface_support`;
- `create_presentation_route`, `destroy_presentation_route`;
- `create_swapchain`, `destroy_swapchain`, `acquire_next_image`, `queue_present`, `cancel_acquire`, `release_late_acquired_image`;
- DDX backend/module lifetime hooks, operation retirement and DDX backend quiescence.

Surface capability query MUST return one internally consistent immutable result containing every v0.1 capability exposed by the reply or used to validate the client-selected Swapchain fields: supported format/color-space pairs, present modes, image-count/range constraints, image-usage bits, extent constraints, and per-queue-family support. It MUST NOT return only a boolean support flag when the wire reply exposes these details. v0.1 has no wire fields or client selectors for image transforms or composite-alpha modes; these are not required fields of the DDX backend/server capability result. If the native backend requires them, the DDX binding MUST select compatible supported values internally during Swapchain creation and MUST NOT expose native enum values or invent client-visible capability fields. If no compatible internal choice exists, the exact Device/Surface pair is not presentable.

Presentation route create/destroy and swapchain create/destroy are separate operations. A route is keyed by exact logical Device, Surface, Window and Screen generations. A swapchain retains its route; destroying the route while a swapchain or accepted acquire/present operation references it is BUSY. A DDX backend may use one internal helper for route and swapchain construction, but it MUST preserve the separate ownership and rollback boundaries.

## 4. Operation classification and completion

Exactly these six operations use the asynchronous operation-token protocol:

1. `write_buffer`
2. `read_buffer`
3. `host_signal_semaphore`
4. `queue_submit`
5. `acquire_next_image`
6. `queue_present`

All other backend operations in this document are synchronous from the request handler's perspective. A synchronous operation MUST NOT retain its input description or output pointer after return, except for ownership explicitly transferred by a successful create operation. A synchronous operation MUST NOT emit a completion callback.

For asynchronous operations, the prepared token pins the exact DDX module-role generation, binding generation, PhysicalDevice incarnation, logical Device generation, and complete resource-generation set. The DDX backend copies only token ID and generation into asynchronous callback userdata; it MUST NOT retain the temporary token pointer. The DDX binding MUST invoke the completion sink exactly once after accepted work reaches a terminal backend outcome. The server completion sink copies payload before returning and serializes state publication.

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
| Command Pool | `commands.destroy_command_pool` |\n| Command Buffer | `commands.free_command_buffer`; allocated by `commands.allocate_command_buffer` and owned by its pool |
| Semaphore | `synchronization.destroy_semaphore` |
| Fence | `synchronization.destroy_fence` |
| DDX backend Surface | `destroy_surface` |
| Presentation Route | `destroy_presentation_route` |
| Swapchain | `destroy_swapchain` |

**Corrections required for the API sketch:** add `free_buffer` to `GpuBackendBufferMemoryOps`; the earlier sketch listed `create_buffer` but omitted matching destruction. Also add `allocate_command_buffer` and `free_command_buffer` to `GpuBackendCommandOps`: the first `CommandBufferData` chunk creates a command-buffer object in the server model, but the previous DDX backend table had no operation to allocate its native counterpart. `DestroyResource` for a Buffer MUST dispatch to `free_buffer`; it MUST NOT call memory-free or infer destruction from unbinding. Command-buffer native allocation MUST occur exactly once when the server allocates the logical command-buffer object, and native free MUST occur only after it is no longer pending and all backend references have retired.

DDX backend object destruction is synchronous only with respect to the DDX binding's native destroy call. If native destruction cannot yet occur because accepted work or callbacks retain the object, the server MUST defer the call until those references retire. A destroy hook MUST NOT silently queue untracked destruction and return SUCCESS unless the backend object wrapper itself remains retained and the hook's contract explicitly reports the deferred state. For this v0.1 interface, typed destroy hooks return SUCCESS only after the native object is no longer usable; otherwise return BUSY/PENDING only where the request path supports retry/deferred retirement, and keep the wrapper/module references pinned.

## 6. Errors and result mapping

| DDX backend result | Synchronous request behavior | Asynchronous acceptance/completion behavior |
|---|---|---|
| SUCCESS | Commit server state/output | On entry: accept token; on completion: publish terminal success |
| UNSUPPORTED | Legal only if capability was not advertised; otherwise DDX backend contract violation | Same; after acceptance, cannot retroactively reject |
| STATUS | Legal only for operations defining a status (for example acquire NOT_READY, present OUT_OF_DATE/SURFACE_LOST) | Completion status is terminal and mapped by that operation's chapter |
| UNAVAILABLE | Map using exact DDX backend-context or binding scope and request-specific error/status | If before acceptance, reject; if accepted, terminal completion/state path |
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
- **166 — DDX backend-native Surface scope:** one DDX-native Surface wrapper is associated with the exact (DDX module-role generation, logical Surface generation) pair, is reusable across Devices/bindings served by that DDX backend, and is never shared across DDX module-role generations.
- **167 — Lazy materialization and unsupported mapping:** the first Device-specific capability query or swapchain creation materializes the DDX-native Surface once; concurrent first use cannot duplicate it; UNSUPPORTED produces a valid no-present-support capability result with every queue-family support bit clear, while direct CreateSwapchain returns UNSUPPORTED_CONFIGURATION without publishing its target XID.
- **168 — Surface retirement:** DestroySurface retires every materialized DDX-native Surface for the exact logical generation after in-flight queries/routes/swapchains drain; deferred or failed destruction keeps DDX backend/module references pinned and blocks quiescence.
- **169 — Capability ABI exactness:** the DDX backend result covers every v0.1 wire capability and every client-selected Swapchain constraint; it does not require nonexistent transform/composite-alpha wire fields, and any backend-required values are selected internally without exposing native enums.
- **170 — DDX backend-generation Surface teardown:** DDX backend shutdown retires only that generation's native Surface wrappers after their users drain, leaves the connection-owned logical Surface live, and never transfers an existing Device or wrapper to another DDX module-role generation.
