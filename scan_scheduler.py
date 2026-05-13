"""
scan_scheduler.py — Background auto-scanner

Runs ending_soon_engine.fetch_ending_soon_deals(force_refresh=True) on a
configurable timer. Thread-safe. Never crashes the app.

Public API:
  start()           — start the background scheduler (idempotent)
  stop()            — stop the scheduler
  trigger_now()     — force an immediate scan outside the schedule
  get_state()       — thread-safe snapshot for the UI
  load_settings()   — load from scheduler_settings.json
  save_settings(d)  — persist scheduler config

State keys returned by get_state():
  enabled            bool   — auto-scan toggle
  status             str    — "idle" | "scanning" | "rate_limited" | "stopped"
  interval_secs      int    — seconds between scans
  last_scan_ts       float  — epoch of last completed scan
  next_scan_ts       float  — epoch of next scheduled scan
  scan_in_progress   bool   — True while a scan thread is live
  queries_done       int    — progress counter (from engine)
  queries_total      int    — total queries this scan
  current_player     str    — player name currently being queried
  api_calls_hour     int    — Browse API calls in the rolling hour window
  api_hourly_limit   int    — calls/hour before warning (default 500)
  scan_history       list   — last 10 scan summary dicts
  last_error         str    — last error message
  rate_limited_until float  — epoch when rate limit lifts (0 if none)
"""
from __future__ import annotations

import csv
import json
import os
import threading
import time
import uuid
from collections import deque
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE            = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR        = os.path.join(_HERE, "data")
_SCAN_LOG        = os.path.join(_DATA_DIR, "scan_log.csv")
_SETTINGS_FILE   = os.path.join(_HERE, "scheduler_settings.json")

_LOG_COLS = [
    "scan_id", "timestamp", "duration_seconds", "players_scanned",
    "listings_found", "elite_deals", "strong_deals", "bin_alerts", "errors",
]

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULTS: Dict[str, Any] = {
    "enabled":        True,
    "interval_secs":  900,       # 15 minutes
    "api_hourly_limit": 500,     # eBay API calls/hour before warning
}

INTERVAL_OPTIONS: Dict[str, int] = {
    "Every 5 min":  300,
    "Every 10 min": 600,
    "Every 15 min": 900,
    "Every 30 min": 1800,
}

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_STATE_LOCK  = threading.Lock()
_STOP_EVENT  = threading.Event()
_SCAN_LOCK   = threading.Lock()   # prevents two scans running simultaneously

_STATE: Dict[str, Any] = {
    "enabled":           True,
    "status":            "stopped",
    "interval_secs":     900,
    "last_scan_ts":      0.0,
    "next_scan_ts":      0.0,
    "scan_in_progress":  False,
    "queries_done":      0,
    "queries_total":     0,
    "current_player":    "",
    "api_calls_hour":    0,
    "api_hourly_limit":  500,
    "scan_history":      [],      # list of dicts, newest first, max 10
    "last_error":        "",
    "rate_limited_until": 0.0,
    "_api_call_times":   [],      # raw timestamps for rolling-hour count
    # ── Imminent scanner state (separate from wide scan) ──
    # Runs every IMMINENT_INTERVAL_SECS, fetches only the 0-1h window,
    # surfaces urgent alerts ahead of the 15-min wide scan.
    #
    # DEFAULT: DISABLED. Initial 3-min cadence with the full pipeline is
    # too aggressive — each scan takes 60-90s so scans queue up and the
    # log floods. Flip imminent_enabled to True (or call enable_imminent())
    # once we tune the cadence and prove it doesn't pile up. To enable
    # for one session: import scan_scheduler; scan_scheduler.enable_imminent().
    "imminent_enabled":          False,
    "imminent_interval_secs":    600,    # 10 min — safe default once enabled
    "imminent_window_hours":     1.0,    # only fetch 0-1h ending
    "imminent_in_progress":      False,
    "imminent_last_scan_ts":     0.0,
    "imminent_next_scan_ts":     0.0,
    "imminent_last_deals":       0,
    "imminent_last_error":       "",
}

