import base64
import os

import requests
from dotenv import load_dotenv

load_dotenv()

EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")


def _ebay_oauth_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.proxies.update({"http": None, "https": None})
    return session


def _token_request_parts():
    if not EBAY_CLIENT_ID or not EBAY_CLIENT_SECRET:
        raise ValueError("Missing EBAY_CLIENT_ID or EBAY_CLIENT_SECRET in .env")

    credentials = f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    url = "https://api.ebay.com/identity/v1/oauth2/token"
    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope",
    }
    return url, headers, data


def get_application_access_token():
    url, headers, data = _token_request_parts()
    response = _ebay_oauth_session().post(url, headers=headers, data=data, timeout=30)
    response.raise_for_status()

    return response.json()["access_token"]


def get_test_ebay_token():
    try:
        url, headers, data = _token_request_parts()
    except Exception as exc:
        result = {
            "ok": False,
            "status_code": None,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
        print(result)
        return result

    try:
        response = _ebay_oauth_session().post(url, headers=headers, data=data, timeout=30)
        result = {
            "ok": response.ok,
            "status_code": response.status_code,
            "error_type": "",
            "error_message": "" if response.ok else response.text[:500],
        }
        if response.ok:
            payload = response.json()
            result["access_token"] = str(payload.get("access_token") or "")
        print(result)
        return result
    except Exception as exc:
        result = {
            "ok": False,
            "status_code": None,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
        print(result)
        return result
