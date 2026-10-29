"""Executable reference state models for XAverius request validation.

These are specification-level oracles, not server implementations. Keep stage
ordering and commit effects aligned with normative spec and conformance rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from weakref import ReferenceType, ref


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
    device_lost: bool = False
    signal_state: BinarySignalState = BinarySignalState.UNSIGNALED
    wait_reservation: tuple[str, int] | None = None
    wait_reservation_owner: object | None = field(default=None, repr=False, compare=False)
    signal_reservation: tuple[str, int] | None = None
    signal_reservation_owner: object | None = field(default=None, repr=False, compare=False)
    signal_consumed: bool = False
    # Durable evidence that a Submit signal was consumed, even after its
    # owner callback retires the transient reservation.
    signal_consumption_confirmed: bool = False
    # Provenance survives the producer callback retiring its reservation, so
    # a later Present wait can record confirmed consumption of that payload.
    signal_from_submit: bool = False
    # Weak references let device loss fan out across partially overlapping
    # semaphore sets without keeping otherwise-dead models alive.
    owners: list[ReferenceType] = field(default_factory=list, repr=False, compare=False)


def _register_semaphore_owner(state: PresentState | SubmissionModel) -> None:
    for shared in state.shared_semaphores:
        # Prune dead weakrefs and deduplicate live owners by object identity.
        # Merely checking whether this state is present leaves pre-existing
        # duplicate refs in place indefinitely, inflating every loss traversal.
        live_owners: list[ReferenceType] = []
        seen_owner_ids: set[int] = set()
        registered = False
        for owner_ref in shared.owners:
            owner = owner_ref()
            if owner is None or id(owner) in seen_owner_ids:
                continue
            seen_owner_ids.add(id(owner))
            live_owners.append(owner_ref)
            if owner is state:
                registered = True
        if not registered:
            live_owners.append(ref(state))
        shared.owners[:] = live_owners


def _unregister_semaphore_owner(state: PresentState | SubmissionModel) -> None:
    """Detach a disconnected model from shared-semaphore owner indexes.

    Keep the model's semaphore list intact: already accepted backend callbacks
    still need those objects to retire their own reservations safely. Normalize
    each surviving index as well, so stale or duplicated owner links do not
    accumulate when disconnect cleanup is retried.
    """
    seen_shared_ids: set[int] = set()
    for shared in state.shared_semaphores:
        if id(shared) in seen_shared_ids:
            continue
        seen_shared_ids.add(id(shared))
        live_owners: list[ReferenceType] = []
        seen_owner_ids: set[int] = set()
        for owner_ref in shared.owners:
            owner = owner_ref()
            if owner is None or owner is state or id(owner) in seen_owner_ids:
                continue
            seen_owner_ids.add(id(owner))
            live_owners.append(owner_ref)
        shared.owners[:] = live_owners


def _propagate_device_loss(origin: PresentState | SubmissionModel) -> None:
    """Propagate loss through the transitive closure of overlapping semaphore sets."""
    pending = [origin]
    seen_models: set[int] = set()
    models: list[PresentState | SubmissionModel] = []
    shared_seen: set[int] = set()
    semaphores: list[SharedBinarySemaphore] = []
    while pending:
        state = pending.pop()
        if id(state) in seen_models:
            continue
        seen_models.add(id(state))
        models.append(state)
        for shared in state.shared_semaphores:
            if id(shared) not in shared_seen:
                shared_seen.add(id(shared))
                semaphores.append(shared)
            # Traversal is also a cleanup opportunity: a semaphore may not be
            # registered again after an owner dies, so registration-time
            # pruning alone cannot guarantee that stale refs disappear.
            live_owner_refs: list[ReferenceType] = []
            seen_owner_ids: set[int] = set()
            for owner_ref in shared.owners:
                owner = owner_ref()
                if owner is None or id(owner) in seen_owner_ids:
                    continue
                seen_owner_ids.add(id(owner))
                live_owner_refs.append(owner_ref)
                if id(owner) not in seen_models:
                    pending.append(owner)
            shared.owners[:] = live_owner_refs
    for state in models:
        state.device_lost = True
    for shared in semaphores:
        shared.device_lost = True
    # Logical terminal outcome and backend cleanup are separate. Record the
    # device-loss outcome for every linked pending submission immediately, but
    # retain foreign operation records until their callbacks retire reservations
    # and backend-access holds. The origin Submit can use the normal finalizer
    # now; other models must not lose their callback-cleanup records.
    for state in models:
        if isinstance(state, SubmissionModel):
            for token in state.pending_submissions:
                state.terminal_submission_status[token] = "DEVICE_LOST"
    if isinstance(origin, SubmissionModel):
        for token in list(origin.pending_submissions):
            finish_submission(origin, token, success=False)
    for state in models:
        if not isinstance(state, PresentState):
            continue
        pending_present = list(state.pending_present_tokens)
        for token in pending_present:
            state.pending_present_tokens.remove(token)
            state.terminal_present_status[token] = "DEVICE_LOST"
        if pending_present:
            state.image_state = ImageState.INVALID
    for shared in semaphores:
        known_empty = (
            shared.signal_state is BinarySignalState.UNSIGNALED
            and shared.signal_consumption_confirmed
        )
        if not known_empty:
            shared.signal_state = BinarySignalState.UNTRUSTED
            shared.signal_reservation = None
            shared.signal_reservation_owner = None
            shared.signal_consumed = False
        shared.signal_from_submit = False
    for state in models:
        for index, shared in enumerate(state.shared_semaphores):
            known_empty = (
                shared.signal_state is BinarySignalState.UNSIGNALED
                and shared.signal_consumption_confirmed
            )
            if index < len(state.binary_signal_states):
                state.binary_signal_states[index] = (
                    BinarySignalState.UNSIGNALED if known_empty
                    else BinarySignalState.UNTRUSTED
                )
            if index < len(state.wait_states):
                state.wait_states[index] = (
                    WaitState.READY
                    if known_empty and isinstance(state, SubmissionModel)
                    else WaitState.UNTRUSTED
                )


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
    pending_present_tokens: set[int] = field(default_factory=set)
    terminal_present_status: dict[int, str] = field(default_factory=dict)
    shared_semaphores: list[SharedBinarySemaphore] = field(default_factory=list)

    def __post_init__(self) -> None:
        _register_semaphore_owner(self)


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
    if state.device_lost or any(shared.device_lost for shared in state.shared_semaphores):
        _propagate_device_loss(state)
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
        if ((shared is not None and (
                    shared.wait_reservation is not None or shared.signal_consumed
                ))
                or any(pending_index == index for _token, pending_index in state.pending_present_waits)):
            # A prior wait may have consumed a still-pending Submit signal
            # before that signal's terminal callback retires its reservation.
            # Do not accept a second waiter against that already-consumed payload.
            return PresentResult("INVALID_SYNCHRONIZATION_STATE", False)

    # Commit point: all acceptance-visible changes happen together.
    state.accepted_tokens.add(request.token)
    state.pending_present_tokens.add(request.token)
    for index in request.wait_indices:
        state.wait_states[index] = WaitState.RESERVED
        state.pending_present_waits.append((request.token, index))
        if index < len(state.shared_semaphores):
            state.shared_semaphores[index].wait_reservation = ("present", request.token)
            state.shared_semaphores[index].wait_reservation_owner = state
    state.image_state = ImageState.PRESENT_PENDING
    return PresentResult("SUCCESS", True)


def finish_present_terminal(state: PresentState, token: int, status: str) -> str:
    """Commit one terminal outcome for an accepted QueuePresent exactly once."""
    if token not in state.pending_present_tokens:
        return "BadValue"
    if status not in {
        "SUCCESS", "OUT_OF_DATE", "SURFACE_LOST", "DEVICE_LOST",
        "PRESENTATION_FAILED",
    }:
        return "BadValue"
    state.pending_present_tokens.remove(token)
    state.terminal_present_status[token] = status
    if status == "SUCCESS":
        state.image_state = ImageState.AVAILABLE
    else:
        state.image_state = ImageState.INVALID
    if status == "DEVICE_LOST":
        # A backend terminal callback may be the first observer of Device Loss.
        # Propagate it across shared semaphore owners just like the explicit
        # device-loss notification path; this terminal token is already retired.
        _propagate_device_loss(state)
    return "SUCCESS"


def mark_present_device_lost(state: PresentState) -> str:
    """Propagate device loss to all models connected by shared semaphores."""
    _propagate_device_loss(state)
    return "SUCCESS"


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
    if shared is not None and (
        shared.wait_reservation != ("present", token)
        or shared.wait_reservation_owner is not state
    ):
        return "BadValue"
    if semaphore_index >= len(state.binary_signal_states):
        state.binary_signal_states.extend(
            [BinarySignalState.UNSIGNALED]
            * (semaphore_index + 1 - len(state.binary_signal_states))
        )
    # A callback can be the first Present-side observation after device loss.
    # Reconcile every shared semaphore mirror before applying this callback;
    # otherwise an earlier, already-retired wait can remain locally READY or
    # SIGNAL_PENDING even though its canonical payload is now UNTRUSTED.
    for index, canonical in enumerate(state.shared_semaphores):
        if canonical.signal_state is not BinarySignalState.UNTRUSTED:
            continue
        if index >= len(state.binary_signal_states):
            state.binary_signal_states.extend(
                [BinarySignalState.UNSIGNALED]
                * (index + 1 - len(state.binary_signal_states))
            )
        if index >= len(state.wait_states):
            state.wait_states.extend(
                [WaitState.READY] * (index + 1 - len(state.wait_states))
            )
        state.binary_signal_states[index] = BinarySignalState.UNTRUSTED
        state.wait_states[index] = WaitState.UNTRUSTED
    if shared is not None and (
        shared.signal_state is BinarySignalState.UNTRUSTED
        or shared.device_lost or state.device_lost
    ):
        # Device loss is device-wide; a late wait callback from a different
        # queue cannot turn a quarantined payload back into a trusted one.
        state.binary_signal_states[semaphore_index] = BinarySignalState.UNTRUSTED
        state.wait_states[semaphore_index] = WaitState.UNTRUSTED
        shared.signal_state = BinarySignalState.UNTRUSTED
    elif consumed is None:
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
            # Only a payload known to originate from Submit can establish
            # durable Submit-consumption evidence. Provenance remains after
            # the producer callback retires its transient reservation.
            if (shared.signal_reservation is not None
                    and shared.signal_reservation[0] == "submit") or shared.signal_from_submit:
                shared.signal_consumption_confirmed = True
            shared.signal_from_submit = False
    else:
        # A known non-consumed payload retains the canonical shared state.
        # The present model's local mirror may predate a competing Submit
        # signal callback, so never leave it stale after resolving this wait.
        if shared is not None:
            state.binary_signal_states[semaphore_index] = shared.signal_state
        state.wait_states[semaphore_index] = WaitState.READY
    if shared is not None:
        shared.wait_reservation = None
        shared.wait_reservation_owner = None
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
class RetiredCommandBufferRecording:
    """References retained for an older recording while its backend holds drain."""
    epoch: int = 0
    entries: list[bytes] = field(default_factory=list)
    descriptor_sets: list[DescriptorSetLifetime] = field(default_factory=list)
    indirect_buffer_refs: set[str] = field(default_factory=set)
    backend_holds: int = 0


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
    # Descriptor-derived Buffer references are separate from recorded Set refs.
    descriptor_sets: list[DescriptorSetLifetime] = field(default_factory=list)
    indirect_buffer_refs: set[str] = field(default_factory=set)
    # Backend work can outlive logical XID invalidation and terminal callbacks.
    # Holds belong to the current recording epoch; reset/abort move outstanding
    # holds together with that epoch's references into retired_recordings.
    backend_holds: int = 0
    recording_epoch: int = 0
    retired_recordings: list[RetiredCommandBufferRecording] = field(default_factory=list)


def _retire_command_buffer_refs_if_quiescent(state: CommandBufferModel) -> None:
    if not state.buffer_live and state.backend_holds == 0:
        state.entries.clear()
        state.descriptor_sets.clear()
        state.indirect_buffer_refs.clear()
    state.retired_recordings[:] = [
        recording for recording in state.retired_recordings
        if recording.backend_holds > 0
    ]


def _discard_command_buffer_recording(state: CommandBufferModel) -> None:
    """Discard current recording without releasing refs still held by backend."""
    if state.backend_holds > 0:
        state.retired_recordings.append(RetiredCommandBufferRecording(
            epoch=state.recording_epoch,
            entries=list(state.entries),
            descriptor_sets=list(state.descriptor_sets),
            indirect_buffer_refs=set(state.indirect_buffer_refs),
            backend_holds=state.backend_holds,
        ))
        state.backend_holds = 0
    state.recording_epoch += 1
    state.entries.clear()
    state.descriptor_sets.clear()
    state.indirect_buffer_refs.clear()


def retire_command_buffer_backend_hold(
    state: CommandBufferModel, *, recording_epoch: int | None = None,
) -> str:
    """Drop a hold for its recording epoch; omitted epoch uses legacy FIFO order."""
    if recording_epoch is not None:
        for recording in state.retired_recordings:
            if recording.epoch == recording_epoch and recording.backend_holds > 0:
                recording.backend_holds -= 1
                _retire_command_buffer_refs_if_quiescent(state)
                return "SUCCESS"
        if recording_epoch == state.recording_epoch and state.backend_holds > 0:
            state.backend_holds -= 1
            _retire_command_buffer_refs_if_quiescent(state)
            return "SUCCESS"
        return "INVALID_SYNCHRONIZATION_STATE"
    for recording in state.retired_recordings:
        if recording.backend_holds > 0:
            recording.backend_holds -= 1
            _retire_command_buffer_refs_if_quiescent(state)
            return "SUCCESS"
    if state.backend_holds <= 0:
        return "INVALID_SYNCHRONIZATION_STATE"
    state.backend_holds -= 1
    _retire_command_buffer_refs_if_quiescent(state)
    return "SUCCESS"


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
        _discard_command_buffer_recording(state)
        state.lifecycle = CommandBufferLifecycle.INITIAL
        return "SUCCESS"
    if state.device_lost:
        return "DEVICE_LOST"
    if request.operation in {"CREATE", "CREATE_FINAL"}:
        if state.lifecycle is not CommandBufferLifecycle.INITIAL:
            return "INVALID_SYNCHRONIZATION_STATE"
        # INITIAL is a fresh recording epoch. Never inherit references from
        # a prior recording even if a caller constructed an inconsistent model.
        state.entries = list(request.entries)
        state.descriptor_sets.clear()
        state.indirect_buffer_refs.clear()
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


def reset_command_buffer(
    state: CommandBufferModel, *, device_xid_valid: bool = True,
    device_available: bool = True, reset_flag: bool = True,
) -> str:
    """Model ResetCommandBuffer with spec-ordered checks and atomic reset."""
    if not device_xid_valid or not state.buffer_live:
        return "BadValue"
    if (not state.correct_type_and_ownership
            or not state.pool_type_and_ownership_valid
            or not state.pool_matches_buffer):
        return "BadMatch"
    if not device_available:
        return "DEVICE_UNAVAILABLE"
    if state.device_lost:
        return "DEVICE_LOST"
    if not state.pool_live or not state.pool_xid_valid:
        return "BadValue"
    if not reset_flag or state.lifecycle is CommandBufferLifecycle.PENDING:
        return "INVALID_SYNCHRONIZATION_STATE"
    # Commit only after every validation phase: entries/references are discarded
    # together with the lifecycle transition.
    _discard_command_buffer_recording(state)
    state.lifecycle = CommandBufferLifecycle.INITIAL
    return "SUCCESS"


def destroy_command_pool(command_buffers: list[CommandBufferModel]) -> str:
    """Atomically invalidate a pool and its children unless one is pending."""
    if any(buffer.lifecycle is CommandBufferLifecycle.PENDING
           for buffer in command_buffers if buffer.buffer_live):
        return "INVALID_SYNCHRONIZATION_STATE"
    for buffer in command_buffers:
        if buffer.buffer_live:
            buffer.buffer_live = False
            buffer.pool_live = False
            _retire_command_buffer_refs_if_quiescent(buffer)
    return "SUCCESS"


@dataclass
class ResourceDestroyModel:
    """Minimal DestroyResource lifetime oracle for command-buffer references."""
    resource_live: bool = True
    xid_valid: bool = True
    supported_type: bool = True
    correct_type_and_ownership: bool = True
    pending_use: bool = False
    recording_refs: list[CommandBufferModel] = field(default_factory=list)
    executable_refs: list[CommandBufferModel] = field(default_factory=list)


def destroy_resource(state: ResourceDestroyModel) -> str:
    """Apply the resource-destruction checks before any public-state mutation."""
    if not state.xid_valid or not state.resource_live:
        return "BadValue"
    if not state.supported_type or not state.correct_type_and_ownership:
        return "BadMatch"
    if state.pending_use:
        return "INVALID_SYNCHRONIZATION_STATE"
    if any(cb.lifecycle is CommandBufferLifecycle.RECORDING and cb.buffer_live
           for cb in state.recording_refs):
        return "INVALID_SYNCHRONIZATION_STATE"
    # Commit atomically: executable references become invalid only if Destroy succeeds.
    for cb in state.executable_refs:
        if cb.buffer_live and cb.lifecycle is CommandBufferLifecycle.EXECUTABLE:
            cb.lifecycle = CommandBufferLifecycle.INVALID
    state.resource_live = False
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
    # Logical terminal outcomes are separate from pending callback-cleanup records.
    terminal_submission_status: dict[int, str] = field(default_factory=dict)
    # Command buffers and an optional fence are owned by individual pending submissions.
    pending_command_buffers: list[tuple[int, int]] = field(default_factory=list)
    pending_fence_submissions: list[int] = field(default_factory=list)
    fence_status: str = "UNSIGNALED"
    framing_valid: bool = True
    scalar_valid: bool = True
    xids_valid: bool = True
    types_and_ownership_valid: bool = True
    dependencies_valid: bool = True
    # Optional lifetime registry enables accepted work to own explicit internal refs.
    buffer_registry: list[BufferMemoryLifetime] = field(default_factory=list)
    accepted_descriptor_set_refs: dict[int, list[DescriptorSetLifetime]] = field(default_factory=dict)
    accepted_buffer_refs: dict[int, list[BufferMemoryLifetime]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _register_semaphore_owner(self)


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
            or len(set(request.command_buffer_indices)) != len(request.command_buffer_indices)
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
    if state.device_lost or any(shared.device_lost for shared in state.shared_semaphores):
        _propagate_device_loss(state)
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
            if ((shared is not None and (
                    shared.wait_reservation is not None or shared.signal_consumed
                )) or any(
                pending_index == index for _token, pending_index in state.pending_binary_waits
            )):
                # A cross-API waiter already consumed this signal even if the
                # originating Submit callback has not yet retired its token.
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
            if value <= counter:
                return "BadValue"
            if any(value <= pending for pending in pending_values):
                # The reservation list is authoritative: the summary slot can
                # change when callbacks for concurrent submissions arrive out
                # of order, but every non-terminal reservation remains binding.
                return "INVALID_SYNCHRONIZATION_STATE"
    # Snapshot indirect resources before acceptance. Every accepted token owns
    # an independent reference set, even when submissions share resources.
    selected_cbs = [state.command_buffers[i] for i in request.command_buffer_indices]
    accepted_sets: list[DescriptorSetLifetime] = []
    for cb in selected_cbs:
        for descriptor_set in cb.descriptor_sets:
            if descriptor_set not in accepted_sets:
                accepted_sets.append(descriptor_set)
    if any(not descriptor_set.live for descriptor_set in accepted_sets):
        return "INVALID_SYNCHRONIZATION_STATE"
    referenced_ids: set[str] = set()
    for descriptor_set in accepted_sets:
        referenced_ids.update(descriptor_set.slots.values())
    for cb in selected_cbs:
        referenced_ids.update(cb.indirect_buffer_refs)
    registry = {buffer.identity: buffer for buffer in state.buffer_registry}
    if state.buffer_registry and any(identity not in registry for identity in referenced_ids):
        return "INVALID_SYNCHRONIZATION_STATE"
    accepted_buffers = [registry[identity] for identity in sorted(referenced_ids)
                        if identity in registry]
    # A generic dependency failure is the fallback only after all concrete
    # wait and signal entry errors have been ruled out.
    if not state.dependencies_valid:
        return "DEPENDENCY_FAILED"
    # Acceptance commit point.
    state.accepted_tokens.add(request.token)
    if accepted_sets:
        state.accepted_descriptor_set_refs[request.token] = list(accepted_sets)
        for descriptor_set in accepted_sets:
            descriptor_set.pending_submission_refs += 1
    if accepted_buffers:
        state.accepted_buffer_refs[request.token] = list(accepted_buffers)
        for buffer in accepted_buffers:
            buffer.accepted_uses += 1
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
                state.shared_semaphores[i].wait_reservation_owner = state
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
                state.shared_semaphores[index].signal_reservation_owner = state
                state.shared_semaphores[index].signal_consumed = False
                state.shared_semaphores[index].signal_consumption_confirmed = False
                state.shared_semaphores[index].signal_from_submit = True
    if request.attach_fence:
        state.fence_attached = True
        state.fence_state_valid = False
        state.fence_status = "PENDING"
        state.pending_fence_submissions.append(request.token)
    state.pending_submissions.append(request.token)
    return "SUCCESS"


def signal_timeline_host(state: SubmissionModel, semaphore_index: int, value: int) -> str:
    """Model SignalSemaphore's counter/reservation validation and atomic update."""
    if state.device_lost or any(shared.device_lost for shared in state.shared_semaphores):
        # An observing API call must fan loss out to the rest of the connected
        # semaphore graph, not just update this model's device flag.
        _propagate_device_loss(state)
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
        return "BadValue"
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
    if any(shared.device_lost for shared in state.shared_semaphores):
        state.device_lost = True
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
                and shared.signal_reservation_owner is state and shared.signal_consumed)
        )
        state.consumed_pending_binary_signals.discard(reservation)
        previous = state.binary_signal_previous_states.pop(reservation, BinarySignalState.UNSIGNALED)
        current = state.binary_signal_states[index]
        # QueuePresent owns the canonical cross-API payload outcome. If its
        # callback made the semaphore untrusted, a later Submit callback must
        # not overwrite that knowledge with a local stale snapshot.
        if shared is not None and (
            shared.signal_state is BinarySignalState.UNTRUSTED or shared.device_lost
        ):
            # Device loss quarantines the canonical payload regardless of a
            # stale local "consumed" bit. Preserve a canonical known-empty
            # state when one was established before loss; otherwise never
            # let this callback make its local mirror more trusted.
            current = shared.signal_state
            state.binary_signal_states[index] = current
            if index < len(state.wait_states):
                state.wait_states[index] = (
                    WaitState.UNTRUSTED
                    if current is BinarySignalState.UNTRUSTED
                    else WaitState.READY
                )
        if current is BinarySignalState.UNTRUSTED:
            # An unknown cross-API payload outcome is stronger than a stale
            # local "unchanged" report from the Submit callback.
            state.binary_signal_states[index] = BinarySignalState.UNTRUSTED
            if index < len(state.wait_states):
                state.wait_states[index] = WaitState.UNTRUSTED
        elif shared is not None and shared.device_lost:
            # The canonical state is authoritative after loss, including
            # confirmed-empty payloads. Do not reinterpret a stale per-token
            # consumed flag as a fresh state transition.
            pass
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
            if (shared.signal_reservation == ("submit", token)
                    and shared.signal_reservation_owner is state):
                shared.signal_reservation = None
                shared.signal_reservation_owner = None
                shared.signal_consumed = False
                # Provenance is retained only when the Submit actually
                # published a signal. A failed callback with a confirmed
                # unchanged payload must not let a later wait claim that a
                # signal from this failed submission was consumed.
                if not effective_success and not consumed:
                    shared.signal_from_submit = False
                    shared.signal_consumption_confirmed = False
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
                if (shared is not None and shared.wait_reservation == ("submit", token)
                        and shared.wait_reservation_owner is state):
                    shared.wait_reservation = None
                    shared.wait_reservation_owner = None
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
                owns_wait_reservation = (
                    shared is not None
                    and shared.wait_reservation == ("submit", token)
                    and shared.wait_reservation_owner is state
                )
                if owns_wait_reservation and shared.signal_reservation is not None:
                    shared.signal_consumed = True
                    if shared.signal_reservation[0] == "submit":
                        shared.signal_consumption_confirmed = True
                        shared.signal_from_submit = False
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
            # A terminal callback may update the canonical shared semaphore
            # only while it still owns this exact wait reservation. If another
            # lifecycle path has retired the old reservation and a newer
            # operation now owns the semaphore, the stale local mirror must
            # not overwrite that newer operation's payload state.
            if (shared.wait_reservation == ("submit", token)
                    and shared.wait_reservation_owner is state):
                shared.wait_reservation = None
                shared.wait_reservation_owner = None
                shared.signal_state = state.binary_signal_states[index]
    state.pending_timeline_waits = [
        wait for wait in state.pending_timeline_waits if wait[0] != token
    ]
    # Each terminal callback drops only the refs owned by its own token.
    for descriptor_set in state.accepted_descriptor_set_refs.pop(token, []):
        descriptor_set.pending_submission_refs -= 1
    for buffer in state.accepted_buffer_refs.pop(token, []):
        buffer.accepted_uses -= 1
        _finish_buffer_release(buffer)
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


