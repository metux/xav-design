# XAverius-Events

Alle folgenden Events verwenden XGE. Die sieben Compute-Baseline-Events verwenden IDs aus der [zentralen Event-Registry](../registries/event-types.md). Die presentation-only Events IMAGE_RELEASED (7) und PRESENTATION_COMPLETE (8) sowie deren Statuswerte stehen in der separaten [Presentation-Event-Registry](../registries/presentation-events.md) und dürfen nur vom presentation-capable Profil verwendet werden. Der gemeinsame 32-Byte-Header entspricht dem X Generic Event-Format:

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

`error_code` enthält den numerischen **Offset** aus der zentralen XAverius-Fehler-Registry, nicht den absoluten X11-Fehlercode (`first_error + offset`) und keinen Core-X11-Fehlercode. `submission_token` ist genau dann 0, wenn der Fehler keiner angenommenen Submission zugeordnet ist. Bei `origin = ORIGIN_QUEUE_SUBMIT` MUSS `submission_token` daher ungleich null sein und den Token der betroffenen, zuvor angenommenen `QueueSubmit`-Anforderung unverändert enthalten. Bei anderen Origins darf der Token nur dann ungleich null sein, wenn der Fehler tatsächlich einer solchen Submission zugeordnet ist; ein nicht-null Token darf niemals eine abgewiesene `QueueSubmit`-Anforderung bezeichnen. `ASYNC_ERROR` ist eine Diagnose für einen Fehler nach Annahme einer Operation; ein vor Annahme erkannter Fehler wird synchron als X11-Fehler oder ausdrücklich definierter normaler Reply gemeldet und darf nicht zusätzlich als `ASYNC_ERROR` für dieselbe Ablehnung ausgegeben werden. Insbesondere darf ein angenommener `QueueSubmit` nach einem Ausführungsfehler keinen verspäteten X11-Request-Fehler erzeugen: sein terminaler Ausgang wird über `SUBMISSION_FAILED` und Synchronisationszustände gemeldet; `ASYNC_ERROR` darf ergänzende Diagnose liefern.

## `DEVICE_LOST`

Gesamtlänge: 48 Bytes; XGE `length = 4`.

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


## `IMAGE_RELEASED`

Gesamtlänge: 64 Bytes; XGE `length = 8`.

| Offset | Typ | Feld |
|---:|---|---|
| 32 | XID | Device-XID |
| 36 | CARD32 | `queue_family_index` der akzeptierten Präsentationsoperation |
| 40 | CARD32 | `queue_index` der akzeptierten Präsentationsoperation |
| 44 | XID | Swapchain-XID |
| 48 | CARD32 | `image_index` |
| 52 | CARD32 | `reserved = 0` |
| 56 | CARD64 | `presentation_token` aus dem Client-Request |

Dieses Event bedeutet ausschließlich, dass die Präsentationsbackend-Zugriffe auf dieses Image beendet sind und es wieder erworben werden darf. Es beweist nicht, dass die Präsentation ihren Completion-Punkt erreicht hat. Ein Event darf nur für eine zuvor akzeptierte Präsentationsoperation und höchstens einmal pro akzeptierter Präsentationsoperation ausgegeben werden.

## `PRESENTATION_COMPLETE`

Gesamtlänge: 64 Bytes; XGE `length = 8`.

| Offset | Typ | Feld |
|---:|---|---|
| 32 | XID | Device-XID |
| 36 | CARD32 | `queue_family_index` der akzeptierten Präsentationsoperation |
| 40 | CARD32 | `queue_index` der akzeptierten Präsentationsoperation |
| 44 | XID | Swapchain-XID |
| 48 | CARD32 | `image_index` |
| 52 | CARD32 | `status` aus der Präsentations-Event-Status-Registry |
| 56 | CARD64 | `presentation_token` aus dem Client-Request |

Dieses Event bedeutet, dass die Operation den definierten Completion-Punkt der Präsentationsbackend erreicht hat. `SUCCESS` bedeutet, dass die Backend-Präsentation erfolgreich abgeschlossen wurde; andere Statuswerte beschreiben den terminalen Fehlerzustand. Das Event darf unabhängig von `IMAGE_RELEASED` eintreffen. Beide Events werden, falls relevant, separat und höchstens einmal pro akzeptierter Präsentationsoperation zugestellt. `PRESENTATION_COMPLETE` allein macht das Image nicht erneut erwerbbar; nur `IMAGE_RELEASED` tut das. Falls ein Fehler die Wiederverwendung verhindert, wird das Image stattdessen invalidiert und die Swapchain als nicht mehr verwendbar markiert.

## Voraussetzung fuer lange XGE-Events

Alle in diesem Kapitel definierten Events sind laenger als der normale 32-Byte-X11-Event. Vor dem Versand solcher Events muss der Server wissen, dass der jeweilige Client XGE unterstuetzt; andernfalls kann der X11-Bytestrom fuer einen Client ohne XGE-Unterstuetzung falsch ausgerichtet werden.

