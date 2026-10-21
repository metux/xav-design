# Errors and error mapping

Error codes are offsets relative to the X11 extension's `first_error` value. The absolute X11 error code is `first_error + offset`; implementations must use the central values in [the error registry](../registries/errors.md), not allocate values ad hoc.

XAverius errors use the standard 32-byte X11 error packet and add no XAverius-specific payload bytes. The packet carries the extension major opcode and the sequence number of the request that caused the error. The resource field identifies the affected resource when meaningful; otherwise it is zero. For v0.1, the X11 request-header `data` byte MUST be zero; XAverius `subopcode` is carried at offset 4, and the error packet's `minorCode` is the zero-extended `subopcode`. The error packet's `majorCode` is the extension major opcode.

## Allgemeine Fehlerklassen

| Situation | Ergebnis |
|---|---|
| Request-Länge oder Count inkonsistent | `BadLength` |
| Ungültiger Feldwert, reservierte Bits oder Flags | `BadValue` |
| Ungültige oder bereits belegte Create-XID | `BadIDChoice` |
| Falscher Ressourcentyp oder Cross-Device-Kombination | normalerweise `BadMatch` |
| XID bezeichnet keine live XAverius-Ressource oder ist in diesem Ressourcen-Kontext unbekannt | `BadValue` |
| Atom-XID ist ungültig | `BadAtom` |
| Live-XID hat einen anderen Ressourcentyp als erwartet | `BadMatch` |
| Live-Ressource gehört einem anderen Client, obwohl kein Sharing-Pfad definiert ist | `BadMatch` |
| Device nicht verfügbar | `DEVICE_UNAVAILABLE` |
| Device verloren | `DEVICE_LOST` |
| Ungültiger Synchronisationszustand | `INVALID_SYNCHRONIZATION_STATE` |
| Synchroner Transferfehler | `TRANSFER_FAILED` |
| Synchroner Allokationsfehler | `ALLOCATION_FAILED` |
| Ungültige Abhängigkeit verhindert Annahme | `DEPENDENCY_FAILED` |
| Unerwarteter Serverfehler | `INTERNAL_SERVER_ERROR` |

## Verbindliche XID-Fehlerregel

Für alle XAverius-Requests gilt dieselbe Grundzuordnung, sofern ein Request keine ausdrücklich engere Regel definiert:

- Eine erforderliche XAverius-XID, die keine live Ressource im XAverius-Ressourcenraum bezeichnet, ergibt `BadValue`. Das umfasst unbekannte, bereits zerstörte und nicht mehr öffentliche XIDs. XAverius-Ressourcen verwenden eigene Extension-Ressourcentypen; es gibt daher keinen passenden Core-Fehler wie `BadWindow` oder `BadPixmap`.
- Eine XID, die eine live Ressource bezeichnet, aber nicht den erwarteten Ressourcentyp hat, ergibt `BadMatch`.
- Eine live Ressource, die einem anderen Client gehört und für die kein expliziter Sharing-Pfad definiert ist, ergibt `BadMatch`. Dasselbe gilt für Cross-Device-Verwendung.
- Ein ungültiger `ATOM`-Wert ergibt `BadAtom`, nicht `BadValue`.
- Eine Create-XID, die ungültig ist oder bereits belegt ist, ergibt `BadIDChoice`; dies ist von einer ungültigen Eingabe-XID zu unterscheiden.
- Für serverseitig vergebene Physical-Device-XIDs gilt ebenfalls `BadValue`, wenn die XID unbekannt oder nicht mehr gültig ist; ein falscher live Ressourcentyp ergibt `BadMatch`.

Diese Zuordnung gilt auch dann, wenn der Request mehrere XIDs enthält: Der Server prüft die Wire-Struktur zuerst, danach Feldwerte und anschließend XIDs in der im jeweiligen Request-Kapitel festgelegten Feldreihenfolge. Die erste fehlerhafte XID bestimmt den gemeldeten Ressourcenfehler. Der Request bleibt atomar.

