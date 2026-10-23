# XAverius Presentation Request Audit

**Branch:** `docs/restructure-2026-10-21`  
**Audit date:** 2026-10-23  
**Scope:** Presentation requests targeting server-side X11 Windows; request error precedence, status replies, and atomic state transitions.

## Result

The initial audit used an incomplete view of the active branch and incorrectly concluded that the presentation chapter was absent. Follow-up inspection of `spec/presentation.md`, `spec/errors.md`, and `spec/conformance.md` found the seven intended request definitions and their cross-chapter precedence rules. That earlier conclusion is superseded by the correction below; the request family is present, but its ABI still needed a systematic wire-length audit.

## Confirmed cross-cutting requirements

Any presentation request added to the protocol must state and test all of the following:

1. **Framing first:** malformed fixed length, variable counts, payload length, or padding is rejected as `BadLength` before resource lookup or state mutation.
2. **Reserved fields and flags:** after framing is valid, unknown flag bits and nonzero reserved fields are rejected as `BadValue`.
3. **Resource validation:** validate XID existence and type, client ownership, window ownership/validity, device association, and presentation-resource state in a documented, deterministic order. Use standard X11 errors where applicable; use `BadMatch` for valid but incompatible resource combinations.
4. **No partial effects on rejection:** validation and all synchronous preconditions complete before committing any state transition, acquiring externally visible ownership, or enqueueing work. A rejected request leaves window and presentation state unchanged.
5. **Reply semantics:** every reply-bearing request must define its exact 32-byte X11 reply header fields, payload length, status domain, and which failures are normal status replies rather than X11 errors. A status reply must not ambiguously coexist with an X11 error for the same request.
6. **Accepted asynchronous work:** once a request has been accepted and work is queued, later execution/presentation failure must be reported through the documented asynchronous mechanism; it must not retroactively become an X11 request error.
7. **X11 window semantics:** presentation must target an actual server-side X11 Window resource. Validate the window's lifecycle and any required visual/depth/size compatibility before committing. Window destruction or resize races must have explicitly defined behavior.
8. **Atomic replacement/serials:** if a request replaces a pending presentation, changes a surface/window association, or advances a present serial, specify the exact commit point and rollback behavior. Serials must not advance on rejected requests.
9. **Ordering:** define the order relative to earlier X11 requests, earlier XAverius requests, and GPU completion. X11 request processing order alone must not be described as GPU completion.
10. **Tests:** include one test per precedence pair (bad framing plus invalid XID; reserved bits plus invalid state; wrong ownership plus unsupported state), plus rejection atomicity, accepted async failure, window destruction, and resize/reconfiguration races.

## Required next correction

Before editing the normative protocol, recover or restore the intended seven presentation request names and their agreed wire layouts. Then add a dedicated presentation chapter and registry rows, map each request's errors/status reply/atomic transition, and add automated consistency checks. Numeric subopcodes must remain `UNASSIGNED` until the registry allocation policy is finalized.

## Branch safety

No changes to `master` are intended. This audit report does not claim that the missing seven request definitions have been implemented or that the presentation ABI is ready to freeze.


## Follow-up correction — 2026-10-23

The active branch already defines these seven presentation requests: CreateSurface, DestroySurface, GetSurfaceCapabilities, CreateSwapchain, DestroySwapchain, AcquireNextImage, and QueuePresent. The numeric subopcodes remain intentionally unassigned. The request names and base semantics were therefore retained; no alternative request family was invented.

The first concrete ABI inconsistency found was in the presentation chapter's section 10 headings: GetSurfaceCapabilities and AcquireNextImage headings described the request size as a reply size, CreateSwapchain was labeled “Reply, 48 bytes” despite defining a 48-byte request and a 40-byte reply, and QueuePresent was labeled as a variable-length reply despite its variable-length request and fixed 36-byte reply. These headings have been corrected, and an explicit seven-request request/reply length matrix has been added to the presentation and conformance chapters.

Verified framing matrix:
- CreateSurface: 16-byte request, no reply.
- DestroySurface: 12-byte request, no reply.
- GetSurfaceCapabilities: 16-byte request, reply size 64 bytes plus variable records.
- CreateSwapchain: 48-byte request, 40-byte reply.
- DestroySwapchain: 12-byte request, no reply.
- AcquireNextImage: 32-byte request, 44-byte reply.
- QueuePresent: request size 40 + 4 × wait_semaphore_count bytes, fixed 36-byte reply.

The normative error-precedence rules already cover framing before scalar validation, scalar validation before XID resolution, XID/type/ownership validation before lifecycle and mutable-state checks, and atomic acceptance/rejection. The conformance chapter now explicitly requires byte-length, reply.length, reserved-field, status-field, mixed-failure precedence, and atomic-state tests for all seven requests.

This follow-up does not assign subopcodes or claim the presentation ABI is frozen. Remaining work is to execute/verify the repository's static checker and CI against the corrected source, resolve any semantic conflicts it exposes, and only then consider registry allocation.
