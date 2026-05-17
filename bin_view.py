"""
bin_view.py — Renders the Buying Radar tab.

Mirror of pool_view.py for BIN listings. Same wallet-card aesthetic,
same Strike Zone logic, same Add to Snipes / View comps actions —
just pointed at bin_pool.json instead of daily_pool.json.

UX differences from Ending Soon:
    - No countdown badge. BIN listings don't end on a timer.
    - "Listed Xh ago" pill shows freshness instead.
    - Sort by "discount-to-MV descending" so the steepest deals float
      to the top (instead of time-ascending).
    - Strike Zone semantics tighter: STRIKE = BIN price <= target.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


HERE = Path(__file__).parent
# PERSISTENT-POOL-2026-05-15: must match the path used by daily_bin_pool.py
# (writer). Render env: SNIPEWINS_BIN_POOL_PATH=/data/bin_pool.json.
POOL_FILE = Path(os.environ.get("SNIPEWINS_BIN_POOL_PATH") or str(HERE / "bin_pool.json"))


# MOBILE-CSS-2026-05-17: cards were squished on phones because the 4-column
# footer (BIN / MV / Target / link) doesn't fit at 360-414px viewports. We
# can't put @media queries inside inline style attributes, so we tag the
# card pieces with classes and inject a <style> block once per session that
# overrides the inline styles with !important on small screens. Stacks the
# footer into a 2x2 grid + full-width link, shrinks the image and padding.
_MOBILE_CARD_CSS = """<style>
@media (max-width: 640px) {
  .snipe-card { padding: 12px 14px !important; gap: 12px !important; }
  .snipe-card-image { width: 64px !important; height: 64px !important; }
  .snipe-card-title { font-size: 13.5px !important; line-height: 1.3 !important; margin-bottom: 10px !important; }
  .snipe-card-footer { flex-wrap: wrap !important; gap: 10px 14px !important; align-items: flex-start !important; }
  .snipe-card-footer > div { flex: 1 1 40% !important; min-width: 0 !important; }
  .snipe-card-footer > .snipe-card-link { flex: 1 1 100% !important; margin-top: 4px !important; }
  .snipe-card-footer .snipe-card-link a { display: flex !important; justify-content: center !important; width: 100% !important; box-sizing: border-box !important; }
}
/* SEARCH-BUTTON-2026-05-17: hollow brand-green primary button — see
   pool_view.py for the same block + rationale. Matches the "View on eBay"
   button style on the cards exactly so the two visual elements feel
   like siblings rather than competing accents. */
.stButton > button[kind="primary"],
button[data-testid="baseButton-primary"],
button[data-testid="stBaseButton-primary"] {
  background: rgba(74,222,128,0.12) !important;
  color: #4ade80 !important;
  border: 1px solid rgba(74,222,128,0.3) !important;
  font-weight: 600 !important;
  letter-spacing: 0.02em !important;
  box-shadow: none !important;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.05s ease !important;
}
.stButton > button[kind="primary"] *,
button[data-testid="baseButton-primary"] *,
button[data-testid="stBaseButton-primary"] * {
  color: #4ade80 !important;
}
.stButton > button[kind="primary"]:hover,
button[data-testid="baseButton-primary"]:hover,
button[data-testid="stBaseButton-primary"]:hover {
  background: rgba(74,222,128,0.22) !important;
  border-color: rgba(74,222,128,0.55) !important;
  color: #4ade80 !important;
}
.stButton > button[kind="primary"]:active,
button[data-testid="baseButton-primary"]:active,
button[data-testid="stBaseButton-primary"]:active {
  transform: translateY(1px) !important;
}
</style>"""


def _inject_mobile_card_css(st) -> None:
    """Emit the responsive style block once per session. Cheap to call
    repeatedly thanks to the session_state guard."""
    try:
        if st.session_state.get("_snipewins_mobile_card_css_v1"):
            return
        st.markdown(_MOBILE_CARD_CSS, unsafe_allow_html=True)
        st.session_state["_snipewins_mobile_card_css_v1"] = True
    except Exception:
        # Worst case we emit the style block twice — harmless.
        try:
            st.markdown(_MOBILE_CARD_CSS, unsafe_allow_html=True)
        except Exception:
            pass


# ── Pool reading ────────────────────────────────────────────────────────────

def _load_pool() -> Dict[str, Any]:
    if not POOL_FILE.exists():
        return {}
    try:
        return json.loads(POOL_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── Field readers (reuse same field-coverage logic as pool_view.py) ─────────

def _row_current_price(row: Dict[str, Any]) -> float:
    for k in (
        "current_price", "current_bid",
        "_authoritative_current_price", "_board_current_price",
    ):
        v = (row or {}).get(k)
        try:
            if v is not None and float(v) > 0:
                return float(v)
        except Exception:
            pass
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
    for k in ("url", "_board_url", "itemWebUrl", "listing_url"):
        v = (row or {}).get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v
    item_id = str(
        (row or {}).get("item_id")
        or (row or {}).get("itemId")
        or (row or {}).get("source_item_id")
        or ""
    )
    if "|" in item_id:
        parts = item_id.split("|")
        if len(parts) >= 2 and parts[1].isdigit():
            return f"https://www.ebay.com/itm/{parts[1]}"
    return None


def _row_top_comp(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Single most-relevant comp that drove this row's MV — used as the
    Primary comp line in the expander and as a tiny basis sub-label on
    the card. Mirrors pool_view._row_top_comp."""
    try:
        import json as _json
        _raw = row.get("_mv_comps_json")
        if not _raw:
            return None
        _arr = _json.loads(_raw)
        if not isinstance(_arr, list) or not _arr:
            return None
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


