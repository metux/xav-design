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

Für Binary-Semaphoren muss `initial_value = 0` sein. Binary-Semaphoren beginnen unsignaled. In `QueueSubmit` müssen die `wait_value`- und `signal_value`-Felder für Binary-Semaphoren ebenfalls null sein. Unbekannte/nicht-live Device-XIDs ergeben `BadValue`; ein falscher live Ressourcentyp oder fremde Device-Ownership ergibt `BadMatch`. Bei einem nicht verfügbaren oder verlorenen logischen Device wird `DEVICE_UNAVAILABLE` beziehungsweise `DEVICE_LOST` gemeldet. Backend-Allokationsfehler ergeben `ALLOCATION_FAILED`. Die Erstellung ist atomar: bei jedem Fehler bleibt die Semaphore-XID unangelegt.

## Binary-Semaphoren

Binary-Semaphoren folgen den Vulkan-Signal-/Wait-Regeln.

- Ein Signal darf nicht mehrere konkurrierende Waits erfüllen.
- Host-Counter-Abfragen, Host-Waits und Host-Signals sind für Binary-Semaphoren ungültig.
- Pending Signal-/Wait-Zustände müssen atomar validiert werden.
- Ein Signal und ein Wait müssen nach den geltenden Vulkan-Regeln zusammenpassen.

In v0.1 darf für eine Binary-Semaphore höchstens eine Signaloperation und höchstens eine Wait-Operation gleichzeitig pending sein. Ein einzelner pending Wait darf auf ein Signal warten, das noch nicht eingereiht wurde; ebenso darf ein Signal pending sein, bevor der passende Wait eingereiht wird. Der Server verfolgt dafür getrennt den Signalzustand (`UNSIGNALED`, `SIGNAL_PENDING`, `SIGNALED` oder `UNTRUSTED`) und die Referenzen auf angenommene Wait-/Signaloperationen. `UNTRUSTED` bedeutet, dass der Server den Backend-Payload-Zustand nach einem fehlgeschlagenen Vorgang nicht sicher bestimmen kann; dieser Zustand ist nicht gleichbedeutend mit `UNSIGNALED`. Die Annahme eines Waits konsumiert das Signal nicht sofort: konsumiert wird es erst, wenn der Wait auf GPU-/Backend-Seite erfolgreich erfüllt ist. Erst nach dieser Konsumption darf ein neuer Signalzyklus beginnen; eine bloß angenommene oder noch pending Wait-Operation gibt das Signal nicht frei. Ein Signal, dessen Operation erfolgreich abgeschlossen wurde, bleibt verfügbar, bis genau ein Wait es konsumiert. Eine zweite Signaloperation wird abgewiesen, solange ein Signal bereits verfügbar ist oder eine Signaloperation pending ist; eine zweite pending Wait-Operation wird abgewiesen, solange ein vorheriger Wait noch nicht erfüllt/abgeschlossen ist. Solche Ablehnungen bei `QueueSubmit` erfolgen atomar mit `INVALID_SYNCHRONIZATION_STATE`. Ein Fehler oder Device Loss darf ein Signal nicht als erfolgreich verfügbar oder konsumiert markieren, wenn das nicht tatsächlich eingetreten ist; beim Device Loss werden betroffene Submissions fehlgeschlagen und das Semaphore-Objekt folgt den Device-Loss-Regeln. Kann der Server nach einem angenommenen, fehlgeschlagenen Backend-Vorgang nicht sicher nachweisen, ob eine Binary-Semaphore-Signal- oder Wait-Operation wirksam wurde, muss er die Binary-Semaphore als `UNTRUSTED` markieren. Dieser Zustand ist terminal für normale Nutzung: weitere Queue-Waits und Queue-Signals auf dieser Semaphore werden vor Annahme mit `DEPENDENCY_FAILED` abgewiesen. Der Server darf die Semaphore nicht als signalverfügbar oder unsignaled behandeln und darf sie nicht durch einen lokalen Zustandsreset wieder nutzbar machen. Die öffentliche Semaphore-XID bleibt bis zu ihrer zulässigen Zerstörung live; interne Backend-Referenzen bleiben bis zur Quieszenz erhalten. Ist dagegen nachweisbar, dass die fehlgeschlagene Operation das Semaphore-Payload nicht verändert hat, bleibt der vorherige bestätigte Signalzustand erhalten. Device Loss folgt weiterhin den strengeren Device-weiten Regeln.

