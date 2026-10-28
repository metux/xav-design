# Errors and error mapping

Error codes are offsets relative to the X11 extension's `first_error` value. The absolute X11 error code is `first_error + offset`; implementations must use the central values in [the error registry](../registries/errors.md), not allocate values ad hoc.

The error registry's offsets and event-local status values are separate numeric namespaces. In particular, `EXECUTION_FAILED` is error offset 3, while `SUBMISSION_FAILED.failure_class = EXECUTION_FAILED` is the event-local value 0; `WaitForFence` also has its own reply-status value for execution failure. Likewise, `DEVICE_LOST` has error offset 1, while the `WaitForFence` reply status is 3 and the `DEVICE_LOST` event's `reason_code` is a separate enum (for example, `VULKAN_DEVICE_LOST = 3`). Implementations MUST use the value from the field's defining registry, never a same-named value from another namespace.

For an accepted `QueueSubmit`, an execution failure is reported through the submission terminal event and synchronization state, with `ASYNC_ERROR` available for diagnostics. It MUST NOT be reported as a delayed X11 request error. The `EXECUTION_FAILED` error offset is not a substitute for the event-local `failure_class` or `WaitForFence` status.

XAverius errors use the standard 32-byte X11 error packet and add no XAverius-specific payload bytes. The packet carries the extension major opcode and the sequence number of the request that caused the error. The resource field identifies the affected resource when meaningful; otherwise it is zero. For v0.1, the X11 request-header `data` byte MUST be zero; XAverius `subopcode` is carried at offset 4, and the error packet's `minorCode` is the zero-extended `subopcode`. The error packet's `majorCode` is the extension major opcode.

## General Error Classes

| Situation | Result |
|---|---|
| Inconsistent request length or count | `BadLength` |
| Invalid field value, reserved bits, or flags | `BadValue` |
| Invalid or already occupied create XID | `BadIDChoice` |
| Wrong resource type or cross-device combination | normally `BadMatch` |
| XID does not identify a live XAverius resource or is unknown in this resource context | `BadValue` |
| Invalid Atom XID | `BadAtom` |
| Live XID has a resource type other than the expected type | `BadMatch` |
| Live resource belongs to another client and no sharing path is defined | `BadMatch` |
| Device unavailable | `DEVICE_UNAVAILABLE` |
| Device lost | `DEVICE_LOST` |
| Logical device normally destroyed while a host wait is open (`WaitSemaphores`) | `DEVICE_DESTROYED` as an X11 error; `WaitForFence` instead uses the normal reply status `DEVICE_DESTROYED = 4` |
| Invalid synchronization state | `INVALID_SYNCHRONIZATION_STATE` |
| Synchronous transfer failure | `TRANSFER_FAILED` |
| Synchronous allocation failure | `ALLOCATION_FAILED` |
| Invalid dependency prevents acceptance | `DEPENDENCY_FAILED` |
| Unexpected server error | `INTERNAL_SERVER_ERROR` |

## Normative XID Error Rule

The following baseline mapping applies to all XAverius requests unless a request defines an explicitly narrower rule:

- A required XAverius XID that does not identify a live resource in the XAverius resource space results in `BadValue`. This includes unknown, destroyed, and no-longer-public XIDs. XAverius resources use extension-specific resource types, so there is no corresponding core error such as `BadWindow` or `BadPixmap`.
- An XID that identifies a live resource but not the expected resource type results in `BadMatch`.
- A live resource owned by another client, with no explicit sharing path defined, results in `BadMatch`. The same applies to cross-device use.
- An invalid `ATOM` value results in `BadAtom`, not `BadValue`.
- An invalid or already-occupied create XID results in `BadIDChoice`; this differs from an invalid input XID.
- For server-assigned physical-device XIDs, an unknown or no-longer-valid XID also results in `BadValue`; a live resource of the wrong type results in `BadMatch`.

This mapping also applies when a request contains multiple XIDs: the server validates wire structure first, then field values, then XIDs in the field order specified by the request chapter. The first invalid XID determines the reported resource error. The request remains atomic.

### Create XIDs and Chunk-Based Creation

The target XID of a create request is not an input XID to be resolved as an existing resource. An invalid or occupied target XID therefore results in `BadIDChoice`; it MUST NOT be treated as an ordinary unknown input XID producing `BadValue`. For atomic batch creation, the entire request is rejected if any target XID is invalid, already occupied, or duplicated within the same request; no subset remains live.

This rule applies in particular to target XIDs for `CreatePipelineLayout`, `CreateComputePipeline`, and descriptor sets requested by `AllocateDescriptorSets`. It also applies to `ShaderModuleData` and `CommandBufferData` when the `CREATE` flag is set. For `ShaderModuleData`, a successful CREATE chunk reserves the target XID for the upload assembly; a second CREATE or an already-live target XID results in `BadIDChoice`.

For `ShaderModuleData` without `CREATE`, a matching upload assembly MUST exist. If the XID identifies a live resource of another type, the result is `BadMatch`; otherwise, a missing assembly results in `INVALID_SYNCHRONIZATION_STATE`, even if no public shader-module object exists yet. For `CommandBufferData` without `CREATE`, the target XID MUST identify a live command buffer: unknown or non-live XIDs result in `BadValue`, a live resource of the wrong type results in `BadMatch`, and a command buffer outside `RECORDING` results in `INVALID_SYNCHRONIZATION_STATE`. All checks occur before any state change.


## `CreateDevice`: Feature and Extension Requirements

Error mapping distinguishes invalid input from valid but unsupported requirements:

- `feature_id` is not defined in the XAverius feature registry: `BadValue`.
- `feature_id` is registered but is not supported by the selected physical device: `BadMatch`.
- A feature record with `enabled != 1` or a duplicate feature ID: `BadValue`.
- An extension name that is empty, longer than 255 bytes, or syntactically invalid: `BadValue`.
- An extension name that is syntactically valid but unknown to the XAverius extension registry or unsupported by the physical device: `BadMatch`.
- Duplicate extension names: `BadValue`.
- All requirements MUST be checked before device creation. On any failure, the requested `device_xid` remains unallocated; the server MUST NOT silently omit features or extensions.

The following error precedence applies to `CreateDevice` and refines the general XID rule for this request. It MUST match the ordered phases in [Device Discovery and Logical Devices](devices.md):

