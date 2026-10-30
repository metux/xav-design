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

The queue-family index MUST identify a queue family of the logical device that supports command buffers. `CreateCommandPool` validation precedence is normative: (1) exact 24-byte request length (`BadLength`); (2) pool flags and all reserved bits (`BadValue`); (3) validate `command_pool_xid` as a create-XID (`BadIDChoice` if invalid or occupied); (4) resolve `device_xid` (`BadValue` if unknown or non-live); (5) validate live resource type, client ownership, and Device association (`BadMatch`); (6) check logical-Device state (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (7) validate `queue_family_index` against the selected Device and require command-buffer support (`BadValue` if it does not identify a suitable family); (8) create the backend pool (`ALLOCATION_FAILED` on allocation failure). A later phase MUST NOT override an earlier error. In particular, Device loss wins over an invalid queue-family index, while XID/type/ownership errors win over Device loss. Creation is atomic: on any failure, the pool XID remains unallocated. The server MUST NOT silently add flags. `TRANSIENT` is an optimization hint and does not change observable semantics. `RESET_COMMAND_BUFFER` permits the explicit `ResetCommandBuffer` request for individual non-pending command buffers. Without this flag, `ResetCommandBuffer` MUST be rejected with `INVALID_SYNCHRONIZATION_STATE`. 

`DestroyCommandPool` has a fixed total length of 16 bytes: `device_xid` is at offset 8 and `command_pool_xid` is at offset 12.
- Offset 8: Device-XID
- Offset 12: Command-Pool-XID

The pool MUST belong to the specified logical device. Unknown or non-live device or pool XIDs result in `BadValue`; a live resource of the wrong type, ownership by another client, or cross-device use results in `BadMatch`. Destruction is atomically rejected with `INVALID_SYNCHRONIZATION_STATE` while any child command buffer is `PENDING`. On rejection, the pool, child XIDs, and states remain unchanged. On success, the pool and all child command buffers are publicly invalidated; internal objects remain alive until possible backend accesses have ended.

Device loss alone does not prevent `DestroyCommandPool`. Once affected accepted submissions have been terminalized and their command buffers become `INVALID` after the pending phase ends, completed device-loss handling no longer blocks destruction solely because of earlier GPU work. No new GPU work may be started; internal backend references remain until safe quiescence or are quarantined.

`ResetCommandBuffer` is a void request with a fixed total length of 16 bytes:
- Offset 8: Device-XID
- Offset 12: Command-Buffer-XID

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

- Allocation → `INITIAL`
- Create chunk of `CommandBufferData` → `RECORDING`
- successful FINAL chunk → `EXECUTABLE`
- accepted submission → `PENDING`
- Successful execution → `EXECUTABLE`
- Asynchronous execution failure or device loss → `INVALID` after the pending phase ends
- Pool or device destruction → public XID becomes invalid

There is no separate `FAILED` command-buffer state in v0.1. A failed submission makes every affected command buffer `INVALID` after the pending phase ends. It MUST NOT be submitted again; it must be reset and recorded again. A failed command buffer never automatically returns to `EXECUTABLE`.

A `PENDING` command buffer MUST NOT be modified, reset, freed, or submitted again. Multiple concurrent pending submissions of the same command buffer are not supported in v0.1.

The server tracks direct and indirect resource references for every recorded command buffer. Binding a descriptor set records a reference to the set object; descriptor-slot contents are not copied into the command buffer as an immutable snapshot. A successful `UpdateDescriptorSets` atomically updates the derived buffer references of every non-pending command buffer that references the affected set. A non-pending `EXECUTABLE` command buffer uses the set's current contents at submission time and is not invalidated solely by a successful descriptor update. If a referenced resource is destroyed while the command buffer is `RECORDING`, the destroy request MUST be rejected. If the resource is destroyed while the command buffer is `EXECUTABLE` and not pending, the command buffer transitions to `INVALID` before the destroy request succeeds. Such a command buffer MUST be recorded again before resubmission. An accepted submission retains its internal resource references until it reaches a terminal state.

## 7.3 `CommandBufferData`

`CommandBufferData` is a void request. Its total length is at least 16 bytes and consists of the 16-byte header plus complete command entries; the payload MUST contain only whole entries. For `ABORT`, the total length MUST be exactly 16 bytes.

Wire-Layout:

- Offset 0: X11-Header
- Offset 4: XAverius-Common-Header
- Offset 8: `CARD32 command_buffer_xid`
- Offset 12: `CARD32 command_pool_xid`
- Offset 16: Command-Entries

Common-header flags:

| Bit | Name | Meaning |
|---:|---|---|
| 0 | `CREATE` | Create a command buffer and begin recording |
| 1 | `FINAL` | Append the final chunk and end recording |
| 2 | `ABORT` | Discard active recording and reset the buffer to `INITIAL` |
| 3–7 | Reserved | MUST be zero |

Allowed combinations:

| CREATE | FINAL | ABORT | Meaning |
|---:|---:|---:|---|
| 0 | 0 | 0 | Append entries to a buffer that is already recording |
| 0 | 1 | 0 | Append final entries and end recording |
| 1 | 0 | 0 | Create a command buffer, begin recording, and record the first chunk |
| 1 | 1 | 0 | Create a command buffer, record the complete stream, and finish recording |
| 0 | 0 | 1 | Abort recording; no entries are allowed |

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

Total length: 8 bytes.

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

Total length: `16 + 4 * descriptor_set_count`.

Entry length: `4 + descriptor_set_count` words.

### `CMD_DISPATCH`

Total length: 16 bytes.

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

Entry length: `5 + ceil(data_length / 4)` words.

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

An invalid `CommandBufferData` request MUST NOT append any entries partially. Complete entries from the current request are appended atomically to the recording stream only after all entries have been validated successfully. If a chunk fails, the command buffer remains `RECORDING`; previously accepted chunks remain, and the failed chunk is discarded in full. The client may send a corrected chunk or discard the recording with `ABORT`. `ABORT` resets a non-pending command buffer to `INITIAL` and discards all entries and resource references recorded so far. This `ABORT` is exclusively the recovery operation for an active chunked `CommandBufferData` recording and therefore does not require the pool's `RESET_COMMAND_BUFFER` flag; it does not replace the explicit `ResetCommandBuffer` request for completed or otherwise invalid buffers. A failed CREATE request leaves neither a command buffer nor a pool-child entry. A failed FINAL chunk leaves the buffer in `RECORDING`, allowing the client to send corrected final entries or abort. ABORT is invalid if the buffer is not `RECORDING` or is already pending.

A FINAL chunk transitions `RECORDING` to `EXECUTABLE` only after the entire chunk and all stream/reference conditions required for finalization have been validated successfully. If any check fails, the current chunk is discarded in full; the buffer remains `RECORDING`, all previously accepted entries and references remain unchanged, and no partially finalized executable recording is published. The client may send a corrected FINAL chunk or use ABORT for cleanup. A successful FINAL chunk also adopts resource references only together with the accepted entries; a failure leaves no reference from the rejected chunk. The later `EXECUTABLE` to `PENDING` transition occurs only at the atomic acceptance point of `QueueSubmit`, as defined in [Queue submission](queue-submission.md#validation-and-atomic-acceptance).

Chunk errors are synchronous errors associated with the corresponding `CommandBufferData` request and do not generate `ASYNC_ERROR`: request processing has not accepted a submission. After successful XID and ownership validation, CREATE, append, and FINAL requests fail with `DEVICE_UNAVAILABLE` or `DEVICE_LOST` if the device is unavailable or lost, without changing the buffer or its previously accepted entries. `ABORT` remains permitted after device loss as a purely logical recovery/cleanup operation, provided the buffer and pool are still live, correctly associated, and the buffer is `RECORDING`; it starts no Vulkan work. A later chunk MUST NOT revive a recording interrupted by device loss. On client disconnect, open recordings are invalidated along with the connection's public resource XIDs; their recorded references are cleaned up according to the normal backend lifetime rules.



### Reset, invalidation, rerecording, and deferred reference retirement

A successful ResetCommandBuffer is a single state transition from the prior non-pending state to INITIAL. It atomically detaches the complete recorded-command list and retires the command buffer's recorded-resource reference edges exactly once. A rejected reset, including reset of a PENDING buffer or reset when the pool lacks RESET_COMMAND_BUFFER, changes neither state nor recorded entries nor reference edges. Reset MUST NOT be used to cancel accepted work; pending buffers are not resettable.

Retiring a recorded reference edge means releasing the command buffer's ownership of that edge, not destroying the referenced object regardless of other owners. If an accepted submission has retained the same resource identity, that submission's independent reference remains until its terminal outcome and backend quiescence. If the backend may still access an object after a command buffer becomes INVALID, INITIAL, or publicly invalid through pool/device destruction, the server MUST retain or quarantine the backend object until access is impossible. Logical state changes and recorded-reference retirement MUST NOT prematurely release backend storage.

After successful execution, a command buffer returns from PENDING to EXECUTABLE and its recorded entries/references remain available for resubmission. After asynchronous execution failure or device loss, it becomes INVALID; its recorded entries are no longer submit-eligible, but reference retirement must be coordinated with terminal submission cleanup and backend quiescence. The implementation MUST NOT both release those edges during terminalization and release them again during a later reset. A subsequent successful reset of an INVALID buffer clears any remaining recorded state and retires only edges still owned by that command buffer. A subsequent successful rerecording begins from INITIAL and builds a fresh reference set; no reference from the previous recording may be inherited. Every accepted backend execution hold MUST capture the command buffer's internal recording epoch. Its callback MUST retire a hold only from that exact epoch; it MUST NOT infer ownership by FIFO order or decrement a current/retired epoch selected by callback arrival order. A callback without an epoch is invalid whenever more than one recording epoch can own outstanding holds. Epoch identity remains attached to the retained recording until its final backend hold is retired.

Destroying a resource referenced by a non-pending EXECUTABLE command buffer first invalidates the affected command buffers atomically with resource public invalidation. Their recorded references are then retired by the invalidation cleanup path exactly once, subject to the same backend-quiescence rule. Resetting such an already INVALID command buffer is permitted when the pool flag and device-state rules allow it, but is not required to make the destroyed resource publicly invalid. Destroying a command pool or device similarly invalidates child command-buffer XIDs immediately while deferred internal references remain attached to the old internal identities until safely retired.

The serialization order of reset, resource destruction, submission acceptance, and rerecording is normative. If submission acceptance wins, reset is rejected while the command buffer is PENDING. If reset wins, the buffer is INITIAL and cannot be submitted until a later recording reaches EXECUTABLE. If resource destruction wins, an affected executable command buffer is INVALID before the destroy request completes; it cannot be submitted or rerecorded without a successful reset. If reset wins before destruction, the old recorded dependency has been detached, so that command buffer alone no longer blocks destruction. Every rejected transition leaves the full state and reference graph unchanged.