def _row_has_real_mv(row: Dict[str, Any]) -> bool:
    mv = row.get("true_mv") or row.get("market_value")
    if mv is None:
        return False
    try:
        if float(mv) <= 0:
            return False
    except Exception:
        return False
    src = str(row.get("market_value_source") or row.get("_mv_market_value_source") or "").lower()
    if "price_anchor_fallback" in src:
        return False
    return True


def _row_target_bid(row: Dict[str, Any]) -> Optional[float]:
    for k in ("target_bid", "_final_target_bid", "_bid_anchor"):
        v = (row or {}).get(k)
        try:
            if v is not None and float(v) > 0:
                return float(v)
        except Exception:
            pass
    return None


def _row_listed_age_secs(row: Dict[str, Any]) -> Optional[float]:
    """How long has this BIN been listed? Pulls from itemCreationDate /
    itemOriginDate / _pool_first_seen_ts whichever is available."""
    now = time.time()
    # Engine-stamped first-seen — most reliable
    fs = row.get("_pool_first_seen_ts")
    try:
        if fs is not None:
            return now - float(fs)
    except Exception:
        pass
    # eBay-provided listing creation date (ISO 8601)
    for k in ("itemCreationDate", "itemOriginDate"):
        s = row.get(k)
        if isinstance(s, str) and s:
            try:
                from datetime import datetime
                # "2026-05-04T00:27:19.000Z" — handle Z suffix
                dt_s = s.rstrip("Z")
                if "." in dt_s:
                    dt_s = dt_s.split(".")[0]
                dt = datetime.fromisoformat(dt_s)
                return now - dt.timestamp()
            except Exception:
                pass
    return None


def _format_listed_age(secs: Optional[float]) -> str:
    if secs is None:
        return "?"
    if secs < 3600:
        return f"{int(secs / 60)}m ago"
    if secs < 86400:
        return f"{int(secs / 3600)}h ago"
    if secs < 86400 * 7:
        return f"{int(secs / 86400)}d ago"
    return f"{int(secs / 86400 / 7)}w ago"


def _format_money(v: Optional[float]) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
    except Exception:
        return "—"
    if f <= 0:
        return "—"
    return f"${f:,.0f}"


def _hex_to_rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return "148,163,184"
    try:
        return f"{int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)}"
    except Exception:
        return "148,163,184"


# ── Strike Zone — BIN semantics ─────────────────────────────────────────────

def _row_accepts_offers(row: Dict[str, Any]) -> bool:
    """RECOMMENDED-OFFER-2026-05-13: True if this BIN listing accepts
    eBay Best Offers. The scanner stamps `buying_options` from the Browse
    API — a list like ["FIXED_PRICE"] or ["FIXED_PRICE","BEST_OFFER"].
    Degrades safely: if the field is missing (old pool data, or the
    scanner change hasn't deployed yet) this returns False and the UI
    behaves exactly as before."""
    opts = (row or {}).get("buying_options") or (row or {}).get("buyingOptions") or []
    if isinstance(opts, str):
        opts = [opts]
    try:
        return any(str(o or "").strip().upper() == "BEST_OFFER" for o in opts)
    except Exception:
        return False


