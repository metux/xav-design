# XAverius Events

All events below use XGE. The seven compute-baseline events use IDs from the [central event registry](../registries/event-types.md). The presentation-only events `IMAGE_RELEASED` (7) and `PRESENTATION_COMPLETE` (8), together with their status values, are defined in the separate [Presentation Event Registry](../registries/presentation-events.md) and MUST be used only by the presentation-capable profile. The shared 32-byte header follows the X Generic Event format:

| Offset | Type | Field |
|---:|---|---|
| 0 | CARD8 | `response_type = GenericEvent (35)` |
| 1 | CARD8 | `extension`: dynamically assigned XAverius major opcode |
| 2 | CARD16 | X11 event sequence number |
| 4 | CARD32 | XGE `length`, number of four-byte units after offset 32 |
| 8 | CARD16 | `evtype`, static event type ID from the event registry |
| 10–31 | — | XGE-reserved header bytes, zero |

Event-specific fields begin at offset 32. The total length is exactly `32 + 4 * length`; the connection byte order applies to both header and payload. The `extension` and `evtype` values are not interchangeable: the former is dynamically assigned by each X11 server, while the latter is statically assigned by XAverius.


## `ASYNC_ERROR`

Total length: 60 bytes; XGE `length = 7`.

| Offset | Type | Field |
|---:|---|---|
| 32 | XID | Device XID; zero if not device-related |
| 36 | CARD32 | `error_code`, central XAverius error offset |
| 40 | CARD32 | `origin` |
| 44 | CARD64 | `submission_token`, 0 if not associated with a submission |
| 52 | XID | affected resource XID, zero if none |
| 56 | CARD32 | `reserved = 0` |

Origin values:

- 0: `ORIGIN_UNSPECIFIED`
- 1: `ORIGIN_QUEUE_SUBMIT`
- 2: `ORIGIN_WRITE_BUFFER`
- 3: `ORIGIN_READ_BUFFER`
- 4: `ORIGIN_SEMAPHORE`
- 5: `ORIGIN_FENCE`
- 6: `ORIGIN_DEVICE`

`error_code` contains the numeric **offset** from the central XAverius error registry, not the absolute X11 error code (`first_error + offset`) or a core X11 error code. `submission_token` is zero exactly when the error is not associated with an accepted submission. For `origin = ORIGIN_QUEUE_SUBMIT`, `submission_token` MUST therefore be non-zero and preserve the token of the affected, previously accepted `QueueSubmit` request. For other origins, the token may be non-zero only when the error is actually associated with such a submission; a non-zero token MUST never identify a rejected `QueueSubmit` request. `ASYNC_ERROR` diagnoses an error after an operation has been accepted. An error detected before acceptance is reported synchronously as an X11 error or explicitly defined normal reply and MUST NOT also be emitted as `ASYNC_ERROR` for the same rejection. Errors during `ShaderModuleData` upload and `CommandBufferData` recording chunks are always synchronous and MUST NOT generate `ASYNC_ERROR`, because no GPU submission has been accepted. Discarding an incomplete shader assembly on disconnect or device loss likewise does not generate an upload-specific `ASYNC_ERROR`; the device-loss event path remains independent. In particular, an accepted `QueueSubmit` MUST NOT generate a delayed X11 request error after an execution failure: its terminal outcome is reported through `SUBMISSION_FAILED` and synchronization state; `ASYNC_ERROR` may provide supplementary diagnostics. If the affected resource XID is no longer publicly live at the event-enqueue linearization point, `resource_xid` MUST be zero. The server MUST NOT resolve the numeric XID again or associate it with an object that has since reused that XID; the internal resource identity is retained only for safe internal cleanup.

## `DEVICE_LOST`

Total length: 48 bytes; XGE `length = 4`.

- Offset 32: Device-XID
- Offset 36: `CARD32 reason_code`
- Offset 40: `CARD64 device_generation`

The `reason_code` values are defined by the shared [device reason-code registry](../registries/reason-codes.md).

## `DEVICE_STATUS_CHANGED`

Total length: 48 bytes; XGE `length = 4`.

