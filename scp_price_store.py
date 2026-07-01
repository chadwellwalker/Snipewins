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
              "treasures", "national", "definitive", "sterling",
              # Distinct Topps lines that share "chrome" with the flagship — a
              # "Chrome Platinum"/"Chrome Update"/"Cosmic" card must match its OWN
              # set, never base Topps Chrome (these are now loaded).
              "platinum", "update", "cosmic", "pristine"}
# Multi-word SET names whose name contains a color word. When present, that color
# is part of the SET, not the card's parallel.
_SET_COLOR_PHRASES = {"chrome black": "black", "topps black": "black",
                      "chrome platinum": "platinum", "cosmic chrome": "cosmic",
                      "chrome cosmic": "cosmic", "black chrome": "black"}


# Parallel DESIGN/pattern words (not colors, not generic). Two parallels that
# differ on any of these are different cards even at the same #: "Blue Mini-Diamond"
# != "Blue Lava", "Gold Wave" != "Gold Refractor", "Tri-Color" != "Cosmic". Used to
# stop same-#/same-color cross-parallel matches (the Bo Nix $6,200 class).
_PARALLEL_DESIGN_WORDS = {
    "lava", "wave", "raywave", "geometric", "mini", "diamond", "cosmic", "shimmer",
    "vibrations", "etch", "mojo", "nebula", "pulsar", "atomic", "velocity", "fusion",
    "sparkle", "snakeskin", "lazer", "laser", "interstellar", "supernova", "eclipse",
    "toile", "speckle", "logofractor", "crackle", "voltage", "marble", "kaboom",
    "downtown", "equinox", "fluorescent", "padparadscha", "scope", "disco",
    "shock", "dragon", "zebra", "fireworks", "kaleidoscope", "stained", "glass",
    "tie", "dye", "fractal", "vinyl", "lunar", "nova", "stella", "meteoric", "careers",
    "voltaic", "breakaway", "concourse", "premier", "die", "cut", "deca", "honeycomb",
    "tiger", "leopard", "giraffe", "elephant", "butterfly", "flash", "lazer",
}

# Distinct inserts / special editions that share set words ("Topps Chrome",
# "Bowman Chrome") with the base and therefore match the base parallel on
# set-overlap alone, inventing a value. A listing naming one of these is a
# DIFFERENT card from the base — hard-skip any product that doesn't itself name
# the insert, so the card falls to a labeled proxy / NO COMPS instead of a false
# scp_exact (the $15K "All Etch -> base Orange #1" and "It Came to the League
# #CFL-9 -> base #BDC-118" class). Only genuinely distinct inserts go here, never
# ordinary parallels (x-fractor/refractor stay matchable).
_INSERT_PHRASES = {
    # Stems chosen so punctuation-insensitive matching catches variants:
    # "night terror" hits Terror/Terrors; "anniversary" hits 25th/30th/35th;
    # "all etch" hits "All-Etch". Never list an ordinary parallel here, and
    # never a phrase that collides with an NBA chase (no "ultra violet"/"glass").
    "all etch", "ben baller", "it came to the league", "night terror",
    "anniversary", "stained glass", "color blast", "power players",
    "shadow etch", "transformative", "double headers", "gladiators",
    "stars of mlb", "planetary pursuit", "extraterrestrial",
    "astrologically aligned", "fortune 15", "iconic",
}

def _insert_norm(_text: str) -> str:
    """Punctuation-insensitive, space-padded form for insert-phrase matching so
    'All-Etch', 'Night Terror', 'CAE25 All Etch' all match their stems."""
    _t = re.sub(r"[^a-z0-9]+", " ", str(_text or "").lower())
    return " " + " ".join(_t.split()) + " "

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = s.encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9#/\- ]", " ", s)
    return " ".join(s.split())


