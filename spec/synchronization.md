# Synchronization objects

## Creating Semaphores

`CreateSemaphore` has a total length of 28 bytes:

- Offset 8: Device-XID
- Offset 12: Semaphore-XID
- Offset 16: `CARD32 semaphore_type`
- Offset 20: `CARD64 initial_value`

Types:

- `BINARY = 0`
- `TIMELINE = 1`

For binary semaphores, `initial_value` MUST be zero. Binary semaphores begin unsignaled. In `QueueSubmit`, the `wait_value` and `signal_value` fields for binary semaphores MUST also be zero. Unknown or non-live device XIDs result in `BadValue`; a live resource of the wrong type or foreign device ownership results in `BadMatch`. An unavailable or lost logical device results in `DEVICE_UNAVAILABLE` or `DEVICE_LOST`, respectively. Backend allocation failures result in `ALLOCATION_FAILED`. Creation is atomic: on any failure, the semaphore XID remains unallocated.

## Binary Semaphores

Binary-Semaphoren folgen den Vulkan-Signal-/Wait-Regeln.

- A signal MUST NOT satisfy multiple competing waits.
- Host counter queries, host waits, and host signals are invalid for binary semaphores.
- Pending signal and wait states MUST be validated atomically.
- A signal and a wait MUST be compatible under the applicable Vulkan rules.

In v0.1 darf für eine Binary-Semaphore höchstens eine Signaloperation und höchstens eine Wait-Operation gleichzeitig pending sein. Ein einzelner pending Wait darf auf ein Signal warten, das noch nicht eingereiht wurde; ebenso darf ein Signal pending sein, bevor der passende Wait eingereiht wird. Der Server verfolgt dafür getrennt den Signalzustand (`UNSIGNALED`, `SIGNAL_PENDING`, `SIGNALED` oder `UNTRUSTED`) und die Referenzen auf angenommene Wait-/Signaloperationen. `UNTRUSTED` bedeutet, dass der Server den Backend-Payload-Zustand nach einem fehlgeschlagenen Vorgang nicht sicher bestimmen kann; dieser Zustand ist nicht gleichbedeutend mit `UNSIGNALED`. Die Annahme eines Waits konsumiert das Signal nicht sofort: konsumiert wird es erst, wenn der Wait auf GPU-/Backend-Seite erfolgreich erfüllt ist. Erst nach dieser Konsumption darf ein neuer Signalzyklus beginnen; eine bloß angenommene oder noch pending Wait-Operation gibt das Signal nicht frei. Ein Signal, dessen Operation erfolgreich abgeschlossen wurde, bleibt verfügbar, bis genau ein Wait es konsumiert. Eine zweite Signaloperation wird abgewiesen, solange ein Signal bereits verfügbar ist oder eine Signaloperation pending ist; eine zweite pending Wait-Operation wird abgewiesen, solange ein vorheriger Wait noch nicht erfüllt/abgeschlossen ist. Solche Ablehnungen bei `QueueSubmit` erfolgen atomar mit `INVALID_SYNCHRONIZATION_STATE`. Ein Fehler oder Device Loss darf ein Signal nicht als erfolgreich verfügbar oder konsumiert markieren, wenn das nicht tatsächlich eingetreten ist; beim Device Loss werden betroffene Submissions fehlgeschlagen und das Semaphore-Objekt folgt den Device-Loss-Regeln. Kann der Server nach einem angenommenen, fehlgeschlagenen Backend-Vorgang nicht sicher nachweisen, ob eine Binary-Semaphore-Signal- oder Wait-Operation wirksam wurde, muss er die Binary-Semaphore als `UNTRUSTED` markieren. Dieser Zustand ist terminal für normale Nutzung: weitere Queue-Waits und Queue-Signals auf dieser Semaphore werden vor Annahme mit `DEPENDENCY_FAILED` abgewiesen. Der Server darf die Semaphore nicht als signalverfügbar oder unsignaled behandeln und darf sie nicht durch einen lokalen Zustandsreset wieder nutzbar machen. Die öffentliche Semaphore-XID bleibt bis zu ihrer zulässigen Zerstörung live; interne Backend-Referenzen bleiben bis zur Quieszenz erhalten. Ist dagegen nachweisbar, dass die fehlgeschlagene Operation das Semaphore-Payload nicht verändert hat, bleibt der vorherige bestätigte Signalzustand erhalten. Device Loss folgt weiterhin den strengeren Device-weiten Regeln.

## Presentation Waits on Binary Semaphores

