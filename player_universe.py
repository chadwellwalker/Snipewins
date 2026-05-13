"""
Preloaded Player Hub universe (JSON-backed, easy to extend).

Merged into hub seed maps by :func:`extend_seed_map_with_universe` — existing
``player_hub_seed.SEED_PLAYERS`` entries always win on ``player_id`` collision.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

UNIVERSE_FILENAME = "player_universe_seed.json"


def universe_json_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), UNIVERSE_FILENAME)


def _default_row(raw: Dict[str, Any]) -> Dict[str, Any]:
    pid = str(raw.get("player_id") or "").strip()
    name = str(raw.get("player_name") or raw.get("display_name") or pid).strip()
    tags = raw.get("tags") or raw.get("universe_tags") or []
    if not isinstance(tags, list):
        tags = []
    cats = raw.get("category_tags")
    if not isinstance(cats, list):
        cats = list(tags) if tags else []
    mt = raw.get("match_tokens")
    if not isinstance(mt, list):
        mt = [name.lower()] if name else []
    hint = str(raw.get("search_query_hint") or f"{name} rookie card").strip()
    return {
        "player_id": pid,
        "player_name": name,
        "display_name": str(raw.get("display_name") or name).strip(),
        "sport": str(raw.get("sport") or "").strip(),
        "league": str(raw.get("league") or "").strip(),
        "team": str(raw.get("team") or "").strip(),
        "position": str(raw.get("position") or "").strip(),
        "rookie_year": raw.get("rookie_year"),
        "category_tags": [str(x) for x in cats if str(x).strip()],
        "tags": [str(x) for x in tags if str(x).strip()],
        "match_tokens": [str(x).strip().lower() for x in mt if str(x).strip()],
        "search_query_hint": hint[:240],
        "seed_source": str(raw.get("seed_source") or "player_universe_seed.json"),
        "seed_priority": int(raw.get("seed_priority") or 50),
        "active": bool(raw.get("active", True)),
    }


def load_universe_players() -> List[Dict[str, Any]]:
    path = universe_json_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("players") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    out: List[Dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        pid = str(raw.get("player_id") or "").strip()
        if not pid:
            continue
        out.append(_default_row(raw))
    return out


def extend_seed_map_with_universe(base: Dict[str, Dict[str, Any]]) -> None:
    """
    In-place: add JSON universe players whose ``player_id`` is not already in ``base``.
    """
    for row in load_universe_players():
        pid = row.get("player_id")
        if not pid or pid in base:
            continue
        base[pid] = row
