# Queue submission and ordering

## Queue Addressing

Queues are addressed by device XID, queue-family index, and queue index. The server MUST verify that the queue was actually created for this logical device.

## `QueueSubmit`

Request-Layout:

| Offset | Type | Field |
|---:|---|---|
| 8 | XID | Device-XID |
| 12 | CARD32 | Queue-Family-Index |
| 16 | CARD32 | Queue-Index |
| 20 | XID | Fence-XID, 0 bedeutet keine Fence |
| 24 | CARD16 | Command-Buffer-Count |
| 26 | CARD16 | Wait-Semaphore-Count |
| 28 | CARD16 | Signal-Semaphore-Count |
| 30 | CARD16 | `reserved = 0` |
| 32 | CARD64 | `submission_token` |
| 40 | variable | Command-Buffer-XIDs, Wait-Entries, Signal-Entries |

Each wait entry is 16 bytes:

- Relativer Offset 0: Semaphore-XID
- Offset 4: `CARD64 wait_value`
- Offset 12: `CARD32 wait_stage_mask`

For binary semaphores, `wait_value` MUST be zero. For timeline semaphores, `wait_value` is the required counter value.

Each signal entry is 12 bytes:

- Relativer Offset 0: Semaphore-XID
- Offset 4: `CARD64 signal_value`

For binary semaphores, `signal_value` MUST be zero. For timeline semaphores, `signal_value` is the counter value to signal.

The variable-length formula uses `C` for Command-Buffer-Count, `W` for Wait-Semaphore-Count, and `S` for Signal-Semaphore-Count; each symbol is the corresponding 16-bit count from the fixed header.

Total length:

`40 + 4*C + 16*W + 12*S`

`submission_token` is supplied by the client and treated as an opaque 64-bit value. It MUST be unique for every `QueueSubmit` request on the same X11 connection instance; reuse is forbidden even after a submission completes, for as long as that connection remains open. The scope is the lifetime of the connection instance, not a client name, process identity, device, queue, or pending-submission set. A newly established X11 connection is a new scope and MAY use token values used on a previous, closed connection. The server MUST key callback lookup by the captured connection instance and token together; it MUST NOT route a delayed callback from a closed connection to a newly established connection merely because the client identity or token matches. Value `0` is reserved and invalid. Tokens need not be ordered and have no temporal or numeric meaning. A timestamp or hash is permitted if the client actually guarantees uniqueness.

Error precedence (the first applicable phase wins): (1) incorrect total length, inconsistent counts, arithmetic overflow, or truncated entries results in `BadLength`; (2) syntactic fields are checked: `submission_token = 0`, a token already used on this connection, non-zero reserved fields, wait-stage masks containing zero or reserved bits, duplicate command-buffer XIDs, duplicate raw semaphore XIDs, and invalid values that can be identified without resolving a resource type result in `BadValue`; (3) required XIDs are resolved in wire order: device, optional fence, command-buffer XIDs in array order, wait-semaphore XIDs in array order, then signal-semaphore XIDs in array order. Unknown or non-live XIDs result in `BadValue`; (4) only then are resource type, client/device ownership, and queue association checked; a live resource of the wrong type, foreign ownership, cross-device association, a queue not created for this device, or a command buffer whose parent Command Pool was created for a different queue family than the submitted queue results in `BadMatch`; (5) after successful XID/type/ownership/queue validation, an unavailable or lost device takes precedence over mutable submission state and results in `DEVICE_UNAVAILABLE` or `DEVICE_LOST`; (6) if the device is operational, mutable preconditions are checked in wire order: first the optional fence state, then command buffers in array order, wait entries in array order, and finally signal entries in array order. Within each wait/signal entry, type-dependent numeric values are checked first, then stage-family compatibility (wait entries only), and then whether the semaphore operation is permitted, including pending/signal reservations. Invalid fence/command-buffer/semaphore states or an unsupported stage result in `INVALID_SYNCHRONIZATION_STATE`; invalid type-dependent numeric values result in `BadValue`. In particular, a timeline signal value that is not greater than the observable counter results in `BadValue`; a value that exceeds the counter but is not greater than every already-reserved pending GPU signal value results in `INVALID_SYNCHRONIZATION_STATE`, as for `SignalSemaphore`. Any other dependency that prevents acceptance results in `DEPENDENCY_FAILED`. Type-dependent values such as binary wait/signal values are checked only after type resolution. Within each phase, the field/array order in the request is preserved. Every synchronously rejected request is atomic and generates no submission event. Execution failures reported after acceptance are not X11 errors. A synchronous error MUST NOT produce `ASYNC_ERROR` for a submission that was never accepted.

