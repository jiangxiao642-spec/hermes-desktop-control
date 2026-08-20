"""
Desktop Control Interfaces — v1.0

Abstract protocols for every pluggable component in the desktop-control pipeline.

Design principles:
  - Every strategy is a Protocol — swap implementations without touching pipeline code
  - Observer pattern for health/circuit/env events — external code reacts without polling
  - All time goes through TimeSource — testable with fake clocks
  - All hashing goes through HashEngine — swappable without cascading changes

Pipeline contract:
  Capture → Annotate → CrossValidate → Decide → Execute → Verify → Record

Each step is a strategy. The pipeline only knows the Protocol, not the implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional, Protocol, runtime_checkable


# ═══════════════════════════════════════════════════════════════════════════
# Domain types — shared across all interfaces
# ═══════════════════════════════════════════════════════════════════════════

class DegradationLevel(Enum):
    NORMAL = auto()
    DEGRADED = auto()
    FALLBACK = auto()
    STALLED = auto()


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class VerifyResult(Enum):
    """Ternary verification result — not binary pass/fail.

    UNCERTAIN is a legitimate state that auto-escalates
    to the next heavier verification layer.
    """
    PASS = "PASS"
    FAIL = "FAIL"
    UNCERTAIN = "UNCERTAIN"


@dataclass
class AnchorHeartbeat:
    """Pre-operation check: confirm key controls are alive before acting.

    Actual UIA scanning happens on the PowerShell side (UIAutomationClient).
    This is the Python-side abstraction recording anchor definitions and
    check results.

    Key anchors (application-specific):
    - Claude Desktop: [("Write your prompt to Claude", "Edit"), ("Send message", "Button")]
    - OpenClaw: [("Message Assistant (Enter to send)", "Edit")]
    """

    _anchors: list = field(default_factory=list)  # [(name, control_type), ...]
    _missing_threshold: int = 2
    _consecutive_missing: int = 0
    _last_check_time: float = 0.0
    _last_result: VerifyResult = VerifyResult.UNCERTAIN
    _clock: Any = None

    def __post_init__(self):
        if self._clock is None:
            import time
            # lightweight clock from stdlib — caller can inject TimeSource for tests
            self._clock = type("_Clock", (), {
                "monotonic": staticmethod(time.monotonic),
            })()

    def set_anchors(self, anchors: list) -> None:
        """Set anchor list: [("Send message", "Button"), ...]"""
        self._anchors = anchors

    def evaluate(self, found_count: int) -> "VerifyResult":
        """Evaluate anchor state from external UIA scan result.

        found_count: number of anchors found by external scan.
        Returns PASS / FAIL / UNCERTAIN (caller decides escalation).
        """
        self._last_check_time = self._clock.monotonic()
        total = len(self._anchors)

        if found_count >= total:
            self._consecutive_missing = 0
            self._last_result = VerifyResult.PASS
            return self._last_result
        elif found_count == 0:
            self._consecutive_missing += 1
            if self._consecutive_missing >= self._missing_threshold:
                self._last_result = VerifyResult.FAIL
                return self._last_result
            self._last_result = VerifyResult.UNCERTAIN
            return self._last_result
        else:
            self._consecutive_missing = 0
            self._last_result = VerifyResult.UNCERTAIN
            return self._last_result

    @property
    def is_alive(self) -> bool:
        return self._consecutive_missing < self._missing_threshold

    @property
    def last_result(self) -> VerifyResult:
        return self._last_result

    def summary(self) -> str:
        return (
            f"AnchorHeartbeat: {len(self._anchors)} anchors | "
            f"consec_missing={self._consecutive_missing}"
        )


@dataclass
class UIElement:
    """Normalized element representation across UIA / vision / DOM sources."""
    index: int
    element_type: str           # Button, Edit, Icon, Tab, CheckBox, etc.
    label: str                  # visible text / accessible name
    bounds: tuple               # (x, y, w, h) in screenshot pixels
    source: str = "unknown"     # "uia" | "vision" | "cdp"
    automation_id: str = ""
    confidence: float = 0.85
    cross_validated: bool = False

    @property
    def center(self) -> tuple:
        x, y, w, h = self.bounds
        return (x + w // 2, y + h // 2)


@dataclass
class Operation:
    """A single GUI operation with expected outcome."""
    action: str                 # "click" | "type" | "read" | "scroll" | "navigate"
    element_index: int = 0
    element_label: str = ""
    text: str = ""              # for type operations
    expected: str = ""          # human-readable expected outcome
    verify_method: str = ""     # "uia_value" | "ocr" | "phash" | "vision"
    max_retries: int = 2
    fallback_action: str = ""   # what to try if this fails
    idempotent: bool = False
    verification_timeout: float = 8.0


@dataclass
class OperationResult:
    """Outcome of a single operation after verification."""
    success: bool
    operation: Operation
    actual_state: str = ""       # what was actually observed
    method_used: str = ""        # which path succeeded: "uia" | "visual" | "fallback"
    retries: int = 0
    latency_ms: float = 0.0
    error: str = ""
    action_executed: bool = False


@dataclass
class EnvSnapshot:
    """Captured environment state."""
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


# ═══════════════════════════════════════════════════════════════════════════
# Time & Hash — infrastructure abstractions (testability)
# ═══════════════════════════════════════════════════════════════════════════

@runtime_checkable
class TimeSource(Protocol):
    """Abstract clock. Use system time in production, fake clock in tests."""
    def now(self) -> float: ...
    def monotonic(self) -> float: ...


@runtime_checkable
class HashEngine(Protocol):
    """Abstract perceptual hashing. imagehash or pixel-sampling or custom."""
    def compute(self, image: Any, hash_size: int = 8) -> str: ...
    def distance(self, h1: str, h2: str) -> int: ...


# ═══════════════════════════════════════════════════════════════════════════
# Pipeline stage interfaces — one Protocol per step
# ═══════════════════════════════════════════════════════════════════════════

@runtime_checkable
class ImageCapture(Protocol):
    """Capture screenshots of the desktop / windows."""
    def fullscreen(self) -> Any: ...          # returns PIL Image or path
    def window_region(self, bounds: tuple) -> Any: ...
    @property
    def current_env(self) -> EnvSnapshot: ...


@runtime_checkable
class SOMAnnotator(Protocol):
    """Produce a list of interactive UI elements from a screenshot."""
    def annotate(self, image: Any, prompt: str = "") -> list[UIElement]: ...
    @property
    def source_name(self) -> str: ...  # "uia" | "vision" | "cdp"


@runtime_checkable
class ElementOperator(Protocol):
    """Execute an operation on a UI element."""
    def click(self, element: UIElement) -> bool: ...
    def type_text(self, element: UIElement, text: str) -> bool: ...
    def read_text(self, element: UIElement) -> str: ...
    @property
    def operator_name(self) -> str: ...  # "uia" | "visual" | "cdp"


@runtime_checkable
class Verifier(Protocol):
    """Verify that an operation produced the expected result."""
    def verify(self, op: Operation, context: dict) -> OperationResult: ...
    @property
    def tier(self) -> int: ...  # 0-3, lower = faster


@runtime_checkable
class VerificationWaiter(Protocol):
    """Poll verification with adaptive delays until success or timeout."""
    async def wait_for(self, probe: Callable[[], OperationResult], *,
                       key: str, timeout: float) -> OperationResult: ...


@runtime_checkable
class CrossValidator(Protocol):
    """Reconcile element lists from two sources (e.g. UIA + vision)."""
    def validate(self, primary: list[UIElement],
                 secondary: list[UIElement]) -> list[UIElement]: ...
    @property
    def strategy_name(self) -> str: ...


# ═══════════════════════════════════════════════════════════════════════════
# Shield interfaces — health / time / circuit / env
# ═══════════════════════════════════════════════════════════════════════════

@runtime_checkable
class HealthMonitor(Protocol):
    """Track health score and degrade capabilities on failure."""
    def record_success(self) -> DegradationLevel: ...
    def record_failure(self, reason: str, penalty: int = -10) -> DegradationLevel: ...
    def record_vision_timeout(self) -> DegradationLevel: ...
    def record_som_parse_failure(self) -> DegradationLevel: ...
    def record_phantom_element(self, element_index: int, label: str) -> DegradationLevel: ...
    def can_use_vision(self) -> bool: ...
    def can_operate(self) -> bool: ...
    def should_suspend_visual_path(self) -> bool: ...
    @property
    def level(self) -> DegradationLevel: ...
    @property
    def score(self) -> int: ...


@runtime_checkable
class HealthObserver(Protocol):
    """React to health state transitions. Register with HealthMonitor."""
    def on_health_change(self, old_level: DegradationLevel,
                         new_level: DegradationLevel,
                         score: int, reason: str) -> None: ...


@runtime_checkable
class TimeGuard(Protocol):
    """Enforce operation / session / cache time budgets."""
    def start_operation(self) -> None: ...
    def check_timeout(self) -> bool: ...
    def remaining_op_time(self) -> float: ...
    def is_som_cache_stale(self) -> bool: ...
    def refresh_som(self) -> None: ...
    def reset_session(self) -> None: ...


@runtime_checkable
class CircuitBreaker(Protocol):
    """Block repeated failing calls to protect downstream services."""
    def record_timeout(self) -> bool: ...
    def record_success(self) -> None: ...
    def record_non_timeout_failure(self, error: str) -> None: ...
    def allow_call(self) -> bool: ...
    @property
    def state(self) -> CircuitState: ...


@runtime_checkable
class EnvDetector(Protocol):
    """Detect resolution / DPI / monitor changes."""
    def capture(self, width: int, height: int, dpi: float,
                monitor_count: int) -> bool: ...
    @property
    def baseline(self) -> Optional[EnvSnapshot]: ...
    @property
    def change_count(self) -> int: ...


@dataclass
class SafePointSnapshot:
    """Captured state at a checkpoint in a multi-step operation.

    Five fields that capture the minimum needed to detect drift and recover:
      - phash: layout fingerprint of the current window region
      - window_class: target window's Win32 ClassName
      - window_title: target window's title text
      - som_element_count: number of SOM elements (drift = count changed)
      - focused_control: which element had keyboard focus
      - action: what operation was performed at this step ("click", "type", …)
      - description: human-readable description of what was done
    """
    phash: str = ""
    window_class: str = ""
    window_title: str = ""
    som_element_count: int = 0
    focused_control: str = ""
    action: str = ""
    description: str = ""
    step_index: int = 0
    timestamp: float = 0.0


@runtime_checkable
class SafePoint(Protocol):
    """5th shield: checkpoint-rollback for multi-step operations.

    Preventive shields (Health, Time, Circuit, Env) detect and block.
    SafePoint is the *recovery* shield — it captures state before each
    step so that on failure the pipeline can return to a known-good
    state instead of retrying from a broken one.

    When rollback exhausts max_consecutive_rollbacks, the caller must
    emit DESKTOP_CONTROL_FAILED instead of retrying further.
    """
    def checkpoint(self, **state) -> SafePointSnapshot: ...
    def rollback(self, failure_reason: str) -> SafePointSnapshot: ...
    def record_success(self) -> None: ...
    def can_recover(self) -> bool: ...
    def get_recovery_action(self, failure_reason: str) -> str: ...
    @property
    def current_snapshot(self) -> Optional[SafePointSnapshot]: ...
    @property
    def step_count(self) -> int: ...


# ═══════════════════════════════════════════════════════════════════════════
# Pipeline — composes all strategies into a single execution flow
# ═══════════════════════════════════════════════════════════════════════════

class Pipeline:
    """Orchestrates the desktop-control pipeline with pluggable strategies.

    Usage:
        pipeline = Pipeline(
            capture=ScreenCapture(),
            annotator=HybridSOMAnnotator(uia=uia_som, vision=vision_som),
            cross_validator=LabelOverlapValidator(),
            operator=AdaptiveOperator(uia_op=uia_op, visual_op=visual_op),
            verifier=TieredVerifier(verifiers=[uia_verifier, ocr_verifier, vision_verifier]),
            health=HealthMonitor(),
            time_guard=TimeGuard(),
            circuit_breaker=CircuitBreaker(),
            env_detector=EnvDetector(),
            safe_point=SafePointManager(),
        )
        result = await pipeline.execute(Operation(action="click", element_index=7))
    """

    def __init__(
        self,
        *,
        capture: ImageCapture,
        annotator: SOMAnnotator,
        secondary_annotator: Optional[SOMAnnotator] = None,
        cross_validator: Optional[CrossValidator] = None,
        verification_waiter: Optional[VerificationWaiter] = None,
        operator: ElementOperator,
        verifier: Verifier,
        health: HealthMonitor,
        time_guard: TimeGuard,
        circuit_breaker: CircuitBreaker,
        env_detector: EnvDetector,
        safe_point: Optional[SafePoint] = None,
        time_source: Optional[TimeSource] = None,
        hash_engine: Optional[HashEngine] = None,
    ):
        self.capture = capture
        self.annotator = annotator
        self.secondary_annotator = secondary_annotator
        self.cross_validator = cross_validator
        self.verification_waiter = verification_waiter
        self.operator = operator
        self.verifier = verifier
        self.health = health
        self.time_guard = time_guard
        self.circuit_breaker = circuit_breaker
        self.env_detector = env_detector
        self.safe_point = safe_point
        self._time = time_source
        self._hash = hash_engine

    async def execute(self, op: Operation) -> OperationResult:
        """Run a single operation through the full pipeline.

        Flow: shields→capture→annotate→cross-validate→checkpoint→execute→verify
        On failure: safepoint.rollback → retry with alternate path → DESKTOP_CONTROL_FAILED
        """
        import time as _time
        t0 = _time.monotonic()
        action_executed_any = False

        # ── Phase 0: Shield check ──────────────────────────────────
        if not self.can_proceed():
            return OperationResult(
                success=False, operation=op,
                error="Shields blocked operation",
                actual_state=f"health={self.health.level.name} breaker={self.circuit_breaker.state.value}",
            )

        # ── Phase 1: Environment check ─────────────────────────────
        env = self.capture.current_env
        self.env_detector.capture(env.screen_width, env.screen_height,
                                   env.dpi_scale, env.monitor_count)

        # ── Phase 2: Time guard ────────────────────────────────────
        try:
            self.time_guard.start_operation()
        except Exception as exc:
            return OperationResult(
                success=False, operation=op, error=str(exc),
            )

        # ── Phase 3: Capture + annotate ────────────────────────────
        for attempt in range(op.max_retries + 1):
            try:
                self.time_guard.check_timeout()

                # Checkpoint before step
                if self.safe_point is not None:
                    self.safe_point.checkpoint(
                        action=op.action,
                        description=f"{op.action} element={op.element_index} '{op.element_label}'",
                    )

                # SOM scan
                if op.element_index > 0:
                    # Targeted operation — get elements, find target
                    image = self.capture.fullscreen()
                    elements = self.annotator.annotate(image)

                    # Cross-validate if available
                    if (self.cross_validator is not None
                            and self.secondary_annotator is not None):
                        cross_elements = self.secondary_annotator.annotate(image)
                        elements = self.cross_validator.validate(elements, cross_elements)

                    # Find target element
                    target = None
                    for el in elements:
                        if el.index == op.element_index:
                            target = el
                            break
                    if target is None and op.element_label:
                        for el in elements:
                            if op.element_label.lower() in el.label.lower():
                                target = el
                                break

                    if target is None:
                        self.health.record_failure(
                            f"element #{op.element_index} '{op.element_label}' not found"
                        )
                        if self.safe_point is not None:
                            self.safe_point.rollback("element not found")
                        continue  # retry

                    # Execute
                    success = False
                    if op.action == "click":
                        success = self.operator.click(target)
                    elif op.action == "type":
                        success = self.operator.type_text(target, op.text)
                    elif op.action == "read":
                        text = self.operator.read_text(target)
                        success = bool(text)
                    elif op.action == "scroll":
                        success = self.operator.click(target)  # fallback: click to focus

                    if not success:
                        reason = f"operator rejected {op.action} for element #{target.index}"
                        self.health.record_failure(reason)
                        self.circuit_breaker.record_non_timeout_failure(reason)
                        if self.safe_point is not None:
                            self.safe_point.rollback(reason)
                        continue

                    action_executed_any = True

                    # Verify
                    verify_ctx = {"elements": elements, "target": target}
                    if op.action == "read":
                        verify_ctx["read_text"] = text
                    if self.verification_waiter is not None:
                        timeout = min(
                            max(0.1, op.verification_timeout),
                            max(0.1, self.time_guard.remaining_op_time()),
                        )
                        result = await self.verification_waiter.wait_for(
                            lambda: self.verifier.verify(op, verify_ctx),
                            key=f"{op.action}:{op.verify_method or 'default'}",
                            timeout=timeout,
                        )
                    else:
                        result = self.verifier.verify(op, verify_ctx)
                    result.action_executed = True

                    if result.success:
                        self.health.record_success()
                        self.circuit_breaker.record_success()
                        if self.safe_point is not None:
                            mark_success = getattr(self.safe_point, "record_success", None)
                            if mark_success is not None:
                                mark_success()
                        result.latency_ms = (_time.monotonic() - t0) * 1000
                        result.retries = attempt
                        return result

                    # Failed — record and rollback
                    self.health.record_failure(result.error or "verification failed")
                    self.circuit_breaker.record_non_timeout_failure(result.error or "")
                    if self.safe_point is not None:
                        snap = self.safe_point.rollback(result.error or "")
                        if not self.safe_point.can_recover():
                            return OperationResult(
                                success=False, operation=op,
                                error=f"DESKTOP_CONTROL_FAILED: [{snap.window_class}] {op.action} {op.element_label} — {result.error}",
                                retries=attempt,
                                latency_ms=(_time.monotonic() - t0) * 1000,
                                action_executed=True,
                            )

                    if not op.idempotent:
                        result.retries = attempt
                        result.latency_ms = (_time.monotonic() - t0) * 1000
                        result.action_executed = True
                        return result

                else:
                    # Untargeted operation (e.g. navigate, open app)
                    success = False
                    if op.action == "navigate":
                        image = self.capture.fullscreen()
                        context = {"image": image, "expected": op.expected}
                        result = self.verifier.verify(op, context)
                        success = result.success
                    if success:
                        self.health.record_success()
                        self.circuit_breaker.record_success()
                        if self.safe_point is not None:
                            mark_success = getattr(self.safe_point, "record_success", None)
                            if mark_success is not None:
                                mark_success()
                        return OperationResult(
                            success=True, operation=op,
                            method_used="vision",
                            latency_ms=(_time.monotonic() - t0) * 1000,
                        )

                    self.health.record_failure(op.action + " navigation failed")

            except Exception as exc:
                self.health.record_failure(str(exc))
                if isinstance(exc, TimeoutError) or exc.__class__.__name__ == "OperationTimeout":
                    self.circuit_breaker.record_timeout()
                else:
                    self.circuit_breaker.record_non_timeout_failure(str(exc))
                if self.safe_point is not None and not self.safe_point.can_recover():
                    return OperationResult(
                        success=False, operation=op,
                        error=f"DESKTOP_CONTROL_FAILED: {op.action} — {exc}",
                        latency_ms=(_time.monotonic() - t0) * 1000,
                    )

        # Exhausted retries
        return OperationResult(
            success=False, operation=op,
            error=f"DESKTOP_CONTROL_FAILED after {op.max_retries + 1} attempts",
            retries=op.max_retries + 1,
            latency_ms=(_time.monotonic() - t0) * 1000,
            action_executed=action_executed_any,
        )

    def can_proceed(self) -> bool:
        """Check all shields before attempting any operation."""
        if not self.health.can_operate():
            return False
        if not self.circuit_breaker.allow_call():
            return False
        return True


# ═══════════════════════════════════════════════════════════════════════════
# Type aliases for plugin registration
# ═══════════════════════════════════════════════════════════════════════════

# A factory that produces a strategy instance given config
StrategyFactory = Callable[[dict[str, Any]], Any]

# Registry of available strategy implementations
STRATEGY_REGISTRY: dict[str, dict[str, StrategyFactory]] = {
    "annotator": {},
    "operator": {},
    "verifier": {},
    "cross_validator": {},
}


def register_strategy(category: str, name: str):
    """Decorator to register a strategy implementation.

    Usage:
        @register_strategy("annotator", "uia_som")
        class UIASOMAnnotator:
            ...
    """
    def decorator(factory: StrategyFactory) -> StrategyFactory:
        STRATEGY_REGISTRY.setdefault(category, {})[name] = factory
        return factory
    return decorator


def resolve_strategy(category: str, name: str, config: dict[str, Any] = None) -> Any:
    """Instantiate a strategy by category and name."""
    if config is None:
        config = {}
    factory = STRATEGY_REGISTRY.get(category, {}).get(name)
    if factory is None:
        raise KeyError(f"Unknown strategy: {category}/{name}")
    return factory(config)


__all__ = [
    # Domain
    "DegradationLevel", "CircuitState", "VerifyResult", "AnchorHeartbeat",
    "UIElement", "Operation", "OperationResult", "EnvSnapshot",
    "SafePointSnapshot",
    # Infrastructure
    "TimeSource", "HashEngine",
    # Pipeline stages
    "ImageCapture", "SOMAnnotator", "ElementOperator", "Verifier",
    "VerificationWaiter",
    "CrossValidator",
    # Shields
    "HealthMonitor", "HealthObserver", "TimeGuard", "CircuitBreaker",
    "EnvDetector", "SafePoint",
    # Orchestration
    "Pipeline",
    # Plugin
    "STRATEGY_REGISTRY", "register_strategy", "resolve_strategy",
]
