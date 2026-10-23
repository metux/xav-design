# 7. Command Pools, Command Buffer und Command Streams

## 7.1 Command Pools

`CreateCommandPool` hat eine feste Gesamtlänge von 24 Bytes:

| Offset | Typ | Feld |
|---:|---|---|
| 8 | XID | `device_xid` |
| 12 | XID | `command_pool_xid` |
| 16 | CARD32 | `queue_family_index` |
| 20 | CARD32 | `flags` |

In v0.1 sind die Pool-Flags:

- Bit 0: `TRANSIENT`
- Bit 1: `RESET_COMMAND_BUFFER`
- Bits 2–31: reserviert und müssen null sein.

Der Queue-Family-Index muss zu einer Queue-Family des logischen Devices gehören, die Command Buffers unterstützt. Unbekannte/nicht-live Device-XIDs ergeben `BadValue`; ein falscher live Ressourcentyp oder fremde Device-Ownership ergibt `BadMatch`; ein ungültiger Queue-Family-Index ergibt `BadValue`. Ein nicht verfügbares oder verlorenes logisches Device ergibt `DEVICE_UNAVAILABLE` beziehungsweise `DEVICE_LOST`; ein Backend-Allokationsfehler ergibt `ALLOCATION_FAILED`. Die Erstellung ist atomar: bei jedem Fehler bleibt die Pool-XID unangelegt. Der Server darf keine Flags stillschweigend hinzufügen. `TRANSIENT` ist ein Hinweis zur Optimierung und ändert keine beobachtbare Semantik. `RESET_COMMAND_BUFFER` erlaubt den expliziten Request `ResetCommandBuffer` für einzelne nicht-pending Command Buffer. Ohne dieses Flag muss `ResetCommandBuffer` mit `INVALID_SYNCHRONIZATION_STATE` abgewiesen werden. 

`DestroyCommandPool` hat eine feste Gesamtlänge von 16 Bytes: `device_xid` bei Offset 8 und `command_pool_xid` bei Offset 12.

`ResetCommandBuffer` ist ein Void-Request mit fester Gesamtlänge von 16 Bytes:

| Offset | Typ | Feld |
|---:|---|---|
| 8 | XID | `device_xid` |
| 12 | XID | `command_buffer_xid` |

Das angegebene logische Device und der Command Buffer müssen live sein und zusammengehören. Unbekannte/nicht-live Device- oder Buffer-XIDs ergeben `BadValue`; ein falscher live Ressourcentyp, fremde Client-Ownership oder Cross-Device-Verwendung ergibt `BadMatch`. Nach erfolgreicher XID-/Ownership-Prüfung ergibt ein nicht verfügbares Device `DEVICE_UNAVAILABLE` und ein verlorenes Device `DEVICE_LOST`. Erst danach prüft der Server das `RESET_COMMAND_BUFFER`-Flag des zugehörigen Pools und den Buffer-Zustand. Fehlt das Flag oder ist der Buffer pending, wird der Request mit `INVALID_SYNCHRONIZATION_STATE` abgewiesen. Sämtliche Prüfungen erfolgen vor jeder Zustandsänderung.

Bei Erfolg setzt `ResetCommandBuffer` einen Buffer aus `INITIAL`, `RECORDING`, `EXECUTABLE` oder `INVALID` auf `INITIAL` zurück. Alle aufgezeichneten Entries und ihre Ressourcenreferenzen werden verworfen. Bei Ablehnung bleiben Zustand, Entries und Referenzen unverändert. Das Zurücksetzen eines `RECORDING`-Buffers verwirft damit auch eine noch nicht finalisierte Aufzeichnung.

`TRANSIENT` und `RESET_COMMAND_BUFFER` sind unabhängige Bits. `TRANSIENT` ändert weder Zulässigkeit noch Ergebnis von Reset-Operationen. Reservierte Bits müssen null sein; der Server darf weder unbekannte Flags akzeptieren noch Flags stillschweigend ergänzen. 

