# Remaining v0.1 issues and future maintenance

This file separates specification design gaps from implementation acceptance tests. A protocol rule can be fully specified before a server exists; static checks cannot prove runtime interoperability. The release gate is [the specification freeze checklist](freeze-checklist.md).

## Specification freeze status

The request registry defines 48 request contracts: common bootstrap `QueryVersion` at subopcode 0, compute-baseline subopcodes 1–40, and presentation-capable-profile subopcodes 41–47. Presentation requests and event types remain profile-gated; their assignment does not imply support in the initial compute-only implementation.

The last fully verified specification baseline is `47651058aa078d6727d681aa832630c2516bff5c`, passed by [exact-tip CI workflow 41835144462](https://github.com/metux/xav-design/actions/runs/41835144462). The current candidate `c4061d4fe8df660132517b714a549f8577d8d689` adds an explicit internal PresentationRoute object, provider route create/retire operations, and route-generation references in the lifecycle serializer; exact-tip CI is pending. The verified prior contract already covers render/scanout separation, PRIME/DRI3 bridge eligibility, pinned route generations, and route outage/invalidation status semantics. Phase 1 ship confirmations and a named shared integration-interface owner remain coordination sign-offs. Runtime acceptance gates remain open and are listed below.

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
