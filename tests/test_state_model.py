"""Executable precedence and atomicity tests for the XAverius state model."""
from __future__ import annotations

import copy
import gc
import unittest
from weakref import ref

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
    finish_present_terminal,
    mark_present_device_lost,
    CommandBufferLifecycle,
    CommandBufferChunk,
    CommandBufferModel,
    ResourceDestroyModel,
    destroy_resource,
    ShaderAssemblyState,
    ShaderChunk,
    SubmissionModel,
    SubmitRequest,
    command_buffer_data,
    reset_command_buffer,
    destroy_command_pool,
    retire_command_buffer_backend_hold,
    queue_submit,
    shader_module_data,
    finish_submission,
    mark_device_lost,
    signal_timeline_host,
    reset_fence,
    DescriptorSetLifetime,
    DescriptorPoolLifetime,
    DescriptorWrite,
    free_descriptor_sets,
    destroy_descriptor_pool,
    update_descriptor_sets,
    BufferMemoryLifetime,
    MemoryAllocationLifetime,
    destroy_buffer_lifetime,
    free_memory_lifetime,
    drop_buffer_internal_ref,
    descriptor_contents_submit_valid,
    AsyncSubmissionEventRegistry,
    AsyncSubmissionIdentity,
    AsyncDeviceIdentity,
    _unregister_semaphore_owner,
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


    def test_late_present_completion_cannot_clear_shared_untrusted_state(self) -> None:
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED)
        state = self.state(
            shared_semaphores=[shared],
            binary_signal_states=[BinarySignalState.SIGNALED],
        )
        self.assertEqual(
            queue_present(state, PresentRequest(token=41, wait_indices=(0,))).result,
            "SUCCESS",
        )
        self.assertEqual(shared.wait_reservation, ("present", 41))

        # Another terminal path discovers uncertain payload state before this
        # presentation callback arrives.
        shared.signal_state = BinarySignalState.UNTRUSTED
        self.assertEqual(finish_present_wait(state, 41, 0, consumed=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)
        self.assertEqual(state.binary_signal_states[0], BinarySignalState.UNTRUSTED)
        self.assertEqual(state.wait_states[0], WaitState.UNTRUSTED)
        self.assertIsNone(shared.wait_reservation)
        self.assertEqual(state.pending_present_waits, [])

        after_terminal = copy.deepcopy(state)
        self.assertEqual(finish_present_wait(state, 41, 0, consumed=True), "BadValue")
        self.assertEqual(state, after_terminal, "duplicate terminal callback mutated state")


    def test_duplicate_wait_indices_are_scalar_error_and_mutation_free(self) -> None:
        state = self.state()
        self.assert_rejected_atomically(
            state, PresentRequest(token=81, wait_indices=(0, 0)), "BadValue"
        )

    def test_unknown_wait_xid_precedes_device_loss_and_mutates_nothing(self) -> None:
        state = self.state(
            device_lost=True,
            valid_wait_xids=(True, False),
            wait_states=[WaitState.READY, WaitState.READY],
        )
        self.assert_rejected_atomically(
            state, PresentRequest(token=82, wait_indices=(1,)), "BadValue"
        )

    def test_shared_untrusted_signal_fails_even_when_local_wait_mirror_is_ready(self) -> None:
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.UNTRUSTED)
        state = self.state(
            wait_states=[WaitState.READY, WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNALED, BinarySignalState.UNSIGNALED],
            shared_semaphores=[shared],
        )
        self.assert_rejected_atomically(
            state, PresentRequest(token=83, wait_indices=(0,)), "DEPENDENCY_FAILED"
        )

    def test_existing_shared_wait_reservation_rejects_all_waits_atomically(self) -> None:
        shared = SharedBinarySemaphore(
            signal_state=BinarySignalState.SIGNALED,
            wait_reservation=("submit", 901),
        )
        state = self.state(
            wait_states=[WaitState.READY, WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNALED, BinarySignalState.SIGNALED],
            shared_semaphores=[shared, SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED)],
        )
        before = copy.deepcopy(state)
        self.assert_rejected_atomically(
            state, PresentRequest(token=84, wait_indices=(1, 0)),
            "INVALID_SYNCHRONIZATION_STATE",
        )
        self.assertEqual(state, before, "later invalid wait partially reserved earlier waits")

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

    def test_duplicate_command_buffer_is_rejected_atomically(self) -> None:
        state = self.state()
        self.assert_atomic_rejection(
            state, SubmitRequest(command_buffer_indices=(0, 0)), "BadValue"
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

    def test_terminal_timeline_wait_callbacks_release_only_their_own_future_waits(self) -> None:
        state = self.state(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
                for _ in range(2)
            ],
            semaphore_kinds=[SemaphoreKind.TIMELINE, SemaphoreKind.BINARY],
            signal_counters=[2, 0],
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=13, command_buffer_indices=(0,),
                wait_indices=(0,), wait_values=(8,),
            )),
            "SUCCESS",
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=14, command_buffer_indices=(1,),
                wait_indices=(0,), wait_values=(10,),
            )),
            "SUCCESS",
        )
        self.assertEqual(
            state.pending_timeline_waits, [(13, 0, 8), (14, 0, 10)]
        )

        # The second callback may terminate first. It must remove only its
        # own wait, and neither failure nor success may synthesize a counter
        # value that has not actually been signaled.
        self.assertEqual(finish_submission(state, 14, success=False), "SUCCESS")
        self.assertEqual(state.pending_timeline_waits, [(13, 0, 8)])
        self.assertEqual(state.signal_counters, [2, 0])
        self.assertEqual(finish_submission(state, 13, success=True), "SUCCESS")
        self.assertEqual(state.pending_timeline_waits, [])
        self.assertEqual(state.signal_counters, [2, 0])

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
            "INVALID_SYNCHRONIZATION_STATE",
        )

    def test_timeline_signal_not_above_observed_counter_is_bad_value(self) -> None:
        state = self.state(
            semaphore_kinds=[SemaphoreKind.TIMELINE],
            signal_slots=[None],
            signal_counters=[12],
            pending_timeline_signals=[],
        )
        self.assert_atomic_rejection(
            state, SubmitRequest(signal_indices=(0,), signal_values=(12,)),
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

    def test_failed_submit_callback_first_then_present_consumption_stays_untrusted(self) -> None:
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
            queue_submit(submit, SubmitRequest(token=198, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            shared_semaphores=[shared],
        )
        self.assertTrue(queue_present(present, PresentRequest(token=199, wait_indices=(0,))).accepted)

        # A failed submit cannot prove whether its signal reached the backend.
        self.assertEqual(finish_submission(submit, 198, success=False), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)
        self.assertEqual(finish_present_wait(present, 199, 0, consumed=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)
        self.assertIsNone(shared.signal_reservation)
        self.assertIsNone(shared.wait_reservation)
        self.assertEqual(
            queue_submit(submit, SubmitRequest(token=200, command_buffer_indices=(), signal_indices=(0,), signal_values=(0,))),
            "DEPENDENCY_FAILED",
        )

    def test_present_consumption_before_failed_submit_callback_preserves_known_consumption(self) -> None:
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
            queue_submit(submit, SubmitRequest(token=201, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            shared_semaphores=[shared],
        )
        self.assertTrue(queue_present(present, PresentRequest(token=202, wait_indices=(0,))).accepted)
        self.assertEqual(finish_present_wait(present, 202, 0, consumed=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)

        # Confirmed consumption is stronger than the later failed signal callback.
        self.assertEqual(finish_submission(submit, 201, success=False), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertIsNone(shared.signal_reservation)
        self.assertIsNone(shared.wait_reservation)
        self.assertFalse(shared.signal_consumed)

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
            "INVALID_SYNCHRONIZATION_STATE",
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

    def test_present_wait_consumption_wins_over_late_submit_signal_callback(self) -> None:
        shared = SharedBinarySemaphore()
        producer = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(producer, SubmitRequest(token=305, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        self.assertTrue(queue_present(present, PresentRequest(token=306, wait_indices=(0,))).accepted)

        # Presentation may consume the binary payload before the producer's
        # asynchronous signal callback arrives. The late callback must retire
        # its own reservation without resurrecting a signal already consumed.
        self.assertEqual(finish_present_wait(present, 306, 0, consumed=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertEqual(shared.signal_reservation, ("submit", 305))
        self.assertTrue(shared.signal_consumed)
        self.assertEqual(finish_submission(producer, 305, success=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertIsNone(shared.signal_reservation)
        self.assertFalse(shared.signal_consumed)

    def test_failed_submit_with_unchanged_payload_clears_signal_provenance(self) -> None:
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
            queue_submit(state, SubmitRequest(
                token=306, signal_indices=(0,), signal_values=(0,),
            )),
            "SUCCESS",
        )
        self.assertTrue(shared.signal_from_submit)
        self.assertEqual(
            finish_submission(
                state, 306, success=False,
                binary_payload_unchanged={("signal", 0)},
            ),
            "SUCCESS",
        )
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertIsNone(shared.signal_reservation)
        self.assertFalse(shared.signal_from_submit)
        self.assertFalse(shared.signal_consumption_confirmed)

    def test_present_consumption_after_submit_completion_survives_later_device_loss(self) -> None:
        shared = SharedBinarySemaphore()
        producer = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(producer, SubmitRequest(
                token=307, signal_indices=(0,), signal_values=(0,),
            )),
            "SUCCESS",
        )
        self.assertTrue(queue_present(
            present, PresentRequest(token=308, wait_indices=(0,))
        ).accepted)

        # The Submit callback can publish and retire its reservation before
        # the independent Present wait callback confirms consumption.
        self.assertEqual(finish_submission(producer, 307, success=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.SIGNALED)
        self.assertIsNone(shared.signal_reservation)
        self.assertEqual(finish_present_wait(
            present, 308, 0, consumed=True
        ), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertTrue(shared.signal_consumption_confirmed)

        # Later device loss must preserve the positively confirmed empty
        # payload rather than quarantining it just because the Submit token
        # no longer owns a transient reservation.
        self.assertEqual(mark_present_device_lost(present), "SUCCESS")
        self.assertTrue(shared.device_lost)
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertIsNone(shared.signal_reservation)
        self.assertTrue(shared.signal_consumption_confirmed)
        self.assertEqual(present.binary_signal_states[0], BinarySignalState.UNSIGNALED)

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


    def test_mixed_timeline_signal_validation_rejects_atomically(self) -> None:
        state = self.state(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE),
            ],
            semaphore_kinds=[SemaphoreKind.TIMELINE, SemaphoreKind.TIMELINE],
            signal_counters=[2, 9],
            signal_slots=[None, None],
        )
        # The first signal is valid, but the second does not exceed its
        # current counter. Validation must not reserve the first semaphore.
        self.assert_atomic_rejection(
            state,
            SubmitRequest(signal_indices=(0, 1), signal_values=(7, 9)),
            "BadValue",
        )
        self.assertEqual(state.pending_timeline_signals, [])
        self.assertEqual(state.signal_slots, [None, None])

    def test_failed_and_late_timeline_callbacks_preserve_other_reservations(self) -> None:
        state = self.state(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
                for _ in range(4)
            ],
            semaphore_kinds=[SemaphoreKind.TIMELINE, SemaphoreKind.TIMELINE],
            signal_counters=[2, 4],
            signal_slots=[None, None],
        )
        # Token 431 reserves both semaphores; token 432 reserves a higher
        # value on semaphore 0. Terminal callbacks must be scoped by token.
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=431, command_buffer_indices=(0,),
                signal_indices=(0, 1), signal_values=(7, 12),
            )),
            "SUCCESS",
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=432, command_buffer_indices=(1,),
                signal_indices=(0,), signal_values=(11,),
            )),
            "SUCCESS",
        )
        self.assertEqual(finish_submission(state, 432, success=False), "SUCCESS")
        self.assertEqual(state.signal_counters, [2, 4])
        self.assertEqual(state.pending_timeline_signals, [(431, 0, 7), (431, 1, 12)])
        self.assertEqual(state.signal_slots, [7, 12])

        # Semaphore 0 can complete while semaphore 1's signal is still
        # pending. A subsequent Device Loss invalidates only unpublished
        # completion work; the late callback drains its own remaining entry.
        self.assertEqual(finish_submission(state, 431, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [7, 12])
        self.assertEqual(state.pending_timeline_signals, [])
        self.assertEqual(state.signal_slots, [None, None])
        before = copy.deepcopy(state)
        self.assertEqual(finish_submission(state, 431, success=False), "BadValue")
        self.assertEqual(state, before)

    def test_device_loss_drains_only_callback_owned_timeline_reservations(self) -> None:
        state = self.state(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
                for _ in range(3)
            ],
            semaphore_kinds=[SemaphoreKind.TIMELINE, SemaphoreKind.TIMELINE],
            signal_counters=[1, 3],
            signal_slots=[None, None],
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=433, command_buffer_indices=(0,),
                signal_indices=(0, 1), signal_values=(8, 15),
            )),
            "SUCCESS",
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=434, command_buffer_indices=(1,),
                signal_indices=(0,), signal_values=(10,),
            )),
            "SUCCESS",
        )
        state.device_lost = True
        # A late success must not publish either value or release another
        # token's reservation.
        self.assertEqual(finish_submission(state, 434, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [1, 3])
        self.assertEqual(state.pending_timeline_signals, [(433, 0, 8), (433, 1, 15)])
        self.assertEqual(state.signal_slots, [8, 15])

        self.assertEqual(finish_submission(state, 433, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [1, 3])
        self.assertEqual(state.pending_timeline_signals, [])
        self.assertEqual(state.signal_slots, [None, None])

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

    def test_timeline_host_signal_rejects_device_loss_observed_by_shared_model(self) -> None:
        shared = SharedBinarySemaphore()
        owner = SubmissionModel(
            semaphore_kinds=[SemaphoreKind.TIMELINE],
            signal_counters=[3],
            signal_slots=[None],
            shared_semaphores=[shared],
        )
        observer = SubmissionModel(shared_semaphores=[shared])

        # Device loss must immediately reach every model attached to the
        # shared semaphore, not wait for the timeline owner's next operation.
        self.assertEqual(mark_device_lost(observer), "SUCCESS")
        self.assertTrue(owner.device_lost)
        self.assertTrue(shared.device_lost)
        before = copy.deepcopy(owner)

        self.assertEqual(signal_timeline_host(owner, 0, 8), "DEVICE_LOST")
        self.assertTrue(owner.device_lost)
        self.assertEqual(owner.signal_counters, before.signal_counters)
        self.assertEqual(owner.signal_slots, before.signal_slots)
        self.assertEqual(owner.pending_timeline_signals, before.pending_timeline_signals)

    def test_host_signal_then_reverse_gpu_callbacks_keep_timeline_monotonic(self) -> None:
        state = self.state(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
                for _ in range(2)
            ],
            semaphore_kinds=[SemaphoreKind.TIMELINE],
            signal_counters=[0],
            signal_slots=[None],
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=417, command_buffer_indices=(0,),
                signal_indices=(0,), signal_values=(7,),
            )),
            "SUCCESS",
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=418, command_buffer_indices=(1,),
                signal_indices=(0,), signal_values=(11,),
            )),
            "SUCCESS",
        )

        # Host signaling may advance below every pending GPU reservation.
        self.assertEqual(signal_timeline_host(state, 0, 5), "SUCCESS")
        self.assertEqual(state.signal_counters, [5])
        self.assertEqual(state.pending_timeline_signals, [(417, 0, 7), (418, 0, 11)])

        # Reverse completion order: the higher GPU value arrives first.
        self.assertEqual(finish_submission(state, 418, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [11])
        self.assertEqual(state.pending_timeline_signals, [(417, 0, 7)])
        self.assertEqual(state.signal_slots, [7])

        # The late lower-valued callback cannot roll the timeline back or
        # remove any reservation except its own.
        self.assertEqual(finish_submission(state, 417, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [11])
        self.assertEqual(state.pending_timeline_signals, [])
        self.assertEqual(state.signal_slots, [None])

        # A host signal below the current counter remains invalid after both
        # callbacks; a duplicate callback is mutation-free as well.
        before = copy.deepcopy(state)
        self.assertEqual(
            signal_timeline_host(state, 0, 10),
            "INVALID_SYNCHRONIZATION_STATE",
        )
        self.assertEqual(state, before)
        self.assertEqual(finish_submission(state, 417, success=False), "BadValue")
        self.assertEqual(state, before)

    def test_host_signal_cannot_cross_lower_gpu_reservation_after_higher_callback(self) -> None:
        state = self.state(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
                for _ in range(2)
            ],
            semaphore_kinds=[SemaphoreKind.TIMELINE],
            signal_counters=[0],
            signal_slots=[None],
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=419, command_buffer_indices=(0,),
                signal_indices=(0,), signal_values=(7,),
            )),
            "SUCCESS",
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=420, command_buffer_indices=(1,),
                signal_indices=(0,), signal_values=(11,),
            )),
            "SUCCESS",
        )

        # The higher GPU signal callback arrives first. Its successful value is
        # observable, but the lower operation still owns its reservation until
        # its own terminal callback; a host signal must not cross that gap.
        self.assertEqual(finish_submission(state, 420, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [11])
        self.assertEqual(state.pending_timeline_signals, [(419, 0, 7)])
        self.assertEqual(state.signal_slots, [7])
        before = copy.deepcopy(state)
        self.assertEqual(
            signal_timeline_host(state, 0, 12),
            "INVALID_SYNCHRONIZATION_STATE",
        )
        self.assertEqual(state, before)

        # The delayed lower callback may fail without rolling back the already
        # observed counter. Once its reservation is retired, host signaling can
        # advance the counter normally.
        self.assertEqual(finish_submission(state, 419, success=False), "SUCCESS")
        self.assertEqual(state.signal_counters, [11])
        self.assertEqual(state.pending_timeline_signals, [])
        self.assertEqual(state.signal_slots, [None])
        self.assertEqual(signal_timeline_host(state, 0, 12), "SUCCESS")
        self.assertEqual(state.signal_counters, [12])

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



    def test_lower_timeline_callback_failure_first_preserves_higher_reservation(self) -> None:
        state = self.state(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
                for _ in range(2)
            ],
            semaphore_kinds=[SemaphoreKind.TIMELINE],
            signal_counters=[2],
            signal_slots=[None],
        )
        self.assertEqual(queue_submit(state, SubmitRequest(
            token=435, command_buffer_indices=(0,),
            signal_indices=(0,), signal_values=(7,),
        )), "SUCCESS")
        self.assertEqual(queue_submit(state, SubmitRequest(
            token=436, command_buffer_indices=(1,),
            signal_indices=(0,), signal_values=(12,),
        )), "SUCCESS")

        # Lower callback arrives first and fails: only its own reservation is
        # retired; the higher value remains the public pending reservation.
        self.assertEqual(finish_submission(state, 435, success=False), "SUCCESS")
        self.assertEqual(state.signal_counters, [2])
        self.assertEqual(state.pending_timeline_signals, [(436, 0, 12)])
        self.assertEqual(state.signal_slots, [12])

        self.assertEqual(finish_submission(state, 436, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [12])
        self.assertEqual(state.pending_timeline_signals, [])
        self.assertEqual(state.signal_slots, [None])
        before = copy.deepcopy(state)
        self.assertEqual(finish_submission(state, 435, success=True), "BadValue")
        self.assertEqual(state, before)

    def test_lower_timeline_callback_success_then_higher_failure_keeps_observed_counter(self) -> None:
        state = self.state(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
                for _ in range(2)
            ],
            semaphore_kinds=[SemaphoreKind.TIMELINE],
            signal_counters=[2],
            signal_slots=[None],
        )
        self.assertEqual(queue_submit(state, SubmitRequest(
            token=437, command_buffer_indices=(0,),
            signal_indices=(0,), signal_values=(7,),
        )), "SUCCESS")
        self.assertEqual(queue_submit(state, SubmitRequest(
            token=438, command_buffer_indices=(1,),
            signal_indices=(0,), signal_values=(12,),
        )), "SUCCESS")

        # The lower value becomes observable first while the higher reservation
        # remains outstanding. Its later failure must not roll back the counter
        # or leave a stale signal slot.
        self.assertEqual(finish_submission(state, 437, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [7])
        self.assertEqual(state.pending_timeline_signals, [(438, 0, 12)])
        self.assertEqual(state.signal_slots, [12])
        self.assertEqual(finish_submission(state, 438, success=False), "SUCCESS")
        self.assertEqual(state.signal_counters, [7])
        self.assertEqual(state.pending_timeline_signals, [])
        self.assertEqual(state.signal_slots, [None])
        before = copy.deepcopy(state)
        self.assertEqual(finish_submission(state, 438, success=True), "BadValue")
        self.assertEqual(state, before)


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


    def test_device_loss_terminalizes_all_pending_submissions_before_late_callbacks(self) -> None:
        buffers = [
            CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
            for _ in range(2)
        ]
        state = self.state(
            command_buffers=buffers,
            semaphore_kinds=[SemaphoreKind.TIMELINE],
            signal_counters=[3],
            signal_slots=[None],
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=420, command_buffer_indices=(0,),
                signal_indices=(0,), signal_values=(8,),
            )),
            "SUCCESS",
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=421, command_buffer_indices=(1,),
                signal_indices=(0,), signal_values=(13,),
            )),
            "SUCCESS",
        )
        self.assertEqual(state.pending_submissions, [420, 421])
        self.assertEqual(state.pending_timeline_signals, [(420, 0, 8), (421, 0, 13)])

        self.assertEqual(mark_device_lost(state), "SUCCESS")
        self.assertTrue(state.device_lost)
        self.assertEqual(state.pending_submissions, [])
        self.assertEqual(state.pending_timeline_signals, [])
        self.assertEqual(state.signal_slots, [None])
        self.assertEqual(state.signal_counters, [3])
        self.assertEqual(
            [buffer.lifecycle for buffer in buffers],
            [CommandBufferLifecycle.INVALID, CommandBufferLifecycle.INVALID],
        )

        # Backend callbacks arriving after loss terminalization cannot revive
        # either command buffer or publish a reserved timeline value.
        before = copy.deepcopy(state)
        self.assertEqual(finish_submission(state, 420, success=True), "BadValue")
        self.assertEqual(finish_submission(state, 421, success=True), "BadValue")
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


    def test_device_loss_drains_competing_timeline_waits_after_reverse_callback(self) -> None:
        state = self.state(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
                for _ in range(2)
            ],
            semaphore_kinds=[SemaphoreKind.TIMELINE],
            signal_counters=[2],
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=441, command_buffer_indices=(0,),
                wait_indices=(0,), wait_values=(8,),
            )),
            "SUCCESS",
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=442, command_buffer_indices=(1,),
                wait_indices=(0,), wait_values=(12,),
            )),
            "SUCCESS",
        )
        self.assertEqual(
            state.pending_timeline_waits, [(441, 0, 8), (442, 0, 12)]
        )

        # The higher-target wait callback arrives first. It retires only its
        # own wait and must not synthesize a timeline counter update.
        self.assertEqual(finish_submission(state, 442, success=True), "SUCCESS")
        self.assertEqual(state.pending_timeline_waits, [(441, 0, 8)])
        self.assertEqual(state.signal_counters, [2])

        # Device loss terminalizes the remaining wait. A later callback for
        # that token must not restore the wait or mutate terminal state.
        self.assertEqual(mark_device_lost(state), "SUCCESS")
        self.assertEqual(state.pending_submissions, [])
        self.assertEqual(state.pending_timeline_waits, [])
        self.assertEqual(state.signal_counters, [2])
        self.assertEqual(state.pending_command_buffers, [])
        self.assertEqual(
            [buffer.lifecycle for buffer in state.command_buffers],
            [CommandBufferLifecycle.INVALID, CommandBufferLifecycle.EXECUTABLE],
        )
        before = copy.deepcopy(state)
        self.assertEqual(finish_submission(state, 441, success=True), "BadValue")
        self.assertEqual(finish_submission(state, 442, success=False), "BadValue")
        self.assertEqual(state, before, "late callbacks mutated device-loss terminal state")



