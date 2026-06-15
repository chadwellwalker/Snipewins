"""
sportscardspro_coverage_test.py — deep coverage probe for SnipeWins.

Run from the `Python Coding` folder:

    python sportscardspro_coverage_test.py

For each of your real cards it shows EVERY price tier the guide has (not just
the one matching the grade), plus a sanity check on whether the matched
product is actually the right card. Writes full detail to coverage_report.txt
so Claude can read it directly.

Read-only. Touches nothing in your live engine.
"""
from __future__ import annotations
import json, re, sys, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path

HERE = Path(__file__).parent
ENV = HERE / ".env"
POOL = HERE / "daily_pool.json"
REPORT = HERE / "coverage_report.txt"
SAMPLE_SIZE = 40
BASE = "https://www.sportscardspro.com/api/product"

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# grade label -> the API field that represents it
GRADE_TO_FIELD = {
    'PSA10': 'manual-only-price', 'GR9.5': 'box-only-price', 'GR9': 'graded-price',
    'GR8': 'new-price', 'GR7': 'cib-price', 'RAW': 'loose-price',
}

def detect_grade(title: str) -> str:
    u = title.upper()
    if re.search(r'PSA\s*10|GEM\s*MT\s*10|BGS\s*10', u): return 'PSA10'
    if re.search(r'\b(PSA|BGS|SGC|CSG)\s*9\.5\b', u):    return 'GR9.5'
    if re.search(r'\b(PSA|BGS|SGC|CSG)\s*9\b', u):       return 'GR9'
    if re.search(r'\b(PSA|BGS|SGC|CSG)\s*8(\.5)?\b', u): return 'GR8'
    if re.search(r'\b(PSA|BGS|SGC)\s*7', u):             return 'GR7'
    return 'RAW'

def clean(t: str) -> str:
    t = re.sub(r'\b(PSA|BGS|SGC|CSG)\s*\d+(\.\d)?\b', '', t, flags=re.I)
    t = re.sub(r'\b(RC|MINT|RARE|HOT|NR|GEM|MT)\b', '', t, flags=re.I)
    t = re.sub(r'[^\w\s/#-]', ' ', t)
    return ' '.join(t.split())

def load_token() -> str:
    for line in ENV.read_text(encoding='utf-8', errors='ignore').splitlines():
        for name in ('SPORTSCARDSPRO_API_KEY=', 'SPORTSCARDSPRO_API_TOKEN=', 'PRICECHARTING_API_TOKEN='):
            if line.strip().startswith(name):
                return line.split('=', 1)[1].strip()
    sys.exit("No SPORTSCARDSPRO_API_KEY found in .env")

def titles_from_pool():
    d = json.loads(POOL.read_text(encoding='utf-8', errors='ignore'))
    out = []
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k.lower() in ('title', 'itemtitle', 'name') and isinstance(v, str):
                    out.append(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for x in o: walk(x)
    walk(d)
    seen, uniq = set(), []
    for t in out:
        if t not in seen:
            seen.add(t); uniq.append(t)
    return uniq

def api(tok, qstr):
    url = BASE + "?" + urllib.parse.urlencode({'t': tok, 'q': qstr})
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {'status': 'error', 'error-message': f"HTTP {e.code}"}
    except Exception as e:
        return {'status': 'error', 'error-message': str(e)[:120]}

def dollars(v):
    return f"${v/100:,.0f}" if isinstance(v, int) and v > 0 else "-"

def year_of(t):
    m = re.search(r'\b(20\d{2})\b', t)
    return m.group(1) if m else None

def last_name(t):
    # crude: pull the longest Capitalized word that isn't a brand/set token
    stop = {'Topps','Chrome','Bowman','Panini','Prizm','Select','Donruss','Optic','Refractor',
            'Gold','Black','Auto','Rookie','Update','Stadium','Club','Spectra','Cosmic','Sapphire',
            'Edition','Anniversary','Supernova','Eclipse','Deca','Fireworks','Stratospheric','Stars',
            'Gilded','Collection','Ultraviolet','Hidden','Potential','Materials','Rising','Concourse',
            'Super','Futures','Draft','Prospect','New','York','Yankees','Titans','Broncos','All'}
    words = re.findall(r'[A-Z][a-zA-Z]+', t)
    cand = [w for w in words if w not in stop and len(w) > 2]
    return cand[-1].lower() if cand else None

def main():
    tok = load_token()
    uniq = titles_from_pool()
    sample = uniq[:SAMPLE_SIZE]
    L = []
    def out(s=""):
        print(s); L.append(s)

    out(f"SportsCardsPro DEEP coverage — token len={len(tok)}")
    out(f"unique cards in pool: {len(uniq)} | testing {len(sample)}\n")

    any_price = exact_grade = ungraded_present = good_match = 0
    detail = []
    for t in sample:
        gl = detect_grade(t)
        fld = GRADE_TO_FIELD[gl]
        res = api(tok, clean(t))
        if res.get('status') == 'success' and res.get('id'):
            pn, cn = res.get('product-name', ''), res.get('console-name', '')
            full = (cn + ' ' + pn).lower()
            prices = {
                'RAW': res.get('loose-price'), 'GR9': res.get('graded-price'),
                'GR8': res.get('new-price'), 'PSA10': res.get('manual-only-price'),
                'GR7': res.get('cib-price'), 'GR9.5': res.get('box-only-price'),
            }
            has_any = any(isinstance(v, int) and v > 0 for v in prices.values())
            has_exact = isinstance(prices.get(gl), int) and prices[gl] > 0
            has_raw = isinstance(prices.get('RAW'), int) and prices['RAW'] > 0
            if has_any: any_price += 1
            if has_exact: exact_grade += 1
            if has_raw: ungraded_present += 1
            # match sanity: year + player last name both present in result
            y = year_of(t); ln = last_name(t)
            yr_ok = (y is None) or (y in full)
            ln_ok = (ln is None) or (ln in full)
            match_ok = yr_ok and ln_ok
            if match_ok: good_match += 1
            flag = "OK   " if match_ok else "SUSPECT"
            detail.append(
                f"{flag} need={gl:5} | {t[:60]}\n"
                f"        -> {cn} | {pn}\n"
                f"        RAW {dollars(prices['RAW'])}  GR9 {dollars(prices['GR9'])}  "
                f"GR8 {dollars(prices['GR8'])}  PSA10 {dollars(prices['PSA10'])}  "
                f"vol={res.get('sales-volume','?')}"
            )
        else:
            detail.append(f"MISS   need={gl:5} | {t[:60]}  ({res.get('error-message','')})")
        time.sleep(1.1)

    n = len(sample)
    out("=== USABLE COVERAGE ===")
    out(f"matched the RIGHT card (yr+name):  {good_match}/{n}  ({100*good_match//n}%)")
    out(f"has ANY price tier:                {any_price}/{n}  ({100*any_price//n}%)")
    out(f"has the EXACT grade you need:      {exact_grade}/{n}  ({100*exact_grade//n}%)")
    out(f"has an UNGRADED price (fallback):  {ungraded_present}/{n}  ({100*ungraded_present//n}%)")
    out("")
    out("=== PER-CARD DETAIL ===")
    for d in detail:
        out(d)
    REPORT.write_text("\n".join(L), encoding='utf-8')
    out(f"\n[written to {REPORT.name}]")

if __name__ == "__main__":
    main()
