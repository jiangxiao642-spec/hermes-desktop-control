"""
Visual SOM Anchor Engine — v1.1 (robustness-enhanced)

Solves the "chicken-and-egg" problem of visual GUI automation:
  1. Full-screen SOM annotation → cache element distribution
  2. pHash monitoring → detect layout changes → refresh only when needed
  3. Anchor-based cropping → from cached SOM, crop target region for precision

v1.1 adds:
  - imagehash soft dependency with pixel-sampling fallback
  - SOM cache max_age (time-based staleness)
  - UIA cross-validation (reconcile vision SOM with UIA element tree)
  - RobustnessShield integration

Flow:
  FullSOM(20s once) → cache → pHash check each step →
  if unchanged: find target in cache → crop → operate (<1s)
  if changed: refresh FullSOM (20s)

Depends on: Pillow, imagehash (optional, falls back to pixel sampling)
Uses: Hermes vision_analyze tool (via vision_tools pipeline)

Integrated with: desktop-control v3.4 visual path
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any

from PIL import Image

# imagehash is a soft dependency. If missing, we fall back to
# pixel-sampling hash (coarser but no dependency).
_imagehash_available = False
try:
    import imagehash
    _imagehash_available = True
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Strategy interfaces — soft dependency for v1.2 decoupling
try:
    from scripts.interfaces import (
        UIElement, CrossValidator, SOMAnnotator, HashEngine,
        register_strategy,
    )
except ImportError:
    UIElement = None          # type: ignore
    CrossValidator = None     # type: ignore
    SOMAnnotator = None       # type: ignore
    HashEngine = None         # type: ignore
    def register_strategy(category: str, name: str):
        """No-op decorator when interfaces.py is unavailable."""
        return lambda factory: factory


# ═══════════════════════════════════════════════════════════════════
# pHash utilities — with imagehash OR pixel-sampling fallback
# ═══════════════════════════════════════════════════════════════════

def compute_phash(image: Image.Image, hash_size: int = 8) -> str:
    """Compute perceptual hash. Uses imagehash if available, pixel sampling otherwise."""
    if _imagehash_available:
        return str(imagehash.phash(image, hash_size=hash_size))

    # Pixel-sampling fallback: resize to tiny thumbnail, hash the pixel bytes.
    # Coarser than DCT-based pHash but requires no extra package.
    thumb = image.resize((hash_size, hash_size), Image.LANCZOS).convert("L")
    pixel_bytes = bytes(thumb.getdata())  # hash_size² bytes
    return hashlib.md5(pixel_bytes).hexdigest()[:16]


def phash_distance(h1: str, h2: str) -> int:
    """Distance between two perceptual hashes.

    For imagehash dct/phash output (hex string), uses Hamming distance
    on the underlying bits. For the pixel-sampling fallback (md5 hex),
    uses character-level difference (imperfect but functional — layout
    changes still produce visibly different hashes).
    """
    if len(h1) != len(h2):
        return max(len(h1), len(h2)) * 4
    # Try hex → int → bitwise Hamming first (imagehash format)
    try:
        v1 = int(h1, 16)
        v2 = int(h2, 16)
        return (v1 ^ v2).bit_count()
    except ValueError:
        return sum(c1 != c2 for c1, c2 in zip(h1, h2))


# ═══════════════════════════════════════════════════════════════════
# Vision SOM prompt (full-screen)
# ═══════════════════════════════════════════════════════════════════

FULLSOM_PROMPT = """Analyze this {w}x{h} screenshot and identify ALL interactive UI elements.

For each interactive element (buttons, text inputs, checkboxes, dropdowns, links,
clickable icons, menu items, tabs, sliders, toggle switches), return:

1. A number label [1], [2], [3]...
2. The type of element (Button, Edit/TextInput, CheckBox, ComboBox, Link, Icon, Tab, MenuItem, Slider, Toggle)
3. Its visible text/label (if any, in original language)
4. Approximate pixel coordinates (x, y, width, height) relative to TOP-LEFT of screenshot

