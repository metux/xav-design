# Resource lifetime and ownership

## Client Resources

Client-created XAverius resources use valid XIDs allocatable by the client.

An invalid or already-occupied create XID results in `BadIDChoice`, unless the request defines a more specific X11 rule.

The server MUST maintain an internal identity for each resource that is distinct from its public XID. Reuse of the same XID MUST never redirect in-flight work to a new resource.

A successfully destroyed public resource is no longer addressable by new requests.

# Resource Lifetime and Destruction

## State Model

Each object has at least two distinct lifetime views:

**Public State**

- `LIVE`
- `INVALID`

**Internal State**

- `ACTIVE`
- `DESTROY_PENDING`
- `RELEASED`

The implementation SHOULD also track internal resource identity, client and device ownership, dependent objects, and outstanding submission references.

The public XID becomes invalid immediately when destruction succeeds. Actual Vulkan object destruction may be deferred.

### `DestroyDevice` cascade linearization

A successful `DestroyDevice` has one server-side linearization point. At that point, as one indivisible public-state transition, the server MUST mark the Device and every public resource owned by that exact internal Device identity invalid, remove its Device/Queue event selections, and terminalize every still-open host wait that has not already reached a terminal result. A wait whose success, timeout, or Device-loss result was established first keeps that result; otherwise the processed destroy yields `DEVICE_DESTROYED`. A wait reply or error already serialized before this point remains unchanged.

Accepted submissions are not cancelled by public invalidation. Each still-nonterminal accepted submission MUST still acquire exactly one internal terminal outcome; a Device-loss outcome MUST NOT be replaced with success. Completion callbacks racing with the cascade MUST serialize against the same lifecycle state: callbacks may finish internal state and release references exactly once, but after the destroy linearization point they MUST NOT enqueue or deliver a new event for the destroyed Device. Events already queued in the X11 output stream before that point remain valid.

Every callback and deferred cleanup operation MUST be keyed by the immutable internal Device/resource/submission identity, never by a numeric XID lookup performed at callback time. If an XID is reused after cascading invalidation, a late callback MUST NOT mutate the new resource, satisfy a new wait, release its allocation, or deliver an event naming it. Internal references and backend allocations for the old identity remain retained or quarantined until backend access is known to be impossible; public invalidation and event suppression MUST NOT be treated as proof of quiescence.

## Normative State Transitions

The following transitions are normative:

- Successful creation: public view is `LIVE`; internal state is `ACTIVE`.
- Rejected destroy request: no change to public state, internal state, dependent command-buffer states, or ownership.
- Successful ordinary destruction: the public view becomes `INVALID` in the same request. If no internal references or backend accesses remain, the object may transition directly to `RELEASED`; otherwise it transitions to `DESTROY_PENDING`.
- `DESTROY_PENDING` → `RELEASED`: only after all internal references are released, no backend access remains possible, and backend destruction has completed.
- Device-wide cascading invalidation on successful `DestroyDevice` or client disconnect: all associated public XIDs become `INVALID`. Objects with remaining internal references or backend accesses remain `DESTROY_PENDING`; other objects may become `RELEASED`. Device loss alone does not invalidate public XIDs: the lost logical device and its resources remain addressable until explicitly destroyed, where the relevant request contracts permit status queries or logical cleanup. In particular, `GetFenceStatus` and `DestroyDevice` remain usable after device loss. For accepted presentations, internal terminal states and safe backend cleanup MUST complete even when lifecycle rules suppress delivery of presentation events. An open `AcquireNextImage` request is terminalized with `DEVICE_DESTROYED` by `DestroyDevice`, unless its result was already terminally serialized; on disconnect, the registration is removed without a reply.

An object in `DESTROY_PENDING` cannot be addressed or destroyed again using its old XID. A reused XID identifies a new internal resource identity and MUST NOT inherit references to the old object. `RELEASED` is terminal.

Internal references are tracked separately for recorded command buffers, accepted submissions, buffer handles in descriptor slots, parent-child ownership, and active server operations. Removing a public XID does not automatically remove references held by an accepted submission. On successful ordinary destruction, all required command-buffer invalidations and internal reference updates MUST occur atomically with public invalidation.

## Ownership Hierarchy

Explicit parent-child relationships:

