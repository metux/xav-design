# Provider operation matrix and typed interface contract

**Status:** Normative supplement to Sections 4, 4.1, 4.1.1, and 7 of [device-registry-architecture.md](device-registry-architecture.md). This document closes the abstract provider-table declarations. It does not define a client ABI and changes no request subopcode, wire field, event ID, or Vulkan capability.

If a summary table in Section 4.1 differs from this matrix, this document governs the provider/server boundary. The request chapters remain authoritative for validation order, observable state, and client-visible error/status behavior.

## 1. Common operation contract

Every provider operation MUST be reached only after the server has completed the request-specific validation required by the normative request chapter. Provider functions MUST NOT parse XAverius wire data, resolve client XIDs, select a PhysicalDevice, choose a queue family, or make client-visible state transitions.

Every synchronous provider operation returns a fully initialized `GpuProviderResult`. Every output parameter MUST be initialized to its failure sentinel before any backend call. On any non-success result, object outputs are NULL, scalar outputs are zero, and output arrays are empty unless that operation explicitly defines a non-error STATUS result. The provider MUST NOT expose a partially created object. It MUST roll back partial backend creation or retain it privately for safe cleanup.

For synchronous operations, `GPU_PROVIDER_SUCCESS` means the requested backend action completed sufficiently for the request handler to commit its server-side state transition. It does not mean that unrelated queued GPU work completed.

For the six asynchronous operations (WriteBuffer, ReadBuffer, host SignalSemaphore, QueueSubmit, AcquireNextImage, QueuePresent), `GPU_PROVIDER_SUCCESS` means **accepted** and requires exactly one eventual completion for the prepared token. It does not mean completion. Any other immediate result means not accepted and requires the matching token rejection path; the provider MUST NOT later access resources or emit a completion for it. A provider that has performed backend access or emitted a completion and then returns non-success violates the contract and is quarantined.

`GPU_PROVIDER_UNSUPPORTED` is legal only for an operation/capability not advertised by the selected provider. If a previously advertised operation returns UNSUPPORTED, this is a provider-contract violation and is handled as FATAL/INTERNAL_SERVER_ERROR, not client BadMatch.

The registry owns all resource validation, generation checks, dependency pinning, operation-token allocation, public XID state, and request ordering. Provider-local handles MUST remain private behind typed opaque wrappers. The provider MUST validate exact provider-local binding ID plus registry binding generation whenever an operation resolves a PhysicalDevice binding.

## 1.1 DDX binding is the direct dispatch target

In the Xlibre/Xorg integration profile, the DDX registers each PhysicalDevice it serves and binds the applicable immutable operation tables, per-device context, and native physical-device handle to that device's registry binding. The selected PhysicalDevice binding is the direct dispatch target for every operation in this matrix. The server MUST NOT perform an additional BackendProvider-object lookup between resolving the PhysicalDevice/logical Device and invoking the typed operation.

The legacy `GpuBackendProvider`/provider-generation terminology in the internal API sketch refers only to a shared DDX module-role lifetime/control record (module lease, callback admission, and quiescence). It is not a per-device backend instance and is not a dispatch proxy. Operation arguments MUST identify the exact device binding and binding generation; the provider/module-role generation is additional lifetime provenance only. Per-device native handles and context remain on the binding. See [ddx-device-registration.md](../implementation-notes/ddx-device-registration.md).

## 2. Complete request-to-provider mapping