### Create-XID und chunk-basierte Erzeugung

Die Ziel-XID eines Create-Requests ist keine Eingabe-XID, die als vorhandene Ressource aufgelöst wird. Eine ungültige oder bereits belegte Ziel-XID ergibt deshalb `BadIDChoice`; sie darf nicht als gewöhnliche unbekannte Eingabe-XID mit `BadValue` behandelt werden. Bei atomaren Batch-Erzeugungen wird der gesamte Request abgewiesen, wenn eine Ziel-XID ungültig, bereits belegt oder innerhalb desselben Requests doppelt angegeben ist; es bleibt keine Teilmenge live.

Diese Regel gilt insbesondere für die Ziel-XIDs von `CreatePipelineLayout`, `CreateComputePipeline` und die in `AllocateDescriptorSets` angeforderten Descriptor Sets. Für `ShaderModuleData` und `CommandBufferData` gilt sie, wenn das `CREATE`-Flag gesetzt ist. Bei `ShaderModuleData` reserviert ein erfolgreicher CREATE-Chunk die Ziel-XID für das Upload-Assembly; ein zweites CREATE oder eine bereits live belegte Ziel-XID ergibt `BadIDChoice`.

Bei `ShaderModuleData` ohne `CREATE` muss ein passendes Upload-Assembly existieren. Ist die XID eine live Ressource eines anderen Typs, gilt `BadMatch`; andernfalls ergibt ein fehlendes Assembly `INVALID_SYNCHRONIZATION_STATE`, auch wenn noch kein öffentliches Shader-Module-Objekt existiert. Bei `CommandBufferData` ohne `CREATE` muss die Ziel-XID einen live Command Buffer bezeichnen: unbekannte/nicht-live XIDs ergeben `BadValue`, ein falscher live Ressourcentyp `BadMatch`, und ein Command Buffer außerhalb von `RECORDING` ergibt `INVALID_SYNCHRONIZATION_STATE`. Alle Prüfungen erfolgen vor einer Zustandsänderung.


## `CreateDevice`: Feature- und Extension-Anforderungen

Die Fehlerzuordnung unterscheidet fehlerhafte Eingaben von gültigen, aber nicht erfüllbaren Anforderungen:

- `feature_id` ist nicht in der XAverius-Feature-Registry definiert: `BadValue`.
- `feature_id` ist registriert, wird aber vom ausgewählten Physical Device nicht unterstützt: `BadMatch`.
- Feature-Record mit `enabled != 1` oder doppelte Feature-ID: `BadValue`.
- Extension-Name ist leer, enthält Nicht-ASCII-/NUL-Bytes oder verletzt das registrierte Wire-Namensformat: `BadValue`.
- Extension-Name ist syntaktisch gültig, aber unbekannt in der XAverius-Extension-Registry oder vom Physical Device nicht unterstützt: `BadMatch`.
- Doppelte Extension-Namen: `BadValue`.
- Alle Anforderungen müssen vor der Device-Erzeugung geprüft werden. Bei jedem Fehler bleibt die angeforderte `device_xid` unangelegt; der Server darf Features oder Extensions nicht stillschweigend auslassen.

## Request-spezifische Fehlerzuordnung

### `WriteBuffer`

- Falsche Request-Länge: `BadLength`
- Länge null oder ungültige reservierte Felder: `BadValue`
- Unbekannte/nicht-live XAverius-XID: `BadValue`
- Falscher Typ, falsches Device, ungebundener Buffer, fehlendes `TRANSFER_DST`, Bereich außerhalb des Buffers: `BadMatch`
- Nicht verfügbares/verlorenes Device: `DEVICE_UNAVAILABLE` / `DEVICE_LOST`
- Synchroner Transferfehler: `TRANSFER_FAILED`
- Fehlgeschlagene Staging-Allokation: `ALLOCATION_FAILED`

### `ReadBuffer`