_SCHED_THREAD: Optional[threading.Thread] = None
_IMMINENT_THREAD: Optional[threading.Thread] = None
_IMMINENT_LOCK = threading.Lock()  # prevents two imminent scans overlapping
_IMMINENT_HEARTBEAT_FILE = "imminent_heartbeat.json"

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def load_settings() -> Dict[str, Any]:
    if not os.path.exists(_SETTINGS_FILE):
        return dict(_DEFAULTS)
    try:
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        merged = dict(_DEFAULTS)
        merged.update({k: v for k, v in saved.items() if k in _DEFAULTS})
        return merged
    except Exception:
        return dict(_DEFAULTS)


def save_settings(settings: Dict[str, Any]) -> None:
    try:
        with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump({k: settings[k] for k in _DEFAULTS if k in settings}, f, indent=2)
    except Exception as exc:
        print(f"[SCHED] Could not save settings: {exc}")


# ---------------------------------------------------------------------------
# Scan log CSV
# ---------------------------------------------------------------------------

def _ensure_log() -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    if not os.path.exists(_SCAN_LOG):
        with open(_SCAN_LOG, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=_LOG_COLS).writeheader()


def _write_scan_log(row: Dict[str, Any]) -> None:
    try:
        _ensure_log()
        with open(_SCAN_LOG, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=_LOG_COLS)
            w.writerow({k: row.get(k, "") for k in _LOG_COLS})
    except Exception as exc:
        print(f"[SCHED] Could not write scan log: {exc}")