| Subopcode | Request | Provider operation(s) | Provider involvement |
|---:|---|---|---|
| 0 | QueryVersion | None | Entirely server-side |
| 1 | EnumeratePhysicalDevices | `enumerate_candidates` during discovery only | No per-request provider call; reply from registry snapshot |
| 2 | GetPhysicalDeviceProperty | None | Snapshot lookup |
| 3 | GetPhysicalDeviceQueueFamilyProperties | None | Snapshot lookup |
| 4 | CreateDevice | `create_logical_device`, `get_queue` for each requested queue | Synchronous create; rollback all queues/device if any step fails |
| 5 | CreateDefaultDevice | Same as CreateDevice | Server selects exact PhysicalDevice/provider first |
| 6 | DestroyDevice | `destroy_logical_device` after dependent backend objects/work retire | Server validates and cascades; backend teardown may be deferred |
| 7 | GetPhysicalDeviceMemoryProperties | None | Snapshot lookup |
| 8 | CreateBuffer | `buffer_memory.create_buffer` | Synchronous create |
| 9 | GetBufferMemoryRequirements | `buffer_memory.get_buffer_memory_requirements` | Synchronous query; no persistent provider object |
| 10 | AllocateMemory | `buffer_memory.allocate_memory` | Synchronous create |
| 11 | FreeMemory | `buffer_memory.free_memory` | Synchronous backend free after server proves no binding/work references |
| 12 | BindBufferMemory | `buffer_memory.bind_buffer_memory` | Synchronous bind; server commits binding only after success |
| 13 | WriteBuffer | `buffer_memory.write_buffer` | Async token; reply after completion/visibility boundary |
| 14 | ReadBuffer | `buffer_memory.read_buffer` | Async token; completion payload copied by sink for reply |
| 15 | ShaderModuleData | `shader_pipeline.create_shader_module` only on validated final-chunk commit; abort/chunk append have no provider call | Server owns assembly |
| 16 | CreateDescriptorSetLayout | `shader_pipeline.create_descriptor_set_layout` | Synchronous create |
| 17 | CreateDescriptorPool | `shader_pipeline.create_descriptor_pool` | Synchronous create |
| 18 | DestroyDescriptorPool | `shader_pipeline.destroy_descriptor_pool` | Synchronous backend destroy after server proves children/dependencies can be invalidated |
| 19 | AllocateDescriptorSets | `shader_pipeline.allocate_descriptor_sets` | Atomic batch create; no partial set publication |
| 20 | UpdateDescriptorSets | `shader_pipeline.update_descriptor_sets` | Atomic batch update; provider receives validated immutable update list |
| 21 | FreeDescriptorSets | `shader_pipeline.free_descriptor_sets` | Synchronous free after server lifetime checks |
| 22 | CreatePipelineLayout | `shader_pipeline.create_pipeline_layout` | Synchronous create |
| 23 | CreateComputePipeline | `shader_pipeline.create_compute_pipeline` | Synchronous create |
| 24 | CreateCommandPool | `commands.create_command_pool` | Synchronous create |
| 25 | DestroyCommandPool | `commands.destroy_command_pool` | Synchronous destroy after server has validated/inactivated children |
| 26 | ResetCommandBuffer | `commands.reset_command_buffer` | Synchronous reset |
| 27 | CommandBufferData | `commands.begin_command_buffer`, `commands.record_commands`, `commands.end_command_buffer` at the validated commit boundary; abort/chunk transport is server-only | Server assembles and validates stream before backend recording |
| 28 | QueueSubmit | top-level `queue_submit` | Async token; provider receives complete validated dependency graph |
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
| 39 | DestroyResource | One typed destroy operation selected by validated resource type: buffer, shader module, descriptor-set layout, pipeline layout, compute pipeline | Server owns type/ownership/dependency validation and XID invalidation; provider performs only the typed backend destroy |
| 40 | SelectEvents | None | Entirely server-side |
| 41 | CreateSurface | None | Creates only the connection-owned logical Surface and retains the exact Window/Screen identity; no Device/provider is selected by this request |
| 42 | DestroySurface | `destroy_surface` once for each successfully materialized provider-native Surface associated with this exact logical Surface generation | Server invalidates the logical XID atomically; native cleanup follows after all Swapchain/route/query references drain |
| 43 | GetSurfaceCapabilities | Ensure/create the provider-native Surface for the exact provider generation if not already materialized, then `query_surface_support` | Synchronous query for exact binding, queue family, logical Surface and selected logical Device; returns formats, present modes, limits and support |
| 44 | CreateSwapchain | Ensure/create the provider-native Surface for the exact provider generation if not already materialized, then `create_presentation_route`, `create_swapchain` | Synchronous create; route is exact logical-Device/Surface/Screen generation |
| 45 | DestroySwapchain | `destroy_swapchain` | Synchronous backend retirement after server proves all blockers drained |
| 46 | AcquireNextImage | `acquire_next_image`; `cancel_acquire` and `release_late_acquired_image` only for the specified timeout/cancellation race | Async token; server arbitrates timeout and late acquisition |
| 47 | QueuePresent | `queue_present` | Async token; server arbitrates accepted completion and presentation events |

