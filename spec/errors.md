# Errors and error mapping

Error codes are offsets relative to the X11 extension's `first_error` value. The absolute X11 error code is `first_error + offset`; implementations must use the central values in [the error registry](../registries/errors.md), not allocate values ad hoc.

XAverius errors use the standard 32-byte X11 error packet and add no XAverius-specific payload bytes. The packet carries the extension major opcode, the request subopcode, and the sequence number of the request that caused the error. The resource field identifies the affected resource when meaningful; otherwise it is zero.

## Allgemeine Fehlerklassen

| Situation | Ergebnis |
|---|---|
| Request-Länge oder Count inkonsistent | `BadLength` |
| Ungültiger Feldwert, reservierte Bits oder Flags | `BadValue` |
| Ungültige oder bereits belegte Create-XID | `BadIDChoice` |
| Falscher Ressourcentyp oder Cross-Device-Kombination | normalerweise `BadMatch` |
| Ungültige Ressource | Request-spezifischer Standard-X11-Fehler |
| Device nicht verfügbar | `DEVICE_UNAVAILABLE` |
| Device verloren | `DEVICE_LOST` |
| Ungültiger Synchronisationszustand | `INVALID_SYNCHRONIZATION_STATE` |
| Synchroner Transferfehler | `TRANSFER_FAILED` |
| Synchroner Allokationsfehler | `ALLOCATION_FAILED` |
| Ungültige Abhängigkeit verhindert Annahme | `DEPENDENCY_FAILED` |
| Unerwarteter Serverfehler | `INTERNAL_SERVER_ERROR` |

## Request-spezifische Fehlerzuordnung

### `WriteBuffer`

- Falsche Request-Länge: `BadLength`
- Länge null oder ungültige reservierte Felder: `BadValue`
- Ungültige XID: request-spezifischer X11-Fehler
- Falscher Typ, falsches Device, ungebundener Buffer, fehlendes `TRANSFER_DST`, Bereich außerhalb des Buffers: `BadMatch`
- Nicht verfügbares/verlorenes Device: `DEVICE_UNAVAILABLE` / `DEVICE_LOST`
- Synchroner Transferfehler: `TRANSFER_FAILED`
- Fehlgeschlagene Staging-Allokation: `ALLOCATION_FAILED`

### `ReadBuffer`

- Falsche Request-Länge: `BadLength`
- Länge null oder ungültige reservierte Felder: `BadValue`
- Ungültige XID: request-spezifischer X11-Fehler
- Falscher Typ, falsches Device, ungebundener Buffer, fehlendes `TRANSFER_SRC`, ungültiger Bereich: `BadMatch`
- Nicht verfügbares/verlorenes Device: `DEVICE_UNAVAILABLE` / `DEVICE_LOST`
- Synchroner Transferfehler: `TRANSFER_FAILED`
- Fehlgeschlagene Staging-Allokation: `ALLOCATION_FAILED`

### `QueueSubmit`

- Count-/Längenfehler: `BadLength`
- Ungültige Masks, reservierte Felder oder numerische Werte: `BadValue`
- Ungültige XID: request-spezifischer X11-Fehler
- Falscher Typ oder Cross-Device-Ressource: `BadMatch`
- Nicht ausführbarer Command Buffer, ungültiger Fence- oder Semaphore-Zustand: `INVALID_SYNCHRONIZATION_STATE`
- Nicht verfügbares/verlorenes Device: `DEVICE_UNAVAILABLE` / `DEVICE_LOST`
- Ungültige Abhängigkeit, die Annahme verhindert: `DEPENDENCY_FAILED`

### Fence-Requests

- Falsche Länge: `BadLength`
- Ungültige Flags oder reservierte Felder: `BadValue`
- Ungültige Ressource: request-spezifischer X11-Fehler
- Falscher Typ oder Device: `BadMatch`
- Ungültiger Reset-/Destroy-Zustand: `INVALID_SYNCHRONIZATION_STATE`
- Timeout und asynchroner Ausführungsfehler bei `WaitForFence`: normaler Reply-Status

### `BindBufferMemory`

Cross-Device-Nutzung, bereits gebundener Buffer, ungültiges Alignment, zu kleine Allokation oder inkompatibler Memory-Type ergeben `BadMatch`.

### `UpdateDescriptorSets`

- Falsche Länge: `BadLength`
- Reservierte Felder oder ungültige Werte: `BadValue`
- Inkompatibler Descriptor, Buffer oder Device: `BadMatch`
- Update während Pending-Use: `INVALID_SYNCHRONIZATION_STATE`

Jeder Request muss vor Implementierungsfreigabe eine vollständige, konkrete Fehlerzuordnung besitzen.

## Synchron versus asynchron

Ein Fehler vor Annahme wird durch einen X11-Fehler oder den ausdrücklich definierten normalen Fehler-Reply signalisiert. Der Request darf keinen Teilzustand hinterlassen.

Ein Fehler nach Annahme wird durch XAverius-Events und Synchronisationszustände signalisiert. Ein später X11-Fehler für einen bereits angenommenen Request ist unzulässig.
