from datetime import datetime
from time import sleep

from calculators import calculate_target_bid, get_float
import ebay_search
from ebay_search import search_auction_items
from settings_tools import load_settings
from storage import read_watchlist_rows, write_watchlist_rows


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def format_ebay_end_time(end_date):
    if not end_date:
        return ""

    try:
        dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        local_dt = dt.astimezone()
        return local_dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ""


def build_snipe_time(end_time_text, snipe_seconds):
    if not end_time_text:
        return ""

    try:
        end_dt = datetime.strptime(end_time_text, "%Y-%m-%d %H:%M:%S")
        snipe_timestamp = end_dt.timestamp() - float(snipe_seconds)
        return datetime.fromtimestamp(snipe_timestamp).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ""


def get_existing_urls(rows):
    urls = set()

    for row in rows:
        item_url = row.get("item_url", "").strip().lower()
        if item_url:
            urls.add(item_url)

    return urls


def get_seconds_left(end_time_text):
    if not end_time_text:
        return None

    try:
        end_time = datetime.strptime(end_time_text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

    seconds_left = (end_time - datetime.now()).total_seconds()
    return seconds_left


def search_ebay():
    keyword = input("Search eBay: ").strip()
    if not keyword:
        print("No keyword entered.")
        return []

    items = search_auction_items(keyword, limit=10)

    if not items:
        print("No results.")
        return []

    for i, item in enumerate(items, start=1):
        title = item.get("title", "No title")
        price = item.get("price", {}) or {}
        current_price = price.get("value", "0")
        end_date = format_ebay_end_time(item.get("itemEndDate", ""))
        url = item.get("itemWebUrl", "")

        print(f"\n{i}. {title}")
        print("Price:", current_price)
        print("Ends:", end_date)
        print("URL:", url)

    return items


def search_and_save():
    items = search_ebay()
    if not items:
        return

    choice = input("\nEnter number to save: ").strip()

    try:
        index = int(choice) - 1
        if index < 0 or index >= len(items):
            print("Invalid selection.")
            return
    except ValueError:
        print("Invalid number.")
        return

    item = items[index]

    title = item.get("title", "No title").strip()
    price = item.get("price", {}) or {}
    current_price = safe_float(price.get("value", 0))
    end_date = format_ebay_end_time(item.get("itemEndDate", ""))
    url = item.get("itemWebUrl", "").strip()

    rows = read_watchlist_rows()
    existing_urls = get_existing_urls(rows)

    if url and url.lower() in existing_urls:
        print("\nThat listing is already in the watchlist.")
        return

    market_value = get_float("Estimated market value: ")
    target_bid = calculate_target_bid(market_value)
    settings = load_settings()
    snipe_seconds = settings["default_snipe_seconds"]
    snipe_time = build_snipe_time(end_date, snipe_seconds)

    decision = "GOOD DEAL" if current_price <= target_bid else "PASS"

    rows.append({
        "card_name": title,
        "current_price": str(round(current_price, 2)),
        "market_value": str(round(market_value, 2)),
        "max_buy_price": str(round(market_value * 0.70, 2)),
        "estimated_profit": str(round(market_value - current_price, 2)),
        "decision": decision,
        "auction_end_time": end_date,
        "snipe_seconds": str(snipe_seconds),
        "snipe_time": snipe_time,
        "target_bid": str(target_bid),
        "item_url": url,
        "notes": "",
        "status": "WATCHING"
    })

    write_watchlist_rows(rows)
    print("\nSaved to watchlist.")


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

    market_value = get_float("Estimated market value for these searches: ")
    target_bid = calculate_target_bid(market_value)

    print("\nScanning eBay...\n")

    found_any = False

    for keyword in keywords:
        print("Scanning:", keyword)

        try:
            items = search_auction_items(keyword, limit=10)
        except Exception as e:
            print("Search error:", e)
            print("------")
            continue

        for item in items:
            title = item.get("title", "No title")
            price = item.get("price", {}) or {}
            current_price = safe_float(price.get("value", 0))
            end_date = format_ebay_end_time(item.get("itemEndDate", ""))
            url = item.get("itemWebUrl", "")

            if current_price <= target_bid:
                found_any = True
                print("\nDEAL FOUND")
                print("Title:", title)
                print("Current Price:", current_price)
                print("Target Bid:", target_bid)
                print("Ends:", end_date)
                print("URL:", url)
                print("------")

    if not found_any:
        print("No deals found under your target bid.")


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

    market_value = get_float("Estimated market value: ")
    refresh_seconds = int(get_float("Refresh every how many seconds? "))
    rounds = int(get_float("How many scan rounds? "))

    target_bid = calculate_target_bid(market_value)

    print("\nStarting radar...\n")

    for r in range(rounds):
        print(f"=== ROUND {r + 1} ===")

        found_any = False

        for keyword in keywords:
            print("Scanning:", keyword)

            try:
                items = search_auction_items(keyword, limit=10)
            except Exception as e:
                print("Search error:", e)
                continue

            for item in items:
                title = item.get("title", "No title")
                price = item.get("price", {}) or {}
                current_price = safe_float(price.get("value", 0))
                end_date = format_ebay_end_time(item.get("itemEndDate", ""))
                url = item.get("itemWebUrl", "")

                if current_price <= target_bid:
                    found_any = True
                    print("\nDEAL FOUND")
                    print("Title:", title)
                    print("Price:", current_price)
                    print("Target:", target_bid)
                    print("Ends:", end_date)
                    print("URL:", url)
                    print("------")

        if not found_any:
            print("No deals found this round.")

        if r < rounds - 1:
            print(f"\nWaiting {refresh_seconds} seconds...\n")
            sleep(refresh_seconds)

    print("\nRadar finished.")


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

    market_value = get_float("Estimated market value: ")
    target_bid = calculate_target_bid(market_value)
    settings = load_settings()
    snipe_seconds = settings["default_snipe_seconds"]

    rows = read_watchlist_rows()
    existing_urls = get_existing_urls(rows)

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
            price = item.get("price", {}) or {}
            current_price = safe_float(price.get("value", 0))
            end_date = format_ebay_end_time(item.get("itemEndDate", ""))
            url = item.get("itemWebUrl", "").strip()

            if current_price > target_bid:
                continue

            if url and url.lower() in existing_urls:
                print("Skipping duplicate URL:", title)
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
                "item_url": url,
                "notes": "",
                "status": "WATCHING"
            })

            if url:
                existing_urls.add(url.lower())
            added_count += 1

            print("\nIMPORTED DEAL")
            print("Title:", title)
            print("Price:", current_price)
            print("Target:", target_bid)
            print("Ends:", end_date)
            print("URL:", url)
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

    market_value = get_float("Estimated market value: ")
    refresh_seconds = int(get_float("Refresh every how many seconds? "))
    rounds = int(get_float("How many scan rounds? "))

    target_bid = calculate_target_bid(market_value)
    settings = load_settings()
    snipe_seconds = settings["default_snipe_seconds"]

    print("\nStarting live auto import radar...\n")

    for round_number in range(rounds):
        print(f"=== ROUND {round_number + 1} ===")

        rows = read_watchlist_rows()
        existing_urls = get_existing_urls(rows)
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
                current_price = safe_float(price.get("value", 0))
                end_date = format_ebay_end_time(item.get("itemEndDate", ""))
                url = item.get("itemWebUrl", "").strip()

                if current_price > target_bid:
                    continue

                if url and url.lower() in existing_urls:
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
                    "item_url": url,
                    "notes": "",
                    "status": "WATCHING"
                })

                if url:
                    existing_urls.add(url.lower())
                added_count += 1

                print("\nAUTO-IMPORTED DEAL")
                print("Title:", title)
                print("Price:", current_price)
                print("Target:", target_bid)
                print("Ends:", end_date)
                print("URL:", url)
                print("------")

        write_watchlist_rows(rows)
        print(f"Round {round_number + 1}: imported {added_count} new deal(s).")

        if round_number < rounds - 1:
            print(f"Waiting {refresh_seconds} seconds...\n")
            sleep(refresh_seconds)

    print("\nLive auto import radar finished.")