class RecreatedDeviceSubmissionCallbackTests(unittest.TestCase):
    def test_old_terminal_callback_cannot_emit_for_recreated_device_generation(self) -> None:
        registry = AsyncSubmissionEventRegistry(live_connections={"client-A"})
        old_device = AsyncDeviceIdentity("device-A", 71)
        registry.register_device("client-A", old_device)
        old_submission = AsyncSubmissionIdentity(
            connection_identity="client-A",
            token=1101,
            device_identity="device-A",
            device_xid=71,
            queue_key=(0, 0),
        )
        self.assertEqual(registry.accept_submission(old_submission), "SUCCESS")
        self.assertEqual(
            registry.select_queue_events("client-A", "device-A", (0, 0), 1),
            "SUCCESS",
        )

        self.assertEqual(registry.destroy_device("device-A"), "SUCCESS")
        new_device = AsyncDeviceIdentity("device-A", 71)
        registry.register_device("client-A", new_device)
        self.assertEqual(
            registry.select_queue_events("client-A", "device-A", (0, 0), 1),
            "SUCCESS",
        )
        new_submission = AsyncSubmissionIdentity(
            connection_identity="client-A",
            token=1102,
            device_identity="device-A",
            device_xid=71,
            queue_key=(0, 0),
        )
        self.assertEqual(registry.accept_submission(new_submission), "SUCCESS")

        # The old callback has the same logical identity, XID, queue and event
        # mask available again, but its captured device object is from the
        # destroyed generation. It may retire its own submission only.
        self.assertEqual(
            registry.terminal_callback("client-A", 1101, "COMPLETE"), "SUCCESS"
        )
        self.assertEqual(old_submission.terminal, "COMPLETE")
        self.assertIsNone(new_submission.terminal)
        self.assertNotIn(("client-A", 1101), registry.submissions)
        self.assertIs(registry.submissions[("client-A", 1102)], new_submission)
        self.assertEqual(registry.emitted_events, [])

        self.assertEqual(
            registry.terminal_callback("client-A", 1102, "COMPLETE"), "SUCCESS"
        )
        self.assertEqual(new_submission.terminal, "COMPLETE")
        self.assertEqual(
            registry.emitted_events,
            [("COMPLETE", "client-A", 71, 1102)],
        )

if __name__ == "__main__":
    unittest.main(verbosity=2)


class ResourceDestroyReferenceTests(unittest.TestCase):
    def test_destroy_rejects_recording_reference_without_mutation(self) -> None:
        recording = CommandBufferModel(lifecycle=CommandBufferLifecycle.RECORDING, entries=[b"recorded"])
        executable = CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE, entries=[b"also recorded"])
        state = ResourceDestroyModel(recording_refs=[recording], executable_refs=[executable])
        before = copy.deepcopy((state, recording, executable))
        self.assertEqual(destroy_resource(state), "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual((state, recording, executable), before)

    def test_destroy_invalidates_executable_references_atomically(self) -> None:
        first = CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE, entries=[b"a"])
        second = CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE, entries=[b"b"])
        state = ResourceDestroyModel(executable_refs=[first, second])
        self.assertEqual(destroy_resource(state), "SUCCESS")
        self.assertFalse(state.resource_live)
        self.assertEqual((first.lifecycle, second.lifecycle), (
            CommandBufferLifecycle.INVALID, CommandBufferLifecycle.INVALID,
        ))
        self.assertEqual((first.entries, second.entries), ([b"a"], [b"b"]))

    def test_pending_use_rejection_preserves_resource_and_executable_buffers(self) -> None:
        cb = CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE, entries=[b"keep"])
        state = ResourceDestroyModel(pending_use=True, executable_refs=[cb])
        before = copy.deepcopy((state, cb))
        self.assertEqual(destroy_resource(state), "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual((state, cb), before)

    def test_unsupported_resource_type_is_rejected_before_reference_checks(self) -> None:
        recording = CommandBufferModel(lifecycle=CommandBufferLifecycle.RECORDING, entries=[b"keep"])
        state = ResourceDestroyModel(supported_type=False, recording_refs=[recording])
        before = copy.deepcopy((state, recording))
        self.assertEqual(destroy_resource(state), "BadMatch")
        self.assertEqual((state, recording), before)


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

    def test_reset_retires_recorded_descriptor_and_indirect_references(self) -> None:
        descriptor_set = DescriptorSetLifetime(slots={0: "buffer-old"})
        state = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.EXECUTABLE,
            entries=[b"old recording"],
            descriptor_sets=[descriptor_set],
            indirect_buffer_refs={"buffer-old", "buffer-derived"},
        )
        self.assertEqual(reset_command_buffer(state), "SUCCESS")
        self.assertEqual(state.lifecycle, CommandBufferLifecycle.INITIAL)
        self.assertEqual(state.entries, [])
        self.assertEqual(state.descriptor_sets, [])
        self.assertEqual(state.indirect_buffer_refs, set())

    def test_reset_and_rerecord_preserve_old_refs_until_all_old_backend_holds_retire(self) -> None:
        old_set = DescriptorSetLifetime(slots={0: "buffer-old"})
        state = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.EXECUTABLE,
            entries=[b"old recording"],
            descriptor_sets=[old_set],
            indirect_buffer_refs={"buffer-old", "indirect-old"},
            backend_holds=2,
        )

        old_epoch = state.recording_epoch
        self.assertEqual(reset_command_buffer(state), "SUCCESS")
        self.assertEqual(state.lifecycle, CommandBufferLifecycle.INITIAL)
        self.assertEqual(state.entries, [])
        self.assertEqual(state.descriptor_sets, [])
        self.assertEqual(state.indirect_buffer_refs, set())
        self.assertEqual(state.backend_holds, 0)
        self.assertEqual(state.recording_epoch, old_epoch + 1)
        self.assertEqual(len(state.retired_recordings), 1)
        retired = state.retired_recordings[0]
        self.assertEqual(retired.epoch, old_epoch)
        self.assertEqual(retired.backend_holds, 2)
        self.assertEqual(retired.entries, [b"old recording"])
        self.assertEqual(retired.descriptor_sets, [old_set])
        self.assertEqual(retired.indirect_buffer_refs, {"buffer-old", "indirect-old"})

        # A fresh recording owns independent references while the old backend
        # work is still draining.
        new_set = DescriptorSetLifetime(slots={1: "buffer-new"})
        self.assertEqual(
            command_buffer_data(
                state, CommandBufferChunk(operation="CREATE", entries=(b"new recording",))
            ),
            "SUCCESS",
        )
        state.descriptor_sets = [new_set]
        state.indirect_buffer_refs = {"buffer-new", "indirect-new"}
        state.backend_holds = 1

        new_epoch = state.recording_epoch
        # A newer recording can finish before an older backend callback arrives.
        # The explicit epoch must release only the new hold, not consume an old one.
        self.assertEqual(
            retire_command_buffer_backend_hold(state, recording_epoch=new_epoch), "SUCCESS"
        )
        self.assertEqual(state.backend_holds, 0)
        self.assertEqual(state.retired_recordings[0].backend_holds, 2)
        self.assertEqual(state.entries, [b"new recording"])
        self.assertEqual(state.descriptor_sets, [new_set])
        self.assertEqual(state.indirect_buffer_refs, {"buffer-new", "indirect-new"})

        self.assertEqual(
            retire_command_buffer_backend_hold(state, recording_epoch=old_epoch), "SUCCESS"
        )
        self.assertEqual(state.retired_recordings[0].backend_holds, 1)
        self.assertEqual(state.retired_recordings[0].entries, [b"old recording"])
        self.assertEqual(state.entries, [b"new recording"])
        self.assertEqual(state.descriptor_sets, [new_set])
        self.assertEqual(state.indirect_buffer_refs, {"buffer-new", "indirect-new"})

        self.assertEqual(
            retire_command_buffer_backend_hold(state, recording_epoch=old_epoch), "SUCCESS"
        )
        self.assertEqual(state.retired_recordings, [])
        self.assertEqual(state.entries, [b"new recording"])
        self.assertEqual(state.descriptor_sets, [new_set])
        self.assertEqual(state.indirect_buffer_refs, {"buffer-new", "indirect-new"})

        # Completing the new recording's backend use must not clear its
        # executable references; those remain until the next reset/destroy.
        before = copy.deepcopy(state)
        self.assertEqual(
            retire_command_buffer_backend_hold(state, recording_epoch=new_epoch),
            "INVALID_SYNCHRONIZATION_STATE",
        )
        self.assertEqual(state, before)

    def test_abort_with_backend_hold_defers_old_recording_reference_release(self) -> None:
        old_set = DescriptorSetLifetime(slots={0: "buffer-old"})
        state = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.RECORDING,
            entries=[b"old partial recording"],
            descriptor_sets=[old_set],
            indirect_buffer_refs={"buffer-old"},
            backend_holds=1,
        )
        self.assertEqual(
            command_buffer_data(state, CommandBufferChunk(operation="ABORT")),
            "SUCCESS",
        )
        self.assertEqual(state.entries, [])
        self.assertEqual(state.descriptor_sets, [])
        self.assertEqual(state.indirect_buffer_refs, set())
        self.assertEqual(len(state.retired_recordings), 1)
        self.assertEqual(state.retired_recordings[0].entries, [b"old partial recording"])
        self.assertEqual(state.retired_recordings[0].descriptor_sets, [old_set])
        self.assertEqual(state.retired_recordings[0].indirect_buffer_refs, {"buffer-old"})
        self.assertEqual(retire_command_buffer_backend_hold(state), "SUCCESS")
        self.assertEqual(state.retired_recordings, [])

    def test_abort_retires_recorded_references_and_rerecording_starts_fresh(self) -> None:
        descriptor_set = DescriptorSetLifetime(slots={0: "buffer-old"})
        state = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.RECORDING,
            entries=[b"old chunk"],
            descriptor_sets=[descriptor_set],
            indirect_buffer_refs={"buffer-old"},
        )
        self.assertEqual(command_buffer_data(state, CommandBufferChunk(operation="ABORT")), "SUCCESS")
        self.assertEqual(state.lifecycle, CommandBufferLifecycle.INITIAL)
        self.assertEqual(state.entries, [])
        self.assertEqual(state.descriptor_sets, [])
        self.assertEqual(state.indirect_buffer_refs, set())

        state.descriptor_sets.append(DescriptorSetLifetime(slots={1: "buffer-new"}))
        state.indirect_buffer_refs.add("buffer-new")
        self.assertEqual(
            command_buffer_data(state, CommandBufferChunk(operation="CREATE", entries=(b"new recording",))),
            "SUCCESS",
        )
        self.assertEqual(state.entries, [b"new recording"])
        self.assertEqual(state.descriptor_sets, [])
        self.assertEqual(state.indirect_buffer_refs, set())

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
        # With no backend hold, logical invalidation can retire recorded refs.
        self.assertEqual([child.entries for child in children], [[], []])
        self.assertEqual([child.descriptor_sets for child in children], [[], []])
        self.assertEqual([child.indirect_buffer_refs for child in children], [set(), set()])

    def test_pool_destroy_retains_refs_until_each_backend_hold_retires(self) -> None:
        descriptor_set = DescriptorSetLifetime(slots={0: "buffer-kept"})
        child = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.EXECUTABLE,
            entries=[b"backend-visible"],
            descriptor_sets=[descriptor_set],
            indirect_buffer_refs={"buffer-kept", "indirect-kept"},
            backend_holds=3,
        )
        sibling = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.INVALID,
            entries=[b"sibling-backend-visible"],
            indirect_buffer_refs={"sibling-buffer-kept"},
            backend_holds=2,
        )

        self.assertEqual(destroy_command_pool([child, sibling]), "SUCCESS")
        for buffer in (child, sibling):
            self.assertFalse(buffer.buffer_live)
            self.assertFalse(buffer.pool_live)
        self.assertEqual(child.entries, [b"backend-visible"])
        self.assertEqual(child.descriptor_sets, [descriptor_set])
        self.assertEqual(child.indirect_buffer_refs, {"buffer-kept", "indirect-kept"})
        self.assertEqual(sibling.entries, [b"sibling-backend-visible"])
        self.assertEqual(sibling.indirect_buffer_refs, {"sibling-buffer-kept"})

        # A callback retiring one backend use must not release references still
        # needed by either of the other outstanding uses.
        self.assertEqual(retire_command_buffer_backend_hold(child), "SUCCESS")
        self.assertEqual(child.backend_holds, 2)
        self.assertEqual(child.entries, [b"backend-visible"])
        self.assertEqual(child.descriptor_sets, [descriptor_set])
        self.assertEqual(child.indirect_buffer_refs, {"buffer-kept", "indirect-kept"})
        self.assertEqual(retire_command_buffer_backend_hold(sibling), "SUCCESS")
        self.assertEqual(sibling.backend_holds, 1)
        self.assertEqual(sibling.entries, [b"sibling-backend-visible"])
        self.assertEqual(sibling.indirect_buffer_refs, {"sibling-buffer-kept"})

        self.assertEqual(retire_command_buffer_backend_hold(child), "SUCCESS")
        self.assertEqual(child.backend_holds, 1)
        self.assertEqual(child.entries, [b"backend-visible"])
        self.assertEqual(child.descriptor_sets, [descriptor_set])
        self.assertEqual(child.indirect_buffer_refs, {"buffer-kept", "indirect-kept"})
        self.assertEqual(retire_command_buffer_backend_hold(child), "SUCCESS")
        self.assertEqual(child.backend_holds, 0)
        self.assertEqual(child.entries, [])
        self.assertEqual(child.descriptor_sets, [])
        self.assertEqual(child.indirect_buffer_refs, set())
        # Retiring the last hold of one child does not release another child's
        # references while that sibling still has a backend user.
        self.assertEqual(sibling.entries, [b"sibling-backend-visible"])
        self.assertEqual(sibling.indirect_buffer_refs, {"sibling-buffer-kept"})
        self.assertEqual(retire_command_buffer_backend_hold(sibling), "SUCCESS")
        self.assertEqual(sibling.backend_holds, 0)
        self.assertEqual(sibling.entries, [])
        self.assertEqual(sibling.indirect_buffer_refs, set())

        before = copy.deepcopy(child)
        self.assertEqual(retire_command_buffer_backend_hold(child),
                         "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual(child, before)


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


class DescriptorSetLifetimeAtomicityTests(unittest.TestCase):
    def test_duplicate_descriptor_set_free_does_not_double_release_slot_refs(self) -> None:
        buffer = BufferMemoryLifetime(identity="buffer-shared", descriptor_slot_refs=2)
        selected = DescriptorSetLifetime(slots={0: buffer.identity})
        still_live = DescriptorSetLifetime(slots={0: buffer.identity})
        before = copy.deepcopy((selected, still_live, buffer))

        self.assertEqual(
            free_descriptor_sets([selected, selected], [buffer]),
            "BadValue",
        )
        self.assertEqual((selected, still_live, buffer), before)
        self.assertEqual(buffer.descriptor_slot_refs, 2)

        self.assertEqual(free_descriptor_sets([selected], [buffer]), "SUCCESS")
        self.assertEqual(buffer.descriptor_slot_refs, 1)
        self.assertTrue(still_live.live)
        self.assertEqual(still_live.slots, {0: buffer.identity})

    def test_free_descriptor_sets_rejects_pending_set_atomically(self) -> None:
        cb = CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE, entries=[b"keep"])
        first = DescriptorSetLifetime(executable_refs=[cb])
        pending = DescriptorSetLifetime(pending_use=True)
        before = copy.deepcopy((first, pending, cb))
        self.assertEqual(free_descriptor_sets([first, pending]), "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual((first, pending, cb), before)

    def test_free_descriptor_sets_rejects_recording_reference_atomically(self) -> None:
        cb = CommandBufferModel(lifecycle=CommandBufferLifecycle.RECORDING, entries=[b"recorded"])
        selected = DescriptorSetLifetime(recording_refs=1, executable_refs=[cb])
        before = copy.deepcopy((selected, cb))
        self.assertEqual(free_descriptor_sets([selected]), "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual((selected, cb), before)

    def test_free_descriptor_sets_invalidates_only_selected_sets_and_executable_refs(self) -> None:
        cb1 = CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE, entries=[b"a"])
        cb2 = CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE, entries=[b"b"])
        selected = DescriptorSetLifetime(executable_refs=[cb1])
        unselected = DescriptorSetLifetime(executable_refs=[cb2])
        self.assertEqual(free_descriptor_sets([selected]), "SUCCESS")
        self.assertFalse(selected.live)
        self.assertTrue(unselected.live)
        self.assertEqual(cb1.lifecycle, CommandBufferLifecycle.INVALID)
        self.assertEqual(cb2.lifecycle, CommandBufferLifecycle.EXECUTABLE)

    def test_destroy_descriptor_pool_rejects_any_child_blocker_without_mutation(self) -> None:
        executable = CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE, entries=[b"a"])
        recording = CommandBufferModel(lifecycle=CommandBufferLifecycle.RECORDING, entries=[b"b"])
        pool = DescriptorPoolLifetime(sets=[
            DescriptorSetLifetime(executable_refs=[executable]),
            DescriptorSetLifetime(recording_refs=1, executable_refs=[recording]),
        ])
        before = copy.deepcopy((pool, executable, recording))
        self.assertEqual(destroy_descriptor_pool(pool), "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual((pool, executable, recording), before)

    def test_destroy_descriptor_pool_invalidates_pool_all_live_sets_and_executable_refs(self) -> None:
        cb1 = CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE, entries=[b"a"])
        cb2 = CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE, entries=[b"b"])
        already_freed = DescriptorSetLifetime(live=False)
        first = DescriptorSetLifetime(executable_refs=[cb1])
        second = DescriptorSetLifetime(executable_refs=[cb2])
        pool = DescriptorPoolLifetime(sets=[first, second, already_freed])
        self.assertEqual(destroy_descriptor_pool(pool), "SUCCESS")
        self.assertFalse(pool.live)
        self.assertFalse(pool.xid_valid)
        self.assertFalse(first.live)
        self.assertFalse(second.live)
        self.assertEqual((cb1.lifecycle, cb2.lifecycle), (
            CommandBufferLifecycle.INVALID, CommandBufferLifecycle.INVALID,
        ))
        self.assertFalse(already_freed.live)

    def test_destroy_descriptor_pool_type_error_precedes_lifecycle_checks(self) -> None:
        pool = DescriptorPoolLifetime(
            correct_type_and_ownership=False,
            sets=[DescriptorSetLifetime(pending_use=True)],
        )
        before = copy.deepcopy(pool)
        self.assertEqual(destroy_descriptor_pool(pool), "BadMatch")
        self.assertEqual(pool, before)


