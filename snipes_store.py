"""
snipes_store.py — Per-user persistence for "Add to Snipes" actions.

MULTI-TENANCY-2026-05-13: rewritten from a single global snipes list to
per-user buckets keyed by email. Before this change every user saw the
SAME snipes (a data-isolation bug — your test cards showed up for
everyone, and real users would have seen each other's snipes). Now each
user has their own isolated bucket.

Every public function takes `email` as its first argument. The Streamlit
views read the email from st.session_state["sw_trial_user_email"] (set by
trial_gate) and pass it through. If email is missing/None we fall back to
an "_anonymous" bucket so nothing crashes — but in normal operation every
caller has a real email.

Storage file shape (v2):
{
    "version": 2,
    "users": {
        "user@example.com": {
            "snipes": [
                {
                    "item_id":      "v1|123456789|0",
                    "title":        "...",
                    "ebay_url":     "https://...",
                    "target_bid":   138.0,
                    "current_bid":  215.0,
                    "market_value": null,
                    "ends_at":      1778455769.0,
                    "added_at":     1778363951.7,
                    "status":       "active",
                    "sms_sent":     false
                },
                ...
            ]
        },
        ...
    }
}

A v1 file (flat {"version": 1, "snipes": [...]}) is intentionally NOT
migrated — those are pre-launch test cards. The loader just starts fresh
on v2 if it sees the old shape.

Persistence path is configurable via SNIPEWINS_SNIPES_PATH env var so it
can live on a Render persistent disk (same pattern as accounts.json).
Without that, snipes wipe on every redeploy.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


HERE = Path(__file__).parent
# PERSISTENT-STORE-2026-05-13: point this at the Render disk in prod
# (e.g. /data/snipes.json) so users' snipes survive restarts/redeploys.
SNIPES_FILE = Path(os.environ.get("SNIPEWINS_SNIPES_PATH") or str(HERE / "snipes.json"))

# Fallback bucket key when a caller doesn't have an email (gate failed
# open, local debugging, etc). Keeps the store from crashing — it just
# won't be isolated, which is acceptable in those degraded cases.
_ANON_BUCKET = "_anonymous"


# ── Persistence ─────────────────────────────────────────────────────────────

def _empty_store() -> Dict[str, Any]:
    return {"version": 2, "users": {}}


def _load() -> Dict[str, Any]:
    """Read the snipes file. Always returns a canonical v2 shape. A v1
    (flat global list) file is treated as empty — those snipes were
    pre-launch test data and we don't want them leaking to real users."""
    if not SNIPES_FILE.exists():
        return _empty_store()
    try:
        data = json.loads(SNIPES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return _empty_store()
    if not isinstance(data, dict):
        return _empty_store()
    # v1 detection: old flat shape had a top-level "snipes" list and no
    # "users" dict. Drop it — start fresh on v2.
    if "users" not in data or not isinstance(data.get("users"), dict):
        return _empty_store()
    data.setdefault("version", 2)
    return data


def _save(store: Dict[str, Any]) -> None:
    """Atomic write — tmp file + os.replace so we can't half-write."""
    SNIPES_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(SNIPES_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(store, fh, indent=2, sort_keys=True)
    os.replace(tmp, SNIPES_FILE)


def _normalize_email(email: Optional[str]) -> str:
    """Lowercase + strip. Falls back to the anonymous bucket when empty
    so callers never have to None-check before calling us."""
    em = str(email or "").strip().lower()
    return em or _ANON_BUCKET


def _user_snipes(store: Dict[str, Any], email: str) -> List[Dict[str, Any]]:
    """Return the (mutable) snipes list for one user, creating the bucket
    if it doesn't exist yet."""
    users = store.setdefault("users", {})
    bucket = users.setdefault(email, {})
    snipes = bucket.setdefault("snipes", [])
    if not isinstance(snipes, list):
        snipes = []
        bucket["snipes"] = snipes
    return snipes


# ── Public API ──────────────────────────────────────────────────────────────

def list_snipes(email: str) -> List[Dict[str, Any]]:
    """Return all of one user's snipes, most-recently-added first."""
    em = _normalize_email(email)
    store = _load()
    snipes = list(_user_snipes(store, em))
    snipes.sort(key=lambda s: float(s.get("added_at") or 0), reverse=True)
    return snipes


def is_sniped(email: str, item_id: str) -> bool:
    """True if this item_id is already on this user's snipes list."""
    if not item_id:
        return False
    em = _normalize_email(email)
    store = _load()
    return any(
        str(s.get("item_id") or "") == str(item_id)
        for s in _user_snipes(store, em)
    )


def add_snipe(email: str, row: Dict[str, Any]) -> Dict[str, Any]:
    """Add a card to this user's snipes list. Returns the snipe dict
    (whether newly added or pre-existing). Idempotent per (user, item_id)."""
    item_id = str(
        row.get("item_id")
        or row.get("itemId")
        or row.get("source_item_id")
        or ""
    )
    if not item_id:
        raise ValueError("Cannot add snipe without an item_id")

    em = _normalize_email(email)
    store = _load()
    snipes = _user_snipes(store, em)
    for existing in snipes:
        if str(existing.get("item_id") or "") == item_id:
            return existing  # already on this user's list — no-op

    snipe: Dict[str, Any] = {
        "item_id":      item_id,
        "title":        str(row.get("title") or row.get("source_title") or "")[:200],
        "ebay_url":     _row_ebay_url(row),
        "target_bid":   _safe_float(
            row.get("target_bid")
            or row.get("_final_target_bid")
            or row.get("_bid_anchor")
        ),
        "current_bid":  _safe_float(
            row.get("current_price")
            or row.get("current_bid")
            or row.get("_authoritative_current_price")
        ),
        "market_value": _safe_float(
            row.get("true_mv") or row.get("market_value")
        ),
        "ends_at":      _safe_float(row.get("_pool_end_dt_ts")),
        "thumbnail":    _row_thumbnail(row),
        "added_at":     time.time(),
        "status":       "active",
        "sms_sent":     False,
    }
    snipes.append(snipe)
    _save(store)

    # Hook: fire SMS if Twilio is configured. Legacy single-user path —
    # kept as a safe no-op for multi-user (SNIPEWINS_USER_PHONE can't be
    # per-user). Real per-user notifications will go through email later.
    try:
        send_sms_if_configured(em, snipe)
    except Exception as exc:
        print(f"[snipes_store] SMS dispatch failed (non-fatal): {exc}")

    return snipe


def remove_snipe(email: str, item_id: str) -> bool:
    """Remove one of a user's snipes by item_id. Returns True if removed."""
    if not item_id:
        return False
    em = _normalize_email(email)
    store = _load()
    snipes = _user_snipes(store, em)
    new_snipes = [s for s in snipes if str(s.get("item_id") or "") != str(item_id)]
    if len(new_snipes) == len(snipes):
        return False
    store["users"][em]["snipes"] = new_snipes
    _save(store)
    return True


# ── Win/Lost resolution + ROI tracking ──────────────────────────────────────

def mark_snipe_resolved(
    email: str,
    item_id: str,
    status: str,
    final_price: Optional[float] = None,
    notes: Optional[str] = None,
) -> bool:
    """Mark one of a user's snipes as 'won', 'lost', or 'active'. Stamps
    final_price + timestamp. Returns True on success, False if not found.

    ROI interpretation (used by the My Snipes tab):
        - won + final_price <= target_bid → user got it under target = $ saved
        - won + final_price >  target_bid → user paid above target (still a win)
        - lost                            → no $ saved, tracked for win rate
    """
    if not item_id or status not in ("won", "lost", "active"):
        return False
    em = _normalize_email(email)
    store = _load()
    snipes = _user_snipes(store, em)
    found = False
    for s in snipes:
        if str(s.get("item_id") or "") != str(item_id):
            continue
        s["status"]      = status
        s["resolved_at"] = time.time()
        if final_price is not None:
            try:
                s["final_price"] = float(final_price)
            except Exception:
                pass
        if notes is not None:
            s["notes"] = str(notes)[:500]
        found = True
        break
    if found:
        _save(store)
    return found


def compute_roi(email: str) -> Dict[str, Any]:
    """Aggregate ROI stats across ONE user's snipes. Used by the My Snipes
    tab header. Returns total_snipes, active, won, lost, win_rate,
    total_saved, total_overpaid, net_savings."""
    em = _normalize_email(email)
    store = _load()
    snipes = list(_user_snipes(store, em))

    total    = len(snipes)
    active   = 0
    won      = 0
    lost     = 0
    saved    = 0.0
    overpaid = 0.0

    for s in snipes:
        status = str(s.get("status") or "active").lower()
        if status == "won":
            won += 1
            tb = _safe_float(s.get("target_bid"))
            fp = _safe_float(s.get("final_price"))
            if tb is not None and fp is not None:
                if fp <= tb:
                    saved += (tb - fp)
                else:
                    overpaid += (fp - tb)
        elif status == "lost":
            lost += 1
        else:
            active += 1

    win_rate = (won / (won + lost)) if (won + lost) > 0 else 0.0
    return {
        "total_snipes":   int(total),
        "active":         int(active),
        "won":            int(won),
        "lost":           int(lost),
        "win_rate":       float(win_rate),
        "total_saved":    float(saved),
        "total_overpaid": float(overpaid),
        "net_savings":    float(saved - overpaid),
    }


# ── SMS dispatch hook (legacy single-user, Twilio-ready, no-op until configured) ─

def send_sms_if_configured(email: str, snipe: Dict[str, Any]) -> bool:
    """LEGACY: single-user SMS via Twilio. Kept as a safe no-op for the
    multi-user world — SNIPEWINS_USER_PHONE is a single number and can't
    be per-user. Real per-user notifications will go through email
    (Resend) in a follow-up. Returns False unless fully configured.
    """
    sid   = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    from_ = os.environ.get("TWILIO_FROM_NUMBER", "").strip()
    to_   = os.environ.get("SNIPEWINS_USER_PHONE", "").strip()

    if not (sid and token and from_ and to_):
        return False  # not configured — silent no-op

    try:
        from twilio.rest import Client
        client = Client(sid, token)
        body = _format_sms_body(snipe)
        client.messages.create(body=body, from_=from_, to=to_)
        em = _normalize_email(email)
        store = _load()
        for s in _user_snipes(store, em):
            if str(s.get("item_id")) == str(snipe.get("item_id")):
                s["sms_sent"] = True
                s["sms_sent_at"] = time.time()
        _save(store)
        return True
    except Exception as exc:
        print(f"[snipes_store] Twilio error: {exc}")
        return False


def _format_sms_body(snipe: Dict[str, Any]) -> str:
    """Compose the SMS text. Kept short for carrier-friendly length."""
    title  = str(snipe.get("title") or "")[:80]
    target = snipe.get("target_bid")
    url    = snipe.get("ebay_url") or ""
    target_str = f"${float(target):,.0f}" if target else "(no target yet)"
    return f"SnipeWins target: {target_str}\n{title}\n{url}"


# ── Local helpers ──────────────────────────────────────────────────────────

def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        f = float(value)
        return f if f > 0 else None
    except Exception:
        return None


def _row_ebay_url(row: Dict[str, Any]) -> Optional[str]:
    for k in ("url", "_board_url", "itemWebUrl", "listing_url"):
        v = (row or {}).get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v
    item_id = str(
        (row or {}).get("item_id")
        or (row or {}).get("itemId")
        or (row or {}).get("source_item_id")
        or ""
    )
    if "|" in item_id:
        parts = item_id.split("|")
        if len(parts) >= 2 and parts[1].isdigit():
            return f"https://www.ebay.com/itm/{parts[1]}"
    return None


def _row_thumbnail(row: Dict[str, Any]) -> Optional[str]:
    for k in ("thumbnail", "image_url"):
        v = (row or {}).get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v
    nested = (row or {}).get("image") or {}
    if isinstance(nested, dict):
        v = nested.get("imageUrl")
        if isinstance(v, str) and v.startswith("http"):
            return v
    return None