1. Validate request framing and all wire-only fields: exact length with checked arithmetic, reserved fields, counts, priorities, `enabled = 1`, duplicates, and extension-name syntax/length. Framing failures return `BadLength`; invalid field values return `BadValue`.
2. Validate create-XID `device_xid`; an invalid or occupied target returns `BadIDChoice`.
3. Resolve `physical_device_xid`; an unknown or non-live XID returns `BadValue`.
4. Validate that the resolved XID is a Physical-Device resource and that its ownership/association is valid for this connection; wrong type or invalid ownership/association returns `BadMatch`.
5. Require successful XGE 1.0-or-later negotiation through `GEQueryVersion`; otherwise return `BadMatch`.
6. Check Physical-Device availability; an unavailable device returns `DEVICE_UNAVAILABLE`.
7. Validate queue-family indices and requested queue counts; an out-of-range family index returns `BadValue`, while a valid family unable to supply the requested count returns `BadMatch`.
8. Validate registered feature support and extension registration/support. An unknown feature ID was already rejected in phase 1 with `BadValue`; a registered but unsupported feature, or a syntactically valid but unknown/unsupported extension, returns `BadMatch`.
9. Only after all validation succeeds may backend creation begin. Backend failures use the defined allocation/device error, and no logical Device or child resources may be published.

A later phase MUST NOT override an error from an earlier phase. In particular, malformed wire fields take precedence over XID errors; target-XID validation precedes physical-device lookup; resource type/ownership checks precede XGE negotiation; and XGE negotiation precedes device availability. All feature and extension records must be validated before creation, and every failure leaves `device_xid` unallocated with no partial Device or Queue objects.

## Request-Specific Error Mapping

### `WriteBuffer`

Normative precedence: (1) total length with checked count/overflow arithmetic and the X11 request limit (BadLength); (2) positive data_length and zero padding (BadValue); (3) device_xid, then buffer_xid in wire order (BadValue for unknown/non-live XIDs); (4) live resource type, client ownership, and Device association (BadMatch); (5) Device state (DEVICE_UNAVAILABLE / DEVICE_LOST); (6) Buffer binding, TRANSFER_DST, and range (BadMatch); (7) transfer/synchronization work.

- Total request length with arithmetic overflow or exceeding the connection's X11 limit: BadLength
- Incorrect request length: BadLength
- Zero length, nonzero padding, or invalid reserved fields: BadValue
- Unknown/non-live XAverius XID: BadValue
- Wrong type, wrong Device, unbound Buffer, missing TRANSFER_DST, or range outside the Buffer: BadMatch
- Unavailable/lost Device: DEVICE_UNAVAILABLE / DEVICE_LOST
- Synchronous transfer failure: TRANSFER_FAILED
- Failed staging allocation: ALLOCATION_FAILED
- Detected dependency cycle while waiting for earlier GPU work: DEPENDENCY_FAILED

### `ReadBuffer`

Normative precedence: (1) exact 28-byte length (BadLength); (2) positive data_length (BadValue); (3) device_xid, then buffer_xid in wire order (BadValue for unknown/non-live XIDs); (4) live resource type, client ownership, and Device association (BadMatch); (5) Device state (DEVICE_UNAVAILABLE / DEVICE_LOST); (6) Buffer binding, TRANSFER_SRC, and range (BadMatch); (7) snapshot/transfer work.

- Incorrect request length: BadLength
- Zero length or invalid reserved fields: BadValue
- Unknown/non-live XAverius XID: BadValue
- Wrong type, wrong Device, unbound Buffer, missing TRANSFER_SRC, or range outside the Buffer: BadMatch
- Unavailable/lost Device: DEVICE_UNAVAILABLE / DEVICE_LOST
- Synchronous transfer failure: TRANSFER_FAILED
- Failed staging allocation: ALLOCATION_FAILED
- Dependency cycle detected before the data snapshot is captured: DEPENDENCY_FAILED

### ShaderModuleData

- Incorrect request length or payload size: BadLength
- Zero data_length for a data chunk, nonzero data_length for ABORT, nonzero padding, or an invalid flag combination: BadValue
- Invalid/non-live device_xid: BadValue; wrong live Device type: BadMatch. With CREATE, an invalid/occupied shader_module_xid returns BadIDChoice. Without CREATE, a matching upload assembly is required; if absent, return INVALID_SYNCHRONIZATION_STATE.
- ABORT without a matching upload assembly in progress: INVALID_SYNCHRONIZATION_STATE
- Invalid SPIR-V or a SPIR-V module that does not satisfy the v0.1 validation rules: BadValue; no Shader Module remains live and the assembly is discarded.
- Vulkan creation failure: the specific backend error, such as DEVICE_LOST, ALLOCATION_FAILED, or INTERNAL_SERVER_ERROR; no Shader Module remains live and the assembly is discarded.
- A malformed chunk discards its entire associated assembly. A later X11 error for that chunk is synchronous and leaves no partial Shader Module. Errors during ShaderModuleData upload MUST NOT generate ASYNC_ERROR; Device loss is reported only through the general Device-loss path, not through an additional upload-specific event.

### Device Discovery and Device Creation

- EnumeratePhysicalDevices: a request length other than 8 bytes returns BadLength; the reply payload consists only of complete PHYSICALDEVICEINFO records. An incomplete record MUST NOT be emitted. If no Physical Devices are available, an empty successful reply with reply.length = 0 is permitted.
- GetPhysicalDeviceProperty: incorrect request length returns BadLength; an invalid Atom returns BadAtom; an unknown/non-live Device XID returns BadValue. For any status other than SUCCESS, property_type, value_length, and the reply payload MUST be zero.
- GetPhysicalDeviceQueueFamilyProperties and GetPhysicalDeviceMemoryProperties: exact request length is 12 bytes; an unknown/non-live Physical-Device XID returns BadValue.
- CreateDevice: incorrect length returns BadLength; queue_family_request_count = 0, queue_count = 0, duplicate queue-family records, nonzero reserved fields, invalid priorities, enabled other than 1, duplicate feature/extension entries, unknown feature IDs, or syntactically invalid extension names return BadValue; an invalid/occupied device_xid returns BadIDChoice; an unknown/non-live Physical-Device XID returns BadValue; a live resource of the wrong type, a queue-family request with an unavailable or unsupported queue count, a registered but unsupported feature, an unknown or unsupported syntactically valid extension, or cross-Device access returns BadMatch; an unavailable Physical Device returns DEVICE_UNAVAILABLE. Validation is atomic and does not publish a logical Device on failure.
- CreateDefaultDevice: incorrect length returns BadLength; zero count, nonzero reserved fields, or invalid priorities return BadValue; an invalid/occupied device_xid returns BadIDChoice; missing XGE negotiation returns BadMatch; no suitable Device returns DEVICE_UNAVAILABLE.

  Normative precedence for CreateDefaultDevice: (1) exact/formula-based request length with checked arithmetic (BadLength); (2) queue_count, reserved fields, and all priorities (BadValue); (3) target XID device_xid (BadIDChoice); (4) successful XGE 1.0 negotiation (BadMatch); (5) selection of a suitable Physical Device and compute queue (DEVICE_UNAVAILABLE). All checks occur before a logical Device is published; on any error, the target XID remains unallocated.
