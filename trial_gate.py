"""
trial_gate.py — Streamlit auth gate for the SnipeWins trial flow.

The single entry point is `enforce_gate(st)`. Call it AT THE TOP of
streamlit_app.py, right after st.set_page_config but BEFORE any
dashboard rendering. The function does one of three things:

    A. Render normal dashboard → returns control to caller. This happens
       when the user is in trial_active or paid status. Caller continues
       rendering tabs as usual. A countdown badge is added to the page
       so the user always sees their remaining trial time.

    B. Render a gate page (login / check-inbox / paywall) and call
       st.stop() — caller's rendering NEVER executes for this request.
       The user sees only the gate page.

    C. Same as B with an error toast — shown when something goes wrong
       (bad magic link, send failure, etc.).

URL params handled:
    ?signup=<email>     → triggers signup flow (form on landing posts here
                          via Formspree's redirect)
    ?token=<magic>      → validates magic link, starts trial
    (none of the above) → checks session_state for active user
"""
from __future__ import annotations

import os
import time
from typing import Any, Optional


# ── Configuration ──────────────────────────────────────────────────────────

# The public URL of the Streamlit app. Used to build the magic-link target
# emailed to users. Must be set via env var in production; defaults to
# localhost for development.
APP_BASE_URL = os.environ.get(
    "SNIPEWINS_APP_BASE_URL",
    "http://localhost:8501",
).rstrip("/")

# Stripe Payment Links — one for the $99/year founder rate, one for the
# $29/month with 7-day free trial. Both are loaded from .env so they can
# be swapped from test → live without code changes. Buttons no-op in dev
# mode when env vars aren't set.
STRIPE_CHECKOUT_URL       = os.environ.get("SNIPEWINS_STRIPE_URL",       "")
STRIPE_TRIAL_CHECKOUT_URL = os.environ.get("SNIPEWINS_STRIPE_TRIAL_URL", "")


# Session-state keys — namespaced to avoid collisions with dashboard state
SS_EMAIL          = "sw_trial_user_email"
SS_GATE_RENDERED  = "sw_trial_gate_already_rendered"


# ── Public API ─────────────────────────────────────────────────────────────

def enforce_gate(st) -> None:
    """Main entry. Either returns (dashboard should render) or st.stop()s
    (gate page rendered, dashboard suppressed). Idempotent — safe to call
    multiple times per request."""
    import trial_accounts

    qp = _read_query_params(st)

    # ── ROUTE 0: URL session-token restore. Streamlit's session_state dies
    # on every browser refresh (websocket reconnect). If we don't restore
    # auth from a durable handle in the URL, every refresh logs the user
    # out — and worse, when the trial timer hits 0 and the iframe reloads
    # the page, the user ends up on the signup screen instead of the
    # paywall. SESSION-TOKEN-2026-05-13.
    if "s" in qp and qp["s"] and not st.session_state.get(SS_EMAIL):
        restored = trial_accounts.find_email_by_session_token(str(qp["s"]))
        if restored:
            st.session_state[SS_EMAIL] = restored

    # ── ROUTE 1: magic link click (?token=xyz) — used for password reset
    #            and as a fallback for users who forgot their password ───
    if "token" in qp and qp["token"]:
        _handle_token_click(st, trial_accounts, qp["token"])
        return  # _handle_token_click sets session and reruns to clean URL

    # ── ROUTE 2: signup redirect from landing (?signup=email@x.com) ──
    # The landing form collects email only. We need a password to create
    # the account, so we show a "set your password" form pre-filled with
    # the email that arrived in the query param.
    if "signup" in qp and qp["signup"]:
        _render_set_password_page(st, prefill_email=str(qp["signup"]))
        st.stop()

    # ── ROUTE 2.5: forgot-password — send a magic link the user can click
    # to set a fresh password. Lives at ?forgot=1.
    if "forgot" in qp:
        _render_forgot_password_page(st)
        st.stop()

    # ── ROUTE 2.7: magic-link click landed us here — show the "set a new
    # password" form for the validated email. Used for both initial welcome
    # links AND forgot-password reset links.
    if st.session_state.get("sw_pending_password_set_email"):
        _render_set_new_password_after_magic(st)
        st.stop()

    # ── ROUTE 3: already logged in — check status ─────────────────────
    email = st.session_state.get(SS_EMAIL)
    if email:
        status = trial_accounts.get_trial_status(email)
        if status == trial_accounts.STATUS_PAID:
            _render_trial_badge(st, email, remaining_secs=None, paid=True)
            return  # full access for paid users
        if status == trial_accounts.STATUS_TRIAL_ACTIVE:
            remaining = trial_accounts.seconds_remaining(email)
            _render_trial_badge(st, email, remaining_secs=remaining, paid=False)
            return  # trial-active users get full dashboard + countdown
        if status == trial_accounts.STATUS_TRIAL_EXPIRED:
            _render_paywall(st, email)
            st.stop()
        # Anything else (pending_email_click, not_signed_up) — fall through
        # to the login page below. We clear the stale session to avoid loops.
        st.session_state.pop(SS_EMAIL, None)

    # ── ROUTE 4: no active session — show login / signup screen ───────
    _render_login_or_signup_page(st)
    st.stop()


