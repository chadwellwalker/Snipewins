"""
Inventory Tab — Streamlit UI

Card collection tracker: add purchases, log sales, track profit/ROI,
manage Whatnot stream sessions.

Called from streamlit_app.py:
    import tab_inventory
    tab_inventory.render_inventory_tab()
"""
from __future__ import annotations

import csv
import os
import time
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE        = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR    = os.path.join(_HERE, "data")
_INV_CSV     = os.path.join(_DATA_DIR, "inventory.csv")
_STREAMS_CSV = os.path.join(_DATA_DIR, "streams.csv")

_INV_COLUMNS = [
    "card_id", "player", "card_description", "sport", "condition",
    "purchase_price", "purchase_date", "purchase_source", "ebay_listing_id",
    "market_value_at_purchase", "velocity_tier", "notes",
    "status", "sale_price", "sale_date", "sale_platform", "stream_id",
    "profit", "roi",
]

_STREAM_COLUMNS = [
    "stream_id", "stream_date", "stream_name", "duration_hours",
    "cards_sold", "total_revenue", "total_profit", "status",
]

# ---------------------------------------------------------------------------
# Velocity tier lookup (mirrors ending_soon_engine._PLAYER_MASTER)
# ---------------------------------------------------------------------------

_TIER_LOOKUP: Dict[str, int] = {}

def _build_tier_lookup() -> None:
    global _TIER_LOOKUP
    if _TIER_LOOKUP:
        return
    try:
        import ending_soon_engine as _ese
        for p in _ese._PLAYER_MASTER:
            _TIER_LOOKUP[p["name"].lower()] = p["tier"]
    except Exception:
        pass

def _infer_tier(player_name: str) -> int:
    _build_tier_lookup()
    key = (player_name or "").strip().lower()
    if key in _TIER_LOOKUP:
        return _TIER_LOOKUP[key]
    # fuzzy — check if any known name is contained in the input
    for known, tier in _TIER_LOOKUP.items():
        if known in key or key in known:
            return tier
    return 3

# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def _ensure_data_dir() -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)


def _load_inventory() -> pd.DataFrame:
    _ensure_data_dir()
    if not os.path.exists(_INV_CSV):
        return pd.DataFrame(columns=_INV_COLUMNS)
    try:
        df = pd.read_csv(_INV_CSV, dtype=str)
        # Add missing columns
        for col in _INV_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df[_INV_COLUMNS]
    except Exception:
        return pd.DataFrame(columns=_INV_COLUMNS)


def _save_inventory(df: pd.DataFrame) -> None:
    _ensure_data_dir()
    df.to_csv(_INV_CSV, index=False)


def _load_streams() -> pd.DataFrame:
    _ensure_data_dir()
    if not os.path.exists(_STREAMS_CSV):
        return pd.DataFrame(columns=_STREAM_COLUMNS)
    try:
        df = pd.read_csv(_STREAMS_CSV, dtype=str)
        for col in _STREAM_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df[_STREAM_COLUMNS]
    except Exception:
        return pd.DataFrame(columns=_STREAM_COLUMNS)


def _save_streams(df: pd.DataFrame) -> None:
    _ensure_data_dir()
    df.to_csv(_STREAMS_CSV, index=False)


def _new_id() -> str:
    return f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        v = float(str(val).replace(",", "").replace("$", ""))
        return v if v == v else default  # NaN check
    except (ValueError, TypeError):
        return default


def _safe_int(val: Any, default: int = 3) -> int:
    try:
        return int(float(str(val)))
    except (ValueError, TypeError):
        return default

# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _fmt_money(v: float) -> str:
    return f"${v:,.2f}"

def _fmt_pct(v: float) -> str:
    return f"{v:.1f}%"

def _sport_emoji(sport: str) -> str:
    return {"NFL": "🏈", "MLB": "⚾", "NBA": "🏀"}.get(str(sport).upper(), "🃏")

def _tier_label(t: int) -> str:
    return {1: "T1 Instant", 2: "T2 Fast", 3: "T3 Steady"}.get(t, f"T{t}")

def _tier_color(t: int) -> str:
    return {1: "#ef4444", 2: "#f97316", 3: "#3b82f6"}.get(t, "#6b7280")

def _gain_color(v: float) -> str:
    return "#00ff88" if v > 0 else "#ef4444" if v < 0 else "#6b7280"

def _condition_short(c: str) -> str:
    mapping = {"PSA 10": "PSA 10", "PSA 9": "PSA 9", "BGS 9.5": "BGS 9.5", "Raw": "Raw"}
    return mapping.get(str(c), str(c))

