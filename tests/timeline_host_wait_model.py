"""Regression model for Host WaitSemaphores racing GPU timeline signals.

Wait registrations are level-triggered predicates over the canonical timeline
counter. They do not reserve signal values and terminal completion is one-shot.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Timeline:
    counter: int
    pending_gpu_signals: dict[int, int] = field(default_factory=dict)
    pending_host_waits: dict[int, int] = field(default_factory=dict)
    terminal_waits: dict[int, str] = field(default_factory=dict)

    def begin_host_wait(self, token: int, value: int) -> str:
        if token == 0 or token in self.pending_host_waits or token in self.terminal_waits:
            return "BadValue"
        if value <= self.counter:
            self.terminal_waits[token] = "SUCCESS"
            return "SUCCESS"
        self.pending_host_waits[token] = value
        return "PENDING"

    def signal_host(self, value: int) -> str:
        if value <= self.counter:
            return "INVALID_SYNCHRONIZATION_STATE"
        if any(value >= reserved for reserved in self.pending_gpu_signals.values()):
            return "INVALID_SYNCHRONIZATION_STATE"
        self.counter = value
        self._resolve_waits()
        return "SUCCESS"

    def reserve_gpu_signal(self, token: int, value: int) -> str:
        if token == 0 or token in self.pending_gpu_signals:
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
        if success:
            self.counter = max(self.counter, value)
            self._resolve_waits()
        return "SUCCESS"

    def finish_host_wait(self, token: int, status: str) -> str:
        if token not in self.pending_host_waits:
            return "BadValue"
        del self.pending_host_waits[token]
        self.terminal_waits[token] = status
        return "SUCCESS"

    def _resolve_waits(self) -> None:
        for token, value in list(self.pending_host_waits.items()):
            if self.counter >= value:
                del self.pending_host_waits[token]
                self.terminal_waits[token] = "SUCCESS"
