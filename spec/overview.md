# XAverius Protocol Specification

**Version:** 0.1 — consolidated working draft  
**Status:** Design draft; the wire protocol and registries are not yet fully frozen  
**Transport:** X11 extension  
**Backend:** Vulkan  
**Initial implementation target:** Xvfb, compute-only  
**Specification language:** English for all normative and explanatory text.

---

## 0. Status and normative language

This specification consolidates the XAverius design decisions made so far.

The keywords **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** express normative requirements when used in their defined normative sense.

There are three status classes:

- **Decided:** Approved as a design decision.
- **Provisional rule:** A proposed rule that still requires validation against the complete Vulkan and X11 semantics.
- **Open:** A decision that must be made before a stable wire-protocol release.

An open numeric registry value MUST NOT be assigned independently by an implementation if that could conflict with a value assigned centrally later.

This specification does not replace either the X11 specification or the Vulkan specification. XAverius defines the network-facing API and its additional guarantees.

## 1. Goals and architecture

XAverius is an X11 extension that exposes Vulkan operations through the X11 protocol. Vulkan objects and handles remain on the server. Clients address resources using XIDs.

The first implementation targets Xvfb and compute workloads. Graphics and presentation remain part of the long-term architecture but are not prerequisites for the first working implementation.

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
