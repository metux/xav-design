# Queue submission and ordering

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
| 32 | CARD64 | `submission_token` |
| 40 | variable | Command-Buffer-XIDs, Wait-Entries, Signal-Entries |

Jeder Wait-Entry ist 16 Bytes groß:

- Relativer Offset 0: Semaphore-XID
- Offset 4: `CARD64 wait_value`
- Offset 12: `CARD32 wait_stage_mask`

Für Binary-Semaphoren muss `wait_value = 0` sein. Für Timeline-Semaphoren ist `wait_value` der erforderliche Counter-Wert.

Jeder Signal-Entry ist 12 Bytes groß:

- Relativer Offset 0: Semaphore-XID
- Offset 4: `CARD64 signal_value`

Für Binary-Semaphoren muss `signal_value = 0` sein. Für Timeline-Semaphoren ist `signal_value` der zu signalisierende Counter-Wert.

Gesamtlänge:

`40 + 4*C + 16*W + 12*S`

`submission_token` wird vom Client vergeben und als undurchsichtiger 64-Bit-Wert behandelt. Er muss innerhalb derselben X11-Client-Verbindung für jede `QueueSubmit`-Anforderung eindeutig sein; Wiederverwendung ist auch nach Abschluss einer Submission nicht zulässig, solange die Verbindung besteht. Der Wert `0` ist reserviert und ungültig. Tokens müssen keiner Reihenfolge folgen und haben keine zeitliche oder numerische Bedeutung. Ein Zeitstempel oder Hash ist zulässig, sofern der Client die Eindeutigkeit tatsächlich sicherstellt.

Der Server übernimmt den Token unverändert in das zugehörige `SUBMISSION_COMPLETE`- oder `SUBMISSION_FAILED`-Event sowie in submissionbezogene `ASYNC_ERROR`-Events. Die X11-Event-Sequence-Number ist davon unabhängig und identifiziert nicht die Submission.

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

`QueueSubmit` ist ein Void-Request. Die Annahme oder Ablehnung wird synchron über die normalen X11-Fehlerregeln signalisiert; der Token dient ausschließlich der Korrelation späterer asynchroner Ergebnisse.

## Terminaler Submission-Zustand und Device Loss

Jede angenommene Submission hat genau einen terminalen Ausgang:

- `SUBMISSION_COMPLETE`: Alle Commands der Submission wurden erfolgreich abgeschlossen.
- `SUBMISSION_FAILED`: Die Submission wurde nicht erfolgreich abgeschlossen; das Event enthält den `submission_token` und einen Fehlerstatus.

Der Server erzeugt für jede angenommene Submission genau eines dieser terminalen Events. Die Zustellung richtet sich nach der XAverius-Event-Auswahl und ist nur möglich, solange die Client-Verbindung besteht. Ein `ASYNC_ERROR` kann zusätzliche Diagnoseinformationen liefern, ersetzt das terminale Submission-Event aber nicht und darf kein zweites terminales Event auslösen. Eine abgelehnte `QueueSubmit`-Anforderung wurde nicht angenommen und erzeugt kein terminales Submission-Event.

Tritt nach der Annahme ein Ausführungsfehler auf, schlägt die Submission fehl; sie gilt nicht als abgeschlossen. Ihre Fence wechselt gegebenenfalls nach `FAILED`. Jeder von dieser Submission verwendete Command Buffer wechselt nach Ende der Pending-Phase nach `INVALID`. Vor einer erneuten Verwendung muss er gemäß der Command-Buffer-API zurückgesetzt und neu aufgezeichnet werden. Der Server hält interne Referenzen, bis die Submission terminal ist und das Backend nicht mehr auf die Ressourcen zugreift.

Bei Device Loss schlagen alle angenommenen, noch nicht terminalen Submissions des betroffenen logischen Devices mit `DEVICE_LOST` fehl. Der Server darf keine erfolgreiche Completion vortäuschen und keine Fence für nicht erfolgreich abgeschlossene Arbeit auf `SIGNALED` setzen. Für jede angenommene Submission bleibt genau ein terminales Event vorgesehen, sofern die Client-Verbindung noch besteht. Weitere GPU-Arbeit auf dem verlorenen Device wird nicht ausgeführt. Requests, die nur den Status abfragen oder das logische Device bereinigen, dürfen nach ihren jeweiligen Regeln weiterlaufen; Operationen, die ein funktionsfähiges Device benötigen, schlagen mit `DEVICE_LOST` fehl.

## Semaphore references

The semaphore types and host-side semaphore operations used by `QueueSubmit` are specified in [Synchronization objects](synchronization.md). The `QueueSubmit` request retains its wait and signal arrays as described above.

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