def _strike_zone_state(
    bin_price: float,
    target_bid: Optional[float],
    accepts_offers: bool = False,
) -> Tuple[str, str, str]:
    """For BIN:
        STRIKE   — BIN price <= target (instant buy opportunity)
        CLOSE    — BIN price within 15% of target (negotiable via Best Offer)
        OFFER    — BIN price > 15% above target BUT the listing accepts
                   Best Offers — actionable via a Recommended Offer
        WAIT     — BIN price > 15% above target, no offers accepted
        PENDING  — no target yet

    RECOMMENDED-OFFER-2026-05-13: the OFFER state is new. Before this, a
    listing priced above target was just "WAIT" and effectively dead
    inventory. Now, if the seller accepts offers, we surface it with a
    Recommended Offer (= the target bid) — the user can still land a
    good deal by negotiating. Expands felt-abundance, which the project
    notes flag as a conversion lever.
    """
    if not target_bid or target_bid <= 0:
        return "PENDING", "#888888", "#fafafa"
    if not bin_price or bin_price <= 0:
        return "PENDING", "#888888", "#fafafa"
    ratio = bin_price / target_bid
    if ratio <= 1.0:
        return "STRIKE", "#4ade80", "#fff"
    if ratio <= 1.15:
        return "CLOSE", "#facc15", "#0a0a0a"
    if accepts_offers:
        # Above target, but negotiable. Blue to read as "actionable" without
        # competing with STRIKE green or CLOSE amber.
        return "OFFER", "#3b82f6", "#fff"
    return "WAIT", "#888888", "#fafafa"


def _discount_to_mv(bin_price: float, mv: Optional[float]) -> Optional[float]:
    """Compute the discount percentage of BIN price vs market value.
    Used for sort priority. Negative when BIN is above MV (overpriced)."""
    if not mv or mv <= 0 or not bin_price or bin_price <= 0:
        return None
    return (mv - bin_price) / mv


# ── Per-card action row (mirrors pool_view._render_card_actions) ────────────

def _render_card_actions(streamlit, row: Dict[str, Any], item_id: str) -> None:
    st = streamlit
    if not item_id:
        return
    try:
        import snipes_store
    except Exception as exc:
        st.caption(f"(snipes_store unavailable: {exc})")
        snipes_store = None

    # MULTI-TENANCY-2026-05-13: snipes are per-user — scope every call
    # to the logged-in email from session_state.
    _user_email = st.session_state.get("sw_trial_user_email")

    col_button, col_expander = st.columns([1, 2])
    with col_button:
        if snipes_store is not None:
            already = snipes_store.is_sniped(_user_email, item_id)
            btn_label = "✓ On snipes list" if already else "⭐ Add to Snipes"
            clicked = st.button(
                btn_label,
                key=f"bin_snipe_btn_{item_id}",
                disabled=already,
                use_container_width=True,
            )
            if clicked and not already:
                snipe = snipes_store.add_snipe(_user_email, row)
                title_short = str(snipe.get("title") or "")[:60]
                st.toast(f"Added to snipes: {title_short}", icon="⭐")
                st.rerun()
    with col_expander:
        with st.expander("View comps", expanded=False):
            _render_comp_summary(st, row)
    st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)


