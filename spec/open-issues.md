# Open issues before v0.1 freeze

The following questions were open in the consolidated draft and remain open. Moving them here does not resolve them.

1. Central numeric subopcode registry for all requests.
2. Final request layouts for Shader Modules, Command Pools, generic destruction, and Descriptor Set Layouts.
3. Event-selection request layouts and event registration.
4. Complete property-name/Atom registry.
5. Numeric registries for descriptor types, shader stages, feature IDs, device types, and queue flags.
6. Complete request-specific X11 error mapping, including invalid-resource and wrong-type cases.
7. Recovery behavior if a later CommandBufferData chunk fails.
8. Final Command Buffer state after asynchronous error or Device Loss.
9. Exact pending-destruction rules for Pipeline, Pipeline Layout, Fence, and Semaphore, including behavior after Device Loss.
10. Semantics of `memory_properties_flags`.
11. Error representation for unsupported device features and extensions in `CreateDevice`.
12. Exact pending signal/wait rules for binary semaphores.
14. Exact completion/failure event delivery rules.
15. Timeout boundaries and scheduling guarantees.
16. Device destruction behavior when asynchronous teardown fails.
17. Ownership for future X11 resource-sharing mechanisms.
18. Wire representation of Physical Device UUID and Driver UUID.
19. Queue-crossing scope of the `WriteBuffer` visibility guarantee.
20. Final Vulkan stage mapping and valid wait-stage masks.
21. Complete normative definition of the central resource state machine.
22. Audit remaining Vulkan lifetime rules, especially destruction of pending fences/semaphores, Device Loss, DescriptorPool cascade destruction, and all indirect references not covered by the normative Command-Buffer invalidation rule.
23. Define the complete request-specific error mapping, including how core X11 errors and XAverius errors are selected for every invalid-resource and wrong-type case.
