# XAverius Implementation Coordination

**Purpose:** Live hand-off for parallel implementation work. This file contains current decisions, interfaces to coordinate, open questions, and verification state. Historical discussion is preserved in [the coordination history archive](IMPLEMENTATION_COORDINATION_HISTORY_2026-11-04.md).

## Authoritative baseline

- Specification repository: `metux/xav-design`.
- Authoritative branch: `docs/restructure-2026-10-21`. Do not use `master`, `wip/001`, or an implementation branch as the specification source.
- The current branch tip is authoritative; agents MUST sync from it before implementation or rebasing.
- This repository is in specification/architecture work. Do not add Xorg/Xlibre backend implementation here unless explicitly requested.
- Wire assignments are fixed: QueryVersion = 0, Compute-Baseline = 1–40, Presentation-Profile = 41–47. The registry is append-only.

## Current verified baseline

- Latest exact-tip CI-verified specification commit: `72f3f17f3e7ea336658ba59ed5ed93a65805e3a9`.
- Exact-tip CI: [workflow 41844649170](https://github.com/metux/xav-design/actions/runs/41844649170) — SUCCESS. Required wire-layout, Timeline, Python, shared-header, XCB client, request/reply/XGE, backend-discovery/handler/callback, and required-check gates passed.
- This verifies vectors 76–78 and multi-provider ownership/vectors 79–88; the multi-provider architecture commit `c88668e023ba31fa38293dba4aef5a827adedb64` independently passed [workflow 41844488352](https://github.com/metux/xav-design/actions/runs/41844488352).
- Newer provider registration/module-lease lifecycle commits `1029787cbf4b7d3f0b8675264e39e9c4527da754`, `63c5339ca702a913f7da55747e877177782492a5`, `7545bda9018b2cc3cb6ef3d666cd3619a14efb36`, and `dc6c8589f7961b587f37a97cc2f4e76c67f8d627` add vectors 89–96. Exact-tip CI is pending; do not treat this refinement as verified until it completes.

## Architecture contracts implementation must follow

### Physical-device inventory

- One process-wide registry owns canonical PhysicalDevice identities and server-owned Physical-Device XIDs.
- A PhysicalDevice is not a Screen, DDX instance, DRM node, Vulkan handle, provider, or Vulkan device group.
- Identity is canonicalized across Xorg/DRM, udev, Vulkan-loader, and other discovery paths before publication. Primary and render nodes for one DRM device resolve to one identity; remove/re-add creates a new incarnation and XID.
- Each published v0.1 PhysicalDevice has exactly one selected execution provider and one immutable metadata snapshot from that provider. No cross-provider capability union or transparent failover.
- ScreenAttachment is a non-owning, generation-checked relation. A Screen may attach to multiple GPUs and a GPU may attach to multiple Screens. Attachment does not establish presentation support; the exact Device/Surface query does.
- Status is AVAILABLE, UNAVAILABLE, or terminal REMOVED. Provider failure is not hardware removal or logical Device Loss. REMOVED entries remain tombstones until server shutdown.

### Provider boundary and lifetime

- The server owns request validation, XID/resource ownership, request ordering, public state transitions, error mapping, and event delivery.
- A provider owns its private Vulkan/backend handles and executes only validated operations supplied through the provider interface.
- Provider selection is deterministic and completed before publication. The selected provider and published snapshot do not change during the PhysicalDevice XID lifetime.
- Provider results are classified. UNAVAILABLE carries explicit PROVIDER_CONTEXT or PHYSICAL_DEVICE scope. Only positive loss for an exact logical Device establishes DEVICE_LOST.
- Accepted asynchronous operations carry non-reusable provider/operation/device/resource generations. Completion callbacks only enqueue immutable records; the server serializes state changes.
- A terminal callback is not proof of quiescence. Only successful exact-token retirement proves no further backend access and permits releasing retained references. Otherwise quarantine; never unload reachable provider code.
- WaitSemaphores and WaitForFence are server-owned registrations, not provider operations and have no provider tokens.

Normative and detailed contracts: `spec/devices.md`, `spec/device-registry-architecture.md`, `spec/resource-lifetime.md`, `spec/presentation.md`, and `spec/synchronization.md`.

## Active coordination items

1. **Inventory/driver registration:** identity matching now defines evidence precedence and conflict outcomes, including DRM node equivalence, Vulkan UUID corroboration, derived-device instance identity, and provider-scoped fallback. Implementation feedback is still needed on which Xlibre/Xorg discovery interfaces can supply authoritative evidence for each device class. Do not let a Screen choose or publish the PhysicalDevice or selected provider.
2. **Shared interfaces:** before parallel agents edit shared dispatch, resource lookup, registry, provider, or header code, record one integration owner and the agreed interface here.
3. **Request ownership:** maintain exactly one handler owner per request. Shared helpers have a separately named owner; request ownership does not imply shared-file ownership.
4. **Lifecycle integration:** report any implementation assumption that conflicts with provider pinning, generation checks, accepted-operation terminalization, or quarantine rules.
5. **Verification:** every implementation/spec change report must include branch, commit SHA, exact test commands or CI run, result, and remaining unverified runtime behavior.
6. **Xlibre startup/hotplug integration:** the normative adapter/barrier contract and source-level hook mapping are in `spec/device-registry-architecture.md` §§2.4 and 8.1. Runtime feedback is still needed on driver-supplied authoritative identity evidence and live hotplug behavior; do not substitute Screen indices or DDX initialization order.

## Latest specification update — Physical-device registration

The registry architecture now separates discovery-source observations, provider-local execution bindings, ScreenAttachments, and XAverius publication. DDX/Screen drivers report topology; only components implementing the complete backend contract register as BackendProviders. Provider registration order and Screen initialization order do not select the execution provider. The startup discovery barrier and the equivalent per-device hotplug publication path are specified in `spec/device-registry-architecture.md`.

The current specification baseline `7f2620726f88bbd28ff6ac5c21a27d87659301e7` passed [exact-tip wire-layout workflow 41830758364](https://github.com/metux/xav-design/actions/runs/41830758364): 4,873 wire-layout checks, 72 Timeline tests, 693 Python tests, header/client builds, and required CI gates all passed. Subsequent status/checklist/open-issues edits are documentation-only; a fresh CI run is tracking those documentation changes. Runtime Xorg/Vulkan integration remains untested.

## Latest specification update — identity evidence and provider selection

The registry architecture now defines an evidence hierarchy and explicit conflict outcomes for platform identity, DRM primary/render-node equivalence, Vulkan `deviceUUID` correlation, derived devices (mediated/SR-IOV/partitioned/MIG), and provider-scoped software/virtual identities. Ambiguous or contradictory candidates remain unpublished; published identities are never merged or rebound. Provider selection now rejects duplicate stable keys and ambiguous preference identifiers, and evaluates identity/snapshot eligibility before ranking. Architecture vectors 36–44 cover these cases. The normative device chapter links to the architecture contract. Exact-tip candidate `f6ae4c056b3621d8b491dc64aad4d361baf2c0c2` passed [workflow 41832770751](https://github.com/metux/xav-design/actions/runs/41832770751): 4,886 wire-layout checks, 72 Timeline regressions, 693 Python tests, header/client builds, request/reply/XGE validation, and all required gates.

## Latest specification update — render GPU versus scanout GPU

The presentation contract now separates the logical Device's render PhysicalDevice from the Surface's owning Screen and scanout PhysicalDevice. ScreenAttachment roles are topology only. The selected execution provider coordinates the exact Device/Surface route, either direct WSI or an explicit PRIME/DRI3 import/copy/composition bridge with complete format/modifier, usage, synchronization, ownership-transfer, and release/completion guarantees. A private DDX/display bridge may participate, but Vulkan handles never cross provider boundaries. No implicit migration to another PhysicalDevice, provider, Screen, or RandR output is permitted. A successful Swapchain pins one route generation; topology changes invalidate it as OUT_OF_DATE. Temporary route unavailability, pending-acquire behavior, and accepted-present failure have explicit status mappings. Architecture vectors 48–56 cover split render/scanout GPUs, bridge eligibility, route outage, route invalidation races, and independent failure domains. Exact-tip CI passed at `47651058aa078d6727d681aa832630c2516bff5c` in workflow 41835144462. The architecture model now has an explicit internal PresentationRoute object and provider operations to create/retire it; CreateSwapchain pins the exact route, and the lifecycle serializer tracks route generations alongside Device/Surface/Screen/Swapchain generations. The explicit PresentationRoute object, route create/retire operations, and route-generation lifecycle references are CI-verified at `df2d09ac8992229934cb407506baed2865a0416d` by workflow 41836070379.

## Agent update format

Post concise updates under this heading using:

- **Agent / branch / commit:**
- **Files or request groups:**
- **Interfaces or assumptions needing coordination:**
- **Tests and result:**
- **Open blockers:**

Do not copy historical audit narratives into this live file. Put durable design decisions in the relevant specification chapter and historical review detail in `audit/`.


## Latest specification update — PresentationRoute result mapping and lifetime — 2026-11-04

The seven presentation requests were audited against provider-result classification and route lifecycle. GetSurfaceCapabilities now defines complete status precedence, including zero-extent combinations. Capability queries are non-committing probes; CreateSwapchain creates and pins the persistent PresentationRoute and revalidates its generation at commit. Provider Swapchain destruction precedes route destruction, and route/bridge references remain retained until operation-token retirement proves quiescence. Failed preparation unwinds in dependency order; unproven retirement requires quarantine. Dedicated conformance vectors are in `spec/presentation-route-conformance.md`. No wire ABI, opcode, or status value changed. Exact-tip CI for these changes is pending.

## Latest specification update — exact logical-Device PresentationRoute binding — 2026-11-04

The provider API sketch now creates a PresentationRoute from the exact provider logical-Device handle plus the provider-scoped Surface, rather than from a PhysicalDevice handle. This matches the normative route scope (logical-Device generation + Surface/Window/Screen generation) and prevents two logical Devices on the same PhysicalDevice from accidentally sharing route lifetime. Architecture vector 57 covers independent route and Swapchain teardown. The removal API now also requires provenance-bearing authoritative evidence for the exact current PhysicalDevice incarnation and returns a classified registry result; vector 58 covers stale or insufficient removal evidence. Spec commits: `084de5c0ccb9f7931c44b2b21fcaba9cb19b94b1`, `d44efd16010b94177199a1b97a9855f64555fbe6`, and `ad6d993cd9fd00eedb68bf42e23f7dd7236d8361`. The registry API result enum now distinguishes success, pending, ambiguity, stale generations, invalid evidence, identity conflicts, allocation failure, and internal failure. Exact-tip CI pending.


## Latest specification update — generation-checked registry mutations — 2026-11-04

The provider availability/recovery API now returns `GpuRegistryResult` for context-wide and device-scoped transitions. Stale provider/device generations, unknown providers, and absent selected bindings are observable rejections and MUST leave state unchanged; valid transitions return `GPU_REGISTRY_SUCCESS` and affect only the exact selected scope. `GpuDeviceRemovalEvidence.source_key` is explicitly borrowed for the call only and resolved before return. Architecture vector 59 covers stale/unknown mutation attempts. Change commit: `bbda0c5036306b0497cda41b825a074b6608460f`; exact-tip CI pending.

The status, freeze checklist, and open-issues summaries have also been refreshed to identify exact-tip workflow 41840312155 as the latest verified baseline and to distinguish subsequent unverified documentation/API deltas.


## Latest specification update — Xlibre/Xorg discovery integration — 2026-11-04

`spec/device-registry-architecture.md` §2.4 now defines the Xlibre/Xorg adapter roles (platform discovery, DDX topology, Vulkan provider), the startup barrier and hotplug scan/event reconciliation, late-source behavior, DRM identity hand-off, Screen-generation teardown, and module/provider unload pinning. It deliberately specifies lifecycle semantics rather than version-specific Xserver hook names. Architecture vectors 61–66 cover barrier independence, discovery failure/late registration, unresolved DDX identity, and unload with outstanding callbacks; the combined contract and vectors passed exact-tip workflow 41842074182 at `4eb0d35938def3f74de579a7bb2e7729a304325f`. A subsequent non-normative source mapping to XLibre master commit `ee4bb3f96eec3b21c1961d54fe45cb33dc402d00` is in `d070c735c3057940c00ac42c1dd0d443363e1fef`; vectors 67–69 in `a90544633e8a9c477ea380ecbac7ee24b27f2653` cover the card/render-node split, GPU-screen removal, and primary-device fallback. Both newer commits are pending exact-tip CI. Runtime Xlibre hook mapping remains an implementation acceptance task.


## XLibre source mapping review — 2026-11-04

The current X11Libre/xserver source was reviewed at `ee4bb3f96eec3b21c1961d54fe45cb33dc402d00`. The practical mapping in `spec/device-registry-architecture.md` §8.1 records that `xf86BusProbe()` invokes `xf86platformProbe()` before extension setup; `config_udev_odev_probe()` enumerates DRM `card[0-9]*` and deduplicates by major/minor; GPU-screen add/remove is a separate DDX/Screen lifecycle; and `xf86platformPrimary()` may fall back to the first platform device. XAverius must not use those Xorg-specific conventions as canonical identity or default-device policy. The §8.1 mapping commit `d070c735c3057940c00ac42c1dd0d443363e1fef` passed workflow 41842380756, and conformance vectors 67–69 (`a90544633e8a9c477ea380ecbac7ee24b27f2653`) passed workflow 41842404893. The follow-up Screen-close/module-quiescence contract and vectors 70–75 are covered by the later verified baseline `5e213d62a116fe2c785c9ba5513a8129f3a4eda0`.


## Latest specification update — DDX Screen close and provider module quiescence — 2026-11-04

The XLibre Screen lifecycle is now explicitly topology-only: `dixScreenRaiseClose()` / `RemoveGPUScreen()` / `xf86DeleteScreen()` and DDX `FreeScreen()` do not prove provider callback or backend quiescence. A DDX/provider module must hold a provider/module lease independent of the `ScrnInfo`/driver Screen reference. Closing one Screen detaches only that exact ScreenAttachment and does not unregister a shared provider. Provider unload is two-phase: close admission, withdraw topology/observations, drain and retire exact operation tokens (including callback return), then perform provider-wide callback/worker quiescence before releasing the final provider/module lease. PENDING/FAILURE means retain or quarantine, never unload. Normative text and vectors 70–75 are in `spec/device-registry-architecture.md`. Contract/vector commit `03253eef3631ff3faf7fbaa55611d5d13388c4a5` passed workflow 41843032895; vectors 70–75 at `5e213d62a116fe2c785c9ba5513a8129f3a4eda0` passed workflow 41843046752. The explicit `quiesce_provider` ABI hook and callback-return strengthening in `5d3c0f69e715a8a0e89b1217e6101c2b1500da21` passed exact-tip workflow 41843078578. A further source-level review of `DuplicateModule()`, `UnloadModule()`, and `LoaderUnload()` shows that duplicated `ModuleDesc` records do not create an independent loader pin, while final unload reaches `dlclose()`. This is documented in §8.1 with vectors 76–77 (`3a42c1a63e68016d952f91542b858fee3d35d300`); exact-tip CI for these additions is pending.


A final Screen-lifetime clarification is in `device-registry-architecture.md` §2.4: asynchronous provider callbacks MUST NOT retain raw `ScreenPtr`, `ScrnInfoPtr`, `pScreen`, `pScrn`, or `FreeScreen()`-owned pointers. Required values are copied or held in a detached, generation-checked ScreenAttachment context with no borrowed Xserver Screen pointers. Vector 78 covers callback completion after Screen deletion. Commit `6f01fcb00e9c6ac46cad72e0c52434494e814413` is newer than the current green baseline and pending exact-tip CI.


## Latest specification update — multi-provider ownership and teardown — 2026-11-04

The provider registry contract now explicitly supports multiple independent BackendProvider generations per canonical PhysicalDevice and multiple PhysicalDevice bindings per provider generation. Each (provider generation, PhysicalDevice incarnation) has at most one executable binding; providers must deduplicate multiple Vulkan aliases inside their own context before registration. A loaded DDX/provider module may own several independent provider generations and adapter roles, each with its own generation, admission state, quiescence, and module-lease reference.

Discovery observations remain source-owned. Removing one provider binding or unloading one DDX source cannot withdraw another source's evidence, another provider's binding, or another DDX's ScreenAttachment. v0.1 still selects one provider and one immutable snapshot per published PhysicalDevice. Non-selected providers are not a failover pool and cannot contribute metadata/capabilities or take over after selected-provider loss; the selected PhysicalDevice becomes UNAVAILABLE if its binding is removed.

Provider-generation shutdown now has an explicit generation-scoped BeginProviderShutdown admission barrier, followed by exact binding/observation/attachment withdrawal, accepted-operation drain, provider-wide quiescence, and release of that generation's module-lease reference. Quiescing one provider does not unload a shared module while another provider or adapter role remains live. Architecture vectors 79–88 cover the multiplicity and race cases.

**Implementation feedback requested:** confirm whether the current provider/driver split can represent (a) multiple provider contexts exported by one DDX module, (b) two independent DDX modules observing the same DRM-backed PhysicalDevice, and (c) one provider context serving several PhysicalDevices. Report any source of shared module-global workers/callbacks that cannot be attributed to an exact provider generation. Do not implement provider failover or merge snapshots to work around ownership issues.

Spec commit: `c88668e023ba31fa38293dba4aef5a827adedb64`. Exact-tip CI [41844488352](https://github.com/metux/xav-design/actions/runs/41844488352) pending.


## Latest specification update — provider registration and module-lease finalization — 2026-11-04

The API sketch now has a one-time `GpuRegistryRegisterProvider()` operation, separate from `GpuRegistryRegisterProviderBinding()`. The descriptor, provider context, and module lease are retained once per provider generation; each PhysicalDevice binding references that registered provider. The server assigns the non-reusable provider generation. This removes the earlier ambiguity in which a provider descriptor appeared to be reinstalled for every binding.

The shared module lease is a server-owned loader pin, shared by all provider generations and adapter roles belonging to one loaded module instance. Provider-wide quiescence and final provider-context release are separate operations. The quiescence hook stops provider-internal workers after externally initiated calls and accepted tokens have drained. PENDING and FAILURE retain/quarantine the module. SUCCESS still does not release the lease while logical-device/provider-object references remain. Finalization performs the last provider release while the module is pinned, then releases that provider generation's lease reference exactly once.

The API now separates registry errors from quiescence status: stale generations are rejected without invoking provider code; unmet preconditions return PENDING; hook FAILURE quarantines; hook SUCCESS records quiescence. Architecture vectors 89–93 exercise the registration, shared lease, and finalization cases.

Implementation feedback requested: confirm that the planned provider registry can install a descriptor once and associate multiple PhysicalDevice bindings with the same provider object. Also identify the Xlibre loader-owned object that can back one shared lease across several provider generations and DDX callback roles. No implementation work is requested in this spec repository.

Spec commits: `1029787cbf4b7d3f0b8675264e39e9c4527da754`, `63c5339ca702a913f7da55747e877177782492a5`. Exact-tip CI pending.


Provider lifecycle follow-up: reserve provider generations through the registry before constructing descriptors; a failed registration consumes its generation. The module lease must be backed by a stable server-owned Xorg loader-owner record and a real independent loader pin. Quiescence waits until provider-owned objects requiring provider code have been destroyed or safely quarantined; after SUCCESS only the registry-controlled final `release_provider` call may enter provider code. Vectors 94–96 cover this ordering and loader-pin validation. No wire ABI changed.


## Implementation guidance follow-up — 2026-11-04

The exact branch tip before this guidance, `de9ec7ee1d3f92b0d55c8d32a4477637760ec0b9`, passed both required workflows: [wire-layout/request-reply/XGE 41846198875](https://github.com/metux/xav-design/actions/runs/41846198875) and [required checks 41846198977](https://github.com/metux/xav-design/actions/runs/41846198977). Provider registration, generation allocation, module-lease, and quiescence refinements through vectors 89–96 are therefore CI-verified.

The non-normative implementation decomposition and sequencing guidance is now in `spec/device-registry-architecture.md` §8.2. It recommends a XAverius-owned registry, separate discovery/provider/lifetime/Screen/presentation responsibilities, immutable queued observations, serialized state mutation, subscribe-before-scan hotplug reconciliation, provider selection as an explicit publication commit, and staged headless tests before full Xorg integration.

**Implementation agents: please report concrete evidence, not just design agreement:**

1. Which Xlibre object/API can provide a server-owned loader pin that demonstrably prevents the final `dlclose()` after `FreeScreen()`? Include the exact source path/call chain and a minimal unload test. If none exists, confirm whether permanent residency is acceptable for the first implementation.
2. Where can platform/udev hotplug subscription be installed before the initial enumeration, and how will add/remove events be sequenced against the scan? Include the actual hook names for the target Xlibre revision.
3. Which existing DDX data can provide authoritative canonical device identity for each supported bus, including the relationship between primary and render DRM nodes? Identify any device classes that must remain unresolved.
4. Can the current provider split support one provider context with multiple PhysicalDevice bindings, multiple provider contexts from one module, and independent DDX sources observing the same PhysicalDevice? Point to the concrete structures/ownership.
5. Identify any worker, callback, or callback trampoline that is module-global rather than provider-generation-scoped, and explain how its lifetime will be pinned/quiesced.
6. Provide the proposed integration order and tests for hotplug-during-scan, two Screens/one GPU, one Screen/multiple GPUs, delayed callbacks after Screen close, and unload after final Screen removal.

Do not start implementation changes in this specification repository. Record implementation evidence and blockers here; durable protocol/architecture changes belong in the corresponding spec chapters.


## CI confirmation and status refresh — 2026-11-04

The implementation-guidance and borrowed-Screen-pointer clarification at `a66d977b436cb05818a07a847e7c4fc1e8065598` passed both exact-tip workflows: [wire-layout/request-reply/XGE 41848200892](https://github.com/metux/xav-design/actions/runs/41848200892) and [required checks 41848200803](https://github.com/metux/xav-design/actions/runs/41848200803). This is now the latest fully CI-verified architecture/spec baseline. The status, freeze checklist, and open-issues summary have been refreshed accordingly.

No new concrete implementation-agent evidence was present in the coordination file at this check. The outstanding requests above remain open: actual loader pin/dlclose proof, exact subscribe-before-scan hook and event sequencing, authoritative per-bus identity mapping, concrete provider multiplicity ownership, module-global callback/worker inventory, and staged integration evidence.


## Registry API audit — 2026-11-04

The internal API sketch in `spec/device-registry-architecture.md` §7 has been audited for missing return values, failure modes, and lifetime ownership. The updated contract now includes:

- classified registry outcomes (`INVALID_ARGUMENT`, `NOT_FOUND`, `NOT_REGISTERED`, `ALREADY_EXISTS`, `BUSY`, `SHUTTING_DOWN`, `UNSUPPORTED`, `QUARANTINED`, etc.) and initialized output sentinels;
- retained caller references with generation-checked retain/release operations, atomic rollback, and explicit borrowed-input copying;
- server-assigned source, provider, binding, ScreenAttachment, and module-role generations;
- explicit discovery-source and module-role registration, including module-lease retention for DDX topology/discovery/callback bridges;
- generation-addressed provider shutdown/quiescence/finalization and Screen detach retry, so callers can release object handles while retirement remains pending;
- transactional PhysicalDevice XID publication and exact failure rollback;
- provider output ownership, candidate-list release, synchronous result validation, server-assigned async tokens, and completion records without raw Xserver/registry/Vulkan pointers.

Architecture vectors 97–114 exercise invalid inputs, reference races, source/module-role retirement, provider registration failures, binding generations, Screen attachment validation, XID allocation rollback, acquisition during loss, registry shutdown, async callback violations, and shared module-role leases.

**Implementation agents: please compare your current registry/provider API against these additions.** Report every incompatible function signature, missing owner reference, or lifecycle transition that cannot be represented. In particular, confirm how the implementation assigns source/binding/module-role generations, represents module roles independently of Screen/DriverPtr lifetime, and handles a PENDING unregister/detach without retaining caller pointers indefinitely. Do not change wire requests or implement provider failover to accommodate an API mismatch.

These API changes are newer than the last verified baseline `a66d977b436cb05818a07a847e7c4fc1e8065598`; exact-tip CI is pending. No wire ABI or opcode changed.


### Operation-token API follow-up

Section 7 now exposes the server-side token handoff explicitly:

- `GpuRegistryPrepareOperation` allocates a non-reusable token and retains exact provider/binding/PhysicalDevice/Device/resource generations before provider entry.
- `GpuRegistryCommitOperationSubmission` commits acceptance after the provider returns SUCCESS. Completion callbacks that race ahead of this commit are buffered and cannot publish state early.
- `GpuRegistryRejectOperationSubmission` handles synchronous provider failure. A callback or backend acceptance after failure is a provider-contract violation and forces quarantine.
- `GpuRegistryRetireOperationToken` drives a typed PENDING/SUCCESS/FAILURE retirement result. Only SUCCESS after backend access and callback frames are gone releases token-held references; FAILURE quarantines and blocks provider quiescence.

The provider `retire_operation` hook now returns `GpuProviderRetirementResult`, distinct from ordinary operation results and provider-wide quiescence. Architecture vectors 115–119 cover callback-before-commit, sync-failure/late-callback, never-terminalized operations, retirement outcomes, and shutdown/resource-destroy races.

Implementation agents: compare your operation submission/callback path with these four registry transitions. Report whether callbacks can arrive before the provider function returns, how such completions are buffered, and what backend proof your retirement hook provides. A terminal protocol outcome alone is not retirement proof.


## Provider API second-pass audit — 2026-11-04

The second API pass found that the abstract signatures still left provider-local PhysicalDevice handles, async operation identity, and full resource retention underspecified. Section 7 now adds:

- explicit candidate-list and candidate records with provider-generation-local, non-reusable binding IDs; candidate storage is temporary, while native handle mappings remain provider-owned until binding/object/token retirement;
- exact binding ID/generation in logical-device creation and Surface support queries; no provider-native physical handle is stored in the central registry;
- explicit operation kinds for WriteBuffer, ReadBuffer, host SignalSemaphore, QueueSubmit, AcquireNextImage, and QueuePresent;
- a server-owned token record retaining the complete resource-generation set, not merely one primary resource; QueueSubmit must pin its complete validated dependency graph;
- a call-scoped provider token pointer plus copied token ID/generation for callback userdata, avoiding backend callbacks retaining registry pointers;
- typed operation-specific status values (NOT_READY, OUT_OF_DATE, SURFACE_LOST, ALREADY_COMPLETED), bounded immutable completion payloads, and stricter completion identity checks;
- BeginShutdown explicitly closes new operation-token preparation.

Architecture vectors now extend through 131. Section 8.3 adds concrete implementation guidance for candidate maps, token states, resource pin sets, callback counters, and diagnostics.

**Implementation agents: please verify specifically:**
1. Does your candidate enumeration produce a stable provider-local binding ID, and does the provider retain the ID-to-native-handle map after the temporary candidate list is freed?
2. Do your WriteBuffer, ReadBuffer, host SignalSemaphore, QueueSubmit, AcquireNextImage, and QueuePresent paths all use the same prepare/commit-or-reject/complete/retire token lifecycle?
3. Does QueueSubmit retain the full validated command/dependency resource set, including semaphores/fences and all buffers/memory, rather than one primary resource?
4. Can any backend callback retain a raw registry token or provider-context pointer after the entry-point call returns?
5. What exact status mapping is used for AcquireNextImage NOT_READY, presentation OUT_OF_DATE/SURFACE_LOST, and cancellation ALREADY_COMPLETED?

No wire ABI or opcode changed. Latest edits are pending exact-tip CI.


### Completion binding-generation check

A final identity check added the registry-assigned binding_generation to GpuProviderCompletion. A completion must now match both the provider-local binding ID and the registry binding generation, in addition to provider generation, token identity, and PhysicalDevice incarnation. Vector 132 tests stale binding completion rejection. Please ensure callback userdata snapshots both binding identifiers; matching only a provider-local ID is insufficient.

The provider-device reference contract is also now explicit: create_logical_device returns one owned provider-device wrapper reference; retain_device/release_device manage additional async/deferred references; destroy_logical_device destroys the native device once, while wrapper storage remains until all retained references are released. The four typed operation tables remain abstract in this chapter, but their operation declarations must use classified results, initialized outputs, and tokens for every listed async operation.


### Availability and discovery event ordering

A further API review made asynchronous status notifications generation- and sequence-safe. Provider context availability uses a monotonic sequence per provider generation; binding-local availability additionally carries the exact registry binding generation and a sequence scoped to that binding. Effective availability is the conjunction of provider-context availability, binding availability, and physical non-removal. A recovery at one scope cannot clear a failure at another. Older notifications return STALE_EVENT; duplicate same-state notifications are idempotent; conflicting sequence reuse is rejected.

Discovery observations and removal evidence now carry a source_event_sequence captured when the source event occurred. This prevents a delayed removal callback from arriving after a newer add/update and incorrectly removing the current incarnation. The registry derives removal authority from registered source capabilities/trust policy; the evidence struct no longer accepts a caller-supplied authority value. Architecture vectors now extend through 137.

Please verify that your udev/provider adapters preserve event sequence at observation time (not callback dispatch time), and that all binding-scoped provider loss/recovery callbacks carry binding_generation. Also confirm the effective availability state is composed rather than overwritten by a context recovery.


### Complete async resource pin sets

The current six asynchronous operation kinds all require an exact logical-Device generation and a nonempty resource set before provider entry. The spec now states the minimum set by operation: Buffer+Memory for Write/ReadBuffer; Semaphore for host SignalSemaphore; Queue plus the complete validated dependency graph for QueueSubmit; and exact Swapchain plus all backend-accessible image/synchronization/route objects for AcquireNextImage/QueuePresent. Resource IDs must be unique in a token, even across generations. Vector 138 tests missing dependencies and atomic rejection. Please compare the actual resource graph builder against this list; do not treat a primary-resource pointer as a substitute for the retained dependency set.


### Fatal provider result handling

Section 7.1 now defines GPU_PROVIDER_FATAL as immediate provider-generation quarantine: close operation/binding admission, mark only selected PhysicalDevices UNAVAILABLE (never REMOVED), retain provider context/module leases/dependent objects, and forbid normal finalization. GPU_PROVIDER_DEVICE_LOST is logical-Device/operation-scoped and must not mark the PhysicalDevice or provider context unavailable. GPU_PROVIDER_CANCELLED is valid only as the terminal completion of an already accepted cancellable operation. Vector 139 covers these distinctions.

Please confirm the implementation has a quarantine state distinct from QUIESCING and DEVICE_LOST, and that a fatal provider result cannot fall through the ordinary destroy/unload path.


### Retain admission and terminal idempotence

The registry contract now explicitly closes new Retain admission at teardown boundaries (provider shutdown/quarantine, ModuleRole unregister, ScreenAttachment detach) while allowing already-held references to be released. PhysicalDevice tombstones remain referenceable but cannot acquire execution providers. Operation-token transitions now define repeated Commit/Reject/Retire behavior; TryQuiesce after recorded success does not re-enter provider code; duplicate finalization cannot release twice. Vector 140 covers retain/shutdown races and terminal idempotence. Please verify the implementation uses state-checked retain paths rather than a raw unconditional refcount increment.


### Observation replay reference accounting

A repeated ObserveDevice call with the same source generation, event sequence, and semantic payload returns the same observation ID but, on SUCCESS, one additional caller-owned PhysicalDevice reference for that call. It does not duplicate the source observation. The caller must release each returned reference independently. Vector 141 covers the case where the original reference is still held during replay.


### Quarantine hook barrier

A fatal provider-generation quarantine now blocks even the normal quiesce/finalize hooks: TryQuiesceProvider returns QUARANTINED/FAILURE without invoking quiesce_provider, and FinalizeProviderShutdown returns QUARANTINED without release_provider. This prevents further entry into a module after its contract has been violated. Vector 142 checks that provider/context/module/object references remain pinned. Any recovery requires a separately specified server-controlled proof-of-safety path.

## Registry API lifetime addendum — 2026-11-04

The follow-up registry API audit found underspecified provider-context access, nested operation-table storage lifetime, shared module-lease identity, exact source/binding/Screen removal barriers, provider quiescence preconditions, and the call-scoped operation-token pointer rule. These are now specified in [registry API lifetime addendum](spec/registry-api-lifetime-addendum.md), normative alongside §7/§7.1 of `spec/device-registry-architecture.md`. Architecture vectors 143–150 cover the new cases. No wire ABI, opcode, event, or Vulkan capability changed.

Implementation agents: please confirm (a) whether the provider context accessor is generation-checked and borrow-only, (b) where nested provider operation tables live and what pins their code/storage, (c) how loader module-owner aliases are canonicalized to one shared lease, (d) that source/binding/Screen removal SUCCESS is emitted only after callbacks and native-handle users drain, (e) that quiescence is not called before all bindings/tokens/objects/external calls/callback bridges retire, and (f) that providers copy only token scalar IDs and never retain the temporary token pointer. Report exact branch/commit and runtime evidence; source-level intent alone is not acceptance evidence.

## Complete provider-operation matrix — 2026-11-04

The full cross-check against request subopcodes 0–47 found a material API gap: `GpuProviderBufferMemoryOps`, `GpuProviderShaderPipelineOps`, `GpuProviderCommandOps`, and `GpuProviderSynchronizationOps` were only forward-declared and had no concrete operation signatures. The provider operation matrix now defines these tables and maps every assigned request to provider work or explicitly server-only work. It also found and fixes a missing `free_buffer` operation, defines all six async operations, output initialization/rollback, result mapping, surface-capability completeness, and typed DestroyResource dispatch. See [provider-operation-matrix.md](spec/provider-operation-matrix.md); vectors 151–164.

Implementation agents: compare each implemented provider vtable against the normative table declarations. In particular report exact signatures and result types for all four tables; whether Buffer has a distinct `free_buffer`; how DescriptorSet allocation/free and CommandBuffer pool ownership are represented; whether surface capability query returns the full format/mode/limit set; and whether all six async operations use token prepare/commit-or-reject/complete/retire. Also identify any extra backend callbacks that are currently not in the normative table. Do not treat a single generic destroy/dispatch callback as satisfying typed destroy symmetry unless the exact resource-type dispatch and lifetime guarantees are preserved.


## Implementierungsbranch-Inventur gegen Provider-Operationsmatrix — 2026-11-04

Die Spec-Seite hat die tatsächlichen Implementierungsbranches gegen `spec/provider-operation-matrix.md` geprüft, konnte sie in diesem Repository aber nicht identifizieren:

- Sichtbare Branches auf GitHub: `docs/restructure-2026-10-21` (maßgeblich), `docs/split-specification`, `master`, `wip/001`. Es gibt hier aktuell keinen sichtbaren aktiven Implementierungsbranch.
- Der frühere Branch `wip/by-local-agent` war Head von PR #3 und ist inzwischen in die Spec-Branch gemergt. PR #3 enthält Wire-Spec- und Golden-Vector-/Checker-Änderungen für Memory-Properties und Presentation, aber keine Provider-/Xserver-Implementierung.
- `wip/001` und `docs/split-specification` sind divergierte ältere Spec-Stände und werden nicht als Implementierungsnachweis verwendet.
- Es gibt keine offenen Pull Requests in diesem Repository, die einen Implementierungsbranch nennen.

**Blocker für den Matrix-Abgleich:** Die Implementierungsagents müssen den tatsächlichen Repository-Namen, Branch-Namen und exakten Commit-SHA hier melden. Für jeden Provider-Adapter sind mindestens die vier vollständigen Operationstabellen, Buffer-/CommandBuffer-/DescriptorSet-Zerstörung, vollständige Surface-Capability-Ergebnisse, die sechs Async-Tokenpfade und die Retain-/Retire-/Quiesce-Barrieren anhand konkreter Quellpfade und Tests zu belegen. Bitte keine bloßen Absichtserklärungen oder Spec-Branch-SHAs melden.

Bis diese Referenzen vorliegen, gibt es keinen belegten Implementierungswiderspruch, den die Spec korrigieren könnte. Die Matrix bleibt normative Soll-Schnittstelle; die fehlende Implementierungsprüfung ist ein offener Integrations-/Nachweis-Punkt und keine Freigabe, die Matrix abzuschwächen.


### Nachprüfung der Agent-Rückmeldungen und Implementierungsquellen — 2026-11-04

Die aktuelle Koordinationsdatei wurde erneut vollständig nach Agent-Einträgen durchsucht. Seit der Aufforderung zum VTable-Abgleich ist keine Rückmeldung im vereinbarten Format eingetragen worden. Auch die GitHub-Issue-Kommentare und offenen PRs des Spec-Repositories enthalten keine technische Agent-Antwort.

Zusätzliche Repository-Prüfung:
- Das einzige weitere für den Xserver passende, für den verbundenen GitHub-Zugang sichtbare Repository ist `metux/xorg-xserver`.
- Dessen Branch-Liste enthält keinen XAverius-/GPU-/Vulkan-Implementierungsbranch; `master` steht auf `610e91dc5f34e64036b7cdd08f0f953a672fcb36` (letzter Commit 2025-06-06). Die Code-Suche nach `XAverius` und `GpuProvider` liefert dort keine Treffer.
- Es gibt in diesem Repository keine offenen PRs mit Provider-Implementierung.

Damit gibt es weiterhin keine tatsächlichen Provider-VTables, die gegen die Matrix verglichen werden könnten. Bitte im nächsten Agent-Update das Repository explizit nennen (falls nicht `metux/xorg-xserver`), dazu Branch + vollständigen Commit-SHA und Quellpfade der VTables. Falls der Code nur lokal oder in einem nicht verbundenen Repository liegt, muss er als Branch/PR oder als Quelltextauszug bereitgestellt werden. Bis dahin bleibt dies ein fehlender Prüfgegenstand, kein bestätigter Spec-Konflikt.


## Logical and provider-native Surface split — 2026-11-04

A cross-check of the presentation request layout against the provider API found that `CreateSurface` has no Device/provider selector, while the logical Surface is connection-owned and may be queried against Devices on different GPUs. The earlier matrix wording could be read as creating a provider-native Surface during `CreateSurface`, which would require an arbitrary provider choice.

The normative contract now makes the distinction explicit:
- `CreateSurface` is server-only and captures the exact Window/Screen identity.
- A provider-native Surface is materialized lazily for the exact provider generation selected by `GetSurfaceCapabilities` or `CreateSwapchain`.
- The provider-native wrapper is scoped to (provider generation, logical Surface generation), shared across Devices served by that provider, and not shared across provider generations.
- `UNSUPPORTED` during native Surface creation means no present support for that provider/Surface pair; the capability reply remains SUCCESS with all queue-family support bits clear, while direct CreateSwapchain returns UNSUPPORTED_CONFIGURATION without publishing its target XID.
- `DestroySurface` retires all native wrappers for that logical generation, and outstanding wrappers block provider quiescence.

Conformance vectors 165–168 were added. No wire layout, opcode, event, or capability assignment changed. Implementation agents: please verify the actual Surface cache key, lazy creation path, provider-generation sharing, unsupported result mapping, and DestroySurface/quiescence accounting. Report exact repository, branch, commit SHA, source paths, and tests; no implementation source has yet been supplied for this check.


### Surface capability ABI boundary — 2026-11-04

A second consistency pass compared the provider capability-result requirement with the actual v0.1 GetSurfaceCapabilities reply and CreateSwapchain request. The wire contract exposes format/color-space pairs, present modes, image-count and extent bounds, image-usage flags, and per-queue-family support. It does not expose image transforms or composite-alpha modes and gives the client no selectors for them. The provider contract now requires exactly the v0.1 capability dimensions; any backend-required transform/composite-alpha choice is internal to the provider during Swapchain creation and native Vulkan enums are never exposed.

The presentation chapter also explicitly distinguishes the cached provider-native Surface backing object from a persistent PresentationRoute: capability probing may materialize/cache the former but MUST NOT create/pin the latter or reserve bridge resources. Vector 169 covers the capability ABI boundary. No wire ABI changed. Implementation agents should report the internal transform/composite-alpha policy and confirm it cannot contradict the wire-visible constraints.


### Provider-generation shutdown and cached native Surfaces — 2026-11-04

One additional lifetime case is now explicit: provider shutdown must retire every native Surface wrapper cached by that provider generation after its dependent Swapchain/route/query references drain, even if the connection-owned logical Surface remains live. Only that provider-generation cache entry is removed; the logical Surface remains valid, and an existing Device is never failed over to another provider. A future Device on another provider generation may materialize a separate native Surface. Vector 170 covers this isolation.

### DDX-owned PhysicalDevice registration and direct operation-vector dispatch — 2026-11-04

The registry architecture has been clarified: in the Xlibre/Xorg profile, each DDX is responsible for registering every PhysicalDevice it serves, including headless/render-only/compute-only devices not attached to a Screen. Platform/udev supplies identity and hotplug evidence; it is not a second executable inventory. There is no independent Vulkan-ICD candidate inventory in this profile.

The selected PhysicalDevice binding now owns/references its immutable typed operation vectors, per-device backend context, and native physical-device handle. Request dispatch calls those vectors directly. The historical BackendProvider term is retained only for shared implementation/module lifetime, callback admission, and quiescence control; it is not an extra per-device dispatch object and must not be looked up on each operation. See `spec/device-registry-architecture.md` and `implementation-notes/ddx-device-registration.md`.

**Implementation agents:** Please verify your current design against this model and report: (1) exact repository/branch/SHA, (2) where the DDX enumerates *all* served PhysicalDevices, (3) where each PhysicalDevice stores its call vectors/context/native handle, (4) how non-Screen devices are registered, and (5) how ScreenAttachment teardown is separated from device/backend lifetime. If your implementation currently has a standalone provider object in the dispatch path, explain what lifetime responsibility requires it and whether it can be reduced to a shared module-role control record. Do not change the wire ABI or invent an independent ICD inventory.
