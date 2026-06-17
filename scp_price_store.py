"""
scp_price_store.py — SportsCardsPro CSV-backed market-value store for SnipeWins.

eBay's Finding (sold) API is decommissioned and Marketplace Insights is
partner-gated, so we value cards from SportsCardsPro's Legendary per-set CSV
price guides (full graded ladder) loaded into a local SQLite table. Zero
per-card API calls, no eBay quota.

Pipeline:
    1. Drop each set's CSV into SNIPEWINS_SCP_CSV_DIR (default ./scp_csv).
    2. rebuild_store()   (or: python scp_price_store.py --rebuild)
    3. lookup(title) -> dict with market_value at the listing's grade.
"""
from __future__ import annotations

import csv
import os
import re
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).parent
CSV_DIR = Path(os.environ.get("SNIPEWINS_SCP_CSV_DIR") or str(HERE / "scp_csv"))
DB_PATH = Path(os.environ.get("SNIPEWINS_SCP_DB_PATH") or str(HERE / "scp_prices.db"))

GRADE_COLUMN = {
    "RAW": "loose_price", "GR7": "cib_price", "GR8": "new_price",
    "GR9": "graded_price", "GR9_5": "box_only_price", "PSA10": "manual_only_price",
    "BGS10": "bgs_10_price", "CGC10": "condition_17_price", "SGC10": "condition_18_price",
}
CSV_TO_COL = {
    "loose-price": "loose_price", "cib-price": "cib_price", "new-price": "new_price",
    "graded-price": "graded_price", "box-only-price": "box_only_price",
    "manual-only-price": "manual_only_price", "bgs-10-price": "bgs_10_price",
    "condition-17-price": "condition_17_price", "condition-18-price": "condition_18_price",
}
PRICE_COLS = list(CSV_TO_COL.values())

