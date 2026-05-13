"""
supervisor.py — Beach mode for SnipeWins.

Launches and watches the three background processes that make up the
24h pipeline. If any of them die or crash, the supervisor restarts
them with exponential backoff. Output from each is line-prefixed and
streamed to a single terminal so you can glance at one window and
see everything that's happening.

Managed processes:
    [POOL]   python daily_pool.py --loop
             Rebuilds the auction pool every hour. New cards flow in,
             stale ones get pruned, sport-suppression + chase_rules
             gates fire on every cycle.

    [WORKER] python valuation_worker.py --loop
             Computes MVs continuously. Wakes every 60s, processes
             a batch of unvalued rows, sleeps. Hits the relaxation
             ladder when exact comps aren't found.

    [APP]    python run_app.py
             Streamlit dashboard. Reads daily_pool.json on every
             user interaction so the data is always fresh.

Run:
    python supervisor.py

Optional flags:
    --pool-interval N      seconds between daily_pool cycles (default 3600)
    --no-pool              skip launching the pool fetcher
    --no-worker            skip launching the valuation worker
    --no-app               skip launching the Streamlit app

Stop:
    Ctrl-C — supervisor terminates all child processes cleanly.

Caveats:
    - Your PC must stay on. Disable sleep in Power Settings.
    - All three processes share the same Python environment. If you
      need different envs per process you'd run them separately.
    - For true 24/7 production, deploy to a cloud VM. This module is
      for desktop / personal use.
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


HERE = Path(__file__).parent
LOG_FILE = HERE / "supervisor.log"


# ── .env loader ────────────────────────────────────────────────────────────

def _load_dotenv() -> int:
    """Load a `.env` file into os.environ at supervisor startup so all
    child processes inherit the keys. Stdlib-only — we don't pull in the
    `python-dotenv` package to keep the deploy surface minimal.

    File format: shell-style `KEY=VALUE` lines, one per line. Blank lines
    and lines starting with `#` are ignored. Surrounding whitespace and
    quotes are stripped from the value.

    Existing env vars take precedence (so the shell can still override
    .env). Returns the count of new vars loaded.
    """
    env_path = HERE / ".env"
    if not env_path.exists():
        return 0
    loaded = 0
    try:
        for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip("'").strip('"')
            if not k:
                continue
            # Don't clobber values the shell already set — that gives the
            # operator an escape hatch to override .env without editing it.
            if k in os.environ and os.environ[k]:
                continue
            os.environ[k] = v
            loaded += 1
    except Exception as exc:
        # Don't fail supervisor startup over a malformed .env. Log and move on.
        try:
            print(f"[supervisor] WARN: .env load failed: {type(exc).__name__}: {exc}")
        except Exception:
            pass
    return loaded


# ── Daily log rotation ───────────────────────────────────────────────────────

def _rotate_log_if_new_day() -> None:
    """ROTATE-2026-05-12: keep supervisor.log digestible by rolling it over
    each calendar day. Renames the existing supervisor.log to
    supervisor.log.YYYY-MM-DD (where the date is the existing log's start
    date), then a fresh empty supervisor.log starts collecting today's output.
    Also sweeps rotated logs older than 7 days. Idempotent — running on the
    same day is a no-op."""
    if not LOG_FILE.exists():
        return
    try:
        # Read just enough of the existing log to find its first-line date.
        # Old log format: "[20:39:23] [SUPER  ] supervisor starting" — no date.
        # New format (post-rotation): "# day=YYYY-MM-DD" stamp on first line.
        # Fallback: use file mtime → calendar date.
        with LOG_FILE.open("r", encoding="utf-8", errors="ignore") as _fh:
            _first = _fh.readline().strip()
        _log_date: Optional[str] = None
        if _first.startswith("# day="):
            _log_date = _first[len("# day="):].strip()[:10]
        if not _log_date:
            try:
                _log_date = datetime.fromtimestamp(LOG_FILE.stat().st_mtime).strftime("%Y-%m-%d")
            except Exception:
                _log_date = None
        _today = datetime.now().strftime("%Y-%m-%d")
        if _log_date and _log_date != _today:
            _archive = HERE / f"supervisor.log.{_log_date}"
            # Don't overwrite a previously-rotated archive of the same day;
            # append a counter suffix instead.
            _counter = 0
            while _archive.exists():
                _counter += 1
                _archive = HERE / f"supervisor.log.{_log_date}.{_counter}"
            LOG_FILE.rename(_archive)
    except Exception:
        # Rotation is convenience; never block supervisor startup if it fails.
        pass
    # Stamp the new (or freshly-created) log with today's date as a header so
    # next-day rotation can recognize it without relying on file mtime.
    try:
        with LOG_FILE.open("a", encoding="utf-8", errors="replace") as _fh:
            _fh.write(f"# day={datetime.now().strftime('%Y-%m-%d')}\n")
    except Exception:
        pass
    # Sweep: drop rotated archives older than 7 days so the folder doesn't
    # accumulate hundreds of multi-million-line files.
    try:
        _cutoff = time.time() - (7 * 86400)
        for _p in HERE.glob("supervisor.log.*"):
            try:
                if _p.stat().st_mtime < _cutoff:
                    _p.unlink()
            except Exception:
                pass
    except Exception:
        pass

# Process specs — each entry becomes one managed child process.
# `name` is the prefix shown in logs. `cmd` is the argv list.
_PYTHON = sys.executable


def _build_process_specs(args) -> List[Dict[str, Any]]:
    """Build the list of managed processes based on CLI flags."""
    pool_cmd = [_PYTHON, "daily_pool.py", "--loop"]
    if args.pool_interval and args.pool_interval > 0:
        pool_cmd.extend(["--interval", str(args.pool_interval)])

    bin_pool_cmd = [_PYTHON, "daily_bin_pool.py", "--loop"]
    if args.bin_interval and args.bin_interval > 0:
        bin_pool_cmd.extend(["--interval", str(args.bin_interval)])

    specs: List[Dict[str, Any]] = []
    if not args.no_pool:
        specs.append({
            "name":          "POOL",
            "cmd":           pool_cmd,
            "restart_count": 0,
            "last_started":  0.0,
            "process":       None,
        })
    if not args.no_bin:
        specs.append({
            "name":          "BIN",
            "cmd":           bin_pool_cmd,
            "restart_count": 0,
            "last_started":  0.0,
            "process":       None,
        })
    if not args.no_worker:
        specs.append({
            "name":          "WORKER",
            "cmd":           [_PYTHON, "valuation_worker.py", "--loop"],
            "restart_count": 0,
            "last_started":  0.0,
            "process":       None,
        })
    if not args.no_app:
        specs.append({
            "name":          "APP",
            "cmd":           [_PYTHON, "run_app.py"],
            "restart_count": 0,
            "last_started":  0.0,
            "process":       None,
        })
    return specs


# ── Output formatting ────────────────────────────────────────────────────

_log_lock = threading.Lock()


def _stamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _emit(label: str, line: str) -> None:
    """Thread-safe write to terminal + supervisor.log."""
    msg = f"[{_stamp()}] [{label:7}] {line.rstrip()}"
    with _log_lock:
        try:
            print(msg, flush=True)
        except Exception:
            pass
        try:
            with LOG_FILE.open("a", encoding="utf-8", errors="replace") as fh:
                fh.write(msg + "\n")
        except Exception:
            pass


def _supervisor(line: str) -> None:
    _emit("SUPER", line)


# ── Process management ───────────────────────────────────────────────────

def _start(spec: Dict[str, Any]) -> bool:
    """Spawn the child process. Returns True on success."""
    name = spec["name"]
    cmd  = spec["cmd"]
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
    except Exception as exc:
        _supervisor(f"failed to start {name}: {type(exc).__name__}: {exc}")
        return False
    spec["process"]       = proc
    spec["last_started"]  = time.time()
    spec["restart_count"] += 1
    _supervisor(f"started {name} (pid={proc.pid}, attempt #{spec['restart_count']})")
    # Spawn a reader thread for this child's stdout
    threading.Thread(
        target=_stream_reader,
        args=(name, proc),
        daemon=True,
    ).start()
    return True


def _stream_reader(name: str, proc: subprocess.Popen) -> None:
    """Read the child's stdout line by line and prefix-log each line."""
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            _emit(name, line)
    except Exception as exc:
        _supervisor(f"stream reader for {name} crashed: {type(exc).__name__}: {exc}")


