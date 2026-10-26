"""Executable reference state model for XAverius QueuePresent validation.

This is a specification-level oracle, not a server implementation. Keep stage
ordering and commit effects aligned with spec/presentation.md and spec/errors.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ImageState(str, Enum):
    AVAILABLE = "AVAILABLE"
    ACQUIRED = "ACQUIRED"
    PRESENT_PENDING = "PRESENT_PENDING"
    INVALID = "INVALID"


class WaitState(str, Enum):
    READY = "READY"
    UNTRUSTED = "UNTRUSTED"
    INCOMPATIBLE = "INCOMPATIBLE"
    RESERVED = "RESERVED"


@dataclass
class PresentState:
    device_lost: bool = False
    surface_lost: bool = False
    out_of_date: bool = False
    present_supported: bool = True
    valid_device_xid: bool = True
    valid_swapchain_xid: bool = True
    valid_wait_xids: tuple[bool, ...] = ()
    correct_types_and_ownership: bool = True
    valid_queue: bool = True
    valid_image_index: bool = True
    image_state: ImageState = ImageState.ACQUIRED
    wait_states: list[WaitState] = field(default_factory=list)
    accepted_tokens: set[int] = field(default_factory=set)


@dataclass(frozen=True)
class PresentRequest:
    token: int = 1
    wait_indices: tuple[int, ...] = ()
    wire_length_valid: bool = True
    scalar_fields_valid: bool = True


@dataclass(frozen=True)
class PresentResult:
    result: str
    accepted: bool


def _first_bad_wait(request: PresentRequest, state: PresentState) -> str | None:
    for index in request.wait_indices:
        wait_state = state.wait_states[index]
        if wait_state is WaitState.UNTRUSTED:
            return "DEPENDENCY_FAILED"
        if wait_state is not WaitState.READY:
            return "INVALID_SYNCHRONIZATION_STATE"
    return None


def queue_present(state: PresentState, request: PresentRequest) -> PresentResult:
    """Validate in normative order, then commit all acceptance mutations together.

    The model uses boolean fixtures for wire/XID/type/queue checks so tests can
    create mixed-failure requests without depending on a real X11 resource DB.
    A rejection performs no mutation. Independent lifecycle changes are modeled
    by changing state before calling this function; they are not rolled back.
    """
    # Stage 1: wire framing / checked length.
    if not request.wire_length_valid:
        return PresentResult("BadLength", False)

    # Stage 2: scalar syntax; token zero and duplicate waits are scalar errors.
    if (not request.scalar_fields_valid or request.token == 0
            or len(set(request.wait_indices)) != len(request.wait_indices)):
        return PresentResult("BadValue", False)

    # Stage 3: XID resolution in wire order: Device, Swapchain, then waits.
    if not state.valid_device_xid or not state.valid_swapchain_xid:
        return PresentResult("BadValue", False)
    if any(
        index < 0 or index >= len(state.valid_wait_xids)
        or index >= len(state.wait_states)
        or not state.valid_wait_xids[index]
        for index in request.wait_indices
    ):
        return PresentResult("BadValue", False)

    # Stage 4: live type, ownership, and cross-device checks.
    if not state.correct_types_and_ownership:
        return PresentResult("BadMatch", False)

    # Stage 5: Device availability precedes queue/image/lifecycle state.
    if state.device_lost:
        return PresentResult("DEVICE_LOST", False)

    # Stage 6: immutable queue/index constraints.
    if not state.valid_queue or not state.valid_image_index:
        return PresentResult("BadValue", False)

    # Stage 7: lifecycle statuses.
    if state.surface_lost:
        return PresentResult("SURFACE_LOST", False)
    if state.out_of_date:
        return PresentResult("OUT_OF_DATE", False)

    # Stage 8: queue presentation capability, then accepted-token reuse.
    if not state.present_supported:
        return PresentResult("BadMatch", False)
    if request.token in state.accepted_tokens:
        return PresentResult("BadValue", False)

    # Stage 9: image state precedes wait eligibility.
    if state.image_state is not ImageState.ACQUIRED:
        return PresentResult("INVALID_SYNCHRONIZATION_STATE", False)
    wait_error = _first_bad_wait(request, state)
    if wait_error:
        return PresentResult(wait_error, False)

    # Commit point: all acceptance-visible changes happen together.
    state.accepted_tokens.add(request.token)
    for index in request.wait_indices:
        state.wait_states[index] = WaitState.RESERVED
    state.image_state = ImageState.PRESENT_PENDING
    return PresentResult("SUCCESS", True)


class CommandBufferLifecycle(str, Enum):
    INITIAL = "INITIAL"
    RECORDING = "RECORDING"
    EXECUTABLE = "EXECUTABLE"
    PENDING = "PENDING"
    INVALID = "INVALID"


@dataclass
class ShaderAssemblyState:
    """Minimal ShaderModuleData lifecycle and assembly state."""
    device_lost: bool = False
    xid_valid: bool = True
    correct_type_and_ownership: bool = True
    module_live: bool = False
    assembly_active: bool = False
    assembly: bytes = b""
    module_code: bytes | None = None


@dataclass(frozen=True)
class ShaderChunk:
    data: bytes = b""
    create: bool = False
    final: bool = False
    abort: bool = False
    framing_valid: bool = True
    padding_valid: bool = True
    chunk_valid: bool = True
    allocation_ok: bool = True


def shader_module_data(state: ShaderAssemblyState, request: ShaderChunk) -> str:
    """Model ShaderModuleData; a bad chunk discards the whole shader assembly."""
    if not request.framing_valid:
        state.assembly_active, state.assembly = False, b""
        return "BadLength"
    if not request.padding_valid:
        state.assembly_active, state.assembly = False, b""
        return "BadValue"
    if not state.xid_valid:
        return "BadValue"
    if not state.correct_type_and_ownership:
        return "BadMatch"
    if request.abort:
        if request.create or request.final or request.data:
            return "BadValue"
        state.assembly_active, state.assembly = False, b""
        return "SUCCESS"
    if state.device_lost:
        state.assembly_active, state.assembly = False, b""
        return "DEVICE_LOST"
    if request.create:
        if state.module_live or state.assembly_active:
            return "BadIDChoice" if state.module_live else "INVALID_SYNCHRONIZATION_STATE"
        if not request.chunk_valid:
            return "BadValue"
        if not request.allocation_ok:
            return "ALLOCATION_FAILED"
        if request.final:
            state.module_live = True
            state.module_code = bytes(request.data)
            return "SUCCESS"
        state.assembly_active = True
        state.assembly = bytes(request.data)
        return "SUCCESS"
    if not state.assembly_active:
        return "INVALID_SYNCHRONIZATION_STATE"
    if not request.chunk_valid:
        state.assembly_active, state.assembly = False, b""
        return "BadValue"
    if not request.allocation_ok:
        state.assembly_active, state.assembly = False, b""
        return "ALLOCATION_FAILED"
    combined = state.assembly + request.data
    if request.final:
        state.module_live = True
        state.module_code = combined
        state.assembly_active, state.assembly = False, b""
    else:
        state.assembly = combined
    return "SUCCESS"


@dataclass
class CommandBufferModel:
    lifecycle: CommandBufferLifecycle = CommandBufferLifecycle.INITIAL
    device_lost: bool = False
    buffer_live: bool = True
    pool_live: bool = True
    correct_type_and_ownership: bool = True
    entries: list[bytes] = field(default_factory=list)


@dataclass(frozen=True)
class CommandBufferChunk:
    operation: str = "APPEND"  # CREATE, APPEND, FINAL, ABORT
    entries: tuple[bytes, ...] = ()
    framing_valid: bool = True
    scalar_valid: bool = True
    target_xid_available: bool = True
    entries_valid: bool = True


def command_buffer_data(state: CommandBufferModel, request: CommandBufferChunk) -> str:
    """Validate a whole chunk before changing recording state or entries."""
    if not request.framing_valid:
        return "BadLength"
    if not request.scalar_valid or request.operation not in {"CREATE", "CREATE_FINAL", "APPEND", "FINAL", "ABORT"}:
        return "BadValue"
    if request.operation == "CREATE" and not request.target_xid_available:
        return "BadIDChoice"
    if not state.buffer_live or not state.pool_live:
        return "BadValue"
    if not state.correct_type_and_ownership:
        return "BadMatch"
    if request.operation == "ABORT":
        if state.lifecycle is not CommandBufferLifecycle.RECORDING:
            return "INVALID_SYNCHRONIZATION_STATE"
        state.entries.clear()
        state.lifecycle = CommandBufferLifecycle.INITIAL
        return "SUCCESS"
    if state.device_lost:
        return "DEVICE_LOST"
    if request.operation in {"CREATE", "CREATE_FINAL"}:
        if state.lifecycle is not CommandBufferLifecycle.INITIAL:
            return "INVALID_SYNCHRONIZATION_STATE"
        if not request.entries_valid:
            return "BadValue"
        state.entries = list(request.entries)
        state.lifecycle = (
            CommandBufferLifecycle.EXECUTABLE if request.operation == "CREATE_FINAL"
            else CommandBufferLifecycle.RECORDING
        )
        return "SUCCESS"
    if state.lifecycle is not CommandBufferLifecycle.RECORDING:
        return "INVALID_SYNCHRONIZATION_STATE"
    if not request.entries_valid:
        return "BadValue"
    # The complete chunk is checked before the append; prior chunks survive.
    state.entries.extend(request.entries)
    if request.operation == "FINAL":
        state.lifecycle = CommandBufferLifecycle.EXECUTABLE
    return "SUCCESS"


@dataclass
class SubmissionModel:
    device_lost: bool = False
    device_xid_valid: bool = True
    command_buffers: list[CommandBufferModel] = field(default_factory=list)
    token: int = 1
    accepted_tokens: set[int] = field(default_factory=set)
    wait_states: list[WaitState] = field(default_factory=list)
    wait_indices: tuple[int, ...] = ()
    signal_slots: list[int | None] = field(default_factory=list)
    signal_values: tuple[int, ...] = ()
    fence_attached: bool = False
    pending_submissions: list[int] = field(default_factory=list)
    framing_valid: bool = True
    scalar_valid: bool = True
    xids_valid: bool = True
    types_and_ownership_valid: bool = True
    dependencies_valid: bool = True


@dataclass(frozen=True)
class SubmitRequest:
    token: int = 1
    command_buffer_indices: tuple[int, ...] = (0,)
    wait_indices: tuple[int, ...] = ()
    signal_values: tuple[int, ...] = ()
    attach_fence: bool = False


def queue_submit(state: SubmissionModel, request: SubmitRequest) -> str:
    """Atomic submission oracle: validate every member, then reserve all state."""
    if not state.framing_valid:
        return "BadLength"
    if (not state.scalar_valid or request.token == 0
            or len(set(request.wait_indices)) != len(request.wait_indices)
            or len(set(request.command_buffer_indices)) != len(request.command_buffer_indices)
            or (request.signal_values and len(request.signal_values) != len(state.signal_slots))):
        return "BadValue"
    if not state.device_xid_valid or not state.xids_valid:
        return "BadValue"
    if not state.types_and_ownership_valid:
        return "BadMatch"
    if state.device_lost:
        return "DEVICE_LOST"
    if request.token in state.accepted_tokens:
        return "BadValue"
    if any(i < 0 or i >= len(state.command_buffers) for i in request.command_buffer_indices):
        return "BadValue"
    if any(i < 0 or i >= len(state.wait_states) for i in request.wait_indices):
        return "BadValue"
    if any(state.command_buffers[i].lifecycle is not CommandBufferLifecycle.EXECUTABLE
           for i in request.command_buffer_indices):
        return "INVALID_SYNCHRONIZATION_STATE"
    if any(state.wait_states[i] is not WaitState.READY for i in request.wait_indices):
        return "INVALID_SYNCHRONIZATION_STATE"
    if not state.dependencies_valid:
        return "DEPENDENCY_FAILED"
    # Validate all signal reservations before mutating any one of them.
    for slot, value in zip(state.signal_slots, request.signal_values):
        if slot is not None and value <= slot:
            return "INVALID_SYNCHRONIZATION_STATE"
    # Acceptance commit point.
    state.accepted_tokens.add(request.token)
    for i in request.wait_indices:
        state.wait_states[i] = WaitState.RESERVED
    for i in request.command_buffer_indices:
        state.command_buffers[i].lifecycle = CommandBufferLifecycle.PENDING
    if request.signal_values:
        state.signal_slots[:] = list(request.signal_values)
    state.fence_attached = request.attach_fence
    state.pending_submissions.append(request.token)
    return "SUCCESS"
