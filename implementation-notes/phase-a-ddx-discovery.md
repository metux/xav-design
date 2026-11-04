# Phase A — DDX-wide PhysicalDevice discovery (X11Libre Xserver)

**Status:** ACTIVE — implementation agents must execute this task before Phase B.  
**Target:** `X11Libre/xserver:wip/xaverius`  
**Specification branch:** `metux/xav-design:docs/restructure-2026-10-21`  
**Current implementation baseline inspected:** `89df8ba0bc41dbb4b291b2242b9945661bb47fad`  
**Normative authority:** `spec/devices.md` (Physical-Device identity, DDX registration, enumeration and XID lifetime); `spec/device-registry-architecture.md` §§1–3.1, 5–7, 8.1–8.3 and 9 (especially §2.4 startup barrier); `spec/registry-api-lifetime-addendum.md`; `implementation-notes/ddx-device-registration.md`. If this task conflicts with those normative documents, the normative documents win.

This file is the complete active Phase A task. It supersedes older Phase A wording in the migration plan and coordination history. Read it in full before editing. Do not infer permission to implement later phases.

## 0. Non-negotiable outcome

PhysicalDevice discovery and registration are owned by the DDX-wide device/backend lifecycle, not by an X11 Screen lifecycle.

A DDX registration pass MUST enumerate every executable PhysicalDevice served by that DDX instance and submit each exact device binding to the one process-wide XAverius registry. This includes headless, render-only, compute-only, and currently Screen-unattached devices. A device is not omitted merely because it has no connector, no `ScrnInfoPtr`, no `ScreenPtr`, or no RandR object.

The registry is authoritative. Platform/udev discovery supplies identity and hotplug evidence; it is not a second executable-device inventory. Do not add an independent Vulkan-ICD candidate inventory. A DDX may use Vulkan internally, but the exact resulting device handle, per-device context, and operation vectors are registered through that DDX's own registration pass.

**Do not declare Phase A complete merely because a global list exists or because the request handler no longer walks Screens.** The registry must have a real, reachable DDX-wide population path and evidence that it discovers the full DDX-served device set without creating Screens.

## 1. Exact scope

Implement only the discovery/registration lifecycle seam and its concrete Xlibre integration:

1. A DDX-wide registration entry point that is independent of `ScreenPtr`, `ScrnInfoPtr`, `XaveriusScreenPtr`, and Screen creation.
2. A DDX-owned enumeration pass that visits all PhysicalDevices served by that DDX instance.
3. A direct per-device registration call into the canonical XAverius registry, using the current normative complete-binding registration contract (semantic equivalent of `GpuRegistryRegisterDdxDevice`).
4. A real call site in the selected XAverius-capable DDX path, invoked after the exact native device handle/context and operation vectors are valid, but without requiring a Screen.
5. Removal of PhysicalDevice enumeration/property/queue-family callbacks from `XaveriusDDXOps`.
6. Removal of all lazy device discovery from client request handlers.
7. Tests proving zero-Screen and multi-device behavior, repeat-call behavior, and separation from Screen lifetime.

Do not implement Phase B's full operation-table redesign, Phase C's complete duplicate arbitration, Phase D's DIX resource redesign, or Phases E–G. However, do not introduce a temporary API that contradicts the normative binding model or publishes incomplete/fabricated devices. If the current registry API is too weak to accept a complete binding, report the exact missing contract and implement only the smallest compileable interface seam needed by Phase A; do not smuggle in a Provider object or snapshot-as-callback workaround.

## 2. Required source/API shape

### 2.1 DDX-wide pass

Provide one explicit DDX-wide entry point with these semantic properties:

- It is invoked for each DDX device-enumerator instance independently of Screens and is associated with the exact registered module-role generation that pins its code/resources. Do not conflate the adapter/pass lifetime with that module-role generation or with each per-device binding generation: every successful per-device registration is still one exact binding with its own registry-assigned generation.
- It receives or resolves a DDX-owned context whose lifetime is independent of `ScrnInfo` and Screen private storage.
- It enumerates the complete device set owned/served by that DDX context.
- It submits each exact device registration directly to the XAverius registry.
- It reports a classified terminal pass result: COMPLETE (the scan reached its end and every discovered candidate has a final disposition), or UNAVAILABLE/FAILED (the DDX could not establish a complete initial inventory). PENDING is permitted only while asynchronous work is genuinely outstanding; PENDING MUST keep the initial discovery barrier closed. A terminal FAILED/UNAVAILABLE pass allows the server-wide barrier to account for that failed adapter without waiting forever, but is not evidence of physical removal and MUST NOT fabricate a device or status transition. A later successful registration follows the normative late-registration path.
- Repeating the same pass or registration for the same exact generations is idempotent and MUST NOT duplicate publication or silently replace a binding. A failed registration consumes its reserved binding generation as required by the registry API; any retry that needs a new binding MUST use a fresh non-reusable binding generation, not recycle the failed one.
- It has an explicit owner and teardown point. Do not retain borrowed Xorg pointers beyond their documented lifetime.