def _tokens(s: str) -> List[str]:
    # Split on # / and - so glued junk in real eBay titles ("-Caleb", "Mini-Diamond",
    # "BDC-14") doesn't hide the player/parallel. Card numbers use a separate field.
    raw = _norm(s).replace("#", " ").replace("/", " ").replace("-", " ")
    return [t for t in raw.split() if t]


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
    skipped_files = []
    for fp in files:
        try:
            # Read bytes, STRIP NUL bytes (a single corrupt download with a stray
            # \x00 used to crash csv with "line contains NUL" and kill the WHOLE
            # rebuild — leaving the store empty on Render's boot rebuild). Per-file
            # try/except so one bad CSV can never take down the rest.
            import io as _io
            _raw = open(fp, "rb").read().replace(b"\x00", b"")
            _text = _raw.decode("utf-8", errors="ignore")
            _file_rows = 0
            for r in csv.DictReader(_io.StringIO(_text)):
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
                _file_rows += 1
        except Exception as _ferr:
            skipped_files.append(fp.name)
            print(f"[scp_price_store] skipped {fp.name}: {type(_ferr).__name__}: {str(_ferr)[:120]}", flush=True)
            continue
    cur.execute("CREATE INDEX idx_player ON products(player_norm)")
    cur.execute("CREATE INDEX idx_year ON products(year)")
    con.commit()
    players = cur.execute(
        "SELECT COUNT(DISTINCT player_norm) FROM products WHERE player_norm != ''"
    ).fetchone()[0]
    con.close()
    return {"files": [f.name for f in files], "rows": n, "distinct_players": players,
            "skipped_files": skipped_files, "db": str(DB_PATH)}


# Team / checklist "players" — SCP stores team cards with the team as the
# product name, which the matcher can mistake for a player. Exclude them.
_TEAM_NAMES = set()
for _city, _nick in [
    ("new york","yankees"),("new york","mets"),("los angeles","dodgers"),("los angeles","angels"),
    ("boston","red sox"),("chicago","cubs"),("chicago","white sox"),("houston","astros"),
    ("atlanta","braves"),("philadelphia","phillies"),("san francisco","giants"),("san diego","padres"),
    ("seattle","mariners"),("toronto","blue jays"),("baltimore","orioles"),("tampa bay","rays"),
    ("minnesota","twins"),("cleveland","guardians"),("detroit","tigers"),("kansas city","royals"),
    ("milwaukee","brewers"),("cincinnati","reds"),("pittsburgh","pirates"),("st louis","cardinals"),
    ("washington","nationals"),("miami","marlins"),("colorado","rockies"),("arizona","diamondbacks"),
    ("texas","rangers"),("oakland","athletics"),
    ("kansas city","chiefs"),("buffalo","bills"),("cincinnati","bengals"),("baltimore","ravens"),
    ("dallas","cowboys"),("philadelphia","eagles"),("san francisco","49ers"),("detroit","lions"),
    ("green bay","packers"),("miami","dolphins"),("new york","jets"),("new york","giants"),
    ("las vegas","raiders"),("denver","broncos"),("los angeles","chargers"),("los angeles","rams"),
    ("minnesota","vikings"),("chicago","bears"),("atlanta","falcons"),("carolina","panthers"),
    ("new orleans","saints"),("tampa bay","buccaneers"),("seattle","seahawks"),("arizona","cardinals"),
    ("houston","texans"),("indianapolis","colts"),("jacksonville","jaguars"),("tennessee","titans"),
    ("cleveland","browns"),("pittsburgh","steelers"),("new england","patriots"),("washington","commanders"),
    ("boston","celtics"),("golden state","warriors"),("los angeles","lakers"),("milwaukee","bucks"),
    ("denver","nuggets"),("oklahoma city","thunder"),("dallas","mavericks"),("phoenix","suns"),
    ("new york","knicks"),("philadelphia","76ers"),("miami","heat"),("cleveland","cavaliers"),
    ("memphis","grizzlies"),("minnesota","timberwolves"),("new orleans","pelicans"),("sacramento","kings"),
    ("san antonio","spurs"),("orlando","magic"),("indiana","pacers"),("atlanta","hawks"),
    ("chicago","bulls"),("toronto","raptors"),("brooklyn","nets"),("houston","rockets"),
    ("detroit","pistons"),("charlotte","hornets"),("portland","trail blazers"),("utah","jazz"),
    ("washington","wizards"),
]:
    _TEAM_NAMES.add(_norm(_city + " " + _nick))
    _TEAM_NAMES.add(_norm(_nick))


_PLAYER_CACHE: Optional[List[Tuple[str, frozenset]]] = None


def _load_players(cur) -> List[Tuple[str, frozenset]]:
    global _PLAYER_CACHE
    if _PLAYER_CACHE is None:
        rows = cur.execute(
            "SELECT DISTINCT player_norm FROM products WHERE player_norm!=''"
        ).fetchall()
        _PLAYER_CACHE = [(r[0], frozenset(r[0].split())) for r in rows
                         if r[0] and r[0] not in _TEAM_NAMES]
    return _PLAYER_CACHE


