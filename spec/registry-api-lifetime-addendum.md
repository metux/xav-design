# Registry API lifetime addendum

This addendum is superseded where it refers to the former `GpuBackendProvider`, provider-generation, provider-local binding-ID, or provider-context accessor API. The current normative model is in [device-registry-architecture.md](device-registry-architecture.md) §§2.4, 3, 3.1, and 7.

## Direct DDX binding

The DDX enumerates every PhysicalDevice it serves and calls `GpuRegistryRegisterDdxDevice` once per device. The registration supplies structured identity evidence, the exact native PhysicalDevice handle, per-device backend context, immutable typed operation vectors, and the owning DDX module-role generation. The registry canonicalizes the identity, validates the complete operation table, queries one immutable snapshot through that binding, and publishes the PhysicalDevice only after successful validation.

There is no independent Vulkan-ICD candidate inventory, no candidate-list callback API, no provider-local numeric binding ID, and no per-request lookup of a provider object. A selected PhysicalDevice binding is the direct dispatch target.

## Module-role control record

A `GpuModuleRole` exists only to pin unloadable DDX code and shared module resources, coordinate callback admission, and establish module-wide quiescence. It is not an execution backend. There is no generic module-role context accessor. Per-device context and native handles are passed directly through the exact DeviceBackendBinding; module-role APIs expose only lifetime and quiescence operations.

The role generation and binding generation are separate, non-reusable identities. A binding retains its role. Operation tokens carry both identities as needed to reject stale callbacks. Module-role shutdown closes admission and drains every binding owned by that role; binding removal affects only one PhysicalDevice. ScreenAttachment teardown remains independent.

## Lifetime requirements

- The DDX binding retains its native handle and device context until all logical Devices, backend objects, synchronous calls, accepted operation tokens, and callbacks that can access them have retired.
- The module role retains its loader lease until all bindings, callbacks, shared contexts, and module-owned workers have quiesced.
- A completion callback identifies a server-owned operation token by token ID and generation, plus the exact binding/module-role generations. It never resolves a raw module-role or binding pointer or client XID.
- A terminal callback does not prove backend quiescence. If later backend access cannot be excluded, retain or quarantine the binding and module lease.
- A Screen close detaches only that Screen generation. It does not unregister a shared DDX device binding.

The API sketch is implementation guidance, not a C ABI. Exact symbol names may be adapted, but these ownership and lifetime semantics are mandatory.
