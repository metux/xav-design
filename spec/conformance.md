# Compute-Referenzablauf

Ziel-Workload:

`C[i] = A[i] + B[i]`

Typischer Ablauf:

1. Physical Device enumerieren oder Default Device erstellen.
2. Memory-Properties abfragen und logisches Device mit Compute-Queue erstellen.
3. A-, B- und C-Buffer erstellen.
4. Memory-Anforderungen abfragen, Speicher allozieren und Buffer binden.
5. A und B mit unabhängigen `WriteBuffer`-Requests hochladen.
6. Shader Module erstellen.
7. Descriptor Set Layout, Descriptor Pool und Descriptor Set erstellen.
8. Pipeline Layout und Compute Pipeline erstellen.
9. Descriptor Set mit A, B und C aktualisieren.
10. Command Pool und Command Buffer erstellen.
11. Pipeline binden.
12. Descriptor Sets binden.
13. Bei Bedarf Push Constants setzen.
14. `Dispatch` aufzeichnen und Command Buffer finalisieren.
15. Fence/Semaphoren erstellen, sofern erforderlich.
16. `QueueSubmit` ausführen.
17. Completion mit Fence oder Semaphore abwarten.
18. C über `ReadBuffer` zurücklesen.
19. Ressourcen nach den Lebenszyklusregeln zerstören.

Der Server muss sicherstellen, dass die Descriptoren zum Shader passen, statisch verwendete Ressourcen vorhanden sind und Dispatch-Limits eingehalten werden.

# Konformität und Tests

Eine Implementierung sollte mindestens folgende Fälle testen:

