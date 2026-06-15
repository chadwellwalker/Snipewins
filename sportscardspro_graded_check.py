"""
sportscardspro_graded_check.py — does this token return GRADED prices at all?

Run from the `Python Coding` folder:
    python sportscardspro_graded_check.py

It looks up a "control group" of mainstream, high-liquidity cards that
definitely have tons of PSA 10 / graded sales. If GRADED/PSA10 columns come
back populated for these, then your plan HAS graded data and the blanks on
your niche parallels are just thin sales depth. If even these come back blank,
your subscription tier doesn't include graded prices (an upgrade/billing fix).

Writes graded_check_report.txt for Claude to read. Read-only.
"""
from __future__ import annotations
import json, sys, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path

HERE = Path(__file__).parent
ENV = HERE / ".env"
REPORT = HERE / "graded_check_report.txt"
BASE = "https://www.sportscardspro.com/api/product"
_HEADERS = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
            "Accept": "application/json, text/plain, */*"}

CONTROL = [
    "Michael Jordan 1986 Fleer #57",
    "2018 Topps Chrome Shohei Ohtani #150",
    "2017 Topps Update Aaron Judge #US300",
    "2023 Topps Chrome Corbin Carroll #220",
    "2003 Topps Chrome LeBron James #111",
    "2024 Topps Chrome Paul Skenes #168",
    "2021 Bowman Chrome Wander Franco",
    "2020 Topps Chrome Luis Robert",
]

def load_token():
    for line in ENV.read_text(encoding='utf-8', errors='ignore').splitlines():
        for name in ('SPORTSCARDSPRO_API_KEY=', 'SPORTSCARDSPRO_API_TOKEN=', 'PRICECHARTING_API_TOKEN='):
            if line.strip().startswith(name):
                return line.split('=', 1)[1].strip()
    sys.exit("No SPORTSCARDSPRO_API_KEY in .env")

def api(tok, q):
    url = BASE + "?" + urllib.parse.urlencode({'t': tok, 'q': q})
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {'status': 'error', 'error-message': f"HTTP {e.code}"}
    except Exception as e:
        return {'status': 'error', 'error-message': str(e)[:120]}

def d(v): return f"${v/100:,.0f}" if isinstance(v, int) and v > 0 else "-"

def main():
    tok = load_token()
    L = []
    def out(s=""):
        print(s); L.append(s)
    out("GRADED-DATA CONTROL CHECK (mainstream liquid cards)\n")
    graded_any = 0
    for q in CONTROL:
        res = api(tok, q)
        if res.get('status') == 'success' and res.get('id'):
            g9, g8, p10, raw = (res.get('graded-price'), res.get('new-price'),
                                res.get('manual-only-price'), res.get('loose-price'))
            if any(isinstance(x, int) and x > 0 for x in (g9, g8, p10)):
                graded_any += 1
            out(f"{q}")
            out(f"   -> {res.get('console-name','')} | {res.get('product-name','')}")
            out(f"   RAW {d(raw)}  GR9 {d(g9)}  GR8 {d(g8)}  PSA10 {d(p10)}")
        else:
            out(f"{q}  -> MISS ({res.get('error-message','')})")
        out("")
        time.sleep(1.1)
    out(f"=== {graded_any}/{len(CONTROL)} mainstream cards returned a GRADED price ===")
    if graded_any == 0:
        out("VERDICT: token returns NO graded data -> plan/tier issue (fixable via SportsCardsPro).")
    else:
        out("VERDICT: plan HAS graded data -> blanks on your parallels are thin-sales depth, not access.")
    REPORT.write_text("\n".join(L), encoding='utf-8')
    out(f"\n[written to {REPORT.name}]")

if __name__ == "__main__":
    main()