def _render_comp_summary(streamlit, row: Dict[str, Any]) -> None:
    st = streamlit
    has_real_mv = _row_has_real_mv(row)
    if not has_real_mv:
        st.markdown(
            "**No comps found yet.** The valuation engine is still working "
            "on this card or couldn't find enough recent eBay sold listings."
        )
        # AUDIT-LINK-2026-05-15: render the same one-click audit link the
        # MV'd cards get. Matches pool_view's no-comps fallback.
        try:
            _audit_title = str(row.get("title") or row.get("source_title") or "").strip()
            if _audit_title and len(_audit_title) >= 8:
                from urllib.parse import quote_plus as _qp
                import re as _re
                _clean = _re.sub(
                    r"\b(PSA|BGS|SGC|CGC)\s*\d+(?:\.\d+)?\b", "",
                    _audit_title, flags=_re.IGNORECASE,
                ).strip()
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
                    f"Check sold prices for this exact card on eBay.</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        except Exception:
            pass
        return
    mv_value = float(row.get("true_mv") or row.get("market_value") or 0)
    target = _row_target_bid(row)
    relax_level = row.get("_mv_relaxation_level")
    relax_desc = row.get("_mv_relaxation_description") or ""
    relax_query = row.get("_mv_relaxation_query") or ""

    rows: List[str] = []
    # Lead with the most relevant comp — same Primary comp treatment as
    # pool_view, so the user sees "where did $24 come from" instantly.
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
        # No individual snapshot — synthesize from cluster stats so the user
        # always sees evidence behind the MV number.
        _dom_n = row.get("_mv_dominant_comp_count") or row.get("_mv_accepted_comp_count") or row.get("_mv_comp_count")
        _dom_low = row.get("_mv_dominant_range_low") or row.get("_mv_value_low")
        _dom_high = row.get("_mv_dominant_range_high") or row.get("_mv_value_high")
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
    if relax_level is not None and int(relax_level) > 0:
        rows.append(f"**Based on similar cards (no exact comps found):** {relax_desc}")
        if relax_query:
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
    rows.append(f"**Market value:** ${mv_value:,.0f}")
    if target and target > 0:
        rows.append(f"**Target bid (75% of MV):** ${target:,.0f}")

    comp_count = row.get("_mv_accepted_comp_count") or row.get("_mv_comp_count")
    if comp_count:
        rows.append(
            f"**Comps used:** {comp_count} "
            f"({row.get('_mv_recent_comp_count_7d') or 0} in last 7d, "
            f"{row.get('_mv_recent_comp_count_30d') or 0} in last 30d)"
        )
    if row.get("_mv_value_low") and row.get("_mv_value_high"):
        rows.append(
            f"**Comp range:** ${float(row['_mv_value_low']):,.0f} – "
            f"${float(row['_mv_value_high']):,.0f}"
        )
    for line in rows:
        st.markdown(line)

    # TRANSPARENCY-2026-05-12: mirror the comp evidence reveal from pool_view
    # so Steals cards also show the actual comps used. Same parser, same trust
    # layer for BIN listings.
    try:
        import json as _json
        _comps_raw = row.get("_mv_comps_json")
        if _comps_raw:
            _comps_list = _json.loads(_comps_raw)
            if isinstance(_comps_list, list) and _comps_list:
                _by_tier: Dict[int, List[Dict[str, Any]]] = {}
                for _c in _comps_list:
                    if not isinstance(_c, dict) or not (_c.get("price") or 0) > 0:
                        continue
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
        pass

    # AUDIT-2026-05-12: always-on "audit on eBay" CTA for Steals too. Same
    # treatment as pool_view — one click takes the user to the eBay sold-
    # listings filter so they can verify the MV against the same data eBay's
    # own price tool uses.
    try:
        _audit_title = str(row.get("title") or row.get("source_title") or "").strip()
        if _audit_title and len(_audit_title) >= 8:
            from urllib.parse import quote_plus as _qp
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


# ── Public API: the radar renderer ──────────────────────────────────────────

