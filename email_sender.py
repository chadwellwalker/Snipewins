"""
email_sender.py — Outbound transactional email for SnipeWins.

Backed by Resend (resend.com) — clean modern API, generous free tier
(100 emails/day forever, 3000/month), and supports custom domain so
mail comes FROM hello@snipewins.com instead of an obvious 3rd-party
forwarder address.

Dev-mode fallback: if RESEND_API_KEY isn't set, every send() call just
prints the magic link to stdout and returns success. That means we can
build and test the entire trial flow before Resend is configured — the
"email" appears in the supervisor log instead of an inbox.

What you (the operator) need to do once, in Resend:
    1. Sign up at https://resend.com (free).
    2. Add and verify snipewins.com as a sending domain. Resend will give
       you 3 DNS records (TXT for SPF, TXT for DKIM, MX) to add at
       Cloudflare DNS. Add them; verification completes in a few minutes.
    3. Create an API key from the Resend dashboard.
    4. Set the env var RESEND_API_KEY=re_xxxxxx before running the app.
       (On Windows: setx RESEND_API_KEY "re_xxxxxx" then restart your
       shell; or edit it into the supervisor's env at boot.)

Once the key is present and the domain is verified, send_magic_link()
sends real email. Until then it falls back to print-to-console so we
can develop end-to-end.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional


# ── Configuration ──────────────────────────────────────────────────────────

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
# The FROM address. Must be on a verified domain in Resend. We default to
# hello@snipewins.com; can be overridden by env var for testing.
FROM_ADDRESS   = os.environ.get(
    "SNIPEWINS_EMAIL_FROM",
    "SnipeWins <hello@snipewins.com>",
)
# The reply-to address — where users hit Reply land. We use the same as FROM
# for v1; later this can point at a support inbox.
REPLY_TO       = os.environ.get(
    "SNIPEWINS_EMAIL_REPLY_TO",
    "hello@snipewins.com",
)

RESEND_API_URL = "https://api.resend.com/emails"


# ── Public API ─────────────────────────────────────────────────────────────

def send_magic_link(email: str, magic_link_url: str) -> bool:
    """Send the magic-link email that grants the 10-minute trial.

    Returns True if the email was accepted by Resend (or successfully
    printed to console in dev mode). Returns False if Resend rejected the
    send (bad API key, unverified domain, etc.). Caller should NOT retry
    on False — log it and surface "we couldn't send the email" to the user
    so they can hit the form again.
    """
    if not email or not magic_link_url:
        return False

    subject = "Your SnipeWins trial is ready"
    html_body = _build_magic_link_html(magic_link_url)
    text_body = _build_magic_link_text(magic_link_url)

    if not RESEND_API_KEY:
        # Dev mode — print the magic link so we can click-test without Resend.
        print(
            f"\n[email_sender][DEV-MODE] No RESEND_API_KEY set. Would have sent:\n"
            f"  to:        {email}\n"
            f"  from:      {FROM_ADDRESS}\n"
            f"  subject:   {subject}\n"
            f"  magic url: {magic_link_url}\n"
        )
        return True

    return _send_via_resend(
        to=email,
        subject=subject,
        html=html_body,
        text=text_body,
    )


# ── Internals ──────────────────────────────────────────────────────────────

def _send_via_resend(*, to: str, subject: str, html: str, text: str) -> bool:
    """POST to Resend's REST endpoint. Returns True on 2xx, False otherwise.
    Uses urllib so we don't add `requests` as a dependency for this one call."""
    payload = {
        "from":     FROM_ADDRESS,
        "to":       [to],
        "subject":  subject,
        "html":     html,
        "text":     text,
        "reply_to": REPLY_TO,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        RESEND_API_URL,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type":  "application/json",
            # USER-AGENT-FIX 2026-05-13: Resend's API is behind Cloudflare.
            # The default Python urllib User-Agent ("Python-urllib/3.x") is
            # on Cloudflare's bot-detection blocklist and returns a 403
            # with error code 1010 before the request ever reaches Resend.
            # A proper browser-style UA bypasses it. Identifying as our own
            # app (SnipeWins) keeps it honest while satisfying the WAF.
            "User-Agent":    "SnipeWins/1.0 (Mozilla/5.0; +https://snipewins.com)",
            "Accept":        "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.getcode()
            body = resp.read().decode("utf-8", errors="ignore")[:500]
            if 200 <= status < 300:
                print(f"[email_sender] sent to={to} resend_status={status}")
                return True
            print(f"[email_sender] resend non-2xx status={status} body={body}")
            return False
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="ignore")[:500]
        except Exception:
            pass
        print(f"[email_sender] resend HTTPError code={exc.code} body={body}")
        return False
    except Exception as exc:
        print(f"[email_sender] resend exception type={type(exc).__name__} msg={str(exc)[:200]}")
        return False


