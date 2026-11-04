# Registry API audit addendum — 2026-11-04

**Status:** Normative supplement to Section 7 and Section 7.1 of [the device-registry architecture](device-registry-architecture.md). If this document and the API sketch differ, this addendum governs the specific API/lifetime points below. It changes no client-visible wire field, opcode, event, or Vulkan capability.

## 1. Provider-context accessor

The sketch's pointer-returning `GpuBackendProviderGetContext()` is underspecified: it has no generation check, no failure result, and no explicit borrow lifetime. Replace it with:

```c
GpuRegistryResult GpuBackendProviderGetContext(
    GpuBackendProvider *provider, uint64_t provider_generation,
    void **out_context);
```

The function MUST initialize `*out_context = NULL` before validation. It returns `SUCCESS` only if the exact provider generation is still registered and the caller holds a retained provider reference. The returned context pointer is borrowed and valid only while that caller-owned provider reference remains held. It MUST NOT be stored in asynchronous callback data, passed to a worker that may outlive the reference, or used after provider shutdown has closed admission, except by a registry-controlled lifecycle hook explicitly authorized by this contract. A stale pointer/generation returns `STALE_GENERATION`; a finalized provider returns `NOT_FOUND`; a quarantined provider returns `QUARANTINED`. The accessor does not retain the context and does not transfer ownership.

Provider operation entry points MUST receive the provider/device/queue objects through their declared typed arguments; they MUST NOT use this accessor to bypass per-operation admission, token preparation, binding-generation validation, or resource pinning.

## 1.1 Scope after DDX-direct dispatch clarification

The `GpuBackendProvider` pointer and `GpuBackendProviderGetContext()` accessor refer only to the shared DDX module-role/control record described in `device-registry-architecture.md` §3.1. They MUST NOT be used as an intermediate per-request dispatch lookup. Per-device backend context and native physical-device handles belong to the exact PhysicalDevice binding and are passed to the typed operation entry point through its device/binding arguments. The shared role context, if any, is for module-wide resources and lifecycle coordination only. A DDX that needs no shared context may use an opaque role token solely for generation and lifetime accounting.

## 2. Provider operation-table storage

The descriptor's `ops` pointer is not the only callback-bearing storage. Every non-NULL nested table (`buffer_memory`, `shader_pipeline`, `commands`, and `synchronization`) and every function pointer reachable through those tables MUST remain immutable and executable until the provider generation's final `release_provider` call has returned.

The registry MUST validate required table pointers and required entries before publishing a provider generation. A missing entry required by an advertised operation/capability returns `UNSUPPORTED` or `INVALID_ARGUMENT` according to whether the capability itself is unsupported or the descriptor is internally inconsistent; it MUST NOT defer this failure until the first client request. Optional entries not advertised by the provider MUST be NULL or explicitly marked unsupported by the typed table contract. The provider MUST NOT replace a table or function pointer in place after registration.

The module lease that pins the provider generation MUST cover the code and read-only storage for the top-level table, all nested tables, and every function reachable from them. A provider MUST NOT place a nested table in temporary probe storage or free it when a candidate list is released.

## 3. Module-lease identity and references

`GpuProviderModuleLeaseCreate(module_owner, out_result)` MUST initialize `out_result` to `GPU_REGISTRY_INVALID_ARGUMENT` and return NULL on every failure. On success it returns one caller-owned lease reference and sets `out_result` to `SUCCESS`.

For one loaded module incarnation, one stable server-owned `module_owner` identity MUST resolve to exactly one shared lease object. A repeated Create for that same identity returns the existing lease with one additional caller-owned reference; it MUST NOT acquire a second independent loader pin. Two different owner records that are aliases for the same loaded module handle are invalid and MUST be canonicalized by the loader adapter before Create. A newly loaded incarnation, even at a reused address/handle, MUST use a new owner identity and lease generation.

Retain succeeds only while the lease is live and has a nonzero reference count. Release consumes exactly one caller-owned reference. The final release is permitted only after all provider-generation and ModuleRole references have been released; otherwise the implementation's reference accounting is inconsistent and it MUST return `BUSY` without decrementing the final reference. A successful final release removes the owner-to-lease mapping before invoking the loader's release operation outside registry locks. No caller may retain a lease by using a raw loader handle or by recreating an alias owner record.

The lease object itself is server-owned and may remain as an inert tombstone after the loader pin is released so stale lease pointers can be diagnosed; it MUST NOT keep the module mapped merely to preserve the lease object's storage.

## 4. Source, binding, and attachment removal barriers

The following meanings apply to the terminal `SUCCESS` result of the corresponding removal API:

- `GpuRegistryUnregisterDiscoverySource`: no source callback is executing or can begin; all observations owned by that exact source generation have been withdrawn or converted to independent registry-owned evidence; no later callback can submit an observation or removal claim under that generation; and the source's owner ModuleRole reference is released exactly once. `PENDING` retains the source and owner-role references. The source adapter MUST keep its callback code and event userdata alive until SUCCESS.
- `GpuRegistryRemoveProviderBinding`: no new operation can resolve the exact binding; all externally initiated calls through it have returned; all accepted tokens that can access its native handle have retired successfully; and no callback can newly name the binding. Only then may the provider remove the provider-local ID-to-native-handle mapping. `PENDING` MUST NOT authorize destroying or reusing that mapping.
- `GpuRegistryDetachScreen`: no new Screen-associated work can be admitted; all callbacks holding the attachment have retired; and its owner ModuleRole reference is released exactly once. The DDX MUST invalidate its separate Screen-to-attachment lookup before freeing Screen-private data. `PENDING` does not authorize freeing callback userdata.

Each operation is exact-generation and retryable. A repeated request while draining returns `PENDING`; after terminal success it returns `NOT_FOUND`. The registry MUST NOT turn a pending removal into success merely because the owning Screen, source object, or DDX has disappeared.

## 5. Provider shutdown and quiescence barrier

`GpuRegistryBeginProviderShutdown` closes admission for the exact provider generation immediately. The provider teardown coordinator then removes every binding owned by that generation, withdraws only its own discovery observations and attachments where applicable, drains all accepted operation tokens, and waits for all externally initiated provider calls to return. It MUST retain the provider reference and module lease while any of these steps is pending.

`GpuRegistryTryQuiesceProvider` MUST return `PENDING` without calling `quiesce_provider` until all bindings are terminally removed, all accepted tokens have successful retirement, all provider-owned objects that require provider code have been destroyed or safely quarantined, all provider entry-point calls have returned, and all callback bridges into or out of the provider have retired. The provider hook itself is responsible for stopping and joining provider-internal workers and closing provider-owned callback dispatch. It MUST NOT wait for GPU progress while holding an Xserver lifecycle lock.

After quiescence SUCCESS, the only permitted entry into provider module code is the one registry-controlled final `release_provider` call. The provider's native handle maps, operation tables, callbacks, and context remain pinned until that call returns. Then the provider-generation lease reference is released. A shared module lease remains live while any other provider generation or ModuleRole still references it.

A provider-generation teardown failure that is not a `GPU_PROVIDER_FATAL` contract violation MAY remain retryable if the provider can later prove safety. `GPU_PROVIDER_FATAL` is different: the existing quarantine rule remains terminal for normal APIs. Neither `TryQuiesceProvider` nor `FinalizeProviderShutdown` may call provider code after fatal quarantine.

## 6. Operation-token handoff clarification

The `GpuProviderOperationToken *` returned by `GpuRegistryPrepareOperation` is a temporary call-in capability, not a reference to the token record. It is valid only for the immediate synchronous invocation of the matching provider operation entry point. The provider MUST copy the token ID and generation during that invocation and store only those scalar values in callback userdata. The server retains the token record and its resource references independently until successful retirement.

The server MUST NOT pass the temporary token pointer to a worker, completion callback, queue, or provider-owned object. The provider MUST NOT dereference it after its operation entry point returns. The ID/generation accessors MUST validate the pointer while that entry point is active; invalid use is a provider-contract violation and quarantines the provider generation.

A callback may arrive before the operation entry point returns. The completion sink copies it into server-owned storage and queues it; the registry buffers its semantic effect until the server commits acceptance after the provider returns SUCCESS. The callback does not commit acceptance and does not release the token. If the provider returns a non-success result after any callback or backend access has occurred, the token and all references are quarantined.

## 7. Additional conformance vectors

The architecture conformance suite MUST include the following cases:

- **143 — Context accessor lifetime:** reject stale/finalized generations; return a borrowed context only while a retained provider reference exists; do not extend lifetime.
- **144 — Nested operation-table lifetime:** reject incomplete advertised tables; retain all nested table storage and reachable code until final provider release.
- **145 — Shared module lease identity:** repeated Create for one owner returns the same lease with balanced references; alias owner records for one loaded module are rejected; reload gets a distinct identity.
- **146 — Final lease release barrier:** reject final release while provider/role references remain; release loader pin only after the last reference and outside registry locks.
- **147 — Source unregister barrier:** PENDING retains callback code/owner role; SUCCESS proves no callback can run and source observations are withdrawn.
- **148 — Binding removal barrier:** PENDING preserves native handle mapping; SUCCESS proves no call/token/callback can use it.
- **149 — Provider quiescence preconditions:** do not call the provider hook while any binding, token, provider object, external call, or callback bridge remains.
- **150 — Token pointer confinement:** provider may copy token scalars during entry; storing/dereferencing the token pointer after return is rejected and quarantines the provider.

These vectors test the internal architecture/API contract. They do not change the wire ABI or imply runtime Xlibre/Vulkan acceptance.