- X11 connection → surface (connection-bound surface; not a device child)
- Surface → exact internal identity of the referenced X11 window (the window is not owned; the reference MUST NOT be replaced by resolving the numeric XID again)
- Device → all public resources owned by the device, including swapchains
- Surface → dependent swapchains (reference relationship; surface destruction is rejected while swapchains remain live)
- CommandPool → associated command buffers
- DescriptorPool → associated descriptor sets

Other relationships are dependencies, not automatic ownership relationships:

- Buffer ↔ Memory
- Pipeline ↔ Pipeline Layout
- Pipeline ↔ Shader Module during creation
- Pipeline Layout ↔ Descriptor Set Layout during creation
- Command buffer ↔ resources used by recorded commands

The implementation MUST NOT assume that every object whose handle was used to create another object must remain alive indefinitely. The applicable Vulkan lifetime rules determine the required lifetime.

## Destruction Matrix

| Resource | Public Destruction | Rule for Pending Use |
|---|---|---|
| Device | Invalidates device and children immediately | Internal cleanup is deferred |
| CommandPool | Atomically invalidates the pool and child command buffers | Reject while any child is pending |
| CommandBuffer | XID becomes invalid | Reject while pending |
| DescriptorPool | Atomically invalidates the pool and all child sets | Reject if any child set is pending or referenced by a `RECORDING` command buffer |
| DescriptorSet | XID becomes invalid | Reject while pending or referenced by a `RECORDING` command buffer; on success, referencing non-pending `EXECUTABLE` command buffers become `INVALID` |
| Buffer | XID becomes invalid | Reject while referenced by a `RECORDING` command buffer or used directly/indirectly by accepted work; on successful destruction, non-pending `EXECUTABLE` command buffers with this reference become `INVALID`. Defer internal release while server operations or descriptor slots still reference the object |
| Memory | Invalidated only after successful validation | Reject `FreeMemory` while any buffer remains bound to it or accepted work uses the allocation |
| Pipeline | XID becomes invalid | Reject while referenced by a `RECORDING` command buffer or used by accepted work; on success, referencing non-pending `EXECUTABLE` command buffers become `INVALID` |
| PipelineLayout | XID becomes invalid | Reject while referenced by a `RECORDING` command buffer or used by accepted work; on success, referencing non-pending `EXECUTABLE` command buffers become `INVALID` |
| ShaderModule | May be destroyed independently after successful pipeline creation | Vulkan lifetime rules remain authoritative |
| DescriptorSetLayout | May be destroyed independently after successful pipeline-layout creation | Vulkan lifetime rules remain authoritative |
| Fence | XID becomes invalid | Reject while the fence belongs to a non-terminal submission or an open `WaitForFence` registration references that exact internal fence identity; a wait already determined to be terminal does not block destruction merely because its reply is still pending |
| Semaphore | XID becomes invalid | Reject while an accepted queue wait/signal, an open `WaitSemaphores` registration for that exact internal semaphore identity, or another active server-side host operation uses the semaphore; a wait already determined to be terminal does not block destruction merely because its reply is still pending |
| Physical Device | Cannot be destroyed by a client | Server-owned; XID is never reassigned |
| Surface (presentation profile) | XID becomes invalid after successful `DestroySurface` or connection teardown; the internal window identity/reference is released only after surface, swapchain, and backend references have safely ended | Destruction is atomically rejected while a live swapchain references the surface; window destruction marks the still-addressable surface as `SURFACE_LOST` and causes neither implicit surface destruction nor rebinding when the XID is reused |
| Swapchain (presentation profile) | XID becomes invalid; image/backend storage may be released later | Destruction is rejected while recording command buffers, pending acquires, accepted queue/presentation work, or possible backend accesses reference the images; an acquired-but-idle image alone does not block destruction. Device destruction invalidates the XID and defers internal release until quiescence |

These rules are XAverius API decisions; they do not claim that Vulkan defines identical lifetime restrictions for all resource types.

## Recorded References and Command Buffer Invalidation

For each command buffer, the server tracks resources referenced directly or indirectly by its recorded commands. These include pipelines, pipeline layouts, descriptor sets, buffers, and buffers referenced through descriptor sets. These dependencies remain while the command buffer is recording or executable. A submission takes its own internal references, which remain until the submission reaches a terminal outcome and all backend accesses have ended. Invalidating an XID MUST never redirect a backend handle to another object.

