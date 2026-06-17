"""
daily_budget.py — Shared daily eBay-API call counter with UTC rollover.

The problem this exists to fix:
    Even with per-cycle caps on the BIN scanner (80 specs) and the
    auction pool's internal budget (~27 specs), the valuation_worker
    runs every 60s and can fire up to 15 comp searches per cycle. Across
    POOL + BIN + WORKER, the system was blowing the 5,000 calls/day eBay
    quota in 2-3 hours for three days running — exactly the failure mode
    this module prevents.

How it works:
    A small JSON file on disk (shared across the supervisor's three
    scanner processes) tracks how many calls have been made today (UTC).
    Each scanner cycle:
      1. Reports the calls it made via record_calls(n)
      2. Checks is_budget_exceeded() before the NEXT cycle and skips
         if we've already burned the day's budget.
    UTC-midnight rollover is implicit — the file's `ymd_utc` field is
    compared on every read; if it doesn't match today, the counter
    resets to 0.

Configuration:
    SNIPEWINS_DAILY_CALL_BUDGET (env var, default 4500)
        Soft cap. We pick 4500 instead of 5000 to leave a 10% buffer for
        bookkeeping drift and request-in-flight overshoot.

    SNIPEWINS_DAILY_BUDGET_PATH (env var, default ./daily_call_budget.json)
        Path to the counter file. In production this should point at the
        Render persistent disk (e.g. /data/daily_call_budget.json) so the
        counter survives process restarts and supervisor child crashes.

This is a SOFT throttle. The reactive cooldown ladder in ebay_search.py
remains the hard backstop — if our counter is off by a bit and we
overshoot, 429s still trigger cooldowns and prevent runaway burn.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


HERE = Path(__file__).parent
BUDGET_FILE = Path(
    os.environ.get("SNIPEWINS_DAILY_BUDGET_PATH") or str(HERE / "daily_call_budget.json")
)

# Default 4500 (10% buffer under eBay's 5,000/day Browse API cap).
# Override per-environment via env var.
DEFAULT_DAILY_BUDGET = 4500
DAILY_BUDGET = int(os.environ.get("SNIPEWINS_DAILY_CALL_BUDGET") or DEFAULT_DAILY_BUDGET)


# Per-process lock — the three scanner processes don't share memory but
# each process can have multiple writers (e.g. concurrent comp fetches in
# the worker's batch). A thread lock + atomic file write is enough.
_FILE_LOCK = threading.Lock()


# ── Persistence ────────────────────────────────────────────────────────────

def _today_ymd_utc() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def _empty_state() -> Dict[str, Any]:
    return {"version": 1, "ymd_utc": _today_ymd_utc(), "calls_today": 0}


def _load() -> Dict[str, Any]:
    """Read the counter file. Auto-rolls over at UTC midnight: if the
    file's ymd_utc doesn't match today, we return a fresh zeroed state
    (the rollover is persisted on the next save)."""
    if not BUDGET_FILE.exists():
        return _empty_state()
    try:
        data = json.loads(BUDGET_FILE.read_text(encoding="utf-8"))
    except Exception:
        return _empty_state()
    if not isinstance(data, dict):
        return _empty_state()
    if str(data.get("ymd_utc") or "") != _today_ymd_utc():
        # UTC day rolled over — start fresh. Old day's count is discarded;
        # we don't keep history because the value of doing so is low.
        return _empty_state()
    data.setdefault("version", 1)
    data.setdefault("calls_today", 0)
    return data


def _save(state: Dict[str, Any]) -> None:
    """Atomic write — tmp + replace so concurrent readers never see a
    half-written file. parents=True so the file can live on a freshly
    mounted persistent disk."""
    BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(BUDGET_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
    os.replace(tmp, BUDGET_FILE)


# ── Public API ─────────────────────────────────────────────────────────────

def record_calls(n: int) -> int:
    """Increment today's call counter by n. Returns the post-increment
    total. Safe to call with n=0 (no-op write skipped). Catches all
    exceptions internally — a budget bookkeeping failure must NEVER
    crash the scanner."""
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        return 0
    if n <= 0:
        return get_calls_today()
    try:
        with _FILE_LOCK:
            state = _load()
            state["calls_today"] = int(state.get("calls_today") or 0) + n
            state["ymd_utc"] = _today_ymd_utc()
            state["last_update_ts"] = time.time()
            _save(state)
            return int(state["calls_today"])
    except Exception as exc:
        print(f"[daily_budget] record_calls failure (non-fatal): {type(exc).__name__}: {exc}")
        return 0


def get_calls_today() -> int:
    try:
        return int(_load().get("calls_today") or 0)
    except Exception:
        return 0


def is_budget_exceeded() -> bool:
    """True if today's call count has hit or passed the daily budget. The
    scanner cycle wrappers check this BEFORE starting a cycle — if True,
    the cycle is skipped and we sleep until the next interval (and
    eventually UTC midnight, when the counter rolls over)."""
    return get_calls_today() >= DAILY_BUDGET


def get_budget_summary() -> Dict[str, Any]:
    """Human-readable snapshot for logs and ops checks."""
    calls = get_calls_today()
    return {
        "calls_today":   calls,
        "daily_budget":  DAILY_BUDGET,
        "remaining":     max(0, DAILY_BUDGET - calls),
        "exceeded":      calls >= DAILY_BUDGET,
        "pct_used":      round(100.0 * calls / max(1, DAILY_BUDGET), 1),
        "ymd_utc":       _today_ymd_utc(),
        "budget_file":   str(BUDGET_FILE),
    }


# ── CLI for ops / debugging ─────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="daily_budget.py — ops CLI")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("status", help="show current budget state")
    p_record = sub.add_parser("record", help="manually record N calls")
    p_record.add_argument("n", type=int)
    sub.add_parser("reset", help="force-reset today's counter to 0")
    args = parser.parse_args()

    if args.cmd == "status":
        print(json.dumps(get_budget_summary(), indent=2))
    elif args.cmd == "record":
        total = record_calls(int(args.n))
        print(f"recorded; calls_today={total}")
    elif args.cmd == "reset":
        with _FILE_LOCK:
            _save(_empty_state())
        print("reset to 0 for today (UTC)")
    else:
        parser.print_help()
