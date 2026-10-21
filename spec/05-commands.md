# 7. Command Pools, Command Buffer und Command Streams

## 7.1 Command Pools

`CreateCommandPool` und `DestroyCommandPool` verwalten die Allokation von Command Buffers. Die genauen Request-Layouts und Subopcodes müssen noch festgelegt werden.

Ein Command Pool ist Elternobjekt der daraus allozierten Command Buffer. Die Zerstörung des Pools invalidiert die öffentlichen XIDs aller zugehörigen Command Buffer.

In v0.1 wird die Pool-Zerstörung abgelehnt, solange ein Kind-Command-Buffer ausstehend ausgeführt wird.

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
- asynchroner Fehler oder Device Loss → terminaler Fehlerzustand
- Pool- oder Device-Zerstörung → öffentliche XID ungültig

Ob der terminale Fehlerzustand `INVALID` oder ein separater `FAILED`-Zustand ist, muss noch festgelegt werden.

Ein `PENDING`-Command-Buffer darf nicht verändert, zurückgesetzt, freigegeben oder erneut eingereicht werden. Gleichzeitige ausstehende Submissions desselben Command Buffers sind in v0.1 nicht vorgesehen.

## 7.3 `CommandBufferData`

Wire-Layout:

- Offset 0: X11-Header
- Offset 4: XAverius-Common-Header
- Offset 8: `CARD32 command_buffer_xid`
- Offset 12: `CARD32 command_pool_xid`
- Offset 16: Command-Entries

Flags im Common-Header:

| CREATE | FINAL | Bedeutung |
|---:|---:|---|
| 0 | 0 | Entries an einen bereits aufzeichnenden Buffer anhängen |
| 0 | 1 | Letzte Entries anhängen und Recording beenden |
| 1 | 0 | Command Buffer erstellen, Recording beginnen, ersten Chunk aufzeichnen |
| 1 | 1 | Command Buffer erstellen, kompletten Stream aufzeichnen und beenden |

`FINAL` entspricht dem Ende der Aufzeichnung. Ein separater `EndCommandBuffer`-Request ist nicht vorgesehen.

Chunks dürfen nur zwischen vollständigen Command-Entries geteilt werden. Kein einzelner Entry darf über mehrere Requests verteilt sein.

## 7.4 Entry-Header

Jeder Entry beginnt mit:

```c
CARD16 command_id;
CARD16 entry_length; /* 32-bit words, including header and padding */
```

Maximale Entry-Größe: 65535 Wörter beziehungsweise 262140 Bytes. Jeder Entry muss vollständig in einen X11-Request passen.

Command-IDs werden zentral registriert und entsprechen den unterstützten `vkCmd*`-Operationen.

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

Für v0.1 muss `stage_flags` exakt dem Compute-Shader-Bit entsprechen. `offset` und `data_length` müssen Vielfache von vier sein. `data_length` muss positiv sein.

Der Bereich muss innerhalb von `maxPushConstantsSize` liegen und von einem kompatiblen Push-Constant-Range des angegebenen Pipeline Layouts abgedeckt werden.

Die Datenbytes sind opak. Wire-Padding gehört nicht zum Push-Constant-Bereich.

## 7.6 Command-Validierung

Der Server validiert Command-Buffer-Zustand, Entry-Längen, Ressourcen-Typen, Device-Ownership, reservierte Felder, Pipeline- und Layout-Kompatibilität, Descriptor-Bindings, Push-Constant-Ranges und Dispatch-Limits.

Ein ungültiger `CommandBufferData`-Request darf keine seiner Entries teilweise anhängen. Bereits durch vorherige Requests akzeptierte Chunks bleiben erhalten, falls ein späterer Chunk fehlschlägt. Das genaue Recovery-Verhalten muss noch eingefroren werden.
