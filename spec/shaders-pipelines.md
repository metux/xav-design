# 6. Shaders, Descriptor Layouts, and Pipelines

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

If a chunk is malformed, has invalid padding, exceeds a limit, or otherwise fails validation, the request receives an X11 error and the entire in-progress upload for that XID is discarded. A failed `FINAL` also discards the assembly and leaves no live shader-module resource. After cleanup, the client may retry using the same XID if it remains a valid unused XID under normal X11 resource-ID rules. An `ABORT` of an existing upload discards it; an `ABORT` with no matching upload fails with the request-specific invalid-state error and changes nothing. Disconnect and device loss discard all affected incomplete uploads synchronously with respect to the connection/device state transition. A later chunk or ABORT for a discarded assembly finds no matching upload and fails with `INVALID_SYNCHRONIZATION_STATE`; it must not recreate or resurrect the old assembly. Chunk-validation and `FINAL`-creation failures are reported only as the synchronous X11 error for that request. They do not emit `ASYNC_ERROR`; device loss itself may emit the single device-level `DEVICE_LOST` event under the normal lifecycle rules, but must not emit a second upload-specific asynchronous error.

`ShaderModuleData` validation and error precedence are normative: (1) validate the X11 envelope and exact total length `20 + pad4(data_length)` with checked arithmetic (`BadLength`); (2) validate the request-specific flag combination, reserved flag bits, `data_length` constraints, and zero payload padding (`BadValue`); (3) for `CREATE`, validate `shader_module_xid` as a create-XID (`BadIDChoice` for an invalid or occupied XID); (4) resolve `device_xid` (`BadValue` for an unknown/non-live XID); (5) validate resource type and client/device ownership (`BadMatch`); (6) check logical-device state (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (7) check upload-assembly state and chunk-size/aggregate-size limits (`INVALID_SYNCHRONIZATION_STATE` for a missing assembly, `BadValue` for a size/limit violation); (8) on `FINAL`, validate the assembled SPIR-V and create the backend module (`BadValue` for invalid SPIR-V or `ALLOCATION_FAILED` for backend allocation failure, with other Vulkan failures mapped centrally). A failed phase MUST NOT execute later phases or mutate state except for the specified cleanup of the affected in-progress assembly. A failed `CREATE` leaves the target XID unallocated and creates no assembly. A failed continuation or `FINAL` discards the matching assembly atomically. Device loss discards all affected assemblies; after that transition, a request against the still-live lost device reports `DEVICE_LOST` before assembly lookup, while a missing assembly on an otherwise available device reports `INVALID_SYNCHRONIZATION_STATE`. This device-loss rule overrides the generic missing-assembly sentence above. Implementations must bound per-upload and aggregate assembly memory and must not allocate based on unchecked lengths.

SPIR-V validation and Vulkan shader-module creation occur atomically at `FINAL`: on success, the public resource becomes live; on failure, no public resource remains. `pNext` structures and Vulkan allocator callbacks are not transmitted in v0.1.

After successful creation of a Compute Pipeline, the Shader Module may be destroyed subject to Vulkan lifetime rules.

## 6.2 Descriptor Set Layout

`CreateDescriptorSetLayout` is a void request with the following wire layout. The total length is `24 + 16 * binding_count` bytes.

| Offset | Type | Field |
|---:|---|---|
| 8 | XID | `device_xid` |
| 12 | XID | `descriptor_set_layout_xid` |
| 16 | CARD32 | `flags`; MUST be zero in v0.1 |
| 20 | CARD32 | `binding_count` |
| 24 | BINDING[] | `binding_count` Binding-Records |

Each binding record is 16 bytes:

| Relative Offset | Type | Field |
|---:|---|---|
| 0 | CARD32 | `binding` |
| 4 | CARD32 | `descriptor_type` |
| 8 | CARD32 | `descriptor_count` |
| 12 | CARD32 | `stage_flags` |

The request MUST have exactly the length determined by `binding_count`. The total length MUST remain within the normal X11 request-size limit. `binding_count = 0` is permitted and creates an empty layout. For each record, `descriptor_count` MUST be greater than zero. Binding numbers MUST be unique within the layout; duplicate binding numbers invalidate the entire request.

`descriptor_type` and `stage_flags` use only the normative [Descriptor Type Registry](../registries/descriptor-types.md) and [Shader Stage Registry](../registries/shader-stages.md). Every value used MUST be supported in v0.1. The stage mask MUST contain no unknown or unsupported bits and MUST include at least one supported stage. Unsupported descriptor types are rejected; numeric values are not assigned locally in this chapter.

`flags` MUST be zero. Non-zero flags are rejected with `BadValue`; v0.1 does not accept layout flags that are silently ignored. `CreateDescriptorSetLayout` validates in this order: (1) exact count-consistent request length (`BadLength`); (2) flags, binding records, counts, unique binding numbers, descriptor types, and stage bits (`BadValue`); (3) target `descriptor_set_layout_xid` as a create-XID (`BadIDChoice` if invalid or occupied); (4) `device_xid` lookup (`BadValue` for unknown/non-live XID); (5) resource type and client/device ownership (`BadMatch`); (6) logical-device state (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (7) device-limit/descriptor support checks (`BadValue` or `BadMatch` as defined for the violated rule), then backend allocation (`ALLOCATION_FAILED`). Creation is atomic: on failure, no public descriptor set layout is created. Unknown or non-live device XIDs result in `BadValue`; a live resource of the wrong type or foreign device ownership results in `BadMatch`. An unavailable or lost logical device results in `DEVICE_UNAVAILABLE` or `DEVICE_LOST`, respectively; a backend allocation failure results in `ALLOCATION_FAILED`.

In the initial compute test, bindings 0, 1, and 2 are each created as `STORAGE_BUFFER` with descriptor count 1 and stage `COMPUTE`.

After successful pipeline-layout creation, the descriptor set layout may be publicly destroyed if the applicable Vulkan lifetime rules permit it. Internal references are retained according to Vulkan rules.

## 6.3 Descriptor Pool

`CreateDescriptorPool` has the following total length:

`24 + 8 * pool_size_count`

- Offset 8: Device-XID
- Offset 12: Descriptor-Pool-XID
- Offset 16: `CARD32 max_sets`
- Offset 20: `CARD16 pool_size_count`
- Offset 22: `CARD16 reserved = 0`
- Offset 24: array of 8-byte entries

Each pool entry contains `CARD32 descriptor_type` and `CARD32 descriptor_count`.

`max_sets`, `pool_size_count`, and every descriptor count MUST be positive. Duplicate pool-size entries are invalid. `CreateDescriptorPool` validates in this order: (1) exact count-consistent request length (`BadLength`); (2) positive counts, duplicate pool-size types, supported descriptor types, and the reserved field (`BadValue`); (3) target pool XID as a create-XID (`BadIDChoice` if invalid or already occupied); (4) Device XID (`BadValue` for an unknown or non-live XID); (5) resource type and client/Device ownership (`BadMatch`); (6) Device state (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (7) backend allocation (`ALLOCATION_FAILED`). Unknown or non-live Device XIDs result in `BadValue`; a live resource of the wrong type or foreign Device ownership results in `BadMatch`. An unavailable or lost logical Device results in `DEVICE_UNAVAILABLE` or `DEVICE_LOST`, respectively; a backend allocation failure results in `ALLOCATION_FAILED`. Creation is atomic: on any error, the pool XID remains unallocated.

## 6.3.1 Destroy Descriptor Pool

`DestroyDescriptorPool` has a fixed total length of 16 bytes:

- Offset 8: Device-XID
- Offset 12: Descriptor-Pool-XID

The pool MUST belong to the specified logical Device. The request is atomically rejected if any contained Descriptor Set is used by pending work or referenced by a `RECORDING` command buffer; the error is `INVALID_SYNCHRONIZATION_STATE`. On rejection, the pool, its sets, and command-buffer states remain unchanged.

On success, the pool and all contained Descriptor Sets are publicly invalidated. Non-pending `EXECUTABLE` command buffers that reference any of these sets become `INVALID`. Internal objects remain alive until all references and backend accesses have ended.

Device loss alone does not prevent `DestroyDescriptorPool` and does not itself produce a `DEVICE_LOST` error for this logical cleanup. Normal atomic validation still applies: a child Set referenced by a `RECORDING` command buffer continues to block destruction. The client can destroy the relevant Command Pool first; after Device loss, the server MUST NOT start new GPU work and MUST retain internal references until safe quiescence or quarantine.

## 6.4 `AllocateDescriptorSets`

`AllocateDescriptorSets` is a Void request with a fixed 20-byte header.

- Offset 8: Device-XID
- Offset 12: Descriptor-Pool-XID
- Offset 16: `CARD16 descriptor_set_count`
- Offset 18: `CARD16 reserved = 0`
- Offset 20: `DESCRIPTORSETALLOCATION[]`

Each allocation entry is eight bytes and contains a Descriptor Set XID and a Descriptor Set Layout XID.

Total length: `20 + 8 * descriptor_set_count`; `descriptor_set_count` MUST be positive.

`AllocateDescriptorSets` validates in this order: (1) request length and complete allocation entries (`BadLength`); (2) `descriptor_set_count > 0` and reserved fields (`BadValue`); (3) each target Set XID in array order, including duplicates (`BadIDChoice`); (4) input XIDs in wire order: Device, Pool, then Layout XIDs in entry order (`BadValue` for an unknown or non-live XID); (5) resource type, client/Device ownership, and Device association (`BadMatch`); (6) Device state (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (7) Pool/Layout compatibility, pool capacity, and backend allocation (`BadMatch` / `ALLOCATION_FAILED`). The operation is atomic. On error, no subset of the sets may remain publicly created.

## 6.5 `UpdateDescriptorSets`

`UpdateDescriptorSets` is a Void request with a fixed 20-byte header.

- Offset 8: Device-XID
- Offset 12: `CARD16 write_count`
- Offset 14: `CARD16 reserved = 0`
- Offset 16: `CARD32 reserved = 0`
- Offset 20: `DESCRIPTORWRITE[]`

Each write is 36 bytes.

| Relative Offset | Type | Field |
|---:|---|---|
| 0 | XID | Descriptor-Set-XID |
| 4 | CARD32 | `binding` |
| 8 | CARD32 | `array_element` |
| 12 | CARD32 | `descriptor_type` |
| 16 | XID | Buffer-XID |
| 20 | CARD64 | `buffer_offset` |
| 28 | CARD64 | `range` |

Gesamtlänge: `20 + 36 * write_count`.

In v0.1, only buffer descriptors are supported; Storage Buffer is the primary type for the initial compute path.

The server checks the layout, binding, array slot, type, Device ownership, buffer binding, alignment, range bounds, and device limits.

Multiple writes to the same descriptor slot within one request are invalid and result in `BadValue`. `descriptor_type` MUST be an assigned value in the Descriptor Type Registry; `0` and unassigned values result in `BadValue`. An assigned descriptor type that does not match the type of the specified layout binding results in `BadMatch`. A failed request MUST NOT leave partial changes. On successful update, descriptor-slot contents and their derived internal Buffer references are replaced atomically. Command buffers retain a reference to the Descriptor Set object when binding it; they do not store a snapshot of its slot contents. A non-pending `EXECUTABLE` command buffer therefore uses the set's current descriptor contents at later submission time. A successful update does not invalidate such a command buffer solely because descriptor contents changed.

`UpdateDescriptorSets` uses this validation precedence: (1) request length/count and structural integrity (`BadLength`); (2) syntax and field-local checks, including `write_count > 0`, reserved fields, duplicate writes to the same slot, and assigned `descriptor_type` (`BadValue`); (3) resolve XIDs in wire order—Device XID, then each Descriptor Set XID and Buffer XID per write—with unknown or non-live XIDs resulting in `BadValue`; (4) resource type, client/Device ownership, and cross-Device association (`BadMatch`); (5) Device state (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (6) layout/binding/array-slot/descriptor-type compatibility, buffer binding, alignment, and range bounds (`BadMatch`), followed by checking whether an affected set is used by accepted work (`INVALID_SYNCHRONIZATION_STATE`). The Device-state check takes precedence over these request-specific compatibility and pending-state checks. An error terminates the request without partial changes; on success, all slot contents and derived Buffer references are replaced atomically.

## 6.6 `FreeDescriptorSets`

`FreeDescriptorSets` is a Void request with a fixed 20-byte header.

- Offset 8: Device-XID
- Offset 12: Descriptor-Pool-XID
- Offset 16: `CARD16 descriptor_set_count`
- Offset 18: `CARD16 reserved = 0`
- Offset 20: array of Descriptor Set XIDs

Total length: `20 + 4 * descriptor_set_count`; `descriptor_set_count` MUST be positive. The reserved field MUST be zero. Unknown or non-live Device, Pool, or Set XIDs result in `BadValue`; live resources of the wrong type, foreign ownership, or a Set that does not belong to the specified Pool/Device result in `BadMatch`. `FreeDescriptorSets` is a logical release and remains permitted after Device loss; it MUST NOT start new Vulkan work and MUST retain internal Descriptor Set/backend references until safe quiescence.

Release is atomic: if any requested XID is invalid, or an affected Set is used by pending work or referenced by a `RECORDING` command buffer, no Set is released. Such state conflicts result in `INVALID_SYNCHRONIZATION_STATE`. On success, all requested Sets are immediately invalidated publicly; internal references remain until all permitted accesses have ended.

## 6.7 `CreatePipelineLayout`

`CreatePipelineLayout` is a Void request containing:

- Offset 8: Device-XID
- Offset 12: Pipeline-Layout-XID
- Offset 16: `CARD16 set_layout_count`
- Offset 18: `CARD16 push_constant_range_count`
- Offset 20: Descriptor-Set-Layout-XID-Array
- followed by push-constant range records, each 12 bytes long

Each push-constant range record contains:

- `CARD32 stage_flags`
- `CARD32 offset`
- `CARD32 size`

The total request length is `20 + 4 * set_layout_count + 12 * push_constant_range_count` bytes.

`CreatePipelineLayout` validates in this order: (1) exact count-consistent wire length (`BadLength`); (2) reserved fields, unsupported stage bits, and invalid range field values (`BadValue`); (3) target XID (`BadIDChoice`); (4) Device and Set Layout XIDs in wire order (`BadValue` for an unknown or non-live XID); (5) resource type, ownership, and cross-Device association (`BadMatch`); (6) Device state (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (7) device-dependent limits and Vulkan compatibility of the range/layout combination (`BadValue` or `BadMatch` according to the violated rule), followed by backend creation (`ALLOCATION_FAILED` for an allocation failure). On any error, the Pipeline Layout XID remains unallocated. This order is binding even when multiple errors are present: in particular, an invalid or occupied target XID takes precedence over unknown input XIDs; Device loss takes precedence over device-dependent compatibility checks and backend creation.

After successful creation, the Descriptor Set Layout may be publicly destroyed. Internal references MUST follow the actual Vulkan lifetime requirements.

## 6.8 Compute Pipeline

`CreateComputePipeline` is a Void request. Its normative total length is:

`28 + ((entry_point_length + 3) & ~3)`

- Offset 8: Device-XID
- Offset 12: Pipeline-XID
- Offset 16: Pipeline-Layout-XID
- Offset 20: Shader-Module-XID
- Offset 24: `CARD16 entry_point_length`
- Offset 26: `CARD16 reserved = 0`
- Offset 28: ASCII entry point without a NUL terminator, padded to a four-byte boundary

The entry point MUST be nonempty and contain only ASCII bytes; NUL is forbidden. Padding bytes MUST be zero. The total length MUST be exactly `28 + ((entry_point_length + 3) & ~3)` bytes; `entry_point_length` MUST be positive. Specialization constants are not supported in v0.1. `CreateComputePipeline` validates in this order: (1) exact wire length (`BadLength`); (2) positive entry-point length, nonempty ASCII bytes without NUL, zero padding, and reserved fields (`BadValue`); (3) target Pipeline XID (`BadIDChoice`); (4) Device, Pipeline Layout, and Shader Module XIDs in wire order (`BadValue` for an unknown or non-live XID); (5) resource type, ownership, and cross-Device association (`BadMatch`); (6) Device state (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (7) backend pipeline creation (`ALLOCATION_FAILED` for an allocation failure; other backend failures use the central Vulkan error mapping). Creation is atomic; on error, no Pipeline object is publicly created. This precedence also applies to mixed-invalid requests: an invalid or occupied target XID results in `BadIDChoice` before resolving the Device, Pipeline Layout, and Shader Module; unknown or non-live input XIDs result in `BadValue` before type/ownership checks (`BadMatch`); and Device loss is reported before backend creation. A rejected request does not reserve the target XID.


### Descriptor-slot replacement and concurrent release invariants

A successful `UpdateDescriptorSets` is one atomic transition over the complete write batch. Validation MUST finish for every write before any slot or reference is changed. The server MUST prepare the replacement slot values and their derived Buffer-reference edges, then commit all slot changes and retire the superseded edges as one serialized operation for each affected Descriptor Set. If any write fails, no slot value or reference edge from the request is committed. Duplicate writes to one slot remain invalid even if they would write identical values.

Each slot owns exactly the internal Buffer reference represented by its committed value, if any. Replacing a slot MUST acquire/establish the new reference before making the new value visible, and MUST retire the old reference exactly once after the replacement is committed. Repeating an update with the same Buffer and range MUST NOT leak a reference or retire the still-current reference. Command-buffer derived references are recomputed from the committed set contents: a non-pending command buffer referencing the set retains the set-object reference, while its derived Buffer references must match the current slots, without duplicate ownership edges for the same slot. A Buffer removed from all slots and all other owners MUST cease to be a dependency of those command buffers; a later destruction of that Buffer MUST NOT invalidate them for the removed edge.

Updates to a Descriptor Set MUST be serialized with submission acceptance and set release. If a submission is accepted first, the set is pending and the update is rejected with `INVALID_SYNCHRONIZATION_STATE` without mutation. If the update commits first, a subsequently accepted submission observes the new complete slot contents. There is no intermediate state in which a submission can observe a partially applied write batch. A request racing with `FreeDescriptorSets` or `DestroyDescriptorPool` is ordered at the same server-side state transition: if release wins, the update fails against the invalid set and creates no references; if update wins, release applies its ordinary validation to the resulting set and reference graph. Pool-wide release is atomic across all child sets.

`FreeDescriptorSets` and `DestroyDescriptorPool` MUST first validate the entire target set collection and all pending/recording blockers, then invalidate the relevant public XIDs and transition non-pending executable command buffers that reference those sets to `INVALID` as one atomic operation. Rejection leaves every target set, pool, command-buffer state, slot value, and internal reference unchanged. On success, each descriptor-slot edge and each command-buffer-to-set/derived-buffer edge is retired exactly once by its owning cleanup path; public invalidation alone does not permit freeing a Buffer or its bound Memory while a submission, active operation, or backend access still retains the old internal identity. Concurrent cleanup callbacks MUST use captured internal identities and idempotent edge-retirement state, never re-resolve numeric XIDs.
