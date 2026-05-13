"""
Buy-universe pool snapshot for Buying Radar: built from **current** hub memberships.

Invalidates in-session radar caches when ``player_memberships`` changes so pool filters
and narrow logic stay coherent with Player Hub.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Dict, List, Optional, Sequence, Tuple

import streamlit as st

import player_hub
import player_master
from player_hub_seed import players_by_id

POOL_RUNTIME_ROWS_KEY = "ph_pool_runtime_rows"
POOL_RUNTIME_HASH_KEY = "ph_pool_runtime_hash"
RADAR_INPUTS_VERSION_KEY = "br_radar_inputs_version"


def hub_membership_fingerprint(ph_state: dict) -> str:
    """Stable hash of ``buy_universe.player_memberships`` (order-independent)."""
    bu = ph_state.get("buy_universe") or {}
    pm = bu.get("player_memberships") or {}
    items: List[Tuple[str, Tuple[str, ...]]] = []
    for pid in sorted(pm.keys(), key=str):
        glist = pm.get(pid)
        if not isinstance(glist, list):
            continue
        items.append((str(pid), tuple(sorted(str(g) for g in glist if g))))
    raw = json.dumps(items, separators=(",", ":"), default=str)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def build_runtime_pool_rows_from_hub(ph_state: dict) -> List[dict]:
    """One row per (player, group) from hub state; canonical fields from ``player_master``."""
    player_hub.ensure_buy_universe_seed(ph_state)
    bu = ph_state.get("buy_universe") or {}
    pm = bu.get("player_memberships") or {}
    groups_meta = bu.get("groups") or {}
    seeds = players_by_id()
    rows: List[dict] = []
    seen: set = set()
    for pid, glist in pm.items():
        if not isinstance(glist, list):
            continue
        seed = seeds.get(str(pid)) or {}
        base = {
            "player_id": str(pid),
            "player_name": str(seed.get("player_name") or pid),
            "name": str(seed.get("player_name") or pid),
            "sport": str(seed.get("sport") or ""),
            "team": str(seed.get("team") or ""),
            "position": str(seed.get("position") or ""),
            "category_tags": list(seed.get("category_tags") or []),
        }
        base = player_master.merge_player_with_master(base)
        pkey = player_master.norm_player_name(base.get("player_name"))
        for gid in glist:
            g_str = str(gid)
            meta = groups_meta.get(g_str) if isinstance(groups_meta, dict) else {}
            meta = meta if isinstance(meta, dict) else {}
            label = str(meta.get("label") or g_str)
            dedupe = (g_str.lower(), pkey)
            if dedupe in seen:
                continue
            seen.add(dedupe)
            row = deepcopy(base)
            row["assigned_group"] = label
            row["group_id"] = g_str
            row["player_pool"] = label
            row["player_key"] = pkey
            rows.append(row)
    rows.sort(
        key=lambda r: (
            (r.get("sport") or "").lower(),
            (r.get("assigned_group") or "").lower(),
            (r.get("player_name") or "").lower(),
        )
    )
    return rows


def sync_runtime_pool_to_session(ph_state: dict) -> Tuple[str, List[dict]]:
    rows = build_runtime_pool_rows_from_hub(ph_state)
    fp = hub_membership_fingerprint(ph_state)
    st.session_state[POOL_RUNTIME_ROWS_KEY] = rows
    st.session_state[POOL_RUNTIME_HASH_KEY] = fp
    return fp, rows


def invalidate_buying_radar_cache_after_hub_mutation() -> None:
    st.session_state[RADAR_INPUTS_VERSION_KEY] = int(st.session_state.get(RADAR_INPUTS_VERSION_KEY) or 0) + 1
    st.session_state.pop("br_radar_session_cache", None)


def get_radar_inputs_version() -> int:
    return int(st.session_state.get(RADAR_INPUTS_VERSION_KEY) or 0)


def get_runtime_player_pool_rows(ph_state: dict) -> List[dict]:
    """Return rows, refreshing the session snapshot when hub fingerprint changes."""
    fp = hub_membership_fingerprint(ph_state)
    old = str(st.session_state.get(POOL_RUNTIME_HASH_KEY) or "")
    if old != fp or POOL_RUNTIME_ROWS_KEY not in st.session_state:
        sync_runtime_pool_to_session(ph_state)
    return list(st.session_state.get(POOL_RUNTIME_ROWS_KEY) or [])


def buying_radar_cache_stale(ph_state: dict, cache: Optional[dict]) -> bool:
    """True if cached radar results should not be shown (membership or version drift)."""
    if not isinstance(cache, dict):
        return True
    cur_fp = hub_membership_fingerprint(ph_state)
    if str(cache.get("hub_membership_fingerprint") or "") != cur_fp:
        return True
    cur_ver = get_radar_inputs_version()
    try:
        cached_ver = int(cache.get("br_radar_inputs_version") or 0)
    except (TypeError, ValueError):
        cached_ver = 0
    return cached_ver != cur_ver


def build_effective_radar_player_inputs(
    ph_state: dict,
    *,
    selected_pool_ids: Optional[Sequence[str]] = None,
    selected_sport: Optional[str] = None,
) -> Tuple[List[dict], List[str]]:
    rows = get_runtime_player_pool_rows(ph_state)
    want_pools = {str(x) for x in (selected_pool_ids or []) if str(x).strip()}
    sport_u = str(selected_sport or "").strip().upper()
    out_rows: List[dict] = []
    for row in rows:
        if want_pools and str(row.get("group_id") or "") not in want_pools:
            continue
        if sport_u and str(row.get("sport") or "").strip().upper() != sport_u:
            continue
        out_rows.append(row)
    names = sorted({str(r.get("player_name") or r.get("name") or "") for r in out_rows if r.get("player_name") or r.get("name")})
    return out_rows, names
