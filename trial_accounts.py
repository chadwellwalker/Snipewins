"""
trial_accounts.py — JSON-backed user/trial store for SnipeWins.

Responsibilities:
    - Capture signups (email + magic-link token)
    - Validate magic links and start the 10-minute trial clock
    - Track trial status, expiry, and paid customer state
    - Provide a single source of truth the Streamlit auth gate queries
      on every page render

Storage: a single JSON file (accounts.json) next to this module. Atomic
writes via tmp+replace so a half-written file is never observed. For a
real production deployment we'd switch to SQLite or a managed DB, but
JSON is fine for the trial-volume scale we're launching at and keeps
the deployment surface to zero new infrastructure.

Account lifecycle:
    not_signed_up
        ↓ signup_email()
    pending_email_click       ← magic-link sent, awaiting click
        ↓ validate_magic_token()
    trial_active              ← 10-minute clock started
        ↓ (clock runs out)
    trial_expired             ← paywall is shown
        ↓ mark_as_paid()
    paid                      ← full access, no timer
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, Optional


HERE = Path(__file__).parent
# PERSISTENT-STORE-2026-05-13: accounts.json path is configurable via
# SNIPEWINS_ACCOUNTS_PATH env var so we can point it at a Render
# persistent disk mount (e.g. /data/accounts.json) without code changes.
# Without persistent storage, every Render restart wipes user accounts —
# meaning the same email gets a fresh 10-minute trial after every deploy
# or OOM. Render Standard supports persistent disks at $0.25/GB/mo.
ACCOUNTS_FILE = Path(os.environ.get("SNIPEWINS_ACCOUNTS_PATH") or str(HERE / "accounts.json"))


# ── Tunables ────────────────────────────────────────────────────────────────

TRIAL_SECONDS = 600                # 10 minutes — per landing page promise
MAGIC_LINK_TTL_SECONDS = 86400     # 24h to click the email before token rots
MAGIC_TOKEN_BYTES = 24             # 24 bytes → 32 url-safe chars; plenty
                                   # of entropy without ugly long URLs
SESSION_TOKEN_BYTES = 32           # URL-pinned "remember me" token — used
                                   # by the gate to restore login on
                                   # browser refresh (Streamlit's
                                   # session_state dies on websocket
                                   # reconnect)

# ADMIN-OVERRIDE-2026-05-13: emails listed in SNIPEWINS_ADMIN_EMAILS env
# var get treated as STATUS_PAID regardless of their stored status. Lets
# the owner (and any team members) use the dashboard without paying
# themselves, and survives accounts.json wipes. Comma-separated. Empty
# var = no admins. The user still needs to sign up normally first
# (email + password) so they have a session token to log in with.
_ADMIN_EMAILS_RAW = os.environ.get("SNIPEWINS_ADMIN_EMAILS") or ""
ADMIN_EMAILS = {
    e.strip().lower() for e in _ADMIN_EMAILS_RAW.split(",") if e.strip()
}

# Status constants — single source of truth for what state a user is in
STATUS_NOT_SIGNED_UP        = "not_signed_up"
STATUS_PENDING_EMAIL_CLICK  = "pending_email_click"
STATUS_TRIAL_ACTIVE         = "trial_active"
STATUS_TRIAL_EXPIRED        = "trial_expired"
STATUS_PAID                 = "paid"

# ── Password hashing config ────────────────────────────────────────────────
# PBKDF2-HMAC-SHA256 with a per-user random salt. 200k iterations is OWASP's
# 2023 recommendation for SHA-256 and runs in ~150ms on commodity hardware
# — fast enough that login isn't laggy, slow enough that brute-force on a
# stolen accounts.json takes years per password. Bump if hardware catches up.
PBKDF2_ITERATIONS = 200_000
PBKDF2_HASH_NAME  = "sha256"
PBKDF2_SALT_BYTES = 16
MIN_PASSWORD_LEN  = 8


def _hash_password(password: str, salt: Optional[bytes] = None) -> Dict[str, str]:
    """Hash a password with PBKDF2. Returns {salt, hash} both hex-encoded.
    Passing `salt=None` generates a fresh random salt (new accounts);
    passing a stored salt is for verification (login)."""
    if salt is None:
        salt = secrets.token_bytes(PBKDF2_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        PBKDF2_HASH_NAME,
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return {
        "salt":       salt.hex(),
        "hash":       derived.hex(),
        "iterations": PBKDF2_ITERATIONS,
        "algorithm":  PBKDF2_HASH_NAME,
    }


def _verify_password(password: str, stored: Dict[str, Any]) -> bool:
    """Constant-time compare of a candidate password against a stored hash
    dict (the shape returned by _hash_password)."""
    if not stored or not isinstance(stored, dict):
        return False
    try:
        salt = bytes.fromhex(stored.get("salt") or "")
        expected = bytes.fromhex(stored.get("hash") or "")
        iters = int(stored.get("iterations") or PBKDF2_ITERATIONS)
        algo = str(stored.get("algorithm") or PBKDF2_HASH_NAME)
    except Exception:
        return False
    derived = hashlib.pbkdf2_hmac(algo, password.encode("utf-8"), salt, iters)
    # hmac.compare_digest avoids timing attacks where an attacker could
    # learn which byte mismatched first.
    return hmac.compare_digest(derived, expected)


# ── Persistence ─────────────────────────────────────────────────────────────

def _load() -> Dict[str, Any]:
    """Read the accounts file. Returns the canonical shape even when the
    file is missing or corrupted, so callers never need to defensive-check."""
    if not ACCOUNTS_FILE.exists():
        return {"version": 1, "users": {}}
    try:
        data = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"version": 1, "users": {}}
        data.setdefault("users", {})
        return data
    except Exception as exc:
        # Don't crash on a corrupted file — log and start fresh. The corrupt
        # file gets renamed so a human can recover any lost signups.
        try:
            ACCOUNTS_FILE.rename(HERE / f"accounts.json.corrupt.{int(time.time())}")
        except Exception:
            pass
        print(f"[trial_accounts] WARN: accounts.json corrupt ({exc}); started fresh")
        return {"version": 1, "users": {}}


def _save(data: Dict[str, Any]) -> None:
    """Atomic write — tmp + replace so half-written files never appear to
    a concurrent reader (the Streamlit app can render mid-write otherwise)."""
    tmp = str(ACCOUNTS_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
    os.replace(tmp, ACCOUNTS_FILE)


def _normalize_email(email: str) -> str:
    """Lowercase + strip. Emails are case-insensitive at the local-part by
    almost every provider in practice, and folding here means jane@gmail.com
    and Jane@gmail.com don't get two accounts."""
    return str(email or "").strip().lower()


