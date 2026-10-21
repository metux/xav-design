# XAverius-Events

Alle folgenden Events verwenden XGE.

## `ASYNC_ERROR`

Gesamtlänge: 60 Bytes; XGE `length = 7`.

| Offset | Typ | Feld |
|---:|---|---|
| 32 | XID | Device-XID, null falls nicht gerätebezogen |
| 36 | CARD32 | `error_code`, zentraler XAverius-Fehleroffset |
| 40 | CARD32 | `origin` |
| 44 | CARD64 | `submission_id`, null falls nicht submissionbezogen |
| 52 | XID | betroffene Ressourcen-XID, null falls keine |
| 56 | CARD32 | `reserved = 0` |

Origin-Werte:

- 0: `ORIGIN_UNSPECIFIED`
- 1: `ORIGIN_QUEUE_SUBMIT`
- 2: `ORIGIN_WRITE_BUFFER`
- 3: `ORIGIN_READ_BUFFER`
- 4: `ORIGIN_SEMAPHORE`
- 5: `ORIGIN_FENCE`
- 6: `ORIGIN_DEVICE`

## `DEVICE_LOST`

Gesamtlänge: 48 Bytes; XGE `length = 4`.

- Offset 32: Device-XID
- Offset 36: `CARD32 reason_code`
- Offset 40: `CARD64 device_generation`

Reason-Codes:

- 0: `REASON_UNSPECIFIED`
- 1: `HOTPLUG_REMOVAL`
- 2: `DRIVER_FAILURE`
- 3: `VULKAN_DEVICE_LOST`
- 4: `SERVER_POLICY`
- 5: `SERVER_SHUTDOWN`

## `DEVICE_STATUS_CHANGED`

Gesamtlänge: 48 Bytes; XGE `length = 4`.

- Offset 32: Physical-Device-XID
- Offset 36: `CARD32 new_status`
- Offset 40: `CARD32 reason_code`
- Offset 44: `CARD32 reserved = 0`

Status:

- 0: `AVAILABLE`
- 1: `UNAVAILABLE`
- 2: `REMOVED`

`REMOVED` ist für diesen XID endgültig. Die XID wird nie einem anderen Device zugewiesen.

## `DEVICE_MEMORY_PRESSURE`

Gesamtlänge: 48 Bytes; XGE `length = 4`.

- Offset 32: Device-XID
- Offset 36: `CARD32 heap_index`; `UINT32_MAX` bedeutet kein bestimmter Heap
- Offset 40: `CARD32 pressure_level`
- Offset 44: `CARD32 reserved = 0`

Pressure-Level:

- 0: `NORMAL`
- 1: `LOW`
- 2: `MEDIUM`
- 3: `HIGH`

## `DEVICE_IDLE`

Gesamtlänge: 48 Bytes; XGE `length = 4`.

- Offset 32: Device-XID
- Offset 36: `CARD32 idle_reason`
- Offset 40: `CARD64 device_generation`

Gründe:

- 0: `IDLE_REASON_UNSPECIFIED`
- 1: `NO_PENDING_WORK`
- 2: `WORK_COMPLETED`

## `SUBMISSION_COMPLETE`

Gesamtlänge: 56 Bytes; XGE `length = 6`.

- Offset 32: Device-XID
- Offset 36: `CARD32 queue_family_index`
- Offset 40: `CARD32 queue_index`
- Offset 44: `CARD32 reserved = 0`
- Offset 48: `CARD64 submission_id`

## `SUBMISSION_FAILED`

Gesamtlänge: 56 Bytes; XGE `length = 6`.

- Offset 32: Device-XID
- Offset 36: `CARD32 queue_family_index`
- Offset 40: `CARD32 queue_index`
- Offset 44: `CARD32 failure_class`
- Offset 48: `CARD64 submission_id`

Failure-Class-Werte:

- 0: `EXECUTION_FAILED`
- 1: `DEVICE_LOST`

## Event-Auswahl

Event-Typen:

| Typ | Event |
|---:|---|
| 0 | `ASYNC_ERROR` |
| 1 | `DEVICE_LOST` |
| 2 | `DEVICE_STATUS_CHANGED` |
| 3 | `DEVICE_MEMORY_PRESSURE` |
| 4 | `DEVICE_IDLE` |
| 5 | `SUBMISSION_COMPLETE` |
| 6 | `SUBMISSION_FAILED` |

Vorgesehene Masks:

- Connection-Mask Bit 0: `DEVICE_STATUS_CHANGED`
- Device-Mask Bit 0: `DEVICE_MEMORY_PRESSURE`
- Device-Mask Bit 1: `DEVICE_IDLE`
- Queue-Mask Bit 0: `SUBMISSION_COMPLETE`
- Queue-Mask Bit 1: `SUBMISSION_FAILED`

Andere Bits sind reserviert.

`ASYNC_ERROR` und `DEVICE_LOST` sind nicht maskierbar. Completion- und Failure-Events werden entsprechend der Event-Auswahl ausgeliefert. Pro angenommener Submission darf niemals sowohl `SUBMISSION_COMPLETE` als auch `SUBMISSION_FAILED` ausgeliefert werden.

Event-Auswahl-Request-Layouts und die endgültigen Event-Opcode-Registrierungen sind noch offen.
