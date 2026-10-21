# Decision log

This file tracks the status of design decisions. The historical draft's “Anhang B” records decisions previously stated as settled; items below are grouped by current confidence, not by whether they are implemented.

## Settled design direction

- X11 is the transport; Vulkan handles remain server-side.
- Initial implementation target is Xvfb with compute-only workloads.
- Wire fields have explicit widths; native C structures, pointers, `size_t`, and compiler-dependent padding are not transmitted.
- Queue identity is the tuple `(device_xid, queue_family_index, queue_index)`; there are no Queue XIDs.
- Physical-device XIDs are server-owned, persist across client disconnects, and must never be silently rebound to another physical device.
- `CreateDefaultDevice` and explicit physical-device selection followed by `CreateDevice` are both intended.
- Images are outside the initial v0.1 compute path.
- `WriteBuffer` uses independent requests rather than an upload transaction.
- Acceptance of `QueueSubmit` is distinct from GPU completion.
- Asynchronous failures are reported through XAverius events and synchronization state.
- Public resource XIDs become invalid on successful destruction; internal Vulkan objects may remain alive until safe release.
- Descriptor sets may not be updated or freed while pending use is possible.
- Unassigned registry values remain open and must not be guessed.

## Provisional rules requiring review

- Exact per-request error mappings and some pending-destruction restrictions.
- The request-size and segmentation limits discussed after the 2026-10-20 draft; these are not yet reconciled with the historical draft's BIG-REQUESTS text.
- Shader-module upload assembly using one opcode with request flags; exact layout and semantics need a dedicated review.
- Conservative synchronization behavior acceptable for the first implementation.
- Generic `DestroyResource` request and its exact applicability to each resource type.

## Open decisions

See [the open-issues chapter](spec/08-reference-tests-open-issues.md). In particular: opcode and type registries, event-selection layouts, property registry, command-stream failure recovery, Vulkan stage masks, submission IDs, semaphore state rules, and exact Vulkan lifetime validation.