def mark_device_lost(state: SubmissionModel) -> str:
    """Atomically terminalize work and propagate loss across shared sets."""
    _propagate_device_loss(state)
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


@dataclass
class DescriptorSetLifetime:
    """Public lifetime and references for one descriptor set."""
    live: bool = True
    pending_use: bool = False
    recording_refs: int = 0
    executable_refs: list[CommandBufferModel] = field(default_factory=list)
    # Slot -> internal Buffer identity; XIDs are deliberately not modeled as identity.
    slots: dict[int, str] = field(default_factory=dict)
    pending_buffer_refs: set[str] = field(default_factory=set)
    pending_submission_refs: int = 0


@dataclass
class DescriptorPoolLifetime:
    """Pool and child-set state for atomic DestroyDescriptorPool."""
    live: bool = True
    xid_valid: bool = True
    correct_type_and_ownership: bool = True
    sets: list[DescriptorSetLifetime] = field(default_factory=list)


def _release_descriptor_slots(
    descriptor_sets: list[DescriptorSetLifetime],
    buffers: list[BufferMemoryLifetime] | None,
) -> str:
    if buffers is None:
        return "SUCCESS"
    by_id = {buffer.identity: buffer for buffer in buffers}
    counts: dict[str, int] = {}
    for descriptor_set in descriptor_sets:
        if not descriptor_set.live:
            continue
        for identity in descriptor_set.slots.values():
            counts[identity] = counts.get(identity, 0) + 1
    if any(identity in by_id and by_id[identity].descriptor_slot_refs < count
           for identity, count in counts.items()):
        return "INVALID_SYNCHRONIZATION_STATE"
    for identity, count in counts.items():
        buffer = by_id.get(identity)
        if buffer is not None:
            buffer.descriptor_slot_refs -= count
            _finish_buffer_release(buffer)
    return "SUCCESS"


