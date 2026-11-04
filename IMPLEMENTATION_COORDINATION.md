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