- Both requests are Void requests; success produces no normal reply.
- DestroyDevice: incorrect length returns BadLength; unknown/non-live XAverius XID returns BadValue; foreign Device ownership returns BadMatch.

### `SelectEvents`

- An incorrect request length results in `BadLength`.
- If the client has not successfully negotiated at least XGE 1.0 with `GEQueryVersion`, the request results in `BadMatch`.
- An unknown scope, nonzero flags/reserved fields, invalid mask bits, or nonzero fields outside the selected scope results in `BadValue`.
- An unknown or non-live Device XID, or an invalid queue-family/queue index, results in `BadValue`; a live resource of the wrong type or foreign client ownership results in `BadMatch`.
- An error leaves the previous event selection unchanged; a successful request atomically replaces only the selection for the specified scope.

### `CreateDescriptorSetLayout`

- Incorrect request length or a payload inconsistent with binding_count: BadLength
- Nonzero flags, reserved/invalid field values, unknown or unsupported stage bits, unsupported descriptor type, or invalid binding records: BadValue
- Invalid or already-occupied create XID: BadIDChoice
- Unknown/non-live Device XID: BadValue; wrong live resource type, foreign Device ownership, or cross-Device resource: BadMatch
- Unavailable/lost Device: DEVICE_UNAVAILABLE / DEVICE_LOST; synchronous backend allocation failure: ALLOCATION_FAILED
- Any error leaves the Descriptor Set Layout unallocated; partial results are not permitted.

### `CreateCommandPool`

- An incorrect request length results in `BadLength`.
- Unknown pool flags or nonzero reserved bits result in `BadValue`; an invalid or already allocated pool XID results in `BadIDChoice`.
- An unknown or non-live Device XID results in `BadValue`; a live resource of the wrong type or foreign Device ownership results in `BadMatch`.
- A queue-family index outside the Device profile, or a queue family without command-buffer support, results in `BadValue`.
- An unavailable or lost Device results in `DEVICE_UNAVAILABLE` or `DEVICE_LOST`, respectively; backend allocation failure results in `ALLOCATION_FAILED`.
- On rejection, the pool XID remains unallocated.

### `CommandPool` and `CommandBufferData`

- An incorrect request length, an entry whose declared length exceeds the request boundary, or an incomplete entry header results in `BadLength`.
- Reserved bits/fields, invalid flag combinations, malformed padding, unknown command IDs, or invalid entry lengths (especially zero or less than the entry header) result in `BadValue`.
- After successful wire-structure validation, `CommandBufferData` validates the target XID before the pool XID, following field order. With `CREATE`, an invalid or already allocated target XID results in `BadIDChoice`; without `CREATE`, an unknown or non-live Buffer XID results in `BadValue`, and a live resource of the wrong type results in `BadMatch`.
- An unknown or non-live pool XID results in `BadValue`; a live resource of the wrong type, foreign client ownership, cross-device association, or incorrect pool association results in `BadMatch`. The specified pool MUST match the Buffer's parent pool even for `ABORT`.
- Without `CREATE`, the Buffer must be in `RECORDING`, otherwise `INVALID_SYNCHRONIZATION_STATE` is returned. For CREATE, append, and FINAL, this state check occurs only after successful XID/type/ownership validation and the Device-state check: an unavailable or lost Device returns `DEVICE_UNAVAILABLE` or `DEVICE_LOST` and takes precedence over an incompatible Buffer state. `ABORT` is the explicit logical exception: after structure, field, XID, type, and ownership validation, the `RECORDING` state is checked even if the Device is unavailable or lost; for a valid live Buffer/pool pair with matching parent pool, ABORT remains permitted after Device loss and starts no Vulkan work.
- `ResetCommandBuffer` with an incorrect request length results in `BadLength`; unknown or non-live Device/Buffer XIDs result in `BadValue`; a live resource of the wrong type, foreign ownership, or cross-device use results in `BadMatch`.
- After successful XID/ownership validation, an unavailable or lost logical Device returns `DEVICE_UNAVAILABLE` or `DEVICE_LOST` before the pool reset flag or Buffer state is checked.
- `ResetCommandBuffer` without the `RESET_COMMAND_BUFFER` pool flag or with a pending Buffer is rejected with `INVALID_SYNCHRONIZATION_STATE`.

### Presentation-only `CMD_COPY_BUFFER_TO_SWAPCHAIN_IMAGE` (provisional command entry)

These rules apply only to the presentation-capable profile; `CMD_COPY_BUFFER_TO_SWAPCHAIN_IMAGE` is assigned Command Entry ID 5 in the central registry. Error precedence is: (1) command-entry structure, exact entry length, `entry_length`, and reserved fields; (2) entry-local field syntax, especially four-byte alignment of `buffer_offset` and the requirement that `row_length`/`image_height` be zero or positive; (3) resolve Buffer XID and then Swapchain XID (`BadValue` for unknown/non-live XIDs); (4) type, client/Device ownership, and cross-Device association (`BadMatch`); (5) validate resource-dependent values: `image_index` outside the Swapchain, effective row length/height smaller than the Swapchain extent, or a source range outside the Buffer return `BadValue`; (6) validate usage flags: a Buffer without `TRANSFER_SRC` or a Swapchain without `TRANSFER_DST` returns `BadMatch`; (7) validate Device/submission state and image state. This order prevents XID-dependent checks before resource resolution while ensuring entry-local syntax errors are not masked by an invalid XID. Image-state validation is atomic at submission acceptance: if the image is not `ACQUIRED` or the submission races a present transition, return `INVALID_SYNCHRONIZATION_STATE`. The check accounts for all earlier state transitions accepted in X11 request order: a copy submission after an accepted `QueuePresent` transition to `PRESENT_PENDING` is rejected; an earlier accepted submission remains valid and retains its internal references. Request order does not replace GPU synchronization. Rejection MUST NOT partially accept the Command Buffer or change image, reference, or semaphore state. Swapchain destruction remains rejected while a recording Command Buffer references it; after successful destruction, a non-pending executable Command Buffer with that reference is invalidated.

### Unified XID and State Mapping for Selected Requests

Validation occurs in this order: wire length and structural integrity; field values and reserved fields; resolution of each required XID; resource type and ownership; request-specific state and backend checks. An error terminates the request without partial changes. An optional XID whose defined value is 0 is not resolved.

