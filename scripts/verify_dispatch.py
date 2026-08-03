"""
desktop-control verification dispatch layer
plugs VerifyResult + AnchorHeartbeat into the actual execution pipeline
"""

import time
from pathlib import Path
from dataclasses import dataclass

# Domain types now live in interfaces (single source of truth)
from scripts.interfaces import VerifyResult, AnchorHeartbeat


# ═══════════════════════════════════════════════════════════════
# Anchor definitions per application
# ═══════════════════════════════════════════════════════════════

ANCHORS = {
    "Claude Desktop (EXE)": [
        ("Write your prompt to Claude", "Edit"),
        ("Send message", "Button"),
    ],
    "OpenClaw Desktop": [
        ("Message Assistant (Enter to send)", "Edit"),
    ],
}


# ═══════════════════════════════════════════════════════════════
# Verification escalation — UNCERTAIN -> heavier layer
# ═══════════════════════════════════════════════════════════════

@dataclass
class VerifyWithUIA:
    """Check UIA element state — fastest (~0ms for attributes)."""

    @staticmethod
    def label() -> str:
        return "UIA"

    @staticmethod
    def cost_ms() -> int:
        return 0  # instantaneous attribute read


@dataclass
class VerifyWithpHash:
    """Compare perceptual hash — ~400ms, catches layout changes."""

    @staticmethod
    def label() -> str:
        return "pHash"

    @staticmethod
    def cost_ms() -> int:
        return 400


@dataclass
class VerifyWithOCR:
    """OCR text verification — ~500ms, catches content changes."""

    @staticmethod
    def label() -> str:
        return "OCR"

    @staticmethod
    def cost_ms() -> int:
        return 500


@dataclass
class VerifyWithVision:
    """Cloud vision model — 2-5s, final escalation."""

    @staticmethod
    def label() -> str:
        return "vision"

    @staticmethod
    def cost_ms() -> int:
        return 3000


# Escalation chain: cheapest -> most expensive
ESCALATION_CHAIN = [VerifyWithUIA, VerifyWithpHash, VerifyWithOCR, VerifyWithVision]


def escalate_verification(
    verification_fn,
    *args,
    **kwargs,
) -> tuple[VerifyResult, int]:
    """If result is UNCERTAIN, try the next heavier verification layer.

    Iterates through ESCALATION_CHAIN (loop, not recursion).
    Returns (final_result, layer_index_used).
    """
    for idx in range(len(ESCALATION_CHAIN)):
        layer = ESCALATION_CHAIN[idx]
        result = verification_fn(layer, *args, **kwargs)

        if result in (VerifyResult.PASS, VerifyResult.FAIL):
            return result, idx

        # UNCERTAIN — continue to next layer
        continue

    # Exhausted all layers
    return VerifyResult.FAIL, len(ESCALATION_CHAIN) - 1


# ═══════════════════════════════════════════════════════════════
# Anchor heartbeat — pre-operation check
# ═══════════════════════════════════════════════════════════════


def _count_anchors_in_snap(anchors: list, uia_snap_path: str) -> int:
    """Count how many anchor elements appear in the UIA snap file.

    Returns the count (0 if file missing). Does NOT mutate any state.
    """
    try:
        snap_text = Path(uia_snap_path).read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return 0

    found = 0
    snap_lower = snap_text.lower()
    for name, _ctrl_type in anchors:
        if name.lower() in snap_lower:
            found += 1
    return found


def check_anchors(app_name: str, uia_snap_path: str) -> AnchorHeartbeat:
    """Read UIA snap file, evaluate anchor presence, return heartbeat.

    Calls evaluate() exactly once — the caller gets a fully-evaluated heartbeat.
    """
    heartbeat = AnchorHeartbeat()

    anchors = ANCHORS.get(app_name)
    if not anchors:
        heartbeat.set_anchors([])
        heartbeat.evaluate(0)
        return heartbeat

    heartbeat.set_anchors(anchors)
    found = _count_anchors_in_snap(anchors, uia_snap_path)
    heartbeat.evaluate(found)
    return heartbeat


def anchor_ok(app_name: str, uia_snap_path: str) -> bool:
    """Quick pre-op check: are key controls alive?

    Delegates to check_anchors and reads the result — no double-evaluate.
    """
    hb = check_anchors(app_name, uia_snap_path)
    return hb.is_alive and len(hb._anchors) > 0


# ═══════════════════════════════════════════════════════════════
# Utility: last snap timestamp
# ═══════════════════════════════════════════════════════════════


def snap_age_seconds(uia_snap_path: str) -> float:
    """How old is the UIA snap file? Used for cache freshness checks."""
    try:
        return time.time() - Path(uia_snap_path).stat().st_mtime
    except FileNotFoundError:
        return float("inf")
