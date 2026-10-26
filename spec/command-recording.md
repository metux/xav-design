# 7. Command Pools, Command Buffers, and Command Streams

## 7.1 Command Pools

`CreateCommandPool` has a fixed total length of 24 bytes:

| Offset | Type | Field |
|---:|---|---|
| 8 | XID | `device_xid` |
| 12 | XID | `command_pool_xid` |
| 16 | CARD32 | `queue_family_index` |
| 20 | CARD32 | `flags` |

The pool flags defined in v0.1 are:

- Bit 0: `TRANSIENT`
- Bit 1: `RESET_COMMAND_BUFFER`
- Bits 2–31 are reserved and MUST be zero.

The queue-family index MUST identify a queue family of the logical device that supports command buffers. Unknown or non-live device XIDs result in `BadValue`; a live resource of the wrong type or ownership by another device results in `BadMatch`; an invalid queue-family index results in `BadValue`. An unavailable or lost logical device results in `DEVICE_UNAVAILABLE` or `DEVICE_LOST`, respectively; a backend allocation failure results in `ALLOCATION_FAILED`. Creation is atomic: on any failure, the pool XID remains unallocated. The server MUST NOT silently add flags. `TRANSIENT` is an optimization hint and does not change observable semantics. `RESET_COMMAND_BUFFER` permits the explicit `ResetCommandBuffer` request for individual non-pending command buffers. Without this flag, `ResetCommandBuffer` MUST be rejected with `INVALID_SYNCHRONIZATION_STATE`. 

`DestroyCommandPool` has a fixed total length of 16 bytes: `device_xid` is at offset 8 and `command_pool_xid` is at offset 12.

The pool MUST belong to the specified logical device. Unknown or non-live device or pool XIDs result in `BadValue`; a live resource of the wrong type, ownership by another client, or cross-device use results in `BadMatch`. Destruction is atomically rejected with `INVALID_SYNCHRONIZATION_STATE` while any child command buffer is `PENDING`. On rejection, the pool, child XIDs, and states remain unchanged. On success, the pool and all child command buffers are publicly invalidated; internal objects remain alive until possible backend accesses have ended.

Device loss alone does not prevent `DestroyCommandPool`. Once affected accepted submissions have been terminalized and their command buffers become `INVALID` after the pending phase ends, completed device-loss handling no longer blocks destruction solely because of earlier GPU work. No new GPU work may be started; internal backend references remain until safe quiescence or are quarantined.

`ResetCommandBuffer` is a void request with a fixed total length of 16 bytes:

| Offset | Type | Field |
|---:|---|---|
| 8 | XID | `device_xid` |
| 12 | XID | `command_buffer_xid` |

The specified logical device and command buffer MUST both be live and belong together. Unknown or non-live device or buffer XIDs result in `BadValue`; a live resource of the wrong type, ownership by another client, or cross-device use results in `BadMatch`. After successful XID and ownership validation, an unavailable device results in `DEVICE_UNAVAILABLE` and a lost device in `DEVICE_LOST`. Only then does the server check the pool's `RESET_COMMAND_BUFFER` flag and the buffer state. If the flag is absent or the buffer is pending, the request is rejected with `INVALID_SYNCHRONIZATION_STATE`. All validation occurs before any state change.

On success, `ResetCommandBuffer` resets a buffer in `INITIAL`, `RECORDING`, `EXECUTABLE`, or `INVALID` to `INITIAL`. All recorded entries and their resource references are discarded. On rejection, the state, entries, and references remain unchanged. Resetting a `RECORDING` buffer therefore also discards an unfinished recording.

`TRANSIENT` and `RESET_COMMAND_BUFFER` are independent bits. `TRANSIENT` changes neither the validity nor the result of reset operations. Reserved bits MUST be zero; the server MUST NOT accept unknown flags or silently add flags. 

A command pool is the parent object of the command buffers allocated from it. Destroying the pool atomically invalidates the public XIDs of all its command buffers. In v0.1, pool destruction is rejected while any child command buffer is pending execution.

## 7.2 Command Buffer States

The defined states are:

- `INITIAL`
- `RECORDING`
- `EXECUTABLE`
- `PENDING`
- `INVALID`