def auto_import_ending_soon_radar():
    print("\nAUTO IMPORT ENDING SOON RADAR")

    keywords_text = input("Enter search keywords separated by commas: ").strip()
    if not keywords_text:
        print("No keywords entered.")
        return

    keywords = [k.strip() for k in keywords_text.split(",") if k.strip()]
    if not keywords:
        print("No valid keywords entered.")
        return

    market_value = get_float("Estimated market value: ")
    minutes_limit = int(get_float("Only import auctions ending within how many minutes? "))
    target_bid = calculate_target_bid(market_value)
    settings = load_settings()
    snipe_seconds = settings["default_snipe_seconds"]

    rows = read_watchlist_rows()
    existing_urls = get_existing_urls(rows)
    added_count = 0

    print("\nScanning and importing ending-soon deals...\n")

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
            current_price = safe_float(price.get("value", 0))
            end_date = format_ebay_end_time(item.get("itemEndDate", ""))
            url = item.get("itemWebUrl", "").strip()

            if current_price > target_bid:
                continue

            if url and url.lower() in existing_urls:
                continue

            seconds_left = get_seconds_left(end_date)
            if seconds_left is None:
                continue

            if seconds_left <= 0 or seconds_left > minutes_limit * 60:
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
                "item_url": url,
                "notes": "",
                "status": "WATCHING"
            })

            if url:
                existing_urls.add(url.lower())
            added_count += 1

            print("\nENDING SOON DEAL IMPORTED")
            print("Title:", title)
            print("Price:", current_price)
            print("Target:", target_bid)
            print("Ends:", end_date)
            print("URL:", url)
            print("------")

    write_watchlist_rows(rows)
    print(f"\nImported {added_count} ending-soon deal(s).")


