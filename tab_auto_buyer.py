"""
Auto-Buyer Tab — Streamlit UI

Called from streamlit_app.py:
    import tab_auto_buyer
    tab_auto_buyer.render_auto_buyer_tab()
"""
from __future__ import annotations

import csv
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import streamlit as st

import auto_buyer_engine as _eng
import ebay_bid as _ebay_bid

_SESSION_LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session_logs")


# ══════════════════════════════════════════════════════════════════════════════
# Audio alert via JavaScript AudioContext
# ══════════════════════════════════════════════════════════════════════════════

def _play_beep(freq: int = 880, duration_ms: int = 500) -> None:
    """Trigger a browser beep using the Web Audio API."""
    js = f"""
    <script>
    (function() {{
        try {{
            var ctx = new (window.AudioContext || window.webkitAudioContext)();
            var osc = ctx.createOscillator();
            var gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.type = 'sine';
            osc.frequency.value = {freq};
            gain.gain.setValueAtTime(0.35, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + {duration_ms / 1000:.2f});
            osc.start(ctx.currentTime);
            osc.stop(ctx.currentTime + {duration_ms / 1000:.2f});
        }} catch(e) {{}}
    }})();
    </script>
    """
    st.markdown(js, unsafe_allow_html=True)


def _play_budget_alert() -> None:
    """Two-tone alert for budget-complete event."""
    js = """
    <script>
    (function() {
        try {
            var ctx = new (window.AudioContext || window.webkitAudioContext)();
            function tone(freq, start, dur) {
                var osc = ctx.createOscillator();
                var gain = ctx.createGain();
                osc.connect(gain); gain.connect(ctx.destination);
                osc.frequency.value = freq;
                gain.gain.setValueAtTime(0.3, ctx.currentTime + start);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + start + dur);
                osc.start(ctx.currentTime + start);
                osc.stop(ctx.currentTime + start + dur);
            }
            tone(660, 0, 0.3);
            tone(880, 0.35, 0.4);
        } catch(e) {}
    })();
    </script>
    """
    st.markdown(js, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Formatting helpers
# ══════════════════════════════════════════════════════════════════════════════

def _fmt_money(v: float) -> str:
    return f"${v:,.2f}"


def _fmt_time_long(secs: Optional[float]) -> str:
    """Xh Xm Xs"""
    if secs is None or secs <= 0:
        return "ENDED"
    s = int(secs)
    h = s // 3600
    m = (s % 3600) // 60
    sc = s % 60
    if h > 0:
        return f"{h}h {m:02d}m {sc:02d}s"
    return f"{m:02d}m {sc:02d}s"


def _fmt_time_short(secs: Optional[float]) -> str:
    """Xh Xm"""
    if secs is None or secs <= 0:
        return "ENDED"
    s = int(secs)
    h = s // 3600
    m = (s % 3600) // 60
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def _sport_emoji(sport: str) -> str:
    return {"NFL": "🏈", "MLB": "⚾", "NBA": "🏀"}.get(str(sport).upper(), "🃏")


def _deal_badge(deal_class: str) -> str:
    colors = {
        "ELITE":  ("#00ff88", "#052e16"),
        "STRONG": ("#3b82f6", "#1e3a5f"),
        "GOOD":   ("#f59e0b", "#1c1400"),
    }
    bg, _ = colors.get(str(deal_class).upper(), ("#6b7280", "#111"))
    return (
        f'<span style="background:{bg};color:#fff;padding:2px 8px;'
        f'border-radius:4px;font-size:0.72rem;font-weight:700;">'
        f'{deal_class.upper()}</span>'
    )


def _tier_badge(tier: int) -> str:
    colors = {1: "#ef4444", 2: "#f97316", 3: "#3b82f6"}
    labels = {1: "T1 Instant", 2: "T2 Fast", 3: "T3 Steady"}
    c = colors.get(tier, "#6b7280")
    l = labels.get(tier, f"T{tier}")
    return (
        f'<span style="background:{c};color:#fff;padding:2px 7px;'
        f'border-radius:4px;font-size:0.68rem;font-weight:600;">{l}</span>'
    )


# ══════════════════════════════════════════════════════════════════════════════
# Section 1 — Session Setup Panel
# ══════════════════════════════════════════════════════════════════════════════

def _render_setup_panel() -> None:
    st.markdown("### Session Setup")

    col_left, col_right = st.columns([3, 2])

    with col_left:
        budget = st.number_input(
            "Daily Budget ($)",
            min_value=10.0, max_value=50000.0,
            value=float(st.session_state.get("ab_budget", 400.0)),
            step=10.0, key="ab_budget",
        )

        st.markdown("##### Sport Allocation")
        nfl_pct = st.slider("🏈 NFL %", 0, 100,
                            int(st.session_state.get("ab_nfl_pct", 40)), key="ab_nfl_pct")
        mlb_pct = st.slider("⚾ MLB %", 0, 100,
                            int(st.session_state.get("ab_mlb_pct", 40)), key="ab_mlb_pct")
        nba_pct = st.slider("🏀 NBA %", 0, 100,
                            int(st.session_state.get("ab_nba_pct", 20)), key="ab_nba_pct")

        total_pct = nfl_pct + mlb_pct + nba_pct
        if total_pct != 100:
            st.warning(f"⚠️ Allocations must sum to 100% — currently {total_pct}%. Adjust sliders.")
        else:
            st.success("✅ Allocations sum to 100%")

        # Budget-per-sport display
        if total_pct == 100:
            st.markdown(
                f"""
                <div class="fs-panel-surface" style="margin-top:8px;font-size:0.9rem;color:#e5e7eb;">
                  🏈 NFL: <b style="color:#f5f5f5;">{_fmt_money(budget * nfl_pct / 100)}</b>
                  &nbsp;&nbsp;⚾ MLB: <b style="color:#f5f5f5;">{_fmt_money(budget * mlb_pct / 100)}</b>
                  &nbsp;&nbsp;🏀 NBA: <b style="color:#f5f5f5;">{_fmt_money(budget * nba_pct / 100)}</b>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with col_right:
        st.markdown("##### Bid Settings")
        snipe_pct = st.slider(
            "Snipe Target (% of MV)",
            50, 90,
            int(st.session_state.get("ab_snipe_pct", 70)),
            step=5, key="ab_snipe_pct",
            help="Bid this % of market value. 70% = bid $70 when MV is $100.",
        )
        st.caption(f"At 70% MV you target a 30% profit margin before fees.")

        min_deal_class = st.selectbox(
            "Minimum Deal Score",
            ["GOOD", "STRONG", "ELITE"],
            index=["GOOD", "STRONG", "ELITE"].index(
                st.session_state.get("ab_min_deal_class", "GOOD")
            ),
            key="ab_min_deal_class",
            help="GOOD=15%+ below MV  STRONG=25%+  ELITE=40%+",
        )

        st.markdown("&nbsp;")

        # eBay connection status
        if not _ebay_bid.is_configured():
            st.error("eBay bidding not configured.\nAdd EBAY_RUNAME to your .env file.")
        elif not _ebay_bid.is_connected():
            st.warning("eBay account not connected.\nGo to **Ending Soon → Connect eBay Account**.")
        else:
            st.success("✅ eBay account connected")

        can_start = (total_pct == 100
                     and _ebay_bid.is_configured()
                     and _ebay_bid.is_connected())

        if st.button(
            "▶ START AUTO-BUYER",
            type="primary",
            disabled=not can_start,
            use_container_width=True,
            key="ab_start_btn",
        ):
            config = {
                "budget":         float(budget),
                "sport_allocs":   {"NFL": nfl_pct, "MLB": mlb_pct, "NBA": nba_pct},
                "snipe_pct":      snipe_pct / 100.0,
                "min_deal_class": min_deal_class,
            }
            _eng.start_session(config)
            st.rerun()

    # How-it-works expander
    with st.expander("ℹ️ How Auto-Buyer works"):
        st.markdown(
            """
**Scan Phase** (every 10 minutes)
- Fetches eBay auctions ending within 3 hours across all 67 target players
- Searches for BIN listings under your snipe target
- Runs the market value engine on every listing
- Scores every deal (ELITE / STRONG / GOOD)

**Auction Action**
- Listings ending **within 8 minutes**: bid placed immediately at snipe % of MV
- Listings ending in **8 min – 3 hours**: scheduled to auto-bid at the 7-minute mark
- Never bids on the same item twice; outbids go to Flagged for Review

**BIN Action**
- Any BIN listing under snipe target % of MV surfaces as a gold alert
- Audio alert fires; BUY NOW button opens eBay directly; expires after 10 minutes

**Priority Queue Order**
1. ELITE deals — any sport, any tier
2. Tier 1 players — STRONG or GOOD
3. Tier 2 players — STRONG only
4. Tier 3 players — STRONG only (never auto-buy GOOD for Tier 3)

**Budget Enforcement**
- Tracks committed spend per sport in real time (uses snipe bid as committed amount)
- When a sport hits its cap, remaining budget redistributes to other sports
- Session stops when total budget is exhausted
            """
        )


# ══════════════════════════════════════════════════════════════════════════════
# Running session header & budget bars
# ══════════════════════════════════════════════════════════════════════════════

def _render_running_header(session: Dict[str, Any]) -> None:
    config    = session.get("config") or {}
    budget    = float(config.get("budget") or 0)
    spent     = sum(float(v) for v in (session.get("spent") or {}).values())
    remaining = max(0.0, budget - spent)
    hit_set   = set(session.get("budget_hit") or [])
    now       = time.time()
    status    = session.get("status", "idle")

    # Rate-limit banner
    rl_until = float(session.get("rate_limited_until") or 0)
    if rl_until > now:
        secs_left = int(rl_until - now)
        st.warning(
            f"⚠️ eBay rate limit active — scan paused for {secs_left}s then resumes automatically."
        )

    # Sport budget-hit badges
    if hit_set:
        badges = " ".join(
            f'<span style="background:#dc2626;color:#fff;padding:3px 10px;'
            f'border-radius:4px;font-weight:700;margin-right:4px;">'
            f'{_sport_emoji(s)} {s} BUDGET HIT</span>'
            for s in sorted(hit_set)
        )
        st.markdown(badges, unsafe_allow_html=True)

    # Budget complete banner + add-budget option
    if status == "complete":
        st.success(f"🏁 SESSION COMPLETE — {_fmt_money(budget)} BUDGET REACHED")
        _play_budget_alert()
        ba1, ba2 = st.columns([2, 1])
        with ba1:
            extra = st.number_input(
                "Add budget ($)", min_value=10.0, value=100.0,
                step=10.0, key="ab_extra_budget",
            )
        with ba2:
            st.markdown("&nbsp;")
            if st.button("➕ Add Budget & Resume", key="ab_add_budget_btn",
                         use_container_width=True):
                _eng.add_budget(float(extra))
                st.rerun()

    # Control row
    next_scan = float(session.get("next_scan_ts") or 0)
    secs_to_scan = max(0, int(next_scan - now))
    scan_count   = int(session.get("scan_count") or 0)
    snipe_pct_disp = int(float(config.get("snipe_pct", 0.70)) * 100)
    hc1, hc2, hc3, hc4 = st.columns([3, 1.3, 1.3, 1.3])
    with hc1:
        st.markdown(
            f"**Session** `{session.get('session_id','')}` &nbsp;|&nbsp; "
            f"Scans: **{scan_count}** &nbsp;|&nbsp; "
            f"Snipe target: **{snipe_pct_disp}% of MV** &nbsp;|&nbsp; "
            f"Min class: **{config.get('min_deal_class','GOOD')}**",
            unsafe_allow_html=True,
        )
    with hc2:
        st.metric("Next Scan", f"{secs_to_scan // 60}m {secs_to_scan % 60:02d}s")
    with hc3:
        st.metric("Remaining", _fmt_money(remaining))
    with hc4:
        st.metric("Spent", _fmt_money(spent))

    # Full-width stop button (JavaScript colors it red by text match)
    st.markdown("""<script>
(function(){function s(){document.querySelectorAll('button').forEach(function(b){
  if(b.textContent&&b.textContent.trim().indexOf('STOP AUTO-BUYER')>=0){
    b.style.setProperty('background-color','#ef4444','important');
    b.style.setProperty('color','#fff','important');
    b.style.setProperty('border-color','#ef4444','important');
    b.style.setProperty('font-weight','900','important');
  }
});}s();var o=new MutationObserver(s);o.observe(document.documentElement,{childList:true,subtree:true});})();
</script>""", unsafe_allow_html=True)
    if st.button("⏹ STOP AUTO-BUYER", type="secondary",
                 use_container_width=True, key="ab_stop_btn"):
        _eng.stop_session()
        st.rerun()

    # Per-sport budget progress bars
    sport_meta = [
        ("NFL", "🏈"),
        ("MLB", "⚾"),
        ("NBA", "🏀"),
    ]
    allocs = config.get("sport_allocs") or {}
    realloc = session.get("reallocated_budget") or {}
    bar_cols = st.columns(3)

    for col, (sport, emoji) in zip(bar_cols, sport_meta):
        with col:
            pct       = float(allocs.get(sport, 0))
            sp_budget = round(budget * pct / 100 + float(realloc.get(sport, 0)), 2)
            sp_spent  = float((session.get("spent") or {}).get(sport, 0))
            sp_rem    = max(0.0, sp_budget - sp_spent)
            bar_w     = int(sp_spent / sp_budget * 100) if sp_budget > 0 else 0
            bar_w     = min(bar_w, 100)
            bar_color = "#ef4444" if sport in hit_set else "#2563eb"
            st.markdown(
                f"""
                <div style="margin-bottom:2px;">
                  <small>{emoji} <b>{sport}</b>
                    <span style="color:#94a3b8;float:right;">{_fmt_money(sp_spent)} / {_fmt_money(sp_budget)}</span>
                  </small>
                  <div style="background:#1a1a1a;border-radius:6px;height:8px;margin-top:4px;">
                    <div style="background:{bar_color};width:{bar_w}%;height:8px;border-radius:6px;"></div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ══════════════════════════════════════════════════════════════════════════════
# Section 3a — BIN Alerts
# ══════════════════════════════════════════════════════════════════════════════

def _render_bin_alerts(session: Dict[str, Any]) -> None:
    now    = time.time()
    alerts = sorted(
        session.get("bin_alerts") or [],
        key=lambda a: -float(a.get("edge_pct") or 0),
    )

    # Detect new alerts and play beep
    prev_ids = set(st.session_state.get("ab_seen_bin_ids") or [])
    new_ids  = {a["item_id"] for a in alerts} - prev_ids
    if new_ids:
        _play_beep(freq=880, duration_ms=700)
    st.session_state["ab_seen_bin_ids"] = [a["item_id"] for a in alerts]

    if not alerts:
        st.markdown(
            '<div class="fs-panel-surface" style="color:#6b7280;text-align:center;">'
            "Scanning for BIN deals under your snipe target…</div>",
            unsafe_allow_html=True,
        )
        return

    for alert in alerts:
        iid      = alert.get("item_id", "")
        is_new   = iid in new_ids
        exp_secs = max(0, int(float(alert.get("expires_at") or 0) - now))
        edge     = float(alert.get("edge_pct") or 0)
        bin_p    = float(alert.get("bin_price") or 0)
        mv       = float(alert.get("market_value") or 0)
        tier     = int(alert.get("whatnot_tier") or 3)
        sport    = str(alert.get("sport") or "")
        url      = alert.get("url", "")

        border = "#fbbf24" if is_new else "#d97706"
        glow   = "box-shadow:0 0 12px rgba(251,191,36,0.4);" if is_new else ""

        new_badge = (
            '<span style="background:#fbbf24;color:#000;padding:1px 7px;'
            'border-radius:3px;font-size:0.68rem;font-weight:700;margin-left:6px;">NEW</span>'
            if is_new else ""
        )

        st.markdown(
            f"""
            <div style="background:#1c1400;border:2px solid {border};
                        border-radius:8px;padding:12px 16px;margin-bottom:10px;{glow}">
              <div style="display:flex;justify-content:space-between;
                          align-items:center;flex-wrap:wrap;gap:8px;">
                <div>
                  <b style="font-size:1rem;">{_sport_emoji(sport)} {alert.get('player_name','')}</b>
                  &nbsp;{_tier_badge(tier)}{new_badge}
                </div>
                <div style="color:#fbbf24;font-weight:700;font-size:1.15rem;">
                  {edge:.1f}% below MV
                </div>
              </div>
              <div style="color:#d1d5db;font-size:0.85rem;margin:6px 0;">
                {alert.get('title','')[:110]}
              </div>
              <div style="display:flex;flex-wrap:wrap;gap:20px;font-size:0.88rem;
                          align-items:center;">
                <span>BIN: <b style="color:#4ade80;">{_fmt_money(bin_p)}</b></span>
                <span>MV: <b>{_fmt_money(mv)}</b></span>
                <span style="color:#94a3b8;">Expires in: <b style="color:#f87171;">{_fmt_time_long(exp_secs)}</b></span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if url:
            st.link_button("🛒 BUY NOW on eBay →", url)


# ══════════════════════════════════════════════════════════════════════════════
# Section 3b — Snipe Queue
# ══════════════════════════════════════════════════════════════════════════════

def _render_snipe_queue(session: Dict[str, Any]) -> None:
    now   = time.time()
    queue = sorted(
        session.get("snipe_queue") or [],
        key=lambda x: float(x.get("fire_at") or 0),
    )

    if not queue:
        st.markdown(
            '<div class="fs-panel-surface" style="color:#6b7280;text-align:center;">'
            "No snipes scheduled yet.</div>",
            unsafe_allow_html=True,
        )
        return

    _CLASS_STYLES = {
        "ELITE":  ("#0a1f14", "#00ff88"),
        "STRONG": ("#0f172a", "#3b82f6"),
        "GOOD":   ("#1c1400", "#f59e0b"),
    }

    for item in queue:
        dc        = str(item.get("deal_class") or "GOOD").upper()
        fire_at   = float(item.get("fire_at") or 0)
        secs_rem  = float(item.get("seconds_remaining") or 0)
        until_fire = max(0.0, fire_at - now)
        mv        = float(item.get("market_value") or 0)
        cp        = float(item.get("current_price") or 0)
        snipe_bid = float(item.get("snipe_bid") or 0)
        tier      = int(item.get("whatnot_tier") or 3)
        sport     = str(item.get("sport") or "")

        bg, border = _CLASS_STYLES.get(dc, ("#1e293b", "#64748b"))
        fire_color = "#ef4444" if until_fire < 120 else "#f87171"

        st.markdown(
            f"""
            <div style="background:{bg};border-left:4px solid {border};
                        border-radius:8px;padding:11px 16px;margin-bottom:8px;">
              <div style="display:flex;justify-content:space-between;
                          align-items:center;flex-wrap:wrap;gap:6px;">
                <div>
                  <b>{_sport_emoji(sport)} {item.get('player_name','')}</b>
                  &nbsp;{_deal_badge(dc)}&nbsp;{_tier_badge(tier)}{"&nbsp;<span style='background:#92400e;color:#fef3c7;border-radius:4px;padding:1px 6px;font-size:0.75rem;font-weight:700;'>⚠️ MED</span>" if str(item.get("mv_confidence","")).upper() == "MEDIUM" else ""}
                </div>
                <div style="color:{fire_color};font-weight:700;">
                  🎯 Fires in: {_fmt_time_long(until_fire)}
                </div>
              </div>
              <div style="color:#cbd5e1;font-size:0.83rem;margin:5px 0;">
                {item.get('title','')[:105]}
              </div>
              <div style="display:flex;flex-wrap:wrap;gap:18px;font-size:0.84rem;">
                <span>Current bid: <b style="color:#93c5fd;">{_fmt_money(cp)}</b></span>
                <span>MV: <b>{_fmt_money(mv)}</b></span>
                <span>Snipe bid: <b style="color:#3b82f6;">{_fmt_money(snipe_bid)}</b></span>
                <span>Auction ends: <b>{_fmt_time_long(secs_rem)}</b></span>
                <span style="color:#94a3b8;">Score: {item.get('deal_score',0)}</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# Section 3c — Completed Buys
# ══════════════════════════════════════════════════════════════════════════════

def _render_completed_buys(session: Dict[str, Any]) -> None:
    completed   = list(reversed(session.get("completed") or []))   # newest first
    bids_placed = int(session.get("bids_placed") or 0)
    bids_won    = int(session.get("bids_won") or 0)
    win_rate    = round(bids_won / bids_placed * 100, 1) if bids_placed > 0 else 0.0

    if not completed:
        st.markdown(
            '<div class="fs-panel-surface" style="color:#6b7280;text-align:center;">'
            "No completed buys yet.</div>",
            unsafe_allow_html=True,
        )
        if bids_placed:
            st.caption(f"Bids placed: {bids_placed} · Win rate: {win_rate:.0f}%")
        return

    total_spent = sum(float(c.get("amount_paid") or 0) for c in completed)
    total_mv    = sum(float(c.get("market_value") or 0) for c in completed)

    # Summary bar
    sm1, sm2, sm3, sm4 = st.columns(4)
    sm1.metric("Bought",    len(completed))
    sm2.metric("Spent",     _fmt_money(total_spent))
    sm3.metric("Total MV",  _fmt_money(total_mv) if total_mv else "—")
    sm4.metric("Win Rate",  f"{win_rate:.0f}%")

    # Per-sport
    by_sport: Dict[str, Dict] = {}
    for c in completed:
        sp = str(c.get("sport") or "?").upper()
        d  = by_sport.setdefault(sp, {"count": 0, "spent": 0.0})
        d["count"] += 1
        d["spent"]  = round(d["spent"] + float(c.get("amount_paid") or 0), 2)
    if by_sport:
        st.caption(
            "  ·  ".join(
                f"{_sport_emoji(sp)} {sp}: {_fmt_money(v['spent'])} ({v['count']})"
                for sp, v in sorted(by_sport.items())
            )
        )

    # Card list
    for c in completed:
        mv   = float(c.get("market_value") or 0)
        paid = float(c.get("amount_paid") or 0)
        edge = round((mv - paid) / mv * 100, 1) if mv > 0 else 0.0
        dc   = str(c.get("deal_class") or "?").upper()

        st.markdown(
            f"""
            <div style="background:#0a1f14;border-left:3px solid #00ff88;
                        border-radius:8px;padding:10px 14px;margin-bottom:8px;">
              <div style="display:flex;justify-content:space-between;flex-wrap:wrap;">
                <span>
                  <b>{_sport_emoji(c.get('sport',''))} {c.get('player_name','')}</b>
                  &nbsp;{_deal_badge(dc)}
                </span>
                <span style="color:#00ff88;font-weight:700;">
                  Won: {_fmt_money(paid)} &nbsp;({edge:.1f}% below MV)
                </span>
              </div>
              <div style="color:#9ca3af;font-size:0.8rem;margin-top:2px;">
                {c.get('title','')[:95]}
                <span style="margin-left:12px;color:#64748b;">{c.get('timestamp','')}</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# Section 3d — Flagged for Review
# ══════════════════════════════════════════════════════════════════════════════

def _render_flagged(session: Dict[str, Any]) -> None:
    flagged = session.get("flagged") or []

    if not flagged:
        st.markdown(
            '<div class="fs-panel-surface" style="color:#6b7280;text-align:center;">'
            "Nothing flagged.</div>",
            unsafe_allow_html=True,
        )
        return

    for item in flagged:
        reason = str(item.get("reason") or "unknown").replace("_", " ").title()
        iid    = item.get("item_id", "")
        err    = str(item.get("error_message") or "")

        c1, c2 = st.columns([7, 1])
        with c1:
            err_html = (
                f'<div style="color:#f87171;font-size:0.75rem;margin-top:2px;">{err[:150]}</div>'
                if err else ""
            )
            st.markdown(
                f"""
                <div style="background:#1f0f0f;border-left:3px solid #ef4444;
                            border-radius:6px;padding:8px 14px;margin-bottom:6px;">
                  <b style="color:#f87171;">{reason}</b>
                  &nbsp;·&nbsp; {item.get('player_name','')}
                  <div style="color:#9ca3af;font-size:0.8rem;margin-top:2px;">
                    {item.get('title','')[:95]}
                  </div>
                  {err_html}
                  <div style="color:#64748b;font-size:0.7rem;margin-top:2px;">
                    {item.get('timestamp','')}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with c2:
            if iid and st.button("✕", key=f"ab_dismiss_{iid}",
                                  use_container_width=True, help="Dismiss"):
                _eng.dismiss_flagged(iid)
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# Section 4 — Session Summary
# ══════════════════════════════════════════════════════════════════════════════

def _render_session_summary(session: Dict[str, Any]) -> None:
    summary = _eng.build_session_summary(session)
    st.markdown("---")
    st.markdown("### 📊 Session Summary")

    r1 = st.columns(5)
    r1[0].metric("Budget",        _fmt_money(summary["budget"]))
    r1[1].metric("Total Spent",   _fmt_money(summary["total_spent"]))
    r1[2].metric("Cards Bought",  summary["cards_bought"])
    r1[3].metric("Avg Discount",  f"{summary['avg_discount_pct']:.1f}%")
    r1[4].metric("Win Rate",      f"{summary['win_rate']:.0f}%")

    r2 = st.columns(4)
    r2[0].metric("Scans Run",    summary["scan_count"])
    r2[1].metric("BIN Alerts",   summary["bin_alerts_count"])
    r2[2].metric("Bids Placed",  summary["bids_placed"])
    r2[3].metric("Bids Won",     summary["bids_won"])

    # By sport
    by_sport = summary.get("by_sport") or {}
    if by_sport:
        st.markdown("**Breakdown by sport:**")
        sp_cols = st.columns(max(1, len(by_sport)))
        for col, (sport, data) in zip(sp_cols, sorted(by_sport.items())):
            col.metric(
                f"{_sport_emoji(sport)} {sport}",
                f"{data['count']} cards",
                f"{_fmt_money(data['spent'])}",
            )

    # By deal class
    by_class = summary.get("by_class") or {}
    if by_class:
        st.markdown("**Breakdown by deal score:**")
        dc_cols = st.columns(max(1, len(by_class)))
        for col, (dc, data) in zip(dc_cols, sorted(by_class.items())):
            col.metric(dc, f"{data['count']} cards", f"{_fmt_money(data['spent'])}")

    # Top card
    top = summary.get("top_card")
    if top:
        mv = float(top.get("market_value") or 0)
        st.info(
            f"⭐ **Top card:** {top.get('player_name','')} — "
            f"{top.get('title','')[:80]}  |  MV: {_fmt_money(mv)}"
        )

    # Export button
    st.markdown("&nbsp;")
    if st.button("📥 Export Session to CSV", key="ab_export_csv"):
        _export_session_csv(session)


def _export_session_csv(session: Dict[str, Any]) -> None:
    os.makedirs(_SESSION_LOGS_DIR, exist_ok=True)
    session_id = session.get("session_id") or datetime.now().strftime("%Y%m%d-%H%M%S")
    fname = os.path.join(_SESSION_LOGS_DIR, f"session_{session_id}.csv")

    completed = session.get("completed") or []
    cols = [
        "session_id", "timestamp", "player_name", "title",
        "sport", "deal_class", "amount_paid", "market_value",
        "edge_pct", "whatnot_tier",
    ]

    with open(fname, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for c in completed:
            mv   = float(c.get("market_value") or 0)
            paid = float(c.get("amount_paid") or 0)
            edge = round((mv - paid) / mv * 100, 1) if mv > 0 else 0.0
            writer.writerow({
                "session_id":  session_id,
                "timestamp":   c.get("timestamp", ""),
                "player_name": c.get("player_name", ""),
                "title":       c.get("title", "")[:120],
                "sport":       c.get("sport", ""),
                "deal_class":  c.get("deal_class", ""),
                "amount_paid": f"{paid:.2f}",
                "market_value": f"{mv:.2f}",
                "edge_pct":    edge,
                "whatnot_tier": c.get("whatnot_tier", ""),
            })

    st.success(f"✅ Exported {len(completed)} records to:\n`{fname}`")


# ══════════════════════════════════════════════════════════════════════════════
# Main entry point
# ══════════════════════════════════════════════════════════════════════════════

def render_auto_buyer_tab() -> None:
    """Called from streamlit_app.py when the Auto-Buyer page is selected."""

    # ── Section header CSS ─────────────────────────────────────────────────
    st.markdown("""<style>
.ab-sec {
    font-size: 10px !important; font-weight: 800 !important;
    letter-spacing: 0.15em !important; text-transform: uppercase !important;
    font-family: Inter, sans-serif !important; padding: 8px 0 8px 14px !important;
    margin: 4px 0 10px 0 !important; border-radius: 4px !important;
}
.ab-sec-gold { color: #fbbf24 !important; border-left: 3px solid #fbbf24 !important; background: rgba(251,191,36,0.04) !important; }
.ab-sec-blue { color: #3b82f6 !important; border-left: 3px solid #3b82f6 !important; background: rgba(59,130,246,0.04) !important; }
.ab-sec-green { color: #00ff88 !important; border-left: 3px solid #00ff88 !important; background: rgba(0,255,136,0.04) !important; }
.ab-sec-red { color: #ef4444 !important; border-left: 3px solid #ef4444 !important; background: rgba(239,68,68,0.04) !important; }
.ab-setup-card {
    background: #111111 !important; border: 1px solid #1a1a1a !important;
    border-radius: 10px !important; padding: 24px !important; margin-bottom: 20px !important;
}
</style>""", unsafe_allow_html=True)

    # ── Header ─────────────────────────────────────────────────────────────
    st.markdown(
        """
<div class="fs-page-hero">
  <p class="fs-ph-title">AUTO-BUYER · COMMAND QUEUE</p>
  <div class="fs-ph-sub">Scheduled snipes, BIN gold alerts, and budget rails — tuned for fast on-camera reads.</div>
</div>
""",
        unsafe_allow_html=True,
    )

    session = _eng.get_session_snapshot()
    status  = session.get("status", "idle")

    # ── Idle / setup ───────────────────────────────────────────────────────
    if status == "idle":
        st.markdown('<div class="ab-setup-card">', unsafe_allow_html=True)
        _render_setup_panel()
        st.markdown('</div>', unsafe_allow_html=True)
        return

    # ── Active / complete ──────────────────────────────────────────────────
    _render_running_header(session)
    st.divider()

    # BIN Alerts — full width at top
    st.markdown(
        '<div class="ab-sec ab-sec-gold">⚡ BIN ALERTS — BUY IT NOW UNDER SNIPE TARGET</div>',
        unsafe_allow_html=True,
    )
    _render_bin_alerts(session)

    st.divider()

    # Snipe Queue + Completed side by side
    sq_col, cb_col = st.columns(2)
    with sq_col:
        st.markdown('<div class="ab-sec ab-sec-blue">🎯 SNIPE QUEUE</div>', unsafe_allow_html=True)
        _render_snipe_queue(session)
    with cb_col:
        st.markdown('<div class="ab-sec ab-sec-green">✅ COMPLETED BUYS</div>', unsafe_allow_html=True)
        _render_completed_buys(session)

    st.divider()

    # Flagged
    st.markdown('<div class="ab-sec ab-sec-red">⚠️ FLAGGED FOR REVIEW</div>', unsafe_allow_html=True)
    _render_flagged(session)

    # Session summary on complete
    if status == "complete":
        _render_session_summary(session)

    # ── Auto-rerun every 2 s while session is running ─────────────────────
    if status == "running":
        # JavaScript reload as backup (handles tab unfocus / sleep)
        st.markdown(
            "<script>setTimeout(function(){window.parent.location.reload();},2000);</script>",
            unsafe_allow_html=True,
        )
        time.sleep(2)
        st.rerun()
