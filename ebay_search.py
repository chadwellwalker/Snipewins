import importlib
import os
import time
from typing import Any, Dict, List, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

EBAY_MARKETPLACE_ID = os.getenv("EBAY_MARKETPLACE_ID", "EBAY_US")


class EbayBrowseAuthError(RuntimeError):
    """
    Raised when Browse API OAuth cannot run (missing ebay_auth module, bad import state,
    or missing EBAY_CLIENT_ID / EBAY_CLIENT_SECRET).
    """


def _get_application_access_token_str() -> str:
    """
    Load ebay_auth at call time via importlib (not `from ebay_auth import …` at module import).

    Why: a top-level `from ebay_auth import …` can fail with KeyError('ebay_auth') when import
    machinery or Streamlit's reloader leaves sys.modules in a partial state during circular
    or repeated loads. Lazy import avoids running that path until a Browse API call is made.
    """
    try:
        auth_mod = importlib.import_module("ebay_auth")
    except (KeyError, ImportError, ModuleNotFoundError) as exc:
        raise EbayBrowseAuthError(
            "Could not load the ebay_auth module. Keep ebay_auth.py in the same folder as "
            "streamlit_app.py, ensure no other package shadows the name 'ebay_auth', then "
            "save files and restart Streamlit (Stop -> Run)."
        ) from exc
    get_tok = getattr(auth_mod, "get_application_access_token", None)
    if not callable(get_tok):
        raise EbayBrowseAuthError("ebay_auth.py must define get_application_access_token().")
    try:
        return str(get_tok())
    except ValueError as exc:
        raise EbayBrowseAuthError(
            "Missing eBay OAuth credentials for the Browse API. Add EBAY_CLIENT_ID and "
            "EBAY_CLIENT_SECRET to a .env file next to the app (eBay Developer Program)."
        ) from exc


def search_auction_items(keyword, limit=10):
    token = _get_application_access_token_str()

    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"

    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": EBAY_MARKETPLACE_ID
    }

    params = {
        "q": keyword,
        "filter": "buyingOptions:{AUCTION}",
        "limit": limit
    }

    response = _ebay_requests_session().get(url, headers=headers, params=params, timeout=8)
    response.raise_for_status()

    data = response.json()

    return data.get("itemSummaries", [])


class EbayRateLimitError(RuntimeError):
    """Raised when eBay Browse API returns 429 Too Many Requests."""


class EbayBrowseFetchError(RuntimeError):
    """Raised when Browse API BIN fetch fails before a usable payload is returned."""


def _ebay_requests_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.proxies.update({"http": None, "https": None})
    return session