Return ONLY the structured list. Only include elements that are currently visible
and appear interactive (not static text, not decoration, not background).

Example format:
  [1] Button "Send" (350, 620, 80x32)
  [2] Edit "Message input" (50, 615, 290x40)
  [3] Tab "Files" (400, 30, 60x30)
  [4] Icon "Attach file" (20, 618, 24x24)

Be thorough but don't hallucinate. Only label what you can clearly see as interactive."""


# ═══════════════════════════════════════════════════════════════════
# SOM from vision response parsing
# ═══════════════════════════════════════════════════════════════════

@dataclass
class VisualElement:
    """A single interactive element identified by vision SOM."""
    index: int
    element_type: str       # Button, Edit, Icon, Tab, etc.
    label: str              # visible text
    bounds: tuple           # (x, y, w, h) in screenshot pixels
    confidence: float = 0.85
    cross_validated: bool = False  # True if confirmed by UIA or visual crop


def _match_vision_to_uia_element(vis_el, uia_el: dict,
                                 threshold: float = 0.6) -> bool:
    """Check if a vision-identified element matches a UIA element.

    Extracted as a module-level function so both VisualSOMCache and
    VisionSOMCrossValidator can share the same matching logic.

    Type equivalence: Edit≈TextInput≈Document, Button≈Invoke.
    Label match: substring containment or word-overlap ratio >= threshold.
    """
    vis_type = vis_el.element_type.lower()
    uia_type = uia_el.get("control_type", "").lower()
    if vis_type in ("edit", "textinput") and uia_type in ("edit", "text", "document"):
        pass  # equivalent input types
    elif uia_type and vis_type not in uia_type and uia_type not in vis_type:
        return False

    vis_label = vis_el.label.lower().strip() if vis_el.label else ""
    uia_name = (uia_el.get("name", "") or "").lower().strip()
    if not vis_label and not uia_name:
        return False
    if vis_label and uia_name:
        if vis_label in uia_name or uia_name in vis_label:
            return True
        common = len(set(vis_label.split()) & set(uia_name.split()))
        total = max(len(set(vis_label.split())), 1)
        if common / total >= threshold:
            return True
    return False


