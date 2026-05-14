"""
Purchased Tab — Streamlit UI

Shows every card the user has logged as Won (from the My Snipes tab),
sorted newest first, with all-time ROI stats.

AUTO-BUYER-PURGE-2026-05-14: the old copy referenced an "auto-buyer"
and a "session spending summary" — both belonged to an automated-bidding
feature that was removed (eBay ToS prohibits unattended auto-bidding).
The Purchased tab is now purely a record of user-confirmed wins.

Called from streamlit_app.py:
    import tab_purchased
    tab_purchased.render_purchased_tab()
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
_SESSION_LOGS_DIR = os.path.join(_HERE, "session_logs")
_SNIPE_LOG_PATH   = os.path.join(_HERE, "snipe_log.csv")
_AUTO_LOG_PATH    = os.path.join(_SESSION_LOGS_DIR, "auto_buyer_log.csv")


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return default


def _load_snipe_log() -> pd.DataFrame:
    """Load snipe_log.csv — manual snipes from Ending Soon tab."""
    if not os.path.isfile(_SNIPE_LOG_PATH):
        return pd.DataFrame()
    try:
        df = pd.read_csv(_SNIPE_LOG_PATH, dtype=str).fillna("")
        # Only successful snipes
        df = df[df["result"].str.strip().str.lower() == "success"].copy()
        if df.empty:
            return pd.DataFrame()
        df["_source"] = "Auction Snipe"
        df["_player"] = df.get("player", df.get("player", ""))
        df["_title"] = df.get("title", df.get("card_description", ""))
        df["_amount_paid"] = df.get("snipe_bid", "0").apply(_safe_float)
        df["_market_value"] = df.get("market_value", "0").apply(_safe_float)
        df["_listing_id"] = df.get("listing_id", "").astype(str).str.strip()
        df["_timestamp"] = pd.to_datetime(df.get("timestamp", ""), errors="coerce")
        return df[["_timestamp", "_player", "_title", "_amount_paid", "_market_value",
                   "_listing_id", "_source"]].copy()
    except Exception:
        return pd.DataFrame()


def _load_auto_log() -> pd.DataFrame:
    """Load auto_buyer_log.csv — auto-buyer snipes and BIN purchases."""
    if not os.path.isfile(_AUTO_LOG_PATH):
        return pd.DataFrame()
    try:
        df = pd.read_csv(_AUTO_LOG_PATH, dtype=str).fillna("")
        # Only won snipes and bin purchases
        won_mask = (
            df["action_type"].str.strip().str.lower().isin(["snipe_won", "bin_bought"])
        ) | (
            (df["action_type"].str.strip().str.lower() == "snipe_placed") &
            (df["result"].str.strip().str.lower() == "won")
        )
        df = df[won_mask].copy()
        if df.empty:
            return pd.DataFrame()
        df["_source"] = df["action_type"].apply(
            lambda x: "BIN Purchase" if "bin" in str(x).lower() else "Auto-Buyer Snipe"
        )
        df["_player"] = df.get("player", "")
        df["_title"] = df.get("card_description", "")
        df["_amount_paid"] = df.get("snipe_bid", "0").apply(_safe_float)
        df["_market_value"] = df.get("market_value", "0").apply(_safe_float)
        df["_listing_id"] = df.get("listing_id", "").astype(str).str.strip()
        df["_timestamp"] = pd.to_datetime(df.get("timestamp", ""), errors="coerce")
        return df[["_timestamp", "_player", "_title", "_amount_paid", "_market_value",
                   "_listing_id", "_source"]].copy()
    except Exception:
        return pd.DataFrame()


def _load_all_purchases() -> pd.DataFrame:
    """Merge snipe log and auto-buyer log into a single sorted DataFrame."""
    snipe = _load_snipe_log()
    auto  = _load_auto_log()
    frames = [f for f in [snipe, auto] if not f.empty]
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df = df.sort_values("_timestamp", ascending=False).reset_index(drop=True)
    return df


def _fmt_money(v: float) -> str:
    return f"${v:,.2f}"


def _ebay_url(listing_id: str) -> str:
    lid = str(listing_id).strip()
    if not lid or lid == "nan":
        return ""
    return f"https://www.ebay.com/itm/{lid}"


# ---------------------------------------------------------------------------
# Session spending helper
# ---------------------------------------------------------------------------

def _get_session_snapshot() -> Dict[str, Any]:
    try:
        import auto_buyer_engine as _eng
        return _eng.get_session_snapshot()
    except Exception:
        return {}


def _load_won_snipes(email: Any) -> pd.DataFrame:
    """PURCHASED-REBUILD-2026-05-14: the Purchased tab now reads from the
    per-user snipes_store — the SAME place My Snipes' "Mark Won" button
    writes to.

    The bug this fixes: the tab used to read legacy snipe_log.csv /
    auto_buyer_log.csv, which the mark-Won flow never touched. So a user
    could mark 20 cards Won and the Purchased tab would still show
    "No wins logged yet" forever — total disconnect between the action
    and the display.

    Returns a DataFrame (newest-first) of this user's status=="won"
    snipes, in the column shape the render code below expects.
    """
    try:
        import snipes_store
    except Exception:
        return pd.DataFrame()

    won = [
        s for s in (snipes_store.list_snipes(email) or [])
        if str(s.get("status") or "").lower() == "won"
    ]
    if not won:
        return pd.DataFrame()

    rows = []
    for s in won:
        paid     = _safe_float(s.get("final_price"))
        mv       = _safe_float(s.get("market_value"))
        resolved = s.get("resolved_at") or s.get("added_at")
        rows.append({
            "_timestamp":    pd.to_datetime(resolved, unit="s", errors="coerce"),
            "_player":       "",  # snipes_store doesn't carry a player field
            "_title":        str(s.get("title") or "—"),
            "_amount_paid":  paid,
            "_market_value": mv,
            "_listing_id":   str(s.get("item_id") or ""),
            "_ebay_url":     str(s.get("ebay_url") or ""),
            "_source":       "Won",
        })
    df = pd.DataFrame(rows)
    df = df.sort_values("_timestamp", ascending=False).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def render_purchased_tab() -> None:
    st.markdown(
        """
