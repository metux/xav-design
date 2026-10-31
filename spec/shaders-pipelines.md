# 6. Shaders, Descriptor Layouts, and Pipelines

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

If a continuation or `FINAL` chunk is malformed, has invalid padding, exceeds a limit, or otherwise fails validation, the request receives an X11 error and the matching in-progress upload is discarded. This cleanup applies only when the complete fixed request header is present so that `shader_module_xid` can be identified, and the request has `CREATE=0`. If the fixed header is truncated before that XID is available, no upload assembly can be identified and no assembly is modified. A rejected `CREATE=1` attempt never discards an already active assembly reserved under that XID; a syntactically valid duplicate CREATE returns `BadIDChoice`, while earlier framing or scalar errors retain their normal precedence. This prevents a malformed new-create attempt from destroying an unrelated in-progress upload. A failed `FINAL` also discards the assembly and leaves no live shader-module resource. After cleanup, the client may retry using the same XID if it remains a valid unused XID under normal X11 resource-ID rules. An `ABORT` of an existing upload discards it; an `ABORT` with no matching upload fails with the request-specific invalid-state error and changes nothing. Disconnect and device loss discard all affected incomplete uploads synchronously with respect to the connection/device state transition. A later chunk or ABORT for a discarded assembly finds no matching upload and fails with `INVALID_SYNCHRONIZATION_STATE`; it must not recreate or resurrect the old assembly. Chunk-validation and `FINAL`-creation failures are reported only as the synchronous X11 error for that request. They do not emit `ASYNC_ERROR`; device loss itself may emit the single device-level `DEVICE_LOST` event under the normal lifecycle rules, but must not emit a second upload-specific asynchronous error.