def free_descriptor_sets(
    sets: list[DescriptorSetLifetime],
    buffers: list[BufferMemoryLifetime] | None = None,
) -> str:
    """Validate all selected sets first, then invalidate and release their slots."""
    # Duplicate entries are invalid at the request boundary. Counting the
    # same set twice would otherwise retire its descriptor-slot edges twice
    # while leaving the set's single live slot graph intact until commit.
    if len({id(descriptor_set) for descriptor_set in sets}) != len(sets):
        return "BadValue"
    if any(not descriptor_set.live for descriptor_set in sets):
        return "BadValue"
    if any(descriptor_set.pending_use or descriptor_set.pending_submission_refs or descriptor_set.recording_refs
           for descriptor_set in sets):
        return "INVALID_SYNCHRONIZATION_STATE"
    if _release_descriptor_slots(sets, buffers) != "SUCCESS":
        return "INVALID_SYNCHRONIZATION_STATE"
    for descriptor_set in sets:
        for cb in descriptor_set.executable_refs:
            if cb.buffer_live and cb.lifecycle is CommandBufferLifecycle.EXECUTABLE:
                cb.lifecycle = CommandBufferLifecycle.INVALID
        descriptor_set.live = False
        descriptor_set.slots.clear()
    return "SUCCESS"