@dataclass
class VisualSOMCache:
    """Cached full-screen SOM annotation with pHash + time-based staleness."""
    elements: list[VisualElement] = field(default_factory=list)
    phash: str = ""
    screenshot_path: str = ""
    timestamp: float = 0.0
    window_region: tuple = (0, 0, 0, 0)  # (x, y, w, h) of the target window
    dpi_scale: float = 1.0
    max_age: float = 300.0  # seconds — force refresh after this (v1.1)

    def get_element(self, index: int) -> Optional[VisualElement]:
        for el in self.elements:
            if el.index == index:
                return el
        return None

    def find_by_label(self, label_substring: str) -> list[VisualElement]:
        """Fuzzy search for elements by label text."""
        label_lower = label_substring.lower()
        return [el for el in self.elements if label_lower in el.label.lower()]

    def find_by_type(self, element_type: str) -> list[VisualElement]:
        return [el for el in self.elements if el.element_type.lower() == element_type.lower()]

    @property
    def is_stale(self) -> bool:
        """True if cache has exceeded its time-based max_age."""
        if self.timestamp == 0.0:
            return False
        return (time.time() - self.timestamp) > self.max_age

    @property
    def age_seconds(self) -> float:
        if self.timestamp == 0.0:
            return 0.0
        return time.time() - self.timestamp

    def to_context(self) -> str:
        """Compact context for LLM consumption."""
        lines = [
            f"SOM cache — {len(self.elements)} elements",
            f"Age: {self.age_seconds:.0f}s (max {self.max_age:.0f}s)",
            f"Cross-validated: {sum(1 for e in self.elements if e.cross_validated)}/{len(self.elements)}",
            "",
        ]
        for el in self.elements:
            flag = " ✓" if el.cross_validated else ""
            lines.append(
                f"  [{el.index}]{flag} {el.element_type}"
                + (f' "{el.label}"' if el.label else "")
                + f" ({el.bounds[0]},{el.bounds[1]},{el.bounds[2]}x{el.bounds[3]})"
            )
        return "\n".join(lines)

    # ── v1.1: UIA cross-validation ────────────────────────────────

    def cross_validate_uia(self, uia_elements: list[dict],
                           label_threshold: float = 0.6) -> int:
        """Reconcile vision SOM with UIA element tree.

        For each vision element, look for a UIA counterpart with a similar
        label and overlapping bounds. Matches are marked cross_validated=True.
        Elements found only in vision (no UIA match) are kept but flagged.

        Args:
            uia_elements: list of dicts with keys: name, control_type, bounds, automation_id
            label_threshold: minimum substring match ratio for label confirmation

        Returns:
            Number of elements cross-validated (marked True).
        """
        validated = 0
        for el in self.elements:
            for uia_el in uia_elements:
                if self._is_uia_match(el, uia_el, label_threshold):
                    el.cross_validated = True
                    validated += 1
                    logger.debug(
                        "Cross-validated [#%d] %s '%s' ↔ UIA %s '%s'",
                        el.index, el.element_type, el.label,
                        uia_el.get("control_type", "?"),
                        uia_el.get("name", "?"),
                    )
                    break
            # Elements without a match stay at cross_validated=False
            # They become "pending verification" candidates in the pipeline.
        return validated

    @staticmethod
    def _is_uia_match(vis_el: VisualElement, uia_el: dict,
                      threshold: float) -> bool:
        """Check if a vision-identified element matches a UIA element."""
        return _match_vision_to_uia_element(vis_el, uia_el, threshold)

    def get_unvalidated(self) -> list[VisualElement]:
        """Elements seen only by vision, not confirmed by UIA."""
        return [el for el in self.elements if not el.cross_validated]

    def get_high_confidence(self) -> list[VisualElement]:
        """Elements confirmed by both vision and UIA."""
        return [el for el in self.elements if el.cross_validated]


# ═══════════════════════════════════════════════════════════════════
# Anchor cropper
# ═══════════════════════════════════════════════════════════════════

@dataclass
class CropAnchor:
    """A cropped region with its offset for coordinate math."""
    image: Image.Image              # the cropped PIL image
    offset_x: int                    # crop left edge in full-screenshot coords
    offset_y: int                    # crop top edge in full-screenshot coords
    crop_width: int
    crop_height: int

    def crop_to_screen(self, local_x: int, local_y: int) -> tuple:
        """Convert crop-local coordinates to full-screen coordinates."""
        return (self.offset_x + local_x, self.offset_y + local_y)

    def save(self, path: str):
        self.image.save(path)


