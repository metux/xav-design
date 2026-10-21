# Open issues before v0.1 freeze

The following questions remain open; listing them here does not resolve them.

1. Future subopcode allocations as new requests are defined. The current 40 requests have stable assignments in [the central request subopcode registry](../registries/request-subopcodes.md). Existing assignments must not be renumbered.
2. Final ABI verification of the `SelectEvents` field order, scope-specific masks, and XGE event framing. The XGE extension field uses the dynamically assigned XAverius major opcode; event type IDs are static values in [the event registry](../registries/event-types.md).
3. Complete property-name/Atom registry.
4. Complete the numeric and semantic registries for feature IDs and device extensions, including the exact v0.1 supported set. The `CreateDevice` mapping and request-specific error rules are documented in [errors.md](errors.md); a final cross-chapter review remains required before v0.1 freeze.
5. Semantics of `memory_properties_flags`.
6. Confirm the `SUBMISSION_COMPLETE` and `SUBMISSION_FAILED` layouts and event-delivery behavior in the final ABI review. The contract for closed connections and failed event sends is defined in [events.md](events.md).
7. Timeout boundaries and scheduling guarantees.
8. Ownership for future X11 resource-sharing mechanisms.
9. Wire representation of Physical Device UUID and Driver UUID.
10. Final Vulkan stage mapping and valid wait-stage masks.
