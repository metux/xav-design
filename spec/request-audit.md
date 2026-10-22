# Request catalogue and wire-contract audit — 2026-10-21

## CommandBufferData and ResetCommandBuffer follow-up — 2026-10-22

The command-recording pass made the five permitted CREATE/FINAL/ABORT combinations explicit in conformance coverage and tightened deterministic error handling: malformed/incomplete entry headers versus invalid entry lengths, CREATE target-XID collisions versus missing input buffers, and the exact parent-pool check even for ABORT. It also records the required recovery guarantees: failed chunks are atomic, failed FINAL leaves the buffer RECORDING, failed CREATE leaves no public buffer or pool-child entry, and rejected ResetCommandBuffer preserves state and references. Static checks now guard these cross-chapter statements. These are documentation and static consistency checks only; runtime server behavior remains untested.
The follow-up's static checker passes on branch `docs/restructure-2026-10-21` in [CI run 39825028342](https://github.com/metux/xav-design/actions/runs/39825028342), including the golden wire-vector tests. The checker currently reports 2,221 checks; this remains static contract coverage rather than runtime Vulkan/X11 interoperability.

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
1. `SelectEvents` is included as subopcode 40. Its wire layout, scope semantics, XGE negotiation prerequisite, dynamic `QueryExtension` discovery, extension-opcode range, and event framing are specified and statically checked; only implementation-level interoperability remains.
2. The v0.1 feature-ID and device-extension registries are explicitly empty, and the physical-device property/Atom-name registry defines four properties. Their basic error mapping and conformance cases are now covered.
3. Implementation-level backend conformance remains open as listed in [open issues](open-issues.md); same-queue order, no implicit cross-queue order, explicit semaphore dependencies, and the absence of fairness or bounded-latency guarantees are now specified in [queue submission](queue-submission.md). Timeout semantics for `WaitSemaphores` and `WaitForFence` now define monotonic deadlines, zero/infinite timeout behavior, terminal-state precedence, and device-loss handling. The v0.1 wait-stage mapping, queue-family compatibility rules, and invalid-mask error precedence are also explicit in [queue submission](queue-submission.md), [synchronization](synchronization.md), [error mapping](errors.md), and the conformance checklist.
## Subopcode allocation policy

The 40 requests in the central registry are assigned explicit values 1 through 40. Value 0 is reserved and MUST NOT identify a request. These numbers are stable: later requests MUST use an unused value and MUST NOT renumber an existing request. `SelectEvents` uses the next unused value, 40; assignments 1 through 39 were not changed.


## Historical findings from the second systematic pass (resolved)

The following items were found during an earlier audit pass and have since been addressed in the defining chapters, central error mapping, registries, or conformance checklist. This list is historical context, not a list of currently open defects:

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
- **Error mapping:** the central error chapter governs XID liveness, live-type mismatch, ownership, Atom validation, Create-XID choice, validation order, and atomic rejection. Request-specific tables define the specialized state and backend failures. The specification-level ABI review is complete for the currently defined reply and XGE layouts. The remaining ABI task is live interoperability testing against an X11/XGE implementation; static checks do not establish runtime interoperability. The feature-ID, device-extension, and physical-device-property registries are defined for v0.1; XGE negotiation and event selection are specified. Timeout behavior and implementation-level backend conformance remain subject to their defining chapters and the open-issues register.

## Event-selection request addition — 2026-10-21

`SelectEvents` is now defined as a 32-byte Void request at subopcode 40. The request atomically replaces the selection for one connection, device, or queue scope; masks are scope-specific and `ASYNC_ERROR`/`DEVICE_LOST` are unmaskable. Conformance coverage was added. This adds one request without changing assignments 1–39.

## Reply and XGE ABI review — 2026-10-21

The specification-level ABI pass rechecked the standard 32-byte X11 reply header, fixed versus variable reply payload lengths, and all seven registered XGE event layouts against the event registry. The common XGE header is now explicit (GenericEvent response type 35, dynamic extension major opcode, 16-bit sequence, 32-bit length, static 16-bit `evtype`, zero reserved header bytes), and all event total lengths agree with `32 + 4 * length`: 60/7 for `ASYNC_ERROR`, 48/4 for four device events, and 56/6 for both submission events. Submission-event offsets, failure-class values, and the exactly-one-terminal-event rule are aligned. `SelectEvents` is checked as a 32-byte Void request with scope-specific fields and masks. Conformance cases now cover these layouts and reply padding. This closes the specification-level layout question for submission events; actual interoperability testing against an X11/XGE server remains an implementation-level task.

