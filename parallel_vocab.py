"""
Set-specific parallel / phrasing hints for comp matching (config-style).

Feeds comp_query.normalize_parallel_bucket only; does not globally rewrite titles.
Keys match comp_query primary_set slugs (prizm, optic, mosaic, select, donruss, ...).

VARIANT_FAMILIES_BY_SET groups wording variants (e.g. Select Zebra vs Zebra Shock Prizm)
under one canonical family id for acceptance and MV eligibility.

SPORT_SUPPRESSED_PARALLELS marks (sport, parallel_family) combos where the
"premium" parallel is actually base-level pricing. Example: Silver Prizm has
real chase value in football (one per pack hobby), but in baseball it's
essentially the base parallel and shouldn't qualify a row as premium.
"""
from __future__ import annotations

import re
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

# (sport_upper, parallel_family) → reason. is_parallel_suppressed_for_sport()
# returns the reason string when a combo is on the blocklist.
SPORT_SUPPRESSED_PARALLELS: Dict[Tuple[str, str], str] = {
    # Silver Prizm baseball: there's no real silver-prizm chase in MLB Prizm.
    # The "silver prizm" wording shows up on near-base inserts (Future Tools,
    # Color Blast, etc.). Football and basketball Silver Prizm are real
    # chase parallels — keep those.
    ("MLB", "silver_prizm"):  "silver_prizm_not_premium_in_baseball",
    ("MLB", "silver"):        "silver_not_premium_in_baseball",
    # Mosaic silver: same dynamic — real in basketball/football, base in MLB.
    ("MLB", "mosaic_silver"): "mosaic_silver_not_premium_in_baseball",
}

# Title-token suppression: when the engine's parallel_family field is empty
# (common on freshly-fetched 24h rows) we still need a way to drop rows whose
# titles indicate a sport-mismatched "premium" parallel. Each entry is a
# (sport_upper, regex) pair; if the title matches AND the row's product is
# the listed product family, the row is suppressed.
#
# Note: regex must be lowercase-anchored. Titles are lowercased before match.
SPORT_SUPPRESSED_TITLE_PATTERNS: Dict[str, Tuple[Tuple[str, str, str], ...]] = {
    "MLB": (
        # (regex, product_family_match (substring, lowercased), reason)
        (r"\b(true\s+)?silver\s+prizm\b", "prizm",  "silver_prizm_not_premium_in_baseball"),
        (r"\bprizm\s+silver\b",            "prizm",  "silver_prizm_not_premium_in_baseball"),
        (r"\bmosaic\s+silver\b",           "mosaic", "mosaic_silver_not_premium_in_baseball"),
        (r"\bsilver\s+mosaic\b",           "mosaic", "mosaic_silver_not_premium_in_baseball"),
    ),
}


def is_parallel_suppressed_for_sport(
    sport: Optional[str],
    parallel_family: Optional[str],
) -> Optional[str]:
    """Return a string reason when this (sport, parallel) combo should be
    dropped (e.g. baseball + silver_prizm). Return None when the combo
    is fine. Both inputs are normalized (uppercased sport, lowercased
    parallel) before lookup."""
    s = (sport or "").strip().upper()
    p = (parallel_family or "").strip().lower()
    if not s or not p:
        return None
    return SPORT_SUPPRESSED_PARALLELS.get((s, p))


def is_title_sport_suppressed(
    sport: Optional[str],
    title: Optional[str],
    product_family: Optional[str] = None,
) -> Optional[str]:
    """Title-based fallback for when parallel_family isn't tagged on the row.
    Reads the title for sport-mismatched parallel keywords. Returns the
    suppression reason or None."""
    s = (sport or "").strip().upper()
    if not s or not title:
        return None
    rules = SPORT_SUPPRESSED_TITLE_PATTERNS.get(s)
    if not rules:
        return None
    title_lc = (title or "").lower()
    product_lc = (product_family or "").lower()
    for pattern, product_match, reason in rules:
        if not re.search(pattern, title_lc):
            continue
        # product_match is a substring requirement — only suppress when the
        # row is in that product family. Without it we'd over-cut (e.g.
        # rejecting "silver prizm" mentions in unrelated card titles).
        if product_match and product_match not in product_lc and product_match not in title_lc:
            continue
        return reason
    return None

