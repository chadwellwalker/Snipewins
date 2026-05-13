"""
Discover inbox ↔ My Players portfolio — backed by ``player_hub_state.json``.

- **Inbox** = not in any buy-universe group **and** not flagged ``is_added_to_my_players``.
- **Promote** = add to a group + set My Players + save (removes from inbox).
- **Return** = strip all group memberships + clear My Players + save (back to inbox).

No parallel Streamlit-only player lists; state keys stay under ``player_hub`` + ``buy_universe``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import player_hub
import player_master


def is_discover_inbox_row(profile_row: dict, ph_state: dict) -> bool:
    """True if this row should appear under **Discover Players** (intake inbox)."""
    if not isinstance(profile_row, dict):
        return False
    pid = str(profile_row.get("player_id") or "").strip()
    if not pid:
        return True
    if player_hub.player_has_any_group_membership(ph_state, pid):
        return False
    if bool(profile_row.get("is_added_to_my_players")):
        return False
    return True


def filter_discover_inbox(candidate_rows: List[dict], ph_state: dict) -> List[dict]:
    return [p for p in (candidate_rows or []) if is_discover_inbox_row(p, ph_state)]


def promote_from_discovery(ph_state: dict, player_id: str, group_id: str) -> dict:
    """Assign to group and mark My Players (persist via save_player_hub_state by caller)."""
    pid = str(player_id or "").strip()
    gid = str(group_id or "").strip()
    if not pid or not gid:
        return ph_state
    st = player_hub.set_player_group_membership(ph_state, pid, gid, True)
    st = player_hub.set_my_player(st, pid, True)
    return st


def return_to_discover_inbox(ph_state: dict, player_id: str) -> dict:
    """Remove from all groups and My Players → back to Discover inbox."""
    pid = str(player_id or "").strip()
    if not pid:
        return ph_state
    st = ph_state
    for gid in list(player_hub.get_player_group_ids(st, pid)):
        st = player_hub.set_player_group_membership(st, pid, gid, False)
    st = player_hub.set_my_player(st, pid, False)
    return st


def resolve_group_id_from_label(ph_state: dict, label: str) -> Optional[str]:
    """Match human pool/group label to ``buy_universe.groups`` id."""
    want = (label or "").strip().lower()
    if not want:
        return None
    for r in player_hub.list_buy_universe_groups(ph_state):
        lab = str(r.get("label") or "").strip().lower()
        gid = str(r.get("group_id") or "").strip()
        if lab == want and gid:
            return gid
    return None


def merge_profile_display_fields(profile_row: dict) -> dict:
    """Apply ``player_master`` canonical team/sport/position for UI (copy-safe)."""
    return player_master.merge_player_with_master(dict(profile_row or {}))


def build_portfolio_profiles(all_profiles: List[dict], ph_state: dict) -> List[dict]:
    """
    My Players portfolio: in at least one buy-universe group **or** on My Players list.
    Deduped by ``player_id``, stable order (first-seen).
    """
    seen: set = set()
    out: List[dict] = []
    for p in all_profiles or []:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("player_id") or "").strip()
        if not pid:
            continue
        if pid in seen:
            continue
        in_pool = player_hub.player_has_any_group_membership(ph_state, pid)
        is_my = bool(p.get("is_added_to_my_players"))
        if in_pool or is_my:
            seen.add(pid)
            out.append(p)
    return out
