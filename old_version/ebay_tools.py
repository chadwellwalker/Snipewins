from time import sleep
from datetime import datetime
from old_version.ebay_search import search_auction_items
from storage import read_watchlist_rows, write_watchlist_rows
from old_version.calculators import calculate_target_bid
from old_version.settings_tools import load_settings


def search_ebay():
    keyword = input("Search eBay: ")

    items = search_auction_items(keyword, limit=10)

    if not items:
        print("No results.")
        return []

    for i, item in enumerate(items, start=1):

        title = item.get("title", "No title")

        price = item.get("price", {})
        price_value = price.get("value", "0")

        end_date = item.get("itemEndDate", "")

        print(i, "-", title)
        print("Price:", price_value)
        print("Ends:", end_date)
        print()

    return items


def search_and_save():
    items = search_ebay()

    if not items:
        return

    choice = input("Enter number to save: ")

    try:
        index = int(choice) - 1
    except:
        print("Invalid number")
        return

    item = items[index]

    title = item.get("title", "No title")

    price = item.get("price", {})
    current_price = float(price.get("value", 0))

    end_date = item.get("itemEndDate", "")

    market_value = float(input("Estimated market value: "))

    target_bid = calculate_target_bid(market_value)

    decision = "GOOD DEAL"
    if current_price > target_bid:
        decision = "PASS"

    rows = read_watchlist_rows()

    rows.append({
        "card_name": title,
        "current_price": current_price,
        "market_value": market_value,
        "max_buy_price": target_bid,
        "estimated_profit": market_value - current_price,
        "decision": decision,
        "auction_end_time": end_date,
        "snipe_seconds": "",
        "snipe_time": "",
        "target_bid": target_bid,
        "notes": "",
        "status": "WATCHING"
    })

    write_watchlist_rows(rows)

    print("Saved to watchlist.")

from time import sleep


def deal_radar():
    print("\nAUTO DEAL RADAR")

    keywords_text = input("Enter search keywords separated by commas: ").strip()

    if not keywords_text:
        print("No keywords entered.")
        return

    keywords = [k.strip() for k in keywords_text.split(",") if k.strip()]

    if not keywords:
        print("No valid keywords entered.")
        return

    market_value = float(input("Estimated market value for these searches: ").strip())

    target_bid = calculate_target_bid(market_value)

    print("\nScanning eBay...\n")

    found_any = False

    for keyword in keywords:
        print(f"Scanning: {keyword}")

        try:
            items = search_auction_items(keyword, limit=10)
        except Exception as e:
            print("Search error:", e)
            print("------")
            continue

        if not items:
            print("No results.")
            print("------")
            continue

        for item in items:
            title = item.get("title", "No title")

            price = item.get("price", {})
            current_price = float(price.get("value", 0) or 0)

            end_date = item.get("itemEndDate", "")
            item_url = item.get("itemWebUrl", "")

            if current_price <= target_bid:
                found_any = True
                print("DEAL FOUND")
                print("Title:", title)
                print("Current Price:", current_price)
                print("Target Bid:", target_bid)
                print("Ends:", end_date)
                print("URL:", item_url)
                print("------")

        print("------")

    if not found_any:
        print("No deals found under your target bid.")

def format_ebay_end_time(end_date):
    if not end_date:
        return ""

    try:
        dt = datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%S.%fZ")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            dt = datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%SZ")
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return ""


def build_snipe_time(end_time_text, snipe_seconds):
    if not end_time_text:
        return ""

    try:
        end_dt = datetime.strptime(end_time_text, "%Y-%m-%d %H:%M:%S")
        snipe_dt = end_dt.timestamp() - snipe_seconds
        return datetime.fromtimestamp(snipe_dt).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ""

def live_deal_radar():
    print("\nLIVE DEAL RADAR")

    keywords_text = input("Enter search keywords separated by commas: ").strip()

    if not keywords_text:
        print("No keywords entered.")
        return

    keywords = [k.strip() for k in keywords_text.split(",") if k.strip()]

    if not keywords:
        print("No valid keywords entered.")
        return

    market_value = float(input("Estimated market value for these searches: ").strip())
    refresh_seconds = int(input("Refresh every how many seconds? ").strip())
    rounds = int(input("How many scan rounds? ").strip())

    target_bid = calculate_target_bid(market_value)

    print("\nStarting live radar...\n")

    for round_number in range(1, rounds + 1):
        print(f"=== ROUND {round_number} ===")

        found_any = False

        for keyword in keywords:
            print(f"Scanning: {keyword}")

            try:
                items = search_auction_items(keyword, limit=10)
            except Exception as e:
                print("Search error:", e)
                print("------")
                continue

            for item in items:
                title = item.get("title", "No title")

                price = item.get("price", {})
                current_price = float(price.get("value", 0) or 0)

                end_date = item.get("itemEndDate", "")
                item_url = item.get("itemWebUrl", "")

                if current_price <= target_bid:
                    found_any = True
                    print("DEAL FOUND")
                    print("Title:", title)
                    print("Current Price:", current_price)
                    print("Target Bid:", target_bid)
                    print("Ends:", end_date)
                    print("URL:", item_url)
                    print("------")

        if not found_any:
            print("No deals found this round.")

        if round_number < rounds:
            print(f"Waiting {refresh_seconds} seconds...\n")
            sleep(refresh_seconds)

    print("\nLive radar finished.")

