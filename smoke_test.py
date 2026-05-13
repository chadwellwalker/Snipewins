"""
smoke_test.py — pre-ship sanity check for the SnipeWins engine.

Why this exists:
    Before any "ship" event (sharing the app with a beta user, deploying a
    fix, kicking off a marketing push) you want one command that proves the
    engine still produces deals end-to-end. This script does that.

What it checks (each line of output is one check):
    [IMPORT]      Engine module imports without SyntaxError or ImportError.
    [SCAN]        fetch_ending_soon_deals() returns a (deals, meta) tuple.
    [TYPES]       Return shape: list of dicts, dict.
    [META_KEYS]   meta has the keys downstream consumers depend on.
    [DEAL_COUNT]  Engine produced ≥1 row in valuation.
    [DEAL_CLASS]  At least one row has a non-empty deal_class.
    [PREPARE]     PREPARE handoff fired and rows reached valuation.
    [NO_TRACEBACK] No Python traceback in the captured log.
    [SUMMARY]     PASS / FAIL plus duration.

Usage:
    python smoke_test.py

    Exits 0 on PASS, non-zero (and prints "FAIL: <reason>") on any failed
    check. Captures full engine output to last_smoke.log.

This script does NOT modify any engine code. It only imports the engine
and calls its public entry point.
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path


HERE = Path(__file__).parent
LOG_PATH = HERE / "last_smoke.log"


class _Tee:
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


def _check(label: str, condition: bool, detail: str = "") -> bool:
    mark = "OK  " if condition else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"[SMOKE] [{mark}] {label}{suffix}", flush=True)
    return condition


def main() -> int:
    os.chdir(HERE)
    sys.path.insert(0, str(HERE))

    log_fh = LOG_PATH.open("w", encoding="utf-8", errors="replace", buffering=1)
    log_fh.write(
        f"# smoke_test started {datetime.now().isoformat(timespec='seconds')}\n"
        f"# python: {sys.executable}\n\n"
    )
    log_fh.flush()

    real_stdout = sys.stdout
    real_stderr = sys.stderr
    sys.stdout = _Tee(real_stdout, log_fh)
    sys.stderr = _Tee(real_stderr, log_fh)

    started = time.time()
    failures: list = []

    def fail(label: str, detail: str = ""):
        failures.append((label, detail))

    # ── Check 1: import ────────────────────────────────────────────────────
    try:
        import ending_soon_engine as ese
        if not _check("IMPORT", True, "ending_soon_engine loaded"):
            fail("IMPORT", "module did not load")
    except Exception as exc:
        _check("IMPORT", False, f"{type(exc).__name__}: {exc}")
        fail("IMPORT", f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
        return _finish(failures, started, log_fh, real_stdout, real_stderr)

    # ── Check 2: scan returns tuple ────────────────────────────────────────
    try:
        result = ese.fetch_ending_soon_deals(force_refresh=True, time_window_hours=3.0)
    except Exception as exc:
        _check("SCAN", False, f"raised {type(exc).__name__}: {exc}")
        fail("SCAN", f"raised {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return _finish(failures, started, log_fh, real_stdout, real_stderr)

    if not _check("SCAN", isinstance(result, tuple) and len(result) == 2,
                  f"got {type(result).__name__}, len={len(result) if hasattr(result, '__len__') else 'n/a'}"):
        fail("SCAN", "return is not a 2-tuple")
        return _finish(failures, started, log_fh, real_stdout, real_stderr)

    deals, meta = result

    # ── Check 3: types ─────────────────────────────────────────────────────
    types_ok = isinstance(deals, list) and isinstance(meta, dict)
    if not _check("TYPES", types_ok,
                  f"deals={type(deals).__name__}, meta={type(meta).__name__}"):
        fail("TYPES", "deals must be list, meta must be dict")
        return _finish(failures, started, log_fh, real_stdout, real_stderr)

    # ── Check 4: meta has expected keys ────────────────────────────────────
    expected_meta_keys = {
        "fetched_at", "total_queries", "displayed_count",
        "auction_feed_count", "rows_passed_to_valuation", "status",
    }
    missing_keys = expected_meta_keys - set(meta.keys())
    if not _check("META_KEYS", not missing_keys,
                  "missing: " + ", ".join(sorted(missing_keys)) if missing_keys else "all required keys present"):
        fail("META_KEYS", f"missing keys: {sorted(missing_keys)}")

    # ── Check 5: at least one row reached valuation ────────────────────────
    rows_to_valuation = int(meta.get("rows_passed_to_valuation") or 0)
    if not _check("DEAL_COUNT", rows_to_valuation >= 1,
                  f"rows_passed_to_valuation={rows_to_valuation}"):
        fail("DEAL_COUNT", "no rows reached valuation — engine produced nothing this cycle")

    # ── Check 6: at least one row has a deal_class ─────────────────────────
    classed = [d for d in deals if str(d.get("deal_class") or "").strip()]
    if not _check("DEAL_CLASS", len(classed) >= 1 or rows_to_valuation == 0,
                  f"{len(classed)} of {len(deals)} rows have deal_class"):
        fail("DEAL_CLASS", "deals returned but none have a deal_class")

    # ── Check 7: PREPARE handoff fired ─────────────────────────────────────
    log_text = ""
    try:
        # Re-read what we've written so far to look for the trace markers.
        log_fh.flush()
        log_text = LOG_PATH.read_text(encoding="utf-8", errors="replace")
    except Exception:
        pass
    prepare_handoff_count = log_text.count("[PREPARE_HANDOFF_TRACE]")
    valuation_start_count = log_text.count("[ENGINE_STAGE] stage=valuation_start")
    if not _check("PREPARE", prepare_handoff_count >= 3 and valuation_start_count >= 1,
                  f"PREPARE_HANDOFF_TRACE={prepare_handoff_count}, valuation_start={valuation_start_count}"):
        fail("PREPARE", f"expected ≥3 PREPARE_HANDOFF_TRACE blocks and ≥1 valuation_start; "
                       f"got {prepare_handoff_count} and {valuation_start_count}")

    # ── Check 8: no traceback in captured output ───────────────────────────
    has_traceback = "Traceback (most recent call last)" in log_text
    if not _check("NO_TRACEBACK", not has_traceback,
                  "tracebacks present in log" if has_traceback else "no tracebacks"):
        fail("NO_TRACEBACK", "engine raised at least one exception during the scan")

    return _finish(failures, started, log_fh, real_stdout, real_stderr)


def _finish(failures, started, log_fh, real_stdout, real_stderr) -> int:
    duration = round(time.time() - started, 1)
    if failures:
        print(f"\n[SMOKE] [SUMMARY] FAIL ({len(failures)} check(s)) — duration={duration}s", flush=True)
        for label, detail in failures:
            print(f"[SMOKE]   - {label}: {detail}", flush=True)
        rc = 1
    else:
        print(f"\n[SMOKE] [SUMMARY] PASS — duration={duration}s", flush=True)
        rc = 0

    sys.stdout = real_stdout
    sys.stderr = real_stderr
    try:
        log_fh.flush()
        log_fh.close()
    except Exception:
        pass
    print(f"[smoke_test] log written to {LOG_PATH}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
