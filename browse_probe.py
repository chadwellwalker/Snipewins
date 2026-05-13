import requests
import json
from ebay_auth import get_application_access_token

BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

HEADERS_BASE = {
    "Content-Type": "application/json",
}


def run_probe(query, filter_str=None):
    token = get_application_access_token()

    headers = {
        **HEADERS_BASE,
        "Authorization": f"Bearer {token}",
    }

    params = {
        "q": query,
        "limit": "5",
    }

    if filter_str:
        params["filter"] = filter_str

    print("\n==============================")
    print(f"[PROBE] QUERY: {query}")
    print(f"[PROBE] FILTER: {filter_str}")

    try:
        resp = requests.get(BROWSE_URL, headers=headers, params=params, timeout=15)

        print(f"[PROBE] STATUS: {resp.status_code}")
        print(f"[PROBE] CONTENT-TYPE: {resp.headers.get('Content-Type')}")

        text_preview = resp.text[:300]
        print(f"[PROBE] BODY PREVIEW:\n{text_preview}")

        if resp.status_code == 429:
            print("[PROBE] RESULT: REAL RATE LIMIT (HTTP 429)")
            return

        if "application/json" not in resp.headers.get("Content-Type", ""):
            print("[PROBE] RESULT: NON-JSON RESPONSE (LIKELY BLOCKED OR BAD)")
            return

        data = resp.json()

        items = data.get("itemSummaries", [])
        print(f"[PROBE] ITEMS RETURNED: {len(items)}")

        if len(items) == 0:
            print("[PROBE] RESULT: EMPTY RESULTS (NOT RATE LIMIT)")
        else:
            print("[PROBE] RESULT: SUCCESS — API WORKING")

    except Exception as e:
        print(f"[PROBE] ERROR: {str(e)}")


if __name__ == "__main__":
    # BIN-style
    run_probe("Patrick Mahomes card", "buyingOptions:{FIXED_PRICE}")

    # AUCTION-style
    run_probe("Patrick Mahomes card", "buyingOptions:{AUCTION}")

    # second player
    run_probe("Aaron Judge card", "buyingOptions:{FIXED_PRICE}")
    run_probe("Aaron Judge card", "buyingOptions:{AUCTION}")