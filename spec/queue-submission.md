# Queue submission and ordering

## Queue Addressing

Queues are addressed by device XID, queue-family index, and queue index. The server MUST verify that the queue was actually created for this logical device.

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

Each wait entry is 16 bytes:

- Relativer Offset 0: Semaphore-XID
- Offset 4: `CARD64 wait_value`
- Offset 12: `CARD32 wait_stage_mask`

For binary semaphores, `wait_value` MUST be zero. For timeline semaphores, `wait_value` is the required counter value.

Each signal entry is 12 bytes:

- Relativer Offset 0: Semaphore-XID
- Offset 4: `CARD64 signal_value`

For binary semaphores, `signal_value` MUST be zero. For timeline semaphores, `signal_value` is the counter value to signal.

Total length:

`40 + 4*C + 16*W + 12*S`

`submission_token` is supplied by the client and treated as an opaque 64-bit value. It MUST be unique for every `QueueSubmit` request on the same X11 client connection; reuse is forbidden even after a submission completes, for as long as the connection remains open. Value `0` is reserved and invalid. Tokens need not be ordered and have no temporal or numeric meaning. A timestamp or hash is permitted if the client actually guarantees uniqueness.

Error precedence (the first applicable phase wins): (1) incorrect total length, inconsistent counts, arithmetic overflow, or truncated entries results in `BadLength`; (2) syntactic fields are checked: `submission_token = 0`, a token already used on this connection, non-zero reserved fields, wait-stage masks containing zero or reserved bits, duplicate raw semaphore XIDs, and invalid values that can be identified without resolving a resource type result in `BadValue`; (3) required XIDs are resolved in wire order: device, optional fence, command-buffer XIDs in array order, wait-semaphore XIDs in array order, then signal-semaphore XIDs in array order. Unknown or non-live XIDs result in `BadValue`; (4) only then are resource type, client/device ownership, and queue association checked; a live resource of the wrong type, foreign ownership, cross-device association, or a queue not created for this device results in `BadMatch`; (5) after successful XID/type/ownership/queue validation, an unavailable or lost device takes precedence over mutable submission state and results in `DEVICE_UNAVAILABLE` or `DEVICE_LOST`; (6) if the device is operational, mutable preconditions are checked in wire order: first the optional fence state, then command buffers in array order, wait entries in array order, and finally signal entries in array order. Within each wait/signal entry, type-dependent numeric values are checked first, then stage-family compatibility (wait entries only), and then whether the semaphore operation is permitted, including pending/signal reservations. Invalid fence/command-buffer/semaphore states or an unsupported stage result in `INVALID_SYNCHRONIZATION_STATE`; invalid type-dependent numeric values result in `BadValue`. In particular, a timeline signal value that is not greater than the observable counter results in `BadValue`; a value that exceeds the counter but is not greater than every already-reserved pending GPU signal value results in `INVALID_SYNCHRONIZATION_STATE`, as for `SignalSemaphore`. Any other dependency that prevents acceptance results in `DEPENDENCY_FAILED`. Type-dependent values such as binary wait/signal values are checked only after type resolution. Within each phase, the field/array order in the request is preserved. Every synchronously rejected request is atomic and generates no submission event. Execution failures reported after acceptance are not X11 errors.

The server copies the token unchanged into the corresponding `SUBMISSION_COMPLETE` or `SUBMISSION_FAILED` event and into submission-related `ASYNC_ERROR` events. The X11 event sequence number is independent and does not identify the submission.

### Wait Stage Mask

`wait_stage_mask` is an XAverius-specific `CARD32` bitmask; its bits are **not** the numeric Vulkan `VkPipelineStageFlags` values. The v0.1 mapping is fixed:

| XAverius Bit | Mask | Vulkan Stage |
|---|---:|---|
| `DRAW_INDIRECT` | `0x00000001` | `VK_PIPELINE_STAGE_DRAW_INDIRECT_BIT` |
| `COMPUTE_SHADER` | `0x00000002` | `VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT` |
| `TRANSFER` | `0x00000004` | `VK_PIPELINE_STAGE_TRANSFER_BIT` |
| `ALL_COMMANDS` | `0x00000008` | `VK_PIPELINE_STAGE_ALL_COMMANDS_BIT` |

