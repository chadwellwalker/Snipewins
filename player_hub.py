"""
Player Hub: discovery (recommendation) + monitoring (heat / momentum) from in-app
eBay activity + explicit user intent (My Players, Active Scan, scans). Persistence:
player_hub_state.json (not watchlist / app_state).
"""

from __future__ import annotations

import json
import math
import os
import re
import statistics
import uuid
from difflib import SequenceMatcher
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from player_hub_seed import (
    HUB_CATEGORY_DEFS,
    PLAYER_HUB_SEED_VERSION,
    SEED_PLAYERS,
    players_by_id,
)
from player_hub_product_catalog import (
    PRODUCT_FAMILY_CATALOG,
    get_product_family,
    parallel_query_fragments,
)

STATE_FILE = "player_hub_state.json"
STATE_VERSION = 8

_MAX_TARGET_SCAN_RUNS_STORED = 35
_MAX_RESULTS_PER_TARGET_RUN = 75
# Extra eBay lines per player from parallel rules (capped; broad query always first).
_MAX_PARALLEL_QUERY_FRAGMENTS_PER_PLAYER = 2

# Generic buy-universe: groups, product targets, attachments (seeded defaults merged at load).
YOUNG_GUN_GROUP_DEFS: List[Tuple[str, Dict[str, Any]]] = [
    ("young_gun_nfl", {"label": "Young Gun · NFL", "sport": "NFL", "kind": "young_gun"}),
    ("young_gun_nba", {"label": "Young Gun · NBA", "sport": "NBA", "kind": "young_gun"}),
    ("young_gun_mlb", {"label": "Young Gun · MLB", "sport": "MLB", "kind": "young_gun"}),
]

# First-class buy-universe groups for each sport + Whatnot velocity tiers.
EXTRA_BUY_UNIVERSE_GROUP_DEFS: List[Tuple[str, Dict[str, Any]]] = [
    # Sport buckets (all players per sport live here for scanning)
    ("nfl_all",  {"label": "NFL All Players",  "sport": "NFL",  "kind": "sport_bucket"}),
    ("mlb_all",  {"label": "MLB All Players",  "sport": "MLB",  "kind": "sport_bucket"}),
    ("nba_all",  {"label": "NBA All Players",  "sport": "NBA",  "kind": "sport_bucket"}),
    # Whatnot velocity tiers (cross-sport; no sport restriction so any player can join)
    ("whatnot_t1", {"label": "Whatnot T1 – Instant Sellers", "sport": "", "kind": "whatnot_velocity"}),
    ("whatnot_t2", {"label": "Whatnot T2 – Fast Movers",     "sport": "", "kind": "whatnot_velocity"}),
    ("whatnot_t3", {"label": "Whatnot T3 – Steady Movers",   "sport": "", "kind": "whatnot_velocity"}),
]

# Preset pool label → existing group id mapping.
_PRESET_POOL_LABEL_TO_GROUP_ID = {
    "nfl all players": "nfl_all",
    "mlb all players": "mlb_all",
    "nba all players": "nba_all",
}

DEFAULT_PARALLELS: List[str] = [
    # Core
    "silver", "refractor", "prizm", "numbered", "auto",
    # Autos / patches
    "rpa", "rookie patch auto", "shimmer auto", "rated rookie auto",
    # NFL inserts
    "prizmania", "nebula", "aurora", "tie-dye", "holo",
    "cherry blossom", "tiger stripe", "manga", "downtown", "uptown",
    "gold die-cut", "black die-cut", "gold vinyl",
    # MLB inserts
    "superfractor", "orange refractor", "black refractor", "red refractor",
    "gold refractor", "atomic refractor", "lava lamp refractor",
    "radiating rookies", "printing plates",
    # NBA inserts
    "gold prizm", "black prizm", "groovy", "fireworks", "kaleidoscopic",
    "talismen", "sensational signatures", "prizmatrix signatures",
    "flashback signatures", "dual auto", "triple auto",
]

_MAX_STRUCTURED_QUERY_LINES_PER_PLAYER = 24
DEFAULT_AUCTION_TARGET_BID_PCT = 0.75
DEFAULT_BIN_TARGET_BUY_PCT = 0.70


def get_default_player_pools() -> Dict[str, List[str]]:
    """
    Preset high-liquidity player name lists (display names; Hub merges match seed catalog only).
    NFL split into three commercial tiers for targeted Whatnot-ready scanning.
    """
    return {
        # ── NFL Tier A: instant sellers / premium rookies / breakout stars ────
        "NFL TIER A": [
            # QBs
            "Patrick Mahomes",
            "Josh Allen",
            "Lamar Jackson",
            "Caleb Williams",
            "Jayden Daniels",
            "Shedeur Sanders",
            # WRs (instant sellers)
            "Justin Jefferson",
            "CeeDee Lamb",
            "Tyreek Hill",
            "Marvin Harrison Jr.",
            "Travis Hunter",
            # RB/TE
            "Christian McCaffrey",
            "Brock Bowers",
        ],
        # ── NFL Tier B: strong liquid stars / fast movers ─────────────────────
        "NFL TIER B": [
            # QBs
            "Jalen Hurts",
            "Joe Burrow",
            "C.J. Stroud",
            "Jordan Love",
            "Anthony Richardson",
            "Drake Maye",
            "Cam Ward",
            # WRs
            "Ja'Marr Chase",
            "Amon-Ra St. Brown",
            "Brian Thomas Jr.",
            # RBs
            "Saquon Barkley",
            "De'Von Achane",
            "Ashton Jeanty",
        ],
        # ── NFL Tier C: secondary upside / volume lanes ───────────────────────
        "NFL TIER C": [
            # QBs
            "Kyler Murray",
            "Justin Herbert",
            "Trevor Lawrence",
            "Dak Prescott",
            "Tua Tagovailoa",
            "Michael Penix Jr.",
            "Bryce Young",
            "Bo Nix",
            # WRs
            "Puka Nacua",
            "Malik Nabers",
            "Garrett Wilson",
            "Rashee Rice",
            "Drake London",
            "Chris Olave",
            "Tee Higgins",
            "DeVonta Smith",
            "Rome Odunze",
            "Xavier Worthy",
            # RBs / TEs
            "Bijan Robinson",
            "Breece Hall",
            "Travis Kelce",
            "Sam LaPorta",
            "Sauce Gardner",
            "Trey McBride",
        ],
        # ── NBA ───────────────────────────────────────────────────────────────
        "NBA YOUNG STARS": [
            "Victor Wembanyama",
            "Anthony Edwards",
            "Tyrese Haliburton",
            "Paolo Banchero",
            "Scottie Barnes",
            "Franz Wagner",
            "Chet Holmgren",
        ],
        "NBA LEGENDS / GOATS": [
            "LeBron James",
            "Stephen Curry",
        ],
        # ── MLB ───────────────────────────────────────────────────────────────
        "MLB YOUNG CORE": [
            "Paul Skenes",
            "Gunnar Henderson",
            "Bobby Witt Jr.",
            "Elly De La Cruz",
            "Corbin Carroll",
            "Julio Rodriguez",
        ],
        "MLB Stars": [
            "Shohei Ohtani",
            "Juan Soto",
            "Ronald Acuna Jr.",
            "Mookie Betts",
        ],
    }


def get_default_product_pools() -> Dict[str, List[str]]:
    """Preset product / set keyword buckets for session reference or manual target terms."""
    return {
        "NBA CHROME / OPTIC": ["Prizm", "Select", "Optic", "Mosaic"],
        "NBA HIGH-END": ["National Treasures", "Flawless", "Immaculate"],
        "NFL CHROME / OPTIC": ["Prizm", "Select", "Optic", "Mosaic"],
        "NFL HIGH-END": ["National Treasures", "Flawless", "Immaculate"],
        "MLB TOPPS CORE": [
            "Topps Chrome",
            "Topps Series 1",
            "Topps Series 2",
            "Bowman Chrome",
            "Bowman Draft",
        ],
    }


def build_search_terms(player: str, product: str) -> List[str]:
    """Template eBay lines for player + product fragment (no network I/O)."""
    p = " ".join(str(player or "").split()).strip()
    d = " ".join(str(product or "").split()).strip()
    if not p or not d:
        return []
    return [
        f"{p} {d} rookie",
        f"{p} {d} auto",
        f"{p} {d} psa 10",
        f"{p} {d} refractor",
        f"{p} {d} silver",
    ]


# Full card/product target records — 36 targets across NFL/MLB/NBA (2016-present).
def _pt(tid, label, sport, brand, set_name, scope=""):
    """Quick product target builder with standard defaults."""
    return {
        "target_id": tid,
        "label": label,
        "sport": sport,
        "brand": brand,
        "product_family_id": tid,
        "set_name": set_name,
        "release_year": None,
        "parallel_rule_ids": [],
        "approved_subsets": [],
        "approved_parallel_families": [],
        "card_scope": scope or f"{label} — raw singles, refractors, numbered parallels.",
        "include_terms": [],
        "exclude_terms": ["lot", "break", "case", "jumbo", "hobby box"],
        "broad_fallback_mode": False,
        "lane_targets": [],
        "default_grade_filter": "",
        "active": True,
    }

DEFAULT_PRODUCT_TARGETS: Dict[str, Dict[str, Any]] = {
    # ── NFL (17 brands) ──────────────────────────────────────────────────────
    # Core chrome/prizm lines — highest heat
    "prizm_nfl":       _pt("prizm_nfl",       "Panini Prizm NFL",         "NFL", "Panini", "Prizm"),
    "select_nfl":      _pt("select_nfl",      "Panini Select NFL",        "NFL", "Panini", "Select"),
    "mosaic_nfl":      _pt("mosaic_nfl",      "Panini Mosaic NFL",        "NFL", "Panini", "Mosaic"),
    "optic_nfl":       _pt("optic_nfl",       "Donruss Optic NFL",        "NFL", "Panini", "Donruss Optic"),
    "contenders_nfl":  _pt("contenders_nfl",  "Panini Contenders NFL",    "NFL", "Panini", "Contenders"),
    "chronicles_nfl":  _pt("chronicles_nfl",  "Panini Chronicles NFL",    "NFL", "Panini", "Chronicles"),
    "absolute_nfl":    _pt("absolute_nfl",    "Panini Absolute NFL",      "NFL", "Panini", "Absolute"),
    "score_nfl":       _pt("score_nfl",       "Panini Score NFL",         "NFL", "Panini", "Score"),
    "illusions_nfl":   _pt("illusions_nfl",   "Panini Illusions NFL",     "NFL", "Panini", "Illusions"),
    "luminance_nfl":   _pt("luminance_nfl",   "Panini Luminance NFL",     "NFL", "Panini", "Luminance"),
    # Extended NFL lines — numbered/premium/high-velocity
    "spectra_nfl":     _pt("spectra_nfl",     "Panini Spectra NFL",       "NFL", "Panini", "Spectra",
                           "Spectra NFL — premium numbered rookies/autos, heavy Whatnot heat."),
    "certified_nfl":   _pt("certified_nfl",   "Panini Certified NFL",     "NFL", "Panini", "Certified"),
    "donruss_nfl":     _pt("donruss_nfl",     "Panini Donruss NFL",       "NFL", "Panini", "Donruss",
                           "Donruss NFL — Rated Rookies base, high-volume, strong resale."),
    "xr_nfl":          _pt("xr_nfl",          "Panini XR NFL",            "NFL", "Panini", "XR"),
    "revolution_nfl":  _pt("revolution_nfl",  "Panini Revolution NFL",    "NFL", "Panini", "Revolution"),
    "one_nfl":         _pt("one_nfl",         "Panini ONE NFL",           "NFL", "Panini", "ONE",
                           "Panini ONE — premium numbered, on-card autos, strong resale."),
    "zenith_nfl":      _pt("zenith_nfl",      "Panini Zenith NFL",        "NFL", "Panini", "Zenith"),
    # ── MLB (14 brands) ──────────────────────────────────────────────────────
    "topps_chrome_mlb":      _pt("topps_chrome_mlb",      "Topps Chrome MLB",           "MLB", "Topps",  "Chrome"),
    "topps_series1_mlb":     _pt("topps_series1_mlb",     "Topps Series 1 MLB",         "MLB", "Topps",  "Series 1"),
    "topps_series2_mlb":     _pt("topps_series2_mlb",     "Topps Series 2 MLB",         "MLB", "Topps",  "Series 2"),
    "topps_update_mlb":      _pt("topps_update_mlb",      "Topps Update MLB",           "MLB", "Topps",  "Update"),
    "bowman_chrome_mlb":     _pt("bowman_chrome_mlb",     "Bowman Chrome MLB",          "MLB", "Topps",  "Bowman Chrome"),
    "bowman_draft_mlb":      _pt("bowman_draft_mlb",      "Bowman Draft MLB",           "MLB", "Topps",  "Bowman Draft"),
    "bowman_platinum_mlb":   _pt("bowman_platinum_mlb",   "Bowman Platinum MLB",        "MLB", "Topps",  "Bowman Platinum"),
    "topps_heritage_mlb":    _pt("topps_heritage_mlb",    "Topps Heritage MLB",         "MLB", "Topps",  "Heritage"),
    "topps_stadium_club_mlb":_pt("topps_stadium_club_mlb","Topps Stadium Club MLB",     "MLB", "Topps",  "Stadium Club"),
    "topps_finest_mlb":      _pt("topps_finest_mlb",      "Topps Finest MLB",           "MLB", "Topps",  "Finest"),
    "prizm_mlb":             _pt("prizm_mlb",             "Panini Prizm Baseball",      "MLB", "Panini", "Prizm"),
    "allen_ginter_mlb":      _pt("allen_ginter_mlb",      "Allen & Ginter MLB",         "MLB", "Topps",  "Allen Ginter"),
    "topps_gold_label_mlb":  _pt("topps_gold_label_mlb",  "Topps Gold Label MLB",       "MLB", "Topps",  "Gold Label"),
    "topps_clearly_auth_mlb":_pt("topps_clearly_auth_mlb","Topps Clearly Authentic MLB","MLB", "Topps",  "Clearly Authentic"),
    # ── NBA (12 brands) ──────────────────────────────────────────────────────
    "prizm_nba":             _pt("prizm_nba",             "Panini Prizm NBA",           "NBA", "Panini", "Prizm"),
    "select_nba":            _pt("select_nba",            "Panini Select NBA",          "NBA", "Panini", "Select"),
    "mosaic_nba":            _pt("mosaic_nba",            "Panini Mosaic NBA",          "NBA", "Panini", "Mosaic"),
    "optic_nba":             _pt("optic_nba",             "Donruss Optic NBA",          "NBA", "Panini", "Donruss Optic"),
    "hoops_nba":             _pt("hoops_nba",             "Panini Hoops NBA",           "NBA", "Panini", "Hoops"),
    "chronicles_nba":        _pt("chronicles_nba",        "Panini Chronicles NBA",      "NBA", "Panini", "Chronicles"),
    "revolution_nba":        _pt("revolution_nba",        "Revolution NBA",             "NBA", "Panini", "Revolution"),
    "court_kings_nba":       _pt("court_kings_nba",       "Court Kings NBA",            "NBA", "Panini", "Court Kings"),
    "national_treasures_nba":_pt("national_treasures_nba","National Treasures NBA",     "NBA", "Panini", "National Treasures"),
    "immaculate_nba":        _pt("immaculate_nba",        "Immaculate Collection NBA",  "NBA", "Panini", "Immaculate"),
    "contenders_nba":        _pt("contenders_nba",        "Panini Contenders NBA",      "NBA", "Panini", "Contenders"),
    "flux_nba":              _pt("flux_nba",              "Panini Flux NBA",            "NBA", "Panini", "Flux"),
}

# Each product linked to its sport's player group.
DEFAULT_TARGET_GROUP_LINKS: Dict[str, List[str]] = {
    tid: (["nfl_all"] if meta["sport"] == "NFL"
          else ["mlb_all"] if meta["sport"] == "MLB"
          else ["nba_all"])
    for tid, meta in DEFAULT_PRODUCT_TARGETS.items()
}

# NBA product targets that require an explicit premium signal to survive contract generation.
# Without auto lanes, serial lanes, or configured premium subsets these products generate
# broad product-bound queries that waste scan budget and never survive truth/supply gates.
_NBA_WEAK_PRODUCT_TARGETS_SUPPRESS: frozenset = frozenset({
    "hoops_nba",
    "chronicles_nba",
    "revolution_nba",
    "court_kings_nba",
    "flux_nba",
})

_MAX_SNAPSHOTS_PER_PLAYER = 20

# ---------------------------------------------------------------------------
# Whatnot velocity helpers
# ---------------------------------------------------------------------------

def get_whatnot_tier_for_player_id(player_id: str) -> int:
    """Return Whatnot velocity tier (1/2/3) for a seed player_id, or 3 if unknown."""
    from player_hub_seed import WHATNOT_TIER_BY_PLAYER_ID
    return int(WHATNOT_TIER_BY_PLAYER_ID.get(str(player_id) or "", 3) or 3)


def get_whatnot_tier_for_display_name(display_name: str) -> int:
    """Resolve display name → player_id → tier. Returns 3 if not found."""
    pid = resolve_hub_player_id_from_display_name(display_name)
    if pid:
        return get_whatnot_tier_for_player_id(pid)
    # Slug fallback for non-seed names added directly to memberships
    slug = re.sub(r"[^a-z0-9]+", "_", (display_name or "").strip().lower()).strip("_")
    if slug:
        return get_whatnot_tier_for_player_id(slug)
    return 3


def get_whatnot_tier_for_scan_row(scan_row: Dict[str, Any]) -> int:
    """Best (lowest) Whatnot tier across all matched players in a scan row."""
    best = 3
    for nm in (scan_row.get("matched_players") or []):
        t = get_whatnot_tier_for_display_name(str(nm))
        if t < best:
            best = t
    return best


def whatnot_tier_label(tier: int) -> str:
    from player_hub_seed import WHATNOT_TIER_LABELS
    return WHATNOT_TIER_LABELS.get(int(tier), "T3 STEADY")


def whatnot_tier_color(tier: int) -> str:
    from player_hub_seed import WHATNOT_TIER_COLORS
    return WHATNOT_TIER_COLORS.get(int(tier), "#94a3b8")

_CAP_LISTING_SNAPSHOT = 12.0
_CAP_KEYWORD = 8.0
_CAP_WATCHLIST = 20.0

HEAT_UP_MIN = 38.0
HEAT_COOL_MAX = 42.0
STEADY_HEAT_LOW = 26.0
STEADY_HEAT_HIGH = 62.0
STEADY_MIN_SNAPSHOTS = 4


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso_ts(ts: str) -> Optional[datetime]:
    if not ts or not isinstance(ts, str):
        return None
    t = ts.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(t)
    except ValueError:
        return None


def _hours_since_iso(ts: str) -> float:
    dt = _parse_iso_ts(ts)
    if not dt:
        return 168.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    return max(0.0, delta.total_seconds() / 3600.0)


def default_state() -> Dict[str, Any]:
    return {
        "version": STATE_VERSION,
        "player_overrides": {},
        "signals": {
            "listing_depth_last_search": {},
            "listing_depth_last_radar": {},
            "keyword_search_count": {},
            "watchlist_card_hits": {},
            "opportunity_hits": {},
            "cockpit_strong_hits_last": {},
            "cockpit_snipe_hits_last": {},
        },
        "monitoring": {
            "per_player": {},
            "meta": {"last_board_signature": ""},
        },
        "scan_meta": {},
        "active_scan_player_ids": [],
        "meta": {
            "last_watchlist_rescan": None,
            "category_source": "player_hub_seed.SEED_PLAYERS",
        },
        "buy_universe": {
            "groups": {},
            "product_targets": {},
            "player_memberships": {},
            "target_group_links": {},
            "target_scan_runs": [],
            "target_latest_run_by_target": {},
            "validation_mode": {
                "enabled": True,
                "max_players": 120,
                "max_targets_per_player": 25,
                "allowed_player_ids": [],
                "allowed_target_ids": [],
            },
        },
    }


def sanitize_target_id(raw: str) -> str:
    """Stable slug for target_id: lowercase letters, digits, underscores."""
    x = (raw or "").strip().lower()
    x = re.sub(r"\s+", "_", x)
    x = re.sub(r"[^a-z0-9_]+", "_", x)
    x = re.sub(r"_+", "_", x).strip("_")
    return x[:120] if x else ""


