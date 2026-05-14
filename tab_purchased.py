"""
Purchased Tab — Streamlit UI

Shows all cards purchased via sniper or auto-buyer, plus session spending summary.

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


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def render_purchased_tab() -> None:
    st.markdown(
        """
<div class="fs-page-hero">
  <p class="fs-ph-title">PURCHASED · ALL-TIME &amp; SESSION</p>
  <div class="fs-ph-sub">Every card bought via sniper or auto-buyer — sorted newest first.</div>
</div>
""",
        unsafe_allow_html=True,
    )

    df = _load_all_purchases()

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
        # Summary stats
        total_cards  = len(df)
        total_spent  = df["_amount_paid"].sum()
        mv_vals      = df[df["_market_value"] > 0]
        if not mv_vals.empty:
            avg_disc = ((mv_vals["_market_value"] - mv_vals["_amount_paid"]) / mv_vals["_market_value"] * 100).mean()
        else:
            avg_disc = 0.0
        df["_edge"] = df["_market_value"] - df["_amount_paid"]
        best_row  = df.loc[df["_edge"].idxmax()] if not df.empty else None
        best_name = str(best_row["_title"])[:40] if best_row is not None else "—"
        best_edge = float(best_row["_edge"]) if best_row is not None else 0.0

        st.markdown(f"""
<div style="background:#0d0d0d;border:1px solid #1a1a1a;border-radius:8px;
     padding:16px 24px;margin:0 0 20px 0;display:flex;align-items:center;
     gap:32px;font-family:Inter,sans-serif;flex-wrap:wrap;">
  <div>
    <div style="font-size:9px;font-weight:600;letter-spacing:0.1em;color:#374151;
                text-transform:uppercase;margin-bottom:4px;">TOTAL PURCHASED</div>
    <div style="font-size:22px;font-weight:800;color:#f5f5f5;
                font-variant-numeric:tabular-nums;">{total_cards}</div>
  </div>
  <div style="width:1px;height:32px;background:#1a1a1a;flex-shrink:0;"></div>
  <div>
    <div style="font-size:9px;font-weight:600;letter-spacing:0.1em;color:#374151;
                text-transform:uppercase;margin-bottom:4px;">TOTAL SPENT</div>
    <div style="font-size:22px;font-weight:800;color:#f5f5f5;
                font-variant-numeric:tabular-nums;">{_fmt_money(total_spent)}</div>
  </div>
  <div style="width:1px;height:32px;background:#1a1a1a;flex-shrink:0;"></div>
  <div>
    <div style="font-size:9px;font-weight:600;letter-spacing:0.1em;color:#374151;
                text-transform:uppercase;margin-bottom:4px;">AVG DISCOUNT</div>
    <div style="font-size:22px;font-weight:800;color:#00ff88;
                font-variant-numeric:tabular-nums;">{avg_disc:.1f}%</div>
  </div>
  <div style="width:1px;height:32px;background:#1a1a1a;flex-shrink:0;"></div>
  <div>
    <div style="font-size:9px;font-weight:600;letter-spacing:0.1em;color:#374151;
                text-transform:uppercase;margin-bottom:4px;">BEST DEAL</div>
    <div style="font-size:13px;font-weight:700;color:#00ff88;
                font-variant-numeric:tabular-nums;">{best_name}</div>
    <div style="font-size:11px;color:#6b7280;font-variant-numeric:tabular-nums;">
      +{_fmt_money(best_edge)} edge</div>
  </div>
</div>
""", unsafe_allow_html=True)

        # Table rows
        for _, row in df.iterrows():
            ts     = row["_timestamp"]
            ts_str = ts.strftime("%b %d %Y · %I:%M %p") if pd.notnull(ts) else "—"
            player = str(row["_player"] or "—")
            title  = str(row["_title"] or "—")
            paid   = float(row["_amount_paid"])
            mv     = float(row["_market_value"])
            edge   = float(row["_edge"])
            lid    = str(row["_listing_id"])
            source = str(row["_source"])
            url    = _ebay_url(lid)

            edge_color = "#00ff88" if edge > 0 else "#ef4444" if edge < 0 else "#6b7280"
            edge_str   = f"+{_fmt_money(edge)}" if edge >= 0 else _fmt_money(edge)
            mv_str     = _fmt_money(mv) if mv > 0 else "—"
            lid_html   = (
                f'<a href="{url}" target="_blank" rel="noopener noreferrer" '
                f'style="color:#3b82f6;font-size:10px;text-decoration:none;">'
                f'{lid[:16]}…</a>' if url else
                f'<span style="color:#374151;font-size:10px;">{lid[:20]}</span>'
            )
            source_color = "#00ff88" if "Snipe" in source else "#fbbf24"

            st.markdown(f"""
