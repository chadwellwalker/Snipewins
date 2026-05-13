"""
snipes_store.py — Local persistence for "Add to Snipes" actions.

Designed to be the lightweight backbone for the SMS-notification feature:
when the user clicks "Add to Snipes" on a card, we record the snipe locally
and (eventually) fire a Twilio SMS with the eBay link + target price.

For now: local JSON store only. SMS dispatch is a separate concern that
this module exposes a hook for (`send_sms_if_configured`).

Snipe file shape:
{
    "snipes": [
        {
            "item_id":     "v1|123456789|0",
            "title":       "...",
            "ebay_url":    "https://...",
            "target_bid":  138.0,
            "current_bid": 215.0,
            "market_value": null,
            "ends_at":     1778455769.0,
            "added_at":    1778363951.7,
            "sms_sent":    false,
        },
        ...
    ],
    "version": 1
}
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


HERE = Path(__file__).parent
SNIPES_FILE = HERE / "snipes.json"


# ── Persistence ─────────────────────────────────────────────────────────────

def _load() -> Dict[str, Any]:
    if not SNIPES_FILE.exists():
        return {"version": 1, "snipes": []}
    try:
        return json.loads(SNIPES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "snipes": []}


def _save(store: Dict[str, Any]) -> None:
    """Atomic write — tmp file + os.replace so we can't half-write."""
    tmp = str(SNIPES_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(store, fh, indent=2, sort_keys=True)
    os.replace(tmp, SNIPES_FILE)


# ── Public API ──────────────────────────────────────────────────────────────

def list_snipes() -> List[Dict[str, Any]]:
    """Return all snipes, most-recently-added first."""
    store = _load()
    snipes = list(store.get("snipes") or [])
    snipes.sort(key=lambda s: float(s.get("added_at") or 0), reverse=True)
    return snipes


def is_sniped(item_id: str) -> bool:
    """True if this item_id is already on the snipes list."""
    if not item_id:
        return False
    return any(
        str(s.get("item_id") or "") == str(item_id)
        for s in _load().get("snipes") or []
    )


def add_snipe(row: Dict[str, Any]) -> Dict[str, Any]:
    """Add a card to the snipes list. Returns the snipe dict (whether
    newly added or existing). Idempotent — calling twice is a no-op on
    the second call."""
    item_id = str(
        row.get("item_id")
        or row.get("itemId")
        or row.get("source_item_id")
        or ""
    )
    if not item_id:
        raise ValueError("Cannot add snipe without an item_id")

    store = _load()
    snipes = list(store.get("snipes") or [])
    for existing in snipes:
        if str(existing.get("item_id") or "") == item_id:
            return existing  # already on the list — no-op

    # Build the snipe record from the row's known fields.
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
        "sms_sent":     False,
    }
    snipes.append(snipe)
    store["snipes"] = snipes
    _save(store)

    # Hook: fire SMS if Twilio is configured. No-op when env vars absent
    # so this never crashes the click handler.
    try:
        send_sms_if_configured(snipe)
    except Exception as exc:
        print(f"[snipes_store] SMS dispatch failed (non-fatal): {exc}")

    return snipe


def remove_snipe(item_id: str) -> bool:
    """Remove a snipe by item_id. Returns True if removed, False if not found."""
    if not item_id:
        return False
    store = _load()
    snipes = list(store.get("snipes") or [])
    new_snipes = [s for s in snipes if str(s.get("item_id") or "") != str(item_id)]
    if len(new_snipes) == len(snipes):
        return False
    store["snipes"] = new_snipes
    _save(store)
    return True


# ── Win/Lost resolution + ROI tracking ──────────────────────────────────────

def mark_snipe_resolved(
    item_id: str,
    status: str,
    final_price: Optional[float] = None,
    notes: Optional[str] = None,
) -> bool:
    """Mark a snipe as 'won' or 'lost'. Stamps final_price (the amount
    the user paid if won, OR the amount it ended up selling for if lost)
    plus a timestamp. Returns True on success, False if snipe not found.

    Used by the My Snipes tab to track ROI:
        - won + final_price <= target_bid → user got it under target = $ saved
        - won + final_price >  target_bid → user paid above target (still a win)
        - lost                              → no $ saved, but tracked for win rate
    """
    if not item_id or status not in ("won", "lost", "active"):
        return False
    store = _load()
    snipes = list(store.get("snipes") or [])
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
        store["snipes"] = snipes
        _save(store)
    return found


def compute_roi() -> Dict[str, Any]:
    """Aggregate ROI stats across all snipes. Used by the My Snipes tab
    header. Returns:
        {
            "total_snipes":     int,    # all snipes ever added
            "active":           int,    # status == 'active' (or unset)
            "won":              int,    # status == 'won'
            "lost":             int,    # status == 'lost'
            "win_rate":         float,  # won / (won + lost), 0..1
            "total_saved":      float,  # sum of (target_bid - final_price) for wins where final < target
            "total_overpaid":   float,  # sum of (final_price - target_bid) for wins where final > target
            "net_savings":      float,  # total_saved - total_overpaid
        }
    """
    store = _load()
    snipes = list(store.get("snipes") or [])

    total       = len(snipes)
    active      = 0
    won         = 0
    lost        = 0
    saved       = 0.0
    overpaid    = 0.0

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


# ── SMS dispatch hook (Twilio-ready, no-op until configured) ─────────────────

def send_sms_if_configured(snipe: Dict[str, Any]) -> bool:
    """
    Send an SMS via Twilio if the relevant env vars are set:
        TWILIO_ACCOUNT_SID
        TWILIO_AUTH_TOKEN
        TWILIO_FROM_NUMBER
        SNIPEWINS_USER_PHONE  (where to send the SMS)

    Returns True if sent, False if any required config is missing OR
    dispatch failed. Designed to be a safe no-op when not configured —
    the snipe still gets saved locally regardless.
    """
    sid   = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    from_ = os.environ.get("TWILIO_FROM_NUMBER", "").strip()
    to_   = os.environ.get("SNIPEWINS_USER_PHONE", "").strip()

    if not (sid and token and from_ and to_):
        return False  # not configured — silent no-op

    try:
        # Lazy import — don't require twilio installed unless user wires it.
        from twilio.rest import Client
        client = Client(sid, token)
        body = _format_sms_body(snipe)
        client.messages.create(body=body, from_=from_, to=to_)
        # Stamp the snipe so we don't re-text on the next launch
        store = _load()
        for s in store.get("snipes") or []:
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
