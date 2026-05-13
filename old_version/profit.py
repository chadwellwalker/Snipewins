purchase_price = float(input("Purchase price: "))
expected_sale_price = float(input("Expected resale price: "))
shipping_cost = float(input("Shipping cost: "))
fee_percent = float(input("Platform fee percent: "))

fees = expected_sale_price * (fee_percent / 100)
profit = expected_sale_price - fees - shipping_cost - purchase_price

print("Fees:", round(fees, 2))
print("Net profit:", round(profit, 2))