# ── Public API ──────────────────────────────────────────────────────────────

def signup_email(email: str, password: Optional[str] = None) -> Optional[str]:
    """Register a new signup or refresh the magic link for an existing one.

    Returns the magic-link token (caller embeds it in the email URL).
    Returns None if the email is malformed or the password is too short.

    If `password` is provided, it's hashed and stored on the account; the
    user can then log in directly with email+password without needing the
    magic link. The magic link is still returned in case the caller wants
    to send a "welcome / verify your email" email anyway.

    If `password` is None, only the magic-link path is enabled — useful
    for the "forgot password" flow where the user has lost access and
    can't supply their old password.

    Idempotent: re-signing-up with the same email rotates the magic token,
    preserves trial state and paid status, and ONLY overwrites the password
    if a non-None value is passed (so the magic-link "forgot password"
    flow doesn't accidentally clear the old password).
    """
    em = _normalize_email(email)
    if not em or "@" not in em or "." not in em.split("@", 1)[-1]:
        return None
    if password is not None and len(password) < MIN_PASSWORD_LEN:
        return None

    data = _load()
    users = data["users"]
    token = secrets.token_urlsafe(MAGIC_TOKEN_BYTES)
    now = time.time()

    existing = users.get(em) or {}
    merged = {
        # Preserve any prior fields the user already has (paid status, etc.)
        **existing,
        "email":                   em,
        "magic_token":             token,
        "magic_token_created_ts":  now,
        "magic_token_used":        False,
        # Only set signed_up_ts on first signup so we can measure "time to
        # first login" later for funnel analysis.
        "signed_up_ts":            existing.get("signed_up_ts") or now,
    }
    # Only set/update password when the caller actually supplied one. This
    # lets the magic-link "forgot password" flow rotate the token without
    # blowing away the user's existing password (which they may still know).
    if password is not None:
        merged["password_hash"] = _hash_password(password)
    users[em] = merged
    _save(data)
    return token


def validate_password(email: str, password: str) -> bool:
    """Returns True if the email exists AND the password matches the stored
    hash. Returns False on any failure (no such user, no password set,
    wrong password). Constant-time on the actual hash comparison.

    Special case: returns False if the user signed up via magic-link only
    and never set a password. The caller should fall back to offering the
    magic-link flow in that case."""
    em = _normalize_email(email)
    user = (_load().get("users") or {}).get(em)
    if not user:
        return False
    stored = user.get("password_hash")
    if not stored:
        return False
    return _verify_password(password, stored)


