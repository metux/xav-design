# Xaverius Implementation Coordination

**Status**: Normative specification freeze-ready; Implementation Phase 1 in progress; 48 request contracts assigned
**Date**: 2026-11-02
**Coordinator**: Enterprise (this agent)
**External Design Agent**: Please review opcode assignments and provide feedback

---

## Opcodes Status: DEFINED (48/48 assigned)

### Subopcode Registry (Complete)
| Range | Profile | Count | Status |
|-------|---------|-------|--------|
| 1-40 | Compute-Baseline | 40 | **DEFINED** |
| 41-47 | Presentation-Profile | 7 | **DEFINED** (Profile-gated) |
| 0 | QueryVersion | 1 | **DEFINED** (Common bootstrap) |

**Registry Location**: `registries/request-subopcodes.md` (48 entries, complete)

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
| **Ship A** | Common wire framing and dispatch integration; coordinate shared interfaces, no ownership of device request handlers | `Xext/xaverius/` | `rfc/xaverius-core-protocol` |
| **Ship B** | `EnumeratePhysicalDevices` (subopcode 1) only | `Xext/xaverius/` | `rfc/xaverius-devices` |
| **Ship C** | `GetPhysicalDeviceProperty` (2) and `GetPhysicalDeviceQueueFamilyProperties` (3) only | `Xext/xaverius/` | `rfc/xaverius-device-props` |
| **Ship D** | Device Lifecycle (4, 5, 6) | `Xext/xaverius/` | `rfc/xaverius-device-lifecycle` |
| **Ship E** | `GetPhysicalDeviceMemoryProperties` (subopcode 7) only | `Xext/xaverius/` | `rfc/xaverius-memory-props` |

This is the canonical single-owner request-handler split. The earlier table that assigned requests 2/3 to both B and C and request 7 to both C and E is superseded. Shared helper/header ownership remains separate and must be named by Ship A before overlapping shared-file edits.

### Shared integration ownership (must be confirmed before shared-file edits)

The request-handler split above is the coordination baseline. It does not assign ownership of shared helpers. Ship A must name the integration owner and publish/agree the interfaces for common dispatch, Physical-Device XID lookup, client ownership checks, and shared device metadata before ships make overlapping changes. Until that owner/interface is recorded, ships MUST NOT independently modify the same shared helper or header; submit the required interface in this file first.

### Wire Protocol Requirements
- Complete fixed request header is 8 bytes: X11 header `reqType(1) | data(1) | length(2)`, followed by XAverius header `subopcode(1) | flags(1) | reserved(2)`. `data` MUST be zero; it is NOT a minor opcode. The subopcode is exclusively at offset 4.
- Subopcode at offset 4 (byte 4)
- BIG-REQUESTS not supported (conflicts with subopcode at offset 4)
- X11 `data` byte MUST be 0 for XAverius requests
- Subopcode 0 QueryVersion (common bootstrap), 1-40 compute-baseline, 41-47 presentation-profile

### Spec Compliance Checklist (from xav-design)
- [x] Wire protocol framing (8-byte header + payload)
- [x] Subopcode dispatch (0-47; QueryVersion is bootstrap request)
- [x] Profile gating (41-47 presentation-only)
- [x] Error mapping (errors.md + conformance.md)
- [x] Chunk upload protocol (ShaderModuleData)
- [x] Resource lifetime management
- [x] Presentation profile (41-47) profile-gated

