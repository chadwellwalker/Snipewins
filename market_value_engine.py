"""
Market value + deal scoring from eBay comp pools.

Uses :mod:`ebay_search` (Finding sold comps when ``EBAY_FINDING_APP_ID`` is set,
else active Browse listings as a proxy).

Upgrades vs v1:
- Outlier removal: comps >3x or <1/3 of median are stripped before MV computation.
- Recency weighting: last 7 days = 3x weight, 8-30 days = 1.5x, 30+ days = 1x.
- Minimum 5 comps required; fewer → LOW_CONFIDENCE (no deal score).
- New output fields: ``comp_recency`` (days since oldest accepted comp) and
  ``raw_vs_graded`` (ratio of raw:graded in pool).
- Whatnot velocity multiplier applied to deal score (T1=1.2x, T2=1.1x, T3=1.0x).
- Grade-filtered path preserved: raw vs graded comp separation maintained.

No Streamlit dependency — safe for scripts and tests.
"""

from __future__ import annotations

import re
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import ebay_search

# ---------------------------------------------------------------------------
# Grade / lot detection helpers
# ---------------------------------------------------------------------------

_GRADING_SERVICES = ("psa", "bgs", "sgc", "cgc", "hga")
_GRADING_PATTERN = re.compile(
    r"\b(psa|bgs|sgc|cgc|hga)\s*(\d{1,2}(?:\.\d)?)\b", re.IGNORECASE
)
_ANY_GRADER = re.compile(
    r"\b(psa|bgs|sgc|cgc|hga)\b", re.IGNORECASE
)
_LOT_PATTERN = re.compile(
    r"\blot\b|\blots\b|\b\d+\s*card[s]?\b|\bbreak\b|\bbox\b|\bcase\b|\bpack[s]?\b",
    re.IGNORECASE,
)


def _is_graded_title(title: str) -> bool:
    """True if the title signals any professional grading service."""
    return bool(_ANY_GRADER.search(title or ""))


def _extract_grade_key(title: str) -> Optional[str]:
    """
    Returns normalized grade key like ``psa_10``, ``psa_9``, ``bgs_9.5``.
    Returns None if no numeric grade found.
    """
    m = _GRADING_PATTERN.search(title or "")
    if not m:
        return None
    svc = m.group(1).lower()
    grade = m.group(2)
    if svc == "psa":
        try:
            g = float(grade)
            grade = str(int(g)) if g == int(g) else grade
        except ValueError:
            pass
    return f"{svc}_{grade}"


def _is_lot_title(title: str) -> bool:
    """True if the title looks like a multi-card lot or sealed product."""
    return bool(_LOT_PATTERN.search(title or ""))


def _extract_item_price(item: Dict[str, Any]) -> float:
    """Extract price from Browse or Finding API shaped dict."""
    for key in ("price", "currentBidPrice", "bidPrice"):
        p = item.get(key)
        if isinstance(p, dict):
            v = p.get("value")
        else:
            v = p
        if v is None:
            continue
        try:
            s = str(v).replace("$", "").replace(",", "").strip()
            x = float(s)
            if x > 0:
                return x
        except (TypeError, ValueError):
            continue
    return 0.0


def _extract_item_age_days(item: Dict[str, Any]) -> Optional[float]:
    """
    Return how many days ago this comp sold/listed.
    Tries common field names from eBay Finding API (endTime, soldDate)
    and Browse API (itemEndDate). Returns None if unavailable.
    """
    for key in ("endTime", "soldDate", "itemEndDate", "lastSoldDate", "date"):
        raw = item.get(key)
        if not raw:
            continue
        try:
            if isinstance(raw, (int, float)):
                ts = float(raw)
                if ts > 1e10:
                    ts /= 1000  # milliseconds → seconds
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            else:
                s = str(raw).strip()
                # ISO 8601 with or without fractional seconds / Z
                s = re.sub(r"\.\d+", "", s).replace("Z", "+00:00")
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            now = datetime.now(tz=timezone.utc)
            return max(0.0, (now - dt).total_seconds() / 86400)
        except Exception:
            continue
    return None


def _recency_weight(age_days: Optional[float]) -> float:
    """Return the recency multiplier for a comp based on its age."""
    if age_days is None:
        return 1.0  # unknown age → treat as old
    if age_days <= 7:
        return 3.0
    if age_days <= 30:
        return 1.5
    return 1.0


def _grade_matches(comp_title: str, target_is_graded: bool, target_grade_key: Optional[str]) -> bool:
    """
    Returns True only if the comp's grade status matches the target's.

    - Graded target → comp must also be graded with same grader+grade.
    - Raw target    → comp must NOT be graded.
    """
    comp_is_graded = _is_graded_title(comp_title)
    if target_is_graded != comp_is_graded:
        return False
    if not target_is_graded:
        return True
    if target_grade_key is None:
        return True
    comp_grade_key = _extract_grade_key(comp_title)
    if comp_grade_key is None:
        return True
    return comp_grade_key == target_grade_key