<div class="fs-page-hero">
  <p class="fs-ph-title">PURCHASED · ALL-TIME</p>
  <div class="fs-ph-sub">Every win you've logged from My Snipes, sorted newest first.</div>
</div>
""",
        unsafe_allow_html=True,
    )

    # PURCHASED-REBUILD-2026-05-14: read from the per-user snipes_store
    # (where My Snipes' "Mark Won" actually writes) instead of the legacy
    # CSV logs that the mark-Won flow never touched.
    _user_email = st.session_state.get("sw_trial_user_email")
    df = _load_won_snipes(_user_email)

    # ── Section 1: Cards Purchased ────────────────────────────────────────
    st.markdown(
        '<div style="font-size:10px;font-weight:700;letter-spacing:0.15em;color:#374151;'
        'text-transform:uppercase;font-family:Inter,sans-serif;margin:20px 0 12px 0;">'
        'CARDS PURCHASED</div>',
        unsafe_allow_html=True,
    )

    if df.empty:
        # EMPTY-STATE-2026-05-13: match the visual treatment from
        # pool_view / bin_view / snipes_view empty states for visual
        # consistency across all tabs. Auto-Buyer reference removed —
        # it's hidden from the user UI per the May 6 cleanup. Users
        # mark wins manually from the My Snipes tab.
        st.markdown(
            """
