"""
scp_refresh.py — refresh ALL loaded SCP price lists in one shot (no browser).

Why: our price CSVs are frozen snapshots from download day — SCP's guide
moves daily, and nothing was refreshing already-loaded sets.

How it works (July 16, revised after probing):
  - The account-level download URL serves the VIDEO GAME guide (SCP shares
    PriceCharting's backend), so the sports guide must be requested per
    console via:  /price-guide/download-custom?t=<TOKEN>&console-uids=G####
  - Each console's G-uid appears on its public console page. This script
    builds a uid map automatically from our scp_csv filenames (which are the
    console slugs), caches it in scp_console_uids.json, then downloads the
    fresh CSVs in chunks and rewrites the per-console files.

Setup (one time):
    PowerShell:  [Environment]::SetEnvironmentVariable("SNIPEWINS_SCP_TOKEN", "<40-char token>", "User")
    (token: sportscardspro.com -> My Account -> Subscriptions -> Download/API link)

Usage:
    python scp_refresh.py --dry-run [--token XXXX]   # report only, write nothing
    python scp_refresh.py [--token XXXX]             # refresh all tracked consoles

After a successful run:
    git add scp_csv scp_console_uids.json
    git commit -m "Weekly SCP price refresh"
    git push origin main
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
CSV_DIR = HERE / "scp_csv"
UID_CACHE = HERE / "scp_console_uids.json"
TOKEN_ENV = "SNIPEWINS_SCP_TOKEN"
BASE = "https://www.sportscardspro.com"
DL_URL = BASE + "/price-guide/download-custom?t={token}&console-uids={uids}"
CHUNK = 20           # consoles per download request
PAGE_DELAY = 0.6     # seconds between console-page fetches (uid discovery)
DL_DELAY = 2.0       # seconds between chunk downloads
# Console uid appears two ways: the logged-in "Download Price List" link uses
# console-uids=G####; the PUBLIC page's "Compare vs." link uses uids=C####.
# Both prefixes are accepted by download-custom (same id namespace). Prefer
# the download link when present, fall back to the compare link.
UID_RES = (re.compile(r"console-uids=([CG]\d+)"), re.compile(r"[?&]uids=([CG]\d+)"))


def _open(url: str, timeout: int = 600):
    req = urllib.request.Request(url, headers={"User-Agent": "SnipeWins-refresh/1.0"})
    return urllib.request.urlopen(req, timeout=timeout)


def _load_uid_map() -> dict:
    try:
        return json.loads(UID_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _discover_uids(slugs, uid_map, verbose=True) -> tuple[dict, list]:
    """Fetch console pages for slugs missing from the cache; extract G-uids."""
    missing = [s for s in slugs if s not in uid_map]
    failed = []
    if not missing:
        return uid_map, failed
    print(f"Discovering console uids for {len(missing)} consoles (one-time, cached)...")
    for i, slug in enumerate(missing, 1):
        url = f"{BASE}/console/{slug}"
        try:
            with _open(url, timeout=60) as resp:
                html = resp.read(400_000).decode("utf-8", "replace")
            m = None
            for _rx in UID_RES:
                m = _rx.search(html)
                if m:
                    break
            if m:
                uid_map[slug] = m.group(1)
                if verbose:
                    print(f"  [{i}/{len(missing)}] {slug} -> {m.group(1)}")
            else:
                failed.append(slug)
                print(f"  [{i}/{len(missing)}] {slug} -> NO UID FOUND on page")
        except Exception as exc:
            failed.append(slug)
            print(f"  [{i}/{len(missing)}] {slug} -> {type(exc).__name__}: {exc}")
        time.sleep(PAGE_DELAY)
        if i % 10 == 0:
            UID_CACHE.write_text(json.dumps(uid_map, indent=1), encoding="utf-8")
    UID_CACHE.write_text(json.dumps(uid_map, indent=1), encoding="utf-8")
    return uid_map, failed


def _find_console_slugs(term: str) -> set:
    """Scrape SCP search pages for console slugs matching a term (e.g.
    'kaboom' -> football-cards-2024-panini-absolute-kaboom-vertical, ...).
    Sports scope: baseball/basketball/football; EuroLeague excluded (owner)."""
    import urllib.parse
    t_slug = "-".join(re.sub(r"[^a-z0-9 ]", " ", term.lower()).split())
    slugs = set()
    queries = [term] + [f"{term} {y}" for y in range(2018, 2027)]
    for q in queries:
        url = BASE + "/search-products?type=prices&q=" + urllib.parse.quote(q)
        try:
            with _open(url, timeout=60) as resp:
                html = resp.read(900_000).decode("utf-8", "replace")
        except Exception as exc:
            print(f"    search {q!r}: {type(exc).__name__}")
            continue
        for m in re.finditer(r"/console/((?:baseball|basketball|football)-cards-[a-z0-9\-]+)", html):
            slug = m.group(1)
            if t_slug in slug and "euroleague" not in slug:
                slugs.add(slug)
        time.sleep(PAGE_DELAY)
    return slugs


def _add_new_consoles(terms: list, token: str, dry_run: bool) -> int:
    """Find + download consoles for chase terms that we don't hold yet."""
    have = {f.stem for f in CSV_DIR.glob("*.csv")}
    all_new = {}
    for term in terms:
        found = _find_console_slugs(term)
        new = sorted(found - have)
        already = len(found & have)
        print(f"[{term}] consoles found: {len(found)} (new: {len(new)}, already tracked: {already})")
        for sl in new:
            all_new[sl] = term
    if not all_new:
        print("Nothing new to add.")
        return 0
    print(f"\n{len(all_new)} new consoles to download{' (dry run — skipping)' if dry_run else ''}:")
    for sl in sorted(all_new):
        print(f"   {sl}")
    if dry_run:
        return 0
    uid_map = _load_uid_map()
    uid_map, failed = _discover_uids(sorted(all_new), uid_map)
    return _download_slugs(sorted(all_new), uid_map, token)