The server copies the token unchanged into the corresponding `SUBMISSION_COMPLETE` or `SUBMISSION_FAILED` event and into submission-related `ASYNC_ERROR` events. The X11 event sequence number is independent and does not identify the submission.

### Wait Stage Mask

`wait_stage_mask` is an XAverius-specific `CARD32` bitmask; its bits are **not** the numeric Vulkan `VkPipelineStageFlags` values. The v0.1 mapping is fixed:

| XAverius Bit | Mask | Vulkan Stage |
|---|---:|---|
| `DRAW_INDIRECT` | `0x00000001` | `VK_PIPELINE_STAGE_DRAW_INDIRECT_BIT` |
| `COMPUTE_SHADER` | `0x00000002` | `VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT` |
| `TRANSFER` | `0x00000004` | `VK_PIPELINE_STAGE_TRANSFER_BIT` |
| `ALL_COMMANDS` | `0x00000008` | `VK_PIPELINE_STAGE_ALL_COMMANDS_BIT` |

Bits 4–31 are reserved and MUST be zero. The mask MUST set at least one bit. As in Vulkan, `ALL_COMMANDS` may be combined with other supported bits; such combinations are semantically redundant but valid. XAverius explicitly translates each set bit to its corresponding Vulkan value and combines the Vulkan bits using bitwise OR; the XAverius mask MUST NOT be passed through unchanged as a Vulkan mask.

The set stages MUST be supported by the addressed queue family under the Vulkan synchronization rules:

- `DRAW_INDIRECT`: queue family with `GRAPHICS` or `COMPUTE`.
- `COMPUTE_SHADER`: queue family with `COMPUTE`.
- `TRANSFER`: queue family with `GRAPHICS`, `COMPUTE`, or `TRANSFER`.
- `ALL_COMMANDS`: permitted on every queue family created for the logical device.

A mask with unknown/reserved bits or no set bits is syntactically invalid and results in `BadValue`. A syntactically valid mask whose stage is unsupported by the addressed queue family results in `INVALID_SYNCHRONIZATION_STATE`. This check occurs before acceptance; failure leaves submission, fence, and semaphore states unchanged.

For the compute-only reference workflow, `COMPUTE_SHADER`, `TRANSFER`, and `ALL_COMMANDS` are valid single-bit masks on a compute-capable queue. `DRAW_INDIRECT` is also permitted as a stage on a compute queue, even though the v0.1 command stream defines no indirect-dispatch commands. The wait takes effect at the selected Vulkan destination stage; it is not a general substitute for required memory dependencies between commands.

Before acceptance, all command buffers and synchronization objects are validated. All resources MUST belong to the specified device. Every command buffer MUST be executable, and its parent Command Pool's `queue_family_index` MUST equal the `queue_family_index` in this `QueueSubmit` request. A command buffer created from one queue family MUST NOT be submitted to a queue from another family, even when both families belong to the same logical Device. This family-compatibility check is part of phase 4 (queue/resource association), before Device-state and mutable-state checks. A mismatch returns `BadMatch` and consumes no token or synchronization state. A specified fence MUST be `UNSIGNALED` and MUST NOT already be pending.

A command-buffer XID MUST occur at most once in a single `QueueSubmit` request. Duplicate command-buffer XIDs are rejected with `BadValue` during scalar validation, before XID resolution or any state mutation. This avoids representing one command buffer as multiple pending entries under one submission token.