Names are implementation-defined, but the separation MUST be visible in the type system and call graph. A function that takes `ScrnInfoPtr` or `ScreenPtr` and loops over records is not DDX-wide. A static helper called only from `ScreenInit()` is not DDX-wide.

### 2.2 Per-device registration

For every enumerated device, pass the complete registration for that exact device to the registry:

- provenance-bearing canonical identity evidence (not only vendor/device IDs or a DRM node pathname);
- exact native PhysicalDevice handle;
- exact per-device context, or a documented retained shared DDX context plus the per-device handle;
- immutable typed operation vectors required by the advertised capabilities;
- owning DDX/module-role generation and lifetime reference required by the current registry contract.

Use the semantic contract in `spec/device-registry-architecture.md` §7. The names there are semantic guidance, not mandatory exported C symbols. Do not invent an intermediate per-device Provider object. Do not place the native handle or device context in a process-global singleton or in a Screen private.

If the current Xserver prototype cannot yet express this descriptor, stop at the adapter seam and report the exact type/function gap. Do not create a competing registry or temporary registration API with weaker publication/lifetime semantics. Do not pass `XaveriusProviderCapabilities *` as if it were an operation table; it is metadata, not executable dispatch. Do not fabricate UUIDs, queue data, capabilities, or successful registrations. A candidate MUST NOT become client-visible until the registry has validated the exact binding and obtained its complete immutable snapshot through that binding.

### 2.3 Screen API

Reduce `XaveriusDDXOps` to Screen-local behavior only. Remove these device-level members entirely:

- `EnumeratePhysicalDevices`
- `GetPhysicalDeviceProperty`
- `GetPhysicalDeviceQueueFamilyProperties`

Keep `XaveriusScreenInit()`, `ScreenInit`, and `ScreenFini` for Screen-local initialization/cleanup only. The Screen close hook may release its Screen private and detach its exact ScreenAttachment when that later phase is implemented. It MUST NOT unregister a shared PhysicalDevice, release the DDX-wide discovery context, or decide which devices exist.

### 2.4 Request path

`ProcXaveriusEnumeratePhysicalDevices()` MUST be read-only with respect to discovery and registration. It serializes the already-published process-wide registry only. It MUST NOT:

- walk `screenInfo.screens`;
- retrieve a Screen private to discover devices;
- call a DDX enumeration callback;
- open DRM nodes or initialize a Vulkan instance;
- allocate/register PhysicalDevices as a side effect.

Property and queue-family requests are not discovery paths either. They MUST serialize the already-published immutable snapshot and MUST NOT re-query another DDX, refresh snapshot fields, or lazily initialize the registry.

## 3. Xlibre/modesetting integration — verified lifecycle and required seam

The target tree was inspected at Xserver commit `89df8ba0bc41dbb4b291b2242b9945661bb47fad`. Its relevant startup order is:

1. `InitOutput()` calls `config_pre_init()`; `config_udev_pre_init()` creates the udev monitor, installs the DRM filter when enabled, and calls `udev_monitor_enable_receiving()`.
2. `xf86BusProbe()` runs next. The platform-bus path calls `config_odev_probe()` and populates `xf86_platform_devices`; the PCI scan also runs here. This is before configured DDX modules are loaded.
3. DDX modules are then loaded and register `DriverRec` entries. `xf86BusConfig()` follows; its existing `xf86CallDriverProbe()` path invokes `platformProbe`, `PciProbe`, or `Probe`.
4. Per-`ScrnInfoPtr` `PreInit()` and per-`ScreenPtr` `ScreenInit()`/`FreeScreen()` occur later.
5. `InitInput()` runs later still. `config_udev_init()` performs its enumeration and only then installs `SetNotifyFd(..., socket_handler, ...)` for event-loop delivery.

