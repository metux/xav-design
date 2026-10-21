# Open issues before v0.1 freeze

The following questions were open in the consolidated draft and remain open. Moving them here does not resolve them.

1. Numeric subopcode allocation for all requests. The inventory is maintained in [the central request subopcode registry](../registries/request-subopcodes.md); numeric assignments remain open.
2. Event-selection request layouts and event registration.
3. Complete property-name/Atom registry.
4. Numeric registries for descriptor types, shader stages, feature IDs, device types, and queue flags.
5. Residual request-specific X11 error mapping, especially the exact standard X11 error code for an invalid/non-live XID by resource class, and unsupported `CreateDevice` feature/extension requests. The selected-request mapping table is in `errors.md`; remaining cases must be finalized before v0.1 freeze.
6. Semantics of `memory_properties_flags`.
7. Final wire layouts for submission completion/failure events and behavior when event delivery is impossible.
8. Timeout boundaries and scheduling guarantees.
9. Ownership for future X11 resource-sharing mechanisms.
10. Wire representation of Physical Device UUID and Driver UUID.
11. Final Vulkan stage mapping and valid wait-stage masks.