def search_bin_items(keyword: str, limit: int = 10):
    """Browse API search restricted to Buy It Now (FIXED_PRICE) listings only.

    Raises EbayRateLimitError on 429 so callers can back off instead of silently
    treating a rate-limit wall as zero results.
    """
    try:
        token = _get_application_access_token_str()
    except EbayBrowseAuthError:
        raise
    except Exception as exc:
        raise EbayBrowseFetchError(
            f"{type(exc).__name__} during OAuth token fetch for BIN query '{keyword[:80]}'"
        ) from exc
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": EBAY_MARKETPLACE_ID,
    }
    lim = max(1, min(int(limit), 50))
    params = {
        "q": keyword,
        "filter": "buyingOptions:{FIXED_PRICE}",
        "limit": lim,
    }
    try:
        response = _ebay_requests_session().get(url, headers=headers, params=params, timeout=8)
        if response.status_code == 429:
            raise EbayRateLimitError(
                f"eBay rate limit (429) on query '{keyword[:60]}'. "
                "Wait a few minutes before scanning again."
            )
        if response.status_code >= 400:
            raise EbayBrowseFetchError(
                f"HTTP {response.status_code} for BIN query '{keyword[:80]}' "
                f"filter={params.get('filter')} marketplace={EBAY_MARKETPLACE_ID}"
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise EbayBrowseFetchError(
                f"Invalid payload type for BIN query '{keyword[:80]}' "
                f"filter={params.get('filter')}"
            )
        if "itemSummaries" not in payload:
            raise EbayBrowseFetchError(
                f"Empty payload for BIN query '{keyword[:80]}' "
                f"filter={params.get('filter')}"
            )
        return payload.get("itemSummaries", []) or []
    except EbayRateLimitError:
        raise  # always propagate rate-limit errors
    except requests.exceptions.Timeout as exc:
        raise EbayBrowseFetchError(
            f"Timeout for BIN query '{keyword[:80]}' filter={params.get('filter')}"
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise EbayBrowseFetchError(
            f"{type(exc).__name__} for BIN query '{keyword[:80]}' filter={params.get('filter')}: {str(exc)[:220]}"
        ) from exc
    except ValueError as exc:
        raise EbayBrowseFetchError(
            f"JSON decode failure for BIN query '{keyword[:80]}' filter={params.get('filter')}"
        ) from exc
    except Exception as exc:
        raise EbayBrowseFetchError(
            f"{type(exc).__name__} for BIN query '{keyword[:80]}' filter={params.get('filter')}: {str(exc)[:220]}"
        ) from exc


def _leaf(x):
    if isinstance(x, list) and x:
        return _leaf(x[0])
    return x


def _finding_item_title(item: Dict[str, Any]) -> str:
    t = item.get("title")
    if isinstance(t, list):
        t = t[0] if t else ""
    return str(t or "").strip()


def _finding_listing_type_raw(item: Dict[str, Any]) -> str:
    li = item.get("listingInfo")
    li = _leaf(li) if li is not None else None
    if isinstance(li, dict):
        lt = li.get("listingType")
        lt = _leaf(lt) if lt is not None else None
        if lt is not None:
            return str(lt).strip().lower()
    return ""


def _classify_sale_type_finding(listing_type: str, title: str) -> str:
    t = (listing_type or "").lower()
    low = (title or "").lower()
    if "chinese" in t or t.endswith("auction") or "auction" in t:
        return "auction"
    if "fixed" in t:
        if any(x in low for x in ("best offer", "accepted offer", " or best offer", "obo")):
            return "fixed_or_offer"
        return "fixed_price"
    return "unknown"


def _classify_sale_type_browse(item: Dict[str, Any]) -> str:
    opts = item.get("buyingOptions") or []
    if isinstance(opts, str):
        opts = [opts]
    u = [str(o).upper() for o in opts if o]
    if "AUCTION" in u and "FIXED_PRICE" in u:
        return "auction_or_bin"
    if "AUCTION" in u:
        return "auction"
    if "FIXED_PRICE" in u:
        return "fixed_price"
    return "unknown"


def _finding_item_end_time_iso(item: Dict[str, Any]) -> str:
    """Auction/listing end time from Finding item (sold listings use this as sale timing)."""
    li = item.get("listingInfo")
    li = _leaf(li) if li is not None else None
    if isinstance(li, dict):
        et = li.get("endTime")
        et = _leaf(et) if et is not None else None
        if et is not None:
            return str(et).strip()
    return ""


def _finding_item_price(item: Dict[str, Any]) -> float:
    ss = item.get("sellingStatus")
    ss = _leaf(ss) if ss is not None else {}
    if not isinstance(ss, dict):
        return 0.0
    cp = ss.get("currentPrice") or ss.get("convertedCurrentPrice")
    cp = _leaf(cp) if cp is not None else {}
    if not isinstance(cp, dict):
        return 0.0
    raw = cp.get("__value__")
    if raw is None:
        raw = cp.get("value")
    raw = _leaf(raw)
    if raw is None:
        return 0.0
    try:
        return float(str(raw).replace(",", ""))
    except ValueError:
        return 0.0

def search_completed_items_finding(keywords: str, limit: int = 40) -> List[Dict[str, Any]]:
    """
    Browse-only compatibility wrapper for historical comp callers.

    The Finding API is decommissioned, so this now returns active Browse market rows.
    """
    items = search_market_comps_browse(keywords, limit=limit)
    out: List[Dict[str, Any]] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        row = dict(it)
        row["itemSource"] = "browse_active_comp"
        row["comp_sale_type"] = _classify_sale_type_browse(it)
        row["comp_listing_type_raw"] = ",".join(
            str(x).upper() for x in (it.get("buyingOptions") or []) if x
        )
        out.append(row)
    return out


# ── Rate-limit cooldown state ────────────────────────────────────────────────
# eBay's Browse API enforces aggressive per-second and per-day quotas. When
# POOL + BIN + WORKER all share one app token, hitting the limit is easy.
# These module-level globals coordinate backoff WITHIN this process. They're
# also read externally by valuation_engine._merge_comp_search_passes which
# aborts remaining query passes once it sees we just got rate-limited (saves
# ~7× the API budget on cards that would otherwise burn 8 passes of 429s).
_consecutive_429s = 0
_last_was_rate_limited = False
_rate_limit_cooldown_until_ts = 0.0
_consecutive_cooldowns = 0           # ESCALATION: # of cooldowns since last 200
_RATE_LIMIT_TRIGGER_COUNT = 3        # after N consecutive 429s, enter cooldown
# QUOTA-FIX 2026-05-12: escalating cooldown ladder. The previous flat 60s
# cooldown was useless when the daily quota was genuinely exhausted — we'd
# wake up, get another 429, sleep another 60s, churn through ~50 cards an hour
# with zero useful work. The ladder backs off aggressively when 429s persist,
# while still recovering fast if it was just a per-minute burst limit.
# Index N = N-th consecutive cooldown without a success in between.
_RATE_LIMIT_COOLDOWN_LADDER_SECONDS = (60.0, 300.0, 900.0, 1800.0, 3600.0)
_RATE_LIMIT_COOLDOWN_SECONDS = _RATE_LIMIT_COOLDOWN_LADDER_SECONDS[0]  # back-compat shim


def search_market_comps_browse(keyword: str, limit: int = 40) -> List[Dict[str, Any]]:
    """
    Active listings (auction + fixed price) for comp proxy when sold API is unavailable.

    Every fetch is logged via [EBAY_COMP_FETCH] so we can distinguish between:
      - status=200 items=0      → eBay returned no matches (legit empty)
      - status=429              → rate-limited (the silent killer of the worker)
      - status=401 / 403        → auth token expired or scope wrong
      - status=exception        → network / timeout / connection error

    Rate-limit aware: after {_RATE_LIMIT_TRIGGER_COUNT} consecutive 429s, the function
    enters a {_RATE_LIMIT_COOLDOWN_SECONDS}-second sleep on the NEXT call to give
    eBay's per-minute quota window a chance to refill. The module-level flag
    `_last_was_rate_limited` is set on 429 so callers (notably
    valuation_engine._merge_comp_search_passes) can abort remaining query passes
    for the same card instead of firing 7 more guaranteed-429 variants.
    """
    global _consecutive_429s, _last_was_rate_limited, _rate_limit_cooldown_until_ts, _consecutive_cooldowns

    # Honor any active cooldown — sleep until it expires before firing again.
    now = time.time()
    if _rate_limit_cooldown_until_ts > now:
        wait_s = _rate_limit_cooldown_until_ts - now
        print(f"[EBAY_COMP_FETCH] cooldown_active sleeping={wait_s:.1f}s")
        time.sleep(wait_s)

    token = _get_application_access_token_str()
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": EBAY_MARKETPLACE_ID,
    }
    lim = max(1, min(int(limit), 50))
    params = {
        "q": keyword,
        "filter": "buyingOptions:{AUCTION|FIXED_PRICE}",
        "limit": lim,
    }
    _q_short = (keyword or "")[:120]
    try:
        response = _ebay_requests_session().get(url, headers=headers, params=params, timeout=30)
    except requests.RequestException as exc:
        print(
            f"[EBAY_COMP_FETCH] status=exception q={_q_short!r} "
            f"exc={type(exc).__name__}: {str(exc)[:200]}"
        )
        return []
    status = response.status_code
    if status == 200:
        # Success — reset rate-limit counters AND the escalation ladder. A
        # single non-429 success means the quota window is healthy again, so
        # the next cooldown (if any) should start back at the bottom of the
        # ladder (60s) rather than the painful end (3600s).
        _consecutive_429s = 0
        _consecutive_cooldowns = 0
        _last_was_rate_limited = False
        try:
            payload = response.json()
        except Exception as exc:
            print(
                f"[EBAY_COMP_FETCH] status=200 q={_q_short!r} "
                f"json_parse_error={type(exc).__name__}: {str(exc)[:200]}"
            )
            return []
        items = payload.get("itemSummaries") or []
        total = payload.get("total") if isinstance(payload.get("total"), int) else None
        print(f"[EBAY_COMP_FETCH] status=200 q={_q_short!r} items={len(items)} total={total}")
        return items
    # Non-200: surface eBay's error body (truncated).
    body_snippet = (response.text or "")[:400].replace("\n", " ")
    print(f"[EBAY_COMP_FETCH] status={status} q={_q_short!r} error_body={body_snippet!r}")
    if status == 429:
        _last_was_rate_limited = True
        _consecutive_429s += 1
        if _consecutive_429s >= _RATE_LIMIT_TRIGGER_COUNT:
            # Walk up the escalation ladder. Each consecutive cooldown without
            # an intervening success doubles roughly: 60s, 5min, 15min, 30min,
            # 1h. After we successfully fetch again, _consecutive_cooldowns
            # resets to 0 (see status==200 branch).
            ladder_idx = min(_consecutive_cooldowns, len(_RATE_LIMIT_COOLDOWN_LADDER_SECONDS) - 1)
            cooldown_secs = _RATE_LIMIT_COOLDOWN_LADDER_SECONDS[ladder_idx]
            _rate_limit_cooldown_until_ts = time.time() + cooldown_secs
            _consecutive_cooldowns += 1
            print(
                f"[EBAY_COMP_FETCH] cooldown_triggered "
                f"consecutive_429s={_consecutive_429s} "
                f"consecutive_cooldowns={_consecutive_cooldowns} "
                f"cooldown_seconds={cooldown_secs:.0f}"
            )
            # Absorbed the 429 batch into a cooldown; reset the counter so the
            # next round of 429s (if they happen) can trigger another cooldown.
            _consecutive_429s = 0
    else:
        # Non-429 error (auth, 5xx, etc.) — not a rate-limit signal.
        _last_was_rate_limited = False
    return []


def infer_comp_sale_type(item: Dict[str, Any], pool_kind: str) -> str:
    """Normalized sale channel for valuation (Finding rows set comp_sale_type upstream)."""
    st = (item.get("comp_sale_type") or "").strip()
    if st:
        return st
    if pool_kind == "active_browse":
        return _classify_sale_type_browse(item)
    return "unknown"


def search_comp_pool(keywords: str, limit: int = 40) -> Tuple[List[Dict[str, Any]], str]:
    """
    Browse-only market comp pool.
    """
    items = search_market_comps_browse(keywords, limit=limit)
    return items, "active_browse"
