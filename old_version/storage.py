import csv
import os

WATCHLIST_FILE = "watchlist.csv"


def read_watchlist_rows():
    if not os.path.exists(WATCHLIST_FILE):
        return []

    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def write_watchlist_rows(rows):

    fieldnames = [
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
        "notes",
        "status"
    ]

    with open(WATCHLIST_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        writer.writeheader()

        for row in rows:
            writer.writerow(row)