def calculate_target_bid(market_value):

    fee_percent = 13.25
    shipping_cost = 5
    desired_profit = 20

    fees = market_value * (fee_percent / 100)

    target_bid = market_value - fees - shipping_cost - desired_profit

    return round(target_bid, 2)