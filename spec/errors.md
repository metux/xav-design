# Errors and error mapping

Error codes are offsets relative to the X11 extension's `first_error` value. The absolute X11 error code is `first_error + offset`; implementations must use the central values in [the error registry](../registries/errors.md), not allocate values ad hoc.

The error registry's offsets and event-local status values are separate numeric namespaces. In particular, `EXECUTION_FAILED` is error offset 3, while `SUBMISSION_FAILED.failure_class = EXECUTION_FAILED` is the event-local value 0; `WaitForFence` also has its own reply-status value for execution failure. Likewise, `DEVICE_LOST` has error offset 1, while the `WaitForFence` reply status is 3 and the `DEVICE_LOST` event's `reason_code` is a separate enum (for example, `VULKAN_DEVICE_LOST = 3`). Implementations MUST use the value from the field's defining registry, never a same-named value from another namespace.

For an accepted `QueueSubmit`, an execution failure is reported through the submission terminal event and synchronization state, with `ASYNC_ERROR` available for diagnostics. It MUST NOT be reported as a delayed X11 request error. The `EXECUTION_FAILED` error offset is not a substitute for the event-local `failure_class` or `WaitForFence` status.

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
| Logisches Device regulär zerstört, während ein Host-Wait offen ist (`WaitSemaphores`) | `DEVICE_DESTROYED` als X11-Fehler; `WaitForFence` verwendet stattdessen den normalen Reply-Status `DEVICE_DESTROYED = 4` |
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
- Extension-Name ist leer, länger als 255 Bytes oder syntaktisch ungültig: `BadValue`.
- Extension-Name ist syntaktisch gültig, aber unbekannt in der XAverius-Extension-Registry oder vom Physical Device nicht unterstützt: `BadMatch`.
- Doppelte Extension-Namen: `BadValue`.
- Alle Anforderungen müssen vor der Device-Erzeugung geprüft werden. Bei jedem Fehler bleibt die angeforderte `device_xid` unangelegt; der Server darf Features oder Extensions nicht stillschweigend auslassen.

## Request-spezifische Fehlerzuordnung

### `WriteBuffer`

- Falsche Request-Länge: `BadLength`
- Länge null, nicht-null Padding oder ungültige reservierte Felder: `BadValue`
- Request-Gesamtlänge mit Überlauf oder oberhalb des für die Verbindung geltenden X11-Limits: `BadLength`
- Unbekannte/nicht-live XAverius-XID: `BadValue`
- Falscher Typ, falsches Device, ungebundener Buffer, fehlendes `TRANSFER_DST`, Bereich außerhalb des Buffers: `BadMatch`
- Nicht verfügbares/verlorenes Device: `DEVICE_UNAVAILABLE` / `DEVICE_LOST`
- Synchroner Transferfehler: `TRANSFER_FAILED`
- Fehlgeschlagene Staging-Allokation: `ALLOCATION_FAILED`
- Erkannter Abhängigkeitszyklus beim Warten auf frühere GPU-Arbeit: `DEPENDENCY_FAILED`

### `ReadBuffer`

- Falsche Request-Länge: `BadLength`
- Länge null oder ungültige reservierte Felder: `BadValue`
- Unbekannte/nicht-live XAverius-XID: `BadValue`
- Falscher Typ, falsches Device, ungebundener Buffer, fehlendes `TRANSFER_SRC`, Bereich außerhalb des Buffers: `BadMatch`
- Nicht verfügbares/verlorenes Device: `DEVICE_UNAVAILABLE` / `DEVICE_LOST`
- Synchroner Transferfehler: `TRANSFER_FAILED`
- Fehlgeschlagene Staging-Allokation: `ALLOCATION_FAILED`
- Erkannter Abhängigkeitszyklus vor Erfassung des Daten-Snapshots: `DEPENDENCY_FAILED`

### `ShaderModuleData`

- Falsche Request-Länge oder unpassender Payload-Umfang: `BadLength`
- Null `data_length` bei einem Datenchunk, nicht-null `data_length` bei ABORT, nicht-null Padding oder ungültige Flag-Kombination: `BadValue`
- Ungültige/nicht-live `device_xid`: `BadValue`; falscher live Device-Typ: `BadMatch`. Bei `CREATE` ergibt eine ungültige/belegte `shader_module_xid` `BadIDChoice`. Ohne `CREATE` erfordert der Request ein passendes Upload-Assembly; fehlt es, ergibt sich `INVALID_SYNCHRONIZATION_STATE`.
- `ABORT` ohne passendes laufendes Upload-Assembly: `INVALID_SYNCHRONIZATION_STATE`
- Ungültiges SPIR-V oder ein SPIR-V-Modul, das die v0.1-Validierungsregeln nicht erfüllt: `BadValue`; kein Shader Module bleibt live und das Assembly wird verworfen
- Fehler bei der Vulkan-Erstellung: konkreter Backendfehler wie `DEVICE_LOST`, `ALLOCATION_FAILED` oder `INTERNAL_SERVER_ERROR`; kein Shader Module bleibt live und das Assembly wird verworfen
- Ein fehlerhafter Chunk verwirft das gesamte zugehörige Assembly. Ein späterer X11-Fehler für diesen Chunk ist synchron und hinterlässt kein partielles Shader Module. Fehler bei `ShaderModuleData` erzeugen kein `ASYNC_ERROR`; Device Loss wird ausschließlich über den allgemeinen Device-Loss-Pfad gemeldet, nicht zusätzlich als upload-spezifisches Event.

