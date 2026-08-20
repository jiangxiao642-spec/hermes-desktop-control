"""Adaptive, state-driven waiting for desktop operations."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Callable

try:
    from .interfaces import OperationResult
except ImportError:
    try:
        from scripts.interfaces import OperationResult
    except ImportError:
        from interfaces import OperationResult


@dataclass
class WaitStats:
    samples: int = 0
    ewma_seconds: float = 0.0

    def observe(self, elapsed: float, alpha: float) -> None:
        self.samples += 1
        if self.samples == 1:
            self.ewma_seconds = elapsed
        else:
            self.ewma_seconds = alpha * elapsed + (1.0 - alpha) * self.ewma_seconds


@dataclass
class AdaptiveWaiter:
    """Poll a verifier using adaptive delays and learned operation latency."""

    initial_delay: float = 0.05
    max_delay: float = 0.8
    multiplier: float = 1.6
    history_alpha: float = 0.3
    min_timeout: float = 0.5
    max_timeout: float = 30.0
    _history: dict[str, WaitStats] = field(default_factory=dict)
    _clock: Callable[[], float] = time.monotonic

    def recommended_timeout(self, key: str, fallback: float) -> float:
        stats = self._history.get(key)
        if stats is None or stats.samples == 0:
            return max(self.min_timeout, min(self.max_timeout, fallback))
        learned = max(self.min_timeout, stats.ewma_seconds * 2.5 + self.initial_delay)
        return min(self.max_timeout, max(learned, min(fallback, self.max_timeout) * 0.5))

    async def wait_for(self, probe, *, key: str, timeout: float) -> OperationResult:
        budget = self.recommended_timeout(key, timeout)
        started = self._clock()
        delay = self.initial_delay
        previous_signature = None
        last_result = probe()

        while not last_result.success:
            elapsed = self._clock() - started
            remaining = budget - elapsed
            if remaining <= 0:
                if not last_result.error:
                    last_result.error = f"verification timed out after {elapsed:.2f}s"
                return last_result

            signature = (
                last_result.actual_state,
                last_result.error,
                last_result.method_used,
            )
            if previous_signature is not None and signature != previous_signature:
                delay = self.initial_delay
            previous_signature = signature

            await asyncio.sleep(min(delay, remaining))
            delay = min(self.max_delay, delay * self.multiplier)
            last_result = probe()

        elapsed = self._clock() - started
        self._history.setdefault(key, WaitStats()).observe(elapsed, self.history_alpha)
        return last_result


__all__ = ["AdaptiveWaiter", "WaitStats"]
