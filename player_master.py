"""
Canonical display metadata for known athletes (team / sport / position).

Hub seeds stay authoritative for IDs; this layer corrects common drift in discovery/session rows.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional

PLAYER_MASTER: Dict[str, Dict[str, Any]] = {
    "shohei ohtani": {
        "name": "Shohei Ohtani",
        "sport": "MLB",
        "league": "Baseball",
        "team": "LAD",
        "position": "DH/P",
        "tags": ["mlb_star", "mlb_pitcher", "mlb_hitter"],
    },
    "luka doncic": {
        "name": "Luka Doncic",
        "sport": "NBA",
        "league": "Basketball",
        "team": "LAL",
        "position": "G",
        "tags": ["nba_young_star"],
    },
}


def norm_player_name(name: Optional[str]) -> str:
    return (name or "").strip().lower()


def get_player_master_record(name: Optional[str]) -> Optional[Dict[str, Any]]:
    rec = PLAYER_MASTER.get(norm_player_name(name))
    return deepcopy(rec) if rec else None


def merge_player_with_master(player_row: Optional[dict]) -> dict:
    """
    Apply canonical metadata without destroying app-specific fields.
    Uses ``player_name`` or ``name`` for lookup; writes ``player_name`` (+ ``name`` alias).
    """
    row = deepcopy(player_row or {})
    lookup = row.get("player_name") or row.get("name") or ""
    master = get_player_master_record(str(lookup))
    if not master:
        return row

    out = deepcopy(row)
    disp = master.get("name") or out.get("player_name") or out.get("name")
    if disp:
        out["player_name"] = disp
        out["name"] = disp
    if master.get("sport"):
        out["sport"] = master["sport"]
    if master.get("league"):
        out["league"] = master["league"]
    if master.get("team"):
        out["team"] = master["team"]
    if master.get("position"):
        out["position"] = master["position"]

    master_tags = master.get("tags") or []
    row_tags = out.get("category_tags") or out.get("tags") or []
    if not isinstance(row_tags, list):
        row_tags = []
    merged_tags: List[str] = []
    seen = set()
    for t in list(master_tags) + list(row_tags):
        key = str(t).strip().lower()
        if key and key not in seen:
            merged_tags.append(str(t).strip() if t in master_tags else str(t))
            seen.add(key)
    out["category_tags"] = merged_tags
    return out


def hydrate_players_from_master(players: Optional[List[dict]]) -> List[dict]:
    return [merge_player_with_master(p) for p in (players or [])]


def ensure_default_player_groups(session_state: Any) -> None:
    """Legacy session list: append default pool labels if missing (non-destructive)."""
    session_state.setdefault("player_groups", [])
    defaults = [
        "Young Gun - MLB",
        "Young Gun - NBA",
        "Young Gun - NFL",
        "NBA Legends",
        "NFL QB Chase",
        "NFL Skill Chase",
        "MLB Stars",
        "High Priority",
        "Spec Plays",
    ]
    existing_norm = {str(x).strip().lower() for x in session_state["player_groups"]}
    for grp in defaults:
        if grp.strip().lower() not in existing_norm:
            session_state["player_groups"].append(grp)
            existing_norm.add(grp.strip().lower())
