"""
pool_view.py — Module 3 of the 24h pipeline rebuild.

Renders the "Morning Briefing" panel at the top of the Ending Soon tab:
the user opens the app and immediately sees everything ending in the next
24 hours, sorted by end-time ascending, with target bids visible for any
card that's already been valued.

Lives in its own module so streamlit_app.py stays minimally touched. To
wire in: import pool_view and call render_morning_briefing() inside the
ending_soon dispatch block.

Reads daily_pool.json. Never writes. Never triggers a live scan. Refresh
is automatic — Streamlit re-runs on every interaction, so the panel always
shows the latest pool state without explicit polling.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Local helper module for Add to Snipes — lazy-imported inside the render
# loop so this module stays importable without snipes_store on the path.

HERE = Path(__file__).parent
POOL_FILE = HERE / "daily_pool.json"


# ── Pool reading (no writes — read-only consumer) ───────────────────────────

def _load_pool() -> Dict[str, Any]:
    if not POOL_FILE.exists():
        return {}
    try:
        return json.loads(POOL_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _to_timestamp(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        try:
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc).timestamp()
            return value.timestamp()
        except Exception:
            return None
    s = str(value).strip().replace(" ", "T", 1)
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        pass
    if s.endswith("Z"):
        try:
            return datetime.fromisoformat(s[:-1] + "+00:00").timestamp()
        except Exception:
            pass
    return None


def _row_seconds_remaining(row: Dict[str, Any]) -> Optional[float]:
    now_ts = time.time()
    v = (row or {}).get("_pool_end_dt_ts")
    try:
        if v is not None:
            return max(0.0, float(v) - now_ts)
    except Exception:
        pass
    for k in ("end_dt", "end_dt_iso"):
        ts = _to_timestamp((row or {}).get(k))
        if ts is not None:
            return max(0.0, ts - now_ts)
    for k in ("remaining_seconds", "seconds_remaining"):
        v = (row or {}).get(k)
        try:
            if v is not None:
                return float(v)
        except Exception:
            pass
    return None


def _row_has_confident_mv(row: Dict[str, Any]) -> bool:
    truth = str((row or {}).get("truth") or "").upper()
    if truth != "TRUE":
        return False
    try:
        mv = (row or {}).get("true_mv") or (row or {}).get("market_value")
        return mv is not None and float(mv) > 0.0
    except Exception:
        return False


def _row_target_bid(row: Dict[str, Any]) -> Optional[float]:
    for k in ("target_bid", "_final_target_bid", "_bid_anchor"):
        v = (row or {}).get(k)
        try:
            if v is not None and float(v) > 0:
                return float(v)
        except Exception:
            pass
    return None


def _row_has_real_mv(row: Dict[str, Any]) -> bool:
    """A row has a "real" MV when the engine produced ANY value — even
    from a single exact-match comp or a confident estimate.

    Philosophy (per user, May 2026): keep exact-match comping even if
    there's only one comp. If no exact comp but the engine has a confident
    estimate, surface it labeled "SnipeWins estimate". Only drop the
    price_anchor_fallback path which is just 75% of current bid (fake).
    """
    if not isinstance(row, dict):
        return False
    mv = row.get("true_mv") or row.get("market_value")
    if mv is None:
        return False
    try:
        if float(mv) <= 0:
            return False
    except Exception:
        return False
    # The only MV we suppress: price_anchor_fallback (target = current × 0.75
    # with no real comp data). Everything else — including single-comp
    # exact matches and machine estimates — is surfaced.
    src = str(row.get("market_value_source") or row.get("_mv_market_value_source") or "").lower()
    if "price_anchor_fallback" in src:
        return False
    return True


def _row_mv_match_quality(row: Dict[str, Any]) -> str:
    """Classify the MV's evidentiary quality:
        'exact'    — engine found 1+ exact-grade comps for this card
        'estimate' — engine produced a value but without exact-grade matches
        'none'     — no MV yet
    Used by the card render to choose between "✓ X exact comps" and
    "≈ SnipeWins estimate" labels.
    """
    if not _row_has_real_mv(row):
        return "none"
    # exact_grade_comp_count is the worker-stamped count of comps that
    # matched the exact grade (or are ungraded matches for raw cards).
    # When > 0 we have an authoritative comp-backed value.
    exact = row.get("_mv_exact_grade_comp_count") or 0
    accepted = row.get("_mv_accepted_comp_count") or row.get("_mv_comp_count") or 0
    try:
        exact_n = int(exact)
        accepted_n = int(accepted)
    except Exception:
        exact_n = 0
        accepted_n = 0
    if exact_n >= 1:
        return "exact"
    if accepted_n >= 1:
        return "estimate"
    # Engine returned a value with literally zero accepted comps —
    # technically an estimate (probably from cross-grade or price-ladder
    # fallback). Surface as estimate, not exact.
    return "estimate"


def _row_exact_comp_count(row: Dict[str, Any]) -> int:
    """Best-available count for the 'X exact comps' label on the card."""
    for k in ("_mv_exact_grade_comp_count", "_mv_accepted_comp_count", "_mv_comp_count"):
        v = (row or {}).get(k)
        try:
            if v is not None and int(v) > 0:
                return int(v)
        except Exception:
            pass
    return 0


def _row_snipewins_estimate(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """DISABLED — kept as a stub for compatibility with the comp expander.
    The formula-based approach (multiply baseline × parallel rarity × auto
    × patch × grade × product tier) was producing falsely-precise dollar
    figures that could mislead users into overbidding. The user correctly
    pointed out: "the machine needs to find similar cards instead of
    multiplying numbers."

    Right approach is relaxed-query comping in valuation_engine — drop
    constraints (year → co-star → dual → /N → grade) until eBay sold
    listings produce real evidence, then surface that. That's a deeper
    engine change being tracked separately.

    Until then, this function returns None so the dashboard shows
    "no comp data yet" honestly, not a fabricated dollar figure.
    """
    return None


def _row_current_price(row: Dict[str, Any]) -> float:
    """Read the current bid / Buy It Now price from the row, trying every
    field variant the engine might stamp."""
    for k in (
        "current_price", "current_bid",
        "_authoritative_current_price", "_board_current_price",
        "authoritative_current_price",
    ):
        v = (row or {}).get(k)
        try:
            if v is not None and float(v) > 0:
                return float(v)
        except Exception:
            pass
    # Nested objects the Browse API hands back. Pre-valuation rows captured
    # straight from `_valuation_candidates_auctions` use these variants
    # rather than the engine-stamped flat fields, so check both.
    for nested_key in ("price", "currentBidPrice"):
        nested = (row or {}).get(nested_key) or {}
        if isinstance(nested, dict):
            v = nested.get("value")
            try:
                if v is not None and float(v) > 0:
                    return float(v)
            except Exception:
                pass
    return 0.0


def _row_image_url(row: Dict[str, Any]) -> Optional[str]:
    """Extract a thumbnail URL for the card image. eBay's Browse API stamps
    `thumbnail` directly and `image.imageUrl` nested. Return s-l225 if we
    have it, otherwise None."""
    for k in ("thumbnail", "image_url", "imageUrl"):
        v = (row or {}).get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v
    nested = (row or {}).get("image") or {}
    if isinstance(nested, dict):
        v = nested.get("imageUrl") or nested.get("image_url")
        if isinstance(v, str) and v.startswith("http"):
            return v
    return None


def _row_ebay_url(row: Dict[str, Any]) -> Optional[str]:
    """Best-effort extraction of the eBay listing URL from a pool row.
    The engine stamps several variants depending on the source; check them
    in priority order. Returns None if nothing usable is found."""
    for k in (
        "url", "_board_url", "alert_listing_url",
        "listing_url", "item_web_url", "itemWebUrl",
        "view_item_url",
    ):
        v = (row or {}).get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v
    # Fall back to constructing one from the item_id.
    item_id = str(
        (row or {}).get("item_id")
        or (row or {}).get("itemId")
        or (row or {}).get("source_item_id")
        or ""
    )
    if "|" in item_id:
        # eBay legacy ID inside a v1| envelope: extract the numeric part.
        parts = item_id.split("|")
        if len(parts) >= 2 and parts[1].isdigit():
            return f"https://www.ebay.com/itm/{parts[1]}"
    elif item_id.isdigit():
        return f"https://www.ebay.com/itm/{item_id}"
    return None


def _format_secs(secs: float) -> str:
    if secs < 60:
        return f"{int(secs)}s"
    if secs < 3600:
        return f"{int(secs / 60)}m"
    if secs < 86400:
        h = int(secs / 3600)
        m = int((secs % 3600) / 60)
        return f"{h}h {m}m"
    return f"{int(secs / 86400)}d"


def _format_money(v: Optional[float]) -> str:
    if v is None or v <= 0:
        return "—"
    return f"${v:,.0f}"


def _hex_to_rgb(hex_color: str) -> str:
    """Convert '#facc15' to '250,204,21' for use inside rgba()."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return "148,163,184"
    try:
        return f"{int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)}"
    except Exception:
        return "148,163,184"


