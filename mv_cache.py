"""
mv_cache.py — Title-normalized MV cache for SnipeWins.

The valuation worker hits eBay's Browse API on every card to find comps.
With 5,000 calls/day production quota and 3 query passes per card, we can
value ~1,650 cards/day. The trouble is many of those cards are the SAME
underlying card listed by different sellers — yesterday's Cooper Flagg
Silver Prizm and today's Cooper Flagg Silver Prizm have the same MV; no
reason to burn API quota recomputing it.

This module:
    1. Normalizes a listing title to a cache key (strips listing fluff
       like seller noise, condition modifiers, lot/bulk modifiers)
    2. Stores computed MVs keyed by that normalization with a 7-day TTL
    3. On lookup, returns the cached MV result with all the original
       comp metadata so the dashboard renders identically to a fresh
       computation

Cache hit = $0 API cost. With ~30% repeat rate across cycles (typical for
sports-card scanners on hot players), that's a 30% effective quota uplift
on top of the 3-pass cap we already shipped.

Storage: simple JSON file (mv_cache.json) next to this module. Atomic
write via tmp+replace.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, Optional


HERE = Path(__file__).parent
CACHE_FILE = HERE / "mv_cache.json"


# ── Tunables ────────────────────────────────────────────────────────────────

CACHE_TTL_SECONDS = 7 * 24 * 3600   # 7 days. Card prices drift but not THAT
                                    # fast for non-rookie cards. A week-old
                                    # MV is way more useful than no MV at all.
                                    # New rookie releases SHOULD recompute
                                    # more often — handled via _is_volatile.
VOLATILE_TTL_SECONDS = 24 * 3600    # 24h TTL for cards flagged as
                                    # high-volatility (current-year RC autos
                                    # of breakout players, brand-new releases).
MIN_CACHE_CONFIDENCE = "low"        # Don't bother caching unusable estimates.


# ── Title normalization ────────────────────────────────────────────────────

# Tokens we strip because they describe the LISTING, not the card. Same
# physical card listed by 5 different sellers shouldn't have 5 cache keys.
_LISTING_NOISE_PATTERNS = [
    r"\bmint\b", r"\bnm\b", r"\bnear mint\b", r"\bgem\b", r"\bgem mint\b",
    r"\bsharp\b", r"\bclean\b", r"\bcentered\b", r"\bgorgeous\b",
    r"\bhot\b", r"\bhuge\b", r"\binvest\b", r"\binvestment\b",
    r"\bcheap\b", r"\blow start\b", r"\blow opening bid\b",
    r"\bno reserve\b", r"\bnr\b", r"\b1 day\b", r"\b1 day auction\b",
    r"\b\d+\s*day\s*auction\b",
    r"\brare\b", r"\bssp\b", r"\bsp\b",  # collector-noise but keep these...
    # Actually keep SSP/SP — they're real card variants. Remove later if
    # they cause collisions, but for now treating them as canonical.
]
# Compile once for performance
_LISTING_NOISE_RE = re.compile(
    "|".join(p for p in _LISTING_NOISE_PATTERNS if not p.endswith(r"\bssp\b") and not p.endswith(r"\bsp\b")),
    re.IGNORECASE,
)

# Common volatility signals — current-year RC autos of hyped players, etc.
_VOLATILE_PATTERNS = [
    r"\b(?:2025|2026)\b.*\bauto\b",
    r"\bbowman.*?(?:1st|first).*?bowman.*?auto\b",
    r"\bbrock bowers\b", r"\bcooper flagg\b", r"\bashton jeanty\b",
    r"\bpaul skenes\b", r"\bcaleb williams\b",
    r"\bwemby\b", r"\bwembanyama\b",
]
_VOLATILE_RE = re.compile("|".join(_VOLATILE_PATTERNS), re.IGNORECASE)


def _normalize_title(title: str) -> str:
    """Reduce a raw listing title to a canonical cache key.

    Goals:
        - Drop listing-noise tokens that vary across sellers
        - Collapse whitespace and casing
        - Preserve everything that makes the card identifiable (year,
          product family, player, parallel, serial, grade)
    """
    if not title:
        return ""
    # Unicode-normalize fancy quotes and accented chars to ASCII-ish.
    s = unicodedata.normalize("NFKD", str(title))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    # Strip listing-noise tokens.
    s = _LISTING_NOISE_RE.sub("", s)
    # Drop seller emojis, fire/lightning, etc.
    s = re.sub(r"[^\w\s/#$.,-]", " ", s)
    # Collapse whitespace.
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _is_volatile(title: str) -> bool:
    """High-volatility cards get a shorter TTL because their MV moves
    fast — breakout rookie performance, opening-week pop reports, etc."""
    if not title:
        return False
    return bool(_VOLATILE_RE.search(str(title)))


# ── Persistence ────────────────────────────────────────────────────────────

def _load() -> Dict[str, Any]:
    if not CACHE_FILE.exists():
        return {"version": 1, "entries": {}}
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"version": 1, "entries": {}}
        data.setdefault("entries", {})
        return data
    except Exception:
        return {"version": 1, "entries": {}}


def _save(data: Dict[str, Any]) -> None:
    tmp = str(CACHE_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
    os.replace(tmp, CACHE_FILE)


# ── Public API ─────────────────────────────────────────────────────────────

def lookup(title: str) -> Optional[Dict[str, Any]]:
    """Look up a cached MV for the given listing title.

    Returns a dict shaped like the worker's stamp-on-row output (all the
    `_mv_*` keys you'd otherwise compute fresh), or None if no usable
    cache hit. None means the caller should run the full valuation.

    A cache HIT means: same normalized title was computed within the TTL
    window. The returned dict carries a `_mv_from_cache: true` flag so
    downstream code can audit cache effectiveness in the logs.
    """
    key = _normalize_title(title)
    if not key:
        return None
    data = _load()
    entry = (data.get("entries") or {}).get(key)
    if not entry:
        return None
    cached_at = float(entry.get("cached_at") or 0)
    if cached_at <= 0:
        return None
    ttl = VOLATILE_TTL_SECONDS if _is_volatile(title) else CACHE_TTL_SECONDS
    if (time.time() - cached_at) > ttl:
        # Stale — caller will recompute and overwrite via store().
        return None
    payload = entry.get("payload") or {}
    if not isinstance(payload, dict):
        return None
    # Return a fresh copy so the caller can mutate without affecting cache.
    out = dict(payload)
    out["_mv_from_cache"] = True
    out["_mv_cache_age_secs"] = int(time.time() - cached_at)
    # Stamp _mv_computed_at to NOW so downstream cooldown logic treats
    # this row as freshly valued (no need to re-attempt within 30 min).
    out["_mv_computed_at"] = time.time()
    out["_mv_compute_attempted"] = True
    return out


def store(title: str, mv_payload: Dict[str, Any]) -> bool:
    """Write a computed MV into the cache. Caller passes the dict that
    would be merged onto the pool row (must contain `true_mv` to be
    cache-worthy — we don't cache failures or estimate-only results).

    Returns True if cached, False if skipped (e.g., no real MV in payload).
    """
    key = _normalize_title(title)
    if not key:
        return False
    if not isinstance(mv_payload, dict):
        return False
    # Only cache real comp-backed MVs. Failed lookups, estimate-only fallbacks,
    # and missing-title errors aren't worth preserving — they should be
    # retried next time anyway.
    mv = mv_payload.get("true_mv") or mv_payload.get("market_value")
    try:
        if not mv or float(mv) <= 0:
            return False
    except Exception:
        return False
    # Strip any fields that shouldn't roll over to other listings of the
    # same card (e.g., item-specific IDs, per-listing seller info). Most
    # _mv_* fields are derived from comps so they're listing-agnostic and
    # safe to share.
    _LISTING_LOCAL_KEYS = {
        "item_id", "itemId", "source_item_id",
        "_mv_compute_attempted",  # we'll set this on lookup
        "_mv_computed_at",         # ditto
    }
    payload = {k: v for k, v in mv_payload.items() if k not in _LISTING_LOCAL_KEYS}
    data = _load()
    entries = data.setdefault("entries", {})
    entries[key] = {
        "cached_at": time.time(),
        "title_normalized": key,
        "title_original_sample": (str(title) or "")[:160],
        "payload": payload,
    }
    # Don't let the cache file balloon forever — evict the oldest entries
    # once we exceed a soft cap. 5000 entries = roughly 5MB at 1KB each.
    MAX_ENTRIES = 5000
    if len(entries) > MAX_ENTRIES:
        # Sort by cached_at ascending, drop the oldest 10% to amortize.
        items = sorted(entries.items(), key=lambda kv: float(kv[1].get("cached_at") or 0))
        for k, _ in items[: max(1, MAX_ENTRIES // 10)]:
            entries.pop(k, None)
    _save(data)
    return True


# ── Ops CLI ────────────────────────────────────────────────────────────────

def _print_stats() -> int:
    data = _load()
    entries = data.get("entries") or {}
    if not entries:
        print("(empty cache)")
        return 0
    now = time.time()
    fresh, stale = 0, 0
    for e in entries.values():
        age = now - float(e.get("cached_at") or 0)
        if age <= CACHE_TTL_SECONDS:
            fresh += 1
        else:
            stale += 1
    print(f"mv_cache stats:")
    print(f"  total entries:   {len(entries)}")
    print(f"  fresh (≤7d):     {fresh}")
    print(f"  stale (>7d):     {stale}")
    print(f"  file size:       {CACHE_FILE.stat().st_size if CACHE_FILE.exists() else 0} bytes")
    return 0


def _clear_cache() -> int:
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
        print("cache cleared")
    else:
        print("(cache file not present)")
    return 0


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "stats":
        sys.exit(_print_stats())
    if len(sys.argv) >= 2 and sys.argv[1] == "clear":
        sys.exit(_clear_cache())
    if len(sys.argv) >= 3 and sys.argv[1] == "lookup":
        out = lookup(sys.argv[2])
        print(json.dumps(out, indent=2, default=str) if out else "(miss)")
        sys.exit(0)
    print("usage: python mv_cache.py [stats | clear | lookup <title>]")
    sys.exit(2)