A server-side request may still depend on state published by earlier provider completions. "None" above means no provider entry point is called by that request itself.

### 2.1 Command entries

Command-buffer entries are not X11 requests and MUST NOT become independent provider entry points unless a future architecture revision explicitly requires it. The v0.1 validated command stream is passed to `record_commands` as typed, host-endian server structures:

- `CMD_BIND_PIPELINE`
- `CMD_BIND_DESCRIPTOR_SETS`
- `CMD_DISPATCH`
- `CMD_PUSH_CONSTANTS`
- `CMD_COPY_BUFFER_TO_SWAPCHAIN_IMAGE` (presentation profile only)

The provider MUST receive no unvalidated wire bytes, client pointers, XIDs, or unpinned resource references. The server has already resolved every referenced object to a retained provider object and generation. Recording order MUST match the validated command stream exactly.

### 2.2 Logical Surface and provider-native Surface lifetime

The XAverius Surface created by request 41 is a server-owned, connection-owned logical resource. It captures the exact Window and Screen generations but has no Device, PhysicalDevice, provider, or Vulkan-instance association. Request 41 MUST NOT call any provider operation. A valid drawable Window therefore remains a valid XAverius Surface even when no currently registered provider can present to it.

A provider-native Surface is a separate provider-owned object. It is materialized lazily when a Device-specific operation first needs it: GetSurfaceCapabilities, or CreateSwapchain when the client did not query capabilities first. The server resolves the exact logical Device to its already selected provider generation and asks that provider to create the native Surface from the captured Window/Screen identity. It MUST NOT select a provider from the Screen, from registration order, or from another Device.

The server maintains at most one live provider-native Surface wrapper for each pair (provider generation, logical Surface resource generation). The wrapper is provider-context scoped, not PhysicalDevice-binding or logical-Device scoped, and may be reused by different Devices/bindings served by that same provider generation. It MUST NOT be shared across provider generations. A provider that internally requires more than one native object may keep those objects behind the one opaque wrapper. The wrapper retains the exact logical Window/Screen identity and provider/module references for its lifetime.

Provider-native Surface creation and publication are serialized per logical Surface/provider-generation pair. Concurrent first-use queries MUST NOT create duplicate wrappers. A failed create publishes no wrapper. If create_surface returns UNSUPPORTED, the server may cache an explicit unsupported result for that pair; it MUST NOT create a fake native handle or repeatedly call the provider for the same unchanged generations. For GetSurfaceCapabilities, this condition produces SUCCESS with present_supported = 0, empty format and present-mode lists, zero non-queue-family capability fields, and one queue-family record per Device queue family with present_supported = 0. This is a valid Device/Surface pair, not DEVICE_UNAVAILABLE or SURFACE_LOST. For CreateSwapchain, the same condition produces UNSUPPORTED_CONFIGURATION and leaves the target Swapchain XID unallocated; no route or swapchain provider operation is called. A cached unsupported result is reused for both requests. A later new provider generation or new Surface generation is evaluated independently.

DestroySurface invalidates the logical Surface XID only after its ordinary type/ownership/Swapchain checks succeed. It then retires every successfully materialized provider-native Surface wrapper for that exact Surface generation. No wrapper may be destroyed twice or used by a later Surface generation that reuses the XID. Native destruction may be deferred until in-flight capability queries and other provider calls release their temporary references; provider shutdown/quiescence MUST wait for these wrappers to be destroyed or safely quarantined. An unsupported-result cache entry contains no provider object and needs no native destroy call. Provider-generation shutdown MUST also retire every provider-native Surface wrapper owned by that generation once its Swapchain/route/query users have drained, even if the logical Surface remains live. This removes only that provider-generation cache entry; it MUST NOT invalidate the logical Surface or trigger provider failover for an existing logical Device. A later Device using another eligible provider generation may materialize its own wrapper for the same logical Surface.

The provider operation matrix in [provider-operation-matrix.md](provider-operation-matrix.md) defines the corresponding request mapping. This rule does not change the wire layout or the logical Surface ownership model.

## 3. Required typed operation-table declarations

