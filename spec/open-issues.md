# Remaining v0.1 issues and future maintenance

This file separates specification design gaps from implementation acceptance tests. A protocol rule can be fully specified before a server exists; static checks cannot prove runtime interoperability. The release gate is [the specification freeze checklist](freeze-checklist.md).

## Specification freeze status

The request registry defines 48 request contracts: common bootstrap `QueryVersion` at subopcode 0, compute-baseline subopcodes 1–40, and presentation-capable-profile subopcodes 41–47. Presentation requests and event types remain profile-gated; their assignment does not imply support in the initial compute-only implementation.

The latest exact-tip CI-verified specification baseline is `53883de2201029de82b63a03f6acc2ba77280e6a`, verified by [workflow 41840947750](https://github.com/metux/xav-design/actions/runs/41840947750): 4,963 wire-layout checks, 72 Timeline regressions, 693 Python tests, shared-header compilation, XCB client prototype build, request/reply/XGE validation, backend-discovery/handler/callback audits, and required-check audit all passed. The verified contract includes render/scanout separation, explicit PRIME/DRI3 bridge eligibility, exact logical-Device PresentationRoute binding, source-authority-validated physical removal, generation-checked provider status transitions, registry result classifications, and provider descriptor/pointer lifetime rules (architecture vector 60). Phase 1 ship confirmations and a named shared integration-interface owner remain coordination sign-offs. Runtime acceptance gates remain open and are listed below.

**Editorial note (not a protocol blocker).** Some normative and explanatory prose remains German while other chapters are English. This is a consistency/readability issue, not evidence of a protocol-design gap. Translation is deferred unless mixed-language wording makes a requirement ambiguous; content reviews must still verify the exact normative meaning regardless of language.

The request/error precedence audit and dedicated `QueryVersion` review cover all 48 registered requests. The exact candidate and CI run above verify the normative request/reply contract, both byte orders, malformed request headers and lengths, and reserved/version reply fields. Resource lifetime, asynchronous terminalization, callback identity, semaphore/fence reservations, and Device-loss behavior retain their dedicated normative audits and reference-model regressions. Passing static checks does not prove runtime behavior; implementation acceptance gates remain open.

### Closed normative audit — render GPU versus scanout GPU — 2026-11-04

The presentation contract now treats the logical Device's render GPU and the Surface's owning Screen/scanout GPU as independent. ScreenAttachment roles are topology only; the selected execution provider coordinates a direct WSI or explicit bridge route for the exact Device/Surface pair. PRIME/DRI3 bridging is permitted only when the provider can prove full format/modifier, usage, synchronization, ownership-transfer, and release/completion compatibility. The route is pinned to a Swapchain generation; topology changes make that Swapchain OUT_OF_DATE. No implicit GPU/provider/Screen/output migration is permitted. Permanent lack of a route maps to no present-capable queue and UNSUPPORTED_CONFIGURATION; temporary route unavailability and accepted route failure have explicit status mappings. No wire ABI changed. Candidate `013be364ea8cc7126b092f46d7c266b43dcda02f` requires exact-tip CI before verification.


## Implementation acceptance work (not a missing wire assignment)

1. **Open — live X11/XGE interoperability.** Exercise standard `QueryExtension("XAverius")`, the new XAverius `QueryVersion` request and 0.1 reply, dynamic major-opcode use, separate `GEQueryVersion` negotiation, `SelectEvents`, XGE framing, masks, byte order, and connection isolation against an actual X11/XGE server and XAverius implementation. Follow the [XGE interoperability test plan](xge-interoperability-test-plan.md). Documentation-only checks cannot prove interoperability.
2. **Open — compute backend conformance.** Validate queue ordering, successful `WriteBuffer` visibility, dispatch/readback, synchronization, Device loss, late callbacks, client disconnect, and resource teardown against an actual Vulkan backend.
3. **Open if presentation is implemented — presentation backend conformance.** Validate Window/Surface lifetime, swapchain creation, acquire/present/release transitions, resize/out-of-date, terminal event behavior, and device/connection teardown races. Keep these results separate from compute-only conformance.

These are implementation acceptance gates. They do not require inventing new request IDs or leaving already-defined layouts ambiguous. They remain open until a real implementation is exercised and evidence is recorded.

## Normative maintenance rules

These are settled rules, not open v0.1 design questions:

- **Request subopcodes:** common bootstrap `QueryVersion` uses subopcode 0; compute-baseline requests use 1–40; presentation-capable-profile requests use 41–47. Subopcode 48 is unassigned. The [central request registry](../registries/request-subopcodes.md) is append-only; existing assignments MUST NOT be renumbered.
- **Physical-device properties:** the five v0.1 properties and their wire representations are defined in the [property registry](../registries/physical-device-properties.md). Future properties must be registered append-only.
- **Feature IDs and device extensions:** future assignments must be registered append-only. The v0.1 optional sets are intentionally empty; see [feature IDs](../registries/feature-ids.md) and [device extensions](../registries/device-extensions.md).
- **Memory properties flags:** `memory_properties_flags` MUST be zero in v0.1 until a registry definition is explicitly assigned; see [memory properties](memory-buffers.md#52-getphysicaldevicememoryproperties).
- **Physical Device UUID and Driver UUID:** both are opaque 16-byte `BYTE_ARRAY` properties. The server preserves Vulkan-returned bytes exactly and MUST NOT fabricate unavailable UUIDs; see the [property registry](../registries/physical-device-properties.md).
- **Presentation profile boundary:** the initial implementation target remains compute-only. A server that does not implement the presentation-capable profile rejects requests 41–47 with core X11 `BadRequest` before payload parsing or XID resolution. Event IDs 7 and 8 and their queue-mask bits remain presentation-profile-only.

## Deferred to future protocol versions

These topics do not block the current contract unless a future version explicitly brings them into scope:

- **Queue fairness and bounded progress:** v0.1 defines same-queue submission order, no implicit cross-queue ordering, and explicit semaphore dependencies, but promises no fairness or bounded scheduling latency. See [queue submission and ordering](queue-submission.md).
- **X11 resource sharing:** cross-client or cross-device sharing is not implicitly provided by v0.1. Current ownership rules are in [device discovery](devices.md) and [resource lifetime](resource-lifetime.md).
- **Additional optional features/extensions:** v0.1 registers none; adding support requires explicit append-only registry assignments and a reviewed protocol change.

## Closed items

- **Submission terminal events:** `SUBMISSION_COMPLETE` and `SUBMISSION_FAILED` layouts, event-type IDs, XGE lengths, terminal-event exclusivity, and delivery behavior are specified in [events](events.md) and covered by the conformance checklist.
- **Shared device reason codes:** `DEVICE_LOST.reason_code` and `DEVICE_STATUS_CHANGED.reason_code` use the same append-only [device reason-code registry](../registries/reason-codes.md). Values are informational and do not replace event-specific lifecycle rules.
- **WriteBuffer dependency cycle:** while waiting for earlier submissions, the server checks deferred `QueueSubmit` signal entries. If a deferred timeline signal would satisfy a wait of an earlier non-terminal submission and no already accepted signal operation can satisfy that wait, `WriteBuffer` fails with `DEPENDENCY_FAILED`; deferred requests are then processed in request order, and no `QueueSubmit` is accepted across a successful upload boundary. See [Memory and buffers](memory-buffers.md#57-writebuffer), [Queue submission and ordering](queue-submission.md), and the conformance checklist.


### Closed normative audit — PresentationRoute result mapping and lifetime — 2026-11-04

The seven presentation requests were cross-checked against the provider-result contract and lifecycle serialization rules. GetSurfaceCapabilities now has a complete status precedence including the zero-extent case. Capability queries do not retain route leases; CreateSwapchain creates and pins the exact route generation and revalidates it at publication. Swapchain/route destruction order, provider-token quiescence, failure rollback, and quarantine are explicit. Dedicated conformance vectors are in [presentation-route-conformance.md](presentation-route-conformance.md). No wire ABI changed. Exact-tip CI after these documentation updates remains required.


### Registry mutation result contract — 2026-11-04

Physical removal confirmation now requires evidence tied to the exact current source observation and PhysicalDevice incarnation. Provider context/device availability and recovery operations return classified registry outcomes; stale generations, unknown providers, or absent selected bindings are rejected without mutation. The source key in removal evidence is borrowed for the call only and resolved before return. The API-result/architecture vectors are in `spec/device-registry-architecture.md` (vectors 58–59). The availability-transition return-value refinement and source-authority validation are verified by workflow 41840825348. The provider pointer-lifetime contract is verified by exact-tip workflow 41840947750. This is internal server architecture, not a wire-protocol design gap.


### Runtime acceptance: XLibre DDX/provider module quiescence — 2026-11-04

The normative lifecycle contract is closed in `device-registry-architecture.md` §2.4: Screen close is topology-only; a provider/module lease is independent of Xorg `ScrnInfo`/driver references; per-token retirement includes callback return; and provider-wide `quiesce_provider` SUCCESS is required before unloading code or userdata reachable by callbacks/workers. PENDING/FAILURE retains or quarantines the provider. Vectors 70–75 cover the static lifecycle cases. Remaining acceptance work is runtime-only: instrument an XLibre build to verify actual module references and unload ordering under GPU hotplug, multiple Screens, provider callback races, and DDX module unload. Do not treat `FreeScreen()`, `xf86DeleteScreen()`, zero driver Screen references, or `RemoveGPUScreen()` as provider quiescence.


The XLibre loader implementation was also checked: `DuplicateModule()` does not acquire an independent module handle, and `LoaderUnload()` calls `dlclose()` on the original handle. Vectors 76–77 now require a separate provider module pin to survive final Screen deletion. The remaining question is runtime acceptance on a built XLibre server: demonstrate that the chosen pin mechanism actually prevents the final `dlclose()` until provider-wide quiescence succeeds.
