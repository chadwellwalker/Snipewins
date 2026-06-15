"""
sportscardspro_fields_check.py — definitive grade-field + tier test.

Run from the `Python Coding` folder:
    python sportscardspro_fields_check.py

Pulls EVERY documented price field (ungraded + all graded tiers) for a few of
your cards, then compares YOUR token vs the public DEMO token on the same
Jordan card. If demo shows graded numbers and yours shows blanks, your plan
doesn't include graded data. Writes fields_check_report.txt. Read-only.
"""
from __future__ import annotations
import json, sys, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path

HERE = Path(__file__).parent
ENV = HERE / ".env"
REPORT = HERE / "fields_check_report.txt"
BASE = "https://www.sportscardspro.com/api/product"
DEMO = "c0b53bce27c1bdab90b1605249e600dc43dfd1d5"
_H = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
      "Accept": "application/json, text/plain, */*"}

# every documented price field -> human label
FIELDS = [
    ("loose-price", "Ungraded"),
    ("cib-price", "Grade7"),
    ("new-price", "Grade8"),
    ("graded-price", "Grade9"),
    ("box-only-price", "BGS9.5"),
    ("manual-only-price", "PSA10"),
    ("bgs-10-price", "BGS10"),
    ("condition-17-price", "CGC10"),
    ("condition-18-price", "SGC10"),
]

CARDS = [
    "Michael Jordan 1986 Fleer #57",
    "2018 Topps Chrome Shohei Ohtani #150",
    "2024 Topps Chrome Black Elly De La Cruz Orange Refractor Autograph",
    "2024 Bowman Chrome Paul Skenes Fuchsia Refractor #31",
]

def load_token():
    for line in ENV.read_text(encoding='utf-8', errors='ignore').splitlines():
        for name in ('SPORTSCARDSPRO_API_KEY=', 'SPORTSCARDSPRO_API_TOKEN=', 'PRICECHARTING_API_TOKEN='):
            if line.strip().startswith(name):
                return line.split('=', 1)[1].strip()
    sys.exit("No SPORTSCARDSPRO_API_KEY in .env")

def api(tok, q):
    url = BASE + "?" + urllib.parse.urlencode({'t': tok, 'q': q})
    req = urllib.request.Request(url, headers=_H)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {'status': 'error', 'error-message': f"HTTP {e.code}"}
    except Exception as e:
        return {'status': 'error', 'error-message': str(e)[:120]}

def money(v): return f"${v/100:,.0f}" if isinstance(v, int) and v > 0 else "-"

def show(out, label, res):
    if res.get('status') != 'success' or not res.get('id'):
        out(f"  {label}: MISS ({res.get('error-message','')})"); return
    out(f"  {label}: {res.get('console-name','')} | {res.get('product-name','')}")
    cells = [f"{lbl}={money(res.get(f))}" for f, lbl in FIELDS]
    out("    " + "  ".join(cells))

def main():
    tok = load_token()
    L = []
    def out(s=""):
        print(s); L.append(s)

    out("FIELDS + TIER CHECK\n")
    for c in CARDS:
        out(c)
        show(out, "YOUR token", api(tok, c))
        out("")
        time.sleep(1.1)

    out("=== HEAD-TO-HEAD: same Jordan card, your token vs demo token ===")
    j = "Michael Jordan 1986 Fleer #57"
    show(out, "YOUR token", api(tok, j)); time.sleep(1.1)
    show(out, "DEMO token", api(DEMO, j))
    out("")
    out("If DEMO shows graded $ and YOURS doesn't -> your plan lacks graded data.")
    REPORT.write_text("\n".join(L), encoding='utf-8')
    out(f"\n[written to {REPORT.name}]")

if __name__ == "__main__":
    main()