The following declarations are semantic C-interface guidance. Exact C type names may be adapted, but every listed operation and its sync/async classification is mandatory. The currently forward-declared four table types MUST NOT remain opaque in an implementation-facing API specification.

All `*_INFO` inputs are immutable, fully validated server-owned descriptions. All returned provider objects are opaque provider wrappers with one owned reference transferred to the caller on SUCCESS. The server MUST release that reference through the corresponding typed destroy/release path exactly once.

```c
struct GpuProviderBufferMemoryOps {
    GpuProviderResult (*create_buffer)(
        GpuProviderDevice *, const GpuBufferCreateInfo *,
        GpuProviderBuffer **out_buffer);
    GpuProviderResult (*free_buffer)(
        GpuProviderDevice *, GpuProviderBuffer *);
    GpuProviderResult (*get_buffer_memory_requirements)(
        GpuProviderDevice *, GpuProviderBuffer *,
        GpuBufferMemoryRequirements *out_requirements);
    GpuProviderResult (*allocate_memory)(
        GpuProviderDevice *, const GpuMemoryAllocateInfo *,
        GpuProviderMemory **out_memory);
    GpuProviderResult (*free_memory)(
        GpuProviderDevice *, GpuProviderMemory *);
    GpuProviderResult (*bind_buffer_memory)(
        GpuProviderDevice *, GpuProviderBuffer *,
        GpuProviderMemory *, uint64_t offset);
    GpuProviderResult (*write_buffer)(
        GpuProviderDevice *, GpuProviderBuffer *, GpuProviderMemory *,
        const GpuBufferTransferInfo *, GpuProviderOperationToken *);
    GpuProviderResult (*read_buffer)(
        GpuProviderDevice *, GpuProviderBuffer *, GpuProviderMemory *,
        const GpuBufferTransferInfo *, GpuProviderOperationToken *);
};

struct GpuProviderShaderPipelineOps {
    GpuProviderResult (*create_shader_module)(
        GpuProviderDevice *, const GpuShaderModuleCreateInfo *,
        GpuProviderShaderModule **out_shader);
    GpuProviderResult (*create_descriptor_set_layout)(
        GpuProviderDevice *, const GpuDescriptorSetLayoutCreateInfo *,
        GpuProviderDescriptorSetLayout **out_layout);
    GpuProviderResult (*create_descriptor_pool)(
        GpuProviderDevice *, const GpuDescriptorPoolCreateInfo *,
        GpuProviderDescriptorPool **out_pool);
    GpuProviderResult (*allocate_descriptor_sets)(
        GpuProviderDevice *, GpuProviderDescriptorPool *,
        const GpuDescriptorSetAllocateInfo *, uint32_t set_count,
        GpuProviderDescriptorSet **out_sets);
    GpuProviderResult (*update_descriptor_sets)(
        GpuProviderDevice *, const GpuDescriptorUpdateInfo *,
        uint32_t update_count);
    GpuProviderResult (*free_descriptor_sets)(
        GpuProviderDevice *, GpuProviderDescriptorPool *,
        GpuProviderDescriptorSet *const *sets, uint32_t set_count);
    GpuProviderResult (*create_pipeline_layout)(
        GpuProviderDevice *, const GpuPipelineLayoutCreateInfo *,
        GpuProviderPipelineLayout **out_layout);
    GpuProviderResult (*create_compute_pipeline)(
        GpuProviderDevice *, const GpuComputePipelineCreateInfo *,
        GpuProviderPipeline **out_pipeline);
    GpuProviderResult (*destroy_shader_module)(GpuProviderDevice *, GpuProviderShaderModule *);
    GpuProviderResult (*destroy_descriptor_set_layout)(GpuProviderDevice *, GpuProviderDescriptorSetLayout *);
    GpuProviderResult (*destroy_descriptor_pool)(GpuProviderDevice *, GpuProviderDescriptorPool *);
    GpuProviderResult (*destroy_pipeline_layout)(GpuProviderDevice *, GpuProviderPipelineLayout *);
    GpuProviderResult (*destroy_compute_pipeline)(GpuProviderDevice *, GpuProviderPipeline *);
};

struct GpuProviderCommandOps {
    GpuProviderResult (*create_command_pool)(
        GpuProviderDevice *, const GpuCommandPoolCreateInfo *,
        GpuProviderCommandPool **out_pool);
    GpuProviderResult (*destroy_command_pool)(
        GpuProviderDevice *, GpuProviderCommandPool *);
    GpuProviderResult (*allocate_command_buffer)(
        GpuProviderDevice *, GpuProviderCommandPool *,
        const GpuCommandBufferAllocateInfo *,
        GpuProviderCommandBuffer **out_command_buffer);
    GpuProviderResult (*free_command_buffer)(
        GpuProviderDevice *, GpuProviderCommandPool *,
        GpuProviderCommandBuffer *);
    GpuProviderResult (*reset_command_buffer)(
        GpuProviderDevice *, GpuProviderCommandBuffer *);
    GpuProviderResult (*begin_command_buffer)(
        GpuProviderDevice *, GpuProviderCommandBuffer *,
        const GpuCommandBufferBeginInfo *);
    GpuProviderResult (*record_commands)(
        GpuProviderDevice *, GpuProviderCommandBuffer *,
        const GpuValidatedCommand *, uint32_t command_count);
    GpuProviderResult (*end_command_buffer)(
        GpuProviderDevice *, GpuProviderCommandBuffer *);
};

struct GpuProviderSynchronizationOps {
    GpuProviderResult (*create_semaphore)(
        GpuProviderDevice *, const GpuSemaphoreCreateInfo *,
        GpuProviderSemaphore **out_semaphore);
    GpuProviderResult (*host_signal_semaphore)(
        GpuProviderDevice *, GpuProviderSemaphore *, uint64_t value,
        GpuProviderOperationToken *);
    GpuProviderResult (*destroy_semaphore)(
        GpuProviderDevice *, GpuProviderSemaphore *);
    GpuProviderResult (*create_fence)(
        GpuProviderDevice *, const GpuFenceCreateInfo *,
        GpuProviderFence **out_fence);
    GpuProviderResult (*reset_fence)(
        GpuProviderDevice *, GpuProviderFence *);
    GpuProviderResult (*destroy_fence)(
        GpuProviderDevice *, GpuProviderFence *);
};
```