### Device-Discovery und Device-Erstellung

- `EnumeratePhysicalDevices`: falsche Request-Länge (`!= 8` Bytes) ergibt `BadLength`; die Reply-Payload besteht ausschließlich aus vollständigen `PHYSICALDEVICEINFO`-Records. Ein unvollständiger Record darf nicht ausgegeben werden; wenn keine Physical Devices verfügbar sind, ist eine leere erfolgreiche Reply mit `reply.length = 0` zulässig.
- `GetPhysicalDeviceProperty`: falsche Request-Länge `BadLength`; ungültiges Atom `BadAtom`; unbekannte/nicht-live Device-XID `BadValue`; bei Status ungleich `SUCCESS` müssen `property_type`, `value_length` und Reply-Payload null sein.
- `GetPhysicalDeviceQueueFamilyProperties` und `GetPhysicalDeviceMemoryProperties`: Request-Länge exakt 12 Bytes; unbekannte/nicht-live Physical-Device-XID `BadValue`.
- `CreateDevice`: falsche Länge `BadLength`; `queue_family_request_count = 0`, `queue_count = 0`, doppelte Queue-Family-Records, nicht-null reserviertes Feld, ungültige Priorität, `enabled` ungleich 1, doppelte Feature-/Extension-Einträge, unbekannte Feature-ID oder formal ungültiger Extension-Name `BadValue`; ungültige/belegte `device_xid` `BadIDChoice`; unbekannte/nicht-live Physical-Device-XID `BadValue`; falscher live Ressourcentyp, Queue-Family-Anforderung mit nicht verfügbarer oder nicht unterstützter Queue-Anzahl, registriertes aber nicht unterstütztes Feature, unbekannte oder nicht unterstützte formal gültige Extension oder Cross-Device-Zugriff `BadMatch`; ein nicht verfügbares Physical Device `DEVICE_UNAVAILABLE`. Die Prüfung ist atomar und veröffentlicht kein logisches Device bei Fehler.
- `CreateDefaultDevice`: falsche Länge `BadLength`; Count null, nicht-null reserviertes Feld oder ungültige Priorität `BadValue`; ungültige/belegte `device_xid` `BadIDChoice`; kein geeignetes Gerät `DEVICE_UNAVAILABLE`.
- Beide Requests sind Void-Requests; Erfolg erzeugt keinen normalen Reply.
- `DestroyDevice`: falsche Länge `BadLength`; unbekannte/nicht-live XAverius-XID `BadValue`; fremde Device-Ownership `BadMatch`.

### `SelectEvents`

- Falsche Request-Länge: `BadLength`.
- Erfolgreicher `GEQueryVersion`-Austausch mindestens mit XGE 1.0 fehlt: `BadMatch`.
- Unbekannter Scope, nicht-null Flags/reservierte Felder, ungültige Maskenbits oder nicht-null Felder außerhalb des ausgewählten Scopes: `BadValue`.
- Unbekannte/nicht-live Device-XID oder ungültiger Queue-Family-/Queue-Index: `BadValue`; falscher live Ressourcentyp oder fremde Client-Ownership: `BadMatch`.
- Ein Fehler muss die bisherige Event-Auswahl unverändert lassen; eine erfolgreiche Anfrage ersetzt atomar nur die Auswahl für den angegebenen Scope.

### `CreateDescriptorSetLayout`

- Falsche Request-Länge oder ein nicht zum `binding_count` passender Payload: `BadLength`
- Nicht-null `flags`, reservierte/ungültige Feldwerte, unbekannte oder nicht unterstützte Stage-Bits, nicht unterstützter Descriptor-Typ oder ungültige Binding-Records: `BadValue`
- Ungültige oder bereits belegte Create-XID: `BadIDChoice`
- Unbekannte/nicht-live Device-XID: `BadValue`; falscher live Ressourcentyp, fremde Device-Ownership oder Cross-Device-Ressource: `BadMatch`
- Nicht verfügbares/verlorenes Device: `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; synchroner Backend-Allokationsfehler: `ALLOCATION_FAILED`
- Jeder Fehler lässt das Descriptor Set Layout unangelegt; Teilresultate sind unzulässig.

### `CreateCommandPool`

- Falsche Request-Länge: `BadLength`
- Unbekannte Pool-Flags oder nicht-null reservierte Bits: `BadValue`; ungültige/belegte Pool-XID: `BadIDChoice`
- Unbekannte/nicht-live Device-XID: `BadValue`; falscher live Ressourcentyp oder fremde Device-Ownership: `BadMatch`
- Queue-Family-Index außerhalb des Device-Profils oder Queue Family ohne Command-Buffer-Unterstützung: `BadValue`
- Nicht verfügbares/verlorenes Device: `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; Backend-Allokationsfehler: `ALLOCATION_FAILED`
- Bei Ablehnung bleibt die Pool-XID unangelegt.