| Request / Condition | Error |
|---|---|
| DestroyResource: incorrect length | BadLength |
| DestroyResource: XID does not resolve to a live resource | BadValue for unknown/non-live XIDs; BadMatch for a live resource of the wrong type |
| DestroyResource: resource type is not eligible for the generic request or the resource belongs to another client | BadMatch |
| DestroyResource: resource is referenced by a RECORDING Command Buffer or its type-specific pending-use rule prohibits destruction | INVALID_SYNCHRONIZATION_STATE |
| BindBufferMemory: incorrect length | BadLength |
| BindBufferMemory: invalid field values or nonzero reserved fields, where present | BadValue |
| BindBufferMemory: Device, Buffer, or Memory XID is invalid/non-live | BadValue for unknown/non-live XIDs; BadMatch for a live resource of the wrong type |
| BindBufferMemory: wrong resource type or mismatched client/Device ownership | BadMatch |
| BindBufferMemory: Device unavailable/lost, after XID/type/ownership checks and before binding-dependent state/backend checks | DEVICE_UNAVAILABLE / DEVICE_LOST |
| BindBufferMemory: Buffer already bound, disallowed Memory Type, invalid alignment, or allocation too small | BadMatch |
| UpdateDescriptorSets: incorrect total length or payload inconsistent with write_count | BadLength |
| UpdateDescriptorSets: write_count = 0, nonzero reserved fields, duplicate writes to the same slot, invalid values/flags, or unassigned descriptor_type | BadValue |
| UpdateDescriptorSets: invalid/non-live Device, Set, or Buffer XID | BadValue for unknown/non-live XIDs; BadMatch for a live resource of the wrong type |
| UpdateDescriptorSets: wrong live type, foreign client/Device ownership, incompatible layout/binding/array slot or assigned descriptor type, unbound Buffer, or invalid range/alignment | BadMatch |
| UpdateDescriptorSets: Device unavailable/lost, after XID/type/ownership checks and before layout/binding/pending-state checks | DEVICE_UNAVAILABLE / DEVICE_LOST |
| UpdateDescriptorSets: layout/binding/slot incompatibility or affected Set used by accepted work | BadMatch / INVALID_SYNCHRONIZATION_STATE as applicable |
| QueueSubmit: incorrect length, inconsistent counts, or length arithmetic overflow | BadLength |
| QueueSubmit: zero or already-used connection token; reserved fields; syntactically invalid wait-stage mask (zero or reserved bits); invalid type-independent values; duplicate raw wait/signal Semaphore XIDs; or the same Semaphore in both arrays | BadValue |
| QueueSubmit: invalid/non-live Device, Command Buffer, Semaphore, or nonzero Fence XID | BadValue for unknown/non-live XIDs; BadMatch for a live resource of the wrong type |
| QueueSubmit: wrong resource type, foreign client/Device ownership, or queue not created for this Device | BadMatch |
| `QueueSubmit`: Device unavailable/lost after successful XID/type/ownership/queue validation and before mutable submission-state checks | `DEVICE_UNAVAILABLE` / `DEVICE_LOST` |
| `QueueSubmit`: type-dependent Binary value is nonzero or Timeline signal value is not greater than the observable counter, after XID, type, and Device-state checks | `BadValue` |
| `QueueSubmit`: Timeline signal value exceeds the observable counter but conflicts with an already reserved pending GPU signal value | `INVALID_SYNCHRONIZATION_STATE` |
| `QueueSubmit`: a Command Buffer is not `EXECUTABLE`, a Fence is not submit-eligible, a Semaphore state is invalid, or a syntactically valid wait-stage mask contains a stage unsupported by the addressed queue family | `INVALID_SYNCHRONIZATION_STATE` |
| QueueSubmit: dependency prevents acceptance when no more specific state rule applies | DEPENDENCY_FAILED |
| `QueueSubmit`: synchronous error before acceptance | no state changes; the token remains unused, command buffers remain `EXECUTABLE`, Fence/Semaphore states and internal references remain unchanged; no submission event or `ASYNC_ERROR` is emitted |
| ResetFence: incorrect length | BadLength |
| ResetFence: invalid/non-live Device or Fence XID | BadValue for unknown/non-live XIDs; BadMatch for a live resource of the wrong type |
| ResetFence: wrong resource type or Fence belongs to another client/Device | BadMatch |
| ResetFence: Fence is neither SIGNALED nor FAILED | INVALID_SYNCHRONIZATION_STATE |
| ResetFence: Device lost | DEVICE_LOST |

For all five requests, errors before acceptance are reported synchronously as X11 errors; the request MUST NOT leave partial changes. After QueueSubmit has been accepted, execution failures are reported only through submission terminal events and associated states, not as delayed X11 errors. An unavailable state is reported only when the request actually requires further backend work; purely logical cleanup after Device loss follows the applicable lifetime rules.

### Synchronization Requests

- `CreateSemaphore`: incorrect length `BadLength`; invalid type, value, flags, or reserved fields `BadValue`; invalid or already allocated create XID `BadIDChoice`; unknown or non-live Device XID `BadValue`; wrong live resource type or foreign Device ownership `BadMatch`; unavailable or lost Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; backend allocation failure `ALLOCATION_FAILED`. On rejection, the target XID remains unallocated.
- `CreateFence`: incorrect length `BadLength`; invalid flags or reserved fields `BadValue`; invalid or already allocated create XID `BadIDChoice`; unknown or non-live Device XID `BadValue`; wrong live resource type or foreign Device ownership `BadMatch`; unavailable or lost Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; backend allocation failure `ALLOCATION_FAILED`. On rejection, the target XID remains unallocated.
- `GetSemaphoreCounterValue`: incorrect length `BadLength`; unknown or non-live Device or Semaphore XIDs `BadValue`; wrong live resource type, foreign ownership, or cross-device use `BadMatch`; only Timeline semaphores are valid; after Device loss, return `DEVICE_LOST` rather than a counter reply.
- `SignalSemaphore`: normative precedence: incorrect length `BadLength`; resolve Device XID, then Semaphore XID (`BadValue` for unknown or non-live XIDs); validate resource type, ownership, and cross-device use (`BadMatch`); check Device state (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); finally validate semaphore type and signal-value/reservation rules (Binary semaphore `BadMatch`, invalid counter or reservation relation `INVALID_SYNCHRONIZATION_STATE`). A synchronous rejection performs no partial host signal and leaves counters and reservations unchanged.
- `WaitSemaphores`: normative precedence: length and overflow `BadLength`; then zero count, invalid wait mode, or duplicate Semaphore XIDs `BadValue`; then resolve Device and Semaphore XIDs in array order (`BadValue` for unknown or non-live XIDs); validate type, ownership, and cross-device use (`BadMatch`); check Device state (`DEVICE_LOST`); finally require every Semaphore to be `TIMELINE` (`BadMatch`). These errors occur before wait registration and leave state unchanged. Device loss of an already registered wait is terminal and reported as X11 error `DEVICE_LOST`; `DestroyDevice` terminates an open wait with `DEVICE_DESTROYED` unless Device loss was already terminally established. `TIMEOUT` is only a normal reply status.
- `GetFenceStatus`: incorrect length `BadLength`; unknown or non-live Device or Fence XIDs `BadValue`; wrong live resource type, foreign ownership, or cross-device use `BadMatch`. After Device loss, query and return the stored Fence state.
- `ResetFence`: incorrect length `BadLength`; unknown or non-live Device or Fence XIDs `BadValue`; wrong live resource type, foreign ownership, or cross-device use `BadMatch`. After valid XID, type, and ownership checks, `DEVICE_LOST` takes precedence over the Fence state. Only when the Device is available may `SIGNALED` and `FAILED` be reset; other states return `INVALID_SYNCHRONIZATION_STATE`.
- `WaitForFence`: incorrect length `BadLength`; unknown or non-live Device or Fence XIDs `BadValue`; wrong live resource type, foreign ownership, or cross-device use `BadMatch`. Timeout, execution failure, Device loss, and `DestroyDevice` are returned as normal reply statuses, not X11 errors.
- `DestroyFence`: incorrect length `BadLength`; unknown or non-live Device or Fence XIDs `BadValue`; wrong live type, foreign client ownership, or cross-device use `BadMatch`; `INVALID_SYNCHRONIZATION_STATE` while the Fence is `PENDING` or an open `WaitForFence` registration references that exact internal Fence identity. A terminally established wait no longer blocks destruction, even if its reply has not yet been sent. Rejection leaves the XID and Fence state unchanged.
- `DestroySemaphore`: incorrect length `BadLength`; unknown or non-live Device or Semaphore XIDs `BadValue`; wrong live type, foreign client ownership, or cross-device use `BadMatch`; `INVALID_SYNCHRONIZATION_STATE` while an accepted queue wait, queue signal, an open `WaitSemaphores` registration for that exact internal Semaphore identity, or another active host operation uses the Semaphore. A terminally established wait no longer blocks destruction, even if its reply has not yet been sent. Rejection leaves the XID and synchronization state unchanged. Device loss alone does not invalidate public XIDs; subsequent `DestroyDevice` cascade invalidation may bypass these ordinary rejection rules.

