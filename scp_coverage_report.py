"""
scp_coverage_report.py — which of your feed's cards price, and which sets are missing.

Runs your live pools (auctions + BIN) through the SportsCardsPro store and tells
you exactly which set+year CSVs to download to cover the gaps.

    python scp_coverage_report.py
"""
import json, re, os
from collections import Counter
from pathlib import Path
import scp_price_store as scp

HERE = Path(__file__).parent
POOLS = [
    Path(os.environ.get("SNIPEWINS_POOL_PATH") or str(HERE / "daily_pool.json")),
    Path(os.environ.get("SNIPEWINS_BIN_POOL_PATH") or str(HERE / "bin_pool.json")),
]
REPORT = HERE / "scp_coverage_report.txt"

SPORT_PREFIX = {"MLB": "baseball-cards", "NBA": "basketball-cards", "NFL": "football-cards",
                "BASEBALL": "baseball-cards", "BASKETBALL": "basketball-cards", "FOOTBALL": "football-cards"}

# title keyword -> (canonical set, slug fragment). Order matters (specific first).
SET_SIGS = [
    (r"topps chrome black", "Topps Chrome Black", "topps-chrome-black"),
    (r"topps chrome update|chrome update", "Topps Chrome Update", "topps-chrome-update"),
    (r"cosmic chrome", "Topps Cosmic Chrome", "topps-cosmic-chrome"),
    (r"stadium club", "Topps Stadium Club", "topps-stadium-club"),
    (r"gilded", "Topps Gilded", "topps-gilded"),
    (r"topps finest|\bfinest\b", "Topps Finest", "topps-finest"),
    (r"bowman chrome sapphire|bowman sapphire", "Bowman Chrome Sapphire", "bowman-chrome-sapphire"),
    (r"bowman draft", "Bowman Draft Chrome", "bowman-draft-chrome"),
    (r"bowman chrome", "Bowman Chrome", "bowman-chrome"),
    (r"\bbowman\b", "Bowman", "bowman"),
    (r"topps chrome", "Topps Chrome", "topps-chrome"),
    (r"\btopps\b", "Topps (flagship)", "topps"),
    (r"donruss optic|\boptic\b", "Panini Donruss Optic", "panini-donruss-optic"),
    (r"national treasures", "Panini National Treasures", "panini-national-treasures"),
    (r"\bselect\b", "Panini Select", "panini-select"),
    (r"\bmosaic\b", "Panini Mosaic", "panini-mosaic"),
    (r"\bspectra\b", "Panini Spectra", "panini-spectra"),
    (r"\bobsidian\b", "Panini Obsidian", "panini-obsidian"),
    (r"\bphoenix\b", "Panini Phoenix", "panini-phoenix"),
    (r"\bprizm\b", "Panini Prizm", "panini-prizm"),
    (r"\bdonruss\b", "Panini Donruss", "panini-donruss"),
]
YEAR = re.compile(r"\b(20[12]\d)\b")


def detect_set(title):
    t = title.lower()
    for pat, name, slug in SET_SIGS:
        if re.search(pat, t):
            return name, slug
    return "UNKNOWN", "unknown"


def load_items(p):
    try:
        d = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
        return d.get("items", {}) or {}
    except Exception:
        return {}


def main():
    L = []
    def out(s=""):
        print(s); L.append(s)

    st = scp.store_stats()
    out("Store: " + str(st))
    out("")
    priced = no_grade = no_match = 0
    missing = Counter()       # (sport, year, set) -> count of unpriced
    untracked = Counter()
    total = 0
    seen = set()
    for p in POOLS:
        for iid, row in load_items(p).items():
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or "")
            if not title or title in seen:
                continue
            seen.add(title)
            total += 1
            r = scp.lookup(title)
            if r.get("market_value"):
                priced += 1
                continue
            # unpriced — figure out the set + year so we know what to download
            sport = str(row.get("sport") or "").upper()
            ymatch = YEAR.search(title)
            year = ymatch.group(1) if ymatch else "?"
            setname, slug = detect_set(title)
            pref = SPORT_PREFIX.get(sport, "?-cards")
            if r.get("matched"):
                no_grade += 1   # matched but no value at that grade (rare insert / thin data)
            else:
                no_match += 1
                key = (pref, year, slug, setname, sport)
                missing[key] += 1

    out(f"Unique cards in feed: {total}")
    out(f"  priced:            {priced} ({100*priced//max(1,total)}%)")
    out(f"  matched, no grade$: {no_grade}  (rare inserts / thin graded data — not a missing set)")
    out(f"  NO match:          {no_match}  (likely a missing set CSV)")
    out("")
    out("=== SETS TO DOWNLOAD (ranked by how many of your feed cards they'd cover) ===")
    for (pref, year, slug, setname, sport), n in missing.most_common(40):
        if slug in ("unknown", "topps"):   # flag generic/uncertain separately
            out(f"  [{n:4}] {sport:4} {year} {setname}  (uncertain set — eyeball a few)")
            continue
        if year == "?":
            out(f"  [{n:4}] {sport:4} ????  {setname}  (no year in title)")
            continue
        url = f"https://www.sportscardspro.com/console/{pref}-{year}-{slug}"
        out(f"  [{n:4}] {url}")
    REPORT.write_text("\n".join(L), encoding="utf-8")
    out("")
    out(f"[written to {REPORT.name}]")


if __name__ == "__main__":
    main()