### `CommandPool` und `CommandBufferData`

- Falsche Request-Länge oder ein Entry, dessen deklarierte Länge über das Request-Ende hinausreicht bzw. dessen Header unvollständig ist: `BadLength`
- Reservierte Bits/Felder, ungültige Flag-Kombination, fehlerhaftes Padding, unbekannte Command-ID oder eine ungültige Entry-Länge (insbesondere null oder kleiner als der Entry-Header): `BadValue`
- Für `CommandBufferData` wird nach erfolgreicher Wire-Strukturprüfung zuerst die Ziel-XID und danach die Pool-XID gemäß der Feldreihenfolge geprüft. Bei `CREATE` ergibt eine ungültige oder bereits belegte Ziel-XID `BadIDChoice`; ohne `CREATE` ergeben unbekannte/nicht-live Buffer-XIDs `BadValue` und ein falscher live Ressourcentyp `BadMatch`.
- Unbekannte/nicht-live Pool-XIDs ergeben `BadValue`; ein falscher live Ressourcentyp, fremde Client-Ownership oder eine Cross-Device-/falsche Pool-Zuordnung ergibt `BadMatch`. Der angegebene Pool muss auch bei `ABORT` exakt der Eltern-Pool des Buffers sein.
- Ohne `CREATE` muss der Buffer im Zustand `RECORDING` sein, sonst `INVALID_SYNCHRONIZATION_STATE`. Für CREATE, Append und FINAL wird dieser Zustandscheck erst nach erfolgreicher XID-/Typ-/Ownership-Prüfung und nach der Device-Zustandsprüfung ausgeführt: ein nicht verfügbares/verlorenes Device ergibt `DEVICE_UNAVAILABLE` beziehungsweise `DEVICE_LOST` und hat damit Vorrang vor einem nicht passenden Buffer-Zustand. `ABORT` ist die ausdrücklich logische Ausnahme: nach Struktur-, Feld-, XID-, Typ- und Ownership-Prüfung wird der `RECORDING`-Zustand geprüft, auch wenn das Device nicht verfügbar/verloren ist; bei gültigem live Buffer/Pool und passendem Eltern-Pool bleibt ABORT nach Device Loss zulässig und startet keine Vulkan-Arbeit.
- `ResetCommandBuffer` mit falscher Request-Länge ergibt `BadLength`; unbekannte/nicht-live Device- oder Buffer-XIDs ergeben `BadValue`; falscher live Ressourcentyp, fremde Ownership oder Cross-Device-Verwendung ergeben `BadMatch`.
- Nach erfolgreicher XID-/Ownership-Prüfung ergeben ein nicht verfügbares oder verlorenes logisches Device `DEVICE_UNAVAILABLE` beziehungsweise `DEVICE_LOST`, bevor Pool-Reset-Flag oder Buffer-Zustand geprüft werden.
- `ResetCommandBuffer` ohne `RESET_COMMAND_BUFFER`-Pool-Flag oder bei einem pending Buffer ergibt `INVALID_SYNCHRONIZATION_STATE`. Jede Ablehnung lässt Zustand, Entries und Ressourcenreferenzen unverändert.
- Fehlerhafte Entries eines `CommandBufferData`-Chunks werden atomar abgewiesen; der aktuelle Chunk wird nicht teilweise angehängt. Bereits vorher akzeptierte Chunks bleiben bis zu einem erfolgreichen Retry oder ABORT erhalten. Ein fehlgeschlagener FINAL-Chunk lässt den Buffer `RECORDING`; ein fehlgeschlagener CREATE hinterlässt weder eine öffentliche Buffer-XID noch einen Kind-Eintrag im Pool.

### Presentation-only `CMD_COPY_BUFFER_TO_SWAPCHAIN_IMAGE` (provisional command entry)

