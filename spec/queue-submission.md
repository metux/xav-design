# Queue Submission und Synchronisation

## Queue-Adressierung

Queues werden durch Device-XID, Queue-Family-Index und Queue-Index adressiert. Der Server muss prüfen, ob die Queue für dieses logische Device tatsächlich erstellt wurde.

## `QueueSubmit`

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

## Semaphoren erstellen

`CreateSemaphore` hat 28 Bytes:

- Offset 8: Device-XID
- Offset 12: Semaphore-XID
- Offset 16: `CARD32 semaphore_type`
- Offset 20: `CARD64 initial_value`

Typen:

- `BINARY = 0`
- `TIMELINE = 1`

Für Binary-Semaphoren muss `initial_value = 0` sein. Binary-Semaphoren beginnen unsignaled.

## Binary-Semaphoren

Binary-Semaphoren folgen den Vulkan-Signal-/Wait-Regeln.

- Ein Signal darf nicht mehrere konkurrierende Waits erfüllen.
- Host-Counter-Abfragen, Host-Waits und Host-Signals sind für Binary-Semaphoren ungültig.
- Pending Signal-/Wait-Zustände müssen atomar validiert werden.
- Ein Signal und ein Wait müssen nach den geltenden Vulkan-Regeln zusammenpassen.

Die vollständigen Regeln für noch ausstehende Signal-/Wait-Operationen sind noch zu präzisieren.

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

Request: 24 Bytes.

- Offset 8: Device-XID
- Offset 12: Semaphore-XID
- Offset 16: `CARD64 signal_value`

Nur Timeline-Semaphoren sind erlaubt. Der Signalwert muss größer als der aktuelle Wert und mit allen ausstehenden Signalen konsistent sein. Prüfung und Signaloperation sind atomar.

# Ordering- und Synchronisationsgarantien

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