def render_bin_radar(streamlit, *, max_cards: int = 30) -> None:
    """Render the Buying Radar tab — continuous BIN feed."""
    st = streamlit
    # MOBILE-CSS-2026-05-17: emit responsive overrides before any card render.
    _inject_mobile_card_css(st)
    pool = _load_pool()
    items: Dict[str, Any] = pool.get("items", {}) or {}

    # Empty state — match the pool_view "scanning eBay" treatment so both
    # tabs feel like part of the same product when they're empty.
    if not items:
        st.markdown(
            "<div style='margin:4px 0 18px 0;padding:36px 28px;"
            "background:linear-gradient(135deg,#161616 0%,#0a0a0a 100%);"
            "border:1px solid rgba(148,163,184,0.10);"
            "border-radius:16px;font-family:-apple-system,\\'SF Pro Display\\',Inter,sans-serif;"
            "color:#fafafa;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,0.25);'>"
            "<div style='font-size:11px;font-weight:700;letter-spacing:0.18em;"
            "color:#4ade80;text-transform:uppercase;margin-bottom:14px;'>"
            "<span style='display:inline-block;width:7px;height:7px;border-radius:50%;"
            "background:#4ade80;margin-right:8px;vertical-align:middle;"
            "animation:swPulse 1.6s ease-in-out infinite;'></span>"
            "Scanning Buy It Now</div>"
            "<div style='font-size:20px;font-weight:700;color:#fafafa;margin-bottom:8px;"
            "letter-spacing:-0.01em;'>"
            "Hunting for steals…</div>"
            "<div style='font-size:14px;color:#b0b0b0;line-height:1.55;max-width:440px;"
            "margin:0 auto;'>"
            "We're scanning live buy-it-now listings for cards priced under their "
            "market value. Steals usually start landing here within 15 minutes. "
            "Refresh the page to see new entries as they're found."
            "</div>"
            "<style>@keyframes swPulse{0%,100%{opacity:1;transform:scale(1)}"
            "50%{opacity:0.45;transform:scale(0.82)}}</style>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    # ── Collect actionable rows + compute discount-to-MV for sorting ──
    actionable: List[Tuple[float, Dict[str, Any]]] = []
    pending_count = 0
    strike_count = 0
    close_count = 0
    offer_count = 0   # RECOMMENDED-OFFER-2026-05-13
    for row in items.values():
        if not isinstance(row, dict):
            continue
        bin_price = _row_current_price(row)
        mv = row.get("true_mv") or row.get("market_value") if _row_has_real_mv(row) else None
        target = _row_target_bid(row) if _row_has_real_mv(row) else None
        # Sort key — discount-to-MV descending. Rows with no MV go to bottom.
        discount = _discount_to_mv(bin_price, mv) if mv else None
        sort_key = -(discount or -1.0)   # negate so high discount = low sort key = top
        actionable.append((sort_key, row))
        sz_label, _, _ = _strike_zone_state(bin_price, target, _row_accepts_offers(row))
        if sz_label == "STRIKE":
            strike_count += 1
        elif sz_label == "CLOSE":
            close_count += 1
        elif sz_label == "OFFER":
            offer_count += 1
        elif sz_label == "PENDING":
            pending_count += 1
    actionable.sort(key=lambda t: t[0])

    last_fetch_ts = float(pool.get("last_fetch_ts") or 0)
    last_fetch_age = (time.time() - last_fetch_ts) if last_fetch_ts > 0 else float("inf")
    if last_fetch_age == float("inf"):
        age_str = "never"
    elif last_fetch_age < 60:
        age_str = f"{int(last_fetch_age)}s"
    elif last_fetch_age < 3600:
        age_str = f"{int(last_fetch_age / 60)}m"
    elif last_fetch_age < 86400:
        age_str = f"{int(last_fetch_age / 3600)}h {int((last_fetch_age % 3600) / 60)}m"
    else:
        age_str = f"{int(last_fetch_age / 86400)}d"

    # ── Headline panel — focused on STRIKE count ───────────────────────────
    _label_css = (
        'font-size:10px;color:#b0b0b0;letter-spacing:0.12em;'
        'text-transform:uppercase;margin-bottom:4px;'
    )
    _headline_html = (
        f'<div style="margin:4px 0 18px 0;padding:22px 26px;'
        f'background:linear-gradient(135deg,#161616 0%,#0a0a0a 100%);'
        f'border-radius:16px;font-family:-apple-system,\'SF Pro Display\',Inter,sans-serif;'
        f'color:#fafafa;box-shadow:0 4px 20px rgba(0,0,0,0.25);">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
        f'<div>'
        f'<div style="font-size:11px;font-weight:600;letter-spacing:0.18em;color:#4ade80;text-transform:uppercase;margin-bottom:4px;">Steals · Live</div>'
        f'<div style="font-size:42px;font-weight:700;color:#fff;line-height:1.1;letter-spacing:-0.02em;margin-bottom:2px;">{len(items)}</div>'
        f'<div style="font-size:14px;color:#b0b0b0;">BIN listings tracked</div>'
        f'</div>'
        f'<div style="text-align:right;">'
        f'<div style="font-size:11px;color:#888888;margin-bottom:6px;">Updated {age_str} ago</div>'
        f'<div style="display:inline-block;padding:6px 12px;background:rgba(74,222,128,0.12);'
        f'border:1px solid rgba(74,222,128,0.3);border-radius:999px;font-size:13px;color:#4ade80;font-weight:600;">'
        f'{strike_count} strikes available</div>'
        f'</div>'
        f'</div>'
        f'<div style="display:flex;gap:14px;margin-top:18px;padding-top:16px;border-top:1px solid rgba(148,163,184,0.12);">'
        f'<div style="flex:1;"><div style="{_label_css}">Strike</div>'
        f'<div style="font-size:22px;font-weight:700;color:#4ade80;">{strike_count}</div></div>'
        f'<div style="flex:1;"><div style="{_label_css}">Close</div>'
        f'<div style="font-size:22px;font-weight:700;color:#facc15;">{close_count}</div></div>'
        f'<div style="flex:1;"><div style="{_label_css}">Offer</div>'
        f'<div style="font-size:22px;font-weight:700;color:#3b82f6;">{offer_count}</div></div>'
        f'<div style="flex:1;"><div style="{_label_css}">Pending MV</div>'
        f'<div style="font-size:22px;font-weight:700;color:#fafafa;">{pending_count}</div></div>'
        f'</div>'
        f'</div>'
    )
    st.markdown(_headline_html, unsafe_allow_html=True)

    # TITLE-SEARCH-2026-05-17: free-text search box, same UX as pool_view.
    # Multi-word queries are AND'd against title + source_title, so typing
    # "judge auto" matches listings with both words in any order.
    # SEARCH-BUTTON-2026-05-17: input + green "Search" button on the same row.
    _search_cols = st.columns([6, 1], gap="small")
    with _search_cols[0]:
        _search_q = st.text_input(
            "Search BIN listings",
            value="",
            placeholder="Search by player, set, parallel… (e.g. 'Wemby Prizm')",
            key="bin_view_search",
            label_visibility="collapsed",
        )
    with _search_cols[1]:
        st.button(
            "Search",
            key="bin_view_search_btn",
            type="primary",
            use_container_width=True,
        )
    _search_norm = (_search_q or "").strip().lower()

    # Filter chip — Strikes / Actionable / All. RECOMMENDED-OFFER-2026-05-13:
    # the middle option now covers everything the user can act on right
    # now — STRIKE (buy it), CLOSE (offer to close the gap), and OFFER
    # (priced above target but negotiable via Best Offer).
    _filter_label = st.radio(
        "Filter",
        options=["Strikes only", "Strike · Close · Offer", "All"],
        index=0,
        horizontal=True,
        key="bin_view_filter",
        label_visibility="collapsed",
    )

    # TITLE-SEARCH-2026-05-17: helper to assemble the searchable haystack
    # for each row. Combined title + source_title catches both display
    # title and raw eBay title.
    def _title_haystack(r: Dict[str, Any]) -> str:
        return " ".join(str(r.get(k) or "") for k in ("title", "source_title")).lower()
    _search_terms = [t for t in _search_norm.split() if t]

    filtered: List[Dict[str, Any]] = []
    for _sort_key, row in actionable:
        bin_price = _row_current_price(row)
        target = _row_target_bid(row) if _row_has_real_mv(row) else None
        sz_label, _, _ = _strike_zone_state(bin_price, target, _row_accepts_offers(row))
        if _filter_label == "Strikes only" and sz_label != "STRIKE":
            continue
        if _filter_label == "Strike · Close · Offer" and sz_label not in {"STRIKE", "CLOSE", "OFFER"}:
            continue
        # TITLE-SEARCH-2026-05-17: apply search after the zone filter so a
        # title hit still has to pass the same zone gate.
        if _search_terms:
            _hay = _title_haystack(row)
            if not all(_t in _hay for _t in _search_terms):
                continue
        filtered.append(row)
    filtered = filtered[:max_cards]

    if not filtered:
        # TITLE-SEARCH-2026-05-17: search-specific empty state if the search
        # box has content, so the user knows what they're seeing zero of.
        if _search_norm:
            st.caption(f"No BIN listings match “{_search_q}”. Clear the search to see all.")
        else:
            st.caption(f"No {_filter_label.lower()} right now. Try a wider filter or refresh.")
        return

    # ── Per-card render — wallet style ────────────────────────────────────
    for row in filtered:
        title = str(row.get("title") or row.get("source_title") or "").strip()
        if len(title) > 110:
            title = title[:107].rstrip() + "…"
        bin_price = _row_current_price(row)
        has_real_mv = _row_has_real_mv(row)
        if has_real_mv:
            mv_value = float(row.get("true_mv") or row.get("market_value") or 0)
            target_value = _row_target_bid(row)
        else:
            mv_value = None
            target_value = None
        ebay_url = _row_ebay_url(row)
        img_url = _row_image_url(row)
        listed_age = _row_listed_age_secs(row)
        listed_str = _format_listed_age(listed_age)

        # Strike Zone badge. RECOMMENDED-OFFER-2026-05-13: pass accepts_offers
        # so an above-target listing that takes Best Offers shows as OFFER
        # rather than dead-weight WAIT.
        _accepts_offers = _row_accepts_offers(row)
        sz_label, sz_bg, sz_fg = _strike_zone_state(bin_price, target_value, _accepts_offers)
        sz_rgb = _hex_to_rgb(sz_bg)
        sz_html = (
            f'<div style="display:inline-block;padding:4px 10px;'
            f'background:rgba({sz_rgb},0.15);border:1px solid {sz_bg};'
            f'border-radius:999px;font-size:10px;font-weight:700;'
            f'color:{sz_bg};letter-spacing:0.1em;">{sz_label}</div>'
        )

        # Discount-to-MV badge (only when MV is real)
        # SPREAD-2026-05-12: upgraded from a small inline span to a proper
        # pill matching the Ending Soon treatment. Same threshold (≥$5 AND
        # ≥5%) keeps low-noise listings out of the spread call-out.
        discount = _discount_to_mv(bin_price, mv_value) if mv_value else None
        discount_html = ""
        if (
            mv_value is not None and mv_value > 0
            and bin_price > 0
            and discount is not None and discount > 0
        ):
            _spread_dollars = float(mv_value) - float(bin_price)
            if _spread_dollars >= 5.0 and discount >= 0.05:
                _spread_label = f"${_spread_dollars:,.0f} BELOW MV · {int(discount * 100)}% SPREAD"
                discount_html = (
                    f'<div style="display:inline-block;padding:4px 10px;'
                    f'background:rgba(74,222,128,0.12);'
                    f'border:1px solid rgba(74,222,128,0.35);'
                    f'border-radius:999px;font-size:10px;font-weight:700;'
                    f'color:#4ade80;letter-spacing:0.08em;'
                    f'margin-right:6px;">{_spread_label}</div>'
                )

        # RECOMMENDED-OFFER-2026-05-13: when a listing is in the OFFER zone
        # (priced above target but accepts Best Offers), surface the
        # recommended offer number — which is just the target bid. This
        # turns "skip it" inventory into "negotiate it" inventory. Rendered
        # as a blue pill that pairs with the OFFER strike-zone badge.
        recommend_offer_html = ""
        if sz_label == "OFFER" and target_value and target_value > 0:
            recommend_offer_html = (
                f'<div style="display:inline-block;padding:4px 10px;'
                f'background:rgba(59,130,246,0.12);'
                f'border:1px solid rgba(59,130,246,0.35);'
                f'border-radius:999px;font-size:10px;font-weight:700;'
                f'color:#3b82f6;letter-spacing:0.08em;'
                f'margin-right:6px;">RECOMMENDED OFFER ${target_value:,.0f}</div>'
            )

        # Image + link + blocks
        if img_url:
            image_html = (
                f'<div class="snipe-card-image" style="flex-shrink:0;width:84px;height:84px;'
                f'border-radius:10px;overflow:hidden;background:#0a0a0a;'
                f'border:1px solid rgba(148,163,184,0.12);">'
                f'<img src="{img_url}" alt="" '
                f'style="width:100%;height:100%;object-fit:cover;display:block;" '
                f'loading="lazy" />'
                f'</div>'
            )
        else:
            image_html = (
                f'<div class="snipe-card-image" style="flex-shrink:0;width:84px;height:84px;'
                f'border-radius:10px;background:#0a0a0a;'
                f'border:1px solid rgba(148,163,184,0.12);'
                f'display:flex;align-items:center;justify-content:center;'
                f'color:#888888;font-size:24px;">●</div>'
            )
        if ebay_url:
            # RECOMMENDED-OFFER-2026-05-13: OFFER-zone listings get a
            # "Make offer" CTA instead of "Buy on eBay" — the action the
            # user should actually take on a negotiable above-target listing.
            _link_label = "Make offer on eBay →" if sz_label == "OFFER" else "Buy on eBay →"
            link_html = (
                f'<a href="{ebay_url}" target="_blank" '
                f'style="display:inline-flex;align-items:center;gap:4px;'
                f'padding:8px 14px;background:rgba(59,130,246,0.12);'
                f'border:1px solid rgba(59,130,246,0.3);border-radius:8px;'
                f'font-size:12px;font-weight:600;color:#4ade80;'
                f'text-decoration:none;">{_link_label}</a>'
            )
        else:
            link_html = '<span></span>'

        _row_label_css = (
            'font-size:10px;color:#b0b0b0;letter-spacing:0.1em;'
            'text-transform:uppercase;margin-bottom:2px;'
        )
        _pending_css = (
            'font-size:14px;font-weight:500;color:#888888;'
            'font-style:italic;padding-top:4px;'
        )
        bin_block = (
            f'<div style="{_row_label_css}">BIN price</div>'
            f'<div style="font-size:20px;font-weight:700;color:#fafafa;">'
            f'{_format_money(bin_price)}</div>'
        )
        if mv_value is not None and mv_value > 0:
            # CARD-COMP-2026-05-12: surface the primary comp directly on the
            # card so users see "based on $X comp · short title" without
            # opening the View comps expander. Falls back to "N comps · range"
            # when no individual comp snapshot is available.
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
                f'<div style="{_row_label_css}">Market value</div>'
                f'<div style="font-size:20px;font-weight:700;color:#fafafa;">'
                f'${mv_value:,.0f}</div>'
                f'{_basis_html}'
            )
        else:
            mv_block = (
                f'<div style="{_row_label_css}">Market value</div>'
                f'<div style="{_pending_css}">computing…</div>'
            )
        if target_value is not None and target_value > 0:
            target_block = (
                f'<div style="{_row_label_css}">Target</div>'
                f'<div style="font-size:20px;font-weight:700;color:#4ade80;">'
                f'${target_value:,.0f}</div>'
            )
        else:
            target_block = (
                f'<div style="{_row_label_css}">Target</div>'
                f'<div style="{_pending_css}">coming soon</div>'
            )

        # Build single-line card HTML
        # MOBILE-CSS-2026-05-17: classes (snipe-card / snipe-card-title /
        # snipe-card-footer / snipe-card-link) let the @media style block
        # collapse the footer into a 2x2 grid + full-width link on phones.
        card_html = (
            f'<div class="snipe-card" style="margin:10px 0;padding:16px 18px;'
            f'background:linear-gradient(180deg,#161616 0%,#1c1c1c 100%);'
            f'border-radius:14px;font-family:-apple-system,\'SF Pro Display\',Inter,sans-serif;'
            f'color:#fafafa;box-shadow:0 2px 12px rgba(0,0,0,0.2);'
            f'border:1px solid rgba(148,163,184,0.08);'
            f'display:flex;gap:16px;">'
            f'{image_html}'
            f'<div style="flex:1;min-width:0;display:flex;flex-direction:column;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
            f'<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">'
            f'{sz_html}'
            f'<span style="font-size:11px;color:#888888;">Listed {listed_str}</span>'
            f'{discount_html}'
            f'{recommend_offer_html}'
            f'</div>'
            f'</div>'
            f'<div class="snipe-card-title" style="font-size:15px;font-weight:600;color:#fafafa;line-height:1.35;margin-bottom:12px;">{title}</div>'
            f'<div class="snipe-card-footer" style="display:flex;align-items:flex-end;gap:18px;padding-top:12px;border-top:1px solid rgba(148,163,184,0.08);margin-top:auto;">'
            f'<div style="flex:1;">{bin_block}</div>'
            f'<div style="flex:1;">{mv_block}</div>'
            f'<div style="flex:1;">{target_block}</div>'
            f'<div class="snipe-card-link" style="flex-shrink:0;">{link_html}</div>'
            f'</div>'
            f'</div>'
            f'</div>'
        )
        item_id = str(
            row.get("item_id")
            or row.get("itemId")
            or row.get("source_item_id")
            or ""
        )
        with st.container():
            st.markdown(card_html, unsafe_allow_html=True)
            _render_card_actions(st, row, item_id)

    if len(actionable) > len(filtered):
        st.caption(
            f"Showing top {len(filtered)} of {len(actionable)}. "
            f"Loosen the filter to see more."
        )
