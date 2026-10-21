# Request catalogue and wire-contract audit — 2026-10-21

## Scope

This audit compares the currently defined request inventory in [the central request subopcode registry](../registries/request-subopcodes.md) with the defining chapters for wire layout, exact or formula-based request length, request kind, common framing, and request-specific error behavior. It is a cross-chapter consistency review, not a claim of complete Vulkan conformance or a frozen v0.1 protocol.

## Inventory result

- The registry contains 40 currently defined requests.
- Every registered request has a defining specification chapter.
- The registry's Reply, Void, and Void + async-events classifications agree with the chapter descriptions for the 40 registered requests.
- The common X11 framing rules specify an 8-byte request header, four-byte request-length units, zero padding, no BIG-REQUESTS in v0.1, and standard 32-byte X11 replies/errors.
- The second systematic pass found several cross-chapter discrepancies and underspecified reply fields. These are recorded below and corrected in follow-up commits; the earlier pass must not be read as a claim that every contract was already consistent.

## Cross-chapter correction made during this audit

An outdated sentence in `DECISIONS.md` incorrectly included Fence and Semaphore in the eligible targets for `DestroyResource`. The normative lifetime chapter, error mapping, conformance cases, and request registry consistently exclude those types and require `DestroyFence` and `DestroySemaphore`. The decision log now matches the normative rule. The project status next steps were also refreshed to remove an obsolete BIG-REQUESTS/64-KiB reconciliation task.

## Known exclusions and unresolved items
1. `SelectEvents` is included as subopcode 40. Its wire layout, scope semantics, XGE negotiation prerequisite, and event framing are specified; final ABI verification remains.
2. The v0.1 feature-ID and device-extension registries are explicitly empty, and the physical-device property/Atom-name registry defines four properties. Their basic error mapping and conformance cases are now covered.
3. Queue scheduling guarantees across independent queues and implementation-level backend conformance remain open as listed in [open issues](open-issues.md). Timeout semantics for `WaitSemaphores` and `WaitForFence` now define monotonic deadlines, zero/infinite timeout behavior, terminal-state precedence, and device-loss handling. The v0.1 wait-stage mapping, queue-family compatibility rules, and invalid-mask error precedence are also explicit in [queue submission](queue-submission.md), [synchronization](synchronization.md), [error mapping](errors.md), and the conformance checklist.
## Subopcode allocation policy

The 40 requests in the central registry are assigned explicit values 1 through 40. Value 0 is reserved and MUST NOT identify a request. These numbers are stable: later requests MUST use an unused value and MUST NOT renumber an existing request. `SelectEvents` uses the next unused value, 40; assignments 1 through 39 were not changed.


## Second systematic pass: findings

The following items were identified by comparing the request inventory, defining chapters, central error rules, and conformance checklist:

1. **Descriptor support cross-check:** the current descriptor registry and conformance contract both correctly restrict v0.1 to `STORAGE_BUFFER`; uniform buffers and image descriptors remain unsupported. No registry change was needed.
2. **Shader-stage symbol mismatch:** the central wire registry names the v0.1 bit `COMPUTE`, while the initial example used `COMPUTE_SHADER`. The example must use the XAverius wire symbol, not a native Vulkan spelling.
3. **Discovery reply completeness:** `EnumeratePhysicalDevices` and `GetPhysicalDeviceQueueFamilyProperties` describe variable reply records but do not explicitly state the corresponding `reply.length` formula. `GetPhysicalDeviceProperty` names statuses without assigning numeric values.
4. **Reply/request contract precision:** the fence-status reply describes the status byte and trailing reserved bytes but leaves the standard reply fields between offsets 2 and 7 implicit. The contract should explicitly separate standard X11 header fields from reserved bytes.
5. **Error-mapping coverage:** several requests rely on the general error chapter without spelling out all Create-XID, field-value, backend-allocation, or status-reply outcomes. The central rules must be applied consistently; no Void request may silently turn a normal status into a reply.
6. **Audit metadata drift:** this audit's earlier registry-completeness statement became stale as registries were added. Its scope and unresolved list must describe the current branch rather than an earlier snapshot.
7. **Create-XID versus input-XID handling:** the general `BadIDChoice` rule was not explicit enough in several pipeline and chunked-create cases, and a few duplicate/count conditions lacked a concrete error. The error chapter now distinguishes target-XID collisions from missing input resources and assigns deterministic errors to the invalid duplicate-entry cases.

These are protocol-documentation corrections, not user-level design changes. Any newly exposed ambiguity that requires choosing new semantics remains an open issue rather than being guessed. The descriptor-type check is a confirmed consistency result, not a defect.


## Per-request contract matrix

The following matrix is the per-request checklist used for the second pass. Lengths are total request bytes, including the 8-byte X11/XAverius header. Variable byte payloads are padded to four bytes; formulas use the counts named by the defining chapter. The registry is authoritative for request kind; chapter links in the central registry identify the authoritative field layouts.

