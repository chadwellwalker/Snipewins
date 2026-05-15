"""
daily_pool.py — Module 1 of the 24h pipeline rebuild.

Pulls every tracked-player auction ending in the next 24 hours, applies
the engine's quality filters, and persists the candidate pool to disk.
The pool is keyed by item_id so existing entries (with prior MVs) are
preserved across fetches — no re-valuation cost on cache hits.

This is the foundation for the "morning briefing" workflow: a user opens
the app and immediately sees everything ending today, with target bids
filling in as the background valuation worker computes them.

Architecture:
    daily_pool.py (this file)
        ↓ runs once per hour, calls the engine with a 24h window
    daily_pool.json
        ↓ read by valuation_worker.py to find unvalued rows
    valuation_worker.py
        ↓ writes computed MVs back to the pool
    daily_pool.json
        ↓ read by streamlit_app.py (Module 3)
    UI

Usage:
    Manual one-off:
        python daily_pool.py

    Background loop (every hour):
        python daily_pool.py --loop

    Status check:
        python daily_pool.py --status

The pool file is daily_pool.json in this folder. Atomic writes (tmp +
replace) so a crash never corrupts state.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


HERE = Path(__file__).parent
POOL_FILE = HERE / "daily_pool.json"
LOG_FILE = HERE / "daily_pool.log"

DEFAULT_WINDOW_HOURS = 24.0


# SCAN-PAUSE-2026-05-15: operator kill switch. Set SNIPEWINS_SCAN_PAUSED=1
# in Render env to halt all eBay calls without suspending the service
# (dashboard stays up; scanners idle). Used to stop quota burn mid-day
# so the next UTC reset gives a clean window for testing. Same helper
# lives in daily_bin_pool.py and valuation_worker.py.
def _is_scan_paused() -> bool:
    return os.environ.get("SNIPEWINS_SCAN_PAUSED", "").strip().lower() in (
        "1", "true", "yes", "on",
    )
DEFAULT_LOOP_INTERVAL_SECS = 3600  # 1 hour


# ── Persistence ─────────────────────────────────────────────────────────────

def load_pool() -> Dict[str, Any]:
    """Load the pool from disk. Returns {} on first run or read failure."""
    if not POOL_FILE.exists():
        return {"version": 1, "items": {}, "last_fetch_ts": 0.0, "last_fetch_iso": ""}
    try:
        return json.loads(POOL_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[daily_pool] WARN: could not parse {POOL_FILE.name}: {exc}. Starting fresh.")
        return {"version": 1, "items": {}, "last_fetch_ts": 0.0, "last_fetch_iso": ""}


def save_pool(pool: Dict[str, Any]) -> None:
    """Atomic write."""
    tmp = str(POOL_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(pool, fh, indent=2, sort_keys=True, default=str)
    os.replace(tmp, POOL_FILE)


# ── Row extraction + merging ────────────────────────────────────────────────

def _extract_item_id(row: Dict[str, Any]) -> str:
    """Stable ID for keying the pool. Tries the same fields the engine uses."""
    for k in ("item_id", "itemId", "source_item_id"):
        v = (row or {}).get(k)
        if v:
            return str(v)
    # Fallback — title-based key. Not ideal but keeps us functional.
    title = str((row or {}).get("title") or (row or {}).get("source_title") or "")
    return f"title:{title[:96]}" if title else f"unknown:{id(row)}"


def _row_seconds_remaining(row: Dict[str, Any]) -> Optional[float]:
    """Authoritative computation: prefer end_dt (absolute time), fall back to
    remaining_seconds. The engine writes end_dt as a datetime object on fresh
    fetches; after JSON round-trip it's a string. Handle both."""
    # 1. Try the timestamp field we add ourselves at merge time.
    v = (row or {}).get("_pool_end_dt_ts")
    try:
        if v is not None:
            return max(0.0, float(v) - time.time())
    except Exception:
        pass
    # 2. Try parsing end_dt — datetime or ISO string.
    end_dt = (row or {}).get("end_dt")
    if end_dt is not None:
        ts = _to_timestamp(end_dt)
        if ts is not None:
            return max(0.0, ts - time.time())
    # 3. Fall back to remaining_seconds snapshot (stale across reads).
    for k in ("remaining_seconds", "seconds_remaining", "_intake_remaining_secs"):
        v = (row or {}).get(k)
        try:
            if v is not None:
                return float(v)
        except Exception:
            pass
    return None


