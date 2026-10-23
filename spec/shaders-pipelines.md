# 6. Shader, Descriptor-Layouts und Pipelines

## 6.1 Shader Modules

Shader upload and creation use one request opcode, `ShaderModuleData`, with request-specific flags in the XAverius common header. The request is a Void request: successful chunks receive no reply; errors are reported as ordinary X11 errors correlated to the offending request. A successful `FINAL` request means the module has been fully validated and created.

The fixed request header and payload are:

| Offset | Type | Field |
|---:|---|---|
| 8 | XID | `device_xid` |
| 12 | XID | `shader_module_xid` |
| 16 | CARD32 | `data_length`, number of SPIR-V payload bytes in this request |
| 20 | BYTE[] | SPIR-V bytes for this chunk, followed by zero padding to a four-byte boundary |

Total request length is `20 + ((data_length + 3) & ~3)` bytes. `data_length` excludes padding. The SPIR-V byte stream is concatenated exactly as received; padding bytes are not part of the module. The total assembled module length must be a multiple of four and the assembled bytes must form a valid SPIR-V module accepted by the server's Vulkan implementation.

The common-header `flags` byte is defined for this request as:

| Bit | Name | Meaning |
|---:|---|---|
| 0 | `CREATE` | Begin a new upload and reserve `shader_module_xid` for this attempt |
| 1 | `FINAL` | This is the final chunk; validate and create the shader module atomically |
| 2 | `ABORT` | Discard an upload in progress |
| 3–7 | reserved | MUST be zero |

Flag combinations and chunk rules:

- `CREATE=1, FINAL=0, ABORT=0`: start a new upload and append this chunk.
- `CREATE=1, FINAL=1, ABORT=0`: create and finalize a module from this single request.
- `CREATE=0, FINAL=0, ABORT=0`: append a chunk to an upload already in progress for this XID.
- `CREATE=0, FINAL=1, ABORT=0`: append the final chunk and attempt module creation.
- `CREATE=0, FINAL=0, ABORT=1`: abort and discard an upload in progress. `data_length` MUST be zero.
- All other combinations are invalid. In particular, `ABORT` cannot be combined with `CREATE` or `FINAL`.

A non-abort chunk must have positive `data_length`. Every request is a complete chunk; chunks cannot split a field of the X11/XAverius framing, and their payloads are concatenated without inter-chunk padding beyond each request's own final zero padding. The server checks request length, padding, flag combinations, device ownership, XID state, accumulated-size overflow, and the implementation's maximum shader-module size before accepting a chunk.

There may be at most one upload in progress for a given `shader_module_xid` on a client connection. The XID must be unused when `CREATE` is received. While an upload is in progress, the XID is reserved for that attempt and cannot be used by another create request. The assembled bytes and metadata are private server state, not a public shader-module resource, until a `FINAL` chunk succeeds.

If a chunk is malformed, has invalid padding, exceeds a limit, or otherwise fails validation, the request receives an X11 error and the entire in-progress upload for that XID is discarded. A failed `FINAL` also discards the assembly and leaves no live shader-module resource. After cleanup, the client may retry using the same XID if it remains a valid unused XID under normal X11 resource-ID rules. An `ABORT` of an existing upload discards it; an `ABORT` with no matching upload fails with the request-specific invalid-state error and changes nothing. Disconnect and device loss discard all affected incomplete uploads synchronously with respect to the connection/device state transition. A later chunk or ABORT for a discarded assembly finds no matching upload and fails with `INVALID_SYNCHRONIZATION_STATE`; it must not recreate or resurrect the old assembly. Chunk-validation and `FINAL`-creation failures are reported only as the synchronous X11 error for that request. They do not emit `ASYNC_ERROR`; device loss itself may emit the single device-level `DEVICE_LOST` event under the normal lifecycle rules, but must not emit a second upload-specific asynchronous error. Implementations must bound per-upload and aggregate assembly memory and must not allocate based on unchecked lengths.

SPIR-V validation and Vulkan shader-module creation occur atomically at `FINAL`: on success, the public resource becomes live; on failure, no public resource remains. `pNext` structures and Vulkan allocator callbacks are not transmitted in v0.1.