- Exakte Request-Längen, Counts und Padding
- `EnumeratePhysicalDevices` ist ein 8-Byte-Reply-Request; `DestroyDevice` ist ein 12-Byte-Void-Request
- `EnumeratePhysicalDevices.reply.length` entspricht der Summe der gepaddeten `PHYSICALDEVICEINFO`-Record-Längen geteilt durch vier; ohne Records ist es null
- `GetPhysicalDeviceQueueFamilyProperties.reply.length` entspricht `3 * queue_family_count`; die Payload-Länge muss durch 12 teilbar sein
- `GetPhysicalDeviceProperty` verwendet `SUCCESS = 0`, `NOT_SUPPORTED = 1`, `NOT_AVAILABLE = 2`; bei Nicht-Erfolg sind `property_type`, `value_length` und Payload null und `reply.length = 0`
- `GetPhysicalDeviceProperty` akzeptiert die vier kanonischen Namen aus der Property-Registry; Atom-IDs bleiben serverseitig vergeben. Unbekannte Atom-IDs ergeben `BadAtom`, gültige aber nicht registrierte Atom-Namen `NOT_SUPPORTED`, registrierte aber nicht verfügbare Properties `NOT_AVAILABLE`
- `XAverius.deviceUUID` und `XAverius.driverUUID` liefern bei Erfolg exakt 16 `BYTE_ARRAY`-Bytes; `XAverius.compute.maxWorkGroupInvocations` liefert einen `CARD32`; `XAverius.compute.maxWorkGroupSize` liefert genau drei `CARD32`-Werte in X/Y/Z-Reihenfolge. Der Reply-Typ und die exakte Wertlänge müssen zur Registry passen
- Die v0.1 Feature-ID- und Device-Extension-Registries sind leer: jede Feature-ID ergibt `BadValue`; syntaktisch gültige optionale Extension-Namen ergeben `BadMatch`; syntaktisch ungültige Extension-Namen ergeben `BadValue`; weder `CreateDevice` noch `CreateDefaultDevice` aktiviert optionale Features oder Extensions implizit
- `CreateDevice`-Länge entspricht exakt den drei geordneten variablen Record-Arrays; mindestens eine Queue-Family-Anforderung ist erforderlich; Queue-Prioritäten müssen endlich und in [0,1] liegen; unbekannte Feature-IDs, `enabled != 1`, doppelte Features/Extensions und syntaktisch ungültige Extension-Namen ergeben `BadValue`; registrierte, aber nicht unterstützte Features sowie unbekannte oder nicht unterstützte syntaktisch gültige Extensions ergeben `BadMatch`; jeder Fehler lässt die Create-XID unangelegt; `CreateDevice` und `CreateDefaultDevice` senden bei Erfolg keinen Reply
- `GetPhysicalDeviceMemoryProperties` liefert Memory-Type-/Heap-Indizes, die über die Lebensdauer der Physical-Device-XID stabil bleiben
- `AllocateMemory` hat exakt 32 Bytes; `allocation_size` muss positiv, `memory_type_index` gültig und das reservierte Feld null sein. Ungültige Werte ergeben `BadValue`, eine ungültige/belegte Ziel-XID `BadIDChoice`, Backend-Allokationsfehler `ALLOCATION_FAILED`; bei Ablehnung bleibt die Ziel-XID unangelegt.
- `CreatePipelineLayout` prüft exakt `20 + 4 * set_layout_count + 12 * push_constant_range_count` Bytes, registrierte Stage-Bits, Push-Constant-Ranges, Device-/Set-Layout-Ownership und Ziel-XID-Kollisionen; Ablehnung hinterlässt kein Pipeline Layout.
- `CreateSemaphore` hat exakt 28 Bytes und akzeptiert nur `BINARY = 0` oder `TIMELINE = 1`; bei Binary muss `initial_value = 0` sein. Ungültige Felder ergeben `BadValue`, Ziel-XID-Kollision `BadIDChoice`, Backend-Allokationsfehler `ALLOCATION_FAILED`.
- `CreateFence` hat exakt 24 Bytes, `create_flags = 0` und `reserved = 0`; der Anfangszustand ist `UNSIGNALED`. Ungültige Felder ergeben `BadValue`, Ziel-XID-Kollision `BadIDChoice`, Backend-Allokationsfehler `ALLOCATION_FAILED`.
- `SelectEvents` hat exakt 32 Bytes und erfordert vorherige erfolgreiche XGE-1.0-Aushandlung; Scope-/Masken- und ungenutzte Feldkombinationen werden validiert. Jeder Fehler erhält die vorherige Event-Auswahl atomar unverändert.
- Nach erfolgreicher Verarbeitung von `DestroyDevice` werden keine neuen Events mit dessen zerstörter `device_xid` mehr erzeugt oder zugestellt; bereits zuvor in den X11-Ausgabestrom eingereihte Events bleiben unberührt. Die interne terminale Abwicklung angenommener Submissions und Backend-Referenzen bleibt unabhängig von dieser Event-Unterdrückung erhalten.
- Nach Client-Disconnect werden für die geschlossene Verbindung keine neuen XAverius-Events mehr eingereiht oder über andere Verbindungen zugestellt; Event-Auswahlen und öffentliche XID-Zuordnungen der Verbindung werden aus dem aktiven Verbindungszustand entfernt. Bereits angenommene Arbeit erreicht intern ihren tatsächlichen terminalen Ausgang, ohne Completion zu erfinden oder Backend-Ressourcen vorzeitig freizugeben; der Disconnect erzwingt kein unbegrenztes Warten.
- `CreateBuffer` weist `usage_flags = 0` und unbekannte Usage-Bits mit `BadValue` ab
- `CreateDescriptorPool`, `AllocateDescriptorSets` und `FreeDescriptorSets` weisen Count null mit `BadValue` ab
- Alle Create-Ziel-XIDs werden getrennt von Eingabe-XIDs geprüft: ungültige/belegte Ziel-XIDs ergeben `BadIDChoice`; Batch-Erzeugung hinterlässt bei Kollision keine Teilmenge
- `ShaderModuleData` ohne passendes Upload-Assembly und `CommandBufferData` ohne passenden `RECORDING`-Buffer werden mit `INVALID_SYNCHRONIZATION_STATE` abgewiesen; CREATE-XID-Kollisionen ergeben `BadIDChoice`
- `CreateDevice` weist null Queue-Family-Records, null Queue-Anzahl und doppelte Queue-Family-Records mit `BadValue` ab; eine nicht unterstützte Queue-Anzahl ergibt `BadMatch`
- Binary-Semaphore: ein angenommener Wait konsumiert das Signal nicht vor tatsächlicher Erfüllung; das Signal wird genau einmal konsumiert und erst dann kann ein neuer Signalzyklus beginnen; doppelte pending Wait-/Signaloperationen werden atomar abgewiesen
- Timeline-Semaphore: angenommene, noch nicht terminale Signaloperationen reservieren ihre Werte, erhöhen den beobachtbaren Counter aber erst nach erfolgreicher Ausführung; neue Signalwerte müssen über allen pending reservierten Werten liegen
- Jede angenommene Queue-Wait-/Signaloperation hält eine Referenz auf die exakte interne Semaphore-Identität bis zum terminalen Operationsausgang und bis das Backend keinen Zugriff mehr ausführen kann; XID-Wiederverwendung darf diese Referenz nicht umleiten
- Doppelte Pool-Size-Typen, doppelte Descriptor-Updates desselben Slots, doppelte Wait-/Signal-Entries sowie eine Semaphore zugleich in Wait und Signal werden gemäß den Fehlerregeln atomar abgewiesen
- `CreateComputePipeline` verwendet die normative Länge `28 + ((entry_point_length + 3) & ~3)` und prüft nichtleeren ASCII-Entry-Point sowie Null-Padding
- `DestroySemaphore` und `DestroyFence` sind jeweils 16-Byte-Void-Requests; `WaitSemaphores` verwendet `28 + 12 * semaphore_count`
- `GetFenceStatus` ist ein 16-Byte-Reply-Request mit Fence-Status in Reply-Byte 1, `reply.length = 0` und null reservierten XAverius-Bytes in Offsets 8–31
- Error-Offsets und Event-/Reply-Statuswerte bleiben getrennte Namespaces: `EXECUTION_FAILED` ist Error-Offset 3, `WaitForFence`-Status 2 und `SUBMISSION_FAILED.failure_class` 0; `DEVICE_LOST` ist Error-Offset 1, `WaitForFence`-Status 3 und `SUBMISSION_FAILED.failure_class` 1. `DEVICE_LOST.reason_code` verwendet wiederum die eigene Reason-Code-Registry.
- `WaitSemaphores` und `WaitForFence` mit Timeout 0 prüfen den Zustand ohne absichtliches Warten; `UINT64_MAX` wartet unbegrenzt, andere Werte verwenden eine monotone Nanosekunden-Frist ab Ausführungsübernahme
- Eine endliche Wait-Frist wird bei internen Warteabschnitten oder Scheduler-Unterbrechungen nicht neu gestartet; die Antwort darf verspätet eintreffen, aber eine bereits erfüllte Bedingung gewinnt bei der abschließenden Zustandsprüfung gegen `TIMEOUT`
- `WaitSemaphores`-Timeout liefert Status `TIMEOUT` ohne Zustandsänderung; `WaitForFence` liefert `SUCCESS`, `EXECUTION_FAILED` oder `TIMEOUT` gemäß dem terminalen Fence-Zustand und der Frist
- Device Loss während eines blockierenden Waits wird nicht als Timeout maskiert: `WaitSemaphores` endet mit `DEVICE_LOST`-X11-Fehler, `WaitForFence` liefert `DEVICE_LOST` im Reply
- Nach Device Loss liefert `GetFenceStatus` den gespeicherten Zustand; Fences aus dadurch fehlgeschlagenen nicht-terminalen Submissions stehen auf `FAILED`, nicht eingereichte Fences werden nicht künstlich verändert. `WaitForFence` liefert nach erkanntem Device Loss stets `DEVICE_LOST`, ohne unbegrenzt weiterzuwarten
- Nach Device Loss liefert `GetSemaphoreCounterValue` keinen scheinbar erfolgreichen Counter-Reply, sondern `DEVICE_LOST`; `SignalSemaphore`, `QueueSubmit` und `WaitSemaphores` können Semaphore-Operationen nicht als erfolgreich fortgesetzt behandeln
- Device-Loss-Teardown invalidiert öffentliche Fence-/Semaphore-XIDs, darf aber interne Synchronisationsobjekte erst freigeben, wenn Backend-Zugriffe und serverseitige Operationen sicher beendet sind oder die Objekte gemäß den Quarantäneregeln isoliert bleiben
- `CommandBufferData`-ABORT hat exakt 16 Bytes; andere Chunks enthalten nur vollständige Entries
- `QueueSubmit`-Länge stimmt exakt mit `40 + 4*C + 16*W + 12*S` überein; Null- und wiederverwendete Submission-Tokens ergeben `BadValue`; Counts/Längenüberlauf ergeben `BadLength`; fremde Ownership/Queue ergeben `BadMatch`; ungültige Zustände ergeben `INVALID_SYNCHRONIZATION_STATE`; synchron abgewiesene Requests erzeugen kein Submission-Event
- `QueueSubmit.wait_stage_mask` wird als XAverius-Bitmaske und nicht als rohe Vulkan-Maske interpretiert: `DRAW_INDIRECT=0x1`, `COMPUTE_SHADER=0x2`, `TRANSFER=0x4`, `ALL_COMMANDS=0x8`; die Backend-Übersetzung verwendet die zugehörigen Vulkan-Stage-Bits
- Wait-Stage-Masken mit Wert 0 oder reservierten Bits ergeben `BadValue`; die Ablehnung ist atomar und lässt Fence-/Semaphore-Zustände unverändert
- Auf einer Compute-Queue sind alle vier einzeln definierten Stage-Bits gültig; auf einer reinen Transfer-Queue sind nur `TRANSFER` und `ALL_COMMANDS` gültig; `COMPUTE_SHADER` auf einer Nicht-Compute-Queue sowie `DRAW_INDIRECT` ohne Graphics- oder Compute-Unterstützung ergeben `INVALID_SYNCHRONIZATION_STATE`
- Kombinierte Masken aus mehreren unterstützten Stages (z. B. `COMPUTE_SHADER | TRANSFER`) werden akzeptiert; auch `ALL_COMMANDS | COMPUTE_SHADER` wird akzeptiert und korrekt als OR der Vulkan-Stage-Bits übersetzt. Eine Maske mit einem nicht unterstützten Stage wird mit `INVALID_SYNCHRONIZATION_STATE` atomar abgewiesen
- `ShaderModuleData`: Einzelrequest CREATE|FINAL, mehrteiliger Upload, exakte Konkatenation ohne Paddingbytes, gültige Flag-Kombinationen und Null-Padding
- Fehler in einem Shader-Chunk verwirft das gesamte Assembly; FINAL-Fehler hinterlässt kein live Shader Module; ABORT gibt Assembly-Speicher frei
- Upload-Grenzen und aggregierte Assembly-Speicherlimits werden vor Allokation geprüft
- `CreateDescriptorSetLayout` prüft die exakte Länge `24 + 16 * binding_count`, `flags = 0`, Binding-Eindeutigkeit, positive Descriptor-Counts und unterstützte Descriptor-/Stage-Werte
- Ein leeres Descriptor Set Layout mit `binding_count = 0` ist gültig; fehlerhafte Binding-Records oder nicht-null Layout-Flags hinterlassen kein öffentliches Objekt
- Ein nicht zum Count passender Payload ergibt `BadLength`; nicht unterstützte Flags, Typen oder Stage-Bits werden abgewiesen
- `CreateCommandPool` prüft Queue-Family-Index und reservierte Pool-Flags; `DestroyCommandPool` invalidiert alle Kinder atomar
- `CreateCommandPool` akzeptiert nur `TRANSIENT` und `RESET_COMMAND_BUFFER`; unbekannte Pool-Flags werden mit `BadValue` abgewiesen und nicht stillschweigend ergänzt
- `TRANSIENT` ändert keine beobachtbare Semantik; `RESET_COMMAND_BUFFER` und `TRANSIENT` sind unabhängig kombinierbar
- `ResetCommandBuffer` ohne `RESET_COMMAND_BUFFER` wird abgewiesen; mit Flag setzt es `INITIAL`, `RECORDING`, `EXECUTABLE` oder `INVALID` auf `INITIAL` und verwirft Entries samt aufgezeichneten Referenzen
- `ResetCommandBuffer` bei `PENDING` wird atomar abgewiesen; Zustand und Referenzen bleiben unverändert
- `CommandBufferData`-`ABORT` kann ein nicht-pending `RECORDING` unabhängig vom Pool-Reset-Flag auf `INITIAL` zurücksetzen, ist aber für andere Zustände unzulässig
- `CommandBufferData` validiert alle Entries eines Chunks vor dem Anhängen; bei einem ungültigen Chunk wird nichts aus diesem Chunk angehängt
- Nach fehlgeschlagenem CommandBufferData-Chunk bleiben zuvor akzeptierte Chunks erhalten; ein korrigierter Chunk kann folgen oder ABORT setzt den Buffer auf INITIAL zurück
- Fehlgeschlagenes CREATE hinterlässt keinen Command Buffer; fehlgeschlagenes FINAL lässt den bestehenden Buffer RECORDING
- ABORT ist bei INITIAL, EXECUTABLE, INVALID oder PENDING unzulässig und ändert keinen Zustand
- Die zentrale Request-Registry enthält genau 40 eindeutige, explizit vergebene Subopcodes (1–40); Subopcode 0 ist reserviert, kein Wert ist doppelt vergeben, und spätere Requests dürfen bestehende Werte nicht verschieben oder wiederverwenden
- Die Command-Entry-Registry weist `CMD_BIND_PIPELINE`, `CMD_BIND_DESCRIPTOR_SETS`, `CMD_DISPATCH` und `CMD_PUSH_CONSTANTS` eindeutig die IDs 1–4 zu; ID 0 und alle nicht zugewiesenen IDs werden mit `BadValue` abgewiesen
- Die Descriptor-Type-Registry definiert in v0.1 ausschließlich `STORAGE_BUFFER = 1`; `0` und alle nicht zugewiesenen Werte werden abgewiesen und niemals stillschweigend umgedeutet
- Die Shader-Stage-Registry definiert ausschließlich das `COMPUTE`-Bit `0x00000001`; andere Bits sind reserviert und müssen abgewiesen werden
- Queue-Flags werden gemäß der zentralen Registry übersetzt und zurückgegeben; Bits 5–31 sind null/reserviert
- `PHYSICALDEVICEINFO.device_type` enthält nur die registrierten Werte 0–4; unbekannte native Kategorien werden als `OTHER = 0` abgebildet
- Byteordnung und feste Wire-Feldbreiten
- Reservierte Felder und unbekannte Flags
- Ungültige XIDs, Ressourcentypen und Ownership
- Cross-Device-Verwendung
- Atomare Create-, Update- und Submit-Operationen
- Überlauf- und Grenzfälle bei Buffer-Bereichen
- `BindBufferMemory`: ungültige XIDs, falscher Typ/Ownership, bereits gebundener Buffer, Alignment, Memory-Type und Bounds werden jeweils dem festgelegten Fehlerpfad zugeordnet; bei Ablehnung bleibt der Buffer ungebunden
- `UpdateDescriptorSets`: Count null ergibt `BadValue`, Payload-Längenfehler `BadLength`, inkompatible Ressourcen `BadMatch`, Pending-Use `INVALID_SYNCHRONIZATION_STATE`; bei Ablehnung keine Teiländerung
- `ResetFence`: nur `SIGNALED` und `FAILED` dürfen zurückgesetzt werden; andere Zustände ergeben `INVALID_SYNCHRONIZATION_STATE`, verlorenes Device `DEVICE_LOST`, Ablehnung erhält den Zustand
- Unbekannte/nicht-live XAverius-XIDs ergeben `BadValue`, falsche live Ressourcentypen und Cross-Client-/Cross-Device-Ownership `BadMatch`, ungültige Atoms `BadAtom` und belegte Create-XIDs `BadIDChoice`; dies gilt auch für `DestroyResource`, `BindBufferMemory`, `UpdateDescriptorSets`, `QueueSubmit` und `ResetFence`
- Memory-Alignment und Memory-Type-Kompatibilität
- Command-Buffer-Zustandsübergänge
- Fence- und Semaphore-Zustände sowie Timeouts
- Descriptor-Update/Freigabe während Pending-Use
- Ressourcenzerstörung bei internen Referenzen
- `DestroyResource` akzeptiert nur Buffer, Shader Module, Descriptor Set Layout, Pipeline Layout und Pipeline; es weist Fence, Semaphore, Device, Pools, Command Buffer, Descriptor Set und Memory mit `BadMatch` ab. Fence und Semaphore werden ausschließlich über `DestroyFence` beziehungsweise `DestroySemaphore` zerstört
- `DestroyResource` hat exakt 12 Bytes und inferiert Device/Ownership aus der Ressource; fremde Ownership und abgewiesene Recording-/Pending-Zustände ändern keine XID oder Referenz
- Erfolgreiches `DestroyResource` invalidiert die öffentliche XID sofort, erhält interne Objekte aber bis zum Ende notwendiger Referenzen und Backend-Zugriffe
- Destroy einer von einem `RECORDING`-Command-Buffer referenzierten Ressource wird atomar abgewiesen.
- Destroy einer von einem nicht-pending `EXECUTABLE`-Command-Buffer referenzierten Ressource invalidiert diesen Command Buffer.
- `DestroyCommandPool`, `DestroyDescriptorPool` und `FreeDescriptorSets` werden bei verbotener Pending-/Recording-Referenz atomar abgewiesen; erfolgreiche Kaskaden invalidieren alle betroffenen XIDs.
- `DestroyDescriptorPool` hat exakt 16 Bytes; es invalidiert Pool und Kind-Sets atomar und setzt referenzierende nicht-pending `EXECUTABLE`-Command-Buffer auf `INVALID`.
- `DestroyResource` auf einen Buffer wird während Pending-Use abgewiesen; nach erfolgreicher Zerstörung verhindern stale Descriptor-Slots eine neue Submission, bis sie aktualisiert oder freigegeben werden.
- `FreeMemory` ist ein eigener Void-Request mit exakt 16 Bytes; bei gebundenem Buffer ergibt er `BadMatch`; bei pending GPU-Zugriff `INVALID_SYNCHRONIZATION_STATE`; bei Ablehnung bleibt die Memory-XID live und die Allokation unverändert.
- Device Loss macht alle angenommenen nicht-terminalen Submissions fehlgeschlagen, setzt zugehörige Fences auf `FAILED`, invalidiert betroffene Command Buffer nach der Pending-Phase und erzeugt keine erfolgreiche Completion.
- Wenn Backend-Quieszenz nach Device Loss nicht nachweisbar ist, werden interne Ressourcen quarantänisiert und weder freigegeben noch wiederverwendet, bis Quieszenz nachgewiesen oder der Serverprozess beendet ist.
- XID-Wiederverwendung bei ausstehender Arbeit
- Device Removal und Device Loss
- Korrekte XGE-Längen und Event-Feldpositionen
- Die XAverius-Major-Opcode wird pro X11-Server mit `QueryExtension` entdeckt, liegt im X11-Erweiterungsbereich 128–255 und wird sowohl als Request-`reqType` als auch als XGE-`extension` verwendet; `evtype` bleibt die statische Event-Type-ID. XGE-Headerlängen, feste Event-Gesamtlängen, reservierte Header-/Payload-Felder und registrierte Event-lokale Werte werden unabhängig validiert.
- Keine verspäteten X11-Fehler für angenommene asynchrone Requests
- Ein terminaler interner Submission-Ausgang auch dann, wenn das zugehörige Event nicht ausgewählt ist; bei ausgewähltem Event genau eine Zustellung des passenden Completion- oder Failure-Events
- Erfolgreiches `WriteBuffer` wartet auf alle zuvor angenommenen Submissions desselben logischen Devices, bevor es den Zielbereich verändert; dies gilt auch bei früherer Arbeit auf einer anderen Queue und bei überlappenden Buffer-Bereichen
- Jede nach erfolgreichem `WriteBuffer` angenommene Submission auf jeder Queue desselben logischen Devices sieht die hochgeladenen Bytes, ohne clientseitige Semaphore oder Barrieren allein für diese Sichtbarkeit
- Ein vorheriger fehlgeschlagener Submission-Ausgang verhindert `WriteBuffer` nicht, sofern das Device weiter verwendbar ist; der Upload erfolgt danach und spätere Submissions sehen die neuen Bytes
- Bei Device Loss oder fehlgeschlagenem Transfer sendet `WriteBuffer` keinen erfolgreichen Reply
- Ein früherer QueueSubmit wartet auf ein Timeline-Signal, das erst durch einen späteren `SignalSemaphore`-Request derselben Verbindung geliefert wird: `WriteBuffer` darf den Dispatcher nicht deadlocken; das Signal wird ausgeführt, die frühere Submission kann terminal werden, und spätere `QueueSubmit`-Requests passieren die Upload-Grenze erst nach erfolgreichem Reply
- `WriteBuffer` auf einem logischen Device erzeugt keine implizite Synchronisation mit einem anderen logischen Device auf derselben physischen GPU
- `ReadBuffer` wartet auf alle zuvor angenommenen Submissions desselben logischen Devices und auf relevante vorherige `WriteBuffer`-Transfers
- Readback-Ergebnisse werden nicht als korrekt vorausgesetzt, wenn fehlgeschlagene frühere GPU-Arbeit den gelesenen Bereich hätte verändern können
- Korrekte Berechnung von `C[i] = A[i] + B[i]`

