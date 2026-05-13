"""
eBay Auction Sniper Tool - Streamlit Dashboard

A clean, dark-themed dashboard for searching eBay auctions, managing a watchlist,
and configuring snipe timing.
"""

import json
import os
import webbrowser
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

import ebay_search
import ebay_tools
from calculators import calculate_target_bid
from profiles import (
    add_or_update_profile,
    delete_profile,
    get_profile_keywords,
    get_profile_names,
    load_profiles,
)
from settings_tools import load_settings, save_settings
from storage import read_watchlist_rows, write_watchlist_rows

# -----------------------------------------------------------------------------
# Persistence: app state (max bids, focus item) in a local JSON file
# -----------------------------------------------------------------------------
APP_STATE_FILE = "app_state.json"

NORMALIZED_KEYS = (
    "title", "url", "item_id", "current_price", "end_time", "time_left",
    "max_bid", "status", "snipe_time", "raw_row"
)


def load_app_state():
    """
    Load app state from app_state.json (max bids per item, focus_item_url, sim_triggers).
    Returns (state_dict, status) where status is one of: "loaded", "missing", "corrupt".
    On missing/corrupt file, returns defaults.
    """
    defaults = {"item_max_bids": {}, "focus_item_url": "", "sim_triggers_logged": {}}
    if not os.path.exists(APP_STATE_FILE):
        return defaults, "missing"
    try:
        with open(APP_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return defaults, "corrupt"
        data.setdefault("item_max_bids", {})
        data.setdefault("focus_item_url", "")
        data.setdefault("sim_triggers_logged", {})
        return data, "loaded"
    except (json.JSONDecodeError, OSError):
        return defaults, "corrupt"


def save_app_state(state):
    """Save app state to app_state.json."""
    try:
        with open(APP_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        logger = globals().get("append_log")
        if callable(logger):
            logger("Persistence: saved app state to app_state.json.", "success")
    except OSError as e:
        logger = globals().get("append_log")
        if callable(logger):
            logger(f"Persistence: could not save app state: {e}", "error")


def extract_item_id_from_url(url):
    """Extract eBay item ID from URL if present; otherwise return empty string."""
    if not url or not isinstance(url, str):
        return ""
    s = url.strip()
    if s.isdigit() and len(s) >= 10:
        return s
    if "/itm/" in s:
        part = s.split("/itm/")[-1].split("?")[0].strip()
        if part.isdigit():
            return part
    return ""


def safe_float_val(value, default=0.0):
    """Return value as float; on failure return default."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_local_end_time(end_time_text):
    """Parse an end time string in local format '%Y-%m-%d %H:%M:%S' into a datetime."""
    if not end_time_text:
        return None
    try:
        return datetime.strptime(str(end_time_text).strip(), "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def normalize_watchlist_row(row, max_bid_override=None):
    """Parse and normalize a raw watchlist row (from CSV) into a consistent structure."""
    if not row or not isinstance(row, dict):
        row = {}
    url = (row.get("item_url") or "").strip()
    end_time = (row.get("auction_end_time") or "").strip()
    time_left_sec = ebay_tools.get_seconds_left(end_time) if end_time else None
    current_price = safe_float_val(row.get("current_price"), 0.0)
    target = safe_float_val(row.get("target_bid"), 0.0)
    max_bid = target if max_bid_override is None else safe_float_val(max_bid_override, target)
    return {
        "title": (row.get("card_name") or "").strip() or "Unknown",
        "url": url,
        "item_id": extract_item_id_from_url(url),
        "current_price": current_price,
        "end_time": end_time,
        "time_left": time_left_sec,
        "max_bid": max_bid,
        "status": (row.get("status") or "WATCHING").strip() or "WATCHING",
        "snipe_time": (row.get("snipe_time") or "").strip(),
        "raw_row": row,
    }


def get_item_max_bid(item_url, item_max_bids_dict, row_target_bid):
    """Resolve max bid for an item: saved override (by url) > row's target_bid."""
    key = (item_url or "").strip().lower()
    if key and key in item_max_bids_dict:
        return safe_float_val(item_max_bids_dict[key], row_target_bid)
    return safe_float_val(row_target_bid, 0.0)


def compute_display_status(norm_row):
    """Compute a single display status for the normalized row."""
    time_left = norm_row.get("time_left")
    current = norm_row.get("current_price", 0)
    max_bid = norm_row.get("max_bid", 0)

    if time_left is not None and time_left <= 0:
        return "ended"
    if time_left is not None and time_left < 600:
        if current > max_bid:
            return "over_budget"
        if max_bid > 0 and (max_bid - current) / max_bid < 0.05:
            return "near_max"
        return "ending_soon"
    if max_bid > 0 and current > max_bid:
        return "over_budget"
    if max_bid > 0 and (max_bid - current) / max_bid < 0.05:
        return "near_max"
    return "good_deal"


def build_auction_state(row, item_max_bids_dict, default_snipe_seconds=7.0, trigger_logged_by_url=None):
    """
    Build a complete auction state model for a raw watchlist row.

    trigger_logged_by_url: optional dict keyed by item URL (lowercase). If the auction
    has ended (now >= end_dt) and the URL key is absent/false, simulation_status is
    "missed" (ready window never reached/logged). If the key is present/truthy,
    simulation_status is "ended".
    """
    row = row or {}
    url = (row.get("item_url") or "").strip()
    max_bid = get_item_max_bid(url, item_max_bids_dict or {}, row.get("target_bid"))
    norm = normalize_watchlist_row(row, max_bid_override=max_bid)
    display_status = compute_display_status(norm)

    snipe_seconds = safe_float_val(row.get("snipe_seconds"), default_snipe_seconds)
    if snipe_seconds <= 0:
        snipe_seconds = default_snipe_seconds

    end_dt = parse_local_end_time(norm.get("end_time"))
    trigger_dt = end_dt - timedelta(seconds=snipe_seconds) if end_dt else None
    trigger_text = trigger_dt.strftime("%Y-%m-%d %H:%M:%S") if trigger_dt else ""

    now = datetime.now()
    time_left = (end_dt - now).total_seconds() if end_dt else None

    simulation_status = "ended"
    if end_dt is None or trigger_dt is None:
        simulation_status = "ended"
    elif now < trigger_dt:
        simulation_status = "pending"
    elif trigger_dt <= now < end_dt:
        simulation_status = "ready"
    else:
        # Auction over: ended only if we ever reached/logged the ready window for this URL
        key = (url or "").strip().lower()
        logged = trigger_logged_by_url or {}
        if key and logged.get(key):
            simulation_status = "ended"
        elif end_dt and now >= end_dt:
            simulation_status = "missed"
        else:
            simulation_status = "ended"

    return {
        "title": norm.get("title", "Unknown"),
        "url": norm.get("url", ""),
        "item_id": norm.get("item_id", ""),
        "current_price": norm.get("current_price", 0.0),
        "max_bid": norm.get("max_bid", 0.0),
        "end_time": norm.get("end_time", ""),
        "time_left": time_left,
        "display_status": display_status,
        "snipe_seconds": snipe_seconds,
        "snipe_trigger_time": trigger_text,
        "simulation_status": simulation_status,
        "raw_row": norm.get("raw_row", row),
    }


def search_results_dataframe(items, market_value):
    """Build a DataFrame of search results with target bid and time left."""
    target_bid = calculate_target_bid(market_value)
    results = []
    for item in items:
        price = item.get("price") or {}
        current_price = ebay_tools.safe_float(price.get("value"), 0.0)
        end_time = ebay_tools.format_ebay_end_time(item.get("itemEndDate") or "")
        seconds_left = ebay_tools.get_seconds_left(end_time)
        results.append({
            "title": item.get("title") or "",
            "current_price": current_price,
            "target_bid": target_bid,
            "decision": "GOOD DEAL" if current_price <= target_bid else "PASS",
            "end_time": end_time,
            "minutes_left": round(seconds_left / 60, 2) if seconds_left and seconds_left > 0 else None,
            "url": item.get("itemWebUrl") or "",
        })
    return pd.DataFrame(results)


def import_results_to_watchlist(items, market_value):
    """Import search/radar results into watchlist, skipping duplicates and over-bid items."""
    rows = read_watchlist_rows()
    existing_urls = {row.get("item_url", "").strip().lower() for row in rows if row.get("item_url", "").strip()}

    settings = load_settings()
    snipe_seconds = settings.get("default_snipe_seconds", 7.0)
    target_bid = calculate_target_bid(market_value)
    added_count = 0

    for item in items:
        title = (item.get("title") or "No title").strip()
        price = item.get("price") or {}
        current_price = ebay_tools.safe_float(price.get("value"), 0.0)
        end_date = ebay_tools.format_ebay_end_time(item.get("itemEndDate") or "")
        url = (item.get("itemWebUrl") or "").strip()

        if current_price > target_bid:
            continue
        if url and url.lower() in existing_urls:
            continue

        snipe_time = ebay_tools.build_snipe_time(end_date, snipe_seconds)
        decision = "GOOD DEAL" if current_price <= target_bid else "PASS"

        rows.append({
            "card_name": title,
            "current_price": str(round(current_price, 2)),
            "market_value": str(round(market_value, 2)),
            "max_buy_price": str(round(market_value * 0.70, 2)),
            "estimated_profit": str(round(market_value - current_price, 2)),
            "decision": decision,
            "auction_end_time": end_date,
            "snipe_seconds": str(snipe_seconds),
            "snipe_time": snipe_time,
            "target_bid": str(target_bid),
            "item_url": url,
            "notes": "",
            "status": "WATCHING",
        })
        if url:
            existing_urls.add(url.lower())
        added_count += 1

    write_watchlist_rows(rows)
    return added_count


def run_radar_once(keywords, market_value, minutes_limit=None):
    """Run one radar pass over keywords; returns (DataFrame of rows, list of found items)."""
    target_bid = calculate_target_bid(market_value)
    rows = []
    found_items = []

    for keyword in keywords:
        try:
            items = ebay_search.search_auction_items(keyword, limit=10)
        except Exception as e:
            rows.append({
                "keyword": keyword,
                "title": "",
                "current_price": "",
                "target_bid": target_bid,
                "decision": f"ERROR: {e}",
                "end_time": "",
                "minutes_left": "",
                "url": "",
            })
            continue

        for item in items:
            title = item.get("title") or ""
            price = item.get("price") or {}
            current_price = ebay_tools.safe_float(price.get("value"), 0.0)
            end_time = ebay_tools.format_ebay_end_time(item.get("itemEndDate") or "")
            seconds_left = ebay_tools.get_seconds_left(end_time)
            url = item.get("itemWebUrl") or ""

            if current_price > target_bid:
                continue
            if minutes_limit is not None and (seconds_left is None or seconds_left <= 0 or seconds_left > minutes_limit * 60):
                continue

            found_items.append(item)
            rows.append({
                "keyword": keyword,
                "title": title,
                "current_price": current_price,
                "target_bid": target_bid,
                "decision": "GOOD DEAL",
                "end_time": end_time,
                "minutes_left": round(seconds_left / 60, 2) if seconds_left and seconds_left > 0 else None,
                "url": url,
            })

    return pd.DataFrame(rows), found_items


def refresh_watchlist_prices(rows):
    """
    Fetch current prices from eBay for all watchlist items with valid item IDs.
    Returns (updated_rows, refresh_report) where refresh_report is a list of dicts with refresh status.
    """
    if not rows:
        return rows, []
    
    refresh_report = []
    updated_rows = []
    
    for idx, row in enumerate(rows):
        item_url = (row.get("item_url") or "").strip()
        item_id = extract_item_id_from_url(item_url)
        card_name = (row.get("card_name") or "Unknown")[:40]
        
        if not item_id:
            refresh_report.append({
                "item": card_name,
                "status": "skipped",
                "reason": "No valid item ID",
                "old_price": row.get("current_price", ""),
                "new_price": "",
            })
            updated_rows.append(row)
            continue
        
        # Check if auction has ended
        end_time = row.get("auction_end_time", "")
        seconds_left = ebay_tools.get_seconds_left(end_time)
        if seconds_left is not None and seconds_left <= 0:
            refresh_report.append({
                "item": card_name,
                "status": "skipped",
                "reason": "Auction ended",
                "old_price": row.get("current_price", ""),
                "new_price": "",
            })
            updated_rows.append(row)
            continue
        
        # Try to fetch fresh data from eBay
        try:
            items = ebay_search.search_auction_items(item_id, limit=1)
            
            if not items:
                refresh_report.append({
                    "item": card_name,
                    "status": "failed",
                    "reason": "Item not found on eBay",
                    "old_price": row.get("current_price", ""),
                    "new_price": "",
                })
                updated_rows.append(row)
                continue
            
            fresh_item = items[0]
            price_obj = fresh_item.get("price") or {}
            new_price = ebay_tools.safe_float(price_obj.get("value"), 0.0)
            old_price = safe_float_val(row.get("current_price"), 0.0)
            
            # Update the row with fresh price
            row["current_price"] = str(round(new_price, 2))
            
            # Recalculate estimated profit if we have market value
            market_value = safe_float_val(row.get("market_value"), 0.0)
            if market_value > 0:
                row["estimated_profit"] = str(round(market_value - new_price, 2))
            
            price_change = new_price - old_price
            refresh_report.append({
                "item": card_name,
                "status": "success",
                "reason": f"Price change: ${price_change:+.2f}" if price_change != 0 else "No change",
                "old_price": f"${old_price:.2f}",
                "new_price": f"${new_price:.2f}",
            })
            updated_rows.append(row)
            
        except Exception as e:
            refresh_report.append({
                "item": card_name,
                "status": "error",
                "reason": str(e)[:50],
                "old_price": row.get("current_price", ""),
                "new_price": "",
            })
            updated_rows.append(row)
    
    return updated_rows, refresh_report


def safe_profile_index(selected_name, profile_names_list):
    """Return index for selectbox so we never pass an invalid index."""
    options = ["None"] + profile_names_list
    if selected_name in options:
        return options.index(selected_name)
    return 0


def _format_countdown(seconds_left):
    """Format seconds into 'Xd Xh Xm Xs' or 'Ended' for display."""
    if seconds_left is None or seconds_left <= 0:
        return "Ended"
    d = int(seconds_left // 86400)
    h = int((seconds_left % 86400) // 3600)
    m = int((seconds_left % 3600) // 60)
    s = int(seconds_left % 60)
    parts = []
    if d > 0:
        parts.append(f"{d}d")
    if h > 0 or parts:
        parts.append(f"{h}h")
    parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


# -----------------------------------------------------------------------------
# Validation helpers
# -----------------------------------------------------------------------------


def validate_ebay_url(url):
    """Check if a string looks like a valid eBay item URL or numeric item ID."""
    if not url or not str(url).strip():
        return False, "URL or item ID is empty."
    s = str(url).strip()
    if s.isdigit() and len(s) >= 10:
        return True, None
    if "ebay.com" in s.lower() and ("/itm/" in s.lower() or "/itm/" in s):
        return True, None
    if "ebay.co.uk" in s.lower() or "ebay.de" in s.lower():
        if "/itm/" in s.lower():
            return True, None
    return False, "Please enter a valid eBay item URL or a numeric item ID."


def validate_market_value(value):
    """Validate market value: must be a positive number."""
    if value is None:
        return False, "Market value is required."
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False, "Market value must be a number."
    if v <= 0:
        return False, "Market value must be greater than 0."
    return True, None


def validate_bid_amount(value, allow_zero=False):
    """Validate bid/max bid amount."""
    if value is None:
        return False, "Bid amount is required."
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False, "Bid amount must be a number."
    if v < 0:
        return False, "Bid amount cannot be negative."
    if not allow_zero and v == 0:
        return False, "Bid amount must be greater than 0."
    return True, None


def validate_keyword(keyword):
    """Validate search keyword: non-empty after strip."""
    if not keyword or not str(keyword).strip():
        return False, "Please enter at least one search keyword."
    return True, None


# -----------------------------------------------------------------------------
# Session state and logging
# -----------------------------------------------------------------------------


def ensure_session_state():
    """Initialize session state keys."""
    defaults = {
        "selected_profile_name": "None",
        "radar_keywords_text": "mahomes psa 10, josh allen psa 10, lamar rookie auto",
        "last_search_items": [],
        "last_radar_items": [],
        "app_log": [],
        "focus_item_url": "",
        "focus_auction_end": "",
        "focus_current_price": "",
        "item_max_bids": {},
        "monitor_refresh_interval": 0,
        "log_level_filter": "All",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    
    if "app_state_loaded" not in st.session_state:
        try:
            loaded, status = load_app_state()
            if status == "missing":
                append_log("Persistence: app_state.json missing; using defaults.", "warning")
            elif status == "corrupt":
                append_log("Persistence: app_state.json corrupt/unreadable; recovered with defaults.", "warning")
            else:
                append_log("Persistence: loaded app_state.json.", "success")

            if loaded.get("item_max_bids"):
                st.session_state["item_max_bids"] = dict(loaded["item_max_bids"])
            if loaded.get("focus_item_url"):
                st.session_state["focus_item_url"] = str(loaded["focus_item_url"]).strip()
            if loaded.get("sim_triggers_logged"):
                st.session_state["sim_triggers_logged"] = dict(loaded["sim_triggers_logged"])
            else:
                st.session_state["sim_triggers_logged"] = {}
            st.session_state["app_state_loaded"] = True
        except Exception as e:
            append_log(f"Persistence: load failed, using defaults: {e}", "warning")
            st.session_state["sim_triggers_logged"] = {}
            st.session_state["app_state_loaded"] = True


def append_log(message, level="info"):
    """Add a timestamped message to the app log."""
    ensure_session_state()
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state["app_log"] = st.session_state["app_log"] + [{"time": ts, "msg": message, "level": level}]
    st.session_state["app_log"] = st.session_state["app_log"][-80:]




# -----------------------------------------------------------------------------
# Page config
# -----------------------------------------------------------------------------
st.set_page_config(page_title="eBay Auction Sniper", layout="wide", initial_sidebar_state="expanded")

# -----------------------------------------------------------------------------
# Dark theme and status box styling
# -----------------------------------------------------------------------------
DARK_CSS = """
<style>
.stApp { background-color: #0e1117; }
[data-testid="stHeader"] { background: #1a1d24; }
div[data-testid="stVerticalBlock"] > div {
    border-radius: 6px;
}
.status-box {
    padding: 1rem 1.25rem;
    border-radius: 8px;
    border: 1px solid #31333b;
    background: #1a1d24;
    margin: 0.5rem 0;
}
.snipe-card {
    padding: 1.25rem;
    border-radius: 8px;
    border: 1px solid #31333b;
    background: #1a1d24;
    margin: 0.5rem 0;
}
.log-panel {
    font-family: ui-monospace, monospace;
    font-size: 0.85rem;
    max-height: 280px;
    overflow-y: auto;
    padding: 0.75rem;
    border-radius: 6px;
    border: 1px solid #31333b;
    background: #161922;
}
</style>
"""
st.markdown(DARK_CSS, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Section 1: Header and quick presets
# -----------------------------------------------------------------------------
ensure_session_state()

header_container = st.container()
with header_container:
    st.markdown("# 🎯 eBay Auction Sniper")
    st.caption("Search auctions, manage your watchlist, and set snipe timing.")
    profiles = load_profiles()
    profile_names_list = list(profiles.keys())
    if profile_names_list:
        preset_cols = st.columns(min(4, len(profile_names_list)))
        for i, name in enumerate(profile_names_list[:4]):
            with preset_cols[i]:
                if st.button(name, key=f"preset_{name}"):
                    st.session_state["selected_profile_name"] = name
                    st.session_state["radar_keywords_text"] = ", ".join(get_profile_keywords(name))
                    append_log(f"Loaded profile: {name}", "info")
                    st.rerun()
st.divider()

# -----------------------------------------------------------------------------
# Section 2: Auction search / item input
# -----------------------------------------------------------------------------
search_container = st.container()
with search_container:
    st.markdown("## Auction search / item input")
    item_input_col1, item_input_col2 = st.columns([2, 1])
    with item_input_col1:
        search_keyword = st.text_input("Search keyword", value="mahomes psa 10", key="global_search_keyword")
    with item_input_col2:
        item_url_or_id = st.text_input("Or paste item URL or auction ID (optional)", key="item_url_or_id", placeholder="https://www.ebay.com/itm/...")
        if item_url_or_id and str(item_url_or_id).strip():
            valid, err = validate_ebay_url(item_url_or_id)
            if valid:
                st.caption("Valid eBay URL/ID.")
            else:
                st.caption(f":orange[{err}]")

    market_value_global = st.number_input(
        "Estimated market value ($)",
        min_value=0.0,
        value=300.0,
        step=1.0,
        key="global_market_value",
    )

    col_search, col_import, _ = st.columns(3)
    with col_search:
        if st.button("Search eBay", type="primary"):
            ok, err = validate_keyword(search_keyword)
            if not ok:
                append_log(err, "warning")
                st.warning(err)
            else:
                append_log("Starting eBay search...", "info")
                try:
                    items = ebay_search.search_auction_items(search_keyword.strip(), limit=10)
                    st.session_state["last_search_items"] = items if items else []
                    append_log(f"Search complete: {len(st.session_state['last_search_items'])} result(s).", "success")
                    if not items:
                        st.info("No results found.")
                    else:
                        st.success(f"Found {len(items)} auction(s).")
                except Exception as e:
                    msg = str(e) if str(e) else "Connection or API error. Check .env credentials."
                    append_log(f"Search failed: {msg}", "error")
                    st.error(f"Search failed. {msg}")
    with col_import:
        if st.button("Import good deals from last search"):
            items = st.session_state.get("last_search_items") or []
            if not items:
                append_log("Import skipped: no search results.", "warning")
                st.warning("Run a search first.")
            else:
                ok, err = validate_market_value(market_value_global)
                if not ok:
                    append_log(err, "warning")
                    st.warning(err)
                else:
                    append_log("Importing good deals to watchlist...", "info")
                    try:
                        added = import_results_to_watchlist(items, market_value_global)
                        append_log(f"Imported {added} deal(s) to watchlist.", "success")
                        st.success(f"Imported {added} new deal(s) to watchlist.")
                    except Exception as e:
                        append_log(f"Import failed: {e}", "error")
                        st.error(f"Import failed. Please try again.")

    last_items = st.session_state.get("last_search_items") or []
    if last_items:
        st.markdown("#### Last search results")
        try:
            df = search_results_dataframe(last_items, market_value_global)
            st.dataframe(df, use_container_width=True)
        except Exception as e:
            append_log(f"Display error: {e}", "warning")
            st.warning("Could not display results.")

st.divider()

# -----------------------------------------------------------------------------
# Section 3: Live auction monitor
# -----------------------------------------------------------------------------
rows = read_watchlist_rows()
item_max_bids = st.session_state.get("item_max_bids") or {}
focus_url = st.session_state.get("focus_item_url") or ""
focus_row = None
focus_state = None
for row in rows:
    if (row.get("item_url") or "").strip() == focus_url:
        focus_row = row
        settings_for_state = load_settings()
        default_snipe = safe_float_val(settings_for_state.get("default_snipe_seconds"), 7.0)
        merged_triggers = {**(st.session_state.get("sim_triggers_logged") or {}), **(st.session_state.get("sim_trigger_logged") or {})}
        focus_state = build_auction_state(row, item_max_bids, default_snipe_seconds=default_snipe, trigger_logged_by_url=merged_triggers)
        break
if not focus_row and rows:
    with_time = [(ebay_tools.get_seconds_left(r.get("auction_end_time") or ""), r) for r in rows]
    with_time = [(s, r) for s, r in with_time if s is not None and s > 0]
    with_time.sort(key=lambda x: x[0])
    if with_time:
        _, focus_row = with_time[0]
        focus_url = (focus_row.get("item_url") or "").strip()
        st.session_state["focus_item_url"] = focus_url
        settings_for_state = load_settings()
        default_snipe = safe_float_val(settings_for_state.get("default_snipe_seconds"), 7.0)
        merged_triggers = {**(st.session_state.get("sim_triggers_logged") or {}), **(st.session_state.get("sim_trigger_logged") or {})}
        focus_state = build_auction_state(focus_row, item_max_bids, default_snipe_seconds=default_snipe, trigger_logged_by_url=merged_triggers)

monitor_container = st.container()
with monitor_container:
    st.markdown("## Live auction monitor")
    refresh_col, _ = st.columns([1, 3])
    with refresh_col:
        interval = st.number_input("Auto-refresh every (sec); 0 = off", min_value=0, value=st.session_state.get("monitor_refresh_interval", 0), step=5, key="monitor_refresh_input")
        st.session_state["monitor_refresh_interval"] = int(interval) if interval is not None else 0
        interval = st.session_state["monitor_refresh_interval"]

    if focus_row and focus_state:
        current_price = focus_state["current_price"]
        max_bid = focus_state["max_bid"]
        seconds_left = focus_state["time_left"]
        countdown_str = _format_countdown(seconds_left)
        end_text = focus_state["end_time"]
        display_status = focus_state["display_status"]
        snipe_seconds = safe_float_val(focus_state.get("snipe_seconds"), 7.0)

        snipe_card = st.container(border=True)
        with snipe_card:
            st.markdown("#### Snipe summary")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Current price", f"${current_price:.2f}")
            with c2:
                st.metric("My max bid", f"${max_bid:.2f}")
            with c3:
                st.metric("Time remaining", countdown_str)
            st.caption(f"**Item:** {focus_state.get('title', 'Unknown')}")
            st.caption(f"**Auction end:** {end_text}")

        status_col1, status_col2, _ = st.columns(3)
        with status_col1:
            if seconds_left is not None and seconds_left <= 0:
                st.info("Auction ended.")
            elif current_price > max_bid:
                st.error("Above your max bid — over budget.")
            elif max_bid > 0 and (max_bid - current_price) / max_bid < 0.05:
                st.warning("Near your max bid — consider raising or watching closely.")
            else:
                st.success("Below your max bid — good deal range.")
        if seconds_left is not None and 0 < seconds_left < snipe_seconds:
            st.error("Strong warning: time remaining is below your configured snipe seconds.")
        elif display_status == "near_max" or (seconds_left is not None and 0 < seconds_left < 300):
            st.warning("Visual warning: auction is close to your max bid or ending in under 5 minutes.")
        with status_col2:
            if st.button("Refresh monitor", key="refresh_monitor"):
                append_log("Monitor: manual refresh.", "info")
                st.rerun()

        sim_card = st.container(border=True)
        with sim_card:
            st.markdown("#### Snipe simulation")
            trigger_time = focus_state.get("snipe_trigger_time", "")
            sim_status = focus_state.get("simulation_status", "ended")
            if sim_status == "pending":
                st.markdown("**Status:** :blue[pending]")
            elif sim_status == "ready":
                st.markdown("**Status:** :green[ready]")
            elif sim_status == "missed":
                st.markdown("**Status:** :orange[missed]")
            else:
                st.markdown("**Status:** :gray[ended]")

            a, b, c = st.columns(3)
            with a:
                st.caption(f"**Title:** {focus_state.get('title', 'Unknown')}")
                st.caption(f"**Current price:** ${current_price:.2f}")
            with b:
                st.caption(f"**My max bid:** ${max_bid:.2f}")
                st.caption(f"**Snipe seconds:** {int(snipe_seconds)}")
            with c:
                st.caption(f"**Auction end:** {end_text}")
                st.caption(f"**Trigger time:** {trigger_time or '—'}")

        if sim_status == "ready":
            if "sim_trigger_logged" not in st.session_state:
                st.session_state["sim_trigger_logged"] = {}
            if "sim_triggers_logged" not in st.session_state:
                st.session_state["sim_triggers_logged"] = {}
            key = (focus_state.get("url") or "").strip().lower()
            if key and not st.session_state["sim_trigger_logged"].get(key):
                append_log(f"Simulation: snipe would trigger now for '{focus_state.get('title','Unknown')}'.", "warning")
                st.session_state["sim_trigger_logged"][key] = True
                st.session_state["sim_triggers_logged"][key] = True
                save_app_state({
                    "item_max_bids": st.session_state.get("item_max_bids") or {},
                    "focus_item_url": st.session_state.get("focus_item_url") or "",
                    "sim_triggers_logged": dict(st.session_state["sim_triggers_logged"]),
                })
    else:
        st.info("No auction selected. Use the selector below or **Watchlist** tab → **Focus this item**.")

    if rows:
        with_time = [(ebay_tools.get_seconds_left(r.get("auction_end_time") or ""), r) for r in rows]
        with_time = [(s, r) for s, r in with_time if s is not None and s > 0]
        with_time.sort(key=lambda x: x[0])
        if with_time:
            monitor_options = []
            for _, r in with_time:
                url = (r.get("item_url") or "").strip()
                title = (r.get("card_name") or "Unknown")[:35]
                end = (r.get("auction_end_time") or "")[:16]
                monitor_options.append((f"{title}… · {end}", url))
            labels = [o[0] for o in monitor_options]
            current_focus = st.session_state.get("focus_item_url") or ""
            idx = 0
            for i, (_, url) in enumerate(monitor_options):
                if url == current_focus:
                    idx = i
                    break
            chosen = st.selectbox("Active monitored item", labels, index=idx, key="monitor_item_select")
            if st.button("Set as monitored", key="set_monitored_btn"):
                sel_idx = labels.index(chosen) if chosen in labels else 0
                new_url = monitor_options[sel_idx][1]
                st.session_state["focus_item_url"] = new_url
                state = {
                    "item_max_bids": st.session_state.get("item_max_bids") or {},
                    "focus_item_url": new_url,
                    "sim_triggers_logged": dict(st.session_state.get("sim_triggers_logged") or {}),
                }
                save_app_state(state)
                append_log("Monitor: active item updated.", "info")
                st.rerun()

st.divider()

# -----------------------------------------------------------------------------
# Section 4: Max bid & snipe timing
# -----------------------------------------------------------------------------
settings = load_settings()
default_snipe = settings.get("default_snipe_seconds", 7.0)
try:
    default_snipe_float = float(default_snipe)
except (TypeError, ValueError):
    default_snipe_float = 7.0

timing_container = st.container()
with timing_container:
    st.markdown("## Max bid & snipe timing")
    bid_col, snipe_col, _ = st.columns(3)
    with bid_col:
        st.markdown("**Max bid (target bid)**")
        st.caption("Calculated from market value minus fees, shipping, and profit (Settings tab).")
    with snipe_col:
        snipe_seconds_display = st.number

