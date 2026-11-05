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
- Full implementation plan: [xserver-registry-rebuild-plan-2026-11-05.md](implementation-notes/xserver-registry-rebuild-plan-2026-11-05.md); use the current active plan revision referenced in the Phase 0 section below.

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

## Active assignment — Phase 0 clean baseline

**ACTIVE — Phase A/Phase B implementation work is paused.**

The previous Phase-A assignment and its C1–C10 corrections are retained below as audit history only; they are NOT authorization to continue implementing against the discarded registry model. The Xserver branch was rolled back and the old implementation is preserved separately:

- Active clean branch: `X11Libre/xserver:wip/xaverius` at `f6f3e87aa81724208496d539e40d2eee2c3d2641`.
- Preserved old branch: `X11Libre/xserver:wip/xaverius_old_1` at `deb0e445001389be031fa7e006e3e2e216616b50`.
- Rebuild plan: [xserver-registry-rebuild-plan-2026-11-05.md](implementation-notes/xserver-registry-rebuild-plan-2026-11-05.md), updated through commit `49d761a651a0ac1ac76fb6be8d8eed5385ff45f3`; normative clarifications are in `spec/device-registry-architecture.md` (latest change `f34c97b99d30cbdf963c550f13740d4a59adf2e3`) and `spec/registry-api-lifetime-addendum.md` (`0f3277c6c25ca80cc88bd5b19a02f9417cce834f`).

**Mandatory commit/source hygiene (all phases):** see §2.6 of the rebuild plan (latest plan commit `1aa136395768b99ce0e95d17dc4a75d149a7227b`). Every commit is one atomic, independently reviewable topic. PhysicalDevice registration, ScreenAttachment, DDX discovery, modesetting, request handlers and backend operations are separate commits. Any `hw/xfree86/drivers/modesetting/` change is a separate DDX-specific commit; core lifecycle/public-header changes (e.g. `xf86Bus.c`, `include/*`) also require separate narrowly scoped commits and explicit rationale/ABI review.

Preserve existing formatting, license headers, EOF newlines, header scopes, names and init/protocol structure. No gratuitous whitespace/comment churn, no extra headers or monolithic duplicate `xaverius.c`, no premature Proc/SProc/request handlers, no legacy SProc/rpcbuf patterns. Do not add unnecessary includes; order them as `dix-config.h` (where required), system, Xserver-wide (canonical paths such as `include/resource.h`), then extension-internal. Do not prefix extension-internal source filenames with `xaverius_`. Treat all `include/*` headers as public SDK/driver ABI and do not change layout/signatures without a separate ABI-reviewed commit and compatibility tests. Reject mixed-purpose commits.

**Current task: Phase 0 only.** Build the untouched `f6f3e87...` baseline using the existing full Xserver portability/SDK CI matrix. Do not modify source files. Report the exact commit, parent, commands/workflows, logs, and PASS/FAIL/BLOCKED result for every target. Do not start Phase 1 until this baseline is recorded and reviewed.

