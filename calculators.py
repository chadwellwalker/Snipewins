from settings_tools import load_settings


def get_float(prompt):
    while True:
        value = input(prompt).strip()
        try:
            return float(value)
        except ValueError:
            print("Please enter a valid number.")


def calculate_target_bid(market_value, fee_percent=None, shipping_cost=None, desired_profit=None):
    settings = load_settings()

    if fee_percent is None:
        fee_percent = settings["fee_percent"]
    if shipping_cost is None:
        shipping_cost = settings["shipping_cost"]
    if desired_profit is None:
        desired_profit = settings["desired_profit"]

    fees = market_value * (fee_percent / 100)
    target_bid = market_value - fees - shipping_cost - desired_profit
    return round(target_bid, 2)