- Falsche Request-Länge: `BadLength`
- Länge null oder ungültige reservierte Felder: `BadValue`
- Unbekannte/nicht-live XAverius-XID: `BadValue`
- Falscher Typ, falsches Device, ungebundener Buffer, fehlendes `TRANSFER_SRC`, ungültiger Bereich: `BadMatch`
- Nicht verfügbares/verlorenes Device: `DEVICE_UNAVAILABLE` / `DEVICE_LOST`
- Synchroner Transferfehler: `TRANSFER_FAILED`
- Fehlgeschlagene Staging-Allokation: `ALLOCATION_FAILED`

### `ShaderModuleData`

- Falsche Request-Länge oder unpassender Payload-Umfang: `BadLength`
- Null `data_length` bei einem Datenchunk, nicht-null `data_length` bei ABORT, nicht-null Padding oder ungültige Flag-Kombination: `BadValue`
- Ungültige/nicht-live `device_xid`: `BadValue`; falscher live Device-Typ: `BadMatch`. Bei `CREATE` ergibt eine ungültige/belegte `shader_module_xid` `BadIDChoice`. Ohne `CREATE` erfordert der Request ein passendes Upload-Assembly; fehlt es, ergibt sich `INVALID_SYNCHRONIZATION_STATE`.
- `ABORT` ohne passendes laufendes Upload-Assembly: `INVALID_SYNCHRONIZATION_STATE`
- Ungültiges SPIR-V oder ein SPIR-V-Modul, das die v0.1-Validierungsregeln nicht erfüllt: `BadValue`; kein Shader Module bleibt live und das Assembly wird verworfen
- Fehler bei der Vulkan-Erstellung: konkreter Backendfehler wie `DEVICE_LOST`, `ALLOCATION_FAILED` oder `INTERNAL_SERVER_ERROR`; kein Shader Module bleibt live und das Assembly wird verworfen
- Ein fehlerhafter Chunk verwirft das gesamte zugehörige Assembly. Ein späterer X11-Fehler für diesen Chunk ist synchron und hinterlässt kein partielles Shader Module.

### Device-Discovery und Device-Erstellung

- `EnumeratePhysicalDevices`: Request muss exakt 8 Bytes lang sein; die Reply-Payload besteht ausschließlich aus vollständigen `PHYSICALDEVICEINFO`-Records. Ein unvollständiger Record darf nicht ausgegeben werden.
- `GetPhysicalDeviceProperty`: falsche Request-Länge `BadLength`; ungültiges Atom `BadAtom`; unbekannte/nicht-live Device-XID `BadValue`; bei Status ungleich `SUCCESS` müssen `property_type`, `value_length` und Reply-Payload null sein.
- `GetPhysicalDeviceQueueFamilyProperties` und `GetPhysicalDeviceMemoryProperties`: Request-Länge exakt 12 Bytes; unbekannte/nicht-live Physical-Device-XID `BadValue`.
- `CreateDevice`: falsche Länge `BadLength`; `queue_family_request_count = 0`, `queue_count = 0`, doppelte Queue-Family-Records, nicht-null reserviertes Feld, ungültige Priorität, `enabled` ungleich 1, doppelte Feature-/Extension-Einträge, unbekannte Feature-ID oder formal ungültiger Extension-Name `BadValue`; ungültige/belegte `device_xid` `BadIDChoice`; unbekannte/nicht-live Physical-Device-XID `BadValue`; falscher live Ressourcentyp, Queue-Family-Anforderung mit nicht verfügbarer oder nicht unterstützter Queue-Anzahl, registriertes aber nicht unterstütztes Feature, unbekannte oder nicht unterstützte formal gültige Extension oder Cross-Device-Zugriff `BadMatch`; ein nicht verfügbares Physical Device `DEVICE_UNAVAILABLE`. Die Prüfung ist atomar und veröffentlicht kein logisches Device bei Fehler.
- `CreateDefaultDevice`: falsche Länge `BadLength`; Count null, nicht-null reserviertes Feld oder ungültige Priorität `BadValue`; ungültige/belegte `device_xid` `BadIDChoice`; kein geeignetes Gerät `DEVICE_UNAVAILABLE`.
- Beide Requests sind Void-Requests; Erfolg erzeugt keinen normalen Reply.
- `DestroyDevice`: falsche Länge `BadLength`; unbekannte/nicht-live XAverius-XID `BadValue`; fremde Device-Ownership `BadMatch`.

