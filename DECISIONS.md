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
- A successful `WriteBuffer` reply is an ordering boundary only within its logical device: all previously accepted submissions on that device reach a terminal outcome before the transfer modifies the destination, and all subsequently accepted submissions on any queue of that device observe the written bytes. It does not synchronize other logical devices on the same physical GPU. No client semaphore/barrier is required solely to make that upload visible. While waiting for prior work, the server must permit a later `SignalSemaphore` on the same connection to unblock that work, but must defer later `QueueSubmit` acceptance until the upload completes. The server may implement this conservatively with full device synchronization; if the device is lost or the transfer fails, no successful reply is sent.
- Acceptance of `QueueSubmit` is distinct from GPU completion.
- `QueueSubmit` carries a client-generated 64-bit `submission_token`; it must be nonzero and unique for the lifetime of that X11 client connection, but has no ordering semantics. The server echoes it in submission-related events.
- Asynchronous failures are reported through XAverius events and synchronization state.
- Every accepted submission has exactly one terminal outcome event (`SUBMISSION_COMPLETE` or `SUBMISSION_FAILED`) while the client connection can receive events; diagnostic `ASYNC_ERROR` events do not replace that terminal outcome.
- Device Loss fails every accepted nonterminal submission with `DEVICE_LOST`; fences become `FAILED`, and affected command buffers become `INVALID` after leaving the pending phase. No successful completion is synthesized.
- Public resource XIDs become invalid on successful destruction; internal Vulkan objects may remain alive until safe release.
- Resource lifetime uses a normative public/internal state machine: `LIVE` + `ACTIVE` on creation; rejected destroys leave state unchanged; successful destruction invalidates the XID atomically and transitions internal state to `DESTROY_PENDING` or `RELEASED`.
- Destroying a resource referenced by a `RECORDING` command buffer is rejected. Destroying one referenced by a non-pending `EXECUTABLE` command buffer invalidates that command buffer. Pending-use destruction is rejected according to the resource-specific lifetime rules.
- `DestroyCommandPool` and `DestroyDescriptorPool` are atomic cascades and are rejected when a child is pending; DescriptorPool destruction is also rejected when a child set is referenced by a `RECORDING` command buffer.
- `FreeMemory` is rejected while any Buffer remains bound to the allocation; v0.1 has no unbind/rebind operation.
- Destroying a Buffer invalidates non-pending executable command buffers that reference it; descriptor slots retaining that Buffer remain non-submittable until updated or freed, and retain the internal Buffer object until then.
- Device teardown invalidates public XIDs immediately but preserves internal references until backend access ends. Device Loss fails nonterminal submissions; it never fabricates successful completion.
- If backend quiescence cannot be proven after Device Loss/teardown failure, the device is isolated and internal resources are quarantined rather than freed or reused; quarantine lasts until backend quiescence is proven or the server process exits.
- The server tracks direct and indirect resource references recorded by command buffers. Destroying a referenced resource is rejected while a command buffer is recording; executable command buffers that reference a destroyed resource become invalid and must be recorded again.
- Descriptor sets may not be updated or freed while pending use is possible.
- Unassigned registry values must not be guessed.

## Settled wire-protocol constraints

- `BIG-REQUESTS` is not supported in v0.1 because its extended-length field conflicts with the XAverius common header at offset 4. The ordinary X11 request-size limit applies; larger payloads must use request-specific chunking where defined.
- For XAverius v0.1, the X11 request-header `data` byte is always zero; the subopcode is at offset 4 and is copied zero-extended to the standard X11 error packet's `minorCode`.

## Provisional rules requiring review

- Shader-module upload assembly using one opcode and request flags; exact layout and semantics need review.
- Complete request-specific error mappings and exact applicability/layout of generic `DestroyResource`.
- Further optimization of the now-settled conservative `WriteBuffer` ordering contract, provided the normative observable ordering remains unchanged.

## Newly settled wire decisions — 2026-10-21

- `ShaderModuleData` uses one opcode and request flags `CREATE`, `FINAL`, and `ABORT`. Chunks concatenate their declared SPIR-V bytes; per-request zero padding is excluded. Any malformed chunk discards the entire in-progress shader assembly; successful FINAL atomically creates the module.
- `CreateCommandPool` and `DestroyCommandPool` layouts are fixed. `CommandBufferData` validates each chunk atomically; a failed chunk does not append partial entries, earlier accepted chunks remain, and ABORT returns a non-pending recording buffer to `INITIAL`.
- `CreateCommandPool` flags are fixed for v0.1: bit 0 `TRANSIENT` (optimization hint only), bit 1 `RESET_COMMAND_BUFFER` (permits explicit `ResetCommandBuffer`), bits 2–31 zero. Unknown flags are rejected; the server never adds flags implicitly. `ResetCommandBuffer` is a 16-byte Void request and requires the pool flag and a non-pending buffer; success resets `INITIAL`, `RECORDING`, `EXECUTABLE`, or `INVALID` to `INITIAL` and drops recorded entries/references. `CommandBufferData` ABORT remains a distinct recording-upload recovery operation and does not require the pool reset flag.
- `CreateDescriptorSetLayout` has a 24-byte fixed header followed by 16-byte binding records; total length is `24 + 16 * binding_count`. Its `flags` field must be zero in v0.1. Empty layouts are allowed; binding numbers must be unique, descriptor counts positive, and descriptor/stage values must be registered and supported. Creation is atomic, and registry numbers are not assigned in this chapter.
- `DestroyResource` is a 12-byte Void request carrying only `resource_xid`; Device and owner are inferred from the resource. It applies only to Buffer, Shader Module, Descriptor Set Layout, Pipeline Layout and Pipeline. Fence and Semaphore are excluded along with Device, Physical Device, CommandPool, DescriptorPool, CommandBuffer, DescriptorSet and Memory; each uses its dedicated destruction/free path. Generic destruction dispatches to the resource-specific lifetime checks and is atomic on rejection.

## Open decisions

See [open issues](spec/open-issues.md). Topics include opcode/type registries, event-selection layouts, property registry, command-stream failure recovery, Vulkan stage masks, and backend teardown failure handling.
