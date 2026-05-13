"""
comp_engine_v2.py — Standalone battle-tested market value engine.

Entry point:
    result = get_comp_value(title: str) -> CompResult

Features:
- Card title parser: player, year, product, parallel, print_run, graded status,
  card_number, rookie/auto/patch flags, sport
- 4-tier cascading eBay sold comp search with discount factors
- Filtering: raw/graded split, junk removal, 2-SD outlier removal,
  recency weighting, shipping normalization
- Confidence scoring: HIGH / MEDIUM / LOW
- 30-minute cache per query string
- Rate limit: wait 60 s and retry once on HTTP 429
- Never raises — always returns a CompResult (possibly with insufficient_data=True)

Use `streamlit run comp_tester.py` to test interactively.
"""

from __future__ import annotations

import os
import re
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

import ebay_search  # search_completed_items_finding, search_comp_pool

load_dotenv()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CACHE_TTL_SECS = 1800  # 30 minutes
RATE_LIMIT_PAUSE = 60  # seconds to wait after 429

# Tier discount factors
TIER3_DISCOUNT = 0.85  # parallel dropped
TIER4_DISCOUNT = 0.75  # year dropped + 180-day window

TIER1_MAX_DAYS = 90
TIER4_MAX_DAYS = 180

MIN_COMPS_REQUIRED = 2  # minimum accepted comps for a result

OUTLIER_SD_MULTIPLIER = 2.0  # remove comps > mean ± 2 SD
SHIPPING_CAP = 5.0           # max shipping added to price

# Grading services
_GRADERS = ("psa", "bgs", "sgc", "cgc", "hga", "gma", "ags")
_GRADING_RE = re.compile(
    r"\b(psa|bgs|sgc|cgc|hga|gma|ags)\s*(\d{1,2}(?:\.\d)?)\b", re.IGNORECASE
)
_ANY_GRADER_RE = re.compile(r"\b(psa|bgs|sgc|cgc|hga|gma|ags)\b", re.IGNORECASE)

# Junk listing patterns to reject
_JUNK_RE = re.compile(
    r"\b(lot|lots|break|box break|case break|pack|repack|redemption|"
    r"sealed box|sealed case|blaster|hobby box|jumbo box|"
    r"reprint|reprints|custom|fake|misprint|damaged|"
    r"\d+\s*cards?(?:\s+lot)?)\b",
    re.IGNORECASE,
)

# Sport keyword detection
_NFL_TOKENS = frozenset(
    ["nfl", "football", "quarterback", "qb", "receiver", "linebacker",
     "cornerback", "tight end", "running back", "wide receiver"]
)
_MLB_TOKENS = frozenset(
    ["mlb", "baseball", "pitcher", "outfield", "infield", "shortstop",
     "catcher", "home run", "batting"]
)
_NBA_TOKENS = frozenset(
    ["nba", "basketball", "guard", "forward", "center", "dunk", "three pointer"]
)

# Common product names for detection
_PRODUCTS = [
    "prizm", "select", "optic", "mosaic", "donruss", "contenders",
    "chronicles", "phoenix", "illusions", "elite", "certified",
    "prestige", "score", "stadium club", "bowman chrome", "bowman",
    "topps chrome", "topps", "heritage", "allen ginter", "gypsy queen",
    "tribute", "finest", "archives", "series 1", "series 2", "update",
    "upper deck", "fleer", "skybox", "hoops", "court kings",
    "national treasures", "immaculate", "noir", "flawless", "spectra",
    "absolute", "revolution", "phoenix", "flux", "recon",
    "obsidian", "luminance", "plates and patches", "plates & patches",
    "clearly donruss", "clearly authentic",
]