def load_scan_history(n: int = 10) -> List[Dict[str, Any]]:
    """Return last n scan log rows (newest first) from scan_log.csv."""
    if not os.path.exists(_SCAN_LOG):
        return []
    try:
        rows = []
        with open(_SCAN_LOG, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(dict(row))
        return list(reversed(rows[-n:]))
    except Exception:
        return []


# ---------------------------------------------------------------------------
# API call tracking (rolling 1-hour window)
# ---------------------------------------------------------------------------

def _record_api_calls(n: int) -> None:
    """Record n API calls as happening right now."""
    now = time.time()
    with _STATE_LOCK:
        calls: List[float] = _STATE["_api_call_times"]
        cutoff = now - 3600
        # Prune old entries
        while calls and calls[0] < cutoff:
            calls.pop(0)
        calls.extend([now] * n)
        _STATE["api_calls_hour"] = len(calls)


def _get_api_calls_last_hour() -> int:
    now = time.time()
    cutoff = now - 3600
    with _STATE_LOCK:
        calls: List[float] = _STATE["_api_call_times"]
        while calls and calls[0] < cutoff:
            calls.pop(0)
        count = len(calls)
        _STATE["api_calls_hour"] = count
        return count


# ---------------------------------------------------------------------------
# Public state accessor
# ---------------------------------------------------------------------------

def get_state() -> Dict[str, Any]:
    """Thread-safe snapshot. Strips internal keys."""
    with _STATE_LOCK:
        s = deepcopy(_STATE)
    s.pop("_api_call_times", None)
    return s


# ---------------------------------------------------------------------------
# Core scan worker (runs in its own thread)
# ---------------------------------------------------------------------------

def _run_scan_worker() -> None:
    """
    Execute one full eBay scan. Runs in a dedicated thread.
    Acquires _SCAN_LOCK so only one scan runs at a time.
    """
    if not _SCAN_LOCK.acquire(blocking=False):
        print("[SCHED] Scan already in progress — skipping.")
        return

    scan_id    = str(uuid.uuid4())[:8]
    start_time = time.time()
    error_msg  = ""

    with _STATE_LOCK:
        _STATE["scan_in_progress"] = True
        _STATE["status"]           = "scanning"
        _STATE["queries_done"]     = 0
        _STATE["queries_total"]    = 0
        _STATE["current_player"]   = ""
        _STATE["last_error"]       = ""

    print(f"[SCHED] Scan {scan_id} starting…")
    deals: List[Dict[str, Any]] = []
    meta: Dict[str, Any]       = {}

    try:
        import ending_soon_engine as _ese

        # Wire up progress callback
        def _on_query_done(player: str, done: int, total: int) -> None:
            with _STATE_LOCK:
                _STATE["queries_done"]   = done
                _STATE["queries_total"]  = total
                _STATE["current_player"] = player

        _ese._PROGRESS_CALLBACK = _on_query_done

        # Guardrail: verify the controlled family executor is in place before launching.
        # If the old mass-parallel constant is somehow missing, abort rather than spam eBay.
        batch_size = getattr(_ese, "_FAMILY_BATCH_SIZE", None)
        if not batch_size:
            print("[SCHED][GUARDRAIL] _FAMILY_BATCH_SIZE not found on ending_soon_engine — "
                  "aborting scan to prevent legacy 144-parallel launch.")
            return

        print(f"[SCHED] Launching controlled scan via family_executor (batch_size={batch_size})")
        deals, meta = _ese.fetch_ending_soon_deals(
            force_refresh=True,
            time_window_hours=3.0,
        )

        _ese._PROGRESS_CALLBACK = None

        # Record API calls made
        api_calls = int(meta.get("total_queries") or 0)
        if api_calls:
            _record_api_calls(api_calls)

        # Rate limit check
        if meta.get("rate_limited"):
            rl_until = time.time() + 60
            with _STATE_LOCK:
                _STATE["rate_limited_until"] = rl_until
                _STATE["status"] = "rate_limited"
            print(f"[SCHED] Rate limited — pausing auto-scan for 60s")

    except Exception as exc:
        error_msg = str(exc)[:200]
        print(f"[SCHED] Scan {scan_id} ERROR: {error_msg}")
        with _STATE_LOCK:
            _STATE["last_error"] = error_msg

    finally:
        _SCAN_LOCK.release()

    duration = round(time.time() - start_time, 1)

    # Count deal classes
    elite  = sum(1 for d in deals if d.get("deal_class") == "ELITE")
    strong = sum(1 for d in deals if d.get("deal_class") == "STRONG")
    bins   = sum(1 for d in deals if d.get("deal_class") in ("BIN_DEAL", "BIN_WATCH"))
    total  = len(deals)

    log_row = {
        "scan_id":          scan_id,
        "timestamp":        datetime.fromtimestamp(start_time).strftime("%Y-%m-%d %H:%M:%S"),
        "duration_seconds": duration,
        "players_scanned":  meta.get("players_searched", 0),
        "listings_found":   total,
        "elite_deals":      elite,
        "strong_deals":     strong,
        "bin_alerts":       bins,
        "errors":           error_msg,
    }
    _write_scan_log(log_row)

    history_entry = {
        **log_row,
        "ts": start_time,
    }

    with _STATE_LOCK:
        _STATE["scan_in_progress"] = False
        _STATE["last_scan_ts"]     = start_time
        if not meta.get("rate_limited"):
            _STATE["status"]       = "idle" if _STATE["enabled"] else "stopped"

        # Update scan history (newest first, keep 10)
        hist: List[Dict[str, Any]] = _STATE["scan_history"]
        hist.insert(0, history_entry)
        _STATE["scan_history"] = hist[:10]

    # PHASE-2 — persist a heartbeat file external watchers can read without
    # touching this process's memory. healthcheck.py reads this and alerts
    # when the timestamp goes stale.
    try:
        _heartbeat_path = os.path.join(_HERE, "scheduler_heartbeat.json")
        _heartbeat = {
            "last_scan_ts":            float(start_time),
            "last_scan_iso":           datetime.fromtimestamp(start_time).isoformat(timespec="seconds"),
            "duration_seconds":        float(duration),
            "scan_id":                 str(scan_id),
            "deals_total":             int(total),
            "deals_elite":             int(elite),
            "deals_strong":            int(strong),
            "deals_bin":               int(bins),
            "error":                   str(error_msg or ""),
            "rate_limited":            bool(meta.get("rate_limited") or False),
            "rate_limited_until":      float(_STATE.get("rate_limited_until") or 0.0),
            "interval_secs":           int(_STATE.get("interval_secs") or 900),
            "api_calls_hour":          int(_STATE.get("api_calls_hour") or 0),
            "api_hourly_limit":        int(_STATE.get("api_hourly_limit") or 500),
            "heartbeat_written_at":    time.time(),
        }
        _tmp_path = _heartbeat_path + ".tmp"
        with open(_tmp_path, "w", encoding="utf-8") as _hb_fh:
            json.dump(_heartbeat, _hb_fh, indent=2, sort_keys=True)
        os.replace(_tmp_path, _heartbeat_path)
    except Exception as _hb_exc:
        # Heartbeat is best-effort observability; never crash the scheduler
        # because we couldn't write the file.
        print(f"[SCHED][HEARTBEAT_WRITE_FAIL] {type(_hb_exc).__name__}: {str(_hb_exc)[:120]}")

        # Schedule next scan
        interval = int(_STATE["interval_secs"])
        _STATE["next_scan_ts"] = start_time + interval

    print(
        f"[SCHED] Scan {scan_id} done in {duration}s — "
        f"{total} listings, {elite} ELITE, {bins} BIN"
    )


# ---------------------------------------------------------------------------
# Background scheduler tick loop
# ---------------------------------------------------------------------------

def _scheduler_loop() -> None:
    """
    Ticks every 1 second.
    - Checks if it's time for the next scan
    - Checks rate-limit cooldown
    - Fires scan in a side thread so this loop never blocks
    """
    while not _STOP_EVENT.is_set():
        now = time.time()

        with _STATE_LOCK:
            enabled      = _STATE.get("enabled", True)
            next_scan    = float(_STATE.get("next_scan_ts") or 0)
            in_progress  = _STATE.get("scan_in_progress", False)
            rl_until     = float(_STATE.get("rate_limited_until") or 0)

        if not enabled:
            with _STATE_LOCK:
                _STATE["status"] = "stopped"
            time.sleep(1)
            continue

        # Rate limit cooldown
        if rl_until > now:
            with _STATE_LOCK:
                _STATE["status"] = "rate_limited"
            time.sleep(1)
            continue
        elif rl_until > 0:
            with _STATE_LOCK:
                _STATE["rate_limited_until"] = 0.0

        # Time to scan?
        if not in_progress and next_scan > 0 and now >= next_scan:
            t = threading.Thread(
                target=_run_scan_worker,
                daemon=True,
                name="sched_scan_worker",
            )
            t.start()

        time.sleep(1)

    with _STATE_LOCK:
        _STATE["status"] = "stopped"


# ---------------------------------------------------------------------------
# Imminent scanner — 1-hour window, 3-min cadence
# ---------------------------------------------------------------------------
# Surfaces auctions ending in the next 60 minutes ahead of the 15-min wide
# scan. Same player set. Same engine. Smaller fetch window so the call is
# light on eBay quota even at high cadence. Designed to feed the urgent
# Buying Radar / 30-min alert paywall.

def _run_imminent_scan_worker() -> None:
    """
    Execute one tight-window imminent scan. Daemon thread.
    Acquires _IMMINENT_LOCK so only one imminent scan runs at a time.
    Runs in parallel with the wide scan (separate _SCAN_LOCK).
    """
    if not _IMMINENT_LOCK.acquire(blocking=False):
        # Previous imminent scan still running — skip this tick rather than
        # queuing up. Auctions in the 0-1h window are the freshest data so
        # missing one cycle is fine; we'll catch it 3 min later.
        return

    scan_id    = "im_" + str(uuid.uuid4())[:6]
    start_time = time.time()
    error_msg  = ""
    deals: List[Dict[str, Any]] = []
    meta:  Dict[str, Any]       = {}

    with _STATE_LOCK:
        _STATE["imminent_in_progress"] = True

    try:
        import ending_soon_engine as _ese

        # Use the configured window — 1h by default. Same engine entry point
        # as the wide scan so all of our PREPARE-funnel work applies here.
        with _STATE_LOCK:
            _window_hours = float(_STATE.get("imminent_window_hours") or 1.0)

        print(f"[SCHED][IMMINENT] {scan_id} starting (window={_window_hours}h)…")
        deals, meta = _ese.fetch_ending_soon_deals(
            force_refresh=True,
            time_window_hours=_window_hours,
        )

        # Record API calls so the rolling-hour quota counter stays accurate.
        api_calls = int((meta or {}).get("total_queries") or 0)
        if api_calls:
            _record_api_calls(api_calls)

        if (meta or {}).get("rate_limited"):
            with _STATE_LOCK:
                _STATE["rate_limited_until"] = time.time() + 60
            print(f"[SCHED][IMMINENT] {scan_id} rate-limited — backing off 60s")

    except Exception as exc:
        error_msg = str(exc)[:200]
        print(f"[SCHED][IMMINENT] {scan_id} ERROR: {error_msg}")

    finally:
        _IMMINENT_LOCK.release()

    duration = round(time.time() - start_time, 1)

    # Count what landed in the urgent buckets so the heartbeat file gives
    # the UI something useful to display without a second API call.
    elite       = sum(1 for d in deals if str(d.get("deal_class") or "") == "ELITE")
    strong      = sum(1 for d in deals if str(d.get("deal_class") or "") == "STRONG")
    sub_30_min  = 0
    sub_60_min  = 0
    for d in (deals or []):
        try:
            secs = float(
                d.get("remaining_seconds")
                or d.get("seconds_remaining")
                or d.get("_intake_remaining_secs")
                or 0.0
            )
        except Exception:
            secs = 0.0
        if 0 < secs <= 1800.0:
            sub_30_min += 1
        if 0 < secs <= 3600.0:
            sub_60_min += 1

    with _STATE_LOCK:
        _STATE["imminent_in_progress"]   = False
        _STATE["imminent_last_scan_ts"]  = start_time
        _STATE["imminent_last_deals"]    = int(len(deals))
        _STATE["imminent_last_error"]    = error_msg

    # Heartbeat file — the UI and external watchers can poll this without
    # touching the engine. Atomic write (tmp + replace) so readers never see
    # a partial JSON.
    try:
        _heartbeat = {
            "scan_id":              str(scan_id),
            "kind":                 "imminent",
            "window_hours":         float(_window_hours),
            "last_scan_ts":         float(start_time),
            "last_scan_iso":        datetime.fromtimestamp(start_time).isoformat(timespec="seconds"),
            "duration_seconds":     float(duration),
            "deals_total":          int(len(deals)),
            "deals_elite":          int(elite),
            "deals_strong":         int(strong),
            "deals_under_30min":    int(sub_30_min),
            "deals_under_60min":    int(sub_60_min),
            "error":                str(error_msg or ""),
            "rate_limited":         bool((meta or {}).get("rate_limited") or False),
            "interval_secs":        int(_STATE.get("imminent_interval_secs") or 180),
            "heartbeat_written_at": time.time(),
        }
        _hb_path = os.path.join(_HERE, _IMMINENT_HEARTBEAT_FILE)
        _tmp_path = _hb_path + ".tmp"
        with open(_tmp_path, "w", encoding="utf-8") as _hb_fh:
            json.dump(_heartbeat, _hb_fh, indent=2, sort_keys=True)
        os.replace(_tmp_path, _hb_path)
    except Exception as _hb_exc:
        print(f"[SCHED][IMMINENT][HEARTBEAT_WRITE_FAIL] {type(_hb_exc).__name__}: {str(_hb_exc)[:120]}")

    print(
        f"[SCHED][IMMINENT] {scan_id} done in {duration}s — "
        f"{len(deals)} deals, {sub_30_min} ending <30min, {sub_60_min} ending <60min"
    )


def _imminent_loop() -> None:
    """
    Ticks every 1 second. When imminent_next_scan_ts is reached, fires
    _run_imminent_scan_worker in a side thread so this loop never blocks.
    Independent of the wide _scheduler_loop — they share the rolling API
    quota counter via _record_api_calls but no other state.
    """
    while not _STOP_EVENT.is_set():
        now = time.time()

        with _STATE_LOCK:
            enabled       = _STATE.get("imminent_enabled", True)
            global_enabled = _STATE.get("enabled", True)
            next_scan     = float(_STATE.get("imminent_next_scan_ts") or 0)
            in_progress   = _STATE.get("imminent_in_progress", False)
            interval_s    = int(_STATE.get("imminent_interval_secs") or 180)
            rl_until      = float(_STATE.get("rate_limited_until") or 0)

        # Honor the global enable flag (stop() pause) and the imminent toggle.
        if not enabled or not global_enabled:
            time.sleep(1)
            continue

        # Honor the same rate-limit cooldown as the wide scan.
        if rl_until > now:
            time.sleep(1)
            continue

        # First tick after start: schedule for 60 seconds out so the wide
        # scan's first cycle gets a head start.
        if next_scan == 0.0:
            with _STATE_LOCK:
                _STATE["imminent_next_scan_ts"] = now + 60
            time.sleep(1)
            continue

        if not in_progress and now >= next_scan:
            with _STATE_LOCK:
                _STATE["imminent_next_scan_ts"] = now + interval_s
            t = threading.Thread(
                target=_run_imminent_scan_worker,
                daemon=True,
                name="imminent_scan_worker",
            )
            t.start()

        time.sleep(1)


# ---------------------------------------------------------------------------
# Public control API
# ---------------------------------------------------------------------------

def start() -> None:
    """
    Start the background scheduler. Idempotent — calling twice is safe.
    Loads settings from disk on first start.
    """
    global _SCHED_THREAD

    # Load persisted settings
    cfg = load_settings()
    with _STATE_LOCK:
        _STATE["enabled"]          = bool(cfg.get("enabled", True))
        _STATE["interval_secs"]    = int(cfg.get("interval_secs", 900))
        _STATE["api_hourly_limit"] = int(cfg.get("api_hourly_limit", 500))

        # Don't start if already running
        if _SCHED_THREAD is not None and _SCHED_THREAD.is_alive():
            return

        # Schedule first scan for 30 seconds from now (let app finish loading)
        if _STATE["next_scan_ts"] == 0.0 and _STATE["enabled"]:
            _STATE["next_scan_ts"] = time.time() + 30

        _STATE["status"] = "idle" if _STATE["enabled"] else "stopped"

    _STOP_EVENT.clear()
    _SCHED_THREAD = threading.Thread(
        target=_scheduler_loop,
        daemon=True,
        name="scan_scheduler",
    )
    _SCHED_THREAD.start()
    print("[SCHED] Scheduler started.")

    # Imminent scanner — separate thread, independent loop. Runs every
    # imminent_interval_secs (180s by default), fetches the 0-1h window only.
    # Spawned alongside the wide scanner; stop()/_STOP_EVENT halts both.
    global _IMMINENT_THREAD
    if _IMMINENT_THREAD is None or not _IMMINENT_THREAD.is_alive():
        _IMMINENT_THREAD = threading.Thread(
            target=_imminent_loop,
            daemon=True,
            name="imminent_scanner",
        )
        _IMMINENT_THREAD.start()
        print(f"[SCHED][IMMINENT] Imminent scanner started "
              f"(interval={int(_STATE.get('imminent_interval_secs') or 180)}s, "
              f"window={float(_STATE.get('imminent_window_hours') or 1.0)}h).")


def stop() -> None:
    """Stop the scheduler. Running scan is allowed to finish."""
    _STOP_EVENT.set()
    with _STATE_LOCK:
        _STATE["enabled"]  = False
        _STATE["status"]   = "stopped"
    print("[SCHED] Scheduler stopped.")


def trigger_now() -> None:
    """Force an immediate scan regardless of next_scan_ts."""
    with _STATE_LOCK:
        _STATE["next_scan_ts"] = time.time() - 1  # make it overdue immediately
    print("[SCHED] Immediate scan triggered.")


def enable_imminent(interval_secs: int = 600) -> None:
    """Turn on the 0-1h imminent scanner. Default interval 10 min."""
    with _STATE_LOCK:
        _STATE["imminent_enabled"]       = True
        _STATE["imminent_interval_secs"] = max(120, int(interval_secs))
        _STATE["imminent_next_scan_ts"]  = 0.0  # reset so the loop reschedules
    print(f"[SCHED][IMMINENT] enabled, interval={_STATE['imminent_interval_secs']}s")


def disable_imminent() -> None:
    """Turn off the imminent scanner. Existing in-flight scan is allowed
    to finish; no new scans will start."""
    with _STATE_LOCK:
        _STATE["imminent_enabled"] = False
    print("[SCHED][IMMINENT] disabled")


def set_enabled(enabled: bool) -> None:
    """Toggle auto-scan on/off without stopping the scheduler thread."""
    with _STATE_LOCK:
        _STATE["enabled"] = enabled
        if enabled:
            _STATE["status"] = "idle"
            if float(_STATE.get("next_scan_ts") or 0) == 0.0:
                _STATE["next_scan_ts"] = time.time() + 5
        else:
            _STATE["status"] = "stopped"


def set_interval(interval_secs: int) -> None:
    """Change the scan interval live."""
    with _STATE_LOCK:
        _STATE["interval_secs"] = max(60, int(interval_secs))
        # Recompute next scan from last scan
        last = float(_STATE.get("last_scan_ts") or 0)
        if last > 0:
            _STATE["next_scan_ts"] = last + _STATE["interval_secs"]


def is_running() -> bool:
    return _SCHED_THREAD is not None and _SCHED_THREAD.is_alive()
