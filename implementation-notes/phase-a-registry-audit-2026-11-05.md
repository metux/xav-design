# Xaverius registry audit — 2026-11-05

**Target:** `X11Libre/xserver:wip/xaverius`  
**Audited tip:** `deb0e445001389be031fa7e006e3e2e216616b50`  
**Parent:** `98ce6f6f281a8b8001d967bafd3debe8ea4db4fa`  
**Result:** **PHASE A NOT ACCEPTED — registry model and lifecycle are not safe to use.**  
**Scope:** source/history audit only; no Xserver source was changed.

## 1. Executive conclusion

The concern is justified. This is not just a naming cleanup. The current code has no coherent single PhysicalDevice object/binding model, the registration API has regressed below the normative contract, the identity is fabricated from unrelated capability fields, DIX publication is not failure-atomic, resource initialization is absent from the active init path, and finalization can double-free or leave stale list entries.

The current modesetting callback also does not call the registry at all. A registry may compile and exist as a global list, but the current branch does not establish a working populated inventory.

Do not build Phase B on this state. Do not solve this by renaming types or reformatting files. First agree on one canonical object model and repair the registration/resource lifecycle with a narrowly scoped diff.

## 2. Current type model and overlap

The branch currently has several competing representations of the same conceptual PhysicalDevice:

| Type | Current location | Actual role / problem |
|---|---|---|
| `XaveriusDeviceRec` / `XaveriusDevicePtr` | `xaverius_intern.h` | Actual registry list object: XID, identity, status, generation, embedded `caps`, native handle, context. |
| `XaveriusDeviceCapabilities` | `xaverius_priv.h` | Metadata/snapshot structure. It repeats device properties and owns pointer-shaped fields, but also contains an unused `provider_handle` that is not snapshot metadata. |
| `XaveriusPhysicalDeviceRec` / Ptr | `xaverius.h` | Legacy second PhysicalDevice record with XID and another copy of vendor/device/API/driver/queue/name/workgroup/UUID/timeline fields. No use sites were found in the branch. |
| `PhysicalDeviceInfoRec` / Ptr | `xaverius.h` | Legacy enumeration-info record duplicating fields already represented by the wire type. No use sites were found. |
| `xAveriusPhysicalDeviceInfo` | `xaverius_proto.h` | Actual wire reply record. This is appropriately separate from the server-owned object, but the legacy internal info record is redundant. |
| `XaveriusDeviceIdentity` | `xaverius_priv.h` | Identity evidence, but it incorrectly also carries `drm_fd`, which is a handle/lifetime value rather than identity. |
| `GpuDeviceBackendOps` | `xaverius_priv.h` | Operation-table declaration only. It is not stored in the registry object or accepted by registration. |

This is semantic overlap, not merely similarly named C structs. The actual registry object embeds a capability record, while a second unused `XaveriusPhysicalDeviceRec` duplicates much of that record's property set. The enumeration path then serializes a third, wire-specific representation.

The intended separation should be explicit and singular:

- one server-owned PhysicalDevice registry record/resource, containing identity/incarnation, lifecycle/generation, immutable queried snapshot, and the exact binding reference;
- one immutable snapshot type containing only queried properties/queues/memory data;
- one exact per-device binding containing native handle, per-device context, typed operation vectors, and its ModuleRole/lifetime reference;
- separate wire structs for protocol serialization;
- no second internal PhysicalDevice record and no Provider-shaped handle hidden in capabilities.

Do not perform broad renames as a first step. Remove/merge redundant types only after call sites and ownership are mapped.

## 3. Confirmed blockers at the audited tip

### R1. Registration API lost the required identity and binding

At `6dffb09bf00e807c90395348ba4c65e4b80ef976`, `XaveriusRegisterDeviceDirect(identity, caps, native_handle, context)` was replaced by:

```c
bool XaveriusRegisterDevice(const XaveriusDeviceCapabilities *caps);
```

The same change removed assignments to `dev->native_handle` and `dev->context`. The current `XaveriusDeviceRec` still contains those fields, but `calloc` leaves them zero. The accessor therefore returns zero for an uninitialized native handle rather than a meaningful handle or `-1`.

The public header comment still claims registration passes capabilities/ops, but the signature accepts neither identity nor ops. `GpuDeviceBackendOps` is declared but is not part of the registration descriptor or registry record. `XaveriusDeviceCapabilities.provider_handle` is the only opaque handle-like field; it is unused and has no ownership contract.

This directly violates Phase-A correction C4: complete binding is a publication prerequisite, not a Phase-B enhancement.

### R2. Identity is fabricated from unrelated fields

In `registry.c:XaveriusRegisterDevice()`, the code maps:

- `vendor_id` → `identity.domain`
- `device_id` → `identity.bus`
- `api_version` → `identity.device`
- `driver_version` → `identity.function`