def _restart_backoff_secs(spec: Dict[str, Any]) -> float:
    """How long to wait before restarting a crashed process. Exponential
    backoff capped at 60s so we don't spam restarts if a process is
    permanently broken."""
    n = spec["restart_count"]
    # 0 attempts → 0s, 1 → 5s, 2 → 10s, 3 → 20s, capped at 60
    if n <= 1:
        return 5.0
    if n <= 3:
        return 10.0 * (2 ** (n - 1))
    return 60.0


def _watchdog(specs: List[Dict[str, Any]]) -> None:
    """Main supervisor loop. Polls each child every 2 seconds. If a
    child has exited, schedules a restart with backoff. Returns when
    a Ctrl-C / shutdown signal is received."""
    _supervisor(f"watchdog online, watching {len(specs)} process(es)")
    while True:
        time.sleep(2.0)
        now = time.time()
        for spec in specs:
            proc: Optional[subprocess.Popen] = spec.get("process")
            if proc is None:
                # Never started or shutting down — try to start
                _start(spec)
                continue
            rc = proc.poll()
            if rc is None:
                # Still running
                continue
            # Process has exited
            _supervisor(f"{spec['name']} exited with code {rc}")
            spec["process"] = None
            # Wait through backoff before restarting
            backoff = _restart_backoff_secs(spec)
            if (now - spec["last_started"]) < backoff:
                continue
            _supervisor(f"restarting {spec['name']} (backoff={backoff:.0f}s)")
            _start(spec)