Transitions:

- Allokation → `INITIAL`
- Create-Chunk von `CommandBufferData` → `RECORDING`
- erfolgreicher FINAL-Chunk → `EXECUTABLE`
- angenommene Submission → `PENDING`
- Successful execution → `EXECUTABLE`
- Asynchronous execution failure or device loss → `INVALID` after the pending phase ends
- Pool or device destruction → public XID becomes invalid

There is no separate `FAILED` command-buffer state in v0.1. A failed submission makes every affected command buffer `INVALID` after the pending phase ends. It MUST NOT be submitted again; it must be reset and recorded again. A failed command buffer never automatically returns to `EXECUTABLE`.

A `PENDING` command buffer MUST NOT be modified, reset, freed, or submitted again. Multiple concurrent pending submissions of the same command buffer are not supported in v0.1.

Der Server verfolgt die direkten und indirekten Ressourcenreferenzen jedes aufgezeichneten Command Buffers. Das Binden eines Descriptor Sets zeichnet eine Referenz auf das Set-Objekt auf; die Descriptor-Slot-Inhalte werden nicht als unveränderlicher Snapshot in den Command Buffer kopiert. Ein erfolgreiches `UpdateDescriptorSets` aktualisiert atomar die abgeleiteten Buffer-Referenzen aller nicht-pending Command Buffer, die das betroffene Set referenzieren. Ein nicht-pending `EXECUTABLE`-Command-Buffer verwendet bei Submission die aktuellen Inhalte des gebundenen Sets und wird allein durch ein erfolgreiches Descriptor-Update nicht invalidiert. Wird eine referenzierte Ressource während `RECORDING` zerstört, muss der Destroy-Request abgewiesen werden. Wird sie zerstört, während der Command Buffer `EXECUTABLE` ist und nicht pending verwendet wird, wechselt der Command Buffer vor erfolgreichem Abschluss der Zerstörung in `INVALID`. Ein solcher Command Buffer muss neu aufgezeichnet werden, bevor er erneut eingereicht werden darf. Eine angenommene Submission behält ihre internen Ressourcenreferenzen bis zum terminalen Abschluss.

## 7.3 `CommandBufferData`

`CommandBufferData` is a void request. Its total length is at least 16 bytes and consists of the 16-byte header plus complete command entries; the payload MUST contain only whole entries. For `ABORT`, the total length MUST be exactly 16 bytes.

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
| 3–7 | Reserved | MUST be zero |

Allowed combinations:

| CREATE | FINAL | ABORT | Bedeutung |
|---:|---:|---:|---|
| 0 | 0 | 0 | Entries an einen bereits aufzeichnenden Buffer anhängen |
| 0 | 1 | 0 | Letzte Entries anhängen und Recording beenden |
| 1 | 0 | 0 | Command Buffer erstellen, Recording beginnen, ersten Chunk aufzeichnen |
| 1 | 1 | 0 | Command Buffer erstellen, kompletten Stream aufzeichnen und beenden |
| 0 | 0 | 1 | Recording abbrechen; keine Entries erlaubt |

All other combinations are invalid. An ABORT request MUST contain no payload beyond the fixed header. `command_pool_xid` MUST match the buffer's pool even for ABORT.

`FINAL` ends recording. No separate `EndCommandBuffer` request is defined.

### Error Precedence for `CommandBufferData`

Errors are evaluated in ordered phases; the first error in the earliest applicable phase is reported:

1. Request length, ABORT length, complete entry headers, and declared entry boundaries; structural errors result in `BadLength`.
2. Common-header flags, reserved bits/fields, valid CREATE/FINAL/ABORT combinations, padding, semantic entry field values, and command IDs; invalid values result in `BadValue`.
3. Target XID, then pool XID. For CREATE, an invalid or occupied target XID results in `BadIDChoice`; without CREATE, an unknown target XID results in `BadValue`. The pool XID and live resource types are then resolved.
4. Resource type, client ownership, device association, and exact parent-pool association; a live resource of the wrong type, foreign ownership, or incorrect association results in `BadMatch`.
5. For CREATE, append, and FINAL, the associated device state is checked; `DEVICE_UNAVAILABLE`/`DEVICE_LOST` takes precedence over a buffer-state error. If the device is operational, a non-CREATE buffer MUST be `RECORDING`, otherwise `INVALID_SYNCHRONIZATION_STATE` is returned.

