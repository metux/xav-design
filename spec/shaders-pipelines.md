# 6. Shader, Descriptor-Layouts und Pipelines

## 6.1 Shader Modules

`CreateShaderModule` überträgt SPIR-V explizit. `DestroyShaderModule` zerstört die öffentliche Ressource.

`pNext`-Strukturen und Vulkan-Allocator-Callbacks werden in v0.1 nicht über das Protokoll übertragen. Die genauen Wire-Layouts und Subopcode-Zuweisungen sind noch offen.

Nach erfolgreicher Erstellung einer Compute-Pipeline darf das Shader Module öffentlich zerstört werden, soweit dies mit den Vulkan-Lebensdauerregeln vereinbar ist.

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
