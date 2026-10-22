# Device reason-code registry

This append-only registry is shared by the `reason_code` field of `DEVICE_LOST` and `DEVICE_STATUS_CHANGED`. Sharing the namespace lets clients interpret the same cause consistently without making the two events' lifecycle semantics interchangeable.

| Value | Symbol |
|---:|---|
| 0 | `REASON_UNSPECIFIED` |
| 1 | `HOTPLUG_REMOVAL` |
| 2 | `DRIVER_FAILURE` |
| 3 | `VULKAN_DEVICE_LOST` |
| 4 | `SERVER_POLICY` |
| 5 | `SERVER_SHUTDOWN` |

Values are stable and MUST NOT be renumbered or reused. New values are appended; unassigned values are reserved.

The reason is informational. It describes the reported cause but does not change the lifecycle rules for either event. A server reports the most specific applicable reason it can establish; if it cannot establish one, it uses `REASON_UNSPECIFIED`. A reason that does not meaningfully apply to a particular event MUST NOT be used merely because it exists in this shared registry.
