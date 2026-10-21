# XAverius v0.1 request subopcode registry

Status: **39 defined requests assigned; registry remains open for future requests and is not a v0.1 freeze**.

This file is the central inventory and numeric assignment for XAverius extension requests. It records only requests already named and described in the current specification chapters. The assignments do not imply that the wire protocol is frozen.

## Rules

- Every listed name denotes one XAverius request opcode unless explicitly noted otherwise.
- Subopcode values are explicit protocol identifiers; clients and servers MUST use the values in this table and MUST NOT infer values from row order, chapter order, or Vulkan enum values.
- Value `0` is reserved and MUST NOT identify a request. Values `1` through `39` are assigned below. Existing assignments are stable and MUST NOT be renumbered; future requests use unused values.
- `Void` means a successful request has no normal reply; request validation errors still use the standard X11 error mechanism.
- `Reply` means the request returns a normal X11 reply. A reply may carry a status rather than reporting that condition as an X11 error.
- `Void + async events` means no normal reply; later outcomes are reported through the specified events and synchronization state.
- Event names are XGE event types, not request subopcodes. `CMD_*` names are command-buffer entries, not X11 requests, and are outside this register.
- Event-selection requests are not listed: their request layouts are not yet specified. Add them only when their wire request definitions exist.
- The responsible chapter defines the request semantics and payload. Generic framing and common error framing remain defined in [wire protocol](../spec/wire-protocol.md).

## Request inventory

