# v0.1 specification freeze checklist

This checklist defines the evidence required before calling the XAverius v0.1 protocol contract frozen. It separates specification completeness from implementation conformance: the latter requires a real server/backend and cannot be proven by documentation-only tests.

## Freeze scope

- The compute-baseline profile is the initial implementation target.
- The presentation-capable profile is specified separately. Its assigned requests and events do not imply support from a compute-only server.
- Wire assignments are stable for a frozen release; any later incompatible change requires an explicit protocol-version decision, not a silent edit.

## Current audit assessment — 2026-11-05

The normative request inventory, request/reply/event layouts, resource lifecycle rules, asynchronous outcomes, numeric registries, request error precedence, and cross-document conformance relationships have been audited against the current chapters, registries, request audit, reference models, and static assertions. These are content gates: they concern whether the protocol is implementable without contradictory or missing rules. Editorial consistency, including the language used in prose, is not a protocol-freeze gate unless it makes a rule ambiguous.

The latest exact-tip CI-verified branch tip is `a66d977b436cb05818a07a847e7c4fc1e8065598` on `docs/restructure-2026-10-21`. Wire-layout/request-reply/XGE workflow [41846198875](https://github.com/metux/xav-design/actions/runs/41846198875) and required-check workflow [41846198977](https://github.com/metux/xav-design/actions/runs/41846198977) both passed. This includes vectors 76–78, multi-DDX backend ownership vectors 79–88, and DDX backend registration, generation allocation, module-lease, and finalization/quiescence vectors 89–96. These results establish static/specification consistency only; they do not establish live Xlibre/X11/Vulkan runtime conformance.

### Render-GPU / scanout-GPU routing audit — 2026-11-04

The presentation audit separates the logical Device's render PhysicalDevice from the Screen's scanout/display PhysicalDevice. A ScreenAttachment is topology evidence only. The selected execution DDX backend remains responsible for its logical Device and coordinates the exact Device/Surface presentation route, which may be direct WSI or an explicit DDX backend-managed PRIME/DRI3 import/copy/composition bridge. The route must prove format/modifier, usage, synchronization, ownership-transfer, and completion/release compatibility. No implicit migration to another PhysicalDevice, DDX backend, Screen, or RandR output is allowed. A successful Swapchain pins one route generation; route topology changes invalidate it as OUT_OF_DATE. Static unsupported, temporary unavailable, and accepted-operation route-failure outcomes are explicitly mapped. Architecture vectors 48–54 cover these cases. No wire ABI or opcode assignments changed.

Candidate branch tip `013be364ea8cc7126b092f46d7c266b43dcda02f` is pending exact-tip CI; the prior green run does not cover this change.


### Physical-device identity evidence audit — 2026-11-04

The identity audit now defines precedence and conflict handling for authoritative platform identity, DRM primary/render-node equivalence, Vulkan `deviceUUID` correlation, derived-device instance discriminators, and DDX backend-scoped fallback identities for software/virtual devices. It also defines ambiguous-match quarantine, immutable published identity behavior, incarnation boundaries, and stable DDX backend-key uniqueness. Architecture vectors 36–44 cover same-device multi-ICD correlation, conflicting/duplicated UUIDs, reused BDF/incarnation, derived-device identity, DDX backend-key ambiguity, ineligible preferred providers, and discovery-order independence. No wire ABI or request assignment changed.

Exact-tip branch commit `f6ae4c056b3621d8b491dc64aad4d361baf2c0c2` contains these normative changes and passed [workflow 41832770751](https://github.com/metux/xav-design/actions/runs/41832770751), including 4,886 wire-layout checks, 72 Timeline regressions, 693 Python tests, and all required checks.


### DDX backend operation contract audit — 2026-11-04

The final DDX backend-operation inventory was checked against all registered request subopcodes 0–47 and the authoritative device, memory/buffer, shader/pipeline, command, queue, synchronization, event, and presentation chapters. The ownership map assigns every request family to either server-owned state/validation or a concrete DDX backend-backed operation. DDX backend result classes, request-specific DEVICE_UNAVAILABLE mappings, protocol-acceptance boundaries, generation-safe completion tokens, destroy/retirement failures, DDX backend quiescence, and late AcquireNextImage retirement are covered by normative rules and conformance vectors.

The synchronization ownership correction is explicit: WaitSemaphores/WaitForFence predicates, deadlines, cancellation, and first-terminal-outcome arbitration are server-owned; they have no DDX backend wait operation or DDX backend token. Only the underlying queue/host-signal backend operation retains DDX backend references. AcquireNextImage remains DDX backend-backed, with server-owned timeout arbitration and DDX backend `cancel_acquire`; cancellation is not quiescence, and a late acquired image must be safely released or quarantined.

A final source review found stale `cancel_host_wait` and generic DDX backend-wait wording in the architecture chapter. These were corrected in `b3ac2f2b7eeb51d8d7a785225edbe3567774ed31`; the coordination record is `feb6bbe53446580107b96cddb4e853382dbb019f`. The conformance host-wait cancellation vector already reflected the correct server-owned model and required no change. The user reports the preceding latest CI job green; exact-tip CI for the new wording correction still needs confirmation. This is a verification item, not an unresolved protocol design decision.

### Logical/DDX backend-native Surface audit — 2026-11-04

The presentation request and DDX backend API were cross-checked for multi-GPU semantics. CreateSurface is now explicitly server-only: it captures the exact Window/Screen identity and does not choose a DDX backend. DDX backend-native Surfaces are materialized lazily for the DDX backend generation selected by the exact logical Device, keyed by DDX backend generation plus logical Surface generation. The wrapper may be reused by Devices served by the same DDX backend generation but cannot cross DDX backend generations. DestroySurface retires all materialized wrappers after their users drain. UNSUPPORTED native creation maps to a valid capability result with no present-capable queue. Vectors 165–168 cover scope, lazy creation, unsupported mapping, and teardown; vector 169 checks that the DDX backend capability result does not invent transform/composite-alpha wire fields; vector 170 checks DDX backend-generation teardown without logical Surface invalidation or Device failover. No wire ABI changed; exact-tip CI for these additions is pending.

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

The normative design gates are assessed as complete. The latest registry API refinements covered by exact-tip workflow 41840947750 at `53883de2201029de82b63a03f6acc2ba77280e6a` include evidence-bearing physical removal, source-authority validation, generation-checked DDX backend state transitions, and classified outcomes. The DDX backend pointer-lifetime refinements and architecture vector 60 are also covered by exact-tip workflow 41840947750. The subsequent status-document refreshes are newer documentation-only deltas and require exact-tip CI. The remaining items below are integration coordination or implementation acceptance gates, not unresolved v0.1 wire-design decisions:
- [ ] Obtain implementation-agent Phase 1 ship confirmations and name the shared registry/DDX backend integration-interface owner.
- [ ] Validate live X11/XGE interoperability against an actual server and XAverius implementation.
- [ ] Validate end-to-end compute execution and lifecycle behavior against a real Vulkan backend.
- [ ] If the presentation-capable profile is implemented, validate its runtime Window/Surface/swapchain/acquire/present lifecycle separately.
- [ ] Preserve exact-tip CI verification after subsequent specification or checker changes.

Static CI does not prove runtime interoperability or backend conformance. No implementation work is authorized by this checklist; the current repository work remains specification-only.

### Host-wait/DDX backend-unavailability boundary — 2026-11-04

The final cross-file DDX backend audit now explicitly states that WaitSemaphores/WaitForFence have no DDX backend token and do not fail solely because the selected DDX backend becomes UNAVAILABLE. Their terminal outcomes derive from published server-visible synchronization state, timeout, exact logical-Device Loss, DestroyDevice, or disconnect. DDX backend failures can affect them only through state transitions actually published by the underlying operation. The stale DDX backend-token acceptance list and ambiguous unavailability test were corrected in commits `cf20155`, `55f5f88`, and `916c140`; the coordination board records the result. This changes no wire ABI. The earlier CI evidence does not cover these commits; exact-tip CI is required before marking the new tip verified.

The static checker was extended in `9e140a7` to enforce this host-wait/DDX backend boundary and the corrected DDX backend-token inventory. Its execution is covered by exact-tip CI, not claimed from source inspection alone.


### DDX backend terminal outcome/quiescence separation — 2026-11-04

The DDX backend lifetime contract now requires exactly one terminal outcome callback for every accepted DDX backend token, even if successful completion or backend quiescence cannot be established. The callback carries a classified failure; it does not prove quiescence. Without proof that no later backend access is possible, the server retains/quarantines the token, resources, and DDX backend context. Architecture and conformance vectors plus static checker assertions were added in commits `8056353`, `0fe8185`, `87bfc63`, and `3fdc226`. No wire ABI changed. The new checker and vectors require exact-tip CI execution; prior green CI does not automatically cover these commits.


### DDX backend token retirement result semantics — 2026-11-04

The final lifecycle audit identified one remaining precision gap: the architecture required `retire_operation` to return a classified result and required quarantine on failure, but did not state the exact condition under which `SUCCESS` authorizes reference release. The contract now makes `SUCCESS` the DDX backend's affirmative proof that the exact token can no longer access backend objects; every non-success result preserves the token and all retained references. Retirement retry is generation-exact and idempotent, and cannot emit a second terminal callback. A dedicated conformance vector and static-checker assertions cover failure, retry, duplicate callback, stale-generation, and exactly-once release behavior. No wire ABI changes.

This update is on branch tip `0eb4e8ce2d6448b58e926bb432aba58866a58ddf` before the new commits. Exact-tip CI remains unverified; the project owner reports the latest CI job is red. The available status/workflow query returned no run records for this tip, so the failing job identity and log are not yet established. No local test suite was executed in this environment.


### CI failure analysis — workflow 41821464018 / job 126545373361 — 2026-11-04

The failing `wire-layout` step ran 4,872 checks and failed only two documentation-contract assertions. The status assertion lacked an explicit normative enum sentence in `spec/devices.md` naming `AVAILABLE`, `UNAVAILABLE`, and `REMOVED`; the separate statement that status transitions do not synthesize logical `DEVICE_LOST` already existed. The identity assertion required the exact canonical phrase `` `deviceUUID` is the preferred Vulkan cross-instance correlation value ``; the existing paragraph expressed the same rule using the fully qualified Atom name. `spec/devices.md` now states the status enum and separation explicitly and names `deviceUUID` directly while retaining the Atom mapping. This is a normative clarification only; no wire fields, opcodes, request layouts, or behavior have changed. The original job's C header compilation and client prototype tests passed; timeline and full Python tests were skipped because the wire-layout step failed. A fresh CI run is required before treating the branch as green.


### Multi-device DDX backend unavailability scope — 2026-11-04

Historical audit note (superseded by the direct DDX-binding model below): the earlier provider-object API used `PROVIDER_CONTEXT` and `PHYSICAL_DEVICE` scopes. Those names are not current enum values or API concepts. The current contract uses `MODULE_ROLE` for shared module-lifetime failures and `PHYSICAL_DEVICE` for one exact selected binding; the affected-device set is derived from the selected bindings that retain that module-role generation. The current conformance vector uses these scopes and does not model non-selected discovery providers. No wire ABI change.


### PresentationRoute/DDX backend result mapping audit — 2026-11-04

The seven presentation requests were rechecked across presentation.md, errors.md, device-registry-architecture.md, and the conformance suite. The GetSurfaceCapabilities normal-status precedence is now complete (DEVICE_LOST > DEVICE_UNAVAILABLE > SURFACE_LOST > TEMPORARILY_NOT_PRESENTABLE > SUCCESS). Capability queries are non-committing probes; CreateSwapchain creates and pins the route generation; successful public destruction does not release DDX backend route objects until swapchain destruction and exact operation-token retirement establish quiescence. Failed preparation unwinds DDX backend Swapchain before its provisional route; unproven retirement requires quarantine. Dedicated vectors are in [presentation-route-conformance.md](presentation-route-conformance.md).

No wire layouts, opcodes, status values, or event IDs changed. Exact-tip CI for this audit is pending; prior green CI does not cover these commits.


### Registry API result and generation contract — 2026-11-04

The registry API now requires provenance-bearing evidence to confirm physical removal, returns explicit classified outcomes for that transition, and returns classified outcomes for DDX backend context/device unavailable and recovery transitions. Stale generations, unknown providers, and absent selected bindings are observable rejections and MUST NOT silently mutate state. The removal evidence source key is borrowed only for the call and resolved before return. This is an internal architecture/API contract; it changes no wire ABI or request assignment. The DDX backend-state-transition return-value clarification is in `bbda0c5036306b0497cda41b825a074b6608460f`; exact-tip CI is pending.


The registry removal authority rule is also explicit: a caller cannot elevate its source by setting the evidence authority field. The registry derives or verifies the allowed authority class from the registered source, validates the exact source/observation/device generations, and rejects insufficient or stale evidence without changing status. This clarification is verified by exact-tip workflow 41840947750 at `53883de2201029de82b63a03f6acc2ba77280e6a`.


### Xlibre/Xorg integration contract — 2026-11-04

The registry architecture now specifies distinct platform-discovery, DDX-topology, and Vulkan-DDX backend adapter roles; a startup barrier that does not wait for Screens; hotplug subscription/scan reconciliation; explicit behavior for failed and late discovery sources; and generation-safe Screen/module teardown. The combined contract and vectors 61–66 passed exact-tip workflow 41842074182 at `4eb0d35938def3f74de579a7bb2e7729a304325f` (4,963 wire checks, 72 Timeline tests, 693 Python tests, all required audits). A non-normative source mapping to XLibre master and vectors 67–69 are newer and pending exact-tip CI. This closes a normative integration-architecture gap, not the runtime Xlibre conformance gate.


### XLibre source-level integration mapping — 2026-11-04

The architecture guidance now maps the registry contract to the current XLibre startup and hotplug flow. It identifies the early `xf86BusProbe()`/`xf86platformProbe()` discovery path, the `card*`-only udev enumeration limitation, DDX GPU-Screen add/remove as topology lifecycle, and the Xorg first-platform-device primary fallback. XAverius must not derive identity or default-device policy from those conventions. Source-mapping commit `d070c735c3057940c00ac42c1dd0d443363e1fef` and follow-up vectors 67–69 (`a90544633e8a9c477ea380ecbac7ee24b27f2653`) are pending exact-tip CI.


### XLibre DDX Screen-close and DDX backend-module quiescence audit — 2026-11-04

The source-level lifecycle was checked against XLibre commit `ee4bb3f96eec3b21c1961d54fe45cb33dc402d00`: GPU-screen removal executes `dixScreenRaiseClose()`, `RemoveGPUScreen()`, and `xf86DeleteScreen()`; the latter invokes `FreeScreen()`, drops the `ScrnInfo` module reference, and decrements the driver's Screen reference count. None of these operations proves that asynchronous DDX backend callbacks/workers have stopped. The normative contract therefore requires a DDX module-role/module lease independent of Xorg's Screen references; exact ScreenAttachment detach; separation of Screen and shared-DDX backend lifetimes; per-token retirement including callback return; and module-role-wide quiescence before module unload. The module-role `quiesce_module_role` hook returns PENDING/SUCCESS/FAILURE; only SUCCESS proves no callback or worker can enter DDX module code again. Failure or unproven quiescence requires quarantine. Architecture vectors 70–75 cover close with shared providers, module lease independence, callback/retire races, DDX backend-wide worker drain, and cross-module bridge callbacks. The Screen-close contract commit `03253eef3631ff3faf7fbaa55611d5d13388c4a5` passed workflow 41843032895; vector commit `5e213d62a116fe2c785c9ba5513a8129f3a4eda0` passed workflow 41843046752. The follow-up DDX backend ABI hook commit `5d3c0f69e715a8a0e89b1217e6101c2b1500da21` is pending exact-tip CI. No wire assignments or client-visible ABI changed.


The loader-specific refinement in §8.1 and vectors 76–77 distinguishes Xorg's duplicated `ModuleDesc` from a true DDX backend module lease: `DuplicateModule()` shares the handle, duplicated descriptors skip `LoaderUnload()`, and the original unload path reaches `dlclose()`. `DriverPtr.refCount` counts Screen use, not asynchronous DDX backend references. The separate DDX backend/module pin is therefore mandatory. Commit `3a42c1a63e68016d952f91542b858fee3d35d300` awaits exact-tip CI.


The DDX backend-wide quiescence ABI refinement at `5d3c0f69e715a8a0e89b1217e6101c2b1500da21` passed exact-tip workflow 41843078578: all 19 steps, 4,963 wire-layout checks, 72 Timeline regressions, 693 Python tests, and all required audits. The follow-up XLibre loader-source mapping and vectors 76–77 at `3a42c1a63e68016d952f91542b858fee3d35d300` are newer and pending exact-tip CI.


The final Screen-pointer safety clarification adds architecture vector 78: asynchronous DDX backend callbacks may use only copied immutable data or a detached generation-checked ScreenAttachment context, never raw `ScreenPtr`/`ScrnInfoPtr` or `FreeScreen()`-owned storage after Screen close. Commit `6f01fcb00e9c6ac46cad72e0c52434494e814413` and subsequent summary updates are pending exact-tip CI.


### Multi-DDX backend ownership and module-lease audit — 2026-11-04

The registry architecture now explicitly defines DDX backend/binding/module cardinality and ownership. A DDX backend generation may bind multiple PhysicalDevices; one PhysicalDevice may have multiple DDX backend bindings; and one loaded module may own multiple independently quiesced DDX backend generations and adapter roles. Each DDX backend-generation/PhysicalDevice-incarnation pair has at most one executable binding. Discovery observations remain source-owned and cannot be withdrawn by another source's teardown.

The v0.1 execution rule is unchanged: one selected DDX backend and one immutable snapshot per published PhysicalDevice. Non-selected providers do not contribute capabilities or metadata and cannot take over after selected-DDX backend loss or unregister. Selected binding removal makes the PhysicalDevice UNAVAILABLE; physical removal remains a separate evidence-bearing terminal transition.

DDX backend shutdown now explicitly closes admission for one exact DDX backend generation before removing its bindings, withdrawing only its own observations/ScreenAttachments, draining accepted operations, and quiescing that DDX backend. A shared module remains pinned until every DDX backend generation and adapter role backed by it has independently retired. Architecture vectors 79–88 cover multi-DDX backend ownership, same-module multiple providers, source-local withdrawal, no-failover behavior, DDX backend-local alias deduplication, and competing teardown orders.

The latest verified exact-tip baseline before this refinement is `ceac0d09dc7e9456e372ae52cea97d46007697fc`, passed by [workflow 41843634177](https://github.com/metux/xav-design/actions/runs/41843634177). The multi-DDX backend refinement is commit `c88668e023ba31fa38293dba4aef5a827adedb64`; exact-tip CI [41844488352](https://github.com/metux/xav-design/actions/runs/41844488352) is pending. No wire assignments or client-visible ABI changed.


### DDX backend registration and final module-lease lifecycle — 2026-11-04

The internal API sketch now separates DDX backend-generation registration from DDX backend-local PhysicalDevice binding registration. A DDX backend descriptor/context/module lease is installed once per DDX backend generation; bindings refer to the existing DDX backend object. The server assigns the DDX backend generation. One server-owned module lease is shared by DDX backend generations and adapter roles belonging to the same loaded module. DDX backend shutdown, quiescence, and finalization are distinct: quiescence stops DDX backend-internal workers after externally initiated calls and accepted tokens have drained; PENDING/FAILURE retain the lease; SUCCESS alone is insufficient to release it while logical-device/DDX backend-object references remain. Final DDX backend-context release runs before the last lease release. Vectors 89–93 cover descriptor/reference counts, admission rejection, shared module pinning, PENDING/FAILURE/SUCCESS, and blocked finalization. Commits `1029787cbf4b7d3f0b8675264e39e9c4527da754` and `63c5339ca702a913f7da55747e877177782492a5`; exact-tip CI pending. No wire ABI or opcode assignments changed.


The follow-up quiescence ordering review adds two further requirements: every DDX backend-owned object needing DDX backend code must be destroyed or quarantined before quiescence SUCCESS, and after SUCCESS only the registry-controlled final `release_module_role` call may enter module code. Module-lease creation must acquire a real loader pin through a stable server-owned module-owner record; a duplicated `ModuleDesc`, `ScrnInfo`, or `DriverPtr` is insufficient. DDX backend generations are reserved by the registry and consumed even when later registration fails. Vectors 94–96 cover these cases. Commit `dc6c8589f7961b587f37a97cc2f4e76c67f8d627`; exact-tip CI pending.


The final `GpuRegistryAttachScreen()` API comment clarification (borrowed `ScreenPtr`, never retained by the registry) is included in exact-tip `a66d977b436cb05818a07a847e7c4fc1e8065598`; both required workflows 41848200892 and 41848200803 passed.


### Registry API ownership/error audit — 2026-11-04

A focused review found missing result contracts and ownership rules in the internal registry API sketch. Section 7 now specifies output initialization, classified errors, retained references, atomic rollback, server-assigned generations, discovery-source and module-role registration, DDX backend binding identity, retryable detach/unregister/quiescence, XID publication transactionality, DDX backend object/output ownership, and accepted asynchronous token/completion semantics. New architecture vectors 97–114 exercise these cases. These edits are pending exact-tip CI; the last fully verified baseline remains `a66d977b436cb05818a07a847e7c4fc1e8065598` with workflows [41848200892](https://github.com/metux/xav-design/actions/runs/41848200892) and [41848200803](https://github.com/metux/xav-design/actions/runs/41848200803). This is an internal implementation-contract audit; no wire ABI or opcode assignment changed.


The API audit was extended to close the asynchronous token lifecycle: `PrepareOperation`, `CommitOperationSubmission`, `RejectOperationSubmission`, and `RetireOperationToken` now define server-assigned token identity, admission linearization, early callback buffering, synchronous failure rejection, and per-token retirement/quarantine. Architecture vectors 115–119 cover admission races, callback-before-commit, invalid late callbacks, retirement outcomes, and teardown races. These changes are pending exact-tip CI; no wire layout or opcode changed.


### DDX backend API second-pass audit — 2026-11-04

Section 7 now also specifies DDX backend candidate-list ownership, DDX backend-local binding-ID/native-handle mapping, exact binding identity in Device/Surface operations, all six asynchronous DDX backend operation kinds, complete per-token resource pin sets, call-scoped token pointer semantics, operation-specific status codes, completion payload bounds, and shutdown admission closure. Section 8.3 contains implementation guidance. Architecture vectors 120–131 cover candidate-list release, native handle retention, context access, async operation coverage, multi-resource submissions, status validation, and completion payload validation. Exact-tip CI pending; no wire ABI/opcode changed.


Completion records now carry both DDX backend-local binding ID and registry binding generation; vector 132 checks stale binding rejection. DDX backend-device wrapper retain/release is explicitly distinct from native logical-device destruction, and typed operation tables must follow the common result/output/token contract.


DDX backend availability notifications are now sequence-checked per context/binding scope and binding-scoped notifications include exact binding_generation. Discovery source events and removal evidence carry source_event_sequence. Effective availability composes independent context/binding/physical state; caller-provided removal authority is forbidden. Architecture vectors 133–137 cover these ordering rules. Exact-tip CI pending.


All current asynchronous operation kinds require an exact logical-Device generation and a complete nonempty resource pin set. QueueSubmit pins its entire validated dependency graph; presentation pins the exact Swapchain and all backend-accessible route/image/synchronization objects. Vector 138 checks incomplete pin sets and atomic rejection.


GPU_BACKEND_FATAL and server-detected DDX backend-contract violations quarantine the DDX module-role generation and prohibit normal finalization; DEVICE_LOST is logical-Device scoped; CANCELLED is only an accepted operation's terminal result. Vector 139 checks the distinctions.


Retain admission closes at DDX backend shutdown/quarantine, ModuleRole unregister, and ScreenAttachment detach; existing references remain releasable. Operation-token and DDX backend finalization calls have explicit repeat/idempotence behavior. Vector 140 covers these transitions.


Repeated successful ObserveDevice calls with identical source event sequence/payload return the same observation ID and one additional caller-owned PhysicalDevice reference per call, without duplicating the observation. Vector 141 checks balanced releases.


After GPU_BACKEND_FATAL quarantine, `GpuRegistryTryQuiesceModuleRole` and `GpuRegistryFinalizeModuleRoleShutdown` must return QUARANTINED without entering DDX backend code or dropping references. Vector 142 covers this barrier.

### Registry API lifetime audit delta — 2026-11-04

The registry API audit addendum in [registry-api-lifetime-addendum.md](registry-api-lifetime-addendum.md) supplements §7/§7.1 with DDX backend-context accessor lifetime, nested operation-table storage lifetime, shared module-lease identity and final-release semantics, exact source/binding/Screen removal barriers, DDX backend-quiescence preconditions, and token-pointer confinement. Architecture vectors 143–150 were added. This is an internal server architecture contract and changes no wire ABI. Exact-tip CI and runtime acceptance remain distinct gates.

### DDX backend operation-table audit delta — 2026-11-04

The DDX backend operation matrix now defines concrete typed operations for all four DDX backend sub-tables and an exhaustive request 0–47 ownership map. It adds Buffer `free_buffer`, create/destroy symmetry, six-operation async classification, output/rollback rules, full resource pin sets, surface capability result completeness, and DDX backend-result invariants. See [DDX backend operation matrix](provider-operation-matrix.md), vectors 151–164. Exact-tip CI and implementation/runtime acceptance remain separate gates.

### DDX registration and direct device dispatch — 2026-11-04

- [ ] Confirm every DDX registers all PhysicalDevices it serves, including headless/render-only/compute-only devices without ScreenAttachments.
- [ ] Confirm platform/udev is identity/hotplug evidence only and does not create a competing executable-device inventory.
- [ ] Confirm operation vectors, per-device context, and native handle are directly bound to the selected PhysicalDevice binding; no second DDX backend-object lookup occurs on each request.
- [ ] Confirm any shared module-role control record exists only for module lease, callback admission/quiescence, and shared lifetime—not as a redundant per-device dispatch layer.
- [ ] Confirm duplicate DDX claims are canonicalized without merging snapshots, contexts, or operation tables.
- [ ] Confirm ScreenAttachment teardown is independent of DDX device-binding and module lifetime.

See `implementation-notes/ddx-device-registration.md`. Exact-tip CI and implementation-agent source review are pending.

- [ ] Confirm no generic module-role context accessor exists; per-device context/native handles are passed directly through the selected binding.

### DDX binding API cleanup — 2026-11-04

- [ ] Confirm the DDX enumerates and registers every PhysicalDevice it serves through `GpuRegistryRegisterDdxDevice`.
- [ ] Confirm no registry-side Vulkan ICD candidate enumeration or DDX-local numeric ID-to-native-handle map remains.
- [ ] Confirm the PhysicalDevice binding is the direct dispatch target and the module role is lifetime/quiescence bookkeeping only.
- [ ] Confirm no generic module-role context accessor or provider-object acquisition API remains.
- [ ] Confirm all callback, completion, error-scope, and Surface cache identities use exact binding and module-role generations.

Exact-tip CI and implementation-agent source review are pending.


### Follow-up DDX binding consistency audit — 2026-11-04

The second pass removed residual registry-side candidate-list/backend-key ranking APIs from §8.2 and updated conformance vectors 42–44 and 88–90 to exercise direct per-device registration and module-role shutdown. The final deterministic selection rule is now an explicit server-configured ordered preference over stable DDX device-registration module-role owner_key values; no DDX-provided priority or separate provider object is introduced. With no matching preference, one eligible binding may be selected; multiple eligible unlisted bindings remain unpublished as ambiguous. The API contract names `GpuPhysicalDeviceAcquireBackendBinding` as the exact binding acquisition operation. Historical provider-object vectors and status entries remain only as superseded audit history; they are not current API requirements. Exact-tip CI and implementation-agent source review remain pending.

### DDX registration/discovery boundary correction — 2026-11-05

A focused review of the registry architecture found residual wording that could be read as permitting Vulkan-loader enumeration to act as an independent discovery/registration source, and an obsolete split between candidate discovery and DDX backend attachment. The architecture now states the single boundary consistently: platform sources contribute identity/hotplug observations; each DDX enumerates and submits complete per-device registrations containing identity, native handle, per-device context, and typed operation vectors; the registry stages these complete registrations until the publication barrier and selects/publishes one complete binding. It does not expose a candidate-list or second attachment/dispatch API. The same pass clarified that a later DDX pass may publish a device that was never published, but cannot recover a withdrawn binding through a different registration generation.

Architecture commits: `e267463711141aef86ec7fd0dc0913afa66f3660`, `efd2c8be5056da52cc31be2090985cd2ef2cb7cd`, and `e1f9c27736ab63c7c3a7cbed750074e241e0b604`. No wire ABI, request assignment, event ID, or client-visible behavior changed. Exact-tip CI has not yet been verified; do not treat this delta as green until the required workflows complete. This is a normative server-architecture consistency correction, not authorization to begin Xserver implementation or to change the Phase 0 gate.

The same audit found one conformance vector still using the superseded `PROVIDER_CONTEXT` scope and a non-selected discovery-provider scenario. It now tests `MODULE_ROLE` versus exact `PHYSICAL_DEVICE` binding scope using two PhysicalDevices selected through one role and a third selected through another role. The historical checklist entry has been explicitly labelled obsolete; no current conformance requirement uses the old provider enum. Conformance update: `8a8611e7803774d7b9f0df9b41062a3f0a5c3529`; historical terminology clarification: `8ef523b383ba31f6b532d4b67e817d01e95819d3`.

### Registry API and four-table operation audit — 2026-11-05

The API/signature/lifetime audit found and corrected several cross-document gaps without changing the wire ABI, request assignments, event IDs, or Vulkan capability set:

- Native DDX Surface wrappers and unsupported-result cache entries are keyed by exact selected binding generation plus logical Surface generation, not module-role generation. This is required because per-device native instance/context lives on the binding and one module role may own multiple independent bindings.
- PresentationRoute wrappers now explicitly retain their exact backend Device wrapper; Swapchain wrappers retain their exact Device/route dependencies. Native destruction order is Swapchain, then route, then logical Device. A route cannot be destroyed while a Swapchain or accepted operation still references it.
- The registry copies operation-table descriptors by value, while native handles and per-device context remain borrowed DDX-owned opaque values. The DDX must keep those values and its function targets alive through exact binding removal and module-role quiescence; the registry never frees DDX-owned context/handles.
- Async completion uses one server-exported process-lifetime GpuBackendCompletionDispatch; no per-binding completion sink or userdata pointer is installed. The DDX calls it exactly once for each accepted token and keeps the completion structure/payload valid until return. Dispatch copies into per-token storage reserved by GpuRegistryPrepareOperation. Only ReadBuffer bytes and the AcquireNextImage CARD32 image index have nonzero v0.1 completion payloads; DDX-owned worker/callback code and its own userdata remain pinned until binding/module-role quiescence.
- GpuRegistryUnregisterModuleRole was removed as a duplicate lifecycle path. Shutdown, quiescence, and finalization now have one explicit sequence; only finalization invokes release_module_role and releases the module lease.
- Repeated successful registration/observation/attachment calls may return an additional caller-owned reference only where their operation-specific contract says so. Ambiguous DDX registration installs no binding and returns no retained pointer/generation; identity evidence must first be resolved through the observation path.
- GPU_BACKEND_DEVICE_LOST is valid only for an already-created logical Device. A failed create_logical_device due to a temporarily unusable PhysicalDevice must report UNAVAILABLE with exact binding or module-role scope instead.

The four typed tables and top-level operations were checked against request subopcodes 0–47. Buffer and CommandBuffer create/destroy symmetry is present; exactly six operations use operation tokens; all other entries are synchronous; typed destroy hooks have no invented generic BUSY/PENDING result and must be invoked only after server-side dependencies drain. Presentation-specific route/Surface corrections are recorded in presentation.md and provider-operation-matrix.md.

Relevant commits include e50641cd1425db3b56b2c0e4eb266e75f11aa6c1, 92e632f8d254cf0851c7dbc3ec3a54e5bfbf2f26, 8582c6a79d734617a9d45f017ebdbd5a25335937, 06cdc899d0a08d1c1f8c1747f86c25c34ce0b0f6, e07db772d83abbf317c198874aa3471680342b7c, c937cb7d0d1167a20a2777e09f4016d466d80d87, and 87dcb76c9b575319e41ef7b0c1361fdf5a1ef720. Exact-tip CI remains pending; static/spec consistency must not be presented as runtime implementation evidence.

### Binding-selection and registry result closure — 2026-11-05

The remaining pre-publication selection ambiguity is now closed. The server may configure an ordered preference list over stable owner_key values of GPU_MODULE_ROLE_DDX_BACKEND roles. The first eligible matching binding is selected; if no key matches, a sole eligible binding is selected; multiple eligible unlisted bindings remain unpublished as AMBIGUOUS. Ineligible bindings (invalid/incomplete descriptors, failed mandatory snapshot query, or unsupported mandatory v0.1 baseline) do not block a later eligible preference. The selected binding is immutable after publication; late higher-preference registrations and selected-binding loss do not cause replacement/failover. Conformance vector 79 exercises registration-order independence, no-match ambiguity, ineligible preferred binding fallback, and no late replacement.

The registry result enum now has UNAVAILABLE distinct from BUSY. Acquire/publish/register result mappings distinguish PENDING (barrier/selection unresolved), AMBIGUOUS (identity or binding selection unresolved), UNSUPPORTED (no binding meets mandatory baseline), UNAVAILABLE (temporarily unusable), BUSY (live dependency blocks transition), and SHUTTING_DOWN (admission closed). Registration validates DDX_BACKEND, DISCOVERY_SOURCE, and DDX_TOPOLOGY role kinds at their respective API boundaries. Binding removal and module-role shutdown immediately close admission and mark only affected selected PhysicalDevices UNAVAILABLE; non-selected bindings do not affect published status.

Presentation route generation is now server-assigned, nonzero, and non-reusable; it is passed into route creation and stored by the DDX wrapper. The route metadata output no longer asks the DDX to allocate the generation. Token retirement after terminal success is idempotent SUCCESS, consistent across the API contract and conformance vector 140. The C sketch no longer contains an empty GpuDeviceIdentity struct.

Latest reviewed commit: 7c056ab0aa4af5e97a2b4a8e29de22f79fed1b39. Its combined commit-status and workflow-run queries returned no entries. Exact-tip CI remains unverified and this delta MUST NOT be described as green.

## DDX operation-table and registry API cross-check — 2026-11-05

The four typed operation tables and top-level DDX operations have been cross-checked against the registry signatures and lifetime rules. The normative contract now includes route-scoped STATUS/DEVICE_UNAVAILABLE (without PhysicalDevice/module-role status mutation), provisional binding-generation handling for snapshot-query UNAVAILABLE, one aggregate surface-support query through the exact logical Device, caller-owned output arrays with all-or-nothing descriptor-set allocation, exact wrapper-reference transfer/consumption, and CommandPool/DescriptorPool child-wrapper cascades. Conformance vectors 172–177 exercise the new boundaries, including exact operation-specific STATUS applicability. No client wire ABI or opcode changed. Exact-tip CI is still required before freeze; documentation-level consistency is not runtime conformance evidence.

### Failed backend-destroy quarantine versus module unload — 2026-11-05

A lifecycle cross-check found that architecture §4.6 item 6 could be read as allowing a DDX-owned quarantine to satisfy the module-unload gate even when the typed destroy/free operation had failed. This contradicted `provider-operation-matrix.md`, which requires a failed or uncertain destroy to retain the exact binding/module references and forbids retrying the same destroy hook in v0.1. Architecture §4.6 now states that such quarantine is not quiescence and blocks binding-removal completion, module-role quiescence/finalization, and module unload; architecture vector 143 covers the case and independent retirement of unrelated generations. Commit `b51c2ab9802efaa875e25c1cd801b1d31a136c99`. No wire ABI, opcode, request behavior, or operation-table signature changed. Exact-tip CI has not yet been verified.

### Registry API summary and publication-boundary audit — 2026-11-05

A cross-check of the registry overview, API declarations, and DDX operation matrix found three wording defects and corrected them without changing the wire ABI or C operation signatures:

- The overview used the obsolete semantic name `GpuRegistryRemoveDeviceBackend`; it now names the actual `GpuRegistryRemoveDeviceBackendBinding` entry point and its exact generation arguments.
- The DDX operation-matrix summary could be read as placing module-role quiescence in `GpuDeviceBackendOps`; it now states unambiguously that only `retire_operation` is in the per-device table and all module-role hooks belong to `GpuModuleRoleDescriptor`.
- Two overview passages implied that a successful physical snapshot immediately publishes a PhysicalDevice/XID. They now distinguish atomic binding/snapshot installation from later publication, which requires resolved identity, selected eligible binding, and an open startup publication gate.

Commits: `c1aad25cf2c366e41d7928d4d258e1a39bf647fa`, `973ebb498454b76dc58ac61ddb8449d9bda3a22c`, `54d0053a6c506926467860b2431b2e13ebe3f289`, `38bd488f78d0655e4d0f522d5711a64f69df4dcd`. No opcode, wire layout, or DDX operation signature changed. Exact-tip CI for these documentation deltas remains to be checked.

### DDX operation-table ABI and rebuild-plan alignment — 2026-11-05

The API audit found that the lifetime addendum called `GpuDeviceBackendOps` versioned, while the normative descriptor sketch had no size/version header. The descriptor now begins with `struct_size` and `abi_version`; v0.1 requires exact current size and `GPU_DEVICE_BACKEND_OPS_ABI_VERSION == 1`. This top-level version governs all four nested typed tables. The registry validates it before reading callbacks; size mismatch is `INVALID_ARGUMENT`, unknown version is `UNSUPPORTED`, and neither path may invoke callbacks or retain registration resources. Architecture conformance vector 144 covers malformed headers and missing mandatory callbacks. The addendum and operation matrix now state the same rule.

The Xserver rebuild plan contained superseded `XaveriusPhysicalDeviceOps`/`XaveriusRegisterPhysicalDevice` sketches, incorrect NULL-on-duplicate semantics, context retain/release callbacks, and an implication that registration success meant immediate publication. These were replaced with the exact normative `GpuDeviceBackendOps`, `GpuDeviceBackendRegistration`, `GpuRegistryRegisterDdxDevice`, borrowed DDX handle/context ownership, idempotent exact-registration replay, and separate `XaPhysicalDevicePublish` gate. This is implementation guidance only; no Xserver source was changed.

Relevant commits: `3f9f91a4257e0f26fe38082af8ef36170895887d`, `79698a37b34cb682fc6a507cd1d1fcb107a03b5f`, `d1bebd05be846b1123adbe9182ee22c24edf9813`, `c9d76eda1c05c1a439d0e7d68492656c62b14949`, `de76d77048cbc2eb383f552f7f7a3432f1e9447c`, `8a449dd19f7ded98e29a71e2574c1d20510ab320`. No wire ABI/opcode changed. Exact-tip spec CI remains unverified for these changes.

The same compatibility check was extended to the two other DDX-supplied registration descriptors: `GpuModuleRoleDescriptor` and `GpuDeviceBackendRegistration` now each carry independent v1 `struct_size`/`abi_version` headers. Their APIs validate the header before reading later fields, acquiring a loader pin, invoking callbacks, or retaining any registration resources. Architecture conformance vector 145 covers malformed and unknown descriptor versions. The lifetime addendum and rebuild plan now reflect this boundary. Commits: `6829490cc367481af5938c03e1960b15d3a746b0`, `41dff347d55088444c1883044ddf245946d61f22`, `8595a7e58a05189f9ea80a74b1d3a4f985e05aab`.