def live_auto_import_ending_soon_radar():
    print("\nLIVE AUTO IMPORT ENDING SOON RADAR")

    keywords_text = input("Enter search keywords separated by commas: ").strip()
    if not keywords_text:
        print("No keywords entered.")
        return

    keywords = [k.strip() for k in keywords_text.split(",") if k.strip()]
    if not keywords:
        print("No valid keywords entered.")
        return

    market_value = get_float("Estimated market value: ")
    minutes_limit = int(get_float("Only import auctions ending within how many minutes? "))
    refresh_seconds = int(get_float("Refresh every how many seconds? "))
    rounds = int(get_float("How many scan rounds? "))

    target_bid = calculate_target_bid(market_value)
    settings = load_settings()
    snipe_seconds = settings["default_snipe_seconds"]

    print("\nStarting live ending-soon auto import radar...\n")

    for round_number in range(rounds):
        print(f"=== ROUND {round_number + 1} ===")

        rows = read_watchlist_rows()
        existing_urls = get_existing_urls(rows)
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
                current_price = safe_float(price.get("value", 0))
                end_date = format_ebay_end_time(item.get("itemEndDate", ""))
                url = item.get("itemWebUrl", "").strip()

                if current_price > target_bid:
                    continue

                if url and url.lower() in existing_urls:
                    continue

                seconds_left = get_seconds_left(end_date)
                if seconds_left is None:
                    continue

                if seconds_left <= 0 or seconds_left > minutes_limit * 60:
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
                    "item_url": url,
                    "notes": "",
                    "status": "WATCHING"
                })

                if url:
                    existing_urls.add(url.lower())
                added_count += 1

                print("\nAUTO-IMPORTED ENDING SOON DEAL")
                print("Title:", title)
                print("Price:", current_price)
                print("Target:", target_bid)
                print("Ends:", end_date)
                print("URL:", url)
                print("------")

        write_watchlist_rows(rows)
        print(f"Round {round_number + 1}: imported {added_count} ending-soon deal(s).")

        if round_number < rounds - 1:
            print(f"Waiting {refresh_seconds} seconds...\n")
            sleep(refresh_seconds)

    print("\nLive ending-soon auto import radar finished.")


