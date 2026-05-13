"""
comp_tester.py — Standalone Streamlit UI for comp_engine_v2.

Run with:
    streamlit run comp_tester.py

Features:
- Paste any eBay card title and click "Run Comp"
- Shows parsed card attributes
- Shows tier explanation + color-coded market value
- USED comps table + REJECTED comps table
- Session history: last 20 cards tested
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import streamlit as st

import comp_engine_v2 as engine
from comp_engine_v2 import CompResult, ParsedCard

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Comp Tester v2",
    page_icon="🃏",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------

if "history" not in st.session_state:
    st.session_state["history"]: List[CompResult] = []

if "last_result" not in st.session_state:
    st.session_state["last_result"] = None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONFIDENCE_COLORS = {
    "HIGH":   "#2ecc71",   # green
    "MEDIUM": "#f39c12",   # orange
    "LOW":    "#e74c3c",   # red
}

_TIER_COLORS = {
    1: "#27ae60",  # green — exact match
    2: "#3498db",  # blue — relaxed
    3: "#f39c12",  # orange — parallel dropped
    4: "#e74c3c",  # red — broadest
    0: "#95a5a6",  # grey — no result
}


def _mv_color(mv: float) -> str:
    if mv >= 100:
        return "#2ecc71"
    if mv >= 30:
        return "#3498db"
    if mv > 0:
        return "#ecf0f1"
    return "#e74c3c"


def _tier_badge(tier: int) -> str:
    color = _TIER_COLORS.get(tier, "#95a5a6")
    label = f"Tier {tier}" if tier > 0 else "No Match"
    return f'<span style="background:{color};color:#fff;padding:2px 8px;border-radius:4px;font-size:0.85em;font-weight:600">{label}</span>'


def _conf_badge(conf: str) -> str:
    color = _CONFIDENCE_COLORS.get(conf, "#95a5a6")
    return f'<span style="background:{color};color:#fff;padding:2px 8px;border-radius:4px;font-size:0.85em;font-weight:600">{conf}</span>'


def _bool_icon(val: bool) -> str:
    return "✅" if val else "—"


def _render_parsed_card(p: Optional[ParsedCard]) -> None:
    if not p:
        st.warning("Could not parse card title.")
        return

    st.markdown("#### Parsed Card Attributes")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Player", p.player_name or "—")
        st.metric("Year", p.year or "—")
        st.metric("Product", (p.product or "—").title())
        st.metric("Sport", p.sport or "—")
    with col2:
        st.metric("Parallel", (p.parallel or "—").title())
        st.metric("Print Run", f"/{p.print_run}" if p.print_run else "—")
        st.metric("Card #", p.card_number or "—")
        st.metric("Graded", "Yes" if p.is_graded else "Raw")
    with col3:
        st.metric("Grading Co.", p.grading_company or "—")
        st.metric("Grade", p.grade or "—")
        flags = []
        if p.is_rookie:
            flags.append("RC")
        if p.is_auto:
            flags.append("Auto")
        if p.is_patch:
            flags.append("Patch")
        st.metric("Flags", " | ".join(flags) if flags else "—")
        st.metric("Grade Key", p.grade_key or "—")


def _render_result(result: CompResult) -> None:
    """Render the full result panel."""

    # ── Header ──────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Results")

    if result.insufficient_data:
        st.error(
            f"**Insufficient data** — no tier produced ≥{engine.MIN_COMPS_REQUIRED} "
            f"accepted comps. "
            + (f"Error: {result.error}" if result.error else "Try a broader title.")
        )
        if result.comps_rejected:
            _render_rejected_table(result.comps_rejected)
        return

    # ── MV + Confidence + Tier ───────────────────────────────────────────────
    col_mv, col_conf, col_tier, col_comps = st.columns(4)
    with col_mv:
        color = _mv_color(result.final_market_value)
        st.markdown(
            f'<div style="background:#1e1e2e;padding:16px;border-radius:8px;text-align:center">'
            f'<div style="color:#aaa;font-size:0.8em">Market Value</div>'
            f'<div style="color:{color};font-size:2em;font-weight:700">'
            f'${result.final_market_value:.2f}</div></div>',
            unsafe_allow_html=True,
        )
    with col_conf:
        st.markdown(
            f'<div style="background:#1e1e2e;padding:16px;border-radius:8px;text-align:center">'
            f'<div style="color:#aaa;font-size:0.8em">Confidence</div>'
            f'<div style="font-size:1.5em;margin-top:4px">{_conf_badge(result.confidence)}</div></div>',
            unsafe_allow_html=True,
        )
    with col_tier:
        st.markdown(
            f'<div style="background:#1e1e2e;padding:16px;border-radius:8px;text-align:center">'
            f'<div style="color:#aaa;font-size:0.8em">Match Tier</div>'
            f'<div style="font-size:1.5em;margin-top:4px">{_tier_badge(result.match_tier)}</div></div>',
            unsafe_allow_html=True,
        )
    with col_comps:
        st.markdown(
            f'<div style="background:#1e1e2e;padding:16px;border-radius:8px;text-align:center">'
            f'<div style="color:#aaa;font-size:0.8em">Comps Used</div>'
            f'<div style="color:#ecf0f1;font-size:2em;font-weight:700">{result.comp_count}</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Tier explanation ─────────────────────────────────────────────────────
    tier_color = _TIER_COLORS.get(result.match_tier, "#95a5a6")
    st.markdown(
        f'<div style="border-left:4px solid {tier_color};padding:8px 12px;'
        f'background:#1e1e2e;border-radius:0 6px 6px 0;margin-bottom:12px">'
        f'<strong>Tier {result.match_tier}:</strong> {result.tier_description}<br>'
        f'<small style="color:#aaa">Date window: {result.date_range_used} days | '
        f'Discount applied: {result.discount_applied * 100:.0f}% | '
        f'Raw weighted avg: ${result.raw_average:.2f} | '
        f'Price CV: {result.price_cv:.1f}% | StdDev: ${result.price_std_dev:.2f}</small>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Used comps table ─────────────────────────────────────────────────────
    if result.comps_used:
        st.markdown(f"#### Comps Used ({len(result.comps_used)})")
        rows = []
        for c in sorted(result.comps_used, key=lambda x: x.age_days or 0):
            rows.append({
                "Title": c.title[:80] + ("…" if len(c.title) > 80 else ""),
                "Price": f"${c.price:.2f}",
                "Shipping": f"${c.shipping:.2f}" if c.shipping > 0 else "—",
                "Total": f"${c.total:.2f}",
                "Age (days)": f"{c.age_days:.0f}" if c.age_days is not None else "?",
                "Weight": f"{c.weight:.2f}",
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)

    # ── Rejected comps table ─────────────────────────────────────────────────
    _render_rejected_table(result.comps_rejected)


def _render_rejected_table(rejected_comps: list) -> None:
    if not rejected_comps:
        return
    with st.expander(f"Rejected Comps ({len(rejected_comps)})", expanded=False):
        rows = []
        for c in rejected_comps:
            rows.append({
                "Title": c.title[:80] + ("…" if len(c.title) > 80 else ""),
                "Price": f"${c.price:.2f}" if c.price > 0 else "—",
                "Age (days)": f"{c.age_days:.0f}" if c.age_days is not None else "?",
                "Reason": c.reject_reason,
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_history() -> None:
    history: List[CompResult] = st.session_state.get("history", [])
    if not history:
        return

    st.markdown("---")
    st.markdown("### Session History (last 20)")

    rows = []
    for r in reversed(history):
        rows.append({
            "Title": r.raw_title[:60] + ("…" if len(r.raw_title) > 60 else ""),
            "Player": (r.parsed_card.player_name if r.parsed_card else "—"),
            "Year": (r.parsed_card.year if r.parsed_card else "—") or "—",
            "MV": f"${r.final_market_value:.2f}" if not r.insufficient_data else "—",
            "Tier": str(r.match_tier) if r.match_tier > 0 else "—",
            "Confidence": r.confidence,
            "Comps": str(r.comp_count),
            "Status": "OK" if not r.insufficient_data else "Insufficient",
        })

    st.dataframe(rows, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------

st.title("🃏 Comp Engine v2 — Tester")
st.caption(
    "Paste any eBay card listing title and run a 4-tier cascading comp search. "
    "Uses the same eBay Finding API as the main app."
)

# Quick test buttons
_QUICK_TESTS = [
    "2023 Panini Prizm Patrick Mahomes Silver Prizm #1",
    "2022 Topps Chrome Mike Trout Gold Refractor /50",
    "2021 Panini Select Luka Doncic Concourse Silver PSA 10",
    "2023 Bowman Chrome Jackson Holliday Blue Refractor /150",
    "2024 Panini Prizm Josh Allen Purple Prizm /49",
]
st.caption("**Quick Tests:**")
_qt_cols = st.columns(len(_QUICK_TESTS))
_qt_clicked: Optional[str] = None
for _i, (_col, _qt) in enumerate(zip(_qt_cols, _QUICK_TESTS)):
    with _col:
        _short = _qt.split()
        _label = " ".join(_short[2:4]) if len(_short) >= 4 else _qt[:20]
        if st.button(_label, key=f"qt_{_i}", use_container_width=True):
            _qt_clicked = _qt

# Input
col_input, col_btn = st.columns([5, 1])
with col_input:
    title_input = st.text_input(
        "Card Title",
        value=_qt_clicked or "",
        placeholder="e.g. 2023 Panini Prizm Patrick Mahomes Silver Prizm /199 PSA 10",
        label_visibility="collapsed",
    )
with col_btn:
    run_clicked = st.button("Run Comp", type="primary", use_container_width=True)

run_clicked = run_clicked or bool(_qt_clicked)

# Cache control
col_cache, col_clear = st.columns([5, 1])
with col_clear:
    if st.button("Clear Cache", use_container_width=True):
        engine.clear_cache()
        st.success("Cache cleared.")

# ── Run ─────────────────────────────────────────────────────────────────────
if run_clicked and title_input.strip():
    with st.spinner("Searching eBay sold comps…"):
        t0 = time.time()
        result = engine.get_comp_value(title_input.strip())
        elapsed = time.time() - t0

    st.caption(f"Completed in {elapsed:.1f}s")

    # Store in session state
    st.session_state["last_result"] = result
    history: List[CompResult] = st.session_state.get("history", [])
    history.append(result)
    if len(history) > 20:
        history = history[-20:]
    st.session_state["history"] = history

elif run_clicked and not title_input.strip():
    st.warning("Please enter a card title.")

# ── Display current result ───────────────────────────────────────────────────
last = st.session_state.get("last_result")
if last:
    _render_parsed_card(last.parsed_card)
    _render_result(last)

# ── History ──────────────────────────────────────────────────────────────────
_render_history()
