"""
Starter product family catalog for Player Hub buy targets (code-seeded, expandable later).

Each row is a durable product line (brand + sport + family), not a user target instance.
Targets reference ``product_family_id`` and may override release year, grade, and terms.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

# --- Generic parallel / card-type options (query fragments; empty = no extra narrow query) ---
PARALLEL_PROFILE_OPTIONS: List[Dict[str, Any]] = [
    {"parallel_id": "base", "label": "Base only (use broad query; no extra narrow lines)", "query_fragment": ""},
    {"parallel_id": "refractor", "label": "Refractor / silver / holo", "query_fragment": "refractor"},
    {"parallel_id": "xfractor", "label": "X-Fractor", "query_fragment": "x-fractor"},
    {"parallel_id": "sapphire", "label": "Sapphire", "query_fragment": "sapphire"},
    {"parallel_id": "nucleus", "label": "Nucleus (Cosmic-style)", "query_fragment": "nucleus"},
    {"parallel_id": "orbit", "label": "Orbit (Cosmic-style)", "query_fragment": "orbit"},
    {"parallel_id": "mojo", "label": "Mojo (Prizm-style)", "query_fragment": "mojo"},
    {"parallel_id": "silver_prizm", "label": "Silver Prizm", "query_fragment": "silver prizm"},
    {"parallel_id": "disco", "label": "Disco / prizm parallel", "query_fragment": "disco"},
    {"parallel_id": "auto", "label": "Autograph", "query_fragment": "auto"},
    {"parallel_id": "rookie_auto", "label": "Rookie autograph", "query_fragment": "rookie auto"},
    {"parallel_id": "numbered", "label": "Numbered / serial", "query_fragment": "serial"},
    {"parallel_id": "color", "label": "Color parallel", "query_fragment": "color"},
    {"parallel_id": "psa10", "label": "PSA 10", "query_fragment": "PSA 10"},
    {"parallel_id": "raw", "label": "Raw (ungraded)", "query_fragment": "raw"},
]

_PARALLEL_BY_ID: Dict[str, Dict[str, Any]] = {str(p["parallel_id"]): p for p in PARALLEL_PROFILE_OPTIONS}

# Keys: product_family_id, brand, sport, product_family_label, set_name,
#       default_query_phrase, default_release_year (optional), active, family_include_terms (optional)
PRODUCT_FAMILY_CATALOG: List[Dict[str, Any]] = [
    # --- Topps / Fanatics — MLB ---
    {
        "product_family_id": "topps_chrome_mlb",
        "brand": "Topps",
        "sport": "MLB",
        "product_family_label": "Topps Chrome Baseball",
        "set_name": "Chrome",
        "default_query_phrase": "Topps Chrome Baseball",
        "default_release_year": None,
        "active": True,
        "family_include_terms": [],
    },
    {
        "product_family_id": "topps_cosmic_chrome_mlb",
        "brand": "Topps",
        "sport": "MLB",
        "product_family_label": "Topps Cosmic Chrome Baseball",
        "set_name": "Cosmic Chrome",
        "default_query_phrase": "Topps Cosmic Chrome Baseball",
        "default_release_year": None,
        "active": True,
        "family_include_terms": [],
    },
    {
        "product_family_id": "bowman_chrome_mlb",
        "brand": "Topps",
        "sport": "MLB",
        "product_family_label": "Bowman Chrome Baseball",
        "set_name": "Bowman Chrome",
        "default_query_phrase": "Bowman Chrome Baseball",
        "default_release_year": None,
        "active": True,
        "family_include_terms": [],
    },
    {
        "product_family_id": "bowman_draft_mlb",
        "brand": "Topps",
        "sport": "MLB",
        "product_family_label": "Bowman Draft Baseball",
        "set_name": "Bowman Draft",
        "default_query_phrase": "Bowman Draft Baseball",
        "default_release_year": None,
        "active": True,
        "family_include_terms": [],
    },
    {
        "product_family_id": "topps_finest_mlb",
        "brand": "Topps",
        "sport": "MLB",
        "product_family_label": "Topps Finest Baseball",
        "set_name": "Finest",
        "default_query_phrase": "Topps Finest Baseball",
        "default_release_year": None,
        "active": True,
        "family_include_terms": [],
    },
    {
        "product_family_id": "topps_series1_mlb",
        "brand": "Topps",
        "sport": "MLB",
        "product_family_label": "Topps Series 1 Baseball",
        "set_name": "Series 1",
        "default_query_phrase": "Topps Series 1 Baseball",
        "default_release_year": None,
        "active": True,
        "family_include_terms": [],
    },
    {
        "product_family_id": "topps_series2_mlb",
        "brand": "Topps",
        "sport": "MLB",
        "product_family_label": "Topps Series 2 Baseball",
        "set_name": "Series 2",
        "default_query_phrase": "Topps Series 2 Baseball",
        "default_release_year": None,
        "active": True,
        "family_include_terms": [],
    },
    # --- Topps / Fanatics — NBA ---
    {
        "product_family_id": "topps_chrome_nba",
        "brand": "Topps",
        "sport": "NBA",
        "product_family_label": "Topps Chrome Basketball",
        "set_name": "Chrome",
        "default_query_phrase": "Topps Chrome Basketball",
        "default_release_year": None,
        "active": True,
        "family_include_terms": [],
    },
    {
        "product_family_id": "topps_cosmic_chrome_nba",
        "brand": "Topps",
        "sport": "NBA",
        "product_family_label": "Topps Cosmic Chrome Basketball",
        "set_name": "Cosmic Chrome",
        "default_query_phrase": "Topps Cosmic Chrome Basketball",
        "default_release_year": None,
        "active": True,
        "family_include_terms": [],
    },
    {
        "product_family_id": "bowman_nba",
        "brand": "Topps",
        "sport": "NBA",
        "product_family_label": "Bowman Basketball",
        "set_name": "Bowman",
        "default_query_phrase": "Bowman Basketball",
        "default_release_year": None,
        "active": True,
        "family_include_terms": [],
    },
    # --- Panini — NFL ---
    {
        "product_family_id": "prizm_nfl",
        "brand": "Panini",
        "sport": "NFL",
        "product_family_label": "Prizm NFL",
        "set_name": "Prizm",
        "default_query_phrase": "Panini Prizm NFL",
        "default_release_year": None,
        "active": True,
        "family_include_terms": [],
    },
    {
        "product_family_id": "select_nfl",
        "brand": "Panini",
        "sport": "NFL",
        "product_family_label": "Select NFL",
        "set_name": "Select",
        "default_query_phrase": "Panini Select NFL",
        "default_release_year": None,
        "active": True,
        "family_include_terms": [],
    },
    {
        "product_family_id": "optic_nfl",
        "brand": "Panini",
        "sport": "NFL",
        "product_family_label": "Donruss Optic NFL",
        "set_name": "Donruss Optic",
        "default_query_phrase": "Panini Donruss Optic NFL",
        "default_release_year": None,
        "active": True,
        "family_include_terms": [],
    },
    {
        "product_family_id": "mosaic_nfl",
        "brand": "Panini",
        "sport": "NFL",
        "product_family_label": "Mosaic NFL",
        "set_name": "Mosaic",
        "default_query_phrase": "Panini Mosaic NFL",
        "default_release_year": None,
        "active": True,
        "family_include_terms": [],
    },
    {
        "product_family_id": "national_treasures_nfl",
        "brand": "Panini",
        "sport": "NFL",
        "product_family_label": "National Treasures NFL",
        "set_name": "National Treasures",
        "default_query_phrase": "National Treasures NFL",
        "default_release_year": None,
        "active": True,
        "family_include_terms": [],
    },
    # --- Panini — NBA ---
    {
        "product_family_id": "prizm_nba",
        "brand": "Panini",
        "sport": "NBA",
        "product_family_label": "Prizm NBA",
        "set_name": "Prizm",
        "default_query_phrase": "Panini Prizm NBA",
        "default_release_year": None,
        "active": True,
        "family_include_terms": [],
    },
    {
        "product_family_id": "select_nba",
        "brand": "Panini",
        "sport": "NBA",
        "product_family_label": "Select NBA",
        "set_name": "Select",
        "default_query_phrase": "Panini Select NBA",
        "default_release_year": None,
        "active": True,
        "family_include_terms": [],
    },
    {
        "product_family_id": "optic_nba",
        "brand": "Panini",
        "sport": "NBA",
        "product_family_label": "Donruss Optic NBA",
        "set_name": "Donruss Optic",
        "default_query_phrase": "Panini Donruss Optic NBA",
        "default_release_year": None,
        "active": True,
        "family_include_terms": [],
    },
    {
        "product_family_id": "mosaic_nba",
        "brand": "Panini",
        "sport": "NBA",
        "product_family_label": "Mosaic NBA",
        "set_name": "Mosaic",
        "default_query_phrase": "Panini Mosaic NBA",
        "default_release_year": None,
        "active": True,
        "family_include_terms": [],
    },
    {
        "product_family_id": "national_treasures_nba",
        "brand": "Panini",
        "sport": "NBA",
        "product_family_label": "National Treasures NBA",
        "set_name": "National Treasures",
        "default_query_phrase": "National Treasures NBA",
        "default_release_year": None,
        "active": True,
        "family_include_terms": [],
    },
    # --- Panini — MLB (optional line) ---
    {
        "product_family_id": "prizm_mlb",
        "brand": "Panini",
        "sport": "MLB",
        "product_family_label": "Prizm MLB",
        "set_name": "Prizm",
        "default_query_phrase": "Panini Prizm MLB",
        "default_release_year": None,
        "active": True,
        "family_include_terms": [],
    },
]

_CATALOG_BY_ID: Dict[str, Dict[str, Any]] = {
    str(e["product_family_id"]): dict(e) for e in PRODUCT_FAMILY_CATALOG if e.get("active", True)
}


def get_product_family(product_family_id: str) -> Optional[Dict[str, Any]]:
    if not product_family_id:
        return None
    row = _CATALOG_BY_ID.get(str(product_family_id).strip())
    return dict(row) if row else None


def catalog_brands() -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for e in PRODUCT_FAMILY_CATALOG:
        if not e.get("active", True):
            continue
        b = str(e.get("brand") or "").strip()
        if b and b not in seen:
            seen.add(b)
            out.append(b)
    return sorted(out, key=lambda x: x.lower())


def catalog_sports_for_brand(brand: str) -> List[str]:
    b = str(brand or "").strip()
    seen: Set[str] = set()
    out: List[str] = []
    for e in PRODUCT_FAMILY_CATALOG:
        if not e.get("active", True):
            continue
        if str(e.get("brand") or "").strip() != b:
            continue
        s = str(e.get("sport") or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return sorted(out, key=lambda x: x.lower())


def catalog_families_for_brand_sport(brand: str, sport: str) -> List[Dict[str, Any]]:
    b = str(brand or "").strip()
    s = str(sport or "").strip()
    out: List[Dict[str, Any]] = []
    for e in PRODUCT_FAMILY_CATALOG:
        if not e.get("active", True):
            continue
        if str(e.get("brand") or "").strip() != b:
            continue
        if str(e.get("sport") or "").strip() != s:
            continue
        out.append(dict(e))
    out.sort(key=lambda x: (str(x.get("product_family_label") or "").lower(), str(x.get("product_family_id") or "")))
    return out


def parallel_query_fragments(parallel_rule_ids: List[str], *, max_fragments: int = 2) -> List[str]:
    """Ordered unique non-empty query fragments from selected parallel ids (capped)."""
    frags: List[str] = []
    seen: Set[str] = set()
    for pid in parallel_rule_ids or []:
        if len(frags) >= max_fragments:
            break
        row = _PARALLEL_BY_ID.get(str(pid))
        if not row:
            continue
        f = str(row.get("query_fragment") or "").strip()
        if not f:
            continue
        if f.lower() in seen:
            continue
        seen.add(f.lower())
        frags.append(f)
    return frags


def parallel_option_ids() -> List[str]:
    return [str(p["parallel_id"]) for p in PARALLEL_PROFILE_OPTIONS]
