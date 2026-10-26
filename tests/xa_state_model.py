"""Executable reference state models for XAverius request validation.

These are specification-level oracles, not server implementations. Keep stage
ordering and commit effects aligned with normative spec and conformance rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ImageState(str, Enum):
    AVAILABLE = "AVAILABLE"
    ACQUIRED = "ACQUIRED"
    PRESENT_PENDING = "PRESENT_PENDING"
    INVALID = "INVALID"


class SemaphoreKind(str, Enum):
    BINARY = "BINARY"
    TIMELINE = "TIMELINE"


class WaitState(str, Enum):
    READY = "READY"
    UNTRUSTED = "UNTRUSTED"
    INCOMPATIBLE = "INCOMPATIBLE"
    RESERVED = "RESERVED"


class BinarySignalState(str, Enum):
    UNSIGNALED = "UNSIGNALED"
    SIGNAL_PENDING = "SIGNAL_PENDING"
    SIGNALED = "SIGNALED"
    UNTRUSTED = "UNTRUSTED"


@dataclass
class SharedBinarySemaphore:
    """Canonical semaphore state shared by submission and presentation models."""
    signal_state: BinarySignalState = BinarySignalState.UNSIGNALED
    wait_reservation: tuple[str, int] | None = None
    signal_reservation: tuple[str, int] | None = None
    signal_consumed: bool = False


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
    binary_signal_states: list[BinarySignalState] = field(default_factory=list)
    pending_binary_waits: list[tuple[int, int]] = field(default_factory=list)
    accepted_tokens: set[int] = field(default_factory=set)
    pending_present_waits: list[tuple[int, int]] = field(default_factory=list)
    shared_semaphores: list[SharedBinarySemaphore] = field(default_factory=list)


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
    for index in request.wait_indices:
        shared = state.shared_semaphores[index] if index < len(state.shared_semaphores) else None
        signal_state = (
            shared.signal_state if shared is not None else
            state.binary_signal_states[index]
            if index < len(state.binary_signal_states)
            else BinarySignalState.UNSIGNALED
        )
        if signal_state is BinarySignalState.UNTRUSTED:
            return PresentResult("DEPENDENCY_FAILED", False)
        if ((shared is not None and shared.wait_reservation is not None)
                or any(pending_index == index for _token, pending_index in state.pending_present_waits)):
            return PresentResult("INVALID_SYNCHRONIZATION_STATE", False)

    # Commit point: all acceptance-visible changes happen together.
    state.accepted_tokens.add(request.token)
    for index in request.wait_indices:
        state.wait_states[index] = WaitState.RESERVED
        state.pending_present_waits.append((request.token, index))
        if index < len(state.shared_semaphores):
            state.shared_semaphores[index].wait_reservation = ("present", request.token)
    state.image_state = ImageState.PRESENT_PENDING
    return PresentResult("SUCCESS", True)


def finish_present_wait(
    state: PresentState, token: int, semaphore_index: int, *,
    consumed: bool | None,
) -> str:
    """Finalize one QueuePresent binary wait; None means payload outcome unknown."""
    reservation = (token, semaphore_index)
    if reservation not in state.pending_present_waits:
        return "BadValue"
    shared = (
        state.shared_semaphores[semaphore_index]
        if semaphore_index < len(state.shared_semaphores) else None
    )
    # Check the canonical reservation before even extending local mirrors:
    # stale callbacks must be mutation-free on every rejection path.
    if shared is not None and shared.wait_reservation != ("present", token):
        return "BadValue"
    if semaphore_index >= len(state.binary_signal_states):
        state.binary_signal_states.extend(
            [BinarySignalState.UNSIGNALED]
            * (semaphore_index + 1 - len(state.binary_signal_states))
        )
    if consumed is None:
        state.binary_signal_states[semaphore_index] = BinarySignalState.UNTRUSTED
        state.wait_states[semaphore_index] = WaitState.UNTRUSTED
        if shared is not None:
            shared.signal_state = BinarySignalState.UNTRUSTED
    elif consumed:
        state.binary_signal_states[semaphore_index] = BinarySignalState.UNSIGNALED
        state.wait_states[semaphore_index] = WaitState.READY
        if shared is not None:
            shared.signal_state = BinarySignalState.UNSIGNALED
            if shared.signal_reservation is not None:
                shared.signal_consumed = True
    else:
        # A known non-consumed payload retains its confirmed signal state.
        state.wait_states[semaphore_index] = WaitState.READY
    if shared is not None:
        shared.wait_reservation = None
    state.pending_present_waits.remove(reservation)
    return "SUCCESS"


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
    max_assembled_size: int | None = None


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
    flags_valid: bool = True
    module_valid: bool = True


def shader_module_data(state: ShaderAssemblyState, request: ShaderChunk) -> str:
    """Model ShaderModuleData; a bad chunk discards the whole shader assembly."""
    if not request.framing_valid:
        state.assembly_active, state.assembly = False, b""
        return "BadLength"
    if not request.padding_valid or not request.flags_valid:
        state.assembly_active, state.assembly = False, b""
        return "BadValue"
    # These are wire-field rules, so they precede XID resolution. A failed
    # chunk for this assembly discards the assembly rather than leaving stale
    # partial bytes addressable.
    if ((request.abort and (request.create or request.final or request.data))
            or (not request.abort and not request.data)):
        state.assembly_active, state.assembly = False, b""
        return "BadValue"
    if not state.xid_valid:
        return "BadValue"
    if not state.correct_type_and_ownership:
        return "BadMatch"
    if state.device_lost:
        # Device loss terminates all upload assemblies. ABORT cannot revive one.
        state.assembly_active, state.assembly = False, b""
        return "DEVICE_LOST"
    if request.abort:
        if not state.assembly_active:
            return "INVALID_SYNCHRONIZATION_STATE"
        state.assembly_active, state.assembly = False, b""
        return "SUCCESS"
    if request.create:
        # CREATE reserves the XID immediately; a second CREATE collides with
        # that reservation just as it collides with an already-live module.
        if state.module_live or state.assembly_active:
            return "BadIDChoice"
        if not request.chunk_valid:
            return "BadValue"
        if (state.max_assembled_size is not None
                and len(request.data) > state.max_assembled_size):
            return "BadValue"
        if not request.allocation_ok:
            return "ALLOCATION_FAILED"
        if request.final:
            if len(request.data) % 4 or not request.module_valid:
                return "BadValue"
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
    if (state.max_assembled_size is not None
            and len(combined) > state.max_assembled_size):
        state.assembly_active, state.assembly = False, b""
        return "BadValue"
    if request.final:
        if len(combined) % 4 or not request.module_valid:
            state.assembly_active, state.assembly = False, b""
            return "BadValue"
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
    pool_xid_valid: bool = True
    pool_type_and_ownership_valid: bool = True
    pool_matches_buffer: bool = True
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
    entries_well_formed: bool = True


def command_buffer_data(state: CommandBufferModel, request: CommandBufferChunk) -> str:
    """Validate a whole chunk before changing recording state or entries."""
    if not request.framing_valid or not request.entries_well_formed:
        return "BadLength"
    if request.operation == "ABORT" and request.entries:
        return "BadLength"
    # Request/entry structure has precedence over flags and command values.
    if not request.scalar_valid or request.operation not in {"CREATE", "CREATE_FINAL", "APPEND", "FINAL", "ABORT"}:
        return "BadValue"
    # Semantic entry values are phase 2 and therefore precede all XID lookup.
    if request.operation != "ABORT" and not request.entries_valid:
        return "BadValue"
    if request.operation in {"CREATE", "CREATE_FINAL"}:
        if not request.target_xid_available:
            return "BadIDChoice"
    elif not state.buffer_live:
        return "BadValue"
    if not state.pool_xid_valid or not state.pool_live:
        return "BadValue"
    if (not state.correct_type_and_ownership
            or not state.pool_type_and_ownership_valid
            or not state.pool_matches_buffer):
        return "BadMatch"
    if request.operation == "ABORT":
        # ABORT is allowed after device loss, but only for the exact parent
        # pool and a live buffer still in RECORDING.
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
        state.entries = list(request.entries)
        state.lifecycle = (
            CommandBufferLifecycle.EXECUTABLE if request.operation == "CREATE_FINAL"
            else CommandBufferLifecycle.RECORDING
        )
        return "SUCCESS"
    if state.lifecycle is not CommandBufferLifecycle.RECORDING:
        return "INVALID_SYNCHRONIZATION_STATE"
    # The complete chunk is checked before the append; prior chunks survive.
    state.entries.extend(request.entries)
    if request.operation == "FINAL":
        state.lifecycle = CommandBufferLifecycle.EXECUTABLE
    return "SUCCESS"


@dataclass
class SubmissionModel:
    device_lost: bool = False
    device_xid_valid: bool = True
    queue_xid_valid: bool = True
    fence_state_valid: bool = True
    command_buffers: list[CommandBufferModel] = field(default_factory=list)
    accepted_tokens: set[int] = field(default_factory=set)
    wait_states: list[WaitState] = field(default_factory=list)
    binary_signal_states: list[BinarySignalState] = field(default_factory=list)
    pending_binary_waits: list[tuple[int, int]] = field(default_factory=list)
    signal_slots: list[int | None] = field(default_factory=list)
    signal_counters: list[int] = field(default_factory=list)
    semaphore_kinds: list[SemaphoreKind] = field(default_factory=list)
    # Binary operations are tracked independently from timeline counters/slots.
    pending_binary_signals: list[tuple[int, int]] = field(default_factory=list)
    consumed_pending_binary_signals: set[tuple[int, int]] = field(default_factory=set)
    binary_signal_previous_states: dict[tuple[int, int], BinarySignalState] = field(default_factory=dict)
    binary_wait_previous_states: dict[tuple[int, int], BinarySignalState] = field(default_factory=dict)
    shared_semaphores: list[SharedBinarySemaphore] = field(default_factory=list)
    # Accepted timeline waits may target future values and coexist.
    pending_timeline_waits: list[tuple[int, int, int]] = field(default_factory=list)
    # (submission token, semaphore index, reserved timeline signal value).
    pending_timeline_signals: list[tuple[int, int, int]] = field(default_factory=list)
    queue_supported_stage_mask: int = 0xF
    fence_attached: bool = False
    pending_submissions: list[int] = field(default_factory=list)
    # Command buffers and an optional fence are owned by individual pending submissions.
    pending_command_buffers: list[tuple[int, int]] = field(default_factory=list)
    pending_fence_submissions: list[int] = field(default_factory=list)
    fence_status: str = "UNSIGNALED"
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
    signal_indices: tuple[int, ...] = ()
    signal_values: tuple[int, ...] = ()
    attach_fence: bool = False
    counts_valid: bool = True
    wait_values: tuple[int, ...] = ()
    wait_stage_masks: tuple[int, ...] = ()


def queue_submit(state: SubmissionModel, request: SubmitRequest) -> str:
    """Atomic submission oracle: validate every member, then reserve all state."""
    if (not state.framing_valid or not request.counts_valid
            or len(request.signal_indices) != len(request.signal_values)
            or (request.wait_values and len(request.wait_values) != len(request.wait_indices))
            or (request.wait_stage_masks and len(request.wait_stage_masks) != len(request.wait_indices))):
        return "BadLength"
    if (not state.scalar_valid or request.token == 0
            or len(set(request.wait_indices)) != len(request.wait_indices)
            or len(set(request.signal_indices)) != len(request.signal_indices)
            or bool(set(request.wait_indices) & set(request.signal_indices))
            or any(mask == 0 or mask & ~0xF for mask in request.wait_stage_masks)):
        return "BadValue"
    # Token reuse is a scalar error and therefore wins over XID resolution.
    if request.token in state.accepted_tokens:
        return "BadValue"
    if not state.device_xid_valid or not state.xids_valid:
        return "BadValue"
    # Resolve referenced resource XIDs in wire order before queue/type checks.
    if any(i < 0 or i >= len(state.command_buffers) for i in request.command_buffer_indices):
        return "BadValue"
    if any(i < 0 or i >= len(state.wait_states) for i in request.wait_indices):
        return "BadValue"
    if any(i < 0 or i >= len(state.signal_slots) for i in request.signal_indices):
        return "BadValue"
    # Queue family/index support and live type/ownership are match failures,
    # not unknown-XID failures; both precede Device Loss.
    if not state.queue_xid_valid or not state.types_and_ownership_valid:
        return "BadMatch"
    if state.device_lost:
        return "DEVICE_LOST"
    # Normative mutable-state order: optional Fence, Command Buffers, waits,
    # then signals. The Fence is not attached until the acceptance commit.
    if request.attach_fence and not state.fence_state_valid:
        return "INVALID_SYNCHRONIZATION_STATE"
    if any(state.command_buffers[i].lifecycle is not CommandBufferLifecycle.EXECUTABLE
           for i in request.command_buffer_indices):
        return "INVALID_SYNCHRONIZATION_STATE"
    # Validate each wait's typed value before its stage and mutable-state
    # checks, as required by the normative per-entry precedence.
    for pos, index in enumerate(request.wait_indices):
        kind = state.semaphore_kinds[index] if index < len(state.semaphore_kinds) else SemaphoreKind.BINARY
        value = request.wait_values[pos] if request.wait_values else 0
        if kind is SemaphoreKind.BINARY and value != 0:
            return "BadValue"
        if kind is SemaphoreKind.TIMELINE and not 0 <= value <= 0xFFFFFFFFFFFFFFFF:
            return "BadValue"
        mask = request.wait_stage_masks[pos] if request.wait_stage_masks else 0x1
        if mask & ~state.queue_supported_stage_mask:
            return "INVALID_SYNCHRONIZATION_STATE"
        wait_state = state.wait_states[index]
        if kind is SemaphoreKind.TIMELINE:
            # Timeline waits are level-triggered and may wait-before-signal.
            # Multiple accepted waits may share the same timeline semaphore.
            if wait_state in {WaitState.UNTRUSTED, WaitState.INCOMPATIBLE}:
                return ("DEPENDENCY_FAILED" if wait_state is WaitState.UNTRUSTED
                        else "INVALID_SYNCHRONIZATION_STATE")
        else:
            shared = state.shared_semaphores[index] if index < len(state.shared_semaphores) else None
            binary_state = (
                shared.signal_state if shared is not None else
                state.binary_signal_states[index]
                if index < len(state.binary_signal_states)
                else BinarySignalState.UNSIGNALED
            )
            if binary_state is BinarySignalState.UNTRUSTED:
                return "DEPENDENCY_FAILED"
            if wait_state is not WaitState.READY:
                return ("DEPENDENCY_FAILED" if wait_state is WaitState.UNTRUSTED
                        else "INVALID_SYNCHRONIZATION_STATE")
            if (shared is not None and shared.wait_reservation is not None) or any(
                pending_index == index for _token, pending_index in state.pending_binary_waits
            ):
                return "INVALID_SYNCHRONIZATION_STATE"
    # Validate all signal reservations before mutating any one of them.
    # Concrete per-entry errors precede the generic dependency fallback.
    for index, value in zip(request.signal_indices, request.signal_values):
        slot = state.signal_slots[index]
        kind = state.semaphore_kinds[index] if index < len(state.semaphore_kinds) else SemaphoreKind.TIMELINE
        if kind is SemaphoreKind.BINARY:
            if value != 0:
                return "BadValue"
            shared = state.shared_semaphores[index] if index < len(state.shared_semaphores) else None
            binary_state = (
                shared.signal_state if shared is not None else
                state.binary_signal_states[index]
                if index < len(state.binary_signal_states)
                else BinarySignalState.UNSIGNALED
            )
            if binary_state is BinarySignalState.UNTRUSTED:
                return "DEPENDENCY_FAILED"
            if binary_state is not BinarySignalState.UNSIGNALED:
                return "INVALID_SYNCHRONIZATION_STATE"
            if ((shared is not None and shared.signal_reservation is not None)
                    or slot is not None or any(
                        pending_index == index for _token, pending_index in state.pending_binary_signals
                    )):
                return "INVALID_SYNCHRONIZATION_STATE"
        else:
            counter = state.signal_counters[index] if index < len(state.signal_counters) else 0
            if not 0 <= value <= 0xFFFFFFFFFFFFFFFF:
                return "BadValue"
            pending_values = [
                pending_value
                for _token, pending_index, pending_value in state.pending_timeline_signals
                if pending_index == index
            ]
            if value <= counter or any(value <= pending for pending in pending_values):
                # The reservation list is authoritative: the summary slot can
                # change when callbacks for concurrent submissions arrive out
                # of order, but every non-terminal reservation remains binding.
                return "BadValue"
    # A generic dependency failure is the fallback only after all concrete
    # wait and signal entry errors have been ruled out.
    if not state.dependencies_valid:
        return "DEPENDENCY_FAILED"
    # Acceptance commit point.
    state.accepted_tokens.add(request.token)
    for pos, i in enumerate(request.wait_indices):
        kind = state.semaphore_kinds[i] if i < len(state.semaphore_kinds) else SemaphoreKind.BINARY
        if kind is SemaphoreKind.TIMELINE:
            value = request.wait_values[pos] if request.wait_values else 0
            state.pending_timeline_waits.append((request.token, i, value))
        else:
            state.wait_states[i] = WaitState.RESERVED
            if i >= len(state.binary_signal_states):
                state.binary_signal_states.extend(
                    [BinarySignalState.UNSIGNALED]
                    * (i + 1 - len(state.binary_signal_states))
                )
            state.binary_wait_previous_states[(request.token, i)] = state.binary_signal_states[i]
            state.pending_binary_waits.append((request.token, i))
            if i < len(state.shared_semaphores):
                state.shared_semaphores[i].wait_reservation = ("submit", request.token)
    for i in request.command_buffer_indices:
        state.command_buffers[i].lifecycle = CommandBufferLifecycle.PENDING
        state.pending_command_buffers.append((request.token, i))
    for index, value in zip(request.signal_indices, request.signal_values):
        kind = state.semaphore_kinds[index] if index < len(state.semaphore_kinds) else SemaphoreKind.TIMELINE
        state.signal_slots[index] = value
        if kind is SemaphoreKind.TIMELINE:
            state.pending_timeline_signals.append((request.token, index, value))
        else:
            if index >= len(state.binary_signal_states):
                state.binary_signal_states.extend(
                    [BinarySignalState.UNSIGNALED]
                    * (index + 1 - len(state.binary_signal_states))
                )
            state.binary_signal_previous_states[(request.token, index)] = state.binary_signal_states[index]
            state.binary_signal_states[index] = BinarySignalState.SIGNAL_PENDING
            state.pending_binary_signals.append((request.token, index))
            if index < len(state.shared_semaphores):
                state.shared_semaphores[index].signal_state = BinarySignalState.SIGNAL_PENDING
                state.shared_semaphores[index].signal_reservation = ("submit", request.token)
                state.shared_semaphores[index].signal_consumed = False
    if request.attach_fence:
        state.fence_attached = True
        state.fence_state_valid = False
        state.fence_status = "PENDING"
        state.pending_fence_submissions.append(request.token)
    state.pending_submissions.append(request.token)
    return "SUCCESS"


def signal_timeline_host(state: SubmissionModel, semaphore_index: int, value: int) -> str:
    """Model SignalSemaphore's counter/reservation validation and atomic update."""
    if state.device_lost:
        return "DEVICE_LOST"
    if semaphore_index < 0 or semaphore_index >= len(state.signal_counters):
        return "BadValue"
    kind = (state.semaphore_kinds[semaphore_index]
            if semaphore_index < len(state.semaphore_kinds)
            else SemaphoreKind.TIMELINE)
    if kind is not SemaphoreKind.TIMELINE:
        return "BadMatch"
    if value < 0 or value > 0xFFFFFFFFFFFFFFFF:
        return "BadValue"
    if value <= state.signal_counters[semaphore_index]:
        return "INVALID_SYNCHRONIZATION_STATE"
    pending_values = [
        pending_value
        for _token, index, pending_value in state.pending_timeline_signals
        if index == semaphore_index
    ]
    # A host signal may advance a wait to an intermediate value, but must not
    # jump over any still-pending GPU signal reservation.
    if any(value >= pending_value for pending_value in pending_values):
        return "INVALID_SYNCHRONIZATION_STATE"
    state.signal_counters[semaphore_index] = value
    return "SUCCESS"