Two details matter:

- The monitor starts receiving before `xf86BusProbe()`; it is wrong to claim that observation starts only in `InitInput()`. However, normal `SetNotifyFd` dispatch is installed later, so events racing with the initial scan can remain queued. Enabling the monitor alone does not prove initial reconciliation is complete.
- `config_udev_odev_probe()` matches DRM `card[0-9]*`, not render-node names. `xf86_platform_devices` is not a complete executable inventory; render-only and compute-only devices must still be found by DDX backend enumeration.

### 3.1 Required DDX callback window

The narrowest suitable existing core window is the beginning of `xf86BusConfig()`: DDX modules and their `DriverRec` entries are available, the initial bus/platform scan has run, and the Screen-oriented `xf86CallDriverProbe()` path has not started.

The current `DriverRec` has no DDX-wide PhysicalDevice discovery callback. Phase A therefore requires a small explicit core-to-DDX seam: preferably an optional driver-level callback associated with `DriverRec` (or an equivalent registered callback with identical ownership and ordering), invoked once per loaded DDX enumerator/module generation before any Screen-oriented probe. If extending `DriverRec`, append the member rather than inserting it among existing members; preserve existing field offsets and report module-ABI implications. Do not rename existing members or change `platformProbe`, `PciProbe`, or `Probe` semantics.

The callback must have a once-per-generation guard; use a DDX-owned context independent of `ScrnInfoPtr` and `ScreenPtr`; enumerate every device served by that DDX, including render-only/no-Screen devices; register complete per-device bindings directly with the process-wide registry; return the classified pass result from §2.1; and have an explicit teardown path independent of `FreeScreen()`. The callback name and exact C signature are implementation-defined. A different mechanism is acceptable only if its call graph, ownership, generation handling, and ordering are equally explicit.

Do not put discovery in `ms_pci_probe()`, `ms_platform_probe()`, `xf86CallDriverProbe()`, or a modesetting Screen callback as a substitute. Those are Screen-probing/configuration paths and can be retried or skipped according to Screen/output matching. The modesetting paths include `check_outputs()` and `xf86AllocateScreen()`; neither may gate registration. `PreInit()` is per-`ScrnInfo`, and its entity fd is not a DDX-wide inventory. Do not use the first Screen, platform device, Entity, or GPU Screen as inventory source or default-device policy, and do not reuse the first Screen's DRM fd/context for other PhysicalDevices.

If modesetting cannot create a backend context for a render-only/no-Screen device, do not pretend that a Screen probe solves it. Add a genuinely DDX-wide backend path with correct ownership, or report why modesetting is not yet an XAverius-capable DDX and identify the correct adapter boundary. A precise blocker is preferable to fake support.

### 3.2 Startup observation and event reconciliation

The startup barrier is part of Phase A. The current tree enables udev reception early but installs normal event-loop delivery later in `InitInput()`. Before initial devices are published or the barrier opens, the implementation must establish the initial DRM identity/hotplug observation, account for events queued since `udev_monitor_enable_receiving()`, reconcile scan results and add/remove events using explicit source/device generations and observation ordering, and transfer ongoing delivery to the event loop without a gap or unordered duplicate transition.

The later `config_udev_init()` scan and `SetNotifyFd()` registration do not satisfy this pre-publication requirement merely because the monitor socket was enabled earlier. If the current udev/config API cannot expose an ordered early snapshot and event drain, add the smallest targeted core/config adapter and report its exact API and ownership. Do not bypass the server serialization domain or treat an unprocessed queued event as reconciled. If a complete initial observation cannot be established, report terminal UNAVAILABLE/FAILED; do not fabricate removal or publish an ambiguous candidate.

The initial barrier closes only after every configured DDX pass and the platform identity/hotplug initial pass is terminal COMPLETE or UNAVAILABLE/FAILED, identity canonicalization and deterministic binding selection are resolved for publishable candidates, and every published candidate has a complete snapshot. PENDING keeps the barrier closed. Terminal failure is accounted for; it does not imply physical removal or block independent completed devices indefinitely. The barrier must not wait for Screen creation, RandR, ScreenAttachment, or a window.

Phase A need not implement all ongoing hotplug handling, but it must wire or preserve startup observation-before-scan and initial-event reconciliation. If that minimum path does not exist, mark Phase A BLOCKED/NOT ACCEPTED and identify the exact missing adapter/API; do not defer it silently.
## 4. Identity and multiplicity rules

