"""
scp_refresh.py — refresh ALL loaded SCP price lists in one shot (no browser).

Why this exists (July 16 day-6 audit): our price CSVs are frozen snapshots
from download day — SCP's guide moves daily, and nothing was refreshing
already-loaded sets. SCP/PriceCharting Legendary accounts expose a tokenized
full price-guide download (regenerated every 24h, one download per 10 min):

    https://www.sportscardspro.com/download-price-guide/<TOKEN>

This script streams that single CSV, keeps only the consoles we already
track (whatever is in scp_csv/), and rewrites each per-console CSV with the
fresh rows. Then commit + push — Render rebuilds the store on deploy.

Setup (one time):
    Set the token in an environment variable (NEVER commit it):
      PowerShell:  [Environment]::SetEnvironmentVariable("SNIPEWINS_SCP_TOKEN", "<40-char token>", "User")
      (token lives at SCP: My Account -> Subscriptions -> Download/API link)

Usage:
    python scp_refresh.py            # refresh every console in scp_csv/
    python scp_refresh.py --dry-run  # download + report row counts, write nothing

After a successful run:
    git add scp_csv
    git commit -m "Weekly SCP price refresh"
    git push origin main
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
CSV_DIR = HERE / "scp_csv"
TOKEN_ENV = "SNIPEWINS_SCP_TOKEN"
GUIDE_URL = "https://www.sportscardspro.com/download-price-guide/{token}"


def _slug(s: str) -> str:
    # Must match scp_sync._slug so refreshed files land on the same names.
    try:
        from scp_sync import _slug as _sync_slug
        return _sync_slug(s)
    except Exception:
        out = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(s or ""))
        while "--" in out:
            out = out.replace("--", "-")
        return out.strip("-")


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh all loaded SCP price lists")
    ap.add_argument("--dry-run", action="store_true", help="download + report, write nothing")
    ap.add_argument("--url", default="", help="override guide URL (testing)")
    ap.add_argument("--token", default="", help="SCP token (alternative to the env var)")
    args = ap.parse_args()

    token = (args.token or os.environ.get(TOKEN_ENV, "")).strip().strip('"').strip("'")
    if not token and not args.url:
        print(f"ERROR: no token. Either run with --token <40-char-token> or set {TOKEN_ENV}.")
        print("Token location: sportscardspro.com -> My Account -> Subscriptions -> Download/API link (last part of that URL).")
        return 2
    if token and not args.url:
        _bad = (" " in token or "<" in token or len(token) < 20)
        _shown = (token[:4] + "..." + token[-4:]) if len(token) > 10 else repr(token)
        print(f"Token read: {_shown} (length {len(token)})")
        if _bad:
            print("ERROR: that doesn't look like a real token (placeholder text, spaces, or too short).")
            print(f"Fix: rerun with --token <the real 40-char string>, or re-set {TOKEN_ENV} and open a NEW PowerShell window.")
            return 2

    tracked = {}  # console-name (as it appears in existing CSVs) -> file path
    for fp in sorted(CSV_DIR.glob("*.csv")):
        try:
            with open(fp, "r", encoding="utf-8-sig", newline="") as fh:
                rd = csv.reader(fh)
                header = next(rd, None)
                row = next(rd, None)
                if not header or not row:
                    continue
                idx = [i for i, h in enumerate(header) if h.strip().lower() == "console-name"]
                if not idx:
                    continue
                tracked[row[idx[0]].strip()] = fp
        except Exception as exc:
            print(f"  WARN: could not read {fp.name}: {exc}")
    if not tracked:
        print("ERROR: no tracked consoles found in scp_csv/.")
        return 2
    print(f"Tracked consoles: {len(tracked)}")

    url = args.url or GUIDE_URL.format(token=token)
    print("Downloading full price guide (single request; SCP regenerates it every 24h)...")
    req = urllib.request.Request(url, headers={"User-Agent": "SnipeWins-refresh/1.0"})
    t0 = time.time()

    writers = {}   # console-name -> (file handle, csv.writer)
    counts = {}    # console-name -> fresh row count
    header_out = None
    skipped_consoles = set()
    total_rows = 0

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            ctype = resp.headers.get("Content-Type", "")
            if "csv" not in ctype and "text" not in ctype and "octet" not in ctype:
                print(f"ERROR: unexpected Content-Type {ctype!r} — token invalid or endpoint changed.")
                return 3
            text = io.TextIOWrapper(resp, encoding="utf-8", errors="replace", newline="")
            rd = csv.reader(text)
            header_out = next(rd, None)
            if not header_out or "console-name" not in [h.strip().lower() for h in header_out]:
                print(f"ERROR: guide header missing console-name: {header_out!r}")
                return 3
            cn_i = [h.strip().lower() for h in header_out].index("console-name")
            for row in rd:
                total_rows += 1
                if len(row) <= cn_i:
                    continue
                cn = row[cn_i].strip()
                if cn not in tracked:
                    skipped_consoles.add(cn)
                    continue
                counts[cn] = counts.get(cn, 0) + 1
                if not args.dry_run:
                    if cn not in writers:
                        fp = tracked[cn]
                        tmp = fp.with_suffix(".csv.refresh_tmp")
                        fh = open(tmp, "w", encoding="utf-8", newline="")
                        wr = csv.writer(fh)
                        wr.writerow(header_out)
                        writers[cn] = (fh, wr, tmp, fp)
                    writers[cn][1].writerow(row)
    finally:
        for cn, (fh, _wr, _tmp, _fp) in writers.items():
            fh.close()

    print(f"Guide streamed: {total_rows:,} rows in {round(time.time()-t0,1)}s; "
          f"{len(counts)} of {len(tracked)} tracked consoles present; "
          f"{len(skipped_consoles):,} untracked consoles skipped.")

    missing = sorted(set(tracked) - set(counts))
    if missing:
        print(f"WARN: {len(missing)} tracked consoles NOT in the guide (kept old files):")
        for m in missing[:20]:
            print(f"   {m}")

    if args.dry_run:
        print("Dry run — nothing written. Per-console fresh counts:")
        for cn in sorted(counts):
            print(f"   {cn}: {counts[cn]:,}")
        return 0

    updated = 0
    for cn, (_fh, _wr, tmp, fp) in writers.items():
        old_rows = max(0, sum(1 for _ in open(fp, "r", encoding="utf-8-sig")) - 1)
        new_rows = counts.get(cn, 0)
        if new_rows < max(10, old_rows // 4):
            print(f"  SAFETY-SKIP {fp.name}: fresh {new_rows} rows vs old {old_rows} — looks truncated, kept old file.")
            tmp.unlink(missing_ok=True)
            continue
        tmp.replace(fp)
        updated += 1
        print(f"  updated {fp.name}: {old_rows:,} -> {new_rows:,} rows")

    print(f"\nDone: {updated} console files refreshed.")
    print("Next: git add scp_csv && git commit -m \"Weekly SCP price refresh\" && git push origin main")
    return 0


if __name__ == "__main__":
    sys.exit(main())
