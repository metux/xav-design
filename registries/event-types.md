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

Event type IDs are stable and MUST NOT be renumbered. Values 7–65535 are unassigned.

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

## `DEVICE_LOST.reason_code`

| Value | Symbol |
|---:|---|
| 0 | `REASON_UNSPECIFIED` |
| 1 | `HOTPLUG_REMOVAL` |
| 2 | `DRIVER_FAILURE` |
| 3 | `VULKAN_DEVICE_LOST` |
| 4 | `SERVER_POLICY` |
| 5 | `SERVER_SHUTDOWN` |

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
