"""
Opportunity scoring and sniper decision layer on top of valuation output.

Pure functions — no Streamlit. Uses watchlist row fields plus optional valuation_debug
(session-cached diagnostics keyed by listing URL).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _sf(v: Any, default: float = 0.0) -> float:
    try:
        if isinstance(v, str):
            s = v.strip().replace(",", "")
            if s.startswith("$"):
                s = s[1:]
            if not s:
                return default
            return float(s)
        return float(v)
    except (TypeError, ValueError):
        return default


def merge_valuation_context(raw_row: Dict[str, Any], valuation_debug: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Prefer debug (fresh run) over CSV row for engine fields."""
    row = raw_row or {}
    dbg = valuation_debug or {}
    vst = (dbg.get("valuation_strength") or row.get("valuation_strength") or "").strip().lower()
    flow = (dbg.get("valuation_flow_label") or row.get("valuation_flow_label") or "").strip().lower()
    return {
        "valuation_strength": vst,
        "valuation_flow_label": flow,
        "duplicate_suppressed_count": int(dbg.get("duplicate_suppressed_count") or _sf(row.get("duplicate_suppressed_count"), 0) or 0),
        "condition_issue_lane_count": int(dbg.get("condition_issue_lane_count") or _sf(row.get("condition_issue_lane_count"), 0) or 0),
        "condition_issue_accepted_count": int(
            dbg.get("condition_issue_accepted_count") or _sf(row.get("condition_issue_accepted_count"), 0) or 0
        ),
        "market_lane_strength": _sf(dbg.get("market_lane_strength"), _sf(row.get("market_lane_strength"), 0.0) or 0.0),
        "valuation_sale_mode": (dbg.get("valuation_sale_mode") or row.get("valuation_sale_mode") or "").strip().lower(),
        "accepted_comps": int(dbg.get("accepted") or _sf(row.get("comp_count"), 0) or 0),
        "recent_7d": int(dbg.get("recent_7d") or _sf(row.get("recent_comp_count_7d"), 0) or 0),
        "recent_30d": int(dbg.get("recent_30d") or _sf(row.get("recent_comp_count_30d"), 0) or 0),
        "grade_fallback_used": bool(dbg.get("grade_fallback_used") or row.get("grade_fallback_used") == "1"),
    }


def _trust_tier(vst: str, conf: str, mv: float, source: str) -> str:
    conf_l = (conf or "").strip().lower()
    src = (source or "").strip().lower()
    if mv <= 0:
        return "unreliable"
    if vst == "no_reliable_value":
        return "unreliable"
    if conf_l == "estimate_only":
        return "unreliable"
    if conf_l in ("manual_override",) or (conf_l == "manual" and "manual_canonical" in src):
        return "high"
    if "manual" in src and conf_l == "manual":
        return "medium"
    if vst == "strong_market_value":
        if conf_l == "high":
            return "high"
        if conf_l == "medium":
            return "high"
        if conf_l == "low":
            return "medium"
        return "medium"
    if vst == "provisional_estimate":
        if conf_l == "high":
            return "medium"
        if conf_l == "medium":
            return "medium"
        return "low"
    if vst:
        return "low"
    if conf_l in ("high", "medium"):
        return "medium"
    if conf_l == "low":
        return "low"
    return "unreliable"


def _margins_for_tier(tier: str) -> Tuple[float, float, float]:
    """
    Returns (safe_discount, aggressive_discount, score_cap).
    Buy caps = mv * (1 - discount); larger discount => more conservative cap.
    """
    if tier == "high":
        return 0.24, 0.09, 100.0
    if tier == "medium":
        return 0.30, 0.14, 68.0
    if tier == "low":
        return 0.38, 0.22, 38.0
    return 0.55, 0.40, 12.0


def _min_edge_pct_for_snipe(tier: str) -> float:
    if tier == "high":
        return 3.0
    if tier == "medium":
        return 6.5
    if tier == "low":
        return 22.0
    return 999.0


def manual_lineage_note(flow: str) -> str:
    if flow == "manual_mv_override":
        return "Canonical manual MV override (your number)."
    if flow == "auto_with_manual_comp_influence":
        return "Auto valuation with manual comp approve/reject / learned weighting."
    if flow == "auto":
        return "Fully automatic comp engine (no manual comp state on this run)."
    return "Valuation lineage unknown or not cached for this listing."


