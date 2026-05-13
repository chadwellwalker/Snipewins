"""
alerts.py — Phone alert system via Pushover

Entry points (all fire-and-forget, never raise):
  alert_elite_deal(deal)          — ELITE auction deal found
  alert_bin_deal(alert)           — BIN listing below 70% MV
  alert_snipe_won(item)           — auto-snipe bid placed successfully
  alert_session_complete(state)   — auto-buyer hits total budget
  alert_budget_warning(state)     — auto-buyer hits 80% of budget
  send_test_alert()               — send a test notification

Settings:
  load_alert_settings()  -> dict
  save_alert_settings(d) -> None

Credentials live in .env:
  PUSHOVER_USER_KEY=...
  PUSHOVER_API_TOKEN=...

Other preferences live in alert_settings.json (next to this file).
"""
from __future__ import annotations

import csv
import importlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE        = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR    = os.path.join(_HERE, "data")
_ALERT_LOG   = os.path.join(_DATA_DIR, "alert_log.csv")
_SETTINGS_FILE = os.path.join(_HERE, "alert_settings.json")

_LOG_COLS = ["timestamp", "alert_type", "listing_id", "player", "card_description", "message_sent"]

# ---------------------------------------------------------------------------
# Default settings
# ---------------------------------------------------------------------------

_DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    "alert_types": {
        "elite_deal":       True,
        "bin_alert":        True,
        "snipe_won":        True,
        "session_complete": True,
        "budget_warning":   True,
    },
    "min_deal_class":       "ELITE",
    "quiet_hours_enabled":  False,
    "quiet_start":          "22:00",
    "quiet_end":            "08:00",
}

# ---------------------------------------------------------------------------
# Settings load/save
# ---------------------------------------------------------------------------

def load_alert_settings() -> Dict[str, Any]:
    if not os.path.exists(_SETTINGS_FILE):
        return dict(_DEFAULTS)
    try:
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        # Merge with defaults so new keys are always present
        merged = dict(_DEFAULTS)
        merged.update(saved)
        if "alert_types" in saved:
            merged["alert_types"] = dict(_DEFAULTS["alert_types"])
            merged["alert_types"].update(saved["alert_types"])
        return merged
    except Exception:
        return dict(_DEFAULTS)


def save_alert_settings(settings: Dict[str, Any]) -> None:
    try:
        with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception as exc:
        print(f"[ALERTS] Could not save alert settings: {exc}")


# ---------------------------------------------------------------------------
# .env writer (updates PUSHOVER credentials without touching other vars)
# ---------------------------------------------------------------------------

def save_pushover_credentials(user_key: str, api_token: str) -> None:
    """Write PUSHOVER_USER_KEY and PUSHOVER_API_TOKEN into .env."""
    env_path = os.path.join(_HERE, ".env")
    try:
        from dotenv import set_key
        set_key(env_path, "PUSHOVER_USER_KEY",  user_key.strip())
        set_key(env_path, "PUSHOVER_API_TOKEN", api_token.strip())
        # Reload so subsequent calls in this process see new values
        load_dotenv(override=True)
    except Exception as exc:
        print(f"[ALERTS] Could not write credentials to .env: {exc}")


# ---------------------------------------------------------------------------
# Pushover library loader (auto-install if missing)
# ---------------------------------------------------------------------------

