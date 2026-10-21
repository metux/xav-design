# Decision log

This file tracks the status and rationale of design decisions. The historical draft's decision appendix records previously stated choices; it does not imply that every technical detail has been fully validated.

## Settled design direction

- X11 is the transport; Vulkan handles remain server-side.
- Initial implementation target is Xvfb with compute-only workloads.
- Wire fields have explicit widths; native C structures, pointers, `size_t`, and compiler-dependent padding are not transmitted.
- Queue identity is `(device_xid, queue_family_index, queue_index)`; there are no Queue XIDs.
- Physical-device XIDs are server-owned, survive client disconnects, and must never be silently rebound to a different physical device.
- Both default device selection and explicit physical-device selection followed by `CreateDevice` are intended.
- Images are outside the initial v0.1 compute path.
- `WriteBuffer` uses independent requests rather than an upload transaction.
- Acceptance of `QueueSubmit` is distinct from GPU completion.
- `QueueSubmit` carries a client-generated 64-bit `submission_token`; it must be nonzero and unique for the lifetime of that X11 client connection, but has no ordering semantics. The server echoes it in submission-related events.
- Asynchronous failures are reported through XAverius events and synchronization state.
- Public resource XIDs become invalid on successful destruction; internal Vulkan objects may remain alive until safe release.
- The server tracks direct and indirect resource references recorded by command buffers. Destroying a referenced resource is rejected while a command buffer is recording; executable command buffers that reference a destroyed resource become invalid and must be recorded again.
- Descriptor sets may not be updated or freed while pending use is possible.
- Unassigned registry values must not be guessed.

## Settled wire-protocol constraints

- `BIG-REQUESTS` is not supported in v0.1 because its extended-length field conflicts with the XAverius common header at offset 4. The ordinary X11 request-size limit applies; larger payloads must use request-specific chunking where defined.
- For XAverius v0.1, the X11 request-header `data` byte is always zero; the subopcode is at offset 4 and is copied zero-extended to the standard X11 error packet's `minorCode`.

## Provisional rules requiring review

- Shader-module upload assembly using one opcode and request flags; exact layout and semantics need review.
- Exact request-specific error mappings and pending-destruction restrictions.
- Generic `DestroyResource` applicability and exact behavior.
- Conservative synchronization rules and queue-crossing visibility guarantees.

## Open decisions

See [open issues](spec/open-issues.md). Topics include opcode/type registries, event-selection layouts, property registry, command-stream failure recovery, Vulkan stage masks, submission-token correlation, semaphore state rules, and Vulkan lifetime validation.