# Parallel phrase list — MORE SPECIFIC phrases MUST come before the generic ones
# they extend. e.g. "silver disco prizm" before "silver prizm" before "silver".
_PARALLELS = [
    # ── Prizm/Select subset/insert parallels (specific — must precede generic silver/prizm) ──
    "flashback silver prizm", "no huddle silver prizm",
    "silver disco prizm", "disco prizm",
    "neon green pulse prizm", "fast break prizm", "emergent prizm",
    "prizmatrix prizm", "color rush prizm",
    "club level silver prizm", "club level prizm",
    "scope silver prizm", "scope prizm",
    "all out silver prizm", "brilliance silver prizm",
    "fireworks silver prizm", "leveled up silver prizm",
    "next level silver prizm",
    # ── True base Prizm silver variants ──
    "true silver prizm", "true silver", "silver prizm", "prizm silver",
    # ── High-end one-of-one / rare ──
    "white sparkle", "gold vinyl", "black finite", "black prizm", "gold prizm",
    "superfractor", "atomic refractor", "orange refractor", "black refractor",
    "red refractor", "gold refractor", "lava lamp refractor",
    "printing plates", "rookie patch autograph", "shimmer autograph",
    "rated rookie autograph", "gold die-cut", "black die-cut",
    # ── Named art/color parallels ──
    "cherry blossom", "prizmania", "tie-dye", "manga", "aurora",
    "color blast", "kaboom", "blue wave", "red wave", "green wave",
    "purple wave", "orange wave", "gold wave", "silver wave",
    "blue ice", "red ice", "green ice", "purple ice", "orange ice",
    "snakeskin", "dragonscale", "tiger stripe", "zebra", "elephant", "leopard",
    "hyper", "nebula", "downtown", "uptown", "holo", "refractor",
    "prizmatrix signatures", "sensational signatures", "flashback signatures",
    "rookie signatures", "dual autograph", "triple autograph",
    "kaleidoscopic", "fireworks", "groovy", "talismen",
    "rookie debut patch autograph", "topps chrome authentics",
    "radiating rookies", "all-etch rookie rush",
    # ── Generic color parallels (must come AFTER more specific phrases above) ──
    "xfractor", "cracked ice", "aqua", "purple", "red",
    "blue", "orange", "green", "gold", "silver", "pink", "cyan",
    "prizm", "wave", "scope",
]

# Synonym groups: these parallel strings all refer to the same base Prizm silver card
_SILVER_PRIZM_FORMS = frozenset({
    "silver prizm", "prizm silver", "true silver prizm", "true silver",
    "silver", "base prizm", "base",
})

# Subset/series words: if present in comp title but NOT in target title at Tier 1/2,
# the comp is from a different subset and must be rejected.
_PRIZM_SUBSET_DISQUALIFIERS = frozenset({
    # Prizm-branded subsets
    "flashback", "no huddle", "disco", "prizmatic", "prizmania",
    "emergent", "fast break", "color rush", "color blast", "neon green pulse",
    "prize rings", "downtown", "uptown", "brilliance", "fireworks",
    "all out", "leveled up", "next level", "holo silver", "all purpose",
    # Select-specific subset tiers
    "scope", "club level", "courtside",
})

# ---------------------------------------------------------------------------
# Parallel / product comparison helpers
# ---------------------------------------------------------------------------

def _parallels_equivalent(target_p: Optional[str], comp_p: Optional[str]) -> bool:
    """
    True if target and comp parallels refer to the same card.
    Handles the Silver Prizm synonym group (Silver = Silver Prizm = Base Prizm).
    All other parallels must match exactly.
    """
    t = (target_p or "").lower().strip()
    c = (comp_p or "").lower().strip()
    if t == c:
        return True
    if t in _SILVER_PRIZM_FORMS and c in _SILVER_PRIZM_FORMS:
        return True
    return False


def _has_subset_disqualifier(comp_title_lower: str, target_title_lower: str) -> bool:
    """
    True if comp title contains a Prizm subset word that is absent from the target.
    Catches 'Flashback Silver Prizm', 'No Huddle Silver Disco Prizm', 'Prizmatic', etc.
    """
    for word in _PRIZM_SUBSET_DISQUALIFIERS:
        if word in comp_title_lower and word not in target_title_lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ParsedCard:
    """Structured attributes extracted from a card title."""
    raw_title: str = ""
    player_name: str = ""
    year: Optional[str] = None
    product: Optional[str] = None
    parallel: Optional[str] = None
    print_run: Optional[int] = None          # e.g. 10 from "/10"
    is_graded: bool = False
    grading_company: Optional[str] = None
    grade: Optional[str] = None              # e.g. "10", "9.5"
    grade_key: Optional[str] = None          # e.g. "psa_10"
    card_number: Optional[str] = None
    is_rookie: bool = False
    is_auto: bool = False
    is_patch: bool = False
    sport: Optional[str] = None              # "NFL" | "MLB" | "NBA" | None


@dataclass
class CompRecord:
    """A single sold comp used in or rejected from MV calculation."""
    title: str
    price: float
    shipping: float
    total: float
    age_days: Optional[float]
    weight: float
    accepted: bool
    reject_reason: str = ""


