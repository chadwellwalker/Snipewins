"""
healthcheck.py — is the scheduler alive and producing deals?

Why this exists:
    A deal-finder app that goes silent for hours kills retention faster than
    any feature gap. This script is the tripwire. Run it from cron, a Task
    Scheduler job, an `npm start` postscript on the landing page server, or
    any uptime monitor that can hit a shell command.

What it does:
    1. Reads scheduler_heartbeat.json (written by scan_scheduler.py at the
       end of every scan).
    2. Compares last_scan_ts to "now" — if the gap exceeds the threshold,
       reports the scheduler as STALE.
    3. Inspects the heartbeat for hard failure signals (rate-limited beyond
       lift time, error message present, etc.).
    4. Prints a single human-readable summary line.
    5. Exits 0 if HEALTHY, 1 if STALE, 2 if RATE_LIMITED, 3 if ERROR,
       4 if NEVER_RUN (no heartbeat file at all).

Usage:
    python healthcheck.py
    python healthcheck.py --threshold-minutes 30
    python healthcheck.py --json     # machine-readable output

Pair with cron:
    */5 * * * * cd /path/to/Python\\ Coding && python healthcheck.py || \\
        curl -X POST -H 'Content-Type: application/json' -d '{"text":"SnipeWins scheduler unhealthy"}' \\
        https://hooks.slack.com/services/your/webhook/here
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Tuple


HERE = Path(__file__).parent
HEARTBEAT_FILE = HERE / "scheduler_heartbeat.json"

EXIT_HEALTHY      = 0
EXIT_STALE        = 1
EXIT_RATE_LIMITED = 2
EXIT_ERROR        = 3
EXIT_NEVER_RUN    = 4


def _load_heartbeat() -> Tuple[Dict[str, Any], str]:
    if not HEARTBEAT_FILE.exists():
        return {}, "heartbeat file not found — scheduler has never written a successful scan"
    try:
        return json.loads(HEARTBEAT_FILE.read_text(encoding="utf-8")), ""
    except Exception as exc:
        return {}, f"could not parse heartbeat file ({type(exc).__name__}: {exc})"


def _format_age(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds/60:.1f}m"
    return f"{seconds/3600:.1f}h"


def main() -> int:
    parser = argparse.ArgumentParser(description="Tripwire for the SnipeWins scan scheduler")
    parser.add_argument(
        "--threshold-minutes",
        type=float,
        default=30.0,
        help="Consider the scheduler stale if no heartbeat for this many minutes (default 30)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a single JSON object instead of a text summary",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress output on healthy state (useful for cron — only speak up on problems)",
    )
    args = parser.parse_args()

    hb, load_err = _load_heartbeat()
    now = time.time()

    result: Dict[str, Any] = {
        "checked_at":   now,
        "heartbeat_file": str(HEARTBEAT_FILE),
        "status":       "unknown",
        "exit_code":    EXIT_HEALTHY,
        "message":      "",
    }

    if not hb:
        result["status"]    = "never_run"
        result["exit_code"] = EXIT_NEVER_RUN
        result["message"]   = load_err or "no heartbeat — has the scheduler ever started?"
        return _emit(result, args)

    # Pull the relevant fields
    last_scan_ts        = float(hb.get("last_scan_ts") or 0.0)
    rate_limited        = bool(hb.get("rate_limited") or False)
    rate_limited_until  = float(hb.get("rate_limited_until") or 0.0)
    error               = str(hb.get("error") or "")
    interval_secs       = int(hb.get("interval_secs") or 900)
    duration_seconds    = float(hb.get("duration_seconds") or 0.0)
    deals_total         = int(hb.get("deals_total") or 0)

    age_s = max(0.0, now - last_scan_ts)
    threshold_s = args.threshold_minutes * 60.0

    # The scheduler runs on `interval_secs`; if the threshold is shorter than
    # one full interval plus typical scan duration we'll false-alarm. Floor
    # the threshold at 1.5 × interval + a 60s buffer.
    floor_s = (interval_secs * 1.5) + 60.0
    effective_threshold_s = max(threshold_s, floor_s)

    result["last_scan_ts"]            = last_scan_ts
    result["last_scan_iso"]           = hb.get("last_scan_iso", "")
    result["age_seconds"]             = round(age_s, 1)
    result["age_human"]               = _format_age(age_s)
    result["threshold_seconds"]       = effective_threshold_s
    result["threshold_human"]         = _format_age(effective_threshold_s)
    result["rate_limited"]            = rate_limited
    result["rate_limited_until_ts"]   = rate_limited_until
    result["last_error"]              = error
    result["last_duration_seconds"]   = duration_seconds
    result["last_deals_total"]        = deals_total
    result["interval_secs"]           = interval_secs

    # Decision tree (most severe condition wins)
    if error:
        result["status"]    = "error"
        result["exit_code"] = EXIT_ERROR
        result["message"]   = (
            f"last scan {result['age_human']} ago errored: {error[:160]}"
        )
    elif rate_limited and rate_limited_until > now:
        result["status"]    = "rate_limited"
        result["exit_code"] = EXIT_RATE_LIMITED
        result["message"]   = (
            f"rate-limited until {_format_age(rate_limited_until - now)} from now "
            f"(last scan {result['age_human']} ago)"
        )
    elif age_s > effective_threshold_s:
        result["status"]    = "stale"
        result["exit_code"] = EXIT_STALE
        result["message"]   = (
            f"no scan for {result['age_human']} (threshold {result['threshold_human']}) "
            f"— scheduler may be down"
        )
    else:
        result["status"]    = "healthy"
        result["exit_code"] = EXIT_HEALTHY
        result["message"]   = (
            f"last scan {result['age_human']} ago; "
            f"{deals_total} deals; "
            f"{duration_seconds:.0f}s duration; "
            f"threshold {result['threshold_human']}"
        )

    return _emit(result, args)


def _emit(result: Dict[str, Any], args) -> int:
    rc = int(result.get("exit_code", 0) or 0)
    if args.quiet and rc == 0:
        return rc
    if args.json:
        print(json.dumps(result, default=str, indent=2, sort_keys=True))
    else:
        print(f"[HEALTHCHECK] {result['status'].upper()} — {result['message']}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