Ein Command Pool ist Elternobjekt der daraus allozierten Command Buffer. Die Zerstörung des Pools invalidiert die öffentlichen XIDs aller zugehörigen Command Buffer atomar. In v0.1 wird die Pool-Zerstörung abgelehnt, solange ein Kind-Command-Buffer ausstehend ausgeführt wird.

## 7.2 Command-Buffer-Zustände

Vorgesehene Zustände:

- `INITIAL`
- `RECORDING`
- `EXECUTABLE`
- `PENDING`
- `INVALID`

Übergänge:

- Allokation → `INITIAL`
- Create-Chunk von `CommandBufferData` → `RECORDING`
- erfolgreicher FINAL-Chunk → `EXECUTABLE`
- angenommene Submission → `PENDING`
- erfolgreiche Ausführung → `EXECUTABLE`
- asynchroner Ausführungsfehler oder Device Loss → nach Ende der Pending-Phase `INVALID`
- Pool- oder Device-Zerstörung → öffentliche XID ungültig

Es gibt in v0.1 keinen separaten `FAILED`-Command-Buffer-Zustand. Eine fehlgeschlagene Submission macht jeden davon betroffenen Command Buffer nach Ende der Pending-Phase `INVALID`. Er darf nicht erneut eingereicht werden; er muss zurückgesetzt und neu aufgezeichnet werden. Ein fehlgeschlagener Command Buffer wird niemals automatisch wieder `EXECUTABLE`.

Ein `PENDING`-Command-Buffer darf nicht verändert, zurückgesetzt, freigegeben oder erneut eingereicht werden. Gleichzeitige ausstehende Submissions desselben Command Buffers sind in v0.1 nicht vorgesehen.

Der Server verfolgt die direkten und indirekten Ressourcenreferenzen jedes aufgezeichneten Command Buffers. Das Binden eines Descriptor Sets zeichnet eine Referenz auf das Set-Objekt auf; die Descriptor-Slot-Inhalte werden nicht als unveränderlicher Snapshot in den Command Buffer kopiert. Ein erfolgreiches `UpdateDescriptorSets` aktualisiert atomar die abgeleiteten Buffer-Referenzen aller nicht-pending Command Buffer, die das betroffene Set referenzieren. Ein nicht-pending `EXECUTABLE`-Command-Buffer verwendet bei Submission die aktuellen Inhalte des gebundenen Sets und wird allein durch ein erfolgreiches Descriptor-Update nicht invalidiert. Wird eine referenzierte Ressource während `RECORDING` zerstört, muss der Destroy-Request abgewiesen werden. Wird sie zerstört, während der Command Buffer `EXECUTABLE` ist und nicht pending verwendet wird, wechselt der Command Buffer vor erfolgreichem Abschluss der Zerstörung in `INVALID`. Ein solcher Command Buffer muss neu aufgezeichnet werden, bevor er erneut eingereicht werden darf. Eine angenommene Submission behält ihre internen Ressourcenreferenzen bis zum terminalen Abschluss.

## 7.3 `CommandBufferData`

`CommandBufferData` ist ein Void-Request. Seine Gesamtlänge beträgt mindestens 16 Bytes und ist durch die Summe des 16-Byte-Headers und der vollständigen Command-Entries bestimmt; der Payload muss vollständig aus ganzen Entries bestehen. Bei `ABORT` muss die Gesamtlänge exakt 16 Bytes betragen.

Wire-Layout:

- Offset 0: X11-Header
- Offset 4: XAverius-Common-Header
- Offset 8: `CARD32 command_buffer_xid`
- Offset 12: `CARD32 command_pool_xid`
- Offset 16: Command-Entries

Flags im Common-Header:

| Bit | Name | Bedeutung |
|---:|---|---|
| 0 | `CREATE` | Command Buffer neu anlegen und Recording beginnen |
| 1 | `FINAL` | Letzten Chunk anhängen und Recording beenden |
| 2 | `ABORT` | Laufendes Recording verwerfen und Buffer auf `INITIAL` zurücksetzen |
| 3–7 | reserviert | Müssen null sein |

Zulässige Kombinationen:

