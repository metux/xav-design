# Fences

## Zustände

Vorgesehene Zustände:

- `UNSIGNALED = 0`
- `PENDING = 1`
- `SIGNALED = 2`
- `FAILED = 3`

Übergänge:

- Erstellung → `UNSIGNALED`
- angenommene Submission mit Fence → `PENDING`
- erfolgreiche Completion → `SIGNALED`
- asynchroner Ausführungsfehler → `FAILED`
- Reset aus `SIGNALED` oder `FAILED` → `UNSIGNALED`
- abgelehnte Submission → Zustand bleibt unverändert

## `CreateFence`

Gesamtlänge: 24 Bytes.

- Offset 8: Device-XID
- Offset 12: Fence-XID
- Offset 16: `CARD32 create_flags = 0`
- Offset 20: `CARD32 reserved = 0`

## `GetFenceStatus`

Request: 16 Bytes; Device-XID bei Offset 8, Fence-XID bei Offset 12.

Reply: 32 Bytes.

- Byte 1: Fence-Status
- Reply-Länge: null
- Offsets 8–31: reserviert, null

## `WaitForFence`

Request: 24 Bytes.

- Offset 8: Device-XID
- Offset 12: Fence-XID
- Offset 16: `CARD64 timeout_ns`

Reply-Status:

- `SUCCESS = 0`
- `TIMEOUT = 1`
- `EXECUTION_FAILED = 2`
- `DEVICE_LOST = 3`

Timeout und Ausführungsfehler werden als normale Reply-Statuswerte zurückgegeben.

## `ResetFence`

Request: 16 Bytes; Device-XID bei Offset 8, Fence-XID bei Offset 12.

Nur `SIGNALED` und `FAILED` dürfen zurückgesetzt werden. Ein Reset aus `PENDING` oder `UNSIGNALED` ergibt `INVALID_SYNCHRONIZATION_STATE`. Bei verlorenem Device wird `DEVICE_LOST` zurückgegeben.

## Fence-Zerstörung

Die öffentliche Fence-XID wird bei erfolgreicher Zerstörung ungültig. Die interne Fence bleibt erhalten, solange angenommene Arbeit sie benötigt.

Die konservative v0.1-Regel lautet: Eine pending Fence kann nicht zerstört werden. Die genaue Fehlerzuordnung und das Verhalten nach Device Loss müssen mit der allgemeinen Zerstörungsregel konsistent umgesetzt werden.
