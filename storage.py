import csv
import os

WATCHLIST_FILE = "watchlist.csv"


def get_watchlist_fieldnames():
    return [
        "card_name",
        "current_price",
        "market_value",
        "max_buy_price",
        "estimated_profit",
        "decision",
        "auction_end_time",
        "snipe_seconds",
        "snipe_time",
        "target_bid",
        "item_url",
        "image_url",
        "market_value_source",
        "market_value_updated_at",
        "market_value_confidence",
        "comp_count",
        "last_comp_date",
        "valuation_notes",
        "value_range_low",
        "value_range_high",
        "notes",
        "status",
        "valuation_strength",
        "valuation_flow_label",
    ]


def ensure_watchlist_row_keys(row):
    """Fill missing CSV columns so DictWriter never fails; ignore unknown keys."""
    out = dict(row or {})
    for k in get_watchlist_fieldnames():
        out.setdefault(k, "")
    return out


def setup_watchlist():
    if not os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=get_watchlist_fieldnames())
            writer.writeheader()


def read_watchlist_rows():
    setup_watchlist()

    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_watchlist_rows(rows):
    fieldnames = get_watchlist_fieldnames()
    with open(WATCHLIST_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=fieldnames, extrasaction="ignore"
        )
        writer.writeheader()
        for row in rows or []:
            writer.writerow(ensure_watchlist_row_keys(row))
