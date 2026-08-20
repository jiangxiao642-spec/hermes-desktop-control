import asyncio
import tempfile
import unittest
from pathlib import Path

import interfaces
import robustness
import verify_dispatch
import visual_som_anchor
from engine import CallbackRecoveryExecutor, DesktopControlEngine, TargetContext
from waiting import AdaptiveWaiter


class AnchorHeartbeatTests(unittest.TestCase):
    def setUp(self):
        verify_dispatch.reset_anchor_heartbeat()

    def test_missing_anchors_persist_across_checks(self):
        missing = str(Path(tempfile.gettempdir()) / "missing-uia-snap.txt")
        self.assertTrue(verify_dispatch.anchor_ok("OpenClaw Desktop", missing))
        self.assertFalse(verify_dispatch.anchor_ok("OpenClaw Desktop", missing))


class SafePointTests(unittest.TestCase):
    def test_checkpoint_does_not_reset_failed_retry_streak(self):
        manager = robustness.SafePointManager()
        manager.checkpoint(action="click")
        manager.rollback("first failure")
        manager.checkpoint(action="click")
        manager.rollback("second failure")
        self.assertEqual(manager._rollback_count, 2)
        manager.record_success()
        self.assertEqual(manager._rollback_count, 0)


class CrossValidationTests(unittest.TestCase):
    def test_validator_accepts_uielement_objects(self):
        primary = [visual_som_anchor.VisualElement(1, "Button", "Send", (0, 0, 10, 10))]
        secondary = [interfaces.UIElement(1, "Button", "Send", (0, 0, 10, 10), source="uia")]
        result = visual_som_anchor.VisionSOMCrossValidator().validate(primary, secondary)
        self.assertTrue(result[0].cross_validated)


class _Capture:
    current_env = interfaces.EnvSnapshot(1920, 1080, 1.0, 1)

    def fullscreen(self):
        return object()


class _Annotator:
    def __init__(self, elements):
        self.elements = elements
        self.calls = 0

    def annotate(self, _image):
        self.calls += 1
        return self.elements


class _Operator:
    def __init__(self):
        self.clicks = 0

    def click(self, _target):
        self.clicks += 1
        return False

    def type_text(self, _target, _text):
        return False

    def read_text(self, _target):
        return ""


class _Verifier:
    def __init__(self):
        self.calls = 0

    def verify(self, op, _context):
        self.calls += 1
        return interfaces.OperationResult(True, op)


class _Health:
    level = interfaces.DegradationLevel.NORMAL

    def can_operate(self):
        return True

    def record_failure(self, *_args, **_kwargs):
        return self.level

    def record_success(self):
        return self.level


class _TimeGuard:
    def start_operation(self):
        pass

    def check_timeout(self):
        return True

    def remaining_op_time(self):
        return 30.0


class _Circuit:
    state = interfaces.CircuitState.CLOSED

    def allow_call(self):
        return True

    def record_non_timeout_failure(self, _error):
        pass

    def record_timeout(self):
        raise AssertionError("ordinary operator failures are not timeouts")

    def record_success(self):
        pass


class _EnvDetector:
    def capture(self, *_args):
        return False