def finish_submission(
    state: SubmissionModel, token: int, success: bool, *,
    binary_payload_unchanged: set[tuple[str, int]] | None = None,
) -> str:
    """Finalize a submission once; Device Loss makes late success callbacks fail."""
    if token not in state.pending_submissions:
        # Terminal callbacks are idempotently rejected without touching state.
        return "BadValue"
    state.pending_submissions.remove(token)
    # A backend may race a Device-Loss notification and later report success.
    # Once loss has been observed, that callback must not publish signal values.
    effective_success = success and not state.device_lost
    for submission_token, index, value in list(state.pending_timeline_signals):
        if submission_token != token:
            continue
        if effective_success:
            state.signal_counters[index] = max(state.signal_counters[index], value)
        state.pending_timeline_signals.remove((submission_token, index, value))
        kind = (state.semaphore_kinds[index]
                if index < len(state.semaphore_kinds) else SemaphoreKind.TIMELINE)
        if kind is SemaphoreKind.TIMELINE:
            # Keep the compatibility slot equal to the highest still-pending
            # reservation, even when a higher-valued operation fails first.
            remaining = [
                pending_value
                for _pending_token, pending_index, pending_value
                in state.pending_timeline_signals
                if pending_index == index
            ]
            state.signal_slots[index] = max(remaining) if remaining else None
    for reservation in list(state.pending_binary_signals):
        signal_token, index = reservation
        if signal_token != token:
            continue
        state.pending_binary_signals.remove(reservation)
        if index >= len(state.binary_signal_states):
            state.binary_signal_states.extend(
                [BinarySignalState.UNSIGNALED]
                * (index + 1 - len(state.binary_signal_states))
            )
        shared = state.shared_semaphores[index] if index < len(state.shared_semaphores) else None
        consumed = (
            reservation in state.consumed_pending_binary_signals
            or (shared is not None and shared.signal_reservation == ("submit", token)
                and shared.signal_consumed)
        )
        state.consumed_pending_binary_signals.discard(reservation)
        previous = state.binary_signal_previous_states.pop(reservation, BinarySignalState.UNSIGNALED)
        current = state.binary_signal_states[index]
        # QueuePresent owns the canonical cross-API payload outcome. If its
        # callback made the semaphore untrusted, a later Submit callback must
        # not overwrite that knowledge with a local stale snapshot.
        if shared is not None and shared.signal_state is BinarySignalState.UNTRUSTED:
            current = BinarySignalState.UNTRUSTED
            state.binary_signal_states[index] = BinarySignalState.UNTRUSTED
        if current is BinarySignalState.UNTRUSTED:
            # An unknown cross-API payload outcome is stronger than a stale
            # local "unchanged" report from the Submit callback.
            state.binary_signal_states[index] = BinarySignalState.UNTRUSTED
        elif not effective_success:
            # A cross-API wait callback may already have proved that this
            # pending signal was consumed. Device Loss invalidates an
            # unobserved completion, but must not erase that known consumption.
            state.binary_signal_states[index] = (
                BinarySignalState.UNSIGNALED if consumed else
                BinarySignalState.UNTRUSTED
                if not (binary_payload_unchanged and ("signal", index) in binary_payload_unchanged)
                else previous
            )
        elif current is BinarySignalState.UNTRUSTED:
            pass
        elif consumed:
            state.binary_signal_states[index] = BinarySignalState.UNSIGNALED
        else:
            state.binary_signal_states[index] = BinarySignalState.SIGNALED
        state.signal_slots[index] = None
        if index < len(state.shared_semaphores):
            shared = state.shared_semaphores[index]
            if shared.signal_reservation == ("submit", token):
                shared.signal_reservation = None
                shared.signal_consumed = False
                shared.signal_state = state.binary_signal_states[index]
    for reservation in list(state.pending_binary_waits):
        wait_token, index = reservation
        if wait_token != token:
            continue
        state.pending_binary_waits.remove(reservation)
        if index >= len(state.binary_signal_states):
            state.binary_signal_states.extend(
                [BinarySignalState.UNSIGNALED]
                * (index + 1 - len(state.binary_signal_states))
            )
        previous = state.binary_wait_previous_states.pop(reservation, BinarySignalState.UNSIGNALED)
        if effective_success:
            shared = state.shared_semaphores[index] if index < len(state.shared_semaphores) else None
            signal_state = state.binary_signal_states[index]
            # A callback from another API/model may have already established
            # the canonical payload state. Never make a stale local mirror
            # authoritative over a shared UNTRUSTED outcome.
            if shared is not None and shared.signal_state is BinarySignalState.UNTRUSTED:
                signal_state = BinarySignalState.UNTRUSTED
                state.binary_signal_states[index] = BinarySignalState.UNTRUSTED
            if signal_state is BinarySignalState.UNTRUSTED:
                state.wait_states[index] = WaitState.UNTRUSTED
                if shared is not None and shared.wait_reservation == ("submit", token):
                    shared.wait_reservation = None
                continue
            if signal_state is BinarySignalState.SIGNAL_PENDING:
                signal_token = next(
                    (pending_token for pending_token, pending_index
                     in state.pending_binary_signals if pending_index == index),
                    None,
                )
                if signal_token is not None:
                    state.consumed_pending_binary_signals.add((signal_token, index))
                # A signal may be owned by a different SubmissionModel (e.g.
                # another queue). Record consumption on the canonical object,
                # or that owner's later terminal callback could resurrect it.
                if shared is not None and shared.signal_reservation is not None:
                    shared.signal_consumed = True
            state.binary_signal_states[index] = BinarySignalState.UNSIGNALED
            state.wait_states[index] = WaitState.READY
        else:
            unchanged = binary_payload_unchanged and ("wait", index) in binary_payload_unchanged
            shared = state.shared_semaphores[index] if index < len(state.shared_semaphores) else None
            if unchanged:
                # The callback only proves this wait left the payload alone;
                # it does not authorize restoring an older snapshot over a
                # signal callback that completed while this wait was pending.
                current = shared.signal_state if shared is not None else previous
                state.binary_signal_states[index] = current
                state.wait_states[index] = (
                    WaitState.UNTRUSTED if current is BinarySignalState.UNTRUSTED
                    else WaitState.READY
                )
            else:
                state.binary_signal_states[index] = BinarySignalState.UNTRUSTED
                state.wait_states[index] = WaitState.UNTRUSTED
        if index < len(state.shared_semaphores):
            shared = state.shared_semaphores[index]
            if shared.wait_reservation == ("submit", token):
                shared.wait_reservation = None
                shared.signal_state = state.binary_signal_states[index]
    state.pending_timeline_waits = [
        wait for wait in state.pending_timeline_waits if wait[0] != token
    ]
    if token in state.pending_fence_submissions:
        state.pending_fence_submissions.remove(token)
        state.fence_attached = False
        state.fence_status = "SIGNALED" if effective_success else "FAILED"
    for submission_token, index in list(state.pending_command_buffers):
        if submission_token != token:
            continue
        command_buffer = state.command_buffers[index]
        command_buffer.lifecycle = (
            CommandBufferLifecycle.EXECUTABLE if effective_success
            else CommandBufferLifecycle.INVALID
        )
        state.pending_command_buffers.remove((submission_token, index))
    return "SUCCESS"


def reset_fence(state: SubmissionModel) -> str:
    """Model ResetFence state eligibility and atomic state transition."""
    if state.device_lost:
        return "DEVICE_LOST"
    if state.fence_status not in {"SIGNALED", "FAILED"} or state.fence_attached:
        return "INVALID_SYNCHRONIZATION_STATE"
    state.fence_status = "UNSIGNALED"
    state.fence_state_valid = True
    return "SUCCESS"
