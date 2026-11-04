# Project status

**Project:** XAverius — network-transparent Vulkan access over X11  
**Specification branch:** `docs/restructure-2026-10-21`  
**Latest exact-tip CI-verified tip:** `4eb0d35938def3f74de579a7bb2e7729a304325f`  
**Status:** Normative v0.1 specification work is substantially complete; the latest verified static CI baseline is green; later status-document refreshes are pending exact-tip CI. Runtime implementation acceptance remains open.

The previous chronological work log is preserved in [project-status-history-2026-11-04.md](PROJECT_STATUS_HISTORY_2026-11-04.md). This file is the live summary; durable protocol rules belong in the normative specification, not here.

## Current verified baseline

- Exact-tip CI: [workflow 41842074182](https://github.com/metux/xav-design/actions/runs/41842074182) — SUCCESS on `4eb0d35938def3f74de579a7bb2e7729a304325f`.
- Results: 4,963 wire-layout checks, 72 Timeline regression tests, and 693 Python tests passed. Required handler/backend checks, shared-header compilation, XCB client prototype build, request/reply/XGE validation, and required-check audit also passed; all 19 workflow steps completed successfully.
- This verifies the Xlibre/Xorg adapter-role and lifecycle contract, including architecture vectors 61–66, in addition to the previously verified logical-Device PresentationRoute binding, evidence-bearing physical-removal API, generation-checked provider status transitions, and registry result classifications. All 19 workflow steps passed: 4,963 wire-layout checks, 72 Timeline regressions, 693 Python tests, header/client builds, request/reply/XGE validation, backend-discovery/handler/callback audits, and required-check audit. Later source-mapping documentation (`d070c735`) and vectors 67–69 (`a9054463`) are newer and pending exact-tip CI.
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