def _shutdown(specs: List[Dict[str, Any]]) -> None:
    """Terminate all managed processes."""
    _supervisor("shutdown requested — terminating children")
    for spec in specs:
        proc: Optional[subprocess.Popen] = spec.get("process")
        if proc is None:
            continue
        try:
            proc.terminate()
        except Exception:
            pass
    # Give them 5s to exit gracefully, then kill.
    deadline = time.time() + 5.0
    for spec in specs:
        proc = spec.get("process")
        if proc is None:
            continue
        remaining = max(0.1, deadline - time.time())
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:
                pass
        spec["process"] = None
    _supervisor("all children stopped")


# ── Entry point ──────────────────────────────────────────────────────────

def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="SnipeWins supervisor — watches the 24h pipeline and respawns crashed processes")
    parser.add_argument("--pool-interval", type=int, default=3600,
                        help="seconds between daily_pool (auction) cycles (default 3600 = 1 hour)")
    parser.add_argument("--bin-interval",  type=int, default=1800,
                        help="seconds between daily_bin_pool cycles (default 1800 = 30 minutes)")
    parser.add_argument("--no-pool",   action="store_true", help="skip daily_pool.py")
    parser.add_argument("--no-bin",    action="store_true", help="skip daily_bin_pool.py")
    parser.add_argument("--no-worker", action="store_true", help="skip valuation_worker.py")
    parser.add_argument("--no-app",    action="store_true", help="skip run_app.py")
    args = parser.parse_args(argv)

    # Load .env into the process environment BEFORE building specs or
    # spawning children — every child inherits these vars via subprocess.
    _n_loaded = _load_dotenv()

    specs = _build_process_specs(args)
    if not specs:
        _supervisor("no processes to manage (all skipped)")
        return 1

    # Rotate the prior day's supervisor.log out of the way before we start
    # appending today's lines. Idempotent — same-day restarts keep the
    # existing log intact and just continue appending.
    _rotate_log_if_new_day()
    if _n_loaded:
        _supervisor(f"loaded {_n_loaded} env vars from .env")

    _supervisor(
        f"supervisor starting "
        f"({', '.join(s['name'] for s in specs)}) — "
        f"pool interval {args.pool_interval}s"
    )
    _supervisor(f"log file: {LOG_FILE}")

    # Start all processes once
    for spec in specs:
        _start(spec)
        # Stagger startup by 2s so log lines don't interleave too badly on the
        # initial print burst from each child.
        time.sleep(2.0)

    # Watchdog loop runs forever until Ctrl-C
    try:
        _watchdog(specs)
    except KeyboardInterrupt:
        _shutdown(specs)
        return 130
    except Exception as exc:
        _supervisor(f"FATAL watchdog error: {type(exc).__name__}: {exc}")
        _shutdown(specs)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
