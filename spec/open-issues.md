# Open issues before v0.1 freeze

The following questions were open in the consolidated draft and remain open. Moving them here does not resolve them.

1. Central numeric subopcode registry for all requests.
2. Final request layouts for Shader Modules, Command Pools, generic destruction, and Descriptor Set Layouts.
3. Event-selection request layouts and event registration.
4. Complete property-name/Atom registry.
5. Numeric registries for descriptor types, shader stages, feature IDs, device types, and queue flags.
6. Complete request-specific X11 error mapping, including invalid-resource and wrong-type cases.
7. Recovery behavior if a later CommandBufferData chunk fails.
8. Semantics of `memory_properties_flags`.
9. Error representation for unsupported device features and extensions in `CreateDevice`.
10. Final wire layouts for submission completion/failure events and behavior when event delivery is impossible.
11. Timeout boundaries and scheduling guarantees.
12. Ownership for future X11 resource-sharing mechanisms.
13. Wire representation of Physical Device UUID and Driver UUID.
14. Queue-crossing scope of the `WriteBuffer` visibility guarantee.
15. Final Vulkan stage mapping and valid wait-stage masks.
