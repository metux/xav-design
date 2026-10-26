# XAverius Events

All events below use XGE. The seven compute-baseline events use IDs from the [central event registry](../registries/event-types.md). The presentation-only events `IMAGE_RELEASED` (7) and `PRESENTATION_COMPLETE` (8), together with their status values, are defined in the separate [Presentation Event Registry](../registries/presentation-events.md) and MUST be used only by the presentation-capable profile. The shared 32-byte header follows the X Generic Event format:

| Offset | Type | Field |
|---:|---|---|
| 0 | CARD8 | `response_type = GenericEvent (35)` |
| 1 | CARD8 | `extension`: dynamisch zugewiesener XAverius-Major-Opcode |
| 2 | CARD16 | X11-Event-Sequenznummer |
| 4 | CARD32 | XGE `length`, Anzahl der Vierbyteeinheiten nach Offset 32 |
| 8 | CARD16 | `evtype`, statische Event-Type-ID aus der Event-Registry |
| 10–31 | — | XGE-reservierte Header-Bytes, null |

Event-specific fields begin at offset 32. The total length is exactly `32 + 4 * length`; the connection byte order applies to both header and payload. The `extension` and `evtype` values are not interchangeable: the former is dynamically assigned by each X11 server, while the latter is statically assigned by XAverius.


## `ASYNC_ERROR`

Total length: 60 bytes; XGE `length = 7`.

| Offset | Type | Field |
|---:|---|---|
| 32 | XID | Device XID; zero if not device-related |
| 36 | CARD32 | `error_code`, zentraler XAverius-Fehleroffset |
| 40 | CARD32 | `origin` |
| 44 | CARD64 | `submission_token`, 0 falls nicht submissionbezogen |
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

`error_code` enthält den numerischen **Offset** aus der zentralen XAverius-Fehler-Registry, nicht den absoluten X11-Fehlercode (`first_error + offset`) und keinen Core-X11-Fehlercode. `submission_token` ist genau dann 0, wenn der Fehler keiner angenommenen Submission zugeordnet ist. Bei `origin = ORIGIN_QUEUE_SUBMIT` MUSS `submission_token` daher ungleich null sein und den Token der betroffenen, zuvor angenommenen `QueueSubmit`-Anforderung unverändert enthalten. Bei anderen Origins darf der Token nur dann ungleich null sein, wenn der Fehler tatsächlich einer solchen Submission zugeordnet ist; ein nicht-null Token darf niemals eine abgewiesene `QueueSubmit`-Anforderung bezeichnen. `ASYNC_ERROR` ist eine Diagnose für einen Fehler nach Annahme einer Operation; ein vor Annahme erkannter Fehler wird synchron als X11-Fehler oder ausdrücklich definierter normaler Reply gemeldet und darf nicht zusätzlich als `ASYNC_ERROR` für dieselbe Ablehnung ausgegeben werden. Fehler beim `ShaderModuleData`-Upload und bei `CommandBufferData`-Recording-Chunks sind immer synchron und dürfen kein `ASYNC_ERROR` erzeugen, da dadurch keine GPU-Submission angenommen wurde. Das Verwerfen eines unvollständigen Shader-Assemblies bei Disconnect oder Device Loss erzeugt ebenfalls kein upload-spezifisches `ASYNC_ERROR`; der Device-Loss-Event-Pfad bleibt davon unabhängig. Insbesondere darf ein angenommener `QueueSubmit` nach einem Ausführungsfehler keinen verspäteten X11-Request-Fehler erzeugen: sein terminaler Ausgang wird über `SUBMISSION_FAILED` und Synchronisationszustände gemeldet; `ASYNC_ERROR` darf ergänzende Diagnose liefern. Ist die betroffene Ressource zum Linearisierungspunkt der Event-Einreihung nicht mehr als öffentliche XID live, MUSS `resource_xid = 0` gesetzt werden. Der Server darf die numerische XID nicht erneut auflösen oder auf ein inzwischen wiederverwendetes Objekt beziehen; die interne Ressourcenidentität bleibt ausschließlich für sichere interne Bereinigung relevant.