Bits 4–31 are reserved and MUST be zero. The mask MUST set at least one bit. As in Vulkan, `ALL_COMMANDS` may be combined with other supported bits; such combinations are semantically redundant but valid. XAverius explicitly translates each set bit to its corresponding Vulkan value and combines the Vulkan bits using bitwise OR; the XAverius mask MUST NOT be passed through unchanged as a Vulkan mask.

The set stages MUST be supported by the addressed queue family under the Vulkan synchronization rules:

- `DRAW_INDIRECT`: queue family with `GRAPHICS` or `COMPUTE`.
- `COMPUTE_SHADER`: queue family with `COMPUTE`.
- `TRANSFER`: queue family with `GRAPHICS`, `COMPUTE`, or `TRANSFER`.
- `ALL_COMMANDS`: permitted on every queue family created for the logical device.

A mask with unknown/reserved bits or no set bits is syntactically invalid and results in `BadValue`. A syntactically valid mask whose stage is unsupported by the addressed queue family results in `INVALID_SYNCHRONIZATION_STATE`. This check occurs before acceptance; failure leaves submission, fence, and semaphore states unchanged.

For the compute-only reference workflow, `COMPUTE_SHADER`, `TRANSFER`, and `ALL_COMMANDS` are valid single-bit masks on a compute-capable queue. `DRAW_INDIRECT` is also permitted as a stage on a compute queue, even though the v0.1 command stream defines no indirect-dispatch commands. The wait takes effect at the selected Vulkan destination stage; it is not a general substitute for required memory dependencies between commands.

Before acceptance, all command buffers and synchronization objects are validated. All resources MUST belong to the specified device. Every command buffer MUST be executable. A specified fence MUST be `UNSIGNALED` and MUST NOT already be pending.

Duplicate wait or signal entries are invalid in v0.1 and result in `BadValue`. The same semaphore MUST NOT appear in both the wait and signal arrays of one submission; this conflict also results in `BadValue`.

**Atomicity guarantee:** If the request is rejected, no submission is created and no synchronization state changes. Acceptance means only that the work has been queued, not that it has completed.

`QueueSubmit` is a void request. Acceptance or rejection is reported synchronously through the normal X11 error rules; the token is used exclusively to correlate later asynchronous results.


### Validation and Atomic Acceptance

Die Validierung ist zweiphasig. Zuerst prüft der Server Request-Framing und Längen/Counts, reservierte Felder und Token-Syntax, danach löst er Ressourcen in der definierten Feldreihenfolge auf und prüft Typ, Client-/Device-Ownership sowie Queue-Zuordnung. Anschließend prüft er den Device-Zustand und sämtliche veränderlichen Submit-Voraussetzungen: jeder Command Buffer muss `EXECUTABLE`, nicht `PENDING` oder `INVALID`, sein; Fence und Semaphore müssen submitbar sein; Wait-Stages, Semaphore-Typen/-Werte, Timeline-Signalreservierungen und alle sonstigen Abhängigkeiten müssen gültig sein. Die allgemeine XID-Fehlerpräzedenz und die request-spezifische Reihenfolge gelten auch bei mehreren fehlerhaften Feldern; eine Implementierung darf nicht vorzeitig Zustand reservieren, nur weil sie einen früheren Eintrag bereits validiert hat.

Erst wenn alle Prüfungen erfolgreich sind, nimmt der Server die Submission als eine einzige serialisierte Transaktion an. In diesem Commit-Punkt werden der `submission_token` als verwendet registriert, die Submission angelegt, die Command Buffer auf `PENDING` gesetzt, Fence und Semaphore-Zuordnungen/Wait-/Signal-Slots reserviert und sämtliche internen Ressourcenreferenzen festgehalten. Kein sichtbarer Teil dieses Commit-Punkts darf für andere Requests oder asynchrone Backend-Callbacks als angenommen gelten, bevor der ganze Commit abgeschlossen ist.