<div style="margin:18px 0 24px 0;padding:36px 28px;
     background:linear-gradient(135deg,#141414 0%,#0a0a0a 100%);
     border:1px solid rgba(148,163,184,0.10);border-radius:16px;
     font-family:-apple-system,'SF Pro Display',Inter,sans-serif;
     color:#fafafa;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,0.25);">
  <div style="font-size:11px;font-weight:700;letter-spacing:0.18em;
              color:#4ade80;text-transform:uppercase;margin-bottom:14px;">
    <span style="display:inline-block;width:7px;height:7px;border-radius:50%;
                 background:#4ade80;margin-right:8px;vertical-align:middle;"></span>
    Purchased
  </div>
  <div style="font-size:20px;font-weight:700;color:#fafafa;margin-bottom:8px;
              letter-spacing:-0.01em;">
    No wins logged yet
  </div>
  <div style="font-size:14px;color:#b0b0b0;line-height:1.55;max-width:460px;
              margin:0 auto;">
    When you win an eBay auction or buy a Steal, head to <strong style="color:#fafafa;">My Snipes</strong>,
    click the card, and mark it Won. Your ROI history and best deals
    will populate here automatically.
  </div>
</div>
""",
            unsafe_allow_html=True,
        )
    else:
        # PURCHASED-REBUILD-2026-05-14: enriched stat panel. "More than
        # eBay's purchase view" = cards, total spent, avg cost/card,
        # collection value, total saved vs market, and the best single
        # deal. All computed from the user's own mark-Won data — no eBay
        # integration needed.
        total_cards   = len(df)
        total_spent   = float(df["_amount_paid"].sum())
        avg_per_card  = (total_spent / total_cards) if total_cards else 0.0
        # Collection value: sum of market values for cards that have one.
        collection_mv = float(df[df["_market_value"] > 0]["_market_value"].sum())
        # Total saved: only count cards that actually have an MV to compare.
        _priced       = df[df["_market_value"] > 0].copy()
        total_saved   = float((_priced["_market_value"] - _priced["_amount_paid"]).sum())
        df["_edge"]   = df["_market_value"] - df["_amount_paid"]
        best_row      = df.loc[df["_edge"].idxmax()] if not df.empty else None
        best_name     = str(best_row["_title"])[:38] if best_row is not None else "—"
        best_edge     = float(best_row["_edge"]) if best_row is not None else 0.0
        saved_color   = "#00ff88" if total_saved >= 0 else "#ef4444"
        saved_str     = f"+{_fmt_money(total_saved)}" if total_saved >= 0 else _fmt_money(total_saved)

        _stat_label = (
            'font-size:9px;font-weight:600;letter-spacing:0.1em;color:#374151;'
            'text-transform:uppercase;margin-bottom:4px;'
        )
        _stat_val = (
            'font-size:22px;font-weight:800;color:#f5f5f5;'
            'font-variant-numeric:tabular-nums;'
        )
        _divider = '<div style="width:1px;height:32px;background:#1a1a1a;flex-shrink:0;"></div>'
        st.markdown(f"""
<div style="background:#0d0d0d;border:1px solid #1a1a1a;border-radius:8px;
     padding:16px 24px;margin:0 0 20px 0;display:flex;align-items:center;
     gap:28px;font-family:Inter,sans-serif;flex-wrap:wrap;">
  <div>
    <div style="{_stat_label}">CARDS</div>
    <div style="{_stat_val}">{total_cards}</div>
  </div>
  {_divider}
  <div>
    <div style="{_stat_label}">TOTAL SPENT</div>
    <div style="{_stat_val}">{_fmt_money(total_spent)}</div>
  </div>
  {_divider}
  <div>
    <div style="{_stat_label}">AVG COST / CARD</div>
    <div style="{_stat_val}">{_fmt_money(avg_per_card)}</div>
  </div>
  {_divider}
  <div>
    <div style="{_stat_label}">COLLECTION VALUE</div>
    <div style="{_stat_val}">{_fmt_money(collection_mv)}</div>
  </div>
  {_divider}
  <div>
    <div style="{_stat_label}">SAVED VS MARKET</div>
    <div style="font-size:22px;font-weight:800;color:{saved_color};
                font-variant-numeric:tabular-nums;">{saved_str}</div>
  </div>
  {_divider}
  <div>
    <div style="{_stat_label}">BEST DEAL</div>
    <div style="font-size:13px;font-weight:700;color:#00ff88;">{best_name}</div>
    <div style="font-size:11px;color:#6b7280;font-variant-numeric:tabular-nums;">
      +{_fmt_money(best_edge)} under market</div>
  </div>
</div>
""", unsafe_allow_html=True)

        # Table rows. PURCHASED-REBUILD-2026-05-14: dropped the source
        # badge (every row is a user-confirmed Won now — no auto-buyer/
        # sniper distinction) and the player label (snipes_store doesn't
        # carry one). eBay link comes from the stored ebay_url, not a
        # reconstructed listing id.
        for _, row in df.iterrows():
            ts      = row["_timestamp"]
            ts_str  = ts.strftime("%b %d %Y") if pd.notnull(ts) else "—"
            title   = str(row["_title"] or "—")
            paid    = float(row["_amount_paid"])
            mv      = float(row["_market_value"])
            edge    = float(row["_edge"])
            url     = str(row.get("_ebay_url") or "")

            edge_color = "#00ff88" if edge > 0 else "#ef4444" if edge < 0 else "#6b7280"
            edge_str   = f"+{_fmt_money(edge)}" if edge >= 0 else _fmt_money(edge)
            mv_str     = _fmt_money(mv) if mv > 0 else "—"
            link_html  = (
                f'<a href="{url}" target="_blank" rel="noopener noreferrer" '
                f'style="color:#3b82f6;font-size:10px;text-decoration:none;">'
                f'View on eBay →</a>' if url else ''
            )

            st.markdown(f"""
<div style="background:#111111;border:1px solid #1a1a1a;border-radius:8px;
     padding:14px 18px;margin-bottom:8px;font-family:Inter,sans-serif;
     display:flex;gap:20px;align-items:center;flex-wrap:wrap;">
  <div style="flex:1;min-width:200px;">
    <div style="font-size:13px;font-weight:600;color:#e5e7eb;line-height:1.35;
                margin-bottom:6px;">{title[:90]}</div>
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
      <span style="background:rgba(0,255,136,0.1);color:#00ff88;font-size:9px;
               font-weight:700;letter-spacing:0.08em;padding:2px 7px;
               border-radius:4px;text-transform:uppercase;">Won</span>
      <span style="color:#374151;font-size:10px;">{ts_str}</span>
      {link_html}
    </div>
  </div>
  <div style="display:flex;gap:24px;align-items:center;flex-wrap:wrap;">
    <div style="text-align:right;">
      <div style="font-size:9px;font-weight:600;letter-spacing:0.1em;color:#374151;
                  text-transform:uppercase;margin-bottom:2px;">PAID</div>
      <div style="font-size:16px;font-weight:800;color:#f5f5f5;
                  font-variant-numeric:tabular-nums;">{_fmt_money(paid)}</div>
    </div>
    <div style="text-align:right;">
      <div style="font-size:9px;font-weight:600;letter-spacing:0.1em;color:#374151;
                  text-transform:uppercase;margin-bottom:2px;">MARKET VALUE</div>
      <div style="font-size:16px;font-weight:800;color:#9ca3af;
                  font-variant-numeric:tabular-nums;">{mv_str}</div>
    </div>
    <div style="text-align:right;">
      <div style="font-size:9px;font-weight:600;letter-spacing:0.1em;color:#374151;
                  text-transform:uppercase;margin-bottom:2px;">SAVED</div>
      <div style="font-size:16px;font-weight:800;color:{edge_color};
                  font-variant-numeric:tabular-nums;">{edge_str}</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

    # AUTO-BUYER-PURGE-2026-05-14: the "Session Spending Summary" section
    # that used to render here was tied to the removed auto-buyer feature.
    # With no auto-buyer there's no "session" — the block always rendered
    # the confusing "Start the Auto-Buyer to track session spending"
    # empty state. Removed entirely. The all-time ROI stats above + the
    # per-card list below are the whole Purchased tab now.