- If a resource referenced by a `RECORDING` command buffer is destroyed, destruction is rejected with `INVALID_SYNCHRONIZATION_STATE`. The client must end recording or discard the command buffer before destroying the resource.
- If a resource referenced by an `EXECUTABLE` command buffer is destroyed, those command buffers transition to `INVALID` before the destroy request completes successfully. They MUST NOT be submitted afterward; recording them again is required.
- If the resource is still in use by an accepted submission, the resource-specific pending-use rule in the destruction matrix applies. A destroy request rejected due to pending use leaves the XID and command-buffer states unchanged.
- A destroy request is atomic: if the resource-specific rule rejects destruction, neither the public XID nor command-buffer states are changed.

This also applies to indirect dependencies through descriptor set → buffer or buffer → bound memory. The server MUST NOT treat an executable command buffer as valid if one of its recorded resource dependencies has been publicly destroyed.

## `DestroyResource`

`DestroyResource` is a generic void request with a fixed total length of 12 bytes:

| Offset | Type | Field |
|---:|---|---|
| 8 | XID | `resource_xid` |

The logical device and owner are determined from the addressed resource. The request may address only a live resource owned by the calling client. There is no additional `device_xid` field, so the request cannot reinterpret a resource belonging to another client or device.

In v0.1, `DestroyResource` is defined only for buffers, shader modules, descriptor set layouts, pipeline layouts, and pipelines.

The request is not valid for physical devices, logical devices, command pools, descriptor pools, command buffers, descriptor sets, memory, fences, or semaphores. These types have their own lifetime or cascading rules and must be handled through `DestroyDevice`, `DestroyCommandPool`, `DestroyDescriptorPool`, `FreeDescriptorSets`, `FreeMemory`, `DestroyFence`, or `DestroySemaphore`. `DestroyResource` on an excluded type is rejected with `BadMatch`. These exclusions are normative; implementations MUST NOT silently choose another destruction path.

Eligibility for the generic request does not replace type-specific lifetime checks:

- Buffer: the pending-use rules, command-buffer invalidation, and stale descriptor-slot rules described above apply.
- Pipeline and pipeline layout: references from a `RECORDING` command buffer prevent destruction; pending use also prevents it. On successful destruction, non-pending `EXECUTABLE` command buffers with matching references become `INVALID`.
- Shader Module and Descriptor Set Layout: after their required creation/Pipeline Layout dependency has ended, the applicable Vulkan lifetime rules apply.

Every rejection is atomic and leaves the public XID, internal lifetime states, and dependent Command Buffer states unchanged. On success, the public XID becomes invalid during the request; internal objects remain retained until all required references and backend accesses have ended. Device-wide cascading invalidation during `DestroyDevice` or client disconnect is unaffected. Device loss alone does not invalidate public XIDs; it terminalizes accepted work and changes affected resource and synchronization states according to the rules below.

## Dedicated destruction requests

`DestroyDevice`, `DestroyCommandPool`, `DestroyDescriptorPool`, `FreeDescriptorSets`, and `FreeMemory` remain separate requests because they have their own ownership, cascade, or memory-release rules. `DestroyFence` and `DestroySemaphore` are also dedicated requests; they are explicitly **not** callable through `DestroyResource`. This avoids two wire paths with different state checks for the same synchronization object.

`FreeMemory` invalidates the Memory XID only on success. Bound Buffers result in `BadMatch`; accepted GPU work accessing the allocation results in `INVALID_SYNCHRONIZATION_STATE`. XAverius v0.1 has no unbind/rebind operation, so all bound Buffers MUST be destroyed first.

## Device Destruction and Client Disconnect

On successful `DestroyDevice` or client disconnect, the public XIDs of the logical Device and its resources become invalid and are no longer addressable by new requests. Cascading invalidation MUST NOT be blocked by ordinary pending-use rejections. It does not retroactively change work that was already accepted: during normal teardown, that work must reach its actual terminal outcome, and internal Vulkan objects remain retained until all backend accesses have ended.

### Cross-resource teardown and backing-memory release

Device-wide cascading invalidation is a public-state operation, not an instruction to free children in arbitrary order. The server MUST retain the old internal identity graph while draining it. Descriptor-set slots, command-buffer recorded references, accepted submissions, active server operations, Buffer-to-Memory bindings, and parent-child references are distinct edges. The server MUST retire each edge exactly once through the operation that owns it. Invalidating a DescriptorSet XID does not by itself prove that its slot-held Buffer references or backend accesses have ended.

