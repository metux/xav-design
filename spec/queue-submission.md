# Queue submission and ordering

## Queue-Adressierung

Queues werden durch Device-XID, Queue-Family-Index und Queue-Index adressiert. Der Server muss prüfen, ob die Queue für dieses logische Device tatsächlich erstellt wurde.

## `QueueSubmit`

Request-Layout:

| Offset | Type | Field |
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

Fehlerpräzedenz (erste zutreffende Phase gewinnt): (1) falsche Gesamtlänge, inkonsistente Counts, arithmetischer Überlauf oder abgeschnittene Einträge ergeben `BadLength`; (2) rein syntaktische Felder werden geprüft: `submission_token = 0`, ein bereits auf derselben Verbindung verwendeter Token, nicht-null reservierte Felder, Wait-Stage-Masken mit 0/reservierten Bits, doppelte rohe Semaphore-XIDs und ungültige Werte, die ohne Auflösung eines Ressourcentyps bestimmbar sind, ergeben `BadValue`; (3) erforderliche XIDs werden in Wire-Reihenfolge aufgelöst: Device, optionale Fence, Command-Buffer-XIDs in Array-Reihenfolge, Wait-Semaphore-XIDs in Array-Reihenfolge, Signal-Semaphore-XIDs in Array-Reihenfolge. Unbekannte/nicht-live XIDs ergeben `BadValue`; (4) erst danach werden Ressourcentyp, Client-/Device-Ownership und Queue-Zuordnung geprüft; falscher live Typ, fremde Ownership, Cross-Device-Zuordnung oder eine nicht für dieses Device erstellte Queue ergeben `BadMatch`; (5) nach erfolgreicher XID-/Typ-/Ownership-/Queue-Prüfung hat ein nicht verfügbares/verlorenes Device Vorrang vor veränderlichen Submit-Zuständen und ergibt `DEVICE_UNAVAILABLE`/`DEVICE_LOST`; (6) bei funktionsfähigem Device werden die veränderlichen Voraussetzungen in Wire-Reihenfolge geprüft: zuerst der Zustand der optionalen Fence, dann die Command Buffer in Array-Reihenfolge, danach die Wait-Entries in Array-Reihenfolge und zuletzt die Signal-Entries in Array-Reihenfolge. Innerhalb jedes Wait-/Signal-Entries werden zuerst typabhängige numerische Werte geprüft, danach Stage-Family-Kompatibilität (nur Wait-Entries) und anschließend die Zulässigkeit der jeweiligen Semaphore-Operation samt Pending-/Signalreservierungen. Unzulässige Fence-/Command-Buffer-/Semaphore-Zustände oder eine nicht unterstützte Stage ergeben `INVALID_SYNCHRONIZATION_STATE`; ungültige typabhängige numerische Werte ergeben `BadValue`. Insbesondere ist ein Timeline-Signalwert, der nicht größer als der beobachtbare Counter ist, `BadValue`; ein Wert, der zwar numerisch größer als der Counter, aber nicht größer als jede bereits reservierte pending GPU-Signalstufe ist, ergibt `INVALID_SYNCHRONIZATION_STATE`, wie bei `SignalSemaphore`. Eine sonstige Abhängigkeit, die die Annahme verhindert, ergibt `DEPENDENCY_FAILED`. Typabhängige Werte wie Binary-Wait-/Signalwerte werden erst nach Typauflösung geprüft. Innerhalb jeder Phase wird die im Request angegebene Feld-/Array-Reihenfolge eingehalten. Jeder synchron abgewiesene Request bleibt atomar und erzeugt kein Submission-Event. Nach Annahme gemeldete Ausführungsfehler sind keine X11-Fehler.

Der Server übernimmt den Token unverändert in das zugehörige `SUBMISSION_COMPLETE`- oder `SUBMISSION_FAILED`-Event sowie in submissionbezogene `ASYNC_ERROR`-Events. Die X11-Event-Sequence-Number ist davon unabhängig und identifiziert nicht die Submission.

### Wait-Stage-Maske