`QueuePresent` verwendet dieselbe globale Zustandsmaschine und dieselbe Pending-Wait-Exklusivität wie `QueueSubmit`. Ein angenommener Present reserviert atomar einen Wait-Slot pro angegebenem Binary-Semaphore; ein bereits inkompatibel wartender oder `UNTRUSTED` Semaphore führt zur synchronen atomaren Ablehnung. Die Annahme selbst konsumiert kein Signal. Konsumption wird erst registriert, wenn der Backend-Wait nachweislich erfolgreich war.

Endet eine angenommene Präsentation, bevor der Wait sicher erfüllt wurde, wird jede betroffene Semaphore separat abgewickelt: Nachweislich nicht konsumierte Payloads behalten ihren bestätigten Zustand und gültige Signalreservierungen; nachweislich konsumierte Payloads werden als konsumiert verbucht; bei unklarem Payload-Ergebnis wird die Semaphore `UNTRUSTED`. Die Wait-Reservierung wird genau einmal aufgehoben, wenn der Wait terminal ist. Eine unsichere Operation darf weder als erfolgreich konsumiert noch als ungesignaled zurückgesetzt werden. Bei Device Loss gelten die strengeren Device-weiten Regeln oben.

## Timeline Semaphores

Timeline-Semaphoren besitzen einen monoton steigenden unsigned 64-bit Counter.

- A wait is satisfied when the observable counter reaches or exceeds the requested value.
- A wait MAY be queued before the signal that satisfies it is queued.
- Signalwerte müssen größer als der aktuelle Counter und mit allen Pending-Signalen konsistent sein. Zur atomaren Validierung zählt ein angenommenes, noch nicht terminales Signal als pending, auch wenn sein Counter-Wert noch nicht erreicht ist; neue GPU-Signalwerte müssen größer als alle bereits reservierten pending Signalwerte derselben Semaphore sein. Ein pending GPU-Signal reserviert seinen Wert, erhöht aber den beobachtbaren Counter nicht.
- The observable counter advances only when the corresponding signal operation has actually completed successfully. Acceptance of a `QueueSubmit` request reserves the signal value but MUST NOT advance the counter prematurely.
- A successfully executed signal satisfies all previously queued waits whose values are reached; a wait does not modify the counter.
- Mehrere Signal-Entries derselben Timeline-Semaphore in einem einzelnen `QueueSubmit` sind in v0.1 nicht erlaubt.
- After a failed submission or device loss, a value that was only reserved and never successfully signaled MUST NOT be reported as reached. Reservations are released only when the corresponding operation becomes terminal; after device loss, no further normal signal operations are permitted on that device.

## `GetSemaphoreCounterValue`

Request: exactly 16 bytes; device XID at offset 8 and semaphore XID at offset 12. Any other total length results in `BadLength`. Unknown or non-live device or semaphore XIDs result in `BadValue`; a live resource of the wrong type, foreign client/device ownership, or cross-device use results in `BadMatch`.

Timeline semaphores only. If the logical device is already known to be lost, the request is rejected with `DEVICE_LOST`: the wire reply has no status field that can reliably distinguish an error from a counter value. The server MUST NOT return a purported current counter as a successful reply.

Reply:

- Offset 8: `CARD64 counter_value`
- Offset 16–31: reserviert, null
- Reply payload length: zero

## `WaitSemaphores`

Fixed request header: 28 bytes; total length: `28 + 12 * semaphore_count` bytes.

- Offset 8: Device-XID
- Offset 12: `CARD32 semaphore_count`
- Offset 16: `CARD32 wait_mode`
- Offset 20: `CARD64 timeout_ns`
- Offset 28: array of 12-byte entries

Each entry contains a semaphore XID and `CARD64 wait_value`.

Wait-Modi:

- `WAIT_ANY = 0`
- `WAIT_ALL = 1`

