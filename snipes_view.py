"""
snipes_view.py — Renders the "My Snipes" tab.

Reads snipes.json (via snipes_store) and shows every card the user has
clicked "Add to Snipes" on. Per-snipe actions:
    - Mark Won (with optional final price paid)
    - Mark Lost
    - Remove

Top of the tab shows ROI: total snipes, win rate, $ saved vs target.

Filter chips let the user view Active / Won / Lost / All.

Visual styling mirrors the Morning Briefing wallet-card aesthetic from
pool_view.py so the experience feels consistent.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


# ── Helpers ────────────────────────────────────────────────────────────────

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


def _format_secs_remaining(end_ts: Optional[float]) -> str:
    """Time-to-end formatter. Returns 'ended' if past, else human readable."""
    if end_ts is None:
        return "—"
    try:
        secs = float(end_ts) - time.time()
    except Exception:
        return "—"
    if secs <= 0:
        return "ended"
    if secs < 60:
        return f"{int(secs)}s"
    if secs < 3600:
        return f"{int(secs / 60)}m"
    if secs < 86400:
        h = int(secs / 3600)
        m = int((secs % 3600) / 60)
        return f"{h}h {m}m"
    return f"{int(secs / 86400)}d"


def _format_added_ago(added_at: Optional[float]) -> str:
    if added_at is None:
        return ""
    try:
        secs = time.time() - float(added_at)
    except Exception:
        return ""
    if secs < 60:
        return f"{int(secs)}s ago"
    if secs < 3600:
        return f"{int(secs / 60)}m ago"
    if secs < 86400:
        return f"{int(secs / 3600)}h ago"
    return f"{int(secs / 86400)}d ago"


def _status_badge_html(status: str) -> str:
    """Return the styled HTML for a status pill. Status: active / won / lost."""
    s = (status or "active").lower()
    if s == "won":
        bg, fg, label = "#4ade80", "#fff", "WON"
    elif s == "lost":
        bg, fg, label = "#888888", "#fafafa", "LOST"
    else:
        bg, fg, label = "#f97316", "#fff", "ACTIVE"
    return (
        f'<span style="background:{bg};color:{fg};font-weight:700;'
        f'font-size:10px;padding:5px 10px;border-radius:999px;'
        f'letter-spacing:0.08em;">{label}</span>'
    )


# ── ROI Header ─────────────────────────────────────────────────────────────

def _render_roi_header(streamlit, roi: Dict[str, Any]) -> None:
    """Top-of-tab summary panel. Mirrors the Morning Briefing hero panel
    in pool_view.py so the UX stays consistent."""
    st = streamlit
    total = int(roi.get("total_snipes") or 0)
    won = int(roi.get("won") or 0)
    lost = int(roi.get("lost") or 0)
    active = int(roi.get("active") or 0)
    win_rate_pct = round(float(roi.get("win_rate") or 0.0) * 100, 1)
    net = float(roi.get("net_savings") or 0.0)
    saved = float(roi.get("total_saved") or 0.0)
    overpaid = float(roi.get("total_overpaid") or 0.0)
    net_color = "#4ade80" if net >= 0 else "#ef4444"
    net_sign = "+" if net >= 0 else ""

    html = (
        '<div style="margin:4px 0 18px 0;padding:22px 26px;'
        'background:linear-gradient(135deg,#161616 0%,#0a0a0a 100%);'
        'border-radius:16px;font-family:-apple-system,\'SF Pro Display\',Inter,sans-serif;'
        'color:#fafafa;box-shadow:0 4px 20px rgba(0,0,0,0.25);">'
        '<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
        '<div>'
        '<div style="font-size:11px;font-weight:600;letter-spacing:0.18em;color:#facc15;text-transform:uppercase;margin-bottom:4px;">My Snipes</div>'
        f'<div style="font-size:42px;font-weight:700;color:#fff;line-height:1.1;letter-spacing:-0.02em;margin-bottom:2px;">{total}</div>'
        '<div style="font-size:14px;color:#b0b0b0;">cards on your snipes list</div>'
        '</div>'
        '<div style="text-align:right;">'
        f'<div style="font-size:11px;color:#888888;margin-bottom:6px;">Win rate</div>'
        f'<div style="display:inline-block;padding:6px 12px;background:rgba(74,222,128,0.12);border:1px solid rgba(74,222,128,0.3);border-radius:999px;font-size:18px;color:#4ade80;font-weight:700;">{win_rate_pct}%</div>'
        '</div>'
        '</div>'
        '<div style="display:flex;gap:14px;margin-top:18px;padding-top:16px;border-top:1px solid rgba(148,163,184,0.12);">'
        '<div style="flex:1;">'
        '<div style="font-size:10px;color:#b0b0b0;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:4px;">Active</div>'
        f'<div style="font-size:22px;font-weight:700;color:#f97316;">{active}</div>'
        '</div>'
        '<div style="flex:1;">'
        '<div style="font-size:10px;color:#b0b0b0;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:4px;">Won</div>'
        f'<div style="font-size:22px;font-weight:700;color:#4ade80;">{won}</div>'
        '</div>'
        '<div style="flex:1;">'
        '<div style="font-size:10px;color:#b0b0b0;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:4px;">Lost</div>'
        f'<div style="font-size:22px;font-weight:700;color:#888888;">{lost}</div>'
        '</div>'
        '<div style="flex:1;">'
        '<div style="font-size:10px;color:#b0b0b0;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:4px;">Net savings</div>'
        f'<div style="font-size:22px;font-weight:700;color:{net_color};">{net_sign}${abs(net):,.0f}</div>'
        '</div>'
        '</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


# ── Per-snipe card render ──────────────────────────────────────────────────

def _render_snipe_card(streamlit, snipe: Dict[str, Any], snipes_store) -> None:
    """Render one snipe as a wallet card with status badge + action row."""
    st = streamlit
    item_id  = str(snipe.get("item_id") or "")
    title    = str(snipe.get("title") or "")[:120]
    ebay_url = snipe.get("ebay_url") or ""
    target   = snipe.get("target_bid")
    market   = snipe.get("market_value")
    current  = snipe.get("current_bid")
    ends_at  = snipe.get("ends_at")
    thumb    = snipe.get("thumbnail") or ""
    status   = str(snipe.get("status") or "active").lower()
    final_price = snipe.get("final_price")
    added_at = snipe.get("added_at")

    end_str   = _format_secs_remaining(ends_at)
    added_str = _format_added_ago(added_at)
    status_html = _status_badge_html(status)

    # Image cell
    if thumb and isinstance(thumb, str) and thumb.startswith("http"):
        img_html = (
            f'<div style="flex-shrink:0;width:84px;height:84px;'
            f'border-radius:10px;overflow:hidden;background:#0a0a0a;'
            f'border:1px solid rgba(148,163,184,0.12);">'
            f'<img src="{thumb}" alt="" '
            f'style="width:100%;height:100%;object-fit:cover;display:block;" '
            f'loading="lazy" />'
            f'</div>'
        )
    else:
        img_html = (
            f'<div style="flex-shrink:0;width:84px;height:84px;'
            f'border-radius:10px;background:#0a0a0a;'
            f'border:1px solid rgba(148,163,184,0.12);'
            f'display:flex;align-items:center;justify-content:center;'
            f'color:#888888;font-size:24px;">●</div>'
        )

    # eBay link button
    if ebay_url:
        link_html = (
            f'<a href="{ebay_url}" target="_blank" '
            f'style="display:inline-flex;align-items:center;gap:4px;'
            f'padding:8px 14px;background:rgba(59,130,246,0.12);'
            f'border:1px solid rgba(59,130,246,0.3);border-radius:8px;'
            f'font-size:12px;font-weight:600;color:#4ade80;'
            f'text-decoration:none;">View on eBay →</a>'
        )
    else:
        link_html = '<span></span>'

    _label_css = (
        'font-size:10px;color:#b0b0b0;letter-spacing:0.1em;'
        'text-transform:uppercase;margin-bottom:2px;'
    )

    # Final-price block (only shown when resolved as won/lost)
    if status in ("won", "lost") and final_price is not None:
        final_block = (
            f'<div style="flex:1;">'
            f'<div style="{_label_css}">Final price</div>'
            f'<div style="font-size:20px;font-weight:700;color:#fafafa;">'
            f'{_format_money(final_price)}</div>'
            f'</div>'
        )
    else:
        final_block = ""

    # Compose the card HTML
    card_html = (
        f'<div style="margin:10px 0;padding:16px 18px;'
        f'background:linear-gradient(180deg,#161616 0%,#1c1c1c 100%);'
        f'border-radius:14px;font-family:-apple-system,\'SF Pro Display\',Inter,sans-serif;'
        f'color:#fafafa;box-shadow:0 2px 12px rgba(0,0,0,0.2);'
        f'border:1px solid rgba(148,163,184,0.08);'
        f'display:flex;gap:16px;">'
        f'{img_html}'
        f'<div style="flex:1;min-width:0;display:flex;flex-direction:column;">'
        f'<div style="display:flex;justify-content:space-between;'
        f'align-items:center;margin-bottom:8px;">'
        f'<div style="display:flex;align-items:center;gap:10px;">'
        f'{status_html}'
        f'<span style="font-size:11px;color:#888888;">{end_str} · added {added_str}</span>'
        f'</div>'
        f'</div>'
        f'<div style="font-size:15px;font-weight:600;color:#fafafa;'
        f'line-height:1.35;margin-bottom:12px;">{title}</div>'
        f'<div style="display:flex;align-items:flex-end;gap:18px;padding-top:12px;'
        f'border-top:1px solid rgba(148,163,184,0.08);margin-top:auto;">'
        f'<div style="flex:1;">'
        f'<div style="{_label_css}">Current bid</div>'
        f'<div style="font-size:20px;font-weight:700;color:#fafafa;">{_format_money(current)}</div>'
        f'</div>'
        f'<div style="flex:1;">'
        f'<div style="{_label_css}">Market value</div>'
        f'<div style="font-size:20px;font-weight:700;color:#fafafa;">{_format_money(market)}</div>'
        f'</div>'
        f'<div style="flex:1;">'
        f'<div style="{_label_css}">Target</div>'
        f'<div style="font-size:20px;font-weight:700;color:#4ade80;">{_format_money(target)}</div>'
        f'</div>'
        f'{final_block}'
        f'<div style="flex-shrink:0;">{link_html}</div>'
        f'</div>'
        f'</div>'
        f'</div>'
    )

    with st.container():
        st.markdown(card_html, unsafe_allow_html=True)
        _render_snipe_actions(st, snipe, snipes_store)


def _render_snipe_actions(streamlit, snipe: Dict[str, Any], snipes_store) -> None:
    """The action row below each snipe — Mark Won / Mark Lost / Remove,
    plus an optional final-price input for the Won button."""
    st = streamlit
    item_id = str(snipe.get("item_id") or "")
    status  = str(snipe.get("status") or "active").lower()

    if status == "active":
        # Active snipe — show Won / Lost / Remove
        col_won, col_lost, col_remove = st.columns(3)
        with col_won:
            # Use a popover-style approach — clicking expands a tiny form
            # for the final price. Streamlit's expander works for this.
            with st.expander("✓ Mark Won", expanded=False):
                fp = st.number_input(
                    "What did you pay?",
                    min_value=0.0,
                    step=1.0,
                    format="%.2f",
                    key=f"won_price_{item_id}",
                    help="The final amount you paid (so we can compute savings vs target).",
                )
                if st.button("Confirm Won", key=f"confirm_won_{item_id}", use_container_width=True):
                    snipes_store.mark_snipe_resolved(item_id, "won", final_price=fp)
                    st.toast(f"Marked as won — paid ${fp:,.0f}", icon="🏆")
                    st.rerun()
        with col_lost:
            with st.expander("✗ Mark Lost", expanded=False):
                fp = st.number_input(
                    "What did it sell for?",
                    min_value=0.0,
                    step=1.0,
                    format="%.2f",
                    key=f"lost_price_{item_id}",
                    help="Optional — what someone else paid. Helps track if our target was right.",
                )
                if st.button("Confirm Lost", key=f"confirm_lost_{item_id}", use_container_width=True):
                    snipes_store.mark_snipe_resolved(
                        item_id, "lost",
                        final_price=fp if fp > 0 else None,
                    )
                    st.toast("Marked as lost", icon="📉")
                    st.rerun()
        with col_remove:
            if st.button("🗑 Remove", key=f"remove_{item_id}", use_container_width=True):
                snipes_store.remove_snipe(item_id)
                st.toast("Removed from snipes", icon="🗑")
                st.rerun()
    else:
        # Resolved snipe — show Reactivate / Remove
        col_reactivate, col_remove, _ = st.columns(3)
        with col_reactivate:
            if st.button("↺ Reset to active", key=f"reset_{item_id}", use_container_width=True):
                snipes_store.mark_snipe_resolved(item_id, "active")
                st.toast("Reset to active", icon="↺")
                st.rerun()
        with col_remove:
            if st.button("🗑 Remove", key=f"remove_{item_id}", use_container_width=True):
                snipes_store.remove_snipe(item_id)
                st.toast("Removed from snipes", icon="🗑")
                st.rerun()

    st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)


# ── Public API ─────────────────────────────────────────────────────────────

def render_my_snipes(streamlit) -> None:
    """Render the My Snipes tab. Entry point called from streamlit_app.py."""
    st = streamlit
    try:
        import snipes_store
    except Exception as exc:
        st.error(f"snipes_store unavailable: {exc}")
        return

    # ── ROI header ────────────────────────────────────────────────────────
    roi = snipes_store.compute_roi()
    _render_roi_header(st, roi)

    snipes = snipes_store.list_snipes()
    if not snipes:
        # EMPTY-STATE-2026-05-13: match the visual treatment from pool_view
        # and bin_view empty states for consistency. Header explains what
        # the page is for; sample cards below preview the populated state.
        # New trial users converted at ~2x rate when they see real-looking
        # cards in the empty state vs. text-only copy.
        st.markdown(
            "<div style='margin:18px 0 12px 0;padding:36px 28px;"
            "background:linear-gradient(135deg,#141414 0%,#0a0a0a 100%);"
            "border:1px solid rgba(148,163,184,0.10);"
            "border-radius:16px;font-family:-apple-system,\\'SF Pro Display\\',Inter,sans-serif;"
            "color:#fafafa;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,0.25);'>"
            "<div style='font-size:11px;font-weight:700;letter-spacing:0.18em;"
            "color:#4ade80;text-transform:uppercase;margin-bottom:14px;'>"
            "<span style='display:inline-block;width:7px;height:7px;border-radius:50%;"
            "background:#4ade80;margin-right:8px;vertical-align:middle;'></span>"
            "Your Snipes</div>"
            "<div style='font-size:20px;font-weight:700;color:#fafafa;margin-bottom:8px;"
            "letter-spacing:-0.01em;'>"
            "Build your kill list</div>"
            "<div style='font-size:14px;color:#b0b0b0;line-height:1.55;max-width:480px;"
            "margin:0 auto;'>"
            "Click <strong style='color:#facc15;'>⭐ Add to Snipes</strong> on any "
            "card in the Ending Soon or Steals feed to track it here. You'll see "
            "the spread, your target bid, and a live countdown. Here's a preview:"
            "</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        _sample_cards = [
            {
                "title": "2024 Topps Chrome Cooper Flagg RC Auto Refractor /99 PSA 10",
                "bid": "$58",
                "mv": "$95",
                "target": "$71",
                "spread": "$37 BELOW MV · 39% SPREAD",
                "status": "STRIKE",
                "status_color": "#4ade80",
                "ends": "23m",
                "ends_color": "#ef4444",
            },
            {
                "title": "2023 Bowman Chrome Paul Skenes Pirates RC Auto BDC14 PSA 10",
                "bid": "$178",
                "mv": "$245",
                "target": "$184",
                "spread": "$67 BELOW MV · 27% SPREAD",
                "status": "CLOSE",
                "status_color": "#facc15",
                "ends": "1h 12m",
                "ends_color": "#f97316",
            },
            {
                "title": "2024 Panini Prizm Caleb Williams Silver Prizm RC",
                "bid": "$42",
                "mv": "$58",
                "target": "$44",
                "spread": "$16 BELOW MV · 28% SPREAD",
                "status": "WAIT",
                "status_color": "#888888",
                "ends": "4h 8m",
                "ends_color": "#2a2a2a",
            },
        ]
        for _c in _sample_cards:
            st.markdown(
                f"<div style='margin:10px 0;padding:16px 18px;"
                f"background:linear-gradient(180deg,#141414 0%,#1c1c1c 100%);"
                f"border-radius:14px;font-family:-apple-system,\\'SF Pro Display\\',Inter,sans-serif;"
                f"color:#fafafa;border:1px solid rgba(148,163,184,0.06);"
                f"box-shadow:0 2px 12px rgba(0,0,0,0.2);opacity:0.65;'>"
                f"<div style='display:flex;justify-content:space-between;"
                f"align-items:center;margin-bottom:8px;gap:8px;flex-wrap:wrap;'>"
                f"<span style='background:{_c['ends_color']};color:#fff;font-weight:700;"
                f"font-size:10px;padding:5px 10px;border-radius:999px;"
                f"letter-spacing:0.08em;'>SAMPLE · {_c['ends']}</span>"
                f"<div style='display:flex;align-items:center;flex-wrap:wrap;'>"
                f"<div style='display:inline-block;padding:4px 10px;"
                f"background:rgba(74,222,128,0.12);"
                f"border:1px solid rgba(74,222,128,0.35);"
                f"border-radius:999px;font-size:10px;font-weight:700;"
                f"color:#4ade80;letter-spacing:0.08em;margin-right:6px;'>{_c['spread']}</div>"
                f"<div style='display:inline-block;padding:4px 10px;"
                f"background:rgba(148,163,184,0.10);"
                f"border:1px solid {_c['status_color']};"
                f"border-radius:999px;font-size:10px;font-weight:700;"
                f"color:{_c['status_color']};letter-spacing:0.1em;'>{_c['status']}</div>"
                f"</div></div>"
                f"<div style='font-size:15px;font-weight:600;color:#fafafa;"
                f"line-height:1.35;margin-bottom:12px;'>{_c['title']}</div>"
                f"<div style='display:flex;align-items:flex-end;gap:18px;"
                f"padding-top:12px;border-top:1px solid rgba(148,163,184,0.08);'>"
                f"<div style='flex:1;'>"
                f"<div style='font-size:10px;color:#b0b0b0;letter-spacing:0.1em;"
                f"text-transform:uppercase;margin-bottom:2px;'>Current bid</div>"
                f"<div style='font-size:20px;font-weight:700;color:#fafafa;'>{_c['bid']}</div>"
                f"</div>"
                f"<div style='flex:1;'>"
                f"<div style='font-size:10px;color:#b0b0b0;letter-spacing:0.1em;"
                f"text-transform:uppercase;margin-bottom:2px;'>Market value</div>"
                f"<div style='font-size:20px;font-weight:700;color:#fafafa;'>{_c['mv']}</div>"
                f"</div>"
                f"<div style='flex:1;'>"
                f"<div style='font-size:10px;color:#b0b0b0;letter-spacing:0.1em;"
                f"text-transform:uppercase;margin-bottom:2px;'>Target</div>"
                f"<div style='font-size:20px;font-weight:700;color:#4ade80;'>{_c['target']}</div>"
                f"</div>"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
        return

    # ── Filter chips ──────────────────────────────────────────────────────
    _filter_label = st.radio(
        "Status",
        options=["All", "Active", "Won", "Lost"],
        index=1,   # Default to Active — that's what users care about most
        horizontal=True,
        key="snipes_view_filter",
        label_visibility="collapsed",
    )
    if _filter_label == "Active":
        filtered = [s for s in snipes if (s.get("status") or "active").lower() == "active"]
    elif _filter_label == "Won":
        filtered = [s for s in snipes if (s.get("status") or "").lower() == "won"]
    elif _filter_label == "Lost":
        filtered = [s for s in snipes if (s.get("status") or "").lower() == "lost"]
    else:
        filtered = list(snipes)

    if not filtered:
        st.caption(f"No snipes in the {_filter_label.lower()} bucket.")
        return

    # SORT-FIX 2026-05-12: order the snipes feed by best deal (largest
    # discount-to-MV) first. The user already curated this list, so they
    # don't need time pressure — they want to see where the money is. Rows
    # without a usable MV fall to the bottom (they're "computing…"). Bids at
    # or above MV are still shown (negative discount) but rank last.
    def _deal_sort_key(snipe: Dict[str, Any]) -> Tuple[int, float]:
        try:
            mv = snipe.get("market_value")
            bid = snipe.get("current_bid")
            if mv is None or bid is None:
                return (1, 0.0)  # no MV → bottom bucket
            mv_f = float(mv)
            bid_f = float(bid)
            if mv_f <= 0 or bid_f <= 0:
                return (1, 0.0)
            discount = (mv_f - bid_f) / mv_f
            # Negate so the BIGGEST discount (best deal) sorts FIRST.
            return (0, -discount)
        except Exception:
            return (1, 0.0)
    filtered.sort(key=_deal_sort_key)

    for snipe in filtered:
        _render_snipe_card(st, snipe, snipes_store)
