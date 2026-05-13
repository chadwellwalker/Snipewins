"""
eBay Bidding via the Buy Offer API (REST).

Placing bids requires a USER OAuth token — not the application-level token used
for Browse/Finding searches.  The user must authorize this app once via eBay's
OAuth Authorization Code flow.

==========  SETUP REQUIRED  ==========
Add these to your .env file:

  EBAY_RUNAME=<your eBay RuName from developer portal>

How to get your RuName:
  1. Log in to https://developer.ebay.com
  2. Go to Application Keys → "Get a Token from eBay via Your Application"
  3. Create / copy your RuName (looks like "First-App-PRD-xxxxxxx-xxxxxxx")
  4. Paste it into .env as EBAY_RUNAME=...

After setting EBAY_RUNAME, visit the "Ending Soon" page and click
"Connect eBay Account" to complete the one-time authorization.

Token is stored locally at: .ebay_user_token.json
=======================================

eBay Buy Offer API doc:
  POST /buy/offer/v1_beta/bidding/{itemId}/place_proxy_bid
  Scope required: https://api.ebay.com/oauth/api_scope/buy.offer.auction
"""

from __future__ import annotations

import base64
import json
import os
import time
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

_CLIENT_ID     = os.getenv("EBAY_CLIENT_ID", "")
_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET", "")
_RUNAME        = os.getenv("EBAY_RUNAME", "")
_MARKETPLACE   = os.getenv("EBAY_MARKETPLACE_ID", "EBAY_US")

_TOKEN_FILE    = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".ebay_user_token.json")

_AUTH_SCOPE    = "https://api.ebay.com/oauth/api_scope/buy.offer.auction"
_AUTH_BASE     = "https://auth.ebay.com/oauth2/authorize"
_TOKEN_URL     = "https://api.ebay.com/identity/v1/oauth2/token"
_BID_URL_BASE  = "https://api.ebay.com/buy/offer/v1_beta/bidding"


# ---------------------------------------------------------------------------
# OAuth helpers
# ---------------------------------------------------------------------------

def is_configured() -> bool:
    """True if EBAY_RUNAME is set — prerequisite for user OAuth."""
    return bool(_RUNAME and _CLIENT_ID and _CLIENT_SECRET)


def get_authorization_url() -> str:
    """
    Return the URL the user must open in their browser to grant bidding permission.
    After authorizing, eBay redirects to the RuName URL with ?code=... in the query string.
    The user copies that code and pastes it into the app.
    """
    import urllib.parse
    params = {
        "client_id":     _CLIENT_ID,
        "response_type": "code",
        "redirect_uri":  _RUNAME,
        "scope":         _AUTH_SCOPE,
        "state":         "ebay_bid_auth",
    }
    return f"{_AUTH_BASE}?{urllib.parse.urlencode(params)}"


def exchange_code_for_token(auth_code: str) -> Dict[str, Any]:
    """
    Exchange the authorization code (from the redirect URL) for access + refresh tokens.
    Saves tokens to .ebay_user_token.json and returns the token dict.
    """
    creds = base64.b64encode(f"{_CLIENT_ID}:{_CLIENT_SECRET}".encode()).decode()
    headers = {
        "Authorization": f"Basic {creds}",
        "Content-Type":  "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type":   "authorization_code",
        "code":         auth_code.strip(),
        "redirect_uri": _RUNAME,
    }
    resp = requests.post(_TOKEN_URL, headers=headers, data=data, timeout=30)
    resp.raise_for_status()
    token = resp.json()
    token["obtained_at"] = time.time()
    _save_token(token)
    return token


