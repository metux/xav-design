# Shader-stage registry

The registry defines the XAverius shader-stage bit mask used by descriptor layouts, pipeline layouts, and push constants. It is a wire protocol namespace and is not a raw Vulkan flag field.

| Bit | Mask | Symbol | v0.1 status |
|---:|---:|---|---|
| 0 | `0x00000001` | `COMPUTE` | Supported |

Bits 1–31 are reserved and unsupported in v0.1. A stage mask must contain at least one supported stage and MUST NOT contain reserved, unknown, or unsupported bits. For v0.1 compute commands, `CMD_PUSH_CONSTANTS.stage_flags` must equal `COMPUTE` exactly.

The numeric bit assignment is shared wherever a field is named `stage_flags`; individual chapters must not define local stage values.
