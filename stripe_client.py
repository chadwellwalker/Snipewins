"""
stripe_client.py — Minimal Stripe API wrapper for SnipeWins.

What this exists for:
    1. Verify Stripe Checkout completions after a user is redirected back
       from a Payment Link with `?paid=1&session_id=cs_xxx`. We pull the
       checkout session, confirm payment_status == "paid", extract the
       customer_id + customer_email + subscription_id, then flip the
       SnipeWins account to STATUS_PAID via trial_accounts.mark_as_paid.

    2. Generate one-time Stripe Customer Portal URLs so the user can
       cancel, switch plans (upgrade Monthly → Annual or downgrade),
       update their payment method, and see invoices — all from a
       Stripe-hosted UI we don't have to build ourselves.

Why we're not using the official `stripe` Python SDK:
    Same reason email_sender.py uses urllib for Resend — we want zero
    extra deploy dependencies. The two endpoints we hit are simple
    enough that urllib + a tiny helper does the job. Trade-off is that
    error formatting is less rich; for our launch scale that's fine.

Required env:
    STRIPE_SECRET_KEY=sk_test_...   (during testing)
    STRIPE_SECRET_KEY=sk_live_...   (in production after Stripe verification)

Configuration steps on the Stripe side (operator does these, not the code):
    1. Stripe Dashboard → Developers → API keys → reveal a Secret key.
    2. Stripe Dashboard → Settings → Billing → Customer portal →
       Activate. Enable: cancel subscriptions, switch plans, update
       payment method, view invoices. Set the business name and the
       privacy/terms links.
    3. Stripe Dashboard → each Payment Link → After payment →
       "Don't show confirmation page; redirect customers to your website"
       → enter: https://app.snipewins.com/?paid=1&session_id={CHECKOUT_SESSION_ID}
       Stripe substitutes the literal {CHECKOUT_SESSION_ID} with the
       real session id when redirecting.

STRIPE-AUTOFLIP-2026-05-15
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional


# ── Configuration ──────────────────────────────────────────────────────────

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()
STRIPE_API_BASE   = "https://api.stripe.com/v1"
STRIPE_API_TIMEOUT_SECS = 15


class StripeApiError(RuntimeError):
    """Wraps any failure reaching or parsing the Stripe API.

    Callers should catch this and surface a friendly "we couldn't verify
    your payment" message rather than letting the trace leak to the user.
    The underlying error is preserved in str(exc) for log diagnostics."""
    pass


def is_configured() -> bool:
    """True if STRIPE_SECRET_KEY is set. Used by callers to decide whether
    to render Stripe-dependent UI (the Manage Subscription button, the
    paid-return route) at all."""
    return bool(STRIPE_SECRET_KEY)


# ── Internal HTTP helper ───────────────────────────────────────────────────

def _request(method: str, path: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Make a request to the Stripe API.

    Stripe is unusual: requests are form-encoded (not JSON), responses are
    JSON. The auth header is `Bearer <secret_key>`.

    Returns the parsed JSON response on 2xx. Raises StripeApiError on
    any failure — connection error, non-2xx status, malformed JSON."""
    if not STRIPE_SECRET_KEY:
        raise StripeApiError("STRIPE_SECRET_KEY env var is not set")

    url = f"{STRIPE_API_BASE}{path}"
    headers = {
        "Authorization": f"Bearer {STRIPE_SECRET_KEY}",
        "Accept":        "application/json",
        # USER-AGENT-FIX: Stripe is also behind aggressive bot detection
        # for some endpoints. Identify clearly to avoid 403s like we hit
        # with Resend's Cloudflare WAF. (Stripe is more permissive than
        # Resend in practice, but this is cheap insurance.)
        "User-Agent":    "SnipeWins/1.0 (snipewins.com)",
    }
    body: Optional[bytes] = None
    if data:
        body = urllib.parse.urlencode(data, doseq=True).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=STRIPE_API_TIMEOUT_SECS) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return json.loads(raw)
            except json.JSONDecodeError as exc:
                raise StripeApiError(f"Stripe returned non-JSON ({exc}): {raw[:200]}")
    except urllib.error.HTTPError as exc:
        body_text = ""
        try:
            body_text = exc.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            pass
        raise StripeApiError(f"Stripe HTTP {exc.code} on {method} {path}: {body_text}")
    except urllib.error.URLError as exc:
        raise StripeApiError(f"Stripe network error on {method} {path}: {exc.reason}")
    except Exception as exc:
        raise StripeApiError(f"Stripe call failed ({type(exc).__name__}): {exc}")


# ── Public API ─────────────────────────────────────────────────────────────

def get_checkout_session(session_id: str) -> Dict[str, Any]:
    """Retrieve a Checkout Session by ID.

    Key fields in the response we care about:
        - payment_status:   "paid" | "unpaid" | "no_payment_required"
        - status:           "complete" | "open" | "expired"
        - customer:         Stripe customer ID (e.g. "cus_xxx") or None
                            for guest checkouts
        - customer_email:   email entered at checkout (may be top-level
                            OR nested under customer_details.email)
        - customer_details: {email, name, phone, address, ...}
        - subscription:     Subscription ID (e.g. "sub_xxx") or None for
                            one-time payments
        - mode:             "subscription" | "payment" | "setup"

    See https://stripe.com/docs/api/checkout/sessions/retrieve."""
    if not session_id or not session_id.startswith("cs_"):
        raise StripeApiError(f"Invalid session_id: {session_id!r}")
    return _request("GET", f"/checkout/sessions/{session_id}")


def create_billing_portal_session(customer_id: str, return_url: str) -> Dict[str, Any]:
    """Create a one-time Customer Portal session for the given customer.

    The returned object has a `url` field — redirect the user there. The
    URL is short-lived (a few minutes) and single-use; if the user lets it
    expire, generate a new one.

    `return_url` is where Stripe sends them after they finish in the
    portal. For SnipeWins we point this at app.snipewins.com/?account=1
    so they land back on the Account page.

    See https://stripe.com/docs/api/customer_portal/sessions/create."""
    if not customer_id or not customer_id.startswith("cus_"):
        raise StripeApiError(f"Invalid customer_id: {customer_id!r}")
    if not return_url:
        raise StripeApiError("return_url is required")
    return _request("POST", "/billing_portal/sessions", data={
        "customer":   customer_id,
        "return_url": return_url,
    })


# ── CLI for ops / debugging ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage:")
        print("  python stripe_client.py session <session_id>")
        print("  python stripe_client.py portal <customer_id> <return_url>")
        sys.exit(2)
    cmd = sys.argv[1]
    try:
        if cmd == "session":
            print(json.dumps(get_checkout_session(sys.argv[2]), indent=2))
        elif cmd == "portal":
            print(json.dumps(create_billing_portal_session(sys.argv[2], sys.argv[3]), indent=2))
        else:
            print(f"unknown command: {cmd}")
            sys.exit(2)
    except StripeApiError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)
