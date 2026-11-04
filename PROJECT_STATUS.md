# Project status

**Project:** XAverius — network-transparent Vulkan access over X11  
**Specification branch:** `docs/restructure-2026-10-21`  
**Latest exact-tip CI-verified tip:** `72f3f17f3e7ea336658ba59ed5ed93a65805e3a9`  
**Status:** Normative v0.1 specification work is substantially complete; exact-tip static CI is green through `72f3f17`. Provider registration/module-lease lifecycle refinements at `1029787` and `63c5339` are newer and pending exact-tip CI. Runtime implementation acceptance remains open.

The previous chronological work log is preserved in [project-status-history-2026-11-04.md](PROJECT_STATUS_HISTORY_2026-11-04.md). This file is the live summary; durable protocol rules belong in the normative specification, not here.

## Current verified baseline

- Exact-tip CI: [workflow 41844649170](https://github.com/metux/xav-design/actions/runs/41844649170) — SUCCESS on `72f3f17f3e7ea336658ba59ed5ed93a65805e3a9`.
- Required wire-layout, Timeline, Python, shared-header, XCB client, request/reply/XGE, backend-discovery/handler/callback, and required-check gates passed.
- This includes vectors 76–78 and the multi-provider ownership refinement vectors 79–88 from `c88668e023ba31fa38293dba4aef5a827adedb64`, which also passed exact-tip workflow [41844488352](https://github.com/metux/xav-design/actions/runs/41844488352). The newer explicit provider-registration, module-lease retain/release, finalization-order, and quiescence-result API refinement at `63c5339ca702a913f7da55747e877177782492a5` adds vectors 89–93 and is pending exact-tip CI.
- These results establish static/specification consistency only. They do not establish live X11/XGE interoperability or runtime Vulkan backend conformance.

## Protocol and profile status

- The central request registry contains 48 assignments: bootstrap `QueryVersion` at subopcode 0, compute-baseline requests 1–40, and presentation-capable-profile requests 41–47.
- The initial implementation target remains compute-only. Presentation requests/events are separately profile-gated; their assignments do not imply server support.
- The normative request/reply/event layouts, resource lifecycle, asynchronous outcomes, error precedence, numeric registries, provider operations, and cross-document conformance contracts have been systematically audited.
- See [the freeze checklist](spec/freeze-checklist.md) for the exact freeze gates and [open issues](spec/open-issues.md) for implementation acceptance work.

## Physical-device inventory and provider architecture

The server-wide inventory is independent of Screen initialization:

1. Discovery sources submit identity observations; the registry canonicalizes hardware identity and rejects ambiguous matches rather than silently merging them.
2. BackendProviders separately register provider-local execution bindings. Registration order does not select the provider.
3. The server selects one eligible provider, obtains its complete immutable snapshot, and only then publishes a PhysicalDevice XID.
4. DDX/Screen drivers report generation-checked ScreenAttachments. A Screen may attach to multiple GPUs and a GPU to multiple Screens; this does not imply WSI support.
5. Provider loss, Screen detach, DRM-node disappearance, and confirmed physical removal are distinct lifecycle inputs. v0.1 has no transparent provider failover.

The detailed contracts, suggested registry API, driver-facing responsibilities, Xlibre/Xorg adapter roles, startup barrier independent of Screen initialization, hotplug scan/event reconciliation, generation-checked provider state transitions, and architecture vectors are in [device-registry architecture](spec/device-registry-architecture.md). The provider operation and lifecycle contracts are in [devices](spec/devices.md) and [resource lifetime](spec/resource-lifetime.md).

## Open implementation acceptance gates

- [ ] Live X11/XGE interoperability: extension discovery, dynamic major opcode, XAverius QueryVersion, GEQueryVersion, SelectEvents, event framing/masks, byte order, and connection isolation. Follow [the XGE test plan](spec/xge-interoperability-test-plan.md).
- [ ] End-to-end compute execution against a real Vulkan backend: upload visibility, dispatch, synchronization, readback, and resource teardown.
- [ ] Runtime lifecycle/failure behavior: Device loss, provider unavailability, late callbacks, disconnect, delayed release/quarantine, semaphore/fence races, and exactly-once terminal outcomes.
- [ ] If presentation is implemented: Window/Surface lifetime, swapchain creation, acquire/present/release, resize/out-of-date, terminal events, and teardown.
- [ ] Implementation-agent Phase 1 ship confirmations and a named shared integration-interface owner are still coordination sign-offs; see [IMPLEMENTATION_COORDINATION.md](IMPLEMENTATION_COORDINATION.md).

These are implementation/conformance gates, not unresolved wire-design decisions. No implementation work is authorized by this specification repository unless explicitly requested.

## Working rules

1. Work on `docs/restructure-2026-10-21`; do not update `master` unless explicitly requested.
2. Keep commits focused and report the exact branch, commit, CI evidence, and remaining unverified behavior.
3. Keep protocol rules in normative chapters; keep this file concise and coordination notes operational.
4. Treat registries as append-only. Never guess or reuse unassigned values.
5. Preserve the distinction between server request order and GPU dependency synchronization.
6. Do not infer PhysicalDevice identity, provider selection, or presentation support from the first XAverius-capable Screen.
7. Static CI is not runtime conformance.

## Authoritative references

- [Specification index](spec/README.md)
- [Freeze checklist](spec/freeze-checklist.md)
- [Open issues and deferred work](spec/open-issues.md)
- [Physical-device registry architecture](spec/device-registry-architecture.md)
- [Live implementation coordination](IMPLEMENTATION_COORDINATION.md)
- [Historical status log](PROJECT_STATUS_HISTORY_2026-11-04.md)


The Xlibre/Xorg integration profile now specifies platform-discovery, DDX-topology, and Vulkan-provider adapters; a Screen-independent startup barrier; hotplug reconciliation; late discovery; and safe Screen/module teardown. The non-normative mapping to current XLibre source hooks is now documented in §8.1; runtime validation against a built Xlibre server and real driver-supplied identity evidence remains unverified.


The registry architecture now makes provider unload a two-phase quiescence operation: per-Screen close detaches only topology, accepted operation retirement includes callback return, and provider-wide quiescence must prove no callback/worker can enter module code before the final provider/module lease is released. An unquiesceable provider is quarantined. The normative hook `quiesce_provider` and its result type are in the provider operation-table sketch; exact-tip CI is pending at `5d3c0f69`.


The source-level loader review adds one important implementation constraint: Xorg's duplicated `ModuleDesc` for a `ScrnInfo` shares the module handle and is not an independent provider pin; final `LoaderUnload()` calls `dlclose()`. Provider code therefore needs a separate loader/module lease beyond Screen references. Vectors 76–77 cover module unload while provider objects and callbacks remain live. Commit `3a42c1a` adds this refinement and awaits exact-tip CI.


The Screen-close contract was tightened further: asynchronous callbacks cannot retain raw Xserver Screen/ScrnInfo pointers or FreeScreen-owned storage. They use copied immutable values or a detached, generation-checked ScreenAttachment context with no borrowed Screen pointers. Architecture vector 78 tests callback completion after Screen deletion. Commit `6f01fcb00e9c6ac46cad72e0c52434494e814413` is pending exact-tip CI.


## Multi-provider ownership and teardown — 2026-11-04

The registry architecture now makes multiplicity explicit: one provider generation may bind many PhysicalDevices; one PhysicalDevice may have bindings from multiple providers; one module may own multiple independent provider generations and adapter roles. Each (provider generation, PhysicalDevice incarnation) has at most one executable binding. Discovery observations remain source-owned, and withdrawing one source cannot remove another source's evidence or binding. The v0.1 selected-provider rule remains unchanged: exactly one immutable snapshot, no capability union, and no transparent failover when the selected provider is removed or unavailable.

Provider shutdown now has an explicit generation-scoped admission-close step, followed by exact binding/observation/ScreenAttachment withdrawal, accepted-operation drain, per-provider quiescence, and per-generation module-lease release. Quiescence of one provider does not authorize unloading a shared module while another provider or adapter role remains live. Architecture vectors 79–88 cover these cases. Spec commit `c88668e023ba31fa38293dba4aef5a827adedb64`; exact-tip CI [41844488352](https://github.com/metux/xav-design/actions/runs/41844488352) is pending.


## Provider registration and final module-lease release — 2026-11-04

The provider API now separates registering a provider generation from registering its PhysicalDevice bindings. One descriptor/context/module lease is installed once per provider generation; additional bindings refer to that registered provider. The server assigns the non-reusable provider generation. Module leases are server-owned loader pins shared by all provider and adapter roles from the same loaded module. Quiescence and finalization are separate: provider-internal workers are stopped by `quiesce_provider`; PENDING/FAILURE retain the lease; SUCCESS does not release it until provider objects and references are gone. Finalization calls the last provider release while the module remains pinned, then drops the generation's lease reference exactly once. Architecture vectors 89–93 cover these transitions. Commits `1029787` and `63c5339`; exact-tip CI pending.
