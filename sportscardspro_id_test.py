"""
sportscardspro_id_test.py — does querying by ID return graded prices?

Run from the `Python Coding` folder:
    python sportscardspro_id_test.py

The website shows full graded prices but the text-search API returned only
ungraded. This tests whether querying by product ID (instead of q=text) returns
the graded ladder. If it does, no subscription upgrade is needed.
Writes id_test_report.txt. Read-only.
"""
from __future__ import annotations
import json, sys, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path

HERE = Path(__file__).parent
ENV = HERE / ".env"
REPORT = HERE / "id_test_report.txt"
BASE = "https://www.sportscardspro.com/api/product"
_H = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
      "Accept": "application/json, text/plain, */*"}
FIELDS = [("loose-price","Ungraded"),("cib-price","Gr7"),("new-price","Gr8"),
          ("graded-price","Gr9"),("box-only-price","Gr9.5"),("manual-only-price","PSA10"),
          ("bgs-10-price","BGS10"),("condition-17-price","CGC10"),("condition-18-price","SGC10")]

def load_token():
    for line in ENV.read_text(encoding='utf-8', errors='ignore').splitlines():
        for n in ('SPORTSCARDSPRO_API_KEY=','SPORTSCARDSPRO_API_TOKEN=','PRICECHARTING_API_TOKEN='):
            if line.strip().startswith(n): return line.split('=',1)[1].strip()
    sys.exit("No SPORTSCARDSPRO_API_KEY in .env")

def call(tok, **params):
    params['t'] = tok
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_H)
    try:
        with urllib.request.urlopen(req, timeout=20) as r: return json.loads(r.read().decode())
    except urllib.error.HTTPError as e: return {'status':'error','error-message':f"HTTP {e.code}"}
    except Exception as e: return {'status':'error','error-message':str(e)[:120]}

def money(v): return f"${v/100:,.0f}" if isinstance(v,int) and v>0 else "-"

def show(out, label, res):
    if res.get('status')!='success' or not res.get('id'):
        out(f"  {label}: MISS ({res.get('error-message','')})"); return
    out(f"  {label}: id={res.get('id')} | {res.get('product-name','')}")
    out("    " + "  ".join(f"{lbl}={money(res.get(f))}" for f,lbl in FIELDS))

def main():
    tok = load_token(); L=[]
    def out(s=""): print(s); L.append(s)
    out("ID vs TEXT-SEARCH test (Jordan 1986 Fleer #57, known PriceCharting ID 72584)\n")
    # 1) text search
    out("Method A — text search (q=):")
    show(out, "q", call(tok, q="michael jordan 1986 fleer 57")); time.sleep(1.1)
    out("")
    # 2) id lookup, known id from the website (PriceCharting ID: 72584)
    out("Method B — id lookup (id=72584):")
    show(out, "id", call(tok, id="72584")); time.sleep(1.1)
    out("")
    out("If Method B shows Gr9/PSA10 $ and Method A doesn't -> we just query by id. No upgrade needed.")
    out("If BOTH show only Ungraded -> graded is an account entitlement, not a query method.")
    REPORT.write_text("\n".join(L), encoding='utf-8')
    out(f"\n[written to {REPORT.name}]")

if __name__ == "__main__":
    main()
