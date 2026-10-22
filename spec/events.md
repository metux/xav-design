# XAverius-Events

Alle folgenden Events verwenden XGE. Der gemeinsame 32-Byte-Header entspricht dem X Generic Event-Format:

| Offset | Typ | Feld |
|---:|---|---|
| 0 | CARD8 | `response_type = GenericEvent (35)` |
| 1 | CARD8 | `extension`: dynamisch zugewiesener XAverius-Major-Opcode |
| 2 | CARD16 | X11-Event-Sequenznummer |
| 4 | CARD32 | XGE `length`, Anzahl der Vierbyteeinheiten nach Offset 32 |
| 8 | CARD16 | `evtype`, statische Event-Type-ID aus der Event-Registry |
| 10–31 | — | XGE-reservierte Header-Bytes, null |

Event-spezifische Felder beginnen bei Offset 32. Die Gesamtlänge ist exakt `32 + 4 * length`; die Verbindung-byte-order gilt auch für Header und Payload. Die Werte `extension` und `evtype` sind nicht austauschbar: Ersterer ist pro X11-Server dynamisch, letzterer ist XAverius-statisch.


## `ASYNC_ERROR`

Gesamtlänge: 60 Bytes; XGE `length = 7`.

| Offset | Typ | Feld |
|---:|---|---|
| 32 | XID | Device-XID, null falls nicht gerätebezogen |
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

`REMOVED` ist für diesen XID endgültig. Nach einem Event mit `new_status = REMOVED` darf der Server für diese XID kein weiteres `DEVICE_STATUS_CHANGED`-Event mehr senden. Die XID wird nie einem anderen Device zugewiesen.

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
- Offset 48: `CARD64 submission_token`, der vom Client in `QueueSubmit` angegebene Token. Er ist ungleich null und innerhalb der zugehörigen X11-Client-Verbindung eindeutig; die Regeln aus [QueueSubmit](queue-submission.md) gelten unverändert.

Die Felder `queue_family_index` und `queue_index` bezeichnen exakt die Queue, an die diese Submission mit `QueueSubmit` übergeben wurde. Sie sind keine globalen Queue-IDs und müssen eine für das angegebene logische Device tatsächlich erstellte Queue identifizieren.

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

## Voraussetzung fuer lange XGE-Events

Alle in diesem Kapitel definierten Events sind laenger als der normale 32-Byte-X11-Event. Vor dem Versand solcher Events muss der Server wissen, dass der jeweilige Client XGE unterstuetzt; andernfalls kann der X11-Bytestrom fuer einen Client ohne XGE-Unterstuetzung falsch ausgerichtet werden.

Ein XAverius-Client muss deshalb vor dem Erzeugen eines logischen Devices oder vor jedem `SelectEvents`-Request erfolgreich `GEQueryVersion` ausfuehren und mindestens XGE 1.0 ausgehandelt haben. Der XAverius-Server muss diesen erfolgreichen Austausch pro Verbindung verfolgen. Ohne ausgehandelte XGE-Unterstuetzung werden `CreateDevice`, `CreateDefaultDevice` und `SelectEvents` mit `BadMatch` abgewiesen; bei `SelectEvents` bleibt die vorherige Auswahl unveraendert. Ein Server, der XGE nicht unterstuetzt, darf XAverius nicht als verfuegbare Extension anbieten.

## Event-Auswahl: `SelectEvents`

Die Event-Type-IDs sind in der [zentralen Event-Registry](../registries/event-types.md) festgelegt. Sie sind von Request-Subopcodes, Error-Offsets und dem serverseitig vergebenen XGE-Event-Base zu unterscheiden.

`SelectEvents` ist ein Void-Request mit fester Gesamtlänge von 32 Bytes. Das Common-Header-Feld `flags` bei Offset 5 muss 0 sein; das reservierte Common-Header-Feld bei Offset 6 muss ebenfalls 0 sein. Der Request ersetzt atomar die bisherige Maske für genau einen Scope dieser X11-Verbindung; er fügt keine Bits hinzu und entfernt keine anderen Scopes.

| Offset | Typ | Feld |
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

Für nicht verwendete Felder müssen die genannten Nullwerte exakt eingehalten werden. Unbekannte Scope-Werte, nicht-null reservierte Felder, ungültige Maskenbits oder Scope/Feld-Kombinationen ergeben `BadValue`. Unbekannte/nicht-live XIDs ergeben `BadValue`; falscher Ressourcentyp oder fremde Client-Ownership ergeben `BadMatch`. Eine nicht existierende Queue innerhalb eines gültigen Devices ergibt `BadValue`. Bei jedem Fehler bleibt die vorherige Auswahl unverändert.

Die Masken sind scopeabhängig:

| Scope | Bit | Event |
|---|---:|---|
| `CONNECTION` | 0 | `DEVICE_STATUS_CHANGED` |
| `DEVICE` | 0 | `DEVICE_MEMORY_PRESSURE` |
| `DEVICE` | 1 | `DEVICE_IDLE` |
| `QUEUE` | 0 | `SUBMISSION_COMPLETE` |
| `QUEUE` | 1 | `SUBMISSION_FAILED` |

Alle anderen Bits sind reserviert und müssen abgewiesen werden. `event_mask = 0` hebt die Auswahl für den angegebenen Scope auf. Das Aufheben einer Device- oder Queue-Maske entfernt keine Auswahl anderer Scopes. Bei erfolgreicher Zerstörung eines logischen Devices werden seine Device- und Queue-Auswahlen entfernt; eine Connection-Auswahl bleibt bestehen.

`ASYNC_ERROR` und `DEVICE_LOST` sind nicht maskierbar und werden unabhängig von `SelectEvents` zugestellt, solange die Verbindung Events empfangen kann. Diese Regel unterliegt den Lebensdauergrenzen aus [Resource lifetime and ownership](resource-lifetime.md): Nach erfolgreicher Verarbeitung von `DestroyDevice` dürfen keine neuen Events mit der zerstörten `device_xid` erzeugt oder zugestellt werden; bereits vorher in den X11-Ausgabestrom eingereihte Events bleiben unberührt. `DEVICE_STATUS_CHANGED` wird nur über die Connection-Maske zugestellt. Die beiden Submission-Events werden nur zugestellt, wenn das jeweilige Queue-Maskenbit bei Eintritt des terminalen Submission-Ergebnisses gesetzt ist. Die Auswahl beeinflusst niemals die Ausführung, den internen terminalen Zustand oder die Fence-/Semaphore-Zustände. Pro angenommener Submission darf niemals sowohl `SUBMISSION_COMPLETE` als auch `SUBMISSION_FAILED` als terminales Event ausgeliefert werden.

Wenn die Verbindung geschlossen ist oder der X11-Server Events für diese Verbindung nicht mehr zustellen kann, ist keine Eventzustellung garantiert. Das ändert nicht den internen terminalen Ausgang der Submission. Ein fehlgeschlagenes Event-Senden darf weder die GPU-/Backend-Abwicklung blockieren noch eine zweite terminale Zustellung auslösen.

Die Event-Type-IDs und event-lokalen Werte sind in der [Event-Registry](../registries/event-types.md) registriert. XGE verwendet den Core-Eventcode GenericEvent (35). Ein XAverius-Event wird durch den XAverius-Major-Opcode im XGE-Feld extension und die registrierte Event-Type-ID im Feld evtype identifiziert. Der Major-Opcode wird ueber die normale X11-Extension-Abfrage ermittelt; es gibt kein separates XAverius-XGE-Event-Base.
