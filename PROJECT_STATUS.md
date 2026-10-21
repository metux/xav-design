# Project status

**Project:** XAverius — an X11 extension for network-transparent Vulkan access  
**Specification baseline:** consolidated working draft dated 2026-10-20  
**Initial implementation target:** Xvfb, compute-only  
**Status:** Design work in progress; wire protocol and registries are not frozen.

## Working rules

1. The historical WIP is preserved as the reference baseline unless an explicitly dated successor is added.
2. The chapter split is structural; it must not silently change protocol semantics.
3. Track decisions as settled, provisional, or open.
4. Before every edit, reread the current branch and relevant source chapters.
5. Work directly on `docs/restructure-2026-10-21` for this temporary workspace; keep commits topic-focused. Do not update `master` unless explicitly requested.
6. Define common framing, byte order, lengths, and padding centrally.
7. Request descriptions focus on request-specific payload and behavior; do not repeat generic headers.
8. Filenames do not duplicate chapter numbers; the specification index defines chapter order.
9. Do not invent unassigned opcode or registry values.

## Immediate next steps

- Continue centralizing numeric registries that can be derived from already-settled protocol semantics.
- Verify XGE event framing and standard X11 extension-opcode lookup during the ABI review.
- Cross-check the newly registered v0.1 feature/extension/property sets against error mappings and conformance cases.
- Finish the final ABI review of request-specific error coverage and reply layouts; keep adding conformance cases with each protocol decision.

## End-to-end compute-path audit — 2026-10-21

Reviewed the specification path from physical-device discovery through logical-device creation, memory and buffer setup, shader/pipeline and descriptor creation, command recording, queue submission, synchronization, readback, and resource teardown.

The audit found no request-length arithmetic contradiction in the reviewed concrete layouts. It did identify two underspecified cross-chapter contracts, now clarified in [queue submission and ordering](spec/queue-submission.md):

- A submission always has one internal terminal outcome; delivery of its completion/failure event depends on event selection and the connection remaining alive.
- In v0.1, `ReadBuffer` waits for all previously accepted submissions on the same logical device and relevant prior writes to the requested range. A prior failed submission must not be treated as successful; read data is not guaranteed correct if failed work could have modified that range.

