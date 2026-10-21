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
- `CreateDevice`-Länge entspricht exakt den drei geordneten variablen Record-Arrays; mindestens eine Queue-Family-Anforderung ist erforderlich; Queue-Prioritäten müssen endlich und in [0,1] liegen; unbekannte Feature-IDs, `enabled != 1`, doppelte Features/Extensions und syntaktisch ungültige Extension-Namen ergeben `BadValue`; registrierte, aber nicht unterstützte Features sowie unbekannte oder nicht unterstützte syntaktisch gültige Extensions ergeben `BadMatch`; jeder Fehler lässt die Create-XID unangelegt; `CreateDevice` und `CreateDefaultDevice` senden bei Erfolg keinen Reply
- `GetPhysicalDeviceMemoryProperties` liefert Memory-Type-/Heap-Indizes, die über die Lebensdauer der Physical-Device-XID stabil bleiben
- `CreateBuffer` weist `usage_flags = 0` und unbekannte Usage-Bits mit `BadValue` ab
- `CreateDescriptorPool`, `AllocateDescriptorSets` und `FreeDescriptorSets` weisen Count null mit `BadValue` ab
- Alle Create-Ziel-XIDs werden getrennt von Eingabe-XIDs geprüft: ungültige/belegte Ziel-XIDs ergeben `BadIDChoice`; Batch-Erzeugung hinterlässt bei Kollision keine Teilmenge
- `ShaderModuleData` ohne passendes Upload-Assembly und `CommandBufferData` ohne passenden `RECORDING`-Buffer werden mit `INVALID_SYNCHRONIZATION_STATE` abgewiesen; CREATE-XID-Kollisionen ergeben `BadIDChoice`
- `CreateDevice` weist null Queue-Family-Records, null Queue-Anzahl und doppelte Queue-Family-Records mit `BadValue` ab; eine nicht unterstützte Queue-Anzahl ergibt `BadMatch`
- Doppelte Pool-Size-Typen, doppelte Descriptor-Updates desselben Slots, doppelte Wait-/Signal-Entries sowie eine Semaphore zugleich in Wait und Signal werden gemäß den Fehlerregeln atomar abgewiesen
- `CreateComputePipeline` verwendet die normative Länge `28 + ((entry_point_length + 3) & ~3)` und prüft nichtleeren ASCII-Entry-Point sowie Null-Padding
- `DestroySemaphore` und `DestroyFence` sind jeweils 16-Byte-Void-Requests; `WaitSemaphores` verwendet `28 + 12 * semaphore_count`
- `GetFenceStatus` ist ein 16-Byte-Reply-Request mit Fence-Status in Reply-Byte 1, `reply.length = 0` und null reservierten XAverius-Bytes in Offsets 8–31
- `CommandBufferData`-ABORT hat exakt 16 Bytes; andere Chunks enthalten nur vollständige Entries
- `QueueSubmit`-Länge stimmt exakt mit `40 + 4*C + 16*W + 12*S` überein; Null- und wiederverwendete Submission-Tokens ergeben `BadValue`; Counts/Längenüberlauf ergeben `BadLength`; fremde Ownership/Queue ergeben `BadMatch`; ungültige Zustände ergeben `INVALID_SYNCHRONIZATION_STATE`; synchron abgewiesene Requests erzeugen kein Submission-Event
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
- Die zentrale Request-Registry enthält genau 39 eindeutige, explizit vergebene Subopcodes (1–39); Subopcode 0 ist reserviert, kein Wert ist doppelt vergeben, und spätere Requests dürfen bestehende Werte nicht verschieben oder wiederverwenden
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
