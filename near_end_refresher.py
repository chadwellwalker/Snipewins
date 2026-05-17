"""
near_end_refresher.py — Tiered current_bid refresh for auctions approaching end.

Why this exists:
    daily_pool.py refreshes the full 24h window once per HOUR. Between
    refreshes, current_bid in the pool can be stale by 4x+ on hot auctions —
    observed 2026-05-17 on a Cam Ward Purple Mosaic /50 PSA 9: dashboard
    showed $24 while eBay was at $100 with 31 bids and 5 minutes left.
    For an auction-sniping tool, that's a critical bug.

What this does:
    Periodically reads daily_pool.json, picks items by time-to-end tier,
    and fires a single per-item Browse API getItem call to refresh
    current_price + bid_count. Writes the updated values back to the pool
    so pool_view's next render sees fresh prices.

Tiered cadence (configurable via env vars):
    - 1-6h out  → every 600s (10 min)
    - <1h out   → every 60s
    - <5min out → every 15s (effective floor = worker loop interval)

Persistence:
    SNIPEWINS_NEAR_END_STATE_PATH (default ./near_end_refresh_state.json,
    in production point at /data/near_end_refresh_state.json so the
    cadence + near-end budget survive redeploys)

    SNIPEWINS_NEAR_END_BUDGET (default 1500 calls/day). Separate counter
    from the main SNIPEWINS_DAILY_CALL_BUDGET so morning comp queries
    can't starve near-end price refreshes — the cards ending in the next
    hour are EXACTLY where we don't want to be choked.

Failure-quiet: never raises. Catches all exceptions and logs only.

Wiring:
    Worker calls near_end_refresher.run_once() once per cycle, right after
    email_drip. Cheap when no tier is due (cadence guards short-circuit
    immediately).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


HERE = Path(__file__).parent

# Match daily_pool.py's path discovery so we read/write the same file in
# both local-dev and Render (where /data is the persistent disk).
POOL_FILE = Path(
    os.environ.get("SNIPEWINS_AUCTION_POOL_PATH") or str(HERE / "daily_pool.json")
)

STATE_FILE = Path(
    os.environ.get("SNIPEWINS_NEAR_END_STATE_PATH")
    or str(HERE / "near_end_refresh_state.json")
)

# Separate near-end budget — 1500 calls/day default. Empirically:
#   TIER_3 worst case (10 cards in <5min for 5min straight, refreshed every
#   15s) = 10 cards × 20 cycles = 200 calls
#   TIER_2 typical (15 cards in <1h, refreshed every 60s) = 15 × 60 = 900 calls
#   TIER_1 typical (40 cards in 1-6h, refreshed every 600s) = 40 × 36 = 1440 calls
# Real load is well under these worst-case numbers because tiers narrow
# as auctions end. 1500/day gives plenty of headroom.
NEAR_END_BUDGET = int(os.environ.get("SNIPEWINS_NEAR_END_BUDGET") or 1500)

# Tier definitions: (min_secs_remaining, max_secs_remaining, refresh_interval_secs)
# Tier 3 is most aggressive — the last 5 minutes is when bidding spikes
# and any stale price matters most. Worker loop is 60s so 15s tier
# effectively refreshes once per worker cycle until we add a sub-loop.
TIER_3 = (0,           5  * 60,       15)
TIER_2 = (5  * 60,     60 * 60,       60)
TIER_1 = (60 * 60,     6  * 60 * 60,  600)
ALL_TIERS: Tuple[Tuple[int, int, int], ...] = (TIER_3, TIER_2, TIER_1)


# ── Pool I/O ───────────────────────────────────────────────────────────────

def _load_pool() -> Dict[str, Any]:
    if not POOL_FILE.exists():
        return {"version": 1, "items": {}, "last_fetch_ts": 0.0}
    try:
        return json.loads(POOL_FILE.read_text(encoding="utf-8")) or {
            "version": 1, "items": {}, "last_fetch_ts": 0.0
        }
    except Exception:
        return {"version": 1, "items": {}, "last_fetch_ts": 0.0}


def _save_pool(pool: Dict[str, Any]) -> None:
    """Atomic write — same pattern daily_pool.py uses so we don't fight it."""
    POOL_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(POOL_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(pool, fh, indent=2, sort_keys=True)
    os.replace(tmp, POOL_FILE)


# ── State (cadence + budget) ───────────────────────────────────────────────

def _today_ymd_utc() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def _empty_state() -> Dict[str, Any]:
    return {
        "version": 1,
        "ymd_utc": _today_ymd_utc(),
        "calls_today": 0,
        "last_run_ts_tier_1": 0.0,
        "last_run_ts_tier_2": 0.0,
        "last_run_ts_tier_3": 0.0,
        "last_summary": {},
    }


def _load_state() -> Dict[str, Any]:
    if not STATE_FILE.exists():
        return _empty_state()
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return _empty_state()
    if not isinstance(data, dict):
        return _empty_state()
    # UTC rollover for the budget counter only — cadence timestamps survive.
    if str(data.get("ymd_utc") or "") != _today_ymd_utc():
        data["ymd_utc"] = _today_ymd_utc()
        data["calls_today"] = 0
    data.setdefault("last_run_ts_tier_1", 0.0)
    data.setdefault("last_run_ts_tier_2", 0.0)
    data.setdefault("last_run_ts_tier_3", 0.0)
    return data


def _save_state(state: Dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(STATE_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
    os.replace(tmp, STATE_FILE)


def _is_near_end_budget_exceeded(state: Dict[str, Any]) -> bool:
    return int(state.get("calls_today") or 0) >= NEAR_END_BUDGET


# ── Time helpers ───────────────────────────────────────────────────────────

def _row_seconds_remaining(row: Dict[str, Any]) -> Optional[float]:
    """Compute seconds-to-end for a pool row using the same field-priority
    pool_view.py uses, so we tier identically."""
    now = time.time()
    # Numeric timestamp stamped by daily_pool at merge time.
    end_ts = row.get("_pool_end_dt_ts") or row.get("end_dt_ts")
    if end_ts:
        try:
            return float(end_ts) - now
        except Exception:
            pass
    # ISO string fallback.
    end_iso = row.get("end_dt_iso") or row.get("end_dt")
    if isinstance(end_iso, str) and end_iso:
        try:
            iso = end_iso.replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp() - now
        except Exception:
            pass
    return None


def _tier_for_secs(secs: Optional[float]) -> int:
    """Return 1/2/3 for which tier this card belongs to, or 0 (none)."""
    if secs is None or secs <= 0:
        return 0
    if TIER_3[0] <= secs < TIER_3[1]:
        return 3
    if TIER_2[0] <= secs < TIER_2[1]:
        return 2
    if TIER_1[0] <= secs < TIER_1[1]:
        return 1
    return 0


# ── eBay item refresh ──────────────────────────────────────────────────────

def _fetch_item_price(item_id: str, headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Fire one Browse API getItem call. Returns a dict with current_price,
    bid_count, raw response shape, or None on any failure. Cheap and safe."""
    if not item_id:
        return None
    # Browse API getItem endpoint. Accepts the v1|<legacyId>|0 envelope
    # directly when URL-encoded, or the bare numeric for some calls.
    # We use the full envelope — what daily_pool stamps on rows.
    encoded = urllib.parse.quote(item_id, safe="")
    url = f"https://api.ebay.com/buy/browse/v1/item/{encoded}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        print(
            f"[near_end_refresher] getItem HTTP {exc.code} item={item_id[:40]} "
            f"body={body}",
            flush=True,
        )
        return None
    except Exception as exc:
        print(
            f"[near_end_refresher] getItem error item={item_id[:40]} "
            f"{type(exc).__name__}: {str(exc)[:120]}",
            flush=True,
        )
        return None
    # Pull current bid the same way the engine does — currentBidPrice for
    # auctions, fall back to price.value for non-auction shapes.
    cbp = (data or {}).get("currentBidPrice") or {}
    bin_p = (data or {}).get("price") or {}
    try:
        bid = float(str(cbp.get("value") or 0).replace(",", ""))
    except Exception:
        bid = 0.0
    try:
        bin_v = float(str(bin_p.get("value") or 0).replace(",", ""))
    except Exception:
        bin_v = 0.0
    current = bid if bid > 0 else bin_v
    bid_count = data.get("bidCount") or 0
    try:
        bid_count = int(bid_count)
    except Exception:
        bid_count = 0
    return {
        "current_price": current,
        "bid_count":     bid_count,
        "raw_price":     bin_p,
        "raw_bid":       cbp,
    }


def _ebay_headers() -> Optional[Dict[str, str]]:
    """Reuse the engine's auth helper so we share its token cache + env
    var handling. Failure-quiet — returns None on any auth issue."""
    try:
        import ending_soon_engine as ese
        return ese._ebay_auth_headers()
    except Exception as exc:
        print(
            f"[near_end_refresher] auth headers unavailable: "
            f"{type(exc).__name__}: {str(exc)[:120]}",
            flush=True,
        )
        return None


# ── Tier refresh ───────────────────────────────────────────────────────────

def _tier_due(tier_id: int, state: Dict[str, Any]) -> bool:
    """True if the named tier hasn't been run within its cadence window."""
    if tier_id == 1:
        last = float(state.get("last_run_ts_tier_1") or 0)
        interval = TIER_1[2]
    elif tier_id == 2:
        last = float(state.get("last_run_ts_tier_2") or 0)
        interval = TIER_2[2]
    elif tier_id == 3:
        last = float(state.get("last_run_ts_tier_3") or 0)
        interval = TIER_3[2]
    else:
        return False
    if last <= 0:
        return True
    return (time.time() - last) >= interval


def _refresh_tier(
    tier_id: int,
    pool: Dict[str, Any],
    headers: Dict[str, str],
    state: Dict[str, Any],
    max_calls_remaining: int,
) -> Dict[str, int]:
    """Refresh every card whose time-to-end currently puts it in this tier.
    Returns counts: {refreshed, unchanged, failed, skipped_budget}."""
    counts = {"refreshed": 0, "unchanged": 0, "failed": 0, "skipped_budget": 0}
    items: Dict[str, Any] = pool.get("items") or {}
    targets: List[Tuple[str, Dict[str, Any]]] = []
    for item_id, row in items.items():
        if not isinstance(row, dict):
            continue
        secs = _row_seconds_remaining(row)
        if _tier_for_secs(secs) == tier_id:
            targets.append((item_id, row))
    # Sort ending-soonest first so if budget runs out the most-imminent
    # cards still get refreshed.
    targets.sort(key=lambda t: _row_seconds_remaining(t[1]) or 1e9)
    for item_id, row in targets:
        if max_calls_remaining <= 0:
            counts["skipped_budget"] += len(targets) - (
                counts["refreshed"] + counts["unchanged"] + counts["failed"]
            )
            break
        result = _fetch_item_price(item_id, headers)
        max_calls_remaining -= 1
        state["calls_today"] = int(state.get("calls_today") or 0) + 1
        # Also count this against the global eBay quota so morning comp
        # queries and near-end refreshes can't sum past 5,000/day.
        try:
            import daily_budget as _global_budget
            _global_budget.record_calls(1)
        except Exception:
            pass
        if not result:
            counts["failed"] += 1
            continue
        new_price = float(result.get("current_price") or 0)
        old_price = 0.0
        for k in ("current_price", "current_bid", "_authoritative_current_price"):
            v = row.get(k)
            try:
                if v is not None and float(v) > old_price:
                    old_price = float(v)
            except Exception:
                pass
        if new_price <= 0:
            counts["failed"] += 1
            continue
        # Stamp the fresh values. _authoritative_current_price is what
        # pool_view._row_current_price reads first, so writing it here
        # guarantees the dashboard sees the update next render.
        row["current_price"] = new_price
        row["_authoritative_current_price"] = new_price
        row["_board_current_price"] = new_price
        if result.get("raw_bid"):
            row["currentBidPrice"] = result["raw_bid"]
        if result.get("raw_price"):
            row["price"] = result["raw_price"]
        if result.get("bid_count"):
            row["bid_count"] = result["bid_count"]
        row["_last_near_end_refresh_ts"] = time.time()
        row["_last_near_end_refresh_tier"] = tier_id
        if abs(new_price - old_price) >= 0.005:
            counts["refreshed"] += 1
            print(
                f"[near_end_refresher] tier={tier_id} item={item_id[:40]} "
                f"price={old_price:.2f}→{new_price:.2f} bids={result.get('bid_count', 0)}",
                flush=True,
            )
        else:
            counts["unchanged"] += 1
    return counts


# ── Public API ─────────────────────────────────────────────────────────────

def run_once(force: bool = False) -> Dict[str, Any]:
    """Refresh whichever tiers are due. Called from the worker loop. Cheap
    on cycles where no tier is due — early-returns after cadence check."""
    summary: Dict[str, Any] = {
        "ran":                 False,
        "skipped_reason":      "",
        "tiers_run":           [],
        "refreshed":           0,
        "unchanged":           0,
        "failed":              0,
        "skipped_budget":      0,
        "calls_used":          0,
    }
    started = time.time()

    try:
        state = _load_state()
    except Exception as exc:
        summary["skipped_reason"] = f"state_load_error:{type(exc).__name__}"
        return summary

    # Cadence: is ANY tier due? If not, return cheap.
    if not force:
        due_tiers = [t for t in (3, 2, 1) if _tier_due(t, state)]
        if not due_tiers:
            summary["skipped_reason"] = "no_tier_due"
            return summary
    else:
        due_tiers = [3, 2, 1]

    # Budget guards. Two layers:
    #   1. Dedicated near-end soft cap (NEAR_END_BUDGET) — prevents this
    #      module from runaway-burning all calls on price refresh.
    #   2. Global daily_budget — eBay's 5,000/day quota wall. We count
    #      near-end calls against it so total burn never exceeds the
    #      external limit. If the global is exhausted, near-end stops too.
    if _is_near_end_budget_exceeded(state):
        summary["skipped_reason"] = (
            f"near_end_budget_exhausted "
            f"({state.get('calls_today')}/{NEAR_END_BUDGET})"
        )
        return summary
    try:
        import daily_budget as _global_budget
        if _global_budget.is_budget_exceeded():
            _summ = _global_budget.get_budget_summary()
            summary["skipped_reason"] = (
                f"global_budget_exhausted "
                f"({_summ.get('calls_today')}/{_summ.get('daily_budget')})"
            )
            return summary
    except Exception:
        # If daily_budget can't be imported (e.g. dev environment without
        # the file), fall through using only the near-end cap.
        pass

    headers = _ebay_headers()
    if not headers:
        summary["skipped_reason"] = "no_auth_headers"
        return summary

    try:
        pool = _load_pool()
    except Exception as exc:
        summary["skipped_reason"] = f"pool_load_error:{type(exc).__name__}"
        return summary

    summary["ran"] = True

    # Tier 3 first (most imminent) so budget exhaustion hurts the
    # longest-ending tier rather than the cards about to close.
    pre_calls = int(state.get("calls_today") or 0)
    for tier_id in due_tiers:
        remaining = NEAR_END_BUDGET - int(state.get("calls_today") or 0)
        if remaining <= 0:
            break
        counts = _refresh_tier(tier_id, pool, headers, state, remaining)
        # Stamp last-run timestamp even if no cards in this tier — keeps
        # the cadence ticking forward.
        if tier_id == 1:
            state["last_run_ts_tier_1"] = time.time()
        elif tier_id == 2:
            state["last_run_ts_tier_2"] = time.time()
        elif tier_id == 3:
            state["last_run_ts_tier_3"] = time.time()
        summary["tiers_run"].append(tier_id)
        summary["refreshed"] += counts["refreshed"]
        summary["unchanged"] += counts["unchanged"]
        summary["failed"] += counts["failed"]
        summary["skipped_budget"] += counts["skipped_budget"]
    summary["calls_used"] = int(state.get("calls_today") or 0) - pre_calls

    # Persist updated pool + state. Save pool first so the dashboard
    # sees prices even if state-save races.
    try:
        if summary["refreshed"] + summary["unchanged"] > 0:
            _save_pool(pool)
    except Exception as exc:
        print(
            f"[near_end_refresher] pool save failed (non-fatal): "
            f"{type(exc).__name__}: {str(exc)[:120]}",
            flush=True,
        )
    try:
        state["last_summary"] = summary
        state["last_run_iso"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started))
        _save_state(state)
    except Exception as exc:
        print(
            f"[near_end_refresher] state save failed (non-fatal): "
            f"{type(exc).__name__}: {str(exc)[:120]}",
            flush=True,
        )

    elapsed = round(time.time() - started, 2)
    if summary["refreshed"] + summary["failed"] > 0 or summary["skipped_budget"] > 0:
        print(
            f"[near_end_refresher] tiers={summary['tiers_run']} "
            f"refreshed={summary['refreshed']} unchanged={summary['unchanged']} "
            f"failed={summary['failed']} skipped_budget={summary['skipped_budget']} "
            f"calls_used={summary['calls_used']} elapsed={elapsed}s",
            flush=True,
        )
    return summary


# ── CLI ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="near_end_refresher.py")
    parser.add_argument("--force", action="store_true",
                        help="Bypass cadence guard and refresh now")
    parser.add_argument("--status", action="store_true",
                        help="Print state JSON and exit")
    parser.add_argument("--loop", action="store_true",
                        help="Run continuously, sleeping --interval between cycles")
    parser.add_argument("--interval", type=int, default=15,
                        help="Seconds between cycles in --loop mode (default 15)")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(_load_state(), indent=2))
    elif args.loop:
        print(f"[near_end_refresher] looping interval={args.interval}s budget={NEAR_END_BUDGET}/day")
        while True:
            try:
                run_once(force=args.force)
            except KeyboardInterrupt:
                print("[near_end_refresher] interrupted")
                break
            except Exception as exc:
                print(f"[near_end_refresher] loop error: {type(exc).__name__}: {exc}")
            try:
                time.sleep(args.interval)
            except KeyboardInterrupt:
                break
    else:
        print(json.dumps(run_once(force=args.force), indent=2))
