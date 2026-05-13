"""
Saved \"trusted buying\" preferences merged into cockpit ranking filters.
Human-edited; optional overlay on session Buyer preferences when enabled.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

PROFILE_PATH = os.path.join(os.path.dirname(__file__) or ".", "trusted_buying_profile.json")

_DEFAULT: Dict[str, Any] = {
    "favorite_players": "",
    "favorite_sets": "",
    "favorite_parallels": "",
    "min_confidence": "any",
    "min_edge_pct": 0.0,
    "max_price_per_card": 0.0,
    "avoid_phrases": "",
    "strict_favorites": False,
    "risk_tolerance": "medium",
    "typical_buy_min": 0.0,
    "typical_buy_max": 0.0,
}


def load_profile(path: str | None = None) -> Dict[str, Any]:
    p = path or PROFILE_PATH
    out = dict(_DEFAULT)
    if not os.path.isfile(p):
        return out
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            out.update({k: data.get(k, out[k]) for k in _DEFAULT})
    except (json.JSONDecodeError, OSError, TypeError):
        pass
    return out


def save_profile(data: Dict[str, Any], path: str | None = None) -> bool:
    p = path or PROFILE_PATH
    try:
        merged = dict(_DEFAULT)
        merged.update({k: data.get(k, merged[k]) for k in _DEFAULT})
        with open(p, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
        return True
    except (OSError, TypeError):
        return False


def merge_into_prefs(prefs: Dict[str, Any], profile: Dict[str, Any], use_trusted: bool) -> Dict[str, Any]:
    """
    Overlay saved profile onto cockpit prefs dict used by filter_groups_by_buyer_preferences.
    Risk tolerance nudges minimum edge% when session prefs are looser.
    """
    if not use_trusted or not profile:
        return prefs
    out = dict(prefs or {})
    for key in (
        "favorite_players",
        "favorite_sets",
        "favorite_parallels",
        "min_confidence",
        "avoid_phrases",
        "strict_favorites",
    ):
        v = profile.get(key)
        if v is not None and v != "" and v is not False:
            out[key] = v
    try:
        mep = float(profile.get("min_edge_pct") or 0)
        if mep > float(out.get("min_edge_pct") or 0):
            out["min_edge_pct"] = mep
    except (TypeError, ValueError):
        pass
    try:
        mpx = float(profile.get("max_price_per_card") or 0)
        if mpx > 0:
            cur = float(out.get("max_price_per_card") or 0)
            if cur <= 0 or mpx < cur:
                out["max_price_per_card"] = mpx
    except (TypeError, ValueError):
        pass
    rt = str(profile.get("risk_tolerance") or "medium").strip().lower()
    base_ep = float(out.get("min_edge_pct") or 0)
    if rt == "low":
        out["min_edge_pct"] = max(base_ep, 4.0)
    elif rt == "high":
        out["min_edge_pct"] = max(0.0, base_ep - 1.0) if base_ep > 1.0 else base_ep
    try:
        tmin = float(profile.get("typical_buy_min") or 0)
        tmax = float(profile.get("typical_buy_max") or 0)
        if tmin > 0 or tmax > 0:
            out["_trusted_price_min"] = tmin
            out["_trusted_price_max"] = tmax
    except (TypeError, ValueError):
        pass
    return out


def trusted_price_bonus(group: dict, prefs: dict) -> float:
    """Small rank bonus when ask sits inside saved typical buy range."""
    lo = float(prefs.get("_trusted_price_min") or 0)
    hi = float(prefs.get("_trusted_price_max") or 0)
    if hi <= 0 or lo < 0 or hi < lo:
        return 0.0
    price = float(group.get("best_price") or 0)
    if price <= 0:
        return 0.0
    if lo <= price <= hi:
        return 2.5
    return 0.0
