"""Executable precedence and atomicity tests for the XAverius state model."""
from __future__ import annotations

import copy
import unittest

from xa_state_model import (
    ImageState,
    PresentRequest,
    PresentState,
    WaitState,
    queue_present,
    CommandBufferLifecycle,
    CommandBufferChunk,
    CommandBufferModel,
    ShaderAssemblyState,
    ShaderChunk,
    SubmissionModel,
    SubmitRequest,
    command_buffer_data,
    queue_submit,
    shader_module_data,
)


class QueuePresentStateModelTests(unittest.TestCase):
    def state(self, **changes) -> PresentState:
        state = PresentState(
            valid_wait_xids=(True, True),
            wait_states=[WaitState.READY, WaitState.READY],
        )
        for name, value in changes.items():
            setattr(state, name, value)
        return state

    def assert_rejected_atomically(
        self, state: PresentState, request: PresentRequest, expected: str
    ) -> None:
        before = copy.deepcopy(state)
        result = queue_present(state, request)
        self.assertEqual((result.result, result.accepted), (expected, False))
        self.assertEqual(state, before, "rejected request mutated model state")

    def test_wire_length_beats_every_other_failure(self) -> None:
        state = self.state(
            device_lost=True,
            valid_device_xid=False,
            surface_lost=True,
        )
        self.assert_rejected_atomically(
            state, PresentRequest(wire_length_valid=False), "BadLength"
        )

    def test_scalar_syntax_beats_xids_and_device_loss(self) -> None:
        state = self.state(device_lost=True, valid_device_xid=False)
        self.assert_rejected_atomically(
            state, PresentRequest(token=0), "BadValue"
        )

    def test_unknown_xid_beats_device_loss(self) -> None:
        state = self.state(device_lost=True, valid_swapchain_xid=False)
        self.assert_rejected_atomically(state, PresentRequest(), "BadValue")

    def test_type_ownership_beats_device_loss(self) -> None:
        state = self.state(device_lost=True, correct_types_and_ownership=False)
        self.assert_rejected_atomically(state, PresentRequest(), "BadMatch")

    def test_device_loss_beats_queue_and_lifecycle(self) -> None:
        state = self.state(
            device_lost=True,
            valid_queue=False,
            surface_lost=True,
            out_of_date=True,
        )
        self.assert_rejected_atomically(state, PresentRequest(), "DEVICE_LOST")

    def test_queue_index_error_beats_surface_lifecycle(self) -> None:
        state = self.state(valid_image_index=False, surface_lost=True)
        self.assert_rejected_atomically(state, PresentRequest(), "BadValue")

    def test_surface_loss_beats_out_of_date_and_token_reuse(self) -> None:
        state = self.state(
            surface_lost=True,
            out_of_date=True,
            accepted_tokens={1},
        )
        self.assert_rejected_atomically(state, PresentRequest(token=1), "SURFACE_LOST")

    def test_out_of_date_beats_token_reuse(self) -> None:
        state = self.state(out_of_date=True, accepted_tokens={1})
        self.assert_rejected_atomically(state, PresentRequest(token=1), "OUT_OF_DATE")

    def test_no_present_support_beats_token_reuse(self) -> None:
        state = self.state(present_supported=False, accepted_tokens={1})
        self.assert_rejected_atomically(state, PresentRequest(token=1), "BadMatch")

    def test_token_reuse_beats_image_and_wait_state(self) -> None:
        state = self.state(
            accepted_tokens={1},
            image_state=ImageState.AVAILABLE,
            wait_states=[WaitState.INCOMPATIBLE, WaitState.READY],
        )
        self.assert_rejected_atomically(
            state, PresentRequest(token=1, wait_indices=(0,)), "BadValue"
        )

    def test_image_state_beats_wait_eligibility(self) -> None:
        state = self.state(
            image_state=ImageState.AVAILABLE,
            wait_states=[WaitState.INCOMPATIBLE, WaitState.READY],
        )
        self.assert_rejected_atomically(
            state, PresentRequest(wait_indices=(0,)), "INVALID_SYNCHRONIZATION_STATE"
        )

    def test_untrusted_wait_fails_without_reserving_anything(self) -> None:
        state = self.state(wait_states=[WaitState.READY, WaitState.UNTRUSTED])
        self.assert_rejected_atomically(
            state, PresentRequest(wait_indices=(0, 1)), "DEPENDENCY_FAILED"
        )

    def test_rejected_token_can_be_retried_and_is_not_reserved(self) -> None:
        state = self.state(image_state=ImageState.AVAILABLE)
        first = queue_present(state, PresentRequest(token=7))
        self.assertEqual(first.result, "INVALID_SYNCHRONIZATION_STATE")
        self.assertNotIn(7, state.accepted_tokens)
        state.image_state = ImageState.ACQUIRED
        second = queue_present(state, PresentRequest(token=7))
        self.assertEqual(second.result, "SUCCESS")
        self.assertIn(7, state.accepted_tokens)

    def test_success_commits_token_waits_and_image_together(self) -> None:
        state = self.state()
        before = copy.deepcopy(state)
        result = queue_present(state, PresentRequest(token=9, wait_indices=(0, 1)))
        self.assertEqual((result.result, result.accepted), ("SUCCESS", True))
        self.assertEqual(state.image_state, ImageState.PRESENT_PENDING)
        self.assertIn(9, state.accepted_tokens)
        self.assertEqual(state.wait_states, [WaitState.RESERVED, WaitState.RESERVED])
        self.assertEqual(len(state.accepted_tokens - before.accepted_tokens), 1)

    def test_independent_lifecycle_change_is_not_rolled_back(self) -> None:
        # The lifecycle change is already serialized before request validation.
        state = self.state(surface_lost=True, image_state=ImageState.INVALID)
        before = copy.deepcopy(state)
        self.assert_rejected_atomically(
            state, PresentRequest(), "SURFACE_LOST"
        )
        self.assertEqual(state, before)
        self.assertEqual(state.image_state, ImageState.INVALID)


