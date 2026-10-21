# Descriptor type registry

This registry defines XAverius wire values for the `descriptor_type` fields in descriptor-set layouts, descriptor-pool sizes, and descriptor writes. Values are XAverius protocol identifiers; implementations must not forward native Vulkan enum values as XAverius values.

| Value | Symbol | v0.1 status | Meaning |
|---:|---|---|---|
| 0 | `DESCRIPTOR_TYPE_UNSPECIFIED` | Reserved; invalid in a descriptor record | No descriptor type |
| 1 | `STORAGE_BUFFER` | Supported | Vulkan storage-buffer descriptor semantics |

All other values are currently unassigned and unsupported in v0.1. A server MUST reject an unassigned or unsupported descriptor type during request validation; it MUST NOT silently substitute another type. A value can be assigned later only through an explicit registry change, without changing existing assignments.

The v0.1 compute reference workload uses storage buffers for input and output data. Other descriptor types, including uniform buffers and image descriptors, are not part of the current supported set.
