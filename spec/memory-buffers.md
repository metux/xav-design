# 5. Memory und Buffers

## 5.1 `CreateBuffer`

Gesamtlänge: 32 Bytes.

| Offset | Typ | Feld |
|---:|---|---|
| 8 | XID | `device_xid` |
| 12 | XID | `buffer_xid` |
| 16 | CARD64 | `size` in Bytes |
| 24 | CARD32 | `usage_flags` |
| 28 | CARD32 | `reserved = 0` |

Die Größe muss positiv sein. Buffer-Erstellung alloziert und bindet noch keinen Speicher.

Usage-Bits:

- Bit 0: `STORAGE_BUFFER`
- Bit 1: `TRANSFER_SRC`
- Bit 2: `TRANSFER_DST`
- Bit 3: `UNIFORM_BUFFER`
- Bit 4: `INDEX_BUFFER`
- Bit 5: `VERTEX_BUFFER`
- Bit 6: `INDIRECT_BUFFER`
- Bits 7–31: reserviert

Der Server darf keine Usage-Flags stillschweigend hinzufügen. Images sind in v0.1 nicht enthalten.

Für den initialen Compute-Test:

- A und B: `STORAGE_BUFFER | TRANSFER_DST`
- C: `STORAGE_BUFFER | TRANSFER_SRC`

## 5.2 `GetPhysicalDeviceMemoryProperties`

Request: Device-XID bei Offset 8, Gesamtlänge 12 Bytes.

Der Reply enthält nach dem 32-Byte-Header:

- `CARD32 memory_type_count`
- `CARD32 memory_heap_count`
- `CARD32 memory_properties_flags`
- `CARD32 reserved = 0`
- `MEMORYTYPEINFO[]`
- `MEMORYHEAPINFO[]`

`MEMORYTYPEINFO` ist 8 Bytes groß:

- `CARD32 property_flags`
- `CARD32 heap_index`

`MEMORYHEAPINFO` ist 16 Bytes groß:

- `CARD64 size`
- `CARD32 heap_flags`
- `CARD32 reserved = 0`

Memory-Type-Flags:

- Bit 0: `DEVICE_LOCAL`
- Bit 1: `HOST_VISIBLE`
- Bit 2: `HOST_COHERENT`
- Bit 3: `HOST_CACHED`
- Bit 4: `LAZILY_ALLOCATED`
- Bit 5: `PROTECTED`

Heap-Flag-Bit 0 bezeichnet `DEVICE_LOCAL`. Andere Bits sind reserviert.

Es gelten maximal 32 Memory Types und 16 Memory Heaps. Indizes beginnen bei null und bleiben während der Lebensdauer des logischen Devices stabil. Jeder Heap-Index muss gültig sein.

`memory_properties_flags` besitzt noch keine festgelegte Semantik; bis zur Zuweisung einer Registry-Definition muss das Feld null sein.

## 5.3 `GetBufferMemoryRequirements`

Request:

- Offset 8: Device-XID
- Offset 12: Buffer-XID
- Gesamtlänge: 16 Bytes

Reply:

| Offset | Typ | Feld |
|---:|---|---|
| 8 | CARD64 | `size` |
| 16 | CARD64 | `alignment` |
| 24 | CARD32 | `memory_type_bits` |
| 28 | CARD32 | `reserved = 0` |

Reply-Payload-Länge ist null. Größe und Alignment müssen positiv sein. Bits außerhalb der Anzahl unterstützter Memory Types müssen null sein.

## 5.4 `AllocateMemory`

Gesamtlänge: 32 Bytes.

- Offset 8: Device-XID
- Offset 12: Memory-XID
- Offset 16: `CARD64 allocation_size`
- Offset 24: `CARD32 memory_type_index`
- Offset 28: `CARD32 reserved = 0`

Die Allokationsgröße muss positiv sein, und der Memory-Type-Index muss existieren.

## 5.5 `BindBufferMemory`

Gesamtlänge: 28 Bytes.

- Offset 8: Device-XID
- Offset 12: Buffer-XID
- Offset 16: Memory-XID
- Offset 20: `CARD64 memory_offset`

Buffer und Memory müssen zum angegebenen Device gehören. In v0.1 darf ein Buffer nur einmal gebunden werden.

Der Memory-Type muss durch `memory_type_bits` erlaubt sein. Der Offset muss ein Vielfaches des gemeldeten Alignments sein.

Die Bounds-Prüfung muss überlaufsicher erfolgen:

- `memory_offset <= allocation_size`
- `requirements.size <= allocation_size - memory_offset`

Cross-Device-Nutzung, unpassender Memory-Type, doppeltes Binden, ungültiges Alignment oder unzureichender Speicher ergeben `BadMatch`.

## 5.6 `WriteBuffer`

Request:

- Offset 8: Device-XID
- Offset 12: Buffer-XID
- Offset 16: `CARD64 buffer_offset`
- Offset 24: `CARD32 data_length`
- Offset 28: Byte-Payload
- anschließend Null-Padding bis zur nächsten Vierbytegrenze

Gesamtlänge:

`28 + ((data_length + 3) & ~3)`

`data_length` muss positiv sein.

Der Buffer muss gebunden sein, `TRANSFER_DST` besitzen und den vollständigen Zielbereich abdecken. Bounds werden mit `buffer_offset <= buffer_size` und `data_length <= buffer_size - buffer_offset` geprüft.

Jeder `WriteBuffer`-Request ist ein eigenständiger Schreibvorgang. Es gibt weder Upload-ID noch einen mehrteiligen Upload-Transaktionszustand oder ein Final-Chunk-Flag.

Clients dürfen mehrere Requests im normalen X11-Request-Stream hintereinander senden. Jeder Request erhält seine eigene Sequenznummer und seinen eigenen Reply.

Ein erfolgreicher Reply garantiert:

1. Die Eingabedaten wurden übernommen.
2. Der Client darf seinen Eingabepuffer wiederverwenden.
3. Der Transfer ist abgeschlossen.
4. Die geschriebenen Bytes sind für nachfolgende abhängige XAverius-GPU-Arbeit sichtbar.

Der Server darf Staging-Speicher einsetzen. Er muss die korrekte Reihenfolge überlappender Writes und nachfolgender abhängiger GPU-Arbeit gewährleisten.

## 5.7 `ReadBuffer`

Request:

- Offset 8: Device-XID
- Offset 12: Buffer-XID
- Offset 16: `CARD64 buffer_offset`
- Offset 24: `CARD32 data_length`

Gesamtlänge: 28 Bytes.

Die Länge muss positiv sein. Der Buffer muss gebunden sein, `TRANSFER_SRC` besitzen und den angeforderten Bereich abdecken.

Der Reply enthält nach dem 32-Byte-Header die gelesenen Bytes ab Offset 32, mit Null-Padding auf vier Bytes. `reply.length = ceil(data_length / 4)`.

Der Reply darf erst gesendet werden, wenn die angeforderten Daten bereit sind und relevante vorherige GPU-Schreibzugriffe sowie erforderliche Host-Visibility- und Cache-Operationen abgeschlossen sind.

Eine konservative Implementierung darf für v0.1 das Device vollständig synchronisieren, wenn keine feinere Abhängigkeitsverfolgung vorhanden ist.