- SelectEvents uses subopcode 40 and an exact total length of 32 bytes.
- SelectEvents rejects unknown scope values, reserved nonzero fields, unsupported mask bits, and inconsistent scope fields; rejection preserves the previous selection.
- A zero event mask clears only the selected scope; unmaskable ASYNC_ERROR and DEVICE_LOST delivery is independent of the selection.

- SelectEvents CONNECTION requires all target fields to be zero; DEVICE requires zero queue indices; QUEUE identifies a requested queue by device XID and family/index tuple.
- SelectEvents rejects a queue tuple that does not identify a requested queue, and rejects resources owned by another client without changing the previous mask.
- A closed client connection or failed event send does not prevent an accepted submission from reaching its internal terminal state or releasing safe backend resources.

- CreateDevice, CreateDefaultDevice, and SelectEvents before successful GEQueryVersion negotiation are rejected with BadMatch; no target XID or event-mask change is left behind.
- After XGE 1.0 negotiation, long XAverius XGE events are framed with GenericEvent (35), the XAverius major opcode in extension, and the registered CARD16 evtype.
- Property UUID byte preservation: a server returns the exact 16 bytes supplied by Vulkan for `deviceUUID` and `driverUUID`, without integer reinterpretation or host-endian conversion.
- Extension-name syntax: empty names, names longer than 255 bytes, non-ASCII bytes, embedded NUL bytes, and names that do not match the required Vulkan extension-name form are rejected with `BadValue` before registry lookup; syntactically valid names absent from the v0.1 registry produce `BadMatch`.
- `CreateDevice` validation order: malformed packet structure and reserved fields are rejected before resource lookup; feature and extension records are checked for syntax, duplicates, registry membership, and Physical Device support before any logical Device or backend object is published.
- `GetPhysicalDeviceProperty` successful replies use the exact registry type and length; UUID properties contain exactly 16 opaque bytes, `maxWorkGroupInvocations` exactly one `CARD32`, and `maxWorkGroupSize` exactly three `CARD32` values; all padding is zero.
- Feature-ID and device-extension registries are empty in v0.1: every feature ID is `BadValue`; malformed extension names are `BadValue`; any syntactically valid extension name is `BadMatch`; failures leave `device_xid` unallocated.
- Extension-name syntax tests include mixed-case extension suffixes (for example `VK_EXT_shaderObject`) and preserve the exact spelling; the syntax check must not incorrectly require the suffix to be lowercase.
- `spec/errors.md` is checked against all 40 assigned request subopcodes: every request uses the common framing/XID/ownership/atomicity rules where applicable, with request-specific length, value, state, backend, and synchronous-versus-asynchronous outcomes taking precedence when explicitly defined.
- Error precedence tests verify malformed length/record structure before field validation, field validation before XID resolution, and XID/type/ownership validation before state/backend checks; no rejected Void request leaves a partial resource or state change.