Ein XAverius-Client muss deshalb vor dem Erzeugen eines logischen Devices oder vor jedem `SelectEvents`-Request erfolgreich `GEQueryVersion` ausfuehren und mindestens XGE 1.0 ausgehandelt haben. Der XAverius-Server muss diesen erfolgreichen Austausch pro Verbindung verfolgen. Ohne ausgehandelte XGE-Unterstuetzung werden `CreateDevice`, `CreateDefaultDevice` und `SelectEvents` mit `BadMatch` abgewiesen; bei `SelectEvents` bleibt die vorherige Auswahl unveraendert. Ein Server, der XGE nicht unterstuetzt, darf XAverius nicht als verfuegbare Extension anbieten.

## Event-Auswahl: `SelectEvents`

Die Compute-Baseline-Event-Type-IDs sind in der [zentralen Event-Registry](../registries/event-types.md) festgelegt; presentation-only IDs sind in der [Presentation-Event-Registry](../registries/presentation-events.md) festgelegt. Beide Namespaces verwenden dieselben append-only Event-Type-IDs und dürfen nicht miteinander kollidieren. Sie sind von Request-Subopcodes und Error-Offsets zu unterscheiden.

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
| `QUEUE` | 2 | `IMAGE_RELEASED` |
| `QUEUE` | 3 | `PRESENTATION_COMPLETE` |

Alle anderen Bits sind reserviert und müssen abgewiesen werden. Die Präsentationsbits sind nur im presentation-capable Profil gültig; ein Compute-only Server muss sie als unbekannte Maskenbits mit `BadValue` zurückweisen. `event_mask = 0` hebt die Auswahl für den angegebenen Scope auf. Das Aufheben einer Device- oder Queue-Maske entfernt keine Auswahl anderer Scopes. Bei erfolgreicher Zerstörung eines logischen Devices werden seine Device- und Queue-Auswahlen entfernt; eine Connection-Auswahl bleibt bestehen.

`ASYNC_ERROR` und `DEVICE_LOST` sind nicht maskierbar und werden unabhängig von `SelectEvents` zugestellt, solange die Verbindung Events empfangen kann. Diese Regel unterliegt den Lebensdauergrenzen aus [Resource lifetime and ownership](resource-lifetime.md): Nach erfolgreicher Verarbeitung von `DestroyDevice` dürfen keine neuen Events mit der zerstörten `device_xid` erzeugt oder zugestellt werden; bereits vorher in den X11-Ausgabestrom eingereihte Events bleiben unberührt. `DEVICE_STATUS_CHANGED` wird nur über die Connection-Maske zugestellt. Die beiden Submission-Events werden nur zugestellt, wenn das jeweilige Queue-Maskenbit bei Eintritt des terminalen Submission-Ergebnisses gesetzt ist. Die Auswahl beeinflusst niemals die Ausführung, den internen terminalen Zustand oder die Fence-/Semaphore-Zustände. Pro angenommener Submission darf niemals sowohl `SUBMISSION_COMPLETE` als auch `SUBMISSION_FAILED` als terminales Event ausgeliefert werden.

**Serialisierung asynchroner Event-Entscheidungen:** Die Verarbeitung eines erfolgreichen `SelectEvents`, die erfolgreiche Verarbeitung von `DestroyDevice` und der terminale Übergang einer Submission einschließlich Entscheidung über das zugehörige terminale Event müssen über einen gemeinsamen serialisierten Serverzustand geordnet werden. Der erfolgreiche `SelectEvents`-Request wirkt ab seinem Linearisierungspunkt; ein Submission-Abschluss wertet die dann geltende Queue-Maske aus. Der terminale Übergang und die Entscheidung, das zugehörige Event in den X11-Ausgabestrom einzureihen oder zu unterdrücken, bilden gegenüber `DestroyDevice` eine unteilbare Entscheidung: Wird der Submission-Abschluss zuerst linearisiert und das Event eingereiht, bleibt dieses bereits eingereihte Event unberührt; wird `DestroyDevice` zuerst erfolgreich linearisiert, wird kein neues Event für dessen zerstörte Device-XID eingereiht. Ein späterer Backend-Callback darf diese Entscheidung nicht nachträglich ändern oder ein unterdrücktes Event erneut einreihen. Diese Serialisierung verändert weder die Reihenfolge der X11-Requests einer Verbindung noch die GPU-Abhängigkeiten zwischen Submissions.

Wenn die Verbindung geschlossen ist oder der X11-Server Events für diese Verbindung nicht mehr zustellen kann, ist keine Eventzustellung garantiert. Das ändert nicht den internen terminalen Ausgang der Submission. Ein fehlgeschlagenes Event-Senden darf weder die GPU-/Backend-Abwicklung blockieren noch eine zweite terminale Zustellung auslösen.

Die Compute-Baseline-Event-Type-IDs und event-lokalen Werte sind in der [Event-Registry](../registries/event-types.md) registriert; presentation-only Event-IDs und Statuswerte stehen in der [Presentation-Event-Registry](../registries/presentation-events.md). XGE verwendet den Core-Eventcode GenericEvent (35). Ein XAverius-Event wird durch den XAverius-Major-Opcode im XGE-Feld extension und die registrierte Event-Type-ID im Feld evtype identifiziert. Der Major-Opcode wird ueber die normale X11-Extension-Abfrage ermittelt; es gibt kein separates XAverius-XGE-Event-Base.