# (internal_tag, substring phrases to find in lowercased normalized title)
PARALLEL_PHRASES_BY_SET: Dict[str, Tuple[Tuple[str, Tuple[str, ...]], ...]] = {
    "prizm": (
        ("silver_prizm", ("true silver prizm", "silver prizm", "prizm silver", "true silver")),
    ),
    "optic": (
        (
            "holo",
            (
                "rated rookie holo",
                "rr holo",
                "donruss optic holo",
                "optic holo",
                "optic rated rookie holo",
                "holo prizm",
                "prizm holo",
                "holo optic",
            ),
        ),
    ),
    "mosaic": (
        ("mosaic_silver", ("mosaic silver", "silver mosaic")),
        ("reactive", ("reactive blue", "reactive red", "reactive green", "reactive orange")),
    ),
    "select": (
        ("select_silver", ("select silver", "silver select")),
        ("die_cut", ("die cut", "die-cut")),
    ),
    "donruss": (
        ("donruss_holo", ("donruss holo", "donruss optic holo")),
        ("press_proof", ("press proof",)),
    ),
    "chronicles": (
        ("chronicles_prizm", ("chronicles prizm",)),
    ),
    "contenders": (
        ("contenders_optic", ("contenders optic",)),
    ),
    "revolution": (
        ("revolution_galactic", ("galactic",)),
    ),
}

# (family_id, phrases longest-first). Phrases are matched as substrings in normalized title.
# family_id becomes normalize_parallel_bucket output when matched (e.g. select_zebra).
VARIANT_FAMILIES_BY_SET: Dict[str, Tuple[Tuple[str, Tuple[str, ...]], ...]] = {
    "select": (
        (
            "select_zebra",
            (
                "zebra shock prizm",
                "zebra shock",
                "zebra prizm",
                "zebra",
            ),
        ),
    ),
    "prizm": (
        (
            "silver_prizm",
            (
                "true silver prizm",
                "true silver",
                "silver prizm",
                "prizm silver",
            ),
        ),
    ),
    "optic": (
        (
            "holo",
            (
                "rated rookie holo",
                "donruss optic holo",
                "optic rated rookie holo",
                "optic holo",
                "rr holo",
                "holo prizm",
                "prizm holo",
            ),
        ),
    ),
    "mosaic": (
        (
            "mosaic_reactive",
            (
                "reactive blue",
                "reactive red",
                "reactive green",
                "reactive orange",
            ),
        ),
        (
            "mosaic_silver",
            (
                "mosaic silver",
                "silver mosaic",
            ),
        ),
    ),
}


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def vocab_parallel_tags(primary_set: Optional[str], title_lower: str) -> FrozenSet[str]:
    """Tags inferred from set-specific multi-word phrases (substring match)."""
    if not primary_set:
        return frozenset()
    cfg = PARALLEL_PHRASES_BY_SET.get(primary_set)
    if not cfg:
        return frozenset()
    lt = _norm(title_lower)
    out: Set[str] = set()
    for _tag, phrases in cfg:
        for ph in phrases:
            p = ph.lower().strip()
            if len(p) >= 4 and p in lt:
                out.add(_tag)
    return frozenset(out)


def vocab_bucket_override(primary_set: Optional[str], title_lower: str) -> Optional[str]:
    """Optional strong bucket name aligned with normalize_parallel_bucket outputs."""
    tags = vocab_parallel_tags(primary_set, title_lower)
    lt = _norm(title_lower)
    if "silver_prizm" in tags and (primary_set == "prizm" or "prizm" in lt):
        return "silver_prizm"
    if "holo" in tags or ("donruss_holo" in tags and "optic" in lt):
        if primary_set == "optic" or "optic" in lt:
            return "holo"
    if "mosaic_silver" in tags and primary_set == "mosaic":
        return "mosaic_silver"
    if "select_silver" in tags and primary_set == "select":
        return "select_silver"
    return None


def infer_variant_family_id(primary_set: Optional[str], title: str) -> str:
    """
    Canonical variant family for set + title (e.g. select_zebra).
    Empty string if no configured family matches.
    """
    ps = (primary_set or "").strip().lower()
    if not ps or not title:
        return ""
    cfg = VARIANT_FAMILIES_BY_SET.get(ps)
    if not cfg:
        return ""
    lt = _norm(title)
    for family_id, phrases in cfg:
        for ph in phrases:
            p = ph.lower().strip()
            if len(p) >= 3 and p in lt:
                return family_id
    return ""


def normalized_variant_family_debug(
    primary_set: Optional[str],
    title: str,
    parallel_bucket: str,
) -> Dict[str, str]:
    """Compact debug dict for comp snapshots / tooling."""
    fid = infer_variant_family_id(primary_set, title)
    return {
        "primary_set": (primary_set or "") or "",
        "raw_title_preview": (title or "")[:120],
        "parallel_bucket": parallel_bucket or "",
        "variant_family_id": fid or "",
    }


def learn_token_adjustments_for_title(title: str, decision: str) -> List[Tuple[str, int]]:
    """
    Extra (token, delta) for manual approve/reject learning — title-only, no comp_query import.
    Keeps boosts small to avoid overfitting.
    """
    low = (title or "").lower()
    out: List[Tuple[str, int]] = []
    if decision == "approve":
        if "select" in low and infer_variant_family_id("select", title) == "select_zebra":
            if re.search(r"\bzebra\b", low):
                out.append(("zebra", 1))
            if re.search(r"\bshock\b", low):
                out.append(("shock", 1))
    return out