Die Request-Länge muss exakt `28 + 12 * semaphore_count` Bytes betragen; eine Längenabweichung oder ein arithmetischer Überlauf ergibt `BadLength`. Die synchrone Validierung folgt verbindlich dieser Reihenfolge: (1) Länge und checked-arithmetic, (2) `semaphore_count != 0`, gültiger `wait_mode` und keine doppelten Semaphore-XIDs (`BadValue`), (3) Device-XID und danach Semaphore-XIDs in Array-Reihenfolge auflösen (`BadValue` bei unbekannt/nicht-live), (4) Ressourcentyp, Client-/Device-Ownership und Cross-Device-Zugehörigkeit prüfen (`BadMatch`), (5) Device-Zustand prüfen, (6) prüfen, dass alle Semaphoren Timeline-Semaphoren sind (`BadMatch`). Die Prüfungen bis einschließlich Schritt 6 erfolgen vor Registrierung des Waits; jede synchrone Ablehnung hinterlässt keine Wait-Registrierung. Ein bereits verlorenes Device führt nach erfolgreicher XID-/Typ-/Ownership-Prüfung zu `DEVICE_LOST` als X11-Fehler. Für einen bereits registrierten offenen Wait ist Device Loss dagegen ein terminales Wait-Ergebnis und kein nachträglicher Request-Validierungsfehler; wird `DestroyDevice` verarbeitet, solange der Wait noch offen ist und Device Loss nicht zuvor terminal festgestellt wurde, ergibt sich `DEVICE_DESTROYED`.

### Timeout-Semantik

The following rules apply to `timeout_ns`:

- `0`: non-blocking; the server checks the condition once and replies immediately.
- `UINT64_MAX`: wait indefinitely until the condition is satisfied or the device is lost.
- Jeder andere Wert: Timeout in Nanosekunden, gemessen mit einer monotonen, nicht durch Systemzeitkorrekturen verstellten Uhr. Die Frist beginnt, sobald der Server diesen Request zur Ausführung übernimmt.

Der Server darf eine endliche Wartefrist intern in mehrere Warteabschnitte aufteilen, muss aber die ursprüngliche Frist beibehalten. Scheduler-Verzögerungen dürfen die Frist nicht absichtlich neu starten. Ist die Bedingung bei der abschließenden Zustandsprüfung erfüllt, wird `SUCCESS` zurückgegeben; andernfalls nach Ablauf der Frist `TIMEOUT`. Der Server muss keine Antwort exakt am Nanosekunden-Grenzpunkt liefern; die tatsächliche Antwort darf durch Scheduling verzögert eintreffen.

Ein offener Wait hat genau einen terminalen Ausgang. Der Server serialisiert die Feststellung von erfüllter Bedingung, Timeout, Device Loss und `DestroyDevice` mit den zugehörigen Zustandsübergängen: Der zuerst festgestellte terminale Ausgang gewinnt und darf nicht nachträglich überschrieben werden. Eine bereits festgestellte erfüllte Bedingung behält `SUCCESS`; ein zuerst festgestellter Device Loss beendet den Wait als `DEVICE_LOST`; wird `DestroyDevice` verarbeitet, solange der Wait noch offen ist und Device Loss nicht bereits festgestellt wurde, beendet `DEVICE_DESTROYED` den Wait. Bei Client-Disconnect wird die serverseitige Wait-Registrierung ohne Reply abgebrochen.

`WaitSemaphores` darf den X11-Request-Dispatcher nicht synchron blockieren. Der Server registriert die Wartebedingung und stellt den Reply später bereit, während er nachfolgende Requests derselben Verbindung weiterverarbeiten kann. Das ist notwendig, damit ein späteres `SignalSemaphore` oder `QueueSubmit` den erwarteten Wert liefern kann. Der Wait-Request selbst ordnet keine nachfolgenden GPU-Submissions und hält sie nicht zurück. Die Timeout-Frist beginnt bei der Übernahme des Wait-Requests und läuft auch dann weiter, wenn nachfolgende Requests verarbeitet werden.

Der Reply ist genau 32 Bytes lang. Offset 8 enthält einen `CARD32 status` mit `SUCCESS = 0` oder `TIMEOUT = 1`; Offsets 12–31 sind null und `reply.length = 0`. Ein Timeout ist ein normaler Reply und kein X11-Fehler. Ein Timeout verändert weder Semaphore-Counter noch Queue-, Fence- oder Semaphore-Zustände. Ein durch Device Loss unmöglich gewordener Wait wird mit `DEVICE_LOST` als normalem X11-Fehler beendet, nicht als `TIMEOUT` maskiert.

## `SignalSemaphore`

Request: 24 bytes; void request with no reply.

- Offset 8: Device-XID
- Offset 12: Semaphore-XID
- Offset 16: `CARD64 signal_value`