After successful `DestroyDevice`, no child XID remains addressable, so the client cannot perform per-resource cleanup to break remaining edges. The server MUST perform that internal teardown itself: stop new work, terminalize accepted submissions and open waits under the established lifecycle rules, invalidate command buffers and descriptor sets, retire descriptor-slot and recorded-command references, and then release buffers and their memory only after submission, active-operation, and backend-access references have drained. The implementation MAY use another safe internal order, but it MUST preserve every dependency until the dependent operation is finished and MUST NOT release a bound Memory allocation before the old Buffer identity and all possible accesses are safely retired.

The same identity rule applies to ordinary resource destruction: a publicly invalidated Buffer can remain internally live because a descriptor slot or other internal owner still references it. Its binding edge to Memory remains live for that entire interval. `FreeMemory` must reject while that internal Buffer remains bound; after device-wide invalidation, internal cleanup instead drains the edge without attempting a new public `FreeMemory` request. No delayed edge retirement may resolve an XID again, since the numeric XID may already identify a different resource.

A client disconnect ends event delivery for that X11 connection only. The server MUST mark the connection as unable to receive events and remove its event selections and public XID mappings from active connection state. Asynchronous backend completions MUST NOT enqueue events to a closed connection or deliver them through another connection. Event associations MUST be bound to the specific X11 connection and internal resource identity, not only to a numeric XID. For `ASYNC_ERROR`, a resource XID that has since been destroyed or reused MUST NOT be emitted as `resource_xid`; if the public resource XID is no longer live at the linearization point, `resource_xid = 0` is serialized. The server MUST NOT resolve an XID again from the current table to construct a delayed event. Accepted work still reaches its actual internal terminal outcome; disconnect neither requires successful completion nor indefinite waiting for GPU progress. Resources that the backend may still access remain alive until those accesses are proven to have ended, or are quarantined under the Device-loss rules.

**Identity of asynchronous completions:** Every backend callback or completion record MUST carry the immutable internal identity of the specific submission or resource and the identity of the original X11 connection. When a callback completes, the server MUST NOT resolve the target resource again from the current XID table using only a numeric XID. Before queueing an event, it MUST verify that the original connection remains active and able to receive events and that the lifecycle rules for the captured internal Device identity still permit delivery. A closed connection, destroyed Device identity, or reused XID MUST NOT be redirected to a new object or another connection. Discarding an undeliverable completion affects delivery only; internal submission, Fence/Semaphore, and backend cleanup states must still be terminalized exactly once.

Open server-side host waits belonging to a disconnected connection are cancelled and removed from wait registrations; no reply is generated because the connection is closed. Cancelling a host wait does not cancel an already accepted GPU submission and does not change its terminal outcome or Semaphore/Fence state. References used only by the cancelled wait registration are released once cancellation is established atomically; references held by active backend operations remain under the normal lifetime rules.

Competing wait completions are resolved through serialized server-side state transitions. For an open wait, the first terminal outcome established wins: an already-established satisfaction or timeout remains final; the first detected Device loss terminates the wait with `DEVICE_LOST`; if `DestroyDevice` is processed while the wait is still open and Device loss has not been detected, the wait ends with `DEVICE_DESTROYED`. Disconnect removes the wait without a reply. A later transition MUST NOT overwrite an already-terminal wait.

After successful processing of `DestroyDevice`, the server MUST NOT generate or deliver new XAverius events whose `device_xid` identifies the destroyed logical Device. This includes `DEVICE_LOST`, `DEVICE_IDLE`, `DEVICE_MEMORY_PRESSURE`, `SUBMISSION_COMPLETE`, `SUBMISSION_FAILED`, and `ASYNC_ERROR`; for `ASYNC_ERROR`, the destroyed Device XID MUST NOT be emitted as `device_xid` or `resource_xid`. Events generated and queued in the X11 output stream before `DestroyDevice` was processed remain unaffected. Suppressing delivery does not change the internal terminal outcome of accepted submissions or the requirement to retain backend references until possible accesses have ended. Device and Queue event selections are removed during cascading invalidation.

Internal cleanup MUST be safe and independent of public XID availability. The server MUST NOT wait indefinitely for a hung or lost Device. If the Device is lost, the following Device-loss rules apply; the server MUST NOT fabricate successful GPU completion.

## Device Loss and Terminal Cleanup

When a logical Device is detected as lost, the following rules apply to all its accepted submissions that have not yet reached a terminal state:

- Each submission terminates as failed with status `DEVICE_LOST`; it MUST NOT be reported as successfully completed.
- Associated Fences transition to `FAILED`, not `SIGNALED`.
- Affected Command Buffers transition to `INVALID` after leaving the pending phase and MUST NOT be submitted again.
- Internal resource references remain retained for as long as the backend driver or server cleanup may access them. Releasing them MUST NOT depend on GPU completion that may never occur after Device loss.

Individual resource-specific Destroy/Free requests are not categorically forbidden after Device loss: they may proceed when their ownership, recording, and lifetime checks are satisfied. Because affected submissions and open host waits are terminalized when Device loss is detected, they MUST NOT remain blockers solely because of their former pending state. `DestroyResource`, `DestroyFence`, `DestroySemaphore`, `DestroyCommandPool`, `DestroyDescriptorPool`, and `FreeDescriptorSets` remain logical cleanup paths under their respective rules; recording references continue to block destruction wherever the request rules require it. `FreeMemory` remains blocked while an internally live Buffer is bound or backend accesses to the allocation may still occur. A logical destroy may invalidate public XIDs but MUST NOT force premature release of internal backend objects.

During Device destruction or cascading cleanup, public resource XIDs may be invalidated even when ordinary pending-use destruction would be rejected. This exception applies only to Device-wide cleanup; it does not remove internal-reference obligations or permit fabricated successful completion. The server MUST safely tear down backend state and MUST NOT release internal resources until backend access is no longer possible.

After Device loss is detected, requests requiring further Vulkan work fail with DEVICE_LOST. Status queries and logical cleanup requests may still be processed where their individual contracts permit.

If the server cannot confirm during Device destruction or Device loss that the backend has stopped accessing internal resources, the Device is considered lost and is isolated: all nonterminal submissions fail internally with DEVICE_LOST, and public XIDs remain invalidated. If Device loss is detected while the logical Device is still publicly live and lifecycle suppression does not apply, the server reports DEVICE_LOST with reason_code = DRIVER_FAILURE when the cause is a backend/driver failure, or with the applicable existing reason code otherwise. If loss is detected during or after processing DestroyDevice, no new event is generated or delivered for the already-destroyed device_xid; internal failure and submission states are still terminalized correctly. This rule follows the general lifecycle boundary and prevents the Device-loss reporting requirement from overriding explicit event suppression after DestroyDevice. Internal resources and associated memory are quarantined, not released or reused for new resources, until backend quiescence is proven. If quiescence cannot be established safely, they remain quarantined until the server process exits. The server MUST NOT wait indefinitely for GPU completion or risk a use-after-free by releasing resources prematurely.

## Descriptor Pools and Sets

DestroyDescriptorPool is atomic. The request is rejected if any contained Set is used by pending work or referenced by a RECORDING Command Buffer. On rejection, the pool, sets, and Command Buffer states remain unchanged. Otherwise, the pool and all contained sets are publicly invalidated; non-pending EXECUTABLE Command Buffers that reference any of these sets become INVALID.

FreeDescriptorSets follows the same rules for the selected sets: repeated Set XIDs within one request are rejected with BadValue before any state change; pending use or a reference from a RECORDING Command Buffer causes atomic rejection. On success, the selected sets are invalidated and non-pending EXECUTABLE Command Buffers that reference them become INVALID. Logical release remains permitted after Device loss if the pending/recording rules are satisfied; internal backend references remain until safe quiescence. A Set MUST NOT be released both by an explicit free request and by the pool cascade; an already-invalidated Set XID is invalid for subsequent free requests.

## Pipelines and Synchronization Objects

DestroyResource for a Pipeline or Pipeline Layout is rejected while an accepted submission uses that resource. Without pending use, the general recorded-reference rules apply: references from RECORDING Command Buffers prevent destruction; referencing non-pending EXECUTABLE Command Buffers become INVALID when destruction succeeds.

DestroyFence is rejected while the Fence is associated with a nonterminal submission or an open WaitForFence registration references that exact internal Fence identity. DestroySemaphore is rejected while an accepted queue wait, queue signal, open WaitSemaphores registration for that exact internal Semaphore identity, or another running server-side host operation uses the semaphore. A host wait is no longer open once its terminal result has been serialized by the server; an unsent reply does not then block destruction. These rejections are atomic and use INVALID_SYNCHRONIZATION_STATE. If DestroyDevice is processed after Device loss, its Device-wide cascading invalidation may bypass these ordinary rejections. Device loss alone does not trigger public cascading invalidation; internal references remain until possible backend accesses have ended.

