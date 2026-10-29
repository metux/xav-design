"""Reference model for Host WaitSemaphores vs GPU timeline signals.

Waits are level-triggered predicates over the canonical timeline counter. They
reserve no signal values. Completion, timeout, device loss and device
destruction are serialized terminal transitions; a satisfied predicate wins
over a timeout observed during the final state check.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Timeline:
    counter: int
    pending_gpu_signals: dict[int, int] = field(default_factory=dict)
    pending_host_waits: dict[int, int] = field(default_factory=dict)
    terminal_waits: dict[int, str] = field(default_factory=dict)
    terminal_gpu_signals: set[int] = field(default_factory=set)
    lifecycle: str = "ACTIVE"

    def begin_host_wait(self, token: int, value: int) -> str:
        if token == 0 or token in self.pending_host_waits or token in self.terminal_waits:
            return "BadValue"
        if self.lifecycle == "DEVICE_LOST":
            return "DEVICE_LOST"
        if self.lifecycle == "DEVICE_DESTROYED":
            return "DEVICE_DESTROYED"
        if value <= self.counter:
            self.terminal_waits[token] = "SUCCESS"
            return "SUCCESS"
        self.pending_host_waits[token] = value
        return "PENDING"

    def signal_host(self, value: int) -> str:
        if self.lifecycle == "DEVICE_LOST":
            return "DEVICE_LOST"
        if self.lifecycle == "DEVICE_DESTROYED":
            return "DEVICE_DESTROYED"
        if value <= self.counter:
            return "BadValue"
        if any(value >= reserved for reserved in self.pending_gpu_signals.values()):
            return "INVALID_SYNCHRONIZATION_STATE"
        self.counter = value
        self._resolve_waits()
        return "SUCCESS"

    def reserve_gpu_signal(self, token: int, value: int) -> str:
        if self.lifecycle == "DEVICE_LOST":
            return "DEVICE_LOST"
        if self.lifecycle == "DEVICE_DESTROYED":
            return "DEVICE_DESTROYED"
        if (token == 0 or token in self.pending_gpu_signals
                or token in self.terminal_gpu_signals):
            return "BadValue"
        if value <= self.counter or any(
            value <= reserved for reserved in self.pending_gpu_signals.values()
        ):
            return "BadValue"
        self.pending_gpu_signals[token] = value
        return "SUCCESS"

    def finish_gpu_signal(self, token: int, *, success: bool) -> str:
        if token not in self.pending_gpu_signals:
            return "BadValue"
        value = self.pending_gpu_signals.pop(token)
        self.terminal_gpu_signals.add(token)
        # A late backend callback after device loss/destruction must not
        # manufacture successful timeline progress or resurrect host waits.
        if self.lifecycle != "ACTIVE":
            return "SUCCESS"
        if success:
            self.counter = max(self.counter, value)
            self._resolve_waits()
        return "SUCCESS"

    def finish_host_wait(self, token: int, status: str) -> str:
        if token not in self.pending_host_waits:
            return "BadValue"
        value = self.pending_host_waits[token]
        # The normative final check gives an already-satisfied predicate
        # precedence over a timeout observed concurrently.
        if self.counter >= value:
            status = "SUCCESS"
        elif status == "SUCCESS":
            return "INVALID_SYNCHRONIZATION_STATE"
        elif status != "TIMEOUT":
            # Device-loss and destruction transitions are serialized through
            # mark_device_lost()/destroy_device(), never injected by a callback.
            return "BadValue"
        del self.pending_host_waits[token]
        self.terminal_waits[token] = status
        return "SUCCESS"

    def mark_device_lost(self) -> str:
        if self.lifecycle != "ACTIVE":
            return "SUCCESS"
        self.lifecycle = "DEVICE_LOST"
        self._terminate_open_waits("DEVICE_LOST")
        self._terminate_gpu_signals()
        return "SUCCESS"

    def destroy_device(self) -> str:
        if self.lifecycle != "ACTIVE":
            return "SUCCESS"
        self.lifecycle = "DEVICE_DESTROYED"
        self._terminate_open_waits("DEVICE_DESTROYED")
        self._terminate_gpu_signals()
        return "SUCCESS"

    def _terminate_open_waits(self, status: str) -> None:
        for token in list(self.pending_host_waits):
            del self.pending_host_waits[token]
            self.terminal_waits[token] = status

    def _terminate_gpu_signals(self) -> None:
        # Lifecycle transitions own finalization. Backend callbacks arriving
        # afterward are stale and must not consume or alias a reservation.
        self.terminal_gpu_signals.update(self.pending_gpu_signals)
        self.pending_gpu_signals.clear()

    def _resolve_waits(self) -> None:
        for token, value in list(self.pending_host_waits.items()):
            if self.counter >= value:
                del self.pending_host_waits[token]
                self.terminal_waits[token] = "SUCCESS"