def destroy_descriptor_pool(
    pool: DescriptorPoolLifetime,
    buffers: list[BufferMemoryLifetime] | None = None,
) -> str:
    """Apply pool-wide preflight checks, then invalidate pool, sets and refs."""
    if not pool.xid_valid or not pool.live:
        return "BadValue"
    if not pool.correct_type_and_ownership:
        return "BadMatch"
    live_sets = [descriptor_set for descriptor_set in pool.sets if descriptor_set.live]
    if any(descriptor_set.pending_use or descriptor_set.pending_submission_refs or descriptor_set.recording_refs
           for descriptor_set in live_sets):
        return "INVALID_SYNCHRONIZATION_STATE"
    if _release_descriptor_slots(live_sets, buffers) != "SUCCESS":
        return "INVALID_SYNCHRONIZATION_STATE"
    for descriptor_set in live_sets:
        for cb in descriptor_set.executable_refs:
            if cb.buffer_live and cb.lifecycle is CommandBufferLifecycle.EXECUTABLE:
                cb.lifecycle = CommandBufferLifecycle.INVALID
        descriptor_set.live = False
        descriptor_set.slots.clear()
    pool.live = False
    pool.xid_valid = False
    return "SUCCESS"



@dataclass(frozen=True)
class DescriptorWrite:
    set_index: int
    slot: int
    buffer_identity: str | None