`wait_stage_mask` ist eine XAverius-eigene `CARD32`-Bitmaske; die Bits sind **nicht** die numerischen Vulkan-`VkPipelineStageFlags`-Werte. Die v0.1-Zuordnung ist festgelegt:

| XAverius-Bit | Maske | Vulkan-Stage |
|---|---:|---|
| `DRAW_INDIRECT` | `0x00000001` | `VK_PIPELINE_STAGE_DRAW_INDIRECT_BIT` |
| `COMPUTE_SHADER` | `0x00000002` | `VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT` |
| `TRANSFER` | `0x00000004` | `VK_PIPELINE_STAGE_TRANSFER_BIT` |
| `ALL_COMMANDS` | `0x00000008` | `VK_PIPELINE_STAGE_ALL_COMMANDS_BIT` |

Bits 4–31 sind reserviert und müssen null sein. Die Maske muss mindestens ein Bit setzen. `ALL_COMMANDS` darf wie in Vulkan mit anderen unterstützten Bits kombiniert werden; solche Kombinationen sind semantisch redundant, aber gültig. XAverius übersetzt jedes gesetzte Bit explizit in den entsprechenden Vulkan-Wert und verknüpft die Vulkan-Bits per bitwise OR; die XAverius-Maske darf nicht unverändert als Vulkan-Maske durchgereicht werden.

Die gesetzten Stages müssen auf der adressierten Queue-Family unterstützt sein, entsprechend Vulkan-Synchronisationsregeln:

- `DRAW_INDIRECT`: Queue-Family mit `GRAPHICS` oder `COMPUTE`.
- `COMPUTE_SHADER`: Queue-Family mit `COMPUTE`.
- `TRANSFER`: Queue-Family mit `GRAPHICS`, `COMPUTE` oder `TRANSFER`.
- `ALL_COMMANDS`: auf jeder Queue-Family zulässig, die für das logische Device erstellt wurde.

Eine Maske mit unbekannten/reservierten Bits oder ohne gesetztes Bit ist syntaktisch ungültig und ergibt `BadValue`. Eine syntaktisch gültige Maske, deren Stage nicht von der adressierten Queue-Family unterstützt wird, ergibt `INVALID_SYNCHRONIZATION_STATE`. Diese Prüfung erfolgt vor Annahme; ein Fehler lässt Submission, Fence und Semaphore-Zustände unverändert.

Für den Compute-only-Referenzablauf sind `COMPUTE_SHADER`, `TRANSFER` und `ALL_COMMANDS` gültige Einzelmasken auf einer Compute-fähigen Queue. `DRAW_INDIRECT` ist ebenfalls stage-seitig auf einer Compute-Queue zulässig, auch wenn der v0.1-Command-Stream keine indirekten Dispatch-Commands definiert. Der Wait wird am gewählten Vulkan-Ziel-Stage wirksam; er ist keine allgemeine Ersetzung für notwendige Memory-Dependencies zwischen Commands.

Vor der Annahme werden alle Command Buffer und Synchronisationsobjekte geprüft. Alle Ressourcen müssen zum angegebenen Device gehören. Jeder Command Buffer muss ausführbar sein. Eine angegebene Fence muss `UNSIGNALED` sein und darf nicht bereits pending sein.

Doppelte Wait- oder Signal-Einträge sind in v0.1 ungültig und ergeben `BadValue`. Dieselbe Semaphore darf in einer Submission nicht gleichzeitig im Wait- und Signal-Array stehen; auch dieser Konflikt ergibt `BadValue`.

**Atomaritätsgarantie:** Wird der Request abgelehnt, wird keine Submission angelegt und kein Synchronisationszustand verändert. Bei Annahme bedeutet der Request nur, dass die Arbeit eingereiht wurde; nicht, dass sie bereits abgeschlossen ist.

`QueueSubmit` ist ein Void-Request. Die Annahme oder Ablehnung wird synchron über die normalen X11-Fehlerregeln signalisiert; der Token dient ausschließlich der Korrelation späterer asynchroner Ergebnisse.


### Validation und atomare Annahme