## Command Buffers and Descriptor Sets

A pending Command Buffer MUST NOT be modified, reset, freed, or submitted again in v0.1.

Ein Descriptor Set darf nicht aktualisiert oder freigegeben werden, solange eine angenommene Submission es verwenden kann. Command buffers reference the Descriptor Set object; slot contents are read from the current set at later execution time and are not frozen during recording. A successful `UpdateDescriptorSets` therefore atomically replaces the affected slot contents and updates the derived internal Buffer references of every non-pending command buffer that references the set. An `EXECUTABLE` command buffer remains executable after the update alone; later destruction of an old resource that is no longer referenced MUST NOT invalidate it because of that removed dependency.

Update-after-bind and Update-unused-while-pending are not supported.

## Buffers and Memory

DestroyResource for a Buffer is rejected while a RECORDING Command Buffer references it directly or indirectly (including through a referenced Descriptor Set), or while an accepted submission uses it directly or through a Descriptor Set. On successful destruction, all non-pending EXECUTABLE Command Buffers that directly or indirectly reference the Buffer become INVALID before the destroy request completes, according to the general rule. Descriptor Sets containing the Buffer remain alive as objects but are not submit-eligible until all affected descriptor slots have been updated with valid Buffer references or the sets have been freed. New submissions using such invalid descriptor contents are rejected atomically.

FreeMemory is rejected while any Buffer remains bound to the allocation or accepted work accesses the allocation. XAverius v0.1 provides no unbind/rebind operation. The client must therefore successfully destroy all bound Buffers before freeing the Memory block. A bound Buffer results in BadMatch; pending GPU work results in INVALID_SYNCHRONIZATION_STATE. A rejected FreeMemory request does not invalidate the Memory XID. If a destroyed Buffer is still referenced by descriptor slots, its internal object remains retained until those slots are overwritten or the Descriptor Sets are freed; the Buffer XID remains invalid in the meantime. Its internal binding reference to the Memory allocation remains for this entire period. The same applies while backend access or another internal reference keeps the Buffer alive. FreeMemory must therefore also be rejected with BadMatch if the public Buffer XID has already been invalidated but the internal Buffer remains bound to the allocation.

## Errors for Invalid Lifetime Operations

- Unknown or destroyed XAverius XID: `BadValue`
- Wrong type or incompatible resource: normally `BadMatch`
- Falsches Device: `BadMatch`
- Destroying a pending command buffer or descriptor set: `INVALID_SYNCHRONIZATION_STATE`
- Invalid fence reset: `INVALID_SYNCHRONIZATION_STATE`
- Lost device: `DEVICE_LOST`, unless the request explicitly permits logical invalidation

Successful device-wide cascading invalidation is a special rule and is not blocked by normal pending-use rejections.


Presentation lifecycle rule: an accepted present has one serialized terminal status and one internal cleanup. A later resize, Surface loss, or Device loss cannot overwrite an already terminal status. If still pending and forced to fail by OUT_OF_DATE, SURFACE_LOST, or DEVICE_LOST, its image is invalidated and IMAGE_RELEASED is not emitted. PRESENTATION_FAILED permits IMAGE_RELEASED only after backend quiescence and confirmation that the Swapchain remains usable. Event suppression never skips internal cleanup.



### Command-buffer recorded references and deferred retirement

A command buffer owns a distinct set of recorded-resource reference edges while it is RECORDING or EXECUTABLE. Successful reset detaches its recorded entries and retires those edges exactly once; successful execution preserves them when the buffer returns to EXECUTABLE. Execution failure or device loss makes the buffer INVALID, but does not permit early destruction of objects retained by an accepted submission or potentially reachable by the backend. Submission references are independent from recorded references and are retired by submission cleanup only after the terminal outcome and backend quiescence requirements are satisfied.

The reset/invalidation cleanup paths MUST be idempotent with respect to edge ownership. If invalidation retires a command buffer's recorded edges, a later reset MUST NOT retire those same edges again. If invalidation only marks the buffer invalid while an internal edge is still required for backend safety, that edge remains explicitly owned/retained until the safe cleanup point; reset may retire only the command-buffer-owned recorded edge and MUST NOT release the separate submission/backend hold. Re-recording creates a fresh reference set tied to the current internal resource identities and MUST NOT inherit stale references from the previous recording. All delayed callbacks use immutable internal identities, not re-resolved XIDs.