# ---------------------------------------------------------------------------
# Core fetch + filter
# ---------------------------------------------------------------------------

def fetch_ebay_comp_prices(
    query: str,
    limit: int = 15,
    *,
    grade_filter: bool = False,
    target_title: str = "",
) -> Tuple[List[float], str]:
    """
    Pull comparable listing prices: sold (Finding) preferred, else active Browse pool.

    Returns (prices, pool_kind). Lot listings always rejected. Grade-filtered when
    grade_filter=True or target_title is supplied.
    """
    q = (query or "").strip()
    if not q:
        return [], "none"
    lim = max(8, min(int(limit), 50))
    items, pool_kind = ebay_search.search_comp_pool(q, limit=lim)

    ref_title = (target_title or "").strip() or q
    do_filter = grade_filter or bool(target_title)
    target_is_graded = _is_graded_title(ref_title)
    target_grade_key = _extract_grade_key(ref_title) if target_is_graded else None

    prices: List[float] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        comp_title = str(item.get("title") or "").strip()
        if _is_lot_title(comp_title):
            continue
        if do_filter and not _grade_matches(comp_title, target_is_graded, target_grade_key):
            continue
        p = _extract_item_price(item)
        if p > 0:
            prices.append(p)

    return prices, pool_kind


def fetch_ebay_comp_items(
    query: str,
    limit: int = 15,
    *,
    grade_filter: bool = False,
    target_title: str = "",
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Like fetch_ebay_comp_prices but returns the full item dicts (with age/title).
    Filters lots and optionally grade-mismatches.
    """
    q = (query or "").strip()
    if not q:
        return [], "none"
    lim = max(8, min(int(limit), 50))
    items, pool_kind = ebay_search.search_comp_pool(q, limit=lim)

    ref_title = (target_title or "").strip() or q
    do_filter = grade_filter or bool(target_title)
    target_is_graded = _is_graded_title(ref_title)
    target_grade_key = _extract_grade_key(ref_title) if target_is_graded else None

    accepted: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        comp_title = str(item.get("title") or "").strip()
        if _is_lot_title(comp_title):
            continue
        if do_filter and not _grade_matches(comp_title, target_is_graded, target_grade_key):
            continue
        p = _extract_item_price(item)
        if p > 0:
            accepted.append(item)

    return accepted, pool_kind


# ---------------------------------------------------------------------------
# MV computation with outlier removal + recency weighting
# ---------------------------------------------------------------------------

MIN_COMP_THRESHOLD = 5  # below this → LOW_CONFIDENCE, no deal score


def _remove_outliers(prices: List[float]) -> List[float]:
    """
    Remove prices that are >3x or <1/3 of the median.
    Requires at least 3 prices to run; otherwise returns as-is.
    """
    if len(prices) < 3:
        return prices
    med = statistics.median(prices)
    if med <= 0:
        return prices
    low = med / 3.0
    high = med * 3.0
    filtered = [p for p in prices if low <= p <= high]
    # Guarantee we don't lose everything (fallback to original if over-trimmed)
    return filtered if len(filtered) >= 2 else prices


def compute_market_value(
    prices: List[float],
    items: Optional[List[Dict[str, Any]]] = None,
) -> Optional[float]:
    """
    Robust center from comp prices with:
    1. Outlier removal (3x median rule)
    2. Recency weighting (last 7d = 3x, 8-30d = 1.5x, 30+d = 1x)

    ``items`` is optional: if provided, age-days are extracted and recency weights applied.
    Falls back to unweighted median when items are not supplied.
    """
    if not prices:
        return None
    raw = sorted(float(x) for x in prices if x and float(x) > 0)
    if not raw:
        return None

    # Step 1: outlier removal
    cleaned = _remove_outliers(raw)

    # Step 2: recency-weighted median (expand by weight)
    if items and len(items) == len(prices):
        # Build weighted list: repeat each price by its weight factor
        weighted: List[float] = []
        for i, p in enumerate(prices):
            fp = float(p)
            if fp <= 0:
                continue
            item = items[i] if i < len(items) else {}
            age = _extract_item_age_days(item)
            w = _recency_weight(age)
            # Check if this price survived outlier removal
            med_before = statistics.median(raw) if raw else 0
            if med_before > 0 and not (med_before / 3.0 <= fp <= med_before * 3.0):
                continue  # outlier — skip
            repeats = max(1, int(w * 2))  # 3x → 6 slots, 1.5x → 3 slots, 1x → 2 slots
            weighted.extend([fp] * repeats)
        if weighted:
            return round(float(statistics.median(weighted)), 2)

    # Fallback: unweighted median on cleaned prices
    return round(float(statistics.median(cleaned)), 2)


def _comp_recency_summary(items: List[Dict[str, Any]]) -> str:
    """Return a human-readable recency label for the comp pool."""
    ages = [_extract_item_age_days(it) for it in items]
    known = [a for a in ages if a is not None]
    if not known:
        return "unknown"
    avg = sum(known) / len(known)
    if avg <= 7:
        return "very_recent"
    if avg <= 30:
        return "recent"
    return "stale"


def _raw_vs_graded_ratio(items: List[Dict[str, Any]]) -> str:
    """Return 'all_raw', 'all_graded', or 'mixed' for the comp pool."""
    if not items:
        return "unknown"
    graded_count = sum(
        1 for it in items if _is_graded_title(str(it.get("title") or ""))
    )
    raw_count = len(items) - graded_count
    if graded_count == 0:
        return "all_raw"
    if raw_count == 0:
        return "all_graded"
    return "mixed"


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------

def get_market_value_for_item(
    title: str,
    limit: int = 15,
    *,
    whatnot_tier: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Main entry: grade-filtered comp-based MV + confidence from sample size and comp source.

    New fields in returned dict:
    - ``comp_recency``: 'very_recent' | 'recent' | 'stale' | 'unknown'
    - ``raw_vs_graded``: 'all_raw' | 'all_graded' | 'mixed' | 'unknown'
    - ``low_confidence``: True when comp count < MIN_COMP_THRESHOLD

    ``whatnot_tier`` (1/2/3): applied as a deal-score multiplier downstream via
    ``compute_deal_score_with_tier()``.
    """
    title = (title or "").strip()
    if not title:
        return {
            "market_value": None,
            "confidence": "LOW",
            "low_confidence": True,
            "comp_count": 0,
            "source": "none",
            "comp_pool": "none",
            "comp_recency": "unknown",
            "raw_vs_graded": "unknown",
        }

    items, pool_kind = fetch_ebay_comp_items(
        title, limit=limit, grade_filter=True, target_title=title
    )
    prices = [_extract_item_price(it) for it in items]
    prices = [p for p in prices if p > 0]

    n = len(prices)
    low_confidence = n < MIN_COMP_THRESHOLD

    mv = compute_market_value(prices, items) if prices else None

    if low_confidence:
        conf = "LOW"
    elif n >= 10:
        conf = "HIGH"
    else:
        conf = "MEDIUM"

    src = "sold_finding" if pool_kind == "sold_finding" else "active_browse_proxy"
    return {
        "market_value": mv,
        "confidence": conf if mv is not None else "LOW",
        "low_confidence": low_confidence,
        "comp_count": n,
        "source": src,
        "comp_pool": pool_kind,
        "comp_recency": _comp_recency_summary(items),
        "raw_vs_graded": _raw_vs_graded_ratio(items),
    }


# ---------------------------------------------------------------------------
# Deal scoring
# ---------------------------------------------------------------------------

_WHATNOT_TIER_MULTIPLIER = {1: 1.2, 2: 1.1, 3: 1.0}


def compute_deal_score(price: Any, market_value: Any) -> int:
    """0–100: discount vs MV. No Whatnot tier applied — use compute_deal_score_with_tier for that."""
    try:
        p = float(price)
    except (TypeError, ValueError):
        return 0
    try:
        mv = float(market_value)
    except (TypeError, ValueError):
        return 0
    if mv is None or mv <= 0:
        return 0
    edge = (mv - p) / mv
    return int(max(0, min(100, edge * 120)))


def compute_deal_score_with_tier(
    price: Any,
    market_value: Any,
    whatnot_tier: Optional[int] = None,
    low_confidence: bool = False,
) -> int:
    """
    Deal score with optional Whatnot velocity multiplier.

    Returns 0 when ``low_confidence`` is True (< MIN_COMP_THRESHOLD comps).
    Applies tier multiplier: T1=1.2x, T2=1.1x, T3=1.0x.
    """
    if low_confidence:
        return 0
    base = compute_deal_score(price, market_value)
    mult = _WHATNOT_TIER_MULTIPLIER.get(whatnot_tier or 3, 1.0)
    return int(max(0, min(100, base * mult)))


def classify_deal(score: int) -> str:
    if score >= 80:
        return "ELITE"
    if score >= 60:
        return "STRONG"
    if score >= 40:
        return "GOOD"
    if score >= 20:
        return "WEAK"
    return "PASS"


def deal_color(deal_class: str) -> str:
    return {
        "ELITE": "#22c55e",
        "STRONG": "#84cc16",
        "GOOD": "#f97316",
        "WEAK": "#9ca3af",
        "PASS": "#ef4444",
    }.get(str(deal_class or "").upper(), "#e5e7eb")


def deal_class_badge(deal_class: str) -> str:
    """Short label for table cells (emoji + class)."""
    dc = str(deal_class or "PASS").upper()
    icon = {
        "ELITE": "🟢",
        "STRONG": "🟡",
        "GOOD": "🟠",
        "WEAK": "⚪",
        "PASS": "🔴",
    }.get(dc, "⚪")
    return f"{icon} {dc}"


def enrich_listing_with_value(
    row: Dict[str, Any],
    *,
    whatnot_tier: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Mutate a listing-shaped dict with MV, confidence, deal score, and new recency/grade fields.

    Added fields: ``market_value``, ``mv_confidence``, ``low_confidence``,
    ``comp_count``, ``mv_engine_source``, ``comp_recency``, ``raw_vs_graded``,
    ``deal_score``, ``deal_class``.

    LOW CONFIDENCE listings get ``deal_score=0`` and ``deal_class='LOW_CONFIDENCE'``.
    """
    if not isinstance(row, dict):
        return row
    title = str(row.get("title") or "")
    mv_data = get_market_value_for_item(title, whatnot_tier=whatnot_tier)

    row["market_value"] = mv_data["market_value"]
    row["mv_confidence"] = mv_data["confidence"]
    row["low_confidence"] = mv_data["low_confidence"]
    row["comp_count"] = mv_data["comp_count"]
    row["mv_engine_source"] = mv_data["source"]
    row["mv_comp_pool"] = mv_data["comp_pool"]
    row["comp_recency"] = mv_data["comp_recency"]
    row["raw_vs_graded"] = mv_data["raw_vs_graded"]

    if mv_data["low_confidence"]:
        row["deal_score"] = 0
        row["deal_class"] = "LOW_CONFIDENCE"
        return row

    price = row.get("current_price")
    if price is None:
        price = row.get("price")
    if isinstance(price, dict):
        price = price.get("value")

    mv = row.get("market_value")
    row["deal_score"] = compute_deal_score_with_tier(
        price, mv, whatnot_tier=whatnot_tier, low_confidence=False
    )
    row["deal_class"] = classify_deal(int(row["deal_score"]))
    return row


# ---------------------------------------------------------------------------
# Diagnostic helpers (exposed for testing / debug panels)
# ---------------------------------------------------------------------------

def comp_filter_debug(query: str, target_title: str, limit: int = 20) -> Dict[str, Any]:
    """
    Return a debug dict showing which comps were accepted vs rejected by the grade filter.
    """
    q = (query or "").strip()
    ref = (target_title or "").strip() or q
    if not q:
        return {"error": "empty query"}

    lim = max(8, min(int(limit), 50))
    items, pool_kind = ebay_search.search_comp_pool(q, limit=lim)

    target_is_graded = _is_graded_title(ref)
    target_grade_key = _extract_grade_key(ref) if target_is_graded else None

    accepted = []
    rejected = []
    for item in items:
        if not isinstance(item, dict):
            continue
        comp_title = str(item.get("title") or "").strip()
        price = _extract_item_price(item)
        age = _extract_item_age_days(item)

        reject_reason = None
        if _is_lot_title(comp_title):
            reject_reason = "lot"
        elif not _grade_matches(comp_title, target_is_graded, target_grade_key):
            comp_is_graded = _is_graded_title(comp_title)
            comp_grade_key = _extract_grade_key(comp_title)
            if target_is_graded != comp_is_graded:
                reject_reason = f"grade_type_mismatch(target={'graded' if target_is_graded else 'raw'} comp={'graded' if comp_is_graded else 'raw'})"
            else:
                reject_reason = f"grade_value_mismatch(target={target_grade_key} comp={comp_grade_key})"

        entry = {"title": comp_title[:120], "price": price, "age_days": age}
        if reject_reason:
            entry["reject_reason"] = reject_reason
            rejected.append(entry)
        else:
            accepted.append(entry)

    accepted_prices = [e["price"] for e in accepted if e["price"] > 0]
    cleaned_prices = _remove_outliers(accepted_prices)
    return {
        "pool_kind": pool_kind,
        "target_is_graded": target_is_graded,
        "target_grade_key": target_grade_key,
        "fetched_total": len(items),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "below_min_threshold": len(accepted_prices) < MIN_COMP_THRESHOLD,
        "accepted": accepted,
        "rejected": rejected,
        "mv_from_filtered": compute_market_value(accepted_prices),
        "mv_from_cleaned": compute_market_value(cleaned_prices),
        "mv_from_all": compute_market_value(
            [_extract_item_price(i) for i in items if _extract_item_price(i) > 0]
        ),
    }
