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

Normative validation precedence: (1) exact 12-byte request length (`BadLength`); (2) resolve the Physical-Device XID (`BadValue` for unknown or non-live XIDs); (3) validate that the live resource is a Physical Device (`BadMatch` otherwise); (4) return the server-stored memory-property snapshot for that Physical Device. There is no logical-Device availability phase: removal or failure of the Physical Device does not invalidate its still-live identity or rewrite its stored memory-type/heap mapping. This query performs no backend operation and changes no state. A later `AllocateMemory` must independently validate the logical Device and memory-type index against the associated Physical Device.

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

Validation precedence is normative: (1) exact 16-byte request length (`BadLength`); (2) resolve `device_xid`, then `buffer_xid` in wire order (`BadValue` for unknown or non-live XIDs); (3) validate live resource types, client ownership, and device association (`BadMatch`); (4) return the buffer's stored memory-requirement metadata. The requirements are fixed for the buffer's lifetime and this query MUST NOT start backend work. It therefore remains valid after logical-device loss, provided the Device and Buffer XIDs are still live and their types/ownership are valid. No state is changed.

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

Validation precedence is normative: (1) calculate the total request length with checked wide arithmetic and enforce the connection's X11 request limit (`BadLength`); (2) validate `data_length > 0` and zero payload padding (`BadValue`); (3) resolve `device_xid`, then `buffer_xid` in wire order (`BadValue` for unknown/non-live XIDs); (4) validate live resource types, client ownership, and device association (`BadMatch`); (5) check logical-device availability (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (6) validate binding, `TRANSFER_DST` usage, and the overflow-safe buffer range (`BadMatch`); (7) perform the ordered transfer, returning `DEPENDENCY_FAILED`, `ALLOCATION_FAILED`, or `TRANSFER_FAILED` as applicable. No wait, transfer, or state reservation may begin before stages 1–6 succeed. A lost Device is reported before binding/usage/range errors, but not before malformed framing, scalar syntax, or earlier XID/type/ownership errors.

Each `WriteBuffer` request is an independent write operation. There is no upload ID, multi-part upload transaction state, or final-chunk flag.

Clients may send multiple requests consecutively in the normal X11 request stream. Each request receives its own sequence number and reply.

`WriteBuffer` is a reply request. On success, the server sends an empty standard 32-byte X11 reply; on a failure before completion, it sends the defined X11 error. A void request without a reply would not satisfy the completion guarantees below.

A successful reply provides the following normative guarantees:

1. The input data has been fully consumed; the client may reuse its input buffer.
2. The transfer has completed and all required host-cache and GPU-visibility operations have completed.
3. All `QueueSubmit` submissions for the same logical device that were accepted before this `WriteBuffer` request have reached a terminal outcome, and the backend no longer accesses resources in a way that could conflict with the write before the transfer modifies the destination data. This prevents races with earlier queued GPU work, including work on another queue.
4. Every `QueueSubmit` for the same logical device accepted after this request is successfully processed MUST observe the written bytes when reading them. This applies regardless of queue family or queue index, including when the buffer or memory is not host-coherent.
5. This guarantee applies to the entire written range and requires no explicit client semaphores or barriers between this upload and later accepted submissions.

These rules define an ordering boundary only within the specified logical device: earlier accepted GPU work → completed `WriteBuffer` transfer → later accepted GPU work. No implicit synchronization exists with other logical devices, even if they use the same physical GPU. Each logical device belongs to the client connection that created it.

### `WriteBuffer` lifecycle and terminalization

After synchronous validation succeeds, the operation remains open until one terminal outcome is committed: successful transfer completion, a defined transfer/dependency/allocation failure, Device Loss, `DestroyDevice`, or client disconnect. The successful outcome is committed only after all earlier accepted submissions are terminal and the transfer plus required visibility operations have completed. This commit is the `WriteBuffer` success linearization point; a later Device Loss or `DestroyDevice` MUST NOT rewrite it, even if the reply has not yet been delivered.

Device Loss and `DestroyDevice` MUST serialize against an open `WriteBuffer` operation. If Device Loss commits first, the request fails with X11 error `DEVICE_LOST`; if `DestroyDevice` commits first, it fails with X11 error `DEVICE_DESTROYED`. Neither outcome may produce a successful reply or establish the upload visibility guarantee. If either transition wins before transfer start, the transfer MUST NOT start. If it wins after backend transfer start, the server MUST retain or quarantine the exact Buffer/Memory/backend references until access is impossible; the destination contents are unspecified, and no later callback may publish success or schedule further visibility work against the destroyed/lost operation. If a transfer failure or dependency failure was already committed first, that failure remains the request's outcome.

A successful `DestroyDevice` is a lifecycle-control request and MUST remain processable while `WriteBuffer` is waiting for earlier submissions; it is not deferred behind the upload barrier. A later `SignalSemaphore` remains dispatchable only while the Device is still live and has not been lost. If Device Loss or destruction has already won, the host signal MUST NOT execute. Later `QueueSubmit` requests remain deferred as specified above.

