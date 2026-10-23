# XAverius command-buffer entry registry

Command-buffer entry IDs are unsigned 16-bit XAverius protocol identifiers. They are distinct from X11 request subopcodes and native Vulkan command identifiers. Value 0 is reserved. Assigned values are stable and MUST NOT be renumbered or reused.

| Value | Symbol | v0.1 support | Wire-layout definition |
|---:|---|---|---|
| 1 | CMD_BIND_PIPELINE | Supported | [Command recording](../spec/command-recording.md#cmd_bind_pipeline) |
| 2 | CMD_BIND_DESCRIPTOR_SETS | Supported | [Command recording](../spec/command-recording.md#cmd_bind_descriptor_sets) |
| 3 | CMD_DISPATCH | Supported | [Command recording](../spec/command-recording.md#cmd_dispatch) |
| 4 | CMD_PUSH_CONSTANTS | Supported | [Command recording](../spec/command-recording.md#cmd_push_constants) |
| 5 | CMD_COPY_BUFFER_TO_SWAPCHAIN_IMAGE | Presentation profile only | [Command recording](../spec/command-recording.md#cmd_copy_buffer_to_swapchain_image) |

All other values are unassigned and MUST be rejected with BadValue. Entry 5 is accepted only when the server advertises the presentation-capable profile; a compute-only implementation must reject it with BadValue. Entry lengths are measured in 32-bit words and include the four-byte entry header and any required padding. A request containing any invalid entry is rejected atomically; no entries from that request are appended.

New entry IDs are appended using unused values. An assigned ID's meaning and wire layout MUST NOT change incompatibly.
