"""
quota_guard.py — per-user usage tracking and weekly cap enforcement.

Implements the tier mechanic from MONETIZATION_PLAN.md:

    FREE         3 scans / week, 5 reveals / week, 5 watchlist players
    PRO          unlimited scans, unlimited reveals, unlimited watchlist

A "scan" = a click that runs fetch_ending_soon_deals.
A "reveal" = unblurring a target bid for a single card. Each unique
             card-id reveal counts once per week (re-clicking the same
             card in the same week is free).

Usage from streamlit_app.py:

    from quota_guard import (
        can_run_scan,
        record_scan,
        can_reveal_target_bid,
        record_reveal,
        get_quota_summary,
    )

    if not can_run_scan(user_id):
        # render paywall modal: "You've used your 3 free scans this week."
        return
    record_scan(user_id)
    # ... run the scan ...

    if not can_reveal_target_bid(user_id, deal_id):
        # render blur + upgrade CTA on this card
        target_bid_display = "▒▒▒"
    else:
        record_reveal(user_id, deal_id)
        target_bid_display = f"${target_bid:.0f}"

State persistence:

    Stored in quota_state.json in the project folder. Atomic writes
    (tmp + replace) so a crash mid-write never corrupts state. NOT
    a database — fine for first hundred users. Migrate to SQLite or
    Postgres around user 100.

Single-user stub:

    Until auth exists, callers should pass user_id="local" (or any
    consistent string per-machine). When auth lands, replace "local"
    with the authenticated user's ID. No quota_guard.py changes needed.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Set, Tuple


HERE = Path(__file__).parent
STATE_FILE = HERE / "quota_state.json"
_STATE_LOCK = threading.Lock()

# ─── Tier definitions ──────────────────────────────────────────────────────
# Numbers come from MONETIZATION_PLAN.md. Update there first if you change
# them; this file is just the enforcement layer.

TIER_FREE = "free"
TIER_PRO  = "pro"

_FREE_LIMITS = {
    "scans_per_week":         3,
    "reveals_per_week":       5,
    "watchlist_max_players":  5,
}

_PRO_LIMITS = {
    "scans_per_week":         None,   # None = unlimited
    "reveals_per_week":       None,
    "watchlist_max_players":  None,
}


def _limits_for_tier(tier: str) -> Dict[str, Any]:
    return dict(_PRO_LIMITS) if str(tier or "").lower() == TIER_PRO else dict(_FREE_LIMITS)


# ─── Weekly window helper ──────────────────────────────────────────────────
# A "week" runs Sunday 00:00 UTC → next Sunday 00:00 UTC. Sunday is the
# rollover so users see a fresh quota at the start of the week, before the
# Sun-Mon evening peak hours begin.

def _current_week_id(now_utc: datetime = None) -> str:
    if now_utc is None:
        now_utc = datetime.now(tz=timezone.utc)
    # Move to most recent Sunday 00:00 UTC
    days_since_sunday = (now_utc.weekday() + 1) % 7  # weekday() Sun=6, Mon=0; we want Sun=0
    week_start = (now_utc - timedelta(days=days_since_sunday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return week_start.strftime("%Y-W%U")  # e.g. "2026-W18"


# ─── State load / save ─────────────────────────────────────────────────────
# State shape:
#   {
#       "users": {
#           "<user_id>": {
#               "tier": "free" | "pro",
#               "weeks": {
#                   "<week_id>": {
#                       "scans": <int>,
#                       "reveals": [ "<deal_id>", ... ]
#                   }
#               }
#           }
#       },
#       "version": 1
#   }
# Old weeks are pruned on every save (kept: most recent 4 weeks).

def _load_state() -> Dict[str, Any]:
    if not STATE_FILE.exists():
        return {"users": {}, "version": 1}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"users": {}, "version": 1}


def _save_state(state: Dict[str, Any]) -> None:
    # Prune any week older than 4 weeks for any user.
    try:
        cutoff = (datetime.now(tz=timezone.utc) - timedelta(weeks=4)).strftime("%Y-W%U")
        for _user in (state.get("users") or {}).values():
            weeks = _user.get("weeks") or {}
            for _w in list(weeks.keys()):
                if _w < cutoff:
                    del weeks[_w]
    except Exception:
        pass

    tmp = str(STATE_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
    os.replace(tmp, STATE_FILE)


def _get_user_record(state: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    users = state.setdefault("users", {})
    user = users.setdefault(user_id, {"tier": TIER_FREE, "weeks": {}})
    user.setdefault("tier", TIER_FREE)
    user.setdefault("weeks", {})
    return user


def _get_week_record(user_record: Dict[str, Any], week_id: str) -> Dict[str, Any]:
    weeks = user_record.setdefault("weeks", {})
    return weeks.setdefault(week_id, {"scans": 0, "reveals": []})


# ─── Public API ────────────────────────────────────────────────────────────

def get_user_tier(user_id: str) -> str:
    with _STATE_LOCK:
        state = _load_state()
        return str(_get_user_record(state, user_id).get("tier") or TIER_FREE)


def set_user_tier(user_id: str, tier: str) -> None:
    """Called when a user upgrades (Stripe webhook) or downgrades (cancel)."""
    if tier not in (TIER_FREE, TIER_PRO):
        raise ValueError(f"Unknown tier: {tier!r}")
    with _STATE_LOCK:
        state = _load_state()
        _get_user_record(state, user_id)["tier"] = tier
        _save_state(state)


def can_run_scan(user_id: str) -> bool:
    with _STATE_LOCK:
        state = _load_state()
        user = _get_user_record(state, user_id)
        limits = _limits_for_tier(user["tier"])
        if limits["scans_per_week"] is None:
            return True
        week = _get_week_record(user, _current_week_id())
        return int(week.get("scans") or 0) < int(limits["scans_per_week"])


def record_scan(user_id: str) -> None:
    with _STATE_LOCK:
        state = _load_state()
        user = _get_user_record(state, user_id)
        week = _get_week_record(user, _current_week_id())
        week["scans"] = int(week.get("scans") or 0) + 1
        _save_state(state)


def can_reveal_target_bid(user_id: str, deal_id: str) -> bool:
    """
    True if the user has either (a) Pro tier, (b) already revealed this
    specific deal this week (idempotent re-views are free), or
    (c) hasn't yet hit the weekly reveal cap.
    """
    with _STATE_LOCK:
        state = _load_state()
        user = _get_user_record(state, user_id)
        limits = _limits_for_tier(user["tier"])
        if limits["reveals_per_week"] is None:
            return True
        week = _get_week_record(user, _current_week_id())
        already_revealed: Set[str] = set(week.get("reveals") or [])
        if str(deal_id) in already_revealed:
            return True  # idempotent
        return len(already_revealed) < int(limits["reveals_per_week"])


def record_reveal(user_id: str, deal_id: str) -> bool:
    """
    Record that a user revealed a target bid. Returns True if newly added,
    False if it was already revealed this week (idempotent — no double-bill).
    """
    with _STATE_LOCK:
        state = _load_state()
        user = _get_user_record(state, user_id)
        week = _get_week_record(user, _current_week_id())
        reveals = list(week.get("reveals") or [])
        deal_id_s = str(deal_id)
        if deal_id_s in reveals:
            return False
        reveals.append(deal_id_s)
        week["reveals"] = reveals
        _save_state(state)
        return True


def can_add_to_watchlist(user_id: str, current_watchlist_size: int) -> bool:
    with _STATE_LOCK:
        state = _load_state()
        user = _get_user_record(state, user_id)
        limits = _limits_for_tier(user["tier"])
        if limits["watchlist_max_players"] is None:
            return True
        return int(current_watchlist_size) < int(limits["watchlist_max_players"])


def get_quota_summary(user_id: str) -> Dict[str, Any]:
    """
    For UI rendering. Returns a snapshot of the user's current week:
        {
            "tier": "free" | "pro",
            "week_id": "2026-W18",
            "scans_used": 2,
            "scans_limit": 3,        # None means unlimited
            "scans_remaining": 1,    # None means unlimited
            "reveals_used": 4,
            "reveals_limit": 5,
            "reveals_remaining": 1,
            "watchlist_limit": 5,
            "next_reset_iso": "2026-05-10T00:00:00+00:00",
        }
    """
    with _STATE_LOCK:
        state = _load_state()
        user = _get_user_record(state, user_id)
        tier = str(user["tier"])
        limits = _limits_for_tier(tier)
        week_id = _current_week_id()
        week = _get_week_record(user, week_id)
        scans_used   = int(week.get("scans") or 0)
        reveals_used = len(week.get("reveals") or [])

        def _remaining(used: int, limit: Any) -> Any:
            if limit is None:
                return None
            return max(0, int(limit) - int(used))

        # Compute next reset (next Sunday 00:00 UTC)
        now = datetime.now(tz=timezone.utc)
        days_to_next_sunday = (6 - now.weekday()) % 7 or 7  # if today IS Sunday, next is 7 days
        next_reset = (now + timedelta(days=days_to_next_sunday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        return {
            "tier":              tier,
            "week_id":           week_id,
            "scans_used":        scans_used,
            "scans_limit":       limits["scans_per_week"],
            "scans_remaining":   _remaining(scans_used, limits["scans_per_week"]),
            "reveals_used":      reveals_used,
            "reveals_limit":     limits["reveals_per_week"],
            "reveals_remaining": _remaining(reveals_used, limits["reveals_per_week"]),
            "watchlist_limit":   limits["watchlist_max_players"],
            "next_reset_iso":    next_reset.isoformat(),
        }


# ─── Self-test (run `python quota_guard.py` to verify) ────────────────────

if __name__ == "__main__":
    test_user = "test_self_check"
    # Reset any prior state for the test user
    with _STATE_LOCK:
        s = _load_state()
        if test_user in (s.get("users") or {}):
            del s["users"][test_user]
        _save_state(s)

    assert can_run_scan(test_user), "free user should start with scans available"
    record_scan(test_user)
    record_scan(test_user)
    record_scan(test_user)
    assert not can_run_scan(test_user), "free user should be capped after 3 scans"

    assert can_reveal_target_bid(test_user, "deal-1"), "free user starts with reveals"
    record_reveal(test_user, "deal-1")
    record_reveal(test_user, "deal-2")
    record_reveal(test_user, "deal-3")
    record_reveal(test_user, "deal-4")
    record_reveal(test_user, "deal-5")
    assert not can_reveal_target_bid(test_user, "deal-6"), "should be capped after 5 reveals"
    assert can_reveal_target_bid(test_user, "deal-1"), "re-revealing same deal is free"

    set_user_tier(test_user, TIER_PRO)
    assert can_run_scan(test_user), "pro should bypass the scan cap"
    assert can_reveal_target_bid(test_user, "deal-99"), "pro should bypass the reveal cap"

    summary = get_quota_summary(test_user)
    assert summary["tier"] == TIER_PRO
    assert summary["scans_remaining"] is None
    print("quota_guard self-test PASSED")
    print(json.dumps(summary, indent=2))