### `CreateDescriptorSetLayout`

- Falsche Request-Länge oder ein nicht zum `binding_count` passender Payload: `BadLength`
- Nicht-null `flags`, reservierte/ungültige Feldwerte, unbekannte oder nicht unterstützte Stage-Bits, nicht unterstützter Descriptor-Typ oder ungültige Binding-Records: `BadValue`
- Ungültige oder bereits belegte Create-XID: `BadIDChoice`
- Ungültiges Device-XID: `BadValue` für eine unbekannte/nicht-live XAverius-XID; Cross-Device-Ressource: `BadMatch`
- Jeder Fehler lässt das Descriptor Set Layout unangelegt; Teilresultate sind unzulässig.

### `CommandPool` und `CommandBufferData`

- Falsche Request-Länge oder unvollständiger Entry: `BadLength`
- Reservierte Bits/Felder, ungültige Flag-Kombination, fehlerhaftes Padding oder ungültige Entry-Länge: `BadValue`
- Falscher live Ressourcentyp, ungültiger Queue-Family-Index oder Cross-Device-Objekt: `BadMatch`; ein ungültiger/belegter Command-Buffer-Ziel-XID bei `CREATE` ergibt `BadIDChoice`. Ohne `CREATE` muss der Buffer im Zustand `RECORDING` sein, sonst `INVALID_SYNCHRONIZATION_STATE`.
- ABORT bei einem Buffer, der nicht `RECORDING` ist, oder bei einem pending Buffer: `INVALID_SYNCHRONIZATION_STATE`
- `ResetCommandBuffer` ohne `RESET_COMMAND_BUFFER`-Pool-Flag oder bei einem pending Buffer: `INVALID_SYNCHRONIZATION_STATE`; Ablehnung lässt Zustand und Ressourcenreferenzen unverändert
- `ResetCommandBuffer` mit unbekannter/nicht-live XID: `BadValue`; falscher live Ressourcentyp oder Cross-Device-Verwendung: `BadMatch`
- Fehlerhafte Entries eines `CommandBufferData`-Chunks werden atomar abgewiesen; der aktuelle Chunk wird nicht teilweise angehängt. Bereits vorher akzeptierte Chunks bleiben bis zu einem erfolgreichen Retry oder ABORT erhalten.

### Einheitliche XID- und Zustandszuordnung für ausgewählte Requests

Die Prüfung erfolgt in dieser Reihenfolge: Wire-Länge und strukturelle Integrität; Feldwerte und reservierte Felder; Auflösung jeder erforderlichen XID; Ressourcentyp und Ownership; request-spezifische Zustands- und Backend-Prüfungen. Ein Fehler beendet den Request ohne Teiländerungen. Ein als `0` definierter optionaler XID-Wert wird nicht aufgelöst.

