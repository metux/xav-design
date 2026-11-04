# Phase A — mandatory corrective implementation requirements

**Applies to:** `implementation-notes/phase-a-ddx-discovery.md` §§1–9.

**Status:** Mandatory acceptance criteria; Phase A remains NOT ACCEPTED until all applicable items are independently verified.

## 3.3 Mandatory corrections for the currently audited implementation

This subsection turns the outstanding source-review findings into explicit repair instructions. It is additive to §§1–3.2 and does not authorize Phase B. The current prototype is NOT ACCEPTED until every applicable item below is fixed and tested. Do not treat a comment, commit message, declaration-only header, or future-phase promise as implementation evidence.

### C1. Driver callback ABI — no unchecked trailing member

The current prototype appends `RegisterXaveriusDevices` to `DriverRec` and reads it after only checking for NULL. This is invalid for a binary DDX compiled against the older, smaller `DriverRec`: the core may read beyond the object. Appending a field alone is NOT ABI-safe.

Required correction:

- Remove the unversioned trailing-member access.
- Prefer a versioned/size-tagged registration mechanism whose size/version is validated before any optional field is read. It must be registered by the loaded DDX/module instance through a core-owned registration API, or use an existing Xorg driver-function/version mechanism whose compatibility guarantees are verified in the target tree.
- If no such mechanism can safely be used, perform an explicit video-driver ABI version bump AND enforce rejection of older modules before accessing the new callback. Merely changing a version constant without an enforced loader check is insufficient.
- Do not infer the size of an old `DriverRec` from the current compile-time `sizeof(DriverRec)`; do not probe the new member and hope it is NULL.
- Preserve all existing `DriverRec` member names, order, and semantics unless the ABI mechanism itself requires a narrowly documented change. Do not change `Probe`, `PciProbe`, or `platformProbe`.
- The report must identify the exact ABI/version gate, loader check, and compatibility behavior for old binary DDX modules.

### C2. Callback result, once-only semantics, and generation ownership

The current callback is `void` and can be invoked again whenever `xf86BusConfig()` is re-entered. Correct it as follows:

- Return the classified pass result required by §2.1: COMPLETE, PENDING, UNAVAILABLE, or FAILED. COMPLETE means the entire enumeration finished and every candidate has a final disposition; it does not mean merely that the callback returned.
- The core must retain the pass state against the exact loaded DDX module/enumerator generation. Re-entry for that same generation must return/observe its existing state and MUST NOT launch a second concurrent or duplicate pass.
- A PENDING pass must have an explicit completion transition tied to the same non-reusable generation. Duplicate, stale, or post-teardown completion must be rejected.
- FAILED/UNAVAILABLE is terminal for that pass and is accounted for by the startup barrier; it is not a removal observation and does not create or alter a PhysicalDevice.
- Do not use a process-global Boolean as the once guard: it cannot distinguish multiple DDX modules, reloads, or generations.
- State who owns the callback registration, pass state, asynchronous completion, and teardown. The core must not retain a callback or opaque pointer after the owning module generation has been quiesced.

### C3. Modesetting must enumerate its own executable devices

The current `modesetting_register_xaverius_devices()` ignores its `DriverPtr drv`, scans global `/dev/dri` names, and passes NULL context. This is not DDX-owned discovery and can register devices served by another DDX.

Required correction:

- Remove the hard-coded global `/dev/dri/card%d` / `renderD%d` scan from the modesetting callback.
- The callback must resolve an explicit modesetting DDX-instance context registered/owned by that exact loaded DDX instance. Enumerate only devices for which that context can create and retain the complete XAverius backend binding.
- Use the target platform's canonical DRM enumeration/device APIs and correlate primary/render nodes through the same underlying kernel device/sysfs identity. Do not guess node numbers, assume a contiguous range, or use a pathname/minor/basename as canonical identity.
- Do not use `drmGetBusid()` as a universal identity fallback: it is not a stable identity for all non-PCI devices and may be absent. Supply structured canonical identity evidence from the platform/device subsystem. If the supported bus cannot provide sufficient evidence, classify that candidate/pass as unresolved/UNAVAILABLE and leave it unpublished.
- Deduplicate card/render aliases of one physical incarnation before registry registration. Never register the primary and render node as two PhysicalDevices merely because both nodes exist.
- A successful registration must pass a valid exact native handle, the correct per-device context (or a documented retained shared DDX context plus exact per-device handle), complete typed operation vectors, and the owning module-role generation. NULL context is allowed only if the normative binding contract explicitly defines a truly context-free backend; otherwise it is a hard registration failure.
- If modesetting cannot provide a no-Screen executable backend context, do not fake support by opening a render node and publishing metadata. Report modesetting as BLOCKED/UNAVAILABLE for XAverius until the backend boundary exists. Other DDXs may still complete their own passes.

