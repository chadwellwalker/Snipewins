"""
SNIPEWINS — Main Streamlit Application
Entry point and tab router. All heavy logic lives in the imported modules.
"""
from __future__ import annotations

import base64
import re
import textwrap
import time
from datetime import datetime, timezone
from html import escape, unescape
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

# ── Must be the very first Streamlit call ─────────────────────────────────────
st.set_page_config(
    page_title="SNIPEWINS",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Global CSS — dark premium shell ──────────────────────────────────────────
# IMPORTANT: every line is left-stripped before injection. Streamlit's markdown
# parser treats ANY line with 4+ leading spaces as an indented code block, which
# would render the entire CSS string as visible <pre> text. lstrip on every line
# guarantees no line trips that path. CSS doesn't care about whitespace, browsers
# will render styles identically.
st.markdown(
    "\n".join(_css_line.lstrip() for _css_line in ("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');

    /* ════════════════════════════════════════════════════
       BASE CHROME — matches snipewins.com landing page palette
       bg:#0a0a0a · surface:#141414 · strike:#4ade80 · text:#fafafa
    ════════════════════════════════════════════════════ */
    html, body, [data-testid="stAppViewContainer"] {
        background-color: #0a0a0a !important;
        color: #fafafa;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    /* Numbers (prices, timers, KPIs, money values) use JetBrains Mono
       to match the landing page's monospaced number aesthetic. Add
       class="mono" to any element to opt in. */
    .mono, [data-testid="stMetricValue"], .sw-kpi-value {
        font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace !important;
        font-variant-numeric: tabular-nums;
    }
    [data-testid="stHeader"]  { background: #0a0a0a !important; border-bottom: 1px solid #2a2a2a; }
    [data-testid="stSidebar"] { background: #0a0a0a !important; }
    section.main > div        { padding-top: 0 !important; }
    .block-container          { padding-top: 0.5rem !important; padding-bottom: 2rem !important; max-width: 1400px !important; }

    /* Hide Streamlit's own top decoration */
    [data-testid="stDecoration"] { display: none !important; }

    /* ════════════════════════════════════════════════════
       NAV BUTTONS  (primary = active page, secondary = inactive)
       All buttons share white-space: nowrap to prevent label wrapping.
    ════════════════════════════════════════════════════ */
    button[kind="primary"],
    button[kind="secondary"] {
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        width: 100% !important;
    }
    button[kind="primary"] {
        background: #0d1f12 !important;
        color: #22c55e !important;
        font-size: 0.71rem !important;
        font-weight: 700 !important;
        letter-spacing: 0.07em !important;
        text-transform: uppercase !important;
        border-radius: 5px !important;
        border: 1px solid #2a5c34 !important;
        border-bottom: 2px solid #4ade80 !important;
        box-shadow: 0 0 12px rgba(74,222,128,0.12), inset 0 1px 0 rgba(74,222,128,0.07) !important;
        padding: 0.42rem 0.6rem !important;
        transition: all 0.12s ease !important;
    }
    button[kind="primary"]:hover {
        background: #163020 !important;
        color: #86efac !important;
        border-color: #22c55e !important;
        border-bottom-color: #22c55e !important;
        box-shadow: 0 0 18px rgba(74,222,128,0.22) !important;
    }
    button[kind="secondary"] {
        background: #0a0a0a !important;
        color: #555555 !important;
        font-size: 0.71rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.06em !important;
        text-transform: uppercase !important;
        border: 1px solid #1f1f1f !important;
        border-bottom: 2px solid transparent !important;
        border-radius: 5px !important;
        padding: 0.42rem 0.6rem !important;
        transition: all 0.12s ease !important;
    }
    button[kind="secondary"]:hover {
        background: #161616 !important;
        color: #888888 !important;
        border-color: #2a2a2a !important;
    }

    /* ── Suppress Streamlit's default button p margin inside nav ── */
    [data-testid="stButton"] > button > div > p {
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        margin: 0 !important;
    }

    /* ── Nav shell container ── */
    .sw-nav-shell {
        background: #0a0a0a;
        border: 1px solid #1f1f1f;
        border-bottom: 1px solid #4ade80;
        border-radius: 8px 8px 0 0;
        padding: 0.55rem 0.5rem 0;
        margin-bottom: 0;
    }
    .sw-nav-divider {
        height: 1px;
        background: linear-gradient(90deg, #4ade80 0%, #2a2a2a 50%, #0a0a0a 100%);
        margin: 0 0 1rem 0;
    }

    /* ════════════════════════════════════════════════════
       PAGE SHELL  (overline / title / subtitle block)
    ════════════════════════════════════════════════════ */
    .sw-page-shell {
        margin: 0 0 1.5rem 0;
        padding: 1rem 1.5rem;
        background: linear-gradient(90deg, #1a1a1a 0%, #0a0a0a 100%);
        border: 1px solid #2a2a2a;
        border-left: 3px solid #4ade80;
        border-radius: 0 8px 8px 0;
    }
    .sw-page-shell-label {
        font-size: 0.63rem;
        font-weight: 800;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: #4ade80;
        margin-bottom: 0.3rem;
    }
    .sw-page-shell-title {
        font-size: 1.4rem;
        font-weight: 800;
        color: #fafafa;
        letter-spacing: -0.025em;
        line-height: 1.1;
        margin-bottom: 0.3rem;
    }
    .sw-page-shell-subtitle {
        font-size: 0.82rem;
        color: #888888;
        font-weight: 400;
        max-width: 720px;
        line-height: 1.5;
    }

    /* ════════════════════════════════════════════════════
       NAV BAR CONTAINER
    ════════════════════════════════════════════════════ */
    .sw-shell-nav {
        display: flex;
        align-items: stretch;
        gap: 0;
        padding: 0.5rem 0 1rem 0;
        margin-bottom: 1rem;
        border-bottom: 1px solid #2a2a2a;
    }

    /* ════════════════════════════════════════════════════
       KPI TILES
    ════════════════════════════════════════════════════ */
    .sw-kpi-card {
        background: #141414;
        border: 1px solid #2a2a2a;
        border-radius: 10px;
        padding: 0.9rem 1.1rem 0.8rem;
        position: relative;
        overflow: hidden;
        height: 100%;
    }
    .sw-kpi-card::before {
        content: '';
        position: absolute;
        top: 0; left: 0;
        width: 3px; height: 100%;
    }
    .sw-kpi-card.kpi-green::before  { background: #22c55e; }
    .sw-kpi-card.kpi-blue::before   { background: #22c55e; }
    .sw-kpi-card.kpi-amber::before  { background: #f59e0b; }
    .sw-kpi-card.kpi-muted::before  { background: #3a3a3a; }
    .sw-kpi-card.kpi-red::before    { background: #ef4444; }
    .sw-kpi-label {
        font-size: 0.63rem;
        font-weight: 800;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #666666;
        margin-bottom: 0.4rem;
    }
    .sw-kpi-value {
        font-size: 1.6rem;
        font-weight: 800;
        color: #fafafa;
        line-height: 1;
        font-variant-numeric: tabular-nums;
        letter-spacing: -0.02em;
    }
    .sw-kpi-value.kpi-green  { color: #22c55e; }
    .sw-kpi-value.kpi-blue   { color: #22c55e; }
    .sw-kpi-value.kpi-red    { color: #ef4444; }
    .sw-kpi-value.kpi-amber  { color: #f59e0b; }
    .sw-kpi-sub {
        font-size: 0.7rem;
        color: #666666;
        margin-top: 0.3rem;
        font-weight: 500;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    /* ════════════════════════════════════════════════════
       COMMAND STRIP
    ════════════════════════════════════════════════════ */
    .sw-command-strip {
        background: #0a0a0a;
        border: 1px solid #1f1f1f;
        border-top: none;
        border-radius: 0 0 8px 8px;
        padding: 0.6rem 1rem 0.5rem;
        margin: 0 0 1rem 0;
    }
    .sw-command-strip-label {
        font-size: 0.58rem;
        font-weight: 800;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: #2a2a2a;
        margin-bottom: 0.5rem;
    }

    /* KPI row visual top border to dock with command strip */
    .sw-kpi-row-top {
        border: 1px solid #1f1f1f;
        border-bottom: none;
        border-radius: 8px 8px 0 0;
        padding: 0.6rem 0.75rem 0.5rem;
        background: #0a0a0a;
        margin-bottom: 0;
    }
    .sw-kpi-row-label {
        font-size: 0.58rem;
        font-weight: 800;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: #2a2a2a;
        margin-bottom: 0.4rem;
    }

    /* ════════════════════════════════════════════════════
       SECTION HEADERS
    ════════════════════════════════════════════════════ */
    .sw-section-hdr {
        font-size: 0.62rem;
        font-weight: 800;
        letter-spacing: 0.15em;
        text-transform: uppercase;
        color: #3a3a3a;
        margin: 1.5rem 0 0.75rem;
        display: flex;
        align-items: center;
        gap: 0.6rem;
    }
    .sw-section-hdr::after {
        content: '';
        flex: 1;
        height: 1px;
        background: #2a2a2a;
    }

    /* ════════════════════════════════════════════════════
       EMPTY / WAITING STATE
    ════════════════════════════════════════════════════ */
    .sw-empty-state {
        background: #0a0a0a;
        border: 1px dashed #3a3a3a;
        border-radius: 12px;
        padding: 4rem 2rem;
        text-align: center;
        margin-top: 1.25rem;
    }
    .sw-empty-state-icon {
        font-size: 2.6rem;
        margin-bottom: 1rem;
        display: block;
        opacity: 0.5;
        filter: grayscale(0.3);
    }
    .sw-empty-state-title {
        font-size: 1rem;
        font-weight: 700;
        color: #fafafa;
        margin-bottom: 0.5rem;
        letter-spacing: -0.01em;
    }
    .sw-empty-state-body {
        font-size: 0.82rem;
        color: #666666;
        max-width: 360px;
        margin: 0 auto;
        line-height: 1.65;
    }
    .sw-empty-state-body strong { color: #888888; }

    /* ════════════════════════════════════════════════════
       DATAFRAME
    ════════════════════════════════════════════════════ */
    [data-testid="stDataFrame"] {
        border: 1px solid #2a2a2a !important;
        border-radius: 8px !important;
        overflow: hidden !important;
    }
    .dvn-scroller { background: #141414 !important; }
    [data-testid="stDataFrame"] thead th {
        background: #141414 !important;
        color: #666666 !important;
        font-size: 0.68rem !important;
        font-weight: 700 !important;
        letter-spacing: 0.08em !important;
        text-transform: uppercase !important;
        border-bottom: 1px solid #2a2a2a !important;
    }

    /* ════════════════════════════════════════════════════
       FORMS / INPUTS
    ════════════════════════════════════════════════════ */
    div[data-testid="stForm"] {
        background: #141414;
        border: 1px solid #2a2a2a;
        border-radius: 10px;
        padding: 1.25rem 1.5rem 1rem;
    }
    input, textarea, [data-baseweb="select"] {
        background: #1c1c1c !important;
        color: #fafafa !important;
        border-color: #3a3a3a !important;
    }
    label { color: #888888 !important; font-size: 0.8rem !important; }

    /* ════════════════════════════════════════════════════
       MISC UI CHROME
    ════════════════════════════════════════════════════ */
    [data-testid="stMetric"] {
        background: #141414;
        border: 1px solid #2a2a2a;
        border-radius: 8px;
        padding: 0.75rem 1rem;
    }
    [data-testid="stMetricLabel"] { color: #666666 !important; font-size: 0.66rem !important; letter-spacing: 0.1em !important; text-transform: uppercase !important; }
    [data-testid="stMetricValue"] { color: #fafafa !important; font-size: 1.4rem !important; font-weight: 800 !important; }
    hr { border-color: #2a2a2a !important; margin: 0.5rem 0; }
    [data-testid="stAlert"] { border-radius: 8px; border-width: 1px; font-size: 0.84rem; }
    details { background: #141414; border: 1px solid #2a2a2a; border-radius: 8px; padding: 0.25rem 0.75rem; }
    summary { color: #888888; font-size: 0.8rem; font-weight: 600; cursor: pointer; }
    [data-testid="stProgress"] > div > div { background: linear-gradient(90deg, #4ade80, #22c55e) !important; border-radius: 99px !important; }
    [data-testid="stCaption"] p { color: #666666 !important; font-size: 0.76rem !important; }

    /* ════════════════════════════════════════════════════
       DEAL CLASS BADGES
    ════════════════════════════════════════════════════ */
    .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 3px; font-size: 0.68rem; font-weight: 800; letter-spacing: 0.07em; }
    .badge-elite  { background: #021a0d; color: #22c55e; border: 1px solid rgba(34,197,94,0.3); }
    .badge-strong { background: #061524; color: #22c55e; border: 1px solid rgba(74,222,128,0.32); }
    .badge-good   { background: #1c1400; color: #f59e0b; border: 1px solid rgba(245,158,11,0.3); }
    .badge-pass   { background: #0d0d0d; color: #374151; border: 1px solid #1a1a1a; }

    /* ════════════════════════════════════════════════════
       WORDMARK / HEADER CHROME
    ════════════════════════════════════════════════════ */
    .sw-wordmark {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 0.6rem 0 0.5rem;
        border-bottom: 1px solid #1a1a1a;
        margin-bottom: 0.4rem;
    }
    .sw-wordmark-logo {
        font-size: 1.4rem;
        font-weight: 900;
        color: #fafafa;
        letter-spacing: -0.04em;
        line-height: 1;
    }
    .sw-wordmark-logo span { color: #4ade80; }
    .sw-wordmark-tagline {
        font-size: 0.68rem;
        color: #2a2a2a;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
    .sw-wordmark-sep {
        color: #1f1f1f;
        font-size: 1rem;
        font-weight: 100;
    }
    .sw-wordmark-badge {
        margin-left: auto;
        font-size: 0.6rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #3a3a3a;
        background: #0a0a0a;
        border: 1px solid #1f1f1f;
        border-radius: 3px;
        padding: 0.18rem 0.5rem;
    }
    .sw-es-header {
        background: linear-gradient(135deg, #1a1a1a 0%, #0a0a0a 100%);
        border: 1px solid #2a2a2a;
        border-left: 3px solid #22c55e;
        border-radius: 10px;
        padding: 0.95rem 1.1rem;
        margin: 0.4rem 0 1rem 0;
    }
    .sw-es-header-label {
        font-size: 0.64rem;
        font-weight: 800;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: #22c55e;
        margin-bottom: 0.25rem;
    }
    .sw-es-header-title {
        font-size: 1.1rem;
        font-weight: 800;
        color: #fafafa;
        margin-bottom: 0.2rem;
    }
    .sw-es-header-subtitle {
        font-size: 0.8rem;
        color: #888888;
    }
    .sw-es-card {
        background: linear-gradient(180deg, #161616 0%, #141414 100%);
        border: 1px solid #2a2a2a;
        border-radius: 12px;
        padding: 1rem 1.05rem 0.9rem;
        margin-bottom: 0.85rem;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.02);
    }
    .sw-es-card-secondary {
        background: linear-gradient(180deg, #141414 0%, #111111 100%);
        border-color: #121a25;
        box-shadow: none;
        opacity: 0.88;
    }
    /* ── Hero card — slot 0 on the Sniper Board ─────────────────────────── */
    .sw-es-hero-card {
        background: linear-gradient(180deg, #111827 0%, #1c1c1c 100%);
        border: 1.5px solid #f59e0b;
        border-radius: 14px;
        padding: 1.4rem 1.25rem 1.15rem;
        margin-bottom: 1.25rem;
        box-shadow: 0 0 0 1px rgba(245,158,11,0.07),
                    0 6px 40px rgba(245,158,11,0.13),
                    inset 0 1px 0 rgba(255,255,255,0.03);
    }
    .sw-es-hero-execute-card {
        border-color: #dc2626;
        box-shadow: 0 0 0 1px rgba(220,38,38,0.07),
                    0 6px 40px rgba(220,38,38,0.18),
                    inset 0 1px 0 rgba(255,255,255,0.03);
    }
    .sw-es-hero-banner {
        display: flex;
        align-items: center;
        gap: 0.55rem;
        font-size: 0.69rem;
        font-weight: 900;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        margin-bottom: 0.85rem;
        padding-bottom: 0.7rem;
        border-bottom: 1px solid rgba(245,158,11,0.12);
    }
    .sw-es-hero-banner-execute {
        border-bottom-color: rgba(220,38,38,0.14);
    }
    .sw-es-hero-card-title {
        font-size: 1.22rem;
        font-weight: 900;
        color: #fafafa;
        line-height: 1.2;
        margin-bottom: 0.25rem;
    }
    .sw-es-card-top {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 1rem;
        margin-bottom: 0.65rem;
    }
    .sw-es-card-title {
        font-size: 1rem;
        font-weight: 800;
        color: #fafafa;
        line-height: 1.25;
        margin-bottom: 0.2rem;
    }
    .sw-es-card-meta {
        font-size: 0.76rem;
        color: #888888;
        line-height: 1.5;
    }
    .sw-es-scarcity-strip {
        display: flex;
        gap: 0.45rem;
        flex-wrap: wrap;
        align-items: center;
        margin: 0.2rem 0 0.55rem 0;
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: #b0b0b0;
    }
    .sw-es-scarcity-sep {
        color: #666666;
    }
    .sw-es-card-time {
        font-size: 0.78rem;
        font-weight: 700;
        color: #fafafa;
        white-space: nowrap;
    }
    .sw-es-badge-row {
        display: flex;
        gap: 0.45rem;
        flex-wrap: wrap;
        margin-bottom: 0.75rem;
    }
    .sw-es-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
        padding: 0.22rem 0.5rem;
        border-radius: 999px;
        font-size: 0.67rem;
        font-weight: 800;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        border: 1px solid transparent;
    }
    .sw-es-badge-blue { background: rgba(56,189,248,0.08); color: #22c55e; border-color: rgba(56,189,248,0.28); }
    .sw-es-badge-green { background: rgba(34,197,94,0.08); color: #22c55e; border-color: rgba(34,197,94,0.28); }
    .sw-es-badge-amber { background: rgba(245,158,11,0.08); color: #f59e0b; border-color: rgba(245,158,11,0.28); }
    .sw-es-badge-red { background: rgba(239,68,68,0.08); color: #ef4444; border-color: rgba(239,68,68,0.28); }
    .sw-es-badge-muted { background: rgba(71,85,105,0.14); color: #b0b0b0; border-color: rgba(71,85,105,0.2); }
    .sw-es-badge-lane-ok { background: rgba(34,197,94,0.08); color: #86efac; border-color: rgba(34,197,94,0.28); }
    .sw-es-badge-lane-fallback { background: rgba(245,158,11,0.08); color: #fbbf24; border-color: rgba(245,158,11,0.28); }
    .sw-es-metrics {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(112px, 1fr));
        gap: 0.55rem;
        margin-bottom: 0.8rem;
    }
    .sw-es-metric {
        background: #0a0f18;
        border: 1px solid #2a2a2a;
        border-radius: 8px;
        padding: 0.55rem 0.65rem;
    }
    .sw-es-metric-label {
        font-size: 0.62rem;
        font-weight: 800;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #888888;
        margin-bottom: 0.22rem;
    }
    .sw-es-metric-value {
        font-size: 0.96rem;
        font-weight: 800;
        color: #fafafa;
        line-height: 1.1;
    }
    .sw-es-action-strip {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.9rem;
        padding-top: 0.75rem;
        border-top: 1px solid #2a2a2a;
    }
    .sw-es-action-copy {
        font-size: 0.78rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #fafafa;
    }
    .sw-es-action-note {
        font-size: 0.74rem;
        color: #888888;
    }
    .sw-es-link a {
        color: #22c55e !important;
        font-size: 0.76rem;
        font-weight: 700;
        text-decoration: none;
    }
    </style>
    """).splitlines()),
    unsafe_allow_html=True,
)

# ── Session state — simple dict init, zero recursive calls ───────────────────
_DEFAULTS: Dict[str, Any] = {
    "es_deals": [],
    "es_rows": [],
    "es_meta": {},
    "es_scan_requested": False,
    "es_is_scanning": False,
    "es_scan_error": None,
    "es_last_scan_ts": 0.0,
    "es_watchdog_last_heartbeat_ts": 0.0,
    "es_watchdog_progress_sig": None,
    "es_recent_players": [],
    "es_recent_products": [],
    "es_recent_item_ids": [],
    "br_feed": None,
    "br_hub_state_loaded": False,
    "br_hub_state": {},
    "search_results": [],
    "search_last_kw": "",
}
for _k, _v in _DEFAULTS.items():
    st.session_state.setdefault(_k, _v)

# ── App header ────────────────────────────────────────────────────────────────
# Logo lockup: load the SnipeWins lockup PNG (saved in the sibling
# snipewins-landing folder along with all the other brand image assets) and
# inline it as a base64 data URI so it renders inside the HTML img tag without
# needing Streamlit's static file serving config. Falls back to the old text
# wordmark if the PNG isn't on disk yet — keeps the app working through the
# asset swap.
_now_str = datetime.now().strftime("%b %d, %Y  %H:%M")
_logo_path = (
    Path(__file__).parent.parent
    / "snipewins-landing"
    / "Snipe Wins Logo Black Background.png"
)
if _logo_path.exists():
    try:
        _logo_b64 = base64.b64encode(_logo_path.read_bytes()).decode("ascii")
        # mix-blend-mode: screen makes the logo's pure-black background
        # disappear against the page's pure-black background, eliminating
        # the visible "box edge" that makes a stock PNG look like a sticker.
        # The green and white logo elements pass through virtually unchanged.
        _logo_html = (
            f"<img src='data:image/png;base64,{_logo_b64}' alt='SnipeWins' "
            f"style='height:72px;width:auto;display:block;"
            f"mix-blend-mode:screen;' />"
        )
    except Exception:
        _logo_html = "<div class='sw-wordmark-logo'>⚡ SNIPE<span>WINS</span></div>"
else:
    _logo_html = "<div class='sw-wordmark-logo'>⚡ SNIPE<span>WINS</span></div>"
st.markdown(
    f"<div class='sw-wordmark'>"
    f"{_logo_html}"
    f"<div class='sw-wordmark-tagline'>Sports card auction intelligence</div>"
    f"<div class='sw-wordmark-badge'>{_now_str}</div>"
    f"</div>",
    unsafe_allow_html=True,
)

# Router registry and premium top navigation
APP_MAIN_PAGES = [
    "Ending Soon",
    "Auto-Buyer",
    "Purchased",
    "Search eBay",
    "Steals",
    "Player Hub",
    "Products",
    "Settings",
]

PAGE_REGISTRY: Dict[str, Dict[str, Any]] = {
    "ending_soon": {
        "label": "Ending Soon",
        "icon": "ES",
        "subtitle": "Live auction scan, sniper-ready filters, and execution feed.",
        "enabled": True,
    },
    # NAV-ORDER-2026-05-12: Steals promoted to slot 2 so the user sees the
    # most action-ready feed (auctions ending now → BIN steals) before the
    # journaling tabs (My Snipes, Purchased).
    "buying_radar": {
        "label": "Steals",
        "icon": "ST",
        "subtitle": "Buy-it-now listings priced below market value. Grab and go.",
        "enabled": True,
    },
    "my_snipes": {
        "label": "My Snipes",
        "icon": "MS",
        "subtitle": "Cards you're tracking. Mark wins / losses to build your ROI history.",
        "enabled": True,
    },
    # CLEANUP-HIDDEN-2026-05-06 — Auto-Buyer hidden from user UI: violates eBay
    # ToS for unattended automated bidding. Module tab_auto_buyer.py and the
    # dispatch block at line ~11019 remain on disk but are unreachable. To
    # restore: uncomment the dict entry below.
    # "auto_buyer": {
    #     "label": "Auto-Buyer",
    #     "icon": "AB",
    #     "subtitle": "Automated acquisition workflows and buying controls.",
    #     "enabled": True,
    # },
    "purchased": {
        "label": "Purchased",
        "icon": "PR",
        "subtitle": "Purchased inventory, outcomes, and post-buy tracking.",
        "enabled": True,
    },
    # CLEANUP-HIDDEN-2026-05-06 — Search eBay tab not part of MVP. Underlying
    # ebay_search.py / ebay_tools.py modules remain on disk for backend use.
    # "search_ebay": {
    #     "label": "Search eBay",
    #     "icon": "SE",
    #     "subtitle": "Direct auction and BIN search across live eBay inventory.",
    #     "enabled": True,
    # },
    # CLEANUP-HIDDEN-2026-05-06 — Player Hub hidden from user UI but ALL
    # backend modules (player_hub.py, player_hub_seed.py, player_hub_state.json,
    # player_hub_product_catalog.py) remain in use by the scanners. Do NOT
    # delete those files.
    # "player_hub": {
    #     "label": "Player Hub",
    #     "icon": "PH",
    #     "subtitle": "Player universe, target tracking, and discovery controls.",
    #     "enabled": True,
    # },
    # CLEANUP-HIDDEN-2026-05-06 — Products tab hidden from user UI. Backend
    # product catalog stays in use by scanners.
    # "products": {
    #     "label": "Products",
    #     "icon": "PD",
    #     "subtitle": "Product catalog, family lanes, and target templates.",
    #     "enabled": True,
    # },
    "settings": {
        "label": "Settings",
        "icon": "SG",
        "subtitle": "Fees, bidding rules, and shell-level configuration.",
        "enabled": True,
    },
}


def _render_friendly_tab_error(tab_label: str, exc: Exception) -> None:
    """ERR-FIX 2026-05-12: a calm, branded error card instead of the default
    red st.error box. Keeps the actual traceback behind a discreet collapsible
    so debugging stays possible without scaring trial users on first run."""
    _err_type = type(exc).__name__
    _err_msg  = str(exc)[:160]
    st.markdown(
        f"<div style='margin:18px 0;padding:24px 22px;"
        f"background:linear-gradient(135deg,#161616 0%,#0a0a0a 100%);"
        f"border-radius:14px;border:1px solid rgba(248,113,113,0.25);"
        f"font-family:-apple-system,\\'SF Pro Display\\',Inter,sans-serif;"
        f"color:#fafafa;'>"
        f"<div style='font-size:11px;font-weight:600;letter-spacing:0.18em;"
        f"color:#f87171;text-transform:uppercase;margin-bottom:8px;'>"
        f"{tab_label} · brief hiccup</div>"
        f"<div style='font-size:15px;font-weight:600;color:#fafafa;margin-bottom:4px;'>"
        f"We hit a small snag rendering this view.</div>"
        f"<div style='font-size:13px;color:#b0b0b0;line-height:1.5;'>"
        f"Try refreshing the tab. If it persists, the pipeline behind the "
        f"scenes is still running and your data is safe — only this view "
        f"failed to render."
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    import traceback as _tb
    with st.expander("Tech details (for debugging)", expanded=False):
        st.caption(f"{_err_type}: {_err_msg}")
        st.code(_tb.format_exc())


def _resolve_active_page(_registry: Dict[str, Dict[str, Any]]) -> str:
    _default_page = next(iter(_registry))
    st.session_state.setdefault("active_page", _default_page)
    _active_page = str(st.session_state.get("active_page") or _default_page)
    if _active_page not in _registry:
        _active_page = _default_page
        st.session_state["active_page"] = _active_page
    return _active_page


def _render_shell_top_nav(_registry: Dict[str, Dict[str, Any]]) -> None:
    # Proportional column widths: each tab gets space proportional to its label length
    # so no label is ever force-wrapped into a narrow column.
    _spec = [max(1.0, len(str(m.get("label", ""))) * 0.13) for m in _registry.values()]

    st.markdown("<div class='sw-nav-shell'>", unsafe_allow_html=True)
    _nav_cols = st.columns(_spec, gap="small")
    for _idx, (_page_id, _page_meta) in enumerate(_registry.items()):
        with _nav_cols[_idx]:
            _is_active = st.session_state["active_page"] == _page_id
            _label     = str(_page_meta.get("label") or _page_id)
            if st.button(
                _label,
                key=f"shell_nav_{_page_id}",
                type="primary" if _is_active else "secondary",
                use_container_width=True,
                disabled=not bool(_page_meta.get("enabled", True)),
            ):
                st.session_state["active_page"] = _page_id
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<div class='sw-nav-divider'></div>", unsafe_allow_html=True)


def _render_page_shell(_page_meta: Dict[str, Any]) -> None:
    _icon  = _page_meta.get("icon", "")
    _label = _page_meta.get("label", "")
    _sub   = _page_meta.get("subtitle", "")
    st.markdown(
        f"<div class='sw-page-shell'>"
        f"<div class='sw-page-shell-label'>{_icon}&nbsp;&nbsp;SNIPEWINS</div>"
        f"<div class='sw-page-shell-title'>{_label}</div>"
        f"<div class='sw-page-shell-subtitle'>{_sub}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def _safe_float(_value: Any) -> Optional[float]:
    try:
        if _value is None or _value == "":
            return None
        return float(_value)
    except (TypeError, ValueError):
        return None


_UI_TRUE_MV_CONTRACT_VERSION = "true_mv_exact_support_split_v2"
_UI_BOARD_CONTRACT_CACHE: Dict[str, Dict[str, Any]] = {}


def _ui_exact_comp_count(_row: Dict[str, Any]) -> int:
    _count = 0
    try:
        _count = max(_count, int(float((_row or {}).get("trusted_exact_comp_count") or 0)))
    except (TypeError, ValueError):
        _count = max(_count, 0)
    try:
        _count = max(_count, int(float((_row or {}).get("exact_comp_count") or 0)))
    except (TypeError, ValueError):
        _count = max(_count, 0)
    _trusted_rows = (_row or {}).get("trusted_detail_rows")
    if isinstance(_trusted_rows, list):
        _count = max(_count, len(_trusted_rows))
    return max(0, int(_count or 0))


def _ui_support_comp_count(_row: Dict[str, Any]) -> int:
    _count = 0
    try:
        _count = max(_count, int(float((_row or {}).get("support_comp_count") or 0)))
    except (TypeError, ValueError):
        _count = max(_count, 0)
    _support_rows = (_row or {}).get("support_detail_rows")
    if isinstance(_support_rows, list):
        _count = max(_count, len(_support_rows))
    _supporting = (_row or {}).get("supporting_comps")
    if isinstance(_supporting, list):
        _count = max(_count, len(_supporting))
    return max(0, int(_count or 0))


def _ui_raw_exact_match_count(_row: Dict[str, Any]) -> int:
    _count = 0
    try:
        _count = max(_count, int(float((_row or {}).get("raw_exact_match_count") or 0)))
    except (TypeError, ValueError):
        _count = max(_count, 0)
    _raw_rows = (_row or {}).get("raw_exact_detail_rows")
    if isinstance(_raw_rows, list):
        _count = max(_count, len(_raw_rows))
    _exact_rows = (_row or {}).get("exact_comps")
    if isinstance(_exact_rows, list):
        _count = max(_count, len(_exact_rows))
    return max(0, int(_count or 0))


def _ui_board_contract_item_key(_row: Dict[str, Any]) -> str:
    return str((_row or {}).get("source_item_id") or (_row or {}).get("item_id") or (_row or {}).get("row_key") or id(_row))


def _prep_comp_cache_key_for_ui(_row: Dict[str, Any]) -> str:
    _row = _row if isinstance(_row, dict) else {}
    _key = str(
        _row.get("prep_comp_cache_key")
        or _row.get("item_id")
        or _row.get("source_item_id")
        or _row.get("itemId")
        or _row.get("listing_url")
        or _row.get("url")
        or _row.get("itemWebUrl")
        or ""
    ).strip()
    if _key:
        return _key
    return "|".join(
        str(_row.get(_field) or "").strip()[:80]
        for _field in ("title", "source_title", "current_price", "end_iso")
        if str(_row.get(_field) or "").strip()
    ) or str(id(_row))


def _apply_cached_prep_comp_payload(_row: Dict[str, Any]) -> Dict[str, Any]:
    _row = _row if isinstance(_row, dict) else dict(_row or {})
    _cache_key = _prep_comp_cache_key_for_ui(_row)
    _row["prep_comp_cache_key"] = _cache_key
    _cache = st.session_state.setdefault("es_prep_comp_cache", {})
    _payload = _cache.get(_cache_key) if isinstance(_cache, dict) else None
    if isinstance(_payload, dict):
        _payload_mode = str(_payload.get("prep_comp_mode") or "")
        _payload_fresh = bool(_payload.get("single_card_fresh_run"))
        _payload_source = str(_payload.get("market_value_source") or _payload.get("mv_source") or _payload.get("valuation_source") or _payload.get("source") or "").strip().lower()
        _payload_fallback = _payload_source in {"price_anchor_fallback", "minimum_renderable_evidence", "structured_fallback", "soft_watchlist_estimate"}
        if _payload_fresh and _payload_mode == "fresh_single_card":
            _row.update(dict(_payload))
            if _payload_fallback:
                _row["prep_comp_ready"] = False
                _row["prep_comp_completed_without_verified_mv"] = True
                _row["prep_reference_value"] = None
                _row["prep_target_bid"] = None
        else:
            _row["prep_comp_ready"] = False
            _row["prep_comp_completed_without_verified_mv"] = bool(_row.get("prep_comp_completed"))
            _row["prep_reference_value"] = None
            _row["prep_target_bid"] = None
    _source = str(_row.get("market_value_source") or _row.get("mv_source") or _row.get("valuation_source") or _row.get("source") or "").strip().lower()
    _fallback_source = _source in {"price_anchor_fallback", "minimum_renderable_evidence", "structured_fallback", "soft_watchlist_estimate"}
    _public_count = int(_row.get("public_comp_count") or _row.get("review_public_count") or _row.get("visible_public_comp_count") or 0)
    _market_evidence = int(_row.get("market_evidence_count") or _row.get("verified_market_evidence_count") or 0)
    if bool(_row.get("prep_comp_completed")) and _fallback_source and _public_count <= 0 and _market_evidence <= 0:
        _row["prep_comp_ready"] = False
        _row["prep_comp_completed_without_verified_mv"] = True
        _row["prep_comp_result_reason"] = str(_row.get("prep_comp_result_reason") or "fallback_without_public_evidence")
        _row["prep_reference_label"] = "No verified MV"
        _row["prep_reference_value"] = None
        _row["prep_target_bid"] = None
    return _row


def _ui_coerce_detail_rows(_payload: Any) -> List[Dict[str, Any]]:
    _rows: List[Dict[str, Any]] = []
    if isinstance(_payload, list):
        for _entry in _payload:
            if isinstance(_entry, dict):
                _rows.append(dict(_entry))
    return _rows


def _ui_apply_board_contract_payload(_row: Dict[str, Any], _payload: Dict[str, Any]) -> Dict[str, Any]:
    _item = _row if isinstance(_row, dict) else dict(_row or {})
    for _field, _value in dict(_payload or {}).items():
        if _field == "_board_comp_payload_rows":
            _item[_field] = [dict(_entry) for _entry in list(_value or []) if isinstance(_entry, dict)]
        else:
            _item[_field] = _value
    return _item


def _ui_board_preserve_proven_contract(_row: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(_row, dict):
        return _row
    _has_proven_value = bool(
        _safe_float(_row.get("true_mv")) is not None
        or _safe_float(_row.get("true_market_value")) is not None
        or _safe_float(_row.get("market_value_true")) is not None
        or _safe_float(_row.get("review_estimate")) is not None
        or _safe_float(_row.get("review")) is not None
        or _safe_float(_row.get("review_estimate_value")) is not None
    )
    _has_proven_bid = bool(_safe_float(_row.get("target_bid")) is not None)
    _has_proven_truth = str(
        _row.get("truth")
        or _row.get("valuation_truth_tier")
        or _row.get("_valuation_truth_tier")
        or ""
    ).strip().upper() == "TRUE"
    try:
        _trusted_exact = int(_row.get("trusted_exact_comp_count") or _row.get("exact_comp_count") or 0)
    except Exception:
        _trusted_exact = 0
    _has_proven_exact = _trusted_exact >= 1
    _clean = bool(_row.get("identity_is_clean") or _row.get("_hydrated_identity_is_clean"))
    if _clean and (_has_proven_value or _has_proven_bid) and (_has_proven_truth or _has_proven_exact):
        _row["_board_preserve_proven_contract"] = True
    return _row


def _ui_apply_canonical_board_contract(_row: Dict[str, Any], *, surface: str = "") -> Dict[str, Any]:
    _item = _row if isinstance(_row, dict) else dict(_row or {})
    _item = _ui_board_preserve_proven_contract(_item)
    _item_key = _ui_board_contract_item_key(_item)
    _cached = _UI_BOARD_CONTRACT_CACHE.get(_item_key)
    _title = str(_item.get("title") or _item.get("source_title") or "").strip()
    _preserve_proven = bool(_item.get("_board_preserve_proven_contract"))
    if isinstance(_cached, dict) and not _preserve_proven:
        _item = _ui_apply_board_contract_payload(_item, _cached)
        if surface in {"sniper", "watchlist"}:
            print(
                f"[BOARD_COMP_PAYLOAD_REUSE] title={_title[:140]} item={_item_key[:32]} "
                f"surface={surface} comp_mode={str(_item.get('_board_comp_mode') or 'none')} "
                f"payload_count={int(_item.get('_board_comp_payload_count') or 0)}"
            )
        return _item

    _attempted_truth = str(_item.get("truth") or _item.get("valuation_truth_tier") or _item.get("_valuation_truth_tier") or "NONE").strip().upper() or "NONE"
    _attempted_truth_level = str(_item.get("valuation_truth_level") or "NONE").strip().upper() or "NONE"
    _source = str(
        _item.get("valuation_source_clean")
        or _item.get("market_value_source")
        or _item.get("mv_source")
        or "none"
    ).strip() or "none"
    _true_mv = _safe_float(_item.get("true_mv")) or _safe_float(_item.get("true_market_value")) or _safe_float(_item.get("market_value_true"))
    _review_estimate = (
        _safe_float(_item.get("review_estimate"))
        or _safe_float(_item.get("review"))
        or _safe_float(_item.get("review_estimate_value"))
        or _safe_float(_item.get("anchored_estimate_value"))
    )
    _market_value_raw = _safe_float(_item.get("market_value_raw")) or _safe_float(_item.get("market_value")) or _safe_float(_item.get("mv_value"))
    _raw_exact = _ui_raw_exact_match_count(_item)
    _trusted_exact = _ui_exact_comp_count(_item)
    _support = _ui_support_comp_count(_item)
    _exact_comp_count = max(_trusted_exact, int(float(_item.get("exact_comp_count") or 0)) if str(_item.get("exact_comp_count") or "").strip() else 0)
    _exact_backed = bool(_trusted_exact > 0 or _raw_exact > 0 or _exact_comp_count > 0)
    _trusted_rows = _ui_coerce_detail_rows(_item.get("trusted_detail_rows"))
    _exact_rows = _ui_coerce_detail_rows(_item.get("exact_comps"))
    if not _exact_rows:
        _exact_rows = _ui_coerce_detail_rows(_item.get("raw_exact_detail_rows"))
    _support_rows = _ui_coerce_detail_rows(_item.get("support_detail_rows"))
    if not _support_rows:
        _support_rows = _ui_coerce_detail_rows(_item.get("supporting_comps"))
    _review_rows = [
        dict(_entry)
        for _entry in list(_item.get("review_evidence_payload") or _item.get("renderable_evidence_rows") or [])
        if isinstance(_entry, dict) and bool(_entry.get("renderable"))
    ]
    _target_bid_ready = bool(_item.get("bid_ceiling_ready") or _item.get("target_bid_ready") or _safe_float(_item.get("target_bid")) is not None)
    _execution_final = str(
        _item.get("canonical_board_execution_final")
        or _item.get("execution_final")
        or _item.get("final_execution_decision")
        or _item.get("execution_decision")
        or "PASS"
    ).strip().upper() or "PASS"
    _incoming_preserved = bool(_item.get("canonical_board_preserved") or _item.get("board_contract_preserved") or _preserve_proven)
    _incoming_canonical_truth = str(_item.get("canonical_board_truth") or "").strip().upper()
    _incoming_canonical_truth_level = str(_item.get("canonical_board_truth_level") or "").strip().upper()
    _incoming_canonical_true_mv = _safe_float(_item.get("canonical_board_true_mv"))
    try:
        _incoming_canonical_exact = int(_item.get("canonical_board_exact_comp_count") or 0)
    except (TypeError, ValueError):
        _incoming_canonical_exact = 0
    try:
        _incoming_canonical_support = int(_item.get("canonical_board_support_comp_count") or 0)
    except (TypeError, ValueError):
        _incoming_canonical_support = 0
    _incoming_canonical_target_ready = bool(_item.get("canonical_board_target_bid_ready"))

    _comp_mode = "none"
    _payload_rows: List[Dict[str, Any]] = []
    _truth = _attempted_truth
    _truth_level = _attempted_truth_level
    _value_label = "Review Estimate"
    _value_mode = "review"
    _bid_mode = "review"

    if _exact_backed:
        _truth = "TRUE"
        _truth_level = "EXACT" if (_trusted_exact > 0 or len(_trusted_rows) > 0 or _exact_comp_count > 0) else "EXACT_RESCUE"
        if not _true_mv or _true_mv <= 0:
            _true_mv = _review_estimate or _market_value_raw
        if _trusted_rows:
            _payload_rows = list(_trusted_rows)
        elif _exact_rows:
            _payload_rows = list(_exact_rows)
        elif _support_rows:
            _payload_rows = list(_support_rows)
        _comp_mode = "exact" if _payload_rows and (_trusted_rows or _exact_rows) else ("support" if _payload_rows else "exact")
        _value_label = "Market Value"
        _value_mode = "exact"
        _bid_mode = "exact"
    elif _support_rows:
        _comp_mode = "support"
        _payload_rows = list(_support_rows)
        _truth_level = "SUPPORT" if (_review_estimate and _review_estimate > 0 and (not _true_mv or _true_mv <= 0)) else _attempted_truth_level
        _value_label = "Review Estimate" if (_review_estimate and _review_estimate > 0 and (not _true_mv or _true_mv <= 0)) else "Market Value"
        _value_mode = "support"
        _bid_mode = "support"
    elif _review_rows:
        _comp_mode = "review"
        _payload_rows = list(_review_rows)
        _truth_level = "REVIEW"
        _value_label = "Review Estimate"
        _value_mode = "review"
        _bid_mode = "review"
    else:
        _value_label = "Market Value" if _true_mv and _true_mv > 0 else "Review Estimate" if _review_estimate and _review_estimate > 0 else "Market Value"
        _value_mode = "exact" if _true_mv and _true_mv > 0 else "review" if _review_estimate and _review_estimate > 0 else "none"
        _bid_mode = _value_mode

    _override_blocked = bool(
        _exact_backed
        and (
        _attempted_truth != "TRUE"
        or _attempted_truth_level not in {"EXACT", "EXACT_RESCUE"}
        or str(_source).strip().lower() == "structured_fallback"
        or not (_safe_float(_item.get("true_market_value")) or _safe_float(_item.get("market_value_true")))
        )
    )
    if _override_blocked:
        print(
            f"[BOARD_CONTRACT_OVERRIDE_BLOCKED] title={_title[:140]} item={_item_key[:32]} "
            f"attempted_truth={_attempted_truth or 'NONE'} kept_truth=TRUE "
            f"reason=exact_backed_row_preserved"
        )

    if _exact_backed and _true_mv and _true_mv > 0:
        _true_mv = round(float(_true_mv), 2)
        _item["true_market_value"] = _true_mv
        _item["market_value_true"] = _true_mv
        _item["market_value"] = _true_mv
        _item["mv_value"] = _true_mv
        _item["market_value_mode"] = "true_market_value"
        _item["has_true_market_value"] = True

    _item["valuation_truth_tier"] = _truth
    _item["_valuation_truth_tier"] = _truth
    _item["valuation_truth_level"] = _truth_level
    _item["trusted_exact_comp_count"] = max(_trusted_exact, len(_trusted_rows), _exact_comp_count if _truth_level in {"EXACT", "EXACT_RESCUE"} else 0)
    _item["exact_comp_count"] = max(_trusted_exact, len(_trusted_rows), _exact_comp_count if _truth_level in {"EXACT", "EXACT_RESCUE"} else 0)
    _item["support_comp_count"] = max(_support, len(_support_rows))
    _item["_board_exact_backed_active"] = bool(_exact_backed)
    _item["_board_comp_mode"] = _comp_mode
    _item["_board_comp_payload_rows"] = [dict(_entry) for _entry in _payload_rows]
    _item["_board_comp_payload_count"] = len(_payload_rows)
    _item["_board_value_label"] = _value_label
    _item["_board_value_mode"] = _value_mode
    _item["_board_bid_mode"] = _bid_mode
    _canonical_preserved = bool(_incoming_preserved or _override_blocked)
    if _canonical_preserved:
        _canonical_truth = _incoming_canonical_truth or _truth or "NONE"
        if _preserve_proven and _canonical_truth == "NONE":
            _canonical_truth = "TRUE"
        _canonical_truth_level = _incoming_canonical_truth_level or _truth_level or "NONE"
        _canonical_true_mv = _incoming_canonical_true_mv if _incoming_canonical_true_mv is not None else _true_mv
        _canonical_exact = max(
            _incoming_canonical_exact,
            int(_item.get("trusted_exact_comp_count") or 0),
            int(_item.get("exact_comp_count") or 0),
        )
        _canonical_support = max(
            _incoming_canonical_support,
            int(_item.get("support_comp_count") or 0),
        )
        _canonical_target_ready = bool(_incoming_canonical_target_ready or _target_bid_ready)
        _item["canonical_board_truth"] = _canonical_truth
        _item["canonical_board_truth_level"] = _canonical_truth_level
        if _canonical_true_mv is not None and _canonical_true_mv > 0:
            _item["canonical_board_true_mv"] = round(float(_canonical_true_mv), 2)
        _item["canonical_board_exact_comp_count"] = _canonical_exact
        _item["canonical_board_support_comp_count"] = _canonical_support
        _item["canonical_board_target_bid_ready"] = _canonical_target_ready
        _item["canonical_board_execution_final"] = _execution_final
        _item["canonical_board_preserved"] = True
        if _preserve_proven:
            _item["truth"] = str(_item.get("truth") or _canonical_truth)
            _item["valuation_truth_tier"] = str(_item.get("valuation_truth_tier") or _canonical_truth)
            _item["_valuation_truth_tier"] = str(_item.get("_valuation_truth_tier") or _canonical_truth)
            if _canonical_true_mv is not None and _canonical_true_mv > 0:
                _item["true_mv"] = round(float(_item.get("true_mv") or _canonical_true_mv), 2)
                _item["true_market_value"] = round(float(_item.get("true_market_value") or _canonical_true_mv), 2)
            if _review_estimate is not None and _review_estimate > 0:
                _item["review_estimate"] = round(float(_item.get("review_estimate") or _review_estimate), 2)
                _item["review"] = round(float(_item.get("review") or _review_estimate), 2)
                _item["review_estimate_value"] = round(float(_item.get("review_estimate_value") or _review_estimate), 2)
            _item["trusted_exact_comp_count"] = max(int(_item.get("trusted_exact_comp_count") or 0), _canonical_exact)
            _item["exact_comp_count"] = max(int(_item.get("exact_comp_count") or 0), _canonical_exact)
            _item["board_contract_preserved"] = True
            _item["board_contract_reason"] = "preserve_proven_contract"
            print(
                f"[BOARD_PROVEN_CONTRACT_PRESERVE] "
                f"title={_title[:160]} "
                f"truth={_item.get('truth')} "
                f"true_mv={_item.get('true_mv')} "
                f"review_estimate={_item.get('review_estimate') or _item.get('review')} "
                f"target_bid={_item.get('target_bid')} "
                f"trusted_exact={_item.get('trusted_exact_comp_count')} "
                f"reason=preserve_proven_contract"
            )
            print(
                f"[BOARD_PROVEN_CONTRACT_ASSERT] "
                f"title={_title[:160]} "
                f"truth={_item.get('truth')} "
                f"true_mv={_item.get('true_mv')} "
                f"review_estimate={_item.get('review_estimate') or _item.get('review')} "
                f"target_bid={_item.get('target_bid')} "
                f"trusted_exact={_item.get('trusted_exact_comp_count')} "
                f"board_contract_preserved={_item.get('board_contract_preserved')}"
            )
        print(
            f"[CANONICAL_TRUTH_FREEZE] title={_title[:140]} item={_item_key[:32]} "
            f"truth={_item.get('canonical_board_truth') or 'NONE'} "
            f"truth_level={_item.get('canonical_board_truth_level') or 'NONE'} "
            f"true_mv={round(float(_item.get('canonical_board_true_mv')), 2) if _safe_float(_item.get('canonical_board_true_mv')) is not None else 'None'} "
            f"exact_comp_count={int(_item.get('canonical_board_exact_comp_count') or 0)} "
            f"support_comp_count={int(_item.get('canonical_board_support_comp_count') or 0)} "
            f"target_bid_ready={1 if bool(_item.get('canonical_board_target_bid_ready')) else 0} "
            f"execution_final={_item.get('canonical_board_execution_final') or 'PASS'}"
        )
    if _comp_mode == "exact" and _payload_rows and not _trusted_rows:
        _item["trusted_detail_rows"] = [dict(_entry) for _entry in _payload_rows]
    if _comp_mode == "support" and _payload_rows and not _support_rows:
        _item["support_detail_rows"] = [dict(_entry) for _entry in _payload_rows]

    print(
        f"[BOARD_CONTRACT_CANONICAL] title={_title[:140]} item={_item_key[:32]} "
        f"truth={_truth} true_mv={round(float(_true_mv), 2) if _true_mv and _true_mv > 0 else None} "
        f"review_estimate={round(float(_review_estimate), 2) if _review_estimate and _review_estimate > 0 else None} "
        f"raw_exact={_raw_exact} trusted_exact={int(_item.get('trusted_exact_comp_count') or 0)} "
        f"support={int(_item.get('support_comp_count') or 0)} value_label={_value_label} comp_mode={_comp_mode}"
    )
    print(
        f"[BOARD_VALUE_BID_CONSISTENCY] title={_title[:140]} item={_item_key[:32]} "
        f"value_mode={_value_mode} bid_mode={_bid_mode} consistent={1 if _value_mode == _bid_mode else 0}"
    )

    _payload = {
        "valuation_truth_tier": _item.get("valuation_truth_tier"),
        "_valuation_truth_tier": _item.get("_valuation_truth_tier"),
        "valuation_truth_level": _item.get("valuation_truth_level"),
        "true_market_value": _item.get("true_market_value"),
        "market_value_true": _item.get("market_value_true"),
        "market_value": _item.get("market_value"),
        "mv_value": _item.get("mv_value"),
        "market_value_mode": _item.get("market_value_mode"),
        "has_true_market_value": _item.get("has_true_market_value"),
        "trusted_exact_comp_count": _item.get("trusted_exact_comp_count"),
        "exact_comp_count": _item.get("exact_comp_count"),
        "support_comp_count": _item.get("support_comp_count"),
        "trusted_detail_rows": [dict(_entry) for _entry in list(_item.get("trusted_detail_rows") or []) if isinstance(_entry, dict)],
        "support_detail_rows": [dict(_entry) for _entry in list(_item.get("support_detail_rows") or []) if isinstance(_entry, dict)],
        "_board_exact_backed_active": _item.get("_board_exact_backed_active"),
        "_board_comp_mode": _item.get("_board_comp_mode"),
        "_board_comp_payload_rows": [dict(_entry) for _entry in list(_item.get("_board_comp_payload_rows") or []) if isinstance(_entry, dict)],
        "_board_comp_payload_count": _item.get("_board_comp_payload_count"),
        "_board_value_label": _item.get("_board_value_label"),
        "_board_value_mode": _item.get("_board_value_mode"),
        "_board_bid_mode": _item.get("_board_bid_mode"),
        "canonical_board_truth": _item.get("canonical_board_truth"),
        "canonical_board_truth_level": _item.get("canonical_board_truth_level"),
        "canonical_board_true_mv": _item.get("canonical_board_true_mv"),
        "canonical_board_exact_comp_count": _item.get("canonical_board_exact_comp_count"),
        "canonical_board_support_comp_count": _item.get("canonical_board_support_comp_count"),
        "canonical_board_target_bid_ready": _item.get("canonical_board_target_bid_ready"),
        "canonical_board_execution_final": _item.get("canonical_board_execution_final"),
        "canonical_board_preserved": _item.get("canonical_board_preserved"),
    }
    _UI_BOARD_CONTRACT_CACHE[_item_key] = dict(_payload)
    if surface in {"sniper", "watchlist"}:
        print(
            f"[BOARD_COMP_PAYLOAD_REUSE] title={_title[:140]} item={_item_key[:32]} "
            f"surface={surface} comp_mode={_comp_mode} payload_count={len(_payload_rows)}"
        )
    return _item


def _ui_consume_canonical_truth_contract(
    row: Dict[str, Any],
    *,
    surface: str,
    emit_log: bool = True,
) -> Dict[str, Any]:
    _raw = row if isinstance(row, dict) else {}
    _title = str(_raw.get("title") or _raw.get("source_title") or "").strip()[:140]
    _item = _ui_apply_canonical_board_contract(_raw)
    _item_key = _ui_board_contract_item_key(_item)[:32]
    _attempted_truth = str((_raw or {}).get("valuation_truth_tier") or (_raw or {}).get("_valuation_truth_tier") or "NONE").strip().upper() or "NONE"
    _truth_source = "canonical_board_contract" if bool(_item.get("canonical_board_preserved")) else "row_state"
    _truth = str(
        _item.get("canonical_board_truth")
        or _item.get("valuation_truth_tier")
        or _item.get("_valuation_truth_tier")
        or "NONE"
    ).strip().upper() or "NONE"
    _truth_level = str(
        _item.get("canonical_board_truth_level")
        or _item.get("valuation_truth_level")
        or "NONE"
    ).strip().upper() or "NONE"
    _true_mv = _safe_float(_item.get("canonical_board_true_mv"))
    if _true_mv is None:
        _true_mv = _safe_float(_item.get("true_market_value") or _item.get("market_value_true"))
    try:
        _exact_comp_count = int(_item.get("canonical_board_exact_comp_count") or 0)
    except (TypeError, ValueError):
        _exact_comp_count = 0
    _exact_comp_count = max(
        _exact_comp_count,
        _ui_exact_comp_count(_item),
        int(_safe_float(_item.get("exact_comp_count")) or 0),
    )
    try:
        _support_comp_count = int(_item.get("canonical_board_support_comp_count") or 0)
    except (TypeError, ValueError):
        _support_comp_count = 0
    _support_comp_count = max(_support_comp_count, _ui_support_comp_count(_item))
    if "canonical_board_target_bid_ready" in _item:
        _target_bid_ready = bool(_item.get("canonical_board_target_bid_ready"))
    else:
        _target_bid_ready = bool(_item.get("bid_ceiling_ready") or _item.get("target_bid_ready"))
    _execution_final = str(
        _item.get("canonical_board_execution_final")
        or _item.get("execution_final")
        or _item.get("final_execution_decision")
        or _item.get("execution_decision")
        or "PASS"
    ).strip().upper() or "PASS"
    _preserved = bool(_item.get("canonical_board_preserved"))
    _immune = bool(
        _preserved
        and _truth == "TRUE"
        and _exact_comp_count >= 1
        and _target_bid_ready
    )
    if emit_log and _truth_source == "canonical_board_contract":
        print(
            f"[CANONICAL_TRUTH_CONSUME] title={_title} item={_item_key} "
            f"surface={surface} truth_source=canonical_board_contract "
            f"truth={_truth} true_mv={round(float(_true_mv), 2) if _true_mv is not None else 'None'} "
            f"exact_comp_count={_exact_comp_count} target_bid_ready={1 if _target_bid_ready else 0}"
        )
    if emit_log and _preserved and _attempted_truth != _truth:
        print(
            f"[CANONICAL_TRUTH_DRIFT_BLOCKED] title={_title} item={_item_key} "
            f"attempted_truth={_attempted_truth or 'NONE'} kept_truth={_truth or 'NONE'} blocked=1"
        )
    if emit_log and _immune:
        print(
            f"[CANONICAL_TRUTH_IMMUNITY] title={_title} item={_item_key} "
            f"immune=1 reason=preserved_exact_backed_true_row"
        )
    return {
        "row": _item,
        "truth_source": _truth_source,
        "truth": _truth,
        "truth_level": _truth_level,
        "true_mv": _true_mv,
        "exact_comp_count": _exact_comp_count,
        "support_comp_count": _support_comp_count,
        "target_bid_ready": _target_bid_ready,
        "execution_final": _execution_final,
        "preserved": _preserved,
        "immune": _immune,
    }


def _ui_comp_truth_split(_row: Dict[str, Any]) -> Dict[str, Any]:
    _item = _ui_apply_canonical_board_contract(_row)
    _raw_exact_match_count = _ui_raw_exact_match_count(_item)
    _trusted_exact_comp_count = _ui_exact_comp_count(_item)
    _support_comp_count = _ui_support_comp_count(_item)
    _truth_level = str(_item.get("valuation_truth_level") or "").strip().upper()
    _review_estimate = _safe_float(_item.get("review_estimate_value") or _item.get("anchored_estimate_value"))
    _truth = str(_item.get("valuation_truth_tier") or _item.get("_valuation_truth_tier") or "").strip().upper()
    _true_mv = _safe_float(_item.get("true_market_value") or _item.get("market_value_true"))
    _board_comp_mode = str(_item.get("_board_comp_mode") or "").strip().lower()
    _board_payload_count = int(_item.get("_board_comp_payload_count") or 0)
    if bool(_item.get("_board_exact_backed_active")):
        _truth = "TRUE"
        _truth_level = str(_item.get("valuation_truth_level") or "EXACT").strip().upper() or "EXACT"
        _label = "Comps"
        _display_count = _board_payload_count or max(_trusted_exact_comp_count, _raw_exact_match_count, int(_item.get("exact_comp_count") or 0))
        return {
            "truth": _truth,
            "truth_level": _truth_level,
            "true_mv": _true_mv,
            "raw_exact_match_count": _raw_exact_match_count,
            "trusted_exact_comp_count": max(_trusted_exact_comp_count, int(_item.get("exact_comp_count") or 0)),
            "support_comp_count": _support_comp_count,
            "label": _label,
            "display_count": _display_count,
        }
    _review_locked = bool(_item.get("_mv_truth_locked_review")) and str(_item.get("_mv_truth_lock_kind") or "").strip().lower() == "hard"
    _mv_true_blocked = bool(_item.get("_mv_true_blocked")) or bool(_item.get("_mv_true_block_reason"))
    if _true_mv and _true_mv > 0 and _truth == "TRUE" and _trusted_exact_comp_count > 0 and not _review_locked and not _mv_true_blocked:
        _truth_level = "EXACT"
    elif (_true_mv is None or _true_mv <= 0) and _support_comp_count > 0 and _review_estimate and _review_estimate > 0:
        _truth_level = "SUPPORT"
    elif _review_estimate and _review_estimate > 0:
        _truth_level = "REVIEW"
    else:
        _truth_level = "NONE"
    if _truth_level != "EXACT":
        _trusted_exact_comp_count = 0
    _label = "Comps" if _truth_level == "EXACT" else "Support comps" if _truth_level == "SUPPORT" else ""
    if _board_comp_mode == "support" and _truth_level == "SUPPORT":
        _display_count = _board_payload_count or _support_comp_count
    else:
        _display_count = _trusted_exact_comp_count if _truth_level == "EXACT" else _support_comp_count if _truth_level == "SUPPORT" else 0
    return {
        "truth": _truth or "NONE",
        "truth_level": _truth_level,
        "true_mv": _true_mv,
        "raw_exact_match_count": _raw_exact_match_count,
        "trusted_exact_comp_count": _trusted_exact_comp_count,
        "support_comp_count": _support_comp_count,
        "label": _label,
        "display_count": _display_count,
    }


def _ui_is_synthetic_review_evidence_entry(entry: Dict[str, Any]) -> bool:
    _item = dict(entry or {})
    _kind = str(_item.get("kind") or _item.get("type") or "").strip().lower()
    _label = str(_item.get("label") or "").strip().lower()
    _source = str(_item.get("source") or _item.get("evidence_source") or _item.get("mode") or "").strip().lower()
    _joined = " ".join(_part for _part in [_kind, _label, _source] if _part)
    _synthetic_kinds = {
        "review_estimate",
        "target_bid",
        "bid_anchor",
        "anchor",
        "current_price",
        "internal_ceiling",
        "internal_floor",
    }
    _synthetic_terms = (
        "review estimate",
        "target bid",
        "bid anchor",
        "current price",
        "internal ceiling",
        "internal floor",
        "model-derived",
        "anchor",
    )
    if _kind in _synthetic_kinds:
        return True
    if any(_term in _joined for _term in _synthetic_terms):
        return True
    _has_external_ref = any(
        _item.get(_key)
        for _key in (
            "item_id",
            "source_item_id",
            "url",
            "source_url",
            "comp_url",
            "listing_url",
            "title",
            "source_title",
            "comp_title",
            "listing_title",
            "sale_date",
            "sold_date",
        )
    )
    return not _has_external_ref


def _ui_review_evidence_contract(_row: Dict[str, Any]) -> Dict[str, Any]:
    _item = _ui_apply_canonical_board_contract(_row)
    _title = str(_item.get("title") or _item.get("source_title") or "").strip()
    _truth = str(_item.get("valuation_truth_tier") or _item.get("_valuation_truth_tier") or "NONE").strip().upper() or "NONE"
    _true_mv = _safe_float(_item.get("true_market_value") or _item.get("market_value_true"))
    _review_estimate = _safe_float(_item.get("review_estimate_value") or _item.get("anchored_estimate_value"))
    _review_truth_class = str(_item.get("review_truth_class") or "").strip().lower()
    _raw_rows = [
        dict(_entry)
        for _entry in list(_item.get("review_evidence_payload") or _item.get("renderable_evidence_rows") or [])
        if isinstance(_entry, dict) and bool(_entry.get("renderable"))
    ]
    _market_rows: List[Dict[str, Any]] = []
    _synthetic_rows: List[Dict[str, Any]] = []
    for _entry in _raw_rows:
        if _ui_is_synthetic_review_evidence_entry(_entry):
            _synthetic_rows.append(dict(_entry))
        else:
            _market_rows.append(dict(_entry))
    _anchor_only = bool(
        _truth == "REVIEW"
        and (_true_mv is None or _true_mv <= 0)
        and (
            _review_truth_class == "anchor_only_review"
            or (len(_raw_rows) > 0 and len(_market_rows) == 0 and len(_synthetic_rows) > 0)
        )
    )
    print(
        f"[REVIEW_EVIDENCE_CLASSIFY] title={_title[:140]} total={len(_raw_rows)} "
        f"market_evidence={len(_market_rows)} synthetic_internal={len(_synthetic_rows)} "
        f"anchor_only={1 if _anchor_only else 0}"
    )
    print(
        f"[REVIEW_COUNT_CONTRACT] title={_title[:140]} raw_count={len(_raw_rows)} "
        f"public_count={len(_market_rows)}"
    )
    if _anchor_only and _raw_rows and not _market_rows:
        print(
            f"[REVIEW_EVIDENCE_SUPPRESS] title={_title[:140]} "
            f"reason=synthetic_only_review_payload shown=0"
        )
    return {
        "truth": _truth,
        "true_mv": _true_mv,
        "review_estimate": _review_estimate,
        "raw_rows": list(_raw_rows),
        "market_evidence_rows": list(_market_rows),
        "synthetic_internal_rows": list(_synthetic_rows),
        "raw_count": len(_raw_rows),
        "public_count": len(_market_rows),
        "anchor_only": _anchor_only,
    }


def _ui_evidence_render_contract(_row: Dict[str, Any]) -> Dict[str, Any]:
    _item = _ui_apply_canonical_board_contract(_row)
    _comp_truth = _ui_comp_truth_split(_item)
    _truth = str(_comp_truth.get("truth") or "NONE")
    _truth_level = str(_comp_truth.get("truth_level") or "NONE")
    _evidence_source = str(_item.get("evidence_render_source") or "").strip()
    _trusted_rows = [
        dict(_entry) for _entry in list(_item.get("trusted_detail_rows") or [])
        if isinstance(_entry, dict)
    ]
    _support_rows = [
        dict(_entry) for _entry in list(_item.get("support_detail_rows") or [])
        if isinstance(_entry, dict)
    ]
    _review_payload = [
        dict(_entry) for _entry in list(_item.get("review_evidence_payload") or _item.get("renderable_evidence_rows") or [])
        if isinstance(_entry, dict) and bool(_entry.get("renderable"))
    ]
    _review_contract = _ui_review_evidence_contract(_item)
    _detail_keys_present, _detail_rows = _card_comp_payload_rows(_item)
    _renderable_rows: List[Dict[str, Any]] = []
    _board_comp_mode = str(_item.get("_board_comp_mode") or "").strip().lower()
    _board_payload_rows = [
        dict(_entry) for _entry in list(_item.get("_board_comp_payload_rows") or [])
        if isinstance(_entry, dict)
    ]
    if _board_comp_mode in {"exact", "support"} and _board_payload_rows:
        _renderable_rows = list(_board_payload_rows)
    elif _truth_level == "EXACT" and _trusted_rows:
        _renderable_rows = list(_trusted_rows)
    elif _truth_level == "SUPPORT" and _support_rows:
        _renderable_rows = list(_support_rows)
    elif _truth_level == "REVIEW" and (_evidence_source == "review_payload" or _review_payload):
        _renderable_rows = list(_review_contract.get("market_evidence_rows") or [])
    elif _truth_level in {"REVIEW", "NONE"} and _detail_rows:
        _renderable_rows = list(_detail_rows)
    # [COMP_EVIDENCE_USED_FALLBACK] — single-comp valuations from the engine
    # populate `comp_evidence.used` (a list of {price, date, match_type, serial}
    # entries) but NOT trusted_detail_rows / support_detail_rows. The board
    # UI's existing readers therefore find nothing to render and the comp
    # panel stays hidden, even though the engine has a real comp on file.
    # User asked for the comp panel to render below PASS rows like it does
    # on sniper rows. Fallback: when the higher-trust paths are empty, pull
    # the engine's accepted comp evidence directly. Each entry is normalized
    # to the schema `_card_comp_render_status_html` expects (price/title/
    # match_type/sale_date) so it renders cleanly.
    if not _renderable_rows:
        _evidence_payload = (_item or {}).get("comp_evidence")
        _used_evidence: List[Dict[str, Any]] = []
        if isinstance(_evidence_payload, dict):
            _raw_used = _evidence_payload.get("used")
            if isinstance(_raw_used, list):
                for _ev in _raw_used:
                    if not isinstance(_ev, dict):
                        continue
                    try:
                        _ev_price = float(_ev.get("price") or _ev.get("sold_price") or 0.0)
                    except Exception:
                        _ev_price = 0.0
                    if _ev_price <= 0:
                        continue
                    _ev_date = str(_ev.get("date") or _ev.get("sale_date") or "").strip()
                    _ev_match = str(_ev.get("match_type") or "exact").strip().lower()
                    _ev_serial = str(_ev.get("serial") or "").strip()
                    _ev_descriptor_parts = [p for p in (_ev_match, _ev_serial) if p]
                    _used_evidence.append({
                        "price": _ev_price,
                        "sold_price": _ev_price,
                        "sale_date": _ev_date,
                        "date": _ev_date,
                        "match_type": _ev_match,
                        # `descriptor` is the key `_card_comp_descriptor()` reads
                        "descriptor": " · ".join(_ev_descriptor_parts) or "Accepted comp",
                        "kind": "accepted_comp",
                        "evidence_source": "comp_evidence_used",
                        # Provide a default grade label since AcceptedComp entries
                        # don't carry grade — descriptor will dominate the display
                        "grade_label": "raw" if _ev_match == "exact" else _ev_match,
                    })
        if _used_evidence:
            _renderable_rows = _used_evidence
            _detail_keys_present = list(_detail_keys_present) + ["comp_evidence.used"]
    _evidence_renderable = 1 if _renderable_rows else 0
    _label = str(_comp_truth.get("label") or "")
    _display_count = int(_comp_truth.get("display_count") or 0)
    if _truth_level == "REVIEW":
        if bool(_review_contract.get("anchor_only")):
            _label = ""
            _display_count = 0
            _renderable_rows = []
            _evidence_renderable = 0
        else:
            _label = "Review Evidence" if (_evidence_source == "review_payload" or _review_payload) and _evidence_renderable else "Evidence" if _evidence_renderable else ""
            _display_count = int(_review_contract.get("public_count") or len(_renderable_rows)) if _evidence_renderable else 0
    elif _truth_level == "NONE":
        _label = ""
        _display_count = 0
    if not _evidence_renderable:
        _display_count = 0
        if _truth_level in {"REVIEW", "NONE"}:
            _label = ""
    # [COMP_EVIDENCE_USED_FALLBACK] cont. — when the only evidence we have is
    # comp_evidence.used (truth_level cleared above), restamp label/count so
    # the comp panel actually renders. We use "Comp Evidence" as the header
    # to distinguish from "Comps" (high-trust) and "Review Evidence" (review
    # payload) — user reads it as "engine has these comp(s) on file".
    if _evidence_renderable and "comp_evidence.used" in _detail_keys_present and not _label:
        _label = "Comp Evidence"
        if _display_count <= 0:
            _display_count = len(_renderable_rows)
    _title = str(_item.get("title") or _item.get("source_title") or "").strip()
    print(
        f"[EVIDENCE_RENDER_CONTRACT] title={_title[:140]} truth={_truth} truth_level={_truth_level} "
        f"comp_count={int(_item.get('comp_count') or 0)} detail_rows={len(_renderable_rows)} "
        f"evidence_renderable={_evidence_renderable} reason={'review_payload' if _evidence_source == 'review_payload' and _evidence_renderable else 'renderable_detail_rows' if _evidence_renderable else 'no_renderable_evidence'}"
    )
    print(
        f"[COMP_UI_BIND] title={_title[:140]} truth={_truth} truth_level={_truth_level} true_mv={_comp_truth.get('true_mv')} "
        f"raw_exact_match_count={_comp_truth.get('raw_exact_match_count') or 0} "
        f"trusted_exact_comp_count={_comp_truth.get('trusted_exact_comp_count') or 0} "
        f"support_comp_count={_comp_truth.get('support_comp_count') or 0} label={_label or 'none'}"
    )
    return {
        "truth": _truth,
        "truth_level": _truth_level,
        "label": _label,
        "display_count": int(max(0, _display_count)),
        "detail_keys_present": list(_detail_keys_present) + (["review_evidence_payload"] if _review_payload else []),
        "detail_rows": list(_renderable_rows),
        "evidence_renderable": int(_evidence_renderable),
        "anchor_only_review": bool(_review_contract.get("anchor_only")),
        "market_evidence_count": int(_review_contract.get("public_count") or 0),
        "synthetic_internal_count": int(len(_review_contract.get("synthetic_internal_rows") or [])),
    }


def _ui_premium_secondary_contract(
    row: Dict[str, Any],
    *,
    emit_log: bool = True,
) -> Dict[str, Any]:
    _resolved_truth = _ui_consume_canonical_truth_contract(row, surface="premium_secondary", emit_log=False)
    _row = _resolved_truth.get("row") if isinstance(_resolved_truth.get("row"), dict) else (row if isinstance(row, dict) else {})
    _title = str(_row.get("title") or _row.get("source_title") or "").strip()[:140]
    _item = _ui_board_contract_item_key(_row)[:32]
    _truth = str(_resolved_truth.get("truth") or "").strip().upper() or "NONE"
    _true_mv = _safe_float(_resolved_truth.get("true_mv"))
    if _true_mv is not None and _true_mv <= 0:
        _true_mv = None
    _review_class = str(_row.get("review_truth_class") or _row.get("review_class") or "").strip().lower() or "none"
    _trusted_exact = int(_resolved_truth.get("exact_comp_count") or 0)
    _support = int(_resolved_truth.get("support_comp_count") or 0)
    _target_bid_ready = bool(_resolved_truth.get("target_bid_ready"))
    _target_bid = _safe_float(
        _row.get("target_bid")
        or _row.get("target_bid_price")
        or _row.get("bid_ceiling_value")
        or _row.get("adjusted_max_bid")
        or _row.get("max_bid")
    )
    _board_payload_rows = _ui_coerce_detail_rows(_row.get("_board_comp_payload_rows"))
    _trusted_rows = _ui_coerce_detail_rows(_row.get("trusted_detail_rows") or _row.get("exact_comps") or _row.get("raw_exact_detail_rows"))
    _support_rows = _ui_coerce_detail_rows(_row.get("support_detail_rows") or _row.get("supporting_comps"))
    _review_payload_rows = [
        dict(_entry)
        for _entry in list(_row.get("review_evidence_payload") or _row.get("renderable_evidence_rows") or [])
        if isinstance(_entry, dict) and bool(_entry.get("renderable"))
    ]
    try:
        _renderable_evidence_count = int(_row.get("renderable_evidence_count") or 0)
    except (TypeError, ValueError):
        _renderable_evidence_count = 0
    try:
        _evidence_renderable = int(_row.get("evidence_renderable") or 0)
    except (TypeError, ValueError):
        _evidence_renderable = 0
    if _board_payload_rows or _trusted_rows or _support_rows or _review_payload_rows or _renderable_evidence_count > 0:
        _evidence_renderable = max(_evidence_renderable, 1)
    _display_state = str(
        _row.get("review_display_state")
        or _row.get("display_state")
        or _row.get("review_badge_state")
        or ""
    ).strip()
    if not _display_state:
        _display_state = "NO VERIFIED COMP EVIDENCE" if (_trusted_exact <= 0 and _support <= 0 and _evidence_renderable <= 0) else "MISSING"
    _has_actionable_target = bool(_target_bid_ready and _target_bid is not None and _target_bid > 0)
    _allow = False
    _reason = "dead_review_only_no_evidence_no_bid"
    if _trusted_exact > 0:
        _allow = True
        _reason = "trusted_exact_support"
    elif _support > 0:
        _allow = True
        _reason = "support_comp_backing"
    elif _has_actionable_target:
        _allow = True
        _reason = "valid_target_bid"
    elif _evidence_renderable > 0:
        _allow = True
        _reason = "renderable_verified_evidence"
    if isinstance(_row, dict):
        _row["_premium_secondary_checked"] = True
        _row["_premium_secondary_allow"] = bool(_allow)
        _row["_premium_secondary_reason"] = str(_reason)
        _row["_premium_secondary_evidence_renderable"] = int(_evidence_renderable)
        _row["premium_secondary_allow"] = bool(_allow)
        _row["premium_secondary_reason"] = str(_reason)
    if emit_log:
        print(
            f"[PREMIUM_SECONDARY_CONTRACT] title={_title} item={_item} "
            f"truth={_truth} true_mv={round(float(_true_mv), 2) if _true_mv is not None else 'None'} "
            f"trusted_exact={_trusted_exact} support={_support} "
            f"target_bid_ready={1 if _target_bid_ready else 0} "
            f"evidence_renderable={_evidence_renderable} "
            f"display_state={_display_state or 'MISSING'} allow={1 if _allow else 0}"
        )
        if _allow:
            print(
                f"[PREMIUM_SECONDARY_ALLOW] title={_title} item={_item} "
                f"reason={_reason} trusted_exact={_trusted_exact} support={_support} "
                f"target_bid_ready={1 if _target_bid_ready else 0} "
                f"evidence_renderable={_evidence_renderable}"
            )
        else:
            print(
                f"[PREMIUM_SECONDARY_BLOCK] title={_title} item={_item} "
                f"reason=dead_review_only_no_evidence_no_bid"
            )
    return {
        "row": _row,
        "allow": bool(_allow),
        "reason": str(_reason),
        "truth": _truth,
        "true_mv": _true_mv,
        "trusted_exact": _trusted_exact,
        "support": _support,
        "target_bid_ready": bool(_target_bid_ready),
        "evidence_renderable": int(_evidence_renderable),
        "display_state": _display_state,
        "review_class": _review_class,
    }


def _ui_watchlist_append_contract(row: Dict[str, Any]) -> Dict[str, Any]:
    _premium_contract = _ui_premium_secondary_contract(row, emit_log=False)
    _resolved_truth = _ui_consume_canonical_truth_contract(row, surface="watchlist_append_sink", emit_log=False)
    _row = _premium_contract.get("row") if isinstance(_premium_contract.get("row"), dict) else (row if isinstance(row, dict) else {})
    _truth = str(_premium_contract.get("truth") or "").strip().upper() or "NONE"
    _raw_truth = str(_resolved_truth.get("truth") or "").strip().upper()
    _trusted_exact = int(_premium_contract.get("trusted_exact") or 0)
    _support = int(_premium_contract.get("support") or 0)
    _target_bid_ready = bool(_premium_contract.get("target_bid_ready"))
    _target_bid = _safe_float(
        _row.get("target_bid")
        or _row.get("target_bid_price")
        or _row.get("bid_ceiling_value")
        or _row.get("adjusted_max_bid")
        or _row.get("max_bid")
    )
    try:
        _evidence_renderable = int(_premium_contract.get("evidence_renderable") or 0)
    except (TypeError, ValueError):
        _evidence_renderable = 0
    try:
        _renderable_evidence_count = int(_row.get("renderable_evidence_count") or 0)
    except (TypeError, ValueError):
        _renderable_evidence_count = 0
    _display_state = str(_premium_contract.get("display_state") or "").strip() or "MISSING"
    _target_bid_state_present = any(
        _key in _row
        for _key in (
            "canonical_board_target_bid_ready",
            "target_bid_ready",
            "bid_ceiling_ready",
            "target_bid",
            "target_bid_price",
            "bid_ceiling_value",
            "adjusted_max_bid",
            "max_bid",
        )
    )
    _display_state_present = any(
        str(_row.get(_key) or "").strip()
        for _key in ("review_display_state", "display_state", "review_badge_state")
    )
    _evidence_state_present = any(
        _key in _row
        for _key in (
            "evidence_renderable",
            "renderable_evidence_count",
            "_board_comp_payload_rows",
            "trusted_detail_rows",
            "exact_comps",
            "raw_exact_detail_rows",
            "support_detail_rows",
            "supporting_comps",
            "review_evidence_payload",
            "renderable_evidence_rows",
        )
    )
    _has_actionable_target = bool(_target_bid_ready and _target_bid is not None and _target_bid > 0)
    _has_verified_evidence = bool(_evidence_renderable > 0 or _renderable_evidence_count > 0)
    _positive_allow_signal = bool(
        _trusted_exact > 0
        or _support > 0
        or _has_actionable_target
        or _has_verified_evidence
    )
    _missing_required_fields: List[str] = []
    if not _positive_allow_signal:
        if not _raw_truth:
            _missing_required_fields.append("truth")
        if not _target_bid_state_present:
            _missing_required_fields.append("target_bid_state")
        if not _display_state_present:
            _missing_required_fields.append("display_state")
        if not _evidence_state_present:
            _missing_required_fields.append("evidence_state")
    _dead_review_shape = bool(
        _truth in {"REVIEW", "NONE"}
        and _trusted_exact <= 0
        and _support <= 0
        and not _has_actionable_target
        and (_target_bid is None or _target_bid <= 0)
        and _display_state in {"NO VERIFIED COMP EVIDENCE", "MISSING"}
        and _evidence_renderable <= 0
        and _renderable_evidence_count <= 0
    )
    _allow = bool(_premium_contract.get("allow"))
    _reason = str(_premium_contract.get("reason") or "dead_review_only_no_evidence_no_bid").strip() or "dead_review_only_no_evidence_no_bid"
    if _missing_required_fields or _dead_review_shape:
        _allow = False
        _reason = "dead_review_only_no_evidence_no_bid"
    if isinstance(_row, dict):
        _row["_watchlist_append_checked"] = True
        _row["_watchlist_append_allow"] = bool(_allow)
        _row["_watchlist_append_reason"] = str(_reason)
        _row["_watchlist_append_dead_shape"] = bool(_dead_review_shape)
        _row["_watchlist_append_missing_fields"] = list(_missing_required_fields)
        _row["watchlist_append_allow"] = bool(_allow)
        _row["watchlist_append_reason"] = str(_reason)
    return {
        "row": _row,
        "allow": bool(_allow),
        "reason": str(_reason),
        "truth": _truth,
        "trusted_exact": _trusted_exact,
        "support": _support,
        "target_bid_ready": bool(_target_bid_ready),
        "target_bid": _target_bid,
        "display_state": _display_state,
        "evidence_renderable": int(_evidence_renderable),
        "renderable_evidence_count": int(_renderable_evidence_count),
        "dead_shape": bool(_dead_review_shape),
        "missing_required_fields": list(_missing_required_fields),
    }


def _ui_apply_true_mv_contract_guard(_row: Dict[str, Any], *, trace_tag: str = "") -> Dict[str, Any]:
    _item = _row if isinstance(_row, dict) else dict(_row or {})
    _item["_valuation_contract_version"] = str(
        _item.get("_valuation_contract_version") or _UI_TRUE_MV_CONTRACT_VERSION
    )
    _item["_valuation_source_module"] = str(_item.get("_valuation_source_module") or "unknown")
    _item["_valuation_publish_stage"] = str(
        _item.get("_valuation_publish_stage") or "valuation_engine_publish"
    )
    _item["_valuation_apply_guard"] = str(_item.get("_valuation_apply_guard") or "exact_only")
    _title = str(_item.get("source_title") or _item.get("title") or "").strip()
    _truth = str(_item.get("_valuation_truth_tier") or _item.get("valuation_truth_tier") or "").strip().upper() or "NONE"
    _source = str(
        _item.get("valuation_source_clean")
        or _item.get("market_value_source")
        or _item.get("mv_source")
        or _item.get("source")
        or "none"
    ).strip() or "none"
    _item = _ui_apply_canonical_board_contract(_item)
    _true_mv = _safe_float(_item.get("true_market_value")) or _safe_float(_item.get("market_value_true"))
    _review_estimate = _safe_float(_item.get("review_estimate_value")) or _safe_float(_item.get("anchored_estimate_value"))
    _comp_split = _ui_comp_truth_split(_item)
    _exact_comp_count = int(_comp_split["trusted_exact_comp_count"])
    _item["exact_comp_count"] = _exact_comp_count
    _item["trusted_exact_comp_count"] = _exact_comp_count
    _item["support_comp_count"] = int(_comp_split["support_comp_count"])
    _item["valuation_truth_level"] = str(_comp_split["truth_level"] or "NONE")
    _truth = str(_item.get("_valuation_truth_tier") or _item.get("valuation_truth_tier") or "").strip().upper() or "NONE"
    _item["source"] = _source
    _item["valuation_source_clean"] = _source
    if trace_tag:
        print(
            f"[{trace_tag}] title={_title[:140]} truth={_truth} source={_source} "
            f"true_mv={round(float(_true_mv), 2) if _true_mv and _true_mv > 0 else None} "
            f"review_estimate={round(float(_review_estimate), 2) if _review_estimate and _review_estimate > 0 else None} "
            f"exact_comp_count={_exact_comp_count} "
            f"valuation_contract_version={_item.get('_valuation_contract_version') or _UI_TRUE_MV_CONTRACT_VERSION}"
        )
    if bool(_item.get("_board_exact_backed_active")):
        return _item
    if _truth != "TRUE" or str(_item.get("valuation_truth_level") or "NONE") != "EXACT":
        return _item
    _reasons: List[str] = []
    if str(_source).strip().lower() != "exact_comp_engine":
        _reasons.append("source_not_exact_comp_engine")
    if _exact_comp_count < 2:
        _reasons.append("exact_comp_count_lt_2")
    if not _true_mv or _true_mv <= 0:
        _reasons.append("true_mv_missing")
    if not _reasons:
        return _item
    for _reason in _reasons:
        print(
            f"[FINAL_BOARD_TRUE_REASON] title={_title[:140]} truth={_truth} source={_source} "
            f"true_mv={round(float(_true_mv), 2) if _true_mv and _true_mv > 0 else None} "
            f"review_estimate={round(float(_review_estimate), 2) if _review_estimate and _review_estimate > 0 else None} "
            f"exact_comp_count={_exact_comp_count} reason={_reason} "
            f"valuation_contract_version={_item.get('_valuation_contract_version') or _UI_TRUE_MV_CONTRACT_VERSION}"
        )
    if _review_estimate is None or _review_estimate <= 0:
        _review_estimate = (
            _safe_float(_item.get("market_value_raw"))
            or _safe_float(_item.get("current_price"))
            or _safe_float(_item.get("current_bid"))
        )
    _review_out = round(float(_review_estimate), 2) if _review_estimate and _review_estimate > 0 else None
    _item["true_market_value"] = None
    _item["market_value_true"] = None
    _item["market_value"] = None
    _item["mv_value"] = None
    _item["mv_mid"] = None
    _item["review_estimate_value"] = _review_out
    _item["_valuation_truth_tier"] = "REVIEW" if _review_out else "NONE"
    _item["valuation_truth_tier"] = _item["_valuation_truth_tier"]
    _item["market_value_mode"] = "review_estimate" if _review_out else "none"
    _item["valuation_mode"] = _item["market_value_mode"]
    _item["mode"] = _item["market_value_mode"]
    _item["bid_mode"] = _item["market_value_mode"]
    print(
        f"[FINAL_BOARD_TRUE_BLOCK] title={_title[:140]} source={_source} "
        f"exact_comp_count={_exact_comp_count} true_mv={round(float(_true_mv), 2) if _true_mv and _true_mv > 0 else None} "
        f"review_estimate={_review_out} final_truth={_item.get('valuation_truth_tier') or 'NONE'} "
        f"valuation_contract_version={_item.get('_valuation_contract_version') or _UI_TRUE_MV_CONTRACT_VERSION}"
    )
    return _item


def _format_money(_value: Any) -> str:
    _num = _safe_float(_value)
    return f"${_num:,.2f}" if _num is not None else "—"


def _format_pct_value(_value: Any) -> str:
    _num = _safe_float(_value)
    return f"{_num:.1f}%" if _num is not None else "?"


def _ui_stamp_research_only_display(row: Dict[str, Any]) -> Dict[str, Any]:
    _row = row if isinstance(row, dict) else dict(row or {})
    if not _row.get("_research_only_price_check"):
        return _row
    _row["_presentation_bucket"] = "monitor"
    _row["_presentation_risk_block"] = True
    _row["decision_label"] = "RESEARCH ONLY"
    _row["action_label"] = "PRICE CHECK NEEDED"
    _row["target_bid"] = None
    _row["target_bid_price"] = None
    _row["target_max_bid"] = None
    _row["adjusted_max_bid"] = None
    _row["bid_ceiling_value"] = None
    _row["max_bid"] = None
    _row["buy_under"] = None
    _row["target_bid_ready"] = False
    _row["bid_ceiling_ready"] = False
    _row["target_bid_confidence"] = "NONE"
    _row["bid_ceiling_confidence"] = "NONE"
    _row["market_value"] = None
    _row["mv_value"] = None
    _row["true_market_value"] = None
    _row["market_value_true"] = None
    return _row


def _card_comp_payload_rows(_row: Dict[str, Any]) -> tuple[list[str], list[Dict[str, Any]]]:
    _detail_keys_present: List[str] = []
    _detail_rows: List[Dict[str, Any]] = []
    _candidate_fields = (
        "trusted_detail_rows",
        "support_detail_rows",
        "comps",
        "comp_rows",
        "exact_comps",
        "supporting_comps",
        "market_value_comps",
        "mv_comp_rows",
        "comp_summary",
        "comp_evidence",
    )
    for _field_name in _candidate_fields:
        _payload = (_row or {}).get(_field_name)
        if not _payload:
            continue
        if isinstance(_payload, list):
            _detail_keys_present.append(_field_name)
            for _entry in _payload:
                if isinstance(_entry, dict):
                    _detail_rows.append(dict(_entry))
        elif isinstance(_payload, dict):
            _used_rows = []
            for _nested_key in ("used", "rows", "exact", "supporting", "comps"):
                _nested_payload = _payload.get(_nested_key)
                if isinstance(_nested_payload, list) and _nested_payload:
                    _used_rows.extend(dict(_entry) for _entry in _nested_payload if isinstance(_entry, dict))
            if _used_rows:
                _detail_keys_present.append(_field_name)
                _detail_rows.extend(_used_rows)
    _seen_rows: set[str] = set()
    _deduped_rows: List[Dict[str, Any]] = []
    for _entry in _detail_rows:
        _row_key = "|".join(
            str(_entry.get(_field) or "").strip().lower()
            for _field in ("price", "sold_price", "date", "sold_date", "title", "descriptor", "serial")
        )
        if _row_key in _seen_rows:
            continue
        _seen_rows.add(_row_key)
        _deduped_rows.append(_entry)
    return _detail_keys_present, _deduped_rows


def _card_comp_descriptor(_entry: Dict[str, Any]) -> str:
    _title = str(
        _entry.get("descriptor")
        or _entry.get("title")
        or _entry.get("card_title")
        or _entry.get("summary")
        or ""
    ).strip()
    if _title:
        return _title[:72]
    _parts: List[str] = []
    for _field_name in ("year", "product", "set_name", "card_name", "parallel", "serial"):
        _value = str(_entry.get(_field_name) or "").strip()
        if _value:
            _parts.append(_value)
    return " ".join(_parts)[:72]


def _card_comp_grade_label(_entry: Dict[str, Any]) -> str:
    for _field_name in ("grade_label", "grade", "condition_label", "condition"):
        _value = str(_entry.get(_field_name) or "").strip()
        if _value:
            return _value
    _is_raw = _entry.get("is_raw")
    if isinstance(_is_raw, bool) and _is_raw:
        return "raw"
    return str(_entry.get("serial") or "").strip() or ""


def _card_comp_date_label(_entry: Dict[str, Any]) -> str:
    for _field_name in ("date", "sold_date", "sale_date", "listing_end_iso", "end_date"):
        _value = str(_entry.get(_field_name) or "").strip()
        if _value:
            return _value[:10]
    return ""


def _card_comp_evidence_html(_detail_rows: List[Dict[str, Any]]) -> str:
    _rows_html: List[str] = []
    for _entry in list(_detail_rows or [])[:3]:
        _price = _format_money(
            _entry.get("price")
            or _entry.get("sold_price")
            or _entry.get("sale_price")
            or _entry.get("amount")
            or _entry.get("value")
        )
        _grade = escape(_card_comp_grade_label(_entry) or "raw")
        _descriptor = escape(_card_comp_descriptor(_entry) or "Supporting comp")
        _date = escape(_card_comp_date_label(_entry))
        _date_html = f"<span style='color:#888888'>{_date}</span>" if _date else ""
        _rows_html.append(
            "<div style='display:flex;align-items:center;justify-content:space-between;"
            "gap:0.8rem;padding:0.48rem 0.62rem;border:1px solid #1f2a37;border-radius:9px;"
            "background:linear-gradient(180deg,#0a1119 0%,#091019 100%);'>"
            "<div style='display:flex;flex-wrap:wrap;align-items:center;gap:0.42rem;min-width:0;'>"
            f"<span style='color:#e2e8f0;font-weight:800'>{escape(_price)}</span>"
            f"<span style='color:#22c55e;font-size:0.74rem;font-weight:700;text-transform:uppercase'>{_grade}</span>"
            f"<span style='color:#b0b0b0'>·</span>"
            f"<span style='color:#fafafa;font-size:0.78rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%'>{_descriptor}</span>"
            "</div>"
            f"{_date_html}"
            "</div>"
        )
    if not _rows_html:
        return ""
    return (
        "<div style='margin-top:0.68rem;padding:0.72rem 0.78rem;border:1px solid #182230;"
        "border-radius:11px;background:#081019;'>"
        "<div style='font-size:0.66rem;font-weight:800;letter-spacing:0.14em;text-transform:uppercase;"
        "color:#888888;margin-bottom:0.52rem'>Comp Evidence</div>"
        f"<div style='display:flex;flex-direction:column;gap:0.42rem'>{''.join(_rows_html)}</div>"
        "</div>"
    )


def _card_comp_render_status_html(*, comp_count: int, detail_rows: List[Dict[str, Any]], label: str = "Comps", evidence_renderable: int = 1) -> str:
    if comp_count <= 0 or not evidence_renderable or not label:
        return ""
    _detail_ready = bool(detail_rows)
    _rows_html = ""
    if _detail_ready:
        _row_bits: List[str] = []
        for _entry in list(detail_rows or [])[:3]:
            _kind = str(_entry.get("kind") or "").strip().lower()
            _entry_label = str(_entry.get("label") or "").strip()
            _price = escape(_format_money(
                _entry.get("price")
                or _entry.get("sold_price")
                or _entry.get("sale_price")
                or _entry.get("amount")
                or _entry.get("value")
            ))
            _grade = escape(_card_comp_grade_label(_entry) or "raw")
            _descriptor = escape(_card_comp_descriptor(_entry) or "Supporting comp")
            _date = escape(_card_comp_date_label(_entry))
            _date_html = f" · {_date}" if _date else ""
            if _kind in {"review_estimate", "target_bid", "bid_anchor", "current_price"}:
                _descriptor = escape(_entry_label or _kind.replace("_", " ").title())
            _row_text = f"{_price} | {_grade} | {_descriptor}{_date_html}"
            if _kind in {"review_estimate", "target_bid", "bid_anchor", "current_price"}:
                _row_text = f"{_descriptor} | {_price}"
            _row_bits.append(
                "<div style='padding:0.38rem 0;border-top:1px solid #273142;"
                "color:#dbe4ee;font-size:0.82rem;line-height:1.35;'>"
                f"{_price} · {_grade} · {_descriptor}{_date_html}"
                "</div>"
            )
        _rows_html = "".join(_row_bits)
    else:
        return ""
    _label_clean = str(label or "").strip()
    _header = escape(_label_clean) if _label_clean.lower().endswith("evidence") else f"{escape(_label_clean)} Evidence"
    _sub = "review evidence" if _label_clean.lower().startswith("review") else "comp block rendered"
    return (
        "<div style='margin:0.48rem 0 0.72rem 0;padding:0.72rem 0.82rem;"
        "border:1px solid #666666;border-radius:10px;background:#0a1119;'>"
        f"<div style='color:#fafafa;font-size:0.82rem;font-weight:800;margin-bottom:0.3rem'>{_header}</div>"
        f"<div style='color:#22c55e;font-size:0.75rem;font-weight:700;margin-bottom:0.28rem'>{_sub}</div>"
        f"{_rows_html}"
        "</div>"
    )


def _mv_blocked_reason_label(row: Dict[str, Any]) -> str:
    """
    Return a short human-readable label explaining why MV is not displayed.
    Used in place of bare '—' so users can distinguish absence from suppression.
    """
    _br = str(row.get("mv_blocked_reason") or row.get("mv_medium_blocked_reason") or "").strip().lower()
    _src = str(row.get("market_value_source") or row.get("mv_source") or "").strip().lower()
    _conf = str(row.get("mv_confidence_strict") or row.get("mv_confidence") or "").strip().upper()
    # Source-level blocks (checked first — most specific)
    if "anchor_only_no_real_mv" in _br or _src in {"price_anchor_fallback", "price_anchor_emergency", "floor_fallback"}:
        return "No trusted MV"
    if _src == "legacy_comp_engine" or "legacy_fallback" in _br:
        return "Blocked: legacy fallback"
    if _src == "common_card_review_clamp" or "review_clamp" in _br:
        return "Blocked: review only"
    if _src in {"none", "", "error"} and not _br:
        return "Blocked: no match"
    # Reason-level blocks
    if "graded_raw_mismatch" in _br or "no_exact_grade" in _br:
        return "Blocked: grade mismatch"
    if "exact_required_fail" in _br or "common_modern_exact" in _br:
        return "Blocked: exact comps thin"
    if "parallel_no_lane" in _br:
        return "Blocked: parallel lane"
    if "generic_lane_reject" in _br or "scarcity_lane" in _br:
        return "Blocked: wrong lane"
    if "insufficient_comps" in _br or "thin" in _br:
        return "Blocked: comps too thin"
    if "high_variance" in _br:
        return "Blocked: price variance"
    if "weak_source" in _br or _src in {"fallback_comp_support", "structured_fallback", "unresolved"}:
        return "Blocked: weak comp lane"
    if "both_failed" in _br or "valuation_error" in _br:
        return "Blocked: valuation error"
    if _conf in {"LEGACY_EXCEPTION_FALLBACK"}:
        return "Blocked: legacy fallback"
    # Generic fallback label
    return "Blocked: low confidence"


def _es_valuation_source_clean(row: Dict[str, Any]) -> str:
    return str(
        (row or {}).get("mv_source")
        or (row or {}).get("market_value_source")
        or (row or {}).get("valuation_source")
        or (row or {}).get("valuation_basis")
        or ""
    ).strip().lower()


def _es_has_true_market_value(row: Dict[str, Any]) -> bool:
    _source = _es_valuation_source_clean(row)
    _comp_count = row.get("usable_comp_count")
    if _comp_count is None:
        _comp_count = row.get("comp_count")
    try:
        _comp_count = int(_comp_count or 0)
    except Exception:
        _comp_count = 0
    if _source in {"soft_watchlist_estimate", "price_anchor_fallback", "anchor_only", "review_estimate"}:
        return False
    if _source == "near_family_support" and _comp_count < 2:
        return False
    _true_mv = _safe_float((row or {}).get("true_market_value"))
    return bool(_true_mv is not None and _true_mv > 0)


def _es_resolve_review_estimate(row: Dict[str, Any]) -> Optional[float]:
    for _key in [
        "review_estimate_value",
        "anchored_estimate_value",
        "market_value",
        "market_value_true",
        "estimated_value",
        "display_value",
        "market_value_raw",
        "mv_value",
    ]:
        _value = (row or {}).get(_key)
        _num = _safe_float(_value)
        if _num is not None and _num > 0:
            return _num
    return None


def _es_looks_like_current_price_clone(row: Dict[str, Any]) -> bool:
    _cp = _safe_float((row or {}).get("current_price"))
    _mv = _safe_float((row or {}).get("true_market_value"))
    if _cp is None or _mv is None:
        return False
    return abs(_cp - _mv) < 0.01 and _es_valuation_source_clean(row) in {
        "soft_watchlist_estimate",
        "price_anchor_fallback",
        "anchor_only",
        "review_estimate",
    }


def _es_is_resolved_board_row(row: Dict[str, Any]) -> bool:
    _item = _es_strengthen_row_valuation(dict(row or {}))
    if _ui_is_live_watchlist_row(_item):
        return True
    if not bool(_item.get("board_visible", True)):
        return False
    if str(_item.get("hidden_reason") or "").strip() == "unresolved_no_trusted_mv":
        return False
    # ── Engine-pre-resolved shortcut ──────────────────────────────────────────
    # If the engine already stamped board_visible=True and execution_admission_bucket
    # as watchlist/monitor, trust that routing — don't re-gate on market_value_true.
    _eng_bucket = str(_item.get("execution_admission_bucket") or "").strip().lower()
    if bool(_item.get("board_visible")) and _eng_bucket in {"watchlist", "monitor", "sniper"}:
        return True
    _true_mv = _safe_float(_item.get("market_value_true")) or 0.0
    _source = str(_item.get("mv_source") or _item.get("market_value_source") or "").strip().lower()
    _comp_count = int((_safe_float(_item.get("mv_comp_count")) or _safe_float(_item.get("comp_count")) or 0))
    _target_bid_ready = bool(_item.get("bid_ceiling_ready") or _item.get("target_bid_ready"))
    if _true_mv <= 0 or _comp_count <= 0 or not _target_bid_ready:
        return False
    if _source == "price_anchor_fallback":
        return False
    if _source == "structured_fallback":
        _conf = str(
            _item.get("mv_confidence_strict")
            or _item.get("valuation_confidence")
            or _item.get("confidence")
            or "LOW"
        ).strip().upper()
        _chase_class = str(_item.get("chase_class") or "").strip().upper()
        if _comp_count < 2 or _conf not in {"MEDIUM", "HIGH"}:
            return False
        if _chase_class not in {"ENDGAME_CHASE", "PREMIUM_SECONDARY"}:
            return False
        if bool(_item.get("memorabilia_junk")) or bool(_item.get("veteran_non_chase")):
            return False
    return True


def _ui_is_live_watchlist_row(row: Dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    if _ui_customer_surface_blocked(row):
        return False
    if not bool(_ui_watchlist_rescue_contract(row, rescued_candidate=False, emit_log=False).get("allow")):
        return False
    if bool(row.get("_commercial_review_floor_blocked")) or str(row.get("commercial_floor_fail_reason") or "").strip():
        return False
    final_bucket = str(row.get("final_bucket") or row.get("execution_admission_bucket") or "").strip().lower()
    visibility = str(row.get("commercial_visibility") or "").strip().lower()
    route = str(row.get("visible_route") or row.get("route") or row.get("_visible_route") or "").strip().lower()
    if final_bucket in {"sniper", "snipe", "execute_now", "execute now", "monitor"}:
        return False
    if visibility in {"sniper", "snipe", "execute_now", "execute now", "monitor"}:
        return False
    board_visible = bool(row.get("board_visible"))
    commercially_visible = bool(row.get("commercially_visible"))
    return (
        commercially_visible
        and (
            final_bucket == "watchlist"
            or visibility == "watchlist"
            or route == "watchlist_visible"
            or bool(row.get("_render_live_watchlist"))
            or bool(row.get("render_live_watchlist"))
            or board_visible
        )
    )


def _ui_customer_surface_blocked(row: Dict[str, Any]) -> bool:
    try:
        if not isinstance(row, dict):
            return True
        if bool(row.get("_customer_surface_blocked")) or str(row.get("_customer_surface_reason") or "").strip() == "no_verified_edge":
            return True
        _bucket = str(row.get("final_bucket") or row.get("execution_admission_bucket") or "").strip().lower()
        _visibility = str(row.get("commercial_visibility") or row.get("visible_route") or "").strip().lower()
        if _bucket == "research" or _visibility == "hidden_research_candidate":
            return True
        _truth = str(row.get("truth") or row.get("truth_level") or row.get("valuation_truth_level") or "").strip().upper()
        _review_class = str(row.get("review_class") or row.get("review_truth_class") or "").strip().lower()
        if not _review_class and bool(row.get("anchor_only_review") or row.get("_anchor_only_review")):
            _review_class = "anchor_only_review"
        _true_mv = _safe_float(row.get("true_mv") or row.get("true_market_value") or row.get("market_value_true"))
        _trusted_exact = int(row.get("trusted_exact_comp_count") or row.get("exact_comp_count") or 0)
        _support = int(row.get("support_comp_count") or 0)
        _evidence_renderable = int(row.get("evidence_renderable") or row.get("renderable_evidence_count") or 0)
        return bool(
            _truth == "REVIEW"
            and _review_class == "anchor_only_review"
            and not (_true_mv is not None and _true_mv > 0)
            and _trusted_exact <= 0
            and _support <= 0
            and _evidence_renderable <= 0
        )
    except Exception:
        return True


def _ui_live_watchlist_row_id(row: Dict[str, Any]) -> str:
    return str((row or {}).get("source_item_id") or (row or {}).get("item_id") or (row or {}).get("row_key") or id(row))


def _is_admitted_visible_watchlist_row(_row):
    try:
        if not isinstance(_row, dict):
            return False
        if _ui_customer_surface_blocked(_row):
            return False
        _bucket = str(_row.get("execution_admission_bucket") or _row.get("commercial_visibility") or _row.get("_final_bucket") or _row.get("final_bucket") or "").strip().lower()
        _board_visible = bool(_row.get("board_visible"))
        _commercially_visible = bool(_row.get("commercially_visible"))
        _has_target_bid = _row.get("target_bid") is not None
        return (
            _board_visible
            and _commercially_visible
            and _has_target_bid
            and _bucket == "watchlist"
        )
    except Exception:
        return False


def _ui_watchlist_rescue_contract(
    row: Dict[str, Any],
    *,
    rescued_candidate: bool = True,
    emit_log: bool = True,
) -> Dict[str, Any]:
    _resolved_truth = _ui_consume_canonical_truth_contract(row, surface="watchlist_rescue", emit_log=emit_log)
    _row = _resolved_truth.get("row") if isinstance(_resolved_truth.get("row"), dict) else (row if isinstance(row, dict) else {})
    _premium_secondary = _ui_premium_secondary_contract(_row, emit_log=emit_log)
    _title = str(_row.get("title") or _row.get("source_title") or "").strip()[:140]
    _item = _ui_board_contract_item_key(_row)[:32]
    _truth = str(_resolved_truth.get("truth") or "").strip().upper()
    _anchor_only_flag = bool(_row.get("anchor_only_review") or _row.get("_anchor_only_review"))
    _review_class = str(_row.get("review_truth_class") or _row.get("review_class") or "").strip().lower()
    if not _review_class and _anchor_only_flag:
        _review_class = "anchor_only_review"
    _true_mv = _safe_float(_resolved_truth.get("true_mv"))
    _trusted_exact = int(_resolved_truth.get("exact_comp_count") or 0)
    _support = int(_resolved_truth.get("support_comp_count") or 0)
    _display_state = str(_row.get("review_display_state") or _row.get("display_state") or "").strip()
    if not _display_state and _anchor_only_flag:
        _display_state = "NO VERIFIED COMP EVIDENCE"
    _commercially_visible_present = "commercially_visible" in _row
    _commercially_visible = bool(_row.get("commercially_visible")) if _commercially_visible_present else False
    _target_bid_state_present = any(
        _key in _row
        for _key in ("target_bid_ready", "bid_ceiling_ready", "target_bid", "target_bid_price", "bid_ceiling_value")
    )
    _target_bid_ready = bool(_resolved_truth.get("target_bid_ready"))
    _target_bid = _safe_float(_row.get("target_bid") or _row.get("target_bid_price") or _row.get("bid_ceiling_value"))
    _target_bid_actionable = bool(_target_bid_ready and _target_bid is not None and _target_bid > 0)
    _commercial_floor_decision = dict(_row.get("_commercial_review_floor_decision") or {})
    _commercial_review_keep_raw = _row.get("commercial_review_floor_keep")
    if _commercial_review_keep_raw is None:
        _commercial_review_keep_raw = _row.get("_commercial_review_floor_keep")
    if _commercial_review_keep_raw is None and _commercial_floor_decision:
        _commercial_review_keep_raw = 1 if bool(_commercial_floor_decision.get("keep")) else 0
    _commercial_floor_blocked = bool(_row.get("_commercial_review_floor_blocked")) or bool(str(_row.get("commercial_floor_fail_reason") or "").strip())
    _commercial_review_keep = 1 if _commercial_review_keep_raw is None else (1 if (_safe_float(_commercial_review_keep_raw) or 0.0) > 0 else 0)
    if _commercial_floor_blocked:
        _commercial_review_keep = 0
    _final_review_keep_raw = _row.get("final_review_gate_keep")
    if _final_review_keep_raw is None:
        _final_review_keep_raw = _row.get("_final_review_gate_keep")
    if _final_review_keep_raw is None:
        _final_review_keep_raw = _row.get("final_surface_allowed")
    _final_review_keep_present = _final_review_keep_raw is not None
    if rescued_candidate and not _final_review_keep_present:
        _final_review_keep = 0
    else:
        _final_review_keep = 1 if _final_review_keep_raw is None else (1 if (_safe_float(_final_review_keep_raw) or 0.0) > 0 else 0)
    _commercial_gate_suppressed = bool(
        _row.get("commercially_suppressed")
        or _row.get("_commercial_blocked")
        or _row.get("commodity_suppressed")
    )
    _execution_final = str(_resolved_truth.get("execution_final") or "").strip().upper()
    _execution_reason = str(
        _row.get("decision_reason")
        or _row.get("_execution_contract_reason")
        or _row.get("premium_review_reason")
        or _row.get("review_failure_reason")
        or _row.get("final_surface_reason")
        or _row.get("commercial_floor_fail_reason")
        or ""
    ).strip().lower()
    _missing_required_fields: List[str] = []
    if not _truth:
        _missing_required_fields.append("truth")
    if not _review_class:
        _missing_required_fields.append("review_class")
    if not _display_state:
        _missing_required_fields.append("display_state")
    if not _target_bid_state_present:
        _missing_required_fields.append("target_bid_state")
    if not _commercially_visible_present:
        _missing_required_fields.append("commercially_visible")
    if not _final_review_keep_present:
        _missing_required_fields.append("final_review_keep")
    _domestic_ineligible = "domestic_eligible" in _row and not bool(_row.get("domestic_eligible"))
    _explicit_price_block = bool(_execution_final == "PASS" and "price_above_bid" in _execution_reason)
    _canonical_immune = bool(_resolved_truth.get("immune"))
    _dead_anchor_only_shape = bool(
        _truth == "REVIEW"
        and _review_class == "anchor_only_review"
        and not (_true_mv is not None and _true_mv > 0)
        and _trusted_exact <= 0
        and _support <= 0
        and not _target_bid_actionable
        and _display_state == "NO VERIFIED COMP EVIDENCE"
        and (not _commercially_visible or _commercial_gate_suppressed or _final_review_keep <= 0)
    )
    _reason = ""
    if _domestic_ineligible:
        _reason = "domestic_ineligible"
    elif _explicit_price_block:
        _reason = "price_above_bid"
    elif _ui_customer_surface_blocked(_row):
        _reason = "no_verified_edge"
    elif _canonical_immune:
        _reason = ""
    elif not bool(_premium_secondary.get("allow")):
        _reason = str(_premium_secondary.get("reason") or "dead_review_only_no_evidence_no_bid")
    elif rescued_candidate and _missing_required_fields:
        _reason = "missing_canonical_rescue_state"
    elif _dead_anchor_only_shape:
        _reason = "dead_anchor_only_review_shape"
    elif _final_review_keep <= 0:
        _reason = "final_review_gate_keep"
    elif _commercial_review_keep <= 0:
        _reason = "commercial_review_floor_keep"
    elif not _commercially_visible:
        _reason = "commercially_visible_false"
    elif _commercial_gate_suppressed:
        _reason = "commercial_gate_suppressed"
    elif _execution_final == "PASS" and _execution_reason == "anchor_only_review":
        _reason = "execution_pass_anchor_only_review"
    elif (
        _review_class == "anchor_only_review"
        and not (_true_mv is not None and _true_mv > 0)
        and _trusted_exact <= 0
        and _support <= 0
    ):
        _reason = "anchor_only_review_no_comp_support"
    _admitted_watchlist_override = bool(
        _reason == "anchor_only_review_no_comp_support"
        and _is_admitted_visible_watchlist_row(_row)
    )
    if _admitted_watchlist_override:
        print(
            f"[RENDER_CONTRACT_OVERRIDE] title={str((_row or {}).get('title') or (_row or {}).get('raw_title') or '')[:140]} "
            f"reason=admitted_visible_watchlist_preserved"
        )
        print(
            f"[RENDER_VISIBLE_ASSERT] title={_title} "
            f"board_visible={_row.get('board_visible')} "
            f"commercially_visible={_row.get('commercially_visible')} "
            f"bucket={_row.get('execution_admission_bucket') or _row.get('commercial_visibility') or _row.get('_final_bucket') or _row.get('final_bucket')} "
            f"target_bid={_row.get('target_bid')}"
        )
        _reason = ""
        _row["_render_live_watchlist"] = True
        _row["render_live_watchlist"] = True
        _row["_fallback_displayable"] = True
        _row["_watchlist_rescue_blocked"] = False
        _row["_watchlist_rescue_block_reason"] = ""
    _allow = not bool(_reason)
    _suppressed = bool(
        False if (_canonical_immune or _admitted_watchlist_override) else bool(
            _domestic_ineligible
            or _explicit_price_block
            or _ui_customer_surface_blocked(_row)
            or not bool(_premium_secondary.get("allow"))
            or (rescued_candidate and bool(_missing_required_fields))
            or _dead_anchor_only_shape
            or _final_review_keep <= 0
            or _commercial_review_keep <= 0
            or not _commercially_visible
            or _commercial_gate_suppressed
            or (_execution_final == "PASS" and _execution_reason == "anchor_only_review")
            or (
                _review_class == "anchor_only_review"
                and not (_true_mv is not None and _true_mv > 0)
                and _trusted_exact <= 0
                and _support <= 0
            )
        )
    )
    if not _allow and isinstance(_row, dict):
        _row["_watchlist_rescue_blocked"] = True
        _row["_watchlist_rescue_block_reason"] = _reason
        _row["_render_live_watchlist"] = False
        _row["render_live_watchlist"] = False
        _row["_fallback_displayable"] = False
        _row["_watchlist_rescue_dead_shape"] = bool(_dead_anchor_only_shape)
        if _reason == "no_verified_edge":
            _row["_customer_surface_blocked"] = True
            _row["_customer_surface_reason"] = "no_verified_edge"
            _row["commercial_visibility"] = "hidden_research_candidate"
            _row["visible_route"] = "hidden_research_candidate"
            _row["final_bucket"] = "research"
            _row["execution_admission_bucket"] = "research"
    if emit_log:
        print(
            f"[WATCHLIST_RESCUE_DEAD_SHAPE] title={_title} item={_item} "
            f"truth={_truth or 'MISSING'} review_class={_review_class or 'missing'} "
            f"true_mv={round(float(_true_mv), 2) if _true_mv is not None else 'None'} "
            f"trusted_exact={_trusted_exact} support={_support} "
            f"target_bid_ready={1 if _target_bid_ready else 0} "
            f"display_state={_display_state or 'MISSING'} allow={1 if _allow else 0}"
        )
        if _dead_anchor_only_shape:
            print(
                f"[WATCHLIST_RESCUE_DEAD_BLOCK] title={_title} item={_item} "
                f"reason=dead_anchor_only_review_shape"
            )
        print(
            f"[WATCHLIST_RESCUE_CONTRACT] title={_title} item={_item} "
            f"rescued_candidate={1 if rescued_candidate else 0} "
            f"commercially_visible={1 if _commercially_visible else 0} "
            f"suppressed={1 if _suppressed else 0} "
            f"final_review_keep={_final_review_keep} "
            f"review_class={_review_class or 'none'} allow={1 if _allow else 0}"
        )
        if not _allow:
            print(
                f"[WATCHLIST_RESCUE_BLOCK] title={_title} item={_item} "
                f"reason={_reason} rescued_candidate={1 if rescued_candidate else 0}"
            )
            print(
                f"[WATCHLIST_RESCUE_LEAK_GUARD] title={_title} item={_item} "
                f"blocked=1 reason=suppressed_row_cannot_be_rescued"
            )
    return {
        "allow": bool(_allow),
        "reason": _reason,
        "commercially_visible": _commercially_visible,
        "suppressed": _suppressed,
        "final_review_keep": _final_review_keep,
        "review_class": _review_class,
        "truth": _truth,
        "trusted_exact": _trusted_exact,
        "support": _support,
        "display_state": _display_state,
        "target_bid_ready": _target_bid_ready,
    }


def _ui_remainder_surface_contract(
    row: Dict[str, Any],
    *,
    emit_log: bool = True,
) -> Dict[str, Any]:
    _resolved_truth = _ui_consume_canonical_truth_contract(row, surface="remainder", emit_log=emit_log)
    _row = _resolved_truth.get("row") if isinstance(_resolved_truth.get("row"), dict) else (row if isinstance(row, dict) else {})
    _title = str(_row.get("title") or _row.get("source_title") or "").strip()[:140]
    _item = _ui_board_contract_item_key(_row)[:32]
    _review_class = str(_row.get("review_truth_class") or _row.get("review_class") or "").strip().lower()
    _true_mv = _safe_float(_resolved_truth.get("true_mv"))
    _trusted_exact = int(_resolved_truth.get("exact_comp_count") or 0)
    _support = int(_resolved_truth.get("support_comp_count") or 0)
    _commercially_visible = bool(_row.get("commercially_visible"))
    _commercial_floor_decision = dict(_row.get("_commercial_review_floor_decision") or {})
    _commercial_review_keep_raw = _row.get("commercial_review_floor_keep")
    if _commercial_review_keep_raw is None:
        _commercial_review_keep_raw = _row.get("_commercial_review_floor_keep")
    if _commercial_review_keep_raw is None and _commercial_floor_decision:
        _commercial_review_keep_raw = 1 if bool(_commercial_floor_decision.get("keep")) else 0
    _commercial_floor_blocked = bool(_row.get("_commercial_review_floor_blocked")) or bool(str(_row.get("commercial_floor_fail_reason") or "").strip())
    _commercial_review_keep = 1 if _commercial_review_keep_raw is None else (1 if (_safe_float(_commercial_review_keep_raw) or 0.0) > 0 else 0)
    if _commercial_floor_blocked:
        _commercial_review_keep = 0
    _final_review_keep_raw = _row.get("final_review_gate_keep")
    if _final_review_keep_raw is None:
        _final_review_keep_raw = _row.get("_final_review_gate_keep")
    if _final_review_keep_raw is None:
        _final_review_keep_raw = _row.get("final_surface_allowed")
    _final_review_keep = 1 if _final_review_keep_raw is None else (1 if (_safe_float(_final_review_keep_raw) or 0.0) > 0 else 0)
    _commercial_gate_suppressed = bool(
        _row.get("commercially_suppressed")
        or _row.get("_commercial_blocked")
        or _row.get("commodity_suppressed")
    )
    _execution_final = str(
        _resolved_truth.get("execution_final")
        or ""
    ).strip().upper()
    _execution_reason = str(
        _row.get("decision_reason")
        or _row.get("_execution_contract_reason")
        or _row.get("premium_review_reason")
        or _row.get("review_failure_reason")
        or _row.get("final_surface_reason")
        or _row.get("commercial_floor_fail_reason")
        or ""
    ).strip().lower()
    _anchor_only_dead = bool(
        str(_resolved_truth.get("truth") or "").strip().upper() == "REVIEW"
        and _review_class == "anchor_only_review"
        and not (_true_mv is not None and _true_mv > 0)
        and _trusted_exact <= 0
        and _support <= 0
    )
    _domestic_ineligible = "domestic_eligible" in _row and not bool(_row.get("domestic_eligible"))
    _explicit_price_block = bool(_execution_final == "PASS" and "price_above_bid" in _execution_reason)
    _canonical_immune = bool(_resolved_truth.get("immune"))
    _reason = ""
    if _domestic_ineligible:
        _reason = "domestic_ineligible"
    elif _explicit_price_block:
        _reason = "price_above_bid"
    elif _canonical_immune:
        _reason = ""
    elif _commercial_gate_suppressed:
        _reason = "commercial_gate_suppressed"
    elif not _commercially_visible:
        _reason = "commercially_visible_false"
    elif _commercial_review_keep <= 0:
        _reason = "commercial_review_floor_keep"
    elif _final_review_keep <= 0 and _review_class == "anchor_only_review":
        _reason = "final_review_gate_keep"
    elif _execution_final == "PASS" and _execution_reason == "anchor_only_review":
        _reason = "execution_pass_anchor_only_review"
    elif _anchor_only_dead:
        _reason = "anchor_only_review_no_comp_support"
    _admitted_watchlist_override = bool(
        _reason == "anchor_only_review_no_comp_support"
        and _is_admitted_visible_watchlist_row(_row)
    )
    if _admitted_watchlist_override:
        print(
            f"[RENDER_CONTRACT_OVERRIDE] title={str((_row or {}).get('title') or (_row or {}).get('raw_title') or '')[:140]} "
            f"reason=admitted_visible_watchlist_preserved"
        )
        print(
            f"[RENDER_VISIBLE_ASSERT] title={_title} "
            f"board_visible={_row.get('board_visible')} "
            f"commercially_visible={_row.get('commercially_visible')} "
            f"bucket={_row.get('execution_admission_bucket') or _row.get('commercial_visibility') or _row.get('_final_bucket') or _row.get('final_bucket')} "
            f"target_bid={_row.get('target_bid')}"
        )
        _reason = ""
        _row["_render_live_watchlist"] = True
        _row["render_live_watchlist"] = True
        _row["_remainder_surface_blocked"] = False
        _row["_remainder_surface_block_reason"] = ""
    _allow = not bool(_reason)
    _suppressed = bool(
        False if (_canonical_immune or _admitted_watchlist_override) else bool(
            _domestic_ineligible
            or _explicit_price_block
            or _commercial_gate_suppressed
            or not _commercially_visible
            or _commercial_review_keep <= 0
            or (_final_review_keep <= 0 and _review_class == "anchor_only_review")
            or (_execution_final == "PASS" and _execution_reason == "anchor_only_review")
            or _anchor_only_dead
        )
    )
    if not _allow and isinstance(_row, dict):
        _row["_remainder_surface_blocked"] = True
        _row["_remainder_surface_block_reason"] = _reason
    if emit_log:
        print(
            f"[REMAINDER_SURFACE_CONTRACT] title={_title} item={_item} "
            f"commercially_visible={1 if _commercially_visible else 0} "
            f"suppressed={1 if _suppressed else 0} "
            f"review_class={_review_class or 'none'} "
            f"final_review_keep={_final_review_keep} allow={1 if _allow else 0}"
        )
        if not _allow:
            print(
                f"[REMAINDER_SURFACE_BLOCK] title={_title} item={_item} "
                f"reason={_reason} suppressed={1 if _suppressed else 0} "
                f"review_class={_review_class or 'none'}"
            )
            print(
                f"[REMAINDER_SURFACE_LEAK_GUARD] title={_title} item={_item} "
                f"blocked=1 reason=suppressed_anchor_only_row_cannot_render_remainder"
            )
    return {
        "allow": bool(_allow),
        "reason": _reason,
        "commercially_visible": _commercially_visible,
        "suppressed": _suppressed,
        "review_class": _review_class,
        "final_review_keep": _final_review_keep,
    }


def _ui_resolve_final_surface_route(
    row: Dict[str, Any],
    *,
    emit_log: bool = True,
) -> Dict[str, Any]:
    _resolved_truth = _ui_consume_canonical_truth_contract(row, surface="final_route", emit_log=False)
    _row = _resolved_truth.get("row") if isinstance(_resolved_truth.get("row"), dict) else (row if isinstance(row, dict) else {})
    _title = str(_row.get("title") or _row.get("source_title") or "").strip()[:140]
    _item = _ui_board_contract_item_key(_row)[:32]
    _board_visible = bool(_row.get("board_visible"))
    _canonical_preserved = bool(_row.get("canonical_board_preserved"))
    _canonical_truth = str(
        _row.get("canonical_board_truth")
        or _resolved_truth.get("truth")
        or _row.get("valuation_truth_tier")
        or _row.get("_valuation_truth_tier")
        or "NONE"
    ).strip().upper() or "NONE"
    _final_bucket = str(_row.get("final_bucket") or "").strip().lower()
    _execution_bucket = str(_row.get("execution_admission_bucket") or "").strip().lower()
    _commercial_visibility = str(_row.get("commercial_visibility") or "").strip().lower()
    _visible_route = str(
        _row.get("visible_route")
        or _row.get("route")
        or _row.get("_visible_route")
        or ""
    ).strip().lower()
    _watchlist_visible_blocked = bool(_row.get("_watchlist_visible_blocked"))
    _watchlist_contract = _ui_watchlist_rescue_contract(_row, rescued_candidate=False, emit_log=False)
    _remainder_contract = _ui_remainder_surface_contract(_row, emit_log=False)
    _force_bucket = str(
        _row.get("final_bucket")
        or _row.get("_final_bucket")
        or _row.get("execution_admission_bucket")
        or ""
    ).strip().lower()
    _force_render = bool(
        _board_visible
        and bool(_row.get("commercially_visible"))
        and (
            _force_bucket in {"watchlist", "prepare", "monitor", "sniper"}
            or bool(_row.get("_render_live_watchlist"))
            or bool(_row.get("render_live_watchlist"))
            or bool(_row.get("review_force_promoted"))
        )
    )
    _watch_reason = str(_watchlist_contract.get("reason") or "").strip()
    _remainder_reason = str(_remainder_contract.get("reason") or "").strip()
    _hard_block_reasons = {
        "domestic_ineligible",
        "price_above_bid",
        "commercial_gate_suppressed",
        "dead_anchor_only_review_shape",
        "execution_pass_anchor_only_review",
        "anchor_only_review_no_comp_support",
        "missing_canonical_rescue_state",
        "no_verified_edge",
    }
    _hard_block_reason = ""
    for _candidate_reason in (_watch_reason, _remainder_reason):
        if _candidate_reason in _hard_block_reasons:
            _hard_block_reason = _candidate_reason
            break
    if _ui_customer_surface_blocked(_row):
        _hard_block_reason = "no_verified_edge"
    _sniper_hints = {"sniper", "snipe", "execute_now", "execute now"}
    _watchlist_hints = {"watchlist", "monitor"}
    _explicit_sniper = bool(
        (_board_visible or _canonical_preserved)
        and (
            _final_bucket in _sniper_hints
            or _execution_bucket in _sniper_hints
            or _commercial_visibility in _sniper_hints
            or _visible_route in {"sniper_visible", "sniper_board", "sniper"}
        )
    )
    _watchlist_preferred = bool(
        _final_bucket in _watchlist_hints
        or _execution_bucket in _watchlist_hints
        or _commercial_visibility in _watchlist_hints
        or _visible_route == "watchlist_visible"
    )
    _board_route_candidate = bool(_board_visible or _canonical_preserved)
    _route = ""
    _reason = ""
    _blocked = False
    if _force_render and not _hard_block_reason:
        _route = "sniper" if _force_bucket == "sniper" else "watchlist"
        _reason = "forced_visible_board_contract"
    elif _explicit_sniper and not _hard_block_reason:
        _route = "sniper"
        _reason = "sniper_eligible"
    elif bool(_watchlist_contract.get("allow")) and not _watchlist_visible_blocked:
        _route = "watchlist"
        _reason = "commercially_eligible"
    elif _watchlist_visible_blocked and (
        bool(_remainder_contract.get("allow"))
        or (_board_route_candidate and not _hard_block_reason)
    ):
        _route = "remainder"
        _reason = "watchlist_visible_quality_gate"
    elif bool(_remainder_contract.get("allow")):
        _route = "remainder"
        _reason = "commercially_eligible_near_miss"
    elif _board_route_candidate and not _hard_block_reason:
        if _watchlist_preferred and not _watchlist_visible_blocked:
            _route = "watchlist"
            _reason = "board_visible_route_recovery"
        else:
            _route = "remainder"
            _reason = "board_visible_route_recovery"
    elif _hard_block_reason:
        _route = "blocked"
        _reason = _hard_block_reason
        _blocked = True
    else:
        if emit_log and _board_visible:
            print(
                f"[FINAL_SURFACE_LIMBO] title={_title} item={_item} "
                f"board_visible=1 sniper=0 watchlist=0 remainder=0 blocked=0"
            )
        _route = "blocked"
        _reason = _watch_reason or _remainder_reason or "no_final_surface_route"
        _blocked = True
    _row["_final_surface_route"] = _route
    _row["final_surface_route"] = _route
    _row["_final_surface_reason"] = _reason
    _row["final_surface_reason"] = _reason
    _row["_route_blocked_hard"] = bool(_blocked)
    _row["route_blocked_hard"] = bool(_blocked)
    if _route == "watchlist":
        _row["final_bucket"] = "watchlist"
        _row["execution_admission_bucket"] = "watchlist"
        _row["commercial_visibility"] = "watchlist"
        _row["visible_route"] = "watchlist_visible"
        _row["commercially_visible"] = True
        _row["board_visible"] = True
        _row["_render_live_watchlist"] = True
        _row["render_live_watchlist"] = True
    elif _route == "sniper":
        _row["final_bucket"] = "sniper"
        _row["execution_admission_bucket"] = "sniper"
        _row["commercial_visibility"] = "sniper"
        _row["visible_route"] = "sniper_visible"
        _row["commercially_visible"] = True
        _row["board_visible"] = True
    elif _route == "remainder":
        _row["visible_route"] = str(_row.get("visible_route") or "remainder_visible")
        _row["board_visible"] = bool(_row.get("board_visible") or _board_route_candidate)
    if emit_log:
        print(
            f"[FINAL_SURFACE_ROUTE] title={_title} item={_item} "
            f"board_visible={1 if _board_visible else 0} "
            f"canonical_truth={_canonical_truth or 'NONE'} "
            f"route={_route} reason={_reason or 'none'}"
        )
    return {
        "row": _row,
        "route": _route,
        "reason": _reason,
        "blocked": bool(_blocked),
        "board_visible": _board_visible,
        "canonical_truth": _canonical_truth,
    }


def _ui_is_engine_visible_watchlist_candidate(row: Dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    if not bool(_ui_watchlist_rescue_contract(row, rescued_candidate=False, emit_log=False).get("allow")):
        return False
    _final_bucket = str(row.get("final_bucket") or row.get("execution_admission_bucket") or "").strip().lower()
    _execution_bucket = str(row.get("execution_admission_bucket") or "").strip().lower()
    _commercial_visibility = str(row.get("commercial_visibility") or "").strip().lower()
    _displayable = bool(
        row.get("displayable")
        or row.get("_fallback_displayable")
        or row.get("_fallback_candidate_admit")
    )
    return bool(
        bool(row.get("_render_live_watchlist"))
        or bool(row.get("render_live_watchlist"))
        or _final_bucket == "watchlist"
        or _execution_bucket == "watchlist"
        or _commercial_visibility == "watchlist"
        or bool(row.get("board_visible"))
        or bool(row.get("commercially_visible"))
        or _displayable
    )


def _ui_engine_visible_watchlist_priority(row: Dict[str, Any]) -> Tuple[int, int, int, int, str]:
    _final_bucket = str((row or {}).get("final_bucket") or (row or {}).get("execution_admission_bucket") or "").strip().lower()
    _execution_bucket = str((row or {}).get("execution_admission_bucket") or "").strip().lower()
    _commercial_visibility = str((row or {}).get("commercial_visibility") or "").strip().lower()
    _render_live_watchlist = bool((row or {}).get("_render_live_watchlist") or (row or {}).get("render_live_watchlist"))
    _board_visible = bool((row or {}).get("board_visible"))
    _commercially_visible = bool((row or {}).get("commercially_visible"))
    _fallback_displayable = bool((row or {}).get("displayable") or (row or {}).get("_fallback_displayable") or (row or {}).get("_fallback_candidate_admit"))
    return (
        0 if _render_live_watchlist else 1,
        0 if (_final_bucket == "watchlist" or _execution_bucket == "watchlist" or _commercial_visibility == "watchlist") else 1,
        0 if (_board_visible and _commercially_visible) else 1,
        0 if _fallback_displayable else 1,
        _ui_live_watchlist_row_id(row),
    )


def _log_watchlist_handoff_drop(row: Dict[str, Any], *, dropped_by: str) -> None:
    _item = dict(row or {})
    print(
        f"[WATCHLIST_HANDOFF_DROP] title={str(_item.get('title') or _item.get('source_title') or '')[:140]} "
        f"item={_ui_live_watchlist_row_id(_item)[:32]} "
        f"board_visible={1 if bool(_item.get('board_visible')) else 0} "
        f"render_live_watchlist={1 if bool(_item.get('_render_live_watchlist') or _item.get('render_live_watchlist')) else 0} "
        f"commercially_visible={1 if bool(_item.get('commercially_visible')) else 0} "
        f"final_bucket={str(_item.get('final_bucket') or _item.get('execution_admission_bucket') or '')[:24]} "
        f"dropped_by={dropped_by}"
    )


def _watchlist_visible_qualified(r: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Returns (passes: bool, reason: str).

    A row is BLOCKED from the primary visible watchlist slot when ALL of:
      - truth is not TRUE
      - true_mv is absent / zero
      - mv_source is a fallback type (price_anchor_fallback, structured_fallback, or "fallback" in name)
      - comp_count < 2  OR  confidence is LOW / NONE
      - title has ambiguity markers (?? or trailing ?)

    Rows that are blocked remain in the hidden watch/review pool (suppressed expander).
    Fast-pass overrides prevent premium rows with confirmed data from being blocked.
    """
    _truth      = str(r.get("mv_truth") or r.get("truth") or "").strip().upper()
    _true_mv    = _safe_float(r.get("true_market_value") or r.get("market_value_true")) or 0.0
    _source     = str(r.get("mv_source") or r.get("market_value_source") or "").strip().lower()
    _comp_count = int(_safe_float(r.get("comp_count") or r.get("mv_comp_count")) or 0)
    _confidence = str(
        r.get("mv_confidence_strict") or r.get("valuation_confidence") or r.get("confidence") or ""
    ).strip().upper()
    _title      = str(r.get("title") or r.get("source_title") or "").lower()
    if _ui_is_live_watchlist_row(r):
        return True, "live_watchlist_contract"
    if int(r.get("final_surface_allowed") or 0) <= 0:
        return False, str(r.get("final_surface_reason") or "no_renderable_evidence")

    # Fast-pass: confirmed truth or present true MV → always visible
    if _truth == "TRUE" or _true_mv > 0:
        return True, "truth_confirmed_or_true_mv_present"

    # Fast-pass: 2+ comps + HIGH or MEDIUM confidence → sufficient data conviction
    if _comp_count >= 2 and _confidence in {"HIGH", "MEDIUM"}:
        return True, f"strong_comps_and_confidence comps={_comp_count} conf={_confidence}"

    # Fast-pass: premium auto/serial with clean title + non-low confidence
    _has_auto   = any(_t in _title for _t in ("auto", "patch", "rpa"))
    _has_serial = any(_t in _title for _t in ("/1 ", "/5 ", "/10 ", "/25 ", "/49 "))
    _title_clean = "??" not in _title and not _title.strip().endswith("?")
    if (_has_auto or _has_serial) and _title_clean and _confidence not in {"LOW", "NONE", ""}:
        return True, f"premium_signal_clean_title signal={'auto' if _has_auto else 'serial'}"

    # ── Block gate — all weak conditions simultaneously ───────────────────────
    _weak_source = (
        _source in {"price_anchor_fallback", "structured_fallback"}
        or "fallback" in _source
    )
    _weak_comps  = _comp_count < 2
    _weak_conf   = _confidence in {"LOW", "NONE", ""}
    _ambig_title = "??" in _title or _title.strip().endswith("?")

    if _weak_source and (_weak_comps or _weak_conf) and _ambig_title:
        return False, (
            f"all_weak: truth={_truth} true_mv={_true_mv:.2f} "
            f"source={_source} comps={_comp_count} conf={_confidence} ambiguous_title=True"
        )

    # Secondary block: no truth, no true_mv, fallback source, thin comps — even without ambiguous title
    if _truth not in {"TRUE"} and _true_mv == 0.0 and _weak_source and _weak_comps:
        return False, (
            f"no_truth_no_mv_fallback_thin_comps: source={_source} comps={_comp_count} conf={_confidence}"
        )

    return True, "passed_visible_quality_gate"


_BOARD_MIN_POPULATION = 8
_FALLBACK_PREPARE_EDGE_PCT = 18.0
_FALLBACK_PREPARE_EDGE_DOLLARS = 20.0
_FALLBACK_MONITOR_EDGE_PCT = 8.0
_FALLBACK_MONITOR_EDGE_DOLLARS = 8.0
_FALLBACK_PREMIUM_PREPARE_EDGE_PCT = 14.0
_FALLBACK_PREMIUM_PREPARE_EDGE_DOLLARS = 14.0
_FALLBACK_PREMIUM_MONITOR_EDGE_PCT = 5.0
_FALLBACK_PREMIUM_MONITOR_EDGE_DOLLARS = 5.0
_FALLBACK_REVIEW_MAX_BOARD_SECONDS = 86400.0


def _es_review_confidence_tier(row: Dict[str, Any]) -> str:
    _raw = str(
        (row or {}).get("valuation_confidence")
        or (row or {}).get("confidence")
        or (row or {}).get("mv_confidence")
        or ""
    ).strip().lower()
    if _raw in {"high", "resolved", "strong"}:
        return "high"
    if _raw in {"medium", "med", "usable", "review"}:
        return "medium"
    if _raw in {"low", "estimate_only", "manual_context", "unknown", "excluded"}:
        return "low"
    return "unknown"


def _es_board_execution_decision(bucket: str) -> str:
    _bucket = str(bucket or "").strip().upper()
    if _bucket == "PREPARE":
        return "PREPARE"
    if _bucket == "MONITOR":
        return "MONITOR"
    if _bucket == "SNIPER":
        return "SNIPE"
    return "WATCH"


def _es_compute_final_execution_action(_row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Final action layer — runs AFTER valuation. Reads only the prices and the
    research/bucket flags already stamped by the upstream layers. Maps to one
    of six unambiguous labels:

      Verified path (target_bid is a real engine target):
        SNIPE_NOW         current_price <= target_bid
        WATCH             current_price <= target_bid * 1.05
        PASS_OVERPRICED   current_price >  target_bid * 1.05

      Research path (rare_research_pricing or research_bid_ready):
        RESEARCH_SNIPE    current_price <= research_value_low (or exploratory_max_bid)
        RESEARCH_WATCH    current_price <= research_value_high
        RESEARCH_PASS     current_price >  research_value_high

    Does not modify valuation, comp, pricing, identity, or discovery layers.
    """
    _r = _row or {}
    # Price authority (delegates to existing helper — no new pricing logic).
    _cp = _ui_authoritative_current_price(_r) if _r else None
    if _cp is None or float(_cp) <= 0:
        return {
            "final_execution_decision": str(_r.get("execution_decision") or "PASS").strip().upper() or "PASS",
            "final_action_label": "AWAITING PRICE",
            "final_cta_text": "Awaiting current price",
            "final_badge_text": "AWAITING PRICE",
            "final_action_reason": "no_current_price",
            "final_edge_dollars": None,
            "final_edge_pct": None,
            "final_action_path": "none",
        }
    _research_path = bool(
        _r.get("_rare_research_pricing")
        or _r.get("rare_research_pricing")
        or _r.get("_research_bid_ready")
        or _r.get("research_bid_ready")
    )
    if _research_path:
        # Research lane uses research_value_low/high + exploratory_max_bid
        # (or, for research_bid_ready rows from earlier turn, research_bid_value
        # plus a 0.70 reference). Choose the most conservative SNIPE threshold
        # available so research labels never overpromise.
        _rl = _safe_float(_r.get("research_value_low"))
        _rh = _safe_float(_r.get("research_value_high"))
        _xm = _safe_float(_r.get("exploratory_max_bid"))
        _rbv = _safe_float(_r.get("research_bid_value") or _r.get("research_bid_reference"))
        _snipe_threshold = None
        for _v in (_xm, _rl, _rbv):
            if _v is not None and _v > 0:
                _snipe_threshold = float(_v) if _snipe_threshold is None else min(_snipe_threshold, float(_v))
        _watch_threshold = None
        for _v in (_rh, _rbv, _rl):
            if _v is not None and _v > 0:
                _watch_threshold = float(_v) if _watch_threshold is None else max(_watch_threshold, float(_v))
        if _snipe_threshold is None and _watch_threshold is None:
            _decision = "RESEARCH_PASS"
            _reason = "research_path_no_anchor_threshold"
        elif _snipe_threshold is not None and float(_cp) <= _snipe_threshold:
            _decision = "RESEARCH_SNIPE"
            _reason = f"research_snipe:cp({_cp:.2f})<=research_low/max_bid({_snipe_threshold:.2f})"
        elif _watch_threshold is not None and float(_cp) <= _watch_threshold:
            _decision = "RESEARCH_WATCH"
            _reason = f"research_watch:cp({_cp:.2f})<=research_high({_watch_threshold:.2f})"
        else:
            _decision = "RESEARCH_PASS"
            _ref = _watch_threshold if _watch_threshold is not None else (_snipe_threshold or 0.0)
            _reason = f"research_pass:cp({_cp:.2f})>research_high({_ref:.2f})"
        _label_map = {
            "RESEARCH_SNIPE": ("RESEARCH SNIPE", "Research-grade snipe — single-anchor pricing"),
            "RESEARCH_WATCH": ("RESEARCH WATCH", "Research-grade watch — verify before bid"),
            "RESEARCH_PASS":  ("RESEARCH PASS",  "Research-grade pass — price above research band"),
        }
        _badge, _cta = _label_map.get(_decision, ("RESEARCH PASS", "Research pass"))
        _edge_dollars = (float(_watch_threshold) if _watch_threshold else (float(_snipe_threshold) if _snipe_threshold else 0.0)) - float(_cp)
        _edge_pct = (_edge_dollars / float(_cp) * 100.0) if float(_cp) > 0 else None
        return {
            "final_execution_decision": _decision,
            "final_action_label": _badge,
            "final_cta_text": _cta,
            "final_badge_text": _badge,
            "final_action_reason": _reason,
            "final_edge_dollars": round(_edge_dollars, 2) if _edge_dollars is not None else None,
            "final_edge_pct": round(_edge_pct, 2) if _edge_pct is not None else None,
            "final_action_path": "research",
        }
    # Verified path — needs an actionable target_bid.
    _tb = _safe_float(_r.get("target_bid_price")) or _safe_float(_r.get("target_bid")) or _safe_float(_r.get("bid_ceiling_value"))
    if _tb is None or _tb <= 0:
        # No target_bid yet — the row is genuinely PASS for this scan.
        return {
            "final_execution_decision": "PASS",
            "final_action_label": "PASS — NO TARGET BID",
            "final_cta_text": "No target bid available — pass for this scan",
            "final_badge_text": "PASS",
            "final_action_reason": "no_target_bid",
            "final_edge_dollars": None,
            "final_edge_pct": None,
            "final_action_path": "verified",
        }
    _watch_ceiling = float(_tb) * 1.05
    _edge_dollars = float(_tb) - float(_cp)
    _edge_pct = (_edge_dollars / float(_cp) * 100.0) if float(_cp) > 0 else 0.0
    # [SNIPE_WINDOW_GUARD] — SNIPE_NOW must require remaining_seconds <= 3h
    # (the strict snipe window). Without this, PREPARE-bucket auctions
    # (3-12h) with current<=target were getting SNIPE_NOW labels — but the
    # user can't actually snipe them yet because they don't end for hours.
    # Outside the snipe window, current<=target should produce a "TARGET
    # READY · WAIT" decision so the user knows the target's clean but the
    # auction needs to enter the snipe window before bid placement.
    _SNIPE_WINDOW_SECONDS = 3.0 * 3600.0
    _remaining_seconds = (
        _safe_float(_r.get("remaining_seconds"))
        or _safe_float(_r.get("seconds_remaining"))
        or _safe_float(_r.get("_window_remaining_seconds"))
    )
    _within_snipe_window = (
        _remaining_seconds is not None
        and _remaining_seconds > 0
        and _remaining_seconds <= _SNIPE_WINDOW_SECONDS
    )
    if float(_cp) <= float(_tb):
        if _within_snipe_window:
            _decision = "SNIPE_NOW"
            _label = "SNIPE NOW"
            _cta = f"Snipe — current ${_cp:.2f} ≤ target ${_tb:.2f}"
            _reason = f"snipe_now:cp({_cp:.2f})<=tb({_tb:.2f})"
        else:
            # Target is clean BUT auction is outside the 0-3h snipe window.
            # User can't bid yet — auction will move before close. Label as
            # WATCH with a "TARGET READY" tone so the user knows to come
            # back when it enters the snipe window.
            _decision = "WATCH"
            _label = "WATCH — TARGET READY"
            _hours_remaining = (
                f"{_remaining_seconds/3600:.1f}h"
                if _remaining_seconds is not None
                else "unknown"
            )
            _cta = (
                f"Target ready (${_tb:.2f}) but auction ends in {_hours_remaining} — "
                f"return inside 3h window to snipe"
            )
            _reason = (
                f"target_ready_outside_snipe_window:"
                f"cp({_cp:.2f})<=tb({_tb:.2f}) "
                f"remaining_s={_remaining_seconds if _remaining_seconds is not None else 'na'}"
            )
    elif float(_cp) <= _watch_ceiling:
        _decision = "WATCH"
        _label = "WATCH"
        _cta = f"Watch — current ${_cp:.2f} within 5% of target ${_tb:.2f}"
        _reason = f"watch:cp({_cp:.2f})<=tb*1.05({_watch_ceiling:.2f})"
    else:
        # [UNDER_MV_TIER] — between target and MV*0.95 the row is still a real
        # deal: bidding under fair market value, just not at deep snipe-target
        # discount. Without this tier, every row sitting at 80-95% of MV got
        # mislabeled "PASS — OVERPRICED" — which is dishonest (it's UNDER market,
        # not over) and kills user retention because customers see PASS PASS PASS
        # forever even when the engine is finding legitimate value. Surface
        # these as UNDER_MV so daily wins are visible.
        # PASS_OVERPRICED now reserved for current_price > MV (true overpriced).
        _mv_for_tier = (
            _safe_float(_r.get("market_value"))
            or _safe_float(_r.get("true_market_value"))
            or _safe_float(_r.get("true_mv"))
            or _safe_float(_r.get("mv_value"))
            or 0.0
        )
        # [SYNTHETIC_MV_TIER_GUARD] — when the engine flagged this row's MV
        # as synthetic (echo of current_price, no real comp evidence) the
        # field looks valid but the UI tile already suppresses it to "—".
        # Using the synthetic MV here would produce dishonest claims like
        # "AT MARKET — current $60 ≈ MV $60" on rows with zero real comp
        # backing. Treat as no-MV: skip UNDER_MV and AT_MARKET, fall through
        # to PASS path (which now correctly says "no MV" instead of lying).
        _mv_is_synthetic = bool(
            (_r or {}).get("_synthetic_no_mv")
            or (_r or {}).get("_synthetic_trusted_exact")
            or ((_r or {}).get("mv_valid") is False)
        )
        if _mv_is_synthetic:
            _mv_for_tier = 0.0
        # Under-MV ceiling: 5% under MV. If current is at or below this, the
        # row is genuinely cheaper than market and worth surfacing.
        _under_mv_ceiling = _mv_for_tier * 0.95 if _mv_for_tier > 0 else 0.0
        if _mv_for_tier > 0 and float(_cp) <= _under_mv_ceiling:
            _decision = "UNDER_MV"
            _label = "UNDER MV"
            _mv_pct_under = (1.0 - float(_cp) / _mv_for_tier) * 100.0
            _cta = (
                f"Deal — current ${_cp:.2f} is {_mv_pct_under:.0f}% under MV ${_mv_for_tier:.2f} "
                f"(above snipe target ${_tb:.2f} but still below market)"
            )
            _reason = (
                f"under_mv:cp({_cp:.2f})<=mv*0.95({_under_mv_ceiling:.2f}) "
                f"mv={_mv_for_tier:.2f} pct_under_mv={_mv_pct_under:.1f}"
            )
            _edge_dollars = _mv_for_tier - float(_cp)
            _edge_pct = _mv_pct_under
        elif _mv_for_tier > 0 and float(_cp) <= _mv_for_tier:
            # Bidding at or just below MV (95-100%) — fair market, hold for now.
            _decision = "WATCH"
            _label = "AT MARKET"
            _cta = f"At market — current ${_cp:.2f} ≈ MV ${_mv_for_tier:.2f}; hold for price drop"
            _reason = f"at_market:mv*0.95({_under_mv_ceiling:.2f})<cp({_cp:.2f})<=mv({_mv_for_tier:.2f})"
        else:
            # current > MV (or no MV available) — true overpriced
            _decision = "PASS_OVERPRICED"
            _label = "PASS — OVERPRICED"
            if _mv_for_tier > 0:
                _cta = f"Pass — current ${_cp:.2f} above MV ${_mv_for_tier:.2f}"
                _reason = f"pass_overpriced:cp({_cp:.2f})>mv({_mv_for_tier:.2f})"
            else:
                _cta = f"Pass — current ${_cp:.2f} > target ${_tb:.2f} +5% (no MV)"
                _reason = f"pass_overpriced_no_mv:cp({_cp:.2f})>tb*1.05({_watch_ceiling:.2f})"
    return {
        "final_execution_decision": _decision,
        "final_action_label": _label,
        "final_cta_text": _cta,
        "final_badge_text": _label,
        "final_action_reason": _reason,
        "final_edge_dollars": round(_edge_dollars, 2),
        "final_edge_pct": round(_edge_pct, 2),
        "final_action_path": "verified",
    }


def _es_apply_final_execution_action(_row: Dict[str, Any]) -> Dict[str, Any]:
    """Compute + stamp the final action onto the row in place. Returns the
    decision dict so callers can also pass it through to view models."""
    _decision = _es_compute_final_execution_action(_row)
    if isinstance(_row, dict):
        _row["execution_final_decision"] = _decision["final_execution_decision"]
        _row["final_execution_decision"] = _decision["final_execution_decision"]
        _row["execution_decision"] = _decision["final_execution_decision"]
        _row["final_action_label"] = _decision["final_action_label"]
        _row["final_cta_text"] = _decision["final_cta_text"]
        _row["final_badge_text"] = _decision["final_badge_text"]
        _row["final_action_reason"] = _decision["final_action_reason"]
        _row["final_edge_dollars"] = _decision["final_edge_dollars"]
        _row["final_edge_pct"] = _decision["final_edge_pct"]
        _row["final_action_path"] = _decision["final_action_path"]
    try:
        _common = (
            f"title={str((_row or {}).get('title') or (_row or {}).get('source_title') or '')[:160]} "
            f"current_price={(_row or {}).get('current_price')} "
            f"target_bid={(_row or {}).get('target_bid_price') or (_row or {}).get('target_bid')} "
            f"research_low={(_row or {}).get('research_value_low')} "
            f"research_high={(_row or {}).get('research_value_high')} "
            f"exploratory_max_bid={(_row or {}).get('exploratory_max_bid')} "
            f"decision={_decision['final_execution_decision']} "
            f"path={_decision['final_action_path']} "
            f"edge_dollars={_decision['final_edge_dollars']} "
            f"edge_pct={_decision['final_edge_pct']} "
            f"reason={_decision['final_action_reason']}"
        )
        print(f"[FINAL_ACTION_DECISION] {_common}")
        if _decision["final_execution_decision"] in {"SNIPE_NOW", "RESEARCH_SNIPE"}:
            print(f"[FINAL_ACTION_SNIPE] {_common}")
        elif _decision["final_execution_decision"] in {"PASS_OVERPRICED", "RESEARCH_PASS", "PASS"}:
            print(f"[FINAL_ACTION_PASS] {_common}")
    except Exception:
        pass
    return _decision


def _ui_live_preserve_log(prefix: str, row: Dict[str, Any]) -> None:
    try:
        _row = row if isinstance(row, dict) else {}
        print(
            f"[{prefix}] "
            f"title={str(_row.get('title') or _row.get('source_title') or '')[:160]} "
            f"decision={_row.get('execution_final_decision') or _row.get('execution_decision') or 'none'} "
            f"bucket={_row.get('execution_admission_bucket') or _row.get('commercial_visibility') or _row.get('_surface_bucket') or 'none'} "
            f"truth={_row.get('truth') or _row.get('truth_level') or _row.get('valuation_truth_tier') or 'NONE'} "
            f"true_mv={_row.get('true_mv') or _row.get('true_market_value')} "
            f"review_estimate={_row.get('review_estimate') or _row.get('review')} "
            f"target_bid={_row.get('target_bid') or _row.get('target_bid_price')} "
            f"board_visible={_row.get('board_visible')} "
            f"commercially_visible={_row.get('commercially_visible')} "
            f"preserved_live={_row.get('board_contract_preserved_live')} "
            f"preserve_reason={_row.get('board_contract_preserve_reason') or 'none'}"
        )
    except Exception:
        pass


def _ui_preserve_live_surface_row_contract(row: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(row, dict):
        return row
    _decision = str(row.get("execution_final_decision") or row.get("execution_decision") or "").strip().upper()
    _bucket = str(row.get("execution_admission_bucket") or row.get("commercial_visibility") or row.get("final_bucket") or "").strip().lower()
    _surface_bucket = str(row.get("_surface_bucket") or "").strip().lower()
    _preserved = bool(
        row.get("board_contract_preserved_live")
        or row.get("late_live_surface_rescue")
        or row.get("_real_live_actionable_rescue")
        or row.get("real_live_actionable_rescue")
        or row.get("_final_visible_append_authority")
        or _decision in {"WATCH", "SNIPE"}
        or _bucket in {"watchlist", "sniper"}
        or _surface_bucket in {"watchlist", "sniper", "customer"}
    )
    if not _preserved:
        return row
    row["board_contract_preserved_live"] = True
    row["board_contract_preserve_reason"] = "live_surface_row_contract"
    if _decision == "SNIPE" or _bucket == "sniper" or _surface_bucket == "sniper":
        row["execution_final_decision"] = "SNIPE"
        row["execution_admission_bucket"] = "sniper"
        row["commercial_visibility"] = "sniper"
        row["final_bucket"] = "sniper"
        row["_final_bucket"] = "SNIPER"
        row["_surface_bucket"] = "sniper"
        row["surface_intent"] = "sniper"
        row["board_bucket"] = "SNIPER"
        row["_board_bucket"] = "SNIPER"
    else:
        row["execution_final_decision"] = "WATCH"
        row["execution_admission_bucket"] = "watchlist"
        row["commercial_visibility"] = "watchlist"
        row["final_bucket"] = "watchlist"
        row["_final_bucket"] = "WATCHLIST"
        row["_surface_bucket"] = "watchlist" if _surface_bucket != "customer" else "customer"
        row["surface_intent"] = "watchlist"
        row["board_bucket"] = "WATCH"
        row["_board_bucket"] = "WATCH"
    row["board_visible"] = True
    row["commercially_visible"] = True
    row["_render_live_watchlist"] = True
    row["render_live_watchlist"] = True
    row["_bucket_scope_locked"] = True
    row["_bucket_scope_lock_reason"] = "live_surface_row_contract"
    _ui_live_preserve_log("LIVE_RENDER_PRESERVE", row)
    _ui_live_preserve_log("LIVE_RENDER_PRESERVE_ASSERT", row)
    return row


def _resolve_es_render_bucket_state(
    row: Dict[str, Any],
    view: Optional[Dict[str, Any]] = None,
    *,
    default_bucket: str = "REVIEW",
) -> Dict[str, Any]:
    _row = _ui_preserve_live_surface_row_contract(dict(row or {}))
    _view = dict(view or {})
    _title = str(_row.get("title") or _row.get("source_title") or "")[:140]
    _item = _ui_board_contract_item_key(_row)[:32]
    if bool(_row.get("board_contract_preserved_live")):
        _locked_bucket = "SNIPER" if str(_row.get("execution_admission_bucket") or "").strip().lower() == "sniper" else "WATCH"
        print(
            f"[LIVE_BUCKET_LOCK] title={_title} item={_item} "
            f"bucket_source=preserved_live bucket_value={_locked_bucket}"
        )
        return {
            "bucket_source": "preserved_live",
            "bucket_value": _locked_bucket,
            "default_used": False,
        }
    _bucket_sources = [
        ("row.board_bucket", _row.get("board_bucket")),
        ("row._board_bucket", _row.get("_board_bucket")),
        ("view.board_bucket", _view.get("board_bucket")),
        ("row.final_bucket", _row.get("final_bucket")),
        ("row.execution_admission_bucket", _row.get("execution_admission_bucket")),
        ("row.execution_decision", _row.get("execution_decision")),
    ]
    for _bucket_source, _bucket_value in _bucket_sources:
        _bucket = str(_bucket_value or "").strip().upper()
        if not _bucket:
            continue
        print(
            f"[BUCKET_SCOPE_FIX] title={_title} item={_item} "
            f"bucket_source={_bucket_source} bucket_value={_bucket}"
        )
        return {
            "bucket_source": _bucket_source,
            "bucket_value": _bucket,
            "default_used": False,
        }
    _default_bucket = str(default_bucket or "REVIEW").strip().upper() or "REVIEW"
    print(
        f"[BUCKET_SCOPE_MISSING] title={_title} item={_item} "
        f"default_used={_default_bucket} reason=missing_bucket_state"
    )
    print(
        f"[ES_RENDER_CRASH_GUARD] title={_title} item={_item} "
        f"crash_prevented=1 field=_fallback_bucket"
    )
    print(
        f"[BUCKET_SCOPE_FIX] title={_title} item={_item} "
        f"bucket_source=default bucket_value={_default_bucket}"
    )
    return {
        "bucket_source": "default",
        "bucket_value": _default_bucket,
        "default_used": True,
    }


def _log_review_promotion_check(
    row: Dict[str, Any],
    profile: Dict[str, Any],
    *,
    chosen: str,
    rejection_reason: str = "",
    stage: str = "profile",
) -> None:
    _row = dict(row or {})
    _profile = dict(profile or {})
    _title = str(_row.get("title") or _row.get("source_title") or "")[:140]
    _price = _safe_float(_profile.get("price") or _row.get("current_price") or _row.get("current_bid") or _row.get("price"))
    _review_est = _safe_float(_profile.get("review_estimate") or _row.get("review_estimate_value") or _row.get("anchored_estimate_value"))
    _target_bid = _safe_float(_profile.get("target_bid") or _row.get("target_bid") or _row.get("target_bid_price") or _row.get("bid_ceiling_value"))
    _edge_pct = _safe_float(_profile.get("edge_pct"))
    _premium_signals = list(_profile.get("premium_signals") or [])
    _comp_count = int(_profile.get("comp_count") or 0)
    _exact_comp_count = int(_profile.get("exact_comp_count") or 0)
    _confidence = str(_profile.get("confidence_tier") or _es_review_confidence_tier(_row)).strip().lower()
    _reasons = list(_profile.get("promotion_reasons") or [])
    print(
        f"[REVIEW_PROMOTION_CHECK] stage={stage} title={_title!r} "
        f"current_price={round(float(_price), 2) if _price and _price > 0 else None} "
        f"review_estimate={round(float(_review_est), 2) if _review_est and _review_est > 0 else None} "
        f"target_bid={round(float(_target_bid), 2) if _target_bid and _target_bid > 0 else None} "
        f"edge_pct={round(float(_edge_pct), 2) if _edge_pct is not None else None} "
        f"premium_signals={_premium_signals} comps={_comp_count} exact_comps={_exact_comp_count} "
        f"confidence={_confidence} chosen={str(chosen or '').upper() or 'REJECT'} "
        f"rejection_reason={str(rejection_reason or '') or 'none'} reasons={_reasons}"
    )


def _es_fallback_candidate_profile(row: Dict[str, Any]) -> Dict[str, Any]:
    _row = row or {}
    _truth = str(
        _row.get("valuation_truth_tier")
        or _row.get("_valuation_truth_tier")
        or _row.get("truth")
        or ""
    ).strip().upper()
    _review_est = _safe_float(_row.get("review_estimate_value") or _row.get("anchored_estimate_value")) or 0.0
    _price = _safe_float(_row.get("current_price") or _row.get("current_bid") or _row.get("price")) or 0.0
    _target_bid = _safe_float(_row.get("target_bid") or _row.get("target_bid_price") or _row.get("bid_ceiling_value")) or 0.0
    _title = str(_row.get("title") or _row.get("source_title") or "").strip().lower()
    _commercial_bucket = str(_row.get("commercial_bucket") or "WEAK").strip().upper()
    _comp_count = int((_safe_float(_row.get("mv_comp_count")) or _safe_float(_row.get("comp_count")) or _safe_float(_row.get("comps_count")) or 0))
    _exact_comp_count = int((_safe_float(_row.get("exact_comp_count")) or 0))
    _confidence_tier = _es_review_confidence_tier(_row)
    _product_tier = str(_row.get("product_tier") or "").strip().upper()
    _endgame_tier = str(_row.get("endgame_tier") or "").strip().lower()
    _chase_class = str(_row.get("chase_class") or "").strip().upper()
    _remaining_seconds = float(_es_time_remaining_seconds(_row) or 999999.0)
    _serial_raw = str(
        _row.get("serial")
        or _row.get("serial_denominator")
        or _row.get("serial_bucket")
        or ""
    ).strip()
    _serial_signal = bool(
        (_serial_raw and _serial_raw.lower() not in {"0", "none", "n/a"})
        or any(_tok in _title for _tok in ("/1 ", "/5 ", "/10 ", "/25 ", "/49 ", "/75 ", "/99 "))
    )
    _auto_signal = any(_tok in _title for _tok in ("auto", "autograph", "rpa", "patch", "relic"))
    _premium_subset_signal = any(
        _tok in _title for _tok in (
            "kaboom", "downtown", "stained glass", "genesis", "color blast",
            "zebra", "vinyl", "gold", "black", "aura",
        )
    )
    _endgame_signal = bool(
        _endgame_tier == "endgame"
        or _product_tier in {"PREMIUM", "ENDGAME"}
        or _chase_class in {"ENDGAME_CHASE", "PREMIUM_SECONDARY"}
        or any(_tok in _title for _tok in (
            "national treasures", "immaculate", "flawless", "spectra", "contenders optic",
        ))
    )
    _premium_signal = bool(
        _serial_signal
        or _auto_signal
        or _premium_subset_signal
        or _endgame_signal
        or _commercial_bucket in {"MID", "STRONG", "ELITE"}
    )
    _premium_signals: List[str] = []
    if _serial_signal:
        _premium_signals.append("serial")
    if _auto_signal:
        _premium_signals.append("auto_patch")
    if _premium_subset_signal:
        _premium_signals.append("premium_subset")
    if _endgame_signal:
        _premium_signals.append("endgame_product")
    if _commercial_bucket in {"MID", "STRONG", "ELITE"}:
        _premium_signals.append(f"commercial_{_commercial_bucket.lower()}")
    if _exact_comp_count > 0:
        _premium_signals.append("exact_comp_support")
    _profile_base = {
        "review_estimate": _review_est,
        "price": _price,
        "target_bid": _target_bid,
        "edge_dollars": 0.0,
        "edge_pct": 0.0,
        "relative_price_vs_review": -1.0,
        "premium_signal": _premium_signal,
        "serial_signal": _serial_signal,
        "premium_signals": list(_premium_signals),
        "premium_score": 0.0,
        "remaining_seconds": _remaining_seconds,
        "comp_count": _comp_count,
        "exact_comp_count": _exact_comp_count,
        "confidence_tier": _confidence_tier,
        "promotion_reasons": [],
        "board_bucket": "",
    }
    if _truth != "REVIEW":
        return {"allow": False, "reason": "truth_not_review", **_profile_base}
    if _review_est <= 0:
        _profile = {"allow": False, "reason": "missing_review_estimate", **_profile_base}
        _log_review_promotion_check(_row, _profile, chosen="REJECT", rejection_reason="missing_review_estimate")
        return _profile
    if _price <= 0:
        _profile = {"allow": False, "reason": "missing_price", **_profile_base}
        _log_review_promotion_check(_row, _profile, chosen="REJECT", rejection_reason="missing_price")
        return _profile
    _edge_dollars = round(_review_est - _price, 2)
    _edge_pct = round(((_review_est - _price) / _review_est) * 100.0, 2) if _review_est > 0 else 0.0
    _relative_price_vs_review = round(((_review_est - _price) / _review_est), 4) if _review_est > 0 else -1.0
    _target_bid_ready = _target_bid > 0
    _time_too_long = _remaining_seconds > _FALLBACK_REVIEW_MAX_BOARD_SECONDS and not _endgame_signal
    _confidence_too_weak = _confidence_tier == "unknown" or (
        _confidence_tier == "low" and _comp_count <= 0 and not (_serial_signal or _auto_signal or _premium_subset_signal or _endgame_signal)
    )
    _prepare_edge_pct = _FALLBACK_PREMIUM_PREPARE_EDGE_PCT if _premium_signal else _FALLBACK_PREPARE_EDGE_PCT
    _prepare_edge_dollars = _FALLBACK_PREMIUM_PREPARE_EDGE_DOLLARS if _premium_signal else _FALLBACK_PREPARE_EDGE_DOLLARS
    _monitor_edge_pct = _FALLBACK_PREMIUM_MONITOR_EDGE_PCT if (_premium_signal and _target_bid_ready) else _FALLBACK_MONITOR_EDGE_PCT
    _monitor_edge_dollars = _FALLBACK_PREMIUM_MONITOR_EDGE_DOLLARS if (_premium_signal and _target_bid_ready) else _FALLBACK_MONITOR_EDGE_DOLLARS
    _prepare_ready = bool(
        _premium_signal
        and not _time_too_long
        and not (_confidence_too_weak and not (_serial_signal or _endgame_signal or _target_bid_ready))
        and (_edge_pct >= _prepare_edge_pct or _edge_dollars >= _prepare_edge_dollars)
        and (_target_bid_ready or _review_est >= 25.0)
    )
    _monitor_ready = bool(
        _premium_signal
        and _target_bid_ready
        and not _time_too_long
        and _confidence_tier in {"high", "medium", "low"}
        and (_edge_pct >= _monitor_edge_pct or _edge_dollars >= _monitor_edge_dollars)
    )
    _watch_ready = bool(
        _premium_signal
        and not _time_too_long
        and (
            _target_bid_ready
            or _review_est >= 18.0
            or _price >= 10.0
            or _edge_dollars >= 3.0
        )
    )
    _promotion_reasons: List[str] = []
    if not _prepare_ready:
        _promotion_reasons.append("prepare_threshold_miss")
    if not _monitor_ready:
        _promotion_reasons.append("monitor_threshold_miss")
    if not _target_bid_ready:
        _promotion_reasons.append("no_target_bid")
    if not _premium_signal:
        _promotion_reasons.append("no_premium_signal")
    if _confidence_too_weak:
        _promotion_reasons.append("confidence_too_weak")
    if _time_too_long:
        _promotion_reasons.append("time_remaining_too_long")
    if _edge_dollars < _monitor_edge_dollars and _edge_pct < _monitor_edge_pct:
        _promotion_reasons.append("review_edge_too_low")
    _bucket = ""
    if _prepare_ready:
        _bucket = "PREPARE"
    elif _monitor_ready:
        _bucket = "MONITOR"
    elif _watch_ready:
        _bucket = "WATCH"
    _premium_score = round(
        float(_row.get("commercial_signal_score") or 0.0)
        + float(_row.get("sniper_board_score") or 0.0) * 0.45
        + float(_row.get("whatnot_heat_score") or 0.0) * 0.20
        + float(_row.get("desirability_score") or 0.0) * 0.15
        + (14.0 if _premium_signal else 0.0)
        + (10.0 if _serial_signal else 0.0)
        + (8.0 if _auto_signal else 0.0)
        + (8.0 if _premium_subset_signal else 0.0)
        + (6.0 if _endgame_signal else 0.0),
        2,
    )
    _primary_reason = ""
    if not _bucket:
        for _reason in (
            "time_remaining_too_long",
            "no_premium_signal",
            "no_target_bid",
            "confidence_too_weak",
            "review_edge_too_low",
            "monitor_threshold_miss",
            "prepare_threshold_miss",
        ):
            if _reason in _promotion_reasons:
                _primary_reason = _reason
                break
        if not _primary_reason:
            _primary_reason = "review_edge_too_low"
    _profile = {
        "allow": bool(_bucket),
        "reason": "review_edge_available" if _bucket else _primary_reason,
        "review_estimate": _review_est,
        "price": _price,
        "target_bid": _target_bid,
        "edge_dollars": _edge_dollars,
        "edge_pct": _edge_pct,
        "relative_price_vs_review": _relative_price_vs_review,
        "premium_signal": _premium_signal,
        "serial_signal": _serial_signal,
        "premium_signals": list(_premium_signals),
        "board_bucket": _bucket,
        "premium_score": _premium_score,
        "remaining_seconds": _remaining_seconds,
        "comp_count": _comp_count,
        "exact_comp_count": _exact_comp_count,
        "confidence_tier": _confidence_tier,
        "promotion_reasons": list(dict.fromkeys(_promotion_reasons)),
    }
    _log_review_promotion_check(
        _row,
        _profile,
        chosen=_bucket or "REJECT",
        rejection_reason="" if _bucket else _primary_reason,
    )
    return _profile


def _es_fallback_backfill_sort_key(row: Dict[str, Any]) -> Tuple[float, float, float, float, float]:
    _profile = dict((row or {}).get("_fallback_candidate_profile") or {})
    _bucket = str(_profile.get("board_bucket") or "").strip().upper()
    _bucket_rank = {"PREPARE": 0, "MONITOR": 1, "WATCH": 2}.get(_bucket, 3)
    return (
        float(_bucket_rank),
        -float(_profile.get("premium_score") or 0.0),
        -float(1 if _profile.get("serial_signal") else 0),
        float(_profile.get("remaining_seconds") or 999999.0),
        -float(_profile.get("relative_price_vs_review") or -1.0),
    )


def _normalize_sport_label(_value: Any) -> str:
    _raw = str(_value or "").strip().lower()
    if _raw in {"football", "nfl"}:
        return "NFL"
    if _raw in {"basketball", "nba"}:
        return "NBA"
    if _raw in {"baseball", "mlb"}:
        return "MLB"
    if _raw in {"hockey", "nhl"}:
        return "NHL"
    if _raw == "soccer":
        return "Soccer"
    return str(_value or "").strip().upper()


def _build_ending_soon_sport_options() -> List[str]:
    """Authoritative sport options for Ending Soon filter.
    Sources from actual tracked auction targets in player_hub_state.json."""
    try:
        import player_hub as _ph
        _hub_state = _ph.load_player_hub_state()
        _sports: set = set()
        _tracked_targets = _ph.build_tracked_scan_targets(_hub_state, listing_mode="auction")
        for _target in _tracked_targets:
            _s = _normalize_sport_label(_target.get("sport"))
            if _s:
                _sports.add(_s)
        _result = ["All"] + sorted(_sports)
        print(f"[SPORTS] tracked_target_sports={sorted(_sports)}")
        print(f"[SPORTS] sport_filter_options={_result}")
        return _result
    except Exception as _e:
        print(f"[ENDING_SOON_UI] sport_options_fallback error={_e}")
        return ["All"]


def _es_time_remaining_seconds(_row: Dict[str, Any]) -> Optional[float]:
    return _safe_float((_row or {}).get("remaining_seconds"))


def _format_remaining_time_label(remaining_seconds: Any) -> str:
    _seconds = _safe_float(remaining_seconds)
    if _seconds is None:
        return "Time unknown"
    if _seconds < 0:
        return "Ended"
    _seconds_int = int(_seconds)
    if _seconds_int < 60:
        return f"{_seconds_int}s left"
    if _seconds_int < 3600:
        _minutes, _secs = divmod(_seconds_int, 60)
        return f"{_minutes}m {_secs}s left"
    if _seconds_int < 86400:
        _hours, _rem = divmod(_seconds_int, 3600)
        _minutes = _rem // 60
        return f"{_hours}h {_minutes}m left"
    _days, _rem = divmod(_seconds_int, 86400)
    _hours = _rem // 3600
    return f"{_days}d {_hours}h left"


def _es_time_remaining_label(_row: Dict[str, Any]) -> str:
    return _format_remaining_time_label(_es_time_remaining_seconds(_row))


def _es_sort_rows_for_decision_surface(_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    _bucket_rank = {"action_ready": 0, "monitor": 1, "suppressed": 2}
    _action_rank = {"EXECUTE NOW": 0, "PREPARE SNIPE": 1, "WATCH CLOSELY": 2, "MONITOR": 3, "REVIEW ONLY": 4, "OVER MV": 5, "NO BID YET": 6, "NO VALID TARGET BID": 6, "PASS": 7}
    _quality_rank = {"execution_ready": 0, "monitor_only": 1, "quarantined": 2}
    _class_rank = {"ELITE": 0, "STRONG": 1, "GOOD": 2, "BIN_DEAL": 3, "UNKNOWN": 4}
    _confidence_rank = {"resolved": 0, "strong": 0, "high": 0, "medium": 1, "weak": 2, "low": 2, "unresolved": 3}

    # Decision rank map MUST match the strings the engine actually stamps via
    # `_es_compute_final_execution_action` (final_execution_decision):
    #   SNIPE_NOW       — current_price <= target_bid (executable)
    #   RESEARCH_SNIPE  — executable but valuation provisional
    #   WATCH           — within 5% of target (approaching executability)
    #   PASS_OVERPRICED — current_price > target_bid * 1.05 (skip)
    #   RESEARCH_PASS   — pass with provisional valuation
    #   PASS / SKIP     — generic non-actionable
    # Earlier this map used legacy strings (EXECUTE_NOW, PREPARE, SNIPE) which
    # the engine never produces, so every row fell to the default rank=3 and
    # the primary sort tier collapsed — PASS_OVERPRICED rows could surface
    # before SNIPE_NOW. Now SNIPE_NOW=0, RESEARCH_SNIPE=1, WATCH=2, PASS=3.
    _dec_rank_map = {
        "SNIPE_NOW": 0,
        "EXECUTE_NOW": 0,
        "RESEARCH_SNIPE": 1,
        "PREPARE": 1,
        "SNIPE": 1,
        # UNDER_MV is a real deal (current < MV) just above the snipe target.
        # Slot it between RESEARCH_SNIPE and WATCH so deals surface near the
        # top of the board. This is the customer-retention tier — daily wins.
        "UNDER_MV": 2,
        "WATCH": 3,
        "RESEARCH_PASS": 4,
        "PASS_OVERPRICED": 5,
        "PASS": 5,
        "SKIP": 5,
    }

    def _row_sort_key(_row: Dict[str, Any]) -> tuple:
        _enriched = _es_strengthen_row_valuation(_row)
        _dq = _es_score_decision_quality(_enriched)
        _view = _es_get_decision_view_model(_enriched)
        _live_signal = _score_live_signal_origin(_enriched)
        _readiness = _es_get_valuation_readiness(_enriched)
        _bucket = str(_readiness.get("bucket") or "suppressed")
        _quality = str(_enriched.get("row_quality_state") or "").strip().lower()
        _deal_class = str(_enriched.get("deal_class") or "UNKNOWN").strip().upper()
        _edge = _safe_float(_enriched.get("edge_pct")) or _safe_float(_enriched.get("edge_percent")) or -999.0
        _edge_dollars = _safe_float(_enriched.get("edge_dollars")) or -999.0
        _target_bid_ready = bool(_readiness.get("target_bid_ready"))
        _confidence = str(_readiness.get("confidence_tier") or "").strip().lower()
        _comp_count = int(_readiness.get("comp_count") or 0)
        _time_left = _es_time_remaining_seconds(_enriched)
        if _time_left is None:
            _time_left = 10**9
        _dqs = float(_dq.get("decision_quality_score") or 0.0)
        _exec_r = float(_dq.get("execution_readiness") or 0.0)
        # Engine-stamped execution decision + score (primary sort signal)
        _exec_dec = str(_enriched.get("execution_decision") or _view.get("execution_decision") or "PASS")
        _exec_score = float(_enriched.get("execution_score") or _view.get("execution_score") or 0.0)
        # Truth contract: actionable first, then review candidates, then rest
        _is_actionable = bool(_view.get("is_actionable_bid") or _enriched.get("is_actionable_bid"))
        _is_review = bool(_view.get("is_review_candidate") or _enriched.get("is_review_candidate"))
        _actionability_tier = 0 if _is_actionable else (1 if _is_review else 2)
        return (
            _dec_rank_map.get(_exec_dec, 6),       # SNIPE_NOW → RESEARCH_SNIPE → UNDER_MV → WATCH → PASS → unknown
            -round(_exec_score),                   # execution score descending within decision tier
            _actionability_tier,                   # actionable → review → rest
            _action_rank.get(str(_view.get("action_label") or "PASS").upper(), 8),
            _bucket_rank.get(_bucket, 3),
            -float(_live_signal.get("live_signal_score") or 0.0),
            -round(_dqs),                          # decision quality descending
            -round(_exec_r),                       # execution readiness descending
            0 if _target_bid_ready else 1,
            -float(_dq.get("valuation_trust_score") or 0.0),
            _quality_rank.get(_quality, 3),
            _time_left,
            _class_rank.get(_deal_class, 5),
            -_edge,
            -_edge_dollars,
            _confidence_rank.get(_confidence, 3),
            -_comp_count,
        )

    _sorted = sorted(list(_rows or []), key=_row_sort_key)
    _actionable_first = sum(1 for _r in _sorted if _r.get("is_actionable_bid"))
    print(f"[ES][BOARD_SORT] actionable_first={_actionable_first} sorted_rows={len(_sorted)}")
    return _sorted


def _es_compute_target_bid_fields(_row: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(_row, dict) and _row.get("_research_only_price_check"):
        return {
            "target_bid_price": None,
            "target_bid_pct_used": None,
            "target_bid_source": "research_only_price_check",
            "target_bid_source_detail": "research_only_price_check",
            "target_bid_ready": False,
            "target_bid_confidence": "NONE",
            "bid_ceiling_value": None,
            "bid_ceiling_source": "NONE",
            "bid_ceiling_confidence": "NONE",
            "bid_ceiling_ready": False,
            "_bid_mode": "none",
        }
    _source = str(_row.get("mv_source") or _row.get("market_value_source") or "").strip().lower()
    _comp_count = int((_safe_float(_row.get("mv_comp_count")) or _safe_float(_row.get("comp_count")) or 0))
    _market_value = _safe_float(_row.get("true_market_value")) or _safe_float(_row.get("market_value_true"))
    _review_estimate = _safe_float(_row.get("review_estimate_value")) or _es_resolve_review_estimate(_row)
    _bid_mode = "true_market_value"
    if _market_value is None or _market_value <= 0:
        _market_value = None
    if (_market_value is None or _market_value <= 0) and (_review_estimate is None or _review_estimate <= 0):
        return {
            "target_bid_price": None,
            "target_bid_pct_used": None,
            "target_bid_source": "unavailable",
            "target_bid_source_detail": "unavailable",
            "target_bid_ready": False,
            "target_bid_confidence": "NONE",
            "bid_ceiling_value": None,
            "bid_ceiling_source": "NONE",
            "bid_ceiling_confidence": "NONE",
            "bid_ceiling_ready": False,
            "_bid_mode": "none",
        }
    _target_pct = _safe_float(_row.get("target_bid_pct")) or 0.75
    if _target_pct > 1.0:
        _target_pct = _target_pct / 100.0
    _target_pct = max(0.05, min(0.99, _target_pct))
    if (_market_value is None or _market_value <= 0) and _review_estimate and _review_estimate > 0:
        _bid_mode = "review_estimate"
    _target_bid = _safe_float(_row.get("bid_ceiling_value"))
    _target_source = str(_row.get("bid_ceiling_source") or "")
    # Read engine-stamped bid confidence (if engine already ran the bid ladder)
    _engine_tb_conf = str(_row.get("bid_ceiling_confidence") or _row.get("target_bid_confidence") or "").strip().upper()
    _engine_tb_src = str(_row.get("bid_ceiling_source") or _row.get("target_bid_source_detail") or _row.get("target_bid_source") or "").strip()
    if _target_bid is None:
        for _field_name, _source_name in [
            ("adjusted_max_bid", "adjusted_max_bid"),
            ("target_max_bid", "target_max_bid"),
            ("target_bid", "target_bid"),
            ("target_bid_price", "target_bid_price"),
            ("max_bid", "max_bid"),
        ]:
            _candidate = _safe_float(_row.get(_field_name))
            if _candidate is not None and _candidate > 0:
                _target_bid = _candidate
                _target_source = _source_name
                break
    if _target_bid is None and _market_value and _market_value > 0:
        _target_bid = round(_market_value * _target_pct, 2)
        _target_source = "market_value_default_75pct"
        _bid_mode = "true_market_value"
    elif _target_bid is None and _review_estimate and _review_estimate > 0:
        _target_bid = round(_review_estimate * 0.72, 2)
        _target_source = "review_estimate_soft_72pct"
        _bid_mode = "review_estimate"
    # Resolve bid confidence: prefer engine-stamped, fall back to source inference
    if _target_bid is not None:
        if _bid_mode == "review_estimate":
            _tb_conf = "REVIEW"
        elif _engine_tb_conf in {"HIGH", "MEDIUM", "REVIEW"}:
            _tb_conf = _engine_tb_conf
        elif _target_source in {"adjusted_max_bid", "target_max_bid", "target_bid", "target_bid_price", "max_bid"}:
            _tb_conf = "HIGH"
        elif _engine_tb_src == "discount_median" or _target_source == "discount_median":
            _tb_conf = "MEDIUM"
        elif _engine_tb_src == "review_ceiling" or _target_source == "review_ceiling":
            _tb_conf = "REVIEW"
        else:
            _tb_conf = "MEDIUM"  # market_value_default_75pct
    else:
        _tb_conf = "NONE"
    print(f"[BID_MODE] title={str(_row.get('title') or '')[:120]} mode={_bid_mode} target_bid={_target_bid}")
    return {
        "target_bid_price": _target_bid,
        "target_bid_pct_used": _target_pct if _target_bid is not None else None,
        "target_bid_source": _target_source or "unavailable",
        "target_bid_source_detail": _engine_tb_src or _target_source or "unavailable",
        "target_bid_ready": bool(_target_bid is not None and _target_bid > 0),
        "target_bid_confidence": _tb_conf,
        "bid_ceiling_value": _target_bid,
        "bid_ceiling_source": _engine_tb_src or _target_source or "NONE",
        "bid_ceiling_confidence": _tb_conf,
        "bid_ceiling_ready": bool(_target_bid is not None and _target_bid > 0),
        "_bid_mode": _bid_mode,
    }


def _es_strengthen_row_valuation(_row: Dict[str, Any]) -> Dict[str, Any]:
    _item = dict(_row or {})
    _item = _ui_stamp_research_only_display(_item)
    # Recompute remaining_seconds live from source_end_time / end_iso (avoids stale cached value)
    _end_iso = str(_item.get("source_end_time") or _item.get("end_iso") or "").strip()
    _remaining_seconds = _safe_float(_item.get("remaining_seconds"))
    if _end_iso:
        try:
            import re as _re
            _s = _re.sub(r"\.\d+", "", _end_iso.replace("Z", "+00:00"))
            from datetime import datetime as _dt, timezone as _tz
            _end_dt = _dt.fromisoformat(_s)
            if _end_dt.tzinfo is None:
                _end_dt = _end_dt.replace(tzinfo=_tz.utc)
            _live_secs = (_end_dt - _dt.now(tz=_tz.utc)).total_seconds()
            if _live_secs > 86400 * 30:
                _live_secs = _live_secs / 1000.0
            _remaining_seconds = max(0.0, _live_secs)
        except Exception:
            pass  # keep pre-computed value on parse failure
    _item["remaining_seconds"] = _remaining_seconds
    # Lock current_price to source_display_price for auction rows (prevents BIN price contamination)
    _src_display = _safe_float(_item.get("source_display_price"))
    _src_price_kind = str(_item.get("source_price_kind") or "").strip()
    if _src_display and _src_display > 0 and _src_price_kind == "auction_bid":
        _item["current_price"] = _src_display
        _item["current_bid"] = _src_display
    _mv_source = str(_item.get("mv_source") or _item.get("market_value_source") or _item.get("valuation_basis") or "").strip() or "none"
    _comp_count = 0
    for _field_name in ("mv_comp_count", "comp_count", "comps_count", "dominant_comp_count", "market_lane_comp_count", "market_lane_recent_count"):
        _candidate = int((_safe_float(_item.get(_field_name)) or 0))
        if _candidate > _comp_count:
            _comp_count = _candidate
    _market_value_raw = _safe_float(_item.get("market_value_raw")) or _safe_float(_item.get("mv_value")) or _safe_float(_item.get("market_value"))
    _valuation_source_clean = _es_valuation_source_clean(_item) or str(_mv_source).strip().lower() or "none"
    _true_mv = _safe_float(_item.get("true_market_value"))
    if _true_mv is None or _true_mv <= 0:
        _true_mv = _safe_float(_item.get("market_value_true"))
    _review_estimate = _safe_float(_item.get("review_estimate_value"))
    if _review_estimate is None or _review_estimate <= 0:
        _review_estimate = _es_resolve_review_estimate(_item)
    _anchor_estimate = _safe_float(_item.get("anchored_estimate_value"))
    if (_anchor_estimate is None or _anchor_estimate <= 0) and _review_estimate and _valuation_source_clean in {
        "price_anchor_fallback",
        "price_anchor_emergency",
        "soft_watchlist_estimate",
        "review_estimate",
        "anchor_only",
    }:
        _anchor_estimate = _review_estimate
    _truth_probe = dict(_item)
    _truth_probe["true_market_value"] = _true_mv
    _truth_probe["valuation_source"] = _valuation_source_clean
    _truth_probe["mv_source"] = _valuation_source_clean
    _truth_probe["market_value_source"] = _valuation_source_clean
    _truth_probe["usable_comp_count"] = _comp_count
    _truth_probe["comp_count"] = _comp_count
    if not _es_has_true_market_value(_truth_probe):
        _true_mv = None
    if _true_mv is None and (_review_estimate is None or _review_estimate <= 0):
        _review_estimate = _es_resolve_review_estimate(_truth_probe)
    _clone_probe = dict(_truth_probe)
    _clone_probe["true_market_value"] = _true_mv
    if _es_looks_like_current_price_clone(_clone_probe):
        _review_estimate = _true_mv
        _true_mv = None
        _item["_estimate_equals_current"] = True
        _item["_research_only_price_check"] = True
        _item["_research_only_reason"] = "mv_clone_or_no_renderable_evidence"
        _item = _ui_stamp_research_only_display(_item)
        print(
            f"[MV_CLONE_BLOCK] title={str(_item.get('title') or _item.get('source_title') or '')[:120]} "
            f"current={_item.get('current_price')} review={_review_estimate}"
        )
    elif _review_estimate is not None:
        _cp_for_est = _safe_float(_item.get("current_price"))
        if _cp_for_est is not None and abs(_cp_for_est - _review_estimate) < 0.01 and _valuation_source_clean in {
            "soft_watchlist_estimate",
            "price_anchor_fallback",
            "anchor_only",
            "review_estimate",
        }:
            _item["_estimate_equals_current"] = True
    _confidence_raw = str(
        _item.get("valuation_confidence")
        or _item.get("mv_confidence")
        or _item.get("market_value_confidence")
        or _item.get("confidence")
        or ""
    ).strip().lower().replace(" ", "_")
    if _confidence_raw in {"high", "resolved", "strong"}:
        _confidence_tier = "high"
    elif _confidence_raw in {"medium", "usable", "med"}:
        _confidence_tier = "medium"
    elif _confidence_raw in {"low", "estimate_only", "manual_context", "unknown", "excluded"}:
        _confidence_tier = "low"
    elif bool(_item.get("low_confidence")):
        _confidence_tier = "low"
    elif _mv_source in {"strong_comp_engine"}:
        _confidence_tier = "high"
    elif _mv_source in {"scarcity_supported_comp_engine", "medium_comp_engine", "hybrid_exact_lane", "hybrid_near_lane"}:
        _confidence_tier = "medium"
    elif _mv_source in {"fallback_comp_support", "structured_fallback", "unresolved", "none", "error",
                        "listing_type_excluded", "legacy_comp_engine", "market_estimate_fallback"}:
        # legacy_comp_engine: exception fallback only — no fingerprint, no strict validation.
        # market_estimate_fallback: permissive fallback layer — let confidence field drive tier.
        # confidence field is checked first above, so this only fires if confidence is absent.
        _confidence_tier = "low"
    else:
        _confidence_tier = "unknown"
    if _true_mv and _true_mv > 0 and not bool(_item.get("insufficient_data", False)):
        _mv_status_norm = "ready"
    elif _review_estimate and _review_estimate > 0:
        _mv_status_norm = "thin_support"
    elif bool(_item.get("insufficient_data", False)):
        _mv_status_norm = "insufficient_data"
    else:
        _mv_status_norm = "no_mv"
    _truth_tier = "TRUE" if (_true_mv and _true_mv > 0) else ("REVIEW" if (_review_estimate and _review_estimate > 0) else "NONE")
    _item["true_market_value"] = _true_mv
    _item["market_value_true"] = _true_mv
    _item["review_estimate_value"] = _review_estimate
    _item["mv_value"] = _true_mv
    _item["market_value"] = _true_mv
    _item["anchored_estimate_value"] = _anchor_estimate
    _item["market_value_raw"] = _market_value_raw
    _item["mv_source"] = _mv_source
    _item["market_value_source"] = str(_item.get("market_value_source") or _mv_source)
    _item["valuation_source"] = str(_item.get("valuation_source") or _item.get("market_value_source") or _item.get("mv_source") or _valuation_source_clean)
    _item["valuation_source_clean"] = _valuation_source_clean
    _item["valuation_truth_tier"] = _truth_tier
    _item["_valuation_truth_tier"] = _truth_tier
    _item["exact_comp_count"] = _ui_exact_comp_count(_item)
    _item["comp_source_label"] = str(_item.get("comp_source_label") or _mv_source or "unresolved")
    _item["mv_confidence"] = str(_item.get("mv_confidence") or _confidence_tier).upper()
    _item["valuation_confidence"] = _confidence_tier
    _item["mv_comp_count"] = _comp_count
    _item["comp_count"] = _comp_count
    _item["mv_status_norm"] = _mv_status_norm
    _item["scarcity_class"] = str(_item.get("scarcity_class") or "unknown")
    _item["subset_name"] = str(_item.get("subset_name") or "")
    _item["parallel_name"] = str(_item.get("parallel_name") or _item.get("parallel_bucket") or "")
    _item["serial_denominator"] = str(_item.get("serial_denominator") or "")
    _item["serial_bucket"] = str(_item.get("serial_bucket") or "")
    _item["one_of_one"] = bool(_item.get("one_of_one"))
    _item["scarcity_confidence"] = _safe_float(_item.get("scarcity_confidence")) or 0.0
    _item["lane_type"] = str(_item.get("lane_type") or "generic")
    _item["lane_aligned"] = bool(_item.get("lane_aligned"))
    _item["primary_query"] = str(_item.get("primary_query") or _item.get("debug_search_query") or "")
    _item["recovery_stage"] = str(_item.get("recovery_stage") or "primary")
    _item["recovery_reason"] = str(_item.get("recovery_reason") or "")
    _item["lane_origin"] = str(_item.get("lane_origin") or "tracked_exact")
    _item["route_stage"] = str(_item.get("route_stage") or "tracked_exact")
    _item["route_reason"] = str(_item.get("route_reason") or "")
    _item["formatted_time_left"] = _format_remaining_time_label(_remaining_seconds)
    _item["promoted_live_candidate"] = bool(_item.get("promoted_live_candidate")) or str(_item.get("route_stage") or "") == "promoted_live_candidate"
    _item["premium_review_status"] = str(_item.get("premium_review_status") or "")
    _item["premium_review_reason"] = str(_item.get("premium_review_reason") or "")
    _item["review_failed"] = bool(_item.get("review_failed"))
    _item["review_failure_reason"] = str(_item.get("review_failure_reason") or "")
    _item = _ui_apply_true_mv_contract_guard(_item, trace_tag="BOARD_HYDRATE_TRACE")
    _true_mv = _safe_float(_item.get("true_market_value")) or _safe_float(_item.get("market_value_true"))
    _review_estimate = _safe_float(_item.get("review_estimate_value")) or _es_resolve_review_estimate(_item)
    _truth_tier = str(_item.get("_valuation_truth_tier") or _item.get("valuation_truth_tier") or "NONE").strip().upper() or "NONE"
    _valuation_source_clean = str(_item.get("valuation_source_clean") or _item.get("market_value_source") or _item.get("mv_source") or "none").strip() or "none"
    if _true_mv and _true_mv > 0 and not bool(_item.get("insufficient_data", False)):
        _mv_status_norm = "ready"
    elif _review_estimate and _review_estimate > 0:
        _mv_status_norm = "thin_support"
    elif bool(_item.get("insufficient_data", False)):
        _mv_status_norm = "insufficient_data"
    else:
        _mv_status_norm = "no_mv"
    _item["mv_status_norm"] = _mv_status_norm
    _item["mv_attempted"] = bool(_item.get("mv_attempted")) or _item["promoted_live_candidate"]
    _item["mv_resolved"] = bool(_item.get("mv_resolved")) or bool(_true_mv and _true_mv > 0)
    _item["mv_valid"] = bool(_true_mv and _true_mv > 0)
    if not bool(_true_mv and _true_mv > 0) and (_mv_source in {"price_anchor_fallback", "price_anchor_emergency", "floor_fallback"} or _comp_count <= 0):
        _item["mv_blocked_reason"] = str(_item.get("mv_blocked_reason") or "anchor_only_no_real_mv")
    if _truth_tier == "REVIEW" and bool(_item.get("_estimate_equals_current")) and _comp_count < 2:
        _item["whatnot_heat_score"] = max(0.0, (_safe_float(_item.get("whatnot_heat_score")) or 0.0) - 6.0)
        _item["commercial_signal_score"] = max(0.0, (_safe_float(_item.get("commercial_signal_score")) or 0.0) - 4.0)
    print(
        f"[MV_TRUTH] title={str(_item.get('title') or _item.get('source_title') or '')[:120]} "
        f"truth={_truth_tier} true_mv={_true_mv} review={_review_estimate} source={_valuation_source_clean}"
    )
    _item["comp_attempted"] = bool(_item.get("comp_attempted")) or _item["promoted_live_candidate"]
    _item["target_bid_attempted"] = bool(_item.get("target_bid_attempted")) or _item["promoted_live_candidate"]
    _target_bid_fields = _es_compute_target_bid_fields(_item)
    _item.update(_target_bid_fields)
    _item["bid_ceiling_value"] = _safe_float(_item.get("bid_ceiling_value"))
    _item["bid_ceiling_source"] = str(_item.get("bid_ceiling_source") or "NONE")
    _item["bid_ceiling_confidence"] = str(_item.get("bid_ceiling_confidence") or "NONE").upper()
    _item["bid_ceiling_ready"] = bool(_item.get("bid_ceiling_ready"))
    _item["commercial_signal_score"] = _safe_float(_item.get("commercial_signal_score")) or 0.0
    _item["commercial_price_floor_pass"] = bool(_item.get("commercial_price_floor_pass"))
    _item["commercial_profit_floor_pass"] = bool(_item.get("commercial_profit_floor_pass"))
    _item["commercially_visible"] = bool(_item.get("commercially_visible", True))
    _item["commercial_visibility_reason"] = str(_item.get("commercial_visibility_reason") or "")
    _item["floor_exception"] = bool(_item.get("floor_exception"))
    _item["floor_exception_reason"] = str(_item.get("floor_exception_reason") or "")
    _item["sniper_board_score"] = _safe_float(_item.get("sniper_board_score")) or 0.0
    _item["hero_board_eligible"] = bool(_item.get("hero_board_eligible"))
    _item["hero_tier"] = str(_item.get("hero_tier") or "")
    _item["hero_reason"] = str(_item.get("hero_reason") or "")
    return _item


def _es_monitor_reason(_row: Dict[str, Any], _view: Optional[Dict[str, Any]] = None) -> str:
    _enriched = _es_strengthen_row_valuation(_row)
    if not bool((_view or {}).get("target_bid_ready") or _enriched.get("target_bid_ready")):
        return "No valid target bid yet"
    if str(_enriched.get("mv_status_norm") or "") in {"no_mv", "insufficient_data"}:
        return "No usable market value yet"
    if int(_enriched.get("mv_comp_count") or 0) <= 0:
        return "Comp depth is still thin"
    if str(_enriched.get("valuation_confidence") or "") not in {"high", "medium"}:
        return "Confidence still below promotion threshold"
    if (_safe_float(_enriched.get("edge_pct")) or 0.0) < 0:
        return "Current edge is not strong enough"
    if str(_enriched.get("mv_source") or "") in {"structured_fallback", "none", "error", "listing_type_excluded"}:
        return "Valuation source is still too weak"
    return "Monitor due to thin support"


def _es_get_valuation_readiness(_row: Dict[str, Any]) -> Dict[str, Any]:
    _normalized = _es_strengthen_row_valuation(_row)
    if not _es_is_resolved_board_row(_normalized):
        return {
            "bucket": "suppressed",
            "has_market_value": False,
            "has_comp_support": False,
            "confidence_tier": str(_normalized.get("valuation_confidence") or "low").strip().lower(),
            "target_bid_ready": False,
            "target_bid_price": None,
            "target_bid_source": "unresolved_no_trusted_mv",
            "target_bid_pct_used": None,
            "comp_count": int((_safe_float(_normalized.get("mv_comp_count")) or _safe_float(_normalized.get("comp_count")) or 0)),
            "deal_class": str(_normalized.get("deal_class") or "UNKNOWN").strip().upper(),
            "edge_pct": _safe_float(_normalized.get("edge_pct")) or _safe_float(_normalized.get("edge_percent")) or -999.0,
            "mv_value": 0.0,
            "mv_source": str(_normalized.get("mv_source") or "none"),
            "mv_status_norm": "unresolved_no_trusted_mv",
        }
    _live_signal = _score_live_signal_origin(_normalized)
    _forced_surface = bool(_normalized.get("forced_surface"))
    _market_value = _safe_float(_normalized.get("mv_value")) or 0.0
    _comp_count = int((_safe_float(_normalized.get("mv_comp_count")) or 0))
    _edge_pct = _safe_float(_normalized.get("edge_pct")) or _safe_float(_normalized.get("edge_percent")) or -999.0
    _quality_state = str(_normalized.get("row_quality_state") or "").strip().lower()
    _deal_class = str(_normalized.get("deal_class") or "UNKNOWN").strip().upper()
    _confidence_tier = str(_normalized.get("valuation_confidence") or "unknown").strip().lower()
    _target_bid_fields = _es_compute_target_bid_fields(_normalized)
    _target_bid_ready = bool(_target_bid_fields.get("target_bid_ready"))

    # ── EDGE SENTINEL REPAIR ────────────────────────────────────────────────
    # Pure repair — when _edge_pct is the -999 sentinel (or otherwise invalid)
    # but the row HAS an authoritative current_price AND a target_bid, compute
    # execution edge directly from the price-vs-bid math. Every downstream
    # gate (action_ready outer-arm, _xp_edge_within_floor, COMP_CONFIDENCE_TRACE,
    # final_action layer) then reads real edge instead of the sentinel.
    # Does not touch valuation, comp logic, identity, UI labels, ranking,
    # price authority, time windows, or self-comp contamination.
    def _edge_pct_is_sentinel(_v: Optional[float]) -> bool:
        if _v is None:
            return True
        try:
            _vf = float(_v)
        except Exception:
            return True
        # Sentinels and obviously-invalid values
        if _vf <= -100.0:
            return True
        if _vf != _vf:    # NaN
            return True
        if _vf in (float("inf"), float("-inf")):
            return True
        return False
    if _edge_pct_is_sentinel(_edge_pct):
        _esr_old_edge = _edge_pct
        _esr_cp = _ui_authoritative_current_price(_normalized)
        _esr_tb = _safe_float(_target_bid_fields.get("target_bid_price"))
        if _esr_tb is None or _esr_tb <= 0:
            _esr_tb = (
                _safe_float(_normalized.get("target_bid_price"))
                or _safe_float(_normalized.get("target_bid"))
                or _safe_float(_normalized.get("bid_ceiling_value"))
            )
        if _esr_cp is not None and _esr_cp > 0 and _esr_tb is not None and _esr_tb > 0:
            _esr_edge_dollars = float(_esr_tb) - float(_esr_cp)
            _esr_edge_pct = (_esr_edge_dollars / float(_esr_cp)) * 100.0
            _edge_pct = _esr_edge_pct
            try:
                print(
                    f"[EDGE_SENTINEL_REPAIR] "
                    f"title={str(_normalized.get('title') or _normalized.get('source_title') or '')[:160]} "
                    f"old_edge_pct={(round(float(_esr_old_edge), 2) if _esr_old_edge is not None else 'na')} "
                    f"current_price={round(float(_esr_cp), 2)} "
                    f"target_bid={round(float(_esr_tb), 2)} "
                    f"repaired_edge_pct={round(float(_esr_edge_pct), 2)} "
                    f"edge_dollars={round(float(_esr_edge_dollars), 2)}"
                )
            except Exception:
                pass
            # Also stamp the repaired edge on the row so downstream consumers
            # (ranking score, [COMP_CONFIDENCE_TRACE], view dict) see real math.
            try:
                if isinstance(_normalized, dict):
                    _normalized["edge_pct"] = round(float(_esr_edge_pct), 2)
                    _normalized["edge_dollars"] = round(float(_esr_edge_dollars), 2)
                    _normalized["_edge_repaired_from_sentinel"] = True
            except Exception:
                pass
    # ────────────────────────────────────────────────────────────────────────

    _has_mv = _market_value > 0
    _has_comp_support = _comp_count > 0
    _has_confidence_support = _confidence_tier in {"high", "medium"}
    _deal_class_ready = _deal_class in {"ELITE", "STRONG", "GOOD"}
    _weak_source = str(_normalized.get("mv_source") or "").strip().lower() in {"structured_fallback", "none", "error", "listing_type_excluded"}
    # ── PREMIUM EXECUTION-PROMOTION precondition ───────────────────────────
    # Strong cards (premium player + premium card structure + clean identity +
    # at least one exact comp + target_bid_ready) currently die at the
    # action_ready gate when:
    #   • valuation_confidence == "low"  (thin comp pools)
    #   • mv_source == "structured_fallback"  (the engine's normal fallback)
    #   • deal_class is "UNKNOWN" (not stamped)
    #   • edge_pct slightly negative (live current price above comp-derived target)
    # This bypass widens the funnel for rows that have already proven premium
    # identity AND a real bid floor, without admitting garbage. Pure execution
    # funnel optimization — does NOT touch identity matching, comp integrity,
    # valuation contamination protections, time windows, or UI truth labels.
    import re as _xp_re
    _xp_exact = int(
        _safe_float(_normalized.get("trusted_exact_comp_count"))
        or _safe_float(_normalized.get("exact_comp_count"))
        or _safe_float(_normalized.get("raw_exact_match_count"))
        or 0
    )
    _xp_serial_raw = str(
        _normalized.get("serial_denominator")
        or _normalized.get("_hydrated_serial_denominator")
        or _normalized.get("serial")
        or ""
    ).strip()
    _xp_has_serial = bool(_xp_serial_raw and _xp_serial_raw.lower() not in {"0", "none", ""})
    _xp_title_lc = str(_normalized.get("title") or _normalized.get("source_title") or "").lower()
    _xp_has_auto = bool(_xp_re.search(r"\b(auto|autograph)\b", _xp_title_lc)) if _xp_title_lc else False
    _xp_grade_uc = str(_normalized.get("grade") or _normalized.get("grade_label") or "").strip().upper()
    _xp_is_psa10 = ("PSA 10" in _xp_grade_uc) or ("PSA10" in _xp_grade_uc) or ("BGS 9.5" in _xp_grade_uc) or ("BGS 10" in _xp_grade_uc)
    _xp_parallel_lc = str(
        _normalized.get("parallel_family")
        or _normalized.get("_hydrated_parallel_family")
        or _normalized.get("parallel_name")
        or _normalized.get("parallel")
        or ""
    ).strip().lower()
    _xp_is_premium_parallel = bool(_xp_parallel_lc and _xp_parallel_lc not in {"base", "common", "none", "refractor"})
    _xp_has_case_hit = bool(_xp_re.search(r"\b(kaboom|downtown|color\s*blast|case\s*hit|national\s*treasures|immaculate|flawless|spectra)\b", _xp_title_lc)) if _xp_title_lc else False
    _xp_premium_card = bool(_xp_has_serial or _xp_has_auto or _xp_is_psa10 or _xp_is_premium_parallel or _xp_has_case_hit)
    _xp_heat = _safe_float(_normalized.get("whatnot_heat_score")) or 0.0
    _xp_desire = _safe_float(_normalized.get("desirability_score")) or 0.0
    _xp_commercial = str(_normalized.get("commercial_bucket") or "").strip().upper()
    _xp_premium_player = bool(_xp_heat >= 50.0 or _xp_desire >= 50.0 or _xp_commercial in {"STRONG", "ELITE"})
    _xp_match_status = str(_normalized.get("target_match_status") or _normalized.get("entity_match_status") or "").strip().lower()
    _xp_clean_identity = bool(
        _normalized.get("identity_is_clean")
        or _normalized.get("_hydrated_identity_is_clean")
        or _normalized.get("_identity_is_clean")
        or _xp_match_status in {"exact_valid", "exact", "strong_match", "premium_soft_valid"}
    )
    _xp_conflicting = bool(
        _normalized.get("comp_quality_conflict")
        or _normalized.get("mv_conflict_flag")
        or _normalized.get("_weak_base_truth_block")
        or _normalized.get("identity_not_clean")
        or _normalized.get("_identity_not_clean")
        or _normalized.get("comp_disagreement")
        or _normalized.get("contaminated_comps")
    )
    # Edge floor: a strong card whose current price has crept ≤15% above the
    # comp-derived target is still snipe-eligible at target-bid price. Beyond
    # 15% over target the card is truly overpriced even on premium identity.
    _xp_edge_within_floor = bool(_edge_pct is not None and _edge_pct >= -15.0)
    _xp_promo_eligible = bool(
        _target_bid_ready
        and _has_mv
        and _xp_exact >= 1
        and _xp_premium_card
        and _xp_premium_player
        and _xp_clean_identity
        and not _xp_conflicting
        and _xp_edge_within_floor
    )
    # Trace why a near-miss didn't promote — names the exact gate that blocked.
    _xp_block_reasons: List[str] = []
    if not _target_bid_ready:
        _xp_block_reasons.append("target_bid_not_ready")
    if not _has_mv:
        _xp_block_reasons.append("no_market_value")
    if _xp_exact < 1:
        _xp_block_reasons.append(f"zero_exact_comps:exact={_xp_exact}")
    if not _xp_premium_card:
        _xp_block_reasons.append("not_premium_card_structure")
    if not _xp_premium_player:
        _xp_block_reasons.append(f"not_premium_player:heat={_xp_heat:.0f},commercial={_xp_commercial}")
    if not _xp_clean_identity:
        _xp_block_reasons.append("not_clean_identity")
    if _xp_conflicting:
        _xp_block_reasons.append("conflicting_comps")
    if not _xp_edge_within_floor:
        _xp_block_reasons.append(f"edge_below_floor:edge_pct={round(float(_edge_pct), 2) if _edge_pct is not None else 'na'}")
    # ────────────────────────────────────────────────────────────────────────

    # ── RARE_EXACT_OVERRIDE precondition ────────────────────────────────────
    # Rare premium inventory often has exactly ONE clean exact comp because
    # the population itself is tiny (numbered ≤ /250 of premium players on
    # premium products). The standard gates require ≥2 comps, so these cards
    # collapse to "unconfirmed value / monitor" even though the single exact
    # is trustworthy. This override lifts ONLY rows that prove rarity AND
    # premium identity AND clean exact-match confidence AND no conflicting
    # comps. It never lets weak/base/junk through.
    import re as _reo_re
    _reo_exact = int(
        _safe_float(_normalized.get("trusted_exact_comp_count"))
        or _safe_float(_normalized.get("exact_comp_count"))
        or _safe_float(_normalized.get("raw_exact_match_count"))
        or 0
    )
    _reo_serial_raw = str(
        _normalized.get("serial_denominator")
        or _normalized.get("_hydrated_serial_denominator")
        or _normalized.get("serial")
        or ""
    ).strip()
    try:
        _reo_serial_n = int(_reo_serial_raw) if _reo_serial_raw and _reo_serial_raw.isdigit() else None
    except Exception:
        _reo_serial_n = None
    _reo_is_rare_serial = bool(
        _reo_serial_n is not None
        and 0 < _reo_serial_n <= 250
    )
    _reo_heat = _safe_float(_normalized.get("whatnot_heat_score")) or 0.0
    _reo_desire = _safe_float(_normalized.get("desirability_score")) or 0.0
    _reo_commercial = str(_normalized.get("commercial_bucket") or "").strip().upper()
    _reo_premium_player = bool(
        _reo_heat >= 50.0 or _reo_desire >= 50.0 or _reo_commercial in {"STRONG", "ELITE"}
    )
    _reo_product_lc = str(
        _normalized.get("product_family")
        or _normalized.get("identity_product_family")
        or _normalized.get("_hydrated_product_family")
        or _normalized.get("target_product_family")
        or _normalized.get("lane_product")
        or _normalized.get("_target_product_canonical")
        or ""
    ).strip().lower()
    _REO_PREMIUM_PRODUCTS = {
        "panini select", "panini prizm", "panini chronicles", "panini optic",
        "donruss optic", "panini mosaic", "panini contenders",
        "national treasures", "flawless", "immaculate", "spectra",
        "topps chrome", "bowman chrome", "bowman draft", "bowman's best",
        "bowman platinum", "topps gilded", "topps gold label",
        "panini one", "panini one and one", "panini obsidian",
        "panini noir", "panini origins", "panini limited",
        "select", "prizm", "optic", "mosaic", "chrome",
    }
    _reo_is_premium_product = bool(
        _reo_product_lc and any(_p in _reo_product_lc for _p in _REO_PREMIUM_PRODUCTS)
    )
    _reo_match_status = str(
        _normalized.get("target_match_status")
        or _normalized.get("entity_match_status")
        or ""
    ).strip().lower()
    _reo_route_stage = str(_normalized.get("route_stage") or _normalized.get("_route_stage") or "").strip().lower()
    _reo_exact_identity = bool(
        _reo_match_status in {"exact_valid", "exact", "strong_match"}
        or _reo_route_stage in {"tracked_exact", "exact_match"}
        or bool(_normalized.get("_trusted_target_routed"))
        or bool(_normalized.get("identity_is_clean") or _normalized.get("_hydrated_identity_is_clean"))
    )
    _reo_conflicting = bool(
        _normalized.get("comp_quality_conflict")
        or _normalized.get("mv_conflict_flag")
        or _normalized.get("_mv_conflict")
        or _normalized.get("_weak_base_truth_block")
        or _normalized.get("identity_not_clean")
        or _normalized.get("_identity_not_clean")
        or _normalized.get("comp_disagreement")
        or _normalized.get("_comp_outlier_flag")
        or _normalized.get("contaminated_comps")
    )
    _reo_true_mv = _safe_float(
        _normalized.get("true_mv")
        or _normalized.get("true_market_value")
        or _normalized.get("market_value_true")
    )
    _reo_review = _safe_float(
        _normalized.get("review_estimate")
        or _normalized.get("review")
        or _normalized.get("review_estimate_value")
    )
    _reo_anchor_value = _reo_true_mv if (_reo_true_mv is not None and _reo_true_mv > 0) else _reo_review
    _reo_eligible = bool(
        _reo_exact == 1
        and _reo_is_rare_serial
        and _reo_premium_player
        and _reo_is_premium_product
        and _reo_exact_identity
        and not _reo_conflicting
        and _reo_anchor_value is not None
        and _reo_anchor_value > 0
    )
    # ────────────────────────────────────────────────────────────────────────

    # ── RARE_RESEARCH_PRICING precondition ──────────────────────────────────
    # Ultra-rare cards (≤ /99) of elite players on premium products that
    # naturally have NO clean exact comp. The standard exact / RARE_EXACT
    # paths cannot fire because exact_comp_count == 0 (or too thin to trust),
    # so without this layer they collapse into HIGH_HEAT_RESEARCH with no
    # actionable bid. This layer reads ONLY what the engine has already
    # surfaced on the row — review_estimate (structured fallback from cohort /
    # adjacent comps), mv_value (raw market value if present), and any
    # support comps the engine already counted — and produces a LOW-confidence
    # exploratory bid range. Does not modify exact-comp logic, RARE_EXACT
    # logic, sniper thresholds, board ranking, or UI layout.
    _rrp_exact = int(
        _safe_float(_normalized.get("trusted_exact_comp_count"))
        or _safe_float(_normalized.get("exact_comp_count"))
        or _safe_float(_normalized.get("raw_exact_match_count"))
        or 0
    )
    _rrp_support = int(
        _safe_float(_normalized.get("support_comp_count"))
        or _safe_float(_normalized.get("support_count"))
        or 0
    )
    _rrp_serial_raw = str(
        _normalized.get("serial_denominator")
        or _normalized.get("_hydrated_serial_denominator")
        or _normalized.get("serial")
        or ""
    ).strip()
    try:
        _rrp_serial_n = int(_rrp_serial_raw) if _rrp_serial_raw and _rrp_serial_raw.isdigit() else None
    except Exception:
        _rrp_serial_n = None
    _rrp_is_ultra_rare_serial = bool(_rrp_serial_n is not None and 0 < _rrp_serial_n <= 99)
    _rrp_heat = _safe_float(_normalized.get("whatnot_heat_score")) or 0.0
    _rrp_desire = _safe_float(_normalized.get("desirability_score")) or 0.0
    _rrp_commercial = str(_normalized.get("commercial_bucket") or "").strip().upper()
    # Stricter than RARE_EXACT_OVERRIDE: elite player only — heat ≥ 65 OR
    # commercial bucket ELITE OR desirability ≥ 65. We are pricing without an
    # exact comp, so the player demand floor must be high.
    _rrp_elite_player = bool(
        _rrp_heat >= 65.0 or _rrp_desire >= 65.0 or _rrp_commercial == "ELITE"
    )
    _rrp_product_lc = str(
        _normalized.get("product_family")
        or _normalized.get("identity_product_family")
        or _normalized.get("_hydrated_product_family")
        or _normalized.get("target_product_family")
        or _normalized.get("lane_product")
        or _normalized.get("_target_product_canonical")
        or ""
    ).strip().lower()
    _RRP_PREMIUM_PRODUCTS = {
        "panini select", "panini prizm", "panini chronicles", "panini optic",
        "donruss optic", "panini mosaic", "panini contenders",
        "national treasures", "flawless", "immaculate", "spectra",
        "topps chrome", "bowman chrome", "bowman draft", "bowman's best",
        "bowman platinum", "topps gilded", "topps gold label",
        "panini one", "panini one and one", "panini obsidian",
        "panini noir", "panini origins", "panini limited",
        "select", "prizm", "optic", "mosaic", "chrome",
    }
    _rrp_is_premium_product = bool(
        _rrp_product_lc and any(_p in _rrp_product_lc for _p in _RRP_PREMIUM_PRODUCTS)
    )
    _rrp_match_status = str(
        _normalized.get("target_match_status")
        or _normalized.get("entity_match_status")
        or ""
    ).strip().lower()
    _rrp_clean_identity = bool(
        _normalized.get("identity_is_clean")
        or _normalized.get("_hydrated_identity_is_clean")
        or _normalized.get("_identity_is_clean")
        or _rrp_match_status in {"exact_valid", "exact", "strong_match", "premium_soft_valid"}
    )
    _rrp_conflicting = bool(
        _normalized.get("comp_quality_conflict")
        or _normalized.get("mv_conflict_flag")
        or _normalized.get("_mv_conflict")
        or _normalized.get("_weak_base_truth_block")
        or _normalized.get("identity_not_clean")
        or _normalized.get("_identity_not_clean")
        or _normalized.get("comp_disagreement")
        or _normalized.get("_comp_outlier_flag")
        or _normalized.get("contaminated_comps")
    )
    # Anchors — engine has already harvested adjacent serial / adjacent grade /
    # same-product / same-player-auto signals into these fields upstream. We
    # only read them; we never trigger new comp searches here.
    _rrp_review = _safe_float(
        _normalized.get("review_estimate")
        or _normalized.get("review")
        or _normalized.get("review_estimate_value")
    )
    _rrp_mv = _safe_float(
        _normalized.get("mv_value")
        or _normalized.get("market_value_raw")
        or _normalized.get("market_value")
    )
    _rrp_true_mv = _safe_float(
        _normalized.get("true_mv")
        or _normalized.get("true_market_value")
        or _normalized.get("market_value_true")
    )
    # Build comp-source list: which signals the engine already populated.
    _rrp_comp_sources: List[Dict[str, Any]] = []
    if _rrp_review is not None and _rrp_review > 0:
        _rrp_comp_sources.append({
            "source": "review_estimate_anchor",
            "value": float(_rrp_review),
            "kind": "structured_fallback",
        })
    if _rrp_mv is not None and _rrp_mv > 0 and (_rrp_review is None or abs(_rrp_mv - (_rrp_review or 0)) > 0.01):
        _rrp_comp_sources.append({
            "source": "mv_value_anchor",
            "value": float(_rrp_mv),
            "kind": "raw_market_value",
        })
    if _rrp_true_mv is not None and _rrp_true_mv > 0:
        _rrp_comp_sources.append({
            "source": "true_mv_anchor",
            "value": float(_rrp_true_mv),
            "kind": "engine_resolved",
        })
    # Adjacent serial / adjacent grade / same-product lower-rarity / same-
    # player auto indicators stamped by the engine if available.
    for _adj_field, _adj_kind in (
        ("adjacent_serial_value", "adjacent_serial_comp"),
        ("adjacent_grade_value", "adjacent_grade_comp"),
        ("same_product_lower_rarity_value", "same_product_lower_rarity_comp"),
        ("same_player_auto_value", "same_player_auto_comp"),
        ("cohort_value", "cohort_comp"),
        ("hybrid_mv_value", "hybrid_mv"),
    ):
        _adj = _safe_float(_normalized.get(_adj_field))
        if _adj is not None and _adj > 0:
            _rrp_comp_sources.append({
                "source": _adj_field,
                "value": float(_adj),
                "kind": _adj_kind,
            })
    # Use support count as evidence of adjacent comps even when no value field
    # is exposed: if support_comp_count >= 2, count it as an adjacent signal
    # but only as a confidence boost, not as a price anchor on its own.
    _rrp_support_evidence = bool(_rrp_support >= 2)
    _rrp_has_anchor = len(_rrp_comp_sources) > 0
    _rrp_thin_exact = bool(_rrp_exact == 0 or (_rrp_exact == 1 and _rrp_conflicting))
    _rrp_eligible = bool(
        _rrp_thin_exact
        and _rrp_is_ultra_rare_serial
        and _rrp_elite_player
        and _rrp_is_premium_product
        and _rrp_clean_identity
        and not _rrp_conflicting
        and _rrp_has_anchor
    )
    # ────────────────────────────────────────────────────────────────────────

    # ── research_bid_ready precondition ─────────────────────────────────────
    # Middle bucket between action_ready and monitor for high-upside imperfect
    # inventory: row has at least one exact comp + two support comps, the
    # review estimate beats the live current price, and the row is either a
    # premium player or carries premium-card structure (auto, serial, PSA 10,
    # premium parallel, named case hit). confidence may stay low/medium and
    # truth_level may stay REVIEW — the row is research-grade, not verified.
    import re as _rbr_re
    _rbr_exact = int(
        _safe_float(_normalized.get("trusted_exact_comp_count"))
        or _safe_float(_normalized.get("exact_comp_count"))
        or _safe_float(_normalized.get("raw_exact_match_count"))
        or 0
    )
    _rbr_support = int(
        _safe_float(_normalized.get("support_comp_count"))
        or _safe_float(_normalized.get("support_count"))
        or 0
    )
    _rbr_review = _safe_float(
        _normalized.get("review_estimate")
        or _normalized.get("review")
        or _normalized.get("review_estimate_value")
    )
    _rbr_current = _safe_float(_normalized.get("current_price")) or _safe_float(_normalized.get("current_bid")) or 0.0
    _rbr_heat = _safe_float(_normalized.get("whatnot_heat_score")) or 0.0
    _rbr_desire = _safe_float(_normalized.get("desirability_score")) or 0.0
    _rbr_commercial = str(_normalized.get("commercial_bucket") or "").strip().upper()
    _rbr_premium_player = bool(
        _rbr_heat >= 50.0 or _rbr_desire >= 50.0 or _rbr_commercial in {"STRONG", "ELITE"}
    )
    _rbr_title_lc = str(_normalized.get("title") or _normalized.get("source_title") or "").lower()
    _rbr_serial_raw = str(
        _normalized.get("serial_denominator")
        or _normalized.get("_hydrated_serial_denominator")
        or _normalized.get("serial")
        or ""
    ).strip()
    _rbr_has_serial = bool(_rbr_serial_raw and _rbr_serial_raw.lower() not in {"0", "none", ""})
    _rbr_has_auto = bool(_rbr_re.search(r"\b(auto|autograph)\b", _rbr_title_lc)) if _rbr_title_lc else False
    _rbr_grade_uc = str(_normalized.get("grade") or _normalized.get("grade_label") or "").strip().upper()
    _rbr_is_psa10 = ("PSA 10" in _rbr_grade_uc) or ("PSA10" in _rbr_grade_uc) or ("BGS 9.5" in _rbr_grade_uc) or ("BGS 10" in _rbr_grade_uc)
    _rbr_parallel_lc = str(
        _normalized.get("parallel_family")
        or _normalized.get("_hydrated_parallel_family")
        or _normalized.get("parallel_name")
        or _normalized.get("parallel")
        or ""
    ).strip().lower()
    _rbr_is_premium_parallel = bool(
        _rbr_parallel_lc and _rbr_parallel_lc not in {"base", "common", "none", "refractor"}
    )
    _rbr_has_case_hit = bool(_rbr_re.search(
        r"\b(kaboom|downtown|color\s*blast|case\s*hit|national\s*treasures|immaculate|flawless|spectra)\b",
        _rbr_title_lc,
    )) if _rbr_title_lc else False
    _rbr_premium_card = bool(
        _rbr_has_serial or _rbr_has_auto or _rbr_is_psa10 or _rbr_is_premium_parallel or _rbr_has_case_hit
    )
    _rbr_research_eligible = bool(
        _rbr_exact >= 1
        and _rbr_support >= 2
        and _rbr_review is not None and _rbr_review > 0
        and _rbr_current > 0
        and _rbr_review > _rbr_current
        and (_rbr_premium_player or _rbr_premium_card)
    )
    # ────────────────────────────────────────────────────────────────────────

    if _forced_surface:
        _bucket = "monitor"
    elif _has_mv and _target_bid_ready and (
        (_has_comp_support and _has_confidence_support)
        or _comp_count >= 2
        or (_has_confidence_support and not _weak_source)
        or _quality_state == "execution_ready"
        or _xp_promo_eligible    # PREMIUM EXECUTION-PROMOTION bypass
    ) and (
        _edge_pct >= 0
        or _quality_state == "execution_ready"
        or _deal_class_ready
        or _xp_promo_eligible    # PREMIUM EXECUTION-PROMOTION bypass
    ):
        _bucket = "action_ready"
        if _xp_promo_eligible and not (
            ((_has_comp_support and _has_confidence_support) or _comp_count >= 2 or (_has_confidence_support and not _weak_source) or _quality_state == "execution_ready")
            and (_edge_pct >= 0 or _quality_state == "execution_ready" or _deal_class_ready)
        ):
            # Promotion was the deciding factor — log SNIPE/PREPARE trace.
            try:
                _xp_rem = _safe_float(_normalized.get("remaining_seconds") or _normalized.get("seconds_remaining"))
                _xp_in_snipe_window = bool(_xp_rem is not None and 0 <= _xp_rem <= 10800.0)
                _xp_in_prepare_window = bool(_xp_rem is not None and 10800.0 < _xp_rem <= 86400.0)
                _xp_title_log = str(_normalized.get("title") or _normalized.get("source_title") or "")[:160]
                _xp_promo_reason = (
                    f"premium_player_heat:{_xp_heat:.0f},"
                    f"exact:{_xp_exact},"
                    f"target_bid_ready:1,"
                    f"premium_card:1,"
                    f"clean_identity:1,"
                    f"edge_within_floor:1"
                )
                if _xp_in_snipe_window:
                    print(
                        f"[SNIPE_READY_TRACE] title={_xp_title_log} "
                        f"reason=premium_promotion:{_xp_promo_reason}"
                    )
                elif _xp_in_prepare_window:
                    print(
                        f"[PREPARE_READY_TRACE] title={_xp_title_log} "
                        f"reason=premium_promotion:{_xp_promo_reason}"
                    )
                else:
                    print(
                        f"[SNIPE_READY_TRACE] title={_xp_title_log} "
                        f"reason=premium_promotion:no_window:{_xp_promo_reason}"
                    )
            except Exception:
                pass
    elif _reo_eligible:
        _bucket = "rare_exact_override"
        # Stamp trusted_mv, reference_bid, and snipe/watch eligibility ONLY for
        # rows that proved rarity+premium identity+clean exact match. Truth
        # level remains as-is — we are not promoting to EXACT/EXACT_RESCUE.
        if isinstance(_normalized, dict):
            _normalized["_rare_exact_override"] = True
            _normalized["rare_exact_override"] = True
            _normalized["rare_exact_override_reason"] = (
                f"single_trusted_exact_serial/{_reo_serial_n or _reo_serial_raw}_"
                f"premium_player_premium_product"
            )
            # trusted_mv anchored on the single exact comp's value (true_mv if
            # already set, else review_estimate which the engine derived from
            # that single exact comp).
            _normalized["trusted_mv"] = float(_reo_anchor_value)
            _normalized["_trusted_mv_source"] = "rare_exact_override"
            # reference_bid = 70% of trusted_mv (conservative single-comp anchor)
            _reo_reference_bid = round(float(_reo_anchor_value) * 0.70, 2)
            _normalized["reference_bid"] = _reo_reference_bid
            _normalized["_reference_bid_source"] = "rare_exact_override"
            # Snipe/watch eligibility: target_bid_ready=True with MEDIUM
            # confidence (single comp can never be HIGH).
            _normalized["target_bid_ready"] = True
            if str(_normalized.get("target_bid_confidence") or "").strip().upper() in {"NONE", "REVIEW", ""}:
                _normalized["target_bid_confidence"] = "MEDIUM"
            if str(_normalized.get("bid_ceiling_confidence") or "").strip().upper() in {"NONE", "REVIEW", ""}:
                _normalized["bid_ceiling_confidence"] = "MEDIUM"
            if not _safe_float(_normalized.get("target_bid_price")):
                _normalized["target_bid_price"] = _reo_reference_bid
            if not _safe_float(_normalized.get("bid_ceiling_value")):
                _normalized["bid_ceiling_value"] = _reo_reference_bid
            _normalized["_target_bid_source"] = str(_normalized.get("_target_bid_source") or "rare_exact_override")
            _normalized["board_visible"] = True
            _normalized["commercially_visible"] = True
        try:
            print(
                f"[RARE_EXACT_OVERRIDE] "
                f"title={str(_normalized.get('title') or _normalized.get('source_title') or '')[:160]} "
                f"player={str(_normalized.get('player_name') or _normalized.get('canonical_player') or '')[:48]} "
                f"product={str(_normalized.get('product_family') or _normalized.get('lane_product') or '')[:48]} "
                f"serial={_reo_serial_raw} "
                f"exact={_reo_exact} "
                f"trusted_mv={round(float(_reo_anchor_value), 2)} "
                f"reference_bid={round(float(_reo_anchor_value) * 0.70, 2)} "
                f"premium_player={1 if _reo_premium_player else 0} "
                f"premium_product={1 if _reo_is_premium_product else 0} "
                f"exact_identity={1 if _reo_exact_identity else 0} "
                f"conflicts={1 if _reo_conflicting else 0}"
            )
        except Exception:
            pass
    elif _rbr_research_eligible:
        _bucket = "research_bid_ready"
        _rbr_spread_pct = ((_rbr_review - _rbr_current) / _rbr_current) * 100.0 if _rbr_current > 0 else 0.0
        # Stamp non-destructive helper fields so downstream consumers can show
        # a clearly-labeled "Suggested Research Bid" without ever claiming
        # verified value / true MV / sniper lock.
        if isinstance(_normalized, dict):
            _normalized["_research_bid_ready"] = True
            _normalized["research_bid_ready"] = True
            _normalized["research_bid_label"] = "Suggested Research Bid"
            _normalized["research_bid_value"] = float(_rbr_review)
            _normalized["research_bid_reference"] = float(_rbr_review)
            _normalized["research_bid_spread_pct"] = round(_rbr_spread_pct, 2)
            _normalized["research_bid_current_price"] = float(_rbr_current)
            _normalized["research_bid_exact_comp_count"] = int(_rbr_exact)
            _normalized["research_bid_support_comp_count"] = int(_rbr_support)
            _rbr_reason_parts: List[str] = []
            if _rbr_premium_player:
                _rbr_reason_parts.append("premium_player")
            if _rbr_has_auto:
                _rbr_reason_parts.append("auto")
            if _rbr_has_serial:
                _rbr_reason_parts.append(f"serial/{_rbr_serial_raw}")
            if _rbr_is_psa10:
                _rbr_reason_parts.append("psa10")
            if _rbr_is_premium_parallel:
                _rbr_reason_parts.append("premium_parallel")
            if _rbr_has_case_hit:
                _rbr_reason_parts.append("case_hit")
            _rbr_reason = ",".join(_rbr_reason_parts) or "comps_plus_review_estimate_above_current"
            _normalized["research_bid_reason"] = _rbr_reason
        else:
            _rbr_reason = "comps_plus_review_estimate_above_current"
        try:
            print(
                f"[RESEARCH_BID_READY] "
                f"title={str(_normalized.get('title') or _normalized.get('source_title') or '')[:160]} "
                f"current_price={round(_rbr_current, 2)} "
                f"review_estimate={round(_rbr_review, 2)} "
                f"exact={_rbr_exact} "
                f"support={_rbr_support} "
                f"reason={_rbr_reason}"
            )
        except Exception:
            pass
    elif _rrp_eligible:
        _bucket = "rare_research_pricing"
        # Build research_value_low / research_value_high from the harvested
        # anchors. Use the median of anchors as a center, then expand by ±25%
        # (or wider if anchors disagree) to bound research uncertainty.
        _rrp_anchor_values = sorted(float(_s.get("value") or 0.0) for _s in _rrp_comp_sources if _s.get("value"))
        _rrp_anchor_count = len(_rrp_anchor_values)
        if _rrp_anchor_count == 1:
            _rrp_center = _rrp_anchor_values[0]
            _rrp_low = round(_rrp_center * 0.75, 2)
            _rrp_high = round(_rrp_center * 1.25, 2)
        else:
            # Median across anchors; range bounded by min/max with safety pad.
            _rrp_center = _rrp_anchor_values[_rrp_anchor_count // 2]
            _rrp_min_anchor = _rrp_anchor_values[0]
            _rrp_max_anchor = _rrp_anchor_values[-1]
            _rrp_low = round(min(_rrp_center * 0.75, _rrp_min_anchor * 0.85), 2)
            _rrp_high = round(max(_rrp_center * 1.25, _rrp_max_anchor * 1.10), 2)
        # Exploratory max bid — deliberately conservative because a single
        # missing exact comp is a real pricing risk. 50% of the LOW anchor.
        _rrp_exploratory_max = round(_rrp_low * 0.50, 2)
        # Pricing reason — comma-joined source list + flags.
        _rrp_pricing_reason_parts: List[str] = [str(_s.get("source") or "") for _s in _rrp_comp_sources if _s.get("source")]
        if _rrp_support_evidence:
            _rrp_pricing_reason_parts.append(f"support_evidence:{_rrp_support}")
        if _rrp_serial_n is not None:
            _rrp_pricing_reason_parts.append(f"ultra_rare_serial/{_rrp_serial_n}")
        _rrp_pricing_reason_parts.append(f"premium_player_heat:{round(_rrp_heat, 1)}")
        _rrp_pricing_reason = ",".join(_p for _p in _rrp_pricing_reason_parts if _p)
        if isinstance(_normalized, dict):
            _normalized["_rare_research_pricing"] = True
            _normalized["rare_research_pricing"] = True
            _normalized["research_value_low"] = float(_rrp_low)
            _normalized["research_value_high"] = float(_rrp_high)
            _normalized["research_value_center"] = float(round(_rrp_center, 2))
            _normalized["exploratory_max_bid"] = float(_rrp_exploratory_max)
            _normalized["pricing_confidence"] = "LOW"
            _normalized["pricing_reason"] = _rrp_pricing_reason
            _normalized["rare_research_anchor_count"] = int(_rrp_anchor_count)
            _normalized["rare_research_comp_sources"] = list(_rrp_comp_sources)
            _normalized["board_visible"] = True
            _normalized["commercially_visible"] = True
        try:
            for _src in _rrp_comp_sources:
                print(
                    f"[RARE_RESEARCH_COMP_SOURCE] "
                    f"title={str(_normalized.get('title') or _normalized.get('source_title') or '')[:120]} "
                    f"source={_src.get('source')} "
                    f"kind={_src.get('kind')} "
                    f"value={round(float(_src.get('value') or 0.0), 2)}"
                )
            print(
                f"[RARE_RESEARCH_PRICING] "
                f"title={str(_normalized.get('title') or _normalized.get('source_title') or '')[:160]} "
                f"player={str(_normalized.get('player_name') or _normalized.get('canonical_player') or '')[:48]} "
                f"product={str(_normalized.get('product_family') or _normalized.get('lane_product') or '')[:48]} "
                f"serial={_rrp_serial_raw} "
                f"exact={_rrp_exact} "
                f"support={_rrp_support} "
                f"anchors={_rrp_anchor_count} "
                f"research_value_low={_rrp_low} "
                f"research_value_high={_rrp_high} "
                f"confidence=LOW "
                f"reason={_rrp_pricing_reason}"
            )
            print(
                f"[RARE_RESEARCH_BID] "
                f"title={str(_normalized.get('title') or _normalized.get('source_title') or '')[:160]} "
                f"exploratory_max_bid={_rrp_exploratory_max} "
                f"research_value_low={_rrp_low} "
                f"research_value_high={_rrp_high} "
                f"confidence=LOW "
                f"reason={_rrp_pricing_reason}"
            )
        except Exception:
            pass
    elif str(_live_signal.get("live_signal_tier") or "") in {"family_valid", "promoted"} and (_has_mv or _target_bid_ready or _has_confidence_support or _has_comp_support):
        _bucket = "monitor"
    elif _has_mv or _target_bid_ready or _has_comp_support or _has_confidence_support or _quality_state in {"execution_ready", "monitor_only"}:
        _bucket = "monitor"
    else:
        _bucket = "suppressed"

    # ── EXECUTION_PROMOTION_BLOCK — observability for near-miss promotions ─
    # Fires when a row landed in monitor/research/suppressed despite carrying
    # at least target_bid_ready + premium_card + premium_player. Names the
    # exact gate(s) blocking promotion so the bottleneck is visible per row.
    if _bucket != "action_ready" and _xp_block_reasons and (_target_bid_ready or _xp_premium_card or _xp_premium_player):
        try:
            print(
                f"[EXECUTION_PROMOTION_BLOCK] "
                f"title={str(_normalized.get('title') or _normalized.get('source_title') or '')[:160]} "
                f"reason={','.join(_xp_block_reasons)}"
            )
        except Exception:
            pass
    # ────────────────────────────────────────────────────────────────────────

    # ── COMP_CONFIDENCE_TRACE — observability only ─────────────────────────
    # Per-row trace of why a row landed in monitor / suppressed instead of
    # action_ready. Reads existing fields, never modifies them.
    try:
        _ccc_title = str(_normalized.get("title") or _normalized.get("source_title") or "")[:160]
        _ccc_player = str(
            _normalized.get("player_name")
            or _normalized.get("canonical_player")
            or _normalized.get("normalized_entity")
            or _normalized.get("_target_player")
            or ""
        )[:48]
        _ccc_product = str(
            _normalized.get("product_family")
            or _normalized.get("identity_product_family")
            or _normalized.get("_hydrated_product_family")
            or _normalized.get("target_product_family")
            or _normalized.get("lane_product")
            or ""
        )[:48]
        _ccc_parallel = str(
            _normalized.get("parallel_family")
            or _normalized.get("_hydrated_parallel_family")
            or _normalized.get("parallel_name")
            or _normalized.get("parallel")
            or ""
        )[:32]
        _ccc_serial = str(
            _normalized.get("serial_denominator")
            or _normalized.get("_hydrated_serial_denominator")
            or _normalized.get("serial")
            or ""
        )[:24]
        _ccc_grade = str(_normalized.get("grade") or _normalized.get("grade_label") or "")[:24]
        _ccc_exact = int(
            _safe_float(_normalized.get("trusted_exact_comp_count"))
            or _safe_float(_normalized.get("exact_comp_count"))
            or _safe_float(_normalized.get("raw_exact_match_count"))
            or 0
        )
        _ccc_support = int(
            _safe_float(_normalized.get("support_comp_count"))
            or _safe_float(_normalized.get("support_count"))
            or 0
        )
        _ccc_fallback_used = bool(
            _normalized.get("_research_only_price_check")
            or _normalized.get("fallback_window")
            or _normalized.get("_fallback_window_used")
            or _normalized.get("structured_fallback_used")
            or str(_normalized.get("mv_source") or "").strip().lower() in {"structured_fallback", "fallback"}
        )
        _ccc_true_mv = _safe_float(
            _normalized.get("true_mv")
            or _normalized.get("true_market_value")
            or _normalized.get("market_value_true")
        )
        _ccc_review_est = _safe_float(
            _normalized.get("review_estimate")
            or _normalized.get("review")
            or _normalized.get("review_estimate_value")
        )
        _ccc_truth_level = str(_normalized.get("valuation_truth_level") or _normalized.get("truth") or _normalized.get("valuation_truth_tier") or "NONE").strip().upper() or "NONE"
        _ccc_conf_tier = str(_confidence_tier or "unknown")
        _ccc_target_bid_conf = str(
            _normalized.get("bid_ceiling_confidence")
            or _normalized.get("target_bid_confidence")
            or "NONE"
        ).strip().upper()
        _ccc_failures: List[str] = []
        if not _has_mv:
            _ccc_failures.append("no_market_value")
        if not _target_bid_ready:
            _ccc_failures.append("target_bid_not_ready")
        if not _has_comp_support and _ccc_exact == 0 and _ccc_support == 0:
            _ccc_failures.append("zero_comps")
        elif _comp_count < 2 and not _has_confidence_support and _quality_state != "execution_ready":
            _ccc_failures.append(f"comp_count_below_2:{_comp_count}")
        if not _has_confidence_support:
            _ccc_failures.append(f"confidence_below_medium:{_ccc_conf_tier}")
        if _weak_source:
            _ccc_failures.append(f"weak_mv_source:{_normalized.get('mv_source')}")
        if _edge_pct < 0 and _quality_state != "execution_ready" and not _deal_class_ready:
            _ccc_failures.append(f"edge_pct_negative:{round(_edge_pct, 2)}")
        if _deal_class not in {"ELITE", "STRONG", "GOOD"} and _quality_state != "execution_ready":
            _ccc_failures.append(f"deal_class_weak:{_deal_class}")
        if _ccc_target_bid_conf in {"NONE", "REVIEW"} and _bucket != "action_ready":
            _ccc_failures.append(f"target_bid_confidence:{_ccc_target_bid_conf}")
        if _ccc_truth_level not in {"EXACT", "EXACT_RESCUE", "SUPPORT"} and _bucket != "action_ready":
            _ccc_failures.append(f"truth_level:{_ccc_truth_level}")
        _ccc_failure_reason = ",".join(_ccc_failures) if _ccc_failures else (
            "action_ready" if _bucket == "action_ready" else _bucket
        )
        print(
            f"[COMP_CONFIDENCE_TRACE] "
            f"title={_ccc_title} "
            f"player={_ccc_player} "
            f"product={_ccc_product} "
            f"parallel={_ccc_parallel} "
            f"serial={_ccc_serial} "
            f"grade={_ccc_grade} "
            f"exact_comp_count={_ccc_exact} "
            f"support_comp_count={_ccc_support} "
            f"fallback_used={1 if _ccc_fallback_used else 0} "
            f"true_mv={(round(_ccc_true_mv, 2) if _ccc_true_mv is not None else 'na')} "
            f"review_estimate={(round(_ccc_review_est, 2) if _ccc_review_est is not None else 'na')} "
            f"confidence={_ccc_conf_tier} "
            f"truth_level={_ccc_truth_level} "
            f"target_bid_confidence={_ccc_target_bid_conf} "
            f"bucket={_bucket} "
            f"failure_reason={_ccc_failure_reason}"
        )
    except Exception as _ccc_exc:
        print(f"[COMP_CONFIDENCE_TRACE] error_type={type(_ccc_exc).__name__} msg={str(_ccc_exc)[:120]}")
    # ────────────────────────────────────────────────────────────────────────

    return {
        "bucket": _bucket,
        "has_market_value": _has_mv,
        "has_comp_support": _has_comp_support,
        "confidence_tier": _confidence_tier,
        "target_bid_ready": _target_bid_ready,
        "target_bid_price": _target_bid_fields.get("target_bid_price"),
        "target_bid_source": _target_bid_fields.get("target_bid_source"),
        "target_bid_pct_used": _target_bid_fields.get("target_bid_pct_used"),
        "comp_count": _comp_count,
        "deal_class": _deal_class,
        "edge_pct": _edge_pct,
        "mv_value": _market_value,
        "mv_source": str(_normalized.get("mv_source") or "none"),
        "mv_status_norm": str(_normalized.get("mv_status_norm") or "unknown"),
    }


def _es_visibility_bucket(_row: Dict[str, Any]) -> str:
    _bucket = str(_es_get_valuation_readiness(_row).get("bucket") or "suppressed")
    return {
        "action_ready": "primary",
        "monitor": "secondary",
        "suppressed": "weak",
    }.get(_bucket, "weak")


def _es_split_primary_vs_secondary_rows(_rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    _primary: List[Dict[str, Any]] = []
    _secondary: List[Dict[str, Any]] = []
    _weak: List[Dict[str, Any]] = []
    for _row in _rows or []:
        _bucket = _es_visibility_bucket(_row)
        if _bucket == "primary":
            _primary.append(_row)
        elif _bucket == "secondary":
            _secondary.append(_row)
        else:
            _weak.append(_row)
    return {"primary": _primary, "secondary": _secondary, "weak": _weak}


def _es_get_suppression_reasons(_row: Dict[str, Any], _view: Optional[Dict[str, Any]] = None) -> List[str]:
    _reasons: List[str] = []
    _floor_reason = str((_row or {}).get("commercial_floor_fail_reason") or "").strip().lower()
    if _floor_reason == "review_equals_current_clone":
        _reasons.append("CLONE VALUE")
    elif _floor_reason == "below_min_price_floor":
        _reasons.append("BELOW PRICE FLOOR")
    elif _floor_reason == "spread_too_thin":
        _reasons.append("THIN SPREAD")
    _readiness = _es_get_valuation_readiness(_row)
    _market_value = _safe_float(_row.get("market_value")) or 0.0
    _comp_count = int(_readiness.get("comp_count") or 0)
    _edge_pct = _safe_float(_row.get("edge_pct")) or _safe_float(_row.get("edge_percent"))
    _confidence = str(_readiness.get("confidence_tier") or "").strip().lower()
    _quality_state = str(_row.get("row_quality_state") or "").strip().lower()
    _action = str((_view or {}).get("action_label") or _row.get("action_label") or "").strip().upper()
    _target_bid = ((_view or {}).get("target_bid_price") if isinstance(_view, dict) else _readiness.get("target_bid_price"))
    if _market_value <= 0:
        _reasons.append("No usable market value")
    if _comp_count <= 0:
        _reasons.append("No comp support")
    if _edge_pct is not None and _edge_pct < 0:
        _reasons.append("Negative edge")
    if _confidence in {"low", "unknown"}:
        _reasons.append("Low-confidence valuation")
    if _target_bid is None:
        _reasons.append("No valid target bid")
    if _quality_state in {"quarantined", "weak"}:
        _reasons.append("Quality state below threshold")
    if _action in {"PASS", "NO VALID TARGET BID", "NO BID YET"}:
        _reasons.append("Pass-tier action only")
    if not _reasons:
        _reasons.append("Below current decision threshold")
    return _reasons


def _es_scarcity_view(_row: Dict[str, Any]) -> Dict[str, Any]:
    _scarcity_class = str(_row.get("scarcity_class") or "unknown").strip().lower() or "unknown"
    _subset_name = str(_row.get("subset_name") or "").strip()
    _parallel_name = str(_row.get("parallel_name") or _row.get("parallel_bucket") or "").strip()
    _serial_denominator = str(_row.get("serial_denominator") or "").strip()
    _serial_bucket = str(_row.get("serial_bucket") or "").strip()
    _class_label = {
        "ssp_insert": "SSP INSERT",
        "serial_numbered": "SERIAL",
        "parallel": "PARALLEL",
        "base": "BASE",
        "unknown": "UNKNOWN",
    }.get(_scarcity_class, _scarcity_class.replace("_", " ").upper())
    _detail_label = _subset_name or _parallel_name
    if _detail_label:
        _detail_label = _detail_label.replace("_", " ").title()
    _serial_label = f"/{_serial_denominator}" if _serial_denominator else ""
    _bucket_label = _serial_bucket.replace("1_of_1", "1 OF 1").replace("to_", "").replace("_", " ").upper() if _serial_bucket else ""
    if _bucket_label and _bucket_label.isdigit():
        _bucket_label = _bucket_label
    _parts = [_class_label]
    if _detail_label:
        _parts.append(_detail_label)
    if _serial_label:
        _parts.append(_serial_label)
    if _bucket_label:
        _parts.append(_bucket_label)
    return {
        "scarcity_class": _scarcity_class,
        "parts": _parts,
    }


def _es_lane_view(_row: Dict[str, Any]) -> Dict[str, str]:
    _lane_type = str(_row.get("lane_type") or "generic").strip().lower() or "generic"
    _lane_aligned = bool(_row.get("lane_aligned"))
    _lane_label = {
        "subset": "SUBSET LANE",
        "serial": "SERIAL LANE",
        "parallel": "PARALLEL LANE",
        "generic": "GENERIC LANE",
    }.get(_lane_type, f"{_lane_type.replace('_', ' ').upper()} LANE")
    return {
        "lane_type": _lane_type,
        "lane_label": _lane_label,
        "lane_tone": "lane-ok" if _lane_aligned else "lane-fallback",
        "lane_aligned_label": "aligned" if _lane_aligned else "fallback",
    }


def _score_live_signal_origin(_row: Dict[str, Any]) -> Dict[str, Any]:
    _promotion_status = str((_row or {}).get("premium_review_status") or "").strip().lower()
    _promoted = bool(
        (_row or {}).get("promoted_live_candidate")
        or (_row or {}).get("mv_resolved")
        or (_row or {}).get("target_bid_ready")
        or _promotion_status in {"resolved", "partial"}
    )
    if _promoted:
        return {
            "live_signal_tier": "promoted",
            "live_signal_score": 64.0,
            "live_signal_reason": str(
                (_row or {}).get("premium_review_reason")
                or (_row or {}).get("route_reason")
                or "Promoted for premium review from truthful live supply"
            ),
            "origin_badge": "REVIEW RESOLVED" if _promotion_status == "resolved" else "PREMIUM REVIEW" if _promotion_status in {"partial", ""} else "REVIEW FAILED",
            "origin_tone": "green" if _promotion_status == "resolved" else "blue" if _promotion_status in {"partial", ""} else "amber",
        }
    if bool((_row or {}).get("forced_surface")):
        _forced_stage = str((_row or {}).get("forced_surface_stage") or "window_rows").strip().lower() or "window_rows"
        return {
            "live_signal_tier": "forced_surface",
            "live_signal_score": {
                "target_rows": 58.0,
                "parallel_rows": 50.0,
                "product_rows": 44.0,
                "player_rows": 38.0,
                "window_rows": 30.0,
            }.get(_forced_stage, 26.0),
            "live_signal_reason": str((_row or {}).get("forced_surface_reason") or "Premium board empty; showing truthful live candidates."),
            "origin_badge": "RAW LIVE",
            "origin_tone": "amber",
        }
    _route_stage = str((_row or {}).get("route_stage") or "tracked_exact").strip().lower() or "tracked_exact"
    _recovery_stage = str((_row or {}).get("recovery_stage") or "primary").strip().lower() or "primary"
    if _route_stage == "tracked_exact" and _recovery_stage == "primary":
        return {
            "live_signal_tier": "tracked_exact",
            "live_signal_score": 100.0,
            "live_signal_reason": "Exact tracked lane",
            "origin_badge": "EXACT",
            "origin_tone": "green",
        }
    if _route_stage in {"family_valid_fallback", "family_valid_premium"}:
        return {
            "live_signal_tier": "family_valid",
            "live_signal_score": 82.0 if _route_stage == "family_valid_premium" else 72.0,
            "live_signal_reason": "Family-valid premium route" if _route_stage == "family_valid_premium" else "Family-valid live fallback",
            "origin_badge": "FAMILY VALID",
            "origin_tone": "blue",
        }
    if _route_stage == "weak_family_rescue":
        return {
            "live_signal_tier": "recovery",
            "live_signal_score": 38.0,
            "live_signal_reason": "Close match — identity confirmed, variant uncertain",
            "origin_badge": "CLOSE MATCH",
            "origin_tone": "amber",
        }
    if _route_stage == "promoted_live_candidate":
        return {
            "live_signal_tier": "promoted",
            "live_signal_score": 64.0,
            "live_signal_reason": "Promoted for premium review from truthful live supply",
            "origin_badge": "PROMOTED",
            "origin_tone": "blue",
        }
    if _recovery_stage == "discovery_fallback":
        return {
            "live_signal_tier": "recovery",
            "live_signal_score": 24.0,
            "live_signal_reason": "Discovery fallback under thin market",
            "origin_badge": "DISCOVERY",
            "origin_tone": "amber",
        }
    if _recovery_stage in {"tracked_expand", "window_expand"}:
        return {
            "live_signal_tier": "recovery",
            "live_signal_score": 42.0,
            "live_signal_reason": "Recovered from thin exact supply",
            "origin_badge": "RECOVERY",
            "origin_tone": "amber",
        }
    return {
        "live_signal_tier": "recovery",
        "live_signal_score": 18.0,
        "live_signal_reason": "Fallback live signal",
        "origin_badge": "RECOVERY",
        "origin_tone": "muted",
    }


def _es_score_decision_quality(_row: Dict[str, Any]) -> Dict[str, Any]:
    """Compute final decision quality metrics for one Ending Soon auction row.
    Input row must already be strengthened by _es_strengthen_row_valuation.
    Returns: decision_quality_score, execution_readiness, valuation_trust_score,
    signal_tier, quality_reasons, decision_reason, readiness_reason, trust_reason.
    """
    _reasons: List[str] = []
    _trust_reasons: List[str] = []
    _readiness_reasons: List[str] = []

    _mv = _safe_float(_row.get("mv_value")) or _safe_float(_row.get("market_value")) or 0.0
    _comp_count = int((_safe_float(_row.get("mv_comp_count")) or _safe_float(_row.get("comp_count")) or 0))
    _edge_pct = _safe_float(_row.get("edge_pct")) or _safe_float(_row.get("edge_percent")) or 0.0
    _confidence_tier = str(_row.get("valuation_confidence") or "unknown").strip().lower()
    _mv_source = str(_row.get("mv_source") or _row.get("market_value_source") or "none").strip().lower()
    _quality_state = str(_row.get("row_quality_state") or "").strip().lower()
    _lane_aligned = bool(_row.get("lane_aligned"))
    _lane_type = str(_row.get("lane_type") or "generic").strip().lower()
    _recovery_stage = str(_row.get("recovery_stage") or "primary").strip().lower() or "primary"
    _target_bid_ready = bool(_row.get("target_bid_ready"))
    _entity_status = str(_row.get("entity_match_status") or "EXACT_MATCH").strip().upper()
    _lane_tier = str(_row.get("lane_tier") or "primary").strip().lower()
    _secs = _es_time_remaining_seconds(_row)
    if _secs is None:
        _secs = 999999.0
    _insufficient_data = bool(_row.get("insufficient_data", True))
    _deal_class = str(_row.get("deal_class") or "UNKNOWN").strip().upper()
    _weak_source = _mv_source in {"structured_fallback", "none", "error", "listing_type_excluded", "unresolved"}

    # ── Valuation Trust Score (0–100) ───────────────────────────────────────
    _trust = 0.0
    if _mv > 0 and not _insufficient_data:
        _trust += 35.0
        _trust_reasons.append("Market value resolved")
    elif _mv > 0:
        _trust += 12.0
        _trust_reasons.append("Market value present but thin data")
    else:
        _trust_reasons.append("No market value")
    if _confidence_tier == "high":
        _trust += 25.0
        _trust_reasons.append("High-confidence comps")
    elif _confidence_tier == "medium":
        _trust += 14.0
        _trust_reasons.append("Medium-confidence comps")
    else:
        _trust_reasons.append("Low confidence — trust penalty applied")
    if _comp_count >= 5:
        _trust += 20.0
    elif _comp_count >= 3:
        _trust += 12.0
    elif _comp_count >= 1:
        _trust += 6.0
    else:
        _trust_reasons.append("No comp support")
    if not _weak_source and _mv > 0:
        _trust += 10.0
    elif _weak_source:
        _trust -= 15.0
        _trust_reasons.append("Weak valuation source")
    if _quality_state == "execution_ready":
        _trust += 10.0
    elif _quality_state == "quarantined":
        _trust -= 20.0
        _trust_reasons.append("Quarantined by quality gate")
    _valuation_trust_score = max(0.0, min(100.0, _trust))

    # ── Execution Readiness (0–100) ─────────────────────────────────────────
    _readiness = 0.0
    if _target_bid_ready:
        _readiness += 30.0
        _readiness_reasons.append("Target bid ready")
    else:
        _readiness -= 20.0
        _readiness_reasons.append("No target bid — not bid-ready")
    if _confidence_tier in {"high", "medium"} and not _weak_source:
        _readiness += 25.0
    elif _confidence_tier == "high":
        _readiness += 15.0
    else:
        _readiness_reasons.append("Confidence below execution threshold")
    if _comp_count >= 3:
        _readiness += 20.0
    elif _comp_count >= 1:
        _readiness += 10.0
    else:
        _readiness -= 15.0
        _readiness_reasons.append("Comp depth too thin for execution")
    if _lane_aligned:
        _readiness += 10.0
    else:
        _readiness -= 5.0
    if _recovery_stage == "primary":
        _readiness += 5.0
    elif _recovery_stage in {"tracked_expand", "window_expand"}:
        _readiness -= 8.0
        _readiness_reasons.append("Expanded recovery row")
    elif _recovery_stage == "discovery_fallback":
        _readiness -= 20.0
        _readiness_reasons.append("Discovery fallback — low execution confidence")
    if _entity_status == "EXACT_MATCH":
        _readiness += 5.0
    elif _entity_status == "NO_MATCH":
        _readiness -= 30.0
        _readiness_reasons.append("Entity not matched")
    if _quality_state == "execution_ready":
        _readiness += 10.0
    elif _quality_state == "quarantined":
        _readiness -= 30.0
    _execution_readiness = max(0.0, min(100.0, _readiness))

    # ── Decision Quality Score (0–100) ──────────────────────────────────────
    _dqs = (_valuation_trust_score * 0.35) + (_execution_readiness * 0.30)
    if _edge_pct >= 25:
        _dqs += 18.0
        _reasons.append(f"Strong edge {_edge_pct:.0f}%")
    elif _edge_pct >= 15:
        _dqs += 12.0
        _reasons.append(f"Good edge {_edge_pct:.0f}%")
    elif _edge_pct >= 8:
        _dqs += 6.0
    elif _edge_pct < 0:
        _dqs -= 10.0
        _reasons.append("Negative edge")
    if _lane_type in {"serial", "subset"} and _lane_aligned:
        _dqs += 8.0
        _reasons.append("Aligned specialty lane")
    elif _lane_aligned:
        _dqs += 3.0
    if _lane_tier == "primary":
        _dqs += 4.0
    if _recovery_stage == "discovery_fallback":
        _dqs -= 18.0
        _reasons.append("Discovery fallback penalty")
    elif _recovery_stage in {"tracked_expand", "window_expand"}:
        _dqs -= 6.0
    if _secs < 900:
        _dqs += 6.0
        _reasons.append("Closing in <15m")
    elif _secs < 3600:
        _dqs += 3.0
    if _deal_class == "ELITE":
        _dqs += 10.0
        _reasons.append("ELITE deal class")
    elif _deal_class == "STRONG":
        _dqs += 6.0
    elif _deal_class == "GOOD":
        _dqs += 3.0
    _decision_quality_score = max(0.0, min(100.0, _dqs))

    # ── Signal Tier ─────────────────────────────────────────────────────────
    if _decision_quality_score >= 75 and _execution_readiness >= 70:
        _signal_tier = "elite"
    elif _decision_quality_score >= 55 and _execution_readiness >= 50:
        _signal_tier = "strong"
    elif _decision_quality_score >= 35 or _execution_readiness >= 35:
        _signal_tier = "medium"
    else:
        _signal_tier = "weak"

    if not _reasons:
        if _signal_tier in {"elite", "strong"}:
            _reasons.append("Aligned tracked row with usable comps and positive edge")
        elif _signal_tier == "medium":
            _reasons.append("Plausible signal with limited valuation support")
        else:
            _reasons.append("Weak signal — monitor without commitment")

    return {
        "decision_quality_score": round(_decision_quality_score, 1),
        "execution_readiness": round(_execution_readiness, 1),
        "valuation_trust_score": round(_valuation_trust_score, 1),
        "signal_tier": _signal_tier,
        "quality_reasons": _reasons[:4],
        "decision_reason": _reasons[0] if _reasons else "Undetermined",
        "readiness_reason": _readiness_reasons[0] if _readiness_reasons else ("Bid-ready" if _execution_readiness >= 70 else "Watch mode"),
        "trust_reason": _trust_reasons[0] if _trust_reasons else "Valuation unresolved",
    }


def _hero_tier_label(_tier: str) -> str:
    return {
        "ACTIONABLE_HERO": "ACTIONABLE HERO",
        "SNIPER_CANDIDATE_HERO": "SNIPER CANDIDATE HERO",
        "WATCHLIST_HERO": "WATCHLIST HERO",
    }.get(str(_tier or "").strip().upper(), "")


def _es_confidence_tooltip(_row: Dict[str, Any]) -> str:
    _subset_name = str(_row.get("subset_name") or "").strip() or "none"
    _parallel_name = str(_row.get("parallel_name") or _row.get("parallel_bucket") or "").strip() or "none"
    _serial_bucket = str(_row.get("serial_bucket") or "").strip() or "none"
    _lane_type = str(_row.get("lane_type") or "generic").strip() or "generic"
    _lane_aligned = "yes" if bool(_row.get("lane_aligned")) else "no"
    _comp_source = str(_row.get("comp_source_label") or _row.get("mv_source") or "unresolved").strip() or "unresolved"
    _comp_count = int((_safe_float(_row.get("mv_comp_count")) or _safe_float(_row.get("comp_count")) or 0))
    return (
        f"lane_type: {_lane_type}\n"
        f"lane_aligned: {_lane_aligned}\n"
        f"comp_source_label: {_comp_source}\n"
        f"comp_count: {_comp_count}\n"
        f"serial_bucket: {_serial_bucket}\n"
        f"subset_name: {_subset_name}\n"
        f"parallel_name: {_parallel_name}"
    )


def _ui_authoritative_current_price(_row: Dict[str, Any]) -> Optional[float]:
    """
    Resolve the authoritative live current bid for a row using the precedence
    order:
        1. source_current_bid          (engine-stamped from Browse pricingSummary)
        2. current_bid                 (legacy field on the row)
        3. currentBidPrice.value /
           currentBidPrice.amount      (raw Browse API payload)
        4. source_display_price        (engine-stamped display value)
        5. current_price               (cached/computed; least trustworthy)
        6. price.value / price.amount  (Browse fallback)

    Returns None when no usable price is available. Emits a single
    [PRICE_AUTHORITY] log per call so the chosen-vs-available picture is
    visible per row.
    """
    _r = _row or {}
    _candidates: List[tuple] = []
    _src_cb = _safe_float(_r.get("source_current_bid"))
    _cb = _safe_float(_r.get("current_bid"))
    _cbp = _r.get("currentBidPrice") or {}
    if isinstance(_cbp, dict):
        _cbp_val = _safe_float(_cbp.get("value") or _cbp.get("amount") or _cbp.get("convertedFromValue"))
    else:
        _cbp_val = None
    _src_disp = _safe_float(_r.get("source_display_price"))
    _cp = _safe_float(_r.get("current_price"))
    _price_obj = _r.get("price") or {}
    if isinstance(_price_obj, dict):
        _price_val = _safe_float(_price_obj.get("value") or _price_obj.get("amount"))
    else:
        _price_val = _safe_float(_r.get("price"))
    _candidates = [
        ("source_current_bid", _src_cb),
        ("current_bid", _cb),
        ("currentBidPrice", _cbp_val),
        ("source_display_price", _src_disp),
        ("current_price", _cp),
        ("price", _price_val),
    ]
    _chosen: Optional[float] = None
    _chosen_reason = "no_price"
    for _name, _val in _candidates:
        if _val is not None and _val > 0:
            _chosen = float(_val)
            _chosen_reason = _name
            break
    try:
        print(
            f"[PRICE_AUTHORITY] "
            f"title={str(_r.get('title') or _r.get('source_title') or '')[:120]} "
            f"chosen_price={(round(_chosen, 2) if _chosen is not None else 'na')} "
            f"source_current_bid={(round(_src_cb, 2) if _src_cb is not None else 'na')} "
            f"current_bid={(round(_cb, 2) if _cb is not None else 'na')} "
            f"currentBidPrice={(round(_cbp_val, 2) if _cbp_val is not None else 'na')} "
            f"source_display_price={(round(_src_disp, 2) if _src_disp is not None else 'na')} "
            f"current_price={(round(_cp, 2) if _cp is not None else 'na')} "
            f"price={(round(_price_val, 2) if _price_val is not None else 'na')} "
            f"reason={_chosen_reason}"
        )
    except Exception:
        pass
    return _chosen


def _es_get_decision_view_model(_row: Dict[str, Any]) -> Dict[str, Any]:
    _row = _ui_preserve_live_surface_row_contract(_row)
    _row = _es_strengthen_row_valuation(_row)
    _row = _ui_preserve_live_surface_row_contract(_row)
    _row = _ui_apply_canonical_board_contract(_row)
    _row = _ui_preserve_live_surface_row_contract(_row)
    _row = _ui_stamp_research_only_display(_row)
    _row = _ui_preserve_live_surface_row_contract(_row)
    _research_only = bool(_row.get("_research_only_price_check"))
    _surface_tier = str(_row.get("_surface_tier") or "").strip()
    _watchlist_verify = _surface_tier == "review_watchlist_verify"
    _verified_watchlist = _surface_tier == "verified_watchlist"
    _surface_watchlist_only = bool(_row.get("_surface_tier_blocks_sniper"))
    _collector_heat = bool(_row.get("_collector_heat_surface"))
    _collector_heat_reasons = [
        str(_reason).strip()
        for _reason in list(_row.get("heat_signal_reasons") or [])
        if str(_reason or "").strip()
    ]
    # Use source_title if available — it is the verbatim eBay listing title, never rewritten
    _title = str(_row.get("source_title") or _row.get("title") or "Unknown listing").strip()
    _player = str(_row.get("player_name") or "").strip()
    _sport = _normalize_sport_label(_row.get("sport") or _row.get("sport_name") or "")
    _product = str(_row.get("product_family") or _row.get("set_name") or _row.get("set") or "").strip()
    _meta_parts = [p for p in [_player, _sport, _product] if p]
    _meta_line = " ? ".join(_meta_parts) if _meta_parts else "Live ending-soon auction"

    _current_price = _ui_authoritative_current_price(_row)
    if _research_only:
        print(
            f"[UI_RESEARCH_ONLY_RENDER] title={str((_row or {}).get('title') or _row.get('raw_title') or '')[:160]} "
            f"current={_row.get('current_price')} "
            f"reason={_row.get('_research_only_reason')}"
        )
    _true_market_value = _safe_float(_row.get("true_market_value")) or _safe_float(_row.get("market_value_true"))
    _review_estimate_value = _safe_float(_row.get("review_estimate_value")) or _es_resolve_review_estimate(_row)
    _market_value = _true_market_value
    _edge_pct = _safe_float(_row.get("edge_pct")) or _safe_float(_row.get("edge_percent"))
    _target_bid_fields = _es_compute_target_bid_fields(_row)
    _readiness = _es_get_valuation_readiness(_row)
    _target_bid = _target_bid_fields.get("target_bid_price")
    _target_bid_pct_used = _target_bid_fields.get("target_bid_pct_used")
    _target_bid_source = str(_target_bid_fields.get("target_bid_source") or "unavailable")
    _target_bid_ready = bool(_target_bid_fields.get("target_bid_ready"))
    _bid_ceiling_value = _target_bid_fields.get("bid_ceiling_value")
    _bid_ceiling_confidence = str(_target_bid_fields.get("bid_ceiling_confidence") or "NONE")
    _bid_ceiling_source = str(_target_bid_fields.get("bid_ceiling_source") or "NONE")
    _presentation_risk_block = str(_row.get("_presentation_risk_block") or "").strip().lower() in {"1", "true", "yes", "y", "on"}
    _presentation_bucket = str(_row.get("_presentation_bucket") or _row.get("presentation_bucket") or "").strip()
    if _presentation_risk_block:
        print(
            f"[UI_PRESENTATION_OVERRIDE] title={_title[:140]} "
            f"bucket={_presentation_bucket} "
            f"risk_block={_row.get('_presentation_risk_block')}"
        )
    _review_evidence_contract = _ui_review_evidence_contract(_row)
    _anchor_only_review = bool(_review_evidence_contract.get("anchor_only"))
    _row["_anchor_only_review"] = _anchor_only_review
    _edge_dollars = _safe_float(_row.get("edge_dollars"))
    if _edge_dollars is None and _true_market_value is not None and _current_price is not None:
        _edge_dollars = _true_market_value - _current_price
    elif _edge_dollars is None and _review_estimate_value is not None and _current_price is not None:
        _edge_dollars = _review_estimate_value - _current_price

    _quality_state = str(_row.get("row_quality_state") or "").strip().lower()
    _deal_class = str(_row.get("deal_class") or "UNKNOWN").strip().upper()
    _mv_status = str(
        _row.get("mv_status_norm")
        or _row.get("mv_source")
        or _row.get("market_value_source")
        or _row.get("valuation_confidence")
        or _row.get("confidence")
        or ("resolved" if _market_value is not None else "unresolved")
    ).strip().lower()
    _time_left_seconds = _es_time_remaining_seconds(_row)
    _comp_count = int((_safe_float(_row.get("mv_comp_count")) or _safe_float(_row.get("comp_count")) or _safe_float(_row.get("comps_count")) or 0))
    _visibility = _es_visibility_bucket(_row)
    _readiness_bucket = str(_readiness.get("bucket") or "suppressed")
    _confidence_tier = str(_readiness.get("confidence_tier") or "unknown")
    _scarcity_view = _es_scarcity_view(_row)
    _lane_view = _es_lane_view(_row)
    _live_signal = _score_live_signal_origin(_row)
    _recovery_stage = str(_row.get("recovery_stage") or "primary").strip().lower() or "primary"
    _recovery_badge = {
        "tracked_expand": ("EXPANDED", "amber"),
        "window_expand": ("WINDOW+", "amber"),
        "discovery_fallback": ("DISCOVERY", "red"),
    }.get(_recovery_stage)
    _promotion_status = str(_row.get("premium_review_status") or "").strip().lower()
    _promotion_reason = str(_row.get("premium_review_reason") or _row.get("review_failure_reason") or "").strip()
    _hero_tier = str(_row.get("hero_tier") or "").strip().upper()
    _hero_reason = str(_row.get("hero_reason") or "").strip()
    _hero_surface_blocked = str(_row.get("_hero_surface_blocked") or _row.get("hero_surface_blocked") or "").strip().lower() in {"1", "true", "yes", "y", "on"}
    if _hero_surface_blocked:
        _hero_tier = ""
        _hero_reason = _hero_reason or "Single exact comp matches current price; no verified edge for sniper label"
    _hero_label = _hero_tier_label(_hero_tier)

    _dq = _es_score_decision_quality(_row)
    _dqs = float(_dq.get("decision_quality_score") or 0.0)
    _exec_r = float(_dq.get("execution_readiness") or 0.0)
    _signal_tier = str(_dq.get("signal_tier") or "weak")
    _decision_reason = str(_dq.get("decision_reason") or "")
    _readiness_reason = str(_dq.get("readiness_reason") or "")
    _trust_reason = str(_dq.get("trust_reason") or "")

    # Truth contract — read engine-stamped fields, fall back to deriving inline
    _is_actionable_bid = bool(_row.get("is_actionable_bid"))
    _has_positive_edge = bool(_row.get("has_positive_edge", True))  # default True if field absent (legacy rows)
    _has_valid_mv = bool(_row.get("has_valid_mv", (_true_market_value or 0) > 0))
    _has_valid_target_bid = bool(_row.get("has_valid_target_bid", _target_bid_ready))
    _is_review_candidate = bool(_row.get("is_review_candidate"))
    # Inline fallback: if engine didn't stamp truth contract, derive it now
    if "is_actionable_bid" not in _row:
        _edge_d_inline = _edge_dollars if _edge_dollars is not None else 0.0
        _has_positive_edge = bool(_edge_d_inline > 0 or ((_edge_pct or 0) > 0))
        _has_valid_mv = bool((_true_market_value or 0) > 0)
        _has_valid_target_bid = bool(_target_bid_ready and ((_true_market_value or 0) > 0))
        _is_review_candidate = bool(
            bool(_row.get("promoted_live_candidate"))
            or str(_row.get("premium_review_status") or "").strip().lower() in {"resolved", "partial"}
            or bool(_row.get("mv_resolved"))
        )
        _is_actionable_bid = bool(_has_valid_mv and _has_positive_edge and _has_valid_target_bid
                                  and str(_row.get("row_quality_state") or "").strip().lower() != "suppressed")
    if not _has_valid_mv:
        _is_actionable_bid = False

    # Rescue trust contract — if row is a rescue row, strip actionable state
    _rescue_trust_tier = str(_row.get("rescue_trust_tier") or "none").strip().lower()
    _is_rescue_row = bool(_row.get("is_rescue_row")) or _rescue_trust_tier != "none"
    if _is_rescue_row and _is_actionable_bid:
        _is_actionable_bid = False   # UI-layer guard matches engine-layer contract
    if _hero_surface_blocked:
        _is_actionable_bid = False
        _has_positive_edge = False
    if _presentation_risk_block:
        _is_actionable_bid = False
        _has_positive_edge = False
    if _surface_watchlist_only or _watchlist_verify:
        _is_actionable_bid = False

    # Canonical action label — negative-edge and non-actionable rows cannot reach positive labels
    if not _has_valid_mv and not _target_bid_ready:
        _action = "NO BID YET"
    elif not _has_positive_edge and _has_valid_mv:
        _action = "OVER MV"
    elif _is_actionable_bid and _readiness_bucket == "action_ready" and _dqs >= 65 and _exec_r >= 70 and _recovery_stage == "primary":
        _action = "EXECUTE NOW"
    elif _is_actionable_bid and _readiness_bucket == "action_ready" and _dqs >= 45 and _exec_r >= 45:
        _action = "PREPARE SNIPE"
    elif _is_actionable_bid and (_readiness_bucket in {"action_ready", "monitor"}) and _target_bid_ready and _dqs >= 28:
        _action = "WATCH CLOSELY"
    elif _is_review_candidate and not _is_actionable_bid:
        _action = "REVIEW ONLY"
    elif _readiness_bucket == "monitor":
        _action = "MONITOR"
    else:
        _action = "MONITOR"   # PASS is internal only; surface as MONITOR

    # ── Primary state (single source of truth for badge selection) ──────────────
    if _is_actionable_bid:
        _primary_state = "ACTIONABLE"
    elif _has_valid_mv and not _has_positive_edge:
        _primary_state = "OVER_MV"
    elif _is_review_candidate:
        _primary_state = "REVIEW"
    else:
        _primary_state = "IGNORE"

    # Confidence badge (shared across all states, shown last)
    _conf_badge = {"label": f"CONF {str(_confidence_tier).upper()}", "tone": "green" if _confidence_tier == "high" else "amber" if _confidence_tier == "medium" else "muted"}

    # ── Rescue rows override primary state before badge selection ─────────────
    # Rows that survived only via broad rescue cannot hold ACTIONABLE or premium states.
    if _is_rescue_row and _primary_state == "ACTIONABLE":
        _primary_state = "REVIEW"
        _action = "REVIEW ONLY"
    elif _is_rescue_row and _primary_state not in {"OVER_MV", "REVIEW"}:
        _primary_state = "REVIEW"
        if _action not in {"OVER MV", "REVIEW ONLY", "MONITOR", "NO VALID TARGET BID", "NO BID YET"}:
            _action = "REVIEW ONLY"

    # ── State-driven badge list — max 3, no accumulation ─────────────────────
    if _primary_state == "ACTIONABLE":
        if _time_left_seconds is not None and _time_left_seconds <= 900 and _action in {"EXECUTE NOW", "PREPARE SNIPE"}:
            _p1 = {"label": "ENDING SOON", "tone": "red"}
        elif _action == "EXECUTE NOW":
            _p1 = {"label": "EXECUTE NOW", "tone": "green"}
        elif _action == "PREPARE SNIPE":
            _p1 = {"label": "PREPARE SNIPE", "tone": "blue"}
        else:
            _p1 = {"label": "WATCH CLOSELY", "tone": "amber"}
        _badges = [_p1, {"label": "TARGET BID READY", "tone": "green"}, _conf_badge]
    elif _primary_state == "OVER_MV":
        if _is_rescue_row:
            _badges = [{"label": "OVER MV", "tone": "red"}, {"label": "CLOSE MATCH", "tone": "amber"}, _conf_badge]
        else:
            _badges = [{"label": "OVER MV", "tone": "red"}, {"label": "MONITOR", "tone": "muted"}, _conf_badge]
    elif _primary_state == "REVIEW":
        if _anchor_only_review:
            _badges = [{"label": "REVIEW ONLY", "tone": "amber"}, {"label": "NO VERIFIED COMP EVIDENCE", "tone": "muted"}, _conf_badge]
        elif _is_rescue_row:
            _badges = [{"label": "REVIEW ONLY", "tone": "amber"}, {"label": "CLOSE MATCH", "tone": "muted"}, _conf_badge]
        else:
            _review_resolved = _promotion_status in {"resolved"} or bool(_row.get("mv_resolved"))
            _p2 = {"label": "REVIEW RESOLVED", "tone": "amber"} if _review_resolved else {"label": "PENDING REVIEW", "tone": "muted"}
            _badges = [{"label": "SURFACED", "tone": "amber"}, _p2, _conf_badge]
    else:
        _badges = [{"label": "MONITOR", "tone": "muted"}, _conf_badge]

    if _hero_label:
        _hero_tone = {
            "ACTIONABLE_HERO": "green",
            "SNIPER_CANDIDATE_HERO": "amber",
            "WATCHLIST_HERO": "blue",
        }.get(_hero_tier, "muted")
        _badges = [{"label": _hero_label, "tone": _hero_tone}] + list(_badges)
    if _presentation_risk_block:
        _action = "MONITOR"
        _primary_state = "IGNORE"
        _hero_label = ""
        _badges = [
            {"label": "MONITOR", "tone": "muted"},
            {"label": "UNCONFIRMED VALUE", "tone": "amber"},
            {"label": "DO NOT CHASE", "tone": "red"},
        ]
    if _verified_watchlist and not _research_only:
        _action = "WATCHLIST"
        _primary_state = "REVIEW"
        _hero_label = ""
        _badges = [
            {"label": "WATCHLIST", "tone": "blue"},
            {"label": "VERIFIED VALUE", "tone": "green"},
            {"label": "EDGE REQUIRED", "tone": "muted"},
        ]
    if _watchlist_verify and not _research_only:
        _action = "WATCHLIST - VERIFY"
        _primary_state = "REVIEW"
        _hero_label = ""
        _badges = [
            {"label": "WATCHLIST - VERIFY", "tone": "amber"},
            {"label": "REFERENCE VALUE", "tone": "muted"},
            {"label": "NO SNIPE", "tone": "red"},
        ]
    if _collector_heat and not (_research_only or _verified_watchlist or _watchlist_verify):
        _action = "HIGH-HEAT RESEARCH"
        _primary_state = "IGNORE"
        _hero_label = ""
        _badges = [{"label": "HIGH-HEAT RESEARCH", "tone": "amber"}] + [
            {"label": _reason, "tone": "blue"} for _reason in _collector_heat_reasons[:2]
        ]
    if _research_only:
        _action = "PRICE CHECK NEEDED"
        _primary_state = "IGNORE"
        _hero_label = ""
        _badges = [
            {"label": "HIGH-HEAT RESEARCH" if _collector_heat else "RESEARCH ONLY", "tone": "amber"},
            {"label": "PRICE CHECK NEEDED", "tone": "muted"},
            {"label": (_collector_heat_reasons[0] if _collector_heat_reasons else "EVIDENCE: NEEDS COMPS"), "tone": "blue" if _collector_heat_reasons else "muted"},
        ]

    # MV display contract — show dollar amount when valid, explicit blocked reason otherwise
    _valuation_truth_tier = str(_row.get("valuation_truth_tier") or _row.get("_valuation_truth_tier") or ("TRUE" if _true_market_value else "REVIEW" if _review_estimate_value else "NONE")).strip().upper()
    _comp_truth = _ui_comp_truth_split(_row)
    _valuation_source_clean = str(_row.get("valuation_source_clean") or _es_valuation_source_clean(_row))
    _value_label = str(_row.get("_board_value_label") or "")
    _value_mode = str(_row.get("_board_value_mode") or "")
    _bid_mode = str(_row.get("_board_bid_mode") or "")
    if not _value_label and _true_market_value and str(_comp_truth.get("truth_level") or "NONE") == "EXACT":
        _value_label = "Market Value"
        _value_value = _true_market_value
        _mv_blocked_display = None
    elif not _value_label and _review_estimate_value:
        _value_label = "Review Estimate"
        _value_value = _review_estimate_value
        _mv_blocked_display = None
    else:
        if _value_label == "Market Value":
            _value_value = _true_market_value
            _mv_blocked_display = None if _true_market_value else _mv_blocked_reason_label(_row)
        elif _value_label == "Review Estimate":
            _value_value = _review_estimate_value
            _mv_blocked_display = None
        else:
            _value_label = "Market Value"
            _value_value = None
            _mv_blocked_display = _mv_blocked_reason_label(_row)
    _mv_display_value = _format_money(_value_value) if _value_value else (_mv_blocked_display or "—")
    print(
        f"[BOARD_VALUE_FIELD] title={_title[:120]} label={_value_label} "
        f"value={_value_value if _value_value is not None else (_mv_blocked_display or '—')}"
    )
    if not _value_mode:
        _value_mode = "exact" if _value_label == "Market Value" and _true_market_value else "review" if _value_label == "Review Estimate" else "none"
    if not _bid_mode:
        _bid_mode = _value_mode
    if _presentation_risk_block:
        # [PRESENTATION_RISK_BLANK] — Untrusted-value contract.
        # If the engine flagged this row's value as risky (single-comp,
        # fallback pricing, self-comp echo), the UI must not advertise a
        # dollar amount. The "Unconfirmed Value" label already tells the
        # user the number isn't trustworthy; printing a number anyway
        # contradicts the label and lets self-comp contamination leak
        # through. Engine-side target/edge math is independent and stays
        # untouched — this only suppresses the public reference figure.
        try:
            _echo_value_log = float(_value_value) if _value_value is not None else None
        except (TypeError, ValueError):
            _echo_value_log = None
        try:
            _echo_current_log = float(_current_price) if _current_price is not None else None
        except (TypeError, ValueError):
            _echo_current_log = None
        print(
            f"[PRESENTATION_RISK_BLANK] title={str(_title)[:120]} "
            f"prior_value={_echo_value_log} current={_echo_current_log} "
            f"label_before={_value_label}"
        )
        _value_label = "Unconfirmed Value"
        _value_mode = "monitor"
        _bid_mode = "monitor"
        _value_value = None
        _mv_display_value = "—"
        _mv_blocked_display = "Unconfirmed"
    if _research_only:
        _value_label = "UNCONFIRMED / DO NOT USE"
        _value_value = None
        _mv_display_value = "PRICE CHECK"
        _mv_blocked_display = "PRICE CHECK"
        _value_mode = "monitor"
        _bid_mode = "none"
    if _watchlist_verify:
        _value_label = "Reference Value"
        _value_value = _review_estimate_value
        _mv_display_value = _format_money(_value_value) if _value_value else (_mv_blocked_display or "—")
        _value_mode = "review"
        _bid_mode = "none"
    _public_target_bid_ready = bool(
        _target_bid_ready
        and not _anchor_only_review
        and not _presentation_risk_block
        and not _surface_watchlist_only
        and not _watchlist_verify
    )
    _public_target_bid = _target_bid if _public_target_bid_ready else None
    _public_target_bid_display = _format_money(_public_target_bid) if _public_target_bid_ready else ""
    _public_bid_ceiling_value = _bid_ceiling_value if _public_target_bid_ready else None
    _public_bid_ceiling_confidence = _bid_ceiling_confidence if _public_target_bid_ready else "NONE"
    _public_bid_ceiling_source = _bid_ceiling_source if _public_target_bid_ready else "NONE"
    _public_bid_mode = _bid_mode if _public_target_bid_ready else "none"
    print(
        f"[BOARD_VALUE_BID_CONSISTENCY] title={_title[:120]} item={_ui_board_contract_item_key(_row)[:32]} "
        f"value_mode={_value_mode} bid_mode={_public_bid_mode} consistent={1 if _value_mode == _public_bid_mode else 0}"
    )

    if _research_only:
        _metric_pairs = [
            ("CURRENT PRICE", _format_money(_current_price)),
            ("UNCONFIRMED / DO NOT USE", "PRICE CHECK"),
            ("EVIDENCE", "needs comps"),
        ]
    else:
        _metric_pairs = [
            ("Current", _format_money(_current_price)),
            (_value_label, _mv_display_value),
            ("Edge %", _format_pct_value(_edge_pct)),
            ("Edge $", _format_money(_edge_dollars)),
        ]
    if not _anchor_only_review and not _research_only:
        _metric_pairs.append(("Target Bid", _format_money(_public_target_bid) if _public_target_bid_ready else "target bid unavailable"))
    if not _research_only:
        _metric_pairs.append(
            (str(_comp_truth.get("label") or "Comps"), str(_comp_truth.get("display_count")) if (_comp_truth.get("display_count") or 0) > 0 else ("?" if (_row.get("comp_count") is not None or _row.get("comps_count") is not None or _comp_count > 0) else "?"))
        )
    _metrics = []
    for _label, _value in _metric_pairs:
        if _value != "?":
            _metrics.append({"label": _label, "value": _value})
    print(
        f"[COMP_UI_BIND] title={_title[:120]} truth={_comp_truth.get('truth') or 'NONE'} "
        f"truth_level={_comp_truth.get('truth_level') or 'NONE'} "
        f"true_mv={_comp_truth.get('true_mv')} "
        f"raw_exact_match_count={_comp_truth.get('raw_exact_match_count') or 0} "
        f"trusted_exact_comp_count={_comp_truth.get('trusted_exact_comp_count') or 0} "
        f"support_comp_count={_comp_truth.get('support_comp_count') or 0} "
        f"label={_comp_truth.get('label') or 'Comps'}"
    )

    if _action == "EXECUTE NOW":
        _action_note = "Highest-confidence opportunity in the current board."
    elif _action == "PREPARE SNIPE":
        _action_note = "Worth lining up before the close."
    elif _action == "WATCH CLOSELY":
        _action_note = "Track this close and be ready if price remains inside your bid lane."
    elif _action == "OVER MV":
        _action_note = "Surfaced for review — MV resolved, but current price is above target."
    elif _action == "REVIEW ONLY":
        _action_note = "Surfaced for review — awaiting confirmation or better pricing."
    elif _action == "MONITOR":
        _action_note = _es_monitor_reason(_row)
    elif _action in {"NO VALID TARGET BID", "NO BID YET"}:
        _action_note = "Pricing support is still too thin to publish a safe bid ceiling."
    else:
        _action_note = "Do not prioritize this listing."
    if bool(_row.get("promoted_live_candidate")) and _promotion_reason and _is_actionable_bid:
        _action_note = _promotion_reason
    if _public_target_bid_ready and _is_actionable_bid:
        _action_note = f"{_action_note} Target bid source: {_target_bid_source.replace('_', ' ')}."
    # Rescue rows get a specific note — never use execution copy for close-match rows
    if _is_rescue_row:
        _action_note = "Surfaced for review — identity is close, but target match is not clean enough for action."
    if _anchor_only_review:
        _action = "REVIEW ONLY"
        _action_note = "No verified comp evidence yet."
    if _presentation_risk_block:
        _action = "MONITOR"
        _action_note = str(_row.get("_presentation_subhead") or "Single-comp or fallback-based pricing")
    if _verified_watchlist and not _research_only:
        _action = "WATCHLIST"
        _action_note = "Verified value row; keep on watchlist unless edge clears sniper rules."
    if _watchlist_verify and not _research_only:
        _action = "WATCHLIST - VERIFY"
        _action_note = "Reference value has supporting evidence, but it still needs verification before any snipe."
    if _collector_heat and not (_research_only or _verified_watchlist or _watchlist_verify):
        _action = "HIGH-HEAT RESEARCH"
        _action_note = "Collector heat is strong; keep visible for research without bid guidance."
    if _research_only:
        _action = "PRICE CHECK NEEDED"
        _action_note = "High collector heat needs comps before this can be used as value or bid guidance." if _collector_heat else "Evidence needs comps before this can be used as value or bid guidance."
    _review_display_state = "NO VERIFIED COMP EVIDENCE" if _anchor_only_review else _action
    print(
        f"[REVIEW_BADGE_CONTRACT] title={_title[:140]} truth={_valuation_truth_tier or 'NONE'} "
        f"true_mv={round(float(_true_market_value), 2) if _true_market_value and _true_market_value > 0 else None} "
        f"review={round(float(_review_estimate_value), 2) if _review_estimate_value and _review_estimate_value > 0 else None} "
        f"anchor_only={1 if _anchor_only_review else 0} "
        f"target_bid_ready={1 if _public_target_bid_ready else 0} display_state={_review_display_state}"
    )
    _origin_reason = str(_promotion_reason or _live_signal.get("live_signal_reason") or _row.get("route_reason") or _row.get("recovery_reason") or "").strip()

    # ── Final action layer — runs AFTER valuation outputs are populated ──
    _final_action = _es_apply_final_execution_action(_row)
    # Render-layer override: when the final layer produced a real decision,
    # legacy _action / _action_note / _badges must reflect the final truth so
    # every downstream renderer (cards, badges, CTAs, monitor/watchlist text)
    # surfaces the new label. Legacy fields used only as fallback when the
    # final layer is empty.
    _final_decision_for_view = str(_final_action.get("final_execution_decision") or "").strip().upper()
    if _final_decision_for_view and _final_decision_for_view not in {"", "SKIP"}:
        _final_label_for_view = str(_final_action.get("final_action_label") or _final_decision_for_view)
        _final_cta_for_view = str(_final_action.get("final_cta_text") or _final_label_for_view)
        # Override the legacy plain-text action label
        _action = _final_label_for_view
        _action_note = _final_cta_for_view
        # Rebuild badges to reflect the final decision. _conf_badge stays as-is.
        if _final_decision_for_view == "SNIPE_NOW":
            _badges = [{"label": "SNIPE NOW", "tone": "green"}, {"label": "TARGET BID READY", "tone": "green"}, _conf_badge]
        elif _final_decision_for_view == "WATCH":
            _badges = [{"label": "WATCH", "tone": "amber"}, {"label": "NEAR TARGET", "tone": "muted"}, _conf_badge]
        elif _final_decision_for_view == "PASS_OVERPRICED":
            _badges = [{"label": "PASS — OVERPRICED", "tone": "red"}, {"label": "ABOVE TARGET +5%", "tone": "muted"}, _conf_badge]
        elif _final_decision_for_view == "PASS":
            _badges = [{"label": "PASS", "tone": "muted"}, {"label": "NO TARGET BID", "tone": "muted"}, _conf_badge]
        elif _final_decision_for_view == "RESEARCH_SNIPE":
            _badges = [{"label": "RESEARCH SNIPE", "tone": "green"}, {"label": "RESEARCH-GRADE", "tone": "amber"}, {"label": "CONF LOW", "tone": "muted"}]
        elif _final_decision_for_view == "RESEARCH_WATCH":
            _badges = [{"label": "RESEARCH WATCH", "tone": "amber"}, {"label": "RESEARCH-GRADE", "tone": "amber"}, {"label": "CONF LOW", "tone": "muted"}]
        elif _final_decision_for_view == "RESEARCH_PASS":
            _badges = [{"label": "RESEARCH PASS", "tone": "red"}, {"label": "ABOVE RESEARCH BAND", "tone": "muted"}, {"label": "CONF LOW", "tone": "muted"}]

    return {
        "title": _title,
        "meta_line": _meta_line,
        "time_label": str(_row.get("formatted_time_left") or _es_time_remaining_label(_row)),
        "final_execution_decision": _final_action["final_execution_decision"],
        "final_action_label": _final_action["final_action_label"],
        "final_cta_text": _final_action["final_cta_text"],
        "final_badge_text": _final_action["final_badge_text"],
        "final_action_reason": _final_action["final_action_reason"],
        "final_edge_dollars": _final_action["final_edge_dollars"],
        "final_edge_pct": _final_action["final_edge_pct"],
        "final_action_path": _final_action["final_action_path"],
        "badges": _badges,
        "metrics": _metrics,
        "action_label": _action,
        "action_note": _action_note,
        "presentation_risk_block": _presentation_risk_block,
        "presentation_bucket": _presentation_bucket,
        "presentation_headline": str(_row.get("_presentation_headline") or "Unconfirmed valuation") if _presentation_risk_block else "",
        "presentation_subhead": str(_row.get("_presentation_subhead") or "Single-comp or fallback-based pricing") if _presentation_risk_block else "",
        "presentation_badges_override": list(_row.get("_presentation_badges_override") or []) if _presentation_risk_block else [],
        "research_only_price_check": _research_only,
        "research_only_reason": str(_row.get("_research_only_reason") or ""),
        "surface_tier": _surface_tier,
        "surface_watchlist_only": _surface_watchlist_only,
        "collector_heat_surface": _collector_heat,
        "heat_signal_score": int(_row.get("heat_signal_score") or 0),
        "heat_signal_reasons": list(_collector_heat_reasons),
        "url": str(_row.get("source_view_url") or _row.get("url") or ""),
        "image_url": str(_row.get("source_image_url") or _row.get("thumbnail") or _row.get("image_url") or ""),
        "source_current_bid": float(_row.get("source_current_bid") or _row.get("current_bid") or _row.get("current_price") or 0.0),
        "source_buy_now_price": _row.get("source_buy_now_price"),
        "source_price_kind": str(_row.get("source_price_kind") or ""),
        "source_end_time": str(_row.get("source_end_time") or _row.get("end_iso") or ""),
        "visibility_bucket": _visibility,
        "readiness_bucket": _readiness_bucket,
        "confidence_tier": _confidence_tier,
        "target_bid_price": _public_target_bid,
        "target_bid_display": _public_target_bid_display,
        "target_bid_pct_used": _target_bid_pct_used,
        "target_bid_source": _target_bid_source if _public_target_bid_ready else "unavailable",
        "target_bid_source_detail": str(_target_bid_fields.get("target_bid_source_detail") or _target_bid_source) if _public_target_bid_ready else "unavailable",
        "target_bid_confidence": str(_target_bid_fields.get("target_bid_confidence") or "NONE") if _public_target_bid_ready else "NONE",
        "target_bid_ready": _public_target_bid_ready,
        "bid_mode": _public_bid_mode,
        "bid_ceiling_value": _public_bid_ceiling_value,
        "bid_ceiling_confidence": _public_bid_ceiling_confidence,
        "bid_ceiling_source": _public_bid_ceiling_source,
        "bid_ceiling_ready": bool(_target_bid_fields.get("bid_ceiling_ready")) and _public_target_bid_ready,
        "scarcity_parts": _scarcity_view.get("parts", []),
        "lane_label": _lane_view.get("lane_label", "GENERIC LANE"),
        "lane_tone": _lane_view.get("lane_tone", "lane-fallback"),
        "recovery_stage": _recovery_stage,
        "origin_reason": _origin_reason,
        "live_signal_tier": str(_live_signal.get("live_signal_tier") or "recovery"),
        "live_signal_score": float(_live_signal.get("live_signal_score") or 0.0),
        "live_signal_reason": str(_live_signal.get("live_signal_reason") or ""),
        "remaining_seconds": _time_left_seconds,
        "formatted_time_left": str(_row.get("formatted_time_left") or _format_remaining_time_label(_time_left_seconds)),
        "promoted_live_candidate": bool(_row.get("promoted_live_candidate")),
        "premium_review_status": _promotion_status,
        "premium_review_reason": _promotion_reason,
        "review_failed": bool(_row.get("review_failed")),
        "review_failure_reason": str(_row.get("review_failure_reason") or ""),
        "mv_attempted": bool(_row.get("mv_attempted")),
        "mv_resolved": bool(_row.get("mv_resolved")),
        "comp_attempted": bool(_row.get("comp_attempted")),
        "target_bid_attempted": bool(_row.get("target_bid_attempted")),
        "decision_quality_score": _dqs,
        "execution_readiness": _exec_r,
        "valuation_trust_score": float(_dq.get("valuation_trust_score") or 0.0),
        "signal_tier": _signal_tier,
        "quality_reasons": _dq.get("quality_reasons", []),
        "decision_reason": _decision_reason,
        "readiness_reason": _readiness_reason,
        "trust_reason": _trust_reason,
        "is_actionable_bid": _is_actionable_bid,
        "has_positive_edge": _has_positive_edge,
        "has_valid_mv": _has_valid_mv,
        "has_valid_target_bid": (False if _anchor_only_review else _has_valid_target_bid),
        "is_review_candidate": _is_review_candidate,
        "auction_quality_score": float(_row.get("auction_quality_score") or 0.0),
        "auction_quality_grade": (
            "A" if float(_row.get("auction_quality_score") or 0.0) >= 70 else
            "B" if float(_row.get("auction_quality_score") or 0.0) >= 45 else
            "C"
        ),
        "target_fit_tier": str(_row.get("target_fit_tier") or ""),
        "is_raw_preferred": bool(_row.get("is_raw_preferred")),
        "is_graded_card": bool(_row.get("is_graded_card")),
        "desirability_score": float(_row.get("desirability_score") or 0.0),
        "rescue_trust_tier": _rescue_trust_tier,
        "is_rescue_row": _is_rescue_row,
        "rescue_reason": str(_row.get("rescue_reason") or ""),
        "anchor_only_review": _anchor_only_review,
        "review_display_state": _review_display_state,
        "execution_decision": str(_final_action["final_execution_decision"] or _row.get("execution_decision") or "SKIP"),
        "execution_score": float(_row.get("execution_score") or 0.0),
        "execution_pressure": str(_row.get("execution_pressure") or "LOW"),
        "whatnot_heat_score": float(_row.get("whatnot_heat_score") or 0.0),
        "heat_fill": bool(_row.get("heat_fill", False)),
        "heat_upgraded": bool(_row.get("heat_upgraded", False)),
        "commercial_signal_score": float(_row.get("commercial_signal_score") or 0.0),
        "sniper_board_score": float(_row.get("sniper_board_score") or 0.0),
        "hero_board_eligible": bool(_row.get("hero_board_eligible")),
        "hero_tier": _hero_tier,
        "hero_tier_label": _hero_label,
        "hero_reason": _hero_reason,
        "board_bucket": str(_row.get("board_bucket") or _row.get("_board_bucket") or ""),
        "commercially_visible": bool(_row.get("commercially_visible", True)),
        "commercial_visibility_reason": str(_row.get("commercial_visibility_reason") or ""),
        "floor_exception": bool(_row.get("floor_exception")),
        "floor_exception_reason": str(_row.get("floor_exception_reason") or ""),
        # MV display contract — authoritative display fields for card render layer
        "market_value_display": _true_market_value,
        "review_estimate_display": _review_estimate_value,
        "value_label": _value_label,
        "value_numeric": _value_value,
        "mv_blocked_reason_display": _mv_blocked_display,
        "mv_display_value": _mv_display_value,
        "mv_valid": bool(_true_market_value and _true_market_value > 0),
        "mv_confidence_strict": str(_row.get("mv_confidence_strict") or ""),
        "mv_blocked_reason": str(_row.get("mv_blocked_reason") or ""),
        "mv_comp_count": _comp_count,
        "market_value_source": str(_row.get("market_value_source") or _row.get("mv_source") or ""),
        "valuation_truth_tier": _valuation_truth_tier,
        "valuation_source_clean": _valuation_source_clean,
        "true_market_value": _true_market_value,
        "review_estimate_value": _review_estimate_value,
    }


def _render_es_results_header(_rows: List[Dict[str, Any]], _sort_label: str, *, _action_ready_count: int = 0, _monitor_count: int = 0, _suppressed_count: int = 0) -> None:
    _exec_ready = sum(1 for _row in _rows if str(_row.get("row_quality_state") or "").strip().lower() == "execution_ready")
    st.markdown(
        f"""
        <div class='sw-es-header'>
          <div class='sw-es-header-label'>Ending Soon opportunities</div>
          <div class='sw-es-header-title'>{len(_rows)} live auction opportunit{'y' if len(_rows) == 1 else 'ies'}</div>
          <div class='sw-es-header-subtitle'>{_action_ready_count} action-ready • {_monitor_count} monitor • {_suppressed_count} suppressed • {_exec_ready} execution-grade • sort: {_sort_label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


_ES_BADGE_GUARD: Dict[str, int] = {
    "structured_ok": 0,
    "legacy_blocked": 0,
    "non_dict_dropped": 0,
    "clean_rows": 0,
    "failed_rows": 0,
}


def _reset_es_badge_guard() -> None:
    for _key in list(_ES_BADGE_GUARD.keys()):
        _ES_BADGE_GUARD[_key] = 0


def _badge_guard_snapshot() -> Dict[str, int]:
    return {str(_k): int(_v or 0) for _k, _v in _ES_BADGE_GUARD.items()}


def _normalize_badge_label(_label: Any) -> str:
    _text = str(_label or "").strip()
    if not _text:
        return ""
    if _text.strip().upper() in {"QA", "QC", "PASS"}:
        return ""
    return _text


def _render_badge_html(_badges: Any) -> str:
    """Render a list of structured badge dicts as safe HTML.
    Each badge must be {"label": str, "tone": str} and optionally {"style": str}.
    Non-dict entries are silently skipped — no raw HTML strings pass through."""
    if not _badges or not isinstance(_badges, list):
        return ""
    _parts: List[str] = []
    _failed = False
    for _b in list(_badges)[:3]:
        if not isinstance(_b, dict):
            if isinstance(_b, str) and ("<span" in _b.lower() or "sw-es-badge" in _b.lower()):
                _ES_BADGE_GUARD["legacy_blocked"] = int(_ES_BADGE_GUARD.get("legacy_blocked", 0) or 0) + 1
                _failed = True
            else:
                _ES_BADGE_GUARD["non_dict_dropped"] = int(_ES_BADGE_GUARD.get("non_dict_dropped", 0) or 0) + 1
            continue
        _lbl = _normalize_badge_label(_b.get("label"))
        if not _lbl:
            continue
        if "<span" in _lbl.lower() or "sw-es-badge" in _lbl.lower():
            _ES_BADGE_GUARD["legacy_blocked"] = int(_ES_BADGE_GUARD.get("legacy_blocked", 0) or 0) + 1
            _failed = True
            continue
        _tone = str(_b.get("tone") or "muted").replace("'", "").replace('"', "").replace(" ", "")
        _lbl_esc = escape(_lbl)
        _extra = f" style='{str(_b['style']).replace(chr(39), '')}'" if _b.get("style") else ""
        _parts.append(f"<span class='sw-es-badge sw-es-badge-{_tone}'{_extra}>{_lbl_esc}</span>")
        _ES_BADGE_GUARD["structured_ok"] = int(_ES_BADGE_GUARD.get("structured_ok", 0) or 0) + 1
    _html = "".join(_parts)
    if "&lt;span class=&#x27;sw-es-badge" in _html or "&lt;span class='sw-es-badge" in _html:
        _failed = True
    if _failed:
        _ES_BADGE_GUARD["failed_rows"] = int(_ES_BADGE_GUARD.get("failed_rows", 0) or 0) + 1
        return ""
    _ES_BADGE_GUARD["clean_rows"] = int(_ES_BADGE_GUARD.get("clean_rows", 0) or 0) + 1
    return _html


def _execution_decision_label_html(view: Dict[str, Any]) -> str:
    """Return styled HTML for the execution decision label shown on each card.
    Final-action fields (final_execution_decision / final_action_label) win
    over legacy fields. Legacy MONITOR / RESEARCH ONLY / WATCHLIST VERIFY
    fallbacks only render when the final layer was unable to compute a real
    decision. This is a render-layer-only patch — it does not change backend
    decision math, valuation trust, or board sorting."""
    _final_decision = str(view.get("final_execution_decision") or "").strip().upper()
    _final_label = str(view.get("final_action_label") or "").strip()
    _final_cta = str(view.get("final_cta_text") or "").strip()
    _final_badge = str(view.get("final_badge_text") or _final_label).strip()
    _final_path = str(view.get("final_action_path") or "").strip().lower()
    _title_log = str(view.get("title") or "")[:120]
    if _final_decision and _final_decision not in {"", "SKIP"}:
        # Map decisions to color tokens. Reds for PASS, ambers for WATCH,
        # greens for SNIPE, neutral for AWAITING.
        _final_cfg = {
            "SNIPE_NOW":        ("🟢", _final_label or "SNIPE NOW",        "#22c55e", "#0a1f10"),
            # UNDER_MV — bidding under fair market, above snipe-target. Cyan/teal
            # so it pops as a real opportunity but visually distinct from the
            # green "deep snipe" tier.
            "UNDER_MV":         ("🔵", _final_label or "UNDER MV",         "#06b6d4", "#03161a"),
            "WATCH":            ("🟡", _final_label or "WATCH",            "#f59e0b", "#1c1407"),
            "PASS_OVERPRICED":  ("🔴", _final_label or "PASS — OVERPRICED","#dc2626", "#1a0505"),
            "PASS":             ("⚪", _final_label or "PASS",              "#b0b0b0", "#0f172a"),
            "RESEARCH_SNIPE":   ("🟢", _final_label or "RESEARCH SNIPE",   "#10b981", "#031f17"),
            "RESEARCH_WATCH":   ("🟠", _final_label or "RESEARCH WATCH",   "#d97706", "#1f1407"),
            "RESEARCH_PASS":    ("🔴", _final_label or "RESEARCH PASS",    "#b91c1c", "#1f0707"),
        }.get(_final_decision)
        if _final_cfg is not None:
            _icon, _label, _color, _bg = _final_cfg
            _legacy_blocked: List[str] = []
            if bool(view.get("research_only_price_check")):
                _legacy_blocked.append("research_only_price_check:RESEARCH ONLY")
            if bool(view.get("presentation_risk_block")):
                _legacy_blocked.append("presentation_risk_block:MONITOR/unconfirmed_value")
            _legacy_action = str(view.get("action_label") or "").strip().upper()
            if _legacy_action in {"MONITOR", "REVIEW ONLY", "OVER MV", "NO BID YET", "NO VALID TARGET BID", "WATCH CLOSELY"}:
                _legacy_blocked.append(f"action_label:{_legacy_action}")
            _legacy_decision = str(view.get("execution_decision") or "").strip().upper()
            if _legacy_decision and _legacy_decision != _final_decision and _legacy_decision in {"WATCHLIST", "MONITOR", "SKIP", "PREPARE", "WATCH CLOSELY"}:
                _legacy_blocked.append(f"execution_decision:{_legacy_decision}")
            try:
                print(
                    f"[UI_FINAL_LABEL] title={_title_log} "
                    f"final_execution_decision={_final_decision} "
                    f"final_action_label={_label} "
                    f"rendered_label={_label} "
                    f"legacy_blocked={','.join(_legacy_blocked) if _legacy_blocked else 'none'}"
                )
                for _lb in _legacy_blocked:
                    print(
                        f"[UI_LEGACY_OVERRIDE_BLOCKED] title={_title_log} "
                        f"legacy_label={_lb} final_label={_label}"
                    )
                print(
                    f"[UI_RENDER_ACTION] title={_title_log} "
                    f"decision={_final_decision} "
                    f"label={_label} "
                    f"cta={_final_cta or _label} "
                    f"badge={_final_badge}"
                )
            except Exception:
                pass
            _sub = _final_cta or {
                "SNIPE_NOW":       "Copy bid · place bid",
                "UNDER_MV":        "Under market value · deal worth bidding",
                "WATCH":           "Near target bid",
                "PASS_OVERPRICED": "Pass — current price above max bid",
                "PASS":            "Pass for this scan",
                "RESEARCH_SNIPE":  "Research-grade · single-anchor pricing",
                "RESEARCH_WATCH":  "Research-grade · verify before bid",
                "RESEARCH_PASS":   "Research-grade · price above research band",
            }.get(_final_decision, "")
            return (
                f"<div style='display:inline-flex;align-items:center;gap:0.4rem;"
                f"background:{_bg};border:1px solid {_color}55;border-radius:6px;"
                f"padding:0.25rem 0.75rem;margin-bottom:0.5rem;'>"
                f"<span style='font-size:0.95rem'>{_icon}</span>"
                f"<span style='font-weight:700;color:{_color};font-size:0.85rem;letter-spacing:0.05em'>"
                f"{_label}</span>"
                f"<span style='color:#888888;font-size:0.74rem'>{_sub}</span>"
                f"</div>"
            )
    # Legacy fallbacks only fire when the final layer produced nothing usable.
    if bool(view.get("research_only_price_check")):
        return (
            "<div style='display:inline-flex;align-items:center;gap:0.4rem;"
            "background:#111827;border:1px solid #f59e0b55;border-radius:6px;"
            "padding:0.25rem 0.75rem;margin-bottom:0.5rem;'>"
            "<span style='font-size:0.95rem'>!</span>"
            "<span style='font-weight:700;color:#f59e0b;font-size:0.85rem;letter-spacing:0.05em'>RESEARCH ONLY</span>"
            "<span style='color:#b0b0b0;font-size:0.74rem'>PRICE CHECK NEEDED</span>"
            "</div>"
        )
    if bool(view.get("presentation_risk_block")):
        return (
            "<div style='display:inline-flex;align-items:center;gap:0.4rem;"
            "background:#111827;border:1px solid #88888855;border-radius:6px;"
            "padding:0.25rem 0.75rem;margin-bottom:0.5rem;'>"
            "<span style='font-size:0.95rem'>•</span>"
            "<span style='font-weight:700;color:#b0b0b0;font-size:0.85rem;letter-spacing:0.05em'>MONITOR</span>"
            "<span style='color:#888888;font-size:0.74rem'>unconfirmed value</span>"
            "</div>"
        )
    _dec = str(view.get("execution_decision") or "SKIP")
    _score = float(view.get("execution_score") or 0.0)
    _pressure = str(view.get("execution_pressure") or "LOW")
    _heat = float(view.get("whatnot_heat_score") or 0.0)
    _heat_fill = bool(view.get("heat_fill", False))
    _heat_upgraded = bool(view.get("heat_upgraded", False))
    if _dec == "PREPARE":
        _dec = "SNIPE"
    elif _dec == "PASS":
        _dec = "WATCH"
    # Premium label map — SKIP/WATCH never shown as-is on visible cards
    _cfg = {
        "EXECUTE_NOW":        ("🔴", "EXECUTE NOW",       "#dc2626", "#1a0505"),
        "SNIPE":              ("🟡", "PREPARE SNIPE",     "#d97706", "#1c1407"),
        "SNIPER_CANDIDATE":   ("🎯", "SNIPER CANDIDATE",  "#b45309", "#1a1000"),
        "WATCH":              ("🔵", "WATCHLIST",          "#2563eb", "#0a1628"),
        "SKIP":               ("🔵", "WATCHLIST",          "#2563eb", "#0a1628"),
    }.get(_dec, ("🔵", "WATCHLIST", "#2563eb", "#0a1628"))
    _icon, _label, _color, _bg = _cfg
    # Pressure annotation — only for high-urgency actionable labels
    _pressure_note = f" · {_pressure}" if (_pressure in {"URGENT", "HIGH"} and _dec in {"EXECUTE_NOW", "SNIPE"}) else ""
    # Heat annotation
    if _heat_fill:
        _heat_note = f" · 🔥 heat {_heat:.0f}"
    elif _heat_upgraded:
        _heat_note = f" · heat-boosted"
    elif _heat >= 65 and _dec in {"EXECUTE_NOW", "SNIPE", "SNIPER_CANDIDATE"}:
        _heat_note = f" · 🔥 {_heat:.0f}"
    else:
        _heat_note = ""
    # Score annotation — only for actionable tiers; watchlist/candidate show heat instead
    _score_note = f"score {_score:.0f}" if _dec in {"EXECUTE_NOW", "SNIPE"} else (f"heat {_heat:.0f}" if _heat > 0 else "")
    return (
        f"<div style='display:inline-flex;align-items:center;gap:0.4rem;"
        f"background:{_bg};border:1px solid {_color}33;border-radius:6px;"
        f"padding:0.25rem 0.75rem;margin-bottom:0.5rem;'>"
        f"<span style='font-size:0.95rem'>{_icon}</span>"
        f"<span style='font-weight:700;color:{_color};font-size:0.85rem;letter-spacing:0.05em'>"
        f"{_label}</span>"
        f"<span style='color:#888888;font-size:0.74rem'>{_score_note}{_pressure_note}{_heat_note}</span>"
        f"</div>"
    )


def _action_box_html(row: Dict[str, Any], view: Dict[str, Any]) -> str:
    """
    Prominent action box shown on every board card.
    Shows BUY UNDER / IDEAL BID / PROFIT / COMPS · CONF plus urgency label.
    Returns empty string if no target bid is available.
    """
    if bool(view.get("presentation_risk_block") or row.get("_presentation_risk_block")):
        return ""
    if bool(view.get("anchor_only_review") or row.get("_anchor_only_review")):
        return ""
    _as = dict(row.get("action_summary") or {})
    _buy_under = _as.get("bid_ceiling_value") or _as.get("buy_under") or view.get("bid_ceiling_value") or view.get("target_bid_price")
    if _buy_under is None:
        return ""
    _ideal_range = _as.get("ideal_range")
    _expected_profit = _as.get("expected_profit")
    _confidence = str(_as.get("confidence") or view.get("confidence_tier") or "LOW").upper()
    _comps = int(_as.get("comps") or 0)
    _secs = _safe_float(view.get("remaining_seconds"))

    # Urgency label
    if _secs is not None and _secs < 120:
        _urgency_html = (
            "<span style='background:#dc2626;color:#fff;font-weight:700;font-size:0.72rem;"
            "padding:0.1rem 0.5rem;border-radius:4px;margin-left:0.5rem;letter-spacing:0.06em'>"
            "🚨 BID NOW</span>"
        )
    elif _secs is not None and _secs < 300:
        _urgency_html = (
            "<span style='background:#d97706;color:#fff;font-weight:700;font-size:0.72rem;"
            "padding:0.1rem 0.5rem;border-radius:4px;margin-left:0.5rem;letter-spacing:0.06em'>"
            "⏱ LAST CHANCE</span>"
        )
    else:
        _urgency_html = ""

    _buy_str = _format_money(_buy_under)
    _range_str = (
        f"{_format_money(_ideal_range[0])} – {_format_money(_ideal_range[1])}"
        if _ideal_range and len(_ideal_range) == 2 else _buy_str
    )
    _profit_str = (
        f"+{_format_money(_expected_profit)}"
        if _expected_profit and float(_expected_profit) > 0 else "—"
    )
    _conf_color = (
        "#22c55e" if _confidence == "HIGH" else
        ("#f59e0b" if _confidence == "MEDIUM" else "#6b7280")
    )
    # Bid trust label — shown next to ACTION header
    _as_tb_conf = str(_as.get("bid_ceiling_confidence") or _as.get("target_bid_confidence") or view.get("bid_ceiling_confidence") or view.get("target_bid_confidence") or "").strip().upper()
    if not _as_tb_conf:
        # Infer from source if not stamped
        _src_chk = str(_as.get("bid_ceiling_source") or _as.get("target_bid_source_detail") or view.get("bid_ceiling_source") or view.get("target_bid_source_detail") or view.get("target_bid_source") or "")
        if _src_chk in {"STRICT", "adjusted_max_bid", "target_max_bid", "target_bid", "target_bid_price", "max_bid"}:
            _as_tb_conf = "HIGH"
        elif _src_chk in {"MEDIAN_DISCOUNT", "discount_median"}:
            _as_tb_conf = "MEDIUM"
        elif _src_chk in {"REVIEW_CEILING", "review_ceiling"}:
            _as_tb_conf = "REVIEW"
        else:
            _as_tb_conf = "MEDIUM"
    _trust_label_map = {
        "HIGH":   ("TARGET BID READY", "#22c55e"),
        "MEDIUM": ("CONSERVATIVE BID",  "#f59e0b"),
        "REVIEW": ("REVIEW BID",         "#b0b0b0"),
        "NONE":   ("NO BID YET",         "#6b7280"),
    }
    _tl_text, _tl_color = _trust_label_map.get(_as_tb_conf, ("CONSERVATIVE BID", "#f59e0b"))
    _trust_label_html = (
        f"<span style='color:{_tl_color};font-size:0.69rem;font-weight:600;"
        f"letter-spacing:0.04em;margin-left:0.6rem'>{_tl_text}</span>"
    )
    return (
        "<div style='background:#0a0f1a;border:1px solid #1e3a5f;border-radius:8px;"
        "padding:0.65rem 1rem;margin:0.4rem 0 0.55rem 0;'>"
        "<div style='display:flex;align-items:center;margin-bottom:0.45rem;'>"
        "<span style='font-weight:700;color:#888888;font-size:0.72rem;letter-spacing:0.06em'>"
        f"ACTION</span>{_trust_label_html}{_urgency_html}</div>"
        "<div style='display:grid;grid-template-columns:1fr 1fr;gap:0.25rem 1.2rem;'>"
        "<div><div style='color:#888888;font-size:0.7rem'>BUY UNDER</div>"
        f"<div style='color:#22c55e;font-weight:700;font-size:1.05rem'>{_buy_str}</div></div>"
        "<div><div style='color:#888888;font-size:0.7rem'>MAX BID</div>"
        f"<div style='color:#e2e8f0;font-weight:600;font-size:0.88rem'>{_range_str}</div></div>"
        "<div><div style='color:#888888;font-size:0.7rem'>EXPECTED PROFIT</div>"
        f"<div style='color:#22c55e;font-weight:700;font-size:0.88rem'>{_profit_str}</div></div>"
        "<div><div style='color:#888888;font-size:0.7rem'>COMPS · CONFIDENCE</div>"
        f"<div style='color:#e2e8f0;font-size:0.82rem'>{_comps} · "
        f"<span style='color:{_conf_color};font-weight:600'>{_confidence}</span></div></div>"
        "</div>"
        "</div>"
    )


def _render_es_monitor_card(_row: Dict[str, Any], _view: Dict[str, Any], _idx: int) -> None:
    _row = _es_strengthen_row_valuation(_row)
    _row = _ui_stamp_research_only_display(_row)
    _research_only = bool(_view.get("research_only_price_check") or _row.get("_research_only_price_check"))
    if _research_only:
        print(
            f"[UI_RESEARCH_ONLY_RENDER] title={str((_row or {}).get('title') or _row.get('raw_title') or '')[:160]} "
            f"current={_row.get('current_price')} "
            f"reason={_row.get('_research_only_reason')}"
        )
    _title = str(_view.get("title") or "Unknown listing").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    _meta = str(_view.get("meta_line") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    _time_label = str(_view.get("time_label") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    _live_signal = _score_live_signal_origin(_row)
    _origin_badge = str(_live_signal.get("origin_badge") or "MONITOR").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    _origin_reason = str(_view.get("premium_review_reason") or _view.get("origin_reason") or _live_signal.get("live_signal_reason") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    _monitor_reasons = []
    if bool(_view.get("promoted_live_candidate")) and str(_view.get("review_failure_reason") or "").strip():
        _monitor_reasons.append(str(_view.get("review_failure_reason") or ""))
    else:
        _monitor_reasons.append(_es_monitor_reason(_row, _view))
    if str(_view.get("confidence_tier") or "") not in {"high", "medium"}:
        _monitor_reasons.append("Valuation confidence still thin")
    if int((_safe_float(_row.get("mv_comp_count")) or _safe_float(_row.get("comp_count")) or _safe_float(_row.get("comps_count")) or 0)) <= 0:
        _monitor_reasons.append("Comp support is limited")
    _reason_badges = [{"label": str(_r2), "tone": "muted"} for _r2 in _monitor_reasons[:3] if str(_r2 or "").strip()]
    if _research_only:
        _reason_badges = [{"label": "EVIDENCE: NEEDS COMPS", "tone": "muted"}]
    _reason_html = _render_badge_html(_reason_badges)
    _badge_html = _render_badge_html(
        [
            {"label": "RESEARCH ONLY", "tone": "amber"},
            {"label": "PRICE CHECK NEEDED", "tone": "muted"},
        ]
        if _research_only
        else [{"label": _origin_badge, "tone": "amber"}]
    )
    _exec_label_html = _execution_decision_label_html(_view)
    st.markdown(
        f"""
        <div class='sw-es-card sw-es-card-secondary'>
          <div class='sw-es-card-top'>
            <div>
              <div class='sw-es-card-title' style='font-size:0.96rem'>{_idx + 1}. {_title}</div>
              <div class='sw-es-card-meta'>{_meta}</div>
            </div>
            <div class='sw-es-card-time'>{_time_label}</div>
          </div>
          {_exec_label_html}
          <div class='sw-es-badge-row'>{_badge_html}</div>
          <div class='sw-es-card-meta' style='margin:0.05rem 0 0.5rem 0;color:#b0b0b0;'>{_origin_reason or 'Real tracked auction. Keep it visible while valuation support, comps, or edge improve.'}</div>
          <div class='sw-es-badge-row'>{_reason_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if _view.get("target_bid_price") is not None:
        st.text_input(
            "Target Bid",
            value=str(_view.get("target_bid_display") or ""),
            key=f"es_target_bid_monitor_{_idx}_{str(_row.get('row_key') or _row.get('url') or _idx)}",
            disabled=True,
        )
    if bool(_row.get("alarm_worthy")):
        st.caption("SET ALARM - Alert before close using your bid settings")
    if _view.get("url"):
        st.markdown(f"<div class='sw-es-link'><a href='{_view['url']}' target='_blank'>Open listing</a></div>", unsafe_allow_html=True)


def _watchlist_heat_tags(row: Dict[str, Any], view: Dict[str, Any]) -> List[str]:
    """Return short heat descriptor tags for the watchlist card (e.g. ["AUTO", "/25", "SILVER PRIZM", "RC"])."""
    _tags: List[str] = []
    for _reason in list(row.get("heat_signal_reasons") or view.get("heat_signal_reasons") or []):
        _reason_text = str(_reason or "").strip().upper()
        if _reason_text and _reason_text not in _tags:
            _tags.append(_reason_text)
    _title_raw = str(row.get("title") or view.get("title") or "").lower()
    _scarcity = dict(row.get("scarcity_data") or {})
    _target_meta = dict(row.get("target_meta") or {})

    # Remove the naked one-of-one badge from this UI tag rail to avoid false serial claims.
    if (
        bool(_scarcity.get("is_one_of_one") or _target_meta.get("is_one_of_one") or row.get("is_one_of_one"))
        or "1/1" in _title_raw
    ):
        print("[CARD_BADGE_FIX] old='ONE OF ONE' new='' reason='badge_removed'")

    # AUTO
    if (
        bool(_target_meta.get("auto"))
        or bool(_scarcity.get("is_auto"))
        or bool(row.get("is_auto"))
        or any(_t in _title_raw for _t in (" auto", "/a ", "autograph"))
    ):
        _tags.append("AUTO")

    # Numbered
    _print_run = _safe_float(
        _scarcity.get("print_run") or _target_meta.get("print_run") or row.get("print_run")
    )
    if _print_run and 1 < _print_run <= 299:
        _tags.append(f"/{int(_print_run)}")

    # SSP
    if (
        bool(_target_meta.get("ssp"))
        or bool(_scarcity.get("is_ssp"))
        or bool(row.get("is_ssp"))
        or "ssp" in _title_raw
        or "short print" in _title_raw
    ):
        _tags.append("SSP")

    # Parallel
    _parallel = str(
        _target_meta.get("parallel")
        or row.get("parallel_family")
        or _scarcity.get("parallel_bucket")
        or _scarcity.get("rare_parallel")
        or ""
    ).strip()
    if _parallel:
        _tags.append(_parallel.upper().replace("_", " "))
    else:
        for _kw, _lbl in (
            ("silver prizm", "SILVER PRIZM"),
            ("blue prizm", "BLUE PRIZM"),
            ("gold prizm", "GOLD PRIZM"),
            ("holo", "HOLO"),
            ("refractor", "REFRACTOR"),
            ("chrome", "CHROME"),
        ):
            if _kw in _title_raw:
                _tags.append(_lbl)
                break

    # RC
    if (
        bool(_target_meta.get("rookie"))
        or bool(_scarcity.get("is_rookie"))
        or bool(row.get("is_rookie"))
        or any(_t in _title_raw for _t in (" rc ", " rc", "rookie"))
    ):
        _tags.append("RC")

    return _tags[:5]


def _render_es_watchlist_card(row: Dict[str, Any], view: Dict[str, Any], idx: int) -> None:
    """
    Watchlist card for high-heat, non-actionable rows.
    Shows identity, heat tags, MV (if valid), current price, and open link.
    Intentionally omits bid CTA — this is a monitoring signal, not a buy signal.
    """
    row = _ui_stamp_research_only_display(row if isinstance(row, dict) else dict(row or {}))
    _research_only = bool(view.get("research_only_price_check") or row.get("_research_only_price_check"))
    _surface_tier = str(view.get("surface_tier") or row.get("_surface_tier") or "").strip()
    _collector_heat = bool(view.get("collector_heat_surface") or row.get("_collector_heat_surface"))
    _collector_reasons = [
        str(_reason).strip().upper()
        for _reason in list(row.get("heat_signal_reasons") or view.get("heat_signal_reasons") or [])
        if str(_reason or "").strip()
    ]
    if _research_only:
        print(
            f"[UI_RESEARCH_ONLY_RENDER] title={str((row or {}).get('title') or row.get('raw_title') or '')[:160]} "
            f"current={row.get('current_price')} "
            f"reason={row.get('_research_only_reason')}"
        )
    _title = str(view.get("title") or "Unknown listing").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    _meta = str(view.get("meta_line") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    _time_label = str(view.get("time_label") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    _current_price_val = _ui_authoritative_current_price(row)
    _current_price = _format_money(_current_price_val) if _current_price_val is not None else "—"
    _heat = float(view.get("whatnot_heat_score") or 0.0)
    _exec_label_html = _execution_decision_label_html(view)
    _image_url = str(view.get("image_url") or row.get("source_image_url") or row.get("thumbnail") or "").strip()
    _image_html = (
        f"<img src='{_image_url}' style='width:64px;height:64px;object-fit:contain;border-radius:8px;"
        f"margin-right:12px;flex-shrink:0;border:1px solid #666666;background:#0b1220;padding:4px' />"
        if _image_url else ""
    )
    _anchor_only_review = bool(view.get("anchor_only_review") or row.get("_anchor_only_review"))
    _presentation_risk_block = bool(_research_only or view.get("presentation_risk_block") or row.get("_presentation_risk_block"))

    # MV display contract — prefer view-stamped display value, fall back to re-deriving
    _mv_valid = bool(view.get("mv_valid") or row.get("mv_valid"))
    _value_label = str(view.get("value_label") or ("Market Value" if _mv_valid else "Review Estimate"))
    _value_num = _safe_float(view.get("value_numeric"))
    if _value_num is None:
        _value_num = _safe_float(view.get("market_value_display")) if _value_label == "Market Value" else _safe_float(view.get("review_estimate_display"))
    if _value_num is None and _value_label == "Review Estimate":
        _value_num = _safe_float(row.get("review_estimate_value"))
    _mv_str = _format_money(_value_num) if (_value_num and _value_num > 0) else None
    # When MV is absent, show an explicit blocked reason instead of bare "—"
    _mv_blocked_label = (
        str(view.get("mv_blocked_reason_display") or "")
        or _mv_blocked_reason_label(row)
    )
    _bid_str = _format_money(_safe_float(view.get("bid_ceiling_value") or view.get("target_bid_price")))
    if _research_only:
        _value_label = "UNCONFIRMED / DO NOT USE"
        _mv_str = None
        _mv_blocked_label = "PRICE CHECK"
        _bid_str = "—"
    elif bool(view.get("_synthetic_no_mv") or row.get("_synthetic_no_mv") or row.get("_synthetic_trusted_exact")):
        # [SYNTHETIC_NO_MV_CARD] — Render-layer guard for synthetic-count rows
        # whose MV has been scrubbed by the engine ([SYNTHETIC_MV_SCRUB]). The
        # row claims `trusted_exact_comp_count = 1` but has zero priced comp
        # evidence; the value carried was a current-price echo, not a real
        # market value. Even though `_presentation_risk_block` is now False
        # for these rows (by design — we don't want the misleading "Single-
        # comp or fallback-based pricing" subtitle), the UI must still blank
        # the MV tile so it doesn't advertise the contaminated number.
        try:
            print(
                f"[SYNTHETIC_NO_MV_CARD] title={str(_title)[:140]} "
                f"prior_mv={_mv_str} current={_current_price} "
                f"reason=engine_synthetic_mv_scrub_marker_present"
            )
        except Exception:
            pass
        _value_label = "Reference Value"
        _mv_str = None
        _mv_blocked_label = "—"
    elif _presentation_risk_block:
        # [PRESENTATION_RISK_BLANK_CARD] — Untrusted-value contract.
        # When the engine flags this row's value as risky (single-comp,
        # fallback pricing, self-comp echo), the watchlist-card UI must
        # not advertise a dollar amount in the UNCONFIRMED VALUE tile.
        # Label stays "Unconfirmed Value"; the dollar number is replaced
        # by "—". Engine-side target/edge math is independent. This is
        # the render-layer twin of the view-model blanking applied in
        # _es_get_decision_view_model.
        try:
            _prior_mv_log = _mv_str
        except Exception:
            _prior_mv_log = None
        print(
            f"[PRESENTATION_RISK_BLANK_CARD] title={str(_title)[:120]} "
            f"prior_mv={_prior_mv_log} current={_current_price} "
            f"bid={_bid_str}"
        )
        _value_label = "Unconfirmed Value"
        _mv_str = None
        _mv_blocked_label = "—"

    # ── Final-action label override (UI truth alignment) ──────────────────
    # Per business doc: "Final-action truth should override legacy UI labels."
    # Read final_execution_decision from view/row and use it to drive the
    # badge stack. Falls through to legacy logic only when the final-action
    # layer hasn't produced a real decision (rare).
    _final_decision_ui = str(
        view.get("final_execution_decision")
        or row.get("execution_final_decision")
        or row.get("final_execution_decision")
        or ""
    ).strip().upper()
    _final_label_ui = str(view.get("final_action_label") or row.get("final_action_label") or "").strip()
    _final_conf_label = str(view.get("target_bid_confidence") or row.get("target_bid_confidence") or "").strip().upper()
    _conf_chip = (
        {"label": f"CONF {_final_conf_label}", "tone": "green" if _final_conf_label == "HIGH" else ("amber" if _final_conf_label == "MEDIUM" else "muted")}
        if _final_conf_label and _final_conf_label != "NONE"
        else None
    )
    _final_action_badges_map = {
        "SNIPE_NOW":        [{"label": "SNIPE NOW", "tone": "green"},        {"label": "TARGET BID READY", "tone": "green"}],
        "UNDER_MV":         [{"label": "UNDER MV", "tone": "blue"},          {"label": "BELOW MARKET", "tone": "blue"}],
        "WATCH":            [{"label": "WATCH", "tone": "amber"},            {"label": "NEAR TARGET", "tone": "muted"}],
        "PASS_OVERPRICED":  [{"label": "PASS — OVERPRICED", "tone": "red"},  {"label": "ABOVE TARGET +5%", "tone": "muted"}],
        "PASS":             [{"label": "PASS", "tone": "muted"},             {"label": "NO TARGET BID", "tone": "muted"}],
        "RESEARCH_SNIPE":   [{"label": "RESEARCH SNIPE", "tone": "green"},   {"label": "RESEARCH-GRADE", "tone": "amber"}],
        "RESEARCH_WATCH":   [{"label": "RESEARCH WATCH", "tone": "amber"},   {"label": "RESEARCH-GRADE", "tone": "amber"}],
        "RESEARCH_PASS":    [{"label": "RESEARCH PASS", "tone": "red"},      {"label": "ABOVE RESEARCH BAND", "tone": "muted"}],
    }
    _final_badges_override = _final_action_badges_map.get(_final_decision_ui)

    # Heat tags
    _tag_badges = [{"label": _t, "tone": "blue"} for _t in _watchlist_heat_tags(row, view)]
    if _final_badges_override is not None:
        # Final-action truth wins. Use the final-action badge stack with the
        # confidence chip appended. Skip every legacy branch below.
        _tag_badges = list(_final_badges_override)
        if _conf_chip:
            _tag_badges.append(_conf_chip)
        try:
            print(
                f"[UI_HEADER_RESOLUTION] "
                f"title={str((row or {}).get('title') or '')[:120]} "
                f"final_decision={_final_decision_ui} "
                f"badge_stack={[b['label'] for b in _tag_badges]} "
                f"legacy_overridden=1"
            )
        except Exception:
            pass
    elif _research_only:
        _tag_badges = [
            {"label": "HIGH-HEAT RESEARCH" if _collector_heat else "RESEARCH ONLY", "tone": "amber"},
            {"label": "PRICE CHECK NEEDED", "tone": "muted"},
            {"label": (_collector_reasons[0] if _collector_reasons else "EVIDENCE: NEEDS COMPS"), "tone": "blue" if _collector_reasons else "muted"},
        ]
    elif _surface_tier == "verified_watchlist":
        _tag_badges = [
            {"label": "WATCHLIST", "tone": "blue"},
            {"label": "VERIFIED VALUE", "tone": "green"},
            {"label": "EDGE REQUIRED", "tone": "muted"},
        ]
    elif _surface_tier == "review_watchlist_verify":
        _tag_badges = [
            {"label": "WATCHLIST - VERIFY", "tone": "amber"},
            {"label": "REFERENCE VALUE", "tone": "muted"},
            {"label": "NO SNIPE", "tone": "red"},
        ]
    elif _collector_heat:
        _tag_badges = [{"label": "HIGH-HEAT RESEARCH", "tone": "amber"}] + [
            {"label": _reason, "tone": "blue"} for _reason in _collector_reasons[:2]
        ]
    elif _presentation_risk_block:
        _tag_badges = [
            {"label": "MONITOR", "tone": "muted"},
            {"label": "UNCONFIRMED VALUE", "tone": "amber"},
            {"label": "DO NOT CHASE", "tone": "red"},
        ]
    elif str(row.get("evidence_render_source") or "").strip() == "review_payload":
        if _anchor_only_review:
            _tag_badges.append({"label": "REVIEW ONLY", "tone": "amber"})
            _tag_badges.append({"label": "NO VERIFIED COMP EVIDENCE", "tone": "muted"})
        else:
            _tag_badges.append({"label": "REVIEW ESTIMATE", "tone": "amber"})
        if (not _anchor_only_review) and bool(row.get("target_bid_ready") or view.get("target_bid_ready")):
            _tag_badges.append({"label": "TARGET BID READY", "tone": "green"})
        if (not _anchor_only_review) and int(row.get("trusted_exact_comp_count") or 0) <= 0 and int(row.get("support_comp_count") or 0) <= 0:
            _tag_badges.append({"label": "NO COMP SUPPORT", "tone": "muted"})
    _tag_html = _render_badge_html(_tag_badges)

    # Reason line
    _evidence_contract = _ui_evidence_render_contract(row)
    _comp_truth = _ui_comp_truth_split(row)
    _comp_count = int(_evidence_contract.get("display_count") or 0)
    _comp_label = str(_evidence_contract.get("label") or "")
    _detail_keys_present = list(_evidence_contract.get("detail_keys_present") or [])
    _detail_rows = list(_evidence_contract.get("detail_rows") or [])
    _evidence_renderable = int(_evidence_contract.get("evidence_renderable") or 0)
    _anchor_only_review = bool(_anchor_only_review or _evidence_contract.get("anchor_only_review"))
    _title_for_log = str(view.get("title") or row.get("title") or row.get("source_title") or "").strip()
    # [SELF_COMP_DISPLAY_FILTER] — strip evidence rows that are the listing
    # itself. Two detection axes:
    #   1. iid match — comp's item_id/iid/listing_id equals the listing's
    #   2. title overlap — comp's normalized title matches >=85% of listing's
    #      normalized title (accommodates minor seller-code suffix diffs)
    # Without this, the comp panel rendered the listing's own current price
    # and title as "comp evidence", creating false MV confidence in the user.
    # Engine-side MV math is untouched — this only affects the displayed
    # evidence panel.
    try:
        _self_iid = str(
            row.get("item_id")
            or row.get("itemId")
            or row.get("source_item_id")
            or ""
        ).strip()
        _raw_self_title = str(row.get("title") or row.get("source_title") or "").lower()
        _self_title_norm = re.sub(r"\s+", " ", _raw_self_title).strip()

        def _is_self_comp_row(_c: Any) -> bool:
            if not isinstance(_c, dict):
                return False
            _c_iid_local = str(
                _c.get("item_id")
                or _c.get("iid")
                or _c.get("listing_id")
                or _c.get("source_item_id")
                or ""
            ).strip()
            if _self_iid and _c_iid_local and _self_iid == _c_iid_local:
                return True
            _c_title_raw = str(
                _c.get("title")
                or _c.get("sold_title")
                or _c.get("comp_title")
                or ""
            ).lower()
            _c_title_norm = re.sub(r"\s+", " ", _c_title_raw).strip()
            if not _c_title_norm or not _self_title_norm:
                return False
            if _c_title_norm == _self_title_norm:
                return True
            _c_tokens = set(_c_title_norm.split())
            _s_tokens = set(_self_title_norm.split())
            if not _c_tokens or not _s_tokens:
                return False
            _denom = float(max(1, min(len(_c_tokens), len(_s_tokens))))
            _overlap_pct = len(_c_tokens & _s_tokens) / _denom
            return _overlap_pct >= 0.85

        _filtered_detail_rows: List[Dict[str, Any]] = []
        _self_filtered_count = 0
        for _dr in list(_detail_rows or []):
            if _is_self_comp_row(_dr):
                _self_filtered_count += 1
                continue
            _filtered_detail_rows.append(_dr)
        if _self_filtered_count > 0:
            print(
                f"[SELF_COMP_DISPLAY_FILTER] "
                f"title={_title_for_log[:140]} "
                f"self_iid={_self_iid[:32]} "
                f"removed_count={_self_filtered_count} "
                f"pre={len(_detail_rows)} post={len(_filtered_detail_rows)}"
            )
            _detail_rows = _filtered_detail_rows
            _comp_count = max(0, _comp_count - _self_filtered_count)
    except Exception as _self_filter_exc:
        print(f"[SELF_COMP_DISPLAY_FILTER] error_type={type(_self_filter_exc).__name__} msg={str(_self_filter_exc)[:120]}")
    print(
        f"[CARD_COMP_PAYLOAD] title={_title_for_log[:140]} comp_count={_comp_count} "
        f"detail_keys_present={_detail_keys_present} detail_rows={len(_detail_rows)}"
    )
    print(
        f"[CARD_COMP_RENDER] title={_title_for_log[:140]} "
        f"rendered_detail={1 if (_comp_count > 0 and bool(_detail_rows)) else 0} rendered_fallback=0"
    )
    print(
        f"[CARD_COMP_POSITION] title={_title_for_log[:140]} inserted_inside_card=1"
    )
    _comp_render_html = _card_comp_render_status_html(
        comp_count=_comp_count,
        detail_rows=_detail_rows,
        label=_comp_label,
        evidence_renderable=_evidence_renderable,
    )
    _edge = float(view.get("edge_pct") or row.get("edge_pct") or 0.0)
    _commercial = float(view.get("commercial_signal_score") or row.get("commercial_signal_score") or 0.0)
    _reason_text = "Worth monitoring"
    _title_raw = str(row.get("title") or view.get("title") or "").lower()
    # Final-action subtitle override: when we have a real final decision, the
    # subtitle should match it, not legacy WATCHLIST / HIGH-HEAT RESEARCH text.
    _final_subtitle_map = {
        "SNIPE_NOW":        "SNIPE NOW — bid window open",
        "UNDER_MV":         "UNDER MV — bidding below market value",
        "WATCH":            "WATCH — near target",
        "PASS_OVERPRICED":  "PASS — overpriced (review later)",
        "PASS":             "PASS — no target bid",
        "RESEARCH_SNIPE":   "RESEARCH — snipe range",
        "RESEARCH_WATCH":   "RESEARCH — verify before bid",
        "RESEARCH_PASS":    "RESEARCH — above band",
    }
    if _final_decision_ui and _final_decision_ui in _final_subtitle_map:
        _reason_text = _final_subtitle_map[_final_decision_ui]
    elif _research_only:
        _reason_text = "HIGH-HEAT RESEARCH" if _collector_heat else "PRICE CHECK NEEDED"
    elif _surface_tier == "verified_watchlist":
        _reason_text = "WATCHLIST"
    elif _surface_tier == "review_watchlist_verify":
        _reason_text = "WATCHLIST - VERIFY"
    elif _collector_heat:
        _reason_text = "HIGH-HEAT RESEARCH"
    elif _presentation_risk_block:
        _reason_text = str(view.get("presentation_headline") or row.get("_presentation_headline") or "Unconfirmed valuation")
    elif _anchor_only_review:
        _reason_text = "No verified comp evidence yet"
    elif "auto" in _title_raw or "autograph" in _title_raw:
        _reason_text = "Auto / SSP interest"
    elif any(_tok in _title_raw for _tok in ["zebra", "gold", "genesis", "kaboom", "downtown", "manga", "color blast"]):
        _reason_text = "Premium parallel"
    elif str(view.get("serial_denominator") or row.get("serial_denominator") or "").strip():
        _reason_text = "Numbered upside"
    elif _comp_count >= 4:
        _reason_text = "Strong comp activity"
    elif _commercial >= 22.0:
        _reason_text = "Strong commercial appeal"
    elif _heat >= 55:
        _reason_text = "Worth monitoring"

    # [SYNTHETIC_NO_MV_SUBTITLE_GUARD] — when SYNTHETIC_MV_SCRUB has fired on
    # this row (MV was current_price echoing through a fallback, no real
    # priced evidence), the misleading "Single-comp or fallback-based
    # pricing" subtitle should NOT appear — that subtitle implies the engine
    # has SOME pricing evidence, but for these rows we have NONE. Use a
    # neutral "Heat N" subtitle instead so the user isn't told there's a
    # comp basis when there isn't.
    _synthetic_no_mv_marker = bool(
        view.get("_synthetic_no_mv")
        or row.get("_synthetic_no_mv")
        or row.get("_synthetic_trusted_exact")
    )
    _submeta_parts = (
        ["Evidence: needs comps"]
        if _research_only
        else (
            [f"Heat {_heat:.0f}"]
            if (_presentation_risk_block and _synthetic_no_mv_marker)
            else [str(view.get("presentation_subhead") or row.get("_presentation_subhead") or "Single-comp or fallback-based pricing")] if _presentation_risk_block
            else [f"Heat {_heat:.0f}"]
        )
    )
    if _mv_str and not _presentation_risk_block:
        _submeta_parts.append(f"{'Review Est' if _value_label == 'Review Estimate' else 'MV'} {_mv_str}")
    if _bid_str != "—" and str(view.get("bid_ceiling_confidence") or "").upper() in {"HIGH", "MEDIUM", "REVIEW"}:
        if not _presentation_risk_block:
            _submeta_parts.append(f"Bid {_bid_str}")
    if (not _presentation_risk_block) and _edge >= 5:
        _submeta_parts.append(f"{_edge:.0f}% edge")
    elif (not _presentation_risk_block) and _comp_count > 0 and _evidence_renderable:
        _submeta_parts.append(f"{_comp_count} {_comp_label.lower()}")
    _submeta = " · ".join(_submeta_parts[:4])

    _bid_metric_label = "Reference Bid" if _presentation_risk_block else "Max Bid"
    _metric_rows = None
    if _research_only:
        _metric_rows = [
            ("CURRENT PRICE", _current_price),
            ("UNCONFIRMED / DO NOT USE", "PRICE CHECK"),
            ("EVIDENCE", "needs comps"),
        ]
    _bid_metric_value = _bid_str if (_presentation_risk_block and _bid_str != "â€”") else (_bid_str if _bid_str != "â€”" else "NO BID YET")
    # [COMPS_TRUTH_FALLBACK] — the COMPS box used to print "—" whenever the
    # display layer couldn't surface detail rows for the comp panel below.
    # That created a UX contradiction: rows like Gunnar Henderson Yellow
    # Refractor showed MV $432 (so comps clearly exist on the engine side)
    # but the COMPS box read "—". Trust contract violation: the box should
    # not silently report "no comps" when the engine has them.
    # New rule:
    #   1. _comp_count > 0 + _evidence_renderable → show count (existing path)
    #   2. _comp_count > 0 + not renderable + NOT synthetic MV → show count
    #      from engine's mv_comp_count / comp_count fallback (truth bridge)
    #   3. synthetic MV (_synthetic_no_mv stamp) → "—" (no real comps)
    #   4. genuinely zero comps → "—"
    _engine_comp_count = int(
        (_safe_float(row.get("mv_comp_count")) or 0)
        or (_safe_float(row.get("comp_count")) or 0)
        or (_safe_float(row.get("comps_count")) or 0)
        or (_safe_float(row.get("trusted_exact_comp_count")) or 0)
        or (_safe_float(row.get("support_comp_count")) or 0)
    )
    if _comp_count > 0 and _evidence_renderable:
        _comp_box_value = str(_comp_count)
    elif _engine_comp_count > 0 and not _synthetic_no_mv_marker:
        # Engine has comps; UI can't surface detail rows. Show truth.
        _comp_box_value = str(_engine_comp_count)
    else:
        _comp_box_value = "—"
    _metric_html = "".join(
        f"<div class='sw-es-metric' style='padding:0.45rem 0.55rem;background:#0b1220;border-color:#1f2d42'>"
        f"<div class='sw-es-metric-label'>{_label}</div><div class='sw-es-metric-value' style='font-size:0.88rem'>{_value}</div></div>"
        for _label, _value in (_metric_rows or [
            ("Current", _current_price),
            (_value_label, _mv_str or _mv_blocked_label),
            (_bid_metric_label, _bid_metric_value),
            (_comp_label or "Evidence", _comp_box_value),
        ])
    )

    st.markdown(
        f"""
        <div class='sw-es-card sw-es-card-secondary' style='border-color:#22344a;box-shadow:0 10px 26px rgba(2,6,23,0.26);background:linear-gradient(180deg,#0b111a 0%,#091019 100%)'>
          <div class='sw-es-card-top' style='display:flex;align-items:flex-start;'>
            {_image_html}
            <div style='flex:1;min-width:0;'>
              <div class='sw-es-card-title' style='font-size:0.98rem;color:#e2e8f0'>{idx + 1}. {_title}</div>
              <div class='sw-es-card-meta' style='color:#7c8ea5'>{_meta}</div>
              <div class='sw-es-card-meta' style='margin-top:0.18rem;color:#fafafa;font-size:0.82rem;font-weight:600'>{_reason_text}</div>
            </div>
            <div class='sw-es-card-time'>{_time_label}</div>
          </div>
          {_exec_label_html}
          <div class='sw-es-badge-row'>{_tag_html}</div>
          <div class='sw-es-card-meta' style='margin:0.35rem 0 0.55rem 0;color:#b0b0b0;font-size:0.8rem'>{_submeta}</div>
          <div class='sw-es-metrics' style='grid-template-columns:repeat(4,minmax(88px,1fr));gap:0.45rem'>{_metric_html}</div>
          {_comp_render_html}
        </div>
        """,
        unsafe_allow_html=True,
    )
    if view.get("url"):
        st.markdown(
            f"<div class='sw-es-link'><a href='{view['url']}' target='_blank'>Open listing</a></div>",
            unsafe_allow_html=True,
        )
    if bool(row.get("alarm_worthy")):
        st.caption("SET ALARM - Alert before close using your bid settings")


def _render_es_prep_board_card(row: Dict[str, Any], view: Dict[str, Any], idx: int) -> None:
    row = _es_strengthen_row_valuation(row if isinstance(row, dict) else dict(row or {}))
    row = _apply_cached_prep_comp_payload(row)
    _prep_comp_cache_key = _prep_comp_cache_key_for_ui(row)
    _prep_comp_completed = bool(row.get("prep_comp_completed"))
    _prep_comp_ready = bool(row.get("prep_comp_ready") or row.get("prep_verified_value"))
    _prep_comp_without_verified_mv = bool(row.get("prep_comp_completed_without_verified_mv"))
    _prep_surface_quality = str(row.get("prep_surface_quality") or "").strip().lower()
    _prep_discovery_fallback = bool(_prep_surface_quality == "discovery_fallback")
    if _prep_discovery_fallback:
        _prep_comp_ready = False
        _prep_comp_without_verified_mv = True

    def _prep_recovery_display_rows(_row: Dict[str, Any]) -> List[Dict[str, Any]]:
        _out: List[Dict[str, Any]] = []
        for _key in (
            "renderable_evidence_rows",
            "evidence_rows",
            "comp_rows",
            "review_evidence_rows",
        ):
            _rows = _row.get(_key)
            if not isinstance(_rows, list):
                continue
            for _r in _rows:
                if not isinstance(_r, dict):
                    continue
                _title = str(
                    _r.get("sold_title")
                    or _r.get("listing_title")
                    or _r.get("comp_title")
                    or _r.get("title")
                    or ""
                ).strip()
                _price = _safe_float(_r.get("sold_price") or _r.get("price") or _r.get("comp_price") or _r.get("sale_price"))
                _source = str(_r.get("evidence_source") or _r.get("source") or "").strip().lower()
                _placeholder = any(
                    _bad in _title.lower()
                    for _bad in ("comp evidence", "minimum renderable evidence", "minimum_renderable_evidence", "price anchor fallback", "price_anchor_fallback", "reference anchor")
                )
                if _title and _price is not None and _price > 0 and not _placeholder:
                    _clean = dict(_r)
                    _clean.setdefault("sold_title", _title)
                    _clean.setdefault("sold_price", float(_price))
                    _clean.setdefault("evidence_source", _source or "verified_sold_comp_recovery")
                    _out.append(_clean)
        return _out[:3]

    _recovered_display_rows = _prep_recovery_display_rows(row)
    if _prep_comp_ready and (bool(row.get("_prep_has_verified_sold_comps")) or int(row.get("_prep_verified_comp_count") or 0) > 0 or _recovered_display_rows):
        if _recovered_display_rows:
            row["renderable_evidence_rows"] = [dict(_r) for _r in _recovered_display_rows]
            row["evidence_rows"] = [dict(_r) for _r in _recovered_display_rows]
            row["renderable_evidence_count"] = len(_recovered_display_rows)
        row["_prep_has_verified_sold_comps"] = True
        row["_prep_verified_comp_count"] = max(int(row.get("_prep_verified_comp_count") or 0), len(_recovered_display_rows))
        row["evidence_renderable"] = 1
        row["evidence_source"] = row.get("evidence_source") or "verified_sold_comp_recovery"
        row["evidence_render_source"] = row.get("evidence_render_source") or "verified_sold_comp_recovery"
        row["reference_label"] = "Reference"
        row["_prep_display_mode"] = "verified_sold_titles"

    def _prep_strip_html(_value: Any, fallback: str = "") -> str:
        _raw = str(_value or fallback or "")
        _decoded = unescape(_raw)
        if any(_token in f"{_raw} {_decoded}".lower() for _token in ("<div", "</div>", "class=", "style=")):
            _cleaned = re.sub(r"<[^>]*>", " ", _decoded)
            _cleaned = re.sub(r"\s+", " ", _cleaned).strip()
            print(f"[PREP_RENDER_SANITIZE] raw_has_html=1 cleaned={_cleaned[:120]}")
        else:
            _cleaned = _decoded.strip()
        return _cleaned or fallback or ""

    _title_raw = str(view.get("title") or row.get("title") or row.get("source_title") or "Unknown listing")
    _meta_raw = "Live ending-soon auction"
    _time_raw = str(view.get("time_label") or row.get("time_left") or row.get("time_remaining_display") or "")
    _title_text = _prep_strip_html(_title_raw, "Unknown listing")
    _meta_text = _prep_strip_html(_meta_raw, "Live ending-soon auction")
    _time_text = _prep_strip_html(_time_raw, "")
    _final_text_blob = f"{_title_text} {_meta_text} {_time_text}".lower()
    _final_has_html_blob = any(_token in _final_text_blob for _token in ("<div", "</div>", "class=", "style="))
    print(
        f"[PREP_RENDER_SOURCE_PATH] "
        f"title_raw={_title_raw[:160]} "
        f"title_clean={_title_text[:160]} "
        f"using_legacy_html_path=0"
    )
    print(
        f"[PREP_RENDER_FINAL_TEXT] "
        f"title={_title_text[:160]} "
        f"meta={_meta_text[:120]} "
        f"time_left={_time_text[:80]}"
    )
    if _final_has_html_blob:
        print(
            f"[PREP_RENDER_HARD_FAIL] "
            f"title={_title_text[:160]} "
            f"meta={_meta_text[:120]} "
            f"time_left={_time_text[:80]}"
    )
    _current_val = _ui_authoritative_current_price(row)
    _target_val = _safe_float(row.get("prep_target_bid") or row.get("target_bid") or row.get("target_bid_price") or row.get("bid_ceiling_value")) if (_prep_comp_ready and not _prep_discovery_fallback) else None
    _reference_val = _safe_float(row.get("prep_reference_value") or row.get("review_estimate") or row.get("review") or row.get("true_mv") or row.get("review_estimate_value") or row.get("true_market_value")) if (_prep_comp_ready and not _prep_discovery_fallback) else None
    _current = _format_money(_current_val) if _current_val is not None else "n/a"
    _target = _format_money(_target_val) if _target_val is not None else "n/a"
    _reference = _format_money(_reference_val) if _reference_val is not None else "n/a"
    _reference_equals_current = bool(
        _current_val is not None
        and _reference_val is not None
        and abs(float(_reference_val) - float(_current_val)) <= max(0.01, abs(float(_current_val)) * 0.01)
    )
    _prep_has_verified_display = bool(_prep_comp_ready and (row.get("_prep_has_verified_sold_comps") or int(row.get("_prep_verified_comp_count") or row.get("prep_verified_comp_count") or 0) > 0))
    _reference_label = str(row.get("prep_reference_label") or ("Reference" if _prep_has_verified_display else ("Reference (anchor)" if _reference_equals_current else "Reference")))
    _reason = str(row.get("prep_time_bucket") or row.get("prep_board_reason") or "premium_not_actionable").strip()
    _reason_label = "ABOVE BID" if _reason == "price_above_bid" else ("OUTSIDE WINDOW" if _reason == "outside_window" else "NOT ACTIONABLE YET")
    _listing_url = str(
        row.get("listing_url")
        or view.get("listing_url")
        or row.get("url")
        or view.get("url")
        or row.get("item_url")
        or view.get("item_url")
        or row.get("canonical_url")
        or row.get("ebay_url")
        or row.get("_board_url")
        or row.get("source_url")
        or row.get("item_web_url")
        or row.get("itemWebUrl")
        or row.get("source_view_url")
        or row.get("view_item_url")
        or row.get("auction_url")
        or row.get("source_listing_url")
        or ""
    ).strip()
    if not _listing_url:
        _item_id_for_url = str(
            row.get("item_id")
            or row.get("source_item_id")
            or row.get("listing_id")
            or row.get("ebay_item_id")
            or ""
        ).strip()
        if _item_id_for_url and _item_id_for_url.isdigit():
            _listing_url = f"https://www.ebay.com/itm/{_item_id_for_url}"
    _item_id_for_log = str(
        row.get("item_id")
        or row.get("source_item_id")
        or row.get("itemId")
        or ""
    ).strip()

    def _prep_thumb_url(_row: Dict[str, Any], _view: Dict[str, Any]) -> Tuple[str, str]:
        _image_fields = (
            "image_url",
            "thumbnail_url",
            "thumb_url",
            "photo_url",
            "primary_image",
            "gallery_image",
            "ebay_image_url",
            "listing_image_url",
            "card_image",
            "image",
            "source_image_url",
            "thumbnail",
        )
        for _source_name, _source in (("view", _view), ("row", _row)):
            if not isinstance(_source, dict):
                continue
            for _field in _image_fields:
                _value = _source.get(_field)
                if isinstance(_value, dict):
                    _value = (
                        _value.get("url")
                        or _value.get("imageUrl")
                        or _value.get("src")
                        or _value.get("href")
                        or ""
                    )
                elif isinstance(_value, list):
                    _value = _value[0] if _value else ""
                    if isinstance(_value, dict):
                        _value = (
                            _value.get("url")
                            or _value.get("imageUrl")
                            or _value.get("src")
                            or _value.get("href")
                            or ""
                        )
                _url = str(_value or "").strip()
                if _url and _url.lower() not in {"none", "null", "nan"}:
                    return _url, f"{_source_name}.{_field}"
        return "", ""

    _thumb_url, _thumb_field = _prep_thumb_url(row, view if isinstance(view, dict) else {})
    _has_thumb = bool(_thumb_url)
    print(
        f"[PREP_THUMB_RESOLVE] "
        f"title={_title_text[:160]} "
        f"has_thumb={1 if _has_thumb else 0} "
        f"thumb_field={_thumb_field} "
        f"thumb_url_present={1 if bool(_thumb_url) else 0}"
    )

    def _prep_evidence_rows(_row: Dict[str, Any]) -> List[Dict[str, Any]]:
        for _key in (
            "renderable_evidence_rows",
            "minimum_renderable_evidence",
            "evidence_rows",
            "comp_rows",
            "review_evidence_rows",
            "review_evidence_payload",
        ):
            _rows = _row.get(_key)
            if isinstance(_rows, list) and _rows:
                return [dict(_r or {}) if isinstance(_r, dict) else {"title": str(_r)} for _r in _rows[:3]]
        return []

    _evidence_rows = _prep_evidence_rows(row) if (_prep_comp_completed or _prep_comp_ready) else []
    if _prep_has_verified_display and _recovered_display_rows:
        _evidence_rows = [dict(_r) for _r in _recovered_display_rows]
    _evidence_count = len(_evidence_rows)
    _prep_comp_titles_rendered = 0
    _prep_comp_prices_rendered = 0
    _prep_comp_synthetic_rows = 0
    _prep_comp_lines: List[str] = []
    _parent_evidence_source = str(
        row.get("evidence_source")
        or row.get("evidence_render_source")
        or row.get("review_evidence_source")
        or row.get("mv_source")
        or row.get("market_value_source")
        or row.get("valuation_source_clean")
        or ""
    ).strip().lower()
    _fallback_evidence_sources = {"minimum_renderable_evidence", "price_anchor_fallback"}
    _placeholder_titles = {
        "",
        "comp evidence",
        "minimum_renderable_evidence",
        "review_payload",
        "market value",
    }
    _current_title_norm = re.sub(r"\s+", " ", _title_text or "").strip().lower()
    _target_for_fake_check = _safe_float(row.get("target_bid") or row.get("target_bid_price") or row.get("bid_ceiling_value"))

    def _is_verified_prep_sold_comp(_erow: Dict[str, Any]) -> Tuple[bool, str, Optional[float]]:
        _price_val = _safe_float(
            _erow.get("sold_price")
            or _erow.get("price")
            or _erow.get("comp_price")
        )
        _sold_title_raw = (
            _erow.get("sold_title")
            or _erow.get("listing_title")
            or _erow.get("comp_title")
        )
        _generic_title_raw = _erow.get("title")
        _sold_title = _prep_strip_html(_sold_title_raw or "", "")
        _generic_title = _prep_strip_html(_generic_title_raw or "", "")
        _title = _sold_title or _generic_title
        _title_norm = re.sub(r"\s+", " ", str(_title or "")).strip().lower()
        _row_source = str(
            _erow.get("evidence_source")
            or _erow.get("source")
            or _erow.get("comp_source")
            or _parent_evidence_source
            or ""
        ).strip().lower()
        _has_sold_title_field = bool(str(_sold_title_raw or "").strip())

        if _price_val is None:
            return False, "", None
        if not _title_norm or _title_norm in _placeholder_titles:
            return False, "", _price_val
        if _row_source in _fallback_evidence_sources and not _has_sold_title_field:
            return False, "", _price_val
        if _title_norm == _current_title_norm and not _has_sold_title_field:
            return False, "", _price_val
        if _target_for_fake_check is not None and abs(float(_price_val) - float(_target_for_fake_check)) <= 0.01 and not _has_sold_title_field:
            return False, "", _price_val
        return True, _title, _price_val

    for _erow in _evidence_rows:
        _verified, _verified_title, _eprice_val = _is_verified_prep_sold_comp(_erow)
        if not _verified:
            _prep_comp_synthetic_rows += 1
            continue
        _eprice = _format_money(_eprice_val) if _eprice_val is not None else "n/a"
        if _eprice_val is not None:
            _prep_comp_prices_rendered += 1
        _etitle = _verified_title
        if _etitle and _etitle != "Comp evidence":
            _prep_comp_titles_rendered += 1
        _egrade = _prep_strip_html(
            _erow.get("grade")
            or _erow.get("grade_label")
            or "",
            "",
        )
        _label = _etitle or "Comp evidence"
        if _egrade and _egrade.lower() not in _label.lower():
            _label = f"{_label} {_egrade}"
        _prep_comp_lines.append(f"{_eprice} - {_label[:120]}")
    _fallback_blocked = bool(_parent_evidence_source in _fallback_evidence_sources and not _prep_comp_lines and _evidence_count > 0)
    print(
        f"[PREP_CARD_EVIDENCE] "
        f"title={_title_text[:160]} "
        f"evidence_count={_evidence_count} "
        f"has_listing_url={1 if _listing_url else 0} "
        f"reference_equals_current={1 if _reference_equals_current else 0}"
    )
    print(
        f"[PREP_COMP_FILTER] "
        f"title={_title_text[:160]} "
        f"input_rows={_evidence_count} "
        f"verified_rows={len(_prep_comp_lines)} "
        f"synthetic_rows={_prep_comp_synthetic_rows} "
        f"evidence_source={_parent_evidence_source or 'none'} "
        f"fallback_blocked={1 if _fallback_blocked else 0}"
    )

    with st.container(border=True):
        _layout_cols = st.columns([1.1, 5])
        with _layout_cols[0]:
            if _thumb_url:
                try:
                    st.image(_thumb_url, width=112)
                except Exception:
                    _thumb_url = ""
                    st.caption("")
            else:
                st.caption("")
        with _layout_cols[1]:
            _header_cols = st.columns([5, 1.2])
            with _header_cols[0]:
                st.markdown(f"**{idx + 1}. {escape(_title_text)}**")
                st.caption(_meta_text)
            with _header_cols[1]:
                st.caption(_time_text)
            st.markdown(f"`PREP` `NOT ACTIONABLE YET` `{_reason_label}`")
            st.caption("Monitor only. Do not treat as a sniper candidate.")
            if _prep_comp_ready:
                _metric_cols = st.columns(3)
                _metric_cols[0].metric("Current", _current)
                _metric_cols[1].metric(_reference_label, _reference)
                _metric_cols[2].metric("Target", _target)
                if _reference_equals_current and not _prep_comp_lines:
                    st.caption("Reference currently matches live price. Verify before acting.")
                st.caption("Comp evidence")
                if _prep_comp_lines:
                    for _line in _prep_comp_lines:
                        st.caption(_line)
                else:
                    st.caption("No verified sold comps yet")
            elif _prep_comp_without_verified_mv:
                _metric_cols = st.columns(2)
                _metric_cols[0].metric("Current", _current)
                _metric_cols[1].metric("Time left", _time_text or "n/a")
                if _prep_discovery_fallback:
                    st.caption("Discovery only — run comps to validate")
                else:
                    st.caption("No verified MV yet")
                    st.caption("Comp evidence")
                    if _prep_comp_lines:
                        for _line in _prep_comp_lines:
                            st.caption(_line)
                    else:
                        st.caption("No verified sold comps yet")
            else:
                _metric_cols = st.columns(2)
                _metric_cols[0].metric("Current", _current)
                _metric_cols[1].metric("Time left", _time_text or "n/a")
                st.caption("Run comps to calculate market value and target bid.")
            _action_cols = st.columns([1.2, 1.2, 4])
            with _action_cols[0]:
                if st.button("Comp Now", key=f"prep_comp_now_{idx}_{_prep_comp_cache_key}", type="secondary"):
                    print(
                        f"[PREP_COMP_NOW_CLICK] "
                        f"title={_title_text[:160]} "
                        f"item_id={_item_id_for_log[:40]} "
                        f"cache_key={_prep_comp_cache_key}"
                    )
                    try:
                        import ending_soon_engine as _ese_comp
                        _comped_row = _ese_comp.build_single_prep_card_valuation(row, force_refresh=True)
                        st.session_state.setdefault("es_prep_comp_cache", {})[_prep_comp_cache_key] = dict(_comped_row)
                        row.update(dict(_comped_row))
                        st.rerun()
                    except Exception as _comp_exc:
                        row["prep_comp_error"] = str(_comp_exc)[:160]
                        st.session_state.setdefault("es_prep_comp_cache", {})[_prep_comp_cache_key] = dict(row)
                        st.caption(f"Comp failed: {row['prep_comp_error']}")
            with _action_cols[1]:
                if _listing_url:
                    st.link_button("Open listing", _listing_url)
            _alert_unlocked = bool((not _prep_discovery_fallback) and _prep_comp_ready and _target_val is not None and _listing_url and _safe_float(row.get("remaining_seconds") or row.get("seconds_remaining") or row.get("source_time_remaining_seconds")) is not None)
            if bool(row.get("alarm_worthy")) and _alert_unlocked:
                st.caption("SET ALARM - Alert before close using your bid settings")
            elif not _prep_comp_ready and not _prep_discovery_fallback:
                st.caption("Run comps first to unlock alert pricing.")
    print(
        f"[PREP_CARD_ASSERT] "
        f"title={_title_text[:160]} "
        f"rendered_link={1 if _listing_url else 0} "
            f"rendered_comp_block=1 "
            f"reference_label={_reference_label}"
    )
    print(
        f"[PREP_COMP_FILTER_ASSERT] "
        f"title={_title_text[:160]} "
        f"rendered_verified_rows={len(_prep_comp_lines)} "
        f"rendered_placeholder_rows=0 "
        f"final_mode={'verified_sold_titles' if _prep_comp_lines else 'no_verified_sold_comps'}"
    )
    print(
        f"[PREP_RENDER_RECOVERY_ASSERT] "
        f"title={_title_text[:160]} "
        f"ui_verified_rows={len(_prep_comp_lines)} "
        f"ui_reference_label={_reference_label} "
        f"ui_no_verified_message={1 if not _prep_comp_lines else 0} "
        f"ui_render_mode={'verified_sold_titles' if _prep_comp_lines else 'no_verified_sold_comps'}"
    )
    print(
        f"[PREP_THUMB_ASSERT] "
        f"title={_title_text[:160]} "
        f"rendered_thumb={1 if bool(_thumb_url) else 0} "
        f"render_mode=prep_card_thumb_layout"
    )


def _render_es_suppressed_card(_row: Dict[str, Any], _view: Dict[str, Any], _idx: int) -> None:
    _title = str(_view.get("title") or "Unknown listing").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    _time_label = str(_view.get("time_label") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    _current_price = _format_money(_ui_authoritative_current_price(_row))
    _suppression_reasons = _es_get_suppression_reasons(_row, _view)
    _suppression_badges = [{"label": str(_sr), "tone": "muted"} for _sr in _suppression_reasons[:4] if str(_sr or "").strip()]
    _reasons_html = _render_badge_html(_suppression_badges)
    st.markdown(
        f"""
        <div class='sw-es-card sw-es-card-secondary'>
          <div class='sw-es-card-top'>
            <div>
              <div class='sw-es-card-title' style='font-size:0.92rem'>{_idx + 1}. {_title}</div>
              <div class='sw-es-card-meta'>Current price {_current_price}</div>
            </div>
            <div class='sw-es-card-time'>{_time_label}</div>
          </div>
          <div class='sw-es-card-meta' style='margin:0.55rem 0 0.45rem 0;color:#b0b0b0;'>Below current decision threshold. Promote if price support, comps, or edge improves.</div>
          <div class='sw-es-badge-row'>{_reasons_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if _view.get("target_bid_price") is not None:
        st.text_input(
            "Target Bid",
            value=str(_view.get("target_bid_display") or ""),
            key=f"es_target_bid_suppressed_{_idx}_{str(_row.get('row_key') or _row.get('url') or _idx)}",
            disabled=True,
        )
    if bool(_row.get("alarm_worthy")):
        st.caption("SET ALARM - Alert before close using your bid settings")
    if _view.get("url"):
        st.markdown(f"<div class='sw-es-link'><a href='{_view['url']}' target='_blank'>Open listing</a></div>", unsafe_allow_html=True)


def _render_es_result_card(_row: Dict[str, Any], _view: Dict[str, Any], _idx: int, _is_hero: bool = False) -> None:
    _row = _es_strengthen_row_valuation(_row)
    _comp_truth = _ui_comp_truth_split(_row)
    _evidence_contract = _ui_evidence_render_contract(_row)
    _anchor_only_review = bool(_view.get("anchor_only_review") or _row.get("_anchor_only_review") or _evidence_contract.get("anchor_only_review"))
    _comp_count = int(_evidence_contract.get("display_count") or 0)
    _comp_label = str(_evidence_contract.get("label") or "")
    _detail_keys_present = list(_evidence_contract.get("detail_keys_present") or [])
    _detail_rows = list(_evidence_contract.get("detail_rows") or [])
    _evidence_renderable = int(_evidence_contract.get("evidence_renderable") or 0)
    _title_for_log = str(_view.get("title") or _row.get("title") or _row.get("source_title") or "").strip()
    print(
        f"[CARD_COMP_PAYLOAD] title={_title_for_log[:140]} comp_count={_comp_count} "
        f"detail_keys_present={_detail_keys_present} detail_rows={len(_detail_rows)}"
    )
    _rendered_detail = 1 if bool(_detail_rows) and _comp_count > 0 else 0
    _rendered_fallback = 0
    _comp_render_html = _card_comp_render_status_html(
        comp_count=_comp_count,
        detail_rows=_detail_rows,
        label=_comp_label,
        evidence_renderable=_evidence_renderable,
    )
    print(
        f"[CARD_COMP_RENDER] title={_title_for_log[:140]} "
        f"rendered_detail={_rendered_detail} rendered_fallback={_rendered_fallback}"
    )
    print(
        f"[CARD_COMP_POSITION] title={_title_for_log[:140]} inserted_inside_card=1"
    )
    # ── Hero vs secondary sizing ──────────────────────────────────────────────
    _board_tier = str(_row.get("_board_tier") or _view.get("execution_decision") or "SNIPER_CANDIDATE").strip().upper()
    _is_execute_now = _board_tier == "EXECUTE_NOW"
    _urgency_w = int(_row.get("_urgency_weight") or 0)
    if _is_hero:
        _card_class = "sw-es-hero-card" + (" sw-es-hero-execute-card" if _is_execute_now else "")
        _title_style = "font-size:1.22rem;font-weight:900;color:#fafafa;line-height:1.2;margin-bottom:0.25rem"
        _metric_value_style = "font-size:1.08rem;font-weight:900;color:#fafafa"
        _img_size = "96px"
        _img_border = "1.5px solid #666666"
    else:
        _card_class = "sw-es-card sw-es-card-secondary"
        _title_style = "font-size:0.93rem;font-weight:800;color:#fafafa;line-height:1.25;margin-bottom:0.18rem"
        _metric_value_style = "font-size:0.88rem;font-weight:800;color:#e2e8f0"
        _img_size = "58px"
        _img_border = "1px solid #1e2d42"
    _metric_html = "".join(
        f"<div class='sw-es-metric'>"
        f"<div class='sw-es-metric-label'>{_metric.get('label', '')}</div>"
        f"<div class='sw-es-metric-value' style='{_metric_value_style}'>{_metric.get('value', '')}</div>"
        f"</div>"
        for _metric in _view.get("metrics", [])
    )
    _safe_title = _view.get("title", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    _safe_meta = _view.get("meta_line", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    _safe_time = _view.get("time_label", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    _safe_action = _view.get("action_label", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    _safe_note = _view.get("action_note", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    _safe_origin = str(_view.get("origin_reason") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    _safe_hero_reason = str(_view.get("hero_reason") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    _scarcity_parts = [
        str(_part).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        for _part in (_view.get("scarcity_parts") or [])
        if str(_part or "").strip()
    ]
    _scarcity_html = ""
    if _scarcity_parts:
        _scarcity_html = "<div class='sw-es-scarcity-strip'>" + "<span class='sw-es-scarcity-sep'>|</span>".join(
            f"<span>{_part}</span>" for _part in _scarcity_parts
        ) + "</div>"
    _lane_label_raw = str(_view.get("lane_label") or "GENERIC LANE")
    _signal_tier = str(_view.get("signal_tier") or "weak")
    _signal_tier_label = {"elite": "ELITE", "strong": "STRONG", "medium": "MEDIUM", "weak": "WEAK"}.get(_signal_tier, "WEAK")
    _signal_tier_tone = {"elite": "green", "strong": "blue", "medium": "amber", "weak": "muted"}.get(_signal_tier, "muted")
    _exec_r_val = float(_view.get("execution_readiness") or 0.0)
    _exec_r_display = f"{int(round(_exec_r_val))}"
    _exec_r_color = "#22c55e" if _exec_r_val >= 70 else ("#f59e0b" if _exec_r_val >= 45 else "#6b7280")
    _aq_grade = str(_view.get("auction_quality_grade") or "C")
    _card_badges: List[Dict[str, Any]] = [dict(_b) for _b in list(_view.get("badges") or []) if isinstance(_b, dict)]
    _presentation_risk_block = bool(_view.get("presentation_risk_block") or _row.get("_presentation_risk_block"))
    _research_only = bool(_view.get("research_only_price_check") or _row.get("_research_only_price_check"))
    if _research_only:
        print(
            f"[UI_RESEARCH_ONLY_RENDER] title={str((_row or {}).get('title') or _row.get('raw_title') or '')[:160]} "
            f"current={_row.get('current_price')} "
            f"reason={_row.get('_research_only_reason')}"
        )
        _card_badges = [
            {"label": "RESEARCH ONLY", "tone": "amber"},
            {"label": "PRICE CHECK NEEDED", "tone": "muted"},
            {"label": "EVIDENCE: NEEDS COMPS", "tone": "muted"},
        ]
    elif _presentation_risk_block:
        _card_badges = [
            {"label": "MONITOR", "tone": "muted"},
            {"label": "UNCONFIRMED VALUE", "tone": "amber"},
            {"label": "DO NOT CHASE", "tone": "red"},
        ]
    elif _lane_label_raw != "GENERIC LANE":
        _card_badges.insert(1 if _card_badges else 0, {"label": _lane_label_raw, "tone": str(_view.get("lane_tone") or "muted")})
    elif _signal_tier_label not in {"", "WEAK"}:
        _card_badges.append({"label": _signal_tier_label, "tone": _signal_tier_tone})
    if (not _presentation_risk_block) and str(_row.get("evidence_render_source") or "").strip() == "review_payload" and not _anchor_only_review:
        _card_badges.append({"label": "REVIEW ESTIMATE", "tone": "amber"})
        if bool(_row.get("target_bid_ready") or _view.get("target_bid_ready")):
            _card_badges.append({"label": "TARGET BID READY", "tone": "green"})
        if int(_row.get("trusted_exact_comp_count") or 0) <= 0 and int(_row.get("support_comp_count") or 0) <= 0:
            _card_badges.append({"label": "NO COMP SUPPORT", "tone": "muted"})
    if len(_card_badges) < 3 and _aq_grade in {"A", "B"}:
        _card_badges.append({"label": f"Q{_aq_grade}", "tone": "muted"})
    _badge_html = _render_badge_html(_card_badges[:5])
    _decision_reason = str(_view.get("decision_reason") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    _decision_reason_html = (
        f"<div class='sw-es-action-note' style='margin-top:0.2rem;color:#b0b0b0;font-size:0.76rem'>{_decision_reason}</div>"
        if _decision_reason else ""
    )
    _hero_reason_html = (
        f"<div class='sw-es-action-note' style='margin:-0.1rem 0 0.5rem 0;color:#fafafa;font-size:0.78rem;font-weight:600'>{_safe_hero_reason}</div>"
        if _safe_hero_reason else ""
    )
    _image_url = str(_view.get("image_url") or _row.get("source_image_url") or _row.get("thumbnail") or "").strip()
    _image_html = (
        f"<img src='{_image_url}' style='width:{_img_size};height:{_img_size};object-fit:contain;border-radius:8px;margin-right:14px;flex-shrink:0;border:{_img_border}' />"
        if _image_url else ""
    )
    _exec_label_html = _execution_decision_label_html(_view)
    _action_box = _action_box_html(_row, _view)
    # ── Hero banner (slot 0 only) ─────────────────────────────────────────────
    _hero_banner_html = ""
    if _is_hero:
        if _is_execute_now:
            _banner_color = "#ef4444"
            _banner_icon = "⚡"
            _banner_label = "EXECUTE NOW"
            _banner_sub = "HIGHEST PRIORITY PLAY"
            _banner_class = "sw-es-hero-banner sw-es-hero-banner-execute"
            _banner_border = "rgba(220,38,38,0.14)"
        else:
            _banner_color = "#f59e0b"
            _banner_icon = "🎯"
            _banner_label = "TOP SNIPER CANDIDATE"
            _banner_sub = "BEST AVAILABLE PLAY"
            _banner_class = "sw-es-hero-banner"
            _banner_border = "rgba(245,158,11,0.12)"
        _urgency_text = (
            "ENDING SOON" if _urgency_w >= 85
            else "ACT IN 1–3H" if _urgency_w >= 70
            else "ACT IN 3–6H" if _urgency_w >= 50
            else "MONITOR CLOSELY" if _urgency_w >= 25
            else "PREPARE"
        )
        _hero_banner_html = (
            f"<div class='{_banner_class}' style='color:{_banner_color};border-bottom-color:{_banner_border}'>"
            f"<span style='font-size:1rem'>{_banner_icon}</span>"
            f"<span>{_banner_label}</span>"
            f"<span style='color:#888888;font-weight:700;letter-spacing:0.08em'>·</span>"
            f"<span style='color:#b0b0b0;font-weight:700'>{_urgency_text}</span>"
            f"<span style='margin-left:auto;color:#888888;font-size:0.62rem;font-weight:700;letter-spacing:0.1em'>{_banner_sub}</span>"
            f"</div>"
        )
    st.markdown(
        f"""
        <div class='{_card_class}'>
          {_hero_banner_html}
          <div class='sw-es-card-top' style='display:flex;align-items:flex-start;'>
            {_image_html}
            <div style='flex:1;min-width:0;'>
              <div style='{_title_style}'>{_idx + 1}. {_safe_title}</div>
              <div class='sw-es-card-meta'>{_safe_meta}</div>
              {_scarcity_html}
            </div>
            <div class='sw-es-card-time'{"style='font-size:0.92rem;font-weight:900'" if _is_hero else ""}>{_safe_time}</div>
          </div>
          {_exec_label_html}
          {_action_box}
          <div class='sw-es-badge-row'>
            {_badge_html}
          </div>
          <div class='sw-es-card-meta' style='margin:-0.2rem 0 0.65rem 0;color:#b0b0b0;'>{_safe_origin}</div>
          {_hero_reason_html}
          <div class='sw-es-metrics'{"style='gap:0.65rem'" if _is_hero else "style='gap:0.45rem'"}>
            {_metric_html}
          </div>
          {_comp_render_html}
          <div class='sw-es-action-strip'>
            <div>
              <div class='sw-es-action-copy'{"style='font-size:0.88rem'" if _is_hero else ""}>{_safe_action}</div>
              <div class='sw-es-action-note'>{_safe_note}</div>
              {_decision_reason_html}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _card_url = str(_view.get("url") or "").strip()
    if _card_url:
        st.markdown(f"<div class='sw-es-link'><a href='{_card_url}' target='_blank'>Open listing</a></div>", unsafe_allow_html=True)
    if bool(_row.get("alarm_worthy")):
        st.caption("SET ALARM - Alert before close using your bid settings")
    if _view.get("target_bid_price") is not None:
        st.text_input(
            "Target Bid",
            value=str(_view.get("target_bid_display") or ""),
            key=f"es_target_bid_copy_{_idx}_{str(_row.get('row_key') or _row.get('url') or _idx)}",
            disabled=True,
            help=f"Copy-ready manual target bid ({int(round(float(_view.get('target_bid_pct_used') or 0.75) * 100))}% of market value).",
        )
    st.caption("Confidence reason", help=_es_confidence_tooltip(_row))
    with st.expander("Valuation Debug", expanded=False):
        st.text(
            "\n".join(
                [
                    "── Decision Quality ──────────────────────",
                    f"decision_quality_score: {_view.get('decision_quality_score', '?')}",
                    f"execution_readiness:    {_view.get('execution_readiness', '?')}",
                    f"valuation_trust_score:  {_view.get('valuation_trust_score', '?')}",
                    f"signal_tier:            {_view.get('signal_tier', '?')}",
                    f"decision_reason:        {_view.get('decision_reason', '?')}",
                    f"readiness_reason:       {_view.get('readiness_reason', '?')}",
                    f"trust_reason:           {_view.get('trust_reason', '?')}",
                    f"quality_reasons:        {_view.get('quality_reasons', [])}",
                    "── Scarcity / Lane ───────────────────────",
                    f"scarcity_class: {str(_row.get('scarcity_class') or None)}",
                    f"subset_name: {str(_row.get('subset_name') or None)}",
                    f"parallel_name: {str(_row.get('parallel_name') or _row.get('parallel_bucket') or None)}",
                    f"serial_denominator: {str(_row.get('serial_denominator') or None)}",
                    f"serial_bucket: {str(_row.get('serial_bucket') or None)}",
                    f"one_of_one: {bool(_row.get('one_of_one'))}",
                    f"scarcity_confidence: {str(_row.get('scarcity_confidence') or None)}",
                    f"lane_type: {str(_row.get('lane_type') or None)}",
                    f"lane_aligned: {bool(_row.get('lane_aligned'))}",
                    f"route_stage: {str(_row.get('route_stage') or None)}",
                    f"route_reason: {str(_row.get('route_reason') or None)}",
                    f"recovery_stage: {str(_row.get('recovery_stage') or 'primary')}",
                    f"remaining_seconds: {str(_view.get('remaining_seconds') if _view.get('remaining_seconds') is not None else None)}",
                    f"formatted_time_left: {str(_view.get('formatted_time_left') or None)}",
                    f"promoted_live_candidate: {bool(_view.get('promoted_live_candidate'))}",
                    f"premium_review_status: {str(_view.get('premium_review_status') or None)}",
                    f"premium_review_reason: {str(_view.get('premium_review_reason') or None)}",
                    f"review_failed: {bool(_view.get('review_failed'))}",
                    f"review_failure_reason: {str(_view.get('review_failure_reason') or None)}",
                    f"mv_attempted: {bool(_view.get('mv_attempted'))}",
                    f"mv_resolved: {bool(_view.get('mv_resolved'))}",
                    f"comp_attempted: {bool(_view.get('comp_attempted'))}",
                    f"target_bid_attempted: {bool(_view.get('target_bid_attempted'))}",
                    "── Valuation ─────────────────────────────",
                    f"comp_source_label: {str(_row.get('comp_source_label') or _row.get('mv_source') or None)}",
                    f"valuation_confidence: {str(_row.get('valuation_confidence') or None)}",
                    f"comp_count: {int((_safe_float(_row.get('mv_comp_count')) or _safe_float(_row.get('comp_count')) or 0))}",
                    f"live_signal_tier: {str(_view.get('live_signal_tier') or None)}",
                    f"live_signal_score: {str(_view.get('live_signal_score') or None)}",
                    f"live_signal_reason: {str(_view.get('live_signal_reason') or None)}",
                    f"primary_query: {str(_row.get('primary_query') or _row.get('debug_search_query') or None)}",
                    "── Source Truth ──────────────────────────",
                    f"source_item_id: {str(_row.get('source_item_id') or _row.get('item_id') or None)}",
                    f"source_listing_type: {str(_row.get('source_listing_type') or None)}",
                    f"source_title: {str(_row.get('source_title') or None)}",
                    f"source_display_price: {str(_row.get('source_display_price') or None)}",
                    f"source_current_bid: {str(_row.get('source_current_bid') or None)}",
                    f"source_buy_now_price: {str(_row.get('source_buy_now_price') or None)}",
                    f"source_price_kind: {str(_row.get('source_price_kind') or None)}",
                    f"source_end_time: {str(_row.get('source_end_time') or _row.get('end_iso') or None)}",
                    f"source_time_remaining_seconds: {str(_row.get('source_time_remaining_seconds') or None)}",
                    f"source_image_url: {str(_row.get('source_image_url') or _row.get('thumbnail') or None)}",
                    f"source_view_url: {str(_row.get('source_view_url') or _row.get('url') or None)}",
                ]
            )
        )


# TRIAL-GATE-2026-05-12: enforce the magic-link / 10-min trial / paywall
# flow before any dashboard rendering. Returns normally if user is in
# trial_active or paid state; calls st.stop() with a gate page (login,
# check-inbox, or paywall) otherwise. Failure-open if the gate module
# blows up — we'd rather show the dashboard than a blank screen.
try:
    import trial_gate as _trial_gate
    _trial_gate.enforce_gate(st)
except Exception as _gate_err:
    print(f"[TRIAL_GATE_ERROR] {type(_gate_err).__name__}: {str(_gate_err)[:200]}")
    import traceback as _tb
    print(_tb.format_exc())

_active_page_id = _resolve_active_page(PAGE_REGISTRY)
_active_page_meta = PAGE_REGISTRY[_active_page_id]
_render_shell_top_nav(PAGE_REGISTRY)
_render_page_shell(_active_page_meta)

# =============================================================================
# TAB 0 — Ending Soon
# =============================================================================
if _active_page_id == "ending_soon":
    try:
        import ending_soon_engine as _ese
        import valuation_engine as _ve

        # ── Module 3 hook — Morning Briefing panel from daily_pool.json ──
        # Renders ABOVE the existing live-scan UI so users see the 24h
        # pipeline first. The existing scan flow remains as a fallback
        # (the "Run Scan" button still triggers a wide live scan).
        # If pool_view import fails or the pool is empty, the panel
        # silently no-ops and the page continues to work as before.
        try:
            import pool_view as _pool_view
            _pool_view.render_morning_briefing(st)
        except Exception as _briefing_err:
            print(f"[UI_BRIEFING_ERROR] {type(_briefing_err).__name__}: {str(_briefing_err)[:160]}")

        def _ui_board_debug(stage, rows):
            try:
                _rows = list(rows or [])
                _titles = [str((r or {}).get("title") or (r or {}).get("raw_title") or "")[:100] for r in _rows[:5]]
                print(f"[UI_BOARD] stage={stage} count={len(_rows)} titles={_titles}")
            except Exception as e:
                print(f"[UI_BOARD_ERROR] stage={stage} error={e}")
        if not bool(st.session_state.get("_es_import_path_logged_once")):
            print(f"[ES_IMPORT_PATH] module=ending_soon_engine file={str(getattr(_ese, '__file__', '') or 'unknown')}")
            st.session_state["_es_import_path_logged_once"] = True

        if not bool(st.session_state.get("_valuation_module_logged_once")):
            print(f"[VALUATION_MODULE_PATH] path={str(getattr(_ve, '__file__', '') or 'unknown')}")
            print(
                f"[VALUATION_CONTRACT_VERSION] version={str(getattr(_ve, 'TRUE_MV_CONTRACT_VERSION', _UI_TRUE_MV_CONTRACT_VERSION) or _UI_TRUE_MV_CONTRACT_VERSION)}"
            )
            st.session_state["_valuation_module_logged_once"] = True

        # Peak-times advisory banner removed May 2026 — referenced the
        # legacy in-page scanner ("the scanner will still run"). The new
        # pipeline runs continuously in the background under supervisor.py,
        # so the banner's framing no longer matches reality.

        # ── Scan state bar ──
        _ss = _ese.get_scan_state()
        _engine_active = bool(_ss.get("scan_active"))
        _active   = bool(st.session_state.get("es_is_scanning", False) or _engine_active)
        _phase    = str(_ss.get("scan_phase") or "idle").upper()
        _failed   = bool(_ss.get("scan_failed"))
        _done     = int(_ss.get("progress_done") or 0)
        _total    = int(_ss.get("progress_total") or 0)
        _player   = str(_ss.get("progress_player") or "")
        _last_act = str(_ss.get("last_completed_action") or "—")

        # ── Stale lock watchdog ────────────────────────────────────────────────────────
        # _SCAN_ACTIVE stays True if the engine threw mid-scan.
        # After 90 s, clear the lock so future clicks can fire.
        _scan_started_at = float(_ss.get("scan_started_at") or 0.0)
        _scan_last_heartbeat_ts = float(_ss.get("scan_last_heartbeat_ts") or _scan_started_at or 0.0)
        _scan_progress_sig = (
            str(_ss.get("scan_phase") or "idle"),
            int(_ss.get("scan_progress_current") or 0),
            int(_ss.get("scan_progress_total") or 0),
            str(_ss.get("scan_progress_label") or ""),
            int(_ss.get("progress_done") or 0),
            int(_ss.get("progress_total") or 0),
            str(_ss.get("progress_player") or ""),
        )
        _prev_watchdog_sig = st.session_state.get("es_watchdog_progress_sig")
        _prev_watchdog_hb = float(st.session_state.get("es_watchdog_last_heartbeat_ts") or 0.0)
        _progress_changed = bool(_scan_progress_sig != _prev_watchdog_sig)
        _heartbeat_moved = bool(_scan_last_heartbeat_ts > (_prev_watchdog_hb + 0.001))
        _watchdog_age_s = (time.time() - _scan_last_heartbeat_ts) if _scan_last_heartbeat_ts > 0 else 0.0
        print(f"[SCAN_WATCHDOG] age_s={_watchdog_age_s:.1f} progress_changed={1 if (_progress_changed or _heartbeat_moved) else 0}")
        if _engine_active and (_progress_changed or _heartbeat_moved or _prev_watchdog_sig is None):
            st.session_state["es_watchdog_progress_sig"] = _scan_progress_sig
            st.session_state["es_watchdog_last_heartbeat_ts"] = _scan_last_heartbeat_ts
        elif not _engine_active:
            st.session_state["es_watchdog_progress_sig"] = None
            st.session_state["es_watchdog_last_heartbeat_ts"] = 0.0
        if (
            _engine_active
            and _scan_started_at > 0
            and _scan_last_heartbeat_ts > 0
            and _watchdog_age_s > 90.0
            and not _progress_changed
            and not _heartbeat_moved
        ):
            _ese.set_scan_failure("Stale scan lock cleared by UI watchdog (heartbeat stalled >90s)")
            _ss = _ese.get_scan_state()
            _engine_active = bool(_ss.get("scan_active"))
            st.session_state["es_is_scanning"] = False
            st.session_state["es_watchdog_progress_sig"] = None
            st.session_state["es_watchdog_last_heartbeat_ts"] = 0.0
            _active   = bool(st.session_state.get("es_is_scanning", False) or _engine_active)
            _failed   = bool(_ss.get("scan_failed"))
            _last_act = str(_ss.get("last_completed_action") or "â€”")
            _phase    = str(_ss.get("scan_phase") or "idle").upper()
            print("[UI][ES_HANDOFF] stale_lock_cleared=1 age_s={:.0f}".format(_watchdog_age_s))
        if False and _engine_active:
            _ese.set_scan_failure("Stale scan lock cleared by UI watchdog (>90s)")
            _ss       = _ese.get_scan_state()
            _engine_active = bool(_ss.get("scan_active"))
            st.session_state["es_is_scanning"] = False
            _active   = bool(st.session_state.get("es_is_scanning", False) or _engine_active)
            _failed   = bool(_ss.get("scan_failed"))
            _last_act = str(_ss.get("last_completed_action") or "—")
            _phase    = str(_ss.get("scan_phase") or "idle").upper()
            print("[UI][ES_HANDOFF] stale_lock_cleared=1 age_s={:.0f}".format(
                time.time() - _scan_started_at
            ))

        # ── Safe commit: run pending scan BEFORE KPI render ────────────────────────────
        # Running here means _deal_ct is authoritative in the same render pass.
        # Widget values are read from session state (persisted across reruns).
        if st.session_state.pop("es_scan_requested", False) and not _engine_active:
            st.session_state["es_is_scanning"] = True
            _es_sp_key   = str(st.session_state.get("es_sport_filter") or "All")
            _es_sport_arg = (
                None if _es_sp_key == "All"
                else _normalize_sport_label(_es_sp_key)
            )
            _es_tw_val   = float(st.session_state.get("es_time_window") or 6.0)
            _es_edge_val = float(st.session_state.get("es_min_edge") or 0.0)
            _returned: List[Dict[str, Any]] = list(st.session_state.get("es_rows") or [])
            _returned_meta: Dict[str, Any] = dict(st.session_state.get("es_meta") or {})
            _diversity_memory = {
                "recent_players": list(st.session_state.get("es_recent_players") or []),
                "recent_products": list(st.session_state.get("es_recent_products") or []),
                "recent_item_ids": list(st.session_state.get("es_recent_item_ids") or []),
            }
            if getattr(_ese, "RUNTIME_BUILD_STAMP", "") != "ES_BUILD_2026_04_17_A":
                raise RuntimeError("Stale ending_soon_engine build loaded")
            print(
                f"[UI_SCAN_CALL_ENTER] window={_es_tw_val} "
                f"sport={_es_sport_arg!r} "
                f"min_edge={_es_edge_val}"
            )
            try:
                _returned, _returned_meta = _ese.fetch_ending_soon_deals(
                    sport_filter=_es_sport_arg,
                    time_window_hours=_es_tw_val,
                    min_edge_pct=_es_edge_val,
                    force_refresh=True,
                    diversity_memory=_diversity_memory,
                )
            except Exception as _scan_exc:
                _returned_meta = {"error": str(_scan_exc)}
                _partial_snapshot: Dict[str, Any] = {}
                try:
                    _partial_snapshot = _ese.get_active_scan_partial_snapshot(
                        sport_filter=_es_sport_arg,
                        time_window_hours=_es_tw_val,
                    )
                except Exception:
                    _partial_snapshot = {}
                _partial_rows = list(_partial_snapshot.get("latest_result_rows") or [])
                _partial_meta = dict(_partial_snapshot.get("meta") or {})
                if _partial_rows:
                    _returned = _partial_rows
                    _returned_meta = dict(_partial_meta or {})
                    _returned_meta["error"] = str(_scan_exc)
                    _returned_meta["scan_failed"] = True
                    _returned_meta["partial_rows"] = len(_partial_rows)
                    print(f"[SCAN_FAILSAFE] partial_rows={len(_partial_rows)} error={str(_scan_exc)[:200]}")
                else:
                    print(f"[SCAN_FAILSAFE] partial_rows=0 error={str(_scan_exc)[:200]}")
                try:
                    _ese.set_scan_failure(str(_scan_exc))  # always reset _SCAN_ACTIVE
                except Exception:
                    pass
            except BaseException as _scan_be:
                print(
                    f"[UI_SCAN_CALL_BASE_EXCEPTION] type={type(_scan_be).__name__} "
                    f"msg={str(_scan_be)[:200]}"
                )
                raise
            _returned = list(_returned or [])
            displayed_rows = list((_returned_meta or {}).get("displayed_rows") or (_returned_meta or {}).get("final_rows") or [])
            live_board_rows = list((_returned_meta or {}).get("live_board_rows") or (_returned_meta or {}).get("main_visible_rows") or [])
            research_queue_rows = list((_returned_meta or {}).get("research_queue_rows") or [])
            prep_board_rows = list((_returned_meta or {}).get("prep_board_rows") or [])
            print(
                f"[UI_SCAN_CALL_EXIT] rows={len(_returned)} "
                f"live_rows={len(live_board_rows)} "
                f"prep_rows={len(prep_board_rows)} "
                f"displayed_rows={len(displayed_rows)} "
                f"keys={list((_returned_meta or {}).keys())[:24]}"
            )
            deal_rows = list((_returned_meta or {}).get("deal_rows") or _returned)
            st.session_state["es_rows"]         = _returned
            st.session_state["es_deals"]        = list(_returned)
            st.session_state["es_meta"]         = dict(_returned_meta or {})
            st.session_state["es_research_queue_rows"] = list(research_queue_rows)
            st.session_state["es_prep_board_rows"] = list(prep_board_rows)
            st.session_state["ending_soon_rows"] = list(displayed_rows)
            st.session_state["live_board_rows"] = list(live_board_rows or displayed_rows)
            _ui_board_debug("returned_displayed_rows", displayed_rows)
            _ui_board_debug("returned_live_board_rows", live_board_rows)
            _ui_board_debug("returned_prep_board_rows", prep_board_rows)
            _ui_board_debug("returned_deal_rows", deal_rows)
            _ui_board_debug("session_ending_soon_rows", st.session_state.get("ending_soon_rows") or [])
            _ui_board_debug("session_live_board_rows", st.session_state.get("live_board_rows") or [])
            _board_visible_count = sum(
                1 for _r in _returned
                if bool(_r.get("board_visible"))
                and str(_r.get("execution_admission_bucket") or "").strip().lower() in {"watchlist", "monitor", "sniper"}
            )
            print(
                f"[SESSION_BOARD_WRITE] rows={len(_returned)} "
                f"board_visible_stamped={_board_visible_count} "
                f"meta_keys={list((_returned_meta or {}).keys())[:8]}"
            )
            st.session_state["es_scan_error"]   = str((_returned_meta or {}).get("error") or "") or None
            st.session_state["es_last_scan_ts"] = time.time()
            st.session_state["es_is_scanning"]  = False
            st.session_state["es_watchdog_progress_sig"] = None
            st.session_state["es_watchdog_last_heartbeat_ts"] = 0.0
            if not st.session_state["es_scan_error"]:
                _recent_players = list(st.session_state.get("es_recent_players") or [])
                _recent_products = list(st.session_state.get("es_recent_products") or [])
                _recent_item_ids = list(st.session_state.get("es_recent_item_ids") or [])
                for _row in list(_returned or []):
                    _p = str((_row or {}).get("player_name") or "").strip().lower()
                    _prod = str((_row or {}).get("product_family") or (_row or {}).get("target_product_family") or "").strip().lower()
                    _iid = str((_row or {}).get("source_item_id") or (_row or {}).get("item_id") or "").strip().lower()
                    _pair = f"{_p}|{_prod}" if _p and _prod else ""
                    if _p:
                        _recent_players.append(_p)
                    if _prod:
                        _recent_products.append(_prod)
                    if _iid:
                        _recent_item_ids.append(_iid)
                    elif _pair:
                        _recent_item_ids.append(_pair)
                st.session_state["es_recent_players"] = _recent_players[-24:]
                st.session_state["es_recent_products"] = _recent_products[-24:]
                st.session_state["es_recent_item_ids"] = _recent_item_ids[-36:]
            # Refresh scan state so KPI cards reflect the completed scan
            _ss       = _ese.get_scan_state()
            _engine_active = bool(_ss.get("scan_active"))
            _active   = bool(st.session_state.get("es_is_scanning", False) or _engine_active)
            _failed   = bool(_ss.get("scan_failed"))
            _last_act = str(_ss.get("last_completed_action") or "—")
            _phase    = str(_ss.get("scan_phase") or "idle").upper()
            print("[UI][SCAN_COMMIT] returned={} stored={} scanning={} error={}".format(
                len(_returned), len(st.session_state.get("es_rows") or []),
                int(bool(st.session_state.get("es_is_scanning", False))),
                int(bool(st.session_state.get("es_scan_error")))
            ))

        # ── Authoritative state ─────────────────────────────────────────────────────────────────
        # All three: DEALS LOADED metric, board render, empty-state check
        # read from this one source. Never diverge.
        _es_rows: list = st.session_state.get("es_rows") or []
        _deal_ct = len(_es_rows)
        _scan_error = st.session_state.get("es_scan_error")
        _active = bool(st.session_state.get("es_is_scanning", False) or _engine_active)
        print("[UI][METRIC] deals_loaded={}".format(_deal_ct))

        _snap = _ese.get_latest_completed_scan_snapshot()
        _budget = _ese.get_budget_snapshot()
        _spent      = _budget.get("session_spent_usd", 0.0) if _budget else 0.0
        _budget_cap = _budget.get("session_cap_usd", 0.0)   if _budget else 0.0

        _status_label = _phase if _active else ("FAILED" if _failed else "IDLE")
        _status_accent = "kpi-green" if _active else ("kpi-red" if _failed else "kpi-muted")

        # Legacy "Live Status" KPI row (Scan Status / Deals Loaded / Last Action
        # / Session Spend) intentionally removed May 2026 — the morning briefing
        # at the top of the page already surfaces pool freshness and deal count
        # via the AUCTION POOL · LIVE card. The old in-memory scanner the row
        # tracked is no longer the source of truth.

        # ── Progress bar when scanning ──
        if _active and _total > 0:
            try:
                _progress_ratio = float(_done) / float(_total)
            except Exception:
                _progress_ratio = 0.0
            if _progress_ratio != _progress_ratio or _progress_ratio in (float("inf"), float("-inf")):
                _progress_ratio = 0.0
            _progress_ratio = max(0.0, min(1.0, _progress_ratio))
            st.progress(_progress_ratio, text=f"Scanning {_player} … {_done}/{_total}")
        elif _active:
            st.progress(0, text=f"Scan running — {_phase.lower()} …")

        if _failed:
            st.error(f"Last scan error: {_ss.get('scan_error_message','Unknown error')}")

        # Legacy bottom-of-page "Pool Controls" block (Refresh Feed button +
        # last-refresh age display) removed May 2026 — replaced with the
        # lightweight `↻ Refresh Feed` button at the top of this tab that
        # simply triggers st.rerun(). The actual pool fetcher runs in the
        # background via daily_pool.py --loop under supervisor.py, so the UI
        # doesn't need to launch a subprocess on every click.

        # ── Results table ── (scan already committed above)
        _deals: List[Dict[str, Any]] = _es_rows
        _meta: Dict[str, Any]        = st.session_state.get("es_meta") or {}
        research_queue_rows: List[Dict[str, Any]] = list(
            (_meta.get("research_queue_rows") or st.session_state.get("es_research_queue_rows") or [])
        )
        prep_board_rows: List[Dict[str, Any]] = list(
            (_meta.get("prep_board_rows") or st.session_state.get("es_prep_board_rows") or [])
        )
        print(f"[UI_RESEARCH_QUEUE] count={len(research_queue_rows)}")
        if not _deals:
            _meta_live_rows = [
                _r for _r in list((_meta.get("main_visible_rows") or [])) + list((_meta.get("other_visible_rows") or []))
                if _ui_is_live_watchlist_row(_r)
            ]
            if _meta_live_rows:
                _deals = list(_meta_live_rows)
                print(f"[UI][LIVE_WATCHLIST_REBIND] added={len(_meta_live_rows)} source=meta_empty_rows")
        displayed_rows = list((_meta.get("displayed_rows") or _meta.get("final_rows") or []))
        live_board_rows = list((_meta.get("live_board_rows") or _meta.get("main_visible_rows") or []))
        _ui_board_debug("returned_displayed_rows", displayed_rows)
        _ui_board_debug("returned_live_board_rows", live_board_rows)
        _ui_board_debug("returned_prep_board_rows", prep_board_rows)
        _ui_board_debug("session_ending_soon_rows", st.session_state.get("ending_soon_rows") or [])
        _ui_board_debug("session_live_board_rows", st.session_state.get("live_board_rows") or [])
        render_source = list(live_board_rows or displayed_rows or [])
        _ui_board_debug("render_source_before_fallback", render_source)
        try:
            _render_rows = list(render_source or [])
            if not _render_rows:
                for _candidate_name, _candidate_rows in [
                    ("displayed_rows", displayed_rows),
                    ("live_board_rows", live_board_rows),
                    ("session_ending_soon_rows", st.session_state.get("ending_soon_rows") or []),
                    ("session_live_board_rows", st.session_state.get("live_board_rows") or []),
                ]:
                    _candidate_rows = list(_candidate_rows or [])
                    if _candidate_rows:
                        _render_rows = _candidate_rows
                        print(f"[UI_BOARD_FALLBACK] source={_candidate_name} count={len(_render_rows)}")
                        break
            _ui_board_debug("render_source_after_fallback", _render_rows)
        except Exception as e:
            print(f"[UI_BOARD_FALLBACK_ERROR] error={e}")
            _render_rows = list(render_source or [])
        _ui_board_debug("pre_ui_filters", _render_rows)
        _deals = list(_render_rows)
        _board_read_visible = sum(
            1 for _r in _deals
            if bool(_r.get("board_visible"))
            and str(_r.get("execution_admission_bucket") or "").strip().lower() in {"watchlist", "monitor", "sniper"}
        )
        print(
            f"[SESSION_BOARD_READ] rows={len(_deals)} "
            f"board_visible_stamped={_board_read_visible}"
        )

        if _scan_error:
            st.error(f"Scan error: {_scan_error}")

        # ── Universe + cohort summary (compact, always visible after scan) ────────
        _u_players = int(_meta.get("universe_players") or 0)
        _u_targets = int(_meta.get("universe_targets") or 0)
        _c_sport = str(_meta.get("cohort_sport") or "NFL")
        _c_total = int(_meta.get("cohort_total") or 0)
        _c_core = int(_meta.get("cohort_core") or 0)
        _c_rot = int(_meta.get("cohort_rotating") or 0)
        _c_cross = bool(_meta.get("cohort_cross_sport"))
        _scan_sports = list(_meta.get("scan_sports") or [])
        _scan_players = int(_meta.get("scan_unique_players") or 0)
        _scan_products = int(_meta.get("scan_unique_products") or 0)
        _scan_lanes = int(_meta.get("scan_lane_count") or 0)
        _cohort_fresh_injected = int(_meta.get("cohort_fresh_injected") or 0)
        if _u_players > 0 or _c_total > 0:
            if _c_total > 0:
                if _c_cross and _scan_sports:
                    _sports_label = " + ".join(_scan_sports)
                    _cohort_label = (
                        f"sports in scan: {_sports_label} · "
                        f"players: {_scan_players} · lanes: {_scan_lanes} "
                        f"(core {_c_core} + rotating {_c_rot})"
                    )
                else:
                    _cohort_label = (
                        f"scan cohort: {_c_sport} core({_c_core}) + rotating({_c_rot}) = {_c_total} targets"
                        + (f" · players: {_scan_players}" if _scan_players else "")
                    )
            else:
                _cohort_label = f"tracked players: {_u_players} · tracked targets: {_u_targets}"
            st.markdown(
                f"<div style='font-size:0.72rem;color:#888888;margin:0.3rem 0 0.6rem 0;'>"
                f"{_cohort_label}"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.caption(
                f"Diversity: {_scan_players} players • {_scan_products} products"
                + (f" • fresh rotation +{_cohort_fresh_injected}" if _cohort_fresh_injected > 0 else "")
            )

        _meta_live_watchlist_count = sum(
            1 for _r in list((_meta.get("main_visible_rows") or [])) + list((_meta.get("other_visible_rows") or []))
            if _ui_is_live_watchlist_row(_r)
        )
        _show_empty_state = (not _active) and len(_deals) == 0 and _meta_live_watchlist_count == 0 and not research_queue_rows and not prep_board_rows
        print("[UI][EMPTY_GATE] scanning={} rows={} show_empty={}".format(
            int(bool(_active)), len(_deals), int(bool(_show_empty_state))
        ))

        if _deals or research_queue_rows or prep_board_rows:
            st.markdown("<div class='sw-section-hdr'>Live Board</div>", unsafe_allow_html=True)

            # ── Filter strip ──
            _fc1, _fc2, _fc3 = st.columns([2, 1, 1])
            with _fc1:
                _kw_filter = st.text_input("Filter title", key="es_kw_filter",
                                           placeholder="e.g. mahomes psa",
                                           label_visibility="collapsed")
            with _fc2:
                _dc_opts = ["All classes"] + sorted({
                    str(r.get("deal_class") or "UNKNOWN") for r in _deals
                })
                _dc_sel = st.selectbox("Class", _dc_opts, key="es_dc_filter",
                                       label_visibility="collapsed")
            with _fc3:
                _quality_opts = ["All quality"] + sorted({
                    str(r.get("row_quality_state") or "—") for r in _deals
                })
                _q_sel = st.selectbox("Quality", _quality_opts, key="es_q_filter",
                                      label_visibility="collapsed")

            _main_visible_rows = list((_meta.get("main_visible_rows") or [])) if isinstance(_meta, dict) else []
            _recovery_rows_hidden = list((_meta.get("recovery_rows_hidden") or [])) if isinstance(_meta, dict) else []
            if not _main_visible_rows:
                _main_visible_rows = [r for r in _deals if _es_is_resolved_board_row(r)]
            _engine_live_watchlist_rows = []
            _engine_live_seen = {
                _ui_live_watchlist_row_id(_r)
                for _r in _main_visible_rows
                if isinstance(_r, dict)
            }
            for _r in list(_deals or []) + list((_meta.get("other_visible_rows") or []) if isinstance(_meta, dict) else []):
                if not _ui_is_live_watchlist_row(_r):
                    continue
                _rid = _ui_live_watchlist_row_id(_r)
                if _rid in _engine_live_seen:
                    continue
                _engine_live_seen.add(_rid)
                _engine_live_watchlist_rows.append(_r)
            if _engine_live_watchlist_rows:
                _main_visible_rows = list(_main_visible_rows) + list(_engine_live_watchlist_rows)
                print(
                    f"[UI][LIVE_WATCHLIST_REBIND] added={len(_engine_live_watchlist_rows)} "
                    f"main_visible={len(_main_visible_rows)}"
                )
            _visible = list(_main_visible_rows)
            if _sport_sel != "All":
                _want_sport = _normalize_sport_label(_sport_sel)
                _visible = [
                    r for r in _visible
                    if _normalize_sport_label(r.get("sport") or r.get("sport_name") or r.get("target_sport") or "") == _want_sport
                ]
            if _kw_filter.strip():
                _lf = _kw_filter.strip().lower()
                _visible = [r for r in _visible if _lf in str(r.get("title") or "").lower()]
            if _dc_sel != "All classes":
                _visible = [r for r in _visible if str(r.get("deal_class") or "UNKNOWN") == _dc_sel]
            if _q_sel != "All quality":
                _visible = [r for r in _visible if str(r.get("row_quality_state") or "—") == _q_sel]

            _sorted_visible = _es_sort_rows_for_decision_surface(_visible)
            # [HIDE_PASS_OVERPRICED] — when actionable inventory exists, the
            # board should not waste user attention on PASS_OVERPRICED rows.
            # Sniping platform = "what to bid", not "what to ignore". Keep
            # SNIPE_NOW / RESEARCH_SNIPE / WATCH rows always; cap PASS rows
            # to 0 when actionable rows ≥ 3, else fill to floor with up to
            # 3 PASS rows so the board isn't empty.
            def _es_decision_for_row(_r: Dict[str, Any]) -> str:
                return str(
                    (_r or {}).get("execution_decision")
                    or (_r or {}).get("final_execution_decision")
                    or "PASS"
                ).strip().upper()
            _PASS_DECISIONS = {"PASS_OVERPRICED", "RESEARCH_PASS", "PASS", "SKIP"}
            # UNDER_MV is a real deal — below market value, worth bidding even
            # though it's above the deep-discount snipe target. Treated as
            # actionable so it counts toward the 3-row threshold that hides PASS.
            _ACTIONABLE_DECISIONS = {"SNIPE_NOW", "EXECUTE_NOW", "RESEARCH_SNIPE", "PREPARE", "SNIPE", "UNDER_MV", "WATCH"}
            _actionable_rows = [_r for _r in _sorted_visible if _es_decision_for_row(_r) in _ACTIONABLE_DECISIONS]
            _pass_rows = [_r for _r in _sorted_visible if _es_decision_for_row(_r) in _PASS_DECISIONS]
            _other_rows = [_r for _r in _sorted_visible if _es_decision_for_row(_r) not in (_PASS_DECISIONS | _ACTIONABLE_DECISIONS)]
            if len(_actionable_rows) >= 3:
                _filtered_visible = _actionable_rows + _other_rows
                _pass_kept_for_floor = 0
                _pass_hidden = len(_pass_rows)
            else:
                _floor_target = 5
                _need = max(0, _floor_target - len(_actionable_rows) - len(_other_rows))
                _pass_kept = _pass_rows[:min(_need, 3)]
                _filtered_visible = _actionable_rows + _other_rows + _pass_kept
                _pass_kept_for_floor = len(_pass_kept)
                _pass_hidden = len(_pass_rows) - _pass_kept_for_floor
            try:
                print(
                    f"[HIDE_PASS_OVERPRICED] actionable={len(_actionable_rows)} "
                    f"pass_total={len(_pass_rows)} pass_kept={_pass_kept_for_floor} "
                    f"pass_hidden={_pass_hidden} other={len(_other_rows)} "
                    f"final={len(_filtered_visible)}"
                )
            except Exception:
                pass
            _sorted_visible = _filtered_visible
            _reset_es_badge_guard()
            _view_models = [(_row, _es_get_decision_view_model(_row)) for _row in _sorted_visible]
            _prep_visible = list(prep_board_rows or [])
            if _sport_sel != "All":
                _want_sport = _normalize_sport_label(_sport_sel)
                _prep_visible = [
                    r for r in _prep_visible
                    if _normalize_sport_label(r.get("sport") or r.get("sport_name") or r.get("target_sport") or "") == _want_sport
                ]
            if _kw_filter.strip():
                _lf = _kw_filter.strip().lower()
                _prep_visible = [r for r in _prep_visible if _lf in str(r.get("title") or r.get("source_title") or "").lower()]
            _prep_seen_ids = set()
            _prep_view_models = []
            for _prep_row in _es_sort_rows_for_decision_surface(_prep_visible):
                if not isinstance(_prep_row, dict):
                    continue
                _prep_rid = _ui_live_watchlist_row_id(_prep_row)
                if _prep_rid in _prep_seen_ids:
                    continue
                _prep_seen_ids.add(_prep_rid)
                _prep_row = _apply_cached_prep_comp_payload(_prep_row)
                _prep_row["_prep_board"] = True
                _prep_row["surface_intent"] = "monitor"
                _prep_view_models.append((_prep_row, _es_get_decision_view_model(_prep_row)))

            # ── MV display contract diagnostics ──────────────────────────────────────
            _mv_display_blocked: Dict[str, int] = {}
            _mv_display_count = 0
            _mv_review_display_count = 0   # REVIEW estimate rows (not "blocked")
            _mv_display_samples: list = []
            for _drow, _dview in _view_models:
                _dval_true   = _dview.get("market_value_display")     # only set for TRUE-truth rows
                _dval_review = _dview.get("review_estimate_display")  # set for REVIEW rows
                # A row is "displayable" if it has either a TRUE MV or a REVIEW estimate
                if _dval_true and float(_dval_true or 0) > 0:
                    _mv_display_count += 1
                    if len(_mv_display_samples) < 2:
                        _mv_display_samples.append(
                            "item={} display={} source={}".format(
                                str(_drow.get("source_item_id") or _drow.get("item_id") or "?")[:16],
                                "${:.2f}".format(float(_dval_true)),
                                str(_dview.get("market_value_source") or "unknown")[:28],
                            )
                        )
                elif _dval_review and float(_dval_review or 0) > 0:
                    # REVIEW estimate — the value IS displayable as "Review Estimate"
                    _mv_review_display_count += 1
                    if len(_mv_display_samples) < 2:
                        _mv_display_samples.append(
                            "item={} review_display={} source={}".format(
                                str(_drow.get("source_item_id") or _drow.get("item_id") or "?")[:16],
                                "${:.2f}".format(float(_dval_review)),
                                str(_dview.get("market_value_source") or "unknown")[:28],
                            )
                        )
                else:
                    # Truly blocked — derive a concrete reason, not "unknown"
                    _dbr = str(_dview.get("mv_blocked_reason_display") or "")
                    if not _dbr or _dbr == "unknown":
                        _src_diag  = str(_drow.get("market_value_source") or _drow.get("mv_source") or "").lower()
                        _truth_diag = str(_drow.get("valuation_truth_tier") or "").upper()
                        _comp_diag  = int(_drow.get("comp_count") or _drow.get("mv_comp_count") or 0)
                        _truth_diag_rv = _safe_float(_drow.get("review_estimate_value")) or 0.0
                        if _truth_diag == "REVIEW" and _truth_diag_rv <= 0:
                            _dbr = "weak_review_only"
                        elif _comp_diag <= 0:
                            _dbr = "no_comp_support"
                        elif _src_diag in {"price_anchor_fallback", "price_anchor_emergency", "floor_fallback"}:
                            _dbr = "no_trusted_mv"
                        elif _src_diag in {"structured_fallback", "fallback_comp_support"}:
                            _dbr = "hidden_non_premium_review"
                        elif not _truth_diag_rv and not _safe_float(_drow.get("true_market_value")):
                            _dbr = "low_commercial_value"
                        else:
                            _dbr = "base_noise"
                        print(f"[MV_DISPLAY_REASON_RESOLVED] item={str(_drow.get('source_item_id') or _drow.get('item_id') or '?')[:16]} derived_reason={_dbr}")
                    _dbr_key = _dbr.replace("Blocked: ", "").replace(" ", "_").lower()[:28]
                    _mv_display_blocked[_dbr_key] = _mv_display_blocked.get(_dbr_key, 0) + 1
                    if len(_mv_display_samples) < 4:
                        _mv_display_samples.append(
                            "item={} display=None blocked_reason={}".format(
                                str(_drow.get("source_item_id") or _drow.get("item_id") or "?")[:16],
                                _dbr_key,
                            )
                        )
            print("[ES][MV_DISPLAY] rows={} true_mv={} review_est={} blocked={}".format(
                len(_view_models),
                _mv_display_count,
                _mv_review_display_count,
                len(_view_models) - _mv_display_count - _mv_review_display_count,
            ))
            if _mv_display_blocked:
                print("[ES][MV_DISPLAY_REASON] {}".format(
                    " ".join("{}={}".format(_k, _v) for _k, _v in sorted(_mv_display_blocked.items()))
                ))
            for _sample in _mv_display_samples:
                print("[ES][MV_DISPLAY_SAMPLE] {}".format(_sample))

            _action_ready_rows = [(_row, _view) for _row, _view in _view_models if _view.get("readiness_bucket") == "action_ready"]
            _premium_review_rows = [
                (_row, _view)
                for _row, _view in _view_models
                if (
                    bool(_row.get("promoted_live_candidate"))
                    or bool(_row.get("mv_resolved"))
                    or bool(_row.get("target_bid_ready"))
                    or str(_row.get("premium_review_status") or "").strip().lower() in {"resolved", "partial"}
                ) and (_row, _view) not in _action_ready_rows
            ]
            _monitor_rows = [(_row, _view) for _row, _view in _view_models if _view.get("readiness_bucket") == "monitor"]
            _monitor_rows = [(_row, _view) for _row, _view in _monitor_rows if (_row, _view) not in _premium_review_rows]
            _suppressed_rows = [(_row, _view) for _row, _view in _view_models if _view.get("readiness_bucket") == "suppressed"]
            _live_watchlist_pairs = [(_row, _view) for _row, _view in _view_models if _ui_is_live_watchlist_row(_row)]
            if _live_watchlist_pairs:
                _suppressed_rows = [(_row, _view) for _row, _view in _suppressed_rows if not _ui_is_live_watchlist_row(_row)]
            _recovered_rows = [(_row, _view) for _row, _view in _view_models if str(_row.get("recovery_stage") or "primary") != "primary"]
            _exact_rows = sum(1 for _row, _view in _view_models if str(_view.get("live_signal_tier") or "") == "tracked_exact")
            _family_valid_rows = sum(1 for _row, _view in _view_models if str(_view.get("live_signal_tier") or "") == "family_valid")
            _promoted_rows = sum(1 for _row, _view in _view_models if str(_view.get("live_signal_tier") or "") == "promoted")
            _raw_live_rows = sum(
                1
                for _row, _view in _view_models
                if bool(_row.get("forced_surface"))
                and not (
                    bool(_row.get("promoted_live_candidate"))
                    or bool(_row.get("mv_resolved"))
                    or bool(_row.get("target_bid_ready"))
                    or str(_row.get("premium_review_status") or "").strip().lower() in {"resolved", "partial"}
                )
            )
            _recovery_rows = sum(1 for _row, _view in _view_models if str(_view.get("live_signal_tier") or "") == "recovery" and str(_row.get("recovery_stage") or "") in {"tracked_expand", "window_expand"})
            _discovery_rows = sum(1 for _row, _view in _view_models if str(_row.get("recovery_stage") or "") == "discovery_fallback")
            _forced_surface_active = bool((_meta.get("auction_forced_surface_active") or False)) and _promoted_rows == 0 and not _action_ready_rows and not _premium_review_rows
            _forced_surface_stage = str((_meta.get("auction_forced_surface_stage") or "")).strip()
            _forced_surface_count = int((_meta.get("auction_forced_surface_count") or 0))
            _rows_without_mv = sum(1 for _row in _sorted_visible if (_safe_float(_row.get("mv_value")) or _safe_float(_row.get("market_value")) or 0.0) <= 0)
            _rows_without_comps = sum(1 for _row in _sorted_visible if int((_safe_float(_row.get("mv_comp_count")) or _safe_float(_row.get("comp_count")) or _safe_float(_row.get("comps_count")) or 0)) <= 0)
            _rows_with_target_bid = sum(1 for _, _view in _view_models if _view.get("target_bid_price") is not None)
            _conf_counts: Dict[str, int] = {}
            for _, _view in _view_models:
                _tier = str(_view.get("confidence_tier") or "unknown")
                _conf_counts[_tier] = int(_conf_counts.get(_tier, 0) or 0) + 1
            _suppressed_no_mv = sum(1 for _row, _view in _suppressed_rows if "No usable market value" in _es_get_suppression_reasons(_row, _view))
            _suppressed_no_comps = sum(1 for _row, _view in _suppressed_rows if "No comp support" in _es_get_suppression_reasons(_row, _view))
            _suppressed_negative_edge = sum(1 for _row, _view in _suppressed_rows if "Negative edge" in _es_get_suppression_reasons(_row, _view))
            _suppressed_no_target_bid = sum(1 for _row, _view in _suppressed_rows if "No valid target bid" in _es_get_suppression_reasons(_row, _view))
            print(
                f"[ES][VALUATION] matched_rows={len(_sorted_visible)} with_mv={len(_sorted_visible) - _rows_without_mv} "
                f"without_mv={_rows_without_mv} with_comps={len(_sorted_visible) - _rows_without_comps} "
                f"no_comps={_rows_without_comps} conf_counts={_conf_counts} target_bid_ready={_rows_with_target_bid} "
                f"primary_ready={len(_action_ready_rows)} suppressed={len(_suppressed_rows)}"
            )
            print(
                f"[ES][QUALITY] total_rows={len(_sorted_visible)} action_ready={len(_action_ready_rows)} "
                f"monitor={len(_monitor_rows)} suppressed={len(_suppressed_rows)} no_mv={_rows_without_mv} "
                f"no_comps={_rows_without_comps} target_bid_ready={_rows_with_target_bid} "
                f"suppressed_no_mv={_suppressed_no_mv} suppressed_no_comps={_suppressed_no_comps} "
                f"suppressed_negative_edge={_suppressed_negative_edge} suppressed_no_target_bid={_suppressed_no_target_bid}"
            )
            _time_ui_samples = [
                (str(int(round(float(_view.get("remaining_seconds"))))), str(_view.get("formatted_time_left") or "Time unknown"))
                for _, _view in _view_models
                if _view.get("remaining_seconds") is not None
            ][:5]
            if _time_ui_samples:
                print(f"[ES][TIME_UI] sample_labels={_time_ui_samples}")
            # ─── Decision Layer: three-bucket split ────────────────────────────────
            # Sniper Board = EXECUTE_NOW / SNIPE (true actionable) + SNIPER_CANDIDATE.
            #   SNIPER_CANDIDATE: clean identity + heat or score above threshold.
            #   Max 3 cards total on sniper board — hero card format.
            # Watchlist = remaining clean-identity high-heat cards. Max 8. Compact format.
            # Everything else → suppressed expander.
            _MAX_SNIPER_BOARD = 5
            _MAX_WATCHLIST = 8
            _dl_input = len(_view_models)
            _suppressed_ids = {
                str(_r.get("source_item_id") or _r.get("item_id") or id(_r))
                for _r, _v in _suppressed_rows
            }

            _actionable_bucket: List = []
            _sniper_candidate_bucket: List = []
            _watchlist_hero_bucket: List = []
            _watchlist_candidates: List = []
            _fallback_admissions: List = []
            _fallback_candidates: List = []
            _dl_remainder: List = []
            _commercial_hidden_pairs: List = []
            _tier_a_bucket: List = []   # max_bid >= current_price * 1.15
            _tier_b_bucket: List = []   # max_bid >= current_price * 1.05
            _fallback_drop_counts: Dict[str, int] = {}
            _review_promotion_reason_counts: Dict[str, int] = {}

            def _record_review_promotion_reasons(_profile: Dict[str, Any], *, bucket: str = "", rejection_reason: str = "") -> None:
                _labels = set()
                for _reason in list((_profile or {}).get("promotion_reasons") or []):
                    if str(_reason or "").strip():
                        _labels.add(str(_reason).strip())
                if bucket:
                    _labels.add(f"bucket_{str(bucket).strip().lower()}")
                if rejection_reason:
                    _labels.add(str(rejection_reason).strip())
                for _label in _labels:
                    _review_promotion_reason_counts[_label] = int(_review_promotion_reason_counts.get(_label, 0) or 0) + 1

            _watchlist_rescue_metrics: Dict[str, int] = {
                "input": 0,
                "rescued_attempted": 0,
                "rescued_allowed": 0,
                "rescued_blocked": 0,
            }
            _premium_secondary_metrics: Dict[str, int] = {
                "input": 0,
                "allowed": 0,
                "blocked": 0,
            }
            _watchlist_append_metrics: Dict[str, int] = {
                "attempted": 0,
                "allowed": 0,
                "blocked": 0,
            }

            def _ui_try_watchlist_admission(
                _candidate_row: Dict[str, Any],
                _candidate_view: Dict[str, Any],
                *,
                _target_bucket: List,
            ) -> bool:
                _watchlist_append_metrics["attempted"] += 1
                _premium_secondary_metrics["input"] += 1
                _candidate_row = _ui_preserve_live_surface_row_contract(_candidate_row)
                if bool((_candidate_row or {}).get("board_contract_preserved_live")):
                    _candidate_view = dict(_candidate_view or {})
                    _candidate_view["board_bucket"] = str((_candidate_row or {}).get("board_bucket") or "WATCH")
                    _candidate_view["execution_tier"] = _candidate_view["board_bucket"]
                    _candidate_view["execution_decision"] = _es_board_execution_decision(_candidate_view["board_bucket"])
                    _watchlist_append_metrics["allowed"] += 1
                    _premium_secondary_metrics["allowed"] += 1
                    _target_bucket.append((_candidate_row, _candidate_view))
                    _ui_live_preserve_log("LIVE_RENDER_PRESERVE_ASSERT", _candidate_row)
                    return True
                _append_contract = _ui_watchlist_append_contract(_candidate_row)
                _title = str((_candidate_row or {}).get("title") or (_candidate_row or {}).get("source_title") or "").strip()[:140]
                _item = _ui_board_contract_item_key(_candidate_row)[:32]
                _allow = bool(_append_contract.get("allow"))
                _reason = str(_append_contract.get("reason") or "dead_review_only_no_evidence_no_bid").strip() or "dead_review_only_no_evidence_no_bid"
                print(
                    f"[WATCHLIST_APPEND_SINK] title={_title} item={_item} "
                    f"allow={1 if _allow else 0} reason={_reason}"
                )
                if not _allow:
                    _watchlist_append_metrics["blocked"] += 1
                    _premium_secondary_metrics["blocked"] += 1
                    print(
                        f"[WATCHLIST_APPEND_BLOCK] title={_title} item={_item} "
                        f"reason={_reason}"
                    )
                    return False
                _watchlist_append_metrics["allowed"] += 1
                _premium_secondary_metrics["allowed"] += 1
                _target_bucket.append((_candidate_row, _candidate_view))
                return True

            _live_preserve_routed_sniper = 0
            _live_preserve_routed_watch = 0
            _live_preserve_bucket_fallbacks_blocked = 0
            _live_preserve_downgrades_blocked = 0

            # ── LANE_ROTATION_STATE — session diversity memory snapshot ────
            try:
                _lrs_recent_players = list(st.session_state.get("es_recent_players") or [])
                _lrs_recent_products = list(st.session_state.get("es_recent_products") or [])
                _lrs_recent_item_ids = list(st.session_state.get("es_recent_item_ids") or [])
                _lrs_player_repeats = {}
                for _p in _lrs_recent_players:
                    _lrs_player_repeats[_p] = _lrs_player_repeats.get(_p, 0) + 1
                _lrs_top_repeats = sorted(_lrs_player_repeats.items(), key=lambda x: -x[1])[:5]
                print(
                    f"[LANE_ROTATION_STATE] "
                    f"recent_players={len(_lrs_recent_players)} "
                    f"recent_products={len(_lrs_recent_products)} "
                    f"recent_item_ids={len(_lrs_recent_item_ids)} "
                    f"top_player_repeats={_lrs_top_repeats}"
                )
            except Exception as _lrs_exc:
                print(f"[LANE_ROTATION_STATE] error_type={type(_lrs_exc).__name__}")
                _lrs_recent_item_ids = []
            _lrs_seen_iid_set = {str(_x or "").strip().lower() for _x in _lrs_recent_item_ids if _x}

            # Per-loop counters for the suppression logs.
            _seen_item_recurring = 0
            _pass_overpriced_seen = 0
            _pass_overpriced_in_actionable = 0
            for _r, _v in _view_models:
                # ── SEEN_ITEM_FILTER — track items already seen in prior scans ──
                _sif_iid = str(
                    (_r or {}).get("source_item_id")
                    or (_r or {}).get("item_id")
                    or (_r or {}).get("itemId")
                    or ""
                ).strip().lower()
                _sif_was_seen = bool(_sif_iid and _sif_iid in _lrs_seen_iid_set)
                _sif_final_decision = str((_r or {}).get("execution_final_decision") or (_r or {}).get("final_execution_decision") or "").strip().upper()
                if _sif_was_seen:
                    _seen_item_recurring += 1
                    try:
                        print(
                            f"[SEEN_ITEM_FILTER] "
                            f"item_id={_sif_iid[:32]} "
                            f"title={str((_r or {}).get('title') or '')[:120]} "
                            f"final_decision={_sif_final_decision or 'unknown'} "
                            f"action=keep_observability_only "
                            f"reason=item_id_in_session_recent_set"
                        )
                    except Exception:
                        pass
                # ── PASS_OVERPRICED_SUPPRESS — surface monopolizing PASS rows ──
                if _sif_final_decision in {"PASS_OVERPRICED", "PASS"}:
                    _pass_overpriced_seen += 1
                    try:
                        _po_edge_dollars = (_v or {}).get("final_edge_dollars")
                        _po_edge_pct = (_v or {}).get("final_edge_pct")
                        print(
                            f"[PASS_OVERPRICED_SUPPRESS] "
                            f"item_id={_sif_iid[:32]} "
                            f"title={str((_r or {}).get('title') or '')[:120]} "
                            f"final_decision={_sif_final_decision} "
                            f"edge_dollars={_po_edge_dollars} "
                            f"edge_pct={_po_edge_pct} "
                            f"recurring_from_prior_scan={1 if _sif_was_seen else 0} "
                            f"action=keep_observability_only"
                        )
                    except Exception:
                        pass
                # ── LIVE PRESERVE EARLY BYPASS ─────────────────────────────
                # ── LIVE PRESERVE EARLY BYPASS ─────────────────────────────
                # Rows already stamped board_contract_preserved_live (or carrying
                # late-live-rescue / final-visible-append-authority signals) are
                # routed to the correct bucket BEFORE any of the readiness /
                # commercial-visibility / long-dated / heat-and-viability gates
                # below can silently drop them into _dl_remainder. The preserve
                # helper also rewrites bucket fields, so the existing pipeline
                # then sees the right values and renders.
                _r = _ui_preserve_live_surface_row_contract(_r)
                if isinstance(_r, dict) and bool(_r.get("board_contract_preserved_live")):
                    _live_decision = str(_r.get("execution_final_decision") or "").strip().upper()
                    _live_bucket = str(_r.get("execution_admission_bucket") or "").strip().lower()
                    _live_view = dict(_v)
                    _live_is_sniper = (_live_decision == "SNIPE") or (_live_bucket == "sniper")
                    if _live_is_sniper:
                        _live_view["execution_decision"] = "EXECUTE_NOW"
                        _live_view["execution_tier"] = "SNIPE"
                        _live_view["board_bucket"] = "SNIPER"
                        _live_view["_board_bucket"] = "SNIPER"
                    else:
                        _live_view["execution_decision"] = "WATCH"
                        _live_view["execution_tier"] = "WATCH"
                        _live_view["board_bucket"] = "WATCH"
                        _live_view["_board_bucket"] = "WATCH"
                    _live_view["commercially_visible"] = True
                    _live_view["board_visible"] = True
                    _live_view["_live_preserve_route"] = True
                    if _live_is_sniper:
                        _actionable_bucket.append((_r, _live_view))
                        _live_preserve_routed_sniper += 1
                    else:
                        _ui_try_watchlist_admission(_r, _live_view, _target_bucket=_watchlist_candidates)
                        _live_preserve_routed_watch += 1
                    _live_preserve_bucket_fallbacks_blocked += 1
                    _live_preserve_downgrades_blocked += 1
                    print(
                        f"[LIVE_RENDER_PRESERVE] "
                        f"title={str((_r or {}).get('title') or '')[:120]} "
                        f"decision={_live_decision} "
                        f"bucket={'sniper' if _live_is_sniper else 'watchlist'} "
                        f"rowsource=preserve_early_bypass "
                        f"visible=1"
                    )
                    _ui_live_preserve_log("LIVE_RENDER_PRESERVE_ASSERT", _r)
                    continue
                # ───────────────────────────────────────────────────────────
                _fallback_profile = _es_fallback_candidate_profile(_r)
                _fallback_view = dict(_v)
                if bool(_fallback_profile.get("allow")):
                    _fallback_bucket = str(_fallback_profile.get("board_bucket") or "").strip().upper()
                    _fallback_view["execution_decision"] = _es_board_execution_decision(_fallback_bucket)
                    _fallback_view["execution_tier"] = _fallback_bucket or "REVIEW"
                    _fallback_view["board_bucket"] = _fallback_bucket or "REVIEW"
                    if isinstance(_r, dict):
                        _r["_fallback_candidate_admit"] = True
                        _r["_fallback_candidate_profile"] = dict(_fallback_profile)
                        _r["board_bucket"] = _fallback_bucket or str(_r.get("board_bucket") or "REVIEW")
                        _r["_board_bucket"] = str(_r.get("board_bucket") or "REVIEW")
                        _r["execution_decision"] = _es_board_execution_decision(_fallback_bucket)
                    _fallback_admissions.append((_r, _fallback_view))
                _bucket_state = _resolve_es_render_bucket_state(_r, _fallback_view, default_bucket="REVIEW")
                _fallback_bucket = str(_bucket_state.get("bucket_value") or "").strip().upper()
                _fallback_bucket_missing = bool(_bucket_state.get("default_used"))
                if _fallback_bucket and not _fallback_bucket_missing:
                    if isinstance(_r, dict):
                        _r["board_bucket"] = _fallback_bucket
                        _r["_board_bucket"] = _fallback_bucket
                        _r["execution_decision"] = _es_board_execution_decision(_fallback_bucket)
                        _r["_fallback_displayable"] = True
                    _fallback_view["execution_decision"] = _es_board_execution_decision(_fallback_bucket)
                    _fallback_view["execution_tier"] = _fallback_bucket
                    _fallback_view["board_bucket"] = _fallback_bucket
                    _fallback_view["_fallback_displayable"] = True
                    _fallback_candidates.append((_r, _fallback_view))
                    _record_review_promotion_reasons(_fallback_profile, bucket=_fallback_bucket)
                else:
                    if isinstance(_r, dict):
                        _r["_fallback_displayable"] = False
                    _fallback_view["_fallback_displayable"] = False
                    _fallback_truth = str(
                        _r.get("valuation_truth_tier")
                        or _r.get("_valuation_truth_tier")
                        or ""
                    ).strip().upper()
                    _fallback_review_value = _safe_float(
                        _r.get("review_estimate_value") or _r.get("anchored_estimate_value")
                    ) or 0.0
                    if _fallback_truth == "REVIEW" or _fallback_review_value > 0:
                        _fallback_reason = str(_fallback_profile.get("reason") or "not_review_fallback")
                        _fallback_drop_counts[_fallback_reason] = _fallback_drop_counts.get(_fallback_reason, 0) + 1
                        _record_review_promotion_reasons(_fallback_profile, rejection_reason=_fallback_reason)
                _ed = str(_v.get("execution_decision") or _r.get("execution_decision") or "PASS")
                _es_score = float(_v.get("execution_score") or _r.get("execution_score") or 0.0)
                _sniper_score = float(_v.get("sniper_board_score") or _r.get("sniper_board_score") or 0.0)
                _readiness = str(_v.get("readiness_bucket") or "monitor")
                _fit_tier = str(_v.get("target_fit_tier") or _r.get("target_fit_tier") or "").lower()
                _entity_status = str(_r.get("entity_match_status") or "").upper()
                _heat = float(_v.get("whatnot_heat_score") or _r.get("whatnot_heat_score") or 0.0)
                _desirability = float(_v.get("desirability_score") or _r.get("desirability_score") or 0.0)
                _rescue = str(_v.get("rescue_trust_tier") or _r.get("rescue_trust_tier") or "none").lower()
                _comps = int(_v.get("comp_count") or _r.get("mv_comp_count") or _r.get("comp_count") or 0)
                _hero_eligible = bool(_v.get("hero_board_eligible") or _r.get("hero_board_eligible"))
                _hero_tier = str(_v.get("hero_tier") or _r.get("hero_tier") or "").strip().upper()
                _target_bid_conf = str(_v.get("target_bid_confidence") or _r.get("target_bid_confidence") or "NONE").strip().upper()
                _target_bid_ready = bool(_v.get("target_bid_ready") or _r.get("target_bid_ready"))
                _has_mv = bool(_v.get("has_valid_mv") or _r.get("has_valid_mv") or ((_safe_float(_r.get("mv_value")) or _safe_float(_r.get("market_value")) or 0.0) > 0))
                _commercially_visible = bool(_v.get("commercially_visible", _r.get("commercially_visible", True)))
                _commercial_bucket = str(_v.get("commercial_bucket") or _r.get("commercial_bucket") or "WEAK").strip().upper()
                _commercially_suppressed = bool(_v.get("commercially_suppressed") or _r.get("commercially_suppressed"))
                _edge_dollars = float(_v.get("edge_dollars") or _r.get("edge_dollars") or ((_safe_float(_r.get("market_value")) or 0.0) - (_safe_float(_r.get("current_price")) or _safe_float(_r.get("current_bid")) or 0.0)))
                _mv_source = str(_v.get("market_value_source") or _r.get("market_value_source") or _r.get("mv_source") or "").strip().lower()
                _is_suppressed = _readiness == "suppressed"
                _hero_surface_blocked = str(
                    _v.get("_hero_surface_blocked")
                    or _v.get("hero_surface_blocked")
                    or _r.get("_hero_surface_blocked")
                    or _r.get("hero_surface_blocked")
                    or ""
                ).strip().lower() in {"1", "true", "yes", "y", "on"}
                if _hero_surface_blocked:
                    _hero_eligible = False
                    _hero_tier = ""
                    _r["hero_board_eligible"] = False
                    _r["hero_tier"] = ""
                    _v["hero_board_eligible"] = False
                    _v["hero_tier"] = ""

                if _is_suppressed:
                    _dl_remainder.append((_r, _v))
                    continue
                if _commercially_suppressed or not _commercially_visible:
                    if _ui_is_engine_visible_watchlist_candidate(_r):
                        _log_watchlist_handoff_drop(_r, dropped_by="commercial_visibility_gate")
                    _commercial_hidden_pairs.append((_r, _v))
                    continue

                # ── HARD TIME GATE ────────────────────────────────────────────────────
                # Sniper Board = auctions ending SOON. This gate enforces urgency
                # routing before any hero/tier bucket assignment.
                #   ≤ 3h  → EXECUTE_NOW eligible  (hero slot)
                #   ≤ 6h  → SNIPER_CANDIDATE eligible  (sniper slot)
                #   6-24h → PREPARE range — watchlist only, never sniper hero
                #   > 24h → long-dated — suppressed from main board entirely
                # Unknown time defaults to 999999 (far-future, conservative).
                _ui_secs = float(
                    _v.get("remaining_seconds")
                    or _r.get("remaining_seconds")
                    or _r.get("seconds_remaining")
                    or _r.get("source_time_remaining_seconds")
                    or 999999.0
                )
                _ui_within_execute  = _ui_secs <= 10800   # ≤ 3h
                _ui_within_sniper   = _ui_secs <= 21600   # ≤ 6h
                _ui_is_prepare      = 21600 < _ui_secs <= 86400   # 6-24h
                _ui_is_long_dated   = _ui_secs > 86400            # > 24h
                # Endgame-chase rows bypass the long-dated drop (structural premium value).
                _ui_endgame_exempt = bool(
                    str(_r.get("endgame_tier") or "").strip().lower() == "endgame"
                    or str(_r.get("chase_class") or "").strip().upper() == "ENDGAME_CHASE"
                )
                if _ui_is_long_dated and not _ui_endgame_exempt:
                    print(
                        f"[UI_TIME_GATE_SUPPRESS] secs={_ui_secs:.0f} ({_ui_secs/3600:.1f}h) "
                        f"title={str(_r.get('title') or '')[:80]} — long-dated, suppressed from main board"
                    )
                    _dl_remainder.append((_r, _v))
                    continue

                # Bucket 1: hero-eligible actionable cards only
                if _hero_eligible and _hero_tier == "ACTIONABLE_HERO":
                    if _ui_within_execute or _ui_endgame_exempt:
                        _actionable_bucket.append((_r, _v))
                    elif _ui_within_sniper:
                        # 3-6h: demote from execute-hero to sniper-candidate
                        _sc_view = dict(_v)
                        _sc_view["execution_decision"] = "SNIPER_CANDIDATE"
                        _sniper_candidate_bucket.append((_r, _sc_view))
                        print(
                            f"[UI_TIME_DEMOTE] ACTIONABLE→SNIPER_CANDIDATE secs={_ui_secs:.0f} "
                            f"title={str(_r.get('title') or '')[:80]}"
                        )
                    else:
                        # prepare range (6-24h): watchlist only
                        _prep_view = dict(_v)
                        _prep_view["execution_decision"] = "WATCH"
                        _prep_view["_time_demote_reason"] = f"prepare_range:{_ui_secs/3600:.1f}h"
                        _ui_try_watchlist_admission(_r, _prep_view, _target_bucket=_watchlist_candidates)
                        print(
                            f"[UI_TIME_DEMOTE] ACTIONABLE→WATCHLIST secs={_ui_secs:.0f} "
                            f"title={str(_r.get('title') or '')[:80]}"
                        )
                    continue

                # Clean identity check (used for both sniper candidate and watchlist)
                _clean_identity = (
                    _fit_tier in {"exact", "strong_family", "exact_match", "strong_match"}
                    or _entity_status in {"EXACT", "STRONG_FAMILY", "EXACT_MATCH"}
                )
                _no_rescue = _rescue == "none"

                # Bucket 2: premium sniper candidates must be hero-eligible.
                if _hero_eligible and _hero_tier == "SNIPER_CANDIDATE_HERO":
                    _sc_view = dict(_v)
                    _sc_view["execution_decision"] = "SNIPER_CANDIDATE"
                    if _ui_within_sniper or _ui_endgame_exempt:
                        _sniper_candidate_bucket.append((_r, _sc_view))
                    else:
                        # prepare range: demote to watchlist
                        _sc_view["execution_decision"] = "WATCH"
                        _sc_view["_time_demote_reason"] = f"prepare_range:{_ui_secs/3600:.1f}h"
                        _ui_try_watchlist_admission(_r, _sc_view, _target_bucket=_watchlist_candidates)
                        print(
                            f"[UI_TIME_DEMOTE] SNIPER_CANDIDATE→WATCHLIST secs={_ui_secs:.0f} "
                            f"title={str(_r.get('title') or '')[:80]}"
                        )
                    continue

                # Rare fallback hero: only used when premium inventory is thin.
                if _hero_eligible and _hero_tier == "WATCHLIST_HERO":
                    _wh_view = dict(_v)
                    _wh_view["execution_decision"] = "WATCH"
                    _ui_try_watchlist_admission(_r, _wh_view, _target_bucket=_watchlist_hero_bucket)
                    continue

                # ── Tier-based promotion: A (>=15% edge) and B (>=5% edge) ─────────────
                # Rescue rows are excluded. No minimum heat or identity requirement.
                # target_bid_price is the engine-computed max bid (MV * pct or explicit).
                _mb_val = float(
                    _v.get("target_bid_price")
                    or _r.get("target_bid_price") or _r.get("adjusted_max_bid")
                    or _r.get("target_max_bid") or _r.get("max_bid") or 0.0
                )
                _cp_val = float(_r.get("current_price") or _r.get("current_bid") or 0.0)
                # Trust rule: tier promotion requires hybrid-validated pricing.
                # legacy_comp_engine rows are always blocked (no fingerprint, no strict validation).
                # Fallback estimate rows (mv_valid=True, market_value_source="market_estimate_fallback")
                # are eligible for Tier B only; Tier A requires HIGH or MEDIUM confidence.
                _mv_auth_for_tier = (
                    bool(_r.get("mv_valid", False))
                    and str(_r.get("market_value_source") or "") != "legacy_comp_engine"
                )
                _mv_conf_for_tier = str(_r.get("mv_confidence_strict") or "").upper()
                _mv_tier_a_eligible = _mv_conf_for_tier in {"HIGH", "MEDIUM"}
                if _no_rescue and _mb_val > 0 and _cp_val > 0 and _mv_auth_for_tier and _commercial_bucket in {"ELITE", "STRONG"} and _edge_dollars >= 8.0 and _mv_source != "price_anchor_fallback":
                    _tier_ratio = _mb_val / _cp_val
                    _tier_edge  = (_mb_val - _cp_val) / _cp_val * 100.0
                    if _tier_ratio >= 1.15 and _mv_tier_a_eligible:
                        _t_view = dict(_v)
                        _t_view["execution_tier"]    = "A"
                        _t_view["edge_pct"]          = _tier_edge
                        _t_view["max_bid"]           = _mb_val
                        _t_view["mv_estimate"]       = float(_r.get("mv_value") or _r.get("market_value") or 0.0) or None
                        _t_view["execution_decision"]= "SNIPE"
                        if _ui_within_sniper or _ui_endgame_exempt:
                            _tier_a_bucket.append((_r, _t_view))
                        else:
                            _t_view["execution_decision"] = "WATCH"
                            _t_view["_time_demote_reason"] = f"prepare_range:{_ui_secs/3600:.1f}h"
                            _ui_try_watchlist_admission(_r, _t_view, _target_bucket=_watchlist_candidates)
                            print(
                                f"[UI_TIME_DEMOTE] TIER_A→WATCHLIST secs={_ui_secs:.0f} "
                                f"title={str(_r.get('title') or '')[:80]}"
                            )
                        continue
                    elif _tier_ratio >= 1.05:
                        _t_view = dict(_v)
                        _t_view["execution_tier"]    = "B"
                        _t_view["edge_pct"]          = _tier_edge
                        _t_view["max_bid"]           = _mb_val
                        _t_view["mv_estimate"]       = float(_r.get("mv_value") or _r.get("market_value") or 0.0) or None
                        _t_view["execution_decision"]= "SNIPER_CANDIDATE"
                        if _ui_within_sniper or _ui_endgame_exempt:
                            _tier_b_bucket.append((_r, _t_view))
                        else:
                            _t_view["execution_decision"] = "WATCH"
                            _t_view["_time_demote_reason"] = f"prepare_range:{_ui_secs/3600:.1f}h"
                            _ui_try_watchlist_admission(_r, _t_view, _target_bucket=_watchlist_candidates)
                            print(
                                f"[UI_TIME_DEMOTE] TIER_B→WATCHLIST secs={_ui_secs:.0f} "
                                f"title={str(_r.get('title') or '')[:80]}"
                            )
                        continue

                # Watchlist absorbs weaker but still interesting clean rows.
                _has_heat = _heat >= 32.0 or _desirability >= 28.0 or _sniper_score >= 38.0
                _watchlist_viable = (_target_bid_conf != "NONE" or _has_mv or _comps > 0 or _heat >= 55.0) and _commercial_bucket in {"MID", "STRONG", "ELITE"} and _edge_dollars >= 4.0
                if _clean_identity and _has_heat and _no_rescue and _watchlist_viable:
                    _ui_try_watchlist_admission(_r, _v, _target_bucket=_watchlist_candidates)
                else:
                    _dl_remainder.append((_r, _v))

            print(
                f"[FALLBACK_ADMISSION] count={len(_fallback_admissions)} "
                f"displayable={len(_fallback_candidates)}"
            )
            for _fallback_reason, _fallback_count in sorted(_fallback_drop_counts.items()):
                print(
                    f"[FALLBACK_DROPPED_REASON] reason={_fallback_reason} "
                    f"count={_fallback_count}"
                )

            # ── Engine-resolved row rescue ────────────────────────────────────────────
            # Rows the local readiness gate suppressed but the engine already resolved
            # as board_visible + watchlist/monitor. Honor engine-stamped routing.
            # Inline commercial quality gate prevents weak/low-dollar rows from taking
            # prime watchlist space even when rescued.
            _engine_rescued_watch: List = []
            _engine_rescued_demoted: List = []
            _new_dl_remainder: List = []
            for _r, _v in _dl_remainder:
                _eng_bucket = str(_r.get("execution_admission_bucket") or "").strip().lower()
                _eng_visible = bool(_r.get("board_visible"))
                if _eng_visible and _eng_bucket in {"watchlist", "monitor"}:
                    _iid = str(_r.get("source_item_id") or _r.get("item_id") or "")[:20]

                    # ── Commercial quality check (inline) ─────────────────────────────
                    _cw_chase   = str(_r.get("chase_class") or "").strip().upper()
                    _cw_bucket  = str(_r.get("commercial_bucket") or "WEAK").strip().upper()
                    _cw_endgame = str(_r.get("endgame_tier") or "").strip().lower()
                    _cw_title   = str(_r.get("title") or _r.get("source_title") or "").lower()
                    _cw_rev_est = _safe_float(_r.get("review_estimate_value")) or 0.0
                    _cw_true_mv = (_safe_float(_r.get("true_market_value"))
                                   or _safe_float(_r.get("market_value_true")) or 0.0)
                    _cw_best_mv = max(_cw_rev_est, _cw_true_mv)
                    _cw_price   = (_safe_float(_r.get("current_price"))
                                   or _safe_float(_r.get("current_bid")) or 0.0)
                    _cw_bid     = _safe_float(_r.get("target_bid")) or 0.0
                    _cw_comps   = int(_r.get("comp_count") or _r.get("mv_comp_count") or 0)
                    _cw_serial  = any(_s in _cw_title for _s in ("/1 ", "/5 ", "/10 ", "/25 ", "/49 "))
                    _cw_prestige = any(_t in _cw_title for _t in ("national treasures", "immaculate", "flawless", "spectra"))
                    _cw_premium  = any(_t in _cw_title for _t in (
                        "patch", "auto", "rpa", "relic", "refractor",
                        "prizm", "optic", "select", "chrome", "finest",
                    ))
                    # Engine already demoted? respect that flag
                    _cw_weak_flag = bool(_r.get("_commercial_watch_weak"))

                    _cw_fast_pass = (
                        _cw_chase == "ENDGAME_CHASE" or _cw_bucket == "ELITE"
                        or _cw_endgame == "endgame" or _cw_serial or _cw_prestige
                    )
                    _cw_clears_dollar = (
                        _cw_best_mv >= 15.0
                        or _cw_price >= 10.0
                        or (_cw_bid >= 10.0 and _cw_comps >= 1)
                    )
                    _cw_not_base_noise = not (
                        _cw_chase in {"COMMODITY", ""} and _cw_bucket in {"WEAK", ""}
                        and not _cw_premium and _cw_best_mv < 30.0 and _cw_price < 25.0
                    )
                    _commercial_ok_rescue = (
                        not _cw_weak_flag
                        and (_cw_fast_pass or (_cw_clears_dollar and _cw_not_base_noise))
                    )
                    # ── end inline commercial check ───────────────────────────────────

                    if _commercial_ok_rescue:
                        _watchlist_rescue_metrics["input"] += 1
                        _watchlist_rescue_metrics["rescued_attempted"] += 1
                        _rescue_contract = _ui_watchlist_rescue_contract(_r)
                        if not bool(_rescue_contract.get("allow")):
                            _watchlist_rescue_metrics["rescued_blocked"] += 1
                            _engine_rescued_demoted.append((_r, _v))
                            _new_dl_remainder.append((_r, _v))
                            continue
                        _watchlist_rescue_metrics["rescued_allowed"] += 1
                        _rescued_view = dict(_v)
                        _rescued_view["execution_decision"] = "WATCH"
                        print(
                            f"[BOARD_SOURCE_OVERRIDE] item={_iid} "
                            f"rescued_from=remainder bucket={_eng_bucket} "
                            f"title={str(_r.get('title') or '')[:60]}"
                        )
                        _ui_try_watchlist_admission(_r, _rescued_view, _target_bucket=_watchlist_candidates)
                        _engine_rescued_watch.append((_r, _rescued_view))
                    else:
                        # Commercially weak — demote to suppressed instead of main board
                        _cw_demote_reason = (
                            str(_r.get("_commercial_watch_weak_reason") or "")
                            or f"low_commercial_value:est={_cw_best_mv:.2f} price={_cw_price:.2f}"
                        )
                        print(
                            f"[COMMERCIAL_WATCH_DEMOTE] item={_iid} "
                            f"reason={_cw_demote_reason} "
                            f"title={str(_r.get('title') or '')[:60]}"
                        )
                        _engine_rescued_demoted.append((_r, _v))
                        _new_dl_remainder.append((_r, _v))
                else:
                    _new_dl_remainder.append((_r, _v))
            _dl_remainder = _new_dl_remainder
            print(
                f"[BOARD_SOURCE_OF_TRUTH] engine_rescued_watch={len(_engine_rescued_watch)} "
                f"engine_rescued_demoted={len(_engine_rescued_demoted)} "
                f"dl_remainder_after={len(_dl_remainder)} "
                f"watchlist_candidates_total={len(_watchlist_candidates)}"
            )
            print(
                f"[BOARD_RENDER_BIND] sniper={len(_actionable_bucket) + len(_sniper_candidate_bucket)} "
                f"watchlist_pool={len(_watchlist_candidates)} "
                f"rescued={len(_engine_rescued_watch)}"
            )

            # Sort hero buckets by hero score first, then execution/bidability.
            _TB_CONF_RANK = {"HIGH": 0, "MEDIUM": 1, "REVIEW": 2, "NONE": 3}

            # ── Final ranking-quality score ─────────────────────────────────
            # Layered on top of sniper_board_score / execution_score so the
            # board prefers liquid premium inventory (top NFL QBs / MLB / NBA
            # stars, elite rookies, premium parallels, low-serial autos, case
            # hits, PSA premium grades) and demotes weak inventory (unproven
            # prospects, low-heat players, niche/no product family). Pure
            # ranking; no valuation, comp, fetch, probe, window, or UI logic.
            import re as _es_rqs_re
            def _es_ranking_quality_score(_row: Dict[str, Any], _view: Dict[str, Any]) -> Dict[str, Any]:
                _r = _row or {}
                _v = _view or {}
                _heat = float(_v.get("whatnot_heat_score") or _r.get("whatnot_heat_score") or 0.0)
                _desire = float(_v.get("desirability_score") or _r.get("desirability_score") or 0.0)
                _commercial = str(_v.get("commercial_bucket") or _r.get("commercial_bucket") or "WEAK").strip().upper()
                _comps = int(_v.get("comp_count") or _r.get("mv_comp_count") or _r.get("comp_count") or 0)
                _conf = str(_v.get("target_bid_confidence") or _r.get("target_bid_confidence") or "NONE").strip().upper()
                _serial_raw = str(_r.get("serial_denominator") or _r.get("_hydrated_serial_denominator") or _r.get("serial") or "").strip()
                try:
                    _serial_n = int(_serial_raw) if _serial_raw and _serial_raw.isdigit() else None
                except Exception:
                    _serial_n = None
                _has_serial = bool(_serial_raw and _serial_raw.lower() not in {"0", "none", ""})
                _title_lc = str(_r.get("title") or _r.get("source_title") or "").lower()
                _has_auto = bool(_es_rqs_re.search(r"\b(auto|autograph)\b", _title_lc)) if _title_lc else False
                _has_patch_auto = bool(_es_rqs_re.search(r"\bpatch\s*auto\b", _title_lc)) if _title_lc else False
                _has_case_hit = bool(_es_rqs_re.search(
                    r"\b(kaboom|downtown|color\s*blast|case\s*hit|national\s*treasures|immaculate|flawless|spectra)\b",
                    _title_lc,
                )) if _title_lc else False
                _parallel_lc = str(
                    _r.get("parallel_family")
                    or _r.get("_hydrated_parallel_family")
                    or _r.get("parallel_name")
                    or _r.get("parallel")
                    or ""
                ).strip().lower()
                _is_premium_parallel = bool(
                    _parallel_lc and _parallel_lc not in {"base", "common", "none", "refractor"}
                )
                _grade_uc = str(_r.get("grade") or _r.get("grade_label") or "").strip().upper()
                _is_psa10 = "PSA 10" in _grade_uc or "PSA10" in _grade_uc or "BGS 9.5" in _grade_uc or "BGS 10" in _grade_uc
                _is_psa9 = (not _is_psa10) and ("PSA 9" in _grade_uc)
                _rookie = bool(_r.get("rookie_card") or _r.get("_is_rookie_card")) or bool(
                    _es_rqs_re.search(r"\b(rc|rookie)\b", _title_lc)
                )
                _sport = str(_r.get("sport") or _r.get("_target_sport") or "").strip().upper()
                _is_top_sport = _sport in {"NFL", "MLB", "NBA"}
                _elite_player = _heat >= 75.0 or _commercial == "ELITE" or _desire >= 75.0
                _strong_player = _heat >= 50.0 or _commercial == "STRONG" or _desire >= 50.0
                _liquid_player = _heat >= 35.0 or _commercial in {"STRONG", "ELITE", "MID"} or _desire >= 35.0
                _historically_searched = bool(
                    _r.get("recent_search_hits")
                    or _r.get("historically_searched")
                    or _r.get("_historically_searched")
                )

                # Liquidity score
                _liq = 0.0
                if _has_serial:
                    if _serial_n is not None and _serial_n <= 25:
                        _liq += 25.0
                    elif _serial_n is not None and _serial_n <= 99:
                        _liq += 18.0
                    elif _serial_n is not None and _serial_n <= 250:
                        _liq += 12.0
                    else:
                        _liq += 6.0
                if _has_auto:
                    _liq += 18.0
                if _has_patch_auto:
                    _liq += 8.0
                if _is_premium_parallel:
                    _liq += 12.0
                if _is_psa10:
                    _liq += 18.0
                elif _is_psa9:
                    _liq += 8.0
                if _has_case_hit:
                    _liq += 15.0
                if _commercial == "ELITE":
                    _liq += 15.0
                elif _commercial == "STRONG":
                    _liq += 10.0
                elif _commercial == "MID":
                    _liq += 4.0
                if _comps >= 8:
                    _liq += 10.0
                elif _comps >= 4:
                    _liq += 5.0
                if _conf == "HIGH":
                    _liq += 10.0
                elif _conf == "MEDIUM":
                    _liq += 5.0

                # Tier score (player quality)
                _tier = 0.0
                if _elite_player:
                    _tier += 50.0
                elif _strong_player:
                    _tier += 30.0
                elif _liquid_player:
                    _tier += 12.0
                else:
                    _tier -= 25.0    # non-elite player penalty
                if _is_top_sport and (_strong_player or _elite_player):
                    _tier += 15.0
                if _rookie and (_elite_player or _strong_player):
                    _tier += 15.0    # elite rookie boost
                if _historically_searched:
                    _tier += 8.0
                if not _liquid_player:
                    _tier -= 10.0    # low liquidity athlete
                # Unproven prospect penalty: no comps, no heat, no premium grade.
                if _comps == 0 and _heat < 25.0 and not _is_psa10 and not _has_auto and not _is_premium_parallel:
                    _tier -= 20.0
                # Niche product penalty: no product family resolved, not elite.
                _product_family_lc = str(
                    _r.get("product_family")
                    or _r.get("identity_product_family")
                    or _r.get("_hydrated_product_family")
                    or _r.get("target_product_family")
                    or _r.get("lane_product")
                    or ""
                ).strip().lower()
                _is_niche_product = (not _product_family_lc) or _product_family_lc in {"unknown", "none"}
                if _is_niche_product and not _elite_player:
                    _tier -= 15.0

                # Final rank: blend of existing engine score + new liquidity + tier
                _existing_score = float(
                    _v.get("sniper_board_score")
                    or _r.get("sniper_board_score")
                    or _v.get("execution_score")
                    or _r.get("execution_score")
                    or 0.0
                )
                _final = (_existing_score * 0.5) + (_liq * 0.3) + (_tier * 0.4)

                _reasons: List[str] = []
                if _elite_player:
                    _reasons.append("elite_player")
                elif _strong_player:
                    _reasons.append("strong_player")
                elif not _liquid_player:
                    _reasons.append("low_liquidity_player")
                if _is_top_sport and (_strong_player or _elite_player):
                    _reasons.append(f"top_{_sport.lower()}_star")
                if _rookie and (_elite_player or _strong_player):
                    _reasons.append("elite_rookie")
                if _has_auto:
                    _reasons.append("auto")
                if _has_patch_auto:
                    _reasons.append("patch_auto")
                if _has_serial and _serial_n is not None and _serial_n <= 99:
                    _reasons.append(f"serial/{_serial_n}")
                if _is_psa10:
                    _reasons.append("psa10")
                if _has_case_hit:
                    _reasons.append("case_hit")
                if _is_premium_parallel:
                    _reasons.append("premium_parallel")
                if _historically_searched:
                    _reasons.append("historically_searched")
                if _is_niche_product and not _elite_player:
                    _reasons.append("niche_product_penalty")
                if _comps == 0 and _heat < 25.0 and not _is_psa10 and not _has_auto and not _is_premium_parallel:
                    _reasons.append("unproven_prospect_penalty")
                if not _liquid_player:
                    _reasons.append("low_liquidity_penalty")
                return {
                    "liquidity_score": round(_liq, 2),
                    "tier_score": round(_tier, 2),
                    "final_rank_score": round(_final, 2),
                    "reason": ",".join(_reasons) or "default",
                }

            def _es_stamp_ranking_quality(_bucket: List) -> None:
                for _r_item, _v_item in (_bucket or []):
                    _scores = _es_ranking_quality_score(_r_item, _v_item)
                    if isinstance(_v_item, dict):
                        _v_item["liquidity_score"] = _scores["liquidity_score"]
                        _v_item["tier_score"] = _scores["tier_score"]
                        _v_item["final_rank_score"] = _scores["final_rank_score"]
                        _v_item["ranking_quality_reason"] = _scores["reason"]
                    if isinstance(_r_item, dict):
                        _r_item["final_rank_score"] = _scores["final_rank_score"]
                    print(
                        f"[RANKING_QUALITY_SCORE] "
                        f"player={str((_r_item or {}).get('player_name') or (_r_item or {}).get('canonical_player') or '')[:48]} "
                        f"product={str((_r_item or {}).get('product_family') or (_r_item or {}).get('identity_product_family') or (_r_item or {}).get('lane_product') or '')[:48]} "
                        f"liquidity_score={_scores['liquidity_score']} "
                        f"tier_score={_scores['tier_score']} "
                        f"final_rank_score={_scores['final_rank_score']} "
                        f"reason={_scores['reason']}"
                    )

            for _bucket_to_rank in (_actionable_bucket, _sniper_candidate_bucket, _watchlist_hero_bucket, _watchlist_candidates):
                _es_stamp_ranking_quality(_bucket_to_rank)
            # ────────────────────────────────────────────────────────────────

            _actionable_bucket.sort(
                key=lambda _rv: (
                    -float(_rv[1].get("final_rank_score") or _rv[0].get("final_rank_score") or 0.0),
                    -float(_rv[1].get("sniper_board_score") or _rv[0].get("sniper_board_score") or 0.0),
                    -float(_rv[1].get("execution_score") or _rv[0].get("execution_score") or 0.0),
                    _TB_CONF_RANK.get(str(_rv[1].get("target_bid_confidence") or _rv[0].get("target_bid_confidence") or "NONE").upper(), 3),
                    -float(_rv[1].get("whatnot_heat_score") or _rv[0].get("whatnot_heat_score") or 0.0),
                    float(_rv[1].get("remaining_seconds") or _rv[0].get("remaining_seconds") or 999999.0),
                )
            )
            _sniper_candidate_bucket.sort(
                key=lambda _rv: (
                    -float(_rv[1].get("final_rank_score") or _rv[0].get("final_rank_score") or 0.0),
                    -float(_rv[1].get("sniper_board_score") or _rv[0].get("sniper_board_score") or 0.0),
                    _TB_CONF_RANK.get(str(_rv[1].get("target_bid_confidence") or _rv[0].get("target_bid_confidence") or "NONE").upper(), 3),
                    -float(_rv[1].get("execution_score") or _rv[0].get("execution_score") or 0.0),
                    -float(_rv[0].get("whatnot_heat_score") or 0.0),
                )
            )
            _watchlist_hero_bucket.sort(
                key=lambda _rv: (
                    -float(_rv[1].get("final_rank_score") or _rv[0].get("final_rank_score") or 0.0),
                    -float(_rv[1].get("sniper_board_score") or _rv[0].get("sniper_board_score") or 0.0),
                    -float(_rv[1].get("whatnot_heat_score") or _rv[0].get("whatnot_heat_score") or 0.0),
                    -float(_rv[1].get("desirability_score") or _rv[0].get("desirability_score") or 0.0),
                )
            )

            # Sort tier buckets: best edge first, soonest ending, higher price slightly preferred.
            def _tier_sort_key(_rv):
                _e = float(_rv[1].get("edge_pct") or 0.0)
                _t = float(_rv[0].get("remaining_seconds") or 999999.0)
                _p = float(_rv[0].get("current_price") or _rv[0].get("current_bid") or 0.0)
                return (-_e, _t, -_p)
            _tier_a_bucket.sort(key=_tier_sort_key)
            _tier_b_bucket.sort(key=_tier_sort_key)

            # Sniper board = actionable heroes, then sniper-candidate heroes only.
            _slots_remaining = _MAX_SNIPER_BOARD - len(_actionable_bucket)
            _sniper_candidates_on_board = _sniper_candidate_bucket[:max(0, _slots_remaining)]
            _sniper_candidates_overflow = _sniper_candidate_bucket[max(0, _slots_remaining):]
            _sniper_board = _actionable_bucket + _sniper_candidates_on_board
            _watchlist_heroes_on_board: List = []
            _watchlist_hero_overflow: List = list(_watchlist_hero_bucket)

            # Fill remaining sniper board slots with tier A, then tier B.
            _slots_remaining = _MAX_SNIPER_BOARD - len(_sniper_board)
            _tier_a_on_board   = _tier_a_bucket[:max(0, _slots_remaining)]
            _tier_a_overflow   = _tier_a_bucket[max(0, _slots_remaining):]
            _slots_remaining   = _MAX_SNIPER_BOARD - len(_sniper_board) - len(_tier_a_on_board)
            _tier_b_on_board   = _tier_b_bucket[:max(0, _slots_remaining)]
            _tier_b_overflow   = _tier_b_bucket[max(0, _slots_remaining):]
            _sniper_board      = _sniper_board + _tier_a_on_board + _tier_b_on_board
            for _sr, _sv in _sniper_board:
                _ui_apply_canonical_board_contract(_sr, surface="sniper")
                if isinstance(_sr, dict):
                    _sr["board_bucket"] = "SNIPE"
                    _sr["_board_bucket"] = "SNIPE"
                if isinstance(_sv, dict):
                    _sv["board_bucket"] = "SNIPE"

            # Watchlist absorbs weaker but still interesting rows, plus hero overflow and tier overflow.
            _watchlist_pool = _watchlist_candidates + _sniper_candidates_overflow + _watchlist_hero_overflow + _tier_a_overflow + _tier_b_overflow
            for _wr, _wv in _watchlist_pool:
                _watch_bucket = str((_wr or {}).get("board_bucket") or (_wv or {}).get("board_bucket") or "").strip().upper()
                if _watch_bucket not in {"PREPARE", "MONITOR", "WATCH"}:
                    _watch_bucket = "WATCH"
                if isinstance(_wr, dict):
                    _wr["board_bucket"] = _watch_bucket
                    _wr["_board_bucket"] = _watch_bucket
                    _wr["execution_decision"] = _es_board_execution_decision(_watch_bucket)
                if isinstance(_wv, dict):
                    _wv["board_bucket"] = _watch_bucket
                    _wv["execution_decision"] = _es_board_execution_decision(_watch_bucket)
            _watchlist_candidates = list(_watchlist_pool)
            _handoff_rows = [_r for _r, _ in _view_models if isinstance(_r, dict)]
            print(
                f"[WATCHLIST_HANDOFF_INPUT] rows={len(_handoff_rows)} "
                f"engine_visible={sum(1 for _r in _handoff_rows if _ui_is_engine_visible_watchlist_candidate(_r))} "
                f"watchlist_flagged={sum(1 for _r in _handoff_rows if bool((_r or {}).get('_render_live_watchlist') or (_r or {}).get('render_live_watchlist')) or str((_r or {}).get('final_bucket') or (_r or {}).get('execution_admission_bucket') or '').strip().lower() == 'watchlist')} "
                f"board_visible={sum(1 for _r in _handoff_rows if bool((_r or {}).get('board_visible')))} "
                f"commercially_visible={sum(1 for _r in _handoff_rows if bool((_r or {}).get('commercially_visible')))}"
            )
            # Re-stamp ranking-quality on the merged watchlist pool so any rows
            # added since the earlier stamp (overflow, hero handoff) carry the
            # final_rank_score before sorting.
            _es_stamp_ranking_quality(_watchlist_candidates)
            _watchlist_candidates.sort(
                key=lambda _rv: (
                    {"PREPARE": 0, "MONITOR": 1, "WATCH": 2}.get(
                        str((_rv[0].get("board_bucket") if isinstance(_rv[0], dict) else "") or (_rv[1].get("board_bucket") if isinstance(_rv[1], dict) else "") or "WATCH").strip().upper(),
                        3,
                    ),
                    -float(_rv[1].get("final_rank_score") or _rv[0].get("final_rank_score") or 0.0),
                    -float(_rv[1].get("sniper_board_score") or _rv[0].get("sniper_board_score") or 0.0),
                    -float(_rv[1].get("whatnot_heat_score") or 0.0),
                    -float(_rv[1].get("desirability_score") or 0.0),
                    -int(_rv[1].get("comp_count") or _rv[0].get("comp_count") or 0),
                )
            )
            _watchlist_bucket = []
            _watchlist_hidden = []
            for _idx, (_row, _view) in enumerate(_watchlist_candidates):
                _watchlist_rescue_metrics["input"] += 1
                _watchlist_rescue_metrics["rescued_attempted"] += 1
                _rescue_contract = _ui_watchlist_rescue_contract(_row)
                if not bool(_rescue_contract.get("allow")):
                    _watchlist_rescue_metrics["rescued_blocked"] += 1
                    _watchlist_hidden.append((_row, _view))
                    continue
                _watchlist_rescue_metrics["rescued_allowed"] += 1
                _surface_allowed = int((_row or {}).get("final_surface_allowed", 1) or 0) > 0
                if _idx < _MAX_WATCHLIST and _surface_allowed:
                    if _ui_try_watchlist_admission(_row, _view, _target_bucket=_watchlist_bucket):
                        continue
                _watchlist_hidden.append((_row, _view))
                if _idx < _MAX_WATCHLIST and not _surface_allowed and _ui_is_engine_visible_watchlist_candidate(_row):
                    _log_watchlist_handoff_drop(_row, dropped_by="final_surface_allowed")
            for _hidden_r, _hidden_v in _watchlist_hidden:
                _hidden_profile = dict((_hidden_r or {}).get("_fallback_candidate_profile") or {})
                if _hidden_profile:
                    _record_review_promotion_reasons(_hidden_profile, rejection_reason="board_rank_lost")
                    _log_review_promotion_check(
                        _hidden_r,
                        _hidden_profile,
                        chosen="REJECT",
                        rejection_reason="board_rank_lost",
                        stage="watchlist_rank",
                    )

            # ── Watchlist visible quality gate ────────────────────────────────────
            # price_anchor_fallback / ambiguous-title rows cannot occupy the primary
            # visible slot regardless of how they were rescued. They remain in the
            # hidden pool (suppressed expander) so discovery is preserved but the
            # main watchlist slot stays clean and trustworthy.
            _watchlist_visible_ok:  List = []
            _watchlist_blocked_vis: List = []
            for _wr, _wv in _watchlist_bucket:
                _wvis_ok, _wvis_reason = _watchlist_visible_qualified(_wr)
                _wiid = str(_wr.get("source_item_id") or _wr.get("item_id") or "")[:20]
                if _wvis_ok:
                    _watchlist_visible_ok.append((_wr, _wv))
                    print(
                        f"[WATCHLIST_VISIBLE_PASS] item={_wiid} reason={_wvis_reason} "
                        f"title={str(_wr.get('title') or '')[:60]}"
                    )
                else:
                    # Stamp the row so no downstream fallback path can resurrect it
                    # into the primary visible slot. The row stays in suppressed pool
                    # for internal inspection but is ineligible for rehydration.
                    _wr["_watchlist_visible_blocked"] = True
                    if _ui_is_engine_visible_watchlist_candidate(_wr):
                        _log_watchlist_handoff_drop(_wr, dropped_by="watchlist_visible_quality_gate")
                    _watchlist_blocked_vis.append((_wr, _wv))
                    print(
                        f"[WATCHLIST_VISIBLE_BLOCK] item={_wiid} reason={_wvis_reason} "
                        f"title={str(_wr.get('title') or '')[:60]}"
                    )
            if _watchlist_visible_ok:
                print(
                    f"[WATCHLIST_VISIBLE_REASON] visible={len(_watchlist_visible_ok)} "
                    f"blocked={len(_watchlist_blocked_vis)} "
                    f"first_title={str(_watchlist_visible_ok[0][0].get('title') or '')[:60]}"
                )
            else:
                print(
                    f"[WATCHLIST_VISIBLE_REASON] visible=0 blocked={len(_watchlist_blocked_vis)} "
                    f"— empty visible watchlist by quality gate"
                )
            # Blocked rows fall back into hidden pool so they appear in suppressed expander
            _watchlist_hidden = _watchlist_blocked_vis + _watchlist_hidden
            _watchlist_bucket = _watchlist_visible_ok
            for _wr, _wv in _watchlist_bucket:
                _ui_apply_canonical_board_contract(_wr, surface="watchlist")

            # Rebuild suppressed list from remainder + overflow
            for _r, _v in _dl_remainder + _watchlist_hidden + _commercial_hidden_pairs:
                _rid = str(_r.get("source_item_id") or _r.get("item_id") or id(_r))
                if _rid not in _suppressed_ids:
                    _suppressed_rows = list(_suppressed_rows) + [(_r, _v)]
                    _suppressed_ids.add(_rid)

            _fallback_promoted = 0
            _fallback_rejected: Dict[str, int] = {}
            _fb_strict_board = len(_sniper_board)   # _n_sniper_board defined later; use list len
            _fb_fallback_candidates_count = len(_fallback_candidates)

            # Rows stamped by the visible quality gate must never be rehydrated into
            # the primary visible slot by any fallback path. Separate them first.
            _watchlist_fallback_gate_skipped = [
                (_r, _v) for _r, _v in _suppressed_rows
                if _es_is_resolved_board_row(_r) and bool(_r.get("_watchlist_visible_blocked"))
            ]
            _resolved_suppressed_rows = [
                (_r, _v) for _r, _v in _suppressed_rows
                if _es_is_resolved_board_row(_r) and not bool(_r.get("_watchlist_visible_blocked"))
            ]
            for _fbsk_r, _fbsk_v in _watchlist_fallback_gate_skipped:
                _fbsk_iid = str(_fbsk_r.get("source_item_id") or _fbsk_r.get("item_id") or "")[:20]
                print(
                    f"[WATCHLIST_FALLBACK_SKIP_BLOCKED] item={_fbsk_iid} "
                    f"title={str(_fbsk_r.get('title') or '')[:60]} "
                    f"reason=visible_gate_blocked_stamp"
                )
            print(
                f"[WATCHLIST_FALLBACK_SUMMARY] gate_skipped={len(_watchlist_fallback_gate_skipped)} "
                f"eligible={len(_resolved_suppressed_rows)} "
                f"sniper_empty={not bool(_sniper_board)} watchlist_empty={not bool(_watchlist_bucket)}"
            )
            _board_target_rows = min(_MAX_SNIPER_BOARD + _MAX_WATCHLIST, _BOARD_MIN_POPULATION)
            _board_total_pre_backfill = len(_sniper_board) + len(_watchlist_bucket)
            _backfill_slots = max(0, min(_MAX_WATCHLIST - len(_watchlist_bucket), _board_target_rows - _board_total_pre_backfill))
            _backfill_added_rows: List = []
            if _backfill_slots > 0 and _fallback_candidates:
                _board_ids = {
                    str(_r.get("source_item_id") or _r.get("item_id") or id(_r))
                    for _r, _ in (_sniper_board + _watchlist_bucket)
                }
                _seen_backfill_ids: set[str] = set()
                _backfill_pool: List = []
                for _bf_r, _bf_v in _fallback_candidates:
                    _bf_id = str(_bf_r.get("source_item_id") or _bf_r.get("item_id") or id(_bf_r))
                    if _bf_id in _board_ids or _bf_id in _seen_backfill_ids:
                        continue
                    _seen_backfill_ids.add(_bf_id)
                    _backfill_pool.append((_bf_r, _bf_v))
                _backfill_pool.sort(key=lambda _rv: _es_fallback_backfill_sort_key(_rv[0]))
                for _bf_r, _bf_v in _backfill_pool[:_backfill_slots]:
                    _watchlist_rescue_metrics["input"] += 1
                    _watchlist_rescue_metrics["rescued_attempted"] += 1
                    _rescue_contract = _ui_watchlist_rescue_contract(_bf_r)
                    if not bool(_rescue_contract.get("allow")):
                        _watchlist_rescue_metrics["rescued_blocked"] += 1
                        continue
                    _watchlist_rescue_metrics["rescued_allowed"] += 1
                    _profile = dict((_bf_r or {}).get("_fallback_candidate_profile") or {})
                    _bucket = str(_profile.get("board_bucket") or (_bf_v or {}).get("board_bucket") or "WATCH").strip().upper() or "WATCH"
                    if isinstance(_bf_r, dict):
                        _bf_r["_fallback_backfill"] = True
                        _bf_r["board_bucket"] = _bucket
                        _bf_r["_board_bucket"] = _bucket
                        _bf_r["_final_bucket"] = _bucket
                        _bf_r["execution_admission_bucket"] = "watchlist"
                        _bf_r["commercial_visibility"] = "watchlist"
                        _bf_r["commercially_visible"] = True
                        _bf_r["board_visible"] = True
                        _bf_r["execution_decision"] = _es_board_execution_decision(_bucket)
                        _bf_r["decision_reason"] = f"fallback_backfill_{_bucket.lower()}"
                    _backfill_view = dict(_bf_v)
                    _backfill_view["execution_decision"] = _es_board_execution_decision(_bucket)
                    _backfill_view["execution_tier"] = _bucket
                    _backfill_view["board_bucket"] = _bucket
                    if _ui_try_watchlist_admission(_bf_r, _backfill_view, _target_bucket=_watchlist_bucket):
                        _backfill_added_rows.append((_bf_r, _backfill_view))
                for _bf_r, _bf_v in _backfill_pool[_backfill_slots:]:
                    _profile = dict((_bf_r or {}).get("_fallback_candidate_profile") or {})
                    _record_review_promotion_reasons(_profile, rejection_reason="board_rank_lost")
                    _log_review_promotion_check(
                        _bf_r,
                        _profile,
                        chosen="REJECT",
                        rejection_reason="board_rank_lost",
                        stage="backfill_rank",
                    )
                if _backfill_added_rows:
                    _fallback_promoted += len(_backfill_added_rows)
                    _backfill_ids = {
                        str(_r.get("source_item_id") or _r.get("item_id") or id(_r))
                        for _r, _ in _backfill_added_rows
                    }
                    _suppressed_rows = [
                        (_r, _v) for _r, _v in _suppressed_rows
                        if str(_r.get("source_item_id") or _r.get("item_id") or id(_r)) not in _backfill_ids
                    ]
                    _suppressed_ids = {
                        str(_r.get("source_item_id") or _r.get("item_id") or id(_r))
                        for _r, _ in _suppressed_rows
                    }
                    print(
                        f"[BOARD_BACKFILL] count={len(_backfill_added_rows)} "
                        f"target={_board_target_rows} pre={_board_total_pre_backfill} "
                        f"post={len(_sniper_board) + len(_watchlist_bucket)}"
                    )
                else:
                    print(
                        f"[BOARD_BACKFILL] count=0 target={_board_target_rows} "
                        f"pre={_board_total_pre_backfill} post={_board_total_pre_backfill}"
                    )
            else:
                print(
                    f"[BOARD_BACKFILL] count=0 target={_board_target_rows} "
                    f"pre={_board_total_pre_backfill} post={_board_total_pre_backfill}"
                )

            # ── Fallback layer: surface valid auctions when board is empty ──────────
            # Activates ONLY when strict bucketing plus forced backfill still produced
            # neither sniper nor watchlist rows.
            # Scans the full suppressed pool for the basic auction sanity contract.
            # Does NOT invent MV, comps, or bid ceilings — missing data stays missing.
            if not _sniper_board and not _watchlist_bucket and _resolved_suppressed_rows:
                _fb_pool: List = []
                for _r, _v in _resolved_suppressed_rows:
                    _fb_item_id   = str(_r.get("source_item_id") or _r.get("item_id") or "").strip()
                    _fb_end_time  = str(_r.get("source_end_time") or _r.get("end_iso") or "").strip()
                    _fb_remaining = float(
                        _r.get("remaining_seconds")
                        or (_v.get("remaining_seconds") if isinstance(_v, dict) else None)
                        or 0.0
                    )
                    _fb_price     = float(_r.get("current_price") or _r.get("current_bid") or 0.0)
                    _fb_title     = str(_r.get("source_title") or _r.get("title") or "").strip()
                    _fb_lt        = str(_r.get("listing_type") or _r.get("source_listing_type") or "Auction").strip().lower()

                    _fb_reject = ""
                    if not _fb_item_id:
                        _fb_reject = "no_item_id"
                    elif not _fb_end_time:
                        _fb_reject = "no_end_time"
                    elif _fb_remaining <= 0:
                        _fb_reject = "expired"
                    elif _fb_price <= 0:
                        _fb_reject = "no_price"
                    elif not _fb_title:
                        _fb_reject = "no_title"
                    elif _fb_lt in {"fixedprice", "bin", "buy_it_now"} and "auction" not in _fb_lt:
                        _fb_reject = "non_auction"

                    if _fb_reject:
                        _fallback_rejected[_fb_reject] = _fallback_rejected.get(_fb_reject, 0) + 1
                        continue

                    # Stamp fallback classification — no precision invented
                    _fb_view = dict(_v) if isinstance(_v, dict) else {}
                    _fb_view["execution_decision"]         = "WATCH"
                    _fb_view["execution_tier"]             = "FALLBACK"
                    _fb_view["valuation_confidence_label"] = "LOW"
                    _fb_view["target_bid_status_label"]    = "UNAVAILABLE"
                    _fb_pool.append((_r, _fb_view))

                _fb_fallback_candidates_count = len(_fb_pool)
                # Sort: soonest-ending first, then cheapest
                _fb_pool.sort(key=lambda _rv: (
                    float(_rv[0].get("remaining_seconds") or 999999.0),
                    float(_rv[0].get("current_price") or _rv[0].get("current_bid") or 9999.0),
                ))
                _fb_pool = _fb_pool[:_MAX_WATCHLIST]
                _fallback_promoted = 0

                if _fb_pool:
                    _fb_watchlist_bucket: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
                    for _fb_r, _fb_v in _fb_pool:
                        print(
                            f"[WATCHLIST_APPEND_BYPASS] title={str((_fb_r or {}).get('title') or (_fb_r or {}).get('source_title') or '')[:140]} "
                            f"item={_ui_board_contract_item_key(_fb_r)[:32]} "
                            f"path=fallback/watchlist_append blocked=1"
                        )
                        if _ui_try_watchlist_admission(_fb_r, _fb_v, _target_bucket=_fb_watchlist_bucket):
                            _fallback_promoted += 1
                    _watchlist_bucket = _fb_watchlist_bucket
                    # Remove promoted rows from suppressed display to avoid duplicates
                    _fb_promoted_ids = {
                        str(_r.get("source_item_id") or _r.get("item_id") or id(_r))
                        for _r, _ in _watchlist_bucket
                    }
                    _suppressed_rows = [
                        (_r, _v) for _r, _v in _suppressed_rows
                        if str(_r.get("source_item_id") or _r.get("item_id") or id(_r))
                        not in _fb_promoted_ids
                    ]
                    _suppressed_ids = {
                        str(_r.get("source_item_id") or _r.get("item_id") or id(_r))
                        for _r, _ in _suppressed_rows
                    }

            print(f"[REVIEW_PROMOTION_SUMMARY] reason_counts={dict(sorted(_review_promotion_reason_counts.items()))}")
            print("[ES][FALLBACK] candidates={} promoted={} rejected_reasons={}".format(
                _fb_fallback_candidates_count, _fallback_promoted, _fallback_rejected
            ))

            _final_watchlist_visible: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
            _final_watchlist_suppressed: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
            for _wr, _wv in _watchlist_bucket:
                _watchlist_rescue_metrics["input"] += 1
                _watchlist_rescue_metrics["rescued_attempted"] += 1
                _rescue_contract = _ui_watchlist_rescue_contract(_wr)
                if not bool(_rescue_contract.get("allow")):
                    _watchlist_rescue_metrics["rescued_blocked"] += 1
                    _final_watchlist_suppressed.append((_wr, _wv))
                    continue
                _watchlist_rescue_metrics["rescued_allowed"] += 1
                if _ui_is_live_watchlist_row(_wr) or int((_wr or {}).get("final_surface_allowed", 1) or 0) > 0:
                    if _ui_try_watchlist_admission(_wr, _wv, _target_bucket=_final_watchlist_visible):
                        continue
                    _final_watchlist_suppressed.append((_wr, _wv))
                else:
                    if _ui_is_engine_visible_watchlist_candidate(_wr):
                        _log_watchlist_handoff_drop(_wr, dropped_by="final_watchlist_visible_gate")
                    _final_watchlist_suppressed.append((_wr, _wv))
            for _r, _v in _final_watchlist_suppressed:
                if _ui_is_live_watchlist_row(_r):
                    print(
                        f"[OTHER_LISTING_REDIRECT_BLOCK] title={str((_r or {}).get('title') or (_r or {}).get('source_title') or '')[:120]} "
                        f"reason=live_watchlist_row"
                    )
                    continue
                _rid = str(_r.get("source_item_id") or _r.get("item_id") or id(_r))
                if _rid not in _suppressed_ids:
                    _suppressed_rows = list(_suppressed_rows) + [(_r, _v)]
                    _suppressed_ids.add(_rid)
            _watchlist_bucket = _final_watchlist_visible
            _watch_ids = {_ui_live_watchlist_row_id(_r) for _r, _ in _watchlist_bucket}
            _live_added_ids: Set[str] = set()
            for _r, _v in _live_watchlist_pairs:
                _rid = _ui_live_watchlist_row_id(_r)
                if _rid in _watch_ids:
                    continue
                _watchlist_rescue_metrics["input"] += 1
                _watchlist_rescue_metrics["rescued_attempted"] += 1
                _rescue_contract = _ui_watchlist_rescue_contract(_r)
                if not bool(_rescue_contract.get("allow")):
                    _watchlist_rescue_metrics["rescued_blocked"] += 1
                    if _rid not in _suppressed_ids:
                        _suppressed_rows = list(_suppressed_rows) + [(_r, _v)]
                        _suppressed_ids.add(_rid)
                    continue
                _watchlist_rescue_metrics["rescued_allowed"] += 1
                _r["final_bucket"] = "watchlist"
                _r["execution_admission_bucket"] = "watchlist"
                _r["commercial_visibility"] = "watchlist"
                _r["visible_route"] = "watchlist_visible"
                _r["commercially_visible"] = True
                _r["board_visible"] = True
                _r["_render_live_watchlist"] = True
                _r["render_live_watchlist"] = True
                if _ui_try_watchlist_admission(_r, _es_get_decision_view_model(_r), _target_bucket=_watchlist_bucket):
                    _watch_ids.add(_rid)
                    _live_added_ids.add(_rid)
            if _live_added_ids:
                _suppressed_rows = [
                    (_r, _v) for _r, _v in _suppressed_rows
                    if _ui_live_watchlist_row_id(_r) not in _live_added_ids
                ]
                _suppressed_ids = {
                    _ui_live_watchlist_row_id(_r)
                    for _r, _ in _suppressed_rows
                }
                _dl_remainder = [
                    (_r, _v) for _r, _v in _dl_remainder
                    if _ui_live_watchlist_row_id(_r) not in _live_added_ids
                ]
                _watchlist_hidden = [
                    (_r, _v) for _r, _v in _watchlist_hidden
                    if _ui_live_watchlist_row_id(_r) not in _live_added_ids
                ]
                _commercial_hidden_pairs = [
                    (_r, _v) for _r, _v in _commercial_hidden_pairs
                    if _ui_live_watchlist_row_id(_r) not in _live_added_ids
                ]
                for _r, _v in _live_watchlist_pairs:
                    if _ui_live_watchlist_row_id(_r) not in _live_added_ids:
                        continue
                    print(
                        f"[LIVE_WATCHLIST_ASSERT] title={str((_r or {}).get('title') or (_r or {}).get('source_title') or '')[:120]} "
                        f"final_bucket={(_r or {}).get('final_bucket')} "
                        f"visibility={(_r or {}).get('commercial_visibility')} "
                        f"route={(_r or {}).get('visible_route') or (_r or {}).get('route')} "
                        f"board_visible={(_r or {}).get('board_visible')} "
                        f"commercially_visible={(_r or {}).get('commercially_visible')} "
                        f"render_live_watchlist={(_r or {}).get('_render_live_watchlist')}"
                    )

            _watchlist_rescued = 0
            if not _sniper_board and not _watchlist_bucket and not _suppressed_rows and not research_queue_rows:
                _rescue_sources = (
                    _live_watchlist_pairs,
                    _watchlist_candidates,
                    _watchlist_hidden,
                    _fallback_admissions,
                    _fallback_candidates,
                    _dl_remainder,
                    _commercial_hidden_pairs,
                    _suppressed_rows,
                )
                _rescue_candidates: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
                _rescue_seen: Set[str] = set()
                for _source_pairs in _rescue_sources:
                    for _r, _v in _source_pairs:
                        if not _ui_is_engine_visible_watchlist_candidate(_r):
                            continue
                        _rid = _ui_live_watchlist_row_id(_r)
                        if _rid in _rescue_seen:
                            continue
                        _rescue_seen.add(_rid)
                        _rescue_candidates.append((_r, _v if isinstance(_v, dict) else {}))
                _rescue_candidates.sort(key=lambda _rv: _ui_engine_visible_watchlist_priority(_rv[0]))
                _rescued_ids: Set[str] = set()
                for _r, _v in _rescue_candidates[:_MAX_WATCHLIST]:
                    _rid = _ui_live_watchlist_row_id(_r)
                    if _rid in _rescued_ids:
                        continue
                    _watchlist_rescue_metrics["input"] += 1
                    _watchlist_rescue_metrics["rescued_attempted"] += 1
                    _rescue_contract = _ui_watchlist_rescue_contract(_r)
                    if not bool(_rescue_contract.get("allow")):
                        _watchlist_rescue_metrics["rescued_blocked"] += 1
                        continue
                    _watchlist_rescue_metrics["rescued_allowed"] += 1
                    _r["final_bucket"] = "watchlist"
                    _r["execution_admission_bucket"] = "watchlist"
                    _r["commercial_visibility"] = "watchlist"
                    _r["visible_route"] = str(_r.get("visible_route") or "watchlist_visible")
                    _r["commercially_visible"] = True
                    _r["board_visible"] = True
                    _r["_render_live_watchlist"] = True
                    _r["render_live_watchlist"] = True
                    _rescue_view = dict(_v) if isinstance(_v, dict) else _es_get_decision_view_model(_r)
                    _rescue_view["execution_decision"] = str(_rescue_view.get("execution_decision") or "WATCH")
                    _rescue_view["execution_tier"] = str(_rescue_view.get("execution_tier") or "WATCH")
                    _rescue_view["board_bucket"] = str(_rescue_view.get("board_bucket") or "WATCH")
                    if _ui_try_watchlist_admission(_r, _rescue_view, _target_bucket=_watchlist_bucket):
                        _rescued_ids.add(_rid)
                        _watchlist_rescued += 1
                        print(
                            f"[WATCHLIST_RESCUE_ROUTE] title={str((_r or {}).get('title') or (_r or {}).get('source_title') or '')[:140]} "
                            f"item={_rid[:32]} reason=engine_visible_preserved surface=watchlist"
                        )
                if _rescued_ids:
                    _suppressed_rows = [
                        (_r, _v) for _r, _v in _suppressed_rows
                        if _ui_live_watchlist_row_id(_r) not in _rescued_ids
                    ]
                    _suppressed_ids = {
                        _ui_live_watchlist_row_id(_r)
                        for _r, _ in _suppressed_rows
                    }
                    _dl_remainder = [
                        (_r, _v) for _r, _v in _dl_remainder
                        if _ui_live_watchlist_row_id(_r) not in _rescued_ids
                    ]
                    _watchlist_hidden = [
                        (_r, _v) for _r, _v in _watchlist_hidden
                        if _ui_live_watchlist_row_id(_r) not in _rescued_ids
                    ]
                    _commercial_hidden_pairs = [
                        (_r, _v) for _r, _v in _commercial_hidden_pairs
                        if _ui_live_watchlist_row_id(_r) not in _rescued_ids
                    ]

            _final_surface_promoted_ids: Set[str] = set()
            _final_surface_seen_ids: Set[str] = {
                _ui_live_watchlist_row_id(_r)
                for _r, _ in (_sniper_board + _watchlist_bucket)
            }
            _final_surface_candidate_map: Dict[str, Tuple[Dict[str, Any], Dict[str, Any]]] = {}
            for _source_pairs in (
                _suppressed_rows,
                _watchlist_hidden,
                _commercial_hidden_pairs,
                _dl_remainder,
            ):
                for _r, _v in _source_pairs:
                    if not isinstance(_r, dict):
                        continue
                    _rid = _ui_live_watchlist_row_id(_r)
                    if _rid in _final_surface_seen_ids or _rid in _final_surface_candidate_map:
                        continue
                    if not (bool(_r.get("board_visible")) or bool(_r.get("canonical_board_preserved"))):
                        continue
                    _final_surface_candidate_map[_rid] = (
                        _r,
                        dict(_v) if isinstance(_v, dict) else _es_get_decision_view_model(_r),
                    )
            for _r in _deals:
                if not isinstance(_r, dict):
                    continue
                _rid = _ui_live_watchlist_row_id(_r)
                if _rid in _final_surface_seen_ids or _rid in _final_surface_candidate_map:
                    continue
                if not (bool(_r.get("board_visible")) or bool(_r.get("canonical_board_preserved"))):
                    continue
                _final_surface_candidate_map[_rid] = (_r, _es_get_decision_view_model(_r))
            for _rid, (_r, _v) in _final_surface_candidate_map.items():
                _route_contract = _ui_resolve_final_surface_route(_r)
                _route = str(_route_contract.get("route") or "blocked").strip().lower()
                if _route == "sniper":
                    _sniper_view = dict(_v) if isinstance(_v, dict) else _es_get_decision_view_model(_r)
                    _sniper_view["execution_decision"] = str(
                        _sniper_view.get("execution_decision")
                        or _r.get("execution_decision")
                        or "PREPARE"
                    )
                    _sniper_view["board_bucket"] = str(
                        _sniper_view.get("board_bucket")
                        or _r.get("board_bucket")
                        or "PREPARE"
                    )
                    _sniper_board.append((_r, _sniper_view))
                    _final_surface_seen_ids.add(_rid)
                    _final_surface_promoted_ids.add(_rid)
                    print(
                        f"[LIVE_BOARD_RENDER_INCLUDE] title={str((_r or {}).get('title') or (_r or {}).get('source_title') or '')[:140]} "
                        f"final_bucket={str((_r or {}).get('final_bucket') or (_r or {}).get('execution_admission_bucket') or '').strip().lower() or 'none'} "
                        f"visible=1"
                    )
                elif _route == "watchlist":
                    _watch_view = dict(_v) if isinstance(_v, dict) else _es_get_decision_view_model(_r)
                    _watch_view["execution_decision"] = str(_watch_view.get("execution_decision") or "WATCH")
                    _watch_view["execution_tier"] = str(_watch_view.get("execution_tier") or "WATCH")
                    _watch_view["board_bucket"] = str(_watch_view.get("board_bucket") or "WATCH")
                    if _ui_try_watchlist_admission(_r, _watch_view, _target_bucket=_watchlist_bucket):
                        _final_surface_seen_ids.add(_rid)
                        _final_surface_promoted_ids.add(_rid)
                        print(
                            f"[LIVE_BOARD_RENDER_INCLUDE] title={str((_r or {}).get('title') or (_r or {}).get('source_title') or '')[:140]} "
                            f"final_bucket={str((_r or {}).get('final_bucket') or (_r or {}).get('execution_admission_bucket') or '').strip().lower() or 'none'} "
                            f"visible=1"
                        )
                    else:
                        print(
                            f"[LIVE_BOARD_RENDER_EXCLUDE] title={str((_r or {}).get('title') or (_r or {}).get('source_title') or '')[:140]} "
                            f"reason=watchlist_admission_blocked"
                        )
                elif _route == "remainder":
                    if _rid not in _suppressed_ids:
                        _suppressed_rows = list(_suppressed_rows) + [(_r, _v)]
                        _suppressed_ids.add(_rid)
                    print(
                        f"[LIVE_BOARD_RENDER_EXCLUDE] title={str((_r or {}).get('title') or (_r or {}).get('source_title') or '')[:140]} "
                        f"reason=remainder_route"
                    )
                else:
                    _r["_route_blocked_hard"] = True
                    _r["route_blocked_hard"] = True
                    print(
                        f"[LIVE_BOARD_RENDER_EXCLUDE] title={str((_r or {}).get('title') or (_r or {}).get('source_title') or '')[:140]} "
                        f"reason={str(_route_contract.get('reason') or 'blocked').strip() or 'blocked'}"
                    )
            if _final_surface_promoted_ids:
                _suppressed_rows = [
                    (_r, _v) for _r, _v in _suppressed_rows
                    if _ui_live_watchlist_row_id(_r) not in _final_surface_promoted_ids
                ]
                _suppressed_ids = {
                    _ui_live_watchlist_row_id(_r)
                    for _r, _ in _suppressed_rows
                }
                _dl_remainder = [
                    (_r, _v) for _r, _v in _dl_remainder
                    if _ui_live_watchlist_row_id(_r) not in _final_surface_promoted_ids
                ]
                _watchlist_hidden = [
                    (_r, _v) for _r, _v in _watchlist_hidden
                    if _ui_live_watchlist_row_id(_r) not in _final_surface_promoted_ids
                ]
                _commercial_hidden_pairs = [
                    (_r, _v) for _r, _v in _commercial_hidden_pairs
                    if _ui_live_watchlist_row_id(_r) not in _final_surface_promoted_ids
                ]

            display_rows = (_sniper_board + _watchlist_bucket) if _sniper_board else _watchlist_bucket
            _guarded_display_rows = []
            for _dr, _dv in display_rows:
                _guarded_row = _ui_apply_true_mv_contract_guard(_dr, trace_tag="FINAL_BOARD_TRACE")
                _guarded_view = _es_get_decision_view_model(_guarded_row)
                _guarded_display_rows.append((_guarded_row, _guarded_view))
            display_rows = _guarded_display_rows

            # ── FINAL BOARD DEDUPE ─────────────────────────────────────────
            # The same listing can reach display_rows twice when a row qualifies
            # both for the sniper bucket and the watchlist pool, or when the
            # PREPARE merge mirrors a row into the title pool that also lives
            # in the auction pool. Dedupe by item_id → normalized URL →
            # normalized title+price, keeping the row with the highest
            # final_rank_score. Pure dedupe — no ranking, valuation, comp,
            # fetch, engine, or UI styling change.
            def _ui_dedupe_item_id_key(_r: Dict[str, Any]) -> str:
                return str(
                    (_r or {}).get("source_item_id")
                    or (_r or {}).get("item_id")
                    or (_r or {}).get("itemId")
                    or ""
                ).strip().lower()

            def _ui_dedupe_url_key(_r: Dict[str, Any]) -> str:
                _url = str(
                    (_r or {}).get("listing_url")
                    or (_r or {}).get("itemWebUrl")
                    or (_r or {}).get("url")
                    or (_r or {}).get("item_url")
                    or ""
                ).strip().lower()
                if not _url:
                    return ""
                # Strip query params and trailing slashes for stable normalization.
                _url = _url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
                return _url

            def _ui_dedupe_title_price_key(_r: Dict[str, Any]) -> str:
                _title = str((_r or {}).get("title") or (_r or {}).get("source_title") or "").strip().lower()
                _title = " ".join(_title.split())
                if not _title:
                    return ""
                _price_raw = (
                    (_r or {}).get("current_price")
                    if (_r or {}).get("current_price") is not None
                    else ((_r or {}).get("current_bid") if (_r or {}).get("current_bid") is not None else (_r or {}).get("price"))
                )
                try:
                    _price_norm = f"{float(_price_raw):.2f}" if _price_raw is not None else "0.00"
                except Exception:
                    _price_norm = "0.00"
                return f"{_title}|{_price_norm}"

            def _ui_dedupe_score(_r: Dict[str, Any], _v: Dict[str, Any]) -> float:
                try:
                    return float((_v or {}).get("final_rank_score") or (_r or {}).get("final_rank_score") or 0.0)
                except Exception:
                    return 0.0

            _dedupe_before = len(display_rows)
            _dedupe_seen_item: Dict[str, int] = {}    # item_id → idx in keep list
            _dedupe_seen_url: Dict[str, int] = {}     # url     → idx in keep list
            _dedupe_seen_title: Dict[str, int] = {}   # title|price → idx in keep list
            _dedupe_kept: List = []
            _dedupe_removed_count = 0
            for _row_dd, _view_dd in display_rows:
                _k_item = _ui_dedupe_item_id_key(_row_dd)
                _k_url = _ui_dedupe_url_key(_row_dd)
                _k_title = _ui_dedupe_title_price_key(_row_dd)
                _existing_idx: Optional[int] = None
                _matched_key_kind = ""
                if _k_item and _k_item in _dedupe_seen_item:
                    _existing_idx = _dedupe_seen_item[_k_item]
                    _matched_key_kind = "item_id"
                elif _k_url and _k_url in _dedupe_seen_url:
                    _existing_idx = _dedupe_seen_url[_k_url]
                    _matched_key_kind = "url"
                elif _k_title and _k_title in _dedupe_seen_title:
                    _existing_idx = _dedupe_seen_title[_k_title]
                    _matched_key_kind = "title_price"
                if _existing_idx is None:
                    _dedupe_kept.append((_row_dd, _view_dd))
                    _new_idx = len(_dedupe_kept) - 1
                    if _k_item:
                        _dedupe_seen_item[_k_item] = _new_idx
                    if _k_url:
                        _dedupe_seen_url[_k_url] = _new_idx
                    if _k_title:
                        _dedupe_seen_title[_k_title] = _new_idx
                    continue
                # Collision — keep the row with the higher final_rank_score.
                _dedupe_removed_count += 1
                _existing_row, _existing_view = _dedupe_kept[_existing_idx]
                _existing_score = _ui_dedupe_score(_existing_row, _existing_view)
                _new_score = _ui_dedupe_score(_row_dd, _view_dd)
                _existing_title_log = str((_existing_row or {}).get("title") or "")[:120]
                _new_title_log = str((_row_dd or {}).get("title") or "")[:120]
                if _new_score > _existing_score:
                    _dedupe_kept[_existing_idx] = (_row_dd, _view_dd)
                    # Refresh keys so they all point at the new row.
                    if _k_item:
                        _dedupe_seen_item[_k_item] = _existing_idx
                    if _k_url:
                        _dedupe_seen_url[_k_url] = _existing_idx
                    if _k_title:
                        _dedupe_seen_title[_k_title] = _existing_idx
                    print(
                        f"[BOARD_DEDUPE_COLLISION] kept_new title={_new_title_log} "
                        f"matched_key={_matched_key_kind} new_score={_new_score:.2f} "
                        f"replaced_score={_existing_score:.2f}"
                    )
                else:
                    print(
                        f"[BOARD_DEDUPE_COLLISION] kept_existing title={_existing_title_log} "
                        f"matched_key={_matched_key_kind} kept_score={_existing_score:.2f} "
                        f"dropped_score={_new_score:.2f}"
                    )
            display_rows = _dedupe_kept
            print(
                f"[BOARD_DEDUPE] before={_dedupe_before} "
                f"after={len(display_rows)} "
                f"removed={_dedupe_removed_count} "
                f"reason=item_id_or_title_price"
            )
            # ────────────────────────────────────────────────────────────────

            board_rows_displayed = list(display_rows)
            _ui_board_debug("post_ui_filters", [_r for _r, _ in board_rows_displayed])
            print(
                f"[WATCHLIST_FINAL_RENDER] sniper={len(_sniper_board)} "
                f"watchlist={len(_watchlist_bucket)} rescued={_watchlist_rescued} "
                f"displayed={len(display_rows)}"
            )
            print(
                f"[WATCHLIST_RESCUE_FINAL] input={_watchlist_rescue_metrics['input']} "
                f"rescued_attempted={_watchlist_rescue_metrics['rescued_attempted']} "
                f"rescued_allowed={_watchlist_rescue_metrics['rescued_allowed']} "
                f"rescued_blocked={_watchlist_rescue_metrics['rescued_blocked']} "
                f"displayed={len(display_rows)}"
            )
            print(
                f"[WATCHLIST_RESCUE_SCOPE_FINAL] input={_watchlist_rescue_metrics['input']} "
                f"rescued_attempted={_watchlist_rescue_metrics['rescued_attempted']} "
                f"rescued_allowed={_watchlist_rescue_metrics['rescued_allowed']} "
                f"rescued_blocked={_watchlist_rescue_metrics['rescued_blocked']} "
                f"displayed={len(display_rows)}"
            )
            print(
                f"[WATCHLIST_APPEND_FINAL] attempted={_watchlist_append_metrics['attempted']} "
                f"allowed={_watchlist_append_metrics['allowed']} "
                f"blocked={_watchlist_append_metrics['blocked']} "
                f"displayed={len(_watchlist_bucket)}"
            )
            print(
                f"[PREMIUM_SECONDARY_FINAL] input={_premium_secondary_metrics['input']} "
                f"allowed={_premium_secondary_metrics['allowed']} "
                f"blocked={_premium_secondary_metrics['blocked']} "
                f"displayed={len(_watchlist_bucket)}"
            )
            print(
                f"[LIVE_WATCHLIST_COUNTS] sniper={len(_sniper_board)} "
                f"watchlist={len(_watchlist_bucket)} "
                f"other={len(_suppressed_rows)} hidden={len(_recovery_rows_hidden)}"
            )
            print(f"[BOARD_HANDOFF] sniper={len(_sniper_board)} watch={len(_watchlist_bucket)} display={len(display_rows)}")
            _prepare_count = sum(1 for _r, _ in display_rows if str(_r.get("board_bucket") or _r.get("_board_bucket") or "").strip().upper() == "PREPARE")
            _monitor_count = sum(1 for _r, _ in display_rows if str(_r.get("board_bucket") or _r.get("_board_bucket") or "").strip().upper() == "MONITOR")
            _watch_count = sum(1 for _r, _ in display_rows if str(_r.get("board_bucket") or _r.get("_board_bucket") or "").strip().upper() == "WATCH")
            print(
                f"[BOARD_EXPANSION_RESULT] total_rows={len(display_rows)} "
                f"sniper={len(_sniper_board)} watch={len(_watchlist_bucket)} "
                f"prepare={_prepare_count} monitor={_monitor_count} watch={_watch_count} "
                f"fallback_candidates={_fb_fallback_candidates_count} backfill={_fallback_promoted}"
            )
            try:
                if hasattr(_ese, "record_board_heat_result"):
                    _ese.record_board_heat_result(
                        len(display_rows),
                        source="streamlit_board",
                        prepare=_prepare_count,
                        monitor=_monitor_count,
                        watch=_watch_count,
                    )
            except Exception:
                pass

            _n_true_actionable = len(_actionable_bucket)
            _n_sniper_candidate = len(_sniper_candidates_on_board)
            _n_watchlist_hero = len(_watchlist_heroes_on_board)
            _n_sniper_board = len(_sniper_board)
            _hero_dropped = sum(
                1
                for _r, _v in (_watchlist_hidden + _dl_remainder)
                if bool(_v.get("hero_board_eligible") or _r.get("hero_board_eligible"))
            )
            _watchlist_rerouted = len(_sniper_candidates_overflow) + len(_watchlist_hero_overflow)

            print("[PROMOTION] A={} B={} WATCH={}".format(
                len(_tier_a_bucket), len(_tier_b_bucket), len(_watchlist_bucket)
            ))
            print("[SNIPER_BOARD] count={} tier_a={} tier_b={} heroes={}".format(
                len(_sniper_board),
                len(_tier_a_on_board), len(_tier_b_on_board),
                _n_true_actionable + _n_sniper_candidate + _n_watchlist_hero,
            ))
            print(
                "[DECISION_LAYER] input_rows={} strict_candidates={} fallback_candidates={} "
                "actionable={} sniper_candidate={} fallback_hero={} "
                "final_sniper={} final_watchlist={} dropped={}".format(
                    _dl_input,
                    _fb_strict_board + len(_watchlist_bucket if not _fallback_promoted else []),
                    _fb_fallback_candidates_count,
                    _n_true_actionable, _n_sniper_candidate, _n_watchlist_hero,
                    _n_sniper_board, len(_watchlist_bucket),
                    len(_dl_remainder),
                )
            )
            print(
                f"[SNIPER_FILTER] hero_kept={_n_sniper_board} hero_dropped={_hero_dropped} "
                f"watchlist_rerouted={_watchlist_rerouted}"
            )
            print(
                f"[WATCHLIST] candidates={len(_watchlist_candidates)} "
                f"kept={len(_watchlist_bucket)} "
                f"hidden={len(_watchlist_hidden)}"
            )
            print(
                f"[COMMERCIAL_VISIBLE] sniper={_n_sniper_board} watchlist={len(_watchlist_bucket)} "
                f"hidden={len(_commercial_hidden_pairs)}"
            )
            print(
                f"[BOARD_MIX] sniper_board={_n_sniper_board} "
                f"watchlist={len(_watchlist_bucket)} "
                f"displayed={len(board_rows_displayed)}"
            )
            print(f"[ES][BADGE_RENDER] mode=sniper_board rows={len(board_rows_displayed)}")
            print(
                f"[ES][BOARD_STATE] all={_dl_input} displayed={len(board_rows_displayed)} "
                f"dropped={len(_dl_remainder)}"
            )
            print(
                f"[LIVE_PRESERVE_SUMMARY] "
                f"preserved_rows={_live_preserve_routed_sniper + _live_preserve_routed_watch} "
                f"preserved_watch={_live_preserve_routed_watch} "
                f"preserved_sniper={_live_preserve_routed_sniper} "
                f"bucket_fallbacks_blocked={_live_preserve_bucket_fallbacks_blocked} "
                f"downgrades_blocked={_live_preserve_downgrades_blocked} "
                f"displayed_after_preserve={len(board_rows_displayed)}"
            )
            # ── BOARD_REPLACEMENT_POOL — alternative-row availability snapshot ──
            try:
                _brp_pass_in_actionable = sum(
                    1 for _r_dr, _v_dr in (board_rows_displayed or [])
                    if str((_r_dr or {}).get("execution_final_decision") or (_v_dr or {}).get("final_execution_decision") or "").strip().upper() in {"PASS_OVERPRICED", "PASS"}
                )
                _brp_recurring_in_actionable = sum(
                    1 for _r_dr, _v_dr in (board_rows_displayed or [])
                    if str((_r_dr or {}).get("source_item_id") or (_r_dr or {}).get("item_id") or "").strip().lower() in _lrs_seen_iid_set
                )
                _brp_dl_remainder_size = len(_dl_remainder or [])
                _brp_commercial_hidden_size = len(_commercial_hidden_pairs or []) if "_commercial_hidden_pairs" in dir() else 0
                _brp_watchlist_hidden_size = len(_watchlist_hidden or []) if "_watchlist_hidden" in dir() else 0
                _brp_overflow_pool = _brp_dl_remainder_size + _brp_commercial_hidden_size + _brp_watchlist_hidden_size
                # Replacement readiness: are there fresh rows in the remainder that
                # could replace recurring PASS_OVERPRICED on the actionable board?
                _brp_fresh_alternatives = 0
                for _r_dr, _v_dr in list(_dl_remainder or [])[:30]:
                    _alt_iid = str((_r_dr or {}).get("source_item_id") or (_r_dr or {}).get("item_id") or "").strip().lower()
                    _alt_decision = str((_r_dr or {}).get("execution_final_decision") or (_v_dr or {}).get("final_execution_decision") or "").strip().upper()
                    if _alt_iid and _alt_iid not in _lrs_seen_iid_set and _alt_decision not in {"PASS_OVERPRICED", "PASS"}:
                        _brp_fresh_alternatives += 1
                print(
                    f"[BOARD_REPLACEMENT_POOL] "
                    f"actionable_total={len(board_rows_displayed or [])} "
                    f"actionable_pass_overpriced={_brp_pass_in_actionable} "
                    f"actionable_recurring_from_prior_scans={_brp_recurring_in_actionable} "
                    f"dl_remainder_pool={_brp_dl_remainder_size} "
                    f"commercial_hidden_pool={_brp_commercial_hidden_size} "
                    f"watchlist_hidden_pool={_brp_watchlist_hidden_size} "
                    f"overflow_total={_brp_overflow_pool} "
                    f"fresh_alternatives_in_remainder={_brp_fresh_alternatives} "
                    f"loop_seen_recurring={_seen_item_recurring} "
                    f"loop_pass_overpriced={_pass_overpriced_seen}"
                )
            except Exception as _brp_exc:
                print(f"[BOARD_REPLACEMENT_POOL] error_type={type(_brp_exc).__name__} msg={str(_brp_exc)[:120]}")
            # ────────────────────────────────────────────────────────────────

            # ── CANDIDATE_FUNNEL_SUMMARY — fetch → board flow per render ────
            # Pure observability — no logic changes, no row mutation.
            try:
                _cfs_es_rows = list(st.session_state.get("es_rows") or [])
                _cfs_meta = dict(st.session_state.get("es_meta") or {})
                _cfs_fetched = int(_cfs_meta.get("raw_auction_count") or _cfs_meta.get("auction_count") or 0)
                _cfs_normalized = len(_cfs_es_rows)
                _cfs_valuation_rows = sum(
                    1 for _r in _cfs_es_rows
                    if (_safe_float((_r or {}).get("mv_value")) or 0.0) > 0
                    or (_safe_float((_r or {}).get("market_value")) or 0.0) > 0
                    or (_safe_float((_r or {}).get("review_estimate")) or 0.0) > 0
                    or (_safe_float((_r or {}).get("true_mv")) or 0.0) > 0
                )
                _cfs_valued_rows = sum(
                    1 for _r in _cfs_es_rows
                    if ((_safe_float((_r or {}).get("mv_value")) or 0.0) > 0 or (_safe_float((_r or {}).get("true_mv")) or 0.0) > 0)
                    and (_safe_float((_r or {}).get("target_bid_price")) or _safe_float((_r or {}).get("target_bid")) or 0.0) > 0
                )
                _cfs_action_ready = 0
                _cfs_watch_rows = 0
                _cfs_pass_rows = 0
                _cfs_suppressed_rows = 0
                _cfs_research_rows = 0
                _cfs_rare_exact_rows = 0
                for _r in _cfs_es_rows:
                    _cfs_decision = str((_r or {}).get("execution_final_decision") or (_r or {}).get("final_execution_decision") or "").strip().upper()
                    if _cfs_decision == "SNIPE_NOW":
                        _cfs_action_ready += 1
                    elif _cfs_decision == "WATCH":
                        _cfs_watch_rows += 1
                    elif _cfs_decision in {"PASS_OVERPRICED", "PASS"}:
                        _cfs_pass_rows += 1
                    elif _cfs_decision in {"RESEARCH_SNIPE", "RESEARCH_WATCH", "RESEARCH_PASS"}:
                        _cfs_research_rows += 1
                    elif bool((_r or {}).get("_rare_exact_override")):
                        _cfs_rare_exact_rows += 1
                    else:
                        _cfs_suppressed_rows += 1
                _cfs_replacement_pool = (
                    len(_dl_remainder or [])
                    + (len(_commercial_hidden_pairs or []) if "_commercial_hidden_pairs" in dir() else 0)
                    + (len(_watchlist_hidden or []) if "_watchlist_hidden" in dir() else 0)
                )
                print(
                    f"[CANDIDATE_FUNNEL_SUMMARY] "
                    f"fetched={_cfs_fetched} "
                    f"normalized={_cfs_normalized} "
                    f"valuation_rows={_cfs_valuation_rows} "
                    f"valued_rows={_cfs_valued_rows} "
                    f"action_ready={_cfs_action_ready} "
                    f"watch_rows={_cfs_watch_rows} "
                    f"pass_rows={_cfs_pass_rows} "
                    f"research_rows={_cfs_research_rows} "
                    f"rare_exact_rows={_cfs_rare_exact_rows} "
                    f"suppressed_rows={_cfs_suppressed_rows} "
                    f"display_rows={len(board_rows_displayed or [])} "
                    f"replacement_pool={_cfs_replacement_pool}"
                )
            except Exception as _cfs_exc:
                print(f"[CANDIDATE_FUNNEL_SUMMARY] error_type={type(_cfs_exc).__name__} msg={str(_cfs_exc)[:120]}")
            # ────────────────────────────────────────────────────────────────

            # ── SNIPE_BUCKET_OUTCOME — final-action gate audit ──────────────
            # Pure observability. For each row whose remaining_seconds is in
            # the 0–3h SNIPE window, emit the final decision and a proximate
            # reason for not reaching SNIPE_NOW. Tells us exactly which gate
            # is killing action_ready when TIME_BUCKET_SPLIT shows snipe>=1.
            # If the snipe row died upstream of display (e.g. at valuation),
            # it won't appear here — the absence itself is informative when
            # cross-referenced with TIME_BUCKET_SPLIT.snipe and the engine
            # death funnel counts.
            try:
                _SNIPE_WINDOW_SECONDS = 3.0 * 3600.0
                _sbo_seen_count = 0
                _sbo_action_ready_count = 0
                for _sbo_row in _cfs_es_rows:
                    _sbo_rem = _safe_float((_sbo_row or {}).get("remaining_seconds"))
                    if _sbo_rem is None:
                        _sbo_rem = _safe_float((_sbo_row or {}).get("seconds_remaining"))
                    if _sbo_rem is None or _sbo_rem <= 0 or _sbo_rem > _SNIPE_WINDOW_SECONDS:
                        continue
                    _sbo_seen_count += 1
                    _sbo_decision = str(
                        (_sbo_row or {}).get("execution_final_decision")
                        or (_sbo_row or {}).get("final_execution_decision")
                        or ""
                    ).strip().upper()
                    _sbo_title = str(
                        (_sbo_row or {}).get("title")
                        or (_sbo_row or {}).get("source_title")
                        or ""
                    )[:140]
                    _sbo_current = _safe_float((_sbo_row or {}).get("current_price"))
                    _sbo_target = (
                        _safe_float((_sbo_row or {}).get("target_bid_price"))
                        or _safe_float((_sbo_row or {}).get("target_bid"))
                    )
                    _sbo_mv = (
                        _safe_float((_sbo_row or {}).get("true_mv"))
                        or _safe_float((_sbo_row or {}).get("market_value"))
                        or _safe_float((_sbo_row or {}).get("mv_value"))
                    )
                    _sbo_risk = bool(
                        (_sbo_row or {}).get("_presentation_risk_block")
                        or (_sbo_row or {}).get("presentation_risk_block")
                    )
                    _sbo_anchor = bool(
                        (_sbo_row or {}).get("_anchor_only_review")
                        or (_sbo_row or {}).get("anchor_only_review")
                    )
                    _sbo_research = bool(
                        (_sbo_row or {}).get("_research_only_price_check")
                        or (_sbo_row or {}).get("research_only_price_check")
                    )
                    # Proximate reason ranking: most actionable first.
                    if _sbo_decision == "SNIPE_NOW":
                        _sbo_reason = "reached_snipe_now"
                        _sbo_action_ready_count += 1
                    elif _sbo_risk:
                        _sbo_reason = "risk_block_thin_comps"
                    elif _sbo_anchor:
                        _sbo_reason = "anchor_only_review"
                    elif _sbo_research:
                        _sbo_reason = "research_only_price_check"
                    elif (
                        _sbo_target is not None
                        and _sbo_current is not None
                        and _sbo_target > 0
                        and _sbo_current > _sbo_target * 1.05
                    ):
                        _sbo_reason = "current_above_target_plus_5pct"
                    elif _sbo_target is None or (_sbo_target or 0) <= 0:
                        _sbo_reason = "no_target_bid"
                    elif _sbo_mv is None or (_sbo_mv or 0) <= 0:
                        _sbo_reason = "no_mv"
                    else:
                        _sbo_reason = f"final_decision={_sbo_decision or 'unknown'}"
                    print(
                        f"[SNIPE_BUCKET_OUTCOME] "
                        f"title={_sbo_title} "
                        f"remaining_seconds={round(float(_sbo_rem), 0)} "
                        f"decision={_sbo_decision or 'NONE'} "
                        f"current={_sbo_current} target={_sbo_target} mv={_sbo_mv} "
                        f"risk_block={1 if _sbo_risk else 0} "
                        f"anchor_only={1 if _sbo_anchor else 0} "
                        f"research_only={1 if _sbo_research else 0} "
                        f"reason={_sbo_reason}"
                    )
                print(
                    f"[SNIPE_BUCKET_OUTCOME_SUMMARY] "
                    f"snipe_window_rows_in_display={_sbo_seen_count} "
                    f"reached_snipe_now={_sbo_action_ready_count}"
                )
            except Exception as _sbo_exc:
                print(f"[SNIPE_BUCKET_OUTCOME] error_type={type(_sbo_exc).__name__} msg={str(_sbo_exc)[:120]}")
            # ────────────────────────────────────────────────────────────────

            # ── BOARD_DROP_REASON_SUMMARY — aggregated drop reasons ────────
            try:
                _bdr_reason_counts: Dict[str, int] = {}
                # _dl_remainder — rows that fell through every gate
                for _r_d, _v_d in list(_dl_remainder or []):
                    _bdr_decision = str((_r_d or {}).get("execution_final_decision") or (_v_d or {}).get("final_execution_decision") or "").strip().upper()
                    _bdr_reason = str((_r_d or {}).get("final_action_reason") or "").strip() or "no_reason"
                    _bdr_action_label = str((_v_d or {}).get("action_label") or (_r_d or {}).get("action_label") or "").strip().upper()
                    _bdr_key = f"dl_remainder:{_bdr_decision or _bdr_action_label or 'unknown'}"
                    _bdr_reason_counts[_bdr_key] = _bdr_reason_counts.get(_bdr_key, 0) + 1
                # commercial_hidden — vetoed by commercial visibility
                if "_commercial_hidden_pairs" in dir():
                    for _r_d, _v_d in list(_commercial_hidden_pairs or []):
                        _bdr_visibility_reason = str((_r_d or {}).get("commercial_visibility_reason") or "").strip() or "commercial_visibility_gate"
                        _bdr_key = f"commercial_hidden:{_bdr_visibility_reason}"
                        _bdr_reason_counts[_bdr_key] = _bdr_reason_counts.get(_bdr_key, 0) + 1
                # watchlist_hidden — admission contract rejected
                if "_watchlist_hidden" in dir():
                    for _r_d, _v_d in list(_watchlist_hidden or []):
                        _bdr_rescue_reason = str((_r_d or {}).get("_watchlist_rescue_block_reason") or (_r_d or {}).get("watchlist_block_reason") or "").strip() or "watchlist_rescue_blocked"
                        _bdr_key = f"watchlist_hidden:{_bdr_rescue_reason}"
                        _bdr_reason_counts[_bdr_key] = _bdr_reason_counts.get(_bdr_key, 0) + 1
                # Suppressed rows from earlier in the pipeline
                if "_suppressed_rows" in dir():
                    for _r_d, _v_d in list(_suppressed_rows or []):
                        _bdr_suppress_reason = str((_v_d or {}).get("monitor_reason") or (_r_d or {}).get("blocked_reason") or "").strip() or "suppression_pipeline"
                        _bdr_key = f"suppressed:{_bdr_suppress_reason}"
                        _bdr_reason_counts[_bdr_key] = _bdr_reason_counts.get(_bdr_key, 0) + 1
                print(f"[BOARD_DROP_REASON_SUMMARY] reason_counts={dict(sorted(_bdr_reason_counts.items(), key=lambda x: -x[1])[:20])}")
            except Exception as _bdr_exc:
                print(f"[BOARD_DROP_REASON_SUMMARY] error_type={type(_bdr_exc).__name__} msg={str(_bdr_exc)[:120]}")
            # ────────────────────────────────────────────────────────────────

            # ── VALUED_ROW_TRACE — per-valued-row visibility & drop trace ──
            try:
                _vrt_actionable_iids = {
                    str((_r_a or {}).get("source_item_id") or (_r_a or {}).get("item_id") or "").strip().lower()
                    for _r_a, _ in (board_rows_displayed or [])
                }
                _vrt_dl_remainder_iids = {
                    str((_r_d or {}).get("source_item_id") or (_r_d or {}).get("item_id") or "").strip().lower()
                    for _r_d, _ in (_dl_remainder or [])
                }
                _vrt_commercial_iids = (
                    {str((_r_d or {}).get("source_item_id") or (_r_d or {}).get("item_id") or "").strip().lower()
                     for _r_d, _ in (_commercial_hidden_pairs or [])}
                    if "_commercial_hidden_pairs" in dir() else set()
                )
                _vrt_watchlist_hidden_iids = (
                    {str((_r_d or {}).get("source_item_id") or (_r_d or {}).get("item_id") or "").strip().lower()
                     for _r_d, _ in (_watchlist_hidden or [])}
                    if "_watchlist_hidden" in dir() else set()
                )
                _vrt_logged = 0
                for _vrt_row in (st.session_state.get("es_rows") or []):
                    if _vrt_logged >= 30:
                        break
                    _vrt_iid = str((_vrt_row or {}).get("source_item_id") or (_vrt_row or {}).get("item_id") or "").strip().lower()
                    _vrt_cp = _ui_authoritative_current_price(_vrt_row) if isinstance(_vrt_row, dict) else None
                    _vrt_tb = (
                        _safe_float((_vrt_row or {}).get("target_bid_price"))
                        or _safe_float((_vrt_row or {}).get("target_bid"))
                        or _safe_float((_vrt_row or {}).get("bid_ceiling_value"))
                    )
                    # Only trace valued rows — has cp and (mv or review or target_bid)
                    _vrt_has_value = bool(
                        (_safe_float((_vrt_row or {}).get("mv_value")) or 0.0) > 0
                        or (_safe_float((_vrt_row or {}).get("true_mv")) or 0.0) > 0
                        or (_safe_float((_vrt_row or {}).get("review_estimate")) or 0.0) > 0
                        or (_vrt_tb is not None and _vrt_tb > 0)
                    )
                    if not _vrt_has_value:
                        continue
                    _vrt_decision = str((_vrt_row or {}).get("execution_final_decision") or (_vrt_row or {}).get("final_execution_decision") or "").strip().upper() or "unknown"
                    if _vrt_iid and _vrt_iid in _vrt_actionable_iids:
                        _vrt_bucket = "actionable"
                        _vrt_visible = 1
                        _vrt_drop_reason = "none"
                    elif _vrt_iid and _vrt_iid in _vrt_dl_remainder_iids:
                        _vrt_bucket = "dl_remainder"
                        _vrt_visible = 0
                        _vrt_drop_reason = str((_vrt_row or {}).get("final_action_reason") or "fell_through_decision_gates")
                    elif _vrt_iid and _vrt_iid in _vrt_commercial_iids:
                        _vrt_bucket = "commercial_hidden"
                        _vrt_visible = 0
                        _vrt_drop_reason = "commercial_visibility_gate"
                    elif _vrt_iid and _vrt_iid in _vrt_watchlist_hidden_iids:
                        _vrt_bucket = "watchlist_hidden"
                        _vrt_visible = 0
                        _vrt_drop_reason = "watchlist_rescue_blocked"
                    else:
                        _vrt_bucket = "absent_from_render"
                        _vrt_visible = 0
                        _vrt_drop_reason = "row_in_es_rows_but_not_in_view_models"
                    print(
                        f"[VALUED_ROW_TRACE] "
                        f"title={str((_vrt_row or {}).get('title') or '')[:160]} "
                        f"current_price={(round(float(_vrt_cp), 2) if _vrt_cp is not None else 'na')} "
                        f"target_bid={(round(float(_vrt_tb), 2) if _vrt_tb is not None else 'na')} "
                        f"final_decision={_vrt_decision} "
                        f"bucket={_vrt_bucket} "
                        f"visible={_vrt_visible} "
                        f"drop_reason={_vrt_drop_reason}"
                    )
                    _vrt_logged += 1
            except Exception as _vrt_exc:
                print(f"[VALUED_ROW_TRACE] error_type={type(_vrt_exc).__name__} msg={str(_vrt_exc)[:120]}")
            # ────────────────────────────────────────────────────────────────
            _visible_labels = sorted({str(_v.get("execution_decision") or "SKIP") for _, _v in board_rows_displayed})
            print("[ES][BOARD_RENDER] sniper={} watchlist={} fallback_active={} total={}".format(
                _n_sniper_board, len(_watchlist_bucket),
                int(_fallback_promoted > 0),
                _n_sniper_board + len(_watchlist_bucket),
            ))
            print("[UI][BOARD_RENDER] rows={} sniper={} watchlist={}".format(
                _n_sniper_board + len(_watchlist_bucket), _n_sniper_board, len(_watchlist_bucket)
            ))
            print(f"[AURA] hero={_n_sniper_board} watchlist={len(_watchlist_bucket)} hidden={len(_suppressed_rows)}")
            print(f"[AURA] actionable={_n_true_actionable} sniper_candidate={_n_sniper_candidate} watchlist_hero={_n_watchlist_hero} watchlist={len(_watchlist_bucket)}")
            print(f"[AURA] visible_labels={_visible_labels}")
            _tb_conf_board = [str(_r.get("target_bid_confidence") or "NONE") for _r, _ in _sniper_board]
            _tb_hero_ready = sum(1 for _c in _tb_conf_board if _c in {"HIGH", "MEDIUM"})
            _tb_hero_review = sum(1 for _c in _tb_conf_board if _c == "REVIEW")
            _tb_hero_none = sum(1 for _c in _tb_conf_board if _c == "NONE")
            print("[TARGET_BID] hero_ready={} hero_review={} hero_none={}".format(
                _tb_hero_ready, _tb_hero_review, _tb_hero_none
            ))

            # ─── Board message ──────────────────────────────────────────────────────
            _n_watch = len(_watchlist_bucket)
            if _n_sniper_board > 0 and _n_watch > 0:
                _board_msg = (
                    f"{_n_sniper_board} sniper board card{'s' if _n_sniper_board != 1 else ''} · "
                    f"{_n_watch} watchlist"
                )
            elif _n_sniper_board > 0:
                _board_msg = f"{_n_sniper_board} sniper board card{'s' if _n_sniper_board != 1 else ''}"
            elif _n_watch > 0:
                _board_msg = f"No immediate snipes · {_n_watch} live watchlist card{'s' if _n_watch != 1 else ''}"
            else:
                _board_msg = "No cards cleared threshold"

            # ─── Render: SNIPER BOARD ─────────────────────────────────────────────
            if _sniper_board:
                # Header accent: red if true actionable present, amber for candidate-only board
                _hdr_accent = "#dc2626" if _n_true_actionable > 0 else "#b45309"
                _hdr_icon = "🔴" if _n_true_actionable > 0 else "🎯"
                _hdr_subcopy = (
                    f"{_n_true_actionable} actionable · {_n_sniper_candidate} sniper candidate{'s' if _n_sniper_candidate != 1 else ''}"
                    if _n_true_actionable > 0 and _n_sniper_candidate > 0
                    else (f"{_n_true_actionable} ready to act" if _n_true_actionable > 0
                          else (f"{_n_sniper_candidate} premium candidate{'s' if _n_sniper_candidate != 1 else ''}" if _n_sniper_candidate > 0
                                else f"{_n_watchlist_hero} fallback hero{'es' if _n_watchlist_hero != 1 else ''}"))
                )
                st.markdown(
                    f"<div style='margin:1rem 0 0.15rem 0;padding:0.55rem 1rem 0.45rem 1rem;"
                    f"background:#0a0f1a;border-left:4px solid {_hdr_accent};border-radius:6px;'>"
                    f"<div style='display:flex;align-items:center;justify-content:space-between;'>"
                    f"<span style='font-weight:800;color:#f1f5f9;font-size:0.95rem;letter-spacing:0.04em'>"
                    f"{_hdr_icon} SNIPER BOARD</span>"
                    f"<span style='color:#888888;font-size:0.76rem'>{_hdr_subcopy}</span>"
                    f"</div>"
                    f"<div style='color:#888888;font-size:0.72rem;margin-top:0.18rem'>"
                    f"Top live looks ranked by bidability, commercial strength, and urgency</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                _rendered_count = 0
                for _idx, (_row, _view) in enumerate(_sniper_board):
                    _render_es_result_card(_row, _view, _idx, _is_hero=(_idx == 0))
                    _rendered_count += 1
                print(
                    f"[ES][BOARD_LOOP] sniper_board={_n_sniper_board} "
                    f"rendered={_rendered_count} true_actionable={_n_true_actionable} "
                    f"candidates={_n_sniper_candidate}"
                )

            # ─── Promote UNDER_MV rows to primary section ─────────────────────
            # UNDER_MV rows are real deals (current price below market value)
            # — surface them between the sniper board and the watchlist block,
            # NOT buried inside watchlist territory. This is the customer-
            # retention tier; it deserves primary visibility.
            if _watchlist_bucket:
                _under_mv_promoted = [
                    (_r, _v) for _r, _v in _watchlist_bucket
                    if str(
                        (_v or {}).get("final_execution_decision")
                        or (_r or {}).get("execution_final_decision")
                        or (_r or {}).get("final_execution_decision")
                        or ""
                    ).strip().upper() == "UNDER_MV"
                ]
                if _under_mv_promoted:
                    st.markdown(
                        "<div style='margin:1.4rem 0 0.3rem 0;padding:0.65rem 1rem;"
                        "background:linear-gradient(90deg,#03161a 0%,#0a0f1a 100%);"
                        "border-left:5px solid #06b6d4;border-radius:8px;"
                        "display:flex;align-items:center;justify-content:space-between;'>"
                        "<span style='font-weight:800;color:#67e8f9;font-size:0.92rem;letter-spacing:0.04em'>"
                        "UNDER MV — DEALS WORTH BIDDING</span>"
                        f"<span style='color:#67e8f9;font-size:0.78rem;opacity:0.85'>"
                        f"{len(_under_mv_promoted)} bidding below market value</span>"
                        "</div>",
                        unsafe_allow_html=True,
                    )
                    print(
                        f"[UI_HEADER_RESOLUTION] section=UNDER_MV_PROMOTED "
                        f"row_count={len(_under_mv_promoted)} location=above_watchlist_block"
                    )
                    _under_mv_start_idx = _n_sniper_board
                    for _umv_idx, (_umv_r, _umv_v) in enumerate(_under_mv_promoted):
                        _render_es_watchlist_card(_umv_r, _umv_v, _under_mv_start_idx + _umv_idx)
                    # Strip these rows from _watchlist_bucket so they don't
                    # double-render inside the watchlist split below.
                    _watchlist_bucket = [
                        (_r, _v) for _r, _v in _watchlist_bucket
                        if (_r, _v) not in _under_mv_promoted
                    ]

            # ─── Render: watchlist split by final_execution_decision ───────────
            # Per business doc: "Final-action truth should override legacy UI
            # labels." Group _watchlist_bucket by decision so PASS rows show
            # under "PASS — overpriced (review later)" instead of "HIGH-HEAT
            # WATCHLIST", and SNIPE/WATCH rows show under decisive headers.
            # Pure UI grouping — no row dropped, no business logic touched.
            if _watchlist_bucket:
                _wb_groups: Dict[str, List] = {
                    "SNIPE_NOW": [], "UNDER_MV": [], "WATCH": [], "RESEARCH_SNIPE": [],
                    "RESEARCH_WATCH": [], "RESEARCH_PASS": [],
                    "PASS_OVERPRICED": [], "PASS": [], "WATCHLIST_LEGACY": [],
                }
                # [WATCHLIST_NO_MV_FILTER] — drop PASS_OVERPRICED rows that have
                # no MV (the "(no MV)" badge text is the fingerprint). User saw
                # 5 of these in latest scan — Pete Crow-Armstrong /25 AP6,
                # Skenes Blue Prizm /199, Holliday Gold /50, Skenes TC Black
                # Auto, etc. — all with REFERENCE VALUE / MAX BID / COMPS
                # blank. They're upstream-provisional frankenrows (target was
                # set when MV briefly existed; MV cleared but target survived)
                # and should not occupy board real estate.
                _no_mv_dropped = 0
                _no_mv_dropped_titles: List[str] = []
                for _row, _view in _watchlist_bucket:
                    _wb_dec = str(
                        _view.get("final_execution_decision")
                        or _row.get("execution_final_decision")
                        or _row.get("final_execution_decision")
                        or ""
                    ).strip().upper()
                    # No-MV PASS row detection — multiple signals:
                    # - reason starts with "pass_overpriced_no_mv"
                    # - market_value is missing/zero AND mv_comp_count=0
                    # - _synthetic_no_mv flag is set
                    _row_reason = str(
                        _view.get("final_action_reason")
                        or _row.get("final_action_reason")
                        or ""
                    ).lower()
                    _row_mv = (
                        _safe_float(_row.get("market_value"))
                        or _safe_float(_row.get("true_market_value"))
                        or _safe_float(_row.get("mv_value"))
                        or _safe_float(_row.get("true_mv"))
                        or 0.0
                    )
                    _row_mv_comp_count = int(
                        (_safe_float(_row.get("mv_comp_count")) or 0)
                        or (_safe_float(_row.get("comp_count")) or 0)
                        or (_safe_float(_row.get("trusted_exact_comp_count")) or 0)
                    )
                    _row_synth = bool(
                        _row.get("_synthetic_no_mv")
                        or _row.get("_synthetic_trusted_exact")
                    )
                    _is_no_mv_pass = (
                        _wb_dec in {"PASS_OVERPRICED", "PASS"}
                        and (
                            _row_reason.startswith("pass_overpriced_no_mv")
                            or _row_synth
                            or (_row_mv <= 0 and _row_mv_comp_count <= 0)
                        )
                    )
                    if _is_no_mv_pass:
                        _no_mv_dropped += 1
                        _t = str(_row.get("title") or _row.get("source_title") or "")[:80]
                        if len(_no_mv_dropped_titles) < 5:
                            _no_mv_dropped_titles.append(_t)
                        continue
                    if _wb_dec in _wb_groups:
                        _wb_groups[_wb_dec].append((_row, _view))
                    else:
                        _wb_groups["WATCHLIST_LEGACY"].append((_row, _view))
                if _no_mv_dropped > 0:
                    try:
                        print(
                            f"[WATCHLIST_NO_MV_FILTER] dropped={_no_mv_dropped} "
                            f"sample_titles={_no_mv_dropped_titles}"
                        )
                    except Exception:
                        pass

                # [WATCHLIST_PASS_CAP] — apply same 3-row cap to PASS_OVERPRICED
                # in watchlist as primary board has via HIDE_PASS_OVERPRICED.
                # Without this, PASS rows still flood the watchlist when
                # actionable inventory exists. If we have 3+ actionable
                # (SNIPE/UNDER_MV/WATCH) rows, hide ALL pass rows.
                _wb_actionable_total = (
                    len(_wb_groups.get("SNIPE_NOW") or [])
                    + len(_wb_groups.get("UNDER_MV") or [])
                    + len(_wb_groups.get("WATCH") or [])
                    + len(_wb_groups.get("RESEARCH_SNIPE") or [])
                )
                _wb_pass_pre = len(_wb_groups.get("PASS_OVERPRICED") or [])
                _wb_pass_pre_pass = len(_wb_groups.get("PASS") or [])
                _wb_pass_pre_research = len(_wb_groups.get("RESEARCH_PASS") or [])
                if _wb_actionable_total >= 3:
                    _wb_groups["PASS_OVERPRICED"] = []
                    _wb_groups["PASS"] = []
                    _wb_groups["RESEARCH_PASS"] = []
                else:
                    _wb_groups["PASS_OVERPRICED"] = (_wb_groups.get("PASS_OVERPRICED") or [])[:3]
                    _wb_groups["PASS"] = (_wb_groups.get("PASS") or [])[:2]
                    _wb_groups["RESEARCH_PASS"] = (_wb_groups.get("RESEARCH_PASS") or [])[:2]
                _wb_pass_after = (
                    len(_wb_groups.get("PASS_OVERPRICED") or [])
                    + len(_wb_groups.get("PASS") or [])
                    + len(_wb_groups.get("RESEARCH_PASS") or [])
                )
                _wb_pass_pre_total = _wb_pass_pre + _wb_pass_pre_pass + _wb_pass_pre_research
                if _wb_pass_pre_total != _wb_pass_after:
                    try:
                        print(
                            f"[WATCHLIST_PASS_CAP] actionable={_wb_actionable_total} "
                            f"pass_pre={_wb_pass_pre_total} pass_after={_wb_pass_after} "
                            f"hidden={_wb_pass_pre_total - _wb_pass_after}"
                        )
                    except Exception:
                        pass
                # UNDER_MV slots between SNIPE_NOW and WATCH — it's a real deal
                # tier (current under MV) and should NOT get buried in the
                # legacy "HIGH-HEAT WATCHLIST · premium secondary looks" header
                # that signals "we're not sure about this one." Cyan/blue tone
                # distinct from green snipes and amber watch.
                _wb_section_specs = [
                    ("SNIPE_NOW",       "SNIPE NOW",                    "snipers ready",          "#22c55e", "#0a1f10", "#86efac"),
                    ("UNDER_MV",        "UNDER MV — deals worth bidding","below market value",    "#06b6d4", "#03161a", "#67e8f9"),
                    ("WATCH",           "WATCH — near target",          "approaching bid window", "#f59e0b", "#1c1407", "#fbbf24"),
                    ("RESEARCH_SNIPE",  "RESEARCH SNIPE",               "research-grade snipe",   "#10b981", "#031f17", "#6ee7b7"),
                    ("RESEARCH_WATCH",  "RESEARCH WATCH",               "verify before bid",      "#d97706", "#1f1407", "#fbbf24"),
                    ("WATCHLIST_LEGACY","HIGH-HEAT WATCHLIST",          "premium secondary looks","#3b82f6", "#0a0f1a", "#93c5fd"),
                    ("RESEARCH_PASS",   "RESEARCH — above band",        "ranged out",             "#b0b0b0", "#0f172a", "#fafafa"),
                    ("PASS_OVERPRICED", "PASS — overpriced (review)",   "current > target +5%",   "#dc2626", "#1a0505", "#fca5a5"),
                    ("PASS",            "PASS — no target bid",         "no actionable bid",      "#b0b0b0", "#0f172a", "#fafafa"),
                ]
                _watch_start_idx = _n_sniper_board
                _wb_rendered = 0
                for _wb_key, _wb_title, _wb_subtitle, _wb_border, _wb_bg, _wb_text in _wb_section_specs:
                    _wb_rows = _wb_groups.get(_wb_key) or []
                    if not _wb_rows:
                        continue
                    st.markdown(
                        f"<div style='margin:1.4rem 0 0.3rem 0;padding:0.55rem 1rem;"
                        f"background:linear-gradient(90deg,{_wb_bg} 0%,#0a0f1a 100%);"
                        f"border-left:4px solid {_wb_border};border-radius:8px;"
                        f"display:flex;align-items:center;justify-content:space-between;'>"
                        f"<span style='font-weight:800;color:{_wb_text};font-size:0.86rem;letter-spacing:0.04em'>"
                        f"{_wb_title}</span>"
                        f"<span style='color:{_wb_text};font-size:0.75rem;opacity:0.85'>"
                        f"{len(_wb_rows)} {_wb_subtitle}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    print(
                        f"[UI_HEADER_RESOLUTION] section={_wb_key} title={_wb_title!r} "
                        f"row_count={len(_wb_rows)}"
                    )
                    for _widx, (_row, _view) in enumerate(_wb_rows):
                        _render_es_watchlist_card(_row, _view, _watch_start_idx + _wb_rendered + _widx)
                    _wb_rendered += len(_wb_rows)
                print(
                    f"[WATCHLIST_MAIN_RENDER] rendered={_wb_rendered} "
                    f"premium_secondary={len(_watchlist_bucket)} "
                    f"groups={ {k: len(v) for k, v in _wb_groups.items() if v} }"
                )

            if _prep_view_models:
                st.markdown(
                    "<div style='margin:1.4rem 0 0.3rem 0;padding:0.55rem 1rem;"
                    "background:linear-gradient(90deg,#111827 0%,#0a0f1a 100%);border-left:4px solid #f59e0b;border-radius:8px;"
                    "display:flex;align-items:center;justify-content:space-between;'>"
                    "<div>"
                    "<div style='font-weight:800;color:#fde68a;font-size:0.86rem;letter-spacing:0.04em'>"
                    "PREP BOARD</div>"
                    "<div style='color:#b0b0b0;font-size:0.74rem;margin-top:0.18rem'>"
                    "premium cards worth tracking before they become actionable</div>"
                    "</div>"
                    f"<span style='color:#fbbf24;font-size:0.75rem'>{len(_prep_view_models)} prep rows</span>"
                    "</div>",
                    unsafe_allow_html=True,
                )
                print(f"[PREP_BOARD_RENDER] rendered={len(_prep_view_models)}")
                for _pidx, (_row, _view) in enumerate(_prep_view_models):
                    _render_es_prep_board_card(_row, _view, _pidx)

            if research_queue_rows:
                st.markdown(
                    "<div style='margin:1.4rem 0 0.3rem 0;padding:0.55rem 1rem;"
                    "background:#111827;border-left:4px solid #b0b0b0;border-radius:8px;'>"
                    "<div style='display:flex;align-items:center;justify-content:space-between;'>"
                    "<span style='font-weight:800;color:#e5e7eb;font-size:0.86rem;letter-spacing:0.04em'>"
                    "RESEARCH QUEUE</span>"
                    f"<span style='color:#fafafa;font-size:0.75rem'>{len(research_queue_rows)} candidates</span>"
                    "</div>"
                    "<div style='color:#b0b0b0;font-size:0.74rem;margin-top:0.18rem'>"
                    "Premium candidates without verified comp evidence yet</div>"
                    "</div>",
                    unsafe_allow_html=True,
                )
                for _rq in list(research_queue_rows or []):
                    _rq_title = str((_rq or {}).get("title") or (_rq or {}).get("source_title") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    _rq_research_only = bool((_rq or {}).get("_research_only_price_check") or str((_rq or {}).get("_surface_tier") or "") == "research_only")
                    _rq_collector_heat = bool((_rq or {}).get("_collector_heat_surface"))
                    _rq_heat_reasons = [
                        str(_reason).strip().upper()
                        for _reason in list((_rq or {}).get("heat_signal_reasons") or [])
                        if str(_reason or "").strip()
                    ]
                    _rq_current = _safe_float((_rq or {}).get("current_price") or (_rq or {}).get("current") or (_rq or {}).get("price"))
                    _rq_review = _safe_float((_rq or {}).get("review_estimate") or (_rq or {}).get("review_estimate_value"))
                    _rq_target = _safe_float((_rq or {}).get("target_bid") or (_rq or {}).get("target_bid_price") or (_rq or {}).get("bid_ceiling_value"))
                    _rq_current_html = f"<span>Current: <b>${_rq_current:.2f}</b></span>" if _rq_current is not None else "<span>Current: <b>n/a</b></span>"
                    if _rq_research_only:
                        _rq_review_html = "<span>Price check: <b>needed</b></span>"
                        _rq_target_html = "<span>Evidence: <b>needs comps</b></span>"
                        _rq_badge_1 = "HIGH-HEAT RESEARCH" if _rq_collector_heat else "RESEARCH ONLY"
                        _rq_badge_2 = "PRICE CHECK NEEDED"
                        _rq_badge_3 = _rq_heat_reasons[0] if _rq_heat_reasons else "CURRENT PRICE ONLY"
                    else:
                        _rq_review_html = f"<span>Review estimate: <b>${_rq_review:.2f}</b></span>" if _rq_review is not None else "<span>Review estimate: <b>n/a</b></span>"
                        _rq_target_html = f"<span>Target bid: <b>${_rq_target:.2f}</b></span>" if _rq_target is not None else "<span>Target bid: <b>n/a</b></span>"
                        _rq_badge_1 = "HIGH-HEAT RESEARCH" if _rq_collector_heat else "RESEARCH"
                        _rq_badge_2 = _rq_heat_reasons[0] if _rq_heat_reasons else "REVIEW ONLY"
                        _rq_badge_3 = _rq_heat_reasons[1] if len(_rq_heat_reasons) > 1 else "NO VERIFIED COMP EVIDENCE"
                    st.markdown(
                        "<div style='margin:0.45rem 0;padding:0.75rem 0.85rem;border:1px solid #666666;"
                        "border-radius:8px;background:#0f172a;'>"
                        f"<div style='font-weight:700;color:#fafafa;font-size:0.9rem'>{_rq_title}</div>"
                        "<div style='margin-top:0.45rem;display:flex;gap:0.4rem;flex-wrap:wrap;'>"
                        f"<span style='background:#666666;color:#e2e8f0;border-radius:999px;padding:0.16rem 0.48rem;font-size:0.68rem;font-weight:800;'>{_rq_badge_1}</span>"
                        f"<span style='background:#78350f;color:#fde68a;border-radius:999px;padding:0.16rem 0.48rem;font-size:0.68rem;font-weight:800;'>{_rq_badge_2}</span>"
                        f"<span style='background:#450a0a;color:#fecaca;border-radius:999px;padding:0.16rem 0.48rem;font-size:0.68rem;font-weight:800;'>{_rq_badge_3}</span>"
                        "</div>"
                        "<div style='margin-top:0.55rem;color:#fafafa;font-size:0.78rem;display:flex;gap:1rem;flex-wrap:wrap;'>"
                        f"{_rq_current_html}{_rq_review_html}{_rq_target_html}"
                        "</div></div>",
                        unsafe_allow_html=True,
                    )

            # ─── Empty state ────────────────────────────────────────────────────────
            if not _sniper_board and not _watchlist_bucket and not _suppressed_rows and not research_queue_rows:
                _eng_visible_count = sum(
                    1 for _r in _deals
                    if _ui_is_engine_visible_watchlist_candidate(_r)
                )
                if _eng_visible_count > 0:
                    print(
                        f"[EMPTY_MESSAGE_BLOCKED] WARN: engine stamped board_visible={_eng_visible_count} "
                        f"rows but board is still empty — rescue did not promote them to watchlist"
                    )
                print('[ES][BOARD_MESSAGE] mode=pre_final_empty_guard text="pending_final_surface_guard"')
            _remainder_surface_metrics = {
                "input": len(_suppressed_rows),
                "allowed": 0,
                "blocked": 0,
            }
            if _suppressed_rows:
                _suppressed_render_rows = []
                for _row, _view in _suppressed_rows:
                    _final_route = _ui_resolve_final_surface_route(_row, emit_log=False)
                    _route = str(_final_route.get("route") or "blocked").strip().lower()
                    if _route in {"sniper", "watchlist"}:
                        _remainder_surface_metrics["blocked"] += 1
                        print(
                            f"[OTHER_LISTING_REDIRECT_BLOCK] title={str((_row or {}).get('title') or (_row or {}).get('source_title') or '')[:120]} "
                            f"reason=final_surface_{_route}"
                        )
                        continue
                    if _route != "remainder":
                        _remainder_surface_metrics["blocked"] += 1
                        continue
                    _remainder_surface_metrics["allowed"] += 1
                    _suppressed_render_rows.append((_row, _view))
                _suppressed_rows = _suppressed_render_rows
            print(
                f"[REMAINDER_SURFACE_FINAL] input={_remainder_surface_metrics['input']} "
                f"allowed={_remainder_surface_metrics['allowed']} "
                f"blocked={_remainder_surface_metrics['blocked']} "
                f"displayed={len(_suppressed_rows)}"
            )
            _final_surface_guard_seen: Set[str] = set()
            _final_surface_guard = {
                "board_visible_rows": 0,
                "routable_rows": 0,
                "blocked_rows": 0,
            }
            for _row in _deals:
                if not isinstance(_row, dict):
                    continue
                _rid = _ui_live_watchlist_row_id(_row)
                if _rid in _final_surface_guard_seen:
                    continue
                _final_surface_guard_seen.add(_rid)
                _board_visible = bool(_row.get("board_visible"))
                _canonical_preserved = bool(_row.get("canonical_board_preserved"))
                if not (_board_visible or _canonical_preserved):
                    continue
                if _board_visible:
                    _final_surface_guard["board_visible_rows"] += 1
                _route_contract = _ui_resolve_final_surface_route(_row, emit_log=False)
                if str(_route_contract.get("route") or "blocked").strip().lower() == "blocked":
                    _final_surface_guard["blocked_rows"] += 1
                else:
                    _final_surface_guard["routable_rows"] += 1
            _show_final_empty_state = bool(
                not _sniper_board
                and not _watchlist_bucket
                and not _suppressed_rows
                and not research_queue_rows
                and _final_surface_guard["routable_rows"] <= 0
                and _deal_ct <= 0
            )
            print(
                f"[LIVE_BOARD_EMPTY_STATE] deals_loaded={_deal_ct} "
                f"visible_rows={len(_sniper_board) + len(_watchlist_bucket)}"
            )
            print(
                f"[FINAL_SURFACE_EMPTY_GUARD] board_visible_rows={_final_surface_guard['board_visible_rows']} "
                f"routable_rows={_final_surface_guard['routable_rows']} "
                f"blocked_rows={_final_surface_guard['blocked_rows']} "
                f"show_empty={1 if _show_final_empty_state else 0}"
            )
            print(
                f"[FINAL_SURFACE_SUMMARY] sniper={len(_sniper_board)} "
                f"watchlist={len(_watchlist_bucket)} "
                f"remainder={len(_suppressed_rows)} "
                f"blocked={_final_surface_guard['blocked_rows']} "
                f"displayed={len(_sniper_board) + len(_watchlist_bucket) + len(_suppressed_rows)}"
            )
            print(
                f"[ES][BOARD_STATE] all={_dl_input} "
                f"displayed={len(_sniper_board) + len(_watchlist_bucket) + len(_suppressed_rows)} "
                f"dropped={max(0, _dl_input - (len(_sniper_board) + len(_watchlist_bucket) + len(_suppressed_rows)))}"
            )
            if _show_final_empty_state:
                if _final_surface_guard["board_visible_rows"] > 0:
                    print(
                        f"[EMPTY_MESSAGE_BLOCKED] WARN: engine stamped board_visible={_final_surface_guard['board_visible_rows']} "
                        f"rows but every final route hard-blocked before render"
                    )
                st.info(
                    "No sniper candidates or watchlist cards right now. "
                    f"Scanned {len(_deals)} listing(s). "
                    "Check back when new auctions open or prices move."
                )
                print('[ES][BOARD_MESSAGE] mode=empty text="no_cards_cleared_threshold"')
            else:
                print(f'[ES][BOARD_MESSAGE] mode=sniper_board text="{_board_msg}"')
            if _suppressed_rows:
                with st.expander(
                    f"All other listings ({len(_suppressed_rows)})", expanded=False
                ):
                    st.caption(
                        "These listings did not clear the decision threshold. "
                        "They may surface if pricing, comps, heat, or edge improves."
                    )
                    for _idx, (_row, _view) in enumerate(
                        _suppressed_rows, start=len(board_rows_displayed)
                    ):
                        _render_es_suppressed_card(_row, _view, _idx)
            _badge_guard = _badge_guard_snapshot()
            print(
                f"[ES][BADGE_GUARD] structured_ok={int(_badge_guard.get('structured_ok') or 0)} "
                f"legacy_blocked={int(_badge_guard.get('legacy_blocked') or 0)} "
                f"non_dict_dropped={int(_badge_guard.get('non_dict_dropped') or 0)}"
            )
            print(
                f"[ES][BADGE_ASSERT] clean_rows={int(_badge_guard.get('clean_rows') or 0)} "
                f"failed_rows={int(_badge_guard.get('failed_rows') or 0)}"
            )

        elif _show_empty_state:
            # Legacy in-page empty state ("No deals this scan" + Scan details
            # debug expander) removed May 2026. The morning briefing at the
            # top of the page surfaces its own empty/loading states off the
            # daily_pool.json pipeline.
            pass
        else:
            # Legacy "Scanning live eBay auctions…" loading state removed
            # May 2026. The new pipeline runs continuously in the background
            # via supervisor.py, so the user never sees a synchronous scan.
            pass

    except Exception as _tab_err:
        # Friendly error state — UPDATED 2026-05-06
        # Old version printed the raw exception ("Ending Soon tab error: ...")
        # which is intimidating to beta users. New version explains, offers
        # an action (refresh + report), and keeps the traceback in a
        # collapsible expander for debugging.
        st.markdown(
            "<div class='sw-empty-state'>"
            "<span class='sw-empty-state-icon'>⚠</span>"
            "<div class='sw-empty-state-title'>Something went wrong rendering this page</div>"
            "<div class='sw-empty-state-body'>"
            "Try reloading the browser. If the error persists, copy the technical "
            "detail below and send it to support."
            "</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.caption(f"Error: `{type(_tab_err).__name__}: {str(_tab_err)[:160]}`")
        import traceback
        with st.expander("Technical detail (copy to report)", expanded=False):
            st.code(traceback.format_exc())

# =============================================================================
# TAB 1 — Auto-Buyer
# =============================================================================
elif _active_page_id == "auto_buyer":
    try:
        import tab_auto_buyer
        tab_auto_buyer.render_auto_buyer_tab()
    except Exception as _tab_err:
        st.error(f"Auto-Buyer tab error: {_tab_err}")
        import traceback
        with st.expander("Traceback", expanded=False):
            st.code(traceback.format_exc())

# =============================================================================
# TAB — My Snipes (added May 2026)
# Renders the snipes.json contents with win/loss tracking + ROI summary.
# =============================================================================
elif _active_page_id == "my_snipes":
    try:
        import snipes_view
        snipes_view.render_my_snipes(st)
    except Exception as _tab_err:
        _render_friendly_tab_error("My Snipes", _tab_err)

# =============================================================================
# TAB 2 — Purchased
# =============================================================================
elif _active_page_id == "purchased":
    try:
        import tab_purchased
        tab_purchased.render_purchased_tab()
    except Exception as _tab_err:
        _render_friendly_tab_error("Purchased", _tab_err)

# =============================================================================
# TAB 3 — Search eBay
# =============================================================================
elif _active_page_id == "search_ebay":
    try:
        import ebay_search as _es_mod
        import pandas as pd

        st.markdown(
            "<div style='font-size:1.1rem;font-weight:700;color:#f1f5f9;margin-bottom:0.5rem'>"
            "Search eBay Auctions</div>",
            unsafe_allow_html=True,
        )

        _s1, _s2, _s3 = st.columns([3, 1, 1])
        with _s1:
            _kw = st.text_input(
                "Keyword", key="srch_kw",
                placeholder="e.g.  mahomes psa 10",
                label_visibility="collapsed",
            )
        with _s2:
            _srch_limit = st.number_input(
                "Limit", min_value=1, max_value=50, value=10, step=1,
                key="srch_limit", label_visibility="collapsed",
            )
            st.caption(f"Max {_srch_limit} results")
        with _s3:
            _srch_mode = st.radio("Type", ["Auction", "BIN"], key="srch_mode",
                                  horizontal=True, label_visibility="collapsed")

        _do_search = st.button("Search eBay", type="primary", key="srch_btn")

        if _do_search:
            if not (_kw or "").strip():
                st.warning("Enter a keyword to search.")
            else:
                with st.spinner("Searching eBay…"):
                    try:
                        if _srch_mode == "BIN":
                            _items = _es_mod.search_bin_items(_kw.strip(), limit=int(_srch_limit))
                        else:
                            _items = _es_mod.search_auction_items(_kw.strip(), limit=int(_srch_limit))
                        st.session_state["search_results"] = list(_items or [])
                        st.session_state["search_last_kw"] = _kw.strip()
                    except Exception as _se:
                        st.error(f"Search failed: {_se}")

        _results: List[Dict[str, Any]] = st.session_state.get("search_results") or []
        _last_kw = st.session_state.get("search_last_kw") or ""

        if _results:
            st.markdown("<div class='sw-section-hdr'>Results</div>", unsafe_allow_html=True)
            st.caption(f'{len(_results)} result(s) for "{_last_kw}"')

            _rrows = []
            for _item in _results:
                _p_obj = _item.get("price") or {}
                _price = _p_obj.get("value") or 0.0
                try:
                    _price = float(_price)
                except (TypeError, ValueError):
                    _price = 0.0
                _end = (_item.get("itemEndDate") or "")[:16].replace("T", " ")
                _rrows.append({
                    "Title":       (_item.get("title") or "")[:60],
                    "Price ($)":   round(_price, 2),
                    "Ends":        _end or "—",
                    "Condition":   (_item.get("condition") or "—")[:20],
                    "URL":         _item.get("itemWebUrl") or "",
                })

            _df_s = pd.DataFrame(_rrows)
            _df_disp = _df_s.drop(columns=["URL"])
            st.dataframe(_df_disp, use_container_width=True, hide_index=True)

            with st.expander("Open listing", expanded=False):
                _s_titles = [r[:55] for r in _df_s["Title"]]
                _s_sel = st.selectbox("Select result", range(len(_s_titles)),
                                      format_func=lambda i: _s_titles[i],
                                      key="srch_url_sel")
                _s_url = _df_s.iloc[_s_sel]["URL"]
                if _s_url:
                    st.markdown(f"[Open on eBay ↗]({_s_url})")
                else:
                    st.caption("No URL for this item.")
        else:
            st.markdown(
                "<div class='sw-empty-state'>"
                "<span class='sw-empty-state-icon'>🔍</span>"
                "<div class='sw-empty-state-title'>No results yet</div>"
                "<div class='sw-empty-state-body'>Enter a keyword above and press "
                "<strong>Search eBay</strong> to query live eBay inventory.</div>"
                "</div>",
                unsafe_allow_html=True,
            )

    except Exception as _tab_err:
        st.error(f"Search eBay tab error: {_tab_err}")
        import traceback
        with st.expander("Traceback", expanded=False):
            st.code(traceback.format_exc())

# =============================================================================
# TAB 4 — Buying Radar (replaced May 2026 with the BIN pipeline)
# The legacy player_hub-driven radar UI lived here before. It read stored
# scan snapshots and didn't have its own live feed. The new implementation
# delegates entirely to bin_view.render_bin_radar(st), which reads
# bin_pool.json (populated by daily_bin_pool.py) and renders the same
# wallet-card aesthetic as the Ending Soon tab, sorted by discount-to-MV.
# =============================================================================
elif _active_page_id == "buying_radar":
    # Replaced May 2026 — full body delegated to bin_view (BIN pipeline).
    # The old player_hub-driven radar UI (~130 lines) was removed during
    # the cut-over. A copy lives in streamlit_app.PRE_CLEANUP_backup.20260506.py
    # if we ever need to restore.
    try:
        import bin_view
        bin_view.render_bin_radar(st)
    except Exception as _tab_err:
        _render_friendly_tab_error("Steals", _tab_err)

# Legacy Buying Radar code (~130 lines of player_hub-driven stored-scan
# UI) was removed during the BIN pipeline cut-over (May 2026). The
# elif buying_radar branch above now delegates entirely to bin_view.
# Restore from streamlit_app.PRE_CLEANUP_backup.20260506.py if needed.

# =============================================================================
# TAB 5 — Player Hub
# =============================================================================
elif _active_page_id == "player_hub":
    try:
        import player_hub as _ph_plh

        _plh1, _plh2 = st.columns([2, 1])
        with _plh1:
            st.markdown(
                "<div style='font-size:1.1rem;font-weight:700;color:#f1f5f9;margin-bottom:0.2rem'>"
                "Player Hub</div>"
                "<div style='font-size:0.82rem;color:#888888'>"
                "Discovery · Monitoring · Heat scores · Buy targets</div>",
                unsafe_allow_html=True,
            )
        with _plh2:
            st.markdown(
                "<div style='text-align:right;margin-top:0.2rem'>"
                "<span style='background:#052e16;color:#22c55e;border:1px solid #22c55e;"
                "border-radius:4px;padding:0.18rem 0.6rem;font-size:0.72rem;font-weight:700'>"
                "ENGINE ONLINE</span></div>",
                unsafe_allow_html=True,
            )

        st.markdown("<hr/>", unsafe_allow_html=True)

        # ── Hub stats from state file ──
        try:
            _plh_state = _ph_plh.load_player_hub_state()
            _players_dict = _plh_state.get("players") or {}
            _bu = _plh_state.get("buy_universe") or {}
            _pt = _bu.get("product_targets") or {}
            _active_targets = sum(1 for v in _pt.values() if isinstance(v, dict) and v.get("active", True))

            _ps1, _ps2, _ps3, _ps4 = st.columns(4)
            for _col, _label, _val in [
                (_ps1, "Players tracked",   len(_players_dict)),
                (_ps2, "Product targets",   len(_pt)),
                (_ps3, "Active targets",    _active_targets),
                (_ps4, "Buy universe rows", len(_bu.get("scan_results") or {})),
            ]:
                with _col:
                    st.markdown(
                        f"<div style='background:#111827;border:1px solid #1e2330;border-radius:8px;"
                        f"padding:0.65rem 1rem'>"
                        f"<div style='font-size:0.68rem;font-weight:700;letter-spacing:0.08em;"
                        f"color:#888888;text-transform:uppercase'>{_label}</div>"
                        f"<div style='font-size:1.4rem;font-weight:800;color:#f1f5f9'>{_val}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

            st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

            # ── Top players list ──
            if _players_dict:
                st.markdown("<div class='sw-section-hdr'>Players</div>", unsafe_allow_html=True)
                _plh_rows = []
                for _pid, _pdata in list(_players_dict.items())[:50]:
                    if not isinstance(_pdata, dict):
                        continue
                    _plh_rows.append({
                        "ID":          str(_pid)[:24],
                        "Name":        str(_pdata.get("name") or _pdata.get("display_name") or _pid)[:30],
                        "Sport":       str(_pdata.get("sport") or "—")[:8],
                        "Tier":        str(_pdata.get("whatnot_tier") or _pdata.get("tier") or "—"),
                        "Active":      "✓" if _pdata.get("active", True) else "—",
                    })
                if _plh_rows:
                    import pandas as pd
                    st.dataframe(pd.DataFrame(_plh_rows), use_container_width=True, hide_index=True)

        except Exception as _plh_err:
            st.warning(f"Could not load Player Hub state: {_plh_err}")

        st.markdown(
            "<div class='sw-empty-state' style='padding:2rem;margin-top:1rem'>"
            "<span class='sw-empty-state-icon'>🧠</span>"
            "<div class='sw-empty-state-title'>Full UI Being Restored</div>"
            "<div class='sw-empty-state-body'>Discovery runs, heat score dashboard, and target builder "
            "are being wired in. The Player Hub backend engine is fully operational.</div>"
            "</div>",
            unsafe_allow_html=True,
        )

    except Exception as _tab_err:
        st.error(f"Player Hub tab error: {_tab_err}")
        import traceback
        with st.expander("Traceback", expanded=False):
            st.code(traceback.format_exc())

# =============================================================================
# TAB 6 — Products
# =============================================================================
elif _active_page_id == "products":
    try:
        import player_hub_product_catalog as _prod_cat

        st.markdown(
            "<div style='font-size:1.1rem;font-weight:700;color:#f1f5f9;margin-bottom:0.2rem'>"
            "Products</div>"
            "<div style='font-size:0.82rem;color:#888888'>"
            "Product family catalog · Buy target templates · Grade and parallel lanes</div>",
            unsafe_allow_html=True,
        )
        st.markdown("<hr/>", unsafe_allow_html=True)

        try:
            # Try to surface catalog data
            _catalog = _prod_cat.PRODUCT_FAMILIES if hasattr(_prod_cat, "PRODUCT_FAMILIES") else None
            if _catalog is None and hasattr(_prod_cat, "get_product_families"):
                _catalog = _prod_cat.get_product_families()
            if _catalog is None and hasattr(_prod_cat, "load_catalog"):
                _catalog = _prod_cat.load_catalog()

            if _catalog:
                import pandas as pd
                _cat_rows = []
                _items = _catalog.items() if isinstance(_catalog, dict) else enumerate(_catalog)
                for _cid, _cdata in list(_items)[:100]:
                    if not isinstance(_cdata, dict):
                        _cat_rows.append({"ID": str(_cid), "Data": str(_cdata)[:60]})
                        continue
                    _cat_rows.append({
                        "ID":     str(_cid)[:24],
                        "Brand":  str(_cdata.get("brand") or "—")[:20],
                        "Sport":  str(_cdata.get("sport") or "—")[:10],
                        "Family": str(_cdata.get("family") or _cdata.get("product_family") or "—")[:30],
                        "Active": "✓" if _cdata.get("active", True) else "—",
                    })
                if _cat_rows:
                    st.markdown("<div class='sw-section-hdr'>Product Families</div>", unsafe_allow_html=True)
                    st.dataframe(pd.DataFrame(_cat_rows), use_container_width=True, hide_index=True)
                else:
                    raise ValueError("empty catalog")
            else:
                raise ValueError("no catalog found")

        except Exception:
            st.markdown(
                "<div class='sw-empty-state'>"
                "<span class='sw-empty-state-icon'>🗂</span>"
                "<div class='sw-empty-state-title'>Product Catalog</div>"
                "<div class='sw-empty-state-body'>Product family browser and buy target template manager. "
                "Catalog UI is being restored — backend module loaded.</div>"
                "</div>",
                unsafe_allow_html=True,
            )

    except ImportError:
        st.markdown(
            "<div class='sw-empty-state'>"
            "<span class='sw-empty-state-icon'>🗂</span>"
            "<div class='sw-empty-state-title'>Products</div>"
            "<div class='sw-empty-state-body'>Product catalog UI coming soon.</div>"
            "</div>",
            unsafe_allow_html=True,
        )
    except Exception as _tab_err:
        st.error(f"Products tab error: {_tab_err}")
        import traceback
        with st.expander("Traceback", expanded=False):
            st.code(traceback.format_exc())

# =============================================================================
# TAB 7 — Settings
# =============================================================================
elif _active_page_id == "settings":
    try:
        import settings_tools as _st_tools

        st.markdown(
            "<div style='font-size:1.1rem;font-weight:700;color:#f1f5f9;margin-bottom:0.75rem'>"
            "Settings</div>",
            unsafe_allow_html=True,
        )

        # HEALTH-2026-05-12: live pipeline status panel. Pulls the freshness
        # timestamps from the JSON files the backend writes and the rate-limit
        # state from ebay_search globals. Read-only: shows the user the system
        # is alive and current, plus surfaces 429 cooldowns when quota is dead
        # so they understand why MVs might be slow to populate.
        try:
            import json as _json
            from pathlib import Path as _Path
            import time as _time
            _hh = _Path(__file__).parent
            def _file_age_str(p: _Path) -> Tuple[str, str]:
                if not p.exists():
                    return ("—", "#888888")
                try:
                    _data = _json.loads(p.read_text(encoding="utf-8"))
                    _ts = float(_data.get("last_fetch_ts") or 0)
                    if _ts <= 0:
                        return ("never", "#f87171")
                    _age = _time.time() - _ts
                    if _age < 60:
                        return (f"{int(_age)}s ago", "#4ade80")
                    if _age < 3600:
                        return (f"{int(_age/60)}m ago", "#4ade80" if _age < 1800 else "#facc15")
                    if _age < 86400:
                        return (f"{int(_age/3600)}h ago", "#facc15")
                    return (f"{int(_age/86400)}d ago", "#f87171")
                except Exception:
                    return ("?", "#888888")
            _pool_age, _pool_color = _file_age_str(_hh / "daily_pool.json")
            _bin_age, _bin_color = _file_age_str(_hh / "bin_pool.json")
            # Rate-limit state read directly from ebay_search module globals
            try:
                import ebay_search as _es_health
                _now_ts = _time.time()
                _cool_until = float(getattr(_es_health, "_rate_limit_cooldown_until_ts", 0) or 0)
                _cooldown_active = _cool_until > _now_ts
                _consec_cooldowns = int(getattr(_es_health, "_consecutive_cooldowns", 0) or 0)
                if _cooldown_active:
                    _quota_status = f"cooldown active ({int(_cool_until - _now_ts)}s left)"
                    _quota_color  = "#facc15" if _consec_cooldowns <= 1 else "#f87171"
                elif _consec_cooldowns > 0:
                    _quota_status = f"recovering ({_consec_cooldowns} cooldowns since last hit)"
                    _quota_color  = "#facc15"
                else:
                    _quota_status = "healthy"
                    _quota_color  = "#4ade80"
            except Exception:
                _quota_status = "unknown"
                _quota_color  = "#888888"
            # Snipes count for the user's own context
            _snipes_count = 0
            try:
                import snipes_store as _ss_health
                _snipes_count = len(_ss_health.list_snipes() or [])
            except Exception:
                pass
            _label_css = (
                "font-size:10px;color:#888888;letter-spacing:0.12em;"
                "text-transform:uppercase;margin-bottom:4px;font-weight:600;"
            )
            _val_css_base = (
                "font-size:16px;font-weight:700;margin-bottom:2px;"
            )
            st.markdown(
                f"<div style='margin:6px 0 22px 0;padding:18px 22px;"
                f"background:linear-gradient(135deg,#141414 0%,#0a0a0a 100%);"
                f"border-radius:14px;font-family:-apple-system,\\'SF Pro Display\\',Inter,sans-serif;"
                f"color:#fafafa;border:1px solid rgba(148,163,184,0.08);'>"
                f"<div style='font-size:11px;font-weight:600;letter-spacing:0.18em;"
                f"color:#4ade80;text-transform:uppercase;margin-bottom:12px;'>"
                f"System health · live</div>"
                f"<div style='display:flex;gap:18px;flex-wrap:wrap;'>"
                f"<div style='flex:1;min-width:130px;'>"
                f"<div style='{_label_css}'>Auction pool</div>"
                f"<div style='{_val_css_base}color:{_pool_color};'>{_pool_age}</div></div>"
                f"<div style='flex:1;min-width:130px;'>"
                f"<div style='{_label_css}'>BIN pool</div>"
                f"<div style='{_val_css_base}color:{_bin_color};'>{_bin_age}</div></div>"
                f"<div style='flex:1;min-width:160px;'>"
                f"<div style='{_label_css}'>eBay API quota</div>"
                f"<div style='{_val_css_base}color:{_quota_color};font-size:14px;'>{_quota_status}</div></div>"
                f"<div style='flex:1;min-width:130px;'>"
                f"<div style='{_label_css}'>Your snipes</div>"
                f"<div style='{_val_css_base}color:#fafafa;'>{_snipes_count}</div></div>"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
        except Exception as _health_err:
            print(f"[SETTINGS_HEALTH_ERR] {type(_health_err).__name__}: {str(_health_err)[:160]}")

        _settings = _st_tools.load_settings()

        _sg1, _sg2 = st.columns([1.6, 1])

        with _sg1:
            with st.form("snipewins_settings_form"):
                st.markdown("<div class='sw-section-hdr'>Fees &amp; Margins</div>", unsafe_allow_html=True)
                _fee_pct = st.number_input(
                    "Selling fee %",
                    min_value=0.0, max_value=100.0,
                    value=float(_settings.get("fee_percent", 13.25)),
                    step=0.25,
                    help="eBay + PayPal combined selling fee percentage.",
                )
                _shipping = st.number_input(
                    "Shipping cost ($)",
                    min_value=0.0,
                    value=float(_settings.get("shipping_cost", 5.0)),
                    step=0.50,
                )
                _profit = st.number_input(
                    "Desired profit ($)",
                    min_value=0.0,
                    value=float(_settings.get("desired_profit", 20.0)),
                    step=1.0,
                )

                st.markdown("<div class='sw-section-hdr'>Snipe Timing</div>", unsafe_allow_html=True)
                _snipe_sec = st.number_input(
                    "Default snipe seconds",
                    min_value=1.0, max_value=30.0,
                    value=float(_settings.get("default_snipe_seconds", 7.0)),
                    step=1.0,
                    help="How many seconds before auction end to place the snipe bid.",
                )

                st.markdown("<div class='sw-section-hdr'>Bidding</div>", unsafe_allow_html=True)
                _auto_target = st.checkbox(
                    "Auto-calculate target bid from market value",
                    value=bool(_settings.get("auto_target_bid_from_market", True)),
                )
                _target_ratio = st.number_input(
                    "Target bid ratio  (0–1)",
                    min_value=0.0, max_value=1.0,
                    value=float(_settings.get("target_bid_ratio", 0.70)),
                    step=0.01,
                    format="%.2f",
                    help="Max bid = market_value × ratio. E.g. 0.70 = buy at 70% of MV.",
                )

                st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
                _save_btn = st.form_submit_button("Save Settings", type="primary")

            if _save_btn:
                _st_tools.save_settings({
                    "fee_percent":                _fee_pct,
                    "shipping_cost":              _shipping,
                    "desired_profit":             _profit,
                    "default_snipe_seconds":      _snipe_sec,
                    "auto_target_bid_from_market": _auto_target,
                    "target_bid_ratio":           _target_ratio,
                })
                st.success("Settings saved.")

        with _sg2:
            st.markdown("<div class='sw-section-hdr'>Current values</div>", unsafe_allow_html=True)
            _s_cur = _st_tools.load_settings()
            for _sk, _sv in _s_cur.items():
                st.markdown(
                    f"<div style='display:flex;justify-content:space-between;padding:0.3rem 0;"
                    f"border-bottom:1px solid #1e2330'>"
                    f"<span style='color:#888888;font-size:0.8rem'>{_sk}</span>"
                    f"<span style='color:#e2e8f0;font-size:0.8rem;font-weight:600'>{_sv}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    except Exception as _tab_err:
        st.error(f"Settings tab error: {_tab_err}")
        import traceback
        with st.expander("Traceback", expanded=False):
            st.code(traceback.format_exc())
