# QueueSubmit versus resource destruction audit — 2026-10-30

## Scope

Reviewed the serialized acceptance and destruction paths at candidate commit `a812e55c2e902c05aee8806383ef7b60a7421257` across `spec/queue-submission.md`, `spec/command-recording.md`, `spec/resource-lifetime.md`, `spec/shaders-pipelines.md`, `spec/memory-buffers.md`, `spec/synchronization.md`, `spec/errors.md`, `spec/conformance.md`, and the queue-submit/resource-lifetime reference models.

## Findings and corrections

The individual pending-use and atomic-acceptance rules were present, but the cross-operation contract did not state the two competing commit orders uniformly for `QueueSubmit` versus resource destruction/release. Added a normative serialization rule to `spec/queue-submission.md`:

- If submission acceptance commits first, its pending-use markers and reservations are visible to destruction; the type-specific destroy/free request rejects atomically.
- If destruction commits first, invalidated directly named XIDs fail normal XID resolution with `BadValue`; a still-live command buffer invalidated because of a destroyed recorded dependency fails its mutable-state check with `INVALID_SYNCHRONIZATION_STATE`.
- A rejected submission consumes no token, creates no submission, reserves no synchronization state, and retains no submission references.
- The rule follows type-specific pending-use semantics rather than treating every internal dependency as a public pending-use blocker. A Pipeline-held PipelineLayout dependency and a DescriptorSet-held DescriptorSetLayout definition remain valid after public layout-XID invalidation.

Added explicit two-order conformance vectors for `DestroyCommandPool`, `DestroyDescriptorPool`, `FreeDescriptorSets`, Buffer/Pipeline destruction, Fence/Semaphore destruction, and the retained PipelineLayout/DescriptorSetLayout cases.

Added eight reference-model regressions in `tests/test_submission_destroy_races.py` for both orders of command-pool, descriptor-pool, descriptor-set, and Buffer destruction versus QueueSubmit.

The first CI attempt exposed a reference-model omission: `queue_submit` resolved command-buffer array indices but did not reject a command buffer whose public XID had already been invalidated by `DestroyCommandPool`. The model now checks command-buffer liveness in the XID-resolution phase, before type/state validation and before Device/mutable-state phases. This matches the normative rule; the follow-up CI run passes.

## Outcome

The cross-operation acceptance/destruction ordering is now explicit and covered for the primary object classes. No wire assignment changed. Device-wide `DestroyDevice` and client-disconnect cascades remain separate lifecycle operations and retain their previously specified ability to invalidate public XIDs despite pending work, while accepted work is terminalized and internally retained safely.

The new reference tests do not model a real multithreaded server; they verify both serial commit orders and atomic externally observable state.

## CI evidence

[CI run 41086491269](https://github.com/metux/xav-design/actions/runs/41086491269) passed on candidate commit `a812e55c2e902c05aee8806383ef7b60a7421257`: 4,696 wire-layout/documentation checks, 72 Timeline regression tests, 673 Python tests, and all required-check presence steps passed. Runtime X11/Vulkan acceptance remains separate.