## Automated wire-layout checker — 2026-10-21

The repository now contains `tools/check-wire-layout.py`, wired into `.github/workflows/wire-layout.yml`. It cross-checks the central 40-request registry against this audit's request-kind/length matrix; checks selected fixed reply fields, reserved bytes, and variable reply-length formulas against their defining chapters; and parses every XGE event's field declarations to detect overlap, holes, alignment violations, out-of-bounds fields, incorrect total/XGE lengths, and registry-ID drift. It is deliberately a static Markdown contract checker. It does not parse every arbitrary formula into an expression tree and does not establish runtime interoperability; those remain separate conformance tasks.

## Expanded Reply ABI checker — 2026-10-21

The static checker now requires exact inventory coverage of all eleven Reply requests in the central registry and checks each against its defining chapter. Coverage includes fixed header/field/status contracts; `PHYSICALDEVICEINFO` variable record size, name length and padding; 12-byte `QUEUEFAMILYINFO` records; memory type/heap record sizes and count bounds; variable physical-property and `ReadBuffer` payload formulas; and the request/response completion contracts of `WriteBuffer` and `WaitSemaphores`. The GitHub Actions run on checker commit `03188b2904cb540b2107008e1e72e462b9b29ae6` passed 606 checks, including explicit boundary vectors for padding, record lengths, empty arrays, and maximum memory counts. This remains static Markdown validation and not live server interoperability.


## Error/conformance coverage follow-up — 2026-10-21

A further inventory scan found that `SelectEvents` had its error behavior defined in the event chapter but was missing from the central error-mapping chapter. Added its exact-length, XGE-negotiation, scope/mask, XID, ownership, and atomic-preservation mapping. The conformance checklist now also has explicit cases for `AllocateMemory`, `CreatePipelineLayout`, `CreateSemaphore`, and `CreateFence`, which were previously represented only indirectly.

The static wire-layout checker now requires every centrally registered request to be named in both the error guidance and conformance checklist. This is a presence/drift check, not a proof that each listed rule is exhaustive; request-specific semantics remain defined by the chapters and the central error mapping.


## Numeric registry integrity follow-up — 2026-10-21

The static checker now verifies uniqueness and expected current ranges for the 40 request subopcodes, seven event-type IDs, contiguous error offsets, four command-entry IDs, the descriptor-type assignments, five physical-device types, five queue-flag bits/masks, the v0.1 compute shader-stage bit, and the eight physical-property type IDs. It also checks that the v0.1 optional feature-ID and device-extension registries remain explicitly empty. The request, event, and error checks detect duplicate names/values and missing assignments; other registries are checked against their current v0.1 supported assignments.

These are drift guards for the current documented ABI. They do not make unassigned values valid, and they do not claim runtime interoperability.

## Host-wait destruction lifetime cross-check — 2026-10-22

A cross-chapter review compared the specialized `DestroyFence` and `DestroySemaphore` mappings against the synchronization chapter, resource-lifetime matrix, error summary, and conformance checklist. The synchronization chapter already defined the required internal-identity rule, but the lifetime matrix and summary error list omitted open host-wait registrations. These summaries now match the normative rules: destruction is rejected while a fence is pending or an exact-identity `WaitForFence` is open, and while a semaphore is used by an accepted queue wait/signal, exact-identity `WaitSemaphores`, or another active host operation. Once a wait has a serialized terminal outcome, a reply still queued for transmission does not keep the resource alive or block destruction. Device-loss cascade teardown remains the explicit exception to normal pending-use rejection. Static checks now guard these cross-chapter statements and the conformance checklist exercises both pending-use and open-wait cases. This is a documentation/lifecycle audit; runtime concurrency behavior still requires an implementation test.

## Physical-device enumeration error-map follow-up — 2026-10-22

A request-specific error-map pass found that `EnumeratePhysicalDevices` specified its exact 8-byte request and complete-record reply contract, but did not explicitly name the X11 error for a malformed request. The central mapping now says that any other request length yields `BadLength`, permits an empty successful reply when no physical devices are available, and forbids partial `PHYSICALDEVICEINFO` records. The conformance checklist and static checker now guard this contract. This closes a documentation omission; it does not exercise a live server.

## CreateBuffer backend error-map follow-up — 2026-10-22