class UpdateDescriptorSetsIndirectReferenceTests(unittest.TestCase):
    def test_update_replaces_derived_buffer_refs_for_executable_cb(self) -> None:
        descriptor_set = DescriptorSetLifetime(slots={0: "buffer-A", 1: "buffer-B"})
        cb = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.EXECUTABLE,
            descriptor_sets=[descriptor_set],
            indirect_buffer_refs={"buffer-A", "buffer-B"},
            entries=[b"recorded bind"],
        )
        self.assertEqual(
            update_descriptor_sets(
                [descriptor_set],
                (DescriptorWrite(0, 0, "buffer-C"), DescriptorWrite(0, 1, None)),
                [cb],
            ),
            "SUCCESS",
        )
        self.assertEqual(descriptor_set.slots, {0: "buffer-C"})
        self.assertEqual(cb.indirect_buffer_refs, {"buffer-C"})
        self.assertEqual(cb.lifecycle, CommandBufferLifecycle.EXECUTABLE)
        self.assertEqual(cb.entries, [b"recorded bind"])

    def test_duplicate_slot_writes_are_rejected_atomically(self) -> None:
        descriptor_set = DescriptorSetLifetime(slots={0: "buffer-A"})
        buffer_a = BufferMemoryLifetime(identity="buffer-A", descriptor_slot_refs=1)
        buffer_b = BufferMemoryLifetime(identity="buffer-B")
        cb = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.EXECUTABLE,
            descriptor_sets=[descriptor_set],
            indirect_buffer_refs={"buffer-A"},
        )
        before = copy.deepcopy((descriptor_set, buffer_a, buffer_b, cb))
        self.assertEqual(
            update_descriptor_sets(
                [descriptor_set],
                (DescriptorWrite(0, 0, "buffer-B"), DescriptorWrite(0, 0, None)),
                [cb], buffers=[buffer_a, buffer_b],
            ),
            "BadValue",
        )
        self.assertEqual((descriptor_set, buffer_a, buffer_b, cb), before)

    def test_update_rejects_pending_affected_set_atomically(self) -> None:
        pending_set = DescriptorSetLifetime(
            slots={0: "buffer-A"}, pending_use=True,
            pending_submission_refs=1,
        )
        other_set = DescriptorSetLifetime(slots={0: "buffer-C"})
        buffer_a = BufferMemoryLifetime(identity="buffer-A", descriptor_slot_refs=1)
        buffer_b = BufferMemoryLifetime(identity="buffer-B")
        buffer_c = BufferMemoryLifetime(identity="buffer-C", descriptor_slot_refs=1)
        cb = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.EXECUTABLE,
            descriptor_sets=[pending_set, other_set],
            indirect_buffer_refs={"buffer-A", "buffer-C"},
        )
        before = copy.deepcopy((pending_set, other_set, buffer_a, buffer_b, buffer_c, cb))

        self.assertEqual(
            update_descriptor_sets(
                [pending_set, other_set],
                (DescriptorWrite(0, 0, "buffer-B"), DescriptorWrite(1, 0, None)),
                [cb], buffers=[buffer_a, buffer_b, buffer_c],
            ),
            "INVALID_SYNCHRONIZATION_STATE",
        )
        self.assertEqual(
            (pending_set, other_set, buffer_a, buffer_b, buffer_c, cb), before,
        )

    def test_update_batch_validation_failure_preserves_slots_and_all_cb_refs(self) -> None:
        descriptor_set = DescriptorSetLifetime(slots={0: "buffer-A"})
        cb = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.EXECUTABLE,
            descriptor_sets=[descriptor_set],
            indirect_buffer_refs={"buffer-A"},
        )
        before = copy.deepcopy((descriptor_set, cb))
        self.assertEqual(
            update_descriptor_sets(
                [descriptor_set],
                (DescriptorWrite(0, 0, "buffer-B"), DescriptorWrite(7, 0, "buffer-C")),
                [cb],
            ),
            "BadValue",
        )
        self.assertEqual((descriptor_set, cb), before)

    def test_update_refreshes_only_nonpending_cb_refs(self) -> None:
        descriptor_set = DescriptorSetLifetime(slots={0: "buffer-A"})
        executable = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.EXECUTABLE,
            descriptor_sets=[descriptor_set],
            indirect_buffer_refs={"buffer-A"},
        )
        pending = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.PENDING,
            descriptor_sets=[descriptor_set],
            indirect_buffer_refs={"buffer-A"},
        )
        self.assertEqual(
            update_descriptor_sets(
                [descriptor_set], (DescriptorWrite(0, 0, "buffer-B"),),
                [executable, pending],
            ),
            "SUCCESS",
        )
        self.assertEqual(executable.indirect_buffer_refs, {"buffer-B"})
        # Accepted work keeps its old internal reference until terminal completion.
        self.assertEqual(pending.indirect_buffer_refs, {"buffer-A"})
        self.assertEqual(descriptor_set.slots, {0: "buffer-B"})

    def test_update_shared_set_refreshes_every_nonpending_cb_indirect_ref(self) -> None:
        descriptor_set = DescriptorSetLifetime(slots={0: "buffer-old"})
        first = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.RECORDING,
            descriptor_sets=[descriptor_set], indirect_buffer_refs={"buffer-old"},
        )
        second = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.EXECUTABLE,
            descriptor_sets=[descriptor_set], indirect_buffer_refs={"buffer-old"},
        )
        self.assertEqual(
            update_descriptor_sets(
                [descriptor_set], (DescriptorWrite(0, 0, "buffer-new"),),
                [first, second],
            ),
            "SUCCESS",
        )
        self.assertEqual(first.indirect_buffer_refs, {"buffer-new"})
        self.assertEqual(second.indirect_buffer_refs, {"buffer-new"})
        self.assertEqual((first.lifecycle, second.lifecycle), (
            CommandBufferLifecycle.RECORDING, CommandBufferLifecycle.EXECUTABLE,
        ))

    def test_clearing_descriptor_slot_releases_indirect_reference_only(self) -> None:
        descriptor_set = DescriptorSetLifetime(slots={0: "buffer-A", 1: "buffer-B"})
        cb = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.EXECUTABLE,
            descriptor_sets=[descriptor_set],
            indirect_buffer_refs={"buffer-A", "buffer-B"},
        )
        self.assertEqual(
            update_descriptor_sets(
                [descriptor_set], (DescriptorWrite(0, 0, None),), [cb],
            ),
            "SUCCESS",
        )
        self.assertEqual(cb.indirect_buffer_refs, {"buffer-B"})
        self.assertEqual(descriptor_set.slots, {1: "buffer-B"})



class BufferAndMemoryDeferredLifetimeTests(unittest.TestCase):
    def test_buffer_destroy_is_atomic_while_recording_or_accepted_work_uses_it(self) -> None:
        for changes in (
            {"recording_refs": [CommandBufferModel(lifecycle=CommandBufferLifecycle.RECORDING)]},
            {"accepted_uses": 1},
        ):
            with self.subTest(changes=changes):
                buffer = BufferMemoryLifetime(**changes)
                cb_refs = copy.deepcopy(buffer.recording_refs)
                before = copy.deepcopy(buffer)
                self.assertEqual(destroy_buffer_lifetime(buffer), "INVALID_SYNCHRONIZATION_STATE")
                self.assertEqual(buffer, before)
                self.assertEqual(buffer.recording_refs, cb_refs)

    def test_destroy_invalidates_xid_but_descriptor_slot_keeps_internal_buffer_and_memory_bound(self) -> None:
        cb = CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE, indirect_buffer_refs={"buffer-A"})
        buffer = BufferMemoryLifetime(
            executable_refs=[cb], descriptor_slot_refs=1,
        )
        memory = MemoryAllocationLifetime()
        self.assertEqual(destroy_buffer_lifetime(buffer), "SUCCESS")
        self.assertFalse(buffer.xid_valid)
        self.assertEqual(buffer.internal_state, "DESTROY_PENDING")
        self.assertEqual(cb.lifecycle, CommandBufferLifecycle.INVALID)
        before = copy.deepcopy(memory)
        self.assertEqual(free_memory_lifetime(memory, [buffer]), "BadMatch")
        self.assertEqual(memory, before)
        self.assertTrue(memory.xid_valid)

    def test_descriptor_slot_removal_releases_destroyed_buffer_only_after_backend_quiescence(self) -> None:
        buffer = BufferMemoryLifetime(
            descriptor_slot_refs=1, backend_accesses=1,
        )
        self.assertEqual(destroy_buffer_lifetime(buffer), "SUCCESS")
        self.assertEqual(buffer.internal_state, "DESTROY_PENDING")
        self.assertEqual(drop_buffer_internal_ref(buffer, descriptor_slots=1), "SUCCESS")
        self.assertEqual(buffer.internal_state, "DESTROY_PENDING")
        self.assertEqual(drop_buffer_internal_ref(buffer, backend_accesses=1), "SUCCESS")
        self.assertEqual(buffer.internal_state, "RELEASED")
        memory = MemoryAllocationLifetime()
        self.assertEqual(free_memory_lifetime(memory, [buffer]), "SUCCESS")
        self.assertFalse(memory.xid_valid)

    def test_free_memory_rejects_accepted_gpu_use_even_if_no_buffer_is_bound(self) -> None:
        memory = MemoryAllocationLifetime(accepted_uses=1)
        before = copy.deepcopy(memory)
        self.assertEqual(free_memory_lifetime(memory, []), "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual(memory, before)

    def test_free_memory_rejects_backend_access_after_public_buffer_destroy(self) -> None:
        buffer = BufferMemoryLifetime(backend_accesses=1)
        memory = MemoryAllocationLifetime()
        self.assertEqual(destroy_buffer_lifetime(buffer), "SUCCESS")
        before = copy.deepcopy((memory, buffer))
        self.assertEqual(free_memory_lifetime(memory, [buffer]), "BadMatch")
        self.assertEqual((memory, buffer), before)
        self.assertEqual(drop_buffer_internal_ref(buffer, backend_accesses=1), "SUCCESS")
        self.assertEqual(free_memory_lifetime(memory, [buffer]), "SUCCESS")

    def test_rejected_internal_ref_drop_does_not_change_counts(self) -> None:
        buffer = BufferMemoryLifetime(descriptor_slot_refs=1, accepted_uses=1)
        before = copy.deepcopy(buffer)
        self.assertEqual(drop_buffer_internal_ref(buffer, descriptor_slots=2), "BadValue")
        self.assertEqual(buffer, before)



class StaleDescriptorBufferReferenceTests(unittest.TestCase):
    def test_destroyed_buffer_keeps_memory_bound_until_stale_slot_is_rewritten(self) -> None:
        buffer = BufferMemoryLifetime(descriptor_slot_refs=1)
        memory = MemoryAllocationLifetime()
        descriptor_set = DescriptorSetLifetime(slots={0: buffer.identity})
        cb = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.EXECUTABLE,
            descriptor_sets=[descriptor_set],
            indirect_buffer_refs={buffer.identity},
        )
        self.assertEqual(destroy_buffer_lifetime(buffer), "SUCCESS")
        self.assertEqual(buffer.internal_state, "DESTROY_PENDING")
        self.assertEqual(descriptor_contents_submit_valid([descriptor_set], [buffer]),
                         "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual(free_memory_lifetime(memory, [buffer]), "BadMatch")

        replacement = BufferMemoryLifetime(identity="buffer-B", memory_identity="memory-B")
        self.assertEqual(
            update_descriptor_sets(
                [descriptor_set], (DescriptorWrite(0, 0, replacement.identity),),
                [cb], buffers=[buffer, replacement],
            ),
            "SUCCESS",
        )
        self.assertEqual(buffer.descriptor_slot_refs, 0)
        self.assertEqual(buffer.internal_state, "RELEASED")
        self.assertEqual(replacement.descriptor_slot_refs, 1)
        self.assertEqual(cb.indirect_buffer_refs, {replacement.identity})
        self.assertEqual(descriptor_contents_submit_valid([descriptor_set], [buffer, replacement]), "SUCCESS")
        self.assertEqual(free_memory_lifetime(memory, [buffer]), "SUCCESS")

    def test_update_cannot_reintroduce_destroyed_buffer_and_is_atomic(self) -> None:
        destroyed = BufferMemoryLifetime(xid_valid=False, live=False, internal_state="DESTROY_PENDING",
                                         descriptor_slot_refs=1)
        descriptor_set = DescriptorSetLifetime(slots={0: destroyed.identity})
        cb = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.EXECUTABLE,
            descriptor_sets=[descriptor_set],
            indirect_buffer_refs={destroyed.identity},
        )
        before = copy.deepcopy((destroyed, descriptor_set, cb))
        self.assertEqual(
            update_descriptor_sets(
                [descriptor_set], (DescriptorWrite(0, 1, destroyed.identity),),
                [cb], buffers=[destroyed],
            ),
            "BadValue",
        )
        self.assertEqual((destroyed, descriptor_set, cb), before)

    def test_rewriting_one_of_two_slots_preserves_other_internal_reference(self) -> None:
        first = BufferMemoryLifetime(identity="buffer-A", descriptor_slot_refs=2)
        second = BufferMemoryLifetime(identity="buffer-B")
        descriptor_set = DescriptorSetLifetime(slots={0: "buffer-A", 1: "buffer-A"})
        cb = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.EXECUTABLE,
            descriptor_sets=[descriptor_set],
            indirect_buffer_refs={"buffer-A"},
        )
        self.assertEqual(
            update_descriptor_sets(
                [descriptor_set], (DescriptorWrite(0, 0, "buffer-B"),),
                [cb], buffers=[first, second],
            ),
            "SUCCESS",
        )
        self.assertEqual(first.descriptor_slot_refs, 1)
        self.assertEqual(second.descriptor_slot_refs, 1)
        self.assertEqual(cb.indirect_buffer_refs, {"buffer-A", "buffer-B"})



