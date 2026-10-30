# Device Discovery and Logical Devices

## Device Selection

Two paths are available:

1. `CreateDefaultDevice`: The server selects a suitable physical device and creates a logical device.
2. Explicit selection: call `EnumeratePhysicalDevices`, query properties and `GetPhysicalDeviceQueueFamilyProperties`, then call `CreateDevice`.

Queues are not addressed using queue XIDs. A queue is identified by the tuple

`(device_xid, queue_family_index, queue_index)`

identifiziert.

The queue-family index corresponds to the position in the returned queue-family list. The queue index identifies a queue actually requested from that family.

The v0.1 logical-Device baseline requires Vulkan `timelineSemaphore` support. The server MUST enable this feature on every successfully created logical Device. It is mandatory protocol functionality, not an optional `DEVICEFEATUREREQUEST`; the selected Physical Device's support is reported by `XAverius.timelineSemaphore`.

## `EnumeratePhysicalDevices`

The request has no request-specific payload and is 8 bytes in total. The request type is `Reply`.

After the 32-byte X11 header, the reply contains zero or more `PHYSICALDEVICEINFO` records directly. There is no separate device-count field. Each record, including its padded name, is four-byte aligned, so `reply.length = sum of all record lengths / 4`; if there are no records, `reply.length = 0`.

Fixed record portion: 32 bytes.

| Relative Offset | Type | Field |
|---:|---|---|
| 0 | XID | `physical_device_xid` |
| 4 | CARD32 | `device_type` |
| 8 | CARD32 | `vendor_id` |
| 12 | CARD32 | `device_id` |
| 16 | CARD32 | `api_version` |
| 20 | CARD32 | `driver_version` |
| 24 | CARD32 | `compute_queue_family_count` |
| 28 | CARD16 | `device_name_length` |
| 30 | CARD16 | `reserved = 0` |
| 32 | BYTE[] | UTF-8 device name, without NUL termination, padded to 4 bytes |

The record length is:

`32 + ((device_name_length + 3) & ~3)`

Padding MUST be zero. `compute_queue_family_count` counts only queue families that support compute.

## `GetPhysicalDeviceProperty`

Request:

- Offset 8: Physical-Device-XID
- Offset 12: `ATOM property_atom`
- Total length: 16 bytes

Reply:

| Offset | Type | Field |
|---:|---|---|
| 8 | CARD32 | `status` |
| 12 | CARD32 | `property_type` |
| 16 | CARD32 | `value_length` in Bytes |
| 20–31 | BYTE[12] | Reserved; MUST be zero |
| 32 | BYTE[] | value, padded to 4 bytes |

Statuswerte:

- `SUCCESS = 0`
- `NOT_SUPPORTED = 1`
- `NOT_AVAILABLE = 2`

For a status other than `SUCCESS`, `property_type` and `value_length` MUST be zero and the reply contains no value payload. On success, `reply.length = ceil(value_length / 4)`; for any non-success status, `reply.length = 0`.

Normative validation precedence: (1) require the exact 16-byte request length (`BadLength`); (2) resolve the Physical-Device XID (`BadValue` if unknown or non-live); (3) validate that the live resource is a Physical Device (`BadMatch` otherwise); (4) validate `property_atom` as a server-known X11 Atom (`BadAtom` if invalid); (5) look up the Atom name in the XAverius property registry and evaluate property availability (`NOT_SUPPORTED` or `NOT_AVAILABLE` as applicable). Earlier phases take precedence over later phases when multiple conditions are invalid. This request-specific order treats Atom validation as a lookup, not scalar syntax, and preserves the request's XID/type checks before property lookup. No backend work or state change occurs.

`property_atom` is an ordinary server-assigned X11 Atom ID; XAverius does not assign numeric Atom IDs. The client MUST resolve the canonical name using the standard X11 Atom mechanisms. An Atom ID unknown to the X server results in `BadAtom`. A valid Atom ID whose name is not registered in the XAverius property registry returns `NOT_SUPPORTED`. A registered property whose value is unavailable for the queried physical device returns `NOT_AVAILABLE`. Both status cases use the empty reply encoding described above.

The canonical v0.1 names, types, exact value lengths, and availability rules are defined by the [Physical Device Property and Atom Name Registry](../registries/physical-device-properties.md). The v0.1 entries are `XAverius.deviceUUID`, `XAverius.driverUUID`, `XAverius.compute.maxWorkGroupInvocations`, `XAverius.compute.maxWorkGroupSize`, and `XAverius.timelineSemaphore`. UUIDs are 16 raw bytes, not text strings; `maxWorkGroupSize` is an array of exactly three `CARD32` values in X, Y, Z order.

