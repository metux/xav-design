"""Regression vectors for QueueSubmit versus resource destruction commits."""
from __future__ import annotations

import unittest

from xa_state_model import (
    BufferMemoryLifetime,
    CommandBufferLifecycle,
    CommandBufferModel,
    DescriptorPoolLifetime,
    DescriptorSetLifetime,
    SubmissionModel,
    SubmitRequest,
    destroy_buffer_lifetime,
    destroy_command_pool,
    destroy_descriptor_pool,
    finish_submission,
    free_descriptor_sets,
    queue_submit,
)


class QueueSubmitCommandPoolRaceTests(unittest.TestCase):
    def test_submit_first_makes_pool_destroy_reject_pending_child(self) -> None:
        command_buffer = CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
        state = SubmissionModel(command_buffers=[command_buffer])
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=2101, command_buffer_indices=(0,))),
            "SUCCESS",
        )
        self.assertEqual(destroy_command_pool([command_buffer]), "INVALID_SYNCHRONIZATION_STATE")
        self.assertTrue(command_buffer.buffer_live)
        self.assertEqual(command_buffer.lifecycle, CommandBufferLifecycle.PENDING)
        self.assertEqual(state.accepted_tokens, {2101})

    def test_pool_destroy_first_makes_later_submit_fail_without_token_use(self) -> None:
        command_buffer = CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
        state = SubmissionModel(command_buffers=[command_buffer])
        self.assertEqual(destroy_command_pool([command_buffer]), "SUCCESS")
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=2102, command_buffer_indices=(0,))),
            "BadValue",
        )
        self.assertEqual(state.accepted_tokens, set())
        self.assertEqual(command_buffer.lifecycle, CommandBufferLifecycle.EXECUTABLE)


class QueueSubmitDescriptorPoolRaceTests(unittest.TestCase):
    def shared_state(self):
        descriptor_set = DescriptorSetLifetime()
        command_buffer = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.EXECUTABLE,
            descriptor_sets=[descriptor_set],
        )
        descriptor_set.executable_refs = [command_buffer]
        pool = DescriptorPoolLifetime(sets=[descriptor_set])
        state = SubmissionModel(command_buffers=[command_buffer])
        return state, pool, descriptor_set, command_buffer

    def test_submit_first_makes_pool_destroy_reject_pending_set(self) -> None:
        state, pool, descriptor_set, command_buffer = self.shared_state()
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=2201, command_buffer_indices=(0,))),
            "SUCCESS",
        )
        self.assertEqual(descriptor_set.pending_submission_refs, 1)
        self.assertEqual(destroy_descriptor_pool(pool), "INVALID_SYNCHRONIZATION_STATE")
        self.assertTrue(pool.xid_valid)
        self.assertTrue(descriptor_set.live)
        self.assertEqual(command_buffer.lifecycle, CommandBufferLifecycle.PENDING)
        self.assertEqual(state.accepted_tokens, {2201})

    def test_pool_destroy_first_invalidates_executable_command_buffer(self) -> None:
        state, pool, descriptor_set, command_buffer = self.shared_state()
        self.assertEqual(destroy_descriptor_pool(pool), "SUCCESS")
        self.assertFalse(pool.xid_valid)
        self.assertFalse(descriptor_set.live)
        self.assertEqual(command_buffer.lifecycle, CommandBufferLifecycle.INVALID)
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=2202, command_buffer_indices=(0,))),
            "INVALID_SYNCHRONIZATION_STATE",
        )
        self.assertEqual(state.accepted_tokens, set())

    def test_submit_first_makes_free_descriptor_sets_reject_pending_set(self) -> None:
        state, _pool, descriptor_set, command_buffer = self.shared_state()
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=2203, command_buffer_indices=(0,))),
            "SUCCESS",
        )
        self.assertEqual(free_descriptor_sets([descriptor_set]), "INVALID_SYNCHRONIZATION_STATE")
        self.assertTrue(descriptor_set.live)
        self.assertEqual(command_buffer.lifecycle, CommandBufferLifecycle.PENDING)

    def test_free_descriptor_sets_first_invalidates_executable_command_buffer(self) -> None:
        state, _pool, descriptor_set, command_buffer = self.shared_state()
        self.assertEqual(free_descriptor_sets([descriptor_set]), "SUCCESS")
        self.assertFalse(descriptor_set.live)
        self.assertEqual(command_buffer.lifecycle, CommandBufferLifecycle.INVALID)
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=2204, command_buffer_indices=(0,))),
            "INVALID_SYNCHRONIZATION_STATE",
        )
        self.assertEqual(state.accepted_tokens, set())


class QueueSubmitBufferDestroyRaceTests(unittest.TestCase):
    def test_submit_first_blocks_buffer_destruction(self) -> None:
        buffer = BufferMemoryLifetime(identity="buffer-A")
        command_buffer = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.EXECUTABLE,
            indirect_buffer_refs={"buffer-A"},
        )
        buffer.executable_refs = [command_buffer]
        state = SubmissionModel(command_buffers=[command_buffer], buffer_registry=[buffer])
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=2301, command_buffer_indices=(0,))),
            "SUCCESS",
        )
        self.assertEqual(buffer.accepted_uses, 1)
        self.assertEqual(destroy_buffer_lifetime(buffer), "INVALID_SYNCHRONIZATION_STATE")
        self.assertTrue(buffer.xid_valid)
        self.assertEqual(command_buffer.lifecycle, CommandBufferLifecycle.PENDING)
        self.assertEqual(state.accepted_tokens, {2301})

    def test_buffer_destroy_first_invalidates_executable_command_buffer(self) -> None:
        buffer = BufferMemoryLifetime(identity="buffer-B")
        command_buffer = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.EXECUTABLE,
            indirect_buffer_refs={"buffer-B"},
        )
        buffer.executable_refs = [command_buffer]
        state = SubmissionModel(command_buffers=[command_buffer], buffer_registry=[buffer])
        self.assertEqual(destroy_buffer_lifetime(buffer), "SUCCESS")
        self.assertFalse(buffer.xid_valid)
        self.assertEqual(command_buffer.lifecycle, CommandBufferLifecycle.INVALID)
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=2302, command_buffer_indices=(0,))),
            "INVALID_SYNCHRONIZATION_STATE",
        )
        self.assertEqual(state.accepted_tokens, set())


if __name__ == "__main__":
    unittest.main()
