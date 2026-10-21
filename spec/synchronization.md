# Synchronization objects

## Semaphoren erstellen

`CreateSemaphore` hat 28 Bytes:

- Offset 8: Device-XID
- Offset 12: Semaphore-XID
- Offset 16: `CARD32 semaphore_type`
- Offset 20: `CARD64 initial_value`

Typen:

- `BINARY = 0`
- `TIMELINE = 1`

Für Binary-Semaphoren muss `initial_value = 0` sein. Binary-Semaphoren beginnen unsignaled. In `QueueSubmit` müssen die `wait_value`- und `signal_value`-Felder für Binary-Semaphoren ebenfalls null sein.

## Binary-Semaphoren

Binary-Semaphoren folgen den Vulkan-Signal-/Wait-Regeln.

- Ein Signal darf nicht mehrere konkurrierende Waits erfüllen.
- Host-Counter-Abfragen, Host-Waits und Host-Signals sind für Binary-Semaphoren ungültig.
- Pending Signal-/Wait-Zustände müssen atomar validiert werden.
- Ein Signal und ein Wait müssen nach den geltenden Vulkan-Regeln zusammenpassen.

In v0.1 darf für eine Binary-Semaphore höchstens eine Signaloperation und höchstens eine Wait-Operation gleichzeitig pending sein. Ein einzelner pending Wait darf auf ein Signal warten, das noch nicht eingereiht wurde; ebenso darf ein Signal pending sein, bevor der passende Wait eingereiht wird. Sobald ein Signal durch einen Wait konsumiert wurde, kann die Semaphore erneut verwendet werden. Eine zweite pending Signaloperation oder eine zweite pending Wait-Operation auf derselben Binary-Semaphore wird bei `QueueSubmit` atomar mit `INVALID_SYNCHRONIZATION_STATE` abgewiesen. Ein erfolgreicher Wait konsumiert das Signal genau einmal.

## Timeline-Semaphoren

Timeline-Semaphoren besitzen einen monoton steigenden unsigned 64-bit Counter.

- Ein Wait ist erfüllt, sobald der Counter mindestens den angeforderten Wert erreicht.
- Ein Wait darf eingereiht werden, bevor das Signal eingereiht wurde, das ihn erfüllt.
- Signalwerte müssen größer als der aktuelle Counter und mit allen Pending-Signalen konsistent sein.
- Mehrere Signal-Entries derselben Timeline-Semaphore in einem einzelnen `QueueSubmit` sind in v0.1 nicht erlaubt.

## `GetSemaphoreCounterValue`

Request: 16 Bytes; Device-XID bei Offset 8, Semaphore-XID bei Offset 12.

Nur für Timeline-Semaphoren.

Reply:

- Offset 8: `CARD64 counter_value`
- Offset 16–31: reserviert, null
- Reply-Payload-Länge: null

## `WaitSemaphores`

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

## `SignalSemaphore`

Request: 24 Bytes; Void-Request ohne Reply.

- Offset 8: Device-XID
- Offset 12: Semaphore-XID
- Offset 16: `CARD64 signal_value`

Nur Timeline-Semaphoren sind erlaubt. Der Signalwert muss größer als der aktuelle Counter und mit allen ausstehenden Signalen konsistent sein. Validierung und Host-Signaloperation bilden eine atomare Request-Operation.

Der Server führt das Host-Signal aus, bevor er mit der Verarbeitung eines späteren Requests derselben X11-Verbindung fortfährt. Sobald die Verarbeitung des Requests fortgesetzt wird, ist der Counter aktualisiert und jeder dadurch erfüllte Wait darf fortschreiten. Der Server darf den Request nicht als abgeschlossen behandeln, solange das Host-Signal nicht erfolgreich ausgeführt wurde.

Validierungsfehler und unmittelbar feststellbare Vulkan-Fehler werden als normale X11-Request-Fehler gemeldet; der Request hinterlässt dann keine teilweise ausgeführte Signaloperation. Ein nach Annahme der Operation auftretender Device Loss wird über die normalen Device-Loss-/asynchronen Fehlermechanismen gemeldet. Da der Request kein Reply erzeugt, kann der Client Fehler mit der üblichen X11-Fehlerbehandlung beziehungsweise `XSync` erkennen. Ein späterer Request derselben Verbindung darf nicht vor Abschluss der Host-Signaloperation ausgeführt werden.

## Fences

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

- Byte 1: Fence-Status (`UNSIGNALED = 0`, `PENDING = 1`, `SIGNALED = 2`, `FAILED = 3`)
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

Eine Fence darf nur zerstört werden, wenn sie nicht `PENDING` ist. Der Destroy-Request wird andernfalls mit `INVALID_SYNCHRONIZATION_STATE` abgewiesen und lässt die XID sowie den Fence-Zustand unverändert. Nach erfolgreicher Zerstörung wird die öffentliche XID sofort ungültig; interne Daten dürfen bis zum Ende noch möglicher Serverzugriffe erhalten bleiben. Eine Fence im Zustand `FAILED` darf zerstört werden.

Bei Device Loss werden Fences aus nicht-terminalen Submissions nach `FAILED` überführt. Sie dürfen anschließend normal zerstört werden; die Device-weite Kaskadeninvalidierung bleibt unabhängig davon zulässig.
