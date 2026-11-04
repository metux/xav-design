# XAverius Implementation Coordination

**Purpose:** Live hand-off for parallel implementation work. This file contains current decisions, interfaces to coordinate, open questions, and verification state. Historical discussion is preserved in [the coordination history archive](IMPLEMENTATION_COORDINATION_HISTORY_2026-11-04.md).

## Authoritative baseline

- Specification repository: `metux/xav-design`.
- Authoritative branch: `docs/restructure-2026-10-21`. Do not use `master`, `wip/001`, or an implementation branch as the specification source.
- The current branch tip is authoritative; agents MUST sync from it before implementation or rebasing.
- This repository is in specification/architecture work. Do not add Xorg/Xlibre backend implementation here unless explicitly requested.
- Wire assignments are fixed: QueryVersion = 0, Compute-Baseline = 1–40, Presentation-Profile = 41–47. The registry is append-only.

## Current verified baseline

- Latest exact-tip verified specification commit: `f6ae4c056b3621d8b491dc64aad4d361baf2c0c2`.
- Exact-tip CI: [workflow 41832770751](https://github.com/metux/xav-design/actions/runs/41832770751) — SUCCESS.
- Verified: 4,886 wire-layout checks, 72 Timeline regressions, 693 Python tests, shared-header compilation, XCB client prototype build, request/reply/XGE validation, backend-discovery/handler/callback audits, and required-check audit. All 18 workflow steps completed successfully.
- Current unverified candidate: `013be364ea8cc7126b092f46d7c266b43dcda02f`; render/scanout routing, PRIME/DRI3 bridge contract, and route-generation lifecycle added. Exact-tip CI is pending; do not treat the earlier green run as evidence for this candidate.

## Architecture contracts implementation must follow

### Physical-device inventory

- One process-wide registry owns canonical PhysicalDevice identities and server-owned Physical-Device XIDs.
- A PhysicalDevice is not a Screen, DDX instance, DRM node, Vulkan handle, provider, or Vulkan device group.
- Identity is canonicalized across Xorg/DRM, udev, Vulkan-loader, and other discovery paths before publication. Primary and render nodes for one DRM device resolve to one identity; remove/re-add creates a new incarnation and XID.
- Each published v0.1 PhysicalDevice has exactly one selected execution provider and one immutable metadata snapshot from that provider. No cross-provider capability union or transparent failover.
- ScreenAttachment is a non-owning, generation-checked relation. A Screen may attach to multiple GPUs and a GPU may attach to multiple Screens. Attachment does not establish presentation support; the exact Device/Surface query does.
- Status is AVAILABLE, UNAVAILABLE, or terminal REMOVED. Provider failure is not hardware removal or logical Device Loss. REMOVED entries remain tombstones until server shutdown.

### Provider boundary and lifetime

- The server owns request validation, XID/resource ownership, request ordering, public state transitions, error mapping, and event delivery.
- A provider owns its private Vulkan/backend handles and executes only validated operations supplied through the provider interface.
- Provider selection is deterministic and completed before publication. The selected provider and published snapshot do not change during the PhysicalDevice XID lifetime.
- Provider results are classified. UNAVAILABLE carries explicit PROVIDER_CONTEXT or PHYSICAL_DEVICE scope. Only positive loss for an exact logical Device establishes DEVICE_LOST.
- Accepted asynchronous operations carry non-reusable provider/operation/device/resource generations. Completion callbacks only enqueue immutable records; the server serializes state changes.
- A terminal callback is not proof of quiescence. Only successful exact-token retirement proves no further backend access and permits releasing retained references. Otherwise quarantine; never unload reachable provider code.
- WaitSemaphores and WaitForFence are server-owned registrations, not provider operations and have no provider tokens.

Normative and detailed contracts: `spec/devices.md`, `spec/device-registry-architecture.md`, `spec/resource-lifetime.md`, `spec/presentation.md`, and `spec/synchronization.md`.

## Active coordination items

1. **Inventory/driver registration:** identity matching now defines evidence precedence and conflict outcomes, including DRM node equivalence, Vulkan UUID corroboration, derived-device instance identity, and provider-scoped fallback. Implementation feedback is still needed on which Xlibre/Xorg discovery interfaces can supply authoritative evidence for each device class. Do not let a Screen choose or publish the PhysicalDevice or selected provider.
2. **Shared interfaces:** before parallel agents edit shared dispatch, resource lookup, registry, provider, or header code, record one integration owner and the agreed interface here.
3. **Request ownership:** maintain exactly one handler owner per request. Shared helpers have a separately named owner; request ownership does not imply shared-file ownership.
4. **Lifecycle integration:** report any implementation assumption that conflicts with provider pinning, generation checks, accepted-operation terminalization, or quarantine rules.
5. **Verification:** every implementation/spec change report must include branch, commit SHA, exact test commands or CI run, result, and remaining unverified runtime behavior.

## Latest specification update — Physical-device registration

The registry architecture now separates discovery-source observations, provider-local execution bindings, ScreenAttachments, and XAverius publication. DDX/Screen drivers report topology; only components implementing the complete backend contract register as BackendProviders. Provider registration order and Screen initialization order do not select the execution provider. The startup discovery barrier and the equivalent per-device hotplug publication path are specified in `spec/device-registry-architecture.md`.

The current specification baseline `7f2620726f88bbd28ff6ac5c21a27d87659301e7` passed [exact-tip wire-layout workflow 41830758364](https://github.com/metux/xav-design/actions/runs/41830758364): 4,873 wire-layout checks, 72 Timeline tests, 693 Python tests, header/client builds, and required CI gates all passed. Subsequent status/checklist/open-issues edits are documentation-only; a fresh CI run is tracking those documentation changes. Runtime Xorg/Vulkan integration remains untested.

## Latest specification update — identity evidence and provider selection

The registry architecture now defines an evidence hierarchy and explicit conflict outcomes for platform identity, DRM primary/render-node equivalence, Vulkan `deviceUUID` correlation, derived devices (mediated/SR-IOV/partitioned/MIG), and provider-scoped software/virtual identities. Ambiguous or contradictory candidates remain unpublished; published identities are never merged or rebound. Provider selection now rejects duplicate stable keys and ambiguous preference identifiers, and evaluates identity/snapshot eligibility before ranking. Architecture vectors 36–44 cover these cases. The normative device chapter links to the architecture contract. Exact-tip candidate `f6ae4c056b3621d8b491dc64aad4d361baf2c0c2` passed [workflow 41832770751](https://github.com/metux/xav-design/actions/runs/41832770751): 4,886 wire-layout checks, 72 Timeline regressions, 693 Python tests, header/client builds, request/reply/XGE validation, and all required gates.

## Latest specification update — render GPU versus scanout GPU

The presentation contract now separates the logical Device's render PhysicalDevice from the Surface's owning Screen and scanout PhysicalDevice. ScreenAttachment roles are topology only. The selected execution provider coordinates the exact Device/Surface route, either direct WSI or an explicit PRIME/DRI3 import/copy/composition bridge with complete format/modifier, usage, synchronization, ownership-transfer, and release/completion guarantees. No implicit migration to another PhysicalDevice, provider, Screen, or RandR output is permitted. A successful Swapchain pins one route generation; route changes invalidate it as OUT_OF_DATE. Temporary route unavailability and accepted route failure have explicit status mappings. Architecture vectors 48–54 cover split render/scanout GPUs, missing bridge support, route changes, and independent failure domains. Candidate `013be364ea8cc7126b092f46d7c266b43dcda02f` is pending exact-tip CI.

## Agent update format

Post concise updates under this heading using:

- **Agent / branch / commit:**
- **Files or request groups:**
- **Interfaces or assumptions needing coordination:**
- **Tests and result:**
- **Open blockers:**

Do not copy historical audit narratives into this live file. Put durable design decisions in the relevant specification chapter and historical review detail in `audit/`.
