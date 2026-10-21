# Open issues before v0.1 freeze

The following questions were open in the consolidated draft and remain open. Moving them here does not resolve them.

1. Central numeric subopcode registry for all requests.
2. Final request layouts for Shader Modules, Command Pools, generic destruction, and Descriptor Set Layouts.
3. Event-selection request layouts and event registration.
4. Complete property-name/Atom registry.
5. Numeric registries for descriptor types, shader stages, feature IDs, device types, and queue flags.
6. Complete request-specific X11 error mapping.
7. Recovery behavior if a later CommandBufferData chunk fails.
8. Final Command Buffer state after asynchronous error or Device Loss.
9. Exact pending-destruction rules for Pipeline, Pipeline Layout, Fence, and Semaphore.
10. Semantics of `memory_properties_flags`.
11. Error representation for unsupported device features and extensions in `CreateDevice`.
12. Exact pending signal/wait rules for binary semaphores.
13. Assignment, uniqueness, and wrap behavior of `submission_id`.
14. Exact completion/failure event delivery rules.
15. Timeout boundaries and scheduling guarantees.
16. Device destruction behavior when asynchronous teardown fails.
17. Ownership for future X11 resource-sharing mechanisms.
18. Wire representation of Physical Device UUID and Driver UUID.
19. Queue-crossing scope of the `WriteBuffer` visibility guarantee.
20. Final Vulkan stage mapping and valid wait-stage masks.
21. Complete normative definition of the central resource state machine.
22. Exact Vulkan lifetime validation for all resource combinations before the specification is considered stable.
23. Resolve the `BIG-REQUESTS` framing conflict: its extended-length field overlaps the XAverius common header at offset 4. Until resolved, `BIG-REQUESTS` is not supported in v0.1.
24. Define how clients learn and correlate `submission_id`; `QueueSubmit` currently is a Void request while completion/failure events carry a server-generated ID.
25. Define the exact success/reply contract for `WriteBuffer` so its transfer-completion and input-buffer-reuse guarantees are observable and protocol-valid.
26. Specify host-side `SignalSemaphore` completion/error behavior and its ordering relative to subsequent requests.
27. Confirm that `GetPhysicalDeviceMemoryProperties` is keyed by a Physical-Device XID, not a logical Device XID.
