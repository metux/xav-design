# Physical-device property and Atom-name registry

This registry defines the canonical names accepted by `GetPhysicalDeviceProperty`. The names are passed as X11 `ATOM` values, but the numeric Atom IDs are allocated by the X server and are not XAverius registry values. Clients obtain an Atom ID for a registered name through ordinary X11 Atom mechanisms (for example, `InternAtom`); clients MUST NOT assume a fixed numeric Atom value.

Names are exact, case-sensitive ASCII strings. Property names are registered by XAverius; a server MUST NOT reinterpret an unregistered name as a backend-specific property.

## v0.1 properties

| Canonical Atom name | Wire type | Value representation | Availability |
|---|---|---|---|
| `XAverius.deviceUUID` | `BYTE_ARRAY` (5) | Exactly 16 raw bytes as defined by Vulkan; no integer endianness conversion | `NOT_AVAILABLE` if the backend does not provide a valid device UUID |
| `XAverius.driverUUID` | `BYTE_ARRAY` (5) | Exactly 16 raw bytes as defined by Vulkan; no integer endianness conversion | `NOT_AVAILABLE` if the backend does not provide a valid driver UUID |
| `XAverius.compute.maxWorkGroupInvocations` | `CARD32` (1) | One unsigned 32-bit integer | Available when the selected Physical Device exposes the corresponding compute limit |
| `XAverius.compute.maxWorkGroupSize` | `CARD32_ARRAY` (6) | Exactly three unsigned 32-bit integers in X, Y, Z order | Available when the selected Physical Device exposes the corresponding compute limit |

The numeric property-type IDs in the table refer to the normative `GetPhysicalDeviceProperty` type table in [device discovery and logical devices](../spec/devices.md). They are repeated here only to make each property row self-contained; the devices chapter remains the sole authority for the type-ID namespace.

For the UUID properties, the value is the exact 16-byte UUID array returned by the applicable Vulkan physical-device properties. UUIDs are opaque byte arrays: the server MUST preserve byte order exactly and MUST NOT reinterpret the bytes as integers or apply host-endian conversion. The protocol does not transmit a native structure, a NUL terminator, or a textual hexadecimal UUID. If a backend cannot provide a valid value, the server returns `NOT_AVAILABLE`; it MUST NOT fabricate a UUID.

For `SUCCESS`, the reply's `property_type` MUST match the registered type, `value_length` MUST equal the exact size specified above, and padding bytes MUST be zero. If a property is registered but unavailable on a device, return `NOT_AVAILABLE` with `property_type = 0`, `value_length = 0`, no payload, and `reply.length = 0`. If a name is not in this registry, return `NOT_SUPPORTED` with the same empty-value encoding. The server MUST NOT substitute a different property or wire type.

Property names are append-only. New properties require an explicit registry entry, including a stable canonical Atom name, wire type, exact value representation, and unavailable-value behavior. X11 Atom numeric IDs remain server-assigned and MUST NOT be added to this registry.