## Queue-Reihenfolge und Fortschritt

- Submissions derselben Queue werden in der Annahmereihenfolge eingereiht; unabhängige Arbeit darf sich überlappen.
- Zwischen verschiedenen Queues besteht ohne explizite Synchronisation keine zugesicherte Reihenfolge oder Memory-Visibility.
- Queueübergreifende Abhängigkeiten werden mit Semaphore-Signal und -Wait hergestellt. Erforderliche Memory-Dependencies werden separat nach Vulkan-Regeln geprüft.
- Fence-Waits und Host-Semaphore-Waits beobachten Zustände, erzeugen aber selbst keine Queue-seitige Abhängigkeit.
- Ein Host-Signal kann einen Queue-Wait auf denselben Semaphore-Wert freigeben, ordnet aber keine unverbundene GPU-Arbeit.
- Submission-Tokens und Event-Sequence-Nummern sind keine Ordnungswerte.
- Für unabhängige Queues sind weder Fairness noch eine feste maximale Scheduling-Latenz zugesichert.

## XGE- und Reply-ABI

- Jeder XAverius-XGE-Event-Header ist genau 32 Bytes groß: `response_type = 35`, `extension` ist der ausgehandelte XAverius-Major-Opcode, `sequence` liegt bei Offset 2, `length` bei Offset 4 und `evtype` bei Offset 8; Header-Padding bei Offset 10–31 ist null.
- XGE-Längen werden als `32 + 4 * length` geprüft: `ASYNC_ERROR` 60 Bytes/length 7; `DEVICE_LOST`, `DEVICE_STATUS_CHANGED`, `DEVICE_MEMORY_PRESSURE` und `DEVICE_IDLE` je 48 Bytes/length 4; `SUBMISSION_COMPLETE` und `SUBMISSION_FAILED` je 56 Bytes/length 6.
- Event-`evtype`-Werte stimmen exakt mit der Event-Registry überein (0–6); der dynamische Extension-Major-Opcode wird nicht als Event-Type-ID verwendet.
- Die event-spezifischen Felder beginnen bei Offset 32. Alle als reserviert definierten Felder sind null; `SUBMISSION_COMPLETE` und `SUBMISSION_FAILED` unterscheiden sich bei Offset 44 (reserviert null bzw. `failure_class`) und dürfen für dieselbe angenommene Submission nicht beide als terminales Event auftreten.
- `SelectEvents` hat exakt 32 Bytes, Subopcode 40, null Flags/reservierte Felder und Scope-spezifische Felder bei Offset 8–31. Der Event-Maskenwert wird anhand des Scopes validiert; Fehler ändern die vorherige Auswahl nicht.
- Feste Replies sind 32 Bytes mit `reply.length = 0`, sofern keine Payload über Offset 32 hinausgeht. Bei variabler Payload bezeichnet `reply.length` ausschließlich die gepaddeten Vierbyteeinheiten nach Offset 32; Payload-Bytes und Null-Padding werden getrennt geprüft.
- `GetFenceStatus` legt den Fence-Status in Reply-Byte 1 ab; Offset 0 bleibt `response_type`, Offsets 2–3 Sequenznummer und Offsets 4–7 `reply.length = 0`. Die restlichen XAverius-reservierten Bytes sind null.