def build_opportunity_score(
    *,
    current_price: float,
    market_value: float,
    max_bid: float,
    market_value_confidence: str,
    market_value_source: str,
    display_status: str,
    time_left: Optional[float],
    vx: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Core opportunity score + buy caps + decision label inputs.
    Returns flat dict of metrics and explanation fields.
    """
    cp = max(0.0, _sf(current_price))
    mv = max(0.0, _sf(market_value))
    mb = max(0.0, _sf(max_bid))
    conf = (market_value_confidence or "").strip().lower()
    src = (market_value_source or "").strip().lower()
    vst = vx.get("valuation_strength") or ""
    flow = vx.get("valuation_flow_label") or ""
    tier = _trust_tier(vst, conf, mv, src)

    edge_dollars = round(mv - cp, 2) if mv > 0 else 0.0
    edge_percent = round((edge_dollars / mv) * 100.0, 2) if mv > 0 else 0.0

    safe_d, agg_d, score_cap = _margins_for_tier(tier)
    safe_buy_price = round(mv * (1.0 - safe_d), 2) if mv > 0 else 0.0
    aggressive_buy_price = round(mv * (1.0 - agg_d), 2) if mv > 0 else 0.0

    penalties: List[str] = []
    components: List[str] = []

    dup_n = int(vx.get("duplicate_suppressed_count") or 0)
    if dup_n >= 3:
        penalties.append(f"duplicate_downweight:{dup_n}")
    cond_lane = int(vx.get("condition_issue_lane_count") or 0)
    if cond_lane >= 2:
        penalties.append(f"condition_in_lane:{cond_lane}")

    lane_st = float(vx.get("market_lane_strength") or 0.0)
    comp_mult = 0.62 + 0.38 * max(0.0, min(1.0, lane_st))
    components.append(f"lane_strength×{comp_mult:.2f}")

    if vst == "strong_market_value":
        strength_mult = 1.0
    elif vst == "provisional_estimate":
        strength_mult = 0.74
    elif vst == "no_reliable_value":
        strength_mult = 0.12
    else:
        strength_mult = 0.55
    components.append(f"result_type×{strength_mult:.2f}")

    if conf == "high":
        conf_mult = 1.0
    elif conf == "medium":
        conf_mult = 0.86
    elif conf == "low":
        conf_mult = 0.58
    elif conf == "estimate_only":
        conf_mult = 0.2
    elif conf in ("manual_override", "manual"):
        conf_mult = 0.95
    else:
        conf_mult = 0.7
    components.append(f"confidence×{conf_mult:.2f}")

    if flow == "auto_with_manual_comp_influence":
        comp_mult *= 0.94
        components.append("manual_comp_influence×0.94")
    if flow == "manual_mv_override":
        components.append("manual_mv_flow")

    sale_mode = vx.get("valuation_sale_mode") or ""
    if sale_mode in ("fixed_price_lane",):
        comp_mult *= 0.9
        penalties.append("sale_mode:fixed_heavy_lane")
    elif sale_mode == "auction_focused":
        comp_mult *= 1.03

    acc_n = int(vx.get("accepted_comps") or 0)
    if acc_n > 0 and acc_n < 4:
        penalties.append(f"thin_comps:{acc_n}")
        comp_mult *= 0.92

    if vx.get("grade_fallback_used"):
        penalties.append("grade_fallback_used")
        comp_mult *= 0.93

    edge_clamped = max(-15.0, min(45.0, edge_percent))
    edge_points = ((edge_clamped + 15.0) / 60.0) * 42.0
    components.append(f"edge_pts={edge_points:.1f}")

    time_boost = 0.0
    if time_left is not None and time_left > 0:
        if time_left < 3600:
            time_boost = 6.0
        elif time_left < 86400:
            time_boost = 3.0
        elif time_left > 72 * 3600:
            time_boost = -2.0
    components.append(f"time_adj={time_boost:+.1f}")

    dup_pen = min(14.0, dup_n * 1.2)
    cond_pen = min(10.0, cond_lane * 2.5)

    raw = edge_points * strength_mult * conf_mult * comp_mult + time_boost - dup_pen - cond_pen
    if display_status == "near_max":
        raw *= 0.82
        penalties.append("near_max_bid")
    if display_status == "over_budget" or (mb > 0 and cp > mb):
        raw = min(raw, 4.0)
        penalties.append("over_max_bid")

    capped = max(0.0, min(score_cap, raw))
    confidence_cap_applied = raw > score_cap + 0.01

    decision_label = "No Reliable Value"
    if mv <= 0 or tier == "unreliable":
        decision_label = "No Reliable Value"
    elif mb > 0 and cp > mb:
        decision_label = "Pass"
    elif mv > 0 and cp >= mv * 0.995:
        decision_label = "Pass"
    elif edge_percent < 2.0 and mv > 0:
        decision_label = "Thin Edge"
    elif tier == "unreliable":
        decision_label = "No Reliable Value"
    elif capped >= 68 and tier == "high" and edge_percent >= 12:
        decision_label = "Strong Buy"
    elif capped >= 48 and edge_percent >= 5:
        decision_label = "Good Opportunity"
    elif capped >= 22:
        decision_label = "Watch Closely"
    elif edge_percent >= 8:
        decision_label = "Watch Closely"
    else:
        decision_label = "Pass"

    lineage = manual_lineage_note(flow)

    return {
        "edge_dollars": edge_dollars,
        "edge_percent": edge_percent,
        "safe_buy_price": safe_buy_price,
        "aggressive_buy_price": aggressive_buy_price,
        "opportunity_score": round(capped, 2),
        "opportunity_score_raw": round(raw, 2),
        "opportunity_score_cap": score_cap,
        "confidence_cap_applied": confidence_cap_applied,
        "trust_tier": tier,
        "decision_label": decision_label,
        "manual_lineage_note": lineage,
        "valuation_strength_used": vst or "unknown",
        "valuation_flow_used": flow or "unknown",
        "opportunity_penalties": "; ".join(penalties) if penalties else "",
        "opportunity_components": " | ".join(components),
    }


def build_sniper_decision(
    *,
    auction_state: Dict[str, Any],
    opportunity: Dict[str, Any],
    timing_health_overall: str,
) -> Dict[str, Any]:
    """Sniper recommendation; conservative when valuation trust is low."""
    cp = _sf(auction_state.get("current_price"))
    mb = _sf(auction_state.get("max_bid"))
    mv = _sf(auction_state.get("market_value"))
    tier = opportunity.get("trust_tier") or "unreliable"
    edge_pct = _sf(opportunity.get("edge_percent"))
    aggressive = _sf(opportunity.get("aggressive_buy_price"))
    display = (auction_state.get("display_status") or "").strip().lower()
    time_left = auction_state.get("time_left")
    risk_flags: List[str] = []
    opp_pen = opportunity.get("opportunity_penalties") or ""
    if opp_pen:
        for chunk in opp_pen.split(";"):
            c = chunk.strip()
            if c:
                risk_flags.append(c.replace(":", "_"))
    if tier == "low":
        risk_flags.append("low_trust_tier")
    if tier == "unreliable":
        risk_flags.append("unreliable_valuation")
    if opportunity.get("valuation_flow_used") == "manual_mv_override":
        risk_flags.append("manual_mv_override")
    elif opportunity.get("valuation_flow_used") == "auto_with_manual_comp_influence":
        risk_flags.append("manual_comp_influence")

    min_edge = _min_edge_pct_for_snipe(tier)
    eligible_time = time_left is not None and time_left > 0
    price_ok = mb <= 0 or cp <= mb
    health_ok = timing_health_overall == "Eligible"
    edge_ok = edge_pct >= min_edge and mv > 0
    under_aggressive = aggressive > 0 and cp <= aggressive * 1.005

    base = (
        eligible_time
        and display != "over_budget"
        and price_ok
        and under_aggressive
        and mv > 0
        and tier != "unreliable"
    )
    if not base:
        should_snipe = False
    elif tier == "low":
        should_snipe = edge_pct >= 25.0 and health_ok
    else:
        should_snipe = edge_ok and health_ok

    recommended = round(min(mb, aggressive), 2) if mb > 0 and aggressive > 0 else round(aggressive, 2)
    if cp > 0 and recommended > 0 and recommended < cp * 0.999:
        recommended = 0.0
        should_snipe = False

    if tier == "unreliable" or mv <= 0:
        reason = "No snipe: valuation not reliable enough to justify automated bidding."
    elif display == "over_budget" or not price_ok:
        reason = "No snipe: current price above your max bid."
    elif not eligible_time:
        reason = "No snipe: auction not active."
    elif not edge_ok:
        reason = f"No snipe: edge {edge_pct:.1f}% below minimum for trust tier ({min_edge:.1f}%)."
    elif not health_ok:
        reason = "No snipe: timing health not Eligible (trigger window / snipe seconds risk)."
    elif should_snipe:
        reason = (
            f"Snipe reasonable: edge {edge_pct:.1f}%, cap aggressive buy ${aggressive:.2f}, "
            f"recommended max ${recommended:.2f} (≤ your max bid)."
        )
    else:
        reason = "Watch only: edge or trust tier does not justify a snipe recommendation."

    if opportunity.get("manual_lineage_note"):
        reason = reason + " | " + str(opportunity.get("manual_lineage_note"))

    urgency = "low"
    if time_left is not None and time_left > 0:
        if time_left < 1800:
            urgency = "high"
        elif time_left < 7200:
            urgency = "medium"

    readiness = "not_ready"
    if eligible_time and price_ok and display != "over_budget":
        if health_ok:
            readiness = "ready"
        else:
            readiness = "future_window"

    return {
        "should_snipe": bool(should_snipe),
        "snipe_max_bid_recommended": recommended if should_snipe else 0.0,
        "sniper_reason_summary": reason,
        "sniper_risk_flags": "; ".join(risk_flags) if risk_flags else "",
        "sniper_urgency_level": urgency,
        "sniper_readiness": readiness,
    }


def build_opportunity_score_row(
    raw_row: Dict[str, Any],
    auction_state: Dict[str, Any],
    valuation_debug: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Public helper: opportunity metrics from a watchlist row + the same auction_state dict
    used in the UI (after base fields are set, before attach_decision_layer).
    """
    vx = merge_valuation_context(raw_row, valuation_debug)
    return build_opportunity_score(
        current_price=_sf(auction_state.get("current_price")),
        market_value=_sf(auction_state.get("market_value")),
        max_bid=_sf(auction_state.get("max_bid")),
        market_value_confidence=str(auction_state.get("market_value_confidence") or ""),
        market_value_source=str(auction_state.get("market_value_source") or ""),
        display_status=str(auction_state.get("display_status") or ""),
        time_left=auction_state.get("time_left"),
        vx=vx,
    )


def build_sniper_decision_row(
    auction_state: Dict[str, Any],
    opportunity: Dict[str, Any],
    timing_health_overall: str,
) -> Dict[str, Any]:
    """Public alias for build_sniper_decision (clearer call sites)."""
    return build_sniper_decision(
        auction_state=auction_state,
        opportunity=opportunity,
        timing_health_overall=timing_health_overall or "Not Eligible",
    )


def attach_decision_layer(
    auction_state: Dict[str, Any],
    raw_row: Dict[str, Any],
    valuation_debug: Optional[Dict[str, Any]] = None,
    timing_health_overall: str = "Not Eligible",
) -> None:
    """Mutate auction_state in place with opportunity + sniper fields."""
    vx = merge_valuation_context(raw_row, valuation_debug)
    opp = build_opportunity_score(
        current_price=_sf(auction_state.get("current_price")),
        market_value=_sf(auction_state.get("market_value")),
        max_bid=_sf(auction_state.get("max_bid")),
        market_value_confidence=str(auction_state.get("market_value_confidence") or ""),
        market_value_source=str(auction_state.get("market_value_source") or ""),
        display_status=str(auction_state.get("display_status") or ""),
        time_left=auction_state.get("time_left"),
        vx=vx,
    )
    sn = build_sniper_decision_row(auction_state, opp, timing_health_overall)
    auction_state["valuation_strength"] = vx.get("valuation_strength") or ""
    auction_state["valuation_flow_label"] = vx.get("valuation_flow_label") or ""
    for k, v in opp.items():
        auction_state[k] = v
    for k, v in sn.items():
        auction_state[k] = v