class ShaderModuleDataModelTests(unittest.TestCase):
    def test_single_create_final_and_chunk_concatenation(self) -> None:
        single = ShaderAssemblyState()
        self.assertEqual(shader_module_data(single, ShaderChunk(data=b"abc", create=True, final=True)), "SUCCESS")
        self.assertEqual(single.module_code, b"abc")
        multi = ShaderAssemblyState()
        self.assertEqual(shader_module_data(multi, ShaderChunk(data=b"ab", create=True)), "SUCCESS")
        self.assertEqual(shader_module_data(multi, ShaderChunk(data=b"cd", final=True)), "SUCCESS")
        self.assertEqual(multi.module_code, b"abcd")
        self.assertFalse(multi.assembly_active)

    def test_bad_chunk_discards_entire_shader_assembly(self) -> None:
        state = ShaderAssemblyState()
        shader_module_data(state, ShaderChunk(data=b"prefix", create=True))
        self.assertEqual(shader_module_data(state, ShaderChunk(data=b"bad", chunk_valid=False)), "BadValue")
        self.assertEqual((state.assembly_active, state.assembly, state.module_live), (False, b"", False))
        self.assertEqual(shader_module_data(state, ShaderChunk(data=b"tail", final=True)), "INVALID_SYNCHRONIZATION_STATE")

    def test_device_loss_terminates_assembly_and_abort_cannot_revive_it(self) -> None:
        state = ShaderAssemblyState(device_lost=True)
        # Device-loss rejects further chunks and clears the partial assembly.
        state.assembly_active, state.assembly = True, b"partial"
        self.assertEqual(shader_module_data(state, ShaderChunk(abort=True)), "DEVICE_LOST")
        self.assertEqual((state.assembly_active, state.assembly), (False, b""))

    def test_abort_without_matching_assembly_is_rejected(self) -> None:
        state = ShaderAssemblyState()
        before = copy.deepcopy(state)
        self.assertEqual(shader_module_data(state, ShaderChunk(abort=True)), "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual(state, before)

    def test_second_create_cannot_reuse_assembly_xid(self) -> None:
        state = ShaderAssemblyState()
        self.assertEqual(shader_module_data(state, ShaderChunk(data=b"part", create=True)), "SUCCESS")
        before = copy.deepcopy(state)
        self.assertEqual(shader_module_data(state, ShaderChunk(data=b"other", create=True)), "BadIDChoice")
        self.assertEqual(state, before)

    def test_empty_data_chunk_is_bad_value_before_xid_lookup(self) -> None:
        state = ShaderAssemblyState(xid_valid=False)
        before = copy.deepcopy(state)
        self.assertEqual(shader_module_data(state, ShaderChunk(data=b"")), "BadValue")
        self.assertEqual(state, before)

    def test_final_allocation_failure_does_not_publish_module(self) -> None:
        state = ShaderAssemblyState()
        shader_module_data(state, ShaderChunk(data=b"part", create=True))
        self.assertEqual(shader_module_data(state, ShaderChunk(data=b"tail", final=True, allocation_ok=False)), "ALLOCATION_FAILED")
        self.assertFalse(state.module_live)
        self.assertFalse(state.assembly_active)


class CommandBufferDataModelTests(unittest.TestCase):
    def test_failed_append_preserves_prior_chunks_and_final_state(self) -> None:
        state = CommandBufferModel()
        self.assertEqual(command_buffer_data(state, CommandBufferChunk(operation="CREATE", entries=(b"a",))), "SUCCESS")
        before = copy.deepcopy(state)
        self.assertEqual(command_buffer_data(state, CommandBufferChunk(entries=(b"b",), entries_valid=False)), "BadValue")
        self.assertEqual(state, before)
        self.assertEqual(command_buffer_data(state, CommandBufferChunk(operation="FINAL", entries=(b"c",), entries_valid=False)), "BadValue")
        self.assertEqual(state, before)

    def test_entry_validation_precedes_target_xid_resolution(self) -> None:
        state = CommandBufferModel(device_lost=True)
        before = copy.deepcopy(state)
        self.assertEqual(
            command_buffer_data(state, CommandBufferChunk(operation="CREATE", target_xid_available=False, entries_valid=False)),
            "BadValue",
        )
        self.assertEqual(state, before)

    def test_malformed_entry_precedes_target_xid_resolution(self) -> None:
        state = CommandBufferModel()
        self.assertEqual(
            command_buffer_data(state, CommandBufferChunk(operation="CREATE", target_xid_available=False, entries_well_formed=False)),
            "BadLength",
        )

    def test_abort_checks_parent_pool_even_after_device_loss(self) -> None:
        state = CommandBufferModel(
            device_lost=True, lifecycle=CommandBufferLifecycle.RECORDING,
            entries=[b"x"], pool_matches_buffer=False,
        )
        before = copy.deepcopy(state)
        self.assertEqual(command_buffer_data(state, CommandBufferChunk(operation="ABORT")), "BadMatch")
        self.assertEqual(state, before)

    def test_single_create_final_is_executable(self) -> None:
        state = CommandBufferModel()
        self.assertEqual(
            command_buffer_data(state, CommandBufferChunk(operation="CREATE_FINAL", entries=(b"one",))),
            "SUCCESS",
        )
        self.assertEqual(state.lifecycle, CommandBufferLifecycle.EXECUTABLE)
        self.assertEqual(state.entries, [b"one"])

    def test_abort_resets_recording_buffer_and_discards_entries(self) -> None:
        state = CommandBufferModel()
        command_buffer_data(state, CommandBufferChunk(operation="CREATE", entries=(b"a", b"b")))
        self.assertEqual(command_buffer_data(state, CommandBufferChunk(operation="ABORT")), "SUCCESS")
        self.assertEqual((state.lifecycle, state.entries), (CommandBufferLifecycle.INITIAL, []))

    def test_abort_allowed_after_device_loss_but_not_pending(self) -> None:
        state = CommandBufferModel(device_lost=True, lifecycle=CommandBufferLifecycle.RECORDING, entries=[b"x"])
        self.assertEqual(command_buffer_data(state, CommandBufferChunk(operation="ABORT")), "SUCCESS")
        state.lifecycle = CommandBufferLifecycle.PENDING
        before = copy.deepcopy(state)
        self.assertEqual(command_buffer_data(state, CommandBufferChunk(operation="ABORT")), "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual(state, before)

    def test_final_commits_executable_only_after_valid_chunk(self) -> None:
        state = CommandBufferModel()
        command_buffer_data(state, CommandBufferChunk(operation="CREATE", entries=(b"first",)))
        self.assertEqual(command_buffer_data(state, CommandBufferChunk(operation="FINAL", entries=(b"last",))), "SUCCESS")
        self.assertEqual(state.lifecycle, CommandBufferLifecycle.EXECUTABLE)
        self.assertEqual(state.entries, [b"first", b"last"])


class QueueSubmitAtomicityTests(unittest.TestCase):
    def state(self, **changes) -> SubmissionModel:
        state = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY, WaitState.READY],
            signal_slots=[None, None],
        )
        for name, value in changes.items():
            setattr(state, name, value)
        return state

    def assert_atomic_rejection(self, state: SubmissionModel, request: SubmitRequest, expected: str) -> None:
        before = copy.deepcopy(state)
        self.assertEqual(queue_submit(state, request), expected)
        self.assertEqual(state, before, "rejected submission partially mutated state")

    def test_reused_token_precedes_xid_type_and_device_errors(self) -> None:
        state = self.state(
            accepted_tokens={7}, xids_valid=False, types_and_ownership_valid=False,
            device_lost=True,
        )
        self.assert_atomic_rejection(state, SubmitRequest(token=7), "BadValue")

    def test_queue_xid_precedes_device_loss(self) -> None:
        state = self.state(device_lost=True, queue_xid_valid=False)
        self.assert_atomic_rejection(state, SubmitRequest(), "BadValue")

    def test_fence_state_precedes_command_buffer_state(self) -> None:
        state = self.state(
            fence_state_valid=False,
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.RECORDING)],
        )
        self.assert_atomic_rejection(state, SubmitRequest(attach_fence=True), "INVALID_SYNCHRONIZATION_STATE")

    def test_late_invalid_signal_rejects_all_reservations(self) -> None:
        state = self.state(signal_slots=[None, 9])
        self.assert_atomic_rejection(state, SubmitRequest(signal_values=(5, 8)), "INVALID_SYNCHRONIZATION_STATE")

    def test_device_loss_precedes_command_buffer_state_after_xid_checks(self) -> None:
        state = self.state(device_lost=True, command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.RECORDING)])
        self.assert_atomic_rejection(state, SubmitRequest(), "DEVICE_LOST")

    def test_unknown_xid_precedes_device_loss(self) -> None:
        state = self.state(device_lost=True, xids_valid=False)
        self.assert_atomic_rejection(state, SubmitRequest(), "BadValue")

    def test_invalid_command_buffer_does_not_reserve_token_waits_fence_or_signals(self) -> None:
        state = self.state(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.RECORDING)],
            wait_states=[WaitState.READY, WaitState.READY],
        )
        self.assert_atomic_rejection(
            state, SubmitRequest(wait_indices=(0,), signal_values=(3, 4), attach_fence=True),
            "INVALID_SYNCHRONIZATION_STATE",
        )

    def test_success_commits_all_submission_state_together(self) -> None:
        state = self.state()
        result = queue_submit(state, SubmitRequest(token=42, wait_indices=(0, 1), signal_values=(2, 7), attach_fence=True))
        self.assertEqual(result, "SUCCESS")
        self.assertEqual(state.command_buffers[0].lifecycle, CommandBufferLifecycle.PENDING)
        self.assertEqual(state.wait_states, [WaitState.RESERVED, WaitState.RESERVED])
        self.assertEqual(state.signal_slots, [2, 7])
        self.assertEqual(state.accepted_tokens, {42})
        self.assertEqual(state.pending_submissions, [42])
        self.assertTrue(state.fence_attached)

    def test_rejected_token_can_be_retried_after_fixing_state(self) -> None:
        state = self.state(command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.RECORDING)])
        request = SubmitRequest(token=9)
        self.assertEqual(queue_submit(state, request), "INVALID_SYNCHRONIZATION_STATE")
        state.command_buffers[0].lifecycle = CommandBufferLifecycle.EXECUTABLE
        self.assertEqual(queue_submit(state, request), "SUCCESS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
