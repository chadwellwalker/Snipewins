"""
steals_engine.py — SnipeWins "Steals" deal scanner.

Mirrors SportsCardsPro's eBay Deal Scanner, but scoped to YOUR tracked universe:
takes the already-discovered BIN pool (bin_pool.json), values each listing against
the SportsCardsPro graded price guide (scp_price_store, local + free), and surfaces
Buy-It-Now listings priced below market by your savings thresholds.

No eBay API calls happen here — discovery already ran (daily_bin_pool, hard-capped
so it never starves auctions); this is pure valuation + filtering.

Run:  python steals_engine.py            # rebuild steals.json from bin_pool.json
Read: load_steals()                       # for the UI tab
"""
from __future__ import annotations
import json, os, time
from pathlib import Path
from typing import Any, Dict, List, Optional

import scp_price_store as scp

HERE = Path(__file__).parent
BIN_POOL = Path(os.environ.get("SNIPEWINS_BIN_POOL_PATH") or str(HERE / "bin_pool.json"))
STEALS_OUT = Path(os.environ.get("SNIPEWINS_STEALS_PATH") or str(HERE / "steals.json"))

# Grade filters mirror the SportsCardsPro scanner UI checkboxes.
GRADE_LABELS = {
    "RAW": "Ungraded", "GR7": "Grade 7", "GR8": "Grade 8", "GR9": "Grade 9",
    "GR9_5": "BGS 9.5", "PSA10": "PSA 10", "BGS10": "BGS 10", "CGC10": "CGC 10", "SGC10": "SGC 10",
}


def _price(row: Dict[str, Any]) -> float:
    for k in ("current_price", "price", "bin_price"):
        v = row.get(k)
        try:
            f = float(str(v).replace("$", "").replace(",", "").strip())
            if f > 0:
                return f
        except (TypeError, ValueError):
            continue
    return 0.0


def build_steals(
    *,
    min_savings: float = 30.0,
    min_savings_pct: float = 0.15,
    sport: Optional[str] = None,
    grades: Optional[set] = None,
    limit: int = 750,
    write: bool = True,
) -> List[Dict[str, Any]]:
    """Scan the BIN pool for below-market Buy-It-Now listings."""
    try:
        pool = json.loads(BIN_POOL.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return []
    items = pool.get("items", {}) or {}
    out: List[Dict[str, Any]] = []
    scanned = matched = 0
    for iid, row in items.items():
        if not isinstance(row, dict):
            continue
        price = _price(row)
        if price <= 0:
            continue
        if sport and str(row.get("sport", "")).upper() != sport.upper():
            continue
        title = str(row.get("title") or "")
        scanned += 1
        r = scp.lookup(title)
        mv = r.get("market_value")
        if not mv or mv <= 0:
            continue
        gk = r.get("grade_key", "RAW")
        if grades and gk not in grades:
            continue
        matched += 1
        savings = mv - price
        if savings < min_savings:
            continue
        pct = savings / mv if mv else 0.0
        if pct < min_savings_pct:
            continue
        out.append({
            "item_id": iid,
            "title": title[:140],
            "price": round(price, 2),
            "market_value": mv,
            "savings": round(savings, 2),
            "savings_pct": round(pct * 100, 1),
            "grade": gk,
            "grade_label": GRADE_LABELS.get(gk, gk),
            "sport": row.get("sport"),
            "player": row.get("player_name"),
            "url": row.get("url"),
            "thumbnail": row.get("thumbnail"),
            "matched_product": r.get("matched"),
            "match_score": r.get("score"),
        })
    out.sort(key=lambda x: (x["savings_pct"], x["savings"]), reverse=True)
    out = out[:limit]
    if write:
        try:
            STEALS_OUT.write_text(json.dumps(
                {"generated_ts": time.time(), "scanned": scanned, "matched": matched,
                 "count": len(out), "steals": out}, indent=2), encoding="utf-8")
        except Exception:
            pass
    return out


def load_steals() -> Dict[str, Any]:
    try:
        return json.loads(STEALS_OUT.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {"generated_ts": 0, "count": 0, "steals": []}


if __name__ == "__main__":
    t = time.time()
    steals = build_steals()
    print(f"built {len(steals)} steals in {time.time()-t:.1f}s -> {STEALS_OUT.name}")
    for s in steals[:15]:
        print(f"  +{s['savings_pct']:>5.1f}%  ${s['savings']:>8,.0f}  "
              f"${s['price']:>8,.2f} -> ${s['market_value']:>9,.2f}  [{s['grade']:5}] {s['title'][:54]}")
