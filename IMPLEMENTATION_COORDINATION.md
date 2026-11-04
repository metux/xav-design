# XAverius Implementation Coordination

**Live hand-off only.** Historical discussion and superseded audit snapshots are preserved in [IMPLEMENTATION_COORDINATION_HISTORY_2026-11-04.md](IMPLEMENTATION_COORDINATION_HISTORY_2026-11-04.md). Do not append long audit narratives here.

## Authoritative repositories

- Spec: `metux/xav-design`, branch **`docs/restructure-2026-10-21`**. Always sync this branch before acting. `master`, `wip/001`, and old spec branches are not authoritative.
- Xserver implementation: `X11Libre/xserver`, branch **`wip/xaverius`**.
- This repository is the specification/coordination workspace. Do not implement Xserver source here.
- Agents poll this file every five minutes. Treat the latest active assignment and its linked task file as instructions.

## Normative architecture — short form

- One process-wide XAverius registry owns canonical PhysicalDevice identities, generations, publication and protocol XIDs.
- Every DDX registers every executable PhysicalDevice it serves, including headless/render-only/compute-only and Screen-unattached devices. Platform/udev supplies identity/hotplug evidence, not a second executable inventory.
- The exact PhysicalDevice binding owns/references its native handle, per-device context and immutable typed operation vectors. Request dispatch uses that binding directly.
- A shared `GpuModuleRole` is lifetime/admission/quiescence control only; it is not a per-device Provider or dispatch proxy.
- ScreenAttachment is separate, non-owning, and generation-checked. Screen close detaches topology only; it never unregisters a shared PhysicalDevice.
- Identity ambiguity/conflict remains unpublished. Never merge snapshots, operation vectors, handles or contexts. No transparent binding failover in v0.1.
- Startup hotplug observation precedes initial scan; reconcile ordered events. Initial inventory publication does not wait for Screen creation, RandR, or a window.
- Async operations require exact generation/resource pins, token prepare/commit-or-reject/complete/retire, callback-return proof, and quarantine when quiescence is uncertain.

Normative detail: `spec/devices.md`, `spec/device-registry-architecture.md`, `spec/registry-api-lifetime-addendum.md`, `spec/provider-operation-matrix.md`, and `implementation-notes/ddx-device-registration.md`.

## Active assignment — Phase A DDX-wide discovery

**ACTIVE — NOT ACCEPTED**

**Assigned target:** `X11Libre/xserver:wip/xaverius`.

Read and execute the complete task: [`implementation-notes/phase-a-ddx-discovery.md`](implementation-notes/phase-a-ddx-discovery.md). Latest task commit: `cab616b1f67d5abeb4e030889404adeb50c507d5`. It supersedes all older Phase A task wording.

The task requires:
- a real DDX-wide enumeration/registration pass independent of `ScreenPtr`, `ScrnInfoPtr`, and Screen creation;
- registration of every DDX-served device, including no-Screen devices;
- removal of the three PhysicalDevice callbacks from `XaveriusDDXOps`;
- no lazy discovery from client requests;
- initial hotplug/identity observation before the DDX scan, ordered event reconciliation, and a barrier that remains closed while any configured initial pass is PENDING; terminal adapter failure is accounted for without fabricating removal or blocking independent completed devices indefinitely;
- concrete modesetting integration or a precise evidence-based blocker (no guessed `PreInit`/`ScreenInit` hook); the verified target-tree window is the beginning of `xf86BusConfig()`, after DDX modules/`DriverRec` registration and before Screen-oriented probes; the task now requires a once-per-module-generation DDX callback or equivalent minimal seam;
- startup-event detail verified against the target tree: `config_udev_pre_init()` enables monitor reception before `xf86BusProbe()`, but normal `SetNotifyFd()` delivery is installed only later in `config_udev_init()` during `InitInput()`; queued events therefore need explicit early reconciliation before initial publication. The existing platform DRM scan matches `card[0-9]*`, not render nodes, and is not the executable inventory;
- minimal diffs only: preserve existing names, file layout, formatting and coding style; no cosmetic renames, broad reformatting or unrelated refactoring; justify every necessary rename or structural change;
- reproducible A1–A9 tests, including the normative subscribe-before-scan/startup discovery barrier and event-race behavior, exact build/test commands and a structured agent report.

**Forbidden:** first-Screen/first-GPU selection, output/connector-gated registration, per-Screen inventory, a Provider dispatch object, capability snapshots masquerading as operation vectors, last-writer-wins rebinding, fake identities/capabilities, or claiming tests without evidence.

**Gate:** Phase B is not authorized until Phase A is independently audited and marked ACCEPTED here. If the complete-binding registry API is missing, report the exact gap and keep the adapter seam honest; do not invent a temporary competing API.

## Current implementation review

- Last inspected Xserver tip: `89df8ba0bc41dbb4b291b2242b9945661bb47fad`.
- `89df8ba` only removes a redundant include-wrapper header; it does not implement Phase A.
- At that tip, `XaveriusDDXOps` still contains the three device callbacks; no DDX-wide registration caller exists; modesetting has no XAverius registration call; `XaveriusRegisterDevice(identity, callbacks)` still overwrites callbacks for duplicate identity.
- Phase A audit: NOT ACCEPTED. Detailed source findings and the acceptance matrix are in the history archive; the active acceptance criteria are in the dedicated task file.
- No agent response with a new implementation SHA, registration call site, tests or build evidence has yet been accepted.

## Other open implementation evidence requests

Do not let these distract from Phase A, but preserve them for subsequent phases:

1. Exact Xorg loader object/call chain that provides an independent module pin preventing final `dlclose()`; include an unload test or state whether permanent residency is the initial policy.
2. Actual subscribe-before-scan hotplug hook and event sequencing in the target Xserver revision.
3. Canonical identity evidence for supported buses and primary/render-node correlation; identify unresolved classes.
4. Concrete ownership for one DDX context serving multiple devices, multiple contexts per module, and multiple DDX sources observing one PhysicalDevice.
5. Inventory of module-global workers/callbacks and their generation-scoped quiescence.
6. Exact conformance of all DDX operation tables and six asynchronous token paths to `spec/provider-operation-matrix.md` and the registry lifetime addendum.

Do not weaken normative requirements to accommodate an implementation shortcut. Report concrete source paths, function signatures, commit SHAs and tests.

## Agent report format

Append a concise report under the relevant active task, using:

- **Agent / repository / branch / commit:** full SHA and parent SHA.
- **Files changed:** paths and purpose.
- **Interfaces/call sites:** exact symbols and ownership.
- **Tests:** exact commands, exit status, results; identify PASS/FAIL/BLOCKED individually.
- **Open blockers:** precise missing contract or lifecycle evidence.

Do not report a spec CI pass as evidence that the Xserver implementation builds or works.

## Specification CI status

Latest fully CI-verified architecture baseline recorded: `a66d977b436cb05818a07a847e7c4fc1e8065598`, workflows [41848200892](https://github.com/metux/xav-design/actions/runs/41848200892) and [41848200803](https://github.com/metux/xav-design/actions/runs/41848200803), both successful. Newer registry API lifetime and operation-matrix refinements were pending exact-tip CI at the last recorded check. Documentation-only coordination commits do not validate Xserver source.