### C4. Complete binding is a Phase-A publication prerequisite

The current registry explicitly describes operation vectors and ModuleRole/binding generation as deferred to Phase B. That deferral is incompatible with the normative direct-binding contract and MUST be removed.

Required correction:

- Extend the existing PhysicalDevice binding/registration seam only as far as necessary to carry the complete normative descriptor: structured identity evidence, exact native handle, per-device context, immutable typed operation-vector pointers, owning ModuleRole generation/reference, and registry-assigned non-reusable binding generation.
- Validate the operation-vector version/size, required operation members, capability-to-operation consistency, role generation, handle/context validity, and ownership before publication.
- Obtain the immutable capability/property/queue/memory snapshot by querying the exact binding through its typed operations. The caller must not supply a fabricated or partially zero-filled snapshot as a substitute for those queries.
- Store the exact binding on the PhysicalDevice and make it the direct dispatch target. Do not add a Provider object, candidate list, DDX-local binding-ID dispatch proxy, or generic ModuleRole context accessor.
- Keep the module-role record limited to code/module lifetime, callback admission, and quiescence. Device context and native handle belong to the exact per-device binding.
- If a required operation is genuinely outside Phase A discovery, do not advertise the corresponding capability or publish a binding that lacks mandatory operations. Report the exact unsupported backend and keep the candidate unpublished.
- Do not label this work "Phase B": complete binding validation and retention are prerequisites to safe PhysicalDevice publication, not request-handler implementation.

### C5. Make DIX resource publication a single, failure-atomic transaction

The current `XaveriusRegisterDeviceDirect()` calls `AddResource()` before deep-copying snapshot fields and then calls `AddResource()` a second time for the same XID. This can expose a partially initialized object, fail on the second insertion, and leave dangling resource data.

Required correction:

1. Validate all input pointers/counts/lengths and acquire all required binding/module references.
2. Allocate the provisional PhysicalDevice record and deep-copy every owned field; initialize its list links, generations, status, destructor-visible fields, and complete binding before it is visible to DIX or registry iteration.
3. Query and validate the immutable snapshot through the exact binding before publication.
4. Allocate/reserve the XID using the established Xorg resource/XID rules.
5. Register the resource exactly once with the PhysicalDevice resource type and its canonical destructor.
6. Only after successful resource registration, link the record into the process-wide registry and mark it published. The registry list and DIX resource table must never disagree about whether the object is published.
7. On any failure before publication, unwind every provisional allocation/reference/handle exactly once; no client-visible XID, list entry, partial record, or leaked reference may remain. A reserved binding generation remains consumed and is never reused.
8. Do not manually free a published record behind the DIX resource table. Registry shutdown must retire/remove resources through the matching DIX resource-destruction path so the destructor is the single owner of final record cleanup. Do not both free the object directly and leave a live DIX resource pointing at it.
9. Initialize/register the PhysicalDevice resource type before the first registration. Verify the actual `xaverius_device_init()`/resource-type initialization call path and its failure behavior; a declaration or unused helper is not evidence.

Use the target tree's existing DIX resource APIs and destructor conventions. The report must name the exact resource type initializer, resource insertion function, destructor, shutdown removal path, and prove that there is exactly one insertion and one final destruction per published XID.

### C6. Define native-handle and context ownership on every return path

The current duplicate path returns success for matching identity without comparing the exact binding or disposing of the newly supplied handle/context; success and shutdown ownership are also undefined.

Required correction:

- Document whether registration borrows or transfers each input: native handle, per-device context, operation-vector storage, ModuleRole reference, and snapshot input (if any). The preferred contract is explicit transfer/retain semantics, not ambiguous "caller keeps it" comments.
- On success, the registry must own/retain exactly the references required by the binding contract until binding retirement. On failure, ownership must remain with the caller or be returned in a documented way; never silently leak or double-release.
- A duplicate registration is not unconditional success. Compare the exact identity incarnation, DDX/module-role generation, binding identity, and native-handle/context ownership. An exact replay may be idempotent and return the existing binding reference/result; a conflicting binding must return a classified conflict and must not replace the existing binding.
- A retry after a failed registration uses a fresh binding generation. Never reset or recycle a consumed generation.
- Binding removal, DDX teardown, and server shutdown must wait for operation/object/callback references as required by the normative lifetime contract. If quiescence cannot be proven, retain/quarantine the binding and module lease; do not close/free resources still reachable by backend code.
- Add failure-injection tests for every allocation, retain, snapshot-query, XID-allocation, and resource-insertion boundary, plus duplicate/conflict and shutdown cases.