class DescriptorPoolBufferReferenceReleaseTests(unittest.TestCase):
    def test_free_descriptor_set_releases_stale_buffer_slot_and_unblocks_memory(self) -> None:
        buffer = BufferMemoryLifetime(descriptor_slot_refs=1)
        memory = MemoryAllocationLifetime()
        descriptor_set = DescriptorSetLifetime(slots={0: buffer.identity})
        self.assertEqual(destroy_buffer_lifetime(buffer), "SUCCESS")
        self.assertEqual(free_memory_lifetime(memory, [buffer]), "BadMatch")
        self.assertEqual(free_descriptor_sets([descriptor_set], [buffer]), "SUCCESS")
        self.assertFalse(descriptor_set.live)
        self.assertEqual(descriptor_set.slots, {})
        self.assertEqual(buffer.descriptor_slot_refs, 0)
        self.assertEqual(buffer.internal_state, "RELEASED")
        self.assertEqual(free_memory_lifetime(memory, [buffer]), "SUCCESS")

    def test_destroy_pool_releases_all_child_slot_refs_atomically(self) -> None:
        first = BufferMemoryLifetime(descriptor_slot_refs=2)
        second = BufferMemoryLifetime(identity="buffer-B", descriptor_slot_refs=1)
        memory = MemoryAllocationLifetime()
        pool = DescriptorPoolLifetime(sets=[
            DescriptorSetLifetime(slots={0: first.identity, 1: first.identity}),
            DescriptorSetLifetime(slots={0: second.identity}),
        ])
        self.assertEqual(destroy_buffer_lifetime(first), "SUCCESS")
        self.assertEqual(destroy_buffer_lifetime(second), "SUCCESS")
        self.assertEqual(destroy_descriptor_pool(pool, [first, second]), "SUCCESS")
        self.assertEqual((first.internal_state, second.internal_state), ("RELEASED", "RELEASED"))
        self.assertEqual((first.descriptor_slot_refs, second.descriptor_slot_refs), (0, 0))
        self.assertEqual(free_memory_lifetime(memory, [first, second]), "SUCCESS")

    def test_pool_rejection_preserves_slot_refs_and_stale_buffer_lifetime(self) -> None:
        buffer = BufferMemoryLifetime(descriptor_slot_refs=1)
        descriptor_set = DescriptorSetLifetime(slots={0: buffer.identity}, recording_refs=1)
        pool = DescriptorPoolLifetime(sets=[descriptor_set])
        self.assertEqual(destroy_buffer_lifetime(buffer), "SUCCESS")
        before = copy.deepcopy((buffer, descriptor_set, pool))
        self.assertEqual(destroy_descriptor_pool(pool, [buffer]), "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual((buffer, descriptor_set, pool), before)
        self.assertEqual(buffer.internal_state, "DESTROY_PENDING")

    def test_free_set_rejects_reference_count_underflow_without_partial_release(self) -> None:
        first = BufferMemoryLifetime(descriptor_slot_refs=1)
        second = BufferMemoryLifetime(identity="buffer-B", descriptor_slot_refs=0)
        descriptor_set = DescriptorSetLifetime(slots={0: first.identity, 1: second.identity})
        before = copy.deepcopy((first, second, descriptor_set))
        self.assertEqual(free_descriptor_sets([descriptor_set], [first, second]),
                         "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual((first, second, descriptor_set), before)



class ConcurrentAcceptedSubmissionResourceReferenceTests(unittest.TestCase):
    def shared_state(self):
        buffer = BufferMemoryLifetime(descriptor_slot_refs=1)
        descriptor_set = DescriptorSetLifetime(slots={0: buffer.identity})
        first = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.EXECUTABLE,
            descriptor_sets=[descriptor_set], indirect_buffer_refs={buffer.identity},
        )
        second = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.EXECUTABLE,
            descriptor_sets=[descriptor_set], indirect_buffer_refs={buffer.identity},
        )
        state = SubmissionModel(command_buffers=[first, second], buffer_registry=[buffer])
        return state, descriptor_set, buffer

    def test_device_loss_terminalizes_submission_but_preserves_backend_hold(self) -> None:
        buffer = BufferMemoryLifetime(backend_accesses=1)
        command_buffer = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.EXECUTABLE,
            indirect_buffer_refs={buffer.identity},
        )
        state = SubmissionModel(
            command_buffers=[command_buffer], buffer_registry=[buffer],
        )
        memory = MemoryAllocationLifetime()
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=803, command_buffer_indices=(0,))),
            "SUCCESS",
        )
        self.assertEqual((buffer.accepted_uses, buffer.backend_accesses), (1, 1))

        # Simulate device-wide public invalidation while backend cleanup still
        # holds the internal allocation identity.
        buffer.xid_valid = False
        buffer.live = False
        buffer.internal_state = "DESTROY_PENDING"
        self.assertEqual(mark_device_lost(state), "SUCCESS")
        self.assertEqual(command_buffer.lifecycle, CommandBufferLifecycle.INVALID)
        self.assertEqual(buffer.accepted_uses, 0)
        self.assertEqual(buffer.backend_accesses, 1)
        self.assertEqual(buffer.internal_state, "DESTROY_PENDING")
        self.assertEqual(free_memory_lifetime(memory, [buffer]), "BadMatch")

        # Only proven backend quiescence releases the final internal hold.
        self.assertEqual(drop_buffer_internal_ref(buffer, backend_accesses=1), "SUCCESS")
        self.assertEqual(buffer.internal_state, "RELEASED")
        self.assertEqual(free_memory_lifetime(memory, [buffer]), "SUCCESS")


    def test_out_of_order_terminal_callbacks_release_only_their_own_refs(self) -> None:
        state, descriptor_set, buffer = self.shared_state()
        self.assertEqual(queue_submit(state, SubmitRequest(token=801, command_buffer_indices=(0,))), "SUCCESS")
        self.assertEqual(queue_submit(state, SubmitRequest(token=802, command_buffer_indices=(1,))), "SUCCESS")
        self.assertEqual(descriptor_set.pending_submission_refs, 2)
        self.assertEqual(buffer.accepted_uses, 2)
        self.assertEqual(finish_submission(state, 802, True), "SUCCESS")
        self.assertEqual(descriptor_set.pending_submission_refs, 1)
        self.assertEqual(buffer.accepted_uses, 1)
        self.assertEqual(free_descriptor_sets([descriptor_set], [buffer]),
                         "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual(destroy_buffer_lifetime(buffer), "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual(finish_submission(state, 801, False), "SUCCESS")
        self.assertEqual(descriptor_set.pending_submission_refs, 0)
        self.assertEqual(buffer.accepted_uses, 0)
        self.assertEqual(finish_submission(state, 801, False), "BadValue")
        self.assertEqual((descriptor_set.pending_submission_refs, buffer.accepted_uses), (0, 0))

    def test_descriptor_update_keeps_each_submission_snapshot_until_its_callback(self) -> None:
        old = BufferMemoryLifetime(identity="buffer-old", descriptor_slot_refs=1)
        new = BufferMemoryLifetime(identity="buffer-new", memory_identity="memory-B")
        descriptor_set = DescriptorSetLifetime(slots={0: old.identity})
        cbs = [
            CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE,
                descriptor_sets=[descriptor_set], indirect_buffer_refs={old.identity})
            for _ in range(2)
        ]
        state = SubmissionModel(command_buffers=cbs, buffer_registry=[old, new])
        self.assertEqual(queue_submit(state, SubmitRequest(token=811, command_buffer_indices=(0,))), "SUCCESS")
        self.assertEqual(queue_submit(state, SubmitRequest(token=812, command_buffer_indices=(1,))), "SUCCESS")
        self.assertEqual(old.accepted_uses, 2)
        before = copy.deepcopy((descriptor_set, old, new, cbs))
        self.assertEqual(update_descriptor_sets(
            [descriptor_set], (DescriptorWrite(0, 0, new.identity),), cbs,
            buffers=[old, new],
        ), "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual((descriptor_set, old, new, cbs), before)
        self.assertEqual((old.accepted_uses, new.accepted_uses), (2, 0))
        self.assertEqual(finish_submission(state, 812, True), "SUCCESS")
        self.assertEqual((old.accepted_uses, new.accepted_uses), (1, 0))
        self.assertEqual(update_descriptor_sets(
            [descriptor_set], (DescriptorWrite(0, 0, new.identity),), cbs,
            buffers=[old, new],
        ), "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual(finish_submission(state, 811, False), "SUCCESS")
        self.assertEqual((old.accepted_uses, new.accepted_uses), (0, 0))
        self.assertEqual(update_descriptor_sets(
            [descriptor_set], (DescriptorWrite(0, 0, new.identity),), cbs,
            buffers=[old, new],
        ), "SUCCESS")
        self.assertEqual(descriptor_set.slots, {0: new.identity})
        self.assertEqual((old.descriptor_slot_refs, new.descriptor_slot_refs), (0, 1))

    def test_destroyed_buffer_waits_for_all_submissions_and_backend_access(self) -> None:
        state, descriptor_set, buffer = self.shared_state()
        self.assertEqual(queue_submit(state, SubmitRequest(token=821, command_buffer_indices=(0,))), "SUCCESS")
        self.assertEqual(queue_submit(state, SubmitRequest(token=822, command_buffer_indices=(1,))), "SUCCESS")
        # A legal DestroyResource is blocked until accepted uses are terminal.
        self.assertEqual(destroy_buffer_lifetime(buffer), "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual(finish_submission(state, 821, True), "SUCCESS")
        self.assertEqual(buffer.accepted_uses, 1)
        self.assertEqual(finish_submission(state, 822, False), "SUCCESS")
        self.assertEqual(buffer.accepted_uses, 0)
        buffer.backend_accesses = 1
        self.assertEqual(destroy_buffer_lifetime(buffer), "SUCCESS")
        self.assertEqual(buffer.internal_state, "DESTROY_PENDING")
        self.assertEqual(free_descriptor_sets([descriptor_set], [buffer]), "SUCCESS")
        self.assertEqual(buffer.descriptor_slot_refs, 0)
        self.assertEqual(drop_buffer_internal_ref(buffer, backend_accesses=1), "SUCCESS")
        self.assertEqual(buffer.internal_state, "RELEASED")


class SemaphoreOwnerReferenceTests(unittest.TestCase):
    def test_registration_prunes_dead_and_duplicate_owner_references(self) -> None:
        shared = SharedBinarySemaphore()
        owner = SubmissionModel(shared_semaphores=[shared])
        # Model pre-existing corruption that can arise after repeated setup or
        # from stale test fixtures: duplicate refs to one live owner and a dead
        # owner ref. Registering another model must normalize the whole list.
        shared.owners.append(ref(owner))
        stale_owner = SubmissionModel(shared_semaphores=[shared])
        stale_ref = ref(stale_owner)
        del stale_owner
        gc.collect()
        self.assertIsNone(stale_ref())

        newcomer = SubmissionModel(shared_semaphores=[shared])
        registered = [owner_ref() for owner_ref in shared.owners]
        self.assertEqual(len(registered), 2)
        self.assertEqual({id(item) for item in registered if item is not None},
                         {id(owner), id(newcomer)})
        self.assertTrue(all(item is not None for item in registered))


    def test_disconnect_unregisters_only_the_disconnected_semaphore_owner(self) -> None:
        shared = SharedBinarySemaphore()
        disconnected = SubmissionModel(shared_semaphores=[shared, shared])
        surviving = PresentState(shared_semaphores=[shared])
        # Simulate duplicate registration of both owners and an owner that died
        # before its connection cleanup ran. Disconnect must remove every
        # matching weakref, deduplicate surviving owners, and prune dead entries
        # even when the disconnected model lists one semaphore more than once.
        shared.owners.extend([ref(disconnected), ref(surviving), ref(surviving)])
        stale_owner = SubmissionModel(shared_semaphores=[shared])
        stale_ref = ref(stale_owner)
        del stale_owner
        gc.collect()
        self.assertIsNone(stale_ref())

        _unregister_semaphore_owner(disconnected)
        _unregister_semaphore_owner(disconnected)
        remaining = [owner_ref() for owner_ref in shared.owners]
        self.assertEqual(remaining, [surviving])
        # Keep the disconnected model's local references for late callback
        # cleanup; unregistering must not destroy shared synchronization state.
        self.assertEqual(disconnected.shared_semaphores, [shared, shared])


    def test_device_loss_traversal_prunes_dead_and_duplicate_owner_references(self) -> None:
        shared = SharedBinarySemaphore()
        owner = SubmissionModel(shared_semaphores=[shared])
        shared.owners.append(ref(owner))
        stale_owner = PresentState(shared_semaphores=[shared])
        stale_ref = ref(stale_owner)
        del stale_owner
        gc.collect()
        self.assertIsNone(stale_ref())

        self.assertEqual(mark_device_lost(owner), "SUCCESS")
        registered = [owner_ref() for owner_ref in shared.owners]
        self.assertEqual(registered, [owner])
        self.assertEqual(len(registered), 1)


class BinarySemaphoreStaleCallbackTests(unittest.TestCase):
    def test_duplicate_old_signal_callback_cannot_mutate_reused_semaphore_cycle(self) -> None:
        shared = SharedBinarySemaphore()
        first = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(first, SubmitRequest(token=201, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        self.assertEqual(finish_submission(first, 201, success=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.SIGNALED)

        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNALED],
            shared_semaphores=[shared],
        )
        self.assertTrue(queue_present(present, PresentRequest(token=202, wait_indices=(0,))).accepted)
        self.assertEqual(finish_present_wait(present, 202, 0, consumed=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)

        second = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(second, SubmitRequest(token=203, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        before_shared = copy.deepcopy(shared)
        before_second = copy.deepcopy(second)
        # Duplicate terminal notification for the old submission must be a
        # mutation-free rejection, not clear the new signal reservation.
        self.assertEqual(finish_submission(first, 201, success=False), "BadValue")
        self.assertEqual(shared, before_shared)
        self.assertEqual(second, before_second)
        self.assertEqual(shared.signal_reservation, ("submit", 203))
        self.assertEqual(shared.signal_state, BinarySignalState.SIGNAL_PENDING)



    def test_disconnected_signal_callback_quarantines_local_wait_state_after_device_loss(self) -> None:
        shared = SharedBinarySemaphore()
        submit = self._shared_signal_submission(shared, 204)
        self.assertEqual(
            queue_submit(submit, SubmitRequest(token=204, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        self.assertEqual(shared.signal_reservation, ("submit", 204))

        observer = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            shared_semaphores=[shared],
        )
        # Disconnect removes the submission model from loss fan-out, but does
        # not cancel the accepted backend operation or release its local refs.
        _unregister_semaphore_owner(submit)
        self.assertNotIn(submit, [owner_ref() for owner_ref in shared.owners])
        self.assertEqual(mark_present_device_lost(observer), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)
        self.assertIsNone(shared.signal_reservation)
        self.assertEqual(submit.wait_states, [WaitState.READY])

        # The late signal callback must drain its token exactly once while
        # reconciling the disconnected model's local wait eligibility. It may
        # not restore canonical semaphore state after loss retired its owner.
        self.assertEqual(finish_submission(submit, 204, success=True), "SUCCESS")
        self.assertEqual(submit.pending_submissions, [])
        self.assertEqual(submit.binary_signal_states, [BinarySignalState.UNTRUSTED])
        self.assertEqual(submit.wait_states, [WaitState.UNTRUSTED])
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)
        self.assertIsNone(shared.signal_reservation)
        after_first = copy.deepcopy((submit, observer, shared))
        self.assertEqual(finish_submission(submit, 204, success=False), "BadValue")
        self.assertEqual((submit, observer, shared), after_first)


    def _shared_signal_submission(self, shared: SharedBinarySemaphore, token: int) -> SubmissionModel:
        return SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[shared.signal_state],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )

    def _shared_present(self, shared: SharedBinarySemaphore, token: int) -> PresentState:
        return PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[shared.signal_state],
            shared_semaphores=[shared],
        )

    def test_present_consumption_before_submit_signal_callback_is_not_resurrected(self) -> None:
        shared = SharedBinarySemaphore()
        submit = self._shared_signal_submission(shared, 301)
        self.assertEqual(
            queue_submit(submit, SubmitRequest(token=301, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        present = self._shared_present(shared, 302)
        self.assertTrue(queue_present(present, PresentRequest(token=302, wait_indices=(0,))).accepted)
        self.assertEqual(shared.signal_reservation, ("submit", 301))
        self.assertEqual(shared.wait_reservation, ("present", 302))

        # Presentation proves consumption before the submit completion arrives.
        self.assertEqual(finish_present_wait(present, 302, 0, consumed=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertTrue(shared.signal_consumed)
        self.assertEqual(finish_submission(submit, 301, success=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertIsNone(shared.signal_reservation)
        self.assertFalse(shared.signal_consumed)

    def test_submit_signal_callback_before_present_consumption_is_not_resurrected(self) -> None:
        shared = SharedBinarySemaphore()
        submit = self._shared_signal_submission(shared, 311)
        self.assertEqual(
            queue_submit(submit, SubmitRequest(token=311, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        present = self._shared_present(shared, 312)
        self.assertTrue(queue_present(present, PresentRequest(token=312, wait_indices=(0,))).accepted)

        self.assertEqual(finish_submission(submit, 311, success=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.SIGNALED)
        self.assertIsNone(shared.signal_reservation)
        self.assertEqual(finish_present_wait(present, 312, 0, consumed=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertIsNone(shared.wait_reservation)
        self.assertEqual(present.pending_present_waits, [])

    def test_submit_and_present_cannot_both_reserve_the_same_binary_wait(self) -> None:
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED)
        present = self._shared_present(shared, 321)
        self.assertTrue(queue_present(present, PresentRequest(token=321, wait_indices=(0,))).accepted)
        submit = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        before = copy.deepcopy(shared)
        self.assertEqual(queue_submit(submit, SubmitRequest(token=322, wait_indices=(0,))), "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual(shared, before)
        self.assertEqual(shared.wait_reservation, ("present", 321))
        self.assertNotIn(322, submit.accepted_tokens)



    def test_duplicate_old_present_wait_callback_cannot_mutate_reused_submit_signal(self) -> None:
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED)
        old_present = self._shared_present(shared, 401)
        self.assertTrue(
            queue_present(
                old_present, PresentRequest(token=401, wait_indices=(0,))
            ).accepted
        )
        self.assertEqual(
            finish_present_wait(old_present, 401, 0, consumed=True), "SUCCESS"
        )
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertIsNone(shared.wait_reservation)

        new_submit = self._shared_signal_submission(shared, 402)
        self.assertEqual(
            queue_submit(
                new_submit,
                SubmitRequest(token=402, signal_indices=(0,), signal_values=(0,)),
            ),
            "SUCCESS",
        )
        before = copy.deepcopy((shared, new_submit, old_present))

        # A duplicated callback from the previous wait generation must not
        # clear the new submit's signal reservation or rewrite its payload.
        self.assertEqual(
            finish_present_wait(old_present, 401, 0, consumed=False), "BadValue"
        )
        self.assertEqual((shared, new_submit, old_present), before)
        self.assertEqual(shared.signal_reservation, ("submit", 402))
        self.assertEqual(shared.signal_state, BinarySignalState.SIGNAL_PENDING)

class BinaryDeviceLossReservationTests(unittest.TestCase):
    def test_device_loss_quarantines_uncertain_binary_signal_and_releases_reservation_once(self) -> None:
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)
        state = SubmissionModel(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
            ],
            wait_states=[],
            signal_slots=[None],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=331, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        self.assertEqual(shared.signal_reservation, ("submit", 331))
        self.assertEqual(shared.signal_state, BinarySignalState.SIGNAL_PENDING)

        self.assertEqual(mark_device_lost(state), "SUCCESS")
        self.assertEqual(state.pending_submissions, [])
        self.assertIsNone(shared.signal_reservation)
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)
        self.assertEqual(state.binary_signal_states, [BinarySignalState.UNTRUSTED])

        # A late backend callback cannot turn the uncertain payload into a
        # confirmed signal or release another operation's reservation.
        before = copy.deepcopy((state, shared))
        self.assertEqual(finish_submission(state, 331, success=True), "BadValue")
        self.assertEqual((state, shared), before)


class BinaryWaitReservationFailureTests(unittest.TestCase):
    def make_submit(self, shared: SharedBinarySemaphore) -> SubmissionModel:
        return SubmissionModel(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
                for _ in range(3)
            ],
            wait_states=[WaitState.READY],
            binary_signal_states=[shared.signal_state],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )

    def test_late_submit_wait_callback_cannot_overwrite_new_shared_reservation(self) -> None:
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED)
        state = self.make_submit(shared)
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=300, wait_indices=(0,))),
            "SUCCESS",
        )
        # Model a lifecycle path that retires the old reservation and lets a
        # newer presentation own the canonical semaphore before the old
        # backend callback is delivered.
        shared.wait_reservation = ("present", 301)
        shared.signal_state = BinarySignalState.SIGNALED
        before_local = list(state.binary_signal_states)

        self.assertEqual(finish_submission(state, 300, success=True), "SUCCESS")
        self.assertEqual(shared.wait_reservation, ("present", 301))
        self.assertEqual(shared.signal_state, BinarySignalState.SIGNALED)
        self.assertEqual(state.binary_signal_states, [BinarySignalState.UNSIGNALED])
        self.assertNotEqual(state.binary_signal_states, before_local)

    def test_failed_wait_with_unchanged_payload_releases_only_wait_reservation(self) -> None:
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED)
        state = self.make_submit(shared)
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=301, wait_indices=(0,))),
            "SUCCESS",
        )
        self.assertEqual(shared.wait_reservation, ("submit", 301))
        self.assertEqual(
            finish_submission(
                state, 301, success=False,
                binary_payload_unchanged={("wait", 0)},
            ),
            "SUCCESS",
        )
        self.assertIsNone(shared.wait_reservation)
        self.assertEqual(shared.signal_state, BinarySignalState.SIGNALED)
        self.assertEqual(state.binary_signal_states, [BinarySignalState.SIGNALED])
        self.assertEqual(state.wait_states, [WaitState.READY])
        # The confirmed signal is reusable by a later wait after terminal cleanup.
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=302, command_buffer_indices=(1,), wait_indices=(0,))),
            "SUCCESS",
        )
        self.assertEqual(shared.wait_reservation, ("submit", 302))

    def test_failed_wait_with_unknown_payload_releases_reservation_but_poison_semaphore(self) -> None:
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED)
        state = self.make_submit(shared)
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=311, wait_indices=(0,))),
            "SUCCESS",
        )
        self.assertEqual(shared.wait_reservation, ("submit", 311))
        self.assertEqual(finish_submission(state, 311, success=False), "SUCCESS")
        self.assertIsNone(shared.wait_reservation)
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)
        self.assertEqual(state.binary_signal_states, [BinarySignalState.UNTRUSTED])
        self.assertEqual(state.wait_states, [WaitState.UNTRUSTED])
        before = copy.deepcopy(state)
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=312, command_buffer_indices=(1,), wait_indices=(0,))),
            "DEPENDENCY_FAILED",
        )
        self.assertEqual(state, before)
        self.assertIsNone(shared.wait_reservation)

    def test_unknown_present_wait_outcome_does_not_release_signal_as_available(self) -> None:
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED)
        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNALED],
            shared_semaphores=[shared],
        )
        self.assertTrue(queue_present(present, PresentRequest(token=321, wait_indices=(0,))).accepted)
        self.assertEqual(shared.wait_reservation, ("present", 321))
        self.assertEqual(finish_present_wait(present, 321, 0, consumed=None), "SUCCESS")
        self.assertIsNone(shared.wait_reservation)
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)
        self.assertEqual(present.wait_states, [WaitState.UNTRUSTED])
        present.image_state = ImageState.ACQUIRED  # independent image-release callback
        before = copy.deepcopy(present)
        result = queue_present(present, PresentRequest(token=322, wait_indices=(0,)))
        self.assertEqual((result.result, result.accepted), ("DEPENDENCY_FAILED", False))
        self.assertEqual(present, before)


