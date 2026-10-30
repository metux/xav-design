# Backend callback generation audit — 2026-10-30

## Result

**No real XAverius backend callback entrypoint is present in this checkout.**
The branch contains the protocol specification, Python reference/state models,
wire/conformance tests, and backend-discovery/audit utilities. It does not
contain a native XAverius backend implementation whose asynchronous callback
registration sites or callback bodies can be inspected.

This is not a pass for backend generation safety. The real-backend portion of
the audit is **blocked pending an implementation checkout**.

Evidence from the checked branch:

- The recursive repository tree contains no native backend source files
  (`.c`, `.cc`, `.cpp`, `.cxx`, `.rs`, or `.zig`) implementing XAverius.
- `tools/check-handler-ci-gate.py` deliberately reports SKIP when there are no
  tracked C/C++ sources. Its purpose is to require compile-database-backed
  handler-signature checking once native C/C++ sources are added; it does not
  establish that a backend exists.
- `tools/find-xav-backend.sh` is a discovery aid. Its Vulkan-call and X11
  handler matches identify candidate source locations, not proof that callback
  captures carry or validate generations.
- The asynchronous tests exercise Python reference models, not callback
  entrypoints compiled into or registered by a live backend.

## Required checks when backend sources are available

For every backend callback registration and entrypoint, the audit must trace
the captured values from registration to callback execution and verify:

1. **Device identity:** capture the immutable internal Device identity and
   Device generation at operation acceptance. A callback must validate that
   exact identity/generation; it must never resolve a reused Device XID or
   reusable label to the current Device.
2. **Resource identity:** capture strong references or immutable internal
   resource identities plus resource generation for every Fence, Semaphore,
   Buffer, Memory, CommandBuffer, Swapchain, and image touched by the callback.
   Validate the exact object/generation before publishing state or events.
3. **Recording identity:** every accepted backend execution hold captures the
   CommandBuffer recording epoch. Retirement must target that exact epoch;
   callback arrival order/FIFO inference is not a valid substitute.
4. **Connection identity:** callbacks capture the connection instance, not a
   client name or reusable pointer/XID. A disconnected connection suppresses
   delivery but does not skip release of the captured backend references.
5. **Exactly-once terminalization:** duplicate, late, cancelled, and
   Device-Lost callbacks must not release another operation's references,
   emit duplicate terminal events, or mutate replacement resources.
6. **Lifetime and concurrency:** verify the callback's captured references
   remain valid until backend quiescence and that callback-vs-destroy,
   callback-vs-reset/rerecord, and callback-vs-device-recreation races are
   serialized or guarded by generation checks.

The required source-level evidence is a table mapping each actual callback
registration site to its callback function, captured Device/resource/
recording/connection identities, validation point, reference-retirement path,
and a regression test that forces stale-generation delivery after XID reuse.
A source scan alone is insufficient.

## Reference-model coverage and limitation

The branch already has regression models for delayed resource callbacks,
Device-loss callbacks, QueueSubmit/QueuePresent, fences, wait registrations,
and CommandBuffer recording holds. The normative rules in
`spec/resource-lifetime.md` and `spec/command-recording.md` describe the
required lifetime/generation behavior.

These tests are useful specification regressions, but they cannot establish
that an eventual native backend captures the same identities. In particular,
the optional generation arguments in some Python model completion helpers
must not be treated as evidence that a real callback may omit its captured
generation. The backend audit must require it at every real asynchronous
entrypoint.

## Follow-up gate

Keep this item open until an implementation source tree is available and the
registration-to-entrypoint trace above has been completed. At that point,
extend CI to fail if a discovered asynchronous callback path lacks a captured
Device generation, resource generation/identity, or recording epoch, and add
native regression tests for stale callbacks after XID reuse and rerecording.
