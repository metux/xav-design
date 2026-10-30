# Synchronization objects

## Creating Semaphores

`CreateSemaphore` has a total length of 28 bytes:

- Offset 8: Device-XID
- Offset 12: Semaphore-XID
- Offset 16: `CARD32 semaphore_type`
- Offset 20: `CARD64 initial_value`

Types:

- `BINARY = 0`
- `TIMELINE = 1`

For binary semaphores, `initial_value` MUST be zero. Binary semaphores begin unsignaled. In `QueueSubmit`, the `wait_value` and `signal_value` fields for binary semaphores MUST also be zero. `CreateSemaphore` validation precedence is normative: (1) exact 28-byte request length (`BadLength`); (2) validate `semaphore_type` and the type-dependent `initial_value` (`BadValue` for an unknown type or nonzero Binary initial value); (3) validate `semaphore_xid` as a create-XID (`BadIDChoice` if invalid or occupied); (4) resolve `device_xid` (`BadValue` if unknown or non-live); (5) validate live resource type, client ownership, and Device association (`BadMatch`); (6) check logical-Device state (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (7) create the backend semaphore (`ALLOCATION_FAILED` on allocation failure). A later phase MUST NOT override an earlier error. Creation is atomic: on any failure, the semaphore XID remains unallocated. Every successful v0.1 logical Device has the mandatory Vulkan `timelineSemaphore` feature enabled, so `TIMELINE` creation requires no additional per-semaphore feature negotiation; backend creation failures use the stated `ALLOCATION_FAILED` outcome.

## Binary Semaphores

Binary semaphores follow the Vulkan signal/wait rules.

- A signal MUST NOT satisfy multiple competing waits.
- Host counter queries, host waits, and host signals are invalid for binary semaphores.
- Pending signal and wait states MUST be validated atomically.
- A signal and a wait MUST be compatible under the applicable Vulkan rules.

In v0.1, at most one signal operation and one wait operation may be pending for a binary semaphore at any time. A pending wait may wait for a signal that has not yet been enqueued, and a signal may be pending before its matching wait is enqueued. The server tracks the signal state (`UNSIGNALED`, `SIGNAL_PENDING`, `SIGNALED`, or `UNTRUSTED`) separately from references to accepted wait and signal operations. `UNTRUSTED` means that after a failed operation the server cannot determine the backend payload state with confidence; it is not equivalent to `UNSIGNALED`. Accepting a wait does not consume the signal immediately: consumption occurs only when the wait is successfully satisfied by the GPU/backend. A new signal cycle may begin only after that consumption; merely accepting a wait or leaving it pending does not release the signal. A successfully completed signal remains available until exactly one wait consumes it. A second signal operation is rejected while a signal is available or another signal operation is pending. A second pending wait is rejected while the previous wait remains unsatisfied or incomplete. Such `QueueSubmit` rejections are atomic and return `INVALID_SYNCHRONIZATION_STATE`. An error or device loss MUST NOT mark a signal available or consumed unless that outcome actually occurred. On device loss, affected submissions fail. For each pending binary semaphore operation belonging to an affected non-terminal submission, the server MUST preserve a confirmed payload state only when it can prove the operation did not change the payload or had already completed successfully; if signal/wait consumption is uncertain, the semaphore MUST transition to `UNTRUSTED`. The operation's reservation is released exactly once as part of terminalization, but this release MUST NOT make an uncertain signal available or permit another operation. Late callbacks MUST NOT overwrite `UNTRUSTED` with `SIGNALED` or `UNSIGNALED`. The semaphore follows these device-loss rules. If the server cannot prove whether an accepted but failed backend operation took effect on a binary semaphore signal or wait, it MUST mark that semaphore `UNTRUSTED`. This state is terminal for normal use: further queue waits and queue signals on the semaphore are rejected before acceptance with `DEPENDENCY_FAILED`. The server MUST NOT treat the semaphore as signaled or unsignaled, and MUST NOT make it usable again through a local state reset. The public semaphore XID remains live until it may validly be destroyed; internal backend references remain until quiescence. If it can be proven that the failed operation did not change the semaphore payload, the previous confirmed signal state is retained. Device loss remains subject to the stricter device-wide rules. Every accepted binary wait or signal reservation has a unique internal reservation identity tied to the exact internal semaphore identity and operation. A callback may change the shared payload state or release a pending-operation slot only if that exact reservation is still current and the operation's terminal transition wins; it MUST NOT find or modify a reservation by numeric XID alone. Every accepted `QueueSubmit` operation MUST additionally capture the non-reusable internal Device identity/generation that accepted it. Its terminal callback MUST validate that captured Device generation before changing submission status, command-buffer state, fence state, timeline counters, binary payload state, or semaphore reservations. Reusing the public Device XID creates a distinct Device generation and fresh semaphore objects/reservation identities; it MUST NOT inherit callback registrations or owner-index entries from the destroyed Device. A late callback from the old generation may retire only its own captured command-buffer, fence, semaphore, and backend references. It MUST NOT clear, consume, publish, or otherwise mutate a reservation belonging to the replacement Device, even if the public Device XID, semaphore XIDs, queue coordinates, and submission token are all reused. Device-loss propagation from an old-generation callback is confined to the old Device and its captured semaphore-owner graph. Device-loss terminalization and callback state publication use the same serialization. After Device Loss has terminalized an operation, a delayed or duplicate callback MUST NOT publish success, change `UNTRUSTED`, consume/resurrect a signal, or clear a reservation owned by another operation. Reservation release is idempotent and reservation-local; any backend hold needed for quiescence is retained separately.

## Presentation Waits on Binary Semaphores

`QueuePresent` uses the same global state machine and pending-wait exclusivity as `QueueSubmit`. An accepted present atomically reserves one wait slot for each specified binary semaphore; a semaphore with an incompatible existing wait or in the `UNTRUSTED` state causes synchronous atomic rejection. Acceptance itself does not consume a signal. Consumption is recorded only after the backend wait is confirmed successful. The shared semaphore record is authoritative across both APIs: whichever terminal callback arrives first must record confirmed consumption there, and a later callback for the other operation MUST NOT resurrect the payload from a stale per-request snapshot. A submission signal reservation remains held until its own callback terminalizes, even if a present wait has already consumed that signal; the shared consumption marker bridges that callback ordering. A failed submit callback with no proof that the signal payload remained unchanged MUST mark the shared semaphore `UNTRUSTED` if consumption has not already been confirmed; a later present callback MUST NOT downgrade that uncertainty. Conversely, if the present callback first confirms consumption, the shared `signal_consumed` marker preserves the known `UNSIGNALED` outcome when the submit later fails, and the submit callback releases only its own signal reservation.

If an accepted presentation ends before its wait is known to have completed, each affected semaphore is handled independently: payloads proven not to have been consumed retain their confirmed state and valid signal reservations; payloads proven consumed are recorded as consumed; an uncertain payload outcome makes the semaphore `UNTRUSTED`. The wait reservation is released exactly once when the wait reaches a terminal state. `UNTRUSTED` is authoritative and terminal for ordinary semaphore use: a late or duplicate completion callback MUST NOT downgrade it to `SIGNALED` or `UNSIGNALED`, even if that callback reports consumption. An uncertain operation MUST NOT be treated as successfully consumed or reset to unsignaled. The stricter device-wide rules above apply on device loss.

## Timeline Semaphores

Timeline semaphores have a monotonically increasing unsigned 64-bit counter.

- A wait is satisfied when the observable counter reaches or exceeds the requested value.
- A wait MAY be queued before the signal that satisfies it is queued.
- Signal values MUST be greater than the current counter and consistent with all pending signals. For atomic validation, an accepted signal that has not reached a terminal state counts as pending even if its counter value has not yet been reached; new GPU signal values MUST be greater than all already reserved pending signal values for the same semaphore. A pending GPU signal reserves its value but does not increase the observable counter.
- The observable counter advances only when the corresponding signal operation has actually completed successfully. Acceptance of a `QueueSubmit` request reserves the signal value but MUST NOT advance the counter prematurely.
- A successfully executed signal satisfies all previously queued waits whose values are reached; a wait does not modify the counter.
- Multiple signal entries for the same timeline semaphore in a single `QueueSubmit` are not permitted in v0.1.
- After a failed submission or device loss, a value that was only reserved and never successfully signaled MUST NOT be reported as reached. Reservations are released only when the corresponding operation becomes terminal; after device loss, no further normal signal operations are permitted on that device. Each pending timeline signal reservation has a unique internal reservation identity tied to the exact semaphore identity and accepted operation. Terminalization removes only that reservation, never all reservations for a numeric XID or a cached maximum-value slot. A callback may publish a counter value only if its operation won terminalization before Device Loss and the signal actually succeeded; after Device Loss terminalization, late or duplicate callbacks MUST NOT advance the counter or remove a newer operation's reservation. Out-of-order successful callbacks update the counter with `max(current_counter, completed_signal_value)` and remove only their own reservation.
- **Signal-operation ordering is distinct from reservation and callback order.** For each Timeline semaphore, all host and GPU signal operations MUST execute in strictly increasing value order. The reservation checks above enforce numeric monotonicity but do not, by themselves, establish execution dependencies. `QueueSubmit` submission order establishes signal-operation order only for submissions to the same queue. Signal operations on different queues have no implicit order; the client MUST establish an explicit execution dependency that orders every lower-valued signal before every higher-valued signal. The server MUST NOT infer such an order from request arrival, reservation creation, `submission_token`, or callback delivery order. Callback delivery MAY be out of order only when the underlying signal operations themselves completed in valid increasing order; the `max(current_counter, completed_signal_value)` rule prevents a delayed callback from decreasing an already-published counter and does not authorize out-of-order signal execution. If the client fails to establish the required execution order, the affected Timeline semaphore use is invalid and v0.1 does not guarantee its counter or wait outcomes.


## `GetSemaphoreCounterValue`

Request: exactly 16 bytes; device XID at offset 8 and semaphore XID at offset 12. Normative validation precedence is: (1) exact total length (`BadLength`); (2) resolve Device XID, then Semaphore XID in wire order (`BadValue` for unknown or non-live XIDs); (3) validate live resource type, client ownership, and Device association (`BadMatch`); (4) check Device state (`DEVICE_LOST`); (5) require a Timeline semaphore (`BadMatch`). Earlier phases take precedence when multiple conditions are invalid. The Device-state check and counter snapshot are serialized against Device Loss: if loss is already established at the check, the request fails with `DEVICE_LOST`; otherwise the query returns the counter snapshot at its linearization point. The wire reply has no status field that can reliably distinguish an error from a counter value, so the server MUST NOT return a purported current counter as a successful reply after Device Loss has been established.

Reply:

- Offset 8: `CARD64 counter_value`
- Offset 16–31: reserved, zero
- Reply payload length: zero

## `WaitSemaphores`

Fixed request header: 28 bytes; total length: `28 + 12 * semaphore_count` bytes.

- Offset 8: Device-XID
- Offset 12: `CARD32 semaphore_count`
- Offset 16: `CARD32 wait_mode`
- Offset 20: `CARD64 timeout_ns`
- Offset 28: array of 12-byte entries

Each entry contains a semaphore XID and `CARD64 wait_value`.

Wait modes:

- `WAIT_ANY = 0`
- `WAIT_ALL = 1`

The request length MUST be exactly `28 + 12 * semaphore_count` bytes; a length mismatch or arithmetic overflow results in `BadLength`. Synchronous validation MUST follow this order: (1) length and checked arithmetic; (2) `semaphore_count != 0`, a valid `wait_mode`, and no duplicate semaphore XIDs (`BadValue`); (3) resolve the device XID and then semaphore XIDs in array order (`BadValue` for unknown or non-live XIDs); (4) check resource type, client/device ownership, and cross-device association (`BadMatch`); (5) check device state; (6) verify that all semaphores are timeline semaphores (`BadMatch`). Checks through step 6 occur before registering the wait; every synchronous rejection leaves no wait registration. For `timeout_ns != 0`, the initial condition check and installation of the open wait registration MUST be one atomic operation in the same serialization domain used by timeline-counter updates and wait terminalization. A signal racing this transition MUST therefore either be visible to the initial condition check or observe the installed registration and trigger its reevaluation; it MUST NOT fall between the check and registration and be lost. For `timeout_ns = 0`, the server performs one serialized condition check and MUST NOT install a wait registration. For nonzero timeouts, condition satisfaction, timeout expiry, Device Loss, and `DestroyDevice` compete in the same serialized terminalization domain: the first terminal outcome committed while the registration is open wins. A condition observed as satisfied before timeout terminalization returns `SUCCESS`; once timeout wins, a later signal MUST NOT rewrite it. Device Loss and `DestroyDevice` likewise MUST NOT overwrite an already-terminal result. Cancellation on disconnect prevents all later callbacks from replying or releasing the registration twice. If the device is already lost, validation after successful XID/type/ownership checks returns the X11 error `DEVICE_LOST`. For a wait that is already registered and open, device loss is instead a terminal wait result, not a subsequent request-validation error. If `DestroyDevice` is processed while the wait remains open and device loss has not already been established as terminal, the result is `DEVICE_DESTROYED`.

### Timeout Semantics

The following rules apply to `timeout_ns`:

- `0`: non-blocking; the server checks the condition once and replies immediately.
- `UINT64_MAX`: wait indefinitely until the condition is satisfied, Device Loss is detected, or `DestroyDevice` is processed while the wait remains open.
- Any other value: timeout in nanoseconds measured with a monotonic clock that is not adjusted by wall-clock corrections. The deadline starts when the server takes the request for execution.

The server MAY divide a finite wait internally into multiple wait intervals, but MUST preserve the original deadline. Scheduler delays MUST NOT intentionally restart the deadline. At deadline expiry, timeout may win only if the wait is still open: a condition already committed as satisfied returns `SUCCESS`, an already committed Device-loss outcome remains `DEVICE_LOST`, and a `DestroyDevice` processed while the wait remains open (and before Device Loss wins) returns `DEVICE_DESTROYED`. If no other terminal outcome has committed when timeout terminalization wins, `TIMEOUT` is returned. The server is not required to reply exactly at the nanosecond boundary; scheduling may delay the actual reply.

An open wait has exactly one terminal outcome. The server serializes detection of condition satisfaction, timeout, device loss, and `DestroyDevice` with the corresponding state transitions. Installation/recheck, timeline counter publication, and wait terminalization MUST use compatible synchronization so that a signal cannot be lost between the initial check and registration, and no callback can terminalize a cancelled or already-terminal registration. The first terminal outcome detected wins and MUST NOT later be overwritten. A condition already detected as satisfied retains `SUCCESS`; device loss detected first terminates the wait with `DEVICE_LOST`; if `DestroyDevice` is processed while the wait remains open and device loss has not already been detected, `DEVICE_DESTROYED` terminates the wait. On client disconnect, the server-side wait registration is cancelled without a reply.

`WaitSemaphores` MUST NOT synchronously block the X11 request dispatcher. The server registers the wait condition and provides the reply later while continuing to process subsequent requests on the same connection. This is necessary so that a later `SignalSemaphore` or `QueueSubmit` can provide the expected value. The wait request itself does not order or hold back subsequent GPU submissions. The timeout deadline starts when the wait request is taken for execution and continues to run while subsequent requests are processed.

The reply is exactly 32 bytes long. Offset 8 contains a `CARD32 status` with `SUCCESS = 0` or `TIMEOUT = 1`; offsets 12–31 are zero and `reply.length = 0`. A timeout is a normal reply, not an X11 error. A timeout changes neither semaphore counters nor queue, fence, or semaphore state. A wait made impossible by device loss terminates with the normal X11 error `DEVICE_LOST`, not as a masked `TIMEOUT`.

## `SignalSemaphore`

Request: 24 bytes; void request with no reply.

- Offset 8: Device-XID
- Offset 12: Semaphore-XID
- Offset 16: `CARD64 signal_value`

Synchronous validation MUST follow this order: (1) exact total length of 24 bytes (`BadLength`); (2) resolve the device XID, then the semaphore XID (`BadValue` for unknown or non-live XIDs); (3) check resource type, client/device ownership, and cross-device association (`BadMatch`); (4) check device state (`DEVICE_UNAVAILABLE` or `DEVICE_LOST`); (5) check timeline type and signal-value/reservation consistency (`BadMatch` for binary semaphores; `BadValue` when `signal_value` is less than or equal to the observable counter; `INVALID_SYNCHRONIZATION_STATE` when the value exceeds the counter but crosses or violates an existing GPU signal reservation). This order also applies when multiple errors are present. All checks before signaling form one atomic request operation; synchronous rejection changes neither counters nor reservations.

Only timeline semaphores are permitted. The signal value MUST be greater than the current counter; a value less than or equal to the observable counter is rejected with `BadValue`. It MUST also be less than every already reserved, non-terminal GPU signal value for the same semaphore; a value that exceeds the counter but crosses or violates an existing GPU signal reservation is rejected with `INVALID_SYNCHRONIZATION_STATE`. This numeric reservation check does not itself establish the required signal-operation execution order. If one or more GPU signal reservations are pending, the client MUST ensure that every corresponding GPU signal operation is ordered after this host signal operation; the fact that the host value is lower than every reserved GPU value is necessary but not sufficient. The host signal MUST NOT be used to bypass or race an otherwise unordered pending GPU signal. This allows a host signal to provide a lower value that releases a waiting submission without skipping over a lower GPU reservation only when the required execution dependency is also established. If there are no GPU reservations, any value greater than the current counter is permitted. Validation and the host signal operation form one atomic request operation. The server checks the current counter and all reservations atomically with execution of the signal.

The server executes the host signal before proceeding with normal processing of the next request on the same X11 connection. Exception: while an earlier `WriteBuffer` request is waiting for prior submissions, the server MAY execute a later `SignalSemaphore` request before that `WriteBuffer` completes if required to let the prior submissions make progress. The signal must still be fully validated and executed atomically. Later `QueueSubmit` requests remain deferred until `WriteBuffer` completes and MUST NOT cross its ordering boundary. Once the signal operation succeeds, the counter is updated and any wait thereby satisfied may proceed. The server MUST NOT treat the signal request as complete until the host signal has executed successfully.

Validation errors and Vulkan errors detected immediately are reported as normal X11 request errors; the request leaves no partially executed signal operation. Device loss occurring after the operation is accepted is reported through the normal device-loss/asynchronous-error mechanisms. Because the request has no reply, the client can detect errors through normal X11 error handling or `XSync`. A later request on the same connection MUST NOT execute before the host signal operation completes.

## Destroying Semaphores

`DestroySemaphore` is a void request with a fixed total length of 16 bytes: device XID at offset 8 and semaphore XID at offset 12. It follows the general lifetime rules in [Resource lifetime and ownership](resource-lifetime.md). Destruction is rejected with `INVALID_SYNCHRONIZATION_STATE` while an accepted queue wait, queue signal, open `WaitSemaphores` registration, or another active server-side host operation references the exact internal semaphore identity. Rejection changes neither the XID nor synchronization state. A wait registration is no longer open once its terminal result has been serialized by the server; a reply not yet sent does not block destruction. After successful destruction, the public XID becomes invalid immediately; internal data is retained while backend accesses remain possible. On device loss, device-wide cascading invalidation may bypass this normal rejection.

## Fences

## States

Defined states:

- `UNSIGNALED = 0`
- `PENDING = 1`
- `SIGNALED = 2`
- `FAILED = 3`

Transitions:

- Creation → `UNSIGNALED`
- accepted submission with a fence → `PENDING`
- successful completion → `SIGNALED`
- asynchronous execution failure → `FAILED`
- reset from `SIGNALED` or `FAILED` → `UNSIGNALED`
- rejected submission → state remains unchanged

## `CreateFence`

Total length: 24 bytes.

- Offset 8: Device-XID
- Offset 12: Fence-XID
- Offset 16: `CARD32 create_flags = 0`
- Offset 20: `CARD32 reserved = 0`

`CreateFence` validation precedence is normative: (1) exact 24-byte request length (`BadLength`); (2) validate `create_flags` and `reserved` (`BadValue` for any nonzero value); (3) validate `fence_xid` as a create-XID (`BadIDChoice` if invalid or occupied); (4) resolve `device_xid` (`BadValue` if unknown or non-live); (5) validate live resource type, client ownership, and Device association (`BadMatch`); (6) check logical-Device state (`DEVICE_UNAVAILABLE` / `DEVICE_LOST`); (7) create the backend Fence (`ALLOCATION_FAILED` on allocation failure). A later phase MUST NOT override an earlier error. Creation is atomic: on any failure, the fence XID remains unallocated.

## `GetFenceStatus`

Request: exactly 16 bytes; device XID at offset 8 and fence XID at offset 12. Normative validation precedence is: (1) exact total length (`BadLength`); (2) resolve Device XID, then Fence XID in wire order (`BadValue` for unknown or non-live XIDs); (3) validate live resource types, client ownership, and Device association (`BadMatch`); (4) atomically snapshot the server-stored Fence state. Device Loss is not an error for this state-only query. The returned state is the value at the query's linearization point, including after Device Loss; a concurrent state transition is observed either before or after that point, never as a partially updated state.

Reply: 32 bytes.

- Byte 0: standard X11 reply `response_type`
- Byte 1: Fence-Status (`UNSIGNALED = 0`, `PENDING = 1`, `SIGNALED = 2`, `FAILED = 3`)
- Offsets 2–3: standard X11 reply sequence number
- Offsets 4–7: standard `reply.length = 0`
- Offsets 8–31: reserved for XAverius, zero

## `WaitForFence`

Request: exactly 24 bytes; any other total length results in `BadLength`.

An unknown or non-live Device or Fence XID is `BadValue`. A live XID with the wrong resource type, foreign client ownership, or a Fence associated with another Device is `BadMatch`. Device loss yields the normal reply status `DEVICE_LOST`, not an X11 error.

- Offset 8: Device-XID
- Offset 12: Fence-XID
- Offset 16: `CARD64 timeout_ns`

Normative validation precedence is: (1) exact 24-byte length (`BadLength`); (2) resolve Device XID, then Fence XID in wire order (`BadValue` for unknown or non-live XIDs); (3) validate live resource types, client ownership, and Device association (`BadMatch`); (4) inspect Device state and the Fence/wait outcome. These checks and the initial state snapshot occur before registering the wait. Device loss already established at that snapshot yields the normal reply status `DEVICE_LOST`, even if the Fence is already `FAILED`; it is not an X11 error. Otherwise, an already `SIGNALED` Fence returns `SUCCESS`, an already `FAILED` Fence returns `EXECUTION_FAILED`, and an unsignaled/pending Fence with `timeout_ns = 0` returns `TIMEOUT`, without installing a registration. For a nonzero timeout, the initial Fence/Device state check and installation of the open wait registration MUST be one atomic operation in the same serialization domain as Fence terminalization, Device Loss, timeout, and `DestroyDevice`. A completion racing this transition MUST either be visible to the initial check or observe the installed registration and terminalize it; it MUST NOT be lost between check and registration. No wait registration or retained wait-only reference may remain after a synchronous X11-error rejection.

An open wait has exactly one terminal outcome. Fence completion (`SIGNALED` or `FAILED`), timeout, Device Loss, and `DestroyDevice` MUST be serialized against one another; the first terminal transition committed while the registration is open wins and MUST NOT be overwritten by a later callback or lifecycle transition. If a Fence terminal state is committed before timeout terminalization, return `SUCCESS` or `EXECUTION_FAILED` even if reply delivery occurs after the deadline. If timeout terminalization wins first, return `TIMEOUT` even if a later Fence callback reports completion. Device Loss wins only if it is detected and committed before another terminal outcome; if it is already established when the initial check occurs, return `DEVICE_LOST` even for an already-`FAILED` Fence. If `DestroyDevice` is processed while the registration remains open and Device Loss has not already won, return `DEVICE_DESTROYED`. Late or duplicate callbacks MUST NOT send another reply, change the selected result, or release a wait reference twice. On client disconnect, cancel the registration without a reply and release its wait-only reference exactly once.

The reply is exactly 32 bytes long. Offset 8 contains a `CARD32 status`; offsets 12–31 are zero and `reply.length = 0`.

Reply status:

- `SUCCESS = 0`
- `TIMEOUT = 1`
- `EXECUTION_FAILED = 2`
- `DEVICE_LOST = 3`
- `DEVICE_DESTROYED = 4`

Timeouts and execution failures are returned as normal reply status values. `timeout_ns` uses the same monotonic deadline semantics as `WaitSemaphores`: 0 means an immediate state check without waiting, `UINT64_MAX` means infinite wait, and all other values are nanoseconds from the time the request is taken for execution. Scheduler delays MUST NOT restart the deadline; a reply may arrive after the deadline. If Fence terminalization and timeout race, `SUCCESS` or `EXECUTION_FAILED` wins if that Fence outcome commits first. If timeout terminalization wins while the wait remains open, `TIMEOUT` is returned. Device Loss returns `DEVICE_LOST` only if its terminal transition wins before another outcome; `DestroyDevice` returns `DEVICE_DESTROYED` if processed while the wait remains open and Device Loss has not already won. A later lifecycle transition MUST NOT overwrite an already committed timeout or Fence outcome. A timeout does not change Fence state.

## `ResetFence`

Request: exactly 16 bytes; device XID at offset 8 and fence XID at offset 12. Normative validation precedence is: (1) exact total length (`BadLength`); (2) resolve Device XID, then Fence XID in wire order (`BadValue` for unknown or non-live XIDs); (3) validate live resource types, client ownership, and Device association (`BadMatch`); (4) check Device state (`DEVICE_LOST`); (5) validate the mutable Fence state. Only `SIGNALED` and `FAILED` may be reset; reset from `PENDING` or `UNSIGNALED` results in `INVALID_SYNCHRONIZATION_STATE`. Earlier phases take precedence over later phases when multiple conditions are invalid. The Device-state check, Fence-state check, and reset to `UNSIGNALED` form one serialized atomic operation against submission terminalization and new `QueueSubmit` acceptance: if the Fence is `PENDING` at the operation's linearization point, reset is rejected; if terminalization has already committed `SIGNALED` or `FAILED`, reset may succeed. Rejection leaves the fence state unchanged. Each Fence has an internal, non-wire-visible use generation. A successful reset advances that generation, and accepting a new submission records its generation together with the exact internal Fence identity and submission identity. A completion/failure callback may update the Fence only if the callback wins that submission's terminal transition and its captured Fence identity, generation, and current submission association still match.

## Destroying Fences

`DestroyFence` is a void request with a fixed total length of 16 bytes: device XID at offset 8 and fence XID at offset 12.
- Offset 8: Device-XID
- Offset 12: Fence-XID Normative validation precedence is: (1) exact total length (`BadLength`); (2) resolve Device XID, then Fence XID in wire order (`BadValue` for unknown or non-live XIDs); (3) validate live resource types, client ownership, and Device association (`BadMatch`); (4) validate lifetime blockers (`INVALID_SYNCHRONIZATION_STATE`) before invalidating the public XID. Device Loss alone is not an error for this logical cleanup request and does not override an earlier validation error or the lifetime-blocker result.

A fence may be destroyed only when it is not `PENDING` and no open `WaitForFence` registration is waiting on that exact internal fence identity. While such a host wait remains open, `DestroyFence` is rejected with `INVALID_SYNCHRONIZATION_STATE`; the XID and fence state remain unchanged. A wait is no longer open once its terminal result (satisfaction, timeout, device loss, or `DestroyDevice`) has been serialized by the server; a reply still waiting in the output buffer does not prevent destruction. After successful destruction, the public XID becomes invalid immediately; internal data may be retained until all possible server accesses have ended. A fence in the `FAILED` state may be destroyed if no host wait remains registered for it.

On device loss, fences from non-terminal submissions transition to `FAILED`. Fences not associated with an affected non-terminal submission retain their last normative state; in particular, a fence that was never submitted MUST NOT be marked failed artificially. After device loss, `GetFenceStatus` remains available as a state-only query and returns the stored state (`FAILED` for submissions failed due to device loss). `WaitForFence`, however, returns `DEVICE_LOST` once device loss is detected, even if the fence is already `FAILED`, so no blocking wait continues on a lost device. `ResetFence` and new work remain rejected with `DEVICE_LOST`. For `ResetFence`, after request length and device/fence XID, type, ownership, and cross-device checks, device state is checked before fence state; a lost device therefore returns `DEVICE_LOST` even if the fence is neither `SIGNALED` nor `FAILED`. Fences in the `FAILED` state may then be destroyed normally; device-wide cascading invalidation remains independently permitted.

After device loss, no pending semaphore signal or wait operation may continue to be treated as successful. Timeline counter queries through `GetSemaphoreCounterValue`, host signals through `SignalSemaphore`, and new `QueueSubmit` operations fail with `DEVICE_LOST`. `WaitSemaphores` terminates with `DEVICE_LOST` rather than continuing to wait for a counter or returning `TIMEOUT`. If `DestroyDevice` is processed while a `WaitSemaphores` request remains open, it terminates with the X11 error `DEVICE_DESTROYED`. A semaphore state or counter MUST NOT be reported as having advanced successfully merely because a submission was internally made terminal after device loss. Semaphore and fence objects remain internally allocated while backend accesses or server-side operations still reference them; public XIDs may become invalid immediately during device-wide cascading invalidation.
