"""
Auto-Buyer Engine — pure backend, no Streamlit.

Thread-safe module-level state. Background thread handles:
  - Full scan every 10 minutes (auctions via ending_soon_engine + BIN search)
  - Snipe scheduler: ticks every second, fires bids at the 7-minute mark
  - BIN alert expiry after 10 minutes
  - Budget enforcement and reallocation

Integrates with existing engines:
  ending_soon_engine.fetch_ending_soon_deals()
  comp_engine_v2.get_market_value_for_item()  — sole MV source (sold listings via Finding API)
  ebay_bid.place_bid()
"""
from __future__ import annotations

import csv
import os
import threading
import time
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import requests

import ebay_bid
import ebay_search
import ending_soon_engine
import comp_engine_v2 as _cev2
import alerts as _alerts

# ── Paths ──────────────────────────────────────────────────────────────────────
_HERE            = os.path.dirname(os.path.abspath(__file__))
SESSION_LOGS_DIR = os.path.join(_HERE, "session_logs")
AUTO_BUYER_LOG   = os.path.join(SESSION_LOGS_DIR, "auto_buyer_log.csv")
os.makedirs(SESSION_LOGS_DIR, exist_ok=True)

# ── CSV columns ────────────────────────────────────────────────────────────────
_LOG_COLS = [
    "timestamp", "session_id", "action_type", "player", "card_description",
    "listing_id", "current_price", "market_value", "snipe_bid", "sport",
    "deal_score", "velocity_tier", "result", "error_message",
]

# ── Deal class ordering ────────────────────────────────────────────────────────
_DEAL_ORDER: Dict[str, int] = {
    "ELITE": 4, "STRONG": 3, "GOOD": 2, "WEAK": 1,
    "PASS": 0, "UNKNOWN": 0, "LOW_CONFIDENCE": 0,
}

# ── Timing constants ───────────────────────────────────────────────────────────
SCAN_INTERVAL_SECS = 600   # 10 minutes between scans
BIN_ALERT_TTL_SECS = 600   # BIN alert expires after 10 minutes
SNIPE_FIRE_WINDOW  = 480   # 8 min: if ending within this, bid immediately
SNIPE_FIRE_AT_SECS = 420   # 7 min: schedule snipe to fire at this mark
RATE_LIMIT_PAUSE   = 60    # wait 60 s after rate-limit hit

# ── Module-level shared state ──────────────────────────────────────────────────
_STATE_LOCK = threading.Lock()
_LOG_LOCK   = threading.Lock()

_EMPTY_STATE: Dict[str, Any] = {
    "status":              "idle",
    "session_id":          None,
    "config":              {},
    "spent":               {"NFL": 0.0, "MLB": 0.0, "NBA": 0.0},
    "budget_hit":          [],
    "reallocated_budget":  {},
    "snipe_queue":         [],
    "bin_alerts":          [],
    "completed":           [],
    "flagged":             [],
    "bids_placed":         0,
    "bids_won":            0,
    "last_scan_ts":        0.0,
    "next_scan_ts":        0.0,
    "scan_count":          0,
    "rate_limited_until":  0.0,
    "errors_this_scan":       0,
    "last_error":             "",
    "_budget_80pct_alerted":  False,
}

_STATE: Dict[str, Any]   = deepcopy(_EMPTY_STATE)
_BID_PLACED_IDS: Set[str] = set()
_SCAN_THREAD: Optional[threading.Thread] = None
_STOP_EVENT = threading.Event()


# ══════════════════════════════════════════════════════════════════════════════
# Public API  (UI thread calls these)
# ══════════════════════════════════════════════════════════════════════════════

def get_session_snapshot() -> Dict[str, Any]:
    """Thread-safe deep copy of current engine state for the UI to render."""
    with _STATE_LOCK:
        return deepcopy(_STATE)


def start_session(config: Dict[str, Any]) -> str:
    """
    Initialise a new session and start the background engine thread.

    config keys:
      budget (float)
      sport_allocs (dict: {"NFL": 40, "MLB": 40, "NBA": 20})
      snipe_pct (float: 0.50–0.90)
      min_deal_class (str: "GOOD" | "STRONG" | "ELITE")

    Returns the session_id string.
    """
    global _SCAN_THREAD, _STATE, _BID_PLACED_IDS

    session_id = datetime.now().strftime("%Y%m%d-%H%M%S")

    with _STATE_LOCK:
        _STATE = deepcopy(_EMPTY_STATE)
        _STATE["status"]        = "running"
        _STATE["session_id"]    = session_id
        _STATE["config"]        = deepcopy(config)
        _STATE["next_scan_ts"]  = time.time()          # scan immediately on start
        _BID_PLACED_IDS.clear()

    _STOP_EVENT.clear()
    _SCAN_THREAD = threading.Thread(
        target=_engine_loop,
        daemon=True,
        name="auto_buyer_engine",
    )
    _SCAN_THREAD.start()
    return session_id