Die synchrone Validierung folgt verbindlich dieser Reihenfolge: (1) Gesamtlänge exakt 24 Bytes (`BadLength`), (2) Device-XID, danach Semaphore-XID auflösen (`BadValue` bei unbekannt/nicht-live), (3) Ressourcentyp, Client-/Device-Ownership und Cross-Device-Zugehörigkeit (`BadMatch`), (4) Device-Zustand (`DEVICE_UNAVAILABLE` beziehungsweise `DEVICE_LOST`), (5) Timeline-Typ und Signalwert-/Reservierungskonsistenz (`BadMatch` für Binary-Semaphoren, `INVALID_SYNCHRONIZATION_STATE` für ungültige Counter-/Reservierungsrelationen). Die Reihenfolge gilt auch bei gemischten Fehlern. Alle Prüfungen vor dem Signal bilden eine atomare Request-Operation; eine synchrone Ablehnung ändert weder Counter noch Reservierungen.

Nur Timeline-Semaphoren sind erlaubt. Der Signalwert muss größer als der aktuelle Counter sein. Zusätzlich muss er kleiner als jeder bereits reservierte, noch nicht terminale GPU-Signalwert derselben Semaphore sein; andernfalls wird der Request mit `INVALID_SYNCHRONIZATION_STATE` abgewiesen. Damit kann ein Host-Signal einen niedrigeren Wert liefern, der eine wartende Submission freigibt, ohne über eine niedrigere GPU-Reservierung hinwegzuspringen. Bei fehlenden GPU-Reservierungen ist jeder Wert größer als der aktuelle Counter zulässig. Validierung und Host-Signaloperation bilden eine atomare Request-Operation. Der Server prüft den aktuellen Counter und sämtliche Reservierungen atomar mit der Ausführung des Signals.

Der Server führt das Host-Signal aus, bevor er mit der regulären Verarbeitung des nächsten Requests derselben X11-Verbindung fortfährt. Ausnahme: Während ein früherer `WriteBuffer`-Request auf vorherige Submissions wartet, darf der Server einen späteren `SignalSemaphore`-Request vor Abschluss dieses `WriteBuffer` ausführen, sofern dies erforderlich ist, um die vorherigen Submissions fortschreiten zu lassen. Das Signal muss dabei weiterhin vollständig validiert und atomar ausgeführt werden. Spätere `QueueSubmit`-Requests bleiben bis zum Abschluss des `WriteBuffer` zurückgestellt und dürfen dessen Ordnungsgrenze nicht passieren. Sobald die Signaloperation erfolgreich ausgeführt ist, ist der Counter aktualisiert und jeder dadurch erfüllte Wait darf fortschreiten. Der Server darf den Signal-Request nicht als abgeschlossen behandeln, solange das Host-Signal nicht erfolgreich ausgeführt wurde.

Validierungsfehler und unmittelbar feststellbare Vulkan-Fehler werden als normale X11-Request-Fehler gemeldet; der Request hinterlässt dann keine teilweise ausgeführte Signaloperation. Ein nach Annahme der Operation auftretender Device Loss wird über die normalen Device-Loss-/asynchronen Fehlermechanismen gemeldet. Da der Request kein Reply erzeugt, kann der Client Fehler mit der üblichen X11-Fehlerbehandlung beziehungsweise `XSync` erkennen. Ein späterer Request derselben Verbindung darf nicht vor Abschluss der Host-Signaloperation ausgeführt werden.

## Destroying Semaphores

`DestroySemaphore` ist ein Void-Request mit fester Gesamtlänge von 16 Bytes: Device-XID bei Offset 8 und Semaphore-XID bei Offset 12. `DestroySemaphore` verwendet die allgemeinen Lebensdauerregeln aus [Resource lifetime and ownership](resource-lifetime.md). Die Zerstörung wird mit `INVALID_SYNCHRONIZATION_STATE` abgewiesen, solange ein angenommener Queue-Wait, ein Queue-Signal oder eine offene `WaitSemaphores`-Registrierung die exakte interne Semaphore-Identität referenziert oder eine andere laufende serverseitige Host-Operation die Semaphore verwendet. Eine Ablehnung ändert weder XID noch Synchronisationszustand. Eine Wait-Registrierung gilt nicht mehr als offen, sobald ihr terminales Ergebnis serverseitig serialisiert festgestellt wurde; ein noch nicht versendeter Reply blockiert die Zerstörung dann nicht. Nach erfolgreicher Zerstörung wird die öffentliche XID sofort ungültig; interne Daten bleiben erhalten, solange Backend-Zugriffe möglich sind. Bei Device Loss darf die Device-weite Kaskadeninvalidierung diese normale Ablehnung umgehen.

## Fences

## States

Defined states:

