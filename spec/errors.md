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
| Ungültige Ressource | Request-spezifischer Standard-X11-Fehler |
| Device nicht verfügbar | `DEVICE_UNAVAILABLE` |
| Device verloren | `DEVICE_LOST` |
| Ungültiger Synchronisationszustand | `INVALID_SYNCHRONIZATION_STATE` |
| Synchroner Transferfehler | `TRANSFER_FAILED` |
| Synchroner Allokationsfehler | `ALLOCATION_FAILED` |
| Ungültige Abhängigkeit verhindert Annahme | `DEPENDENCY_FAILED` |
| Unerwarteter Serverfehler | `INTERNAL_SERVER_ERROR` |

## Request-spezifische Fehlerzuordnung

### `WriteBuffer`

- Falsche Request-Länge: `BadLength`
- Länge null oder ungültige reservierte Felder: `BadValue`
- Ungültige XID: request-spezifischer X11-Fehler
- Falscher Typ, falsches Device, ungebundener Buffer, fehlendes `TRANSFER_DST`, Bereich außerhalb des Buffers: `BadMatch`
- Nicht verfügbares/verlorenes Device: `DEVICE_UNAVAILABLE` / `DEVICE_LOST`
- Synchroner Transferfehler: `TRANSFER_FAILED`
- Fehlgeschlagene Staging-Allokation: `ALLOCATION_FAILED`

### `ReadBuffer`

- Falsche Request-Länge: `BadLength`
- Länge null oder ungültige reservierte Felder: `BadValue`
- Ungültige XID: request-spezifischer X11-Fehler
- Falscher Typ, falsches Device, ungebundener Buffer, fehlendes `TRANSFER_SRC`, ungültiger Bereich: `BadMatch`
- Nicht verfügbares/verlorenes Device: `DEVICE_UNAVAILABLE` / `DEVICE_LOST`
- Synchroner Transferfehler: `TRANSFER_FAILED`
- Fehlgeschlagene Staging-Allokation: `ALLOCATION_FAILED`

### `ShaderModuleData`

- Falsche Request-Länge oder unpassender Payload-Umfang: `BadLength`
- Null `data_length` bei einem Datenchunk, nicht-null `data_length` bei ABORT, nicht-null Padding oder ungültige Flag-Kombination: `BadValue`
- Ungültige oder falsche Device-/Shader-Module-XID: request-spezifischer X11-Fehler beziehungsweise `BadMatch` bei falschem Typ oder Device
- `ABORT` ohne passendes laufendes Upload-Assembly: `INVALID_SYNCHRONIZATION_STATE`
- Ungültiges SPIR-V oder ein SPIR-V-Modul, das die v0.1-Validierungsregeln nicht erfüllt: `BadValue`; kein Shader Module bleibt live und das Assembly wird verworfen
- Fehler bei der Vulkan-Erstellung: konkreter Backendfehler wie `DEVICE_LOST`, `ALLOCATION_FAILED` oder `INTERNAL_SERVER_ERROR`; kein Shader Module bleibt live und das Assembly wird verworfen
- Ein fehlerhafter Chunk verwirft das gesamte zugehörige Assembly. Ein späterer X11-Fehler für diesen Chunk ist synchron und hinterlässt kein partielles Shader Module.

### Device-Discovery und Device-Erstellung

- `EnumeratePhysicalDevices`: Request muss exakt 8 Bytes lang sein; die Reply-Payload besteht ausschließlich aus vollständigen `PHYSICALDEVICEINFO`-Records. Ein unvollständiger Record darf nicht ausgegeben werden.
- `GetPhysicalDeviceProperty`: falsche Request-Länge `BadLength`; ungültige Atom-/Device-XID über Standard-X11-Fehler; bei Status ungleich `SUCCESS` müssen `property_type`, `value_length` und Reply-Payload null sein.
- `GetPhysicalDeviceQueueFamilyProperties` und `GetPhysicalDeviceMemoryProperties`: Request-Länge exakt 12 Bytes; ungültige Physical-Device-XID über Standard-X11-Fehler.
- `CreateDevice` und `CreateDefaultDevice`: Void-Requests; Erfolg erzeugt keinen Reply. `CreateDefaultDevice` meldet fehlendes geeignetes Gerät mit `DEVICE_UNAVAILABLE`. Nicht unterstützte Feature-/Extension-Anfragen bei `CreateDevice` bleiben gemäß Open Issues noch nicht abschließend zugeordnet.
- `DestroyDevice`: falsche Länge `BadLength`; ungültige XID über Standard-X11-Fehler; fremde Device-Ownership `BadMatch`.

