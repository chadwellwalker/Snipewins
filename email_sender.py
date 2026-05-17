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


# ── Conversion sequence sends. EMAIL-CONVERSION-2026-05-15 ────────────────
# Four emails covering the highest-leverage conversion moments. Two
# transactional (fired by app code on specific events), two marketing
# (fired by email_drip.py sweeps). All four use the same visual DNA as
# send_magic_link above so users see one consistent SnipeWins brand.

def send_trial_expired(email: str) -> bool:
    """Transactional. Fire when a user's 10-minute trial ends and the
    paywall renders for the first time. Caller (trial_gate._render_paywall)
    must guard with a per-user 'sent' flag so we don't re-send on every
    paywall page view."""
    if not email:
        return False
    subject = "Your 10 minutes is up."
    if not RESEND_API_KEY:
        print(
            f"\n[email_sender][DEV-MODE] No RESEND_API_KEY set. send_trial_expired:\n"
            f"  to:      {email}\n  subject: {subject}\n"
        )
        return True
    return _send_via_resend(
        to=email, subject=subject,
        html=_build_trial_expired_html(),
        text=_build_trial_expired_text(),
    )


def send_welcome_paid(email: str) -> bool:
    """Transactional. Fire when Stripe checkout completes and the account
    flips to PAID. Sent from trial_gate._handle_stripe_return right after
    mark_as_paid. Guard with a per-user 'sent' flag."""
    if not email:
        return False
    subject = "You're in. Here's where to look first."
    if not RESEND_API_KEY:
        print(
            f"\n[email_sender][DEV-MODE] No RESEND_API_KEY set. send_welcome_paid:\n"
            f"  to:      {email}\n  subject: {subject}\n"
        )
        return True
    return _send_via_resend(
        to=email, subject=subject,
        html=_build_welcome_paid_html(),
        text=_build_welcome_paid_text(),
    )


def send_trial_followup(email: str) -> bool:
    """Marketing. Sent 48h after the trial expired if the user still
    hasn't paid AND has marketing_optin=True. Fired by email_drip sweeps."""
    if not email:
        return False
    subject = "Still thinking about it?"
    if not RESEND_API_KEY:
        print(
            f"\n[email_sender][DEV-MODE] No RESEND_API_KEY set. send_trial_followup:\n"
            f"  to:      {email}\n  subject: {subject}\n"
        )
        return True
    return _send_via_resend(
        to=email, subject=subject,
        html=_build_trial_followup_html(),
        text=_build_trial_followup_text(),
    )