Thus, wire-structure errors take precedence over field errors; field errors take precedence over target/pool XID errors; and XID/type/ownership errors take precedence over device and buffer-state errors. Within the XID phase, the target XID is checked before the pool XID.

`ABORT` is the defined exception to phase 5: after phases 1–4, the server checks that the buffer is `RECORDING` and not pending. This logical cleanup remains permitted after device loss, starts no Vulkan work, and is rejected with `INVALID_SYNCHRONIZATION_STATE` if the buffer is in the wrong state. Every rejection leaves previously accepted entries and references unchanged; the current chunk is never partially accepted.


Chunks may split only between complete command entries. An individual entry MUST NOT span multiple requests.

## 7.4 Entry-Header

Jeder Entry beginnt mit:

```c
CARD16 command_id;
CARD16 entry_length; /* 32-bit words, including header and padding */
```

Maximum entry size: 65535 words (262140 bytes). Every entry MUST fit entirely within one X11 request.

Command IDs are numerically defined in the [Command Entry Registry](../registries/command-entries.md). They are XAverius wire IDs and MUST NOT be interpreted as native Vulkan command IDs.

## 7.5 Supported Command Entries

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

Dispatch values MUST be within the limits supported by the device.

### `CMD_PUSH_CONSTANTS`

- Relativer Offset 0: `CARD16 command_id`
- Offset 2: `CARD16 entry_length`
- Offset 4: `CARD32 stage_flags`
- Offset 8: Pipeline-Layout-XID
- Offset 12: `CARD32 offset`
- Offset 16: `CARD32 data_length`
- Offset 20: Datenbytes, danach Null-Padding bis zur Vierbytegrenze

Entry-Länge: `5 + ceil(data_length / 4)` Wörter.

For v0.1, `stage_flags` MUST equal exactly the `COMPUTE` bit defined in the [Shader Stage Registry](../registries/shader-stages.md). `offset` and `data_length` MUST be multiples of four. `data_length` MUST be positive.

The range MUST fit within `maxPushConstantsSize` and be covered by a compatible push-constant range in the specified pipeline layout.

The data bytes are opaque. Wire padding is not part of the push-constant range.


### `CMD_COPY_BUFFER_TO_SWAPCHAIN_IMAGE` — presentation-capable profile only

This entry is a minimal pixel-production path for the first on-screen presentation profile; it does not add general Vulkan Image resources or graphics pipelines. It copies a tightly or explicitly row-pitched rectangle from a Buffer into one acquired Swapchain image. The entry is valid only when the source Buffer has `TRANSFER_SRC` usage, the selected Swapchain was created with `TRANSFER_DST` image usage, and the referenced image is currently `ACQUIRED` at the point the command is validated for submission.

Assigned command ID: 5 (presentation-capable profile only; not part of the compute-only v0.1 entry set).

Fixed total length: 36 bytes; `entry_length = 9` words.

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

A command buffer referencing a Swapchain image retains an internal reference to the Swapchain. Destroying the Swapchain is rejected while a recording command buffer refers to it; non-pending executable command buffers that refer to it are invalidated atomically when the Swapchain is successfully destroyed. At submission acceptance, the referenced image must be ACQUIRED and the command must not race a presentation transition. A pending submission retains the image until its terminal outcome and all backend accesses end. The server serializes request validation and acceptance in X11 request order for a connection. A `QueueSubmit` accepted before `QueuePresent` retains its exact image/Swapchain identity; if it can access the image, presentation must wait on a binary semaphore dependency covering that work. A later copy submission processed after the image has transitioned to `PRESENT_PENDING` is rejected atomically with `INVALID_SYNCHRONIZATION_STATE`. Request order alone creates no GPU memory dependency. If `QueuePresent` is rejected, the image remains `ACQUIRED`, so a later submission may still be accepted if all other checks pass.

