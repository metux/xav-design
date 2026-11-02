# v0.1 specification freeze checklist

This checklist defines the evidence required before calling the XAverius v0.1 protocol contract frozen. It separates specification completeness from implementation conformance: the latter requires a real server/backend and cannot be proven by documentation-only tests.

## Freeze scope

- The compute-baseline profile is the initial implementation target.
- The presentation-capable profile is specified separately. Its assigned requests and events do not imply support from a compute-only server.
- Wire assignments are stable for a frozen release; any later incompatible change requires an explicit protocol-version decision, not a silent edit.

## Current audit assessment — 2026-11-02

The normative request inventory, request/reply/event layouts, resource lifecycle rules, asynchronous outcomes, numeric registries, request error precedence, and cross-document conformance relationships have been audited against the current chapters, registries, request audit, reference models, and static assertions. These are content gates: they concern whether the protocol is implementable without contradictory or missing rules. Editorial consistency, including the language used in prose, is not a protocol-freeze gate unless it makes a rule ambiguous.

The latest verified branch baseline after integrating the local-agent WIP through PR #3 is merge commit `a6019f53fbc14f0cf2824889f14d92de6629694d`. Branch-tip CI run [41452447103](https://github.com/metux/xav-design/actions/runs/41452447103) passed the wire-layout checker, 72 Timeline regression tests, all 685 Python tests, and the required-check audit; the accompanying audit run [41452447172](https://github.com/metux/xav-design/actions/runs/41452447172) also passed. This verified baseline includes the cross-request audit of all 48 registered requests, including `QueryVersion` at subopcode 0, and the integrated memory/presentation layouts. Subsequent post-merge audit commits clarify absolute memory-reply offsets, bound `QueuePresent`'s variable wait list, and add fixed/variable request-length negative vectors plus the corrected 16-Reply inventory. GitHub status queries have not yet exposed CI results for those later direct commits; exact-tip verification is therefore pending, and this checklist does not claim those additions passed CI. The earlier protocol-content candidates `61e4e5517c94074d11cb5319f747528a8fc3f148` and `6a752174e0e4b4d455623752c8b45378ea42b1a7` remain evidence for their respective historical baselines only. Normative design was freeze-ready at the verified baseline; the post-merge audit delta must pass CI before the current branch tip is declared verified. Phase 1 ship confirmations and a named shared integration-interface owner remain project-coordination sign-offs, not unresolved wire-protocol rules.

## Normative contract gates

- [x] Every registered request has one authoritative defining chapter, a stable subopcode, request kind, exact fixed/formula length, field widths/offsets, reserved-field and padding rules, validation order, error/status mapping, atomicity, and lifecycle effects as applicable.
- [x] Every reply and XGE event has an exact layout, byte-order rules, length formula, status-dependent field requirements, and reserved-byte rules.
- [x] Every public resource has explicit ownership, create/destroy behavior, XID invalidation, internal-reference retention, pending-use restrictions, teardown behavior, and Device-loss behavior.
- [x] Every asynchronous operation defines its acceptance point, terminal outcomes, synchronization effects, event-delivery behavior, and behavior on disconnect or Device loss.
- [x] Numeric registries are unique, internally consistent, append-only, and explicit about values that are intentionally unsupported or unassigned.
- [x] Error precedence is deterministic for mixed-invalid requests. A rejected request leaves no request-attributable partial state; independent asynchronous lifecycle transitions are not rolled back.
- [x] The normative chapters, central registries, request/error matrices, conformance checklist, reference models, and static assertions agree. No historical WIP text is treated as normative.
- [x] Local document links and anchors resolve.
- [x] No unresolved v0.1 design decision remains hidden in prose. Anything intentionally deferred is labelled as future-version work or implementation-time conformance.

## Automated evidence

- [x] Historical checkpoint `0e0ced45371a2548031c4b9d1370c1dead69d724` passed its own checker, Python suite, and required-check audit; this is retained as historical evidence only and is superseded by the final content candidate below.
- [x] Reran the checker, wire vectors, complete Python suite, and required-check presence audit on protocol-content candidate `61e4e5517c94074d11cb5319f747528a8fc3f148` in [CI run 41442418120](https://github.com/metux/xav-design/actions/runs/41442418120): 4,823 checks, 72 Timeline regression tests, 685 Python tests, and all required checks passed.
- [x] Rechecked the post-migration branch tip `305b4a73bc2b21046e4f2313d272272313827143` in [CI run 41442608830](https://github.com/metux/xav-design/actions/runs/41442608830): all required checks passed.
- [x] Rechecked the PR #3 integration baseline `a6019f53fbc14f0cf2824889f14d92de6629694d` in [CI run 41452447103](https://github.com/metux/xav-design/actions/runs/41452447103): 4,823 wire-layout checks, 72 Timeline regressions, 685 Python tests, and required-check audit passed.
- [ ] Run the same required CI checks on the post-merge audit delta, including the QueuePresent count bound, fixed request-length negatives, and 16-Reply inventory correction.
- [x] The audit record names the commit tested and describes what the checks do **not** establish.
- [x] Project status, open issues, registry counts, profile boundaries, and the test plan describe the same current state.

## Implementation acceptance gates (not documentation-only proof)

These remain open until an actual XAverius implementation exists and the evidence is captured. They are not a substitute for the normative gates above, and they must not be reported as passed based on static tests.

- [ ] Live X11/XGE interoperability: standard extension discovery, negotiated dynamic major opcode, `GEQueryVersion`, `SelectEvents`, event framing, masks, byte order, and connection isolation. Follow [the XGE interoperability plan](xge-interoperability-test-plan.md).
- [ ] End-to-end compute execution against a real Vulkan backend, including upload visibility across queues, dispatch, synchronization, readback, and resource teardown.
- [ ] Runtime concurrency and failure behavior: Device loss, late callbacks, client disconnect, delayed internal release, semaphore/fence races, and exactly-once terminal outcomes.
- [ ] If the presentation-capable profile is implemented, validate Window/Surface lifetime, swapchain creation, acquisition, presentation, resize/out-of-date, terminal events, and image release independently of event delivery.

## Freeze decision

The v0.1 normative content was **freeze-ready** at the verified PR #3 integration baseline `a6019f53fbc14f0cf2824889f14d92de6629694d`; [CI run 41452447103](https://github.com/metux/xav-design/actions/runs/41452447103) passed all required static and Python checks. The post-merge audit delta on the current branch adds clarifications and negative-vector coverage, but its exact-tip CI is still pending; do not mark the current branch tip verified until that run passes. The initial implementation target remains the compute-baseline profile; presentation remains a separately specified optional profile. Runtime X11/XGE and Vulkan acceptance gates remain open. Formal implementation coordination is still pending Phase 1 agent ship confirmations and a named shared integration-interface owner on the coordination board; that is an integration sign-off, not an unresolved protocol-design decision.