class CommandBufferResetPrecedenceAtomicityTests(unittest.TestCase):
    """Reset error precedence must match the normative validation phases."""

    def _state(self, **overrides):
        values = dict(
            lifecycle=CommandBufferLifecycle.EXECUTABLE,
            entries=[b"retained entry"],
            descriptor_sets=[DescriptorSetLifetime(slots={0: "buffer-retained"})],
            indirect_buffer_refs={"buffer-retained", "indirect-retained"},
            backend_holds=2,
        )
        values.update(overrides)
        return CommandBufferModel(**values)

    def test_reset_error_precedence_is_spec_ordered_and_rejection_is_atomic(self):
        cases = (
            # Device/buffer XID resolution precedes ownership and device state.
            ("xid", {"device_xid_valid": False, "device_available": False},
             {"correct_type_and_ownership": False, "device_lost": True}, "BadValue"),
            # Type/ownership precedes unavailable/lost device status.
            ("ownership", {"device_available": False},
             {"correct_type_and_ownership": False, "device_lost": True}, "BadMatch"),
            # Availability precedes loss, and both precede reset flag/lifecycle.
            ("unavailable", {"device_available": False, "reset_flag": False},
             {"device_lost": True, "lifecycle": CommandBufferLifecycle.PENDING}, "DEVICE_UNAVAILABLE"),
            ("lost", {"reset_flag": False},
             {"device_lost": True, "lifecycle": CommandBufferLifecycle.PENDING}, "DEVICE_LOST"),
            ("flag", {"reset_flag": False},
             {"lifecycle": CommandBufferLifecycle.PENDING}, "INVALID_SYNCHRONIZATION_STATE"),
            ("pending", {},
             {"lifecycle": CommandBufferLifecycle.PENDING}, "INVALID_SYNCHRONIZATION_STATE"),
        )
        for name, kwargs, state_kwargs, expected in cases:
            with self.subTest(name=name):
                state = self._state(**state_kwargs)
                before = copy.deepcopy(state)
                self.assertEqual(reset_command_buffer(state, **kwargs), expected)
                self.assertEqual(state, before)

    def test_successful_reset_moves_only_held_recording_refs_to_retired_epoch(self):
        state = self._state()
        old_epoch = state.recording_epoch
        old_entries = list(state.entries)
        old_sets = list(state.descriptor_sets)
        old_indirect = set(state.indirect_buffer_refs)

        self.assertEqual(reset_command_buffer(state), "SUCCESS")
        self.assertEqual(state.lifecycle, CommandBufferLifecycle.INITIAL)
        self.assertEqual(state.recording_epoch, old_epoch + 1)
        self.assertEqual(state.entries, [])
        self.assertEqual(state.descriptor_sets, [])
        self.assertEqual(state.indirect_buffer_refs, set())
        self.assertEqual(state.backend_holds, 0)
        self.assertEqual(len(state.retired_recordings), 1)
        retired = state.retired_recordings[0]
        self.assertEqual(retired.epoch, old_epoch)
        self.assertEqual(retired.backend_holds, 2)
        self.assertEqual(retired.entries, old_entries)
        self.assertEqual(retired.descriptor_sets, old_sets)
        self.assertEqual(retired.indirect_buffer_refs, old_indirect)

    def test_rejected_reset_and_stale_hold_retirement_are_mutation_free(self):
        state = self._state(lifecycle=CommandBufferLifecycle.PENDING)
        before = copy.deepcopy(state)
        self.assertEqual(reset_command_buffer(state), "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual(state, before)

        before = copy.deepcopy(state)
        self.assertEqual(
            retire_command_buffer_backend_hold(state, recording_epoch=state.recording_epoch + 99),
            "INVALID_SYNCHRONIZATION_STATE",
        )
        self.assertEqual(state, before)

    def test_multiple_successful_resets_keep_each_backend_epoch_independent(self):
        first_set = DescriptorSetLifetime(slots={0: "buffer-epoch-0"})
        state = self._state(
            lifecycle=CommandBufferLifecycle.EXECUTABLE,
            entries=[b"epoch-0"],
            descriptor_sets=[first_set],
            indirect_buffer_refs={"buffer-epoch-0"},
            backend_holds=2,
            recording_epoch=10,
        )
        self.assertEqual(reset_command_buffer(state), "SUCCESS")
        self.assertEqual(state.retired_recordings[0].epoch, 10)

        # A later recording acquires its own hold and references. Resetting it
        # must create a second retired epoch rather than merging old ownership.
        second_set = DescriptorSetLifetime(slots={0: "buffer-epoch-1"})
        state.lifecycle = CommandBufferLifecycle.EXECUTABLE
        state.entries = [b"epoch-1"]
        state.descriptor_sets = [second_set]
        state.indirect_buffer_refs = {"buffer-epoch-1"}
        state.backend_holds = 1
        second_epoch = state.recording_epoch
        self.assertEqual(reset_command_buffer(state), "SUCCESS")
        self.assertEqual(
            [(r.epoch, r.backend_holds) for r in state.retired_recordings],
            [(10, 2), (second_epoch, 1)],
        )

        # Complete the newer epoch first; it must not consume either old hold.
        self.assertEqual(
            retire_command_buffer_backend_hold(state, recording_epoch=second_epoch),
            "SUCCESS",
        )
        self.assertEqual(
            [(r.epoch, r.backend_holds) for r in state.retired_recordings],
            [(10, 2)],
        )
        self.assertEqual(state.retired_recordings[0].entries, [b"epoch-0"])
        self.assertEqual(state.retired_recordings[0].descriptor_sets, [first_set])
        self.assertEqual(state.retired_recordings[0].indirect_buffer_refs, {"buffer-epoch-0"})

        self.assertEqual(retire_command_buffer_backend_hold(state, recording_epoch=10), "SUCCESS")
        self.assertEqual(state.retired_recordings[0].backend_holds, 1)
        self.assertEqual(retire_command_buffer_backend_hold(state, recording_epoch=10), "SUCCESS")
        self.assertEqual(state.retired_recordings, [])
        before = copy.deepcopy(state)
        self.assertEqual(
            retire_command_buffer_backend_hold(state, recording_epoch=10),
            "INVALID_SYNCHRONIZATION_STATE",
        )
        self.assertEqual(state, before)

    def test_reset_success_matrix_covers_all_non_pending_lifecycles(self):
        for lifecycle in (
            CommandBufferLifecycle.INITIAL,
            CommandBufferLifecycle.RECORDING,
            CommandBufferLifecycle.EXECUTABLE,
            CommandBufferLifecycle.INVALID,
        ):
            for holds in (0, 2):
                with self.subTest(lifecycle=lifecycle, holds=holds):
                    descriptor_set = DescriptorSetLifetime(slots={0: "buffer-old"})
                    state = self._state(
                        lifecycle=lifecycle,
                        entries=[b"recorded"],
                        descriptor_sets=[descriptor_set],
                        indirect_buffer_refs={"buffer-old"},
                        backend_holds=holds,
                        recording_epoch=4,
                    )
                    self.assertEqual(reset_command_buffer(state), "SUCCESS")
                    self.assertEqual(state.lifecycle, CommandBufferLifecycle.INITIAL)
                    self.assertEqual(state.recording_epoch, 5)
                    self.assertEqual(state.entries, [])
                    self.assertEqual(state.descriptor_sets, [])
                    self.assertEqual(state.indirect_buffer_refs, set())
                    self.assertEqual(state.backend_holds, 0)
                    if holds:
                        self.assertEqual(len(state.retired_recordings), 1)
                        self.assertEqual(state.retired_recordings[0].epoch, 4)
                        self.assertEqual(state.retired_recordings[0].backend_holds, holds)
                    else:
                        self.assertEqual(state.retired_recordings, [])


class ClientDisconnectCallbackCleanupTests(unittest.TestCase):
    def test_disconnect_drops_event_subscriptions_and_terminal_callback_link(self) -> None:
        registry = AsyncSubmissionEventRegistry(live_connections={"client-A"})
        device = AsyncDeviceIdentity("device-A", 17)
        registry.register_device("client-A", device)
        submission = AsyncSubmissionIdentity(
            token=91,
            connection_identity="client-A",
            device_identity=device.identity,
            device_xid=device.xid,
            queue_key=(0, 0),
        )
        self.assertEqual(registry.accept_submission(submission), "SUCCESS")
        self.assertEqual(
            registry.select_queue_events("client-A", device.identity, (0, 0), 1),
            "SUCCESS",
        )
        key = ("client-A", 91)
        self.assertIn(key, registry.submissions)

        registry.disconnect("client-A")
        self.assertNotIn("client-A", registry.live_connections)
        self.assertFalse(any(connection == "client-A"
                             for connection, _queue in registry.queue_masks))
        # Client-facing links disappear immediately, while accepted backend
        # work remains internally owned until its actual terminal callback.
        self.assertNotIn(key, registry.submissions)
        self.assertIs(registry.detached_submissions[key], submission)
        self.assertEqual(registry.terminal_callback("client-A", 91, "COMPLETE"), "SUCCESS")
        self.assertEqual(submission.terminal, "COMPLETE")
        self.assertNotIn(key, registry.detached_submissions)
        self.assertEqual(registry.emitted_events, [])
        snapshot = dict(registry.detached_submissions)
        self.assertEqual(registry.terminal_callback("client-A", 91, "COMPLETE"), "BadValue")
        self.assertEqual(registry.detached_submissions, snapshot)


class ClientDisconnectWaitRegistrationTests(unittest.TestCase):
    def test_disconnect_cancels_only_connection_waits_not_accepted_work(self) -> None:
        registry = AsyncSubmissionEventRegistry(live_connections={"client-A", "client-B"})
        device = AsyncDeviceIdentity("device-A", 17)
        registry.register_device("client-A", device)
        submission = AsyncSubmissionIdentity(
            token=92,
            connection_identity="client-A",
            device_identity=device.identity,
            device_xid=device.xid,
            queue_key=(0, 0),
        )
        self.assertEqual(registry.accept_submission(submission), "SUCCESS")
        self.assertEqual(
            registry.register_wait("client-A", 101, "WaitSemaphores", ("sem-A", "sem-B")),
            "SUCCESS",
        )
        self.assertEqual(
            registry.register_wait("client-A", 102, "WaitForFence", ("fence-A",)),
            "SUCCESS",
        )
        self.assertEqual(
            registry.register_wait("client-B", 103, "WaitForFence", ("fence-B",)),
            "SUCCESS",
        )

        old_wait_a = registry.wait_registrations[("client-A", 101)]
        old_wait_b = registry.wait_registrations[("client-A", 102)]
        surviving_wait = registry.wait_registrations[("client-B", 103)]
        registry.disconnect("client-A")
        self.assertNotIn(("client-A", 101), registry.wait_registrations)
        self.assertNotIn(("client-A", 102), registry.wait_registrations)
        self.assertIn(("client-B", 103), registry.wait_registrations)
        self.assertNotIn(("client-A", 92), registry.submissions)
        self.assertIs(registry.detached_submissions[("client-A", 92)], submission)

        # A new wait may reuse the connection/token pair, but an old callback
        # must be bound to its captured registration object, not the pair.
        registry.live_connections.add("client-A")
        self.assertEqual(
            registry.register_wait("client-A", 101, "WaitForFence", ("fence-new",)),
            "SUCCESS",
        )
        replacement_wait = registry.wait_registrations[("client-A", 101)]
        self.assertIsNot(replacement_wait, old_wait_a)
        self.assertEqual(registry.finish_wait(old_wait_a), "BadValue")
        self.assertIs(registry.wait_registrations[("client-A", 101)], replacement_wait)
        self.assertEqual(registry.finish_wait(old_wait_b), "BadValue")
        self.assertEqual(registry.finish_wait(surviving_wait), "SUCCESS")
        self.assertEqual(registry.finish_wait(replacement_wait), "SUCCESS")
        # Accepted work still reaches its actual terminal state.
        self.assertEqual(registry.terminal_callback("client-A", 92, "FAILED"), "SUCCESS")
        self.assertEqual(submission.terminal, "FAILED")
        self.assertNotIn(("client-A", 92), registry.detached_submissions)


class SubmitPresentDeviceLossCallbackRaceTests(unittest.TestCase):
    """Device Loss must dominate late cross-API semaphore callback mirrors."""

    def test_late_present_consumed_success_cannot_restore_trust_after_submit_device_loss(self):
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)
        submit = SubmissionModel(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
            ],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(
                submit,
                SubmitRequest(token=801, signal_indices=(0,), signal_values=(0,)),
            ),
            "SUCCESS",
        )

        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_present(present, PresentRequest(token=802, wait_indices=(0,))).result,
            "SUCCESS",
        )
        self.assertEqual(shared.signal_reservation, ("submit", 801))
        self.assertEqual(shared.wait_reservation, ("present", 802))

        # Device Loss terminalizes the submit and quarantines the shared
        # payload, while the already accepted present still owns its wait.
        self.assertEqual(mark_device_lost(submit), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)
        self.assertIsNone(shared.signal_reservation)
        self.assertEqual(shared.wait_reservation, ("present", 802))

        # A late successful-looking Present callback must not downgrade the
        # canonical UNTRUSTED state, even when it reports known consumption.
        self.assertEqual(
            finish_present_wait(present, 802, 0, consumed=True), "SUCCESS"
        )
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)
        self.assertEqual(present.binary_signal_states, [BinarySignalState.UNTRUSTED])
        self.assertEqual(present.wait_states, [WaitState.UNTRUSTED])
        self.assertIsNone(shared.signal_reservation)
        self.assertIsNone(shared.wait_reservation)
        self.assertEqual(present.pending_present_waits, [])

        # Neither terminal callback may mutate state or release another
        # operation's reservations a second time.
        after_terminal = copy.deepcopy((submit, present, shared))
        self.assertEqual(finish_submission(submit, 801, success=True), "BadValue")
        self.assertEqual(
            finish_present_wait(present, 802, 0, consumed=True), "BadValue"
        )
        self.assertEqual((submit, present, shared), after_terminal)


    def test_late_present_nonconsumption_cannot_restore_trust_after_submit_device_loss(self):
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)
        submit = SubmissionModel(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
            ],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(
                submit,
                SubmitRequest(token=803, signal_indices=(0,), signal_values=(0,)),
            ),
            "SUCCESS",
        )
        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            shared_semaphores=[shared],
        )
        self.assertTrue(
            queue_present(present, PresentRequest(token=804, wait_indices=(0,))).accepted
        )

        self.assertEqual(mark_device_lost(submit), "SUCCESS")
        before_present_callback = copy.deepcopy((submit, present, shared))
        self.assertEqual(
            finish_present_wait(present, 804, 0, consumed=False), "SUCCESS"
        )
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)
        self.assertEqual(present.binary_signal_states, [BinarySignalState.UNTRUSTED])
        self.assertEqual(present.wait_states, [WaitState.UNTRUSTED])
        self.assertIsNone(shared.signal_reservation)
        self.assertIsNone(shared.wait_reservation)
        self.assertEqual(present.pending_present_waits, [])

        terminal_state = copy.deepcopy((submit, present, shared))
        self.assertEqual(finish_present_wait(present, 804, 0, consumed=False), "BadValue")
        self.assertEqual(finish_submission(submit, 803, success=False), "BadValue")
        self.assertEqual((submit, present, shared), terminal_state)

    def test_known_present_nonconsumption_then_device_loss_quarantines_pending_signal(self):
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)
        submit = SubmissionModel(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
            ],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(
                submit,
                SubmitRequest(token=805, signal_indices=(0,), signal_values=(0,)),
            ),
            "SUCCESS",
        )
        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            shared_semaphores=[shared],
        )
        self.assertTrue(
            queue_present(present, PresentRequest(token=806, wait_indices=(0,))).accepted
        )

        # Present proves it did not consume the pending signal. That does not
        # prove the Submit signal completed, so a subsequent Device Loss must
        # still quarantine it rather than publishing SIGNALED or UNSIGNALED.
        self.assertEqual(
            finish_present_wait(present, 806, 0, consumed=False), "SUCCESS"
        )
        self.assertEqual(shared.signal_state, BinarySignalState.SIGNAL_PENDING)
        self.assertEqual(shared.signal_reservation, ("submit", 805))
        self.assertIsNone(shared.wait_reservation)

        self.assertEqual(mark_device_lost(submit), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)
        self.assertIsNone(shared.signal_reservation)
        self.assertIsNone(shared.wait_reservation)
        self.assertEqual(submit.binary_signal_states, [BinarySignalState.UNTRUSTED])
        self.assertEqual(submit.pending_submissions, [])

        terminal_state = copy.deepcopy((submit, present, shared))
        self.assertEqual(finish_submission(submit, 805, success=True), "BadValue")
        self.assertEqual(finish_present_wait(present, 806, 0, consumed=True), "BadValue")
        self.assertEqual((submit, present, shared), terminal_state)



    def test_confirmed_signal_consumption_survives_repeated_present_device_loss(self):
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)
        submit = SubmissionModel(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
            ],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(submit, SubmitRequest(
                token=811, signal_indices=(0,), signal_values=(0,)
            )),
            "SUCCESS",
        )
        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            shared_semaphores=[shared],
        )
        self.assertTrue(queue_present(
            present, PresentRequest(token=812, wait_indices=(0,))
        ).accepted)

        # Present confirms that it consumed the Submit signal before the
        # Submit owner receives its terminal callback.
        self.assertEqual(
            finish_present_wait(present, 812, 0, consumed=True), "SUCCESS"
        )
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertTrue(shared.signal_consumed)
        self.assertEqual(shared.signal_reservation, ("submit", 811))

        # Repeated device-loss observations must preserve this positive
        # consumption evidence, rather than treating the known-empty payload
        # as unknown and destroying the owner's retirement token.
        self.assertEqual(mark_present_device_lost(present), "SUCCESS")
        self.assertEqual(mark_present_device_lost(present), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertTrue(shared.signal_consumed)
        self.assertEqual(shared.signal_reservation, ("submit", 811))
        # Device loss fans out immediately, including the submit owner's
        # local mirror, while its pending token remains available for callback
        # retirement.
        self.assertEqual(
            submit.binary_signal_states, [BinarySignalState.UNSIGNALED]
        )

        # The owning Submit callback retires its reservation exactly once;
        # device loss must not resurrect a signal known to have been consumed.
        self.assertEqual(finish_submission(submit, 811, success=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertIsNone(shared.signal_reservation)
        self.assertFalse(shared.signal_consumed)
        self.assertEqual(submit.pending_submissions, [])
        self.assertEqual(submit.pending_binary_signals, [])


    def test_completed_signal_consumption_survives_later_present_device_loss(self):
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)
        submit = SubmissionModel(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
            ],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(submit, SubmitRequest(
                token=813, signal_indices=(0,), signal_values=(0,)
            )),
            "SUCCESS",
        )
        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            shared_semaphores=[shared],
        )
        self.assertTrue(queue_present(
            present, PresentRequest(token=814, wait_indices=(0,))
        ).accepted)
        self.assertEqual(
            finish_present_wait(present, 814, 0, consumed=True), "SUCCESS"
        )
        # The Submit owner has now retired the signal reservation and its
        # consumption marker; the canonical payload is nevertheless known empty.
        self.assertEqual(finish_submission(submit, 813, success=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertIsNone(shared.signal_reservation)
        self.assertFalse(shared.signal_consumed)
        self.assertEqual(submit.binary_signal_states, [BinarySignalState.UNSIGNALED])

        # Device Loss arriving only after that completed callback must not
        # downgrade the known-empty semaphore to UNTRUSTED.
        self.assertEqual(mark_present_device_lost(present), "SUCCESS")
        self.assertEqual(mark_present_device_lost(present), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertIsNone(shared.signal_reservation)
        self.assertFalse(shared.signal_consumed)
        self.assertEqual(present.binary_signal_states, [BinarySignalState.UNSIGNALED])

    def test_present_consumption_before_submit_success_callback_is_not_resurrected(self):
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)
        submit = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(submit, SubmitRequest(token=807, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            shared_semaphores=[shared],
        )
        self.assertTrue(queue_present(present, PresentRequest(token=808, wait_indices=(0,))).accepted)

        # Present confirms consumption before the Submit completion callback
        # arrives. The late Submit callback must not resurrect the payload.
        self.assertEqual(finish_present_wait(present, 808, 0, consumed=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertEqual(shared.signal_reservation, ("submit", 807))
        self.assertTrue(shared.signal_consumed)
        self.assertEqual(finish_submission(submit, 807, success=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertIsNone(shared.signal_reservation)
        self.assertFalse(shared.signal_consumed)
        self.assertEqual(submit.binary_signal_states, [BinarySignalState.UNSIGNALED])
        self.assertEqual(present.binary_signal_states, [BinarySignalState.UNSIGNALED])

    def test_present_consumption_before_submit_failure_callback_preserves_known_empty_payload(self):
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)
        submit = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(submit, SubmitRequest(token=809, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            shared_semaphores=[shared],
        )
        self.assertTrue(queue_present(present, PresentRequest(token=810, wait_indices=(0,))).accepted)
        self.assertEqual(finish_present_wait(present, 810, 0, consumed=True), "SUCCESS")

        # Even a failed completion cannot turn a payload whose consumption is
        # known into UNTRUSTED or SIGNALED.
        self.assertEqual(finish_submission(submit, 809, success=False), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertEqual(shared.signal_reservation, None)
        self.assertFalse(shared.signal_consumed)
        self.assertEqual(submit.binary_signal_states, [BinarySignalState.UNSIGNALED])


class SharedSubmitPresentReservationRaceTests(unittest.TestCase):
    """Cross-API wait reservations are exclusive and callbacks are token-owned."""

    def _submit_state(self, shared):
        return SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[shared.signal_state],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )

    def _present_state(self, shared):
        return PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[shared.signal_state],
            shared_semaphores=[shared],
        )

    def test_submit_wait_reservation_blocks_present_without_mutation(self):
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED)
        submit = self._submit_state(shared)
        self.assertEqual(queue_submit(submit, SubmitRequest(token=601, wait_indices=(0,))), "SUCCESS")
        self.assertEqual(shared.wait_reservation, ("submit", 601))
        present = self._present_state(shared)
        before_present, before_shared = copy.deepcopy(present), copy.deepcopy(shared)
        result = queue_present(present, PresentRequest(token=701, wait_indices=(0,)))
        self.assertEqual((result.result, result.accepted), ("INVALID_SYNCHRONIZATION_STATE", False))
        self.assertEqual(present, before_present)
        self.assertEqual(shared, before_shared)

    def test_present_wait_reservation_blocks_submit_without_mutation(self):
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED)
        present = self._present_state(shared)
        result = queue_present(present, PresentRequest(token=702, wait_indices=(0,)))
        self.assertEqual((result.result, result.accepted), ("SUCCESS", True))
        self.assertEqual(shared.wait_reservation, ("present", 702))
        submit = self._submit_state(shared)
        before_submit, before_shared = copy.deepcopy(submit), copy.deepcopy(shared)
        self.assertEqual(queue_submit(submit, SubmitRequest(token=602, wait_indices=(0,))),
                         "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual(submit, before_submit)
        self.assertEqual(shared, before_shared)

    def test_submit_signal_then_present_consumption_retires_signal_once(self):
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)
        signaler = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(queue_submit(signaler, SubmitRequest(
            token=603, signal_indices=(0,), signal_values=(0,))), "SUCCESS")
        self.assertEqual(finish_submission(signaler, 603, success=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.SIGNALED)

        present = self._present_state(shared)
        self.assertEqual(queue_present(present, PresentRequest(token=703, wait_indices=(0,))).result,
                         "SUCCESS")
        self.assertEqual(finish_present_wait(present, 703, 0, consumed=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        after = (copy.deepcopy(signaler), copy.deepcopy(present), copy.deepcopy(shared))
        self.assertEqual(finish_submission(signaler, 603, success=True), "BadValue")
        self.assertEqual((signaler, present, shared), after)

    def test_unknown_present_consumption_cannot_be_overridden_by_stale_submit_mirror(self):
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED)
        present = self._present_state(shared)
        self.assertEqual(queue_present(present, PresentRequest(token=704, wait_indices=(0,))).result,
                         "SUCCESS")
        self.assertEqual(finish_present_wait(present, 704, 0, consumed=None), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)

        submit = self._submit_state(shared)
        submit.binary_signal_states[0] = BinarySignalState.SIGNALED
        submit.wait_states[0] = WaitState.READY
        before = copy.deepcopy(submit)
        self.assertEqual(queue_submit(submit, SubmitRequest(token=604, wait_indices=(0,))),
                         "DEPENDENCY_FAILED")
        self.assertEqual(submit, before)
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)



    def test_submit_signal_completion_before_nonconsuming_present_callback_syncs_mirror(self):
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)
        submit = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(submit, SubmitRequest(token=605, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            shared_semaphores=[shared],
        )
        self.assertTrue(queue_present(present, PresentRequest(token=705, wait_indices=(0,))).accepted)

        # The submit callback wins the race and confirms the signal. Present
        # then reports that its wait did not consume the payload; its stale
        # local SIGNAL_PENDING snapshot must be reconciled with shared state.
        self.assertEqual(finish_submission(submit, 605, success=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.SIGNALED)
        self.assertEqual(present.binary_signal_states, [BinarySignalState.SIGNAL_PENDING])
        self.assertEqual(finish_present_wait(present, 705, 0, consumed=False), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.SIGNALED)
        self.assertEqual(present.binary_signal_states, [BinarySignalState.SIGNALED])
        self.assertEqual(present.wait_states, [WaitState.READY])
        self.assertIsNone(shared.wait_reservation)


    def test_consumed_pending_signal_cannot_be_reserved_by_second_submit_or_present_wait(self):
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)
        signaler = self._submit_state(shared)
        self.assertEqual(
            queue_submit(signaler, SubmitRequest(token=606, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )

        first_present = self._present_state(shared)
        self.assertTrue(
            queue_present(first_present, PresentRequest(token=706, wait_indices=(0,))).accepted
        )
        # The wait consumes the pending payload, but the signal owner's
        # terminal callback has not run yet, so its reservation is still live.
        self.assertEqual(finish_present_wait(first_present, 706, 0, consumed=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertEqual(shared.signal_reservation, ("submit", 606))
        self.assertTrue(shared.signal_consumed)

        second_present = self._present_state(shared)
        before_present, before_shared = copy.deepcopy(second_present), copy.deepcopy(shared)
        result = queue_present(second_present, PresentRequest(token=707, wait_indices=(0,)))
        self.assertEqual(
            (result.result, result.accepted),
            ("INVALID_SYNCHRONIZATION_STATE", False),
        )
        self.assertEqual(second_present, before_present)
        self.assertEqual(shared, before_shared)

        second_submit = self._submit_state(shared)
        before_submit = copy.deepcopy(second_submit)
        self.assertEqual(
            queue_submit(second_submit, SubmitRequest(token=607, wait_indices=(0,))),
            "INVALID_SYNCHRONIZATION_STATE",
        )
        self.assertEqual(second_submit, before_submit)
        self.assertEqual(shared, before_shared)

        # The original signal callback retires its own reservation exactly
        # once and leaves the known-empty payload reusable.
        self.assertEqual(finish_submission(signaler, 606, success=True), "SUCCESS")
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertIsNone(shared.signal_reservation)
        self.assertFalse(shared.signal_consumed)




    def test_independent_device_loss_callbacks_quarantine_all_pending_semaphores(self):
        shared = [
            SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED),
            SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED),
        ]

        def submit(token, index):
            state = SubmissionModel(
                command_buffers=[
                    CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
                ],
                wait_states=[WaitState.READY, WaitState.READY],
                binary_signal_states=[
                    BinarySignalState.UNSIGNALED, BinarySignalState.UNSIGNALED
                ],
                signal_slots=[None, None],
                semaphore_kinds=[SemaphoreKind.BINARY, SemaphoreKind.BINARY],
                shared_semaphores=shared,
            )
            self.assertEqual(queue_submit(state, SubmitRequest(
                token=token, signal_indices=(index,), signal_values=(0,)
            )), "SUCCESS")
            return state

        submit0, submit1 = submit(940, 0), submit(941, 1)
        presents = []
        for token, index in ((950, 0), (951, 1)):
            present = PresentState(
                valid_wait_xids=(True, True),
                wait_states=[WaitState.READY, WaitState.READY],
                binary_signal_states=[
                    BinarySignalState.SIGNAL_PENDING,
                    BinarySignalState.SIGNAL_PENDING,
                ],
                shared_semaphores=shared,
            )
            self.assertTrue(queue_present(
                present, PresentRequest(token=token, wait_indices=(index,))
            ).accepted)
            presents.append((present, token, index))

        # Two independent observers report the same device-wide loss. The
        # second notification must not resurrect reservations or alter the
        # terminal status established by the first observer.
        self.assertEqual(mark_device_lost(submit0), "SUCCESS")
        snapshot = copy.deepcopy(shared)
        self.assertEqual(mark_present_device_lost(presents[0][0]), "SUCCESS")
        self.assertEqual(mark_present_device_lost(presents[1][0]), "SUCCESS")
        self.assertTrue(all(item.device_lost for item in shared))
        self.assertEqual(
            [item.signal_state for item in shared],
            [BinarySignalState.UNTRUSTED, BinarySignalState.UNTRUSTED],
        )

        # Late Submit and Present callbacks retire only their own outstanding
        # work; neither callback may restore a quarantined payload.
        self.assertEqual(finish_submission(submit1, 941, success=True), "SUCCESS")
        for present, token, index in presents:
            self.assertEqual(
                finish_present_wait(present, token, index, consumed=True), "SUCCESS"
            )
        self.assertEqual(
            [item.signal_state for item in shared],
            [BinarySignalState.UNTRUSTED, BinarySignalState.UNTRUSTED],
        )
        self.assertTrue(all(item.signal_reservation is None for item in shared))
        self.assertTrue(all(item.wait_reservation is None for item in shared))
        self.assertEqual(submit1.pending_submissions, [])
        self.assertEqual(submit1.pending_binary_signals, [])
        for present, token, _index in presents:
            self.assertNotIn((token, _index), present.pending_present_waits)
            self.assertEqual(present.terminal_present_status[token], "DEVICE_LOST")

        # A repeated loss report after all callbacks is a no-op on semaphore
        # knowledge and does not manufacture fresh reservations.
        final_snapshot = copy.deepcopy(shared)
        self.assertEqual(mark_present_device_lost(presents[0][0]), "SUCCESS")
        self.assertEqual(shared, final_snapshot)

    def test_submit_observing_shared_device_loss_propagates_to_other_semaphores(self):
        shared_ab = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)
        shared_bc = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)
        shared_c = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)

        def make_model(shared):
            return SubmissionModel(
                command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
                wait_states=[WaitState.READY for _ in shared],
                binary_signal_states=[BinarySignalState.UNSIGNALED for _ in shared],
                signal_slots=[None for _ in shared],
                semaphore_kinds=[SemaphoreKind.BINARY for _ in shared],
                shared_semaphores=shared,
            )

        model_a = make_model([shared_ab])
        model_b = make_model([shared_ab, shared_bc])
        model_c = make_model([shared_bc, shared_c])
        self.assertEqual(queue_submit(
            model_c, SubmitRequest(token=976, signal_indices=(1,), signal_values=(0,))
        ), "SUCCESS")

        # Simulate another API/model having published the canonical device-loss
        # flag; the first subsequent Submit on the overlapping model must fan
        # it out instead of merely setting model_b.device_lost.
        shared_ab.device_lost = True
        self.assertEqual(queue_submit(model_b, SubmitRequest(token=977)), "DEVICE_LOST")
        self.assertTrue(all(state.device_lost for state in (model_a, model_b, model_c)))
        self.assertTrue(all(shared.device_lost for shared in (shared_ab, shared_bc, shared_c)))
        self.assertEqual(
            [shared.signal_state for shared in (shared_ab, shared_bc, shared_c)],
            [BinarySignalState.UNTRUSTED] * 3,
        )
        self.assertEqual(
            model_c.binary_signal_states,
            [BinarySignalState.UNTRUSTED, BinarySignalState.UNTRUSTED],
        )
        # Foreign accepted work remains callback-owned after immediate quarantine.
        self.assertEqual(model_c.pending_submissions, [976])
        self.assertEqual(finish_submission(model_c, 976, success=True), "SUCCESS")
        self.assertEqual(shared_c.signal_state, BinarySignalState.UNTRUSTED)

    def test_device_loss_propagates_across_partially_overlapping_semaphore_sets(self):
        shared_ab = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)
        shared_bc = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)
        shared_c = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)

        def make_model(shared):
            return SubmissionModel(
                command_buffers=[
                    CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
                ],
                wait_states=[WaitState.READY for _ in shared],
                binary_signal_states=[BinarySignalState.UNSIGNALED for _ in shared],
                signal_slots=[None for _ in shared],
                semaphore_kinds=[SemaphoreKind.BINARY for _ in shared],
                shared_semaphores=shared,
            )

        model_a = make_model([shared_ab])
        model_b = make_model([shared_ab, shared_bc])
        model_c = make_model([shared_bc, shared_c])
        self.assertEqual(
            queue_submit(model_c, SubmitRequest(token=972, signal_indices=(1,), signal_values=(0,))),
            "SUCCESS",
        )

        self.assertEqual(mark_device_lost(model_a), "SUCCESS")
        # A -> B -> C is connected transitively, despite no model owning the
        # complete semaphore set. Every model and every canonical payload is
        # marked lost/quarantined immediately.
        self.assertTrue(model_a.device_lost)
        self.assertTrue(model_b.device_lost)
        self.assertTrue(model_c.device_lost)
        self.assertTrue(all(s.device_lost for s in (shared_ab, shared_bc, shared_c)))
        self.assertEqual(
            [s.signal_state for s in (shared_ab, shared_bc, shared_c)],
            [BinarySignalState.UNTRUSTED] * 3,
        )
        # Foreign pending work remains callback-owned, but its mirrors and
        # payloads are quarantined immediately. The callback can drain its own
        # token without restoring trust.
        self.assertEqual(model_c.pending_submissions, [972])
        self.assertEqual(model_c.pending_binary_signals, [(972, 1)])
        self.assertEqual(
            model_c.binary_signal_states,
            [BinarySignalState.UNTRUSTED, BinarySignalState.UNTRUSTED],
        )
        self.assertEqual(finish_submission(model_c, 972, success=True), "SUCCESS")
        self.assertEqual(model_c.pending_submissions, [])
        self.assertEqual(shared_c.signal_state, BinarySignalState.UNTRUSTED)

    def test_present_device_loss_propagates_through_mixed_overlapping_models(self):
        shared_ab = SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED)
        shared_bc = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)
        shared_c = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)

        present_a = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNALED],
            shared_semaphores=[shared_ab],
        )
        submit_b = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY, WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED, BinarySignalState.UNSIGNALED],
            signal_slots=[None, None],
            semaphore_kinds=[SemaphoreKind.BINARY, SemaphoreKind.BINARY],
            shared_semaphores=[shared_ab, shared_bc],
        )
        present_c = PresentState(
            valid_wait_xids=(True, True),
            wait_states=[WaitState.READY, WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED, BinarySignalState.UNSIGNALED],
            shared_semaphores=[shared_bc, shared_c],
        )
        self.assertTrue(queue_present(
            present_a, PresentRequest(token=973, wait_indices=(0,))
        ).accepted)
        self.assertEqual(queue_submit(
            submit_b,
            SubmitRequest(token=974, signal_indices=(1,), signal_values=(0,)),
        ), "SUCCESS")
        self.assertEqual(mark_present_device_lost(present_a), "SUCCESS")
        self.assertTrue(all(state.device_lost for state in (present_a, submit_b, present_c)))
        self.assertTrue(all(shared.device_lost for shared in (shared_ab, shared_bc, shared_c)))
        self.assertEqual(present_a.terminal_present_status[973], "DEVICE_LOST")
        self.assertNotIn(973, present_a.pending_present_tokens)
        # Presentation terminalization and its wait callback are independent:
        # the accepted wait retains its reservation until that callback drains.
        self.assertEqual(present_a.pending_present_waits, [(973, 0)])
        self.assertEqual(shared_ab.wait_reservation, ("present", 973))
        self.assertEqual(
            finish_present_wait(present_a, 973, 0, consumed=True), "SUCCESS"
        )
        self.assertIsNone(shared_ab.wait_reservation)
        self.assertEqual(shared_ab.signal_state, BinarySignalState.UNTRUSTED)
        # Foreign Submit work remains owned by its callback, but every mirror
        # in the transitively connected model is already quarantined.
        self.assertEqual(submit_b.pending_submissions, [974])
        self.assertEqual(submit_b.binary_signal_states,
                         [BinarySignalState.UNTRUSTED, BinarySignalState.UNTRUSTED])
        self.assertEqual(finish_submission(submit_b, 974, success=True), "SUCCESS")
        self.assertEqual(shared_c.signal_state, BinarySignalState.UNTRUSTED)

    def test_submit_device_loss_preserves_confirmed_empty_shared_payload(self):
        shared = SharedBinarySemaphore(
            signal_state=BinarySignalState.UNSIGNALED,
            signal_consumption_confirmed=True,
        )
        state = SubmissionModel(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
            ],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )

        self.assertEqual(mark_device_lost(state), "SUCCESS")
        self.assertTrue(state.device_lost)
        self.assertTrue(shared.device_lost)
        self.assertEqual(shared.signal_state, BinarySignalState.UNSIGNALED)
        self.assertTrue(shared.signal_consumption_confirmed)
        self.assertEqual(state.binary_signal_states, [BinarySignalState.UNSIGNALED])
        self.assertEqual(state.wait_states, [WaitState.READY])
        # Loss remains terminal even though the known-empty binary payload is
        # preserved for correct state accounting.
        self.assertEqual(
            queue_submit(state, SubmitRequest(token=963, wait_indices=(0,))),
            "DEVICE_LOST",
        )

    def test_submit_device_loss_immediately_quarantines_foreign_shared_signal(self):
        shared = [
            SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED),
            SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED),
        ]

        def make_submit(token, index):
            state = SubmissionModel(
                command_buffers=[
                    CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
                ],
                wait_states=[WaitState.READY, WaitState.READY],
                binary_signal_states=[
                    BinarySignalState.UNSIGNALED, BinarySignalState.UNSIGNALED,
                ],
                signal_slots=[None, None],
                semaphore_kinds=[SemaphoreKind.BINARY, SemaphoreKind.BINARY],
                shared_semaphores=shared,
            )
            self.assertEqual(queue_submit(
                state, SubmitRequest(token=token, signal_indices=(index,), signal_values=(0,))
            ), "SUCCESS")
            return state

        # The second queue owns a pending signal the observer cannot retire.
        foreign_owner = make_submit(962, 1)
        observer = make_submit(960, 0)
        self.assertEqual(mark_device_lost(observer), "SUCCESS")
        self.assertTrue(all(item.device_lost for item in shared))
        self.assertEqual(
            [item.signal_state for item in shared],
            [BinarySignalState.UNTRUSTED, BinarySignalState.UNTRUSTED],
        )
        self.assertIsNone(shared[1].signal_reservation)
        self.assertEqual(
            observer.binary_signal_states,
            [BinarySignalState.UNTRUSTED, BinarySignalState.UNTRUSTED],
        )
        # The foreign owner's late callback can drain its token but cannot
        # republish the old signal payload or restore its local mirror.
        self.assertEqual(finish_submission(foreign_owner, 962, success=True), "SUCCESS")
        self.assertEqual(shared[1].signal_state, BinarySignalState.UNTRUSTED)
        self.assertEqual(foreign_owner.binary_signal_states[1], BinarySignalState.UNTRUSTED)
        self.assertIsNone(shared[1].signal_reservation)

    def test_device_loss_quarantines_multiple_cross_queue_submit_present_callbacks(self):
        def make_race():
            shared = [
                SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED),
                SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED),
            ]

            def submit_state():
                return SubmissionModel(
                    command_buffers=[
                        CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
                    ],
                    wait_states=[WaitState.READY, WaitState.READY],
                    binary_signal_states=[
                        BinarySignalState.UNSIGNALED, BinarySignalState.UNSIGNALED
                    ],
                    signal_slots=[None, None],
                    semaphore_kinds=[SemaphoreKind.BINARY, SemaphoreKind.BINARY],
                    shared_semaphores=shared,
                )

            first, second = submit_state(), submit_state()
            self.assertEqual(queue_submit(first, SubmitRequest(
                token=920, signal_indices=(0,), signal_values=(0,)
            )), "SUCCESS")
            self.assertEqual(queue_submit(second, SubmitRequest(
                token=921, signal_indices=(1,), signal_values=(0,)
            )), "SUCCESS")

            presents = []
            for token, index in ((930, 0), (931, 1)):
                present = PresentState(
                    valid_wait_xids=(True, True),
                    wait_states=[WaitState.READY, WaitState.READY],
                    binary_signal_states=[
                        BinarySignalState.SIGNAL_PENDING,
                        BinarySignalState.SIGNAL_PENDING,
                    ],
                    shared_semaphores=shared,
                )
                self.assertTrue(queue_present(
                    present, PresentRequest(token=token, wait_indices=(index,))
                ).accepted)
                presents.append((present, token, index))
            return shared, first, second, presents

        # The same pending operations are finalized in different orders after
        # Submit observes device loss. The second queue's late callback claims
        # its signal payload was unchanged, which must not restore a stale
        # UNSIGNALED snapshot or contradict a Present callback.
        orders = (
            ("submit1", "present1"),
            ("present1", "submit1"),
            ("present0", "submit1", "present1"),
        )
        finals = []
        for order in orders:
            shared, first, second, presents = make_race()
            self.assertEqual(mark_device_lost(first), "SUCCESS")
            for event in order:
                if event == "submit1":
                    self.assertEqual(finish_submission(
                        second, 921, success=True,
                        binary_payload_unchanged={("signal", 1)},
                    ), "SUCCESS")
                else:
                    present, token, index = presents[int(event[-1])]
                    self.assertEqual(finish_present_wait(
                        present, token, index, consumed=(event == "present0")
                    ), "SUCCESS")

            # All semaphores are device-scoped: callbacks cannot re-trust the
            # signal owned by the other queue, regardless of arrival order.
            self.assertTrue(all(item.device_lost for item in shared))
            self.assertEqual(shared[1].signal_state, BinarySignalState.UNTRUSTED)
            self.assertEqual(second.binary_signal_states[1], BinarySignalState.UNTRUSTED)
            if "present1" in order:
                self.assertEqual(presents[1][0].binary_signal_states[1],
                                 BinarySignalState.UNTRUSTED)
                self.assertEqual(presents[1][0].wait_states[1], WaitState.UNTRUSTED)
                self.assertIsNone(shared[1].wait_reservation)
            finals.append((shared, first, second, presents))

        # Compare canonical shared payload state and the signal owner's mirror;
        # each order may legitimately differ in which wait reservations drained.
        for shared, first, second, presents in finals:
            self.assertEqual(shared[0].signal_state, BinarySignalState.UNTRUSTED)
            self.assertEqual(shared[1].signal_state, BinarySignalState.UNTRUSTED)
            self.assertIsNone(shared[0].signal_reservation)
            self.assertIsNone(shared[1].signal_reservation)
            self.assertFalse(shared[1].signal_consumed)
            self.assertEqual(second.pending_submissions, [])

    def test_present_device_loss_quarantines_late_submit_signal_callback(self):
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)
        submit = SubmissionModel(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
            ],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(
                submit, SubmitRequest(token=908, signal_indices=(0,), signal_values=(0,))
            ),
            "SUCCESS",
        )
        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            shared_semaphores=[shared],
        )
        self.assertTrue(
            queue_present(present, PresentRequest(token=909, wait_indices=(0,))).accepted
        )

        # Device loss is device-wide even when first observed by Present.
        # A later success-shaped Submit callback must not resurrect the payload
        # or clear the quarantine just because its local model missed the event.
        self.assertEqual(mark_present_device_lost(present), "SUCCESS")
        self.assertTrue(shared.device_lost)
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)
        self.assertEqual(finish_submission(submit, 908, success=True), "SUCCESS")
        self.assertTrue(submit.device_lost)
        self.assertEqual(submit.binary_signal_states, [BinarySignalState.UNTRUSTED])
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)
        self.assertIsNone(shared.signal_reservation)
        self.assertFalse(shared.signal_consumed)

        before_submit = copy.deepcopy(submit)
        self.assertEqual(
            queue_submit(submit, SubmitRequest(token=910)),
            "DEVICE_LOST",
        )
        # The request observes the device-wide terminal state without
        # mutating unrelated submission reservations or resource state.
        self.assertEqual(submit, before_submit)