def _detect_player(title_tokens: frozenset, cur, title_norm: str = "") -> Optional[str]:
    # Rank candidate players by (token-count, contiguity). Token-count keeps full
    # names winning over short coincidences. Contiguity breaks ties: the real
    # player's words appear as a contiguous phrase in the title, while a false
    # 2-token match assembled from scattered words (e.g. "Anthony Edwards Prizm
    # BLACK" spuriously matching player "Anthony Black") does not.
    best, best_key = None, (0, 0)
    for pname, pset in _load_players(cur):
        if pset and pset <= title_tokens:
            contig = 1 if (title_norm and pname in title_norm) else 0
            key = (len(pset), contig)
            if key > best_key:
                best, best_key = pname, key
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

        player = _detect_player(toks, cur, _norm(title))
        if not player:
            return {"market_value": None, "matched": None, "reason": "no_player_match",
                    "grade_key": grade_key, "score": 0.0, "sales_volume": 0}

        rows = cur.execute("SELECT * FROM products WHERE player_norm=?", (player,)).fetchall()
        leftover = toks - set(player.split())
        listing_is_auto = bool(_AUTO_RE.search(title))
        listing_is_relic = bool(_RELIC_RE.search(title))
        listing_is_multi = bool(_MULTI_RE.search(title))
        # Color words that are part of a SET name ("Topps Chrome Black", "Chrome
        # Platinum", "Cosmic Chrome") are not parallels — strip them from parallel
        # matching so they don't false-match a "[Black Border]" parallel.
        _nt = _norm(title)
        _rawtoks = _tokens(title)
        for _ph, _w in _SET_COLOR_PHRASES.items():
            # Only strip when the color word appears once (pure set name). If it
            # appears twice it's also the parallel ("Chrome Black ... Black Refractor")
            # and must be kept so the [Black] parallel can match.
            if _ph in _nt and _rawtoks.count(_w) <= 1:
                leftover = leftover - {_w}
        listing_colors = leftover & set(_COLOR_TIER.keys())
        _nt_ins = _insert_norm(title)
        _listing_inserts = {_ph for _ph in _INSERT_PHRASES if (" "+_ph+" ") in _nt_ins}
        best, best_score = None, 0.0
        for row in rows:
            cset = set((row["console_norm"] or "").split()) - _SET_STOP
            if row["year"]:
                cset.discard(row["year"])
            set_overlap = len(cset & toks)
            if cset and set_overlap == 0:
                continue                              # different set entirely — skip
            # Bowman and Topps (flagship/Chrome) are different product lines that
            # share the word "chrome". A "Bowman Chrome" listing must not match a
            # "Topps Chrome" product (or vice versa) — that's how a $61 Bowman
            # insert got valued off a $406 Topps Chrome parallel.
            if ("bowman" in toks) != ("bowman" in (row["console_norm"] or "")):
                continue
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
            par = set(_tokens(row["parallel_norm"] or ""))
            if par:
                # Brand/set words ("topps", "bowman", "panini") appear in every
                # listing and must NOT count as a parallel match — otherwise a base
                # "[Topps Logo]" parallel spuriously matches any Topps card.
                _par_left = leftover - {"topps", "bowman", "panini"}
                inter = len(par & _par_left)
                score += 0.6 * (inter / len(par))
                score += 0.05 * inter
            else:
                score += 0.15
            # Auto must match auto: an autograph card is a different (pricier)
            # product than the base parallel. Don't let "Auto /499" match base "#88".
            _prod_type_text = (row["parallel_norm"] or "") + " " + (row["product_name"] or "")
            prod_is_auto = bool(_AUTO_RE.search(_prod_type_text))
            if listing_is_auto != prod_is_auto:
                continue
            # Relic/patch and multi-player are different cards — a patch RPA must not
            # match a plain auto, a dual must not match a solo (the $13-comp-on-a-/10
            # class). Require the product's card type to match the listing's.
            if listing_is_relic != bool(_RELIC_RE.search(_prod_type_text)):
                continue
            if listing_is_multi != bool(_MULTI_RE.search(_prod_type_text)):
                continue
            # Wrong parallel color: if the listing names a color the product lacks
            # ("Blue Refractor" vs base "[Black Border]"), demote it.
            _missing = listing_colors - par
            if _missing:
                score -= 0.3 * len(_missing)
            # Symmetric guard: penalize when the PRODUCT names a rarity color the
            # listing does NOT — a base "#1" must not match a rarer "[Blue Refractor]
            # #1" (that's the $15K Ohtani inflation), and a "Green Refractor" must
            # not match a "[Blue Refractor]" of the same number.
            _extra = (par & set(_COLOR_TIER)) - listing_colors
            if _extra:
                score -= 0.4 * len(_extra)
            # Prefer the PLAINEST product when the listing doesn't name the parallel.
            # The base "#1" listing ties with both "[Batting]" and "[Batting Refractor]"
            # of the same number; without this it grabbed the $29K refractor. Penalize
            # every extra parallel word the product carries that the listing doesn't,
            # so the cheaper base ("[Batting]") wins.
            _extra_par_tokens = par - leftover
            if _extra_par_tokens:
                score -= 0.18 * len(_extra_par_tokens)
            # Parallel-NAME discipline: the specific design/pattern must match, not
            # just the color. Penalize design words on one side but not the other so
            # "Gold Wave" can't take "[Gold Refractor]" and "Tri-Color" can't take
            # "[Cosmic]". Strong enough to drop a wrong-parallel match to proxy.
            _design_diff = (leftover & _PARALLEL_DESIGN_WORDS) ^ (par & _PARALLEL_DESIGN_WORDS)
            if _design_diff:
                score -= 0.45 * len(_design_diff)
            # Insert/edition discipline: if the listing names a distinct insert the
            # product doesn't carry, it's a different card — never an exact match.
            if _listing_inserts:
                _prod_blob = _insert_norm(
                    (row["console_norm"] or "") + " "
                    + (row["product_name"] or "") + " "
                    + (row["parallel_norm"] or "")
                )
                if any((" "+_ph+" ") not in _prod_blob for _ph in _listing_inserts):
                    continue
            if year and row["year"] and row["year"] != year:
                continue                              # different year — never cross-year match
            if year and row["year"] == year:
                score += 0.2
            # Card-number discipline: if the listing names a card number and this
            # product has a DIFFERENT one, it's a different card — never an exact
            # match (this is what let "Meteoric Rise #MR-12" match base "#17" and
            # flash a $943 STRIKE). Skip it; the card falls to a labeled proxy.
            # Compare card numbers with dashes/spaces stripped so "USC-200" ==
            # "USC200" and "BDC-118" == "BDC118" (SCP and eBay format them differently).
            _rn = _norm(row["card_number"] or "").replace("-", "").replace(" ", "")
            _ln = listing_num.replace("-", "").replace(" ", "")
            if _ln and _rn:
                if _ln == _rn:
                    score += 0.30
                else:
                    continue
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