- Offset 32: Physical-Device-XID
- Offset 36: `CARD32 new_status`
- Offset 40: `CARD32 reason_code`
- Offset 44: `CARD32 reserved = 0`

Status:

- 0: `AVAILABLE`
- 1: `UNAVAILABLE`
- 2: `REMOVED`

The `reason_code` field uses the shared [device reason-code registry](../registries/reason-codes.md). The reason is informational and does not change the status-transition rules.

`REMOVED` is final for this XID. After an event with `new_status = REMOVED`, the server MUST NOT send another `DEVICE_STATUS_CHANGED` event for this XID. The XID is never reassigned to another device.

## `DEVICE_MEMORY_PRESSURE`

Total length: 48 bytes; XGE `length = 4`.

- Offset 32: Device-XID
- Offset 36: `CARD32 heap_index`; `UINT32_MAX` means no specific heap. Any other value MUST be less than `memory_heap_count` from `GetPhysicalDeviceMemoryProperties` for the physical device underlying the logical device; otherwise, this event MUST NOT be sent.
- Offset 40: `CARD32 pressure_level`
- Offset 44: `CARD32 reserved = 0`

Pressure-Level:

- 0: `NORMAL`
- 1: `LOW`
- 2: `MEDIUM`
- 3: `HIGH`

## `DEVICE_IDLE`

Total length: 48 bytes; XGE `length = 4`.

- Offset 32: Device-XID
- Offset 36: `CARD32 idle_reason`
- Offset 40: `CARD64 device_generation`

Reasons:

- 0: `IDLE_REASON_UNSPECIFIED`
- 1: `NO_PENDING_WORK`
- 2: `WORK_COMPLETED`

## `SUBMISSION_COMPLETE`

Total length: 56 bytes; XGE `length = 6`.

- Offset 32: Device-XID
- Offset 36: `CARD32 queue_family_index`
- Offset 40: `CARD32 queue_index`
- Offset 44: `CARD32 reserved = 0`
- Offset 48: `CARD64 submission_token`, the token supplied by the client in `QueueSubmit`. It is non-zero and unique within the associated X11 client connection; the rules in [QueueSubmit](queue-submission.md) apply unchanged.

The `queue_family_index` and `queue_index` fields identify exactly the queue to which this submission was passed through `QueueSubmit`. They are not global queue IDs and MUST identify a queue actually created for the specified logical device.

## `SUBMISSION_FAILED`

Total length: 56 bytes; XGE `length = 6`.

- Offset 32: Device-XID
- Offset 36: `CARD32 queue_family_index`
- Offset 40: `CARD32 queue_index`
- Offset 44: `CARD32 failure_class`
- Offset 48: `CARD64 submission_token`, the token supplied by the client in `QueueSubmit`. It is non-zero and unique within the corresponding X11 client connection; the rules in [QueueSubmit](queue-submission.md) apply unchanged.

The `queue_family_index` and `queue_index` fields identify exactly the queue to which the submission was passed through `QueueSubmit`. They are not global queue IDs and MUST identify a queue actually created for the specified logical device.

Failure-class values:

- 0: `EXECUTION_FAILED`
- 1: `DEVICE_LOST`


## `IMAGE_RELEASED`

Total length: 64 bytes; XGE `length = 8`.

| Offset | Type | Field |
|---:|---|---|
| 32 | XID | Device-XID |
| 36 | CARD32 | `queue_family_index` of the accepted presentation operation |
| 40 | CARD32 | `queue_index` of the accepted presentation operation |
| 44 | XID | Swapchain-XID |
| 48 | CARD32 | `image_index` |
| 52 | CARD32 | `reserved = 0` |
| 56 | CARD64 | `presentation_token` from the client request |

This event identifies the internal transition at which presentation-backend access to the image has ended and the image may be acquired again. It does not prove that presentation has reached its completion point. This release transition may occur at most once per accepted presentation operation. An `IMAGE_RELEASED` event is queued exactly when the image is reusable, queue mask bit 2 is set at the release linearization point, the original connection can still receive events, and device lifecycle rules permit event generation. If the image is invalidated before the release milestone, no `IMAGE_RELEASED` event is queued; invalidation after a previously committed release cannot retract an event already queued at that release point. `PRESENTATION_COMPLETE` reports the terminal failure if its own delivery conditions are met and its independent delivery conditions are met. Masking or suppressed delivery never skips the internal release/invalidation transition. A later mask change does not alter the delivery decision already made.