def update_descriptor_sets(
    sets: list[DescriptorSetLifetime],
    writes: tuple[DescriptorWrite, ...],
    command_buffers: list[CommandBufferModel],
    *,
    writes_valid: bool = True,
    buffers: list[BufferMemoryLifetime] | None = None,
) -> str:
    """Atomically update slots, tracked slot refs, and nonpending CB refs.

    When a Buffer registry is supplied, new writes must resolve to live public
    Buffer XIDs. Existing stale slots may remain after Buffer destruction until
    overwritten or their DescriptorSet is freed.
    """
    if not writes_valid:
        return "BadValue"
    if len({(w.set_index, w.slot) for w in writes}) != len(writes):
        return "BadValue"
    if any(w.set_index < 0 or w.set_index >= len(sets)
           or not sets[w.set_index].live or w.slot < 0 for w in writes):
        return "BadValue"
    buffer_by_id = {buffer.identity: buffer for buffer in buffers or []}
    if buffers is not None and any(
        w.buffer_identity is not None and
        (w.buffer_identity not in buffer_by_id
         or not buffer_by_id[w.buffer_identity].xid_valid
         or not buffer_by_id[w.buffer_identity].live)
        for w in writes
    ):
        return "BadValue"
    # The spec places the pending-use check after XID/ownership/device and
    # descriptor compatibility validation. The model's writes_valid fixture
    # represents those request-specific checks; only then may pending sets
    # reject the whole batch before candidate slots or refs are changed.
    affected_set_indices = {w.set_index for w in writes}
    if any(
        sets[index].pending_use or sets[index].pending_submission_refs
        for index in affected_set_indices
    ):
        return "INVALID_SYNCHRONIZATION_STATE"
    candidate = [dict(descriptor_set.slots) for descriptor_set in sets]
    for w in writes:
        if w.buffer_identity is None:
            candidate[w.set_index].pop(w.slot, None)
        else:
            candidate[w.set_index][w.slot] = w.buffer_identity

    # Compute refcount deltas before committing, including repeated slots that
    # point to the same Buffer identity.
    deltas: dict[str, int] = {}
    for old, new in zip((s.slots for s in sets), candidate):
        for identity in old.values():
            deltas[identity] = deltas.get(identity, 0) - 1
        for identity in new.values():
            deltas[identity] = deltas.get(identity, 0) + 1
    if buffers is not None and any(
        identity in buffer_by_id
        and buffer_by_id[identity].descriptor_slot_refs + delta < 0
        for identity, delta in deltas.items()
    ):
        return "INVALID_SYNCHRONIZATION_STATE"

    for descriptor_set, slots in zip(sets, candidate):
        descriptor_set.slots = slots
    if buffers is not None:
        for identity, delta in deltas.items():
            if identity in buffer_by_id:
                buffer_by_id[identity].descriptor_slot_refs += delta
                _finish_buffer_release(buffer_by_id[identity])
    for cb in command_buffers:
        if cb.lifecycle is CommandBufferLifecycle.PENDING:
            continue
        refs: set[str] = set()
        for descriptor_set in cb.descriptor_sets:
            if descriptor_set.live:
                refs.update(descriptor_set.slots.values())
        cb.indirect_buffer_refs = refs
    return "SUCCESS"