Diese Regeln gelten nur im presentation-capable Profil und reservieren keine Command-ID. Nach der strukturellen Prüfung des Entries werden unbekannte/nicht-live Buffer- oder Swapchain-XIDs mit `BadValue` abgewiesen; falscher live Ressourcentyp, fremde Client-Ownership oder Cross-Device-Verwendung ergibt `BadMatch`. Ein `image_index` außerhalb der Swapchain, ungültige `row_length`/`image_height`, fehlerhafte Ausrichtung oder ein Quellbereich außerhalb des Buffers ergibt `BadValue`. Ein Buffer ohne `TRANSFER_SRC`-Nutzung oder eine Swapchain ohne `TRANSFER_DST`-Nutzung ist als inkompatible Ressourcenkombination mit `BadMatch` abzulehnen. Die erforderliche Image-State-Prüfung erfolgt atomar bei Submission-Annahme: ist das Image dann nicht `ACQUIRED` oder konkurriert der Submit mit einer Present-Transition, ergibt sich `INVALID_SYNCHRONIZATION_STATE`. Die Prüfung berücksichtigt alle zuvor in X11-Request-Reihenfolge angenommenen Zustandsübergänge: ein Copy-Submit nach einer bereits angenommenen `QueuePresent`-Transition auf `PRESENT_PENDING` wird abgewiesen; ein zuvor angenommener Submit bleibt dagegen gültig und behält seine internen Referenzen. Die Request-Reihenfolge ersetzt keine GPU-Synchronisation. Die Ablehnung darf weder den Command-Buffer teilweise annehmen noch Image-, Referenz- oder Semaphore-Zustände verändern. Ein Swapchain-Destroy bleibt abgewiesen, solange ein Recording-Command-Buffer darauf referenziert; nach erfolgreichem Destroy wird ein nicht-pending ausführbarer Command-Buffer mit dieser Referenz invalidiert.

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
| `UpdateDescriptorSets`: `write_count = 0`, reservierte Felder ungleich null, doppelte Writes desselben Slots, ungültige Werte/Flags oder nicht zugewiesener `descriptor_type` | `BadValue` |
| `UpdateDescriptorSets`: ungültige/nicht-live Device-, Set- oder Buffer-XID | `BadValue` für unbekannte/nicht-live XIDs; `BadMatch` für einen falschen live Ressourcentyp |
| `UpdateDescriptorSets`: falscher live Typ, fremde Client-/Device-Ownership, Layout/Binding/Array-Slot oder registrierter Descriptor-Typ inkompatibel, Buffer ungebunden oder Bereich/Alignment ungültig | `BadMatch` |
| `UpdateDescriptorSets`: betroffenes Set wird von angenommener Arbeit verwendet | `INVALID_SYNCHRONIZATION_STATE` |
| `UpdateDescriptorSets`: Device ist nicht verfügbar/verloren | `DEVICE_UNAVAILABLE` / `DEVICE_LOST` |
| `QueueSubmit`: falsche Länge, inkonsistente Counts oder Längenberechnung läuft über | `BadLength` |
| `QueueSubmit`: Token ist null oder auf derselben Verbindung bereits verwendet; reservierte Felder, syntaktisch ungültige Wait-Stage-Maske (0 oder reservierte Bits), ungültige typunabhängige Feldwerte, doppelte rohe Wait-/Signal-Semaphore-XIDs oder dieselbe Semaphore in beiden Arrays | `BadValue` |
| `QueueSubmit`: Device-, Command-Buffer-, Semaphore- oder nicht-null Fence-XID ungültig/nicht live | `BadValue` für unbekannte/nicht-live XIDs; `BadMatch` für einen falschen live Ressourcentyp |
| `QueueSubmit`: falscher Ressourcentyp, fremde Client-/Device-Ownership oder angegebene Queue wurde nicht für dieses Device erstellt | `BadMatch` |
| `QueueSubmit`: Device nicht verfügbar/verloren, nach erfolgreicher XID-/Typ-/Ownership-/Queue-Prüfung und vor veränderlichen Submit-Zustandsprüfungen | `DEVICE_UNAVAILABLE` / `DEVICE_LOST` |
| `QueueSubmit`: typabhängiger Binary-/Timeline-Semaphore-Wert ist ungültig, nachdem XID, Typ und Device-Zustand geprüft wurden | `BadValue` |
| `QueueSubmit`: Command Buffer nicht `EXECUTABLE`, Fence nicht submitbar, Semaphore-Zustand unzulässig oder syntaktisch gültige Wait-Stage-Maske enthält eine Stage, die von der adressierten Queue-Family nicht unterstützt wird | `INVALID_SYNCHRONIZATION_STATE` |
| `QueueSubmit`: Abhängigkeit verhindert die Annahme, ohne dass eine speziellere Zustandsregel greift | `DEPENDENCY_FAILED` |
| `QueueSubmit`: synchroner Fehler vor Annahme | keinerlei Zustandsänderung; Token bleibt unbenutzt, Command Buffer bleiben `EXECUTABLE`, Fence-/Semaphore-Zustände und interne Referenzen bleiben unverändert; kein Submission-Event und kein `ASYNC_ERROR` |
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
- Device Loss während `WaitSemaphores` wird als `DEVICE_LOST`-X11-Fehler gemeldet; bei `WaitForFence` wird `DEVICE_LOST` als normaler Reply-Status zurückgegeben.
- Verarbeitung von `DestroyDevice` beendet offene `WaitSemaphores`-Requests mit `DEVICE_DESTROYED`; offene `WaitForFence`-Requests erhalten den Reply-Status `DEVICE_DESTROYED`. Dies ist von `DEVICE_LOST` getrennt.

### Fence-Requests