Duplicate wait or signal entries are invalid in v0.1 and result in `BadValue`. The same semaphore MUST NOT appear in both the wait and signal arrays of one submission; this conflict also results in `BadValue`.

**Atomicity guarantee:** If the request is rejected, no submission is created and no synchronization state changes. Acceptance means only that the work has been queued, not that it has completed.

`QueueSubmit` is a void request. Acceptance or rejection is reported synchronously through the normal X11 error rules; the token is used exclusively to correlate later asynchronous results.


### Validation and Atomic Acceptance

Validation has two phases. First, the server checks request framing, lengths/counts, reserved fields, and token syntax. It then resolves resources in the defined field order and checks type, client/device ownership, and queue association. Next, it checks device state and all mutable submission preconditions: every command buffer MUST be `EXECUTABLE`, not `PENDING` or `INVALID`; fences and semaphores must be eligible for submission; wait stages, semaphore types/values, timeline signal reservations, and all other dependencies must be valid. General XID error precedence and request-specific ordering also apply when multiple fields are invalid. An implementation MUST NOT reserve state early merely because an earlier entry has already been validated.

Only after all checks succeed does the server accept the submission as one serialized transaction. At this commit point, the `submission_token` is registered as used, the submission is created, command buffers are set to `PENDING`, fence and semaphore associations and wait/signal slots are reserved, and all internal resource references are retained. No visible part of this commit may be treated as accepted by other requests or asynchronous backend callbacks until the entire commit is complete.

Any rejection before this commit point is fully non-mutating: the token remains unused and may be reused in a corrected request; no command buffer leaves `EXECUTABLE`; no fence changes state or becomes associated with a submission; semaphore counters, signal availability, pending slots, and timeline reservations remain unchanged; and no submission objects, internal submission references, or submission events are created. This also applies if several command buffers or synchronization objects have already been validated individually before a later entry fails. A synchronous error MUST NOT produce `ASYNC_ERROR` for a submission that was never accepted.

The `EXECUTABLE`-to-`PENDING` transitions and synchronization reservations therefore form one shared commit, not separate incremental changes. After this commit, the submission is accepted; subsequent backend failures are handled exclusively through the terminal submission outcome and the defined synchronization states.

### Serialization against resource destruction and release

QueueSubmit acceptance MUST be serialized with every resource-destruction or release operation whose type-specific lifetime rule treats the submitted work as a blocker. This includes `DestroyCommandPool`, `DestroyDescriptorPool`, `FreeDescriptorSets`, eligible `DestroyResource` operations, `DestroyFence`, and `DestroySemaphore`. The serialization covers the complete submission commit and the complete public invalidation/cleanup commit; validating a resource and reserving submission state in separate unsynchronized steps is not permitted.

If QueueSubmit acceptance commits first, all of its pending-use markers, synchronization reservations, and internal references are visible to the competing destruction request. That request MUST apply its ordinary type-specific blocker and reject atomically where the contract requires it. If destruction commits first, its public XID invalidation and any required executable-command-buffer invalidation are visible to QueueSubmit: a directly named invalidated XID fails normal XID resolution with `BadValue`; a still-live command-buffer XID whose state was changed to `INVALID` fails the mutable command-buffer check with `INVALID_SYNCHRONIZATION_STATE`. The rejected submission consumes no token, creates no submission, reserves no Fence/Semaphore state, and retains no submission references.

The rule is based on each resource's specified pending-use semantics, not on every internal dependency edge. In particular, a Pipeline-held PipelineLayout dependency does not by itself block public PipelineLayout invalidation while work uses the Pipeline; a direct PipelineLayout use by recorded commands or accepted work remains a blocker. Likewise, a DescriptorSet's retained DescriptorSetLayout definition permits public DescriptorSetLayout invalidation while existing Sets remain usable; the retained Set/backend dependency is not a public-XID pending-use blocker. Internal identities and backend references remain protected in either ordering.