## `DEVICE_LOST`

Total length: 48 bytes; XGE `length = 4`.

- Offset 32: Device-XID
- Offset 36: `CARD32 reason_code`
- Offset 40: `CARD64 device_generation`

The `reason_code` values are defined by the shared [device reason-code registry](../registries/reason-codes.md).

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

The `reason_code` field uses the shared [device reason-code registry](../registries/reason-codes.md). The reason is informational and does not change the status-transition rules.

`REMOVED` is final for this XID. After an event with `new_status = REMOVED`, the server MUST NOT send another `DEVICE_STATUS_CHANGED` event for this XID. The XID is never reassigned to another device.

## `DEVICE_MEMORY_PRESSURE`

Gesamtlänge: 48 Bytes; XGE `length = 4`.

- Offset 32: Device-XID
- Offset 36: `CARD32 heap_index`; `UINT32_MAX` bedeutet kein bestimmter Heap. Jeder andere Wert MUSS kleiner als `memory_heap_count` aus `GetPhysicalDeviceMemoryProperties` des physischen Devices sein, auf dem das logische Device basiert; andernfalls darf dieses Event nicht gesendet werden.
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

Gesamtlänge: 56 Bytes; XGE `length = 6`.

- Offset 32: Device-XID
- Offset 36: `CARD32 queue_family_index`
- Offset 40: `CARD32 queue_index`
- Offset 44: `CARD32 failure_class`
- Offset 48: `CARD64 submission_token`, der vom Client in `QueueSubmit` angegebene Token. Er ist ungleich null und innerhalb der zugehörigen X11-Client-Verbindung eindeutig; die Regeln aus [QueueSubmit](queue-submission.md) gelten unverändert.

Die Felder `queue_family_index` und `queue_index` bezeichnen exakt die Queue, an die diese Submission mit `QueueSubmit` übergeben wurde. Sie sind keine globalen Queue-IDs und müssen eine für das angegebene logische Device tatsächlich erstellte Queue identifizieren.

Failure-Class-Werte:

- 0: `EXECUTION_FAILED`
- 1: `DEVICE_LOST`


## `IMAGE_RELEASED`

Total length: 64 bytes; XGE `length = 8`.

| Offset | Type | Field |
|---:|---|---|
| 32 | XID | Device-XID |
| 36 | CARD32 | `queue_family_index` der akzeptierten Präsentationsoperation |
| 40 | CARD32 | `queue_index` der akzeptierten Präsentationsoperation |
| 44 | XID | Swapchain-XID |
| 48 | CARD32 | `image_index` |
| 52 | CARD32 | `reserved = 0` |
| 56 | CARD64 | `presentation_token` aus dem Client-Request |

Dieses Event bezeichnet den internen Übergang, bei dem die Präsentationsbackend-Zugriffe auf dieses Image beendet sind und es wieder erworben werden darf. Es beweist nicht, dass die Präsentation ihren Completion-Punkt erreicht hat. Dieser Freigabeübergang darf pro akzeptierter Präsentationsoperation höchstens einmal stattfinden. Ein `IMAGE_RELEASED`-Event wird genau dann eingereiht, wenn das Image wiederverwendbar ist, die Queue-Maske (Bit 2) am Freigabe-Linearisierungspunkt gesetzt ist, die ursprüngliche Verbindung noch zustellbar ist und die Device-Lifecycle-Regeln die Event-Erzeugung erlauben. Wird das Image stattdessen invalidiert, wird kein `IMAGE_RELEASED`-Event eingereiht; `PRESENTATION_COMPLETE` meldet den terminalen Fehler, sofern dessen eigene Zustellbedingungen erfüllt sind. Maskierung oder unterdrückte Zustellung überspringt niemals den internen Freigabe-/Invalidierungsübergang. Eine spätere Änderung der Maske ändert die bereits getroffene Zustellentscheidung nicht.