After successful creation of a Compute Pipeline, the Shader Module may be destroyed subject to Vulkan lifetime rules.

## 6.2 Descriptor Set Layout

`CreateDescriptorSetLayout` ist ein Void-Request mit folgendem Wire-Layout. Die Gesamtlänge beträgt `24 + 16 * binding_count` Bytes.

| Offset | Typ | Feld |
|---:|---|---|
| 8 | XID | `device_xid` |
| 12 | XID | `descriptor_set_layout_xid` |
| 16 | CARD32 | `flags`; in v0.1 MUSS null sein |
| 20 | CARD32 | `binding_count` |
| 24 | BINDING[] | `binding_count` Binding-Records |

Jeder Binding-Record ist 16 Bytes groß:

| Relativer Offset | Typ | Feld |
|---:|---|---|
| 0 | CARD32 | `binding` |
| 4 | CARD32 | `descriptor_type` |
| 8 | CARD32 | `descriptor_count` |
| 12 | CARD32 | `stage_flags` |

Der Request muss exakt die durch `binding_count` bestimmte Länge haben. Die Gesamtlänge muss innerhalb der normalen X11-Requestgrößenbegrenzung liegen. `binding_count = 0` ist zulässig und erzeugt ein leeres Layout. Für jeden Record muss `descriptor_count` größer als null sein. Binding-Nummern müssen innerhalb des Layouts eindeutig sein; doppelte Binding-Nummern machen den gesamten Request ungültig.

`descriptor_type` und `stage_flags` verwenden ausschließlich die normativen [Descriptor-Type-Registry](../registries/descriptor-types.md) und [Shader-Stage-Registry](../registries/shader-stages.md). Jeder verwendete Wert muss in v0.1 unterstützt sein. Die Stage-Maske darf keine unbekannten oder nicht unterstützten Bits enthalten und muss mindestens eine unterstützte Stage enthalten. Nicht unterstützte Descriptor-Typen werden abgewiesen; die numerischen Werte werden nicht lokal in diesem Kapitel vergeben.

`flags` muss null sein. Nicht-null Flags werden mit `BadValue` abgewiesen; v0.1 akzeptiert keine implizit ignorierten Layout-Flags. Der Server prüft zusätzlich Device-Ownership, unbenutzte Create-XID, Descriptor- und Stage-Unterstützung sowie Geräte-Limits. Die Erstellung ist atomar: Bei einem Fehler wird kein Descriptor Set Layout öffentlich angelegt. Unbekannte/nicht-live Device-XIDs ergeben `BadValue`; ein falscher live Ressourcentyp oder fremde Device-Ownership ergibt `BadMatch`. Ein nicht verfügbares oder verlorenes logisches Device ergibt `DEVICE_UNAVAILABLE` beziehungsweise `DEVICE_LOST`; ein Backend-Allokationsfehler ergibt `ALLOCATION_FAILED`.

Im initialen Compute-Test werden Bindings 0, 1 und 2 jeweils als `STORAGE_BUFFER`, Anzahl 1 und `COMPUTE` angelegt.

Nach erfolgreicher Pipeline-Layout-Erstellung darf das Descriptor Set Layout öffentlich zerstört werden, sofern die tatsächlichen Vulkan-Lebensdauerregeln dies erlauben. Interne Referenzen werden entsprechend den Vulkan-Regeln erhalten.

## 6.3 Descriptor Pool

`CreateDescriptorPool` hat die Gesamtlänge:

`24 + 8 * pool_size_count`

- Offset 8: Device-XID
- Offset 12: Descriptor-Pool-XID
- Offset 16: `CARD32 max_sets`
- Offset 20: `CARD16 pool_size_count`
- Offset 22: `CARD16 reserved = 0`
- Offset 24: Array aus 8-Byte-Entries

Jeder Pool-Entry enthält `CARD32 descriptor_type` und `CARD32 descriptor_count`.

