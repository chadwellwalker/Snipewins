"""
reset_mv_cooldown.py — Clear the valuation_worker's per-row cooldown
flags so it re-attempts valuation on every card immediately.

The worker has a 30-minute cooldown per row that prevents it from
retrying the same card too often. When you've just shipped new
relaxation logic (or comp_relaxer changes), you typically want to
force a fresh pass without waiting for the cooldown to expire.

Usage:
    python reset_mv_cooldown.py

This wipes _mv_computed_at and _mv_compute_attempted from every row
in daily_pool.json, then saves atomically. The next time the worker
runs (whether already in --loop or freshly started), the queue will
contain every unvalued card.

Safe to run while the worker is running — atomic write means the
worker reads either the old version or the new version, never a
half-written file.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path


HERE = Path(__file__).parent
POOL_FILE = HERE / "daily_pool.json"


def main() -> int:
    if not POOL_FILE.exists():
        print(f"[reset_mv_cooldown] no pool file at {POOL_FILE}")
        return 1
    try:
        pool = json.loads(POOL_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[reset_mv_cooldown] couldn't parse pool: {exc}")
        return 1

    items = pool.get("items") or {}
    reset_n = 0
    for item_id, row in items.items():
        if not isinstance(row, dict):
            continue
        if row.get("_mv_computed_at") is None and not row.get("_mv_compute_attempted"):
            continue
        # Clear cooldown markers — worker will see these as never-attempted.
        for k in ("_mv_computed_at", "_mv_compute_attempted"):
            row.pop(k, None)
        reset_n += 1

    # Atomic write
    tmp = str(POOL_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(pool, fh, indent=2, sort_keys=True, default=str)
    os.replace(tmp, POOL_FILE)

    print(
        f"[reset_mv_cooldown] cleared cooldown on {reset_n} of "
        f"{len(items)} rows. Worker will re-attempt valuation on its "
        f"next loop tick (within {time.time():.0f}s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
