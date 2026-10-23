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
- Extend and validate `tools/check-wire-layout.py` for the seven presentation request/reply layouts, the presentation-only command entry, and the separate presentation event registry. Previous update attempts to the executable checker were blocked; no checker modification is claimed.
- Reconcile the proposed presentation event layouts against XGE framing and validate their event IDs against the separate profile registry without changing the compute-only event registry.
- Assign request subopcodes 41–47 and command-entry ID 5 only after checker coverage and the full wire/error audit are complete.
- Run CI after these changes. No successful CI result has been confirmed for the current presentation commits.