The request-specific mapping for `CreateBuffer` listed backend allocation failure but omitted the distinct `DEVICE_UNAVAILABLE` / `DEVICE_LOST` outcomes and the general wrong-live-type `BadMatch` case. The central mapping now distinguishes invalid input, device state, and memory-related backend creation failure, and states that rejection leaves no live Buffer. The conformance checklist and static checker guard the distinction. Runtime Vulkan error injection remains untested because there is no server implementation.

## AllocateMemory device-state error-map follow-up — 2026-10-22

The central error map had two summaries for `AllocateMemory`: the detailed memory section included wrong-live-type, foreign-ownership and unavailable/lost-device errors, while the earlier request summary omitted them. The normative memory chapter also specified allocation failure but not the device-state/ownership outcomes. The chapter, both error-map entries and conformance checklist now agree: `BadValue` for unknown/non-live device XIDs, `BadMatch` for wrong live type/foreign ownership, `DEVICE_UNAVAILABLE` / `DEVICE_LOST` for device state, and `ALLOCATION_FAILED` for allocation failure. Every rejection leaves the target XID unallocated. The static checker guards this mapping; no backend runtime behavior is claimed.

## CreateDescriptorPool device-state error-map follow-up — 2026-10-22

The `CreateDescriptorPool` request mapping listed input validation and backend allocation failure but omitted wrong-live-type/foreign-ownership and unavailable/lost-device outcomes. The normative descriptor-pool section now specifies `BadValue`, `BadMatch`, `DEVICE_UNAVAILABLE` / `DEVICE_LOST`, and `ALLOCATION_FAILED` separately, and states that failure leaves the target Pool XID unallocated. The central mapping, conformance checklist and static checker now guard the same contract. Runtime backend error injection remains untested.

## Semaphore/fence creation error-map follow-up — 2026-10-22

The `CreateSemaphore` and `CreateFence` error map omitted wrong-live-type/foreign-ownership and unavailable/lost-device outcomes, and their normative request sections did not state the atomic target-XID guarantee. The synchronization chapter, central mapping and conformance checklist now consistently distinguish `BadValue`, `BadMatch`, `DEVICE_UNAVAILABLE` / `DEVICE_LOST`, and `ALLOCATION_FAILED`; failed creation leaves no public semaphore/fence XID. Static checks now guard these rules. Backend runtime error paths remain untested.

## Descriptor-layout and pipeline creation error-map follow-up — 2026-10-22