`ShaderModuleData` validation and error precedence are normative: (1) validate the X11 envelope and exact total length `20 + pad4(data_length)` with checked arithmetic (`BadLength`); (2) validate the request-specific flag combination, reserved flag bits, `data_length` constraints, and zero payload padding (`BadValue`); (3) for `CREATE`, validate `shader_module_xid` as a create-XID (`BadIDChoice` for an invalid or occupied XID); (4) resolve `device_xid` (`BadValue` for an unknown/non-live XID); (5) validate resource type and client/device ownership (`BadMatch`); (6) check logical-device state (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (7) check upload-assembly state and chunk-size/aggregate-size limits (`INVALID_SYNCHRONIZATION_STATE` for a missing assembly, `BadValue` for a size/limit violation); (8) on `FINAL`, validate the assembled SPIR-V and create the backend module (`BadValue` for invalid SPIR-V or `ALLOCATION_FAILED` for backend allocation failure, with other Vulkan failures mapped centrally). A failed phase MUST NOT execute later phases or mutate state except for the specified cleanup of the affected in-progress assembly. A failed `CREATE` leaves the target XID unallocated and creates no assembly. A failed continuation or `FINAL` discards the matching assembly atomically. Device loss discards all affected assemblies; after that transition, a request against the still-live lost device reports `DEVICE_LOST` before assembly lookup, while a missing assembly on an otherwise available device reports `INVALID_SYNCHRONIZATION_STATE`. This device-loss rule overrides the generic missing-assembly sentence above. Implementations must bound per-upload and aggregate assembly memory and must not allocate based on unchecked lengths.

SPIR-V validation and Vulkan shader-module creation occur atomically at `FINAL`: on success, the public resource becomes live; on failure, no public resource remains. `pNext` structures and Vulkan allocator callbacks are not transmitted in v0.1.

After successful creation of a Compute Pipeline, the Shader Module may be destroyed subject to Vulkan lifetime rules.

## 6.2 Descriptor Set Layout

`CreateDescriptorSetLayout` is a void request with the following wire layout. The total length is `24 + 16 * binding_count` bytes.

| Offset | Type | Field |
|---:|---|---|
| 8 | XID | `device_xid` |
| 12 | XID | `descriptor_set_layout_xid` |
| 16 | CARD32 | `flags`; MUST be zero in v0.1 |
| 20 | CARD32 | `binding_count` |
| 24 | BINDING[] | `binding_count` Binding-Records |

Each binding record is 16 bytes:

| Relative Offset | Type | Field |
|---:|---|---|
| 0 | CARD32 | `binding` |
| 4 | CARD32 | `descriptor_type` |
| 8 | CARD32 | `descriptor_count` |
| 12 | CARD32 | `stage_flags` |

The request MUST have exactly the length determined by `binding_count`. The total length MUST remain within the normal X11 request-size limit. `binding_count = 0` is permitted and creates an empty layout. For each record, `descriptor_count` MUST be greater than zero. Binding numbers MUST be unique within the layout; duplicate binding numbers invalidate the entire request.

`descriptor_type` and `stage_flags` use only the normative [Descriptor Type Registry](../registries/descriptor-types.md) and [Shader Stage Registry](../registries/shader-stages.md). Every value used MUST be supported in v0.1. The stage mask MUST contain no unknown or unsupported bits and MUST include at least one supported stage. Unsupported descriptor types are rejected; numeric values are not assigned locally in this chapter.

`flags` MUST be zero. Non-zero flags are rejected with `BadValue`; v0.1 does not accept layout flags that are silently ignored. `CreateDescriptorSetLayout` validates in this order: (1) exact count-consistent request length (`BadLength`); (2) flags, binding records, counts, unique binding numbers, descriptor types, and stage bits (`BadValue`); (3) target `descriptor_set_layout_xid` as a create-XID (`BadIDChoice` if invalid or occupied); (4) `device_xid` lookup (`BadValue` for unknown/non-live XID); (5) resource type and client/device ownership (`BadMatch`); (6) logical-device state (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (7) device-limit/descriptor support checks (`BadValue` or `BadMatch` as defined for the violated rule), then backend allocation (`ALLOCATION_FAILED`). Creation is atomic: on failure, no public descriptor set layout is created. Unknown or non-live device XIDs result in `BadValue`; a live resource of the wrong type or foreign device ownership results in `BadMatch`. An unavailable or lost logical device results in `DEVICE_UNAVAILABLE` or `DEVICE_LOST`, respectively; a backend allocation failure results in `ALLOCATION_FAILED`.

In the initial compute test, bindings 0, 1, and 2 are each created as `STORAGE_BUFFER` with descriptor count 1 and stage `COMPUTE`.

After successful pipeline-layout creation, the descriptor set layout may be publicly destroyed if the applicable Vulkan lifetime rules permit it. Internal references are retained according to Vulkan rules.

## 6.3 Descriptor Pool

`CreateDescriptorPool` has the following total length:

`24 + 8 * pool_size_count`

- Offset 8: Device-XID
- Offset 12: Descriptor-Pool-XID
- Offset 16: `CARD32 max_sets`
- Offset 20: `CARD16 pool_size_count`
- Offset 22: `CARD16 reserved = 0`
- Offset 24: Array aus 8-Byte-Entries

Jeder Pool-Entry enthält `CARD32 descriptor_type` und `CARD32 descriptor_count`.

`max_sets`, `pool_size_count` und alle Descriptor-Counts müssen positiv sein. Doppelte Pool-Size-Einträge sind ungültig. Da `CreateDescriptorPool` keine Pool-Flags vom Client entgegennimmt, `FreeDescriptorSets` aber Teil von v0.1 ist, MUSS der Server jeden Backend-`VkDescriptorPool` mit `VK_DESCRIPTOR_POOL_CREATE_FREE_DESCRIPTOR_SET_BIT` erzeugen. Dieses Flag ist serverseitig verpflichtend und nicht vom Client steuerbar; eine Implementierung darf es nicht weglassen.

**Normative Pool-Kapazität:** `max_sets` ist die maximale Anzahl gleichzeitig allozierter, öffentlich live Descriptor Sets im Pool. Jeder Pool-Size-Eintrag legt zusätzlich die Gesamtzahl der Deskriptoren dieses Typs fest, die über alle Sets dieses Pools gleichzeitig alloziert sein dürfen. Der Bedarf eines Sets ist für jeden Descriptor-Typ die Summe von `descriptor_count` über alle Bindings dieses Typs in seinem Layout; jedes allozierte Set verbraucht diesen Bedarf genau einmal. Mehrfaches Allozieren desselben Layouts zählt jedes Mal vollständig. `AllocateDescriptorSets` prüft den gesamten Batch gegen `max_sets` und sämtliche Typ-Kapazitäten, bevor es irgendeine Kapazität reserviert. Ein fehlender Pool-Size-Eintrag oder unzureichende Set-/Typ-Kapazität ist `ALLOCATION_FAILED`, nicht `BadMatch`. Erfolgreiche Allokation verbraucht die Kapazität atomar mit der Veröffentlichung aller Sets. Erfolgreiches `FreeDescriptorSets` gibt die Kapazität der ausgewählten Sets atomar zurück; `DestroyDescriptorPool` beendet die gesamte Pool-Kapazitätsbilanz. Bei abgewiesener Allokation oder Freigabe bleiben Set-Menge und alle Kapazitätszähler unverändert. Backend-Freigabe und interne Referenzretirement dürfen verzögert sein, ändern aber nicht den Zeitpunkt der öffentlichen Kapazitätsbuchung. `CreateDescriptorPool` prüft in dieser Reihenfolge: (1) exakte count-konsistente Request-Länge (`BadLength`); (2) positive Counts, doppelte Pool-Size-Typen, unterstützte Descriptor-Typen und reserviertes Feld (`BadValue`); (3) Ziel-Pool-XID als Create-XID (`BadIDChoice` bei ungültiger oder belegter XID); (4) Device-XID (`BadValue` bei unbekannter/nicht-live XID); (5) Ressourcentyp und Client-/Device-Ownership (`BadMatch`); (6) Device-Zustand (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (7) Backend-Allokation (`ALLOCATION_FAILED`). Unbekannte/nicht-live Device-XIDs ergeben `BadValue`; ein falscher live Ressourcentyp oder fremde Device-Ownership ergibt `BadMatch`. Ein nicht verfügbares oder verlorenes logisches Device ergibt `DEVICE_UNAVAILABLE` beziehungsweise `DEVICE_LOST`; ein Backend-Allokationsfehler ergibt `ALLOCATION_FAILED`. Die Erstellung ist atomar: bei jedem Fehler bleibt die Pool-XID unangelegt.

## 6.3.1 Destroy Descriptor Pool

`DestroyDescriptorPool` hat eine feste Gesamtlänge von 16 Bytes:

- Offset 8: Device-XID
- Offset 12: Descriptor-Pool-XID

Der Pool muss zum angegebenen logischen Device gehören. Der Request wird atomar abgewiesen, wenn ein enthaltenes Descriptor Set pending verwendet wird oder von einem `RECORDING`-Command-Buffer referenziert wird; der Fehler ist `INVALID_SYNCHRONIZATION_STATE`. Bei Ablehnung bleiben Pool, Sets und Command-Buffer-Zustände unverändert.

Bei Erfolg werden der Pool und alle enthaltenen Descriptor Sets öffentlich invalidiert. Nicht-pending `EXECUTABLE`-Command-Buffer, die eines dieser Sets referenzieren, werden `INVALID`. Interne Objekte bleiben erhalten, bis alle Referenzen und Backend-Zugriffe beendet sind.

Device loss alone does not prevent `DestroyDescriptorPool` and does not itself produce a `DEVICE_LOST` error for this logical cleanup. Normal atomic validation still applies: a child Set referenced by a `RECORDING` command buffer continues to block destruction. The client can destroy the relevant Command Pool first; after Device loss, the server MUST NOT start new GPU work and MUST retain internal references until safe quiescence or quarantine.

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

| Relative Offset | Type | Field |
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

Mehrere Writes desselben Descriptor-Slots innerhalb eines Requests sind ungültig und ergeben `BadValue`. `descriptor_type` muss ein zugewiesener Wert der Descriptor-Type-Registry sein; `0` und nicht zugewiesene Werte ergeben `BadValue`. Ein registrierter Descriptor-Typ, der nicht zum Typ des angegebenen Layout-Bindings passt, ergibt `BadMatch`. Ein fehlgeschlagener Request darf keine Teiländerungen hinterlassen. On successful update, descriptor-slot contents and their derived internal Buffer references are replaced atomically. Command buffers retain a reference to the Descriptor Set object when binding it; they do not store a snapshot of its slot contents. A non-pending `EXECUTABLE` command buffer therefore uses the set's current descriptor contents at later submission time. A successful update does not invalidate such a command buffer solely because descriptor contents changed.

`UpdateDescriptorSets` verwendet diese normative Fehlerpräzedenz; alle Phasen werden für den gesamten Request abgeschlossen, bevor irgendein Slot oder eine Referenz geändert wird:

1. Exakte Gesamtlänge `20 + 36 * write_count` mit geprüfter Arithmetik und X11-Requestlimit (`BadLength`). Trunkierung, zusätzliche Bytes und Count-/Längenabweichungen sind Fehler.
2. Feldlokale Syntaxprüfung aller Writes (`BadValue`): `write_count > 0`, beide Reserved-Felder null, alle typunabhängigen Feldwerte gültig, `descriptor_type` registriert/zugewiesen, und kein Descriptor-Slot (Set-XID, Binding, Array-Element) wird mehrfach beschrieben. Mehrere unterschiedliche Slots desselben Sets sind zulässig.
3. Auflösung aller XIDs in Wire-Reihenfolge (`BadValue` für unbekannte/nicht-live XIDs): zuerst `device_xid`, danach für jeden Write Set-XID und Buffer-XID in Array-Reihenfolge. Kein Ressourcentyp- oder Device-State-Check darf die vollständige XID-Auflösung unterbrechen.
4. Validierung der aufgelösten Ressourcen (`BadMatch`): erwartete Ressourcentypen, Client-Ownership, Device-Zuordnung und Buffer-/Set-Zuordnung. Ein live XID mit falschem Typ oder fremder Ownership ist `BadMatch`.
5. Device-Verfügbarkeit (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`). Dieser Check erfolgt nach sämtlichen XID-/Typ-/Ownership-Prüfungen, aber vor jeder Binding-, Layout-, Slot-, Usage-, Alignment-, Range-, Limit- oder Pending-Prüfung. Device Loss gewinnt daher gegen jeden solchen späteren Fehler.
6. Prüfung aller Writes auf Layout-/Binding-/Array-Slot-/Descriptor-Typ-Kompatibilität, Buffer-Bindung und erforderliche Usage-Flags, Alignment, nichtleere/zulässige Range, Überlauf und Geräte-Limits (`BadMatch`). Die Writes werden in Wire-Reihenfolge geprüft; die erste inkompatible Write bestimmt den Fehler.
7. Prüfung aller betroffenen Sets auf bereits angenommene GPU-Arbeit, die deren Descriptor-Inhalte verwenden kann (`INVALID_SYNCHRONIZATION_STATE`). Ein einziges betroffenes pending Set weist den gesamten Request ab. Diese Prüfung erfolgt erst, nachdem jede Write-Kompatibilitätsprüfung erfolgreich war.

Ein späterer Fehler darf keinen früheren überstimmen. Insbesondere schlagen `BadLength` und `BadValue` vor XID-Fehlern, XID-Fehler vor `BadMatch` aus Typ/Ownership, Typ/Ownership vor Device Loss, und Device Loss vor Layout-/Buffer-/Pending-Fehlern.

**Atomarer Commit und Rollback:** Der Server MUSS zunächst für jede Write den vollständigen neuen Slot-Inhalt validieren und alle dafür benötigten internen Buffer-Referenzen vorbereiten/retainen, ohne bestehende Slots zu verändern. Scheitert irgendeine Validierung oder Referenzvorbereitung, werden sämtliche in diesem Request vorbereiteten Referenzen freigegeben; alle bisherigen Slot-Inhalte und Referenzkanten bleiben exakt unverändert. Nach erfolgreicher Vorbereitung werden sämtliche betroffenen Slots und die zugehörigen internen Referenzkanten in einem serialisierten Commit gemeinsam ersetzt. Erst nach diesem Commit dürfen alte Slot-Referenzen freigegeben werden. Es darf weder einen sichtbaren Zwischenzustand mit nur einem Teil der Writes noch ein Fenster geben, in dem ein alter Buffer bereits freigegeben ist, bevor seine Ersatzreferenz gesichert wurde. Der Request löst keine asynchrone Arbeit aus; jede synchrone Ablehnung erzeugt genau einen X11-Fehler und keine Teiländerung.

Command buffers retain a reference to the Descriptor Set object when binding it; they do not store a snapshot of its slot contents. A non-pending `EXECUTABLE` command buffer therefore uses the set's current descriptor contents at later submission time. A successful update does not invalidate such a command buffer solely because descriptor contents changed.

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

`CreatePipelineLayout` prüft in dieser Reihenfolge: (1) exakte, count-konsistente Wire-Länge (`BadLength`); (2) reservierte Felder, nicht unterstützte Stage-Bits und ungültige Range-Feldwerte (`BadValue`); (3) Ziel-XID (`BadIDChoice`); (4) Device- und Set-Layout-XIDs in Wire-Reihenfolge (`BadValue` bei unbekannter/nicht-live XID); (5) Ressourcentyp, Ownership und Cross-Device-Zuordnung (`BadMatch`); (6) Device-Zustand (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (7) geräteabhängige Limits und Vulkan-Kompatibilität der Ranges/Layout-Kombination (`BadValue` oder `BadMatch` gemäß verletzter Regel), danach Backend-Erstellung (`ALLOCATION_FAILED` bei Allokationsfehler). Bei jedem Fehler bleibt die Pipeline-Layout-XID unangelegt. Diese Reihenfolge ist auch bei mehreren gleichzeitigen Fehlern verbindlich: insbesondere hat ein ungültiges/belegtes Ziel-XID Vorrang vor unbekannten Eingabe-XIDs; Device Loss hat Vorrang vor geräteabhängigen Kompatibilitätsprüfungen und Backend-Erstellung.

Nachdem alle beabsichtigten `CreatePipelineLayout`- und `AllocateDescriptorSets`-Requests mit diesem Layout abgeschlossen sind, darf das Descriptor Set Layout öffentlich zerstört werden. Die öffentliche XID wird dadurch sofort ungültig, sodass keine neuen Pipeline Layouts oder Descriptor Sets mehr über diese XID angelegt werden können. Bereits alloziierte Descriptor Sets bleiben jedoch gültig und updatefähig: jedes Set hält die unveränderliche Layout-Definition und die benötigte interne Backend-Layout-Identität fest. Die tatsächliche Freigabe des Backend-Layouts wird bis zur Freigabe aller davon allozierten Sets und bis zum Ende sämtlicher Backend-Zugriffe aufgeschoben. Ein erfolgreicher `DestroyResource` auf dem Descriptor Set Layout darf daher weder bestehende Sets unbrauchbar machen noch spätere `UpdateDescriptorSets`-Requests für diese Sets allein wegen der ungültigen Layout-XID ablehnen.

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

Der Entry-Point muss nichtleer sein und ausschließlich ASCII-Bytes enthalten; NUL ist nicht erlaubt. Padding-Bytes müssen null sein. Die Gesamtlänge muss exakt `28 + ((entry_point_length + 3) & ~3)` Bytes betragen; `entry_point_length` muss positiv sein. Specialization Constants werden in v0.1 nicht unterstützt. `CreateComputePipeline` prüft in dieser Reihenfolge: (1) exakte Wire-Länge (`BadLength`); (2) positiven Entry-Point-Count, nichtleere ASCII-Bytes ohne NUL und Null-Padding sowie reservierte Felder (`BadValue`); (3) Ziel-Pipeline-XID (`BadIDChoice`); (4) Device-, Pipeline-Layout- und Shader-Module-XIDs in Wire-Reihenfolge (`BadValue` bei unbekannter/nicht-live XID); (5) Ressourcentyp, Ownership und Cross-Device-Zuordnung (`BadMatch`); (6) Device-Zustand (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (7) Backend-Pipeline-Erstellung (`ALLOCATION_FAILED` bei Allokationsfehler; andere backendseitige Fehler folgen der zentralen Vulkan-Fehlerzuordnung). Die Erstellung ist atomar; bei Fehlern wird kein Pipeline-Objekt öffentlich angelegt. Die Fehlerpräzedenz gilt auch bei Mehrfachfehlern: ein ungültiges/belegtes Ziel-XID ergibt `BadIDChoice` vor der Auflösung von Device, Pipeline-Layout und Shader-Modul; unbekannte/nicht-live Eingabe-XIDs ergeben `BadValue` vor Typ-/Ownership-Prüfungen (`BadMatch`), und Device Loss wird vor Backend-Erstellung gemeldet. Ein abgewiesener Request reserviert die Ziel-XID nicht.

Eine erfolgreich erstellte Pipeline behält eine interne Referenz auf die bei `CreateComputePipeline` angegebene Pipeline-Layout-Definition und deren Backend-Identität. `DestroyResource` darf die öffentliche PipelineLayout-XID invalidieren, sobald keine direkte RECORDING- oder Pending-Referenz die Zerstörung blockiert; eine davon abhängige bestehende Pipeline bleibt dabei live. Die interne Pipeline-Layout-Ressource darf erst freigegeben werden, wenn alle davon abhängigen Pipelines zerstört sind und keine Backend-Zugriffe mehr möglich sind. Ein späterer `CreateComputePipeline`-Request mit der invalidierten PipelineLayout-XID ergibt `BadValue`. Command Buffers, die das Pipeline Layout direkt referenzieren, folgen weiterhin den normalen RECORDING-/EXECUTABLE-Invalidierungsregeln.


### Descriptor-slot replacement and concurrent release invariants

A successful `UpdateDescriptorSets` is one atomic transition over the complete write batch. Validation MUST finish for every write before any slot or reference is changed. The server MUST prepare the replacement slot values and their derived Buffer-reference edges, then commit all slot changes and retire the superseded edges as one serialized operation for each affected Descriptor Set. If any write fails, no slot value or reference edge from the request is committed. Duplicate writes to one slot remain invalid even if they would write identical values.

Each slot owns exactly the internal Buffer reference represented by its committed value, if any. Replacing a slot MUST acquire/establish the new reference before making the new value visible, and MUST retire the old reference exactly once after the replacement is committed. Repeating an update with the same Buffer and range MUST NOT leak a reference or retire the still-current reference. Command-buffer derived references are recomputed from the committed set contents: a non-pending command buffer referencing the set retains the set-object reference, while its derived Buffer references must match the current slots, without duplicate ownership edges for the same slot. A Buffer removed from all slots and all other owners MUST cease to be a dependency of those command buffers; a later destruction of that Buffer MUST NOT invalidate them for the removed edge.

Updates to a Descriptor Set MUST be serialized with submission acceptance and set release. If a submission is accepted first, the set is pending and the update is rejected with `INVALID_SYNCHRONIZATION_STATE` without mutation. If the update commits first, a subsequently accepted submission observes the new complete slot contents. There is no intermediate state in which a submission can observe a partially applied write batch. A request racing with `FreeDescriptorSets` or `DestroyDescriptorPool` is ordered at the same server-side state transition: if release wins, the update fails against the invalid set and creates no references; if update wins, release applies its ordinary validation to the resulting set and reference graph. Pool-wide release is atomic across all child sets.

`FreeDescriptorSets` and `DestroyDescriptorPool` MUST first validate the entire target set collection and all pending/recording blockers, then invalidate the relevant public XIDs and transition non-pending executable command buffers that reference those sets to `INVALID` as one atomic operation. Rejection leaves every target set, pool, command-buffer state, slot value, and internal reference unchanged. On success, each descriptor-slot edge and each command-buffer-to-set/derived-buffer edge is retired exactly once by its owning cleanup path; public invalidation alone does not permit freeing a Buffer or its bound Memory while a submission, active operation, or backend access still retains the old internal identity. Concurrent cleanup callbacks MUST use captured internal identities and idempotent edge-retirement state, never re-resolve numeric XIDs.
