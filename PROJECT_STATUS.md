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

- Review chapter boundaries and links.
- Reconcile the 64 KiB request/segmentation proposal with the historical BIG-REQUESTS wording before making either normative.
- Finalize remaining request/reply layouts and registry ownership.
- Resolve the questions in [open issues](spec/open-issues.md).
- Add conformance tests as protocol decisions are made.

## End-to-end compute-path audit — 2026-10-21

Reviewed the specification path from physical-device discovery through logical-device creation, memory and buffer setup, shader/pipeline and descriptor creation, command recording, queue submission, synchronization, readback, and resource teardown.

The audit found no request-length arithmetic contradiction in the reviewed concrete layouts. It did identify two underspecified cross-chapter contracts, now clarified in [queue submission and ordering](spec/queue-submission.md):

- A submission always has one internal terminal outcome; delivery of its completion/failure event depends on event selection and the connection remaining alive.
- In v0.1, `ReadBuffer` waits for all previously accepted submissions on the same logical device and relevant prior writes to the requested range. A prior failed submission must not be treated as successful; read data is not guaranteed correct if failed work could have modified that range.

The queue-crossing scope of the successful `WriteBuffer` visibility guarantee is now settled as a device-wide ordering boundary and documented in [Memory und Buffers](spec/memory-buffers.md#56-writebuffer), [queue submission and ordering](spec/queue-submission.md), [DECISIONS.md](DECISIONS.md), and the conformance tests. Other implementation blockers remain listed in [open issues](spec/open-issues.md), especially event registration/layouts, complete error mapping, and final wait-stage masks.

This is an internal consistency and compute-workflow audit, not a claim of full Vulkan-spec conformance or a frozen v0.1 wire protocol.

## WriteBuffer visibility decision — 2026-10-21

The former open issue on cross-queue visibility is closed. A successful `WriteBuffer` reply guarantees this order for its logical device:

1. All earlier accepted submissions have reached a terminal outcome.
2. The transfer has completed and required visibility operations have completed.
3. Every later accepted submission on any queue sees the written bytes.

The contract applies to the full written range and does not require client semaphore/barrier operations solely for upload visibility. It is scoped to one logical device, not all devices on a physical GPU. To avoid a dispatcher deadlock, a later `SignalSemaphore` on the same connection may run while `WriteBuffer` waits for earlier work; later `QueueSubmit` requests must remain deferred until the upload completes. A conservative implementation may fully synchronize the device. Device loss or transfer failure must not produce a successful reply. Conformance cases cover these ordering and progress requirements.


## Shader and command-recording wire decisions — 2026-10-21

The working draft now defines the `ShaderModuleData` chunk layout and `CREATE`/`FINAL`/`ABORT` flags, including atomic final creation and cleanup of failed/incomplete assemblies. It also defines fixed `CreateCommandPool`/`DestroyCommandPool` layouts and deterministic recovery from failed `CommandBufferData` chunks: a chunk is atomic, previously accepted chunks remain, and ABORT returns a non-pending recording buffer to `INITIAL`. Conformance cases and request-specific error guidance were added. The `CreateDescriptorSetLayout` fixed header, binding-record layout, zero-flags rule, validation and atomicity are now documented, with conformance cases. The `DestroyResource` request is also scoped to eligible standalone resource types, with dedicated requests retained for device, pools, command buffers, descriptor sets and memory. The binding reset semantics are also fixed in the working draft: `RESET_COMMAND_BUFFER` gates explicit `ResetCommandBuffer`, `TRANSIENT` is only an optimization hint, and chunk-recovery `ABORT` remains independent. Conformance cases cover the allowed states and atomic rejection. These decisions are documented but the v0.1 protocol and registries remain unfrozen.
