# Open issues before v0.1 freeze

The following questions were open in the consolidated draft and remain open. Moving them here does not resolve them.

1. Central numeric subopcode registry for all requests.
2. Final request layout and applicability rules for generic destruction.
3. Event-selection request layouts and event registration.
4. Complete property-name/Atom registry.
5. Numeric registries for descriptor types, shader stages, feature IDs, device types, and queue flags.
6. Complete request-specific X11 error mapping, including invalid-resource and wrong-type cases.
7. Semantics of `memory_properties_flags`.
8. Error representation for unsupported device features and extensions in `CreateDevice`.
9. Final wire layouts for submission completion/failure events and behavior when event delivery is impossible.
10. Timeout boundaries and scheduling guarantees.
11. Ownership for future X11 resource-sharing mechanisms.
12. Wire representation of Physical Device UUID and Driver UUID.
13. Final Vulkan stage mapping and valid wait-stage masks.