def _to_timestamp(value: Any) -> Optional[float]:
    """Coerce a datetime, ISO string, or numeric to a unix timestamp.
    Returns None if the value can't be parsed."""
    if value is None:
        return None
    # numeric — already a timestamp
    if isinstance(value, (int, float)):
        return float(value)
    # datetime object
    if isinstance(value, datetime):
        try:
            if value.tzinfo is None:
                # treat naive as UTC
                return value.replace(tzinfo=timezone.utc).timestamp()
            return value.timestamp()
        except Exception:
            return None
    # string — try ISO parse
    s = str(value).strip()
    if not s:
        return None
    # Common patterns: "2026-05-09T14:30:00+00:00", "2026-05-09 14:30:00.000000+00:00"
    # Replace " " with "T" to make ISO parser happy
    s_iso = s.replace(" ", "T", 1)
    try:
        # Python 3.11+ handles +HH:MM offsets natively
        return datetime.fromisoformat(s_iso).timestamp()
    except Exception:
        pass
    # Strip a "Z" suffix
    if s_iso.endswith("Z"):
        try:
            return datetime.fromisoformat(s_iso[:-1] + "+00:00").timestamp()
        except Exception:
            pass
    return None


def _row_has_confident_mv(row: Dict[str, Any]) -> bool:
    """True if the engine produced a confident comp-backed MV for this row."""
    truth = str((row or {}).get("truth") or "").upper()
    if truth != "TRUE":
        return False
    try:
        mv = (row or {}).get("true_mv") or (row or {}).get("market_value")
        return mv is not None and float(mv) > 0.0
    except Exception:
        return False


def _is_sport_suppressed(row: Dict[str, Any]) -> Optional[str]:
    """Return a suppression reason when this row's (sport, parallel) combo
    is on the parallel_vocab blocklist (e.g. baseball Silver Prizm). Backstops
    the engine-side gate in case the engine ever admits one anyway."""
    try:
        import parallel_vocab as pv
    except Exception:
        return None
    sport = str((row or {}).get("sport") or "").strip().upper()
    parallel_family = str(
        (row or {}).get("parallel_family")
        or (row or {}).get("_hydrated_parallel_family")
        or ""
    ).strip().lower()
    title = str((row or {}).get("title") or (row or {}).get("source_title") or "")
    product_family = str(
        (row or {}).get("product_family")
        or (row or {}).get("_hydrated_product_family")
        or (row or {}).get("target_product_family")
        or ""
    )
    return (
        pv.is_parallel_suppressed_for_sport(sport, parallel_family)
        or pv.is_title_sport_suppressed(sport, title, product_family)
    )


def _extract_player_slug(row: Dict[str, Any]) -> str:
    """Normalize the row's player identity to the snake_case slug format
    that chase_rules.PLAYER_TIER_* sets use. Tries engine-stamped IDs
    first (target_entity_id, player_id) which are already slugs, then
    falls back to building a slug from the player name with accent
    folding and punctuation stripping."""
    for k in ("target_entity_id", "player_id", "_lane_audit_player_slug"):
        v = (row or {}).get(k)
        if v:
            return str(v).strip().lower().replace("-", "_").replace(" ", "_")
    raw_name = str(
        (row or {}).get("target_player_name")
        or (row or {}).get("canonical_player")
        or (row or {}).get("player_name")
        or (row or {}).get("player")
        or ""
    ).strip().lower()
    if not raw_name:
        return ""
    # Fold accents (José → jose, Acuña → acuna) before token clean-up.
    normalized = unicodedata.normalize("NFKD", raw_name)
    folded = "".join(c for c in normalized if not unicodedata.combining(c))
    # Strip apostrophes and periods entirely (Ja'Marr → jamarr, St. → st),
    # then map hyphens / spaces / underscores to single underscores.
    cleaned = re.sub(r"[\'\.\,]", "", folded)
    cleaned = re.sub(r"[\s\-_]+", "_", cleaned)
    return cleaned.strip("_")


def _is_strict_auction(row: Dict[str, Any]) -> bool:
    """True only when the eBay row is a PURE auction (no BIN side, no
    hybrid). Drops AUCTION_WITH_BIN hybrids and FIXED_PRICE-only listings.
    The user's feed is auction-only; BIN is a separate product.

    eBay Browse API field `buyingOptions` is a list. We accept exactly
    `["AUCTION"]` and reject everything else. Defaults to False when the
    field is missing so unknown rows can't slip through."""
    opts = (row or {}).get("buyingOptions")
    if not isinstance(opts, list):
        return False
    if len(opts) != 1:
        return False
    return str(opts[0]).upper().strip() == "AUCTION"