| Request / Bedingung | Fehler |
|---|---|
| `DestroyResource`: falsche Länge | `BadLength` |
| `DestroyResource`: XID löst keine live Ressource auf | `BadValue` für unbekannte/nicht-live XIDs; `BadMatch` für einen falschen live Ressourcentyp |
| `DestroyResource`: Ressourcentyp ist nicht für den generischen Request zugelassen oder Ressource gehört einem anderen Client | `BadMatch` |
| `DestroyResource`: Ressource wird von einem `RECORDING`-Command-Buffer referenziert oder ihre typabhängige Pending-Regel verbietet die Zerstörung | `INVALID_SYNCHRONIZATION_STATE` |
| `BindBufferMemory`: falsche Länge | `BadLength` |
| `BindBufferMemory`: ungültige Feldwerte oder nicht-null reservierte Felder, sofern vorhanden | `BadValue` |
| `BindBufferMemory`: Device-, Buffer- oder Memory-XID ist ungültig/nicht live | `BadValue` für unbekannte/nicht-live XIDs; `BadMatch` für einen falschen live Ressourcentyp |
| `BindBufferMemory`: falscher Ressourcentyp, Client-/Device-Ownership passt nicht, Buffer bereits gebunden, Memory-Type nicht erlaubt, Alignment falsch oder Allocation zu klein | `BadMatch` |
| `BindBufferMemory`: Device ist nicht verfügbar/verloren | `DEVICE_UNAVAILABLE` / `DEVICE_LOST` |
| `UpdateDescriptorSets`: falsche Gesamtlänge oder Payload passt nicht zu `write_count` | `BadLength` |
| `UpdateDescriptorSets`: `write_count = 0`, reservierte Felder ungleich null oder ungültige Werte/Flags | `BadValue` |
| `UpdateDescriptorSets`: ungültige/nicht-live Device-, Set- oder Buffer-XID | `BadValue` für unbekannte/nicht-live XIDs; `BadMatch` für einen falschen live Ressourcentyp |
| `UpdateDescriptorSets`: falscher Typ, fremde Client-/Device-Ownership, Layout/Binding/Array-Slot/Descriptor-Typ inkompatibel, Buffer ungebunden oder Bereich/Alignment ungültig | `BadMatch` |
| `UpdateDescriptorSets`: betroffenes Set wird von angenommener Arbeit verwendet | `INVALID_SYNCHRONIZATION_STATE` |
| `UpdateDescriptorSets`: Device ist nicht verfügbar/verloren | `DEVICE_UNAVAILABLE` / `DEVICE_LOST` |
| `QueueSubmit`: falsche Länge, inkonsistente Counts oder Längenberechnung läuft über | `BadLength` |
| `QueueSubmit`: Token ist null oder auf derselben Verbindung bereits verwendet; reservierte Felder, ungültige Masks oder numerische Werte | `BadValue` |
| `QueueSubmit`: Device-, Command-Buffer-, Semaphore- oder nicht-null Fence-XID ungültig/nicht live | `BadValue` für unbekannte/nicht-live XIDs; `BadMatch` für einen falschen live Ressourcentyp |
| `QueueSubmit`: falscher Ressourcentyp, fremde Client-/Device-Ownership oder angegebene Queue wurde nicht für dieses Device erstellt | `BadMatch` |
| `QueueSubmit`: Command Buffer nicht `EXECUTABLE`, Fence nicht submitbar, Semaphore-Zustand unzulässig oder Wait-Stage-Mask ungültig für die Queue | `INVALID_SYNCHRONIZATION_STATE` |
| `QueueSubmit`: Abhängigkeit verhindert die Annahme, ohne dass eine speziellere Zustandsregel greift | `DEPENDENCY_FAILED` |
| `QueueSubmit`: Device nicht verfügbar/verloren | `DEVICE_UNAVAILABLE` / `DEVICE_LOST` |
| `ResetFence`: falsche Länge | `BadLength` |
| `ResetFence`: Device- oder Fence-XID ungültig/nicht live | `BadValue` für unbekannte/nicht-live XIDs; `BadMatch` für einen falschen live Ressourcentyp |
| `ResetFence`: falscher Ressourcentyp oder Fence gehört zu einem anderen Client/Device | `BadMatch` |
| `ResetFence`: Fence ist weder `SIGNALED` noch `FAILED` | `INVALID_SYNCHRONIZATION_STATE` |
| `ResetFence`: Device verloren | `DEVICE_LOST` |

