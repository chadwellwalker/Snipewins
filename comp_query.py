"""
Precise eBay comp search query builder and listing profile parsing.

Used to build specific marketplace queries (sold or active) and to filter/score comp titles.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

import parallel_vocab

# Major product lines — used for set detection and cross-set rejection.
SET_KEYWORDS: Tuple[str, ...] = (
    "national treasures",
    "immaculate",
    "flawless",
    "spectra",
    "absolute",
    "totally certified",
    "prizm",
    "select",
    "optic",
    "mosaic",
    "donruss",
    "contenders",
    "chronicles",
    "phoenix",
    "illusions",
    "elite",
    "certified",
    "prestige",
    "score",
    "stadium club",
    "bowman",
    "topps chrome",
    "topps",
    "leaf",
    "sage",
)

BRAND_KEYWORDS: Tuple[str, ...] = ("panini", "topps", "bowman", "leaf", "upper deck", "futera")

LISTING_TYPE_SINGLE_CARD = "SINGLE_CARD"
LISTING_TYPE_MULTI_CARD_LOT = "MULTI_CARD_LOT"
LISTING_TYPE_BREAK_OR_SPOT = "BREAK_OR_SPOT"
LISTING_TYPE_SEALED_WAX_OR_BOX = "SEALED_WAX_OR_BOX"
LISTING_TYPE_TEAM_SET_OR_COLLECTION = "TEAM_SET_OR_COLLECTION"
LISTING_TYPE_UNKNOWN_AMBIGUOUS = "UNKNOWN_AMBIGUOUS"

# Parallel / insert phrases (longer first for matching).
PARALLEL_PHRASES: Tuple[str, ...] = (
    # Base / silver
    "true silver prizm",
    "true silver",
    "silver prizm",
    "prizm silver",
    "white sparkle",
    # Topps Chrome specific parallels - keep ahead of generic refractor
    "negative refractor",
    "x-fractor",
    "x fractor",
    "prism refractor",
    "raywave refractor",
    "raywave",
    "logofractor",
    "mini diamond refractor",
    "mini diamond",
    "sonic refractor",
    "sepia refractor",
    "lava refractor",
    # Animal prints
    "snakeskin",
    "dragonscale",
    "tiger stripe",
    "zebra",
    "elephant",
    "leopard",
    # Color parallels
    "blue ice",
    "red ice",
    "green ice",
    "purple ice",
    "orange ice",
    "gold vinyl",
    "black finite",
    "color blast duals",
    "color blast",
    "kaboom",
    "blue wave",
    "red wave",
    "green wave",
    "purple wave",
    "orange wave",
    "gold wave",
    "silver wave",
    "hyper",
    # NFL case hits
    "rookie patch autograph",
    "patch auto",
    "auto patch",
    "shimmer autograph",
    "rated rookie autograph",
    "gold die-cut",
    "black die-cut",
    "cherry blossom",
    "prizmania",
    "tie-dye",
    "manga",
    "aurora",
    "profiles",
    "nebula",
    "downtown",
    "uptown",
    "holo",
    "rpa",
    # MLB case hits
    "superfractor",
    "orange refractor",
    "black refractor",
    "red refractor",
    "printing plates",
    "atomic refractor",
    "lava lamp refractor",
    "gold refractor",
    "radiating rookies",
    "all-etch rookie rush",
    "rookie debut patch autograph",
    "sunday spectacle",
    "topps chrome authentics",
    # NBA case hits
    "prizmatrix signatures",
    "sensational signatures",
    "flashback signatures",
    "rookie signatures",
    "dual autograph",
    "triple autograph",
    "kaleidoscopic",
    "fireworks",
    "groovy",
    "gold prizm",
    "black prizm",
    "talismen",
    "rookie patch autograph",
    # Generic
    "refractor",
)

PRODUCT_FAMILY_PHRASES: Tuple[str, ...] = (
    "national treasures",
    "immaculate",
    "flawless",
    "spectra",
    "absolute",
    "totally certified",
    "donruss optic",
    "topps chrome black",
    "topps cosmic chrome",
    "topps chrome sapphire",
    "topps finest",
    "topps chrome",
    "bowman chrome",
    "stadium club",
)

SUBSET_FAMILY_PHRASES: Tuple[str, ...] = (
    "sunday spectacle",
    "gold team",
    "color blast duals",
    "color blast",
    "downtown",
    "kaboom",
    "all aces",
    "ace of diamonds",
    "ace of diamond",
    "net marvels",
    "bomb squad",
    "money men",
    "gold vinyl",
    "black finite",
    "radiating rookies",
    "all-etch rookie rush",
    "rookie rush",
    "rookie debut patch autograph",
    "topps chrome authentics",
    "prizmatrix signatures",
    "sensational signatures",
    "flashback signatures",
    "rookie signatures",
    "dual autograph",
    "triple autograph",
    "kaleidoscopic",
    "razzle dazzle",
    "fireworks",
    "groovy",
    "talismen",
    "profiles",
    "manga",
    "aura",
    "aurora",
    "prizmania",
    "genesis",
    "international",
    "stained glass",
    "power players",
    "all etch",
    "cosmic constellation",
    "planetary pursuit",
    "ultra violet all stars",
    "ultra-violet all stars",
    "beam team",
    "1990 topps",
    "fortune 15",
)

_CHECKLIST_ROLE_PHRASES: Tuple[str, ...] = (
    "all-star rookie",
    "rookie cup",
    "future stars",
    "1984 topps",
    "1984 chrome",
    "batting",
    "hitting",
    "pitching",
)

_GRADE_COMPANY_PATTERN = r"(?:psa|gma|sgc|bgs|bvg|csg|cgc)"
_TOPPS_CHROME_FAMILY_PHRASES: Tuple[str, ...] = (
    "topps chrome black",
    "topps cosmic chrome",
    "topps chrome sapphire",
    "topps finest",
    "topps chrome",
    "bowman chrome",
)
_TOPPS_RC_OPTIONAL_ROLE_TOKENS: Tuple[str, ...] = ("pitching", "batting", "hitting")
_TOPPS_RC_OPTIONAL_DECORATION_TOKENS: Tuple[str, ...] = ("rc", "rookie", "gem mint", "gem mt")
EXACT_ARCHETYPE_BASE_CHROME_RC_PSA10 = "BASE_CHROME_RC_PSA10"
EXACT_ARCHETYPE_CHROME_PARALLEL_SERIAL = "CHROME_PARALLEL_SERIAL"
_BASE_CHROME_RC_PSA10_PRODUCT_FAMILIES: FrozenSet[str] = frozenset({
    "topps_chrome",
    "bowman_chrome",
    "topps_finest",
})
_CHROME_PARALLEL_SERIAL_PRODUCT_FAMILIES: FrozenSet[str] = frozenset({
    "topps_chrome",
    "bowman_chrome",
    "topps_finest",
})
_EXACT_SUBJECT_IDENTITY_CACHE: Dict[str, Dict[str, str]] = {}
_MLB_TEAM_QUERY_TOKENS: FrozenSet[str] = frozenset({
    "angels", "astros", "athletics", "blue jays", "braves", "brewers", "cardinals",
    "cubs", "diamondbacks", "dodgers", "giants", "guardians", "mariners", "marlins",
    "mets", "nationals", "orioles", "padres", "phillies", "pirates", "rangers",
    "rays", "reds", "red sox", "rockies", "royals", "tigers", "twins", "white sox",
    "yankees",
})
_TOPPS_RC_EXACT_PARALLEL_BLOCK_RE = re.compile(
    r"\b("
    r"prism|prizm|negative|sapphire|orange|gold|sepia|raywave|wave|logofractor|"
    r"cosmic|black|x[\s-]?fractor|refractor|"
    r"mojo|sonic|lava|mini diamond|diamond|shimmer"
    r")\b",
    re.IGNORECASE,
)
_TOPPS_RC_EXACT_UPDATE_BLOCK_RE = re.compile(
    r"\b(update|updates|update series|hmt\d+|usc\d+)\b",
    re.IGNORECASE,
)

_PREMIUM_SUPPORT_LANE_MAP: Dict[str, Dict[str, Any]] = {
    "downtown": {
        "canonical_subset": "downtown",
        "subset_aliases": ("downtown",),
        "accepted_product_aliases": ("donruss", "optic", "donruss optic"),
        "query_products": ("Donruss", "Donruss Optic"),
        "query_subset_labels": ("Downtown",),
    },
    "kaboom": {
        "canonical_subset": "kaboom",
        "subset_aliases": ("kaboom", "kaboom!"),
        "accepted_product_aliases": ("absolute",),
        "query_products": ("Absolute",),
        "query_subset_labels": ("Kaboom",),
    },
    "aurora": {
        "canonical_subset": "aurora",
        "subset_aliases": ("aurora", "aura"),
        "accepted_product_aliases": ("spectra",),
        "query_products": ("Spectra",),
        "query_subset_labels": ("Aura", "Aurora"),
    },
}

# Team / franchise nicknames often left in titles; must not become part of player_key_slug.
NFL_TEAM_NICKNAMES: FrozenSet[str] = frozenset(
    {
        "eagles",
        "cowboys",
        "giants",
        "commanders",
        "commander",
        "bills",
        "dolphins",
        "patriots",
        "jets",
        "ravens",
        "bengals",
        "browns",
        "steelers",
        "texans",
        "colts",
        "jaguars",
        "titans",
        "broncos",
        "chiefs",
        "raiders",
        "chargers",
        "packers",
        "bears",
        "vikings",
        "lions",
        "buccaneers",
        "bucs",
        "saints",
        "falcons",
        "panthers",
        "seahawks",
        "rams",
        "cardinals",
        "49ers",
        "niners",
    }
)

# Erroneous "Prizm" in a Donruss Optic title should not split the holo bucket.
OPTIC_HOLO_NOISE_TOKENS: FrozenSet[str] = frozenset({"holo", "prizm"})

STOPWORDS: FrozenSet[str] = frozenset(
    {
        "panini",
        "donruss",
        "prizm",
        "select",
        "optic",
        "mosaic",
        "contenders",
        "chronicles",
        "phoenix",
        "illusions",
        "elite",
        "certified",
        "prestige",
        "score",
        "card",
        "cards",
        "football",
        "baseball",
        "basketball",
        "soccer",
        "hockey",
        "nfl",
        "mlb",
        "nba",
        "nhl",
        "ncaa",
        "rookie",
        "rc",
        "gem",
        "mint",
        "psa",
        "bgs",
        "sgc",
        "cgc",
        "graded",
        "slab",
        "lot",
        "break",
        "read",
        "description",
        "shipping",
        "free",
        "new",
        "sealed",
        "pack",
    }
)


@dataclass
class CardVariantClassification:
    """Strict variant bucket for comp acceptance (base vs holo vs parallel vs auto, etc.)."""

    raw_title: str = ""
    variant_family: str = "base"
    is_auto: bool = False
    is_relic: bool = False
    is_graded: bool = False
    grade_key: str = "raw"
    primary_set: Optional[str] = None
    card_number: Optional[str] = None
    number_print: Optional[str] = None
    insert_hint: str = ""
    parallel_hint: str = ""


@dataclass
class CardListingProfile:
    """Structured signals parsed from a listing title (target card)."""

    raw_title: str = ""
    year: Optional[str] = None
    card_number: Optional[str] = None
    brands: Tuple[str, ...] = ()
    set_tokens: FrozenSet[str] = frozenset()
    primary_set: Optional[str] = None
    product_family: str = ""
    subset_family: str = ""
    parallel_phrase: Optional[str] = None
    parallel_tokens: FrozenSet[str] = frozenset()
    player_guess: str = ""
    player_tokens: FrozenSet[str] = frozenset()
    is_rookie: bool = False
    is_auto: bool = False
    is_memorabilia: bool = False
    team_tokens: Tuple[str, ...] = ()
    graded_hint: bool = False


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def listing_title_for_canonical(item: Optional[Dict[str, Any]]) -> str:
    """
    Single field precedence for identity everywhere (watchlist + search + manual review).

    Prefer card_name when present (watchlist), else marketplace title, else summary.
    """
    if not item:
        return ""
    c = (item.get("card_name") or "").strip()
    t = (item.get("title") or "").strip()
    s = (item.get("summary") or "").strip()
    return (c or t or s).strip()


def normalize_card_number_for_key(card_number: Optional[str]) -> str:
    """Stable #248 vs #0248 for canonical grouping."""
    if card_number is None:
        return "na"
    raw = str(card_number).strip().lstrip("#")
    if not raw:
        return "na"
    if raw.isdigit():
        return str(int(raw))
    return re.sub(r"^0+", "", raw) or "na"


def _donruss_optic_base_holo_bucket(p: CardListingProfile, lt: str) -> Optional[str]:
    """
    Collapse Donruss Optic retail holo wording variants when no stronger parallel phrase matched.

    Does not run when PARALLEL_PHRASES matched (e.g. blue ice) or non-holo parallel tokens remain.
    """
    if p.primary_set != "optic":
        return None
    if not re.search(r"\bholo\b", lt):
        return None
    if p.parallel_phrase:
        return None
    if not p.parallel_tokens.issubset(OPTIC_HOLO_NOISE_TOKENS):
        return None
    return "holo"


def _extract_year(title: str) -> Optional[str]:
    m = re.search(r"\b(19|20)\d{2}\b", title or "")
    return m.group(0) if m else None


def _extract_card_number(title: str) -> Optional[str]:
    for pat in (
        r"#\s*(\d{1,4})\b",
        r"\bno\.?\s*(\d{1,4})\b",
        r"\bcard\s*#?\s*(\d{1,4})\b",
    ):
        m = re.search(pat, title or "", flags=re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _extract_sets(title: str) -> Set[str]:
    lower = _norm(title)
    found: Set[str] = set()
    for phrase in (
        "national treasures",
        "immaculate",
        "flawless",
        "spectra",
        "absolute",
        "stadium club",
        "topps chrome",
        "totally certified",
        "donruss optic",
        "bowman chrome",
    ):
        if phrase in lower:
            found.add(phrase.replace(" ", ""))
    for kw in SET_KEYWORDS:
        if kw in ("topps",) and "topps chrome" in lower:
            continue
        if re.search(rf"\b{re.escape(kw)}\b", lower):
            if kw == "topps" and "topps chrome" in lower:
                found.add("toppschrome")
            else:
                found.add(kw.replace(" ", ""))
    return found


def _extract_brands(title: str) -> Tuple[str, ...]:
    lower = _norm(title)
    out: List[str] = []
    for b in BRAND_KEYWORDS:
        if b in lower:
            out.append(b.title() if b != "upper deck" else "Upper Deck")
    return tuple(out)


def _primary_set(sets: Set[str]) -> Optional[str]:
    if not sets:
        return None
    # When both "mosaic" AND "prizm" appear, the card is Mosaic —
    # "Prizm" is part of the parallel name ("Silver Prizm"), not the product.
    # Mosaic Silver Prizm != Panini Prizm. Give mosaic precedence.
    if "mosaic" in sets and "prizm" in sets:
        return "mosaic"
    priority = (
        "nationaltreasures",
        "immaculate",
        "flawless",
        "spectra",
        "absolute",
        "totallycertified",
        "bowmanchrome",
        "select",
        "prizm",
        "optic",
        "mosaic",
        "donruss",
        "contenders",
        "chronicles",
        "toppschrome",
        "bowman",
        "topps",
    )
    for p in priority:
        if p in sets:
            return p
    return next(iter(sorted(sets)), None)


def _extract_parallel_phrase(title: str) -> Tuple[Optional[str], Set[str]]:
    lower = _norm(title)
    tokens: Set[str] = set()
    phrase: Optional[str] = None
    for p in PARALLEL_PHRASES:
        if p in lower:
            phrase = p
            tokens.update(p.split())
            break
    singles = (
        "silver",
        "gold",
        "blue",
        "red",
        "green",
        "purple",
        "orange",
        "pink",
        "yellow",
        "black",
        "white",
        "laser",
        "shimmer",
        "sparkle",
        "ice",
        "wave",
        "holo",
        "mojo",
        "scope",
        "pulsar",
        "disco",
        "finite",
        "zebra",
        "shock",
    )
    for s in singles:
        if re.search(rf"\b{re.escape(s)}\b", lower):
            tokens.add(s)
    return phrase, tokens


def _extract_product_family(title: str, primary_set: Optional[str] = None) -> str:
    lower = _norm(title)
    for phrase in PRODUCT_FAMILY_PHRASES:
        if phrase in lower:
            return phrase.replace(" ", "_")
    if primary_set:
        return str(primary_set).strip().lower()
    return ""


def _extract_grade_label(title: str) -> str:
    raw = str(title or "").strip()
    if not raw:
        return ""
    patterns = (
        rf"\b{_GRADE_COMPANY_PATTERN}\s*(?:gem\s+mint\s+|mint\s+|pristine\s+|black\s+label\s+)?\d{{1,2}}(?:\.\d)?\b",
        r"\bgem\s+mint\s+\d{1,2}(?:\.\d)?\b",
        r"\bmint\s+\d{1,2}(?:\.\d)?\b",
        r"\bpristine\s+\d{1,2}(?:\.\d)?\b",
    )
    for pattern in patterns:
        m = re.search(pattern, raw, flags=re.IGNORECASE)
        if m:
            return re.sub(r"\s+", " ", str(m.group(0) or "").strip()).upper()
    return ""


def _grade_lane_key(title: str) -> str:
    _raw = str(title or "").strip()
    if not _raw:
        return "raw"
    _lower = _norm(_raw)
    if not _graded_tokens(_lower):
        return "raw"
    _m = re.search(r"\b(psa|bgs|sgc|cgc|csg|gma|agc)\s*(\d{1,2}(?:\.\d)?)\b", _raw, re.IGNORECASE)
    if _m:
        return f"{_m.group(1).lower()}{_m.group(2).replace('.', 'p')}"
    _m = re.search(r"\b(psa|bgs|sgc|cgc|csg|gma|agc)\b", _raw, re.IGNORECASE)
    if _m:
        return f"{_m.group(1).lower()}_slab"
    return "slab_other"


def _extract_checklist_role_identity(title: str) -> str:
    _lower = _norm(title)
    for _phrase in _CHECKLIST_ROLE_PHRASES:
        if _phrase in _lower:
            return _phrase.replace(" ", "_")
    return ""


def _is_topps_chrome_family_product(product_family: Any, title: str = "") -> bool:
    _hay = _norm(f"{product_family or ''} {title or ''}").replace("_", " ")
    if any(_phrase in _hay for _phrase in _TOPPS_CHROME_FAMILY_PHRASES):
        return True
    return bool(
        "topps" in _hay
        and any(
            _tok in _hay
            for _tok in ("chrome", "refractor", "sapphire", "raywave", "sepia", "x fractor", "x-fractor")
        )
    )


def _exact_subject_cache_key(prof_or_title: Any) -> str:
    if isinstance(prof_or_title, CardListingProfile):
        return _norm(str(prof_or_title.raw_title or ""))
    return _norm(str(prof_or_title or ""))


def _identity_slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


_TOPPS_CHROME_PARALLEL_FAMILY_PATTERNS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("purple_speckle", (r"\bpurple\s+speckle(?:\s+refractor)?\b",)),
    ("negative_refractor", (r"\bnegative\s+refractor\b",)),
    ("x_fractor", (r"\bx[\s_-]?fractor\b",)),
    ("prism_refractor", (r"\bprism\s+refractor\b",)),
    ("raywave", (r"\bray\s*wave(?:\s+refractor)?\b", r"\braywave(?:\s+refractor)?\b")),
    ("wave", (r"\b(?:blue|red|green|purple|orange|gold|silver|aqua)?\s*wave(?:\s+refractor)?\b",)),
    ("sparkle", (r"\bsparkle(?:\s+refractor)?\b",)),
    ("lava_lamp_refractor", (r"\blava\s+lamp\s+refractor\b",)),
    ("lava_refractor", (r"\blava\s+refractor\b",)),
    ("mini_diamond_refractor", (r"\bmini\s+diamond(?:\s+refractor)?\b",)),
    ("sonic_refractor", (r"\bsonic\s+refractor\b",)),
    ("logofractor", (r"\blogofractor\b",)),
    ("sepia_refractor", (r"\bsepia(?:\s+refractor)?\b",)),
    ("refractor", (r"\brefractor\b",)),
)


def _infer_topps_chrome_parallel_family(value: Any) -> str:
    _raw = str(value or "").strip()
    if not _raw:
        return ""
    _lower = _norm(_raw).replace("_", " ")
    for _family, _patterns in _TOPPS_CHROME_PARALLEL_FAMILY_PATTERNS:
        if any(re.search(_pattern, _lower) for _pattern in _patterns):
            return _family
    return ""


def _parallel_identity_specificity(value: Any) -> int:
    _parallel = str(value or "").strip().lower()
    if _parallel in {"", "base", "raw"}:
        return 0
    if _parallel == "refractor":
        return 1
    if _parallel in {"wave", "sparkle"}:
        return 2
    return 3 + min(2, _parallel.count("_"))


def _prefer_specific_parallel_identity(*values: Any) -> str:
    _best = ""
    _best_score = -1
    for _value in values:
        _parallel = str(_value or "").strip().lower()
        _score = _parallel_identity_specificity(_parallel)
        if _score > _best_score:
            _best = _parallel
            _best_score = _score
    return _best


_TOPPS_CHROME_AUTO_PARALLEL_HINTS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("purple_speckle", (r"\bpurple\s+speckle(?:\s+refractor)?\b",)),
    ("green_lava", (r"\bgreen\s+lava(?:\s+lamp)?(?:\s+refractor)?\b",)),
    ("green_refractor", (r"\bgreen\s+refractor\b",)),
    ("gold_refractor", (r"\bgold(?:\s+\w+){0,2}\s+(?:refractor|wave)\b", r"\bgold\s+wave\b")),
    ("sapphire_refractor", (r"\bsapphire\s+refractor\b",)),
    ("black_refractor", (r"\bblack(?:\s+refractor)?\b",)),
    ("refractor", (r"\brefractor\b",)),
)

_TOPPS_CHROME_AUTO_SUPPORT_SERIAL_ALLOW: Dict[Tuple[int, int], str] = {
    (85, 99): "serial_band_85_99_support",
    (99, 150): "serial_band_99_150_cautious_support",
}

_TOPPS_CHROME_AUTO_SUPPORT_SERIAL_BLOCK: Dict[Tuple[int, int], str] = {
    (85, 199): "serial_band_85_199_blocked",
}


def _topps_auto_grade_lane(title: str) -> str:
    _grade_key = _grade_lane_key(title)
    if _grade_key == "raw":
        return "raw"
    for _prefix in ("psa", "bgs", "sgc", "cgc", "csg", "gma", "agc"):
        if _grade_key.startswith(_prefix):
            return _prefix
    return "slab_other"


def _topps_auto_serial_int(serial_denominator: Any) -> Optional[int]:
    _raw = str(serial_denominator or "").strip().lower()
    if not _raw:
        return None
    _digits = re.sub(r"[^0-9]", "", _raw)
    if not _digits:
        return None
    try:
        return int(_digits)
    except ValueError:
        return None


def _extract_topps_chrome_auto_parallel_family(title: str, *parallel_hints: Any) -> str:
    _hay = _norm(" ".join([str(title or "")] + [str(_hint or "") for _hint in parallel_hints]))
    for _family, _patterns in _TOPPS_CHROME_AUTO_PARALLEL_HINTS:
        if any(re.search(_pattern, _hay) for _pattern in _patterns):
            return _family
    _fallback = _infer_topps_chrome_parallel_family(_hay)
    if _fallback in {"lava_lamp_refractor", "lava_refractor"} and "green" in _hay:
        return "green_lava"
    if _fallback == "refractor":
        return "refractor"
    if _fallback == "logofractor":
        return "logofractor"
    return _fallback


def _extract_topps_chrome_auto_identity(title_or_profile: Any) -> Dict[str, str]:
    prof = title_or_profile if isinstance(title_or_profile, CardListingProfile) else parse_listing_profile(str(title_or_profile or ""))
    if not isinstance(prof, CardListingProfile):
        prof = parse_listing_profile(str(title_or_profile or ""))
    _title = str(prof.raw_title or title_or_profile or "").strip()
    _product = str(prof.product_family or prof.primary_set or "").strip().lower()
    if not _is_topps_chrome_family_product(_product, _title):
        return {}
    _lower = _norm(_title)
    _auto_family = bool(
        prof.is_auto
        or re.search(r"\b(auto|autograph|autographs|signature|signed)\b", _lower)
    )
    if not _auto_family:
        return {}
    if "chrome black" in _lower:
        _product_branch = "chrome_black"
    elif ("update" in _lower and "sapphire" in _lower) or "update sapphire" in _lower:
        _product_branch = "update_sapphire"
    elif "sapphire" in _lower:
        _product_branch = "sapphire"
    elif "logofractor" in _lower:
        _product_branch = "logofractor"
    elif re.search(r"\bupdate\b", _lower):
        _product_branch = "update"
    else:
        _product_branch = "base_chrome"
    _auto_card_number = normalize_card_number_for_key(prof.card_number)
    if _auto_card_number in {"", "na"}:
        _m = re.search(r"(?:#|\b)([a-z]{1,4}-[a-z0-9]{1,6})\b", _title, re.IGNORECASE)
        _auto_card_number = normalize_card_number_for_key(_m.group(1) if _m else "")
    if not re.search(r"[a-z]", _auto_card_number, re.IGNORECASE) or "-" not in _auto_card_number:
        _auto_card_number = ""
    _parallel_family = _extract_topps_chrome_auto_parallel_family(
        _title,
        normalize_parallel_bucket(prof),
        prof.parallel_phrase,
    )
    _player = str(prof.player_guess or "").strip()
    if not _player and prof.player_tokens:
        _player = " ".join(str(_tok).title() for _tok in prof.player_tokens[:3]).strip()
    return {
        "title": _title,
        "player": _player,
        "year": str(prof.year or "").strip(),
        "product_root": "topps_chrome",
        "product_branch": _product_branch,
        "auto_family": "1",
        "auto_card_number": str(_auto_card_number or "").strip().lower(),
        "parallel_family": str(_parallel_family or "").strip().lower(),
        "serial_denominator": str(_extract_serial_denominator(_title) or "").strip().lower(),
        "grade_lane": _topps_auto_grade_lane(_title),
        "grade_key": _grade_lane_key(_title),
    }