def auto_import_radar():
    print("\nAUTO IMPORT RADAR")

    keywords_text = input("Enter search keywords separated by commas: ").strip()

    if not keywords_text:
        print("No keywords entered.")
        return

    keywords = [k.strip() for k in keywords_text.split(",") if k.strip()]

    if not keywords:
        print("No valid keywords entered.")
        return

    market_value = float(input("Estimated market value: ").strip())

    target_bid = calculate_target_bid(market_value)

    rows = read_watchlist_rows()
    existing_titles = set()

    for row in rows:
        existing_titles.add(row.get("card_name", "").strip().lower())

    added_count = 0

    print("\nScanning and importing deals...\n")

    for keyword in keywords:
        print("Scanning:", keyword)

        try:
            items = search_auction_items(keyword, limit=10)
        except Exception as e:
            print("Search error:", e)
            print("------")
            continue

        for item in items:
            title = item.get("title", "No title").strip()

            price = item.get("price", {})
            current_price = float(price.get("value", 0) or 0)

            end_date = item.get("itemEndDate", "")
            url = item.get("itemWebUrl", "")

            if current_price > target_bid:
                continue

            if title.lower() in existing_titles:
                print("Skipping duplicate:", title)
                continue

            rows.append({
                "card_name": title,
                "current_price": str(round(current_price, 2)),
                "market_value": str(round(market_value, 2)),
                "max_buy_price": str(round(market_value * 0.70, 2)),
                "estimated_profit": str(round(market_value - current_price, 2)),
                "decision": "GOOD DEAL",
                "auction_end_time": end_date,
                "snipe_seconds": "",
                "snipe_time": "",
                "target_bid": str(target_bid),
                "notes": url,
                "status": "WATCHING"
            })

            existing_titles.add(title.lower())
            added_count += 1

            print("IMPORTED DEAL")
            print("Title:", title)
            print("Price:", current_price)
            print("Target:", target_bid)
            print("Ends:", end_date)
            print("------")

    write_watchlist_rows(rows)

    print(f"\nImported {added_count} new deal(s).")

def live_auto_import_radar():
    print("\nLIVE AUTO IMPORT RADAR")

    keywords_text = input("Enter search keywords separated by commas: ").strip()
    if not keywords_text:
        print("No keywords entered.")
        return

    keywords = [k.strip() for k in keywords_text.split(",") if k.strip()]
    if not keywords:
        print("No valid keywords entered.")
        return

    try:
        market_value = float(input("Estimated market value: ").strip())
        refresh_seconds = int(input("Refresh every how many seconds? ").strip())
        rounds = int(input("How many scan rounds? ").strip())
    except ValueError:
        print("Please enter valid numbers.")
        return

    target_bid = calculate_target_bid(market_value)
    settings = load_settings()
    snipe_seconds = settings.get("default_snipe_seconds", 5)

    print("\nStarting live auto import radar...\n")

    for round_number in range(rounds):
        print(f"=== ROUND {round_number + 1} ===")

        rows = read_watchlist_rows()
        existing_titles = set()

        for row in rows:
            existing_titles.add(row.get("card_name", "").strip().lower())

        added_count = 0

        for keyword in keywords:
            print("Scanning:", keyword)

            try:
                items = search_auction_items(keyword, limit=10)
            except Exception as e:
                print("Search error:", e)
                print("------")
                continue

            for item in items:
                title = item.get("title", "No title").strip()

                price = item.get("price", {}) or {}
                current_price = float(price.get("value", 0) or 0)

                raw_end_date = item.get("itemEndDate", "")
                end_date = format_ebay_end_time(raw_end_date)
                url = item.get("itemWebUrl", "")

                if current_price > target_bid:
                    continue

                if title.lower() in existing_titles:
                    continue

                snipe_time = build_snipe_time(end_date, snipe_seconds)

                rows.append({
                    "card_name": title,
                    "current_price": str(round(current_price, 2)),
                    "market_value": str(round(market_value, 2)),
                    "max_buy_price": str(round(market_value * 0.70, 2)),
                    "estimated_profit": str(round(market_value - current_price, 2)),
                    "decision": "GOOD DEAL",
                    "auction_end_time": end_date,
                    "snipe_seconds": str(snipe_seconds),
                    "snipe_time": snipe_time,
                    "target_bid": str(target_bid),
                    "notes": url,
                    "status": "WATCHING"
                })

                existing_titles.add(title.lower())
                added_count += 1

                print("AUTO-IMPORTED DEAL")
                print("Title:", title)
                print("Price:", current_price)
                print("Target:", target_bid)
                print("Ends:", end_date)
                print("------")

        write_watchlist_rows(rows)
        print(f"Round {round_number + 1}: imported {added_count} new deal(s).")

        if round_number < rounds - 1:
            print(f"Waiting {refresh_seconds} seconds...\n")
            sleep(refresh_seconds)

    print("\nLive auto import radar finished.")