### `CreateDescriptorSetLayout`

- Falsche Request-Länge oder ein nicht zum `binding_count` passender Payload: `BadLength`
- Nicht-null `flags`, reservierte/ungültige Feldwerte, unbekannte oder nicht unterstützte Stage-Bits, nicht unterstützter Descriptor-Typ oder ungültige Binding-Records: `BadValue`
- Ungültige oder bereits belegte Create-XID: `BadIDChoice`
- Ungültiges Device-XID: request-spezifischer Standard-X11-Fehler; Cross-Device-Ressource: `BadMatch`
- Jeder Fehler lässt das Descriptor Set Layout unangelegt; Teilresultate sind unzulässig.

### `CommandPool` und `CommandBufferData`

- Falsche Request-Länge oder unvollständiger Entry: `BadLength`
- Reservierte Bits/Felder, ungültige Flag-Kombination, fehlerhaftes Padding oder ungültige Entry-Länge: `BadValue`
- Falscher Ressourcentyp, Queue-Family-Index oder Cross-Device-Objekt: `BadMatch`
- ABORT bei einem Buffer, der nicht `RECORDING` ist, oder bei einem pending Buffer: `INVALID_SYNCHRONIZATION_STATE`
- `ResetCommandBuffer` ohne `RESET_COMMAND_BUFFER`-Pool-Flag oder bei einem pending Buffer: `INVALID_SYNCHRONIZATION_STATE`; Ablehnung lässt Zustand und Ressourcenreferenzen unverändert
- `ResetCommandBuffer` mit ungültiger Ressource oder falschem Device: request-spezifischer X11-Fehler beziehungsweise `BadMatch` bei Cross-Device-Verwendung
- Fehlerhafte Entries eines `CommandBufferData`-Chunks werden atomar abgewiesen; der aktuelle Chunk wird nicht teilweise angehängt. Bereits vorher akzeptierte Chunks bleiben bis zu einem erfolgreichen Retry oder ABORT erhalten.

### `QueueSubmit`

- Count-/Längenfehler: `BadLength`
- Ungültige Masks, reservierte Felder oder numerische Werte: `BadValue`
- Ungültige XID: request-spezifischer X11-Fehler
- Falscher Typ oder Cross-Device-Ressource: `BadMatch`
- Nicht ausführbarer Command Buffer, ungültiger Fence- oder Semaphore-Zustand: `INVALID_SYNCHRONIZATION_STATE`
- Nicht verfügbares/verlorenes Device: `DEVICE_UNAVAILABLE` / `DEVICE_LOST`
- Ungültige Abhängigkeit, die Annahme verhindert: `DEPENDENCY_FAILED`

### Synchronisations-Requests

- `CreateSemaphore`: exakt 28 Bytes; `CreateFence`: exakt 24 Bytes; `DestroySemaphore`, `GetSemaphoreCounterValue`, `DestroyFence`, `GetFenceStatus` und `ResetFence`: exakt 16 Bytes; `SignalSemaphore` und `WaitForFence`: exakt 24 Bytes.
- `WaitSemaphores`: exakt `28 + 12 * semaphore_count` Bytes; Count null oder nicht exakt passende Länge wird abgewiesen (`BadValue` bei null Count, `BadLength` bei Längenabweichung).
- Ungültige Semaphoren-/Fence-XIDs: Standard-X11-Fehler; falscher Typ oder Device `BadMatch`; unzulässige Zustandsübergänge `INVALID_SYNCHRONIZATION_STATE`.
- `WaitSemaphores` und `WaitForFence` liefern bei Timeout einen normalen Reply-Status und keinen X11-Fehler.

