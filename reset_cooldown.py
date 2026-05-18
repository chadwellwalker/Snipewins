"""
reset_cooldown.py — ops CLI to unstick a worker parked in a long cooldown.

When ebay_search.py's cooldown ladder escalates to the top (1h) and 429s
keep firing on resume, the worker can sit idle for hours. This script:

    1. Resets the in-memory cooldown state in ebay_search (only works
       inside the same process, so this is mostly useful from a Python
       shell — for cross-process resets see option (3) below).
    2. Prints the current daily_budget situation so you can see whether
       calls_today is actually at the cap or not.
    3. Optionally clears the daily_budget counter via --reset-budget so
       a stale local counter that's drifted past reality doesn't lock
       out fresh attempts.

Usage on Render shell:
    python reset_cooldown.py                # print status, do nothing
    python reset_cooldown.py --reset-state  # reset in-process cooldown vars
    python reset_cooldown.py --reset-budget # zero daily call counter

NOTE: this is a debug/ops tool, not user-facing. The cooldown ladder
exists for good reasons (auto-protects us from burning the eBay quota).
Only reset when you've confirmed the quota isn't actually exhausted.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))


def _print_status() -> None:
    """Snapshot of every guardrail counter the worker checks."""
    print("=== Daily budget ===")
    try:
        import daily_budget
        summary = daily_budget.get_budget_summary()
        print(json.dumps(summary, indent=2))
    except Exception as exc:
        print(f"  ERROR reading daily_budget: {type(exc).__name__}: {exc}")
    print()
    print("=== ebay_search cooldown state (in-process) ===")
    try:
        import ebay_search
        # Read module-level globals directly.
        print(json.dumps({
            "consecutive_429s":             getattr(ebay_search, "_consecutive_429s", "?"),
            "consecutive_cooldowns":        getattr(ebay_search, "_consecutive_cooldowns", "?"),
            "last_was_rate_limited":        getattr(ebay_search, "_last_was_rate_limited", "?"),
            "rate_limit_cooldown_until_ts": getattr(ebay_search, "_rate_limit_cooldown_until_ts", "?"),
        }, indent=2))
        # Note: this is THIS process's view. The worker process has its
        # own in-memory copy — these are separate.
        print("  NOTE: each process has its own copy. To reset the WORKER's")
        print("  cooldown you have to either restart the worker or trigger a")
        print("  successful fetch (the success-path resets the counters).")
    except Exception as exc:
        print(f"  ERROR importing ebay_search: {type(exc).__name__}: {exc}")
    print()
    print("=== near_end_refresher state ===")
    try:
        import near_end_refresher
        state = near_end_refresher._load_state()
        print(json.dumps(state, indent=2))
    except Exception as exc:
        print(f"  ERROR reading near_end state: {type(exc).__name__}: {exc}")


def _reset_state() -> None:
    """Reset the in-process ebay_search cooldown counters. Only affects
    THIS Python invocation — for the running worker, restart it instead."""
    try:
        import ebay_search
        ebay_search._consecutive_429s = 0
        ebay_search._consecutive_cooldowns = 0
        ebay_search._last_was_rate_limited = False
        ebay_search._rate_limit_cooldown_until_ts = 0.0
        print("[reset_cooldown] ebay_search cooldown state cleared (in-process)")
        print("[reset_cooldown] NOTE: worker process has its own state — restart it")
        print("[reset_cooldown] or trigger a successful fetch to clear the worker's view.")
    except Exception as exc:
        print(f"[reset_cooldown] ERROR: {type(exc).__name__}: {exc}")


def _reset_budget() -> None:
    """Zero the daily_budget counter file. Use only if you're confident
    the on-disk count has drifted high vs eBay's actual count — otherwise
    you'll bypass quota protection and risk hitting eBay's real 5,000/day
    cap with no soft floor."""
    try:
        import daily_budget
        state = daily_budget._load()
        prev = int(state.get("calls_today") or 0)
        state["calls_today"] = 0
        daily_budget._save(state)
        print(f"[reset_cooldown] daily_budget counter reset: {prev} → 0")
        print(f"[reset_cooldown] NOTE: if eBay's real-side count was already high")
        print(f"[reset_cooldown] you'll keep getting 429s regardless of this reset.")
    except Exception as exc:
        print(f"[reset_cooldown] ERROR: {type(exc).__name__}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset stuck cooldown / budget state")
    parser.add_argument("--reset-state", action="store_true",
                        help="Reset in-process ebay_search cooldown counters")
    parser.add_argument("--reset-budget", action="store_true",
                        help="Zero the daily_budget calls_today counter")
    args = parser.parse_args()

    if args.reset_state:
        _reset_state()
    if args.reset_budget:
        _reset_budget()
    print()
    _print_status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
