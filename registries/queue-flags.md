# Queue-flag registry

This registry defines the `QUEUEFAMILYINFO.queue_flags` bits returned by `GetPhysicalDeviceQueueFamilyProperties`. The values are XAverius wire bits, not a native Vulkan bitmask.

| Bit | Mask | Symbol | Meaning |
|---:|---:|---|---|
| 0 | `0x00000001` | `GRAPHICS` | Queue family supports graphics commands |
| 1 | `0x00000002` | `COMPUTE` | Queue family supports compute commands |
| 2 | `0x00000004` | `TRANSFER` | Queue family supports transfer commands |
| 3 | `0x00000008` | `SPARSE_BINDING` | Queue family supports sparse binding |
| 4 | `0x00000010` | `PROTECTED` | Queue family supports protected operations |

Bits 5–31 are reserved and MUST be zero. Servers translate native Vulkan queue flags to these wire bits; clients MUST NOT assume that a native Vulkan bitmask is wire-compatible. Vulkan graphics- and compute-capable queue families also support transfer commands by Vulkan's implicit transfer capability, even when the native `VK_QUEUE_TRANSFER_BIT` is absent. Therefore effective transfer-command support is present when any of `GRAPHICS`, `COMPUTE`, or `TRANSFER` is set; the wire `TRANSFER` bit continues to represent the native transfer flag and is not a requirement for graphics/compute families.
