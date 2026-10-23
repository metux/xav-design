# Project status

## CI follow-up — 2026-10-23

Two earlier `wire-layout` CI runs failed for separate reasons. Run 39935266354 exposed a checker `NameError` in the CreateCommandPool error-map assertion; run 39940007063 reached the golden-wire tests but used stale SelectEvents expectations that omitted presentation-profile queue mask entries. The current branch version of `tools/check-wire-layout.py` checks the already-loaded `descriptor_errors` text, and `tests/test_select_events_vectors.py` now expects all seven documented scope/mask rows. These corrections are present in the current branch content, but a successful CI run against that exact tree still needs confirmation.


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

- Continue centralizing numeric registries that can be derived from already-settled protocol semantics; the checker now verifies request/event/error assignments plus command-entry, descriptor-type, device-type, queue-flag, shader-stage, and physical-property type registries.
- Run implementation-level interoperability tests for `QueryExtension`, XGE framing, and `SelectEvents` when a live X11/XGE implementation is available; static checks do not prove runtime interoperability.
- Validate queue-ordering and `WriteBuffer` visibility against backend behavior once a server implementation exists.
- Continue the systematic request-specific error-mapping, lifetime, and conformance review. A cross-chapter audit found and corrected a summary/matrix omission for `DestroyFence`/`DestroySemaphore`: open host-wait registrations now block destruction by exact internal resource identity, while a wait with a serialized terminal result no longer blocks destruction merely because its reply is queued. Conformance cases and static drift guards cover both pending-use and open-wait behavior.
- The latest explicitly recorded CI run for the request/error/lifetime audit passed `tools/check-wire-layout.py` (2,234 checks) and all 90 golden-wire unit tests (run 39830304211). Later SelectEvents test additions are not confirmed by a reported CI result. Static checks and reference vectors verify specification consistency, not live X11/XGE interoperability or Vulkan backend behavior.
- The shared `DEVICE_STATUS_CHANGED.reason_code` / `DEVICE_LOST.reason_code` registry is defined in [reason-codes](registries/reason-codes.md); it is not an open design item. The only currently listed v0.1 validation issue is live XGE interoperability, as tracked in [open issues](spec/open-issues.md).

## End-to-end compute-path audit — 2026-10-21

Reviewed the specification path from physical-device discovery through logical-device creation, memory and buffer setup, shader/pipeline and descriptor creation, command recording, queue submission, synchronization, readback, and resource teardown.

The audit found no request-length arithmetic contradiction in the reviewed concrete layouts. It did identify two underspecified cross-chapter contracts, now clarified in [queue submission and ordering](spec/queue-submission.md):

- A submission always has one internal terminal outcome; delivery of its completion/failure event depends on event selection and the connection remaining alive.
- In v0.1, `ReadBuffer` waits for all previously accepted submissions on the same logical device and relevant prior writes to the requested range. A prior failed submission must not be treated as successful; read data is not guaranteed correct if failed work could have modified that range.

