import json
import os

PROFILES_FILE = "profiles.json"


def load_profiles():
    default_profiles = {
        "NFL QBs": [
            "mahomes psa 10",
            "josh allen psa 10",
            "lamar jackson rookie auto",
            "justin herbert psa 10"
        ],
        "Basketball Rookies": [
            "wembanyama psa 10",
            "anthony edwards rookie psa 10",
            "paolo banchero rookie auto"
        ],
        "Cheap Flips": [
            "prizm rookie psa 9",
            "optic rookie psa 9",
            "rookie auto raw"
        ]
    }

    if not os.path.exists(PROFILES_FILE):
        return default_profiles

    try:
        with open(PROFILES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return default_profiles
    except (json.JSONDecodeError, OSError):
        return default_profiles


def save_profiles(profiles):
    with open(PROFILES_FILE, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=4)


def _normalize_keywords(value):
    if isinstance(value, list):
        return [str(k).strip() for k in value if str(k).strip()]
    if isinstance(value, str):
        return [k.strip() for k in value.split(",") if k.strip()]
    return []


def _safe_price(value, default=0.0):
    try:
        v = float(value)
        if v < 0:
            return default
        return v
    except (TypeError, ValueError):
        return default


def get_profile_settings(profile_name):
    """
    Return normalized profile settings with backward compatibility.
    Supports both legacy list-based profiles and dict-based profiles.
    """
    profiles = load_profiles()
    raw = profiles.get(profile_name, [])
    if isinstance(raw, dict):
        keywords = _normalize_keywords(raw.get("keywords", []))
        min_price = _safe_price(raw.get("min_price"), 0.0)
        max_price = _safe_price(raw.get("max_price"), 0.0)
    else:
        keywords = _normalize_keywords(raw)
        min_price = 0.0
        max_price = 0.0
    return {
        "keywords": keywords,
        "min_price": min_price,
        "max_price": max_price,
    }


def get_profile_names():
    profiles = load_profiles()
    return list(profiles.keys())


def get_profile_keywords(profile_name):
    return get_profile_settings(profile_name).get("keywords", [])


def add_or_update_profile(profile_name, keywords, min_price=0.0, max_price=0.0):
    profiles = load_profiles()
    profiles[profile_name] = {
        "keywords": _normalize_keywords(keywords),
        "min_price": _safe_price(min_price, 0.0),
        "max_price": _safe_price(max_price, 0.0),
    }
    save_profiles(profiles)


def delete_profile(profile_name):
    profiles = load_profiles()
    if profile_name in profiles:
        del profiles[profile_name]
        save_profiles(profiles)