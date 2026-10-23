# Event type and event-local value registries

XAverius events use XGE. The XGE `extension` field carries the dynamically assigned XAverius extension major opcode; `evtype` carries the static event type ID below. XGE uses core event code `GenericEvent = 35`; XAverius has no separate server-assigned XGE event base. Event type IDs are separate from request subopcodes and XAverius error offsets.

## Event type IDs

| Value | Symbol |
|---:|---|
| 0 | `ASYNC_ERROR` |
| 1 | `DEVICE_LOST` |
| 2 | `DEVICE_STATUS_CHANGED` |
| 3 | `DEVICE_MEMORY_PRESSURE` |
| 4 | `DEVICE_IDLE` |
| 5 | `SUBMISSION_COMPLETE` |
| 6 | `SUBMISSION_FAILED` |
| 7 | `IMAGE_RELEASED` |
| 8 | `PRESENTATION_COMPLETE` |

Event type IDs are stable and MUST NOT be renumbered. Values 9–65535 are unassigned.


## Presentation event status values

| Value | Symbol |
|---:|---|
| 0 | SUCCESS |
| 1 | OUT_OF_DATE |
| 2 | SURFACE_LOST |
| 3 | DEVICE_LOST |
| 4 | PRESENTATION_FAILED |

These status values apply to presentation events only. They are not X11 error codes or XAverius error offsets.

## `ASYNC_ERROR.error_code`

The event field is a zero-based offset from the central [XAverius error registry](errors.md), in the range 0–8 for v0.1. It is not the absolute X11 error code (`first_error + offset`) and is not an X11 core error code. `ASYNC_ERROR` reports diagnostics for failures discovered after an operation was accepted; it does not duplicate a synchronous request rejection. For an accepted `QueueSubmit`, `SUBMISSION_FAILED` and synchronization state carry the terminal failure, while `ASYNC_ERROR` is optional supplementary diagnostic information.

## `ASYNC_ERROR.origin`

| Value | Symbol |
|---:|---|
| 0 | `ORIGIN_UNSPECIFIED` |
| 1 | `ORIGIN_QUEUE_SUBMIT` |
| 2 | `ORIGIN_WRITE_BUFFER` |
| 3 | `ORIGIN_READ_BUFFER` |
| 4 | `ORIGIN_SEMAPHORE` |
| 5 | `ORIGIN_FENCE` |
| 6 | `ORIGIN_DEVICE` |

Both `DEVICE_LOST.reason_code` and `DEVICE_STATUS_CHANGED.reason_code` use the shared append-only [device reason-code registry](reason-codes.md); their lifecycle semantics remain specific to each event.


## `DEVICE_STATUS_CHANGED.new_status`

| Value | Symbol |
|---:|---|
| 0 | `AVAILABLE` |
| 1 | `UNAVAILABLE` |
| 2 | `REMOVED` |

`REMOVED` is terminal for a physical-device XID. After emitting `new_status = REMOVED`, the server MUST NOT emit another `DEVICE_STATUS_CHANGED` event for that XID; the XID must never be reassigned to another physical device.

## `DEVICE_MEMORY_PRESSURE.pressure_level`

| Value | Symbol |
|---:|---|
| 0 | `NORMAL` |
| 1 | `LOW` |
| 2 | `MEDIUM` |
| 3 | `HIGH` |

## `DEVICE_IDLE.idle_reason`

| Value | Symbol |
|---:|---|
| 0 | `IDLE_REASON_UNSPECIFIED` |
| 1 | `NO_PENDING_WORK` |
| 2 | `WORK_COMPLETED` |

## `SUBMISSION_FAILED.failure_class`

| Value | Symbol |
|---:|---|
| 0 | `EXECUTION_FAILED` |
| 1 | `DEVICE_LOST` |

Event selection is implemented by the 32-byte Void request `SelectEvents` at subopcode 40 in the central request registry. Its scopes, masks, atomic replacement semantics, and XGE negotiation prerequisite are specified in [the event chapter](../spec/events.md). This event-type registry remains separate from request subopcodes.