### Fence-Requests

- Falsche Länge: `BadLength`
- Ungültige Flags oder reservierte Felder: `BadValue`
- Ungültige Ressource: request-spezifischer X11-Fehler
- Falscher Typ oder Device: `BadMatch`
- Ungültiger Reset-/Destroy-Zustand: `INVALID_SYNCHRONIZATION_STATE`
- Timeout und asynchroner Ausführungsfehler bei `WaitForFence`: normaler Reply-Status

### `DestroyResource`

- Falsche Request-Länge: `BadLength`
- Ungültige oder nicht mehr live XID: request-spezifischer Standard-X11-Fehler
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

- `CreateBuffer`: falsche feste Länge `BadLength`; nicht-positive Größe, unbekannte Usage-Bits oder nicht-null reservierte Felder `BadValue`; ungültige oder bereits belegte Create-XID `BadIDChoice`; ungültiges Device-XID als Standard-X11-Fehler; fehlgeschlagene Backend-Allokation `ALLOCATION_FAILED`.
- `GetBufferMemoryRequirements`: falsche Länge `BadLength`; ungültiges Buffer-/Device-XID als Standard-X11-Fehler; falscher Ressourcentyp oder Cross-Device-Zugriff `BadMatch`.
- `AllocateMemory`: falsche Länge `BadLength`; ungültige Größe, Memory-Type-Index oder reserviertes Feld `BadValue`; ungültige oder belegte Create-XID `BadIDChoice`; ungültiges Device-XID als Standard-X11-Fehler; fehlgeschlagene Backend-Allokation `ALLOCATION_FAILED`.
- `FreeMemory`: siehe die Lebensdauerregeln unten; bei Ablehnung bleibt die Allokation öffentlich gültig.
- `BindBufferMemory`: siehe die spezifische Zuordnung unten.

### Descriptor-Pool- und Pipeline-Requests

- `CreateDescriptorPool`: falsche Länge oder nicht zum `pool_size_count` passende Payload `BadLength`; ungültige Counts, nicht unterstützte Descriptor-Typen oder nicht-null reservierte Felder `BadValue`; ungültige/belegte Pool-XID `BadIDChoice`; ungültiges Device-XID als Standard-X11-Fehler; Backend-Allokationsfehler `ALLOCATION_FAILED`.
- `AllocateDescriptorSets`: falsche Länge oder unvollständiger Allocation-Entry `BadLength`; Count null oder nicht-null reservierte Felder `BadValue`; ungültige Pool-/Layout-XID als Standard-X11-Fehler; falsches Device, falscher Typ, Pool-/Layout-Inkompatibilität oder Pool-Kapazität erschöpft `ALLOCATION_FAILED`; Layout-/Device-Inkompatibilität `BadMatch`. Die Operation ist atomar.
- `FreeDescriptorSets`: falsche Länge `BadLength`; Count null oder nicht-null reservierte Felder `BadValue`; Set gehört nicht zum angegebenen Pool oder Device `BadMatch`; ungültige XID als Standard-X11-Fehler; pending oder RECORDING-Referenz `INVALID_SYNCHRONIZATION_STATE`. Keine Teilfreigabe bei Ablehnung.
- `CreatePipelineLayout`: falsche Länge/Count `BadLength`; nicht unterstützte Stage-Bits, ungültige Push-Constant-Ranges oder nicht-null reservierte Felder `BadValue`; ungültige XID als Standard-X11-Fehler; inkompatibles oder fremdes Set-Layout `BadMatch`; Backend-Erstellungsfehler werden als passender XAverius-Fehler gemeldet.
- `CreateComputePipeline`: falsche Länge `BadLength`; leerer Entry-Point, ungültiges Padding oder nicht-null reservierte Felder `BadValue`; ungültige Shader-/Layout-/Device-XID als Standard-X11-Fehler; inkompatibles oder gerätefremdes Shader Module beziehungsweise Pipeline Layout `BadMatch`; Backend-Erstellungsfehler werden als passender XAverius-Fehler gemeldet. Kein Pipeline-Objekt bleibt bei Ablehnung live.