def descriptor_contents_submit_valid(
    descriptor_sets: list[DescriptorSetLifetime],
    buffers: list[BufferMemoryLifetime],
) -> str:
    """Reject submission if any live set contains a stale Buffer identity."""
    buffer_by_id = {buffer.identity: buffer for buffer in buffers}
    for descriptor_set in descriptor_sets:
        if not descriptor_set.live:
            return "BadValue"
        for identity in descriptor_set.slots.values():
            buffer = buffer_by_id.get(identity)
            if buffer is None or not buffer.xid_valid or not buffer.live:
                return "INVALID_SYNCHRONIZATION_STATE"
    return "SUCCESS"



@dataclass
class BufferMemoryLifetime:
    """Public Buffer XID and deferred internal lifetime, keyed by identity."""
    identity: str = "buffer-A"
    memory_identity: str = "memory-A"
    xid_valid: bool = True
    live: bool = True
    internal_state: str = "ACTIVE"  # ACTIVE, DESTROY_PENDING, RELEASED
    recording_refs: list[CommandBufferModel] = field(default_factory=list)
    executable_refs: list[CommandBufferModel] = field(default_factory=list)
    accepted_uses: int = 0
    descriptor_slot_refs: int = 0
    backend_accesses: int = 0


@dataclass
class MemoryAllocationLifetime:
    """Memory XID remains live until FreeMemory passes all lifetime checks."""
    identity: str = "memory-A"
    xid_valid: bool = True
    live: bool = True
    accepted_uses: int = 0


def _finish_buffer_release(buffer: BufferMemoryLifetime) -> None:
    if (not buffer.xid_valid and buffer.accepted_uses == 0
            and buffer.descriptor_slot_refs == 0 and buffer.backend_accesses == 0):
        buffer.internal_state = "RELEASED"
    elif not buffer.xid_valid:
        buffer.internal_state = "DESTROY_PENDING"


def destroy_buffer_lifetime(buffer: BufferMemoryLifetime) -> str:
    """DestroyResource(Buffer): preflight blockers, then invalidate XID atomically."""
    if not buffer.xid_valid or not buffer.live:
        return "BadValue"
    if any(cb.buffer_live and cb.lifecycle is CommandBufferLifecycle.RECORDING
           for cb in buffer.recording_refs):
        return "INVALID_SYNCHRONIZATION_STATE"
    if buffer.accepted_uses:
        return "INVALID_SYNCHRONIZATION_STATE"
    for cb in buffer.executable_refs:
        if cb.buffer_live and cb.lifecycle is CommandBufferLifecycle.EXECUTABLE:
            cb.lifecycle = CommandBufferLifecycle.INVALID
    buffer.xid_valid = False
    buffer.live = False
    _finish_buffer_release(buffer)
    return "SUCCESS"


def free_memory_lifetime(
    memory: MemoryAllocationLifetime,
    buffers: list[BufferMemoryLifetime],
) -> str:
    """FreeMemory rejects any still-internally-bound Buffer before pending work."""
    if not memory.xid_valid or not memory.live:
        return "BadValue"
    if any(buffer.memory_identity == memory.identity
           and buffer.internal_state != "RELEASED" for buffer in buffers):
        return "BadMatch"
    if memory.accepted_uses or any(
        buffer.memory_identity == memory.identity and
        (buffer.accepted_uses or buffer.backend_accesses)
        for buffer in buffers
    ):
        return "INVALID_SYNCHRONIZATION_STATE"
    memory.xid_valid = False
    memory.live = False
    return "SUCCESS"


def drop_buffer_internal_ref(
    buffer: BufferMemoryLifetime, *, descriptor_slots: int = 0,
    accepted_uses: int = 0, backend_accesses: int = 0,
) -> str:
    """Drop known internal references and release only after backend quiescence."""
    if (descriptor_slots < 0 or accepted_uses < 0 or backend_accesses < 0
            or descriptor_slots > buffer.descriptor_slot_refs
            or accepted_uses > buffer.accepted_uses
            or backend_accesses > buffer.backend_accesses):
        return "BadValue"
    buffer.descriptor_slot_refs -= descriptor_slots
    buffer.accepted_uses -= accepted_uses
    buffer.backend_accesses -= backend_accesses
    _finish_buffer_release(buffer)
    return "SUCCESS"


@dataclass
class AsyncResourceIdentity:
    """Immutable identity captured by backend work; XID is only a public name."""
    identity: str
    xid: int
    device_identity: str
    live: bool = True
    backend_refs: int = 1
    callback_count: int = 0
    completed_callback_tokens: set[str] = field(default_factory=set)


@dataclass
class AsyncDeviceIdentity:
    identity: str
    xid: int
    live: bool = True


@dataclass
class AsyncCallbackRegistry:
    """Oracle for delayed callbacks: never resolve callback targets by reused XID."""
    resources_by_xid: dict[int, AsyncResourceIdentity] = field(default_factory=dict)
    devices_by_xid: dict[int, AsyncDeviceIdentity] = field(default_factory=dict)
    # These are opaque connection-instance handles, not client names. A
    # reconnect must allocate a fresh handle even when the peer/process label
    # is unchanged; delayed callbacks retain the original handle.
    connections_live: set[object] = field(default_factory=set)
    emitted_events: list[tuple[str, int, int]] = field(default_factory=list)

    def disconnect(self, connection_identity: object) -> None:
        self.connections_live.discard(connection_identity)

    def register_device(self, device: AsyncDeviceIdentity) -> None:
        self.devices_by_xid[device.xid] = device

    def register_resource(self, resource: AsyncResourceIdentity) -> None:
        self.resources_by_xid[resource.xid] = resource

    def destroy_resource(self, resource: AsyncResourceIdentity) -> str:
        if self.resources_by_xid.get(resource.xid) is not resource or not resource.live:
            return "BadValue"
        del self.resources_by_xid[resource.xid]
        resource.live = False
        return "SUCCESS"

    def destroy_device(self, device: AsyncDeviceIdentity) -> str:
        if self.devices_by_xid.get(device.xid) is not device or not device.live:
            return "BadValue"
        del self.devices_by_xid[device.xid]
        device.live = False
        for xid, resource in list(self.resources_by_xid.items()):
            if resource.device_identity == device.identity:
                del self.resources_by_xid[xid]
                resource.live = False
        return "SUCCESS"

    def complete_backend_callback(
        self, resource: AsyncResourceIdentity, device: AsyncDeviceIdentity,
        connection_identity: object, *, token: str,
    ) -> str:
        """Finish captured work; event targets come from captured identities only."""
        # One operation token owns one backend reference. A duplicate
        # completion must not consume a different operation's outstanding ref.
        if (resource.backend_refs <= 0 or token in resource.completed_callback_tokens):
            return "BadValue"
        resource.completed_callback_tokens.add(token)
        resource.backend_refs -= 1
        resource.callback_count += 1
        # A stale resource/device or dead connection suppresses delivery. In
        # particular, never look up resource.xid in resources_by_xid here.
        if (resource.device_identity == device.identity
                and device.live and self.devices_by_xid.get(device.xid) is device
                and connection_identity in self.connections_live):
            resource_xid = (
                resource.xid if resource.live
                and self.resources_by_xid.get(resource.xid) is resource else 0
            )
            self.emitted_events.append((token, device.xid, resource_xid))
        return "SUCCESS"


