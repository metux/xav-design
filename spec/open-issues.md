# Remaining v0.1 issues and future maintenance

This file separates specification design gaps from implementation acceptance tests. A protocol rule can be fully specified before a server exists; static checks cannot prove runtime interoperability. The release gate is [the specification freeze checklist](freeze-checklist.md).

## Specification freeze status

The request registry defines 48 request contracts: common bootstrap `QueryVersion` at subopcode 0, compute-baseline subopcodes 1–40, and presentation-capable-profile subopcodes 41–47. Presentation requests and event types remain profile-gated; their assignment does not imply support in the initial compute-only implementation.

The latest exact-tip CI-verified specification baseline is `a66d977b436cb05818a07a847e7c4fc1e8065598`, verified by [wire-layout/request-reply/XGE workflow run 41846198875](https://github.com/metux/xav-design/actions/runs/41846198875) and [required-check workflow run 41846198977](https://github.com/metux/xav-design/actions/runs/41846198977). The verified baseline includes XLibre loader/module-pin mapping, DDX backend-wide quiescence, callback-return retirement, detached Screen callback state, multi-DDX backend ownership, and DDX backend registration/module-lease finalization vectors 79–96. Phase 1 ship confirmations, concrete loader-pin/hotplug/identity evidence, and a named shared integration-interface owner remain coordination sign-offs. Runtime acceptance gates remain open and are listed below.

**Editorial note (not a protocol blocker).** Some normative and explanatory prose remains German while other chapters are English. This is a consistency/readability issue, not evidence of a protocol-design gap. Translation is deferred unless mixed-language wording makes a requirement ambiguous; content reviews must still verify the exact normative meaning regardless of language.

The request/error precedence audit and dedicated `QueryVersion` review cover all 48 registered requests. The exact candidate and CI run above verify the normative request/reply contract, both byte orders, malformed request headers and lengths, and reserved/version reply fields. Resource lifetime, asynchronous terminalization, callback identity, semaphore/fence reservations, and Device-loss behavior retain their dedicated normative audits and reference-model regressions. Passing static checks does not prove runtime behavior; implementation acceptance gates remain open.

### Closed normative audit — render GPU versus scanout GPU — 2026-11-04

The presentation contract now treats the logical Device's render GPU and the Surface's owning Screen/scanout GPU as independent. ScreenAttachment roles are topology only; the selected execution DDX backend coordinates a direct WSI or explicit bridge route for the exact Device/Surface pair. PRIME/DRI3 bridging is permitted only when the DDX backend can prove full format/modifier, usage, synchronization, ownership-transfer, and release/completion compatibility. The route is pinned to a Swapchain generation; topology changes make that Swapchain OUT_OF_DATE. No implicit GPU/DDX backend/Screen/output migration is permitted. Permanent lack of a route maps to no present-capable queue and UNSUPPORTED_CONFIGURATION; temporary route unavailability and accepted route failure have explicit status mappings. No wire ABI changed. Candidate `013be364ea8cc7126b092f46d7c266b43dcda02f` requires exact-tip CI before verification.


### Closed normative audit — logical versus DDX backend-native Surface — 2026-11-04

The logical Surface is connection-owned and independent of any Device/DDX backend. CreateSurface therefore performs no DDX backend call. Native DDX backend Surfaces are created lazily for the exact DDX backend generation selected by a Device-specific capability query or swapchain creation, and are scoped to the exact DDX binding-generation/logical-Surface-generation pair. DestroySurface retires all such wrappers after dependent use drains. This resolves the multi-GPU ambiguity without changing the wire ABI. Vectors 165–170 were added; exact-tip CI is pending. DDX backend shutdown retires only that generation's native Surface wrappers; the logical Surface remains live and existing Devices are not failed over. Transform/composite-alpha choices remain backend-internal because v0.1 has no corresponding wire fields or client selectors. Runtime confirmation of the actual DDX backend Surface cache and teardown remains an implementation acceptance item.

## Implementation acceptance work (not a missing wire assignment)

1. **Open — live X11/XGE interoperability.** Exercise standard `QueryExtension("XAverius")`, the new XAverius `QueryVersion` request and 0.1 reply, dynamic major-opcode use, separate `GEQueryVersion` negotiation, `SelectEvents`, XGE framing, masks, byte order, and connection isolation against an actual X11/XGE server and XAverius implementation. Follow the [XGE interoperability test plan](xge-interoperability-test-plan.md). Documentation-only checks cannot prove interoperability.
2. **Open — compute backend conformance.** Validate queue ordering, successful `WriteBuffer` visibility, dispatch/readback, synchronization, Device loss, late callbacks, client disconnect, and resource teardown against an actual Vulkan backend.
3. **Open if presentation is implemented — presentation backend conformance.** Validate Window/Surface lifetime, swapchain creation, acquire/present/release transitions, resize/out-of-date, terminal event behavior, and device/connection teardown races. Keep these results separate from compute-only conformance.

These are implementation acceptance gates. They do not require inventing new request IDs or leaving already-defined layouts ambiguous. They remain open until a real implementation is exercised and evidence is recorded.

## Normative maintenance rules

These are settled rules, not open v0.1 design questions:

- **Request subopcodes:** common bootstrap `QueryVersion` uses subopcode 0; compute-baseline requests use 1–40; presentation-capable-profile requests use 41–47. Subopcode 48 is unassigned. The [central request registry](../registries/request-subopcodes.md) is append-only; existing assignments MUST NOT be renumbered.
- **Physical-device properties:** the five v0.1 properties and their wire representations are defined in the [property registry](../registries/physical-device-properties.md). Future properties must be registered append-only.
- **Feature IDs and device extensions:** future assignments must be registered append-only. The v0.1 optional sets are intentionally empty; see [feature IDs](../registries/feature-ids.md) and [device extensions](../registries/device-extensions.md).
- **Memory properties flags:** `memory_properties_flags` MUST be zero in v0.1 until a registry definition is explicitly assigned; see [memory properties](memory-buffers.md#52-getphysicaldevicememoryproperties).
- **Physical Device UUID and Driver UUID:** both are opaque 16-byte `BYTE_ARRAY` properties. The server preserves Vulkan-returned bytes exactly and MUST NOT fabricate unavailable UUIDs; see the [property registry](../registries/physical-device-properties.md).
- **Presentation profile boundary:** the initial implementation target remains compute-only. A server that does not implement the presentation-capable profile rejects requests 41–47 with core X11 `BadRequest` before payload parsing or XID resolution. Event IDs 7 and 8 and their queue-mask bits remain presentation-profile-only.

## Deferred to future protocol versions

These topics do not block the current contract unless a future version explicitly brings them into scope:

- **Queue fairness and bounded progress:** v0.1 defines same-queue submission order, no implicit cross-queue ordering, and explicit semaphore dependencies, but promises no fairness or bounded scheduling latency. See [queue submission and ordering](queue-submission.md).
- **X11 resource sharing:** cross-client or cross-device sharing is not implicitly provided by v0.1. Current ownership rules are in [device discovery](devices.md) and [resource lifetime](resource-lifetime.md).
- **Additional optional features/extensions:** v0.1 registers none; adding support requires explicit append-only registry assignments and a reviewed protocol change.

## Closed items

- **Submission terminal events:** `SUBMISSION_COMPLETE` and `SUBMISSION_FAILED` layouts, event-type IDs, XGE lengths, terminal-event exclusivity, and delivery behavior are specified in [events](events.md) and covered by the conformance checklist.
- **Shared device reason codes:** `DEVICE_LOST.reason_code` and `DEVICE_STATUS_CHANGED.reason_code` use the same append-only [device reason-code registry](../registries/reason-codes.md). Values are informational and do not replace event-specific lifecycle rules.
- **WriteBuffer dependency cycle:** while waiting for earlier submissions, the server checks deferred `QueueSubmit` signal entries. If a deferred timeline signal would satisfy a wait of an earlier non-terminal submission and no already accepted signal operation can satisfy that wait, `WriteBuffer` fails with `DEPENDENCY_FAILED`; deferred requests are then processed in request order, and no `QueueSubmit` is accepted across a successful upload boundary. See [Memory and buffers](memory-buffers.md#57-writebuffer), [Queue submission and ordering](queue-submission.md), and the conformance checklist.


### Closed normative audit — PresentationRoute result mapping and lifetime — 2026-11-04

The seven presentation requests were cross-checked against the DDX backend-result contract and lifecycle serialization rules. GetSurfaceCapabilities now has a complete status precedence including the zero-extent case. Capability queries do not retain route leases; CreateSwapchain creates and pins the exact route generation and revalidates it at publication. Swapchain/route destruction order, DDX backend-token quiescence, failure rollback, and quarantine are explicit. Dedicated conformance vectors are in [presentation-route-conformance.md](presentation-route-conformance.md). No wire ABI changed. Exact-tip CI after these documentation updates remains required.


### Registry mutation result contract — 2026-11-04

Physical removal confirmation now requires evidence tied to the exact current source observation and PhysicalDevice incarnation. DDX per-device context/device availability and recovery operations return classified registry outcomes; stale generations, unknown module-role generations, or absent selected bindings are rejected without mutation. The source key in removal evidence is borrowed for the call only and resolved before return. The API-result/architecture vectors are in `spec/device-registry-architecture.md` (vectors 58–59). The availability-transition return-value refinement and source-authority validation are verified by workflow 41840825348. The DDX backend pointer-lifetime contract is verified by exact-tip workflow 41840947750. This is internal server architecture, not a wire-protocol design gap.


### Runtime acceptance: XLibre DDX/DDX backend module quiescence — 2026-11-04

The normative lifecycle contract is closed in `device-registry-architecture.md` §2.4: Screen close is topology-only; a DDX backend/module lease is independent of Xorg `ScrnInfo`/driver references; per-token retirement includes callback return; and module-role `quiesce_module_role` SUCCESS is required before unloading code or userdata reachable by callbacks/workers. PENDING/FAILURE retains or quarantines the DDX backend. Vectors 70–75 cover the static lifecycle cases. Remaining acceptance work is runtime-only: instrument an XLibre build to verify actual module references and unload ordering under GPU hotplug, multiple Screens, DDX backend callback races, and DDX module unload. Do not treat `FreeScreen()`, `xf86DeleteScreen()`, zero driver Screen references, or `RemoveGPUScreen()` as DDX backend quiescence.


The XLibre loader implementation was also checked: `DuplicateModule()` does not acquire an independent module handle, and `LoaderUnload()` calls `dlclose()` on the original handle. Vectors 76–77 now require a separate DDX backend module pin to survive final Screen deletion. The remaining question is runtime acceptance on a built XLibre server: demonstrate that the chosen pin mechanism actually prevents the final `dlclose()` until DDX backend-wide quiescence succeeds.


The Screen-close contract also forbids asynchronous callbacks from retaining raw `ScreenPtr`/`ScrnInfoPtr` or pointers into `FreeScreen()`-owned storage. Runtime acceptance must verify that the DDX uses a detached generation-checked ScreenAttachment context (or copied immutable values) and that callbacks after close never enter Screen/RandR hooks. Vector 78 covers this case.


### Multi-DDX backend ownership — 2026-11-04

The normative registry contract now distinguishes DDX backend generations, DDX backend-local bindings, source-owned discovery observations, ScreenAttachments, and shared module-owner leases. Multiple providers may bind one canonical PhysicalDevice, but v0.1 still selects exactly one DDX backend and one immutable snapshot; no cross-DDX backend capability union or transparent failover is allowed. One DDX backend generation may serve multiple PhysicalDevices, and one module may own multiple independently quiesced DDX backend generations. Source withdrawal and binding removal are exact-scope operations; concurrent teardown is serialized by generation.

This closes the remaining architecture ambiguity for multiple DDX/DDX backend modules and shared module ownership. Remaining work is implementation acceptance only: exercise multiple DDX backend generations in one module, providers from separate modules observing one GPU, source-local withdrawal, no-failover behavior, and competing Screen-close/DDX backend-unregister/physical-remove races on a built Xlibre server. The normative text and vectors 79–88 are in [device-registry architecture](device-registry-architecture.md). Exact-tip CI for commit `c88668e023ba31fa38293dba4aef5a827adedb64` is pending; no wire ABI changed.


### DDX backend registration and module-lease finalization — 2026-11-04

The DDX backend lifecycle API sketch now makes DDX backend-generation registration a one-time operation separate from per-PhysicalDevice binding registration. The registry retains the DDX backend context and module lease once per generation; each binding references the registered DDX backend. The server assigns non-reusable DDX backend generations. A single server-owned module lease is shared across all DDX backend and adapter roles backed by the same loaded module. `XaveriusRegistryTryQuiesceModuleRole` is generation-checked and reports registry errors separately from PENDING/SUCCESS/FAILURE; DDX backend-internal workers are stopped by the hook itself. Finalization waits for all DDX backend objects/references, calls the final `release_module_role` hook while the module remains pinned, then releases the lease exactly once. Vectors 89–93 cover these cases. This closes an API-sketch ambiguity; no wire ABI changed. Runtime acceptance remains open for actual Xlibre loader pinning, multi-DDX backend module ownership, and teardown races. Commits `1029787` and `63c5339`; exact-tip CI pending.


The DDX backend API follow-up also closes three lifecycle edge cases: registry-assigned DDX backend generations are reserved and never recycled after failed registration; quiescence cannot run while any DDX backend-owned object still needs DDX backend code; and successful quiescence permits only the registry's final DDX backend release call before dropping the real loader pin. The loader lease must be based on a stable server-owned module-owner record and an independent loader reference, never a duplicated Xorg ModuleDesc or Screen refcount. Architecture vectors 94–96 cover these cases. Commits `7545bda` and `dc6c858`; exact-tip CI pending.


### Implementation guidance — 2026-11-04

The architecture now provides non-normative Xlibre implementation decomposition and sequencing guidance in [device-registry architecture §8.2](device-registry-architecture.md#82-suggested-implementation-decomposition-non-normative). This does not add a wire-design blocker. Outstanding work is evidence from the implementation agents and runtime acceptance: loader pin behavior against the actual Xlibre loader, subscribe-before-scan hook placement, authoritative identity sources, DDX backend/context multiplicity, and callback/worker module lifetime. See [IMPLEMENTATION_COORDINATION.md](../IMPLEMENTATION_COORDINATION.md).


The `XaveriusRegistryAttachScreen()` API sketch now explicitly treats its `ScreenPtr` argument as borrowed for the call only and prohibits registry retention. This clarification is CI-verified at `a66d977b436cb05818a07a847e7c4fc1e8065598` by workflows 41848200892 and 41848200803. Remaining items below are runtime/implementation evidence and coordination sign-offs, not unresolved protocol rules.


### Registry API audit follow-up — 2026-11-04

The registry API sketch has been strengthened in `device-registry-architecture.md` §7. It now defines failure/result semantics, output sentinels, reference ownership, source and module-role registration, server-assigned binding generations, callback/role lifetime, transactional publication, DDX backend output ownership, and async token/completion contracts. Vectors 97–114 were added. Exact-tip CI is pending; this is not a wire-design blocker and changes no protocol assignments. Runtime acceptance still needs evidence that the implementation's concrete registry/loader structures satisfy these contracts.


The registry API audit also closed the server/DDX backend operation-token handoff. Token preparation occurs before DDX backend entry; DDX backend return is committed or rejected explicitly; callbacks arriving before commit are buffered; and per-token retirement has PENDING/SUCCESS/FAILURE outcomes. Failure to prove retirement quarantines the token and blocks DDX backend-wide quiescence. Vectors 115–119 exercise these races. Exact-tip CI is pending; this remains an internal implementation contract, not a wire-design gap.


The second registry API pass closed candidate enumeration and DDX backend-local handle lifetime, explicit asynchronous operation-kind coverage, complete resource pin sets, token pointer lifetime, status-code payloads, and bounded completion payloads. Vectors 120–131 and §8.3 implementation guidance were added. Remaining acceptance is implementation evidence: stable binding-ID mapping, correct token use by all six async operations, full QueueSubmit dependency pinning, callback pointer discipline, and exact status mapping. Exact-tip CI pending.


The API second pass now also requires completion binding-generation validation and separates DDX backend-device wrapper references from native logical-device destruction. Vector 132 covers stale binding completions. Runtime evidence is still required for callback userdata carrying both binding identifiers and exact DDX backend-device retain/release pairing.


The API audit now also closes delayed status-event races: context and binding availability notifications use monotonic scope-specific sequences; binding events include exact binding_generation; source observations/removal evidence include source_event_sequence. Effective availability is composed across DDX backend context, binding, and physical state. Runtime evidence remains required that adapters capture source event sequence before dispatch and DDX backend callbacks carry the exact binding generation. Vectors 133–137 added.


Runtime acceptance now also requires evidence that all six asynchronous operation paths build the complete per-token resource pin set, especially QueueSubmit's full dependency graph and presentation's Swapchain/route/image/synchronization dependencies. Vector 138 added.


Runtime acceptance requires a distinct DDX backend-generation quarantine state for XAVERIUS_BACKEND_FATAL, separate from logical-device DEVICE_LOST and ordinary shutdown/quiescence. Verify fatal paths close admission and retain the module/context rather than entering normal unload. Vector 139 added.


Runtime acceptance must verify state-checked Retain admission and the exact idempotence behavior for operation-token and DDX backend lifecycle transitions. Vector 140 added.


Runtime acceptance should verify repeated successful ObserveDevice replay increments only the caller-owned PhysicalDevice reference count and does not duplicate source observation state. Vector 141 added.


Runtime acceptance must verify fatal quarantine blocks subsequent DDX backend quiesce/final release hooks and preserves all module/context/object references. Vector 142 added.

### Registry API lifetime addendum — 2026-11-04

The second API pass added a normative supplement in [registry-api-lifetime-addendum.md](registry-api-lifetime-addendum.md). It clarifies the DDX backend-context accessor result/borrow contract, nested operation-table storage and code lifetime, canonical shared module-lease identity, final lease-release barrier, terminal source/binding/Screen removal semantics, complete DDX backend-quiescence preconditions, and temporary operation-token pointer confinement. Architecture vectors 143–150 cover these cases. These are specification refinements, not wire-design changes. Exact-tip CI is required; implementation acceptance still needs evidence for the actual Xlibre loader and DDX backend callback paths.

### DDX backend operation-table completeness — 2026-11-04

The audit found the four typed DDX backend operation tables were opaque forward declarations only. [DDX backend operation matrix](provider-operation-matrix.md) now normatively defines their operation signatures and maps all request subopcodes 0–47. It also closes the missing Buffer destroy callback, asynchronous classification, create/destroy symmetry, output initialization, command-stream boundary, and presentation capability result completeness. Vectors 151–164 cover the new requirements. Implementation-agent signature comparison and runtime acceptance remain open; exact-tip CI is pending.

### DDX binding API supersedes provider-object API — 2026-11-04

The current normative design supersedes the historical provider-generation/candidate-binding API described in earlier entries. The DDX owns complete device enumeration and registers every served PhysicalDevice directly, with native handle, per-device context, and typed operations on the binding. The module-role control record exists only for shared code/module lifetime and quiescence. No independent Vulkan-ICD inventory, candidate-list API, provider-local numeric handle map, generic provider context accessor, or per-request provider-object dispatch is part of the current design. Earlier entries below document historical decisions and are not current API requirements where they conflict with this superseding model.


### Residual candidate-ranking language removed — 2026-11-04

A final consistency pass corrected the non-normative §8.2 selection guidance and the related conformance vectors. The current design has no registry-side DDX candidate list, stable backend-key ranking API, or intermediate provider-object acquisition. Each DDX registers each served PhysicalDevice directly; the registry validates complete bindings and selects before publication using an explicit server-configured ordered preference over stable module-role owner_key values. Unconfigured multiple eligible bindings remain ambiguous; published bindings never fail over. The shared module role is lifetime/quiescence state only. This is an internal architecture/API clarification, not a wire-protocol change. Exact-tip CI and implementation-agent conformance evidence remain pending.
### Closed normative audit — registry API versus typed DDX operation tables — 2026-11-05

A cross-check of the registry API and all four typed DDX operation tables closed several server-contract ambiguities without changing the client wire ABI:

- A route-only temporary outage now has an explicit backend STATUS/DEVICE_UNAVAILABLE result. It maps to the exact Device/Surface request status and does not mark the PhysicalDevice or module role unavailable. An accepted QueuePresent still uses its terminal presentation failure channel.
- A registration attempt reserves its non-reusable provisional binding generation before query_physical_snapshot; a PHYSICAL_DEVICE-scoped snapshot failure identifies that provisional generation, rejects only the attempt, and cannot mutate an existing selected binding.
- query_surface_support receives the exact logical XaveriusBackendDevice and returns one aggregate for all queue families in one call. It cannot assemble a capability snapshot from per-family calls or another logical Device.
- All four typed tables now have explicit output initialization, caller-owned array capacity, batch atomicity, object-reference transfer/consumption, borrowed queue-handle, and CommandPool/DescriptorPool cascade rules.

The corresponding conformance additions are vectors 172–177 in [the DDX backend operation matrix](provider-operation-matrix.md). No request, reply, event, opcode, or Vulkan capability changed. These are normative specification checks only; exact-tip CI and live implementation conformance remain separate gates.
