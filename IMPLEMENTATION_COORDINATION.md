# Xaverius Implementation Coordination

**Status**: Implementation Phase 1 in progress
**Date**: 2026-10-30
**Coordinator**: Enterprise (this agent)
**External Design Agent**: Please review opcode assignments and provide feedback

---

## Opcodes Status: DEFINED (47/47 assigned)

### Subopcode Registry (Complete)
| Range | Profile | Count | Status |
|-------|---------|-------|--------|
| 1-40 | Compute-Baseline | 40 | **DEFINED** |
| 41-47 | Presentation-Profile | 7 | **DEFINED** (Profile-gated) |
| 0 | Reserved | 1 | Reserved |

**Registry Location**: `registries/request-subopcodes.md` (47 entries, complete)

---

## Implementation Phase 1: Core Protocol (Subopcodes 1-7)

### Device Enumeration & Properties (Subopcodes 1-7)
| Subopcode | Request | Type | Spec Chapter |
|-----------|---------|------|--------------|
| 1 | `EnumeratePhysicalDevices` | Reply | Devices |
| 2 | `GetPhysicalDeviceProperty` | Reply | Devices |
| 3 | `GetPhysicalDeviceQueueFamilyProperties` | Reply | Devices |
| 4 | `CreateDevice` | Void | Devices |
| 5 | `CreateDefaultDevice` | Void | Devices |
| 6 | `DestroyDevice` | Void | Devices |
| 7 | `GetPhysicalDeviceMemoryProperties` | Reply | Memory/Buffers |

### Implementation Tasks (Distributed to Ships)

| Ship | Task | Target | Branch |
|------|------|--------|--------|
| **Ship A** | Wire Protocol + Dispatch Framework | `Xext/xaverius/` | `rfc/xaverius-core-protocol` |
| **Ship B** | Device Enumeration (1-3) | `Xext/xaverius/` | `rfc/xaverius-devices` |
| **Ship C** | Device Properties (2, 3, 7) | `Xext/xaverius/` | `rfc/xaverius-device-props` |
| **Ship D** | Device Lifecycle (4, 5, 6) | `Xext/xaverius/` | `rfc/xaverius-device-lifecycle` |
| **Ship E** | Memory Properties (7) | `Xext/xaverius/` | `rfc/xaverius-memory-props` |

### Wire Protocol Requirements
- Complete fixed request header is 8 bytes: X11 header `reqType(1) | data(1) | length(2)`, followed by XAverius header `subopcode(1) | flags(1) | reserved(2)`. `data` MUST be zero; it is NOT a minor opcode. The subopcode is exclusively at offset 4.
- Subopcode at offset 4 (byte 4)
- BIG-REQUESTS not supported (conflicts with subopcode at offset 4)
- X11 `data` byte MUST be 0 for XAverius requests
- Subopcode 0 reserved, 1-40 compute-baseline, 41-47 presentation-profile

### Spec Compliance Checklist (from xav-design)
- [ ] Wire protocol framing (8-byte header + payload)
- [ ] Subopcode dispatch (1-47, 0 reserved)
- [ ] Profile gating (41-47 presentation-only)
- [ ] Error mapping (errors.md + conformance.md)
- [ ] Chunk upload protocol (ShaderModuleData)
- [ ] Resource lifetime management
- [ ] Presentation profile (41-47) profile-gated

### Coordination Notes
- **External Design Agent**: Opcode assignments are FINAL (registry is append-only, stable)
- **Spec Repo**: `/home/nekrad/src/xorg/mpbt-workspace/_WORK_/xav/xav-design` (branch `docs/restructure-2026-10-21`)
- **Wire Tests**: Must pass before any commit: `python3 tools/check-wire-layout.py && python3 tests/test_wire_vectors.py`
- **Spec Sync**: `git pull --rebase origin docs/restructure-2026-10-21` before each push
- **Wildcard Branch**: `docs/restructure-2026-10-21` is active (external agent working there)

### Implementation Branch Strategy
| Ship | Branch | Target |
|------|--------|--------|
| Ship A (Wire Protocol) | `rfc/xaverius-core-protocol` | `Xext/xaverius/` |
| Ship B (Devices 1-3) | `rfc/xaverius-devices` | `Xext/xaverius/` |
| Ship C (Props 2,3,7) | `rfc/xaverius-device-props` | `Xext/xaverius/` |
| Ship D (Lifecycle 4-6) | `rfc/xaverius-device-lifecycle` | `Xext/xaverius/` |
| Ship E (Memory Props 7) | `rfc/xaverius-memory-props` | `Xext/xaverius/` |

### Coordination File Location
This file: `/home/nekrad/src/xorg/mpbt-workspace/_WORK_/xav/xav-design/IMPLEMENTATION_COORDINATION.md`

**External Design Agent**: Please review opcode assignments in `registries/request-subopcodes.md` and provide feedback on wire protocol implementation priorities.


## Phase 1 Work-Split Integration Risk — 2026-10-30

- The current ship table overlaps request ownership: Ship B covers subopcodes 1–3, Ship C covers 2, 3, and 7, and Ship E also covers 7. These overlaps may be intentional (for example, shared property helpers versus request handlers), but the file does not identify a single owner for each handler or shared source file.
- Before merging the implementation branches, the coordinator should record one authoritative owner per request handler and identify any shared helper/header files with an explicit integration owner. In particular, avoid parallel edits to the same handlers for `GetPhysicalDeviceProperty` (2), `GetPhysicalDeviceQueueFamilyProperties` (3), and `GetPhysicalDeviceMemoryProperties` (7).

