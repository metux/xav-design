# v0.1 specification freeze checklist

This checklist defines the evidence required before calling the XAverius v0.1 protocol contract frozen. It separates specification completeness from implementation conformance: the latter requires a real server/backend and cannot be proven by documentation-only tests.

## Freeze scope

- The compute-baseline profile is the initial implementation target.
- The presentation-capable profile is specified separately. Its assigned requests and events do not imply support from a compute-only server.
- Wire assignments are stable for a frozen release; any later incompatible change requires an explicit protocol-version decision, not a silent edit.

## Current audit assessment — 2026-10-30

The normative request inventory, request/reply/event layouts, resource lifecycle rules, asynchronous outcomes, numeric registries, request error precedence, and cross-document conformance relationships have been cross-checked against the current chapters, registries, request audit, reference models, and static assertions. The corresponding gates are checked below. The editorial gate remains open: the style guide requires English throughout `spec/` and `registries/`, but the current normative chapters still contain German headings and substantive German prose (notably in shaders/pipelines, resource lifetime, errors, conformance, and parts of the request-audit record. The devices headings, memory/buffers ordering prose, and queue-submission ordering/finalization prose translated in this audit must remain English). These passages must be translated and rechecked before the gate can be closed.

Automated evidence was rerun on commit `3c90c9d1e44e5c90a4155980b5ced0c261c99ec8`: the wire-layout checker passed 4,688 checks, the full Python suite passed 655 tests, and all required CI steps—including the mandatory non-skipped-check audit—succeeded in [run 41067862556](https://github.com/metux/xav-design/actions/runs/41067862556). This is not yet the freeze commit; any subsequent edits require a new exact-commit CI run.

## Normative contract gates

- [x] Every registered request has one authoritative defining chapter, a stable subopcode, request kind, exact fixed/formula length, field widths/offsets, reserved-field and padding rules, validation order, error/status mapping, atomicity, and lifecycle effects as applicable.
- [x] Every reply and XGE event has an exact layout, byte-order rules, length formula, status-dependent field requirements, and reserved-byte rules.
- [x] Every public resource has explicit ownership, create/destroy behavior, XID invalidation, internal-reference retention, pending-use restrictions, teardown behavior, and Device-loss behavior.
- [x] Every asynchronous operation defines its acceptance point, terminal outcomes, synchronization effects, event-delivery behavior, and behavior on disconnect or Device loss.
- [x] Numeric registries are unique, internally consistent, append-only, and explicit about values that are intentionally unsupported or unassigned.
- [x] Error precedence is deterministic for mixed-invalid requests. A rejected request leaves no request-attributable partial state; independent asynchronous lifecycle transitions are not rolled back.
- [x] The normative chapters, central registries, request/error matrices, conformance checklist, reference models, and static assertions agree. No historical WIP text is treated as normative.
- [x] Local document links and anchors resolve.
- [ ] Normative specification and registry text follows the English-language editorial requirement in the style guide.
- [x] No unresolved v0.1 design decision remains hidden in prose. Anything intentionally deferred is labelled as future-version work or implementation-time conformance.

## Automated evidence at the current checkpoint (rerun on the final freeze commit)

- [x] `tools/check-wire-layout.py` passes against the exact freeze commit.
- [x] The complete Python test suite passes, including golden wire vectors in both byte orders, negative request/reply cases, state models, callback identity, device-loss cleanup, semaphore reservation races, and presentation-profile contracts.
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

The protocol may be called **specification-frozen** only when all normative and automated-evidence gates above are checked and the freeze commit is recorded. Runtime acceptance gates may remain open only when they are explicitly tracked as implementation validation; they must not be described as completed. The initial implementation may then target the compute-baseline profile without implying presentation support.
