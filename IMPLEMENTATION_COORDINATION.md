# XAverius Implementation Coordination

**Purpose:** Live hand-off for parallel implementation work. This file contains current decisions, interfaces to coordinate, open questions, and verification state. Historical discussion is preserved in [the coordination history archive](audit/implementation-coordination-history-2026-11-04.md).

## Authoritative baseline

- Specification repository: `metux/xav-design`.
- Authoritative branch: `docs/restructure-2026-10-21`. Do not use `master`, `wip/001`, or an implementation branch as the specification source.
- The current branch tip is authoritative; agents MUST sync from it before implementation or rebasing.
- This repository is in specification/architecture work. Do not add Xorg/Xlibre backend implementation here unless explicitly requested.
- Wire assignments are fixed: QueryVersion = 0, Compute-Baseline = 1–40, Presentation-Profile = 41–47. The registry is append-only.

## Current verified baseline

- Exact branch tip: `bc8d2ef3cc2143f3306349bc531d88724fc0991a`.
- Exact-tip CI: [workflow 41828369007](https://github.com/metux/xav-design/actions/runs/41828369007) — SUCCESS.
- Verified: wire/layout and header/client checks, request/reply/XGE validation, 72 Timeline regressions, and full Python suite (693 tests).
- This verification applies only to the exact commit above. Any later change requires a new exact-tip CI result.

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

1. **Inventory/driver registration:** implementation feedback is needed on how DDX/Screen observations, Vulkan discovery providers, canonical identity matching, and provider execution registration are wired together. Do not let a Screen choose or publish the PhysicalDevice or selected provider.
2. **Shared interfaces:** before parallel agents edit shared dispatch, resource lookup, registry, provider, or header code, record one integration owner and the agreed interface here.
3. **Request ownership:** maintain exactly one handler owner per request. Shared helpers have a separately named owner; request ownership does not imply shared-file ownership.
4. **Lifecycle integration:** report any implementation assumption that conflicts with provider pinning, generation checks, accepted-operation terminalization, or quarantine rules.
5. **Verification:** every implementation/spec change report must include branch, commit SHA, exact test commands or CI run, result, and remaining unverified runtime behavior.

## Latest specification update — Physical-device registration

The registry architecture now separates discovery-source observations, provider-local execution bindings, ScreenAttachments, and XAverius publication. DDX/Screen drivers report topology; only components implementing the complete backend contract register as BackendProviders. Provider registration order and Screen initialization order do not select the execution provider. The startup discovery barrier and the equivalent per-device hotplug publication path are specified in `spec/device-registry-architecture.md`.

The registry architecture changes were validated by [wire-layout workflow 41830568502](https://github.com/metux/xav-design/actions/runs/41830568502), SUCCESS on specification commit `783766cb28a8e9a32522013c8e6174c35c9016bf`: 4,873 wire-layout checks, 72 Timeline tests, and 693 Python tests passed; header/client builds and required CI gates also passed. The subsequent board-only coordination note does not alter specification or test inputs. Runtime Xorg/Vulkan integration remains untested.

## Agent update format

Post concise updates under this heading using:

- **Agent / branch / commit:**
- **Files or request groups:**
- **Interfaces or assumptions needing coordination:**
- **Tests and result:**
- **Open blockers:**

Do not copy historical audit narratives into this live file. Put durable design decisions in the relevant specification chapter and historical review detail in `audit/`.
