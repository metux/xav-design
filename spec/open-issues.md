# Open issues before v0.1 freeze

The following questions remain open; listing them here does not resolve them.

1. Future subopcode allocations as new requests are defined. The current 39 requests have stable assignments in [the central request subopcode registry](../registries/request-subopcodes.md); event-selection requests remain excluded until their wire layouts are specified. Existing assignments must not be renumbered.
2. Event-selection request layouts and final registration of the XGE event base. Event type IDs and event-local values are already defined in [the event registry](../registries/event-types.md).
3. Complete property-name/Atom registry.
4. Complete the numeric and semantic registries for feature IDs and device extensions, including the exact v0.1 supported set. The `CreateDevice` mapping and request-specific error rules are documented in [errors.md](errors.md); a final cross-chapter review remains required before v0.1 freeze.
5. Semantics of `memory_properties_flags`.
6. The `SUBMISSION_COMPLETE` and `SUBMISSION_FAILED` layouts are specified in [events.md](events.md); confirm them in the final ABI review and define behavior when event delivery is impossible.
7. Timeout boundaries and scheduling guarantees.
8. Ownership for future X11 resource-sharing mechanisms.
9. Wire representation of Physical Device UUID and Driver UUID.
10. Final Vulkan stage mapping and valid wait-stage masks.
