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
| **Ship A** | Common wire framing and dispatch integration (no ownership of device request handlers) | `Xext/xaverius/` | `rfc/xaverius-core-protocol` |
| **Ship B** | `EnumeratePhysicalDevices` (subopcode 1) only | `Xext/xaverius/` | `rfc/xaverius-devices` |
| **Ship C** | `GetPhysicalDeviceProperty` (2) and `GetPhysicalDeviceQueueFamilyProperties` (3) only | `Xext/xaverius/` | `rfc/xaverius-device-props` |
| **Ship D** | Device Lifecycle (4, 5, 6) | `Xext/xaverius/` | `rfc/xaverius-device-lifecycle` |
| **Ship E** | `GetPhysicalDeviceMemoryProperties` (subopcode 7) only | `Xext/xaverius/` | `rfc/xaverius-memory-props` |

### Shared integration ownership (must be confirmed before shared-file edits)

The request-handler split above is the coordination baseline. It does not assign ownership of shared helpers. Ship A must name the integration owner and publish/agree the interfaces for common dispatch, Physical-Device XID lookup, client ownership checks, and shared device metadata before ships make overlapping changes. Until that owner/interface is recorded, ships MUST NOT independently modify the same shared helper or header; submit the required interface in this file first.

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