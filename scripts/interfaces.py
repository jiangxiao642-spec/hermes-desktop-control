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
        cross_validator: Optional[CrossValidator] = None,
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
        self.cross_validator = cross_validator
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
        """Run a single operation through the full pipeline."""
        raise NotImplementedError("Pipeline.execute — implement in v3.5")

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
    "DegradationLevel", "CircuitState",
    "UIElement", "Operation", "OperationResult", "EnvSnapshot",
    "SafePointSnapshot",
    # Infrastructure
    "TimeSource", "HashEngine",
    # Pipeline stages
    "ImageCapture", "SOMAnnotator", "ElementOperator", "Verifier",
    "CrossValidator",
    # Shields
    "HealthMonitor", "HealthObserver", "TimeGuard", "CircuitBreaker",
    "EnvDetector", "SafePoint",
    # Orchestration
    "Pipeline",
    # Plugin
    "STRATEGY_REGISTRY", "register_strategy", "resolve_strategy",
]