`DestroyDevice` and client disconnect are separate lifecycle operations: their defined cascading invalidation is not rejected by ordinary pending-use blockers. Accepted submissions retain their captured identities and reach the terminal outcomes and cleanup required by the Device/connection lifecycle rules.
## Terminal Submission State and Device Loss

Every accepted submission has exactly one terminal outcome:

- `SUBMISSION_COMPLETE`: all commands in the submission completed successfully.
- `SUBMISSION_FAILED`: the submission did not complete successfully; the event contains the `submission_token` and an error status.

Each accepted submission receives exactly one internal terminal outcome. If the corresponding completion or failure event is selected for the queue and the client connection remains active, the server delivers exactly that event unless delivery is suppressed by a previously processed `DestroyDevice` request under [Resource lifetime and ownership](resource-lifetime.md). Without a matching event selection, or when lifecycle rules suppress delivery, no such event is delivered to the client; the internal terminal state is unaffected. `ASYNC_ERROR` may provide additional diagnostic information, but does not replace the terminal outcome and MUST NOT create a second terminal outcome. A rejected `QueueSubmit` request was not accepted and receives no terminal outcome.

If an execution failure occurs after acceptance, the submission fails; it is not considered complete. Its fence transitions to `FAILED`, if applicable. Every command buffer used by the submission transitions to `INVALID` when its pending phase ends. Before reuse, it must be reset and recorded again according to the command-buffer API. The server retains internal references until the submission is terminal and the backend no longer accesses the resources.

On device loss, all accepted submissions of the affected logical device that have not yet reached a terminal state fail with `DEVICE_LOST`. The server MUST NOT fabricate successful completion or set a fence to `SIGNALED` for work that did not complete successfully. Exactly one terminal event remains designated for each accepted submission, provided the client connection remains active and delivery is not suppressed by the `DestroyDevice` lifecycle rules. No further GPU work is executed on the lost device. Requests that only query status or clean up the logical device may proceed according to their respective rules; operations requiring a functional device fail with `DEVICE_LOST`.

**Atomic terminal transition:** The transition of an accepted submission from non-terminal to exactly one terminal result (`COMPLETE` or `FAILED`) is a one-time serialized state transition. Success callbacks, failure callbacks, and device-loss handling compete for this same transition; the first valid outcome serialized by the server wins. A device-loss transition MUST mark all submissions that are still non-terminal at that point as `FAILED/DEVICE_LOST` before later backend callbacks for those submissions can be processed. A callback arriving after a terminal state has been established MUST NOT change the outcome, fence/semaphore states, or event decisions. Fence updates additionally require that the callback's captured internal Fence identity, internal use generation, and submission association still match the Fence's current association. `ResetFence` and a subsequent submission on the same Fence advance/rebind this internal generation/association under the same serialization used for terminalization; a delayed or duplicate callback from an older submission MUST be ignored even if the numeric Fence XID has since been reused or the same internal Fence has been reset and submitted again. The Fence state update, clearing of the submission association, and release of the Fence's pending-use marker are one atomic terminalization step. Semaphore callbacks additionally capture the exact internal semaphore identity and a unique reservation identity for the specific wait/signal operation. They may mutate shared semaphore state or release a pending slot only if that reservation is still current and the operation's terminal transition wins; numeric XID lookup alone is never sufficient. Device-loss terminalization is serialized against semaphore state publication, and a late or duplicate callback MUST NOT publish success, change an `UNTRUSTED` binary semaphore, advance a timeline counter, or remove another operation's reservation. Reservation release is idempotent and local to that reservation; backend-access holds remain until quiescence is established. If successful completion was already terminalized, later-detected device loss cannot retroactively turn it into a failure. If device loss was terminalized first, a later success MUST NOT set `SIGNALED`, advance a timeline counter, or mark a signal as successfully consumed.

Finalization manages all resources owned by a submission as one idempotent operation: each wait/signal reservation, fence association, pending reference, and command-buffer pending marker is released or completed at most once. Logical terminalization MUST NOT wait for backend quiescence. References and memory that the backend may still access remain retained separately until those accesses are proven to have ended, or are quarantined under the Device-loss rules. Event delivery is a downstream effect of the terminal decision and cannot roll it back or repeat it.