## `PRESENTATION_COMPLETE`

Gesamtlänge: 64 Bytes; XGE `length = 8`.

| Offset | Type | Field |
|---:|---|---|
| 32 | XID | Device-XID |
| 36 | CARD32 | `queue_family_index` der akzeptierten Präsentationsoperation |
| 40 | CARD32 | `queue_index` der akzeptierten Präsentationsoperation |
| 44 | XID | Swapchain-XID |
| 48 | CARD32 | `image_index` |
| 52 | CARD32 | `status` aus der Präsentations-Event-Status-Registry |
| 56 | CARD64 | `presentation_token` aus dem Client-Request |

Dieses Event bezeichnet den einmaligen internen terminalen Ausgang jeder akzeptierten Präsentationsoperation. Ein `PRESENTATION_COMPLETE`-Event wird genau dann eingereiht, wenn die Queue-Maske (Bit 3) beim Serialisieren dieses terminalen Ergebnisses gesetzt ist, die ursprüngliche Verbindung noch zustellbar ist und die Device-Lifecycle-Regeln die Event-Erzeugung erlauben. `SUCCESS` bedeutet, dass der definierte Completion-Punkt der Präsentationsbackend erfolgreich erreicht wurde; andere Statuswerte beschreiben den terminalen Fehlerzustand. Das Event darf unabhängig von `IMAGE_RELEASED` eintreffen. `PRESENTATION_COMPLETE` allein macht das Image nicht erneut erwerbbar. Wenn ein Fehler die Wiederverwendung verhindert, wird das Image invalidiert und die Swapchain als nicht mehr verwendbar markiert. Nach erfolgreicher Verarbeitung von `DestroyDevice` dürfen keine neuen Events mit dessen Device-XID erzeugt oder zugestellt werden; bereits vorher in den X11-Ausgabestrom eingereihte Events bleiben unberührt. Nach Disconnect wird nichts mehr an die geschlossene Verbindung zugestellt, die interne Operation wird dennoch terminalisiert. Spätere Maskenänderungen ändern die Zustellentscheidung für dieses Event nicht. Beide Events haben voneinander unabhängige Masken- und Lifecycle-Entscheidungen, da ihre terminalen Zeitpunkte verschieden sein können.

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

Scope-Werte:

- `CONNECTION = 0`: `device_xid = 0`, `queue_family_index = 0`, `queue_index = 0`. Gilt für die X11-Verbindung als Ganzes.
- `DEVICE = 1`: `device_xid` bezeichnet ein logisches Device dieser Verbindung; beide Queue-Indizes müssen null sein.
- `QUEUE = 2`: `device_xid` bezeichnet ein logisches Device dieser Verbindung; das Tupel `(queue_family_index, queue_index)` muss eine tatsächlich angeforderte Queue dieses Devices identifizieren.

Unused fields must contain exactly the specified zero values. Unknown scope values, non-zero reserved fields, invalid mask bits, or invalid scope/field combinations result in `BadValue`. Unknown or non-live XIDs result in `BadValue`; an incorrect resource type or foreign client ownership results in `BadMatch`. A nonexistent queue within a valid device results in `BadValue`. On any error, the previous selection remains unchanged.

Die Masken sind scopeabhängig:

| Scope | Bit | Event |
|---|---:|---|
| `CONNECTION` | 0 | `DEVICE_STATUS_CHANGED` |
| `DEVICE` | 0 | `DEVICE_MEMORY_PRESSURE` |
| `DEVICE` | 1 | `DEVICE_IDLE` |
| `QUEUE` | 0 | `SUBMISSION_COMPLETE` |
| `QUEUE` | 1 | `SUBMISSION_FAILED` |
| `QUEUE` | 2 | `IMAGE_RELEASED` |
| `QUEUE` | 3 | `PRESENTATION_COMPLETE` |