### C7. Extension initialization and resource-type initialization

The source audit found the extension init symbol and PhysicalDevice resource initialization inconsistent across declarations/call sites.

Required correction:

- Keep the extension init symbol exported with the exact spelling/signature expected by the server extension registration table. Verify the declaration, definition, and registration-table reference all match and link in the actual Xorg binary.
- Initialize the PhysicalDevice DIX resource type before any device registration can occur. Initialization must be idempotent and report failure; on failure, the extension/registry must not accept registrations.
- Do not add a second wrapper/init path that can initialize or finalize the same registry twice. Choose the existing canonical server init/fini path and document it.
- Ensure extension fini cannot free registry records while DIX resources still exist. Resource destruction order must be explicit and tested.

### C8. Keep platform build portability local to the changed code

The prior CI run reported:
- redundant `strlcpy`, `strlcat`, and `strndup` declarations under `-Werror`;
- `timingsafe_memcmp` and `CSRG_BASED` macro redefinition on some BSD/RHEL configurations;
- an unresolved extension-init symbol in the SDK link;
- an unavailable `pciaccess.h` pulled into the extension source on macOS.

Required correction:

- Do not add broad platform headers such as `xf86.h` to generic XAverius extension/registry translation units merely to obtain a declaration. Put XFree86-specific integration in the narrowest xf86-only source file and use the existing public/private header boundary.
- Do not redeclare libc/OS functions already declared by Xorg portability headers. Remove redundant declarations and use the target tree's established portability wrappers/feature guards.
- Guard platform-specific macros and headers using the same conventions already present in adjacent Xserver code; do not globally redefine system macros.
- Fix the exported init symbol at its actual declaration/definition/registration-table boundary.
- Run the full supported CI matrix on the final exact commit. A successful local Linux build does not waive BSD, RHEL, macOS, or SDK link failures. Report each job's final conclusion and link.

### C9. Remove unauthorized Phase-B handlers or make them fail closed

The current branch contains Compute Memory request handlers that were added before Phase A acceptance. The audited handlers use hard-coded alignment/memory-type masks and return success for ReadBuffer/WriteBuffer without executing a backend transfer.

Required correction:

- Remove these out-of-scope handlers and their registry/wire registrations from the Phase-A submission unless they are required as pre-existing code; do not expand or polish them during this task.
- If removal would break an independently required existing build, leave only a fail-closed path that returns the defined unsupported/backend-unavailable error and cannot report success without performing the operation. Do not expose fake capabilities or success.
- Do not implement further Phase-B request handlers, wire behavior, queue submission, synchronization, presentation, or resource management until Phase A is independently ACCEPTED on the board.
- Report every out-of-scope file/hunk left in the branch and why it cannot safely be removed in this focused correction.

### C10. Required targeted regression tests for C1–C9

In addition to A1–A9, provide deterministic tests or explicit BLOCKED evidence for each:

- **C1 ABI compatibility:** load an old/smaller binary DDX fixture and prove the core never reads an absent callback field; test the selected version/size rejection path.
- **C2 pass state:** multiple DDX instances, same-generation re-entry, concurrent re-entry, PENDING completion, stale completion after reload, and teardown while PENDING.
- **C3 modesetting enumeration:** render node numbers outside 0–31, non-contiguous node numbers, card/render aliases, multiple physical devices, no-Screen devices, a device owned by another DDX, and missing canonical identity. Assert only complete devices owned by this DDX are submitted.
- **C4 binding completeness:** missing operation member, incompatible table version/size, stale ModuleRole generation, NULL/invalid context, and capability without required operation all fail before publication.
- **C5 DIX atomicity:** inject failure before/after each preparation stage and at resource insertion; assert exactly zero partial XIDs/list entries and exactly one destructor for each successful publication.
- **C6 ownership:** success, exact duplicate replay, conflicting duplicate, failed registration, retry with fresh generation, binding removal with outstanding operation, and shutdown/quarantine. Assert each handle/context/reference is released exactly once and only after safe retirement.
- **C7 init/fini:** extension symbol resolves in SDK link; resource type is initialized once before registration; repeated init/fini and resource destruction do not double-free or leave dangling resources.
- **C8 portability:** full supported CI matrix passes on the exact submitted commit, including SDK link and all previously failing platforms.
- **C9 phase gate:** verify no handler returns SUCCESS without the corresponding typed backend operation being invoked; Phase-A diff contains no new Phase-B behavior.

If a test cannot yet be run because the necessary harness/API does not exist, mark it BLOCKED, state the exact missing dependency and do not claim Phase A acceptance. Do not replace a required assertion with a source comment.

---