def _is_freshness_stale(row: Dict[str, Any]) -> bool:
    """True when this row was last seen too long ago AND is now claiming
    a very-soon end. Pattern: fetched 9am, end_dt was 11pm, now it's
    11pm and we're showing "22 seconds remaining" — but the auction
    might have ended/converted to BIN hours ago. We can't re-fetch on
    every render, so we just drop suspicious-stale rows.

    Rules:
        - Row must have been seen in a scan (has _pool_last_seen_ts).
        - If `last_seen` is >6h old AND remaining_seconds < 1800 (30 min),
          treat as stale.
    """
    last_seen = (row or {}).get("_pool_last_seen_ts")
    try:
        last_seen_f = float(last_seen) if last_seen is not None else None
    except Exception:
        return False
    if last_seen_f is None:
        return False
    end_ts = (row or {}).get("_pool_end_dt_ts")
    try:
        end_ts_f = float(end_ts) if end_ts is not None else None
    except Exception:
        return False
    if end_ts_f is None:
        return False
    now = time.time()
    age_since_seen = now - last_seen_f
    remaining = end_ts_f - now
    return age_since_seen > (6 * 3600) and 0 <= remaining < 1800


def _evaluate_chase_rules(row: Dict[str, Any]) -> Dict[str, Any]:
    """Run a row through chase_rules.evaluate_card_target. Returns the
    decision dict, or a safe default (qualifies=True, priority=0) when
    the chase_rules import or call fails — we don't want a bad import
    to silently nuke the entire pool."""
    try:
        sys.path.insert(0, str(HERE))
        import chase_rules
        return chase_rules.evaluate_card_target(
            title=str(row.get("title") or row.get("source_title") or ""),
            sport=str(row.get("sport") or ""),
            player_slug=_extract_player_slug(row),
            parallel_family=str(
                row.get("parallel_family")
                or row.get("_hydrated_parallel_family")
                or ""
            ),
            product_family=str(
                row.get("product_family")
                or row.get("_hydrated_product_family")
                or row.get("target_product_family")
                or ""
            ),
        )
    except Exception as exc:
        return {
            "qualifies":   True,
            "reason":      f"chase_rules_error:{type(exc).__name__}",
            "priority":    0,
            "player_tier": "?",
            "signals":     {"error": str(exc)[:120]},
        }


