# XAverius error registry

Error codes are offsets relative to the X11 extension's `first_error`.

| Offset | Symbol |
|---:|---|
| 0 | `DEVICE_UNAVAILABLE` |
| 1 | `DEVICE_LOST` |
| 2 | `INVALID_SYNCHRONIZATION_STATE` |
| 3 | `EXECUTION_FAILED` |
| 4 | `TRANSFER_FAILED` |
| 5 | `ALLOCATION_FAILED` |
| 6 | `DEPENDENCY_FAILED` |
| 7 | `INTERNAL_SERVER_ERROR` |

The absolute X11 error code is `first_error + offset`. Do not allocate new values ad hoc. Detailed packet and request-specific rules are defined in [the error chapter](../spec/errors.md).