class CompetingTimelineWaitCallbackOutcomeTests(unittest.TestCase):
    """Out-of-order wait completions must retire only their own reservations."""

    def test_failed_lower_wait_callback_does_not_disturb_completed_higher_wait(self):
        state = SubmissionModel(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
                for _ in range(2)
            ],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.TIMELINE],
            signal_counters=[3],
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=451, command_buffer_indices=(0,),
                wait_indices=(0,), wait_values=(7,),
            )),
            "SUCCESS",
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=452, command_buffer_indices=(1,),
                wait_indices=(0,), wait_values=(11,),
            )),
            "SUCCESS",
        )

        # A higher-target wait may finish first. Its callback must neither
        # publish the waited value as the semaphore counter nor retire token
        # 451's lower-target wait.
        self.assertEqual(finish_submission(state, 452, success=True), "SUCCESS")
        self.assertEqual(state.signal_counters, [3])
        self.assertEqual(state.pending_timeline_waits, [(451, 0, 7)])
        self.assertEqual(state.pending_submissions, [451])

        # Failure of the remaining callback only drains its own wait. It must
        # not rewrite the already-terminal higher submission or counter.
        self.assertEqual(finish_submission(state, 451, success=False), "SUCCESS")
        self.assertEqual(state.signal_counters, [3])
        self.assertEqual(state.pending_timeline_waits, [])
        self.assertEqual(state.pending_submissions, [])
        self.assertEqual(
            [buffer.lifecycle for buffer in state.command_buffers],
            [CommandBufferLifecycle.INVALID, CommandBufferLifecycle.EXECUTABLE],
        )
        terminal = copy.deepcopy(state)
        self.assertEqual(finish_submission(state, 451, success=True), "BadValue")
        self.assertEqual(finish_submission(state, 452, success=False), "BadValue")
        self.assertEqual(state, terminal)

    def test_duplicate_wait_values_owned_by_one_token_are_drained_together(self):
        state = SubmissionModel(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
            ],
            wait_states=[WaitState.READY, WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.TIMELINE, SemaphoreKind.TIMELINE],
            signal_counters=[2, 4],
        )
        self.assertEqual(
            queue_submit(state, SubmitRequest(
                token=453, command_buffer_indices=(0,),
                wait_indices=(0, 1), wait_values=(8, 13),
            )),
            "SUCCESS",
        )
        self.assertEqual(
            state.pending_timeline_waits, [(453, 0, 8), (453, 1, 13)]
        )
        self.assertEqual(finish_submission(state, 453, success=False), "SUCCESS")
        self.assertEqual(state.pending_timeline_waits, [])
        self.assertEqual(state.signal_counters, [2, 4])
        terminal = copy.deepcopy(state)
        self.assertEqual(finish_submission(state, 453, success=True), "BadValue")
        self.assertEqual(state, terminal)