@dataclass(frozen=True, eq=False)
class ConnectionInstance:
    """Opaque identity for one concrete X11 connection lifetime.

    Equality and hashing intentionally use object identity, never the reusable
    peer/client label. Construct a fresh instance for every accepted connection.
    """
    client_label: str

@dataclass
class AsyncSubmissionIdentity:
    """Submission callback target captured at QueueSubmit acceptance."""
    token: int
    connection_identity: ConnectionInstance
    device_identity: str
    device_xid: int
    queue_key: tuple[int, int]
    terminal: str | None = None
    # Capture the actual device generation; identity strings and XIDs may be reused.
    captured_device: AsyncDeviceIdentity | None = None


@dataclass(frozen=True)
class AsyncWaitIdentity:
    """One open server-side host wait, independent of accepted GPU work."""
    connection_identity: ConnectionInstance
    token: int
    kind: str
    resource_identities: tuple[str, ...]


@dataclass
class AsyncSubmissionEventRegistry:
    """Callback oracle keyed by opaque per-connection instance handles."""
    live_connections: set[ConnectionInstance] = field(default_factory=set)
    retired_connections: set[ConnectionInstance] = field(default_factory=set)

    def connect(self, client_label: str) -> ConnectionInstance:
        """Create a fresh identity even when the client label was seen before."""
        connection = ConnectionInstance(client_label)
        self.live_connections.add(connection)
        return connection

    def _is_connection_handle(self, connection: object) -> bool:
        return isinstance(connection, ConnectionInstance)

    def _connection_is_live(self, connection: object) -> bool:
        # Legacy string fixtures remain accepted for older model tests; new
        # reconnect-sensitive tests and all new callers must use handles.
        if isinstance(connection, str):
            return connection in self.live_connections
        return (self._is_connection_handle(connection)
                and connection not in self.retired_connections
                and connection in self.live_connections)
    live_devices: dict[str, AsyncDeviceIdentity] = field(default_factory=dict)
    queue_masks: dict[tuple[str, tuple[int, int]], int] = field(default_factory=dict)
    submissions: dict[tuple[str, int], AsyncSubmissionIdentity] = field(default_factory=dict)
    # Submission IDs are unique for the lifetime of a connection, not merely
    # while an operation is pending. Otherwise a duplicate late backend callback
    # carrying an old (connection, token) pair could resolve a newer submission
    # after the first operation has been retired (an ABA reuse).
    used_submission_keys: set[tuple[str, int]] = field(default_factory=set)
    # Disconnect detaches client/event links immediately, but accepted backend
    # work remains indexed here until its real terminal callback arrives.
    detached_submissions: dict[tuple[str, int], AsyncSubmissionIdentity] = field(default_factory=dict)
    # Open host waits hold wait-only references and are canceled on disconnect;
    # they are not backend submissions and must not survive the connection.
    wait_registrations: dict[tuple[str, int], AsyncWaitIdentity] = field(default_factory=dict)
    emitted_events: list[tuple[str, str, int, int]] = field(default_factory=list)

    def register_device(self, connection: ConnectionInstance, device: AsyncDeviceIdentity) -> None:
        if not self._connection_is_live(connection):
            raise ValueError("callback registry requires a live connection-instance handle")
        self.live_devices[device.identity] = device
        self.queue_masks[(connection, (device.xid, 0))] = 0

    def accept_submission(self, submission: AsyncSubmissionIdentity) -> str:
        key = (submission.connection_identity, submission.token)
        # A disconnected submission may still be owned by a backend callback.
        # Its key remains reserved until that callback retires the detached link;
        # reusing it would make terminal_callback ambiguous and could leak the
        # old detached submission indefinitely.
        if (submission.token == 0 or key in self.used_submission_keys
                or key in self.submissions or key in self.detached_submissions):
            return "BadValue"
        if not self._connection_is_live(submission.connection_identity):
            return "BadValue"
        device = self.live_devices.get(submission.device_identity)
        if device is None or not device.live or device.xid != submission.device_xid:
            return "BadValue"
        submission.captured_device = device
        self.submissions[key] = submission
        self.used_submission_keys.add(key)
        return "SUCCESS"

    def select_queue_events(
        self, connection: ConnectionInstance, device_identity: str, queue: tuple[int, int], mask: int,
    ) -> str:
        device = self.live_devices.get(device_identity)
        if not self._connection_is_live(connection) or device is None or not device.live:
            return "BadValue"
        self.queue_masks[(connection, (device.xid, queue[0] * 65536 + queue[1]))] = mask
        return "SUCCESS"

    def destroy_device(self, device_identity: str) -> str:
        device = self.live_devices.get(device_identity)
        if device is None or not device.live:
            return "BadValue"
        device.live = False
        del self.live_devices[device_identity]
        for key in [key for key in self.queue_masks if key[1][0] == device.xid]:
            del self.queue_masks[key]
        return "SUCCESS"

    def register_wait(
        self, connection: ConnectionInstance, token: int, kind: str,
        resource_identities: tuple[str, ...],
    ) -> str:
        key = (connection, token)
        if (not self._connection_is_live(connection) or token == 0
                or kind not in {"WaitSemaphores", "WaitForFence"}
                or not resource_identities or key in self.wait_registrations):
            return "BadValue"
        self.wait_registrations[key] = AsyncWaitIdentity(
            connection, token, kind, resource_identities
        )
        return "SUCCESS"

    def finish_wait(self, registration: AsyncWaitIdentity) -> str:
        """Retire only the exact wait captured by its callback.

        Connection/token pairs can be reused after disconnect. Resolving a
        delayed callback by that pair alone could otherwise cancel a newer
        wait registered under the same pair.
        """
        key = (registration.connection_identity, registration.token)
        if self.wait_registrations.get(key) is not registration:
            return "BadValue"
        del self.wait_registrations[key]
        return "SUCCESS"

    def disconnect(self, connection: ConnectionInstance) -> None:
        self.live_connections.discard(connection)
        if self._is_connection_handle(connection):
            self.retired_connections.add(connection)
        for key in [key for key in self.queue_masks if key[0] == connection]:
            del self.queue_masks[key]
        # Open host waits are connection-owned, not backend work. Cancel them
        # without a reply and release their wait-only resource references.
        for key in [key for key in self.wait_registrations if key[0] == connection]:
            del self.wait_registrations[key]
        # Remove client-facing callback links now. The detached table models
        # the independent backend completion ownership for accepted work.
        for key, submission in list(self.submissions.items()):
            if key[0] == connection:
                self.detached_submissions[key] = submission
                del self.submissions[key]

    def terminal_callback(self, connection: ConnectionInstance, token: int, result: str) -> str:
        if not self._connection_is_live(connection) and not isinstance(connection, str):
            return "BadValue"
        key = (connection, token)
        submission = self.submissions.get(key)
        detached = False
        if submission is None:
            submission = self.detached_submissions.get(key)
            detached = submission is not None
        if submission is None or submission.terminal is not None:
            return "BadValue"
        if result not in ("COMPLETE", "FAILED"):
            return "BadValue"
        # Terminal state is committed exactly once regardless of event delivery.
        submission.terminal = result
        device = self.live_devices.get(submission.device_identity)
        if (detached or connection not in self.live_connections or device is None
                or not device.live or device.xid != submission.device_xid
                or submission.captured_device is not device):
            self.submissions.pop(key, None)
            self.detached_submissions.pop(key, None)
            return "SUCCESS"
        queue_code = submission.queue_key[0] * 65536 + submission.queue_key[1]
        mask = self.queue_masks.get((connection, (submission.device_xid, queue_code)), 0)
        bit = 1 if result == "COMPLETE" else 2
        if mask & bit:
            self.emitted_events.append((result, connection, submission.device_xid, token))
        # A terminal callback has consumed this connection/token link. Keep the
        # captured object alive only through any external backend ownership;
        # the registry must not retain completed submissions indefinitely.
        self.submissions.pop(key, None)
        return "SUCCESS"

    def async_error(
        self, connection: ConnectionInstance, captured_device: AsyncDeviceIdentity, token: int,
    ) -> str:
        """Deliver only if the callback's captured device generation is still live."""
        if not self._connection_is_live(connection):
            return "SUCCESS"
        device = self.live_devices.get(captured_device.identity)
        if (self._connection_is_live(connection) and captured_device.live
                and device is captured_device):
            self.emitted_events.append(("ASYNC_ERROR", connection, captured_device.xid, token))
        return "SUCCESS"