- `UNSIGNALED = 0`
- `PENDING = 1`
- `SIGNALED = 2`
- `FAILED = 3`

Transitions:

- Erstellung → `UNSIGNALED`
- accepted submission with a fence → `PENDING`
- erfolgreiche Completion → `SIGNALED`
- asynchronous execution failure → `FAILED`
- reset from `SIGNALED` or `FAILED` → `UNSIGNALED`
- rejected submission → state remains unchanged

## `CreateFence`

Total length: 24 bytes.

- Offset 8: Device-XID
- Offset 12: Fence-XID
- Offset 16: `CARD32 create_flags = 0`
- Offset 20: `CARD32 reserved = 0`

Unbekannte/nicht-live Device-XIDs ergeben `BadValue`; ein falscher live Ressourcentyp oder fremde Device-Ownership ergibt `BadMatch`. Bei einem nicht verfügbaren oder verlorenen logischen Device wird `DEVICE_UNAVAILABLE` beziehungsweise `DEVICE_LOST` gemeldet. Backend-Allokationsfehler ergeben `ALLOCATION_FAILED`. Die Erstellung ist atomar: bei jedem Fehler bleibt die Fence-XID unangelegt.

## `GetFenceStatus`

Request: exakt 16 Bytes; Device-XID bei Offset 8, Fence-XID bei Offset 12. Andere Längen ergeben `BadLength`. Unbekannte/nicht-live Device- oder Fence-XIDs ergeben `BadValue`; falscher live Ressourcentyp, fremde Client-/Device-Ownership oder Cross-Device-Verwendung ergeben `BadMatch`. Die Abfrage gibt den serverseitig gespeicherten Fence-Zustand zurück, auch nach Device Loss.

Reply: 32 bytes.

- Byte 0: standard X11 reply `response_type`
- Byte 1: Fence-Status (`UNSIGNALED = 0`, `PENDING = 1`, `SIGNALED = 2`, `FAILED = 3`)
- Offsets 2–3: standard X11 reply sequence number
- Offsets 4–7: standard `reply.length = 0`
- Offsets 8–31: XAverius-reserviert, null

## `WaitForFence`

Request: 24 Bytes exakt; eine andere Gesamtlänge ergibt `BadLength`.

- Offset 8: Device-XID
- Offset 12: Fence-XID
- Offset 16: `CARD64 timeout_ns`

Unbekannte/nicht-live Device- oder Fence-XIDs ergeben `BadValue`; falscher live Ressourcentyp, fremde Client-/Device-Ownership oder Cross-Device-Verwendung ergeben `BadMatch`. Diese Prüfungen erfolgen vor dem Anlegen einer Wait-Registrierung.

Der Reply ist genau 32 Bytes lang. Offset 8 enthält einen `CARD32 status`; Offsets 12–31 sind null und `reply.length = 0`.

Reply-Status:

- `SUCCESS = 0`
- `TIMEOUT = 1`
- `EXECUTION_FAILED = 2`
- `DEVICE_LOST = 3`
- `DEVICE_DESTROYED = 4`

Timeout und Ausführungsfehler werden als normale Reply-Statuswerte zurückgegeben. Für `timeout_ns` gilt dieselbe monotone Fristsemantik wie bei `WaitSemaphores`: 0 bedeutet sofortige Zustandsprüfung ohne Warten, `UINT64_MAX` bedeutet unbegrenzt, alle anderen Werte sind Nanosekunden ab Übernahme des Requests zur Ausführung. Scheduler-Verzögerungen dürfen die Frist nicht neu starten; eine Antwort kann nach Fristablauf eintreffen. Wenn Fence-Zustand und Fristablauf konkurrieren, gewinnt `SUCCESS` beziehungsweise `EXECUTION_FAILED`, falls der Fence bei der abschließenden Zustandsprüfung bereits terminal ist; andernfalls wird `TIMEOUT` zurückgegeben. Bei Device Loss wird `DEVICE_LOST` zurückgegeben. Wird `DestroyDevice` verarbeitet, solange dieser Wait noch offen ist, wird `DEVICE_DESTROYED` zurückgegeben. Ein Timeout verändert den Fence-Zustand nicht.

## `ResetFence`

Request: exakt 16 Bytes; Device-XID bei Offset 8, Fence-XID bei Offset 12. Eine andere Gesamtlänge ergibt `BadLength`. Unbekannte/nicht-live Device- oder Fence-XIDs ergeben `BadValue`; falscher live Ressourcentyp, fremde Client-/Device-Ownership oder Cross-Device-Verwendung ergeben `BadMatch`. Bei verlorenem Device wird `DEVICE_LOST` zurückgegeben.