The types shown above are opaque server/provider boundary types. Their payload fields MUST be defined by the corresponding request chapter's validated semantic data, not copied wire structs. Implementations MUST NOT cast raw wire buffers to these structures.

### 3.1 Top-level operation table completion

The top-level `GpuProviderOps` retains the following operations in addition to the four typed tables:

- `enumerate_candidates`, `release_candidate_list`, `query_physical_snapshot`;
- `create_logical_device`, `get_queue`, `destroy_logical_device`;
- `queue_submit`;
- `create_surface`, `destroy_surface`, `query_surface_support`;
- `create_presentation_route`, `destroy_presentation_route`;
- `create_swapchain`, `destroy_swapchain`, `acquire_next_image`, `queue_present`, `cancel_acquire`, `release_late_acquired_image`;
- provider/module lifetime hooks, operation retirement and provider quiescence.

Surface capability query MUST return one internally consistent immutable result containing every v0.1 capability exposed by the reply or used to validate the client-selected Swapchain fields: supported format/color-space pairs, present modes, image-count/range constraints, image-usage bits, extent constraints, and per-queue-family support. It MUST NOT return only a boolean support flag when the wire reply exposes these details. v0.1 has no wire fields or client selectors for image transforms or composite-alpha modes; these are not required fields of the provider/server capability result. If the native backend requires them, the provider MUST select compatible supported values internally during Swapchain creation and MUST NOT expose native enum values or invent client-visible capability fields. If no compatible internal choice exists, the exact Device/Surface pair is not presentable.

Presentation route create/destroy and swapchain create/destroy are separate operations. A route is keyed by exact logical Device, Surface, Window and Screen generations. A swapchain retains its route; destroying the route while a swapchain or accepted acquire/present operation references it is BUSY. A provider may use one internal helper for route and swapchain construction, but it MUST preserve the separate ownership and rollback boundaries.

## 4. Operation classification and completion

Exactly these six operations use the asynchronous operation-token protocol:

1. `write_buffer`
2. `read_buffer`
3. `host_signal_semaphore`
4. `queue_submit`
5. `acquire_next_image`
6. `queue_present`