def stop_session() -> None:
    """Signal the background engine to stop."""
    _STOP_EVENT.set()
    with _STATE_LOCK:
        if _STATE["status"] == "running":
            _STATE["status"] = "complete"


def add_budget(amount: float) -> None:
    """Add dollars to the current session and resume if budget-stopped."""
    with _STATE_LOCK:
        _STATE["config"]["budget"] = float(_STATE["config"].get("budget", 0)) + float(amount)
        if _STATE["status"] == "complete" and _total_budget_remaining(_STATE) > 0:
            _STATE["status"] = "running"
            _STOP_EVENT.clear()
            # Restart background thread if it died
            global _SCAN_THREAD
            if _SCAN_THREAD is None or not _SCAN_THREAD.is_alive():
                _SCAN_THREAD = threading.Thread(
                    target=_engine_loop, daemon=True, name="auto_buyer_engine"
                )
                _SCAN_THREAD.start()


def dismiss_flagged(item_id: str) -> None:
    """Remove an item from the flagged list (user action)."""
    with _STATE_LOCK:
        _STATE["flagged"] = [
            f for f in _STATE["flagged"] if f.get("item_id") != item_id
        ]


def is_running() -> bool:
    return (
        _STATE.get("status") == "running"
        and _SCAN_THREAD is not None
        and _SCAN_THREAD.is_alive()
    )


# ══════════════════════════════════════════════════════════════════════════════
# Budget helpers  (called from background thread — no lock needed for reads)
# ══════════════════════════════════════════════════════════════════════════════

def _sport_budget(state: Dict[str, Any], sport: str) -> float:
    config = state["config"]
    total  = float(config.get("budget", 0))
    pct    = float((config.get("sport_allocs") or {}).get(sport, 0)) / 100.0
    base   = total * pct
    extra  = float((state.get("reallocated_budget") or {}).get(sport, 0))
    return round(base + extra, 2)


def _sport_budget_remaining(state: Dict[str, Any], sport: str) -> float:
    spent = float((state.get("spent") or {}).get(sport, 0))
    return round(_sport_budget(state, sport) - spent, 2)


def _total_budget_remaining(state: Dict[str, Any]) -> float:
    total = float(state["config"].get("budget", 0))
    spent = sum(float(v) for v in (state.get("spent") or {}).values())
    return round(total - spent, 2)


def _check_and_update_budget_hit(state: Dict[str, Any]) -> None:
    """
    Update budget_hit list. Reallocate a newly-hit sport's remaining budget
    evenly across sports that still have headroom.
    """
    sports   = ["NFL", "MLB", "NBA"]
    hit_list = list(state.get("budget_hit") or [])
    newly_hit: List[str] = []

    for sport in sports:
        if sport in hit_list:
            continue
        if _sport_budget_remaining(state, sport) <= 0.01:
            hit_list.append(sport)
            newly_hit.append(sport)

    state["budget_hit"] = hit_list

    # Reallocate
    for sport in newly_hit:
        remaining_sports = [s for s in sports if s not in hit_list]
        if not remaining_sports:
            continue
        leftover = _sport_budget(state, sport) - float((state.get("spent") or {}).get(sport, 0))
        if leftover <= 0:
            continue
        per_sport = leftover / len(remaining_sports)
        realloc = state.setdefault("reallocated_budget", {})
        for s in remaining_sports:
            realloc[s] = float(realloc.get(s, 0)) + per_sport
        _log_action(
            session_id=state.get("session_id", ""),
            action_type="budget_hit",
            player="", card_desc="", listing_id="",
            current_price=0, market_value=0, snipe_bid=0,
            sport=sport, deal_score=0, tier=0,
            result=f"reallocated ${leftover:.2f} to {remaining_sports}",
            error="",
        )

    # Budget 80% warning (fire once per session)
    total_budget = float(state["config"].get("budget") or 0)
    if total_budget > 0 and not state.get("_budget_80pct_alerted"):
        total_spent = sum(float(v) for v in (state.get("spent") or {}).values())
        if total_spent / total_budget >= 0.80:
            state["_budget_80pct_alerted"] = True
            try:
                _alerts.alert_budget_warning(state)
            except Exception:
                pass

    # Stop session if total budget exhausted
    if _total_budget_remaining(state) <= 0.01:
        state["status"] = "complete"
        _STOP_EVENT.set()
        _log_action(
            session_id=state.get("session_id", ""),
            action_type="budget_hit",
            player="", card_desc="", listing_id="",
            current_price=0, market_value=0, snipe_bid=0,
            sport="ALL", deal_score=0, tier=0,
            result="total_budget_reached", error="",
        )
        try:
            _alerts.alert_session_complete(state)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# Priority queue
