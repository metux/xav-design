# Remaining v0.1 issues and future maintenance

This file separates specification design gaps from implementation acceptance tests. A protocol rule can be fully specified before a server exists; static checks cannot prove runtime interoperability. The release gate is [the specification freeze checklist](freeze-checklist.md).

## Specification freeze status

The request registry defines 48 request contracts: common bootstrap `QueryVersion` at subopcode 0, compute-baseline subopcodes 1–40, and presentation-capable-profile subopcodes 41–47. Presentation requests and event types remain profile-gated; their assignment does not imply support in the initial compute-only implementation.

The latest verified specification-content candidate is `0b9c40e0907592f7f96687912d948abf221123d0`, verified by [exact-tip CI run 41476931362](https://github.com/metux/xav-design/actions/runs/41476931362): 4,836 wire-layout/documentation checks, 72 Timeline regression tests, all 692 Python tests, and the companion branch-tip monitor passed. The final cross-request audit covers all 48 registered requests: bootstrap `QueryVersion` 0, compute baseline 1–40, and presentation profile 41–47. The QueryVersion request/reply contract has dedicated positive and negative wire vectors in both byte orders. The earlier historical checkpoints and their CI runs remain historical evidence only. The current normative content is complete and freeze-ready; formal coordination sign-off still awaits implementation-agent Phase 1 ship confirmations and a named shared integration-interface owner on the blackboard. Earlier resource-lifetime, retained-layout, QueueSubmit/destruction, final cross-document, and post-checkpoint normative-delta reviews are recorded in the [resource-lifetime audit](../audit/resource-lifetime-audit-2026-10-30.md), [layout audit](../audit/pipeline-descriptor-command-buffer-audit-2026-10-30.md), [submission/destruction audit](../audit/queue-submit-resource-destruction-audit-2026-10-30.md), [final audit](../audit/final-cross-document-specification-audit-2026-10-30.md), and [delta audit](../audit/post-freeze-normative-delta-audit-2026-10-30.md).

**Editorial note (not a protocol blocker).** Some normative and explanatory prose remains German while other chapters are English. This is a consistency/readability issue, not evidence of a protocol-design gap. Translation is deferred unless mixed-language wording makes a requirement ambiguous; content reviews must still verify the exact normative meaning regardless of language.

The request/error precedence audit and dedicated `QueryVersion` review cover all 48 registered requests. The exact candidate and CI run above verify the normative request/reply contract, both byte orders, malformed request headers and lengths, and reserved/version reply fields. Resource lifetime, asynchronous terminalization, callback identity, semaphore/fence reservations, and Device-loss behavior retain their dedicated normative audits and reference-model regressions. Passing static checks does not prove runtime behavior; implementation acceptance gates remain open.

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