def _save_token(token: Dict[str, Any]) -> None:
    with open(_TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(token, f, indent=2)


def _load_token() -> Optional[Dict[str, Any]]:
    if not os.path.isfile(_TOKEN_FILE):
        return None
    try:
        with open(_TOKEN_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _refresh_access_token(token: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Use the refresh_token to get a new access_token."""
    rt = token.get("refresh_token")
    if not rt:
        return None
    creds = base64.b64encode(f"{_CLIENT_ID}:{_CLIENT_SECRET}".encode()).decode()
    headers = {
        "Authorization": f"Basic {creds}",
        "Content-Type":  "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type":    "refresh_token",
        "refresh_token": rt,
        "scope":         _AUTH_SCOPE,
    }
    try:
        resp = requests.post(_TOKEN_URL, headers=headers, data=data, timeout=30)
        resp.raise_for_status()
        new_tok = resp.json()
        new_tok["obtained_at"]   = time.time()
        new_tok["refresh_token"] = rt  # preserve refresh token
        _save_token(new_tok)
        return new_tok
    except Exception:
        return None


def get_valid_access_token() -> Optional[str]:
    """
    Return a valid access token string, refreshing if needed.
    Returns None if no token is stored or refresh fails.
    """
    token = _load_token()
    if not token:
        return None

    obtained_at  = float(token.get("obtained_at", 0))
    expires_in   = float(token.get("expires_in", 7200))
    age          = time.time() - obtained_at

    # Refresh if fewer than 120 seconds of life remain
    if age >= (expires_in - 120):
        token = _refresh_access_token(token)

    if not token:
        return None
    return token.get("access_token")


def is_connected() -> bool:
    """True if a stored user token exists (may be expired — checked on use)."""
    return os.path.isfile(_TOKEN_FILE)


def disconnect() -> None:
    """Delete the stored user token (forces re-auth)."""
    if os.path.isfile(_TOKEN_FILE):
        os.remove(_TOKEN_FILE)


# ---------------------------------------------------------------------------
# Bidding
# ---------------------------------------------------------------------------

def place_bid(item_id: str, max_bid: float) -> Dict[str, Any]:
    """
    Place a proxy bid on an eBay auction via the Buy Offer API.

    Returns a dict with:
        success (bool)
        message (str)
        raw_response (dict, if available)

    Requires EBAY_RUNAME in .env and a connected user token (see is_connected()).
    """
    if not is_configured():
        return {
            "success": False,
            "message": (
                "eBay bidding not configured. Add EBAY_RUNAME to your .env file "
                "and connect your eBay account via the 'Ending Soon' page."
            ),
        }

    access_token = get_valid_access_token()
    if not access_token:
        return {
            "success": False,
            "message": (
                "No valid eBay user token. Connect your eBay account via the "
                "'Ending Soon' page → 'Connect eBay Account'."
            ),
        }

    url = f"{_BID_URL_BASE}/{item_id}/place_proxy_bid"
    headers = {
        "Authorization":           f"Bearer {access_token}",
        "X-EBAY-C-MARKETPLACE-ID": _MARKETPLACE,
        "Content-Type":            "application/json",
    }
    body = {
        "maxAmount": {
            "currency": "USD",
            "value":    f"{max_bid:.2f}",
        }
    }

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=20)
    except requests.RequestException as e:
        return {"success": False, "message": f"Network error: {e}"}

    try:
        raw = resp.json()
    except Exception:
        raw = {"status_code": resp.status_code, "text": resp.text[:500]}

    if resp.status_code in (200, 201):
        auction_status = raw.get("auctionStatus", "")
        if auction_status in ("WINNING", "WON", "OUTBID", ""):
            return {
                "success": True,
                "message": f"Bid placed: ${max_bid:.2f}. Auction status: {auction_status or 'placed'}",
                "raw_response": raw,
            }
        # eBay returned 200 but with an error in body
        errors = raw.get("errors") or raw.get("warnings") or []
        msg = errors[0].get("message", str(raw)) if errors else str(raw)
        return {"success": False, "message": msg, "raw_response": raw}

    if resp.status_code == 429:
        return {"success": False, "message": "eBay rate limit hit. Try again in a few seconds.", "raw_response": raw}

    if resp.status_code == 401:
        # Try one refresh
        token = _load_token()
        if token:
            refreshed = _refresh_access_token(token)
            if refreshed:
                return place_bid(item_id, max_bid)  # retry once
        return {"success": False, "message": "eBay auth expired. Reconnect your account.", "raw_response": raw}

    errors = (raw.get("errors") or [{}])
    err_msg = errors[0].get("message", f"HTTP {resp.status_code}") if errors else f"HTTP {resp.status_code}"
    return {"success": False, "message": err_msg, "raw_response": raw}