_GRADE_RE = re.compile(r"\b(psa|bgs|sgc|cgc|hga)\s*(10|[1-9](?:\.5)?)\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
_NUM_RE = re.compile(r"#\s*([A-Za-z]{0,4}-?\d+[A-Za-z]?)")
_SET_STOP = {"cards", "baseball", "football", "basketball", "hockey", "soccer",
             "racing", "wrestling", "ufc", "pokemon"}
# Unambiguous SET names (not parallels). If a listing names one of these and the
# matched product's set doesn't, it's a different product -> reject. Excludes
# words that double as parallels (chrome, prizm, optic, refractor, gold, cosmic).
_HARD_SETS = {"stadium", "club", "heritage", "ginter", "allen", "gallery", "gypsy",
              "archives", "museum", "tribute", "inception", "contenders", "immaculate",
              "flawless", "obsidian", "finest", "sapphire", "mosaic", "spectra", "select",
              "treasures", "national", "definitive", "sterling"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = s.encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9#/\- ]", " ", s)
    return " ".join(s.split())


def _tokens(s: str) -> List[str]:
    return [t for t in _norm(s).replace("#", " ").replace("/", " ").split() if t]


def _cents(v: Any) -> Optional[int]:
    s = str(v or "").strip().replace("$", "").replace(",", "")
    if not s:
        return None
    try:
        n = int(round(float(s) * 100))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _int(v: Any) -> int:
    s = str(v or "").strip().replace(",", "")
    try:
        return int(float(s)) if s else 0
    except (TypeError, ValueError):
        return 0


def detect_grade_key(title: str) -> str:
    m = _GRADE_RE.search(title or "")
    if not m:
        return "RAW"
    svc, num = m.group(1).lower(), m.group(2)
    if num == "10":
        return {"psa": "PSA10", "bgs": "BGS10", "cgc": "CGC10", "sgc": "SGC10"}.get(svc, "PSA10")
    if num == "9.5":
        return "GR9_5"
    if num.startswith("9"):
        return "GR9"
    if num.startswith("8"):
        return "GR8"
    if num.startswith("7"):
        return "GR7"
    return "RAW"


def parse_product_name(product_name: str) -> Tuple[str, str, str]:
    pn = product_name or ""
    parallel = ""
    mpar = re.search(r"\[([^\]]+)\]", pn)
    if mpar:
        parallel = _norm(mpar.group(1))
    number = ""
    mnum = _NUM_RE.search(pn)
    if mnum:
        number = _norm(mnum.group(1))
    player = re.sub(r"\[[^\]]*\]", " ", pn)
    player = re.sub(r"#\s*[A-Za-z0-9\-]+", " ", player)
    player = _norm(player)
    return player, parallel, number


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    return c


def rebuild_store(csv_dir: Optional[Path] = None) -> Dict[str, Any]:
    global _PLAYER_CACHE
    _PLAYER_CACHE = None
    d = Path(csv_dir or CSV_DIR)
    files = sorted(d.glob("*.csv")) if d.exists() else []
    con = _conn()
    cur = con.cursor()
    cur.execute("DROP TABLE IF EXISTS products")
    price_col_defs = ", ".join("{} INTEGER".format(c) for c in PRICE_COLS)
    cur.execute(
        "CREATE TABLE products ("
        "scp_id TEXT, console_name TEXT, product_name TEXT, "
        "console_norm TEXT, player_norm TEXT, parallel_norm TEXT, card_number TEXT, "
        "year TEXT, sales_volume INTEGER, release_date TEXT, src_file TEXT, "
        + price_col_defs + ")"
    )
    fixed_cols = ("scp_id,console_name,product_name,console_norm,player_norm,"
                  "parallel_norm,card_number,year,sales_volume,release_date,src_file")
    insert_sql = (
        "INSERT INTO products (" + fixed_cols + "," + ",".join(PRICE_COLS) + ") "
        "VALUES (" + ",".join(["?"] * (11 + len(PRICE_COLS))) + ")"
    )
    n = 0
    for fp in files:
        with open(fp, newline="", encoding="utf-8", errors="ignore") as fh:
            for r in csv.DictReader(fh):
                cn = r.get("console-name", "") or ""
                pn = r.get("product-name", "") or ""
                player, parallel, number = parse_product_name(pn)
                ymatch = _YEAR_RE.search(cn)
                price_vals = [_cents(r.get(csvk)) for csvk in CSV_TO_COL]
                cur.execute(
                    insert_sql,
                    [r.get("id", ""), cn, pn, _norm(cn), player, parallel, number,
                     ymatch.group(1) if ymatch else "",
                     _int(r.get("sales-volume")), r.get("release-date", ""), fp.name,
                     *price_vals],
                )
                n += 1
    cur.execute("CREATE INDEX idx_player ON products(player_norm)")
    cur.execute("CREATE INDEX idx_year ON products(year)")
    con.commit()
    players = cur.execute(
        "SELECT COUNT(DISTINCT player_norm) FROM products WHERE player_norm != ''"
    ).fetchone()[0]
    con.close()
    return {"files": [f.name for f in files], "rows": n, "distinct_players": players,
            "db": str(DB_PATH)}


_PLAYER_CACHE: Optional[List[Tuple[str, frozenset]]] = None


def _load_players(cur) -> List[Tuple[str, frozenset]]:
    global _PLAYER_CACHE
    if _PLAYER_CACHE is None:
        rows = cur.execute(
            "SELECT DISTINCT player_norm FROM products WHERE player_norm!=''"
        ).fetchall()
        _PLAYER_CACHE = [(r[0], frozenset(r[0].split())) for r in rows]
    return _PLAYER_CACHE


def _detect_player(title_tokens: frozenset, cur) -> Optional[str]:
    best, best_len = None, 0
    for pname, pset in _load_players(cur):
        if pset and pset <= title_tokens and len(pset) > best_len:
            best, best_len = pname, len(pset)
    return best


def lookup(title: str, *, min_score: float = 0.45) -> Dict[str, Any]:
    grade_key = detect_grade_key(title)
    if not DB_PATH.exists():
        return {"market_value": None, "matched": None, "reason": "store_not_built",
                "grade_key": grade_key, "score": 0.0, "sales_volume": 0}
    con = _conn()
    cur = con.cursor()
    try:
        grade_col = GRADE_COLUMN[grade_key]
        toks = frozenset(_tokens(title))
        ym = _YEAR_RE.search(title)
        year = ym.group(1) if ym else ""
        numm = _NUM_RE.search(title)
        listing_num = _norm(numm.group(1)) if numm else ""

        player = _detect_player(toks, cur)
        if not player:
            return {"market_value": None, "matched": None, "reason": "no_player_match",
                    "grade_key": grade_key, "score": 0.0, "sales_volume": 0}

        rows = cur.execute("SELECT * FROM products WHERE player_norm=?", (player,)).fetchall()
        leftover = toks - set(player.split())
        best, best_score = None, 0.0
        for row in rows:
            cset = set((row["console_norm"] or "").split()) - _SET_STOP
            if row["year"]:
                cset.discard(row["year"])
            set_overlap = len(cset & toks)
            if cset and set_overlap == 0:
                continue                              # different set entirely — skip
            # Reject when the listing names an unambiguous set this product isn't
            # (e.g. "Stadium Club"/"Heritage" listing vs flagship Topps product).
            if (toks & _HARD_SETS) - (cset & _HARD_SETS):
                continue
            score = 0.0
            if cset:
                set_ratio = set_overlap / len(cset)
                score += 0.4 * set_ratio
                score += 0.05 * set_overlap   # prefer the more specific set when several match
                if set_ratio < 0.5:
                    score -= 0.45                     # weak set overlap -> likely wrong set
            par = set((row["parallel_norm"] or "").split())
            if par:
                inter = len(par & leftover)
                score += 0.6 * (inter / len(par))
                score += 0.05 * inter
            else:
                score += 0.15
            if year and row["year"] and row["year"] != year:
                continue                              # different year — never cross-year match
            if year and row["year"] == year:
                score += 0.2
            if listing_num and row["card_number"] and listing_num == _norm(row["card_number"]):
                score += 0.25
            if score > best_score:
                best, best_score = row, score

        if not best or best_score < min_score:
            return {"market_value": None,
                    "matched": best["product_name"] if best else None,
                    "reason": "low_match_score", "grade_key": grade_key,
                    "score": round(best_score, 3), "sales_volume": 0}

        cents = best[grade_col]
        mv = round(cents / 100.0, 2) if isinstance(cents, int) and cents > 0 else None
        return {
            "market_value": mv,
            "matched": best["product_name"],
            "matched_set": best["console_name"],
            "grade_key": grade_key,
            "grade_available": mv is not None,
            "score": round(best_score, 3),
            "sales_volume": best["sales_volume"] or 0,
            "scp_id": best["scp_id"],
            "reason": "ok" if mv is not None else "grade_price_missing",
        }
    finally:
        con.close()


def store_stats() -> Dict[str, Any]:
    if not DB_PATH.exists():
        return {"built": False}
    con = _conn()
    cur = con.cursor()
    n = cur.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    sets = cur.execute("SELECT COUNT(DISTINCT console_name) FROM products").fetchone()[0]
    players = cur.execute(
        "SELECT COUNT(DISTINCT player_norm) FROM products WHERE player_norm!=''").fetchone()[0]
    graded = cur.execute("SELECT COUNT(*) FROM products WHERE manual_only_price>0").fetchone()[0]
    con.close()
    return {"built": True, "rows": n, "sets": sets, "players": players,
            "rows_with_psa10": graded, "db": str(DB_PATH)}


if __name__ == "__main__":
    if "--rebuild" in sys.argv:
        t = time.time()
        print(rebuild_store())
        print("rebuilt in {:.1f}s".format(time.time() - t))
    print(store_stats())



# ── Valuation + comps breakdown (for the "View Comps" dropdown) ───────────────
_GRADE_DISPLAY = {
    "loose_price": "Ungraded", "cib_price": "Grade 7", "new_price": "Grade 8",
    "graded_price": "Grade 9", "box_only_price": "BGS 9.5", "manual_only_price": "PSA 10",
    "bgs_10_price": "BGS 10", "condition_17_price": "CGC 10", "condition_18_price": "SGC 10",
}
_AUTO_RE = re.compile(r"\b(auto|autograph|signature|signed|sig)\b", re.IGNORECASE)
_PANINI_HINTS = ("panini", "prizm", "select", "optic", "mosaic", "donruss", "contenders",
                 "certified", "absolute", "obsidian", "illusions", "spectra", "phoenix",
                 "immaculate", "flawless", "national treasures", "chronicles", "zenith",
                 "revolution", "score", "luminance", "xr", "playbook", "origins")
_SUPER_RE = re.compile(r"superfractor|1\s*of\s*1|\b1/1\b", re.IGNORECASE)


def _brand_family(text: str) -> str:
    """Coarse brand bucket so Panini cards don't comp against Topps/Bowman."""
    t = (text or "").lower()
    if "panini" in t or any(h in t for h in _PANINI_HINTS):
        return "panini"
    if "topps" in t or "bowman" in t:
        return "topps"
    return ""


def _grade_ladder(row) -> List[Dict[str, Any]]:
    out = []
    for col, label in _GRADE_DISPLAY.items():
        v = row[col] if col in row.keys() else None
        if isinstance(v, int) and v > 0:
            out.append({"label": label, "price": round(v / 100.0, 2), "col": col})
    return out


def _proxy(cur, player: str, grade_col: str, is_auto: bool, ultra: bool, listing_brand: str) -> Dict[str, Any]:
    rows = cur.execute("SELECT * FROM products WHERE player_norm=?", (player,)).fetchall()
    cands = []
    for r in rows:
        # Same brand family only (Panini cards comp vs Panini, Topps vs Topps).
        rb = _brand_family(r["console_name"])
        if listing_brand and rb and rb != listing_brand:
            continue
        price = r[grade_col] if (isinstance(r[grade_col], int) and r[grade_col] > 0) else None
        if price is None:
            price = r["manual_only_price"] or r["loose_price"]
        if not (isinstance(price, int) and price > 0):
            continue
        par = (r["parallel_norm"] or "")
        pname = (r["product_name"] or "")
        # Exclude 1/1-tier (Superfractor / 1-of-1) unless the listing itself is ultra.
        if _SUPER_RE.search(par + " " + pname) and not ultra:
            continue
        if is_auto and not _AUTO_RE.search(par + " " + pname):
            continue
        cands.append((price, r))
    if not cands:
        return {}
    prices = sorted(p for p, _ in cands)
    n = len(prices)
    if ultra:
        top = sorted((p for p, _ in cands), reverse=True)[: max(3, n // 4)]
        center = sorted(top)[len(top) // 2]
    else:
        # IQR-trim so a lone high/low parallel doesn't skew the estimate.
        lo, hi = n // 4, max(n // 4 + 1, (3 * n) // 4)
        trimmed = prices[lo:hi] or prices
        center = trimmed[len(trimmed) // 2]
    # Show the comps CLOSEST to the estimate first (most representative).
    cands.sort(key=lambda t: abs(t[0] - center))
    shown = cands[:6]
    shown_prices = [p for p, _ in shown]
    comps = [{
        "title": r["product_name"], "set": r["console_name"],
        "price": round(p / 100.0, 2), "sale_type": "comparable parallel",
        "used": (idx == 0),
    } for idx, (p, r) in enumerate(shown)]
    return {
        "market_value": round(center / 100.0, 2),
        "value_low": round(min(shown_prices) / 100.0, 2),
        "value_high": round(max(shown_prices) / 100.0, 2),
        "comps": comps, "n_comparables": len(cands),
    }


def value_with_comps(title: str, *, min_score: float = 0.45, proxy: bool = True) -> Dict[str, Any]:
    """Tiered value + comps breakdown. Exact card+grade first; then nearest grade
    of the SAME card; then same-player, SAME-BRAND comparable parallels (estimate)."""
    base = lookup(title, min_score=min_score)
    grade_key = base.get("grade_key", "RAW")
    grade_col = GRADE_COLUMN.get(grade_key, "loose_price")
    if not DB_PATH.exists():
        return {**base, "valuation_tier": "store_not_built", "comps": []}
    con = _conn(); cur = con.cursor()
    try:
        scp_id = base.get("scp_id")
        row = cur.execute("SELECT * FROM products WHERE scp_id=?", (scp_id,)).fetchone() if scp_id else None

        if row is not None:
            ladder = _grade_ladder(row)
            headline_col = grade_col
            # Order: the grade we used first (checkmark), then nearest by price.
            used_entry = next((e for e in ladder if e["col"] == headline_col and e["price"] > 0), None)
            if base.get("market_value") and used_entry:
                rest = sorted([e for e in ladder if e is not used_entry],
                              key=lambda e: abs(e["price"] - used_entry["price"]))
                ordered = [used_entry] + rest
                comps = [{"title": str(base.get("matched") or ""), "set": str(base.get("matched_set") or ""),
                          "price": e["price"], "grade_label": e["label"],
                          "sale_type": e["label"] + " guide",
                          "used": (e is used_entry)} for e in ordered]
                return {**base, "valuation_tier": "exact_grade", "source": "scp_exact",
                        "comps": comps, "disclaimer": ""}
            if ladder:  # exact card, no value at this grade -> nearest grade of same card
                near = min(ladder, key=lambda e: e["price"])
                rest = sorted([e for e in ladder if e is not near], key=lambda e: e["price"])
                ordered = [near] + rest
                comps = [{"title": str(base.get("matched") or ""), "set": str(base.get("matched_set") or ""),
                          "price": e["price"], "grade_label": e["label"],
                          "sale_type": e["label"] + " guide",
                          "used": (e is near)} for e in ordered]
                return {**base, "market_value": near["price"], "valuation_tier": "same_card_other_grade",
                        "source": "scp_exact_other_grade", "comps": comps,
                        "disclaimer": f"No {grade_key} guide value for this exact card - showing its {near['label']} value."}

        # Tier 3: same-player, same-brand comparable parallels
        if proxy:
            toks = frozenset(_tokens(title))
            pnorm = _detect_player(toks, cur)
            if pnorm:
                is_auto = bool(_AUTO_RE.search(title))
                ultra = bool(re.search(r"/\s*([1-5])\b", title)) or bool(_SUPER_RE.search(title))
                listing_brand = _brand_family(title)
                est = _proxy(cur, pnorm, grade_col, is_auto, ultra, listing_brand)
                if est.get("market_value"):
                    disp = pnorm.title()
                    return {"market_value": est["market_value"], "value_low": est["value_low"],
                            "value_high": est["value_high"], "grade_key": grade_key,
                            "valuation_tier": "player_parallel_estimate", "source": "scp_proxy",
                            "comps": est["comps"], "n_comparables": est["n_comparables"], "matched": None,
                            "disclaimer": f"No exact comp for this card. Estimated from {est['n_comparables']} comparable {disp} parallels (same brand)."}
        return {**base, "valuation_tier": "none", "comps": []}
    finally:
        con.close()