## Timeline-Semaphoren

Timeline-Semaphoren besitzen einen monoton steigenden unsigned 64-bit Counter.

- Ein Wait ist erfüllt, sobald der beobachtbare Counter mindestens den angeforderten Wert erreicht.
- Ein Wait darf eingereiht werden, bevor das Signal eingereiht wurde, das ihn erfüllt.
- Signalwerte müssen größer als der aktuelle Counter und mit allen Pending-Signalen konsistent sein. Zur atomaren Validierung zählt ein angenommenes, noch nicht terminales Signal als pending, auch wenn sein Counter-Wert noch nicht erreicht ist; neue GPU-Signalwerte müssen größer als alle bereits reservierten pending Signalwerte derselben Semaphore sein. Ein pending GPU-Signal reserviert seinen Wert, erhöht aber den beobachtbaren Counter nicht.
- Der beobachtbare Counter steigt erst, wenn die jeweilige Signaloperation tatsächlich erfolgreich ausgeführt wurde. Die bloße Annahme einer `QueueSubmit`-Anforderung reserviert den Signalwert, erhöht aber nicht vorzeitig den Counter.
- Ein erfolgreich ausgeführtes Signal erfüllt alle bereits eingereihten Waits, deren Werte dadurch erreicht werden; ein Wait verändert den Counter nicht.
- Mehrere Signal-Entries derselben Timeline-Semaphore in einem einzelnen `QueueSubmit` sind in v0.1 nicht erlaubt.
- Nach fehlgeschlagener Submission oder Device Loss darf ein nur reservierter, aber nicht erfolgreich signalisierter Wert nicht als erreicht ausgegeben werden. Reservierungen werden erst aufgehoben, wenn die zugehörige Operation terminal ist; bei Device Loss gelten keine weiteren normalen Signaloperationen für das Device.

## `GetSemaphoreCounterValue`

Request: exakt 16 Bytes; Device-XID bei Offset 8, Semaphore-XID bei Offset 12. Eine andere Gesamtlänge ergibt `BadLength`. Unbekannte/nicht-live Device- oder Semaphore-XIDs ergeben `BadValue`; falscher live Ressourcentyp, fremde Client-/Device-Ownership oder Cross-Device-Verwendung ergeben `BadMatch`.

Nur für Timeline-Semaphoren. Bei einem bereits als verloren erkannten logischen Device wird der Request mit `DEVICE_LOST` abgewiesen: Das Wire-Reply besitzt kein Statusfeld, mit dem ein Fehler sicher von einem Counter-Wert unterschieden werden könnte. Der Server darf keinen vermeintlich aktuellen Counter als erfolgreichen Reply ausgeben.

Reply:

- Offset 8: `CARD64 counter_value`
- Offset 16–31: reserviert, null
- Reply-Payload-Länge: null

## `WaitSemaphores`

Fester Request-Header: 28 Bytes; Gesamtlänge: `28 + 12 * semaphore_count` Bytes.

- Offset 8: Device-XID
- Offset 12: `CARD32 semaphore_count`
- Offset 16: `CARD32 wait_mode`
- Offset 20: `CARD64 timeout_ns`
- Offset 28: Array aus 12-Byte-Entries

Jeder Entry enthält Semaphore-XID und `CARD64 wait_value`.

Wait-Modi:

- `WAIT_ANY = 0`
- `WAIT_ALL = 1`

Die Request-Länge muss exakt `28 + 12 * semaphore_count` Bytes betragen; eine Längenabweichung oder ein arithmetischer Überlauf ergibt `BadLength`. `semaphore_count = 0` ergibt `BadValue`. Unbekannte/nicht-live Device- oder Semaphore-XIDs ergeben `BadValue`; ein falscher live Ressourcentyp, fremde Client-/Device-Ownership oder Cross-Device-Verwendung ergibt `BadMatch`. Alle Semaphoren müssen Timeline-Semaphoren desselben Devices sein; doppelte XIDs und ungültige `wait_mode`-Werte ergeben `BadValue`. Diese Prüfungen erfolgen vor Registrierung des Waits. Bei Device Loss wird der Wait mit `DEVICE_LOST` als X11-Fehler beendet; wird `DestroyDevice` verarbeitet, solange der Wait noch offen ist, ergibt sich `DEVICE_DESTROYED`.