Die Validierung ist zweiphasig. Zuerst prüft der Server Request-Framing und Längen/Counts, reservierte Felder und Token-Syntax, danach löst er Ressourcen in der definierten Feldreihenfolge auf und prüft Typ, Client-/Device-Ownership sowie Queue-Zuordnung. Anschließend prüft er den Device-Zustand und sämtliche veränderlichen Submit-Voraussetzungen: jeder Command Buffer muss `EXECUTABLE`, nicht `PENDING` oder `INVALID`, sein; Fence und Semaphore müssen submitbar sein; Wait-Stages, Semaphore-Typen/-Werte, Timeline-Signalreservierungen und alle sonstigen Abhängigkeiten müssen gültig sein. Die allgemeine XID-Fehlerpräzedenz und die request-spezifische Reihenfolge gelten auch bei mehreren fehlerhaften Feldern; eine Implementierung darf nicht vorzeitig Zustand reservieren, nur weil sie einen früheren Eintrag bereits validiert hat.

Erst wenn alle Prüfungen erfolgreich sind, nimmt der Server die Submission als eine einzige serialisierte Transaktion an. In diesem Commit-Punkt werden der `submission_token` als verwendet registriert, die Submission angelegt, die Command Buffer auf `PENDING` gesetzt, Fence und Semaphore-Zuordnungen/Wait-/Signal-Slots reserviert und sämtliche internen Ressourcenreferenzen festgehalten. Kein sichtbarer Teil dieses Commit-Punkts darf für andere Requests oder asynchrone Backend-Callbacks als angenommen gelten, bevor der ganze Commit abgeschlossen ist.

Jede Ablehnung vor diesem Commit-Punkt ist vollständig nicht-mutierend: der Token bleibt unbenutzt und darf in einem korrigierten Request wiederverwendet werden; kein Command Buffer verlässt `EXECUTABLE`; keine Fence wechselt ihren Zustand oder wird einer Submission zugeordnet; Semaphore-Counter, Signalverfügbarkeit, Pending-Slots und Timeline-Reservierungen bleiben unverändert; es entstehen keine Submission-Objekte, internen Submission-Referenzen oder Submission-Events. Das gilt auch dann, wenn mehrere Command Buffer oder Synchronisationsobjekte bereits einzeln validiert wurden, bevor ein späterer Eintrag fehlschlägt. Ein synchroner Fehler darf kein `ASYNC_ERROR` für eine nicht angenommene Submission erzeugen.

Die `EXECUTABLE`-zu-`PENDING`-Übergänge und die Synchronisationsreservierungen sind somit ein gemeinsamer Commit, nicht voneinander getrennte schrittweise Änderungen. Nach diesem Commit ist die Submission angenommen; spätere Backend-Fehler werden ausschließlich über den terminalen Submission-Ausgang und die definierten Synchronisationszustände verarbeitet.
## Terminaler Submission-Zustand und Device Loss

Jede angenommene Submission hat genau einen terminalen Ausgang:

- `SUBMISSION_COMPLETE`: Alle Commands der Submission wurden erfolgreich abgeschlossen.
- `SUBMISSION_FAILED`: Die Submission wurde nicht erfolgreich abgeschlossen; das Event enthält den `submission_token` und einen Fehlerstatus.

Jede angenommene Submission erhält intern genau einen terminalen Ausgang. Ist das passende Completion- oder Failure-Event für die Queue ausgewählt und die Client-Verbindung noch aktiv, liefert der Server genau das dazugehörige Event aus, sofern die Event-Zustellung nicht durch eine bereits verarbeitete `DestroyDevice`-Anforderung gemäß [Resource lifetime and ownership](resource-lifetime.md) unterdrückt ist. Ohne passende Event-Auswahl oder bei solcher Lifecycle-Unterdrückung wird kein solches Event an den Client zugestellt; der terminale interne Zustand bleibt davon unberührt. Ein `ASYNC_ERROR` kann zusätzliche Diagnoseinformationen liefern, ersetzt den terminalen Ausgang nicht und darf keinen zweiten terminalen Ausgang erzeugen. Eine abgelehnte `QueueSubmit`-Anforderung wurde nicht angenommen und erhält keinen terminalen Ausgang.

