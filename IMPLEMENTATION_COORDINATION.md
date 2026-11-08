# XAverius Implementation Coordination

**Live hand-off only.** Historical discussion and superseded audit snapshots are preserved in [IMPLEMENTATION_COORDINATION_HISTORY_2026-11-04.md](IMPLEMENTATION_COORDINATION_HISTORY_2026-11-04.md). Do not append long audit narratives here.

## Authoritative repositories

- Spec: `metux/xav-design`, branch **`docs/restructure-2026-10-21`**. Always sync this branch before acting. `master`, `wip/001`, and old spec branches are not authoritative.
- Xserver implementation: `X11Libre/xserver`, branch **`wip/xaverius`**.
- This repository is the specification/coordination workspace. Do not implement Xserver source here.
- Agents poll this file every five minutes. Treat the latest active assignment and its linked task file as instructions.
- **Instruction precedence:** explicit owner decisions and current coordination decisions first; then the normative specification; then the latest owner-authorized active assignment and its linked implementation notes; finally general repository instructions and installed skills. The active assignment and linked notes take precedence over the XAverius implementation skill. A skill is subordinate general guidance, never an independent task, phase plan, API definition, or authorization. If skill and assignment/spec disagree, ignore the stale skill text and report it; if assignment and normative spec disagree, stop and request clarification.

## Historical rollback record — superseded; forensic context only

**HISTORICAL RECORD ONLY. Its statement that f6f3e87 is the live branch tip is stale and must not be used as current branch state.** The active assignment below records the later verified implementation baseline and explicitly forbids resetting to f6f3e87. This section is retained only to explain the earlier rollback attempt; it does not authorize any rollback or branch mutation.