- Falsche Länge: `BadLength`
- Ungültige Flags oder reservierte Felder: `BadValue`
- Unbekannte/nicht-live XAverius-XID: `BadValue`
- Falscher Typ oder Device: `BadMatch`
- Ungültiger Reset-/Destroy-Zustand: `INVALID_SYNCHRONIZATION_STATE`
- `WaitForFence`: falsche Länge `BadLength`; unbekannte/nicht-live Device- oder Fence-XIDs `BadValue`; falscher live Ressourcentyp, fremde Ownership oder Cross-Device-Verwendung `BadMatch`; Timeout, Ausführungsfehler, Device Loss und `DestroyDevice` werden als normale Reply-Statuswerte zurückgegeben

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
- `DestroyFence`: `INVALID_SYNCHRONIZATION_STATE`, solange die Fence einer nicht-terminalen Submission zugeordnet ist oder eine offene `WaitForFence`-Registrierung genau diese interne Fence-Identität referenziert.
- `DestroySemaphore`: `INVALID_SYNCHRONIZATION_STATE`, solange ein angenommener Queue-Wait/-Signal, eine offene `WaitSemaphores`-Registrierung für genau diese interne Semaphore-Identität oder eine andere laufende Host-Operation die Semaphore verwendet.
- Bei beiden Requests blockiert ein Host-Wait die Zerstörung nicht mehr, sobald sein terminales Ergebnis serverseitig serialisiert festgestellt wurde; ein noch nicht versendeter Reply ist kein Hindernis. Device Loss allein invalidiert keine öffentlichen XIDs. Wenn anschließend `DestroyDevice` verarbeitet wird, darf dessen Device-weite Kaskadeninvalidierung diese normalen Ablehnungen umgehen.
- `FreeMemory`: `BadMatch`, solange irgendein intern noch lebender Buffer an die Allokation gebunden ist, auch wenn dessen öffentliche XID bereits invalidiert wurde; `INVALID_SYNCHRONIZATION_STATE`, solange angenommene Arbeit auf die Allokation zugreift.
- Ein Destroy-Request, der wegen Lebensdauerregeln abgewiesen wird, lässt alle öffentlichen XIDs und Command-Buffer-Zustände unverändert.
- Die Device-weite Kaskadeninvalidierung durch `DestroyDevice` ist von diesen normalen Pending-Use-Ablehnungen ausgenommen; Device Loss allein invalidiert keine öffentlichen XIDs. Interne Referenzen müssen in jedem Fall sicher erhalten bleiben.

### Buffer- und Memory-Requests

- `CreateBuffer`: falsche feste Länge `BadLength`; nicht-positive Größe, unbekannte Usage-Bits oder nicht-null reservierte Felder `BadValue`; ungültige oder bereits belegte Create-XID `BadIDChoice`; unbekannte/nicht-live Device-XID `BadValue`; falscher live Ressourcentyp oder fremdes Device `BadMatch`; nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; fehlgeschlagene Backend-Erstellung wegen Speicherknappheit `ALLOCATION_FAILED`; kein Buffer bleibt bei Ablehnung live.
- `GetBufferMemoryRequirements`: falsche Länge `BadLength`; unbekannte/nicht-live Buffer-/Device-XID `BadValue`; falscher Ressourcentyp oder Cross-Device-Zugriff `BadMatch`.
- `AllocateMemory`: falsche Länge `BadLength`; ungültige Größe, Memory-Type-Index oder reserviertes Feld `BadValue`; ungültige oder belegte Create-XID `BadIDChoice`; unbekannte/nicht-live Device-XID `BadValue`; falscher live Ressourcentyp oder fremde Device-Ownership `BadMatch`; nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; fehlgeschlagene Backend-Allokation `ALLOCATION_FAILED`; bei Ablehnung bleibt die Ziel-XID unangelegt.
- `FreeMemory`: siehe die Lebensdauerregeln unten; bei Ablehnung bleibt die Allokation öffentlich gültig.
- `BindBufferMemory`: siehe die spezifische Zuordnung unten.

### Descriptor-Pool- und Pipeline-Requests