The queue-crossing scope of the successful `WriteBuffer` visibility guarantee is now settled as a device-wide ordering boundary and documented in [Memory und Buffers](spec/memory-buffers.md#56-writebuffer), [queue submission and ordering](spec/queue-submission.md), [DECISIONS.md](DECISIONS.md), and the conformance tests. Other implementation blockers remain listed in [open issues](spec/open-issues.md), especially complete error mapping and final wait-stage masks.

This is an internal consistency and compute-workflow audit, not a claim of full Vulkan-spec conformance or a frozen v0.1 wire protocol.

## WriteBuffer visibility decision — 2026-10-21

The former open issue on cross-queue visibility is closed. A successful `WriteBuffer` reply guarantees this order for its logical device:

1. All earlier accepted submissions have reached a terminal outcome.
2. The transfer has completed and required visibility operations have completed.
3. Every later accepted submission on any queue sees the written bytes.

The contract applies to the full written range and does not require client semaphore/barrier operations solely for upload visibility. It is scoped to one logical device, not all devices on a physical GPU. To avoid a dispatcher deadlock, a later `SignalSemaphore` on the same connection may run while `WriteBuffer` waits for earlier work; later `QueueSubmit` requests must remain deferred until the upload completes. A conservative implementation may fully synchronize the device. Device loss or transfer failure must not produce a successful reply. Conformance cases cover these ordering and progress requirements.


## Shader and command-recording wire decisions — 2026-10-21

The working draft now defines the `ShaderModuleData` chunk layout and `CREATE`/`FINAL`/`ABORT` flags, including atomic final creation and cleanup of failed/incomplete assemblies. It also defines fixed `CreateCommandPool`/`DestroyCommandPool` layouts and deterministic recovery from failed `CommandBufferData` chunks: a chunk is atomic, previously accepted chunks remain, and ABORT returns a non-pending recording buffer to `INITIAL`. Conformance cases and request-specific error guidance were added. The `CreateDescriptorSetLayout` fixed header, binding-record layout, zero-flags rule, validation and atomicity are now documented, with conformance cases. The `DestroyResource` request is also scoped to eligible standalone resource types, with dedicated requests retained for device, pools, command buffers, descriptor sets and memory. The binding reset semantics are also fixed in the working draft: `RESET_COMMAND_BUFFER` gates explicit `ResetCommandBuffer`, `TRANSIENT` is only an optimization hint, and chunk-recovery `ABORT` remains independent. Conformance cases cover the allowed states and atomic rejection. These decisions are documented but the v0.1 protocol and registries remain unfrozen.


## Request catalogue and wire-contract audit — 2026-10-21

The current 40-request inventory was cross-checked against the defining chapters for request kind, fixed/formula-based lengths, common framing, and request-specific error rules. An outdated `DestroyResource` scope statement in `DECISIONS.md` was corrected: Fence and Semaphore require their dedicated destroy requests. The audit record is [spec/request-audit.md](spec/request-audit.md). Event selection is now registered as subopcode 40. Feature/extension and property registries have since been defined for the v0.1 baseline. The 40 currently defined requests now have stable subopcode assignments; this does not freeze v0.1.


## Second systematic request-contract audit — 2026-10-21

Rechecked all 39 registered requests against their defining chapter, request kind, total request length, reply framing, and error mapping. Added a 39-row per-request length matrix to [the audit record](spec/request-audit.md) and committed follow-up corrections in separate steps:

- Made the `EnumeratePhysicalDevices` and `GetPhysicalDeviceQueueFamilyProperties` reply-length formulas explicit, and assigned numeric values to `GetPhysicalDeviceProperty` statuses.
- Clarified the standard X11 reply header fields in `GetFenceStatus`.
- Corrected the initial compute example to use XAverius' `COMPUTE` stage symbol; the descriptor registry already consistently limits v0.1 to `STORAGE_BUFFER = 1`.
- Distinguished Create-target XID collisions (`BadIDChoice`) from missing input resources (`BadValue`) for pipeline creation, descriptor-set batch allocation, and chunked shader/command-buffer creation.
- Filled in missing error mappings for invalid queue counts, duplicate queue-family records, duplicate descriptor-pool size types, duplicate descriptor writes, duplicate submission synchronization entries, and duplicate wait semaphore IDs.
- Extended conformance checks for the new reply formulas, statuses, Create-XID rules, and duplicate-entry handling.

The request registry still contains 39 unique assignments (1–39); no existing subopcode was changed. This pass does not resolve the open feature/extension set, property/Atom registry, event-selection wire layouts, wait-stage mapping, or timeout/scheduling semantics. The protocol remains a working draft and `master` was not changed.


## Event selection contract — 2026-10-21

Defined `SelectEvents` as a 32-byte Void request assigned subopcode 40. It atomically replaces the mask for one connection, device, or queue scope; masks and unused fields are validated per scope, and failures preserve the previous selection. `ASYNC_ERROR` and `DEVICE_LOST` remain unmaskable. Event delivery failure or connection closure does not alter the internal terminal result of a submission or block backend cleanup. The event chapter, request registry, request audit, open-issues list, and conformance tests were updated in separate commits. Remaining event-related work is final ABI verification of XGE framing and standard extension-opcode lookup.


## XGE long-event prerequisite — 2026-10-21

The event chapter now requires successful per-connection `GEQueryVersion` negotiation of XGE 1.0 before `CreateDevice`, `CreateDefaultDevice`, or `SelectEvents`. The server rejects these requests with `BadMatch` until negotiation succeeds, preserving target XIDs and prior event selections. This addresses the XGE rule that a server must not send long events to clients unless it knows they support XGE. Conformance cases cover rejection before negotiation and event framing after negotiation.


## Feature, extension and physical-device property registries — 2026-10-21

The v0.1 optional feature-ID and device-extension sets are explicitly empty: the compute baseline requires no optional feature requests or device extensions. Unknown feature IDs therefore produce `BadValue`; syntactically valid but unregistered extension names produce `BadMatch`. Four physical-device properties are registered by canonical Atom name, while numeric Atom IDs remain assigned by the X server. UUID properties use 16 raw bytes; compute work-group limits use `CARD32` and a three-element `CARD32_ARRAY`. Registered-but-unavailable values are distinguished from unknown properties. See the three new registry files and the updated device-discovery chapter.
