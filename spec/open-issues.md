# Open issues before v0.1 freeze

The following questions were open in the consolidated draft and remain open. Moving them here does not resolve them.

1. Central numeric subopcode registry for all requests.
2. Final request layouts for Shader Modules, Command Pools, generic destruction, and Descriptor Set Layouts.
3. Event-selection request layouts and event registration.
4. Complete property-name/Atom registry.
5. Numeric registries for descriptor types, shader stages, feature IDs, device types, and queue flags.
6. Complete request-specific X11 error mapping, including invalid-resource and wrong-type cases.
7. Recovery behavior if a later CommandBufferData chunk fails.
8. Exact pending-destruction rules for Pipeline, Pipeline Layout, Fence, and Semaphore, including behavior after Device Loss.
9. Semantics of `memory_properties_flags`.
10. Error representation for unsupported device features and extensions in `CreateDevice`.
11. Exact pending signal/wait rules for binary semaphores.
12. Final wire layouts for submission completion/failure events and behavior when event delivery is impossible.
13. Timeout boundaries and scheduling guarantees.
14. Device destruction behavior when asynchronous teardown fails.
15. Ownership for future X11 resource-sharing mechanisms.
16. Wire representation of Physical Device UUID and Driver UUID.
17. Queue-crossing scope of the `WriteBuffer` visibility guarantee.
18. Final Vulkan stage mapping and valid wait-stage masks.
19. Complete normative definition of the central resource state machine.
20. Audit remaining Vulkan lifetime rules, especially pending Fence/Semaphore destruction, DescriptorPool cascade destruction, and indirect references not covered by the normative Command-Buffer invalidation rule.