# ---------------------------------------------------------------------------
# Dashboard summary stats
# ---------------------------------------------------------------------------

def _compute_summary(df: pd.DataFrame) -> Dict[str, Any]:
    inv = df[df["status"] == "inventory"].copy()
    sold = df[df["status"] == "sold"].copy()

    total_invested     = sum(_safe_float(v) for v in inv["purchase_price"])
    unrealized_gains   = []
    for _, row in inv.iterrows():
        pp  = _safe_float(row["purchase_price"])
        mv  = _safe_float(row["market_value_at_purchase"])
        if mv > 0:
            unrealized_gains.append(mv - pp)

    total_unrealized   = sum(unrealized_gains)
    cards_in_inventory = len(inv)
    cards_sold_count   = len(sold)

    profits = [_safe_float(r["profit"]) for _, r in sold.iterrows()]
    total_profit   = sum(profits)
    total_revenue  = sum(_safe_float(r["sale_price"]) for _, r in sold.iterrows())

    rois = []
    for _, row in sold.iterrows():
        pp  = _safe_float(row["purchase_price"])
        pr  = _safe_float(row["profit"])
        if pp > 0:
            rois.append(pr / pp * 100)
    avg_roi = sum(rois) / len(rois) if rois else 0.0

    best_flip      = max(profits) if profits else 0.0
    best_flip_card = ""
    if profits:
        idx = profits.index(best_flip)
        best_flip_card = sold.iloc[idx]["player"] if len(sold) > idx else ""

    # Consecutive profitable flips (most recent first)
    streak = 0
    if not sold.empty:
        sorted_sold = sold.copy()
        sorted_sold["_sale_date"] = pd.to_datetime(
            sorted_sold["sale_date"], errors="coerce"
        )
        sorted_sold = sorted_sold.sort_values("_sale_date", ascending=False)
        for _, row in sorted_sold.iterrows():
            if _safe_float(row["profit"]) > 0:
                streak += 1
            else:
                break

    return {
        "cards_in_inventory": cards_in_inventory,
        "total_invested":     total_invested,
        "total_unrealized":   total_unrealized,
        "cards_sold":         cards_sold_count,
        "total_profit":       total_profit,
        "total_revenue":      total_revenue,
        "avg_roi":            avg_roi,
        "best_flip":          best_flip,
        "best_flip_card":     best_flip_card,
        "streak":             streak,
    }

# ---------------------------------------------------------------------------
# Dashboard header
# ---------------------------------------------------------------------------

