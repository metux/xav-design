# Remaining v0.1 issues and future maintenance

This file distinguishes unresolved v0.1 validation work from rules that are already normative and questions intentionally deferred to later protocol versions. Listing a maintenance rule or future question here does not make it a blocker for the v0.1 specification.

## Remaining v0.1 validation work

1. **Open — implementation-level XGE interoperability.** Exercise `SelectEvents` and XGE framing against an actual X11/XGE implementation. The normative 32-byte GenericEvent header, dynamic extension opcode, static event type IDs, event lengths, and scope-specific selection masks are specified in [events](events.md), [wire protocol](wire-protocol.md), and the conformance checklist. This requires implementation-level testing; documentation-only checks cannot prove interoperability.

## Normative maintenance rules

These points are already specified and are not unresolved v0.1 design questions:

- **Request subopcodes:** the current 40 requests have stable assignments in the [central request subopcode registry](../registries/request-subopcodes.md). New assignments are append-only; existing assignments MUST NOT be renumbered.
- **Physical-device properties:** the four v0.1 properties and their wire representations are defined in the [property registry](../registries/physical-device-properties.md). Future properties must be registered append-only.
- **Feature IDs and device extensions:** future assignments must be registered append-only. The v0.1 optional sets are intentionally empty; see [feature IDs](../registries/feature-ids.md) and [device extensions](../registries/device-extensions.md).
- **Memory properties flags:** `memory_properties_flags` MUST be zero in v0.1 until a registry definition is explicitly assigned; see [memory properties](memory-buffers.md#52-getphysicaldevicememoryproperties).
- **Physical Device UUID and Driver UUID:** both are opaque 16-byte `BYTE_ARRAY` properties. The server preserves Vulkan-returned bytes exactly and MUST NOT fabricate unavailable UUIDs; see the [property registry](../registries/physical-device-properties.md).

## Deferred to future protocol versions

These topics do not block the current v0.1 contract:

- **Queue fairness and bounded progress:** v0.1 specifies same-queue submission order, no implicit cross-queue ordering, semaphore dependencies, and no fairness or latency guarantee in [queue submission and ordering](queue-submission.md). Any stronger guarantee is a future-version design question.
- **X11 resource sharing:** ownership and semantics for future cross-client or cross-device resource-sharing mechanisms remain unspecified. v0.1 does not implicitly provide such sharing; current ownership rules are in [device discovery](devices.md) and [resource lifetime](resource-lifetime.md).
- **Presentation-capable profile:** server-side presentation into ordinary X11 windows has an architectural chapter in [presentation](presentation.md), but it is not part of the initial compute-only v0.1 request inventory. Surface/swapchain ownership, capability semantics, image acquisition/presentation synchronization, event distinction, resize/loss behavior, and provisional request layouts are now documented in [presentation](presentation.md). Remaining work is cross-chapter wire/error validation and checker coverage; presentation request subopcodes have not yet been assigned.

## Closed items

- **Submission terminal events:** `SUBMISSION_COMPLETE` and `SUBMISSION_FAILED` layouts, event-type IDs, XGE lengths, terminal-event exclusivity, and delivery behavior are specified in [events](events.md) and covered by the conformance checklist.
- **Shared device reason codes:** `DEVICE_LOST.reason_code` and `DEVICE_STATUS_CHANGED.reason_code` use the same append-only [device reason-code registry](../registries/reason-codes.md). Values are informational and do not replace event-specific lifecycle rules.
- **WriteBuffer dependency cycle:** while waiting for earlier submissions, the server checks deferred `QueueSubmit` signal entries. If a deferred timeline signal would satisfy a wait of an earlier non-terminal submission and no already accepted signal operation can satisfy that wait, `WriteBuffer` fails with `DEPENDENCY_FAILED`; deferred requests are then processed in request order, and no `QueueSubmit` is accepted across a successful upload boundary. See [Memory and buffers](memory-buffers.md#57-writebuffer), [Queue submission and ordering](queue-submission.md), and the conformance checklist.