def _coerce_release_year(val: Any) -> Optional[int]:
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _coerce_term_list(val: Any) -> List[str]:
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str) and val.strip():
        return [t.strip() for t in val.replace("\n", ",").split(",") if t.strip()]
    return []


def normalize_product_target(target_id: str, raw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Canonical product/card target dict for storage and query generation."""
    raw = raw if isinstance(raw, dict) else {}
    tid = sanitize_target_id(target_id) or str(target_id).strip()
    out: Dict[str, Any] = {
        "target_id": tid,
        "label": "",
        "sport": "",
        "brand": "",
        "product_family_id": "",
        "set_name": "",
        "release_year": None,
        "parallel_rule_ids": [],
        "approved_subsets": [],
        "approved_parallel_families": [],
        "card_scope": "",
        "include_terms": [],
        "exclude_terms": [],
        "broad_fallback_mode": False,
        "lane_targets": [],
        "default_grade_filter": "",
        "active": True,
    }
    for k in list(out.keys()):
        if k == "target_id":
            continue
        if k not in raw:
            continue
        val = raw[k]
        if k in ("include_terms", "exclude_terms", "approved_subsets", "approved_parallel_families"):
            out[k] = _coerce_term_list(val)
        elif k == "lane_targets":
            _lanes: List[Dict[str, Any]] = []
            for _entry in (val or []):
                if not isinstance(_entry, dict):
                    continue
                _lane = {
                    "product": " ".join(str(_entry.get("product") or raw.get("set_name") or "").split()).strip(),
                    "subset": " ".join(str(_entry.get("subset") or "").split()).strip(),
                    "parallel": " ".join(str(_entry.get("parallel") or "").split()).strip(),
                    "tier": "secondary" if str(_entry.get("tier") or "").strip().lower() == "secondary" else "primary",
                }
                if _lane["product"]:
                    _lanes.append(_lane)
            out[k] = _lanes
        elif k == "parallel_rule_ids":
            if isinstance(val, list):
                out[k] = [str(x).strip() for x in val if str(x).strip()]
            else:
                out[k] = []
        elif k == "release_year":
            out[k] = _coerce_release_year(val)
        elif k == "active":
            out[k] = bool(val)
        elif k == "broad_fallback_mode":
            out[k] = bool(val)
        else:
            out[k] = str(val).strip() if val is not None else ""
    out["target_id"] = tid
    return out


def resolve_effective_product_target_meta(meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge saved target row with catalog defaults for the selected ``product_family_id``.
    Used for query text, validation anchors, and ranking — does not write to disk.
    """
    if not meta:
        return normalize_product_target("", {})
    tid = str(meta.get("target_id") or "")
    m = normalize_product_target(tid, meta)
    _passthrough = {
        str(k): v
        for k, v in dict(meta or {}).items()
        if str(k) not in m and v not in (None, "", [], {})
    }
    fid = str(m.get("product_family_id") or "").strip()
    if not fid:
        m.update(_passthrough)
        return m
    ce = get_product_family(fid)
    if not ce:
        m.update(_passthrough)
        return m
    if not str(m.get("brand") or "").strip():
        m["brand"] = str(ce.get("brand") or "").strip()
    if not str(m.get("sport") or "").strip():
        m["sport"] = str(ce.get("sport") or "").strip()
    if not str(m.get("set_name") or "").strip():
        m["set_name"] = str(ce.get("set_name") or "").strip()
    if m.get("release_year") is None and ce.get("default_release_year") is not None:
        m["release_year"] = _coerce_release_year(ce.get("default_release_year"))
    if not str(m.get("label") or "").strip():
        m["label"] = str(ce.get("product_family_label") or "").strip()
    _resolved = normalize_product_target(tid, m)
    _resolved.update(_passthrough)
    return _resolved


def merge_product_target_defaults(target_id: str, raw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Merge saved row with seed defaults (when target_id matches a seed) and normalize."""
    raw = raw if isinstance(raw, dict) else {}
    tid_key = sanitize_target_id(target_id) or str(target_id).strip()
    seed = DEFAULT_PRODUCT_TARGETS.get(tid_key)
    if seed:
        merged = {**normalize_product_target(tid_key, seed), **raw}
    else:
        merged = {**normalize_product_target(tid_key, {}), **raw}
    return normalize_product_target(tid_key, merged)


def upgrade_all_product_targets(bu: Dict[str, Any]) -> None:
    pt = bu.get("product_targets") or {}
    if not isinstance(pt, dict):
        return
    for tid in list(pt.keys()):
        row = pt[tid]
        pt[tid] = merge_product_target_defaults(str(tid), row if isinstance(row, dict) else {})


def ensure_buy_universe_seed(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge in default Young Gun groups, product targets, starter target→group links,
    and auto-seed all seed players into their sport bucket groups (idempotent).
    """
    bu = state.setdefault("buy_universe", default_state()["buy_universe"])
    bu.setdefault("groups", {})
    bu.setdefault("product_targets", {})
    bu.setdefault("player_memberships", {})
    bu.setdefault("target_group_links", {})
    bu.setdefault("target_scan_runs", [])
    bu.setdefault("target_latest_run_by_target", {})
    for gid, meta in YOUNG_GUN_GROUP_DEFS:
        if gid not in bu["groups"]:
            bu["groups"][gid] = dict(meta)
    for gid, meta in EXTRA_BUY_UNIVERSE_GROUP_DEFS:
        if gid not in bu["groups"]:
            bu["groups"][gid] = dict(meta)
    for tid, meta in DEFAULT_PRODUCT_TARGETS.items():
        if tid not in bu["product_targets"]:
            bu["product_targets"][tid] = dict(meta)
    for tid, gids in DEFAULT_TARGET_GROUP_LINKS.items():
        if tid not in bu["target_group_links"]:
            bu["target_group_links"][tid] = list(gids)
    upgrade_all_product_targets(bu)

    # Auto-seed all SEED_PLAYERS into their sport bucket groups (nfl_all, mlb_all, nba_all).
    # Idempotent: only adds membership if not already present.
    _sport_to_bucket = {"NFL": "nfl_all", "MLB": "mlb_all", "NBA": "nba_all"}
    _pm = bu["player_memberships"]
    from player_hub_seed import SEED_PLAYERS as _SEED_PLAYERS_REF
    for _sp in _SEED_PLAYERS_REF:
        _pid = str(_sp.get("player_id") or "").strip()
        _sport_norm = normalize_hub_sport(str(_sp.get("sport") or ""))
        _bucket = _sport_to_bucket.get(_sport_norm)
        if _pid and _bucket and _bucket in bu["groups"]:
            _member_list = _pm.setdefault(_pid, [])
            if _bucket not in _member_list:
                _member_list.append(_bucket)

    return state


def normalize_hub_sport(s: str) -> str:
    """Map seed/UI sport strings to NFL | NBA | MLB."""
    x = (s or "").strip().lower()
    if x in ("football", "nfl"):
        return "NFL"
    if x in ("basketball", "nba"):
        return "NBA"
    if x in ("baseball", "mlb"):
        return "MLB"
    return ""


def young_gun_group_id_for_sport(seed_sport: str) -> Optional[str]:
    code = normalize_hub_sport(seed_sport)
    return {"NFL": "young_gun_nfl", "NBA": "young_gun_nba", "MLB": "young_gun_mlb"}.get(code)


def get_player_group_ids(state: Dict[str, Any], player_id: str) -> List[str]:
    bu = (state.get("buy_universe") or {})
    pm = bu.get("player_memberships") or {}
    raw = pm.get(str(player_id)) or []
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw if str(x)]


def get_player_group_memberships(state: Dict[str, Any], player_id: str) -> List[str]:
    """Group/pool ids for this player from ``buy_universe.player_memberships`` (alias of :func:`get_player_group_ids`)."""
    return list(get_player_group_ids(state, player_id))


def get_target_group_ids(state: Dict[str, Any], target_id: str) -> List[str]:
    """
    Stable attached group ids for a product target.
    Falls back to seeded defaults or sport bucket when explicit links are missing.
    """
    ensure_buy_universe_seed(state)
    bu = state.get("buy_universe") or {}
    tid = str(target_id or "").strip()
    valid_groups = set((bu.get("groups") or {}).keys())
    raw_links = (bu.get("target_group_links") or {}).get(tid) or []
    ordered: List[str] = []
    seen: set = set()

    def _push_many(values: Any) -> None:
        for raw in list(values or []):
            gid = str(raw or "").strip()
            if not gid or gid not in valid_groups or gid in seen:
                continue
            seen.add(gid)
            ordered.append(gid)

    _push_many(raw_links)
    if ordered:
        return ordered

    _push_many(DEFAULT_TARGET_GROUP_LINKS.get(tid) or [])
    if ordered:
        return ordered

    meta = get_product_target(state, tid) or {}
    sport = normalize_hub_sport(str(meta.get("sport") or ""))
    fallback_gid = {"NFL": "nfl_all", "NBA": "nba_all", "MLB": "mlb_all"}.get(sport)
    _push_many([fallback_gid] if fallback_gid else [])
    return ordered


def player_has_any_group_membership(state: Dict[str, Any], player_id: str) -> bool:
    return bool(get_player_group_ids(state, str(player_id)))


def partition_profiles_by_pool_membership(
    profiles: List[Dict[str, Any]], state: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split profile rows into (in at least one pool, in no pool) using real ``player_memberships`` only."""
    tracked: List[Dict[str, Any]] = []
    untracked: List[Dict[str, Any]] = []
    for p in profiles:
        pid = str(p.get("player_id") or "")
        if player_has_any_group_membership(state, pid):
            tracked.append(p)
        else:
            untracked.append(p)
    return tracked, untracked


def get_tracked_players(
    profiles: List[Dict[str, Any]], state: Dict[str, Any]
) -> List[Dict[str, Any]]:
    t, _ = partition_profiles_by_pool_membership(profiles, state)
    return t


def get_untracked_players(
    profiles: List[Dict[str, Any]], state: Dict[str, Any]
) -> List[Dict[str, Any]]:
    _, u = partition_profiles_by_pool_membership(profiles, state)
    return u


def set_player_group_membership(state: Dict[str, Any], player_id: str, group_id: str, member: bool) -> Dict[str, Any]:
    ensure_buy_universe_seed(state)
    bu = state["buy_universe"]
    gid = str(group_id)
    pid = str(player_id)
    grp = bu["groups"].get(gid)
    if not isinstance(grp, dict):
        return state
    seeds = players_by_id()
    seed = seeds.get(pid)
    if not seed:
        return state
    p_sport = normalize_hub_sport(str(seed.get("sport") or ""))
    g_sport = str(grp.get("sport") or "").strip().upper()
    if p_sport and g_sport and p_sport != g_sport:
        return state
    cur = set(get_player_group_ids(state, pid))
    if member:
        cur.add(gid)
    else:
        cur.discard(gid)
    bu.setdefault("player_memberships", {})
    bu["player_memberships"][pid] = sorted(cur)
    return state


def set_target_attached_groups(
    state: Dict[str, Any], target_id: str, group_ids: List[str]
) -> Dict[str, Any]:
    ensure_buy_universe_seed(state)
    bu = state["buy_universe"]
    tid = str(target_id)
    if tid not in bu.get("product_targets", {}):
        return state
    valid = set(bu.get("groups", {}).keys())
    cleaned = [str(g) for g in group_ids if str(g) in valid]
    bu.setdefault("target_group_links", {})
    bu["target_group_links"][tid] = cleaned
    return state


def resolve_product_target_player_ids(state: Dict[str, Any], target_id: str) -> List[str]:
    ensure_buy_universe_seed(state)
    bu = state.get("buy_universe") or {}
    group_ids = set(bu.get("target_group_links", {}).get(str(target_id)) or [])
    if not group_ids:
        return []
    pm = bu.get("player_memberships") or {}
    out: List[str] = []
    for pid, glist in pm.items():
        if not isinstance(glist, list):
            continue
        if group_ids.intersection(str(g) for g in glist):
            out.append(str(pid))
    return sorted(out)


def get_target_player_records(state: Dict[str, Any], target_id: str) -> List[Dict[str, str]]:
    """Structured rows: player_id + player_name for this card target."""
    pids = resolve_product_target_player_ids(state, target_id)
    seeds = players_by_id()
    out: List[Dict[str, str]] = []
    for pid in pids:
        row = seeds.get(pid) or {}
        out.append({"player_id": pid, "player_name": str(row.get("player_name") or pid)})
    out.sort(key=lambda x: x["player_name"].lower())
    return out


def get_target_players(state: Dict[str, Any], target_id: str) -> List[str]:
    """
    For target X, which players should be scanned? Display names from attached groups.
    Ordered A–Z by name.
    """
    return [r["player_name"] for r in get_target_player_records(state, target_id)]


def normalize_hub_display_name(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def resolve_hub_player_id_from_display_name(display_name: str) -> Optional[str]:
    """
    Map a listing/scanner display name to a hub seed player_id (first exact normalized name match).
    """
    want = normalize_hub_display_name(display_name)
    if not want:
        return None
    seeds = players_by_id()
    for pid, row in seeds.items():
        nm = normalize_hub_display_name(str((row or {}).get("player_name") or ""))
        if nm == want:
            return str(pid)
    return None


def merge_player_pool_presets_into_buy_universe(
    state: Dict[str, Any],
    player_pools: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Add non-destructive preset groups (pp_*) and memberships for names that resolve to hub seeds.
    Existing groups and memberships are kept.
    """
    ensure_buy_universe_seed(state)
    if not isinstance(player_pools, dict):
        return state
    bu = state["buy_universe"]
    bu.setdefault("groups", {})
    for label, names in player_pools.items():
        if not isinstance(names, list):
            continue
        lk = str(label).strip().lower()
        mapped = _PRESET_POOL_LABEL_TO_GROUP_ID.get(lk)
        if mapped and mapped in bu["groups"]:
            gid = mapped
        else:
            slug = sanitize_target_id(str(label)) or re.sub(r"[^a-z0-9]+", "_", str(label).lower()).strip("_")[:80]
            gid = f"pp_{slug}" if slug else f"pp_pool_{abs(hash(str(label))) % 10_000_000}"
        if gid not in bu["groups"]:
            ul = str(label).upper()
            sport = ""
            if "NBA" in ul:
                sport = "NBA"
            elif "NFL" in ul:
                sport = "NFL"
            elif "MLB" in ul:
                sport = "MLB"
            bu["groups"][gid] = {"label": str(label), "sport": sport, "kind": "preset_pool"}
        for nm in names:
            pid = resolve_hub_player_id_from_display_name(str(nm))
            if pid:
                state = set_player_group_membership(state, pid, gid, True)
    return state


def iter_player_ids_in_selected_groups(state: Dict[str, Any], selected_group_ids: Set[str]) -> List[str]:
    """Player ids that belong to at least one of ``selected_group_ids``."""
    ensure_buy_universe_seed(state)
    if not selected_group_ids:
        return []
    bu = state.get("buy_universe") or {}
    pm = bu.get("player_memberships") or {}
    want = {str(g) for g in selected_group_ids if str(g).strip()}
    out: List[str] = []
    for pid, glist in pm.items():
        if not isinstance(glist, list):
            continue
        if want.intersection(str(g) for g in glist):
            out.append(str(pid))
    return out


def list_buy_universe_groups(state: Dict[str, Any]) -> List[Dict[str, str]]:
    """Buy-universe group ids + labels for filters/UI (sorted by label)."""
    ensure_buy_universe_seed(state)
    bu = state.get("buy_universe") or {}
    raw = bu.get("groups") or {}
    out: List[Dict[str, str]] = []
    for gid, meta in raw.items():
        if not isinstance(meta, dict):
            continue
        out.append(
            {
                "group_id": str(gid),
                "label": str(meta.get("label") or gid),
                "sport": str(meta.get("sport") or ""),
            }
        )
    out.sort(key=lambda x: (x["label"].lower(), x["group_id"]))
    return out


def scan_row_matches_selected_player_pools(
    state: Dict[str, Any],
    scan_row: Dict[str, Any],
    selected_group_ids: set,
) -> bool:
    """
    True if no pool filter, or at least one matched_players name resolves to a player
    who is a member of at least one selected group (durable group_id in buy_universe).

    Also re-checks the **listing title** against current members of the selected groups
    so pool changes take effect without requiring a new target scan when the title
    already names that player.
    """
    if not selected_group_ids:
        return True
    sel = {str(g) for g in selected_group_ids if g}
    bu_pm = ((state.get("buy_universe") or {}).get("player_memberships") or {})
    names = scan_row.get("matched_players") or []
    for nm in names:
        pid = resolve_hub_player_id_from_display_name(str(nm))
        if not pid:
            # Fallback: non-seed player — derive slug from display name and check memberships directly
            slug = re.sub(r"[^a-z0-9]+", "_", (str(nm) or "").strip().lower()).strip("_")
            if slug and slug in bu_pm:
                pid = slug
        if not pid:
            continue
        pg = set(get_player_group_ids(state, pid))
        if pg & sel:
            return True
    item = scan_row.get("item") if isinstance(scan_row.get("item"), dict) else {}
    title = str(item.get("title") or scan_row.get("title") or "")
    nt = normalize_title_for_match(title)
    if nt:
        for pid in iter_player_ids_in_selected_groups(state, sel):
            seed = players_by_id().get(pid)
            if isinstance(seed, dict) and listing_matches_target_player(nt, seed)[0]:
                return True
            elif seed is None:
                # Non-seed player: derive name from slug id and check if title contains it
                derived_name = pid.replace("_", " ").strip()
                if derived_name and derived_name in nt:
                    return True
    return False


def resolve_product_target_player_names(state: Dict[str, Any], target_id: str) -> List[str]:
    """For product target X, return display names of players in any attached group."""
    return get_target_players(state, target_id)


def get_product_target(state: Dict[str, Any], target_id: str) -> Optional[Dict[str, Any]]:
    ensure_buy_universe_seed(state)
    bu = state.get("buy_universe") or {}
    tid = str(target_id)
    row = bu.get("product_targets", {}).get(tid)
    if not isinstance(row, dict):
        return None
    return merge_product_target_defaults(tid, row)


def build_target_product_phrase(meta: Dict[str, Any]) -> str:
    """Human/product fragment for eBay (catalog phrase + optional release year, or legacy brand/set/year)."""
    m = resolve_effective_product_target_meta(meta)
    fid = str(m.get("product_family_id") or "").strip()
    if fid:
        ce = get_product_family(fid)
        if ce:
            dq = str(ce.get("default_query_phrase") or "").strip()
            if dq:
                ry = m.get("release_year")
                if ry is not None:
                    try:
                        dq = f"{dq} {int(ry)}".strip()
                    except (TypeError, ValueError):
                        pass
                return dq[:180].strip()
    brand = str(m.get("brand") or "").strip()
    set_name = str(m.get("set_name") or "").strip()
    ry = m.get("release_year")
    ry_s = str(int(ry)) if ry is not None else ""
    parts = [p for p in [brand, set_name, ry_s] if p]
    return " ".join(parts)[:180].strip()


def _target_subset_terms(meta: Dict[str, Any]) -> List[str]:
    m = resolve_effective_product_target_meta(meta)
    vals = list(m.get("approved_subsets") or [])
    if not vals:
        vals = list(m.get("include_terms") or [])
    out: List[str] = []
    seen: Set[str] = set()
    for val in vals:
        s = " ".join(str(val).split()).strip()
        if not s:
            continue
        sk = s.lower()
        if sk in seen:
            continue
        seen.add(sk)
        out.append(s)
    return out[:8]


def _target_parallel_terms(meta: Dict[str, Any]) -> List[str]:
    m = resolve_effective_product_target_meta(meta)
    vals = list(m.get("approved_parallel_families") or [])
    if vals:
        return [str(v).strip() for v in vals if str(v).strip()][:6]
    pids = m.get("parallel_rule_ids") or []
    return parallel_query_fragments(
        pids if isinstance(pids, list) else [],
        max_fragments=_MAX_PARALLEL_QUERY_FRAGMENTS_PER_PLAYER,
    )


# Premium signal keywords — any hit on subset or parallel terms qualifies a weak product target.
_PREMIUM_SIGNAL_SUBSET_KEYWORDS: frozenset = frozenset({
    "auto", "autograph", "patch", "rpa", "auto patch",
    "refractor", "gold", "silver", "ssp", "case hit",
    "rookie auto", "base auto", "numbered",
})
_PREMIUM_SIGNAL_PARALLEL_KEYWORDS: frozenset = frozenset({
    "#", "/", "auto", "gold", "patch", "refractor", "silver",
    "superfractor", "orange", "red", "black", "numbered",
})


def _nba_target_has_premium_signal(
    meta_eff: Dict[str, Any],
    subset_terms: List[str],
    parallel_terms: List[str],
) -> str:
    """Return a non-empty reason string if the target carries a premium signal; empty string if not.

    Used to gate weak NBA product families (Hoops, Chronicles, etc.) — if no premium signal
    is present the target is suppressed entirely from contract generation.
    """
    # Explicit config flags override everything
    for _flag in ("auto_only", "serial_required", "endgame_only", "require_premium_signal", "premium_required"):
        if bool(meta_eff.get(_flag)):
            return f"explicit_flag:{_flag}"
    # User-configured lane_targets always carry intent
    if list(meta_eff.get("lane_targets") or []):
        return "lane_targets_configured"
    # Premium subset terms (autos, patches, refractors, SSPs)
    _sub_joined = " ".join(s.lower() for s in subset_terms)
    for _kw in _PREMIUM_SIGNAL_SUBSET_KEYWORDS:
        if _kw in _sub_joined:
            return f"premium_subset:{_kw}"
    # Premium parallel terms (serials, golds, autos)
    _par_joined = " ".join(p.lower() for p in parallel_terms)
    for _kw in _PREMIUM_SIGNAL_PARALLEL_KEYWORDS:
        if _kw in _par_joined:
            return f"premium_parallel:{_kw}"
    return ""


def build_target_scan_query_specs(
    state: Dict[str, Any],
    target_id: str,
    *,
    scan_options: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    """
    Per-player eBay query specs: lane-first lines built from approved product/subset/parallel
    targets. Broad player+product fallback is opt-in via target config.
    """
    ensure_buy_universe_seed(state)
    tid = str(target_id)
    meta = get_product_target(state, tid)
    if not meta or not meta.get("active", True):
        return []
    m_eff = resolve_effective_product_target_meta(meta)
    phrase = build_target_product_phrase(m_eff)
    if not phrase:
        return []
    opts = scan_options if isinstance(scan_options, dict) else {}
    use_structured = bool(opts.get("use_structured_terms"))
    append_par = bool(opts.get("append_default_parallels"))

    include = m_eff.get("include_terms") or []
    inc_tail = " ".join(str(t).strip() for t in include if str(t).strip())[:120].strip()
    grade = str(m_eff.get("default_grade_filter") or "").strip()
    fam_extra = ""
    fid = str(m_eff.get("product_family_id") or "").strip()
    if fid:
        ce = get_product_family(fid)
        if ce:
            ft = ce.get("family_include_terms") or []
            fam_extra = " ".join(str(t).strip() for t in ft if str(t).strip())[:80].strip()
    subset_terms = _target_subset_terms(m_eff)
    parallel_terms = _target_parallel_terms(m_eff)
    broad_fallback = bool(m_eff.get("broad_fallback_mode"))
    lane_targets = [dict(x) for x in (m_eff.get("lane_targets") or []) if isinstance(x, dict)]
    if not lane_targets:
        if subset_terms:
            for _subset in subset_terms[:8]:
                lane_targets.append({"product": phrase, "subset": _subset, "parallel": "", "tier": "primary"})
                for _par in parallel_terms[:_MAX_PARALLEL_QUERY_FRAGMENTS_PER_PLAYER]:
                    lane_targets.append({"product": phrase, "subset": _subset, "parallel": _par, "tier": "primary"})
        elif parallel_terms:
            for _par in parallel_terms[:_MAX_PARALLEL_QUERY_FRAGMENTS_PER_PLAYER]:
                lane_targets.append({"product": phrase, "subset": "", "parallel": _par, "tier": "primary"})
        lane_targets.append({"product": phrase, "subset": "", "parallel": "", "tier": "secondary"})

    def _one_query(player_name: str, extra_parallel: str) -> str:
        q = f"{player_name} {phrase}".strip()
        if fam_extra:
            q = f"{q} {fam_extra}".strip()
        if inc_tail:
            q = f"{q} {inc_tail}".strip()
        if extra_parallel:
            q = f"{q} {extra_parallel}".strip()
        if grade:
            q = f"{q} {grade}".strip()
        return " ".join(q.split())[:240].strip()

    def _finish_structured_line(base: str) -> str:
        q = str(base or "").strip()
        if fam_extra:
            q = f"{q} {fam_extra}".strip()
        if inc_tail:
            q = f"{q} {inc_tail}".strip()
        if grade:
            q = f"{q} {grade}".strip()
        return " ".join(q.split())[:240].strip()

    records = get_target_player_records(state, tid)
    out: List[Dict[str, str]] = []
    for rec in records:
        name = (rec.get("player_name") or "").strip()
        if not name:
            continue
        pid = str(rec.get("player_id") or "")

        if use_structured:
            raw_terms = build_search_terms(name, phrase)
            if raw_terms:
                expanded: List[str] = list(raw_terms)
                if append_par:
                    for t in raw_terms:
                        for par in DEFAULT_PARALLELS:
                            expanded.append(f"{t} {par}".strip())
                n_base = len(raw_terms)
                seen_q: set = set()
                for i, qraw in enumerate(expanded):
                    qf = _finish_structured_line(qraw)
                    if not qf or qf in seen_q:
                        continue
                    seen_q.add(qf)
                    if len(seen_q) > _MAX_STRUCTURED_QUERY_LINES_PER_PLAYER:
                        break
                    kind = "structured_parallel" if i >= n_base else "structured_template"
                    out.append({
                        "player_id": pid,
                        "player_name": name,
                        "query": qf,
                        "query_kind": kind,
                        "lane_tier": "secondary" if kind == "structured_parallel" else "primary",
                        "lane_product": phrase,
                        "lane_subset": "",
                        "lane_parallel": "",
                    })
                continue

        seen_q: Set[str] = set()

        def _push(_query: str, _kind: str, *, _tier: str = "primary", _product: str = "", _subset: str = "", _parallel: str = "") -> None:
            _qf = " ".join(str(_query or "").split()).strip()[:240]
            if not _qf or _qf in seen_q:
                return
            seen_q.add(_qf)
            out.append({
                "player_id": pid,
                "player_name": name,
                "query": _qf,
                "query_kind": _kind,
                "lane_tier": "secondary" if str(_tier).strip().lower() == "secondary" else "primary",
                "lane_product": str(_product or phrase).strip(),
                "lane_subset": str(_subset or "").strip(),
                "lane_parallel": str(_parallel or "").strip(),
            })

        for _lane in lane_targets[:24]:
            _product = " ".join(str(_lane.get("product") or phrase).split()).strip() or phrase
            _subset = " ".join(str(_lane.get("subset") or "").split()).strip()
            _parallel = " ".join(str(_lane.get("parallel") or "").split()).strip()
            _tier = "secondary" if str(_lane.get("tier") or "").strip().lower() == "secondary" else "primary"
            _parts = [name, _product]
            if _subset:
                _parts.append(_subset)
            if _parallel:
                _parts.append(_parallel)
            _query = _finish_structured_line(" ".join(_parts))
            _kind = "lane_product_only"
            if _subset and _parallel:
                _kind = "lane_subset_parallel"
            elif _subset:
                _kind = "lane_subset"
            elif _parallel:
                _kind = "lane_parallel"
            _push(_query, _kind, _tier=_tier, _product=_product, _subset=_subset, _parallel=_parallel)

        if (not seen_q) or broad_fallback:
            _push(_one_query(name, ""), "broad_fallback", _tier="secondary", _product=phrase)
    return out


def build_ebay_search_queries_for_target(
    state: Dict[str, Any],
    target_id: str,
    *,
    scan_options: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    First-pass eBay keywords: one query per resolved player × product phrase.
    include_terms appended; default_grade_filter appended when set.
    exclude_terms reserved for future minus-keyword behavior (not appended here).
    """
    return [s["query"] for s in build_target_scan_query_specs(state, target_id, scan_options=scan_options)]


def _dedupe_str_list(values: Any) -> List[str]:
    """
    Stable string-list normalization:
    - preserves first-seen order
    - trims whitespace
    - drops blanks / None
    - dedupes case-insensitively
    """
    out: List[str] = []
    seen: set = set()
    for raw in list(values or []):
        if raw is None:
            continue
        if isinstance(raw, str):
            text = " ".join(raw.split()).strip()
        else:
            text = " ".join(str(raw).split()).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _normalize_target_pct(raw_value: Any, *, default_value: float) -> float:
    try:
        pct = float(raw_value)
    except (TypeError, ValueError):
        return float(default_value)
    if pct > 1.0:
        pct = pct / 100.0
    if pct <= 0:
        return float(default_value)
    return max(0.05, min(0.99, float(pct)))


def _tracked_target_search_terms(player_name: str, product_keywords: List[str], card_keywords: List[str], parallel_keywords: List[str]) -> List[str]:
    terms: List[str] = []
    for _part in [player_name] + list(product_keywords or []) + list(card_keywords or []) + list(parallel_keywords or []):
        _s = " ".join(str(_part or "").split()).strip()
        if _s and _s.lower() not in {t.lower() for t in terms}:
            terms.append(_s)
    return terms[:10]


def build_tracked_scan_targets(
    state: Dict[str, Any],
    *,
    listing_mode: str = "both",
    sport_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Canonical tracked-target contract shared by auctions (Ending Soon) and BIN (Buying Radar).
    One target == one player x one product target.
    """
    ensure_buy_universe_seed(state)
    bu = state.get("buy_universe") or {}
    pt = bu.get("product_targets") or {}
    validation_mode = get_validation_mode_settings(state)
    wanted_mode = str(listing_mode or "both").strip().lower()
    wanted_sport = str(sport_filter or "").strip().upper()
    allowed_player_ids = set(validation_mode.get("allowed_player_ids") or [])
    allowed_target_ids = set(validation_mode.get("allowed_target_ids") or [])
    groups_found_count = 0
    fallback_groups_used = 0
    _nba_suppress_count = 0

    tracked: List[Dict[str, Any]] = []
    for tid_key, raw_meta in pt.items():
        if not isinstance(raw_meta, dict):
            continue
        meta = merge_product_target_defaults(str(tid_key), raw_meta)
        if not meta.get("active", True):
            continue
        target_id = str(meta.get("target_id") or tid_key)
        if allowed_target_ids and target_id not in allowed_target_ids:
            continue
        meta_eff = resolve_effective_product_target_meta(meta)
        sport = str(meta_eff.get("sport") or meta.get("sport") or "").strip().upper()
        if wanted_sport and sport and sport != wanted_sport:
            continue
        product_phrase = build_target_product_phrase(meta_eff)
        if not product_phrase:
            continue
        include_terms = [str(t).strip() for t in (meta_eff.get("include_terms") or []) if str(t).strip()]
        subset_terms = _target_subset_terms(meta_eff)
        parallel_terms = _target_parallel_terms(meta_eff)
        # ── NBA weak-product suppression gate ────────────────────────────────
        # Weak NBA product families (Hoops, Chronicles, Revolution, Court Kings, Flux)
        # generate broad product-bound scan lanes that waste budget and never survive
        # supply gates. Suppress unless the target carries an explicit premium signal.
        if sport == "NBA" and target_id in _NBA_WEAK_PRODUCT_TARGETS_SUPPRESS:
            _premium_signal = _nba_target_has_premium_signal(meta_eff, subset_terms, parallel_terms)
            if not _premium_signal:
                print(
                    f"[TARGET_PRODUCT_SUPPRESS] target_id={target_id} "
                    f"family={str(meta_eff.get('set_name') or product_phrase)[:40]} "
                    f"sport=NBA reason=weak_product_no_premium_signal"
                )
                _nba_suppress_count += 1
                continue
            print(
                f"[TARGET_PRODUCT_KEEP] target_id={target_id} "
                f"family={str(meta_eff.get('set_name') or product_phrase)[:40]} "
                f"sport=NBA signal={_premium_signal}"
            )
        # ─────────────────────────────────────────────────────────────────────
        family_terms: List[str] = []
        fid = str(meta_eff.get("product_family_id") or "").strip()
        if fid:
            _ce = get_product_family(fid)
            if _ce:
                family_terms = [str(t).strip() for t in (_ce.get("family_include_terms") or []) if str(t).strip()]
        product_keywords = _dedupe_str_list([product_phrase] + family_terms + include_terms)
        card_keywords = _dedupe_str_list(subset_terms)
        parallel_keywords = _dedupe_str_list(parallel_terms)
        allow_auction = bool(meta_eff.get("allow_auction", True))
        allow_bin = bool(meta_eff.get("allow_bin", True))
        if wanted_mode == "auction" and not allow_auction:
            continue
        if wanted_mode == "bin" and not allow_bin:
            continue
        target_bid_pct = _normalize_target_pct(
            meta_eff.get("target_bid_pct") or meta_eff.get("auction_target_pct") or meta_eff.get("target_bid_ratio"),
            default_value=DEFAULT_AUCTION_TARGET_BID_PCT,
        )
        target_buy_pct = _normalize_target_pct(
            meta_eff.get("target_buy_pct") or meta_eff.get("bin_target_pct") or meta_eff.get("target_buy_ratio"),
            default_value=DEFAULT_BIN_TARGET_BUY_PCT,
        )
        raw_group_links = list(((bu.get("target_group_links") or {}).get(target_id) or []))
        source_groups = get_target_group_ids(state, target_id)
        groups_found_count += len(source_groups)
        if source_groups and source_groups != raw_group_links:
            fallback_groups_used += 1

        for rec in get_target_player_records(state, target_id):
            player_id = str(rec.get("player_id") or "").strip()
            if allowed_player_ids and player_id not in allowed_player_ids:
                continue
            player_name = str(rec.get("player_name") or "").strip()
            if not player_name:
                continue
            tracked.append({
                "tracked_target_id": f"{target_id}:{player_id or player_name}",
                "target_id": target_id,
                "player_id": player_id,
                "player_name": player_name,
                "sport": sport,
                "product_family": str(meta_eff.get("set_name") or product_phrase).strip(),
                "product_family_id": fid,
                "product_keywords": list(product_keywords),
                "parallel_family": parallel_keywords[0] if parallel_keywords else "",
                "parallel_keywords": list(parallel_keywords),
                "card_keywords": list(card_keywords),
                "search_terms": _tracked_target_search_terms(player_name, product_keywords, card_keywords, parallel_keywords),
                "allow_auction": allow_auction,
                "allow_bin": allow_bin,
                "target_bid_pct": target_bid_pct,
                "target_buy_pct": target_buy_pct,
                "source_groups": list(source_groups),
                "target_label": str(meta_eff.get("label") or meta.get("label") or target_id),
                "target_meta": meta_eff,
                "listing_mode": wanted_mode,
            })

    if validation_mode.get("enabled"):
        _grouped: Dict[str, List[Dict[str, Any]]] = {}
        for _target in tracked:
            _grouped.setdefault(str(_target.get("player_id") or _target.get("player_name") or ""), []).append(_target)
        _player_keys = list(_grouped.keys())[: int(validation_mode.get("max_players") or 5)]
        _limited: List[Dict[str, Any]] = []
        for _pk in _player_keys:
            _limited.extend((_grouped.get(_pk) or [])[: int(validation_mode.get("max_targets_per_player") or 5)])
        tracked = _limited

    _nba_kept = sum(1 for t in tracked if str(t.get("sport") or "").upper() == "NBA")
    if _nba_suppress_count or _nba_kept:
        print(
            f"[TARGET_PRODUCT_SUMMARY] nba_suppressed={_nba_suppress_count} "
            f"nba_kept={_nba_kept} "
            f"total_before={len(tracked) + _nba_suppress_count} "
            f"total_after={len(tracked)}"
        )
    print(
        f"[TARGETS] built={len(tracked)} mode={wanted_mode} "
        f"auction={sum(1 for t in tracked if t.get('allow_auction'))} "
        f"bin={sum(1 for t in tracked if t.get('allow_bin'))} "
        f"groups={groups_found_count} fallback_targets={fallback_groups_used}"
    )

    # ── Target universe diagnostics ──────────────────────────────────────────
    _uniq_players = len({str(t.get("player_id") or t.get("player_name") or "") for t in tracked})
    _uniq_targets = len({str(t.get("target_id") or "") for t in tracked})
    _sport_counts: Dict[str, int] = {}
    for _t in tracked:
        _s = str(_t.get("sport") or "?").upper()
        _sport_counts[_s] = _sport_counts.get(_s, 0) + 1
    print(
        f"[TARGETS][UNIVERSE] players={_uniq_players} "
        f"groups={groups_found_count} targets={len(tracked)} "
        f"by_sport={_sport_counts}"
    )
    _prod_mix: Dict[str, int] = {}
    for _t in tracked:
        _fam = str(_t.get("product_family") or "").lower()
        for _kw, _lbl in (
            ("prizm", "prizm"), ("mosaic", "mosaic"), ("select", "select"),
            ("optic", "optic"), ("spectra", "spectra"), ("donruss", "donruss"),
            ("contenders", "contenders"), ("auto", "auto"),
        ):
            if _kw in _fam:
                _prod_mix[_lbl] = _prod_mix.get(_lbl, 0) + 1
                break
        else:
            _prod_mix["other"] = _prod_mix.get("other", 0) + 1
    print(f"[TARGETS][PRODUCT_MIX] {_prod_mix}")
    if tracked:
        _per_player_counts: Dict[str, int] = {}
        for _t in tracked:
            _pk = str(_t.get("player_id") or _t.get("player_name") or "")
            _per_player_counts[_pk] = _per_player_counts.get(_pk, 0) + 1
        _counts = sorted(_per_player_counts.values())
        _median = _counts[len(_counts) // 2] if _counts else 0
        print(
            f"[TARGETS][PLAYER_COVERAGE] "
            f"min_targets={_counts[0] if _counts else 0} "
            f"median_targets={_median} "
            f"max_targets={_counts[-1] if _counts else 0}"
        )

    return tracked


def build_query_specs_for_listing_mode(
    state: Dict[str, Any],
    *,
    listing_mode: str,
    sport_filter: Optional[str] = None,
    scan_options: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    tracked_targets = build_tracked_scan_targets(state, listing_mode=listing_mode, sport_filter=sport_filter)
    query_specs: List[Dict[str, Any]] = []
    grouped_targets = sum(1 for target in tracked_targets if target.get("source_groups"))
    for target in tracked_targets:
        target_id = str(target.get("target_id") or "")
        player_id = str(target.get("player_id") or "")
        for spec in build_target_scan_query_specs(state, target_id, scan_options=scan_options):
            if player_id and str(spec.get("player_id") or "") != player_id:
                continue
            merged = dict(spec or {})
            merged["tracked_target"] = dict(target)
            merged["listing_mode"] = str(listing_mode or "").strip().lower()
            merged["allow_auction"] = bool(target.get("allow_auction"))
            merged["allow_bin"] = bool(target.get("allow_bin"))
            merged["target_bid_pct"] = float(target.get("target_bid_pct") or DEFAULT_AUCTION_TARGET_BID_PCT)
            merged["target_buy_pct"] = float(target.get("target_buy_pct") or DEFAULT_BIN_TARGET_BUY_PCT)
            query_specs.append(merged)
    print(
        f"[TARGETS] query_specs mode={listing_mode} count={len(query_specs)} "
        f"tracked_targets={len(tracked_targets)} grouped_targets={grouped_targets}"
    )
    return query_specs


def listing_matches_tracked_target(title: str, tracked_target: Dict[str, Any]) -> Dict[str, Any]:
    nt = normalize_title_for_match(title)
    _norm_title = _normalize_player_match_text(title)
    _norm_product_title = _normalize_product_match_text(title)
    _norm_parallel_title = _normalize_parallel_match_text(title)
    _target_parallel_text = " | ".join(str(t or "") for t in (tracked_target.get("parallel_keywords") or []) if str(t or "").strip())
    result = {
        "ok": False,
        "reason": "empty_title",
        "entity_match_status": "NO_MATCH",
        "entity_match_score": 0.0,
        "alias_soft_match": False,
        "player_match": False,
        "product_match": False,
        "parallel_match": False,
        "target_player_norm": _normalize_player_match_text(str(tracked_target.get("player_name") or "")),
        "row_player_norm": _norm_title,
        "player_match_reason": "",
        "product_match_reason": "",
        "parallel_match_reason": "",
        "row_product_norm": _norm_product_title,
        "row_parallel_norm": _norm_parallel_title,
    }
    if not nt:
        return result

    player_id = str(tracked_target.get("player_id") or "").strip()
    seed = players_by_id().get(player_id) if player_id else None
    if not seed and str(tracked_target.get("player_name") or "").strip():
        seed = {
            "player_name": str(tracked_target.get("player_name") or "").strip(),
            "match_tokens": [str(tracked_target.get("player_name") or "").strip()],
            "search_query_hint": str(tracked_target.get("player_name") or "").strip(),
        }
    if seed:
        entity_status, entity_score, entity_reason = classify_target_player_match(_norm_title, seed)
        result["entity_match_status"] = entity_status
        result["entity_match_score"] = entity_score
        result["player_match_reason"] = str(entity_reason or "")
        result["alias_soft_match"] = str(entity_reason or "") == "duplicate_alias_noise"
        if entity_status == "NO_MATCH":
            result["reason"] = entity_reason
            _log_player_match_sample(
                title=title,
                target_name=str(tracked_target.get("player_name") or (seed or {}).get("player_name") or ""),
                row_player_norm=_norm_title,
                target_player_norm=result["target_player_norm"],
                reason=str(entity_reason or "player_mismatch"),
            )
            return result
        if player_id and other_hub_players_in_title(_norm_title, player_id):
            result["reason"] = "conflicting_seed_player"
            _log_player_match_sample(
                title=title,
                target_name=str(tracked_target.get("player_name") or (seed or {}).get("player_name") or ""),
                row_player_norm=_norm_title,
                target_player_norm=result["target_player_norm"],
                reason="conflicting_seed_player",
            )
            return result
        result["player_match"] = True
    elif player_id:
        result["reason"] = "unknown_player_seed"
        _log_player_match_sample(
            title=title,
            target_name=str(tracked_target.get("player_name") or ""),
            row_player_norm=_norm_title,
            target_player_norm=result["target_player_norm"],
            reason="unknown_player_seed",
        )
        return result

    ok_prod, prod_reason = listing_matches_product_target(nt, tracked_target.get("target_meta") or {})
    result["product_match_reason"] = str(prod_reason or "")
    if not ok_prod:
        result["reason"] = prod_reason
        _log_product_parallel_match_sample(
            channel="PRODUCT_MATCH",
            title=title,
            target_name=str(tracked_target.get("player_name") or ""),
            target_product=str((tracked_target.get("target_meta") or {}).get("set_name") or tracked_target.get("product_family") or ""),
            target_parallel=_target_parallel_text,
            row_norm=_norm_product_title,
            reason=str(prod_reason or "family_exact_miss"),
        )
        return result
    result["product_match"] = True

    parallel_keywords = [str(t) for t in (tracked_target.get("parallel_keywords") or []) if str(t).strip()]
    _ok_parallel, _parallel_reason = _row_matches_target_parallel(_norm_parallel_title, parallel_keywords)
    result["parallel_match_reason"] = str(_parallel_reason or "")
    if not _ok_parallel:
        result["reason"] = "parallel_mismatch"
        _log_product_parallel_match_sample(
            channel="PARALLEL_MATCH",
            title=title,
            target_name=str(tracked_target.get("player_name") or ""),
            target_product=str((tracked_target.get("target_meta") or {}).get("set_name") or tracked_target.get("product_family") or ""),
            target_parallel=_target_parallel_text,
            row_norm=_norm_parallel_title,
            reason=str(_parallel_reason or "parallel_missing"),
        )
        return result
    result["parallel_match"] = True

    result["ok"] = True
    result["reason"] = "ok"
    return result


def compute_target_action_prices(row: Dict[str, Any], tracked_target: Dict[str, Any], *, listing_mode: str = "both") -> Dict[str, Any]:
    market_value = row.get("market_value")
    try:
        market_value_float = float(market_value) if market_value is not None else None
    except (TypeError, ValueError):
        market_value_float = None
    bid_pct = float(tracked_target.get("target_bid_pct") or DEFAULT_AUCTION_TARGET_BID_PCT)
    buy_pct = float(tracked_target.get("target_buy_pct") or DEFAULT_BIN_TARGET_BUY_PCT)
    return {
        "target_bid_pct": bid_pct,
        "target_buy_pct": buy_pct,
        "target_bid_price": round(market_value_float * bid_pct, 2) if market_value_float is not None else None,
        "target_buy_price": round(market_value_float * buy_pct, 2) if market_value_float is not None else None,
        "target_price_mode": str(listing_mode or "both").strip().lower(),
    }


def upsert_product_target(state: Dict[str, Any], target_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    """Create or update a product target (normalized, merged with seed defaults if applicable)."""
    ensure_buy_universe_seed(state)
    bu = state["buy_universe"]
    tid = sanitize_target_id(target_id) or str(target_id).strip()
    if not tid:
        return state
    cur = bu["product_targets"].get(tid)
    base = dict(cur) if isinstance(cur, dict) else {}
    base.update(fields or {})
    base["target_id"] = tid
    bu["product_targets"][tid] = merge_product_target_defaults(tid, base)
    bu.setdefault("target_group_links", {})
    if tid not in bu["target_group_links"]:
        bu["target_group_links"][tid] = []
    return state


def delete_product_target(state: Dict[str, Any], target_id: str) -> Dict[str, Any]:
    ensure_buy_universe_seed(state)
    bu = state["buy_universe"]
    tid = str(target_id)
    bu.get("product_targets", {}).pop(tid, None)
    bu.get("target_group_links", {}).pop(tid, None)
    bu.get("target_latest_run_by_target", {}).pop(tid, None)
    return state


def _browse_item_id_key(item: Dict[str, Any]) -> str:
    item = item or {}
    iid = str(item.get("itemId") or "").strip()
    if iid:
        return f"id:{iid}"
    url = (item.get("itemWebUrl") or "").strip().lower()
    if url:
        return f"url:{url}"
    return f"t:{hash(str(item.get('title') or '')[:120])}"


def _browse_item_price(item: Dict[str, Any]) -> float:
    item = item or {}
    for key in ("price", "currentBidPrice", "bidPrice", "convertedCurrentBidPrice"):
        c = item.get(key)
        if isinstance(c, dict):
            v = c.get("value")
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    cp = item.get("currentPrice")
    if isinstance(cp, dict):
        try:
            return float(cp.get("value"))
        except (TypeError, ValueError):
            pass
    return 0.0


def _browse_thumbnail_url(item: Dict[str, Any]) -> str:
    item = item or {}
    im = item.get("image") or {}
    u = (im.get("imageUrl") or "").strip()
    if u:
        return u
    thumbs = item.get("thumbnailImages") or []
    if thumbs and isinstance(thumbs, list) and thumbs:
        return (thumbs[0].get("imageUrl") or "").strip()
    return ""


def _phrase_match_score(title: str, phrase_lower: str) -> int:
    if not phrase_lower or not title:
        return 0
    t = title.lower()
    toks = [x for x in phrase_lower.split() if len(x) > 1]
    return sum(1 for tok in toks if tok in t)


def _sale_priority_sort(item: Dict[str, Any]) -> int:
    opts = item.get("buyingOptions") or []
    if isinstance(opts, str):
        opts = [opts]
    u = [str(o).upper() for o in opts if o]
    if "FIXED_PRICE" in u:
        return 0
    if "AUCTION" in u:
        return 1
    return 2


# --- Card target scan: strict title validation (player + product). Accuracy > volume. ---

_NAME_SUFFIX_TOKENS = frozenset(
    {"jr", "sr", "jr.", "sr.", "ii", "iii", "iv", "v", "ii.", "iii.", "iv."}
)
_MIN_CONFLICT_TOKEN_LEN = 5
_PLAYER_MATCH_DEBUG_LIMIT = 12
_PLAYER_MATCH_DEBUG_EMITTED = 0


def normalize_title_for_match(text: str) -> str:
    """
    Lowercase, drop most punctuation, collapse whitespace — for substring checks on listing titles.
    Explainable; not fuzzy/phonetic.
    """
    t = (text or "").lower()
    t = t.replace("’", "'")
    t = re.sub(r"[.,#|/+]", " ", t)
    t = re.sub(r"[^\w\s'-]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _normalize_player_match_text(text: str) -> str:
    t = normalize_title_for_match(text)
    t = re.sub(r"'s\b", "", t)
    t = t.replace("-", " ").replace("'", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _player_tokens(text: str) -> List[str]:
    return [tok for tok in _normalize_player_match_text(text).split() if tok]


def _ordered_token_match(title_tokens: List[str], alias_tokens: List[str]) -> bool:
    if not alias_tokens:
        return False
    _pos = 0
    for _want in alias_tokens:
        try:
            _idx = title_tokens.index(_want, _pos)
        except ValueError:
            return False
        _pos = _idx + 1
    return True


def _log_player_match_sample(*, title: str, target_name: str, row_player_norm: str, target_player_norm: str, reason: str) -> None:
    global _PLAYER_MATCH_DEBUG_EMITTED
    if _PLAYER_MATCH_DEBUG_EMITTED >= _PLAYER_MATCH_DEBUG_LIMIT:
        return
    _PLAYER_MATCH_DEBUG_EMITTED += 1
    print(
        f"[ES][PLAYER_MATCH] reject title=\"{str(title or '')[:96]}\" "
        f"target=\"{str(target_name or '')[:48]}\" "
        f"row_player_norm=\"{row_player_norm[:64]}\" "
        f"target_player_norm=\"{target_player_norm[:64]}\" "
        f"reason=\"{str(reason or '')[:48]}\""
    )


def _normalize_product_match_text(text: str) -> str:
    t = normalize_title_for_match(text)
    t = t.replace("-", " ").replace("/", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _normalize_parallel_match_text(text: str) -> str:
    t = _normalize_product_match_text(text)
    t = re.sub(r"\bnumbered\b", " serial ", t)
    t = re.sub(r"\bno\b", " number ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _normalize_subset_binding_name(text: str) -> str:
    t = str(text or "").strip().lower().replace("_", " ").replace("-", " ")
    t = re.sub(r"[^a-z0-9\s]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _subset_product_ecosystem(subset_name: str) -> Dict[str, Any]:
    subset_norm = _normalize_subset_binding_name(subset_name)
    _mapping: Dict[str, Dict[str, Any]] = {
        "kaboom": {
            "canonical_products": ["absolute"],
            "accepted_product_aliases": ["absolute", "panini absolute"],
            "loose_binding_allowed": True,
            "exact_binding_required": False,
        },
        "downtown": {
            "canonical_products": ["donruss", "donruss optic"],
            "accepted_product_aliases": ["donruss", "donruss optic", "optic", "panini donruss", "panini donruss optic"],
            "loose_binding_allowed": True,
            "exact_binding_required": False,
        },
        "color blast": {
            "canonical_products": ["prizm", "select"],
            "accepted_product_aliases": ["prizm", "panini prizm", "select", "panini select"],
            "loose_binding_allowed": False,
            "exact_binding_required": True,
        },
        "stained glass": {
            "canonical_products": ["mosaic", "select"],
            "accepted_product_aliases": ["mosaic", "panini mosaic", "select", "panini select"],
            "loose_binding_allowed": False,
            "exact_binding_required": True,
        },
        "manga": {
            "canonical_products": ["prizm", "select"],
            "accepted_product_aliases": ["prizm", "panini prizm", "select", "panini select"],
            "loose_binding_allowed": False,
            "exact_binding_required": True,
        },
    }
    _entry = dict(_mapping.get(subset_norm) or {})
    _canon = [_normalize_product_match_text(v) for v in list(_entry.get("canonical_products") or []) if str(v).strip()]
    _canon = [v for v in _canon if v]
    _aliases = [_normalize_product_match_text(v) for v in list(_entry.get("accepted_product_aliases") or []) if str(v).strip()]
    _aliases = [v for v in _aliases if v]
    return {
        "subset_name": subset_norm,
        "canonical_products": _dedupe_str_list(_canon),
        "accepted_product_aliases": _dedupe_str_list(_canon + _aliases),
        "loose_binding_allowed": bool(_entry.get("loose_binding_allowed")),
        "exact_binding_required": bool(_entry.get("exact_binding_required")),
    }


def _subset_product_display_name(products: List[str]) -> str:
    _vals = [str(v or "").strip().title() for v in list(products or []) if str(v or "").strip()]
    return " / ".join(_vals)


def _normalize_query_slot_token(text: str) -> str:
    _raw = str(text or "").strip().lower().replace("-", " ").replace("/", " ")
    _raw = re.sub(r"[^a-z0-9\s]+", " ", _raw)
    return " ".join(_raw.split())


def _parallel_query_slot_family(parallel: str, lane_type: str = "") -> str:
    _parallel = _normalize_query_slot_token(parallel)
    _lane_type = _normalize_query_slot_token(lane_type)
    if "auto" in _parallel or _lane_type == "auto":
        return "auto"
    if "superfractor" in _parallel:
        return "superfractor"
    if "gold vinyl" in _parallel:
        return "gold_vinyl"
    if any(_tok in _parallel for _tok in ("genesis", "honeycomb", "zebra", "nebula", "black finite")):
        return _parallel.replace(" ", "_")
    if "gold" in _parallel:
        return "gold"
    if any(_tok in _parallel for _tok in ("silver", "refractor", "holo", "chrome")):
        return "chrome_silver"
    if any(_tok in _parallel for _tok in ("numbered", "/")) or _lane_type == "serial parallel":
        return "serial_numbered"
    if _parallel:
        return _parallel.replace(" ", "_")
    if _lane_type:
        return _lane_type.replace(" ", "_")
    return "product"


def build_query_slot_signature(spec: Dict[str, Any]) -> Dict[str, str]:
    _spec = dict(spec or {})
    _meta = resolve_effective_product_target_meta(dict(_spec.get("target_meta") or {}))
    _sport = str(_spec.get("sport") or _meta.get("sport") or "").strip().upper()
    _player = str(_spec.get("player_id") or _spec.get("player_name") or "").strip().lower()
    _lane_type = _normalize_query_slot_token(str(_spec.get("target_lane_type") or _spec.get("query_kind") or ""))
    _subset = _normalize_subset_binding_name(
        str(_spec.get("lane_subset") or _spec.get("subset_name") or _meta.get("subset_name") or "")
    )
    _product = _normalize_query_slot_token(
        str(
            _spec.get("subset_product_family")
            or _meta.get("subset_product_family")
            or _spec.get("lane_product")
            or _spec.get("target_product_family")
            or _meta.get("set_name")
            or ""
        )
    )
    _rarity_class = _normalize_query_slot_token(
        str(
            _spec.get("lane_subset_rarity_tier")
            or _meta.get("rarity_tier")
            or ("endgame" if _lane_type in {"ssp case hit", "premium subset"} else "")
            or ("premium_secondary" if _lane_type in {"premium parallel", "serial parallel", "auto"} else "")
            or _lane_type
            or "premium"
        )
    ).replace(" ", "_")

    if _subset:
        _subset_ecosystem = _subset_product_ecosystem(_subset)
        _canon = [
            _normalize_query_slot_token(_p).replace(" ", "_")
            for _p in list(_subset_ecosystem.get("canonical_products") or [])
            if _normalize_query_slot_token(_p)
        ]
        _product_ecosystem = _canon[0] if _canon else _product.replace(" ", "_")
        _intent_type = "subset"
        _intent_label = _subset.replace(" ", "_")
        if not _rarity_class or _rarity_class == "premium":
            _rarity_class = str(_subset_ecosystem.get("rarity_tier") or "premium").strip().lower().replace(" ", "_")
    else:
        _product_ecosystem = _product.replace(" ", "_")
        _intent_type = "parallel" if str(_spec.get("lane_parallel") or "").strip() else "product"
        _intent_label = _parallel_query_slot_family(str(_spec.get("lane_parallel") or ""), lane_type=_lane_type)

    _player_key = f"{_sport}|{_player}" if _sport else _player
    _signature = "|".join([
        _player_key or "unknown_player",
        _intent_type or "intent",
        _intent_label or "generic",
        _product_ecosystem or "unknown_product",
        _rarity_class or "premium",
    ])
    _intent_key = "|".join([_intent_type or "intent", _intent_label or "generic", _rarity_class or "premium"])
    _exposure_key = "|".join([_product_ecosystem or "unknown_product", _intent_type or "intent", _intent_label or "generic"])
    return {
        "signature": _signature,
        "player_key": _player_key,
        "product_ecosystem": _product_ecosystem or "unknown_product",
        "intent_type": _intent_type or "product",
        "intent_label": _intent_label or "generic",
        "intent_key": _intent_key,
        "exposure_key": _exposure_key,
        "rarity_class": _rarity_class or "premium",
    }


def _apply_subset_product_binding(target_meta: Dict[str, Any], *, lane_subset: str = "", lane_product: str = "") -> Dict[str, Any]:
    _meta = resolve_effective_product_target_meta(target_meta or {})
    _subset = _normalize_subset_binding_name(lane_subset or _meta.get("subset_name") or "")
    _ecosystem = _subset_product_ecosystem(_subset)
    _canon = list(_ecosystem.get("canonical_products") or [])
    if not _subset or not _canon:
        return _meta
    _bound = dict(_meta)
    _bound["subset_name"] = _subset
    _bound["subset_binding_override"] = True
    _bound["subset_product_family"] = _subset_product_display_name(_canon) or str(_bound.get("set_name") or "").strip()
    _bound["subset_product_family_canonical"] = list(_canon)
    _bound["subset_product_aliases"] = list(_ecosystem.get("accepted_product_aliases") or [])
    _bound["subset_binding_loose_allowed"] = bool(_ecosystem.get("loose_binding_allowed"))
    _bound["subset_binding_exact_required"] = bool(_ecosystem.get("exact_binding_required"))
    _bound["inherited_target_product"] = str(_bound.get("set_name") or lane_product or "").strip()
    _bound["set_name"] = str(_canon[0]).title()
    _include_terms = [str(v).strip() for v in list(_bound.get("include_terms") or []) if str(v).strip()]
    _bound["include_terms"] = _dedupe_str_list(list(_ecosystem.get("accepted_product_aliases") or []) + _include_terms)
    _bound["default_query_phrase"] = str(_bound.get("default_query_phrase") or _bound.get("set_name") or "").strip()
    return _bound


def _subset_binding_aliases(target_meta: Dict[str, Any]) -> List[str]:
    _meta = target_meta or {}
    if not bool(_meta.get("subset_binding_override")):
        return []
    _aliases: List[str] = []
    for _cand in list(_meta.get("subset_product_family_canonical") or []) + list(_meta.get("subset_product_aliases") or []) + [str(_meta.get("subset_product_family") or "")]:
        _norm = _normalize_product_match_text(_cand)
        if _norm and _norm not in _aliases:
            _aliases.append(_norm)
    return _aliases


def _product_family_aliases(target_meta: Dict[str, Any]) -> List[str]:
    _meta = resolve_effective_product_target_meta(target_meta or {})
    _aliases: List[str] = []
    for _cand in list(_subset_binding_aliases(_meta)) + [
        str(_meta.get("set_name") or ""),
        str(_meta.get("brand") or ""),
        f"{str(_meta.get('brand') or '').strip()} {str(_meta.get('set_name') or '').strip()}".strip(),
        str(_meta.get("default_query_phrase") or ""),
        str(_meta.get("product_family_label") or ""),
        str(_meta.get("product_family_id") or "").replace("_", " "),
    ] + [str(x) for x in (_meta.get("family_include_terms") or [])]:
        _norm = _normalize_product_match_text(_cand)
        if _norm and _norm not in _aliases:
            _aliases.append(_norm)
    return _aliases


def _parallel_aliases(parallel_keywords: List[str]) -> List[str]:
    _aliases: List[str] = []
    _synonyms = {
        "silver": ["silver", "silver prizm", "prizm silver", "holo", "refractor"],
        "holo": ["holo", "silver", "refractor"],
        "refractor": ["refractor", "holo", "silver"],
        "x fractor": ["x fractor", "xfractor"],
        "xfractor": ["x fractor", "xfractor"],
        "zebra": ["zebra", "zebra prizm"],
        "gold": ["gold", "gold prizm"],
        "mojo": ["mojo"],
        "wave": ["wave"],
        "cracked ice": ["cracked ice", "ice"],
        "fluorescent": ["fluorescent"],
        "disco": ["disco"],
        "serial": ["serial", "numbered", "number", "/"],
    }
    for _raw in list(parallel_keywords or []):
        _norm = _normalize_parallel_match_text(str(_raw or ""))
        if not _norm:
            continue
        _expanded = [_norm]
        for _key, _vals in _synonyms.items():
            if _key in _norm:
                _expanded.extend(_vals)
        if re.search(r"/\s*\d+", _norm) or re.search(r"\b\d+\b", _norm):
            _expanded.extend([_norm.replace("/", " "), _norm, "serial", "numbered"])
        for _cand in _expanded:
            _cand_norm = _normalize_parallel_match_text(_cand)
            if _cand_norm and _cand_norm not in _aliases:
                _aliases.append(_cand_norm)
    return _aliases


def _row_matches_target_product_family(norm_title: str, target_meta: Dict[str, Any]) -> Tuple[bool, str]:
    if not norm_title:
        return False, "empty_title"
    _title_norm = _normalize_product_match_text(norm_title)
    _title_tokens = set(_title_norm.split())
    _meta = resolve_effective_product_target_meta(target_meta or {})
    _subset_name = _normalize_subset_binding_name(str(_meta.get("subset_name") or ""))
    _subset_override = bool(_meta.get("subset_binding_override")) and bool(_subset_name)
    _subset_canonical = _subset_product_display_name(list(_meta.get("subset_product_family_canonical") or [])) or str(_meta.get("subset_product_family") or "").strip()
    _subset_item = str(_meta.get("_log_item_id") or _meta.get("item_id") or "")
    _brand = _normalize_product_match_text(str(_meta.get("brand") or ""))
    _set_name = _normalize_product_match_text(str(_meta.get("set_name") or ""))
    _aliases = _product_family_aliases(_meta)

    if _subset_override:
        _matched_alias = ""
        for _alias in _subset_binding_aliases(_meta):
            _alias_tokens = [tok for tok in _alias.split() if len(tok) >= 3]
            if not _alias_tokens:
                continue
            if _ordered_token_match(list(_title_tokens), _alias_tokens) or all(tok in _title_tokens for tok in _alias_tokens):
                _matched_alias = _alias
                break
        if _matched_alias:
            print(
                f"[SUBSET_PRODUCT_MATCH] item={_subset_item or '?'} subset={_subset_name or 'none'} "
                f"canonical={(_subset_canonical or 'none').lower()} decision=pass reason=subset_ecosystem_alias"
            )
            return True, "subset_ecosystem_alias"
        _conflicts = _catalog_family_conflict_tokens(_meta)
        _conflict_hit = next((_conflict for _conflict in _conflicts if _conflict and _conflict in _title_norm), "")
        if _conflict_hit:
            print(
                f"[SUBSET_PRODUCT_MATCH] item={_subset_item or '?'} subset={_subset_name or 'none'} "
                f"canonical={(_subset_canonical or 'none').lower()} decision=reject reason=off_target_subset_family:{_conflict_hit.replace(' ', '_')}"
            )
            return False, f"off_target_subset_family:{_conflict_hit.replace(' ', '_')}"
        if bool(_meta.get("subset_binding_loose_allowed")):
            print(
                f"[SUBSET_PRODUCT_MATCH] item={_subset_item or '?'} subset={_subset_name or 'none'} "
                f"canonical={(_subset_canonical or 'none').lower()} decision=pass reason=subset_loose_binding"
            )
            return True, "subset_loose_binding"
        print(
            f"[SUBSET_PRODUCT_MATCH] item={_subset_item or '?'} subset={_subset_name or 'none'} "
            f"canonical={(_subset_canonical or 'none').lower()} decision=reject reason=subset_product_miss"
        )
        return False, "subset_product_miss"

    _set_tokens = [tok for tok in _set_name.split() if len(tok) >= 3]
    _alias_token_hits = 0
    for _alias in _aliases:
        _alias_tokens = [tok for tok in _alias.split() if len(tok) >= 3]
        if not _alias_tokens:
            continue
        if _ordered_token_match(list(_title_tokens), _alias_tokens) or all(tok in _title_tokens for tok in _alias_tokens):
            _alias_token_hits += 1
            if len(_alias_tokens) >= 2:
                return True, "family_alias_phrase"
    if _set_tokens and all(tok in _title_tokens for tok in _set_tokens):
        return True, "set_token_match"
    if _brand and _set_tokens and _brand in _title_norm and any(tok in _title_tokens for tok in _set_tokens):
        return True, "brand_plus_set_token"
    if _alias_token_hits > 0:
        return True, "family_alias_token"
    return False, "family_exact_miss"


def _row_matches_target_parallel(norm_title: str, parallel_keywords: List[str]) -> Tuple[bool, str]:
    _aliases = _parallel_aliases(parallel_keywords)
    if not _aliases:
        return True, "parallel_not_required"
    _title_norm = _normalize_parallel_match_text(norm_title)
    _title_tokens = set(_title_norm.split())
    for _alias in _aliases:
        if not _alias:
            continue
        if _alias == "/" and re.search(r"/\s*\d+", norm_title):
            return True, "serial_number_match"
        if _alias in _title_norm:
            return True, "parallel_alias_phrase"
        _alias_tokens = [tok for tok in _alias.split() if tok]
        if _alias_tokens and all(tok in _title_tokens for tok in _alias_tokens):
            return True, "parallel_alias_tokens"
    return False, "parallel_missing"


def _log_product_parallel_match_sample(*, channel: str, title: str, target_name: str, target_product: str, target_parallel: str, row_norm: str, reason: str) -> None:
    global _PLAYER_MATCH_DEBUG_EMITTED
    if _PLAYER_MATCH_DEBUG_EMITTED >= _PLAYER_MATCH_DEBUG_LIMIT:
        return
    _PLAYER_MATCH_DEBUG_EMITTED += 1
    print(
        f"[ES][{channel}] reject title=\"{str(title or '')[:96]}\" "
        f"target=\"{str(target_name or '')[:42]}\" "
        f"target_product=\"{str(target_product or '')[:42]}\" "
        f"target_parallel=\"{str(target_parallel or '')[:32]}\" "
        f"row_norm=\"{row_norm[:72]}\" "
        f"reason=\"{str(reason or '')[:48]}\""
    )


def _strip_name_suffix_tokens(phrase: str) -> str:
    parts = phrase.strip().split()
    while parts:
        p = parts[-1].lower().rstrip(".")
        if p in _NAME_SUFFIX_TOKENS or (p in ("jr", "sr") and len(parts) > 1):
            parts.pop()
            continue
        break
    return " ".join(parts).strip()


def _entity_alias_phrases(seed_row: Dict[str, Any]) -> List[str]:
    _name_raw = str(seed_row.get("player_name") or "").strip()
    _aliases: List[str] = []
    for _cand in [_name_raw, _strip_name_suffix_tokens(_name_raw), str(seed_row.get("search_query_hint") or "")] + [str(x) for x in (seed_row.get("match_tokens") or [])]:
        _norm = _normalize_player_match_text(_cand)
        if not _norm:
            continue
        if _norm not in _aliases:
            _aliases.append(_norm)
    return _aliases


def _negative_alias_conflict(norm_title: str, seed_row: Dict[str, Any]) -> str:
    _name_raw = str(seed_row.get("player_name") or "").strip()
    _core = _normalize_player_match_text(_strip_name_suffix_tokens(_name_raw))
    _tokens = [t for t in _core.split() if t]
    if len(_tokens) < 2:
        return ""
    _first_token = _tokens[0]
    _last_token = _tokens[-1]
    _first = re.escape(_first_token)
    _last = re.escape(_last_token)
    _alias_first_tokens: Set[str] = {_first_token}
    for _alias in _entity_alias_phrases(seed_row):
        _parts = [p for p in _alias.split() if p]
        if len(_parts) < 2:
            continue
        if _parts[-1] != _last_token:
            continue
        _alias_first_tokens.add(_parts[0])

    def _duplicate_alias_noise(_middle_token: str) -> bool:
        _middle = str(_middle_token or "").strip().lower()
        if not _middle or _middle not in _alias_first_tokens:
            return False
        _player_id = str(seed_row.get("player_id") or seed_row.get("id") or "").strip()
        if _player_id and other_hub_players_in_title(norm_title, _player_id):
            return False
        return True

    _forward = re.search(rf"\b{_first}\s+([a-z]{{2,}})\s+{_last}\b", norm_title)
    if _forward:
        if f"{_first_token} {_last_token}" not in norm_title:
            if _duplicate_alias_noise(_forward.group(1)):
                return "duplicate_alias_noise"
            return "negative_alias_conflict"
    _reverse = re.search(rf"\b([a-z]{{2,}})\s+{_last}\s+{_first}\b", norm_title)
    if _reverse:
        if f"{_last_token} {_first_token}" not in norm_title:
            if _duplicate_alias_noise(_reverse.group(1)):
                return "duplicate_alias_noise"
            return "negative_alias_conflict"
    return ""


def _name_token_parts(seed_row: Dict[str, Any]) -> Tuple[str, str]:
    _name_raw = str(seed_row.get("player_name") or "").strip()
    _core = _normalize_player_match_text(_strip_name_suffix_tokens(_name_raw))
    _tokens = [t for t in _core.split() if t]
    if not _tokens:
        return "", ""
    if len(_tokens) == 1:
        return _tokens[0], _tokens[0]
    return _tokens[0], _tokens[-1]


def classify_target_player_match(norm_title: str, seed_row: Dict[str, Any]) -> Tuple[str, float, str]:
    """
    Tiered entity gate used by premium feed validation.
    Returns (status, score, reason) where status is one of:
    EXACT_MATCH, STRONG_MATCH, WEAK_MATCH, NO_MATCH.
    """
    if not norm_title:
        return "NO_MATCH", 0.0, "empty_title"
    _norm_title = _normalize_player_match_text(norm_title)
    _bounded_title = f" {_norm_title} "
    _title_tokens = _player_tokens(_norm_title)
    _first, _last = _name_token_parts(seed_row)
    if not _first or not _last:
        return "NO_MATCH", 0.0, "unknown_player_seed"

    _neg = _negative_alias_conflict(_norm_title, seed_row)
    if _neg:
        if _neg == "duplicate_alias_noise":
            print(
                f"[PLAYER_ALIAS_SOFTMATCH] title={str(norm_title or '')[:96]} "
                f"target={str(seed_row.get('player_name') or '')[:42]} reason=duplicate_alias_noise"
            )
            return "STRONG_MATCH", 0.94, "duplicate_alias_noise"
        return "NO_MATCH", 0.0, _neg

    _aliases = _entity_alias_phrases(seed_row)
    for _alias in _aliases:
        _parts = [p for p in _alias.split() if p]
        if len(_parts) < 2:
            continue
        if f" {_alias} " in _bounded_title:
            return "EXACT_MATCH", 1.0, "canonical_alias_phrase"
        if _ordered_token_match(_title_tokens, _parts):
            return "STRONG_MATCH", 0.96, "ordered_alias_tokens"
        if all(_part in _title_tokens for _part in _parts):
            return "STRONG_MATCH", 0.91, "alias_token_set"

    _reverse = f"{_last} {_first}".strip()
    if (
        len(_reverse.split()) >= 2
        and f" {_reverse} " in _bounded_title
        and not re.search(rf"\b[a-z]{{2,}}\s+{re.escape(_last)}\s+{re.escape(_first)}\b", _norm_title)
    ):
        return "STRONG_MATCH", 0.93, "reverse_name_phrase"

    _initial_last = f"{_first[:1]} {_last}".strip()
    if len(_last) >= 3 and f" {_initial_last} " in _bounded_title:
        return "STRONG_MATCH", 0.88, "initial_last_phrase"

    _tokens = {t for t in _title_tokens if t}
    _first_present = _first in _tokens
    _last_present = _last in _tokens
    if _first_present and _last_present:
        return "STRONG_MATCH", 0.84, "first_last_tokens"

    _best_ratio = 0.0
    for _alias in _aliases:
        _parts = [p for p in _alias.split() if p]
        if len(_parts) < 2:
            continue
        _ratio = SequenceMatcher(None, _norm_title, _alias).ratio()
        if _ratio > _best_ratio:
            _best_ratio = _ratio
    if _best_ratio >= 0.92:
        return "STRONG_MATCH", round(_best_ratio, 3), "high_fuzzy_similarity"

    if _last_present and len(_last) >= 4:
        return "WEAK_MATCH", 0.54, "last_name_only"

    return "NO_MATCH", max(0.0, round(_best_ratio, 3)), "player_mismatch"


def listing_matches_target_player(norm_title: str, seed_row: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Intended player must appear as a canonical or multi-token alias phrase.
    Premium feed validation intentionally rejects weak surname-only matches.
    """
    _status, _score, _reason = classify_target_player_match(norm_title, seed_row)
    return _status != "NO_MATCH", (_reason if _status == "NO_MATCH" else _status.lower())


def other_hub_players_in_title(norm_title: str, intended_player_id: str) -> List[str]:
    """
    Other hub-seed players whose display name or a long match_token appears in the title.
    Used to reject wrong-player SERP noise (e.g. Alex Freeland when scanning Paul Skenes).
    """
    ip = str(intended_player_id)
    found: List[str] = []
    seeds = players_by_id()
    _title_tokens = _player_tokens(norm_title)
    _intended_seed = seeds.get(ip) or {}
    _intended_name = _normalize_player_match_text(str(_intended_seed.get("player_name") or ""))
    _intended_core = _normalize_player_match_text(_strip_name_suffix_tokens(str(_intended_seed.get("player_name") or "")))
    for pid, row in seeds.items():
        if str(pid) == ip:
            continue
        _row_name = _normalize_player_match_text(str(row.get("player_name") or ""))
        _row_core = _normalize_player_match_text(_strip_name_suffix_tokens(str(row.get("player_name") or "")))
        if (_intended_name and _row_name == _intended_name) or (_intended_core and _row_core == _intended_core):
            continue
        pn = _normalize_player_match_text(str(row.get("player_name") or ""))
        _pn_tokens = [t for t in pn.split() if t]
        if pn and len(_pn_tokens) >= 2 and _ordered_token_match(_title_tokens, _pn_tokens):
            found.append(str(pid))
            continue
        pnc = _normalize_player_match_text(_strip_name_suffix_tokens(str(row.get("player_name") or "")))
        _pnc_tokens = [t for t in pnc.split() if t]
        if pnc and len(_pnc_tokens) >= 2 and _ordered_token_match(_title_tokens, _pnc_tokens):
            found.append(str(pid))
            continue
        for tok in row.get("match_tokens") or []:
            t = _normalize_player_match_text(str(tok))
            _tok_parts = [p for p in t.split() if p]
            if len(_tok_parts) < 2:
                continue
            if _ordered_token_match(_title_tokens, _tok_parts):
                found.append(str(pid))
                break
    return found


def _catalog_family_conflict_tokens(target_meta: Dict[str, Any]) -> List[str]:
    _meta = resolve_effective_product_target_meta(target_meta or {})
    _sport = str(_meta.get("sport") or "").strip().upper()
    _target_set = _normalize_product_match_text(str(_meta.get("set_name") or ""))
    _allowed = set(_subset_binding_aliases(_meta))
    _conflicts: List[str] = []
    for _row in PRODUCT_FAMILY_CATALOG:
        if str(_row.get("sport") or "").strip().upper() != _sport:
            continue
        _set_name = _normalize_product_match_text(str(_row.get("set_name") or ""))
        if not _set_name or _set_name == _target_set:
            continue
        if _set_name in _allowed or any(_set_name in _alias or _alias in _set_name for _alias in _allowed):
            continue
        _conflicts.append(_set_name)
    return _conflicts


def listing_matches_product_target(norm_title: str, target_meta: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Require target year, brand/product-family alignment, approved subset/lane alignment,
    and reject obvious off-target product families before valuation.
    """
    if not norm_title:
        return False, "empty_title"
    _meta = resolve_effective_product_target_meta(target_meta)
    _norm_product_title = _normalize_product_match_text(norm_title)
    ry = target_meta.get("release_year")
    if ry is not None:
        try:
            ys = str(int(ry))
        except (TypeError, ValueError):
            ys = ""
        if ys and ys not in _norm_product_title:
            return False, "year_missing"
    _ok_family, _family_reason = _row_matches_target_product_family(_norm_product_title, _meta)
    if not _ok_family:
        return False, _family_reason
    for _conflict in _catalog_family_conflict_tokens(_meta):
        if _conflict and _conflict in _norm_product_title:
            return False, f"off_target_product_family:{_conflict.replace(' ', '_')}"
    _exclude_terms = [_normalize_product_match_text(_t) for _t in (_meta.get("exclude_terms") or []) if str(_t).strip()]
    for _ex in _exclude_terms:
        if _ex and _ex in _norm_product_title:
            return False, f"excluded_term:{_ex.replace(' ', '_')}"
    return True, "ok"


def validate_target_listing(
    title: str,
    *,
    intended_player_id: str,
    target_meta: Dict[str, Any],
) -> Tuple[bool, str]:
    """
    Application-side gate after eBay returns items. Prefer zero rows over wrong-player rows.
    Order: empty → unknown seed → intended player → other seed conflict → product anchors.
    """
    nt = normalize_title_for_match(title)
    if not nt:
        return False, "empty_title"
    seed = players_by_id().get(str(intended_player_id))
    if not seed:
        return False, "unknown_player_seed"
    others = other_hub_players_in_title(nt, str(intended_player_id))
    ok_p, pr = listing_matches_target_player(nt, seed)
    if not ok_p:
        if others:
            return False, "other_player_in_title"
        return False, pr
    if others:
        return False, "conflicting_seed_player"
    ok_t, tr = listing_matches_product_target(nt, target_meta)
    if not ok_t:
        return False, tr
    return True, "ok"


def _dedupe_rank_target_listing_hits(
    raw_hits: List[Tuple[Dict[str, Any], Dict[str, str]]],
    *,
    phrase_lower: str,
    target_id: str,
    target_label: str,
) -> List[Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for item, meta in raw_hits:
        if not isinstance(item, dict):
            continue
        k = _browse_item_id_key(item)
        b = buckets.setdefault(
            k,
            {
                "item": item,
                "matched_queries": [],
                "matched_players": [],
                "max_phrase_score": 0,
            },
        )
        mq = str(meta.get("matched_query") or "")
        mp = str(meta.get("matched_player") or "")
        if mq and mq not in b["matched_queries"]:
            b["matched_queries"].append(mq)
        if mp and mp not in b["matched_players"]:
            b["matched_players"].append(mp)
        sc = _phrase_match_score(str(item.get("title") or ""), phrase_lower)
        b["max_phrase_score"] = max(int(b["max_phrase_score"] or 0), sc)
        b["item"] = item

    rows: List[Dict[str, Any]] = []
    for _k, b in buckets.items():
        item = b["item"]
        pr = _browse_item_price(item)
        sp = _sale_priority_sort(item)
        opts = item.get("buyingOptions")
        if not isinstance(opts, list):
            opts = [opts] if opts else []
        rows.append(
            {
                "item_id": str(item.get("itemId") or ""),
                "title": str(item.get("title") or ""),
                "item_web_url": str(item.get("itemWebUrl") or ""),
                "image_url": _browse_thumbnail_url(item),
                "current_price": pr,
                "buying_options": [str(x) for x in opts],
                "matched_queries": list(b["matched_queries"]),
                "matched_players": list(b["matched_players"]),
                "target_id": str(target_id),
                "target_label": str(target_label),
                "phrase_match_score": int(b.get("max_phrase_score") or 0),
                "sale_priority": sp,
                "item": item,
            }
        )
    rows.sort(
        key=lambda r: (
            -int(r.get("phrase_match_score") or 0),
            int(r.get("sale_priority") or 9),
            float(r.get("current_price") or 0.0),
            str(r.get("item_id") or ""),
        )
    )
    return rows[:_MAX_RESULTS_PER_TARGET_RUN]


def run_product_target_scan(
    state: Dict[str, Any],
    target_id: str,
    *,
    search_fn: Callable[[str, int], List[Dict[str, Any]]],
    limit_per_query: int = 10,
    scan_options: Optional[Dict[str, Any]] = None,
    max_query_specs: int = 0,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Execute generated queries via search_fn (e.g. ebay_search.search_auction_items), dedupe, rank, persist run.

    Returns (updated_state, run_record). Caller should save_player_hub_state(updated_state).
    Continues on per-query failure; does not raise unless search_fn does before try.
    """
    ensure_buy_universe_seed(state)
    bu = state["buy_universe"]
    tid = str(target_id)
    started = _utc_now_iso()
    run_id = f"cts_{uuid.uuid4().hex[:14]}"
    meta = get_product_target(state, tid)
    meta_eff = resolve_effective_product_target_meta(meta)
    tlabel = str((meta_eff or {}).get("label") or (meta or {}).get("label") or tid)

    empty_run: Dict[str, Any] = {
        "run_id": run_id,
        "target_id": tid,
        "target_label": tlabel,
        "started_at": started,
        "finished_at": started,
        "query_count": 0,
        "listing_count_raw": 0,
        "listing_count_validated_pre_dedupe": 0,
        "listing_count_rejected": 0,
        "listing_count_deduped": 0,
        "status": "no_queries",
        "queries_executed": [],
        "results": [],
        "errors": [],
        "rejection_reasons_aggregate": {},
        "rejected_samples": [],
    }

    if not meta or not meta.get("active", True):
        empty_run["status"] = "inactive_target"
        bu.setdefault("target_scan_runs", []).append(empty_run)
        bu["target_scan_runs"] = bu["target_scan_runs"][-_MAX_TARGET_SCAN_RUNS_STORED:]
        bu.setdefault("target_latest_run_by_target", {})[tid] = run_id
        return state, empty_run

    specs = build_target_scan_query_specs(state, tid, scan_options=scan_options)
    if max_query_specs and max_query_specs > 0 and len(specs) > max_query_specs:
        specs = specs[:max_query_specs]
    if not specs:
        empty_run["status"] = "no_queries"
        bu.setdefault("target_scan_runs", []).append(empty_run)
        bu["target_scan_runs"] = bu["target_scan_runs"][-_MAX_TARGET_SCAN_RUNS_STORED:]
        bu.setdefault("target_latest_run_by_target", {})[tid] = run_id
        return state, empty_run

    phrase_lower = build_target_product_phrase(meta_eff).lower()
    _subset_terms = _target_subset_terms(meta_eff)
    _parallel_terms = _target_parallel_terms(meta_eff)
    _lane_scan_labels = list(_subset_terms or [str(meta_eff.get("set_name") or phrase_lower or tid)])
    query_log: List[Dict[str, Any]] = []
    raw_hits: List[Tuple[Dict[str, Any], Dict[str, str]]] = []
    errors: List[str] = []
    rejected_samples: List[Dict[str, Any]] = []
    raw_listing_count = 0
    raw_bin_listing_count = 0
    raw_non_bin_listing_count = 0
    raw_missing_price_count = 0
    validated_pre_dedupe_count = 0
    n_ok = 0
    n_fail = 0
    lim = max(1, min(50, int(limit_per_query)))
    _MAX_REJECT_SAMPLES = 40

    for spec in specs:
        q = str(spec.get("query") or "")
        pname = str(spec.get("player_name") or "")
        pid_spec = str(spec.get("player_id") or "")
        if not q:
            continue
        entry: Dict[str, Any] = {
            "query": q,
            "player_name": pname,
            "player_id": pid_spec,
            "fetch_mode": "browse_fixed_price",
            "fetch_filter": "buyingOptions:{FIXED_PRICE}",
            "ok": False,
            "error": "",
            "hits": 0,
            "raw_hits": 0,
            "bin_hits": 0,
            "non_bin_hits": 0,
            "missing_price_hits": 0,
            "validated_hits": 0,
            "rejected_hits": 0,
            "rejection_reasons": {},
        }
        try:
            items = search_fn(q, lim) or []
            if not isinstance(items, list):
                items = []
            entry["ok"] = True
            entry["hits"] = len(items)
            entry["raw_hits"] = len(items)
            n_ok += 1
            raw_listing_count += len(items)
            per_reason: Dict[str, int] = {}
            n_val = 0
            n_bin = 0
            n_non_bin = 0
            n_missing_price = 0
            for it in items:
                if not isinstance(it, dict):
                    continue
                _opts = it.get("buyingOptions") or []
                if isinstance(_opts, str):
                    _opts = [_opts]
                _opts_u = {str(o).upper() for o in _opts if o}
                _is_bin = "FIXED_PRICE" in _opts_u
                if _is_bin:
                    n_bin += 1
                    raw_bin_listing_count += 1
                else:
                    n_non_bin += 1
                    raw_non_bin_listing_count += 1
                if _browse_item_price(it) <= 0:
                    n_missing_price += 1
                    raw_missing_price_count += 1
                tit = str(it.get("title") or "")
                ok_lv, reason = validate_target_listing(
                    tit,
                    intended_player_id=pid_spec,
                    target_meta=meta_eff,
                )
                if ok_lv:
                    n_val += 1
                    raw_hits.append(
                        (
                            it,
                            {
                                "matched_query": q,
                                "matched_player": pname,
                                "matched_player_id": pid_spec,
                            },
                        )
                    )
                else:
                    per_reason[reason] = per_reason.get(reason, 0) + 1
                    if len(rejected_samples) < _MAX_REJECT_SAMPLES:
                        rejected_samples.append(
                            {
                                "title": tit[:220],
                                "reason": reason,
                                "query": q[:200],
                                "intended_player": pname,
                                "target_id": tid,
                            }
                        )
            entry["bin_hits"] = n_bin
            entry["non_bin_hits"] = n_non_bin
            entry["missing_price_hits"] = n_missing_price
            entry["validated_hits"] = n_val
            entry["rejected_hits"] = len(items) - n_val
            entry["rejection_reasons"] = per_reason
            validated_pre_dedupe_count += n_val
        except Exception as exc:
            entry["error"] = str(exc)[:500]
            entry["error_type"] = type(exc).__name__
            errors.append(f"{q[:80]}: {entry['error']}")
            n_fail += 1
        query_log.append(entry)

    if n_ok == 0 and n_fail > 0:
        status = "failed"
    elif n_fail > 0:
        status = "partial"
    else:
        status = "ok"

    results = _dedupe_rank_target_listing_hits(
        raw_hits,
        phrase_lower=phrase_lower,
        target_id=tid,
        target_label=tlabel,
    )
    finished = _utc_now_iso()
    agg_rejection: Dict[str, int] = {}
    for ent in query_log:
        for rk, rv in (ent.get("rejection_reasons") or {}).items():
            if isinstance(rv, int):
                agg_rejection[rk] = agg_rejection.get(rk, 0) + rv
    rejected_total = max(0, raw_listing_count - validated_pre_dedupe_count)
    run_rec: Dict[str, Any] = {
        "run_id": run_id,
        "target_id": tid,
        "target_label": tlabel,
        "started_at": started,
        "finished_at": finished,
        "query_count": len(specs),
        "configured_target_lanes": len(_lane_scan_labels),
        "lanes_scanned": list(_lane_scan_labels)[:12],
        "listing_count_raw": raw_listing_count,
        "listing_count_bin_raw": raw_bin_listing_count,
        "listing_count_non_bin_raw": raw_non_bin_listing_count,
        "listing_count_missing_price_raw": raw_missing_price_count,
        "listing_count_validated_pre_dedupe": validated_pre_dedupe_count,
        "listing_count_rejected": rejected_total,
        "listing_count_off_target_rejected": sum(
            int(v) for k, v in agg_rejection.items() if str(k).startswith("off_target_product_family") or str(k).startswith("subset_")
        ),
        "listing_count_deduped": len(results),
        "status": status,
        "queries_executed": query_log,
        "results": results,
        "errors": errors,
        "rejection_reasons_aggregate": agg_rejection,
        "rejected_samples": rejected_samples[:30],
        "result_summary": {
            "queries_ok": n_ok,
            "queries_failed": n_fail,
            "phrase_used": phrase_lower,
            "raw_listings": raw_listing_count,
            "bin_raw": raw_bin_listing_count,
            "non_bin_raw": raw_non_bin_listing_count,
            "missing_price_raw": raw_missing_price_count,
            "validated_pre_dedupe": validated_pre_dedupe_count,
            "rejected": rejected_total,
            "deduped": len(results),
            "configured_target_lanes": len(_lane_scan_labels),
            "parallel_lane_terms": list(_parallel_terms)[:6],
        },
    }
    bu.setdefault("target_scan_runs", []).append(run_rec)
    bu["target_scan_runs"] = bu["target_scan_runs"][-_MAX_TARGET_SCAN_RUNS_STORED:]
    bu.setdefault("target_latest_run_by_target", {})[tid] = run_id
    return state, run_rec


def get_latest_target_scan_run(state: Dict[str, Any], target_id: str) -> Optional[Dict[str, Any]]:
    ensure_buy_universe_seed(state)
    bu = state.get("buy_universe") or {}
    tid = str(target_id)
    rid = (bu.get("target_latest_run_by_target") or {}).get(tid)
    runs = bu.get("target_scan_runs") or []
    if rid:
        for r in reversed(runs):
            if isinstance(r, dict) and r.get("run_id") == rid:
                return r
    for r in reversed(runs):
        if isinstance(r, dict) and r.get("target_id") == tid:
            return r
    return None


def get_validation_mode_settings(state: Dict[str, Any]) -> Dict[str, Any]:
    ensure_buy_universe_seed(state)
    _raw = ((state.get("buy_universe") or {}).get("validation_mode") or {})
    # Enforce a minimum floor so stale persisted state files don't choke the supply.
    # Old state files may have max_players=5 / max_targets_per_player=5 baked in.
    _raw_players = int(_raw.get("max_players") or 120)
    _raw_targets = int(_raw.get("max_targets_per_player") or 25)
    return {
        "enabled": bool(_raw.get("enabled", True)),
        "max_players": max(60, min(500, _raw_players)),
        "max_targets_per_player": max(17, min(100, _raw_targets)),
        "allowed_player_ids": [str(x).strip() for x in (_raw.get("allowed_player_ids") or []) if str(x).strip()],
        "allowed_target_ids": [str(x).strip() for x in (_raw.get("allowed_target_ids") or []) if str(x).strip()],
    }


def get_target_scan_results(state: Dict[str, Any], target_id: str) -> List[Dict[str, Any]]:
    run = get_latest_target_scan_run(state, target_id)
    if not run:
        return []
    return list(run.get("results") or [])


def browse_listing_dedupe_key(item: Dict[str, Any]) -> str:
    """Stable id for a Browse listing (same logic as target scan dedupe)."""
    return _browse_item_id_key(item)


def collect_buying_radar_candidate_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    All validated rows from the latest stored scan per **active** product target.
    Not globally deduped (same listing may appear for multiple targets).
    """
    ensure_buy_universe_seed(state)
    bu = state.get("buy_universe") or {}
    pt = bu.get("product_targets") or {}
    tracked_targets = {
        (str(t.get("target_id") or ""), str(t.get("player_id") or "")): t
        for t in build_tracked_scan_targets(state, listing_mode="bin")
    }
    out: List[Dict[str, Any]] = []
    matched_count = 0
    rejected_player = 0
    rejected_product = 0
    rejected_parallel = 0
    for tid_key, row in pt.items():
        if not isinstance(row, dict):
            continue
        meta = merge_product_target_defaults(str(tid_key), row)
        if not meta.get("active", True):
            continue
        tid = str(meta.get("target_id") or tid_key)
        sport = str(meta.get("sport") or "").strip()
        results = get_target_scan_results(state, tid)
        for r in results:
            if not isinstance(r, dict):
                continue
            d = dict(r)
            _tracked = tracked_targets.get((tid, str(d.get("matched_player_id") or ""))) or tracked_targets.get((tid, ""))
            if _tracked:
                _match = listing_matches_tracked_target(str(d.get("title") or ""), _tracked)
                if not _match.get("ok"):
                    _reason = str(_match.get("reason") or "")
                    if "player" in _reason or "entity" in _reason:
                        rejected_player += 1
                    elif "product" in _reason or "set_token" in _reason or "brand_missing" in _reason:
                        rejected_product += 1
                    elif _reason == "parallel_mismatch":
                        rejected_parallel += 1
                    continue
                d["tracked_target"] = dict(_tracked)
                d.update(compute_target_action_prices(d, _tracked, listing_mode="bin"))
                matched_count += 1
            d["radar_target_sport"] = sport
            d["radar_target_id"] = tid
            out.append(d)
    print(
        f"[TARGETS][BIN] matched={matched_count} rejected_player={rejected_player} "
        f"rejected_product={rejected_product} rejected_parallel={rejected_parallel}"
    )
    return out


def dedupe_buying_radar_candidate_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    One row per listing. Merges target labels, player hits, and queries when a listing
    matched multiple active targets.
    """
    buckets: Dict[str, Dict[str, Any]] = {}
    order_keys: List[str] = []
    for r in rows:
        it = r.get("item")
        if not isinstance(it, dict):
            continue
        k = _browse_item_id_key(it)
        if k not in buckets:
            nr = dict(r)
            lab = str(nr.get("target_label") or "").strip()
            nr["radar_merged_target_labels"] = [lab] if lab else []
            tid = str(nr.get("target_id") or nr.get("radar_target_id") or "").strip()
            nr["radar_merged_target_ids"] = [tid] if tid else []
            sp0 = str(nr.get("radar_target_sport") or "").strip()
            nr["radar_merged_sports"] = [sp0] if sp0 else []
            buckets[k] = nr
            order_keys.append(k)
            continue
        cur = buckets[k]
        lab = str(r.get("target_label") or "").strip()
        if lab and lab not in (cur.get("radar_merged_target_labels") or []):
            cur.setdefault("radar_merged_target_labels", []).append(lab)
        tid = str(r.get("target_id") or r.get("radar_target_id") or "").strip()
        if tid and tid not in (cur.get("radar_merged_target_ids") or []):
            cur.setdefault("radar_merged_target_ids", []).append(tid)
        for mp in r.get("matched_players") or []:
            s = str(mp).strip()
            if s and s not in (cur.get("matched_players") or []):
                cur.setdefault("matched_players", []).append(s)
        for mq in r.get("matched_queries") or []:
            s = str(mq).strip()
            if s and s not in (cur.get("matched_queries") or []):
                cur.setdefault("matched_queries", []).append(s)
        if int(r.get("phrase_match_score") or 0) > int(cur.get("phrase_match_score") or 0):
            cur["phrase_match_score"] = r.get("phrase_match_score")
        sp = str(r.get("radar_target_sport") or "").strip()
        if sp and sp not in (cur.get("radar_merged_sports") or []):
            cur.setdefault("radar_merged_sports", []).append(sp)
    return [buckets[k] for k in order_keys]


def build_buying_radar_feed(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Aggregated, deduped buying radar rows from active targets' latest scans."""
    return dedupe_buying_radar_candidate_rows(collect_buying_radar_candidate_rows(state))


def summarize_buying_radar_feed_sources(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lightweight stats for Buying Radar UI (no Streamlit). Active targets vs latest scans vs rows on file.
    """
    ensure_buy_universe_seed(state)
    bu = state.get("buy_universe") or {}
    pt = bu.get("product_targets") or {}
    active_ids: List[str] = []
    with_latest: List[str] = []
    with_listings: List[str] = []
    idle: List[Tuple[str, str]] = []
    last_ts: List[Tuple[str, str]] = []
    for tid_key, row in pt.items():
        if not isinstance(row, dict):
            continue
        meta = merge_product_target_defaults(str(tid_key), row)
        if not meta.get("active", True):
            continue
        tid = str(meta.get("target_id") or tid_key)
        active_ids.append(tid)
        run = get_latest_target_scan_run(state, tid)
        if not run:
            idle.append((tid, "no_scan_yet"))
            continue
        with_latest.append(tid)
        fin = str(run.get("finished_at") or run.get("started_at") or "").strip()
        if fin:
            last_ts.append((tid, fin))
        ded = int(run.get("listing_count_deduped") or 0)
        if ded > 0:
            with_listings.append(tid)
        else:
            rstatus = str(run.get("status") or "—")
            idle.append((tid, rstatus))
    return {
        "active_target_ids": active_ids,
        "targets_with_latest_scan": with_latest,
        "targets_with_deduped_listings": with_listings,
        "targets_idle_or_empty": idle,
        "last_finished_by_target": sorted(last_ts, key=lambda x: x[1], reverse=True)[:12],
    }


def compute_trade_activity_score(
    player_id: str,
    state: Dict[str, Any],
    *,
    raw_counts: Dict[str, Any],
    scan_meta: Dict[str, Any],
    heat_score: float,
    sales_volume_score: float,
) -> Dict[str, Any]:
    """
    Single sortable score: listing visibility + in-app frequency + scan cadence + heat.
    Uses existing demand/scan signals (not external sold comps).
    """
    raw = raw_counts or {}
    ld = int(raw.get("listing_depth_max") or 0)
    ls = int(raw.get("listing_depth_last_search") or 0)
    lr = int(raw.get("listing_depth_last_radar") or 0)
    listing_component = min(
        100.0,
        float(ld) * 14.0 + float(ls + lr) * 3.5,
    )
    scans = int((scan_meta or {}).get("scan_count") or 0)
    ns = count_snapshots_with_source(state, player_id, "search")
    nr = count_snapshots_with_source(state, player_id, "radar")
    freq = float(scans) * 2.0 + float(ns) + float(nr)
    freq_component = min(100.0, freq * 6.0)
    sv = max(0.0, min(100.0, float(sales_volume_score or 0.0)))
    heat = max(0.0, min(100.0, float(heat_score or 0.0)))
    score = (
        0.34 * listing_component
        + 0.26 * sv
        + 0.22 * freq_component
        + 0.18 * heat
    )
    return {
        "trade_activity_score": round(score, 2),
        "trade_activity_listing": round(listing_component, 2),
        "trade_activity_frequency": round(freq_component, 2),
        "trade_activity_scan_events": int(scans + ns + nr),
    }


def filter_players_by_sport_rookie_year(
    state: Dict[str, Any],
    sport_code: str,
    rookie_year: int,
    *,
    hide_ignored: bool = True,
) -> List[Dict[str, Any]]:
    """
    Players from hub seed matching NFL/NBA/MLB and exact rookie season (None excluded).
    Rookie scout uses `rookie_year` only — category_tags are not used for bucket placement.
    """
    want = (sport_code or "").strip().upper()
    try:
        y = int(rookie_year)
    except (TypeError, ValueError):
        return []
    profiles = build_all_profiles(state)
    out: List[Dict[str, Any]] = []
    for p in profiles:
        if hide_ignored and p.get("is_ignored"):
            continue
        if normalize_hub_sport(str(p.get("sport") or "")) != want:
            continue
        ry = p.get("rookie_year")
        if ry is None:
            continue
        try:
            if int(ry) != y:
                continue
        except (TypeError, ValueError):
            continue
        out.append(p)
    out.sort(
        key=lambda x: (
            -float(x.get("trade_activity_score") or 0),
            str(x.get("player_name") or "").lower(),
        )
    )
    return out


def _merge_signals(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
    if not isinstance(src, dict):
        return
    for k, v in src.items():
        if k in dst and isinstance(v, dict):
            dst[k] = {str(a): int(b) for a, b in v.items() if str(a)}


def _normalize_player_overrides(raw: Any) -> Dict[str, Any]:
    """Force string player_id keys so overrides match seed ids (avoids int/str mismatches)."""
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Any] = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            out[str(k)] = dict(v)
    return out


def active_scan_id_set(state: Dict[str, Any]) -> set:
    """Normalized string ids for Active Scan membership checks."""
    return {str(x) for x in (state.get("active_scan_player_ids") or []) if str(x)}


def load_player_hub_state(*, apply_buy_universe_seed: bool = True) -> Dict[str, Any]:
    """
    Merge ``player_hub_state.json`` into the default skeleton.

    When ``apply_buy_universe_seed`` is False (emergency shell / triage), skips
    ``ensure_buy_universe_seed`` so opening Player Hub does not inject default
    groups/targets into memory on every render. Call ``ensure_buy_universe_seed``
    only after an explicit user action when using that mode.
    """
    if not os.path.exists(STATE_FILE):
        base0 = default_state()
        return ensure_buy_universe_seed(base0) if apply_buy_universe_seed else base0
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            base0 = default_state()
            return ensure_buy_universe_seed(base0) if apply_buy_universe_seed else base0
        base = default_state()
        base["player_overrides"] = _normalize_player_overrides(data.get("player_overrides"))
        _merge_signals(base["signals"], data.get("signals") or {})
        if isinstance(data.get("monitoring"), dict):
            mon = data["monitoring"]
            if isinstance(mon.get("per_player"), dict):
                base["monitoring"]["per_player"] = mon["per_player"]
            if isinstance(mon.get("meta"), dict):
                base["monitoring"]["meta"].update(mon["meta"])
        if isinstance(data.get("scan_meta"), dict):
            base["scan_meta"] = {str(k): dict(v) for k, v in data["scan_meta"].items() if isinstance(v, dict)}
        ids = data.get("active_scan_player_ids")
        if isinstance(ids, list):
            base["active_scan_player_ids"] = [str(x) for x in ids if str(x)]
        if isinstance(data.get("meta"), dict):
            base["meta"].update(data["meta"])
        bu_src = data.get("buy_universe")
        if isinstance(bu_src, dict):
            bu = base.setdefault("buy_universe", default_state()["buy_universe"])
            if isinstance(bu_src.get("groups"), dict):
                for gk, gv in bu_src["groups"].items():
                    if isinstance(gv, dict):
                        bu["groups"][str(gk)] = dict(gv)
            if isinstance(bu_src.get("product_targets"), dict):
                for tk, tv in bu_src["product_targets"].items():
                    if isinstance(tv, dict):
                        bu["product_targets"][str(tk)] = dict(tv)
            if isinstance(bu_src.get("player_memberships"), dict):
                for pk, pv in bu_src["player_memberships"].items():
                    if isinstance(pv, list):
                        bu["player_memberships"][str(pk)] = [str(x) for x in pv if str(x)]
            if isinstance(bu_src.get("target_group_links"), dict):
                for tk, tv in bu_src["target_group_links"].items():
                    if isinstance(tv, list):
                        bu["target_group_links"][str(tk)] = [str(x) for x in tv if str(x)]
            if isinstance(bu_src.get("target_scan_runs"), list):
                bu["target_scan_runs"] = [x for x in bu_src["target_scan_runs"] if isinstance(x, dict)][
                    -_MAX_TARGET_SCAN_RUNS_STORED:
                ]
            if isinstance(bu_src.get("target_latest_run_by_target"), dict):
                for tk, rv in bu_src["target_latest_run_by_target"].items():
                    bu["target_latest_run_by_target"][str(tk)] = str(rv)
        if apply_buy_universe_seed:
            base = ensure_buy_universe_seed(base)
        base["version"] = STATE_VERSION
        return base
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        base0 = default_state()
        return ensure_buy_universe_seed(base0) if apply_buy_universe_seed else base0


def save_player_hub_state(state: Dict[str, Any]) -> bool:
    try:
        state = dict(state or {})
        state["version"] = STATE_VERSION
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        return True
    except OSError:
        return False


def _get_override(state: Dict[str, Any], player_id: str) -> Dict[str, Any]:
    pid = str(player_id)
    po = state.setdefault("player_overrides", {})
    return po.setdefault(pid, {})


def append_player_monitoring_snapshot(state: Dict[str, Any], player_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    pid = str(player_id)
    mon = state.setdefault("monitoring", {}).setdefault("per_player", {}).setdefault(pid, {})
    snaps: List[Dict[str, Any]] = list(mon.get("snapshots") or [])
    snap = {"ts": _utc_now_iso()}
    snap.update(fields or {})
    snaps.append(snap)
    mon["snapshots"] = snaps[-_MAX_SNAPSHOTS_PER_PLAYER:]
    mon["last_checked_ts"] = snap["ts"]
    return state


def set_my_player(state: Dict[str, Any], player_id: str, value: bool) -> Dict[str, Any]:
    o = _get_override(state, player_id)
    o["is_added_to_my_players"] = bool(value)
    o["last_updated"] = _utc_now_iso()
    append_player_monitoring_snapshot(state, player_id, {"source": "manual_my_players", "my_players": bool(value)})
    # Auto-assign to sport's default group so the player appears in the Buying Radar.
    if value:
        seeds = players_by_id()
        seed = seeds.get(str(player_id))
        if seed:
            sport = seed.get("sport") or ""
            default_group = young_gun_group_id_for_sport(sport)
            if default_group and not player_has_any_group_membership(state, player_id):
                state = set_player_group_membership(state, player_id, default_group, True)
            # Also slot QBs into the QB-core group
            if seed.get("position") == "QB":
                state = set_player_group_membership(state, player_id, "pp_nfl_qb_core", True)
    return state


def set_ignored(state: Dict[str, Any], player_id: str, value: bool) -> Dict[str, Any]:
    o = _get_override(state, player_id)
    o["is_ignored"] = bool(value)
    o["last_updated"] = _utc_now_iso()
    return state


def set_notes(state: Dict[str, Any], player_id: str, notes: str) -> Dict[str, Any]:
    o = _get_override(state, player_id)
    o["notes"] = str(notes or "")[:2000]
    o["last_updated"] = _utc_now_iso()
    return state


def set_active_scan(state: Dict[str, Any], player_id: str, value: bool) -> Dict[str, Any]:
    raw = state.get("active_scan_player_ids") or []
    ids = [str(x) for x in raw if str(x)]
    pid = str(player_id)
    if value:
        if pid not in ids:
            ids.append(pid)
    else:
        ids = [x for x in ids if x != pid]
    state["active_scan_player_ids"] = ids
    append_player_monitoring_snapshot(state, player_id, {"source": "active_scan", "active_scan": bool(value)})
    return state


def sync_active_scan_from_my_players(state: Dict[str, Any]) -> Dict[str, Any]:
    po = state.get("player_overrides") or {}
    ids = active_scan_id_set(state)
    for pid, row in po.items():
        if isinstance(row, dict) and row.get("is_added_to_my_players"):
            ids.add(str(pid))
    state["active_scan_player_ids"] = sorted(ids)
    return state


def active_scan_runner_queue(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Ordered entries for Active Scan players (seeded ids only)."""
    seeds = players_by_id()
    out: List[Dict[str, Any]] = []
    for pid in state.get("active_scan_player_ids") or []:
        ps = seeds.get(str(pid))
        if not ps:
            continue
        out.append(
            {
                "player_id": str(pid),
                "query": resolve_scan_query_for_seed(ps),
                "name": ps.get("player_name") or pid,
            }
        )
    return out


def build_default_scan_query(seed_row: Dict[str, Any]) -> str:
    """
    Practical default eBay query from seed/profile fields (when search_query_hint is empty).
    Keeps queries short and searchable.
    """
    name = (seed_row.get("player_name") or "").strip()
    if not name:
        return ""
    sport = (seed_row.get("sport") or "").strip().lower()
    ry = seed_row.get("rookie_year")
    tags = [str(t).lower() for t in (seed_row.get("category_tags") or [])]
    parts = [name]
    if ry is not None:
        parts.append(str(ry))
    if ry is not None or any("rookie" in t for t in tags):
        parts.append("rookie")
    else:
        parts.append("card")
    if sport == "basketball":
        parts.append("prizm")
    elif sport == "baseball":
        parts.append("bowman")
    return " ".join(parts).strip()[:220]


def resolve_scan_query_for_seed(seed_row: Dict[str, Any]) -> str:
    h = (seed_row.get("search_query_hint") or "").strip()
    if h:
        return h[:240]
    return build_default_scan_query(seed_row)[:240]


def count_player_hits_in_items(player_id: str, items: Optional[List[Dict[str, Any]]]) -> int:
    """How many returned listing titles match this seeded player (SERP visibility)."""
    seeds = players_by_id()
    if player_id not in seeds:
        return 0
    subset = {player_id: seeds[player_id]}
    return int(_count_title_matches(items, subset).get(player_id, 0))


def record_player_scan_completion(
    state: Dict[str, Any],
    player_id: str,
    keyword: str,
    result_count: int,
    opportunity_group_hits: int = 0,
    *,
    scan_source: str = "player_hub",
) -> Dict[str, Any]:
    """After a Search eBay run tied to this player (scan runner or Scan now)."""
    pid = str(player_id)
    sm = state.setdefault("scan_meta", {}).setdefault(pid, {})
    sm["scan_count"] = int(sm.get("scan_count") or 0) + 1
    sm["last_scan_ts"] = _utc_now_iso()
    sm["last_scan_time"] = sm["last_scan_ts"]
    sm["last_keyword"] = str(keyword or "")[:220]
    sm["last_scan_query"] = sm["last_keyword"]
    sm["last_result_count"] = int(result_count)
    sm["last_opportunity_groups"] = int(opportunity_group_hits)
    sm["last_scan_had_listings"] = bool(int(result_count) > 0)
    sm["last_scan_source"] = str(scan_source or "player_hub")[:80]

    ld = min(10, max(0, int(result_count)))
    append_player_monitoring_snapshot(
        state,
        pid,
        {
            "source": "player_scan",
            "listing_depth": ld,
            "strong_board": 0,
            "snipe_board": 0,
            "watchlist_import": 0,
            "scan_hit": 1,
            "scan_source": str(scan_source or "player_hub")[:80],
        },
    )
    return state


def count_snapshots_with_source(state: Dict[str, Any], player_id: str, source: str) -> int:
    snaps = (state.get("monitoring") or {}).get("per_player", {}).get(player_id, {}).get("snapshots") or []
    return sum(1 for s in snaps if (s.get("source") or "") == source)


def _count_title_matches(items: Optional[List[Dict[str, Any]]], seeds: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    if not items:
        return counts
    for item in items:
        title = (item.get("title") or "").lower()
        if not title:
            continue
        for pid, row in seeds.items():
            for tok in row.get("match_tokens") or []:
                if str(tok).lower() in title:
                    counts[pid] = counts.get(pid, 0) + 1
                    break
    return counts


def _keyword_hits(keyword: str, seeds: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    if not keyword or not str(keyword).strip():
        return counts
    kw = keyword.lower()
    for pid, row in seeds.items():
        for tok in row.get("match_tokens") or []:
            if str(tok).lower() in kw:
                counts[pid] = counts.get(pid, 0) + 1
                break
    return counts


def _group_match_counts(groups: Optional[List[Dict[str, Any]]], seeds: Dict[str, Dict[str, Any]]):
    strong_by: Dict[str, int] = {}
    snipe_by: Dict[str, int] = {}
    matched_any: Dict[str, bool] = {}
    if not groups:
        return strong_by, snipe_by, matched_any

    for g in groups:
        label = (g.get("group_action_label") or "").strip()
        blob_parts = [g.get("representative_title") or ""]
        for m in g.get("members") or []:
            blob_parts.append((m.get("title") or ""))
        blob = " ".join(blob_parts).lower()
        for pid, row in seeds.items():
            toks = row.get("match_tokens") or []
            if not any(str(t).lower() in blob for t in toks):
                continue
            matched_any[pid] = True
            if label == "Snipe Now":
                snipe_by[pid] = snipe_by.get(pid, 0) + 1
            if label in ("Snipe Now", "Priority Watch", "Good Board Spot"):
                strong_by[pid] = strong_by.get(pid, 0) + 1
    return strong_by, snipe_by, matched_any


def on_ebay_search_finished(state: Dict[str, Any], keyword: str, items: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    seeds = players_by_id()
    sig = state.setdefault("signals", {})
    counts = _count_title_matches(items, seeds)
    sig["listing_depth_last_search"] = counts
    kh = _keyword_hits(keyword, seeds)
    kstore = sig.setdefault("keyword_search_count", {})
    for pid, n in kh.items():
        kstore[pid] = int(kstore.get(pid, 0)) + int(n)

    touched = set(counts.keys()) | set(kh.keys())
    for pid in touched:
        snap: Dict[str, Any] = {"source": "search", "strong_board": 0, "snipe_board": 0, "watchlist_import": 0}
        ld = int(counts.get(pid, 0))
        if ld > 0:
            snap["listing_depth"] = ld
        if int(kh.get(pid, 0)) > 0:
            snap["keyword_hit"] = int(kh.get(pid, 0))
        append_player_monitoring_snapshot(state, pid, snap)
    return state


def on_radar_items(state: Dict[str, Any], items: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    seeds = players_by_id()
    sig = state.setdefault("signals", {})
    counts = _count_title_matches(items, seeds)
    sig["listing_depth_last_radar"] = counts
    for pid, n in counts.items():
        append_player_monitoring_snapshot(
            state,
            pid,
            {
                "source": "radar",
                "listing_depth": int(n),
                "keyword_hit": 0,
                "strong_board": 0,
                "snipe_board": 0,
                "watchlist_import": 0,
            },
        )
    return state


def ingest_cockpit_groups(state: Dict[str, Any], groups: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    seeds = players_by_id()
    sig = state.setdefault("signals", {})
    strong_by, snipe_by, matched = _group_match_counts(groups or [], seeds)
    sig["cockpit_strong_hits_last"] = {k: int(v) for k, v in strong_by.items()}
    sig["cockpit_snipe_hits_last"] = {k: int(v) for k, v in snipe_by.items()}

    ls = sig.get("listing_depth_last_search") or {}
    lr = sig.get("listing_depth_last_radar") or {}
    for pid in matched.keys():
        depth = max(int(ls.get(pid, 0) or 0), int(lr.get(pid, 0) or 0))
        append_player_monitoring_snapshot(
            state,
            pid,
            {
                "source": "cockpit_board",
                "listing_depth": depth,
                "strong_board": int(strong_by.get(pid, 0)),
                "snipe_board": int(snipe_by.get(pid, 0)),
                "keyword_hit": 0,
                "watchlist_import": 0,
            },
        )
    return state


def on_watchlist_items_added(state: Dict[str, Any], items: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    seeds = players_by_id()
    counts = _count_title_matches(items, seeds)
    for pid, n in counts.items():
        if n <= 0:
            continue
        append_player_monitoring_snapshot(
            state,
            pid,
            {
                "source": "watchlist_import",
                "watchlist_import": int(n),
                "strong_board": 0,
                "snipe_board": 0,
                "keyword_hit": 0,
            },
        )
    return state


def refresh_watchlist_signals(state: Dict[str, Any], watchlist_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    seeds = players_by_id()
    counts: Dict[str, int] = {pid: 0 for pid in seeds}
    for row in watchlist_rows or []:
        name = (row.get("card_name") or "").lower()
        if not name:
            continue
        for pid, row_seed in seeds.items():
            for tok in row_seed.get("match_tokens") or []:
                if str(tok).lower() in name:
                    counts[pid] = counts.get(pid, 0) + 1
                    break
    state.setdefault("signals", {})["watchlist_card_hits"] = counts
    state.setdefault("meta", {})["last_watchlist_rescan"] = _utc_now_iso()
    for pid, n in counts.items():
        if n <= 0:
            continue
        append_player_monitoring_snapshot(
            state,
            pid,
            {
                "source": "watchlist_rescan",
                "watchlist_rows_hits": int(n),
                "strong_board": 0,
                "snipe_board": 0,
                "keyword_hit": 0,
                "watchlist_import": 0,
            },
        )
    return state


def _norm_listing_depth(n: int) -> float:
    if n <= 0:
        return 0.0
    return min(1.0, float(n) / _CAP_LISTING_SNAPSHOT)


def _norm_keyword(n: int) -> float:
    if n <= 0:
        return 0.0
    return min(1.0, float(n) / _CAP_KEYWORD)


def _norm_watch(n: int) -> float:
    if n <= 0:
        return 0.0
    return min(1.0, float(n) / _CAP_WATCHLIST)


def build_player_demand_signals(
    player_id: str,
    state: Dict[str, Any],
) -> Tuple[Dict[str, float], Dict[str, Any]]:
    sig = state.get("signals") or {}
    ls = int((sig.get("listing_depth_last_search") or {}).get(player_id, 0))
    lr = int((sig.get("listing_depth_last_radar") or {}).get(player_id, 0))
    kw = int((sig.get("keyword_search_count") or {}).get(player_id, 0))
    wh = int((sig.get("watchlist_card_hits") or {}).get(player_id, 0))
    oh = int((sig.get("opportunity_hits") or {}).get(player_id, 0))
    cs = int((sig.get("cockpit_strong_hits_last") or {}).get(player_id, 0))
    sn = int((sig.get("cockpit_snipe_hits_last") or {}).get(player_id, 0))

    depth_listing = max(ls, lr)
    sales_volume_score = 100.0 * _norm_listing_depth(depth_listing)
    search_interest_score = 100.0 * _norm_keyword(kw)
    watch_activity_score = 100.0 * _norm_watch(wh)
    opp_events = max(cs, sn, min(oh, 20))
    opportunity_signal_score = 100.0 * min(1.0, float(opp_events) / 5.0)

    demand_score = (
        0.34 * sales_volume_score
        + 0.20 * search_interest_score
        + 0.26 * watch_activity_score
        + 0.20 * opportunity_signal_score
    )

    trend_score = 0.55 * sales_volume_score + 0.45 * search_interest_score

    raw = {
        "listing_depth_last_search": ls,
        "listing_depth_last_radar": lr,
        "listing_depth_max": depth_listing,
        "keyword_search_count": kw,
        "watchlist_card_hits": wh,
        "opportunity_hits": oh,
        "cockpit_strong_hits_last": cs,
        "cockpit_snipe_hits_last": sn,
    }
    components = {
        "sales_volume_score": sales_volume_score,
        "search_interest_score": search_interest_score,
        "watch_activity_score": watch_activity_score,
        "opportunity_signal_score": opportunity_signal_score,
        "demand_score": demand_score,
        "trend_score": trend_score,
    }
    return components, raw


def _profile_intent_points(is_my_players: bool, is_active_scan: bool, tag_count: int) -> Tuple[float, str]:
    """Explicit user + hub-registry signals (not market fabrication)."""
    pts = 10.0
    bits: List[str] = ["On hub seed list (+10 baseline)"]
    if is_my_players:
        pts += 20.0
        bits.append("My Players (+20)")
    if is_active_scan:
        pts += 14.0
        bits.append("Active Scan (+14)")
    tag_pts = min(12.0, 3.0 * max(0, int(tag_count)))
    if tag_pts > 0:
        pts += tag_pts
        bits.append(f"Category tags (+{tag_pts:.0f})")
    note = "; ".join(bits)
    return pts, note


def build_player_recommendation_score(
    player_id: str,
    state: Dict[str, Any],
    is_ignored: bool,
    *,
    is_my_players: bool = False,
    is_active_scan: bool = False,
    tag_count: int = 0,
) -> Tuple[float, Dict[str, Any], List[str], str]:
    comps, raw = build_player_demand_signals(player_id, state)
    activity_signal = (
        raw["listing_depth_max"]
        + raw["keyword_search_count"]
        + raw["watchlist_card_hits"]
        + raw["cockpit_strong_hits_last"]
        + raw["cockpit_snipe_hits_last"]
        + min(raw["opportunity_hits"], 10)
    )
    activity_blend = 0.42 * comps["demand_score"] + 0.33 * comps["trend_score"] + 0.25 * comps["watch_activity_score"]
    intent_pts, intent_note = _profile_intent_points(is_my_players, is_active_scan, tag_count)

    thin_activity = activity_signal < 2
    activity_eff = activity_blend * (0.62 if thin_activity else 1.0)
    intent_component = min(55.0, intent_pts * 1.15)
    rec = 0.62 * activity_eff + 0.38 * intent_component
    if is_ignored:
        rec = 0.0
    rec = max(0.0, min(100.0, rec))

    reasons: List[str] = []
    if raw["listing_depth_max"] >= 2:
        reasons.append("Multiple matching listings in your last Search/Radar snapshot")
    elif raw["listing_depth_max"] == 1:
        reasons.append("At least one listing matched in Search/Radar snapshot")
    if raw["keyword_search_count"] >= 1:
        reasons.append("Your search keywords overlapped this player")
    if raw["watchlist_card_hits"] >= 1:
        reasons.append("Watchlist cards mention this player")
    if raw["cockpit_strong_hits_last"] >= 1 or raw["cockpit_snipe_hits_last"] >= 1:
        reasons.append("Buyer cockpit board recently showed strong/snipe rows for this player")
    elif raw["opportunity_hits"] >= 1:
        reasons.append("Legacy opportunity counter in saved state")
    if intent_pts >= 10:
        reasons.append(f"Intent / hub profile: {intent_note}")

    if not reasons:
        reasons.append("Seeded in hub only — run Scan or Search to collect live listing signals")

    honesty = (
        "Recommendation blends live signals (listings, keywords, watchlist, cockpit) with **your** choices "
        "(My Players, Active Scan) and hub seed tags. It is not external market intel."
    )
    if thin_activity and intent_pts < 8:
        honesty += " Live activity is thin; scores lean on intent until you search or import."

    breakdown = {
        "recommendation_score": rec,
        "signal_components": comps,
        "raw_counts": raw,
        "activity_signal_events": activity_signal,
        "thin_activity": thin_activity,
        "intent_points": intent_pts,
        "intent_note": intent_note,
        "activity_blend": round(activity_blend, 2),
        "ignored": is_ignored,
    }
    return rec, breakdown, reasons, honesty


def build_player_monitoring_snapshot(player_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    mon = (state.get("monitoring") or {}).get("per_player", {}).get(player_id) or {}
    snaps = list(mon.get("snapshots") or [])
    last = snaps[-1] if snaps else {}
    return {
        "player_id": player_id,
        "snapshot_count": len(snaps),
        "last_snapshot": last,
        "recent_tail": snaps[-5:],
        "last_checked_ts": mon.get("last_checked_ts") or (last.get("ts") if last else ""),
    }


def build_player_heat_score(
    player_id: str,
    state: Dict[str, Any],
    *,
    is_my_players: bool = False,
    is_active_scan: bool = False,
) -> Dict[str, Any]:
    sm = (state.get("scan_meta") or {}).get(player_id) or {}
    scan_count = int(sm.get("scan_count") or 0)
    scan_boost = min(24.0, 5.5 * math.sqrt(max(0, scan_count)))
    if scan_count >= 1:
        hrs = _hours_since_iso(str(sm.get("last_scan_ts") or ""))
        scan_boost += max(0.0, 20.0 * math.exp(-hrs / 30.0))
    intent_h = (11.0 if is_active_scan else 0.0) + (7.0 if is_my_players else 0.0)

    mon = (state.get("monitoring") or {}).get("per_player", {}).get(player_id) or {}
    snaps: List[Dict[str, Any]] = list(mon.get("snapshots") or [])
    n = len(snaps)

    if n == 0:
        base = min(100.0, scan_boost + intent_h)
        thin = scan_count == 0 and not is_active_scan and not is_my_players
        return {
            "heat_score": round(base, 2),
            "heat_trend": "flat",
            "heat_thin": thin,
            "heat_peak_listing_depth": 0,
            "heat_snapshot_count": 0,
            "heat_last_checked": str(sm.get("last_scan_ts") or ""),
            "heat_breakdown": {
                "scan_boost": round(scan_boost, 2),
                "intent_boost": round(intent_h, 2),
                "snapshot_count": 0,
                "thin_heat": thin,
            },
            "heat_honesty": "No monitoring snapshots yet; heat reflects scan history + Active Scan / My Players only.",
        }

    recent = snaps[-12:]
    hold_l = 0
    listing_series: List[int] = []
    for s in recent:
        if "listing_depth" in s:
            hold_l = int(s.get("listing_depth") or 0)
        listing_series.append(hold_l)
    strong_series = [int(s.get("strong_board") or 0) for s in recent]
    snipe_series = [int(s.get("snipe_board") or 0) for s in recent]
    wl_series = [int(s.get("watchlist_import") or 0) + int(s.get("watchlist_rows_hits") or 0) for s in recent]

    last_l = listing_series[-1]
    peak_l = max(listing_series) if listing_series else 0
    avg_prev_l = statistics.mean(listing_series[:-1]) if len(listing_series) >= 2 else float(last_l)
    delta_l = last_l - avg_prev_l
    m_list = max(-1.0, min(1.0, delta_l / 4.0))

    last_board = strong_series[-1] + snipe_series[-1]
    if len(strong_series) >= 3:
        prev_window = statistics.mean(
            [strong_series[i] + snipe_series[i] for i in range(max(0, len(strong_series) - 3), len(strong_series) - 1)]
        )
    else:
        prev_window = float(strong_series[-2] + snipe_series[-2]) if len(strong_series) >= 2 else 0.0
    delta_b = float(last_board) - float(prev_window)
    m_board = max(-1.0, min(1.0, delta_b / 4.0))

    last_ts = str(snaps[-1].get("ts") or "")
    freshness = math.exp(-_hours_since_iso(last_ts) / 36.0)
    wl_pulse = min(1.0, float(wl_series[-1]) / 3.0) if wl_series else 0.0

    list_contrib = (m_list + 1.0) / 2.0
    board_contrib = max(0.0, (m_board + 1.0) / 2.0)

    heat_raw = 34.0 * list_contrib + 32.0 * board_contrib + 14.0 * freshness + 9.0 * wl_pulse
    series_sum = sum(listing_series) + sum(strong_series) + sum(snipe_series) + sum(wl_series)
    thin = n < 2 and series_sum == 0 and scan_count < 1
    if thin:
        heat_raw *= 0.55

    heat_momentum = max(0.0, min(100.0, heat_raw))
    heat = max(heat_momentum, min(100.0, scan_boost + intent_h))

    trend = "flat"
    if delta_l >= 1 or delta_b >= 1:
        trend = "up"
    elif delta_l <= -1 or delta_b <= -1:
        trend = "down"

    breakdown = {
        "listing_momentum": round(m_list, 3),
        "board_momentum": round(m_board, 3),
        "freshness": round(freshness, 3),
        "watchlist_pulse": round(wl_pulse, 3),
        "delta_listing_vs_prev_avg": round(delta_l, 3),
        "delta_board_vs_prev_window": round(delta_b, 3),
        "snapshot_count": n,
        "scan_boost": round(scan_boost, 2),
        "intent_boost": round(intent_h, 2),
        "thin_heat": thin and heat < 18,
    }
    honesty = (
        "Heat mixes snapshot momentum with Player Scan Runner history and Active Scan / My Players. "
        "It is not a global market temperature."
    )
    if thin and heat < 15:
        honesty += " Very little live history yet."

    return {
        "heat_score": round(float(heat), 2),
        "heat_trend": trend,
        "heat_thin": bool(thin and heat < 20),
        "heat_peak_listing_depth": int(peak_l),
        "heat_snapshot_count": int(n),
        "heat_last_checked": last_ts or str(sm.get("last_scan_ts") or ""),
        "heat_breakdown": breakdown,
        "heat_honesty": honesty,
    }


def summarize_player_heat_reason(heat: Dict[str, Any]) -> Tuple[str, List[str]]:
    lines: List[str] = []
    bd = heat.get("heat_breakdown") or {}
    if float(bd.get("scan_boost") or 0) >= 8:
        lines.append("Player Scan Runner or recent scans are warming this profile")
    if float(bd.get("intent_boost") or 0) >= 10:
        lines.append("Active Scan / My Players adds a monitoring floor")
    if float(bd.get("delta_listing_vs_prev_avg") or 0) >= 1:
        lines.append("Search/listing snapshots trending up vs your recent average")
    elif float(bd.get("delta_listing_vs_prev_avg") or 0) <= -1:
        lines.append("Listing snapshots cooled vs your recent average")
    if float(bd.get("delta_board_vs_prev_window") or 0) >= 1:
        lines.append("More strong or snipe-ready cockpit rows recently")
    elif float(bd.get("delta_board_vs_prev_window") or 0) <= -1:
        lines.append("Fewer strong/snipe cockpit hits in the latest board view")
    if float(bd.get("watchlist_pulse") or 0) >= 0.34:
        lines.append("Recent watchlist import/rescan mentions this player")
    if heat.get("heat_thin"):
        lines.append("Limited live history - heat is cautious")

    summary = "; ".join(lines[:2]) if lines else "Stable monitoring - no strong momentum yet."
    return summary, lines


def build_why_score_summary(
    player_id: str,
    state: Dict[str, Any],
    raw: Dict[str, Any],
    is_my: bool,
    is_scan: bool,
    scan_meta: Dict[str, Any],
) -> str:
    parts: List[str] = []
    ns = count_snapshots_with_source(state, player_id, "search")
    if ns:
        parts.append(f"{ns} search snapshot(s) logged")
    nr = count_snapshots_with_source(state, player_id, "radar")
    if nr:
        parts.append(f"{nr} radar snapshot(s)")
    sc = int(scan_meta.get("scan_count") or 0)
    if sc:
        parts.append(f"{sc} Player Hub scan(s)")
    if int(raw.get("watchlist_card_hits") or 0):
        parts.append(f"{raw['watchlist_card_hits']} watchlist mention(s)")
    if int(raw.get("cockpit_strong_hits_last") or 0) or int(raw.get("cockpit_snipe_hits_last") or 0):
        parts.append("Seen on buyer cockpit board")
    if is_scan:
        parts.append("On Active Scan")
    if is_my:
        parts.append("In My Players")
    if not parts:
        return "Seeded rookie only — no live activity yet; use Scan now or Search."
    return " · ".join(parts[:5])


def _stat_labels(
    value: float,
    *,
    kind: str,
    thin_activity: bool,
    thin_heat: bool,
    has_live: bool,
    demand_live: float = 0.0,
) -> Tuple[str, str]:
    """Returns (primary_display, muted caption)."""
    if kind == "heat":
        if thin_heat and value < 15:
            return ("Quiet", "not enough activity yet")
        if value >= 70:
            return (f"{value:.0f}", "elevated")
        if value >= 40:
            return (f"{value:.0f}", "warming")
        return (f"{value:.0f}", "steady / building")
    if kind == "rec":
        if thin_activity and value < 22:
            return (f"{value:.0f}", "early profile — add search or cockpit data")
        if value >= 65:
            return (f"{value:.0f}", "strong radar")
        return (f"{value:.0f}", "building")
    if kind == "demand":
        if not has_live or demand_live < 4.0:
            return (f"{value:.0f}", "listing depth thin — includes hub intent")
        if value < 22:
            return (f"{value:.0f}", "light")
        return (f"{value:.0f}", "active")
    return (f"{value:.0f}", "")


def _merge_profile(player_id: str, seed: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    ov = (state.get("player_overrides") or {}).get(player_id) or {}
    is_my = bool(ov.get("is_added_to_my_players", False))
    is_ignored = bool(ov.get("is_ignored", False))
    notes = str(ov.get("notes") or "")
    last_updated = str(ov.get("last_updated") or "")
    tags = list(seed.get("category_tags") or [])

    scan_ids = active_scan_id_set(state)
    rec, breakdown, reasons, honesty = build_player_recommendation_score(
        player_id,
        state,
        is_ignored,
        is_my_players=is_my,
        is_active_scan=player_id in scan_ids,
        tag_count=len(tags),
    )
    is_active_scan = player_id in scan_ids

    heat = build_player_heat_score(player_id, state, is_my_players=is_my, is_active_scan=is_active_scan)
    heat_summary, heat_lines = summarize_player_heat_reason(heat)

    comps = breakdown["signal_components"]
    raw = breakdown["raw_counts"]
    reason_summary = _compact_reason_summary(reasons, seed.get("player_name") or player_id)
    scan_meta = (state.get("scan_meta") or {}).get(player_id) or {}

    intent_pts = float(breakdown.get("intent_points") or 0)
    demand_live = float(comps["demand_score"])
    demand_display = min(100.0, demand_live + intent_pts * 0.45)

    has_live = bool(int(breakdown.get("activity_signal_events") or 0) >= 1)
    why = build_why_score_summary(player_id, state, raw, is_my, is_active_scan, scan_meta)

    h_disp, h_sub = _stat_labels(
        float(heat["heat_score"]),
        kind="heat",
        thin_activity=bool(breakdown.get("thin_activity")),
        thin_heat=bool(heat.get("heat_thin")),
        has_live=has_live,
    )
    r_disp, r_sub = _stat_labels(
        float(rec),
        kind="rec",
        thin_activity=bool(breakdown.get("thin_activity")),
        thin_heat=bool(heat.get("heat_thin")),
        has_live=has_live,
    )
    d_disp, d_sub = _stat_labels(
        demand_display,
        kind="demand",
        thin_activity=bool(breakdown.get("thin_activity")),
        thin_heat=bool(heat.get("heat_thin")),
        has_live=has_live,
        demand_live=float(demand_live),
    )

    ta = compute_trade_activity_score(
        player_id,
        state,
        raw_counts=raw,
        scan_meta=scan_meta,
        heat_score=float(heat["heat_score"]),
        sales_volume_score=float(comps["sales_volume_score"]),
    )

    utags = list(seed.get("tags") or [])
    if not utags and isinstance(seed.get("universe_tags"), list):
        utags = list(seed.get("universe_tags") or [])
    return {
        "player_id": player_id,
        "player_name": seed.get("player_name", player_id),
        "display_name": str(seed.get("display_name") or seed.get("player_name") or player_id),
        "sport": seed.get("sport", ""),
        "league": str(seed.get("league") or ""),
        "category_tags": tags,
        "universe_tags": utags,
        "seed_source": str(seed.get("seed_source") or "player_hub_seed"),
        "seed_priority": int(seed.get("seed_priority") or 50),
        "team": seed.get("team", ""),
        "position": seed.get("position", ""),
        "rookie_year": seed.get("rookie_year"),
        "trend_score": round(float(comps["trend_score"]), 2),
        "demand_score": round(float(demand_live), 2),
        "demand_display": round(float(demand_display), 2),
        "sales_volume_score": round(float(comps["sales_volume_score"]), 2),
        "search_interest_score": round(float(comps["search_interest_score"]), 2),
        "recommendation_score": round(float(rec), 2),
        "notes": notes,
        "is_added_to_my_players": is_my,
        "is_ignored": is_ignored,
        "is_active_scan": is_active_scan,
        "last_updated": last_updated,
        "search_query_hint": seed.get("search_query_hint") or seed.get("player_name", ""),
        "reason_phrases": reasons,
        "reason_summary": reason_summary,
        "honesty_note": honesty,
        "recommendation_breakdown": breakdown,
        "category_assignment_source": "seed:player_hub_seed.SEED_PLAYERS",
        "heat_score": heat["heat_score"],
        "heat_trend": heat["heat_trend"],
        "heat_thin": heat["heat_thin"],
        "heat_peak_listing_depth": heat["heat_peak_listing_depth"],
        "heat_snapshot_count": heat["heat_snapshot_count"],
        "heat_last_checked": heat["heat_last_checked"],
        "heat_summary": heat_summary,
        "heat_reason_lines": heat_lines,
        "heat_breakdown": heat["heat_breakdown"],
        "heat_honesty": heat["heat_honesty"],
        "monitoring_snapshot_debug": build_player_monitoring_snapshot(player_id, state),
        "why_score_summary": why,
        "scan_meta": scan_meta,
        "display_heat_primary": h_disp,
        "display_heat_sub": h_sub,
        "display_rec_primary": r_disp,
        "display_rec_sub": r_sub,
        "display_demand_primary": d_disp,
        "display_demand_sub": d_sub,
        "has_live_activity": has_live,
        "trade_activity_score": ta["trade_activity_score"],
        "trade_activity_listing": ta["trade_activity_listing"],
        "trade_activity_frequency": ta["trade_activity_frequency"],
        "trade_activity_scan_events": ta["trade_activity_scan_events"],
    }


def _compact_reason_summary(reasons: List[str], name: str) -> str:
    if not reasons:
        return f"No strong in-app signals yet for {name}."
    top = reasons[:2]
    return "; ".join(top)


def build_all_profiles(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    seeds = players_by_id()
    return [_merge_profile(pid, seed, state) for pid, seed in seeds.items()]


def get_recommended_players_for_category(
    category_id: str,
    state: Dict[str, Any],
    *,
    name_filter: str = "",
    hide_ignored: bool = True,
    only_not_added: bool = False,
    sort_by: str = "recommendation_score",
    profiles: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """If ``profiles`` is provided (e.g. same-run ``build_all_profiles``), skips rebuilding."""
    profiles = build_all_profiles(state) if profiles is None else profiles
    nf = (name_filter or "").strip().lower()

    if category_id == "trending":
        pool = [p for p in profiles]
    elif category_id == "my_players":
        pool = [p for p in profiles if p.get("is_added_to_my_players")]
    elif category_id == "heating_up":
        pool = [
            p
            for p in profiles
            if (p.get("heat_trend") == "up")
            and float(p.get("heat_score") or 0) >= HEAT_UP_MIN
            and not p.get("heat_thin")
        ]
    elif category_id == "cooling_off":
        pool = [
            p
            for p in profiles
            if (p.get("heat_trend") == "down")
            and float(p.get("heat_score") or 0) <= HEAT_COOL_MAX
            and int(p.get("heat_peak_listing_depth") or 0) >= 2
            and int(p.get("heat_snapshot_count") or 0) >= 2
        ]
    elif category_id == "steady_demand":
        pool = [
            p
            for p in profiles
            if (p.get("heat_trend") == "flat")
            and STEADY_HEAT_LOW <= float(p.get("heat_score") or 0) <= STEADY_HEAT_HIGH
            and int(p.get("heat_snapshot_count") or 0) >= STEADY_MIN_SNAPSHOTS
            and not p.get("heat_thin")
        ]
    elif category_id == "active_scan":
        ids = active_scan_id_set(state)
        pool = [p for p in profiles if p.get("player_id") in ids]
    else:
        pool = [p for p in profiles if category_id in (p.get("category_tags") or [])]

    if hide_ignored:
        pool = [p for p in pool if not p.get("is_ignored")]
    if only_not_added:
        pool = [p for p in pool if not p.get("is_added_to_my_players")]
    if nf:
        pool = [
            p
            for p in pool
            if nf in (p.get("player_name") or "").lower() or nf in p.get("player_id", "").lower()
        ]

    sort_keys = {
        "recommendation_score": lambda p: (-float(p.get("recommendation_score") or 0), p.get("player_name") or ""),
        "sales_volume_score": lambda p: (-float(p.get("sales_volume_score") or 0), p.get("player_name") or ""),
        "trade_activity_score": lambda p: (-float(p.get("trade_activity_score") or 0), p.get("player_name") or ""),
        "trend_score": lambda p: (-float(p.get("trend_score") or 0), p.get("player_name") or ""),
        "heat_score": lambda p: (-float(p.get("heat_score") or 0), p.get("player_name") or ""),
        "player_name": lambda p: (p.get("player_name") or "").lower(),
    }
    pool.sort(key=sort_keys.get(sort_by, sort_keys["recommendation_score"]))
    if category_id == "trending":
        pool = pool[:25]
    return pool


def hub_categories_for_select():
    opts = [(c["id"], c["label"]) for c in HUB_CATEGORY_DEFS]
    opts.append(("trending", "Trending (in-app signals)"))
    opts.append(("heating_up", "Heating Up (monitoring)"))
    opts.append(("cooling_off", "Cooling Off"))
    opts.append(("steady_demand", "Steady Demand"))
    opts.append(("active_scan", "Active Scan List"))
    opts.append(("my_players", "My Players"))
    return opts


def export_seed_stats() -> Dict[str, Any]:
    return {
        "seed_version": PLAYER_HUB_SEED_VERSION,
        "player_count": len(SEED_PLAYERS),
        "categories": HUB_CATEGORY_DEFS,
    }


def build_discoverable_players_from_results(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Extract players from radar/search-style rows (each needs ``player`` and optional ``deal_quality_score``).
    Returns dict: player display name -> aggregate stats.
    """
    player_map: Dict[str, Dict[str, Any]] = {}

    for r in rows or []:
        if not isinstance(r, dict):
            continue
        player = r.get("player")
        if not player:
            continue
        player = str(player).strip()
        if not player:
            continue

        if player not in player_map:
            player_map[player] = {
                "count": 0,
                "avg_dqs": 0.0,
                "best_dqs": 0.0,
            }

        player_map[player]["count"] += 1

        try:
            dqs = float(r.get("deal_quality_score", 0) or 0)
        except (TypeError, ValueError):
            dqs = 0.0

        player_map[player]["avg_dqs"] += dqs
        player_map[player]["best_dqs"] = max(float(player_map[player]["best_dqs"]), dqs)

    for p in player_map:
        c = int(player_map[p]["count"])
        if c > 0:
            player_map[p]["avg_dqs"] = round(float(player_map[p]["avg_dqs"]) / c, 1)

    return player_map


def rank_discoverable_players(
    player_map: Dict[str, Dict[str, Any]],
) -> List[Tuple[str, float, Dict[str, Any]]]:
    ranked: List[Tuple[str, float, Dict[str, Any]]] = []

    for player, data in (player_map or {}).items():
        score = (
            float(data.get("best_dqs", 0) or 0) * 0.5
            + float(data.get("avg_dqs", 0) or 0) * 0.3
            + float(data.get("count", 0) or 0) * 2.0
        )

        ranked.append((player, score, data))

    ranked.sort(key=lambda x: x[1], reverse=True)

    return ranked