The queue-crossing scope of the successful `WriteBuffer` visibility guarantee is now settled as a device-wide ordering boundary and documented in [Memory und Buffers](spec/memory-buffers.md#56-writebuffer), [queue submission and ordering](spec/queue-submission.md), [DECISIONS.md](DECISIONS.md), and the conformance tests. Other implementation blockers remain listed in [open issues](spec/open-issues.md), especially final ABI review and backend conformance. Queue-ordering semantics, timeout behavior, and the wait-stage mask mapping are now specified and covered by conformance cases.

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

At the time of this second audit, the request registry contained 39 assignments (1–39); the later `SelectEvents` addition assigned subopcode 40 without changing earlier values. The registry, property/Atom definitions, event-selection layouts, and wait-stage mapping have since been addressed in follow-up commits. Cross-queue scheduling guarantees and backend conformance remain open; timeout semantics are specified in the synchronization chapter. The protocol remains a working draft and `master` was not changed.


## Event selection contract — 2026-10-21

Defined `SelectEvents` as a 32-byte Void request assigned subopcode 40. It atomically replaces the mask for one connection, device, or queue scope; masks and unused fields are validated per scope, and failures preserve the previous selection. `ASYNC_ERROR` and `DEVICE_LOST` remain unmaskable. Event delivery failure or connection closure does not alter the internal terminal result of a submission or block backend cleanup. The event chapter, request registry, request audit, open-issues list, and conformance tests were updated in separate commits. Remaining event-related work is final ABI verification of XGE framing and standard extension-opcode lookup.


## XGE long-event prerequisite — 2026-10-21

The event chapter now requires successful per-connection `GEQueryVersion` negotiation of XGE 1.0 before `CreateDevice`, `CreateDefaultDevice`, or `SelectEvents`. The server rejects these requests with `BadMatch` until negotiation succeeds, preserving target XIDs and prior event selections. This addresses the XGE rule that a server must not send long events to clients unless it knows they support XGE. Conformance cases cover rejection before negotiation and event framing after negotiation.


## Feature, extension and physical-device property registries — 2026-10-21

The v0.1 optional feature-ID and device-extension sets are explicitly empty: the compute baseline requires no optional feature requests or device extensions. Unknown feature IDs therefore produce `BadValue`; syntactically valid but unregistered extension names produce `BadMatch`. Four physical-device properties are registered by canonical Atom name, while numeric Atom IDs remain assigned by the X server. UUID properties use 16 raw bytes; compute work-group limits use `CARD32` and a three-element `CARD32_ARRAY`. Registered-but-unavailable values are distinguished from unknown properties. See the three new registry files and the updated device-discovery chapter.

## Queue-ordering contract — 2026-10-21

The queue-submission chapter now distinguishes same-queue submission order from completion order and execution overlap, specifies that different queues have no implicit ordering or memory dependency, and requires explicit semaphore dependencies for queue-to-queue GPU ordering. Fence and host waits observe status but do not create queue dependencies; host semaphore signals only satisfy waits on the signaled semaphore. Submission tokens and event sequence numbers are correlation/transport values, not ordering values. v0.1 promises neither fairness nor bounded scheduling latency for independent queues. Conformance cases were added, and the open issue was narrowed to whether a future protocol version should add stronger fairness/progress guarantees. Backend conformance remains to be verified.

## Request error and conformance coverage — 2026-10-21

The request inventory was compared against the error-mapping chapter and conformance checklist. This found a missing central `SelectEvents` error-mapping section and missing explicit conformance cases for `AllocateMemory`, `CreatePipelineLayout`, `CreateSemaphore`, and `CreateFence`; these have been added. The wire-layout checker now detects if any registered request disappears from either document, while preserving the defining chapter as the semantic authority.

## Expanded reply and XGE validation — 2026-10-21

The reply golden set now covers 62 byte-exact replies in both X11 byte orders, including one- and five-byte BYTE_ARRAY boundary payloads, the registered 16-byte UUID and three-element CARD32_ARRAY shapes, padding/word-count boundaries, and the maximum memory type/heap counts. The 52 negative reply vectors cover variable record truncation, reserved fields, invalid memory type/heap indices, count limits, reserved flag masks, aggregate payload length, and nonzero padding; the unit tests assert that each vector violates exactly one named invariant. The validator also checks every PHYSICALDEVICEINFO record in a variable enumeration payload, rather than only the first record.

The XGE reference validator checks the dynamic extension major-opcode range, exact event-type-specific total lengths, the GenericEvent header, event-local enum ranges, and event-specific reserved fields. Tests cross-check event-local value ranges against the central event registry. The wire protocol now explicitly requires standard X11 `QueryExtension` discovery and forbids hard-coded extension major opcodes. These remain specification/reference tests; no live X11 server interoperability has been claimed.

## Reply and XGE ABI review — 2026-10-21

Completed a specification-level cross-check of fixed and variable reply lengths, standard X11 reply header fields, the seven registered XGE event IDs and layouts, the GenericEvent header, and `SelectEvents` field/mask rules. All event total lengths agree with the XGE length formula; event-specific offsets and reserved fields are now explicit and have conformance cases. The submission-event layout question is closed at the specification level. Remaining ABI work is implementation-level interoperability testing against an X11/XGE server; this review does not claim that a server implementation has been tested.

## Automated wire-layout checker — 2026-10-21

Added `tools/check-wire-layout.py` and a GitHub Actions workflow. The checker validates all seven registered XGE event IDs and expected total/XGE lengths, parses event fields to detect overlaps, payload holes, out-of-bounds fields, alignment violations, and reserved fields without an explicit zero requirement. It also checks the 40-entry request/reply matrix against the central subopcode registry and requires complete coverage of all eleven registered Reply requests. For each, it asserts the normative field/status contracts and formulas, including variable PHYSICALDEVICEINFO and QUEUEFAMILYINFO records, memory-type/heap arrays, property and ReadBuffer payloads, and variable WriteBuffer/WaitSemaphores request contracts. The expanded CI run passed 606 checks, including boundary vectors for payload padding, record lengths, empty arrays, and maximum memory counts: [run 39650068011](https://github.com/metux/xav-design/actions/runs/39650068011), on the final checker code. This remains static specification validation, not implementation interoperability or Vulkan backend conformance. Run it with `python3 tools/check-wire-layout.py`; CI also syntax-checks the script first.

## Golden-Wire-Tests — 2026-10-21

Ergänzend zur statischen Markdown-Prüfung gibt es jetzt `tests/wire-vectors.json` und `tests/test_wire_vectors.py`. Die sechs Golden-Vektoren decken `CreateBuffer`, `WriteBuffer` und `ReadBuffer` in beiden X11-Byteordnungen ab, einschließlich Header, exakter Länge und Null-Padding. Zusätzliche Negativtests prüfen, dass der Referenz-Encoder inkonsistente Request-Längen, fehlerhafte Payload-Längen, nicht-nulliges Padding und nicht-nullige reservierte Felder zurückweist. Die Wire-Tests decken Payload-Längen 1, 3, 4 und 5 in beiden Byteordnungen ab und testen rohe abgeschnittene Header, abweichende Längenfelder sowie nicht-nullige reservierte Headerbytes. GitHub Actions führt diese Tests zusätzlich zum bisherigen Wire-Layout-Checker aus. Sie verwenden einen kleinen Referenz-Encoder und belegen noch keine Live-Interoperabilität; im Repository liegt weiterhin keine XAverius-Client-/Serverimplementierung, gegen die echte Pakete getestet werden könnten. Die Vektoren sind als gemeinsamer Byte-Level-Vertrag für spätere Implementierungstests gedacht.

## Physical-device enumeration error-map audit — 2026-10-22

The central error map now explicitly assigns `BadLength` to `EnumeratePhysicalDevices` requests whose total size is not exactly 8 bytes, and explicitly permits a successful empty result (`reply.length = 0`) when no physical devices are available. The conformance checklist and static checker guard these requirements. CI passed on commit `4c2428cc1e547283aba5b110215a34de097b7ab5`: [run 39820302380](https://github.com/metux/xav-design/actions/runs/39820302380). This is still static documentation and golden-wire validation, not live X11/XGE interoperability.

## CreateBuffer backend error-map audit — 2026-10-22

The request-specific error map now distinguishes malformed fields and XID/type failures from unavailable/lost-device errors and memory-related backend creation failure for `CreateBuffer`. The conformance checklist and static checker guard the mapping. CI passed on commit `e27bf276b6ae6b1592effa522c3d3afec6811f99`: [run 39820652069](https://github.com/metux/xav-design/actions/runs/39820652069). This remains static specification and golden-wire validation; Vulkan runtime error-path tests await an implementation.

## AllocateMemory error-map audit — 2026-10-22

`AllocateMemory` now has consistent request-specific behavior across the normative memory chapter, central error map and conformance checklist: invalid/non-live Device XIDs use `BadValue`, wrong live type or foreign ownership uses `BadMatch`, unavailable/lost devices use `DEVICE_UNAVAILABLE` / `DEVICE_LOST`, and backend allocation failure uses `ALLOCATION_FAILED`. All failure paths leave the target XID unallocated. The checker guards these distinctions. CI passed on checker fix commit `ba23938eef28fa496856a3bac685fb8d268dead9`: [run 39821251825](https://github.com/metux/xav-design/actions/runs/39821251825). Earlier checker failures on this audit were caused by an over-specific wording assertion; the assertion was corrected to match the normative text, and the full run now passes.

## CreateDescriptorPool error-map audit — 2026-10-22

The normative descriptor-pool section and central error map now distinguish invalid XIDs/fields, wrong live resource type or foreign ownership, unavailable/lost devices, and backend allocation failure. Rejected creation leaves the Pool XID unallocated. The conformance checklist and static checker cover this contract. CI passed on audit commit `245d473b00acb064b374066944927c12d3abc73b`: [run 39821507592](https://github.com/metux/xav-design/actions/runs/39821507592). No live Vulkan runtime test is possible until a server implementation exists.

## Semaphore/fence creation error-map audit — 2026-10-22

`CreateSemaphore` and `CreateFence` now explicitly distinguish invalid/non-live Device XIDs (`BadValue`), wrong live type or foreign ownership (`BadMatch`), unavailable/lost device (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`), and backend allocation failure (`ALLOCATION_FAILED`). Failed creation leaves the target XID unallocated. The synchronization chapter, error map, conformance checklist and static checker agree. CI passed on audit commit `9b0e59d4241eb6bdbd4cb426a564112f2fa0ad94`: [run 39821711263](https://github.com/metux/xav-design/actions/runs/39821711263). Runtime Vulkan error paths remain untested.

## Descriptor, pipeline and command-pool error-map audit — 2026-10-22

The normative shader/pipeline chapter, central error map and conformance checklist now consistently specify device-state and allocation errors for `CreateDescriptorSetLayout`, `CreatePipelineLayout`, and `CreateComputePipeline`; failed creation leaves no public target resource. `CreateCommandPool` now has a dedicated error-map section rather than being buried in command-stream errors, with explicit `BadValue`, `BadIDChoice`, `BadMatch`, `DEVICE_UNAVAILABLE` / `DEVICE_LOST`, and `ALLOCATION_FAILED` behavior and atomic target-XID handling. Static checker assertions cover these contracts. CI passed on audit commit `532a236d58b3cc6598ff453e104fed2e383a476f`: [run 39822417517](https://github.com/metux/xav-design/actions/runs/39822417517). The non-allocation shader compiler/backend failure mapping is still intentionally not expanded beyond existing rules; no live Vulkan backend tests are claimed.

## Descriptor-set allocation/free audit — 2026-10-22

`AllocateDescriptorSets` now explicitly maps unknown input XIDs, wrong live types/ownership, device unavailable/lost, and pool/backend allocation failures, while guaranteeing no partial set allocation. `FreeDescriptorSets` now guarantees all-or-nothing batch behavior, defines the same device-state distinction, and rejects pending or recording references without freeing any requested set. The central error map, conformance checklist, request audit, and static checker were updated. CI passed on audit commit `b37527d303f3dfb9d8d7146935363379c8a4f48d`: [run 39823296844](https://github.com/metux/xav-design/actions/runs/39823296844). Runtime Vulkan backend failure injection remains untested.


## Command-buffer contract audit — 2026-10-22

The current pass tightened the central error mapping and conformance coverage for `CommandBufferData` and `ResetCommandBuffer`: the five legal `CREATE`/`FINAL`/`ABORT` combinations, target-XID versus input-XID precedence, malformed entry lengths, exact parent-pool validation including `ABORT`, and atomic failed-chunk recovery are now cross-checked by the static checker. Failed `FINAL` preserves `RECORDING`; failed `CREATE` leaves no public buffer or pool-child entry; rejected reset preserves state and references. This remains a specification/static-check pass, not a live server test.


The command-buffer audit passes CI on branch `docs/restructure-2026-10-21`: [run 39825028342](https://github.com/metux/xav-design/actions/runs/39825028342) completed successfully, including the golden wire-vector tests (2,221 static checks).

## Descriptor update validation audit — 2026-10-22

Clarified `UpdateDescriptorSets` error semantics: zero/unassigned descriptor-type values and duplicate writes to one slot yield `BadValue`; a registered descriptor type incompatible with a binding yields `BadMatch`. The normative request chapter, central error map, conformance checklist, and static checker now agree. CI passed at [run 39825499901](https://github.com/metux/xav-design/actions/runs/39825499901), including 2,223 static checks and the golden wire-vector tests.

## Descriptor-set contents and command-buffer references — 2026-10-22

Descriptor-set updates now have explicit reference-graph semantics across chapters: command buffers reference the set object, not a frozen descriptor snapshot; successful updates atomically refresh indirect Buffer references for all non-pending command buffers that use the set. An executable command buffer observes current descriptor contents when submitted and is not invalidated by the update alone. The conformance checklist and static checker cover the rule. CI passed in [run 39826027013](https://github.com/metux/xav-design/actions/runs/39826027013), including 2,225 static checks and the golden wire-vector tests.

## QueueSubmit semaphore-entry validation — 2026-10-22

Duplicate wait/signal semaphore entries and using the same semaphore in both arrays now have explicit `BadValue` mappings. Conformance coverage checks Binary semaphore values, Timeline signal reservations, and that rejected submissions reserve neither the token nor synchronization slots. Static checker guards are in place. CI passed on validation commit `5e6fb4d2f41942ef60413856a758364069684a7d`: [run 39828130540](https://github.com/metux/xav-design/actions/runs/39828130540). Runtime backend behavior remains untested until an XAverius server implementation exists.

## SignalSemaphore error-precedence audit — 2026-10-22

`SignalSemaphore` now explicitly specifies exact request length, unknown-XID versus wrong-live-type/ownership errors, and unavailable/lost-device outcomes before validating the Timeline counter and pending signal reservations. The central mapping, conformance checklist and static checker agree. CI passed on checker commit `b9fa01aafd25dff9a32d1b02c2306b06b6549562`: [run 39828317685](https://github.com/metux/xav-design/actions/runs/39828317685). Runtime behavior remains untested until a server implementation exists.

## Host semaphore wait/signal error audit — 2026-10-22

`SignalSemaphore` and `WaitSemaphores` now have explicit request-specific error precedence across the normative synchronization chapter, central error map, conformance checklist and static checker. CI passed on checker commit `12df57b95b8ffb8067b2f15cd8063a476937b76e`: [run 39828507464](https://github.com/metux/xav-design/actions/runs/39828507464). This remains a spec/static-check pass, not a runtime Vulkan test.

## WaitForFence request-validation audit — 2026-10-22

`WaitForFence` now defines exact request length, XID/type/ownership validation, and terminal reply statuses across the normative chapter, central error map, conformance checklist and static checker. CI passed on checker commit `4cceb27230a70489584cba5a163777ed951c2d07`: [run 39828776699](https://github.com/metux/xav-design/actions/runs/39828776699). An earlier guard mismatch was corrected; no runtime backend tests are claimed.

## GetFenceStatus request-validation audit — 2026-10-22

`GetFenceStatus` now has explicit request length, XID/type/ownership, and post-Device-Loss state-query semantics across the normative chapter, central error map, conformance checklist and static checker. CI passed on checker commit `a9bc31667ee52385f325548a9ae82df51aa97fd7`: [run 39828908220](https://github.com/metux/xav-design/actions/runs/39828908220), including golden wire vectors. No runtime backend test is claimed.

## Fence status/reset validation audit — 2026-10-22

`GetFenceStatus` and `ResetFence` now have explicit request-length, XID/type/ownership, state and Device-Loss rules across the normative chapter, error map, conformance checklist and checker. CI passed on checker commit `74879a43c8c5e7d96da4fe27f40a2d38757a7bec`: [run 39829069365](https://github.com/metux/xav-design/actions/runs/39829069365). Runtime Vulkan behavior remains untested.

## GetSemaphoreCounterValue request-validation audit — 2026-10-22

`GetSemaphoreCounterValue` now has explicit length, XID/type/ownership, Timeline-only, and post-loss error semantics across the normative chapter, error map, conformance checklist and checker. CI passed on checker commit `afeac993c1fade3de04871aa624dcfa860f52b58`: [run 39829221170](https://github.com/metux/xav-design/actions/runs/39829221170), including golden wire vectors. No runtime backend test is claimed.

## ResetCommandBuffer device-state audit — 2026-10-22

ResetCommandBuffer now specifies unavailable/lost logical Device outcomes consistently across the normative chapter, central error map and conformance checklist, with XID/type/ownership validation taking precedence over device-state and reset-state checks. The static checker guards the cross-chapter contract. CI passed in [run 39830304211](https://github.com/metux/xav-design/actions/runs/39830304211), including 2,234 static checks and 90 golden wire-vector tests. This remains a specification/static-check pass, not a live server test.


## Server-side X11 presentation direction — 2026-10-23

Added [the presentation architecture chapter](spec/presentation.md) for a future presentation-capable profile. The intended model is server-side: clients create ordinary X11 windows, then identify them by XID; XAverius owns the presentation backend and does not require client-native Vulkan WSI handles. A native server WSI path is an implementation option, not a protocol requirement; server-managed images with an internal copy/blit/composition path remain possible.

The existing 40-request compute-oriented registry was deliberately not changed. Before allocating presentation request subopcodes, the design still needs exact Surface/Swapchain lifetimes, capability and format registries, acquire/present synchronization, distinct GPU-completion/image-release/presentation-completion semantics, and resize/surface-loss handling. The chapter is indexed, the direction is recorded in the decision log, and the work is tracked as future-profile work rather than a v0.1 compute blocker. No live X11 or Vulkan implementation behavior has been tested by these documentation commits.


## Presentation design pass 1 — ownership and window identity — 2026-10-23

Settled the initial presentation-profile ownership model in [presentation](spec/presentation.md) and added Surface/Swapchain rows to [resource lifetime](spec/resource-lifetime.md):

- Surface belongs to the creating X11 connection, is not Device-owned, and holds an internal reference to one exact X11 Window identity.
- Swapchain belongs to exactly one logical Device and references one Surface; its images are not independently destroyable resources.
- Surface destruction is rejected while a live Swapchain references it. Swapchain destruction is rejected while images are acquired or presentation/backend work may still access them.
- Window destruction transitions the Surface to SURFACE_LOST; XID reuse must never retarget the existing Surface.
- DestroyDevice/client disconnect invalidate public presentation XIDs immediately while internal resources remain until safe backend quiescence.

Provisional request shapes are noted for later wire/error review: CreateSurface 16 bytes, DestroySurface 12 bytes, DestroySwapchain 12 bytes. No subopcodes were allocated. The current command-entry registry is compute-only and has no image or graphics commands; this is explicitly called out as a separate prerequisite for actual rendering to swapchain images.


## Presentation design pass 2 — capabilities and synchronization — 2026-10-23

Added the presentation format/mode registry and capability-query semantics. The profile defines wire IDs for RGBA8_UNORM, BGRA8_UNORM, SRGB_NONLINEAR, and FIFO. The chapter now specifies the capability snapshot, swapchain image-index/state model, acquire and present synchronization, resize/loss transitions, and provisional request/reply layouts. Presentation XGE events IMAGE_RELEASED and PRESENTATION_COMPLETE distinguish image reuse from presentation completion. The existing static checker still needs to be extended for the additional presentation event definitions before new presentation subopcodes are assigned; no CI pass is claimed for these latest changes.


## Presentation design pass 3 — image path, event milestones, and lifecycle — 2026-10-23

Defined the minimal image path for the future presentation profile: compute can write a Buffer, and the new presentation-only CMD_COPY_BUFFER_TO_SWAPCHAIN_IMAGE entry copies the buffer into an acquired swapchain image. Initial swapchain image usage is TRANSFER_DST only; no graphics pipeline/rasterization support is implied. Added separate IMAGE_RELEASED and PRESENTATION_COMPLETE event definitions and queue mask bits, plus conformance cases for their distinct semantics and for the presentation lifecycle.

The chapter now includes provisional layouts for CreateSurface, DestroySurface, GetSurfaceCapabilities, CreateSwapchain, DestroySwapchain, AcquireNextImage, and QueuePresent. These are not yet assigned request subopcodes. The wire-layout checker still needs corresponding updates for the additional event IDs and presentation-only command entry before the request registry is extended. CI has not reported a status for these commits; no successful test run is claimed.


## Presentation ABI review checkpoint — 2026-10-23

The compute-only registries remain unchanged: the central event registry still assigns IDs 0–6, and the command-entry registry still assigns IDs 1–4. Presentation-only event IDs 7 and 8 are documented in a separate profile registry. The buffer-to-swapchain copy entry is specified but has no allocated numeric ID yet. This keeps the compute-only checker assumptions and stable IDs intact while the presentation profile's checker support is completed.

The seven presentation request/reply layouts are specified provisionally in spec/presentation.md, but their request subopcodes are intentionally unassigned. The next implementation step is a reviewed static-checker extension for profile-specific events, command entries, request layouts, and reply formulas; only then should those request IDs be appended. No CI result was reported for the latest branch head.


## Presentation-profile audit checkpoint — 2026-10-23

The presentation chapter now has a provisional fixed wire layout for all seven requests, with request subopcodes still deliberately unassigned. The latest cross-chapter pass reconciled the acquisition/destroy rules and added presentation-specific error mapping plus profile-gated conformance cases. Key distinctions are explicit: core X11 `BadWindow` for the source Window XID, `BadIDChoice` for create-target collisions, synchronous X11 errors for malformed/invalid resources, normal reply statuses for expected runtime outcomes, and presentation events for accepted asynchronous outcomes.

Still open before numeric allocation:
- The checker now has a provisional `check_presentation_profile` hook for the separate event registry, event framing, request-layout presence, and key reply-length formulas. It is not yet validated: review found incorrect escaping in the newly added event-registry regex, and the attempted corrective update was blocked. Do not treat the checker as passing; fix that regex and run the script before allocating IDs.
- Reconcile the proposed presentation event layouts against XGE framing and validate their event IDs against the separate profile registry without changing the compute-only event registry.
- Assign request subopcodes 41–47 and command-entry ID 5 only after checker coverage and the full wire/error audit are complete.
- Run CI after these changes. No successful CI result has been confirmed for the current presentation commits.


## Presentation-profile checker hardening — 2026-10-23

Corrected the raw-regex escaping in `check_presentation_profile`. During the follow-up review, found and removed a second checker defect: the provisional request-layout headings are plain names followed by the request kind/size, not backtick-wrapped names, so the old heading matcher would have rejected all seven valid sections. The checker now validates the actual headings, fixed reply sizes and `reply.length` values, the exact presentation-event payload offset/type sequence and complete byte coverage, the separate event IDs, and that request IDs 1–40 plus command-entry IDs 1–4 remain unchanged until the profile audit is complete.

The acquisition contract now explicitly permits either optional binary semaphore and optional fence to be omitted or supplied together, and states that each supplied object is signaled exactly once on success. The `IMAGE_RELEASED` wording now limits event cardinality per accepted presentation operation, avoiding an interpretation that an image may receive the event only once for its entire Swapchain lifetime.

The changes are committed on `docs/restructure-2026-10-21`; `master` remains untouched. **Validation is still pending:** no local checkout/execution was available in this pass, and the GitHub status/workflow queries returned no checks for the observed commit. Do not treat the checker as passing and do not allocate presentation request subopcodes 41–47 or command-entry ID 5 until an actual checker/CI run succeeds.


## Swapchain lifetime cross-chapter correction — 2026-10-23

The cross-chapter audit found a substantive contradiction: `spec/presentation.md` and the presentation error rules allowed destroying a Swapchain with an acquired-but-idle image, but the resource-lifetime matrix still rejected destruction whenever any image was acquired. The matrix now agrees with the normative presentation contract: destruction is blocked by recording command buffers, pending acquires, accepted queue/presentation work, or possible backend accesses; an acquired-but-idle image alone does not block it. A conformance case and a static checker assertion now guard this agreement.

The checker has also been extended to verify the seven actual presentation request headings and fixed reply-size/`reply.length` pairs, in addition to the corrected event registry regex and exact 64-byte presentation event layouts. This remains an unexecuted checker change: the GitHub status and workflow queries for the latest observed commit returned no checks. Numeric request IDs 41–47 and command-entry ID 5 remain intentionally unassigned pending an actual successful run.


## Presentation event-mask audit — 2026-10-23

Reviewed the presentation event selection against the shared XGE event namespace. Queue mask bits 2 and 3 map to `IMAGE_RELEASED` and `PRESENTATION_COMPLETE`; compute-only servers reject those bits with `BadValue`. The checker now verifies the presentation event status registry (0–4), those queue-mask mappings, and the compute-only rejection rule. The presentation profile remains separate from the compute baseline and no numeric request or command-entry assignments were added.

The latest checker edits have not been executed locally or confirmed by CI; the current GitHub status/workflow query still needs to be checked after the latest commit. The next safe step remains obtaining a real successful checker/CI run, then fixing any surfaced failures before allocating IDs.


## CI failure from run 39935266354 — 2026-10-23

Inspected job 120353145994. Python syntax compilation passed; the matrix/layout validation failed before the golden wire-vector tests ran. The traceback identified a real checker bug in `check_other_numeric_registries()`: the CreateCommandPool error-map assertions referenced an undefined local variable `errors`, raising `NameError`. Changed those references to the already loaded `descriptor_errors` content. Confirmed both expected error strings exist in `spec/errors.md`.

Fix committed as `fed81540744047f913531bfe9181db7b52e11dbe`. A new successful run has not yet been observed; the connector's status query currently reports no status entries and its commit-run query only returns pull-request-triggered runs. Treat validation as pending until a new Actions run reaches the layout-validation and golden-vector steps.

## Presentation copy-command checker coverage — 2026-10-23

Extended `check_presentation_profile` to validate the presentation-only `CMD_COPY_BUFFER_TO_SWAPCHAIN_IMAGE` command entry rather than merely checking that its name and nominal size appear. The checker now compares all nine field offsets, order, wire types/descriptions, the fixed 36-byte/9-word framing, source/destination usage, buffer-span arithmetic, alignment/bounds rules, and the still-unassigned numeric command-entry ID.

During source-level review of the new assertion, corrected the regex escaping and aligned the expected `row_length` / `image_height` descriptions with the normative text. A source-level comparison confirms the nine documented offsets and required contract phrases are present. This is not an execution of the Python checker: the current environment cannot clone the repository, and GitHub status queries still return no checks for the latest commits. The CI failure fix and this additional checker coverage remain unvalidated until Actions runs the current branch head. Presentation request subopcodes 41–47 and command-entry ID 5 remain unassigned.
## Presentation request offset checker — 2026-10-23

Extended `check_presentation_profile` to compare the fixed request-field offsets for all seven provisional presentation requests and all fourteen fixed `GetSurfaceCapabilities` reply fields. This supplements the existing size/formula assertions and copy-command entry layout checks. The checker uses the actual `### RequestName — ...` headings in `spec/presentation.md`; source-level extraction against the current spec confirms the expected offset sequences are present.

During implementation, corrected the regex escaping and used a presentation-specific section extractor because the existing `chapter_section` helper targets a different heading convention. These were source-review corrections, not a successful execution of the checker. CI remains unverified; no subopcodes or command-entry IDs have been allocated.

## Golden wire-vector CI follow-up — 2026-10-23

Inspected Actions run [39940007063](https://github.com/metux/xav-design/actions/runs/39940007063): syntax checking and the request/reply/XGE layout checker passed, while the golden-vector suite reported 13 failures. Nine were overly strict event-field label assertions that did not recognize names written after their wire type in a shared inline-code span. The remaining failures were stale SelectEvents test expectations: two tests omitted the presentation-profile queue mask bits and one assertion used an outdated phrase for the queue-mask linearization rule.

Updated the event field checks to match field names as tokens, aligned the SelectEvents contract test with the normative presentation event-mask table, and corrected the linearization wording expectation. The first rerun exposed one additional stale expected mask list in the exhaustive vector/spec test; that list was corrected as well.

Actions run [39940369790](https://github.com/metux/xav-design/actions/runs/39940369790) then completed successfully: syntax check, request/reply matrix and XGE event layout validation, and all golden wire-vector tests passed. No request subopcodes or command-entry IDs were allocated by this test-only correction.


## Presentation error-map checker follow-up — 2026-10-23

Continued the cross-chapter presentation audit after the golden-vector CI recovery. The presentation chapter still described its checker coverage as unvalidated, and the open-issues list still described cross-chapter error-map/checker coverage as unfinished, despite the successful CI run. Updated those status statements.

Extended `tools/check-wire-layout.py` so the presentation-profile pass also checks key request-specific error-map invariants across all seven provisional requests: target-XID creation errors, unknown-XID errors, atomic failure semantics, the acquired-but-idle Swapchain destruction rule, and QueuePresent rejection preserving image/wait state. This remains profile-gated; request subopcodes 41–47 and command-entry ID 5 remain unassigned.


## Presentation terminal-event semantics — 2026-10-23

The cross-chapter lifecycle pass found that the presentation chapter still called asynchronous failure reporting and destruction with acquired images unresolved even though the event registry and conformance cases already defined most of the behavior. Reconciled those stale statements and made failure cardinality explicit: every accepted presentation gets a terminal `PRESENTATION_COMPLETE` outcome when delivery is permitted; `IMAGE_RELEASED` is emitted only if the image is reusable. If it cannot be reused, the image and Swapchain are invalidated instead. `DestroyDevice` and disconnect suppress event delivery at their established lifecycle boundary without skipping internal terminal cleanup.


## Pending AcquireNextImage teardown semantics — 2026-10-23

The lifecycle audit found one remaining gap: unlike the existing `WaitForFence`/`WaitSemaphores` contracts, the provisional `AcquireNextImage` contract did not define what happens when `DestroyDevice` is processed while an acquire is waiting for an image. Added the distinct normal reply status `DEVICE_DESTROYED=6`, with the first server-serialized terminal result winning. Device destruction terminates an open acquire without signaling its semaphore/fence; disconnect removes the registration without a reply. Destroying the referenced Surface or Swapchain while the acquire is still pending remains an atomic `INVALID_SYNCHRONIZATION_STATE` rejection. The request/error/lifetime/conformance chapters and static checker agree, and CI passed on `b0cf322470e63ffc4d112aaa0dc0634b022ae2d2` ([run 39943267748](https://github.com/metux/xav-design/actions/runs/39943267748)).


## Accepted presentation lifecycle races — 2026-10-23

Clarified the terminal-state race for accepted `QueuePresent` operations across window resize/zero extent, Window destruction, and Device loss. Each accepted operation records one serialized terminal status; later lifecycle notifications cannot overwrite it. A pending operation that cannot complete because of `OUT_OF_DATE`, `SURFACE_LOST`, or `DEVICE_LOST` invalidates the affected image/Swapchain and does not emit `IMAGE_RELEASED`. `PRESENTATION_FAILED` permits image release only after backend quiescence and confirmation that the Swapchain remains usable. Conformance and resource-lifetime text now cover the same rule. Presentation request subopcodes 41–47 and command-entry ID 5 remain unassigned pending the broader ABI review.


## QueuePresent binary-wait state integration — 2026-10-23

Cross-checked presentation waits against the common binary-semaphore state machine. Accepted QueuePresent operations now reserve each semaphore wait slot atomically with image/token acceptance; the signal is consumed only after a confirmed backend wait. If an accepted presentation fails before a wait is resolved, the semaphore preserves a provably unconsumed state, records confirmed consumption, or becomes `UNTRUSTED` if the payload outcome is uncertain. Incompatible pending waits reject atomically with `INVALID_SYNCHRONIZATION_STATE`; `UNTRUSTED` waits reject with `DEPENDENCY_FAILED`. Added conformance and static-checker coverage. Presentation request subopcodes 41–47 and command-entry ID 5 remain unassigned.


## Presentation synchronization and event selection — 2026-10-23

Completed another cross-chapter check of QueuePresent. Binary presentation waits now participate in the same pending-wait exclusivity and payload-state accounting as QueueSubmit waits: reservation is atomic with acceptance, signal consumption requires a confirmed backend wait, and uncertain payload outcomes mark the semaphore `UNTRUSTED` rather than guessing. Error mapping and conformance now distinguish incompatible pending waits (`INVALID_SYNCHRONIZATION_STATE`) from an already `UNTRUSTED` semaphore (`DEPENDENCY_FAILED`). Presentation event masks are sampled independently at each event's own terminal milestone, so later `SelectEvents` changes cannot retroactively alter an event's delivery decision. Static checks cover both contracts. Presentation subopcodes 41–47 and command-entry ID 5 remain unassigned.


## Copy-command validation and error mapping — 2026-10-23

The provisional `CMD_COPY_BUFFER_TO_SWAPCHAIN_IMAGE` path now has an explicit error map and conformance coverage. Resource lookup/type/ownership, transfer-usage compatibility, image-index bounds, row geometry, alignment and source-span checks are distinguished; the image must still be `ACQUIRED` atomically at submission acceptance. The checker validates that this remains documented. The command-entry ID is still unassigned and presentation request subopcodes 41–47 remain unassigned pending the complete ABI review.

## Command-buffer / presentation lifetime cross-check — 2026-10-23

The cross-chapter audit corrected the Buffer destruction matrix to match the general recorded-reference rule: a Buffer referenced by a RECORDING command buffer blocks destruction; successful destruction invalidates non-pending EXECUTABLE command buffers that still reference it. The provisional swapchain-copy path now explicitly ties image-state validation to serialized X11 request acceptance: a copy submission accepted before QueuePresent retains its exact image/Swapchain identity, while a later copy submission after the image transitions to PRESENT_PENDING is rejected atomically. Request order is explicitly not a GPU memory dependency, and presentation must wait on a binary semaphore dependency when prior accepted work may still access the image.

Conformance and the static checker now assert these rules, including indirect Buffer references through Descriptor Sets during recording. GitHub Actions run [39948495316](https://github.com/metux/xav-design/actions/runs/39948495316) passed syntax checking, request/reply and XGE layout validation, and all golden wire-vector tests. Presentation request subopcodes 41–47 and command-entry ID 5 remain unassigned.