### Command-Pool-Requests

- `CreateCommandPool`: falsche Länge `BadLength`; unbekannte Flags oder nicht-null reservierte Felder `BadValue`; ungültige/belegte Pool-XID `BadIDChoice`; ungültige Queue Family oder ungültiges Device `BadMatch` beziehungsweise Standard-X11-Fehler für eine ungültige XID.
- `DestroyCommandPool`: falsche Länge `BadLength`; ungültige XID als Standard-X11-Fehler; falscher Typ oder Cross-Device-Ownership `BadMatch`; mindestens ein pending Kind-Command-Buffer `INVALID_SYNCHRONIZATION_STATE`. Ablehnung ist atomar.

### Synchronisations-Requests

- `CreateSemaphore` und `CreateFence`: falsche Länge `BadLength`; ungültige Typen, Werte, Flags oder reservierte Felder `BadValue`; ungültige/belegte Create-XID `BadIDChoice`; ungültiges Device-XID als Standard-X11-Fehler; Backend-Allokationsfehler `ALLOCATION_FAILED`.
- `GetSemaphoreCounterValue`: nur für Timeline-Semaphoren; falscher Typ `BadMatch`, ungültige XID als Standard-X11-Fehler.
- `SignalSemaphore`: nur für Timeline-Semaphoren; ungültige XID als Standard-X11-Fehler; falscher Typ oder Device `BadMatch`; Signalwert, der nicht größer als der aktuelle Counter oder mit pending Signalen inkonsistent ist, `INVALID_SYNCHRONIZATION_STATE`. Bei synchroner Ablehnung wird kein Host-Signal teilweise ausgeführt.
- `WaitSemaphores`: ungültige XID als Standard-X11-Fehler; falscher Typ, falsches Device oder doppelte Semaphore-XID `BadMatch`; ungültiger Wait-Modus oder ungültige Werte `BadValue`. `TIMEOUT` ist ausschließlich ein normaler Reply-Status.
- `GetFenceStatus`: ungültige XID als Standard-X11-Fehler; falscher Typ oder Device `BadMatch`.
- `ResetFence`: nur `SIGNALED` und `FAILED` dürfen zurückgesetzt werden; andere Zustände `INVALID_SYNCHRONIZATION_STATE`. Bei verlorenem Device `DEVICE_LOST`.
- Die genauen Standard-X11-Fehler für ungültige XIDs richten sich nach Ressourcentyp und vorhandener X11-Ressourcenregistrierung; XAverius darf sie nicht pauschal in `BadValue` umwandeln.

### `BindBufferMemory`

Cross-Device-Nutzung, bereits gebundener Buffer, ungültiges Alignment, zu kleine Allokation oder inkompatibler Memory-Type ergeben `BadMatch`.

### `UpdateDescriptorSets`

- Falsche Länge: `BadLength`
- Reservierte Felder oder ungültige Werte: `BadValue`
- Inkompatibler Descriptor, Buffer oder Device: `BadMatch`
- Update während Pending-Use: `INVALID_SYNCHRONIZATION_STATE`

Jeder Request muss vor Implementierungsfreigabe eine vollständige, konkrete Fehlerzuordnung besitzen.

## Synchron versus asynchron

Ein Fehler vor Annahme wird durch einen X11-Fehler oder den ausdrücklich definierten normalen Fehler-Reply signalisiert. Der Request darf keinen Teilzustand hinterlassen.

Ein Fehler nach Annahme wird durch XAverius-Events und Synchronisationszustände signalisiert. Ein später X11-Fehler für einen bereits angenommenen Request ist unzulässig.