All other bits are reserved and must be rejected. Presentation bits are valid only in the presentation-capable profile; a compute-only server must reject them as unknown mask bits with `BadValue`. `event_mask = 0` hebt die Auswahl für den angegebenen Scope auf. Das Aufheben einer Device- oder Queue-Maske entfernt keine Auswahl anderer Scopes. Bei erfolgreicher Zerstörung eines logischen Devices werden seine Device- und Queue-Auswahlen entfernt; eine Connection-Auswahl bleibt bestehen.

`ASYNC_ERROR` und `DEVICE_LOST` sind nicht maskierbar und werden unabhängig von `SelectEvents` zugestellt, solange die Verbindung Events empfangen kann. Diese Regel unterliegt den Lebensdauergrenzen aus [Resource lifetime and ownership](resource-lifetime.md): Nach erfolgreicher Verarbeitung von `DestroyDevice` dürfen keine neuen Events mit der zerstörten `device_xid` erzeugt oder zugestellt werden; bereits vorher in den X11-Ausgabestrom eingereihte Events bleiben unberührt. `DEVICE_STATUS_CHANGED` wird nur über die Connection-Maske zugestellt. Die beiden Submission-Events werden nur zugestellt, wenn das jeweilige Queue-Maskenbit bei Eintritt des terminalen Submission-Ergebnisses gesetzt ist. Die Auswahl beeinflusst niemals die Ausführung, den internen terminalen Zustand oder die Fence-/Semaphore-Zustände. Pro angenommener Submission darf niemals sowohl `SUBMISSION_COMPLETE` als auch `SUBMISSION_FAILED` als terminales Event ausgeliefert werden.

**Serialisierung asynchroner Event-Entscheidungen:** Die Verarbeitung eines erfolgreichen `SelectEvents`, die erfolgreiche Verarbeitung von `DestroyDevice` und der terminale Übergang einer Submission einschließlich Entscheidung über das zugehörige terminale Event müssen über einen gemeinsamen serialisierten Serverzustand geordnet werden. Der erfolgreiche `SelectEvents`-Request wirkt ab seinem Linearisierungspunkt; ein Submission-Abschluss wertet die dann geltende Queue-Maske aus. Der terminale Übergang und die Entscheidung, das zugehörige Event in den X11-Ausgabestrom einzureihen oder zu unterdrücken, bilden gegenüber `DestroyDevice` eine unteilbare Entscheidung: Wird der Submission-Abschluss zuerst linearisiert und das Event eingereiht, bleibt dieses bereits eingereihte Event unberührt; wird `DestroyDevice` zuerst erfolgreich linearisiert, wird kein neues Event für dessen zerstörte Device-XID eingereiht. Ein späterer Backend-Callback darf diese Entscheidung nicht nachträglich ändern oder ein unterdrücktes Event erneut einreihen. Diese Serialisierung verändert weder die Reihenfolge der X11-Requests einer Verbindung noch die GPU-Abhängigkeiten zwischen Submissions.

Wenn die Verbindung geschlossen ist oder der X11-Server Events für diese Verbindung nicht mehr zustellen kann, ist keine Eventzustellung garantiert. Das ändert nicht den internen terminalen Ausgang der Submission. Ein fehlgeschlagenes Event-Senden darf weder die GPU-/Backend-Abwicklung blockieren noch eine zweite terminale Zustellung auslösen.

Die Compute-Baseline-Event-Type-IDs und event-lokalen Werte sind in der [Event-Registry](../registries/event-types.md) registriert; presentation-only Event-IDs und Statuswerte stehen in der [Presentation-Event-Registry](../registries/presentation-events.md). XGE verwendet den Core-Eventcode GenericEvent (35). Ein XAverius-Event wird durch den XAverius-Major-Opcode im XGE-Feld extension und die registrierte Event-Type-ID im Feld evtype identifiziert. Der Major-Opcode wird ueber die normale X11-Extension-Abfrage ermittelt; es gibt kein separates XAverius-XGE-Event-Base.
