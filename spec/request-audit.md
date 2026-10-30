## Physical-device metadata query precedence audit — 2026-10-29

The two physical-device metadata queries had only a partial central mapping: exact length and unknown-XID outcomes were listed, while the live wrong-type phase and the meaning of a still-live but removed/failed Physical Device were not stated together as one normative order. `GetPhysicalDeviceQueueFamilyProperties` and `GetPhysicalDeviceMemoryProperties` now both define exact 12-byte framing → Physical-Device XID resolution → live resource-type validation → immutable server-stored metadata snapshot. They do not perform logical-Device availability checks or backend calls; operational requests such as `CreateDevice` and `AllocateMemory` retain their own current-availability checks. Conformance now tests the competing length/XID/type failures and verifies metadata stability after physical-device removal/failure. Static tests enforce agreement among both request chapters, the central error map, and conformance vectors.

## Semaphore reservation identity and Device Loss callback race audit — 2026-10-29

The semaphore audit found that submission-level idempotent terminalization and exact internal semaphore references were specified, but the matching rule for an individual semaphore reservation was not as explicit as the Fence callback identity/generation rule. The normative text now assigns each wait/signal operation a unique reservation identity tied to the exact internal semaphore identity. State mutation and reservation release require that exact reservation to remain current; callbacks never resolve or clear reservations by numeric XID alone. Device Loss and callback publication share serialization, timeline counters remain monotonic under out-of-order completion, and delayed/duplicate callbacks cannot publish success after loss or clear another operation's reservation. Added static regression assertions and conformance obligations for binary payload uncertainty, timeline signal reservations, and Device Loss callback interleavings. These tests validate specification contracts only; backend runtime race testing remains open.

## ResetFence and stale submission-callback race audit — 2026-10-29

The Fence audit now explicitly serializes `ResetFence` with submission terminalization and new submission acceptance. A successful reset advances an internal use generation; each accepted submission captures the Fence identity, generation, and association. Delayed or duplicate callbacks from an older submission cannot overwrite a Fence after reset/reuse. Regression coverage asserts the ordering contract and the stale-callback guard. Static tests do not replace runtime race testing against a backend.

## Fence wait/destruction precedence audit — 2026-10-29

The fence request cross-check found that `WaitForFence` described its XID failures and terminal statuses but did not state the complete validation order, while `DestroyFence` described lifetime blockers without explicitly ordering them after XID/type/ownership checks. The normative synchronization chapter and central error map now agree on the phase order. `WaitForFence` explicitly keeps `DEVICE_LOST` and `DEVICE_DESTROYED` as normal reply statuses and defines their race by which terminal result was established first; `DestroyFence` explicitly permits logical cleanup after Device Loss unless ordinary validation or a live lifetime blocker rejects it. Regression coverage checks phase ordering, status precedence, and agreement between the two chapters. These are static specification checks, not evidence of runtime backend conformance.

## Request-wide error-precedence follow-up — 2026-10-29

The all-request pass found one concrete ordering gap in `SelectEvents`: the defining chapter listed its individual error cases, while the central error chapter placed the XGE prerequisite before scalar validation without stating whether that order was normative. This conflicted with the common framing/scalar/XID ordering rule. Both normative chapters now define the same phases: exact length; scalar scope/reserved/mask validation; applicable Device-XID resolution; type/ownership; XGE negotiation; queue existence; atomic mask replacement. Regression coverage checks the phase order in both chapters and preserves the prior selection on rejection. This is a specification consistency correction; it does not change request layouts, subopcodes, or event IDs.

The request-wide static audit remains distinct from runtime conformance. The complete request inventory and cross-chapter precedence tests are the regression oracle; live X11/XGE interoperability and Vulkan backend acceptance remain open implementation gates.

# Request catalogue and wire-contract audit — 2026-10-21

## Request-specific error-precedence cross-check — 2026-10-27

The shared wire-protocol rule now distinguishes invariant envelope/header checks from request-local ordering among scalar validation, XID resolution, ownership/type, lifecycle, and mutable-state checks. The current cleanup pass adds explicit precedence for `DestroyResource` and `FreeMemory`: Device Loss alone does not reject logical cleanup, terminalized work is no longer a blocker solely because it was formerly pending, while live recording references, bound buffers, and uncertain backend access retain their normal blockers or quarantine requirements. The checker audits the explicit ordering contracts for `CreateDefaultDevice`, `CreateBuffer`, `AllocateMemory`, `CreateDescriptorSetLayout`, `CreateDescriptorPool`, `BindBufferMemory`, `UpdateDescriptorSets`, `CommandBufferData`, `QueueSubmit`, `WaitSemaphores`, `SignalSemaphore`, and all seven presentation requests, and retains the central create-XID versus input-XID distinction. Regression tests specifically guard the differing `WaitSemaphores` and `SignalSemaphore` orderings rather than incorrectly forcing them into one identical phase order. These are static specification-consistency checks, not tests against a running server.


## Presentation registry value-coverage audit — 2026-10-23

Added a golden-registry test for the future presentation profile. It now verifies that presentation event IDs 7 (`IMAGE_RELEASED`) and 8 (`PRESENTATION_COMPLETE`) extend, without colliding with, the compute baseline IDs 0–6; that the combined event namespace remains contiguous through 8; and that presentation-local terminal status values remain exactly 0–4 (`SUCCESS`, `OUT_OF_DATE`, `SURFACE_LOST`, `DEVICE_LOST`, `PRESENTATION_FAILED`). It also asserts that the registry remains explicitly outside compute-only v0.1 and that presentation-only queue mask bits are rejected there.