The audit found inconsistent coverage for `CreateDescriptorSetLayout`, `CreatePipelineLayout`, and `CreateComputePipeline`: the descriptor-layout map omitted unavailable/lost-device and backend allocation outcomes, while the pipeline mappings used vague “appropriate XAverius error” language and did not explicitly cover device state. The normative shader/pipeline chapter, central error map, conformance checklist, and static checker now distinguish invalid/non-live input XIDs (`BadValue`), wrong live type/foreign ownership/Cross-Device combinations (`BadMatch`), unavailable/lost devices (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`), and backend allocation failures (`ALLOCATION_FAILED`). Failed creation leaves no public target resource. This audit does not define a new error for non-allocation shader compiler/backend failures; that remains a separate mapping question if Vulkan result coverage is expanded.

## CreateCommandPool error-map follow-up — 2026-10-22

The command-pool chapter specified queue-family and flag validation but did not explicitly define device-state errors or guarantee that failed creation leaves the target XID unused. The central error map also grouped pool creation with command-buffer stream errors, obscuring the creation-specific cases. `CreateCommandPool` now has a dedicated mapping for `BadLength`, `BadValue`, `BadIDChoice`, `BadMatch`, `DEVICE_UNAVAILABLE` / `DEVICE_LOST`, and `ALLOCATION_FAILED`; the normative chapter and conformance checklist require atomic creation. The static checker guards these requirements. No runtime backend test is claimed.

## AllocateDescriptorSets error-map follow-up — 2026-10-22

The descriptor-set allocation request already had atomic-batch semantics and basic XID mapping, but its error table omitted unavailable/lost-device outcomes and did not fully separate unknown input XIDs from wrong live types/foreign ownership. The normative descriptor-set section, central mapping, and conformance checklist now distinguish `BadValue`, `BadMatch`, `BadIDChoice`, `DEVICE_UNAVAILABLE` / `DEVICE_LOST`, and `ALLOCATION_FAILED`; rejection leaves no partial set allocation. Static checker coverage was added. Runtime Vulkan allocation failure injection remains untested.

## FreeDescriptorSets atomicity and device-state follow-up — 2026-10-22

`FreeDescriptorSets` already rejected pending/recording references, but the normative section did not spell out all-or-nothing behavior for a batch containing an invalid set, nor did it state unavailable/lost-device outcomes. The request chapter, central mapping, conformance checklist, and static checker now require `BadValue` for unknown/non-live XIDs, `BadMatch` for wrong live types/ownership/pool mismatch, `DEVICE_UNAVAILABLE` / `DEVICE_LOST` for device state, and `INVALID_SYNCHRONIZATION_STATE` for prohibited references. Any rejection frees no subset of the requested sets.


## UpdateDescriptorSets descriptor-type validation — 2026-10-22

CI passed on the reviewed branch in [run 39825499901](https://github.com/metux/xav-design/actions/runs/39825499901), including all 2,223 static checks and the golden wire-vector tests.
The descriptor update path previously described descriptor-type incompatibility as `BadMatch` without clearly separating unassigned wire values from a registered type that conflicts with a layout binding. The normative chapter now maps zero/unassigned `descriptor_type` values and duplicate writes to one slot to `BadValue`, while a registered but incompatible type remains `BadMatch`. The central error table, conformance checklist and static checker now assert this distinction. This is a specification-level validation correction; backend runtime behavior is not yet tested.


## Descriptor contents and command-buffer references — 2026-10-22

CI passed in [run 39826027013](https://github.com/metux/xav-design/actions/runs/39826027013), with 2,225 static checks and the golden wire-vector tests.
A cross-chapter lifetime review found that the spec tracked indirect Buffer references from recorded command buffers but did not explicitly say how those references react when a Descriptor Set is updated while not pending. The contract now states that command buffers retain the Descriptor Set object rather than a snapshot of its contents; successful `UpdateDescriptorSets` atomically refreshes indirect Buffer references for all non-pending command buffers referencing the set. An executable command buffer uses the current set contents at submission and is not invalidated solely by the update. The decision record, command-recording chapter, lifetime chapter, conformance checklist and static checker are aligned. Backend execution behavior remains untested.

## QueueSubmit semaphore-entry validation — 2026-10-22

A focused audit of the `QueueSubmit` path found that duplicate wait/signal entries and a semaphore appearing in both arrays were prohibited normatively, but their synchronous error code was not explicit. The queue-submission chapter and central error map now define these conflicts as `BadValue`. The conformance checklist also covers Binary semaphore zero values, Timeline signal reservation checks, rejected-submit atomicity, and the guarantee that a rejected request reserves neither its token nor semaphore operation slots. Static checks guard the normative prohibition and the new conformance cases. CI passed in [run 39828130540](https://github.com/metux/xav-design/actions/runs/39828130540). This is protocol/specification validation; no live Vulkan backend is available to test runtime behavior.

## SignalSemaphore error-precedence audit — 2026-10-22

`SignalSemaphore` had detailed Timeline counter rules, but its own request section did not explicitly spell out exact-length, XID/ownership, and unavailable/lost-device errors. The synchronization chapter, central error map, conformance checklist, and static checker now cover those outcomes and require device/XID checks before counter/reservation validation. CI passed in [run 39828317685](https://github.com/metux/xav-design/actions/runs/39828317685). This is a specification/static-check result; no runtime backend test is claimed.

## Host semaphore wait/signal error audit — 2026-10-22

`SignalSemaphore` now explicitly maps request length, XID/ownership, and device-state errors before validating Timeline counter/reservation rules. `WaitSemaphores` now explicitly maps its exact count-derived length, zero count, duplicate XIDs, invalid mode, XID/type/ownership and cross-device errors, and distinguishes Device Loss from `DestroyDevice` termination. The central error map, conformance checklist and static checker cover the same behavior. CI passed in [run 39828507464](https://github.com/metux/xav-design/actions/runs/39828507464). Runtime backend behavior remains untested.

## WaitForFence request-validation audit — 2026-10-22

`WaitForFence` now explicitly specifies its fixed 24-byte request length, XID/type/ownership checks before wait registration, and the normal reply statuses for timeout, execution failure, device loss, and device destruction. The central error map, conformance checklist and static checker were aligned. An initial checker run exposed that the older ABI guard required the literal phrase “Request: 24 Bytes”; the normative wording and assertion were aligned, and CI passed in [run 39828776699](https://github.com/metux/xav-design/actions/runs/39828776699). No runtime server behavior is claimed.