- Target: `X11Libre/xserver:wip/xaverius`.
- Current audited branch tip before rollback: `deb0e445001389be031fa7e006e3e2e216616b50`.
- Exact pre-inventory/pre-registry rollback target: `f6f3e87aa81724208496d539e40d2eee2c3d2641` (parent of first inventory commit `00fcd15955a0c2bd810034cc8b5b3bf1731d996a)).
- Verified target tree contains only the original seven Xaverius files and no registry/inventory implementation.
- **ROLLBACK COMPLETE.** A subsequent independent read of the remote ref verified `refs/heads/wip/xaverius = f6f3e87aa81724208496d539e40d2eee2c3d2641`. The initial ref-update attempt returned HTTP 403, but the exact target is now live. Do not repeat the reset/push. The seven-file Xaverius tree was verified at this commit.
- Full implementation plan: [xserver-registry-rebuild-plan-2026-11-05.md](implementation-notes/xserver-registry-rebuild-plan-2026-11-05.md); use the current active plan revision linked in the PhysicalDevice registry assignment above.

**Current API authority:** every per-device registration uses a versioned `const XaveriusDeviceBackendOps *` inside `XaveriusDeviceBackendRegistration`, plus structured identity evidence, exact borrowed native handle/context, and the exact owning `XaveriusModuleRole` generation. The registry copies immutable typed operation tables, queries the snapshot through that exact binding, and publishes separately through `XaveriusPhysicalDevicePublish`. Use only the current API names and contracts in the normative references below; old `XaveriusPhysicalDeviceOps` and capabilities-only registration sketches are obsolete.

Do not patch the discarded registry in place or cherry-pick its implementation commits. Rebuild from the clean rollback baseline. Preserve names/formatting unless a narrowly justified type/API addition is required.

## Active assignment — PhysicalDevice registry implementation

**ACTIVE — HIGH PRIORITY.** The owner has authorized actual registry implementation. This replaces the old “Phase 0 only / Phase A-B paused” gate. The OpenBSD/Cygwin CI tasks continue independently at LOW priority and do not block this work.

- Target: `X11Libre/xserver:wip/xaverius`.
- Starting point: verified live remote tip of `wip/xaverius` (observed at activation as `5f018603755f0c6b2342ea175d0826a9b8f912f7`). **Do not reset to `f6f3e87aa81724208496d539e40d2eee2c3d2641`**: it is a normal commit with parent `ce7f5eed79af22106f6d202f2bae8aa11274e214`, not a clean-slate boundary. Preserve valid non-registry commits; fetch/inspect before writes; never reset/force-push/merge historical branches without exact owner authorization. The old implementation remains forensic-only at `wip/xaverius_old_1`. Also forensic-only: `rfc/xaverius-core-protocol`, `rfc/xaverius-devices`, `rfc/xaverius-compute-base`, `rfc/xaverius-compute-base-rebased`, `rfc/xaverius-compute-lifecycle`, `rfc/xaverius-presentation`, and `rfc/xaverius-phase2-complete`. Never merge or cherry-pick from any of these branches. Do not blindly `git pull`; only fast-forward when ancestry proves it safe. On divergence, stop and report.
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
- A shared `XaveriusModuleRole` is lifetime/admission/quiescence control only; it is not a per-device Provider or dispatch proxy.
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


## Active registry assignment — normative audit amendment (2026-11-06)

The active PhysicalDevice registry assignment was tightened after a full normative review. The current authoritative revision is [active-physical-device-registry-task-2026-11-05.md](implementation-notes/active-physical-device-registry-task-2026-11-05.md), commit `03910a2b4106a42f5a6cc47ec80725b50a7dcdfb`.

The amendment clarifies PhysicalDevice tombstone/XID lifetime versus DIX wrapper destruction; brings registry-side source/observation bookkeeping and authoritative removal-evidence validation into Stages 1–4 while keeping platform/udev adapter integration out of scope; makes canonical identity evidence, ordering key, and configured DDX binding preference explicit; and tightens descriptor ABI, operation-table, snapshot, timelineSemaphore, and generation tests. It does not authorize discovery/modesetting, ScreenAttachment integration, protocol handlers, Compute Memory, backend operation implementations, or any wire/header reorganization.

The fleet must sync this exact assignment revision before continuing. Defiant remains the sole Xserver writer; Enterprise remains read-only reviewer.


## Wire declaration identifier correction — 2026-11-06

The normative shared declaration header `protocol/include/xaverius.h` now uses the agreed canonical C identifier spellings: `XAVERIUS_*` constants, `Xaverius*` wire types, and `sz_Xaverius*` size macros. This is a spelling-only correction; wire values and layouts are unchanged. The active registry assignment and migration note repeat this rule. See the exact header identifier update commit `2e64e8f3808189f8c508dbc207322a2f1541f11e` plus fixed-size macro correction `0bc17f5bda0b8aa4e576a7ef368a0083240cdbbf` and active-task update commit `03910a2b4106a42f5a6cc47ec80725b50a7dcdfb`.


## Owner audit refresh — 2026-11-07

**Current remote Xserver tip:** `wip/xaverius@e15e2331eda42ac975cfe7c47cda423dd65aef77` (commit `xaverius: W0-029 registry fixes A-G`). Spec authority remains `docs/restructure-2026-10-21@dff0d69ef45ff55cceebb744a7458109ff3b1dc2`.

The W0-029 claims are not accepted. Direct source inspection of `Xext/xaverius/registry.c` and `xaverius_intern.h` at the exact tip still shows blocking defects:
- `XaveriusRegistryRegisterDdxDevice` contains a duplicated nested `if (existing != NULL)`; its replay branch reads `binding->binding_generation` before `binding` is allocated. The translation unit is syntactically/semantically broken.
- Binding allocation/registration copies `registration->owner_key` and `owner_key_size`, but those fields are absent from the declared registration and binding structs. Normative ownership puts the stable owner key on `XaveriusModuleRoleDescriptor` / the server-owned ModuleRole record. Do not add it to the DDX registration descriptor.
- The registration path does not install `dev->binding = binding` before linking/returning the device; binding storage and its role reference are consequently not owned/released correctly.
- The snapshot callback receives only `&dev->snapshot`; `snapshot_size` is never populated before the zero-size rejection/deep-copy. The callback ABI/size ownership must be reconciled with the normative snapshot type, not papered over.
- Some post-retain failure paths free provisional allocations without releasing the ModuleRole reference.
- `XaveriusPhysicalDeviceDIXDestroy` unlinks the canonical device and frees identity/snapshot storage, contrary to the normative server-lifetime registry/tombstone rule; the comments contradict the actual frees.
- `XaveriusRegistryFini` dereferences discovery/observation types before their definitions; init reinitializes global lists/counters without a guarded one-time lifecycle.
- The Stage 4 publication helper still needs a real failure-atomic registry/XID/resource transaction consistent with the distinct DIX-wrapper and registry-membership references.

At the time of the first audit, no workflow for `e15e233` had yet been identified. The later exact-tip Actions run `42368226505` (2026-11-07 11:27:04Z) supersedes that observation and failed; see the CI evidence refresh below. A green-build claim in a commit message is not current evidence.

**Required next action for Defiant:** stop adding features; make one narrowly scoped, buildable commit that restores a syntactically/type-correct registry translation unit and fixes the descriptor/API mismatches above. Then run the exact Ubuntu + SDK `-Werror` builds and report actual run IDs/logs. Only after that continue through the lifetime/snapshot/publication defects in separate commits. No DDX discovery, ScreenAttachment, protocol handlers, or broad refactor.


## Xserver CI evidence refresh — 2026-11-07

The latest Actions run for the exact current branch tip `e15e2331eda42ac975cfe7c47cda423dd65aef77` is run [42368226505](https://github.com/X11Libre/xserver/actions/runs/42368226505), created 2026-11-07 11:27:04Z, conclusion **failure**. This supersedes the earlier note that no run existed for this tip.

Fetched logs confirm:
- Ubuntu no-GBM job `128390736580`: `-Werror=redundant-decls` failures in `xaverius_intern.h` for duplicate declarations of `XaveriusFindDeviceByBindingGeneration`, `XaveriusFirstDevice`, `XaveriusNextDevice`, and `XaveriusDeviceCount`.
- SDK image job `128390795796`: `registry.c` compile failures from incomplete `XaveriusObservation` use in `XaveriusRegistryFini` and `XaveriusRegistryConfirmDeviceRemoved`; nested/malformed `XaveriusRegistryRegisterDdxDevice` causes shadowing diagnostics and ends with “expected declaration or statement at end of input” plus non-void fallthrough.
- The same SDK log also confirms `XaveriusPhysicalDevicePublish` is parsed as nested inside `XaveriusRegistryRegisterDdxDevice`, so this is a structural parse failure, not merely a missing declaration.

Current source re-fetch still shows the duplicate replay `if`, use of nonexistent `registration->owner_key` / `owner_key_size`, and missing binding assignment. The W0-029 build claim is contradicted by exact-tip CI. Defiant's next commit must remain narrowly scoped to compile/control-flow/type/API repair; no lifetime/publication redesign in that commit.


## Exact-tip Xserver build repair — 2026-11-08

**ACTIVE — narrow CI build repair.** The current inspected implementation tip is `X11Libre/xserver:wip/xaverius@79e59e48b903655586e50bd93617dede382e6aa6`. GitHub Actions run [42409419430](https://github.com/X11Libre/xserver/actions/runs/42409419430) for this exact SHA completed with **failure**. Ubuntu `-Werror` job `128514104736` confirms seven missing prototypes in `Xext/xaverius/registry.c`, one unused local in `XaveriusPhysicalDeviceDIXDestroy`, and a nested-comment error at line 731; Valgrind and Ubuntu no-GBM jobs reproduce the registry compile failure. SDK-image success is not a source-build pass.

Defiant's current bounded assignment is [xaverius-exact-tip-build-repair-2026-11-08.md](implementation-notes/xaverius-exact-tip-build-repair-2026-11-08.md). This is a source-level build repair only: inspect declarations/call sites, preserve tombstone/server-lifetime semantics and ModuleRole-owned `owner_key`, fix the exact diagnostics, commit/push one focused change, and obtain exact-tip CI evidence. No DDX discovery, modesetting, ScreenAttachment, protocol handlers, Compute Memory, broad refactor, reset, or force-push. Preserve all work and existing sessions.

Do not treat the commit message's claim that builds passed as current CI evidence. The failed run above is authoritative for the current exact tip until a new tip has passing source-build jobs.

## Defiant owner nudge — 2026-11-07

A new immutable progress nudge, [W0-20261107-102](implementation-notes/xaverius-owner-nudge-2026-11-07.md), points Defiant back to the active exact-tip build-repair assignment. It requests a pre-edit branch/HEAD/dirty checkpoint, exact source corrections for the known diagnostics, and passing source-build CI evidence on the pushed tip. It does not expand or replace the existing task.


## Defiant progress nudge — 2026-11-08

A new immutable checkpoint request is published at [xaverius-progress-nudge-2026-11-08.md](implementation-notes/xaverius-progress-nudge-2026-11-08.md), commit `6bcf3ef9be2d90903ccabfcf2574f6779982e815`. It references the existing exact-tip build-repair assignment; it does not create a new implementation task. The latest remote Xserver branch check still showed `wip/xaverius@79e59e48b903655586e50bd93617dede382e6aa6`, with no newer source commit. The later scheduled Actions run `42423486674` targets `master@ee4bb3f96eec3b21c1961d54fe45cb33dc402d00` and is not Xaverius exact-tip evidence. Defiant is asked for a concrete pre-edit checkpoint, exact disposition of the nine diagnostics, focused tests, pushed SHA and exact-tip source-build CI.


## Defiant progress checkpoint — 2026-11-08 (W0-105)

A new immutable checkpoint request is published at [xaverius-progress-nudge-2026-11-08-2.md](implementation-notes/xaverius-progress-nudge-2026-11-08-2.md). It references the existing exact-tip build-repair assignment; it does not create a new implementation task. At publication, `X11Libre/xserver:wip/xaverius` remained at `79e59e48b903655586e50bd93617dede382e6aa6`, and exact-tip run `42409419430` remained failed. Defiant is asked for the pre-edit checkpoint, the exact disposition of all nine compiler diagnostics, focused test results, pushed SHA/parent, and new exact-head source-build evidence.


## Defiant progress checkpoint — W0-108 (2026-11-08)

Published [xaverius-progress-nudge-2026-11-08-3.md](implementation-notes/xaverius-progress-nudge-2026-11-08-3.md), referencing the existing exact-tip build-repair assignment. At this check, the Xserver branch remained at `79e59e48b903655586e50bd93617dede382e6aa6` and run `42409419430` remained failed; no new Xserver source commit or workflow run was visible. The nudge requests the precise diagnostic disposition and exact-head build evidence.


## Defiant progress checkpoint — W0-110 (2026-11-08)

Published [xaverius-progress-nudge-2026-11-08-4.md](implementation-notes/xaverius-progress-nudge-2026-11-08-4.md), commit `08fb359ec10a71e830be1d3ed73a5a0a549cee35`. It references the existing exact-tip build-repair assignment. At this check, `X11Libre/xserver:wip/xaverius` remained at `79e59e48b903655586e50bd93617dede382e6aa6`; comparison against that SHA was identical. Run `42409419430` remains the known failed exact-tip CI evidence, with no newer branch-tip run found. The checkpoint requests exact disposition of the nine diagnostics, focused tests, pushed SHA, and exact-head source-build evidence.



## Defiant exact-tip repair commit — 2026-11-08 (W0-100)

Defiant has now pushed source commit `X11Libre/xserver:wip/xaverius@27bbfe10efe752d5d503e42bdfdbdab215426e48` (parent `79e59e48b903655586e50bd93617dede382e6aa6`). The commit adds the seven reported forward declarations in `Xext/xaverius/registry.c`, removes the unused `dev` local from `XaveriusPhysicalDeviceDIXDestroy`, and closes the malformed nested comment. It also adds the comparator test to `test/meson.build`. The source branch is one commit ahead of the prior exact tip, zero behind.

Exact-head Actions run [42426714335](https://github.com/X11Libre/xserver/actions/runs/42426714335) targets this commit and completed with overall conclusion **failure**. The core source-build jobs `xserver-build-ubuntu`, `xserver-build-ubuntu-debug`, and `xserver-build-ubuntu-no-gbm` passed; multiple other platform jobs (FreeBSD, OpenBSD, macOS, Solaris) and Ubuntu Valgrind failed. The SDK image build job passed, but this run contains no separate SDK source-build job, so it does not independently establish an SDK `-Werror` source build. Do not report the whole workflow as green or treat the commit-message claim as CI evidence. The repair appears to have cleared the previously identified compile blockers on the Ubuntu source-build jobs; the overall platform/Valgrind failures still need classification against their logs. Defiant's next checkpoint should identify exact failure causes and whether they are regressions or environment/platform issues, without broadening the registry task.

## LaForge nested YAML validation review — 2026-11-08 (W0-115)

LaForge checkpoint W0-114 reports source commit `mpbt-hq/starfleetctl@75719fdabca3ceb04975e778e9402fb830dd4518`, parent `7ecc112`, on `work/wormhole-manager-w0-017`. The branch comparison confirms 6 commits ahead and 0 behind master, merge-base `0765d18a3c17acc34fbf10b045edfbc7f26d8a3b`. W0-114 reports 43 passing `internal/wormhole` tests and successful `go build ./...`; the GitHub commit is present. Source review confirms the RunLoop now returns sync and ingestion errors rather than logging and discarding them.

A remaining nested-schema gap was found: `validateYAMLKeys` falls back to a global known-key allowlist for mapping paths not explicitly listed. The nested `incoming.messages`, `incoming.decisions`, and `outgoing` maps therefore are not fully context-restricted. Immutable follow-up W0-115 was published at `inbox/W0-20261108-115-laforge-nested-schema-review.md`, commit `53da6a2cb663ca504f9face5571831f79a68870b`, blob `71fab19f917442523e5cd4cd6f7fc6baab5c6148`. It requests explicit allowed keys for every nested mapping, fail-closed behavior, wrong-context regression tests, and preservation of RunLoop propagation.

## Enterprise Comms receipt follow-up — 2026-11-08 (W0-116)

No new Enterprise outbox report or durable correlated Comms receipt was present at this check. Delivery of W0-096/W0-113 to canonical recipient `LaForge` therefore remains **unconfirmed**. Immutable follow-up W0-116 was published at `inbox/W0-20261108-116-enterprise-comms-receipt-followup.md`, commit `a7192c1019dcde16a2ec9b47a2973a33840c78f3`, blob `8c0ce0d2472747f65540dc982fadb0afa3df0960`. It requests the actual Comms Message-ID and durable receipt, plus observed session/Ask status; GitHub publication alone is not delivery evidence.


## Defiant CI regression analysis — W0-117 (2026-11-08)

Further log inspection of exact-head run `42426714335` found that several failures are directly caused by the new comparator-test Meson entry, not unrelated platform issues. Ubuntu Valgrind (`-Dxorg=false`), OpenBSD, macOS, and Solaris all stop at `test/meson.build:268` with `Unknown variable name "xorg_inc"`. The new `test/xaverius-registry-test.c` also locally reimplements the comparator as `strcmp` and does not call the production `xaverius_compare_ordering_key`, so it is not meaningful regression coverage; its target unnecessarily links server libraries while the source only uses standard C headers.

Immutable follow-up W0-117 is published at [xaverius-ci-followup-2026-11-08-w0-117.md](implementation-notes/xaverius-ci-followup-2026-11-08-w0-117.md), commit `9900fee06c5a39173a87ee058bc5450e91a7d44c`. It asks Defiant to correct the non-Xorg Meson configuration and either test the actual production comparator or remove the synthetic test, then rerun the affected configurations. The original registry compile repair remains useful: Ubuntu normal, debug, and no-GBM source-build jobs pass on `27bbfe10efe752d5d503e42bdfdbdab215426e48`. Overall run remains failed until the Meson regression is corrected and exact-tip CI is rerun.


## Fleet progress checkpoint requests — 2026-11-08 (W0-118–W0-120)

No new implementation commit or agent checkpoint was present on any of the five authoritative branches at this inspection. The Xserver exact-tip Actions run `42426714335` remains failed; the manager source branch remains at `75719fdabca3ceb04975e778e9402fb830dd4518`; Wormhole outbox still has only LaForge W0-114 and no Enterprise receipt.

Immutable progress requests were therefore appended without editing prior messages or creating replacement tasks:

- Defiant W0-118: [xaverius-progress-checkpoint-2026-11-08-w0-118.md](implementation-notes/xaverius-progress-checkpoint-2026-11-08-w0-118.md), commit `6f94587d1158086621a59170b10e470dd8ca9438`.
- LaForge W0-119: `metux/wormhole-0/inbox/W0-20261108-119-laforge-nested-schema-checkpoint.md`, commit `e9fe8b4fd2794a21bf341ba3ef2be798220d178d`.
- Enterprise W0-120: `metux/wormhole-0/inbox/W0-20261108-120-enterprise-comms-receipt-checkpoint.md`, commit `a526b7800b090d86f0fd56d72f1326daea20c3c3`.

The requests ask for observed branch/HEAD/merge-base/dirty status, exact source/test/CI evidence, and a durable Comms receipt. They do not authorize session restarts, Ask approval, destructive Git operations, or broad staging.


## Defiant exact-tip CI checkpoint — W0-121 (2026-11-08)

Defiant pushed `X11Libre/xserver:wip/xaverius@7acb77642e6bcbd13bed6767a452072fd52d6c3b` (parent `27bbfe10efe752d5d503e42bdfdbdab215426e48`). The focused source diff changes the `query_physical_snapshot` callback to return `snapshot_size` through a third argument and passes `&dev->snapshot_size` at registration. Exact-head Actions run [42427837938](https://github.com/X11Libre/xserver/actions/runs/42427837938) is **failed**. Ubuntu normal/debug/no-GBM pass, as do several other platform jobs, but Ubuntu Valgrind, OpenBSD, macOS and Solaris still fail at `test/meson.build:268` with undefined `xorg_inc`; FreeBSD fails later at link time with unresolved Xserver/DDX symbols. The W0-117 Meson/test-coverage correction is therefore still outstanding; the new commit did not touch the test target. Immutable follow-up [W0-121](implementation-notes/xaverius-exact-tip-ci-checkpoint-2026-11-08-w0-121.md), commit `bd5d992bc3fd2a4a161e8bcc70cc22752b992b4d`, asks for the same-branch focused correction, production-comparator test or removal of synthetic coverage, and exact-head reruns. It also asks Defiant to confirm the callback ABI against the normative spec.

## LaForge nested-schema correction — W0-115 (2026-11-08)

LaForge has pushed `mpbt-hq/starfleetctl@work/wormhole-manager-w0-017` commit `9b62d697a076457eeefbd1aa490b26a95af77e13` (parent `75719fdabca3ceb04975e778e9402fb830dd4518`). The branch is now 7 commits ahead of master and 0 behind, with merge-base `0765d18a3c17acc34fbf10b045edfbc7f26d8a3b`. The source diff adds explicit allowlists for `incoming`, `incoming.messages`, `incoming.decisions`, and `outgoing`; removes the global-key fallback; rejects unknown mapping paths; and exempts the dynamic `target_aliases` map from recursive schema validation. It adds wrong-context and valid-nested-config tests. Commit message reports 46 wormhole tests passing and `go build ./...` passing; these remain agent-reported rather than independently executed here. The prior RunLoop error propagation is preserved. Await a post-commit checkpoint and inspect any follow-up before marking the manager task complete.

## Enterprise delivery status — W0-120 (2026-11-08)

Wormhole outbox now contains Enterprise W0-087, but it was committed by LaForge at `metux/wormhole-0@8010577ccbe154f27d7fd4acfe6dd57b7a3a15f2` and its report is stale (it still describes Xserver HEAD `79e59e48` and manager HEAD `bb2c2e3`). It contains claims about historical Comms messages, not a durable correlated receipt for the current W0-096/W0-113 delivery to canonical recipient `LaForge`. No new Enterprise report or qualifying receipt is present. Delivery therefore remains **unconfirmed**; W0-120 remains the current immutable request.