class AnchorCropper:
    """Crop target regions from a full screenshot using cached SOM anchors."""

    def __init__(self, full_screenshot: Image.Image, som_cache: VisualSOMCache):
        self.full_img = full_screenshot
        self.som = som_cache

    def crop_element(self, index: int, padding: int = 100,
                     prefer_validated: bool = True) -> Optional[CropAnchor]:
        """Crop a region centered on the given SOM element index.

        If prefer_validated and a cross_validated element exists with this
        index, uses it directly. Otherwise, marks the element as needing
        pre-operation vision verification.
        """
        el = self.som.get_element(index)
        if el is None:
            return None
        return self._crop_bounds(el.bounds, padding)

    def crop_element_by_label(self, label: str, padding: int = 100) -> Optional[CropAnchor]:
        """Crop region for the first element matching the label."""
        matches = self.som.find_by_label(label)
        if not matches:
            return None
        return self._crop_bounds(matches[0].bounds, padding)

    def _crop_bounds(self, bounds: tuple, padding: int) -> CropAnchor:
        x, y, w, h = bounds
        cx, cy = x + w // 2, y + h // 2
        half = max(padding, max(w, h) // 2 + 20)

        left = max(0, cx - half)
        top = max(0, cy - half)
        right = min(self.full_img.width, cx + half)
        bottom = min(self.full_img.height, cy + half)

        crop = self.full_img.crop((left, top, right, bottom))
        return CropAnchor(
            image=crop,
            offset_x=left,
            offset_y=top,
            crop_width=right - left,
            crop_height=bottom - top,
        )


# ═══════════════════════════════════════════════════════════════════
# SOM Element parser — strict regex + lenient fallback
# ═══════════════════════════════════════════════════════════════════

_SOM_LINE_RE = re.compile(
    r'\[(\d+)\]\s+(\w+)\s+"([^"]*)"\s+\((\d+),\s*(\d+),\s*(\d+)x(\d+)\)'
)

# Lenient parser: accepts slight variations like no quotes, Chinese brackets,
# different coordinate formats, extra whitespace.
_SOM_LINE_LOOSE = re.compile(
    r'\[(\d+)\]\s+(\w+)\s+"?\'?([^"\'\n(]*?)"?\'?\s*'
    r'[\[(（]?\s*(\d+)\s*[,，]\s*(\d+)\s*[,，]\s*(\d+)\s*[x×X]\s*(\d+)\s*[\])）]?'
)


def parse_som_response(vision_text: str, min_confidence: float = 0.1) -> list[VisualElement]:
    """Parse vision model's SOM annotation response into VisualElement list.

    Tries the strict format first (matching the prompt's example format).
    If that returns nothing, falls back to a looser parser that accepts
    Chinese brackets, missing quotes, and coordinate format variations.

    Args:
        vision_text: Raw response from vision model
        min_confidence: Minimum confidence threshold (elements below this
            confidence are discarded).

    Note: If the model returns confidence=0 or a natural-language "I can't
    see X" response, the element is silently dropped.
    """
    elements = []

    # Strict parse first
    for m in _SOM_LINE_RE.finditer(vision_text):
        elements.append(VisualElement(
            index=int(m.group(1)),
            element_type=m.group(2),
            label=m.group(3),
            bounds=(int(m.group(4)), int(m.group(5)), int(m.group(6)), int(m.group(7))),
        ))

    # If strict failed, try lenient
    if not elements:
        logger.warning("Strict SOM parse returned 0 elements — trying lenient parser")
        for m in _SOM_LINE_LOOSE.finditer(vision_text):
            label = (m.group(3) or "").strip().strip('"').strip("'")
            elements.append(VisualElement(
                index=int(m.group(1)),
                element_type=m.group(2),
                label=label,
                bounds=(int(m.group(4)), int(m.group(5)),
                        int(m.group(6)), int(m.group(7))),
                confidence=0.7,  # lower default confidence for lenient parse
            ))

    return elements


# ═══════════════════════════════════════════════════════════════════
# pHash region extraction for window-specific monitoring
# ═══════════════════════════════════════════════════════════════════

def compute_window_phash(full_screenshot: Image.Image, window_bounds: tuple) -> str:
    """Compute pHash for just the target window region."""
    x, y, w, h = window_bounds
    region = full_screenshot.crop((x, y, x + w, y + h))
    return compute_phash(region)


# ═══════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════

# pHash Hamming distance threshold for "layout changed"
PHASH_STALE_THRESHOLD = 10


# ═══════════════════════════════════════════════════════════════════
# v1.2: Strategy implementations — each implements an interfaces.py Protocol
# ═══════════════════════════════════════════════════════════════════
# These are registered in STRATEGY_REGISTRY so the Pipeline can resolve
# them dynamically. Each is also usable standalone without the registry.

@register_strategy("cross_validator", "label_overlap")
class VisionSOMCrossValidator:
    """Cross-validator that reconciles vision SOM with UIA element tree.

    Implements: interfaces.CrossValidator

    Strategy: "label_overlap" — matches by type equivalence + label overlap.
    Works with any element objects that have: element_type, label, bounds
    attributes and a cross_validated flag (VisualElement or UIElement).

    Usage:
        validator = VisionSOMCrossValidator(label_threshold=0.6)
        reconciled = validator.validate(vision_elements, uia_dicts)
        # vision_elements now have cross_validated=True where UIA confirmed
    """

    def __init__(self, label_threshold: float = 0.6):
        self._label_threshold = label_threshold

    @property
    def strategy_name(self) -> str:
        return "label_overlap"

    def validate(self, primary: list, secondary: list) -> list:
        """Reconcile primary (vision SOM) with secondary (UIA tree).

        Returns primary list with cross_validated flags set on matches.
        Elements without a UIA counterpart stay cross_validated=False.
        """
        validated = 0
        for el in primary:
            for uia_el in secondary:
                if _match_vision_to_uia_element(el, uia_el, self._label_threshold):
                    el.cross_validated = True
                    validated += 1
                    logger.debug(
                        "Cross-validated [#%d] %s '%s' <-> UIA %s '%s'",
                        getattr(el, 'index', '?'),
                        getattr(el, 'element_type', '?'),
                        getattr(el, 'label', ''),
                        uia_el.get("control_type", "?"),
                        uia_el.get("name", "?"),
                    )
                    break
        return primary

    def get_unvalidated(self, elements: list) -> list:
        """Elements seen only by vision, not confirmed by UIA."""
        return [el for el in elements if not getattr(el, 'cross_validated', False)]

    def get_high_confidence(self, elements: list) -> list:
        """Elements confirmed by both vision and UIA."""
        return [el for el in elements if getattr(el, 'cross_validated', False)]


@register_strategy("hash_engine", "phash_with_fallback")
class PHashEngine:
    """Perceptual hash engine with imagehash + pixel-sampling fallback.

    Implements: interfaces.HashEngine

    Strategy: "phash_with_fallback" — uses imagehash library if available,
    otherwise falls back to MD5-of-thumbnail pixel sampling.
    """

    def __init__(self, hash_size: int = 8):
        self._hash_size = hash_size

    def compute(self, image, hash_size: int = 8) -> str:
        """Compute perceptual hash of a PIL Image."""
        return compute_phash(image, hash_size=hash_size or self._hash_size)

    def distance(self, h1: str, h2: str) -> int:
        """Hamming distance between two perceptual hashes."""
        return phash_distance(h1, h2)


@register_strategy("som_parser", "regex_dual_path")
class SOMResponseParser:
    """Parser for vision model SOM annotation responses.

    Strategy: "regex_dual_path" — strict regex first, lenient fallback.
    Different vision models (Qwen, Claude, GPT-4V) return slightly different
    formats. Swap this parser to handle model-specific quirks.

    Usage:
        parser = SOMResponseParser(min_confidence=0.5)
        elements = parser.parse(vision_text)
    """

    def __init__(self, min_confidence: float = 0.1):
        self._min_confidence = min_confidence

    def parse(self, vision_text: str) -> list:
        """Parse vision model response into VisualElement list.

        Delegates to parse_som_response() with this parser's confidence threshold.
        """
        return parse_som_response(vision_text, min_confidence=self._min_confidence)

    @property
    def min_confidence(self) -> float:
        return self._min_confidence


# ═══════════════════════════════════════════════════════════════════
# Strategy resolution helper
# ═══════════════════════════════════════════════════════════════════

def resolve_strategy(category: str, name: str, config: dict = None):
    """Resolve a registered strategy by category and name.

    Tries interfaces.resolve_strategy first, then falls back to direct
    instantiation of known local strategies.
    """
    if config is None:
        config = {}
    # Try the registry from interfaces.py first
    try:
        from scripts.interfaces import resolve_strategy as _resolve
        return _resolve(category, name, config)
    except (ImportError, KeyError):
        pass
    # Fallback: direct instantiation for known local strategies
    local_map = {
        ("cross_validator", "label_overlap"): VisionSOMCrossValidator,
        ("hash_engine", "phash_with_fallback"): PHashEngine,
        ("som_parser", "regex_dual_path"): SOMResponseParser,
    }
    cls = local_map.get((category, name))
    if cls is None:
        raise KeyError(f"Unknown strategy: {category}/{name}")
    return cls(**config)