- `CreateDescriptorPool`: falsche Länge oder nicht zum `pool_size_count` passende Payload `BadLength`; ungültige Counts, doppelte Pool-Size-Typen, nicht unterstützte Descriptor-Typen oder nicht-null reservierte Felder `BadValue`; ungültige/belegte Pool-XID `BadIDChoice`; unbekannte/nicht-live Device-XID `BadValue`; falscher live Ressourcentyp oder fremde Device-Ownership `BadMatch`; nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; Backend-Allokationsfehler `ALLOCATION_FAILED`; bei Ablehnung bleibt die Pool-XID unangelegt.
- `AllocateDescriptorSets`: falsche Länge oder unvollständiger Allocation-Entry `BadLength`; Count null oder nicht-null reservierte Felder `BadValue`; ungültige/belegte oder innerhalb des Requests doppelte Ziel-Set-XID `BadIDChoice`; unbekannte/nicht-live Device-, Pool- oder Layout-Eingabe-XID `BadValue`; falsche live Ressourcentypen, fremde Client-/Device-Ownership oder Pool-/Layout-Inkompatibilität `BadMatch`; nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; erschöpfte Pool-Kapazität oder Backend-Allokationsfehler `ALLOCATION_FAILED`. Die Operation ist atomar; bei Ablehnung bleibt keine Teilmenge der angeforderten Sets live.
- `FreeDescriptorSets`: falsche Länge `BadLength`; Count null oder nicht-null reservierte Felder `BadValue`; unbekannte/nicht-live Device-, Pool- oder Set-XID `BadValue`; falsche live Ressourcentypen, fremde Ownership oder Set gehört nicht zum angegebenen Pool/Device `BadMatch`; pending oder RECORDING-Referenz `INVALID_SYNCHRONIZATION_STATE`. Nach Device Loss bleibt die logische Freigabe zulässig und erfordert keine neue Vulkan-Arbeit; interne Referenzen bleiben bis zur sicheren Quieszenz erhalten. Keine Teilfreigabe bei Ablehnung.
- `DestroyDescriptorPool`: falsche Request-Länge `BadLength`; unbekannte/nicht-live Pool-XID `BadValue`; falscher live Ressourcentyp oder fremde Client-/Device-Ownership `BadMatch`; wenn ein Kind-Set pending verwendet oder von einem `RECORDING`-Command-Buffer referenziert wird, `INVALID_SYNCHRONIZATION_STATE`. Device Loss allein ist kein Ablehnungsgrund für die logische Bereinigung; die Pending-/Recording-Prüfungen bleiben bestehen. Die Ablehnung ist atomar: Pool, Sets und Referenzen bleiben unverändert.
- `CreatePipelineLayout`: falsche Gesamtlänge oder Counts, die nicht zum Payload passen, `BadLength`; nicht unterstützte Stage-Bits, ungültige Push-Constant-Ranges oder nicht-null reservierte Felder `BadValue`; ungültige/belegte `pipeline_layout_xid` `BadIDChoice`; unbekannte/nicht-live Device- oder Set-Layout-XID `BadValue`; falsche live Ressourcentypen, inkompatible/fremde Set-Layouts oder Cross-Device-Objekte `BadMatch`; nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; Backend-Allokationsfehler `ALLOCATION_FAILED`. Kein Pipeline Layout bleibt bei Ablehnung live.
- `CreateComputePipeline`: falsche Länge `BadLength`; leerer Entry-Point, ungültiges Padding oder nicht-null reservierte Felder `BadValue`; ungültige/belegte `pipeline_xid` `BadIDChoice`; unbekannte/nicht-live Shader-/Layout-/Device-Eingabe-XID `BadValue`; falsche live Ressourcentypen, inkompatible/fremde Shader-Module oder Pipeline-Layouts und Cross-Device-Objekte `BadMatch`; nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; Backend-Allokationsfehler `ALLOCATION_FAILED`. Kein Pipeline-Objekt bleibt bei Ablehnung live.

### Command-Pool-Requests

- `CreateCommandPool`: falsche Länge `BadLength`; unbekannte Flags oder nicht-null reservierte Felder `BadValue`; ungültige/belegte Pool-XID `BadIDChoice`; unbekannte/nicht-live Device-XID `BadValue`; falscher live Ressourcentyp oder fremde Device-Ownership `BadMatch`; Queue-Family-Index außerhalb des Device-Profils oder ohne Command-Buffer-Unterstützung `BadValue`.
- `DestroyCommandPool`: falsche Länge `BadLength`; unbekannte/nicht-live XID `BadValue`; falscher Typ oder Cross-Device-Ownership `BadMatch`; mindestens ein pending Kind-Command-Buffer `INVALID_SYNCHRONIZATION_STATE`. Device Loss allein ist kein Ablehnungsgrund; sobald betroffene Submissions terminalisiert und ihre Command Buffer nicht mehr pending sind, bleibt die logische Pool-Bereinigung zulässig. Ablehnung ist atomar.

### Synchronisations-Requests