@dataclass
class CompResult:
    """Full output from get_comp_value()."""
    # Inputs
    raw_title: str = ""
    parsed_card: Optional[ParsedCard] = None

    # Tier used
    match_tier: int = 0          # 1–4; 0 = no result
    tier_description: str = ""

    # MV computation
    comp_count: int = 0
    comps_used: List[CompRecord] = field(default_factory=list)
    comps_rejected: List[CompRecord] = field(default_factory=list)
    raw_average: float = 0.0     # weighted average before discount
    discount_applied: float = 0.0  # e.g. 0.15 for Tier3
    final_market_value: float = 0.0
    market_value: float = 0.0    # alias for final_market_value
    date_range_used: int = TIER1_MAX_DAYS

    # Confidence
    confidence: str = "LOW"      # HIGH | MEDIUM | LOW
    low_confidence: bool = True

    # Status
    insufficient_data: bool = False
    error: str = ""

    # Price spread
    price_std_dev: float = 0.0
    price_cv: float = 0.0        # coefficient of variation (std/mean)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
_RESULT_CACHE: Dict[str, Tuple[float, "CompResult"]] = {}


def _card_signature(parsed: "ParsedCard") -> str:
    """Stable cache key based on card identity, not raw query string."""
    parts = [
        (parsed.player_name or "").lower().strip(),
        parsed.year or "",
        (parsed.product or "").lower().strip(),
        (parsed.parallel or "").lower().strip(),
        str(parsed.print_run) if parsed.print_run else "",
        "graded" if parsed.is_graded else "raw",
        parsed.grade or "",
    ]
    return "|".join(parts)


def _cached_search(keywords: str) -> List[Dict[str, Any]]:
    """
    Search completed items, with 30-minute in-process cache.
    Retries once after 60 s on rate limit.
    """
    now = time.time()
    if keywords in _CACHE:
        ts, items = _CACHE[keywords]
        if now - ts < CACHE_TTL_SECS:
            return items

    items = _do_search(keywords)
    _CACHE[keywords] = (now, items)
    return items


def _finding_api_configured() -> bool:
    """True if any Finding API credential is present in the environment."""
    return bool(
        os.getenv("EBAY_FINDING_APP_ID") or
        os.getenv("EBAY_APP_ID") or
        os.getenv("EBAY_CLIENT_ID")
    )


class _RateLimitError(Exception):
    """Raised when eBay Finding API signals a rate limit (errorId 10001 / HTTP 429)."""


def _do_search(keywords: str) -> List[Dict[str, Any]]:
    """
    Execute Finding API sold-listings search. Never falls back to Browse active listings.
    Returns only SOLD comps with itemSource='finding_sold'.
    Retries once after RATE_LIMIT_PAUSE seconds on any rate-limit signal (HTTP 429 or
    eBay errorId 10001 which arrives as HTTP 500).
    Raises _RateLimitError if both attempts are rate-limited.
    """
    try:
        items = ebay_search.search_completed_items_finding(keywords, limit=80)
        return items or []
    except Exception as exc:
        msg = str(exc).lower()
        if "429" in msg or "rate" in msg or "10001" in msg:
            print(f"[COMP] eBay rate limit hit — waiting {RATE_LIMIT_PAUSE}s then retrying…")
            time.sleep(RATE_LIMIT_PAUSE)
            try:
                items = ebay_search.search_completed_items_finding(keywords, limit=80)
                return items or []
            except Exception as exc2:
                msg2 = str(exc2).lower()
                if "429" in msg2 or "rate" in msg2 or "10001" in msg2:
                    raise _RateLimitError("eBay Finding API rate limit — daily quota may be exhausted") from exc2
                return []
        return []


# ---------------------------------------------------------------------------
# Title parser
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _extract_year(title: str) -> Optional[str]:
    m = re.search(r"\b(19[8-9]\d|20[0-3]\d)\b", title)
    return m.group(0) if m else None


