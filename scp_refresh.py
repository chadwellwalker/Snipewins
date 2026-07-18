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
UID_RE = re.compile(r"console-uids=(G\d+)")


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
            m = UID_RE.search(html)
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh all loaded SCP price lists")
    ap.add_argument("--dry-run", action="store_true", help="download + report, write nothing")
    ap.add_argument("--token", default="", help="SCP token (alternative to the env var)")
    ap.add_argument("--only", default="", help="comma-separated slugs to refresh (testing)")
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

    try:
        for ci in range(0, len(have), CHUNK):
            chunk = have[ci:ci + CHUNK]
            uids = ",".join(uid_map[s] for s in chunk)
            url = DL_URL.format(token=token, uids=uids)
            try:
                with _open(url) as resp:
                    text = io.TextIOWrapper(resp, encoding="utf-8", errors="replace", newline="")
                    rd = csv.reader(text)
                    header_out = next(rd, None)
                    if not header_out or "console-name" not in [h.strip().lower() for h in header_out]:
                        print(f"  chunk {ci//CHUNK+1}: unexpected response (not CSV) — skipped")
                        continue
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
                print(f"  chunk {ci//CHUNK+1}/{(len(have)+CHUNK-1)//CHUNK}: ok ({len(chunk)} consoles)")
            except Exception as exc:
                print(f"  chunk {ci//CHUNK+1}: {type(exc).__name__}: {exc} — consoles kept as-is")
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