def _download_slugs(slugs: list, uid_map: dict, token: str) -> int:
    """CHUNKED downloader for new consoles: 20 uids per request (~12 requests
    for 220 consoles instead of 220). Splits each response by console-name
    into per-slug CSVs. RESUMABLE (existing files skipped). 429 rate limits:
    waits 11 minutes and retries the SAME chunk, up to 8 tries — leave it
    running and it grinds through; Ctrl+C and rerun any time."""
    def _slugify(cn: str) -> str:
        out = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(cn or ""))
        while "--" in out:
            out = out.replace("--", "-")
        return out.strip("-")

    todo = [sl for sl in slugs if uid_map.get(sl) and not (CSV_DIR / f"{sl}.csv").exists()]
    skipped = len(slugs) - len(todo)
    print(f"Downloading {len(todo)} consoles ONE per request ({skipped} already on disk / no uid).")
    print("NOTE: multi-console requests 503 on SCP's side; singles are the proven shape.")
    print("Pacing is gentle (90s between downloads) to protect the account's standing.")
    ok = 0
    hard_fails = 0
    for n, sl in enumerate(todo, 1):
        url = DL_URL.format(token=token, uids=uid_map[sl])
        data = None
        for att in range(1, 4):
            try:
                with _open(url) as resp:
                    data = resp.read()
                if data[:15].lstrip().startswith(b"<"):
                    data = None
                break
            except Exception as exc:
                msg = str(exc)
                if "429" in msg or "503" in msg:
                    if att < 3:
                        time.sleep(120 * att)
                        continue
                break
        if data is None or data.count(b"\n") < 2:
            hard_fails += 1
            print(f"  [{n}/{len(todo)}] {sl}: unavailable ({hard_fails} consecutive failures)")
            if hard_fails >= 3:
                print("\nSCP is refusing downloads right now — STOPPING to protect the account.")
                print("Try again tomorrow with the same command; progress is saved.")
                print("Recommended: email SCP support about bulk price-list access for your")
                print("Legendary token (you are a paying customer using a paid feature).")
                break
            time.sleep(90)
            continue
        hard_fails = 0
        header_ok = data.split(b"\n", 1)[0].lower().find(b"console-name") >= 0
        if not header_ok:
            print(f"  [{n}/{len(todo)}] {sl}: unexpected content — skipped")
            time.sleep(90)
            continue
        (CSV_DIR / f"{sl}.csv").write_bytes(data)
        _nrows = data.count(b"\n") - 1
        print(f"  + [{n}/{len(todo)}] {sl}.csv ({_nrows:,} rows)")
        ok += 1
        time.sleep(90)
    remaining = [sl for sl in slugs if uid_map.get(sl) and not (CSV_DIR / f"{sl}.csv").exists()]
    print(f"\nAdded {ok} console CSVs; {len(remaining)} still missing.")
    if remaining:
        print("Rerun later:  python scp_refresh.py --download-missing --token <token>")
    else:
        print('All done. Next: git add scp_csv scp_console_uids.json && git commit -m "Add chase consoles" && git push origin main')
    return 0

