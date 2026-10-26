"""Device-loss regressions for concurrent accepted resource references."""
from __future__ import annotations

import unittest

from xa_state_model import (
    BufferMemoryLifetime,
    CommandBufferLifecycle,
    CommandBufferModel,
    DescriptorSetLifetime,
    SubmissionModel,
    SubmitRequest,
    finish_submission,
    queue_submit,
)


class DeviceLossAcceptedResourceReferenceTests(unittest.TestCase):
    def shared_state(self):
        buffer = BufferMemoryLifetime(descriptor_slot_refs=1)
        descriptor_set = DescriptorSetLifetime(slots={0: buffer.identity})
        command_buffers = [
            CommandBufferModel(
                lifecycle=CommandBufferLifecycle.EXECUTABLE,
                descriptor_sets=[descriptor_set],
                indirect_buffer_refs={buffer.identity},
            )
            for _ in range(2)
        ]
        state = SubmissionModel(
            command_buffers=command_buffers,
            buffer_registry=[buffer],
        )
        return state, descriptor_set, buffer

    def test_late_callbacks_after_device_loss_release_only_their_refs(self) -> None:
        state, descriptor_set, buffer = self.shared_state()
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=901, command_buffer_indices=(0,), attach_fence=True)),
            "SUCCESS",
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=902, command_buffer_indices=(1,))),
            "SUCCESS",
        )
        self.assertEqual((descriptor_set.pending_submission_refs, buffer.accepted_uses), (2, 2))

        # Device loss terminalizes work as failure, but cannot prove backend
        # quiescence. Resource references therefore remain until each callback.
        state.device_lost = True
        self.assertEqual(finish_submission(state, 902, success=True), "SUCCESS")
        self.assertEqual((descriptor_set.pending_submission_refs, buffer.accepted_uses), (1, 1))
        self.assertEqual(state.command_buffers[1].lifecycle, CommandBufferLifecycle.INVALID)
        self.assertEqual(state.fence_status, "PENDING")

        self.assertEqual(finish_submission(state, 901, success=True), "SUCCESS")
        self.assertEqual((descriptor_set.pending_submission_refs, buffer.accepted_uses), (0, 0))
        self.assertEqual(state.command_buffers[0].lifecycle, CommandBufferLifecycle.INVALID)
        self.assertEqual(state.fence_status, "FAILED")

        # A duplicate callback cannot underflow either reference count.
        self.assertEqual(finish_submission(state, 901, success=False), "BadValue")
        self.assertEqual((descriptor_set.pending_submission_refs, buffer.accepted_uses), (0, 0))


if __name__ == "__main__":
    unittest.main()