### `DestroyResource`

- Incorrect request length: BadLength
- Invalid or no-longer-live XID: BadValue for an unknown/non-live XAverius XID
- Resource type not eligible for the generic request (especially Fence and Semaphore), or incorrect ownership: BadMatch
- Violation of type-specific recording/pending lifetime rules: INVALID_SYNCHRONIZATION_STATE
- Rejection leaves the XID, internal lifetime states, and dependent Command Buffer states unchanged.
- Normative precedence: (1) exact request length (BadLength); (2) resolve resource_xid (BadValue if unknown/non-live); (3) eligible resource type and client ownership (BadMatch); (4) type-specific recording/pending lifetime rules (INVALID_SYNCHRONIZATION_STATE). Validation and public invalidation form one atomic transition. Device loss alone is not an additional rejection reason and MUST NOT cause DestroyResource to return DEVICE_LOST generically. GPU work that is already terminal no longer blocks destruction solely because it was previously pending; actual recording references and type-specific active uses remain decisive. Internal objects and backend references are retained or quarantined until safe quiescence. DestroyDevice may subsequently perform the defined cascading invalidation.

### Resource Destruction and Memory Release

- Destroying a resource referenced by a RECORDING Command Buffer: INVALID_SYNCHRONIZATION_STATE.
- Destroying a pending Command Buffer, Descriptor Set, Buffer, Pipeline, or Pipeline Layout: INVALID_SYNCHRONIZATION_STATE.
- DestroyCommandPool: INVALID_SYNCHRONIZATION_STATE if at least one child Command Buffer is pending.
- DestroyDescriptorPool or FreeDescriptorSets: INVALID_SYNCHRONIZATION_STATE if an affected Set is used by pending work or referenced by a RECORDING Command Buffer.
- DestroyFence: INVALID_SYNCHRONIZATION_STATE while the Fence is associated with a nonterminal submission or an open WaitForFence registration references that exact internal Fence identity.
- DestroySemaphore: INVALID_SYNCHRONIZATION_STATE while an accepted queue wait/signal, an open WaitSemaphores registration for that exact internal Semaphore identity, or another running host operation uses the Semaphore.
- For both requests, a host wait no longer blocks destruction once its terminal result has been serialized by the server; an unsent reply is not a blocker. Device loss alone does not invalidate public XIDs. If DestroyDevice is processed afterward, its Device-wide cascading invalidation may bypass these ordinary rejections.
- FreeMemory: BadMatch while any internally live Buffer remains bound to the allocation, even if its public XID has already been invalidated; INVALID_SYNCHRONIZATION_STATE while accepted work accesses the allocation.
- A destroy request rejected by lifetime rules leaves all public XIDs and Command Buffer states unchanged.
- Device-wide cascading invalidation through DestroyDevice is exempt from these ordinary pending-use rejections; Device loss alone does not invalidate public XIDs. Internal references MUST always be retained safely.

### Buffer and Memory Requests

- CreateBuffer: incorrect fixed length returns BadLength; non-positive size, unknown usage bits, or nonzero reserved fields return BadValue; an invalid/occupied create XID returns BadIDChoice; unknown/non-live Device XID returns BadValue; a live resource of the wrong type or foreign Device ownership returns BadMatch; an unavailable/lost Device returns DEVICE_UNAVAILABLE / DEVICE_LOST; backend creation failure due to memory exhaustion returns ALLOCATION_FAILED. No Buffer remains live after rejection. Precedence: length, scalar fields, target XID, Device XID, type/ownership, Device state, backend creation.
- GetBufferMemoryRequirements: incorrect length returns BadLength; unknown/non-live Buffer/Device XID returns BadValue; wrong resource type or cross-Device access returns BadMatch. Precedence: (1) exact 16-byte length; (2) Device XID, then Buffer XID in wire order; (3) resource type, ownership, and Device association; (4) return stored requirements. The query starts no backend work and remains permitted after Device loss while the public XIDs remain valid.
- `AllocateMemory`: incorrect length `BadLength`; invalid size, memory-type index, or reserved field `BadValue`; invalid or occupied create XID `BadIDChoice`; unknown or non-live Device XID `BadValue`; live resource of the wrong type or foreign Device ownership `BadMatch`; unavailable or lost Device `DEVICE_UNAVAILABLE` / `DEVICE_LOST`; backend allocation failure `ALLOCATION_FAILED`; on rejection, the target XID remains unallocated. Precedence: length, scalar fields, target XID, Device XID, type/ownership, Device state, backend allocation.
- FreeMemory: see the lifetime rules below; on rejection, the allocation remains publicly valid.
- BindBufferMemory: see the specific mapping below.

### Descriptor Pool and Pipeline Requests

