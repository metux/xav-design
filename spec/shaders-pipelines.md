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

If a chunk is malformed, has invalid padding, exceeds a limit, or otherwise fails validation, the request receives an X11 error and the entire in-progress upload for that XID is discarded. A failed `FINAL` also discards the assembly and leaves no live shader-module resource. After cleanup, the client may retry using the same XID if it remains a valid unused XID under normal X11 resource-ID rules. An `ABORT` of an existing upload discards it; an `ABORT` with no matching upload fails with the request-specific invalid-state error and changes nothing. Disconnect and device loss discard all affected incomplete uploads. Implementations must bound per-upload and aggregate assembly memory and must not allocate based on unchecked lengths.

SPIR-V validation and Vulkan shader-module creation occur atomically at `FINAL`: on success, the public resource becomes live; on failure, no public resource remains. `pNext` structures and Vulkan allocator callbacks are not transmitted in v0.1.

After successful creation of a Compute Pipeline, the Shader Module may be destroyed subject to Vulkan lifetime rules.

## 6.2 Descriptor Set Layout

Die Binding-Records von `CreateDescriptorSetLayout` sind jeweils 16 Bytes groß.

| Relativer Offset | Typ | Feld |
|---:|---|---|
| 0 | CARD32 | `binding` |
| 4 | CARD32 | `descriptor_type` |
| 8 | CARD32 | `descriptor_count` |
| 12 | CARD32 | `stage_flags` |

Im initialen Compute-Test werden Bindings 0, 1 und 2 jeweils als `STORAGE_BUFFER`, Anzahl 1 und `COMPUTE_SHADER` angelegt.

Binding-Nummern müssen innerhalb eines Layouts eindeutig sein. Die Descriptor-Anzahl muss positiv sein. Descriptor-Type- und Stage-Flag-IDs müssen zentral registriert werden.

Nach erfolgreicher Pipeline-Layout-Erstellung darf das Descriptor Set Layout öffentlich zerstört werden, wenn keine Vulkan-Regel eine weitere Lebensdauer verlangt.

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

`max_sets` und alle Descriptor-Counts müssen positiv sein. Doppelte Pool-Size-Einträge sind ungültig.

## 6.4 Allocate Descriptor Sets

Fester Header: 20 Bytes.

- Offset 8: Device-XID
- Offset 12: Descriptor-Pool-XID
- Offset 16: `CARD16 descriptor_set_count`
- Offset 18: `CARD16 reserved = 0`
- Offset 20: `DESCRIPTORSETALLOCATION[]`

Jeder Allocation-Entry ist acht Bytes groß und enthält Descriptor-Set-XID sowie Descriptor-Set-Layout-XID.

Gesamtlänge: `20 + 8 * descriptor_set_count`.

Die Allokation ist atomar. Bei einem Fehler darf keine Teilmenge der Sets öffentlich angelegt bleiben.

## 6.5 Update Descriptor Sets

Fester Header: 20 Bytes.

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

Mehrere Writes desselben Descriptor-Slots innerhalb eines Requests sind ungültig. Ein fehlgeschlagener Request darf keine Teiländerungen hinterlassen.

Ein Descriptor Set darf nicht aktualisiert werden, solange eine angenommene Submission es verwenden kann. In diesem Fall wird `INVALID_SYNCHRONIZATION_STATE` zurückgegeben.

## 6.6 Free Descriptor Sets

Fester Header: 20 Bytes.

- Offset 8: Device-XID
- Offset 12: Descriptor-Pool-XID
- Offset 16: `CARD16 descriptor_set_count`
- Offset 18: `CARD16 reserved = 0`
- Offset 20: Array aus Descriptor-Set-XIDs

Gesamtlänge: `20 + 4 * descriptor_set_count`.

Erfolgreich freigegebene Sets werden sofort öffentlich ungültig. Ein Set, das noch ausstehend verwendet wird, darf nicht freigegeben werden.

## 6.7 Pipeline Layout

`CreatePipelineLayout` enthält:

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

Der Server prüft Device-Ownership, Set-Layout- und Push-Constant-Limits, Stage-Masks, Offsets, Größen und Vulkan-Kompatibilitätsregeln.

Nach erfolgreicher Erstellung darf das Descriptor Set Layout öffentlich zerstört werden. Die internen Referenzen müssen den tatsächlichen Vulkan-Lebensdauerregeln entsprechen.

## 6.8 Compute Pipeline

Vorgeschlagene Gesamtlänge von `CreateComputePipeline`:

`28 + ((entry_point_length + 3) & ~3)`

- Offset 8: Device-XID
- Offset 12: Pipeline-XID
- Offset 16: Pipeline-Layout-XID
- Offset 20: Shader-Module-XID
- Offset 24: `CARD16 entry_point_length`
- Offset 26: `CARD16 reserved = 0`
- Offset 28: ASCII-Entry-Point ohne NUL, auf vier Bytes gepaddet

Der Entry-Point muss nichtleer sein. Specialization Constants werden in v0.1 nicht unterstützt. Die Erstellung ist atomar.