These are not PCI BDF coordinates. The function does not receive `XaveriusDeviceIdentity` at all, never supplies a Vulkan UUID, and leaves DRM identity zero. It only checks that `device_name` is non-empty.

Consequences include false identity collisions between devices with the same vendor/device/API/driver values and unstable identity when API/driver versions change. A display name is not identity evidence. The current identity comparison's all-zero-BDF heuristic also cannot represent a legitimate PCI BDF 0000:00:00.0 without a separate `has_pci_identity` discriminator.

### R3. DIX resource insertion is still duplicated and not failure-atomic

Current `registry.c` contains **two** `AddResource(xid, XaveriusPhysicalDeviceType, dev)` calls for the same XID and pointer:

1. the first occurs immediately after the shallow `dev->caps = *caps`;
2. only afterwards are dynamic snapshot fields deep-copied;
3. a second AddResource is then attempted after the copies.

The second insertion conflicts with the first. More importantly, if any deep-copy allocation fails, the code frees `dev` while the first DIX resource may still refer to it. The second AddResource failure path also frees the object while the first resource remains registered.

The claimed fix commit `d443f4eeb0ee978862c2ac6f1b2750baf38dc040` says it removes the duplicate AddResource call, but the source at that commit still has two calls (lines 187 and 240); the current tip still has two (lines 182 and 235). The commit message is not evidence of a fix.

### R4. Capability snapshot copying is incomplete

`dev->caps = *caps` initially shallow-copies all pointers. Some arrays/name are later copied, but:

- `provider_handle` remains a shallow, unowned pointer;
- pointer/count consistency is not validated;
- if a pointer is non-NULL with count zero, the shallow pointer can remain in the published record;
- there is no complete snapshot validation before publication.

The physical device destructor in `device.c` only calls `free(dev)`; it does not free the copied name/queue/memory arrays. Conversely, `XaveriusRegistryFini()` frees those arrays directly. Ownership is split between incompatible cleanup paths.

### R5. Resource-type initialization is not called

`device.c` defines `xaverius_device_init()`, which creates `XaveriusPhysicalDeviceType` and the other DIX resource types. A scan of every C/header file under `Xext/xaverius` found only the function definition and declaration: **there is no call site**.

The active `init.c:XaveriusExtensionInit()` calls `XaveriusRegistryInit()` but not `xaverius_device_init()`. Thus `XaveriusPhysicalDeviceType` remains zero when registration attempts to call AddResource. The `XaveriusDevicesInit()` declaration added to `xaverius_intern.h` has no matching definition; the actual function is lower-case `xaverius_device_init()`.

The latest commit `deb0e445001389be031fa7e006e3e2e216616b50` does not fix this. It renames a fini function and adds more fini calls, but still does not initialize resource types.

### R6. Registry and DIX destruction have contradictory ownership

- `XaveriusRegistryFini()` unlinks and directly frees every registry record, but does not remove its DIX resource.
- `XaveriusDevicesFini()` calls `FreeResourceByType(..., XaveriusPhysicalDeviceType, TRUE)`, whose PhysicalDevice destructor calls `free(dev)` again.
- Current `init.c:XaveriusExtensionFini()` calls RegistryFini first and DevicesFini second. Once resource types/registration are made operational, that order can double-free the same object.
- The alternative `xaverius.c` cleanup path uses the opposite order in `xaverius_extension_fini()`; that frees DIX resources first, but the destructor does not unlink registry list entries, so RegistryFini then walks stale pointers.
- `xaverius.c` also has a separate ExtensionFini callback that calls RegistryFini alone.

There must be one canonical shutdown path: retire/unpublish each record through the DIX resource-destruction path exactly once; the resource destructor must unlink the registry entry and release every owned field/reference. RegistryFini must not independently free a published resource object.

### R7. There are competing extension init/fini implementations

The Meson source list compiles both `init.c` and `xaverius.c`. Both define global `XaveriusExtensionInit()` and `noXaveriusExtension`, but have different dispatch symbols, event-base variables and finalization paths. This is an unnecessary second lifecycle implementation and creates duplicate-symbol/selection ambiguity depending on which archive members are pulled.

The current `init.c` registers `ProcXaveriusDispatch` for both normal and swapped dispatch. `xaverius.c` instead references `ProcXAveriusDispatch`/`SProcXAveriusDispatch`, while the current `dispatch.c` defines `ProcXaveriusDispatch`. These are not one coherent entry path.

Choose the server's actual extension registration path and keep one definition, one dispatch pairing, one registry init and one registry fini.

### R8. No DDX currently populates the registry