def send_unverified_nudge(email: str, magic_link_url: str) -> bool:
    """Marketing-adjacent. Sent 24h after a user signed up but didn't
    click the verification link. Carries a freshly-minted magic_link_url
    so they can land directly in the trial flow."""
    if not email or not magic_link_url:
        return False
    subject = "Your trial is one click away."
    if not RESEND_API_KEY:
        print(
            f"\n[email_sender][DEV-MODE] No RESEND_API_KEY set. send_unverified_nudge:\n"
            f"  to:        {email}\n  subject:   {subject}\n  magic url: {magic_link_url}\n"
        )
        return True
    return _send_via_resend(
        to=email, subject=subject,
        html=_build_unverified_nudge_html(magic_link_url),
        text=_build_unverified_nudge_text(magic_link_url),
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


# ── Conversion-sequence template builders. EMAIL-CONVERSION-2026-05-15 ────

def _email_shell(*, kicker: str, kicker_color: str, headline: str, body_html: str) -> str:
    """Shared outer wrapper for all conversion emails. One shell, four
    different inner bodies — keeps the brand consistent without copy/pasting
    the layout boilerplate four times."""
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/></head>
<body style="margin:0;padding:0;background:#0a0a0a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,Helvetica,Arial,sans-serif;color:#fafafa;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0a0a0a;">
    <tr><td align="center" style="padding:40px 20px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;background:#161616;border-radius:16px;border:1px solid rgba(148,163,184,0.10);">
        <tr><td style="padding:36px 32px;">
          <div style="font-size:11px;font-weight:600;letter-spacing:0.18em;color:{kicker_color};text-transform:uppercase;margin-bottom:18px;">{kicker}</div>
          <h1 style="margin:0 0 16px 0;font-size:26px;font-weight:700;color:#fafafa;line-height:1.25;">{headline}</h1>
          {body_html}
        </td></tr>
      </table>
      <div style="margin-top:18px;font-size:11px;color:#666;">© 2026 SnipeWins · hello@snipewins.com</div>
    </td></tr>
  </table>
</body>
</html>"""


# ── Email 1: Trial expired (immediate, transactional) ────────────────────

def _build_trial_expired_html() -> str:
    body = """\
<p style="margin:0 0 18px 0;font-size:15px;line-height:1.55;color:#b0b0b0;">
  You just watched SnipeWins do in 10 minutes what takes most people hours of scrolling eBay: surface the cards priced under what they're worth, with the exact number to bid.
</p>
<p style="margin:0 0 26px 0;font-size:15px;line-height:1.55;color:#b0b0b0;">
  That feed doesn't stop. Every auction ending in the next 24 hours, comped against real sold listings, sorted by where the money actually is.
</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:18px;">
  <tr><td style="padding:0 0 6px 0;font-size:11px;font-weight:700;letter-spacing:0.10em;color:#4ade80;text-transform:uppercase;">FOUNDER RATE · $99/YEAR</td></tr>
  <tr><td style="padding:0 0 12px 0;font-size:13px;color:#888;">Normally $228/yr. Locked in for life. The first two wins pay for the year.</td></tr>
  <tr><td>
    <a href="https://snipewins.com/checkout/annual" style="display:inline-block;padding:13px 26px;background:#4ade80;color:#0a0a0a;font-weight:700;font-size:15px;border-radius:10px;text-decoration:none;">Lock in $99/year →</a>
  </td></tr>
</table>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:8px;padding-top:18px;border-top:1px solid rgba(148,163,184,0.10);">
  <tr><td style="padding:6px 0;font-size:11px;font-weight:700;letter-spacing:0.10em;color:#9ca3af;text-transform:uppercase;">MONTHLY · $29/MONTH</td></tr>
  <tr><td style="padding:0 0 12px 0;font-size:13px;color:#888;">Free for 7 days, card required. Cancel anytime in week one, $0 charged.</td></tr>
  <tr><td>
    <a href="https://snipewins.com/checkout/monthly" style="display:inline-block;padding:10px 22px;background:transparent;color:#fafafa;font-weight:600;font-size:14px;border-radius:10px;text-decoration:none;border:1px solid rgba(148,163,184,0.30);">Start 7-day free trial →</a>
  </td></tr>
</table>
<p style="margin:24px 0 0 0;font-size:12px;color:#666;line-height:1.5;">
  The next auction you're not watching ends in under an hour.
</p>"""
    return _email_shell(
        kicker="TRIAL ENDED", kicker_color="#facc15",
        headline="Your 10 minutes is up.", body_html=body,
    )


def _build_trial_expired_text() -> str:
    return """\
Your 10 minutes is up.

You just watched SnipeWins do in 10 minutes what takes most people hours of scrolling eBay: surface the cards priced under what they're worth, with the exact number to bid.

That feed doesn't stop. Every auction ending in the next 24 hours, comped against real sold listings, sorted by where the money actually is.

Two ways back in:

FOUNDER RATE · $99/year (normally $228). Locked in for life. The first two wins pay for the year.
→ https://snipewins.com/checkout/annual

MONTHLY · $29/month. Free for 7 days, card required. Cancel anytime in week one, $0 charged.
→ https://snipewins.com/checkout/monthly

The next auction you're not watching ends in under an hour.

—
SnipeWins · hello@snipewins.com
"""


# ── Email 2: Trial expired follow-up (+2 days, marketing) ────────────────

def _build_trial_followup_html() -> str:
    body = """\
<p style="margin:0 0 18px 0;font-size:15px;line-height:1.55;color:#b0b0b0;">
  You saw the dashboard two days ago. The founder rate is still $99 because we're early. That number goes to $228 once we hit our launch cap.
</p>
<p style="margin:0 0 26px 0;font-size:15px;line-height:1.55;color:#b0b0b0;">
  What you're paying for: every auction ending in the next 24 hours, comped against real sold listings, with the exact target bid. No bidding wars, no FOMO scrolling, no overpaying. Two or three typical wins clear the year.
</p>
<table role="presentation" cellpadding="0" cellspacing="0" style="margin-bottom:18px;">
  <tr><td>
    <a href="https://snipewins.com/checkout/annual" style="display:inline-block;padding:14px 28px;background:#4ade80;color:#0a0a0a;font-weight:700;font-size:15px;border-radius:10px;text-decoration:none;">Lock in $99/year →</a>
  </td></tr>
</table>
<p style="margin:0 0 8px 0;font-size:13px;color:#888;">
  Not ready for annual? Start the 7-day monthly trial. Card required, $0 charged in week one.
</p>
<p style="margin:0 0 0 0;font-size:13px;">
  <a href="https://snipewins.com/checkout/monthly" style="color:#60a5fa;text-decoration:none;">Start 7-day monthly trial →</a>
</p>
<p style="margin:28px 0 0 0;padding-top:20px;border-top:1px solid rgba(148,163,184,0.10);font-size:12px;color:#666;line-height:1.5;">
  Manage email preferences in your <a href="https://app.snipewins.com/?account=1" style="color:#60a5fa;text-decoration:none;">account</a>. Reply with "stop" and we'll quit emailing.
</p>"""
    return _email_shell(
        kicker="FOUNDER RATE · STILL OPEN", kicker_color="#4ade80",
        headline="Still thinking about it?", body_html=body,
    )


def _build_trial_followup_text() -> str:
    return """\
Still thinking about it?

You saw the dashboard two days ago. The founder rate is still $99 because we're early. That number goes to $228 once we hit our launch cap.

What you're paying for: every auction ending in the next 24 hours, comped against real sold listings, with the exact target bid. No bidding wars, no FOMO scrolling, no overpaying. Two or three typical wins clear the year.

Lock in $99/year:
→ https://snipewins.com/checkout/annual

Not ready for annual? Start the 7-day monthly trial. Card required, $0 charged in week one:
→ https://snipewins.com/checkout/monthly

Manage email preferences: https://app.snipewins.com/?account=1
Reply with "stop" and we'll quit emailing.

—
SnipeWins · hello@snipewins.com
"""


# ── Email 3: Welcome after payment (transactional) ───────────────────────

def _build_welcome_paid_html() -> str:
    body = """\
<p style="margin:0 0 22px 0;font-size:15px;line-height:1.55;color:#b0b0b0;">
  Three minutes from now you can be on your first STRIKE. Here's the loop:
</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:22px;">
  <tr><td style="padding:10px 0;font-size:14px;color:#fafafa;line-height:1.5;">
    <strong style="color:#4ade80;">1. Ending Soon</strong> — the live feed of every relevant auction ending in the next 24 hours, sorted by how much under MV the current bid is. Look for green STRIKE badges.
  </td></tr>
  <tr><td style="padding:10px 0;font-size:14px;color:#fafafa;line-height:1.5;border-top:1px solid rgba(148,163,184,0.10);">
    <strong style="color:#3b82f6;">2. Steals</strong> — Buy-It-Now listings priced under MV, plus our Recommended Offer numbers for sellers who accept best offers.
  </td></tr>
  <tr><td style="padding:10px 0;font-size:14px;color:#fafafa;line-height:1.5;border-top:1px solid rgba(148,163,184,0.10);">
    <strong style="color:#facc15;">3. Add to Snipes</strong> — click the star on any card to track it. Mark Won when you take it down. Your ROI starts building in the Purchased tab.
  </td></tr>
</table>
<table role="presentation" cellpadding="0" cellspacing="0" style="margin-bottom:8px;">
  <tr><td>
    <a href="https://app.snipewins.com" style="display:inline-block;padding:14px 28px;background:#4ade80;color:#0a0a0a;font-weight:700;font-size:15px;border-radius:10px;text-decoration:none;">Open my dashboard →</a>
  </td></tr>
</table>
<p style="margin:28px 0 0 0;padding-top:20px;border-top:1px solid rgba(148,163,184,0.10);font-size:12px;color:#666;line-height:1.55;">
  Receipt and subscription details: <a href="https://app.snipewins.com/?account=1" style="color:#60a5fa;text-decoration:none;">Account page</a>. Hit reply on this email any time — every reply goes straight to me.
</p>"""
    return _email_shell(
        kicker="YOU'RE IN", kicker_color="#4ade80",
        headline="Welcome to SnipeWins.", body_html=body,
    )


def _build_welcome_paid_text() -> str:
    return """\
Welcome to SnipeWins.

Three minutes from now you can be on your first STRIKE. Here's the loop:

1. Ending Soon — the live feed of every relevant auction ending in the next 24 hours, sorted by how much under MV the current bid is. Look for green STRIKE badges.

2. Steals — Buy-It-Now listings priced under MV, plus our Recommended Offer numbers for sellers who accept best offers.

3. Add to Snipes — click the star on any card to track it. Mark Won when you take it down. Your ROI starts building in the Purchased tab.

Open your dashboard:
→ https://app.snipewins.com

Receipt and subscription: https://app.snipewins.com/?account=1
Hit reply on this email any time.

—
SnipeWins · hello@snipewins.com
"""


# ── Email 4: Captured-email nudge (verification unclicked, marketing) ────

def _build_unverified_nudge_html(magic_link_url: str) -> str:
    body = f"""\
<p style="margin:0 0 22px 0;font-size:15px;line-height:1.55;color:#b0b0b0;">
  You started signing up yesterday but didn't finish. Your 10-minute SnipeWins trial is still here — full access to every auction ending in the next 24 hours, every Steal, every comp, every target bid. No card.
</p>
<table role="presentation" cellpadding="0" cellspacing="0" style="margin-bottom:8px;">
  <tr><td>
    <a href="{magic_link_url}" style="display:inline-block;padding:14px 28px;background:#4ade80;color:#0a0a0a;font-weight:700;font-size:15px;border-radius:10px;text-decoration:none;">Start my 10-minute trial →</a>
  </td></tr>
</table>
<p style="margin:24px 0 0 0;font-size:12px;color:#666;line-height:1.55;">
  The clock starts when you click. If 10 minutes goes by and you don't see a card worth bidding on, the product isn't ready for you yet and you walk away. No charge, no email follow-ups.
</p>"""
    return _email_shell(
        kicker="YOUR TRIAL IS WAITING", kicker_color="#4ade80",
        headline="One click and you're in.", body_html=body,
    )


def _build_unverified_nudge_text(magic_link_url: str) -> str:
    return f"""\
One click and you're in.

You started signing up yesterday but didn't finish. Your 10-minute SnipeWins trial is still here — full access to every auction ending in the next 24 hours, every Steal, every comp, every target bid. No card.

Start your 10-minute trial:
→ {magic_link_url}

The clock starts when you click. If 10 minutes goes by and you don't see a card worth bidding on, the product isn't ready for you yet and you walk away. No charge, no email follow-ups.

—
SnipeWins · hello@snipewins.com
"""


# ── CLI for testing ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage:")
        print("  python email_sender.py magic <to_email> <magic_link_url>")
        print("  python email_sender.py trial-expired <to_email>")
        print("  python email_sender.py welcome <to_email>")
        print("  python email_sender.py followup <to_email>")
        print("  python email_sender.py nudge <to_email> <magic_link_url>")
        sys.exit(2)
    cmd = sys.argv[1]
    ok = False
    if cmd == "magic" and len(sys.argv) >= 4:
        ok = send_magic_link(sys.argv[2], sys.argv[3])
    elif cmd == "trial-expired" and len(sys.argv) >= 3:
        ok = send_trial_expired(sys.argv[2])
    elif cmd == "welcome" and len(sys.argv) >= 3:
        ok = send_welcome_paid(sys.argv[2])
    elif cmd == "followup" and len(sys.argv) >= 3:
        ok = send_trial_followup(sys.argv[2])
    elif cmd == "nudge" and len(sys.argv) >= 4:
        ok = send_unverified_nudge(sys.argv[2], sys.argv[3])
    else:
        print(f"bad command or args: {sys.argv[1:]}")
        sys.exit(2)
    print("sent ok" if ok else "send failed")
    sys.exit(0 if ok else 1)