class DisconnectWaitDeviceLossInterleavingTests(unittest.TestCase):
    """Disconnect and device loss must not steal callback-owned reservations."""

    def _make_pending_pair(self):
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)
        submit = SubmissionModel(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
            ],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
        )
        self.assertEqual(
            queue_submit(submit, SubmitRequest(token=990, signal_indices=(0,), signal_values=(0,))),
            "SUCCESS",
        )
        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            shared_semaphores=[shared],
        )
        self.assertTrue(queue_present(
            present, PresentRequest(token=991, wait_indices=(0,))
        ).accepted)
        return shared, submit, present

    def test_disconnect_then_device_loss_then_late_wait_releases_once(self):
        shared, submit, present = self._make_pending_pair()
        _unregister_semaphore_owner(present)
        self.assertNotIn(present, [owner() for owner in shared.owners])
        self.assertEqual(shared.signal_reservation, ("submit", 990))
        self.assertEqual(shared.wait_reservation, ("present", 991))

        self.assertEqual(mark_device_lost(submit), "SUCCESS")
        self.assertTrue(shared.device_lost)
        self.assertIsNone(shared.signal_reservation)
        # The disconnected Present callback still owns its wait reservation.
        self.assertEqual(shared.wait_reservation, ("present", 991))
        self.assertEqual(
            finish_present_wait(present, 991, 0, consumed=True), "SUCCESS"
        )
        self.assertIsNone(shared.wait_reservation)
        self.assertEqual(present.pending_present_waits, [])
        snapshot = copy.deepcopy((shared, submit, present))
        self.assertEqual(
            finish_present_wait(present, 991, 0, consumed=False), "BadValue"
        )
        self.assertEqual(finish_submission(submit, 990, success=True), "BadValue")
        self.assertEqual((shared, submit, present), snapshot)

    def test_disconnected_late_signal_callback_releases_submission_refs_once(self):
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)
        buffer = BufferMemoryLifetime(descriptor_slot_refs=1)
        descriptor_set = DescriptorSetLifetime(slots={0: buffer.identity})
        command_buffer = CommandBufferModel(
            lifecycle=CommandBufferLifecycle.EXECUTABLE,
            descriptor_sets=[descriptor_set],
            indirect_buffer_refs={buffer.identity},
        )
        submit = SubmissionModel(
            command_buffers=[command_buffer],
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED],
            signal_slots=[None],
            semaphore_kinds=[SemaphoreKind.BINARY],
            shared_semaphores=[shared],
            buffer_registry=[buffer],
        )
        self.assertEqual(queue_submit(
            submit,
            SubmitRequest(token=992, command_buffer_indices=(0,),
                          signal_indices=(0,), signal_values=(0,)),
        ), "SUCCESS")
        self.assertEqual((descriptor_set.pending_submission_refs, buffer.accepted_uses), (1, 1))

        observer = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            shared_semaphores=[shared],
        )
        _unregister_semaphore_owner(submit)
        self.assertEqual(mark_present_device_lost(observer), "SUCCESS")
        # The disconnected model retains its accepted token and reference
        # ledger; the late callback, not disconnect or the foreign loss walk,
        # is responsible for retiring those per-submission references.
        self.assertEqual(submit.pending_submissions, [992])
        self.assertEqual((descriptor_set.pending_submission_refs, buffer.accepted_uses), (1, 1))
        self.assertIsNone(shared.signal_reservation)
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)

        self.assertEqual(finish_submission(submit, 992, success=True), "SUCCESS")
        self.assertTrue(submit.device_lost)
        self.assertEqual(submit.pending_submissions, [])
        self.assertEqual((descriptor_set.pending_submission_refs, buffer.accepted_uses), (0, 0))
        self.assertEqual(command_buffer.lifecycle, CommandBufferLifecycle.INVALID)
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)
        self.assertIsNone(shared.signal_reservation)
        after_first = copy.deepcopy((submit, descriptor_set, buffer, command_buffer, shared))
        self.assertEqual(finish_submission(submit, 992, success=False), "BadValue")
        self.assertEqual((submit, descriptor_set, buffer, command_buffer, shared), after_first)

    def test_wait_completion_then_disconnect_then_device_loss_does_not_double_release(self):
        shared, submit, present = self._make_pending_pair()
        self.assertEqual(
            finish_present_wait(present, 991, 0, consumed=False), "SUCCESS"
        )
        self.assertIsNone(shared.wait_reservation)
        _unregister_semaphore_owner(present)
        self.assertEqual(mark_device_lost(submit), "SUCCESS")
        self.assertIsNone(shared.signal_reservation)
        self.assertIsNone(shared.wait_reservation)
        snapshot = copy.deepcopy((shared, submit, present))
        self.assertEqual(
            finish_present_wait(present, 991, 0, consumed=True), "BadValue"
        )
        self.assertEqual(finish_submission(submit, 990, success=False), "BadValue")
        self.assertEqual((shared, submit, present), snapshot)