def set_password(email: str, password: str) -> bool:
    """Replace a user's password. Used by the password-reset flow (after
    the user clicks a magic link). Returns True on success, False if the
    email isn't registered or the password is too short."""
    if not password or len(password) < MIN_PASSWORD_LEN:
        return False
    em = _normalize_email(email)
    data = _load()
    user = data.get("users", {}).get(em)
    if not user:
        return False
    user["password_hash"] = _hash_password(password)
    _save(data)
    return True


def start_trial_now(email: str) -> bool:
    """Start the 10-minute trial timer immediately, bypassing the magic-link
    click step. Used when the user signed up with email+password directly —
    we don't need email-ownership proof to grant the trial; we'll send the
    welcome email asynchronously.

    Idempotent: if the trial is already running (or expired), this is a
    no-op so a returning user re-logging in doesn't get their clock reset.

    Returns True if a trial timer is/becomes active, False if the email
    isn't registered."""
    em = _normalize_email(email)
    data = _load()
    user = data.get("users", {}).get(em)
    if not user:
        return False
    if not user.get("trial_started_ts"):
        now = time.time()
        user["trial_started_ts"]  = now
        user["trial_expires_ts"]  = now + TRIAL_SECONDS
    # Mark magic token consumed so a leaked link can't re-trigger the
    # trial later — the password is the canonical access credential now.
    user["magic_token_used"] = True
    _save(data)
    return True


def create_session_token(email: str) -> Optional[str]:
    """Generate a URL-pinned session token so the user stays logged in
    across browser refreshes. Streamlit's session_state dies on every
    websocket reconnect (which is what a refresh causes), so we need a
    durable handle the URL itself can carry. Stored on the user record;
    the gate looks it up via `?s=<token>` on every request before falling
    back to session_state.

    Rotated on each successful auth so an old leaked URL stops working
    once the user logs in fresh. Returns None if the email isn't registered.
    SESSION-TOKEN-2026-05-13."""
    em = _normalize_email(email)
    data = _load()
    user = data.get("users", {}).get(em)
    if not user:
        return None
    token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
    user["session_token"]            = token
    user["session_token_created_ts"] = time.time()
    _save(data)
    return token


def find_email_by_session_token(token: str) -> Optional[str]:
    """Reverse-lookup an email from a session token. Returns None if the
    token doesn't match any user. Constant-ish time because the user store
    is dict-based; if we ever scale to enough users that O(n) scans matter
    we'll add an index, but at launch volume (hundreds) this is fine."""
    if not token:
        return None
    data = _load()
    for em, user in (data.get("users") or {}).items():
        if user.get("session_token") == token:
            return em
    return None


# ── Email-send flag helpers. EMAIL-CONVERSION-2026-05-15 ──────────────────
# Each conversion email writes a timestamp flag on the user record so we
# don't double-send. Generic helper plus four named wrappers for clarity
# at call sites.

def _mark_email_sent(email: str, flag_field: str) -> bool:
    em = _normalize_email(email)
    data = _load()
    user = data.get("users", {}).get(em)
    if not user:
        return False
    user[flag_field] = time.time()
    _save(data)
    return True


def mark_trial_expired_email_sent(email: str) -> bool:
    return _mark_email_sent(email, "trial_expired_email_sent_ts")


def mark_welcome_email_sent(email: str) -> bool:
    return _mark_email_sent(email, "welcome_email_sent_ts")


def mark_trial_followup_email_sent(email: str) -> bool:
    return _mark_email_sent(email, "trial_followup_email_sent_ts")


def mark_unverified_nudge_sent(email: str) -> bool:
    return _mark_email_sent(email, "unverified_nudge_sent_ts")


def has_email_been_sent(email: str, flag_field: str) -> bool:
    em = _normalize_email(email)
    user = (_load().get("users") or {}).get(em)
    if not user:
        return False
    ts = user.get(flag_field)
    try:
        return bool(ts and float(ts) > 0)
    except Exception:
        return False


# ── Drip query helpers — feed email_drip.py with users due for a send ────
# Each helper iterates accounts.json, applies all the gating conditions
# (status, marketing_optin, time-since-event, not-already-sent), and
# returns email addresses ready to receive that specific email.

