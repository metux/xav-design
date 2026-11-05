# XAverius Implementation Coordination

**Live hand-off only.** Historical discussion and superseded audit snapshots are preserved in [IMPLEMENTATION_COORDINATION_HISTORY_2026-11-04.md](IMPLEMENTATION_COORDINATION_HISTORY_2026-11-04.md). Do not append long audit narratives here.

## Authoritative repositories

- Spec: `metux/xav-design`, branch **`docs/restructure-2026-10-21`**. Always sync this branch before acting. `master`, `wip/001`, and old spec branches are not authoritative.
- Xserver implementation: `X11Libre/xserver`, branch **`wip/xaverius`**.
- This repository is the specification/coordination workspace. Do not implement Xserver source here.
- Agents poll this file every five minutes. Treat the latest active assignment and its linked task file as instructions.

## Immediate decision — discard current registry and rebuild from clean baseline

**ACTIVE — rollback required before further Xserver implementation.**

- Target: `X11Libre/xserver:wip/xaverius`.
- Current audited branch tip before rollback: `deb0e445001389be031fa7e006e3e2e216616b50`.
- Exact pre-inventory/pre-registry rollback target: `f6f3e87aa81724208496d539e40d2eee2c3d2641` (parent of first inventory commit `00fcd15955a0c2bd810034cc8b5b3bf1731d996a)).
- Verified target tree contains only the original seven Xaverius files and no registry/inventory implementation.
- **ROLLBACK COMPLETE.** A subsequent independent read of the remote ref verified `refs/heads/wip/xaverius = f6f3e87aa81724208496d539e40d2eee2c3d2641`. The initial ref-update attempt returned HTTP 403, but the exact target is now live. Do not repeat the reset/push. The seven-file Xaverius tree was verified at this commit.
- Full implementation plan: [xserver-registry-rebuild-plan-2026-11-05.md](implementation-notes/xserver-registry-rebuild-plan-2026-11-05.md), commit `6c3965315b213eb428045bc08f7c061359a9ebf4`.

**Mandatory design point:** every per-device registration MUST pass a versioned `XaveriusPhysicalDeviceOps` structure containing that device's callbacks, together with structured identity, exact native handle, per-device context and owning ModuleRole generation. The registry copies/validates the immutable typed operation tables, queries the snapshot through that exact binding, and publishes only after complete validation. The four typed operation tables and top-level callbacks follow `spec/provider-operation-matrix.md`; ModuleRole-wide quiescence remains a separate lifetime/control API, not a PhysicalDevice dispatch callback.

Do not patch the broken registry in place, cherry-pick its implementation commits, or continue Phase B. Rebuild in the ordered phases and gates in the plan. Preserve existing names/formatting unless a narrowly justified type/API addition requires otherwise.

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

Read and execute the complete task: [`implementation-notes/phase-a-ddx-discovery.md`](implementation-notes/phase-a-ddx-discovery.md). Latest task commit: `15485e3183e4c1c78ff3754983d50d9b80caa910`. Mandatory detailed corrections: [`implementation-notes/phase-a-ddx-corrections.md`](implementation-notes/phase-a-ddx-corrections.md), commit `61cf71817878ac48b0fd1d9c7a9848739b802ff8`. Both files are part of the active assignment.

The task requires:
- a real DDX-wide enumeration/registration pass independent of `ScreenPtr`, `ScrnInfoPtr`, and Screen creation;
- registration of every DDX-served device, including no-Screen devices;
- removal of the three PhysicalDevice callbacks from `XaveriusDDXOps`;
- no lazy discovery from client requests;
- initial hotplug/identity observation before the DDX scan, ordered event reconciliation, and a barrier that remains closed while any configured initial pass is PENDING; terminal adapter failure is accounted for without fabricating removal or blocking independent completed devices indefinitely;
- concrete modesetting integration or a precise evidence-based blocker (no guessed `PreInit`/`ScreenInit` hook); the verified target-tree window is the beginning of `xf86BusConfig()`, after DDX modules/`DriverRec` registration and before Screen-oriented probes; the task requires a once-per-module-generation DDX callback or equivalent minimal seam;
- startup-event detail verified against the target tree: `config_udev_pre_init()` enables monitor reception before `xf86BusProbe()`, but normal `SetNotifyFd()` delivery is installed only later in `config_udev_init()` during `InitInput()`; queued events therefore need explicit early reconciliation before initial publication. The existing platform DRM scan matches `card[0-9]*`, not render nodes, and is not the executable inventory;
- minimal diffs only: preserve existing names, file layout, formatting and coding style; no cosmetic renames, broad reformatting or unrelated refactoring; justify every necessary rename or structural change;
- reproducible A1–A9 tests, including the normative subscribe-before-scan/startup discovery barrier and event-race behavior, exact build/test commands and a structured agent report;
- mandatory C1–C10 corrections in [`implementation-notes/phase-a-ddx-corrections.md`](implementation-notes/phase-a-ddx-corrections.md): safe callback ABI/version gate; classified pass result and per-module-generation once guard; DDX-owned modesetting enumeration with canonical DRM correlation (no global `/dev/dri` scan or `renderD0..31`); complete typed binding before publication; one failure-atomic DIX resource insertion and canonical destructor/shutdown path; explicit FD/context/reference ownership; exported extension/resource-type initialization; portability/SDK-link fixes; removal or fail-closed treatment of unauthorized Compute Memory handlers; targeted regression tests for each correction.

**Forbidden:** first-Screen/first-GPU selection, output/connector-gated registration, per-Screen inventory, a Provider dispatch object, capability snapshots masquerading as operation vectors, last-writer-wins rebinding, fake identities/capabilities, or claiming tests without evidence.

**Gate:** Phase B is not authorized until Phase A is independently audited and marked ACCEPTED here. If the complete-binding registry API is missing, report the exact gap and keep the adapter seam honest; do not invent a temporary competing API.

## Latest registry re-audit — 2026-11-05

- Latest inspected Xserver tip: `deb0e445001389be031fa7e006e3e2e216616b50` (parent `98ce6f6f281a8b8001d967bafd3debe8ea4db4fa`). Full source/history audit: [phase-a-registry-audit-2026-11-05.md](implementation-notes/phase-a-registry-audit-2026-11-05.md), audit commit `931005ab36c864d6947a0465226c03f68f336b91`.
- **Registry model is NOT ACCEPTED and currently unusable.** `XaveriusRegisterDevice()` regressed to a capabilities-only argument; identity, native handle, per-device context, typed ops and ModuleRole/binding generation are absent. Identity is fabricated from vendor/device/API/driver version fields.
- `registry.c` still calls `AddResource()` twice for one XID, publishes before deep-copy completion, and can free an object still referenced by DIX. The commit claiming to remove the duplicate did not remove either call.
- `xaverius_device_init()` has no call site, so the PhysicalDevice resource type is not initialized. RegistryFini and DevicesFini have contradictory ownership/order and can double-free or traverse stale list entries. `init.c` and `xaverius.c` contain competing extension init/fini implementations.
- The internal model has overlapping `XaveriusDeviceRec`, `XaveriusDeviceCapabilities`, unused `XaveriusPhysicalDeviceRec`, and unused `PhysicalDeviceInfoRec` types. `provider_handle` remains as an unowned Provider remnant.
- No current DDX call site invokes `XaveriusRegisterDevice()`; modesetting constructs identity/capability locals and discards them, explicitly deferring registration to Phase B. This violates Phase A.
- History shows the critical regression at `6dffb09bf00e807c90395348ba4c65e4b80ef976`, which dropped identity/native handle/context and disabled modesetting registration. The subsequent `98ce...` and `deb0...` commits did not restore the contract or initialize the resource type.
- **Required:** agents must stop Phase B, repair the single type/binding model and lifecycle per R1–R9 in the audit, then satisfy existing C1–C10/A1–A9. Preserve names/formatting unless a type consolidation is required and justified. Do not edit Xserver source from this spec workspace.

## Current implementation review

- Latest inspected Xserver tip: `189eac7532db7530f70a68f2e659216aa19df626` (sequence: `4c35fcce487f95b48252f8cf696504cbc8ca2feb` Phase-A fixup, `8f0266fd21bf6c0daf699c6fc4fbec06ad830fab` operation-table declarations, `189eac7532db7530f70a68f2e659216aa19df626` Compute Memory handlers).
- **Phase A audit: NOT ACCEPTED; Phase B remains unauthorized.** The callback moved to the beginning of `xf86BusConfig()`, but the implementation still fails critical requirements. The detailed repair contract is C1–C10 in `implementation-notes/phase-a-ddx-corrections.md`:
  - `DriverRec::RegisterXaveriusDevices` is read with a NULL check only; this is not ABI-safe for old smaller binary DriverRec objects. There is no once-per-module-generation guard. Its callback type returns `void`, so it cannot report the required COMPLETE/PENDING/UNAVAILABLE/FAILED pass result. The modesetting callback ignores `drv` and scans global `/dev/dri` paths rather than enumerating devices actually served by a DDX-owned context.
  - The claimed `config_udev_init()`-before-`xf86BusConfig()` ordering is false: `config_udev_init()` runs later in `InitInput()`. No early event drain/reconciliation or startup barrier was implemented.
  - The modesetting scan tries `renderD0..renderD31`, not normal Linux render-node numbers, and does not use canonical DRM device enumeration.
  - Non-PCI identity evidence is insufficient; zero BDF and absent UUID cannot distinguish non-PCI devices. Comments claiming a devnode/`drmGetBusid` fallback do not implement canonical stable identity.
  - Registry registration calls `AddResource()` twice for the same XID/type. The first call publishes before deep-copy completion; the second conflicts, and failure paths can leave a dangling DIX resource. PhysicalDevice resource type initialization is unproven.
  - The extension init symbol was previously found static/mismatched; the latest inspected source has a non-static definition, but it still needs exact declaration/registration-table/link verification and canonical init/fini ownership.
  - The registry stores fd/context but not the immutable typed operation vectors or exact ModuleRole/binding generation. Header-only operation-table declarations do not satisfy the direct-binding contract.
  - fd/context ownership on duplicate, failure, and shutdown is undefined; duplicate identity must not return unconditional success without validating the exact binding and disposing/retaining supplied resources correctly.
- The branch also contains Compute Memory handlers added before Phase A acceptance. The audited handlers use hard-coded alignment/memory-type masks and return success for ReadBuffer/WriteBuffer without actual backend execution. Remove them from the Phase-A submission or make them fail closed; do not continue Phase B work.
- Xserver workflow [41921533156](https://github.com/X11Libre/xserver/actions/runs/41921533156) for `189eac7` failed: Ubuntu/DragonFlyBSD/RHEL registry builds reported redundant `strlcpy`/`strlcat`/`strndup` declarations under `-Werror` (plus DragonFly/RHEL `timingsafe_memcmp`/`CSRG_BASED` issues); the SDK image failed linking `XaveriusExtensionInit`; macOS failed because extension sources pulled in `pciaccess.h` through `xf86.h`. The overall workflow was not green. No A1–A9 harness or structured agent report was present in that audit.
- Full findings and precise corrective instructions are in [the follow-up audit history](IMPLEMENTATION_COORDINATION_HISTORY_2026-11-04.md). Keep the gate closed until the DDX callback ABI/once guard, early udev reconciliation, canonical identity, atomic DIX publication, exported init symbol, complete binding/lifetime contract, A1–A9 tests, and exact-tip build are all independently verified.

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