def _build_magic_link_html(magic_link_url: str) -> str:
    """The actual email body, HTML. Single black button on a clean off-black
    background — matches the dashboard's aesthetic so the brand carries
    through. Keep this lightweight — heavy CSS breaks in Outlook etc."""
    return f"""\
<!DOCTYPE html>
<html>
  <body style="margin:0;padding:0;background:#0a0a0a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,Helvetica,Arial,sans-serif;color:#fafafa;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0a0a0a;">
      <tr>
        <td align="center" style="padding:40px 20px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;background:#161616;border-radius:16px;border:1px solid rgba(148,163,184,0.10);">
            <tr>
              <td style="padding:36px 32px;">
                <div style="font-size:11px;font-weight:600;letter-spacing:0.18em;color:#4ade80;text-transform:uppercase;margin-bottom:18px;">SnipeWins</div>
                <h1 style="margin:0 0 16px 0;font-size:24px;font-weight:700;color:#fafafa;line-height:1.25;">Your trial is ready.</h1>
                <p style="margin:0 0 24px 0;font-size:15px;line-height:1.5;color:#b0b0b0;">
                  Click the button below to open your SnipeWins dashboard. Your 10-minute clock starts when you click. Make it count.
                </p>
                <p style="margin:0 0 28px 0;">
                  <a href="{magic_link_url}" style="display:inline-block;padding:14px 28px;background:#4ade80;color:#0a0a0a;font-weight:700;font-size:15px;border-radius:10px;text-decoration:none;">Open my dashboard →</a>
                </p>
                <p style="margin:0 0 8px 0;font-size:13px;color:#888;">Or paste this link into your browser:</p>
                <p style="margin:0 0 24px 0;font-size:12px;color:#60a5fa;word-break:break-all;">{magic_link_url}</p>
                <p style="margin:24px 0 0 0;padding-top:20px;border-top:1px solid rgba(148,163,184,0.10);font-size:12px;color:#666;line-height:1.5;">
                  This link is single-use and expires in 24 hours. After your 10-minute trial you'll see two options: lock in the founder annual rate, or start a 7-day trial with card.
                </p>
              </td>
            </tr>
          </table>
          <div style="margin-top:18px;font-size:11px;color:#666;">© 2026 SnipeWins · hello@snipewins.com</div>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def _build_magic_link_text(magic_link_url: str) -> str:
    """Plain-text fallback for clients that strip HTML (and for spam filters
    that downscore HTML-only sends)."""
    return f"""\
Your SnipeWins trial is ready.

Open your dashboard:
{magic_link_url}

Your 10-minute clock starts when you click. After it ends you'll see two
options: lock in the founder annual rate, or start a 7-day trial with card.

This link is single-use and expires in 24 hours.

—
SnipeWins · hello@snipewins.com
"""


# ── CLI for testing ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("usage: python email_sender.py <to_email> <magic_link_url>")
        sys.exit(2)
    ok = send_magic_link(sys.argv[1], sys.argv[2])
    print("sent ok" if ok else "send failed")
    sys.exit(0 if ok else 1)