# ══════════════════════════════════════════════════════════════════════════════

def _get_deal_priority(tier: int, deal_class: str) -> Optional[int]:
    """
    Returns priority 1-4 or None (do not auto-buy).
    1 = ELITE (any tier) — always first
    2 = Tier 1 STRONG or GOOD
    3 = Tier 2 STRONG
    4 = Tier 3 STRONG
    """
    dc = deal_class.upper()
    if dc == "ELITE":
        return 1
    if tier == 1 and dc in ("STRONG", "GOOD"):
        return 2
    if tier == 2 and dc == "STRONG":
        return 3
    if tier == 3 and dc == "STRONG":
        return 4
    return None


def _build_priority_queue(
    deals: List[Dict[str, Any]],
    state: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Filter deals and return action-ready list sorted by priority."""
    # IDs already in queue, completed, or flagged
    actioned: Set[str] = set()
    for group in ("snipe_queue", "completed", "flagged"):
        for item in state.get(group) or []:
            iid = str(item.get("item_id") or "")
            if iid:
                actioned.add(iid)

    min_class = str(state["config"].get("min_deal_class", "GOOD")).upper()
    min_order = _DEAL_ORDER.get(min_class, 2)
    hit_sports = set(state.get("budget_hit") or [])

    queued: List[Dict[str, Any]] = []

    for deal in deals:
        iid = str(deal.get("item_id") or "")
        if not iid or iid in actioned or iid in _BID_PLACED_IDS:
            continue

        sport = str(deal.get("sport") or "").upper()
        if sport in hit_sports:
            continue

        # Never auto-snipe insufficient data or low confidence
        if deal.get("insufficient_data", False):
            continue
        mv_confidence = str(deal.get("mv_confidence") or deal.get("confidence") or "").upper()
        if mv_confidence == "LOW":
            continue

        dc    = str(deal.get("deal_class") or "").upper()
        order = _DEAL_ORDER.get(dc, 0)
        if order < min_order:
            continue

        tier = int(deal.get("whatnot_tier") or 3)
        pri  = _get_deal_priority(tier, dc)
        if pri is None:
            continue

        # Check budget
        mv        = float(deal.get("market_value") or 0)
        snipe_pct = float(state["config"].get("snipe_pct", 0.70))
        snipe_bid = round(mv * snipe_pct, 2) if mv > 0 else 0.0
        budget_rem = _sport_budget_remaining(state, sport)

        if snipe_bid <= 0 or budget_rem < snipe_bid:
            continue
        if float(deal.get("current_price") or 0) > snipe_bid:
            continue

        queued.append({
            **deal,
            "snipe_bid":    snipe_bid,
            "_priority":    pri,
            "_budget_rem":  budget_rem,
            "mv_confidence": mv_confidence,
        })

    # Sort: priority → sport budget remaining desc → soonest ending
    queued.sort(key=lambda x: (
        x["_priority"],
        -x["_budget_rem"],
        x.get("seconds_remaining") or float("inf"),
    ))

    return queued


# ══════════════════════════════════════════════════════════════════════════════
# BIN search
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_bin_items_for_spec(spec: Dict[str, Any], limit: int = 20) -> List[Dict[str, Any]]:
    """Call eBay Browse API for FIXED_PRICE listings matching a player spec."""
    try:
        token = ebay_search._get_application_access_token_str()
    except Exception:
        return []

    url     = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    headers = {
        "Authorization":           f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": ebay_search.EBAY_MARKETPLACE_ID,
    }
    params = {
        "q": spec["query"],
        "filter": (
            f"buyingOptions:{{FIXED_PRICE}},"
            f"price:[{ending_soon_engine.MIN_PRICE:.0f}..{ending_soon_engine.MAX_PRICE:.0f}],"
            f"priceCurrency:USD"
        ),
        "limit": limit,
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=20)
    except requests.RequestException:
        return []

    if resp.status_code != 200:
        return []

    try:
        items = resp.json().get("itemSummaries") or []
    except Exception:
        return []

    out: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        opts = item.get("buyingOptions") or []
        if "FIXED_PRICE" not in opts and "BUY_IT_NOW" not in opts:
            continue
        title = str(item.get("title") or "")
        if not ending_soon_engine._passes_card_type_filter(title):
            continue
        price_obj = item.get("price") or {}
        try:
            price = float(str(price_obj.get("value") or 0).replace(",", ""))
        except (ValueError, TypeError):
            price = 0.0
        if not (ending_soon_engine.MIN_PRICE <= price <= ending_soon_engine.MAX_PRICE):
            continue
        out.append({
            "item_id":      str(item.get("itemId") or ""),
            "title":        title,
            "bin_price":    price,
            "url":          str(item.get("itemWebUrl") or ""),
            "player_name":  spec["player_name"],
            "sport":        spec["sport"],
            "whatnot_tier": spec["whatnot_tier"],
        })

    return out


def _scan_bin_deals(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Search all players for BIN listings below snipe_pct × market_value.
    Returns list of new bin_alert dicts (deduped against existing alerts).
    """
    snipe_pct      = float(state["config"].get("snipe_pct", 0.70))
    existing_ids   = {a["item_id"] for a in state.get("bin_alerts") or []}
    specs          = ending_soon_engine._build_query_specs()
    alerts: List[Dict[str, Any]] = []
    mv_done        = 0
    max_mv         = ending_soon_engine.MAX_MV_COMPUTATIONS

    for spec in specs:
        try:
            bin_items = _fetch_bin_items_for_spec(spec)
        except Exception:
            continue

        for item in bin_items:
            iid = item["item_id"]
            if not iid or iid in existing_ids or iid in _BID_PLACED_IDS:
                continue
            if mv_done >= max_mv:
                break

            try:
                mv_data = _cev2.get_market_value_for_item(item["title"])
                mv_done += 1
            except Exception:
                continue

            mv           = mv_data.get("market_value")
            insufficient = mv_data.get("insufficient_data", True)
            confidence   = mv_data.get("confidence", "LOW")
            if not mv or insufficient or confidence == "LOW":
                continue

            threshold = snipe_pct * mv
            if item["bin_price"] > threshold:
                continue

            edge_pct = round((mv - item["bin_price"]) / mv * 100, 1)
            now      = time.time()
            alerts.append({
                "item_id":      iid,
                "player_name":  item["player_name"],
                "sport":        item["sport"],
                "whatnot_tier": item["whatnot_tier"],
                "title":        item["title"],
                "bin_price":    item["bin_price"],
                "market_value": mv,
                "edge_pct":     edge_pct,
                "url":          item["url"],
                "found_at":     now,
                "expires_at":   now + BIN_ALERT_TTL_SECS,
            })

    return alerts


# ══════════════════════════════════════════════════════════════════════════════
# Snipe execution
# ══════════════════════════════════════════════════════════════════════════════

def _execute_snipe(item: Dict[str, Any]) -> None:
    """
    Place a bid and record the result.
    Called from background thread WITHOUT holding _STATE_LOCK.
    """
    iid       = str(item.get("item_id") or "")
    snipe_bid = float(item.get("snipe_bid") or 0)
    sport     = str(item.get("sport") or "").upper()

    if not iid or snipe_bid <= 0:
        return

    # Mark as bid-placed before API call so parallel ticks don't double-bid
    _BID_PLACED_IDS.add(iid)

    result    = ebay_bid.place_bid(iid, snipe_bid)
    now_str   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    _log_action(
        session_id    = _STATE.get("session_id", ""),
        action_type   = "snipe_placed",
        player        = item.get("player_name", ""),
        card_desc     = item.get("title", "")[:100],
        listing_id    = iid,
        current_price = float(item.get("current_price") or 0),
        market_value  = float(item.get("market_value") or 0),
        snipe_bid     = snipe_bid,
        sport         = sport,
        deal_score    = int(item.get("deal_score") or 0),
        tier          = int(item.get("whatnot_tier") or 3),
        result        = "placed" if result["success"] else "failed",
        error         = "" if result["success"] else result.get("message", ""),
    )

    if result["success"]:
        auction_status = (result.get("raw_response") or {}).get("auctionStatus", "WINNING")

        if auction_status in ("WINNING", "WON", ""):
            with _STATE_LOCK:
                _STATE["bids_placed"] += 1
                _STATE["bids_won"]    += 1
                _STATE["spent"][sport] = round(
                    float(_STATE["spent"].get(sport, 0)) + snipe_bid, 2
                )
                _STATE["completed"].append({
                    **item,
                    "amount_paid":    snipe_bid,
                    "auction_status": auction_status,
                    "timestamp":      now_str,
                })
                _check_and_update_budget_hit(_STATE)

            try:
                _alerts.alert_snipe_won(item)
            except Exception:
                pass

            _log_action(
                session_id=_STATE.get("session_id", ""), action_type="snipe_won",
                player=item.get("player_name", ""), card_desc=item.get("title", "")[:100],
                listing_id=iid, current_price=float(item.get("current_price") or 0),
                market_value=float(item.get("market_value") or 0),
                snipe_bid=snipe_bid, sport=sport,
                deal_score=int(item.get("deal_score") or 0),
                tier=int(item.get("whatnot_tier") or 3),
                result="won", error="",
            )

        elif auction_status == "OUTBID":
            with _STATE_LOCK:
                _STATE["bids_placed"] += 1
                _STATE["flagged"].append({
                    **item, "reason": "outbid", "timestamp": now_str,
                })
            _log_action(
                session_id=_STATE.get("session_id", ""), action_type="snipe_lost",
                player=item.get("player_name", ""), card_desc=item.get("title", "")[:100],
                listing_id=iid, current_price=float(item.get("current_price") or 0),
                market_value=float(item.get("market_value") or 0),
                snipe_bid=snipe_bid, sport=sport,
                deal_score=int(item.get("deal_score") or 0),
                tier=int(item.get("whatnot_tier") or 3),
                result="outbid", error="",
            )
    else:
        with _STATE_LOCK:
            _STATE["flagged"].append({
                **item,
                "reason":        "api_error",
                "error_message": result.get("message", ""),
                "timestamp":     now_str,
            })
        _log_action(
            session_id=_STATE.get("session_id", ""), action_type="error",
            player=item.get("player_name", ""), card_desc=item.get("title", "")[:100],
            listing_id=iid, current_price=float(item.get("current_price") or 0),
            market_value=float(item.get("market_value") or 0),
            snipe_bid=snipe_bid, sport=sport,
            deal_score=int(item.get("deal_score") or 0),
            tier=int(item.get("whatnot_tier") or 3),
            result="error", error=result.get("message", ""),
        )


# ══════════════════════════════════════════════════════════════════════════════
# Full scan
# ══════════════════════════════════════════════════════════════════════════════

def _run_scan() -> None:
    """
    Full scan pipeline: fetch auctions + BIN, score, enqueue/fire snipes.
    Runs in background thread. Does NOT hold _STATE_LOCK during network calls.
    """
    now = time.time()

    # Snapshot config without holding lock during network calls
    with _STATE_LOCK:
        config    = deepcopy(_STATE.get("config") or {})
        session_id = _STATE.get("session_id", "")

    snipe_pct  = float(config.get("snipe_pct", 0.70))
    min_class  = str(config.get("min_deal_class", "GOOD")).upper()
    min_order  = _DEAL_ORDER.get(min_class, 2)

    # ── 1. Fetch auction deals ─────────────────────────────────────────────
    try:
        deals, meta = ending_soon_engine.fetch_ending_soon_deals(
            force_refresh=True,
            min_deal_classes=["ELITE", "STRONG", "GOOD"],
        )
    except Exception as exc:
        with _STATE_LOCK:
            _STATE["errors_this_scan"] = _STATE.get("errors_this_scan", 0) + 1
            _STATE["last_error"]       = str(exc)[:200]
        _log_action(
            session_id=session_id, action_type="error",
            player="", card_desc="scan_fetch_failed", listing_id="",
            current_price=0, market_value=0, snipe_bid=0,
            sport="", deal_score=0, tier=0, result="error", error=str(exc)[:200],
        )
        return

    # Rate-limit signal from ending_soon_engine
    if meta.get("rate_limited"):
        with _STATE_LOCK:
            _STATE["rate_limited_until"] = now + RATE_LIMIT_PAUSE
        _log_action(
            session_id=session_id, action_type="error",
            player="", card_desc="rate_limited", listing_id="",
            current_price=0, market_value=0, snipe_bid=0,
            sport="", deal_score=0, tier=0,
            result="rate_limited", error="eBay rate limit; pausing scan 60s",
        )
        return

    # ── 2. BIN scan ────────────────────────────────────────────────────────
    with _STATE_LOCK:
        state_snap = deepcopy(_STATE)

    try:
        new_bin_alerts = _scan_bin_deals(state_snap)
    except Exception:
        new_bin_alerts = []

    # ── 3. Build priority queue ────────────────────────────────────────────
    with _STATE_LOCK:
        state_snap = deepcopy(_STATE)

    priority_queue = _build_priority_queue(deals, state_snap)

    # ── 3a. ELITE deal alerts ──────────────────────────────────────────────
    for deal in priority_queue:
        if str(deal.get("deal_class") or "").upper() == "ELITE":
            try:
                _alerts.alert_elite_deal(deal)
            except Exception:
                pass

    # ── 4. Schedule / fire snipes ──────────────────────────────────────────
    for deal in priority_queue:
        iid = str(deal.get("item_id") or "")
        if not iid or iid in _BID_PLACED_IDS:
            continue

        secs      = float(deal.get("seconds_remaining") or 0)
        snipe_bid = deal.get("snipe_bid") or 0.0

        if snipe_bid <= 0:
            continue

        if secs <= SNIPE_FIRE_WINDOW:
            # Ending within 8 min — bid immediately
            _execute_snipe(deal)
        else:
            # Schedule to fire at 7-minute mark
            fire_at = now + secs - SNIPE_FIRE_AT_SECS
            if fire_at <= now:
                _execute_snipe(deal)
                continue

            with _STATE_LOCK:
                already = any(
                    q.get("item_id") == iid for q in _STATE["snipe_queue"]
                )
                if not already:
                    _STATE["snipe_queue"].append({
                        **deal,
                        "fire_at":      fire_at,
                        "scheduled_at": now,
                    })

    # ── 5. Merge new BIN alerts ────────────────────────────────────────────
    with _STATE_LOCK:
        existing_bin_ids = {a["item_id"] for a in _STATE["bin_alerts"]}
        for alert in new_bin_alerts:
            if alert["item_id"] not in existing_bin_ids:
                _STATE["bin_alerts"].append(alert)
                try:
                    _alerts.alert_bin_deal(alert)
                except Exception:
                    pass
                _log_action(
                    session_id=session_id, action_type="bin_alert",
                    player=alert["player_name"], card_desc=alert["title"][:100],
                    listing_id=alert["item_id"], current_price=alert["bin_price"],
                    market_value=alert["market_value"], snipe_bid=0,
                    sport=alert["sport"], deal_score=0, tier=alert["whatnot_tier"],
                    result="alerted", error="",
                )

    # ── 6. Update scan metadata ────────────────────────────────────────────
    with _STATE_LOCK:
        _STATE["last_scan_ts"]   = now
        _STATE["next_scan_ts"]   = now + SCAN_INTERVAL_SECS
        _STATE["scan_count"]     = _STATE.get("scan_count", 0) + 1
        _STATE["errors_this_scan"] = 0


# ══════════════════════════════════════════════════════════════════════════════
# Background engine loop
# ══════════════════════════════════════════════════════════════════════════════

def _engine_loop() -> None:
    """
    Main background thread.
    Ticks every 1 second:
      - Fires scheduled snipes whose fire_at <= now
      - Expires BIN alerts past their TTL
      - Triggers full scan when next_scan_ts <= now
    """
    while not _STOP_EVENT.is_set():
        now = time.time()

        with _STATE_LOCK:
            status        = _STATE.get("status")
            rl_until      = float(_STATE.get("rate_limited_until") or 0)
            next_scan     = float(_STATE.get("next_scan_ts") or 0)

        if status != "running":
            time.sleep(1)
            continue

        if rl_until > now:
            time.sleep(1)
            continue

        # ── Fire scheduled snipes ──────────────────────────────────────────
        to_fire: List[Dict[str, Any]] = []
        with _STATE_LOCK:
            remaining: List[Dict[str, Any]] = []
            for item in _STATE["snipe_queue"]:
                iid     = str(item.get("item_id") or "")
                fire_at = float(item.get("fire_at") or 0)
                if iid in _BID_PLACED_IDS:
                    continue
                if fire_at <= now:
                    to_fire.append(item)
                else:
                    remaining.append(item)
            _STATE["snipe_queue"] = remaining

        for item in to_fire:
            _execute_snipe(item)

        # ── Expire BIN alerts ──────────────────────────────────────────────
        with _STATE_LOCK:
            _STATE["bin_alerts"] = [
                a for a in _STATE["bin_alerts"]
                if float(a.get("expires_at") or 0) > now
            ]

        # ── Full scan ──────────────────────────────────────────────────────
        if now >= next_scan:
            _run_scan()

        time.sleep(1)


# ══════════════════════════════════════════════════════════════════════════════
# CSV logging
# ══════════════════════════════════════════════════════════════════════════════

def _log_action(
    *,
    session_id: str,
    action_type: str,
    player: str,
    card_desc: str,
    listing_id: str,
    current_price: float,
    market_value: float,
    snipe_bid: float,
    sport: str,
    deal_score: int,
    tier: int,
    result: str,
    error: str,
) -> None:
    row = {
        "timestamp":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "session_id":       session_id,
        "action_type":      action_type,
        "player":           player,
        "card_description": card_desc,
        "listing_id":       listing_id,
        "current_price":    f"{current_price:.2f}",
        "market_value":     f"{market_value:.2f}" if market_value else "",
        "snipe_bid":        f"{snipe_bid:.2f}" if snipe_bid else "",
        "sport":            sport,
        "deal_score":       deal_score,
        "velocity_tier":    f"Tier {tier}" if tier else "",
        "result":           result,
        "error_message":    str(error)[:300],
    }
    file_exists = os.path.isfile(AUTO_BUYER_LOG)
    with _LOG_LOCK:
        with open(AUTO_BUYER_LOG, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_LOG_COLS)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)