CI: [39965463283](https://github.com/metux/xav-design/actions/runs/39965463283) passed. Commit: `f8ce010` (registry stability test). This is a guard against silent value drift; it does not promote presentation events into compute-only v0.1. `master` remains unchanged.

## Registry drift and presentation-profile mask audit — 2026-10-23

The event/error registry cross-check confirms that the golden XGE tests already fail when the seven compute-baseline event IDs, event-local enum values, shared reason codes, or v0.1 error offsets drift from their registries. The standalone wire checker now also explicitly ties the `ASYNC_ERROR.error_code` range to offsets 0–8 in `registries/errors.md`, preserving the distinction between an extension-relative offset and an absolute X11 error code.

The SelectEvents audit found a profile-boundary gap in the test coverage: queue mask bits 2 and 3 correspond to presentation-only event IDs 7 and 8, but must be rejected by the compute-only v0.1 profile. The test encoder and raw-wire validator now check both modes explicitly: compute-only rejects those bits; a presentation-capable profile accepts them. The test cross-checks the separate presentation event registry and exercises both byte orders. This is test coverage for the existing normative profile distinction, not an assignment of presentation events to compute-only v0.1.

Commits: `7654b7a` (central error-registry range guard), `a41a44c` / `b4a92b9` (profile-gated SelectEvents mask tests and assertion correction). CI run [39964812429](https://github.com/metux/xav-design/actions/runs/39964812429) passed after the test correction. `master` was not modified.

## CommandBufferData and ResetCommandBuffer follow-up — 2026-10-22

The command-recording pass made the five permitted CREATE/FINAL/ABORT combinations explicit in conformance coverage and tightened deterministic error handling: malformed/incomplete entry headers versus invalid entry lengths, CREATE target-XID collisions versus missing input buffers, and the exact parent-pool check even for ABORT. It also records the required recovery guarantees: failed chunks are atomic, failed FINAL leaves the buffer RECORDING, failed CREATE leaves no public buffer or pool-child entry, and rejected ResetCommandBuffer preserves state and references. Static checks now guard these cross-chapter statements. These are documentation and static consistency checks only; runtime server behavior remains untested.
The follow-up's static checker passes on branch `docs/restructure-2026-10-21` in [CI run 39825028342](https://github.com/metux/xav-design/actions/runs/39825028342), including the golden wire-vector tests. The checker currently reports 2,221 checks; this remains static contract coverage rather than runtime Vulkan/X11 interoperability.

## Scope

This audit compares the currently defined request inventory in [the central request subopcode registry](../registries/request-subopcodes.md) with the defining chapters for wire layout, exact or formula-based request length, request kind, common framing, and request-specific error behavior. It is a cross-chapter consistency review, not a claim of complete Vulkan conformance or a frozen v0.1 protocol.

## Inventory result

- The registry contains 47 assigned request contracts: the 40-request compute baseline plus seven requests gated on the presentation-capable profile.
- Every registered request has a defining specification chapter.
- The registry's Reply, Void, and Void + async-events classifications agree with the chapter descriptions for all 47 assigned requests.
- The common X11 framing rules specify an 8-byte request header, four-byte request-length units, zero padding, no BIG-REQUESTS in v0.1, and standard 32-byte X11 replies/errors.
- The second systematic pass found several cross-chapter discrepancies and underspecified reply fields. These are recorded below and corrected in follow-up commits; the earlier pass must not be read as a claim that every contract was already consistent.

## Cross-chapter correction made during this audit

An outdated sentence in `DECISIONS.md` incorrectly included Fence and Semaphore in the eligible targets for `DestroyResource`. The normative lifetime chapter, error mapping, conformance cases, and request registry consistently exclude those types and require `DestroyFence` and `DestroySemaphore`. The decision log now matches the normative rule. The project status next steps were also refreshed to remove an obsolete BIG-REQUESTS/64-KiB reconciliation task.

## Known exclusions and unresolved items
1. `SelectEvents` is included as subopcode 40. Its wire layout, scope semantics, XGE negotiation prerequisite, dynamic `QueryExtension` discovery, extension-opcode range, and event framing are specified and statically checked; only implementation-level interoperability remains.
2. The v0.1 feature-ID and device-extension registries are explicitly empty, and the physical-device property/Atom-name registry defines four properties. Their basic error mapping and conformance cases are now covered.
3. Implementation-level backend conformance remains open as listed in [open issues](open-issues.md); same-queue order, no implicit cross-queue order, explicit semaphore dependencies, and the absence of fairness or bounded-latency guarantees are now specified in [queue submission](queue-submission.md). Timeout semantics for `WaitSemaphores` and `WaitForFence` now define monotonic deadlines, zero/infinite timeout behavior, terminal-state precedence, and device-loss handling. The v0.1 wait-stage mapping, queue-family compatibility rules, and invalid-mask error precedence are also explicit in [queue submission](queue-submission.md), [synchronization](synchronization.md), [error mapping](errors.md), and the conformance checklist.
## Host-wait error-versus-reply distinction — 2026-10-22

A cross-chapter review found that the general error-class table described `DEVICE_DESTROYED` for an open host wait without distinguishing the two wire contracts. `WaitSemaphores` reports `DEVICE_DESTROYED` as an X11 error, while `WaitForFence` reports the same-named condition as normal reply status `4`. The error table now states that distinction explicitly; the numeric namespaces and request semantics are unchanged. This is a documentation consistency correction only. CI status for this follow-up commit has not been verified.

## Subopcode allocation policy

The 40 compute-baseline requests retain explicit values 1 through 40. The seven presentation-capable requests are now appended at values 41 through 47. Value 0 is reserved and MUST NOT identify a request. All numbers are stable: later requests MUST use an unused value and MUST NOT renumber an existing request. `SelectEvents` remains subopcode 40; no pre-existing assignment changed.


## Historical findings from the second systematic pass (resolved)

The following items were found during an earlier audit pass and have since been addressed in the defining chapters, central error mapping, registries, conformance checklist, or this audit metadata. This list is historical context, not a list of currently open defects:

1. **Descriptor support cross-check:** the current descriptor registry and conformance contract both correctly restrict v0.1 to `STORAGE_BUFFER`; uniform buffers and image descriptors remain unsupported. No registry change was needed.
2. **Shader-stage symbol mismatch:** the central wire registry names the v0.1 bit `COMPUTE`, while the initial example used `COMPUTE_SHADER`. The example must use the XAverius wire symbol, not a native Vulkan spelling.
3. **Discovery reply completeness:** `EnumeratePhysicalDevices` and `GetPhysicalDeviceQueueFamilyProperties` describe variable reply records but do not explicitly state the corresponding `reply.length` formula. `GetPhysicalDeviceProperty` names statuses without assigning numeric values.
4. **Reply/request contract precision:** the fence-status reply describes the status byte and trailing reserved bytes but leaves the standard reply fields between offsets 2 and 7 implicit. The contract should explicitly separate standard X11 header fields from reserved bytes.
5. **Error-mapping coverage:** several requests rely on the general error chapter without spelling out all Create-XID, field-value, backend-allocation, or status-reply outcomes. The central rules must be applied consistently; no Void request may silently turn a normal status into a reply.

6. **Create-XID versus input-XID handling:** the general `BadIDChoice` rule was not explicit enough in several pipeline and chunked-create cases, and a few duplicate/count conditions lacked a concrete error. The error chapter now distinguishes target-XID collisions from missing input resources and assigns deterministic errors to the invalid duplicate-entry cases.
7. **Audit metadata drift:** the earlier registry-completeness statement and unresolved list became stale as the registries and request inventory grew. This audit now reports the current 47-request inventory and keeps only implementation-level interoperability as an open v0.1 validation item.

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
| 41 | `CreateSurface` | Void | 16 |
| 42 | `DestroySurface` | Void | 12 |
| 43 | `GetSurfaceCapabilities` | Reply | 16 |
| 44 | `CreateSwapchain` | Reply | 48 |
| 45 | `DestroySwapchain` | Void | 12 |
| 46 | `AcquireNextImage` | Reply | 32 |
| 47 | `QueuePresent` | Reply | `40 + 4*wait_semaphore_count` |

Here `pad4(n) = (n + 3) & ~3`. Every formula must be evaluated with checked arithmetic before allocation or parsing. Counts and the actual packet length must agree exactly; extra trailing bytes are not permitted unless the request definition explicitly includes them.

### Presentation-capable profile: provisional request/reply matrix

The presentation chapter is normative for the presentation-capable profile. Its seven requests are now assigned append-only subopcodes 41–47 and are included in the central request matrix; the separate profile matrix remains as a profile-gating and wire-layout cross-check. Request lengths below include the standard 8-byte XAverius header; reply totals include the standard 32-byte X11 reply header.

| Request | Kind | Total request length | Total reply length |
|---|---|---:|---:|
| `CreateSurface` | Void | 16 | — |
| `DestroySurface` | Void | 12 | — |
| `GetSurfaceCapabilities` | Reply | 16 | `64 + 8*format_pair_count + 4*present_mode_count + 8*queue_family_count` |
| `CreateSwapchain` | Reply | 48 | 40 |
| `DestroySwapchain` | Void | 12 | — |
| `AcquireNextImage` | Reply | 32 | 44 |
| `QueuePresent` | Reply | `40 + 4*wait_semaphore_count` | 36 |

For `GetSurfaceCapabilities`, the reply length field is `8 + 2*format_pair_count + present_mode_count + 2*queue_family_count` four-byte units. The variable counts and all aggregate-size calculations require checked wide arithmetic. `CreateSwapchain` has a 48-byte request but a 40-byte reply; the 40-byte reply consists of the standard 32-byte header plus `status` and `actual_image_count`. `AcquireNextImage` replies with `status`, `image_index`, and a zero reserved word. `QueuePresent` has a variable request and a fixed 36-byte reply.

This profile matrix is intentionally separate from the assigned 1–40 request matrix. It records request kind and lengths from [the presentation chapter](presentation.md#10-requestreply-wire-layouts) as an independent profile-gating cross-check; the actual 41–47 assignments are recorded in the central registry and main per-request matrix, and these requests are not part of compute-only v0.1.



## Cross-chapter consistency results

- **Request kind:** all 47 assigned request kinds agree with the defining chapter; `WriteBuffer` is a Reply request because its successful reply is the upload-completion/visibility boundary. `QueueSubmit` remains Void; post-acceptance outcomes are asynchronous.
- **Reply lengths:** discovery reply formulas and property status values are now explicit; fixed replies use `reply.length = 0` when all data fits in the standard 32-byte reply header. Variable data begins at byte 32 and `reply.length` counts four-byte units after that header.
- **Descriptor/stage values:** v0.1 supports `STORAGE_BUFFER = 1` only and the XAverius stage bit `COMPUTE = 0x00000001`; examples must not substitute native Vulkan enum names.
- **Error mapping:** the central error chapter governs XID liveness, live-type mismatch, ownership, Atom validation, Create-XID choice, validation order, and atomic rejection. Request-specific tables define the specialized state and backend failures. The specification-level ABI review is complete for the currently defined reply and XGE layouts. The remaining ABI task is live interoperability testing against an X11/XGE implementation; static checks do not establish runtime interoperability. The feature-ID, device-extension, and physical-device-property registries are defined for v0.1; XGE negotiation and event selection are specified. Timeout behavior and implementation-level backend conformance remain subject to their defining chapters and the open-issues register.

## Event-selection request addition — 2026-10-21

`SelectEvents` is now defined as a 32-byte Void request at subopcode 40. The request atomically replaces the selection for one connection, device, or queue scope; masks are scope-specific and `ASYNC_ERROR`/`DEVICE_LOST` are unmaskable. Conformance coverage was added. This adds one request without changing assignments 1–39.

## Reply and XGE ABI review — 2026-10-21

The specification-level ABI pass rechecked the standard 32-byte X11 reply header, fixed versus variable reply payload lengths, and all seven registered XGE event layouts against the event registry. The common XGE header is now explicit (GenericEvent response type 35, dynamic extension major opcode, 16-bit sequence, 32-bit length, static 16-bit `evtype`, zero reserved header bytes), and all event total lengths agree with `32 + 4 * length`: 60/7 for `ASYNC_ERROR`, 48/4 for four device events, and 56/6 for both submission events. Submission-event offsets, failure-class values, and the exactly-one-terminal-event rule are aligned. `SelectEvents` is checked as a 32-byte Void request with scope-specific fields and masks. Conformance cases now cover these layouts and reply padding. This closes the specification-level layout question for submission events; actual interoperability testing against an X11/XGE server remains an implementation-level task.

## Automated wire-layout checker — 2026-10-21

The repository contains `tools/check-wire-layout.py`, wired into `.github/workflows/wire-layout.yml`. The current checker cross-checks all 47 assigned request contracts (compute baseline 1–40 and presentation-profile-only 41–47) against this audit's request-kind/length matrix; checks selected fixed reply fields, reserved bytes, and variable reply-length formulas against their defining chapters; and parses every XGE event's field declarations to detect overlap, holes, alignment violations, out-of-bounds fields, incorrect total/XGE lengths, and registry-ID drift. It is deliberately a static Markdown contract checker. It does not parse every arbitrary formula into an expression tree and does not establish runtime interoperability; those remain separate conformance tasks.

## Expanded Reply ABI checker — 2026-10-21

The static checker now requires exact inventory coverage of all eleven Reply requests in the central registry and checks each against its defining chapter. Coverage includes fixed header/field/status contracts; `PHYSICALDEVICEINFO` variable record size, name length and padding; 12-byte `QUEUEFAMILYINFO` records; memory type/heap record sizes and count bounds; variable physical-property and `ReadBuffer` payload formulas; and the request/response completion contracts of `WriteBuffer` and `WaitSemaphores`. The GitHub Actions run on checker commit `03188b2904cb540b2107008e1e72e462b9b29ae6` passed 606 checks, including explicit boundary vectors for padding, record lengths, empty arrays, and maximum memory counts. This remains static Markdown validation and not live server interoperability.


## Error/conformance coverage follow-up — 2026-10-21

A further inventory scan found that `SelectEvents` had its error behavior defined in the event chapter but was missing from the central error-mapping chapter. Added its exact-length, XGE-negotiation, scope/mask, XID, ownership, and atomic-preservation mapping. The conformance checklist now also has explicit cases for `AllocateMemory`, `CreatePipelineLayout`, `CreateSemaphore`, and `CreateFence`, which were previously represented only indirectly.

The static wire-layout checker now requires every centrally registered request to be named in both the error guidance and conformance checklist. This is a presence/drift check, not a proof that each listed rule is exhaustive; request-specific semantics remain defined by the chapters and the central error mapping.


## Numeric registry integrity follow-up — 2026-10-21

The static checker verifies uniqueness and expected ranges for the 47 assigned request subopcodes (40 compute-baseline plus seven presentation-profile-only), nine event-type IDs across the profile-gated registries, contiguous error offsets, five command-entry IDs (including the presentation-only copy entry), descriptor-type assignments, physical-device types, queue-flag bits/masks, the v0.1 compute shader-stage bit, and physical-property type IDs. It also checks that the v0.1 optional feature-ID and device-extension registries remain explicitly empty. The request, event, and error checks detect duplicate names/values and missing assignments; other registries are checked against their current v0.1 supported assignments.

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

## GetFenceStatus request-validation audit — 2026-10-22

`GetFenceStatus` now explicitly defines exact request length, XID/type/ownership validation, and the requirement to return the stored fence state after Device Loss. The central error map, conformance checklist and static checker now guard this contract. CI passed in [run 39828908220](https://github.com/metux/xav-design/actions/runs/39828908220), including the golden wire-vector tests. Runtime backend behavior remains untested.

## Fence status/reset validation audit — 2026-10-22

`GetFenceStatus` and `ResetFence` now explicitly define exact request length, Device/Fence XID validation, wrong-live-type/ownership/cross-device errors, and behavior after Device Loss. The central error map, conformance checklist and static checker guard the same contracts. CI passed in [run 39829069365](https://github.com/metux/xav-design/actions/runs/39829069365). No runtime backend behavior is claimed.

## GetSemaphoreCounterValue request-validation audit — 2026-10-22

`GetSemaphoreCounterValue` now specifies its exact 16-byte request length, Device/Semaphore XID and ownership validation, Timeline-only constraint, and post-Device-Loss `DEVICE_LOST` behavior. The central error map, conformance checklist and static checker cover these rules. CI passed in [run 39829221170](https://github.com/metux/xav-design/actions/runs/39829221170), including golden wire-vector tests. Runtime backend behavior remains untested.

## ResetCommandBuffer device-state and command-buffer recovery audit — 2026-10-22

A cross-chapter pass found that ResetCommandBuffer defined XID/type/ownership and pending/reset-flag errors, but omitted the outcome for a live logical Device that is unavailable or lost. The normative command-recording chapter, central error mapping, conformance checklist and static checker now consistently require DEVICE_UNAVAILABLE / DEVICE_LOST after XID/ownership validation and before pool-flag or buffer-state validation. The checker wording was also reconciled with the updated conformance phrase. CI passed on the working branch in [run 39830304211](https://github.com/metux/xav-design/actions/runs/39830304211): 2,234 static checks and 90 golden wire-vector tests. This is a specification/static-check result; no live XAverius/Vulkan backend is available for runtime testing.

## Duplicate CreateCommandPool error-map reconciliation — 2026-10-22

The cross-chapter pass found that the detailed CreateCommandPool mapping and command-recording chapter correctly classified a queue-family index outside the logical Device profile as BadValue, while a later summary line ambiguously classified an invalid Queue Family as BadMatch or BadValue. The duplicate summary now agrees with the detailed rule: unknown/non-live Device XID is BadValue; wrong live type or foreign Device ownership is BadMatch; a Queue-Family index outside the Device profile or lacking command-buffer support is BadValue. The static wire-layout checker now guards against reintroducing the conflicting summary wording. The change is committed, but no CI result is available for this commit yet.

## WaitForFence reply-status ABI correction — 2026-10-22

A renewed cross-check found a real mismatch: the normative `WaitForFence` status table defines `DEVICE_DESTROYED = 4`, but the golden-reply validator and its positive status-coverage test only accepted values 0–3. The negative vectors also incorrectly treated 4 as invalid. The validator and tests now accept all five defined statuses, the negative vectors use 5 as the out-of-range value, and Little-/Big-Endian golden replies cover `DEVICE_DESTROYED`. The reply-spec coverage test now extracts and verifies all five status assignments. `GetFenceStatus` remains a separate four-value namespace (0–3); it was intentionally not widened.

This correction aligns the reply ABI tests with the existing normative synchronization and error chapters; it does not change the protocol assignment. The conformance checklist's concise WaitForFence status summary was also expanded to include `DEVICE_LOST` and `DEVICE_DESTROYED`, matching its detailed terminal-state cases. The updated commits have been saved on `docs/restructure-2026-10-21`. CI status could not be confirmed through the available status interfaces, so this audit note does not claim a passing run.


## CreateCommandPool queue-family error detail — 2026-10-22

The request-specific error summary already classified both out-of-profile queue-family indices and queue families that do not support command buffers as `BadValue`, while the detailed `CreateCommandPool` section mentioned only out-of-profile indices. The detailed mapping now covers both conditions, and the checker ties that mapping to the normative command-pool requirement. This is a documentation/static-check consistency fix; no new runtime or CI result is implied.
## Device Loss and explicit resource teardown — 2026-10-23

A cross-chapter audit found a direct contradiction: the lifetime state-transition summary said Device Loss immediately invalidated every public XID, while `GetFenceStatus` explicitly remains available after Device Loss and `DestroyDevice` has a defined post-loss cleanup path. The lifecycle rule now distinguishes a lost-but-still-addressable logical Device from explicit device teardown: Device Loss terminalizes accepted work and marks affected state, but public XIDs remain valid for the status-query and cleanup requests whose contracts permit them. `DestroyDevice` or client disconnect triggers public cascade invalidation. The synchronization destroy summaries and conformance checklist now use that same boundary, and the static checker guards it. This is a spec consistency correction; runtime teardown/quiescence still needs implementation tests.

## Recorded-reference lifecycle matrix correction — 2026-10-23

A systematic comparison of the summary destruction matrix against the normative recorded-reference rules found that the `DescriptorSet` row only mentioned pending use, and the `Pipeline` row only mentioned accepted work. That understated the general rule: a destroy/free operation must be rejected while a `RECORDING` command buffer retains the object; after successful destruction, non-pending `EXECUTABLE` command buffers retaining the object are invalidated. The matrix now states both rejection and invalidation behavior explicitly for `DescriptorSet`, `Pipeline`, and `PipelineLayout`. The conformance checklist has matching explicit cases, and `tools/check-wire-layout.py` now guards the summary rows against future drift. These are specification-consistency corrections; runtime behavior still requires implementation testing.
Follow-up during the same audit: `FreeDescriptorSets` was the outlier among resource cleanup operations because its error mapping rejected a lost Device even though it is a logical free operation and the related pool destruction path permits teardown. The request now remains usable after Device Loss, subject to the existing atomic pending/recording-reference guards. It must not start new Vulkan work, and backend references are retained until safe quiescence. The error map, normative descriptor-set section, conformance checklist, and static checker agree on this exception.


## Pool destruction after Device Loss — 2026-10-23

A follow-up lifecycle audit checked dedicated pool cleanup against the rule that Device Loss preserves public XIDs until explicit teardown. The normative request chapters now state that Device Loss alone does not prohibit logical `DestroyCommandPool` or `DestroyDescriptorPool`: terminalized submissions no longer count as pending uses, while descriptor sets referenced by a still-`RECORDING` command buffer continue to block descriptor-pool destruction until that command pool is destroyed. Error mapping and conformance cases match, and the wire-layout checker guards the cross-chapter contract. Internal backend references still require proven quiescence or quarantine; this does not claim runtime server behavior.


## Complete resource-specific cleanup policy after Device Loss — 2026-10-23

The follow-up audit generalized the pool finding across resource-specific cleanup. The lifecycle chapter and conformance checklist now explicitly state that Device Loss alone does not blanket-reject logical destroy/free requests: ordinary ownership, recording-reference, pending-use, and backend-safety guards remain authoritative. Terminalized submissions and host waits no longer block solely because they were formerly pending. `FreeMemory` remains blocked while an internally live Buffer is bound or backend access to the allocation is still possible. The wire-layout checker guards this policy; backend quiescence and runtime behavior remain implementation-level requirements.


## Interrupted shader and command-buffer data transfer audit — 2026-10-23

The chunk-transfer review aligned failure and event semantics across `ShaderModuleData`, `CommandBufferData`, the central error map, conformance cases, and XGE documentation. Shader chunk validation/`FINAL` failures synchronously report the offending X11 error and discard the whole private assembly; disconnect/device loss removes the incomplete assembly so later chunks cannot resurrect it. Command-buffer chunk errors remain atomic per request, preserve prior accepted chunks for retry/ABORT, and failed FINAL remains `RECORDING`. After Device Loss, CREATE/append/FINAL recording requests fail without changing prior state, while ABORT remains a logical cleanup path if the live buffer/pool and recording-state checks pass. Neither kind of pre-submission chunk failure emits `ASYNC_ERROR`; Device Loss reporting remains its independent device-level event path. Static checker coverage is being added; this is not runtime backend validation.


## Command-buffer finalization and QueueSubmit acceptance atomicity — 2026-10-23

A state-transition audit checked the `RECORDING` → `EXECUTABLE` finalization path and the `EXECUTABLE` → `PENDING` submission path against error precedence, resource references, fences, binary/timeline semaphore state, and the client-scoped `submission_token`. The command-recording chapter now explicitly requires failed FINAL validation to discard the whole current chunk while preserving the prior recording and its references. Queue submission now has an explicit validate-then-commit model: only one serialized acceptance point consumes the token, creates the submission, marks command buffers pending, reserves fence/semaphore operations, and commits internal references. Every pre-acceptance rejection leaves those states untouched and emits no submission event or `ASYNC_ERROR`. Error mapping, conformance cases, and the static checker were updated to require the same contract. This is specification and static consistency work; it does not prove runtime backend atomicity.


## CommandBufferData and QueueSubmit error-precedence audit — 2026-10-23

A systematic precedence review found that the general rule (wire structure, field values, XID/type/ownership, then state/backend checks) was not fully spelled out for these two requests, and the QueueSubmit error table listed mutable command/synchronization states before Device Loss even though its normative acceptance procedure checked Device state first. The CommandBufferData chapter and error map now define the phases explicitly, including target-XID-before-pool-XID ordering, CREATE/Append/FINAL Device-state precedence, and ABORT's logical-cleanup exception after Device Loss. QueueSubmit now specifies exact XID resolution order and places Device Unavailable/Lost after XID/type/ownership/queue checks but before mutable submission-state checks; syntax-only masks/token/duplicate checks precede XID resolution, while type-dependent semaphore values are checked after type/device validation. Conformance cases and static assertions cover mixed-failure combinations and ensure rejected requests remain non-mutating. These are specification/static checks, not runtime backend tests.

## XGE event negative-fixture and stale resource-XID audit — 2026-10-23

The event review found that `ASYNC_ERROR.resource_xid` had no explicit rule for a resource destroyed after accepted work retained its internal identity but before a delayed diagnostic was enqueued. Without a wire rule, a reused numeric XID could misidentify a new resource. The event and lifetime chapters now require `resource_xid = 0` when the affected resource is no longer publicly live at the event's serialization point; callbacks must carry internal identity and must not re-resolve a numeric XID. Device-destruction suppression remains stricter: no new event is emitted for the destroyed Device identity. Conformance cases, the static checker, and executable Little-/Big-Endian golden-frame tests cover the distinction. CI passed in [run 39963955754](https://github.com/metux/xav-design/actions/runs/39963955754), including the wire-layout checks and golden wire-vector suite. These are protocol/specification tests, not runtime X11-server or Vulkan-backend tests.


## Request-subopcode registry and golden-vector cross-check — 2026-10-23

The central request registry and static wire checker enforce all 47 assignments (1–47), unique request names and numeric values, reserved subopcode 0, and a one-to-one match with the per-request audit matrix; the presentation request layouts remain profile-gated. The golden request-vector tests previously checked encoded bytes and framing but did not compare each fixture's request name and subopcode against the central registry. That meant a stale fixture could remain self-consistent after an assignment drift.

Added a cross-check in `tests/test_wire_vectors.py`: every golden vector must name a registered request, use that request's assigned subopcode, and carry the same value in wire-header byte 4. The test also checks uniqueness and reservation of zero in the parsed registry. This complements rather than duplicates the checker’s full contiguous 1–47 assignment check. Current golden byte coverage remains intentionally limited to `CreateBuffer`, `WriteBuffer`, and `ReadBuffer`; this change does not claim byte-vector coverage for all 47 request layouts.

Commit: `1d58cfe`. CI validation pending. `master` remains unchanged.


## Full request-matrix length cross-check — 2026-10-23

Rechecked all 47 assigned request-matrix rows against the defining normative chapters linked from the central request registry. No request-kind, fixed-length, or variable-length formula discrepancy was found in the current matrix. One important coverage gap was in the checker rather than the protocol text: the previous checker compared registry assignments with the matrix but did not systematically require the matrix's length rule to be present in the normative request section.

The wire-layout checker now validates all 26 fixed request lengths against their defining sections, all 13 arithmetic variable-length formulas against the normative formula and the matrix expression (including the pad4 shorthand), and the variable CommandBufferData minimum/ABORT lengths. This also caught a wording variation in CreateSemaphore (the chapter says “has a total length of 28 bytes” rather than “total length: 28 bytes”); the checker accepts both explicit forms, without changing the protocol contract. The current matrix contains all 47 rows (40 compute-baseline and seven presentation-profile requests), and request kinds continue to be checked against the central registry.

CI: [39967702408](https://github.com/metux/xav-design/actions/runs/39967702408) passed. Checker commit: `21b3643`. This is static specification consistency coverage, not live implementation interoperability. `master` remains unchanged.


## Ordinary request-size limit and BIG-REQUESTS framing audit — 2026-10-23

A framing review revisited the relationship between the standard X11 16-bit request length and the XAverius common header. BIG-REQUESTS places its extended length at offset 4, which is also the XAverius subopcode/flags/reserved header. The wire chapter already declared BIG-REQUESTS unsupported, but did not explicitly state the dispatch-time rejection rule or tie the 262140-byte limit and checked arithmetic to every variable-length request before allocation.

The normative framing rule now requires XAverius servers to reject requests whose original X11 16-bit `length` is zero with `BadLength` before interpreting offset 4 as the XAverius common header. All variable-length request formulas must be computed with checked arithmetic; overflow, an expected total above 262140 bytes, or disagreement between declared length, counts and actual packet end yields `BadLength` before payload allocation, XID resolution or state mutation. The maximum applies per wire request, including chunked uploads/recordings. The conformance checklist covers normal maximum length, oversized requests, zero-length/BIG-REQUESTS framing, overflow, and non-mutating failure. The static checker verifies this contract and that the request matrix still has exactly the expected 14 variable-length requests.

Commits: `c910c49` (normative framing), `91182a6` (conformance cases), `088b9f3` / `143cd26` (static checker and wording fix). CI passed in [run 39968407308](https://github.com/metux/xav-design/actions/runs/39968407308). This validates the specification and static checks; actual X server dispatch behavior still requires implementation-level testing. `master` remains unchanged.


## Repository-local Markdown link audit — 2026-10-23

Added a repository-wide local Markdown link check to the wire-layout validation workflow. It scans Markdown files, resolves relative destinations from each source document, rejects missing local targets and links that escape the repository, and reports the source path and line number. The check intentionally validates target paths rather than generated heading fragments; anchor-fragment validation remains a separate possible extension.

The first CI run passed with the new check enabled: [run 39968554690](https://github.com/metux/xav-design/actions/runs/39968554690). Checker commit: `b8da4ba`. This run found no broken local target paths in the current Markdown corpus. `master` remains unchanged.


## Request error/conformance coverage audit — 2026-10-23

Extended `check_error_registry` so error validation now cross-checks the complete request matrix (47 assigned requests in the current presentation-aware branch; 40 in a compute-only baseline) against the central subopcode registry, requires every registered request to appear in both `spec/errors.md` and `spec/conformance.md`, and guards the normative validation order and atomic-failure rules. This is a coverage floor, not a claim that every request has a separate exhaustive error table: shared rules are intentionally centralized, while request-specific precedence and exceptional cases remain in the error chapter.

The first run exposed a wording mismatch in the checker assertion (the normative text used the singular adjective form); the assertion was corrected without changing the protocol contract. The follow-up CI run passed: [run 39969925813](https://github.com/metux/xav-design/actions/runs/39969925813). Checker commit: `446f512`; wording assertion follow-up: `a9f83dc`. `master` remains unchanged.


## Multi-XID error precedence: binding and descriptor updates — 2026-10-23

A precedence pass found that the central error table listed bind/pending-state failures before Device Loss for `BindBufferMemory` and `UpdateDescriptorSets`, while both operations require a functioning logical Device and the shared policy gives Device-state failures precedence over request-specific state/backend checks. The request chapters now define explicit validation phases: framing/field syntax, XID resolution in wire order, type/ownership, Device state, then request-specific compatibility and mutable-state checks. The central mapping, conformance cases, and static checker now guard the intended mixed-failure outcomes. This is a specification/static-check result only; no live server or Vulkan backend error injection is available.


## Create and batch allocation error precedence — 2026-10-23

The next precedence pass covered `AllocateDescriptorSets`, `CreatePipelineLayout`, and `CreateComputePipeline`. Their error lists named all major error classes but did not consistently prescribe the winner when a request combines invalid target XIDs, invalid input XIDs, and Device Loss. The request chapters now define field-syntax → target-XID → input-XID wire order → type/ownership → Device state → device-dependent compatibility/capacity/backend order. Batch descriptor-set allocation checks every requested target XID before resolving input resources and remains all-or-nothing. The central error map, conformance cases, and static checker were aligned. This is a specification/static-check audit, not runtime backend fault injection.


## ResetFence Device-loss precedence — 2026-10-23

The synchronization chapter already stated that ResetFence is rejected after Device Loss, but the central error table listed the invalid-fence-state result first. The mapping now explicitly places Device Loss after XID/type/ownership validation and before the mutable fence-state check. Conformance coverage and the static checker assert that a lost Device wins over an otherwise non-resettable Fence state while preserving the stored state. This is a spec/static-check correction, not runtime validation.


## WaitSemaphores validation and terminal-result precedence — 2026-10-23

The synchronization pass made the distinction between initial request validation and an already registered wait explicit. `WaitSemaphores` now defines a single precedence order: framing/count/mode/duplicate syntax, Device then Semaphore XIDs in wire order, type/ownership/cross-device checks, Device state, and finally the Timeline-only requirement. This settles mixed-failure outcomes (a lost Device wins over a live Binary Semaphore type mismatch after ownership checks) without allowing malformed requests to register waits. Device Loss and `DestroyDevice` remain terminal outcomes only for waits already registered; an earlier terminal result cannot be overwritten. The central error mapping, conformance checklist and static checker now assert the same contract. This is a specification/static-check change, not live backend validation.

## SignalSemaphore validation precedence — 2026-10-23

The host-signal path now states a single mixed-failure order: exact 24-byte framing; Device then Semaphore XID resolution; resource type/ownership/cross-device validation; Device state; finally Timeline-only and counter/reservation consistency checks. A Device-loss result therefore takes precedence over a live Binary Semaphore type mismatch once XID and ownership validation has passed. Synchronous rejection is atomic and leaves both the observable counter and pending signal reservations unchanged. The error registry, conformance checklist and static checker assert this contract alongside the prior `WaitSemaphores` split between pre-registration validation and terminal outcomes.
## Presentation reply status-vector audit — 2026-10-25

The presentation reply vectors previously exercised only representative failure statuses for `GetSurfaceCapabilities`, `CreateSwapchain`, and `AcquireNextImage`, while `QueuePresent` had a complete 0–3 loop. Expanded the presentation reply test to exercise every currently documented status value for all four reply-bearing presentation requests in both X11 byte orders. The checks assert reply framing/word counts, status-field round-tripping, zero image index and reserved word on failed acquisition, zero actual image count on failed swapchain creation, and zeroed capability payloads/no variable records on non-success capability statuses.

The capability SUCCESS vector retains its variable-record fixture (92 bytes, `reply.length = 15`); non-success capability vectors are the 64-byte zero-payload base (`reply.length = 8`). This test expansion does not allocate new status values or change the wire contract. Commits: `13cc4b4` (status coverage), `96c37bb` (assert status fields and capability SUCCESS length). At the time of this 2026-10-25 entry, current-head CI was **unconfirmed**; the later 2026-10-26 check supersedes that snapshot, as recorded in the audit entry below. Do not interpret this as runtime presentation-race validation. `master` remains unchanged.
## Presentation lifecycle race conformance vectors — 2026-10-25

Added an explicit serialized-race matrix to `spec/conformance.md` for acquire timeout versus lifecycle transitions, DestroyDevice versus pending acquire, Surface destruction versus swapchain creation, Device destruction/loss versus swapchain creation, lifecycle changes during swapchain preparation, QueuePresent rejection versus atomic acceptance, accepted presentation terminalization, DestroySwapchain pending-reference checks, and uncertain binary-semaphore consumption after presentation failure. Each vector requires assertions for wire-visible outcomes and internal resource/image/token/semaphore/reference invariants, including masked-event cleanup cases.

This adds normative test obligations and clarifies the expected test oracle; it does not claim that a runtime server harness exists or that these race tests have executed. The earlier statement that current-head CI still needed confirmation was stale at the time of the follow-up: commit `98d9609f48dfba291aa0ad39c5b234fd3ff13263` passed `wire-layout` in [run 40303024899](https://github.com/metux/xav-design/actions/runs/40303024899), including syntax, request/reply/XGE layout checks, and golden-wire tests. The subsequent commits in this audit are documentation-only; GitHub exposes no status/workflow result for the final documentation commit, so its exact-commit CI status remains unconfirmed. This does not execute runtime race tests. `master` remains unchanged.


## Normative-source precedence and historical-draft drift — 2026-10-26

A source-of-truth audit found that the README linked the 2026-10-20 consolidated WIP as a preserved baseline without explicitly saying that it was non-normative. That snapshot still says BIG-REQUESTS follows standard X11 rules, while the current wire-protocol chapter and decision log disable BIG-REQUESTS for v0.1 because its extended-length field overlaps the XAverius common header. This could cause an implementer to treat the old statement as a competing rule.

The README and the WIP header now explicitly mark the consolidated draft as historical and direct readers to `spec/` and `registries/` as the authoritative working design. No protocol assignment or current normative rule was changed; the obsolete WIP statement is preserved for historical traceability but cannot override the current framing contract. The branch-head CI check remains static-only; live X11/XGE interoperability and Vulkan-backend conformance are still open implementation-level work.


## Timeline-Signalreservierungen und Fehlerpräzedenz — 2026-10-26

The semantic cross-check of QueueSubmit, SignalSemaphore, the error summary, and the reference tests found a conflicting error mapping: a Timeline signal value conflicting with an existing pending GPU-signal reservation was described as BadValue in the reference conformance text, although SignalSemaphore maps the same reservation conflict to INVALID_SYNCHRONIZATION_STATE. The rules now distinguish the cases clearly: a signal value not greater than the observable counter is an invalid value (BadValue); a value above the counter that violates an existing pending GPU-signal reservation is an invalid synchronization state (INVALID_SYNCHRONIZATION_STATE). QueueSubmit remains atomic before acceptance; the counter, token, and all reservations remain unchanged on rejection. The static checker enforces the same mapping in normative text, the error summary, and reference tests. This checks specification consistency, not runtime behavior of a XAverius/Vulkan server that does not yet exist.


## DestroyDevice cascade/callback race audit — 2026-10-27

The DestroyDevice lifecycle audit now defines one linearization point for cascading public invalidation, event-selection removal, and open-wait termination. Already terminal waits and replies serialized before that point retain their result. Accepted submissions still terminalize exactly once internally, while post-destroy event delivery is suppressed. Deferred callbacks and cleanup use immutable internal identities, not a second numeric-XID lookup; XID reuse cannot redirect old work, satisfy a new wait, or free a new allocation. Backend references remain retained or quarantined until access is known to be impossible. Added checker assertions and a negative-contract regression guard. This is a specification/static-contract check, not a live Vulkan backend race test. `master` remains unchanged.


## Cross-resource teardown and memory-reference audit — 2026-10-27

Cross-checked `DestroyDevice`, `DestroyResource` for Buffer, descriptor-slot references, command-buffer references, Buffer-to-Memory bindings, and `FreeMemory`. Public XID invalidation is not equivalent to dropping internal dependency edges. Device-wide teardown must internally retire each edge exactly once, preserve the old internal identity graph while submissions and backend accesses drain, and release backing memory only after the old Buffer identity and every possible access are safely retired. Ordinary `FreeMemory` remains rejected while an internally live Buffer is bound; after device cascade, cleanup must not re-enter public free semantics for already-invalidated XIDs. Added static contract checks and a negative regression guard. These are specification/static checks, not a runtime Vulkan-backend lifetime test; `master` remains unchanged.


## Descriptor update and set-release reference audit — 2026-10-27

Audited `UpdateDescriptorSets`, `FreeDescriptorSets`, and `DestroyDescriptorPool` as competing transitions over descriptor-slot values, derived command-buffer Buffer references, submission acceptance, and pool/set invalidation. Normative rules now require all-write validation before commit, atomic slot/reference replacement, exactly-once retirement of superseded slot edges, and serialization against submission and release. A successful update leaves executable command buffers executable but refreshes their derived Buffer dependencies; a removed dependency must not later invalidate a command buffer. Free/pool destruction validate all blockers before mutation, then invalidate target XIDs and affected executable command buffers atomically. Added static contract assertions and a negative-contract regression test. These are specification/static checks, not a runtime server/backend race test; `master` remains unchanged.


## Command-buffer reset/invalidation/reference-retirement audit — 2026-10-27

Audited the state machine across ResetCommandBuffer, resource-driven executable-buffer invalidation, accepted submission completion/failure, pool/device destruction, and rerecording. The spec now separates command-buffer-owned recorded edges from submission-owned references and backend holds; successful reset retires only edges still owned by that buffer, successful execution preserves recorded dependencies, and failure invalidates the buffer without allowing premature backend release. Cleanup paths must be idempotent and callbacks use immutable internal identities. Added static checker contracts and regression tests for reset rejection atomicity, invalidation/reset double-release, and fresh reference sets after rerecording. These checks validate specification contracts, not a live server/backend implementation. master remains unchanged.


## Repository-local Markdown anchor audit — 2026-10-28

Extended the existing repository-wide Markdown link check to validate generated heading fragments as well as local target paths. The check now covers same-document fragments, relative Markdown links, duplicate heading slugs, explicit HTML IDs, URL-encoded fragments, and paths escaping the repository. It found and corrected a stale WriteBuffer section link and a presentation command-entry link whose heading includes a profile qualifier. The checker follows GitHub-style heading slugs, including underscores. On commit `be14180755b17423577bc249f01713ab983ad594`, CI passed with 4,575 wire-layout/documentation assertions and all 549 Python tests. This validates repository-local links and static protocol consistency, not runtime X11/XGE interoperability or Vulkan backend behavior.

## Normative request-error precedence audit — 2026-10-29

Audited the 47 registered request contracts against the common validation stages in `wire-protocol.md`, request-specific mappings in `errors.md`, and the negative-case matrix in `conformance.md`. The common order remains: X11 envelope framing; invariant common-header fields; subopcode/profile dispatch; supported-request layout and checked length; then request-local scalar, XID, ownership/type, lifecycle, and backend checks. Documented local exceptions remain constrained to later phases and do not bypass the envelope/header/profile boundary.

No conflicting phase order was found in the reviewed request-specific contracts. One under-specified mixed-failure case was found in `GetPhysicalDeviceProperty`: the error map named `BadAtom` and Device-XID errors but did not say which wins when both inputs are invalid. The contract now explicitly orders exact length, Physical-Device XID resolution, live resource type, Atom validation, then property registry/availability lookup. The conformance matrix now covers the mixed pairs (malformed length + invalid Atom, unknown Device + invalid Atom, wrong live resource type + invalid Atom, and valid Device + invalid Atom), and a regression test checks the ordering and error-map agreement.

The automated checks here are specification/contract regression checks, not execution against a live X11 server. Server-side runtime tests must still exercise the same mixed-failure cases when an implementation exists.



## Freeze-checklist evidence refresh — 2026-10-30

The current working-branch commit `2f34416ebd665fa83f6c19c571ddf07110dccecb` was checked by GitHub Actions run [41065436558](https://github.com/metux/xav-design/actions/runs/41065436558). The `wire-layout` job completed successfully: `tools/check-wire-layout.py` reported 4,685 checks, the Timeline semaphore regression step passed, and the complete Python suite ran 655 tests with result `OK`. The final required-check audit also succeeded, confirming that every required step ran and returned success.

This evidence covers static specification/layout/registry consistency and executable reference-model/fixture regressions on that exact commit. It does **not** establish interoperability with a live X11/XGE server, behavior of a native XAverius server, Vulkan backend conformance, real GPU execution, or runtime concurrency/failure behavior. The tested commit is an evidence checkpoint, not the final freeze commit; the final edited candidate must receive its own successful run.


## English-language editorial pass and current CI checkpoint — 2026-10-30

The freeze-checklist review found that the English-only requirement in [the style guide](style-guide.md) was not met consistently: several normative chapters still contained German headings and substantive German text. This pass translated the Physical Devices and Device Ownership headings, the `WriteBuffer`/`ReadBuffer` ordering and snapshot contract prose, and the queue-submission finalization, queue-ordering, and synchronization-guarantee prose. The synchronization and command-recording headings were also normalized. Static test expectations were updated to assert the English normative wording rather than the old German phrases. No wire values or intended protocol semantics were changed.

The resulting working-branch commit `3c90c9d1e44e5c90a4155980b5ced0c261c99ec8` passed [CI run 41067862556](https://github.com/metux/xav-design/actions/runs/41067862556): 4,688 wire-layout checks, 72 dedicated Timeline regression tests, and all 655 Python tests passed. Every required CI step ran and the mandatory check-presence audit succeeded.

The editorial gate is still open. German normative prose remains in at least `spec/shaders-pipelines.md`, `spec/resource-lifetime.md`, `spec/errors.md`, and `spec/conformance.md`, as well as a historical-language heading/entry in this audit record. The checklist intentionally leaves the English-language style gate unchecked. The CI run verifies that the translation did not break current static contracts; it does not establish live X11/XGE or Vulkan-backend conformance.

## ShaderModuleData assembly cleanup identity boundary — 2026-10-30

A content review of the shader-upload contract and its reference model found that the phrase “any invalid chunk discards the entire assembly” was broader than the implementation could safely apply. A request truncated before the fixed header exposes `shader_module_xid` cannot identify which assembly should be discarded. Likewise, a rejected `CREATE=1` request is a new-create attempt and must not destroy an existing upload that already reserves the same XID. The normative rule now scopes cleanup to failed continuation/`FINAL` requests with a complete fixed header, an identifiable target XID, and `CREATE=0`. A truncated fixed header leaves assemblies unchanged; a failed CREATE leaves any pre-existing assembly unchanged. The error summary, conformance vectors, and reference model now assert these cases.

The updated branch checkpoint `a6c9a8fb04d56e0630121ccf52756dc250d79486` passed [CI run 41069851593](https://github.com/metux/xav-design/actions/runs/41069851593): 4,688 wire-layout checks, 72 Timeline regression tests, all 656 Python tests, and the mandatory required-check audit. These checks validate the written contract and reference model; they do not prove a live server's request-buffer handling or Vulkan behavior.
## CommandBufferData wire maximum, validation phases, and DescriptorSetLayout lifetime — 2026-10-30

A wire-boundary pass found that `CommandBufferData.entry_length` is a 16-bit word count, but its maximum legal value is lower than the field's representable maximum. The fixed request header is 16 bytes (four 32-bit words) and the ordinary X11 request limit is 65535 words, so one request can carry at most 65531 entry words (262124 bytes). A 65531-word entry plus the fixed header is exactly 262140 bytes; 65532 words cannot fit. The request chapter, command-entry registry, and conformance vectors now state the boundary, including aggregate-entry overflow and atomic rejection. The static checker asserts the arithmetic and the exact-boundary cases.

The same review found that one `CommandBufferData` conformance summary placed entry-local scalar/field syntax after XID and ownership checks, contradicting the normative phase order. It now distinguishes entry-local syntax (`BadValue` before XID resolution) from resource-dependent command compatibility (after XID, type/ownership, and Device checks). Mixed-failure vectors require the earlier-phase error.

A resource-lifetime pass also made the `DescriptorSet` → `DescriptorSetLayout` association explicit. After all intended `CreatePipelineLayout` and `AllocateDescriptorSets` requests using a layout have completed, its public XID may be destroyed. Existing allocated Sets remain valid and updateable because their immutable layout definition and internal backend-layout identity are retained until all dependent Sets are freed and backend access has ended. The old XID cannot be used for new `CreatePipelineLayout` or `AllocateDescriptorSets` requests (`BadValue`). The resource-lifetime summary now also explicitly states that successful `DestroyDescriptorPool` invalidates non-pending executable command buffers referencing its child Sets. Conformance vectors and static assertions cover these rules.

The exact candidate commit `006f8bee2fbf35fd055926827ef56de30dc74470` passed [CI run 41077796346](https://github.com/metux/xav-design/actions/runs/41077796346): 4,691 wire-layout/documentation checks, 72 Timeline regression tests, all 658 Python tests, and the mandatory required-check audit. These are static specification and reference-model checks, not live X11/Vulkan runtime conformance. `master` remains untouched.
## PipelineLayout destruction with live Pipeline dependencies — 2026-10-30

A follow-up resource-lifetime review found that the dependency graph already connected Pipeline to PipelineLayout, but the destruction contract did not distinguish that retained internal dependency from direct PipelineLayout use by command buffers or accepted work. The normative rules now separate them: direct `RECORDING` references and direct accepted pending use block public PipelineLayout XID destruction; a Pipeline-held dependency alone does not. Successful public invalidation leaves existing Pipelines live and retains the backend layout identity until all dependent Pipelines and backend accesses have ended. New `CreateComputePipeline` requests using the destroyed XID return `BadValue`. Direct command-buffer references still block while recording and invalidate non-pending executable command buffers after successful destruction.

The central error summary, resource-lifetime matrix, pipeline chapter, conformance vectors, and static checker now express the same distinction. The conformance matrix separately tests destruction while a submission uses only the Pipeline, direct pending layout use, direct recording references, and post-destruction pipeline creation.

The exact candidate commit `2c0e14559a34b4cb611846bf04fb6a3c59045b82` passed [CI run 41078714133](https://github.com/metux/xav-design/actions/runs/41078714133): 4,692 wire-layout/documentation checks, 72 Timeline regression tests, all 658 Python tests, and the mandatory required-check audit. These checks validate static specification and reference-model consistency, not live X11/Vulkan runtime behavior. `master` remains untouched.