### Timeout-Semantik

Für `timeout_ns` gilt:

- `0`: nicht blockierend; der Server prüft den Zustand einmal und antwortet sofort.
- `UINT64_MAX`: unbegrenzt warten, bis die Bedingung erfüllt ist oder das Device verloren geht.
- Jeder andere Wert: Timeout in Nanosekunden, gemessen mit einer monotonen, nicht durch Systemzeitkorrekturen verstellten Uhr. Die Frist beginnt, sobald der Server diesen Request zur Ausführung übernimmt.

Der Server darf eine endliche Wartefrist intern in mehrere Warteabschnitte aufteilen, muss aber die ursprüngliche Frist beibehalten. Scheduler-Verzögerungen dürfen die Frist nicht absichtlich neu starten. Ist die Bedingung bei der abschließenden Zustandsprüfung erfüllt, wird `SUCCESS` zurückgegeben; andernfalls nach Ablauf der Frist `TIMEOUT`. Der Server muss keine Antwort exakt am Nanosekunden-Grenzpunkt liefern; die tatsächliche Antwort darf durch Scheduling verzögert eintreffen.

Ein offener Wait hat genau einen terminalen Ausgang. Der Server serialisiert die Feststellung von erfüllter Bedingung, Timeout, Device Loss und `DestroyDevice` mit den zugehörigen Zustandsübergängen: Der zuerst festgestellte terminale Ausgang gewinnt und darf nicht nachträglich überschrieben werden. Eine bereits festgestellte erfüllte Bedingung behält `SUCCESS`; ein zuerst festgestellter Device Loss beendet den Wait als `DEVICE_LOST`; wird `DestroyDevice` verarbeitet, solange der Wait noch offen ist und Device Loss nicht bereits festgestellt wurde, beendet `DEVICE_DESTROYED` den Wait. Bei Client-Disconnect wird die serverseitige Wait-Registrierung ohne Reply abgebrochen.

`WaitSemaphores` darf den X11-Request-Dispatcher nicht synchron blockieren. Der Server registriert die Wartebedingung und stellt den Reply später bereit, während er nachfolgende Requests derselben Verbindung weiterverarbeiten kann. Das ist notwendig, damit ein späteres `SignalSemaphore` oder `QueueSubmit` den erwarteten Wert liefern kann. Der Wait-Request selbst ordnet keine nachfolgenden GPU-Submissions und hält sie nicht zurück. Die Timeout-Frist beginnt bei der Übernahme des Wait-Requests und läuft auch dann weiter, wenn nachfolgende Requests verarbeitet werden.

Der Reply ist genau 32 Bytes lang. Offset 8 enthält einen `CARD32 status` mit `SUCCESS = 0` oder `TIMEOUT = 1`; Offsets 12–31 sind null und `reply.length = 0`. Ein Timeout ist ein normaler Reply und kein X11-Fehler. Ein Timeout verändert weder Semaphore-Counter noch Queue-, Fence- oder Semaphore-Zustände. Ein durch Device Loss unmöglich gewordener Wait wird mit `DEVICE_LOST` als normalem X11-Fehler beendet, nicht als `TIMEOUT` maskiert.

## `SignalSemaphore`

Request: 24 Bytes; Void-Request ohne Reply.

- Offset 8: Device-XID
- Offset 12: Semaphore-XID
- Offset 16: `CARD64 signal_value`

Die Gesamtlänge muss exakt 24 Bytes betragen, andernfalls `BadLength`. Unbekannte/nicht-live Device- oder Semaphore-XIDs ergeben `BadValue`; ein falscher live Ressourcentyp, fremde Client-/Device-Ownership oder Cross-Device-Verwendung ergibt `BadMatch`. Ein nicht verfügbares oder verlorenes Device wird vor Ausführung mit `DEVICE_UNAVAILABLE` beziehungsweise `DEVICE_LOST` abgewiesen. Erst nach diesen Prüfungen wird der Semaphore-Typ und der Signalwert validiert.