| Request | Subopcode | Kind | Responsibility |
|---|---|---|---|
| `EnumeratePhysicalDevices` | 1 | Reply | Enumerate server-visible physical devices and return `PHYSICALDEVICEINFO` records. [Devices](../spec/devices.md) |
| `GetPhysicalDeviceProperty` | 2 | Reply | Query one registered physical-device property by Atom. [Devices](../spec/devices.md) |
| `GetPhysicalDeviceQueueFamilyProperties` | 3 | Reply | Query queue-family capabilities for a physical device. [Devices](../spec/devices.md) |
| `CreateDevice` | 4 | Void | Create a client-owned logical device on an explicitly selected physical device with requested queues, features, and extensions. [Devices](../spec/devices.md) |
| `CreateDefaultDevice` | 5 | Void | Let the server select a suitable physical device and create a logical device with requested queue count. [Devices](../spec/devices.md) |
| `DestroyDevice` | 6 | Void | Destroy a logical device and invalidate its public resource XIDs according to device teardown rules. [Devices](../spec/devices.md), [lifetime](../spec/resource-lifetime.md) |
| `GetPhysicalDeviceMemoryProperties` | 7 | Reply | Return physical-device memory types and heaps. [Memory and buffers](../spec/memory-buffers.md) |
| `CreateBuffer` | 8 | Void | Create a buffer resource with size and usage flags. [Memory and buffers](../spec/memory-buffers.md) |
| `GetBufferMemoryRequirements` | 9 | Reply | Return buffer allocation size, alignment, and compatible memory-type bits. [Memory and buffers](../spec/memory-buffers.md) |
| `AllocateMemory` | 10 | Void | Allocate device memory. [Memory and buffers](../spec/memory-buffers.md) |
| `FreeMemory` | 11 | Void | Free a memory allocation only after all bound buffers are destroyed and no accepted work uses it. [Memory and buffers](../spec/memory-buffers.md), [lifetime](../spec/resource-lifetime.md) |
| `BindBufferMemory` | 12 | Void | Bind an allocation and offset to a buffer. [Memory and buffers](../spec/memory-buffers.md) |
| `WriteBuffer` | 13 | Reply | Upload bytes to a buffer; successful reply establishes the specified device-scoped ordering and visibility boundary. [Memory and buffers](../spec/memory-buffers.md) |
| `ReadBuffer` | 14 | Reply | Read buffer bytes after required earlier work and visibility operations. [Memory and buffers](../spec/memory-buffers.md) |
| `ShaderModuleData` | 15 | Void | Create a shader module through chunked SPIR-V upload, finalization, or abort. [Shaders and pipelines](../spec/shaders-pipelines.md) |
| `CreateDescriptorSetLayout` | 16 | Void | Create a descriptor-set layout from binding records. [Shaders and pipelines](../spec/shaders-pipelines.md) |
| `CreateDescriptorPool` | 17 | Void | Create a descriptor pool with set and descriptor capacity. [Shaders and pipelines](../spec/shaders-pipelines.md) |
| `DestroyDescriptorPool` | 18 | Void | Destroy a descriptor pool and atomically invalidate its child sets when lifetime rules permit. [Shaders and pipelines](../spec/shaders-pipelines.md), [lifetime](../spec/resource-lifetime.md) |
| `AllocateDescriptorSets` | 19 | Void | Atomically allocate descriptor sets from a pool using supplied layouts. [Shaders and pipelines](../spec/shaders-pipelines.md) |
| `UpdateDescriptorSets` | 20 | Void | Atomically update descriptor slots, currently for supported buffer descriptors. [Shaders and pipelines](../spec/shaders-pipelines.md) |
| `FreeDescriptorSets` | 21 | Void | Free selected descriptor sets from their pool subject to lifetime rules. [Shaders and pipelines](../spec/shaders-pipelines.md), [lifetime](../spec/resource-lifetime.md) |
| `CreatePipelineLayout` | 22 | Void | Create a pipeline layout from descriptor-set layouts and push-constant ranges. [Shaders and pipelines](../spec/shaders-pipelines.md) |
| `CreateComputePipeline` | 23 | Void | Create a compute pipeline from a shader module and pipeline layout. [Shaders and pipelines](../spec/shaders-pipelines.md) |
| `CreateCommandPool` | 24 | Void | Create a command pool for a queue family, including v0.1 pool flags. [Command recording](../spec/command-recording.md) |
| `DestroyCommandPool` | 25 | Void | Destroy a command pool and atomically invalidate its child command buffers when permitted. [Command recording](../spec/command-recording.md), [lifetime](../spec/resource-lifetime.md) |
| `ResetCommandBuffer` | 26 | Void | Reset an eligible non-pending command buffer to `INITIAL`, subject to its pool flag. [Command recording](../spec/command-recording.md) |
| `CommandBufferData` | 27 | Void | Create, append to, finalize, or abort a chunked command-buffer recording. [Command recording](../spec/command-recording.md) |
| `QueueSubmit` | 28 | Void + async events | Atomically validate and accept queue work, correlated by the client-supplied submission token; terminal outcome is asynchronous. [Queue submission](../spec/queue-submission.md), [events](../spec/events.md) |
| `CreateSemaphore` | 29 | Void | Create a binary or timeline semaphore. [Synchronization](../spec/synchronization.md) |
| `GetSemaphoreCounterValue` | 30 | Reply | Query a timeline semaphore counter. [Synchronization](../spec/synchronization.md) |
| `WaitSemaphores` | 31 | Reply | Host-wait for timeline semaphore values with WAIT_ANY/WAIT_ALL and timeout status. [Synchronization](../spec/synchronization.md) |
| `SignalSemaphore` | 32 | Void | Host-signal a timeline semaphore with request-ordering guarantees. [Synchronization](../spec/synchronization.md) |
| `DestroySemaphore` | 33 | Void | Destroy a semaphore subject to pending queue/host-operation lifetime rules. [Synchronization](../spec/synchronization.md), [lifetime](../spec/resource-lifetime.md) |
| `CreateFence` | 34 | Void | Create an unsignaled fence. [Synchronization](../spec/synchronization.md) |
| `GetFenceStatus` | 35 | Reply | Query the fence state. [Synchronization](../spec/synchronization.md) |
| `WaitForFence` | 36 | Reply | Wait for a fence with timeout and execution/device-loss status. [Synchronization](../spec/synchronization.md) |
| `ResetFence` | 37 | Void | Reset a signaled or failed fence to unsignaled. [Synchronization](../spec/synchronization.md) |
| `DestroyFence` | 38 | Void | Destroy a non-pending fence. [Synchronization](../spec/synchronization.md), [lifetime](../spec/resource-lifetime.md) |
| `DestroyResource` | 39 | Void | Generic destroy for Buffer, Shader Module, Descriptor Set Layout, Pipeline Layout, and Pipeline; synchronization objects use dedicated destroy requests. [Resource lifetime](../spec/resource-lifetime.md) |
| `SelectEvents` | 40 | Void | Replace one connection, device, or queue event mask. [Events](../spec/events.md) |

## Allocation work still required

The currently defined inventory has explicit assignments 1–40. New request definitions MUST be assigned an unused value; existing values MUST NOT be moved to make room for later requests. The registry is not a frozen v0.1 ABI; additions must still follow the stable, append-only allocation rule.

Separate numeric namespaces MUST NOT be conflated with request subopcodes. Registries already defined are [descriptor types](descriptor-types.md), [shader stages](shader-stages.md), [device types](device-types.md), [queue flags](queue-flags.md), and [XAverius error codes](errors.md). Registries already defined include [command-buffer entry IDs](command-entries.md) and [event types plus event-local values](event-types.md). Registries still requiring completion include feature IDs and property identifiers. The server-assigned XGE event base remains a separate open issue. Event types are XGE event types, not request subopcodes.
