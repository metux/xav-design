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

Fehlerzuordnung: falsche Gesamtlänge, inkonsistente Counts oder arithmetischer Überlauf ergeben `BadLength`; Token `0`, ein bereits auf derselben Verbindung verwendeter Token, nicht-null reservierte Felder sowie ungültige Masks/Werte ergeben `BadValue`. Unbekannte/nicht-live XIDs ergeben `BadValue`; falscher live Ressourcentyp, fremde Client-/Device-Ownership oder eine nicht für dieses Device erstellte Queue ergeben `BadMatch`. Ein nicht ausführbarer Command Buffer, ein unzulässiger Fence-/Semaphore-Zustand oder eine für die Queue ungültige Wait-Stage-Mask ergibt `INVALID_SYNCHRONIZATION_STATE`; eine sonstige Abhängigkeit, die die Annahme verhindert, ergibt `DEPENDENCY_FAILED`. Ein nicht verfügbares/verlorenes Device ergibt `DEVICE_UNAVAILABLE`/`DEVICE_LOST`. Jeder synchron abgewiesene Request bleibt atomar und erzeugt kein Submission-Event. Nach Annahme gemeldete Ausführungsfehler sind keine X11-Fehler.

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

Doppelte Wait- oder Signal-Einträge sind in v0.1 ungültig. Dieselbe Semaphore darf in einer Submission nicht gleichzeitig im Wait- und Signal-Array stehen.

**Atomaritätsgarantie:** Wird der Request abgelehnt, wird keine Submission angelegt und kein Synchronisationszustand verändert. Bei Annahme bedeutet der Request nur, dass die Arbeit eingereiht wurde; nicht, dass sie bereits abgeschlossen ist.

`QueueSubmit` ist ein Void-Request. Die Annahme oder Ablehnung wird synchron über die normalen X11-Fehlerregeln signalisiert; der Token dient ausschließlich der Korrelation späterer asynchroner Ergebnisse.

## Terminaler Submission-Zustand und Device Loss

Jede angenommene Submission hat genau einen terminalen Ausgang:

- `SUBMISSION_COMPLETE`: Alle Commands der Submission wurden erfolgreich abgeschlossen.
- `SUBMISSION_FAILED`: Die Submission wurde nicht erfolgreich abgeschlossen; das Event enthält den `submission_token` und einen Fehlerstatus.

Jede angenommene Submission erhält intern genau einen terminalen Ausgang. Ist das passende Completion- oder Failure-Event für die Queue ausgewählt und die Client-Verbindung noch aktiv, liefert der Server genau das dazugehörige Event aus. Ohne passende Event-Auswahl wird kein solches Event an den Client zugestellt; der terminale interne Zustand bleibt davon unberührt. Ein `ASYNC_ERROR` kann zusätzliche Diagnoseinformationen liefern, ersetzt den terminalen Ausgang nicht und darf keinen zweiten terminalen Ausgang erzeugen. Eine abgelehnte `QueueSubmit`-Anforderung wurde nicht angenommen und erhält keinen terminalen Ausgang.

Tritt nach der Annahme ein Ausführungsfehler auf, schlägt die Submission fehl; sie gilt nicht als abgeschlossen. Ihre Fence wechselt gegebenenfalls nach `FAILED`. Jeder von dieser Submission verwendete Command Buffer wechselt nach Ende der Pending-Phase nach `INVALID`. Vor einer erneuten Verwendung muss er gemäß der Command-Buffer-API zurückgesetzt und neu aufgezeichnet werden. Der Server hält interne Referenzen, bis die Submission terminal ist und das Backend nicht mehr auf die Ressourcen zugreift.

Bei Device Loss schlagen alle angenommenen, noch nicht terminalen Submissions des betroffenen logischen Devices mit `DEVICE_LOST` fehl. Der Server darf keine erfolgreiche Completion vortäuschen und keine Fence für nicht erfolgreich abgeschlossene Arbeit auf `SIGNALED` setzen. Für jede angenommene Submission bleibt genau ein terminales Event vorgesehen, sofern die Client-Verbindung noch besteht. Weitere GPU-Arbeit auf dem verlorenen Device wird nicht ausgeführt. Requests, die nur den Status abfragen oder das logische Device bereinigen, dürfen nach ihren jeweiligen Regeln weiterlaufen; Operationen, die ein funktionsfähiges Device benötigen, schlagen mit `DEVICE_LOST` fehl.

## Semaphore references

The semaphore types and host-side semaphore operations used by `QueueSubmit` are specified in [Synchronization objects](synchronization.md). The `QueueSubmit` request retains its wait and signal arrays as described above.

# Ordering- und Synchronisationsgarantien

1. Requests derselben X11-Verbindung werden grundsätzlich in X11-Protokollreihenfolge validiert und verarbeitet. Ein Request, der auf GPU-Fortschritt wartet, darf den Dispatcher aber nicht so blockieren, dass ein späterer `SignalSemaphore`-Request derselben Verbindung den Fortschritt nicht mehr ermöglichen kann.
2. Ein erfolgreicher `WriteBuffer`-Reply ist ein Ordnungsübergang innerhalb des angegebenen logischen Devices: alle zuvor angenommenen Submissions dieses Devices sind terminal, der Transfer ist abgeschlossen, und jede danach angenommene Submission auf jeder Queue dieses Devices sieht die geschriebenen Bytes. Es gibt keine geräteübergreifende Synchronisation. Während `WriteBuffer` wartet, darf ein späterer `SignalSemaphore`-Request ausgeführt werden, um frühere Arbeit freizugeben; spätere `QueueSubmit`-Requests bleiben bis zum Erfolg oder Fehlschlag des `WriteBuffer` zurückgestellt. Die Details sind in [Memory und Buffers](memory-buffers.md#57-writebuffer) normativ festgelegt.
3. Ein angenommener `QueueSubmit` ist nicht automatisch abgeschlossen.
4. `ReadBuffer` antwortet erst, wenn die angeforderten Daten bereit sind und notwendige GPU-/Host-Visibility-Operationen erfolgt sind. In v0.1 muss der Server vor dem Reply alle zuvor angenommenen `QueueSubmit`-Submissions desselben logischen Devices bis zu ihrem terminalen Ausgang abwarten; eine vollständige Device-Synchronisation erfüllt diese Anforderung. Der Server muss außerdem frühere `WriteBuffer`-Transfers berücksichtigen, die den gelesenen Bereich betreffen. Ein fehlgeschlagener vorheriger GPU-Auftrag darf nicht als erfolgreiche Ausführung behandelt werden; die Daten sind nicht garantiert korrekt, wenn fehlgeschlagene Arbeit den gelesenen Bereich hätte verändern können.
5. X11-`Sync` bestätigt die Verarbeitung vorheriger X11-Requests, nicht die GPU-Completion.
6. XAverius synchronisiert die von `WriteBuffer` und `ReadBuffer` benötigten Transfergrenzen automatisch. Die `WriteBuffer`-Garantie gilt über alle Queues desselben logischen Devices; Client-seitige Semaphore oder Barrieren sind zwischen erfolgreichem Upload und später angenommener Arbeit für die Sichtbarkeit dieses Uploads nicht erforderlich.
7. XAverius leitet keine beliebigen Shader-zu-Shader-Abhängigkeiten aus dem Inhalt von Shadern ab.
8. Clients bleiben für explizite GPU-Abhängigkeiten zwischen beliebigen Commands verantwortlich.
9. Für die erste Implementierung ist eine konservative vollständige Device-Synchronisation akzeptabel.
10. Nach angenommener asynchroner Arbeit werden Fehler durch Events und Synchronisationszustände gemeldet.