def _render_summary_strip(stats: Dict[str, Any]) -> None:
    c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8)

    def _metric(col, label: str, value: str, delta_color: str = "#94a3b8") -> None:
        col.markdown(
            f"""<div class="fs-inv-metric">
              <div class="fs-inv-l">{label}</div>
              <div class="fs-inv-v" style="color:{delta_color};">{value}</div>
            </div>""",
            unsafe_allow_html=True,
        )

    _metric(c1, "In Inventory", str(stats["cards_in_inventory"]), "#e2e8f0")
    _metric(c2, "Total Invested", _fmt_money(stats["total_invested"]), "#93c5fd")
    gain_color = _gain_color(stats["total_unrealized"])
    _metric(c3, "Unrealized Gain", _fmt_money(stats["total_unrealized"]), gain_color)
    _metric(c4, "Cards Sold", str(stats["cards_sold"]), "#e2e8f0")
    profit_color = _gain_color(stats["total_profit"])
    _metric(c5, "Total Profit", _fmt_money(stats["total_profit"]), profit_color)
    roi_color = _gain_color(stats["avg_roi"])
    _metric(c6, "Avg ROI", _fmt_pct(stats["avg_roi"]), roi_color)
    best_color = _gain_color(stats["best_flip"])
    best_label = f"{_fmt_money(stats['best_flip'])}"
    if stats["best_flip_card"]:
        best_label += f" ({stats['best_flip_card'].split()[-1]})"
    _metric(c7, "Best Flip", best_label, best_color)
    streak_color = "#22c55e" if stats["streak"] >= 3 else "#f59e0b" if stats["streak"] >= 1 else "#6b7280"
    _metric(c8, "Profit Streak", f"{stats['streak']}🔥" if stats["streak"] else "0", streak_color)
    st.markdown("<div style='margin-top:6px;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 1 — Add Card Form
# ---------------------------------------------------------------------------

def _render_add_form(df: pd.DataFrame) -> pd.DataFrame:
    st.markdown("### Add Card to Inventory")

    with st.form("inv_add_card_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            player = st.text_input("Player Name", placeholder="e.g. Patrick Mahomes")
            card_desc = st.text_input(
                "Card Description",
                placeholder="e.g. 2023 Prizm Silver #149",
            )
            purchase_price = st.number_input(
                "Purchase Price ($)", min_value=0.0, value=0.0, step=0.50, format="%.2f"
            )
            purchase_date = st.date_input("Purchase Date", value=date.today())
            purchase_source = st.selectbox(
                "Purchase Source", ["eBay Auction", "eBay BIN", "Other"]
            )
            ebay_listing_id = st.text_input(
                "eBay Listing ID (optional)", placeholder="e.g. 123456789012"
            )

        with col2:
            sport = st.selectbox("Sport", ["NFL", "MLB", "NBA"])
            condition = st.selectbox(
                "Condition", ["Raw", "PSA 10", "PSA 9", "BGS 9.5", "Other"]
            )

            # Velocity tier — auto-infer but user can override
            inferred_tier = _infer_tier(player) if player else 3
            velocity_tier = st.selectbox(
                "Velocity Tier",
                [1, 2, 3],
                index=inferred_tier - 1,
                format_func=_tier_label,
            )

            # Market value — user enters manually; if listing ID exists, prompt
            mv_note = (
                "Enter card description above, then save — MV lookup runs on save"
                if ebay_listing_id or card_desc
                else "Enter card description to enable MV lookup"
            )
            market_value = st.number_input(
                "Market Value at Purchase ($)",
                min_value=0.0,
                value=0.0,
                step=0.50,
                format="%.2f",
                help=mv_note,
            )
            auto_mv = st.checkbox(
                "Auto-fetch MV from comp engine on save",
                value=bool(card_desc),
            )
            notes = st.text_input("Notes (optional)", placeholder="Any extra notes")

        submitted = st.form_submit_button("💾 Save Card", type="primary", use_container_width=True)

    if submitted:
        if not player.strip():
            st.error("Player name is required.")
            return df
        if purchase_price <= 0:
            st.error("Purchase price must be greater than zero.")
            return df

        # Auto-fetch MV if requested
        final_mv = market_value
        if auto_mv and card_desc.strip():
            with st.spinner("Fetching market value from comp engine…"):
                try:
                    import comp_engine_v2 as _cev2
                    mv_data = _cev2.get_market_value_for_item(card_desc.strip())
                    fetched = mv_data.get("market_value") or 0.0
                    if fetched > 0 and not mv_data.get("insufficient_data"):
                        final_mv = fetched
                        st.success(
                            f"MV fetched: {_fmt_money(final_mv)} "
                            f"(confidence: {mv_data.get('confidence','?')})"
                        )
                    else:
                        st.warning("MV lookup returned insufficient data — enter manually.")
                except Exception as exc:
                    st.warning(f"MV lookup failed: {exc}")

        new_row = {
            "card_id":                  _new_id(),
            "player":                   player.strip(),
            "card_description":         card_desc.strip(),
            "sport":                    sport,
            "condition":                condition,
            "purchase_price":           str(round(purchase_price, 2)),
            "purchase_date":            str(purchase_date),
            "purchase_source":          purchase_source,
            "ebay_listing_id":          ebay_listing_id.strip(),
            "market_value_at_purchase": str(round(final_mv, 2)),
            "velocity_tier":            str(velocity_tier),
            "notes":                    notes.strip(),
            "status":                   "inventory",
            "sale_price":               "",
            "sale_date":                "",
            "sale_platform":            "",
            "stream_id":                "",
            "profit":                   "",
            "roi":                      "",
        }

        new_df  = pd.DataFrame([new_row])
        df      = pd.concat([df, new_df], ignore_index=True)
        _save_inventory(df)
        st.success(f"✅ {player.strip()} added to inventory.")
        st.rerun()

    return df

# ---------------------------------------------------------------------------
# Section 2 — Inventory Table
# ---------------------------------------------------------------------------

def _render_inventory_table(df: pd.DataFrame) -> pd.DataFrame:
    inv = df[df["status"] == "inventory"].copy()

    if inv.empty:
        st.info("No cards in inventory yet. Add one above.")
        return df

    # ── Filter bar ────────────────────────────────────────────────────────
    fc1, fc2, fc3, fc4 = st.columns(4)
    sport_f   = fc1.selectbox("Sport",        ["All", "NFL", "MLB", "NBA"], key="inv_f_sport")
    tier_f    = fc2.selectbox("Velocity Tier", ["All", "Tier 1", "Tier 2", "Tier 3"], key="inv_f_tier")
    cond_f    = fc3.selectbox("Condition",     ["All", "Raw", "Graded"], key="inv_f_cond")
    sort_by   = fc4.selectbox(
        "Sort By",
        ["Purchase Date", "Days Owned", "Unrealized Gain", "Market Value"],
        key="inv_sort",
    )

    if sport_f != "All":
        inv = inv[inv["sport"].str.upper() == sport_f.upper()]
    if tier_f != "All":
        t = int(tier_f.split()[-1])
        inv = inv[inv["velocity_tier"].apply(lambda x: _safe_int(x)) == t]
    if cond_f == "Raw":
        inv = inv[inv["condition"].str.lower() == "raw"]
    elif cond_f == "Graded":
        inv = inv[inv["condition"].str.lower() != "raw"]

    # Compute derived columns for display
    today = date.today()
    rows: List[Dict[str, Any]] = []
    for _, row in inv.iterrows():
        pp   = _safe_float(row["purchase_price"])
        mv   = _safe_float(row["market_value_at_purchase"])
        gain = mv - pp if mv > 0 else 0.0
        gain_pct = (gain / pp * 100) if pp > 0 else 0.0

        try:
            pd_raw = str(row["purchase_date"])
            pdate  = datetime.strptime(pd_raw, "%Y-%m-%d").date()
            days   = (today - pdate).days
        except Exception:
            pdate = None
            days  = 0

        rows.append({
            "_card_id":      row["card_id"],
            "Player":        row["player"],
            "Description":   str(row["card_description"])[:50],
            "Sport":         row["sport"],
            "Condition":     row["condition"],
            "Buy Price":     pp,
            "MV":            mv,
            "Gain $":        gain,
            "Gain %":        gain_pct,
            "Tier":          _safe_int(row["velocity_tier"]),
            "Days Owned":    days,
            "Purchase Date": str(pdate) if pdate else "",
        })

    # Sort
    sort_key_map = {
        "Purchase Date":    ("Purchase Date", True),
        "Days Owned":       ("Days Owned", False),
        "Unrealized Gain":  ("Gain $", False),
        "Market Value":     ("MV", False),
    }
    sk, asc = sort_key_map.get(sort_by, ("Purchase Date", True))
    rows.sort(key=lambda r: r[sk], reverse=not asc)

    st.markdown(
        f"**{len(rows)} card{'s' if len(rows) != 1 else ''} in inventory**",
        unsafe_allow_html=True,
    )

    # ── Header row ────────────────────────────────────────────────────────
    hc = st.columns([2, 3, 1, 1.4, 1.2, 1.2, 1.2, 1.2, 1, 1.2, 1.8])
    for h, col in zip(
        ["Player", "Description", "Sport", "Condition", "Buy $", "MV $",
         "Gain $", "Gain %", "Tier", "Days", "Actions"],
        hc,
    ):
        col.markdown(
            f"<div style='color:#64748b;font-size:0.72rem;font-weight:700;"
            f"text-transform:uppercase;letter-spacing:.05em;'>{h}</div>",
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Rows ──────────────────────────────────────────────────────────────
    sell_key    = "inv_sell_id"
    del_key     = "inv_del_id"
    del_conf_key = "inv_del_confirm"

    for i, row in enumerate(rows):
        cid = row["_card_id"]

        rc = st.columns([2, 3, 1, 1.4, 1.2, 1.2, 1.2, 1.2, 1, 1.2, 1.8])

        sport_em = _sport_emoji(row["Sport"])
        rc[0].markdown(f"**{sport_em} {row['Player']}**")
        rc[1].markdown(
            f"<div style='font-size:0.8rem;color:#cbd5e1;'>{row['Description']}</div>",
            unsafe_allow_html=True,
        )
        rc[2].markdown(row["Sport"])
        rc[3].markdown(
            f"<span style='font-size:0.78rem;'>{row['Condition']}</span>",
            unsafe_allow_html=True,
        )
        rc[4].markdown(_fmt_money(row["Buy Price"]))
        rc[5].markdown(
            _fmt_money(row["MV"]) if row["MV"] > 0 else "—"
        )

        g_col = _gain_color(row["Gain $"])
        rc[6].markdown(
            f"<b style='color:{g_col};'>{_fmt_money(row['Gain $']) if row['MV'] > 0 else '—'}</b>",
            unsafe_allow_html=True,
        )
        rc[7].markdown(
            f"<b style='color:{g_col};'>{_fmt_pct(row['Gain %']) if row['MV'] > 0 else '—'}</b>",
            unsafe_allow_html=True,
        )

        t_color = _tier_color(row["Tier"])
        rc[8].markdown(
            f"<span style='background:{t_color};color:#fff;padding:2px 6px;"
            f"border-radius:4px;font-size:0.68rem;font-weight:700;'>T{row['Tier']}</span>",
            unsafe_allow_html=True,
        )
        rc[9].markdown(str(row["Days Owned"]))

        btn_col = rc[10]
        b1, b2 = btn_col.columns(2)
        if b1.button("💰 Sell", key=f"inv_sell_{cid}_{i}", use_container_width=True):
            st.session_state[sell_key] = cid
            st.session_state[del_key]  = ""
            st.rerun()

        del_label = "✓ Sure?" if st.session_state.get(del_conf_key) == cid else "🗑 Del"
        if b2.button(del_label, key=f"inv_del_{cid}_{i}", use_container_width=True):
            if st.session_state.get(del_conf_key) == cid:
                df = df[df["card_id"] != cid].reset_index(drop=True)
                _save_inventory(df)
                st.session_state[del_conf_key] = ""
                st.success("Card deleted.")
                st.rerun()
            else:
                st.session_state[del_conf_key] = cid

        # ── Mark Sold inline form ─────────────────────────────────────────
        if st.session_state.get(sell_key) == cid:
            with st.container():
                st.markdown(
                    f"<div style='background:#0f172a;border:1px solid #f59e0b;"
                    f"border-radius:8px;padding:14px 18px;margin:6px 0 14px 0;'>",
                    unsafe_allow_html=True,
                )
                st.markdown(f"**Mark as Sold — {row['Player']}**")
                sc1, sc2, sc3 = st.columns(3)
                sale_price    = sc1.number_input(
                    "Sale Price ($)",
                    min_value=0.0,
                    value=float(row["Buy Price"]),
                    step=0.50,
                    format="%.2f",
                    key=f"sp_{cid}",
                )
                sale_date_val = sc2.date_input(
                    "Sale Date", value=date.today(), key=f"sd_{cid}"
                )
                sale_platform = sc3.selectbox(
                    "Platform",
                    ["Whatnot", "eBay", "Other"],
                    key=f"spl_{cid}",
                )

                # Assign to open stream if one exists
                streams_df  = _load_streams()
                open_streams = streams_df[streams_df["status"] == "open"]
                stream_opts  = ["None"] + [
                    f"{r['stream_name']} ({r['stream_date']})"
                    for _, r in open_streams.iterrows()
                ]
                stream_sel = sc1.selectbox(
                    "Add to Stream (optional)", stream_opts, key=f"ss_{cid}"
                )

                bc1, bc2 = st.columns([1, 4])
                if bc1.button("✅ Confirm Sale", key=f"inv_confirm_sale_{cid}", type="primary"):
                    if sale_price <= 0:
                        st.error("Sale price must be greater than zero.")
                    else:
                        pp     = _safe_float(
                            df.loc[df["card_id"] == cid, "purchase_price"].values[0]
                        )
                        profit = round(sale_price - pp, 2)
                        roi    = round(profit / pp * 100, 2) if pp > 0 else 0.0

                        # Resolve stream_id
                        sid = ""
                        if stream_sel != "None" and not open_streams.empty:
                            idx = stream_opts.index(stream_sel) - 1  # -1 for "None"
                            if idx >= 0 and idx < len(open_streams):
                                sid = open_streams.iloc[idx]["stream_id"]

                        df.loc[df["card_id"] == cid, "status"]       = "sold"
                        df.loc[df["card_id"] == cid, "sale_price"]    = str(round(sale_price, 2))
                        df.loc[df["card_id"] == cid, "sale_date"]     = str(sale_date_val)
                        df.loc[df["card_id"] == cid, "sale_platform"] = sale_platform
                        df.loc[df["card_id"] == cid, "stream_id"]     = sid
                        df.loc[df["card_id"] == cid, "profit"]        = str(profit)
                        df.loc[df["card_id"] == cid, "roi"]           = str(roi)
                        _save_inventory(df)

                        # Update stream totals
                        if sid:
                            _update_stream_totals(sid, df)

                        st.session_state[sell_key] = ""
                        st.success(
                            f"Sold for {_fmt_money(sale_price)} — profit: "
                            f"{_fmt_money(profit)} ({_fmt_pct(roi)})"
                        )
                        st.rerun()

                if bc2.button("✕ Cancel", key=f"inv_cancel_sale_{cid}"):
                    st.session_state[sell_key] = ""
                    st.rerun()

                st.markdown("</div>", unsafe_allow_html=True)

    return df

# ---------------------------------------------------------------------------
# Section 3 — Sold History
# ---------------------------------------------------------------------------

def _render_sold_history(df: pd.DataFrame) -> None:
    sold = df[df["status"] == "sold"].copy()

    # Running totals
    total_invested  = sum(_safe_float(r["purchase_price"])        for _, r in sold.iterrows())
    total_revenue   = sum(_safe_float(r["sale_price"])            for _, r in sold.iterrows())
    total_profit    = sum(_safe_float(r["profit"])                for _, r in sold.iterrows())
    rois            = [
        _safe_float(r["roi"]) for _, r in sold.iterrows()
        if _safe_float(r["purchase_price"]) > 0
    ]
    avg_roi = sum(rois) / len(rois) if rois else 0.0

    # Totals strip
    tc1, tc2, tc3, tc4 = st.columns(4)
    def _tot(col, label, val, color):
        col.markdown(
            f"""<div class="fs-inv-metric">
              <div class="fs-inv-l">{label}</div>
              <div class="fs-inv-v" style="color:{color};">{val}</div>
            </div>""",
            unsafe_allow_html=True,
        )
    _tot(tc1, "Total Invested",  _fmt_money(total_invested),  "#93c5fd")
    _tot(tc2, "Total Revenue",   _fmt_money(total_revenue),   "#e2e8f0")
    _tot(tc3, "Total Profit",    _fmt_money(total_profit),    _gain_color(total_profit))
    _tot(tc4, "Avg ROI",         _fmt_pct(avg_roi),           _gain_color(avg_roi))
    st.markdown("<div style='margin:10px 0;'></div>", unsafe_allow_html=True)

    if sold.empty:
        st.info("No sold cards yet.")
        return

    # Sort newest first
    sold["_sale_dt"] = pd.to_datetime(sold["sale_date"], errors="coerce")
    sold = sold.sort_values("_sale_dt", ascending=False)

    # Header
    hc = st.columns([2, 3, 1, 1.2, 1.2, 1, 1.2, 1.1, 1, 1])
    for h, col in zip(
        ["Player", "Card", "Sport", "Buy $", "Sale $", "Platform",
         "Sale Date", "Profit $", "ROI %", "Tier"],
        hc,
    ):
        col.markdown(
            f"<div style='color:#64748b;font-size:0.72rem;font-weight:700;"
            f"text-transform:uppercase;'>{h}</div>",
            unsafe_allow_html=True,
        )
    st.divider()

    for _, row in sold.iterrows():
        pp      = _safe_float(row["purchase_price"])
        sp      = _safe_float(row["sale_price"])
        profit  = _safe_float(row["profit"])
        roi     = _safe_float(row["roi"])
        pc      = _gain_color(profit)
        tier    = _safe_int(row["velocity_tier"])

        rc = st.columns([2, 3, 1, 1.2, 1.2, 1, 1.2, 1.1, 1, 1])
        rc[0].markdown(f"**{row['player']}**")
        rc[1].markdown(
            f"<div style='font-size:0.78rem;color:#cbd5e1;'>{str(row['card_description'])[:48]}</div>",
            unsafe_allow_html=True,
        )
        rc[2].markdown(f"{_sport_emoji(row['sport'])} {row['sport']}")
        rc[3].markdown(_fmt_money(pp))
        rc[4].markdown(_fmt_money(sp))
        rc[5].markdown(str(row["sale_platform"] or "—"))
        rc[6].markdown(str(row["sale_date"] or "—"))
        rc[7].markdown(
            f"<b style='color:{pc};'>{_fmt_money(profit)}</b>",
            unsafe_allow_html=True,
        )
        rc[8].markdown(
            f"<b style='color:{pc};'>{_fmt_pct(roi)}</b>",
            unsafe_allow_html=True,
        )
        tc = _tier_color(tier)
        rc[9].markdown(
            f"<span style='background:{tc};color:#fff;padding:2px 6px;"
            f"border-radius:4px;font-size:0.68rem;font-weight:700;'>T{tier}</span>",
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Stream Tracker helpers
# ---------------------------------------------------------------------------

def _update_stream_totals(stream_id: str, inv_df: pd.DataFrame) -> None:
    """Recompute stream totals from sold cards assigned to this stream."""
    streams_df = _load_streams()
    if streams_df.empty:
        return
    mask = streams_df["stream_id"] == stream_id
    if not mask.any():
        return

    stream_cards = inv_df[
        (inv_df["status"] == "sold") & (inv_df["stream_id"] == stream_id)
    ]
    cards_sold   = len(stream_cards)
    total_rev    = sum(_safe_float(r["sale_price"]) for _, r in stream_cards.iterrows())
    total_profit = sum(_safe_float(r["profit"])     for _, r in stream_cards.iterrows())

    streams_df.loc[mask, "cards_sold"]    = str(cards_sold)
    streams_df.loc[mask, "total_revenue"] = str(round(total_rev, 2))
    streams_df.loc[mask, "total_profit"]  = str(round(total_profit, 2))
    _save_streams(streams_df)

# ---------------------------------------------------------------------------
# Section 4 — Stream Tracker
# ---------------------------------------------------------------------------

def _render_stream_tracker(inv_df: pd.DataFrame) -> None:
    streams_df = _load_streams()

    # ── Start new stream ─────────────────────────────────────────────────
    with st.expander("➕ Start New Stream", expanded=streams_df.empty):
        with st.form("new_stream_form", clear_on_submit=True):
            nc1, nc2, nc3 = st.columns(3)
            s_date     = nc1.date_input("Stream Date",  value=date.today())
            s_name     = nc2.text_input("Stream Name",  placeholder="e.g. Saturday Night Prizm Break")
            s_duration = nc3.number_input("Duration (hours)", min_value=0.0, value=2.0, step=0.5)
            if st.form_submit_button("🚀 Start Stream", type="primary"):
                if not s_name.strip():
                    st.error("Stream name is required.")
                else:
                    new_stream = {
                        "stream_id":     _new_id(),
                        "stream_date":   str(s_date),
                        "stream_name":   s_name.strip(),
                        "duration_hours": str(round(s_duration, 1)),
                        "cards_sold":    "0",
                        "total_revenue": "0.0",
                        "total_profit":  "0.0",
                        "status":        "open",
                    }
                    streams_df = pd.concat(
                        [streams_df, pd.DataFrame([new_stream])],
                        ignore_index=True,
                    )
                    _save_streams(streams_df)
                    st.success(f"Stream '{s_name.strip()}' started.")
                    st.rerun()

    if streams_df.empty:
        st.info("No streams yet. Start one above.")
        return

    # ── Open streams ──────────────────────────────────────────────────────
    open_streams  = streams_df[streams_df["status"] == "open"]
    closed_streams = streams_df[streams_df["status"] == "closed"]

    if not open_streams.empty:
        st.markdown("#### Open Streams")
        for _, stream in open_streams.iterrows():
            sid        = stream["stream_id"]
            sname      = stream["stream_name"]
            sdate      = stream["stream_date"]
            n_sold     = _safe_int(stream["cards_sold"], 0)
            rev        = _safe_float(stream["total_revenue"])
            profit     = _safe_float(stream["total_profit"])

            with st.container():
                sh1, sh2 = st.columns([5, 1])
                sh1.markdown(
                    f"<div style='background:#0f172a;border:1px solid #22c55e;"
                    f"border-radius:8px;padding:12px 18px;'>"
                    f"<b style='color:#22c55e;'>🔴 LIVE</b> &nbsp;"
                    f"<b style='font-size:1.05rem;'>{sname}</b> &nbsp;"
                    f"<span style='color:#94a3b8;font-size:0.85rem;'>{sdate} · "
                    f"{stream['duration_hours']}h</span><br>"
                    f"<span style='color:#93c5fd;'>Cards sold: <b>{n_sold}</b></span> &nbsp;|&nbsp; "
                    f"Revenue: <b>{_fmt_money(rev)}</b> &nbsp;|&nbsp; "
                    f"Profit: <b style='color:{_gain_color(profit)};'>{_fmt_money(profit)}</b>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                if sh2.button("🏁 Close", key=f"close_stream_{sid}", use_container_width=True):
                    streams_df.loc[streams_df["stream_id"] == sid, "status"] = "closed"
                    _save_streams(streams_df)
                    st.success(f"Stream '{sname}' closed.")
                    st.rerun()

            # Cards in this stream
            stream_cards = inv_df[
                (inv_df["status"] == "sold") & (inv_df["stream_id"] == sid)
            ]
            if not stream_cards.empty:
                st.markdown("**Cards sold in this stream:**")
                for _, sc in stream_cards.iterrows():
                    sp_val = _safe_float(sc["sale_price"])
                    pr_val = _safe_float(sc["profit"])
                    sc_col = _gain_color(pr_val)
                    st.markdown(
                        f"• {sc['player']} — {str(sc['card_description'])[:45]} &nbsp;"
                        f"Sale: **{_fmt_money(sp_val)}** &nbsp;"
                        f"Profit: <b style='color:{sc_col};'>{_fmt_money(pr_val)}</b>",
                        unsafe_allow_html=True,
                    )

            # Add unassigned sold cards to this stream
            unassigned = inv_df[
                (inv_df["status"] == "sold") &
                ((inv_df["stream_id"] == "") | inv_df["stream_id"].isna())
            ]
            if not unassigned.empty:
                st.markdown("**Add sold card to this stream:**")
                ac1, ac2 = st.columns([4, 1])
                opts     = [
                    f"{r['player']} — {str(r['card_description'])[:35]} ({r['sale_date']})"
                    for _, r in unassigned.iterrows()
                ]
                sel = ac1.selectbox(
                    "Select sold card",
                    opts,
                    key=f"add_to_stream_sel_{sid}",
                    label_visibility="collapsed",
                )
                if ac2.button("Add", key=f"add_to_stream_{sid}", use_container_width=True):
                    idx_sel = opts.index(sel)
                    cid_add = unassigned.iloc[idx_sel]["card_id"]
                    inv_df.loc[inv_df["card_id"] == cid_add, "stream_id"] = sid
                    _save_inventory(inv_df)
                    _update_stream_totals(sid, inv_df)
                    st.success("Card added to stream.")
                    st.rerun()

            st.markdown("---")

    # ── Closed stream history ──────────────────────────────────────────────
    if not closed_streams.empty:
        st.markdown("#### Stream History")
        closed_sorted = closed_streams.copy()
        closed_sorted["_dt"] = pd.to_datetime(closed_sorted["stream_date"], errors="coerce")
        closed_sorted = closed_sorted.sort_values("_dt", ascending=False)

        hc = st.columns([3, 1.2, 1.2, 1.5, 1.5, 1.5])
        for h, col in zip(
            ["Stream Name", "Date", "Duration", "Cards Sold", "Revenue", "Profit"],
            hc,
        ):
            col.markdown(
                f"<div style='color:#64748b;font-size:0.7rem;font-weight:700;"
                f"text-transform:uppercase;'>{h}</div>",
                unsafe_allow_html=True,
            )
        st.divider()

        for _, stream in closed_sorted.iterrows():
            profit_v = _safe_float(stream["total_profit"])
            pc       = _gain_color(profit_v)
            rc       = st.columns([3, 1.2, 1.2, 1.5, 1.5, 1.5])
            rc[0].markdown(f"**{stream['stream_name']}**")
            rc[1].markdown(stream["stream_date"])
            rc[2].markdown(f"{stream['duration_hours']}h")
            rc[3].markdown(stream["cards_sold"])
            rc[4].markdown(_fmt_money(_safe_float(stream["total_revenue"])))
            rc[5].markdown(
                f"<b style='color:{pc};'>{_fmt_money(profit_v)}</b>",
                unsafe_allow_html=True,
            )

# ---------------------------------------------------------------------------
# Main render entry point
# ---------------------------------------------------------------------------

def render_inventory_tab() -> None:
    st.markdown(
        """
<div class="fs-page-hero">
  <p class="fs-ph-title">INVENTORY · P&amp;L COCKPIT</p>
  <div class="fs-ph-sub">Collection economics, velocity tiers, and stream performance in one surface.</div>
</div>
""",
        unsafe_allow_html=True,
    )

    # Load data
    df = _load_inventory()

    # ── Dashboard Summary strip ───────────────────────────────────────────
    with st.container(border=True):
        st.markdown(
            '<p class="fs-filter-rail-title"><span>◇</span> Portfolio snapshot</p>',
            unsafe_allow_html=True,
        )
        stats = _compute_summary(df)
        _render_summary_strip(stats)
    st.divider()

    # ── Sub-tabs ──────────────────────────────────────────────────────────
    tab_inv, tab_sold, tab_streams = st.tabs(
        ["📋 Inventory", "✅ Sold History", "🎙 Stream Tracker"]
    )

    with tab_inv:
        # Add form at top
        df = _render_add_form(df)
        st.markdown("---")
        st.markdown("### Current Inventory")
        df = _render_inventory_table(df)

    with tab_sold:
        st.markdown("### Sold History")
        _render_sold_history(df)

    with tab_streams:
        st.markdown("### Whatnot Stream Tracker")
        _render_stream_tracker(df)
