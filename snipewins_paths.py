"""
snipewins_paths.py — one place to resolve where runtime state files live.

On Render, the app's working directory is ephemeral: every deploy wipes it,
which erases the discovered auction/BIN pools and the daily-budget counter.
That makes the board go empty after each deploy and lets the per-lane budget
caps reset (so near_end over-spends). The fix is to keep that state on a
persistent disk.

Set ONE env var to make all state persist:
    SNIPEWINS_DATA_DIR=/var/data      (point it at your Render persistent disk mount)

Per-file env vars (SNIPEWINS_AUCTION_POOL_PATH, SNIPEWINS_BIN_POOL_PATH,
SNIPEWINS_DAILY_BUDGET_PATH, SNIPEWINS_NEAR_END_STATE_PATH) still override
individually if set. If neither is set, files fall back to the repo dir
(fine for local dev).
"""
from __future__ import annotations

import os
from pathlib import Path

_HERE = Path(__file__).parent


def data_dir() -> Path:
    """Persistent state directory if SNIPEWINS_DATA_DIR is set and writable,
    else the repo directory (local-dev fallback)."""
    d = os.environ.get("SNIPEWINS_DATA_DIR")
    if d:
        p = Path(d)
        try:
            p.mkdir(parents=True, exist_ok=True)
            # confirm writable
            _t = p / ".write_test"
            _t.write_text("ok", encoding="utf-8")
            _t.unlink()
            return p
        except Exception:
            pass
    return _HERE


def state_path(env_var: str, filename: str) -> Path:
    """Resolve a state file: explicit per-file env var wins, then the shared
    data dir, then the repo dir."""
    explicit = os.environ.get(env_var)
    if explicit:
        return Path(explicit)
    return data_dir() / filename