- `CreateSemaphore` und `CreateFence`: falsche Länge `BadLength`; ungültige Typen, Werte, Flags oder reservierte Felder `BadValue`; ungültige/belegte Create-XID `BadIDChoice`; unbekannte/nicht-live Device-XID `BadValue`; falscher live Ressourcentyp oder fremde Device-Ownership `BadMatch`; nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; Backend-Allokationsfehler `ALLOCATION_FAILED`; bei Ablehnung bleibt die jeweilige Ziel-XID unangelegt.
- `GetSemaphoreCounterValue`: falsche Länge `BadLength`; unbekannte/nicht-live Device- oder Semaphore-XIDs `BadValue`; falscher live Ressourcentyp, fremde Ownership oder Cross-Device-Verwendung `BadMatch`; nur für Timeline-Semaphoren; bei Device Loss `DEVICE_LOST` statt eines Counter-Reply.
- `SignalSemaphore`: falsche Länge `BadLength`; unbekannte/nicht-live Device- oder Semaphore-XID `BadValue`; falscher live Ressourcentyp, fremde Client-/Device-Ownership oder Cross-Device-Verwendung `BadMatch`; nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; nur Timeline-Semaphoren zulässig; Signalwert nicht größer als Counter oder inkonsistent mit pending GPU-Signalreservierungen `INVALID_SYNCHRONIZATION_STATE`. Bei synchroner Ablehnung wird kein Host-Signal teilweise ausgeführt.
- `WaitSemaphores`: falsche Länge oder Überlauf der Längenberechnung `BadLength`; Count null, doppelte Semaphore-XIDs, ungültiger Wait-Modus oder ungültige Werte `BadValue`; unbekannte/nicht-live Device- oder Semaphore-XIDs `BadValue`; falscher live Ressourcentyp, fremde Ownership oder Cross-Device-Verwendung `BadMatch`. Device Loss wird als X11-Fehler `DEVICE_LOST`, `DestroyDevice` bei offenem Wait als `DEVICE_DESTROYED` gemeldet. `TIMEOUT` ist ausschließlich ein normaler Reply-Status.
- `GetFenceStatus`: falsche Länge `BadLength`; unbekannte/nicht-live Device- oder Fence-XIDs `BadValue`; falscher live Ressourcentyp, fremde Ownership oder Cross-Device-Verwendung `BadMatch`; nach Device Loss wird der gespeicherte Fence-Zustand abgefragt.
- `ResetFence`: falsche Länge `BadLength`; unbekannte/nicht-live Device- oder Fence-XIDs `BadValue`; falscher live Ressourcentyp, fremde Ownership oder Cross-Device-Verwendung `BadMatch`; nur `SIGNALED` und `FAILED` dürfen zurückgesetzt werden, andere Zustände ergeben `INVALID_SYNCHRONIZATION_STATE`; bei verlorenem Device `DEVICE_LOST`.
- `DestroyFence`: falsche Länge `BadLength`; unbekannte/nicht-live Device- oder Fence-XID `BadValue`; falscher live Typ, fremde Client-Ownership oder Cross-Device-Verwendung `BadMatch`; `INVALID_SYNCHRONIZATION_STATE`, solange die Fence `PENDING` ist oder eine offene `WaitForFence`-Registrierung genau diese interne Fence-Identität referenziert. Eine bereits terminal festgestellte Wait-Registrierung blockiert die Zerstörung nicht, auch wenn der Reply noch nicht gesendet wurde. Jede Ablehnung lässt XID und Fence-Zustand unverändert.
- `DestroySemaphore`: falsche Länge `BadLength`; unbekannte/nicht-live Device- oder Semaphore-XID `BadValue`; falscher live Typ, fremde Client-Ownership oder Cross-Device-Verwendung `BadMatch`; `INVALID_SYNCHRONIZATION_STATE`, solange ein angenommener Queue-Wait, Queue-Signal, eine offene `WaitSemaphores`-Registrierung für genau diese interne Semaphore-Identität oder eine andere laufende Host-Operation die Semaphore verwendet. Eine bereits terminal festgestellte Wait-Registrierung blockiert die Zerstörung nicht, auch wenn der Reply noch nicht gesendet wurde. Jede Ablehnung lässt XID und Synchronisationszustand unverändert. Device Loss allein invalidiert keine öffentlichen XIDs; wenn anschließend `DestroyDevice` verarbeitet wird, darf dessen Kaskadeninvalidierung diese normalen Ablehnungen umgehen.
- Die verbindliche XID-Zuordnung steht im Abschnitt „Verbindliche XID-Fehlerregel“: unbekannte/nicht-live XAverius-XIDs ergeben `BadValue`, falsche live Ressourcentypen `BadMatch`, ungültige Atoms `BadAtom`.

### Memory-Allokation und Bindung

- `GetBufferMemoryRequirements`: falsche Request-Länge `BadLength`; unbekannte/nicht-live Device- oder Buffer-XID `BadValue`; falscher live Ressourcentyp oder Buffer eines anderen Devices `BadMatch`.
- `AllocateMemory`: falsche Request-Länge `BadLength`; nicht-positive Allokationsgröße, reserviertes Feld ungleich null oder nicht existierender Memory-Type-Index `BadValue`; unbekannte/nicht-live Device-XID `BadValue`; falscher live Ressourcentyp `BadMatch`; nicht verfügbares/verlorenes Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; Backend-Allokationsfehler `ALLOCATION_FAILED`. Bei jedem Fehler bleibt die angeforderte `memory_xid` unangelegt.
- `FreeMemory`: falsche Request-Länge `BadLength`; unbekannte/nicht-live Device- oder Memory-XID `BadValue`; falscher live Ressourcentyp, fremde Ownership oder Cross-Device-Nutzung `BadMatch`; irgendein intern noch lebender, gebundener Buffer `BadMatch` (auch bei bereits invalidierter Buffer-XID); angenommene GPU-Arbeit mit Zugriff auf die Allokation `INVALID_SYNCHRONIZATION_STATE`. Bei Ablehnung bleibt die Allokation unverändert.
- `BindBufferMemory`: falsche Request-Länge `BadLength`; unbekannte/nicht-live Device-, Buffer- oder Memory-XID `BadValue`; falscher live Ressourcentyp, fremde Ownership oder Cross-Device-Nutzung `BadMatch`; inkompatibler Memory-Type, bereits gebundener Buffer, ungültiges Alignment oder unzureichende Allokationsgrenzen `BadMatch`. Bei Ablehnung bleibt der Buffer ungebunden.

### `BindBufferMemory`

Die vollständige XID-, Ownership-, Feldwert- und Device-Fehlerzuordnung steht in der einheitlichen Tabelle oben. Cross-Device-Nutzung, bereits gebundener Buffer, ungültiges Alignment, zu kleine Allokation oder inkompatibler Memory-Type ergeben `BadMatch`.

### `UpdateDescriptorSets`