`max_sets`, `pool_size_count` und alle Descriptor-Counts müssen positiv sein. Doppelte Pool-Size-Einträge sind ungültig. Unbekannte/nicht-live Device-XIDs ergeben `BadValue`; ein falscher live Ressourcentyp oder fremde Device-Ownership ergibt `BadMatch`. Ein nicht verfügbares oder verlorenes logisches Device ergibt `DEVICE_UNAVAILABLE` beziehungsweise `DEVICE_LOST`; ein Backend-Allokationsfehler ergibt `ALLOCATION_FAILED`. Die Erstellung ist atomar: bei jedem Fehler bleibt die Pool-XID unangelegt.

## 6.3.1 Destroy Descriptor Pool

`DestroyDescriptorPool` hat eine feste Gesamtlänge von 16 Bytes:

- Offset 8: Device-XID
- Offset 12: Descriptor-Pool-XID

Der Pool muss zum angegebenen logischen Device gehören. Der Request wird atomar abgewiesen, wenn ein enthaltenes Descriptor Set pending verwendet wird oder von einem `RECORDING`-Command-Buffer referenziert wird; der Fehler ist `INVALID_SYNCHRONIZATION_STATE`. Bei Ablehnung bleiben Pool, Sets und Command-Buffer-Zustände unverändert.

Bei Erfolg werden der Pool und alle enthaltenen Descriptor Sets öffentlich invalidiert. Nicht-pending `EXECUTABLE`-Command-Buffer, die eines dieser Sets referenzieren, werden `INVALID`. Interne Objekte bleiben erhalten, bis alle Referenzen und Backend-Zugriffe beendet sind.

Device Loss allein verhindert `DestroyDescriptorPool` nicht und erzeugt für sich genommen keinen `DEVICE_LOST`-Fehler für diese logische Bereinigung. Die normale atomare Prüfung bleibt jedoch bestehen: Ein Kind-Set, das noch von einem `RECORDING`-Command-Buffer referenziert wird, blockiert die Zerstörung weiterhin. Der Client kann zuerst den betreffenden Command Pool zerstören; nach Device Loss darf der Server dafür keine neue GPU-Arbeit starten und muss interne Referenzen bis zur sicheren Quieszenz halten oder quarantänisieren.

## 6.4 `AllocateDescriptorSets`

`AllocateDescriptorSets` ist ein Void-Request. Fester Header: 20 Bytes.

- Offset 8: Device-XID
- Offset 12: Descriptor-Pool-XID
- Offset 16: `CARD16 descriptor_set_count`
- Offset 18: `CARD16 reserved = 0`
- Offset 20: `DESCRIPTORSETALLOCATION[]`

Jeder Allocation-Entry ist acht Bytes groß und enthält Descriptor-Set-XID sowie Descriptor-Set-Layout-XID.

Gesamtlänge: `20 + 8 * descriptor_set_count`; `descriptor_set_count` muss positiv sein.

