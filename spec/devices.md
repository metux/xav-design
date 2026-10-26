# Device Discovery and Logical Devices

## Device Selection

Two paths are available:

1. `CreateDefaultDevice`: The server selects a suitable physical device and creates a logical device.
2. Explicit selection: call `EnumeratePhysicalDevices`, query properties and `GetPhysicalDeviceQueueFamilyProperties`, then call `CreateDevice`.

Queues are not addressed using queue XIDs. A queue is identified by the tuple

`(device_xid, queue_family_index, queue_index)`

identifiziert.

The queue-family index corresponds to the position in the returned queue-family list. The queue index identifies a queue actually requested from that family.

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

`property_atom` is an ordinary server-assigned X11 Atom ID; XAverius does not assign numeric Atom IDs. The client MUST resolve the canonical name using the standard X11 Atom mechanisms. An Atom ID unknown to the X server results in `BadAtom`. A valid Atom ID whose name is not registered in the XAverius property registry returns `NOT_SUPPORTED`. A registered property whose value is unavailable for the queried physical device returns `NOT_AVAILABLE`. Both status cases use the empty reply encoding described above.

The canonical v0.1 names, types, exact value lengths, and availability rules are defined by the [Physical Device Property and Atom Name Registry](../registries/physical-device-properties.md). The v0.1 entries are `XAverius.deviceUUID`, `XAverius.driverUUID`, `XAverius.compute.maxWorkGroupInvocations`, and `XAverius.compute.maxWorkGroupSize`. UUIDs are 16 raw bytes, not text strings; `maxWorkGroupSize` is an array of exactly three `CARD32` values in X, Y, Z order.

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

The `queue_flags` bits are normatively defined in the [Queue Flag Registry](../registries/queue-flags.md). Servers MUST translate native Vulkan flags into these XAverius wire bits; bits 5–31 are reserved.

## `CreateDevice`

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

Before creation, this connection MUST have successfully negotiated XGE 1.0 or later through `GEQueryVersion`. Otherwise, `BadMatch` is reported and the target XID remains unallocated.

Request:

- Offset 8: `XID device_xid`
- Offset 12: `CARD16 queue_count`
- Offset 14: `CARD16 reserved = 0`
- Offset 16: `FLOAT32 priorities[queue_count]`

Total length: `16 + 4 * queue_count`.

The queue count MUST be at least 1. All priorities MUST be finite and within [0,1], otherwise `BadValue` is reported. The reserved field MUST be zero. The server selects a suitable physical device and a compute-capable queue family. No optional features or extensions are enabled implicitly.

`CreateDefaultDevice` is a void request. If no suitable device exists, the server reports the XAverius X11 error `DEVICE_UNAVAILABLE`; no normal reply is generated.

## `DestroyDevice`

`DestroyDevice` is a void request with a fixed total length of 12 bytes; the device XID is at offset 8. The XID MUST identify a logical device owned by this client connection. An unknown or non-live XID results in `BadValue`; a live resource of the wrong type or foreign ownership results in `BadMatch`. Cleanup may continue after device loss according to the lifetime rules.

On success, the public device XID and all public XIDs of its resources become invalid immediately.

All still-open host waits (`WaitSemaphores` and `WaitForFence`) associated with this logical device are terminated when this request is processed: `WaitSemaphores` returns the X11 error `DEVICE_DESTROYED`, while `WaitForFence` returns reply status `DEVICE_DESTROYED`. This also applies to infinite waits. Wait conditions whose successful result was established before `DestroyDevice` was processed retain their normal result. Terminating a wait does not require GPU completion.

Internal Vulkan objects are released only when Vulkan lifetime rules and all outstanding dependencies permit it.

Successful destruction does not mean that GPU work has completed or that the device has been redirected to another physical device.

## Physische Devices

Physical-device XIDs are assigned by the server.

- Clients MUST NOT destroy physical-device XIDs.
- An existing XID MUST never be assigned to a different physical-device object.
- The identity remains stable if the device is removed or fails; its status changes.
- Visibility of a physical device does not guarantee that a logical device can be created on it.
- Permission to use the device is checked separately.

## Device-Ownership

Every logical-device resource belongs to exactly one logical device.

Cross-device use normally results in `BadMatch`, even if both logical devices use the same physical GPU.

A resource request MUST validate:

1. XID existence and type,
2. client ownership,
3. device association,
4. resource state,
5. request-specific Vulkan conditions.

The general XID error mapping is defined in [Errors and error mapping](errors.md). Request-specific rules may extend this mapping only explicitly; they MUST NOT silently override it.