Nur Timeline-Semaphoren sind erlaubt. Der Signalwert muss größer als der aktuelle Counter sein. Zusätzlich muss er kleiner als jeder bereits reservierte, noch nicht terminale GPU-Signalwert derselben Semaphore sein; andernfalls wird der Request mit `INVALID_SYNCHRONIZATION_STATE` abgewiesen. Damit kann ein Host-Signal einen niedrigeren Wert liefern, der eine wartende Submission freigibt, ohne über eine niedrigere GPU-Reservierung hinwegzuspringen. Bei fehlenden GPU-Reservierungen ist jeder Wert größer als der aktuelle Counter zulässig. Validierung und Host-Signaloperation bilden eine atomare Request-Operation. Der Server prüft den aktuellen Counter und sämtliche Reservierungen atomar mit der Ausführung des Signals.

Der Server führt das Host-Signal aus, bevor er mit der regulären Verarbeitung des nächsten Requests derselben X11-Verbindung fortfährt. Ausnahme: Während ein früherer `WriteBuffer`-Request auf vorherige Submissions wartet, darf der Server einen späteren `SignalSemaphore`-Request vor Abschluss dieses `WriteBuffer` ausführen, sofern dies erforderlich ist, um die vorherigen Submissions fortschreiten zu lassen. Das Signal muss dabei weiterhin vollständig validiert und atomar ausgeführt werden. Spätere `QueueSubmit`-Requests bleiben bis zum Abschluss des `WriteBuffer` zurückgestellt und dürfen dessen Ordnungsgrenze nicht passieren. Sobald die Signaloperation erfolgreich ausgeführt ist, ist der Counter aktualisiert und jeder dadurch erfüllte Wait darf fortschreiten. Der Server darf den Signal-Request nicht als abgeschlossen behandeln, solange das Host-Signal nicht erfolgreich ausgeführt wurde.

Validierungsfehler und unmittelbar feststellbare Vulkan-Fehler werden als normale X11-Request-Fehler gemeldet; der Request hinterlässt dann keine teilweise ausgeführte Signaloperation. Ein nach Annahme der Operation auftretender Device Loss wird über die normalen Device-Loss-/asynchronen Fehlermechanismen gemeldet. Da der Request kein Reply erzeugt, kann der Client Fehler mit der üblichen X11-Fehlerbehandlung beziehungsweise `XSync` erkennen. Ein späterer Request derselben Verbindung darf nicht vor Abschluss der Host-Signaloperation ausgeführt werden.

## Semaphore-Zerstörung

`DestroySemaphore` ist ein Void-Request mit fester Gesamtlänge von 16 Bytes: Device-XID bei Offset 8 und Semaphore-XID bei Offset 12. `DestroySemaphore` verwendet die allgemeinen Lebensdauerregeln aus [Resource lifetime and ownership](resource-lifetime.md). Die Zerstörung wird mit `INVALID_SYNCHRONIZATION_STATE` abgewiesen, solange ein angenommener Queue-Wait, ein Queue-Signal oder eine offene `WaitSemaphores`-Registrierung die exakte interne Semaphore-Identität referenziert oder eine andere laufende serverseitige Host-Operation die Semaphore verwendet. Eine Ablehnung ändert weder XID noch Synchronisationszustand. Eine Wait-Registrierung gilt nicht mehr als offen, sobald ihr terminales Ergebnis serverseitig serialisiert festgestellt wurde; ein noch nicht versendeter Reply blockiert die Zerstörung dann nicht. Nach erfolgreicher Zerstörung wird die öffentliche XID sofort ungültig; interne Daten bleiben erhalten, solange Backend-Zugriffe möglich sind. Bei Device Loss darf die Device-weite Kaskadeninvalidierung diese normale Ablehnung umgehen.

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

Unbekannte/nicht-live Device-XIDs ergeben `BadValue`; ein falscher live Ressourcentyp oder fremde Device-Ownership ergibt `BadMatch`. Bei einem nicht verfügbaren oder verlorenen logischen Device wird `DEVICE_UNAVAILABLE` beziehungsweise `DEVICE_LOST` gemeldet. Backend-Allokationsfehler ergeben `ALLOCATION_FAILED`. Die Erstellung ist atomar: bei jedem Fehler bleibt die Fence-XID unangelegt.

## `GetFenceStatus`