Nur `SIGNALED` und `FAILED` dürfen zurückgesetzt werden. Ein Reset aus `PENDING` oder `UNSIGNALED` ergibt `INVALID_SYNCHRONIZATION_STATE`. Unbekannte/nicht-live Device- oder Fence-XIDs ergeben `BadValue`; falscher live Ressourcentyp oder fremde Client-/Device-Ownership ergibt `BadMatch`. Bei verlorenem Device wird `DEVICE_LOST` zurückgegeben. Eine Ablehnung lässt den Fence-Zustand unverändert.

## Destroying Fences

`DestroyFence` ist ein Void-Request mit fester Gesamtlänge von 16 Bytes: Device-XID bei Offset 8 und Fence-XID bei Offset 12.

Eine Fence darf nur zerstört werden, wenn sie nicht `PENDING` ist und keine offene `WaitForFence`-Registrierung mehr auf genau diese interne Fence-Identität wartet. Solange ein solcher Host-Wait offen ist, wird `DestroyFence` mit `INVALID_SYNCHRONIZATION_STATE` abgewiesen; XID und Fence-Zustand bleiben unverändert. Ein Wait gilt nicht mehr als offen, sobald sein terminales Ergebnis (Erfüllung, Timeout, Device Loss oder `DestroyDevice`) serverseitig serialisiert festgestellt wurde; dass der Reply noch im Ausgabepuffer wartet, verhindert die Zerstörung nicht. Nach erfolgreicher Zerstörung wird die öffentliche XID sofort ungültig; interne Daten dürfen bis zum Ende noch möglicher Serverzugriffe erhalten bleiben. Eine Fence im Zustand `FAILED` darf zerstört werden, sofern kein offener Host-Wait auf sie registriert ist.

Bei Device Loss werden Fences aus nicht-terminalen Submissions nach `FAILED` überführt. Fences, die keiner betroffenen nicht-terminalen Submission zugeordnet sind, behalten ihren letzten normativen Zustand; insbesondere wird ein nicht eingereichter Fence nicht künstlich als fehlgeschlagen markiert. `GetFenceStatus` bleibt nach Device Loss als reine Zustandsabfrage zulässig und liefert den gespeicherten Zustand (`FAILED` für die von Device Loss fehlgeschlagenen Submissions). `WaitForFence` liefert dagegen `DEVICE_LOST`, sobald das Device als verloren erkannt wurde, auch wenn der Fence bereits `FAILED` ist; dadurch wird kein blockierender Wait auf einem verlorenen Device fortgesetzt. `ResetFence` und neue Arbeit bleiben mit `DEVICE_LOST` abgewiesen. Bei `ResetFence` wird nach Request-Länge und Device-/Fence-XID-, Typ-, Ownership- und Cross-Device-Prüfung der Device-Zustand vor dem Fence-Zustand geprüft: ein verlorenes Device ergibt daher `DEVICE_LOST`, auch wenn die Fence nicht `SIGNALED` oder `FAILED` ist. Fences im Zustand `FAILED` dürfen anschließend normal zerstört werden; die Device-weite Kaskadeninvalidierung bleibt unabhängig davon zulässig.

Nach Device Loss werden keine ausstehenden Semaphore-Signal-/Wait-Operationen weiter als erfolgreich behandelt. Timeline-Counter-Abfragen über `GetSemaphoreCounterValue`, Host-Signale über `SignalSemaphore` und neue `QueueSubmit`-Operationen schlagen mit `DEVICE_LOST` fehl. `WaitSemaphores` wird mit `DEVICE_LOST` beendet, statt weiter auf einen Counter zu warten oder `TIMEOUT` zurückzugeben. Wird `DestroyDevice` verarbeitet, solange ein `WaitSemaphores`-Request noch offen ist, wird dieser mit dem X11-Fehler `DEVICE_DESTROYED` beendet. Ein Semaphore-Zustand oder Counter darf nicht als erfolgreich fortgeschritten ausgegeben werden, nur weil eine Submission nach Device Loss intern terminalisiert wurde. Die Semaphore- und Fence-Objekte bleiben intern erhalten, solange Backend-Zugriffe oder serverseitige Operationen noch darauf verweisen; öffentliche XIDs dürfen bei der Device-weiten Kaskadeninvalidierung sofort ungültig werden.