Tritt nach der Annahme ein Ausführungsfehler auf, schlägt die Submission fehl; sie gilt nicht als abgeschlossen. Ihre Fence wechselt gegebenenfalls nach `FAILED`. Jeder von dieser Submission verwendete Command Buffer wechselt nach Ende der Pending-Phase nach `INVALID`. Vor einer erneuten Verwendung muss er gemäß der Command-Buffer-API zurückgesetzt und neu aufgezeichnet werden. Der Server hält interne Referenzen, bis die Submission terminal ist und das Backend nicht mehr auf die Ressourcen zugreift.

Bei Device Loss schlagen alle angenommenen, noch nicht terminalen Submissions des betroffenen logischen Devices mit `DEVICE_LOST` fehl. Der Server darf keine erfolgreiche Completion vortäuschen und keine Fence für nicht erfolgreich abgeschlossene Arbeit auf `SIGNALED` setzen. Für jede angenommene Submission bleibt genau ein terminales Event vorgesehen, sofern die Client-Verbindung noch besteht und die Event-Zustellung nicht durch die Lifecycle-Regeln für `DestroyDevice` unterdrückt ist. Weitere GPU-Arbeit auf dem verlorenen Device wird nicht ausgeführt. Requests, die nur den Status abfragen oder das logische Device bereinigen, dürfen nach ihren jeweiligen Regeln weiterlaufen; Operationen, die ein funktionsfähiges Device benötigen, schlagen mit `DEVICE_LOST` fehl.

**Atomarer Terminal-Übergang:** Der Wechsel einer angenommenen Submission von nicht-terminal zu genau einem terminalen Ergebnis (`COMPLETE` oder `FAILED`) ist ein einmaliger, serialisierter Zustandsübergang. Erfolgs-Callbacks, Fehler-Callbacks und Device-Loss-Verarbeitung konkurrieren um denselben Übergang; der erste vom Server serialisiert festgestellte gültige Ausgang gewinnt. Ein Device-Loss-Übergang muss alle zu diesem Zeitpunkt noch nicht-terminalen Submissions auf `FAILED/DEVICE_LOST` setzen, bevor spätere Backend-Callbacks für diese Submissions verarbeitet werden können. Ein Callback, der nach einem bereits festgestellten terminalen Zustand eintrifft, darf weder das Ergebnis, Fence-/Semaphore-Zustände noch Event-Entscheidungen verändern. Falls eine erfolgreiche Completion bereits vorher terminalisiert wurde, kann ein später erkannter Device Loss sie nicht rückwirkend in einen Fehler umwandeln; falls Device Loss zuerst terminalisiert wurde, darf ein späterer Erfolg weder `SIGNALED` setzen noch den Timeline-Counter erhöhen oder ein Signal als erfolgreich verbraucht markieren.

Die Finalisierung verwaltet alle Ressourcen der Submission als eine einzige idempotente Finalisierungsoperation: Jede Wait-/Signal-Reservierung, Fence-Zuordnung, Pending-Referenz und Pending-Markierung des Command Buffers wird höchstens einmal freigegeben beziehungsweise abgeschlossen. Die logische Terminalisierung darf nicht auf Backend-Quieszenz warten; Referenzen und Speicher, auf die das Backend noch zugreifen könnte, bleiben davon getrennt bis zum nachweislichen Ende dieser Zugriffe erhalten oder werden gemäß den Device-Loss-Regeln quarantänisiert. Event-Zustellung ist ein nachgelagerter Effekt der terminalen Entscheidung und kann diese weder zurückrollen noch wiederholen.

## Semaphore references

The semaphore types and host-side semaphore operations used by `QueueSubmit` are specified in [Synchronization objects](synchronization.md). The `QueueSubmit` request retains its wait and signal arrays as described above.

For an accepted submission, all semaphore wait/signal reservations and internal references are committed atomically with submission acceptance. A rejected request leaves the semaphore counters, binary signal availability, pending-operation slots, and internal references unchanged. Each accepted wait/signal entry retains the exact internal semaphore identity, not just its numeric XID, until that operation has reached its actual terminal outcome and the backend can no longer access the semaphore. A public XID becoming invalid cannot redirect an already accepted operation to a later resource that reuses the same XID.

