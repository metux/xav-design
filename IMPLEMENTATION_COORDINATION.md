# XAverius Implementation Coordination

**Live hand-off only.** Historical discussion and superseded audit snapshots are preserved in [IMPLEMENTATION_COORDINATION_HISTORY_2026-11-04.md](IMPLEMENTATION_COORDINATION_HISTORY_2026-11-04.md). Do not append long audit narratives here.

## Authoritative repositories

- Spec: `metux/xav-design`, branch **`docs/restructure-2026-10-21`**. Always sync this branch before acting. `master`, `wip/001`, and old spec branches are not authoritative.
- Xserver implementation: `X11Libre/xserver`, branch **`wip/xaverius`**.
- This repository is the specification/coordination workspace. Do not implement Xserver source here.
- Agents poll this file every five minutes. Treat the latest active assignment and its linked task file as instructions.

## Rollback record — completed

**COMPLETE — no further rollback action is authorized or required.**

- Target: `X11Libre/xserver:wip/xaverius`.
- Current audited branch tip before rollback: `deb0e445001389be031fa7e006e3e2e216616b50`.
- Exact pre-inventory/pre-registry rollback target: `f6f3e87aa81724208496d539e40d2eee2c3d2641` (parent of first inventory commit `00fcd15955a0c2bd810034cc8b5b3bf1731d996a)).
- Verified target tree contains only the original seven Xaverius files and no registry/inventory implementation.
- **ROLLBACK COMPLETE.** A subsequent independent read of the remote ref verified `refs/heads/wip/xaverius = f6f3e87aa81724208496d539e40d2eee2c3d2641`. The initial ref-update attempt returned HTTP 403, but the exact target is now live. Do not repeat the reset/push. The seven-file Xaverius tree was verified at this commit.
- Full implementation plan: [xserver-registry-rebuild-plan-2026-11-05.md](implementation-notes/xserver-registry-rebuild-plan-2026-11-05.md); use the current active plan revision linked in the PhysicalDevice registry assignment above.

**Current API authority:** every per-device registration uses a versioned `const GpuDeviceBackendOps *` inside `GpuDeviceBackendRegistration`, plus structured identity evidence, exact borrowed native handle/context, and the exact owning `GpuModuleRole` generation. The registry copies immutable typed operation tables, queries the snapshot through that exact binding, and publishes separately through `XaPhysicalDevicePublish`. Use only the current API names and contracts in the normative references below; old `XaveriusPhysicalDeviceOps` and capabilities-only registration sketches are obsolete.

Do not patch the discarded registry in place or cherry-pick its implementation commits. Rebuild from the clean rollback baseline. Preserve names/formatting unless a narrowly justified type/API addition is required.

## Active assignment — PhysicalDevice registry implementation

**ACTIVE — HIGH PRIORITY.** The owner has authorized actual registry implementation. This replaces the old “Phase 0 only / Phase A-B paused” gate. The OpenBSD/Cygwin CI tasks continue independently at LOW priority and do not block this work.

- Target: `X11Libre/xserver:wip/xaverius`.
- Starting point: clean rollback baseline `f6f3e87aa81724208496d539e40d2eee2c3d2641`; verify the live remote ref before editing. The old implementation remains forensic-only at `wip/xaverius_old_1`.
- Detailed active assignment: [active-physical-device-registry-task-2026-11-05.md](implementation-notes/active-physical-device-registry-task-2026-11-05.md), added in commit `03552114193bcd6b6ea1fbece035fa147a5df8a5`.
- Fleet hand-off: [W0-20261105-003](https://github.com/metux/wormhole-0/blob/master/inbox/2026-11-05T1700Z--W0-20261105-003--physical-device-registry.md), commit `559308759a31c21fbc7ec9fef75e7df78b1031bd`.
- Authorized scope: Stages 1–4 — canonical types/API, ModuleRole lifetime substrate, registry/identity core, failure-atomic registration and snapshot, and separate DIX publication. Implement incrementally with synthetic/mock DDX tests.
- Not authorized yet: DDX-wide discovery/modesetting, ScreenAttachment integration, protocol handlers, Compute Memory handlers, or backend operation implementations. Those follow only after registry Stages 1–4 are reviewed and accepted.
- Mandatory hygiene: one independently reviewable topic per commit; no cosmetic renames/reformatting, no broad refactors, no duplicate init/fini paths, no unnecessary headers/includes, no unreviewed public SDK ABI changes. Any future modesetting change is a separate commit.
- API/lifetime caution: native handle and per-device context are borrowed DDX-owned values; registry must not free them and must not invent context retain/release callbacks. The DDX keeps them valid until binding removal and all dependent users retire.
- Reports must include full commit and parent SHAs, exact files/symbols/call sites, ownership/refcount table, exact test commands/results, and remaining blockers.

**CI priority:** continue the separate OpenBSD/Cygwin repairs in parallel at LOW priority. Do not wait for them or the full baseline matrix before starting registry implementation. Record CI outcomes honestly; a CI failure is not a reason to stop unrelated registry work, and a passing spec CI is not evidence that Xserver code works.

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

## Historical registry re-audit — discarded implementation (2026-11-05)

**Forensic reference only.** This audit describes the discarded pre-rollback implementation, not the current clean branch. Its findings explain why the registry is being rebuilt; the active task and current normative API supersede its old sequencing/API wording.

- Latest inspected Xserver tip: `deb0e445001389be031fa7e006e3e2e216616b50` (parent `98ce6f6f281a8b8001d967bafd3debe8ea4db4fa`). Full source/history audit: [phase-a-registry-audit-2026-11-05.md](implementation-notes/phase-a-registry-audit-2026-11-05.md), audit commit `931005ab36c864d6947a0465226c03f68f336b91`.
- **Registry model is NOT ACCEPTED and currently unusable.** `XaveriusRegisterDevice()` regressed to a capabilities-only argument; identity, native handle, per-device context, typed ops and ModuleRole/binding generation are absent. Identity is fabricated from vendor/device/API/driver version fields.
- `registry.c` still calls `AddResource()` twice for one XID, publishes before deep-copy completion, and can free an object still referenced by DIX. The commit claiming to remove the duplicate did not remove either call.
- `xaverius_device_init()` has no call site, so the PhysicalDevice resource type is not initialized. RegistryFini and DevicesFini have contradictory ownership/order and can double-free or traverse stale list entries. `init.c` and `xaverius.c` contain competing extension init/fini implementations.
- The internal model has overlapping `XaveriusDeviceRec`, `XaveriusDeviceCapabilities`, unused `XaveriusPhysicalDeviceRec`, and unused `PhysicalDeviceInfoRec` types. `provider_handle` remains as an unowned Provider remnant.
- No current DDX call site invokes `XaveriusRegisterDevice()`; modesetting constructs identity/capability locals and discards them, explicitly deferring registration to Phase B. This violates Phase A.
- History shows the critical regression at `6dffb09bf00e807c90395348ba4c65e4b80ef976`, which dropped identity/native handle/context and disabled modesetting registration. The subsequent `98ce...` and `deb0...` commits did not restore the contract or initialize the resource type.
- **Required:** agents must stop Phase B, repair the single type/binding model and lifecycle per R1–R9 in the audit, then satisfy existing C1–C10/A1–A9. Preserve names/formatting unless a type consolidation is required and justified. Do not edit Xserver source from this spec workspace.

## Historical Phase-A implementation review — discarded branch

**Forensic reference only.** The following source findings apply to the discarded implementation history, not to the clean rollback baseline. Do not treat the old Phase-A/Phase-B gate as active; follow the new Stages 1–4 assignment above.

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
- The discarded branch also contained premature Compute Memory handlers with hard-coded alignment/memory-type masks and success-returning ReadBuffer/WriteBuffer stubs. Those files were discarded by the rollback; do not cherry-pick or reintroduce them.
- Xserver workflow [41921533156](https://github.com/X11Libre/xserver/actions/runs/41921533156) for `189eac7` failed: Ubuntu/DragonFlyBSD/RHEL registry builds reported redundant `strlcpy`/`strlcat`/`strndup` declarations under `-Werror` (plus DragonFly/RHEL `timingsafe_memcmp`/`CSRG_BASED` issues); the SDK image failed linking `XaveriusExtensionInit`; macOS failed because extension sources pulled in `pciaccess.h` through `xf86.h`. The overall workflow was not green. No A1–A9 harness or structured agent report was present in that audit.
- Full findings and precise corrective instructions are in [the follow-up audit history](IMPLEMENTATION_COORDINATION_HISTORY_2026-11-04.md). The listed DDX callback, hotplug, discovery and modesetting findings are follow-up work after registry Stages 1–4; the registry's identity, atomic publication and binding/lifetime requirements are covered by the new active assignment.

## Later implementation evidence requests

Preserve these for the discovery/ScreenAttachment follow-up after registry Stages 1–4 are accepted; they are not blockers for the current registry-core task:

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


## Parallel CI repair assignments — 2026-11-05

**ACTIVE — LOW PRIORITY, independent of the registry implementation.** These tasks continue in separate branches/worktrees and must not block the HIGH-priority PhysicalDevice registry task.

1. **OpenBSD patch:** [ci-openbsd-static-assert-fix.md](implementation-notes/ci-openbsd-static-assert-fix.md), task commit `2159b5e719a786e70b99ded3994292ab8e98cd41`.
2. **Cygwin independent attribution:** [ci-cygwin-baseline-attribution.md](implementation-notes/ci-cygwin-baseline-attribution.md), task commit `7f93fe80e8a87a6ae693c7fa0534d6d603701dd4`.
3. **Cygwin repair:** [ci-cygwin-repair.md](implementation-notes/ci-cygwin-repair.md), task commit `f9d9820590ee8c3bd046de2b61287f471c316e24`.

Keep these tasks on their separate branches/worktrees. No shared working tree with registry implementation. The attribution ship must provide evidence to the repair ship before it chooses a PR destination. Do not merge unrelated CI patches into registry commits.

**Baseline evidence:** Xserver clean baseline `wip/xaverius@f6f3e87aa81724208496d539e40d2eee2c3d2641`; full matrix run [42052262759](https://github.com/X11Libre/xserver/actions/runs/42052262759). OpenBSD failure is the fallback static-assert macro's token-paste expansion issue. Cygwin already installs `python312-lxml`, `libxml2_2`, and `libxslt`; adding them again is not a valid fix. These are tracked maintenance findings, not registry gates.

## Communication-channel migration — 2026-11-05

**TRANSITION ACTIVE — continue all existing work without interruption.** The owner-approved priority change in [W0-20261105-003](https://github.com/metux/wormhole-0/blob/master/inbox/2026-11-05T1700Z--W0-20261105-003--physical-device-registry.md) activates registry implementation now; this supersedes the former Phase-0-only gate. The three CI maintenance assignments remain active at LOW priority.

The shared cross-system message channel is moving to **`metux/wormhole-0`, branch `master`**. The fleet's local clone is available at `_WORK_/wormhole-0`.

- New cross-system requests, questions, acknowledgements, replies, hand-offs, and durable coordination decisions belong in `metux/wormhole-0`, following its `COLLABORATION.md`.
- The first migration request is `W0-20261105-002`: [fleet-channel-migration](https://github.com/metux/wormhole-0/blob/master/inbox/2026-11-05T1645Z--W0-20261105-002--fleet-channel-migration.md).
- Flagship must notify all ships, switch their communication polling/write path, and collect acknowledgements in the new repository's `outbox/`.
- **Do not pause, cancel, reassign, or reset existing tasks.** All active work continues under its existing instructions, ownership, branches, worktrees, and phase gates. In particular, the OpenBSD/Cygwin CI maintenance work remains active and unchanged, but no longer gates registry implementation.
- The XAverius spec remains authoritative at `metux/xav-design@docs/restructure-2026-10-21`; Xserver implementation remains `X11Libre/xserver@wip/xaverius`. This migration changes only the communication channel.
- Keep this file and its active technical assignments intact during transition. Treat this section as the pointer for agents still polling the old channel. Do not add new general discussion here; reply and coordinate in wormhole-0.
- Do not perform unrelated Starfleetctl refactoring. Make only the minimum configuration/SOP changes required for the new channel, using existing task/worktree discipline.

The old channel can be considered retired only after the flagship and active ships have confirmed that they can read and write the new repository and all active assignments remain accounted for.