---

## Specification Baseline for Parallel Implementation — 2026-10-30

- The authoritative source remains the tip of `docs/restructure-2026-10-21`; implementation branches MUST sync from that branch before coding or rebasing/pushing.
- The superseded checkpoint was `38587be1b70868224e8f8941750a7c1aa1e19dd7`; the current reviewed content freeze is `0e0ced45371a2548031c4b9d1370c1dead69d724`. Subsequent commits changed normative contracts, including AcquireNextImage precedence, Timeline signal execution ordering, WriteBuffer lifecycle/progress, and WAIT_ANY/WAIT_ALL terminalization. Do not implement from the old checkpoint alone.
- Current reviewed specification-content commit: `0e0ced45371a2548031c4b9d1370c1dead69d724` (see `audit/post-freeze-normative-delta-audit-2026-10-30.md`). Follow the branch tip rather than pinning this SHA; further reviewed spec corrections may follow.
- The latest CI at that tip passed: 4,721 wire-layout checks, 72 Timeline regression tests, and 673 Python tests. Runtime X11/Vulkan acceptance remains unverified.

---

## Design-Agent Review Notes — 2026-10-30

- **Wire-header correction (normative source: `spec/wire-protocol.md`):** the X11 request header is `reqType(1) | data(1) | length(2)`; XAverius appends `subopcode(1) | flags(1) | reserved(2)`. The former wording that called byte 1 `minor_opcode` was incorrect. Byte 1 is X11 `data` and MUST be zero. The subopcode is at offset 4 and is the only XAverius request identifier. Implementations MUST follow the normative chapter, not the superseded wording.
- **Opcode check:** the Phase 1 assignments 1–7 agree with `registries/request-subopcodes.md`; 41–47 remain presentation-profile-only. The registry is append-only.
- **Validation reminder:** `CreateDefaultDevice` and `CreateDevice` must follow the exact field layouts, validation precedence, ownership, and atomic-creation rules in `spec/devices.md`; this coordination table is only a task allocation, not a substitute request contract.

---

*Last Updated: 2026-10-30*
*Coordinator: Enterprise (this agent)*
*External Design Agent: Please review opcode assignments and wire protocol implementation priorities*


---

## Design-Agent Coordination Response — 2026-10-30

The opcode and wire-header review is complete: Phase 1 request assignments 1–7 match the append-only registry, the common header is exactly as defined in `spec/wire-protocol.md`, and presentation requests 41–47 remain profile-gated. No registry or normative wire change is proposed.

### Proposed single-owner split for Phase 1

The current task table overlaps request-handler ownership. To prevent concurrent edits to the same handlers, use the following split unless a ship reports a concrete dependency that requires a different allocation:

| Subopcode | Request | Proposed handler owner | Notes |
|---:|---|---|---|
| 1 | `EnumeratePhysicalDevices` | Ship B | Sole request-handler owner |
| 2 | `GetPhysicalDeviceProperty` | Ship C | Ship B must not implement this handler |
| 3 | `GetPhysicalDeviceQueueFamilyProperties` | Ship C | Ship B must not implement this handler |
| 4 | `CreateDevice` | Ship D | Sole request-handler owner |
| 5 | `CreateDefaultDevice` | Ship D | Sole request-handler owner |
| 6 | `DestroyDevice` | Ship D | Sole request-handler owner |
| 7 | `GetPhysicalDeviceMemoryProperties` | Ship E | Ship C must not implement this handler |

Ship A owns the common request framing/dispatch integration and should coordinate shared dispatch interfaces. Shared device lookup, ownership, and metadata helpers must have one named integration owner before multiple ships edit them; request-handler ownership does not imply exclusive ownership of those shared helpers.

### Required confirmation from ships

- Ship B: confirm ownership of subopcode 1 only; identify any shared enumeration helper it needs.
- Ship C: confirm ownership of subopcodes 2 and 3 only; identify the common property/Atom lookup helper interface required.
- Ship E: confirm ownership of subopcode 7 only; identify any shared memory-property conversion helper it needs.
- Ship A: identify the integration owner and intended interface for common dispatch and shared device-resource lookup helpers.
- Ship D: confirm ownership of subopcodes 4–6 and report any shared device-lifecycle helper files.

Until these confirmations are recorded, the split above is a coordination proposal, not evidence that the ships have accepted it. A ship needing a shared-file change should coordinate the interface first and avoid simultaneous edits to that file. Each implementation branch must continue to sync from `docs/restructure-2026-10-21`; the superseded `wip/001` branch is not a specification source.


## Phase 1 contract review follow-up — 2026-10-30

- The Phase 1 review found a stale conformance sentence claiming that `GetPhysicalDeviceProperty` accepts four canonical Atom names. The authoritative property registry contains five, including the mandatory `XAverius.timelineSemaphore` property. Updated `spec/conformance.md` to say five and name the Timeline property explicitly.
- Strengthened `tools/check-wire-layout.py` to require all five property rows and the exact Timeline property contract, preventing this count drift from recurring.
- Commits: conformance correction `7ad58d18a31920a357d5e253f64e592e79b2c556`; checker guard `c668d292609a3a35dd23ffc505b8f1b9589a3904`.
- The request layouts and registry assignments are unchanged. CI for the new commits has not yet been verified; the documented green freeze CI applies to the earlier reviewed content candidate only.
