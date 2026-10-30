# Resource lifetime cross-chapter audit — 2026-10-30

## Scope and evidence

Reviewed the current branch at `10d13670ac01085f083e2badb9d324975937b923` against:

- `spec/resource-lifetime.md`
- `spec/devices.md`, `spec/memory-buffers.md`, `spec/shaders-pipelines.md`, and `spec/command-recording.md`
- `spec/queue-submission.md`, `spec/synchronization.md`, `spec/events.md`, and `spec/presentation.md`
- `spec/errors.md`, `spec/request-audit.md`, and `spec/conformance.md`
- Resource, descriptor, memory, command-pool, callback-identity, Device-loss, and presentation lifecycle reference-model tests.

This is a semantic cross-document review, not a claim of runtime Vulkan or X11 validation.

## Resource-class findings

| Resource class | Cross-chapter result |
|---|---|
| Logical Device and owned children | Cascading public invalidation is separated from internal quiescence; immutable identities prevent XID reuse from retargeting callbacks or cleanup. |
| Physical Device | Server-owned identity is not treated as a client-destroyable Device child; property snapshots remain queryable under their stated lifetime rules. |
| Buffer and Memory | Buffer binding, descriptor-slot references, recorded references, accepted submissions, backend accesses, and allocation release are distinct lifetime edges. `FreeMemory` remains blocked while an internally live Buffer is bound or an access remains unsafe. |
| Shader Module, Pipeline, PipelineLayout | Shader modules may be released after successful pipeline creation; live Pipelines retain the exact internal PipelineLayout identity. Public PipelineLayout invalidation does not destroy that dependency prematurely. |
| DescriptorSetLayout and DescriptorSet | Allocated sets retain the immutable layout definition/backend identity. Descriptor-slot Buffer references survive public Buffer invalidation until slots are replaced or sets are freed. |
| CommandPool and CommandBuffer | Pool destruction is atomic against pending children; recorded-resource edges and submission/backend holds are independently retired exactly once. Recording references block ordinary resource destruction; executable references are invalidated on successful destruction. |
| DescriptorPool and DescriptorSet | Pool and selected-set destruction preserve atomicity, reject pending/recording blockers, invalidate affected executable command buffers, and release slot references through the owning operation. |
| Fence and Semaphore | Accepted queue operations and open host-wait registrations hold exact internal identities. A terminal wait whose reply is not yet delivered no longer blocks destruction; disconnect cancels only the wait registration, not accepted GPU work. |
| Surface and Swapchain | Connection/window identity, Surface-to-Swapchain dependencies, pending acquires, accepted presentation work, image release/invalidation, and event suppression are specified separately. Device/connection teardown does not imply backend quiescence. |

## Cross-document consistency checks

- The generic `DestroyResource` allowlist and exclusions agree with the dedicated destroy/free requests and error mapping.
- `DestroyDevice` and disconnect invalidate public names without freeing objects still reachable through recorded commands, descriptor slots, submissions, host operations, or backend access.
- Device loss terminalizes accepted work as failure and permits logical cleanup where the request contract allows it; it does not by itself prove backend quiescence or invalidate all public XIDs.
- Rejected ordinary destruction leaves public state, ownership, and dependent command-buffer state unchanged.
- Descriptor updates replace derived Buffer references atomically; stale references cannot make a destroyed/reused XID valid again.
- Wait terminalization, event suppression, and cleanup are consistent with the asynchronous lifecycle and presentation chapters.
- The conformance inventory contains targeted cases for resource destruction, descriptor/pool atomicity, stale Buffer slots, backing-memory release, callback identity, Device loss, and presentation teardown.

## Outcome

No new normative contradiction or missing v0.1 resource-lifetime decision was found in this pass. No wire assignment or protocol behavior was changed.

The following remain implementation acceptance work, not specification gaps: live X11/XGE interoperability; real Vulkan compute execution and memory visibility; runtime teardown/Device-loss races; and presentation-backend validation if that profile is implemented.

The normative chapter still contains legacy German passages and a few mixed-language lines. Per the current task priority, these are editorial cleanup only and were not allowed to displace the semantic audit.

## CI evidence

The audited branch tip was checked by [CI run 41083773986](https://github.com/metux/xav-design/actions/runs/41083773986). The wire-layout job completed all required steps successfully: 4,693 wire-layout checks, 72 Timeline regression tests, 658 Python tests, and the required-check presence audit. These results establish static/documentation and reference-model test success only; they do not establish live server/backend behavior.
