"""
run_app.py — runs Streamlit and saves all output to last_scan.log.

Why this exists:
    Right now you screenshot the terminal and paste it. That's slow. This
    wrapper runs your app exactly the same way, but ALSO saves every line of
    output to last_scan.log in this folder. After a scan, you (or Claude or
    diag.py) can read that file directly — no screenshots needed.

How to use it (Windows / Mac / Linux):
    From a terminal opened in the "Python Coding" folder:

        python run_app.py

    The app starts. Click around in your browser as normal. Every line that
    would have appeared in the terminal is also written to last_scan.log.

    When you're done diagnosing, Ctrl-C in the terminal to stop.

What runs by default:
    streamlit run streamlit_app.py
    (any extra arguments you pass are appended)

Examples:
    python run_app.py
    python run_app.py --server.port 8502
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List


HERE = Path(__file__).parent
LOG_PATH = HERE / "last_scan.log"


def _bootstrap_streamlit_secrets() -> None:
    """OAUTH-BOOTSTRAP-2026-05-13: write .streamlit/secrets.toml from env
    vars before Streamlit boots. This is how Streamlit's native OIDC
    auth (st.login / st.user) reads its config — and we cannot commit
    the real secrets to git, so they live in Render env vars and we
    materialize them to disk at startup.

    Required env vars (if any missing, Google sign-in is silently skipped
    and the existing email+password flow continues to work):
      - GOOGLE_OAUTH_CLIENT_ID
      - GOOGLE_OAUTH_CLIENT_SECRET
      - STREAMLIT_COOKIE_SECRET (any random ≥32-char string)

    Optional:
      - STREAMLIT_REDIRECT_URI (defaults to https://app.snipewins.com/oauth2callback)
    """
    client_id     = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    cookie_secret = os.environ.get("STREAMLIT_COOKIE_SECRET")
    redirect_uri  = os.environ.get(
        "STREAMLIT_REDIRECT_URI",
        "https://app.snipewins.com/oauth2callback",
    )
    if not (client_id and client_secret and cookie_secret):
        print("[OAUTH] Google sign-in env vars not set, skipping secrets.toml")
        return
    secrets_dir  = HERE / ".streamlit"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    secrets_file = secrets_dir / "secrets.toml"
    # Stay alphabetically organized — Streamlit reads the file as TOML and
    # doesn't care about ordering, but it's easier to debug.
    content = (
        '[auth]\n'
        f'redirect_uri  = "{redirect_uri}"\n'
        f'cookie_secret = "{cookie_secret}"\n'
        '\n'
        '[auth.google]\n'
        f'client_id            = "{client_id}"\n'
        f'client_secret        = "{client_secret}"\n'
        'server_metadata_url  = "https://accounts.google.com/.well-known/openid-configuration"\n'
    )
    secrets_file.write_text(content, encoding="utf-8")
    print(f"[OAUTH] wrote {secrets_file} for Google sign-in (redirect_uri={redirect_uri})")


def _resolve_streamlit_command() -> List[str]:
    """Locate streamlit. Prefer `python -m streamlit run` for portability.

    DEPLOY-2026-05-13: read $PORT from env so the same script works on
    both your local machine (no PORT set → 8501) and Render (PORT injected
    by the platform). Also bind to 0.0.0.0 when deployed so the platform's
    load balancer can route external traffic in; on local we stay on
    localhost since binding to 0.0.0.0 unnecessarily exposes the dev
    server to your LAN.
    """
    deploy_port = os.environ.get("PORT")
    port = deploy_port or "8501"
    address = "0.0.0.0" if deploy_port else "localhost"
    cmd = [
        sys.executable, "-m", "streamlit", "run", "streamlit_app.py",
        "--server.port", port,
        "--server.address", address,
        # Headless suppresses Streamlit's "would you like to share?" / browser
        # auto-open prompts that don't apply in a containerized deploy.
        "--server.headless", "true",
    ]
    return cmd


def main(argv: List[str]) -> int:
    # Materialize Streamlit's OIDC secrets.toml from env vars before
    # spawning Streamlit. Idempotent (overwrites previous file each boot).
    _bootstrap_streamlit_secrets()
    cmd = _resolve_streamlit_command() + argv
    # Truncate / open the log fresh for this run.
    try:
        log_fh = LOG_PATH.open("w", encoding="utf-8", errors="replace", buffering=1)  # line buffered
    except Exception as exc:
        print(f"ERROR: could not open {LOG_PATH}: {exc}", file=sys.stderr)
        return 2

    header = (
        f"# SNIPEWINS run started {datetime.now().isoformat(timespec='seconds')}\n"
        f"# command: {' '.join(cmd)}\n"
        f"# cwd: {HERE}\n"
        f"# All output below is mirrored to your terminal.\n\n"
    )
    log_fh.write(header)
    log_fh.flush()
    sys.stdout.write(header)
    sys.stdout.flush()

    # Spawn streamlit, merge stderr into stdout, stream line-by-line to console + log.
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(HERE),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,             # line buffered
            universal_newlines=True,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"},
        )
    except FileNotFoundError:
        print(
            "ERROR: could not start streamlit. Install it with `pip install streamlit`.",
            file=sys.stderr,
        )
        log_fh.close()
        return 2

    # PERF — filter trace-level noise out of both terminal and log unless
    # SNIPEWINS_VERBOSE=1. Reduces typical scan log volume by ~80%. Engine
    # behavior is unchanged; we just decline to write the noisiest lines.
    try:
        from log_filter import is_noisy_line, is_verbose_mode
        _filter_active = not is_verbose_mode()
    except Exception:
        is_noisy_line = lambda _line: False
        _filter_active = False

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if _filter_active and is_noisy_line(line):
                # Drop this line from terminal AND log. Engine still printed
                # it — we just suppress it here.
                continue
            sys.stdout.write(line)
            sys.stdout.flush()
            log_fh.write(line)
            # Flush every line so Ctrl-C doesn't lose the tail.
        proc.wait()
        return proc.returncode or 0
    except KeyboardInterrupt:
        # Polite shutdown — give streamlit a moment to clean up, then kill if needed.
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        return 130
    finally:
        try:
            log_fh.write(
                f"\n# SNIPEWINS run ended {datetime.now().isoformat(timespec='seconds')}\n"
            )
        except Exception:
            pass
        log_fh.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
