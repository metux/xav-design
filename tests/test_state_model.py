"""Executable precedence and atomicity tests for the XAverius state model."""
from __future__ import annotations

import copy
import unittest

from xa_state_model import (
    ImageState,
    BinarySignalState,
    PresentRequest,
    PresentState,
    WaitState,
    SemaphoreKind,
    queue_present,
    finish_present_wait,
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
    finish_submission,
    reset_fence,
)


class QueuePresentStateModelTests(unittest.TestCase):
    def present_state(self, **changes) -> PresentState:
        state = PresentState(
            valid_wait_xids=(True, True),
            wait_states=[WaitState.READY, WaitState.READY],
        )
        for name, value in changes.items():
            setattr(state, name, value)
        return state

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

    def test_target_xid_precedes_semantic_entry_validation(self) -> None:
        state = CommandBufferModel(device_lost=True)
        before = copy.deepcopy(state)
        self.assertEqual(
            command_buffer_data(state, CommandBufferChunk(operation="CREATE", target_xid_available=False, entries_valid=False)),
            "BadIDChoice",
        )
        self.assertEqual(state, before)

    def test_device_loss_precedes_buffer_lifecycle_after_resource_checks(self) -> None:
        state = CommandBufferModel(
            device_lost=True, lifecycle=CommandBufferLifecycle.INITIAL,
        )
        self.assertEqual(
            command_buffer_data(state, CommandBufferChunk(operation="FINAL")),
            "DEVICE_LOST",
        )

    def test_malformed_entry_precedes_target_xid_resolution(self) -> None:
        state = CommandBufferModel()
        self.assertEqual(
            command_buffer_data(state, CommandBufferChunk(operation="CREATE", scalar_valid=False, target_xid_available=False, entries_well_formed=False)),
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
            signal_counters=[0, 0],
        )
        for name, value in changes.items():
            setattr(state, name, value)
        return state

    def assert_atomic_rejection(self, state: SubmissionModel, request: SubmitRequest, expected: str) -> None:
        before = copy.deepcopy(state)
        self.assertEqual(queue_submit(state, request), expected)
        self.assertEqual(state, before, "rejected submission partially mutated state")

    def test_counts_length_precedes_scalar_and_xid_errors(self) -> None:
        state = self.state(xids_valid=False, scalar_valid=False)
        self.assert_atomic_rejection(state, SubmitRequest(counts_valid=False), "BadLength")

    def test_reused_token_precedes_xid_type_and_device_errors(self) -> None:
        state = self.state(
            accepted_tokens={7}, xids_valid=False, types_and_ownership_valid=False,
            device_lost=True,
        )
        self.assert_atomic_rejection(state, SubmitRequest(token=7), "BadValue")

    def test_bad_command_buffer_index_precedes_device_loss(self) -> None:
        state = self.state(device_lost=True)
        self.assert_atomic_rejection(
            state, SubmitRequest(command_buffer_indices=(99,)), "BadValue"
        )

    def test_queue_xid_precedes_device_loss(self) -> None:
        state = self.state(device_lost=True, queue_xid_valid=False)
        self.assert_atomic_rejection(state, SubmitRequest(), "BadValue")

    def test_type_ownership_precedes_device_loss(self) -> None:
        state = self.state(device_lost=True, types_and_ownership_valid=False)
        self.assert_atomic_rejection(state, SubmitRequest(), "BadMatch")

    def test_timeline_wait_rejects_values_outside_unsigned_64_bit_range(self) -> None:
        for value in (-1, 0x10000000000000000):
            with self.subTest(value=value):
                state = self.state(
                    semaphore_kinds=[SemaphoreKind.TIMELINE, SemaphoreKind.BINARY],
                    signal_counters=[3, 0],
                )
                self.assert_atomic_rejection(
                    state,
                    SubmitRequest(wait_indices=(0,), wait_values=(value,)),
                    "BadValue",
                )

    def test_timeline_signal_rejects_values_outside_unsigned_64_bit_range(self) -> None:
        for value in (-1, 0x10000000000000000):
            with self.subTest(value=value):
                state = self.state(
                    semaphore_kinds=[SemaphoreKind.TIMELINE, SemaphoreKind.TIMELINE],
                    signal_counters=[0, 0],
                )
                self.assert_atomic_rejection(
                    state,
                    SubmitRequest(signal_indices=(0,), signal_values=(value,)),
                    "BadValue",
                )

    def test_timeline_wait_may_target_value_not_yet_reached(self) -> None:
        state = self.state(
            semaphore_kinds=[SemaphoreKind.TIMELINE, SemaphoreKind.BINARY],
            signal_counters=[3, 0],
        )
        result = queue_submit(
            state, SubmitRequest(token=10, wait_indices=(0,), wait_values=(9,))
        )
        self.assertEqual(result, "SUCCESS")
        self.assertEqual(state.pending_timeline_waits, [(10, 0, 9)])
        self.assertEqual(state.wait_states[0], WaitState.READY)

    def test_concurrent_timeline_waits_can_share_same_future_target(self) -> None:
        state = self.state(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE),
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE),
            ],
            semaphore_kinds=[SemaphoreKind.TIMELINE, SemaphoreKind.BINARY],
            signal_counters=[2, 0],
        )
        first = queue_submit(
            state, SubmitRequest(token=11, command_buffer_indices=(0,),
                                 wait_indices=(0,), wait_values=(8,))
        )
        second = queue_submit(
            state, SubmitRequest(token=12, command_buffer_indices=(1,),
                                 wait_indices=(0,), wait_values=(8,))
        )
        self.assertEqual((first, second), ("SUCCESS", "SUCCESS"))
        self.assertEqual(
            state.pending_timeline_waits, [(11, 0, 8), (12, 0, 8)]
        )

    def test_later_timeline_signal_must_exceed_existing_reservation(self) -> None:
        state = self.state(
            semaphore_kinds=[SemaphoreKind.TIMELINE, SemaphoreKind.TIMELINE],
            signal_slots=[None, 12],
            signal_counters=[0, 0],
        )
        self.assert_atomic_rejection(
            state, SubmitRequest(signal_indices=(1,), signal_values=(11,)),
            "BadValue",
        )

    def test_binary_signal_and_wait_cycle_requires_actual_consumption(self) -> None:
        state = self.state(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
                for _ in range(4)
            ],
            wait_states=[WaitState.READY],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=101, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        self.assertEqual(state.binary_signal_states, [BinarySignalState.SIGNAL_PENDING])
        before = copy.deepcopy(state)
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=102, command_buffer_indices=(1,),
                                              signal_indices=(0,), signal_values=(0,))),
            "INVALID_SYNCHRONIZATION_STATE",
        )
        self.assertEqual(state, before)
        self.assertEqual(finish_submission(state, 101, success=True), "SUCCESS")
        self.assertEqual(state.binary_signal_states, [BinarySignalState.SIGNALED])
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=103, command_buffer_indices=(1,),
                                              signal_indices=(0,), signal_values=(0,))),
            "INVALID_SYNCHRONIZATION_STATE",
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=104, command_buffer_indices=(1,),
                                              wait_indices=(0,))),
            "SUCCESS",
        )
        self.assertEqual(state.binary_signal_states, [BinarySignalState.SIGNALED])
        before = copy.deepcopy(state)
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=105, command_buffer_indices=(2,),
                                              wait_indices=(0,))),
            "INVALID_SYNCHRONIZATION_STATE",
        )
        self.assertEqual(state, before)
        self.assertEqual(finish_submission(state, 104, success=True), "SUCCESS")
        self.assertEqual(state.binary_signal_states, [BinarySignalState.UNSIGNALED])
        self.assertEqual(state.wait_states, [WaitState.READY])
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=106, command_buffer_indices=(2,),
                                              signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )

    def test_binary_wait_before_signal_consumes_signal_even_if_callbacks_reverse(self) -> None:
        state = self.state(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
                for _ in range(3)
            ],
            wait_states=[WaitState.READY],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=110, command_buffer_indices=(0,),
                                              wait_indices=(0,))),
            "SUCCESS",
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=111, command_buffer_indices=(1,),
                                              signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        self.assertEqual(finish_submission(state, 110, success=True), "SUCCESS")
        self.assertEqual(state.binary_signal_states, [BinarySignalState.UNSIGNALED])
        self.assertEqual(state.consumed_pending_binary_signals, {(111, 0)})
        self.assertEqual(finish_submission(state, 111, success=True), "SUCCESS")
        self.assertEqual(state.binary_signal_states, [BinarySignalState.UNSIGNALED])
        self.assertEqual(state.consumed_pending_binary_signals, set())

    def test_failed_binary_operation_makes_uncertain_payload_untrusted(self) -> None:
        state = self.state(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
                for _ in range(3)
            ],
            wait_states=[WaitState.READY],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=120, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        self.assertEqual(finish_submission(state, 120, success=False), "SUCCESS")
        self.assertEqual(state.binary_signal_states, [BinarySignalState.UNTRUSTED])
        for token, op in (
            (121, SubmitRequest(token=121, wait_indices=(0,))),
            (122, SubmitRequest(token=122, command_buffer_indices=(1,),
                                signal_indices=(0,), signal_values=(0,))),
        ):
            before = copy.deepcopy(state)
            self.assertEqual(queue_submit(state, op), "DEPENDENCY_FAILED")
            self.assertEqual(state, before)

    def test_present_wait_reservation_is_released_only_when_wait_is_terminal(self) -> None:
        state = self.present_state(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNALED],
        )
        result = queue_present(state, PresentRequest(token=130, wait_indices=(0,)))
        self.assertEqual((result.result, result.accepted), ("SUCCESS", True))
        before = copy.deepcopy(state)
        duplicate = queue_present(state, PresentRequest(token=131, wait_indices=(0,)))
        self.assertEqual((duplicate.result, duplicate.accepted),
                         ("INVALID_SYNCHRONIZATION_STATE", False))
        self.assertEqual(state, before)
        self.assertEqual(finish_present_wait(state, 130, 0, consumed=False), "SUCCESS")
        self.assertEqual(state.binary_signal_states, [BinarySignalState.SIGNALED])
        self.assertEqual(state.wait_states, [WaitState.READY])
        self.assertEqual(
            queue_present(state, PresentRequest(token=132, wait_indices=(0,))).result,
            "SUCCESS",
        )

    def test_present_wait_unknown_payload_marks_semaphore_untrusted(self) -> None:
        state = self.present_state(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNALED],
        )
        self.assertTrue(queue_present(state, PresentRequest(token=140, wait_indices=(0,))).accepted)
        self.assertEqual(finish_present_wait(state, 140, 0, consumed=None), "SUCCESS")
        self.assertEqual(state.binary_signal_states, [BinarySignalState.UNTRUSTED])
        self.assertEqual(
            queue_present(state, PresentRequest(token=141, wait_indices=(0,))).result,
            "DEPENDENCY_FAILED",
        )

    def test_binary_semaphore_nonzero_wait_value_is_bad_value(self) -> None:
        state = self.state(semaphore_kinds=[SemaphoreKind.BINARY, SemaphoreKind.BINARY])
        self.assert_atomic_rejection(
            state, SubmitRequest(wait_indices=(0,), wait_values=(1,)), "BadValue"
        )

    def test_binary_semaphore_nonzero_signal_value_is_bad_value(self) -> None:
        state = self.state(semaphore_kinds=[SemaphoreKind.BINARY, SemaphoreKind.BINARY])
        self.assert_atomic_rejection(
            state, SubmitRequest(signal_indices=(0,), signal_values=(1,)), "BadValue"
        )

    def test_binary_semaphore_signal_slot_must_be_available(self) -> None:
        state = self.state(
            semaphore_kinds=[SemaphoreKind.BINARY, SemaphoreKind.BINARY],
            signal_slots=[1, None],
        )
        self.assert_atomic_rejection(
            state, SubmitRequest(signal_indices=(0,), signal_values=(0,)),
            "INVALID_SYNCHRONIZATION_STATE",
        )

    def test_reserved_wait_stage_bits_precede_xid_resolution(self) -> None:
        state = self.state(xids_valid=False)
        self.assert_atomic_rejection(
            state, SubmitRequest(wait_indices=(0,), wait_stage_masks=(0x10,)), "BadValue"
        )

    def test_unsupported_wait_stage_follows_device_loss(self) -> None:
        state = self.state(
            device_lost=True, queue_supported_stage_mask=0x4,
        )
        self.assert_atomic_rejection(
            state, SubmitRequest(wait_indices=(0,), wait_stage_masks=(0x2,)), "DEVICE_LOST"
        )

    def test_unsupported_wait_stage_rejected_after_device_check(self) -> None:
        state = self.state(queue_supported_stage_mask=0x4)
        self.assert_atomic_rejection(
            state, SubmitRequest(wait_indices=(0,), wait_stage_masks=(0x2,)),
            "INVALID_SYNCHRONIZATION_STATE",
        )

    def test_same_semaphore_in_wait_and_signal_arrays_is_bad_value(self) -> None:
        state = self.state()
        self.assert_atomic_rejection(
            state,
            SubmitRequest(wait_indices=(0,), signal_indices=(0,), signal_values=(1,)),
            "BadValue",
        )

    def test_signal_count_mismatch_is_bad_length(self) -> None:
        state = self.state(scalar_valid=False, xids_valid=False)
        self.assert_atomic_rejection(
            state, SubmitRequest(signal_indices=(0,), signal_values=()), "BadLength"
        )

    def test_fence_state_precedes_command_buffer_state(self) -> None:
        state = self.state(
            fence_state_valid=False,
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.RECORDING)],
        )
        self.assert_atomic_rejection(state, SubmitRequest(attach_fence=True), "INVALID_SYNCHRONIZATION_STATE")

    def test_late_invalid_signal_rejects_all_reservations(self) -> None:
        state = self.state(signal_slots=[None, 9])
        self.assert_atomic_rejection(state, SubmitRequest(signal_indices=(0, 1), signal_values=(5, 8)), "BadValue")

    def test_timeline_signal_not_above_current_counter_is_bad_value(self) -> None:
        state = self.state(signal_counters=[6, 0])
        self.assert_atomic_rejection(
            state, SubmitRequest(signal_indices=(0,), signal_values=(6,)), "BadValue"
        )

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
            state, SubmitRequest(wait_indices=(0,), signal_indices=(0, 1), signal_values=(3, 4), attach_fence=True),
            "INVALID_SYNCHRONIZATION_STATE",
        )

    def test_success_commits_all_submission_state_together(self) -> None:
        state = self.state()
        result = queue_submit(state, SubmitRequest(token=42, wait_indices=(0, 1), signal_indices=(0, 1), signal_values=(2, 7), attach_fence=True))
        self.assertEqual(result, "SUCCESS")
        self.assertEqual(state.command_buffers[0].lifecycle, CommandBufferLifecycle.PENDING)
        self.assertEqual(state.wait_states, [WaitState.RESERVED, WaitState.RESERVED])
        self.assertEqual(state.signal_slots, [2, 7])
        self.assertEqual(state.accepted_tokens, {42})
        self.assertEqual(state.pending_submissions, [42])
        self.assertTrue(state.fence_attached)

    def test_fence_cannot_be_attached_twice_and_requires_reset_after_completion(self) -> None:
        state = self.state()
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=70, attach_fence=True)),
            "SUCCESS",
        )
        self.assertEqual(state.fence_status, "PENDING")
        self.assertTrue(state.fence_attached)
        self.assertFalse(state.fence_state_valid)
        before = copy.deepcopy(state)
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=71, attach_fence=True)),
            "INVALID_SYNCHRONIZATION_STATE",
        )
        self.assertEqual(state, before)

        self.assertEqual(finish_submission(state, 70, success=True), "SUCCESS")
        self.assertEqual(state.fence_status, "SIGNALED")
        self.assertFalse(state.fence_attached)
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=72, attach_fence=True)),
            "INVALID_SYNCHRONIZATION_STATE",
        )
        self.assertEqual(reset_fence(state), "SUCCESS")
        self.assertEqual(state.fence_status, "UNSIGNALED")
        self.assertTrue(state.fence_state_valid)
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=73, attach_fence=True)),
            "SUCCESS",
        )

    def test_failed_submission_sets_fence_failed_and_reset_recovers_it(self) -> None:
        state = self.state()
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=80, attach_fence=True)),
            "SUCCESS",
        )
        self.assertEqual(finish_submission(state, 80, success=False), "SUCCESS")
        self.assertEqual(state.fence_status, "FAILED")
        self.assertFalse(state.fence_attached)
        self.assertEqual(reset_fence(state), "SUCCESS")
        self.assertEqual(state.fence_status, "UNSIGNALED")

    def test_reset_fence_rejects_nonterminal_and_device_lost_states_atomically(self) -> None:
        state = self.state(fence_status="PENDING", fence_attached=True,
                           fence_state_valid=False)
        before = copy.deepcopy(state)
        self.assertEqual(reset_fence(state), "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual(state, before)
        lost = self.state(device_lost=True, fence_status="SIGNALED",
                          fence_state_valid=False)
        before_lost = copy.deepcopy(lost)
        self.assertEqual(reset_fence(lost), "DEVICE_LOST")
        self.assertEqual(lost, before_lost)

    def test_rejected_token_can_be_retried_after_fixing_state(self) -> None:
        state = self.state(command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.RECORDING)])
        request = SubmitRequest(token=9)
        self.assertEqual(queue_submit(state, request), "INVALID_SYNCHRONIZATION_STATE")
        state.command_buffers[0].lifecycle = CommandBufferLifecycle.EXECUTABLE
        self.assertEqual(queue_submit(state, request), "SUCCESS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