def _strike_zone_state(
    current_bid: float,
    target_bid: Optional[float],
) -> Tuple[str, str, str]:
    """Compute the strike-zone state for a card. Returns (label, bg_color,
    fg_color). When target isn't available, returns a neutral 'PENDING'
    state. Thresholds:
        STRIKE   — current bid is at or below target (immediate snipe window)
        WATCHING — current bid is within 10% above target (close to action)
        WAIT     — current bid exceeds target by >10%
        PENDING  — no target yet (worker still computing MV)
    """
    if not target_bid or target_bid <= 0:
        return "PENDING", "#888888", "#fafafa"
    if not current_bid or current_bid <= 0:
        # No bids yet — anything ≤ target is a strike opportunity
        return "STRIKE", "#4ade80", "#fff"
    ratio = current_bid / target_bid
    if ratio <= 1.0:
        return "STRIKE", "#4ade80", "#fff"
    if ratio <= 1.10:
        return "WATCHING", "#facc15", "#0a0a0a"
    return "WAIT", "#f97316", "#fafafa"


def _row_top_comp(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """RECEIPTS-2026-05-12: return the single most relevant comp dict that
    drove this row's MV — used in the expander as the lead "Primary comp:"
    line AND on the card itself as a tiny "based on: [title] · $X" sub-label
    under MV. Returns None when no comp snapshot is present.

    Selection: prefer comps where value_tier == 'used_in_final_value'; within
    that bucket, prefer the most recent sold_date. Same priority rules the
    full top-3 list uses, just sliced to 1 result.
    """
    try:
        import json as _json
        _raw = row.get("_mv_comps_json")
        if not _raw:
            return None
        _arr = _json.loads(_raw)
        if not isinstance(_arr, list) or not _arr:
            return None
        # Same priority sort as _render_comp_summary top-3 block.
        _by_tier: Dict[int, List[Dict[str, Any]]] = {}
        for _c in _arr:
            if not isinstance(_c, dict) or not (_c.get("price") or 0) > 0:
                continue
            _tier = str(_c.get("value_tier") or "")
            _p = 0 if _tier == "used_in_final_value" else (1 if _tier.startswith("accepted") else 2)
            _by_tier.setdefault(_p, []).append(_c)
        for _p in sorted(_by_tier.keys()):
            _bucket = sorted(_by_tier[_p], key=lambda c: str(c.get("sold_date") or ""), reverse=True)
            if _bucket:
                return _bucket[0]
        return None
    except Exception:
        return None


def _row_comp_summary(row: Dict[str, Any]) -> Dict[str, Any]:
    """Extract comp-summary fields the valuation_worker stamped on the row.
    Returns a dict the dashboard's expander can render. Missing fields
    show up as None — render with a friendly fallback in the UI."""
    return {
        "comp_count":          row.get("_mv_comp_count") or row.get("_mv_accepted_comp_count"),
        "accepted_count":      row.get("_mv_accepted_comp_count"),
        "last_date":           row.get("_mv_last_comp_date"),
        "value_low":           row.get("_mv_value_low"),
        "value_high":          row.get("_mv_value_high"),
        "dominant_low":        row.get("_mv_dominant_range_low"),
        "dominant_high":       row.get("_mv_dominant_range_high"),
        "dominant_count":      row.get("_mv_dominant_comp_count"),
        "recent_7d":           row.get("_mv_recent_comp_count_7d"),
        "recent_30d":          row.get("_mv_recent_comp_count_30d"),
        "auction_count":       row.get("_mv_auction_comp_count"),
        "fixed_price_count":   row.get("_mv_fixed_price_comp_count"),
        "exact_grade_count":   row.get("_mv_exact_grade_comp_count"),
        "valuation_basis":     row.get("_mv_valuation_basis"),
        "source":              row.get("_mv_market_value_source"),
        "cluster_method":      row.get("_mv_cluster_method"),
        "grade_fallback_used": row.get("_mv_grade_fallback_used"),
        "confidence":          row.get("_mv_confidence"),
        # Relaxation ladder metadata (set when comp_relaxer rescued the MV)
        "relax_level":         row.get("_mv_relaxation_level"),
        "relax_label":         row.get("_mv_relaxation_label"),
        "relax_description":   row.get("_mv_relaxation_description"),
        "relax_query":         row.get("_mv_relaxation_query"),
    }


# ── Per-card interactive widgets (Add to Snipes + Comp dropdown) ────────────

def _render_card_actions(streamlit, row: Dict[str, Any], item_id: str) -> None:
    """Render the interactive widgets that sit BELOW each card:
        - "⭐ Add to Snipes" button — persists to snipes.json, fires SMS
          via snipes_store.send_sms_if_configured if Twilio env vars are set
        - "View comps" expander — shows comp-summary data the worker stamped

    Both widgets are Streamlit-native (st.button, st.expander). Each gets
    a unique `key` derived from item_id so re-renders don't collide.
    """
    st = streamlit
    if not item_id:
        return

    # Lazy import — keeps pool_view importable in non-Streamlit contexts.
    try:
        import snipes_store
    except Exception as exc:
        st.caption(f"(snipes_store unavailable: {exc})")
        snipes_store = None

    # MULTI-TENANCY-2026-05-13: snipes are per-user now. The logged-in
    # email comes from session_state (set by trial_gate). Every
    # snipes_store call is scoped to this email.
    _user_email = st.session_state.get("sw_trial_user_email")

    # ── Action row: button + expander side-by-side ───────────────────────
    col_button, col_expander = st.columns([1, 2])

    with col_button:
        if snipes_store is not None:
            already_sniped = snipes_store.is_sniped(_user_email, item_id)
            btn_label = "✓ On snipes list" if already_sniped else "⭐ Add to Snipes"
            btn_disabled = already_sniped
            clicked = st.button(
                btn_label,
                key=f"snipe_btn_{item_id}",
                disabled=btn_disabled,
                use_container_width=True,
            )
            if clicked and not already_sniped:
                snipe = snipes_store.add_snipe(_user_email, row)
                title_short = str(snipe.get("title") or "")[:60]
                st.toast(f"Added to snipes: {title_short}", icon="⭐")
                # Force a re-render so the button shows the new state
                st.rerun()
        else:
            st.caption(" ")

    with col_expander:
        with st.expander("View comps", expanded=False):
            _render_comp_summary(st, row)

    # Tiny vertical breathing room before the next card.
    st.markdown(
        "<div style='height:6px;'></div>",
        unsafe_allow_html=True,
    )


def _render_comp_summary(streamlit, row: Dict[str, Any]) -> None:
    """Render the comp transparency block inside the expander. Three states:
        1. Real comp-backed MV → show comp summary fields the worker stamped
        2. No real MV but SnipeWins estimate produced → show the formula
           breakdown so the user can see how we arrived at the estimate
        3. No MV at all → "still computing" caption
    """
    st = streamlit
    summary = _row_comp_summary(row)
    has_real_mv = _row_has_real_mv(row)

    if not has_real_mv:
        st.markdown(
            "**No comps found yet.** The valuation engine couldn't locate "
            "enough recent eBay sold listings to produce a confident "
            "market value for this card. This is common for brand-new "
            "2026 releases and ultra-rare parallels (/5, /10) where "
            "there are only a handful of these cards in existence."
        )
        st.markdown(
            "**What to do:**\n\n"
            "- Cross-reference with eBay's sold listings filter directly\n"
            "- Look up sister-product comps (e.g., previous year's same player + parallel)\n"
            "- Use the listing's bidding velocity as a signal\n\n"
            "_We don't fabricate dollar figures from formula. As soon as "
            "real comp data appears, the worker will fill this in._"
        )
        return

    # Header — the MV + confidence
    mv_value = float(row.get("true_mv") or row.get("market_value") or 0)
    confidence = str(summary.get("confidence") or "").replace("_", " ").title()
    target = _row_target_bid(row)

    rows: List[str] = []

    # LEAD-COMP-2026-05-12: the single most-relevant comp goes FIRST. The
    # user opens this expander to answer "where did $24 come from?" — they
    # should see the answer in the first sentence, not the 7th line down.
    # FALLBACK-2026-05-12: when the engine produced an MV from range/cluster
    # data but didn't serialize individual comp examples (debug_accepted_
    # comps_json was empty), synthesize a useful line from the dominant
    # cluster stats. Never leave the user staring at just MV + Target.
    _top = _row_top_comp(row)
    if _top:
        _t_title = str(_top.get("title") or "")[:110]
        _t_price = float(_top.get("price") or 0)
        _t_date  = str(_top.get("sold_date") or "")[:10]
        _t_type  = str(_top.get("sale_type") or "").lower()
        _verb    = "sold" if "sold" in _t_type or _t_date else "listed"
        rows.append(
            f"**Primary comp:** _{_t_title}_  ·  "
            f"**${_t_price:,.0f}** {_verb}"
            + (f" {_t_date}" if _t_date else "")
        )
        rows.append("")
    else:
        # No individual comps captured — synthesize a "based on N comps in
        # $X–$Y range" line from whatever cluster data IS stamped. This is
        # the worst-case fallback but still gives the user actionable info.
        _dom_n = summary.get("dominant_count") or summary.get("comp_count") or summary.get("accepted_count")
        _dom_low = summary.get("dominant_low") or summary.get("value_low")
        _dom_high = summary.get("dominant_high") or summary.get("value_high")
        if _dom_n and _dom_low and _dom_high:
            try:
                rows.append(
                    f"**Based on {int(_dom_n)} recent sold comps clustered between** "
                    f"**${float(_dom_low):,.0f}** and **${float(_dom_high):,.0f}**. "
                    f"_(Individual comp examples weren't captured for this "
                    f"valuation path — use the Audit link below to see the "
                    f"underlying eBay sold listings yourself.)_"
                )
                rows.append("")
            except Exception:
                pass

    # RECEIPTS-2026-05-12: when MV is based on similar cards (relaxation
    # ladder), make the receipts loud. The user mandate: "if the machine
    # used a similar card, show it." Three layers of disclosure:
    #   1. The relaxation method ("matched on similar players in this product")
    #   2. The exact eBay search the engine ran
    #   3. A clickable link to that search on eBay's sold listings filter,
    #      so the user can audit in one click without leaving the dashboard.
    relax_level = summary.get("relax_level")
    relax_desc = summary.get("relax_description") or ""
    relax_query = summary.get("relax_query") or ""
    if relax_level is not None and int(relax_level) > 0:
        rows.append(
            f"**Based on similar cards (no exact comps found):** {relax_desc}"
        )
        if relax_query:
            # Build a clickable eBay sold-listings URL so the user can verify
            # the engine's similar-card reasoning in one click.
            from urllib.parse import quote_plus as _qp
            _ebay_sold_url = (
                f"https://www.ebay.com/sch/i.html?_nkw={_qp(relax_query)}"
                f"&LH_Sold=1&LH_Complete=1"
            )
            rows.append(
                f"_Searched eBay sold listings for:_ `{relax_query}` "
                f"[(audit on eBay →)]({_ebay_sold_url})"
            )
        rows.append("---")

    rows.append(
        f"**Market value:** ${mv_value:,.0f}"
        + (f"  ·  confidence: {confidence}" if confidence else "")
    )
    if target and target > 0:
        rows.append(f"**Target bid (75% of MV):** ${target:,.0f}")

    accepted = summary.get("accepted_count")
    comp_count = summary.get("comp_count")
    if accepted or comp_count:
        rows.append(
            f"**Comps used:** {accepted or comp_count} "
            f"({summary.get('recent_7d') or 0} in last 7d, "
            f"{summary.get('recent_30d') or 0} in last 30d)"
        )

    if summary.get("value_low") and summary.get("value_high"):
        rows.append(
            f"**Comp range:** ${float(summary['value_low']):,.0f} – "
            f"${float(summary['value_high']):,.0f}"
        )

    if summary.get("dominant_low") and summary.get("dominant_high"):
        dom_count = summary.get("dominant_count") or "?"
        rows.append(
            f"**Tightest cluster:** ${float(summary['dominant_low']):,.0f} – "
            f"${float(summary['dominant_high']):,.0f} ({dom_count} comps)"
        )

    if summary.get("auction_count") is not None or summary.get("fixed_price_count") is not None:
        rows.append(
            f"**Comp mix:** {summary.get('auction_count') or 0} auction · "
            f"{summary.get('fixed_price_count') or 0} BIN"
        )

    if summary.get("last_date"):
        rows.append(f"**Most recent comp:** {summary['last_date']}")

    if summary.get("valuation_basis"):
        rows.append(f"**Basis:** {summary['valuation_basis']}")

    if summary.get("grade_fallback_used"):
        rows.append("_⚠ Grade fallback used — comps from adjacent grade tier._")

    for line in rows:
        st.markdown(line)

    # AUDIT-2026-05-12: always-on "audit on eBay" CTA. Even when we have a
    # full comp snapshot, the user might want to cross-check against the live
    # eBay sold-listings view. We construct a search from the listing title
    # (trimmed of noise) so one click takes them to a verifiable comp set.
    try:
        _audit_title = str(row.get("title") or row.get("source_title") or "").strip()
        if _audit_title and len(_audit_title) >= 8:
            from urllib.parse import quote_plus as _qp
            # Light cleanup — drop "PSA 10", "BGS 9.5" graders so the sold
            # filter returns broader, more useful comps. The user can re-add
            # if they want grade-specific.
            import re as _re
            _clean = _re.sub(r"\b(PSA|BGS|SGC|CGC)\s*\d+(?:\.\d+)?\b", "", _audit_title, flags=_re.IGNORECASE).strip()
            _clean = _re.sub(r"\s+", " ", _clean)[:140]
            _audit_url = (
                f"https://www.ebay.com/sch/i.html?_nkw={_qp(_clean)}"
                f"&LH_Sold=1&LH_Complete=1"
            )
            st.markdown(
                f"<div style='margin-top:14px;padding-top:10px;"
                f"border-top:1px solid rgba(148,163,184,0.08);'>"
                f"<a href='{_audit_url}' target='_blank' style='"
                f"display:inline-flex;align-items:center;gap:6px;"
                f"padding:6px 12px;background:rgba(59,130,246,0.10);"
                f"border:1px solid rgba(59,130,246,0.25);border-radius:8px;"
                f"font-size:12px;font-weight:600;color:#60a5fa;"
                f"text-decoration:none;'>Audit this on eBay sold listings →</a>"
                f"<span style='font-size:11px;color:#888;margin-left:10px;'>"
                f"Verify our MV against the same data eBay shows you.</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
    except Exception:
        pass

    # TRANSPARENCY-2026-05-12: real comp examples that drove this MV. This
    # converts the dashboard from "trust us" to "here's the receipts" — same
    # transparency eBay's Price Insights tool offers, except ours is forward-
    # looking instead of historical-only. Pulls from _mv_comps_json (snapshot
    # the worker stamps via debug_accepted_comps_json) and renders the 3 most
    # value-relevant entries: prefer comps where value_tier="used_in_final_value"
    # and sale_type="sold" with valid sold_date, sorted by date descending.
    try:
        import json as _json
        _comps_raw = row.get("_mv_comps_json")
        if _comps_raw:
            _comps_list = _json.loads(_comps_raw)
            if isinstance(_comps_list, list) and _comps_list:
                # Filter + sort: prioritize comps used in final value, then by
                # most recent sold_date. Drop any without a meaningful price.
                def _comp_sort_key(c: Dict[str, Any]) -> Tuple[int, str]:
                    _tier = str(c.get("value_tier") or "")
                    _used_priority = 0 if _tier == "used_in_final_value" else (1 if _tier.startswith("accepted") else 2)
                    _date = str(c.get("sold_date") or "")
                    # Sort: lower priority first, then most recent date first
                    return (_used_priority, _date)
                _ranked = sorted(
                    [c for c in _comps_list if isinstance(c, dict) and (c.get("price") or 0) > 0],
                    key=_comp_sort_key,
                    reverse=False,
                )
                # Reverse the date axis: we sorted ascending; flip so newest is first
                # for the same priority bucket. Simple two-step: sort priority asc,
                # then within each priority bucket re-sort date desc.
                _by_tier: Dict[int, List[Dict[str, Any]]] = {}
                for _c in _ranked:
                    _tier = str(_c.get("value_tier") or "")
                    _p = 0 if _tier == "used_in_final_value" else (1 if _tier.startswith("accepted") else 2)
                    _by_tier.setdefault(_p, []).append(_c)
                _final: List[Dict[str, Any]] = []
                for _p in sorted(_by_tier.keys()):
                    _final.extend(sorted(_by_tier[_p], key=lambda c: str(c.get("sold_date") or ""), reverse=True))
                _top = _final[:3]
                if _top:
                    st.markdown("---")
                    st.markdown(f"**Top {len(_top)} comp{'s' if len(_top) != 1 else ''} used:**")
                    for _c in _top:
                        _t = str(_c.get("title") or "")[:90]
                        _p = float(_c.get("price") or 0)
                        _d = str(_c.get("sold_date") or "")[:10]
                        _src = str(_c.get("sale_type") or "")
                        _used_marker = "✓" if str(_c.get("value_tier") or "") == "used_in_final_value" else "·"
                        st.markdown(
                            f"  {_used_marker} ${_p:,.0f}  ·  {_d or 'date unknown'}  "
                            f"·  _{_src}_  \n   <span style='color:#888;font-size:13px;'>{_t}</span>",
                            unsafe_allow_html=True,
                        )
    except Exception:
        # Comp transparency is bonus context — never let a parse error break
        # the main "View comps" expander.
        pass


# ── Public API: the briefing renderer ───────────────────────────────────────

def render_morning_briefing(streamlit, *, max_cards: int = 150) -> None:
    """
    Render the Morning Briefing panel. Pass `streamlit` (the imported `st`
    module) so this module doesn't import streamlit at top level — keeps
    it usable from non-UI contexts (CLI, tests).
    """
    st = streamlit
    pool = _load_pool()
    items: Dict[str, Any] = pool.get("items", {}) or {}

    # Empty state — pool hasn't been populated yet. Match the wallet-card
    # aesthetic so the panel doesn't look broken before the first scan.
    # Single-line HTML to avoid Streamlit's indented-code-block parsing bug.
    if not items:
        # USER-FACING-EMPTY-STATE-2026-05-13: previous copy told the user
        # to "run python daily_pool.py in a separate terminal" — fine for
        # local dev, terrible for actual customers. New copy mirrors the
        # pulse indicator pattern from the landing's "Live" dot and tells
        # the user what's happening and what to do (refresh).
        _empty_html = (
            '<div style="margin:4px 0 18px 0;padding:36px 28px;'
            'background:linear-gradient(135deg,#141414 0%,#0a0a0a 100%);'
            'border:1px solid rgba(148,163,184,0.10);'
            'border-radius:16px;font-family:-apple-system,\'SF Pro Display\',Inter,sans-serif;'
            'color:#fafafa;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,0.25);">'
            '<div style="font-size:11px;font-weight:700;letter-spacing:0.18em;'
            'color:#4ade80;text-transform:uppercase;margin-bottom:14px;">'
            '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;'
            'background:#4ade80;margin-right:8px;vertical-align:middle;'
            'box-shadow:0 0 0 0 rgba(74,222,128,0.6);animation:swPulse 1.6s ease-in-out infinite;"></span>'
            'Scanning eBay</div>'
            '<div style="font-size:20px;font-weight:700;color:#fafafa;margin-bottom:8px;'
            'letter-spacing:-0.01em;">'
            'Building your auction feed…</div>'
            '<div style="font-size:14px;color:#b0b0b0;line-height:1.55;max-width:440px;'
            'margin:0 auto;">'
            "We're combing every relevant eBay auction ending in the next 24 hours "
            'and pulling sold comps to grade each one. Your first batch of cards '
            'arrives within a few minutes. Refresh the page to see new entries as '
            'they land.</div>'
            '<style>@keyframes swPulse{0%,100%{opacity:1;transform:scale(1)}'
            '50%{opacity:0.45;transform:scale(0.82)}}</style>'
            '</div>'
        )
        st.markdown(_empty_html, unsafe_allow_html=True)
        return

    # Bucketize for the headline
    now_ts = time.time()
    buckets = {"<1h": 0, "1-3h": 0, "3-6h": 0, "6-24h": 0, ">24h": 0}
    actionable_rows: List[Tuple[float, Dict[str, Any]]] = []
    confident_count = 0
    for row in items.values():
        if not isinstance(row, dict):
            continue
        secs = _row_seconds_remaining(row)
        if secs is None or secs <= 0:
            continue
        # Bucket
        if secs <= 3600:
            buckets["<1h"] += 1
        elif secs <= 10800:
            buckets["1-3h"] += 1
        elif secs <= 21600:
            buckets["3-6h"] += 1
        elif secs <= 86400:
            buckets["6-24h"] += 1
        else:
            buckets[">24h"] += 1
        # Confident MV
        if _row_has_confident_mv(row):
            confident_count += 1
        # Action queue: anything ending in next 24h
        if secs <= 86400:
            actionable_rows.append((secs, row))

    # SORT-FIX 2026-05-12: pure time-ascending. The tab is named "Ending Soon"
    # — the user opens it when they need to act now, not browse premium tiers.
    # Previously this sorted by chase_priority first (with time as tiebreak),
    # which buried imminent fire cards (22m left, /39 Bowers Orange Finite)
    # underneath premium-tier cards that weren't ending for hours. chase_priority
    # is preserved as a tiebreaker so when two cards end at the same minute,
    # the more premium one wins. Value-based sorting lives on the My Snipes tab
    # where the user has already curated.
    def _sort_key(t: Tuple[float, Dict[str, Any]]) -> Tuple[float, int]:
        secs, row = t
        priority = int(row.get("_chase_priority") or 0)
        return (secs, -priority)
    actionable_rows.sort(key=_sort_key)
    last_fetch_ts = float(pool.get("last_fetch_ts") or 0)
    last_fetch_age = (now_ts - last_fetch_ts) if last_fetch_ts > 0 else float("inf")
    age_str = _format_secs(last_fetch_age) if last_fetch_age != float("inf") else "never"

    # ── Headline panel ───────────────────────────────────────────────────────
    # Time-agnostic branding: "Auction Pool" instead of "Morning Briefing" so
    # the page reads naturally at any hour. Hero number first, supporting
    # metrics under a divider.
    #
    # IMPORTANT: HTML rendered via st.markdown is one long single-line string.
    # Multi-line HTML with indented continuation lines makes Streamlit's
    # markdown parser interpret the indented lines as code blocks (4+ leading
    # spaces = <pre><code>). Keep the markup compact.
    _hero_n   = len(actionable_rows)
    _hero_tgt = confident_count
    _imm = int(buckets.get("<1h") or 0)
    _imm_color = "#ef4444" if _imm > 0 else "#475569"
    _label_css = "font-size:10px;color:#b0b0b0;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:4px;"

    # CURATION-DEPTH-2026-05-12: reach into player_hub to show the breadth
    # of the scan ("we're watching N players across X products"). This is
    # the visible proof of curation depth — it's what justifies the trial
    # subscription regardless of how many auctions happen to be ending in
    # the current 24h window. Failure-quiet: if player_hub isn't available
    # we just skip the line.
    _curation_line = ""
    try:
        import player_hub as _ph
        _state = _ph.load_player_hub_state()
        _all_players = set()
        _all_sports = set()
        for tgt in _ph.build_tracked_scan_targets(_state, listing_mode="auction") or []:
            _pid = str((tgt or {}).get("player_id") or "").strip()
            _sp = str((tgt or {}).get("sport") or "").strip()
            if _pid:
                _all_players.add(_pid)
            if _sp:
                _all_sports.add(_sp)
        if _all_players:
            _sport_label = " / ".join(sorted(_all_sports)) if _all_sports else "all sports"
            _curation_line = (
                f'<div style="margin-top:6px;font-size:12px;color:#888;">'
                f'Continuously scanning <strong style="color:#4ade80;">{len(_all_players)}</strong> '
                f'tracked players across {_sport_label} for premium parallels, autos, and case hits.'
                f'</div>'
            )
    except Exception:
        pass

    _headline_html = (
        f'<div style="margin:4px 0 18px 0;padding:22px 26px;'
        f'background:linear-gradient(135deg,#141414 0%,#0a0a0a 100%);'
        f'border-radius:16px;font-family:-apple-system,\'SF Pro Display\',Inter,sans-serif;'
        f'color:#fafafa;box-shadow:0 4px 20px rgba(0,0,0,0.25);">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
        f'<div>'
        f'<div style="font-size:11px;font-weight:600;letter-spacing:0.18em;color:#4ade80;text-transform:uppercase;margin-bottom:4px;">Auction Pool · Live</div>'
        f'<div style="font-size:42px;font-weight:700;color:#fff;line-height:1.1;letter-spacing:-0.02em;margin-bottom:2px;">{_hero_n}</div>'
        f'<div style="font-size:14px;color:#b0b0b0;">auctions ending in the next 24 hours</div>'
        f'{_curation_line}'
        f'</div>'
        f'<div style="text-align:right;">'
        f'<div style="font-size:11px;color:#888888;margin-bottom:6px;">Updated {age_str} ago</div>'
        f'<div style="display:inline-block;padding:6px 12px;background:rgba(74,222,128,0.12);'
        f'border:1px solid rgba(74,222,128,0.3);border-radius:999px;font-size:13px;color:#4ade80;font-weight:600;">'
        f'{_hero_tgt} with target bid</div>'
        f'</div>'
        f'</div>'
        f'<div style="display:flex;gap:14px;margin-top:18px;padding-top:16px;border-top:1px solid rgba(148,163,184,0.12);">'
        f'<div style="flex:1;"><div style="{_label_css}">&lt; 1h</div>'
        f'<div style="font-size:22px;font-weight:700;color:{_imm_color};">{_imm}</div></div>'
        f'<div style="flex:1;"><div style="{_label_css}">1-3h</div>'
        f'<div style="font-size:22px;font-weight:700;color:#f97316;">{buckets["1-3h"]}</div></div>'
        f'<div style="flex:1;"><div style="{_label_css}">3-6h</div>'
        f'<div style="font-size:22px;font-weight:700;color:#facc15;">{buckets["3-6h"]}</div></div>'
        f'<div style="flex:1;"><div style="{_label_css}">6-24h</div>'
        f'<div style="font-size:22px;font-weight:700;color:#fafafa;">{buckets["6-24h"]}</div></div>'
        f'</div>'
        f'</div>'
    )
    st.markdown(_headline_html, unsafe_allow_html=True)

    if not actionable_rows:
        st.caption("No auctions ending in the next 24 hours match your tracked players.")
        return

    # FILTER-FIX 2026-05-12: time-window chips replaced with sport chips. The
    # tab is "Ending Soon" so the 24h window is the implicit contract — surface
    # buckets ( <1h / 1-3h / 3-6h / 6-24h ) already live in the headline panel
    # above. Sport filter is the more useful axis: most users follow one or
    # two sports and want to slice the feed accordingly. "All" stays default.
    _filter_label = st.radio(
        "Sport",
        options=["All", "NFL", "MLB", "NBA"],
        index=0,
        horizontal=True,
        key="pool_view_filter",
        label_visibility="collapsed",
    )
    def _row_sport(r: Dict[str, Any]) -> str:
        for k in ("sport", "_target_sport", "target_sport", "_row_sport"):
            v = (r or {}).get(k)
            if isinstance(v, str) and v.strip():
                return v.strip().upper()
        return ""
    if _filter_label == "All":
        _window_filtered = [r for s, r in actionable_rows]
    else:
        _window_filtered = [
            r for s, r in actionable_rows
            if _row_sport(r) == _filter_label
        ]

    # ── Per-player diversity cap ─────────────────────────────────────────
    # ABUNDANCE-2026-05-12: cap RELAXED from 3 → 8 per player. The product
    # value is felt-abundance — users who scroll through 100+ curated cards
    # convert at multiples of users who see 11 and bounce. We still keep
    # SOME cap so a single hot player doesn't entirely dominate (e.g. a
    # Caleb Williams release dropping 30 SKUs at once), but the cap is now
    # generous enough that interesting depth always shows. Overflow still
    # exists, it just rarely triggers in practice.
    PER_PLAYER_DISPLAY_CAP = 8
    _player_counts: Dict[str, int] = {}
    _capped_primary: List[Dict[str, Any]] = []
    _capped_overflow: List[Dict[str, Any]] = []
    for _r in _window_filtered:
        _player_key = str(
            (_r or {}).get("target_player_name")
            or (_r or {}).get("canonical_player")
            or (_r or {}).get("player_name")
            or "unknown"
        ).strip().lower()
        _seen = _player_counts.get(_player_key, 0)
        if _seen < PER_PLAYER_DISPLAY_CAP:
            _capped_primary.append(_r)
            _player_counts[_player_key] = _seen + 1
        else:
            _capped_overflow.append(_r)
    # Primary list first (diverse top), then overflow (any extras within cap)
    _filtered = (_capped_primary + _capped_overflow)[:max_cards]

    if not _filtered:
        if _filter_label == "All":
            st.caption("No auctions ending in the next 24 hours.")
        else:
            st.caption(f"No {_filter_label} auctions ending in the next 24 hours.")
        return

    # ── Apple Wallet cards ────────────────────────────────────────────────────
    # Each auction is a self-contained card: thumbnail image, urgency pill,
    # title, three metrics (Bid / Market / Target), and a one-tap eBay link.
    # Honest loading states: MV reads "computing…" and Target reads "coming
    # soon" until the engine produces a real comp-backed valuation. Targets
    # derived from price_anchor_fallback (just 75% of current bid — not a
    # real valuation) are suppressed so the dashboard doesn't lie.
    for row in _filtered:
        secs = _row_seconds_remaining(row) or 0
        title = str(row.get("title") or row.get("source_title") or "").strip()
        # Trim aggressively long titles but preserve the first ~100 chars so
        # the player + product + parallel are still readable.
        if len(title) > 110:
            title = title[:107].rstrip() + "…"
        cur_price = _row_current_price(row)
        has_real_mv = _row_has_real_mv(row)
        # Three-tier MV resolution:
        #   1. Real comp-backed MV from the engine → use it
        #   2. No real MV but row has formula-eligible data → SnipeWins estimate
        #   3. Nothing → show "computing…" placeholder
        snipewins_est: Optional[Dict[str, Any]] = None
        if has_real_mv:
            mv_value = float(row.get("true_mv") or row.get("market_value") or 0)
            target_value = _row_target_bid(row)
            mv_is_estimate = False
        else:
            snipewins_est = _row_snipewins_estimate(row)
            if snipewins_est:
                mv_value = float(snipewins_est.get("estimated_mv") or 0)
                target_value = float(snipewins_est.get("target_bid") or 0)
                mv_is_estimate = True
            else:
                mv_value = None
                target_value = None
                mv_is_estimate = False
        deal_class = str(row.get("deal_class") or "").upper() if has_real_mv else ""
        ebay_url = _row_ebay_url(row)
        img_url = _row_image_url(row)

        # Color the time pill by urgency. Slightly brighter palette than the
        # old list view since the pill is on a darker card.
        if secs <= 1800:
            pill_bg, pill_fg, pill_label = "#ef4444", "#fff", "ENDS SOON"
        elif secs <= 3600:
            pill_bg, pill_fg, pill_label = "#f97316", "#fff", "WITHIN 1H"
        elif secs <= 10800:
            pill_bg, pill_fg, pill_label = "#facc15", "#0a0a0a", "WITHIN 3H"
        elif secs <= 21600:
            pill_bg, pill_fg, pill_label = "#2a2a2a", "#b0b0b0", "WITHIN 6H"
        else:
            pill_bg, pill_fg, pill_label = "#1c1c1c", "#888888", "TODAY"

        # ── Strike Zone badge ────────────────────────────────────────────
        # Replaces the old deal_class badge with a more actionable signal:
        # is the card currently in a strike opportunity, watching range,
        # or wait state? Computed from current_bid vs target_bid.
        sz_label, sz_bg, sz_fg = _strike_zone_state(cur_price, target_value)
        sz_rgb = _hex_to_rgb(sz_bg)
        badge_html = (
            f'<div style="display:inline-block;padding:4px 10px;'
            f'background:rgba({sz_rgb},0.15);border:1px solid {sz_bg};'
            f'border-radius:999px;font-size:10px;font-weight:700;'
            f'color:{sz_bg};letter-spacing:0.1em;">{sz_label}</div>'
        )

        # ── Spread pill ──────────────────────────────────────────────────
        # SPREAD-2026-05-12: this is the "where the money is" claim. When
        # current bid is below MV by a meaningful margin, show a green chip
        # right next to the strike zone badge so the value gap is the first
        # thing the eye lands on. Hidden when MV is missing/loading or when
        # the bid is at/above MV (we don't want to surface those as deals).
        spread_html = ""
        if mv_value is not None and mv_value > 0 and cur_price > 0:
            _spread_dollars = float(mv_value) - float(cur_price)
            if _spread_dollars > 0:
                _spread_pct = _spread_dollars / float(mv_value)
                # Only label as a meaningful spread when >= $5 AND >= 5% — keeps
                # noise off small low-value listings.
                if _spread_dollars >= 5.0 and _spread_pct >= 0.05:
                    _spread_label = f"${_spread_dollars:,.0f} BELOW MV · {int(_spread_pct * 100)}% SPREAD"
                    spread_html = (
                        f'<div style="display:inline-block;padding:4px 10px;'
                        f'background:rgba(74,222,128,0.12);'
                        f'border:1px solid rgba(74,222,128,0.35);'
                        f'border-radius:999px;font-size:10px;font-weight:700;'
                        f'color:#4ade80;letter-spacing:0.08em;'
                        f'margin-right:6px;">{_spread_label}</div>'
                    )

        # MV / Target presentation. Both share the same "honest loading"
        # treatment: the engine computes MV from comp data (the science),
        # then target = MV × 0.75 (deterministic). So when MV isn't real,
        # neither is target — both fall back to muted italic placeholders.
        _label_css = (
            'font-size:10px;color:#b0b0b0;letter-spacing:0.1em;'
            'text-transform:uppercase;margin-bottom:2px;'
        )
        _pending_css = (
            'font-size:14px;font-weight:500;color:#888888;'
            'font-style:italic;padding-top:4px;'
        )
        # MV display with match-quality micro-label below the dollar value.
        # "✓ N exact comps" when the engine found exact-grade matches,
        # "≈ SnipeWins estimate" when produced via fallback/cross-grade, or
        # "computing…" when nothing yet.
        if mv_value is not None and mv_value > 0:
            # Decide which badge to show under MV:
            #   - "✓ N exact comps" when engine had exact-grade matches
            #   - "≈ SnipeWins estimate" when engine fell back to fuzzy comps
            #   - "≈ SnipeWins estimate (no comps)" for our formula fallback
            if mv_is_estimate:
                # Pure formula-based estimate — no comp data at all
                quality_html = (
                    f'<div style="font-size:10px;color:#facc15;font-weight:600;'
                    f'margin-top:2px;">≈ SnipeWins estimate (no comps)</div>'
                )
            else:
                # CONFIDENCE-2026-05-13: always show SOME confidence signal
                # when we have a real MV. Previously cards with `match_quality
                # == None` showed nothing — looked like a number floating in
                # space, no proof. Now every MV gets either:
                #   ✓ N exact comps     (best — exact-grade matches)
                #   ≈ based on N comps  (still real comp data, looser match)
                #   ≈ SnipeWins estimate (no fallback)
                match_quality = _row_mv_match_quality(row)
                # Pull the most-credible comp count we have available.
                _conf_count = (
                    row.get("_mv_exact_grade_comp_count")
                    or row.get("_mv_accepted_comp_count")
                    or row.get("_mv_comp_count")
                    or row.get("_mv_dominant_comp_count")
                    or 0
                )
                try:
                    _conf_count = int(_conf_count)
                except Exception:
                    _conf_count = 0
                if match_quality == "exact":
                    exact_n = _row_exact_comp_count(row)
                    quality_html = (
                        f'<div style="font-size:10px;color:#4ade80;font-weight:600;'
                        f'margin-top:2px;">✓ {exact_n} exact comp{"s" if exact_n != 1 else ""}</div>'
                    )
                elif match_quality == "estimate":
                    if _conf_count > 0:
                        quality_html = (
                            f'<div style="font-size:10px;color:#facc15;font-weight:600;'
                            f'margin-top:2px;">≈ based on {_conf_count} comp'
                            f'{"s" if _conf_count != 1 else ""}</div>'
                        )
                    else:
                        quality_html = (
                            f'<div style="font-size:10px;color:#facc15;font-weight:600;'
                            f'margin-top:2px;">≈ SnipeWins estimate</div>'
                        )
                else:
                    # No match_quality stamp but we have a real MV — show
                    # raw comp count if available so nothing reads as a
                    # number with zero context.
                    if _conf_count > 0:
                        quality_html = (
                            f'<div style="font-size:10px;color:#b0b0b0;font-weight:500;'
                            f'margin-top:2px;">based on {_conf_count} comp'
                            f'{"s" if _conf_count != 1 else ""}</div>'
                        )
                    else:
                        quality_html = ""
                # Append a tiny "cached" tag when the MV came from the
                # title-cache (zero API cost reuse). Signals to power
                # users that we're efficient with their quota.
                if row.get("_mv_from_cache"):
                    _age = int(row.get("_mv_cache_age_secs") or 0)
                    _age_str = (
                        f"{_age // 86400}d ago" if _age >= 86400
                        else f"{_age // 3600}h ago" if _age >= 3600
                        else f"{_age // 60}m ago" if _age >= 60
                        else "just now"
                    )
                    quality_html += (
                        f'<div style="font-size:9px;color:#6b7280;'
                        f'margin-top:1px;font-style:italic;">cached · {_age_str}</div>'
                    )
            # CARD-COMP-2026-05-12: tiny "based on:" sub-label that surfaces
            # the single most-relevant comp directly on the card, no expander
            # required. Truncated hard to one-line — full comp lives in the
            # View comps expander below. Falls back to "N comps · $X–$Y range"
            # when no individual comp snapshot is available (the engine had
            # the data but didn't serialize examples).
            _card_top_comp = _row_top_comp(row)
            _basis_html = ""
            if _card_top_comp:
                _bt_title = str(_card_top_comp.get("title") or "").strip()
                _bt_price = float(_card_top_comp.get("price") or 0)
                if _bt_title and _bt_price > 0:
                    _bt_short = _bt_title if len(_bt_title) <= 55 else _bt_title[:52].rstrip() + "…"
                    _basis_html = (
                        f'<div style="font-size:10px;color:#888888;'
                        f'margin-top:3px;line-height:1.35;">'
                        f'<span style="color:#4ade80;font-weight:600;">${_bt_price:,.0f}</span> '
                        f'comp · {_bt_short}'
                        f'</div>'
                    )
            else:
                _dom_n   = row.get("_mv_dominant_comp_count") or row.get("_mv_accepted_comp_count") or row.get("_mv_comp_count")
                _dom_low = row.get("_mv_dominant_range_low") or row.get("_mv_value_low")
                _dom_high= row.get("_mv_dominant_range_high") or row.get("_mv_value_high")
                try:
                    if _dom_n and _dom_low and _dom_high and int(_dom_n) > 0:
                        _basis_html = (
                            f'<div style="font-size:10px;color:#888888;'
                            f'margin-top:3px;line-height:1.35;">'
                            f'based on <span style="color:#4ade80;font-weight:600;">'
                            f'{int(_dom_n)} comps</span> · '
                            f'${float(_dom_low):,.0f}–${float(_dom_high):,.0f}'
                            f'</div>'
                        )
                except Exception:
                    pass
            mv_block = (
                f'<div style="{_label_css}">Market value</div>'
                f'<div style="font-size:20px;font-weight:700;color:#fafafa;">'
                f'${mv_value:,.0f}</div>'
                f'{quality_html}'
                f'{_basis_html}'
            )
        else:
            # LOADING-STATE-2026-05-13: replace generic "computing…" with
            # signal about WHERE in the pipeline we are. Three states based
            # on what fields the worker has stamped:
            #   1. Compute attempted, no MV → "no comps found, audit on eBay"
            #   2. Compute not attempted → "scanning eBay for comps"
            #   3. Compute failed with error → show the error category
            _attempted = bool(row.get("_mv_compute_attempted"))
            _err = str(row.get("_mv_compute_error") or "").strip()
            if _attempted and _err:
                _err_short = _err.split(":")[0][:20]
                _state_msg = f"comp fetch failed"
                _state_sub = f"<div style='font-size:9px;color:#6b7280;margin-top:3px;'>{_err_short}</div>"
            elif _attempted:
                _state_msg = "no recent comps"
                _state_sub = "<div style='font-size:9px;color:#6b7280;margin-top:3px;'>use Audit link below</div>"
            else:
                _state_msg = "scanning eBay…"
                _state_sub = "<div style='font-size:9px;color:#6b7280;margin-top:3px;'>comps inbound</div>"
            mv_block = (
                f'<div style="{_label_css}">Market value</div>'
                f'<div style="{_pending_css}">{_state_msg}</div>'
                f'{_state_sub}'
            )
        if target_value is not None and target_value > 0:
            target_block = (
                f'<div style="{_label_css}">Target</div>'
                f'<div style="font-size:20px;font-weight:700;color:#4ade80;">'
                f'${target_value:,.0f}</div>'
            )
        else:
            target_block = (
                f'<div style="{_label_css}">Target</div>'
                f'<div style="{_pending_css}">coming soon</div>'
            )

        # Current bid block — unify "no bids yet" vs "we don't know"
        if cur_price > 0:
            current_block = (
                f'<div style="{_label_css}">Current bid</div>'
                f'<div style="font-size:20px;font-weight:700;color:#fafafa;">'
                f'{_format_money(cur_price)}</div>'
            )
        else:
            current_block = (
                f'<div style="{_label_css}">Current bid</div>'
                f'<div style="{_pending_css}">no bids yet</div>'
            )

        # Image — render a clean thumbnail on the left of the card. eBay
        # serves these from i.ebayimg.com so they load fast with no auth.
        if img_url:
            image_html = (
                f'<div style="flex-shrink:0;width:84px;height:84px;'
                f'border-radius:10px;overflow:hidden;background:#0a0a0a;'
                f'border:1px solid rgba(148,163,184,0.12);">'
                f'<img src="{img_url}" alt="" '
                f'style="width:100%;height:100%;object-fit:cover;display:block;" '
                f'loading="lazy" />'
                f'</div>'
            )
        else:
            image_html = (
                f'<div style="flex-shrink:0;width:84px;height:84px;'
                f'border-radius:10px;background:#0a0a0a;'
                f'border:1px solid rgba(148,163,184,0.12);'
                f'display:flex;align-items:center;justify-content:center;'
                f'color:#3a3a3a;font-size:24px;">●</div>'
            )

        # eBay link — render as button when we have a URL, otherwise empty.
        if ebay_url:
            link_html = (
                f'<a href="{ebay_url}" target="_blank" '
                f'style="display:inline-flex;align-items:center;gap:4px;'
                f'padding:8px 14px;background:rgba(74,222,128,0.12);'
                f'border:1px solid rgba(74,222,128,0.3);border-radius:8px;'
                f'font-size:12px;font-weight:600;color:#4ade80;'
                f'text-decoration:none;">View on eBay →</a>'
            )
        else:
            link_html = '<span></span>'

        # Build the whole card as a single-line HTML string. Streamlit's
        # markdown parser treats indented continuation lines as code blocks,
        # so multi-line HTML breaks rendering on dynamic content. Layout is
        # image-on-left, content-on-right, with the bottom metric row using
        # the prebuilt blocks above so loading states stay consistent.
        card_html = (
            f'<div style="margin:10px 0;padding:16px 18px;'
            f'background:linear-gradient(180deg,#141414 0%,#1c1c1c 100%);'
            f'border-radius:14px;font-family:-apple-system,\'SF Pro Display\',Inter,sans-serif;'
            f'color:#fafafa;box-shadow:0 2px 12px rgba(0,0,0,0.2);'
            f'border:1px solid rgba(148,163,184,0.08);'
            f'display:flex;gap:16px;">'
            # Left column: image
            f'{image_html}'
            # Right column: header + title + metrics
            f'<div style="flex:1;min-width:0;display:flex;flex-direction:column;">'
            # Header row: timer pill (left) + spread + strike zone badge (right)
            f'<div style="display:flex;justify-content:space-between;'
            f'align-items:center;margin-bottom:8px;gap:8px;flex-wrap:wrap;">'
            f'<span style="background:{pill_bg};color:{pill_fg};font-weight:700;'
            f'font-size:10px;padding:5px 10px;border-radius:999px;'
            f'letter-spacing:0.08em;">{pill_label} · {_format_secs(secs)}</span>'
            f'<div style="display:flex;align-items:center;flex-wrap:wrap;">'
            f'{spread_html}{badge_html}'
            f'</div>'
            f'</div>'
            # Title
            f'<div style="font-size:15px;font-weight:600;color:#fafafa;'
            f'line-height:1.35;margin-bottom:12px;">{title}</div>'
            # Bottom metrics row
            f'<div style="display:flex;align-items:flex-end;gap:18px;padding-top:12px;'
            f'border-top:1px solid rgba(148,163,184,0.08);margin-top:auto;">'
            f'<div style="flex:1;">{current_block}</div>'
            f'<div style="flex:1;">{mv_block}</div>'
            f'<div style="flex:1;">{target_block}</div>'
            f'<div style="flex-shrink:0;">{link_html}</div>'
            f'</div>'
            f'</div>'  # close right column
            f'</div>'  # close card
        )

        # Render card + interactive widgets inside a single container so
        # Streamlit visually groups them. The button and expander stack
        # below the card HTML.
        item_id = str(
            row.get("item_id")
            or row.get("itemId")
            or row.get("source_item_id")
            or ""
        )
        with st.container():
            st.markdown(card_html, unsafe_allow_html=True)
            _render_card_actions(st, row, item_id)

    if len(actionable_rows) > len(_filtered):
        st.caption(
            f"Showing top {len(_filtered)} of {len([r for s, r in actionable_rows if s <= _max_secs])}. "
            f"Adjust filter above to see more."
        )
