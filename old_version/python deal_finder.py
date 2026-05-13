import csv
import os

FILE_NAME = "watchlist.csv"

def setup_file():
    if not os.path.exists(FILE_NAME):
        with open(FILE_NAME, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "card_name",
                "current_price",
                "market_value",
                "max_buy_price",
                "estimated_profit",
                "notes"
            ])

def add_card():
    card_name = input("Card name: ")
    current_price = float(input("Current auction price: "))
    market_value = float(input("Estimated market value: "))

    max_buy_price = market_value * 0.70
    estimated_profit = market_value - current_price

    if current_price <= max_buy_price:
        notes = "GOOD DEAL"
    else:
        notes = "PASS"

    with open(FILE_NAME, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            card_name,
            current_price,
            market_value,
            round(max_buy_price, 2),
            round(estimated_profit, 2),
            notes
        ])

    print("\nSaved to watchlist.csv")
    print("Max buy price:", round(max_buy_price, 2))
    print("Estimated profit:", round(estimated_profit, 2))
    print("Decision:", notes)

setup_file()
add_card()