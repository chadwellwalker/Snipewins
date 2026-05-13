"""
daily_bin_pool.py — Continuous Buy-It-Now scanner. Module 5 of the pipeline.

Mirrors daily_pool.py but for FIXED_PRICE (BIN) listings instead of auctions.
Fetches new BIN inventory across the same tracked player/product universe,
applies chase_rules + sport-suppression, and writes the survivors to
bin_pool.json for the dashboard.

Why a separate file: BIN has different semantics from auctions. There's
no "ends in N hours" urgency. We sort by "freshly listed" + "under target"
instead. Keeping the pipelines separate also makes the data easier to
reason about — `daily_pool.json` is always auctions, `bin_pool.json` is
always BIN. No mode flags, no ambiguity.

Architecture:
    daily_bin_pool.py
        ↓ runs every 30 minutes, builds BIN query specs from chase_rules
    bin_pool.json
        ↓ read by valuation_worker.py (same worker handles both pools)
    bin_pool.json (with MVs)
        ↓ read by bin_view.py (Streamlit Buying Radar tab)
    UI

Usage:
    Manual one-off:           python daily_bin_pool.py
    Background loop (30 min): python daily_bin_pool.py --loop
    Status check:             python daily_bin_pool.py --status

Atomic writes via tmp + replace so the valuation worker never reads a
half-written file. Idempotent merge — re-running won't duplicate rows.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


HERE = Path(__file__).parent
POOL_FILE = HERE / "bin_pool.json"
LOG_FILE  = HERE / "daily_bin_pool.log"

DEFAULT_LOOP_INTERVAL_SECS = 1800  # 30 minutes — twice as fresh as auctions
MAX_ITEMS_PER_SPEC         = 50    # eBay returns up to 200; 50 is the sweet
                                   # spot between coverage and API budget.


# ── Persistence ─────────────────────────────────────────────────────────────

def load_pool() -> Dict[str, Any]:
    if not POOL_FILE.exists():
        return {"version": 1, "items": {}, "last_fetch_ts": 0.0, "last_fetch_iso": ""}
    try:
        return json.loads(POOL_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[daily_bin_pool] WARN: couldn't parse {POOL_FILE.name}: {exc}. Starting fresh.")
        return {"version": 1, "items": {}, "last_fetch_ts": 0.0, "last_fetch_iso": ""}


def save_pool(pool: Dict[str, Any]) -> None:
    tmp = str(POOL_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(pool, fh, indent=2, sort_keys=True, default=str)
    os.replace(tmp, POOL_FILE)


# ── Row extraction + merging ────────────────────────────────────────────────

def _extract_item_id(row: Dict[str, Any]) -> str:
    for k in ("item_id", "itemId", "source_item_id"):
        v = (row or {}).get(k)
        if v:
            return str(v)
    title = str((row or {}).get("title") or "")
    return f"title:{title[:96]}" if title else f"unknown:{id(row)}"


def _row_current_price(row: Dict[str, Any]) -> float:
    """Pull BIN price from whichever field the engine stamps."""
    for k in (
        "current_price", "current_bid", "_authoritative_current_price",
        "_board_current_price",
    ):
        v = (row or {}).get(k)
        try:
            if v is not None and float(v) > 0:
                return float(v)
        except Exception:
            pass
    # eBay Browse nested shapes
    for nested_key in ("price", "currentBidPrice"):
        nested = (row or {}).get(nested_key) or {}
        if isinstance(nested, dict):
            v = nested.get("value")
            try:
                if v is not None and float(v) > 0:
                    return float(v)
            except Exception:
                pass
    return 0.0


def _extract_player_slug(row: Dict[str, Any]) -> str:
    """Same logic as daily_pool — chase_rules expects snake_case slugs."""
    for k in ("target_entity_id", "player_id"):
        v = (row or {}).get(k)
        if v:
            return str(v).strip().lower().replace("-", "_").replace(" ", "_")
    raw = str(
        (row or {}).get("target_player_name")
        or (row or {}).get("canonical_player")
        or (row or {}).get("player_name")
        or ""
    ).strip().lower()
    if not raw:
        return ""
    normalized = unicodedata.normalize("NFKD", raw)
    folded = "".join(c for c in normalized if not unicodedata.combining(c))
    cleaned = re.sub(r"[\'\.\,]", "", folded)
    cleaned = re.sub(r"[\s\-_]+", "_", cleaned)
    return cleaned.strip("_")


def _evaluate_chase_rules(row: Dict[str, Any]) -> Dict[str, Any]:
    """Run a BIN row through chase_rules.evaluate_card_target. Same rules
    as auction pipeline — a chase card is a chase card regardless of
    listing type. Returns the decision dict (qualifies, reason, priority,
    player_tier, signals)."""
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
    items: Dict[str, Any] = pool.setdefault("items", {})
    counts = {
        "added": 0,
        "updated": 0,
        "rejected_by_chase_rules": 0,
    }
    for row in (new_rows or []):
        if not isinstance(row, dict):
            continue
        item_id = _extract_item_id(row)
        if not item_id or item_id.startswith("unknown:"):
            continue

        # chase_rules gate — same filter as the auction pipeline.
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

        # Stamp chase decision so bin_view can sort + audit.
        row["_chase_priority"]    = int(_eval.get("priority") or 0)
        row["_chase_reason"]      = str(_eval.get("reason") or "")
        row["_chase_player_tier"] = str(_eval.get("player_tier") or "?")
        # Marker that distinguishes BIN rows from auction rows in the
        # combined valuation worker view.
        row["_source"] = "bin"

        existing = items.get(item_id)
        if existing is None:
            items[item_id] = dict(row)
            items[item_id]["_pool_first_seen_ts"] = time.time()
            items[item_id]["_pool_last_seen_ts"]  = time.time()
            counts["added"] += 1
            continue

        # Existing entry — preserve prior MV if we had one.
        prior_has_mv = bool(existing.get("true_mv") or existing.get("market_value"))
        new_has_mv   = bool(row.get("true_mv") or row.get("market_value"))
        merged = dict(row)
        merged["_pool_first_seen_ts"] = existing.get("_pool_first_seen_ts") or time.time()
        merged["_pool_last_seen_ts"]  = time.time()
        if prior_has_mv and not new_has_mv:
            for k in ("true_mv", "market_value", "target_bid", "truth", "truth_level",
                      "_mv_computed_at", "_mv_source", "_mv_confidence",
                      "_mv_comp_count", "_mv_accepted_comp_count"):
                if k in existing:
                    merged[k] = existing[k]

        # ALWAYS preserve worker-stamped diagnostic / cooldown / progress fields
        # so the valuation worker's attempt history and partial state survive
        # across BIN refresh cycles. (Mirrors the same fix in daily_pool.py.)
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
            if k not in merged and k in existing:
                merged[k] = existing[k]

        items[item_id] = merged
        counts["updated"] += 1
    return counts


def prune_no_longer_listed(pool: Dict[str, Any], stale_after_hours: float = 24.0) -> int:
    """Drop rows we haven't seen in the last N hours. BIN listings come and
    go (sellers end early, sold, etc.). If a row didn't show up in this
    fetch and it's been more than stale_after_hours since we last saw it,
    evict. Default 24h — generous because some sellers leave BIN listings
    up for weeks."""
    items: Dict[str, Any] = pool.get("items", {})
    pruned = 0
    now = time.time()
    cutoff = stale_after_hours * 3600.0
    for item_id in list(items.keys()):
        row = items[item_id]
        last_seen = float(row.get("_pool_last_seen_ts") or 0.0)
        if last_seen > 0 and (now - last_seen) > cutoff:
            del items[item_id]
            pruned += 1
    return pruned


# ── Fetch driver — calls the engine's BIN fetcher per spec ──────────────────

def fetch_and_update() -> Dict[str, Any]:
    """One cycle: fetch BIN listings for every tracked spec, merge, prune."""
    started = time.time()

    pool = load_pool()
    items_before = len(pool.get("items", {}) or {})

    # Lazy import — heavy.
    print(f"[daily_bin_pool] importing ending_soon_engine + player_hub…", flush=True)
    sys.path.insert(0, str(HERE))
    os.chdir(HERE)
    import ending_soon_engine as ese
    import player_hub

    # Build BIN query specs from the player_hub state. listing_mode="bin"
    # tells player_hub to construct queries with the FIXED_PRICE intent.
    # NOTE: actual function is load_player_hub_state, not load_state.
    ph_state = player_hub.load_player_hub_state()
    try:
        specs = list(
            player_hub.build_query_specs_for_listing_mode(
                ph_state,
                listing_mode="bin",
                sport_filter=None,
            )
            or []
        )
    except Exception as exc:
        print(f"[daily_bin_pool] ERROR: player_hub failed: {type(exc).__name__}: {exc}")
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {str(exc)[:200]}",
            "elapsed_seconds": round(time.time() - started, 1),
        }

    print(f"[daily_bin_pool] built {len(specs)} BIN query specs", flush=True)

    # Fetch each spec via the engine's existing BIN fetcher. We reuse the
    # engine's auth + throttle + parse logic so the API behavior matches
    # exactly what the auction pipeline does.
    all_rows: List[Dict[str, Any]] = []
    rate_limited = False
    failed_specs = 0
    for i, spec in enumerate(specs, start=1):
        # BIN-FIX 2026-05-12: build_target_scan_query_specs doesn't stamp
        # `sport` on the spec, but _fetch_bin_for_spec needs it (was raising
        # KeyError on every spec → zero BIN cards in the pool). Hoist it
        # from tracked_target before the call so chase_rules + the worker
        # see a proper `sport` on every row this fetch produces.
        if not spec.get("sport"):
            _tt = spec.get("tracked_target") or {}
            _hoisted_sport = str(_tt.get("sport") or "").strip()
            if _hoisted_sport:
                spec["sport"] = _hoisted_sport
        try:
            items, was_rate_limited, _pre_count = ese._fetch_bin_for_spec(spec)
        except Exception as exc:
            failed_specs += 1
            if failed_specs <= 3:
                print(
                    f"[daily_bin_pool] spec #{i} failed "
                    f"({spec.get('player_name', '?')}): {type(exc).__name__}: {exc}"
                )
            continue
        if was_rate_limited:
            rate_limited = True
            print(f"[daily_bin_pool] rate-limited at spec #{i}; pausing 30s")
            time.sleep(30.0)
            continue
        if items:
            all_rows.extend(items)
        if i % 25 == 0:
            print(
                f"[daily_bin_pool] progress: {i}/{len(specs)} specs, "
                f"{len(all_rows)} raw items so far",
                flush=True,
            )

    print(
        f"[daily_bin_pool] fetch complete — {len(all_rows)} raw items from "
        f"{len(specs)} specs ({failed_specs} failures, rate_limited={rate_limited})",
        flush=True,
    )

    # RACE-FIX 2026-05-11: re-read the pool from disk RIGHT BEFORE merging.
    # The BIN fetch loop above can run for many minutes (one HTTP call per
    # player spec), during which the valuation_worker may have stamped
    # _mv_* fields on rows. If we merge against the stale `pool` snapshot
    # we took at the start of the cycle, we'll save back over the worker's
    # writes. Re-reading here gives merge_into_pool the freshest `existing`
    # rows, and the always-preserve worker-keys loop inside merge_into_pool
    # then carries the worker stamps forward onto the merged entry.
    try:
        fresh_pool = load_pool()
        pool = fresh_pool
    except Exception as _exc:
        print(f"[daily_bin_pool] WARN: pool re-read before merge failed: {_exc}", flush=True)

    # Merge survivors into the pool (chase_rules gate fires inside merge).
    merge_counts = merge_into_pool(pool, all_rows)
    stale_pruned = prune_no_longer_listed(pool)

    pool["last_fetch_ts"]  = started
    pool["last_fetch_iso"] = datetime.fromtimestamp(started, tz=timezone.utc).isoformat(timespec="seconds")
    pool["last_fetch_meta"] = {
        "specs_built":            int(len(specs)),
        "raw_items_returned":     int(len(all_rows)),
        "failed_specs":           int(failed_specs),
        "rate_limited":           bool(rate_limited),
        "merge_counts":           dict(merge_counts),
        "pruned_stale":           int(stale_pruned),
        "items_before":           int(items_before),
        "items_after":            int(len(pool.get("items", {}) or {})),
    }
    save_pool(pool)

    summary = {
        "ok":              True,
        "elapsed_seconds": round(time.time() - started, 1),
        "items_before":    items_before,
        "items_after":     len(pool.get("items", {}) or {}),
        "added":           merge_counts["added"],
        "updated":         merge_counts["updated"],
        "rejected":        merge_counts["rejected_by_chase_rules"],
        "stale_pruned":    stale_pruned,
    }
    print(
        f"[daily_bin_pool] cycle done in {summary['elapsed_seconds']}s "
        f"— added={summary['added']} updated={summary['updated']} "
        f"rejected={summary['rejected']} stale_pruned={summary['stale_pruned']} "
        f"pool_size={summary['items_after']}",
        flush=True,
    )
    return summary


# ── Status / observability ──────────────────────────────────────────────────

def print_status() -> int:
    pool = load_pool()
    items = pool.get("items", {}) or {}
    last_ts = float(pool.get("last_fetch_ts") or 0.0)
    age = (time.time() - last_ts) if last_ts > 0 else float("inf")
    age_str = f"{age/60:.1f}m" if age != float("inf") else "never"
    confident = sum(1 for r in items.values() if r.get("true_mv") or r.get("market_value"))
    print(f"[daily_bin_pool] STATUS")
    print(f"  pool file:           {POOL_FILE}")
    print(f"  total BIN items:     {len(items)}")
    print(f"  with confident MV:   {confident}")
    print(f"  last fetch:          {age_str} ago")
    return 0


# ── CLI ─────────────────────────────────────────────────────────────────────

class _Tee:
    """Mirror writes to terminal + log file."""
    def __init__(self, *streams):
        self._streams = [s for s in streams if s is not None]
    def write(self, data):
        for s in self._streams:
            try: s.write(data)
            except Exception: pass
    def flush(self):
        for s in self._streams:
            try: s.flush()
            except Exception: pass
    def isatty(self):
        try: return bool(self._streams[0].isatty())
        except Exception: return False


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Daily BIN pool fetcher (Module 5 of pipeline)")
    parser.add_argument("--loop", action="store_true",
                        help="Run continuously, fetching every --interval seconds")
    parser.add_argument("--interval", type=int, default=DEFAULT_LOOP_INTERVAL_SECS,
                        help=f"Seconds between cycles in --loop mode (default {DEFAULT_LOOP_INTERVAL_SECS})")
    parser.add_argument("--status", action="store_true",
                        help="Print BIN pool status and exit")
    args = parser.parse_args(argv)

    if args.status:
        return print_status()

    # Mirror output to log file for post-hoc debugging
    try:
        if LOG_FILE.exists():
            prev = LOG_FILE.with_suffix(".log.prev")
            if prev.exists():
                prev.unlink()
            LOG_FILE.rename(prev)
        log_fh = LOG_FILE.open("w", encoding="utf-8", errors="replace", buffering=1)
        log_fh.write(f"# daily_bin_pool run started {datetime.now().isoformat(timespec='seconds')}\n")
        log_fh.write(f"# argv={argv}\n# cwd={HERE}\n\n")
        sys.stdout = _Tee(sys.__stdout__, log_fh)
        sys.stderr = _Tee(sys.__stderr__, log_fh)
    except Exception as exc:
        print(f"[daily_bin_pool] WARN: couldn't open log {LOG_FILE}: {exc}")

    if not args.loop:
        result = fetch_and_update()
        return 0 if result.get("ok") else 1

    print(f"[daily_bin_pool] entering loop mode — interval={args.interval}s")
    while True:
        try:
            fetch_and_update()
        except KeyboardInterrupt:
            print("[daily_bin_pool] interrupted, exiting")
            return 130
        except Exception as exc:
            print(f"[daily_bin_pool] cycle error: {type(exc).__name__}: {exc}")
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("[daily_bin_pool] interrupted, exiting")
            return 130


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
