"""
diag.py — one-shot scan diagnostic summarizer.

What it does:
    Reads your most recent Streamlit run log (last_scan.log by default), finds
    the funnel/observability logs we've been building up, and prints a clean
    summary in one block you can paste straight to Claude.

How to use it:
    1) Run your app and capture the output to last_scan.log (see HOW_TO_USE.md).
    2) Click "Run a scan" in Streamlit. Wait for the scan to finish.
    3) Open a terminal in the "Python Coding" folder and run:
           python diag.py
       (or pass a specific log path: python diag.py mylog.log)
    4) Copy the printed summary and paste it into Claude.

Optional: --write flag dumps the same summary to latest_diag.md so Claude can
read it directly with its file tool ("read latest_diag.md").
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---- Logs we care about, in funnel order ---------------------------------

# Each entry: (display_label, log_tag, "last" | "all")
#   "last" → keep only the final occurrence in the log (one per scan)
#   "all"  → keep every occurrence (per-row trace lines)
KEY_LOGS: List[Tuple[str, str, str]] = [
    ("Engine death funnel",        "[ENGINE_DEATH_FUNNEL]",      "last"),
    ("Engine death reasons",       "[ENGINE_DEATH_REASON_SUMMARY]", "last"),
    ("Time bucket split",          "[TIME_BUCKET_SPLIT]",        "last"),
    ("Player routing summary",     "[PLAYER_ROUTING_SUMMARY]",   "last"),
    ("Post-player funnel",         "[POST_PLAYER_FUNNEL]",       "last"),
    ("Target route summary",       "[TARGET_ROUTE_SUMMARY]",     "last"),
    ("Valuation handoff (final)",  "[VALUATION_HANDOFF_GATE] stage=final_pre_valuation", "last"),
    ("Candidate funnel (UI)",      "[CANDIDATE_FUNNEL_SUMMARY]", "last"),
    ("Board state",                "[ES][BOARD_STATE]",          "last"),
    ("Board mix",                  "[BOARD_MIX]",                "last"),
    ("Board replacement pool",     "[BOARD_REPLACEMENT_POOL]",   "last"),
    ("Board drop reasons",         "[BOARD_DROP_REASON_SUMMARY]", "last"),
    ("Live preserve summary",     "[LIVE_PRESERVE_SUMMARY]",     "last"),
]

# Per-row drop traces — show the most recent few of each.
ROW_TRACES: List[Tuple[str, str, int]] = [
    ("Player routing drops",   "[PLAYER_ROUTING_DROP]", 8),
    ("Post-player row drops",  "[POST_PLAYER_DROP]",    12),
    ("Target route traces",    "[TARGET_ROUTE_TRACE]",  6),
    ("Valued row traces",      "[VALUED_ROW_TRACE]",    8),
    ("Final action decisions", "[FINAL_ACTION_DECISION]", 6),
    ("Strict window blocks",   "[STRICT_WINDOW_RESCUE_BLOCKED]", 4),
    ("Self-comp blocks",       "[SELF_COMP_BLOCK]", 4),
    ("Price echo blocks",      "[PRICE_ECHO_BLOCK]", 4),
]

# ---- Implementation ------------------------------------------------------

def _find_default_log(folder: Path) -> Optional[Path]:
    """Find the most recent .log file in the folder."""
    candidates = sorted(folder.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _read_log(path: Path) -> List[str]:
    try:
        # Use latin-1 to never blow up on weird bytes; we only care about ASCII tags.
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return fh.read().splitlines()
    except Exception as exc:
        print(f"ERROR: could not read {path}: {exc}", file=sys.stderr)
        sys.exit(2)


def _matches(line: str, tag: str) -> bool:
    return tag in line


def _format_section(title: str, lines: List[str]) -> str:
    if not lines:
        return f"## {title}\n  (none found in log)\n"
    body = "\n".join(f"  {ln.strip()}" for ln in lines)
    return f"## {title}\n{body}\n"


def _summarize(lines: List[str]) -> str:
    blocks: List[str] = []

    # First: scan-level summary lines (last occurrence of each)
    for label, tag, mode in KEY_LOGS:
        matches = [ln for ln in lines if _matches(ln, tag)]
        if not matches:
            blocks.append(_format_section(label, []))
            continue
        if mode == "last":
            blocks.append(_format_section(label, [matches[-1]]))
        else:
            blocks.append(_format_section(label, matches))

    # Then: per-row drop traces (last N of each)
    blocks.append("\n# Per-row drops (most recent)\n")
    for label, tag, n in ROW_TRACES:
        matches = [ln for ln in lines if _matches(ln, tag)]
        if not matches:
            continue
        recent = matches[-n:]
        blocks.append(_format_section(f"{label} (showing {len(recent)} of {len(matches)})", recent))

    # Lightweight tally over the entire log — counts of major drop types.
    tally: Dict[str, int] = defaultdict(int)
    for tag in (
        "[PLAYER_ROUTING_DROP]",
        "[POST_PLAYER_DROP]",
        "[TARGET_ROUTE_TRACE]",
        "[STRICT_WINDOW_RESCUE_BLOCKED]",
        "[SELF_COMP_BLOCK]",
        "[ACTIVE_LISTING_BLOCK]",
        "[PRICE_ECHO_BLOCK]",
        "[DISCOVERY_QUALITY_DROP]",
        "[EXECUTION_PROMOTION_BLOCK]",
        "[FINAL_ACTION_PASS]",
        "[FINAL_ACTION_SNIPE]",
        "[PREPARE_BUCKET]",
        "[TIME_BUCKET_ASSIGN]",
    ):
        for ln in lines:
            if _matches(ln, tag):
                tally[tag] += 1
    if tally:
        blocks.append("\n# Tag tally over the whole log\n")
        max_tag = max(len(t) for t in tally)
        for t, n in sorted(tally.items(), key=lambda kv: -kv[1]):
            blocks.append(f"  {t.ljust(max_tag)}  {n}")
        blocks.append("")

    return "\n".join(blocks)


def _diagnostic_hint(lines: List[str]) -> str:
    """A tiny natural-language hint about where the funnel is dying."""
    def _last_match(tag: str) -> Optional[str]:
        for ln in reversed(lines):
            if tag in ln:
                return ln
        return None

    def _grab_int(s: Optional[str], key: str) -> Optional[int]:
        if not s:
            return None
        m = re.search(rf"{re.escape(key)}=(\-?\d+)", s)
        return int(m.group(1)) if m else None

    hints: List[str] = []
    edf = _last_match("[ENGINE_DEATH_FUNNEL]")
    if edf:
        stages = [
            ("raw_fetched", "raw_fetched"),
            ("auction_only", "auction_only"),
            ("strict_window", "strict_window"),
            ("title_clean", "title_clean"),
            ("player_pass", "player_pass"),
            ("product_pass", "product_pass"),
            ("parallel_pass", "parallel_pass"),
            ("target_pass", "target_pass"),
            ("quality_pass", "quality_pass"),
            ("valuation_pass", "valuation_pass"),
            ("final_candidates", "final_candidates"),
            ("return_rows", "return_rows"),
        ]
        prev_label, prev_val = None, None
        for label, key in stages:
            val = _grab_int(edf, key)
            if val is None:
                continue
            if prev_val is not None and prev_val > 0 and val < prev_val:
                drop = prev_val - val
                pct = round(100 * drop / prev_val) if prev_val else 0
                if pct >= 30:
                    hints.append(f"  - {prev_label} → {label}: {prev_val} → {val} (lost {drop}, {pct}% of stage)")
            prev_label, prev_val = label, val

    if not hints:
        return ""

    out = ["", "# Quick read — biggest stage cliffs (>=30% drop)"]
    out.extend(hints)
    out.append("")
    return "\n".join(out)


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Summarize the most recent SNIPEWINS scan log.")
    ap.add_argument("path", nargs="?", default=None, help="Log file to read (default: most recent *.log here)")
    ap.add_argument("--write", action="store_true", help="Also write summary to latest_diag.md")
    args = ap.parse_args(argv)

    here = Path(__file__).parent

    if args.path:
        log_path = Path(args.path)
        if not log_path.is_absolute():
            log_path = here / log_path
    else:
        log_path = _find_default_log(here)
        if log_path is None:
            print("ERROR: no .log files found in", here, file=sys.stderr)
            print("Run your app with output redirected first. See HOW_TO_USE.md.", file=sys.stderr)
            return 2

    if not log_path.exists():
        print(f"ERROR: {log_path} does not exist", file=sys.stderr)
        return 2

    lines = _read_log(log_path)
    summary = []
    summary.append(f"# SNIPEWINS scan summary")
    summary.append(f"  source: {log_path.name}  ({len(lines)} lines)")
    summary.append("")
    summary.append(_summarize(lines))
    summary.append(_diagnostic_hint(lines))

    text = "\n".join(summary)
    print(text)

    if args.write:
        out_path = here / "latest_diag.md"
        try:
            out_path.write_text(text, encoding="utf-8")
            print(f"\n[wrote summary to {out_path.name}]")
        except Exception as exc:
            print(f"WARN: could not write {out_path.name}: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