Für alle fünf Requests gilt: Fehler vor Annahme werden synchron als X11-Fehler gemeldet; der Request darf keine Teiländerungen hinterlassen. Nach angenommener `QueueSubmit` werden Ausführungsfehler ausschließlich über die Submission-Terminalereignisse und zugehörige Zustände gemeldet, nicht als nachträglicher X11-Fehler. Ein nicht verfügbarer Zustand wird nur dann gemeldet, wenn der Request tatsächlich weitere Backend-Arbeit benötigt; rein logische Bereinigung nach Device Loss folgt den jeweiligen Lebensdauerregeln.

### Synchronisations-Requests

- `CreateSemaphore`: exakt 28 Bytes; `CreateFence`: exakt 24 Bytes; `DestroySemaphore`, `GetSemaphoreCounterValue`, `DestroyFence`, `GetFenceStatus` und `ResetFence`: exakt 16 Bytes; `SignalSemaphore` und `WaitForFence`: exakt 24 Bytes.
- `WaitSemaphores`: exakt `28 + 12 * semaphore_count` Bytes; Count null oder nicht exakt passende Länge wird abgewiesen (`BadValue` bei null Count, `BadLength` bei Längenabweichung).
- Unbekannte/nicht-live Semaphore-/Fence-XIDs: `BadValue`; falscher Typ oder Device `BadMatch`; unzulässige Zustandsübergänge `INVALID_SYNCHRONIZATION_STATE`.
- `WaitSemaphores` und `WaitForFence` liefern bei Timeout einen normalen Reply-Status und keinen X11-Fehler.

### Fence-Requests

- Falsche Länge: `BadLength`
- Ungültige Flags oder reservierte Felder: `BadValue`
- Unbekannte/nicht-live XAverius-XID: `BadValue`
- Falscher Typ oder Device: `BadMatch`
- Ungültiger Reset-/Destroy-Zustand: `INVALID_SYNCHRONIZATION_STATE`
- Timeout und asynchroner Ausführungsfehler bei `WaitForFence`: normaler Reply-Status

### `DestroyResource`

- Falsche Request-Länge: `BadLength`
- Ungültige oder nicht mehr live XID: `BadValue` für eine unbekannte/nicht-live XAverius-XID
- Ressourcentyp, der nicht für den generischen Request zugelassen ist (insbesondere Fence und Semaphore), oder falsche Ownership: `BadMatch`
- Verstoß gegen die typabhängigen Recording-/Pending-Lebensdauerregeln: `INVALID_SYNCHRONIZATION_STATE`
- Ablehnung lässt XID, interne Lebensdauerzustände und abhängige Command-Buffer-Zustände unverändert.

### Ressourcenzerstörung und Memory-Freigabe

- Destroy einer Ressource, die von einem `RECORDING`-Command-Buffer referenziert wird: `INVALID_SYNCHRONIZATION_STATE`.
- Destroy eines pending Command Buffers, Descriptor Sets, Buffers, einer Pipeline oder eines Pipeline Layouts: `INVALID_SYNCHRONIZATION_STATE`.
- `DestroyCommandPool`: `INVALID_SYNCHRONIZATION_STATE`, wenn mindestens ein Kind-Command-Buffer pending ist.
- `DestroyDescriptorPool` oder `FreeDescriptorSets`: `INVALID_SYNCHRONIZATION_STATE`, wenn ein betroffenes Set pending verwendet oder von einem `RECORDING`-Command-Buffer referenziert wird.
- `DestroyFence`: `INVALID_SYNCHRONIZATION_STATE`, solange die Fence einer nicht-terminalen Submission zugeordnet ist.
- `DestroySemaphore`: `INVALID_SYNCHRONIZATION_STATE`, solange Queue- oder Host-Operationen die Semaphore pending verwenden.
- `FreeMemory`: `BadMatch`, solange ein Buffer an die Allokation gebunden ist; `INVALID_SYNCHRONIZATION_STATE`, solange angenommene Arbeit auf die Allokation zugreift.
- Ein Destroy-Request, der wegen Lebensdauerregeln abgewiesen wird, lässt alle öffentlichen XIDs und Command-Buffer-Zustände unverändert.
- Device-weite Kaskadeninvalidierung ist von diesen normalen Pending-Use-Ablehnungen ausgenommen; interne Referenzen müssen trotzdem sicher erhalten bleiben.

