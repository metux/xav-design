# v0.1 specification freeze checklist

This checklist defines the evidence required before calling the XAverius v0.1 protocol contract frozen. It separates specification completeness from implementation conformance: the latter requires a real server/backend and cannot be proven by documentation-only tests.

## Freeze scope

- The compute-baseline profile is the initial implementation target.
- The presentation-capable profile is specified separately. Its assigned requests and events do not imply support from a compute-only server.
- Wire assignments are stable for a frozen release; any later incompatible change requires an explicit protocol-version decision, not a silent edit.

## Current audit assessment — 2026-11-04

The normative request inventory, request/reply/event layouts, resource lifecycle rules, asynchronous outcomes, numeric registries, request error precedence, and cross-document conformance relationships have been audited against the current chapters, registries, request audit, reference models, and static assertions. These are content gates: they concern whether the protocol is implementable without contradictory or missing rules. Editorial consistency, including the language used in prose, is not a protocol-freeze gate unless it makes a rule ambiguous.

The latest exact-tip CI-verified branch tip is `aaa93b0ffdea9edb1b7a82f1b7eaaaadc3ef6e29` on `docs/restructure-2026-10-21`. Workflow [41840312155](https://github.com/metux/xav-design/actions/runs/41840312155) passed 4,963 wire-layout checks, 72 Timeline regressions, 693 Python tests, shared-header compilation, XCB client prototype build, request/reply/XGE validation, backend-discovery/handler/callback audits, and required-check audit. All 19 workflow steps completed successfully. This includes the exact logical-Device PresentationRoute binding, evidence-bearing physical-removal confirmation, classified registry API results, and architecture vectors 57–58.

### Render-GPU / scanout-GPU routing audit — 2026-11-04

The presentation audit separates the logical Device's render PhysicalDevice from the Screen's scanout/display PhysicalDevice. A ScreenAttachment is topology evidence only. The selected execution provider remains responsible for its logical Device and coordinates the exact Device/Surface presentation route, which may be direct WSI or an explicit provider-managed PRIME/DRI3 import/copy/composition bridge. The route must prove format/modifier, usage, synchronization, ownership-transfer, and completion/release compatibility. No implicit migration to another PhysicalDevice, provider, Screen, or RandR output is allowed. A successful Swapchain pins one route generation; route topology changes invalidate it as OUT_OF_DATE. Static unsupported, temporary unavailable, and accepted-operation route-failure outcomes are explicitly mapped. Architecture vectors 48–54 cover these cases. No wire ABI or opcode assignments changed.

Candidate branch tip `013be364ea8cc7126b092f46d7c266b43dcda02f` is pending exact-tip CI; the prior green run does not cover this change.


### Physical-device identity evidence audit — 2026-11-04

The identity audit now defines precedence and conflict handling for authoritative platform identity, DRM primary/render-node equivalence, Vulkan `deviceUUID` correlation, derived-device instance discriminators, and provider-scoped fallback identities for software/virtual devices. It also defines ambiguous-match quarantine, immutable published identity behavior, incarnation boundaries, and stable provider-key uniqueness. Architecture vectors 36–44 cover same-device multi-ICD correlation, conflicting/duplicated UUIDs, reused BDF/incarnation, derived-device identity, provider-key ambiguity, ineligible preferred providers, and discovery-order independence. No wire ABI or request assignment changed.

Exact-tip branch commit `f6ae4c056b3621d8b491dc64aad4d361baf2c0c2` contains these normative changes and passed [workflow 41832770751](https://github.com/metux/xav-design/actions/runs/41832770751), including 4,886 wire-layout checks, 72 Timeline regressions, 693 Python tests, and all required checks.


### Provider operation contract audit — 2026-11-04

The final provider-operation inventory was checked against all registered request subopcodes 0–47 and the authoritative device, memory/buffer, shader/pipeline, command, queue, synchronization, event, and presentation chapters. The ownership map assigns every request family to either server-owned state/validation or a concrete provider-backed operation. Provider result classes, request-specific DEVICE_UNAVAILABLE mappings, protocol-acceptance boundaries, generation-safe completion tokens, destroy/retirement failures, provider quiescence, and late AcquireNextImage retirement are covered by normative rules and conformance vectors.

The synchronization ownership correction is explicit: WaitSemaphores/WaitForFence predicates, deadlines, cancellation, and first-terminal-outcome arbitration are server-owned; they have no provider wait operation or provider token. Only the underlying queue/host-signal backend operation retains provider references. AcquireNextImage remains provider-backed, with server-owned timeout arbitration and provider `cancel_acquire`; cancellation is not quiescence, and a late acquired image must be safely released or quarantined.

A final source review found stale `cancel_host_wait` and generic provider-wait wording in the architecture chapter. These were corrected in `b3ac2f2b7eeb51d8d7a785225edbe3567774ed31`; the coordination record is `feb6bbe53446580107b96cddb4e853382dbb019f`. The conformance host-wait cancellation vector already reflected the correct server-owned model and required no change. The user reports the preceding latest CI job green; exact-tip CI for the new wording correction still needs confirmation. This is a verification item, not an unresolved protocol design decision.

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
- [x] Run the required CI checks on the post-merge audit delta, including the QueuePresent count bound, fixed request-length negatives, 16-Reply inventory correction, and presentation XGE golden vectors; exact-tip run 41476931362 passed.
- [x] The audit record names the commit tested and describes what the checks do **not** establish.
- [x] Project status, open issues, registry counts, profile boundaries, and the test plan describe the same current state.

## Implementation acceptance gates (not documentation-only proof)

These remain open until an actual XAverius implementation exists and the evidence is captured. They are not a substitute for the normative gates above, and they must not be reported as passed based on static tests.

- [ ] Live X11/XGE interoperability: standard extension discovery, negotiated dynamic major opcode, `GEQueryVersion`, `SelectEvents`, event framing, masks, byte order, and connection isolation. Follow [the XGE interoperability plan](xge-interoperability-test-plan.md).
- [ ] End-to-end compute execution against a real Vulkan backend, including upload visibility across queues, dispatch, synchronization, readback, and resource teardown.
- [ ] Runtime concurrency and failure behavior: Device loss, late callbacks, client disconnect, delayed internal release, semaphore/fence races, and exactly-once terminal outcomes.
- [ ] If the presentation-capable profile is implemented, validate Window/Surface lifetime, swapchain creation, acquisition, presentation, resize/out-of-date, terminal events, and image release independently of event delivery.

## Freeze decision

The render/scanout routing contract, explicit PresentationRoute object, route create/retire operations, route-generation lifecycle, exact logical-Device route binding, evidence-bearing physical-removal API, and classified registry result enum are verified at `aaa93b0ffdea9edb1b7a82f1b7eaaaadc3ef6e29` by exact-tip [workflow 41840312155](https://github.com/metux/xav-design/actions/runs/41840312155): 4,963 wire-layout checks, 72 Timeline regressions, 693 Python tests, shared-header compilation, XCB client build, request/reply/XGE validation, and required audits.

The normative design gates are assessed as complete. The latest registry API refinements covered by exact-tip workflow 41840825348 at `3172dd2ef7579f621f3f468a6ede2028ffdf312b` include evidence-bearing physical removal, source-authority validation, generation-checked provider state transitions, and classified outcomes. Subsequent provider pointer-lifetime refinements and status-document refreshes are newer deltas and require exact-tip CI. The remaining items below are integration coordination or implementation acceptance gates, not unresolved v0.1 wire-design decisions:
- [ ] Obtain implementation-agent Phase 1 ship confirmations and name the shared registry/provider integration-interface owner.
- [ ] Validate live X11/XGE interoperability against an actual server and XAverius implementation.
- [ ] Validate end-to-end compute execution and lifecycle behavior against a real Vulkan backend.
- [ ] If the presentation-capable profile is implemented, validate its runtime Window/Surface/swapchain/acquire/present lifecycle separately.
- [ ] Preserve exact-tip CI verification after subsequent specification or checker changes.

Static CI does not prove runtime interoperability or backend conformance. No implementation work is authorized by this checklist; the current repository work remains specification-only.

### Host-wait/provider-unavailability boundary — 2026-11-04

The final cross-file provider audit now explicitly states that WaitSemaphores/WaitForFence have no provider token and do not fail solely because the selected provider becomes UNAVAILABLE. Their terminal outcomes derive from published server-visible synchronization state, timeout, exact logical-Device Loss, DestroyDevice, or disconnect. Provider failures can affect them only through state transitions actually published by the underlying operation. The stale provider-token acceptance list and ambiguous unavailability test were corrected in commits `cf20155`, `55f5f88`, and `916c140`; the coordination board records the result. This changes no wire ABI. The earlier CI evidence does not cover these commits; exact-tip CI is required before marking the new tip verified.

The static checker was extended in `9e140a7` to enforce this host-wait/provider boundary and the corrected provider-token inventory. Its execution is covered by exact-tip CI, not claimed from source inspection alone.


### Provider terminal outcome/quiescence separation — 2026-11-04

The provider lifetime contract now requires exactly one terminal outcome callback for every accepted provider token, even if successful completion or backend quiescence cannot be established. The callback carries a classified failure; it does not prove quiescence. Without proof that no later backend access is possible, the server retains/quarantines the token, resources, and provider context. Architecture and conformance vectors plus static checker assertions were added in commits `8056353`, `0fe8185`, `87bfc63`, and `3fdc226`. No wire ABI changed. The new checker and vectors require exact-tip CI execution; prior green CI does not automatically cover these commits.


### Provider token retirement result semantics — 2026-11-04

The final lifecycle audit identified one remaining precision gap: the architecture required `retire_operation` to return a classified result and required quarantine on failure, but did not state the exact condition under which `SUCCESS` authorizes reference release. The contract now makes `SUCCESS` the provider's affirmative proof that the exact token can no longer access backend objects; every non-success result preserves the token and all retained references. Retirement retry is generation-exact and idempotent, and cannot emit a second terminal callback. A dedicated conformance vector and static-checker assertions cover failure, retry, duplicate callback, stale-generation, and exactly-once release behavior. No wire ABI changes.

This update is on branch tip `0eb4e8ce2d6448b58e926bb432aba58866a58ddf` before the new commits. Exact-tip CI remains unverified; the project owner reports the latest CI job is red. The available status/workflow query returned no run records for this tip, so the failing job identity and log are not yet established. No local test suite was executed in this environment.


### CI failure analysis — workflow 41821464018 / job 126545373361 — 2026-11-04

The failing `wire-layout` step ran 4,872 checks and failed only two documentation-contract assertions. The status assertion lacked an explicit normative enum sentence in `spec/devices.md` naming `AVAILABLE`, `UNAVAILABLE`, and `REMOVED`; the separate statement that status transitions do not synthesize logical `DEVICE_LOST` already existed. The identity assertion required the exact canonical phrase `` `deviceUUID` is the preferred Vulkan cross-instance correlation value ``; the existing paragraph expressed the same rule using the fully qualified Atom name. `spec/devices.md` now states the status enum and separation explicitly and names `deviceUUID` directly while retaining the Atom mapping. This is a normative clarification only; no wire fields, opcodes, request layouts, or behavior have changed. The original job's C header compilation and client prototype tests passed; timeline and full Python tests were skipped because the wire-layout step failed. A fresh CI run is required before treating the branch as green.


### Multi-device provider unavailability scope — 2026-11-04

The provider-result audit found that `UNAVAILABLE` did not distinguish a provider-context failure from loss of one provider-local PhysicalDevice binding. Since one provider may serve several canonical PhysicalDevices, the previous wording could be implemented as an overly broad status transition. The contract now requires explicit `PROVIDER_CONTEXT` or `PHYSICAL_DEVICE` scope, affects only PhysicalDevices selected through that exact provider generation (and only the named binding for device-scoped failure), and excludes non-selected discovery providers. The abstract registry API and conformance vectors now cover both scopes and generation-safe recovery. No wire ABI change.


### PresentationRoute/provider result mapping audit — 2026-11-04

The seven presentation requests were rechecked across presentation.md, errors.md, device-registry-architecture.md, and the conformance suite. The GetSurfaceCapabilities normal-status precedence is now complete (DEVICE_LOST > DEVICE_UNAVAILABLE > SURFACE_LOST > TEMPORARILY_NOT_PRESENTABLE > SUCCESS). Capability queries are non-committing probes; CreateSwapchain creates and pins the route generation; successful public destruction does not release provider route objects until swapchain destruction and exact operation-token retirement establish quiescence. Failed preparation unwinds provider Swapchain before its provisional route; unproven retirement requires quarantine. Dedicated vectors are in [presentation-route-conformance.md](presentation-route-conformance.md).

No wire layouts, opcodes, status values, or event IDs changed. Exact-tip CI for this audit is pending; prior green CI does not cover these commits.


### Registry API result and generation contract — 2026-11-04

The registry API now requires provenance-bearing evidence to confirm physical removal, returns explicit classified outcomes for that transition, and returns classified outcomes for provider context/device unavailable and recovery transitions. Stale generations, unknown providers, and absent selected bindings are observable rejections and MUST NOT silently mutate state. The removal evidence source key is borrowed only for the call and resolved before return. This is an internal architecture/API contract; it changes no wire ABI or request assignment. The provider-state-transition return-value clarification is in `bbda0c5036306b0497cda41b825a074b6608460f`; exact-tip CI is pending.


The registry removal authority rule is also explicit: a caller cannot elevate its source by setting the evidence authority field. The registry derives or verifies the allowed authority class from the registered source, validates the exact source/observation/device generations, and rejects insufficient or stale evidence without changing status. This clarification is verified by exact-tip workflow 41840825348 at `3172dd2ef7579f621f3f468a6ede2028ffdf312b`.
