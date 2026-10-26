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
