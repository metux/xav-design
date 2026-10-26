"""Executable precedence and atomicity tests for the XAverius state model."""
from __future__ import annotations

import copy
import unittest

from xa_state_model import (
    ImageState,
    BinarySignalState,
    SharedBinarySemaphore,
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
    reset_command_buffer,
    destroy_command_pool,
    queue_submit,
    shader_module_data,
    finish_submission,
    signal_timeline_host,
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
        self.assertEqual(shader_module_data(single, ShaderChunk(data=b"abcd", create=True, final=True)), "SUCCESS")
        self.assertEqual(single.module_code, b"abcd")
        multi = ShaderAssemblyState()
        self.assertEqual(shader_module_data(multi, ShaderChunk(data=b"ab", create=True)), "SUCCESS")
        self.assertEqual(shader_module_data(multi, ShaderChunk(data=b"cd", final=True)), "SUCCESS")
        self.assertEqual(multi.module_code, b"abcd")
        self.assertFalse(multi.assembly_active)

    def test_final_shader_validation_and_assembled_size_fail_atomically(self) -> None:
        single = ShaderAssemblyState()
        self.assertEqual(
            shader_module_data(single, ShaderChunk(data=b"abc", create=True, final=True)),
            "BadValue",
        )
        self.assertFalse(single.module_live)
        self.assertIsNone(single.module_code)

        invalid = ShaderAssemblyState()
        self.assertEqual(
            shader_module_data(invalid, ShaderChunk(data=b"abcd", create=True, final=True, module_valid=False)),
            "BadValue",
        )
        self.assertFalse(invalid.module_live)
        self.assertIsNone(invalid.module_code)

        bounded = ShaderAssemblyState(max_assembled_size=4)
        self.assertEqual(shader_module_data(bounded, ShaderChunk(data=b"ab", create=True)), "SUCCESS")
        before = copy.deepcopy(bounded)
        self.assertEqual(shader_module_data(bounded, ShaderChunk(data=b"cde", final=True)), "BadValue")
        self.assertFalse(bounded.assembly_active)
        self.assertEqual(bounded.assembly, b"")
        self.assertFalse(bounded.module_live)
        self.assertNotEqual(bounded, before)

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

    def test_semantic_entry_validation_precedes_target_xid_resolution(self) -> None:
        state = CommandBufferModel(device_lost=True)
        before = copy.deepcopy(state)
        self.assertEqual(
            command_buffer_data(state, CommandBufferChunk(operation="CREATE", target_xid_available=False, entries_valid=False)),
            "BadValue",
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
    def present_state(self, **changes) -> PresentState:
        state = PresentState(
            valid_wait_xids=(True, True),
            wait_states=[WaitState.READY, WaitState.READY],
        )
        for name, value in changes.items():
            setattr(state, name, value)
        return state

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

    def test_queue_mismatch_precedes_device_loss(self) -> None:
        state = self.state(device_lost=True, queue_xid_valid=False)
        self.assert_atomic_rejection(state, SubmitRequest(), "BadMatch")

    def test_unknown_resource_xid_precedes_queue_mismatch(self) -> None:
        state = self.state(queue_xid_valid=False)
        self.assert_atomic_rejection(
            state, SubmitRequest(command_buffer_indices=(99,)), "BadValue"
        )

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

    def test_timeline_signal_value_validation_follows_device_validation(self) -> None:
        state = self.state(
            device_lost=True,
            semaphore_kinds=[SemaphoreKind.TIMELINE, SemaphoreKind.TIMELINE],
            signal_counters=[0, 0],
        )
        self.assert_atomic_rejection(
            state,
            SubmitRequest(signal_indices=(0,), signal_values=(0x10000000000000000,)),
            "DEVICE_LOST",
        )
        state = self.state(
            types_and_ownership_valid=False,
            semaphore_kinds=[SemaphoreKind.TIMELINE, SemaphoreKind.TIMELINE],
            signal_counters=[0, 0],
        )
        self.assert_atomic_rejection(
            state,
            SubmitRequest(signal_indices=(0,), signal_values=(0x10000000000000000,)),
            "BadMatch",
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

    def test_wait_entries_are_validated_in_array_order(self) -> None:
        state = self.state(
            semaphore_kinds=[SemaphoreKind.BINARY, SemaphoreKind.BINARY],
            wait_states=[WaitState.UNTRUSTED, WaitState.READY],
        )
        self.assert_atomic_rejection(
            state,
            SubmitRequest(
                wait_indices=(0, 1), wait_values=(0, 1),
                wait_stage_masks=(0x1, 0x1),
            ),
            "DEPENDENCY_FAILED",
        )

    def test_signal_entries_are_validated_in_array_order(self) -> None:
        state = self.state(
            semaphore_kinds=[SemaphoreKind.BINARY, SemaphoreKind.BINARY],
            binary_signal_states=[
                BinarySignalState.SIGNALED, BinarySignalState.UNSIGNALED,
            ],
        )
        self.assert_atomic_rejection(
            state,
            SubmitRequest(signal_indices=(0, 1), signal_values=(0, 1)),
            "INVALID_SYNCHRONIZATION_STATE",
        )

    def test_signal_entry_value_error_precedes_generic_dependency_failure(self) -> None:
        state = self.state(
            dependencies_valid=False,
            semaphore_kinds=[SemaphoreKind.TIMELINE, SemaphoreKind.TIMELINE],
            signal_counters=[0, 0],
        )
        self.assert_atomic_rejection(
            state,
            SubmitRequest(signal_indices=(0,), signal_values=(0x10000000000000000,)),
            "BadValue",
        )

    def test_signal_entry_state_error_precedes_generic_dependency_failure(self) -> None:
        state = self.state(
            dependencies_valid=False,
            semaphore_kinds=[SemaphoreKind.BINARY, SemaphoreKind.BINARY],
            binary_signal_states=[BinarySignalState.SIGNALED],
        )
        self.assert_atomic_rejection(
            state,
            SubmitRequest(signal_indices=(0,), signal_values=(0,)),
            "INVALID_SYNCHRONIZATION_STATE",
        )

    def test_generic_dependency_failure_follows_valid_signal_entries(self) -> None:
        state = self.state(
            dependencies_valid=False,
            semaphore_kinds=[SemaphoreKind.TIMELINE, SemaphoreKind.TIMELINE],
            signal_counters=[0, 0],
        )
        self.assert_atomic_rejection(
            state,
            SubmitRequest(signal_indices=(0,), signal_values=(5,)),
            "DEPENDENCY_FAILED",
        )

    def test_timeline_wait_value_validation_follows_device_validation(self) -> None:
        state = self.state(
            device_lost=True,
            semaphore_kinds=[SemaphoreKind.TIMELINE, SemaphoreKind.BINARY],
            signal_counters=[3, 0],
        )
        self.assert_atomic_rejection(
            state,
            SubmitRequest(wait_indices=(0,), wait_values=(-1,)),
            "DEVICE_LOST",
        )
        state = self.state(
            types_and_ownership_valid=False,
            semaphore_kinds=[SemaphoreKind.TIMELINE, SemaphoreKind.BINARY],
            signal_counters=[3, 0],
        )
        self.assert_atomic_rejection(
            state,
            SubmitRequest(wait_indices=(0,), wait_values=(-1,)),
            "BadMatch",
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
            pending_timeline_signals=[(99, 1, 12)],
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
            (121, SubmitRequest(token=121, command_buffer_indices=(1,), wait_indices=(0,))),
            (122, SubmitRequest(token=122, command_buffer_indices=(1,),
                                signal_indices=(0,), signal_values=(0,))),
        ):
            before = copy.deepcopy(state)
            self.assertEqual(queue_submit(state, op), "DEPENDENCY_FAILED")
            self.assertEqual(state, before)

    def test_failed_binary_signal_with_proven_unchanged_payload_restores_unsignaled(self) -> None:
        state = self.state(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
                for _ in range(2)
            ],
            wait_states=[WaitState.READY],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=150, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        self.assertEqual(
            finish_submission(
                state, 150, success=False,
                binary_payload_unchanged={("signal", 0)},
            ),
            "SUCCESS",
        )
        self.assertEqual(state.binary_signal_states, [BinarySignalState.UNSIGNALED])
        self.assertEqual(state.wait_states, [WaitState.READY])
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=151, command_buffer_indices=(1,),
                                              signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )

    def test_failed_binary_wait_with_proven_unchanged_payload_preserves_signal(self) -> None:
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
            queue_submit(state, SubmitRequest(token=160, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        self.assertEqual(finish_submission(state, 160, success=True), "SUCCESS")
        self.assertEqual(state.binary_signal_states, [BinarySignalState.SIGNALED])
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=161, command_buffer_indices=(1,),
                                              wait_indices=(0,))),
            "SUCCESS",
        )
        self.assertEqual(
            finish_submission(
                state, 161, success=False,
                binary_payload_unchanged={("wait", 0)},
            ),
            "SUCCESS",
        )
        self.assertEqual(state.binary_signal_states, [BinarySignalState.SIGNALED])
        self.assertEqual(state.wait_states, [WaitState.READY])
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=162, command_buffer_indices=(2,),
                                              wait_indices=(0,))),
            "SUCCESS",
        )

    def test_present_wait_reservation_is_released_only_when_wait_is_terminal(self) -> None:
        state = PresentState(
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
        state.image_state = ImageState.ACQUIRED  # independent image-release callback
        self.assertEqual(
            queue_present(state, PresentRequest(token=132, wait_indices=(0,))).result,
            "SUCCESS",
        )

    def test_present_consumes_shared_pending_submit_signal_once(self) -> None:
        shared = SharedBinarySemaphore()
        submit = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(submit, SubmitRequest(token=185, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        self.assertEqual(shared.signal_state, BinarySignalState.SIGNAL_PENDING)
        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            shared_semaphores=[shared],
        )
        self.assertTrue(queue_present(present, PresentRequest(token=186, wait_indices=(0,))).accepted)
        self.assertEqual(finish_present_wait(present, 186, 0, consumed=True), "SUCCESS")
        self.assertTrue(shared.signal_consumed)
        self.assertEqual(finish_submission(submit, 185, success=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertIsNone(shared.signal_reservation)
        self.assertFalse(shared.signal_consumed)

    def test_device_loss_and_unknown_present_callback_preserve_untrusted_state_submit_last(self) -> None:
        shared = SharedBinarySemaphore()
        submit = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(submit, SubmitRequest(token=194, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            shared_semaphores=[shared],
        )
        self.assertTrue(queue_present(present, PresentRequest(token=195, wait_indices=(0,))).accepted)

        # Present completes with an unknown payload first; Device Loss then
        # races the still-pending Submit callback, which arrives last.
        self.assertEqual(finish_present_wait(present, 195, 0, consumed=None), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)
        submit.device_lost = True
        self.assertEqual(finish_submission(submit, 194, success=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)
        self.assertIsNone(shared.signal_reservation)
        self.assertIsNone(shared.wait_reservation)

    def test_device_loss_submit_callback_first_then_unknown_present_callback(self) -> None:
        shared = SharedBinarySemaphore()
        submit = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(submit, SubmitRequest(token=196, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            shared_semaphores=[shared],
        )
        self.assertTrue(queue_present(present, PresentRequest(token=197, wait_indices=(0,))).accepted)

        # Reverse the callback order: Submit observes Device Loss first.
        submit.device_lost = True
        self.assertEqual(finish_submission(submit, 196, success=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)
        self.assertEqual(finish_present_wait(present, 197, 0, consumed=None), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)
        self.assertIsNone(shared.signal_reservation)
        self.assertIsNone(shared.wait_reservation)

    def test_device_loss_callback_preserves_present_consumption_of_pending_submit_signal(self) -> None:
        shared = SharedBinarySemaphore()
        submit = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(submit, SubmitRequest(token=190, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            shared_semaphores=[shared],
        )
        self.assertTrue(queue_present(present, PresentRequest(token=191, wait_indices=(0,))).accepted)
        self.assertEqual(finish_present_wait(present, 191, 0, consumed=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)

        # The Device-Loss notification wins over a late backend success.
        submit.device_lost = True
        self.assertEqual(finish_submission(submit, 190, success=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertIsNone(shared.signal_reservation)
        self.assertIsNone(shared.wait_reservation)
        self.assertFalse(shared.signal_consumed)

    def test_device_loss_releases_submit_wait_reservation_for_shared_present_state(self) -> None:
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED)
        submit = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(submit, SubmitRequest(token=192, wait_indices=(0,))),
            "SUCCESS",
        )
        submit.device_lost = True
        self.assertEqual(finish_submission(submit, 192, success=True), "SUCCESS")
        self.assertIsNone(shared.wait_reservation)
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)

        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNTRUSTED],
            shared_semaphores=[shared],
        )
        before = copy.deepcopy(present)
        result = queue_present(present, PresentRequest(token=193, wait_indices=(0,)))
        self.assertEqual((result.result, result.accepted), ("DEPENDENCY_FAILED", False))
        self.assertEqual(present, before)
        self.assertIsNone(shared.wait_reservation)

    def test_queue_submit_wait_conflicts_with_pending_queue_present_wait(self) -> None:
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED)
        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNALED],
            shared_semaphores=[shared],
        )
        self.assertTrue(queue_present(present, PresentRequest(token=170, wait_indices=(0,))).accepted)
        self.assertEqual(shared.wait_reservation, ("present", 170))

        submit = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        before = copy.deepcopy(submit)
        self.assertEqual(
            queue_submit(submit, SubmitRequest(token=171, wait_indices=(0,))),
            "INVALID_SYNCHRONIZATION_STATE",
        )
        self.assertEqual(submit, before)
        self.assertEqual(shared.wait_reservation, ("present", 170))

    def test_queue_present_wait_conflicts_with_pending_queue_submit_wait(self) -> None:
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED)
        submit = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(submit, SubmitRequest(token=180, wait_indices=(0,))),
            "SUCCESS",
        )
        self.assertEqual(shared.wait_reservation, ("submit", 180))

        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNALED],
            shared_semaphores=[shared],
        )
        before = copy.deepcopy(present)
        result = queue_present(present, PresentRequest(token=181, wait_indices=(0,)))
        self.assertEqual((result.result, result.accepted),
                         ("INVALID_SYNCHRONIZATION_STATE", False))
        self.assertEqual(present, before)
        self.assertEqual(shared.wait_reservation, ("submit", 180))

    def test_present_wait_unknown_payload_marks_semaphore_untrusted(self) -> None:
        state = self.present_state(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNALED],
        )
        self.assertTrue(queue_present(state, PresentRequest(token=140, wait_indices=(0,))).accepted)
        self.assertEqual(finish_present_wait(state, 140, 0, consumed=None), "SUCCESS")
        self.assertEqual(state.binary_signal_states, [BinarySignalState.UNTRUSTED])
        state.image_state = ImageState.ACQUIRED  # let semaphore validation be reached
        self.assertEqual(
            queue_present(state, PresentRequest(token=141, wait_indices=(0,))).result,
            "DEPENDENCY_FAILED",
        )

    def test_binary_semaphore_nonzero_wait_value_is_bad_value(self) -> None:
        state = self.state(semaphore_kinds=[SemaphoreKind.BINARY, SemaphoreKind.BINARY])
        self.assert_atomic_rejection(
            state, SubmitRequest(wait_indices=(0,), wait_values=(1,)), "BadValue"
        )

    def test_binary_wait_value_precedes_unsupported_stage_and_wait_state(self) -> None:
        state = self.state(
            queue_supported_stage_mask=0x1,
            semaphore_kinds=[SemaphoreKind.BINARY, SemaphoreKind.BINARY],
            wait_states=[WaitState.UNTRUSTED, WaitState.READY],
        )
        self.assert_atomic_rejection(
            state,
            SubmitRequest(wait_indices=(0,), wait_values=(1,), wait_stage_masks=(0x2,)),
            "BadValue",
        )

    def test_binary_semaphore_nonzero_signal_value_is_bad_value(self) -> None:
        state = self.state(semaphore_kinds=[SemaphoreKind.BINARY, SemaphoreKind.BINARY])
        self.assert_atomic_rejection(
            state, SubmitRequest(signal_indices=(0,), signal_values=(1,)), "BadValue"
        )

    def test_binary_signal_value_precedes_untrusted_signal_state(self) -> None:
        state = self.state(
            semaphore_kinds=[SemaphoreKind.BINARY, SemaphoreKind.BINARY],
            binary_signal_states=[BinarySignalState.UNTRUSTED],
        )
        self.assert_atomic_rejection(
            state,
            SubmitRequest(signal_indices=(0,), signal_values=(1,)),
            "BadValue",
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
        state = self.state(
            signal_slots=[None, 9],
            pending_timeline_signals=[(98, 1, 9)],
        )
        self.assert_atomic_rejection(
            state, SubmitRequest(signal_indices=(0, 1), signal_values=(5, 8)),
            "BadValue",
        )

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
            wait_states=[WaitState.READY, WaitState.READY, WaitState.READY],
            semaphore_kinds=[SemaphoreKind.TIMELINE, SemaphoreKind.TIMELINE, SemaphoreKind.BINARY],
        )
        self.assert_atomic_rejection(
            state, SubmitRequest(command_buffer_indices=(0,), wait_indices=(2,), signal_indices=(0, 1), signal_values=(3, 4), attach_fence=True),
            "INVALID_SYNCHRONIZATION_STATE",
        )

    def test_success_commits_all_submission_state_together(self) -> None:
        state = self.state(
            wait_states=[WaitState.READY, WaitState.READY, WaitState.READY, WaitState.READY],
            semaphore_kinds=[SemaphoreKind.TIMELINE, SemaphoreKind.TIMELINE, SemaphoreKind.BINARY, SemaphoreKind.BINARY],
        )
        result = queue_submit(state, SubmitRequest(token=42, command_buffer_indices=(0,), wait_indices=(2, 3), signal_indices=(0, 1), signal_values=(2, 7), attach_fence=True))
        self.assertEqual(result, "SUCCESS")
        self.assertEqual(state.command_buffers[0].lifecycle, CommandBufferLifecycle.PENDING)
        self.assertEqual(state.wait_states, [WaitState.READY, WaitState.READY, WaitState.RESERVED, WaitState.RESERVED])
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


    def test_duplicate_submit_terminal_callback_after_device_loss_is_noop(self) -> None:
        shared = SharedBinarySemaphore()
        state = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=201, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        self.assertEqual(finish_submission(state, 201, success=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.SIGNALED)

        # A later Device-Loss notification and duplicate terminal callback
        # must not retroactively rewrite a completion already committed.
        state.device_lost = True
        before = copy.deepcopy(state)
        self.assertEqual(finish_submission(state, 201, success=False), "BadValue")
        self.assertEqual(state, before)

    def test_late_duplicate_present_callback_cannot_clear_new_wait_reservation(self) -> None:
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED)
        state = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNALED],
            shared_semaphores=[shared],
        )
        self.assertTrue(queue_present(state, PresentRequest(token=202, wait_indices=(0,))).accepted)
        self.assertEqual(finish_present_wait(state, 202, 0, consumed=False), "SUCCESS")

        # A later operation reuses the semaphore after the first operation is
        # terminal. A duplicate callback for the old token must not consume or
        # release the new operation's reservation.
        state.image_state = ImageState.ACQUIRED
        self.assertTrue(queue_present(state, PresentRequest(token=203, wait_indices=(0,))).accepted)
        before = copy.deepcopy(state)
        self.assertEqual(finish_present_wait(state, 202, 0, consumed=None), "BadValue")
        self.assertEqual(state, before)


    def test_device_loss_unchanged_signal_report_cannot_override_unknown_present_outcome(self) -> None:
        shared = SharedBinarySemaphore()
        submit = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(submit, SubmitRequest(token=204, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            shared_semaphores=[shared],
        )
        self.assertTrue(queue_present(present, PresentRequest(token=205, wait_indices=(0,))).accepted)
        self.assertEqual(finish_present_wait(present, 205, 0, consumed=None), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)

        # Even a backend's stale assertion that the signal payload was
        # unchanged must not restore a trusted state after the Present callback
        # explicitly reported an unknown payload outcome.
        submit.device_lost = True
        self.assertEqual(
            finish_submission(
                submit, 204, success=False,
                binary_payload_unchanged={("signal", 0)},
            ),
            "SUCCESS",
        )
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)
        self.assertEqual(submit.binary_signal_states[0], BinarySignalState.UNTRUSTED)
        self.assertIsNone(shared.signal_reservation)


    def test_stale_present_reservation_mismatch_rejection_is_mutation_free(self) -> None:
        shared = SharedBinarySemaphore(
            signal_state=BinarySignalState.SIGNALED,
            wait_reservation=("present", 207),
        )
        state = PresentState(
            wait_states=[],
            binary_signal_states=[],
            pending_present_waits=[(206, 0)],
            shared_semaphores=[shared],
        )
        before = copy.deepcopy(state)
        self.assertEqual(finish_present_wait(state, 206, 0, consumed=None), "BadValue")
        self.assertEqual(state, before)


    def test_cross_model_wait_completion_is_recorded_for_pending_signal_owner(self) -> None:
        shared = SharedBinarySemaphore()
        producer = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        consumer = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(producer, SubmitRequest(token=301, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        self.assertEqual(
            queue_submit(consumer, SubmitRequest(token=302, wait_indices=(0,))),
            "SUCCESS",
        )
        self.assertEqual(finish_submission(consumer, 302, success=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertEqual(shared.signal_reservation, ("submit", 301))
        self.assertTrue(shared.signal_consumed)

        # The producer's later terminal callback must observe consumption
        # recorded on the canonical semaphore, not resurrect its signal.
        self.assertEqual(finish_submission(producer, 301, success=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertIsNone(shared.signal_reservation)
        self.assertFalse(shared.signal_consumed)

    def test_failed_wait_unchanged_report_does_not_restore_stale_pending_signal(self) -> None:
        shared = SharedBinarySemaphore()
        producer = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        consumer = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(producer, SubmitRequest(token=303, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        self.assertEqual(
            queue_submit(consumer, SubmitRequest(token=304, wait_indices=(0,))),
            "SUCCESS",
        )
        # Signal completion races ahead of the still-pending wait callback.
        self.assertEqual(finish_submission(producer, 303, success=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.SIGNALED)
        self.assertEqual(finish_submission(
            consumer, 304, success=False,
            binary_payload_unchanged={("wait", 0)},
        ), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.SIGNALED)
        self.assertEqual(consumer.binary_signal_states[0], BinarySignalState.SIGNALED)
        self.assertEqual(consumer.wait_states[0], WaitState.READY)
        self.assertIsNone(shared.wait_reservation)


    def test_timeline_signal_callbacks_preserve_foreign_pending_reservations(self) -> None:
        state = self.state(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
                for _ in range(3)
            ],
            semaphore_kinds=[SemaphoreKind.TIMELINE],
            signal_counters=[2],
            signal_slots=[None],
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=401, command_buffer_indices=(0,),
                signal_indices=(0,), signal_values=(7,),
            )),
            "SUCCESS",
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=402, command_buffer_indices=(1,),
                signal_indices=(0,), signal_values=(11,),
            )),
            "SUCCESS",
        )
        self.assertEqual(state.pending_timeline_signals, [(401, 0, 7), (402, 0, 11)])
        self.assertEqual(state.signal_slots, [11])

        # Higher value completes first. Its callback must release only its own
        # reservation and leave the lower-valued pending signal binding.
        self.assertEqual(finish_submission(state, 402, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [11])
        self.assertEqual(state.pending_timeline_signals, [(401, 0, 7)])
        self.assertEqual(state.signal_slots, [7])

        # A duplicate terminal callback for 402 cannot clear 401's reservation
        # or rewrite the completed counter.
        before = copy.deepcopy(state)
        self.assertEqual(finish_submission(state, 402, success=False), "BadValue")
        self.assertEqual(state, before)

        # The lower callback may arrive later, but the timeline counter must
        # remain monotonic and the reservation slot must finally clear.
        self.assertEqual(finish_submission(state, 401, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [11])
        self.assertEqual(state.pending_timeline_signals, [])
        self.assertEqual(state.signal_slots, [None])

    def test_lower_timeline_signal_completion_keeps_higher_reservation_and_allows_intermediate_host_signal(self) -> None:
        state = SubmissionModel(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE),
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE),
            ],
            wait_states=[],
            signal_slots=[None],
            signal_counters=[0],
            semaphore_kinds=[SemaphoreKind.TIMELINE],
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=415, command_buffer_indices=(0,),
                signal_indices=(0,), signal_values=(7,),
            )),
            "SUCCESS",
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=416, command_buffer_indices=(1,),
                signal_indices=(0,), signal_values=(11,),
            )),
            "SUCCESS",
        )

        # Completing the lower reservation first must not erase the higher one.
        self.assertEqual(finish_submission(state, 415, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [7])
        self.assertEqual(state.pending_timeline_signals, [(416, 0, 11)])
        self.assertEqual(state.signal_slots, [11])

        # A host signal may advance the counter between the current value and
        # the still-pending GPU signal, but must not cross that reservation.
        self.assertEqual(signal_timeline_host(state, 0, 9), "SUCCESS")
        self.assertEqual(state.signal_counters, [9])
        before = copy.deepcopy(state)
        self.assertEqual(
            signal_timeline_host(state, 0, 11),
            "INVALID_SYNCHRONIZATION_STATE",
        )
        self.assertEqual(state, before)

        self.assertEqual(finish_submission(state, 416, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [11])
        self.assertEqual(state.pending_timeline_signals, [])
        self.assertEqual(state.signal_slots, [None])

    def test_failed_timeline_signal_releases_only_its_own_reservation(self) -> None:
        state = self.state(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
                for _ in range(3)
            ],
            semaphore_kinds=[SemaphoreKind.TIMELINE],
            signal_counters=[3],
            signal_slots=[None],
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=411, command_buffer_indices=(0,),
                signal_indices=(0,), signal_values=(8,),
            )),
            "SUCCESS",
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=412, command_buffer_indices=(1,),
                signal_indices=(0,), signal_values=(13,),
            )),
            "SUCCESS",
        )
        self.assertEqual(finish_submission(state, 412, success=False), "SUCCESS")
        self.assertEqual(state.signal_counters, [3])
        self.assertEqual(state.pending_timeline_signals, [(411, 0, 8)])
        self.assertEqual(state.signal_slots, [8])

        # Failure of the higher reservation does not poison or release the
        # unrelated lower reservation; it can still complete successfully.
        self.assertEqual(finish_submission(state, 411, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [8])
        self.assertEqual(state.pending_timeline_signals, [])
        self.assertEqual(state.signal_slots, [None])


    def test_device_loss_callbacks_in_reverse_order_do_not_publish_timeline_values(self) -> None:
        state = self.state(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
                for _ in range(3)
            ],
            semaphore_kinds=[SemaphoreKind.TIMELINE],
            signal_counters=[3],
            signal_slots=[None],
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=413, command_buffer_indices=(0,),
                signal_indices=(0,), signal_values=(8,),
            )),
            "SUCCESS",
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=414, command_buffer_indices=(1,),
                signal_indices=(0,), signal_values=(13,),
            )),
            "SUCCESS",
        )

        # Device loss wins over a late backend success. The higher reservation
        # completes first but must not publish its value or release token 413.
        state.device_lost = True
        self.assertEqual(finish_submission(state, 414, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [3])
        self.assertEqual(state.pending_timeline_signals, [(413, 0, 8)])
        self.assertEqual(state.signal_slots, [8])

        # The lower callback is also late; it must drain its own reservation
        # without advancing the counter after Device Loss.
        self.assertEqual(finish_submission(state, 413, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [3])
        self.assertEqual(state.pending_timeline_signals, [])
        self.assertEqual(state.signal_slots, [None])

        before = copy.deepcopy(state)
        self.assertEqual(finish_submission(state, 414, success=False), "BadValue")
        self.assertEqual(state, before)


    def test_timeline_wait_callbacks_remove_only_their_own_pending_waits(self) -> None:
        state = self.state(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
                for _ in range(3)
            ],
            semaphore_kinds=[SemaphoreKind.TIMELINE],
            signal_counters=[1],
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=421, command_buffer_indices=(0,),
                wait_indices=(0,), wait_values=(8,),
            )),
            "SUCCESS",
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=422, command_buffer_indices=(1,),
                wait_indices=(0,), wait_values=(12,),
            )),
            "SUCCESS",
        )
        self.assertEqual(
            state.pending_timeline_waits, [(421, 0, 8), (422, 0, 12)]
        )

        self.assertEqual(finish_submission(state, 421, success=True), "SUCCESS")
        self.assertEqual(state.pending_timeline_waits, [(422, 0, 12)])
        before = copy.deepcopy(state)
        self.assertEqual(finish_submission(state, 421, success=False), "BadValue")
        self.assertEqual(state, before)

        self.assertEqual(finish_submission(state, 422, success=False), "SUCCESS")
        self.assertEqual(state.pending_timeline_waits, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class CommandBufferResetAndPoolDestructionTests(unittest.TestCase):
    def test_reset_returns_every_nonpending_lifecycle_to_initial(self) -> None:
        for lifecycle in (
            CommandBufferLifecycle.INITIAL,
            CommandBufferLifecycle.RECORDING,
            CommandBufferLifecycle.EXECUTABLE,
            CommandBufferLifecycle.INVALID,
        ):
            with self.subTest(lifecycle=lifecycle):
                state = CommandBufferModel(lifecycle=lifecycle, entries=[b"recorded"])
                self.assertEqual(reset_command_buffer(state), "SUCCESS")
                self.assertEqual(state.lifecycle, CommandBufferLifecycle.INITIAL)
                self.assertEqual(state.entries, [])

    def test_reset_rejects_missing_pool_flag_or_pending_atomically(self) -> None:
        for changes in (
            {"lifecycle": CommandBufferLifecycle.EXECUTABLE},
            {"lifecycle": CommandBufferLifecycle.PENDING},
        ):
            with self.subTest(changes=changes):
                state = CommandBufferModel(**changes, entries=[b"keep"])
                before = copy.deepcopy(state)
                self.assertEqual(
                    reset_command_buffer(state, reset_flag=False if changes["lifecycle"] is not CommandBufferLifecycle.PENDING else True),
                    "INVALID_SYNCHRONIZATION_STATE",
                )
                self.assertEqual(state, before)

    def test_reset_checks_device_state_before_pool_flag_and_lifecycle(self) -> None:
        state = CommandBufferModel(device_lost=True, lifecycle=CommandBufferLifecycle.PENDING, entries=[b"keep"])
        before = copy.deepcopy(state)
        self.assertEqual(reset_command_buffer(state, reset_flag=False), "DEVICE_LOST")
        self.assertEqual(state, before)
        state.device_lost = False
        self.assertEqual(reset_command_buffer(state, device_available=False), "DEVICE_UNAVAILABLE")
        self.assertEqual(state.lifecycle, CommandBufferLifecycle.PENDING)
        self.assertEqual(state.entries, [b"keep"])

    def test_pool_destroy_is_atomic_when_any_live_child_is_pending(self) -> None:
        children = [
            CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE, entries=[b"a"]),
            CommandBufferModel(lifecycle=CommandBufferLifecycle.PENDING, entries=[b"b"]),
        ]
        before = copy.deepcopy(children)
        self.assertEqual(destroy_command_pool(children), "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual(children, before)

    def test_pool_destroy_invalidates_all_live_children_together(self) -> None:
        children = [
            CommandBufferModel(lifecycle=CommandBufferLifecycle.RECORDING, entries=[b"a"]),
            CommandBufferModel(lifecycle=CommandBufferLifecycle.INVALID, entries=[b"b"]),
        ]
        self.assertEqual(destroy_command_pool(children), "SUCCESS")
        self.assertTrue(all(not child.buffer_live and not child.pool_live for child in children))
        # Logical invalidation does not pretend backend references are already freed.
        self.assertEqual([child.entries for child in children], [[b"a"], [b"b"]])


class CommandBufferLifecycleTransitionTests(unittest.TestCase):
    def test_recording_buffer_cannot_be_submitted_or_mutated_partially(self) -> None:
        buffer = CommandBufferModel(lifecycle=CommandBufferLifecycle.RECORDING, entries=[b"accepted"])
        state = SubmissionModel(command_buffers=[buffer])
        before = copy.deepcopy(state)
        self.assertEqual(queue_submit(state, SubmitRequest(token=301)), "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual(state, before)

        self.assertEqual(
            command_buffer_data(buffer, CommandBufferChunk(operation="APPEND", entries=(b"later",))),
            "SUCCESS",
        )
        self.assertEqual(buffer.lifecycle, CommandBufferLifecycle.RECORDING)
        self.assertEqual(buffer.entries, [b"accepted", b"later"])

    def test_executable_buffer_becomes_pending_then_executable_on_success(self) -> None:
        buffer = CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE, entries=[b"entry"])
        state = SubmissionModel(command_buffers=[buffer])
        self.assertEqual(queue_submit(state, SubmitRequest(token=302)), "SUCCESS")
        self.assertEqual(buffer.lifecycle, CommandBufferLifecycle.PENDING)

        before = copy.deepcopy(buffer)
        self.assertEqual(
            command_buffer_data(buffer, CommandBufferChunk(operation="APPEND", entries=(b"illegal",))),
            "INVALID_SYNCHRONIZATION_STATE",
        )
        self.assertEqual(buffer, before)

        self.assertEqual(finish_submission(state, 302, success=True), "SUCCESS")
        self.assertEqual(buffer.lifecycle, CommandBufferLifecycle.EXECUTABLE)
        self.assertEqual(buffer.entries, [b"entry"])

    def test_failed_submission_invalidates_buffer_and_prevents_resubmission(self) -> None:
        buffer = CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE, entries=[b"entry"])
        state = SubmissionModel(command_buffers=[buffer])
        self.assertEqual(queue_submit(state, SubmitRequest(token=303)), "SUCCESS")
        self.assertEqual(finish_submission(state, 303, success=False), "SUCCESS")
        self.assertEqual(buffer.lifecycle, CommandBufferLifecycle.INVALID)

        before = copy.deepcopy(state)
        self.assertEqual(queue_submit(state, SubmitRequest(token=304)), "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual(state, before)
        self.assertEqual(
            command_buffer_data(buffer, CommandBufferChunk(operation="FINAL", entries=(b"more",))),
            "INVALID_SYNCHRONIZATION_STATE",
        )
        self.assertEqual(buffer.lifecycle, CommandBufferLifecycle.INVALID)

    def test_device_loss_racing_success_callback_does_not_restore_executable(self) -> None:
        buffer = CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
        state = SubmissionModel(command_buffers=[buffer])
        self.assertEqual(queue_submit(state, SubmitRequest(token=305)), "SUCCESS")
        self.assertEqual(buffer.lifecycle, CommandBufferLifecycle.PENDING)
        state.device_lost = True
        self.assertEqual(finish_submission(state, 305, success=True), "SUCCESS")
        self.assertEqual(buffer.lifecycle, CommandBufferLifecycle.INVALID)

    def test_terminal_callback_is_rejected_without_changing_invalid_buffer(self) -> None:
        buffer = CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
        state = SubmissionModel(command_buffers=[buffer])
        self.assertEqual(queue_submit(state, SubmitRequest(token=306)), "SUCCESS")
        self.assertEqual(finish_submission(state, 306, success=False), "SUCCESS")
        before = copy.deepcopy(state)
        self.assertEqual(finish_submission(state, 306, success=True), "BadValue")
        self.assertEqual(state, before)