Normative XAverius property type IDs:

| ID | Type |
|---:|---|
| 0 | `NONE` |
| 1 | `CARD32` |
| 2 | `CARD64` |
| 3 | `ATOM` |
| 4 | `STRING8` |
| 5 | `BYTE_ARRAY` |
| 6 | `CARD32_ARRAY` |
| 7 | `CARD64_ARRAY` |

The complete property registry and its types are defined in the [Physical Device Property and Atom Name Registry](../registries/physical-device-properties.md).

## `GetPhysicalDeviceQueueFamilyProperties`

Request: physical-device XID at offset 8; total length 12 bytes.

Reply: standard reply header followed by 12-byte `QUEUEFAMILYINFO` records. There is no separate count field; `reply.length = 3 * queue_family_count`, where `queue_family_count` is the payload length divided by 12. If there are no queue families, `reply.length = 0`.

| Relative Offset | Type | Field |
|---:|---|---|
| 0 | CARD32 | `queue_flags` |
| 4 | CARD32 | `queue_count` |
| 8 | CARD32 | `reserved = 0` |

Records follow Vulkan order. The payload length MUST be divisible by 12.

Normative validation precedence: (1) exact 12-byte request length (`BadLength`); (2) resolve the Physical-Device XID (`BadValue` for unknown or non-live XIDs); (3) validate that the live resource is a Physical Device (`BadMatch` otherwise); (4) return the server-stored queue-family snapshot for that Physical Device. There is no logical-Device availability phase: removal or failure of the Physical Device does not invalidate its still-live identity or rewrite its stored queue-family metadata. This query performs no backend operation and changes no state. A later `CreateDevice` must independently evaluate current availability and queue support.

The `queue_flags` bits are normatively defined in the [Queue Flag Registry](../registries/queue-flags.md). Servers MUST translate native Vulkan flags into these XAverius wire bits; bits 5–31 are reserved.

## `CreateDevice`

### Normative validation precedence

The following order is normative; the server MUST complete these checks before publishing a logical Device or creating externally visible state:

1. Validate the complete variable-length request framing with checked arithmetic. The exact length formula below must match; truncation, trailing bytes, or arithmetic overflow returns `BadLength`.
2. Validate wire-level and scalar fields: all reserved fields and padding are zero; every queue count is positive; queue-family entries are unique; every priority is finite and in [0,1]; feature IDs and extension names are unique; extension names have valid ASCII Vulkan-name syntax and length 1–255. Any violation returns `BadValue`. An unknown feature ID, because no optional feature IDs are assigned in v0.1, also returns `BadValue` at this stage. A syntactically valid extension name is not rejected merely for being absent from the registry at this stage.
3. Validate `device_xid` as a create-XID. An invalid or already occupied target returns `BadIDChoice`.
4. Resolve `physical_device_xid`; an unknown or no-longer-live XID returns `BadValue`.
5. Validate that the XID is a Physical-Device resource owned by the server and usable by this connection. A live resource of the wrong type or invalid ownership/association returns `BadMatch`.
6. Require successful XGE 1.0-or-later negotiation through `GEQueryVersion`; otherwise return `BadMatch`.
7. Check physical-device availability; if unavailable, return `DEVICE_UNAVAILABLE`.
8. Validate every requested queue-family index and queue count against the selected Physical Device. An out-of-range family index returns `BadValue`; a valid family that cannot supply the requested count returns `BadMatch`. These checks occur only after physical-device availability is established.
9. Check the mandatory v0.1 baseline capability: the selected Physical Device MUST report `XAverius.timelineSemaphore = 1`; otherwise return `BadMatch`. The server MUST enable Vulkan `timelineSemaphore` for the logical Device. It MAY enable `VK_KHR_timeline_semaphore` internally when the selected Vulkan API version requires the extension; this is a protocol-required backend dependency, not a client-requested optional extension. Then check requested registry-defined optional features and extensions against the selected Physical Device. A registered optional feature unsupported by that device, or a syntactically valid extension unknown to the XAverius extension registry or unsupported by that device, returns `BadMatch`. In v0.1 every syntactically valid client extension name is unregistered, because the optional extension registry is intentionally empty.
10. Only after all prior checks succeed may backend device creation begin. If backend creation fails, report the defined allocation/device error and publish no logical Device. Any failure leaves `device_xid` unallocated and creates no partially visible child resources.

A later phase MUST NOT override an error from an earlier phase. In particular, malformed lengths or scalar fields take precedence over XID errors; an unknown feature ID takes precedence over target-XID occupancy; and target-XID validation precedes physical-device lookup. The error mappings below define the outcome within each phase.

