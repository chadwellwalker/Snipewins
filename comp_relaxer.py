"""
comp_relaxer.py — Relaxed-query comping wrapper around valuation_engine.

User asked (May 2026): "the machine needs to find similar cards instead of
multiplying numbers." This module makes that happen.

When the valuation engine produces no exact comps for a brand-new release
(e.g. 2026 Topps Chrome Black Paul Skenes/Bubba Chandler Auto Dual Red /5),
this wrapper progressively drops constraints from the search query until
something hits. Each level is labeled so the dashboard can show *what*
similar cards we used (e.g., "based on 3 Paul Skenes Topps Chrome Black
auto comps from 2025 — same product, looser parallel").

Relaxation ladder (built from a parsed listing):

    L0: exact card                  Paul Skenes Bubba Chandler 2026 Topps Chrome Black Dual Auto Red /5
    L1: drop co-star                Paul Skenes 2026 Topps Chrome Black Dual Auto Red /5
    L2: drop year                   Paul Skenes Topps Chrome Black Dual Auto Red /5
    L3: drop dual/triple modifier   Paul Skenes Topps Chrome Black Auto Red /5
    L4: drop /N numbering           Paul Skenes Topps Chrome Black Auto Red
    L5: drop color word             Paul Skenes Topps Chrome Black Auto
    L6: drop auto                   Paul Skenes Topps Chrome Black
    L7: drop product specifier      Paul Skenes Topps Chrome
    [stop]

We never go broader than L7 — at that point the comps are too diluted
to be a useful signal and would mislead the user.

Caller pattern:

    from comp_relaxer import value_with_relaxation
    result = value_with_relaxation(title, item_id, item_url, target_row)
    # result is a HybridValuation with extra `relaxation_level` / `relaxation_query`
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# ── Regex helpers for parsing card features out of a title ────────────────
_YEAR_RE       = re.compile(r"\b(19|20)\d{2}\b")
_SERIAL_RE     = re.compile(r"#?\s*\d{1,3}\s*/\s*\d{1,4}\b|/\s*\d{1,4}\b", re.IGNORECASE)
_DUAL_RE       = re.compile(r"\b(dual|double|triple|quad)\b", re.IGNORECASE)
_AUTO_RE       = re.compile(r"\b(auto|autograph|autographed|signed)\b", re.IGNORECASE)
_GRADE_RE      = re.compile(r"\b(psa|bgs|sgc|cgc)\s?\d+(?:\.\d)?\b", re.IGNORECASE)
_GEM_MINT_RE   = re.compile(r"\bgem\s?(mt|mint)\b", re.IGNORECASE)
# Color words that often qualify a parallel (Red, Blue, Gold etc.).
# When relaxing we drop these one at a time. Order matters — match longer first.
_COLOR_WORDS = (
    "blue ice", "red ice", "green ice", "orange ice", "purple power",
    "neon green pulsar", "purple pulsar", "red sparkle", "pink wave",
    "blue wave", "green wave", "red wave", "purple wave", "orange wave",
    "gold wave", "silver wave",
    "snake skin", "snakeskin", "dragon scale", "tie dye", "tie-dye",
    "shock", "lazer", "hyper", "disco",
    "red", "blue", "green", "gold", "orange", "purple", "pink", "silver", "black",
    "white", "yellow", "neon",
)
# Common product family substrings to detect.
_PRODUCT_FAMILIES = (
    "topps chrome black", "topps cosmic chrome", "topps chrome sapphire",
    "topps chrome", "topps finest", "topps", "bowman chrome",
    "bowman draft", "bowman", "national treasures", "immaculate",
    "flawless", "spectra", "absolute", "panini prizm", "prizm",
    "donruss optic", "optic", "mosaic", "select", "donruss",
    "contenders", "score", "phoenix", "rookies and stars", "rookies & stars",
)


@dataclass
class ParsedCard:
    """Lightweight parse of a card title into the dimensions we relax along."""
    title_raw:        str
    title_lc:         str
    player_tokens:    List[str]     # Best guess at player name tokens
    co_star_tokens:   List[str]     # "/" or "&" separated additional player
    year:             Optional[str] # e.g. "2026"
    product:          Optional[str] # e.g. "Topps Chrome Black"
    serial_denom:     Optional[int] # /N number
    has_dual:         bool
    has_auto:         bool
    color_words:      List[str]     # In order they appear
    grade_token:      Optional[str] # e.g. "PSA 10"


def parse_card_title(title: str, player_hint: Optional[str] = None) -> ParsedCard:
    """Parse a card title into the dimensions used by the relaxation ladder.

    player_hint: optional pre-resolved player name from the row (e.g. from
    chase_rules.player_tier lookup); helps when the title has co-stars or
    unusual formatting.
    """
    title_lc = title.lower()

    # Year
    year_match = _YEAR_RE.search(title)
    year = year_match.group(0) if year_match else None

    # Product family
    product = None
    for p in _PRODUCT_FAMILIES:
        if p in title_lc:
            product = p
            break

    # Serial denominator
    serial_denom: Optional[int] = None
    serial_match = _SERIAL_RE.search(title_lc)
    if serial_match:
        chunk = serial_match.group(0)
        denom = re.search(r"/\s*(\d{1,4})", chunk)
        if denom:
            try:
                serial_denom = int(denom.group(1))
            except ValueError:
                pass

    # Dual / auto flags
    has_dual = bool(_DUAL_RE.search(title_lc))
    has_auto = bool(_AUTO_RE.search(title_lc))

    # Color words (preserve order found in title)
    color_words: List[str] = []
    for cw in _COLOR_WORDS:
        if cw in title_lc:
            color_words.append(cw)
    # Dedupe substrings — if both "blue ice" and "blue" matched, keep the longer
    color_words = _dedupe_substrings(color_words)

    # Grade
    grade_match = _GRADE_RE.search(title)
    grade_token = grade_match.group(0) if grade_match else None

    # Player + co-star — naive heuristic: split on slash or "and" if the title
    # contains them, else use the player_hint.
    co_star_tokens: List[str] = []
    if "/" in title and player_hint:
        # "Paul Skenes/Bubba Chandler" — split off the co-star
        parts = re.split(r"\s*/\s*", title)
        for p in parts[1:]:
            # Stop at first non-name token (year, product etc.)
            tok = p.split()[0:3]
            co_star_tokens.append(" ".join(tok))
    player_tokens = (player_hint or "").split() if player_hint else []

    return ParsedCard(
        title_raw=title,
        title_lc=title_lc,
        player_tokens=player_tokens,
        co_star_tokens=co_star_tokens,
        year=year,
        product=product,
        serial_denom=serial_denom,
        has_dual=has_dual,
        has_auto=has_auto,
        color_words=color_words,
        grade_token=grade_token,
    )


def _dedupe_substrings(items: List[str]) -> List[str]:
    """Keep only items that aren't substrings of another item in the list.
    Sorts by length desc first so longer matches survive."""
    sorted_items = sorted(items, key=len, reverse=True)
    kept: List[str] = []
    for it in sorted_items:
        if not any(it != other and it in other for other in kept):
            kept.append(it)
    return kept


# ── Query builders for each relaxation level ──────────────────────────────

def build_relaxation_queries(parsed: ParsedCard) -> List[Dict[str, Any]]:
    """Build the relaxation ladder as a list of (level, label, query) dicts.

    Returns ordered from MOST SPECIFIC to LEAST SPECIFIC. Caller tries each
    in order and stops at the first one that produces a confident MV.
    """
    levels: List[Dict[str, Any]] = []

    # Level 0 — exact (use the raw title as the query)
    levels.append({
        "level": 0,
        "label": "exact_title",
        "query": parsed.title_raw,
        "description": "the exact card you're looking at",
    })

    # Level 1 — drop co-star (for dual/triple cards)
    if parsed.co_star_tokens and parsed.player_tokens:
        l1_query = _compose(
            parsed.player_tokens,
            [parsed.year] if parsed.year else [],
            [parsed.product] if parsed.product else [],
            ["dual"] if parsed.has_dual else [],
            ["auto"] if parsed.has_auto else [],
            parsed.color_words,
            [f"/{parsed.serial_denom}"] if parsed.serial_denom else [],
            [parsed.grade_token] if parsed.grade_token else [],
        )
        levels.append({
            "level": 1,
            "label": "drop_co_star",
            "query": l1_query,
            "description": f"same {parsed.product or 'product'}, your player only (drop co-star)",
        })

    # Level 2 — drop year
    l2_query = _compose(
        parsed.player_tokens,
        [parsed.product] if parsed.product else [],
        ["dual"] if parsed.has_dual else [],
        ["auto"] if parsed.has_auto else [],
        parsed.color_words,
        [f"/{parsed.serial_denom}"] if parsed.serial_denom else [],
        [parsed.grade_token] if parsed.grade_token else [],
    )
    if l2_query:
        levels.append({
            "level": 2,
            "label": "drop_year",
            "query": l2_query,
            "description": "any year, same product + parallel",
        })

    # Level 3 — drop dual/triple modifier
    if parsed.has_dual:
        l3_query = _compose(
            parsed.player_tokens,
            [parsed.product] if parsed.product else [],
            ["auto"] if parsed.has_auto else [],
            parsed.color_words,
            [f"/{parsed.serial_denom}"] if parsed.serial_denom else [],
            [parsed.grade_token] if parsed.grade_token else [],
        )
        levels.append({
            "level": 3,
            "label": "drop_dual",
            "query": l3_query,
            "description": "same product + parallel + auto (single, not dual)",
        })

    # Level 4 — drop /N numbering
    if parsed.serial_denom:
        l4_query = _compose(
            parsed.player_tokens,
            [parsed.product] if parsed.product else [],
            ["auto"] if parsed.has_auto else [],
            parsed.color_words,
            [parsed.grade_token] if parsed.grade_token else [],
        )
        levels.append({
            "level": 4,
            "label": "drop_serial",
            "query": l4_query,
            "description": "any serial, same product + color + auto",
        })

    # Level 5 — drop color word(s)
    if parsed.color_words:
        l5_query = _compose(
            parsed.player_tokens,
            [parsed.product] if parsed.product else [],
            ["auto"] if parsed.has_auto else [],
            [parsed.grade_token] if parsed.grade_token else [],
        )
        levels.append({
            "level": 5,
            "label": "drop_color",
            "query": l5_query,
            "description": "any color/parallel, same product + auto",
        })

    # Level 6 — drop auto
    if parsed.has_auto:
        l6_query = _compose(
            parsed.player_tokens,
            [parsed.product] if parsed.product else [],
            [parsed.grade_token] if parsed.grade_token else [],
        )
        levels.append({
            "level": 6,
            "label": "drop_auto",
            "query": l6_query,
            "description": "same product, any card type",
        })

    # Level 7 — drop product specifier down to a broader family
    # e.g. "Topps Chrome Black" → "Topps Chrome"
    if parsed.product and " " in parsed.product:
        broader = parsed.product.rsplit(" ", 1)[0]
        l7_query = _compose(
            parsed.player_tokens,
            [broader],
            [parsed.grade_token] if parsed.grade_token else [],
        )
        levels.append({
            "level": 7,
            "label": "drop_product_specifier",
            "query": l7_query,
            "description": f"any {broader} card of the player",
        })

    return levels


def _compose(*token_groups: List[Any]) -> str:
    """Join non-empty tokens with spaces into a clean query string."""
    tokens: List[str] = []
    for group in token_groups:
        for t in group:
            if t is None:
                continue
            s = str(t).strip()
            if s and s not in tokens:
                tokens.append(s)
    return " ".join(tokens)


# ── Public valuation API ──────────────────────────────────────────────────

def value_with_relaxation(
    title: str,
    item_id: str = "",
    item_url: str = "",
    target_row: Optional[Dict[str, Any]] = None,
    player_hint: Optional[str] = None,
    min_accepted_comps: int = 1,
) -> Optional[Dict[str, Any]]:
    """Run the valuation engine through the relaxation ladder. Returns the
    first level where the engine produced an acceptable result, or None if
    even Level 7 came up empty.

    Returns a dict:
        {
            "level":               0..7,
            "label":               "exact_title" | "drop_co_star" | ...
            "description":         human-readable
            "query":               the actual query used
            "mv":                  float (the engine's estimated_value)
            "comp_count":          int
            "accepted_comp_count": int
            "confidence":          str (engine's confidence label)
        }

    min_accepted_comps: minimum accepted_comp_count to consider a level
    "successful." For exact match (L0) we accept 1+. For relaxed levels we
    might want to require more (handled by caller via threshold passed in).
    """
    if not title:
        return None

    parsed = parse_card_title(title, player_hint=player_hint)
    levels = build_relaxation_queries(parsed)
    if not levels:
        return None

    # Lazy import to keep this module light when not used.
    try:
        import valuation_engine as ve
    except Exception as exc:
        print(f"[comp_relaxer] valuation_engine import failed: {exc}")
        return None

    for level_info in levels:
        try:
            result = ve.run_hybrid_valuation(
                listing_title=title,
                item_id=item_id,
                item_url=item_url,
                search_query=level_info["query"],
                target_listing_item=target_row,
            )
        except Exception as exc:
            print(f"[comp_relaxer] L{level_info['level']} engine error: {exc}")
            continue

        # The engine returns a HybridValuation. Extract the fields we care about.
        accepted_n = int(getattr(result, "accepted_comp_count", 0) or 0)
        comp_n     = int(getattr(result, "comp_count", 0) or 0)
        value      = getattr(result, "value", None)

        # Threshold scales with relaxation level — exact match is fine with 1
        # comp, but at level 4+ we want 2+ to consider it a real signal.
        required = max(min_accepted_comps, 1 if level_info["level"] <= 2 else 2)
        if accepted_n < required or value is None:
            continue

        # TRANSPARENCY-2026-05-12: pass through the engine's accepted-comp
        # snapshot so the dashboard can render which similar cards actually
        # produced this estimate. Without this the user gets a number with
        # no receipts — the user's mandate: "if the machine used a similar
        # card, show it."
        _comps_json = ""
        try:
            _comps_json = str(getattr(result, "debug_accepted_comps_json", "") or "")
        except Exception:
            _comps_json = ""
        return {
            "level":               level_info["level"],
            "label":               level_info["label"],
            "description":         level_info["description"],
            "query":               level_info["query"],
            "mv":                  float(value),
            "comp_count":          comp_n,
            "accepted_comp_count": accepted_n,
            "confidence":          str(getattr(result, "confidence", "") or ""),
            "comps_json":          _comps_json,
        }

    return None  # Even the broadest query found nothing
