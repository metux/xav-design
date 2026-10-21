# 8. Queue Submission und Synchronisation

## 8.1 Queue-Adressierung

Queues werden durch Device-XID, Queue-Family-Index und Queue-Index adressiert. Der Server muss prüfen, ob die Queue für dieses logische Device tatsächlich erstellt wurde.

## 8.2 `QueueSubmit`

Request-Layout:

| Offset | Typ | Feld |
|---:|---|---|
| 8 | XID | Device-XID |
| 12 | CARD32 | Queue-Family-Index |
| 16 | CARD32 | Queue-Index |
| 20 | XID | Fence-XID, 0 bedeutet keine Fence |
| 24 | CARD16 | Command-Buffer-Count |
| 26 | CARD16 | Wait-Semaphore-Count |
| 28 | CARD16 | Signal-Semaphore-Count |
| 30 | CARD16 | `reserved = 0` |
| 32 | variable | Command-Buffer-XIDs, Wait-Entries, Signal-Entries |

Jeder Wait-Entry ist 16 Bytes groß:

- Relativer Offset 0: Semaphore-XID
- Offset 4: `CARD64 wait_value`
- Offset 12: `CARD32 wait_stage_mask`

Jeder Signal-Entry ist 12 Bytes groß:

- Relativer Offset 0: Semaphore-XID
- Offset 4: `CARD64 signal_value`

Gesamtlänge:

`32 + 4*C + 16*W + 12*S`

Vorgesehene Wait-Stage-Bits:

- Bit 0: `DRAW_INDIRECT`
- Bit 1: `COMPUTE_SHADER`
- Bit 2: `TRANSFER`
- Bit 3: `ALL_COMMANDS`
- Bits 4–31: reserviert

`ALL_COMMANDS` darf nicht mit anderen Bits kombiniert werden. Die konkrete Vulkan-Zuordnung und die zulässigen Masks für jede Queue-Art müssen vor der Implementierung final geprüft werden. Für den Compute-only-Pfad sind insbesondere Compute, Transfer und All-Commands relevant.

Vor der Annahme werden alle Command Buffer und Synchronisationsobjekte geprüft. Alle Ressourcen müssen zum angegebenen Device gehören. Jeder Command Buffer muss ausführbar sein. Eine angegebene Fence muss `UNSIGNALED` sein und darf nicht bereits pending sein.

Doppelte Wait- oder Signal-Einträge sind in v0.1 ungültig. Dieselbe Semaphore darf in einer Submission nicht gleichzeitig im Wait- und Signal-Array stehen.

**Atomaritätsgarantie:** Wird der Request abgelehnt, wird keine Submission angelegt und kein Synchronisationszustand verändert. Bei Annahme bedeutet der Request nur, dass die Arbeit eingereiht wurde; nicht, dass sie bereits abgeschlossen ist.

`QueueSubmit` ist ein Void-Request.

## 8.3 Semaphoren erstellen

`CreateSemaphore` hat 28 Bytes:

- Offset 8: Device-XID
- Offset 12: Semaphore-XID
- Offset 16: `CARD32 semaphore_type`
- Offset 20: `CARD64 initial_value`

Typen:

- `BINARY = 0`
- `TIMELINE = 1`

Für Binary-Semaphoren muss `initial_value = 0` sein. Binary-Semaphoren beginnen unsignaled.

## 8.4 Binary-Semaphoren

Binary-Semaphoren folgen den Vulkan-Signal-/Wait-Regeln.

- Ein Signal darf nicht mehrere konkurrierende Waits erfüllen.
- Host-Counter-Abfragen, Host-Waits und Host-Signals sind für Binary-Semaphoren ungültig.
- Pending Signal-/Wait-Zustände müssen atomar validiert werden.
- Ein Signal und ein Wait müssen nach den geltenden Vulkan-Regeln zusammenpassen.

Die vollständigen Regeln für noch ausstehende Signal-/Wait-Operationen sind noch zu präzisieren.

## 8.5 Timeline-Semaphoren

Timeline-Semaphoren besitzen einen monoton steigenden unsigned 64-bit Counter.

- Ein Wait ist erfüllt, sobald der Counter mindestens den angeforderten Wert erreicht.
- Ein Wait darf eingereiht werden, bevor das Signal eingereiht wurde, das ihn erfüllt.
- Signalwerte müssen größer als der aktuelle Counter und mit allen Pending-Signalen konsistent sein.
- Mehrere Signal-Entries derselben Timeline-Semaphore in einem einzelnen `QueueSubmit` sind in v0.1 nicht erlaubt.

## 8.6 `GetSemaphoreCounterValue`

Request: 16 Bytes; Device-XID bei Offset 8, Semaphore-XID bei Offset 12.

Nur für Timeline-Semaphoren.

Reply:

- Offset 8: `CARD64 counter_value`
- Offset 16–31: reserviert, null
- Reply-Payload-Länge: null

## 8.7 `WaitSemaphores`

Fester Request-Header: 28 Bytes.

- Offset 8: Device-XID
- Offset 12: `CARD32 semaphore_count`
- Offset 16: `CARD32 wait_mode`
- Offset 20: `CARD64 timeout_ns`
- Offset 28: Array aus 12-Byte-Entries

Jeder Entry enthält Semaphore-XID und `CARD64 wait_value`.

Wait-Modi:

- `WAIT_ANY = 0`
- `WAIT_ALL = 1`

