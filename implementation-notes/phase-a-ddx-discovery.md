# Phase A — DDX-wide PhysicalDevice discovery (X11Libre Xserver)

**Status:** ACTIVE — implementation agents must execute this task before Phase B.  
**Target:** `X11Libre/xserver:wip/xaverius`  
**Specification branch:** `metux/xav-design:docs/restructure-2026-10-21`  
**Current implementation baseline inspected:** `89df8ba0bc41dbb4b291b2242b9945661bb47fad`  
**Normative authority:** `spec/device-registry-architecture.md` §§2.1–2.4, 7, 8.1–8.2; `spec/devices.md` (DDX registration and enumeration); `implementation-notes/ddx-device-registration.md`.

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

- It is invoked once for each DDX backend/device-enumerator generation, not once per Screen.
- It receives or resolves a DDX-owned context whose lifetime is independent of `ScrnInfo` and Screen private storage.
- It enumerates the complete device set owned/served by that DDX context.
- It submits each exact device registration directly to the XAverius registry.
- It reports a classified pass result: complete, unavailable/failed, or pending if the existing startup lifecycle genuinely supports asynchronous completion. Do not turn an enumeration failure into physical removal.
- It is safe to invoke again for the same generation. Repeated invocation must not duplicate publication or silently replace an existing binding.
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

If the current Xserver prototype cannot yet express this descriptor, stop at the adapter seam and report the exact type/function gap. Do not pass `XaveriusProviderCapabilities *` as if it were an operation table; it is metadata, not executable dispatch. Do not fabricate UUIDs, queue data, capabilities, or successful registrations.

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

Property and queue-family requests are not discovery paths either. Do not use them to lazily initialize the registry.

## 3. Xlibre/modesetting integration — mandatory investigation, no guessed hook

The current target tree has distinct modesetting paths:

- `ms_pci_probe()` and `ms_platform_probe()`;
- output checks such as `check_outputs()`;
- `xf86AllocateScreen()`;
- per-`ScrnInfoPtr` `PreInit()`;
- per-`ScreenPtr` `ScreenInit()` and `FreeScreen()`.

The last three are not DDX-wide discovery hooks. In particular:

- Do NOT put the complete device scan only in `ScreenInit()`.
- Do NOT gate XAverius registration on `check_outputs()`, connector count, `xf86AllocateScreen()`, GPU-Screen creation, or successful RandR initialization.
- Do NOT treat `PreInit()` as DDX-wide merely because it opens a DRM fd; it is per-`ScrnInfo`.
- Do NOT use `screenInfo.screens[0]`, the first platform device, the first Entity, or the first GPU Screen as the inventory source or default-device policy.

Trace the real target call graph and select the narrowest DDX-owned lifecycle point where the backend can enumerate all devices it serves and has the exact backend handle/context needed for registration. If the modesetting driver's current ownership model cannot create a backend context for a render-only/no-Screen device, do not pretend that a Screen probe solves it. Either add a genuinely DDX-wide device-enumeration path with correct ownership, or report why modesetting is not yet an XAverius-capable DDX and identify the correct DDX adapter boundary. A blocker report is preferable to fake support.

The DDX registration pass must complete (or report unavailable/failed) before the initial XAverius inventory is exposed to clients. Respect the startup discovery barrier in §2.4: it does not wait for Screen creation, RandR, or a window. Do not implement the full platform hotplug/event-reconciliation subsystem in Phase A unless it is already required to make the initial pass correct; record any remaining barrier integration dependency explicitly.

## 4. Identity and multiplicity rules

- Enumerate all devices served by one DDX instance, not just the device attached to one configured Screen.
- Correlate DRM primary/render nodes by the underlying DRM device identity and canonical sysfs/device relationship. A pathname, minor number, fd identity, or node basename is not sufficient.
- DDX-local aliases for one physical incarnation must be deduplicated before multiple registrations can publish duplicates.
- Multiple Screens referring to one GPU do not cause repeated device registration.
- One Screen may later attach to multiple PhysicalDevices; Screen topology does not define inventory membership.
- Two distinct PhysicalDevices in one DDX context must retain distinct native handles and contexts even if they share module code.
- Repeated pass invocation for the same DDX generation must be idempotent. It must not overwrite a previously published binding ("last writer wins" is forbidden).
- An ambiguous or conflicting identity is left unpublished and reported. Do not guess by vendor/device ID, name, enumeration order, or first-Screen selection.