All other provider operations in this document are synchronous from the request handler's perspective. A synchronous operation MUST NOT retain its input description or output pointer after return, except for ownership explicitly transferred by a successful create operation. A synchronous operation MUST NOT emit a completion callback.

For asynchronous operations, the prepared token pins the exact provider generation, binding generation, PhysicalDevice incarnation, logical Device generation, and complete resource-generation set. The provider copies only token ID and generation into asynchronous callback userdata; it MUST NOT retain the temporary token pointer. The provider MUST invoke the completion sink exactly once after accepted work reaches a terminal backend outcome. The server completion sink copies payload before returning and serializes state publication.

The token resource sets are minimum requirements:

| Operation | Required pinned resources |
|---|---|
| WriteBuffer / ReadBuffer | Buffer and its bound Memory, plus exact logical Device and provider binding |
| Host SignalSemaphore | Semaphore, exact logical Device and provider binding |
| QueueSubmit | Queue and every validated CommandBuffer, Pipeline, PipelineLayout, DescriptorPool/Set/Layout, Buffer, Memory, Semaphore, Fence and other backend object reachable from the validated submission graph |
| AcquireNextImage | Swapchain, Surface/route objects, image-state storage, acquire semaphore/fence if supplied, and every provider object touched by backend acquisition |
| QueuePresent | Queue, Swapchain/image, Surface/route, wait semaphores and every provider object touched by presentation |

If the server cannot build and pin the complete resource set atomically, it MUST reject before provider entry. Duplicate resource identities in one token are invalid in the internal pin set and MUST be deduplicated before refcount changes; conflicting generations for the same identity reject atomically.

## 5. Destroy and deferred-retirement coverage

Every provider-created persistent object has exactly one typed destruction operation:

| Provider object | Matching destroy operation |
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
| Provider Surface | `destroy_surface` |
| Presentation Route | `destroy_presentation_route` |
| Swapchain | `destroy_swapchain` |

**Corrections required for the API sketch:** add `free_buffer` to `GpuProviderBufferMemoryOps`; the earlier sketch listed `create_buffer` but omitted matching destruction. Also add `allocate_command_buffer` and `free_command_buffer` to `GpuProviderCommandOps`: the first `CommandBufferData` chunk creates a command-buffer object in the server model, but the previous provider table had no operation to allocate its native counterpart. `DestroyResource` for a Buffer MUST dispatch to `free_buffer`; it MUST NOT call memory-free or infer destruction from unbinding. Command-buffer native allocation MUST occur exactly once when the server allocates the logical command-buffer object, and native free MUST occur only after it is no longer pending and all backend references have retired.

Provider object destruction is synchronous only with respect to the provider's native destroy call. If native destruction cannot yet occur because accepted work or callbacks retain the object, the server MUST defer the call until those references retire. A destroy hook MUST NOT silently queue untracked destruction and return SUCCESS unless the provider object wrapper itself remains retained and the hook's contract explicitly reports the deferred state. For this v0.1 interface, typed destroy hooks return SUCCESS only after the native object is no longer usable; otherwise return BUSY/PENDING only where the request path supports retry/deferred retirement, and keep the wrapper/module references pinned.

## 6. Errors and result mapping

| Provider result | Synchronous request behavior | Asynchronous acceptance/completion behavior |
|---|---|---|
| SUCCESS | Commit server state/output | On entry: accept token; on completion: publish terminal success |
| UNSUPPORTED | Legal only if capability was not advertised; otherwise provider contract violation | Same; after acceptance, cannot retroactively reject |
| STATUS | Legal only for operations defining a status (for example acquire NOT_READY, present OUT_OF_DATE/SURFACE_LOST) | Completion status is terminal and mapped by that operation's chapter |
| UNAVAILABLE | Map using exact provider-context or binding scope and request-specific error/status | If before acceptance, reject; if accepted, terminal completion/state path |
| DEVICE_LOST | Request-specific DEVICE_LOST error/status; does not imply PhysicalDevice removal | Terminal completion marks exact logical Device lost per queue/presentation rules |
| OUT_OF_HOST_MEMORY / OUT_OF_DEVICE_MEMORY | ALLOCATION_FAILED for allocation/create requests; otherwise INTERNAL_SERVER_ERROR unless chapter defines another mapping | Completion failure uses operation-specific terminal event/state |
| TRANSFER_FAILURE | TRANSFER_FAILED where request defines synchronous transfer failure | Terminal transfer reply outcome |
| EXECUTION_FAILURE | INTERNAL_SERVER_ERROR for a synchronous operation not defined to execute work | Accepted queue/present work uses terminal event/status, never delayed X11 error |
| CANCELLED | Invalid as a generic synchronous result unless operation explicitly defines it | Valid only as terminal outcome of an accepted cancellable operation |
| FATAL | Quarantine provider generation; no normal quiesce/finalize hooks | Quarantine; preserve token/resource/module pins and suppress unsafe callback-driven re-entry |