def loaded_src_file_count() -> int:
    """How many distinct CSV files are represented in the built store. Lets the
    supervisor detect that new price lists were added (csv count > loaded count)
    and trigger a rebuild — otherwise newly-downloaded sets never load."""
    if not DB_PATH.exists():
        return 0
    try:
        con = _conn()
        n = con.execute("SELECT COUNT(DISTINCT src_file) FROM products").fetchone()[0]
        con.close()
        return int(n or 0)
    except Exception:
        return 0


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
# Cross-comp groups — which products are comparable. A high-end patch/RPA card
# (National Treasures/Immaculate/Flawless) must NOT proxy against a mid-tier set
# (Phoenix/Spectra), Chrome stays with Chrome, Prizm-family with Prizm-family.
# First matching substring wins, so order matters (most specific first).
_PRODUCT_GROUP_MAP = [
    ("national treasures", "highend"), ("immaculate", "highend"), ("flawless", "highend"),
    ("definitive", "highend"), ("dynasty", "highend"), ("sterling", "highend"),
    ("museum", "highend"), ("transcendent", "highend"), ("five star", "highend"),
    ("panini one", "highend"), ("noir", "highend"), ("opulence", "highend"),
    ("optic", "prizm"), ("prizm", "prizm"), ("select", "prizm"), ("mosaic", "prizm"),
    ("finest", "chrome"), ("sapphire", "chrome"), ("chrome", "chrome"), ("bowman", "chrome"),
    ("phoenix", "midpanini"), ("spectra", "midpanini"), ("certified", "midpanini"),
    ("zenith", "midpanini"), ("absolute", "midpanini"), ("illusions", "midpanini"),
    ("luminance", "midpanini"), ("origins", "midpanini"), ("obsidian", "midpanini"),
    ("contenders", "contenders"), ("score", "score"),
]
def _product_group(text: str) -> str:
    t = (text or "").lower()
    for _sub, _grp in _PRODUCT_GROUP_MAP:
        if _sub in t:
            return _grp
    return ""