<div style="background:#111111;border:1px solid #1a1a1a;border-radius:8px;
     padding:14px 18px;margin-bottom:8px;font-family:Inter,sans-serif;
     display:flex;gap:20px;align-items:center;flex-wrap:wrap;">
  <div style="flex:1;min-width:200px;">
    <div style="font-size:10px;font-weight:600;letter-spacing:0.08em;color:#374151;
                text-transform:uppercase;margin-bottom:2px;">{player}</div>
    <div style="font-size:13px;font-weight:600;color:#e5e7eb;line-height:1.35;
                margin-bottom:6px;">{title[:80]}</div>
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
      <span style="background:rgba({
          '0,255,136' if 'Snipe' in source else '251,191,36'
      },0.1);color:{source_color};font-size:9px;font-weight:700;
               letter-spacing:0.08em;padding:2px 7px;border-radius:4px;
               text-transform:uppercase;">{source}</span>
      <span style="color:#374151;font-size:10px;">{ts_str}</span>
      {lid_html}
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
                  text-transform:uppercase;margin-bottom:2px;">EDGE</div>
      <div style="font-size:16px;font-weight:800;color:{edge_color};
                  font-variant-numeric:tabular-nums;">{edge_str}</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

    # ── Section 2: Session Spending Summary ───────────────────────────────
    st.markdown(
        '<div style="font-size:10px;font-weight:700;letter-spacing:0.15em;color:#374151;'
        'text-transform:uppercase;font-family:Inter,sans-serif;margin:28px 0 12px 0;">'
        'SESSION SPENDING SUMMARY</div>',
        unsafe_allow_html=True,
    )

    snap    = _get_session_snapshot()
    status  = snap.get("status", "idle")
    config  = snap.get("config") or {}
    budget  = float(config.get("budget") or 0)
    spent_d = snap.get("spent") or {}
    session_spent    = sum(float(v) for v in spent_d.values())
    session_cards    = len(snap.get("completed") or [])
    budget_remaining = max(0.0, budget - session_spent)
    pct_used         = (session_spent / budget * 100) if budget > 0 else 0.0
    bar_color = "#00ff88" if pct_used < 50 else "#f59e0b" if pct_used < 80 else "#ef4444"

    if status == "idle" and session_cards == 0 and budget == 0:
        st.markdown(
            """
<div style="background:#0d0d0d;border:1px dashed #1a1a1a;border-radius:8px;
     padding:24px;text-align:center;font-family:Inter,sans-serif;">
  <div style="font-size:12px;color:#374151;line-height:1.6;">
    No session active. Start the Auto-Buyer to track session spending.
  </div>
</div>
""",
            unsafe_allow_html=True,
        )
    else:
        pct_display = min(pct_used, 100.0)
        st.markdown(f"""
<div style="background:#0d0d0d;border:1px solid #1a1a1a;border-radius:8px;
     padding:20px 24px;font-family:Inter,sans-serif;margin-bottom:12px;">
  <div style="display:flex;gap:32px;margin-bottom:16px;flex-wrap:wrap;">
    <div>
      <div style="font-size:9px;font-weight:600;letter-spacing:0.1em;color:#374151;
                  text-transform:uppercase;margin-bottom:4px;">SESSION BUDGET</div>
      <div style="font-size:20px;font-weight:800;color:#f5f5f5;
                  font-variant-numeric:tabular-nums;">{_fmt_money(budget)}</div>
    </div>
    <div style="width:1px;height:32px;background:#1a1a1a;flex-shrink:0;align-self:center;"></div>
    <div>
      <div style="font-size:9px;font-weight:600;letter-spacing:0.1em;color:#374151;
                  text-transform:uppercase;margin-bottom:4px;">SPENT THIS SESSION</div>
      <div style="font-size:20px;font-weight:800;color:#f5f5f5;
                  font-variant-numeric:tabular-nums;">{_fmt_money(session_spent)}</div>
    </div>
    <div style="width:1px;height:32px;background:#1a1a1a;flex-shrink:0;align-self:center;"></div>
    <div>
      <div style="font-size:9px;font-weight:600;letter-spacing:0.1em;color:#374151;
                  text-transform:uppercase;margin-bottom:4px;">BUDGET REMAINING</div>
      <div style="font-size:20px;font-weight:800;color:{bar_color};
                  font-variant-numeric:tabular-nums;">{_fmt_money(budget_remaining)}</div>
    </div>
    <div style="width:1px;height:32px;background:#1a1a1a;flex-shrink:0;align-self:center;"></div>
    <div>
      <div style="font-size:9px;font-weight:600;letter-spacing:0.1em;color:#374151;
                  text-transform:uppercase;margin-bottom:4px;">CARDS BOUGHT</div>
      <div style="font-size:20px;font-weight:800;color:#f5f5f5;
                  font-variant-numeric:tabular-nums;">{session_cards}</div>
    </div>
  </div>
  <div style="font-size:9px;font-weight:600;letter-spacing:0.08em;color:#374151;
              text-transform:uppercase;margin-bottom:6px;">
    BUDGET USED · {pct_display:.0f}%
  </div>
  <div style="width:100%;height:4px;background:#1a1a1a;border-radius:2px;overflow:hidden;">
    <div style="width:{pct_display:.1f}%;height:100%;background:{bar_color};border-radius:2px;
                transition:width 0.3s ease;"></div>
  </div>
</div>
""", unsafe_allow_html=True)