| CREATE | FINAL | ABORT | Bedeutung |
|---:|---:|---:|---|
| 0 | 0 | 0 | Entries an einen bereits aufzeichnenden Buffer anhängen |
| 0 | 1 | 0 | Letzte Entries anhängen und Recording beenden |
| 1 | 0 | 0 | Command Buffer erstellen, Recording beginnen, ersten Chunk aufzeichnen |
| 1 | 1 | 0 | Command Buffer erstellen, kompletten Stream aufzeichnen und beenden |
| 0 | 0 | 1 | Recording abbrechen; keine Entries erlaubt |

Alle anderen Kombinationen sind ungültig. Ein ABORT-Request muss außer dem festen Header keine Payload enthalten. `command_pool_xid` muss auch bei ABORT dem Pool des Buffers entsprechen.

`FINAL` entspricht dem Ende der Aufzeichnung. Ein separater `EndCommandBuffer`-Request ist nicht vorgesehen.

Chunks dürfen nur zwischen vollständigen Command-Entries geteilt werden. Kein einzelner Entry darf über mehrere Requests verteilt sein.

## 7.4 Entry-Header

Jeder Entry beginnt mit:

```c
CARD16 command_id;
CARD16 entry_length; /* 32-bit words, including header and padding */
```

Maximale Entry-Größe: 65535 Wörter beziehungsweise 262140 Bytes. Jeder Entry muss vollständig in einen X11-Request passen.

Command-IDs sind in der [Command-Entry-Registry](../registries/command-entries.md) numerisch festgelegt. Sie sind XAverius-Wire-IDs und dürfen nicht als native Vulkan-Command-IDs interpretiert werden.

## 7.5 Unterstützte Command-Entries

### `CMD_BIND_PIPELINE`

Gesamtlänge: 8 Bytes.

- Relativer Offset 0: `CARD16 command_id`
- Offset 2: `CARD16 entry_length = 2`
- Offset 4: Pipeline-XID

### `CMD_BIND_DESCRIPTOR_SETS`

- Relativer Offset 0: `CARD16 command_id`
- Offset 2: `CARD16 entry_length`
- Offset 4: Pipeline-Layout-XID
- Offset 8: `CARD32 first_set`
- Offset 12: `CARD16 descriptor_set_count`
- Offset 14: `CARD16 reserved = 0`
- Offset 16: Descriptor-Set-XID-Array

Gesamtlänge: `16 + 4 * descriptor_set_count`.

Entry-Länge: `4 + descriptor_set_count` Wörter.

### `CMD_DISPATCH`

Gesamtlänge: 16 Bytes.

- Relativer Offset 0: `CARD16 command_id`
- Offset 2: `CARD16 entry_length = 4`
- Offset 4: `CARD32 group_count_x`
- Offset 8: `CARD32 group_count_y`
- Offset 12: `CARD32 group_count_z`

Die Dispatch-Werte müssen innerhalb der vom Device unterstützten Limits liegen.

### `CMD_PUSH_CONSTANTS`

- Relativer Offset 0: `CARD16 command_id`
- Offset 2: `CARD16 entry_length`
- Offset 4: `CARD32 stage_flags`
- Offset 8: Pipeline-Layout-XID
- Offset 12: `CARD32 offset`
- Offset 16: `CARD32 data_length`
- Offset 20: Datenbytes, danach Null-Padding bis zur Vierbytegrenze

Entry-Länge: `5 + ceil(data_length / 4)` Wörter.

Für v0.1 muss `stage_flags` exakt dem in der [Shader-Stage-Registry](../registries/shader-stages.md) definierten `COMPUTE`-Bit entsprechen. `offset` und `data_length` müssen Vielfache von vier sein. `data_length` muss positiv sein.

Der Bereich muss innerhalb von `maxPushConstantsSize` liegen und von einem kompatiblen Push-Constant-Range des angegebenen Pipeline Layouts abgedeckt werden.

Die Datenbytes sind opak. Wire-Padding gehört nicht zum Push-Constant-Bereich.


### `CMD_COPY_BUFFER_TO_SWAPCHAIN_IMAGE` — presentation-capable profile only