def _log_topps_auto_identity(
    tag: str,
    target_identity: Dict[str, str],
    comp_identity: Optional[Dict[str, str]],
    reason: str,
) -> None:
    _target = dict(target_identity or {})
    _comp = dict(comp_identity or {})
    print(
        f"[{tag}] title={str(_target.get('title') or '')[:140]} "
        f"comp_title={str(_comp.get('title') or '')[:140]} "
        f"player={str(_target.get('player') or _comp.get('player') or '')[:64]} "
        f"product_branch={str(_target.get('product_branch') or '')[:32]} "
        f"comp_product_branch={str(_comp.get('product_branch') or '')[:32]} "
        f"auto_card_number={str(_target.get('auto_card_number') or '')[:24]} "
        f"comp_auto_card_number={str(_comp.get('auto_card_number') or '')[:24]} "
        f"parallel_family={str(_target.get('parallel_family') or '')[:32]} "
        f"comp_parallel_family={str(_comp.get('parallel_family') or '')[:32]} "
        f"serial_denominator={str(_target.get('serial_denominator') or '')[:16]} "
        f"comp_serial_denominator={str(_comp.get('serial_denominator') or '')[:16]} "
        f"grade_lane={str(_target.get('grade_lane') or '')[:16]} "
        f"comp_grade_lane={str(_comp.get('grade_lane') or '')[:16]} "
        f"reason={reason}"
    )


def _topps_auto_branch_support_allowed(
    target_branch: str,
    comp_branch: str,
    *,
    shared_auto_card: bool,
) -> Tuple[bool, str]:
    _target = str(target_branch or "").strip().lower()
    _comp = str(comp_branch or "").strip().lower()
    if not _target or not _comp:
        return False, "missing_product_branch"
    if _target == _comp:
        return True, "same_product_branch"
    _pair = frozenset({_target, _comp})
    if _pair == frozenset({"update", "update_sapphire"}):
        return True, "update_update_sapphire_support"
    if _pair == frozenset({"base_chrome", "update"}):
        if shared_auto_card:
            return True, "base_chrome_update_shared_auto_card"
        return False, "base_chrome_update_blocked"
    return False, "product_branch_blocked"


def _topps_auto_parallel_exact_allowed(target_parallel: str, comp_parallel: str) -> Tuple[bool, str]:
    _target = str(target_parallel or "").strip().lower()
    _comp = str(comp_parallel or "").strip().lower()
    if not _target or not _comp:
        return False, "missing_parallel_family"
    if _target == _comp:
        return True, "same_parallel_family"
    return False, "parallel_family_mismatch_exact"


def _topps_auto_parallel_support_allowed(
    target_parallel: str,
    comp_parallel: str,
    *,
    branch_reason: str,
) -> Tuple[bool, str]:
    _target = str(target_parallel or "").strip().lower()
    _comp = str(comp_parallel or "").strip().lower()
    if not _target or not _comp:
        return False, "missing_parallel_family"
    if _target == _comp:
        return True, "same_parallel_family"
    _pair = frozenset({_target, _comp})
    if _pair == frozenset({"green_lava", "green_refractor"}):
        return True, "green_lava_green_refractor_support"
    if _pair == frozenset({"green_lava", "gold_refractor"}):
        return False, "green_lava_gold_blocked"
    if _pair == frozenset({"refractor", "sapphire_refractor"}):
        if branch_reason in {"same_product_branch", "update_update_sapphire_support"}:
            return True, "refractor_sapphire_refractor_support"
        return False, "refractor_sapphire_branch_blocked"
    return False, "parallel_family_blocked"


def _topps_auto_serial_support_allowed(target_serial: str, comp_serial: str) -> Tuple[bool, str]:
    _target_raw = str(target_serial or "").strip().lower()
    _comp_raw = str(comp_serial or "").strip().lower()
    if not _target_raw or not _comp_raw:
        return False, "missing_serial_denominator"
    if _target_raw == _comp_raw:
        return True, "same_serial_denominator"
    _target_int = _topps_auto_serial_int(_target_raw)
    _comp_int = _topps_auto_serial_int(_comp_raw)
    if _target_int is None or _comp_int is None:
        return False, "serial_denominator_unparseable"
    _pair = tuple(sorted((_target_int, _comp_int)))
    if _pair in _TOPPS_CHROME_AUTO_SUPPORT_SERIAL_BLOCK:
        return False, _TOPPS_CHROME_AUTO_SUPPORT_SERIAL_BLOCK[_pair]
    if _pair in _TOPPS_CHROME_AUTO_SUPPORT_SERIAL_ALLOW:
        return True, _TOPPS_CHROME_AUTO_SUPPORT_SERIAL_ALLOW[_pair]
    return False, "serial_band_blocked"


def _evaluate_topps_auto_identity_pair(
    target: CardListingProfile,
    comp_title: str,
    *,
    emit_log: bool = False,
) -> Dict[str, Any]:
    _target_identity = _extract_topps_chrome_auto_identity(target)
    if not _target_identity:
        return {"applies": False}
    _raw_comp_identity = _extract_topps_chrome_auto_identity(comp_title)
    _comp_identity = dict(_raw_comp_identity or {"title": str(comp_title or "").strip()})
    if emit_log:
        _log_topps_auto_identity("TOPPS_AUTO_IDENTITY", _target_identity, _comp_identity, "pair_evaluate")
    _result: Dict[str, Any] = {
        "applies": True,
        "target": _target_identity,
        "comp": _comp_identity,
        "exact_allow": False,
        "exact_reason": "topps_auto_not_evaluated",
        "support_allow": False,
        "support_reason": "topps_auto_not_evaluated",
    }
    if not _raw_comp_identity:
        _result["exact_reason"] = "comp_not_topps_chrome_auto"
        _result["support_reason"] = "comp_not_topps_chrome_auto"
        return _result
    _pm, _ = player_match_score(target, comp_title)
    if _pm < 0.88:
        _result["exact_reason"] = "player_mismatch"
        _result["support_reason"] = "player_mismatch"
        return _result
    if _target_identity.get("year") and _comp_identity.get("year") and _comp_identity.get("year") != _target_identity.get("year"):
        _result["exact_reason"] = "year_mismatch"
        _result["support_reason"] = "year_mismatch"
        return _result
    if _target_identity.get("product_root") != "topps_chrome" or _comp_identity.get("product_root") != "topps_chrome":
        _result["exact_reason"] = "product_root_mismatch"
        _result["support_reason"] = "product_root_mismatch"
        return _result
    if _target_identity.get("auto_family") != "1" or _comp_identity.get("auto_family") != "1":
        _result["exact_reason"] = "auto_family_mismatch"
        _result["support_reason"] = "auto_family_mismatch"
        return _result
    _target_card = str(_target_identity.get("auto_card_number") or "").strip()
    _comp_card = str(_comp_identity.get("auto_card_number") or "").strip()

    # Only block if ONE side has it and the other doesn't
    if bool(_target_card) != bool(_comp_card):
        _result["exact_reason"] = "auto_card_number_mismatch"
        _result["support_reason"] = "auto_card_number_mismatch"
        return _result

    # If BOTH have card numbers, enforce match
    if _target_card and _comp_card and _target_card != _comp_card:
        _result["exact_reason"] = "auto_card_number_mismatch"
        _result["support_reason"] = "auto_card_number_mismatch"
        return _result

    # If BOTH are empty → ALLOW FLOW TO CONTINUE
    _target_grade_lane = str(_target_identity.get("grade_lane") or "").strip().lower()
    _comp_grade_lane = str(_comp_identity.get("grade_lane") or "").strip().lower()
    if not _target_grade_lane or not _comp_grade_lane or _target_grade_lane != _comp_grade_lane:
        _result["exact_reason"] = "grade_lane_mismatch"
        _result["support_reason"] = "grade_lane_mismatch"
        return _result

    _target_grade_key = str(_target_identity.get("grade_key") or "").strip().lower()
    _comp_grade_key = str(_comp_identity.get("grade_key") or "").strip().lower()
    _branch_allow, _branch_reason = _topps_auto_branch_support_allowed(
        str(_target_identity.get("product_branch") or ""),
        str(_comp_identity.get("product_branch") or ""),
        shared_auto_card=True,
    )
    _parallel_support_allow, _parallel_support_reason = _topps_auto_parallel_support_allowed(
        str(_target_identity.get("parallel_family") or ""),
        str(_comp_identity.get("parallel_family") or ""),
        branch_reason=_branch_reason,
    )
    _serial_support_allow, _serial_support_reason = _topps_auto_serial_support_allowed(
        str(_target_identity.get("serial_denominator") or ""),
        str(_comp_identity.get("serial_denominator") or ""),
    )
    _target_parallel_norm = str(
        _infer_topps_chrome_parallel_family(_target_identity.get("parallel_family") or "")
        or _identity_slug(_target_identity.get("parallel_family") or "")
        or ""
    ).strip().lower()
    _comp_parallel_norm = str(
        _infer_topps_chrome_parallel_family(_comp_identity.get("parallel_family") or "")
        or _identity_slug(_comp_identity.get("parallel_family") or "")
        or ""
    ).strip().lower()
    _target_serial_int = _topps_auto_serial_int(_target_identity.get("serial_denominator") or "")
    _comp_serial_int = _topps_auto_serial_int(_comp_identity.get("serial_denominator") or "")
    _target_serial_norm = str(_target_serial_int) if _target_serial_int is not None else re.sub(r"[^0-9]", "", str(_target_identity.get("serial_denominator") or "").strip())
    _comp_serial_norm = str(_comp_serial_int) if _comp_serial_int is not None else re.sub(r"[^0-9]", "", str(_comp_identity.get("serial_denominator") or "").strip())
    _grade_compatible = bool(
        (_target_grade_lane == "raw" and _comp_grade_lane == "raw")
        or (
            _target_grade_lane != "raw"
            and _comp_grade_lane != "raw"
            and _target_grade_key
            and _comp_grade_key
            and _target_grade_key == _comp_grade_key
        )
    )
    print(
        f"[TOPPS_AUTO_SUPPORT_GATE] target_parallel={_target_parallel_norm[:24]} "
        f"comp_parallel={_comp_parallel_norm[:24]} target_serial={_target_serial_norm[:12]} "
        f"comp_serial={_comp_serial_norm[:12]} target_grade_lane={_target_grade_lane[:16]} "
        f"comp_grade_lane={_comp_grade_lane[:16]} target_grade_key={_target_grade_key[:16]} "
        f"comp_grade_key={_comp_grade_key[:16]} target_card={_target_card[:24]} comp_card={_comp_card[:24]}"
    )
    _blank_card_parallel_serial_support = bool(
        not _target_card
        and not _comp_card
        and _target_parallel_norm
        and _target_parallel_norm == _comp_parallel_norm
        and _target_serial_norm
        and _target_serial_norm == _comp_serial_norm
        and _grade_compatible
    )
    _fallback_block_reason = ""
    if not _raw_comp_identity:
        _fallback_block_reason = "missing_comp_identity"
    elif bool(_target_card) != bool(_comp_card):
        _fallback_block_reason = "card_presence_mismatch"
    elif not _target_parallel_norm or not _comp_parallel_norm or _target_parallel_norm != _comp_parallel_norm:
        _fallback_block_reason = "parallel_mismatch"
    elif not _target_serial_norm or not _comp_serial_norm or _target_serial_norm != _comp_serial_norm:
        _fallback_block_reason = "serial_mismatch"
    elif not _grade_compatible:
        _fallback_block_reason = "grade_mismatch"
    if _blank_card_parallel_serial_support:
        print(
            f"[TOPPS_AUTO_SERIAL_PARALLEL_SUPPORT] title={str(_target_identity.get('title') or '')[:140]} "
            f"parallel={_target_parallel_norm[:24]} "
            f"serial={_target_serial_norm[:12]} "
            f"reason=blank_card_number_exact_parallel_serial"
        )
        print(
            f"[TOPPS_AUTO_SUPPORT_ASSERT] target_parallel={_target_parallel_norm[:24]} "
            f"comp_parallel={_comp_parallel_norm[:24]} "
            f"target_serial={_target_serial_norm[:12]} "
            f"comp_serial={_comp_serial_norm[:12]} support_allow=1"
        )
        _support_parts = ["blank_card_number_exact_parallel_serial"]
        if _branch_allow:
            _support_parts.append(_branch_reason)
        if _target_grade_key and _comp_grade_key and _target_grade_key == _comp_grade_key:
            _support_parts.append("same_grade_bucket")
        _result["support_allow"] = True
        _result["support_reason"] = "|".join([_part for _part in _support_parts if _part]) or "topps_auto_support_allow"
    elif not _branch_allow:
        _result["support_reason"] = _branch_reason
    elif not _parallel_support_allow:
        _result["support_reason"] = _parallel_support_reason
    elif not _serial_support_allow:
        _result["support_reason"] = _serial_support_reason
    else:
        _support_parts = [_branch_reason, _parallel_support_reason, _serial_support_reason]
        if _target_grade_key and _comp_grade_key and _target_grade_key == _comp_grade_key:
            _support_parts.append("same_grade_bucket")
        _result["support_allow"] = True
        _result["support_reason"] = "|".join([_part for _part in _support_parts if _part]) or "topps_auto_support_allow"
    if not _blank_card_parallel_serial_support and not bool(_result.get("support_allow")):
        print(
            f"[TOPPS_AUTO_SUPPORT_BLOCK] reason={_fallback_block_reason or 'parallel_mismatch'} "
            f"target_parallel={_target_parallel_norm[:24]} comp_parallel={_comp_parallel_norm[:24]} "
            f"target_serial={_target_serial_norm[:12]} comp_serial={_comp_serial_norm[:12]} "
            f"target_grade_key={_target_grade_key[:16]} comp_grade_key={_comp_grade_key[:16]}"
        )

    _parallel_exact_allow, _parallel_exact_reason = _topps_auto_parallel_exact_allowed(
        str(_target_identity.get("parallel_family") or ""),
        str(_comp_identity.get("parallel_family") or ""),
    )
    if str(_target_identity.get("product_branch") or "") != str(_comp_identity.get("product_branch") or ""):
        _result["exact_reason"] = "product_branch_mismatch_exact"
    elif _target_grade_key != _comp_grade_key:
        _result["exact_reason"] = "grade_bucket_mismatch_exact"
    elif not _parallel_exact_allow:
        _result["exact_reason"] = _parallel_exact_reason
    elif str(_target_identity.get("serial_denominator") or "") != str(_comp_identity.get("serial_denominator") or ""):
        _result["exact_reason"] = "serial_denominator_mismatch_exact"
    else:
        _result["exact_allow"] = True
        _result["exact_reason"] = "topps_auto_exact_identity_pass"
    return _result


def _subject_identity_row_value(row: Optional[Dict[str, Any]], *keys: str) -> str:
    _row = dict(row or {})
    _target_meta = dict(_row.get("target_meta") or {})
    for _key in keys:
        _value = _row.get(_key)
        if _value not in (None, "") and str(_value).strip():
            return str(_value).strip()
        _meta_value = _target_meta.get(_key)
        if _meta_value not in (None, "") and str(_meta_value).strip():
            return str(_meta_value).strip()
    return ""


def _normalize_parallel_identity(value: Any) -> str:
    _topps_parallel = _infer_topps_chrome_parallel_family(value)
    if _topps_parallel:
        return _topps_parallel
    _slug = _identity_slug(value)
    if _slug in {"", "na", "none"}:
        return ""
    if _slug.count("_") > 6:
        return ""
    return _slug


