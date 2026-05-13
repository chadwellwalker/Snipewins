"""
Buy-universe player group helpers for Player Hub.

Groups live in ``player_hub_state.json`` under ``buy_universe.groups`` and
``player_memberships`` — not in a parallel Streamlit-only dict. This module
wraps :mod:`player_hub` for UI-friendly labels, suggestions, and pick lists.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import player_hub


def list_all_groups(state: Dict[str, Any]) -> List[Dict[str, str]]:
    """All group rows (id, label, sport), sorted by label."""
    player_hub.ensure_buy_universe_seed(state)
    return player_hub.list_buy_universe_groups(state)


def build_group_select_options(state: Dict[str, Any]) -> List[Tuple[str, str]]:
    """(group_id, display_label) for selectboxes; label shows human name + id."""
    out: List[Tuple[str, str]] = []
    for r in list_all_groups(state):
        gid = str(r.get("group_id") or "")
        lab = str(r.get("label") or gid)
        if not gid:
            continue
        sp = str(r.get("sport") or "").strip()
        disp = f"{lab} ({gid})" + (f" · {sp}" if sp else "")
        out.append((gid, disp))
    return out


def format_current_groups_line(state: Dict[str, Any], player_id: str) -> str:
    """Markdown line listing current memberships (all groups)."""
    pid = str(player_id or "").strip()
    gids = player_hub.get_player_group_ids(state, pid)
    bu = (state.get("buy_universe") or {}).get("groups") or {}
    if not gids:
        return "**Current groups:** ⚪ _None_"
    parts: List[str] = []
    for gid in gids:
        meta = bu.get(gid) if isinstance(bu.get(gid), dict) else {}
        lab = str((meta or {}).get("label") or gid)
        parts.append(f"**{lab}** (`{gid}`)")
    return "**Current groups:** 🟢 " + " · ".join(parts)


def suggest_group_id_from_profile(player_row: Dict[str, Any], state: Dict[str, Any]) -> Optional[str]:
    """
    Light heuristic: rookies/young → Young Gun for sport; legends → first group with 'legend' in label.
    """
    tags_l: List[str] = []
    for k in ("category_tags", "universe_tags"):
        for t in player_row.get(k) or []:
            tags_l.append(str(t).lower())
    sport = str(player_row.get("sport") or "").strip()
    code = player_hub.normalize_hub_sport(sport)

    if any("rook" in t or "young" in t or "prospect" in t for t in tags_l):
        yg = player_hub.young_gun_group_id_for_sport(code)
        if yg:
            return yg

    if any("legend" in t or "goat" in t for t in tags_l):
        for r in list_all_groups(state):
            lab = str(r.get("label") or "").lower()
            gid = str(r.get("group_id") or "")
            if "legend" in lab or "goat" in lab:
                return gid

    if any("star" in t for t in tags_l):
        for r in list_all_groups(state):
            lab = str(r.get("label") or "").lower()
            gid = str(r.get("group_id") or "")
            if "star" in lab and "young" not in lab:
                return gid

    return None


def suggest_group_label(state: Dict[str, Any], group_id: Optional[str]) -> str:
    if not group_id:
        return ""
    bu = (state.get("buy_universe") or {}).get("groups") or {}
    meta = bu.get(group_id) if isinstance(bu.get(group_id), dict) else {}
    return str((meta or {}).get("label") or group_id)


def memberships_for_removal(state: Dict[str, Any], player_id: str) -> List[Tuple[str, str]]:
    """Groups the player is in, as (group_id, display_label)."""
    pid = str(player_id or "").strip()
    opts = build_group_select_options(state)
    gid_set = set(player_hub.get_player_group_ids(state, pid))
    return [(gid, lab) for gid, lab in opts if gid in gid_set]