# Relic/patch/memorabilia signal — these are physically different (and usually far
# pricier) cards than a plain parallel; must not match a non-relic product.
_RELIC_RE = re.compile(r"\b(patch\w*|jersey|relic|memorabilia|swatch|laundry|button|rpa|materials?|game[ -]?used|dual\s+patch|combo\s+patch)\b", re.IGNORECASE)
# Multi-player signal (dual/combo/booklet) — a different card than a solo.
_MULTI_RE = re.compile(r"\b(dual|triple|quad|combo|synced|duos?|tandem|booklet)\b", re.IGNORECASE)
_PANINI_HINTS = ("panini", "prizm", "select", "optic", "mosaic", "donruss", "contenders",
                 "certified", "absolute", "obsidian", "illusions", "spectra", "phoenix",
                 "immaculate", "flawless", "national treasures", "chronicles", "zenith",
                 "revolution", "score", "luminance", "xr", "playbook", "origins")
_SUPER_RE = re.compile(r"superfractor|1\s*of\s*1|\b1/1\b", re.IGNORECASE)
# Coarse rarity tier (0 = rarest). Serial number wins; else infer from the
# parallel color. Used so a Black /10 comps against Black/Orange-tier parallels,
# not Green /99.
_COLOR_TIER = {
    "superfractor": 0, "black": 0,
    "red": 1, "gold": 1,
    "orange": 2, "purple": 2, "pink": 2, "magenta": 2, "fuchsia": 2, "rose": 1,
    "green": 3, "blue": 3, "aqua": 3, "teal": 3,
    "silver": 4, "bronze": 4, "yellow": 4, "white": 4,
}
_SERIAL_RE_T = re.compile(r"/\s*(\d{1,4})\b")


def _tier_of(text: str) -> Optional[int]:
    t = (text or "").lower()
    m = _SERIAL_RE_T.search(t)
    if m:
        n = int(m.group(1))
        if n <= 5: return 0
        if n <= 10: return 1
        if n <= 25: return 2
        if n <= 99: return 3
        return 4
    for c, tier in _COLOR_TIER.items():
        if c in t:
            return tier
    return None


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


