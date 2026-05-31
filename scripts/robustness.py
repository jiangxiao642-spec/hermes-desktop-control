"""
Desktop Control Robustness Layer — v1.1 (decoupled)

Four independent shields, each usable standalone or composed:

  HealthMonitor   — global health score + observer pattern for state transitions
  TimeGuard       — per-op deadline, session TTL, SOM cache max_age
  CircuitBreaker  — 3 consecutive timeouts → OPEN; auto-half-open after cooldown
  EnvDetector     — screenshot size / DPI change → invalidate SOM cache immediately

v1.1 changes:
  - All shields independently instantiable (no longer requires RobustnessShield)
  - HealthMonitor supports observer registration (HealthObserver Protocol)
  - Optional TimeSource injection for testability
  - Each class explicitly implements its interfaces.Protocol

Implements:
  - interfaces.HealthMonitor
  - interfaces.TimeGuard
  - interfaces.CircuitBreaker
  - interfaces.EnvDetector
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependency — only needed for type hints
# and isinstance checks. At runtime, duck-typing against the Protocol works.
try:
    from scripts.interfaces import (
        DegradationLevel, CircuitState, EnvSnapshot,
        HealthObserver, TimeSource, SafePointSnapshot,
    )
except ImportError:
    # Fallback when running standalone or from a different CWD
    DegradationLevel = None    # type: ignore
    CircuitState = None         # type: ignore
    EnvSnapshot = None          # type: ignore
    HealthObserver = None       # type: ignore
    TimeSource = None           # type: ignore
    SafePointSnapshot = None    # type: ignore


# ═══════════════════════════════════════════════════════════════════════════
# System time source (default)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class SystemTime:
    """Production TimeSource using the real system clock."""
    def now(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()


# ═══════════════════════════════════════════════════════════════════════════
# Verification Result — Ternary (Claude's suggestion, 2026-05-31)
# ═══════════════════════════════════════════════════════════════════════════

from enum import Enum


class VerifyResult(Enum):
    """三元验证结果——不是 pass/fail 二元，uncertain 是合法状态。

    PASS: 验证通过，操作成功
    FAIL: 验证失败，需要 rollback
    UNCERTAIN: 不确定——需要升级到更重的验证层
    """
    PASS = "PASS"
    FAIL = "FAIL"
    UNCERTAIN = "UNCERTAIN"


# ═══════════════════════════════════════════════════════════════════════════
# Anchor Heartbeat (Claude's suggestion, 2026-05-31)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class AnchorHeartbeat:
    """每轮操作前确认关键控件还在——不等失败才发现窗口没了。

    注意：实际 UIA 扫描在 PowerShell 端执行（有 UIAutomationClient）。
    此类是 Python 侧的抽象——记录锚点定义和检查结果。
    真正的元素存活检查走 bridge: mcp_windows_bridge_run_powershell

    关键锚点（每个应用定义自己的一套）:
    - Claude Desktop: [("Send message", "Button"), ("Write your prompt to Claude", "Edit")]
    - OpenClaw: [("Message Assistant (Enter to send)", "Edit")]
    """

    _anchors: list = field(default_factory=list)  # [(name, control_type), ...]
    _missing_threshold: int = 2
    _consecutive_missing: int = 0
    _last_check_time: float = 0.0
    _clock: Any = field(default_factory=SystemTime)

    def set_anchors(self, anchors: list):
        """设定锚点列表。anchors: [("Send message", "Button"), ...]"""
        self._anchors = anchors

    def evaluate(self, found_count: int) -> VerifyResult:
        """根据外部 UIA 扫描结果评估锚点状态。

        found_count: 外部扫描找到的锚点数量
        返回 PASS/FAIL/UNCERTAIN（由外部决定升级策略）
        """
        self._last_check_time = self._clock.monotonic()
        total = len(self._anchors)

        if found_count >= total:
            self._consecutive_missing = 0
            return VerifyResult.PASS
        elif found_count == 0:
            self._consecutive_missing += 1
            if self._consecutive_missing >= self._missing_threshold:
                return VerifyResult.FAIL
            return VerifyResult.UNCERTAIN
        else:
            self._consecutive_missing = 0
            return VerifyResult.UNCERTAIN

    @property
    def is_alive(self) -> bool:
        return self._consecutive_missing < self._missing_threshold

    def summary(self) -> str:
        return (
            f"AnchorHeartbeat: {len(self._anchors)} anchors | "
            f"consec_missing={self._consecutive_missing}"
        )

# DegradationLevel enum used even if interfaces import fails
if DegradationLevel is None:
    from enum import Enum, auto
    class DegradationLevel(Enum):
        NORMAL = auto()
        DEGRADED = auto()
        FALLBACK = auto()
        STALLED = auto()


class OperationTimeout(Exception):
    """Raised when a single operation exceeds its time budget."""
    pass


class SessionExpired(Exception):
    """Raised when the visual session has exceeded its total TTL."""
    pass


class CircuitBreakerOpen(Exception):
    """Raised when the circuit breaker is open and the operation is blocked."""
    pass


@dataclass
class HealthMonitor:
    """Tracks a global health score and degrades capabilities on failure.

    Implements: interfaces.HealthMonitor

    Observers: register HealthObserver callables via add_observer().
    They fire on every level transition (NORMAL→DEGRADED, etc.).
    """

    score: int = 100
    level: DegradationLevel = DegradationLevel.NORMAL
    consecutive_successes: int = 0
    consecutive_failures: int = 0
    total_ops: int = 0
    failed_ops: int = 0
    last_failure_reason: str = ""
    stall_reason: str = ""
    _recovery_threshold: int = 3
    _degradation_threshold: int = 80
    _fallback_threshold: int = 50
    _stall_threshold: int = 20
    _observers: list = field(default_factory=list)
    _clock: Any = field(default_factory=SystemTime)

    # ── Observer management ──────────────────────────────────────

    def add_observer(self, observer) -> None:
        """Register a HealthObserver to be notified on level transitions.

        observer can be:
          - An object with on_health_change(old, new, score, reason)
          - A callable taking (old_level, new_level, score, reason)
        """
        self._observers.append(observer)

    def remove_observer(self, observer) -> None:
        if observer in self._observers:
            self._observers.remove(observer)

    def _notify_observers(self, old_level: DegradationLevel,
                          reason: str) -> None:
        for obs in self._observers:
            try:
                if hasattr(obs, "on_health_change"):
                    obs.on_health_change(old_level, self.level, self.score, reason)
                elif callable(obs):
                    obs(old_level, self.level, self.score, reason)
            except Exception as exc:
                logger.warning("HealthMonitor observer error: %s", exc)

    # ── Scoring ─────────────────────────────────────────────────

    def record_success(self) -> DegradationLevel:
        self.total_ops += 1
        self.consecutive_successes += 1
        self.consecutive_failures = 0
        self.score = min(100, self.score + 5)

        old_level = self.level
        if self.consecutive_successes >= self._recovery_threshold:
            self._auto_recover()
            self.consecutive_successes = 0

        if self.level != old_level:
            self._notify_observers(old_level, "auto-recovery after successes")
        return self.level

    def record_failure(self, reason: str, penalty: int = -10) -> DegradationLevel:
        self.total_ops += 1
        self.failed_ops += 1
        self.consecutive_failures += 1
        self.consecutive_successes = 0
        self.score = max(0, self.score + penalty)
        self.last_failure_reason = reason
        old_level = self.level
        self._recompute_level()
        if self.level != old_level:
            self._notify_observers(old_level, reason)
        return self.level

    def record_vision_timeout(self) -> DegradationLevel:
        return self.record_failure("vision API timeout", penalty=-20)

    def record_som_parse_failure(self) -> DegradationLevel:
        return self.record_failure("SOM parse returned empty", penalty=-30)

    def record_phantom_element(self, element_index: int, label: str) -> DegradationLevel:
        reason = f"phantom element #{element_index} '{label}'"
        return self.record_failure(reason, penalty=-40)

    # ── Degradation control ─────────────────────────────────────

    def _auto_recover(self):
        if self.level == DegradationLevel.DEGRADED:
            self.level = DegradationLevel.NORMAL
            self.score = max(self.score, 80)
            logger.info("HealthMonitor: recovered to NORMAL (score=%d)", self.score)
        elif self.level == DegradationLevel.FALLBACK:
            self.level = DegradationLevel.DEGRADED
            self.score = max(self.score, 50)
            logger.info("HealthMonitor: recovered to DEGRADED (score=%d)", self.score)
        elif self.level == DegradationLevel.STALLED:
            self.level = DegradationLevel.FALLBACK
            self.score = max(self.score, 20)
            logger.info("HealthMonitor: recovered to FALLBACK (score=%d)", self.score)

    def _recompute_level(self):
        if self.score < self._stall_threshold:
            if self.level != DegradationLevel.STALLED:
                self.stall_reason = self.last_failure_reason
                logger.error("HealthMonitor: STALLED (score=%d, reason=%s)",
                           self.score, self.stall_reason)
            self.level = DegradationLevel.STALLED
        elif self.score < self._fallback_threshold:
            if self.level != DegradationLevel.FALLBACK:
                logger.warning("HealthMonitor: FALLBACK (score=%d)", self.score)
            self.level = DegradationLevel.FALLBACK
        elif self.score < self._degradation_threshold:
            if self.level != DegradationLevel.DEGRADED:
                logger.warning("HealthMonitor: DEGRADED (score=%d)", self.score)
            self.level = DegradationLevel.DEGRADED

    # ── Capability queries ──────────────────────────────────────

    def can_use_vision(self) -> bool:
        return self.level in (DegradationLevel.NORMAL, DegradationLevel.DEGRADED)

    def can_operate(self) -> bool:
        return self.level != DegradationLevel.STALLED

    def should_suspend_visual_path(self) -> bool:
        return self.level in (DegradationLevel.FALLBACK, DegradationLevel.STALLED)

    def summary(self) -> str:
        return (
            f"Health: score={self.score} level={self.level.name} "
            f"ops={self.total_ops} failed={self.failed_ops} "
            f"consec_fail={self.consecutive_failures}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Time Guard
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class TimeGuard:
    """Enforces time budgets at three levels. Independently usable.

    Implements: interfaces.TimeGuard
    """

    op_timeout: float = 30.0
    session_ttl: float = 600.0
    som_cache_max_age: float = 300.0

    _session_start: float = field(default_factory=time.monotonic)
    _op_start: float = 0.0
    _som_age: float = 0.0
    _clock: Any = field(default_factory=SystemTime)

    def start_operation(self):
        if self._clock.monotonic() - self._session_start > self.session_ttl:
            raise SessionExpired(
                f"Visual session expired (>{self.session_ttl:.0f}s)"
            )
        self._op_start = self._clock.monotonic()

    def check_timeout(self) -> bool:
        elapsed = self._clock.monotonic() - self._op_start
        if elapsed > self.op_timeout:
            raise OperationTimeout(
                f"Operation exceeded budget ({elapsed:.1f}s > {self.op_timeout:.0f}s)"
            )
        return True

    def remaining_op_time(self) -> float:
        return max(0.0, self.op_timeout - (self._clock.monotonic() - self._op_start))

    def is_som_cache_stale(self) -> bool:
        if self._som_age == 0.0:
            return False
        return (self._clock.monotonic() - self._som_age) > self.som_cache_max_age

    def refresh_som(self):
        self._som_age = self._clock.monotonic()

    def reset_session(self):
        self._session_start = self._clock.monotonic()
        self._som_age = 0.0

    def summary(self) -> str:
        elapsed = self._clock.monotonic() - self._session_start
        cache_age = (self._clock.monotonic() - self._som_age) if self._som_age else 0.0
        return (
            f"Session: {elapsed:.0f}s/{self.session_ttl:.0f}s | "
            f"Cache age: {cache_age:.0f}s/{self.som_cache_max_age:.0f}s"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Circuit Breaker
# ═══════════════════════════════════════════════════════════════════════════

# CircuitState enum even if interfaces import fails
if CircuitState is None:
    from enum import Enum
    class CircuitState(Enum):
        CLOSED = "CLOSED"
        OPEN = "OPEN"
        HALF_OPEN = "HALF_OPEN"

# SafePointSnapshot dataclass even if interfaces import fails
if SafePointSnapshot is None:
    @dataclass
    class SafePointSnapshot:
        phash: str = ""
        window_class: str = ""
        window_title: str = ""
        som_element_count: int = 0
        focused_control: str = ""
        action: str = ""
        description: str = ""
        step_index: int = 0
        timestamp: float = 0.0


@dataclass
class CircuitBreaker:
    """Circuit breaker for vision API calls. Independently usable.

    Implements: interfaces.CircuitBreaker
    """

    failure_threshold: int = 3
    cooldown_seconds: float = 60.0

    _consecutive_timeouts: int = 0
    _state: CircuitState = CircuitState.CLOSED
    _opened_at: float = 0.0
    _total_tripped: int = 0
    _clock: Any = field(default_factory=SystemTime)

    def record_timeout(self) -> bool:
        self._consecutive_timeouts += 1
        if self._consecutive_timeouts >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = self._clock.monotonic()
            self._total_tripped += 1
            logger.error(
                "CircuitBreaker: OPEN after %d consecutive timeouts (trip #%d)",
                self._consecutive_timeouts, self._total_tripped,
            )
            return True
        return False

    def record_success(self):
        self._consecutive_timeouts = 0
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            logger.info("CircuitBreaker: CLOSED (probe succeeded)")

    def record_non_timeout_failure(self, error: str = ""):
        pass  # input errors don't indicate infrastructure problems

    def allow_call(self) -> bool:
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.OPEN:
            if self._clock.monotonic() - self._opened_at >= self.cooldown_seconds:
                self._state = CircuitState.HALF_OPEN
                logger.info("CircuitBreaker: HALF_OPEN (probing)")
                return True
            return False
        return True  # HALF_OPEN

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN

    def summary(self) -> str:
        cooldown_left = 0.0
        if self._state == CircuitState.OPEN:
            cooldown_left = max(
                0.0,
                self.cooldown_seconds - (self._clock.monotonic() - self._opened_at),
            )
        return (
            f"Breaker: {self._state.value} | "
            f"timeouts={self._consecutive_timeouts}/{self.failure_threshold} | "
            f"cooldown={cooldown_left:.0f}s | "
            f"trips={self._total_tripped}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Environment Detector
# ═══════════════════════════════════════════════════════════════════════════

# EnvSnapshot dataclass even if interfaces import fails
if EnvSnapshot is None:
    @dataclass
    class EnvSnapshot:
        screen_width: int = 0
        screen_height: int = 0
        dpi_scale: float = 1.0
        monitor_count: int = 1

        def __eq__(self, other: object) -> bool:
            if not isinstance(other, EnvSnapshot):
                return False
            return (
                self.screen_width == other.screen_width
                and self.screen_height == other.screen_height
                and abs(self.dpi_scale - other.dpi_scale) < 0.01
                and self.monitor_count == other.monitor_count
            )


@dataclass
class EnvDetector:
    """Detects environment changes that invalidate cached visual state.

    Implements: interfaces.EnvDetector
    """

    _baseline: Optional[EnvSnapshot] = None
    _change_count: int = 0
    _observers: list = field(default_factory=list)

    def add_observer(self, observer) -> None:
        """Register a callable(EnvSnapshot, EnvSnapshot) for env changes."""
        self._observers.append(observer)

    def capture(self, width: int, height: int, dpi: float = 1.0,
                monitor_count: int = 1) -> bool:
        snap = EnvSnapshot(
            screen_width=width,
            screen_height=height,
            dpi_scale=dpi,
            monitor_count=monitor_count,
        )
        if self._baseline is None:
            self._baseline = snap
            return False
        if snap != self._baseline:
            old = self._baseline
            self._change_count += 1
            logger.warning(
                "EnvDetector: change #%d — %dx%d@%.1fx(%d) → %dx%d@%.1fx(%d)",
                self._change_count,
                old.screen_width, old.screen_height, old.dpi_scale, old.monitor_count,
                snap.screen_width, snap.screen_height, snap.dpi_scale, snap.monitor_count,
            )
            self._baseline = snap
            for obs in self._observers:
                try:
                    obs(old, snap)
                except Exception as exc:
                    logger.warning("EnvDetector observer error: %s", exc)
            return True
        return False

    @property
    def baseline(self) -> Optional[EnvSnapshot]:
        return self._baseline

    @property
    def change_count(self) -> int:
        return self._change_count


# ═══════════════════════════════════════════════════════════════════════════
# SafePoint Manager — 5th shield (recovery)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class SafePointManager:
    """5th shield: checkpoint-rollback for multi-step operations.

    Implements: interfaces.SafePoint

    The first four shields (Health, Time, Circuit, Env) are *preventive* —
    they detect problems and block before things get worse. SafePoint is the
    *recovery* shield — it captures state before each step so that on failure
    the pipeline returns to a known-good state instead of retrying from a
    broken one.

    Usage:
        sp = SafePointManager()
        sp.checkpoint(phash="abc", window_class="Notepad", ...)
        # step 1 executes...
        sp.checkpoint(phash="def", window_class="Notepad", ...)
        # step 2 fails
        snap = sp.rollback("弹窗遮挡")
        action = sp.get_recovery_action("弹窗遮挡")  # → "close_popup"
    """

    _checkpoints: list = field(default_factory=list)
    _rollback_count: int = 0
    _max_consecutive_rollbacks: int = 3
    _clock: Any = field(default_factory=SystemTime)

    # ── Checkpoint ──────────────────────────────────────────────────

    def checkpoint(self, **state) -> SafePointSnapshot:
        """Capture current state before executing one step of a multi-step operation.

        Call before each step. Accepts keyword arguments:
          phash, window_class, window_title, som_element_count, focused_control
          action — what this step does ("click", "type", "scroll", …)
          description — human-readable: "click element=7 (Button '发送')"
        """
        snap = SafePointSnapshot(
            phash=state.get("phash", ""),
            window_class=state.get("window_class", ""),
            window_title=state.get("window_title", ""),
            som_element_count=state.get("som_element_count", 0),
            focused_control=state.get("focused_control", ""),
            action=state.get("action", ""),
            description=state.get("description", ""),
            step_index=len(self._checkpoints),
            timestamp=self._clock.monotonic(),
        )
        self._checkpoints.append(snap)
        self._rollback_count = 0  # reset on successful checkpoint
        logger.debug("SafePoint: checkpoint #%d — %s %s",
                      snap.step_index, snap.action, snap.description or "")
        return snap

    # ── Rollback ────────────────────────────────────────────────────

    def rollback(self, failure_reason: str = "") -> SafePointSnapshot:
        """Return to the last known-safe state.

        Does NOT mutate external state (windows, processes). Returns the
        snapshot of the safe point so the caller can restore state.

        After max_consecutive_rollbacks (3), can_recover() returns False.
        Caller MUST emit DESKTOP_CONTROL_FAILED instead of retrying further:
          DESKTOP_CONTROL_FAILED: [目标窗口] [操作] [原因]
        """
        self._rollback_count += 1

        if not self._checkpoints:
            logger.warning("SafePoint: rollback called but no checkpoints saved")
            return SafePointSnapshot(step_index=-1)

        # Pop failed step's checkpoint, keep the previous known-good one
        if len(self._checkpoints) > 1:
            discarded = self._checkpoints.pop()
            logger.info("SafePoint: discarding step #%d checkpoint (%s)",
                        discarded.step_index, discarded.description or "?")

        snap = self._checkpoints[-1]
        action = self.get_recovery_action(failure_reason)

        if self._rollback_count > self._max_consecutive_rollbacks:
            logger.error(
                "SafePoint: %d consecutive rollbacks — DESKTOP_CONTROL_FAILED: "
                "step #%d %s — reason=%s",
                self._rollback_count, snap.step_index,
                snap.description or snap.action, failure_reason,
            )

        logger.info("SafePoint: rollback to step #%d → %s → reason=%s",
                     snap.step_index, action, failure_reason or "unknown")
        return snap

    # ── Recovery decision ───────────────────────────────────────────

    def can_recover(self) -> bool:
        """True if there's a known-good state and we haven't exhausted retries."""
        return (len(self._checkpoints) > 0
                and self._rollback_count <= self._max_consecutive_rollbacks)

    def get_recovery_action(self, failure_reason: str) -> str:
        """Recommend a recovery action based on failure reason.

        Returns one of:
          - "close_popup" — dismiss modal/popup/overlay, retry
          - "refocus_window" — re-SetForegroundWindow, retry
          - "relaunch_app" — target window is gone, re-launch
          - "refresh_som" — layout changed, redo full-screen SOM
          - "retry_alternate_path" — same state, different approach
          - "notify_user" — out of automated recovery options
        """
        reason_lower = failure_reason.lower()

        # Popup / modal / overlay blocking the target
        if any(kw in reason_lower for kw in (
                "弹窗", "遮挡", "popup", "modal", "dialog", "overlay",
                "覆盖", "遮挡", "弹框",
        )):
            return "close_popup"

        # Focus / foreground lost
        if any(kw in reason_lower for kw in (
                "焦点", "focus", "foreground", "前台", "激活",
        )):
            return "refocus_window"

        # Window disappeared entirely
        if any(kw in reason_lower for kw in (
                "窗口", "window gone", "closed", "crash", "消失",
                "关闭", "崩溃",
        )):
            return "relaunch_app"

        # Layout / resolution / SOM drift
        if any(kw in reason_lower for kw in (
                "布局", "layout", "resolution", "phash", "changed",
                "变化", "分辨率", "漂移",
        )):
            return "refresh_som"

        # Exhausted automated recovery
        if self._rollback_count > self._max_consecutive_rollbacks:
            return "notify_user"

        return "retry_alternate_path"

    # ── Properties ──────────────────────────────────────────────────

    @property
    def current_snapshot(self) -> Optional[SafePointSnapshot]:
        if self._checkpoints:
            return self._checkpoints[-1]
        return None

    @property
    def step_count(self) -> int:
        return len(self._checkpoints)

    # ── Lifecycle ───────────────────────────────────────────────────

    def clear(self):
        """Reset all checkpoints for a new operation sequence."""
        self._checkpoints.clear()
        self._rollback_count = 0

    def summary(self) -> str:
        return (
            f"SafePoint: {len(self._checkpoints)} checkpoints | "
            f"rollbacks={self._rollback_count}/{self._max_consecutive_rollbacks}"
            + (f" | current_step={self._checkpoints[-1].step_index}"
               if self._checkpoints else " | empty")
        )


# ═══════════════════════════════════════════════════════════════════════════
# Unified shield — convenience composition (backward-compatible)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class RobustnessShield:
    """Convenience composition of all five shields.

    For simple use cases, create this and access .health / .time / .breaker / .env / .safepoint.
    For advanced use, instantiate each shield independently and wire observers.

    Backward-compatible with v1.0 API.
    """

    health: HealthMonitor = field(default_factory=HealthMonitor)
    time: TimeGuard = field(default_factory=TimeGuard)
    breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    env: EnvDetector = field(default_factory=EnvDetector)
    safepoint: SafePointManager = field(default_factory=SafePointManager)

    def __post_init__(self):
        # Wire default observers: env change → invalidate SOM cache
        def _on_env_change(old, new):
            self.time._som_age = 0.0
            logger.info("RobustnessShield: SOM cache invalidated (env change)")
            # If health is degraded due to env issues, give partial recovery
            if self.health.level == DegradationLevel.FALLBACK:
                self.health.score = min(100, self.health.score + 10)
        self.env.add_observer(_on_env_change)

        # Wire health → circuit breaker synergy
        def _on_health_change(old_level, new_level, score, reason):
            if new_level == DegradationLevel.STALLED:
                logger.error("RobustnessShield: STALLED — reason=%s", reason)
            # Auto-checkpoint on health degradation — capture state before things degrade further
            if new_level in (DegradationLevel.DEGRADED, DegradationLevel.FALLBACK):
                self.safepoint.checkpoint(
                    window_class=getattr(self.env.baseline, 'screen_width', 0),
                    som_element_count=0,
                )
        self.health.add_observer(_on_health_change)

    def force_som_refresh(self):
        self.time._som_age = 0.0

    def is_healthy(self) -> bool:
        return (
            self.health.can_operate()
            and self.breaker.allow_call()
            and not self.health.should_suspend_visual_path()
        )

    def summary(self) -> str:
        lines = [
            self.health.summary(),
            self.time.summary(),
            self.breaker.summary(),
            self.safepoint.summary(),
        ]
        if self.env.baseline:
            b = self.env.baseline
            lines.append(
                f"Env: {b.screen_width}x{b.screen_height}@{b.dpi_scale:.1f}x"
                + (f" changes={self.env.change_count}" if self.env.change_count else "")
            )
        return " | ".join(lines)