## `PRESENTATION_COMPLETE`

Total length: 64 bytes; XGE `length = 8`.

| Offset | Type | Field |
|---:|---|---|
| 32 | XID | Device-XID |
| 36 | CARD32 | `queue_family_index` of the accepted presentation operation |
| 40 | CARD32 | `queue_index` of the accepted presentation operation |
| 44 | XID | Swapchain-XID |
| 48 | CARD32 | `image_index` |
| 52 | CARD32 | `status` from the presentation event status registry |
| 56 | CARD64 | `presentation_token` from the client request |

This event represents the unique internal terminal outcome of each accepted presentation operation. A `PRESENTATION_COMPLETE` event is queued exactly when queue mask bit 3 is set while serializing that terminal result, the original connection can still receive events, and device lifecycle rules permit event generation. `SUCCESS` means the defined presentation-backend completion point was reached successfully; other status values describe the terminal failure. This event may arrive independently of `IMAGE_RELEASED`. `PRESENTATION_COMPLETE` alone does not make the image acquirable again. If a failure prevents reuse, the image is invalidated and the swapchain is marked unusable. After `DestroyDevice` has been processed successfully, no new events using its device XID may be generated or delivered; events already queued in the X11 output stream remain unaffected. After disconnect, nothing more is delivered to the closed connection, but the internal operation is still terminalized. Later mask changes do not alter this event's delivery decision. The two events have independent mask and lifecycle decisions because their terminal points may differ.

## Prerequisite for Extended XGE Events

All events defined in this chapter are longer than the standard 32-byte X11 event. Before sending such events, the server must know that the client supports XGE; otherwise, the X11 byte stream could become misaligned for a client without XGE support.

An XAverius client must successfully execute `GEQueryVersion` and negotiate at least XGE 1.0 before creating a logical device or issuing any `SelectEvents` request. The XAverius server must track successful negotiation per connection. Without negotiated XGE support, `CreateDevice`, `CreateDefaultDevice`, and `SelectEvents` are rejected with `BadMatch`; for `SelectEvents`, the previous selection remains unchanged. A server that does not support XGE must not advertise XAverius as an available extension.

## Event Selection: `SelectEvents`

Compute-baseline event type IDs are defined in the [central event registry](../registries/event-types.md); presentation-only IDs are defined in the [Presentation Event Registry](../registries/presentation-events.md). Both namespaces use the same append-only event type IDs and must not collide. They are distinct from request sub-opcodes and error offsets.

`SelectEvents` is a void request with a fixed total length of 32 bytes. The common-header `flags` field at offset 5 must be zero; the reserved common-header field at offset 6 must also be zero. The request atomically replaces the existing mask for exactly one scope of this X11 connection; it does not add bits or remove other scopes.

| Offset | Type | Field |
|---:|---|---|
| 8 | CARD32 | `scope` |
| 12 | XID | `device_xid` |
| 16 | CARD32 | `queue_family_index` |
| 20 | CARD32 | `queue_index` |
| 24 | CARD32 | `event_mask` |
| 28 | CARD32 | `reserved = 0` |

Scope values:

- `CONNECTION = 0`: `device_xid = 0`, `queue_family_index = 0`, and `queue_index = 0`. Applies to the entire X11 connection.
- `DEVICE = 1`: `device_xid` identifies a logical Device owned by this connection; both queue indices must be zero.
- `QUEUE = 2`: `device_xid` identifies a logical Device owned by this connection; the tuple `(queue_family_index, queue_index)` must identify a queue actually requested from that Device.

Unused fields must contain exactly the specified zero values. Unknown scope values, non-zero reserved fields, invalid mask bits, or invalid scope/field combinations result in `BadValue`. Unknown or non-live XIDs result in `BadValue`; an incorrect resource type or foreign client ownership results in `BadMatch`. A nonexistent queue within a valid device results in `BadValue`. On any error, the previous selection remains unchanged.