- CreateDescriptorPool: incorrect length or payload inconsistent with pool_size_count returns BadLength; invalid counts, duplicate pool-size types, unsupported descriptor types, or nonzero reserved fields return BadValue; invalid/occupied Pool XID returns BadIDChoice; unknown/non-live Device XID returns BadValue; wrong live resource type or foreign Device ownership returns BadMatch; unavailable/lost Device returns DEVICE_UNAVAILABLE / DEVICE_LOST; backend allocation failure returns ALLOCATION_FAILED. On rejection, the Pool XID remains unallocated.
- AllocateDescriptorSets: length/entry structure returns BadLength; count/reserved-field errors return BadValue; target Set XIDs in array order return BadIDChoice; input XIDs in wire order (Device, Pool, Layouts) then return BadValue; wrong live types/ownership return BadMatch; Device state returns DEVICE_UNAVAILABLE / DEVICE_LOST; Pool/Layout incompatibility returns BadMatch; capacity/backend allocation failures return ALLOCATION_FAILED. Precedence and batch atomicity are normative in the request chapter; no subset remains live.
- FreeDescriptorSets: incorrect length returns BadLength; zero count or nonzero reserved fields return BadValue; unknown/non-live Device, Pool, or Set XIDs return BadValue; wrong live resource types, foreign ownership, or a Set not belonging to the specified Pool/Device return BadMatch; pending use or a RECORDING reference returns INVALID_SYNCHRONIZATION_STATE. Logical release remains permitted after Device loss and requires no new Vulkan work; internal references remain until safe quiescence. Rejection frees no subset.
- DestroyDescriptorPool: incorrect request length returns BadLength; unknown/non-live Pool XID returns BadValue; wrong live resource type or foreign client/Device ownership returns BadMatch; if a child Set is used by pending work or referenced by a RECORDING Command Buffer, return INVALID_SYNCHRONIZATION_STATE. Device loss alone is not a rejection reason for logical cleanup; pending/recording checks still apply. Rejection is atomic: the Pool, Sets, and references remain unchanged.
- CreatePipelineLayout: wire-length errors return BadLength; stage/range/reserved-field errors return BadValue; target XID errors return BadIDChoice; Device/Set-Layout XIDs return BadValue; wrong live types/ownership/cross-Device use return BadMatch; Device state returns DEVICE_UNAVAILABLE / DEVICE_LOST; device-dependent limits/compatibility and backend allocation are checked afterward. No Pipeline Layout remains live after rejection.
- CreateComputePipeline: wire-length errors return BadLength; entry-point/padding/reserved-field errors return BadValue; target XID errors return BadIDChoice; Device/Layout/Shader XIDs return BadValue; wrong live types/ownership/cross-Device use return BadMatch; Device state returns DEVICE_UNAVAILABLE / DEVICE_LOST; backend creation/allocation is checked afterward. No Pipeline object remains live after rejection.

### Command Pool Requests

- CreateCommandPool: incorrect length returns BadLength; unknown flags or nonzero reserved fields return BadValue; invalid/occupied Pool XID returns BadIDChoice; unknown/non-live Device XID returns BadValue; wrong live resource type or foreign Device ownership returns BadMatch; a queue-family index outside the Device profile or without Command Buffer support returns BadValue.
- DestroyCommandPool: incorrect length returns BadLength; unknown/non-live XID returns BadValue; wrong type or cross-Device ownership returns BadMatch; at least one pending child Command Buffer returns INVALID_SYNCHRONIZATION_STATE. Device loss alone is not a rejection reason; once affected submissions are terminal and their Command Buffers are no longer pending, logical pool cleanup remains permitted. Rejection is atomic.

### Synchronization Requests

- CreateSemaphore and CreateFence: incorrect length returns BadLength; invalid types, values, flags, or reserved fields return BadValue; invalid/occupied create XID returns BadIDChoice; unknown/non-live Device XID returns BadValue; wrong live resource type or foreign Device ownership returns BadMatch; unavailable/lost Device returns DEVICE_UNAVAILABLE / DEVICE_LOST; backend allocation failure returns ALLOCATION_FAILED. On rejection, the target XID remains unallocated.
- GetSemaphoreCounterValue: incorrect length returns BadLength; unknown/non-live Device or Semaphore XIDs return BadValue; wrong live resource type, foreign ownership, or cross-Device use returns BadMatch; only Timeline semaphores are valid; after Device loss, return DEVICE_LOST instead of a counter reply.
- SignalSemaphore precedence: incorrect length returns BadLength; resolve Device XID, then Semaphore XID (BadValue for unknown/non-live); resource type/ownership/cross-Device checks (BadMatch); Device state (DEVICE_UNAVAILABLE / DEVICE_LOST); finally check Semaphore type and signal-value/reservation rules (Binary returns BadMatch, invalid counter/reservation relation returns INVALID_SYNCHRONIZATION_STATE). A synchronous rejection does not partially perform a host signal and leaves the counter and reservations unchanged.
- WaitSemaphores precedence: length/overflow returns BadLength; then zero count, invalid wait mode, or duplicate Semaphore XIDs return BadValue; then resolve Device XID and Semaphore XIDs in array order (BadValue for unknown/non-live); then type/ownership/cross-Device checks (BadMatch); then Device state (DEVICE_LOST); finally, every Semaphore must be TIMELINE (BadMatch). These errors occur before wait registration and change no state. Device loss of an already registered wait is terminal and reported as X11 error DEVICE_LOST; DestroyDevice terminates an open wait with DEVICE_DESTROYED unless Device loss was already established as terminal. TIMEOUT is only a normal reply status.
- GetFenceStatus: incorrect length returns BadLength; unknown/non-live Device or Fence XIDs return BadValue; wrong live resource type, foreign ownership, or cross-Device use returns BadMatch; after Device loss, query the stored Fence state.
- ResetFence: incorrect length returns BadLength; unknown/non-live Device or Fence XIDs return BadValue; wrong live resource type, foreign ownership, or cross-Device use returns BadMatch; after valid XID/type/ownership checks, DEVICE_LOST takes precedence over Fence state; only SIGNALED and FAILED may be reset while the Device is available, and other states return INVALID_SYNCHRONIZATION_STATE.
- DestroyFence: incorrect length returns BadLength; unknown/non-live Device or Fence XID returns BadValue; wrong live type, foreign client ownership, or cross-Device use returns BadMatch; INVALID_SYNCHRONIZATION_STATE applies while the Fence is PENDING or an open WaitForFence registration references that exact internal Fence identity. A wait registration whose terminal result is already established does not block destruction, even if its reply has not yet been sent. Every rejection leaves the XID and Fence state unchanged.
- DestroySemaphore: incorrect length returns BadLength; unknown/non-live Device or Semaphore XID returns BadValue; wrong live type, foreign client ownership, or cross-Device use returns BadMatch; INVALID_SYNCHRONIZATION_STATE applies while an accepted queue wait, queue signal, open WaitSemaphores registration for that exact internal Semaphore identity, or another running host operation uses the Semaphore. A wait registration whose terminal result is already established does not block destruction, even if its reply has not yet been sent. Every rejection leaves the XID and synchronization state unchanged. Device loss alone does not invalidate public XIDs; if DestroyDevice is processed afterward, its cascading invalidation may bypass these ordinary rejections.
- The binding XID mapping is defined in the “Normative XID Error Rule” section: unknown/non-live XAverius XIDs return BadValue, live resources of the wrong type return BadMatch, and invalid Atoms return BadAtom.

