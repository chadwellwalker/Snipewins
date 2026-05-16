"""
valuation_worker.py — Module 2 of the 24h pipeline rebuild.

Reads daily_pool.json (written by daily_pool.py), finds rows without a
confident MV, prioritizes them by time-to-end + player tier, and computes
MVs in batches via valuation_engine.run_hybrid_valuation. Writes the
results back to the pool.

The cost we're cutting:
    Old model: 4 wide scans/hour × 80-100 rows × 1 MV query per row
             ≈ 320-400 MV queries/hour
    New model: each card valued ONCE per 24h, cached for the day
             ≈ 150-300 unique MV queries TOTAL per day
    25× reduction in eBay sold-comps API calls.

Usage:
    Manual one-off (compute MVs for top N priority rows, then exit):
        python valuation_worker.py --batch 20

    Background loop:
        python valuation_worker.py --loop

    Status check:
        python valuation_worker.py --status

Priority sort (highest priority first):
    1. Time-to-end ASC — rows ending sooner come first
    2. Player tier ASC (1 = elite, higher = lower priority)
    3. Premium signal DESC — RPA / patch-auto / serial / auto rank up
    4. Title length DESC — longer titles often have richer parallel info

Idempotency:
    A row with a confident MV is never re-valued in the same 24h cycle.
    If you want to force re-valuation, delete the row's true_mv field or
    set _mv_computed_at to 0 and the worker will pick it up.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


HERE = Path(__file__).parent
# PERSISTENT-POOL-2026-05-15: env-var paths must match daily_pool.py /
# daily_bin_pool.py / pool_view.py / bin_view.py so the worker reads
# what the scanners just wrote and the dashboard reads what the worker
# just stamped. Render env: SNIPEWINS_AUCTION_POOL_PATH=/data/daily_pool.json
# and SNIPEWINS_BIN_POOL_PATH=/data/bin_pool.json.
POOL_FILE     = Path(os.environ.get("SNIPEWINS_AUCTION_POOL_PATH") or str(HERE / "daily_pool.json"))   # auctions
BIN_POOL_FILE = Path(os.environ.get("SNIPEWINS_BIN_POOL_PATH")     or str(HERE / "bin_pool.json"))     # BIN listings
                                            # Worker iterates both pools each
                                            # cycle so MV computation flows
                                            # the same way for either feed.

DEFAULT_BATCH_SIZE = 20
DEFAULT_LOOP_INTERVAL_SECS = 60
DEFAULT_LOOP_BATCH = 5  # smaller batch in loop mode so we cycle faster


# SCAN-PAUSE-2026-05-15: operator kill switch. Set SNIPEWINS_SCAN_PAUSED=1
# in Render env to halt all eBay calls without suspending the service
# (dashboard stays up; scanners idle). Used to stop quota burn mid-day
# so the next UTC reset gives a clean window for testing. The worker
# is the biggest quota spender — capping it here is the most impactful
# leg of the three-process pause.
def _is_scan_paused() -> bool:
    return os.environ.get("SNIPEWINS_SCAN_PAUSED", "").strip().lower() in (
        "1", "true", "yes", "on",
    )

PRIORITY_END_BUCKETS = [
    (1800,    "<30m"),
    (3600,    "30m-1h"),
    (10800,   "1-3h"),
    (21600,   "3-6h"),
    (86400,   "6-24h"),
]


# ── Pool I/O (must stay in sync with daily_pool.py) ─────────────────────────

def load_pool() -> Dict[str, Any]:
    if not POOL_FILE.exists():
        return {"version": 1, "items": {}}
    try:
        return json.loads(POOL_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[valuation_worker] WARN: could not parse pool file: {exc}")
        return {"version": 1, "items": {}}


def save_pool(pool: Dict[str, Any]) -> None:
    tmp = str(POOL_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(pool, fh, indent=2, sort_keys=True, default=str)
    os.replace(tmp, POOL_FILE)


def load_bin_pool() -> Dict[str, Any]:
    """Load the BIN pool. Same shape as auction pool; missing file is fine."""
    if not BIN_POOL_FILE.exists():
        return {"version": 1, "items": {}}
    try:
        return json.loads(BIN_POOL_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[valuation_worker] WARN: could not parse BIN pool file: {exc}")
        return {"version": 1, "items": {}}


def save_bin_pool(pool: Dict[str, Any]) -> None:
    tmp = str(BIN_POOL_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(pool, fh, indent=2, sort_keys=True, default=str)
    os.replace(tmp, BIN_POOL_FILE)


# ── Row inspection ──────────────────────────────────────────────────────────

def _row_seconds_remaining(row: Dict[str, Any]) -> Optional[float]:
    """Read seconds_remaining from the pool entry. Authoritative source is
    _pool_end_dt_ts (added at merge time by daily_pool.py). Falls back to
    end_dt / end_dt_iso parsing, then to the snapshot fields. Mirrors the
    logic in daily_pool._row_seconds_remaining."""
    now_ts = time.time()
    # 1. Pool-level computed timestamp (set by daily_pool.merge_into_pool)
    v = (row or {}).get("_pool_end_dt_ts")
    try:
        if v is not None:
            return max(0.0, float(v) - now_ts)
    except Exception:
        pass
    # 2. Parse end_dt / end_dt_iso as datetime or string
    for k in ("end_dt", "end_dt_iso"):
        ev = (row or {}).get(k)
        if ev is not None:
            ts = _to_timestamp(ev)
            if ts is not None:
                return max(0.0, ts - now_ts)
    # 3. Snapshot fallbacks (may be stale)
    for k in ("remaining_seconds", "seconds_remaining", "_intake_remaining_secs"):
        v = (row or {}).get(k)
        try:
            if v is not None:
                return float(v)
        except Exception:
            pass
    return None


def _to_timestamp(value: Any) -> Optional[float]:
    """Coerce a datetime, ISO string, or numeric to a unix timestamp."""
    from datetime import datetime, timezone
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        try:
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc).timestamp()
            return value.timestamp()
        except Exception:
            return None
    s = str(value).strip()
    if not s:
        return None
    s_iso = s.replace(" ", "T", 1)
    try:
        return datetime.fromisoformat(s_iso).timestamp()
    except Exception:
        pass
    if s_iso.endswith("Z"):
        try:
            return datetime.fromisoformat(s_iso[:-1] + "+00:00").timestamp()
        except Exception:
            pass
    return None


def _row_has_confident_mv(row: Dict[str, Any]) -> bool:
    truth = str((row or {}).get("truth") or "").upper()
    if truth != "TRUE":
        return False
    try:
        mv = (row or {}).get("true_mv") or (row or {}).get("market_value")
        return mv is not None and float(mv) > 0.0
    except Exception:
        return False


def _row_premium_signal_score(row: Dict[str, Any]) -> int:
    """Quick heuristic — higher = more premium. Used as a tiebreaker."""
    title = str((row or {}).get("title") or (row or {}).get("source_title") or "").lower()
    score = 0
    # Use module-level patterns from ending_soon_engine if available.
    if "rpa" in title or ("patch" in title and ("auto" in title or "autograph" in title)):
        score += 10
    if "auto" in title or "autograph" in title or "signature" in title:
        score += 5
    if "patch" in title or "relic" in title or "memorabilia" in title:
        score += 3
    # Low serial = premium
    import re as _re
    if _re.search(r"/\s*(?:1|5|10|25)\b", title):
        score += 6
    elif _re.search(r"/\s*(?:50|75|99)\b", title):
        score += 3
    if "psa 10" in title or "bgs 9.5" in title or "bgs 10" in title:
        score += 4
    return score


def _row_player_tier(row: Dict[str, Any]) -> int:
    """Lower tier = higher priority. Falls back to tier 5 if unknown."""
    for k in ("_player_tier", "player_tier", "_premium_player_tier"):
        v = (row or {}).get(k)
        try:
            if v is not None:
                return int(v)
        except Exception:
            pass
    return 5


def _priority_key(row: Dict[str, Any]) -> Tuple[float, int, int, int]:
    """
    Lower tuple = higher priority.
    """
    secs = _row_seconds_remaining(row)
    secs_for_sort = secs if secs is not None and secs > 0 else 1e9
    tier = _row_player_tier(row)
    premium = _row_premium_signal_score(row)
    title_len = len(str((row or {}).get("title") or ""))
    # Negate premium and title_len so HIGHER is sorted FIRST (since we
    # use ascending sort).
    return (secs_for_sort, tier, -premium, -title_len)


# ── Valuation driver ────────────────────────────────────────────────────────

def _compute_mv_for_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call valuation_engine.run_hybrid_valuation on a single row. Returns the
    dict to merge back into the pool entry. Never raises — wraps everything
    in try/except so one bad row doesn't kill the worker.
    """
    item_id = str(row.get("item_id") or row.get("itemId") or row.get("source_item_id") or "")
    title   = str(row.get("title") or row.get("source_title") or "")
    item_url = str(row.get("item_url") or row.get("url") or "")

    if not title:
        return {
            "_mv_compute_attempted": True,
            "_mv_compute_error": "missing_title",
            "_mv_computed_at": time.time(),
        }

    # CACHE-2026-05-13: check the title-normalized MV cache first. A hit
    # means we already computed an MV for this exact card type within the
    # last 7 days (24h for volatile rookie autos) — return it instantly
    # at zero API cost. Misses fall through to the full valuation engine.
    try:
        import mv_cache
        _cached = mv_cache.lookup(title)
        if _cached:
            print(
                f"[valuation_worker] CACHE HIT for item={item_id[:24]} "
                f"age={_cached.get('_mv_cache_age_secs', '?')}s "
                f"title={title[:80]!r}",
                flush=True,
            )
            return _cached
    except Exception as _cache_err:
        # Cache failures should NEVER stop the valuation. Log and fall through.
        print(f"[valuation_worker] cache lookup error (non-fatal): {_cache_err}")

    try:
        # Lazy import — heavy.
        sys.path.insert(0, str(HERE))
        os.chdir(HERE)
        import valuation_engine as ve
        result = ve.run_hybrid_valuation(
            listing_title=title,
            item_id=item_id,
            item_url=item_url,
            target_listing_item=dict(row),
        )
    except Exception as exc:
        return {
            "_mv_compute_attempted": True,
            "_mv_compute_error": f"{type(exc).__name__}: {str(exc)[:200]}",
            "_mv_computed_at": time.time(),
        }

    # Relaxation ladder fallback: when the engine's exact-match call produces
    # no usable value (common for brand-new 2026 releases like
    # Topps Chrome Black Dual Auto Red /5 cards where literally zero sold
    # listings exist), try progressively broader queries via comp_relaxer.
    # The user's mandate: "the machine needs to find similar cards instead
    # of multiplying numbers."
    _engine_produced_value = (
        getattr(result, "value", None) is not None
        and getattr(result, "value", 0) > 0
    )
    if not _engine_produced_value:
        try:
            import comp_relaxer
            player_hint = str(
                row.get("target_player_name")
                or row.get("canonical_player")
                or row.get("player_name")
                or ""
            )
            relaxed = comp_relaxer.value_with_relaxation(
                title=title,
                item_id=item_id,
                item_url=item_url,
                target_row=dict(row),
                player_hint=player_hint,
            )
            if relaxed:
                # Build a synthetic HybridValuation-like object that gets stamped
                # on the row. We can't easily mutate the dataclass, so capture
                # the relaxation result in a separate dict that the field-extraction
                # loop below picks up via _get().
                class _RelaxedResult:
                    pass
                rr = _RelaxedResult()
                rr.value = float(relaxed.get("mv") or 0)
                rr.estimated_value = float(relaxed.get("mv") or 0)
                rr.comp_count = int(relaxed.get("comp_count") or 0)
                rr.accepted_comp_count = int(relaxed.get("accepted_comp_count") or 0)
                rr.confidence = str(relaxed.get("confidence") or "low") + "_relaxed"
                rr.valuation_basis = (
                    f"relaxed_L{relaxed.get('level')}_{relaxed.get('label')}"
                )
                # Mark which relaxation level produced the result so the
                # dashboard can show "based on X comps from {description}".
                rr.relaxation_level = int(relaxed.get("level") or 0)
                rr.relaxation_label = str(relaxed.get("label") or "")
                rr.relaxation_description = str(relaxed.get("description") or "")
                rr.relaxation_query = str(relaxed.get("query") or "")
                # Pass through the comp snapshot so the dashboard's "View
                # comps" expander can render the similar cards that produced
                # this relaxed estimate. The downstream field-extraction loop
                # picks this up via the same _mv_comps_json capture path used
                # for exact-comp MVs.
                rr.debug_accepted_comps_json = str(relaxed.get("comps_json") or "")
                result = rr
                print(
                    f"[valuation_worker] L{relaxed.get('level')} "
                    f"({relaxed.get('label')}) rescued value=${rr.value:.0f} "
                    f"comps={rr.accepted_comp_count} title={title[:80]!r}"
                )
        except Exception as exc:
            print(f"[valuation_worker] comp_relaxer error: {exc}")

    # HybridValuation has fields like estimated_value, confidence, comp_count,
    # truth, etc. Pull them defensively — different versions may add/remove.
    out: Dict[str, Any] = {
        "_mv_compute_attempted": True,
        "_mv_computed_at":       time.time(),
    }

    def _get(name: str, default=None):
        try:
            return getattr(result, name, default)
        except Exception:
            return default

    estimated = _get("estimated_value", None)
    if estimated is not None:
        try:
            out["true_mv"] = float(estimated)
            out["market_value"] = float(estimated)
            out["truth"] = "TRUE"
            out["truth_level"] = "WORKER_RESCUE"
        except Exception:
            pass

    for field in ("confidence", "comp_count", "lane_quality", "sale_mode",
                  "weighted_median", "trimmed_mean", "lane_recency_score"):
        v = _get(field, None)
        if v is not None:
            out[f"_mv_{field}"] = v

    # TRANSPARENCY-2026-05-12: capture the actual accepted-comp snapshot so the
    # dashboard can show users the real comps that drove the MV (title, sold
    # price, sold date). This is the trust layer — without it we're a black box.
    # The snapshot can be large (48k chars cap inside the engine) so we trim
    # to ~6k here to keep daily_pool.json reasonable. Only the title/price/date
    # subset is rendered in the UI; the full snapshot stays available for
    # debugging via the raw JSON expander.
    _comps_json = _get("debug_accepted_comps_json", None)
    if _comps_json:
        try:
            _comps_str = str(_comps_json)
            if len(_comps_str) > 6000:
                _comps_str = _comps_str[:6000]
            out["_mv_comps_json"] = _comps_str
        except Exception:
            pass

    # Additional comp summary fields used by the dashboard's "View comps"
    # dropdown. These give the user transparency into how the MV was
    # derived without needing to expose individual comp listings.
    for field in (
        "accepted_comp_count",        # N comps that survived filters
        "last_comp_date",             # most recent comp date
        "value_low",                  # price range floor from comps
        "value_high",                 # price range ceiling from comps
        "dominant_range_low",         # tightest cluster low
        "dominant_range_high",        # tightest cluster high
        "dominant_comp_count",        # N comps inside the dominant cluster
        "recent_comp_count_7d",       # comps in last 7 days
        "recent_comp_count_30d",      # comps in last 30 days
        "auction_comp_count",         # how many of the comps were auctions
        "fixed_price_comp_count",     # how many were BIN
        "exact_grade_comp_count",     # how many matched the exact grade
        "valuation_basis",            # human-readable basis string
        "market_value_source",        # comp source detail
        "cluster_method",             # how the cluster was identified
        "grade_fallback_used",        # bool — fell back from exact grade?
        # Relaxation metadata (set when comp_relaxer rescued the valuation)
        "relaxation_level",           # 0..7 ladder step that produced the MV
        "relaxation_label",           # short id ("drop_co_star", "drop_serial")
        "relaxation_description",     # human-readable explanation
        "relaxation_query",           # actual query that hit
    ):
        v = _get(field, None)
        if v is not None:
            out[f"_mv_{field}"] = v

    out["_mv_source"] = "valuation_worker"

    # CACHE-2026-05-13: store the freshly-computed MV in the title-normalized
    # cache so other listings of the same card type (different sellers, same
    # physical card) get instant zero-API-cost MV reuse for up to 7 days.
    # Non-fatal if the cache write fails — we already have the MV stamped on
    # the row in `out`.
    try:
        import mv_cache
        mv_cache.store(title, out)
    except Exception as _cache_err:
        print(f"[valuation_worker] cache store error (non-fatal): {_cache_err}")

    return out