### Buffer- und Memory-Requests

- `CreateBuffer`: falsche feste Länge `BadLength`; nicht-positive Größe, unbekannte Usage-Bits oder nicht-null reservierte Felder `BadValue`; ungültige oder bereits belegte Create-XID `BadIDChoice`; unbekannte/nicht-live Device-XID `BadValue`; fehlgeschlagene Backend-Allokation `ALLOCATION_FAILED`.
- `GetBufferMemoryRequirements`: falsche Länge `BadLength`; unbekannte/nicht-live Buffer-/Device-XID `BadValue`; falscher Ressourcentyp oder Cross-Device-Zugriff `BadMatch`.
- `AllocateMemory`: falsche Länge `BadLength`; ungültige Größe, Memory-Type-Index oder reserviertes Feld `BadValue`; ungültige oder belegte Create-XID `BadIDChoice`; unbekannte/nicht-live Device-XID `BadValue`; fehlgeschlagene Backend-Allokation `ALLOCATION_FAILED`.
- `FreeMemory`: siehe die Lebensdauerregeln unten; bei Ablehnung bleibt die Allokation öffentlich gültig.
- `BindBufferMemory`: siehe die spezifische Zuordnung unten.

### Descriptor-Pool- und Pipeline-Requests

- `CreateDescriptorPool`: falsche Länge oder nicht zum `pool_size_count` passende Payload `BadLength`; ungültige Counts, doppelte Pool-Size-Typen, nicht unterstützte Descriptor-Typen oder nicht-null reservierte Felder `BadValue`; ungültige/belegte Pool-XID `BadIDChoice`; unbekannte/nicht-live Device-XID `BadValue`; Backend-Allokationsfehler `ALLOCATION_FAILED`.
- `AllocateDescriptorSets`: falsche Länge oder unvollständiger Allocation-Entry `BadLength`; Count null oder nicht-null reservierte Felder `BadValue`; ungültige/belegte oder innerhalb des Requests doppelte Ziel-Set-XID `BadIDChoice`; unbekannte/nicht-live Pool-/Layout-Eingabe-XID `BadValue`; falsches Device, falscher Typ oder Layout-/Device-Inkompatibilität `BadMatch`; Pool-Kapazität erschöpft `ALLOCATION_FAILED`. Die Operation ist atomar.
- `FreeDescriptorSets`: falsche Länge `BadLength`; Count null oder nicht-null reservierte Felder `BadValue`; Set gehört nicht zum angegebenen Pool oder Device `BadMatch`; unbekannte/nicht-live XID `BadValue`; pending oder RECORDING-Referenz `INVALID_SYNCHRONIZATION_STATE`. Keine Teilfreigabe bei Ablehnung.
- `CreatePipelineLayout`: falsche Gesamtlänge oder Counts, die nicht zum Payload passen, `BadLength`; nicht unterstützte Stage-Bits, ungültige Push-Constant-Ranges oder nicht-null reservierte Felder `BadValue`; ungültige/belegte `pipeline_layout_xid` `BadIDChoice`; unbekannte/nicht-live Device- oder Set-Layout-XID `BadValue`; falscher live Ressourcentyp oder inkompatibles/fremdes Set-Layout `BadMatch`; Backend-Erstellungsfehler werden als passender XAverius-Fehler gemeldet.
- `CreateComputePipeline`: falsche Länge `BadLength`; leerer Entry-Point, ungültiges Padding oder nicht-null reservierte Felder `BadValue`; ungültige/belegte `pipeline_xid` `BadIDChoice`; unbekannte/nicht-live Shader-/Layout-/Device-Eingabe-XID `BadValue`; falscher live Ressourcentyp, inkompatibles oder gerätefremdes Shader Module beziehungsweise Pipeline Layout `BadMatch`; Backend-Erstellungsfehler werden als passender XAverius-Fehler gemeldet. Kein Pipeline-Objekt bleibt bei Ablehnung live.