def _proxy(cur, player: str, grade_col: str, is_auto: bool, ultra: bool,
           listing_brand: str, listing_tier: Optional[int] = None,
           listing_year: str = "", listing_bowman: bool = False,
           is_relic: bool = False, is_multi: bool = False,
           listing_group: str = "") -> Dict[str, Any]:
    rows = cur.execute("SELECT * FROM products WHERE player_norm=?", (player,)).fetchall()
    cands = []  # (price, row, cand_tier)
    for r in rows:
        rb = _brand_family(r["console_name"])
        if listing_brand and rb and rb != listing_brand:
            continue
        # Cross-comp group gate: don't proxy across product tiers (a $XX Phoenix
        # parallel must not stand in for a National Treasures /99 patch).
        if listing_group and _product_group(r["console_name"]) != listing_group:
            continue
        # Bowman and Topps share the "topps" family bucket but are different
        # product lines — don't proxy a Topps card off Bowman parallels.
        if listing_bowman != ("bowman" in (r["console_name"] or "").lower()):
            continue
        price = r[grade_col] if (isinstance(r[grade_col], int) and r[grade_col] > 0) else None
        if price is None:
            price = r["manual_only_price"] or r["loose_price"]
        if not (isinstance(price, int) and price > 0):
            continue
        par = (r["parallel_norm"] or "")
        pname = (r["product_name"] or "")
        if _SUPER_RE.search(par + " " + pname) and not ultra:
            continue
        if is_auto and not _AUTO_RE.search(par + " " + pname):
            continue
        if is_relic and not _RELIC_RE.search(par + " " + pname):
            continue
        if is_multi and not _MULTI_RE.search(par + " " + pname):
            continue
        cands.append((price, r, _tier_of(pname)))
    if not cands:
        return {}
    # Rarity-tier match: keep parallels within +-1 tier of the listing (a /10
    # comps against /5-/25-tier, not /99). Fall back to all if too few.
    if listing_tier is not None:
        near = [c for c in cands if c[2] is not None and abs(c[2] - listing_tier) <= 1]
        if len(near) >= 2:
            cands = near
    # Year guard: prefer same-year comps; otherwise allow within 1 year; beyond
    # that, refuse (a 2013 card must not be valued off 2025 parallels — this also
    # blocks same-name different-era players, e.g. Cam Ward hockey vs football).
    if listing_year and listing_year.isdigit():
        _ly = int(listing_year)
        sy = [c for c in cands if (c[1]["year"] or "") == listing_year]
        near = [c for c in cands if c[1]["year"] and abs(int(c[1]["year"]) - _ly) <= 1]
        if sy:
            cands = sy
        elif near:
            cands = near
        else:
            return {}
    prices = sorted(p for p, _, _ in cands)
    n = len(prices)
    if ultra:
        top = sorted((p for p, _, _ in cands), reverse=True)[: max(3, n // 4)]
        center = sorted(top)[len(top) // 2]
    else:
        lo, hi = n // 4, max(n // 4 + 1, (3 * n) // 4)
        trimmed = prices[lo:hi] or prices
        center = trimmed[len(trimmed) // 2]
    # Order by tier-closeness first, then price-closeness to the estimate.
    def _key(c):
        ct = c[2]
        td = abs(ct - listing_tier) if (ct is not None and listing_tier is not None) else 2
        return (td, abs(c[0] - center))
    cands.sort(key=_key)
    shown = cands[:6]
    shown_prices = [p for p, _, _ in shown]
    comps = [{
        "title": r["product_name"], "set": r["console_name"],
        "price": round(p / 100.0, 2), "sale_type": "comparable parallel",
        "used": (idx == 0),
    } for idx, (p, r, _ct) in enumerate(shown)]
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

        # Rarity guard: a serial /1-/25 card must NOT take a base-parallel exact
        # match that lacks its rarity color (e.g. "Black Refractor /10" matching
        # a plain "[Refractor]"). SCP rarely has the serialed variant, so the base
        # value is wrong — route to the tier-matched proxy instead.
        _ser = re.search(r"/\s*(\d{1,4})", title)
        _low_serial = bool(_ser and int(_ser.group(1)) <= 25)
        _listing_colors = set(_tokens(title)) & set(_COLOR_TIER.keys())
        _matched_par = set(_tokens(row["parallel_norm"] or "")) if row is not None else set()
        # Fire when the listing names a rarity color the matched product lacks
        # ("Rose Gold" vs base "[Gold]" -> missing {rose} -> reject exact, use proxy).
        _rarity_mismatch = bool(_low_serial and (_listing_colors - _matched_par))

        if row is not None and not _rarity_mismatch:
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
            pnorm = _detect_player(toks, cur, _norm(title))
            if pnorm:
                is_auto = bool(_AUTO_RE.search(title))
                ultra = bool(re.search(r"/\s*([1-5])\b", title)) or bool(_SUPER_RE.search(title))
                listing_brand = _brand_family(title)
                listing_tier = _tier_of(title)
                _ly = (_YEAR_RE.search(title).group(1) if _YEAR_RE.search(title) else "")
                _lb = "bowman" in _norm(title)
                est = _proxy(cur, pnorm, grade_col, is_auto, ultra, listing_brand, listing_tier, _ly, _lb,
                             is_relic=bool(_RELIC_RE.search(title)), is_multi=bool(_MULTI_RE.search(title)),
                             listing_group=_product_group(title))
                if est.get("market_value"):
                    disp = pnorm.title()
                    return {"market_value": est["market_value"], "value_low": est["value_low"],
                            "value_high": est["value_high"], "grade_key": grade_key,
                            "valuation_tier": "player_parallel_estimate", "source": "scp_proxy",
                            "comps": est["comps"], "n_comparables": est["n_comparables"], "matched": None,
                            "disclaimer": f"No exact comp for this card. Estimated from {est['n_comparables']} comparable {disp} parallels (same brand)."}
        # If we deliberately rejected the exact match (rarity mismatch) and the
        # proxy produced nothing, don't surface the rejected base price — a wrong
        # cheap value is worse than NO COMPS. Drop it.
        if _rarity_mismatch:
            return {**base, "market_value": None, "matched": None, "source": None,
                    "valuation_tier": "rarity_no_comp", "comps": []}
        return {**base, "valuation_tier": "none", "comps": []}
    finally:
        con.close()
