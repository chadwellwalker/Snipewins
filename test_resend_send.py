"""
test_resend_send.py — One-shot Resend connectivity test.

Sends a single "Hello World" email through the existing email_sender.py
module so we validate the full pipeline:
    1. .env loads RESEND_API_KEY correctly
    2. The key is valid (not revoked / typo-free)
    3. email_sender.py's urllib request works end-to-end
    4. The recipient inbox actually receives the email

Usage:
    python test_resend_send.py [recipient_email]

If no recipient is passed, defaults to the address baked into Resend's
own getting-started example (chadwellwalker@gmail.com). Edit below if
you want a different default.

IMPORTANT: Until snipewins.com is verified as a sending domain in Resend,
the FROM address has to be `onboarding@resend.dev` — that's Resend's
public test sender, no verification required. Once you verify your
domain, switch back to hello@snipewins.com (set in .env via
SNIPEWINS_EMAIL_FROM, or just rely on the email_sender.py default).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _load_env_for_test() -> None:
    """The supervisor normally loads .env; standalone scripts need to do
    it themselves. Same stdlib-only logic, abbreviated."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        print(f"[test_resend_send] WARN: .env not found at {env_path}")
        return
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip("'").strip('"')
        if k and k not in os.environ:
            os.environ[k] = v


def main() -> int:
    _load_env_for_test()

    # Sanity-check the API key is set.
    key = os.environ.get("RESEND_API_KEY", "").strip()
    if not key:
        print("[test_resend_send] ERROR: RESEND_API_KEY not set. Check your .env file.")
        return 2
    print(f"[test_resend_send] RESEND_API_KEY = {key[:7]}...{key[-4:]} (loaded OK)")

    # Recipient: CLI arg, else default.
    recipient = sys.argv[1] if len(sys.argv) > 1 else "chadwellwalker@gmail.com"
    print(f"[test_resend_send] sending test email to: {recipient}")

    # As of 2026-05-13 snipewins.com is verified in Resend, so we send
    # from hello@snipewins.com (the email_sender.py default). No FROM
    # override needed. If verification ever lapses, re-set:
    #   os.environ["SNIPEWINS_EMAIL_FROM"] = "SnipeWins <onboarding@resend.dev>"

    # Import email_sender AFTER setting env vars so its module-level config
    # reads the overrides we just applied.
    sys.path.insert(0, str(Path(__file__).parent))
    import email_sender

    # Use a real-looking magic link URL so the test email matches what a
    # production user would receive. The token here is bogus and won't
    # validate, but the email body / structure is identical to production.
    magic_link_url = "http://localhost:8501/?token=TEST_TOKEN_THIS_WILL_NOT_VALIDATE"
    ok = email_sender.send_magic_link(recipient, magic_link_url)

    if ok:
        print(f"[test_resend_send] SUCCESS — check {recipient}'s inbox")
        print(f"[test_resend_send] (may take 10-30 seconds to arrive)")
        return 0
    else:
        print("[test_resend_send] FAILED — see the [email_sender] log lines above")
        print("[test_resend_send] Common causes:")
        print("  - API key wrong / revoked")
        print("  - FROM address uses an unverified domain")
        print("  - Network issue / Resend service degraded")
        return 1


if __name__ == "__main__":
    sys.exit(main())
