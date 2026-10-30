# XAverius Protocol Specification

**Version:** 0.1 — specification candidate  
**Status:** Final cross-document freeze review; normative request contracts and registries are defined  
**Transport:** X11 extension  
**Backend:** Vulkan  
**Initial implementation target:** Xvfb, compute-only  
**Specification language:** English; legacy German passages are retained where their normative meaning is unambiguous.

---

## 0. Status and normative language

This specification defines the XAverius v0.1 protocol candidate. The chapters under `spec/` and central registries under `registries/` are authoritative; historical material under `wip/` is non-normative. The compute-baseline profile is the initial implementation target. The separately defined presentation-capable profile is optional and MUST NOT be inferred from compute-baseline support.

The keywords **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** express normative requirements when used in their defined normative sense.

Normative protocol requirements are expressed using the keywords defined above. A rule described as profile-gated applies only when that profile is advertised; it is not provisional merely because the profile is optional. Runtime interoperability and backend conformance are implementation-acceptance matters and are tracked separately in `spec/open-issues.md` and `spec/freeze-checklist.md`. Numeric values not assigned in the central registries remain unassigned and MUST NOT be selected independently by an implementation.

This specification does not replace either the X11 specification or the Vulkan specification. XAverius defines the network-facing API and its additional guarantees.

## 1. Goals and architecture

XAverius is an X11 extension that exposes Vulkan operations through the X11 protocol. Vulkan objects and handles remain on the server. Clients address resources using XIDs.

The first implementation targets Xvfb and compute workloads. General graphics rendering is outside v0.1; a separately specified presentation-capable profile defines a limited buffer-to-swapchain-image path and is not a prerequisite for the first working implementation.

### 1.1 Core principles

1. Vulkan handles MUST NOT be transmitted over the network as raw handles.
2. Pointers, `size_t`, native C structures, and compiler-dependent padding are forbidden on the wire.
3. Every wire field has an explicit width and position.
4. Each logical device owns its own resources.
5. Resources belonging to different logical devices MUST NOT be mixed.
6. All conditions that can be checked synchronously MUST be validated before a request is accepted.
7. Rejected requests MUST NOT leave partial state changes.
8. Accepted asynchronous GPU work may fail later; such failures are reported through XAverius events and synchronization states.
9. Public XID validity and the lifetime of internal Vulkan objects are separate.
10. Device selection is explicit or performed by a defined server-side selection function.

### 1.2 Request families

The proposed family organization is:

| Family | Contents |
|---:|---|
| 0 | Protocol and version |
| 1 | Devices and queues |
| 2 | Memory |
| 3 | Buffers and images |
| 4 | Shaders and pipelines |
| 5 | Commands |
| 6 | Synchronization |
| 7 | Submission and presentation |
| 8 | Queries and optional features |

These family numbers are an organizational structure, **not assigned subopcodes**.

See the [Specification Language and Layout Style Guide](style-guide.md) for the mandatory English-language and layout conventions.
