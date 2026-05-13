"""
Guardrails: never treat the target listing as its own comp; validate sold dates for sold pools.

Title/ID/url only — no new API calls. Safe to import from valuation_engine without cycles.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional, Tuple


def normalize_item_id(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    if "|" in s:
        parts = s.split("|")
        for p in reversed(parts):
            p = p.strip()
            if p.isdigit() and len(p) >= 10:
                return p
    if s.isdigit() and len(s) >= 10:
        return s
    return s


def item_id_from_comp_item(item: Dict[str, Any]) -> str:
    return normalize_item_id(item.get("itemId") or item.get("legacyItemId") or "")


def extract_item_id_from_url(url: str) -> str:
    if not url or not isinstance(url, str):
        return ""
    s = url.strip()
    if s.isdigit() and len(s) >= 10:
        return s
    if "/itm/" in s:
        part = s.split("/itm/")[-1].split("?")[0].strip()
        if part.isdigit():
            return part
    return ""


def _norm_url(u: str) -> str:
    return re.sub(r"\s+", "", (u or "").strip().lower())


def _comp_image_url_key(item: Dict[str, Any]) -> str:
    img = item.get("image")
    if isinstance(img, dict):
        u = (img.get("imageUrl") or img.get("url") or "").strip().lower()
        if u:
            return u[:400]
    thumbs = item.get("thumbnailImages") or []
    if isinstance(thumbs, list) and thumbs:
        t0 = thumbs[0] if isinstance(thumbs[0], dict) else {}
        u = (t0.get("imageUrl") or "").strip().lower()
        if u:
            return u[:400]
    return ""


def _seller_key(item: Dict[str, Any]) -> str:
    s = item.get("seller")
    if isinstance(s, dict):
        return (s.get("username") or s.get("sellerUsername") or "").strip().lower()[:120]
    return (item.get("sellerUsername") or "").strip().lower()[:120]


def parse_iso_to_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    raw = str(value).strip()
    if not raw:
        return None
    raw = raw.replace("Z", "+00:00")
    try:
        if "T" in raw:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc)
            return dt.date()
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def parse_comp_item_end_date(item: Dict[str, Any]) -> Optional[date]:
    return parse_iso_to_date(item.get("itemEndDate"))


def is_valid_sold_date_for_pool(sale_d: Optional[date], today: date) -> bool:
    if sale_d is None:
        return False
    return sale_d <= today


def validate_comp_sale_temporal(
    pool_kind: str,
    item: Dict[str, Any],
    today: date,
) -> Tuple[bool, str, Optional[date]]:
    """
    For sold_finding: require parsable end/sold date on or before today.
    For active_browse: allow any parse (future = listing end); sale date for MV is not implied.
    """
    d = parse_comp_item_end_date(item)
    if pool_kind == "sold_finding":
        if d is None:
            return False, "missing_sold_date_evidence", None
        if d > today:
            return False, "invalid_future_sold_date", None
        return True, "", d
    if pool_kind != "active_browse":
        if d is not None and d > today:
            return False, "invalid_future_sold_date", None
        return True, "", d
    return True, "", d


def is_same_listing_as_target(
    target_item_id: str,
    target_item_url: str,
    target_item: Optional[Dict[str, Any]],
    comp_item: Dict[str, Any],
) -> Tuple[bool, str]:
    """
    Strong identity match = reject comp. Returns (is_same, reason_tag).
    """
    tid = normalize_item_id(target_item_id)
    cid = item_id_from_comp_item(comp_item)
    if tid and cid and tid == cid:
        return True, "same_as_target_listing"

    turl = _norm_url(target_item_url)
    if turl:
        for k in ("itemWebUrl", "itemAffiliateWebUrl", "itemHref"):
            cu = _norm_url(str(comp_item.get(k) or ""))
            if cu and cu == turl:
                return True, "duplicate_target_identity"
        for cu in _candidate_comp_urls(comp_item):
            if cu and cu == turl:
                return True, "duplicate_target_identity"
        tid_from_turl = extract_item_id_from_url(target_item_url)
        if tid_from_turl and cid and tid_from_turl == cid:
            return True, "same_as_target_listing"

    if target_item and isinstance(target_item, dict):
        t_tit = re.sub(
            r"\s+",
            " ",
            (target_item.get("title") or target_item.get("card_name") or "").strip().lower(),
        )[:200]
        c_tit = re.sub(r"\s+", " ", (comp_item.get("title") or "").strip().lower())[:200]
        t_img = _comp_image_url_key(target_item)
        c_img = _comp_image_url_key(comp_item)
        if t_img and c_img and t_img == c_img and t_tit and c_tit and t_tit == c_tit:
            return True, "duplicate_target_identity"

        ts = _seller_key(target_item)
        cs = _seller_key(comp_item)
        if ts and cs and ts == cs and t_tit and c_tit and t_tit == c_tit:
            return True, "duplicate_target_identity"

    return False, ""


def _candidate_comp_urls(item: Dict[str, Any]) -> Tuple[str, ...]:
    out = []
    for k in ("itemWebUrl", "itemAffiliateWebUrl", "itemHref"):
        v = _norm_url(str(item.get(k) or ""))
        if v:
            out.append(v)
    return tuple(out)


def comp_source_type_label(pool_kind: str) -> str:
    if pool_kind == "sold_finding":
        return "sold_comp"
    if pool_kind == "active_browse":
        return "active_listing"
    return "unknown"


def assert_no_target_in_accepted(
    target_item_id: str,
    accepted_items: Tuple[Dict[str, Any], ...],
) -> Tuple[bool, str]:
    """Lightweight integrity check for debug (never raises)."""
    tid = normalize_item_id(target_item_id)
    if not tid:
        return True, ""
    for it in accepted_items:
        if item_id_from_comp_item(it) == tid:
            return False, "target_item_id_in_accepted_buffer"
    return True, ""


if __name__ == "__main__":
    _t = date(2026, 3, 26)
    assert is_valid_sold_date_for_pool(date(2026, 3, 25), _t)
    assert not is_valid_sold_date_for_pool(date(2026, 3, 27), _t)
    assert not is_valid_sold_date_for_pool(None, _t)
    same, tag = is_same_listing_as_target(
        "12345",
        "https://www.ebay.com/itm/12345",
        None,
        {"itemId": "12345", "title": "x"},
    )
    assert same and tag == "same_as_target_listing"
    print("comp_listing_validation ok")
