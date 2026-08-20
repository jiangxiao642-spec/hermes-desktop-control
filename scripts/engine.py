"""Unified desktop-control execution engine.

The engine owns the full control chain:
lock -> anchor preflight -> pipeline -> recovery -> final result.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol

try:
    from .interfaces import Operation, OperationResult, Pipeline, VerifyResult
    from .verify_dispatch import check_anchors
except ImportError:
    try:
        from scripts.interfaces import Operation, OperationResult, Pipeline, VerifyResult
        from scripts.verify_dispatch import check_anchors
    except ImportError:
        from interfaces import Operation, OperationResult, Pipeline, VerifyResult
        from verify_dispatch import check_anchors


@dataclass(frozen=True)
class TargetContext:
    session_id: str
    window_key: str
    app_name: str = ""
    uia_snap_path: str = ""
    metadata: Optional[dict[str, Any]] = None

    @property
    def lock_key(self) -> str:
        return f"{self.session_id}:{self.window_key}"


class RecoveryExecutor(Protocol):
    async def perform(self, action: str, target: TargetContext, reason: str) -> bool: ...


class CallbackRecoveryExecutor:
    """Execute named recovery actions through injected callbacks."""

    def __init__(self, callbacks: Optional[dict[str, Callable]] = None):
        self._callbacks = dict(callbacks or {})

    def register(self, action: str, callback: Callable) -> None:
        self._callbacks[action] = callback

    async def perform(self, action: str, target: TargetContext, reason: str) -> bool:
        callback = self._callbacks.get(action)
        if callback is None:
            return False
        result = callback(target, reason)
        if inspect.isawaitable(result):
            result = await result
        return bool(result)


class DesktopControlEngine:
    """Serialize access per target and run the complete safety chain."""

    def __init__(
        self,
        pipeline: Pipeline,
        *,
        recovery: Optional[RecoveryExecutor] = None,
        anchor_probe: Callable = check_anchors,
        max_recovery_attempts: int = 1,
    ):
        self.pipeline = pipeline
        self.recovery = recovery
        self.anchor_probe = anchor_probe
        self.max_recovery_attempts = max(0, max_recovery_attempts)
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, target: TargetContext) -> asyncio.Lock:
        lock = self._locks.get(target.lock_key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[target.lock_key] = lock
        return lock

    def _anchor_status(self, target: TargetContext) -> VerifyResult:
        if not target.app_name or not target.uia_snap_path:
            return VerifyResult.PASS
        heartbeat = self.anchor_probe(target.app_name, target.uia_snap_path)
        if not heartbeat._anchors:
            return VerifyResult.PASS
        return heartbeat.last_result

    async def _recover(self, action: str, target: TargetContext, reason: str) -> bool:
        if self.recovery is None:
            return False
        return await self.recovery.perform(action, target, reason)

    def _result(self, op: Operation, error: str) -> OperationResult:
        return OperationResult(success=False, operation=op, error=error)

    async def execute(self, op: Operation, target: TargetContext) -> OperationResult:
        async with self._lock_for(target):
            anchor_status = self._anchor_status(target)
            if anchor_status is not VerifyResult.PASS:
                recovered = await self._recover(
                    "reactivate_uia", target, f"anchor preflight: {anchor_status.value}"
                )
                if not recovered or self._anchor_status(target) is not VerifyResult.PASS:
                    return self._result(
                        op,
                        f"DESKTOP_CONTROL_FAILED: anchor preflight {anchor_status.value}",
                    )

            result = await self.pipeline.execute(op)
            if result.success or result.action_executed:
                return result

            for _attempt in range(self.max_recovery_attempts):
                action = op.fallback_action or "retry_alternate_path"
                safe_point = getattr(self.pipeline, "safe_point", None)
                if safe_point is not None:
                    action = safe_point.get_recovery_action(result.error or "")
                if not await self._recover(action, target, result.error or ""):
                    break
                if self._anchor_status(target) is VerifyResult.FAIL:
                    break
                result = await self.pipeline.execute(op)
                if result.success or result.action_executed:
                    break

            return result


__all__ = [
    "CallbackRecoveryExecutor",
    "DesktopControlEngine",
    "RecoveryExecutor",
    "TargetContext",
]