The presentation-only command-entry ID is 5. Every new numeric ID must be allocated append-only in the [command-entry registry](../registries/command-entries.md) before an implementation advertises support. It is not part of the current compute-only v0.1 entry set.

## 7.6 Command-Validierung

The server validates command-buffer state, entry lengths, resource types, device ownership, reserved fields, pipeline and layout compatibility, descriptor bindings, push-constant ranges, and dispatch limits.

Ein ungültiger `CommandBufferData`-Request darf keine seiner Entries teilweise anhängen. Die vollständigen Entries des aktuellen Requests werden erst nach erfolgreicher Validierung aller Entries atomar an den Recording-Stream angehängt. Scheitert ein Chunk, bleibt der Command Buffer im Zustand `RECORDING`; zuvor erfolgreich angehängte Chunks bleiben erhalten, der fehlgeschlagene Chunk wird vollständig verworfen. Der Client kann einen korrigierten Chunk senden oder das Recording mit `ABORT` verwerfen. `ABORT` setzt einen nicht-pending Command Buffer auf `INITIAL` und verwirft alle bis dahin aufgezeichneten Entries und Ressourcenreferenzen. Dieses `ABORT` ist ausschließlich die Recovery-Operation für ein laufendes, chunk-basiertes `CommandBufferData`-Recording und benötigt deshalb nicht das Pool-Flag `RESET_COMMAND_BUFFER`; es ersetzt nicht den expliziten `ResetCommandBuffer`-Request für bereits abgeschlossene oder anderweitig ungültige Buffer. Ein fehlgeschlagener CREATE-Request hinterlässt weder einen Command Buffer noch einen Pool-Kind-Eintrag. Ein fehlgeschlagener FINAL-Chunk lässt den Buffer im Zustand `RECORDING`, sodass der Client korrigierte letzte Entries senden oder abbrechen kann. ABORT ist nicht zulässig, wenn der Buffer nicht `RECORDING` oder bereits pending ist.

Ein FINAL-Chunk führt den Übergang `RECORDING` → `EXECUTABLE` erst nach erfolgreicher Validierung des gesamten Chunks und aller für die Finalisierung erforderlichen Stream-/Referenzbedingungen aus. Schlägt eine Prüfung fehl, wird der ganze aktuelle Chunk verworfen; der Buffer bleibt `RECORDING`, alle vorher akzeptierten Entries und ihre Referenzen bleiben unverändert und es wird keine teilweise finalisierte ausführbare Aufzeichnung veröffentlicht. Der Client kann einen korrigierten FINAL-Chunk senden oder mit ABORT aufräumen. Auch ein erfolgreicher FINAL-Chunk darf Ressourcenreferenzen erst gemeinsam mit den akzeptierten Entries übernehmen; ein Fehler hinterlässt keine Referenz aus dem abgewiesenen Chunk. Der spätere Übergang `EXECUTABLE` → `PENDING` erfolgt ausschließlich am atomaren Annahmepunkt von `QueueSubmit` gemäß [Queue submission](queue-submission.md#validation-und-atomare-annahme).

Chunk-Fehler sind synchron dem jeweiligen `CommandBufferData`-Request zugeordnet und erzeugen kein `ASYNC_ERROR`: Die Request-Verarbeitung hat noch keine Submission angenommen. Nach erfolgreicher XID-/Ownership-Prüfung schlagen CREATE-, Append- und FINAL-Requests bei nicht verfügbarem/verlorenem Device mit `DEVICE_UNAVAILABLE` beziehungsweise `DEVICE_LOST` fehl, ohne den Buffer oder seine bisherigen Entries zu verändern. `ABORT` bleibt als rein logische Recovery-/Cleanup-Operation auch nach Device Loss zulässig, sofern Buffer und Pool noch live sind, korrekt zusammengehören und der Buffer `RECORDING` ist; sie startet keine Vulkan-Arbeit. Device Loss darf bereits laufende bzw. unvollständige Recordings nicht durch einen späteren Chunk wiederbeleben. Beim Client-Disconnect werden offene Recordings zusammen mit den öffentlichen Ressourcen-XIDs der Verbindung invalidiert; ihre aufgezeichneten Referenzen werden nach den normalen Backend-Lebensdauerregeln bereinigt.
