# Pipeline, descriptor, and command-buffer lifetime audit — 2026-10-30

## Scope

Reviewed the current candidate commit `1da4495b30c31f5406bc8928a974db9ef4eeadb8` across:

- `spec/shaders-pipelines.md`
- `spec/command-recording.md`
- `spec/queue-submission.md`
- `spec/resource-lifetime.md`
- `spec/errors.md` and the resource-related sections of `spec/conformance.md)
- The command-buffer, descriptor, buffer-reference, submission, and callback reference models.

## Semantic consistency results

- A command buffer retains a DescriptorSet object, not a frozen copy of its slots. Descriptor updates are serialized against submission acceptance and release; derived Buffer-reference edges follow the committed slot contents.
- A resource referenced by a RECORDING command buffer blocks ordinary destruction. Successful destruction of a resource referenced by a non-pending EXECUTABLE command buffer invalidates that command buffer atomically. Rejected destruction leaves the full state unchanged.
- An accepted submission owns references independently of the command buffer's recorded references. Terminalization, reset, invalidation, pool/device teardown, and backend-quiescence cleanup cannot release the same edge twice.
- A Pipeline retains the exact internal PipelineLayout identity used at creation. Public PipelineLayout destruction may proceed despite that Pipeline-held dependency, but direct recording references and direct accepted uses remain blockers. The existing Pipeline remains valid; new Pipeline creation through the invalid XID is rejected.
- A DescriptorSet retains the immutable DescriptorSetLayout definition/backend identity needed for validation and updates. Public layout invalidation prevents new PipelineLayout/Set creation through the old XID but does not invalidate existing Sets. Internal layout release waits for dependent Sets and backend access to end.
- DescriptorPool and FreeDescriptorSets operations validate the complete target set collection and all blockers before atomically invalidating XIDs, invalidating executable command buffers, and retiring owned references.
- QueueSubmit acceptance and descriptor update/free operations share a serialization boundary; a submission sees either the complete old descriptor contents or the complete new contents, never a partial batch.
- Device loss and late callbacks cannot turn a terminal failure into success, publish stale semaphore/fence state, or release backend holds before quiescence.

## Coverage improvement

The normative rules were consistent, but the reference-model suite did not have focused tests for the two retained-layout distinctions. Added:

- `tests/test_pipeline_layout_lifetime.py`: seven regressions for PipelineLayout public invalidation with live Pipelines, direct RECORDING/Pending blockers, executable-reference invalidation, DescriptorSetLayout invalidation with allocated Sets, continued Set updates, delayed backend-layout release, and exactly-once Set release.
- Two explicit conformance vectors in `spec/conformance.md` covering PipelineLayout and DescriptorSetLayout retained dependencies.

## Outcome

No new normative contradiction or unresolved v0.1 design decision was found. The identified test-coverage gap is closed by the new reference-model tests and conformance vectors. This review changes no wire assignment or protocol behavior.

Runtime implementation acceptance remains open: live X11/XGE interoperability, real Vulkan compute and memory-visibility behavior, runtime concurrency/Device-loss teardown, and presentation backend validation if implemented.

## CI evidence

[CI run 41085895794](https://github.com/metux/xav-design/actions/runs/41085895794) passed on candidate commit `1da4495b30c31f5406bc8928a974db9ef4eeadb8`. The wire-layout job completed all required steps, including the full Python suite (665 tests), Timeline regressions (72 tests), wire-layout validation, and required-check presence audit. This is static/reference-model evidence, not live server/backend validation.