This entry is a minimal pixel-production path for the first on-screen presentation profile; it does not add general Vulkan Image resources or graphics pipelines. It copies a tightly or explicitly row-pitched rectangle from a Buffer into one acquired Swapchain image. The entry is valid only when the source Buffer has `TRANSFER_SRC` usage, the selected Swapchain was created with `TRANSFER_DST` image usage, and the referenced image is currently `ACQUIRED` at the point the command is validated for submission.

Fixed total length: 36 bytes; `entry_length = 9) words.

- Relative offset 0: `CARD16 command_id`
- Relative offset 2: `CARD16 entry_length = 9`
- Relative offset 4: Buffer-XID
- Relative offset 8: Swapchain-XID
- Relative offset 12: `CARD32 image_index`
- Relative offset 16: `CARD64 buffer_offset`
- Relative offset 24: `CARD32 row_length` in texels; zero means the Swapchain width
- Relative offset 28: `CARD32 image_height` in texels; zero means the Swapchain height
- Relative offset 32: `CARD32 reserved = 0`

The copy covers the entire Swapchain extent. The effective row length and image height must be at least the image width and height. Pixel size is four bytes for the initial RGBA8_UNORM and BGRA8_UNORM formats. The server must calculate the last byte read using overflow-safe wide arithmetic; the required source span is `4 * (effective_row_length * (height - 1) + width)` bytes from `buffer_offset`. The complete span must lie within the source Buffer, and `buffer_offset` must be four-byte aligned. The Swapchain image's format determines channel order; this command does not convert formats or color spaces.

The server manages the image's backend layout transitions required for the copy. Queue ordering and cross-queue visibility still follow the ordinary XAverius submission/semaphore rules; the entry does not imply that a later presentation waits for this copy unless the client establishes a dependency (for example, by signaling a binary semaphore in the submission and supplying it to QueuePresent).

A command buffer referencing a Swapchain image retains an internal reference to the Swapchain. Destroying the Swapchain is rejected while a recording command buffer refers to it; non-pending executable command buffers that refer to it are invalidated atomically when the Swapchain is successfully destroyed. At submission acceptance, the referenced image must be ACQUIRED and the command must not race a presentation transition. A pending submission retains the image until its terminal outcome and all backend accesses end.

This entry's numeric ID must be allocated append-only in the [command-entry registry](../registries/command-entries.md) before an implementation advertises support. It is not part of the current compute-only v0.1 entry set.

## 7.6 Command-Validierung

Der Server validiert Command-Buffer-Zustand, Entry-Längen, Ressourcen-Typen, Device-Ownership, reservierte Felder, Pipeline- und Layout-Kompatibilität, Descriptor-Bindings, Push-Constant-Ranges und Dispatch-Limits.

Ein ungültiger `CommandBufferData`-Request darf keine seiner Entries teilweise anhängen. Die vollständigen Entries des aktuellen Requests werden erst nach erfolgreicher Validierung aller Entries atomar an den Recording-Stream angehängt. Scheitert ein Chunk, bleibt der Command Buffer im Zustand `RECORDING`; zuvor erfolgreich angehängte Chunks bleiben erhalten, der fehlgeschlagene Chunk wird vollständig verworfen. Der Client kann einen korrigierten Chunk senden oder das Recording mit `ABORT` verwerfen. `ABORT` setzt einen nicht-pending Command Buffer auf `INITIAL` und verwirft alle bis dahin aufgezeichneten Entries und Ressourcenreferenzen. Dieses `ABORT` ist ausschließlich die Recovery-Operation für ein laufendes, chunk-basiertes `CommandBufferData`-Recording und benötigt deshalb nicht das Pool-Flag `RESET_COMMAND_BUFFER`; es ersetzt nicht den expliziten `ResetCommandBuffer`-Request für bereits abgeschlossene oder anderweitig ungültige Buffer. Ein fehlgeschlagener CREATE-Request hinterlässt weder einen Command Buffer noch einen Pool-Kind-Eintrag. Ein fehlgeschlagener FINAL-Chunk lässt den Buffer im Zustand `RECORDING`, sodass der Client korrigierte letzte Entries senden oder abbrechen kann. ABORT ist nicht zulässig, wenn der Buffer nicht `RECORDING` oder bereits pending ist.
