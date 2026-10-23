# XAverius Presentation Request Audit

**Branch:** `docs/restructure-2026-10-21`  
**Audit date:** 2026-10-23  
**Scope:** Presentation requests targeting server-side X11 Windows; request error precedence, status replies, and atomic state transitions.

## Result

The checked branch currently contains only `wip/wip-2026-10-20.md` as the protocol specification. Its section 1.2 lists “Submission und Presentation” as a request family, but the specification has no presentation chapter, no seven-request definition, no presentation request registry entries, and no corresponding layouts or tests. The current central error mapping is generic and does not define presentation-specific precedence.

Therefore a request-by-request audit of seven existing definitions cannot honestly be completed from this branch state. The seven request names/layouts are not present in the checked-in specification or discoverable repository search results. This report records the concrete gap rather than inventing request names, opcodes, layouts, or status values.

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
