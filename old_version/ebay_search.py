import os
import requests
from dotenv import load_dotenv
from old_version.ebay_auth import get_application_access_token

load_dotenv()

EBAY_MARKETPLACE_ID = os.getenv("EBAY_MARKETPLACE_ID", "EBAY_US")


def search_auction_items(keyword: str, limit: int = 10) -> list[dict]:
    token = get_application_access_token()

    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": EBAY_MARKETPLACE_ID,
    }
    params = {
        "q": keyword,
        "filter": "buyingOptions:{AUCTION}",
        "limit": str(limit),
    }

    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()

    data = response.json()
    return data.get("itemSummaries", [])


def print_auction_results(items: list[dict]) -> None:
    if not items:
        print("No auction items found.")
        return

    for i, item in enumerate(items, start=1):
        title = item.get("title", "No title")
        item_id = item.get("itemId", "")
        item_url = item.get("itemWebUrl", "")
        end_date = item.get("itemEndDate", "")
        price_obj = item.get("price", {}) or {}
        price_value = price_obj.get("value", "N/A")
        currency = price_obj.get("currency", "")

        print(f"{i}. {title}")
        print(f"   Item ID: {item_id}")
        print(f"   Current Price: {price_value} {currency}")
        print(f"   Ends: {end_date}")
        print(f"   URL: {item_url}")
        print("------")


if __name__ == "__main__":
    keyword = input("Enter search keyword: ").strip()
    results = search_auction_items(keyword, limit=10)
    print_auction_results(results)