Die Anzahl muss mindestens 1 sein. Alle Semaphoren müssen Timeline-Semaphoren desselben Devices sein; doppelte XIDs sind unzulässig.

Timeout:

- 0: nicht blockierend
- `UINT64_MAX`: unendlich
- sonst: Nanosekunden

Der Reply enthält bei Offset 8 den Status `SUCCESS = 0` oder `TIMEOUT = 1`. Ein Timeout ist ein normaler Reply und kein X11-Fehler.

## 8.8 `SignalSemaphore`

Request: 24 Bytes.

- Offset 8: Device-XID
- Offset 12: Semaphore-XID
- Offset 16: `CARD64 signal_value`

Nur Timeline-Semaphoren sind erlaubt. Der Signalwert muss größer als der aktuelle Wert und mit allen ausstehenden Signalen konsistent sein. Prüfung und Signaloperation sind atomar.

# 9. Fences

## 9.1 Zustände

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

## 9.2 `CreateFence`

Gesamtlänge: 24 Bytes.

- Offset 8: Device-XID
- Offset 12: Fence-XID
- Offset 16: `CARD32 create_flags = 0`
- Offset 20: `CARD32 reserved = 0`

## 9.3 `GetFenceStatus`

Request: 16 Bytes; Device-XID bei Offset 8, Fence-XID bei Offset 12.

Reply: 32 Bytes.

- Byte 1: Fence-Status
- Reply-Länge: null
- Offsets 8–31: reserviert, null

## 9.4 `WaitForFence`

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

## 9.5 `ResetFence`

Request: 16 Bytes; Device-XID bei Offset 8, Fence-XID bei Offset 12.

Nur `SIGNALED` und `FAILED` dürfen zurückgesetzt werden. Ein Reset aus `PENDING` oder `UNSIGNALED` ergibt `INVALID_SYNCHRONIZATION_STATE`. Bei verlorenem Device wird `DEVICE_LOST` zurückgegeben.

## 9.6 Fence-Zerstörung

Die öffentliche Fence-XID wird bei erfolgreicher Zerstörung ungültig. Die interne Fence bleibt erhalten, solange angenommene Arbeit sie benötigt.

Die konservative v0.1-Regel lautet: Eine pending Fence kann nicht zerstört werden. Die genaue Fehlerzuordnung und das Verhalten nach Device Loss müssen mit der allgemeinen Zerstörungsregel konsistent umgesetzt werden.

# 12. XAverius-Events

Alle folgenden Events verwenden XGE.

## 12.1 `ASYNC_ERROR`

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

## 12.2 `DEVICE_LOST`

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

## 12.3 `DEVICE_STATUS_CHANGED`

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

## 12.4 `DEVICE_MEMORY_PRESSURE`

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

## 12.5 `DEVICE_IDLE`

Gesamtlänge: 48 Bytes; XGE `length = 4`.

- Offset 32: Device-XID
- Offset 36: `CARD32 idle_reason`
- Offset 40: `CARD64 device_generation`

Gründe:

- 0: `IDLE_REASON_UNSPECIFIED`
- 1: `NO_PENDING_WORK`
- 2: `WORK_COMPLETED`

## 12.6 `SUBMISSION_COMPLETE`

Gesamtlänge: 56 Bytes; XGE `length = 6`.

- Offset 32: Device-XID
- Offset 36: `CARD32 queue_family_index`
- Offset 40: `CARD32 queue_index`
- Offset 44: `CARD32 reserved = 0`
- Offset 48: `CARD64 submission_id`

## 12.7 `SUBMISSION_FAILED`

Gesamtlänge: 56 Bytes; XGE `length = 6`.

- Offset 32: Device-XID
- Offset 36: `CARD32 queue_family_index`
- Offset 40: `CARD32 queue_index`
- Offset 44: `CARD32 failure_class`
- Offset 48: `CARD64 submission_id`

Failure-Class-Werte:

- 0: `EXECUTION_FAILED`
- 1: `DEVICE_LOST`

## 12.8 Event-Auswahl

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

# 13. Ordering- und Synchronisationsgarantien

1. Requests desselben X11-Clients werden in X11-Protokollreihenfolge verarbeitet.
2. Ein erfolgreicher `WriteBuffer`-Reply garantiert abgeschlossenen Transfer und Sichtbarkeit für spätere abhängige XAverius-GPU-Arbeit.
3. Ein angenommener `QueueSubmit` ist nicht automatisch abgeschlossen.
4. `ReadBuffer` antwortet erst, wenn die angeforderten Daten bereit sind und notwendige GPU-/Host-Visibility-Operationen erfolgt sind.
5. X11-`Sync` bestätigt die Verarbeitung vorheriger X11-Requests, nicht die GPU-Completion.
6. XAverius synchronisiert die von `WriteBuffer` und `ReadBuffer` benötigten Transfergrenzen automatisch.
7. XAverius leitet keine beliebigen Shader-zu-Shader-Abhängigkeiten aus dem Inhalt von Shadern ab.
8. Clients bleiben für explizite GPU-Abhängigkeiten zwischen beliebigen Commands verantwortlich.
9. Für die erste Implementierung ist eine konservative vollständige Device-Synchronisation akzeptabel.
10. Nach angenommener asynchroner Arbeit werden Fehler durch Events und Synchronisationszustände gemeldet.

Die genaue Queue-übergreifende Reichweite der `WriteBuffer`-Sichtbarkeitsgarantie muss noch abschließend definiert werden.