# ── Main worker loop ────────────────────────────────────────────────────────

def find_unvalued_rows(
    pool: Dict[str, Any],
    cutoff_secs: float = 86400.0,
    skip_time_check: bool = False,
) -> List[str]:
    """
    Return a priority-sorted list of item_ids needing valuation.
    cutoff_secs limits the window — rows ending more than 24h out aren't
    worth valuing yet (they may not survive to the action window anyway).

    skip_time_check: when True, ignore the end-time filter entirely. Used
    for the BIN pool where listings don't have an end-time deadline.
    """
    items = pool.get("items", {}) or {}
    candidates: List[Tuple[Tuple, str]] = []
    for item_id, row in items.items():
        if not isinstance(row, dict):
            continue
        if _row_has_confident_mv(row):
            continue
        if not skip_time_check:
            secs = _row_seconds_remaining(row)
            if secs is None:
                continue
            if secs <= 0:
                continue  # ended
            if secs > cutoff_secs:
                continue
        # Skip rows we tried recently (last 30 min) and got no confident MV
        # to avoid hammering the API on consistently-failing rows.
        last_attempt = float(row.get("_mv_computed_at") or 0)
        if last_attempt > 0 and (time.time() - last_attempt) < 1800.0:
            continue

        candidates.append((_priority_key(row), item_id))

    candidates.sort(key=lambda t: t[0])
    return [item_id for _, item_id in candidates]


