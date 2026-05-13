WATCHLIST_FILE = "watchlist.csv"
SETTINGS_FILE = "settings.json"
BACKUP_FILE = "watchlist_backup.csv"
GOOD_DEALS_EXPORT_FILE = "good_deals_export.csv"
ENDING_SOON_EXPORT_FILE = "ending_soon_export.csv"


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
        "notes",
        "status"
    ]