Die vollständige XID-, Ownership-, Feldwert- und Device-Fehlerzuordnung steht in der einheitlichen Tabelle oben. Der Request bleibt bei jedem Fehler atomar.

Jeder Request muss vor Implementierungsfreigabe eine vollständige, konkrete Fehlerzuordnung besitzen.

### Presentation requests (provisional wire layouts)

These rules apply to the presentation-capable profile only. They do not allocate request subopcodes and do not make the presentation profile part of the compute-only v0.1 baseline.

- All presentation requests validate the exact fixed or formula-based request length first; a mismatch or overflow in `40 + 4 * wait_semaphore_count` is `BadLength`. Non-zero reserved fields, invalid enum/flag values, zero presentation tokens, reuse of a token from an already accepted presentation, duplicate wait semaphore XIDs, and malformed count/field combinations are `BadValue`.
- `CreateSurface`: invalid/already allocated target `surface_xid` is `BadIDChoice`; an unknown, destroyed, or non-Window core X11 `window_xid` is core X11 `BadWindow`. A failed create leaves the target XID unallocated and retains no window reference.
- `DestroySurface`: unknown/non-live Surface XID is `BadValue`; a live XID of another type or a Surface owned by another connection is `BadMatch`; a live Swapchain still referencing the Surface causes atomic rejection with `INVALID_SYNCHRONIZATION_STATE`.
- `GetSurfaceCapabilities`: unknown/non-live Device or Surface XID is `BadValue`; a live wrong type, foreign connection ownership, or cross-device use is `BadMatch`. `SUCCESS`, `TEMPORARILY_NOT_PRESENTABLE`, `SURFACE_LOST`, and `DEVICE_LOST` are normal reply statuses, not X11 errors. Status-dependent zero fields and the reply-length formula remain mandatory.
- `CreateSwapchain`: invalid/already allocated target `swapchain_xid` is `BadIDChoice`; unknown/non-live Device or Surface XID is `BadValue`; wrong live type, foreign ownership, or cross-device combination is `BadMatch`; invalid counts, dimensions, format/mode identifiers, usage bits, or non-zero reserved fields are `BadValue`. `OUT_OF_DATE`, `SURFACE_LOST`, `DEVICE_LOST`, `UNSUPPORTED_CONFIGURATION`, and `ALLOCATION_FAILED` are normal reply statuses. On every non-success status the target XID remains unallocated.
- `DestroySwapchain`: unknown/non-live Swapchain XID is `BadValue`; a live wrong type or foreign ownership is `BadMatch`; a recording command buffer, pending acquire registration, accepted queue work, accepted presentation, or possible backend access causes atomic rejection with `INVALID_SYNCHRONIZATION_STATE`; non-pending executable command buffers referencing the Swapchain are invalidated atomically on successful destruction. An acquired-but-idle image alone does not block destruction.
- `AcquireNextImage`: unknown/non-live Device or Swapchain XID is `BadValue`; wrong live type, foreign ownership, or cross-device use is `BadMatch`; a supplied semaphore/fence with wrong type, ownership, or device is `BadMatch`; an ineligible semaphore/fence state or conflicting pending acquisition is `INVALID_SYNCHRONIZATION_STATE`. `TIMEOUT`, `NOT_READY`, `OUT_OF_DATE`, `SURFACE_LOST`, `DEVICE_LOST`, and `DEVICE_DESTROYED` are normal reply statuses and must not signal either synchronization object or change image state. `DestroyDevice` terminalizes any still-open acquire with `DEVICE_DESTROYED`; a previously serialized terminal result wins.
- `QueuePresent`: unknown/non-live Device, Swapchain, or wait-semaphore XID is `BadValue`; wrong live type, foreign ownership, cross-device use, or a queue not belonging to the Device is `BadMatch`; nonexistent queue-family/index or image index outside the Swapchain is `BadValue`; a valid queue family whose capability record has `present_supported = 0` for the target Surface is `BadMatch`; an image not in `ACQUIRED`, or a wait semaphore that cannot be legally consumed because of an incompatible pending wait/state, is `INVALID_SYNCHRONIZATION_STATE`; a wait semaphore already marked `UNTRUSTED` is rejected with `DEPENDENCY_FAILED`. `OUT_OF_DATE`, `SURFACE_LOST`, and `DEVICE_LOST` are normal reply statuses. Any rejected request leaves the image `ACQUIRED`, leaves wait-semaphore state unchanged, and does not reserve its presentation token. Token uniqueness is checked against previously accepted presentations and recorded atomically with acceptance.
- For all seven requests, validation is atomic: no partial object, reference, image-state, or synchronization-state change may remain after a synchronous error or a non-success status. An accepted `QueuePresent` cannot later produce an X11 request error; its terminal result is reported through the presentation events and image/Swapchain state.

## Synchron versus asynchron

Ein Fehler vor Annahme wird durch einen X11-Fehler oder den ausdrücklich definierten normalen Fehler-Reply signalisiert. Der Request darf keinen Teilzustand hinterlassen.

Ein Fehler nach Annahme wird durch XAverius-Events und Synchronisationszustände signalisiert. Ein später X11-Fehler für einen bereits angenommenen Request ist unzulässig.
