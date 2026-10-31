# v0.1 specification freeze checklist

This checklist defines the evidence required before calling the XAverius v0.1 protocol contract frozen. It separates specification completeness from implementation conformance: the latter requires a real server/backend and cannot be proven by documentation-only tests.

## Freeze scope

- The compute-baseline profile is the initial implementation target.
- The presentation-capable profile is specified separately. Its assigned requests and events do not imply support from a compute-only server.
- Wire assignments are stable for a frozen release; any later incompatible change requires an explicit protocol-version decision, not a silent edit.

## Current audit assessment — 2026-10-31

The normative request inventory, request/reply/event layouts, resource lifecycle rules, asynchronous outcomes, numeric registries, request error precedence, and cross-document conformance relationships have been audited against the current chapters, registries, request audit, reference models, and static assertions. These are content gates: they concern whether the protocol is implementable without contradictory or missing rules. Editorial consistency, including the language used in prose, is not a protocol-freeze gate unless it makes a rule ambiguous.

The last fully CI-verified specification-content checkpoint is the historical commit `0e0ced45371a2548031c4b9d1370c1dead69d724`, verified by [CI run 41109805393](https://github.com/metux/xav-design/actions/runs/41109805393): 4,721 wire-layout/documentation checks, 72 Timeline regression tests, all 673 Python tests, and the required-check presence audit passed. Subsequent Phase 3–5 normative audits on this branch corrected descriptor/pipeline contracts, queue-family/command-buffer compatibility, and DestroySemaphore validation order, and added conformance/checker assertions. GitHub reports no status checks or workflow runs for these later commits, and the tests have not been rerun on the current branch tip. Therefore the historical checkpoint is evidence for that exact commit only; the current branch is **not yet re-frozen**. The earlier resource-lifetime, pipeline/descriptor/command-buffer, QueueSubmit/destruction, final cross-document, and post-checkpoint normative-delta audits remain useful background, but the new deltas must be included in the final verification.

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

## Automated evidence at the current checkpoint (rerun on the final freeze commit)

- [x] `tools/check-wire-layout.py` passes against the exact candidate commit named in the audit record; rerun on the final freeze commit.
- [x] The complete Python test suite passes on the exact candidate commit, including golden wire vectors in both byte orders, negative request/reply cases, state models, callback identity, device-loss cleanup, semaphore reservation races, and presentation-profile contracts; rerun on the final freeze commit.
- [x] CI explicitly runs all required checks and fails if a required check is skipped or missing.
- [x] The audit record names the commit tested and describes what the checks do **not** establish.
- [x] Project status, open issues, registry counts, profile boundaries, and the test plan describe the same current state.

## Implementation acceptance gates (not documentation-only proof)

These remain open until an actual XAverius implementation exists and the evidence is captured. They are not a substitute for the normative gates above, and they must not be reported as passed based on static tests.

- [ ] Live X11/XGE interoperability: standard extension discovery, negotiated dynamic major opcode, `GEQueryVersion`, `SelectEvents`, event framing, masks, byte order, and connection isolation. Follow [the XGE interoperability plan](xge-interoperability-test-plan.md).
- [ ] End-to-end compute execution against a real Vulkan backend, including upload visibility across queues, dispatch, synchronization, readback, and resource teardown.
- [ ] Runtime concurrency and failure behavior: Device loss, late callbacks, client disconnect, delayed internal release, semaphore/fence races, and exactly-once terminal outcomes.
- [ ] If the presentation-capable profile is implemented, validate Window/Surface lifetime, swapchain creation, acquisition, presentation, resize/out-of-date, terminal events, and image release independently of event delivery.

## Freeze decision

The historical content checkpoint `0e0ced45371a2548031c4b9d1370c1dead69d724` passed its exact-commit CI, but later normative changes have been committed to the authoritative branch. The current branch is **not declared frozen yet**. Re-freeze only after the final cross-request audit includes the Phase 3–5 deltas and the checker, wire vectors, full Python suite, and required-check audit pass on one exact current-tip commit. The compute-baseline profile remains the initial implementation target. Runtime acceptance gates remain open and must not be reported as completed. Presentation remains a separately specified, optional profile.
