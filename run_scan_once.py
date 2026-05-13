"""
run_scan_once.py — fire one headless scan and tee everything to last_scan.log.

Why this exists:
    The Streamlit UI is the normal way to run a scan, but it requires clicking.
    scan_scheduler.trigger_now() only flips a state flag and depends on the
    scheduler thread already running. This script just calls
    fetch_ending_soon_deals(force_refresh=True) directly, captures all stdout
    and stderr to last_scan.log, and exits when the scan finishes.

Usage (Windows / Mac / Linux), from this folder:
    python run_scan_once.py

When it returns, last_scan.log contains the full output of one scan,
including all [PREPARE_HANDOFF_TRACE] / [PREPARE_DROP] / [ENGINE_STAGE] lines.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path


HERE = Path(__file__).parent
LOG_PATH = HERE / "last_scan.log"


class _Tee:
    """Write to two streams at once (terminal + log file)."""

    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            try:
                s.write(data)
            except Exception:
                pass

    def flush(self):
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass


# PERF — drop trace-level noise (SUBSET_PARSE_RESULT, SERIAL_PARSE, etc.)
# from the captured log unless SNIPEWINS_VERBOSE=1. ~80% reduction in log
# volume on a typical valuation. Fully reversible — set the env var or
# revert this import to use _Tee instead of FilteringTee below.
try:
    from log_filter import FilteringTee as _PreferredTee
except Exception:
    _PreferredTee = _Tee


def main() -> int:
    # Make sure the engine can import everything it needs from this folder.
    os.chdir(HERE)
    sys.path.insert(0, str(HERE))

    log_fh = LOG_PATH.open("w", encoding="utf-8", errors="replace", buffering=1)
    log_fh.write(
        f"# run_scan_once started {datetime.now().isoformat(timespec='seconds')}\n"
        f"# cwd: {HERE}\n"
        f"# python: {sys.executable}\n\n"
    )
    log_fh.flush()

    real_stdout = sys.stdout
    real_stderr = sys.stderr
    sys.stdout = _PreferredTee(real_stdout, log_fh)
    sys.stderr = _PreferredTee(real_stderr, log_fh)

    try:
        print("[run_scan_once] importing ending_soon_engine ...", flush=True)
        import ending_soon_engine as ese

        print("[run_scan_once] calling fetch_ending_soon_deals(force_refresh=True, time_window_hours=3.0) ...", flush=True)
        deals, meta = ese.fetch_ending_soon_deals(
            force_refresh=True,
            time_window_hours=3.0,
        )

        print(
            f"[run_scan_once] DONE — deals={len(deals)} "
            f"meta_keys={list((meta or {}).keys())[:12]}",
            flush=True,
        )
        return 0
    except SystemExit as exc:
        print(f"[run_scan_once] SystemExit: {exc}", flush=True)
        return int(exc.code or 0)
    except Exception as exc:
        import traceback
        print(f"[run_scan_once] ERROR: {type(exc).__name__}: {exc}", flush=True)
        traceback.print_exc()
        return 1
    finally:
        sys.stdout = real_stdout
        sys.stderr = real_stderr
        try:
            log_fh.flush()
            log_fh.close()
        except Exception:
            pass
        print(f"[run_scan_once] log written to {LOG_PATH}")


if __name__ == "__main__":
    sys.exit(main())
