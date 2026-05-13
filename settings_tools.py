import json
import os

SETTINGS_FILE = "settings.json"


def load_settings():
    defaults = {
        "fee_percent": 13.25,
        "shipping_cost": 5.0,
        "desired_profit": 20.0,
        "default_snipe_seconds": 7.0,
        "auto_target_bid_from_market": True,
        "target_bid_ratio": 0.70,
    }

    if not os.path.exists(SETTINGS_FILE):
        return defaults

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
    except (json.JSONDecodeError, OSError):
        return defaults

    for key, value in defaults.items():
        if key not in saved:
            saved[key] = value

    return saved


def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4)


def view_settings():
    settings = load_settings()

    print("\nCURRENT SETTINGS")
    print("Fee Percent:", settings["fee_percent"])
    print("Shipping Cost:", settings["shipping_cost"])
    print("Desired Profit:", settings["desired_profit"])
    print("Default Snipe Seconds:", settings["default_snipe_seconds"])


def edit_settings():
    settings = load_settings()

    print("\nEDIT SETTINGS")
    print("Leave blank to keep current value.\n")

    fee_text = input(f"Selling fee percent [{settings['fee_percent']}]: ").strip()
    shipping_text = input(f"Shipping cost [{settings['shipping_cost']}]: ").strip()
    profit_text = input(f"Desired profit [{settings['desired_profit']}]: ").strip()
    snipe_text = input(f"Default snipe seconds [{settings['default_snipe_seconds']}]: ").strip()

    try:
        if fee_text:
            settings["fee_percent"] = float(fee_text)
        if shipping_text:
            settings["shipping_cost"] = float(shipping_text)
        if profit_text:
            settings["desired_profit"] = float(profit_text)
        if snipe_text:
            settings["default_snipe_seconds"] = float(snipe_text)
    except ValueError:
        print("Invalid number entered.")
        return

    save_settings(settings)
    print("\nSettings saved.")