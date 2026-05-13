"""
Persistent manual comp review, per-canonical-key MV overrides, and lightweight
learned weight adjustments from approve/reject history.

Sits on top of automated valuation; corrupt files load as empty defaults.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import parallel_vocab

DEFAULT_STATE_PATH = os.path.join(os.path.dirname(__file__) or ".", "manual_comp_state.json")

_STATE_VERSION = 1

# Token learning: skip very common filler tokens
_LEARN_STOP = frozenset(
    """
    the and for with from this that card listing ebay psa bgs sgc cgc slab graded
    mint nm near pack fresh lot see pics photo read description
    """.split()
)


def _norm_token(t: str) -> str:
    s = (t or "").lower().strip()
    return s if len(s) >= 3 and s not in _LEARN_STOP else ""


def tokenize_title(title: str) -> List[str]:
    raw = re.split(r"[^a-z0-9]+", (title or "").lower())
    out: List[str] = []
    for x in raw:
        t = _norm_token(x)
        if t:
            out.append(t[:48])
    return out[:48]


def comp_stable_id(item: Dict[str, Any], title: str) -> str:
    iid = str(item.get("itemId") or "").strip()
    if iid:
        return f"id:{iid}"
    pv = item.get("price")
    if isinstance(pv, dict):
        pv = str(pv.get("value") or "")
    else:
        pv = str(pv or "")
    et = str(item.get("itemEndDate") or "")
    raw = f"{(title or '').strip().lower()}|{et}|{pv}"
    h = hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:20]
    return f"h:{h}"


def seller_from_item(item: Dict[str, Any]) -> str:
    if not item:
        return ""
    for k in ("sellerUsername", "seller", "sellerId"):
        v = item.get(k)
        if v:
            return str(v).strip().lower()[:120]
    u = item.get("seller")
    if isinstance(u, dict):
        for k in ("username", "sellerUsername"):
            v = u.get(k)
            if v:
                return str(v).strip().lower()[:120]
    return ""


def thumb_url_from_item(item: Dict[str, Any]) -> str:
    if not item:
        return ""
    img = item.get("image")
    if isinstance(img, dict):
        u = img.get("imageUrl") or img.get("url")
        if u:
            return str(u).strip()[:500]
    return ""


def load_manual_state(path: Optional[str] = None) -> Dict[str, Any]:
    p = path or DEFAULT_STATE_PATH
    empty: Dict[str, Any] = {
        "version": _STATE_VERSION,
        "by_canonical": {},
        "learned": {
            "reject_tokens": {},
            "approve_tokens": {},
            "reject_sellers": {},
            "approve_sellers": {},
        },
    }
    if not os.path.isfile(p):
        return empty
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return empty
        data.setdefault("version", _STATE_VERSION)
        data.setdefault("by_canonical", {})
        data.setdefault(
            "learned",
            {
                "reject_tokens": {},
                "approve_tokens": {},
                "reject_sellers": {},
                "approve_sellers": {},
            },
        )
        ln = data["learned"]
        for k in ("reject_tokens", "approve_tokens", "reject_sellers", "approve_sellers"):
            ln.setdefault(k, {})
        return data
    except (json.JSONDecodeError, OSError, TypeError):
        return empty


def save_manual_state(data: Dict[str, Any], path: Optional[str] = None) -> bool:
    p = path or DEFAULT_STATE_PATH
    try:
        data["version"] = _STATE_VERSION
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except (OSError, TypeError):
        return False


def read_canonical_entry(state: Dict[str, Any], ckey: str) -> Dict[str, Any]:
    """Read-only; does not create keys."""
    if not ckey:
        return {}
    ent = (state.get("by_canonical") or {}).get(ckey)
    return ent if isinstance(ent, dict) else {}


def get_comp_decisions_map(state: Dict[str, Any], ckey: str) -> Dict[str, str]:
    ent = read_canonical_entry(state, ckey)
    raw = ent.get("comp_decisions") or {}
    return {str(k): str(v) for k, v in raw.items() if v in ("approve", "reject", "neutral")}


def get_manual_mv_config(state: Dict[str, Any], ckey: str) -> Dict[str, Any]:
    ent = read_canonical_entry(state, ckey)
    return {
        "use_manual_mv": bool(ent.get("use_manual_mv")),
        "manual_value": ent.get("manual_value"),
        "manual_low": ent.get("manual_low"),
        "manual_high": ent.get("manual_high"),
    }


def get_canonical_block(state: Dict[str, Any], ckey: str) -> Dict[str, Any]:
    if not ckey:
        return {}
    bc = state.setdefault("by_canonical", {})
    ent = bc.get(ckey)
    if not isinstance(ent, dict):
        ent = {}
        bc[ckey] = ent
    ent.setdefault("comp_decisions", {})
    ent.setdefault("use_manual_mv", False)
    ent.setdefault("manual_value", None)
    ent.setdefault("manual_low", None)
    ent.setdefault("manual_high", None)
    return ent


def set_comp_decision(
    state: Dict[str, Any],
    ckey: str,
    comp_id: str,
    decision: str,
) -> None:
    if not ckey or not comp_id:
        return
    ent = get_canonical_block(state, ckey)
    dec = (decision or "neutral").strip().lower()
    if dec not in ("approve", "reject", "neutral"):
        dec = "neutral"
    cd = ent.setdefault("comp_decisions", {})
    if dec == "neutral":
        cd.pop(comp_id, None)
    else:
        cd[comp_id] = dec


def set_manual_mv(
    state: Dict[str, Any],
    ckey: str,
    *,
    use_manual: bool,
    value: Optional[float],
    low: Optional[float],
    high: Optional[float],
) -> None:
    if not ckey:
        return
    ent = get_canonical_block(state, ckey)
    ent["use_manual_mv"] = bool(use_manual)
    ent["manual_value"] = value
    ent["manual_low"] = low
    ent["manual_high"] = high


def learn_from_decision(
    state: Dict[str, Any],
    *,
    title: str,
    seller: str,
    decision: str,
) -> None:
    """Update lightweight token/seller counts from a manual approve/reject."""
    dec = (decision or "").strip().lower()
    if dec not in ("approve", "reject"):
        return
    ln = state.setdefault("learned", {})
    for k in ("reject_tokens", "approve_tokens", "reject_sellers", "approve_sellers"):
        ln.setdefault(k, {})
    if dec == "reject":
        tk, sk = ln["reject_tokens"], ln["reject_sellers"]
    else:
        tk, sk = ln["approve_tokens"], ln["approve_sellers"]
    prefix = " ".join((title or "").split()[:14])
    prefix_toks = frozenset(tokenize_title(prefix))
    for tok in tokenize_title(title):
        inc = 2 if dec == "reject" and tok in prefix_toks else 1
        tk[tok] = int(tk.get(tok, 0)) + inc
    for xt, delta in parallel_vocab.learn_token_adjustments_for_title(title, dec):
        tk[xt] = int(tk.get(xt, 0)) + int(delta)
    if seller:
        sk[seller] = int(sk.get(seller, 0)) + (2 if dec == "reject" else 1)


def learned_comp_multiplier(
    state: Dict[str, Any],
    *,
    title: str,
    seller: str,
) -> Tuple[float, str]:
    """
    Returns (multiplier, short debug note). Clamped to [0.55, 1.35].
    Human Yes/No comp votes update token/seller counts; repeated No patterns
    accumulate extra downweight (still heuristic — not image understanding).
    """
    ln = state.get("learned") or {}
    rt = ln.get("reject_tokens") or {}
    at = ln.get("approve_tokens") or {}
    rs = ln.get("reject_sellers") or {}
    as_ = ln.get("approve_sellers") or {}

    mult = 1.0
    notes: List[str] = []
    for tok in tokenize_title(title):
        rc = int(rt.get(tok, 0))
        ac = int(at.get(tok, 0))
        if rc or ac:
            # net signal: reject pushes down, approve up (damped)
            delta = 0.014 * ac - 0.024 * rc
            if abs(delta) > 1e-6:
                mult *= 1.0 + delta
                if rc > ac + 1:
                    notes.append(f"-{tok}")
                elif ac > rc + 1:
                    notes.append(f"+{tok}")
            if rc >= 4 and rc > ac + 2:
                mult *= max(0.9, 1.0 - 0.018 * min(rc - ac - 2, 8))
    if seller:
        rsc = int(rs.get(seller, 0))
        asc = int(as_.get(seller, 0))
        if rsc > asc + 1:
            mult *= max(0.86, 1.0 - 0.045 * min(rsc, 8))
            notes.append("seller-")
        elif asc > rsc + 1:
            mult *= min(1.12, 1.0 + 0.034 * min(asc, 8))
            notes.append("seller+")
        if rsc >= 3 and rsc > asc + 2:
            mult *= max(0.92, 1.0 - 0.025 * min(rsc - asc - 2, 6))

    mult = max(0.55, min(1.35, mult))
    note = ",".join(notes[:8]) if notes else ""
    return mult, note


def learning_impact_summary(state: Dict[str, Any]) -> Dict[str, int]:
    """Compact counts for UI: stored votes + learned token/seller pattern tallies."""
    n_dec = 0
    for ent in (state.get("by_canonical") or {}).values():
        if not isinstance(ent, dict):
            continue
        n_dec += len(ent.get("comp_decisions") or {})
    ln = state.get("learned") or {}
    rt = ln.get("reject_tokens") or {}
    at = ln.get("approve_tokens") or {}
    rs = ln.get("reject_sellers") or {}
    as_ = ln.get("approve_sellers") or {}
    penalty_tokens = sum(1 for _t, c in rt.items() if int(c) >= 2)
    boost_tokens = sum(1 for _t, c in at.items() if int(c) >= 2)
    penalty_sellers = sum(1 for _s, c in rs.items() if int(c) >= 2)
    boost_sellers = sum(1 for _s, c in as_.items() if int(c) >= 2)
    return {
        "decisions": n_dec,
        "penalty_tokens": penalty_tokens,
        "boost_tokens": boost_tokens,
        "penalty_sellers": penalty_sellers,
        "boost_sellers": boost_sellers,
    }


def summarize_counts_for_audit(
    decisions: Dict[str, str],
) -> Tuple[int, int, int]:
    """approved count, rejected count, neutral (unset) treated as 0."""
    ap = sum(1 for v in decisions.values() if v == "approve")
    rj = sum(1 for v in decisions.values() if v == "reject")
    return ap, rj, len(decisions)
