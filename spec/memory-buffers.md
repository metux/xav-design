# 5. Memory and Buffers

## 5.1 `CreateBuffer`

Total length: 32 bytes.

| Offset | Type | Field |
|---:|---|---|
| 8 | XID | `device_xid` |
| 12 | XID | `buffer_xid` |
| 16 | CARD64 | `size` in Bytes |
| 24 | CARD32 | `usage_flags` |
| 28 | CARD32 | `reserved = 0` |

The size MUST be positive and at least one supported `usage_flags` bit MUST be set. Unknown bits or `usage_flags = 0` are rejected with `BadValue`. Creating a buffer does not allocate or bind memory.

`CreateBuffer` validates in this order: (1) exact request length (`BadLength`); (2) `size`, `usage_flags`, and `reserved` (`BadValue`); (3) target `buffer_xid` as a create-XID (`BadIDChoice` if invalid or occupied); (4) `device_xid` lookup (`BadValue` for unknown/non-live XID); (5) resource type and client/device ownership (`BadMatch`); (6) logical-device state (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (7) backend buffer creation (`ALLOCATION_FAILED` on allocation failure). Failure is atomic and leaves `buffer_xid` unallocated.

Usage-Bits:

- Bit 0: `STORAGE_BUFFER`
- Bit 1: `TRANSFER_SRC`
- Bit 2: `TRANSFER_DST`
- Bit 3: `UNIFORM_BUFFER`
- Bit 4: `INDEX_BUFFER`
- Bit 5: `VERTEX_BUFFER`
- Bit 6: `INDIRECT_BUFFER`
- Bits 7–31: reserved

The server MUST NOT silently add usage flags. Images are not included in v0.1.

For the initial compute test:

- A and B: `STORAGE_BUFFER | TRANSFER_DST`
- C: `STORAGE_BUFFER | TRANSFER_SRC`

## 5.2 `GetPhysicalDeviceMemoryProperties`

Request: physical-device XID at offset 8; total length 12 bytes. This request explicitly uses a physical-device XID, not a logical-device XID.

The reply contains the following after the 32-byte header:

- `CARD32 memory_type_count`
- `CARD32 memory_heap_count`
- `CARD32 memory_properties_flags`
- `CARD32 reserved = 0`
- `MEMORYTYPEINFO[]`
- `MEMORYHEAPINFO[]`

`MEMORYTYPEINFO` is 8 bytes:

- `CARD32 property_flags`
- `CARD32 heap_index`

`MEMORYHEAPINFO` is 16 bytes:

- `CARD64 size`
- `CARD32 heap_flags`
- `CARD32 reserved = 0`

The reply payload length is `16 + 8 * memory_type_count + 16 * memory_heap_count` bytes. Accordingly, `reply.length = 4 + 2 * memory_type_count + 4 * memory_heap_count`.

Memory-Type-Flags:

- Bit 0: `DEVICE_LOCAL`
- Bit 1: `HOST_VISIBLE`
- Bit 2: `HOST_COHERENT`
- Bit 3: `HOST_CACHED`
- Bit 4: `LAZILY_ALLOCATED`
- Bit 5: `PROTECTED`

Heap flag bit 0 denotes `DEVICE_LOCAL`. Other bits are reserved.

At most 32 memory types and 16 memory heaps are supported. Indices start at zero and remain stable for the lifetime of the physical-device XID or its device generation; all logical devices on that physical device use the same mapping. Every heap index MUST be valid. `memory_type_count` and `memory_heap_count` MUST NOT exceed their respective limits. Each `property_flags` value may contain only defined bits; reserved bits MUST be zero. `heap_index` MUST be less than `memory_heap_count`. If the number of memory types or memory heaps is zero, no corresponding records may follow.

`memory_properties_flags` has no defined semantics yet; the field MUST be zero until a registry definition is assigned.

## 5.3 `GetBufferMemoryRequirements`

Request:

- Offset 8: Device-XID
- Offset 12: Buffer-XID
- Total length: 16 bytes

Reply:

| Offset | Type | Field |
|---:|---|---|
| 8 | CARD64 | `size` |
| 16 | CARD64 | `alignment` |
| 24 | CARD32 | `memory_type_bits` |
| 28 | CARD32 | `reserved = 0` |

The reply payload length is zero. Size and alignment MUST be positive. `memory_type_bits` is a bitmask: bit N permits `memory_type_index = N`; bits beyond `memory_type_count` MUST be zero. A successful buffer query MUST return at least one supported memory-type bit, so `memory_type_bits` MUST NOT be zero. These values refer to the physical device associated with the specified logical device and remain stable for its lifetime.

## 5.4 `AllocateMemory`

Total length: 32 bytes.

- Offset 8: Device-XID
- Offset 12: Memory-XID
- Offset 16: `CARD64 allocation_size`
- Offset 24: `CARD32 memory_type_index`
- Offset 28: `CARD32 reserved = 0`

The allocation size MUST be positive, and the memory-type index MUST exist for the physical device associated with the logical device. `AllocateMemory` reserves exactly `allocation_size` bytes and does not bind a buffer. Validation order is normative: (1) exact request length (`BadLength`); (2) `allocation_size`, `memory_type_index`, and `reserved` (`BadValue`); (3) target `memory_xid` as a create-XID (`BadIDChoice` if invalid or occupied); (4) `device_xid` lookup (`BadValue` for unknown/non-live XID); (5) resource type and client/device ownership (`BadMatch`); (6) logical-device state (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (7) backend allocation (`ALLOCATION_FAILED`). The server MUST NOT silently round up the requested size; required internal backend alignment must be implemented without changing the publicly visible allocation size. If allocation fails, `ALLOCATION_FAILED` is reported and `memory_xid` remains unallocated. Unknown or non-live device XIDs result in `BadValue`; a live resource of the wrong type or foreign device ownership results in `BadMatch`. An unavailable or lost logical device results in `DEVICE_UNAVAILABLE` or `DEVICE_LOST`, respectively. The request is atomic: on any failure, `memory_xid` remains unallocated and no partial allocation remains.

## 5.5 `FreeMemory`

Total length: 16 bytes.

- Offset 8: Device-XID
- Offset 12: Memory-XID

The memory block MUST belong to the specified logical device. The request is atomically rejected if any internally live buffer remains bound to this allocation (`BadMatch`) or accepted GPU work accesses the allocation (`INVALID_SYNCHRONIZATION_STATE`). This also applies to buffers whose public XID has already been invalidated by `DestroyResource` but whose internal object cannot yet be released because of descriptor slots, internal references, or possible backend accesses. On rejection, the memory XID and allocation remain unchanged. Validation precedence is normative: (1) exact 16-byte request length (`BadLength`); (2) resolve `device_xid`, then `memory_xid` (`BadValue` for unknown/non-live XIDs); (3) validate live resource types, client ownership, and device association (`BadMatch`); (4) check whether an internally live Buffer remains bound (`BadMatch`); (5) check accepted GPU access that has not reached a terminal outcome (`INVALID_SYNCHRONIZATION_STATE`). Device loss alone is not a blanket rejection for this logical cleanup: submissions terminalized by Device loss no longer block `FreeMemory` solely because they were formerly pending. A still-bound internal Buffer continues to block it, and possible backend access that has not been proven quiescent requires retaining/quarantining the internal allocation even if the public free is otherwise accepted. The server MUST NOT free or reuse backing storage while access safety is unknown.

XAverius v0.1 does not support unbinding or rebinding. Therefore, all buffers bound to an allocation MUST be successfully destroyed before `FreeMemory`. On success, the public memory XID becomes invalid immediately; the internal allocation may be released only when no internal references or backend accesses remain. Successful `FreeMemory` requires that no live internal buffer identity remains bound to the allocation. Device-wide `DestroyDevice` invalidates the public Memory and Buffer XIDs together, but it does not bypass internal dependency retirement: descriptor-slot, recorded-command, submission, active-operation, and backend-access references MUST be drained against their captured internal identities. The server MUST retire each Buffer-to-Memory binding exactly once and MUST retain/quarantine the allocation until all possible backend access has ended. It MUST NOT invoke public `FreeMemory` semantics on an already invalidated child XID or use XID lookup to decide which allocation a delayed cleanup releases.

## 5.6 `BindBufferMemory`

Total length: 28 bytes.

- Offset 8: Device-XID
- Offset 12: Buffer-XID
- Offset 16: Memory-XID
- Offset 20: `CARD64 memory_offset`

The buffer and memory MUST belong to the specified device. In v0.1, a buffer may be bound only once.

The allocation's `memory_type_index` MUST be less than `memory_type_count`, and the corresponding bit in `memory_type_bits` MUST be set (`(memory_type_bits & (1u << memory_type_index)) != 0`). The offset is in bytes and MUST be a multiple of the reported `alignment`. The binding bound is determined by `requirements.size`, not merely the logical buffer size; the allocation must cover the complete range required by the backend.

Bounds checks MUST be performed without integer overflow:

- `memory_offset <= allocation_size`
- `requirements.size <= allocation_size - memory_offset`

`BindBufferMemory` validates in this order: (1) exact wire length (`BadLength`); (2) resolve device, buffer, and memory XIDs in wire order, with unknown or non-live XIDs resulting in `BadValue`; (3) resource type, client/device ownership, and cross-device association (`BadMatch`); (4) device state (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (5) binding-specific checks: an already-bound buffer, an incompatible memory type, invalid alignment, or insufficient allocation results in `BadMatch`. Device loss takes precedence over these binding-specific state/backend checks, but not over an earlier XID or ownership error. The request is atomic: if rejected, the buffer remains unbound.

## 5.7 `WriteBuffer`

Request:

- Offset 8: Device-XID
- Offset 12: Buffer-XID
- Offset 16: `CARD64 buffer_offset`
- Offset 24: `CARD32 data_length`
- Offset 28: Byte-Payload
- zero padding through the next four-byte boundary

Total length:

`28 + ((uint64(data_length) + 3) & ~uint64(3))`

`data_length` MUST be positive. The total length MUST be calculated using arithmetic wider than 32 bits. If it cannot be represented without overflow or exceeds the maximum X11 request length for this connection, the request is rejected with `BadLength`. Padding MUST consist entirely of zero bytes; non-zero padding results in `BadValue`.

The buffer MUST be bound, have `TRANSFER_DST` usage, and cover the complete destination range. Bounds are checked without overflow using `buffer_offset <= buffer_size` and `data_length <= buffer_size - buffer_offset`.

Each `WriteBuffer` request is an independent write operation. There is no upload ID, multi-part upload transaction state, or final-chunk flag.

Clients may send multiple requests consecutively in the normal X11 request stream. Each request receives its own sequence number and reply.

`WriteBuffer` is a reply request. On success, the server sends an empty standard 32-byte X11 reply; on a failure before completion, it sends the defined X11 error. A void request without a reply would not satisfy the completion guarantees below.

Ein erfolgreicher Reply garantiert normativ:

1. The input data has been fully consumed; the client may reuse its input buffer.
2. The transfer has completed and all required host-cache and GPU-visibility operations have completed.
3. All `QueueSubmit` submissions for the same logical device that were accepted before this `WriteBuffer` request have reached a terminal outcome, and the backend no longer accesses resources in a way that could conflict with the write before the transfer modifies the destination data. This prevents races with earlier queued GPU work, including work on another queue.
4. Every `QueueSubmit` for the same logical device accepted after this request is successfully processed MUST observe the written bytes when reading them. This applies regardless of queue family or queue index, including when the buffer or memory is not host-coherent.
5. This guarantee applies to the entire written range and requires no explicit client semaphores or barriers between this upload and later accepted submissions.

These rules define an ordering boundary only within the specified logical device: earlier accepted GPU work → completed `WriteBuffer` transfer → later accepted GPU work. No implicit synchronization exists with other logical devices, even if they use the same physical GPU. Each logical device belongs to the client connection that created it.

The server MUST NOT synchronously block the X11 request dispatcher while waiting for earlier GPU work if doing so would prevent a later `SignalSemaphore` request on the same connection from being processed. Ein solcher späterer Host-Signal-Request darf ausgeführt werden, um frühere Submissions freizugeben. Spätere `QueueSubmit`-Requests derselben Verbindung dürfen dagegen erst angenommen werden, nachdem `WriteBuffer` erfolgreich abgeschlossen wurde; sie müssen bis dahin zurückgestellt werden. So bleibt die Upload-Grenze wirksam, ohne eine Submission durch einen Host-Signal-Request zu deadlocken. Bei einem fehlgeschlagenen `WriteBuffer` gilt die erfolgreiche Upload-Garantie nicht; zurückgestellte Requests werden nach Feststellung des Fehlers gemäß ihren normalen Regeln weiterverarbeitet. While `WriteBuffer` waits for earlier submissions, the server MUST also inspect signal entries in deferred `QueueSubmit` requests for a possible dependency cycle. If a deferred submission signals a Binary semaphore awaited by an earlier non-terminal submission, or signals a Timeline value that reaches or exceeds a value awaited by an earlier non-terminal submission, and no already-accepted signal operation can satisfy that wait, the server MUST terminate the pending `WriteBuffer` with `DEPENDENCY_FAILED` rather than wait for the deferred GPU signal operation. Signal entries in deferred submissions do not count as accepted or available signals for this check. While a `QueueSubmit` is deferred, it MUST NOT change semaphore/fence state or pending reservations, or commit internal resource references as an accepted submission; full validation and atomic state transfer occur only after `WriteBuffer` completes. Deferred requests are then processed in normal request order. This conservative rule may reject an upload even if a later host-signal request could have satisfied the same wait, but it prevents the upload-ordering boundary from creating a recognizable, unresolvable cycle.

In v0.1, the server MAY implement this conservatively by waiting for all earlier submissions and using the required transfer/memory barriers or device synchronization. An optimized implementation may use finer-grained synchronization but MUST guarantee the same observable ordering and progress behavior.

An earlier submission failure alone does not prevent the upload if the device remains usable: the server waits for the terminal outcome, then performs the transfer and guarantees the new bytes to later work. If the device is lost, `WriteBuffer` fails with `DEVICE_LOST` and MUST NOT send a successful reply. A failed upload likewise MUST NOT produce a successful reply; the destination contents are then not guaranteed.

## 5.8 `ReadBuffer`

Request:

- Offset 8: Device-XID
- Offset 12: Buffer-XID
- Offset 16: `CARD64 buffer_offset`
- Offset 24: `CARD32 data_length`

Total length: 28 bytes.

The length MUST be positive. The buffer MUST be bound, have `TRANSFER_SRC` usage, and cover the requested range. Bounds are checked without overflow using `buffer_offset <= buffer_size` and `data_length <= buffer_size - buffer_offset`.

After the 32-byte header, the reply contains exactly `data_length` bytes read from offset 32, followed by zero padding to a four-byte boundary. `reply.length = floor((uint64(data_length) + 3) / 4)`; the calculation uses at least 64-bit arithmetic. Padding is part of X11 reply transport, not buffer data.

`ReadBuffer` definiert einen Snapshot-Ordnungsübergang innerhalb des adressierten logischen Devices. Der Server muss vor dem Snapshot alle vor diesem Request angenommenen `QueueSubmit`-Submissions abwarten, deren Arbeit den angeforderten Bereich direkt oder über eine andere gebundene Ressource schreiben kann, und sicherstellen, dass deren Backend-Zugriffe auf den Bereich beendet sind. Dasselbe gilt für alle vor diesem Request eingereihten `WriteBuffer`-Transfers: Ein erfolgreicher Transfer muss abgeschlossen sein; ein fehlgeschlagener Transfer muss terminal sein und darf den Zielbereich nicht mehr im Backend verändern können. Eine bloße logische Terminalisierung reicht nicht aus, solange Backend-Zugriffe noch möglich sind. Ein fehlgeschlagener früherer `WriteBuffer` liefert keine Sichtbarkeitsgarantie für dessen Zielbereich; `ReadBuffer` darf deshalb nicht so tun, als seien die fehlgeschlagenen Eingabedaten geschrieben worden. Erforderliche Host-Visibility- und Cache-Operationen müssen vor dem Snapshot abgeschlossen sein. Bloße Queue-Reihenfolge auf einer einzelnen Queue reicht nicht aus, wenn andere Queues beteiligt sind.

Der Server muss die angeforderten Bytes in einen stabilen Daten-Snapshot übernehmen, bevor ein späterer `QueueSubmit` desselben Devices den gelesenen Bereich verändern darf. Solche späteren `QueueSubmit`-Requests dürfen bis zur Erfassung des Snapshots zurückgestellt werden; sie gelten währenddessen nicht als angenommen und dürfen keine Semaphore-/Fence-Zustände, Pending-Reservierungen oder internen Referenzen angenommener Submissions verändern. Danach werden sie in normaler Request-Reihenfolge validiert und verarbeitet. Der Request-Dispatcher darf während des Wartens nicht so blockieren, dass ein späterer Host-`SignalSemaphore`-Request derselben Verbindung eine frühere Submission nicht mehr freigeben kann. Wie bei `WriteBuffer` muss der Server erkennbare Abhängigkeitszyklen prüfen: Wenn ein zurückgestelltes Queue-Signal für eine frühere nicht-terminale Submission erforderlich wäre und kein bereits angenommener Signalvorgang den Wait erfüllen kann, muss `ReadBuffer` mit `DEPENDENCY_FAILED` fehlschlagen, statt auf den zurückgestellten Signalvorgang zu warten. Signal-Entries zurückgestellter Submissions gelten dabei nicht als angenommene oder verfügbare Signale. Ein fehlgeschlagener `ReadBuffer` verspricht keinen Snapshot; zurückgestellte Requests werden danach nach ihren normalen Regeln weiterverarbeitet.

An earlier submission failure does not by itself prevent `ReadBuffer` while the device remains usable. The reply contains the bytes actually readable in the snapshot, but XAverius does not guarantee that a range whose intended write failed contains the data expected from the failed shader or transfer. The server MUST NOT infer successful execution or data integrity from a failed submission status. If the logical device is lost, `ReadBuffer` MUST fail with `DEVICE_LOST` and MUST NOT send a successful data reply; data MUST NOT be read from a backend whose access safety or quiescence is unknown. Internal resources and memory remain referenced until possible backend accesses are proven to have ended, or are quarantined under the device-loss rules.

For v0.1, an implementation MAY synchronize the entire device if finer-grained dependency tracking is unavailable. It MUST still stabilize the snapshot before later write submissions and comply with the rules above for submission failures, dependency cycles, and device loss.