A successful wait releases its pending-wait slot only after the wait has actually been satisfied. A successful signal releases its pending-signal slot only after its signal operation has actually completed; for a binary semaphore the signal then remains available until consumed by one successful wait. For a timeline semaphore, the successful signal updates the observable counter and removes its pending-value reservation. If a submission fails before an operation succeeds, the server must not fabricate a successful signal or wait consumption; it releases only reservations whose operation is known to be terminal, and applies the device-loss quarantine rules if backend quiescence cannot be established. Device loss fails all affected non-terminal submissions and prohibits new work on that device; it does not imply that backend references can be freed immediately.

# Queue-Reihenfolge und queueübergreifende Abhängigkeiten

Die folgenden Regeln gelten für angenommene Submissions desselben logischen Devices:

- **Dieselbe Queue:** Der Server reicht angenommene Submissions in der Reihenfolge ihrer `QueueSubmit`-Annahme auf dieser Queue ein. Queue-Reihenfolge ist keine Garantie, dass eine Submission vollständig abgeschlossen ist, bevor die nächste mit ihrer Ausführung beginnt; unabhängige Arbeit darf sich überlappen. Die Reihenfolge allein ersetzt weder eine notwendige Memory-Dependency noch eine explizite Synchronisation zwischen Commands.
- **Verschiedene Queues:** Zwischen unterschiedlichen Queues, auch innerhalb derselben Queue-Family, besteht keine implizite Reihenfolge und keine implizite Memory-Dependency. Der Server darf weder eine gemeinsame FIFO-Reihenfolge noch Fairness oder eine maximale Wartezeit versprechen.
- **Explizite Abhängigkeit:** Eine queueübergreifende GPU-Abhängigkeit muss mit einem passenden Semaphore-Signal und -Wait hergestellt werden. Das Wait-Stage-Mask bestimmt, an welchen unterstützten Pipeline-Stages die Warteabhängigkeit wirksam wird; es erzeugt nicht automatisch beliebige Memory-Dependencies für alle Ressourcen. Erforderliche Memory-Dependencies müssen den Vulkan-Regeln entsprechend durch die unterstützten Commands und Synchronisationsoperationen abgedeckt sein.
- **Fence und Host-Wait:** Eine Fence beobachtet den terminalen Zustand der Submission, der sie zugeordnet ist. `WaitForFence` und `WaitSemaphores` blockieren den aufrufenden Client bis zum Reply, erzeugen aber selbst keine GPU-Abhängigkeit zwischen Queues. Ein Host-Wait auf ein Semaphore ist kein Ersatz für ein Queue-seitiges Semaphore-Wait.
- **Host-Signal:** `SignalSemaphore` aktualisiert den Timeline-Counter hostseitig. Eine Queue, die auf diesen Wert wartet, kann dadurch fortschreiten; die Host-Signaloperation ordnet jedoch keine anderen GPU-Commands, die nicht über diese Semaphore-Abhängigkeit verbunden sind.
- **Token und Events:** `submission_token` ist nur ein Korrelationswert. Weder sein Zahlenwert noch die Reihenfolge von Tokens oder Event-Sequence-Nummern legt eine Submission-Reihenfolge fest. Terminal-Events melden Ergebnisse, sie schaffen keine Synchronisation.

Diese Regeln spezifizieren notwendige Vulkan-kompatible Ordnungsgrenzen, nicht Scheduler-Implementierungsdetails. Insbesondere gibt es in v0.1 keine Zusage zu Fairness, maximaler Scheduling-Latenz oder Fortschritt innerhalb einer festen Frist.

# Ordering- und Synchronisationsgarantien