## Automatisierter Wire-Layout-Check

Im Repository-Root ausführen:

```sh
python3 -m py_compile tools/check-wire-layout.py
python3 tools/check-wire-layout.py
```

Der Checker verwendet nur die Python-Standardbibliothek. Er prüft die sieben registrierten XGE-Event-IDs und -Längen, extrahiert die Event-Felder aus den Layoutbeschreibungen und meldet Überlappungen, Lücken, unzulässige Offsets/Ausrichtung, Felder außerhalb der Eventlänge sowie nicht explizit auf null gesetzte reservierte Felder. Für Replies vergleicht er das 40-Request-Inventar und die Längenmatrix mit dem Subopcode-Register und prüft zentrale feste Reply-Felder sowie variable `reply.length`-Formeln in den normativen Kapiteln. GitHub Actions führt den Check bei Änderungen auf dem Arbeitsbranch und bei Pull Requests aus.

Der Check ist eine statische Dokumentations-Konsistenzprüfung. Er ersetzt weder Tests gegen einen laufenden X11/XGE-Server noch Backend-/Vulkan-Konformitätstests.

### Reply-ABI-Abdeckung des statischen Prüfers

Der Wire-Layout-Check muss alle elf als `Reply` registrierten Requests abdecken: `EnumeratePhysicalDevices`, `GetPhysicalDeviceProperty`, `GetPhysicalDeviceQueueFamilyProperties`, `GetPhysicalDeviceMemoryProperties`, `GetBufferMemoryRequirements`, `WriteBuffer`, `ReadBuffer`, `GetSemaphoreCounterValue`, `WaitSemaphores`, `GetFenceStatus` und `WaitForFence`. Die Prüfliste wird mit den `Reply`-Einträgen im zentralen Subopcode-Register verglichen; fehlt ein registrierter Reply oder ein erwarteter Vertrag, schlägt der Check fehl.