- Enumerate all devices served by one DDX instance, not just the device attached to one configured Screen.
- Correlate DRM primary/render nodes by the underlying DRM device identity and canonical sysfs/device relationship. A pathname, minor number, fd identity, or node basename is not sufficient.
- The DDX MUST deduplicate aliases it discovers for one physical incarnation (including handles obtained through multiple Vulkan instances) before submitting per-device registrations. Cross-DDX identity canonicalization and deterministic binding selection remain registry responsibilities; Phase A MUST use that normative registry contract and MUST NOT implement a competing DDX-side global arbitration policy.
- Multiple Screens referring to one GPU do not cause repeated device registration.
- One Screen may later attach to multiple PhysicalDevices; Screen topology does not define inventory membership.
- Two distinct PhysicalDevices in one DDX context must retain distinct exact native handles and distinct binding records. Each binding MUST reference its correct context; the contexts MAY be one explicitly retained shared DDX context where the normative binding contract permits that, or separate per-device contexts. Sharing module code/context MUST NOT collapse device handles or binding identity.
- Repeated pass invocation for the same DDX generation must be idempotent. It must not overwrite a previously published binding ("last writer wins" is forbidden).
- An ambiguous or conflicting identity is left unpublished and reported. Do not guess by vendor/device ID, name, enumeration order, or first-Screen selection.

Do not expand this phase into a second implementation of registry identity matching or cross-DDX duplicate arbitration. The registry owns those decisions. Phase A must nevertheless use the existing normative canonicalization/selection/publication contract; if that contract is absent or cannot be called, keep candidates unpublished and report the precise missing registry operation. DDX-local alias deduplication remains the DDX's responsibility.

## 5. Required tests (must be reproducible)

Add a focused test harness using a fake DDX enumerator/backend registration fixture. It must not require a real GPU or X11 Screen to prove the lifecycle separation.

| Test | Setup | Required assertion |
|---|---|---|
| A1 zero devices | DDX pass returns an empty device set; create zero Screens | Pass completes successfully; registry remains empty; no fabricated device |
| A2 one device / zero Screens | One complete fake device binding; create zero Screens | Exactly one PhysicalDevice is published and enumerable |
| A3 multiple devices / zero Screens | At least two distinct identities, handles, and contexts; create zero Screens | Both devices are published exactly once; no first-device truncation |
| A4 repeat pass | Invoke the same DDX generation/pass twice | No duplicate XID/publication and no binding overwrite |
| A5 multiple Screens / one device | One device registration, then exercise two lightweight Screen-lifecycle fixtures (do not implement the later ScreenAttachment subsystem in this phase) | Still exactly one PhysicalDevice; closing one Screen invokes no device-unregister path and does not unregister the shared binding |
| A6 headless device | Device has no connector and no Screen fixture | Device remains registered/enumerable |
| A7 request purity | Invoke EnumeratePhysicalDevices after registration | No DDX enumerate callback, DRM open, Vulkan init, or registry mutation occurs |
| A8 error path | One candidate has incomplete/failed registration, or the DDX scan itself fails | The failed candidate gets no partial record/XID and its failed binding generation is not reused; independent fully validated candidates follow the registry's per-device transaction rules; the pass reports COMPLETE only if the scan reached its end and every candidate has a final disposition, otherwise terminal UNAVAILABLE/FAILED (or PENDING while work remains) |

If current registry transactionality cannot yet guarantee A4 or the per-candidate rollback portion of A8, write the test at the DDX-pass boundary and mark the registry-level assertion BLOCKED by the exact missing API. Do not impose all-or-nothing rollback across unrelated devices unless the normative registry contract requires it; do not weaken the per-candidate no-partial-publication rule or claim it passed. A failed candidate does not roll back unrelated complete candidates, but a pass that did not enumerate/reach a final disposition for every candidate is not COMPLETE.

| A9 startup barrier and event race | Start platform identity/hotplug observation before the initial DDX scan; inject add/remove observations during the scan and hold one adapter PENDING | Initial inventory remains hidden while any configured initial pass is PENDING; ordered events are reconciled against exact source/device generations; terminal failure does not fabricate REMOVED or block independent completed devices forever; closing the barrier does not wait for Screens; a late registration does not reopen it or mutate an already published binding/snapshot. |

Build/test report must include exact commands, exit status, and relevant output. "Build clean" without commands is not evidence. Runtime hardware testing is additional evidence, not a substitute for the deterministic harness.