def _process_pool_batch(
    pool_label: str,
    load_fn,
    save_fn,
    batch_size: int,
    skip_time_check: bool,
) -> Dict[str, Any]:
    """Process one pool's unvalued queue. Shared logic between auction
    and BIN pools — only the load/save functions and time-check flag differ."""
    pool = load_fn()
    queue = find_unvalued_rows(pool, skip_time_check=skip_time_check)
    if not queue:
        return {"label": pool_label, "queue_size": 0, "valued": 0, "failed": 0, "confident": 0}

    print(
        f"[valuation_worker] {pool_label} queue size: {len(queue)}, batch: {batch_size}",
        flush=True,
    )
    valued = 0
    failed = 0
    confident = 0

    for item_id in queue[:batch_size]:
        row = pool.get("items", {}).get(item_id)
        if not row:
            continue
        title = str(row.get("title") or row.get("source_title") or "")[:90]
        if skip_time_check:
            # BIN — no end-time context
            print(
                f"[valuation_worker] valuing {pool_label} {item_id[:20]}: {title}",
                flush=True,
            )
        else:
            secs = _row_seconds_remaining(row) or 0.0
            print(
                f"[valuation_worker] valuing {pool_label} {item_id[:20]} "
                f"({secs:.0f}s left): {title}",
                flush=True,
            )

        mv_data = _compute_mv_for_row(row)
        for k, v in mv_data.items():
            row[k] = v

        if mv_data.get("_mv_compute_error"):
            failed += 1
        else:
            valued += 1
            if str(row.get("truth")) == "TRUE" and row.get("true_mv"):
                confident += 1

    save_fn(pool)
    return {
        "label":      pool_label,
        "queue_size": len(queue),
        "valued":     valued,
        "failed":     failed,
        "confident":  confident,
    }