Do not expand this phase into the full identity-evidence/duplicate-arbitration implementation if the registry contract is not yet present. Instead, keep the adapter boundary typed and report the precise missing registry operation. The above behaviors remain acceptance requirements for the completed integration.

## 5. Required tests (must be reproducible)

Add a focused test harness using a fake DDX enumerator/backend registration fixture. It must not require a real GPU or X11 Screen to prove the lifecycle separation.

| Test | Setup | Required assertion |
|---|---|---|
| A1 zero devices | DDX pass returns an empty device set; create zero Screens | Pass completes successfully; registry remains empty; no fabricated device |
| A2 one device / zero Screens | One complete fake device binding; create zero Screens | Exactly one PhysicalDevice is published and enumerable |
| A3 multiple devices / zero Screens | At least two distinct identities, handles, and contexts; create zero Screens | Both devices are published exactly once; no first-device truncation |
| A4 repeat pass | Invoke the same DDX generation/pass twice | No duplicate XID/publication and no binding overwrite |
| A5 multiple Screens / one device | One device registration, then create two Screen fixtures/attachments | Still exactly one PhysicalDevice; closing one Screen does not unregister it |
| A6 headless device | Device has no connector and no Screen fixture | Device remains registered/enumerable |
| A7 request purity | Invoke EnumeratePhysicalDevices after registration | No DDX enumerate callback, DRM open, Vulkan init, or registry mutation occurs |
| A8 error path | DDX enumeration fails partway through | No partial/fabricated publication; pass reports failure/unavailable and retry semantics are documented |

If current registry transactionality cannot yet guarantee A4/A8, write the test at the DDX-pass boundary and mark the registry-level assertion blocked by the exact missing later-phase API. Do not weaken the test or claim it passed.

Build/test report must include exact commands, exit status, and relevant output. "Build clean" without commands is not evidence. Runtime hardware testing is additional evidence, not a substitute for the deterministic harness.

## 6. Forbidden shortcuts / automatic rejection

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

## 7. Required implementation-agent response

Commit the implementation to `X11Libre/xserver:wip/xaverius`. Then append one concise report under the Phase A heading in the spec coordination board. Use this exact structure:

1. **Agent / branch / commit:** full repository, branch, full SHA, parent SHA.
2. **Changed files:** paths and one-line purpose each.
3. **DDX enumeration:** exact function name, DDX instance owner, enumeration source, and loop that visits every device.
4. **Registration call:** exact call site and descriptor fields passed for each device.
5. **Lifecycle proof:** why this runs without `ScrnInfoPtr`/`ScreenPtr`; where it runs relative to initial inventory exposure; how no-Screen devices are covered.
6. **Modesetting decision:** exact source call chain and why chosen hook is valid; or a precise blocker explaining why modesetting cannot yet serve as the XAverius DDX.
7. **Screen separation:** show that the three callbacks are gone from `XaveriusDDXOps` and Screen close cannot unregister a PhysicalDevice.
8. **Tests:** A1–A8 individually PASS/FAIL/BLOCKED, exact commands, exit status, output summary.
9. **Open blockers:** exact missing APIs/ownership assumptions. Do not call a blocked item complete.

No Phase B work is authorized until the Phase A implementation is reviewed and accepted. If a required later-phase registry API blocks a test, report the dependency; do not implement an ad-hoc replacement.

## 8. Reviewer checklist

The reviewer will independently inspect the branch tip and diffs, not accept the report at face value. Phase A is accepted only when:

- the DDX-wide entry point is reachable in the actual server startup/device lifecycle;
- the call graph has no Screen dependency;
- the DDX loop covers every served device and retains exact per-device handles/contexts;
- zero-Screen, multi-device, repeat-pass, headless, and request-purity tests pass or any unavoidable later-phase boundary is explicitly isolated;
- Screen callbacks and teardown are Screen-local;
- no forbidden shortcut above exists;
- exact Xserver build/test evidence is supplied.

Until then the board status remains **ACTIVE / NOT ACCEPTED**.
