"""
eBay Partner Network (EPN) affiliate link helper.

Every outbound eBay link in SnipeWins (item links + "audit on eBay" search links)
should be routed through `affiliate_url()` so clicks that lead to a purchase earn
EPN commission.

Approach (per https://developer.ebay.com/api-docs/buy/static/ref-epn-link.html):
append tracking params to ANY ebay.com URL —

    {target}&mkevt=1&mkcid=1&mkrid={rotation}&campid={campid}&toolid=10001&customid={subid}

Config is env-driven so nothing is hardcoded and the whole thing is a safe no-op
until you set your Campaign ID in the Render environment:

    EBAY_EPN_CAMPAIGN_ID   (required to earn — your 10-digit EPN campaign id)
    EBAY_EPN_ROTATION_ID   (optional, default 711-53200-19255-0 = eBay US)
    EBAY_EPN_TOOL_ID       (optional, default 10001)
    EBAY_EPN_CHANNEL_ID    (optional, default 1 = EPN)

If EBAY_EPN_CAMPAIGN_ID is unset, affiliate_url() returns the original URL
unchanged, so the site behaves exactly as before until you're approved.
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlsplit, urlunsplit

# eBay US rotation id. Override via env for other marketplaces if ever needed.
_DEFAULT_ROTATION_US = "711-53200-19255-0"


def _cfg() -> dict:
    # Read on each call so setting the env var in Render takes effect on the next
    # request without a code change (values are tiny; this is not a hot path).
    return {
        "campid": (os.environ.get("EBAY_EPN_CAMPAIGN_ID") or "").strip(),
        "mkrid": (os.environ.get("EBAY_EPN_ROTATION_ID") or _DEFAULT_ROTATION_US).strip(),
        "toolid": (os.environ.get("EBAY_EPN_TOOL_ID") or "10001").strip(),
        "mkcid": (os.environ.get("EBAY_EPN_CHANNEL_ID") or "1").strip(),
    }


def epn_enabled() -> bool:
    """True when a campaign id is configured (i.e. links will earn commission)."""
    return bool((os.environ.get("EBAY_EPN_CAMPAIGN_ID") or "").strip())


def _sanitize_customid(value: str) -> str:
    """EPN customid: alphanumeric-ish sub id, <=256 chars. Keep it URL-safe and
    readable in EPN reports (surface + player + item)."""
    s = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "")).strip("-")
    return s[:256]


def affiliate_url(url: str, customid: str = "") -> str:
    """
    Append EPN tracking params to an eBay URL. Returns the URL unchanged when:
      - no campaign id is configured (not approved yet / disabled),
      - the URL is empty or not an ebay.* domain,
      - the URL is already an affiliate/tracked link (has campid or mkcid).

    Works for item URLs (/itm/...) and search URLs (/sch/i.html?_nkw=...).
    """
    if not url:
        return url
    cfg = _cfg()
    if not cfg["campid"]:
        return url
    try:
        parts = urlsplit(url)
    except Exception:
        return url
    host = (parts.netloc or "").lower()
    if "ebay." not in host:
        return url
    existing = parts.query or ""
    low = existing.lower()
    if "campid=" in low or "mkcid=" in low:
        return url  # already tracked — don't double-tag

    added = [
        "mkevt=1",
        f"mkcid={cfg['mkcid']}",
        f"mkrid={cfg['mkrid']}",
        f"campid={cfg['campid']}",
        f"toolid={cfg['toolid']}",
    ]
    cid = _sanitize_customid(customid)
    if cid:
        added.append(f"customid={cid}")

    new_query = (existing + "&" if existing else "") + "&".join(added)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


# Convenience: build a customid like "pool-nba-anthony_edwards-v1|123..." from parts.
def build_customid(*parts: str) -> str:
    return _sanitize_customid("-".join(str(p) for p in parts if str(p or "").strip()))
