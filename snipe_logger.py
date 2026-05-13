"""
Snipe Logger — append snipe attempts to snipe_log.csv and read them back.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime
from typing import Optional

import pandas as pd

_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snipe_log.csv")

_COLUMNS = [
    "timestamp",
    "player",
    "card_description",
    "title",
    "listing_id",
    "current_bid",
    "market_value",
    "snipe_bid",
    "result",
    "error_message",
]


def log_snipe(
    *,
    player: str,
    card_description: str,
    listing_id: str,
    current_bid: float,
    market_value: float,
    snipe_bid: float,
    result: str,
    error_message: str = "",
    title: str = "",
) -> None:
    """Append one row to snipe_log.csv.  Creates the file + header if needed."""
    file_exists = os.path.isfile(_LOG_PATH)
    with open(_LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "player": player,
                "card_description": card_description,
                "title": title[:120],
                "listing_id": listing_id,
                "current_bid": f"{current_bid:.2f}",
                "market_value": f"{market_value:.2f}" if market_value else "",
                "snipe_bid": f"{snipe_bid:.2f}",
                "result": result,
                "error_message": error_message[:300],
            }
        )


def load_log() -> Optional[pd.DataFrame]:
    """Return the full snipe log as a DataFrame, newest first. None if empty."""
    if not os.path.isfile(_LOG_PATH):
        return None
    try:
        df = pd.read_csv(_LOG_PATH, dtype=str)
        if df.empty:
            return None
        # newest first
        df = df.iloc[::-1].reset_index(drop=True)
        return df
    except Exception:
        return None


def log_path() -> str:
    return _LOG_PATH