The branch scan found no call to `XaveriusRegisterDevice()` outside its declaration/definition. The modesetting callback still builds local `identity` and `caps` variables, then explicitly discards them with `(void)identity; (void)caps;` and closes/retains no registration binding. Its own comment says registration is deferred to Phase B.

Therefore the registry is not merely broken internally; the current branch has no effective registration caller. A no-op callback is not Phase-A discovery.

### R9. Phase-B code remains in the branch before Phase-A acceptance

The current tree still includes Compute Memory/Buffer/Shader handlers and operation-table declarations. This is contrary to the active gate. In particular, the prior audit already found fabricated memory requirements and transfers that can return success without backend execution. Keep Phase B unauthorized; remove those handlers from the Phase-A patch or make them fail closed under C9.

## 4. Relevant history and regression points

Branch history was inspected from the actual `wip/xaverius` ref, not inferred from commit messages alone:

1. `7eb8b738f7ba8725748e2fa4b7c5e686c21afd91` introduced a PhysicalDevice inventory with separate provider/capability/lifecycle/screen-attachment concepts.
2. `6b36065ee9c7bf58173a7fb9437886bf26332e5f` and the following inventory simplification replaced the inventory object with a process-global list and dropped several of those explicit records.
3. `6deb8aec906953c0fba8cc48173585580e1859d8` introduced the Screen/discovery split and the `XaveriusDeviceRec` registry record.
4. `a0399e1def8667f2f9afeb7394bda5047a2e86a1` added a DDX-wide callback seam and a registration signature carrying identity, caps, native handle and context, but already had the double-AddResource/failure-atomicity defect.
5. `d443f4eeb0ee978862c2ac6f1b2750baf38dc040` claimed to fix duplicate AddResource, but its resulting source still contained two calls. It also set generation to 1 and exported the extension init symbol.
6. `6dffb09bf00e807c90395348ba4c65e4b80ef976` regressed the registration contract: it dropped identity/native handle/context from the signature and record assignment, and disabled the modesetting registration calls by replacing them with no-op casts. Its comment explicitly defers registration to Phase B, contrary to the active Phase-A task.
7. `98ce6f6f281a8b8001d967bafd3debe8ea4db4fa` attempted a C7 fix, but only changed the secondary `xaverius.c` cleanup/declaration path; it did not call `xaverius_device_init()` from the active `init.c` entry path.
8. `deb0e445001389be031fa7e006e3e2e216616b50` (commit message `1`) moved `XaveriusDevicesFini()` into more cleanup paths and added the stale `XaveriusDevicesInit()` declaration, but still did not add the missing resource-type initialization call and preserved the contradictory fini ordering.

The most important regression is step 6: the implementation went from an incomplete but explicit identity/handle/context registration descriptor to a capabilities-only API that cannot possibly satisfy the binding contract. The subsequent commits did not restore that contract.

## 5. Required repair order (do not broaden scope)

1. **Freeze the type model first.** Identify the one PhysicalDevice record, the snapshot-only type, the exact per-device binding type, and the wire-only structs. Remove only proven-unused duplicate internal records; do not mass-rename.
2. **Restore a complete registration descriptor.** It must carry structured identity evidence, exact native handle, per-device context, immutable typed ops, ModuleRole generation/reference and explicit ownership. Do not put those fields back into a Provider abstraction or into Screen state.
3. **Build identity from actual evidence.** Never derive BDF from vendor/device/API/driver version. Separate identity from file descriptors and render-node handles.
4. **Make registration one transaction.** Validate and prepare/deep-copy/query everything first; allocate XID; call AddResource exactly once; link into registry only after success. All pre-publication failure paths release provisional ownership; published objects are destroyed only through their DIX destructor.
5. **Choose one init/fini path.** Initialize resource types before any callback can register a device. One extension init definition and one fini path. Destructor unlinks registry membership and releases all owned fields; shutdown destroys DIX resources once.
6. **Restore a real population call.** Modesetting must either submit complete DDX-owned bindings during Phase A or report a precise blocker and publish nothing. Do not silently defer the required Phase-A registry population to Phase B.
7. **Remove/fail-close unauthorized Phase-B handlers.** No handler may claim success without a typed backend operation.
8. Add targeted tests for each failure boundary and run the exact-tip build matrix. Do not claim acceptance from a compile-only check.

**Minimal-diff constraint:** preserve existing file names, symbols and formatting wherever possible. Any type consolidation must be driven by the ownership model above, with every changed call site accounted for. No cosmetic renames or broad reformatting.

## 6. Acceptance status

**NOT ACCEPTED. Phase B remains unauthorized.**

The registry must not be treated as a usable implementation until R1–R9 are resolved and C1–C10/A1–A9 evidence is supplied. This audit does not authorize implementation changes in the Xserver repository; agents should make the corrections on `wip/xaverius` and report exact commits/tests on the coordination board.
