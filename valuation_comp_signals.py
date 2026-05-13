"""
Comp enrichment: condition heuristics, listing-quality penalties, duplicate suppression,
and exactness-tier labels. Title-only where API fields are missing.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from comp_visual_hooks import get_visual_match_signal

_RAW_BAD = re.compile(
    r"\b("
    r"damaged|damage|crease|creased|bent|ding|dented|soft\s*corners?|rounded\s*corners?|"
    r"surface\s*scratch|scratched|poor\s*condition|hp|heavily\s*played|"
    r"trimmed|altered|writing\s*on|ink|stain|torn|tear|warped|water\s*damage"
    r")\b",
    re.I,
)
_GRADED_BAD = re.compile(
    r"\b("
    r"cracked\s*(slab|case|holder)|broken\s*case|resealed|tamper|trimmed|altered|"
    r"miscut|mis-cut|recolor|color\s*added|fake\s*slab|questionable"
    r")\b",
    re.I,
)
_LOT_AMBIGUOUS = re.compile(
    r"\b("
    r"\blot\s+of\b|\blots?\b|\bx\s*\d+\b|\b\d+\s*x\b|\bpair\b|\bduo\b|\bbundle\b|"
    r"\bmulti[-\s]?card\b|\b\d+\s+card\b|\bcomplete\s+set\b|\bteam\s+set\b|"
    r"\byou\s+pick\b|\bpick\s+one\b|\bchoose\b"
    r")\b",
    re.I,
)
_VAGUE_TITLE = re.compile(
    r"\b("
    r"see\s*photos?|see\s*pics?|read\s*description|as\s*is|no\s*returns|"
    r"untested|unknown\s*year|random\s*card|mystery"
    r")\b",
    re.I,
)
_RELIST_HINT = re.compile(
    r"\b("
    r"relist|re-list|back\s*up|backup\s*listing|second\s*chance"
    r")\b",
    re.I,
)


def parse_condition_signals(comp_title: str, target_is_graded: bool) -> Tuple[str, float]:
    """
    Returns (comma-joined flags, multiplier in (0,1]).
    Raw targets: strong downweight on raw damage language.
    Graded targets: only slab/integrity issues matter much.
    """
    t = (comp_title or "").strip()
    if not t:
        return "", 1.0
    low = t.lower()
    flags: List[str] = []
    mult = 1.0
    if target_is_graded:
        if _GRADED_BAD.search(low):
            flags.append("graded_integrity_risk")
            mult *= 0.35
        if _RAW_BAD.search(low):
            flags.append("raw_condition_noise_on_graded_comp")
            mult *= 0.92
    else:
        if _RAW_BAD.search(low):
            flags.append("raw_damage_language")
            mult *= 0.42
        if _GRADED_BAD.search(low):
            flags.append("slab_issue_mention")
            mult *= 0.55
    return ",".join(flags), mult


def listing_quality_adjustment(comp_title: str, sale_type: str) -> Tuple[float, str]:
    """
    Soft penalties — keep borderline comps but downweight.
    Returns (multiplier, debug token string).
    """
    t = (comp_title or "").strip()
    low = t.lower()
    parts: List[str] = []
    m = 1.0
    if len(low) < 22:
        parts.append("short_title")
        m *= 0.88
    if _LOT_AMBIGUOUS.search(low):
        parts.append("lot_ambiguity")
        m *= 0.62
    if _VAGUE_TITLE.search(low):
        parts.append("vague_listing")
        m *= 0.85
    if _RELIST_HINT.search(low):
        parts.append("relist_hint")
        m *= 0.80
    if sale_type in ("fixed_or_offer", "unknown"):
        parts.append("sale_uncertainty")
        m *= 0.90
    return m, "|".join(parts) if parts else ""


def assign_exactness_tier(
    *,
    gb_reason: str,
    grade_fallback: bool,
    qual: float,
    condition_mult: float,
    listing_mult: float,
    sale_type: str,
    variant_match_level: str = "",
) -> str:
    if gb_reason in ("cross_grade", "graded_other"):
        return "weaker_context_only"
    if grade_fallback or gb_reason == "adjacent_grade":
        return "exact_grade_fallback"
    if gb_reason in ("exact_grade", "raw_both"):
        if sale_type in ("fixed_price", "fixed_or_offer", "unknown"):
            if variant_match_level in ("exact_variant_match", "same_variant_family") and qual >= 0.58:
                return "exact_synonym_normalized"
            return "sale_type_fallback"
        strict_ok = (
            qual >= 0.70
            and condition_mult >= 0.88
            and listing_mult >= 0.88
        )
        if strict_ok:
            return "exact_strict"
        return "exact_synonym_normalized"
    return "weaker_context_only"


def _norm_title_key(title: str) -> str:
    s = (title or "").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def _seller_key(item: Dict[str, Any]) -> str:
    for k in ("sellerUsername", "seller", "sellerId"):
        v = item.get(k)
        if v:
            return str(v).strip().lower()
    u = item.get("seller", {})
    if isinstance(u, dict):
        for k in ("username", "sellerUsername"):
            v = u.get(k)
            if v:
                return str(v).strip().lower()
    return ""


def _price_key(p: float) -> str:
    return f"{round(float(p), 2):.2f}"


def _date_key(item: Dict[str, Any], today: date) -> str:
    raw = item.get("itemEndDate")
    if raw:
        return str(raw)[:10]
    return ""


def _image_key(item: Dict[str, Any]) -> str:
    img = item.get("image")
    if isinstance(img, dict):
        u = img.get("imageUrl") or img.get("url")
        if u:
            return str(u).strip().lower()[:200]
    return ""


def apply_duplicate_suppression(
    comps: List[Any],
    items: List[Dict[str, Any]],
    today: date,
) -> int:
    """
    Downweight likely duplicate relists in-place on comps (expects .weight and .duplicate_suppression_mult).
    Returns count of comps that were downweighted as non-primary duplicates.
    """
    if len(comps) != len(items):
        return 0
    groups: Dict[str, List[int]] = defaultdict(list)
    for i, (c, it) in enumerate(zip(comps, items)):
        iid = str(it.get("itemId") or "").strip()
        if iid:
            key = f"id:{iid}"
        else:
            key = "|".join(
                [
                    _norm_title_key(getattr(c, "title", "") or ""),
                    _price_key(getattr(c, "price", 0.0)),
                    _date_key(it, today),
                    _seller_key(it),
                    _image_key(it),
                ]
            )
        groups[key].append(i)

    downgraded = 0
    for _k, idxs in groups.items():
        if len(idxs) <= 1:
            continue
        # Keep strongest-weight index as primary
        best = max(idxs, key=lambda j: getattr(comps[j], "weight", 0.0))
        for j in idxs:
            if j == best:
                continue
            co = comps[j]
            co.duplicate_of_primary = True
            co.duplicate_suppression_mult *= 0.18
            co.weight = max(0.0, co.weight) * 0.18
            downgraded += 1
    return downgraded


def enrich_accepted_comp_pool(
    comps: List[Any],
    items: List[Dict[str, Any]],
    *,
    target_title: str,
    target_item: Optional[Dict[str, Any]],
    target_is_graded: bool,
    today: date,
) -> Tuple[int, Dict[str, int], str]:
    """
    Mutates comps in-place (weight + diagnostic fields).
    Returns (duplicate_downgraded_count, visual_status_counts, dominant_visual_status).
    """
    visual_counts: Dict[str, int] = defaultdict(int)
    for c, it in zip(comps, items):
        flags, cm = parse_condition_signals(c.title, target_is_graded)
        c.condition_flags = flags
        c.condition_penalty_mult = cm
        lq, lq_note = listing_quality_adjustment(c.title, c.sale_type or "unknown")
        c.listing_quality_penalty_mult = lq
        c.listing_quality_notes = lq_note

        vs, vst = get_visual_match_signal(target_item, it)
        c.visual_match_score = vs
        c.visual_verification_status = vst
        visual_counts[vst] += 1

        if vs is not None and vst == "used_custom_hook":
            c.weight *= max(0.2, min(1.0, 0.5 + 0.5 * float(vs)))

        c.weight *= cm * lq

        c.exactness_tier = assign_exactness_tier(
            gb_reason=c.gb_reason,
            grade_fallback=c.grade_fallback,
            qual=float(c.qual),
            condition_mult=cm,
            listing_mult=lq,
            sale_type=c.sale_type or "unknown",
            variant_match_level=getattr(c, "variant_match_level", "") or "",
        )

    dup_n = apply_duplicate_suppression(comps, items, today)

    dom_vis = ""
    if visual_counts:
        dom_vis = max(visual_counts.items(), key=lambda x: x[1])[0]

    return dup_n, dict(visual_counts), dom_vis


def tier_counts(comps: List[Any]) -> Dict[str, int]:
    out: Dict[str, int] = defaultdict(int)
    for c in comps:
        out[getattr(c, "exactness_tier", "") or "unknown"] += 1
    return dict(out)


def condition_issue_count(comps: List[Any]) -> int:
    n = 0
    for c in comps:
        fl = getattr(c, "condition_flags", "") or ""
        if fl and getattr(c, "condition_penalty_mult", 1.0) < 0.95:
            n += 1
    return n


def lane_weaker_tier_weight_fraction(lane_comps: List[Any]) -> float:
    weak = {
        "weaker_context_only",
        "sale_type_fallback",
        "exact_grade_fallback",
    }
    if not lane_comps:
        return 0.0
    mass = sum(max(0.0, c.weight) for c in lane_comps)
    if mass <= 0:
        return 1.0
    wmass = sum(max(0.0, c.weight) for c in lane_comps if c.exactness_tier in weak)
    return wmass / mass