Normative validation precedence is: (1) validate the exact 32-byte request length (`BadLength`); (2) validate scope, zero-valued unused fields, reserved fields, and profile-legal mask bits (`BadValue`); (3) for `DEVICE` and `QUEUE` scope, resolve `device_xid` (`BadValue` if unknown/non-live); (4) validate live type and client ownership (`BadMatch`); (5) require successful XGE 1.0-or-later negotiation (`BadMatch` otherwise); (6) for `QUEUE` scope, validate the queue-family/index tuple (`BadValue` if it does not identify a queue); (7) atomically replace the selection. A later phase MUST NOT override an earlier error. The previous selection is unchanged on every rejection.

The masks depend on the scope:

| Scope | Bit | Event |
|---|---:|---|
| `CONNECTION` | 0 | `DEVICE_STATUS_CHANGED` |
| `DEVICE` | 0 | `DEVICE_MEMORY_PRESSURE` |
| `DEVICE` | 1 | `DEVICE_IDLE` |
| `QUEUE` | 0 | `SUBMISSION_COMPLETE` |
| `QUEUE` | 1 | `SUBMISSION_FAILED` |
| `QUEUE` | 2 | `IMAGE_RELEASED` |
| `QUEUE` | 3 | `PRESENTATION_COMPLETE` |

All other bits are reserved and must be rejected. Presentation bits are valid only in the presentation-capable profile; a compute-only server must reject them as unknown mask bits with `BadValue`. `event_mask = 0` clears the selection for the specified scope. Clearing a Device or Queue mask does not remove selections for other scopes. When a logical Device is successfully destroyed, its Device and Queue selections are removed; the Connection selection remains.

`ASYNC_ERROR` and `DEVICE_LOST` are unmaskable and are delivered independently of `SelectEvents` while the connection can receive events. This rule is subject to the lifecycle limits in [Resource lifetime and ownership](resource-lifetime.md): after successful processing of `DestroyDevice`, no new events using the destroyed `device_xid` may be generated or delivered; events already queued in the X11 output stream remain unaffected. `DEVICE_STATUS_CHANGED` is delivered only through the Connection mask. The two submission events are delivered only if the corresponding Queue mask bit is set when the terminal submission outcome occurs. Event selection never affects execution, internal terminal state, or Fence/Semaphore state. For each accepted submission, `SUBMISSION_COMPLETE` and `SUBMISSION_FAILED` must never both be delivered as terminal events.

**Serialization of asynchronous event decisions:** Processing a successful `SelectEvents`, successful processing of `DestroyDevice`, a Submission's terminal transition, and both presentation milestones (presentation terminalization and image release) MUST be ordered by one shared serialized server state. A successful `SelectEvents` request takes effect at its linearization point. Submission completion evaluates the Queue mask then in effect; presentation terminalization independently samples Queue mask bit 3, and image release independently samples Queue mask bit 2, each at that milestone's own linearization point. The transition and the decision to queue or suppress its event in the X11 output stream are atomic with respect to both `SelectEvents` and `DestroyDevice`: if a milestone linearizes first and queues its event, that queued event remains unaffected by a later mask change or Device destruction; if `SelectEvents` linearizes first, the new mask governs the later milestone; if `DestroyDevice` successfully linearizes first, no new event for its destroyed Device XID is queued. A later backend callback MUST NOT retroactively change this decision or requeue a suppressed event. The two presentation event bits are sampled independently even when both milestones occur in one backend callback. This serialization changes neither the order of X11 requests on a connection nor GPU dependencies between submissions or presentation operations.

If the connection is closed or the X11 server can no longer deliver events to it, event delivery is not guaranteed. This does not change the Submission's internal terminal outcome. A failed event send MUST NOT block GPU/backend processing or trigger a second terminal delivery.

The compute-baseline event type IDs and event-local values are registered in the [Event Registry](../registries/event-types.md); presentation-only event IDs and status values are defined in the [Presentation Event Registry](../registries/presentation-events.md). XGE uses the core event code `GenericEvent (35)`. An XAverius event is identified by the XAverius major opcode in the XGE `extension` field and the registered event type ID in the `evtype` field. The major opcode is discovered through the normal X11 extension query; there is no separate XAverius XGE event base.