1. Requests derselben X11-Verbindung werden grundsätzlich in X11-Protokollreihenfolge validiert und verarbeitet. Ein Request, der auf GPU-Fortschritt wartet, darf den Dispatcher aber nicht so blockieren, dass ein späterer `SignalSemaphore`-Request derselben Verbindung den Fortschritt nicht mehr ermöglichen kann.
2. Ein erfolgreicher `WriteBuffer`-Reply ist ein Ordnungsübergang innerhalb des angegebenen logischen Devices: alle zuvor angenommenen Submissions dieses Devices sind terminal, der Transfer ist abgeschlossen, und jede danach angenommene Submission auf jeder Queue dieses Devices sieht die geschriebenen Bytes. Es gibt keine geräteübergreifende Synchronisation. Während `WriteBuffer` wartet, darf ein späterer `SignalSemaphore`-Request ausgeführt werden, um frühere Arbeit freizugeben; spätere `QueueSubmit`-Requests bleiben bis zum Erfolg oder Fehlschlag des `WriteBuffer` zurückgestellt. Die Details sind in [Memory und Buffers](memory-buffers.md#57-writebuffer) normativ festgelegt. Erkennt der Server unter diesen zurückgestellten Requests einen Binary- oder Timeline-Signal-Entry, der einen Wait einer früheren nicht-terminalen Submission erfüllen würde, ohne dass bereits ein angenommener Signalvorgang diesen Wait erfüllen kann, muss `WriteBuffer` mit `DEPENDENCY_FAILED` fehlschlagen. Bei Timeline-Semaphoren muss der Signalwert den wartenden Wert erreichen oder überschreiten; bei Binary-Semaphoren muss es sich um dieselbe Semaphore handeln. Die Prüfung berücksichtigt nur bereits angenommene Signaloperationen als mögliche Freigabe, nicht Signal-Entries aus zurückgestellten Submissions. Der zurückgestellte `QueueSubmit` wird danach normal verarbeitet; er darf nicht vor einem erfolgreichen `WriteBuffer` angenommen werden. Solange er zurückgestellt ist, gilt er nicht als angenommen: Er darf weder Semaphore-/Fence-Zustände oder Pending-Reservierungen verändern noch interne Ressourcenreferenzen als angenommene Submission festschreiben. Seine vollständige Validierung und atomare Zustandsübernahme erfolgen erst bei der normalen Annahme nach Abschluss des `WriteBuffer`.
3. Ein angenommener `QueueSubmit` ist nicht automatisch abgeschlossen.
4. `ReadBuffer` antwortet erst, wenn die angeforderten Daten bereit sind und notwendige GPU-/Host-Visibility-Operationen erfolgt sind. In v0.1 muss der Server vor dem Reply alle zuvor angenommenen `QueueSubmit`-Submissions desselben logischen Devices bis zu ihrem terminalen Ausgang abwarten; eine vollständige Device-Synchronisation erfüllt diese Anforderung. Der Server muss außerdem frühere `WriteBuffer`-Transfers berücksichtigen, die den gelesenen Bereich betreffen. Ein fehlgeschlagener vorheriger GPU-Auftrag darf nicht als erfolgreiche Ausführung behandelt werden; die Daten sind nicht garantiert korrekt, wenn fehlgeschlagene Arbeit den gelesenen Bereich hätte verändern können.
5. X11-`Sync` bestätigt die Verarbeitung vorheriger X11-Requests, nicht die GPU-Completion.
6. XAverius synchronisiert die von `WriteBuffer` und `ReadBuffer` benötigten Transfergrenzen automatisch. Die `WriteBuffer`-Garantie gilt über alle Queues desselben logischen Devices; Client-seitige Semaphore oder Barrieren sind zwischen erfolgreichem Upload und später angenommener Arbeit für die Sichtbarkeit dieses Uploads nicht erforderlich.
7. XAverius leitet keine beliebigen Shader-zu-Shader-Abhängigkeiten aus dem Inhalt von Shadern ab.
8. Clients bleiben für explizite GPU-Abhängigkeiten zwischen beliebigen Commands verantwortlich.
9. Für die erste Implementierung ist eine konservative vollständige Device-Synchronisation akzeptabel.
10. Nach angenommener asynchroner Arbeit werden Fehler durch Events und Synchronisationszustände gemeldet.

