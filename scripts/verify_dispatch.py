"""
desktop-control verification dispatch layer
plugs VerifyResult + AnchorHeartbeat into the actual execution pipeline
"""

import subprocess
import json
import time
from pathlib import Path
from dataclasses import dataclass

# imports from our own package
from scripts.robustness import VerifyResult, AnchorHeartbeat, SystemTime


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
# Verification escalation — UNCERTAIN → heavier layer
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


# Escalation chain: cheapest → most expensive
ESCALATION_CHAIN = [VerifyWithUIA, VerifyWithpHash, VerifyWithOCR, VerifyWithVision]


def escalate_verification(
    current_idx: int,
    verification_fn,
    *args,
    **kwargs,
) -> tuple[VerifyResult, int]:
    """If current result is UNCERTAIN, try next heavier layer.

    Returns (final_result, layer_index_used).
    """
    layer = ESCALATION_CHAIN[min(current_idx, len(ESCALATION_CHAIN) - 1)]
    result = verification_fn(layer, *args, **kwargs)

    if result == VerifyResult.PASS or result == VerifyResult.FAIL:
        return result, current_idx

    # UNCERTAIN — escalate
    next_idx = current_idx + 1
    if next_idx >= len(ESCALATION_CHAIN):
        return VerifyResult.FAIL, current_idx  # exhausted all layers

    return escalate_verification(next_idx, verification_fn, *args, **kwargs)


# ═══════════════════════════════════════════════════════════════
# Anchor heartbeat — pre-operation check
# ═══════════════════════════════════════════════════════════════


def check_anchors(app_name: str, uia_snap_path: str) -> AnchorHeartbeat:
    """Read UIA snap file and count how many anchor elements are present.

    Snap file format: first line is header like '  UIA elements: 2003'
    Actual element scan happens in PowerShell via bridge.
    Here we do a lightweight parse of the cached snap.
    """
    heartbeat = AnchorHeartbeat()

    anchors = ANCHORS.get(app_name)
    if not anchors:
        heartbeat.set_anchors([])
        return heartbeat

    heartbeat.set_anchors(anchors)

    try:
        snap_text = Path(uia_snap_path).read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        heartbeat.evaluate(0)
        return heartbeat

    found = 0
    for name, ctrl_type in anchors:
        if name.lower() in snap_text.lower():
            found += 1

    heartbeat.evaluate(found)
    return heartbeat


def anchor_ok(app_name: str, uia_snap_path: str) -> bool:
    """Quick pre-op check: are key controls alive?"""
    hb = check_anchors(app_name, uia_snap_path)
    return hb.evaluate(len(hb._anchors)) == VerifyResult.PASS


# ═══════════════════════════════════════════════════════════════
# Utility: last snap timestamp
# ═══════════════════════════════════════════════════════════════


def snap_age_seconds(uia_snap_path: str) -> float:
    """How old is the UIA snap file? Used for cache freshness checks."""
    try:
        return time.time() - Path(uia_snap_path).stat().st_mtime
    except FileNotFoundError:
        return float("inf")