def users_needing_trial_followup(min_hours_since_expiry: float = 48.0) -> list:
    """Users whose trial expired ≥ min_hours_since_expiry ago, haven't
    paid, opted into marketing, and haven't received the followup yet.
    Returns a list of email strings."""
    out = []
    now = time.time()
    cutoff = now - (float(min_hours_since_expiry) * 3600.0)
    for em, user in (_load().get("users") or {}).items():
        if not isinstance(user, dict):
            continue
        # Must have a real trial that's expired
        exp_ts = float(user.get("trial_expires_ts") or 0)
        if exp_ts <= 0 or exp_ts > cutoff:
            continue
        # Must not be paid
        if (user.get("paid_status") or "").lower() == "paid":
            continue
        # Must have opted in (default True for older accounts)
        if not bool(user.get("marketing_optin", True)):
            continue
        # Must not have been sent already
        if user.get("trial_followup_email_sent_ts"):
            continue
        out.append(em)
    return out


def users_needing_unverified_nudge(min_hours_since_signup: float = 24.0) -> list:
    """Users who signed up ≥ min_hours_since_signup ago, never clicked
    the verification link, opted into marketing, and haven't received
    the nudge yet. Returns a list of email strings."""
    out = []
    now = time.time()
    cutoff = now - (float(min_hours_since_signup) * 3600.0)
    for em, user in (_load().get("users") or {}).items():
        if not isinstance(user, dict):
            continue
        # Must have signed up long enough ago
        signed_up = float(user.get("signed_up_ts") or 0)
        if signed_up <= 0 or signed_up > cutoff:
            continue
        # Must not have clicked the verification link yet
        if user.get("magic_token_used"):
            continue
        # Must not be paid (paid users skip verification via admin/Stripe path)
        if (user.get("paid_status") or "").lower() == "paid":
            continue
        # Must have opted in
        if not bool(user.get("marketing_optin", True)):
            continue
        # Must not have been nudged already
        if user.get("unverified_nudge_sent_ts"):
            continue
        out.append(em)
    return out


def set_marketing_optin(email: str, optin: bool) -> bool:
    """Record the user's preference for product/marketing email. Used by
    the signup forms' "Daily eBay briefing and SnipeWins alerts" checkbox.
    Returns True on success, False if the email isn't registered.
    MARKETING-OPTIN-2026-05-15."""
    em = _normalize_email(email)
    data = _load()
    user = data.get("users", {}).get(em)
    if not user:
        return False
    user["marketing_optin"]        = bool(optin)
    user["marketing_optin_set_ts"] = time.time()
    _save(data)
    return True


def get_marketing_optin(email: str) -> bool:
    """Read the user's product/marketing email opt-in. Defaults to True
    for users who signed up before this field existed — the checkbox is
    pre-checked at signup, so older accounts were implicitly opted in.
    Returns False only if the user explicitly unchecked the box or the
    email isn't registered."""
    em = _normalize_email(email)
    user = (_load().get("users") or {}).get(em)
    if not user:
        return False
    return bool(user.get("marketing_optin", True))


def has_password(email: str) -> bool:
    """True if the user has ever set a password. Used by the gate to
    decide whether to offer the password login form or only the magic-link
    flow for this account."""
    em = _normalize_email(email)
    user = (_load().get("users") or {}).get(em)
    return bool(user and user.get("password_hash"))


def validate_magic_token(token: str) -> Optional[str]:
    """Validate the magic-link token. On success, marks the token as used,
    starts the 10-minute trial clock (if not already started for this user),
    and returns the user's email. On failure, returns None.

    Failure modes:
        - Token doesn't match any user
        - Token already used (single-use protection)
        - Token older than MAGIC_LINK_TTL_SECONDS (24h)
    """
    if not token:
        return None
    data = _load()
    users = data["users"]
    now = time.time()
    for em, user in users.items():
        if user.get("magic_token") != token:
            continue
        # Single-use enforcement — replaying an old link does nothing.
        if user.get("magic_token_used"):
            return None
        # TTL enforcement — emails sitting unopened for >24h are stale.
        created = float(user.get("magic_token_created_ts") or 0)
        if created > 0 and (now - created) > MAGIC_LINK_TTL_SECONDS:
            return None
        # All checks passed — mark used, start trial clock.
        user["magic_token_used"] = True
        # Only set the trial start ON FIRST SUCCESSFUL LOGIN. If the user
        # already started a trial (e.g., they're re-clicking a fresh magic
        # link after their session expired), don't reset the clock — let
        # the trial naturally expire and the paywall do its job.
        if not user.get("trial_started_ts"):
            user["trial_started_ts"]  = now
            user["trial_expires_ts"]  = now + TRIAL_SECONDS
        _save(data)
        return em
    return None