## Semaphore references

The semaphore types and host-side semaphore operations used by `QueueSubmit` are specified in [Synchronization objects](synchronization.md). The `QueueSubmit` request retains its wait and signal arrays as described above.

For an accepted submission, all semaphore wait/signal reservations and internal references are committed atomically with submission acceptance. A rejected request leaves the semaphore counters, binary signal availability, pending-operation slots, and internal references unchanged. Each accepted wait/signal entry retains the exact internal semaphore identity, not just its numeric XID, until that operation has reached its actual terminal outcome and the backend can no longer access the semaphore. A public XID becoming invalid cannot redirect an already accepted operation to a later resource that reuses the same XID.

A successful wait releases its pending-wait slot only after the wait has actually been satisfied. A successful signal releases its pending-signal slot only after its signal operation has actually completed; for a binary semaphore the signal then remains available until consumed by one successful wait. For a timeline semaphore, the successful signal updates the observable counter and removes its pending-value reservation. If a submission fails before an operation succeeds, the server must not fabricate a successful signal or wait consumption; it releases only reservations whose operation is known to be terminal, and applies the device-loss quarantine rules if backend quiescence cannot be established. Device loss fails all affected non-terminal submissions and prohibits new work on that device; it does not imply that backend references can be freed immediately. Each wait/signal reservation is an independently identified record; removing a reservation must compare the captured internal semaphore identity and reservation identity against that record. Implementations MUST NOT release reservations by recomputing the semaphore's current XID mapping or by clearing all reservations when one callback arrives.

# Queue Ordering and Cross-Queue Dependencies

The following rules apply to accepted submissions on the same logical Device:

- **Same queue:** The server submits accepted work to a queue in the order in which the corresponding `QueueSubmit` requests were accepted. Queue order does not guarantee that one submission has fully completed before execution of the next begins; independent work MAY overlap. Queue order alone does not replace a required memory dependency or explicit synchronization between commands.
- **Different queues:** No implicit ordering or memory dependency exists between different queues, including queues in the same queue family. The server MUST NOT promise a shared FIFO order, fairness, or a maximum wait time.