## 6. Change discipline — minimal diffs only

The implementation task is not permission to rename or reformat unrelated code.

- Preserve existing public/internal symbol names, type names, file names, directory layout, comment style, formatting, and local coding conventions unless a specific item conflicts with a normative requirement or prevents the required lifecycle separation.
- Do not perform cosmetic renames, broad formatting, whitespace-only cleanup, include sorting, file splitting/merging, generalized refactoring, or unrelated cleanup as part of Phase A.
- Do not rename existing APIs merely to make them resemble names used in the specification. Specification names such as `GpuRegistryRegisterDdxDevice` describe semantic contracts unless the normative spec explicitly declares an ABI symbol name.
- Prefer the smallest additive or targeted change that establishes the required DDX-wide lifecycle and removes the explicitly forbidden Screen-level device callbacks.
- If a rename, file move, formatting change, or broader refactor is genuinely required, explain the concrete technical/normative reason in the commit report and keep it limited to the affected code.
- Keep unrelated hunks out of the commit. Review the final diff for accidental formatting churn and report its scope.
- Do not rewrite existing comments or documentation just for stylistic consistency. Update only statements made incorrect by the implementation.

A Phase A submission with broad unexplained renames, formatting churn, or unrelated refactoring is NOT ACCEPTED even if it builds.

## 7. Forbidden shortcuts / automatic rejection

Any of the following means Phase A is NOT ACCEPTED:

- registration only from `ScreenInit()`, `FreeScreen()`, or a Screen close callback;
- a function whose only source of devices is `screenInfo.screens`;
- selecting the first Screen, first GPU, first Entity, or first DRM node as the inventory;
- registration gated on connector/output detection or successful Screen allocation;
- leaving the three PhysicalDevice callbacks in `XaveriusDDXOps`;
- client requests that lazily discover/register devices;
- a second registry, DDX-local public XID namespace, or independent Vulkan-ICD candidate list;
- a Provider object used as an intermediate per-device dispatch target;
- snapshot/capability data masquerading as executable operation vectors;
- overwriting a published device's binding on duplicate registration;
- fake success, zero-filled UUIDs, guessed identity, fabricated capabilities, or silently skipped devices;
- tests that create a Screen before asserting discovery, or that test only one device.

## 8. Required implementation-agent response

Commit the implementation to `X11Libre/xserver:wip/xaverius`. Then append one concise report under the Phase A heading in the spec coordination board. Use this exact structure:

1. **Agent / branch / commit:** full repository, branch, full SHA, parent SHA.
2. **Changed files:** paths and one-line purpose each.
3. **DDX enumeration:** exact function name, DDX instance owner, enumeration source, and loop that visits every device.
4. **Registration call:** exact call site and descriptor fields passed for each device.
5. **Lifecycle proof:** why this runs without `ScrnInfoPtr`/`ScreenPtr`; where it runs relative to initial inventory exposure; how no-Screen devices are covered.
6. **Modesetting decision:** exact source call chain and why chosen hook is valid; or a precise blocker explaining why modesetting cannot yet serve as the XAverius DDX.
7. **Screen separation:** show that the three callbacks are gone from `XaveriusDDXOps` and Screen close cannot unregister a PhysicalDevice.
8. **Tests:** A1–A9 individually PASS/FAIL/BLOCKED, exact commands, exit status, output summary.
9. **Open blockers:** exact missing APIs/ownership assumptions. Do not call a blocked item complete.

No Phase B work is authorized until the Phase A implementation is reviewed and accepted. If a required later-phase registry API blocks a test, report the dependency; do not implement an ad-hoc replacement.

## 9. Reviewer checklist

The reviewer will independently inspect the branch tip and diffs, not accept the report at face value. Phase A is accepted only when:

- the DDX-wide entry point is reachable in the actual server startup/device lifecycle;
- the call graph has no Screen dependency;
- the DDX loop covers every served device and retains exact per-device handles/contexts;
- zero-Screen, multi-device, repeat-pass, headless, request-purity, and startup-barrier tests pass; any later-phase ScreenAttachment behavior is isolated to a fixture and is not claimed as implemented;
- Screen callbacks and teardown are Screen-local;
- no forbidden shortcut above exists;
- exact Xserver build/test evidence is supplied.

Until then the board status remains **ACTIVE / NOT ACCEPTED**.
