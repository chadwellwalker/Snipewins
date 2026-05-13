"""
Optional image-aware comp verification hooks.

Default-safe: no CV/OCR. Callers can register a custom scorer later.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

# Optional override: (target_item, comp_item) -> (score 0..1 or None, status str)
_VISUAL_SIGNAL_FN: Optional[
    Callable[[Optional[Dict[str, Any]], Dict[str, Any]], Tuple[Optional[float], str]]
] = None


def register_visual_match_hook(
    fn: Optional[
        Callable[[Optional[Dict[str, Any]], Dict[str, Any]], Tuple[Optional[float], str]]
    ],
) -> None:
    """Register a custom visual match hook, or pass None to clear."""
    global _VISUAL_SIGNAL_FN
    _VISUAL_SIGNAL_FN = fn


def _image_urls(item: Optional[Dict[str, Any]]) -> List[str]:
    if not item or not isinstance(item, dict):
        return []
    out: List[str] = []
    img = item.get("image")
    if isinstance(img, dict):
        u = img.get("imageUrl") or img.get("url")
        if u:
            out.append(str(u).strip())
    elif isinstance(img, str) and img.strip():
        out.append(img.strip())
    for k in ("thumbnailImages", "additionalImages"):
        block = item.get(k)
        if isinstance(block, list):
            for el in block:
                if isinstance(el, dict):
                    u = el.get("imageUrl") or el.get("url")
                    if u:
                        out.append(str(u).strip())
    return [u for u in out if u]


def get_visual_match_signal(
    target_item: Optional[Dict[str, Any]],
    comp_item: Dict[str, Any],
) -> Tuple[Optional[float], str]:
    """
    Returns (visual_match_score, status).

    status values:
      unavailable_no_target — no target listing dict provided
      skipped_no_images — one side missing usable image URL
      unavailable_no_hook — custom hook not registered (default)
      used_custom_hook — score produced by registered hook
    """
    if _VISUAL_SIGNAL_FN is not None:
        return _VISUAL_SIGNAL_FN(target_item, comp_item)

    if target_item is None:
        return None, "unavailable_no_target"

    tu = _image_urls(target_item)
    cu = _image_urls(comp_item)
    if not tu or not cu:
        return None, "skipped_no_images"

    return None, "unavailable_no_hook"


def verify_comp_visual_match(
    target_item: Optional[Dict[str, Any]],
    comp_item: Dict[str, Any],
    *,
    min_score: float = 0.72,
) -> bool:
    """Strict gate for future use; today returns False unless a hook supplies a score."""
    score, status = get_visual_match_signal(target_item, comp_item)
    if score is None:
        return False
    return status == "used_custom_hook" and score >= min_score
