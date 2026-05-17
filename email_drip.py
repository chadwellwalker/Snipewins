"""
email_drip.py — Marketing-email sweep for SnipeWins.

Runs `run_once()` periodically (piggybacking on valuation_worker's 60s
loop) and sends the two MARKETING emails when users meet the trigger
conditions:

    1. Trial-followup (+48h after expiry, unpaid, opted in) →
       email_sender.send_trial_followup
    2. Unverified-nudge (+24h after signup, magic link unclicked, opted in) →
       email_sender.send_unverified_nudge (with a freshly-minted token)

Transactional emails (trial-expired immediate, welcome-after-payment)
are NOT handled here — those are fired from trial_gate.py at the moment
the event happens. This module is for the time-delayed marketing sends.

Cadence guard:
    `run_once()` is called from the worker's 60s loop. We don't want to
    iterate the accounts file 60 times an hour. A small JSON state file
    tracks the last successful sweep timestamp; if less than
    DRIP_INTERVAL_SECONDS has passed, the function returns immediately.

Persistence:
    Same env-var pattern as accounts/snipes/mv_cache/budget: point
    SNIPEWINS_DRIP_STATE_PATH at /data/email_drip_state.json in production
    so the cadence guard survives redeploys.

EMAIL-CONVERSION-2026-05-15.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict


HERE = Path(__file__).parent
DRIP_STATE_FILE = Path(
    os.environ.get("SNIPEWINS_DRIP_STATE_PATH") or str(HERE / "email_drip_state.json")
)

# How often to actually run a sweep. Worker calls run_once() every cycle
# (~60s); the cadence guard skips most calls. Hourly is the right balance:
# we only need to send these emails once every ~hour at most, and an hour
# of latency on a marketing send is invisible to users.
DRIP_INTERVAL_SECONDS = int(os.environ.get("SNIPEWINS_DRIP_INTERVAL_SECONDS") or 3600)


# ── State persistence ─────────────────────────────────────────────────────

def _load_state() -> Dict[str, Any]:
    if not DRIP_STATE_FILE.exists():
        return {}
    try:
        return json.loads(DRIP_STATE_FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _save_state(state: Dict[str, Any]) -> None:
    DRIP_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(DRIP_STATE_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
    os.replace(tmp, DRIP_STATE_FILE)


def _seconds_since_last_run() -> float:
    state = _load_state()
    last = float(state.get("last_run_ts") or 0)
    if last <= 0:
        return float("inf")
    return time.time() - last


# ── Public API ─────────────────────────────────────────────────────────────

def run_once(force: bool = False) -> Dict[str, Any]:
    """Check both marketing-email conditions and fire any due sends.
    Guarded by DRIP_INTERVAL_SECONDS so calls within the cadence window
    early-return without doing work. Pass force=True to bypass the guard
    (useful for manual / CLI runs).

    Returns a small summary dict for logging. NEVER raises — all errors
    are caught and logged so the caller (the worker loop) is unaffected."""
    started = time.time()
    summary: Dict[str, Any] = {
        "ran":               False,
        "skipped_reason":    "",
        "followup_sent":     0,
        "followup_failed":   0,
        "nudge_sent":        0,
        "nudge_failed":      0,
    }

    # Cadence guard.
    if not force:
        age = _seconds_since_last_run()
        if age < DRIP_INTERVAL_SECONDS:
            summary["skipped_reason"] = f"cadence_guard ({age:.0f}s < {DRIP_INTERVAL_SECONDS}s)"
            return summary

    summary["ran"] = True

    try:
        import trial_accounts
        import email_sender
    except Exception as exc:
        summary["skipped_reason"] = f"import_error:{type(exc).__name__}:{str(exc)[:80]}"
        return summary

    # ── Sweep 1: trial-expired followup (+48h, unpaid, opted in) ────────
    try:
        followup_emails = trial_accounts.users_needing_trial_followup(
            min_hours_since_expiry=48.0,
        )
        for em in followup_emails:
            try:
                if email_sender.send_trial_followup(em):
                    trial_accounts.mark_trial_followup_email_sent(em)
                    summary["followup_sent"] += 1
                else:
                    summary["followup_failed"] += 1
            except Exception as exc:
                summary["followup_failed"] += 1
                print(f"[email_drip] followup send failed for {em}: {type(exc).__name__}: {exc}")
    except Exception as exc:
        print(f"[email_drip] followup sweep error: {type(exc).__name__}: {exc}")

    # ── Sweep 2: unverified nudge (+24h, magic_token_used=False, opted in)
    try:
        nudge_emails = trial_accounts.users_needing_unverified_nudge(
            min_hours_since_signup=24.0,
        )
        # Pull APP_BASE_URL the same way trial_gate does so the magic
        # link points at the right environment.
        app_base = os.environ.get("SNIPEWINS_APP_BASE_URL", "http://localhost:8501").rstrip("/")
        for em in nudge_emails:
            try:
                # Rotate a fresh magic token for this user so the link
                # they click is valid (single-use, 24h TTL).
                token = trial_accounts.signup_email(em, password=None)
                if not token:
                    summary["nudge_failed"] += 1
                    continue
                magic_link_url = f"{app_base}/?token={token}"
                if email_sender.send_unverified_nudge(em, magic_link_url):
                    trial_accounts.mark_unverified_nudge_sent(em)
                    summary["nudge_sent"] += 1
                else:
                    summary["nudge_failed"] += 1
            except Exception as exc:
                summary["nudge_failed"] += 1
                print(f"[email_drip] nudge send failed for {em}: {type(exc).__name__}: {exc}")
    except Exception as exc:
        print(f"[email_drip] nudge sweep error: {type(exc).__name__}: {exc}")

    # Record this run.
    try:
        state = _load_state()
        state["last_run_ts"]      = started
        state["last_summary"]     = summary
        state["last_run_iso"]     = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started))
        _save_state(state)
    except Exception as exc:
        print(f"[email_drip] state save failed: {type(exc).__name__}: {exc}")

    elapsed = round(time.time() - started, 2)
    if (summary["followup_sent"] + summary["nudge_sent"]
            + summary["followup_failed"] + summary["nudge_failed"]) > 0:
        print(
            f"[email_drip] sweep done in {elapsed}s — "
            f"followup_sent={summary['followup_sent']} "
            f"followup_failed={summary['followup_failed']} "
            f"nudge_sent={summary['nudge_sent']} "
            f"nudge_failed={summary['nudge_failed']}",
            flush=True,
        )
    return summary


# ── CLI for ops / debugging ────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="email_drip.py — marketing sweep")
    parser.add_argument("--force", action="store_true",
                        help="Bypass the cadence guard and run immediately")
    parser.add_argument("--status", action="store_true",
                        help="Print current drip state without sending")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(_load_state(), indent=2))
    else:
        result = run_once(force=args.force)
        print(json.dumps(result, indent=2))