@dataclass
class AsyncFenceIdentity:
    """Fence generation captured by one accepted backend operation."""
    identity: str
    xid: int
    device_identity: str
    status: str = "UNSIGNALED"
    live: bool = True
    generation: int = 0
    pending_token: int | None = None
    completed_tokens: set[int] = field(default_factory=set)
    device_generation: int = 0


@dataclass
class AsyncFenceCallbackModel:
    """Oracle ensuring delayed fence callbacks cannot signal across device generations."""
    fences: dict[int, AsyncFenceIdentity] = field(default_factory=dict)
    devices: dict[str, bool] = field(default_factory=dict)
    device_generations: dict[str, int] = field(default_factory=dict)

    def register_device(self, identity: str) -> None:
        self.device_generations[identity] = self.device_generations.get(identity, 0) + 1
        self.devices[identity] = True

    def mark_device_lost(self, identity: str) -> str:
        if not self.devices.get(identity, False):
            return "DEVICE_LOST"
        self.devices[identity] = False
        return "SUCCESS"

    def _device_is_current(self, fence: AsyncFenceIdentity) -> bool:
        return (
            self.devices.get(fence.device_identity, False)
            and self.device_generations.get(fence.device_identity, 0) == fence.device_generation
        )

    def register_fence(self, fence: AsyncFenceIdentity) -> str:
        if fence.xid in self.fences and self.fences[fence.xid].live:
            return "BadIDChoice"
        if not self.devices.get(fence.device_identity, False):
            return "BadValue"
        fence.device_generation = self.device_generations[fence.device_identity]
        self.fences[fence.xid] = fence
        return "SUCCESS"

    def accept(self, fence: AsyncFenceIdentity, token: int) -> str:
        if not self._device_is_current(fence):
            return "DEVICE_LOST"
        if (not fence.live or self.fences.get(fence.xid) is not fence
                or fence.status != "UNSIGNALED" or fence.pending_token is not None
                or token == 0 or token in fence.completed_tokens):
            return "INVALID_SYNCHRONIZATION_STATE"
        fence.pending_token = token
        fence.status = "PENDING"
        return "SUCCESS"

    def destroy(self, fence: AsyncFenceIdentity) -> str:
        if not fence.live or self.fences.get(fence.xid) is not fence:
            return "BadValue"
        if fence.pending_token is not None:
            return "INVALID_SYNCHRONIZATION_STATE"
        fence.live = False
        del self.fences[fence.xid]
        return "SUCCESS"

    def reset(self, fence: AsyncFenceIdentity) -> str:
        if not self._device_is_current(fence):
            return "DEVICE_LOST"
        if not fence.live or self.fences.get(fence.xid) is not fence:
            return "BadValue"
        if fence.pending_token is not None or fence.status not in {"SIGNALED", "FAILED"}:
            return "INVALID_SYNCHRONIZATION_STATE"
        fence.generation += 1
        fence.status = "UNSIGNALED"
        return "SUCCESS"

    def callback(self, captured_fence: AsyncFenceIdentity, token: int, success: bool) -> str:
        if token in captured_fence.completed_tokens or captured_fence.pending_token != token:
            return "BadValue"
        captured_fence.completed_tokens.add(token)
        captured_fence.pending_token = None
        # Always terminalize the captured internal fence, even after its
        # public XID was invalidated by DestroyDevice. Public replacement state
        # is never resolved by XID and therefore cannot be changed here.
        captured_fence.status = (
            "SIGNALED" if (
                success and captured_fence.live
                and self.fences.get(captured_fence.xid) is captured_fence
                and self._device_is_current(captured_fence)
            ) else "FAILED"
        )
        return "SUCCESS"
