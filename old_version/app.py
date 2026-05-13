import csv
import os
import time
import json
from datetime import datetime, timedelta
from old_version.constants import *
from storage import *
from old_version.settings_tools import *
from old_version.calculators import *
import old_version.ebay_tools as ebay_tools

WATCHLIST_FILE = "watchlist.csv"
SETTINGS_FILE = "settings.json"
BACKUP_FILE = "watchlist_backup.csv"
GOOD_DEALS_EXPORT_FILE = "good_deals_export.csv"
ENDING_SOON_EXPORT_FILE = "ending_soon_export.csv"

def setup_watchlist():
    if not os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "card_name",
                "current_price",
                "market_value",
                "max_buy_price",
                "estimated_profit",
                "decision",
                "auction_end_time",
                "target_bid",
                "notes"
            ])

def view_ending_soon():
    print("\nENDING SOON WATCHLIST")

    if not os.path.exists(WATCHLIST_FILE):
        print("No watchlist file found yet.")
        return

    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("No cards saved yet.")
        return

    now = datetime.now()
    soon_rows = []

    for row in rows:
        end_text = row.get("auction_end_time", "").strip()
        if not end_text:
            continue

        try:
            end_time = datetime.strptime(end_text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

        seconds_left = (end_time - now).total_seconds()

        if seconds_left > 0:
            soon_rows.append((seconds_left, row))

    if not soon_rows:
        print("No active auction times found.")
        return

    soon_rows.sort(key=lambda x: x[0])

    for seconds_left, row in soon_rows:
        minutes = int(seconds_left // 60)
        seconds = int(seconds_left % 60)

        try:
            current_price = float(row.get("current_price", 0))
            target_bid = float(row.get("target_bid", 0))
            bid_gap = calculate_bid_gap(current_price, target_bid)
            bid_status = get_bid_status(current_price, target_bid)
        except ValueError:
            bid_gap = ""
            bid_status = ""

        print("Card:", row["card_name"])
        print("Current Price:", row["current_price"])
        print("Market Value:", row["market_value"])
        print("Max Buy:", row["max_buy_price"])
        print("Target Bid:", row.get("target_bid", ""))
        print("Bid Gap:", bid_gap)
        print("Bid Status:", bid_status)
        print("Decision:", row["decision"])
        print("Ends:", row["auction_end_time"])
        print("Snipe Time:", row.get("snipe_time", ""))
        print("Notes:", row.get("notes", ""))

def top_deals_radar():
    print("\nTOP DEALS RADAR")

    if not os.path.exists(WATCHLIST_FILE):
        print("No watchlist file found yet.")
        return

    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("No cards saved yet.")
        return

    now = datetime.now()
    deals = []

    for row in rows:
        decision = row.get("decision", "").strip().upper()
        if decision != "GOOD DEAL":
            continue

        end_text = row.get("auction_end_time", "").strip()

        if end_text:
            try:
                end_time = datetime.strptime(end_text, "%Y-%m-%d %H:%M:%S")
                seconds_left = (end_time - now).total_seconds()
            except ValueError:
                seconds_left = float("inf")
        else:
            seconds_left = float("inf")

        try:
            estimated_profit = float(row.get("estimated_profit", 0))
        except ValueError:
            estimated_profit = 0.0

        deals.append((seconds_left, -estimated_profit, row))

    if not deals:
        print("No GOOD DEAL cards found.")
        return

    sort_mode = input("Sort by (1) ending soonest or (2) biggest profit? ").strip()

    if sort_mode == "2":
        deals.sort(key=lambda x: (x[1], x[0]))
    else:
        deals.sort(key=lambda x: (x[0], x[1]))
    for seconds_left, neg_profit, row in deals:
        try:
            current_price = float(row.get("current_price", 0))
            target_bid = float(row.get("target_bid", 0))
            bid_gap = calculate_bid_gap(current_price, target_bid)
            bid_status = get_bid_status(current_price, target_bid)
        except ValueError:
            bid_gap = ""
            bid_status = ""

        print("Card:", row.get("card_name", ""))
        print("Current Price:", row.get("current_price", ""))
        print("Market Value:", row.get("market_value", ""))
        print("Max Buy:", row.get("max_buy_price", ""))
        print("Target Bid:", row.get("target_bid", ""))
        print("Bid Gap:", bid_gap)
        print("Bid Status:", bid_status)
        print("Estimated Profit:", row.get("estimated_profit", ""))
        print("Decision:", row.get("decision", ""))
        print("Notes:", row.get("notes", ""))
        end_text = row.get("auction_end_time", "").strip()
        snipe_text = row.get("snipe_time", "").strip()

        if seconds_left != float("inf") and seconds_left > 0:
            minutes = int(seconds_left // 60)
            seconds = int(seconds_left % 60)
            print(f"Time Left: {minutes}m {seconds}s")
        elif seconds_left != float("inf"):
            print("Time Left: Auction ended")

        if end_text:
            print("Ends:", end_text)
        if snipe_text:
            print("Snipe Time:", snipe_text)

        print("------")

def profit_leaderboard():
    print("\nPROFIT LEADERBOARD")

    if not os.path.exists(WATCHLIST_FILE):
        print("No watchlist file found yet.")
        return

    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("No cards saved yet.")
        return

    leaderboard = []

    for row in rows:
        try:
            profit = float(row.get("estimated_profit", 0))
        except ValueError:
            profit = 0

        leaderboard.append((profit, row))

    leaderboard.sort(reverse=True)

    for profit, row in leaderboard[:10]:
        print("Card:", row.get("card_name", ""))
        print("Current Price:", row.get("current_price", ""))
        print("Market Value:", row.get("market_value", ""))
        print("Target Bid:", row.get("target_bid", ""))
        print("Estimated Profit:", profit)
        print("------")
        print("Notes:", row.get("notes", ""))        

def sniper_alerts():
    print("\nSNIPER ALERTS")

    if not os.path.exists(WATCHLIST_FILE):
        print("No watchlist file found yet.")
        return

    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("No cards saved yet.")
        return

    now = datetime.now()
    found_alert = False

    for row in rows:
        end_text = row.get("auction_end_time", "").strip()
        snipe_seconds_text = row.get("snipe_seconds", "").strip()

        if not end_text or not snipe_seconds_text:
            continue

        try:
            end_time = datetime.strptime(end_text, "%Y-%m-%d %H:%M:%S")
            snipe_seconds = float(snipe_seconds_text)
        except ValueError:
            continue

        seconds_left = (end_time - now).total_seconds()

        if 0 < seconds_left <= snipe_seconds:
            found_alert = True
            print("BID NOW:", row.get("card_name", ""))
            print("Current Price:", row.get("current_price", ""))
            print("Target Bid:", row.get("target_bid", ""))
            print("Ends:", row.get("auction_end_time", ""))
            print("Seconds Left:", round(seconds_left, 2))
            print("------")

    if not found_alert:
        print("No cards are inside the snipe window right now.")

def live_sniper_monitor():
    print("\nLIVE SNIPER MONITOR")

    duration_seconds = int(get_float("How many seconds should the monitor run? "))

    if duration_seconds <= 0:
        print("Please enter a number greater than 0.")
        return

    print("Watching for sniper alerts...")
    print("Press Ctrl + C to stop early.\n")

    start_time = datetime.now()

    try:
        while True:
            now = datetime.now()
            elapsed = (now - start_time).total_seconds()

            if elapsed >= duration_seconds:
                print("\nMonitor finished.")
                break

            if not os.path.exists(WATCHLIST_FILE):
                print("No watchlist file found yet.")
                break

            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

            found_alert = False

            for row in rows:
                end_text = row.get("auction_end_time", "").strip()
                snipe_seconds_text = row.get("snipe_seconds", "").strip()

                if not end_text or not snipe_seconds_text:
                    continue

                try:
                    end_time = datetime.strptime(end_text, "%Y-%m-%d %H:%M:%S")
                    snipe_seconds = float(snipe_seconds_text)
                except ValueError:
                    continue

                seconds_left = (end_time - now).total_seconds()

                if 0 < seconds_left <= snipe_seconds:
                    found_alert = True
                    print("BID NOW:", row.get("card_name", ""))
                    print("Current Price:", row.get("current_price", ""))
                    print("Target Bid:", row.get("target_bid", ""))
                    print("Ends:", row.get("auction_end_time", ""))
                    print("Seconds Left:", round(seconds_left, 2))
                    print("------")

            if not found_alert:
                print("No sniper alerts at", now.strftime("%H:%M:%S"))

            time.sleep(1)

    except KeyboardInterrupt:
        print("\nMonitor stopped.")

def load_sample_data():
    print("\nLOAD SAMPLE DATA")

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

    now = datetime.now()

    sample_cards = [
{
    "card_name": "Lamar Jackson Rookie Auto",
    "current_price": "220.0",
    "market_value": "250.0",
    "max_buy_price": "175.0",
    "estimated_profit": "30.0",
    "decision": "PASS",
    "auction_end_time": (now.replace(microsecond=0) + timedelta(minutes=40)).strftime("%Y-%m-%d %H:%M:%S"),
    "snipe_seconds": "7.0",
    "snipe_time": (now.replace(microsecond=0) + timedelta(minutes=40, seconds=-7)).strftime("%Y-%m-%d %H:%M:%S"),
    "target_bid": "191.88",
    "notes": "Already too expensive",
    "status": "WATCHING"
},
        {
            "card_name": "Josh Allen Prizm Rookie",
            "current_price": "150.0",
            "market_value": "260.0",
            "max_buy_price": "182.0",
            "estimated_profit": "110.0",
            "decision": "GOOD DEAL",
            "auction_end_time": (now.replace(microsecond=0) + timedelta(minutes=25)).strftime("%Y-%m-%d %H:%M:%S"),
            "snipe_seconds": "7.0",
            "snipe_time": (now.replace(microsecond=0) + timedelta(minutes=25, seconds=-7)).strftime("%Y-%m-%d %H:%M:%S"),
            "target_bid": "200.55"
        },
        {
            "card_name": "Lamar Jackson Rookie Auto",
            "current_price": "220.0",
            "market_value": "250.0",
            "max_buy_price": "175.0",
            "estimated_profit": "30.0",
            "decision": "PASS",
            "auction_end_time": (now.replace(microsecond=0) + timedelta(minutes=40)).strftime("%Y-%m-%d %H:%M:%S"),
            "snipe_seconds": "7.0",
            "snipe_time": (now.replace(microsecond=0) + timedelta(minutes=40, seconds=-7)).strftime("%Y-%m-%d %H:%M:%S"),
            "target_bid": "191.88"
        }
    ]

    file_exists = os.path.exists(WATCHLIST_FILE)

    if not file_exists:
        with open(WATCHLIST_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

    with open(WATCHLIST_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        for card in sample_cards:
            writer.writerow(card)

    print("Loaded 3 sample cards into watchlist.csv")

def reset_watchlist():
    print("\nRESET WATCHLIST")

    confirm = input("Type YES to erase watchlist.csv: ").strip()

    if confirm != "YES":
        print("Reset cancelled.")
        return

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
        "notes"
    ]

    with open(WATCHLIST_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(fieldnames)

    print("watchlist.csv has been reset.")

def dashboard_summary():
    print("\nDASHBOARD SUMMARY")

    if not os.path.exists(WATCHLIST_FILE):
        print("No watchlist file found yet.")
        return

    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("No cards saved yet.")
        return

    now = datetime.now()

    total_cards = len(rows)
    good_deals = 0
    pass_cards = 0
    ending_soon = 0
    best_profit = None
    best_profit_row = None

    for row in rows:
        decision = row.get("decision", "").strip().upper()

        if decision == "GOOD DEAL":
            good_deals += 1
        elif decision == "PASS":
            pass_cards += 1

        end_text = row.get("auction_end_time", "").strip()
        if end_text:
            try:
                end_time = datetime.strptime(end_text, "%Y-%m-%d %H:%M:%S")
                seconds_left = (end_time - now).total_seconds()
                if 0 < seconds_left <= 3600:
                    ending_soon += 1
            except ValueError:
                pass

        try:
            profit = float(row.get("estimated_profit", 0))
            if best_profit is None or profit > best_profit:
                best_profit = profit
                best_profit_row = row
        except ValueError:
            pass

    print("Total Cards:", total_cards)
    print("GOOD DEAL Cards:", good_deals)
    print("PASS Cards:", pass_cards)
    print("Ending Within 1 Hour:", ending_soon)

    if best_profit_row:
        print("\nBEST PROFIT CARD")
        print("Card:", best_profit_row.get("card_name", ""))
        print("Current Price:", best_profit_row.get("current_price", ""))
        print("Market Value:", best_profit_row.get("market_value", ""))
        print("Target Bid:", best_profit_row.get("target_bid", ""))
        print("Estimated Profit:", best_profit)

def search_cards():
    print("\nSEARCH CARDS")

    if not os.path.exists(WATCHLIST_FILE):
        print("No watchlist file found yet.")
        return

    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("No cards saved yet.")
        return

    search_term = input("Enter player name or keyword: ").strip().lower()

    if not search_term:
        print("Please enter a search term.")
        return

    matches = []

    for row in rows:
        card_name = row.get("card_name", "").lower()
        notes = row.get("notes", "").lower()

        if search_term in card_name or search_term in notes:
            matches.append(row)

    if not matches:
        print("No matching cards found.")
        return

    for row in matches:
        print("Card:", row.get("card_name", ""))
        print("Current Price:", row.get("current_price", ""))
        print("Market Value:", row.get("market_value", ""))
        print("Target Bid:", row.get("target_bid", ""))
        print("Decision:", row.get("decision", ""))
        print("Auction End:", row.get("auction_end_time", ""))
        print("Notes:", row.get("notes", ""))
        print("------")

def search_good_deals():
    print("\nSEARCH GOOD DEALS")

    if not os.path.exists(WATCHLIST_FILE):
        print("No watchlist file found yet.")
        return

    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("No cards saved yet.")
        return

    search_term = input("Enter player name or keyword: ").strip().lower()

    if not search_term:
        print("Please enter a search term.")
        return

    matches = []

    for row in rows:
        card_name = row.get("card_name", "").lower()
        notes = row.get("notes", "").lower()
        decision = row.get("decision", "").strip().upper()

        if decision == "GOOD DEAL" and (search_term in card_name or search_term in notes):
            matches.append(row)

    if not matches:
        print("No GOOD DEAL matches found.")
        return

    for row in matches:
        print("Card:", row.get("card_name", ""))
        print("Current Price:", row.get("current_price", ""))
        print("Market Value:", row.get("market_value", ""))
        print("Target Bid:", row.get("target_bid", ""))
        print("Estimated Profit:", row.get("estimated_profit", ""))
        print("Decision:", row.get("decision", ""))
        print("Auction End:", row.get("auction_end_time", ""))
        print("Notes:", row.get("notes", ""))
        print("------")


def search_pass_cards():
    print("\nSEARCH PASS CARDS")

    if not os.path.exists(WATCHLIST_FILE):
        print("No watchlist file found yet.")
        return

    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("No cards saved yet.")
        return

    search_term = input("Enter player name or keyword: ").strip().lower()

    if not search_term:
        print("Please enter a search term.")
        return

    matches = []

    for row in rows:
        card_name = row.get("card_name", "").lower()
        notes = row.get("notes", "").lower()
        decision = row.get("decision", "").strip().upper()

        if decision == "PASS" and (search_term in card_name or search_term in notes):
            matches.append(row)

    if not matches:
        print("No PASS matches found.")
        return

    for row in matches:
        print("Card:", row.get("card_name", ""))
        print("Current Price:", row.get("current_price", ""))
        print("Market Value:", row.get("market_value", ""))
        print("Target Bid:", row.get("target_bid", ""))
        print("Estimated Profit:", row.get("estimated_profit", ""))
        print("Decision:", row.get("decision", ""))
        print("Auction End:", row.get("auction_end_time", ""))
        print("Notes:", row.get("notes", ""))
        print("------")


def search_ending_soon():
    print("\nSEARCH ENDING SOON")

    if not os.path.exists(WATCHLIST_FILE):
        print("No watchlist file found yet.")
        return

    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("No cards saved yet.")
        return

    search_term = input("Enter player name or keyword: ").strip().lower()

    if not search_term:
        print("Please enter a search term.")
        return

    now = datetime.now()
    matches = []

    for row in rows:
        card_name = row.get("card_name", "").lower()
        notes = row.get("notes", "").lower()
        end_text = row.get("auction_end_time", "").strip()

        if search_term not in card_name and search_term not in notes:
            continue

        if not end_text:
            continue

        try:
            end_time = datetime.strptime(end_text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

        seconds_left = (end_time - now).total_seconds()

        if seconds_left > 0:
            matches.append((seconds_left, row))

    if not matches:
        print("No ending-soon matches found.")
        return

    matches.sort(key=lambda x: x[0])

    for seconds_left, row in matches:
        minutes = int(seconds_left // 60)
        seconds = int(seconds_left % 60)

        print("Card:", row.get("card_name", ""))
        print("Current Price:", row.get("current_price", ""))
        print("Target Bid:", row.get("target_bid", ""))
        print("Estimated Profit:", row.get("estimated_profit", ""))
        print("Decision:", row.get("decision", ""))
        print("Auction End:", row.get("auction_end_time", ""))
        print("Time Left:", f"{minutes}m {seconds}s")
        print("Notes:", row.get("notes", ""))
        print("------")


def search_best_profit():
    print("\nSEARCH BEST PROFIT")

    if not os.path.exists(WATCHLIST_FILE):
        print("No watchlist file found yet.")
        return

    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("No cards saved yet.")
        return

    search_term = input("Enter player name or keyword: ").strip().lower()

    if not search_term:
        print("Please enter a search term.")
        return

    matches = []

    for row in rows:
        card_name = row.get("card_name", "").lower()
        notes = row.get("notes", "").lower()

        if search_term in card_name or search_term in notes:
            try:
                profit = float(row.get("estimated_profit", 0))
            except ValueError:
                profit = 0.0

            matches.append((profit, row))

    if not matches:
        print("No matching cards found.")
        return

    matches.sort(key=lambda x: x[0], reverse=True)

    for profit, row in matches:
        print("Card:", row.get("card_name", ""))
        print("Current Price:", row.get("current_price", ""))
        print("Market Value:", row.get("market_value", ""))
        print("Target Bid:", row.get("target_bid", ""))
        print("Estimated Profit:", profit)
        print("Decision:", row.get("decision", ""))
        print("Auction End:", row.get("auction_end_time", ""))
        print("Notes:", row.get("notes", ""))
        print("------")


def search_summary():
    print("\nSEARCH SUMMARY")

    if not os.path.exists(WATCHLIST_FILE):
        print("No watchlist file found yet.")
        return

    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("No cards saved yet.")
        return

    search_term = input("Enter player name or keyword: ").strip().lower()

    if not search_term:
        print("Please enter a search term.")
        return

    total_matches = 0
    good_deals = 0
    pass_cards = 0
    best_profit = None
    best_card = ""

    for row in rows:
        card_name = row.get("card_name", "").lower()
        notes = row.get("notes", "").lower()

        if search_term in card_name or search_term in notes:
            total_matches += 1

            decision = row.get("decision", "").strip().upper()
            if decision == "GOOD DEAL":
                good_deals += 1
            elif decision == "PASS":
                pass_cards += 1

            try:
                profit = float(row.get("estimated_profit", 0))
                if best_profit is None or profit > best_profit:
                    best_profit = profit
                    best_card = row.get("card_name", "")
            except ValueError:
                pass

    if total_matches == 0:
        print("No matching cards found.")
        return

    print("Matches:", total_matches)
    print("GOOD DEAL:", good_deals)
    print("PASS:", pass_cards)
    print("Best Profit Card:", best_card)
    print("Best Estimated Profit:", best_profit if best_profit is not None else "")

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



    with open(WATCHLIST_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def export_good_deals():
    print("\nEXPORT GOOD DEALS")

    rows = read_watchlist_rows()
    if not rows:
        print("No cards saved yet.")
        return

    good_rows = []
    for row in rows:
        if row.get("decision", "").strip().upper() == "GOOD DEAL":
            good_rows.append(row)

    if not good_rows:
        print("No GOOD DEAL cards to export.")
        return

    with open(GOOD_DEALS_EXPORT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=get_watchlist_fieldnames())
        writer.writeheader()
        writer.writerows(good_rows)

    print(f"Exported {len(good_rows)} GOOD DEAL card(s) to {GOOD_DEALS_EXPORT_FILE}")


def export_ending_soon():
    print("\nEXPORT ENDING SOON")

    rows = read_watchlist_rows()
    if not rows:
        print("No cards saved yet.")
        return

    now = datetime.now()
    soon_rows = []

    for row in rows:
        end_text = row.get("auction_end_time", "").strip()
        if not end_text:
            continue

        try:
            end_time = datetime.strptime(end_text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

        seconds_left = (end_time - now).total_seconds()

        if 0 < seconds_left <= 3600:
            soon_rows.append(row)

    if not soon_rows:
        print("No cards ending within 1 hour.")
        return

    with open(ENDING_SOON_EXPORT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=get_watchlist_fieldnames())
        writer.writeheader()
        writer.writerows(soon_rows)

    print(f"Exported {len(soon_rows)} ending-soon card(s) to {ENDING_SOON_EXPORT_FILE}")


def backup_watchlist():
    print("\nBACKUP WATCHLIST")

    rows = read_watchlist_rows()
    if not rows:
        print("No cards saved yet.")
        return

    with open(BACKUP_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=get_watchlist_fieldnames())
        writer.writeheader()
        writer.writerows(rows)

    print(f"Backup saved to {BACKUP_FILE}")


def restore_watchlist():
    print("\nRESTORE WATCHLIST")

    if not os.path.exists(BACKUP_FILE):
        print("No backup file found.")
        return

    confirm = input("Type YES to replace watchlist.csv with the backup: ").strip()
    if confirm != "YES":
        print("Restore cancelled.")
        return

    with open(BACKUP_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    write_watchlist_rows(rows)
    print(f"Restored {len(rows)} row(s) from {BACKUP_FILE}")


def remove_duplicate_cards():
    print("\nREMOVE DUPLICATE CARDS")

    rows = read_watchlist_rows()
    if not rows:
        print("No cards saved yet.")
        return

    seen = set()
    unique_rows = []
    removed_count = 0

    for row in rows:
        key = (
            row.get("card_name", "").strip().lower(),
            row.get("auction_end_time", "").strip(),
            row.get("current_price", "").strip()
        )

        if key in seen:
            removed_count += 1
            continue

        seen.add(key)
        unique_rows.append(row)

    write_watchlist_rows(unique_rows)

    print(f"Removed {removed_count} duplicate row(s).")
    print(f"Kept {len(unique_rows)} unique row(s).")

def sort_watchlist():
    print("\nSORT WATCHLIST")

    rows = read_watchlist_rows()
    if not rows:
        print("No cards saved yet.")
        return

    print("1. Sort by card name")
    print("2. Sort by estimated profit")
    print("3. Sort by auction end time")

    choice = input("Choose sort option: ").strip()

    if choice == "1":
        rows.sort(key=lambda row: row.get("card_name", "").lower())
    elif choice == "2":
        def profit_key(row):
            try:
                return float(row.get("estimated_profit", 0))
            except ValueError:
                return 0.0
        rows.sort(key=profit_key, reverse=True)
    elif choice == "3":
        def end_key(row):
            end_text = row.get("auction_end_time", "").strip()
            if not end_text:
                return datetime.max
            try:
                return datetime.strptime(end_text, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return datetime.max
        rows.sort(key=end_key)
    else:
        print("Invalid sort option.")
        return

    for row in rows:
        print("Card:", row.get("card_name", ""))
        print("Current Price:", row.get("current_price", ""))
        print("Estimated Profit:", row.get("estimated_profit", ""))
        print("Auction End:", row.get("auction_end_time", ""))
        print("Status:", row.get("status", ""))
        print("------")


def good_deals_ending_soon():
    print("\nGOOD DEALS ENDING SOON")

    rows = read_watchlist_rows()
    if not rows:
        print("No cards saved yet.")
        return

    now = datetime.now()
    matches = []

    for row in rows:
        if row.get("decision", "").strip().upper() != "GOOD DEAL":
            continue

        end_text = row.get("auction_end_time", "").strip()
        if not end_text:
            continue

        try:
            end_time = datetime.strptime(end_text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

        seconds_left = (end_time - now).total_seconds()

        if 0 < seconds_left <= 3600:
            matches.append((seconds_left, row))

    if not matches:
        print("No GOOD DEAL cards ending within 1 hour.")
        return

    matches.sort(key=lambda x: x[0])

    for seconds_left, row in matches:
        minutes = int(seconds_left // 60)
        seconds = int(seconds_left % 60)

        print("Card:", row.get("card_name", ""))
        print("Current Price:", row.get("current_price", ""))
        print("Target Bid:", row.get("target_bid", ""))
        print("Estimated Profit:", row.get("estimated_profit", ""))
        print("Time Left:", f"{minutes}m {seconds}s")
        print("Status:", row.get("status", ""))
        print("Notes:", row.get("notes", ""))
        print("------")


def mark_card_status():
    print("\nMARK CARD STATUS")

    rows = read_watchlist_rows()
    if not rows:
        print("No cards saved yet.")
        return

    for i, row in enumerate(rows, start=1):
        print(f"{i}. {row.get('card_name', '')} | Status: {row.get('status', 'WATCHING')}")

    choice = input("Enter card number: ").strip()

    try:
        index = int(choice) - 1
        if index < 0 or index >= len(rows):
            print("Invalid selection.")
            return
    except ValueError:
        print("Please enter a valid number.")
        return

    print("Choose new status:")
    print("1. WATCHING")
    print("2. WON")
    print("3. LOST")
    print("4. BOUGHT")
    print("5. SOLD")

    status_choice = input("Status option: ").strip()

    status_map = {
        "1": "WATCHING",
        "2": "WON",
        "3": "LOST",
        "4": "BOUGHT",
        "5": "SOLD"
    }

    if status_choice not in status_map:
        print("Invalid status option.")
        return

    rows[index]["status"] = status_map[status_choice]
    write_watchlist_rows(rows)

    print("Updated status to:", rows[index]["status"])
    print("Card:", rows[index].get("card_name", ""))


def results_summary():
    print("\nRESULTS SUMMARY")

    rows = read_watchlist_rows()
    if not rows:
        print("No cards saved yet.")
        return

    counts = {
        "WATCHING": 0,
        "WON": 0,
        "LOST": 0,
        "BOUGHT": 0,
        "SOLD": 0
    }

    for row in rows:
        status = row.get("status", "WATCHING").strip().upper()
        if status in counts:
            counts[status] += 1
        else:
            counts["WATCHING"] += 1

    print("WATCHING:", counts["WATCHING"])
    print("WON:", counts["WON"])
    print("LOST:", counts["LOST"])
    print("BOUGHT:", counts["BOUGHT"])
    print("SOLD:", counts["SOLD"])


def main():
    setup_watchlist()

    while True:
        print("1. Dashboard summary")
        print("2. Add card to watchlist")
        print("3. Quick add card")
        print("4. View watchlist")
        print("5. Update existing card")
        print("6. Delete card")
        print("7. Auto remove ended auctions")
        print("8. Auction countdown")
        print("9. Target bid calculator")
        print("10. Snipe time calculator")
        print("11. View ending soon watchlist")
        print("12. Top deals radar")
        print("13. Profit leaderboard")
        print("14. Sniper alerts")
        print("15. View settings")
        print("16. Edit settings")
        print("17. Live sniper monitor")
        print("18. Load sample data")
        print("19. Reset watchlist")
        print("20. Search cards")
        print("21. Search GOOD DEAL cards")
        print("22. Search PASS cards")
        print("23. Search ending soon")
        print("24. Search best profit")
        print("25. Search summary")
        print("26. Export GOOD DEAL cards")
        print("27. Export ending soon cards")
        print("28. Backup watchlist")
        print("29. Restore watchlist")
        print("30. Remove duplicate cards")
        print("31. Sort watchlist")
        print("32. GOOD DEALS ending soon")
        print("33. Mark card status")
        print("34. Results summary")
        print("35. Search eBay auctions")
        print("36. Search eBay and save to watchlist")
        print("37. Auto deal radar")
        print("38. Live deal radar")
        print("39. Auto import radar")
        print("40. Live auto import radar")
        print("41. Exit")

        choice = input("\nChoose an option: ").strip()

        if choice == "1":
            dashboard_summary()

        elif choice == "2":
            add_card()

        elif choice == "3":
            quick_add_card()

        elif choice == "4":
            view_watchlist()

        elif choice == "5":
            update_existing_card()

        elif choice == "6":
            delete_card()

        elif choice == "7":
            auto_remove_ended_auctions()

        elif choice == "8":
            countdown()

        elif choice == "9":
            target_bid_calculator()

        elif choice == "10":
            snipe_time_calculator()

        elif choice == "11":
            view_ending_soon()

        elif choice == "12":
            top_deals_radar()

        elif choice == "13":
            profit_leaderboard()

        elif choice == "14":
            sniper_alerts()

        elif choice == "15":
            view_settings()

        elif choice == "16":
            edit_settings()

        elif choice == "17":
            live_sniper_monitor()

        elif choice == "18":
            load_sample_data()

        elif choice == "19":
            reset_watchlist()

        elif choice == "20":
            search_cards()

        elif choice == "21":
            search_good_deals()

        elif choice == "22":
            search_pass_cards()

        elif choice == "23":
            search_ending_soon()

        elif choice == "24":
            search_best_profit()

        elif choice == "25":
            search_summary()

        elif choice == "26":
            export_good_deals()

        elif choice == "27":
            export_ending_soon()

        elif choice == "28":
            backup_watchlist()

        elif choice == "29":
            restore_watchlist()

        elif choice == "30":
            remove_duplicate_cards()

        elif choice == "31":
            sort_watchlist()

        elif choice == "32":
            good_deals_ending_soon()

        elif choice == "33":
            mark_card_status()

        elif choice == "34":
            results_summary()

        elif choice == "35":
            ebay_tools.search_ebay()

        elif choice == "36":
            ebay_tools.search_and_save()

        elif choice == "37":
            ebay_tools.deal_radar()

        elif choice == "38":
            ebay_tools.live_deal_radar()

        elif choice == "39":
            ebay_tools.auto_import_radar()

        elif choice == "40":
            ebay_tools.live_auto_import_radar()

        elif choice == "41":
            print("Goodbye.")
            break

        else:
            print("Please choose 1 through 41.")





if __name__ == "__main__":
    main()