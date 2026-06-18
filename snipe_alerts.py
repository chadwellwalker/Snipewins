"""
snipe_alerts.py — Ending-soon email alerts for tracked snipes.

When a user adds a card to My Snipes, they're saying "I want to act on this
before it ends." This module emails them when one of those cards is about to
close, with the live current bid, market value, and their target cap — the
exact moment of value for an auction-sniping tool.

Flow (run_once, called from the worker loop like email_drip):
    1. Cadence guard — only sweep every ALERT_SWEEP_INTERVAL_SECONDS.
    2. snipes_store.iter_snipes_ending_within(window) → (email, snipe) for
       active snipes ending within the alert window, not yet alerted.
    3. For each, if the user has ending_alert_optin on, send the email and
       mark the snipe alert_email_sent=True so it fires at most once.

Window:
    ALERT_WINDOW_SECONDS (default 900 = 15 min). The worker loop is 60s, so
    a card entering the final 15 minutes gets caught within ~a minute. Email
    (not SMS) deliberately — no TCPA / 10DLC overhead, infra already exists.

Persistence:
    SNIPEWINS_SNIPE_ALERT_STATE_PATH → snipe_alert_state.json on the
    persistent disk so the cadence guard survives redeploys.

Never raises — all errors caught and logged so the worker loop is unaffected.
ENDING-ALERT-2026-05-20.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict


HERE = Path(__file__).parent
STATE_FILE = Path(
    os.environ.get("SNIPEWINS_SNIPE_ALERT_STATE_PATH")
    or str(HERE / "snipe_alert_state.json")
)

# How far out to start alerting. 15 min gives the user time to open eBay and
# bid before the close.
ALERT_WINDOW_SECONDS = float(os.environ.get("SNIPEWINS_SNIPE_ALERT_WINDOW_SECONDS") or 900)

# Don't iterate the snipes store every 60s worker cycle — every ~2 min is
# plenty given the 15-min window (a card can't slip through in 2 min).
ALERT_SWEEP_INTERVAL_SECONDS = float(os.environ.get("SNIPEWINS_SNIPE_ALERT_INTERVAL_SECONDS") or 120)


def _load_state() -> Dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _save_state(state: Dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(STATE_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
    os.replace(tmp, STATE_FILE)


def _seconds_since_last_run() -> float:
    last = float(_load_state().get("last_run_ts") or 0)
    if last <= 0:
        return float("inf")
    return time.time() - last


def _fresh_current_bid(item_id: str) -> Any:
    """Look up the freshest current bid for an item from the live pools.
    The snipe record snapshots current_bid at ADD time, which can be hours
    stale by the time the card is ending — and near_end_refresher keeps the
    pool's current_price current for ending-soon cards. So we prefer the
    pool value and fall back to the snipe snapshot if the item isn't found.
    Returns a float or None. Failure-quiet."""
    if not item_id:
        return None
    for env_var, default_name in (
        ("SNIPEWINS_AUCTION_POOL_PATH", "daily_pool.json"),
        ("SNIPEWINS_BIN_POOL_PATH", "bin_pool.json"),
    ):
        try:
            from snipewins_paths import state_path as _state_path
            path = _state_path(env_var, default_name)
            if not path.exists():
                continue
            pool = json.loads(path.read_text(encoding="utf-8")) or {}
            row = (pool.get("items") or {}).get(item_id)
            if not isinstance(row, dict):
                continue
            for k in ("_authoritative_current_price", "current_price", "current_bid"):
                v = row.get(k)
                try:
                    if v is not None and float(v) > 0:
                        return float(v)
                except Exception:
                    pass
        except Exception:
            continue
    return None


def run_once(force: bool = False) -> Dict[str, Any]:
    """Sweep tracked snipes and email any that are ending soon. Cheap on
    cycles where the cadence window hasn't elapsed. Never raises."""
    started = time.time()
    summary: Dict[str, Any] = {
        "ran":            False,
        "skipped_reason": "",
        "sent":           0,
        "skipped_optout": 0,
        "failed":         0,
    }

    if not force:
        age = _seconds_since_last_run()
        if age < ALERT_SWEEP_INTERVAL_SECONDS:
            summary["skipped_reason"] = f"cadence_guard ({age:.0f}s < {ALERT_SWEEP_INTERVAL_SECONDS:.0f}s)"
            return summary

    summary["ran"] = True

    try:
        import snipes_store
        import trial_accounts
        import email_sender
    except Exception as exc:
        summary["skipped_reason"] = f"import_error:{type(exc).__name__}:{str(exc)[:80]}"
        return summary

    # Backfill ends_at on snipes that don't have it (added before the field
    # existed, or the pool row lacked the timestamp at add time) so they can
    # actually alert. Cheap; no-op once everything's backfilled.
    try:
        _bf = snipes_store.backfill_missing_ends_at()
        if _bf:
            print(f"[snipe_alerts] backfilled ends_at on {_bf} snipe(s)", flush=True)
    except Exception as exc:
        print(f"[snipe_alerts] backfill error (non-fatal): {type(exc).__name__}: {exc}", flush=True)

    try:
        due = snipes_store.iter_snipes_ending_within(ALERT_WINDOW_SECONDS)
    except Exception as exc:
        summary["skipped_reason"] = f"iter_error:{type(exc).__name__}:{str(exc)[:80]}"
        return summary

    for email, snipe in due:
        try:
            # Respect the per-user opt-in. Default is on (see
            # trial_accounts.get_ending_alert_optin), but a user who turned
            # it off on My Snipes is honored here.
            if not trial_accounts.get_ending_alert_optin(email):
                summary["skipped_optout"] += 1
                continue
            # Freshen the current bid from the live pool so the email isn't
            # showing the stale add-time snapshot. Pass a shallow copy so we
            # don't mutate the stored record.
            _snipe_for_email = dict(snipe)
            _fresh = _fresh_current_bid(str(snipe.get("item_id") or ""))
            if _fresh is not None:
                _snipe_for_email["current_bid"] = _fresh
            if email_sender.send_ending_soon_alert(email, _snipe_for_email):
                snipes_store.mark_alert_email_sent(email, str(snipe.get("item_id") or ""))
                summary["sent"] += 1
            else:
                summary["failed"] += 1
        except Exception as exc:
            summary["failed"] += 1
            print(f"[snipe_alerts] send failed for {email}: {type(exc).__name__}: {exc}", flush=True)

    # Record this run.
    try:
        state = _load_state()
        state["last_run_ts"]  = started
        state["last_summary"] = summary
        state["last_run_iso"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started))
        _save_state(state)
    except Exception as exc:
        print(f"[snipe_alerts] state save failed: {type(exc).__name__}: {exc}", flush=True)

    if summary["sent"] + summary["failed"] > 0:
        print(
            f"[snipe_alerts] sweep done — sent={summary['sent']} "
            f"failed={summary['failed']} skipped_optout={summary['skipped_optout']} "
            f"elapsed={round(time.time() - started, 2)}s",
            flush=True,
        )
    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="snipe_alerts.py — ending-soon email sweep")
    parser.add_argument("--force", action="store_true", help="Bypass the cadence guard")
    parser.add_argument("--status", action="store_true", help="Print state and exit")
    args = parser.parse_args()
    if args.status:
        print(json.dumps(_load_state(), indent=2))
    else:
        print(json.dumps(run_once(force=args.force), indent=2))