All seven items are specification-completeness checks, not implementation ship confirmations. Evidence: `spec/freeze-checklist.md`; verified content candidate `0b9c40e0907592f7f96687912d948abf221123d0` passed exact-tip CI run [41476931362](https://github.com/metux/xav-design/actions/runs/41476931362) (4,836 wire-layout checks, 72 Timeline regressions, 692 Python tests). The later status/board metadata tip `dccb0e838e0f2880e3d50865c7c038e7bc0424b7` also passed exact-tip wire-layout CI [41478640475](https://github.com/metux/xav-design/actions/runs/41478640475) and branch-tip monitor [41478640287](https://github.com/metux/xav-design/actions/runs/41478640287).

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

*Last Updated: 2026-11-02*
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


## Design-Agent Blackboard Update — 2026-10-30 (follow-up)

The Phase 1 task table above now reflects the single-handler-owner split recorded below; the earlier overlapping assignment is superseded. Ship A is responsible for publishing the shared dispatch/device-lookup interfaces and naming one integration owner for shared helpers. Ship B/C/D/E should confirm their handler scope and list shared-file dependencies here before parallel edits. No ship acceptance has yet been observed in this file.

The recent conformance/checker commits have no reported GitHub status checks on their commit SHAs (the status API returned an empty status list); do not treat the earlier freeze CI result as validation of these later commits. Please run the documented wire checker and wire-vector tests on the current branch tip and post the exact command, commit SHA, and result here.


## Phase 1 normative cross-check — 2026-10-30

A second pass compared the Phase 1 contracts (requests 1–7) against the property registry, memory-property contract, error mapping, conformance vectors, and wire-layout checker.

- Requests 1–3: framing, record/reply lengths, Atom lookup order, immutable physical-device snapshots, and removal behavior agree across the normative chapters and conformance sections.
- Requests 4–6: CreateDevice's ten validation phases, CreateDefaultDevice's five phases, XGE prerequisite, atomic publication, and DestroyDevice's loss-independent teardown agree with the conformance vectors.
- Request 7: 12-byte request, reply-size formula, 32/16 count limits, reserved/flag checks, heap-index constraints, and stable snapshot behavior agree with the checker and conformance requirements.
- The five-property registry correction is consistent with the mandatory Timeline baseline and the existing property type table. No further Phase 1 normative mismatch was identified in this pass; no additional wire-contract change is proposed.
- Verification limitation: GitHub reports no status checks for the recent direct branch commits. The checker source now contains the five-property assertion, but this agent has not executed the repository test suite in this environment. Please report actual current-tip test results here rather than treating static review as CI.


## Phase 2 normative audit — Buffer and Memory requests 8–14 — 2026-10-31

Reviewed subopcodes 8–14 (`CreateBuffer`, `GetBufferMemoryRequirements`, `AllocateMemory`, `FreeMemory`, `BindBufferMemory`, `WriteBuffer`, `ReadBuffer`) against the normative memory chapter, central error mapping, resource lifetime, device teardown, conformance matrix, request registry, and static wire-layout checker.

### Finding corrected: ReadBuffer did not serialize later WriteBuffer requests

The previous snapshot rule held the read data stable before later `QueueSubmit` writes, but did not include a later direct `WriteBuffer` request. A later upload could therefore modify the requested range before the earlier ReadBuffer had captured its snapshot. This was a real request-ordering ambiguity.

The normative rule now places both later `QueueSubmit` and later `WriteBuffer` operations behind the ReadBuffer snapshot boundary. Deferred requests do not start work or reserve/commit accepted-operation state, and are processed in original request order after snapshot success or read failure. Host `SignalSemaphore` and independent `WaitSemaphores` remain available to make earlier work progress. The ReadBuffer operation now also has an explicit snapshot linearization point and first-terminal-outcome behavior against Device Loss, `DestroyDevice`, and disconnect; backend references are retained/quarantined until safe quiescence.

### Files and commits

- `spec/memory-buffers.md`: `c74756ac623ea6ca932c53fae3f90f9cda662be7`
- `spec/errors.md`: `8a3d7ff8298173405521a7bdfaa65c3f3bf63cab`
- `spec/devices.md`: `8f23e6b0b7c918b00c8342550e4f508a3c476765`
- `spec/resource-lifetime.md`: `bb8083812e9c3bca39b8d472a01e53b368755c80`
- `spec/conformance.md`: `cf6a800148303a1d20b517036b564ba5eff9a0cc`
- `tools/check-wire-layout.py`: `66f6fa30f85c09d1266b7b76f1c3b8ce27d63839`

### Other review results

The remaining request contracts in this group were cross-checked without finding another normative contradiction: CreateBuffer/AllocateMemory create-XID and Device-state precedence; stored buffer-requirement snapshots after Device Loss; memory-type index/mask and alignment/bounds checks; FreeMemory's internal Buffer-binding and backend-access blockers; and WriteBuffer's upload barrier, dependency-cycle handling, and lifecycle terminalization. Existing conformance entries cover their major validation and atomicity cases. No opcode or wire-layout changes were needed.

### Verification and open points

- Static source review only. The newly added checker assertions and repository tests have **not** been executed in this environment.
- Please run `python3 tools/check-wire-layout.py && python3 tests/test_wire_vectors.py` and the full Python test suite on the resulting branch tip; report exact SHA and results here.
- Runtime X11/XGE and Vulkan backend behavior remain unverified, including injected transfer/allocation failures and real backend quiescence.
- Phase 1 agent confirmations and shared integration-interface ownership remain outstanding unless a ship posts an update below.


## Phase 3 normative audit — Shader, Descriptor, and Pipeline requests 15–23 — 2026-10-31

Reviewed subopcodes 15–23 (`ShaderModuleData`, `CreateDescriptorSetLayout`, `CreateDescriptorPool`, `DestroyDescriptorPool`, `AllocateDescriptorSets`, `UpdateDescriptorSets`, `FreeDescriptorSets`, `CreatePipelineLayout`, `CreateComputePipeline`) against the shader/pipeline chapter, command recording, central error mapping, resource lifetime, request registry, conformance vectors, and static wire-layout checker.

### Findings corrected

- Descriptor Pool capacity semantics were not fully defined: the spec named `max_sets`, pool-size counts, and allocation capacity failures but did not normatively state how each layout consumes per-type capacity or when capacity is returned. Added exact accounting: each Set consumes its layout's per-type descriptor totals plus one set slot; repeated layouts count independently; batches reserve atomically; insufficient capacity is `ALLOCATION_FAILED`; successful free returns capacity in the public invalidation commit; rejection leaves all counters unchanged.
- `CreateDescriptorSetLayout` had ambiguous `BadValue`/`BadMatch` classification for device descriptor limits. A syntactically valid layout exceeding the selected Device's descriptor limits is now `BadMatch`, after Device availability; the v0.1 binding stage mask is exactly `COMPUTE`.
- `CreatePipelineLayout` did not enumerate push-constant range field rules precisely. It now requires COMPUTE stage, positive size, four-byte alignment, checked non-overflowing end, and no overlap (only COMPUTE exists in v0.1). Device-limit violations (`maxPushConstantsSize`, `maxBoundDescriptorSets`) are `BadMatch` after Device-state validation.
- `CMD_PUSH_CONSTANTS` coverage now explicitly requires the complete half-open data interval to fit within one declared COMPUTE range; adjacent ranges cannot be combined to cover a command.
- `CreateComputePipeline` now requires the selected name to identify a SPIR-V `GLCompute` entry point; absent/non-compute entry points are `BadMatch`.

### Commits

- `spec/shaders-pipelines.md`: `15910900a1a1fb25776f634d0f7f13afbd89bda3` (pool capacity); `7eb5b0a252f628c118acc653d1112d768e1554b0` (descriptor limits); `d94e0ce1ec5b30b1cd6e23f44cbc895bcb385f04` (push range syntax); `67c4fb1565dc498dfe92c16b345b909989d8be2b` (pipeline layout device limits); `cc8c692849be6cd9371adf8a99e9f7b6f5b3d713` (compute entry point).
- `spec/command-recording.md`: `8e9303a7c5a4b4dbd2bf05a5bfdcea48a9600f1b`.
- `spec/errors.md`: `ec7269d89dd4a660d5c66a0211f06210f1a3fc31`; `23b3b31a2ebd11c119e8c03d072bff9dc0466c4a`; `db9a9fe36e5a537d3b5203e2cead7c1971fe1993`.
- `spec/conformance.md`: `ab9e5d0485b4ef1dfc94e69887387e266a2850ee`.
- `tools/check-wire-layout.py`: `5271e257567e61e0d4150af69171f18f91433770`; `688efa98b9a6e125fb05642f1a27a33380fb99d2`; `36a9b859a4437bb8feffe8befae5032657b9ead1`.

### Conformance and verification

Added explicit vectors for shader chunk failure/cleanup, descriptor device limits and pool capacity accounting, batch allocation precedence/atomicity, UpdateDescriptorSets races against QueueSubmit and release, PipelineLayout range validation, CMD_PUSH_CONSTANTS single-range coverage, compute entry-point validation, and injected backend allocation failures.

Static cross-document checks were performed after the edits, including verifying the exact phrases used by the newly added checker assertions. The repository checker and Python test suite have **not** been executed in this environment; no green CI result is claimed. Please run `python3 tools/check-wire-layout.py && python3 tests/test_wire_vectors.py` and the full Python test suite on the branch tip, then post the exact SHA and results here. Runtime Vulkan backend tests are still required for descriptor pool exhaustion/reuse, shader validation, push constants, and pipeline creation.

### Coordination status

No new Phase 1 ship confirmations or shared integration-interface owner were present in this file at the time of this audit. The Phase 1 implementation split and interface confirmations remain open. Continue implementation against the tip of `docs/restructure-2026-10-21`; do not use `wip/001`.


### Phase 3 audit addendum — 2026-10-31

The final consistency pass also made the `CMD_PUSH_CONSTANTS` error mapping explicit: malformed stage/length/alignment/padding and arithmetic overflow are `BadValue`; a range not contained in one declared COMPUTE range or exceeding `maxPushConstantsSize` is `BadMatch`. The `CreateComputePipeline` scalar check now names `entry_point_length > 0` (there is no entry-point count field). Descriptor-limit text now names the Vulkan limits used for storage-buffer totals.

Additional commits:
- `spec/shaders-pipelines.md`: `579b00c810eb37d372437b6d74e27fb9c0c1012b`, `c00b9cd90aaced76762b01e02efb4e6dd9909c0b`.
- `spec/errors.md`: `43a238f18d0cdd6dc8942a02d2d37b5e57ed0bfd`.
- `spec/conformance.md`: `62e50fc8f9469d7fe7d92e603eb7447b9dd3de52`.
- `tools/check-wire-layout.py`: `a1e92971573aef0e5ab6ed9e4e0c3396d3635cf3`, `249562ee82a79e33e650db74b231670d89097f81`.

Post-edit static source checks confirm that the newly added checker assertions' expected strings are present in the normative and conformance files. This is not a test execution; no CI pass is claimed.

## Phase 4 normative audit — Command Pools, Command Buffers, QueueSubmit, and Semaphore query requests 24–30 — 2026-10-31

Reviewed subopcodes 24–30 (CreateCommandPool, DestroyCommandPool, ResetCommandBuffer, CommandBufferData, QueueSubmit, CreateSemaphore, GetSemaphoreCounterValue) against command recording, queue submission, synchronization, device queue-family properties/flags, lifetime, error mapping, conformance vectors, and the static wire-layout checker.

### Findings corrected

- Queue-family capability was not implementable as written. CreateCommandPool required a family that “supports command buffers”, but the XAverius queue-flag registry has only the Vulkan graphics/compute/transfer/sparse/protected bits and defines no command-buffer-support flag. The rule now requires a family configured for the logical Device with a positive requested queue count; no extra capability flag is invented. Command buffers inherit the pool's family identity.
- QueueSubmit lacked explicit command-buffer family matching. A command buffer created from a pool for one queue family could previously be interpreted as submit-eligible on any queue of the same logical Device. The normative phase-4 association check now requires every submitted command buffer's parent pool family to equal the addressed queue family; mismatch is BadMatch, before Device-state/mutable checks and without consuming the token or reserving state.
- Command-entry capability is distinct from pool validity. CMD_DISPATCH requires the pool family to include the COMPUTE queue flag. A family without COMPUTE may still own command buffers for entries it supports (and synchronization-only submissions), but recording CMD_DISPATCH there is BadMatch in resource-dependent CommandBufferData validation. Added error mapping and vectors, including Device Loss precedence.
- DestroyCommandPool precedence is now explicit: exact length, Device then Pool XID in wire order, live type/ownership/device association, then all-child pending blockers; success invalidates the pool and child XIDs atomically.
- Semaphore requests: CreateSemaphore type and type-dependent initial-value syntax remains before target-XID collision; added mixed-failure vectors for unknown type and nonzero Binary initial value against an occupied target, plus backend-allocation rollback. GetSemaphoreCounterValue remains a Device-loss X11-error query with no status reply; added counter-publication/query linearization and delayed-reply race vectors.

### Files and commits

- spec/command-recording.md: c3bb654f3c20dfc19a25c1d695cd96586f5062b9
- spec/queue-submission.md: 82185b66ecf68c39e2eac0b81554b9148c3cec77
- spec/errors.md: 61caf95d1674ee88dfd84265fb1e136ddc8430ad, 4382ac6c8206f69146cdf5df0e4edd5750d94c0f
- spec/conformance.md: b084eae3c057bd77a54200954e4e021d3b4ffa82, 5f9602fbd85cfa5a3e660a535c22a73d2077c9b6, 0aacd422919a06e279036922146a990c19a67790
- tools/check-wire-layout.py: 37bb22fd60341471d730d6d2d7a1945e16be737d, fa8a68a8660969ad2212d2fda431d02a4daf174a

### Other review results

- CommandBufferData CREATE/append/FINAL/ABORT atomicity, chunk boundaries, entry-length limits, XID order, device-loss handling, and recorded-reference epochs agree with the command-buffer lifecycle rules.
- QueueSubmit token uniqueness/acceptance commit, resource XID order, device-loss precedence, mutable Fence/Buffer/Semaphore order, reservation rollback, callback terminalization, and serialization against destroy/release remain consistent.
- CreateSemaphore has the exact 28-byte layout and ordered type/initial-value → target XID → Device → ownership → Device state → backend-allocation phases.
- GetSemaphoreCounterValue has the exact 16-byte request and 32-byte reply, zero reserved bytes, Device → Semaphore XID order, ownership before Device Loss, and Device Loss before the Timeline-only type check.

### Verification and remaining open points

- GitHub status and workflow-run queries for the latest audit commit returned empty collections. This is not evidence of a green CI run.
- The repository checker, wire vectors, and Python suite have not been executed in this environment. Run python3 tools/check-wire-layout.py && python3 tests/test_wire_vectors.py and the full Python test suite on the current branch tip; report exact SHA and output.
- Runtime Vulkan/X11 validation remains outstanding, especially command-pool family compatibility, dispatch on non-compute families, and semaphore allocation/counter behavior.
- Phase 1 ship confirmations and a named shared integration-interface owner remain outstanding in this coordination file. No implementation branch should infer ownership or modify shared dispatch/device headers until that is recorded.
- Next spec-only audit: subopcodes 31–40 (host semaphore operations, fences, generic destruction, and event selection), then a final cross-request freeze pass.

### Phase 4 checker follow-up — 2026-10-31

- Extended the static wire-layout checker to guard queue-family identity, CMD_DISPATCH's COMPUTE-family requirement, CreateSemaphore scalar-before-target precedence, and GetSemaphoreCounterValue snapshot/Device-loss semantics.
- Additional checker commits: 9d2d5248c5c3e8965a15c6e675a62da3ff4067d5; ac0599ce173e6dd865faf7d834d67f1d54588361.
- GitHub status and workflow-run queries for ac0599ce173e6dd865faf7d834d67f1d54588361 returned empty collections. The checker has still not been executed locally or in CI; no passing result is claimed.
## Phase 5 normative audit — Host synchronization, fences, generic destruction, and event selection requests 31–40 — 2026-10-31

Reviewed subopcodes 31–40 (WaitSemaphores, SignalSemaphore, DestroySemaphore, CreateFence, GetFenceStatus, WaitForFence, ResetFence, DestroyFence, DestroyResource, SelectEvents) against synchronization, queue submission, events, resource lifetime, error mapping, event/request registries, conformance vectors, and the XGE/wire-layout checker.

### Finding corrected

- DestroySemaphore previously described its length, XID/type errors, and lifetime blockers, but did not itself state the exact validation phase order as explicitly as DestroyFence. The normative request text and error map now require exact length → Device XID → Semaphore XID → live type/ownership/Device association → exact-identity lifetime blockers. Device Loss alone does not block logical destruction, but does not override an active blocker. Added mixed-failure vectors for Device-versus-Semaphore XID order, Device Loss, active host operations, and already-terminal waits whose replies are still queued.

### Cross-document review results

- WaitSemaphores WAIT_ANY/WAIT_ALL predicates, coherent snapshots, lost-wakeup prevention, timeout deadlines, first-terminal-outcome rules, disconnect cancellation, and WriteBuffer/host-signal dispatch interactions agree across synchronization, errors, conformance, and lifetime rules.
- SignalSemaphore host/GPU Timeline reservation ordering, value monotonicity, request-order execution, WriteBuffer exception, Device-loss handling, and ASYNC_ERROR origin/token rules remain consistent with QueueSubmit and event definitions.
- Fence creation, status query, wait, reset, and destruction agree on exact request/reply layouts, status namespaces, Device-loss behavior, use generations, callback identity, and the rule that a terminal wait no longer blocks destruction merely because its reply has not yet been sent.
- DestroyResource remains a single-XID request with explicit allowed types, dedicated synchronization destruction paths, type-specific recording/pending blockers, atomic public invalidation, and internal reference retention. No cross-chapter contradiction was found in the audited lifetime matrix.
- SelectEvents scope fields, scope-specific masks, presentation-profile gating, XGE negotiation, error precedence, atomic per-scope replacement, unmaskable ASYNC_ERROR/DEVICE_LOST delivery, and event-mask sampling at terminal linearization points agree with the event registry and conformance vectors.

### Files and commits

- spec/synchronization.md: f4f7be06f27a74a5012f15d810c02e39fd940d08
- spec/conformance.md: 089a6411e98f611b0b3539353ba1bbf0718fc5f3
- spec/errors.md: 4331ae845e0eec2e9ca30f197bd52f7d63403844
- tools/check-wire-layout.py: 76bcc721de50181817921514134516d8752f8022

### Verification and remaining open points

- GitHub status and workflow-run queries for 76bcc721de50181817921514134516d8752f8022 returned empty collections. This is not evidence of a passing CI run.
- The static checker, wire vectors, and Python suite have not been executed in this environment. Run python3 tools/check-wire-layout.py && python3 tests/test_wire_vectors.py and the full Python test suite on the current branch tip; report the exact SHA and output.
- Runtime validation remains outstanding for real host/GPU semaphore interaction, Fence reuse under delayed callbacks, event-mask/DestroyDevice/completion races, and live X11/XGE delivery.
- Phase 1 ship confirmations and a named shared integration-interface owner remain outstanding. No implementation ownership or shared-helper edits should be inferred from the spec audit.
- Next: final cross-request freeze review across subopcodes 1–40 and presentation-profile 41–47, including registry/error/conformance/checker drift and implementation-readiness checklist closure.
## Freeze metadata and registry-drift follow-up — 2026-10-31

The cross-request freeze pass found one stale historical count in spec/request-audit.md: it said the physical-device property registry had four properties although the current registry and conformance contract define five. Corrected to five.

Updated spec/freeze-checklist.md and spec/open-issues.md so commit 0e0ced45371a2548031c4b9d1370c1dead69d724 is described only as the historical exact-commit CI checkpoint. Phase 3–5 normative deltas are later commits and have no verified status checks/workflow runs; therefore the current branch is explicitly not re-frozen. The checklist now has a separate unchecked requirement to rerun the checker, wire vectors, full Python suite, and required-check presence audit on one exact current-tip candidate.

Registry drift spot-check: 47 request assignments remain 1–40 compute baseline and 41–47 presentation-profile-only; error offsets remain 0–8; compute event IDs remain 0–6 with presentation IDs 7–8; command-entry IDs remain 1–5 with entry 5 presentation-only; descriptor types remain 0/1; queue flags remain five defined bits; optional feature and extension registries remain intentionally empty; the physical-device property registry contains five properties. No numeric assignment changed.

Commits: request-audit property count de81269a5dee156cb17e6d1a11298e68f2b92ddc; freeze checklist 338a2d46265d0cffdadb9b0609748b69b604ab22 and 654138ef6b60dd71cb9e0af6ddc2d4c1bb025676; open issues 8a83d6f11f568e3c9ccc2cdb8c44b0a45be98407; request audit Phase 4–5 entries 38f29c9f882e7230a89aa50ab7330104978fa469.

Remaining before declaring the current branch frozen: finish the cross-request drift pass, get implementation-agent confirmations/shared interface owner onto this board, and run the full required CI/test set against the exact final tip. Runtime X11/XGE and Vulkan backend acceptance remains a separate implementation gate.
### Project-status metadata alignment — 2026-10-31

Found stale current-status claims in README.md and PROJECT_STATUS.md that still called the protocol frozen at historical commit 0e0ced45371a2548031c4b9d1370c1dead69d724 and said implementation should begin immediately. Updated both to distinguish that historical CI-verified checkpoint from the current branch, which has later normative deltas and is not yet re-frozen. Updated spec/README.md to link the current Phase 4–5 request-audit additions and to permit unambiguous legacy German passages while requiring new/materially revised normative text to be clear. The historical dated log entries in PROJECT_STATUS.md remain as history.

Commits: README.md 7821365838c115b40753752f496bbf82e2976d60; PROJECT_STATUS.md 9b4c4498112f5088183e900831138225c5f18217; spec/README.md a50fccbf3a3553690d472e858808974904041048; checker variable-scope correction cc53bd3451904bfc54939a6a44e706d8798c2011.

Request inventory cross-check on this branch: 47 registry rows and 47 request-audit rows match exactly by subopcode, name, and request kind; all 47 names appear in the error and conformance chapters; all 47 map to one of eight defining chapters. This is a source-level comparison, not execution of the repository checker or tests.
## Phase 6 presentation-profile cross-audit — 2026-10-31

Reviewed subopcodes 41–47, presentation event IDs 7–8, QueuePresent event delivery, capability/format registries, command-entry ID 5, request/error precedence, reference lifetimes, and the presentation conformance matrix.

### Findings corrected

1. `CreateSwapchain` incorrectly listed a Device/Surface 'cross-device combination' as `BadMatch`. This conflicts with the normative Surface ownership model: a Surface belongs to the X11 connection, not a logical Device, and may be queried with multiple Devices. A valid Device/Surface pair that cannot present now explicitly returns `UNSUPPORTED_CONFIGURATION`; `BadMatch` is reserved for wrong type/foreign connection ownership or actual cross-Device use of Device-owned resources. Added a same-Surface/two-Device and unsupported-pair creation vector.
2. `CMD_COPY_BUFFER_TO_SWAPCHAIN_IMAGE` required transfer usage on resources but did not define queue-family capability. It now requires the parent pool family to support transfer commands. Any GRAPHICS, COMPUTE, or TRANSFER queue capability is sufficient; graphics/compute queues have Vulkan's implicit transfer support even if native `VK_QUEUE_TRANSFER_BIT` is absent. A family with only SPARSE_BINDING and/or PROTECTED is incompatible (`BadMatch`). Added Device-loss precedence and queue-family conformance vectors.

Updated files: spec/errors.md, spec/presentation.md, spec/conformance.md, spec/command-recording.md, registries/queue-flags.md, tools/check-wire-layout.py, spec/request-audit.md.

Latest Phase 6 audit record commit: c6d6f92f496555e8339fcff87e3a879b7e50dfa1. Checker updates include bf841861b86b380d9d8717c587cbe52b6795a91a and e5f464e3631eb6073819112f6912180687c0d795; the checker has not been executed.

Remaining: inspect presentation wire-reply boundary and lifecycle/event cross-contracts for any further drift; run exact-tip checker, golden wire vectors, full Python suite, and required-check audit. Runtime X11/XGE and Vulkan WSI/queue-family acceptance remains separate. Phase 1 agent ship confirmations/shared integration-interface owner are still not posted here.
### Phase 6 lifecycle addendum — DestroySwapchain after Device Loss

Clarified a lifecycle edge case: Device Loss invalidates Swapchain/image usability but does not itself invalidate the public Swapchain XID. `DestroySwapchain` remains a permitted logical cleanup request on the still-live lost Device once all blockers clear; it must still reject while accepted operations or possible backend access can reference images. Successful `DestroyDevice` is different because the cascade already invalidates the Swapchain XID, making a later destroy `BadValue`. Added matching error-map, conformance, and checker contracts.

Commits: spec/presentation.md dc5c1a21d5bcb58558848fdd6ecb9c0775411438; spec/errors.md a231e737df4d01edb52c79562a995a5651512e01; spec/conformance.md 28151e73d42bbc716142d05012bfe84990e4289b; tools/check-wire-layout.py 0b4a966f0e846a8220100267e3bed89bde13dacd; request-audit record 79165fd5b70f0f3537edcde2e75ff8c65d66e3d2.
## CI diagnosis and presentation cross-audit addenda — 2026-10-31

### Automated verification recovered on an intermediate tip

Direct GitHub Actions inspection exposed the push-triggered wire-layout workflow; the earlier commit-status helper did not surface these runs. The initial failing run 41205023918 on `aef3e426...` exposed stale checker/test text anchors after normative edits. The checker assertions and regression expectations were updated to match the current normative language, while the actual CreateDescriptorSetLayout device-limit phase was added to errors.md to remove a genuine cross-document omission.

Run 41205782690 on exact SHA `9c7c8e876458cb22226d161228d29e2a2ce6df5e` completed successfully: wire-layout/request-reply/XGE validation, Timeline semaphore regressions, all 673 Python tests, and required-check presence audit passed. Run 41206737160 on exact SHA `6e8a787781cc20e323e183b0bc6d26c81ff41864` also completed successfully with all required steps green and `Ran 673 tests ... OK`. This second successful run includes the pending-acquire Fence state-machine additions and checker guards. These results apply only to those exact SHAs; later presentation-event and request-audit commits still require a fresh exact-tip run.

### Further presentation cross-contract findings

- A live `InputOnly` Window is a valid Window XID but is not a drawable presentation target. `CreateSurface` now returns `BadMatch` for live InputOnly/non-drawable Window classes, while unknown/destroyed/non-Window XIDs remain `BadWindow`. Backend inability to present to an otherwise valid drawable Window remains a capability/`UNSUPPORTED_CONFIGURATION` result. The 16-byte `CreateSurface` request has no request-specific scalar/reserved fields; conformance and checker contracts no longer invent such a phase.
- `GetSurfaceCapabilities` XID order is now explicitly Device then Surface; `QueuePresent` is Device, Swapchain, then wait Semaphore XIDs in array order. Mixed-unknown-XID conformance vectors pin down those winners.
- Pending `AcquireNextImage` Fence reservations now use the shared Fence `PENDING` state; status queries and waits can observe it, conflicting signal/reset/destroy operations are blocked, success signals once, and non-success terminalization returns it to `UNSIGNALED` without `FAILED`.
- Presentation terminal and image-release milestones now share the same serialized event-decision domain as `SelectEvents` and `DestroyDevice`. Each event independently samples its queue mask at its own milestone; added both-order race vectors.

Latest audit commits after the last fully green exact SHA: `events.md` 40c331a8fdbc410580fd08af9ecb469ad63e0299; `conformance.md` b2ce60e430ef182c9be90d67c65257905f856f96; `tools/check-wire-layout.py` 281dafdc268250c0d46896951fbfded871133fb9; `synchronization.md` 67b6e2ef97197aec724840bb4403133306a742e5; request-audit note 45b23c00e3afd659f080535af6ae8cc2ff0f91c4.

Remaining: run the full required workflow on the latest exact branch tip after these deltas; finish the presentation wire-reply/event/lifecycle cross-review; collect implementation-agent ship confirmations and a named shared integration-interface owner. Runtime X11/XGE and Vulkan WSI/queue-family validation remains a separate implementation acceptance gate.
### Phase 6 completion addendum — presentation milestone/event ordering — 2026-10-31

A cross-contract contradiction was found in the release-first callback order. The event registry semantics sample the IMAGE_RELEASED queue mask and delivery eligibility at the image-release linearization point, and later mask/Device changes cannot retract an already queued event. Some lifecycle prose and conformance vectors nevertheless implied that any later resize/Surface loss/Device loss invalidated the image and suppressed IMAGE_RELEASED even when release had already committed.

Corrected the contract: invalidation before release prevents the release milestone/event; release first while reusable commits its release record and event decision permanently. A later lifecycle transition can invalidate the image/Swapchain for subsequent use but cannot retract the event or rewrite the separate terminal status. Clarified `PRESENTATION_FAILED` and `DestroyDevice` races. Updated tests to cover both milestone orders; no wire ABI values changed.

Files: spec/presentation.md, spec/events.md, spec/conformance.md, tools/check-wire-layout.py, tests/test_presentation_lifecycle_contract.py, tests/test_request_error_path_coverage.py.

Verification: exact branch tip `3ba8641fc8457446ed55aacfabeac4806ad5d3cd`; workflow run 41219811208 SUCCESS. All workflow steps passed, including request/reply/XGE layout validation, Timeline semaphore regressions, all 673 Python tests, and required-check audit.

Still open: runtime X11/XGE and Vulkan WSI validation, especially callback ordering, backend image-reuse guarantees, and disconnect/Device-loss generation isolation. Phase 1 agent ship confirmations and a named shared integration-interface owner remain outstanding.
## Presentation reply/event/lifecycle cross-review addendum — 2026-10-31

A final cross-read of the presentation reply ABI, XGE event definitions, event-selection serialization, conformance vectors, and resource-lifetime summary found two residual normative contradictions:

1. `spec/events.md` described `PRESENTATION_COMPLETE` as reporting only a 'terminal failure', although its event status registry and event-layout section include `SUCCESS = 0`, and the main event contract correctly defines it as the unique terminal outcome. Corrected the shared presentation-event paragraph to state explicitly that the event reports either `SUCCESS` or a failure status.
2. The earlier release-first correction had not been propagated to two older summary/test statements: `spec/conformance.md` said lifecycle terminal failures never emit `IMAGE_RELEASED` and that an invalidated image never emits it; `spec/resource-lifetime.md` likewise said lifecycle-forced failure always suppresses it. Those statements were overbroad when image release committed first while the image was still reusable. They now distinguish invalidation-before-release (no event) from release-before-invalidation (immutable release record/event decision; later invalidation affects only future use).

Updated: spec/events.md 0940e4e47d36f6486967a04ac10df47dae6ba5d7; spec/conformance.md bfb98e51c29d466ade3427ff7e9b3cdb3028f25e and fa97283e3a5e9eea46c3dd0698ef447b7aaeda94; spec/resource-lifetime.md 04984de871953504b9a8657b8af938faadcbd52f; tools/check-wire-layout.py 30d31f31d80542fb10c64c39870f052a020c9e36.

The fixed reply ABI was rechecked: `GetSurfaceCapabilities` has a 64-byte fixed base plus checked variable records and `reply.length = 8 + 2*format_pair_count + present_mode_count + 2*queue_family_count`; all non-success statuses are exactly 64 bytes with zero capability fields. `CreateSwapchain` is 40 bytes (`reply.length=2`), `AcquireNextImage` 44 bytes (`reply.length=3`), and `QueuePresent` 36 bytes (`reply.length=1`), with zero unused reply-header data bytes and explicit non-success payload rules. No wire offsets, lengths, status IDs, or request subopcodes changed.

Static checker guard now requires the success-inclusive terminal event wording and the release-first lifecycle rule in both conformance and resource-lifetime chapters. Exact-tip CI was subsequently completed successfully on `0bbb543faf2ab1046d8a1729ca845bf86bd22a70`; see the verification addendum below.
CI follow-up for the presentation cross-review: the first exact-tip run passed the wire-layout/XGE checker and Timeline regressions but the full Python suite found one stale assertion in `test_image_release_requires_quiescent_reusable_image` that expected the old `PRESENTATION_FAILED permits IMAGE_RELEASED...` wording. Updated that test to assert the corrected normative condition (backend quiescence plus a still-usable Swapchain). The earlier run also exposed and corrected an exact-text mismatch in the new checker guard; no normative rule was weakened to satisfy tests.

Test correction commit: `tests/test_presentation_lifecycle_contract.py` 746ba80a6f65d99747a45563027882b4656cec03. This intermediate run was superseded by the successful exact-tip run recorded below.
### Exact-tip verification — presentation reply/event/lifecycle audit

The branch tip `0bbb543faf2ab1046d8a1729ca845bf86bd22a70` completed workflow run [41233370197](https://github.com/metux/xav-design/actions/runs/41233370197) successfully. Every required step passed: checker syntax, request/reply/XGE validation (4,754 checks), Timeline semaphore regressions, full Python suite (**675 tests, OK**), and required-check presence audit. This supersedes the intermediate failed runs caused by the checker wording mismatch and one stale lifecycle-test expectation; both were corrected without weakening normative requirements.

The presentation wire reply layouts remain unchanged. Remaining acceptance gates are runtime X11/XGE interoperability and Vulkan WSI/backend lifecycle validation. Phase 1 ship confirmations and a named shared integration-interface owner are still outstanding in the blackboard.
## Request group 24–30 audit — command-pool/recording and queue/synchronization boundary — 2026-10-31

Reviewed subopcodes 24–30 (`CreateCommandPool`, `DestroyCommandPool`, `ResetCommandBuffer`, `CommandBufferData`, `QueueSubmit`, `CreateSemaphore`, `GetSemaphoreCounterValue`) across command recording, queue submission, synchronization, error precedence, resource lifetime, registries, and conformance.

### Normative gap corrected

The command-pool rule said only `CMD_DISPATCH` required a COMPUTE-capable queue family. However, the registry defines IDs 1–4 as compute command entries: `CMD_BIND_PIPELINE`, `CMD_BIND_DESCRIPTOR_SETS`, `CMD_DISPATCH`, and `CMD_PUSH_CONSTANTS`. Binding a compute pipeline/set or issuing compute-stage push constants into a command buffer from a non-COMPUTE family was not explicitly rejected. The common resource-dependent validation rule now requires COMPUTE for every entry ID 1–4, including chunks with no dispatch. Presentation copy ID 5 retains its separate GRAPHICS/COMPUTE/TRANSFER rule. Pool creation itself remains permitted for any requested queue family; empty/non-compute command buffers retain the documented family-local submission path.

Added error mapping and conformance vectors for each of the four compute entries on a non-COMPUTE family, with valid resources; require `BadMatch`, no chunk/reference append, and `DEVICE_LOST` precedence after valid identity checks. The checker now cross-checks the common rule, error mapping, and all-entry conformance vector.

Commits: spec/command-recording.md updated (latest command-recording commit recorded in the branch history); spec/errors.md `04978de064f6fb52780d5dbe6e160488a52600b1`; spec/conformance.md `54581d42bbccd84e4c759379b2b6579a3833ae9a`; tools/check-wire-layout.py `db35fc5b8d29e999885026bdbd0e3a4894520c86`.

### Cross-checks with no further changes in this pass

- Command Pool creation uses requested `queue_count > 0` only; it does not invent a command-buffer-support flag. Destroy/Reset/CommandBufferData pool identity and child-XID ordering are serialized consistently.
- `CommandBufferData` structural/scalar/XID/type/ownership/Device/buffer-state/resource-compatibility/preparation phases agree with the central error map; ABORT remains the only post-loss logical exception and is bound to the exact parent Pool.
- `QueueSubmit` count formula, 16-bit count fields, checked total length, token scope/uniqueness, XID order, type-dependent semaphore values, wait-stage support, mutable-state order, all-or-nothing acceptance, destruction races, and callback-generation/reservation rules remain mutually consistent in this pass.
- `CreateSemaphore`'s mandatory Timeline feature is backed by the logical-Device baseline. `GetSemaphoreCounterValue` correctly returns an X11 `DEVICE_LOST` error with no reply after loss, while its Binary-type `BadMatch` is later in precedence; conformance covers both.

Exact-tip CI for the newly added compute-entry capability rule is pending. Runtime Vulkan validation must still confirm queue-family command support and callback/lifetime behavior.
### Command-buffer entry semantics addendum — descriptor binding and dispatch context — 2026-10-31

A second pass over subopcode 27 found that the wire layout for `CMD_BIND_DESCRIPTOR_SETS` did not define positive count, `first_set` arithmetic/range bounds, or the precise immutable layout comparison. More broadly, the spec named pipeline/layout compatibility and descriptor binding checks without defining the recording context or the prerequisite state for dispatch. This left implementers to infer state persistence across chunks and how a bound Pipeline relates to the layouts used by descriptor/push-constant entries.

Defined the v0.1 behavior:
- `descriptor_set_count` is positive; checked `first_set + count` overflow is `BadValue`; the resulting interval must fit the specified PipelineLayout's set slots (`BadMatch`). Each DescriptorSet layout must match its indexed PipelineLayout slot by binding number/type/count/stage flags, independent of source record order.
- Recording context is ordered and persists across accepted chunks. Pipeline binding replaces the current Pipeline; descriptor-set binding replaces only the specified slots; push constants replace only the specified byte interval. Failed chunks leave context unchanged; ABORT/reset clear it; FINAL preserves it.
- Dispatch requires a previously bound Pipeline and every statically used descriptor set/slot initialized (`INVALID_SYNCHRONIZATION_STATE`). At dispatch, descriptor binding PipelineLayouts are checked against the Pipeline's layout using the v0.1 Vulkan-compatible prefix rule (identical push ranges and identical set-layout definitions through the used set index); push-constant layouts require identical push-range definitions. Public PipelineLayout XIDs need not be identical.
Added matching error and conformance vectors, including count/overflow-before-XID, exact range boundary, layout mismatch, differing lower-prefix versus higher-unused set layouts, missing pipeline/descriptor state, persistence across chunks, failed-chunk rollback, reset/abort clearing, and current DescriptorSet contents after update.

Commits: spec/command-recording.md `43211375f29662174083dc707c0d96064aaf2be0`; spec/errors.md `5f6cd628b1fdc181b8f79927c5d6a5e4f86ea509`; spec/conformance.md `5aab284bdea36f6f2f7d74adea83a1f390785bb9`; tools/check-wire-layout.py `ecf3c97b39215fe412a8d56e3778193cd910cae7`.

Exact-tip CI is pending for this addendum. This does not change request/reply wire layouts.
### Command recording replay and empty QueueSubmit addendum — 2026-10-31

Two further implementation semantics are now explicit:

- The command-buffer binding context is a recording-time validation view across accepted chunks and FINAL, but each execution/replay of an EXECUTABLE command buffer starts from a fresh empty binding context and reconstructs Pipeline, DescriptorSet, and push-constant state from the recorded entries. No state leaks between submissions. Added a conformance vector that submits the same executable buffer more than once.
- `QueueSubmit` counts C/W/S are independently allowed to be zero. Semaphore-only/fence-only submissions and a fully empty 40-byte submission are valid; the empty submission still consumes its unique token at acceptance, participates in the addressed queue order, and has the ordinary terminal outcome/event behavior. Empty arrays create no associated references/reservations. Added vectors for each zero-count combination and the all-zero case.

Commits: spec/command-recording.md `4d6e558a8eefc4d81f61d22eab35cc2e80685df5`; spec/conformance.md `8527836ea78423ef93d24a7fc674c3ea15ac84b5` and `ac123d2c633d63c6d114c7a91a1a94e0cf14cae6`; spec/queue-submission.md `f52ccbb68cfaf63102099dc46b456f36f93b108a`; tools/check-wire-layout.py `b2ff755971631d366c8be87ce4179f6102b76dbc` and `f31f656a882bd4f11fbbc0962e3e67d433a78cbb`.

These additions do not change the QueueSubmit request wire formula or any opcode. Exact-tip CI is pending.
### Exact-tip verification — request group 24–30 and command-recording addenda

The latest branch tip `415e02e10e489fc4eab5697debb2f23c127a3cb8` completed workflow run [41234267087](https://github.com/metux/xav-design/actions/runs/41234267087) successfully. All steps passed: wire-layout/XGE validation (4,754 checks), Timeline semaphore regressions, full Python suite (675 tests), and required-check audit. This includes the compute-entry queue-family rule, descriptor-set bounds/layout compatibility, ordered command-buffer binding context, fresh state on every replay, and zero-count/empty QueueSubmit semantics.

Remaining implementation acceptance gates: runtime Vulkan validation of queue-family command support, descriptor/pipeline-layout compatibility and dispatch state; runtime callback/reference-retirement behavior; X11/XGE interoperability. Phase 1 ship confirmations and a named shared integration-interface owner remain outstanding in this coordination file.
### Recording-context chunk atomicity clarification — 2026-10-31

Clarified that entries within a `CommandBufferData` chunk are evaluated in wire order against a tentative copy of the current recording context, and the context commits only with the entire accepted chunk. A valid bind earlier in a rejected chunk cannot leak into the previously accepted recording context. Added the matching conformance vector and checker guard.

Commits: spec/command-recording.md `ec1d978a73d34cf7d30cc0863ce6f7aa76d9a8a1`; spec/conformance.md `6805c30913a4b2c1d3b10843c4a153f65b252f69`; tools/check-wire-layout.py `7b286420a1d0e0813033bb9d30ee3443f442bfbd`. Exact-tip CI pending.
### Exact-tip verification — command recording and QueueSubmit semantics

The exact branch tip `6f35e8c0eddb0753ce8cdb8debc14c5980d7a224` completed workflow run [41234397601](https://github.com/metux/xav-design/actions/runs/41234397601) successfully. All steps passed: checker syntax, request/reply/XGE validation, Timeline regressions, complete Python suite (675 tests), and required-check audit. This includes the final chunk-atomic recording-context clarification and the fresh-empty-context-per-replay rule.

Group 24–30 audit is complete at the normative/conformance/static-check level. Runtime Vulkan behavior remains an implementation acceptance requirement. Phase 1 agent ship confirmations/shared integration-interface owner remain outstanding.
## Request group 31–40 audit — host synchronization, fences, generic destruction, and event selection — 2026-10-31

Reviewed `WaitSemaphores`, `SignalSemaphore`, `DestroySemaphore`, `CreateFence`, `GetFenceStatus`, `WaitForFence`, `ResetFence`, `DestroyFence`, `DestroyResource`, and `SelectEvents` against synchronization state, Device Loss/DestroyDevice, resource lifetime, event masks/XGE layouts, and conformance.

### Findings corrected

1. `WaitForFence` defined an open registration and atomic completion/timeout/lifecycle races, but unlike `WaitSemaphores` did not explicitly prohibit blocking the X11 request dispatcher. This could deadlock when the later request on the same connection is the `QueueSubmit` that carries the Fence. It now MUST register asynchronously and continue processing later requests; the timeout continues independently, including while an earlier `WriteBuffer` is pending and a dependent QueueSubmit is deferred. Added same-connection and deferred-upload conformance vectors and a checker guard.
2. `DestroySemaphore` referred generically to accepted queue waits and other host operations, but the precise relationship to presentation waits and pending `AcquireNextImage` signal reservations was implicit, and the conformance matrix did not test both. The blocker now explicitly includes `QueueSubmit`/`QueuePresent` waits, `QueueSubmit` signals, open `WaitSemaphores` registrations, and open `AcquireNextImage` signal reservations. It also states that presentation terminal/release milestones alone do not keep the Semaphore alive after its own wait/backend holds have retired. Added both commit-order and post-terminalization vectors; aligned the English/German error maps and resource-lifetime chapter.
3. `DEVICE_STATUS_CHANGED` described Physical-Device availability/removal, while the effect on already-created logical Devices was unspecified. Clarified that Physical-Device status governs discovery/property/new-device eligibility and does not itself synthesize logical `DEVICE_LOST`; existing logical Devices follow their own backend Device-Loss state machine. `REMOVED` remains final for the Physical-Device XID and blocks future creation while stored metadata remains queryable. Added status-versus-logical-loss conformance and checker guard.

Commits: spec/synchronization.md `5e313e6b27cccb96bc1bc8821a7d7f70948382e2`; spec/conformance.md `a7f4a08bda0c1ad192ec9ca3777b8d51361da1a9` and `e4b5155a2528b2fe77ccd2e74f87564508266ceb`; spec/errors.md `70dc682943f098dd9b16bee40c123f701a685803`, `a4bc5f0d063d164f8651ccbf63b993535b75d176`, `e9ea44564a2a24c3320f2f0810a117a89f6eea0d`; spec/resource-lifetime.md `9438044045fe131670a55b9dae3af835569449d5`; spec/devices.md `cd9f3eecd33ae02d791de7a8d608e3f53ff88082`; spec/conformance.md `1a32c6d3c8fb87820bd5f7594df7233c5fe0d95a`; tools/check-wire-layout.py `71fdb0daf225280f592d977d28e1cb7bc97fb709` and `d61882aa7da37fd232211a0692ccda4706509e0a`.

### Cross-checks with no further change in this pass

- WAIT_ANY/WAIT_ALL coherent snapshots, zero/finite/infinite timeout, first-terminal-wins races, counter publication order, and disconnect cancellation remain consistent.
- Host SignalSemaphore reservation/order rules, including the WriteBuffer progress exception, remain consistent with QueueSubmit deferred dependency rules.
- Fence state transitions across QueueSubmit and AcquireNextImage, WaitForFence/GetFenceStatus/ResetFence precedence, and exact-identity DestroyFence blockers agree.
- DestroyResource's allowed/excluded resource types, logical cleanup after Device Loss, command-buffer invalidation, and deferred internal reference release agree with the resource-lifetime rules.
- SelectEvents scope fields, profile-specific mask bits, XGE negotiation, atomic replacement, DestroyDevice mask removal, and milestone-time event-mask sampling remain consistent with the XGE event layouts.

Exact-tip CI is pending for these changes. Runtime X11/XGE event delivery and Vulkan synchronization/callback acceptance remain implementation gates.
### Exact-tip verification — request group 31–40

The exact tip `00b56d0a2ff11f68cbb9c8d3c9a5a97385b5ea6f` completed workflow run [41235359899](https://github.com/metux/xav-design/actions/runs/41235359899) successfully. All steps passed: syntax checks, request/reply/XGE validation (**4,759 checks**), Timeline semaphore regressions, complete Python suite (**675 tests**), and required-check audit. This includes the non-blocking `WaitForFence` rule, explicit QueuePresent/AcquireNextImage semaphore destroy blockers, and Physical-Device status/logical-Device-loss separation. Intermediate failures were limited to checker insertion/wording mismatches; those were fixed, and no normative requirements were weakened.

Group 31–40 audit is complete at the normative/conformance/static-check level. Runtime X11/XGE delivery, Vulkan semaphore/fence behavior, and backend callback/reference-retirement remain implementation acceptance gates. Phase 1 agent ship confirmations and a named shared integration-interface owner are still outstanding.
## Final specification-content readiness — 2026-10-31

All 47 registered request contracts (compute baseline 1–40 and presentation profile 41–47) have completed the final cross-request normative/error/conformance audit. The latest normative content candidate `7ffd9c5b17cc706d0810d6c8fdbb6bf433ce6576` passed exact CI run [41235437766](https://github.com/metux/xav-design/actions/runs/41235437766): 4,759 wire-layout/documentation checks, 72 Timeline regression tests, 675 Python tests, and required-check audit. `spec/freeze-checklist.md`, `spec/open-issues.md`, `README.md`, and `PROJECT_STATUS.md` now record that the v0.1 normative content is freeze-ready; later status/audit metadata edits do not alter protocol rules and are being rechecked by CI.

### Still open — implementation coordination and runtime acceptance

- Phase 1 Ship A–E confirmations and the named shared integration-interface owner have not yet been posted here. Ship A must continue to own common framing/dispatch integration only; the device request ownership split remains as recorded above.
- Runtime acceptance remains open: live X11/XGE interoperability; compute backend upload/dispatch/readback and synchronization; callback/reference retirement under Device Loss/disconnect; and presentation WSI/resize/image-release behavior if the optional profile is implemented.

Normative design gaps are not currently known. This does not claim that runtime conformance or integration ownership is complete.

## QueryVersion assignment and implementation note — 2026-11-02

The specification now assigns `QueryVersion` common bootstrap subopcode 0; compute requests 1–40 and presentation requests 41–47 are unchanged. It is a compute-baseline control request, not presentation-profile-gated.

- Ship A (common protocol framing/dispatch) is the proposed sole owner for the `QueryVersion` request handler and reply encoding; it must not be duplicated by the device ships.
- Request: exactly the 8-byte common header, no payload, `flags = 0`, `reserved = 0`.
- Reply: standard 32-byte X11 reply, `reply.length = 0`, `major_version = 0`, `minor_version = 1` at offsets 8 and 10, and zero bytes at offsets 12–31.
- The request is usable after standard `QueryExtension` discovery without `GEQueryVersion`, Device creation, or event selection. XGE negotiation remains a separate prerequisite for the requests that already require it.
- Golden request/reply frames and malformed-header/version/reserved-field tests are in `tests/query-version-vectors.json` and `tests/test_query_version_vectors.py`.
- The version reply reports the server's implemented protocol version; it is not a negotiated per-connection version and causes no state change.

This update changes only the new request assignment and its contract; subopcodes 1–47 and the Phase 1 handler split are unchanged. Please confirm Ship A's ownership and add the handler to its implementation plan before integrating the new contract.


## QueryVersion conformance verification — 2026-11-02 (superseded opcode note)

The complete `QueryVersion` specification, registry, request audit, error mapping, golden request/reply vectors, test guards, and status metadata are present on this branch. The verified normative/test candidate `fe45f897fc6dd079f914f8290b94855f37dd864c` passed [CI run 41432690799](https://github.com/metux/xav-design/actions/runs/41432690799): **4,823 wire-layout checks**, **72 Timeline regressions**, **685 Python tests**, and the required-check audit all passed.

The golden request and reply fixtures cover both X11 byte orders; malformed request common-header/length cases and malformed reply version/length/reserved-field cases are rejected by offline reference tests. These checks do not establish live server behavior. Ship A remains the proposed sole owner of the `QueryVersion` dispatch handler and reply encoding; explicit ship confirmation is still outstanding.


## Design-Agent update — QueryVersion bootstrap subopcode migration — 2026-11-02

The design branch now moves `QueryVersion` from subopcode 48 to subopcode 0. This is intentional: zero is no longer reserved; it is the common bootstrap control request available immediately after `QueryExtension`, before XGE negotiation or any Device setup. Compute-baseline requests 1–40 and presentation-profile requests 41–47 are unchanged. The registry and request audit contain 48 assignments total, contiguous over 0–47.

Updated normative and test surfaces include `registries/request-subopcodes.md`, `spec/wire-protocol.md`, `spec/request-audit.md`, `spec/errors.md`, `spec/conformance.md`, the XGE interoperability plan, QueryVersion request fixtures and tests, generic request framing tests, the error-map consistency test, and the static wire-layout checker. The two request golden frames now encode byte 4 as `0x00` in both byte orders. The 32-byte reply ABI is unchanged.

This changes the request-dispatch ABI. Ship A must use subopcode 0 for the bootstrap handler; any implementation-side dispatch tables or generated opcode constants copied from the old subopcode 48 assignment must be updated before implementation branches are integrated. Do not retain 48 as an alias: it is unassigned after this migration. The older QueryVersion notes above record the superseded assignment and are historical; this section and the current normative registry are authoritative.

Verification is pending on the resulting branch tip. Runtime X11 interoperability and implementation-branch dispatch synchronization remain open.


### Migration CI result — 2026-11-02

The first CI run exposed two stale test assertions: the big-endian fixture metadata still carried subopcode 48, and the generic request-vector registry test still asserted that zero was reserved. Both were corrected. The final migration commit `61e4e5517c94074d11cb5319f747528a8fc3f148` passed [CI run 41442418120](https://github.com/metux/xav-design/actions/runs/41442418120): **4,823 wire-layout checks**, **72 Timeline regressions**, **685 Python tests**, and the required-check audit all passed. This verifies the specification/reference tests, not a live X11 server or implementation dispatch table.

## Local-agent WIP integration — 2026-11-02

The local-agent branch `wip/by-local-agent` was reviewed and integrated into `docs/restructure-2026-10-21` through [PR #3](https://github.com/metux/xav-design/pull/3), merged as `a6019f53fbc14f0cf2824889f14d92de6629694d`.

Integrated coverage:
- `GetPhysicalDeviceMemoryProperties`: little-/big-endian request vectors and normative field-offset/reply-layout documentation.
- All seven presentation requests (subopcodes 41–47): explicit fixed request lengths and normative field-offset/length tests.
- `QueuePresent`: reference encoder now serializes the variable wait-semaphore XID list, checks count/list agreement and duplicate XIDs; golden vectors cover zero and two waits in both byte orders.
- CARD64 fixture metadata was corrected to match the actual encoded wire bytes; JSON number precision must not be used to round these values.
- Removed duplicate request-layout prose while retaining the compact request contract required by the wire checker.

Verification: PR-head workflow run [41452295432](https://github.com/metux/xav-design/actions/runs/41452295432) passed the wire-layout checker, all **72 Timeline regressions**, the complete **685-test Python suite**, and the required-check audit. Post-merge branch-tip run [41452447103](https://github.com/metux/xav-design/actions/runs/41452447103) also passed; branch-tip audit [41452447172](https://github.com/metux/xav-design/actions/runs/41452447172) passed.

This is spec/reference-test integration only. It does not close the outstanding live X11/XGE or Vulkan runtime acceptance gates, nor the Phase 1 ship ownership confirmations/shared integration-interface owner.



## Post-merge wire-contract audit — 2026-11-02

Reviewed the local-agent WIP integration from PR #3 against the normative memory/presentation chapters, request/error audit, conformance matrix, golden fixtures, and reference encoder.

### Finding corrected

- `GetPhysicalDeviceMemoryProperties` had an ambiguous lead-in saying that the reply fields followed the 32-byte X11 header while its new offset table used absolute packet offsets (8, 12, 16, 20, and 32). Clarified that offsets are absolute, fixed fields occupy the ordinary reply data area at offsets 8–23, and variable records begin at offset 32.
- `QueuePresent` now receives request-specific raw-wire validation in `tests/test_wire_vectors.py`: the declared wait count must exactly match the variable XID tail, and the count-derived request size must fit the ordinary X11 limit (262140 bytes; maximum representable wait count 65525). Added little- and big-endian negative vectors for count/tail disagreement in both directions and arithmetic/envelope overflow.

Commits:
- `spec/memory-buffers.md` clarification: `9e970d57dde23005228d5805c18c28c23d74b631`
- `tests/test_wire_vectors.py` QueuePresent raw-wire count/length checks: `15166a57e496330001324b8b3d22b4e8423a1006`

### Review result and verification

- The integrated presentation layouts agree with the fixed request offsets, CARD64 alignment, QueuePresent variable-tail offset/formula, and reply sizes. The two QueuePresent positive fixtures cover zero and two waits in both byte orders; semantic acceptance/error precedence remains covered by the existing state model and conformance vectors.
- The memory-properties reply formula remains `reply.length = 4 + 2 * memory_type_count + 4 * memory_heap_count`; record offsets and count bounds are consistent with the 32-byte X11 reply header.
- Exact-tip CI has not yet been observed for the two post-merge audit commits. Run the wire checker, golden vectors, Timeline regressions, full Python suite, and required-check audit on the resulting branch tip before treating these additions as verified.

This is specification/reference-test work only; no runtime implementation was added.


### QueuePresent count bound and checker guard — 2026-11-02

The presentation wire audit also made the derived ordinary-request bound explicit: `40 + 4 * wait_semaphore_count` MUST fit within 262140 bytes, so the maximum wait count is 65525; larger values are `BadLength`. The common wire-envelope rule already sets this 262140-byte limit and BIG-REQUESTS remains unsupported.

- `spec/presentation.md`: `c3db6aa5533b0cdac9c9e547206e022da9d53b39`
- `tools/check-wire-layout.py`: `848b01a8137cc79b7d468bd590b6e3fadd713421`

The checker now guards the normative bound and requires the raw-wire count/length and overflow assertions in `tests/test_wire_vectors.py`. No wire layout or opcode changed.

The GitHub status endpoint currently reports no checks/workflow runs for the direct post-merge commits in this audit; therefore the green PR #3 merge CI does not validate these later corrections. Exact-tip CI remains pending, and no passing result is claimed for this audit series.

The QueuePresent boundary test now accepts the exact maximum 262140-byte ordinary request (65525 waits) in both byte orders and rejects 65526 waits. The static checker also cross-checks the bound against the common framing chapter.

- `tests/test_wire_vectors.py` boundary coverage: `477d0921c7daba11bc826b4aa813fcf86e5f144e`
- `tools/check-wire-layout.py` common-limit cross-check: `358023526dd66eb6518d9a16df701e8041516e0e`

### Fixed request-length negative coverage — 2026-11-02

Extended the raw-wire reference validator to enforce the exact fixed request sizes for `GetPhysicalDeviceMemoryProperties` and all six fixed-size presentation requests (subopcodes 41–46). New tests exercise the valid request and both one-word-short and one-word-long frames in little- and big-endian order. `QueuePresent` remains count-derived and is covered separately by the variable-tail and ordinary-limit tests.

- `tests/test_wire_vectors.py`: `72b28a8adcfa6461491e4344460022bb5141f8ee`
- `tools/check-wire-layout.py` guard: `1e0927d0323770818e87f322d5f6d2b9bb2395f6`

This closes the request-length negative-vector gap identified during the PR #3 post-merge audit at the reference-wire-validation level. It does not replace live server conformance testing. Exact-tip CI remains unobserved for the direct commits in this audit series.


## Reply-request inventory correction — 2026-11-02

The post-QueryVersion audit found one stale count in the conformance text: it still described 15 Reply requests and omitted the newly assigned bootstrap `QueryVersion` request. The central registry and checker already included `QueryVersion`, so the actual inventory is 16: `QueryVersion`, eleven other compute-baseline Reply requests, and four presentation-profile Reply requests.

- `spec/conformance.md` now lists all 16 explicitly: `46a615b5620b5584a625655eeeaae137d949a500`
- `tools/check-wire-layout.py` now asserts the total and the profile breakdown against the registry and conformance text: `054ce3a0213e805494be073ef47b1426fd9aa90c`

No request layout, kind, subopcode, or runtime behavior changed. Historical dated audit entries that accurately recorded the pre-QueryVersion inventory remain historical; current normative/conformance inventory is 16. Exact-tip CI remains to be confirmed.

### Freeze/status metadata reconciliation — 2026-11-02

Reconciled current status documents against the actual verified CI baseline and the unverified post-merge audit delta:

- `spec/freeze-checklist.md` now identifies `a6019f53fbc14f0cf2824889f14d92de6629694d` / CI run 41452447103 as the latest verified baseline and explicitly leaves exact-tip CI for the post-merge audit delta unchecked.
- `PROJECT_STATUS.md` now uses the same baseline, records the 16-Reply inventory, and does not label the current branch tip CI-verified.
- `README.md` had a mismatched CI URL (label 41442418120 pointed to run 41432690799); the URL now points to 41442418120.

Commits: freeze checklist `8a2dbd1354ccf1a853e6796d6c8dd290b94222db`; project status `a5f1258fce01e0e6cf982470d79cffff5629fb75`; README `6f470ad309cf1b96aae1c2464ca0f388d742aa32`.

These are status/traceability corrections. The latest direct commits still have no visible status checks from the GitHub status endpoint; exact-tip CI remains pending.


## Exact-tip wire/XGE CI verification — 2026-11-02

The post-merge audit CI failures on the prior tip were reproducible and have been corrected on `docs/restructure-2026-10-21`:

- `spec/memory-buffers.md`: introduced an explicit `Reply layout:` boundary after the 12-byte request contract. This prevents the request-field audit from treating reply-header fields at offsets 12, 16, and 20 as request fields.
- `spec/conformance.md`: explicitly enumerates all 16 registered Reply requests, separating the common bootstrap, compute-baseline, and presentation-profile groups.
- `tools/check-wire-layout.py`: validates that the enumerated names exactly match the central Reply registry; the inventory matcher uses a literal-parenthesis pattern.

Commits:
- `8ab04a4a5e46dbd13e5818f37bc7d55d8e21b67f` — request/reply boundary and 16-reply inventory.
- `dd6242139849e252e88bbf16552fa0dd531c1ed4` — correct inventory matcher.

Exact-tip GitHub Actions run for `dd6242139849e252e88bbf16552fa0dd531c1ed4` succeeded (run 41471016473):

- `python tools/check-wire-layout.py`: 4,829 checks passed.
- Timeline regression runner: 72 tests passed.
- Full `unittest discover -s tests -p 'test_*.py' -v`: 688 tests passed.
- All 33 test methods in `tests/test_event_vectors.py` were present in the successful suite log.
- Required-check audit: success. Branch-tip monitor run 41471016586: success.

Local execution is still blocked in the current automation container: `getent ahosts github.com` returns no addresses (exit 2), and `git ls-remote https://github.com/metux/xav-design.git refs/heads/docs/restructure-2026-10-21` fails with `Could not resolve host: github.com`. No local checkout is present. Therefore the requested local commands `python3 tools/check-wire-layout.py` and `python3 -m unittest tests.test_event_vectors` have **not** been run locally; the results above are GitHub Actions results, not local results.

No runtime X11/XGE or Vulkan backend interoperability test was performed by this static CI run.


## XGE event sequence-number ABI audit — 2026-11-02

The XGE event audit confirmed that the nine event layouts, profile-specific IDs, status registries, both byte orders, fixed lengths, reserved bytes, and SelectEvents mask mappings are covered by the normative chapters and reference tests. One normative ambiguity remained: the 16-bit XGE sequence field was identified by offset but its source was not stated precisely for asynchronous backend events.

Corrected:
- spec/events.md now requires the low 16 bits of the sequence number of the last X11 request issued by the recipient client that the server has processed or is currently processing at the event-enqueue point. It explicitly forbids substituting another client's request sequence, a submission token, or a backend callback's stored sequence; wrap is modulo 65536.
- spec/conformance.md adds the recipient-connection and wrap-boundary requirement.
- tests/test_event_vectors.py checks sequence encoding at 0 and 65535 in both byte orders.
- tools/check-wire-layout.py now guards the normative source and anti-confusion rules.

This is an XGE ABI clarification; event layouts, IDs, mask bits, and runtime behavior are unchanged. Exact-tip CI is required before marking this delta verified.

### XGE sequence-number audit CI result — 2026-11-02

The final event-sequence wording was aligned with the X11 core protocol: the 16-bit event sequence is the low 16 bits of the last request issued by the recipient client that the server has processed or is currently processing when the event is enqueued. This preserves the X11 rule for events generated during request processing as well as later asynchronous events.

Exact-tip validation on commit 96bede90c558d8127b07c53d6a009ea52a40f717 succeeded:
- Wire-layout workflow 41473067916: 4,831 static wire-layout checks passed; full Python suite: 689 tests passed; Timeline and required-check steps succeeded.
- Branch-tip monitor 41473068396: success.

The earlier wire-layout failure on intermediate commit 12911c4f was the expected missing static-checker guard; the guard was added in 93480019 and the final branch-tip run passed. No runtime X11/XGE server test or Vulkan backend test was performed.

## Device XID reuse and event-selection isolation — 2026-11-02

The cross-chapter lifecycle audit confirmed that disconnect, DestroyDevice, callback identity, queued-event preservation, and XGE negotiation were already specified. One point was only implicit: although DestroyDevice removed Device/Queue selections, the text did not explicitly state that those selections are keyed by immutable Device identity and cannot be inherited when the public Device XID is reused.

Clarified in spec/events.md: Device/Queue masks belong to the internal Device identity; successful DestroyDevice atomically removes them; a newly created Device using the same numeric XID starts with no Device/Queue selection. The Connection mask survives. Added a conformance case and a static checker guard, plus a regression test in tests/test_select_events_vectors.py.

No event layout, event ID, mask bit, request layout, or runtime behavior was changed. This closes a protocol identity/selection ambiguity and makes the XID-reuse behavior directly testable. Exact-tip CI is required before treating this delta as verified.

The live XGE interoperability plan was also extended to exercise Device XID reuse: a new Device generation must not inherit Device/Queue masks, while the Connection mask remains active. This is a runtime test requirement for the eventual X11/XGE server, not something the static fixture suite can prove.


## Presentation XGE golden-byte coverage — 2026-11-02

The event/profile audit found no ID collision or profile-gating contradiction: compute events remain IDs 0–6, presentation events remain IDs 7–8, and queue mask bits 2/3 are presentation-only. The static checker already compared both 64-byte presentation payload layouts against the normative chapter, but the golden-byte fixture contained only the seven compute events.

Added four presentation golden vectors (both events in little- and big-endian), a dedicated encoder/validator, negative checks for nonzero IMAGE_RELEASED reserved data and out-of-range PRESENTATION_COMPLETE status, and a static checker guard requiring this coverage. The conformance chapter now states the 64-byte/length-8 and event-local value requirements.

These are static ABI tests only. Live XGE delivery, profile-gate behavior, and actual presentation backend behavior remain implementation-level interoperability work.

Commits:
- `63a9a9643c689eef06055d2326554a026b40c8be` — presentation event encoder and tests.
- `1e912abdcf7c4026bc744d6963a410cb58cfe1cd` — four presentation event golden vectors.
- `16af6b40a1a3c9b7e339bf69e0fc6c20677005d9` — static checker guard.


### Presentation XGE checker follow-up

The first CI attempts for the presentation golden-vector checker stopped before the test suite because the checker used `json.loads` without importing `json`. This was a checker-only failure, not a vector or protocol failure. Added the missing standard-library import in commit `db1b5d38479911eb8e3bdef8859105285deca505`; exact-tip CI for that correction is pending. The earlier failed runs must not be treated as validation.


## Freeze checklist reconciliation — 2026-11-02

Exact-tip CI for the completed post-merge specification audit passed on candidate `0b9c40e0907592f7f96687912d948abf221123d0`:
- [Wire-layout run 41476931362](https://github.com/metux/xav-design/actions/runs/41476931362): 4,836 static checks passed; Timeline regression runner passed (72); full Python suite passed (692 tests).
- [Branch-tip monitor 41476931297](https://github.com/metux/xav-design/actions/runs/41476931297): success.

Updated `spec/freeze-checklist.md`, `PROJECT_STATUS.md`, `README.md`, and `spec/open-issues.md` to stop presenting the PR #3 merge baseline or October candidate as the latest verified content. The freeze checklist now marks the post-merge audit CI gate complete. Implementation acceptance remains open: live X11/XGE, Vulkan compute/runtime lifecycle, and optional presentation backend validation. Project coordination still needs Phase 1 ship confirmations and a named shared integration-interface owner.

The checklist/status-only edits themselves are committed separately and must receive their own exact-tip CI result before that later tip is called verified.


## Spec freeze and implementation handoff — 2026-11-02

The specification-compliance checklist above is now checked against the completed freeze checklist and exact-tip CI. No remaining normative protocol-design item is known to block starting implementation. This does not mean Phase 1 implementation is complete: the ships still need to confirm their request-handler ownership, Ship A must name the shared integration-interface owner, and the live X11/XGE and Vulkan acceptance gates remain open.

The canonical non-overlapping handler split is Ship B: subopcode 1; Ship C: 2–3; Ship D: 4–6; Ship E: 7. Ship A coordinates common framing/dispatch and shared helper interfaces. The five required ship confirmations listed below remain outstanding unless a ship posts an explicit confirmation here.

The previous 2026-10-30 baseline references in older coordination-history sections are historical snapshots; follow the current `docs/restructure-2026-10-21` branch and `spec/freeze-checklist.md`, not those old pinned hashes.


## Shared client/server protocol header audit — 2026-11-03

The public C wire declarations have been consolidated into the single header `protocol/include/xaverius.h`; the former split `xaveriusconst.h` and `xaveriusproto.h` files were removed. Both server and client consumers include `<xaverius.h>`. `protocol/README.md` documents the include path, X11 byte order, four-byte packing, CARD32 wire XIDs/Atoms, and checked variable-payload sizing.

A full comparison against the current normative chapters and registries found no differing request/reply/event field offsets, fixed prefixes, wire sizes, or assigned numeric values. The header now statically verifies the IEEE-754 binary32 assumptions for `FLOAT32`, every fixed request size, every variable request prefix, key nested/reply payload offsets, all fixed reply sizes, and all nine XGE event sizes. The unchecked `XAV_PAD4` arithmetic macro was removed so callers must apply the specification's checked-size arithmetic rather than risk overflow.

The normative source remains `spec/` and `registries/`; this header is only their C projection. Exact-tip CI for the latest header commit is running; do not treat the prior successful header compile as verification of the later padding-helper removal. Runtime X11/XGE and Vulkan interoperability remain implementation acceptance work.


## Client-side prototype — 2026-11-04

The client prototype lives under `client/` on the authoritative specification branch. The chosen layering is a small XCB-based protocol runtime (public XCB APIs only); a Vulkan ICD will be a later consumer, not part of the transport.

Implemented files:
- `client/include/xaverius_client.h`: public opaque-connection API and host-order Physical-Device records.
- `client/src/internal.h`: internal transport, connection state and wire-decoding interfaces.
- `client/src/connection.c`: XAV extension discovery, custom XCB request framing, QueryVersion and connection lifecycle.
- `client/src/devices.c`: EnumeratePhysicalDevices and bounded variable-record decoding.
- `client/src/xge.c`: standard Generic Event Extension GEQueryVersion negotiation (1.0+).
- `client/Makefile`: static-library build.
- `client/README.md`: architecture, ownership, build and staged implementation plan.
- `protocol/include/xaverius.h`: the single shared client/server wire header. The old `xaverius_proto.h` path was reconciled with the public protocol README and removed.

Transport rule: XCB's extension descriptor minor opcode is zero, leaving the X11 `data` byte zero; XAverius subopcode is encoded as the first body byte at absolute offset 4. The implementation uses XCB's client byte order for protocol scalars, copies fields into aligned host objects, and checks the 32-byte reply envelope and variable-tail bounds before exposing data. The X11 connection and event queue remain caller-owned.

The current source implements XAV QueryVersion, Physical-Device enumeration and explicit XGE 1.0+ negotiation. It has **not yet been built against the full repository header or exercised against a live XAverius server**. Event dispatch, Atom interning, remaining device/property/resource requests, logical-device creation, Vulkan ICD and presentation support are not claimed. Call `xav_connection_negotiate_xge()` successfully before selecting XAverius XGE events or issuing `CreateDevice`.


## Multi-Screen Physical-Device / Surface clarification — 2026-11-04

A spec gap was identified during client/server implementation review: choosing the first X11 Screen with XAverius support can associate a Physical Device with the wrong Screen on multi-Screen servers. The normative contract is now explicit:
- Physical-Device enumeration is server-wide, not Screen-scoped or ordered by Screen initialization.
- A Surface retains the Screen identity of its exact X11 Window; the server derives it from the Window and never selects a default/first Screen.
- Presentation support is queried for the exact logical Device / Surface pair, with per-queue-family support. The same Physical Device may present on several, some, or no Screens; no implicit device or Screen migration is permitted.
- RandR outputs are not separate X11 Screens; monitor-specific routing is outside this profile.
- Conformance cases cover two Screens/two GPUs, one GPU spanning Screens, a compute-only non-presenting GPU, enumeration-order independence, and the lack of a presentation guarantee from CreateDefaultDevice.

The client event-dispatcher work is paused until this spec clarification is reviewed and the client/server selection code follows the Surface-scoped model.


### Client-only source exclusion in the native handler CI gate — 2026-11-04

The first CI run after adding the XCB client prototype exposed a gate-scope bug: the native server-handler audit treated tracked `client/*.c` files as server request handlers and failed because the standalone client intentionally has no `compile_commands.json`. The gate now excludes only the root `client/` prototype tree while continuing to require compile-database coverage for tracked native server C/C++ sources. A regression test covers a client-only checkout; native-source-without-database and native async-callback cases remain mandatory failures.


### Shared-header CI include-path correction — 2026-11-04

After the client-only handler-gate exclusion passed, CI reached the shared-header compile and exposed a stale workflow include of the removed `xaverius_proto.h`. The canonical header is `protocol/include/xaverius.h`; the wire-layout workflow now compiles against that path. The previous CI run did not reach wire vectors or the Python suite because this compile step failed.


## Client XGE event selection and decoding — 2026-11-04

The client prototype now has:
- xav_connection_select_events(): checked 32-byte SelectEvents request, requiring successful per-connection XGE 1.0+ negotiation and returning server X11 errors to the caller.
- xav_event_decode(): non-consuming decoder for all nine registered event types. The application continues to own and poll the shared XCB event queue; unrelated events are left to the application. Unknown XAverius event IDs are surfaced with a borrowed payload view.
- Exact fixed payload-length and reserved-byte checks, host-order decoded scalar fields, and tests for every event layout.

Important XCB ABI detail: xcb_ge_generic_event_t contains full_sequence at byte 32, so XCB's in-memory event-specific payload starts at byte 36 even though the XGE wire payload starts at byte 32. The decoder accounts for that insertion. No live XAverius server has yet exercised selection or delivery; the client-side synthetic event tests are the current validation.


## Design-Agent review — multi-Screen Physical-Device / Surface contract — 2026-11-04

Reviewed the current normative text in `spec/devices.md` (Physical-Device inventory, CreateDefaultDevice, lifecycle), `spec/presentation.md` (Window identity, Screen binding, GetSurfaceCapabilities and swapchain negotiation), `spec/resource-lifetime.md`, the Physical-Device property registry, and the corresponding conformance vectors.

The existing correction is internally consistent; no additional wire request or normative change is required in this pass. The required client/server selection sequence is:

1. Enumerate the server-wide Physical-Device inventory. Do not associate an entry with a Screen based on enumeration position, initialization order, or a presumed default Screen.
2. Create the target X11 Window through core X11.
3. Create one Surface for that exact Window. The server resolves and retains both the Window resource identity and its owning X11 Screen; the client does not supply or guess a Screen number.
4. For each candidate logical Device, query `GetSurfaceCapabilities(device_xid, surface_xid)`. The result is specific to that Device's Physical Device, the retained Window/Screen, and every queue family. A successful query with no present-capable family is a valid negative result, not permission to retry against a different Screen or silently substitute another Physical Device.
5. Create the Swapchain only on a Device/Surface pair whose returned configuration and queue-family support satisfy the request. No implicit Device migration or cross-Screen presentation is permitted.

Additional cross-checks:
- `CreateDefaultDevice` is compute-baseline selection only and carries no presentation guarantee.
- A Physical Device may present on multiple Screens, a subset of Screens, or none; different Physical Devices may serve different Screens. A Screen may therefore have more than one candidate Physical Device.
- RandR outputs/monitors are not X11 Screens. Moving/resizing a Window within its Screen does not change the retained Screen association; resize affects Swapchain state as specified.
- The conformance matrix already covers two Screens/two GPUs with disjoint presentation support, one Physical Device serving both Screens, a compute-only/non-presenting Physical Device, initialization/enumeration-order independence, and the absence of a CreateDefaultDevice presentation guarantee.

Implementation follow-up (not a specification gap): the server's Physical-Device registry must be server-wide even if screen-specific backends initialize independently. The implementation must preserve one canonical server-owned Physical-Device identity for the same underlying device and must keep per-Surface presentation support separate from that inventory. Client code must not infer presentation support from enumeration or device properties; it must use the exact Surface-scoped capability query. The paused client event-dispatcher work should remain paused until its device-selection path follows this sequence.

No protocol IDs, layouts, error precedence, or normative rules were changed by this review.


## Physical-Device canonical identity, UUID and hotplug lifecycle — 2026-11-04

A cross-Screen identity audit found that the previous text prohibited duplicate identities in principle but did not define the canonicalization boundary, the limits of Vulkan UUID uniqueness, how newly connected clients learn current status, or whether a removed identity can be resurrected. The normative spec now defines:
- One server-wide canonical Physical-Device registry shared by every X11 Screen/backend discovery path. Duplicate discoveries of the same underlying device map to one identity/XID before publication; backend handles and pointers are not cross-instance keys.
- `deviceUUID` is a preferred correlation value, not an infallible globally unique key. Equal UUIDs require platform/backend identity cross-check when ambiguous; driverUUID and pipelineCacheUUID are not physical-device identity keys. An all-zero deviceUUID is invalid/NOT_AVAILABLE. If UUID is unavailable, platform/backend identity still must deduplicate.
- `XAverius.deviceStatus` (CARD32: AVAILABLE=0, UNAVAILABLE=1, REMOVED=2) lets clients connecting after a transition discover current status without depending on an earlier event. The property is a serialized server-state snapshot.
- Enumeration includes each retained identity once, including UNAVAILABLE entries and REMOVED tombstones. AVAILABLE/UNAVAILABLE may transition recoverably with the same XID; REMOVED is terminal. Tombstones and metadata remain queryable through server shutdown. A replacement after removal gets a new XID even if UUID/properties match. Physical-Device XIDs are never reused during one X-server lifetime; no cross-restart stability is promised.
- Added conformance vectors for cross-Screen duplicate discovery, UUID collision/fallback, status query after connect, hotplug/removal/replacement, and XID non-reuse.

The Vulkan UUID guidance was checked against the current Vulkan specification: deviceUUID is intended to correlate a device across instances/processes/driver APIs and is immutable for a given device, but Khronos explicitly notes that uniqueness cannot be guaranteed by conformance testing. Therefore XAverius does not equate UUID equality with proof of identity. No request opcode or fixed wire layout changed; the property registry gained one append-only property.


Follow-up to the identity audit: the `deviceStatus` conformance cases were placed in the baseline device-discovery section (not presentation-profile-only), because status and canonical identity exist independently of presentation support. The top-level property conformance summary now names all six registered properties. `tools/check-wire-layout.py` was updated from five to six property rows and now guards the canonical registry, UUID limitations, tombstone lifecycle, and XID non-reuse requirements. `CreateDefaultDevice` is explicitly restricted to AVAILABLE devices; the conformance matrix checks the no-AVAILABLE-device outcome. The old Phase 1 notes above remain historical records of the then-five-property registry and are not current requirements.


## Physical-Device registry and provider architecture — 2026-11-04

The Physical-Device identity audit now separates canonical hardware identity from backend providers and Screen attachments.

- The server MUST maintain one registry shared by all Screens and discovery paths. A DDX/driver/ICD registers a discovery/provider observation; it does not allocate a Physical-Device XID or create a Screen-local Physical Device.
- One published Physical Device uses one selected execution provider and one coherent metadata/capability snapshot. Provider selection is deterministic and fixed for that Physical-Device XID. v0.1 does not permit transparent failover to a different ICD/provider because queue families, limits, features, and object compatibility may differ.
- Linux identity guidance: resolve DRM primary/render nodes to the same DRM device; prefer canonical sysfs identity plus complete PCI BDF (or bus-specific identity), using libdrm device comparison where available. Do not key by `/dev/dri/cardN`, `renderD*`, minor number, `dev_t`, Screen index, or Vulkan handle.
- A provider becoming unavailable is not proof of hardware removal: mark the Physical Device `UNAVAILABLE`. A confirmed hardware remove is terminal `REMOVED`; re-add at the same BDF/path is a new incarnation and receives a new XID.
- Vulkan physical-device groups are not v0.1 Physical Devices. Each member remains a separate identity; v0.1 creates a logical Device from exactly one member.
- Implementation architecture recommendation: keep the registry independent of `ScreenRec`; provide a narrow server-owned registration API with opaque provider handles and immutable identity evidence. DDX drivers report observations and lifecycle changes; the registry performs deduplication and status serialization; XAverius owns protocol XID publication and query handling. Provider callbacks should be marshalled to the server's serialized event/request context, and provider/module references must outlive all dependent Vulkan objects and callbacks.

No backend implementation work is part of this specification change. The conformance vectors and static checker now require the provider, Linux hotplug, and group distinctions. Runtime behavior still requires implementation testing.


### Xlibre source-architecture observations — 2026-11-04

A source review of X11Libre/xserver's current Xorg DDX confirms that it already has a global platform-device discovery path (`xf86_platform_devices` in `xf86platformBus.c`) and DRM hotplug enumeration in `config/udev.c`. These are useful integration points, but they are not a sufficient XAverius canonical-identity registry:

- The current platform list is primarily organized around platform/DRM device nodes and Xorg entity/Screen claiming. The udev DRM path filters `card*` nodes; `xf86_find_platform_device_by_devnum()` matches major/minor numbers. Those are discovery/access-node bookkeeping, not stable GPU identity across primary/render nodes, ICDs, or hotplug generations.
- Do not simply reuse `xf86_platform_devices` as the XAverius identity table, and do not equate an Xorg Entity, `ScrnInfoRec`, `ScreenRec`, RandR output, or DRM node with a Physical Device.
- Preferred integration: feed the existing udev/platform discovery events into a separate server-wide GPU identity registry. Add a provider registration interface at a server-core boundary, then let Xorg DDX drivers register provider observations and let XAverius consume canonical registry entries. Keep the identity registry independent of Screen/Entity allocation.
- For an initial Xorg-only prototype, the registry implementation can live near the Xorg platform-device infrastructure, but its API and object model should not expose Screen-local ownership; if XAverius is intended to work with other DDX server variants, move the registry service to a DIX/server-core layer and keep Xorg discovery as one provider.
- `CreateDefaultDevice` is now explicitly Screen-independent: when several devices qualify, choose deterministically from server policy and canonical identity, never “the first Screen that supports XAverius”.

This is architecture guidance only; no Xserver source files or backend implementation were changed.


## Physical-Device registry API boundary — 2026-11-04

Added `spec/device-registry-architecture.md` and linked it from `spec/devices.md`. This records the implementation contract before backend coding:

- `PhysicalDevice`: canonical hardware incarnation, immutable published snapshot, status, provider references; registry-owned.
- `BackendProvider`: one concrete ICD/DDX/backend execution context, private Vulkan handles/ops/module lifetime; provider-manager-owned and pinned by logical Devices/async work.
- `ScreenAttachment`: generation-checked, non-owning relation between a Screen and a PhysicalDevice; Screen/DDX-owned. It conveys topology/role only, never identity or presentation support.
- One process-wide registry, independent of ScreenRec/Entity and client connections. XAverius alone maps published canonical records to server-owned Physical-Device XIDs.
- Provider discovery/selection must finish deterministically before first publication. A later provider may be attached but cannot change the selected execution provider or published metadata snapshot in v0.1.
- All registry mutation and status/XGE publication is serialized through the server event/request domain. Worker callbacks submit immutable observations; all delayed references carry object generations.
- The abstract API sketch and 12 required architecture tests are in the new document. No C implementation, Xserver source, backend, wire field, or opcode was changed.

Xorg integration findings: `xf86_platform_devices` and `config/udev.c` remain discovery inputs, not the canonical registry. The existing platform list and major/minor lookup are tied to device-node/Xorg ownership; udev currently filters DRM `card*` nodes. The new architecture explicitly prevents treating these as cross-ICD, primary/render-node, or hotplug-incarnation identity.

Remaining design point before coding: settle the concrete provider-selection configuration syntax and the exact Xserver module/ABI location for the registry service. The object model and ownership semantics are now fixed.


### Provider-selection and source-location decision — 2026-11-04

Closed the two pre-implementation architecture choices:

- **Owner/location:** the XAverius-specific registry should live with the XAverius server subsystem (initially `Xext/xaverius/registry.c`), with a private server-internal interface in an exported header such as `include/xaverius_registry.h`. Do not put Vulkan-specific policy into generic DIX, and do not make `xf86_platform_devices` the registry. Xorg common code supplies discovery/Screen-attachment adapters; a Vulkan-loader discovery provider serves configurations such as Xvfb. The header is an internal server/module interface, not a client ABI or a third-party stable ABI promise.
- **Provider preference:** allow an optional ordered list of stable provider identifiers in server configuration. During initial discovery, skip providers that cannot successfully produce a complete consistent snapshot. If no explicit preference chooses one, select the usable provider with the lexicographically lowest canonical provider key (e.g. ICD manifest identity plus configured instance slot). Never use provider registration/load order, pointer values, DRM node numbers, or Screen indices. Selection is finalized before publication and immutable for the PhysicalDevice XID lifetime.
- The exact Xorg config spelling is deliberately left to the implementation patch; the semantic contract is fixed in `spec/device-registry-architecture.md`.

No implementation source has been changed.


Registry-location clarification: the registry itself remains in the XAverius subsystem (`Xext/xaverius/`) for both Xorg and Xvfb. Only Xorg-specific platform/udev discovery adapters belong in `hw/xfree86/common/` and `config/`. Generic DIX is not made Vulkan-aware. This supersedes any earlier suggestion to place an Xorg-only registry beside `xf86platformBus.c`.


## Provider operation, error, and lifetime contract — 2026-11-04

The XAverius architecture contract now defines the provider boundary beyond discovery and identity. This is specification/architecture work only; no backend or Xserver implementation was added.

### Provider operation groups

The selected provider is responsible for:
- one coherent pre-publication physical-device snapshot;
- exact logical-device creation, queue acquisition, and logical-device destruction;
- Buffer/Memory operations;
- Shader, Descriptor, and Pipeline object operations;
- CommandPool/CommandBuffer creation, recording, reset, and destruction;
- Semaphore/Fence creation and host/device synchronization operations;
- queue submission and completion retirement;
- presentation support/capability queries for the exact Device/Surface pair, plus swapchain/acquire/present operations when the presentation profile is enabled.

The provider operation names in the architecture document are semantic, not a public ABI. The server remains responsible for all XAverius wire validation, XID/resource ownership, request ordering, error precedence, and public state transitions. Backend handles remain opaque and provider-local.

### Provider result mapping

The internal result classes are SUCCESS, UNSUPPORTED, UNAVAILABLE, DEVICE_LOST, OUT_OF_HOST_MEMORY, OUT_OF_DEVICE_MEMORY, TRANSFER_FAILURE, EXECUTION_FAILURE, CANCELLED, and FATAL. Mapping to XAverius errors is now recorded in the architecture document and cross-linked from spec/errors.md:
- During CreateDevice, backend Device Lost before a logical Device exists means PhysicalDevice UNAVAILABLE + DEVICE_UNAVAILABLE; no phantom Device/XID and no Device-Loss event.
- After logical Device creation, positive loss of that exact logical Device enters its DEVICE_LOST state machine.
- Allocation failures map to ALLOCATION_FAILED; synchronous transfer failures to TRANSFER_FAILED; accepted execution/transfer failures use their defined terminal status/event, never a delayed X11 request error.
- UNSUPPORTED after publication of the corresponding capability is a provider contract violation (INTERNAL_SERVER_ERROR), not client BadMatch, and does not mutate the published snapshot.
- Provider-context unavailability alone does not synthesize Device Loss for existing logical Devices.

### Lifetime and callback contract

- Every live logical Device pins the selected provider and exact PhysicalDevice/provider generations.
- Every asynchronous operation separately pins the provider, logical Device, queue, and all backend objects it can access until callback retirement proves backend quiescence.
- Provider callbacks carry immutable operation/device/provider/resource generations and only enqueue completion records; server-serialized state transitions decide terminal outcomes and X11 events.
- Accepted asynchronous operations get exactly one terminal outcome. First committed outcome wins against loss, destroy, timeout, and disconnect.
- DestroyDevice/disconnect invalidate public XIDs at the existing linearization point, but do not imply backend quiescence. Provider modules/contexts and backend objects remain retained or quarantined if safe release cannot be proven.
- Provider teardown is forbidden while any provider call, logical Device, accepted operation, callback, or deferred cleanup can still execute provider code or access provider objects.

### Files/commits

- spec/device-registry-architecture.md: operation groups, snapshot/create semantics, classified result contract, sync/async model, pinning/teardown rules, and architecture tests. Commits: 37010a0, 6f50455, 4c2468d.
- spec/devices.md: explicit link and CreateDevice-vs-existing-Device loss distinction. Commit: 3d07304.
- spec/errors.md: central provider-result mapping cross-reference and normative summary. Commit: fa169fc.

### Remaining review points

- Cross-check every provider operation family against the exact request chapters and ensure no v0.1 request has no provider operation owner.
- Check whether any currently synchronous request chapter can return an asynchronous provider result without defining a completion path.
- Validate that WSI provider operations cover all presentation-profile requests, including surface lifetime and swapchain teardown.
- Add/align conformance vectors for provider-result mapping and callback/lifecycle races; architecture tests 13–22 are required implementation tests, not yet executable conformance vectors.
- No runtime backend behavior or provider-quiescence mechanism has been tested. CI for the commits above has not yet been verified.


### Provider contract review follow-up — 2026-11-04

The request registry and the actual command-recording, synchronization, memory/buffer, and presentation chapters were cross-checked against the provider operation inventory. The architecture contract was tightened accordingly:

- Added provider candidate enumeration, physical snapshot query, exact logical-device creation, queue acquisition, and logical-device teardown.
- Added explicit operation coverage for every backend-facing request family: Buffer/Memory; Shader/Descriptor/Pipeline; CommandPool/CommandBuffer and command entries; Semaphore/Fence; QueueSubmit; and presentation.
- Corrected the command chapter reference to spec/command-recording.md.
- Deferred reply operations are asynchronous too, not only accepted QueueSubmit-style work. This explicitly includes WriteBuffer, ReadBuffer, nonzero-timeout WaitSemaphores/WaitForFence, and AcquireNextImage. Provider wait registrations use operation tokens; the server owns timeout arbitration and never blocks the X11 dispatcher.
- Added a distinct provider STATUS result for request-defined non-error outcomes such as TIMEOUT, OUT_OF_DATE, SURFACE_LOST, SUBOPTIMAL, and UNSUPPORTED_CONFIGURATION. The request chapter remains authoritative for exact status values.
- Provider unavailability for an existing logical Device maps requests that need the unavailable provider to DEVICE_UNAVAILABLE, without changing the logical Device identity or synthesizing DEVICE_LOST. Already accepted operations use their own terminal failure channel unless exact logical-Device loss is positively established.
- WSI surface objects are provider/instance-scoped, not logical-Device-scoped. The same XAverius Surface queried through different providers gets separate provider-local surface objects, each pinned to its provider and exact Window/Screen generation. No WSI handle crosses provider instances.
- Added architecture tests 23–24 for multi-provider Surface isolation and server-owned wait timeout arbitration.

Additional commits:
- d3f5c59 — complete command and WSI operation inventory; correct command-recording chapter path.
- cc8dc15 — deferred operations, provider STATUS results, and provider-unavailability semantics.
- 9546459 — provider-scoped WSI surface lifetimes.
- f97c0be — provider candidate enumeration and host semaphore signal operations.
- 73e163d — WSI isolation and deferred-wait architecture tests.

The operation inventory is an internal semantic contract, not a stable C ABI. The abstract C sketch is illustrative; implementations must use typed wrappers and preserve the stated ownership/result/callback semantics.


### Final provider API consistency pass — 2026-11-04

- Provider API now explicitly exposes candidate enumeration, physical snapshot query, logical Device create/get-queue/destroy, typed object-family operation tables, queue submission, provider-scoped WSI surface operations, swapchain/acquire/present operations, and lifecycle/refcount hooks.
- Removed a duplicate async-operation sentence and duplicate sync operation pointers from the illustrative base ops table; Buffer/Memory, Shader/Pipeline, Command, and Synchronization functions are represented by separate typed operation tables.
- Provider wait registrations carry operation tokens; they do not receive a provider-owned timeout. The X server owns WaitSemaphores/WaitForFence deadlines and first-terminal-outcome arbitration.
- The exact same XAverius Surface can be used with Devices from multiple providers, but each provider owns a separate VkSurface/WSI object tied to the Window/Screen generation. This follows the presentation chapter's cross-Device Surface semantics.
- Latest architecture/API consistency commits: 8b8ae12 and 3d508e6.
- GitHub status and workflow-run queries for the coordination commit returned empty lists. CI is unverified; no claim of passing tests is made.

- Final consistency correction: provider STATUS examples no longer imply that provider waits own X11 timeout deadlines; WaitSemaphores/WaitForFence timeout arbitration remains server-owned. Commit: 2dca851.


## Provider contract audit follow-up — 2026-11-04

A complete cross-check against request subopcodes 0–47 and the authoritative chapters for devices, memory/buffers, shaders/pipelines, command recording, queue submission, synchronization, events, and presentation found and corrected several interface-level ambiguities. No request opcode or wire layout changed.

### Corrections

- Backend destroy operations now return classified provider results. Their failures cannot undo public XID invalidation or create delayed protocol errors; the affected backend objects/provider context remain quarantined until safe retirement.
- The completion sink is now an explicit field of GpuProviderDescriptor. Completion records carry non-reusable provider/operation/token generations; the server-side token record retains the complete Device/resource-generation set. Completion payloads must be copied by the enqueue-only sink before the callback returns.
- Provider-operation token acceptance is explicitly distinguished from XAverius protocol acceptance. QueueSubmit is protocol-accepted after its void request is accepted; QueuePresent is protocol-accepted after its SUCCESS reply. WriteBuffer, ReadBuffer, WaitSemaphores, WaitForFence, and AcquireNextImage remain reply-pending and retain their request-specific final reply/status/error channel despite internal provider-token acceptance. This resolves the generic delayed-X11-error wording against the request-specific contracts.
- query_surface_support now receives the provider's physical-device handle and queue-family index, matching the Vulkan physical-device surface-support query model; it does not incorrectly attempt to query support through a logical VkDevice.
- Host-wait and acquire cancellation are explicit provider operations. Cancellation is not quiescence and cannot release references by itself. A late successful acquire after the server timeout must be safely returned to the swapchain or quarantined; a provider unable to guarantee this cannot advertise presentation support.
- Provider token retirement itself returns a classified result; failed retirement preserves/quarantines the token and provider context.

### Conformance additions

spec/conformance.md now includes provider-injection integration vectors for:
- CreateDevice loss/allocation failure and atomic non-publication;
- provider unavailable versus exact logical-Device loss and recovery;
- published capability returning UNSUPPORTED;
- QueueSubmit/QueuePresent protocol acceptance versus reply-pending provider operations;
- duplicate/late callbacks, destroy failures, wait cancellation, and late image acquisition after timeout.

### Commits

- cfb5d46 — provider callback, destroy, and acquire-cancellation contract.
- 6fb40fe — provider-result and callback-lifetime conformance vectors.
- 30a215d — pointer-safe completion identity.
- d125c6f — provider-token versus protocol-acceptance semantics.
- e98b69f — central error-chapter acceptance clarification.
- 384c66e — conformance vectors aligned with protocol acceptance.
- 901c63b — generation-safe completion token and classified retirement.
- 28d85c8 — typed completion sink in provider descriptor.

### Remaining review points

- Re-run the entire provider-operation inventory against the final request registry after these corrections, including SelectEvents and generic DestroyResource ownership boundaries.
- Review the provider result taxonomy against every request-specific error/status mapping; especially ensure provider STATUS is never used to override server-owned timeout decisions.
- Run the repository wire checker, wire vectors, Python suite, and exact-tip CI. The documentation changes above have not yet been verified by CI.
- Runtime backend conformance, including safe WSI late-acquire retirement and provider unload/quiescence, remains untested.