def run_batch(batch_size: int = DEFAULT_BATCH_SIZE) -> Dict[str, Any]:
    """Compute MVs for the top `batch_size` priority unvalued rows.

    AUCTION-PRIORITY-2026-05-15: drain auctions FIRST. Previously this
    split each batch 60% AUC / 40% BIN, which meant when 2,600 BIN listings
    landed in the pool the worker spent 40% of every cycle on BINs even
    when there were unvalued auctions sitting time-pressured. Bad: BINs
    have no clock; auctions end on a timer and an empty Ending Soon page
    is the conversion killer. New behavior: the auction pool gets the
    ENTIRE batch budget every cycle. BIN only gets cycles where the
    auction queue is empty. The BIN pool will fill in over time once
    auctions are healthy."""
    started = time.time()

    # Drain auctions first. If the auction queue is smaller than the batch,
    # spill the leftover capacity into BIN so we still make BIN progress.
    auction_result = _process_pool_batch(
        pool_label="AUC",
        load_fn=load_pool,
        save_fn=save_pool,
        batch_size=batch_size,
        skip_time_check=False,
    )
    auction_used = int(auction_result.get("valued", 0)) + int(auction_result.get("failed", 0))
    bin_budget = max(0, batch_size - auction_used)
    if bin_budget > 0:
        bin_result = _process_pool_batch(
            pool_label="BIN",
            load_fn=load_bin_pool,
            save_fn=save_bin_pool,
            batch_size=bin_budget,
            skip_time_check=True,
        )
    else:
        # Auctions consumed the full batch — BIN waits this cycle.
        bin_result = {"label": "BIN", "queue_size": 0, "valued": 0, "failed": 0, "confident": 0}

    # Compose the combined counters so the legacy print path still works
    valued = auction_result["valued"] + bin_result["valued"]
    failed = auction_result["failed"] + bin_result["failed"]
    confident = auction_result["confident"] + bin_result["confident"]
    total_queue = auction_result["queue_size"] + bin_result["queue_size"]

    if total_queue == 0:
        return {
            "ok":              True,
            "valued":          0,
            "queue_size":      0,
            "elapsed_seconds": round(time.time() - started, 1),
        }

    elapsed = round(time.time() - started, 1)
    queue_remaining = max(0, total_queue - batch_size)
    print(
        f"[valuation_worker] batch done in {elapsed}s — "
        f"AUC valued={auction_result['valued']}/{auction_result['queue_size']} · "
        f"BIN valued={bin_result['valued']}/{bin_result['queue_size']} · "
        f"confident={confident}, failed={failed}, queue_remaining={queue_remaining}",
        flush=True,
    )
    return {
        "ok":               True,
        "valued":           valued,
        "confident":        confident,
        "failed":           failed,
        "queue_size":       total_queue,
        "queue_remaining":  queue_remaining,
        "elapsed_seconds":  elapsed,
    }