def get_user(email: str) -> Optional[Dict[str, Any]]:
    """Read a user record by email. Returns None if not signed up."""
    em = _normalize_email(email)
    if not em:
        return None
    return (_load().get("users") or {}).get(em)


def get_trial_status(email: str) -> str:
    """One-line status check for the auth gate. Returns one of:
        not_signed_up, pending_email_click, trial_active,
        trial_expired, paid
    """
    user = get_user(email)
    if user is None:
        return STATUS_NOT_SIGNED_UP
    # ADMIN-OVERRIDE-2026-05-13: admin emails are always paid regardless
    # of stored state. Survives Render disk wipes — even if accounts.json
    # gets reset, the owner re-signs-up and is immediately PAID.
    if _normalize_email(email) in ADMIN_EMAILS:
        return STATUS_PAID
    # Paid customers always win regardless of trial state.
    if (user.get("paid_status") or "").lower() == "paid":
        return STATUS_PAID
    if not user.get("magic_token_used"):
        return STATUS_PENDING_EMAIL_CLICK
    # Magic link has been clicked, so trial_started_ts/expires_ts are set.
    exp = float(user.get("trial_expires_ts") or 0)
    if exp > 0 and time.time() < exp:
        return STATUS_TRIAL_ACTIVE
    return STATUS_TRIAL_EXPIRED


def seconds_remaining(email: str) -> int:
    """Seconds left in the trial. 0 if expired, not started, or unknown."""
    user = get_user(email)
    if not user:
        return 0
    exp = float(user.get("trial_expires_ts") or 0)
    if exp <= 0:
        return 0
    remaining = exp - time.time()
    return max(0, int(remaining))


def mark_as_paid(email: str, stripe_customer_id: Optional[str] = None,
                 stripe_subscription_id: Optional[str] = None) -> bool:
    """Flip a user from trial_expired (or any other state) to paid. Called
    from the Stripe webhook handler after successful checkout. Returns True
    on success, False if the email isn't registered."""
    em = _normalize_email(email)
    data = _load()
    user = data.get("users", {}).get(em)
    if not user:
        return False
    user["paid_status"]            = "paid"
    user["paid_at_ts"]             = time.time()
    user["stripe_customer_id"]     = stripe_customer_id
    user["stripe_subscription_id"] = stripe_subscription_id
    _save(data)
    return True


def admin_grant_paid(email: str) -> bool:
    """Manually flip a user to paid status. Useful before Stripe is wired
    so you can onboard your first paid customers by hand."""
    return mark_as_paid(email, stripe_customer_id="manual", stripe_subscription_id="manual")


def admin_reset_trial(email: str) -> bool:
    """Reset a user's trial clock so they can start over. Useful for
    debugging / for giving a friend a second pass during beta testing."""
    em = _normalize_email(email)
    data = _load()
    user = data.get("users", {}).get(em)
    if not user:
        return False
    user["magic_token_used"]   = False
    user["trial_started_ts"]   = None
    user["trial_expires_ts"]   = None
    _save(data)
    return True


# ── CLI for ops / debugging ─────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="trial_accounts.py — ops CLI")
    sub = parser.add_subparsers(dest="cmd")

    p_list = sub.add_parser("list", help="list all signed-up users")
    p_status = sub.add_parser("status", help="show status for one email")
    p_status.add_argument("email")
    p_grant = sub.add_parser("grant-paid", help="manually mark a user as paid")
    p_grant.add_argument("email")
    p_reset = sub.add_parser("reset", help="reset a user's trial clock")
    p_reset.add_argument("email")
    p_signup = sub.add_parser("signup", help="manually trigger a signup (returns magic token)")
    p_signup.add_argument("email")

    args = parser.parse_args()
    if args.cmd == "list":
        data = _load()
        users = data.get("users", {}) or {}
        if not users:
            print("(no signups yet)")
        for em, user in users.items():
            status = get_trial_status(em)
            remaining = seconds_remaining(em)
            print(f"  {em:40s}  {status:24s}  trial_remaining={remaining}s")
    elif args.cmd == "status":
        print(f"status={get_trial_status(args.email)}  remaining={seconds_remaining(args.email)}s")
    elif args.cmd == "grant-paid":
        ok = admin_grant_paid(args.email)
        print("ok" if ok else "user not found")
    elif args.cmd == "reset":
        ok = admin_reset_trial(args.email)
        print("ok" if ok else "user not found")
    elif args.cmd == "signup":
        tok = signup_email(args.email)
        print(f"token={tok}")
    else:
        parser.print_help()
