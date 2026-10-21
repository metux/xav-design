# Physical-device type registry

This registry defines the `PHYSICALDEVICEINFO.device_type` values. The meanings correspond to the Vulkan physical-device type categories, but the wire values are explicitly defined here rather than passed through as a native implementation enum.

| Value | Symbol | Meaning |
|---:|---|---|
| 0 | `OTHER` | Device does not fit another category or its category is unknown |
| 1 | `INTEGRATED_GPU` | Integrated GPU |
| 2 | `DISCRETE_GPU` | Discrete GPU |
| 3 | `VIRTUAL_GPU` | Virtual GPU |
| 4 | `CPU` | CPU-based Vulkan implementation |

Values 5 and above are unassigned in v0.1. A server MUST map any implementation-specific or future native device category that has no XAverius value to `OTHER`; it MUST NOT emit an unassigned wire value. New categories require an explicit registry extension and do not change the meanings above.