Before creation, this connection MUST have successfully negotiated XGE 1.0 or later through `GEQueryVersion`, so that the server can safely deliver later extended XAverius events. Otherwise, `BadMatch` is reported and the target XID remains unallocated.

Request:

| Offset | Type | Field |
|---:|---|---|
| 8 | XID | `device_xid` |
| 12 | XID | `physical_device_xid` |
| 16 | CARD16 | `queue_family_request_count` |
| 18 | CARD16 | `feature_request_count` |
| 20 | CARD16 | `device_extension_count` |
| 22 | CARD16 | `reserved = 0` |
| 24 | variable | Queue-family, feature, and extension requests |

`QUEUEFAMILYREQUEST`:

- `CARD32 queue_family_index`
- `CARD16 queue_count`
- `CARD16 reserved = 0`
- `FLOAT32 queue_priorities[queue_count]`

Size: `8 + 4 * queue_count`.

The count MUST be positive and supported. `queue_family_request_count` MUST be at least 1. Priorities MUST be finite and within [0,1]. Duplicate queue-family entries are invalid.

`DEVICEFEATUREREQUEST`:

- `CARD32 feature_id`
- `CARD32 enabled`

Size: 8 bytes. In v0.1, `enabled` MUST equal 1. Features not listed are not requested. Duplicate feature IDs are invalid.

`DEVICEEXTENSIONREQUEST`:

- `CARD16 name_length`
- `CARD16 reserved = 0`
- ASCII extension name without NUL, padded to four bytes

Size: `4 + ((name_length + 3) & ~3)`.

Duplicate extensions are invalid. Feature IDs and extensions are defined by central registries. The registry distinguishes known feature IDs from unknown IDs; a known feature may or may not be supported by a given physical device. Extension names MUST be non-empty ASCII strings without NUL termination and MUST follow the Vulkan extension-name format: `VK_`, a non-empty author portion, an underscore, and a non-empty extension name. Both portions may contain only ASCII letters, digits, and underscores; extension-name case is preserved and checked exactly. The wire length is limited to 255 bytes; this check occurs before registry lookup.

The following error mapping applies:

- An unknown `feature_id` not defined in the XAverius feature registry results in `BadValue`.
- A registered feature unsupported by the selected physical device results in `BadMatch`.
- A syntactically invalid extension name results in `BadValue`.
- A syntactically valid extension that is unknown to the XAverius extension registry or unsupported by the selected physical device results in `BadMatch`.
- Duplicate feature IDs or extension names result in `BadValue`.
- The server enables only explicitly requested and supported features and extensions. It MUST NOT silently ignore unsupported requests.

All validation occurs before creating the logical device. On failure, `device_xid` remains unallocated and no partial Vulkan objects are published.

The total length is `24 + Σ(8 + 4 * queue_count_i) + 8 * feature_request_count + Σ(4 + ((name_length_j + 3) & ~3))`. Queue-family records appear first, followed by all feature records, then all extension records. The request MUST have exactly this length; extra or missing bytes result in `BadLength`.

`CreateDevice` is a void request. Success produces no reply; failures are reported as ordinary X11 errors for this request. The error mapping for unknown or unsupported features and extensions is defined in [Errors and error mapping](errors.md).

If the selected physical device is unavailable, `DEVICE_UNAVAILABLE` is reported as an X11 error. Creation is atomic: no partially created logical device may remain after a failure.

## `CreateDefaultDevice`

Validation precedence is normative: (1) validate the exact/formula-based request length using checked arithmetic (`BadLength`); (2) validate `queue_count`, the reserved field, and every priority (`BadValue`); (3) validate the target `device_xid` as a create-XID (`BadIDChoice` if invalid or already occupied); (4) require successful XGE 1.0-or-later negotiation through `GEQueryVersion` (`BadMatch` otherwise); (5) select a suitable physical device and compute-capable queue family that reports `XAverius.timelineSemaphore = 1` (`DEVICE_UNAVAILABLE` if none exists). Every check completes before device publication, and failure leaves `device_xid` unallocated.

Request:

- Offset 8: `XID device_xid`
- Offset 12: `CARD16 queue_count`
- Offset 14: `CARD16 reserved = 0`
- Offset 16: `FLOAT32 priorities[queue_count]`

Total length: `16 + 4 * queue_count`.