Request: exakt 16 Bytes; Device-XID bei Offset 8, Fence-XID bei Offset 12. Andere Längen ergeben `BadLength`. Unbekannte/nicht-live Device- oder Fence-XIDs ergeben `BadValue`; falscher live Ressourcentyp, fremde Client-/Device-Ownership oder Cross-Device-Verwendung ergeben `BadMatch`. Die Abfrage gibt den serverseitig gespeicherten Fence-Zustand zurück, auch nach Device Loss.

Reply: 32 Bytes.

- Byte 0: standardmäßiges X11-Reply-`response_type`
- Byte 1: Fence-Status (`UNSIGNALED = 0`, `PENDING = 1`, `SIGNALED = 2`, `FAILED = 3`)
- Offsets 2–3: standardmäßige X11-Reply-Sequenznummer
- Offsets 4–7: standardmäßiges `reply.length = 0`
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

## Fence-Zerstörung

`DestroyFence` ist ein Void-Request mit fester Gesamtlänge von 16 Bytes: Device-XID bei Offset 8 und Fence-XID bei Offset 12.

Eine Fence darf nur zerstört werden, wenn sie nicht `PENDING` ist und keine offene `WaitForFence`-Registrierung mehr auf genau diese interne Fence-Identität wartet. Solange ein solcher Host-Wait offen ist, wird `DestroyFence` mit `INVALID_SYNCHRONIZATION_STATE` abgewiesen; XID und Fence-Zustand bleiben unverändert. Ein Wait gilt nicht mehr als offen, sobald sein terminales Ergebnis (Erfüllung, Timeout, Device Loss oder `DestroyDevice`) serverseitig serialisiert festgestellt wurde; dass der Reply noch im Ausgabepuffer wartet, verhindert die Zerstörung nicht. Nach erfolgreicher Zerstörung wird die öffentliche XID sofort ungültig; interne Daten dürfen bis zum Ende noch möglicher Serverzugriffe erhalten bleiben. Eine Fence im Zustand `FAILED` darf zerstört werden, sofern kein offener Host-Wait auf sie registriert ist.

Bei Device Loss werden Fences aus nicht-terminalen Submissions nach `FAILED` überführt. Fences, die keiner betroffenen nicht-terminalen Submission zugeordnet sind, behalten ihren letzten normativen Zustand; insbesondere wird ein nicht eingereichter Fence nicht künstlich als fehlgeschlagen markiert. `GetFenceStatus` bleibt nach Device Loss als reine Zustandsabfrage zulässig und liefert den gespeicherten Zustand (`FAILED` für die von Device Loss fehlgeschlagenen Submissions). `WaitForFence` liefert dagegen `DEVICE_LOST`, sobald das Device als verloren erkannt wurde, auch wenn der Fence bereits `FAILED` ist; dadurch wird kein blockierender Wait auf einem verlorenen Device fortgesetzt. `ResetFence` und neue Arbeit bleiben mit `DEVICE_LOST` abgewiesen. Fences im Zustand `FAILED` dürfen anschließend normal zerstört werden; die Device-weite Kaskadeninvalidierung bleibt unabhängig davon zulässig.

Nach Device Loss werden keine ausstehenden Semaphore-Signal-/Wait-Operationen weiter als erfolgreich behandelt. Timeline-Counter-Abfragen über `GetSemaphoreCounterValue`, Host-Signale über `SignalSemaphore` und neue `QueueSubmit`-Operationen schlagen mit `DEVICE_LOST` fehl. `WaitSemaphores` wird mit `DEVICE_LOST` beendet, statt weiter auf einen Counter zu warten oder `TIMEOUT` zurückzugeben. Wird `DestroyDevice` verarbeitet, solange ein `WaitSemaphores`-Request noch offen ist, wird dieser mit dem X11-Fehler `DEVICE_DESTROYED` beendet. Ein Semaphore-Zustand oder Counter darf nicht als erfolgreich fortgeschritten ausgegeben werden, nur weil eine Submission nach Device Loss intern terminalisiert wurde. Die Semaphore- und Fence-Objekte bleiben intern erhalten, solange Backend-Zugriffe oder serverseitige Operationen noch darauf verweisen; öffentliche XIDs dürfen bei der Device-weiten Kaskadeninvalidierung sofort ungültig werden.