class PipelineTests(unittest.TestCase):
    def test_operator_failure_cannot_be_verified_as_success(self):
        primary = _Annotator([interfaces.UIElement(1, "Button", "Send", (0, 0, 10, 10))])
        verifier = _Verifier()
        pipeline = interfaces.Pipeline(
            capture=_Capture(),
            annotator=primary,
            operator=_Operator(),
            verifier=verifier,
            health=_Health(),
            time_guard=_TimeGuard(),
            circuit_breaker=_Circuit(),
            env_detector=_EnvDetector(),
        )
        result = asyncio.run(pipeline.execute(
            interfaces.Operation(action="click", element_index=1, max_retries=0)
        ))
        self.assertFalse(result.success)
        self.assertEqual(verifier.calls, 0)

    def test_adaptive_verification_polls_without_repeating_action(self):
        primary = _Annotator([interfaces.UIElement(1, "Button", "Send", (0, 0, 10, 10))])

        class PassingOperator(_Operator):
            def click(self, _target):
                self.clicks += 1
                return True

        class EventuallyPasses(_Verifier):
            def verify(self, op, _context):
                self.calls += 1
                return interfaces.OperationResult(self.calls >= 3, op, error="pending")

        operator = PassingOperator()
        verifier = EventuallyPasses()
        pipeline = interfaces.Pipeline(
            capture=_Capture(),
            annotator=primary,
            operator=operator,
            verifier=verifier,
            verification_waiter=AdaptiveWaiter(initial_delay=0.001, max_delay=0.002),
            health=_Health(),
            time_guard=_TimeGuard(),
            circuit_breaker=_Circuit(),
            env_detector=_EnvDetector(),
        )
        result = asyncio.run(pipeline.execute(
            interfaces.Operation(
                action="click", element_index=1, max_retries=0,
                verification_timeout=0.1,
            )
        ))
        self.assertTrue(result.success)
        self.assertEqual(operator.clicks, 1)
        self.assertEqual(verifier.calls, 3)

    def test_cross_validation_uses_distinct_secondary_annotator(self):
        primary = _Annotator([interfaces.UIElement(1, "Button", "Send", (0, 0, 10, 10))])
        secondary = _Annotator([interfaces.UIElement(1, "Button", "Send", (0, 0, 10, 10))])

        class PassingOperator(_Operator):
            def click(self, _target):
                return True

        pipeline = interfaces.Pipeline(
            capture=_Capture(),
            annotator=primary,
            secondary_annotator=secondary,
            cross_validator=visual_som_anchor.VisionSOMCrossValidator(),
            operator=PassingOperator(),
            verifier=_Verifier(),
            health=_Health(),
            time_guard=_TimeGuard(),
            circuit_breaker=_Circuit(),
            env_detector=_EnvDetector(),
        )
        result = asyncio.run(pipeline.execute(
            interfaces.Operation(action="click", element_index=1, max_retries=0)
        ))
        self.assertTrue(result.success)
        self.assertEqual(primary.calls, 1)
        self.assertEqual(secondary.calls, 1)


class EngineTests(unittest.TestCase):
    def test_anchor_failure_runs_recovery_before_pipeline(self):
        class PipelineStub:
            safe_point = None

            def __init__(self):
                self.calls = 0

            async def execute(self, op):
                self.calls += 1
                return interfaces.OperationResult(True, op)

        statuses = [interfaces.VerifyResult.UNCERTAIN, interfaces.VerifyResult.PASS]

        class Heartbeat:
            _anchors = [("Send", "Button")]

            def __init__(self, status):
                self.last_result = status

        def anchor_probe(_app, _path):
            return Heartbeat(statuses.pop(0))

        recovery = CallbackRecoveryExecutor({"reactivate_uia": lambda _target, _reason: True})
        pipeline = PipelineStub()
        engine = DesktopControlEngine(pipeline, recovery=recovery, anchor_probe=anchor_probe)
        target = TargetContext("session", "window", "OpenClaw Desktop", "snap")
        result = asyncio.run(engine.execute(interfaces.Operation("click"), target))
        self.assertTrue(result.success)
        self.assertEqual(pipeline.calls, 1)

    def test_same_window_operations_are_serialized(self):
        class PipelineStub:
            safe_point = None

            def __init__(self):
                self.active = 0
                self.max_active = 0

            async def execute(self, op):
                self.active += 1
                self.max_active = max(self.max_active, self.active)
                await asyncio.sleep(0.005)
                self.active -= 1
                return interfaces.OperationResult(True, op)

        async def run_test():
            pipeline = PipelineStub()
            engine = DesktopControlEngine(pipeline)
            target = TargetContext("session", "window")
            await asyncio.gather(
                engine.execute(interfaces.Operation("read"), target),
                engine.execute(interfaces.Operation("read"), target),
            )
            return pipeline.max_active

        self.assertEqual(asyncio.run(run_test()), 1)


if __name__ == "__main__":
    unittest.main()