def merge_into_pool(pool: Dict[str, Any], new_rows: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Merge fresh fetch results into the pool. Returns counts:
        {
            "added":    rows newly added,
            "updated":  rows whose data changed (price, time, etc.),
            "preserved_mv": rows where we kept the prior MV (skipped re-valuation),
            "suppressed_sport_parallel": rows dropped because of a sport+parallel
                                          mismatch (e.g. baseball Silver Prizm).
        }
    """
    items: Dict[str, Any] = pool.setdefault("items", {})
    counts = {
        "added": 0,
        "updated": 0,
        "preserved_mv": 0,
        "suppressed_sport_parallel": 0,
        "rejected_by_chase_rules": 0,
        "rejected_non_auction": 0,
    }

    for row in (new_rows or []):
        if not isinstance(row, dict):
            continue
        item_id = _extract_item_id(row)
        if not item_id or item_id.startswith("unknown:"):
            continue
        # ── STRICT AUCTION-ONLY GATE ─────────────────────────────────────
        # The user's feed is auction-only. BIN listings and AUCTION+BIN
        # hybrids must not enter the pool because their BIN side resolves
        # immediately when clicked, breaking the auction-snipe workflow.
        if not _is_strict_auction(row):
            print(
                f"[POOL_REJECT_NON_AUCTION] item_id={item_id} "
                f"buying_options={row.get('buyingOptions')} "
                f"title={str(row.get('title') or '')[:96]}"
            )
            counts["rejected_non_auction"] += 1
            items.pop(item_id, None)
            continue
        # Sport-aware backstop. Drop rows where the parallel family is
        # essentially base-level for the listed sport (e.g. baseball Silver
        # Prizm). Logged so we can audit suppression behavior over time.
        _suppress_reason = _is_sport_suppressed(row)
        if _suppress_reason:
            print(
                f"[POOL_SUPPRESS] item_id={item_id} reason={_suppress_reason} "
                f"title={str(row.get('title') or '')[:96]}"
            )
            counts["suppressed_sport_parallel"] += 1
            items.pop(item_id, None)
            continue
        # chase_rules.evaluate_card_target — single source of truth for
        # "is this card a SnipeWins target?" Drops Tier 3 base cards,
        # PSA-10-required inserts at non-PSA-10 grade, QB legends without
        # auto/case-hit, etc. Also stamps `_chase_priority` for downstream
        # sort and `_chase_reason` for audit.
        _eval = _evaluate_chase_rules(row)
        if not _eval.get("qualifies"):
            print(
                f"[POOL_CHASE_REJECT] item_id={item_id} "
                f"reason={_eval.get('reason')} "
                f"tier={_eval.get('player_tier')} "
                f"title={str(row.get('title') or '')[:96]}"
            )
            counts["rejected_by_chase_rules"] += 1
            items.pop(item_id, None)
            continue
        # Stamp chase decision onto the row so pool_view can sort + audit.
        row["_chase_priority"]   = int(_eval.get("priority") or 0)
        row["_chase_reason"]     = str(_eval.get("reason") or "")
        row["_chase_player_tier"] = str(_eval.get("player_tier") or "?")

        # Compute and stash an end-of-auction timestamp at merge time so
        # downstream code (and the worker) can read a reliable numeric
        # end time without re-parsing end_dt every time.
        end_ts = _to_timestamp((row or {}).get("end_dt"))

        existing = items.get(item_id)
        if existing is None:
            items[item_id] = dict(row)
            # Drop the raw datetime — JSON-unsafe and we have the timestamp.
            if isinstance(items[item_id].get("end_dt"), datetime):
                items[item_id]["end_dt_iso"] = items[item_id]["end_dt"].isoformat()
                del items[item_id]["end_dt"]
            items[item_id]["_pool_first_seen_ts"] = time.time()
            items[item_id]["_pool_last_seen_ts"]  = time.time()
            if end_ts is not None:
                items[item_id]["_pool_end_dt_ts"] = end_ts
            counts["added"] += 1
            continue

        # Existing entry — preserve prior MV if we had one and the new row
        # doesn't have a confident one. This is the cache-hit win.
        prior_has_mv = _row_has_confident_mv(existing)
        new_has_mv   = _row_has_confident_mv(row)

        merged = dict(row)
        # Same datetime cleanup for existing entries.
        if isinstance(merged.get("end_dt"), datetime):
            merged["end_dt_iso"] = merged["end_dt"].isoformat()
            del merged["end_dt"]
        merged["_pool_first_seen_ts"] = existing.get("_pool_first_seen_ts") or time.time()
        merged["_pool_last_seen_ts"]  = time.time()
        merged["_pool_end_dt_ts"]     = end_ts if end_ts is not None else existing.get("_pool_end_dt_ts")

        if prior_has_mv and not new_has_mv:
            # Keep prior MV
            for k in ("true_mv", "market_value", "target_bid", "truth", "truth_level",
                      "trusted_exact", "_mv_computed_at", "_mv_source"):
                if k in existing:
                    merged[k] = existing[k]
            counts["preserved_mv"] += 1

        # ALWAYS preserve worker-stamped diagnostic / cooldown / progress fields,
        # regardless of whether the engine produced a confident MV. Without this
        # the worker re-attempts the same row every cycle because daily_pool
        # wipes its progress markers (cooldown, attempt count, partial comp
        # state) on every hourly refresh — producing an infinite retry loop
        # and zero net progress. These fields all start with `_mv_` so they're
        # safe to preserve verbatim from `existing` onto `merged`.
        _worker_preserve_keys = (
            "_mv_compute_attempted",
            "_mv_computed_at",
            "_mv_compute_error",
            "_mv_source",
            "_mv_confidence",
            "_mv_comp_count",
            "_mv_accepted_comp_count",
            "_mv_exact_grade_comp_count",
            "_mv_auction_comp_count",
            "_mv_fixed_price_comp_count",
            "_mv_recent_comp_count_7d",
            "_mv_recent_comp_count_30d",
            "_mv_value_low",
            "_mv_value_high",
            "_mv_dominant_range_low",
            "_mv_dominant_range_high",
            "_mv_valuation_basis",
            "_mv_market_value_source",
            "_mv_cluster_method",
            "_mv_grade_fallback_used",
            "_mv_relaxation_level",
            "_mv_relaxation_label",
            "_mv_relaxation_description",
            "_mv_relaxation_query",
        )
        for k in _worker_preserve_keys:
            # If the new fetch row didn't set it but the existing row has it,
            # carry it forward. (If the new row DID set it, the dict(row)
            # copy above already won — we don't clobber that.)
            if k not in merged and k in existing:
                merged[k] = existing[k]

        items[item_id] = merged
        counts["updated"] += 1

    return counts


def prune_sport_suppressed(pool: Dict[str, Any]) -> int:
    """Sweep the entire pool and evict rows that the parallel_vocab sport-aware
    suppression rules flag as out-of-scope (e.g. baseball Silver Prizm cards
    that snuck into the pool before the suppression rules existed, or via a
    code path that didn't run the merge-time check). Runs once per cycle so
    new rules get applied retroactively to stale entries.

    Returns the count of items pruned, and prints a [POOL_SUPPRESS_SWEEP]
    line per evicted row for audit visibility.
    """
    items: Dict[str, Any] = pool.get("items", {})
    pruned = 0
    for item_id in list(items.keys()):
        row = items[item_id]
        if not isinstance(row, dict):
            continue
        reason = _is_sport_suppressed(row)
        if reason:
            print(
                f"[POOL_SUPPRESS_SWEEP] item_id={item_id} reason={reason} "
                f"title={str(row.get('title') or '')[:96]}"
            )
            del items[item_id]
            pruned += 1
    return pruned


def prune_wrong_player(pool: Dict[str, Any]) -> int:
    """Sweep the pool and evict rows whose title doesn't match the player
    the lane was searching for. eBay's fuzzy search sometimes returns
    cross-player results (e.g., a "Cam Ward Prizm" query returning a
    Tetairoa McMillan card) and the engine's own entity-match logic
    correctly flags entity_match_status=NO_MATCH or low score. Without
    this sweep, those rows leak into the pool and get valued using the
    WRONG player's comps, producing misleading MVs.

    Returns count of items pruned. Emits [POOL_WRONG_PLAYER_SWEEP] per
    evicted row.
    """
    items: Dict[str, Any] = pool.get("items", {})
    pruned = 0
    for item_id in list(items.keys()):
        row = items[item_id]
        if not isinstance(row, dict):
            continue
        status = str(row.get("entity_match_status") or "").upper()
        try:
            score = float(row.get("entity_match_score") or 0.0)
        except Exception:
            score = 0.0
        exact = bool(row.get("exact_entity_match"))
        if status == "NO_MATCH" or (score and score < 0.55 and not exact):
            print(
                f"[POOL_WRONG_PLAYER_SWEEP] item_id={item_id} "
                f"queried_player={str(row.get('target_player_name') or '?')} "
                f"entity_match_status={status} "
                f"entity_match_score={score:.3f} "
                f"title={str(row.get('title') or '')[:96]}"
            )
            del items[item_id]
            pruned += 1
    return pruned


def prune_non_auction(pool: Dict[str, Any]) -> int:
    """Sweep the pool and evict any row whose buyingOptions isn't a strict
    ['AUCTION']. Catches stale hybrids that entered before the auction-only
    gate existed. Returns count pruned."""
    items: Dict[str, Any] = pool.get("items", {})
    pruned = 0
    for item_id in list(items.keys()):
        row = items[item_id]
        if not isinstance(row, dict):
            continue
        if not _is_strict_auction(row):
            print(
                f"[POOL_NON_AUCTION_SWEEP] item_id={item_id} "
                f"buying_options={row.get('buyingOptions')} "
                f"title={str(row.get('title') or '')[:96]}"
            )
            del items[item_id]
            pruned += 1
    return pruned


def prune_stale_near_end(pool: Dict[str, Any]) -> int:
    """Sweep the pool and evict rows that are suspiciously stale-near-end —
    fetched >6h ago and now claiming <30min remaining. These rows are at
    high risk of having converted to BIN or been canceled since the fetch.
    Returns count pruned."""
    items: Dict[str, Any] = pool.get("items", {})
    pruned = 0
    for item_id in list(items.keys()):
        row = items[item_id]
        if not isinstance(row, dict):
            continue
        if _is_freshness_stale(row):
            print(
                f"[POOL_STALE_NEAR_END_SWEEP] item_id={item_id} "
                f"title={str(row.get('title') or '')[:96]}"
            )
            del items[item_id]
            pruned += 1
    return pruned


def prune_chase_rules(pool: Dict[str, Any]) -> int:
    """Sweep the entire pool and evict rows that fail chase_rules.evaluate_card_target.
    Picks up stale rows that entered the pool before the latest chase_rules
    update. Also re-stamps `_chase_priority` on surviving rows so the
    dashboard sort stays current after tier-list edits.

    Returns count of items pruned. Emits [POOL_CHASE_SWEEP] per evicted row.
    """
    items: Dict[str, Any] = pool.get("items", {})
    pruned = 0
    for item_id in list(items.keys()):
        row = items[item_id]
        if not isinstance(row, dict):
            continue
        _eval = _evaluate_chase_rules(row)
        if not _eval.get("qualifies"):
            print(
                f"[POOL_CHASE_SWEEP] item_id={item_id} "
                f"reason={_eval.get('reason')} "
                f"tier={_eval.get('player_tier')} "
                f"title={str(row.get('title') or '')[:96]}"
            )
            del items[item_id]
            pruned += 1
            continue
        # Re-stamp on surviving rows in case the tier list changed.
        row["_chase_priority"]    = int(_eval.get("priority") or 0)
        row["_chase_reason"]      = str(_eval.get("reason") or "")
        row["_chase_player_tier"] = str(_eval.get("player_tier") or "?")
    return pruned


def prune_ended(pool: Dict[str, Any]) -> int:
    """Remove items whose auction has ended. Returns count pruned."""
    items: Dict[str, Any] = pool.get("items", {})
    pruned = 0
    now_ts = time.time()
    for item_id in list(items.keys()):
        row = items[item_id]
        # Check our pre-computed timestamp first, then fall back to parsing
        # end_dt / end_dt_iso if a row predates the computed field.
        end_ts: Optional[float] = None
        v = row.get("_pool_end_dt_ts")
        try:
            if v is not None:
                end_ts = float(v)
        except Exception:
            end_ts = None
        if end_ts is None:
            end_ts = _to_timestamp(row.get("end_dt") or row.get("end_dt_iso"))

        # If we still don't have an end time, fall back to "stale entry" rule:
        # drop entries we haven't refreshed in 48h so the pool can't grow
        # forever from broken rows.
        if end_ts is None:
            last_seen = float(row.get("_pool_last_seen_ts") or 0)
            if last_seen > 0 and (now_ts - last_seen) > (48 * 3600):
                del items[item_id]
                pruned += 1
            continue

        if end_ts < now_ts:
            del items[item_id]
            pruned += 1

    return pruned


# ── Fetch driver ────────────────────────────────────────────────────────────

def fetch_and_update(window_hours: float = DEFAULT_WINDOW_HOURS) -> Dict[str, Any]:
    """
    Run one fetch cycle:
        1. Call the engine with a 24h window
        2. Merge results into the pool
        3. Prune ended auctions
        4. Save
    Returns a summary dict (counts + timings) for logging / observability.
    """
    started = time.time()

    pool = load_pool()
    items_before = len(pool.get("items", {}) or {})

    # The engine is heavy. Import lazily so this script can be loaded
    # for --status without paying the import cost.
    print(f"[daily_pool] importing ending_soon_engine…", flush=True)
    sys.path.insert(0, str(HERE))
    os.chdir(HERE)
    import ending_soon_engine as ese

    print(f"[daily_pool] fetching {window_hours:.1f}h window (force_refresh=True)…", flush=True)
    fetch_started = time.time()
    try:
        deals, meta = ese.fetch_ending_soon_deals(
            force_refresh=True,
            time_window_hours=float(window_hours),
        )
    except Exception as exc:
        print(f"[daily_pool] ERROR: engine fetch raised {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {str(exc)[:200]}",
            "elapsed_seconds": round(time.time() - started, 1),
        }
    fetch_seconds = round(time.time() - fetch_started, 1)
    print(f"[daily_pool] engine returned {len(deals)} deals in {fetch_seconds}s", flush=True)

    # DEFENSIVE-PATCH 2026-05-10: merge pre-valuation rows too. The engine's
    # `deals` list only contains rows that fully passed valuation (typically
    # 5-10 of 40-50 routing-passing rows, due to comp coverage). The
    # `pool_pre_valuation_rows` list in meta contains every row that passed
    # routing — including those whose valuation failed. Capturing them here
    # gives the morning briefing a much richer pool; valuation_worker.py
    # retries comp lookups for them on its own cadence.
    pre_val_rows = list((meta or {}).get("pool_pre_valuation_rows") or [])
    print(
        f"[daily_pool] engine pre-valuation candidates: {len(pre_val_rows)} "
        f"(of which {len(deals)} fully valued)",
        flush=True,
    )
    # RACE-FIX 2026-05-11: re-read the pool from disk RIGHT BEFORE merging.
    # The engine fetch above can take 30-60+ seconds, during which the
    # valuation_worker may have stamped _mv_compute_attempted /
    # _mv_computed_at / _mv_source / true_mv on rows. If we merge against
    # the stale `pool` snapshot we took at the start of the cycle, we'll
    # save back over the worker's writes and obliterate them. Re-reading
    # here gives merge_into_pool the freshest `existing` rows, and the
    # always-preserve worker-keys loop inside merge_into_pool then carries
    # the worker stamps forward onto the merged entry.
    #
    # Note: we only re-read if the on-disk file changed (last_fetch_ts is
    # unchanged for daily_pool's own writes, but the worker doesn't touch
    # that field). To keep things simple we just always re-read — it's a
    # single JSON parse and runs once per cycle.
    try:
        fresh_pool = load_pool()
        # Carry over any fields we just set on `pool` (none yet — last_fetch_*
        # is set below at line ~718), but preserve the freshly-loaded items.
        pool = fresh_pool
    except Exception as _exc:
        print(f"[daily_pool] WARN: pool re-read before merge failed: {_exc}", flush=True)

    # Merge deals first so any successful MV/target_bid takes priority over
    # the unvalued pre-val row for the same item_id.
    merge_counts = merge_into_pool(pool, deals)
    pre_val_merge_counts = merge_into_pool(pool, pre_val_rows)
    # Combine the counts so logging stays accurate.
    for _k in (
        "added", "updated", "preserved_mv",
        "suppressed_sport_parallel", "rejected_by_chase_rules",
        "rejected_non_auction",
    ):
        merge_counts[_k] = int(merge_counts.get(_k, 0) or 0) + int(pre_val_merge_counts.get(_k, 0) or 0)
    # Pool-wide sweeps — apply current vocab + chase_rules + auction-only
    # to stale entries. Order matters: cheapest filters first.
    non_auction_pruned      = prune_non_auction(pool)
    wrong_player_pruned     = prune_wrong_player(pool)
    stale_near_end_pruned   = prune_stale_near_end(pool)
    sport_pruned            = prune_sport_suppressed(pool)
    chase_pruned            = prune_chase_rules(pool)
    pruned                  = prune_ended(pool)

    pool["last_fetch_ts"]  = started
    pool["last_fetch_iso"] = datetime.fromtimestamp(started, tz=timezone.utc).isoformat(timespec="seconds")
    pool["last_fetch_window_hours"] = float(window_hours)
    pool["last_fetch_meta"] = {
        "deals_returned":            int(len(deals)),
        "fetch_seconds":             fetch_seconds,
        "merge_counts":              dict(merge_counts),
        "pruned_ended":              int(pruned),
        "pruned_sport_suppressed":   int(sport_pruned),
        "pruned_chase_rules":        int(chase_pruned),
        "pruned_non_auction":        int(non_auction_pruned),
        "pruned_wrong_player":       int(wrong_player_pruned),
        "pruned_stale_near_end":     int(stale_near_end_pruned),
        "items_before":              int(items_before),
        "items_after":               int(len(pool.get("items", {}) or {})),
        "engine_meta_keys_sample":   list((meta or {}).keys())[:6],
    }
    save_pool(pool)

    summary = {
        "ok":                  True,
        "elapsed_seconds":     round(time.time() - started, 1),
        "fetch_seconds":       fetch_seconds,
        "deals_returned":      len(deals),
        "items_before":        items_before,
        "items_after":         len(pool.get("items", {}) or {}),
        "added":               merge_counts["added"],
        "updated":             merge_counts["updated"],
        "preserved_mv":        merge_counts["preserved_mv"],
        "pruned_ended":        pruned,
    }

    print(
        f"[daily_pool] cycle done in {summary['elapsed_seconds']}s "
        f"— added={summary['added']} updated={summary['updated']} "
        f"preserved_mv={summary['preserved_mv']} pruned={summary['pruned_ended']} "
        f"pool_size={summary['items_after']}",
        flush=True,
    )
    return summary


# ── Status / observability ──────────────────────────────────────────────────

def print_status() -> int:
    pool = load_pool()
    items = pool.get("items", {}) or {}
    last_fetch_ts = float(pool.get("last_fetch_ts") or 0.0)
    last_fetch_iso = str(pool.get("last_fetch_iso") or "never")
    age = (time.time() - last_fetch_ts) if last_fetch_ts > 0 else float("inf")
    age_human = f"{age/60:.1f}m" if age != float("inf") else "never"

    # Bucket by time-to-end
    now_ts = time.time()
    buckets = {"<30m": 0, "30m-1h": 0, "1-3h": 0, "3-6h": 0, "6-24h": 0, ">24h": 0, "ended": 0}
    confident_mv = 0
    for row in items.values():
        end_ts = None
        for k in ("end_dt_ts", "_end_dt_ts", "end_time_ts"):
            v = row.get(k)
            try:
                if v is not None:
                    end_ts = float(v); break
            except Exception:
                pass
        if end_ts is None:
            secs = _row_seconds_remaining(row) or 0.0
        else:
            secs = max(0.0, end_ts - now_ts)
        if secs <= 0:
            buckets["ended"] += 1
        elif secs <= 1800:
            buckets["<30m"] += 1
        elif secs <= 3600:
            buckets["30m-1h"] += 1
        elif secs <= 10800:
            buckets["1-3h"] += 1
        elif secs <= 21600:
            buckets["3-6h"] += 1
        elif secs <= 86400:
            buckets["6-24h"] += 1
        else:
            buckets[">24h"] += 1
        if _row_has_confident_mv(row):
            confident_mv += 1

    print(f"[daily_pool] STATUS")
    print(f"  pool file:           {POOL_FILE}")
    print(f"  total items:         {len(items)}")
    print(f"  confident MV:        {confident_mv}")
    print(f"  last fetch:          {last_fetch_iso} ({age_human} ago)")
    print(f"  buckets:")
    for k, v in buckets.items():
        print(f"    {k:>8} : {v}")
    return 0


# ── CLI ─────────────────────────────────────────────────────────────────────

class _Tee:
    """Mirror writes to both the original stream and a file. Used so the
    engine's funnel/stage prints land in daily_pool.log as well as the
    terminal — without that file, we can't see WHERE the engine drops rows."""
    def __init__(self, *streams):
        self._streams = [s for s in streams if s is not None]
    def write(self, data):
        for s in self._streams:
            try:
                s.write(data)
            except Exception:
                pass
    def flush(self):
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass
    def isatty(self):
        try:
            return bool(self._streams[0].isatty())
        except Exception:
            return False


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Daily pool fetcher (Module 1 of 24h pipeline)")
    parser.add_argument("--loop", action="store_true",
                        help="Run continuously, fetching every --interval seconds")
    parser.add_argument("--interval", type=int, default=DEFAULT_LOOP_INTERVAL_SECS,
                        help=f"Seconds between fetches in --loop mode (default {DEFAULT_LOOP_INTERVAL_SECS})")
    parser.add_argument("--window", type=float, default=DEFAULT_WINDOW_HOURS,
                        help=f"Hours of forward window to fetch (default {DEFAULT_WINDOW_HOURS})")
    parser.add_argument("--status", action="store_true",
                        help="Print pool status and exit")
    args = parser.parse_args(argv)

    if args.status:
        return print_status()

    # OBS-ADD: mirror all stdout/stderr to daily_pool.log so we can post-mortem
    # the engine funnel without re-running. Re-opens the file on each run so
    # each cycle gets a fresh log (we keep the previous run as .prev).
    try:
        if LOG_FILE.exists():
            try:
                _prev = LOG_FILE.with_suffix(".log.prev")
                if _prev.exists():
                    _prev.unlink()
                LOG_FILE.rename(_prev)
            except Exception:
                pass
        _log_fh = LOG_FILE.open("w", encoding="utf-8", errors="replace", buffering=1)
        _log_fh.write(f"# daily_pool run started {datetime.now().isoformat(timespec='seconds')}\n")
        _log_fh.write(f"# argv={argv}\n# cwd={HERE}\n\n")
        sys.stdout = _Tee(sys.__stdout__, _log_fh)
        sys.stderr = _Tee(sys.__stderr__, _log_fh)
    except Exception as exc:
        print(f"[daily_pool] WARN: could not open log {LOG_FILE}: {exc}")

    if not args.loop:
        result = fetch_and_update(window_hours=args.window)
        return 0 if result.get("ok") else 1

    # --loop mode
    print(f"[daily_pool] entering loop mode — interval={args.interval}s window={args.window}h")
    while True:
        if _is_scan_paused():
            print("[daily_pool] PAUSED via SNIPEWINS_SCAN_PAUSED — skipping cycle", flush=True)
        else:
            try:
                fetch_and_update(window_hours=args.window)
            except KeyboardInterrupt:
                print("[daily_pool] interrupted, exiting")
                return 130
            except Exception as exc:
                print(f"[daily_pool] cycle error: {type(exc).__name__}: {exc}")
        # Sleep until next cycle
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("[daily_pool] interrupted, exiting")
            return 130


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