# ══════════════════════════════════════════════════════════════════════════════
# Session summary
# ══════════════════════════════════════════════════════════════════════════════

def build_session_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    completed = state.get("completed") or []
    config    = state.get("config") or {}
    budget    = float(config.get("budget") or 0)

    total_spent = sum(float(state.get("spent", {}).get(s, 0)) for s in ("NFL", "MLB", "NBA"))
    cards_bought = len(completed)

    by_sport: Dict[str, Dict[str, Any]] = {}
    by_class: Dict[str, Dict[str, Any]] = {}
    discounts: List[float] = []

    for item in completed:
        sport = str(item.get("sport") or "?").upper()
        dc    = str(item.get("deal_class") or "?").upper()
        paid  = float(item.get("amount_paid") or 0)
        mv    = float(item.get("market_value") or 0)

        s = by_sport.setdefault(sport, {"count": 0, "spent": 0.0})
        s["count"] += 1
        s["spent"]  = round(s["spent"] + paid, 2)

        c = by_class.setdefault(dc, {"count": 0, "spent": 0.0})
        c["count"] += 1
        c["spent"]  = round(c["spent"] + paid, 2)

        if mv > 0 and paid > 0:
            discounts.append((mv - paid) / mv * 100)

    avg_discount = round(sum(discounts) / len(discounts), 1) if discounts else 0.0

    top_card = max(
        completed, key=lambda x: float(x.get("market_value") or 0), default=None
    )

    bids_placed = int(state.get("bids_placed") or 0)
    bids_won    = int(state.get("bids_won") or 0)
    win_rate    = round(bids_won / bids_placed * 100, 1) if bids_placed > 0 else 0.0

    all_bin_alerts = state.get("bin_alerts") or []
    # Count all that were ever found (including expired) by checking the log — simplification:
    # use current count as minimum
    bin_count = len(all_bin_alerts)

    return {
        "budget":            budget,
        "total_spent":       round(total_spent, 2),
        "cards_bought":      cards_bought,
        "by_sport":          by_sport,
        "by_class":          by_class,
        "avg_discount_pct":  avg_discount,
        "bin_alerts_count":  bin_count,
        "bids_placed":       bids_placed,
        "bids_won":          bids_won,
        "win_rate":          win_rate,
        "top_card":          top_card,
        "session_id":        state.get("session_id", ""),
        "scan_count":        int(state.get("scan_count") or 0),
    }
