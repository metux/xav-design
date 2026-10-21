# XAverius v0.1 request subopcode registry

Status: **request inventory established; numeric subopcode assignments are not yet allocated**.

This file is the central inventory for XAverius extension requests. It records only requests already named and described in the current specification chapters. It does not assign numeric values or imply that the wire protocol is frozen.

## Rules

- Every listed name denotes one XAverius request opcode unless explicitly noted otherwise.
- `Subopcode` remains **UNASSIGNED** until a reviewed numeric allocation is committed here. Do not infer a value from row order, chapter order, or Vulkan enum values.
- `Void` means a successful request has no normal reply; request validation errors still use the standard X11 error mechanism.
- `Reply` means the request returns a normal X11 reply. A reply may carry a status rather than reporting that condition as an X11 error.
- `Void + async events` means no normal reply; later outcomes are reported through the specified events and synchronization state.
- Event names are XGE event types, not request subopcodes. `CMD_*` names are command-buffer entries, not X11 requests, and are outside this register.
- Event-selection requests are not listed: their request layouts are not yet specified. Add them only when their wire request definitions exist.
- The responsible chapter defines the request semantics and payload. Generic framing and common error framing remain defined in [wire protocol](../spec/wire-protocol.md).

## Request inventory

| Request | Subopcode | Kind | Responsibility |
|---|---|---|---|
| `EnumeratePhysicalDevices` | UNASSIGNED | Reply | Enumerate server-visible physical devices and return `PHYSICALDEVICEINFO` records. [Devices](../spec/devices.md) |
| `GetPhysicalDeviceProperty` | UNASSIGNED | Reply | Query one registered physical-device property by Atom. [Devices](../spec/devices.md) |
| `GetPhysicalDeviceQueueFamilyProperties` | UNASSIGNED | Reply | Query queue-family capabilities for a physical device. [Devices](../spec/devices.md) |
| `CreateDevice` | UNASSIGNED | Void | Create a client-owned logical device on an explicitly selected physical device with requested queues, features, and extensions. [Devices](../spec/devices.md) |
| `CreateDefaultDevice` | UNASSIGNED | Void | Let the server select a suitable physical device and create a logical device with requested queue count. [Devices](../spec/devices.md) |
| `DestroyDevice` | UNASSIGNED | Void | Destroy a logical device and invalidate its public resource XIDs according to device teardown rules. [Devices](../spec/devices.md), [lifetime](../spec/resource-lifetime.md) |
| `GetPhysicalDeviceMemoryProperties` | UNASSIGNED | Reply | Return physical-device memory types and heaps. [Memory and buffers](../spec/memory-buffers.md) |
| `CreateBuffer` | UNASSIGNED | Void | Create a buffer resource with size and usage flags. [Memory and buffers](../spec/memory-buffers.md) |
| `GetBufferMemoryRequirements` | UNASSIGNED | Reply | Return buffer allocation size, alignment, and compatible memory-type bits. [Memory and buffers](../spec/memory-buffers.md) |
| `AllocateMemory` | UNASSIGNED | Void | Allocate device memory. [Memory and buffers](../spec/memory-buffers.md) |
| `FreeMemory` | UNASSIGNED | Void | Free a memory allocation only after all bound buffers are destroyed and no accepted work uses it. [Memory and buffers](../spec/memory-buffers.md), [lifetime](../spec/resource-lifetime.md) |
| `BindBufferMemory` | UNASSIGNED | Void | Bind an allocation and offset to a buffer. [Memory and buffers](../spec/memory-buffers.md) |
| `WriteBuffer` | UNASSIGNED | Reply | Upload bytes to a buffer; successful reply establishes the specified device-scoped ordering and visibility boundary. [Memory and buffers](../spec/memory-buffers.md) |
| `ReadBuffer` | UNASSIGNED | Reply | Read buffer bytes after required earlier work and visibility operations. [Memory and buffers](../spec/memory-buffers.md) |
| `ShaderModuleData` | UNASSIGNED | Void | Create a shader module through chunked SPIR-V upload, finalization, or abort. [Shaders and pipelines](../spec/shaders-pipelines.md) |
| `CreateDescriptorSetLayout` | UNASSIGNED | Void | Create a descriptor-set layout from binding records. [Shaders and pipelines](../spec/shaders-pipelines.md) |
| `CreateDescriptorPool` | UNASSIGNED | Void | Create a descriptor pool with set and descriptor capacity. [Shaders and pipelines](../spec/shaders-pipelines.md) |
| `DestroyDescriptorPool` | UNASSIGNED | Void | Destroy a descriptor pool and atomically invalidate its child sets when lifetime rules permit. [Shaders and pipelines](../spec/shaders-pipelines.md), [lifetime](../spec/resource-lifetime.md) |
| `AllocateDescriptorSets` | UNASSIGNED | Void | Atomically allocate descriptor sets from a pool using supplied layouts. [Shaders and pipelines](../spec/shaders-pipelines.md) |
| `UpdateDescriptorSets` | UNASSIGNED | Void | Atomically update descriptor slots, currently for supported buffer descriptors. [Shaders and pipelines](../spec/shaders-pipelines.md) |
| `FreeDescriptorSets` | UNASSIGNED | Void | Free selected descriptor sets from their pool subject to lifetime rules. [Shaders and pipelines](../spec/shaders-pipelines.md), [lifetime](../spec/resource-lifetime.md) |
| `CreatePipelineLayout` | UNASSIGNED | Void | Create a pipeline layout from descriptor-set layouts and push-constant ranges. [Shaders and pipelines](../spec/shaders-pipelines.md) |
| `CreateComputePipeline` | UNASSIGNED | Void | Create a compute pipeline from a shader module and pipeline layout. [Shaders and pipelines](../spec/shaders-pipelines.md) |
| `CreateCommandPool` | UNASSIGNED | Void | Create a command pool for a queue family, including v0.1 pool flags. [Command recording](../spec/command-recording.md) |
| `DestroyCommandPool` | UNASSIGNED | Void | Destroy a command pool and atomically invalidate its child command buffers when permitted. [Command recording](../spec/command-recording.md), [lifetime](../spec/resource-lifetime.md) |
| `ResetCommandBuffer` | UNASSIGNED | Void | Reset an eligible non-pending command buffer to `INITIAL`, subject to its pool flag. [Command recording](../spec/command-recording.md) |
| `CommandBufferData` | UNASSIGNED | Void | Create, append to, finalize, or abort a chunked command-buffer recording. [Command recording](../spec/command-recording.md) |
| `QueueSubmit` | UNASSIGNED | Void + async events | Atomically validate and accept queue work, correlated by the client-supplied submission token; terminal outcome is asynchronous. [Queue submission](../spec/queue-submission.md), [events](../spec/events.md) |
| `CreateSemaphore` | UNASSIGNED | Void | Create a binary or timeline semaphore. [Synchronization](../spec/synchronization.md) |
| `GetSemaphoreCounterValue` | UNASSIGNED | Reply | Query a timeline semaphore counter. [Synchronization](../spec/synchronization.md) |
| `WaitSemaphores` | UNASSIGNED | Reply | Host-wait for timeline semaphore values with WAIT_ANY/WAIT_ALL and timeout status. [Synchronization](../spec/synchronization.md) |
| `SignalSemaphore` | UNASSIGNED | Void | Host-signal a timeline semaphore with request-ordering guarantees. [Synchronization](../spec/synchronization.md) |
| `DestroySemaphore` | UNASSIGNED | Void | Destroy a semaphore subject to pending queue/host-operation lifetime rules. [Synchronization](../spec/synchronization.md), [lifetime](../spec/resource-lifetime.md) |
| `CreateFence` | UNASSIGNED | Void | Create an unsignaled fence. [Synchronization](../spec/synchronization.md) |
| `GetFenceStatus` | UNASSIGNED | Reply | Query the fence state. [Synchronization](../spec/synchronization.md) |
| `WaitForFence` | UNASSIGNED | Reply | Wait for a fence with timeout and execution/device-loss status. [Synchronization](../spec/synchronization.md) |
| `ResetFence` | UNASSIGNED | Void | Reset a signaled or failed fence to unsignaled. [Synchronization](../spec/synchronization.md) |
| `DestroyFence` | UNASSIGNED | Void | Destroy a non-pending fence. [Synchronization](../spec/synchronization.md), [lifetime](../spec/resource-lifetime.md) |
| `DestroyResource` | UNASSIGNED | Void | Generic destroy for Buffer, Shader Module, Descriptor Set Layout, Pipeline Layout, and Pipeline; synchronization objects use dedicated destroy requests. [Resource lifetime](../spec/resource-lifetime.md) |

## Allocation work still required

The inventory does not resolve the numeric subopcode assignment. Before allocating values, review the request set for completeness and settle a stable allocation policy. Then replace each `UNASSIGNED` cell with an explicitly reviewed value and add a conformance check that rejects duplicate allocations.

Separate registries remain necessary for command-buffer entry IDs, descriptor types, shader stages, feature IDs, device types, queue flags, event types, error codes, and property identifiers. Their numeric namespaces must not be conflated with request subopcodes.