The queue count MUST be at least 1. All priorities MUST be finite and within [0,1], otherwise `BadValue` is reported. The reserved field MUST be zero. The server selects a physical device with `XAverius.timelineSemaphore = 1` and a compute-capable queue family that can supply the requested `queue_count`; if no such combination is available, it reports `DEVICE_UNAVAILABLE`. The mandatory baseline `timelineSemaphore` feature is enabled automatically; no optional client-requested features or extensions are enabled implicitly.

`CreateDefaultDevice` is a void request. If no suitable device exists, the server reports the XAverius X11 error `DEVICE_UNAVAILABLE`; no normal reply is generated.

## `DestroyDevice`

`DestroyDevice` is a void request with a fixed total length of 12 bytes; the device XID is at offset 8. The XID MUST identify a logical device owned by this client connection. An unknown or non-live XID results in `BadValue`; a live resource of the wrong type or foreign ownership results in `BadMatch`. Cleanup may continue after device loss according to the lifetime rules.

Normative validation precedence is: (1) exact 12-byte request length (`BadLength`); (2) resolve the Device XID (`BadValue` if unknown or non-live); (3) validate that the live resource is a logical Device owned by this client (`BadMatch` for a wrong live type or foreign ownership); (4) perform the atomic logical teardown. There is no Device-availability phase: Device Loss MUST NOT prevent `DestroyDevice` from cleaning up the logical Device. A later phase MUST NOT override an earlier error.

On success, the public device XID and all public XIDs of its resources become invalid immediately.

All still-open host waits (`WaitSemaphores` and `WaitForFence`) associated with this logical device are terminated when this request is processed: `WaitSemaphores` returns the X11 error `DEVICE_DESTROYED`, while `WaitForFence` returns reply status `DEVICE_DESTROYED`. This also applies to infinite waits. Wait conditions whose successful result was established before `DestroyDevice` was processed retain their normal result. Terminating a wait does not require GPU completion.

Any open `WriteBuffer` operation for this Device is also terminalized at the `DestroyDevice` linearization point. If its successful completion was not committed first, it fails with X11 error `DEVICE_DESTROYED` and MUST NOT start a not-yet-started transfer or return success. An already-started backend transfer retains its internal references until it is safe to retire; the destination is not guaranteed unchanged. `DestroyDevice` MUST remain processable while such a write waits for earlier submissions and MUST NOT be held behind the `WriteBuffer` upload barrier.

The successful request has a single server-side linearization point. At that point, cascading public invalidation of the Device and all its children, removal of Device/Queue event selections, and termination of still-open host waits are committed atomically. A wait already terminally established before this point keeps its result; otherwise it terminates as `DEVICE_DESTROYED`. A reply/error already serialized before the point is not rewritten.

Accepted submissions are not cancelled. Their internal terminal states and synchronization objects are finalized exactly once, including when Device loss races with destruction; no successful completion may be fabricated. A callback that races with destruction may perform internal terminalization and cleanup, but MUST NOT enqueue a new event for the destroyed Device after the linearization point. Delayed callbacks MUST use captured internal object identities rather than re-resolving numeric XIDs, so reuse of a child XID cannot redirect old work to a new resource. The captured identity MUST include a non-reusable Device generation as well as the child-resource generation. Reuse of the public Device XID creates a distinct Device generation; it MUST NOT inherit old callback registrations, semaphore-owner links, wait reservations, or device-loss state. Every accepted operation retains references to the exact semaphore objects it reserved until its own callbacks retire them. A late callback from the destroyed Device may release only those captured old-generation references and MUST NOT mutate a semaphore or resource belonging to the replacement Device, even when public XIDs and operation tokens are reused.

Internal Vulkan objects are released only when Vulkan lifetime rules and all outstanding dependencies permit it. If backend access cannot be proven to have ended, the old allocation/reference is retained or quarantined rather than freed or reused.

Successful destruction does not mean that GPU work has completed or that the device has been redirected to another physical device.

## Physical Devices

Physical-device XIDs are assigned by the server.

- Clients MUST NOT destroy physical-device XIDs.
- An existing XID MUST never be assigned to a different physical-device object.
- The identity remains stable if the device is removed or fails; its status changes.
- Visibility of a physical device does not guarantee that a logical device can be created on it.
- Permission to use the device is checked separately.

## Device Ownership

Every logical-device resource belongs to exactly one logical device.

Cross-device use normally results in `BadMatch`, even if both logical devices use the same physical GPU.

A resource request MUST validate:

1. XID existence and type,
2. client ownership,
3. device association,
4. resource state,
5. request-specific Vulkan conditions.

The general XID error mapping is defined in [Errors and error mapping](errors.md). Request-specific rules may extend this mapping only explicitly; they MUST NOT silently override it.