def _get_pushover_api():
    """
    Return PushoverAPI class or None if unavailable.
    Tries to pip-install pushover-complete once if the import fails.
    """
    for attempt in range(2):
        try:
            mod = importlib.import_module("pushover_complete")
            return getattr(mod, "PushoverAPI", None)
        except ImportError:
            if attempt == 0:
                print("[ALERTS] pushover-complete not found — attempting pip install…")
                try:
                    subprocess.check_call(
                        [sys.executable, "-m", "pip", "install", "pushover-complete"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    importlib.invalidate_caches()
                except Exception as e:
                    print(f"[ALERTS] pip install failed: {e}")
                    return None
    return None


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def _get_credentials() -> tuple[str, str]:
    """Return (user_key, api_token) from env. Empty strings if missing."""
    load_dotenv(override=True)
    user_key  = (os.getenv("PUSHOVER_USER_KEY")  or "").strip()
    api_token = (os.getenv("PUSHOVER_API_TOKEN") or "").strip()
    return user_key, api_token


def _credentials_ok() -> bool:
    u, t = _get_credentials()
    return bool(u) and bool(t)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _ensure_log() -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    if not os.path.exists(_ALERT_LOG):
        with open(_ALERT_LOG, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=_LOG_COLS).writeheader()


def _was_recently_alerted(listing_id: str, alert_type: str, window_secs: int = 3600) -> bool:
    """Return True if this (listing_id, alert_type) was sent within window_secs."""
    if not listing_id:
        return False
    try:
        _ensure_log()
        cutoff = time.time() - window_secs
        with open(_ALERT_LOG, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("listing_id") != listing_id:
                    continue
                if row.get("alert_type") != alert_type:
                    continue
                try:
                    ts = float(row.get("timestamp", 0) or 0)
                    if ts > cutoff:
                        return True
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass
    return False


def _log_alert(
    alert_type: str,
    listing_id: str,
    player: str,
    card_description: str,
    message_sent: str,
) -> None:
    try:
        _ensure_log()
        with open(_ALERT_LOG, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_LOG_COLS)
            writer.writerow({
                "timestamp":        time.time(),
                "alert_type":       alert_type,
                "listing_id":       listing_id,
                "player":           player,
                "card_description": card_description[:120],
                "message_sent":     message_sent[:300],
            })
    except Exception as exc:
        print(f"[ALERTS] Could not write alert log: {exc}")


# ---------------------------------------------------------------------------
# Quiet hours check
# ---------------------------------------------------------------------------

def _in_quiet_hours(settings: Dict[str, Any]) -> bool:
    """Return True if current local time is inside the user's quiet window."""
    if not settings.get("quiet_hours_enabled"):
        return False
    try:
        now_t = datetime.now().time()
        start_str = str(settings.get("quiet_start") or "22:00")
        end_str   = str(settings.get("quiet_end")   or "08:00")
        h_s, m_s  = map(int, start_str.split(":"))
        h_e, m_e  = map(int, end_str.split(":"))
        from datetime import time as _time
        start_t = _time(h_s, m_s)
        end_t   = _time(h_e, m_e)
        if start_t <= end_t:
            return start_t <= now_t <= end_t
        else:
            # Wraps midnight: quiet if after start OR before end
            return now_t >= start_t or now_t <= end_t
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Deal class order gate
# ---------------------------------------------------------------------------

_CLASS_ORDER = {"ELITE": 4, "STRONG": 3, "GOOD": 2, "WEAK": 1, "PASS": 0}

def _passes_min_class(deal_class: str, settings: Dict[str, Any]) -> bool:
    min_c = str(settings.get("min_deal_class") or "ELITE").upper()
    dc    = str(deal_class or "").upper()
    return _CLASS_ORDER.get(dc, 0) >= _CLASS_ORDER.get(min_c, 4)


# ---------------------------------------------------------------------------
# Core send function
# ---------------------------------------------------------------------------

def _send(
    title: str,
    message: str,
    priority: int,            # 1 = high (breaks DND), 0 = normal
    sound: str,
    alert_type: str,
    listing_id: str,
    player: str,
    card_description: str,
    is_high_priority: bool = False,
) -> bool:
    """
    Send a Pushover notification.

    HIGH priority (is_high_priority=True) bypasses quiet hours — these use
    Pushover priority 1 which breaks through phone Do Not Disturb.
    NORMAL priority respects quiet hours.

    Returns True on success, False on any failure (never raises).
    """
    settings = load_alert_settings()

    if not settings.get("enabled", True):
        return False

    # Check alert type toggle
    atype_key = alert_type.replace("-", "_").lower()
    if not settings.get("alert_types", {}).get(atype_key, True):
        return False

    # Quiet hours — only NORMAL priority respects them
    if not is_high_priority and _in_quiet_hours(settings):
        print(f"[ALERTS] Suppressed (quiet hours): {alert_type}")
        return False

    # Deduplication
    if _was_recently_alerted(listing_id, alert_type):
        print(f"[ALERTS] Deduplicated (1h): {alert_type} {listing_id}")
        return False

    if not _credentials_ok():
        print("[ALERTS] Missing PUSHOVER_USER_KEY or PUSHOVER_API_TOKEN — skipping alert.")
        return False

    PushoverAPI = _get_pushover_api()
    if PushoverAPI is None:
        print("[ALERTS] Could not load PushoverAPI — skipping alert.")
        return False

    user_key, api_token = _get_credentials()
    try:
        p = PushoverAPI(api_token)
        p.send_message(
            user_key,
            message,
            title=title,
            priority=priority,
            sound=sound,
        )
        print(f"[ALERTS] Sent {alert_type}: {title}")
        _log_alert(alert_type, listing_id, player, card_description, message)
        return True
    except Exception as exc:
        print(f"[ALERTS] Pushover API error ({alert_type}): {exc}")
        _log_alert(alert_type, listing_id, player, card_description, f"ERROR: {exc}")
        return False


# ---------------------------------------------------------------------------
# Public alert functions
# ---------------------------------------------------------------------------

def alert_elite_deal(deal: Dict[str, Any]) -> None:
    """
    Call when an ELITE deal is found in Ending Soon or Auto-Buyer scan.
    deal dict keys: player_name, title, current_price, market_value, snipe_bid,
                    seconds_remaining, item_id
    """
    settings = load_alert_settings()
    if not settings.get("alert_types", {}).get("elite_deal", True):
        return
    if not _passes_min_class("ELITE", settings):
        return

    player  = str(deal.get("player_name") or "Unknown")
    title_s = str(deal.get("title") or "")[:60]
    price   = float(deal.get("current_price") or 0)
    mv      = float(deal.get("market_value") or 0)
    bid     = float(deal.get("snipe_bid") or 0)
    secs    = deal.get("seconds_remaining")
    iid     = str(deal.get("item_id") or "")

    if secs is not None and secs > 0:
        h, rem = divmod(int(secs), 3600)
        m, s   = divmod(rem, 60)
        time_s = f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"
    else:
        time_s = "ending soon"

    msg = (
        f"{title_s} | "
        f"Current: ${price:.2f} | "
        f"MV: ${mv:.2f} | "
        f"Snipe: ${bid:.2f} | "
        f"{time_s} left"
    )

    _send(
        title            = f"🚨 ELITE DEAL — {player}",
        message          = msg,
        priority         = 1,
        sound            = "pushover",
        alert_type       = "elite_deal",
        listing_id       = iid,
        player           = player,
        card_description = title_s,
        is_high_priority = True,
    )


def alert_bin_deal(alert: Dict[str, Any]) -> None:
    """
    Call when a BIN listing is found below 70% MV.
    alert dict keys: player_name, title, bin_price, market_value, edge_pct, item_id
    """
    settings = load_alert_settings()
    if not settings.get("alert_types", {}).get("bin_alert", True):
        return

    player   = str(alert.get("player_name") or "Unknown")
    title_s  = str(alert.get("title") or "")[:60]
    bin_p    = float(alert.get("bin_price") or 0)
    mv       = float(alert.get("market_value") or 0)
    iid      = str(alert.get("item_id") or "")
    pct_below = round((1 - bin_p / mv) * 100, 1) if mv > 0 else 0.0

    msg = (
        f"{title_s} | "
        f"BIN: ${bin_p:.2f} | "
        f"MV: ${mv:.2f} | "
        f"{pct_below}% below market"
    )

    _send(
        title            = f"💰 BIN ALERT — {player}",
        message          = msg,
        priority         = 1,
        sound            = "pushover",
        alert_type       = "bin_alert",
        listing_id       = iid,
        player           = player,
        card_description = title_s,
        is_high_priority = True,
    )


def alert_snipe_won(item: Dict[str, Any]) -> None:
    """
    Call after a successful snipe bid is placed.
    item dict keys: player_name, title, snipe_bid, market_value, item_id
    """
    settings = load_alert_settings()
    if not settings.get("alert_types", {}).get("snipe_won", True):
        return

    player  = str(item.get("player_name") or "Unknown")
    title_s = str(item.get("title") or "")[:60]
    bid     = float(item.get("snipe_bid") or 0)
    mv      = float(item.get("market_value") or 0)
    iid     = str(item.get("item_id") or "")

    msg = (
        f"{title_s} | "
        f"Bid: ${bid:.2f} | "
        f"MV: ${mv:.2f}"
    )

    _send(
        title            = f"✅ SNIPE PLACED — {player}",
        message          = msg,
        priority         = 0,
        sound            = "pushover",
        alert_type       = "snipe_won",
        listing_id       = iid,
        player           = player,
        card_description = title_s,
    )


def alert_session_complete(state: Dict[str, Any]) -> None:
    """
    Call when auto-buyer session hits total budget limit.
    state: _STATE dict from auto_buyer_engine
    """
    settings = load_alert_settings()
    if not settings.get("alert_types", {}).get("session_complete", True):
        return

    config       = state.get("config") or {}
    spent_dict   = state.get("spent") or {}
    total_spent  = sum(float(v) for v in spent_dict.values())
    total_budget = float(config.get("budget") or 0)
    cards        = int(state.get("bids_won") or 0)
    session_id   = str(state.get("session_id") or "")

    # Avg discount
    completed = state.get("completed") or []
    discounts = []
    for c in completed:
        mv  = float(c.get("market_value") or 0)
        bid = float(c.get("amount_paid") or 0)
        if mv > 0:
            discounts.append((mv - bid) / mv * 100)
    avg_discount = round(sum(discounts) / len(discounts), 1) if discounts else 0.0

    msg = (
        f"Spent: ${total_spent:.2f} of ${total_budget:.2f} | "
        f"Cards: {cards} | "
        f"Avg discount: {avg_discount}%"
    )

    _send(
        title            = "🏁 SESSION COMPLETE",
        message          = msg,
        priority         = 0,
        sound            = "pushover",
        alert_type       = "session_complete",
        listing_id       = session_id,
        player           = "",
        card_description = "",
    )


def alert_budget_warning(state: Dict[str, Any]) -> None:
    """
    Call when auto-buyer hits 80% of total budget.
    state: _STATE dict from auto_buyer_engine
    """
    settings = load_alert_settings()
    if not settings.get("alert_types", {}).get("budget_warning", True):
        return

    config       = state.get("config") or {}
    spent_dict   = state.get("spent") or {}
    total_spent  = sum(float(v) for v in spent_dict.values())
    total_budget = float(config.get("budget") or 0)
    cards        = int(state.get("bids_won") or 0)
    session_id   = str(state.get("session_id") or "")

    msg = (
        f"${total_spent:.2f} of ${total_budget:.2f} used | "
        f"{cards} cards bought"
    )

    _send(
        title            = "⚠️ BUDGET 80% USED",
        message          = msg,
        priority         = 0,
        sound            = "pushover",
        alert_type       = "budget_warning",
        listing_id       = f"budget_{session_id}",
        player           = "",
        card_description = "",
    )


def send_test_alert() -> bool:
    """Send a test Pushover notification. Returns True on success."""
    if not _credentials_ok():
        print("[ALERTS] Cannot send test — missing credentials.")
        return False

    PushoverAPI = _get_pushover_api()
    if PushoverAPI is None:
        return False

    user_key, api_token = _get_credentials()
    try:
        p = PushoverAPI(api_token)
        p.send_message(
            user_key,
            "Your eBay card alert system is working. 🎉",
            title="✅ Test Alert — eBay Sniper",
            priority=0,
            sound="pushover",
        )
        print("[ALERTS] Test alert sent successfully.")
        return True
    except Exception as exc:
        print(f"[ALERTS] Test alert failed: {exc}")
        return False