class MultiWaitPresentDeviceLossRaceTests(unittest.TestCase):
    """Every accepted Present wait must retire independently across Device Loss."""

    def test_disconnected_multisignal_callback_cannot_restore_stale_consumed_mirror(self):
        shared = [
            SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED),
            SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED),
        ]
        submit = SubmissionModel(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
            ],
            wait_states=[WaitState.READY, WaitState.READY],
            binary_signal_states=[
                BinarySignalState.UNSIGNALED, BinarySignalState.UNSIGNALED,
            ],
            signal_slots=[None, None],
            semaphore_kinds=[SemaphoreKind.BINARY, SemaphoreKind.BINARY],
            shared_semaphores=shared,
        )
        self.assertEqual(queue_submit(
            submit,
            SubmitRequest(token=993, signal_indices=(0, 1), signal_values=(0, 0)),
        ), "SUCCESS")
        # Model a per-token consumed marker left by a competing wait callback.
        # After disconnect, the model is no longer in the owner traversal, so
        # its local SIGNAL_PENDING mirrors intentionally remain stale.
        submit.consumed_pending_binary_signals.add((993, 0))
        _unregister_semaphore_owner(submit)
        observer = PresentState(
            valid_wait_xids=(True, True),
            wait_states=[WaitState.READY, WaitState.READY],
            binary_signal_states=[
                BinarySignalState.SIGNAL_PENDING, BinarySignalState.SIGNAL_PENDING,
            ],
            shared_semaphores=shared,
        )
        self.assertEqual(mark_present_device_lost(observer), "SUCCESS")
        self.assertEqual(
            [item.signal_state for item in shared],
            [BinarySignalState.UNTRUSTED, BinarySignalState.UNTRUSTED],
        )
        self.assertEqual(
            submit.binary_signal_states,
            [BinarySignalState.SIGNAL_PENDING, BinarySignalState.SIGNAL_PENDING],
        )

        # A late success-shaped callback retires its token but must reconcile
        # both local mirrors from the canonical post-loss state. In particular,
        # the stale consumed marker for index 0 cannot make it look empty.
        self.assertEqual(finish_submission(submit, 993, success=True), "SUCCESS")
        self.assertEqual(
            submit.binary_signal_states,
            [BinarySignalState.UNTRUSTED, BinarySignalState.UNTRUSTED],
        )
        self.assertEqual(
            submit.wait_states, [WaitState.UNTRUSTED, WaitState.UNTRUSTED]
        )
        self.assertEqual(
            [item.signal_state for item in shared],
            [BinarySignalState.UNTRUSTED, BinarySignalState.UNTRUSTED],
        )
        self.assertEqual(
            [item.signal_reservation for item in shared], [None, None]
        )
        self.assertEqual(submit.pending_submissions, [])
        snapshot = copy.deepcopy((submit, shared))
        self.assertEqual(finish_submission(submit, 993, success=False), "BadValue")
        self.assertEqual((submit, shared), snapshot)

    def test_device_loss_between_competing_wait_callbacks_quarantines_all_waits(self):
        shared = [
            SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED),
            SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED),
        ]
        submit = SubmissionModel(
            command_buffers=[
                CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)
            ],
            wait_states=[WaitState.READY, WaitState.READY],
            binary_signal_states=[
                BinarySignalState.UNSIGNALED, BinarySignalState.UNSIGNALED,
            ],
            signal_slots=[None, None],
            semaphore_kinds=[SemaphoreKind.BINARY, SemaphoreKind.BINARY],
            shared_semaphores=shared,
        )
        self.assertEqual(
            queue_submit(
                submit,
                SubmitRequest(
                    token=901, signal_indices=(0, 1), signal_values=(0, 0),
                ),
            ),
            "SUCCESS",
        )
        present = PresentState(
            valid_wait_xids=(True, True),
            wait_states=[WaitState.READY, WaitState.READY],
            binary_signal_states=[
                BinarySignalState.SIGNAL_PENDING, BinarySignalState.SIGNAL_PENDING,
            ],
            shared_semaphores=shared,
        )
        self.assertTrue(
            queue_present(
                present, PresentRequest(token=902, wait_indices=(0, 1)),
            ).accepted
        )
        self.assertEqual(
            [item.wait_reservation for item in shared],
            [("present", 902), ("present", 902)],
        )

        # One callback resolves before loss; the other races after loss. Loss
        # must quarantine both payloads, including the one whose wait callback
        # already reported known non-consumption.
        self.assertEqual(
            finish_present_wait(present, 902, 0, consumed=False), "SUCCESS"
        )
        self.assertEqual(shared[0].signal_state, BinarySignalState.SIGNAL_PENDING)
        self.assertIsNone(shared[0].wait_reservation)
        self.assertEqual(shared[1].wait_reservation, ("present", 902))

        self.assertEqual(mark_device_lost(submit), "SUCCESS")
        self.assertEqual(
            [item.signal_state for item in shared],
            [BinarySignalState.UNTRUSTED, BinarySignalState.UNTRUSTED],
        )
        self.assertEqual(
            [item.signal_reservation for item in shared], [None, None]
        )

        # A late success-shaped callback for the second wait cannot restore
        # trust. It must still retire its own Present reservation exactly once.
        self.assertEqual(
            finish_present_wait(present, 902, 1, consumed=True), "SUCCESS"
        )
        self.assertEqual(
            [item.signal_state for item in shared],
            [BinarySignalState.UNTRUSTED, BinarySignalState.UNTRUSTED],
        )
        self.assertEqual(present.binary_signal_states, [
            BinarySignalState.UNTRUSTED, BinarySignalState.UNTRUSTED,
        ])
        self.assertEqual(present.wait_states, [WaitState.UNTRUSTED, WaitState.UNTRUSTED])
        self.assertEqual(present.pending_present_waits, [])
        self.assertEqual(
            [item.wait_reservation for item in shared], [None, None]
        )

        terminal = copy.deepcopy((submit, present, shared))
        self.assertEqual(
            finish_present_wait(present, 902, 0, consumed=True), "BadValue"
        )
        self.assertEqual(
            finish_present_wait(present, 902, 1, consumed=False), "BadValue"
        )
        self.assertEqual(finish_submission(submit, 901, success=True), "BadValue")
        self.assertEqual((submit, present, shared), terminal)

    def test_present_device_lost_terminal_callback_propagates_and_late_submit_retires_once(self):
        shared_ab = SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED)
        shared_bc = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)
        shared_c = SharedBinarySemaphore(signal_state=BinarySignalState.UNSIGNALED)
        present_a = PresentState(
            valid_wait_xids=(True,), wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNALED],
            shared_semaphores=[shared_ab],
        )
        present_b = PresentState(
            valid_wait_xids=(True, True), wait_states=[WaitState.READY, WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNALED, BinarySignalState.UNSIGNALED],
            shared_semaphores=[shared_ab, shared_bc],
        )
        submit_c = SubmissionModel(
            command_buffers=[CommandBufferModel(lifecycle=CommandBufferLifecycle.EXECUTABLE)],
            wait_states=[WaitState.READY, WaitState.READY],
            binary_signal_states=[BinarySignalState.UNSIGNALED, BinarySignalState.UNSIGNALED],
            signal_slots=[None, None],
            semaphore_kinds=[SemaphoreKind.BINARY, SemaphoreKind.BINARY],
            shared_semaphores=[shared_bc, shared_c],
        )
        self.assertTrue(queue_present(
            present_a, PresentRequest(token=981, wait_indices=(0,))
        ).accepted)
        self.assertEqual(queue_submit(
            submit_c, SubmitRequest(token=982, signal_indices=(1,), signal_values=(0,))
        ), "SUCCESS")
        self.assertEqual(shared_c.signal_reservation, ("submit", 982))

        # The backend's Present terminal callback is the first loss report.
        self.assertEqual(finish_present_terminal(present_a, 981, "DEVICE_LOST"), "SUCCESS")
        self.assertEqual(present_a.terminal_present_status, {981: "DEVICE_LOST"})
        self.assertEqual(present_a.image_state, ImageState.INVALID)
        self.assertTrue(all(model.device_lost for model in (present_a, present_b, submit_c)))
        self.assertTrue(all(item.device_lost for item in (shared_ab, shared_bc, shared_c)))
        self.assertEqual(
            [item.signal_state for item in (shared_ab, shared_bc, shared_c)],
            [BinarySignalState.UNTRUSTED] * 3,
        )
        # The foreign Submit token remains owned by its callback, but its
        # reservation is already quarantined and cannot be resurrected.
        self.assertEqual(submit_c.pending_submissions, [982])
        self.assertIsNone(shared_c.signal_reservation)
        self.assertEqual(finish_submission(submit_c, 982, success=True), "SUCCESS")
        after_first = copy.deepcopy((submit_c, present_a, present_b, shared_ab, shared_bc, shared_c))
        self.assertEqual(finish_submission(submit_c, 982, success=False), "BadValue")
        self.assertEqual((submit_c, present_a, present_b, shared_ab, shared_bc, shared_c), after_first)

    def test_device_loss_terminalizes_pending_present_once_and_late_success_is_ignored(self):
        shared = SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED)
        present = PresentState(
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNALED],
            shared_semaphores=[shared],
        )
        self.assertTrue(queue_present(
            present, PresentRequest(token=904, wait_indices=(0,))
        ).accepted)
        self.assertEqual(present.image_state, ImageState.PRESENT_PENDING)
        self.assertEqual(mark_present_device_lost(present), "SUCCESS")
        self.assertEqual(present.image_state, ImageState.INVALID)
        self.assertEqual(present.terminal_present_status, {904: "DEVICE_LOST"})
        self.assertEqual(present.pending_present_tokens, set())
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)

        terminal = copy.deepcopy(present)
        self.assertEqual(finish_present_terminal(present, 904, "SUCCESS"), "BadValue")
        self.assertEqual(finish_present_terminal(present, 904, "DEVICE_LOST"), "BadValue")
        self.assertEqual(present, terminal, "late terminal callbacks mutated device-loss state")

        # Wait cleanup is a separate callback lifecycle: it can drain its
        # reservation, but must not revive the image or semaphore payload.
        self.assertEqual(finish_present_wait(present, 904, 0, consumed=True), "SUCCESS")
        self.assertEqual(present.image_state, ImageState.INVALID)
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)
        self.assertEqual(present.terminal_present_status, {904: "DEVICE_LOST"})
        terminal = copy.deepcopy(present)
        self.assertEqual(finish_present_wait(present, 904, 0, consumed=False), "BadValue")
        self.assertEqual(present, terminal)

    def test_late_device_loss_does_not_rewrite_already_terminal_present_success(self):
        present = PresentState(
            valid_wait_xids=(True, True),
            wait_states=[WaitState.READY, WaitState.READY],
        )
        self.assertTrue(queue_present(
            present, PresentRequest(token=905)
        ).accepted)
        self.assertEqual(finish_present_terminal(present, 905, "SUCCESS"), "SUCCESS")
        self.assertEqual(present.image_state, ImageState.AVAILABLE)
        self.assertEqual(mark_present_device_lost(present), "SUCCESS")
        self.assertEqual(present.terminal_present_status, {905: "SUCCESS"})
        self.assertEqual(present.image_state, ImageState.AVAILABLE)
        self.assertEqual(finish_present_terminal(present, 905, "DEVICE_LOST"), "BadValue")
        self.assertEqual(present.pending_present_tokens, set())


    def test_wait_callback_orders_converge_after_present_device_loss(self):
        def make_state():
            shared = [
                SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED),
                SharedBinarySemaphore(signal_state=BinarySignalState.SIGNALED),
            ]
            state = PresentState(
                valid_wait_xids=(True, True),
                wait_states=[WaitState.READY, WaitState.READY],
                binary_signal_states=[
                    BinarySignalState.SIGNALED, BinarySignalState.SIGNALED
                ],
                shared_semaphores=shared,
            )
            accepted = queue_present(
                state, PresentRequest(token=906, wait_indices=(0, 1))
            )
            self.assertTrue(accepted.accepted)
            return state

        orders = (
            ("loss", "wait0", "wait1"),
            ("wait0", "loss", "wait1"),
            ("wait1", "wait0", "loss"),
            ("wait1", "loss", "wait0"),
        )
        final_states = []
        for order in orders:
            state = make_state()
            for event in order:
                if event == "loss":
                    self.assertEqual(mark_present_device_lost(state), "SUCCESS")
                else:
                    index = int(event[-1])
                    self.assertEqual(
                        finish_present_wait(state, 906, index, consumed=True),
                        "SUCCESS",
                    )
            # A terminal present callback arriving after loss must be rejected
            # regardless of which wait callbacks were already processed.
            snapshot = copy.deepcopy(state)
            self.assertEqual(finish_present_terminal(state, 906, "SUCCESS"), "BadValue")
            self.assertEqual(state, snapshot)
            self.assertEqual(state.terminal_present_status, {906: "DEVICE_LOST"})
            self.assertEqual(state.pending_present_tokens, set())
            self.assertEqual(state.pending_present_waits, [])
            self.assertEqual(state.image_state, ImageState.INVALID)
            self.assertEqual(
                [x.signal_state for x in state.shared_semaphores],
                [BinarySignalState.UNTRUSTED, BinarySignalState.UNTRUSTED],
            )
            self.assertEqual(
                state.binary_signal_states,
                [BinarySignalState.UNTRUSTED, BinarySignalState.UNTRUSTED],
            )
            self.assertEqual(
                state.wait_states, [WaitState.UNTRUSTED, WaitState.UNTRUSTED]
            )
            self.assertTrue(all(x.wait_reservation is None for x in state.shared_semaphores))
            final_states.append(state)

        for state in final_states[1:]:
            self.assertEqual(state, final_states[0], "callback order changed terminal state")

    def test_stale_present_mirror_cannot_accept_wait_after_device_loss(self):
        shared = SharedBinarySemaphore(
            signal_state=BinarySignalState.UNTRUSTED,
            signal_reservation=None,
            wait_reservation=None,
        )
        # This PresentState is a competing queue/model whose local mirror has
        # not yet received the callback that reconciles it after device loss.
        stale = PresentState(
            device_lost=False,
            valid_wait_xids=(True,),
            wait_states=[WaitState.READY],
            binary_signal_states=[BinarySignalState.SIGNAL_PENDING],
            shared_semaphores=[shared],
        )
        before = copy.deepcopy(stale)
        result = queue_present(stale, PresentRequest(token=903, wait_indices=(0,)))
        self.assertEqual(result.result, "DEPENDENCY_FAILED")
        self.assertFalse(result.accepted)
        self.assertEqual(stale, before)
        self.assertEqual(shared.signal_state, BinarySignalState.UNTRUSTED)
        self.assertIsNone(shared.wait_reservation)



class DisconnectCallbackCleanupTests(unittest.TestCase):
    def test_late_submission_callback_cannot_target_recreated_device_identity(self) -> None:
        registry = AsyncSubmissionEventRegistry(live_connections={"client-A"})
        old_device = AsyncDeviceIdentity("device-A", 71)
        registry.register_device("client-A", old_device)
        submission = AsyncSubmissionIdentity(
            token=299,
            connection_identity="client-A",
            device_identity="device-A",
            device_xid=71,
            queue_key=(0, 0),
        )
        self.assertEqual(registry.accept_submission(submission), "SUCCESS")
        self.assertEqual(
            registry.select_queue_events("client-A", "device-A", (0, 0), 1),
            "SUCCESS",
        )
        self.assertEqual(registry.destroy_device("device-A"), "SUCCESS")

        # Reuse both the logical identity and public XID before the old
        # backend callback arrives. The new device's event mask must not make
        # the old callback appear to belong to the new device generation.
        new_device = AsyncDeviceIdentity("device-A", 71)
        registry.register_device("client-A", new_device)
        self.assertEqual(
            registry.select_queue_events("client-A", "device-A", (0, 0), 1),
            "SUCCESS",
        )
        self.assertEqual(registry.terminal_callback("client-A", 299, "COMPLETE"), "SUCCESS")
        self.assertEqual(submission.terminal, "COMPLETE")
        self.assertEqual(registry.emitted_events, [])
        self.assertNotIn(("client-A", 299), registry.submissions)


    def test_late_device_loss_error_cannot_target_recreated_device(self) -> None:
        registry = AsyncSubmissionEventRegistry(live_connections={"client-A"})
        old_device = AsyncDeviceIdentity("device-A", 71)
        registry.register_device("client-A", old_device)
        self.assertEqual(registry.destroy_device("device-A"), "SUCCESS")

        new_device = AsyncDeviceIdentity("device-A", 71)
        registry.register_device("client-A", new_device)

        # A delayed Device-Loss/ASYNC_ERROR callback still carries the old
        # device object. It must neither emit against the replacement's XID
        # nor mark the replacement device dead.
        self.assertEqual(registry.async_error("client-A", old_device, 999), "SUCCESS")
        self.assertEqual(registry.emitted_events, [])
        self.assertTrue(new_device.live)
        self.assertIs(registry.live_devices["device-A"], new_device)

        # A callback captured from the current generation remains deliverable.
        self.assertEqual(registry.async_error("client-A", new_device, 1000), "SUCCESS")
        self.assertEqual(registry.emitted_events, [
            ("ASYNC_ERROR", "client-A", 71, 1000),
        ])


    def test_disconnect_detaches_client_callback_links_but_keeps_backend_work(self) -> None:
        registry = AsyncSubmissionEventRegistry(live_connections={"client-a", "client-b"})
        device = AsyncDeviceIdentity(identity="device-a", xid=71)
        registry.register_device("client-a", device)
        submission = AsyncSubmissionIdentity(
            connection_identity="client-a",
            token=301,
            device_identity="device-a",
            device_xid=71,
            queue_key=(0, 0),
        )
        self.assertEqual(registry.accept_submission(submission), "SUCCESS")
        registry.select_queue_events("client-a", "device-a", (0, 0), 1)

        registry.disconnect("client-a")
        self.assertNotIn(("client-a", 301), registry.submissions)
        self.assertIs(registry.detached_submissions[("client-a", 301)], submission)
        self.assertFalse(any(key[0] == "client-a" for key in registry.queue_masks))

        # The backend's actual terminal result is still recorded, but it can
        # neither emit an event on the closed connection nor retain its link.
        self.assertEqual(registry.terminal_callback("client-a", 301, "COMPLETE"), "SUCCESS")
        self.assertEqual(submission.terminal, "COMPLETE")
        self.assertNotIn(("client-a", 301), registry.detached_submissions)
        self.assertEqual(registry.emitted_events, [])
        self.assertEqual(registry.terminal_callback("client-a", 301, "FAILED"), "BadValue")

    def test_disconnect_reserves_submission_token_until_detached_callback_retires(self) -> None:
        registry = AsyncSubmissionEventRegistry(live_connections={"client-a"})
        device = AsyncDeviceIdentity(identity="device-a", xid=71)
        registry.register_device("client-a", device)
        original = AsyncSubmissionIdentity(
            connection_identity="client-a",
            token=302,
            device_identity="device-a",
            device_xid=71,
            queue_key=(0, 0),
        )
        self.assertEqual(registry.accept_submission(original), "SUCCESS")
        registry.disconnect("client-a")
        self.assertIs(registry.detached_submissions[("client-a", 302)], original)

        # A reintroduced connection identity must not reuse a key still owned
        # by an accepted backend callback.
        registry.live_connections.add("client-a")
        replacement = AsyncSubmissionIdentity(
            connection_identity="client-a",
            token=302,
            device_identity="device-a",
            device_xid=71,
            queue_key=(0, 0),
        )
        self.assertEqual(registry.accept_submission(replacement), "BadValue")
        self.assertEqual(registry.terminal_callback("client-a", 302, "COMPLETE"), "SUCCESS")
        self.assertEqual(original.terminal, "COMPLETE")
        self.assertIsNone(replacement.terminal)
        self.assertNotIn(("client-a", 302), registry.detached_submissions)
        self.assertEqual(registry.accept_submission(replacement), "SUCCESS")

