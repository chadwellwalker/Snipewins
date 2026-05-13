"""
run_filtered.py — runs Streamlit, prints ONLY funnel/observability lines live,
                  AND saves the full unfiltered log to last_scan.log.

Why this exists:
    The PowerShell + findstr one-liner trips over Windows quoting rules. This
    Python wrapper does the same job (filter live + save full log) without
    any shell-quoting drama.

How to use it:
    cd "C:\\Users\\Chris Walker\\Downloads\\Python Coding-20260414T195928Z-3-001\\Python Coding"
    python run_filtered.py

    The terminal will only show lines you care about (funnel tags). Every
    line that Streamlit emits — filtered or not — is written to last_scan.log
    so you (or Claude or diag.py) can read the full picture afterward.

    To stop: Ctrl+C in this terminal.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List


HERE = Path(__file__).parent
LOG_PATH = HERE / "last_scan.log"


# Tags we want to surface live in the terminal. Edit this list freely.
FILTER_TAGS: List[str] = [
    "[TARGET_ROUTE_TRACE]",
    "[TARGET_ROUTE_SUMMARY]",
    "[POST_PLAYER_FUNNEL]",
    "[POST_PLAYER_DROP]",
    "[BOARD_MIX]",
    "[ENGINE_DEATH_FUNNEL]",
    "[ENGINE_DEATH_REASON_SUMMARY]",
    "[TIME_BUCKET_SPLIT]",
    "[PLAYER_ROUTING_SUMMARY]",
    "[VALUATION_HANDOFF_GATE] stage=final_pre_valuation",
    "[CANDIDATE_FUNNEL_SUMMARY]",
    "[ES][BOARD_STATE]",
    "[BOARD_REPLACEMENT_POOL]",
    "[FINAL_ACTION_DECISION]",
    "[STRICT_WINDOW_RESCUE_BLOCKED]",
    "[SELF_COMP_BLOCK]",
    "[PRICE_ECHO_BLOCK]",
    "[RARE_EXACT_OVERRIDE]",
    "[RARE_RESEARCH_PRICING]",
    "[EDGE_SENTINEL_REPAIR]",
    "[ENGINE_STAGE]",
]


def _line_matches_filter(line: str) -> bool:
    return any(tag in line for tag in FILTER_TAGS)


def main(argv: List[str]) -> int:
    cmd = [sys.executable, "-m", "streamlit", "run", "streamlit_app.py"] + argv

    try:
        log_fh = LOG_PATH.open("w", encoding="utf-8", errors="replace", buffering=1)
    except Exception as exc:
        print(f"ERROR: could not open {LOG_PATH}: {exc}", file=sys.stderr)
        return 2

    header = (
        f"# SNIPEWINS run started {datetime.now().isoformat(timespec='seconds')}\n"
        f"# command: {' '.join(cmd)}\n"
        f"# cwd: {HERE}\n\n"
    )
    log_fh.write(header)
    log_fh.flush()

    print(f"# SNIPEWINS run_filtered.py started; full log → {LOG_PATH.name}")
    print(f"# Showing only funnel tags below; press Ctrl+C to stop.\n")
    sys.stdout.flush()

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(HERE),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"},
        )
    except FileNotFoundError:
        print("ERROR: could not start streamlit. Try `pip install streamlit`.", file=sys.stderr)
        log_fh.close()
        return 2

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            log_fh.write(line)            # full log gets every line
            if _line_matches_filter(line):
                sys.stdout.write(line)    # terminal gets only filtered lines
                sys.stdout.flush()
        proc.wait()
        return proc.returncode or 0
    except KeyboardInterrupt:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        return 130
    finally:
        try:
            log_fh.write(f"\n# SNIPEWINS run ended {datetime.now().isoformat(timespec='seconds')}\n")
        except Exception:
            pass
        log_fh.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