On client disconnect, an open `WriteBuffer` is cancelled without a reply. If no transfer has started, it MUST NOT start; an in-flight transfer may only drain to safe quiescence while its references remain held or quarantined. Disconnect does not cancel earlier accepted GPU submissions. No success guarantee, reply, or event may be generated for the cancelled write.

The server MUST NOT synchronously block the X11 request dispatcher while waiting for earlier GPU work if doing so would prevent later synchronization requests on the same connection from being processed. In particular, later `SignalSemaphore` requests MUST remain dispatchable while the upload is pending; the server MUST execute a valid host signal before processing subsequent ordinary requests when that signal can release earlier accepted work. This exception does not permit later `QueueSubmit` requests to cross the upload boundary: those requests MUST remain deferred until `WriteBuffer` has completed successfully or failed. Later `WaitSemaphores` requests MAY be registered normally while the upload is pending; their independent timeout deadlines continue to run and they do not delay the upload. A host signal processed during the upload may satisfy both an earlier queue wait and any still-open host wait registration. If a host wait times out or is otherwise terminalized first, a later signal MUST NOT rewrite its result. If `WriteBuffer` fails, the successful-upload guarantee does not apply; deferred requests are processed under their normal rules after the failure is determined.

While `WriteBuffer` waits for earlier submissions, the server MUST inspect signal entries in deferred `QueueSubmit` requests for a possible dependency cycle. If a deferred submission signals a Binary semaphore awaited by an earlier non-terminal submission, or signals a Timeline value that reaches or exceeds a value awaited by an earlier non-terminal submission, and no already-accepted signal operation is eligible to satisfy that wait, the server MUST terminate the pending `WriteBuffer` with `DEPENDENCY_FAILED` rather than wait for the deferred GPU signal operation. For Timeline waits, eligibility is defined by the signal/wait ordering rule in [Synchronization objects](synchronization.md#timeline-semaphores): a pending value reservation is not sufficient, and a signal operation ordered after the wait (including a later submission on the same queue) cannot satisfy it. Only already-accepted and eligible signal operations count as possible releases. Signal entries in deferred submissions do not count as accepted or available signals. This conservative rule may reject an upload even if a later host-signal request could have satisfied the same wait, but it prevents the upload-ordering boundary from depending on a GPU submission that is itself held behind that boundary. While a `QueueSubmit` is deferred, it MUST NOT change semaphore/fence state or pending reservations, or commit internal resource references as an accepted submission; full validation and atomic state transfer occur only after `WriteBuffer` completes. Deferred requests are then processed in normal request order.

In v0.1, the server MAY implement this conservatively by waiting for all earlier submissions and using the required transfer/memory barriers or device synchronization. An optimized implementation may use finer-grained synchronization but MUST guarantee the same observable ordering and progress behavior.

An earlier submission failure alone does not prevent the upload if the device remains usable: the server waits for the terminal outcome, then performs the transfer and guarantees the new bytes to later work. If the device is lost, `WriteBuffer` fails with `DEVICE_LOST` and MUST NOT send a successful reply, subject to the first-committed terminalization rule above. A failed upload likewise MUST NOT produce a successful reply; the destination contents are then not guaranteed.

## 5.8 `ReadBuffer`

Request:

- Offset 8: Device-XID
- Offset 12: Buffer-XID
- Offset 16: `CARD64 buffer_offset`
- Offset 24: `CARD32 data_length`

Total length: 28 bytes.

The length MUST be positive. The buffer MUST be bound, have `TRANSFER_SRC` usage, and cover the requested range. Bounds are checked without overflow using `buffer_offset <= buffer_size` and `data_length <= buffer_size - buffer_offset`.

Validation precedence is normative: (1) exact 28-byte request length (`BadLength`); (2) validate `data_length > 0` (`BadValue`); (3) resolve `device_xid`, then `buffer_xid` in wire order (`BadValue` for unknown/non-live XIDs); (4) validate live resource types, client ownership, and device association (`BadMatch`); (5) check logical-device availability (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (6) validate binding, `TRANSFER_SRC` usage, and the overflow-safe buffer range (`BadMatch`); (7) establish the required snapshot ordering and perform the read, returning `DEPENDENCY_FAILED`, `ALLOCATION_FAILED`, or `TRANSFER_FAILED` as applicable. No wait, snapshot, or backend read may begin before stages 1–6 succeed. A lost Device is reported before binding/usage/range errors, but not before malformed framing, scalar syntax, or earlier XID/type/ownership errors.

After the 32-byte header, the reply contains exactly `data_length` bytes read from offset 32, followed by zero padding to a four-byte boundary. `reply.length = floor((uint64(data_length) + 3) / 4)`; the calculation uses at least 64-bit arithmetic. Padding is part of X11 reply transport, not buffer data.

`ReadBuffer` defines a snapshot-ordering boundary within the addressed logical Device. Before taking the snapshot, the server MUST wait for every earlier accepted `QueueSubmit` whose work could write the requested range, directly or through another bound resource, and MUST ensure that all backend accesses to that range have ended. The same requirement applies to every earlier enqueued `WriteBuffer` transfer: a successful transfer MUST have completed, and a failed transfer MUST have reached a terminal outcome and MUST no longer be capable of modifying the target range in the backend. Logical terminalization alone is insufficient while backend accesses remain possible. An earlier failed `WriteBuffer` provides no visibility guarantee for its target range; `ReadBuffer` MUST NOT behave as though the failed input data had been written. Required host-visibility and cache operations MUST complete before the snapshot is taken. Queue order on a single queue alone is insufficient when other queues are involved.

The server MUST copy the requested bytes into a stable data snapshot before a later write operation on the same Device may modify the read range. This includes both later `QueueSubmit` requests and later `WriteBuffer` requests. Such later `QueueSubmit` and `WriteBuffer` requests MUST be deferred until the snapshot has been captured; while deferred, they are not accepted or started and MUST NOT change semaphore or fence state, create pending reservations, begin a transfer, or commit internal references for accepted submissions. They are then validated and processed in normal X11 request order. The deferral is device-scoped and applies even when the later write targets a different Buffer range: the implementation MAY use finer-grained tracking, but MUST preserve the same per-device request-order behavior for overlapping writes and MUST NOT let a later write overtake an unresolved earlier snapshot. A failed `ReadBuffer` does not establish a snapshot boundary; deferred requests are subsequently processed under their normal rules.

The request dispatcher MUST NOT block while waiting in a way that prevents a later host `SignalSemaphore` request on the same connection from releasing an earlier submission. Later `WaitSemaphores` requests MAY be registered normally and retain their independent timeout and terminalization behavior. As with `WriteBuffer`, the server MUST detect recognizable dependency cycles: if a deferred `QueueSubmit` signal would be required by an earlier non-terminal submission and no already-accepted signal operation can satisfy that wait, `ReadBuffer` MUST fail with `DEPENDENCY_FAILED` rather than wait for the deferred signal operation. Signal entries in deferred submissions do not count as accepted or available signals. A later `SignalSemaphore` remains dispatchable only while the Device is live and has not been lost. After the snapshot succeeds or the read fails, deferred `QueueSubmit` and `WriteBuffer` requests are processed in their original request order.

An earlier submission failure does not by itself prevent `ReadBuffer` while the device remains usable. The reply contains the bytes actually readable in the snapshot, but XAverius does not guarantee that a range whose intended write failed contains the data expected from the failed shader or transfer. The server MUST NOT infer successful execution or data integrity from a failed submission status.

### `ReadBuffer` lifecycle and terminalization

After synchronous validation succeeds, `ReadBuffer` remains open until one terminal outcome is committed: successful stable-snapshot capture and completion of required host-visibility/cache operations, a defined dependency/allocation/transfer failure, Device Loss, `DestroyDevice`, or client disconnect. Successful snapshot capture is the read's linearization point. A later Device Loss or `DestroyDevice` MUST NOT rewrite a success already committed at that point, even if the reply payload has not yet been delivered.

Device Loss and `DestroyDevice` MUST serialize against an open `ReadBuffer`. If Device Loss commits first, the request fails with X11 error `DEVICE_LOST`; if `DestroyDevice` commits first, it fails with X11 error `DEVICE_DESTROYED`. Neither outcome may produce a successful data reply. If either transition wins after a backend read has started but before the snapshot is committed, the server MUST retain or quarantine the exact Device/Buffer/Memory/backend references until access is impossible; no later callback may publish success or access a reused XID. `DestroyDevice` MUST remain processable while `ReadBuffer` waits for earlier submissions and MUST NOT be held behind the snapshot barrier.

On client disconnect, an open `ReadBuffer` is cancelled without a reply if its snapshot has not already been committed. A read already in progress may drain only as needed to reach safe backend quiescence while its references remain held or quarantined. Disconnect does not cancel earlier accepted GPU submissions. No reply or event may be generated for the cancelled read.

If the logical device is lost, `ReadBuffer` MUST fail with `DEVICE_LOST` and MUST NOT send a successful data reply; data MUST NOT be read from a backend whose access safety or quiescence is unknown. Internal resources and memory remain referenced until possible backend accesses are proven to have ended, or are quarantined under the device-loss rules.

For v0.1, an implementation MAY synchronize the entire device if finer-grained dependency tracking is unavailable. It MUST still stabilize the snapshot before later write operations, preserve the deferred request ordering and progress rules above, and comply with the rules for submission failures, dependency cycles, and device loss.