def _extract_card_number(title: str) -> Optional[str]:
    for pat in (
        r"#\s*([A-Z0-9]{1,6})\b",
        r"\bno\.?\s*([A-Z0-9]{1,6})\b",
        r"\bcard\s*#?\s*(\d{1,4})\b",
    ):
        m = re.search(pat, title, flags=re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _extract_print_run(title: str) -> Optional[int]:
    """Extract /10, /25, /99 etc. from title."""
    m = re.search(r"/\s*(\d{1,4})\b", title)
    if m:
        val = int(m.group(1))
        if 1 <= val <= 9999:
            return val
    return None


def _extract_grade(title: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """Returns (is_graded, grading_company, grade, grade_key)."""
    m = _GRADING_RE.search(title)
    if m:
        company = m.group(1).upper()
        grade_str = m.group(2)
        try:
            g = float(grade_str)
            grade_str = str(int(g)) if g == int(g) else grade_str
        except ValueError:
            pass
        grade_key = f"{company.lower()}_{grade_str}"
        return True, company, grade_str, grade_key
    if _ANY_GRADER_RE.search(title):
        m2 = _ANY_GRADER_RE.search(title)
        company = m2.group(1).upper()
        return True, company, None, f"{company.lower()}_unknown"
    return False, None, None, None


def _extract_product(title_lower: str) -> Optional[str]:
    for prod in sorted(_PRODUCTS, key=len, reverse=True):
        if prod in title_lower:
            return prod
    return None


def _extract_parallel(title_lower: str) -> Optional[str]:
    for phrase in _PARALLELS:
        if phrase in title_lower:
            return phrase
    return None


def _detect_sport(title: str) -> Optional[str]:
    lower = title.lower()
    tokens = set(re.findall(r"\b\w+\b", lower))
    if tokens & _NFL_TOKENS:
        return "NFL"
    if tokens & _NBA_TOKENS:
        return "NBA"
    if tokens & _MLB_TOKENS:
        return "MLB"
    # Product-based heuristic
    if any(k in lower for k in ("prizm", "select", "mosaic", "contenders", "donruss", "optic")):
        # These sets exist for all sports — no inference
        pass
    if any(k in lower for k in ("bowman", "topps", "heritage", "gypsy queen", "allen ginter")):
        return "MLB"
    return None


def _extract_player_name(title: str, year: Optional[str], product: Optional[str]) -> str:
    """
    Heuristic: strip known non-player tokens, return first 2-3 capitalized words.
    This is best-effort; exact player name is often the first words before year/set info.
    """
    low = title.lower()

    # Remove grader tokens
    low = _GRADING_RE.sub("", low)
    low = _ANY_GRADER_RE.sub("", low)

    # Remove year
    if year:
        low = low.replace(year, "")

    # Remove product
    if product:
        low = low.replace(product, "")

    # Remove common noise tokens
    for noise in (
        # Grading / condition
        "rookie", "rc", "auto", "autograph", "patch", "relic",
        "refractor", "prizm", "insert", "card", "football", "baseball",
        "basketball", "nfl", "mlb", "nba", "psa", "bgs", "sgc",
        "panini", "topps", "bowman", "donruss", "sp", "#",
        "gem", "mint", "graded", "slab", "short print",
        # Color parallel words — these appear AFTER the player name and bleed in
        "silver", "gold", "blue", "red", "orange", "green", "purple",
        "pink", "black", "white", "aqua", "cyan", "yellow", "brown",
        "gray", "grey", "neon", "hyper", "disco", "camo", "tiger",
        "lava", "ice", "emerald", "ruby", "sapphire", "amber",
        "bronze", "copper", "platinum",
        # Set tier / subset words that appear after player name
        "concourse", "premier", "scope", "hanger", "clutch", "power",
        "cracked", "xfractor", "wave", "velocity", "explosion",
        "mosaic", "select", "optic", "chronicles", "illusions",
        "contenders", "certified", "absolute", "spectra",
        "immaculate", "national", "treasures", "flawless",
        "prizms", "base", "variation",
    ):
        low = re.sub(rf"\b{re.escape(noise)}\b", "", low)

    # Remove /NNN print runs
    low = re.sub(r"/\s*\d{1,4}", "", low)
    # Remove card numbers
    low = re.sub(r"#\s*[A-Z0-9]{1,6}", "", low, flags=re.IGNORECASE)

    # Clean up
    low = re.sub(r"[^a-z\s'-]", " ", low)
    low = re.sub(r"\s+", " ", low).strip()

    # Take first 1-3 words that look like a name (title-case words in original)
    # Re-run on original for proper capitalization
    words = low.split()
    # Filter out single letters and very short junk
    name_words = [w for w in words if len(w) > 1][:3]
    return " ".join(name_words).title().strip()


def parse_card_title(title: str) -> ParsedCard:
    """
    Extract structured attributes from a raw eBay card listing title.
    Best-effort — never raises.
    """
    if not title:
        return ParsedCard(raw_title=title)

    title_clean = title.strip()
    low = _norm(title_clean)

    year = _extract_year(low)
    product = _extract_product(low)
    parallel = _extract_parallel(low)
    print_run = _extract_print_run(low)
    card_number = _extract_card_number(title_clean)
    is_graded, grading_co, grade, grade_key = _extract_grade(title_clean)
    is_rookie = bool(re.search(r"\b(rookie|rc)\b", low))
    is_auto = bool(re.search(r"\b(auto|autograph|signed|ink)\b", low))
    is_patch = bool(re.search(r"\b(patch|relic|mem|memorabilia|jersey|bat|shoe|helmet)\b", low))
    sport = _detect_sport(title_clean)
    player = _extract_player_name(title_clean, year, product)

    return ParsedCard(
        raw_title=title_clean,
        player_name=player,
        year=year,
        product=product,
        parallel=parallel,
        print_run=print_run,
        is_graded=is_graded,
        grading_company=grading_co,
        grade=grade,
        grade_key=grade_key,
        card_number=card_number,
        is_rookie=is_rookie,
        is_auto=is_auto,
        is_patch=is_patch,
        sport=sport,
    )


# ---------------------------------------------------------------------------
# Query builders (4 tiers)
# ---------------------------------------------------------------------------

def _build_tier1_query(p: ParsedCard) -> str:
    """Exact: player + year + product + parallel + /print_run."""
    parts = []
    if p.player_name:
        parts.append(p.player_name)
    if p.year:
        parts.append(p.year)
    if p.product:
        parts.append(p.product)
    if p.parallel:
        parts.append(p.parallel)
    if p.print_run:
        parts.append(f"/{p.print_run}")
    return " ".join(parts)


def _build_tier2_query(p: ParsedCard) -> str:
    """Relax print_run: player + year + product + parallel."""
    parts = []
    if p.player_name:
        parts.append(p.player_name)
    if p.year:
        parts.append(p.year)
    if p.product:
        parts.append(p.product)
    if p.parallel:
        parts.append(p.parallel)
    return " ".join(parts)


def _build_tier3_query(p: ParsedCard) -> str:
    """Drop parallel: player + year + product."""
    parts = []
    if p.player_name:
        parts.append(p.player_name)
    if p.year:
        parts.append(p.year)
    if p.product:
        parts.append(p.product)
    return " ".join(parts)


def _build_tier4_query(p: ParsedCard) -> str:
    """Drop year: player + product (broadest, 180-day window)."""
    parts = []
    if p.player_name:
        parts.append(p.player_name)
    if p.product:
        parts.append(p.product)
    elif p.year:
        # If no product, use player + year still
        parts.append(p.year)
    return " ".join(parts) if parts else (p.player_name or p.raw_title[:40])


# ---------------------------------------------------------------------------
# Comp filtering
# ---------------------------------------------------------------------------

def _item_price(item: Dict[str, Any]) -> float:
    for key in ("price", "currentBidPrice", "bidPrice"):
        p = item.get(key)
        if isinstance(p, dict):
            v = p.get("value")
        else:
            v = p
        if v is None:
            continue
        try:
            return float(str(v).replace("$", "").replace(",", "").strip())
        except (TypeError, ValueError):
            continue
    return 0.0


def _item_shipping(item: Dict[str, Any]) -> float:
    """Extract shipping cost, cap at SHIPPING_CAP."""
    for key in ("shippingOptions", "shipping"):
        s = item.get(key)
        if isinstance(s, list) and s:
            s = s[0]
        if isinstance(s, dict):
            sc = s.get("shippingCost") or s.get("cost") or {}
            if isinstance(sc, dict):
                v = sc.get("value")
                if v is not None:
                    try:
                        return min(float(str(v).replace("$", "")), SHIPPING_CAP)
                    except (TypeError, ValueError):
                        pass
    return 0.0


def _item_age_days(item: Dict[str, Any]) -> Optional[float]:
    """
    Days since sale. Returns None if date is missing or unparseable.

    Handles all eBay date formats:
      "2024-03-15T14:23:00.000Z"        (Finding API, 3-digit ms + Z)
      "2024-03-15T14:23:00.000000Z"     (6-digit microseconds + Z)
      "2024-03-15T14:23:00Z"            (no fractional seconds)
      "2024-03-15T14:23:00+00:00"       (UTC offset form)
      "2024-03-15"                       (date only)
    """
    for key in ("itemEndDate", "endTime", "soldDate", "lastSoldDate", "date"):
        raw = item.get(key)
        if not raw:
            continue
        if isinstance(raw, list):
            raw = raw[0] if raw else None
        if not raw:
            continue
        try:
            raw_s = str(raw).strip()
            if not raw_s:
                continue

            # Strategy 1: normalize trailing Z → +00:00, then fromisoformat
            # (Python 3.7-3.10 don't support Z in fromisoformat; 3.11+ do)
            normalized = raw_s
            if normalized.endswith("Z"):
                normalized = normalized[:-1] + "+00:00"
            try:
                dt = datetime.fromisoformat(normalized)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - dt).total_seconds() / 86400
                if age >= 0:          # only past dates count as sold
                    return age
                # Future date (active Browse listing end) — not a sold comp date
                continue
            except ValueError:
                pass

            # Strategy 2: manual strptime with multiple format attempts
            for fmt in (
                "%Y-%m-%dT%H:%M:%S.%fZ",   # 3 or 6 digit ms + Z
                "%Y-%m-%dT%H:%M:%SZ",       # no ms + Z
                "%Y-%m-%dT%H:%M:%S.%f",     # ms, no timezone
                "%Y-%m-%dT%H:%M:%S",        # no ms, no tz
                "%Y-%m-%d",                 # date only
            ):
                for s in (raw_s, raw_s[:26], raw_s[:19], raw_s[:10]):
                    try:
                        dt = datetime.strptime(s, fmt)
                        dt = dt.replace(tzinfo=timezone.utc)
                        age = (datetime.now(timezone.utc) - dt).total_seconds() / 86400
                        if age >= 0:
                            return age
                    except ValueError:
                        continue

        except Exception:
            continue
    return None


def _recency_weight(age_days: Optional[float]) -> float:
    """Weight based on how recent the sale is."""
    if age_days is None:
        return 0.5  # unknown age: moderate weight
    if age_days <= 30:
        return 1.0
    if age_days <= 60:
        return 0.75
    if age_days <= 90:
        return 0.5
    if age_days <= 180:
        return 0.25
    return 0.1


def _is_junk(title: str) -> bool:
    """True if listing appears to be a lot, break, or sealed product."""
    return bool(_JUNK_RE.search(title or ""))


def _grade_key_from_title(title: str) -> Optional[str]:
    """Same as _extract_grade but just the key."""
    _, _, _, gk = _extract_grade(title)
    return gk


def filter_comps(
    items: List[Dict[str, Any]],
    target: ParsedCard,
    max_age_days: int,
    tier_num: int = 0,
) -> Tuple[List[CompRecord], List[CompRecord]]:
    """
    Apply full filtering pipeline.
    Returns (accepted, rejected) lists of CompRecord.

    tier_num controls strictness:
      1 or 2 → enforce product + parallel + subset matching
      3 or 4 → enforce product only (parallel intentionally dropped)
    """
    accepted: List[CompRecord] = []
    rejected: List[CompRecord] = []

    target_grade_key = target.grade_key  # None means raw
    target_title_lower = (target.raw_title or "").lower()
    strict = tier_num in (1, 2)

    for item in items:
        title = str(item.get("title") or "").strip()
        if not title:
            continue

        price = _item_price(item)
        shipping = _item_shipping(item)
        total = price + shipping
        age = _item_age_days(item)

        def reject(reason: str) -> None:
            rejected.append(CompRecord(
                title=title,
                price=price,
                shipping=shipping,
                total=total,
                age_days=age,
                weight=0.0,
                accepted=False,
                reject_reason=reason,
            ))

        # 1. Price must be positive
        if price <= 0:
            reject("zero price")
            continue

        # 2. Age gate
        if age is not None and age > max_age_days:
            reject(f"too old ({age:.0f}d > {max_age_days}d)")
            continue

        # 2b. No sold date handling
        # Finding API items always include a sold date — if missing, parsing failed → reject
        # Browse API active listings have no sold date by design → allow with stale weight
        if age is None and item.get("itemSource") == "finding_sold":
            reject("no sold date")
            continue

        # 3. Junk listing
        if _is_junk(title):
            reject("junk listing (lot/break/sealed)")
            continue

        # 4. Product mismatch — never cross products (all tiers)
        if target.product:
            comp_product = _extract_product(title.lower())
            if comp_product and comp_product != target.product:
                reject(f"product mismatch ({comp_product} != {target.product})")
                continue

        # 5. Raw vs graded split — must match target graded status exactly
        comp_graded = bool(_ANY_GRADER_RE.search(title))
        if target.is_graded and not comp_graded:
            reject("target is graded, comp is raw")
            continue
        if not target.is_graded and comp_graded:
            reject("target is raw, comp is graded")
            continue

        # 6. If graded, must match exact grade key
        if target.is_graded and target_grade_key:
            comp_gk = _grade_key_from_title(title)
            if comp_gk and comp_gk != target_grade_key:
                reject(f"grade mismatch ({comp_gk} != {target_grade_key})")
                continue

        # 7. Parallel mismatch — strict at Tier 1 and 2 only
        if strict and target.parallel:
            comp_parallel = _extract_parallel(title.lower())
            if not _parallels_equivalent(target.parallel, comp_parallel):
                reject(f"parallel mismatch ({comp_parallel or 'none'} != {target.parallel})")
                continue
            # Also reject known subset/insert variations (e.g. Flashback Silver Prizm)
            if _has_subset_disqualifier(title.lower(), target_title_lower):
                reject("subset/insert mismatch (different Prizm series)")
                continue

        weight = _recency_weight(age)

        accepted.append(CompRecord(
            title=title,
            price=price,
            shipping=shipping,
            total=total,
            age_days=age,
            weight=weight,
            accepted=True,
        ))

    # 6. Outlier removal: 2 SD from mean of totals
    if len(accepted) >= 4:
        totals = [c.total for c in accepted]
        mean = statistics.mean(totals)
        sd = statistics.stdev(totals)
        threshold_low = mean - OUTLIER_SD_MULTIPLIER * sd
        threshold_high = mean + OUTLIER_SD_MULTIPLIER * sd

        kept: List[CompRecord] = []
        for c in accepted:
            if threshold_low <= c.total <= threshold_high:
                kept.append(c)
            else:
                c.accepted = False
                c.reject_reason = f"outlier (${c.total:.2f}, mean=${mean:.2f}, sd=${sd:.2f})"
                rejected.append(c)
        accepted = kept

    return accepted, rejected


# ---------------------------------------------------------------------------
# Weighted average
# ---------------------------------------------------------------------------

def _weighted_average(comps: List[CompRecord]) -> float:
    """Weighted mean of comp totals using recency weights."""
    total_weight = sum(c.weight for c in comps)
    if total_weight <= 0:
        return statistics.mean([c.total for c in comps]) if comps else 0.0
    return sum(c.total * c.weight for c in comps) / total_weight


def _price_stats(comps: List[CompRecord]) -> Tuple[float, float]:
    """Returns (std_dev, coefficient_of_variation)."""
    if len(comps) < 2:
        return 0.0, 0.0
    prices = [c.total for c in comps]
    sd = statistics.stdev(prices)
    mean = statistics.mean(prices)
    cv = (sd / mean * 100) if mean > 0 else 0.0
    return sd, cv


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

def _compute_confidence(
    tier: int,
    comp_count: int,
    age_days_oldest: Optional[float],
    cv: float,
) -> Tuple[str, bool]:
    """
    Returns (confidence_label, low_confidence_bool).

    HIGH:   Tier1 or Tier2, >=5 comps, oldest <30d, CV <20%
    MEDIUM: Tier1 or Tier2, 2–4 comps OR older comps OR CV 20-40%
    LOW:    Tier3 or Tier4, OR <2 comps, OR CV >40%, OR 180-day window
    """
    if comp_count < MIN_COMPS_REQUIRED:
        return "LOW", True

    if tier in (1, 2):
        if comp_count >= 5 and (age_days_oldest or 999) <= 30 and cv < 20:
            return "HIGH", False
        if comp_count >= 2 and cv <= 40:
            return "MEDIUM", False
        return "LOW", True

    # Tier 3 or 4 — always lower confidence
    if comp_count >= 5 and cv < 20:
        return "MEDIUM", False
    return "LOW", True


# ---------------------------------------------------------------------------
# Core cascading engine
# ---------------------------------------------------------------------------

def get_comp_value(title: str) -> CompResult:
    """
    Main entry point. Parse title, run 4-tier cascade, return CompResult.
    Never raises. Results cached 30 minutes by card signature.
    """
    result = CompResult(raw_title=title)

    # Guard: Finding API credential must be present — no silent Browse fallback
    if not _finding_api_configured():
        result.insufficient_data = True
        result.confidence = "LOW"
        result.low_confidence = True
        result.error = (
            "Missing EBAY_FINDING_APP_ID in .env — comp engine requires sold listing data. "
            "Add: EBAY_FINDING_APP_ID=<your App ID from eBay Developer Portal> to your .env file."
        )
        return result

    try:
        parsed = parse_card_title(title)
        result.parsed_card = parsed

        # Check result-level cache (by card identity, not query string)
        sig = _card_signature(parsed)
        now = time.time()
        if sig in _RESULT_CACHE:
            cached_ts, cached_result = _RESULT_CACHE[sig]
            if now - cached_ts < CACHE_TTL_SECS:
                return cached_result

        # Build queries for each tier
        queries = [
            (1, _build_tier1_query(parsed), 0.0,   TIER1_MAX_DAYS,
             "Exact: player + year + product + parallel + /print_run"),
            (2, _build_tier2_query(parsed), 0.0,   TIER1_MAX_DAYS,
             "Relaxed: player + year + product + parallel (no print run)"),
            (3, _build_tier3_query(parsed), 1.0 - TIER3_DISCOUNT, TIER1_MAX_DAYS,
             "Broad: player + year + product (parallel dropped, 0.85× discount)"),
            (4, _build_tier4_query(parsed), 1.0 - TIER4_DISCOUNT, TIER4_MAX_DAYS,
             "Broadest: player + product (year dropped, 180d, 0.75× discount)"),
        ]

        # Skip Tier1 if it's identical to Tier2 (no print_run to add)
        seen_queries: set = set()

        for tier_num, query, discount_factor, max_days, tier_desc in queries:
            if not query.strip():
                continue

            query_key = query.strip().lower()
            if query_key in seen_queries:
                continue
            seen_queries.add(query_key)

            raw_items = _cached_search(query)
            accepted, rejected = filter_comps(raw_items, parsed, max_days, tier_num)

            if len(accepted) < MIN_COMPS_REQUIRED:
                # Accumulate rejected for reporting even if we keep going
                result.comps_rejected.extend(rejected)
                continue

            # Enough comps — compute MV
            wav = _weighted_average(accepted)
            sd, cv = _price_stats(accepted)
            discount = discount_factor
            mv = wav * (1.0 - discount)

            oldest_age = max(
                (c.age_days for c in accepted if c.age_days is not None),
                default=None,
            )
            confidence, low_conf = _compute_confidence(tier_num, len(accepted), oldest_age, cv)

            result.match_tier = tier_num
            result.tier_description = tier_desc
            result.comp_count = len(accepted)
            result.comps_used = accepted
            result.comps_rejected = result.comps_rejected + rejected
            result.raw_average = round(wav, 2)
            result.discount_applied = round(discount, 4)
            result.final_market_value = round(mv, 2)
            result.market_value = round(mv, 2)
            result.date_range_used = max_days
            result.confidence = confidence
            result.low_confidence = low_conf
            result.insufficient_data = False
            result.price_std_dev = round(sd, 2)
            result.price_cv = round(cv, 1)
            _RESULT_CACHE[sig] = (time.time(), result)
            return result

        # No tier produced enough comps
        result.insufficient_data = True
        result.confidence = "LOW"
        result.low_confidence = True
        result.match_tier = 0
        result.tier_description = "No tier produced sufficient comps"

    except _RateLimitError as exc:
        result.insufficient_data = True
        result.error = f"eBay API rate limited — {exc}. Try again later."
        result.confidence = "LOW"
        result.low_confidence = True
    except Exception as exc:
        result.insufficient_data = True
        result.error = str(exc)
        result.confidence = "LOW"
        result.low_confidence = True

    return result


# ---------------------------------------------------------------------------
# Convenience: invalidate cache for a query
# ---------------------------------------------------------------------------

def clear_cache() -> None:
    """Clear all cached comp results."""
    global _CACHE, _RESULT_CACHE
    _CACHE = {}
    _RESULT_CACHE = {}


def get_market_value_for_item(title: str, limit: int = 40) -> Dict[str, Any]:
    """
    Compatibility wrapper — same interface as market_value_engine.get_market_value_for_item().
    Returns a plain dict so callers don't need to know about CompResult.
    """
    result = get_comp_value(title)

    # Recency: oldest comp age in days
    if result.comps_used:
        ages = [c.age_days for c in result.comps_used if c.age_days is not None]
        oldest = max(ages) if ages else None
        if oldest is None:
            recency = "unknown"
        elif oldest <= 30:
            recency = "recent"
        elif oldest <= 90:
            recency = "moderate"
        else:
            recency = "stale"
    else:
        recency = "unknown"

    # Raw vs graded mix
    graded_count = sum(1 for c in result.comps_used if c.is_graded) if result.comps_used else 0
    raw_count = (result.comp_count or 0) - graded_count
    if graded_count > 0 and raw_count > 0:
        raw_vs_graded = "mixed"
    elif graded_count > 0:
        raw_vs_graded = "graded"
    elif raw_count > 0:
        raw_vs_graded = "raw"
    else:
        raw_vs_graded = "unknown"

    return {
        "market_value": result.final_market_value,
        "confidence": result.confidence,
        "low_confidence": result.low_confidence,
        "comp_count": result.comp_count or 0,
        "comp_pool": result.comp_count or 0,
        "match_tier": result.match_tier,
        "tier_description": result.tier_description,
        "insufficient_data": result.insufficient_data,
        "comp_recency": recency,
        "raw_vs_graded": raw_vs_graded,
        "price_cv": result.price_cv,
        "raw_average": result.raw_average,
        "error": result.error,
        "source": "comp_engine_v2",
    }