def view_ending_soon():
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

        if seconds_left > 0:
            soon_rows.append((seconds_left, row))

    if not soon_rows:
        print("No active auction times found.")
        return

    soon_rows.sort(key=lambda x: x[0])

    print("\nENDING SOON WATCHLIST")

    for seconds_left, row in soon_rows:
        minutes = int(seconds_left // 60)
        seconds = int(seconds_left % 60)

        print("\nCard:", row.get("card_name", ""))
        print("Current Price:", row.get("current_price", ""))
        print("Target Bid:", row.get("target_bid", ""))
        print("Ends:", row.get("auction_end_time", ""))
        print("Snipe Time:", row.get("snipe_time", ""))
        print("URL:", row.get("item_url", ""))
        print(f"Time Left: {minutes}m {seconds}s")


def sniper_queue():
    rows = read_watchlist_rows()

    if not rows:
        print("No cards saved yet.")
        return

    queue_rows = []

    for row in rows:
        snipe_time_text = row.get("snipe_time", "").strip()
        if not snipe_time_text:
            continue

        try:
            snipe_time = datetime.strptime(snipe_time_text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

        seconds_until_snipe = (snipe_time - datetime.now()).total_seconds()

        if seconds_until_snipe > 0:
            queue_rows.append((seconds_until_snipe, row))

    if not queue_rows:
        print("No upcoming sniper queue items.")
        return

    queue_rows.sort(key=lambda x: x[0])

    print("\nSNIPER QUEUE")

    for seconds_until_snipe, row in queue_rows:
        minutes = int(seconds_until_snipe // 60)
        seconds = int(seconds_until_snipe % 60)

        print("\nCard:", row.get("card_name", ""))
        print("Current Price:", row.get("current_price", ""))
        print("Target Bid:", row.get("target_bid", ""))
        print("Snipe Time:", row.get("snipe_time", ""))
        print("URL:", row.get("item_url", ""))
        print(f"Bid In: {minutes}m {seconds}s")


def top_sniper_targets():
    rows = read_watchlist_rows()

    if not rows:
        print("No cards saved yet.")
        return

    candidates = []

    for row in rows:
        try:
            current_price = safe_float(row.get("current_price", 0))
            target_bid = safe_float(row.get("target_bid", 0))
            estimated_profit = safe_float(row.get("estimated_profit", 0))
        except ValueError:
            continue

        seconds_left = get_seconds_left(row.get("auction_end_time", ""))
        if seconds_left is None or seconds_left <= 0:
            continue

        bid_gap = round(target_bid - current_price, 2)
        if bid_gap < 0:
            continue

        candidates.append((seconds_left, -estimated_profit, -bid_gap, row))

    if not candidates:
        print("No active sniper targets.")
        return

    candidates.sort(key=lambda x: (x[0], x[1], x[2]))

    print("\nTOP SNIPER TARGETS")

    for seconds_left, neg_profit, neg_gap, row in candidates[:10]:
        minutes = int(seconds_left // 60)
        seconds = int(seconds_left % 60)

        current_price = safe_float(row.get("current_price", 0))
        target_bid = safe_float(row.get("target_bid", 0))
        bid_gap = round(target_bid - current_price, 2)

        print("\nCard:", row.get("card_name", ""))
        print("Current Price:", row.get("current_price", ""))
        print("Target Bid:", row.get("target_bid", ""))
        print("Bid Gap:", bid_gap)
        print("Estimated Profit:", row.get("estimated_profit", ""))
        print("Ends:", row.get("auction_end_time", ""))
        print("URL:", row.get("item_url", ""))
        print(f"Time Left: {minutes}m {seconds}s")


def sniper_alerts():
    rows = read_watchlist_rows()

    if not rows:
        print("No cards saved yet.")
        return

    now = datetime.now()
    found_alert = False

    print("\nSNIPER ALERTS")

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
            print("\nBID NOW:", row.get("card_name", ""))
            print("Current Price:", row.get("current_price", ""))
            print("Target Bid:", row.get("target_bid", ""))
            print("Ends:", row.get("auction_end_time", ""))
            print("URL:", row.get("item_url", ""))
            print("Seconds Left:", round(seconds_left, 2))

    if not found_alert:
        print("No cards are inside the snipe window right now.")