**Phase 0 progress (2026-11-05):**
- User-confirmed local state: worktree at `f6f3e87aa81724208496d539e40d2eee2c3d2641`, `git clean` run, local build successful. Exact local build command/configuration has not yet been recorded; do not ask the user to repeat the build unless needed to reproduce it.
- Remote `wip/xaverius` independently resolves to the exact target SHA; preserved `wip/xaverius_old_1` resolves to `deb0e445001389be031fa7e006e3e2e216616b50`.
- Full existing workflow: [Build X servers, run 42052262759](https://github.com/X11Libre/xserver/actions/runs/42052262759), commit `f6f3e87...`. At the latest inspection it was still in progress.
- Completed PASS jobs include Ubuntu (normal, debug, no-GBM), macOS, FreeBSD, NetBSD, DragonFlyBSD, RHEL 9/10, Alpine, Solaris, Arch, Gentoo, GNU/Hurd, MinGW cross-build, Ubuntu SDK image and completed Ubuntu driver builds.
- FAIL: OpenBSD after three attempts. Compiler log shows repeated redefinition of `xav_static_assert___LINE__` from `Xext/xaverius/xaverius_proto.h` (the fallback `XAV_STATIC_ASSERT` macro token-pastes `__LINE__` without an expansion layer). This is a baseline finding; do not patch it during Phase 0.
- FAIL: Cygwin build. `hw/xwin/glx/gen_gl_wrappers.py` cannot import `lxml.etree` from the Cygwin Python environment while generating WGL/GL shim files. This is a baseline CI/environment finding; do not patch it during Phase 0.
  - Important refinement: `python312-lxml` is already explicitly requested and is shown as installed in the job log; `libxml2_2` and `libxslt` are also installed. Therefore, merely adding the lxml package is not a fix. The `ImportError: No such file or directory` at `from lxml import etree` is consistent with failure to load the compiled Cygwin extension or one of its DLL dependencies. Before changing packages, add a diagnostic/preflight in a separate CI-fix commit: run `/usr/bin/python3.12.exe -c 'from lxml import etree; print(etree.LXML_VERSION)'` immediately after PATH setup; on failure print the installed lxml extension path and run `cygcheck` on its `etree*.dll` to identify the exact missing DLL. Then add/fix only the missing runtime package or DLL search path. Do not replace the Khronos registry parser or switch Python versions without evidence.
- PENDING at latest inspection: Ubuntu Valgrind job and remaining matrix jobs.
- Combined status API returned no status contexts; the Actions run is the authoritative matrix evidence. Recheck run completion and record final job inventory before closing Phase 0.
- Gate interpretation: record all baseline outcomes, including pre-existing failures; do not silently repair baseline issues or treat the matrix as green. Phase 1 remains blocked until the run completes and failures are classified/documented.

**Updated object contract (normative):**

- Exactly one internal `PhysicalDevice` object per canonical physical-device incarnation. It owns the immutable capability/property snapshot as a member/value; no separate DeviceCaps/PhysicalDeviceInfo registry object.
- Each registration supplies the matching pointer to a versioned `const XaveriusPhysicalDeviceOps` structure. The registry validates and copies its typed operation vectors into immutable server-owned storage.
- PhysicalDevice's DIX resource wrapper and XID are server-private. The DDX cannot allocate, inspect, store, free, or otherwise manage XIDs. The DDX-facing PhysicalDevice type, if visible at all, is opaque.
- Registration may return an opaque non-NULL PhysicalDevice pointer on success and NULL on every failure, including duplicate/conflicting identity. The returned pointer is only an immediate result; the DDX must not retain/dereference it after the call. Later references are generation-checked server-owned references/tokens.
- The XID never appears in PhysicalDeviceOps, the registration descriptor, or a DDX-visible structure.

**Phase gates:** Phase 1 (type/API freeze) is not yet assigned. Do not add registry lists, DIX resources, request handlers, or modesetting enumeration during Phase 0. The old Phase-A task files are superseded for sequencing by the rebuild plan; their technical findings remain relevant only where the plan explicitly carries them forward.

**Preservation rules:** agents work only on `X11Libre/xserver:wip/xaverius`; no Xserver source edits from this spec workspace. Minimal diffs, preserve names/layout/formatting, no cosmetic renames or broad refactors. Do not cherry-pick the discarded registry commits.

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


## Parallel CI repair assignments — 2026-11-05

**ACTIVE — three independent fleet tasks.** These are maintenance tasks for the Phase 0 baseline failures only. They do not authorize Phase 1 or any XAverius registry implementation.

1. **OpenBSD patch:** [ci-openbsd-static-assert-fix.md](implementation-notes/ci-openbsd-static-assert-fix.md), task commit `2159b5e719a786e70b99ded3994292ab8e98cd41`.
   - One minimal patch to `Xext/xaverius/xaverius_proto.h`, fixing fallback C99 static-assert identifier expansion with two-stage token concatenation.
   - Keep C++/C11 paths, wire ABI and all unrelated files unchanged.
2. **Cygwin independent attribution:** [ci-cygwin-baseline-attribution.md](implementation-notes/ci-cygwin-baseline-attribution.md), task commit `7f93fe80e8a87a6ae693c7fa0534d6d603701dd4`.
   - Investigation only; compare `wip/xaverius@f6f3e87...` against exact current `master` SHA and its CI. No edits.
3. **Cygwin repair:** [ci-cygwin-repair.md](implementation-notes/ci-cygwin-repair.md), task commit `f9d9820590ee8c3bd046de2b61287f471c316e24`.
   - Separate minimal patch; prove the lxml/DLL/runtime cause before editing. Coordinate with attribution agent.
   - If failure exists on unchanged master, target a standalone general Xserver PR based on master. If introduced by XAverius branch, target a separate XAverius patch. If inconclusive, do not open a PR or guess.

**Fleet coordination:** flagship should create three separately tracked tasks and assign separate ships. The attribution ship must message its evidence to the repair ship and flagship before the repair ship chooses the PR destination. No shared working tree or shared feature branch between OpenBSD and Cygwin work. Use separate worktrees/branches and serialized commit/push operations per starfleetctl conventions. Each ship reports exact base/head SHAs, changed paths, commands, CI run/job URLs and PASS/FAIL/BLOCKED outcomes. Do not merge these patches together.

**Common base/evidence:** Xserver clean baseline `wip/xaverius@f6f3e87aa81724208496d539e40d2eee2c3d2641`; failing full matrix run [42052262759](https://github.com/X11Libre/xserver/actions/runs/42052262759). Cygwin already installs `python312-lxml`, `libxml2_2`, and `libxslt`; adding them again is not a valid fix. OpenBSD failure is the fallback macro's direct token-paste of `__LINE__`.

**Phase gate:** Phase 0 baseline failures are being repaired/classified in separate maintenance work. Do not start Phase 1 until the original baseline matrix is fully inventoried and these independent patches have been reviewed and their CI effects recorded.

## Communication-channel migration — 2026-11-05

**TRANSITION ACTIVE — continue all existing work without interruption.**

The shared cross-system message channel is moving to **`metux/wormhole-0`, branch `master`**. The fleet's local clone is available at `_WORK_/wormhole-0`.

- New cross-system requests, questions, acknowledgements, replies, hand-offs, and durable coordination decisions belong in `metux/wormhole-0`, following its `COLLABORATION.md`.
- The first migration request is `W0-20261105-002`: [fleet-channel-migration](https://github.com/metux/wormhole-0/blob/master/inbox/2026-11-05T1645Z--W0-20261105-002--fleet-channel-migration.md).
- Flagship must notify all ships, switch their communication polling/write path, and collect acknowledgements in the new repository's `outbox/`.
- **Do not pause, cancel, reassign, or reset existing tasks.** All active work continues under its existing instructions, ownership, branches, worktrees, and phase gates. In particular, the Phase 0 OpenBSD/Cygwin baseline work remains active and unchanged.
- The XAverius spec remains authoritative at `metux/xav-design@docs/restructure-2026-10-21`; Xserver implementation remains `X11Libre/xserver@wip/xaverius`. This migration changes only the communication channel.
- Keep this file and its active technical assignments intact during transition. Treat this section as the pointer for agents still polling the old channel. Do not add new general discussion here; reply and coordinate in wormhole-0.
- Do not perform unrelated Starfleetctl refactoring. Make only the minimum configuration/SOP changes required for the new channel, using existing task/worktree discipline.

The old channel can be considered retired only after the flagship and active ships have confirmed that they can read and write the new repository and all active assignments remain accounted for.
