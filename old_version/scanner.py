import os
import time
import base64
import argparse
import requests

# scanner.py

CLIENT_ID = os.getenv("EBAY_CLIENT_ID") or ""
CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET") or ""

_token_cache = {"access_token": None, "expires_at": 0}


def _ensure_credentials():
    global CLIENT_ID, CLIENT_SECRET
    if CLIENT_ID and CLIENT_SECRET:
        return
    CLIENT_ID = input("Enter eBay CLIENT_ID: ").strip()
    CLIENT_SECRET = input("Enter eBay CLIENT_SECRET: ").strip()


def get_access_token():
    now = time.time()
    if _token_cache["access_token"] and _token_cache["expires_at"] > now + 10:
        return _token_cache["access_token"]

    _ensure_credentials()
    creds = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded = base64.b64encode(creds.encode()).decode()

    url = "https://api.ebay.com/identity/v1/oauth2/token"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded}",
    }
    data = {"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}

    resp = requests.post(url, headers=headers, data=data, timeout=20)
    resp.raise_for_status()
    jd = resp.json()
    token = jd.get("access_token")
    expires_in = int(jd.get("expires_in", 3600))
    _token_cache["access_token"] = token
    _token_cache["expires_at"] = now + expires_in
    return token


def search_auctions(keyword, limit=10):
    token = get_access_token()
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    headers = {"Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"}
    params = {"q": keyword, "filter": "buyingOptions:{AUCTION}", "limit": limit}

    resp = requests.get(url, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    items = data.get("itemSummaries", [])
    if not items:
        print("No auction items found.")
        return

    for it in items:
        title = it.get("title", "No title")
        price = it.get("price", {}).get("value", "N/A")
        currency = it.get("price", {}).get("currency", "")
        url = it.get("itemWebUrl", "No URL")
        ends = it.get("itemEndDate", "No end date")
        print(f"Title: {title}\nPrice: {price} {currency}\nEnds: {ends}\nURL: {url}\n------")


def main():
    p = argparse.ArgumentParser(description="Search eBay auctions")
    p.add_argument("keyword", nargs="?", help="Search keyword")
    p.add_argument("-n", "--limit", type=int, default=10, help="Max results")
    args = p.parse_args()

    kw = args.keyword or input("Enter search keyword: ").strip()
    if not kw:
        print("No keyword provided.")
        return
    try:
        search_auctions(kw, limit=args.limit)
    except requests.HTTPError as e:
        print("HTTP error:", e)
    except Exception as e:
        print("Error:", e)


if __name__ == "__main__":
    main()