| Subopcode | Request | Kind | Total request length |
|---:|---|---|---|
| 1 | `EnumeratePhysicalDevices` | Reply | 8 |
| 2 | `GetPhysicalDeviceProperty` | Reply | 16 |
| 3 | `GetPhysicalDeviceQueueFamilyProperties` | Reply | 12 |
| 4 | `CreateDevice` | Void | `24 + Σ(8 + 4*queue_count_i) + 8*feature_request_count + Σ(4 + pad4(name_length_j))` |
| 5 | `CreateDefaultDevice` | Void | `16 + 4*queue_count` |
| 6 | `DestroyDevice` | Void | 12 |
| 7 | `GetPhysicalDeviceMemoryProperties` | Reply | 12 |
| 8 | `CreateBuffer` | Void | 32 |
| 9 | `GetBufferMemoryRequirements` | Reply | 16 |
| 10 | `AllocateMemory` | Void | 32 |
| 11 | `FreeMemory` | Void | 16 |
| 12 | `BindBufferMemory` | Void | 28 |
| 13 | `WriteBuffer` | Reply | `28 + pad4(data_length)` |
| 14 | `ReadBuffer` | Reply | 28 |
| 15 | `ShaderModuleData` | Void | `20 + pad4(data_length)`; ABORT has zero data and exactly 20 bytes |
| 16 | `CreateDescriptorSetLayout` | Void | `24 + 16*binding_count` |
| 17 | `CreateDescriptorPool` | Void | `24 + 8*pool_size_count` |
| 18 | `DestroyDescriptorPool` | Void | 16 |
| 19 | `AllocateDescriptorSets` | Void | `20 + 8*descriptor_set_count` |
| 20 | `UpdateDescriptorSets` | Void | `20 + 36*write_count` |
| 21 | `FreeDescriptorSets` | Void | `20 + 4*descriptor_set_count` |
| 22 | `CreatePipelineLayout` | Void | `20 + 4*set_layout_count + 12*push_constant_range_count` |
| 23 | `CreateComputePipeline` | Void | `28 + pad4(entry_point_length)` |
| 24 | `CreateCommandPool` | Void | 24 |
| 25 | `DestroyCommandPool` | Void | 16 |
| 26 | `ResetCommandBuffer` | Void | 16 |
| 27 | `CommandBufferData` | Void | At least 16; ABORT exactly 16; other payloads contain whole entries |
| 28 | `QueueSubmit` | Void + async events | `40 + 4*C + 16*W + 12*S` |
| 29 | `CreateSemaphore` | Void | 28 |
| 30 | `GetSemaphoreCounterValue` | Reply | 16 |
| 31 | `WaitSemaphores` | Reply | `28 + 12*semaphore_count` |
| 32 | `SignalSemaphore` | Void | 24 |
| 33 | `DestroySemaphore` | Void | 16 |
| 34 | `CreateFence` | Void | 24 |
| 35 | `GetFenceStatus` | Reply | 16 |
| 36 | `WaitForFence` | Reply | 24 |
| 37 | `ResetFence` | Void | 16 |
| 38 | `DestroyFence` | Void | 16 |
| 39 | `DestroyResource` | Void | 12 |
| 40 | `SelectEvents` | Void | 32 |

Here `pad4(n) = (n + 3) & ~3`. Every formula must be evaluated with checked arithmetic before allocation or parsing. Counts and the actual packet length must agree exactly; extra trailing bytes are not permitted unless the request definition explicitly includes them.

## Cross-chapter consistency results

- **Request kind:** all 40 inventory kinds agree with the defining chapter; `WriteBuffer` is a Reply request because its successful reply is the upload-completion/visibility boundary. `QueueSubmit` remains Void; post-acceptance outcomes are asynchronous.
- **Reply lengths:** discovery reply formulas and property status values are now explicit; fixed replies use `reply.length = 0` when all data fits in the standard 32-byte reply header. Variable data begins at byte 32 and `reply.length` counts four-byte units after that header.
- **Descriptor/stage values:** v0.1 supports `STORAGE_BUFFER = 1` only and the XAverius stage bit `COMPUTE = 0x00000001`; examples must not substitute native Vulkan enum names.
- **Error mapping:** the central error chapter governs XID liveness, live-type mismatch, ownership, Atom validation, Create-XID choice, validation order, and atomic rejection. Request-specific tables define the specialized state and backend failures. A final ABI review is still required for full implementation readiness. The feature-ID, device-extension, and physical-device-property registries are now defined for v0.1; XGE negotiation and event selection are specified. Timeout behavior and implementation-level backend conformance remain subject to their defining chapters and the open-issues register.

## Event-selection request addition — 2026-10-21

`SelectEvents` is now defined as a 32-byte Void request at subopcode 40. The request atomically replaces the selection for one connection, device, or queue scope; masks are scope-specific and `ASYNC_ERROR`/`DEVICE_LOST` are unmaskable. Conformance coverage was added. This adds one request without changing assignments 1–39.