`AllocateDescriptorSets` prüft in dieser Reihenfolge: (1) Request-Länge und vollständige Allocation-Entries (`BadLength`); (2) `descriptor_set_count > 0` und reservierte Felder (`BadValue`); (3) jede Ziel-Set-XID in Array-Reihenfolge einschließlich Duplikaten (`BadIDChoice`); (4) Eingabe-XIDs in Wire-Reihenfolge: Device, Pool, danach Layout-XIDs in Entry-Reihenfolge (`BadValue` bei unbekannter/nicht-live XID); (5) Ressourcentyp, Client-/Device-Ownership und Device-Zuordnung (`BadMatch`); (6) Device-Zustand (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (7) Pool-/Layout-Kompatibilität, Pool-Kapazität und Backend-Allokation (`BadMatch` / `ALLOCATION_FAILED`). Die Operation ist atomar. Bei einem Fehler darf keine Teilmenge der Sets öffentlich angelegt bleiben.

## 6.5 `UpdateDescriptorSets`

`UpdateDescriptorSets` ist ein Void-Request. Fester Header: 20 Bytes.

- Offset 8: Device-XID
- Offset 12: `CARD16 write_count`
- Offset 14: `CARD16 reserved = 0`
- Offset 16: `CARD32 reserved = 0`
- Offset 20: `DESCRIPTORWRITE[]`

Jeder Write ist 36 Bytes groß.

| Relativer Offset | Typ | Feld |
|---:|---|---|
| 0 | XID | Descriptor-Set-XID |
| 4 | CARD32 | `binding` |
| 8 | CARD32 | `array_element` |
| 12 | CARD32 | `descriptor_type` |
| 16 | XID | Buffer-XID |
| 20 | CARD64 | `buffer_offset` |
| 28 | CARD64 | `range` |

Gesamtlänge: `20 + 36 * write_count`.

In v0.1 sind nur Buffer-Deskriptoren vorgesehen, für den initialen Compute-Pfad insbesondere Storage Buffer.

Der Server prüft Layout, Binding, Array-Slot, Typ, Device-Ownership, Buffer-Bindung, Alignment, Bereichsgrenzen und Geräte-Limits.

Mehrere Writes desselben Descriptor-Slots innerhalb eines Requests sind ungültig und ergeben `BadValue`. `descriptor_type` muss ein zugewiesener Wert der Descriptor-Type-Registry sein; `0` und nicht zugewiesene Werte ergeben `BadValue`. Ein registrierter Descriptor-Typ, der nicht zum Typ des angegebenen Layout-Bindings passt, ergibt `BadMatch`. Ein fehlgeschlagener Request darf keine Teiländerungen hinterlassen. Bei erfolgreichem Update werden die Descriptor-Slot-Inhalte und die daraus abgeleiteten internen Buffer-Referenzen atomar ersetzt. Command Buffer speichern beim Binden eine Referenz auf das Descriptor-Set-Objekt, keinen Snapshot seiner Slot-Inhalte; ein nicht-pending `EXECUTABLE`-Command-Buffer verwendet daher bei der späteren Submission die dann aktuellen Descriptor-Inhalte. Eine erfolgreiche Aktualisierung invalidiert einen solchen Command Buffer nicht allein wegen der geänderten Descriptor-Inhalte.

`UpdateDescriptorSets` verwendet diese Fehlerpräzedenz: (1) Request-Länge/Count und strukturelle Integrität (`BadLength`); (2) syntax- und feldlokale Prüfungen einschließlich `write_count > 0`, reservierter Felder, doppelter Writes desselben Slots und zugewiesener `descriptor_type` (`BadValue`); (3) Auflösung der XIDs in Wire-Reihenfolge – Device-XID, dann pro Write Descriptor-Set-XID und Buffer-XID – wobei unbekannte/nicht-live XIDs `BadValue` ergeben; (4) Ressourcentyp, Client-/Device-Ownership und Cross-Device-Zuordnung (`BadMatch`); (5) Device-Zustand (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (6) Layout-/Binding-/Array-Slot-/Descriptor-Typ-Kompatibilität, Buffer-Bindung, Alignment und Bereichsgrenzen (`BadMatch`), danach die Prüfung, ob ein betroffenes Set von angenommener Arbeit verwendet wird (`INVALID_SYNCHRONIZATION_STATE`). Die Device-Zustandsprüfung hat Vorrang vor diesen request-spezifischen Kompatibilitäts- und Pending-Zustandsprüfungen. Ein Fehler beendet den Request ohne Teiländerungen; bei Erfolg werden alle Slot-Inhalte und abgeleiteten Buffer-Referenzen atomar ersetzt.

## 6.6 `FreeDescriptorSets`

`FreeDescriptorSets` ist ein Void-Request. Fester Header: 20 Bytes.

- Offset 8: Device-XID
- Offset 12: Descriptor-Pool-XID
- Offset 16: `CARD16 descriptor_set_count`
- Offset 18: `CARD16 reserved = 0`
- Offset 20: Array aus Descriptor-Set-XIDs

Gesamtlänge: `20 + 4 * descriptor_set_count`; `descriptor_set_count` muss positiv sein. Das reservierte Feld muss null sein. Unbekannte/nicht-live Device-, Pool- oder Set-XIDs ergeben `BadValue`; falsche live Ressourcentypen, fremde Ownership oder ein Set, das nicht zum angegebenen Pool/Device gehört, ergeben `BadMatch`. `FreeDescriptorSets` ist eine logische Freigabe und bleibt nach Device Loss zulässig; es darf keine neue Vulkan-Arbeit auslösen und muss interne Descriptor-Set-/Backend-Referenzen bis zur sicheren Quieszenz erhalten.

Die Freigabe ist atomar: Wenn eine angeforderte XID ungültig ist oder ein betroffenes Set pending verwendet wird beziehungsweise von einem `RECORDING`-Command-Buffer referenziert wird, wird kein Set freigegeben. Solche Zustandskonflikte ergeben `INVALID_SYNCHRONIZATION_STATE`. Bei Erfolg werden alle angeforderten Sets sofort öffentlich ungültig; interne Referenzen bleiben bis zum Ende aller zulässigen Zugriffe erhalten.

## 6.7 `CreatePipelineLayout`

`CreatePipelineLayout` ist ein Void-Request und enthält:

- Offset 8: Device-XID
- Offset 12: Pipeline-Layout-XID
- Offset 16: `CARD16 set_layout_count`
- Offset 18: `CARD16 push_constant_range_count`
- Offset 20: Descriptor-Set-Layout-XID-Array
- danach Push-Constant-Range-Records mit jeweils 12 Bytes

Jeder Push-Constant-Range-Record enthält:

- `CARD32 stage_flags`
- `CARD32 offset`
- `CARD32 size`

Die Gesamtlänge des Requests beträgt `20 + 4 * set_layout_count + 12 * push_constant_range_count` Bytes.

`CreatePipelineLayout` prüft in dieser Reihenfolge: (1) exakte, count-konsistente Wire-Länge (`BadLength`); (2) reservierte Felder, nicht unterstützte Stage-Bits und ungültige Range-Feldwerte (`BadValue`); (3) Ziel-XID (`BadIDChoice`); (4) Device- und Set-Layout-XIDs in Wire-Reihenfolge (`BadValue` bei unbekannter/nicht-live XID); (5) Ressourcentyp, Ownership und Cross-Device-Zuordnung (`BadMatch`); (6) Device-Zustand (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (7) geräteabhängige Limits und Vulkan-Kompatibilität der Ranges/Layout-Kombination (`BadValue` oder `BadMatch` gemäß verletzter Regel), danach Backend-Erstellung (`ALLOCATION_FAILED` bei Allokationsfehler). Bei jedem Fehler bleibt die Pipeline-Layout-XID unangelegt.

Nach erfolgreicher Erstellung darf das Descriptor Set Layout öffentlich zerstört werden. Die internen Referenzen müssen den tatsächlichen Vulkan-Lebensdauerregeln entsprechen.

## 6.8 Compute Pipeline

`CreateComputePipeline` ist ein Void-Request. Die normative Gesamtlänge beträgt:

`28 + ((entry_point_length + 3) & ~3)`

- Offset 8: Device-XID
- Offset 12: Pipeline-XID
- Offset 16: Pipeline-Layout-XID
- Offset 20: Shader-Module-XID
- Offset 24: `CARD16 entry_point_length`
- Offset 26: `CARD16 reserved = 0`
- Offset 28: ASCII-Entry-Point ohne NUL, auf vier Bytes gepaddet

Der Entry-Point muss nichtleer sein und ausschließlich ASCII-Bytes enthalten; NUL ist nicht erlaubt. Padding-Bytes müssen null sein. Die Gesamtlänge muss exakt `28 + ((entry_point_length + 3) & ~3)` Bytes betragen; `entry_point_length` muss positiv sein. Specialization Constants werden in v0.1 nicht unterstützt. `CreateComputePipeline` prüft in dieser Reihenfolge: (1) exakte Wire-Länge (`BadLength`); (2) positiven Entry-Point-Count, nichtleere ASCII-Bytes ohne NUL und Null-Padding sowie reservierte Felder (`BadValue`); (3) Ziel-Pipeline-XID (`BadIDChoice`); (4) Device-, Pipeline-Layout- und Shader-Module-XIDs in Wire-Reihenfolge (`BadValue` bei unbekannter/nicht-live XID); (5) Ressourcentyp, Ownership und Cross-Device-Zuordnung (`BadMatch`); (6) Device-Zustand (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (7) Backend-Pipeline-Erstellung (`ALLOCATION_FAILED` bei Allokationsfehler; andere backendseitige Fehler folgen der zentralen Vulkan-Fehlerzuordnung). Die Erstellung ist atomar; bei Fehlern wird kein Pipeline-Objekt öffentlich angelegt.