### Memory Allocation and Binding

- GetBufferMemoryRequirements: incorrect request length returns BadLength; unknown/non-live Device or Buffer XID returns BadValue; live resource of the wrong type or a Buffer belonging to another Device returns BadMatch.
- AllocateMemory: incorrect request length returns BadLength; non-positive allocation size, nonzero reserved field, or nonexistent Memory-Type index returns BadValue; unknown/non-live Device XID returns BadValue; wrong live resource type returns BadMatch; unavailable/lost Device returns DEVICE_UNAVAILABLE / DEVICE_LOST; backend allocation failure returns ALLOCATION_FAILED. On any error, the requested memory_xid remains unallocated.
- FreeMemory: incorrect request length returns BadLength; unknown/non-live Device or Memory XID returns BadValue; wrong live resource type, foreign ownership, or cross-Device use returns BadMatch; any internally live Buffer still bound to the allocation returns BadMatch (even if its public Buffer XID has been invalidated); accepted GPU work accessing the allocation returns INVALID_SYNCHRONIZATION_STATE. On rejection, the allocation remains unchanged.
- BindBufferMemory: incorrect request length returns BadLength; unknown/non-live Device, Buffer, or Memory XID returns BadValue; wrong live resource type, foreign ownership, or cross-Device use returns BadMatch; incompatible Memory Type, already-bound Buffer, invalid alignment, or insufficient allocation bounds returns BadMatch. On rejection, the Buffer remains unbound.

### BindBufferMemory

The complete XID, ownership, field-value, and Device error mapping is provided in the unified table above. Cross-Device use, an already-bound Buffer, invalid alignment, insufficient allocation size, or an incompatible Memory Type returns BadMatch.

### UpdateDescriptorSets

The complete XID, ownership, field-value, and Device error mapping is provided in the unified table above. The request remains atomic on every error.

Every request MUST have a complete, concrete error mapping before implementation acceptance.

### Presentation requests (presentation-capable profile)

These rules apply to the presentation-capable profile only. The central request registry assigns `CreateSurface` through `QueuePresent` append-only subopcodes 41–47. This assignment does not make the presentation profile part of the compute-only v0.1 baseline; a compute-only server rejects these requests with core `BadRequest` before payload parsing or XID resolution.

- All presentation requests validate the exact fixed or formula-based request length first; a mismatch or overflow in `40 + 4 * wait_semaphore_count` is `BadLength`. Non-zero reserved fields, invalid enum/flag values, zero presentation tokens, duplicate wait semaphore XIDs, and malformed count/field combinations are `BadValue`. Reuse of a token from an already accepted presentation is a stateful acceptance check, not scalar syntax.
- `CreateSurface`: invalid/already allocated target `surface_xid` is `BadIDChoice`; an unknown, destroyed, or non-Window core X11 `window_xid` is core X11 `BadWindow`; a live Window owned by another X11 client is `BadMatch`. A failed create leaves the target XID unallocated and retains no window reference.
- `DestroySurface`: unknown/non-live Surface XID is `BadValue`; a live XID of another type or a Surface owned by another connection is `BadMatch`; any live Swapchain still referencing the Surface causes atomic rejection with `INVALID_SYNCHRONIZATION_STATE`. The only request-level lifetime blocker is a live Swapchain reference. Internal Window-identity tombstones and already-retained backend/notification references do not by themselves block destruction; after successful public invalidation they remain retained internally until quiescent. The checks and public invalidation are serialized atomically against Window lifecycle notifications and connection teardown: Window destruction first leaves the Surface `SURFACE_LOST`, which remains explicitly destroyable once no live Swapchain references it; successful `DestroySurface` first invalidates the public XID so later notifications cannot affect a reused XID. A rejected destroy leaves the Surface and its references unchanged.
- `GetSurfaceCapabilities`: unknown/non-live Device or Surface XID is `BadValue`; a live wrong type or foreign connection ownership is `BadMatch`. A Surface is not Device-owned, so querying the same live Surface with different owned Devices is valid; the reply reports each Device/Surface pair's support independently and does not migrate resources. `SUCCESS`, `TEMPORARILY_NOT_PRESENTABLE`, `SURFACE_LOST`, and `DEVICE_LOST` are normal reply statuses, not X11 errors. Status-dependent zero fields and the reply-length formula remain mandatory.
- `CreateSwapchain`: invalid/already allocated target `swapchain_xid` is `BadIDChoice`; unknown/non-live Device or Surface XID is `BadValue`; wrong live type, foreign ownership, or cross-device combination is `BadMatch`; zero image count or dimensions, unknown format/color-space/present-mode identifiers, unassigned usage bits, or non-zero reserved fields are `BadValue`. A syntactically valid but unsupported configuration returns `UNSUPPORTED_CONFIGURATION`; a zero-sized Surface or requested extent outside current bounds returns `OUT_OF_DATE`, except that a requested width or height of zero is rejected earlier as `BadValue` during scalar validation. `SURFACE_LOST`, `DEVICE_LOST`, and `ALLOCATION_FAILED` are normal reply statuses. On every non-success status the target XID remains unallocated. After wire-length and scalar-field validation, XID validation follows request field order: resolve `device_xid`, validate the target `swapchain_xid` as a create-XID, then resolve `surface_xid`. Capability/status checks occur only after these XID, type, ownership, and Device-state checks.
- `DestroySwapchain`: unknown/non-live Swapchain XID is `BadValue`; a live wrong type or foreign ownership is `BadMatch`; a recording command buffer, pending acquire registration, accepted queue work, accepted presentation, or possible backend access causes atomic rejection with `INVALID_SYNCHRONIZATION_STATE`; non-pending executable command buffers referencing the Swapchain are invalidated atomically on successful destruction. An acquired-but-idle image alone does not block destruction.
- `AcquireNextImage`: unknown/non-live Device or Swapchain XID is `BadValue`; wrong live type, foreign ownership, or cross-device use is `BadMatch`; a supplied semaphore/fence with wrong type, ownership, or device is `BadMatch`; an ineligible semaphore/fence state or conflicting pending acquisition is `INVALID_SYNCHRONIZATION_STATE`. `TIMEOUT`, `NOT_READY`, `OUT_OF_DATE`, `SURFACE_LOST`, `DEVICE_LOST`, and `DEVICE_DESTROYED` are normal reply statuses and must not signal either synchronization object or change image state. `DestroyDevice` terminalizes any still-open acquire with `DEVICE_DESTROYED`; a previously serialized terminal result wins.
- `QueuePresent`: unknown/non-live Device, Swapchain, or wait-semaphore XID is `BadValue`; wrong live type, foreign ownership, or cross-device use between the Device, Swapchain, and wait semaphores is `BadMatch`; nonexistent queue-family/index or image index outside the Swapchain is `BadValue`; a valid queue family whose capability record has `present_supported = 0` for the target Surface is `BadMatch`; an image not in `ACQUIRED`, or a wait semaphore that cannot be legally consumed because of an incompatible pending wait/state, is `INVALID_SYNCHRONIZATION_STATE`; a wait semaphore already marked `UNTRUSTED` is rejected with `DEPENDENCY_FAILED`. A zero token, duplicate wait XID, or reuse of a token reserved by an earlier accepted presentation is `BadValue`. `OUT_OF_DATE`, `SURFACE_LOST`, and `DEVICE_LOST` are normal reply statuses with the precedence defined below. Any rejected `QueuePresent` leaves the image state as it was immediately before that request, leaves wait-semaphore state unchanged, and does not reserve its presentation token. If an independent Device-loss transition has already invalidated the image, rejection does not restore it to `ACQUIRED`. Token uniqueness is checked against previously accepted presentations and recorded atomically with acceptance.
- For all seven requests, validation is atomic: no partial object, reference, image-state, synchronization-state, or token change attributable to the request may remain after a synchronous error or a non-success status. Independent asynchronous lifecycle transitions (especially Device loss) still take effect and are not rolled back by a rejected request. An accepted `QueuePresent` cannot later produce an X11 request error; its terminal result is reported through the presentation events and image/Swapchain state.

