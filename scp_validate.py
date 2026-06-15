"""
scp_validate.py — measure matcher coverage against your real daily_pool.json.

Run AFTER `python scp_sync.py`:
    python scp_validate.py

Reports, over the cards your scanner actually pulled: how many matched a product,
how many got a price at the listing's grade, and a per-card sample. Writes
scp_validate_report.txt for review.
"""
import json, os
from pathlib import Path
import scp_price_store as s

HERE = Path(__file__).parent
POOL = HERE / "daily_pool.json"
REPORT = HERE / "scp_validate_report.txt"

def titles():
    d = json.loads(POOL.read_text(encoding="utf-8", errors="ignore"))
    out = []
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k.lower() in ("title", "itemtitle", "name") and isinstance(v, str):
                    out.append(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(d)
    seen, u = set(), []
    for t in out:
        if t not in seen:
            seen.add(t); u.append(t)
    return u

def main():
    L = []
    def w(x=""):
        print(x); L.append(x)
    st = s.store_stats()
    w("Store: " + str(st))
    if not st.get("built"):
        w("Store not built — run: python scp_sync.py")
        REPORT.write_text("\n".join(L), encoding="utf-8"); return
    ts = titles()
    matched = priced = 0
    rows = []
    for t in ts:
        r = s.lookup(t)
        if r.get("matched"):
            matched += 1
        if r.get("market_value"):
            priced += 1
        mv = ("$%.2f" % r["market_value"]) if r.get("market_value") else "-"
        rows.append((t[:50], r.get("grade_key", ""), mv, r.get("score", 0), str(r.get("matched") or r.get("reason"))[:34]))
    n = len(ts) or 1
    w("")
    w("Cards in pool: %d | matched a product: %d (%d%%) | priced at grade: %d (%d%%)"
      % (len(ts), matched, 100 * matched // n, priced, 100 * priced // n))
    w("")
    w("%-50s %-6s %-9s %-5s %s" % ("LISTING", "GRADE", "VALUE", "SCORE", "MATCH/REASON"))
    w("-" * 120)
    for t, g, mv, sc, m in rows:
        w("%-50s %-6s %-9s %-5s %s" % (t, g, mv, sc, m))
    REPORT.write_text("\n".join(L), encoding="utf-8")
    w("")
    w("[written to %s]" % REPORT.name)

if __name__ == "__main__":
    main()