def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh all loaded SCP price lists")
    ap.add_argument("--dry-run", action="store_true", help="download + report, write nothing")
    ap.add_argument("--token", default="", help="SCP token (alternative to the env var)")
    ap.add_argument("--only", default="", help="comma-separated slugs to refresh (testing)")
    ap.add_argument("--add-terms", default="", help="comma-separated search terms; finds + downloads NEW consoles for them")
    ap.add_argument("--download-missing", action="store_true", help="download any console in the uid cache that has no CSV yet (resume after rate limit)")
    args = ap.parse_args()

    token = (args.token or os.environ.get(TOKEN_ENV, "")).strip().strip('"').strip("'")
    if not token:
        print(f"ERROR: no token. Run with --token <40-char-token> or set {TOKEN_ENV}.")
        print("Token: sportscardspro.com -> My Account -> Subscriptions -> Download/API link (last URL segment).")
        return 2
    shown = (token[:4] + "..." + token[-4:]) if len(token) > 10 else repr(token)
    print(f"Token read: {shown} (length {len(token)})")
    if " " in token or "<" in token or len(token) < 20:
        print("ERROR: that doesn't look like a real token.")
        return 2

    if args.add_terms:
        terms = [t.strip() for t in args.add_terms.split(",") if t.strip()]
        return _add_new_consoles(terms, token, args.dry_run)

    if args.download_missing:
        uid_map = _load_uid_map()
        return _download_slugs(sorted(uid_map), uid_map, token)

    files = sorted(CSV_DIR.glob("*.csv"))
    if args.only:
        keep = {s.strip() for s in args.only.split(",") if s.strip()}
        files = [f for f in files if f.stem in keep]
    slugs = [f.stem for f in files]
    slug_to_file = {f.stem: f for f in files}
    print(f"Tracked consoles: {len(slugs)}")
    if not slugs:
        print("ERROR: nothing to refresh.")
        return 2

    uid_map, failed_uids = _discover_uids(slugs, _load_uid_map())
    have = [s for s in slugs if s in uid_map]
    if failed_uids:
        print(f"WARN: no uid for {len(failed_uids)} consoles (their files kept as-is): {failed_uids[:8]}")
    print(f"Refreshing {len(have)} consoles in chunks of {CHUNK}...")

    counts: dict[str, int] = {}     # console-name -> fresh rows
    tmp_files: dict[str, tuple] = {}  # console-name -> (tmp path, final path)
    writers: dict[str, tuple] = {}
    t0 = time.time()
    total_rows = 0
    unmatched_names = set()
    # console-name (guide) -> slug: build from existing files' first data row
    name_to_slug = {}
    for f in files:
        try:
            with open(f, "r", encoding="utf-8-sig", newline="") as fh:
                rd = csv.reader(fh)
                header = next(rd, None)
                row = next(rd, None)
                if header and row:
                    ci = [i for i, h in enumerate(header) if h.strip().lower() == "console-name"]
                    if ci:
                        name_to_slug[row[ci[0]].strip()] = f.stem
        except Exception:
            pass

    def _open_with_retry(url, label):
        """SCP's CSV generator 503s routinely and succeeds on retry (observed
        across every browser session too). Retry with growing waits."""
        waits = [0, 8, 20, 45, 90]
        last = None
        for att, w in enumerate(waits, 1):
            if w:
                print(f"    {label}: retrying in {w}s (attempt {att}/{len(waits)})...")
                time.sleep(w)
            try:
                return _open(url)
            except Exception as exc:
                last = exc
                if "503" not in str(exc):
                    raise
        raise last

    def _stream_into(resp):
        nonlocal total_rows
        got = 0
        with resp:
            text = io.TextIOWrapper(resp, encoding="utf-8", errors="replace", newline="")
            rd = csv.reader(text)
            header_out = next(rd, None)
            if not header_out or "console-name" not in [h.strip().lower() for h in header_out]:
                return -1
            cn_i = [h.strip().lower() for h in header_out].index("console-name")
            for row in rd:
                total_rows += 1
                if len(row) <= cn_i:
                    continue
                cn = row[cn_i].strip()
                slug = name_to_slug.get(cn)
                if slug is None:
                    unmatched_names.add(cn)
                    continue
                counts[cn] = counts.get(cn, 0) + 1
                got += 1
                if not args.dry_run:
                    if cn not in writers:
                        fp = slug_to_file[slug]
                        tmp = fp.with_suffix(".csv.refresh_tmp")
                        fh = open(tmp, "w", encoding="utf-8", newline="")
                        wr = csv.writer(fh)
                        wr.writerow(header_out)
                        writers[cn] = (fh, wr)
                        tmp_files[cn] = (tmp, fp)
                    writers[cn][1].writerow(row)
        return got

    try:
        for ci in range(0, len(have), CHUNK):
            chunk = have[ci:ci + CHUNK]
            uids = ",".join(uid_map[s] for s in chunk)
            url = DL_URL.format(token=token, uids=uids)
            _label = f"chunk {ci//CHUNK+1}/{(len(have)+CHUNK-1)//CHUNK}"
            try:
                got = _stream_into(_open_with_retry(url, _label))
                if got >= 0:
                    print(f"  {_label}: ok ({len(chunk)} consoles, {got:,} rows)")
                    time.sleep(DL_DELAY)
                    continue
                print(f"  {_label}: response was not CSV — falling back to per-console")
            except Exception as exc:
                print(f"  {_label}: {type(exc).__name__}: {exc} — falling back to per-console")
            # Per-console fallback (the shape every successful browser download used)
            for slug2 in chunk:
                u2 = DL_URL.format(token=token, uids=uid_map[slug2])
                try:
                    got2 = _stream_into(_open_with_retry(u2, slug2))
                    print(f"    {slug2}: {'ok' if got2 >= 0 else 'NOT CSV'} ({max(got2,0):,} rows)")
                except Exception as exc2:
                    print(f"    {slug2}: {type(exc2).__name__} — kept old file")
                time.sleep(DL_DELAY)
            time.sleep(DL_DELAY)
    finally:
        for cn, (fh, _wr) in writers.items():
            fh.close()
    print(f"\nStreamed {total_rows:,} rows in {round(time.time()-t0,1)}s; "
          f"{len(counts)} consoles matched.")
    if unmatched_names:
        print(f"NOTE: {len(unmatched_names)} console names in responses didn't match our files: "
              f"{sorted(unmatched_names)[:6]}")

    if args.dry_run:
        print("Dry run — nothing written. Sample fresh counts:")
        for cn in sorted(counts)[:15]:
            print(f"   {cn}: {counts[cn]:,}")
        print(f"   ... ({len(counts)} consoles total)")
        return 0

    updated = 0
    for cn, (tmp, fp) in tmp_files.items():
        try:
            old_rows = max(0, sum(1 for _ in open(fp, "r", encoding="utf-8-sig")) - 1)
        except Exception:
            old_rows = 0
        new_rows = counts.get(cn, 0)
        if new_rows < max(10, old_rows // 4):
            print(f"  SAFETY-SKIP {fp.name}: fresh {new_rows} vs old {old_rows} rows — kept old file.")
            tmp.unlink(missing_ok=True)
            continue
        tmp.replace(fp)
        updated += 1

    print(f"Done: {updated} console files refreshed.")
    print('Next: git add scp_csv scp_console_uids.json && git commit -m "Weekly SCP price refresh" && git push origin main')
    return 0


if __name__ == "__main__":
    sys.exit(main())