Jede Ablehnung vor diesem Commit-Punkt ist vollständig nicht-mutierend: der Token bleibt unbenutzt und darf in einem korrigierten Request wiederverwendet werden; kein Command Buffer verlässt `EXECUTABLE`; keine Fence wechselt ihren Zustand oder wird einer Submission zugeordnet; Semaphore-Counter, Signalverfügbarkeit, Pending-Slots und Timeline-Reservierungen bleiben unverändert; es entstehen keine Submission-Objekte, internen Submission-Referenzen oder Submission-Events. Das gilt auch dann, wenn mehrere Command Buffer oder Synchronisationsobjekte bereits einzeln validiert wurden, bevor ein späterer Eintrag fehlschlägt. Ein synchroner Fehler darf kein `ASYNC_ERROR` für eine nicht angenommene Submission erzeugen.

Die `EXECUTABLE`-zu-`PENDING`-Übergänge und die Synchronisationsreservierungen sind somit ein gemeinsamer Commit, nicht voneinander getrennte schrittweise Änderungen. Nach diesem Commit ist die Submission angenommen; spätere Backend-Fehler werden ausschließlich über den terminalen Submission-Ausgang und die definierten Synchronisationszustände verarbeitet.
## Terminal Submission State and Device Loss

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

# Queue Ordering and Cross-Queue Dependencies

Die folgenden Regeln gelten für angenommene Submissions desselben logischen Devices:

- **Dieselbe Queue:** Der Server reicht angenommene Submissions in der Reihenfolge ihrer `QueueSubmit`-Annahme auf dieser Queue ein. Queue-Reihenfolge ist keine Garantie, dass eine Submission vollständig abgeschlossen ist, bevor die nächste mit ihrer Ausführung beginnt; unabhängige Arbeit darf sich überlappen. Die Reihenfolge allein ersetzt weder eine notwendige Memory-Dependency noch eine explizite Synchronisation zwischen Commands.
- **Verschiedene Queues:** Zwischen unterschiedlichen Queues, auch innerhalb derselben Queue-Family, besteht keine implizite Reihenfolge und keine implizite Memory-Dependency. Der Server darf weder eine gemeinsame FIFO-Reihenfolge noch Fairness oder eine maximale Wartezeit versprechen.
- **Explizite Abhängigkeit:** Eine queueübergreifende GPU-Abhängigkeit muss mit einem passenden Semaphore-Signal und -Wait hergestellt werden. Das Wait-Stage-Mask bestimmt, an welchen unterstützten Pipeline-Stages die Warteabhängigkeit wirksam wird; es erzeugt nicht automatisch beliebige Memory-Dependencies für alle Ressourcen. Erforderliche Memory-Dependencies müssen den Vulkan-Regeln entsprechend durch die unterstützten Commands und Synchronisationsoperationen abgedeckt sein.
- **Fence und Host-Wait:** Eine Fence beobachtet den terminalen Zustand der Submission, der sie zugeordnet ist. `WaitForFence` und `WaitSemaphores` blockieren den aufrufenden Client bis zum Reply, erzeugen aber selbst keine GPU-Abhängigkeit zwischen Queues. Ein Host-Wait auf ein Semaphore ist kein Ersatz für ein Queue-seitiges Semaphore-Wait.
- **Host-Signal:** `SignalSemaphore` aktualisiert den Timeline-Counter hostseitig. Eine Queue, die auf diesen Wert wartet, kann dadurch fortschreiten; die Host-Signaloperation ordnet jedoch keine anderen GPU-Commands, die nicht über diese Semaphore-Abhängigkeit verbunden sind.
- **Token und Events:** `submission_token` ist nur ein Korrelationswert. Weder sein Zahlenwert noch die Reihenfolge von Tokens oder Event-Sequence-Nummern legt eine Submission-Reihenfolge fest. Terminal-Events melden Ergebnisse, sie schaffen keine Synchronisation.

Diese Regeln spezifizieren notwendige Vulkan-kompatible Ordnungsgrenzen, nicht Scheduler-Implementierungsdetails. Insbesondere gibt es in v0.1 keine Zusage zu Fairness, maximaler Scheduling-Latenz oder Fortschritt innerhalb einer festen Frist.

# Ordering and Synchronization Guarantees

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