Every provider result structure MUST obey its field invariants from Section 7.1. An operation-specific STATUS value not defined for that operation is FATAL. A result with contradictory fields (for example, nonzero status_code when code is not STATUS, or a non-NONE unavailable_scope for another code) is FATAL.

## 7. Conformance additions

The architecture conformance suite MUST cover:

- **151 — Table completeness:** all four typed tables have every operation required by the enabled v0.1 profile; missing advertised entries reject provider registration.
- **152 — Request mapping completeness:** every assigned request 0–47 maps to provider work or explicitly server-only work; no request handler invents an unlisted provider entry.
- **153 — Create/destroy symmetry:** every persistent provider object has exactly one matching typed destruction path; Buffer creation cannot register without `free_buffer`; command-buffer creation cannot register without `allocate_command_buffer` and `free_command_buffer`.
- **154 — Async classification:** exactly six operations use tokens; all other operations reject/forbid completion callbacks.
- **155 — Output initialization and rollback:** every synchronous failure leaves outputs initialized and no partially published provider object.
- **156 — Descriptor and batch atomicity:** descriptor allocation/update either commits the whole validated batch or exposes no partial result.
- **157 — Command-stream boundary:** provider sees only validated typed command entries in order, never raw wire bytes or client XIDs.
- **158 — Surface capability completeness:** returned support data covers every capability field exposed in the reply and used for Swapchain validation.
- **159 — Full resource pin set:** QueueSubmit and presentation tokens retain every backend-accessible resource generation.
- **160 — Result-field invariants:** malformed combinations of provider result code/status/availability fields quarantine the provider.
- **161 — DestroyResource dispatch:** resource type selects exactly the matching typed destroy operation; no generic untyped destroy fallback.
- **162 — Server-only request isolation:** QueryVersion, snapshot queries, host waits, status queries and SelectEvents do not call provider code directly.

- **163 — Command-buffer native allocation:** first logical CommandBuffer allocation creates exactly one provider command buffer from the exact pool; failure rolls back XID and pool child-list insertion.
- **164 — Command-buffer native free:** pool destruction and command-buffer invalidation free each native command buffer exactly once, only after pending submissions and all backend references retire; no free occurs for a reused XID's replacement generation.
- **165 — Logical Surface independence:** CreateSurface performs no provider call and succeeds for a valid drawable Window even when no provider can present to it; it captures the exact Window/Screen generation without selecting a Device or provider.
- **166 — Provider-native Surface scope:** one provider-native Surface wrapper is associated with the exact (provider generation, logical Surface generation) pair, is reusable across Devices/bindings served by that provider, and is never shared across provider generations.
- **167 — Lazy materialization and unsupported mapping:** the first Device-specific capability query or swapchain creation materializes the provider-native Surface once; concurrent first use cannot duplicate it; UNSUPPORTED produces a valid no-present-support capability result with every queue-family support bit clear, while direct CreateSwapchain returns UNSUPPORTED_CONFIGURATION without publishing its target XID.
- **168 — Surface retirement:** DestroySurface retires every materialized provider-native Surface for the exact logical generation after in-flight queries/routes/swapchains drain; deferred or failed destruction keeps provider/module references pinned and blocks quiescence.
- **169 — Capability ABI exactness:** the provider result covers every v0.1 wire capability and every client-selected Swapchain constraint; it does not require nonexistent transform/composite-alpha wire fields, and any backend-required values are selected internally without exposing native enums.
- **170 — Provider-generation Surface teardown:** provider shutdown retires only that generation's native Surface wrappers after their users drain, leaves the connection-owned logical Surface live, and never transfers an existing Device or wrapper to another provider generation.