# ── Route handlers ─────────────────────────────────────────────────────────

def _handle_token_click(st, trial_accounts, token: str) -> None:
    """User clicked a magic link (either forgot-password reset OR initial
    welcome email). Validate the token, then route to "set a password" so
    they can either set a new password (reset case) or pick their first one
    (welcome case). Once set, the trial starts and they enter the dashboard."""
    email = trial_accounts.validate_magic_token(token)
    if not email:
        _clear_query_params(st)
        st.session_state["sw_trial_error_msg"] = (
            "That link is no longer valid — it may have been used already, "
            "or expired after 24 hours. Sign in below or hit "
            "\"forgot password\" for a fresh link."
        )
        _render_login_or_signup_page(st)
        st.stop()
    # Park the email in a one-shot session slot so the next render knows
    # who's setting the password without trusting query params.
    st.session_state["sw_pending_password_set_email"] = email
    _clear_query_params(st)
    st.rerun()


def _render_set_new_password_after_magic(st) -> None:
    """User clicked a valid magic link and we parked their email in
    session_state. Show them a "set your password" form. Once they submit
    a valid password, save it, start the trial (if not started), log them
    in, and forward to the dashboard."""
    import trial_accounts
    _inject_gate_css(st)
    email = str(st.session_state.get("sw_pending_password_set_email") or "")
    if not email:
        # Defensive — shouldn't happen because enforce_gate already checked
        # this key. Fall back to the regular login page.
        _render_login_or_signup_page(st)
        return
    err_msg = st.session_state.pop("sw_trial_error_msg", None)

    st.markdown(
        f"<div class='sw-gate-shell'>"
        f"<div class='sw-gate-card'>"
        f"<div class='sw-gate-kicker'>SnipeWins · Magic link confirmed</div>"
        f"<h1 class='sw-gate-h1'>Set your password.</h1>"
        f"<p class='sw-gate-sub'>One more step for <strong>{email}</strong>. "
        f"Pick a password you'll remember — your 10-minute trial starts "
        f"the moment you save it.</p>"
        f"</div></div>",
        unsafe_allow_html=True,
    )
    if err_msg:
        st.error(err_msg)

    with st.form("sw_set_password_via_magic", clear_on_submit=False):
        password_input = st.text_input(
            "New password",
            placeholder="New password (8+ characters)",
            type="password",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button(
            "Save password and start my trial  →",
            type="primary",
            use_container_width=True,
        )
    if submitted:
        pw = password_input or ""
        if len(pw) < trial_accounts.MIN_PASSWORD_LEN:
            st.error(f"Password needs at least {trial_accounts.MIN_PASSWORD_LEN} characters.")
            return
        ok = trial_accounts.set_password(email, pw)
        if not ok:
            st.error("Couldn't save that password. Try again in a moment.")
            return
        trial_accounts.start_trial_now(email)
        st.session_state[SS_EMAIL] = email
        st.session_state.pop("sw_pending_password_set_email", None)
        _persist_session_in_url(st, trial_accounts, email)
        st.rerun()


def _render_forgot_password_page(st) -> None:
    """User clicked "forgot password" — collect their email and send a
    magic link they can click to set a new password. The magic-link token
    becomes a single-use password-reset credential."""
    import trial_accounts
    import email_sender
    _inject_gate_css(st)
    err_msg = st.session_state.pop("sw_trial_error_msg", None)

    # Show a success screen if the user just submitted the form below
    if st.session_state.pop("sw_forgot_sent_to", None):
        sent_email = st.session_state.pop("sw_forgot_sent_email", "")
        st.markdown(
            f"<div class='sw-gate-shell'>"
            f"<div class='sw-gate-card'>"
            f"<div class='sw-gate-kicker'>SnipeWins · Reset link sent</div>"
            f"<h1 class='sw-gate-h1'>Check your inbox.</h1>"
            f"<p class='sw-gate-sub'>If <strong>{sent_email}</strong> has a "
            f"SnipeWins account, we just emailed a link you can click to "
            f"set a new password. The link expires in 24 hours and works "
            f"once.</p>"
            f"<p class='sw-gate-sub' style='font-size:13px;color:#888;'>"
            f"<a href='?' style='color:#60a5fa;'>← Back to login</a>"
            f"</p>"
            f"</div></div>",
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        "<div class='sw-gate-shell'>"
        "<div class='sw-gate-card'>"
        "<div class='sw-gate-kicker'>SnipeWins · Forgot password</div>"
        "<h1 class='sw-gate-h1'>Send me a reset link.</h1>"
        "<p class='sw-gate-sub'>Enter the email on your SnipeWins account. "
        "We'll send you a single-use link you can click to set a new password.</p>"
        "</div></div>",
        unsafe_allow_html=True,
    )
    if err_msg:
        st.error(err_msg)

    with st.form("sw_forgot_password_form", clear_on_submit=False):
        email_input = st.text_input(
            "Email address",
            placeholder="you@example.com",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button(
            "Email me a reset link  →",
            type="primary",
            use_container_width=True,
        )
    if submitted:
        em = (email_input or "").strip().lower()
        if not em or "@" not in em or "." not in em.split("@")[-1]:
            st.error("Enter a valid email address.")
            return
        # Always rotate a magic token even for non-existent accounts so
        # we can't be used as an oracle ("does this email have an account?").
        # signup_email creates the account if it doesn't exist; that's a
        # tiny side effect but it keeps the gate simpler and the user can
        # always abandon the unused account.
        token = trial_accounts.signup_email(em, password=None)
        if token:
            magic_link_url = f"{APP_BASE_URL}/?token={token}"
            email_sender.send_magic_link(em, magic_link_url)
        # Always show success — don't leak whether the email was in our store.
        st.session_state["sw_forgot_sent_to"]    = True
        st.session_state["sw_forgot_sent_email"] = em
        st.rerun()

    st.markdown(
        "<div class='sw-gate-footnote'>"
        "<a href='?' style='color:#60a5fa;'>← Back to login</a>"
        "</div>",
        unsafe_allow_html=True,
    )


# ── Rendered pages (each owns its full markup) ─────────────────────────────

def _render_login_or_signup_page(st) -> None:
    """Default unauthenticated screen. Toggles between SIGNUP and LOGIN
    modes based on a session-state flag. Each mode shows the other's link
    at the bottom so the user always has a way over to the right form.

    Modes:
        - signup (default): email + password → creates account, starts trial
        - login: email + password → validates against stored hash

    The form handler (_handle_email_password_submit) is still smart enough
    to do the right thing even if the user is on the "wrong" screen
    (typing an existing email on the signup screen still logs them in),
    but the UI affordance matches what they explicitly chose.
    """
    import trial_accounts
    _inject_gate_css(st)
    err_msg = st.session_state.pop("sw_trial_error_msg", None)
    mode = st.session_state.get("sw_gate_mode", "signup")
    is_signup = (mode == "signup")

    headline = "Start your trial" if is_signup else "Welcome back"
    subline = (
        "Enter your email and pick a password. Returning members can use "
        "the sign-in link below."
        if is_signup else
        "Enter the email and password you used when you signed up."
    )
    button_text = (
        "Start my 10-minute trial  →"
        if is_signup else
        "Sign in  →"
    )
    pw_placeholder = (
        "Pick a password (8+ characters)"
        if is_signup else
        "Your password"
    )

    st.markdown(
        f"<div class='sw-gate-shell'>"
        f"<div class='sw-gate-card'>"
        f"<div class='sw-gate-kicker'>SnipeWins</div>"
        f"<h1 class='sw-gate-h1'>{headline}</h1>"
        f"<p class='sw-gate-sub'>{subline}</p>"
        f"</div></div>",
        unsafe_allow_html=True,
    )
    if err_msg:
        st.error(err_msg)

    form_key = "sw_signup_form" if is_signup else "sw_login_form"
    with st.form(form_key, clear_on_submit=False):
        email_input = st.text_input(
            "Email address",
            placeholder="you@example.com",
            label_visibility="collapsed",
        )
        password_input = st.text_input(
            "Password",
            placeholder=pw_placeholder,
            type="password",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button(
            button_text,
            type="primary",
            use_container_width=True,
        )

    if submitted:
        em = (email_input or "").strip().lower()
        pw = password_input or ""
        if not em or "@" not in em or "." not in em.split("@")[-1]:
            st.error("Enter a valid email address.")
            return
        if len(pw) < trial_accounts.MIN_PASSWORD_LEN:
            st.error(f"Password needs at least {trial_accounts.MIN_PASSWORD_LEN} characters.")
            return
        _handle_email_password_submit(st, trial_accounts, em, pw)

    # Cross-link between the two modes + the forgot-password escape hatch.
    # Streamlit's recommended way to flip session state on click is via a
    # button (links don't trigger reruns reliably). Two tiny inline buttons
    # to keep the layout tight.
    _col_a, _col_b = st.columns(2)
    with _col_a:
        if is_signup:
            if st.button("Already have an account? Sign in", key="sw_gate_to_login", use_container_width=True):
                st.session_state["sw_gate_mode"] = "login"
                st.rerun()
        else:
            if st.button("Don't have an account? Sign up", key="sw_gate_to_signup", use_container_width=True):
                st.session_state["sw_gate_mode"] = "signup"
                st.rerun()
    with _col_b:
        # Forgot-password link only matters on the login screen, but it's
        # cheap to keep visible on both so the user always has the escape.
        st.markdown(
            "<a href='?forgot=1' style='display:block;text-align:center;"
            "padding:10px;color:#60a5fa;font-size:13px;text-decoration:none;'>"
            "Forgot your password?</a>",
            unsafe_allow_html=True,
        )


def _render_set_password_page(st, prefill_email: str) -> None:
    """User just submitted email on the landing page and was redirected
    here with ?signup=email. We need to collect a password to finish account
    creation and start their trial. Email field is pre-filled (and editable
    so a typo on the landing form can be fixed)."""
    import trial_accounts
    _inject_gate_css(st)
    err_msg = st.session_state.pop("sw_trial_error_msg", None)
    em_clean = str(prefill_email or "").strip().lower()

    st.markdown(
        f"<div class='sw-gate-shell'>"
        f"<div class='sw-gate-card'>"
        f"<div class='sw-gate-kicker'>SnipeWins · Almost in</div>"
        f"<h1 class='sw-gate-h1'>Set a password to start your 10-minute trial.</h1>"
        f"<p class='sw-gate-sub'>Save this — it's how you'll log back in if you "
        f"close the tab. We're not sending a verification email; your trial "
        f"starts the moment you click the button below.</p>"
        f"</div></div>",
        unsafe_allow_html=True,
    )
    if err_msg:
        st.error(err_msg)

    with st.form("sw_set_password_form", clear_on_submit=False):
        email_input = st.text_input(
            "Email address",
            value=em_clean,
            label_visibility="collapsed",
        )
        password_input = st.text_input(
            "Choose a password",
            placeholder="Pick a password (8+ characters)",
            type="password",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button(
            "Start my 10-minute trial  →",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        em = (email_input or "").strip().lower()
        pw = password_input or ""
        if not em or "@" not in em or "." not in em.split("@")[-1]:
            st.error("Enter a valid email address.")
            return
        if len(pw) < trial_accounts.MIN_PASSWORD_LEN:
            st.error(f"Password needs at least {trial_accounts.MIN_PASSWORD_LEN} characters.")
            return
        _handle_email_password_submit(st, trial_accounts, em, pw)


def _handle_email_password_submit(st, trial_accounts, email: str, password: str) -> None:
    """Single handler used by BOTH the landing-redirect signup AND the
    in-app login/signup form. Logic:
        - If the email already has a password set:
            * Matches → log in (resume existing trial or paywall)
            * Doesn't match → error, suggest forgot-password
        - If the email is new OR has no password yet:
            * Create the account with this password, start the trial,
              log them in immediately.

    This way users never have to think "am I signing up or logging in?"
    — they just type email + password and the right thing happens."""
    existing_user = trial_accounts.get_user(email)
    has_pw = trial_accounts.has_password(email)

    if existing_user and has_pw:
        # Login path
        if trial_accounts.validate_password(email, password):
            st.session_state[SS_EMAIL] = email
            _clear_query_params(st)
            _persist_session_in_url(st, trial_accounts, email)
            st.rerun()
        else:
            st.error(
                "That email has an account, but the password doesn't match. "
                "Try again, or use the forgot-password link below."
            )
        return

    # Signup path: no account yet OR account exists without a password
    # (e.g. they used a magic link once before but never set a password).
    # Create/upgrade the account with this password.
    token = trial_accounts.signup_email(email, password=password)
    if not token:
        st.error("We couldn't create your account. Try again in a moment.")
        return
    # Start the trial immediately — no email verification step. We grant
    # the trial credit on the strength of the email + password combination.
    trial_accounts.start_trial_now(email)
    st.session_state[SS_EMAIL] = email
    _clear_query_params(st)
    _persist_session_in_url(st, trial_accounts, email)
    st.rerun()


def _render_check_inbox_page(st, email: str) -> None:
    """Shown immediately after signup — 'we sent you a link, go click it.'
    The user is NOT logged in yet at this point; they have to click the
    email link to start the trial."""
    _inject_gate_css(st)
    st.markdown(
        f"<div class='sw-gate-shell'>"
        f"<div class='sw-gate-card'>"
        f"<div class='sw-gate-kicker'>SnipeWins · Check your inbox</div>"
        f"<h1 class='sw-gate-h1'>Magic link sent.</h1>"
        f"<p class='sw-gate-sub'>We just emailed <strong>{email}</strong> a "
        f"one-click link to your dashboard. Click it from your inbox to "
        f"start your 10-minute trial.</p>"
        f"<p class='sw-gate-sub' style='font-size:13px;color:#888;margin-top:18px;'>"
        f"Not seeing it? Check spam, or try again with a different address. "
        f"The link expires in 24 hours and can only be used once."
        f"</p>"
        f"</div></div>",
        unsafe_allow_html=True,
    )


def _render_paywall(st, email: str) -> None:
    """The 10-minute clock has run out. Show the upgrade options.

    Two CTAs, two separate Stripe Payment Links:
        - $99/year founder rate (headline conversion goal, normally $228)
        - $29/month with 7-day free trial (gentler ramp for the hesitant)

    Each button reads from its own env var so they can be swapped from
    test → live independently. If a URL isn't set the button no-ops.
    """
    _inject_gate_css(st)
    checkout_annual = STRIPE_CHECKOUT_URL or "#"
    checkout_trial  = STRIPE_TRIAL_CHECKOUT_URL or "#"
    st.markdown(
        f"<div class='sw-gate-shell'>"
        f"<div class='sw-gate-card'>"
        f"<div class='sw-gate-kicker' style='color:#facc15;'>Trial ended</div>"
        f"<h1 class='sw-gate-h1'>Your 10 minutes is up.</h1>"
        f"<p class='sw-gate-sub'>Hope you saw a card worth bidding on. "
        f"Pick how you want to keep going:</p>"
        f""
        f"<div class='sw-paywall-row'>"
        f"<div class='sw-paywall-option sw-paywall-recommend'>"
        f"<div class='sw-paywall-tag'>Founder rate</div>"
        f"<div class='sw-paywall-price'>$99<span>/year</span></div>"
        f"<div class='sw-paywall-detail'>"
        f"<span style='text-decoration:line-through;color:#666;'>Normally $228/yr.</span> "
        f"Locked in for life as a founder. Two or three typical wins clear it.</div>"
        f"<a href='{checkout_annual}' target='_top' class='sw-paywall-cta sw-paywall-cta-primary'>"
        f"Lock in $99/year  →</a>"
        f"</div>"
        f""
        f"<div class='sw-paywall-option'>"
        f"<div class='sw-paywall-tag'>Monthly</div>"
        f"<div class='sw-paywall-price'>$29<span>/month</span></div>"
        f"<div class='sw-paywall-detail'>Free for 7 days, card required. "
        f"Cancel anytime in the first week, no charge.</div>"
        f"<a href='{checkout_trial}' target='_top' class='sw-paywall-cta sw-paywall-cta-secondary'>"
        f"Start 7-day trial  →</a>"
        f"</div>"
        f"</div>"
        f""
        f"<div class='sw-gate-footnote' style='margin-top:24px;'>"
        f"Trial associated with <strong>{email}</strong>. Already upgraded? "
        f"<a href='?refresh=1' style='color:#60a5fa;'>Refresh your access</a>."
        f"</div>"
        f"</div></div>",
        unsafe_allow_html=True,
    )


def _render_trial_badge(st, email: str, remaining_secs: Optional[int], paid: bool) -> None:
    """Always-on status pill shown above the nav for active users. Trial
    users see a live JS-driven countdown that ticks every second; paid
    users see a green 'member' badge.

    LIVE-COUNTDOWN-2026-05-12: previously this rendered via st.markdown
    and only updated when Streamlit re-ran the script (tab nav, button
    click). Now the trial badge renders via st.components.v1.html() so we
    can embed a client-side JS timer that updates the countdown text
    every second without any Streamlit re-execution. When the timer
    reaches zero the JS triggers a parent-window reload, which causes
    Streamlit to re-run, see the expired trial, and show the paywall.
    """
    _inject_gate_css(st)
    if paid:
        # Paid users — no countdown needed, stay with the simple inline markdown.
        st.markdown(
            f"<div class='sw-trial-badge sw-trial-badge-paid'>"
            f"<span class='sw-trial-badge-dot' style='background:#4ade80;'></span>"
            f"Member · <strong>{email}</strong>"
            f"</div>",
            unsafe_allow_html=True,
        )
        return

    # Trial user — render the self-updating countdown via components.html.
    # The iframe runs same-origin so it can read the parent's window object
    # to trigger a reload at expiry.
    import trial_accounts
    user = trial_accounts.get_user(email) or {}
    expires_ts = float(user.get("trial_expires_ts") or 0)
    expires_ms = int(expires_ts * 1000)
    safe_email = (email or "").replace("<", "&lt;").replace(">", "&gt;")

    # All CSS is inline because the iframe is isolated from the parent's
    # injected styles. Match the .sw-trial-badge look exactly.
    badge_html = f"""\
<!DOCTYPE html>
<html>
<head>
<style>
  html, body {{
    margin: 0;
    padding: 0;
    background: transparent;
    font-family: -apple-system, 'SF Pro Display', Inter, sans-serif;
    overflow: hidden;
  }}
  #sw-trial-badge {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 14px;
    background: #141414;
    border: 1px solid rgba(148,163,184,0.12);
    border-radius: 999px;
    font-size: 12px;
    color: #b0b0b0;
    margin: 4px 0 8px 0;
    line-height: 1.2;
  }}
  #sw-trial-dot {{
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #4ade80;
  }}
  #sw-trial-countdown {{
    font-weight: 700;
    color: #4ade80;
    font-variant-numeric: tabular-nums;
  }}
  .sw-trial-sep {{
    color: #444;
    margin: 0 6px;
  }}
  .sw-trial-email {{
    color: #666;
    font-size: 11px;
  }}
</style>
</head>
<body>
  <div id="sw-trial-badge">
    <span id="sw-trial-dot"></span>
    Trial · <strong id="sw-trial-countdown">--:--</strong> remaining
    <span class="sw-trial-sep">·</span>
    <span class="sw-trial-email">{safe_email}</span>
  </div>
<script>
(function() {{
  var EXPIRES_MS = {expires_ms};
  var countdownEl = document.getElementById('sw-trial-countdown');
  var dotEl = document.getElementById('sw-trial-dot');
  if (!countdownEl || !dotEl) return;
  function fmt(n) {{ return n < 10 ? '0' + n : '' + n; }}
  function tick() {{
    var remainingSec = Math.max(0, Math.floor((EXPIRES_MS - Date.now()) / 1000));
    if (remainingSec <= 0) {{
      // Trial just hit zero — reload the parent so Streamlit can re-run
      // the gate and show the paywall.
      try {{ window.parent.location.reload(); }}
      catch (e) {{ window.location.reload(); }}
      return;
    }}
    var mm = Math.floor(remainingSec / 60);
    var ss = remainingSec % 60;
    countdownEl.textContent = mm + ':' + fmt(ss);
    // Color escalation: green > 2min, amber > 30s, red below 30s
    var color;
    if (remainingSec < 30)       color = '#ef4444';
    else if (remainingSec < 120) color = '#facc15';
    else                          color = '#4ade80';
    dotEl.style.background = color;
    countdownEl.style.color = color;
  }}
  tick();
  setInterval(tick, 1000);
}})();
</script>
</body>
</html>"""
    # Height of 44px = exactly enough for the pill with its margins. Any
    # taller and we get visible empty space below the badge.
    st.components.v1.html(badge_html, height=44)


# ── Helpers ────────────────────────────────────────────────────────────────

def _read_query_params(st) -> dict:
    """Streamlit changed the API around 1.30 — st.query_params (dict-like)
    superseded st.experimental_get_query_params. Handle both."""
    try:
        qp = st.query_params
        # st.query_params returns a QueryParamsProxy that's dict-like
        return {k: v for k, v in qp.items()}
    except Exception:
        try:
            raw = st.experimental_get_query_params() or {}
            return {k: (v[0] if isinstance(v, list) and v else v) for k, v in raw.items()}
        except Exception:
            return {}


def _clear_query_params(st) -> None:
    try:
        st.query_params.clear()
    except Exception:
        try:
            st.experimental_set_query_params()
        except Exception:
            pass


def _set_query_params(st, params: dict) -> None:
    try:
        st.query_params.clear()
        for k, v in params.items():
            st.query_params[k] = v
    except Exception:
        try:
            st.experimental_set_query_params(**params)
        except Exception:
            pass


def _persist_session_in_url(st, trial_accounts, email: str) -> None:
    """Pin a session token to the URL via `?s=<token>` so the user stays
    logged in across browser refreshes. Streamlit's session_state dies on
    every websocket reconnect; this is the durable handle the gate uses
    to restore login (see ROUTE 0 in enforce_gate). Rotates the token on
    each successful auth so a stale shared URL goes dead after the next
    login. Silent no-op on any failure — we'd rather show the dashboard
    than block the user from progressing. SESSION-TOKEN-2026-05-13."""
    try:
        token = trial_accounts.create_session_token(email)
        if not token:
            return
        st.query_params["s"] = token
    except Exception as _exc:
        print(f"[SESSION_TOKEN_SET_ERR] {type(_exc).__name__}: {str(_exc)[:140]}")


# ── CSS — single source of truth for gate visual ──────────────────────────

def _inject_gate_css(st) -> None:
    """Inject on every call. The previous session-state guard skipped
    re-injection across reruns, which made the CSS disappear after
    st.rerun() (paywall rendered bare, primary buttons briefly flashed
    Streamlit's default red). Streamlit's renderer dedupes identical
    markdown blocks, so re-injecting is safe and cheap. CSS-2026-05-13."""
    st.markdown(
        """
<style>
.sw-gate-shell {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 40px 16px;
    font-family: -apple-system, 'SF Pro Display', Inter, sans-serif;
}
.sw-gate-card {
    width: 100%;
    max-width: 540px;
    background: linear-gradient(135deg, #161616 0%, #0a0a0a 100%);
    border-radius: 18px;
    border: 1px solid rgba(148, 163, 184, 0.10);
    padding: 36px 32px;
    color: #fafafa;
    box-shadow: 0 8px 40px rgba(0,0,0,0.35);
}
.sw-gate-kicker {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.18em;
    color: #4ade80;
    text-transform: uppercase;
    margin-bottom: 14px;
}
.sw-gate-h1 {
    margin: 0 0 12px 0;
    font-size: 26px;
    font-weight: 700;
    line-height: 1.25;
    color: #fafafa;
    letter-spacing: -0.01em;
}
.sw-gate-sub {
    margin: 0 0 22px 0;
    font-size: 15px;
    line-height: 1.5;
    color: #b0b0b0;
}
.sw-gate-footnote {
    margin-top: 16px;
    font-size: 12px;
    color: #888;
    text-align: center;
}
.sw-paywall-row {
    display: flex;
    gap: 14px;
    flex-wrap: wrap;
    margin-top: 18px;
}
.sw-paywall-option {
    flex: 1 1 220px;
    padding: 22px 20px;
    background: #1c1c1c;
    border: 1px solid rgba(148,163,184,0.10);
    border-radius: 14px;
    display: flex;
    flex-direction: column;
}
.sw-paywall-recommend {
    border: 1px solid rgba(74,222,128,0.40);
    background: linear-gradient(180deg, rgba(74,222,128,0.06) 0%, #1c1c1c 100%);
}
.sw-paywall-tag {
    font-size: 10px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: #888;
    margin-bottom: 8px;
}
.sw-paywall-recommend .sw-paywall-tag { color: #4ade80; }
.sw-paywall-price {
    font-size: 32px;
    font-weight: 700;
    color: #fafafa;
    margin-bottom: 6px;
    line-height: 1.1;
}
.sw-paywall-price span {
    font-size: 14px;
    font-weight: 500;
    color: #b0b0b0;
}
.sw-paywall-detail {
    font-size: 13px;
    color: #b0b0b0;
    line-height: 1.45;
    margin-bottom: 16px;
    flex: 1;
}
.sw-paywall-cta {
    display: inline-block;
    padding: 12px 18px;
    border-radius: 10px;
    font-weight: 700;
    font-size: 14px;
    text-align: center;
    text-decoration: none;
}
.sw-paywall-cta-primary {
    background: #4ade80;
    color: #0a0a0a;
}
.sw-paywall-cta-secondary {
    background: transparent;
    color: #fafafa;
    border: 1px solid rgba(148,163,184,0.30);
}
.sw-trial-badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 14px;
    background: #141414;
    border: 1px solid rgba(148,163,184,0.12);
    border-radius: 999px;
    font-size: 12px;
    color: #b0b0b0;
    margin: 4px 0 12px 0;
    font-family: -apple-system, 'SF Pro Display', Inter, sans-serif;
}
.sw-trial-badge-dot {
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
}
.sw-trial-badge-paid {
    border-color: rgba(74,222,128,0.30);
    color: #fafafa;
}

/* GREEN-BUTTON-2026-05-12: override Streamlit's default primary button
   styling so the gate's CTAs match the SnipeWins green wordmark. Streamlit's
   default primary is bright red (#FF4B4B). Various selectors below cover
   every internal-DOM combo Streamlit ships across recent versions —
   data-testid-based attributes are the most stable. !important everywhere
   so Streamlit's component CSS can't reclaim. */
[data-testid="stFormSubmitButton"] button,
[data-testid="stFormSubmitButton"] button[kind="primary"],
[data-testid="stFormSubmitButton"] button[kind="primaryFormSubmit"],
[data-testid="baseButton-primary"],
[data-testid="baseButton-primaryFormSubmit"],
.stButton button[kind="primary"],
.stButton button[kind="primaryFormSubmit"],
button[kind="primary"],
button[kind="primaryFormSubmit"] {
    background-color: #4ade80 !important;
    background-image: none !important;
    color: #0a0a0a !important;
    border: 1px solid #4ade80 !important;
    font-weight: 700 !important;
    padding: 12px 18px !important;
    border-radius: 10px !important;
    transition: background-color 0.12s ease, transform 0.08s ease !important;
    box-shadow: none !important;
}
[data-testid="stFormSubmitButton"] button:hover,
[data-testid="baseButton-primary"]:hover,
.stButton button[kind="primary"]:hover,
button[kind="primary"]:hover,
button[kind="primaryFormSubmit"]:hover {
    background-color: #22c55e !important;
    border-color: #22c55e !important;
    color: #0a0a0a !important;
    transform: translateY(-1px);
}
[data-testid="stFormSubmitButton"] button:active,
button[kind="primary"]:active,
button[kind="primaryFormSubmit"]:active {
    transform: translateY(0);
}
/* And kill the red focus ring Streamlit injects on primary buttons */
[data-testid="stFormSubmitButton"] button:focus,
button[kind="primary"]:focus,
button[kind="primaryFormSubmit"]:focus {
    box-shadow: 0 0 0 3px rgba(74,222,128,0.30) !important;
    outline: none !important;
}

/* Dark-theme the text inputs inside the gate. We have to defeat Streamlit's
   BaseWeb defaults at every layer — the wrapper div sets a background, and
   the inner input has its own. */
[data-baseweb="input"],
[data-baseweb="input"] > div,
.stTextInput > div > div,
.stTextInput > div > div > div {
    background-color: #0a0a0a !important;
    border-radius: 10px !important;
    border: 1px solid rgba(148,163,184,0.22) !important;
}
[data-baseweb="input"] input,
[data-baseweb="input"] input[type="text"],
[data-baseweb="input"] input[type="password"],
.stTextInput input,
.stTextInput input[type="text"],
.stTextInput input[type="password"] {
    background-color: #0a0a0a !important;
    color: #fafafa !important;
    -webkit-text-fill-color: #fafafa !important;
    border: none !important;
    padding: 14px 16px !important;
    font-size: 16px !important;
    caret-color: #4ade80 !important;
}

/* PLACEHOLDER VISIBILITY FIX — bumped from #6b7280 to #a1a1aa, with stronger
   specificity and -webkit-text-fill-color (Safari/Chrome ignore plain `color`
   for placeholders unless this is also set). Result: clearly readable
   placeholder hints without being so loud they look like real values. */
div[data-baseweb="input"] input::placeholder,
div[data-baseweb="input"] input::-webkit-input-placeholder,
div[data-baseweb="input"] input::-moz-placeholder,
div[data-baseweb="input"] input:-ms-input-placeholder,
.stTextInput input::placeholder,
.stTextInput input::-webkit-input-placeholder,
.stTextInput input::-moz-placeholder,
.stTextInput input:-ms-input-placeholder,
input::placeholder,
input::-webkit-input-placeholder,
input::-moz-placeholder,
input:-ms-input-placeholder {
    color: #a1a1aa !important;
    -webkit-text-fill-color: #a1a1aa !important;
    opacity: 1 !important;
    font-weight: 400 !important;
    font-size: 15px !important;
}

/* Green ring on focus instead of red — applied to the OUTER wrapper since
   the inner input has no border. */
[data-baseweb="input"]:focus-within,
.stTextInput > div > div:focus-within {
    border: 1px solid #4ade80 !important;
    box-shadow: 0 0 0 3px rgba(74,222,128,0.18) !important;
}

/* CHROME-AUTOFILL FIX — when the browser autofills a saved email/password
   it paints its own light-blue background and ignores normal `background`
   CSS. The standard workaround is a massive inset box-shadow that "paints
   over" the autofill bg, plus -webkit-text-fill-color to force readable
   text. transition-delay is a sneaky-but-reliable way to suppress the
   autofill yellow that briefly flashes on page load. */
input:-webkit-autofill,
input:-webkit-autofill:hover,
input:-webkit-autofill:focus,
input:-webkit-autofill:active,
[data-baseweb="input"] input:-webkit-autofill,
.stTextInput input:-webkit-autofill {
    -webkit-box-shadow: 0 0 0 1000px #0a0a0a inset !important;
    box-shadow: 0 0 0 1000px #0a0a0a inset !important;
    -webkit-text-fill-color: #fafafa !important;
    caret-color: #4ade80 !important;
    transition: background-color 9999s ease-out 0s !important;
    -webkit-transition: background-color 9999s ease-out 0s !important;
    background-color: #0a0a0a !important;
    background-clip: content-box !important;
    border-radius: 10px !important;
}

/* Secondary button (the "Already have an account?" / "Don't have an
   account?" inline toggles below the form). Make them subtle so the
   primary CTA stays the star, but still readable on dark background. */
[data-testid="baseButton-secondary"],
.stButton button[kind="secondary"],
button[kind="secondary"] {
    background-color: transparent !important;
    color: #b0b0b0 !important;
    border: 1px solid rgba(148,163,184,0.20) !important;
    font-weight: 500 !important;
    border-radius: 10px !important;
}
[data-testid="baseButton-secondary"]:hover,
button[kind="secondary"]:hover {
    color: #fafafa !important;
    border-color: rgba(148,163,184,0.40) !important;
    background-color: rgba(148,163,184,0.05) !important;
}
</style>
""",
        unsafe_allow_html=True,
    )