### Normative validation precedence for the seven presentation requests

The following order is normative and applies before any externally visible state change. It supplements the request-specific error mapping above; a later stage MUST NOT run before an earlier stage has succeeded.

1. Validate exact/fixed or formula-derived wire length using checked wide arithmetic. A length mismatch or arithmetic overflow is `BadLength`.
2. Validate scalar syntax and reserved fields, including nonzero `presentation_token`, legal `wait_semaphore_count`, unique wait-semaphore XIDs, and create-request scalar values. Invalid scalar syntax is `BadValue`. For variable `QueuePresent`, compute `40 + 4 * wait_semaphore_count` with checked arithmetic before reading the wait array. Do not test whether a nonzero presentation token was previously accepted at this stage; that depends on mutable server state.
3. Resolve request XIDs in wire-field order. For create requests, validate the target XID at its defined create-XID position; `CreateSurface` checks `surface_xid` before resolving `window_xid`, while `CreateSwapchain` checks `device_xid`, then target `swapchain_xid`, then `surface_xid`. Unknown/non-live XAverius resource XIDs are `BadValue`; an unknown, destroyed, or non-Window core X11 `window_xid` is `BadWindow`.
4. Validate live resource types, connection ownership, Device ownership, and cross-device relationships. A live wrong type or ownership mismatch is `BadMatch`. For `CreateSurface`, a live Window belonging to another X11 client is `BadMatch`.
5. For requests with a Device, check Device availability after valid XIDs/types/ownership. If the reply has a defined `DEVICE_LOST` status (`GetSurfaceCapabilities`, `CreateSwapchain`, `AcquireNextImage`, `QueuePresent`), return that status; otherwise use the request's established Device error. Device loss takes precedence over Surface loss and all later mutable-state checks.
6. Validate request-specific indices and immutable constraints: queue-family/index existence, image-index bounds, and syntactic format/mode/usage identifiers. Failures use the request-specific X11 error mapping. A valid but unsupported configuration is not a syntax error and is handled by the normal status rules below.
7. Resolve lifecycle/capability outcomes before mutable image/semaphore eligibility: `GetSurfaceCapabilities` returns `SURFACE_LOST` for a lost Surface; `CreateSwapchain` returns `SURFACE_LOST` for a lost Surface and `OUT_OF_DATE` for a zero-sized Surface or a requested extent outside current bounds; `AcquireNextImage` returns `SURFACE_LOST` or `OUT_OF_DATE` before evaluating availability/timeout; `QueuePresent` returns `SURFACE_LOST` before `OUT_OF_DATE`. A valid `QueuePresent` queue-family tuple with no presentation support is `BadMatch` before the image-state check. A valid but unsupported swapchain configuration returns `UNSUPPORTED_CONFIGURATION` only after the higher-priority lifecycle statuses have been ruled out.
8. Validate mutable state and synchronization eligibility, then commit all state changes atomically. For `QueuePresent`, after higher-priority XID, Device, queue/index, lifecycle, and presentation-support checks, reject reuse of a token from an earlier accepted presentation with `BadValue`; then check image state, and if it is `ACQUIRED`, validate wait semaphores in array order. For each wait, `UNTRUSTED` yields `DEPENDENCY_FAILED`; another incompatible state or pending-wait conflict yields `INVALID_SYNCHRONIZATION_STATE`. A state failure leaves all object/image/semaphore state, references, and token reservations unchanged by that request; it does not roll back an independent asynchronous lifecycle transition. On successful `QueuePresent` acceptance, reserve the token and all semaphore wait slots and transition the image to `PRESENT_PENDING` as one indivisible commit.

For a new `AcquireNextImage` evaluation, after the preceding validation stages, `DEVICE_LOST` takes precedence over `SURFACE_LOST`, which takes precedence over `OUT_OF_DATE`; these outcomes precede mutable synchronization-state checks and timeout polling. Once lifecycle checks pass, validate every supplied semaphore/fence for acquisition-signal eligibility and absence of a conflicting pending acquire before polling or registering the wait; an ineligible object or conflicting registration returns `INVALID_SYNCHRONIZATION_STATE` even if no image is available or the timeout is zero. Only a usable swapchain with eligible synchronization objects reaches the timeout decision. A zero timeout then returns `NOT_READY` if no image is immediately available; a finite timeout returns `TIMEOUT` only when it expires. `DEVICE_DESTROYED` applies only when `DestroyDevice` terminalizes an already-pending acquire registration; the first terminal result serialized by the server wins, and `DestroyDevice` cannot overwrite an earlier terminal result.

For `QueuePresent`, status replies (`OUT_OF_DATE`, `SURFACE_LOST`, `DEVICE_LOST`) and synchronous X11 errors are pre-acceptance outcomes: the rejected request itself consumes no semaphore, reserves no token, and makes no image-state change. The image remains in its pre-request state; a separate lifecycle transition such as Device loss may already have invalidated it. Token reuse is a `BadValue` only if that token belongs to a previously accepted presentation; a token used only by a rejected attempt remains available. A zero token is always `BadValue`.

## Synchronous versus Asynchronous Errors

An error before acceptance is reported by an X11 error or the explicitly defined normal error reply. The request MUST NOT leave partial state.

An error after acceptance is reported through XAverius events and synchronization states. A later X11 error for an already-accepted request is invalid.
