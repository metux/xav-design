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
- Continue final ABI review of reply layouts and XGE event framing; validate the specified queue-ordering contract against backend behavior.
- Keep request-specific error mappings and conformance cases synchronized as protocol decisions evolve; the v0.1 feature/extension/property registry cross-check is complete.

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

## Expanded reply and XGE validation — 2026-10-21

The reply golden set now covers 56 byte-exact replies in both X11 byte orders, including one- and five-byte BYTE_ARRAY property payloads, padding/word-count boundaries, and the maximum memory type/heap counts. The 52 negative reply vectors cover variable record truncation, reserved fields, invalid memory type/heap indices, count limits, reserved flag masks, aggregate payload length, and nonzero padding. The validator also checks every PHYSICALDEVICEINFO record in a variable enumeration payload, rather than only the first record.

The XGE reference validator checks the dynamic extension major-opcode range, exact event-type-specific total lengths, the GenericEvent header, event-local enum ranges, and event-specific reserved fields. Tests cross-check event-local value ranges against the central event registry. The wire protocol now explicitly requires standard X11 `QueryExtension` discovery and forbids hard-coded extension major opcodes. These remain specification/reference tests; no live X11 server interoperability has been claimed.

## Reply and XGE ABI review — 2026-10-21

Completed a specification-level cross-check of fixed and variable reply lengths, standard X11 reply header fields, the seven registered XGE event IDs and layouts, the GenericEvent header, and `SelectEvents` field/mask rules. All event total lengths agree with the XGE length formula; event-specific offsets and reserved fields are now explicit and have conformance cases. The submission-event layout question is closed at the specification level. Remaining ABI work is implementation-level interoperability testing against an X11/XGE server; this review does not claim that a server implementation has been tested.

## Automated wire-layout checker — 2026-10-21

Added `tools/check-wire-layout.py` and a GitHub Actions workflow. The checker validates all seven registered XGE event IDs and expected total/XGE lengths, parses event fields to detect overlaps, payload holes, out-of-bounds fields, alignment violations, and reserved fields without an explicit zero requirement. It also checks the 40-entry request/reply matrix against the central subopcode registry and requires complete coverage of all eleven registered Reply requests. For each, it asserts the normative field/status contracts and formulas, including variable PHYSICALDEVICEINFO and QUEUEFAMILYINFO records, memory-type/heap arrays, property and ReadBuffer payloads, and variable WriteBuffer/WaitSemaphores request contracts. The expanded CI run passed 606 checks, including boundary vectors for payload padding, record lengths, empty arrays, and maximum memory counts: [run 39650068011](https://github.com/metux/xav-design/actions/runs/39650068011), on the final checker code. This remains static specification validation, not implementation interoperability or Vulkan backend conformance. Run it with `python3 tools/check-wire-layout.py`; CI also syntax-checks the script first.

## Golden-Wire-Tests — 2026-10-21

Ergänzend zur statischen Markdown-Prüfung gibt es jetzt `tests/wire-vectors.json` und `tests/test_wire_vectors.py`. Die sechs Golden-Vektoren decken `CreateBuffer`, `WriteBuffer` und `ReadBuffer` in beiden X11-Byteordnungen ab, einschließlich Header, exakter Länge und Null-Padding. Zusätzliche Negativtests prüfen, dass der Referenz-Encoder inkonsistente Request-Längen, fehlerhafte Payload-Längen, nicht-nulliges Padding und nicht-nullige reservierte Felder zurückweist. Die Wire-Tests decken Payload-Längen 1, 3, 4 und 5 in beiden Byteordnungen ab und testen rohe abgeschnittene Header, abweichende Längenfelder sowie nicht-nullige reservierte Headerbytes. GitHub Actions führt diese Tests zusätzlich zum bisherigen Wire-Layout-Checker aus. Sie verwenden einen kleinen Referenz-Encoder und belegen noch keine Live-Interoperabilität; im Repository liegt weiterhin keine XAverius-Client-/Serverimplementierung, gegen die echte Pakete getestet werden könnten. Die Vektoren sind als gemeinsamer Byte-Level-Vertrag für spätere Implementierungstests gedacht.