def print_status() -> int:
    # ── Auction pool ─────────────────────────────────────────────────────
    pool = load_pool()
    items = pool.get("items", {}) or {}
    confident = sum(1 for r in items.values() if _row_has_confident_mv(r))
    queue = find_unvalued_rows(pool)
    print(f"[valuation_worker] STATUS — Auction pool")
    print(f"  pool file:                 {POOL_FILE}")
    print(f"  total items:               {len(items)}")
    print(f"  with confident MV:         {confident}")
    print(f"  queue (needs MV, in 24h):  {len(queue)}")
    if queue:
        print(f"  next 3 to value:")
        for item_id in queue[:3]:
            row = items.get(item_id, {})
            secs = _row_seconds_remaining(row) or 0
            title = str(row.get("title") or "")[:80]
            print(f"    [{secs/60:.0f}m left] {item_id[:24]}  {title}")

    # ── BIN pool ─────────────────────────────────────────────────────────
    bin_pool = load_bin_pool()
    bin_items = bin_pool.get("items", {}) or {}
    bin_confident = sum(1 for r in bin_items.values() if _row_has_confident_mv(r))
    bin_queue = find_unvalued_rows(bin_pool, skip_time_check=True)
    print()
    print(f"[valuation_worker] STATUS — BIN pool")
    print(f"  pool file:                 {BIN_POOL_FILE}")
    print(f"  total items:               {len(bin_items)}")
    print(f"  with confident MV:         {bin_confident}")
    print(f"  queue (needs MV):          {len(bin_queue)}")
    if bin_queue:
        print(f"  next 3 to value:")
        for item_id in bin_queue[:3]:
            row = bin_items.get(item_id, {})
            title = str(row.get("title") or "")[:80]
            print(f"    {item_id[:24]}  {title}")
    return 0