def _extract_subject_grade_identity(prof: CardListingProfile, source_row: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    _row = dict(source_row or {})
    _grade_bucket = _identity_slug(
        _subject_identity_row_value(
            _row,
            "grade_bucket",
            "grade_bucket_strict",
            "exact_grade_bucket",
            "fingerprint_grade_bucket",
        )
        or grade_bucket_key(prof.raw_title)
    )
    _grade_label = str(
        _subject_identity_row_value(_row, "grade_label")
        or (
            f"{_subject_identity_row_value(_row, 'grade_company').upper()} {_subject_identity_row_value(_row, 'grade_value')}".strip()
            if _subject_identity_row_value(_row, "grade_company") or _subject_identity_row_value(_row, "grade_value")
            else ""
        )
        or _extract_grade_label(prof.raw_title)
        or _grade_query_label(_grade_bucket)
    ).strip()
    return _grade_bucket, _grade_label


def _extract_exact_subject_identity_bundle(
    prof_or_title: Any,
    *,
    source_row: Optional[Dict[str, Any]] = None,
    emit_log: bool = False,
) -> Dict[str, str]:
    prof = prof_or_title if isinstance(prof_or_title, CardListingProfile) else parse_listing_profile(str(prof_or_title or ""))
    if not isinstance(prof, CardListingProfile):
        prof = parse_listing_profile(str(prof_or_title or ""))
    _title = str(prof.raw_title or _subject_identity_row_value(source_row, "title", "source_title") or "").strip()
    _cache_key = _exact_subject_cache_key(prof)
    _cached = dict(_EXACT_SUBJECT_IDENTITY_CACHE.get(_cache_key) or {})
    _row = dict(source_row or {})
    _player = str(_player_display_from_source(prof, _row) or prof.player_guess or _cached.get("player") or "").strip()
    _year = str(
        _subject_identity_row_value(_row, "year", "release_year")
        or prof.year
        or _cached.get("year")
        or ""
    ).strip()
    _product_family = _identity_slug(
        _subject_identity_row_value(
            _row,
            "product_family",
            "target_product_family",
            "set_name",
            "primary_set",
        )
        or prof.product_family
        or prof.primary_set
        or _cached.get("product_family")
    )
    if not _product_family and _is_topps_chrome_family_product("", _title):
        _product_family = "topps_chrome"
    _subset_family = _identity_slug(
        _subject_identity_row_value(
            _row,
            "subset_family",
            "subset_name",
            "subset_product_family",
        )
        or prof.subset_family
        or _cached.get("subset_family")
    )
    _row_parallel_family = _normalize_parallel_identity(
        _subject_identity_row_value(_row, "parallel_family", "parallel_name", "parallel")
    )
    _profile_parallel_family = _normalize_parallel_identity(
        normalize_parallel_bucket(prof)
        or prof.parallel_phrase
    )
    _cached_parallel_family = _normalize_parallel_identity(_cached.get("parallel_family"))
    _parallel_family = _prefer_specific_parallel_identity(
        _row_parallel_family,
        _profile_parallel_family,
        _cached_parallel_family,
    )
    _serial_denominator = str(
        _subject_identity_row_value(
            _row,
            "serial_denominator",
            "fingerprint_serial_denominator",
            "serial",
        )
        or _extract_serial_denominator(_title)
        or _cached.get("serial_denominator")
        or ""
    ).strip().lower()
    _serial_class = str(
        _parallel_band(_parallel_family, _serial_denominator)
        or _serial_support_bucket(_serial_denominator)
        or _premium_serial_band(_serial_denominator)
        or _cached.get("serial_class")
        or ""
    ).strip().lower()
    _card_number = normalize_card_number_for_key(
        _subject_identity_row_value(
            _row,
            "card_number",
            "fingerprint_card_number",
            "target_card_number",
            "exact_card_number",
        )
        or prof.card_number
        or _cached.get("card_number")
    )
    _grade_bucket, _grade_label = _extract_subject_grade_identity(prof, _row)
    if not _grade_bucket and _cached.get("grade_bucket"):
        _grade_bucket = str(_cached.get("grade_bucket") or "")
    if not _grade_label and _cached.get("grade_label"):
        _grade_label = str(_cached.get("grade_label") or "")
    _team_token = _identity_slug(
        _subject_identity_row_value(_row, "team", "team_name")
        or ((prof.team_tokens or ("",))[0] if prof.team_tokens else "")
        or _cached.get("team_token")
    )
    _bundle = {
        "title": _title,
        "player": _player,
        "year": _year,
        "product_family": _product_family,
        "parallel_family": _parallel_family,
        "serial_denominator": _serial_denominator,
        "serial_class": _serial_class,
        "card_number": _card_number,
        "subset_family": _subset_family,
        "grade_bucket": _grade_bucket,
        "grade_label": _grade_label,
        "team_token": _team_token,
    }
    if _cache_key and any(str(_v or "").strip() for _v in _bundle.values()):
        _EXACT_SUBJECT_IDENTITY_CACHE[_cache_key] = dict(_bundle)
    if emit_log:
        print(
            f"[PARALLEL_IDENTITY_SUBJECT] title={_title[:140]} player={_player[:64]} "
            f"product_family={_product_family[:48]} parallel_family={_parallel_family[:48]} "
            f"card_number={_card_number[:16]} grade={_grade_label[:32]}"
        )
    return _bundle


def select_exact_comp_archetype(
    prof_or_title: Any,
    *,
    source_row: Optional[Dict[str, Any]] = None,
    emit_log: bool = True,
) -> str:
    prof = prof_or_title if isinstance(prof_or_title, CardListingProfile) else parse_listing_profile(str(prof_or_title or ""))
    if not isinstance(prof, CardListingProfile):
        prof = parse_listing_profile(str(prof_or_title or ""))
    _title = str(prof.raw_title or (source_row or {}).get("title") or (source_row or {}).get("source_title") or "").strip()
    _product = str(prof.product_family or prof.primary_set or "").strip().lower()
    _parallel = str(normalize_parallel_bucket(prof) or "").strip().lower()
    _grade_lane = str(_grade_lane_key(prof.raw_title) or "raw").strip().lower()
    _class_meta = _detect_premium_card_class(dict(source_row or {"title": _title}))
    _card_class = str(_class_meta.get("card_class") or "").strip().lower()
    _has_update_block = bool(_TOPPS_RC_EXACT_UPDATE_BLOCK_RE.search(_title))
    _identity_bundle = _extract_exact_subject_identity_bundle(prof, source_row=source_row, emit_log=False)
    _archetype = ""
    if bool(
        _product in _BASE_CHROME_RC_PSA10_PRODUCT_FAMILIES
        and prof.is_rookie
        and str(prof.card_number or "").strip()
        and bool(str(prof.player_guess or "").strip() or len(prof.player_tokens) >= 1)
        and _grade_lane == "psa10"
        and not prof.is_auto
        and not prof.is_memorabilia
        and not str(prof.subset_family or "").strip()
        and _parallel in {"", "base", "raw"}
        and not _extract_serial_denominator(prof.raw_title)
        and _card_class == "base"
        and not _has_update_block
    ):
        _archetype = EXACT_ARCHETYPE_BASE_CHROME_RC_PSA10
    elif bool(
        (_identity_bundle.get("product_family") or _product) in _CHROME_PARALLEL_SERIAL_PRODUCT_FAMILIES
        and bool(_identity_bundle.get("player"))
        and bool(_identity_bundle.get("year"))
        and bool(_identity_bundle.get("parallel_family"))
        and _identity_bundle.get("parallel_family") not in {"base", "raw"}
        and bool(_identity_bundle.get("serial_denominator"))
        and not prof.is_auto
        and not prof.is_memorabilia
        and not bool(_identity_bundle.get("subset_family"))
        and _card_class in {"base", "parallel", "base_parallel", ""}
        and not _has_update_block
    ):
        _archetype = EXACT_ARCHETYPE_CHROME_PARALLEL_SERIAL
    if emit_log and _archetype:
        if _archetype == EXACT_ARCHETYPE_CHROME_PARALLEL_SERIAL:
            _identity_bundle = _extract_exact_subject_identity_bundle(prof, source_row=source_row, emit_log=True)
            print(
                f"[PARALLEL_ARCHETYPE_SELECTED] title={_title[:140]} archetype={_archetype} "
                f"player={str(_identity_bundle.get('player') or '')[:64]} year={str(_identity_bundle.get('year') or '')[:8]} "
                f"product_family={str(_identity_bundle.get('product_family') or '')[:48]} "
                f"parallel_family={str(_identity_bundle.get('parallel_family') or '')[:48]} "
                f"serial_denominator={str(_identity_bundle.get('serial_denominator') or '')[:16]} "
                f"card_number={str(_identity_bundle.get('card_number') or '')[:20]}"
            )
        else:
            print(
                f"[EXACT_ARCHETYPE_SELECTED] title={_title[:140]} archetype={_archetype} "
                f"player={str(_player_display_from_source(prof, source_row) or '')[:64]} "
                f"product_family={_product[:48]} card_number={str(prof.card_number or '')[:20]} grade=PSA 10"
            )
    return _archetype


def _exact_archetype_query_team_token(raw_title: str, source_row: Optional[Dict[str, Any]] = None) -> str:
    _team = str((source_row or {}).get("team") or (source_row or {}).get("team_name") or "").strip()
    if _team:
        return _team.title()
    _lower = _norm(raw_title)
    for _team_token in sorted(_MLB_TEAM_QUERY_TOKENS, key=len, reverse=True):
        if _team_token in _lower:
            return _team_token.title()
    return ""


def _exact_archetype_query_pack_from_profile(
    prof: CardListingProfile,
    fallback_title: str = "",
    *,
    source_row: Optional[Dict[str, Any]] = None,
) -> List[Tuple[str, str]]:
    _archetype = select_exact_comp_archetype(prof, source_row=source_row, emit_log=True)
    if _archetype not in {EXACT_ARCHETYPE_BASE_CHROME_RC_PSA10, EXACT_ARCHETYPE_CHROME_PARALLEL_SERIAL}:
        return []
    _title = str(prof.raw_title or fallback_title or "").strip()
    _identity_bundle = _extract_exact_subject_identity_bundle(prof, source_row=source_row, emit_log=False)
    _year = str(_identity_bundle.get("year") or prof.year or "").strip()
    _player = str(_identity_bundle.get("player") or _player_display_from_source(prof, source_row) or "").strip()
    _card_number = str(_identity_bundle.get("card_number") or prof.card_number or "").strip()
    _grade = "PSA 10"
    _product_display = str(_product_display_from_profile(prof) or "").strip() or "Topps Chrome"
    _role = ""
    _lower = _norm(_title)
    for _token in _TOPPS_RC_OPTIONAL_ROLE_TOKENS:
        if re.search(rf"\b{re.escape(_token)}\b", _lower):
            _role = _token.title()
            break
    _team = _exact_archetype_query_team_token(_title, source_row=source_row)
    _queries: List[Tuple[str, str]] = []
    _seen: Set[str] = set()
    _grade_label = str(_identity_bundle.get("grade_label") or "").strip()

    def _push(_label: str, *parts: str) -> None:
        _q = " ".join(str(_part or "").strip() for _part in parts if str(_part or "").strip()).strip()[:200]
        if len(_q) < 10:
            return
        _key = _q.lower()
        if _key in _seen:
            return
        _seen.add(_key)
        _queries.append((_label, _q))

    if _archetype == EXACT_ARCHETYPE_BASE_CHROME_RC_PSA10:
        _push("exact_archetype_pass_a", _year, _product_display, _player, f"#{_card_number}", _grade)
        _push("exact_archetype_pass_b", _year, _product_display, f"#{_card_number}", _player, _grade)
        _push("exact_archetype_pass_c", _year, _product_display, _player, "RC", f"#{_card_number}", _grade)
        _push("exact_archetype_pass_d", _year, _product_display, _player, "Rookie", f"#{_card_number}", _grade)
        if _role:
            _push("exact_archetype_pass_role", _year, _product_display, _player, _role, f"#{_card_number}", _grade)
        if _team:
            _push("exact_archetype_pass_team", _year, _product_display, f"#{_card_number}", _player, _team, _grade)
        _push("exact_archetype_pass_combined", _year, _product_display.upper(), f"#{_card_number}", _player.upper(), "RC", _team.upper() if _team else "", _role.upper() if _role else "", _grade)
    else:
        _parallel_label = str(_identity_bundle.get("parallel_family") or "").replace("_", " ").title()
        _serial_label = f"/{str(_identity_bundle.get('serial_denominator') or '').strip()}".strip()
        _push("parallel_exact_pass_a", _year, _product_display, _player, _parallel_label, _serial_label, _grade_label)
        _push("parallel_exact_pass_b", _year, _product_display, _parallel_label, _player, _serial_label)
        if _card_number:
            _push("parallel_exact_pass_card", _year, _product_display, _player, f"#{_card_number}", _parallel_label, _serial_label)
        if _team:
            _push("parallel_exact_pass_team", _year, _product_display, _player, _parallel_label, _serial_label, _team)
        if _grade_label:
            _push("parallel_exact_pass_grade", _year, _product_display, _player, _parallel_label, _serial_label, _grade_label)
    print(
        f"[EXACT_ARCHETYPE_QUERY_PACK] title={_title[:140]} archetype={_archetype} "
        f"queries={json.dumps([_q for _, _q in _queries])}"
    )
    return _queries


def _exact_archetype_candidate_match(
    target: CardListingProfile,
    comp_title: str,
) -> Tuple[bool, str]:
    _target_title = str(target.raw_title or "").strip()
    _archetype = select_exact_comp_archetype(target, emit_log=False)
    if _archetype not in {EXACT_ARCHETYPE_BASE_CHROME_RC_PSA10, EXACT_ARCHETYPE_CHROME_PARALLEL_SERIAL}:
        return False, "not_exact_archetype"
    if _archetype == EXACT_ARCHETYPE_CHROME_PARALLEL_SERIAL:
        _subject = _extract_exact_subject_identity_bundle(target, emit_log=False)
        ct = _extract_card_identity_tokens(comp_title)
        _pm, _ = player_match_score(target, comp_title)
        _player_match = _pm >= 0.88
        _year_match = bool(_subject.get("year") and str(ct.get("year") or "").strip() == str(_subject.get("year") or "").strip())
        _target_product = str(_subject.get("product_family") or "").strip().lower()
        _comp_product = str(ct.get("product_family") or ct.get("primary_set") or "").strip().lower()
        _product_match = bool(_target_product and _comp_product and _comp_product == _target_product)
        _parallel_contract = exact_parallel_identity_contract(target, comp_title, emit_log=True)
        _target_parallel = str(_parallel_contract.get("subject_parallel") or _subject.get("parallel_family") or "").strip().lower()
        _comp_parallel = str(_parallel_contract.get("candidate_parallel") or "").strip().lower()
        _parallel_match = bool(
            _parallel_contract.get("allow")
            and _target_parallel
            and _comp_parallel
            and _comp_parallel == _target_parallel
        )
        _target_serial = str(_subject.get("serial_denominator") or "").strip().lower()
        _comp_serial = str(ct.get("serial_denominator") or "").strip().lower()
        _serial_match = bool(_target_serial and _comp_serial and _comp_serial == _target_serial)
        _target_card = str(_subject.get("card_number") or "").strip().lower()
        _comp_card = str(ct.get("card_number") or "").strip().lower()
        _target_subset = str(_subject.get("subset_family") or "").strip().lower()
        _comp_subset = str(ct.get("subset_family") or "").strip().lower()
        _subset_conflict = bool(
            (_target_subset and _comp_subset and _comp_subset != _target_subset)
            or (not _target_subset and _comp_subset)
        )
        _card_match = 1
        if _target_card not in {"", "na"}:
            _card_match = 1 if (_comp_card not in {"", "na"} and _comp_card == _target_card) else 0
        _target_grade = str(_subject.get("grade_bucket") or "").strip().lower()
        _comp_grade = str(ct.get("grade") or ct.get("grade_lane") or "").strip().lower()
        _target_is_graded = _target_grade not in {"", "raw"}
        _comp_is_graded = _comp_grade not in {"", "raw"}
        _grade_match = 1
        if _target_is_graded and _comp_is_graded:
            _grade_match = 1 if _comp_grade == _target_grade else 0
        elif _target_is_graded != _comp_is_graded:
            _grade_match = 0
        _reason = "parallel_exact_identity"
        _allow = True
        if not _player_match:
            _allow = False
            _reason = "missing_strong_identity"
        elif not _year_match:
            _allow = False
            _reason = "year_mismatch"
        elif not _product_match:
            _allow = False
            _reason = "wrong_product_family"
        elif not _parallel_match:
            _allow = False
            _reason = "blocked_parallel_family"
        elif not _serial_match:
            _allow = False
            _reason = "blocked_serial"
        elif _subset_conflict:
            _allow = False
            _reason = "blocked_subset"
        elif not _card_match:
            _allow = False
            _reason = "blocked_card_number"
        elif not _grade_match:
            _allow = False
            _reason = "blocked_grade"
        print(
            f"[PARALLEL_EXACT_CANDIDATE] title={_target_title[:140]} candidate_title={comp_title[:140]} "
            f"match={1 if _allow else 0} reason={_reason} player_match={1 if _player_match else 0} "
            f"year_match={1 if _year_match else 0} product_match={1 if _product_match else 0} "
            f"parallel_match={1 if _parallel_match else 0} serial_match={1 if _serial_match else 0} "
            f"card_match={int(_card_match)} subset_conflict={1 if _subset_conflict else 0} grade_match={int(_grade_match)}"
        )
        return _allow, _reason
    tt = _extract_card_identity_tokens(target)
    ct = _extract_card_identity_tokens(comp_title)
    _pm, _ = player_match_score(target, comp_title)
    _player_match = _pm >= 0.88
    _target_product = str(tt.get("product_family") or tt.get("primary_set") or "").strip().lower()
    _comp_product = str(ct.get("product_family") or ct.get("primary_set") or "").strip().lower()
    _product_match = bool(_target_product and _comp_product and _comp_product == _target_product)
    _card_match = bool(
        tt.get("card_number") not in {"", "na"}
        and ct.get("card_number") not in {"", "na"}
        and ct.get("card_number") == tt.get("card_number")
    )
    _grade_match = bool(
        str(tt.get("grade_lane") or "").strip().lower() == "psa10"
        and str(ct.get("grade_lane") or "").strip().lower() == "psa10"
    )
    _candidate_lower = _norm(comp_title)
    _variant_tokens = [
        _token for _token in ("rc", "rookie", "pitching", "batting", "hitting", "gem mint", "gem mt")
        if _token in _candidate_lower
    ]
    _target_parallel = _identity_parallel_family(tt)
    _comp_parallel = _identity_parallel_family(ct)
    _comp_subset = str(ct.get("subset_family") or "").strip().lower()
    _parallel_block = bool(
        (_target_parallel and _target_parallel not in {"", "base", "raw"})
        or (_comp_parallel and _comp_parallel not in {"", "base", "raw"})
        or bool(_comp_subset)
        or bool(str(ct.get("serial_denominator") or "").strip())
        or bool(_TOPPS_RC_EXACT_PARALLEL_BLOCK_RE.search(comp_title))
    )
    _update_block = bool(_TOPPS_RC_EXACT_UPDATE_BLOCK_RE.search(comp_title))
    _reason = "exact_core_identity"
    _allow = True
    if not _player_match:
        _allow = False
        _reason = "missing_strong_identity"
    elif not _product_match:
        _allow = False
        _reason = "wrong_product_family"
    elif not _card_match:
        _allow = False
        _reason = "blocked_card_number"
    elif not _grade_match:
        _allow = False
        _reason = "blocked_grade"
    elif _update_block:
        _allow = False
        _reason = "blocked_update"
    elif _parallel_block:
        _allow = False
        _reason = "blocked_parallel"
    print(
        f"[EXACT_ARCHETYPE_CANDIDATE] title={_target_title[:140]} archetype={_archetype} candidate_title={comp_title[:140]} "
        f"match={1 if _allow else 0} reason={_reason} player_match={1 if _player_match else 0} "
        f"product_match={1 if _product_match else 0} card_match={1 if _card_match else 0} "
        f"grade_match={1 if _grade_match else 0} parallel_block={1 if _parallel_block else 0} "
        f"update_block={1 if _update_block else 0}"
    )
    return _allow, _reason


def _is_topps_chrome_rookie_psa10_exact_lane(
    prof: CardListingProfile,
    *,
    source_row: Optional[Dict[str, Any]] = None,
) -> bool:
    return select_exact_comp_archetype(prof, source_row=source_row, emit_log=False) == EXACT_ARCHETYPE_BASE_CHROME_RC_PSA10


def _is_noisy_subset_identity(value: Any, *, raw_title: str = "", card_number: Any = "") -> bool:
    _slug = _support_slug(value)
    if not _slug:
        return False
    if re.fullmatch(r"\d+(?:\.\d+)?", _slug):
        return True
    if re.fullmatch(rf"{_GRADE_COMPANY_PATTERN}(?:\s+(?:gem mint|mint|pristine|black label))?\s+\d{{1,2}}(?:\.\d+)?", _slug):
        return True
    if re.fullmatch(r"(?:gem mint|mint|pristine)\s+\d{1,2}(?:\.\d+)?", _slug):
        return True
    if re.fullmatch(r"(?:card\s+)?\d{1,4}", _slug):
        return True
    _card_no = _support_slug(card_number)
    if _card_no and _slug == _card_no:
        return True
    _grade_label = _support_slug(_extract_grade_label(raw_title))
    if _grade_label and _slug == _grade_label:
        return True
    return False


def _extract_subset_family(title: str, *, product_family: str = "", card_number: Optional[str] = None) -> str:
    lower = _norm(title)
    for phrase in SUBSET_FAMILY_PHRASES:
        if phrase in lower:
            return phrase.replace(" ", "_")
    _hint = _insert_premium_hint(lower)
    if _hint:
        return _hint
    if _is_topps_chrome_family_product(product_family, title) and card_number:
        return ""
    return ""


PLAYER_NAME_SUFFIXES: FrozenSet[str] = frozenset(
    "jr jr. sr sr. ii iii iv v vi 2nd 3rd 4th".split()
)


def normalize_player_name(raw: str) -> str:
    """Lowercase cleanup for token compare; strips common suffixes (Jr., III, etc.)."""
    s = (raw or "").lower().strip()
    s = re.sub(r"[^a-z0-9\s\-'.]", " ", s)
    parts = [p.strip(".") for p in s.split() if p.strip()]
    out: List[str] = []
    for p in parts:
        if p in PLAYER_NAME_SUFFIXES:
            continue
        if len(p) >= 2:
            out.append(p)
    return " ".join(out)


def _strip_name_suffixes(parts: List[str]) -> List[str]:
    while parts and parts[-1].lower().strip(".") in PLAYER_NAME_SUFFIXES:
        parts = parts[:-1]
    return parts


def _extract_player_guess(title: str) -> Tuple[str, FrozenSet[str]]:
    """Heuristic: name tokens after stripping year / brand / first set word."""
    raw = title or ""
    s = re.sub(r"\|.*$", "", raw, flags=re.DOTALL)
    s = re.sub(r"\b(psa|bgs|sgc|cgc)\s*\d+.*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(19|20)\d{2}\b", " ", s)
    s = re.sub(r"#[^\s]+", " ", s)
    s = re.sub(r"\bno\.?\s*\d+\b", " ", s, flags=re.IGNORECASE)
    lower = s.lower()
    for b in BRAND_KEYWORDS:
        lower = re.sub(rf"\b{re.escape(b)}\b", " ", lower)
    for kw in SET_KEYWORDS:
        lower = re.sub(rf"\b{re.escape(kw)}\b", " ", lower, count=1)
    for noise in (
        "rookie",
        "rc",
        "silver",
        "prizm",
        "refractor",
        "parallel",
        "insert",
        "sp",
        "ssp",
        "variation",
        "jersey",
        "patch",
        "auto",
        "autograph",
    ):
        lower = re.sub(rf"\b{re.escape(noise)}\b", " ", lower)
    words = re.findall(r"[A-Za-z][a-zA-Za-z'\-.]+", lower)
    name_parts = [w for w in words if w.lower() not in STOPWORDS and len(w) > 1]
    name_parts = [w for w in name_parts if w.lower() not in NFL_TEAM_NICKNAMES]
    name_parts = _strip_name_suffixes(name_parts)
    if len(name_parts) >= 2:
        guess = f"{name_parts[0]} {name_parts[1]}".strip()
        toks = frozenset(normalize_player_name(x) for x in name_parts[:5] if normalize_player_name(x))
        return guess, toks
    if name_parts:
        g0 = name_parts[0]
        ng = normalize_player_name(g0)
        return g0, frozenset({ng}) if ng else frozenset()
    return "", frozenset()


def target_has_identifiable_player(target: CardListingProfile) -> bool:
    """Whether we should hard-require a player match on comps."""
    if len(target.player_tokens) >= 2:
        return True
    if len(target.player_tokens) == 1:
        t = next(iter(target.player_tokens))
        return len(t) >= 4
    g = normalize_player_name(target.player_guess or "")
    return bool(g) and len(g) >= 8 and " " in g


def player_match_score(target: CardListingProfile, comp_title: str) -> Tuple[float, str]:
    """
    0..1 style confidence that the comp references the same player as target.
    Title-only; does not inspect images.
    """
    cl = _norm(comp_title)
    if not cl.strip():
        return 0.0, "empty_comp"
    if not target.player_tokens and not (target.player_guess or "").strip():
        return 1.0, "no_target_player"

    _, comp_toks = _extract_player_guess(comp_title)
    tt = {normalize_player_name(t) for t in target.player_tokens if t and normalize_player_name(t)}
    ct = {normalize_player_name(t) for t in comp_toks if t and normalize_player_name(t)}
    tt.discard("")
    ct.discard("")
    if not tt:
        return 1.0, "no_target_player"

    inter = tt & ct
    guess_norm = normalize_player_name(target.player_guess or "")
    bonus = 0.0
    if guess_norm and len(guess_norm) >= 5 and guess_norm in cl:
        bonus = 0.12

    if len(tt) >= 2:
        if len(inter) >= 2:
            return min(1.0, 0.96 + bonus), "multi_strong"
        if len(inter) == 1:
            only = next(iter(inter))
            if len(only) >= 5:
                return min(1.0, 0.62 + bonus), "multi_one_distinctive"
            return min(1.0, 0.42 + bonus), "multi_one_weak"
        if guess_norm and guess_norm in cl:
            return min(1.0, 0.55 + bonus), "multi_guess_substring"
        return 0.12 + bonus, "multi_no_overlap"

    if inter:
        return min(1.0, 0.82 + bonus), "single_token_hit"
    if guess_norm and guess_norm in cl:
        return min(1.0, 0.74 + bonus), "single_guess_substring"
    return 0.1 + bonus, "single_miss"


def is_exact_player_match(target: CardListingProfile, comp_title: str) -> bool:
    sc, _lab = player_match_score(target, comp_title)
    return sc >= 0.88


def comp_set_matches_target_strict(comp_title: str, target: CardListingProfile) -> bool:
    """Strict shared product line: required when target parsed a set family."""
    tset = target.set_tokens
    if not tset:
        return True
    csets = _extract_sets(comp_title)
    return bool(csets & tset)


def _has_auto_identity_signal(title_or_text: Any) -> bool:
    _raw = str(title_or_text or "").strip()
    if not _raw:
        return False
    _lower = _norm(_raw)
    _patterns = (
        r"\bon[- ]card\s+auto(graph)?\b",
        r"\bsticker\s+auto(graph)?\b",
        r"\bauto(graph)?\b",
        r"\bsigned\b",
        r"\bsignatures?\b",
        r"\bsig\s+card\b",
    )
    return any(re.search(_pattern, _lower, re.IGNORECASE) for _pattern in _patterns)


def subject_has_auto_identity(title_or_text: Any) -> bool:
    return _has_auto_identity_signal(title_or_text)


def comp_has_auto_identity(title_or_text: Any) -> bool:
    return _has_auto_identity_signal(title_or_text)


def _listing_implies_auto(lower: str) -> bool:
    return subject_has_auto_identity(lower)


def _listing_implies_mem(lower: str) -> bool:
    return bool(
        re.search(
            r"\b(material|materials|patch|jersey|relic|memorabilia|swatch|swatches|jumbo\s*patch|rpa|dual\s*patch|quad\s*patch|player[- ]?worn|mem)\b",
            lower,
            re.IGNORECASE,
        )
    )


def _listing_implies_lot(lower: str) -> bool:
    if re.search(r"\b(lot|bundle|collection\s*of|complete\s*set|team\s*set)\b", lower):
        return True
    if re.search(r"\b\d+\s*(card|cards)\s*(lot|bundle)?\b", lower):
        return True
    if re.search(r"\bx\s*\d+\b", lower) and "card" in lower:
        return True
    if re.search(r"\b(mixed\s+lot|lot\s+of|set\s+of|rookie\s+lot|bulk|wholesale)\b", lower):
        return True
    if re.search(r"\b(pair|duo|trio)\b", lower):
        return True
    if re.search(r"\b(plus\s+extras|with\s+extras)\b", lower):
        return True
    return False


def _listing_implies_break(lower: str) -> bool:
    return bool(
        re.search(
            r"\b(break|break\s+spot|case\s+break|random\s+team|pick\s+your\s+team|pyt|rt|hobby\s+break)\b",
            lower,
            re.IGNORECASE,
        )
    )


def _listing_implies_sealed_wax(lower: str) -> bool:
    return bool(
        re.search(
            r"\b(hobby\s+box|blaster|mega|hanger|fat\s+pack|cello|sealed|wax|booster\s+box|retail\s+box|pack)\b",
            lower,
            re.IGNORECASE,
        )
    )


def _listing_implies_team_set_or_collection(lower: str) -> bool:
    return bool(
        re.search(
            r"\b(team\s+set|complete\s+set|set\s+break|full\s+set|master\s+set|collection)\b",
            lower,
            re.IGNORECASE,
        )
    )


def classify_listing_type(title_or_item: Any) -> str:
    """Classify a listing for single-card valuation workflows."""
    if isinstance(title_or_item, dict):
        raw = listing_title_for_canonical(title_or_item)
    else:
        raw = str(title_or_item or "")
    lower = _norm(raw)
    if not lower:
        return LISTING_TYPE_UNKNOWN_AMBIGUOUS
    if _listing_implies_break(lower):
        return LISTING_TYPE_BREAK_OR_SPOT
    if _listing_implies_sealed_wax(lower):
        return LISTING_TYPE_SEALED_WAX_OR_BOX
    if _listing_implies_team_set_or_collection(lower):
        return LISTING_TYPE_TEAM_SET_OR_COLLECTION
    if _listing_implies_lot(lower):
        return LISTING_TYPE_MULTI_CARD_LOT
    if re.search(r"\b\d+\s*(?:card|cards)\b", lower) or re.search(r"\b(?:x|lot\s+of)\s*\d+\b", lower):
        return LISTING_TYPE_MULTI_CARD_LOT
    return LISTING_TYPE_SINGLE_CARD


def listing_type_exclusion_reason(listing_type: str) -> str:
    lt = str(listing_type or "").strip().upper()
    return {
        LISTING_TYPE_MULTI_CARD_LOT: "lot_bundle_multi_card",
        LISTING_TYPE_BREAK_OR_SPOT: "break_or_spot_listing",
        LISTING_TYPE_SEALED_WAX_OR_BOX: "sealed_wax_or_box",
        LISTING_TYPE_TEAM_SET_OR_COLLECTION: "team_set_or_collection",
        LISTING_TYPE_UNKNOWN_AMBIGUOUS: "ambiguous_listing_type",
    }.get(lt, "")


def is_non_single_card_listing(title_or_item: Any) -> bool:
    return classify_listing_type(title_or_item) != LISTING_TYPE_SINGLE_CARD


def should_exclude_from_single_card_valuation(title_or_item: Any) -> Tuple[bool, str, str]:
    listing_type = classify_listing_type(title_or_item)
    reason = listing_type_exclusion_reason(listing_type)
    return bool(reason), listing_type, reason


def _graded_tokens(lower: str) -> bool:
    return bool(
        re.search(rf"\b{_GRADE_COMPANY_PATTERN}\s*(?:gem\s+mint\s+|mint\s+|pristine\s+|black\s+label\s+)?\d", lower, re.IGNORECASE)
        or re.search(r"\b(gem\s+mint|mint|pristine)\s+\d{1,2}(?:\.\d)?\b", lower, re.IGNORECASE)
        or re.search(r"\bgraded\b", lower, re.IGNORECASE)
    )


def parse_listing_profile(title: str) -> CardListingProfile:
    raw = (title or "").strip()
    lower = _norm(raw)
    year = _extract_year(raw)
    cn = _extract_card_number(raw)
    sets = _extract_sets(raw)
    brands = _extract_brands(raw)
    pset = _primary_set(sets)
    product_family = _extract_product_family(raw, pset)
    subset_family = _extract_subset_family(raw, product_family=product_family, card_number=cn)
    par_phrase, par_toks = _extract_parallel_phrase(raw)
    player, ptoks = _extract_player_guess(raw)
    grade_label = _extract_grade_label(raw)
    if subset_family and _is_noisy_subset_identity(subset_family, raw_title=raw, card_number=cn):
        print(
            f"[SUBSET_PARSE_GUARD] title={raw[:140]} ignored_token={subset_family[:40]} "
            f"reason=grade_or_card_number_noise"
        )
        subset_family = ""
    if not subset_family and grade_label:
        print(
            f"[SUBSET_PARSE_GUARD] title={raw[:140]} ignored_token={grade_label[:40]} "
            f"reason=grade_or_card_number_noise"
        )
    if not subset_family and cn:
        print(
            f"[SUBSET_PARSE_GUARD] title={raw[:140]} ignored_token=#{str(cn)[:20]} "
            f"reason=grade_or_card_number_noise"
        )
    rookie = bool(
        re.search(r"\b(rc|rookie)\b", lower)
        or re.search(r"\brated\s+rookie\b", lower)
        or re.search(r"\brr\b", lower)
    )
    auto = _listing_implies_auto(lower)
    mem = _listing_implies_mem(lower)

    if ("prizm" in sets or pset == "prizm") and re.search(r"\btrue\s+silver\b", lower):
        if not par_phrase or "silver" in (par_phrase or ""):
            par_phrase = "silver prizm"
            par_toks = frozenset(set(par_toks) | {"silver", "prizm"})
    _parallel_family = (par_phrase or "_".join(sorted(par_toks)) or "").strip().replace(" ", "_")
    if _is_topps_chrome_family_product(product_family or pset or "", raw):
        print(
            f"[TOPPS_FAMILY_PARSE] title={raw[:140]} product_family={str(product_family or pset or '')[:40]} "
            f"subset_family={subset_family[:32] if subset_family else ''} parallel_family={_parallel_family[:32]}"
        )
        if not subset_family:
            print(f"[TOPPS_FAMILY_GUARD] title={raw[:140]} reason=prefer_family_over_fake_subset")
    print(
        f"[SUBSET_PARSE_RESULT] title={raw[:140]} subset={subset_family[:32] if subset_family else ''} "
        f"card_number={str(cn or '')[:16]} grade={grade_label[:24] if grade_label else ''}"
    )

    return CardListingProfile(
        raw_title=raw,
        year=year,
        card_number=cn,
        brands=brands,
        set_tokens=frozenset(sets),
        primary_set=pset,
        product_family=product_family[:80],
        subset_family=subset_family[:80],
        parallel_phrase=par_phrase,
        parallel_tokens=frozenset(par_toks),
        player_guess=player,
        player_tokens=ptoks,
        is_rookie=rookie,
        is_auto=auto,
        is_memorabilia=mem,
        team_tokens=(),
        graded_hint=_graded_tokens(lower),
    )


_PREMIUM_CARD_CLASS_MEM_TERMS: FrozenSet[str] = frozenset(
    {
        "material",
        "materials",
        "memorabilia",
        "relic",
        "jersey",
        "swatch",
        "swatches",
        "fabric",
        "player worn",
        "player-worn",
        "worn",
        "gear",
        "sunday spectacle",
        "mem",
    }
)
_PREMIUM_CARD_CLASS_PATCH_TERMS: FrozenSet[str] = frozenset(
    {
        "patch",
        "jumbo patch",
        "super patch",
        "laundry tag",
        "tag",
        "logo",
        "shield",
        "nameplate",
        "bat knob",
        "button",
    }
)
_PREMIUM_CARD_CLASS_AUTO_TERMS: FrozenSet[str] = frozenset(
    {"auto", "autograph", "signature", "signed", "sig", "signatures"}
)
_PREMIUM_CARD_CLASS_DUAL_TERMS: FrozenSet[str] = frozenset(
    {"dual", "double", "duo", "triple", "quad"}
)
_PREMIUM_CARD_CLASS_RPA_TERMS: FrozenSet[str] = frozenset(
    {
        "rpa",
        "rookie patch autograph",
        "rookie patch auto",
        "rookie debut patch autograph",
        "rookie jersey autograph",
    }
)


def _product_display_from_profile(prof: CardListingProfile) -> str:
    if prof.primary_set == "optic" and "donruss" in prof.set_tokens:
        return "Donruss Optic"
    if prof.primary_set == "toppschrome":
        return "Topps Chrome"
    if prof.primary_set == "bowmanchrome":
        return "Bowman Chrome"
    if prof.primary_set == "totallycertified":
        return "Totally Certified"
    if prof.primary_set == "nationaltreasures":
        return "National Treasures"
    if prof.primary_set:
        return prof.primary_set.replace("_", " ").title()
    if prof.product_family:
        return prof.product_family.replace("_", " ").title()
    if prof.set_tokens:
        return sorted(prof.set_tokens)[0].replace("toppschrome", "Topps Chrome").replace("_", " ").title()
    return ""


def _player_display_from_source(prof: CardListingProfile, source_row: Optional[Dict[str, Any]] = None) -> str:
    _row = dict(source_row or {})
    return str(
        _row.get("player_name")
        or _row.get("target_player_name")
        or _row.get("player")
        or prof.player_guess
        or ""
    ).strip()


def _subset_display_label(subset_family: str) -> str:
    _subset = str(subset_family or "").strip().lower().replace("_", " ")
    if not _subset:
        return ""
    if _subset in {"aura", "aurora"}:
        return "Aura"
    return _subset.title()


def _serial_query_label(serial_value: Any) -> str:
    _raw = str(serial_value or "").strip()
    if not _raw:
        return ""
    if "/" in _raw:
        return _raw
    _digits = re.sub(r"[^0-9]", "", _raw)
    if not _digits:
        return ""
    return f"/{_digits}"


def _grade_query_label(grade_key: str) -> str:
    _key = str(grade_key or "").strip().lower()
    if not _key or _key == "raw":
        return ""
    _m = re.match(r"^(psa|bgs|sgc|cgc)(\d{1,2}(?:\.\d)?)$", _key)
    if _m:
        return f"{_m.group(1).upper()} {_m.group(2)}"
    return _key.upper()


def _premium_card_class_family(card_class: str) -> str:
    _card_class = str(card_class or "").strip().lower()
    if _card_class == "dual_patch_auto":
        return "dual_patch_auto_family"
    if _card_class in {"rpa", "patch_auto"}:
        return "patch_auto_family"
    if _card_class in {"relic", "memorabilia"}:
        return "memorabilia_family"
    if _card_class == "auto":
        return "auto_family"
    if _card_class == "subset_insert":
        return "subset_insert_family"
    if _card_class == "parallel":
        return "parallel_family"
    return "base_family"


def _premium_query_class_terms(meta: Dict[str, Any], prof: CardListingProfile) -> List[str]:
    _meta = dict(meta or {})
    _title = _norm(str(_meta.get("raw_title") or prof.raw_title or ""))
    _card_class = str(_meta.get("card_class") or "").strip().lower()
    _subset_label = str(_meta.get("subset_label") or "")
    _parallel_label = str(_meta.get("parallel_label") or "")
    _serial_label = str(_meta.get("serial_label") or "")
    _terms: List[str] = []
    if _subset_label and _card_class == "subset_insert":
        _terms.append(_subset_label)
    if _card_class == "dual_patch_auto":
        _terms.extend(["Dual Patch Auto", "RPA"])
    elif _card_class == "rpa":
        _terms.extend(["RPA", "Patch Auto"])
    elif _card_class == "patch_auto":
        _terms.append("Patch Auto")
    elif _card_class == "auto":
        _terms.append("Auto")
    elif _card_class in {"relic", "memorabilia"}:
        if "materials" in _title or "material" in _title:
            _terms.append("Materials")
        elif "swatches" in _title or "swatch" in _title:
            _terms.append("Swatch")
        elif "relic" in _title:
            _terms.append("Relic")
        elif "jersey" in _title:
            _terms.append("Jersey")
        elif "memorabilia" in _title or "mem" in _title:
            _terms.append("Memorabilia")
        elif "patch" in _title:
            _terms.append("Patch")
        else:
            _terms.append("Relic")
    elif _subset_label:
        _terms.append(_subset_label)
    if _card_class == "parallel" and _parallel_label and _parallel_label not in {"Base", "Raw"}:
        _terms.append(_parallel_label)
    if _serial_label:
        _terms.append(_serial_label)
    _deduped: List[str] = []
    _seen: Set[str] = set()
    for _term in _terms:
        _clean = str(_term or "").strip()
        if not _clean:
            continue
        _key = _clean.lower()
        if _key in _seen:
            continue
        _seen.add(_key)
        _deduped.append(_clean)
    return _deduped


def _is_premium_class_aware_profile(prof: CardListingProfile, meta: Optional[Dict[str, Any]] = None) -> bool:
    _meta = dict(meta or {})
    if str(_meta.get("card_class") or "").strip().lower() in {
        "relic",
        "memorabilia",
        "patch_auto",
        "rpa",
        "dual_patch_auto",
        "subset_insert",
        "auto",
    }:
        return True
    _product = _norm(str(prof.product_family or prof.primary_set or "").replace("_", " "))
    return _product in {"spectra", "national treasures", "immaculate", "flawless", "absolute"}


def _detect_premium_card_class(row: Any) -> Dict[str, Any]:
    _row = dict(row or {}) if isinstance(row, dict) else {}
    _title = listing_title_for_canonical(_row) if isinstance(row, dict) else str(row or "").strip()
    _profile = parse_listing_profile(_title)
    _lower = _norm(_title)
    _subset_family = str(
        _row.get("subset_name")
        or _row.get("lane_subset")
        or _row.get("subset")
        or getattr(_profile, "subset_family", "")
        or ""
    ).strip().lower().replace(" ", "_")
    _parallel_label = str(
        _row.get("parallel_name")
        or _row.get("parallel")
        or _row.get("parallel_bucket")
        or _profile.parallel_phrase
        or normalize_parallel_bucket(_profile)
        or ""
    ).strip()
    _serial_value = str(
        _row.get("serial")
        or _row.get("serial_denominator")
        or _extract_serial_denominator(_title)
        or ""
    ).strip()
    _grade_key = grade_bucket_key(_title)
    _auto_flag = bool(_row.get("is_auto")) or _listing_implies_auto(_lower)
    _mem_flag = bool(_row.get("is_memorabilia") or _row.get("memorabilia_flag")) or _listing_implies_mem(_lower)
    _patch_flag = any(_term in _lower for _term in _PREMIUM_CARD_CLASS_PATCH_TERMS)
    _dual_flag = any(re.search(rf"\b{re.escape(_term)}\b", _lower) for _term in _PREMIUM_CARD_CLASS_DUAL_TERMS)
    _rookie_flag = bool(_row.get("is_rookie")) or bool(getattr(_profile, "is_rookie", False))
    _rpa_flag = any(_term in _lower for _term in _PREMIUM_CARD_CLASS_RPA_TERMS)
    _serial_label = _serial_query_label(_serial_value)
    _subset_label = _subset_display_label(_subset_family)
    if _dual_flag and _auto_flag and (_patch_flag or _mem_flag):
        _card_class = "dual_patch_auto"
    elif _rpa_flag or (_auto_flag and (_patch_flag or _mem_flag) and _rookie_flag):
        _card_class = "rpa"
    elif _auto_flag and (_patch_flag or _mem_flag):
        _card_class = "patch_auto"
    elif _auto_flag:
        _card_class = "auto"
    elif _mem_flag:
        if any(_term in _lower for _term in ("relic", "swatch", "swatches", "materials", "material", "jersey", "memorabilia", "mem")):
            _card_class = "relic"
        else:
            _card_class = "memorabilia"
    elif _subset_family:
        _card_class = "subset_insert"
    elif _parallel_label and _parallel_label.strip().lower() not in {"", "base", "raw"}:
        _card_class = "parallel"
    elif _serial_value:
        _card_class = "parallel"
    else:
        _card_class = "base"
    _card_class_family = _premium_card_class_family(_card_class)
    _product_display = _product_display_from_profile(_profile)
    _parallel_display = _parallel_label.replace("_", " ").title() if _parallel_label else ""
    _signature_parts = [
        _product_display,
        _subset_label,
        _card_class_family.replace("_", " "),
        _parallel_display if _parallel_display not in {"Base", "Raw"} else "",
        _serial_label,
        _grade_query_label(_grade_key),
    ]
    _premium_family_signature = "|".join(
        re.sub(r"\s+", "_", str(_part or "").strip().lower())
        for _part in _signature_parts
        if str(_part or "").strip()
    )
    return {
        "raw_title": _title,
        "card_class": _card_class,
        "card_class_family": _card_class_family,
        "memorabilia_flag": bool(_mem_flag),
        "auto_flag": bool(_auto_flag),
        "patch_flag": bool(_patch_flag),
        "dual_flag": bool(_dual_flag),
        "subset_family": _subset_family,
        "subset_label": _subset_label,
        "parallel_label": _parallel_display,
        "serial_label": _serial_label,
        "serial_value": _serial_value,
        "grade_key": _grade_key,
        "grade_label": _grade_query_label(_grade_key),
        "product_display": _product_display,
        "premium_family_signature": _premium_family_signature[:180],
        "query_terms": tuple(_premium_query_class_terms(
            {
                "raw_title": _title,
                "card_class": _card_class,
                "subset_label": _subset_label,
                "parallel_label": _parallel_display,
                "serial_label": _serial_label,
            },
            _profile,
        )),
    }


def build_precise_sold_query_from_profile(
    prof: CardListingProfile,
    fallback_title: str = "",
    *,
    omit_parallel_in_query: bool = False,
    omit_card_number_in_query: bool = False,
    source_row: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build marketplace query from an already-parsed profile (stable across title wording).

    omit_parallel_in_query / omit_card_number_in_query widen **retrieval** only; comp acceptance
    still uses strict is_bad_comp_match / variant checks on returned titles.
    """
    title = (prof.raw_title or fallback_title or "").strip()
    parts: List[str] = []
    low = _norm(title)
    pbucket = normalize_parallel_bucket(prof)
    _player_display = _player_display_from_source(prof, source_row)
    _class_meta = _detect_premium_card_class(
        dict(source_row or {"title": title, "subset_name": prof.subset_family, "parallel_name": prof.parallel_phrase or pbucket})
    )
    _premium_mode = _is_premium_class_aware_profile(prof, _class_meta)
    _product_display = _class_meta.get("product_display") or _product_display_from_profile(prof)
    _subset_label = str(_class_meta.get("subset_label") or "")
    _grade_label = str(_class_meta.get("grade_label") or "")
    _query_terms = list(_class_meta.get("query_terms") or ())

    if _premium_mode:
        if prof.year:
            parts.append(prof.year)
        if _product_display:
            parts.append(_product_display)
        if _subset_label:
            parts.append(_subset_label)
        if _player_display:
            parts.append(_player_display)
        _serial_term = str(_class_meta.get("serial_label") or "").strip().lower()
        _query_prefix_terms: List[str] = []
        _query_suffix_terms: List[str] = []
        for _term in _query_terms:
            _clean = str(_term or "").strip()
            if not _clean:
                continue
            if _clean.lower() == _serial_term:
                _query_suffix_terms.append(_clean)
            else:
                _query_prefix_terms.append(_clean)
        for _term in _query_prefix_terms:
            if _term and _term.lower() not in " ".join(parts).lower():
                parts.append(_term)
        if not omit_parallel_in_query and pbucket not in {"base", "raw"}:
            _parallel_display = str(_class_meta.get("parallel_label") or "")
            if (
                _parallel_display
                and _parallel_display.lower() != _subset_label.lower()
                and _parallel_display.lower() not in " ".join(parts).lower()
            ):
                parts.append(_parallel_display)
        for _term in _query_suffix_terms:
            if _term and _term.lower() not in " ".join(parts).lower():
                parts.append(_term)
        if not omit_card_number_in_query and prof.card_number:
            parts.append(f"#{prof.card_number}")
        if prof.is_rookie:
            parts.append("RC")
        if prof.is_auto and _class_meta.get("card_class") not in {"rpa", "patch_auto", "dual_patch_auto"}:
            parts.append("Auto")
        if _grade_label:
            parts.append(_grade_label)
        q = " ".join(p for p in parts if p).strip()
        if len(q) < 8 and title:
            return title[:120].strip()
        return q[:200].strip()

    if prof.year:
        parts.append(prof.year)
    for b in prof.brands:
        parts.append(b)
    if prof.primary_set == "optic" and "donruss" in prof.set_tokens:
        parts.append("Donruss Optic")
    elif prof.primary_set:
        parts.append(prof.primary_set.capitalize() if prof.primary_set != "toppschrome" else "Topps Chrome")
    elif prof.set_tokens:
        parts.append(sorted(prof.set_tokens)[0].capitalize())

    if _player_display:
        parts.append(_player_display)
    if prof.card_number and not omit_card_number_in_query:
        parts.append(f"#{prof.card_number}")

    # Base queries must not inject parallel color tokens (pulls holo/silver/wave noise from eBay).
    if not omit_parallel_in_query and (pbucket != "base" or prof.is_auto):
        if prof.parallel_phrase:
            parts.append(prof.parallel_phrase.title())
        else:
            for t in ("Silver", "Gold", "Blue", "Red", "Green"):
                if t.lower() in prof.parallel_tokens:
                    parts.append(t)
                    break

    # Subset family — must appear in comp query for SSP/case-hit cards.
    # Placed before rookie/auto so subset is a leading discriminator.
    # Only inject if the subset is not already present in the parts built so far.
    if prof.subset_family:
        _sf_display = prof.subset_family.replace("_", " ").title()
        _parts_so_far = " ".join(parts).lower()
        if prof.subset_family.replace("_", " ").lower() not in _parts_so_far:
            parts.append(_sf_display)

    if prof.is_rookie:
        if re.search(r"\brated\s+rookie\b", low):
            parts.append("Rated Rookie")
        else:
            parts.append("RC")

    if prof.is_auto:
        parts.append("Auto")

    if prof.graded_hint and title:
        m = re.search(r"\b(psa|bgs|sgc)\s*(\d{1,2})\b", title, re.IGNORECASE)
        if m:
            parts.append(f"{m.group(1).upper()} {m.group(2)}")

    q = " ".join(p for p in parts if p).strip()
    if len(q) < 8 and title:
        return title[:120].strip()
    return q[:200].strip()


_QUERY_STOPWORDS = frozenset(
    """
    the a an and or for of to in on at by from with per lot see pics
    """.split()
)


def title_keyword_retrieval_query(raw_title: str, max_tokens: int = 14) -> str:
    """
    Short keyword window from the listing title for a last-resort comp search.
    Acceptance filters still reject wrong card # / variant / set.
    """
    t = (raw_title or "").strip()
    if len(t) < 10:
        return ""
    toks = re.findall(r"[A-Za-z0-9]+|\#\d+", t)
    out: List[str] = []
    for tok in toks:
        bare = tok.strip("#").lower()
        if len(bare) < 2 or bare in _QUERY_STOPWORDS:
            continue
        out.append(tok if tok.startswith("#") else tok)
        if len(out) >= max_tokens:
            break
    q = " ".join(out).strip()
    return q[:200].strip()


def _family_fallback_query_from_profile(
    prof: CardListingProfile,
    fallback_title: str = "",
    *,
    source_row: Optional[Dict[str, Any]] = None,
) -> str:
    """Product-family fallback: keep year/brand/set/player, drop card number and parallel noise."""
    title = (prof.raw_title or fallback_title or "").strip()
    parts: List[str] = []
    _class_meta = _detect_premium_card_class(dict(source_row or {"title": title}))
    _player_display = _player_display_from_source(prof, source_row)
    if _is_premium_class_aware_profile(prof, _class_meta):
        if prof.year:
            parts.append(prof.year)
        _product_display = str(_class_meta.get("product_display") or _product_display_from_profile(prof))
        if _product_display:
            parts.append(_product_display)
        if _player_display:
            parts.append(_player_display)
        if _class_meta.get("subset_label"):
            parts.append(str(_class_meta.get("subset_label")))
        for _term in list(_class_meta.get("query_terms") or ())[:2]:
            if _term and _term.lower() not in " ".join(parts).lower():
                parts.append(_term)
    else:
        if prof.year:
            parts.append(prof.year)
        for b in prof.brands[:2]:
            parts.append(b)
        if prof.primary_set == "optic" and "donruss" in prof.set_tokens:
            parts.append("Donruss Optic")
        elif prof.primary_set == "totallycertified":
            parts.append("Totally Certified")
        elif prof.primary_set:
            parts.append(prof.primary_set.capitalize() if prof.primary_set != "toppschrome" else "Topps Chrome")
        if _player_display:
            parts.append(_player_display)
        if prof.is_rookie:
            parts.append("RC")
        if prof.is_auto:
            parts.append("Auto")
    q = " ".join(p for p in parts if p).strip()
    if len(q) < 8 and title:
        return title[:120].strip()
    return q[:200].strip()


def _normalize_sold_title_tokens(title: str) -> str:
    raw = (title or "").strip()
    if not raw:
        return ""
    s = raw
    s = re.sub(r"\bpsa\s*([0-9]{1,2})\b", r"PSA \1", s, flags=re.IGNORECASE)
    s = re.sub(r"\bbgs\s*([0-9]{1,2}(?:\.\d)?)\b", r"BGS \1", s, flags=re.IGNORECASE)
    s = re.sub(r"\bsgc\s*([0-9]{1,2})\b", r"SGC \1", s, flags=re.IGNORECASE)
    s = re.sub(r"\bcgc\s*([0-9]{1,2})\b", r"CGC \1", s, flags=re.IGNORECASE)
    s = re.sub(r"\bno\.?\s*([0-9]{1,4})\b", r"#\1", s, flags=re.IGNORECASE)
    s = re.sub(r"\bnumber\s*([0-9]{1,4})\b", r"#\1", s, flags=re.IGNORECASE)
    s = re.sub(r"\brc\b", "Rookie", s, flags=re.IGNORECASE)
    s = re.sub(r"[^\w#\/ ]+", " ", s)
    toks = [tok for tok in s.split() if tok]
    ordered: List[str] = []
    seen: Set[str] = set()
    for tok in toks:
        key = tok.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(tok)
    return " ".join(ordered)[:200].strip()


def _grade_bridge_queries_from_profile(
    prof: CardListingProfile,
    fallback_title: str = "",
    *,
    source_row: Optional[Dict[str, Any]] = None,
) -> List[Tuple[str, str]]:
    title = (prof.raw_title or fallback_title or "").strip()
    if not prof.graded_hint:
        return []
    _class_meta = _detect_premium_card_class(dict(source_row or {"title": title}))
    _player_display = _player_display_from_source(prof, source_row)
    base_parts: List[str] = []
    if _is_premium_class_aware_profile(prof, _class_meta):
        if prof.year:
            base_parts.append(prof.year)
        if _class_meta.get("product_display"):
            base_parts.append(str(_class_meta.get("product_display")))
        if _class_meta.get("subset_label"):
            base_parts.append(str(_class_meta.get("subset_label")))
        if _player_display:
            base_parts.append(_player_display)
        for _term in list(_class_meta.get("query_terms") or ()):
            if _term and _term.lower() not in " ".join(base_parts).lower():
                base_parts.append(str(_term))
        if prof.card_number:
            base_parts.append(f"#{prof.card_number}")
    else:
        if prof.year:
            base_parts.append(prof.year)
        for b in prof.brands[:2]:
            base_parts.append(b)
        if prof.primary_set == "optic" and "donruss" in prof.set_tokens:
            base_parts.append("Donruss Optic")
        elif prof.primary_set == "totallycertified":
            base_parts.append("Totally Certified")
        elif prof.primary_set:
            base_parts.append(prof.primary_set.capitalize() if prof.primary_set != "toppschrome" else "Topps Chrome")
        if _player_display:
            base_parts.append(_player_display)
        if prof.card_number:
            base_parts.append(f"#{prof.card_number}")
        if prof.subset_family:
            base_parts.append(prof.subset_family.replace("_", " ").title())
        if prof.parallel_phrase:
            base_parts.append(prof.parallel_phrase.title())
        elif prof.parallel_tokens:
            for tok in sorted(prof.parallel_tokens):
                if tok not in ("base", "prizm"):
                    base_parts.append(tok.title())
                    break
        if prof.is_rookie:
            base_parts.append("RC")
        if prof.is_auto:
            base_parts.append("Auto")

    base_q = " ".join(x for x in base_parts if x).strip()
    if len(base_q) < 8 and title:
        base_q = title[:120].strip()
    passes: List[Tuple[str, str]] = []
    if base_q:
        passes.append(("recovery_pass_grade_bridge_raw", base_q[:200]))
    m = re.search(r"\bpsa\s*(\d{1,2})\b", title, re.IGNORECASE)
    if m:
        try:
            grade_n = int(m.group(1))
        except ValueError:
            grade_n = 0
        for delta, label in ((-1, "lower"), (1, "higher")):
            g = grade_n + delta
            if 1 <= g <= 10 and base_q:
                passes.append((f"recovery_pass_grade_bridge_{label}", f"{base_q} PSA {g}"[:200].strip()))
    dedup: List[Tuple[str, str]] = []
    seen_q: Set[str] = set()
    for label, q in passes:
        qn = (q or "").strip()
        if not qn:
            continue
        key = qn.lower()
        if key in seen_q:
            continue
        seen_q.add(key)
        dedup.append((label, qn))
    return dedup


def build_sold_query_variants(
    prof: CardListingProfile,
    fallback_title: str = "",
    *,
    source_row: Optional[Dict[str, Any]] = None,
) -> List[Tuple[str, str]]:
    title = (prof.raw_title or fallback_title or "").strip()
    passes: List[Tuple[str, str]] = []
    _player_display = _player_display_from_source(prof, source_row)

    strict_q = build_precise_sold_query_from_profile(prof, fallback_title=fallback_title, source_row=source_row)
    if strict_q:
        passes.append(("recovery_pass_a_strict", strict_q))

    for label, q in _exact_archetype_query_pack_from_profile(prof, fallback_title=fallback_title, source_row=source_row):
        if q and q.lower() not in {existing.lower() for _, existing in passes}:
            passes.append((label, q))

    for label, q in _premium_support_queries_from_profile(prof, fallback_title=fallback_title, source_row=source_row):
        if q and q.lower() not in {existing.lower() for _, existing in passes}:
            passes.append((label, q))

    # For subset-carrying cards, emit a subset-anchored pass after strict identity.
    if prof.subset_family and _player_display:
        _sf_display = prof.subset_family.replace("_", " ").title()
        _subset_anchor_q = f"{_player_display} {_sf_display}".strip()[:200]
        if _subset_anchor_q and _subset_anchor_q.lower() not in {existing.lower() for _, existing in passes}:
            passes.append(("recovery_pass_subset_anchor", _subset_anchor_q))

    normalized_q = _normalize_sold_title_tokens(strict_q or title)
    if normalized_q and normalized_q.lower() != (strict_q or "").lower():
        passes.append(("recovery_pass_b_normalized", normalized_q))

    near_q = build_precise_sold_query_from_profile(
        prof,
        fallback_title=fallback_title,
        omit_parallel_in_query=True,
        source_row=source_row,
    )
    if near_q and near_q.lower() not in {(strict_q or "").lower(), normalized_q.lower() if normalized_q else ""}:
        passes.append(("recovery_pass_c_near_lane", near_q))

    if prof.card_number:
        near_subset_q = build_precise_sold_query_from_profile(
            prof,
            fallback_title=fallback_title,
            omit_parallel_in_query=True,
            omit_card_number_in_query=True,
            source_row=source_row,
        )
        seen_lower = {q.lower() for _, q in passes}
        if near_subset_q and near_subset_q.lower() not in seen_lower:
            passes.append(("recovery_pass_c_near_lane_loose_number", near_subset_q))

    seen_lower = {q.lower() for _, q in passes}
    for label, q in _grade_bridge_queries_from_profile(prof, fallback_title=fallback_title, source_row=source_row):
        if q.lower() not in seen_lower:
            passes.append((label, q))
            seen_lower.add(q.lower())

    return passes


def _player_product_fallback_query_from_profile(
    prof: CardListingProfile,
    fallback_title: str = "",
    *,
    source_row: Optional[Dict[str, Any]] = None,
) -> str:
    """Broader fallback: keep player plus strongest product anchors without variant precision."""
    title = (prof.raw_title or fallback_title or "").strip()
    parts: List[str] = []
    _class_meta = _detect_premium_card_class(dict(source_row or {"title": title}))
    _player_display = _player_display_from_source(prof, source_row)
    if _player_display:
        parts.append(_player_display)
    if prof.year:
        parts.append(prof.year)
    if _is_premium_class_aware_profile(prof, _class_meta):
        if _class_meta.get("product_display"):
            parts.append(str(_class_meta.get("product_display")))
        if _class_meta.get("subset_label"):
            parts.append(str(_class_meta.get("subset_label")))
        for _term in list(_class_meta.get("query_terms") or ())[:2]:
            if _term and _term.lower() not in " ".join(parts).lower():
                parts.append(str(_term))
    else:
        if prof.primary_set == "optic" and "donruss" in prof.set_tokens:
            parts.append("Donruss Optic")
        elif prof.primary_set:
            parts.append(prof.primary_set.capitalize() if prof.primary_set != "toppschrome" else "Topps Chrome")
        elif prof.brands:
            parts.append(prof.brands[0])
        if prof.is_rookie:
            parts.append("RC")
        if prof.is_auto:
            parts.append("Auto")
    q = " ".join(p for p in parts if p).strip()
    if len(q) < 8 and title:
        return title[:120].strip()
    return q[:200].strip()


def build_comp_retrieval_query_passes(
    prof: CardListingProfile,
    fallback_title: str = "",
    *,
    source_row: Optional[Dict[str, Any]] = None,
) -> List[Tuple[str, str]]:
    """
    Ordered retrieval passes: strict → looser queries. Same strict filtering after fetch.

    Returns list of (pass_label, query_string).
    """
    title = (prof.raw_title or fallback_title or "").strip()
    passes: List[Tuple[str, str]] = []
    _class_meta = _detect_premium_card_class(dict(source_row or {"title": title}))
    _premium_mode = _is_premium_class_aware_profile(prof, _class_meta)

    p1 = build_precise_sold_query_from_profile(prof, fallback_title=fallback_title, source_row=source_row)
    if p1:
        passes.append(("pass1_strict", p1))

    for label, q in _exact_archetype_query_pack_from_profile(prof, fallback_title=fallback_title, source_row=source_row):
        if q and q.lower() not in {existing.lower() for _, existing in passes}:
            passes.append((label, q))

    for label, q in _premium_support_queries_from_profile(prof, fallback_title=fallback_title, source_row=source_row):
        if q and q.lower() not in {existing.lower() for _, existing in passes}:
            passes.append((label, q))

    p2 = build_precise_sold_query_from_profile(
        prof, fallback_title=fallback_title, omit_parallel_in_query=True, source_row=source_row
    )
    if p2 and p2.strip().lower() != (p1 or "").strip().lower():
        passes.append(("pass2_no_parallel_in_query", p2))

    if prof.card_number:
        p3 = build_precise_sold_query_from_profile(
            prof,
            fallback_title=fallback_title,
            omit_parallel_in_query=True,
            omit_card_number_in_query=True,
            source_row=source_row,
        )
        if p3 and p3.strip().lower() not in {(p1 or "").strip().lower(), (p2 or "").strip().lower()}:
            passes.append(("pass3_no_card_number_in_query", p3))

    p4 = _family_fallback_query_from_profile(prof, fallback_title=fallback_title, source_row=source_row)
    prev_lower = {x[1].strip().lower() for x in passes}
    if p4 and p4.strip().lower() not in prev_lower:
        passes.append(("pass4_product_family_fallback", p4))

    p5 = _player_product_fallback_query_from_profile(prof, fallback_title=fallback_title, source_row=source_row)
    prev_lower = {x[1].strip().lower() for x in passes}
    if p5 and p5.strip().lower() not in prev_lower:
        passes.append(("pass5_player_product_fallback", p5))

    if title and not _premium_mode:
        p4 = title_keyword_retrieval_query(title, max_tokens=14)
        prev_lower = {x[1].strip().lower() for x in passes}
        if p4 and p4.strip().lower() not in prev_lower and len(p4) >= 10:
            passes.append(("pass6_title_keywords", p4))

    return passes


def build_precise_sold_query(item: Dict[str, str]) -> str:
    """
    Build a specific marketplace query from an item dict (eBay-style keys supported).

    Uses the same title field precedence as canonical identity (card_name → title → summary).
    """
    title = listing_title_for_canonical(item)
    if not title or title.lower() in ("no title", "unknown"):
        return ""

    prof = parse_listing_profile(title)
    return build_precise_sold_query_from_profile(prof, fallback_title=title, source_row=dict(item or {}))


def grade_bucket_key(title: str) -> str:
    """Stable slab bucket for canonical identity (raw vs graded + company/grade)."""
    t = title or ""
    low = _norm(t)
    if not _graded_tokens(low):
        return "raw"
    m = re.search(r"\bpsa\s*(\d{1,2})\b", t, re.IGNORECASE)
    if m:
        return f"psa{m.group(1)}"
    m = re.search(r"\bbgs\s*(\d{1,2}(?:\.\d)?)\b", t, re.IGNORECASE)
    if m:
        return "bgs" + m.group(1).replace(".", "p")
    m = re.search(r"\bsgc\s*(\d{1,2})\b", t, re.IGNORECASE)
    if m:
        return f"sgc{m.group(1)}"
    m = re.search(r"\bcgc\s*(\d{1,2})\b", t, re.IGNORECASE)
    if m:
        return f"cgc{m.group(1)}"
    return "slab_other"


def normalize_parallel_bucket(p: CardListingProfile) -> str:
    """
    Collapse wording variants into one parallel bucket (e.g. True Silver / Silver Prizm).
    """
    lt = _norm(p.raw_title)
    vb = parallel_vocab.vocab_bucket_override(p.primary_set, lt)
    if vb:
        return vb
    fam = parallel_vocab.infer_variant_family_id(p.primary_set, p.raw_title)
    if fam:
        return fam
    ob = _donruss_optic_base_holo_bucket(p, lt)
    if ob:
        return ob
    if _is_topps_chrome_family_product(p.product_family or p.primary_set or "", p.raw_title):
        _topps_parallel = _infer_topps_chrome_parallel_family(p.raw_title)
        if _topps_parallel:
            return _topps_parallel
    prizm = p.primary_set == "prizm" or "prizm" in p.set_tokens
    mosaic_product = p.primary_set == "mosaic"
    if prizm and not mosaic_product and (
        p.parallel_phrase in ("silver prizm", "prizm silver")
        or re.search(r"\b(true\s+)?silver(\s+prizm)?\b", lt)
    ):
        return "silver_prizm"
    # On Mosaic cards "Silver Prizm" is a parallel branded with the Prizm name.
    # Strip "prizm" from the parallel bucket so it stays comparable to explicit parallel_bucket="silver".
    if mosaic_product and p.parallel_phrase:
        clean_phrase = re.sub(r"\bprizm\b", "", p.parallel_phrase.lower()).strip()
        if clean_phrase:
            slug = re.sub(r"[^a-z0-9]+", "_", clean_phrase).strip("_")
            if slug:
                return slug[:48]
    if p.parallel_phrase:
        slug = re.sub(r"[^a-z0-9]+", "_", p.parallel_phrase.strip().lower()).strip("_")
        return (slug or "para")[:48]
    if "silver" in p.parallel_tokens and prizm and not mosaic_product:
        return "silver_prizm"
    if p.parallel_tokens:
        return "_".join(sorted(p.parallel_tokens))[:48]
    return "base"


def player_key_slug(p: CardListingProfile) -> str:
    if not p.player_tokens:
        return "unknown"
    toks = {t for t in p.player_tokens if t.lower() not in NFL_TEAM_NICKNAMES}
    if not toks:
        return "unknown"
    return "_".join(sorted(toks))


def build_canonical_card_key_from_profile(prof: CardListingProfile) -> str:
    """
    Canonical key from an already-parsed profile (use after shared normalization).
    """
    y = prof.year or "na"
    st = prof.primary_set or "unknown"
    cn = normalize_card_number_for_key(prof.card_number)
    pb = normalize_parallel_bucket(prof)
    rc = "1" if prof.is_rookie else "0"
    au = "1" if prof.is_auto else "0"
    mem = "1" if prof.is_memorabilia else "0"
    gk = grade_bucket_key(prof.raw_title)
    pk = player_key_slug(prof)
    base = f"{y}|{st}|{cn}|{pb}|rc{rc}|a{au}|m{mem}|{gk}|{pk}"
    sn = _extract_serial_denominator(prof.raw_title)
    if sn:
        return f"{base}|sn{sn}"
    return base


def build_canonical_card_key(item: Dict[str, Any]) -> str:
    """
    Stable identity for the same card across listing title variants.
    Split auto/relic/set/slab/#/parallel/rookie; do not merge different products.
    """
    title = listing_title_for_canonical(item)
    if not title:
        return "empty"
    prof = parse_listing_profile(title)
    return build_canonical_card_key_from_profile(prof)


def build_canonical_key_components(item: Dict[str, Any]) -> Dict[str, Any]:
    """Structured fields used for the canonical key (for debug / split diagnostics)."""
    title = listing_title_for_canonical(item)
    if not title:
        return {
            "listing_title_preview": "",
            "title_fields_used": "card_name|title|summary (all empty)",
            "canonical_key": "empty",
        }
    src_bits = []
    if (item.get("card_name") or "").strip():
        src_bits.append("card_name")
    if (item.get("title") or "").strip():
        src_bits.append("title")
    if (item.get("summary") or "").strip():
        src_bits.append("summary")
    if (item.get("card_name") or "").strip():
        title_source = "card_name"
    elif (item.get("title") or "").strip():
        title_source = "title"
    elif (item.get("summary") or "").strip():
        title_source = "summary"
    else:
        title_source = "(none)"
    prof = parse_listing_profile(title)
    sn = _extract_serial_denominator(prof.raw_title)
    key = build_canonical_card_key_from_profile(prof)
    return {
        "listing_title_preview": title[:200],
        "canonical_title_source": title_source,
        "fields_populated": " > ".join(src_bits) or "(none)",
        "year": prof.year or "na",
        "primary_set": prof.primary_set or "unknown",
        "set_tokens": ",".join(sorted(prof.set_tokens)),
        "card_number_raw": prof.card_number or "",
        "card_number_normalized": normalize_card_number_for_key(prof.card_number),
        "parallel_bucket": normalize_parallel_bucket(prof),
        "is_rookie": prof.is_rookie,
        "is_auto": prof.is_auto,
        "is_memorabilia": prof.is_memorabilia,
        "grade_bucket": grade_bucket_key(prof.raw_title),
        "player_guess": prof.player_guess,
        "player_tokens": ",".join(sorted(prof.player_tokens)),
        "player_key_slug": player_key_slug(prof),
        "serial_denominator": sn or "",
        "canonical_key": key,
        "key_formula": "y|set|#|parallel|rc|a|m|grade|player[|sn{d}]",
    }


def detect_potential_canonical_over_splits(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Groups listings that share the same coarse identity but landed in different canonical keys
    (often parallel wording or player-token noise).
    """
    rows: List[Dict[str, Any]] = []
    for it in items or []:
        title = listing_title_for_canonical(it)
        if not title:
            continue
        prof = parse_listing_profile(title)
        ck = build_canonical_card_key(it)
        fp = (
            prof.year or "na",
            prof.primary_set or "unknown",
            normalize_card_number_for_key(prof.card_number),
            grade_bucket_key(prof.raw_title),
            player_key_slug(prof),
            "1" if prof.is_auto else "0",
            "1" if prof.is_memorabilia else "0",
            "1" if prof.is_rookie else "0",
            _extract_serial_denominator(prof.raw_title) or "",
        )
        rows.append(
            {
                "fp": fp,
                "ckey": ck,
                "title": title[:160],
                "parallel_bucket": normalize_parallel_bucket(prof),
            }
        )
    by_fp: Dict[tuple, List[dict]] = defaultdict(list)
    for r in rows:
        by_fp[r["fp"]].append(r)
    out: List[Dict[str, Any]] = []
    for fp, group in by_fp.items():
        keys = {g["ckey"] for g in group}
        if len(keys) <= 1:
            continue
        key_to_parallel = {g["ckey"]: g["parallel_bucket"] for g in group}
        out.append(
            {
                "shared_fingerprint": {
                    "year": fp[0],
                    "primary_set": fp[1],
                    "card_number": fp[2],
                    "grade_bucket": fp[3],
                    "player_key_slug": fp[4],
                    "auto": fp[5],
                    "mem": fp[6],
                    "rookie": fp[7],
                    "serial_denominator": fp[8] or "(none)",
                },
                "distinct_canonical_keys": sorted(keys),
                "parallel_bucket_by_key": key_to_parallel,
                "listing_count": len(group),
                "sample_titles": [g["title"] for g in group[:6]],
            }
        )
    out.sort(key=lambda x: -x["listing_count"])
    return out


def format_canonical_over_split_report(items: List[Dict[str, Any]], limit: int = 12) -> str:
    """Human-readable block for Streamlit debug."""
    groups = detect_potential_canonical_over_splits(items)[:limit]
    if not groups:
        return "(no potential over-split groups in this result set)"
    return json.dumps(groups, indent=2, ensure_ascii=False)[:14000]


def format_profile_for_debug(p: CardListingProfile) -> str:
    v = classify_card_variant(p.raw_title)
    return (
        f"year={p.year or '?'} | set={p.primary_set or '?'} | #={p.card_number or '?'} | "
        f"parallel_bucket={normalize_parallel_bucket(p)} | player={p.player_guess or '?'} | "
        f"RC={p.is_rookie} auto={p.is_auto} relic={p.is_memorabilia} graded_hint={p.graded_hint} | "
        f"variant={v.variant_family}"
    )


def synthetic_listing_title_for_valuation(p: CardListingProfile) -> str:
    """Single normalized title string used as listing_title for hybrid valuation (canonical runs)."""
    t = build_precise_sold_query_from_profile(p, fallback_title=p.raw_title)
    return t if t else (p.raw_title or "Unknown Card")


def _extract_serial_denominator(title: str) -> Optional[str]:
    """e.g. /149 -> 149, or 25/99 -> 99 (print run)."""
    if not title:
        return None
    m = re.search(r"(?:#\s*)?\b(\d{1,3})\s*/\s*(\d{1,4})\b", title)
    if m:
        try:
            a, b = int(m.group(1)), int(m.group(2))
        except ValueError:
            a, b = 99, 99
        pre = title[: m.start()].lower()
        # Skip PSA-style "9/10" centering notes near a PSA mention
        if not (a <= 10 and b <= 10 and re.search(r"\bpsa\b", pre[-120:])):
            _num = str(int(m.group(1)))
            _den = str(int(m.group(2)))
            print(
                f"[SERIAL_PARSE] title={str(title)[:140]} raw_fraction={m.group(0)!r} "
                f"numerator={_num} denominator={_den}"
            )
            return _den
    m = re.search(r"/\s*(\d{1,4})\b", title)
    if m:
        _den = str(int(m.group(1)))
        print(
            f"[SERIAL_PARSE] title={str(title)[:140]} raw_fraction={m.group(0)!r} "
            f"numerator= denominator={_den}"
        )
        return _den
    return None


def _support_slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower()).strip()


def _normalize_support_subset_name(value: Any) -> str:
    _slug = _support_slug(value).replace(" ", "_")
    if _slug in {"aura", "aurora"}:
        return "aurora"
    return _slug


def _premium_support_lane_meta(subset_name: Any) -> Dict[str, Any]:
    _key = _normalize_support_subset_name(subset_name)
    _meta = _PREMIUM_SUPPORT_LANE_MAP.get(_key) or {}
    return dict(_meta)


_PREMIUM_LANE_PRODUCTS: FrozenSet[str] = frozenset(
    {
        "topps chrome",
        "topps chrome black",
        "bowman chrome",
        "prizm",
        "select",
        "optic",
        "donruss optic",
        "finest",
        "topps finest",
    }
)

_PROMO_JUNK_TERMS: FrozenSet[str] = frozenset(
    {"rare", "investment", "mint", "mvp", "nice", "hot card", "look", "wow", "ssp"}
)


def _premium_identity_context(prof: CardListingProfile, source_row: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    _title = prof.raw_title or listing_title_for_canonical(source_row or {}) or ""
    _class_meta = _detect_premium_card_class(dict(source_row or {"title": _title}))
    _parallel_bucket = normalize_parallel_bucket(prof)
    return {
        "player": str(_player_display_from_source(prof, source_row) or "").strip(),
        "year": str(prof.year or "").strip(),
        "product": str(_class_meta.get("product_display") or _product_display_from_profile(prof) or "").strip(),
        "card_number": str(prof.card_number or "").strip(),
        "subset": str(_class_meta.get("subset_label") or (prof.subset_family.replace("_", " ").title() if prof.subset_family else "")).strip(),
        "parallel": str(_class_meta.get("parallel_label") or (prof.parallel_phrase or _parallel_bucket or "").replace("_", " ").title()).strip(),
        "serial": str(_class_meta.get("serial_label") or _serial_query_label(_extract_serial_denominator(_title))).strip(),
        "auto": "Auto" if prof.is_auto else "",
        "grade": str(_class_meta.get("grade_label") or _grade_query_label(grade_bucket_key(_title))).strip(),
    }


def _premium_query_string_from_identity(
    identity: Dict[str, str],
    *,
    include_card_number: bool = True,
    include_subset: bool = True,
    include_parallel: bool = True,
    include_serial: bool = True,
    include_grade: bool = True,
    include_auto: bool = True,
) -> str:
    _parts: List[str] = []
    for _field in ("year", "product", "player"):
        _value = str(identity.get(_field) or "").strip()
        if _value:
            _parts.append(_value)
    if include_card_number and str(identity.get("card_number") or "").strip():
        _parts.append(f"#{str(identity.get('card_number') or '').strip()}")
    if include_subset and str(identity.get("subset") or "").strip():
        _parts.append(str(identity.get("subset") or "").strip())
    if include_parallel and str(identity.get("parallel") or "").strip() and str(identity.get("parallel") or "").strip().lower() not in {"base", "raw"}:
        _parts.append(str(identity.get("parallel") or "").strip())
    if include_serial and str(identity.get("serial") or "").strip():
        _parts.append(str(identity.get("serial") or "").strip())
    if include_auto and str(identity.get("auto") or "").strip():
        _parts.append(str(identity.get("auto") or "").strip())
    if include_grade and str(identity.get("grade") or "").strip():
        _parts.append(str(identity.get("grade") or "").strip())
    _deduped: List[str] = []
    _seen: Set[str] = set()
    for _part in _parts:
        _key = _part.lower()
        if _key in _seen:
            continue
        _seen.add(_key)
        _deduped.append(_part)
    return " ".join(_deduped).strip()[:200]


def _promo_junk_identity_reason(target: CardListingProfile, comp_title: str) -> str:
    _cl = _norm(comp_title)
    _tokens = _extract_card_identity_tokens(comp_title)
    _promo_hits = [term for term in _PROMO_JUNK_TERMS if term in _cl]
    if not _promo_hits:
        return ""
    _has_card = bool(_tokens.get("card_number") and _tokens.get("card_number") != "na")
    _has_subset = bool(_tokens.get("subset_family"))
    _has_parallel = bool(_identity_parallel_family(_tokens) not in {"", "base", "raw"})
    _has_serial = bool(_tokens.get("serial_denominator"))
    _target_class_family = str(_extract_card_identity_tokens(target).get("card_class_family") or "").strip().lower()
    if "ssp" in _promo_hits and (_has_subset or _has_parallel or _has_serial):
        _promo_hits = [term for term in _promo_hits if term != "ssp"]
    if _promo_hits and not (_has_card or _has_subset or _has_parallel or _has_serial or _target_class_family not in {"", "base_family"}):
        return "promo_junk_identity"
    return ""


def _premium_support_signal_reason(target: CardListingProfile, comp_title: str) -> str:
    _topps_auto_eval = _evaluate_topps_auto_identity_pair(target, comp_title, emit_log=False)
    if bool(_topps_auto_eval.get("applies")):
        if bool(_topps_auto_eval.get("support_allow")):
            return str(_topps_auto_eval.get("support_reason") or "topps_auto_support_allow")
        return ""
    _tt = _extract_card_identity_tokens(target)
    _ct = _extract_card_identity_tokens(comp_title)
    _target_parallel = _identity_parallel_family(_tt)
    _comp_parallel = _identity_parallel_family(_ct)
    _subject_auto = 1 if subject_has_auto_identity(target.raw_title) else 0
    _comp_auto = 1 if comp_has_auto_identity(comp_title) else 0
    print(
        f"[AUTO_IDENTITY] title={str(target.raw_title or '')[:140]} subject_auto={_subject_auto} "
        f"comp_title={comp_title[:140]} comp_auto={_comp_auto}"
    )
    if _tt.get("card_number") and _tt.get("card_number") != "na" and _ct.get("card_number") == _tt.get("card_number"):
        return "card_number_match"
    if _tt.get("subset_family") and _ct.get("subset_family") == _tt.get("subset_family"):
        return "subset_match"
    if _target_parallel and _target_parallel not in {"base", "raw"} and _comp_parallel == _target_parallel:
        return "parallel_match"
    if _tt.get("serial_denominator") and _ct.get("serial_denominator") == _tt.get("serial_denominator"):
        return "serial_bucket_match"
    if _subject_auto and _comp_auto:
        print(
            f"[AUTO_MATCH_ASSERT] title={str(target.raw_title or '')[:140]} comp_title={comp_title[:140]} allow=1 reason=auto_match"
        )
        return "auto_match"
    if _subject_auto or _comp_auto:
        print(
            f"[AUTO_MATCH_ASSERT] title={str(target.raw_title or '')[:140]} comp_title={comp_title[:140]} "
            f"allow=0 reason={'auto_mismatch' if _subject_auto != _comp_auto else 'subject_not_auto'}"
        )
    _target_grade = _tt.get("grade_key") or ""
    _comp_grade = _ct.get("grade_key") or ""
    if _target_grade and _target_grade != "raw" and _comp_grade == _target_grade and (_target_parallel == _comp_parallel or _tt.get("subset_family") == _ct.get("subset_family")):
        return "graded_lane_match"
    if _tt.get("product_family") and _ct.get("product_family") == _tt.get("product_family") and _tt.get("subset_family") and _ct.get("subset_family") == _tt.get("subset_family"):
        return "strong_same_product_insert_family"
    return ""


def _support_lane_assert(target: CardListingProfile, comp_title: str) -> Tuple[bool, str]:
    _topps_auto_eval = _evaluate_topps_auto_identity_pair(target, comp_title, emit_log=True)
    if bool(_topps_auto_eval.get("applies")):
        _support_allow = bool(_topps_auto_eval.get("support_allow"))
        _support_reason = str(_topps_auto_eval.get("support_reason") or "topps_auto_support_blocked")
        _log_topps_auto_identity(
            "TOPPS_AUTO_SUPPORT_ALLOW" if _support_allow else "TOPPS_AUTO_SUPPORT_BLOCK",
            dict(_topps_auto_eval.get("target") or {}),
            dict(_topps_auto_eval.get("comp") or {}),
            _support_reason,
        )
        return _support_allow, _support_reason
    _tt = _extract_card_identity_tokens(target)
    _ct = _extract_card_identity_tokens(comp_title)
    _pm, _ = player_match_score(target, comp_title)
    _target_product = _tt.get("product_family") or _tt.get("primary_set") or ""
    _comp_product = _ct.get("product_family") or _ct.get("primary_set") or ""
    _support_reason = _premium_support_signal_reason(target, comp_title)
    _target_role = str(_tt.get("role_identity") or "").strip().lower()
    _comp_role = str(_ct.get("role_identity") or "").strip().lower()
    _target_subset = str(_tt.get("subset_family") or "").strip().lower()
    _comp_subset = str(_ct.get("subset_family") or "").strip().lower()
    _target_parallel = _identity_parallel_family(_tt)
    _comp_parallel = _identity_parallel_family(_ct)
    _target_grade_lane = str(_tt.get("grade_lane") or "raw").strip().lower()
    _comp_grade_lane = str(_ct.get("grade_lane") or "raw").strip().lower()
    _target_serial = str(_tt.get("serial_denominator") or "").strip().lower()
    _comp_serial = str(_ct.get("serial_denominator") or "").strip().lower()
    _subject_auto = subject_has_auto_identity(target.raw_title)
    _comp_auto = comp_has_auto_identity(comp_title)
    _target_card = str(_tt.get("card_number") or "").strip().lower()
    _comp_card = str(_ct.get("card_number") or "").strip().lower()
    _player_ok = bool(_pm >= 0.88)
    _product_ok = _premium_support_product_compatible(_target_product, _comp_product)
    _insert_ok = bool(
        not _target_subset
        or not _comp_subset
        or _comp_subset == _target_subset
        or (
            _premium_subset_bucket(target.raw_title) != "other"
            and _premium_subset_bucket(target.raw_title) == _premium_subset_bucket(comp_title)
        )
    )
    _parallel_ok = bool(
        _target_parallel
        and _target_parallel not in {"", "base", "raw"}
        and _comp_parallel == _target_parallel
    )
    _serial_ok = bool(
        _target_serial
        and _comp_serial
        and (
            _comp_serial == _target_serial
            or (
                _serial_support_bucket(_target_serial)
                and _serial_support_bucket(_target_serial) == _serial_support_bucket(_comp_serial)
            )
        )
    )
    _grade_ok = bool(
        _target_grade_lane == _comp_grade_lane
        or (_target_grade_lane != "raw" and _comp_grade_lane != "raw")
    )
    _accepted = False
    _reject_reason = ""
    if not _player_ok:
        _reject_reason = "missing_verified_overlap"
    elif _tt.get("year") and _ct.get("year") != _tt.get("year"):
        _reject_reason = "missing_verified_overlap"
    elif not _product_ok:
        _reject_reason = "missing_verified_overlap"
    elif _target_role and _comp_role and _target_role != _comp_role:
        _reject_reason = "role_mismatch_support"
    elif (_target_grade_lane != "raw" and _comp_grade_lane == "raw") or (_target_grade_lane == "raw" and _comp_grade_lane != "raw"):
        if _support_reason not in {"graded_lane_match", "subset_match", "parallel_match", "serial_bucket_match", "auto_match", "strong_same_product_insert_family"} and not (_player_ok and _product_ok and (_parallel_ok or _serial_ok)):
            _reject_reason = "raw_vs_graded_support_mismatch"
    _base_lane_chrome = bool(
        _target_product in {"topps_chrome", "topps_chrome_black", "bowman_chrome", "topps_finest"}
        and _target_parallel in {"", "base", "raw"}
        and not _target_serial
        and not _target_subset
        and not _subject_auto
    )
    if not _reject_reason and _support_reason == "card_number_match":
        _reject_reason = "card_number_only_support_too_weak"
    if not _reject_reason and _target_grade_lane != "raw":
        _strong_non_grade_anchor = _support_reason in {
            "subset_match", "parallel_match", "serial_bucket_match", "auto_match", "strong_same_product_insert_family"
        }
        if _support_reason != "graded_lane_match" and not (_strong_non_grade_anchor or (_player_ok and _product_ok and (_parallel_ok or _serial_ok))):
            _reject_reason = "graded_support_identity_too_weak"
    if not _reject_reason and _base_lane_chrome and _support_reason not in {"graded_lane_match", "subset_match", "strong_same_product_insert_family"} and not (_player_ok and _product_ok and (_parallel_ok or _serial_ok)):
        _reject_reason = "card_number_only_support_too_weak"
    if not _reject_reason:
        if _player_ok and _product_ok and _grade_ok and (_parallel_ok or _serial_ok):
            _accepted = True
        elif not _support_reason:
            if _target_role and _comp_role and _target_role == _comp_role:
                _accepted = True
            elif _insert_ok:
                if _target_parallel and _target_parallel not in {"", "base", "raw"} and _comp_parallel == _target_parallel:
                    _accepted = True
                elif _target_serial and _comp_serial and _serial_ok:
                    _accepted = True
                elif _subject_auto and _comp_auto:
                    _accepted = True
                elif _target_grade_lane != "raw" and _grade_ok:
                    _accepted = True
                elif _target_card and _target_card == _comp_card:
                    _reject_reason = "card_number_only_support_too_weak"
            if not _accepted and not _reject_reason:
                _reject_reason = "missing_verified_overlap"
        else:
            _accepted = True
    print(
        f"[COMP_FILTER_TRACE] title={str(target.raw_title or '')[:140]} "
        f"candidate={comp_title[:140]} "
        f"player_match={1 if _player_ok else 0} "
        f"product_match={1 if _product_ok else 0} "
        f"insert_match={1 if _insert_ok else 0} "
        f"parallel_match={1 if _parallel_ok else 0} "
        f"serial_match={1 if _serial_ok else 0} "
        f"grade_match={1 if _grade_ok else 0} "
        f"decision={'ACCEPT' if _accepted else 'REJECT'} "
        f"reject_reason={_reject_reason or ''}"
    )
    return _accepted, ("support_identity_pass" if _accepted else (_reject_reason or "missing_verified_overlap"))

_PREMIUM_LANE_PARALLEL_TERMS: FrozenSet[str] = frozenset(
    {
        "refractor",
        "sepia",
        "x-fractor",
        "x fractor",
        "prism refractor",
        "logofractor",
        "sapphire",
        "black",
        "mojo",
        "wave",
        "raywave",
        "shimmer",
        "lava",
        "atomic",
        "gold",
        "orange",
        "red",
        "blue",
        "green",
        "purple",
        "pink",
        "silver",
        "holo",
        "tie dye",
        "tie-dye",
        "zebra",
        "checkerboard",
        "elephant",
        "tiger",
        "vinyl",
        "superfractor",
    }
)

_PREMIUM_LANE_INSERT_TERMS: FrozenSet[str] = frozenset(
    {
        "future stars",
        "power players",
        "1984 topps",
        "1984 chrome",
    }
)


def premium_lane_classifier_signals(row: Any) -> Dict[str, Any]:
    _row = dict(row or {}) if isinstance(row, dict) else {}
    _title = str(_row.get("title") or _row.get("source_title") or row or "").strip()
    _profile = parse_listing_profile(_title)
    _class_meta = _detect_premium_card_class(_row or _title)
    _lower = _norm(_title)
    _product_raw = str(
        _row.get("product_family")
        or _row.get("target_product_family")
        or _row.get("lane_product")
        or _profile.product_family
        or _profile.primary_set
        or ""
    ).strip().lower()
    _parallel_raw = str(
        _row.get("parallel_name")
        or _row.get("parallel")
        or _row.get("parallel_bucket")
        or _class_meta.get("parallel_label")
        or _profile.parallel_phrase
        or ""
    ).strip().lower().replace("_", " ")
    _subset_raw = str(
        _row.get("subset_name")
        or _row.get("lane_subset")
        or _profile.subset_family
        or ""
    ).strip().lower().replace("_", " ")
    _serial = str(
        _row.get("serial")
        or _row.get("serial_denominator")
        or _extract_serial_denominator(_title)
        or ""
    ).strip().lower()
    _grade = str(
        _row.get("grade")
        or _row.get("grade_label")
        or _extract_grade_label(_title)
        or ""
    ).strip().lower()
    _insert_hint = str(_insert_premium_hint(_lower) or "").strip().lower().replace("_", " ")
    _reasons: List[str] = []
    _product_hit = any(_term in f" {_product_raw} " or _term in _lower for _term in _PREMIUM_LANE_PRODUCTS)
    if _product_hit:
        _reasons.append("premium_product_family")
    _parallel_terms = [
        _term for _term in _PREMIUM_LANE_PARALLEL_TERMS
        if _term in _parallel_raw or _term in _lower
    ]
    if _parallel_terms:
        _reasons.append(f"parallel_family:{sorted(set(_parallel_terms))[0]}")
    if _serial:
        _reasons.append("serial_numbered_lane")
    if _grade:
        _reasons.append("explicit_grade")
    if _insert_hint:
        _reasons.append(f"insert_family:{_insert_hint.replace(' ', '_')}")
    else:
        for _term in _PREMIUM_LANE_INSERT_TERMS:
            if _term in _lower:
                _reasons.append(f"insert_family:{_term.replace(' ', '_')}")
                break
    if bool(_class_meta.get("card_class_family")) in {True} and str(_class_meta.get("card_class_family") or "") in {"parallel_family", "subset_insert_family", "auto_family"}:
        _reasons.append(str(_class_meta.get("card_class_family") or ""))
    _premium_lane = bool(
        _product_hit
        and (
            bool(_parallel_terms)
            or bool(_serial)
            or bool(_insert_hint)
            or any(_term.startswith("insert_family:") for _term in _reasons)
            or (bool(_grade) and (bool(_parallel_terms) or bool(_serial)))
        )
    )
    if not _premium_lane and bool(_class_meta.get("card_class_family") or "") == "subset_insert_family" and _product_hit:
        _premium_lane = True
    return {
        "premium_lane": _premium_lane,
        "product": _product_raw,
        "subset": _subset_raw,
        "parallel": _parallel_raw,
        "serial": _serial,
        "grade": _grade,
        "insert_hint": _insert_hint,
        "reasons": list(dict.fromkeys(_reasons)),
    }


def _serial_support_bucket(value: Any) -> str:
    _raw = str(value or "").strip().lower()
    if not _raw or _raw in {"1/1", "1of1", "one_of_one"}:
        return ""
    try:
        if "/" in _raw:
            _fraction_match = re.search(r"(\d{1,3})\s*/\s*(\d{1,4})", _raw)
            if _fraction_match:
                _den = int(_fraction_match.group(2))
            else:
                _den = int(_extract_serial_denominator(_raw) or 0)
        else:
            _digits = re.sub(r"[^0-9]", "", _raw)
            if not _digits:
                return ""
            _den = int(_digits)
    except ValueError:
        return ""
    if 5 <= _den <= 10:
        return "serial_5_10"
    if 11 <= _den <= 25:
        return "serial_15_25"
    if 35 <= _den <= 50:
        return "serial_35_50"
    if 75 <= _den <= 99:
        return "serial_75_99"
    if 149 <= _den <= 199:
        return "serial_149_199"
    return ""


def _product_matches_support_alias(product_name: Any, aliases: Tuple[str, ...]) -> bool:
    _slug = _support_slug(product_name)
    if not _slug:
        return False
    _dense = _slug.replace(" ", "")
    for _alias in aliases or ():
        _alias_slug = _support_slug(_alias)
        if not _alias_slug:
            continue
        if _alias_slug in _slug or _alias_slug.replace(" ", "") in _dense:
            return True
    return False


def _premium_support_product_compatible(target_product: Any, comp_product: Any) -> bool:
    _target = str(target_product or "").strip().lower()
    _comp = str(comp_product or "").strip().lower()
    if not _target or not _comp:
        return False
    if _target == _comp:
        return True
    _target_family = _premium_product_family_key(_target)
    _comp_family = _premium_product_family_key(_comp)
    return bool(_target_family and _comp_family and _target_family == _comp_family)


def _log_support_handoff_out(
    target: CardListingProfile,
    support_comps: List[Dict[str, Any]],
    result: Optional[Dict[str, Any]] = None,
) -> None:
    _support_list = [dict(_c) for _c in list(support_comps or []) if isinstance(_c, dict)]
    print(
        f"[SUPPORT_HANDOFF_OUT] title={str(target.raw_title or '')[:140]} "
        f"accepted_support_count={len(list(_support_list or []))} "
        f"support_titles={[str((_c or {}).get('title') or '')[:100] for _c in list(_support_list or [])[:3]]}"
    )
    _result = result if isinstance(result, dict) else {
        "trusted_exact_comps": [],
        "support_comps": list(_support_list or []),
    }
    print(
        f"[COMP_RESULT_PAYLOAD] title={str(target.raw_title or '')[:140]} "
        f"trusted_exact_count={len(list(_result.get('trusted_exact_comps') or []))} "
        f"support_count={len(list(_result.get('support_comps') or []))}"
    )


def _is_generic_memorabilia_support_block(target: CardListingProfile) -> bool:
    if not target.is_memorabilia:
        return False
    _low = _norm(target.raw_title)
    if target.is_auto or re.search(r"\b(rpa|patch\s*auto|rookie\s*patch\s*autograph)\b", _low):
        return False
    return True


def _card_numbers_adjacent(target_card: str, comp_card: str) -> bool:
    if not target_card or not comp_card:
        return False
    if not str(target_card).isdigit() or not str(comp_card).isdigit():
        return False
    return abs(int(target_card) - int(comp_card)) <= 1


def _serial_bucket_rank(bucket: str) -> int:
    _order = {
        "serial_5_10": 0,
        "serial_15_25": 1,
        "serial_35_50": 2,
        "serial_75_99": 3,
        "serial_149_199": 4,
    }
    return int(_order.get(str(bucket or "").strip().lower(), -999))


def _serial_buckets_same_or_adjacent(a: str, b: str) -> bool:
    _ra = _serial_bucket_rank(a)
    _rb = _serial_bucket_rank(b)
    if _ra < 0 or _rb < 0:
        return False
    return abs(_ra - _rb) <= 1


def _premium_subset_bucket(title: str) -> str:
    _title = _norm(title)
    if "rpa" in _title or ("patch" in _title and "auto" in _title):
        return "patch_auto_family"
    if "auto" in _title or "autograph" in _title or "signature" in _title:
        return "auto_family"
    if any(_term in _title for _term in ("patch", "relic", "jersey", "material", "materials", "memorabilia", "mem", "swatch", "swatches")):
        return "relic_family"
    # Recognize premium base parallels (Prizm, Select, Mosaic, Optic, Chrome, etc.)
    # These are high-liquidity product families with real comp populations.
    if any(_term in _title for _term in ("prizm", "select", "mosaic", "optic", "chrome", "refractor", "donruss optic", "contenders", "spectra", "luminance")):
        return "base_parallel_family"
    return "other"


def _premium_product_family_key(value: Any) -> str:
    _slug = _support_slug(value)
    if not _slug:
        return ""
    _dense = _slug.replace(" ", "")
    if "topps chrome black" in _slug or "chrome black" in _slug:
        return "topps_chrome_black_family"
    if "topps chrome sapphire" in _slug or ("chrome" in _slug and "sapphire" in _slug):
        return "topps_chrome_sapphire_family"
    if "logofractor" in _slug:
        return "topps_chrome_logofractor_family"
    if "bowman chrome" in _slug:
        return "bowman_chrome_family"
    if "topps finest" in _slug or _slug == "finest" or " finest " in f" {_slug} ":
        return "finest_family"
    if "donruss optic" in _slug or _slug == "optic":
        return "optic_family"
    if _slug == "prizm" or " prizm " in f" {_slug} ":
        return "prizm_family"
    if _slug == "select" or " select " in f" {_slug} ":
        return "select_family"
    if _is_topps_chrome_family_product(_slug):
        return "topps_chrome_family"
    if any(_term in _slug for _term in ("sapphire", "logofractor", "mojo", "wave", "x fractor", "x-fractor", "refractor")):
        if "chrome" in _slug or "bowman" in _slug or "topps" in _slug or "finest" in _slug:
            return "topps_chrome_family"
    if "national treasures" in _slug or _slug == "nt":
        return "national_treasures"
    if "immaculate" in _slug:
        return "immaculate"
    if "flawless" in _slug:
        return "flawless"
    if "spectra" in _slug:
        return "spectra"
    if _dense in {"optic", "prizm", "select"}:
        return f"{_dense}_family"
    return ""


def _premium_serial_band(value: Any) -> str:
    _raw = str(value or "").strip().lower()
    if not _raw or _raw in {"1/1", "1of1", "one_of_one"}:
        return ""
    _digits = re.sub(r"[^0-9]", "", _raw)
    if not _digits:
        return ""
    try:
        _den = int(_digits)
    except ValueError:
        return ""
    if 5 <= _den <= 10:
        return "ultra_low"
    if 11 <= _den <= 25:
        return "low"
    if 26 <= _den <= 49:
        return "mid_low"
    if 50 <= _den <= 99:
        return "mid"
    return ""


def _parallel_band(parallel_name: str, serial_denominator: Any) -> str:
    _parallel = str(parallel_name or "").strip().lower()
    try:
        _den = int(serial_denominator) if serial_denominator not in (None, "") else None
    except Exception:
        _den = None
    if _den is not None:
        if _den <= 10:
            return "ultra_low"
        if _den <= 25:
            return "low"
        if _den <= 49:
            return "mid_low"
        if _den <= 99:
            return "mid"
    if "gold" in _parallel:
        return "gold_family"
    if "holo" in _parallel or "silver" in _parallel:
        return "holo_family"
    if "sapphire" in _parallel:
        return "sapphire_family"
    if "logofractor" in _parallel:
        return "logofractor_family"
    if "mojo" in _parallel:
        return "mojo_family"
    if "wave" in _parallel:
        return "wave_family"
    if "x-fractor" in _parallel or "x fractor" in _parallel:
        return "xfractor_family"
    if "refractor" in _parallel:
        return "refractor_family"
    if "black" in _parallel:
        return "black_family"
    return "generic"


def _premium_parallel_recovery_allowed(target: CardListingProfile, comp_title: str) -> Tuple[bool, str]:
    _meta = _premium_same_family_bucket_meta(target, comp_title)
    if not bool(_meta.get("allowed")):
        print(f"[PREMIUM_PARALLEL_DROP] title={comp_title[:120]} reason=same_family_bucket_missing")
        return False, "same_family_bucket_missing"
    _target_tokens = _extract_card_identity_tokens(target)
    _comp_tokens = _extract_card_identity_tokens(comp_title)
    _subject_band = _parallel_band(
        _identity_parallel_family(_target_tokens),
        _extract_serial_denominator(getattr(target, "raw_title", "") or ""),
    )
    _comp_band = _parallel_band(
        _identity_parallel_family(_comp_tokens),
        _extract_serial_denominator(comp_title),
    )
    _subject_serial_band = _premium_serial_band(_extract_serial_denominator(getattr(target, "raw_title", "") or ""))
    _comp_serial_band = _premium_serial_band(_extract_serial_denominator(comp_title))
    _allowed = False
    _reason = "parallel_band_mismatch"
    if _subject_band and _subject_band == _comp_band and _subject_band != "generic":
        _allowed = True
        _reason = "serial_or_gold_band"
    elif _subject_band == "gold_family" and _comp_band == "gold_family":
        _allowed = True
        _reason = "serial_or_gold_band"
    elif _subject_band and _subject_band == _comp_band and _subject_band in {
        "sapphire_family",
        "logofractor_family",
        "mojo_family",
        "wave_family",
        "xfractor_family",
        "refractor_family",
        "black_family",
    }:
        _allowed = True
        _reason = "parallel_family_match"
    elif (
        {_subject_band, _comp_band}.issubset({"gold_family", "holo_family"})
        and _subject_serial_band in {"ultra_low", "low", "mid_low"}
        and _subject_serial_band == _comp_serial_band
    ):
        _allowed = True
        _reason = "serial_or_gold_band"
    if _allowed:
        print(f"[PREMIUM_PARALLEL_RECOVERY] title={comp_title[:120]} allowed=1 reason={_reason}")
        return True, _reason
    print(f"[PREMIUM_PARALLEL_DROP] title={comp_title[:120]} reason={_reason}")
    return False, _reason


def _premium_same_family_bucket_meta(target: CardListingProfile, comp_title: str) -> Dict[str, Any]:
    _target_title = getattr(target, "raw_title", "") or ""
    _tt = _extract_card_identity_tokens(target)
    _ct = _extract_card_identity_tokens(comp_title)
    _subject_bucket = _premium_subset_bucket(_target_title)
    _comp_bucket = _premium_subset_bucket(comp_title)
    _subject_product = _premium_product_family_key(_tt.get("product_family") or _tt.get("primary_set") or _target_title)
    _comp_product = _premium_product_family_key(_ct.get("product_family") or _ct.get("primary_set") or comp_title)
    _allowed = bool(
        _subject_product
        and _comp_product
        and _subject_product == _comp_product
        and _subject_bucket in {"patch_auto_family", "auto_family", "relic_family", "base_parallel_family"}
        and _comp_bucket == _subject_bucket
    )
    print(f"[PREMIUM_BUCKET] subject={_subject_bucket} comp={_comp_bucket} allowed={int(_allowed)}")
    return {
        "allowed": _allowed,
        "subject_bucket": _subject_bucket,
        "comp_bucket": _comp_bucket,
        "subject_product": _subject_product,
        "comp_product": _comp_product,
    }


def _premium_serial_band_allowed(target: CardListingProfile, comp_title: str) -> bool:
    _meta = _premium_same_family_bucket_meta(target, comp_title)
    _subject_serial = _extract_serial_denominator(getattr(target, "raw_title", "") or "")
    _comp_serial = _extract_serial_denominator(comp_title)
    _subject_band = _premium_serial_band(_subject_serial)
    _comp_band = _premium_serial_band(_comp_serial)
    _allowed = bool(
        _meta.get("allowed")
        and _subject_serial
        and _comp_serial
        and _subject_band
        and _subject_band == _comp_band
    )
    print(f"[SERIAL_BAND] subject={_subject_serial} comp={_comp_serial} allowed={int(_allowed)}")
    return _allowed


def _premium_card_class_match(
    target_title_or_profile: Any,
    comp_title: str,
    *,
    lane_name: str = "",
) -> Tuple[bool, str]:
    _target_title = (
        target_title_or_profile.raw_title
        if isinstance(target_title_or_profile, CardListingProfile)
        else str(target_title_or_profile or "")
    )
    _target_meta = _detect_premium_card_class(_target_title)
    _comp_meta = _detect_premium_card_class(comp_title)
    _target_class = str(_target_meta.get("card_class") or "").strip().lower()
    _comp_class = str(_comp_meta.get("card_class") or "").strip().lower()
    _target_family = str(_target_meta.get("card_class_family") or "").strip().lower()
    _comp_family = str(_comp_meta.get("card_class_family") or "").strip().lower()
    _lane = str(lane_name or "").strip().lower()

    if _target_family == "base_family":
        return True, "base_family"
    if _target_family == "dual_patch_auto_family":
        return (_comp_family == _target_family), (
            "dual_patch_auto_family" if _comp_family == _target_family else "dual_patch_auto_only"
        )
    if _target_family == "patch_auto_family":
        return (_comp_family == _target_family), (
            "patch_auto_family" if _comp_family == _target_family else "patch_auto_family_only"
        )
    if _target_family == "memorabilia_family":
        if _comp_family != "memorabilia_family":
            return False, "memorabilia_family_only"
        return True, "memorabilia_family"
    if _target_family == "auto_family":
        return (_comp_family in {"auto_family", "patch_auto_family"}), (
            "auto_family" if _comp_family in {"auto_family", "patch_auto_family"} else "auto_family_only"
        )
    if _target_family == "subset_insert_family":
        _target_subset = _normalize_support_subset_name(_target_meta.get("subset_family"))
        _comp_subset = _normalize_support_subset_name(_comp_meta.get("subset_family"))
        if not _target_subset:
            return True, "subset_family_missing_target"
        if _comp_subset != _target_subset:
            return False, "subset_card_class_mismatch"
        return True, "subset_insert_family"
    if _target_family == "parallel_family":
        if _comp_family in {"memorabilia_family", "patch_auto_family", "dual_patch_auto_family"}:
            return False, "parallel_vs_mem_auto_mismatch"
        return True, "parallel_family"

    if _lane == "scarcity_bucket_support" and _target_family in {
        "patch_auto_family",
        "dual_patch_auto_family",
        "subset_insert_family",
        "memorabilia_family",
    }:
        _target_bucket = _serial_support_bucket(_target_meta.get("serial_value"))
        _comp_bucket = _serial_support_bucket(_comp_meta.get("serial_value"))
        if _target_bucket and _comp_bucket and _target_bucket == _comp_bucket:
            return True, "scarcity_bucket_support"
    return (_target_class == _comp_class), (
        "same_card_class" if _target_class == _comp_class else "wrong_card_class"
    )


def _premium_support_queries_from_profile(
    prof: CardListingProfile,
    fallback_title: str = "",
    *,
    source_row: Optional[Dict[str, Any]] = None,
) -> List[Tuple[str, str]]:
    passes: List[Tuple[str, str]] = []
    seen: Set[str] = set()

    def _push(label: str, *parts: Any) -> None:
        _deduped_parts: List[str] = []
        _seen_parts: Set[str] = set()
        for part in parts:
            _clean = str(part or "").strip()
            if not _clean:
                continue
            _key = _clean.lower()
            if _key in _seen_parts:
                continue
            _seen_parts.add(_key)
            _deduped_parts.append(_clean)
        _query = " ".join(_deduped_parts).strip()[:200]
        if not _query:
            return
        _key = _query.lower()
        if _key in seen:
            return
        seen.add(_key)
        passes.append((label, _query))

    _player = _player_display_from_source(prof, source_row)
    if not _player:
        return passes
    _class_meta = _detect_premium_card_class(dict(source_row or {"title": prof.raw_title or fallback_title}))
    _product_display = str(_class_meta.get("product_display") or _product_display_from_profile(prof))
    _subset_label = str(_class_meta.get("subset_label") or "")
    _serial_label = str(_class_meta.get("serial_label") or "")
    _grade_label = str(_class_meta.get("grade_label") or "")
    _query_terms = [str(_term) for _term in list(_class_meta.get("query_terms") or ()) if str(_term).strip()]
    _identity = _premium_identity_context(prof, source_row)

    if _is_premium_class_aware_profile(prof, _class_meta):
        _strict_query = _premium_query_string_from_identity(_identity)
        _support_query = _premium_query_string_from_identity(
            _identity,
            include_card_number=bool(_identity.get("card_number")),
            include_subset=True,
            include_parallel=True,
            include_serial=bool(_identity.get("serial")),
            include_grade=False,
        )
        print(
            f"[PREMIUM_QUERY_BUILD] title={str(prof.raw_title or fallback_title or '')[:140]} strict_query=\"{_strict_query}\" "
            f"support_query=\"{_support_query}\" card_number={_identity.get('card_number') or ''} subset={_identity.get('subset') or ''} "
            f"parallel={_identity.get('parallel') or ''} serial={_identity.get('serial') or ''} auto={1 if prof.is_auto else 0} "
            f"grade={_identity.get('grade') or ''}"
        )
        if _strict_query:
            _push("pass0_exact_identity", _strict_query)
        _query_mode = str((source_row or {}).get("query_mode") or "").strip().lower()
        _insert_serial_support_query = ""
        if (
            _query_mode == "insert_parallel_serial"
            and not str(_identity.get("card_number") or "").strip()
            and str(_identity.get("subset") or "").strip()
            and str(_identity.get("parallel") or "").strip()
            and str(_identity.get("serial") or "").strip()
            and str(_identity.get("auto") or "").strip()
        ):
            _insert_serial_support_query = _premium_query_string_from_identity(
                _identity,
                include_card_number=False,
                include_subset=True,
                include_parallel=False,
                include_serial=True,
                include_grade=False,
                include_auto=True,
            )
            if _insert_serial_support_query and _insert_serial_support_query.lower() != (_strict_query or "").lower():
                print(
                    f"[SUPPORT_QUERY_TRIGGER] title={str(prof.raw_title or fallback_title or '')[:140]} "
                    f"reason=exact_zero parallel_dropped=1 serial_locked={str(_identity.get('serial') or '')[:16]}"
                )
                _push("pass0_insert_serial_support", _insert_serial_support_query)
        _exact_product_card_parallel = _premium_query_string_from_identity(
            _identity,
            include_subset=False,
            include_serial=False,
            include_grade=True,
            include_auto=True,
        )
        if _exact_product_card_parallel and _exact_product_card_parallel.lower() != (_strict_query or "").lower():
            _push("pass1_product_card_parallel", _exact_product_card_parallel)
        if _support_query and _support_query.lower() not in {
            (_strict_query or "").lower(),
            (_exact_product_card_parallel or "").lower(),
            (_insert_serial_support_query or "").lower(),
        }:
            _push("pass2_same_family_premium_support", _support_query)
        if _serial_label:
            _push("pass2_same_family_serial_support", prof.year, _product_display, _subset_label, _player, *_query_terms[:2], _serial_label, _grade_label)
        if _class_meta.get("card_class") in {"relic", "memorabilia", "patch_auto", "rpa", "dual_patch_auto"}:
            _family_term = "Patch Auto" if str(_class_meta.get("card_class") or "") in {"patch_auto", "rpa", "dual_patch_auto"} else (_query_terms[0] if _query_terms else "Relic")
            _push("pass3_card_class_family", prof.year, _product_display, _player, _subset_label, _family_term, _serial_label, _grade_label)

    _meta = _premium_support_lane_meta(prof.subset_family)
    if _meta:
        for _subset_label in tuple(_meta.get("query_subset_labels") or (prof.subset_family.replace("_", " ").title(),)):
            _push("pass0_subset_anchor", prof.year, _player, _subset_label)
            for _product_label in tuple(_meta.get("query_products") or ()):
                _push("pass0_support_ecosystem", prof.year, _player, _product_label, _subset_label)

    _parallel_bucket = normalize_parallel_bucket(prof)
    _parallel_display = (prof.parallel_phrase or _parallel_bucket or "").replace("_", " ").strip().title()
    _product_display = str(_class_meta.get("product_display") or _product_display_from_profile(prof))
    if (
        prof.is_rookie
        and str(_class_meta.get("card_class") or "") in {"parallel", "subset_insert"}
        and _product_display
        and _parallel_display
        and _parallel_bucket not in {"", "base", "raw"}
    ):
        _subset_display = prof.subset_family.replace("_", " ").title() if prof.subset_family else ""
        _push(
            "pass0_rookie_color_support",
            prof.year,
            _player,
            _product_display,
            _subset_display,
            _parallel_display,
            "RC",
        )

    return passes


def _insert_premium_hint(lower: str) -> str:
    if "gold team" in lower:
        return "gold_team"
    if "color blast" in lower:
        return "color_blast"
    if "downtown" in lower:
        return "downtown"
    if "kaboom" in lower:
        return "kaboom"
    return ""


def classify_card_variant(title_or_item: Any) -> CardVariantClassification:
    """
    Strict variant bucket for comp gating: base vs holo/silver/parallel vs auto/relic vs numbered inserts.
    Accepts a raw title string or an item dict with title-like keys.
    """
    if isinstance(title_or_item, dict):
        title = listing_title_for_canonical(title_or_item)
    else:
        title = (title_or_item or "").strip()

    prof = parse_listing_profile(title)
    low = _norm(title)
    gk = grade_bucket_key(title)
    graded = gk != "raw"
    num = _extract_serial_denominator(title)
    ins = _insert_premium_hint(low)
    pb = normalize_parallel_bucket(prof)
    class_meta = _detect_premium_card_class(title)

    if str(class_meta.get("card_class") or "") == "dual_patch_auto":
        vf = "dual_patch_auto"
    elif str(class_meta.get("card_class") or "") in {"rpa", "patch_auto"}:
        vf = "patch_auto"
    elif prof.is_auto:
        vf = "auto"
    elif prof.is_memorabilia:
        vf = "relic"
    elif ins:
        vf = "insert_premium"
    elif num:
        vf = "numbered"
    else:
        vf = pb

    parallel_hint = (prof.parallel_phrase or "").strip()
    if not parallel_hint and prof.parallel_tokens:
        parallel_hint = "_".join(sorted(prof.parallel_tokens))

    return CardVariantClassification(
        raw_title=title,
        variant_family=vf,
        is_auto=prof.is_auto,
        is_relic=prof.is_memorabilia,
        is_graded=graded,
        grade_key=gk,
        primary_set=prof.primary_set,
        card_number=prof.card_number,
        number_print=num,
        insert_hint=ins,
        parallel_hint=parallel_hint[:80],
    )


def variant_match_assessment(
    target_prof: CardListingProfile,
    comp_title: str,
) -> Tuple[str, str]:
    """
    Classify how comp parallel relates to target (title-only).

    Returns (level, debug_compact) where level is one of:
    exact_variant_match | same_variant_family | weak_variant_match | wrong_variant
    """
    t_set = target_prof.primary_set
    tf = parallel_vocab.infer_variant_family_id(t_set, target_prof.raw_title)
    cf = parallel_vocab.infer_variant_family_id(t_set, comp_title)
    tb = normalize_parallel_bucket(target_prof)
    cp = parse_listing_profile(comp_title)
    cb = normalize_parallel_bucket(cp)

    dbg = f"set={t_set or '-'}|t_fam={tf or '-'}|c_fam={cf or '-'}|t_pb={tb}|c_pb={cb}"

    if tf and cf:
        if tf != cf:
            return "wrong_variant", dbg + "|cmp=wrong_family"
        if tb == cb:
            return "exact_variant_match", dbg + "|cmp=exact_bucket"
        return "same_variant_family", dbg + "|cmp=family_same_bucket_diff"

    if tf and not cf:
        return "wrong_variant", dbg + "|cmp=comp_missing_family"

    if cf and not tf:
        if tb != cb:
            return "wrong_variant", dbg + "|cmp=target_lacks_comp_family"
        return "weak_variant_match", dbg + "|cmp=ambiguous_target"

    if tb == cb:
        return "exact_variant_match", dbg + "|cmp=bucket_equal"

    return "weak_variant_match", dbg + "|cmp=bucket_diff"


def format_variant_class_debug(c: CardVariantClassification) -> str:
    num = c.number_print or "—"
    ins = c.insert_hint or "—"
    ph = c.parallel_hint or "—"
    return (
        f"family={c.variant_family} | grade={c.grade_key} | #={c.card_number or '?'} | "
        f"set={c.primary_set or '?'} | num_print={num} | insert={ins} | parallel={ph[:40]}"
    )


def _grade_keys_strict_mismatch(tk: str, ck: str) -> bool:
    """Same slab company, different numeric bucket (e.g. psa9 vs psa10)."""
    if not tk or not ck or tk == ck:
        return False
    for pref in ("psa", "bgs", "sgc", "cgc"):
        if tk.startswith(pref) and ck.startswith(pref):
            return tk != ck
    return False


def _psa_one_step_adjacent(tgk: str, cgk: str) -> bool:
    """PSA only: allow comps exactly one numeric grade away (e.g. 10 vs 9)."""
    if not (tgk.startswith("psa") and cgk.startswith("psa")):
        return False
    try:
        a = int(tgk[3:])
        b = int(cgk[3:])
    except ValueError:
        return False
    return abs(a - b) == 1


def _variants_compatible(t: CardVariantClassification, c: CardVariantClassification) -> Tuple[bool, str]:
    if t.variant_family == "dual_patch_auto":
        if c.variant_family != "dual_patch_auto":
            return False, "dual_patch_auto_mismatch"
        return True, ""
    if t.variant_family == "patch_auto":
        if c.variant_family != "patch_auto":
            return False, "patch_auto_family_mismatch"
        return True, ""
    if t.variant_family == "insert_premium":
        if t.insert_hint and c.insert_hint and t.insert_hint != c.insert_hint:
            return False, "insert_mismatch"
    if t.variant_family == "numbered":
        tp, cp = t.number_print or "", c.number_print or ""
        if tp and cp and tp != cp:
            return False, "numbered_print_mismatch"
        if (tp and not cp) or (cp and not tp):
            return False, "numbered_print_mismatch"

    if t.variant_family not in ("insert_premium", "numbered", "auto", "relic"):
        tp = parse_listing_profile(t.raw_title)
        vm_level, _ = variant_match_assessment(tp, c.raw_title)
        if vm_level == "wrong_variant":
            return False, "wrong_variant"
        return True, ""

    if t.variant_family != c.variant_family:
        return False, f"variant_family_mismatch ({t.variant_family} vs {c.variant_family})"
    return True, ""


def _extract_card_identity_tokens(title_or_profile: Any) -> Dict[str, str]:
    prof = title_or_profile if isinstance(title_or_profile, CardListingProfile) else parse_listing_profile(str(title_or_profile or ""))
    if not isinstance(prof, CardListingProfile):
        prof = parse_listing_profile(str(title_or_profile or ""))
    meta = _detect_premium_card_class(prof.raw_title)
    serial = _extract_serial_denominator(prof.raw_title)
    parallel_bucket = normalize_parallel_bucket(prof)
    parallel_family = _prefer_specific_parallel_identity(
        _normalize_parallel_identity(parallel_bucket),
        _normalize_parallel_identity(prof.parallel_phrase),
    )
    subset = (prof.subset_family or "").strip().lower()
    product = (prof.product_family or prof.primary_set or "").strip().lower()
    brand = ((prof.brands or ("",))[0] or "").strip().lower()
    _topps_auto = _extract_topps_chrome_auto_identity(prof)
    return {
        "year": (prof.year or "").strip(),
        "brand": brand,
        "product_family": product,
        "primary_set": (prof.primary_set or "").strip().lower(),
        "subset_family": subset,
        "role_identity": _extract_checklist_role_identity(prof.raw_title),
        "parallel_family": parallel_family,
        "parallel_bucket": (parallel_bucket or "").strip().lower(),
        "parallel_phrase": (prof.parallel_phrase or "").strip().lower().replace(" ", "_"),
        "card_number": normalize_card_number_for_key(prof.card_number),
        "serial_denominator": (serial or "").strip().lower(),
        "rookie": "1" if prof.is_rookie else "0",
        "auto": "1" if prof.is_auto else "0",
        "relic": "1" if prof.is_memorabilia else "0",
        "grade": grade_bucket_key(prof.raw_title),
        "grade_lane": _grade_lane_key(prof.raw_title),
        "card_class": str(meta.get("card_class") or "").strip().lower(),
        "card_class_family": str(meta.get("card_class_family") or "").strip().lower(),
        "premium_family_signature": str(meta.get("premium_family_signature") or "").strip().lower(),
        "product_root": str(_topps_auto.get("product_root") or "").strip().lower(),
        "product_branch": str(_topps_auto.get("product_branch") or "").strip().lower(),
        "auto_card_number": str(_topps_auto.get("auto_card_number") or "").strip().lower(),
        "topps_auto_parallel_family": str(_topps_auto.get("parallel_family") or "").strip().lower(),
        "topps_auto_grade_lane": str(_topps_auto.get("grade_lane") or "").strip().lower(),
    }


def _identity_parallel_family(tokens: Dict[str, str]) -> str:
    return str(
        tokens.get("parallel_family")
        or tokens.get("parallel_bucket")
        or tokens.get("parallel_phrase")
        or ""
    ).strip().lower()


def exact_parallel_identity_contract(
    target_or_profile: Any,
    candidate_title: str,
    *,
    source_row: Optional[Dict[str, Any]] = None,
    emit_log: bool = True,
) -> Dict[str, Any]:
    _source_row = dict(source_row or {})
    if isinstance(target_or_profile, dict):
        _source_row = dict(target_or_profile or {}) if not _source_row else _source_row
        _target_title = _subject_identity_row_value(_source_row, "title", "source_title")
        _target_profile = parse_listing_profile(str(_target_title or ""))
    else:
        _target_profile = (
            target_or_profile
            if isinstance(target_or_profile, CardListingProfile)
            else parse_listing_profile(str(target_or_profile or ""))
        )
    if not isinstance(_target_profile, CardListingProfile):
        _target_profile = parse_listing_profile(str(target_or_profile or ""))
    _subject = _extract_exact_subject_identity_bundle(
        _target_profile,
        source_row=_source_row,
        emit_log=emit_log,
    )
    _target_title = str(_subject.get("title") or getattr(_target_profile, "raw_title", "") or "").strip()
    _subject_parallel = str(_subject.get("parallel_family") or "").strip().lower()
    _candidate_tokens = _extract_card_identity_tokens(candidate_title)
    _candidate_parallel = _identity_parallel_family(_candidate_tokens)
    _product_family = str(_subject.get("product_family") or "").strip().lower()
    _topps_chrome_parallel = bool(
        _is_topps_chrome_family_product(_product_family, _target_title)
        and _subject_parallel not in {"", "base", "raw"}
    )
    _allow = True
    _reason = "parallel_family_not_applicable"
    if _topps_chrome_parallel:
        if _candidate_parallel == _subject_parallel:
            _reason = "parallel_family_match"
        elif not _candidate_parallel or _candidate_parallel in {"base", "raw"}:
            _allow = False
            _reason = "missing_candidate_parallel"
        else:
            _allow = False
            _reason = "wrong_parallel_family"
    if emit_log:
        print(
            f"[PARALLEL_IDENTITY_CANDIDATE] title={_target_title[:140]} "
            f"candidate_title={str(candidate_title or '')[:140]} "
            f"candidate_parallel={_candidate_parallel[:48]} match={1 if _allow else 0} "
            f"reason={_reason}"
        )
        if not _allow and _reason == "wrong_parallel_family":
            print(
                f"[PARALLEL_IDENTITY_REJECT] title={_target_title[:140]} "
                f"candidate_title={str(candidate_title or '')[:140]} "
                f"reason=wrong_parallel_family subject_parallel={_subject_parallel[:48]} "
                f"candidate_parallel={_candidate_parallel[:48]}"
            )
    return {
        "allow": bool(_allow),
        "reason": _reason,
        "subject_parallel": _subject_parallel,
        "candidate_parallel": _candidate_parallel,
        "product_family": _product_family,
    }


def _build_card_identity_signature(title_or_profile: Any) -> str:
    toks = _extract_card_identity_tokens(title_or_profile)
    parts: List[str] = []
    if toks.get("year"):
        parts.append(toks["year"])
    if toks.get("brand"):
        parts.append(toks["brand"].title())
    product = toks.get("product_family") or toks.get("primary_set") or ""
    if product:
        parts.append(product.replace("_", " ").title())
    if toks.get("subset_family"):
        parts.append(toks["subset_family"].replace("_", " ").title())
    if toks.get("card_number") and toks["card_number"] != "na":
        parts.append(f"#{toks['card_number']}")
    parallel = _identity_parallel_family(toks)
    if parallel and parallel not in ("base", "raw"):
        parts.append(parallel.replace("_", " ").title())
    return " • ".join(parts[:5])


def _exact_lane_assert(target: CardListingProfile, comp_title: str) -> Tuple[bool, str]:
    _archetype = select_exact_comp_archetype(target, emit_log=False)
    if _archetype:
        _archetype_allow, _archetype_reason = _exact_archetype_candidate_match(target, comp_title)
        if _archetype_allow:
            return True, "exact_archetype_identity_pass"
        return False, _archetype_reason
    _topps_auto_eval = _evaluate_topps_auto_identity_pair(target, comp_title, emit_log=True)
    if bool(_topps_auto_eval.get("applies")):
        if bool(_topps_auto_eval.get("exact_allow")):
            return True, "topps_auto_exact_identity_pass"
        _exact_reason = str(_topps_auto_eval.get("exact_reason") or "topps_auto_exact_blocked")
        _log_topps_auto_identity(
            "TOPPS_AUTO_EXACT_BLOCK",
            dict(_topps_auto_eval.get("target") or {}),
            dict(_topps_auto_eval.get("comp") or {}),
            _exact_reason,
        )
        return False, _exact_reason
    ct = _extract_card_identity_tokens(comp_title)
    tt = _extract_card_identity_tokens(target)
    _pm, _ = player_match_score(target, comp_title)
    if _pm < 0.88:
        return False, "missing_strong_identity"
    _class_ok, _class_reason = _premium_card_class_match(target, comp_title, lane_name="exact_lane")
    if not _class_ok:
        return False, _class_reason or "missing_strong_identity"
    if tt["year"] and ct["year"] != tt["year"]:
        return False, "missing_strong_identity"
    target_product = tt["product_family"] or tt["primary_set"]
    comp_product = ct["product_family"] or ct["primary_set"]
    if not target_product or not comp_product or comp_product != target_product:
        return False, "missing_strong_identity"
    if tt["card_number"] == "na" or ct["card_number"] == "na":
        return False, "card_number_only_not_enough"
    if ct["card_number"] != tt["card_number"]:
        return False, "card_number_only_not_enough"
    _target_role = str(tt.get("role_identity") or "").strip().lower()
    _comp_role = str(ct.get("role_identity") or "").strip().lower()
    if _target_role and _comp_role and _target_role != _comp_role:
        return False, "role_mismatch"
    if (_target_role and not _comp_role) or (_comp_role and not _target_role):
        return False, "missing_strong_identity"
    if tt["subset_family"] and ct["subset_family"] and ct["subset_family"] != tt["subset_family"]:
        return False, "subset_mismatch"
    if (tt["subset_family"] and not ct["subset_family"]) or (ct["subset_family"] and not tt["subset_family"]):
        return False, "missing_strong_identity"
    _target_parallel = _identity_parallel_family(tt)
    _comp_parallel = _identity_parallel_family(ct)
    if _is_topps_chrome_family_product(
        tt.get("product_family") or tt.get("primary_set") or "",
        getattr(target, "raw_title", "") or "",
    ):
        _parallel_contract = exact_parallel_identity_contract(target, comp_title, emit_log=True)
        if _target_parallel and _target_parallel not in {"base", "raw"} and not bool(_parallel_contract.get("allow")):
            return False, "parallel_mismatch"
    if _target_parallel and _target_parallel not in {"base", "raw"}:
        if _comp_parallel != _target_parallel:
            return False, "parallel_mismatch"
    elif _comp_parallel and _comp_parallel not in {"base", "raw"}:
        return False, "parallel_mismatch"
    _target_grade_lane = str(tt.get("grade_lane") or "raw").strip().lower()
    _comp_grade_lane = str(ct.get("grade_lane") or "raw").strip().lower()
    if _target_grade_lane != "raw" and _comp_grade_lane == "raw":
        return False, "raw_vs_graded_mismatch"
    if _target_grade_lane == "raw" and _comp_grade_lane != "raw":
        return False, "raw_vs_graded_mismatch"
    if _target_grade_lane != _comp_grade_lane:
        return False, "graded_lane_mismatch"
    if tt["serial_denominator"] and ct["serial_denominator"] != tt["serial_denominator"]:
        return False, "parallel_mismatch"
    return True, "exact_identity_pass"


def _same_exact_comp_lane(target: CardListingProfile, comp_title: str) -> bool:
    _allow, _reason = _exact_lane_assert(target, comp_title)
    print(
        f"[EXACT_LANE_ASSERT] title={str(target.raw_title or '')[:140]} comp_title={comp_title[:140]} "
        f"allow={1 if _allow else 0} reason={_reason}"
    )
    return _allow


def _same_near_comp_lane(target: CardListingProfile, comp_title: str) -> bool:
    _topps_auto_eval = _evaluate_topps_auto_identity_pair(target, comp_title, emit_log=False)
    if bool(_topps_auto_eval.get("applies")):
        return True
    ct = _extract_card_identity_tokens(comp_title)
    tt = _extract_card_identity_tokens(target)
    _class_ok, _ = _premium_card_class_match(target, comp_title, lane_name="near_lane")
    if not _class_ok:
        return False
    _premium_bucket_meta = _premium_same_family_bucket_meta(target, comp_title)
    _target_class_family = str(tt.get("card_class_family") or "").strip().lower()
    if tt["year"] and ct["year"] and ct["year"] != tt["year"]:
        return False
    target_product = tt["product_family"] or tt["primary_set"]
    comp_product = ct["product_family"] or ct["primary_set"]
    if target_product and comp_product and comp_product != target_product:
        return False
    if tt["subset_family"]:
        if ct["subset_family"] != tt["subset_family"] and not bool(_premium_bucket_meta.get("allowed")):
            return False
    elif ct["subset_family"]:
        return False
    if tt["card_number"] != "na" and ct["card_number"] != "na" and ct["card_number"] != tt["card_number"]:
        return False
    if tt["serial_denominator"] and ct["serial_denominator"] and ct["serial_denominator"] != tt["serial_denominator"]:
        if not _premium_serial_band_allowed(target, comp_title):
            return False
        print(f"[COMP_KEEP_NEAR] title={comp_title[:140]} reason=same_family_bucket")
    if _target_class_family not in {"patch_auto_family", "memorabilia_family", "dual_patch_auto_family"}:
        _target_parallel = _identity_parallel_family(tt)
        _comp_parallel = _identity_parallel_family(ct)
        if _target_parallel and _target_parallel not in {"base", "raw"} and _comp_parallel != _target_parallel:
            return False
    return True


def _same_subset_ecosystem_support_lane(target: CardListingProfile, comp_title: str) -> bool:
    if _is_generic_memorabilia_support_block(target):
        return False
    _class_ok, _ = _premium_card_class_match(target, comp_title, lane_name="subset_ecosystem_support")
    if not _class_ok:
        return False
    tt = _extract_card_identity_tokens(target)
    ct = _extract_card_identity_tokens(comp_title)
    _meta = _premium_support_lane_meta(tt["subset_family"])
    if not _meta:
        return False
    _target_subset = _normalize_support_subset_name(tt["subset_family"])
    _comp_subset = _normalize_support_subset_name(ct["subset_family"])
    if not _target_subset or _comp_subset != _target_subset:
        return False
    if tt["year"] and ct["year"] and ct["year"] != tt["year"]:
        return False
    _target_product = tt["product_family"] or tt["primary_set"]
    _comp_product = ct["product_family"] or ct["primary_set"]
    _aliases = tuple(_meta.get("accepted_product_aliases") or ())
    if _target_product and not _product_matches_support_alias(_target_product, _aliases):
        return False
    if not _comp_product or not _product_matches_support_alias(_comp_product, _aliases):
        return False
    if tt["card_number"] != "na" and ct["card_number"] != "na" and ct["card_number"] != tt["card_number"]:
        return False
    _target_serial = tt["serial_denominator"]
    _comp_serial = ct["serial_denominator"]
    if _target_serial:
        if not _comp_serial:
            return False
        if _comp_serial != _target_serial:
            _target_bucket = _serial_support_bucket(_target_serial)
            _comp_bucket = _serial_support_bucket(_comp_serial)
            if not _target_bucket or _target_bucket != _comp_bucket:
                return False
    return True


def _same_scarcity_bucket_support_lane(target: CardListingProfile, comp_title: str) -> bool:
    if _is_generic_memorabilia_support_block(target):
        return False
    _class_ok, _ = _premium_card_class_match(target, comp_title, lane_name="scarcity_bucket_support")
    if not _class_ok:
        return False
    tt = _extract_card_identity_tokens(target)
    ct = _extract_card_identity_tokens(comp_title)
    _target_bucket = _serial_support_bucket(tt["serial_denominator"])
    _comp_bucket = _serial_support_bucket(ct["serial_denominator"])
    _premium_bucket_meta = _premium_same_family_bucket_meta(target, comp_title)
    _target_family = str(tt.get("card_class_family") or "").strip().lower()
    _bucket_ok = bool(_target_bucket and _comp_bucket and _target_bucket == _comp_bucket)
    if not _bucket_ok and _premium_serial_band_allowed(target, comp_title):
        _bucket_ok = True
    if not _bucket_ok:
        return False
    if tt["year"] and ct["year"] and ct["year"] != tt["year"]:
        return False
    _target_product = tt["product_family"] or tt["primary_set"]
    _comp_product = ct["product_family"] or ct["primary_set"]
    _meta = _premium_support_lane_meta(tt["subset_family"])
    _ecosystem_ok = bool(
        _meta
        and _comp_product
        and _product_matches_support_alias(_comp_product, tuple(_meta.get("accepted_product_aliases") or ()))
        and (
            not _target_product
            or _product_matches_support_alias(_target_product, tuple(_meta.get("accepted_product_aliases") or ()))
        )
    )
    if _target_product and _comp_product != _target_product and not _ecosystem_ok:
        return False
    if tt["subset_family"]:
        if (
            _normalize_support_subset_name(ct["subset_family"]) != _normalize_support_subset_name(tt["subset_family"])
            and not bool(_premium_bucket_meta.get("allowed"))
        ):
            return False
    elif ct["subset_family"]:
        return False
    if tt["card_number"] != "na" and ct["card_number"] != "na" and ct["card_number"] != tt["card_number"]:
        return False
    _target_parallel = _identity_parallel_family(tt)
    _comp_parallel = _identity_parallel_family(ct)
    if _target_family not in {"patch_auto_family", "memorabilia_family", "dual_patch_auto_family"} and _target_parallel and _target_parallel not in ("base", "raw"):
        if not _comp_parallel or _comp_parallel != _target_parallel:
            return False
    return True


def _same_rookie_color_support_lane(target: CardListingProfile, comp_title: str) -> bool:
    if _is_generic_memorabilia_support_block(target) or not target.is_rookie:
        return False
    _class_ok, _ = _premium_card_class_match(target, comp_title, lane_name="rookie_color_support")
    if not _class_ok:
        return False
    tt = _extract_card_identity_tokens(target)
    ct = _extract_card_identity_tokens(comp_title)
    if tt["year"] and ct["year"] and ct["year"] != tt["year"]:
        return False
    _target_product = tt["product_family"] or tt["primary_set"]
    _comp_product = ct["product_family"] or ct["primary_set"]
    if not _target_product or not _comp_product or _comp_product != _target_product:
        return False
    _target_parallel = _identity_parallel_family(tt)
    _comp_parallel = _identity_parallel_family(ct)
    if not _target_parallel or _target_parallel in {"base", "raw"}:
        return False
    if _comp_parallel != _target_parallel:
        return False
    if tt["subset_family"]:
        if ct["subset_family"] != tt["subset_family"]:
            return False
    elif ct["subset_family"]:
        return False
    _target_serial = tt["serial_denominator"]
    if _target_serial:
        _comp_serial = ct["serial_denominator"]
        if not _comp_serial:
            return False
        if _comp_serial != _target_serial:
            _target_bucket = _serial_support_bucket(_target_serial)
            _comp_bucket = _serial_support_bucket(_comp_serial)
            if not _target_bucket or _target_bucket != _comp_bucket:
                return False
    _target_card = tt["card_number"]
    _comp_card = ct["card_number"]
    if _target_card != "na" and _comp_card != "na" and _comp_card != _target_card:
        if not _card_numbers_adjacent(_target_card, _comp_card):
            return False
    if target.is_rookie and ct["rookie"] != "1":
        return False
    return True


def _detect_comp_lane_contamination(
    target: CardListingProfile,
    comp_titles: List[str],
) -> Tuple[bool, str, str]:
    subset_fams: Set[str] = set()
    product_fams: Set[str] = set()
    card_fams: Set[str] = set()
    class_fams: Set[str] = set()
    for ct in comp_titles or []:
        sig = _extract_card_identity_tokens(ct)
        subset = sig.get("subset_family") or ""
        product = sig.get("product_family") or sig.get("primary_set") or ""
        card_no = sig.get("card_number") or ""
        class_family = sig.get("card_class_family") or ""
        if subset:
            subset_fams.add(subset)
        if product:
            product_fams.add(product)
        if card_no and card_no != "na":
            card_fams.add(card_no)
        if class_family and class_family != "base_family":
            class_fams.add(class_family)
    target_class_family = _extract_card_identity_tokens(target).get("card_class_family") or ""
    if target_class_family and target_class_family != "base_family" and len(class_fams) > 1:
        return True, "card_class_family_mixed", ", ".join(sorted(x.replace("_", " ") for x in class_fams)[:4])
    if target.subset_family and len(subset_fams) > 1:
        return True, "subset_family_mixed", ", ".join(sorted(x.replace("_", " ") for x in subset_fams)[:4])
    if target.card_number and len(card_fams) > 1:
        return True, "card_number_family_mixed", ", ".join(sorted(card_fams)[:4])
    target_product = (target.product_family or target.primary_set or "").strip().lower()
    if target_product and len(product_fams) > 1:
        return True, "product_family_mixed", ", ".join(sorted(x.replace("_", " ") for x in product_fams)[:4])
    return False, "", ""


_RAW_TITLE_PRODUCT_BRAND_TOKENS_ORDERED: Tuple[Tuple[str, str], ...] = (
    # Longest tokens first (so "topps chrome black" matches before "topps chrome").
    ("topps chrome black", "topps_chrome_black"),
    ("topps chrome sapphire", "topps_chrome_sapphire"),
    ("topps chrome update", "topps_chrome"),
    ("contenders optic", "contenders_optic"),
    ("contenders v", "contenders"),
    ("donruss optic", "donruss_optic"),
    ("panini prizm draft picks", "prizm_draft_picks"),
    ("prizm draft picks", "prizm_draft_picks"),
    ("national treasures", "national_treasures"),
    ("topps transcendent", "topps_transcendent"),
    ("topps definitive", "topps_definitive"),
    ("rookies & stars", "rookies_and_stars"),
    ("rookies and stars", "rookies_and_stars"),
    ("topps chrome", "topps_chrome"),
    ("bowman chrome", "bowman_chrome"),
    ("topps finest", "topps_finest"),
    ("topps heritage", "topps_heritage"),
    ("topps update", "topps_flagship"),
    ("topps phoenix", "phoenix"),
    ("panini phoenix", "phoenix"),
    ("panini absolute", "absolute"),
    ("panini select", "select"),
    ("panini mosaic", "mosaic"),
    ("panini obsidian", "obsidian"),
    ("panini contenders", "contenders"),
    ("panini prizm", "prizm"),
    ("panini chronicles", "chronicles"),
    ("panini legacy", "legacy"),
    ("panini score", "score"),
    ("panini donruss", "donruss"),
    ("contenders", "contenders"),
    ("immaculate", "immaculate"),
    ("flawless", "flawless"),
    ("spectra", "spectra"),
    ("absolute", "absolute"),
    ("phoenix", "phoenix"),
    ("optic", "donruss_optic"),
    ("mosaic", "mosaic"),
    ("select", "select"),
    ("prizm", "prizm"),
    ("bowman", "bowman_paper"),
    ("topps", "topps_flagship"),
    ("score", "score"),
    ("legacy", "legacy"),
    ("donruss", "donruss"),
    ("zenith", "zenith"),
)


def _raw_title_product_brand(title: Any) -> str:
    """
    Extract a canonical product brand from the raw title using longest-token-
    wins matching. Used to prevent cross-product comp contamination where the
    structured `product_family` extractor mistakes a parallel name like
    "Silver Prizm" inside a Contenders Optic title for the "Panini Prizm"
    product brand. Operates purely on raw title strings — no extractor.
    """
    try:
        _lower = str(title or "").lower()
        if not _lower:
            return ""
        for _tok, _canon in _RAW_TITLE_PRODUCT_BRAND_TOKENS_ORDERED:
            if _tok in _lower:
                return _canon
    except Exception:
        return ""
    return ""


def _raw_title_product_brand_match(target_title: Any, comp_title: Any) -> Tuple[bool, str, str]:
    """
    True iff both titles resolve to the same canonical product brand, OR
    either title's brand could not be determined (in which case downstream
    structured checks remain authoritative). False only when BOTH titles
    resolve to brands AND those brands differ — that's a definitive cross-
    product mismatch (e.g. Contenders Optic vs Panini Prizm).
    """
    _target_brand = _raw_title_product_brand(target_title)
    _comp_brand = _raw_title_product_brand(comp_title)
    if not _target_brand or not _comp_brand:
        return True, _target_brand, _comp_brand
    return _target_brand == _comp_brand, _target_brand, _comp_brand


def _apply_comp_lane_penalties(
    target: CardListingProfile,
    comp_title: str,
) -> Dict[str, Any]:
    target_sig = _build_card_identity_signature(target)
    comp_sig = _build_card_identity_signature(comp_title)
    target_tokens = _extract_card_identity_tokens(target)
    target_class_family = str(target_tokens.get("card_class_family") or "").strip().lower()
    # [RAW_TITLE_PRODUCT_BRAND_GUARD] — cross-product safety check.
    # The structured extractor (_extract_card_identity_tokens) sometimes
    # confuses a parallel name like "Silver Prizm" inside a Contenders
    # Optic title with the "Panini Prizm" product brand, allowing comps
    # to admit across products. This raw-title check uses unambiguous
    # product brand tokens to detect these cross-product mismatches and
    # block them at the comp-lane gate.
    _raw_brand_match, _raw_target_brand, _raw_comp_brand = _raw_title_product_brand_match(
        getattr(target, "raw_title", "") or "",
        comp_title,
    )
    if not _raw_brand_match:
        try:
            print(
                f"[RAW_TITLE_PRODUCT_BRAND_GUARD] "
                f"title={str(getattr(target, 'raw_title', '') or '')[:140]} "
                f"comp_title={str(comp_title)[:140]} "
                f"target_brand={_raw_target_brand} comp_brand={_raw_comp_brand} "
                f"action=reject_cross_product_comp"
            )
        except Exception:
            pass
        return {
            "reject": True,
            "lane": "reject",
            "quality_mult": 0.0,
            "exactness_tier": "weak_fallback_lane",
            "reason": f"raw_brand_mismatch:{_raw_target_brand}_vs_{_raw_comp_brand}",
            "target_signature": target_sig,
            "comp_signature": comp_sig,
            "support_signal_reason": "",
        }
    # [LOW_SERIAL_TIER_GUARD] — protect low-print-run targets from being
    # valued against high-print-run comps. A /25 Black Pandora is dramatically
    # more rare and more valuable than a /199 base parallel — comping the two
    # together produces a falsely-low MV. The user's repeated complaint about
    # Cam Ward Downtown Black Pandora /25 ($2,550 actual) being valued at
    # $750 (regular Downtown comps) and Brock Bowers Downtown Black Pandora
    # /25 ($5,000 actual) being valued at $569 (regular Downtown comps) is
    # this exact contamination class.
    #
    # Rule: when target's serial denominator is in the ultra_low (≤10) or
    # low (11-25) band, the comp's serial denominator must also be ultra_low
    # or low. Higher-band comps (mid_low 26-49, mid 50-99, or unserialized)
    # are rejected. We allow ultra_low ↔ low cross-comping because /10 and
    # /25 are close enough that their market values track within a tier
    # discount; the existing serial_lane_summary downstream applies the ratio.
    try:
        _target_serial_raw = _extract_serial_denominator(getattr(target, "raw_title", "") or "")
        _comp_serial_raw = _extract_serial_denominator(comp_title)
        _target_serial_band = _premium_serial_band(_target_serial_raw)
        _comp_serial_band = _premium_serial_band(_comp_serial_raw)
        _LOW_PRINT_BANDS = {"ultra_low", "low"}
        if _target_serial_band in _LOW_PRINT_BANDS and _comp_serial_band not in _LOW_PRINT_BANDS:
            try:
                print(
                    f"[LOW_SERIAL_TIER_GUARD] "
                    f"title={str(getattr(target, 'raw_title', '') or '')[:140]} "
                    f"comp_title={str(comp_title)[:140]} "
                    f"target_serial={_target_serial_raw} target_band={_target_serial_band} "
                    f"comp_serial={_comp_serial_raw} comp_band={_comp_serial_band or 'high_or_unserialized'} "
                    f"action=reject_high_serial_comp_for_low_target"
                )
            except Exception:
                pass
            return {
                "reject": True,
                "lane": "reject",
                "quality_mult": 0.0,
                "exactness_tier": "weak_fallback_lane",
                "reason": (
                    f"low_serial_target_high_serial_comp_mismatch:"
                    f"target_band={_target_serial_band}"
                    f"_comp_band={_comp_serial_band or 'high_or_unserialized'}"
                ),
                "target_signature": target_sig,
                "comp_signature": comp_sig,
                "support_signal_reason": "",
            }
    except Exception as _low_serial_exc:
        try:
            print(
                f"[LOW_SERIAL_TIER_GUARD] error_type={type(_low_serial_exc).__name__} "
                f"msg={str(_low_serial_exc)[:120]}"
            )
        except Exception:
            pass
    _support_signal_reason = _premium_support_signal_reason(target, comp_title)
    _exact_allow, _exact_reason = _exact_lane_assert(target, comp_title)
    print(
        f"[EXACT_LANE_ASSERT] title={str(target.raw_title or '')[:140]} comp_title={comp_title[:140]} "
        f"allow={1 if _exact_allow else 0} reason={_exact_reason}"
    )
    if _exact_allow:
        print(
            f"[PREMIUM_COMP_ADMIT] title={str(target.raw_title or '')[:140]} comp_title={comp_title[:140]} "
            f"admit_type=exact reason=exact_lane"
        )
        return {
            "reject": False,
            "lane": "exact_lane",
            "quality_mult": 1.0,
            "exactness_tier": "exact_strict",
            "reason": "",
            "target_signature": target_sig,
            "comp_signature": comp_sig,
            "support_signal_reason": "exact_lane",
        }
    _tt = _extract_card_identity_tokens(target)
    _ct = _extract_card_identity_tokens(comp_title)
    _same_broad_identity = bool(
        _tt.get("year")
        and _ct.get("year") == _tt.get("year")
        and (_tt.get("product_family") or _tt.get("primary_set"))
        and (_ct.get("product_family") or _ct.get("primary_set")) == (_tt.get("product_family") or _tt.get("primary_set"))
        and _tt.get("card_number") not in {"", "na"}
        and _ct.get("card_number") == _tt.get("card_number")
    )
    if _same_broad_identity and _exact_reason in {
        "role_mismatch", "subset_mismatch", "parallel_mismatch", "graded_lane_mismatch", "raw_vs_graded_mismatch", "missing_strong_identity", "card_number_only_not_enough"
    }:
        print(
            f"[EXACT_TO_SUPPORT_DEMOTE] title={str(target.raw_title or '')[:140]} comp_title={comp_title[:140]} reason={_exact_reason}"
        )
    if _same_near_comp_lane(target, comp_title):
        _support_allow, _support_assert_reason = _support_lane_assert(target, comp_title)
        print(
            f"[SUPPORT_LANE_ASSERT] title={str(target.raw_title or '')[:140]} comp_title={comp_title[:140]} "
            f"allow={1 if _support_allow else 0} reason={_support_assert_reason}"
        )
        if not _support_allow:
            print(
                f"[PREMIUM_COMP_REJECT] title={str(target.raw_title or '')[:140]} comp_title={comp_title[:140]} "
                f"reason={_support_assert_reason}"
            )
            return {
                "reject": True,
                "lane": "reject",
                "quality_mult": 0.0,
                "exactness_tier": "weak_fallback_lane",
                "reason": _support_assert_reason,
                "target_signature": target_sig,
                "comp_signature": comp_sig,
                "support_signal_reason": "",
            }
        if not _support_signal_reason:
            print(
                f"[PREMIUM_COMP_REJECT] title={str(target.raw_title or '')[:140]} comp_title={comp_title[:140]} "
                f"reason=base_family_only"
            )
            return {
                "reject": True,
                "lane": "reject",
                "quality_mult": 0.0,
                "exactness_tier": "weak_fallback_lane",
                "reason": "base_family_only",
                "target_signature": target_sig,
                "comp_signature": comp_sig,
                "support_signal_reason": "",
            }
        print(
            f"[PREMIUM_COMP_ADMIT] title={str(target.raw_title or '')[:140]} comp_title={comp_title[:140]} "
            f"admit_type=support reason={_support_signal_reason}"
        )
        return {
            "reject": False,
            "lane": "near_lane",
            "quality_mult": 0.78,
            "exactness_tier": "near_lane",
            "reason": _support_signal_reason,
            "target_signature": target_sig,
            "comp_signature": comp_sig,
            "support_signal_reason": _support_signal_reason,
        }
    if _same_rookie_color_support_lane(target, comp_title):
        _support_allow, _support_assert_reason = _support_lane_assert(target, comp_title)
        print(
            f"[SUPPORT_LANE_ASSERT] title={str(target.raw_title or '')[:140]} comp_title={comp_title[:140]} "
            f"allow={1 if _support_allow else 0} reason={_support_assert_reason}"
        )
        if not _support_allow:
            return {
                "reject": True,
                "lane": "reject",
                "quality_mult": 0.0,
                "exactness_tier": "weak_fallback_lane",
                "reason": _support_assert_reason,
                "target_signature": target_sig,
                "comp_signature": comp_sig,
                "support_signal_reason": "",
            }
        print(
            f"[PREMIUM_COMP_ADMIT] title={str(target.raw_title or '')[:140]} comp_title={comp_title[:140]} "
            f"admit_type=support reason=rookie_color_support"
        )
        _log_support_handoff_out(target, [{"title": comp_title}])
        return {
            "reject": False,
            "lane": "rookie_color_support",
            "quality_mult": 0.72,
            "exactness_tier": "rookie_color_support",
            "reason": "rookie_color_support",
            "target_signature": target_sig,
            "comp_signature": comp_sig,
            "support_signal_reason": "rookie_color_support",
        }
    if _same_scarcity_bucket_support_lane(target, comp_title):
        _support_allow, _support_assert_reason = _support_lane_assert(target, comp_title)
        print(
            f"[SUPPORT_LANE_ASSERT] title={str(target.raw_title or '')[:140]} comp_title={comp_title[:140]} "
            f"allow={1 if _support_allow else 0} reason={_support_assert_reason}"
        )
        if not _support_allow:
            return {
                "reject": True,
                "lane": "reject",
                "quality_mult": 0.0,
                "exactness_tier": "weak_fallback_lane",
                "reason": _support_assert_reason,
                "target_signature": target_sig,
                "comp_signature": comp_sig,
                "support_signal_reason": "",
            }
        _quality_mult = 0.64
        if target_class_family in {"patch_auto_family", "dual_patch_auto_family"}:
            _quality_mult = 0.82
        elif target_class_family == "subset_insert_family":
            _quality_mult = 0.80
        elif target_class_family == "memorabilia_family":
            _quality_mult = 0.74
        print(
            f"[PREMIUM_COMP_ADMIT] title={str(target.raw_title or '')[:140]} comp_title={comp_title[:140]} "
            f"admit_type=support reason=scarcity_bucket_support"
        )
        _log_support_handoff_out(target, [{"title": comp_title}])
        return {
            "reject": False,
            "lane": "scarcity_bucket_support",
            "quality_mult": _quality_mult,
            "exactness_tier": "scarcity_bucket_support",
            "reason": "scarcity_bucket_support",
            "target_signature": target_sig,
            "comp_signature": comp_sig,
            "support_signal_reason": "scarcity_bucket_support",
        }
    if _same_subset_ecosystem_support_lane(target, comp_title):
        _support_allow, _support_assert_reason = _support_lane_assert(target, comp_title)
        print(
            f"[SUPPORT_LANE_ASSERT] title={str(target.raw_title or '')[:140]} comp_title={comp_title[:140]} "
            f"allow={1 if _support_allow else 0} reason={_support_assert_reason}"
        )
        if not _support_allow:
            return {
                "reject": True,
                "lane": "reject",
                "quality_mult": 0.0,
                "exactness_tier": "weak_fallback_lane",
                "reason": _support_assert_reason,
                "target_signature": target_sig,
                "comp_signature": comp_sig,
                "support_signal_reason": "",
            }
        print(
            f"[PREMIUM_COMP_ADMIT] title={str(target.raw_title or '')[:140]} comp_title={comp_title[:140]} "
            f"admit_type=support reason=subset_ecosystem_support"
        )
        _log_support_handoff_out(target, [{"title": comp_title}])
        return {
            "reject": False,
            "lane": "subset_ecosystem_support",
            "quality_mult": 0.68,
            "exactness_tier": "subset_ecosystem_support",
            "reason": "subset_ecosystem_support",
            "target_signature": target_sig,
            "comp_signature": comp_sig,
            "support_signal_reason": "subset_ecosystem_support",
        }
    _support_allow, _support_assert_reason = _support_lane_assert(target, comp_title)
    if _support_allow:
        _tt = _extract_card_identity_tokens(target)
        _ct = _extract_card_identity_tokens(comp_title)
        _target_parallel = _identity_parallel_family(_tt)
        _comp_parallel = _identity_parallel_family(_ct)
        _target_serial = str(_tt.get("serial_denominator") or "").strip().lower()
        _comp_serial = str(_ct.get("serial_denominator") or "").strip().lower()
        _support_lane = "subset_ecosystem_support"
        _quality_mult = 0.68
        if (
            (_target_parallel and _target_parallel not in {"", "base", "raw"} and _comp_parallel == _target_parallel)
            or (_target_serial and _comp_serial and (
                _comp_serial == _target_serial
                or (
                    _serial_support_bucket(_target_serial)
                    and _serial_support_bucket(_target_serial) == _serial_support_bucket(_comp_serial)
                )
            ))
        ):
            _support_lane = "scarcity_bucket_support"
            _quality_mult = 0.64
        print(
            f"[PREMIUM_COMP_ADMIT] title={str(target.raw_title or '')[:140]} comp_title={comp_title[:140]} "
            f"admit_type=support reason=generic_support_identity"
        )
        _log_support_handoff_out(target, [{"title": comp_title}])
        return {
            "reject": False,
            "lane": _support_lane,
            "quality_mult": _quality_mult,
            "exactness_tier": _support_lane,
            "reason": _support_assert_reason or "generic_support_identity",
            "target_signature": target_sig,
            "comp_signature": comp_sig,
            "support_signal_reason": _support_assert_reason or "generic_support_identity",
        }
    return {
        "reject": True,
        "lane": "reject",
        "quality_mult": 0.0,
        "exactness_tier": "weak_fallback_lane",
        "reason": "weak_card_identity_match",
        "target_signature": target_sig,
        "comp_signature": comp_sig,
        "support_signal_reason": "",
    }


MAJOR_SET_SLUGS: FrozenSet[str] = frozenset(
    s.replace(" ", "") for s in SET_KEYWORDS
) | frozenset({"toppschrome"})


def is_bad_comp_match(
    comp_title: str,
    target: CardListingProfile,
    *,
    target_variant: Optional[CardVariantClassification] = None,
    allow_psa_adjacent: bool = False,
) -> Tuple[bool, str]:
    """
    Hard rejection for comps that would pollute the pool (wrong product, lots, etc.).
    Returns (reject, reason_code).
    """
    if not comp_title or not str(comp_title).strip():
        return True, "empty_title"
    cl = _norm(comp_title)
    lane_gate = _apply_comp_lane_penalties(target, comp_title)
    lane_name = str(lane_gate.get("lane") or "")
    _premium_bucket_meta = _premium_same_family_bucket_meta(target, comp_title)

    def _lane_supports_reason(reason_code: str) -> bool:
        if lane_name == "scarcity_bucket_support" and reason_code in {"serial_mismatch", "numbered_print_mismatch"}:
            return True
        if lane_name == "rookie_color_support" and reason_code == "wrong_card_number":
            return True
        if lane_name == "subset_ecosystem_support" and reason_code == "wrong_set":
            return True
        return False

    def _reject(reason_code: str) -> Tuple[bool, str]:
        print(
            f"[PREMIUM_COMP_REJECT] title={str(target.raw_title or '')[:140]} comp_title={comp_title[:140]} reason={reason_code}"
        )
        print(f"[COMP_DROP] title={comp_title[:140]} reason={reason_code}")
        return True, reason_code

    _promo_junk_reason = _promo_junk_identity_reason(target, comp_title)
    if _promo_junk_reason:
        return _reject(_promo_junk_reason)

    if select_exact_comp_archetype(target, emit_log=False):
        _topps_lane_reason = str(lane_gate.get("reason") or "").strip()
        if _topps_lane_reason in {
            "blocked_parallel",
            "blocked_parallel_family",
            "blocked_update",
            "blocked_grade",
            "blocked_card_number",
            "blocked_serial",
            "blocked_subset",
        }:
            return _reject(_topps_lane_reason)

    if target_has_identifiable_player(target):
        pm, _ = player_match_score(target, comp_title)
        if pm < 0.52:
            return _reject("wrong_player")

    _subject_auto = subject_has_auto_identity(target.raw_title)
    _comp_auto = comp_has_auto_identity(comp_title)
    print(
        f"[AUTO_IDENTITY] title={str(target.raw_title or '')[:140]} subject_auto={1 if _subject_auto else 0} "
        f"comp_title={comp_title[:140]} comp_auto={1 if _comp_auto else 0}"
    )
    if _subject_auto != _comp_auto:
        print(
            f"[AUTO_MATCH_ASSERT] title={str(target.raw_title or '')[:140]} comp_title={comp_title[:140]} "
            f"allow=0 reason=auto_mismatch"
        )
        return _reject("auto_mismatch")
    print(
        f"[AUTO_MATCH_ASSERT] title={str(target.raw_title or '')[:140]} comp_title={comp_title[:140]} "
        f"allow={1 if _subject_auto and _comp_auto else 0} reason={'auto_match' if _subject_auto and _comp_auto else 'subject_not_auto'}"
    )

    if _listing_implies_lot(cl):
        return _reject("lot_or_bundle")

    if not target.is_memorabilia and _listing_implies_mem(cl):
        return _reject("memorabilia_mismatch")

    if not target.graded_hint and _graded_tokens(cl):
        return _reject("graded_vs_raw_target")

    comp_sets = _extract_sets(comp_title)
    tset = set(target.set_tokens) if target.set_tokens else set()
    if tset:
        comp_major = comp_sets & MAJOR_SET_SLUGS
        if comp_major and not (comp_sets & tset) and not _lane_supports_reason("wrong_set"):
            return _reject("wrong_set")

    if target.brands:
        comp_brands = set(_extract_brands(comp_title))
        target_brands = set(target.brands)
        if comp_brands and target_brands and not (comp_brands & target_brands):
            return _reject("wrong_brand")

    tc = target.card_number
    cc = _extract_card_number(comp_title)
    if tc and cc and tc != cc and not _lane_supports_reason("wrong_card_number"):
        return _reject("wrong_card_number")

    _class_ok, _class_reason = _premium_card_class_match(target, comp_title, lane_name=lane_name)
    if not _class_ok and not _lane_supports_reason(_class_reason):
        return _reject(_class_reason or "wrong_card_class")

    target_subset = _normalize_support_subset_name(target.subset_family)
    if target_subset and _is_noisy_subset_identity(target_subset, raw_title=target.raw_title, card_number=target.card_number):
        print(
            f"[WRONG_SUBSET_GUARD] title={str(target.raw_title or '')[:140]} dropped_subset={target_subset[:40]} "
            f"reason=noisy_subset_identity"
        )
        target_subset = ""
    if target_subset:
        _comp_profile = parse_listing_profile(comp_title)
        comp_subset = _normalize_support_subset_name(_comp_profile.subset_family)
        if comp_subset and _is_noisy_subset_identity(comp_subset, raw_title=comp_title, card_number=_comp_profile.card_number):
            print(
                f"[WRONG_SUBSET_GUARD] title={comp_title[:140]} dropped_subset={comp_subset[:40]} "
                f"reason=noisy_subset_identity"
            )
            comp_subset = ""
        if comp_subset and comp_subset != target_subset:
            _parallel_recovery_ok, _parallel_recovery_reason = _premium_parallel_recovery_allowed(target, comp_title)
            if not bool(_premium_bucket_meta.get("allowed")) and not _parallel_recovery_ok:
                return _reject("subset_mismatch")
            print(f"[COMP_KEEP_NEAR] title={comp_title[:140]} reason={_parallel_recovery_reason if _parallel_recovery_ok else 'same_family_bucket'}")
        if not comp_subset:
            _parallel_recovery_ok, _parallel_recovery_reason = _premium_parallel_recovery_allowed(target, comp_title)
            if not bool(_premium_bucket_meta.get("allowed")) and not _parallel_recovery_ok:
                return _reject("missing_subset_family")
            print(f"[COMP_KEEP_NEAR] title={comp_title[:140]} reason={_parallel_recovery_reason if _parallel_recovery_ok else 'same_family_bucket'}")

    tsn = _extract_serial_denominator(target.raw_title)
    csn = _extract_serial_denominator(comp_title)
    if tsn and csn and tsn != csn and not _lane_supports_reason("serial_mismatch"):
        _parallel_recovery_ok, _parallel_recovery_reason = _premium_parallel_recovery_allowed(target, comp_title)
        if not _premium_serial_band_allowed(target, comp_title) and not _parallel_recovery_ok:
            return _reject("serial_mismatch")
        print(f"[COMP_KEEP_NEAR] title={comp_title[:140]} reason={_parallel_recovery_reason if _parallel_recovery_ok else 'same_family_bucket'}")

    tgk = grade_bucket_key(target.raw_title)
    cgk = grade_bucket_key(comp_title)
    if _grade_keys_strict_mismatch(tgk, cgk):
        if allow_psa_adjacent and _psa_one_step_adjacent(tgk, cgk):
            pass
        else:
            return _reject("grade_mismatch")

    t_cls = target_variant if target_variant is not None else classify_card_variant(target.raw_title)
    c_cls = classify_card_variant(comp_title)
    v_ok, v_reason = _variants_compatible(t_cls, c_cls)
    if not v_ok and not _lane_supports_reason(str(v_reason or "variant_mismatch")):
        return _reject(v_reason or "variant_mismatch")

    if ("silver" in (target.parallel_tokens or ()) or (target.parallel_phrase and "silver" in target.parallel_phrase)) and (
        "prizm" in tset or "prizm" in comp_sets
    ):
        if re.search(r"\bgold\b", cl) and not re.search(r"\bsilver\b", cl):
            _parallel_recovery_ok, _ = _premium_parallel_recovery_allowed(target, comp_title)
            if not _parallel_recovery_ok:
                return _reject("wrong_parallel")

    if not str(lane_gate.get("reason") or "").strip():
        return _reject("missing_verified_overlap")
    if lane_gate.get("reject"):
        return _reject(str(lane_gate.get("reason") or "weak_card_identity_match"))

    return False, ""


def comp_match_quality(comp_title: str, target: CardListingProfile) -> float:
    """
    Soft score 0..1 for weighting accepted comps (weighted median weights).
    """
    cl = _norm(comp_title)
    score = 0.0
    lane_gate = _apply_comp_lane_penalties(target, comp_title)
    if lane_gate.get("reject"):
        return 0.0
    _class_ok, _class_reason = _premium_card_class_match(target, comp_title, lane_name=str(lane_gate.get("lane") or ""))
    if not _class_ok:
        return 0.0

    if target.year and target.year in comp_title:
        score += 0.22

    if target.primary_set:
        pat = target.primary_set.replace("toppschrome", r"topps\s*chrome")
        if re.search(rf"\b{pat}\b", cl):
            score += 0.22

    if target.card_number and re.search(
        rf"#\s*{re.escape(target.card_number)}\b", comp_title, flags=re.IGNORECASE
    ):
        score += 0.20
    elif target.card_number:
        score += 0.02

    if target.parallel_phrase and target.parallel_phrase in cl:
        score += 0.18
    elif target.parallel_tokens:
        hits = sum(1 for t in target.parallel_tokens if re.search(rf"\b{re.escape(t)}\b", cl))
        if hits:
            score += min(0.14, 0.05 * hits)
        else:
            score -= 0.04

    if target.player_tokens:
        tt = {normalize_player_name(t) for t in target.player_tokens if t}
        _, cpt = _extract_player_guess(comp_title)
        ctoks = {normalize_player_name(t) for t in cpt if t}
        inter = len(tt & ctoks)
        if inter:
            score += min(0.22, 0.07 * inter)
        elif target_has_identifiable_player(target):
            score *= 0.22
        elif len(target.player_tokens) >= 2:
            score *= 0.45

    if target.is_rookie and re.search(r"\b(rc|rookie)\b", cl):
        score += 0.08
    elif target.is_rookie:
        score -= 0.05
    elif re.search(r"\b(rc|rookie)\b", cl):
        score -= 0.04

    if target.brands:
        brand_hit = False
        for b in target.brands:
            if _norm(b) in cl:
                score += 0.05
                brand_hit = True
                break
        if not brand_hit:
            score -= 0.08

    tsn = _extract_serial_denominator(target.raw_title)
    csn = _extract_serial_denominator(comp_title)
    if tsn and csn and tsn == csn:
        score += 0.10
    elif tsn and not csn:
        score -= 0.08

    vm_level, _ = variant_match_assessment(target, comp_title)
    if vm_level == "exact_variant_match":
        score += 0.12
    elif vm_level == "same_variant_family":
        score += 0.09
    elif vm_level == "weak_variant_match":
        score += 0.02
    else:
        score -= 0.12

    if lane_gate.get("lane") == "exact_lane":
        score += 0.18
    elif lane_gate.get("lane") == "near_lane":
        score += 0.03
    elif lane_gate.get("lane") in {"subset_ecosystem_support", "scarcity_bucket_support", "rookie_color_support"}:
        score += 0.05
    if _class_reason in {"patch_auto_family", "dual_patch_auto_family", "memorabilia_family", "subset_insert_family"}:
        score += 0.06
    score *= float(lane_gate.get("quality_mult") or 1.0)

    return max(0.0, min(1.0, score))
