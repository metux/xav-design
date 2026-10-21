# Open issues before v0.1 freeze

The following questions remain open; listing them here does not resolve them.

1. Future subopcode allocations as new requests are defined. The current 40 requests have stable assignments in [the central request subopcode registry](../registries/request-subopcodes.md). Existing assignments must not be renumbered.
2. Final ABI verification of the `SelectEvents` field order, scope-specific masks, and XGE event framing. The XGE extension field uses the dynamically assigned XAverius major opcode; event type IDs are static values in [the event registry](../registries/event-types.md).
3. The v0.1 property-name/Atom registry is assigned. Future property additions and final ABI review remain.
4. The v0.1 feature-ID and device-extension registries are defined as empty optional sets. Future assignments remain append-only; cross-chapter validation is still required before v0.1 freeze.
5. Semantics of `memory_properties_flags`.
6. Confirm the `SUBMISSION_COMPLETE` and `SUBMISSION_FAILED` layouts and event-delivery behavior in the final ABI review. The contract for closed connections and failed event sends is defined in [events.md](events.md).
7. Timeout boundaries and scheduling guarantees.
8. Ownership for future X11 resource-sharing mechanisms.
9. Physical Device UUID and Driver UUID are defined as 16-byte `BYTE_ARRAY` properties; final ABI review of the Vulkan UUID byte order remains.
10. Final Vulkan stage mapping and valid wait-stage masks.