### Command-Pool-Requests

- `CreateCommandPool`: falsche Länge `BadLength`; unbekannte Flags oder nicht-null reservierte Felder `BadValue`; ungültige/belegte Pool-XID `BadIDChoice`; ungültige Queue Family oder ungültiges Device `BadMatch` beziehungsweise `BadValue` für eine unbekannte/nicht-live XID.
- `DestroyCommandPool`: falsche Länge `BadLength`; unbekannte/nicht-live XID `BadValue`; falscher Typ oder Cross-Device-Ownership `BadMatch`; mindestens ein pending Kind-Command-Buffer `INVALID_SYNCHRONIZATION_STATE`. Ablehnung ist atomar.

### Synchronisations-Requests

- `CreateSemaphore` und `CreateFence`: falsche Länge `BadLength`; ungültige Typen, Werte, Flags oder reservierte Felder `BadValue`; ungültige/belegte Create-XID `BadIDChoice`; unbekannte/nicht-live Device-XID `BadValue`; Backend-Allokationsfehler `ALLOCATION_FAILED`.
- `GetSemaphoreCounterValue`: nur für Timeline-Semaphoren; falscher Typ `BadMatch`, unbekannte/nicht-live XID `BadValue`.
- `SignalSemaphore`: nur für Timeline-Semaphoren; unbekannte/nicht-live XID `BadValue`; falscher Typ oder Device `BadMatch`; Signalwert, der nicht größer als der aktuelle Counter oder mit pending Signalen inkonsistent ist, `INVALID_SYNCHRONIZATION_STATE`. Bei synchroner Ablehnung wird kein Host-Signal teilweise ausgeführt.
- `WaitSemaphores`: unbekannte/nicht-live XID `BadValue`; falscher live Typ oder falsches Device `BadMatch`; doppelte Semaphore-XID, ungültiger Wait-Modus oder ungültige Werte `BadValue`. `TIMEOUT` ist ausschließlich ein normaler Reply-Status.
- `GetFenceStatus`: unbekannte/nicht-live XID `BadValue`; falscher Typ oder Device `BadMatch`.
- `ResetFence`: nur `SIGNALED` und `FAILED` dürfen zurückgesetzt werden; andere Zustände `INVALID_SYNCHRONIZATION_STATE`. Bei verlorenem Device `DEVICE_LOST`.
- Die verbindliche XID-Zuordnung steht im Abschnitt „Verbindliche XID-Fehlerregel“: unbekannte/nicht-live XAverius-XIDs ergeben `BadValue`, falsche live Ressourcentypen `BadMatch`, ungültige Atoms `BadAtom`.

### `BindBufferMemory`

Die vollständige XID-, Ownership-, Feldwert- und Device-Fehlerzuordnung steht in der einheitlichen Tabelle oben. Cross-Device-Nutzung, bereits gebundener Buffer, ungültiges Alignment, zu kleine Allokation oder inkompatibler Memory-Type ergeben `BadMatch`.

### `UpdateDescriptorSets`

Die vollständige XID-, Ownership-, Feldwert- und Device-Fehlerzuordnung steht in der einheitlichen Tabelle oben. Der Request bleibt bei jedem Fehler atomar.

Jeder Request muss vor Implementierungsfreigabe eine vollständige, konkrete Fehlerzuordnung besitzen.

## Synchron versus asynchron

Ein Fehler vor Annahme wird durch einen X11-Fehler oder den ausdrücklich definierten normalen Fehler-Reply signalisiert. Der Request darf keinen Teilzustand hinterlassen.

Ein Fehler nach Annahme wird durch XAverius-Events und Synchronisationszustände signalisiert. Ein später X11-Fehler für einen bereits angenommenen Request ist unzulässig.
