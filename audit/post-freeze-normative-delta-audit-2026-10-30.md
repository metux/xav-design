# Post-freeze normative delta audit — 2026-10-30

## Scope

This addendum covers the normative changes committed after the earlier content checkpoint `38587be1b70868224e8f8941750a7c1aa1e19dd7`, through specification content commit `0e0ced45371a2548031c4b9d1370c1dead69d724`. It supplements, rather than replaces, the [final cross-document audit](final-cross-document-specification-audit-2026-10-30.md).

Reviewed the current normative contracts and their corresponding error/conformance coverage in:

- `spec/presentation.md`, `spec/errors.md`, and `spec/conformance.md` for AcquireNextImage and the presentation-only copy entry;
- `spec/synchronization.md`, `spec/queue-submission.md`, `spec/memory-buffers.md`, and `spec/errors.md` for Timeline signals, queue waits, host waits, and WriteBuffer;
- `spec/devices.md`, `spec/resource-lifetime.md`, and `spec/conformance.md` for DestroyDevice, pending host waits, pending writes, and retained backend references;
- the shared semaphore reservation/lifecycle rules for QueueSubmit, QueuePresent, and AcquireNextImage;
- the central request registry and request/error audit to confirm that no wire assignment or request identity changed.

## Results

### 1. Acquire and presentation precedence

The seven presentation request assignments remain 41–47 and profile-gated. AcquireNextImage resolves all supplied XIDs and validates type/ownership/device association before Device state; Device Loss then precedes Surface Loss and Out-of-Date. Acquisition-signal eligibility and pending-acquire conflicts are checked before availability/timeout. Zero-timeout misses return NOT_READY without registration or signal. The first serialized terminal result wins for an open registration. The presentation copy entry validates entry syntax, resource identity/ownership, Device state, and resource-dependent compatibility in the documented phases; the image's mutable ACQUIRED state is checked atomically at QueueSubmit acceptance. The error summary and conformance vectors reflect these orders.

### 2. Timeline signal execution and wait eligibility

Timeline counter reservation, signal execution order, callback delivery order, and counter publication are explicitly distinct. Signal operations for one Timeline semaphore must execute in strictly increasing value order. Same-queue submission order supplies that dependency only within one queue; cross-queue and host/GPU ordering requires an explicit execution dependency. Callback delivery may be out of order only when the underlying operations executed in valid order. A reservation alone does not make a signal eligible to satisfy a queue wait; in particular, a later submission on the same queue cannot satisfy an earlier wait. The host-signal reservation checks and client ordering obligation are consistent across synchronization, queue submission, error guidance, and conformance.

### 3. WriteBuffer ordering and lifecycle

A successful WriteBuffer reply remains a device-wide ordering boundary: all earlier accepted submissions are terminal, the transfer and visibility work are complete, and later accepted submissions on any queue observe the uploaded bytes. While the earlier-submission drain is open, a later valid host SignalSemaphore remains dispatchable when it can release earlier work; later WaitSemaphores registrations keep independent timeout/terminalization; later QueueSubmit requests remain deferred and are not accepted or reserved across the upload boundary. Dependency-cycle detection considers only already-accepted, eligible signal operations. Each open write has one first-committed terminal outcome; Device Loss and DestroyDevice can terminate it, disconnect cancels reply delivery, and an already-started transfer retains/quarantines exact backend references until safe retirement. The memory, queue, device, lifetime, error, and conformance chapters agree on these boundaries.

### 4. WAIT_ANY / WAIT_ALL and host-wait lifecycle

Each entry is satisfied by its observable Timeline counter reaching its threshold. WAIT_ANY requires at least one satisfied entry; WAIT_ALL requires every entry. Partial WAIT_ALL progress remains open, does not consume counters, and cannot produce SUCCESS. The complete predicate is evaluated from a coherent snapshot in the same serialization domain as counter publication and terminalization. Initial validation/snapshot/registration is atomic against signal publication and Device Loss. A zero timeout performs one check and installs no registration; finite deadlines are not restarted; timeout, predicate success, Device Loss, and DestroyDevice compete for one terminal commit. Disconnect cancels the registration without a reply. Device teardown and resource-lifetime rules preserve a previously committed success and terminate only still-open waits.

### 5. Shared binary semaphore and callback identity

Acquire, QueueSubmit, and QueuePresent use shared binary semaphore reservation/payload state. A single confirmed wait consumes a signal; uncertain failed operations produce UNTRUSTED rather than guessed payload state. Reservation release is operation-local and exactly once. Device/resource generations and exact reservation identities prevent delayed callbacks from mutating a replacement resource after XID reuse. The resource-lifetime and queue-submit/destruction audits provide the corresponding broader acceptance/destruction checks.

## Verification

The exact specification-content candidate `0e0ced45371a2548031c4b9d1370c1dead69d724` passed CI run [41109805393](https://github.com/metux/xav-design/actions/runs/41109805393): 4,721 wire-layout/documentation checks, 72 Timeline regression tests, and all 673 Python tests passed. The companion required-check presence run [41109805402](https://github.com/metux/xav-design/actions/runs/41109805402) also passed.

These checks establish static contract consistency and reference-model regression coverage. They do not establish live X11/XGE interoperability, actual Vulkan backend ordering, or native callback-generation safety.

## Outcome and remaining gates

No unresolved contradiction was found in the reviewed post-checkpoint normative deltas, and no request ID, wire layout, or status value changed in these corrections. Together with the earlier final cross-document audit, this addendum supplies the missing review evidence for the later normative changes.

The earlier freeze metadata must therefore be advanced from the historical checkpoint `38587be1b70868224e8f8941750a7c1aa1e19dd7` to this reviewed content candidate. The remaining open work is implementation acceptance only:

1. Live X11/XGE interoperability, including dynamic opcode discovery and event delivery.
2. End-to-end compute behavior against a real Vulkan backend, including ordering, visibility, readback, and teardown.
3. Native runtime concurrency, Device Loss, late callbacks, disconnect, and backend-quiescence behavior. The current repository contains no native XAverius backend, so the backend callback-generation audit remains blocked until implementation sources are available.
4. Presentation backend validation if the optional presentation-capable profile is implemented.