Zusätzlich zu festen Reply-Feldern prüft er jetzt die variablen Record- und Payload-Verträge: `PHYSICALDEVICEINFO`-Records einschließlich Namenslänge und Padding, `QUEUEFAMILYINFO`-Records, `MEMORYTYPEINFO`/`MEMORYHEAPINFO`-Größen und -Counts, Property-Werte, `ReadBuffer`-Payloads sowie den variablen Request-/Reply-Vertrag von `WriteBuffer` und `WaitSemaphores`. Der Check ist absichtlich eine normative Text-Konsistenzprüfung; er führt keine Server- oder Vulkan-Operation aus.

Die Formeltests enthalten zusätzlich Grenzwertvektoren für Byte-Padding und Reply-Wörter bei Payload-Längen 0, 1, 3, 4 und 5; für `PHYSICALDEVICEINFO`-Namenslängen 0, 1, 4 und 5; für leere und nichtleere Queue-Family-Arrays; sowie für Memory-Type-/Heap-Counts einschließlich der v0.1-Maxima 32/16. Für `WriteBuffer` und `WaitSemaphores` werden variable Request-Längen ebenfalls anhand konkreter Count-/Payload-Vektoren geprüft.

## Golden-Wire-Testvektoren

`tests/wire-vectors.json` enthält konkrete Request-Bytes für `CreateBuffer`, `WriteBuffer` und `ReadBuffer`, jeweils in Little- und Big-Endian-Byteordnung. Die `WriteBuffer`-Vektoren decken Payload-Längen 1, 3, 4 und 5 Bytes ab und prüfen damit Padding von 3, 1, 0 und 3 Bytes. Die Fixtures prüfen den 8-Byte-Request-Header, das Null-`data`-Feld, den Subopcode am Offset 4, die vierbytebasierte Request-Länge und die festen Feldlayouts. Zusätzliche Raw-Frame-Tests weisen abgeschnittene Header, falsche deklarierte Längen und nicht-nullige reservierte Headerbytes zurück. Der Major-Opcode `0x90` ist nur ein Fixture-Wert; im Betrieb wird er vom X-Server zugewiesen.

Mit `python3 -m unittest discover -s tests -p 'test_*.py' -v` werden die Golden-Bytes gegen einen kleinen Referenz-Encoder geprüft. Der Referenz-Encoder ist kein XAverius-Client und keine Serverimplementierung: Die Tests belegen die Konsistenz der Vektoren und der abgedeckten Wire-Regeln, nicht die Interoperabilität. Sobald ein Client- oder Server-Encoder existiert, muss derselbe Vektorsatz direkt gegen dessen erzeugte beziehungsweise geparste Bytes laufen. Die Negativtests weisen außerdem abweichende deklarierte Paketlängen, nicht-nulliges WriteBuffer-Padding, inkonsistente Payload-Längen und nicht-nullige reservierte CreateBuffer-Felder zurück. Diese Tests prüfen die Ablehnungslogik des Referenz-Encoders; sie sind ausdrücklich noch kein Nachweis, dass ein Server dieselben fehlerhaften Pakete korrekt zurückweist.
