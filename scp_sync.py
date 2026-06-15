"""
scp_sync.py — import downloaded SportsCardsPro CSVs and rebuild the price store.

SportsCardsPro CSV downloads are per-set and gated behind your logged-in
Legendary session (no token-based or master download for sports), so the files
arrive via the browser's "Download Price List" button. This script does the rest
hands-off:

    1. Scans your download folders for SportsCardsPro price-guide CSVs
       (identified by their column signature, not their filename).
    2. Copies each into ./scp_csv/, named by the set it contains (console-name),
       so re-downloads OVERWRITE the old copy instead of piling up duplicates.
    3. Rebuilds the SQLite price store.

Usage:
    python scp_sync.py                # scan default download folders + rebuild
    python scp_sync.py --dir "C:\\path\\to\\folder"   # add an extra source folder

Default source folders scanned: your ~/Downloads, this project folder, and the
folder above it. Override/add with --dir (repeatable).
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).parent
SCP_CSV_DIR = Path(os.environ.get("SNIPEWINS_SCP_CSV_DIR") or str(HERE / "scp_csv"))

# A file is a SportsCardsPro price guide if its header has these columns.
SIGNATURE_COLS = {"id", "console-name", "product-name", "loose-price", "manual-only-price"}


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-")
    return s or "unknown-set"


def _is_scp_csv(path: Path) -> bool:
    try:
        with open(path, newline="", encoding="utf-8", errors="ignore") as fh:
            header = next(csv.reader(fh), [])
        return SIGNATURE_COLS.issubset(set(h.strip() for h in header))
    except Exception:
        return False


def _console_name(path: Path) -> str:
    """Read the set name from the first data row's console-name column."""
    try:
        with open(path, newline="", encoding="utf-8", errors="ignore") as fh:
            for row in csv.DictReader(fh):
                cn = (row.get("console-name") or "").strip()
                if cn:
                    return cn
    except Exception:
        pass
    return ""


def default_source_dirs() -> list:
    dirs = [Path.home() / "Downloads", HERE, HERE.parent]
    out, seen = [], set()
    for d in dirs:
        try:
            rp = d.resolve()
        except Exception:
            continue
        if rp.exists() and rp not in seen:
            seen.add(rp)
            out.append(rp)
    return out


def sync(extra_dirs=None, rebuild=True):
    SCP_CSV_DIR.mkdir(exist_ok=True)
    sources = default_source_dirs() + [Path(d) for d in (extra_dirs or [])]
    imported, skipped = [], 0
    seen_sets = {}
    # newest files first so the freshest copy of a set wins
    candidates = []
    for d in sources:
        candidates += [p for p in d.glob("*.csv")]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for p in candidates:
        # don't re-scan files already inside scp_csv
        try:
            if p.resolve().parent == SCP_CSV_DIR.resolve():
                continue
        except Exception:
            pass
        if not _is_scp_csv(p):
            continue
        cn = _console_name(p)
        if not cn:
            skipped += 1
            continue
        if cn in seen_sets:
            continue  # already imported a newer copy of this set
        seen_sets[cn] = True
        dest = SCP_CSV_DIR / (_slug(cn) + ".csv")
        shutil.copy2(p, dest)
        imported.append((cn, p.name, dest.name))

    print(f"Scanned: {', '.join(str(d) for d in sources)}")
    print(f"Imported {len(imported)} set file(s) into {SCP_CSV_DIR}:")
    for cn, src, dst in imported:
        print(f"   {cn:48} <- {src}")
    if skipped:
        print(f"   ({skipped} SCP-looking file(s) skipped: no console-name)")

    if rebuild:
        try:
            import scp_price_store as store
            stats = store.rebuild_store()
            print("\nStore rebuilt:", stats)
        except Exception as e:
            print("\nRebuild failed:", e)
    return imported


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", action="append", default=[], help="extra source folder to scan")
    ap.add_argument("--no-rebuild", action="store_true")
    args = ap.parse_args()
    sync(extra_dirs=args.dir, rebuild=not args.no_rebuild)