# ── CLI ─────────────────────────────────────────────────────────────────────

def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Background MV worker (Module 2 of 24h pipeline)")
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH_SIZE,
                        help=f"Rows to value per cycle (default {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--loop", action="store_true",
                        help="Run continuously, sleeping --interval between cycles")
    parser.add_argument("--interval", type=int, default=DEFAULT_LOOP_INTERVAL_SECS,
                        help=f"Seconds between cycles in --loop mode (default {DEFAULT_LOOP_INTERVAL_SECS})")
    parser.add_argument("--status", action="store_true",
                        help="Print queue status and exit")
    args = parser.parse_args(argv)

    if args.status:
        return print_status()

    if not args.loop:
        result = run_batch(batch_size=args.batch)
        return 0 if result.get("ok") else 1

    # --loop mode — smaller batches per cycle so we drain the queue smoothly
    print(f"[valuation_worker] loop mode — batch={DEFAULT_LOOP_BATCH}, interval={args.interval}s")
    while True:
        if _is_scan_paused():
            print("[valuation_worker] PAUSED via SNIPEWINS_SCAN_PAUSED — skipping cycle", flush=True)
        else:
            try:
                import daily_budget
                if daily_budget.is_budget_exceeded():
                    _summ = daily_budget.get_budget_summary()
                    print(
                        f"[valuation_worker] DAILY BUDGET REACHED "
                        f"({_summ['calls_today']}/{_summ['daily_budget']} calls today) — "
                        f"skipping cycle until UTC rollover",
                        flush=True,
                    )
                else:
                    _result = run_batch(batch_size=DEFAULT_LOOP_BATCH)
                    # DAILY-BUDGET-2026-05-15: each card processed in a batch
                    # fires up to ~3 comp searches (after relaxation cap),
                    # often 1-2 with cache hits. We estimate calls as
                    # (valued + failed) × 2 — a middle ground between best
                    # case (1 call/card via cache) and worst case (3 passes).
                    try:
                        _cards = int(_result.get("valued", 0)) + int(_result.get("failed", 0))
                        daily_budget.record_calls(_cards * 2)
                    except Exception:
                        pass
            except KeyboardInterrupt:
                print("[valuation_worker] interrupted")
                return 130
            except Exception as exc:
                print(f"[valuation_worker] cycle error: {type(exc).__name__}: {exc}")
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            return 130


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