For Timeline semaphore signal operations, same-queue submission order establishes signal-operation order only among signals submitted to that same queue. The fact that `QueueSubmit` reserves Timeline signal values in increasing numeric order does not order signals submitted to different queues. The client MUST establish explicit execution dependencies so that, for each Timeline semaphore, every lower-valued signal operation executes before every higher-valued signal operation, including host signals. Separately, a queue-side Timeline wait may be satisfied only by a successful signal operation whose value reaches the wait value and which is not ordered after that wait; a later signal on the same queue cannot satisfy an earlier wait on that queue. A reservation does not establish wait eligibility. The server MUST NOT treat acceptance order, increasing reservation values, or callback delivery order as a substitute for these dependencies. The common rules and host-signal constraints are defined in [Synchronization objects](synchronization.md#timeline-semaphores).
- **Explicit dependency:** A GPU dependency across queues MUST be established with a matching semaphore signal and wait. The wait-stage mask determines the supported pipeline stages at which the wait dependency applies; it does not automatically create arbitrary memory dependencies for all resources. Required memory dependencies MUST be covered by supported commands and synchronization operations in accordance with Vulkan rules.
- **Fence and host wait:** A fence observes the terminal state of the submission to which it is attached. `WaitForFence` and `WaitSemaphores` block the requesting client until the reply, but do not themselves create a GPU dependency between queues. A host wait on a semaphore is not a substitute for a queue-side semaphore wait.
- **Host signal:** `SignalSemaphore` updates the Timeline counter on the host. A queue waiting for that value may thereby make progress; the host-signal operation does not order other GPU commands that are not connected through that semaphore dependency.
- **Token and events:** `submission_token` is only a correlation value. Neither its numeric value nor the order of tokens or event sequence numbers establishes submission order. Terminal events report outcomes; they do not create synchronization.

These rules specify required Vulkan-compatible ordering boundaries, not scheduler implementation details. In particular, v0.1 makes no guarantee of fairness, maximum scheduling latency, or progress within a fixed deadline.

# Ordering and Synchronization Guarantees

1. Requests on the same X11 connection are generally validated and processed in X11 protocol order. A request waiting for GPU progress MUST NOT block the dispatcher in a way that prevents a later `SignalSemaphore` request on the same connection from enabling that progress.
2. A successful `WriteBuffer` reply is an ordering boundary within the specified logical Device: all earlier accepted submissions on that Device are terminal, the transfer is complete, and every later accepted submission on any queue of that Device observes the written bytes. No cross-device synchronization is implied. While `WriteBuffer` is waiting, later `SignalSemaphore` requests remain dispatchable and a valid host signal MUST execute when it can release earlier work; later `WaitSemaphores` requests MAY register normally and their own timeout deadlines continue to run. Later `QueueSubmit` requests remain deferred until `WriteBuffer` succeeds or fails. The normative details are in [Memory and Buffers](memory-buffers.md#57-writebuffer). If the server finds among those deferred requests a Binary or Timeline signal entry that would satisfy a wait of an earlier non-terminal submission, and no already-accepted signal operation is eligible to satisfy that wait, `WriteBuffer` MUST fail with `DEPENDENCY_FAILED`. For Timeline semaphores, the signal value must reach or exceed the waited value and its signal operation must not be ordered after the wait; for Binary semaphores, it must be the same semaphore with a compatible accepted signal operation. Only already-accepted and eligible signal operations count as possible releases; signal entries in deferred submissions do not. A `QueueSubmit` deferred behind `WriteBuffer` cannot satisfy a host `WaitSemaphores` registration until the upload completes and that submission is accepted. The deferred `QueueSubmit` is processed normally afterward and MUST NOT be accepted before a successful `WriteBuffer`. While deferred, it is not accepted: it MUST NOT change semaphore or fence state, create pending reservations, or commit internal resource references as an accepted submission. Full validation and atomic state transfer occur only during normal acceptance after `WriteBuffer` completes.
3. An accepted `QueueSubmit` is not necessarily complete.
4. `ReadBuffer` replies only after the requested data is ready and required GPU/host visibility operations have completed. In v0.1, the server MUST wait for all earlier accepted `QueueSubmit` submissions on the same logical Device to reach a terminal outcome before replying; full Device synchronization satisfies this requirement. The server MUST also account for earlier `WriteBuffer` transfers affecting the read range. An earlier failed GPU operation MUST NOT be treated as successful execution; the data is not guaranteed to be correct if the failed work could have modified the read range.
5. X11 `Sync` confirms processing of earlier X11 requests, not GPU completion.
6. XAverius automatically synchronizes the transfer boundaries required by `WriteBuffer` and `ReadBuffer`. The `WriteBuffer` guarantee applies across all queues of the same logical Device; client-side semaphores or barriers are not required solely to make that upload visible to later accepted work.
7. XAverius does not infer arbitrary shader-to-shader dependencies from shader contents.
8. Clients remain responsible for explicit GPU dependencies between arbitrary commands.
9. For the first implementation, conservative full-Device synchronization is acceptable.
10. Errors discovered after asynchronous work has been accepted are reported through events and synchronization state.



Command-buffer reference retirement is separate from submission terminalization. The terminal transition may set a command buffer to INVALID and release its submission-owned references/reservations exactly once, but any recorded-reference edge and backend hold still needed to protect a possible in-flight access remains retained until that access is known to have ended. The reset/invalidation cleanup path MUST consult explicit edge ownership so that later reset, pool destruction, device cascade, or callback completion cannot release the same reference twice. A successful execution preserves the recorded references for the command buffer's return to EXECUTABLE; a failed execution does not make the recorded command stream reusable, and reset plus rerecording is required.
