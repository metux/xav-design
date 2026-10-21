# Open issues before v0.1 freeze

The following questions remain open; listing them here does not resolve them.

1. Future subopcode allocations as new requests are defined. The current 40 requests have stable assignments in [the central request subopcode registry](../registries/request-subopcodes.md). Existing assignments must not be renumbered.
2. Final ABI verification of the `SelectEvents` field order, scope-specific masks, and XGE event framing. The XGE extension field uses the dynamically assigned XAverius major opcode; event type IDs are static values in [the event registry](../registries/event-types.md).
3. Future property additions must be registered append-only; the four v0.1 properties and their wire representations are defined.
4. Future feature IDs and device extensions must be registered append-only; the v0.1 optional sets are intentionally empty.
5. Semantics of `memory_properties_flags`.
6. Confirm the `SUBMISSION_COMPLETE` and `SUBMISSION_FAILED` layouts and event-delivery behavior in the final ABI review. The contract for closed connections and failed event sends is defined in [events.md](events.md).
7. Timeout boundaries and scheduling guarantees.
8. Ownership for future X11 resource-sharing mechanisms.
9. Physical Device UUID and Driver UUID are defined as opaque 16-byte `BYTE_ARRAY` properties; the server preserves the Vulkan-returned bytes exactly.

