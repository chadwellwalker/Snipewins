"""
Hybrid valuation layer for watchlist items.

Priority (honest labeling):
  1) Card Ladder exact match (optional JSON — CARD_LADDER_LOOKUP_JSON)
  2) eBay sold comps via Finding API if EBAY_FINDING_APP_ID / EBAY_APP_ID is set
  3) Else Browse active listings (auction + fixed price) as comp proxy
  4) Cross-grade matches are heavily downweighted

Uses comp_query (precise search string, profile parsing, bad-match rejects, quality score),
then a recency-aware **market lane** (scored sliding windows on price-sorted comps, preferring recent
exact sales) and a **trimmed weighted median** inside the lane. See HybridValuation debug_* fields.
"""
from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Set, Tuple

import ebay_search
from ebay_search import infer_comp_sale_type
import comp_engine_v2 as _legacy_comp_engine

import parallel_vocab
from comp_query import (
    _apply_comp_lane_penalties,
    _build_card_identity_signature,
    _detect_premium_card_class,
    _detect_comp_lane_contamination,
    _extract_card_number,
    _extract_serial_denominator,
    _norm,
    _premium_card_class_match,
    _premium_product_family_key,
    _premium_serial_band,
    _premium_subset_bucket,
    _psa_one_step_adjacent,
    _serial_support_bucket,
    build_sold_query_variants,
    build_comp_retrieval_query_passes,
    build_precise_sold_query,
    build_precise_sold_query_from_profile,
    classify_card_variant,
    classify_listing_type,
    comp_match_quality,
    comp_set_matches_target_strict,
    format_variant_class_debug,
    grade_bucket_key,
    is_bad_comp_match,
    normalize_card_number_for_key,
    normalize_parallel_bucket,
    parse_listing_profile,
    player_match_score,
    should_exclude_from_single_card_valuation,
    _same_exact_comp_lane,
    _same_near_comp_lane,
    target_has_identifiable_player,
    variant_match_assessment,
)
import comp_listing_validation
import manual_comp_review
from valuation_comp_signals import (
    condition_issue_count,
    enrich_accepted_comp_pool,
    lane_weaker_tier_weight_fraction,
    tier_counts,
)

# Optional Card Ladder (or any trusted external) lookup file.
# Env CARD_LADDER_LOOKUP_JSON overrides default path.
DEFAULT_CARD_LADDER_PATH = "card_ladder_lookup.json"

_CARD_LADDER_CACHE: Optional[Dict[str, Any]] = None
_CARD_LADDER_MTIME: Optional[float] = None
TRUE_MV_CONTRACT_VERSION = "true_mv_exact_only_v1"
VALUATION_SOURCE_MODULE = __file__
VALUATION_PUBLISH_STAGE = "valuation_engine_publish"
VALUATION_APPLY_GUARD = "exact_only"


def _grade_company_from_title(title: str) -> str:
    t = str(title or "")
    for lab in ("PSA", "BGS", "SGC", "CGC"):
        if re.search(rf"\b{lab}\b", t, flags=re.IGNORECASE):
            return lab
    return ""


def _grade_value_from_title(title: str) -> str:
    t = str(title or "")
    m = re.search(r"\b(?:psa|bgs|sgc|cgc)\s*(\d{1,2}(?:\.\d)?)\b", t, flags=re.IGNORECASE)
    return str(m.group(1)) if m else ""


def _ensure_legacy_comprecord_contract() -> None:
    comp_rec = getattr(_legacy_comp_engine, "CompRecord", None)
    if comp_rec is None:
        return
    if not hasattr(comp_rec, "is_graded"):
        setattr(comp_rec, "is_graded", property(lambda self: _is_graded_listing(getattr(self, "title", ""))))
    if not hasattr(comp_rec, "is_raw"):
        setattr(comp_rec, "is_raw", property(lambda self: not _is_graded_listing(getattr(self, "title", ""))))
    if not hasattr(comp_rec, "grade_company"):
        setattr(comp_rec, "grade_company", property(lambda self: _grade_company_from_title(getattr(self, "title", ""))))
    if not hasattr(comp_rec, "grade_value"):
        setattr(comp_rec, "grade_value", property(lambda self: _grade_value_from_title(getattr(self, "title", ""))))


_ensure_legacy_comprecord_contract()


def _safe_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    if v is None or v == "":
        return default
    try:
        x = float(v)
        if x < 0:
            return default
        return x
    except (TypeError, ValueError):
        return default


def _load_card_ladder_db() -> Dict[str, Any]:
    global _CARD_LADDER_CACHE, _CARD_LADDER_MTIME
    path = os.getenv("CARD_LADDER_LOOKUP_JSON", DEFAULT_CARD_LADDER_PATH)
    if not path or not os.path.isfile(path):
        return {"by_item_id": {}, "by_title_key": {}}
    try:
        mtime = os.path.getmtime(path)
        if _CARD_LADDER_CACHE is not None and _CARD_LADDER_MTIME == mtime:
            return _CARD_LADDER_CACHE
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {"by_item_id": {}, "by_title_key": {}}
        data.setdefault("by_item_id", {})
        data.setdefault("by_title_key", {})
        _CARD_LADDER_CACHE = data
        _CARD_LADDER_MTIME = mtime
        return data
    except (OSError, json.JSONDecodeError):
        return {"by_item_id": {}, "by_title_key": {}}


def _title_key(title: str) -> str:
    t = (title or "").lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(t.split())


def _extract_psa_grade(title: str) -> Optional[int]:
    m = re.search(r"\bpsa\s*(\d{1,2})\b", title or "", flags=re.IGNORECASE)
    if not m:
        return None
    try:
        g = int(m.group(1))
        return g if 1 <= g <= 10 else None
    except ValueError:
        return None


def _is_graded_listing(title: str) -> bool:
    t = title or ""
    if _extract_psa_grade(t) is not None:
        return True
    return bool(re.search(r"\b(bgs|sgc|cgc|psa)\b", t, flags=re.IGNORECASE))


def _is_raw_listing(title: str) -> bool:
    return not _is_graded_listing(title)


def _comp_is_graded(title: str) -> bool:
    return _is_graded_listing(title)


def _extract_price_from_item(item: Dict[str, Any]) -> Optional[float]:
    """Mirror Browse API price shapes without importing streamlit_app."""
    if not item:
        return None
    for key in ("price", "currentBidPrice", "bidPrice", "convertedCurrentBidPrice"):
        p = item.get(key)
        if isinstance(p, dict):
            v = p.get("value")
        else:
            v = p
        if v is None or str(v).strip() == "":
            continue
        try:
            s = str(v).replace("$", "").replace(",", "").strip()
            x = float(s)
            if x > 0:
                return x
        except ValueError:
            continue
    return None


_FINGERPRINT_SUBSET_OVERRIDES: Tuple[Tuple[str, str], ...] = (
    ("nfl debut", "nfl_debut"),
    ("global reach", "global_reach"),
    ("touchdown masters", "touchdown_masters"),
    ("net marvels", "net_marvels"),
    ("stained glass", "stained_glass"),
    ("color blast", "color_blast"),
    ("downtown", "downtown"),
    ("uptown", "uptown"),
    ("kaboom", "kaboom"),
    ("fireworks", "fireworks"),
    ("prizmatic", "prizmatic"),
    ("visionary", "visionary"),
    ("emergent", "emergent"),
    ("concourse", "concourse"),
    ("premier level", "premier_level"),
    ("suite level", "suite_level"),
    ("genesis", "genesis"),
    ("manga", "manga"),
    ("honeycomb", "honeycomb"),
)

_FINGERPRINT_PARALLEL_OVERRIDES: Tuple[Tuple[str, str], ...] = (
    ("red blue shock", "red_blue_shock"),
    ("red/blue shock", "red_blue_shock"),
    ("silver prizm", "silver_prizm"),
    ("pink prizm", "pink_prizm"),
    ("orange lazer", "orange_lazer"),
    ("red wave", "red_wave"),
    ("blue wave", "blue_wave"),
    ("reactive", "reactive"),
    ("wave", "wave"),
    ("lazer", "lazer"),
    ("holo", "holo"),
    ("silver", "silver"),
    ("honeycomb", "honeycomb"),
    ("genesis", "genesis"),
    ("zebra", "zebra"),
    ("gold", "gold"),
    ("mojo", "mojo"),
    ("shimmer", "shimmer"),
    ("sparkle", "sparkle"),
    ("orange", "orange"),
    ("pink", "pink"),
    ("yellow", "yellow"),
    ("green", "green"),
)

_FINGERPRINT_RARE_SUBSETS: FrozenSet[str] = frozenset(
    {"uptown", "downtown", "kaboom", "color_blast", "stained_glass", "genesis", "manga", "net_marvels"}
)
_FINGERPRINT_RARE_PARALLELS: FrozenSet[str] = frozenset(
    {"honeycomb", "genesis", "zebra", "gold", "mojo", "shimmer", "sparkle", "black_finite", "superfractor"}
)


def _fp_norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _normalize_fingerprint_serial_denominator(value: Any) -> Optional[str]:
    _digits = re.sub(r"[^0-9]", "", str(value or "").strip())
    return _digits or None


def _serial_bucket_same(a: str, b: str) -> bool:
    _a = str(a or "").strip().lower()
    _b = str(b or "").strip().lower()
    return bool(_a and _b and _a == _b)


def _fingerprint_serials_compatible(subject_fp: Dict[str, Any], comp_fp: Dict[str, Any]) -> Tuple[bool, bool]:
    _subject_serial = _normalize_fingerprint_serial_denominator(subject_fp.get("serial_denominator"))
    _comp_serial = _normalize_fingerprint_serial_denominator(comp_fp.get("serial_denominator"))
    if not _subject_serial:
        return True, False
    if not _comp_serial:
        return False, False
    if _subject_serial == _comp_serial:
        return True, False
    _class_family = str(subject_fp.get("card_class_family") or "").strip().lower()
    _subject_bucket = _serial_support_bucket(_subject_serial)
    _comp_bucket = _serial_support_bucket(_comp_serial)
    if _class_family in {
        "patch_auto_family",
        "dual_patch_auto_family",
        "auto_family",
        "subset_insert_family",
        "memorabilia_family",
    }:
        if _serial_bucket_same(_subject_bucket, _comp_bucket):
            return True, True
        _subject_premium_product = str(subject_fp.get("premium_product_family") or "").strip().lower()
        _comp_premium_product = str(comp_fp.get("premium_product_family") or "").strip().lower()
        _subject_premium_bucket = str(subject_fp.get("premium_subset_bucket") or "").strip().lower()
        _comp_premium_bucket = str(comp_fp.get("premium_subset_bucket") or "").strip().lower()
        _subject_band = str(subject_fp.get("premium_serial_band") or "").strip().lower()
        _comp_band = str(comp_fp.get("premium_serial_band") or "").strip().lower()
        if (
            _subject_premium_product
            and _subject_premium_product == _comp_premium_product
            and _subject_premium_bucket in {"patch_auto_family", "auto_family", "relic_family"}
            and _subject_premium_bucket == _comp_premium_bucket
            and _subject_band
            and _subject_band == _comp_band
        ):
            return True, True
    return False, False


def _parallel_band(parallel_name: Any, serial_denominator: Any) -> str:
    _parallel = str(parallel_name or "").strip().lower()
    _serial = _normalize_fingerprint_serial_denominator(serial_denominator)
    try:
        _den = int(_serial) if _serial else None
    except Exception:
        _den = None
    if _den is not None:
        if _den <= 10:
            return "ultra_low"
        if _den <= 25:
            return "low"
        if _den <= 49:
            return "mid_low"
        if _den <= 99:
            return "mid"
    if "gold" in _parallel:
        return "gold_family"
    if "holo" in _parallel or "silver" in _parallel:
        return "holo_family"
    if "black" in _parallel:
        return "black_family"
    return "generic"


def _premium_parallel_recovery_allowed_from_fp(subject_fp: Dict[str, Any], comp_fp: Dict[str, Any]) -> Tuple[bool, str]:
    _subject = subject_fp or {}
    _comp = comp_fp or {}
    _subject_player = str(_subject.get("player") or "").strip()
    _comp_player = str(_comp.get("player") or "").strip()
    _subject_product = str(_subject.get("premium_product_family") or "").strip().lower()
    _comp_product = str(_comp.get("premium_product_family") or "").strip().lower()
    _subject_bucket = str(_subject.get("premium_subset_bucket") or "").strip().lower()
    _comp_bucket = str(_comp.get("premium_subset_bucket") or "").strip().lower()
    if not (_subject_player and _subject_player == _comp_player and _subject_product and _subject_product == _comp_product):
        print(f"[PREMIUM_PARALLEL_DROP] title={str(_comp.get('title') or '')[:120]} reason=premium_identity_mismatch")
        return False, "premium_identity_mismatch"
    if _subject_bucket not in {"patch_auto_family", "auto_family", "relic_family"} or _subject_bucket != _comp_bucket:
        print(f"[PREMIUM_PARALLEL_DROP] title={str(_comp.get('title') or '')[:120]} reason=premium_bucket_mismatch")
        return False, "premium_bucket_mismatch"
    _subject_parallel_band = _parallel_band(_subject.get("parallel"), _subject.get("serial_denominator"))
    _comp_parallel_band = _parallel_band(_comp.get("parallel"), _comp.get("serial_denominator"))
    _subject_serial_band = str(_subject.get("premium_serial_band") or "").strip().lower()
    _comp_serial_band = str(_comp.get("premium_serial_band") or "").strip().lower()
    _allowed = False
    _reason = "parallel_band_mismatch"
    if _subject_parallel_band and _subject_parallel_band == _comp_parallel_band and _subject_parallel_band != "generic":
        _allowed = True
        _reason = "serial_or_gold_band"
    elif _subject_parallel_band == "gold_family" and _comp_parallel_band == "gold_family":
        _allowed = True
        _reason = "serial_or_gold_band"
    elif (
        {_subject_parallel_band, _comp_parallel_band}.issubset({"gold_family", "holo_family"})
        and _subject_serial_band in {"ultra_low", "low", "mid_low"}
        and _subject_serial_band == _comp_serial_band
    ):
        _allowed = True
        _reason = "serial_or_gold_band"
    if _allowed:
        print(f"[PREMIUM_PARALLEL_RECOVERY] title={str(_comp.get('title') or '')[:120]} allowed=1 reason={_reason}")
        return True, _reason
    print(f"[PREMIUM_PARALLEL_DROP] title={str(_comp.get('title') or '')[:120]} reason={_reason}")
    return False, _reason


def _extract_fingerprint_overrides(title: str) -> Dict[str, str]:
    _lower = _norm(title)
    _subset = ""
    _parallel = ""
    for _phrase, _normed in _FINGERPRINT_SUBSET_OVERRIDES:
        if _phrase in _lower:
            _subset = _normed
            break
    for _phrase, _normed in _FINGERPRINT_PARALLEL_OVERRIDES:
        if _phrase in _lower:
            _parallel = _normed
            break
    return {"subset": _subset, "parallel": _parallel}


def _is_clearly_premium_title(title: str) -> bool:
    _lower = _norm(title)
    if _premium_product_family_key(title):
        return True
    if _premium_subset_bucket(title) in {"patch_auto_family", "auto_family", "relic_family"}:
        return True
    return any(
        _token in _lower
        for _token in (
            "rpa",
            "kaboom",
            "downtown",
            "color blast",
            "stained glass",
            "aura",
            "aurora",
            "gold",
            "black",
            "1/1",
            "/25",
            "/10",
            "/5",
        )
    )


def _is_high_end_premium_title(title: str) -> bool:
    _family = _premium_product_family_key(title)
    return _family in {"national_treasures", "immaculate", "flawless", "spectra"}


def _split_truth_market_value(
    *,
    title: str,
    value: Optional[float],
    source: str,
    accepted_count: int,
    comp_lane_status: str,
    confidence: str,
    comp_lane_warning: str = "",
    serial_lane_summary: Optional[Dict[str, Any]] = None,
    exact_comp_count: int = 0,
    exact_comp_value: Optional[float] = None,
) -> Tuple[Optional[float], Optional[float], str]:
    _mv = _safe_float(value)
    _source = str(source or "").strip().lower()
    _exact_mv = _safe_float(exact_comp_value)
    _ = (
        title,
        accepted_count,
        comp_lane_status,
        confidence,
        comp_lane_warning,
        serial_lane_summary,
    )
    if not _mv or _mv <= 0:
        return None, None, "NONE"
    if _source == "manual_canonical_override":
        return round(_mv, 2), None, "TRUE"
    if _source == "support_comp_engine":
        return round(_mv, 2), None, "TRUE"
    # Per user (May 2026): a single exact comp IS the MV. Threshold lowered
    # from >=2 to >=1 so single-comp matches commit to TRUE instead of being
    # downgraded to REVIEW.
    if exact_comp_count >= 1 and _exact_mv and _exact_mv > 0:
        return round(_exact_mv, 2), None, "TRUE"
    if _source != "none":
        return None, round(_mv, 2), "REVIEW"
    return None, None, "NONE"


def _is_single_comp_clone_case(current_price, true_mv, trusted_exact_comp_count):
    try:
        if int(trusted_exact_comp_count or 0) != 1:
            return False
        if current_price is None or true_mv is None:
            return False
        _current = float(current_price)
        _mv = float(true_mv)
        if _current <= 0:
            return False
        _delta = abs(_mv - _current) / _current
        return _delta <= 0.03
    except Exception:
        return False


def _support_truth_eligible(row, support_comps):
    try:
        _row = row if isinstance(row, dict) else {}
        _comps = [c for c in list(support_comps or []) if isinstance(c, AcceptedComp)]
        _lane_type = str(_row.get("lane_type") or "").strip().lower()
        _product = str(_row.get("product_family") or "").strip().lower()
        _parallel = str(_row.get("parallel_family") or "").strip().lower()
        _serial = str(_row.get("serial_denominator") or _row.get("serial") or "").strip().lower()
        _insert = str(_row.get("insert_family") or "").strip().lower()

        if not _comps:
            return False, "no_support_comps"

        if _lane_type not in {"insert_parallel", "parallel_serial", "insert_parallel_serial"}:
            return False, "lane_not_supported"

        if not _product:
            return False, "missing_product"

        if not (_parallel or _serial or _insert):
            return False, "weak_identity"

        return True, "eligible"
    except Exception as e:
        return False, f"error:{e}"


def _accepted_comp_to_evidence_row(comp: AcceptedComp) -> Optional[Dict[str, Any]]:
    if not isinstance(comp, AcceptedComp):
        return None
    _price = _safe_float(getattr(comp, "price", None))
    if _price is None or _price <= 0:
        return None
    _sale_date = getattr(comp, "sale_date", None)
    return {
        "title": str(getattr(comp, "title", "") or "").strip()[:180],
        "price": round(float(_price), 2),
        "sold_date": _sale_date.isoformat() if isinstance(_sale_date, date) else "",
        "source": str(getattr(comp, "comp_source_type", "") or "").strip()[:48],
        "lane": str(getattr(comp, "comp_lane_tier", "") or "").strip()[:48],
        "exactness_tier": str(getattr(comp, "exactness_tier", "") or "").strip()[:64],
        "support_signal_reason": str(getattr(comp, "comp_lane_reason", "") or "").strip()[:120],
    }


def _infer_card_brand(title: str, product: Any = None) -> Optional[str]:
    _title_norm = _norm(title)
    _product_norm = _fp_norm(product).replace("_", "")
    if "topps" in _title_norm or "topps" in _product_norm:
        return "topps"
    if "bowman" in _title_norm or "bowman" in _product_norm:
        return "bowman"
    if "upper deck" in _title_norm or "upperdeck" in _product_norm:
        return "upper_deck"
    if "leaf" in _title_norm or "leaf" in _product_norm:
        return "leaf"
    if "wild card" in _title_norm or "wildcard" in _product_norm:
        return "wild_card"
    if any(
        _token in _title_norm or _token in _product_norm
        for _token in (
            "panini",
            "prizm",
            "select",
            "optic",
            "mosaic",
            "donruss",
            "contenders",
            "chronicles",
            "phoenix",
            "illusions",
            "elite",
            "certified",
            "prestige",
            "score",
            "spectra",
            "absolute",
            "revolution",
            "recon",
            "obsidian",
            "flawless",
            "immaculate",
            "nationaltreasures",
            "courtkings",
            "flux",
            "noir",
        )
    ):
        return "panini"
    return None


def _fingerprint_missing_fields(fp: Dict[str, Any]) -> List[str]:
    _fp = fp or {}
    _missing: List[str] = []
    for _field in ("player", "year", "brand", "product"):
        if not str(_fp.get(_field) or "").strip():
            _missing.append(_field)
    return _missing


def build_card_fingerprint(title: str) -> Dict[str, Any]:
    _title = str(title or "").strip()
    if not _title:
        return {
            "title": "",
            "player": None,
            "player_display": None,
            "year": None,
            "brand": None,
            "product": None,
            "card_number": None,
            "subset": None,
            "parallel": None,
            "serial": None,
            "serial_denominator": None,
            "serial_numbered": False,
            "one_of_one": False,
            "is_auto": False,
            "grade_state": "raw",
            "grade_company": None,
            "grade": None,
            "card_class": "",
            "card_class_family": "",
            "premium_family_signature": "",
            "premium_product_family": "",
            "premium_subset_bucket": "",
            "premium_serial_band": "",
            "scarcity_class": "unknown",
            "fingerprint_key": "na|na|na|na|na|na|na|raw|na",
        }

    _profile = parse_listing_profile(_title)
    _legacy_parsed = None
    try:
        _legacy_parsed = _legacy_comp_engine.parse_card_title(_title)
    except Exception:
        _legacy_parsed = None
    _class_meta = _detect_premium_card_class(
        {
            "title": _title,
            "subset_name": getattr(_profile, "subset_family", ""),
            "parallel_name": normalize_parallel_bucket(_profile),
            "serial_denominator": _extract_serial_denominator(_title),
            "serial": _extract_serial_denominator(_title),
        }
    )
    _overrides = _extract_fingerprint_overrides(_title)
    _player_display = str(
        getattr(_profile, "player_guess", "")
        or getattr(_legacy_parsed, "player_name", "")
        or ""
    ).strip()
    _player = _fp_norm(_player_display) or None
    _year = str(
        getattr(_profile, "year", "")
        or getattr(_legacy_parsed, "year", "")
        or ""
    ).strip() or None
    _product = str(
        getattr(_profile, "product_family", "")
        or getattr(_profile, "primary_set", "")
        or getattr(_legacy_parsed, "product", "")
        or ""
    ).strip().lower().replace(" ", "_") or None
    _brand = _infer_card_brand(_title, _product)
    _card_number = str(
        _extract_card_number(_title)
        or getattr(_profile, "card_number", "")
        or getattr(_legacy_parsed, "card_number", "")
        or ""
    ).strip().upper() or None
    _subset = str(
        _overrides.get("subset")
        or getattr(_profile, "subset_family", "")
        or ""
    ).strip().lower().replace(" ", "_") or None
    _parallel = str(
        _overrides.get("parallel")
        or normalize_parallel_bucket(_profile)
        or getattr(_legacy_parsed, "parallel", "")
        or ""
    ).strip().lower().replace(" ", "_") or None
    if _product == "mosaic" and _parallel and "prizm" in _parallel:
        _parallel_stripped = re.sub(r"_?prizm_?|prizm_?", "", _parallel).strip("_")
        if _parallel_stripped:
            _parallel = _parallel_stripped
    _serial_denominator = _normalize_fingerprint_serial_denominator(
        _extract_serial_denominator(_title) or ""
    )
    _serial: Optional[int] = None
    if _serial_denominator:
        try:
            _serial = int(str(_serial_denominator).strip())
        except (TypeError, ValueError):
            _serial = None
    _grade_company = _grade_company_from_title(_title) or str(
        getattr(_legacy_parsed, "grading_company", "") or ""
    ).upper() or None
    _grade = _grade_value_from_title(_title) or str(getattr(_legacy_parsed, "grade", "") or "").strip() or None
    _grade_state = "graded" if _grade_company else "raw"
    # Guard against "non auto" / "non-auto" / "no auto" / "no autograph" being
    # misclassified as Auto. The bare-word regex below matches "auto" /
    # "autograph", but eBay listings frequently say "Elly De La Cruz Non Auto
    # /99" or "Skenes No Autograph Refractor" — those are explicitly NOT
    # autograph cards and were being tagged as Auto, which poisoned the MV
    # (autos comp 5-20× higher than the same card non-auto). Also check the
    # profile/legacy bool sources first — those come from the structured
    # parser and are trustworthy; only fall through to the regex if neither
    # said yes AND there's no negation marker in the title.
    _has_non_auto_marker = bool(re.search(
        r"\bno[n]?[\s\-]*(?:auto(?:graph)?|signed|ink)\b",
        _title,
        flags=re.IGNORECASE,
    ))
    _is_auto = bool(
        getattr(_profile, "is_auto", False)
        or getattr(_legacy_parsed, "is_auto", False)
        or (
            not _has_non_auto_marker
            and re.search(r"\b(auto|autograph|signed|ink)\b", _title, flags=re.IGNORECASE)
        )
    )
    _scarcity_class = ""
    if _serial_denominator:
        _scarcity_class = "serial_numbered"
    elif _subset in _FINGERPRINT_RARE_SUBSETS:
        _scarcity_class = "ssp_insert"
    elif _parallel in _FINGERPRINT_RARE_PARALLELS:
        _scarcity_class = "parallel"
    elif _subset or (_parallel and _parallel not in {"base", "raw"}):
        _scarcity_class = "parallel"
    elif _card_number:
        _scarcity_class = "base"
    else:
        _scarcity_class = "unknown"
    _fingerprint_key = "|".join(
        [
            _fp_norm(_year) or "na",
            _fp_norm(_player) or "na",
            _fp_norm(_product) or "na",
            _fp_norm(_card_number) or "na",
            _fp_norm(_subset) or "na",
            _fp_norm(_parallel if _parallel and _parallel != "base" else ("base" if _scarcity_class == "base" else "")) or "na",
            _fp_norm(_serial_denominator) or "na",
            _fp_norm(_grade_state) or "na",
            _fp_norm(_class_meta.get("card_class_family")) or "na",
        ]
    )
    return {
        "title": _title,
        "player": _player,
        "player_display": _player_display or None,
        "year": _year,
        "brand": _brand,
        "product": _product,
        "card_number": _card_number,
        "subset": _subset,
        "parallel": _parallel,
        "serial": _serial,
        "serial_denominator": _serial_denominator,
        "serial_numbered": bool(_serial_denominator),
        "one_of_one": bool(str(_serial_denominator or "").strip() == "1"),
        "is_auto": _is_auto,
        "grade_state": _grade_state,
        "grade_company": _grade_company,
        "grade": _grade,
        "card_class": str(_class_meta.get("card_class") or "").strip().lower(),
        "card_class_family": str(_class_meta.get("card_class_family") or "").strip().lower(),
        "premium_family_signature": str(_class_meta.get("premium_family_signature") or "").strip().lower(),
        "premium_product_family": _premium_product_family_key(_product or getattr(_profile, "product_family", "") or _title),
        "premium_subset_bucket": _premium_subset_bucket(_title),
        "premium_serial_band": _premium_serial_band(_serial_denominator),
        "scarcity_class": _scarcity_class,
        "fingerprint_key": _fingerprint_key,
    }


def is_identity_clean(fp: Dict[str, Any]) -> bool:
    return not _fingerprint_missing_fields(fp)


def _build_card_fingerprint(row: Dict[str, Any]) -> Dict[str, Any]:
    _row = row or {}
    _title = str(_row.get("title") or _row.get("card_name") or "").strip()
    _existing = dict(_row.get("card_fingerprint") or {})
    _profile = parse_listing_profile(_title)
    _base = build_card_fingerprint(_title)
    _class_meta = _detect_premium_card_class(
        {
            "title": _title,
            "subset_name": _row.get("subset_name"),
            "parallel_name": _row.get("parallel_name") or _row.get("parallel_bucket"),
            "serial_denominator": _row.get("serial_denominator"),
            "serial": _row.get("serial"),
        }
    )
    _overrides = _extract_fingerprint_overrides(_title)
    _player_display = str(
        _existing.get("player_display")
        or _row.get("player_name")
        or _row.get("target_player_name")
        or _base.get("player_display")
        or getattr(_profile, "player_guess", "")
        or ""
    ).strip()
    _player = str(_existing.get("player") or "").strip().lower() or str(_base.get("player") or "").strip().lower() or _fp_norm(_player_display)
    _year = str(_existing.get("year") or _row.get("year") or _base.get("year") or getattr(_profile, "year", "") or "").strip() or None
    _brand = str(_existing.get("brand") or _row.get("brand") or _base.get("brand") or "").strip().lower() or None
    _product = str(
        _existing.get("product")
        or _row.get("product_family")
        or _row.get("target_product_family")
        or _base.get("product")
        or getattr(_profile, "product_family", "")
        or getattr(_profile, "primary_set", "")
        or ""
    ).strip().lower().replace(" ", "_") or None
    _card_number = str(
        _existing.get("card_number")
        or _row.get("card_number")
        or _base.get("card_number")
        or getattr(_profile, "card_number", "")
        or ""
    ).strip().upper() or None
    _subset = str(
        _existing.get("subset")
        or _row.get("subset_name")
        or _overrides.get("subset")
        or _base.get("subset")
        or getattr(_profile, "subset_family", "")
        or ""
    ).strip().lower().replace(" ", "_") or None
    _parallel = str(
        _existing.get("parallel")
        or _row.get("parallel_name")
        or _row.get("parallel_bucket")
        or _overrides.get("parallel")
        or _base.get("parallel")
        or normalize_parallel_bucket(_profile)
        or ""
    ).strip().lower().replace(" ", "_") or None
    # On Mosaic cards "Silver Prizm" / "Pink Prizm" etc. are parallel program names where
    # "Prizm" is Panini's branding, not a product differentiator.
    # Strip "prizm" from the parallel bucket so it aligns with explicit parallel_bucket="silver".
    if _product == "mosaic" and _parallel and "prizm" in _parallel:
        _parallel_stripped = re.sub(r"_?prizm_?|prizm_?", "", _parallel).strip("_")
        if _parallel_stripped:
            _parallel = _parallel_stripped
    _serial_denominator = _normalize_fingerprint_serial_denominator(
        _existing.get("serial_denominator")
        or _row.get("serial_denominator")
        or _base.get("serial_denominator")
        or _extract_serial_denominator(_title)
        or ""
    )
    _serial = _base.get("serial")
    _grade_state = str(
        _existing.get("grade_state")
        or _base.get("grade_state")
        or ("graded" if _is_graded_listing(_title) else "raw")
    ).strip().lower() or "raw"
    _grade_company = str(
        _existing.get("grade_company")
        or _row.get("grade_company")
        or _base.get("grade_company")
        or ""
    ).strip().upper() or None
    _grade = str(
        _existing.get("grade")
        or _row.get("grade")
        or _base.get("grade")
        or ""
    ).strip() or None
    _is_auto = bool(
        _existing.get("is_auto")
        if "is_auto" in _existing
        else _row.get("is_auto")
        if "is_auto" in _row
        else _base.get("is_auto")
    )
    _scarcity_class = str(_existing.get("scarcity_class") or "").strip().lower()
    if not _scarcity_class:
        if _serial_denominator:
            _scarcity_class = "serial_numbered"
        elif _subset in _FINGERPRINT_RARE_SUBSETS:
            _scarcity_class = "ssp_insert"
        elif _parallel in _FINGERPRINT_RARE_PARALLELS:
            _scarcity_class = "parallel"
        elif _subset or (_parallel and _parallel not in {"base", "raw"}):
            _scarcity_class = "parallel"
        elif _card_number:
            _scarcity_class = "base"
        else:
            _scarcity_class = "unknown"
    _fingerprint_key = "|".join(
        [
            _fp_norm(_year) or "na",
            _fp_norm(_player) or "na",
            _fp_norm(_product) or "na",
            _fp_norm(_card_number) or "na",
            _fp_norm(_subset) or "na",
            _fp_norm(_parallel if _parallel and _parallel != "base" else ("base" if _scarcity_class == "base" else "")) or "na",
            _fp_norm(_serial_denominator) or "na",
            _fp_norm(_grade_state) or "na",
            _fp_norm(_class_meta.get("card_class_family")) or "na",
        ]
    )
    return {
        "title": _title,
        "player": _player or None,
        "player_display": _player_display or None,
        "year": _year,
        "brand": _brand,
        "product": _product,
        "card_number": _card_number,
        "subset": _subset,
        "parallel": _parallel,
        "serial": _serial,
        "serial_denominator": _serial_denominator,
        "serial_numbered": bool(_serial_denominator),
        "one_of_one": bool(str(_serial_denominator or "").strip() == "1/1"),
        "is_auto": _is_auto,
        "grade_state": _grade_state,
        "grade_company": _grade_company,
        "grade": _grade,
        "card_class": str(_class_meta.get("card_class") or "").strip().lower(),
        "card_class_family": str(_class_meta.get("card_class_family") or "").strip().lower(),
        "premium_family_signature": str(_class_meta.get("premium_family_signature") or "").strip().lower(),
        "premium_product_family": _premium_product_family_key(_product or getattr(_profile, "product_family", "") or _title),
        "premium_subset_bucket": _premium_subset_bucket(_title),
        "premium_serial_band": _premium_serial_band(_serial_denominator),
        "scarcity_class": _scarcity_class,
        "fingerprint_key": _fingerprint_key,
    }


def _fingerprint_match_result_for_titles(
    target_title: str,
    comp_title: str,
    *,
    ignore_grade: bool = False,
) -> Dict[str, Any]:
    _subject_fp = build_card_fingerprint(target_title)
    _comp_fp = build_card_fingerprint(comp_title)
    if ignore_grade:
        _subject_fp = dict(_subject_fp)
        _comp_fp = dict(_comp_fp)
        _subject_fp["grade_state"] = ""
        _comp_fp["grade_state"] = ""
    return _score_comp_fingerprint_match(_subject_fp, _comp_fp)


def _serial_lane_identity_match(subject_fp: Dict[str, Any], comp_fp: Dict[str, Any]) -> bool:
    _subject = subject_fp or {}
    _comp = comp_fp or {}
    _subject_player = str(_subject.get("player") or "").strip()
    _comp_player = str(_comp.get("player") or "").strip()
    if _subject_player and _comp_player != _subject_player:
        return False

    _subject_card = str(_subject.get("card_number") or "").strip().upper()
    _comp_card = str(_comp.get("card_number") or "").strip().upper()
    if _subject_card and (not _comp_card or _comp_card != _subject_card):
        return False

    _subject_premium_product = str(_subject.get("premium_product_family") or "").strip().lower()
    _comp_premium_product = str(_comp.get("premium_product_family") or "").strip().lower()
    if _subject_premium_product:
        if not _comp_premium_product or _comp_premium_product != _subject_premium_product:
            return False
    else:
        _subject_product = str(_subject.get("product") or "").strip().lower()
        _comp_product = str(_comp.get("product") or "").strip().lower()
        if _subject_product and (not _comp_product or _comp_product != _subject_product):
            return False

    _subject_subset = str(_subject.get("subset") or "").strip().lower()
    _comp_subset = str(_comp.get("subset") or "").strip().lower()
    if _subject_subset and _comp_subset and _comp_subset != _subject_subset:
        return False
    return True


def _serial_lane_anchor_window(
    comps: List["AcceptedComp"],
    point: Optional[float],
    *,
    single_band_pct: float,
) -> Tuple[Optional[float], Optional[float]]:
    _point = _safe_float(point)
    _prices = [round(float(getattr(c, "price", 0.0) or 0.0), 2) for c in comps if float(getattr(c, "price", 0.0) or 0.0) > 0]
    if not _prices or _point is None or _point <= 0:
        return None, None
    if len(_prices) == 1:
        _low = round(_point * (1.0 - single_band_pct), 2)
        _high = round(_point * (1.0 + single_band_pct), 2)
        return _low, _high
    return round(min(_prices), 2), round(max(_prices), 2)


def _summarize_premium_serial_lane(
    target_title: str,
    accepted_comps: List["AcceptedComp"],
    *,
    item_id: str = "",
) -> Dict[str, Any]:
    _target_fp = _build_card_fingerprint({"title": target_title})
    _target_serial = _normalize_fingerprint_serial_denominator(_target_fp.get("serial_denominator"))
    _premium_product = str(_target_fp.get("premium_product_family") or "").strip().lower()
    _premium_subset = str(_target_fp.get("premium_subset_bucket") or "").strip().lower()
    _is_premium_serial = bool(
        _target_serial
        and (
            _premium_product
            or _premium_subset in {"patch_auto_family", "dual_patch_auto_family", "auto_family", "relic_family", "subset_insert_family", "base_parallel_family"}
            or _is_clearly_premium_title(target_title)
        )
    )
    _summary: Dict[str, Any] = {
        "is_premium_serial": _is_premium_serial,
        "target_serial": _target_serial or "",
        "target_bucket": _serial_support_bucket(_target_serial) if _target_serial else "",
        "exact_same_denominator_count": 0,
        "cross_serial_count": 0,
        "cross_serial_same_bucket_count": 0,
        "cross_serial_other_bucket_count": 0,
        "exact_anchor_value": None,
        "exact_anchor_low": None,
        "exact_anchor_high": None,
        "cross_anchor_value": None,
        "cross_anchor_low": None,
        "cross_anchor_high": None,
        "cross_serial_conservative_value": None,
        "cross_serial_discount_factor": None,
    }
    if not _is_premium_serial or not _target_serial:
        return _summary

    _exact_same_denom: List[AcceptedComp] = []
    _cross_serial: List[Tuple[AcceptedComp, str, str]] = []
    _target_bucket = str(_summary.get("target_bucket") or "").strip().lower()
    for _comp in accepted_comps:
        _comp_fp = _build_card_fingerprint({"title": getattr(_comp, "title", "")})
        if not _serial_lane_identity_match(_target_fp, _comp_fp):
            continue
        _comp_serial = _normalize_fingerprint_serial_denominator(_comp_fp.get("serial_denominator"))
        if not _comp_serial:
            continue
        _comp_bucket = _serial_support_bucket(_comp_serial)
        _target_parallel = str(_target_fp.get("parallel") or "").strip().lower()
        _comp_parallel = str(_comp_fp.get("parallel") or "").strip().lower()
        _explicit_parallel_conflict = bool(
            _target_parallel
            and _target_parallel not in {"", "base", "raw"}
            and _comp_parallel
            and _comp_parallel not in {"", "base", "raw"}
            and _comp_parallel != _target_parallel
        )
        _variant_level = str(getattr(_comp, "variant_match_level", "") or "").strip().lower()
        _same_variant_lane = _variant_level in {"exact_variant_match", "same_variant_family"} or str(
            getattr(_comp, "comp_lane_tier", "") or ""
        ) in {"exact_lane", "near_lane"}
        if _comp_serial == _target_serial:
            if _explicit_parallel_conflict and not _same_variant_lane:
                continue
            _exact_same_denom.append(_comp)
            print(
                f"[EXACT_SERIAL_COMP_KEEP] item={item_id[:24] or '?'} target_serial=/{_target_serial} "
                f"comp_serial=/{_comp_serial} price={round(float(getattr(_comp, 'price', 0.0) or 0.0), 2)} "
                f"lane={str(getattr(_comp, 'comp_lane_tier', '') or '')[:24]} title={str(getattr(_comp, 'title', '') or '')[:140]}"
            )
        else:
            _cross_serial.append((_comp, _comp_serial, _comp_bucket))
            print(
                f"[CROSS_SERIAL_COMP_REJECT] item={item_id[:24] or '?'} target_serial=/{_target_serial} "
                f"comp_serial=/{_comp_serial} target_bucket={_target_bucket or 'n/a'} comp_bucket={_comp_bucket or 'n/a'} "
                f"price={round(float(getattr(_comp, 'price', 0.0) or 0.0), 2)} "
                f"lane={str(getattr(_comp, 'comp_lane_tier', '') or '')[:24]} title={str(getattr(_comp, 'title', '') or '')[:140]}"
            )

    _summary["exact_same_denominator_count"] = len(_exact_same_denom)
    _summary["cross_serial_count"] = len(_cross_serial)
    _summary["cross_serial_same_bucket_count"] = sum(1 for _, _, _bucket in _cross_serial if _bucket and _bucket == _target_bucket)
    _summary["cross_serial_other_bucket_count"] = max(
        0,
        len(_cross_serial) - int(_summary["cross_serial_same_bucket_count"]),
    )

    _exact_pw = [
        (float(getattr(_comp, "price", 0.0) or 0.0), max(0.0, float(getattr(_comp, "weight", 0.0) or 0.0)))
        for _comp in _exact_same_denom
        if float(getattr(_comp, "price", 0.0) or 0.0) > 0
    ]
    if _exact_pw:
        if len(_exact_pw) == 1:
            _summary["exact_anchor_value"] = round(float(_exact_pw[0][0]), 2)
        else:
            _pt, _, _ = _fallback_trimmed_weighted_median(_exact_pw)
            _summary["exact_anchor_value"] = round(float(_pt), 2) if _pt else None
        _low, _high = _serial_lane_anchor_window(
            _exact_same_denom,
            _summary["exact_anchor_value"],
            single_band_pct=0.10,
        )
        _summary["exact_anchor_low"] = _low
        _summary["exact_anchor_high"] = _high

    _cross_only = [_comp for _comp, _, _ in _cross_serial]
    _cross_pw = [
        (float(getattr(_comp, "price", 0.0) or 0.0), max(0.0, float(getattr(_comp, "weight", 0.0) or 0.0)))
        for _comp in _cross_only
        if float(getattr(_comp, "price", 0.0) or 0.0) > 0
    ]
    if _cross_pw:
        if len(_cross_pw) == 1:
            _summary["cross_anchor_value"] = round(float(_cross_pw[0][0]), 2)
        else:
            _pt, _, _ = _fallback_trimmed_weighted_median(_cross_pw)
            _summary["cross_anchor_value"] = round(float(_pt), 2) if _pt else None
        _cross_low, _cross_high = _serial_lane_anchor_window(
            _cross_only,
            _summary["cross_anchor_value"],
            single_band_pct=0.16,
        )
        _summary["cross_anchor_low"] = _cross_low
        _summary["cross_anchor_high"] = _cross_high
        _same_bucket_n = int(_summary.get("cross_serial_same_bucket_count") or 0)
        _discount = 0.88 if _same_bucket_n == len(_cross_only) else 0.78
        _summary["cross_serial_discount_factor"] = _discount
        if _summary["cross_anchor_value"]:
            _summary["cross_serial_conservative_value"] = round(float(_summary["cross_anchor_value"]) * _discount, 2)

    print(
        f"[SERIAL_LANE_SUMMARY] item={item_id[:24] or '?'} target_serial=/{_target_serial} "
        f"target_bucket={_serial_bucket_display(_target_bucket) if _target_bucket else 'n/a'} "
        f"exact_same_denominator={int(_summary['exact_same_denominator_count'])} "
        f"cross_serial={int(_summary['cross_serial_count'])} "
        f"cross_same_bucket={int(_summary['cross_serial_same_bucket_count'])} "
        f"exact_anchor={_summary.get('exact_anchor_value')} "
        f"cross_anchor={_summary.get('cross_anchor_value')} "
        f"cross_discount={_summary.get('cross_serial_discount_factor')}"
    )
    return _summary


def _build_operator_comp_plan(row: Dict[str, Any]) -> Dict[str, Any]:
    _fp = _build_card_fingerprint(row)
    _title = str((row or {}).get("title") or (row or {}).get("card_name") or "").strip()
    _profile = parse_listing_profile(_title)
    _class_meta = _detect_premium_card_class(row or {"title": _title})
    _player_display = str(_fp.get("player_display") or "").strip()
    _year = str(_fp.get("year") or "").strip()
    _product = str(_fp.get("product") or "").strip().replace("_", " ")
    _subset = str(_fp.get("subset") or "").strip().replace("_", " ")
    _parallel = str(_fp.get("parallel") or "").strip().replace("_", " ")
    _card_no = str(_fp.get("card_number") or "").strip()
    _serial_den = str(_fp.get("serial_denominator") or "").strip()
    _grade_state = str(_fp.get("grade_state") or "raw").strip().lower()
    _strict_fields: List[str] = ["player", "product"]
    if _card_no:
        _strict_fields.append("card_number")
    if _subset:
        _strict_fields.append("subset")
    if _parallel and _parallel not in {"base"}:
        _strict_fields.append("parallel")
    if _serial_den:
        _strict_fields.append("serial_denominator")
    if _grade_state:
        _strict_fields.append("grade_state")
    if str(_fp.get("card_class_family") or "").strip():
        _strict_fields.append("card_class_family")
    _parts = [
        _year,
        _player_display,
        _product.title() if _product else "",
        _subset.title() if _subset else "",
        f"#{_card_no}" if _card_no else "",
        _parallel.title() if _parallel and _parallel not in {"base"} else "",
        _serial_den,
        _grade_state,
    ]
    _query_primary = build_precise_sold_query_from_profile(_profile, fallback_title=_title, source_row=row)
    _backup_1 = _query_primary
    _backup_2 = " ".join([_p for _p in _parts if _p and _p not in {_year, _grade_state}]).strip()
    if str(_class_meta.get("query_terms") or ""):
        _backup_2 = " ".join(
            [str(_year or "").strip(), str(_player_display or "").strip(), str(_class_meta.get("product_display") or "").strip()]
            + [str(_term) for _term in list(_class_meta.get("query_terms") or ())[:3]]
        ).strip()[:200]
    return {
        **_fp,
        "query_primary": _query_primary,
        "query_backup_1": _backup_1,
        "query_backup_2": _backup_2,
        "strict_fields": _strict_fields,
    }


def _score_comp_fingerprint_match(subject_fp: Dict[str, Any], comp_fp: Dict[str, Any]) -> Dict[str, Any]:
    _subject = subject_fp or {}
    _comp = comp_fp or {}
    _reasons: List[str] = []
    _near = False
    _subject_premium_product = str(_subject.get("premium_product_family") or "").strip().lower()
    _comp_premium_product = str(_comp.get("premium_product_family") or "").strip().lower()
    _subject_premium_bucket = str(_subject.get("premium_subset_bucket") or "").strip().lower()
    _comp_premium_bucket = str(_comp.get("premium_subset_bucket") or "").strip().lower()
    _premium_bucket_match = bool(
        _subject_premium_product
        and _subject_premium_product == _comp_premium_product
        and _subject_premium_bucket in {"patch_auto_family", "auto_family", "relic_family", "base_parallel_family"}
        and _subject_premium_bucket == _comp_premium_bucket
    )
    _subject_player = str(_subject.get("player") or "").strip()
    _comp_player = str(_comp.get("player") or "").strip()
    if _subject_player:
        if not _comp_player or _comp_player != _subject_player:
            _reasons.append("wrong_player")
    _subject_product = str(_subject.get("product") or "").strip()
    _comp_product = str(_comp.get("product") or "").strip()
    if _subject_product:
        if not _comp_product:
            _parallel_recovery_ok, _parallel_recovery_reason = _premium_parallel_recovery_allowed_from_fp(_subject, _comp)
            if _parallel_recovery_ok:
                _near = True
                print(f"[COMP_KEEP_NEAR] title={str(_comp.get('title') or '')[:140]} reason={_parallel_recovery_reason}")
            else:
                _reasons.append("generic_product_only_reject")
        elif _comp_product != _subject_product:
            _reasons.append("wrong_product")
    _subject_year = str(_subject.get("year") or "").strip()
    _comp_year = str(_comp.get("year") or "").strip()
    if _subject_year and _comp_year and _subject_year != _comp_year:
        _reasons.append("wrong_year")
    elif _subject_year and not _comp_year:
        _near = True
    _subject_card = str(_subject.get("card_number") or "").strip().upper()
    _comp_card = str(_comp.get("card_number") or "").strip().upper()
    if _subject_card:
        if not _comp_card or _comp_card != _subject_card:
            _reasons.append("wrong_card_number")
    _subject_subset = str(_subject.get("subset") or "").strip()
    _comp_subset = str(_comp.get("subset") or "").strip()
    if _subject_subset:
        if not _comp_subset or _comp_subset != _subject_subset:
            _parallel_recovery_ok, _parallel_recovery_reason = _premium_parallel_recovery_allowed_from_fp(_subject, _comp)
            if _premium_bucket_match or _parallel_recovery_ok:
                _near = True
                print(f"[PREMIUM_BUCKET] subject={_subject_premium_bucket} comp={_comp_premium_bucket} allowed=1")
                print(f"[COMP_KEEP_NEAR] title={str(_comp.get('title') or '')[:140]} reason={_parallel_recovery_reason if _parallel_recovery_ok else 'same_family_bucket'}")
            else:
                _reasons.append("wrong_subset")
    elif _comp_subset:
        _reasons.append("wrong_subset")
    _subject_parallel = str(_subject.get("parallel") or "").strip()
    _comp_parallel = str(_comp.get("parallel") or "").strip()
    if _subject_parallel and _subject_parallel not in {"base", "raw"}:
        if not _comp_parallel or _comp_parallel != _subject_parallel:
            _parallel_recovery_ok, _parallel_recovery_reason = _premium_parallel_recovery_allowed_from_fp(_subject, _comp)
            if _parallel_recovery_ok:
                _near = True
                print(f"[COMP_KEEP_NEAR] title={str(_comp.get('title') or '')[:140]} reason={_parallel_recovery_reason}")
            else:
                _reasons.append("wrong_parallel")
    elif _comp_parallel and _comp_parallel not in {"", "base", "raw"}:
        _reasons.append("wrong_parallel")
    _subject_serial = _normalize_fingerprint_serial_denominator(_subject.get("serial_denominator"))
    _serial_ok, _serial_near = _fingerprint_serials_compatible(_subject, _comp)
    if not _serial_ok:
        _subject_serial_band = str(_subject.get("premium_serial_band") or "").strip().lower()
        _comp_serial_band = str(_comp.get("premium_serial_band") or "").strip().lower()
        _band_ok = bool(_premium_bucket_match and _subject_serial_band and _subject_serial_band == _comp_serial_band)
        print(
            f"[SERIAL_BAND] subject={_subject_serial or ''} comp={_normalize_fingerprint_serial_denominator(_comp.get('serial_denominator')) or ''} "
            f"allowed={int(_band_ok)}"
        )
        _parallel_recovery_ok, _parallel_recovery_reason = _premium_parallel_recovery_allowed_from_fp(_subject, _comp)
        if _band_ok or _parallel_recovery_ok:
            _near = True
            print(f"[COMP_KEEP_NEAR] title={str(_comp.get('title') or '')[:140]} reason={_parallel_recovery_reason if _parallel_recovery_ok else 'same_family_bucket'}")
        else:
            _reasons.append("wrong_serial_bucket")
    elif _serial_near:
        _near = True
    _subject_grade = str(_subject.get("grade_state") or "").strip().lower()
    _comp_grade = str(_comp.get("grade_state") or "").strip().lower()
    if _subject_grade and _comp_grade and _subject_grade != _comp_grade:
        _reasons.append("graded_raw_mismatch")
    _subject_class_family = str(_subject.get("card_class_family") or "").strip().lower()
    _comp_class_family = str(_comp.get("card_class_family") or "").strip().lower()
    if _subject_class_family:
        if not _comp_class_family:
            _reasons.append("missing_card_class_family")
        elif _comp_class_family != _subject_class_family:
            _reasons.append("wrong_card_class_family")
    _specificity = sum(
        1
        for _value in (_subject_card, _subject_subset, _subject_parallel if _subject_parallel not in {"", "base", "raw"} else "", _subject_serial)
        if str(_value or "").strip()
    )
    if _reasons:
        return {
            "matched": False,
            "match_score": 0.0,
            "mismatch_reasons": _reasons,
            "match_level": "reject",
        }
    _match_level = "exact"
    if _near:
        _match_level = "near"
    if _specificity == 0 and not _subject_product:
        _match_level = "generic"
        return {
            "matched": False,
            "match_score": 0.0,
            "mismatch_reasons": ["generic_match_only"],
            "match_level": "generic",
        }
    _score = 1.0 if _match_level == "exact" else 0.84
    return {
        "matched": True,
        "match_score": _score,
        "mismatch_reasons": [],
        "match_level": _match_level,
    }


def _verify_operator_comp(subject_plan: Dict[str, Any], comp_row: Dict[str, Any]) -> Dict[str, Any]:
    _subject_fp = dict(subject_plan or {})
    _comp_seed = dict(comp_row or {})
    if str(_subject_fp.get("player_display") or "").strip() and not str(_comp_seed.get("player_name") or "").strip():
        _comp_seed["player_name"] = str(_subject_fp.get("player_display") or "").strip()
    _comp_fp = _build_card_fingerprint(_comp_seed)
    _match = _score_comp_fingerprint_match(_subject_fp, _comp_fp)
    return {
        "matched": bool(_match.get("matched")),
        "level": str(_match.get("match_level") or "reject"),
        "score": float(_match.get("match_score") or 0.0),
        "reject_reasons": list(_match.get("mismatch_reasons") or []),
        "comp_fingerprint": _comp_fp,
    }


def _trimmed_weighted_median(values: List[float], weights: List[float]) -> Optional[float]:
    if not values or len(values) != len(weights):
        return None
    pairs = sorted(zip(values, weights), key=lambda x: x[0])
    vals = [p[0] for p in pairs]
    wts = [max(0.0, p[1]) for p in pairs]
    if not any(w > 0 for w in wts):
        return None
    n = len(vals)
    if n >= 5:
        lo = int(n * 0.1)
        hi = max(lo + 1, n - int(n * 0.1))
        vals = vals[lo:hi]
        wts = wts[lo:hi]
    total_w = sum(wts)
    if total_w <= 0:
        return None
    cum = 0.0
    mid = total_w / 2.0
    for v, w in zip(vals, wts):
        cum += w
        if cum >= mid:
            return round(v, 2)
    return round(vals[-1], 2)


def _simple_median(values: List[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    m = len(s) // 2
    if len(s) % 2:
        return s[m]
    return (s[m - 1] + s[m]) / 2.0


RECENCY_DAYS_7 = 7
RECENCY_DAYS_30 = 30
FALLBACK_FLAGSHIP_SETS: FrozenSet[str] = frozenset(
    {"prizm", "select", "optic", "mosaic", "toppschrome", "bowmanchrome", "bowman", "topps"}
)


def _parallel_bucket_factor(bucket: str) -> float:
    b = str(bucket or "").strip().lower()
    if not b or b == "base":
        return 1.0
    if "silver" in b or "holo" in b:
        return 1.14
    if any(tok in b for tok in ("wave", "ice", "shock", "disco", "scope", "pulsar", "mojo")):
        return 1.22
    if "gold" in b:
        return 1.48
    if any(tok in b for tok in ("zebra", "genesis", "kaleidoscopic", "kaboom", "downtown", "color_blast", "superfractor", "finite")):
        return 1.65
    if "numbered" in b:
        return 1.32
    return 1.12


def _subset_family_factor(subset_family: str) -> float:
    s = str(subset_family or "").strip().lower()
    if not s:
        return 1.0
    if s in ("gold_team", "fireworks", "groovy", "razzle_dazzle", "genesis", "kaleidoscopic"):
        return 1.18
    if s in ("color_blast", "downtown", "kaboom"):
        return 1.42
    return 1.12


def _apply_grade_bridge_adjustment(
    price: float,
    *,
    target_grade_key: str,
    comp_grade_key: str,
) -> float:
    base = float(price or 0.0)
    if base <= 0:
        return 0.0
    tg = str(target_grade_key or "").strip().lower()
    cg = str(comp_grade_key or "").strip().lower()
    if not tg or tg == cg:
        return round(base, 2)
    bridge_map: Dict[Tuple[str, str], float] = {
        ("raw", "psa8"): 0.82,
        ("raw", "psa9"): 0.70,
        ("raw", "psa10"): 0.52,
        ("psa8", "raw"): 1.16,
        ("psa9", "raw"): 1.26,
        ("psa10", "raw"): 1.62,
        ("psa8", "psa9"): 0.88,
        ("psa9", "psa8"): 1.12,
        ("psa9", "psa10"): 0.82,
        ("psa10", "psa9"): 1.18,
    }
    factor = bridge_map.get((cg, tg))
    if factor is None and cg.startswith("psa") and tg.startswith("psa"):
        try:
            cgv = int(cg[3:])
            tgv = int(tg[3:])
            diff = tgv - cgv
            factor = 1.0 + (0.11 * diff)
        except ValueError:
            factor = 1.0
    if factor is None:
        factor = 1.0
    factor = min(1.75, max(0.52, float(factor)))
    return round(base * factor, 2)


def _structured_fallback_estimate(
    *,
    profile,
    items: List[Dict[str, Any]],
    target_title: str,
    target_item_id: str,
    target_item_url: str,
    target_listing_item: Optional[Dict[str, Any]],
    today: date,
) -> Optional[Dict[str, Any]]:
    if not items:
        return None

    target_parallel = normalize_parallel_bucket(profile)
    target_subset = str(getattr(profile, "subset_family", "") or "").strip().lower()
    target_product = str(getattr(profile, "product_family", "") or getattr(profile, "primary_set", "") or "").strip().lower()
    target_year = str(getattr(profile, "year", "") or "").strip()
    target_grade = grade_bucket_key(target_title)
    target_sig = _build_card_identity_signature(profile)
    estimates: List[Tuple[float, float, str, str]] = []

    for it in items or []:
        ct = (it.get("title") or "").strip()
        if not ct:
            continue
        same, _same_reason = comp_listing_validation.is_same_listing_as_target(
            target_item_id, target_item_url, target_listing_item, it
        )
        if same:
            continue
        excluded_listing, _, _ = should_exclude_from_single_card_valuation(ct)
        if excluded_listing:
            continue
        price = _extract_price_from_item(it)
        if price is None or price <= 0:
            continue
        pm, _ = player_match_score(profile, ct)
        if pm < 0.72:
            continue
        cp = parse_listing_profile(ct)
        comp_grade = grade_bucket_key(ct)
        if bool(target_grade != "raw") != bool(comp_grade != "raw"):
            continue
        if target_year and cp.year and cp.year != target_year:
            continue
        _direct_match = _fingerprint_match_result_for_titles(
            target_title,
            ct,
            ignore_grade=True,
        )
        if _direct_match.get("matched") and str(_direct_match.get("match_level") or "") in {"exact", "near"}:
            continue

        comp_product = str(getattr(cp, "product_family", "") or getattr(cp, "primary_set", "") or "").strip().lower()
        comp_subset = str(getattr(cp, "subset_family", "") or "").strip().lower()
        comp_parallel = normalize_parallel_bucket(cp)
        anchor_type = ""
        weight = 0.0
        band = 0.30
        inferred_price = float(price)

        if target_product and comp_product == target_product and target_subset and comp_subset == target_subset:
            anchor_type = "same_set_insert_diff_parallel"
            weight = 1.0
            band = 0.22
            comp_factor = _parallel_bucket_factor(comp_parallel)
            target_factor = _parallel_bucket_factor(target_parallel)
            ratio = min(1.85, max(0.58, target_factor / max(comp_factor, 0.55)))
            inferred_price = price * ratio
        elif target_product and comp_product == target_product:
            anchor_type = "same_product_player_diff_insert"
            weight = 0.72
            band = 0.30
            comp_factor = _subset_family_factor(comp_subset)
            target_factor = _subset_family_factor(target_subset)
            ratio = min(1.55, max(0.72, target_factor / max(comp_factor, 0.75)))
            inferred_price = price * ratio
        elif target_year and cp.year == target_year and comp_product in FALLBACK_FLAGSHIP_SETS:
            anchor_type = "same_player_year_flagship"
            weight = 0.48
            band = 0.38
            inferred_price = price
        else:
            continue

        if inferred_price <= 0:
            continue
        estimates.append((round(inferred_price, 2), weight, anchor_type, ct[:180]))

    if not estimates:
        return None

    prices = [x[0] for x in estimates]
    weights = [x[1] for x in estimates]
    midpoint = _trimmed_weighted_median(prices, weights) or _simple_median(prices)
    if midpoint is None or midpoint <= 0:
        return None
    anchor_counts = Counter(x[2] for x in estimates)
    dominant_anchor = anchor_counts.most_common(1)[0][0]
    base_band = {
        "same_set_insert_diff_parallel": 0.22,
        "same_product_player_diff_insert": 0.30,
        "same_player_year_flagship": 0.38,
    }.get(dominant_anchor, 0.34)
    spread = 0.0
    if len(prices) >= 2:
        spread = (max(prices) - min(prices)) / max(midpoint, 1e-6)
    band = min(0.45, max(base_band, base_band + spread * 0.35))
    low = round(max(1.0, midpoint * (1.0 - band)), 2)
    high = round(max(low, midpoint * (1.0 + band)), 2)
    return {
        "value_mid": round(float(midpoint), 2),
        "value_low": low,
        "value_high": high,
        "market_value_source": "structured_fallback",
        "market_lane_method": "inferred_structured_fallback",
        "valuation_basis": "structured_fallback_inferred",
        "valuation_flow_label": "structured_fallback",
        "valuation_final_status": "fallback_estimate_published",
        "confidence": "low",
        "comp_count": 0,
        "anchor_count": len(estimates),
        "anchor_type": dominant_anchor,
        "notes": (
            "No direct comps — inferred value only. "
            f"Fallback lane from {dominant_anchor.replace('_', ' ')} anchors ({len(estimates)} anchor listings)."
        ),
        "comp_lane_status": "fallback_family_only",
        "comp_lane_warning": "no direct comps - inferred value only",
        "comp_lane_label": target_sig,
        "comp_lane_signature": target_sig,
    }


@dataclass
class AcceptedComp:
    """One accepted comp after all hard filters (variant, grade, quality, etc.)."""

    idx: int
    title: str
    price: float
    weight: float
    qual: float
    gb_reason: str
    sale_date: Optional[date]
    days_ago: Optional[int]
    recency_bucket: str
    eligible_for_lane_pool: bool
    pool_exclude_reason: str
    sale_type: str = "unknown"
    grade_fallback: bool = False
    exactness_tier: str = "exact_strict"
    condition_flags: str = ""
    condition_penalty_mult: float = 1.0
    listing_quality_penalty_mult: float = 1.0
    listing_quality_notes: str = ""
    visual_match_score: Optional[float] = None
    visual_verification_status: str = "unavailable"
    duplicate_of_primary: bool = False
    duplicate_suppression_mult: float = 1.0
    manual_decision: str = "neutral"
    learned_adjust_mult: float = 1.0
    learned_adjust_note: str = ""
    counts_toward_value: bool = True
    mv_selection_tags: str = ""
    variant_match_level: str = ""
    variant_debug: str = ""
    comp_source_type: str = ""
    comp_source_pass: str = ""
    sold_date_valid: bool = True
    listing_end_iso: str = ""
    comp_lane_tier: str = ""
    comp_lane_reason: str = ""
    comp_identity_signature: str = ""


@dataclass
class MarketLanePick:
    lo: float
    hi: float
    lane_indices: FrozenSet[int]
    pool_indices: FrozenSet[int]
    method: str
    strength: float
    score: float
    recent_7_in_lane: int
    recent_30_in_lane: int
    used_fallback_value: bool
    fallback_reason: str
    lane_score_breakdown: str = ""
    lane_relaxed_beyond_strict: bool = False
    mv_lane_pool_relax_reason: str = ""


def _parse_iso_to_date(s: Any) -> Optional[date]:
    if s is None or s == "":
        return None
    raw = str(s).strip()
    if not raw:
        return None
    raw = raw.replace("Z", "+00:00")
    try:
        if "T" in raw:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc)
            return dt.date()
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _sale_date_from_item(item: Dict[str, Any]) -> Optional[date]:
    return _parse_iso_to_date(item.get("itemEndDate"))


def _build_accepted_comp(
    idx: int,
    item: Dict[str, Any],
    title: str,
    price: float,
    weight: float,
    qual: float,
    gb_reason: str,
    pool_kind: str,
    today: date,
    sold_recent_depth: int,
    sale_type: str = "unknown",
    grade_fallback: bool = False,
    exactness_tier: str = "exact_strict",
    variant_match_level: str = "",
    variant_debug: str = "",
    comp_lane_tier: str = "",
    comp_lane_reason: str = "",
    comp_identity_signature: str = "",
) -> AcceptedComp:
    src_pass = str(item.get("_valuation_query_pass") or "")
    src_type = comp_listing_validation.comp_source_type_label(pool_kind)
    end_raw = str(item.get("itemEndDate") or "").strip()[:40]
    sd = item.get("_val_resolved_sale_date")
    if sd is not None and not isinstance(sd, date):
        sd = None
    if sd is None:
        sd = _sale_date_from_item(item)
    pool_exclude_reason = ""
    if pool_kind == "active_browse":
        bucket = "active_proxy"
        days_ago: Optional[int] = None
        eligible = True
        sd = None
        listing_end_iso = end_raw
        sold_ok = False
    elif sd is not None:
        days_ago = max(0, (today - sd).days)
        if days_ago <= RECENCY_DAYS_7:
            bucket = "7d"
        elif days_ago <= RECENCY_DAYS_30:
            bucket = "30d"
        else:
            bucket = "older"
        if sold_recent_depth >= 4 and bucket == "older":
            eligible = False
            pool_exclude_reason = "stale>30d while enough 30d comps"
        else:
            eligible = True
        listing_end_iso = ""
        sold_ok = bool(sd) and sd <= today
    else:
        days_ago = None
        bucket = "unknown_sold"
        eligible = True
        pool_exclude_reason = ""
        listing_end_iso = ""
        sold_ok = pool_kind != "sold_finding"

    return AcceptedComp(
        idx=idx,
        title=title,
        price=price,
        weight=weight,
        qual=qual,
        gb_reason=gb_reason,
        sale_date=sd,
        days_ago=days_ago,
        recency_bucket=bucket,
        eligible_for_lane_pool=eligible,
        pool_exclude_reason=pool_exclude_reason,
        sale_type=sale_type or "unknown",
        grade_fallback=grade_fallback,
        exactness_tier=exactness_tier or "exact_strict",
        variant_match_level=variant_match_level,
        variant_debug=variant_debug,
        comp_source_type=src_type,
        comp_source_pass=src_pass,
        sold_date_valid=sold_ok,
        listing_end_iso=listing_end_iso,
        comp_lane_tier=comp_lane_tier,
        comp_lane_reason=comp_lane_reason,
        comp_identity_signature=comp_identity_signature[:180],
    )


def _sale_type_lane_boost(sale_type: str) -> float:
    """Higher = preferred when scoring market-lane windows (auction-first)."""
    return {
        "auction": 1.15,
        "auction_or_bin": 0.95,
        "fixed_price": 0.62,
        "fixed_or_offer": 0.55,
        "unknown": 0.78,
    }.get((sale_type or "unknown").lower(), 0.75)


def _smooth_recency_multiplier(days_ago: Optional[int], bucket: str) -> float:
    """
    Smooth decay vs calendar age; sqrt-capped so one single newest sale cannot dominate.
    """
    if bucket == "active_proxy":
        return 1.0
    if days_ago is None:
        return 0.84
    d = max(0.0, float(days_ago))
    raw = 0.38 + 0.62 * math.exp(-d / 19.0)
    capped = min(1.12, max(0.48, raw))
    return 0.55 + 0.45 * math.sqrt(capped)


def _recency_weight(bucket: str) -> float:
    return {
        "7d": 6.0,
        "30d": 3.6,
        "older": 1.0,
        "unknown_sold": 1.5,
        "active_proxy": 3.9,
    }.get(bucket, 1.0)


def _exactness_boost(gb_reason: str, qual: float) -> float:
    base = qual
    if gb_reason == "exact_grade":
        base += 0.18
    elif gb_reason == "raw_both":
        base += 0.05
    elif gb_reason == "cross_grade":
        base *= 0.52
    return min(1.35, base)


_PREMIUM_SUPPORT_LANE_TIERS: FrozenSet[str] = frozenset(
    {"subset_ecosystem_support", "scarcity_bucket_support", "rookie_color_support"}
)


def _exactness_tier_lane_weight(tier: str) -> float:
    return {
        "exact_strict": 1.22,
        "exact_synonym_normalized": 1.04,
        # legacy tier label from older runs / cached debug
        "exact_with_synonym_normalization": 1.04,
        "near_lane": 0.70,
        "subset_ecosystem_support": 0.62,
        "scarcity_bucket_support": 0.56,
        "rookie_color_support": 0.60,
        "weak_fallback_lane": 0.34,
        "sale_type_fallback": 0.80,
        "exact_grade_fallback": 0.66,
        "weaker_context_only": 0.40,
    }.get(tier or "", 0.72)


def _lane_price_mad_cv(comps: List[AcceptedComp]) -> Tuple[float, float]:
    ps = [c.price for c in comps]
    n = len(ps)
    if n < 2:
        return 0.0, 0.0
    med = _simple_median(ps)
    devs = [abs(p - med) for p in ps]
    mad_norm = _simple_median(devs) / max(med, 1e-6)
    mean = sum(ps) / n
    var = sum((p - mean) ** 2 for p in ps) / max(n - 1, 1)
    cv = (math.sqrt(var) / mean) if mean > 1e-6 else 0.0
    return mad_norm, cv


def _lane_window_score(
    comps: List[AcceptedComp],
    med_ref: float,
) -> Tuple[float, str]:
    if not comps:
        return -1e9, ""
    span = comps[-1].price - comps[0].price
    denom = max(med_ref, 1e-6)
    rel_span = span / denom
    count = len(comps)
    rw = sum(_recency_weight(c.recency_bucket) for c in comps)
    ex = sum(
        _exactness_tier_lane_weight(getattr(c, "exactness_tier", ""))
        * _exactness_boost(c.gb_reason, c.qual)
        * max(0.0, c.weight)
        for c in comps
    )
    density = count / (span + 0.04 * denom)
    tight = 1.0 / (1.0 + rel_span * 1.85)
    st_boost = sum(_sale_type_lane_boost(c.sale_type) for c in comps)
    mad_norm, cv = _lane_price_mad_cv(comps)
    dup_pen = sum(
        1.0 - min(1.0, float(getattr(c, "duplicate_suppression_mult", 1.0) or 1.0))
        for c in comps
    ) / max(len(comps), 1)
    strict_ratio = sum(1 for c in comps if c.exactness_tier == "exact_strict") / len(comps)
    recent_strict_ratio = (
        sum(
            1
            for c in comps
            if c.recency_bucket == "7d" and c.exactness_tier == "exact_strict"
        )
        / max(len(comps), 1)
    )
    auc = sum(1 for c in comps if c.sale_type in ("auction", "auction_or_bin"))
    sale_maj = max(auc, len(comps) - auc) / len(comps)
    consistency_bonus = 3.8 / (1.0 + 2.35 * mad_norm + 1.2 * cv + 2.0 * dup_pen)
    tier_mix_bonus = 2.05 * (strict_ratio**0.75)
    sale_mix_bonus = 0.52 * sale_maj
    base = (
        1.15 * rw
        + 0.95 * ex
        + 0.42 * (count**1.08)
        + 5.5 * tight
        + 1.1 * min(density, 8.0)
        + 0.52 * st_boost
    )
    total = base + consistency_bonus + tier_mix_bonus + sale_mix_bonus
    br = (
        f"base={base:.2f} mad={mad_norm:.3f} cv={cv:.3f} dup_pen={dup_pen:.2f} "
        f"strict_r={strict_ratio:.2f} recent7_strict_r={recent_strict_ratio:.2f} "
        f"sale_maj={sale_maj:.2f} "
        f"+cons={consistency_bonus:.2f} +tier={tier_mix_bonus:.2f} +sale={sale_mix_bonus:.2f}"
    )
    return total, br


def _iqr_trim_comps(lane: List[AcceptedComp]) -> List[AcceptedComp]:
    if len(lane) < 5:
        return lane
    ps = sorted(c.price for c in lane)
    n = len(ps)
    q1 = ps[n // 4]
    q3 = ps[(3 * n) // 4]
    iqr = q3 - q1
    if iqr <= 0:
        return lane
    lo_b, hi_b = q1 - 1.45 * iqr, q3 + 1.45 * iqr
    out = [c for c in lane if lo_b <= c.price <= hi_b]
    return out if len(out) >= 2 else lane


def select_market_lane(
    accepted: List[AcceptedComp],
    pool_kind: str,
    today: date,
) -> MarketLanePick:
    """
    Score contiguous windows on price-sorted lane pool; prefer tight bands with strong recency
    and exact-grade comps. Stale sold comps are dropped from the pool when enough 30d/7d depth exists.
    Prefers counts_toward_value (strict) lane members; does not expand a single strict comp into
    broader lane comps for window scoring.
    """
    n = len(accepted)
    idx_all = frozenset(c.idx for c in accepted)
    if n < 2:
        if n == 1:
            c0 = accepted[0]
            st_ok = bool(getattr(c0, "counts_toward_value", True))
            return MarketLanePick(
                lo=c0.price,
                hi=c0.price,
                lane_indices=frozenset({c0.idx}),
                pool_indices=idx_all,
                method="single_comp",
                strength=0.35,
                score=0.0,
                recent_7_in_lane=1 if c0.recency_bucket == "7d" else 0,
                recent_30_in_lane=1 if c0.recency_bucket in ("7d", "30d") else 0,
                used_fallback_value=True,
                fallback_reason="small_n",
                lane_score_breakdown="single_comp",
                lane_relaxed_beyond_strict=not st_ok,
                mv_lane_pool_relax_reason="" if st_ok else "single_accepted_not_strict",
            )
        return MarketLanePick(
            lo=0.0,
            hi=0.0,
            lane_indices=frozenset(),
            pool_indices=frozenset(),
            method="empty",
            strength=0.0,
            score=0.0,
            recent_7_in_lane=0,
            recent_30_in_lane=0,
            used_fallback_value=True,
            fallback_reason="empty",
            lane_score_breakdown="empty",
            lane_relaxed_beyond_strict=False,
            mv_lane_pool_relax_reason="",
        )

    base_lane = [c for c in accepted if c.eligible_for_lane_pool]
    strict_lane = [c for c in base_lane if getattr(c, "counts_toward_value", True)]
    lane_relaxed = False
    lane_relax_reason = ""

    if len(strict_lane) >= 2:
        pool = strict_lane
    elif len(strict_lane) == 1:
        pool = strict_lane
    elif len(base_lane) >= 2:
        pool = base_lane
        lane_relaxed = True
        lane_relax_reason = "strict_lane_thin_used_broad_eligible"
    elif len(base_lane) == 1:
        pool = base_lane
        lane_relaxed = True
        lane_relax_reason = "no_strict_used_sole_broad_lane"
    else:
        pool = strict_lane

    pool_idx = frozenset(c.idx for c in pool)

    if len(pool) == 1:
        c0 = pool[0]
        return MarketLanePick(
            lo=c0.price,
            hi=c0.price,
            lane_indices=frozenset({c0.idx}),
            pool_indices=pool_idx,
            method="single_comp",
            strength=0.35,
            score=0.0,
            recent_7_in_lane=1 if c0.recency_bucket == "7d" else 0,
            recent_30_in_lane=1 if c0.recency_bucket in ("7d", "30d") else 0,
            used_fallback_value=True,
            fallback_reason="small_n",
            lane_score_breakdown="single_comp",
            lane_relaxed_beyond_strict=lane_relaxed,
            mv_lane_pool_relax_reason=lane_relax_reason,
        )

    if len(pool) == 0:
        if len(accepted) >= 2:
            pool = list(accepted)
            pool_idx = idx_all
            lane_relaxed = True
            extra = "empty_lane_pool_full_accepted"
            lane_relax_reason = f"{lane_relax_reason}|{extra}" if lane_relax_reason else extra
        elif len(accepted) == 1:
            c0 = accepted[0]
            return MarketLanePick(
                lo=c0.price,
                hi=c0.price,
                lane_indices=frozenset({c0.idx}),
                pool_indices=idx_all,
                method="single_comp",
                strength=0.35,
                score=0.0,
                recent_7_in_lane=1 if c0.recency_bucket == "7d" else 0,
                recent_30_in_lane=1 if c0.recency_bucket in ("7d", "30d") else 0,
                used_fallback_value=True,
                fallback_reason="small_n",
                lane_score_breakdown="single_comp",
                lane_relaxed_beyond_strict=True,
                mv_lane_pool_relax_reason="no_eligible_lane_pool",
            )
        return MarketLanePick(
            lo=0.0,
            hi=0.0,
            lane_indices=frozenset(),
            pool_indices=frozenset(),
            method="empty",
            strength=0.0,
            score=0.0,
            recent_7_in_lane=0,
            recent_30_in_lane=0,
            used_fallback_value=True,
            fallback_reason="empty",
            lane_score_breakdown="empty",
            lane_relaxed_beyond_strict=False,
            mv_lane_pool_relax_reason="",
        )

    med_pool = _simple_median([c.price for c in pool])
    sort_key = lambda c: (c.price, -_recency_weight(c.recency_bucket), -c.qual, -c.weight)
    psort = sorted(pool, key=sort_key)
    m = len(psort)

    best_score = -1e18
    best_sub: List[AcceptedComp] = psort[:2]
    best_breakdown = ""
    for i in range(m):
        for j in range(i + 1, m):
            sub = psort[i : j + 1]
            sc, br = _lane_window_score(sub, med_pool)
            if sc > best_score + 1e-9:
                best_score = sc
                best_sub = sub
                best_breakdown = br
            elif abs(sc - best_score) <= 1e-9:
                # Tie-break: more recent mass, then tighter span
                old_r = sum(_recency_weight(c.recency_bucket) for c in best_sub)
                new_r = sum(_recency_weight(c.recency_bucket) for c in sub)
                if new_r > old_r + 1e-9:
                    best_score = sc
                    best_sub = sub
                    best_breakdown = br
                elif abs(new_r - old_r) <= 1e-9:
                    if (sub[-1].price - sub[0].price) < (best_sub[-1].price - best_sub[0].price) - 1e-9:
                        best_sub = sub
                        best_breakdown = br

    lo = min(c.price for c in best_sub)
    hi = max(c.price for c in best_sub)
    lane_idx = frozenset(c.idx for c in best_sub)
    rel_w = (hi - lo) / max(med_pool, 1e-6)
    r7 = sum(1 for c in best_sub if c.recency_bucket == "7d")
    r30 = sum(1 for c in best_sub if c.recency_bucket in ("7d", "30d", "active_proxy"))
    strength = min(
        1.0,
        (sum(_recency_weight(c.recency_bucket) for c in best_sub) / (5.5 * len(best_sub)))
        * min(1.2, len(best_sub) / 6.0)
        * (1.0 / (1.0 + rel_w * 1.2)),
    )

    method = "market_lane_scored_window"
    if pool_kind == "sold_finding" and any(not c.eligible_for_lane_pool for c in accepted):
        method = "market_lane_recent_pref"

    return MarketLanePick(
        lo=lo,
        hi=hi,
        lane_indices=lane_idx,
        pool_indices=pool_idx,
        method=method,
        strength=round(strength, 4),
        score=best_score,
        recent_7_in_lane=r7,
        recent_30_in_lane=r30,
        used_fallback_value=False,
        fallback_reason="",
        lane_score_breakdown=best_breakdown,
        lane_relaxed_beyond_strict=lane_relaxed,
        mv_lane_pool_relax_reason=lane_relax_reason,
    )


def compute_lane_market_value(
    lane_comps: List[AcceptedComp],
    *,
    accepted_n7: int = 0,
) -> Tuple[Optional[float], Dict[int, float]]:
    """
    Trimmed weighted median inside the lane with smooth recency multipliers.
    Returns (point_estimate, per-comp final weights for debug).
    """
    if not lane_comps:
        return None, {}
    trimmed = _iqr_trim_comps(lane_comps)
    vals = [c.price for c in trimmed]
    wts: List[float] = []
    dbg: Dict[int, float] = {}
    tier_vw = {
        "exact_strict": 1.0,
        "exact_synonym_normalized": 0.94,
        "exact_with_synonym_normalization": 0.94,
        "near_lane": 0.64,
        "subset_ecosystem_support": 0.56,
        "scarcity_bucket_support": 0.50,
        "rookie_color_support": 0.54,
        "weak_fallback_lane": 0.28,
        "sale_type_fallback": 0.86,
        "exact_grade_fallback": 0.72,
        "weaker_context_only": 0.48,
    }
    for c in trimmed:
        w = max(0.0, c.weight)
        if c.gb_reason == "cross_grade":
            w *= 0.38
        if c.gb_reason == "adjacent_grade":
            w *= 0.26
        w *= tier_vw.get(getattr(c, "exactness_tier", "") or "", 0.78)
        if accepted_n7 >= 3 and c.recency_bucket == "older":
            w *= 0.22
        rm = _smooth_recency_multiplier(c.days_ago, c.recency_bucket)
        w *= rm
        if c.sale_type in ("fixed_price", "fixed_or_offer"):
            w *= 0.88
        dbg[c.idx] = w
        wts.append(w)
    pt = _trimmed_weighted_median(vals, wts)
    if pt is not None:
        return pt, dbg
    return round(_simple_median(vals), 2), dbg


def _format_accepted_comp_debug_line(
    c: AcceptedComp,
    in_lane: bool,
    reason: str,
    recency_mult: float,
    final_w: float,
) -> str:
    t = (c.title or "").replace("\n", " ").strip()
    if len(t) > 90:
        t = t[:87] + "..."
    ds = c.sale_date.isoformat() if c.sale_date else "n/a"
    lane_flag = "IN_LANE" if in_lane else "OUT_OF_LANE"
    gf = "gf" if c.grade_fallback else "ex"
    tier = getattr(c, "exactness_tier", "") or "?"
    cf = (c.condition_flags or "-").replace("|", "/")[:36]
    lqn = (getattr(c, "listing_quality_notes", "") or "-")[:32]
    dup = "DUP" if getattr(c, "duplicate_of_primary", False) else ""
    vis = getattr(c, "visual_verification_status", "") or "-"
    vsc = c.visual_match_score
    vs_s = f"{vsc:.2f}" if vsc is not None else "-"
    cpen = getattr(c, "condition_penalty_mult", 1.0)
    lqpen = getattr(c, "listing_quality_penalty_mult", 1.0)
    md = getattr(c, "manual_decision", "neutral") or "neutral"
    lm = getattr(c, "learned_adjust_mult", 1.0)
    return (
        f"{lane_flag} | ${c.price:.2f} | {ds} | {c.recency_bucket} | rm={recency_mult:.2f} | "
        f"w={final_w:.3f} | tier={tier} | sale={c.sale_type} | {gf} | gb={c.gb_reason} | q={c.qual:.2f} | "
        f"cond={cf} c×{cpen:.2f} lq×{lqpen:.2f} [{lqn}] | vis={vis}({vs_s}) {dup} | "
        f"man={md} learn×{lm:.2f} | "
        f"{reason} | {t}"
    )


def build_lane_debug_report(
    accepted: List[AcceptedComp],
    pick: MarketLanePick,
    n7: int,
    n30: int,
    valuation_method: str,
    final_mv: Optional[float],
    lane_weights: Optional[Dict[int, float]] = None,
    valuation_sale_mode: str = "",
    auction_n: int = 0,
    fixed_n: int = 0,
    exact_grade_n: int = 0,
    fallback_grade_n: int = 0,
    confidence_rationale: str = "",
) -> str:
    lw = lane_weights or {}
    tc = tier_counts(accepted)
    lines: List[str] = [
        f"summary: accepted={len(accepted)} | recent_7d={n7} | recent_30d={n30} | "
        f"auction={auction_n} fixed={fixed_n} | exact_grade={exact_grade_n} grade_fb={fallback_grade_n} | "
        f"sale_mode={valuation_sale_mode} | lane=[{pick.lo:.2f},{pick.hi:.2f}] lane_n={len(pick.lane_indices)} | "
        f"method={valuation_method} | strength={pick.strength:.3f} | mv={final_mv}",
        f"exactness_tiers: {tc}",
        f"lane_score: {getattr(pick, 'lane_score_breakdown', '') or 'n/a'}",
    ]
    if confidence_rationale:
        lines.append(f"confidence_rationale: {confidence_rationale}")
    for c in accepted:
        if c.idx in pick.lane_indices:
            reason = "included in selected market lane"
        elif not c.eligible_for_lane_pool:
            reason = c.pool_exclude_reason or "excluded from lane pool"
        elif c.idx not in pick.pool_indices:
            reason = "not in lane pool"
        else:
            reason = "outside winning price window (suppressed vs lane)"
        rm = _smooth_recency_multiplier(c.days_ago, c.recency_bucket)
        fw = lw.get(c.idx, 0.0)
        lines.append(_format_accepted_comp_debug_line(c, c.idx in pick.lane_indices, reason, rm, fw))
    return "\n".join(lines)[:12000]


def _confidence_from_market_lane(
    n_accepted: int,
    pick: MarketLanePick,
    rel_lane_width: float,
    cross_grade_used: bool,
    used_value_fallback: bool,
    fallback_reason: str,
    n7: int,
    n30: int,
    *,
    exact_grade_n: int,
    grade_fallback_used: bool,
    valuation_sale_mode: str,
    auction_in_lane: int,
    lane_n: int,
    weak_lane_frac: float = 0.0,
    dup_downgraded: int = 0,
    cond_issues_accepted: int = 0,
    cond_issues_lane: int = 0,
    mv_relaxed_beyond_strict: bool = False,
    strict_comp_count: int = 0,
    mv_pool_mode: str = "",
) -> Tuple[str, str]:
    """Returns (confidence, short rationale for debug)."""
    parts: List[str] = []
    if n_accepted < MIN_ACCEPTED_COMPS:
        return "estimate_only", "too_few_accepted_comps"
    if used_value_fallback and fallback_reason == "small_n":
        return "estimate_only", "fallback_small_n"
    if cross_grade_used:
        parts.append("cross_grade_in_pool")
    if grade_fallback_used:
        parts.append("psa_adjacent_grade_fallback")
    if used_value_fallback:
        parts.append(f"value_fallback:{fallback_reason}")
    if mv_relaxed_beyond_strict:
        parts.append("relaxed_mv_pool_beyond_strict")
    if mv_pool_mode == "relaxed_only":
        parts.append("mv_pool_relaxed_only")
    if strict_comp_count < 2 and n_accepted >= MIN_ACCEPTED_COMPS:
        parts.append("thin_strict_value_eligible")
    if strict_comp_count == 0:
        parts.append("no_strict_comps")
    if pick.strength < 0.38 or rel_lane_width > 0.62:
        parts.append("weak_lane_or_wide")
    if rel_lane_width > 0.72:
        parts.append("very_wide_lane")
    if exact_grade_n < 2 and n7 < 2:
        parts.append("thin_exact_or_recent")
    if valuation_sale_mode == "fixed_price_lane" and auction_in_lane == 0:
        parts.append("no_auction_in_lane")
    if valuation_sale_mode == "blended":
        parts.append("blended_sale_types")
    if weak_lane_frac >= 0.52:
        parts.append("weak_exactness_lane_mix")
    if dup_downgraded >= max(2, n_accepted // 3):
        parts.append("duplicate_suppression_stress")
    if cond_issues_accepted >= max(2, n_accepted // 3):
        parts.append("condition_noise_pool")
    if cond_issues_lane >= max(2, lane_n // 2) and lane_n >= 2:
        parts.append("condition_noise_lane")

    penalized = (
        len(parts) >= 3
        or grade_fallback_used
        or (used_value_fallback and fallback_reason != "small_n")
        or mv_relaxed_beyond_strict
        or mv_pool_mode == "relaxed_only"
        or strict_comp_count == 0
        or rel_lane_width > 0.72
        or weak_lane_frac >= 0.60
    )

    if (
        not penalized
        and n7 >= 4
        and pick.recent_7_in_lane >= 3
        and rel_lane_width <= 0.28
        and pick.strength >= 0.56
        and exact_grade_n >= 4
        and valuation_sale_mode == "auction_focused"
    ):
        return "high", ";".join(parts) if parts else "strong_recent_auction_lane"
    if (
        not cross_grade_used
        and not grade_fallback_used
        and not used_value_fallback
        and not mv_relaxed_beyond_strict
        and mv_pool_mode != "relaxed_only"
        and n30 >= 5
        and pick.recent_30_in_lane >= 4
        and rel_lane_width <= 0.40
        and exact_grade_n >= 3
        and strict_comp_count >= 3
    ):
        return "medium", ";".join(parts) if parts else "solid_lane"
    if (
        cross_grade_used
        or grade_fallback_used
        or used_value_fallback
        or pick.strength < 0.36
        or strict_comp_count == 0
        or mv_pool_mode == "relaxed_only"
    ):
        return "low", ";".join(parts) if parts else "fallbacks_or_noise"
    if exact_grade_n < 2 or rel_lane_width > 0.52:
        return "low", ";".join(parts) if parts else "thin_exact_or_wide_lane"
    return "low", ";".join(parts) if parts else "default_low"


def _cap_confidence_for_relaxed_mv_pool(conf: str, mv_pool_mode: str, mv_relaxed_beyond_strict: bool) -> str:
    """Prevent overstating certainty when pricing used non-strict accepted comps."""
    c = (conf or "low").strip().lower()
    if mv_pool_mode == "relaxed_only":
        if c == "high":
            return "medium"
        return c
    if mv_relaxed_beyond_strict and c == "high":
        return "medium"
    return c


def _lane_valuation_sale_mode(lane_comps: List[AcceptedComp]) -> str:
    if not lane_comps:
        return "unknown"
    a = sum(1 for c in lane_comps if c.sale_type in ("auction", "auction_or_bin"))
    f = sum(1 for c in lane_comps if c.sale_type in ("fixed_price", "fixed_or_offer"))
    n = len(lane_comps)
    if a >= max(2, (n + 1) // 2):
        return "auction_focused"
    if a == 0 and f > 0:
        return "fixed_price_lane"
    if a > 0 and f > 0:
        return "blended"
    return "blended"


def _decide_valuation_strength(
    val_point: Optional[float],
    n: int,
    lane_list: List[AcceptedComp],
    pick: MarketLanePick,
    dup_downgraded: int,
    cond_issues_accepted: int,
    weak_lane_frac: float,
    rel_lane: float,
    used_fallback: bool,
    grade_fallback_used: bool,
    cross_grade_used: bool,
    cond_issues_lane: int,
    *,
    mv_relaxed_beyond_strict: bool = False,
    strict_comp_count: int = 0,
) -> Tuple[str, List[str]]:
    """
    strong_market_value — publish as primary MV
    provisional_estimate — numeric hint only; confidence capped
    no_reliable_value — suppress published MV (value cleared)
    """
    reasons: List[str] = []
    if val_point is None or val_point <= 0:
        return "no_reliable_value", ["no_numeric_value"]
    if n < 2:
        reasons.append("very_few_comps")
    dup_thresh = max(2, int(0.45 * max(n, 1)))
    if dup_downgraded >= dup_thresh:
        reasons.append("heavy_duplicate_suppression")
    ci_thresh = max(2, int(0.5 * max(n, 1)))
    if cond_issues_accepted >= ci_thresh:
        reasons.append("many_condition_flagged_comps")
    if weak_lane_frac >= 0.58:
        reasons.append("weak_exactness_dominates_lane")
    ln = len(lane_list)
    if ln and cond_issues_lane >= max(2, (ln + 1) // 2):
        reasons.append("condition_issues_in_lane")
    if used_fallback and rel_lane > 0.55:
        reasons.append("wide_lane_value_fallback")
    if cross_grade_used:
        reasons.append("cross_grade_in_pool")
    if grade_fallback_used and n < 7:
        reasons.append("grade_adjacent_thin_context")
    if pick.strength < 0.30 and n >= 4:
        reasons.append("unstable_lane_strength")
    if mv_relaxed_beyond_strict:
        reasons.append("relaxed_value_pool_beyond_strict")
    if strict_comp_count < 2 and n >= 4 and mv_relaxed_beyond_strict:
        reasons.append("thin_strict_with_relaxed_pricing")

    # Require more downgrade signals before withholding (common cards often hit 2 borderline flags).
    if len(reasons) >= 4:
        return "no_reliable_value", reasons
    if (
        len(reasons) == 0
        and not used_fallback
        and not mv_relaxed_beyond_strict
        and rel_lane <= 0.36
        and n >= 6
        and weak_lane_frac < 0.42
        and dup_downgraded <= max(1, n // 4)
        and cond_issues_accepted <= max(1, n // 3)
    ):
        return "strong_market_value", []
    if len(reasons) >= 1:
        return "provisional_estimate", reasons
    if used_fallback or weak_lane_frac >= 0.35:
        return "provisional_estimate", reasons or ["fallback_or_mixed_context"]
    return "strong_market_value", []


def _format_visual_debug_summary(
    dominant: str,
    counts: Dict[str, int],
) -> str:
    parts = [f"dominant_status={dominant or 'n/a'}"]
    for k, v in sorted(counts.items(), key=lambda x: -x[1])[:8]:
        parts.append(f"{k}:{v}")
    return " | ".join(parts)


def _build_valuation_audit_header(
    *,
    valuation_strength: str,
    downgrade_reasons: List[str],
    canonical_key: str,
    profile_summary: str,
    valuation_sale_mode: str,
    exact_grade_n: int,
    fallback_grade_n: int,
    tier_counts_map: Dict[str, int],
    n7: int,
    n30: int,
    dup_suppressed: int,
    cond_issues_accepted: int,
    cond_issues_lane: int,
    lane_breakdown: str,
    weak_lane_frac: float,
    confidence: str,
    confidence_rationale: str,
    visual_summary: str,
    result_mv: Optional[float],
    withheld_mv: Optional[float] = None,
    manual_audit_line: str = "",
) -> str:
    ck = (canonical_key or "")[:200]
    prof = (profile_summary or "")[:400].replace("\n", " ")
    dr = "; ".join(downgrade_reasons) if downgrade_reasons else "—"
    wh = f"{withheld_mv:.2f}" if withheld_mv is not None else "—"
    mv_s = f"{result_mv:.2f}" if result_mv is not None and result_mv > 0 else "—"
    lines = [
        "=== VALUATION AUDIT (read first) ===",
        f"result_type: {valuation_strength} "
        f"(strong_market_value | provisional_estimate | no_reliable_value)",
        f"published_mv: {mv_s}",
        f"withheld_pre_gate_mv: {wh}",
        f"top_downgrades: {dr}",
        f"canonical_key: {ck or '—'}",
        f"normalized_profile: {prof or '—'}",
        f"sale_mode(lane): {valuation_sale_mode}",
        f"exact_grade_comps: {exact_grade_n} | grade_fallback_comps: {fallback_grade_n}",
        f"exactness_tier_counts: {tier_counts_map}",
        f"recent_accepted: 7d={n7} | 30d={n30}",
        f"duplicate_comps_downweighted: {dup_suppressed}",
        f"condition_flagged_accepted: {cond_issues_accepted} | in_lane: {cond_issues_lane}",
        f"weak_tier_weight_fraction(lane): {weak_lane_frac:.3f}",
        f"lane_score_components: {lane_breakdown or '—'}",
        f"visual_verification: {visual_summary}",
        f"confidence: {confidence} | rationale: {confidence_rationale}",
        f"manual_review: {manual_audit_line or '—'}",
        "=== DETAIL: accepted / rejected comps below ===",
    ]
    return "\n".join(lines)


def _apply_mv_value_pool_tags(
    accepted_comps: List[AcceptedComp],
    comp_items: List[Dict[str, Any]],
    profile,
    listing_title: str,
) -> int:
    """
    Mark comps that may stay in the accepted list for transparency but must not
    drive market value when stricter matches exist. Uses title-only signals.
    """
    _ = listing_title
    strict_tiers = frozenset({"exact_strict", "exact_synonym_normalized"})
    support_tiers = _PREMIUM_SUPPORT_LANE_TIERS
    n_ok = 0
    for c in accepted_comps:
        tags: List[str] = []
        pm, _pm_lab = player_match_score(profile, c.title)
        if pm >= 0.72:
            tags.append("strong_player")
        elif target_has_identifiable_player(profile):
            tags.append("player_context")

        if not comp_set_matches_target_strict(c.title, profile):
            tags.append("set_mismatch")

        cn_ok = True
        if profile.card_number:
            ccn = _extract_card_number(c.title)
            if ccn != profile.card_number:
                comp_lane_tier = getattr(c, "comp_lane_tier", "") or ""
                _adj_ok = (
                    comp_lane_tier == "rookie_color_support"
                    and str(ccn or "").isdigit()
                    and str(profile.card_number or "").isdigit()
                    and abs(int(str(ccn)) - int(str(profile.card_number))) <= 1
                )
                if _adj_ok:
                    tags.append("card_number_adjacent_support")
                else:
                    tags.append("card_number_mismatch")
                    cn_ok = False

        tier = getattr(c, "exactness_tier", "") or ""
        comp_lane_tier = getattr(c, "comp_lane_tier", "") or ""
        support_lane = comp_lane_tier in support_tiers or tier in support_tiers
        if comp_lane_tier and comp_lane_tier != "exact_lane":
            tags.append(comp_lane_tier)
        if support_lane:
            tags.append("premium_support_lane")
        if tier not in strict_tiers:
            tags.append("weak_exactness")

        qual = float(getattr(c, "qual", 0.0) or 0.0)
        if qual < 0.60:
            tags.append("weak_context")

        fb = bool(getattr(c, "grade_fallback", False)) or c.gb_reason in (
            "adjacent_grade",
            "cross_grade",
            "graded_other",
        )
        if fb:
            tags.append("fallback_only")

        vm = (getattr(c, "variant_match_level", "") or "").strip()
        if vm:
            tags.append(vm)
        elif tier in ("weaker_context_only", "sale_type_fallback", "exact_grade_fallback"):
            tags.append("weak_variant_match")

        family_boost = vm in ("exact_variant_match", "same_variant_family")
        support_vm_ok = vm in ("exact_variant_match", "same_variant_family") or (
            comp_lane_tier == "scarcity_bucket_support" and vm == "weak_variant_match"
        )
        qual_floor = 0.62 if support_lane else (0.56 if family_boost else 0.60)
        tier_ok = (
            (tier in strict_tiers and comp_lane_tier in ("", "exact_lane"))
            or (
                family_boost
                and tier in ("exact_strict", "exact_synonym_normalized")
                and comp_lane_tier in ("", "exact_lane")
                and qual >= 0.56
            )
            or (
                family_boost
                and tier in ("sale_type_fallback", "near_lane")
                and comp_lane_tier in ("near_lane", "")
                and qual >= 0.58
            )
            or (
                support_lane
                and tier in support_tiers
                and comp_lane_tier in support_tiers
                and support_vm_ok
                and qual >= 0.62
            )
        )

        eligible = (
            pm >= 0.58
            and comp_set_matches_target_strict(c.title, profile)
            and cn_ok
            and tier_ok
            and qual >= qual_floor
            and not fb
        )
        if eligible:
            tags.append("final_value_eligible")
            c.counts_toward_value = True
            n_ok += 1
        else:
            c.counts_toward_value = False
        c.mv_selection_tags = "|".join(tags)
    return n_ok


def _apply_manual_review_weights(
    accepted_comps: List[AcceptedComp],
    comp_items: List[Dict[str, Any]],
    man_state: Dict[str, Any],
    decisions: Dict[str, str],
) -> Tuple[int, bool]:
    """Boost approved comps; apply learned token/seller multipliers. Returns (n_approve_boosted, learned_skewed)."""
    n_ap = 0
    skewed = False
    for c, it in zip(accepted_comps, comp_items):
        cid = manual_comp_review.comp_stable_id(it, c.title)
        dec = decisions.get(cid, "neutral")
        c.manual_decision = dec
        if dec == "approve":
            c.weight *= 1.58
            n_ap += 1
        lm, lnote = manual_comp_review.learned_comp_multiplier(
            man_state, title=c.title, seller=manual_comp_review.seller_from_item(it)
        )
        c.learned_adjust_mult = lm
        c.learned_adjust_note = lnote
        if abs(lm - 1.0) > 0.025:
            skewed = True
        c.weight = max(0.0, c.weight) * lm
    return n_ap, skewed


def _build_accepted_comps_snapshot_json(
    accepted_comps: List[AcceptedComp],
    comp_items: List[Dict[str, Any]],
    pick: MarketLanePick,
    target_title: str = "",
    target_item_id: str = "",
) -> str:
    rows: List[Dict[str, Any]] = []
    tp = parse_listing_profile(target_title) if (target_title or "").strip() else None
    for c, it in zip(accepted_comps, comp_items):
        cid = manual_comp_review.comp_stable_id(it, c.title)
        in_lane = c.idx in pick.lane_indices
        ct = bool(getattr(c, "counts_toward_value", True))
        if in_lane and ct:
            value_tier = "used_in_final_value"
        elif ct:
            value_tier = "accepted_mv_eligible_not_lane"
        else:
            value_tier = "accepted_not_in_mv"
        cp = parse_listing_profile(c.title)
        c_dbg = parallel_vocab.normalized_variant_family_debug(
            cp.primary_set, cp.raw_title, normalize_parallel_bucket(cp)
        )
        parallel_payload: Dict[str, Any] = {"comp": c_dbg}
        if tp is not None:
            parallel_payload["target"] = parallel_vocab.normalized_variant_family_debug(
                tp.primary_set, tp.raw_title, normalize_parallel_bucket(tp)
            )
            parallel_payload["families_equal"] = parallel_vocab.infer_variant_family_id(
                tp.primary_set, tp.raw_title
            ) == parallel_vocab.infer_variant_family_id(tp.primary_set, c.title)
        rows.append(
            {
                "comp_id": cid,
                "item_id": str(it.get("itemId") or ""),
                "title": c.title,
                "price": c.price,
                "sold_date": c.sale_date.isoformat() if c.sale_date else "",
                "listing_end_preview": (getattr(c, "listing_end_iso", "") or "")[:36],
                "source_type": getattr(c, "comp_source_type", "") or "",
                "source_pass": getattr(c, "comp_source_pass", "") or "",
                "sold_date_valid": bool(getattr(c, "sold_date_valid", True)),
                "target_item_id": (target_item_id or "")[:32],
                "target_id_match": "no",
                "sale_type": c.sale_type,
                "grade_bucket": grade_bucket_key(c.title),
                "exactness_tier": getattr(c, "exactness_tier", ""),
                "lane": getattr(c, "comp_lane_tier", "") or "",
                "comp_lane_tier": getattr(c, "comp_lane_tier", "") or "",
                "comp_lane_reason": getattr(c, "comp_lane_reason", "") or "",
                "support_signal_reason": getattr(c, "comp_lane_reason", "") or "",
                "condition_flags": c.condition_flags or "",
                "in_lane": in_lane,
                "counts_toward_value": ct,
                "value_tier": value_tier,
                "mv_selection_tags": getattr(c, "mv_selection_tags", "") or "",
                "variant_match_level": getattr(c, "variant_match_level", "") or "",
                "variant_match_debug": (getattr(c, "variant_debug", "") or "")[:320],
                "parallel_debug": json.dumps(parallel_payload, ensure_ascii=False)[:450],
                "image_url": manual_comp_review.thumb_url_from_item(it),
                "seller": manual_comp_review.seller_from_item(it),
                "manual_decision": getattr(c, "manual_decision", "neutral") or "neutral",
                "learned_mult": round(float(getattr(c, "learned_adjust_mult", 1.0) or 1.0), 4),
            }
        )
    try:
        return json.dumps(rows, ensure_ascii=False)[:48000]
    except (TypeError, ValueError):
        return "[]"


_TRUE_MV_EXACT_TIERS: FrozenSet[str] = frozenset(
    {"exact_strict", "exact_synonym_normalized", "exact_with_synonym_normalization", "exact_grade_fallback"}
)


def _accepted_comp_serial_label(title: str) -> str:
    _serial = _normalize_fingerprint_serial_denominator(_extract_serial_denominator(title))
    return f"/{_serial}" if _serial else ""


def _accepted_comp_evidence_entry(
    comp: AcceptedComp,
    *,
    match_type: str,
    reason: str = "",
) -> Dict[str, Any]:
    _price = round(float(getattr(comp, "price", 0.0) or 0.0), 2)
    _date = ""
    if getattr(comp, "sale_date", None):
        _date = comp.sale_date.isoformat()
    elif str(getattr(comp, "listing_end_iso", "") or "").strip():
        _date = str(getattr(comp, "listing_end_iso", "") or "").strip()[:10]
    _entry: Dict[str, Any] = {
        "price": _price,
        "date": _date,
        "match_type": match_type,
        "serial": _accepted_comp_serial_label(str(getattr(comp, "title", "") or "")),
    }
    if reason:
        _entry["reason"] = reason
    return _entry


def _is_exact_true_mv_comp(comp: AcceptedComp) -> bool:
    _lane_tier = str(getattr(comp, "comp_lane_tier", "") or "").strip().lower()
    _exactness = str(getattr(comp, "exactness_tier", "") or "").strip().lower()
    return bool(
        float(getattr(comp, "price", 0.0) or 0.0) > 0
        and bool(getattr(comp, "counts_toward_value", True))
        and _lane_tier in {"", "exact_lane"}
        and _exactness in _TRUE_MV_EXACT_TIERS
    )


def _true_mv_reject_reason(target_title: str, comp: AcceptedComp) -> str:
    _target_fp = _build_card_fingerprint({"title": target_title})
    _comp_fp = _build_card_fingerprint({"title": str(getattr(comp, "title", "") or "")})
    _target_serial = _normalize_fingerprint_serial_denominator(_target_fp.get("serial_denominator"))
    _comp_serial = _normalize_fingerprint_serial_denominator(_comp_fp.get("serial_denominator"))
    _target_parallel = str(_target_fp.get("parallel") or "").strip().lower()
    _comp_parallel = str(_comp_fp.get("parallel") or "").strip().lower()
    _lane_tier = str(getattr(comp, "comp_lane_tier", "") or "").strip().lower()
    _exactness = str(getattr(comp, "exactness_tier", "") or "").strip().lower()
    if _target_serial and _comp_serial != _target_serial:
        return "wrong_serial"
    if (
        _target_parallel
        and _target_parallel not in {"", "base", "raw"}
        and _comp_parallel
        and _comp_parallel not in {"", "base", "raw"}
        and _comp_parallel != _target_parallel
    ):
        return "wrong_parallel"
    if _lane_tier in _PREMIUM_SUPPORT_LANE_TIERS or _exactness in _PREMIUM_SUPPORT_LANE_TIERS:
        return "support_lane"
    if _lane_tier == "near_lane" or _exactness == "near_lane":
        return "near_family"
    if not bool(getattr(comp, "counts_toward_value", True)):
        return "not_value_eligible"
    if _exactness in {"weak_fallback_lane", "sale_type_fallback", "weaker_context_only"}:
        return "fallback_anchor"
    return "not_exact"


def _build_exact_true_mv_payload(
    target_title: str,
    accepted_comps: List[AcceptedComp],
) -> Dict[str, Any]:
    _used_comps = [c for c in accepted_comps if _is_exact_true_mv_comp(c)]
    _used_prices = [round(float(c.price), 2) for c in _used_comps if float(c.price) > 0]
    _used = [
        _accepted_comp_evidence_entry(c, match_type="exact")
        for c in _used_comps
    ]
    _rejected_reason_counts: Counter = Counter()
    _rejected: List[Dict[str, Any]] = []
    for _comp in accepted_comps:
        if _comp in _used_comps or float(getattr(_comp, "price", 0.0) or 0.0) <= 0:
            continue
        _reason = _true_mv_reject_reason(target_title, _comp)
        _rejected_reason_counts[_reason] += 1
        _rejected.append(
            _accepted_comp_evidence_entry(_comp, match_type="rejected", reason=_reason)
        )
    _exact_median_any = round(_simple_median(_used_prices), 2) if _used_prices else None
    return {
        "exact_comp_count": len(_used_comps),
        "exact_median": _exact_median_any,
        "exact_range_low": round(min(_used_prices), 2) if _used_prices else None,
        "exact_range_high": round(max(_used_prices), 2) if _used_prices else None,
        "used": _used,
        "rejected": _rejected[:48],
        "rejected_count": sum(int(v) for v in _rejected_reason_counts.values()),
        "rejected_reason_counts": {str(k): int(v) for k, v in _rejected_reason_counts.items()},
    }


def _fallback_trimmed_weighted_median(
    prices_weights: List[Tuple[float, float]],
) -> Tuple[Optional[float], List[float], List[float]]:
    """Downweight far-from-median comps, then trimmed weighted median."""
    raw_prices = [p for p, _ in prices_weights]
    med = sorted(raw_prices)[len(raw_prices) // 2]
    filtered: List[Tuple[float, float]] = []
    for p, w in prices_weights:
        if med > 0 and (p < med * 0.4 or p > med * 2.8):
            filtered.append((p, w * 0.15))
        else:
            filtered.append((p, w))
    vals = [x[0] for x in filtered]
    wts = [x[1] for x in filtered]
    point = _trimmed_weighted_median(vals, wts)
    return point, vals, wts


def resolve_mv_value_pools(accepted: List[AcceptedComp]) -> Tuple[List[AcceptedComp], List[AcceptedComp], int, int]:
    """
    Split accepted comps into strict value-eligible (counts_toward_value) vs broader accepted.
    Returns (strict_comps, all_accepted, strict_n, relaxed_n).
    """
    strict = [c for c in accepted if getattr(c, "counts_toward_value", True)]
    relaxed_n = max(0, len(accepted) - len(strict))
    return strict, accepted, len(strict), relaxed_n


def _fallback_trimmed_weighted_median_strict_first(
    accepted: List[AcceptedComp],
) -> Tuple[Optional[float], List[float], List[float], bool, str]:
    """
    Prefer counts_toward_value comps for fallback median; only then widen to all accepted.
    Returns (point, vals, wts, used_relaxed_beyond_strict, reason_if_relaxed).
    """
    strict = [c for c in accepted if getattr(c, "counts_toward_value", True)]
    pw_s = [(c.price, c.weight) for c in strict]
    if pw_s:
        pt, vals, wts = _fallback_trimmed_weighted_median(pw_s)
        if pt is not None and pt > 0:
            return pt, vals, wts, False, ""
    if not strict and accepted:
        pt, vals, wts = _fallback_trimmed_weighted_median([(c.price, c.weight) for c in accepted])
        return pt, vals, wts, True, "no_strict_comps"
    if strict and len(strict) < len(accepted):
        pt, vals, wts = _fallback_trimmed_weighted_median([(c.price, c.weight) for c in accepted])
        return pt, vals, wts, True, "strict_pool_insufficient"
    pt, vals, wts = _fallback_trimmed_weighted_median([(c.price, c.weight) for c in accepted])
    return pt, vals, wts, False, ""


def _serial_bucket_display(bucket: str) -> str:
    return {
        "serial_5_10": "/5-/10",
        "serial_15_25": "/15-/25",
        "serial_35_50": "/35-/50",
        "serial_75_99": "/75-/99",
        "serial_149_199": "/149-/199",
    }.get(str(bucket or "").strip().lower(), str(bucket or "").strip())


def _premium_scarcity_bucket_publish_plan(
    *,
    target_title: str,
    item_id: str,
    accepted_comps: List[AcceptedComp],
    today: date,
) -> Optional[Dict[str, Any]]:
    if not accepted_comps:
        return None
    target_bucket = _serial_support_bucket(_extract_serial_denominator(target_title))
    if not target_bucket:
        return None

    exact_tiers = {"exact_strict", "exact_synonym_normalized", "exact_grade_fallback"}
    exact_or_near = []
    for c in accepted_comps:
        _lane_tier = str(getattr(c, "comp_lane_tier", "") or "")
        _exact_tier = str(getattr(c, "exactness_tier", "") or "")
        if _lane_tier in {"exact_lane", "near_lane"}:
            exact_or_near.append(c)
            continue
        if _lane_tier in {"", "exact_lane"} and _exact_tier in exact_tiers:
            exact_or_near.append(c)
    support = [
        c
        for c in accepted_comps
        if str(getattr(c, "comp_lane_tier", "") or "") == "scarcity_bucket_support"
        and _serial_support_bucket(_extract_serial_denominator(getattr(c, "title", ""))) == target_bucket
    ]
    if len(exact_or_near) > 1 or not support:
        return None

    grade_downgraded = any(
        bool(getattr(c, "grade_fallback", False))
        or str(getattr(c, "gb_reason", "") or "") in {"adjacent_grade", "cross_grade", "graded_other", "grade_bridge_raw"}
        for c in support
    )
    support_prices = [(float(c.price), max(0.0, float(getattr(c, "weight", 0.0) or 0.0))) for c in support if float(c.price) > 0]
    if not support_prices:
        return None
    if len(support_prices) >= 2:
        point, _, _ = _fallback_trimmed_weighted_median(support_prices)
    else:
        point = round(float(support_prices[0][0]), 2)
    if point is None or point <= 0:
        return None

    support_n = len(support)
    exact_n = len(exact_or_near)
    qual_floor = min(float(getattr(c, "qual", 0.0) or 0.0) for c in support)
    confidence = "MEDIUM" if support_n >= 2 and exact_n >= 1 and not grade_downgraded and qual_floor >= 0.66 else "LOW"
    band_pct = 0.22 if support_n == 1 else 0.18
    if support_n >= 3:
        band_pct = 0.14
    if exact_n == 0:
        band_pct += 0.02
    if grade_downgraded:
        band_pct += 0.04
        confidence = "LOW"

    value = round(float(point), 2)
    value_low = round(value * (1.0 - band_pct), 2)
    value_high = round(value * (1.0 + band_pct), 2)
    recent_count = sum(1 for c in support if str(getattr(c, "recency_bucket", "") or "") in {"7d", "30d", "active_proxy"})
    last_comp_date = max(
        (
            c.sale_date.isoformat()
            for c in support
            if getattr(c, "sale_date", None)
        ),
        default=today.isoformat(),
    )
    bucket_label = _serial_bucket_display(target_bucket)
    print(
        f"[SCARCITY_BUCKET_SUPPORT] item={item_id[:24] or '?'} bucket={bucket_label} "
        f"exact={int(exact_n)} support={int(support_n)} conf={confidence}"
    )
    return {
        "value": value,
        "value_low": value_low,
        "value_high": value_high,
        "confidence": confidence.lower(),
        "support_count": support_n,
        "exact_count": exact_n,
        "bucket": target_bucket,
        "bucket_label": bucket_label,
        "recent_count": recent_count,
        "last_comp_date": last_comp_date,
        "market_lane_strength": round(sum(float(getattr(c, "qual", 0.0) or 0.0) for c in support) / max(support_n, 1), 3),
        "grade_downgraded": grade_downgraded,
    }


def _grade_bucket_match(
    listing_title: str,
    comp_title: str,
    *,
    allow_psa_adjacent: bool = False,
) -> Tuple[bool, str]:
    """
    Returns (compatible, reason).
    Never mix raw listing with graded comps or vice versa.
    When allow_psa_adjacent, PSA slabs one numeric step apart map to adjacent_grade.
    """
    listing_raw = _is_raw_listing(listing_title)
    comp_graded = _comp_is_graded(comp_title)
    if listing_raw and comp_graded:
        return False, "raw_vs_graded"
    if not listing_raw and not comp_graded:
        return False, "graded_vs_raw_comp"
    if not listing_raw and comp_graded:
        tgk = grade_bucket_key(listing_title)
        cgk = grade_bucket_key(comp_title)
        if tgk.startswith("psa") and cgk.startswith("psa"):
            if tgk == cgk:
                return True, "exact_grade"
            if allow_psa_adjacent and _psa_one_step_adjacent(tgk, cgk):
                return True, "adjacent_grade"
            return False, "psa_grade_mismatch"
        lg = _extract_psa_grade(listing_title)
        cg = _extract_psa_grade(comp_title)
        if lg is not None and cg is not None and lg == cg:
            return True, "exact_grade"
        if lg is not None and cg is not None:
            return True, "cross_grade"
        return True, "graded_other"
    return True, "raw_both"


MIN_COMP_QUALITY_SCORE = 0.58
MIN_COMP_QUALITY_ADJACENT_PASS = 0.60
MIN_EXACT_GRADE_FOR_LADDER = 4
# Per user (May 2026): "if the machine even finds one exact comp, that means
# that that is the mv." Lowered from 2 → 1 so a single exact-grade comp commits
# to a real MV instead of falling back to estimate_only. Multiple comps still
# average / cluster downstream — only the floor for "do we have enough" changed.
MIN_ACCEPTED_COMPS = 1


@dataclass
class HybridValuation:
    value: Optional[float] = None
    true_market_value: Optional[float] = None
    review_estimate_value: Optional[float] = None
    value_low: Optional[float] = None
    value_high: Optional[float] = None
    tier: str = ""
    market_value_source: str = ""
    valuation_truth_tier: str = ""
    confidence: str = "estimate_only"
    comp_count: int = 0
    last_comp_date: str = ""
    notes: str = ""
    debug_search_query: str = ""
    debug_pool_kind: str = ""
    debug_fetched_count: int = 0
    debug_accepted_count: int = 0
    debug_rejections_top: str = ""
    debug_canonical_key: str = ""
    debug_profile_summary: str = ""
    debug_cache_hit: str = ""
    debug_comp_trace: str = ""
    debug_lane_detail: str = ""
    dominant_range_low: Optional[float] = None
    dominant_range_high: Optional[float] = None
    dominant_comp_count: int = 0
    cluster_method: str = ""
    cluster_strength: float = 0.0
    valuation_basis: str = ""
    accepted_comp_count: int = 0
    full_comp_price_low: Optional[float] = None
    full_comp_price_high: Optional[float] = None
    market_lane_low: Optional[float] = None
    market_lane_high: Optional[float] = None
    market_lane_comp_count: int = 0
    market_lane_recent_count: int = 0
    market_lane_method: str = ""
    market_lane_strength: float = 0.0
    recent_comp_count_7d: int = 0
    recent_comp_count_30d: int = 0
    valuation_sale_mode: str = ""
    auction_comp_count: int = 0
    fixed_price_comp_count: int = 0
    exact_grade_comp_count: int = 0
    fallback_grade_comp_count: int = 0
    grade_fallback_used: bool = False
    debug_confidence_rationale: str = ""
    debug_audit_summary: str = ""
    valuation_strength: str = ""
    valuation_downgrade_reasons: str = ""
    duplicate_suppressed_count: int = 0
    condition_issue_accepted_count: int = 0
    condition_issue_lane_count: int = 0
    exactness_tier_counts: str = ""
    debug_visual_verification_summary: str = ""
    debug_audit_panel: str = ""
    debug_comp_detail_only: str = ""
    debug_accepted_comps_json: str = ""
    manual_review_audit: str = ""
    valuation_flow_label: str = ""
    valuation_failure_reason: str = ""
    valuation_final_status: str = ""
    comp_search_attempted: bool = False
    debug_comp_passes_json: str = ""
    debug_valuation_pipeline_json: str = ""
    comps_pre_enrich_count: int = 0
    comps_lane_selected_count: int = 0
    mv_pool_mode: str = ""
    mv_strict_comp_count: int = 0
    mv_relaxed_comp_count: int = 0
    mv_strict_lane_comp_count: int = 0
    mv_relaxed_fallback_used: bool = False
    mv_fallback_reason: str = ""
    comp_lane_label: str = ""
    comp_lane_status: str = ""
    comp_lane_warning: str = ""
    comp_lane_signature: str = ""
    recovery_mode: str = ""
    recovery_note: str = ""
    operator_plan_query: str = ""
    operator_plan_fingerprint: str = ""
    operator_exact_kept: int = 0
    operator_near_kept: int = 0
    operator_rejected: int = 0
    operator_accept_profile: str = ""
    exact_comp_count: int = 0
    valuation_contract_version: str = TRUE_MV_CONTRACT_VERSION
    valuation_source_module: str = VALUATION_SOURCE_MODULE
    valuation_publish_stage: str = VALUATION_PUBLISH_STAGE
    valuation_apply_guard: str = VALUATION_APPLY_GUARD
    single_comp_clone_block: bool = False
    comp_evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, str]:
        """CSV-friendly string fields."""
        _true_mv = self.true_market_value if self.true_market_value and self.true_market_value > 0 else None
        out = {
            "market_value": f"{_true_mv:.2f}" if _true_mv is not None else "",
            "true_market_value": f"{self.true_market_value:.2f}" if self.true_market_value and self.true_market_value > 0 else "",
            "review_estimate_value": f"{self.review_estimate_value:.2f}" if self.review_estimate_value and self.review_estimate_value > 0 else "",
            "mv_mid": f"{_true_mv:.2f}" if _true_mv is not None else "",
            "market_value_source": self.market_value_source,
            "mv_source": self.market_value_source,
            "valuation_source_clean": self.market_value_source,
            "valuation_truth_tier": self.valuation_truth_tier,
            "exact_comp_count": str(int(self.exact_comp_count or 0)),
            "_valuation_contract_version": str(self.valuation_contract_version or TRUE_MV_CONTRACT_VERSION),
            "_valuation_source_module": str(self.valuation_source_module or VALUATION_SOURCE_MODULE),
            "_valuation_publish_stage": str(self.valuation_publish_stage or VALUATION_PUBLISH_STAGE),
            "_valuation_apply_guard": str(self.valuation_apply_guard or VALUATION_APPLY_GUARD),
            "single_comp_clone_block": "1" if self.single_comp_clone_block else "",
            "market_value_confidence": self.confidence,
            "mv_confidence_adjusted": self.confidence,
            "comp_count": str(self.comp_count),
            "last_comp_date": self.last_comp_date,
            "valuation_notes": (self.notes or "")[:2000],
            "value_range_low": f"{self.value_low:.2f}" if self.value_low is not None else "",
            "value_range_high": f"{self.value_high:.2f}" if self.value_high is not None else "",
            "mv_low": f"{self.value_low:.2f}" if self.value_low is not None else "",
            "mv_high": f"{self.value_high:.2f}" if self.value_high is not None else "",
            "comp_evidence_json": json.dumps(self.comp_evidence or {"used": [], "rejected": []}, ensure_ascii=False)[:12000],
        }
        if self.dominant_range_low is not None and self.dominant_range_high is not None:
            out["dominant_range_low"] = f"{self.dominant_range_low:.2f}"
            out["dominant_range_high"] = f"{self.dominant_range_high:.2f}"
            out["dominant_comp_count"] = str(self.dominant_comp_count)
            out["cluster_method"] = self.cluster_method
            out["cluster_strength"] = f"{self.cluster_strength:.3f}"
            out["valuation_basis"] = self.valuation_basis
        if self.market_lane_low is not None and self.market_lane_high is not None:
            out["market_lane_low"] = f"{self.market_lane_low:.2f}"
            out["market_lane_high"] = f"{self.market_lane_high:.2f}"
            out["market_lane_comp_count"] = str(self.market_lane_comp_count)
            out["market_lane_recent_count"] = str(self.market_lane_recent_count)
            out["market_lane_method"] = self.market_lane_method
            out["mv_method"] = self.market_lane_method
            out["market_lane_strength"] = f"{self.market_lane_strength:.3f}"
            out["recent_comp_count_7d"] = str(self.recent_comp_count_7d)
            out["recent_comp_count_30d"] = str(self.recent_comp_count_30d)
        if self.valuation_sale_mode:
            out["valuation_sale_mode"] = self.valuation_sale_mode
            out["auction_comp_count"] = str(self.auction_comp_count)
            out["fixed_price_comp_count"] = str(self.fixed_price_comp_count)
            out["exact_grade_comp_count"] = str(self.exact_grade_comp_count)
            out["fallback_grade_comp_count"] = str(self.fallback_grade_comp_count)
            out["grade_fallback_used"] = "1" if self.grade_fallback_used else "0"
        if self.valuation_strength:
            out["valuation_strength"] = self.valuation_strength
            out["valuation_downgrade_reasons"] = (self.valuation_downgrade_reasons or "")[:500]
        if self.mv_pool_mode:
            out["mv_pool_mode"] = self.mv_pool_mode
            out["mv_strict_comp_count"] = str(self.mv_strict_comp_count)
            out["mv_relaxed_comp_count"] = str(self.mv_relaxed_comp_count)
            out["mv_strict_lane_comp_count"] = str(self.mv_strict_lane_comp_count)
            out["mv_relaxed_fallback_used"] = "1" if self.mv_relaxed_fallback_used else "0"
            out["mv_fallback_reason"] = (self.mv_fallback_reason or "")[:300]
        if self.comp_lane_status or self.comp_lane_signature:
            out["comp_lane_label"] = (self.comp_lane_label or "")[:160]
            out["comp_lane_status"] = (self.comp_lane_status or "")[:64]
            out["comp_lane_warning"] = (self.comp_lane_warning or "")[:200]
            out["comp_lane_signature"] = (self.comp_lane_signature or "")[:200]
        if self.recovery_mode or self.recovery_note:
            out["recovery_mode"] = (self.recovery_mode or "")[:80]
            out["recovery_note"] = (self.recovery_note or "")[:200]
        return out


def _true_mv_contract_reasons(
    *,
    source: str,
    exact_comp_count: int,
    true_mv: Optional[float],
) -> List[str]:
    _reasons: List[str] = []
    _source = str(source or "").strip().lower()
    _exact = int(exact_comp_count or 0)
    _true_mv = _safe_float(true_mv)
    if _source == "support_comp_engine":
        if not _true_mv or _true_mv <= 0:
            _reasons.append("true_mv_missing")
        return _reasons
    if _source != "exact_comp_engine":
        _reasons.append("source_not_exact_comp_engine")
    # Per user (May 2026): single exact comp = real MV. Was `< 2`.
    if _exact < 1:
        _reasons.append("exact_comp_count_lt_1")
    if not _true_mv or _true_mv <= 0:
        _reasons.append("true_mv_missing")
    return _reasons


def _enforce_true_mv_contract(
    *,
    title: str,
    stage: str,
    truth: str,
    source: str,
    exact_comp_count: int,
    true_mv: Optional[float],
    review_estimate: Optional[float],
    published_value: Optional[float],
) -> Dict[str, Any]:
    _title = str(title or "").strip()
    _stage = str(stage or "").strip().lower() or "unknown"
    _truth = str(truth or "").strip().upper() or "NONE"
    _source = str(source or "").strip()
    _exact = int(exact_comp_count or 0)
    _true_mv = _safe_float(true_mv)
    _review = _safe_float(review_estimate)
    _published = _safe_float(published_value)
    _result = {
        "truth": _truth,
        "source": _source,
        "exact_comp_count": _exact,
        "true_mv": round(float(_true_mv), 2) if _true_mv and _true_mv > 0 else None,
        "review_estimate": round(float(_review), 2) if _review and _review > 0 else None,
        "blocked": False,
        "reasons": [],
    }
    if _truth != "TRUE":
        return _result
    _reasons = _true_mv_contract_reasons(
        source=_source,
        exact_comp_count=_exact,
        true_mv=_true_mv,
    )
    if not _reasons:
        print(
            f"[MV_TRUE_CONTRACT_PASS] stage={_stage} title={_title[:140]} "
            f"source={_source or 'none'} exact_comp_count={_exact} true_mv={_result['true_mv']}"
        )
        return _result
    for _reason in _reasons:
        print(
            f"[MV_TRUE_CONTRACT_REASON] stage={_stage} title={_title[:140]} "
            f"source={_source or 'none'} exact_comp_count={_exact} reason={_reason}"
        )
    _review_out = _review if _review and _review > 0 else (_published if _published and _published > 0 else None)
    print(
        f"[MV_TRUE_CONTRACT_BLOCK] stage={_stage} title={_title[:140]} "
        f"source={_source or 'none'} exact_comp_count={_exact} "
        f"true_mv={_result['true_mv']} review_estimate={round(float(_review_out), 2) if _review_out else None} "
        f"final_truth=REVIEW"
    )
    _result["truth"] = "REVIEW"
    _result["true_mv"] = None
    _result["review_estimate"] = round(float(_review_out), 2) if _review_out and _review_out > 0 else None
    _result["blocked"] = True
    _result["reasons"] = list(_reasons)
    return _result


def card_ladder_valuation_only(item_id: str, title: str) -> Optional[HybridValuation]:
    """
    Card Ladder JSON lookup only (local file). No live eBay comp network.
    Used by Buying Radar fast/triage tier.
    """
    return _card_ladder_lookup((item_id or "").strip(), (title or "").strip())


def _card_ladder_lookup(item_id: str, title: str) -> Optional[HybridValuation]:
    db = _load_card_ladder_db()
    by_id = db.get("by_item_id") or {}
    if item_id and item_id in by_id:
        entry = by_id[item_id]
        v = _safe_float(entry.get("value"))
        if v and v > 0:
            low = _safe_float(entry.get("low"))
            high = _safe_float(entry.get("high"))
            return HybridValuation(
                value=v,
                value_low=low,
                value_high=high,
                tier="card_ladder_exact",
                market_value_source="card_ladder",
                confidence=str(entry.get("confidence") or "high"),
                comp_count=int(entry.get("comp_count") or 0),
                last_comp_date=str(entry.get("last_comp_date") or "")[:32],
                notes=str(entry.get("notes") or "Card Ladder lookup (trusted external)."),
            )
    by_key = db.get("by_title_key") or {}
    tk = _title_key(title)
    if tk and tk in by_key:
        entry = by_key[tk]
        v = _safe_float(entry.get("value"))
        if v and v > 0:
            low = _safe_float(entry.get("low"))
            high = _safe_float(entry.get("high"))
            return HybridValuation(
                value=v,
                value_low=low,
                value_high=high,
                tier="card_ladder_exact",
                market_value_source="card_ladder",
                confidence=str(entry.get("confidence") or "medium"),
                comp_count=int(entry.get("comp_count") or 0),
                last_comp_date=str(entry.get("last_comp_date") or "")[:32],
                notes=str(entry.get("notes") or "Card Ladder title-key match."),
            )
    return None


def _format_rejection_summary(counter: Counter, limit: int = 8) -> str:
    if not counter:
        return ""
    parts = [f"{k}: {v}" for k, v in counter.most_common(limit)]
    return "; ".join(parts)


def _merge_comp_search_passes(
    pass_specs: List[Tuple[str, str]],
    *,
    search_fn: Optional[Callable[[str, int], List[Dict[str, Any]]]],
    limit_per_pass: int,
) -> Tuple[List[Dict[str, Any]], str, List[Dict[str, Any]], int, Optional[str]]:
    """
    Run ordered comp queries; merge unique listings; tag each row with _valuation_pool_kind.

    Returns (merged_items, effective_pool_kind, pass_logs, total_raw_fetched, first_error_message).
    """
    merged: List[Dict[str, Any]] = []
    dedupe_seen: Set[Tuple[str, str]] = set()
    logs: List[Dict[str, Any]] = []
    total_fetched = 0
    any_sold = False
    first_err: Optional[str] = None
    last_pool = "active_browse"

    for label, q in pass_specs:
        q = (q or "").strip()
        if not q:
            continue
        try:
            if search_fn is not None:
                batch = list(search_fn(q, limit_per_pass) or []) if callable(search_fn) else []
                pk = "custom_auction"
            else:
                batch, pk = ebay_search.search_comp_pool(q, limit=limit_per_pass)
        except Exception as e:
            msg = str(e)[:500]
            if first_err is None:
                first_err = msg
            logs.append(
                {
                    "pass": label,
                    "query": q[:220],
                    "fetched": 0,
                    "added_unique": 0,
                    "pool": "",
                    "error": msg,
                }
            )
            continue

        nf = len(batch or [])
        total_fetched += nf
        last_pool = pk
        added_u = 0
        for raw in batch or []:
            it = dict(raw)
            it["_valuation_pool_kind"] = pk
            it["_valuation_query_pass"] = label
            iid = str(it.get("itemId") or "").strip()
            tit = (it.get("title") or "").strip()
            dk: Tuple[str, str] = ("id", iid) if iid else ("t", tit[:220].lower())
            if dk in dedupe_seen:
                continue
            dedupe_seen.add(dk)
            merged.append(it)
            added_u += 1
        if pk == "sold_finding":
            any_sold = True
        logs.append(
            {
                "pass": label,
                "query": q[:220],
                "fetched": nf,
                "added_unique": added_u,
                "pool": pk,
            }
        )
        # Merge cap 52 → 80 (was 120, dialed back for scan perf). Still gives
        # enough comp pool depth to find multi-comp matches without blowing
        # out scan time. Downstream IQR trim handles outliers.
        if len(merged) >= 80:
            break
        # Per user (May 2026): if eBay just rate-limited us, abort the remaining
        # query passes for this card. The worker fires 7-8 variants per card;
        # without this, one 429 means all 7 more variants will also 429 — burning
        # ~8× the API budget for a card that's already blocked. ebay_search sets
        # this module-level flag inside search_market_comps_browse on HTTP 429.
        if getattr(ebay_search, "_last_was_rate_limited", False):
            if first_err is None:
                first_err = "rate_limit_abort_remaining_passes"
            break

    eff = "sold_finding" if any_sold else last_pool
    return merged, eff, logs, total_fetched, first_err


def run_hybrid_valuation(
    listing_title: str,
    item_id: str = "",
    item_url: str = "",
    search_query: Optional[str] = None,
    search_fn: Optional[Callable[[str, int], List[Dict[str, Any]]]] = None,
    *,
    target_listing_item: Optional[Dict[str, Any]] = None,
    audit_canonical_key: str = "",
    audit_profile_summary: str = "",
    manual_review_canonical_key: str = "",
    radar_fast_mode: bool = False,
    radar_trace: bool = False,
) -> HybridValuation:
    """
    Run full hybrid stack. Does not mutate watchlist rows.

    listing_title: full card title (used for profile parsing and grade/raw filters).
    search_query: optional query string; otherwise build_precise_sold_query(listing).
    """
    title = (listing_title or "").strip()
    iid = (item_id or "").strip()

    notes_parts: List[str] = []
    profile = parse_listing_profile(title)
    target_row_for_class = dict(target_listing_item or {})
    if "title" not in target_row_for_class:
        target_row_for_class["title"] = title
    premium_class_meta = _detect_premium_card_class(target_row_for_class)
    print(
        f"[CARD_CLASS] item={iid[:24] or '?'} class={str(premium_class_meta.get('card_class') or 'base')} "
        f"subset={str(premium_class_meta.get('subset_family') or '')[:28]} "
        f"auto={1 if bool(premium_class_meta.get('auto_flag')) else 0} "
        f"patch={1 if bool(premium_class_meta.get('patch_flag')) else 0} "
        f"mem={1 if bool(premium_class_meta.get('memorabilia_flag')) else 0}"
    )
    excluded_listing, listing_type, exclusion_reason = should_exclude_from_single_card_valuation(title)
    if excluded_listing:
        return HybridValuation(
            notes=(
                f"Excluded from single-card valuation ({listing_type}): "
                f"{exclusion_reason.replace('_', ' ')}."
            ),
            confidence="excluded",
            market_value_source="listing_type_excluded",
            valuation_basis="listing_type_excluded",
            valuation_flow_label="listing_type_filter",
            valuation_failure_reason=exclusion_reason,
            valuation_final_status="excluded_listing_type",
            comp_search_attempted=False,
            debug_pool_kind="listing_type_filter",
            debug_profile_summary=format_profile_for_debug(profile),
            debug_comp_passes_json="[]",
            debug_valuation_pipeline_json=json.dumps(
                {
                    "final_status": "excluded_listing_type",
                    "reason": exclusion_reason,
                    "listing_type": classify_listing_type(title),
                },
                ensure_ascii=False,
            ),
        )
    target_variant = classify_card_variant(title)
    ctx_psa = _extract_psa_grade(title)

    man_key = (manual_review_canonical_key or audit_canonical_key or "").strip()
    man_state = manual_comp_review.load_manual_state()
    decisions = (
        manual_comp_review.get_comp_decisions_map(man_state, man_key) if man_key else {}
    )
    manual_reject_hits = 0

    # 1) Card Ladder
    cl = _card_ladder_lookup(iid, title)
    if cl is not None:
        return cl

    if radar_fast_mode:
        print(f"[RADAR][MV] fast_mode_skip_live_comps=True title={(title or '')[:80]!r}")
        return HybridValuation(
            notes="Radar fast mode: live comp fetch skipped (Card Ladder only when hit above).",
            confidence="estimate_only",
            market_value_source="none",
            valuation_failure_reason="radar_fast_mode",
            valuation_final_status="no_estimate",
            comp_search_attempted=False,
            debug_comp_passes_json="[]",
            debug_valuation_pipeline_json=json.dumps(
                {"final_status": "no_estimate", "reason": "radar_fast_mode"}, ensure_ascii=False
            ),
        )

    explicit_q = (search_query or "").strip()
    pass_rows: List[Tuple[str, str]] = []
    if explicit_q:
        pass_rows.append(("pass0_explicit_search_query", explicit_q))
    pass_rows.extend(
        build_comp_retrieval_query_passes(
            profile,
            fallback_title=title,
            source_row=target_row_for_class,
        )
    )
    if not pass_rows:
        fallback_single = (
            build_precise_sold_query({"title": title, "card_name": title})
            or title
            or iid
            or (item_url or "").strip()
        ).strip()
        if fallback_single:
            pass_rows.append(("pass_fallback_title_or_id", fallback_single))

    seen_q: Set[str] = set()
    uniq_specs: List[Tuple[str, str]] = []
    for lab, q in pass_rows:
        qn = (q or "").strip()
        if not qn:
            continue
        k = qn.lower()
        if k in seen_q:
            continue
        seen_q.add(k)
        uniq_specs.append((lab, qn))
    # QUOTA-FIX 2026-05-12: cap to first 3 query passes. Previously we fired up
    # to 8 variants per card which burned the 5,000 daily Browse-API budget on
    # ~625 cards. With 3 passes we triple the daily card throughput (the first
    # pass — strict — gets the goods for ~80% of cards anyway; passes 4–8 were
    # mostly redundant relaxations that the comp_relaxer module handles better
    # on a per-card basis as a deliberate fallback rather than a brute-force
    # blast). Restore by removing this slice if quota stops being the binding
    # constraint (e.g. after the eBay Growth Check approves us for 20k/day).
    if len(uniq_specs) > 3:
        uniq_specs = uniq_specs[:3]
    for _lab, _query in uniq_specs:
        print(f"[CLASS_QUERY] item={iid[:24] or '?'} query={str(_query)[:160]}")

    if not uniq_specs:
        return HybridValuation(
            notes="No title or id for valuation.",
            confidence="estimate_only",
            market_value_source="none",
            debug_search_query="",
            valuation_failure_reason="no_query",
            valuation_final_status="no_estimate",
            comp_search_attempted=False,
            debug_comp_passes_json="[]",
            debug_valuation_pipeline_json=json.dumps(
                {"final_status": "no_estimate", "reason": "no_query"}, ensure_ascii=False
            ),
        )

    primary_query = uniq_specs[0][1]
    print(f"[COMP_TRACE][QUERY] item={iid[:24]} passes={len(uniq_specs)} query='{primary_query[:120]}'")
    if radar_trace:
        print("[RADAR][MV] step=comp_search:start (internal)")
    # Bumped 52 → 75 (eBay max 200). 100 was killing scan time because the
    # comp engine runs this once per valuation row × multiple passes. 75 is
    # ~45% wider net than baseline while keeping the per-pass cost bounded.
    items, pool_kind, pass_logs, total_raw_fetched, fetch_first_err = _merge_comp_search_passes(
        uniq_specs,
        search_fn=search_fn,
        limit_per_pass=75,
    )
    if radar_trace:
        print(
            f"[RADAR][MV] step=comp_search:done (internal) fetched={len(items or [])} "
            f"pool={pool_kind!r}"
        )
    query = primary_query
    comp_search_attempted = True
    passes_json = json.dumps(pass_logs, ensure_ascii=False)[:12000]

    if fetch_first_err and not items:
        return HybridValuation(
            notes=f"Comp search failed (all passes): {fetch_first_err}",
            confidence="estimate_only",
            market_value_source="error",
            debug_search_query=query,
            debug_pool_kind="error",
            valuation_failure_reason="retrieval_error",
            valuation_final_status="no_estimate",
            comp_search_attempted=True,
            debug_fetched_count=0,
            debug_comp_passes_json=passes_json,
            debug_valuation_pipeline_json=json.dumps(
                {
                    "final_status": "no_estimate",
                    "reason": "retrieval_error",
                    "passes": pass_logs,
                    "error": fetch_first_err[:400],
                },
                ensure_ascii=False,
            )[:8000],
        )

    fetched = len(items or [])
    print(f"[COMP_TRACE][FETCH] item={iid[:24]} raw_rows={total_raw_fetched} unique_merged={fetched} pool={pool_kind}")
    print(f"[RAW_COMP_PAYLOAD] title={title[:140]} count={len(list(items or []))}")
    for c in list(items or [])[:3]:
        print(f"[RAW_COMP_SAMPLE] {str((c or {}).get('title') or '')[:140]} | price={(c or {}).get('price')}")
    pool_kinds_in_items = {it.get("_valuation_pool_kind") for it in items if it.get("_valuation_pool_kind")}
    debug_pool_kind = "mixed" if len(pool_kinds_in_items) > 1 else pool_kind
    rej: Counter = Counter()
    accepted_buffer: List[
        Tuple[Dict[str, Any], str, float, float, float, str, str, bool, str, str, str]
    ] = []
    cross_grade_used = False
    trace_lines: List[str] = []
    _MAX_COMP_TRACE = 48
    today = date.today()
    tgt_gk = grade_bucket_key(title)
    seen_sigs: Set[Tuple[str, str]] = set()
    operator_plan = _build_operator_comp_plan(
        dict(target_listing_item or {"title": title, "player_name": getattr(profile, "player_guess", "")})
    )
    subject_fingerprint = dict(operator_plan)
    print(
        f"[OPERATOR_PLAN] item={str(iid or '')[:24]} "
        f"query_primary=\"{str(operator_plan.get('query_primary') or '')[:140]}\""
    )
    _normalized_query = str(operator_plan.get("query_primary") or "").strip()
    _serial_den_log = str(operator_plan.get("serial_denominator") or "none")
    print(f"[MV][HYBRID_OK] item={iid[:24]} normalized_query='{_normalized_query[:120]}' serial_denominator={_serial_den_log}")
    fingerprint_reject_counts: Counter = Counter()
    fingerprint_exact_kept = 0
    fingerprint_near_kept = 0
    fingerprint_generic_rejected = 0
    fingerprint_match_logs = 0
    recovery_diag: Dict[str, Any] = {
        "sold_candidates_fetched": int(total_raw_fetched or 0),
        "sold_candidates_after_norm": int(fetched or 0),
        "strict_lane_accept_count": 0,
        "near_lane_accept_count": 0,
        "support_lane_accept_count": 0,
        "grade_bridge_accept_count": 0,
        "rejection_reason_counts": {},
        "recovery_mode": "",
        "recovery_note": "",
    }
    if radar_trace:
        print("[RADAR][MV] step=comp_filter:start (internal)")

    def _comp_trace_row(status: str, comp_title: str, reason: str) -> str:
        c_cls = classify_card_variant(comp_title)
        dbg = format_variant_class_debug(c_cls)
        ts = (comp_title or "").replace("\n", " ").strip()
        if len(ts) > 120:
            ts = ts[:117] + "..."
        return f"{status} | {dbg} | {reason} | {ts}"

    def _accept_candidate_items(
        candidate_items: List[Dict[str, Any]],
        *,
        allow_psa_adjacent: bool,
        min_quality: float,
        stage_tag: str,
        bridge_mode: str = "none",
    ) -> None:
        nonlocal manual_reject_hits, cross_grade_used
        nonlocal fingerprint_exact_kept, fingerprint_near_kept, fingerprint_generic_rejected, fingerprint_match_logs
        for raw_item in candidate_items or []:
            ct = (raw_item.get("title") or "").strip()
            if not ct:
                continue
            sig = (str(raw_item.get("itemId") or ""), ct)
            if sig in seen_sigs:
                continue
            ipk0 = raw_item.get("_valuation_pool_kind") or pool_kind
            same, same_r = comp_listing_validation.is_same_listing_as_target(
                iid, item_url, target_listing_item, raw_item
            )
            if same:
                rej[same_r or "same_as_target_listing"] += 1
                if len(trace_lines) < _MAX_COMP_TRACE:
                    trace_lines.append(_comp_trace_row("REJECT", ct, same_r or "same_as_target_listing"))
                continue

            ok_temp, temp_r, parsed_sale = comp_listing_validation.validate_comp_sale_temporal(
                ipk0, raw_item, today
            )
            if not ok_temp:
                rej[temp_r or "invalid_sale_temporal"] += 1
                if len(trace_lines) < _MAX_COMP_TRACE:
                    trace_lines.append(_comp_trace_row("REJECT", ct, temp_r or "invalid_sale_temporal"))
                continue

            it = dict(raw_item)
            it["_val_resolved_sale_date"] = parsed_sale if ipk0 == "sold_finding" else None
            it["_valuation_recovery_stage"] = stage_tag
            cid = manual_comp_review.comp_stable_id(it, ct)
            if decisions.get(cid) == "reject":
                manual_reject_hits += 1
                rej["manual_reject"] += 1
                if len(trace_lines) < _MAX_COMP_TRACE:
                    trace_lines.append(_comp_trace_row("REJECT", ct, "manual_reject"))
                continue

            gb_ok, gb_reason = _grade_bucket_match(title, ct, allow_psa_adjacent=allow_psa_adjacent)
            grade_bridge_used = False
            if not gb_ok:
                _grade_bridge_match = _fingerprint_match_result_for_titles(
                    title,
                    ct,
                    ignore_grade=True,
                )
                if (
                    bridge_mode in ("raw_or_adjacent", "raw_only")
                    and not _is_raw_listing(title)
                    and _is_raw_listing(ct)
                    and bool(_grade_bridge_match.get("matched"))
                    and str(_grade_bridge_match.get("match_level") or "") == "exact"
                ):
                    gb_ok = True
                    gb_reason = "grade_bridge_raw"
                    grade_bridge_used = True
                else:
                    rej[f"grade:{gb_reason}"] += 1
                    if len(trace_lines) < _MAX_COMP_TRACE:
                        trace_lines.append(_comp_trace_row("REJECT", ct, f"grade:{gb_reason}"))
                    if sum(rej.values()) <= 4:
                        print(f"[COMP_TRACE][DROP] item={iid[:24]} reason=grade:{gb_reason} title='{ct[:80]}'")
                    continue
            elif bridge_mode == "adjacent_grade_only" and gb_reason != "adjacent_grade":
                continue
            elif bridge_mode in ("raw_or_adjacent", "raw_only") and gb_reason not in ("adjacent_grade", "grade_bridge_raw"):
                continue

            bad, br = is_bad_comp_match(
                ct,
                profile,
                target_variant=target_variant,
                allow_psa_adjacent=(allow_psa_adjacent or gb_reason == "grade_bridge_raw"),
            )
            if bad:
                rej[br or "bad_match"] += 1
                if len(trace_lines) < _MAX_COMP_TRACE:
                    trace_lines.append(_comp_trace_row("REJECT", ct, br or "bad_match"))
                if sum(rej.values()) <= 6:
                    print(f"[COMP_TRACE][DROP] item={iid[:24]} reason={br or 'bad_match'} title='{ct[:80]}'")
                continue

            lane_gate = _apply_comp_lane_penalties(profile, ct)
            _class_ok, _class_reason = _premium_card_class_match(
                profile,
                ct,
                lane_name=str(lane_gate.get("lane") or ""),
            )
            print(
                f"[CLASS_MATCH] item={iid[:24] or '?'} comp_title={ct[:96]} "
                f"class_match={'pass' if _class_ok else 'reject'} reason={str(_class_reason or '')[:48]}"
            )
            if lane_gate.get("reject"):
                rej[str(lane_gate.get("reason") or "weak_card_identity_match")] += 1
                if len(trace_lines) < _MAX_COMP_TRACE:
                    trace_lines.append(
                        _comp_trace_row(
                            "REJECT",
                            ct,
                            str(lane_gate.get("reason") or "weak_card_identity_match"),
                        )
                    )
                continue
            if bridge_mode in ("raw_or_adjacent", "raw_only") and str(lane_gate.get("lane") or "") != "exact_lane":
                rej["grade_bridge_non_exact_lane"] += 1
                continue

            verified_comp = _verify_operator_comp(operator_plan, {"title": ct})
            comp_fingerprint = dict(verified_comp.get("comp_fingerprint") or {})
            if not verified_comp.get("matched"):
                _fp_reason = str((verified_comp.get("reject_reasons") or ["generic_product_only_reject"])[0] or "generic_product_only_reject")
                rej[_fp_reason] += 1
                fingerprint_reject_counts[_fp_reason] += 1
                if str(verified_comp.get("level") or "") == "generic":
                    fingerprint_generic_rejected += 1
                if len(trace_lines) < _MAX_COMP_TRACE:
                    trace_lines.append(_comp_trace_row("REJECT", ct, _fp_reason))
                if sum(fingerprint_reject_counts.values()) <= 4:
                    print(f"[COMP_TRACE][DROP] item={iid[:24]} reason={_fp_reason} title='{ct[:80]}'")
                continue
            if str(verified_comp.get("level") or "") == "exact":
                fingerprint_exact_kept += 1
            else:
                fingerprint_near_kept += 1
            if fingerprint_match_logs < 3:
                print(
                    f"[OPERATOR_VERIFY] item={str(iid or '')[:24]} "
                    f"comp_title=\"{ct[:84]}\" level={str(verified_comp.get('level') or '')}"
                )
                print(
                    f"[FINGERPRINT_MATCH] subject=\"{str(subject_fingerprint.get('fingerprint_key') or '')[:120]}\" "
                    f"comp=\"{str(comp_fingerprint.get('fingerprint_key') or '')[:120]}\" "
                    f"level={str(verified_comp.get('level') or '')} reasons=[]"
                )
                fingerprint_match_logs += 1

            qual = comp_match_quality(ct, profile)
            if decisions.get(cid) == "approve" and qual < min_quality:
                qual = max(float(qual), min_quality)
            if qual < min_quality:
                rej["below_quality_threshold"] += 1
                if len(trace_lines) < _MAX_COMP_TRACE:
                    trace_lines.append(_comp_trace_row("REJECT", ct, "below_quality_threshold"))
                continue

            price = _extract_price_from_item(it)
            if price is None or price <= 0:
                rej["no_price"] += 1
                if len(trace_lines) < _MAX_COMP_TRACE:
                    trace_lines.append(_comp_trace_row("REJECT", ct, "no_price"))
                continue

            if gb_reason == "grade_bridge_raw":
                price = _apply_grade_bridge_adjustment(
                    price,
                    target_grade_key=tgt_gk,
                    comp_grade_key="raw",
                )
            elif gb_reason == "adjacent_grade":
                price = _apply_grade_bridge_adjustment(
                    price,
                    target_grade_key=tgt_gk,
                    comp_grade_key=grade_bucket_key(ct),
                )
            if price <= 0:
                continue

            w = float(qual)
            if gb_reason == "cross_grade":
                w *= 0.35
                cross_grade_used = True
            elif gb_reason == "graded_other":
                w *= 0.5
            elif gb_reason == "adjacent_grade":
                w *= 0.24
            elif gb_reason == "grade_bridge_raw":
                w *= 0.22

            sale_type = infer_comp_sale_type(it, ipk0)
            if len(trace_lines) < _MAX_COMP_TRACE:
                trace_lines.append(
                    _comp_trace_row(
                        "ACCEPT",
                        ct,
                        f"{stage_tag} qual={qual:.2f} gb={gb_reason} sale={sale_type}",
                    )
                )
            if str(lane_gate.get("lane") or "") == "exact_lane":
                recovery_diag["strict_lane_accept_count"] += 1
            elif str(lane_gate.get("lane") or "") == "near_lane":
                recovery_diag["near_lane_accept_count"] += 1
            elif str(lane_gate.get("lane") or "") in _PREMIUM_SUPPORT_LANE_TIERS:
                recovery_diag["support_lane_accept_count"] += 1
                print(
                    f"[SUPPORT_ACCEPTED] title={title[:140]} "
                    f"comp={ct[:140]} "
                    f"price={round(float(price), 2)}"
                )
            if gb_reason in ("grade_bridge_raw", "adjacent_grade"):
                recovery_diag["grade_bridge_accept_count"] += 1

            accepted_buffer.append(
                (
                    it,
                    ct,
                    round(float(price), 2),
                    w,
                    float(qual),
                    gb_reason,
                    sale_type,
                    gb_reason in ("adjacent_grade", "grade_bridge_raw"),
                    str(lane_gate.get("lane") or ""),
                    str(lane_gate.get("reason") or ""),
                    str(lane_gate.get("comp_signature") or ""),
                )
            )
            seen_sigs.add(sig)

    _accept_candidate_items(
        items or [],
        allow_psa_adjacent=False,
        min_quality=MIN_COMP_QUALITY_SCORE,
        stage_tag="strict_pool",
    )

    if radar_trace:
        print(
            f"[RADAR][MV] step=comp_filter:done (internal) accepted_buffer={len(accepted_buffer)}"
        )

    exact_ct = sum(1 for x in accepted_buffer if x[5] == "exact_grade")
    if (
        tgt_gk.startswith("psa")
        and exact_ct < MIN_EXACT_GRADE_FOR_LADDER
        and len(accepted_buffer) < 28
    ):
        _accept_candidate_items(
            items or [],
            allow_psa_adjacent=True,
            min_quality=MIN_COMP_QUALITY_ADJACENT_PASS,
            stage_tag="adjacent_grade_pool",
            bridge_mode="adjacent_grade_only",
        )

    if len(accepted_buffer) < MIN_ACCEPTED_COMPS:
        _existing_queries = {q.lower() for _, q in uniq_specs}
        _recovery_specs = [
            (lab, q)
            for lab, q in build_sold_query_variants(profile, fallback_title=title, source_row=target_row_for_class)
            if (q or "").strip() and q.lower() not in _existing_queries
        ]
        for _lab, _query in _recovery_specs:
            print(f"[CLASS_QUERY] item={iid[:24] or '?'} query={str(_query)[:160]}")
        if _recovery_specs:
            rec_items, rec_pool_kind, rec_logs, rec_fetched, _rec_err = _merge_comp_search_passes(
                _recovery_specs,
                search_fn=search_fn,
                limit_per_pass=52,
            )
            total_raw_fetched += rec_fetched
            recovery_diag["sold_candidates_fetched"] = int(total_raw_fetched or 0)
            pass_logs.extend(rec_logs)
            recovery_diag["sold_candidates_after_norm"] = int(
                recovery_diag.get("sold_candidates_after_norm", 0)
            ) + len(rec_items or [])
            recovery_diag["recovery_mode"] = "sold_comp_recovery_cascade"
            if rec_items:
                recovery_diag["recovery_note"] = "Recovered additional candidates before fallback."
                _merge_by_sig: Dict[Tuple[str, str], Dict[str, Any]] = {
                    (str(it.get("itemId") or ""), str(it.get("title") or "").strip()): it
                    for it in (items or [])
                }
                for _rit in rec_items or []:
                    _rkey = (str(_rit.get("itemId") or ""), str(_rit.get("title") or "").strip())
                    if _rkey not in _merge_by_sig:
                        _merge_by_sig[_rkey] = _rit
                items = list(_merge_by_sig.values())
                fetched = len(items)
                if rec_pool_kind and rec_pool_kind != pool_kind:
                    debug_pool_kind = "mixed"
                _accept_candidate_items(
                    rec_items or [],
                    allow_psa_adjacent=False,
                    min_quality=MIN_COMP_QUALITY_SCORE,
                    stage_tag="recovery_pass_strict",
                )
                _accept_candidate_items(
                    rec_items or [],
                    allow_psa_adjacent=True,
                    min_quality=MIN_COMP_QUALITY_ADJACENT_PASS,
                    stage_tag="recovery_pass_grade_bridge",
                    bridge_mode="raw_or_adjacent",
                )
            elif _rec_err:
                recovery_diag["recovery_note"] = f"Recovery cascade fetch miss: {_rec_err[:120]}"

    cross_grade_used = any(x[5] == "cross_grade" for x in accepted_buffer)
    recovery_diag["rejection_reason_counts"] = {str(k): int(v) for k, v in rej.items()}
    print(
        f"[OPERATOR_SUMMARY] exact_kept={fingerprint_exact_kept} "
        f"near_kept={fingerprint_near_kept} rejected={sum(int(v) for v in fingerprint_reject_counts.values())}"
    )
    print(
        f"[FINGERPRINT_SUMMARY] exact_kept={fingerprint_exact_kept} "
        f"near_kept={fingerprint_near_kept} generic_rejected={fingerprint_generic_rejected}"
    )
    if fingerprint_reject_counts:
        print(
            "[OPERATOR_REJECT] "
            + " ".join(
                f"{str(_k)}={int(_v)}" for _k, _v in fingerprint_reject_counts.items() if int(_v) > 0
            )
        )
        print(
            "[FINGERPRINT_REJECT] "
            + " ".join(
                f"{str(_k)}={int(_v)}" for _k, _v in fingerprint_reject_counts.items() if int(_v) > 0
            )
        )
    passes_json = json.dumps(pass_logs, ensure_ascii=False)[:12000]

    comp_trace = "\n".join(trace_lines)[:8000]

    reject_summary = _format_rejection_summary(rej)
    sold_recent_30 = 0
    for it, _ct, _p, _w, _q, _g, _st, _gf, _lt, _lr, _ls in accepted_buffer:
        ipk_s = it.get("_valuation_pool_kind") or pool_kind
        if ipk_s != "sold_finding":
            continue
        sd = it.get("_val_resolved_sale_date")
        if not isinstance(sd, date):
            sd = _sale_date_from_item(it)
        if sd is not None and (today - sd).days <= RECENCY_DAYS_30:
            sold_recent_30 += 1

    # ── Contamination filter — drop any comp that mirrors the source listing
    #    or is an active/unsold listing. Runs BEFORE accepted_comps construction
    #    so contaminated rows never reach trusted_exact / support / true_mv /
    #    target_bid / valuation authority. Pure filter — no comp matching,
    #    pricing, or identity logic is changed.
    def _vc_normalize_url(_u: str) -> str:
        _s = str(_u or "").strip().lower()
        if not _s:
            return ""
        return _s.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    def _vc_title_fingerprint(_t: str) -> str:
        _s = str(_t or "").lower()
        _s = "".join(_c if _c.isalnum() or _c.isspace() else " " for _c in _s)
        return " ".join(_s.split())
    def _vc_comp_fingerprint(_it: Dict[str, Any]) -> str:
        return "|".join([
            str((_it or {}).get("player_name") or "").strip().lower()[:32],
            str((_it or {}).get("product_family") or (_it or {}).get("set_name") or "").strip().lower()[:32],
            str((_it or {}).get("parallel_family") or (_it or {}).get("parallel_name") or "").strip().lower()[:32],
            str((_it or {}).get("serial_denominator") or (_it or {}).get("serial") or "").strip().lower()[:16],
            str((_it or {}).get("grade") or (_it or {}).get("grade_label") or "").strip().lower()[:16],
            _vc_title_fingerprint((_it or {}).get("title") or "")[:80],
            str((_it or {}).get("seller") or (_it or {}).get("seller_username") or (_it or {}).get("sellerUsername") or "").strip().lower()[:32],
        ])
    _vc_src_iid = str(iid or "").strip()
    _vc_src_url = _vc_normalize_url(item_url or "")
    _vc_src_target = dict(target_listing_item or {})
    _vc_src_seller = str(
        _vc_src_target.get("seller")
        or _vc_src_target.get("seller_username")
        or _vc_src_target.get("sellerUsername")
        or ""
    ).strip().lower()
    _vc_src_title_fp = _vc_title_fingerprint(title)
    _vc_filtered_buffer: List = []
    _vc_seen_fingerprints: set = set()
    _vc_blocked_self = 0
    _vc_blocked_active = 0
    _vc_blocked_dup = 0
    for _vc_row in list(accepted_buffer or []):
        _vc_it = _vc_row[0] if (isinstance(_vc_row, tuple) and len(_vc_row) > 0) else {}
        if not isinstance(_vc_it, dict):
            _vc_it = {}
        _vc_comp_iid = str(
            _vc_it.get("item_id") or _vc_it.get("itemId") or _vc_it.get("source_item_id") or ""
        ).strip()
        _vc_comp_url = _vc_normalize_url(
            _vc_it.get("url") or _vc_it.get("itemWebUrl") or _vc_it.get("listing_url") or ""
        )
        _vc_comp_seller = str(
            _vc_it.get("seller") or _vc_it.get("seller_username") or _vc_it.get("sellerUsername") or ""
        ).strip().lower()
        _vc_comp_title_fp = _vc_title_fingerprint(_vc_it.get("title") or "")
        _vc_comp_pool_kind = str(_vc_it.get("_valuation_pool_kind") or pool_kind or "").strip().lower()
        _vc_comp_listing_status = str(_vc_it.get("listing_status") or _vc_it.get("_listing_status") or "").strip().lower()
        _vc_block_reason = ""
        # Self-comp: same eBay item_id
        if _vc_src_iid and _vc_comp_iid and _vc_comp_iid == _vc_src_iid:
            _vc_block_reason = "self_item_id_match"
        # Mirror listing: same normalized URL
        elif _vc_src_url and _vc_comp_url and _vc_comp_url == _vc_src_url:
            _vc_block_reason = "mirror_url_match"
        # Same seller + same title fingerprint = self / duplicate listing
        elif _vc_src_seller and _vc_comp_seller and _vc_src_seller == _vc_comp_seller and _vc_src_title_fp and _vc_comp_title_fp == _vc_src_title_fp:
            _vc_block_reason = "same_seller_same_title_fingerprint"
        if _vc_block_reason:
            _vc_blocked_self += 1
            try:
                print(
                    f"[SELF_COMP_BLOCK] title={str(_vc_it.get('title') or '')[:160]} "
                    f"reason={_vc_block_reason}"
                )
            except Exception:
                pass
            continue
        # Active listings / unsold listings — must be sold comps only
        if _vc_comp_pool_kind in {"active", "active_listings", "active_finding", "browse_active", "live"}:
            _vc_blocked_active += 1
            try:
                print(
                    f"[ACTIVE_LISTING_BLOCK] title={str(_vc_it.get('title') or '')[:160]} "
                    f"reason=pool_kind={_vc_comp_pool_kind}"
                )
            except Exception:
                pass
            continue
        if _vc_comp_listing_status in {"active", "live", "running", "in_progress"}:
            _vc_blocked_active += 1
            try:
                print(
                    f"[ACTIVE_LISTING_BLOCK] title={str(_vc_it.get('title') or '')[:160]} "
                    f"reason=listing_status={_vc_comp_listing_status}"
                )
            except Exception:
                pass
            continue
        if bool(_vc_it.get("is_active")) or bool(_vc_it.get("_is_active_listing")):
            _vc_blocked_active += 1
            try:
                print(
                    f"[ACTIVE_LISTING_BLOCK] title={str(_vc_it.get('title') or '')[:160]} "
                    f"reason=is_active_flag"
                )
            except Exception:
                pass
            continue
        # Fingerprint duplicate (player+product+parallel+serial+grade+title_fp+seller)
        _vc_fp = _vc_comp_fingerprint(_vc_it)
        if _vc_fp and _vc_fp in _vc_seen_fingerprints:
            _vc_blocked_dup += 1
            try:
                print(
                    f"[SELF_COMP_BLOCK] title={str(_vc_it.get('title') or '')[:160]} "
                    f"reason=duplicate_fingerprint"
                )
            except Exception:
                pass
            continue
        if _vc_fp:
            _vc_seen_fingerprints.add(_vc_fp)
        _vc_filtered_buffer.append(_vc_row)
    if (_vc_blocked_self + _vc_blocked_active + _vc_blocked_dup) > 0:
        try:
            print(
                f"[CONTAMINATION_FILTER_SUMMARY] item={_vc_src_iid[:24] or '?'} "
                f"buffer_in={len(accepted_buffer)} "
                f"buffer_out={len(_vc_filtered_buffer)} "
                f"self_comp_blocks={_vc_blocked_self} "
                f"active_listing_blocks={_vc_blocked_active} "
                f"duplicate_blocks={_vc_blocked_dup}"
            )
        except Exception:
            pass
    accepted_buffer = _vc_filtered_buffer
    # ────────────────────────────────────────────────────────────────────────

    accepted_comps: List[AcceptedComp] = []
    for i, (it, ct, price, w, qual, gb_reason, sale_type, grade_fb, lane_tier, lane_reason, lane_sig) in enumerate(
        accepted_buffer
    ):
        ipk_b = it.get("_valuation_pool_kind") or pool_kind
        vm_level, vm_dbg = variant_match_assessment(profile, ct)
        exactness_tier = "exact_strict"
        if lane_tier == "near_lane":
            exactness_tier = "near_lane"
        elif lane_tier in _PREMIUM_SUPPORT_LANE_TIERS:
            exactness_tier = lane_tier
        elif lane_tier not in ("", "exact_lane"):
            exactness_tier = "weak_fallback_lane"
        if grade_fb and exactness_tier == "exact_strict":
            exactness_tier = "exact_grade_fallback"
        accepted_comps.append(
            _build_accepted_comp(
                i,
                it,
                ct,
                price,
                w,
                qual,
                gb_reason,
                ipk_b,
                today,
                sold_recent_30,
                sale_type=sale_type,
                grade_fallback=grade_fb,
                exactness_tier=exactness_tier,
                variant_match_level=vm_level,
                variant_debug=vm_dbg[:400],
                comp_lane_tier=lane_tier,
                comp_lane_reason=lane_reason,
                comp_identity_signature=lane_sig,
            )
        )

    comp_items = [row[0] for row in accepted_buffer]
    _int_ok, _int_msg = comp_listing_validation.assert_no_target_in_accepted(
        iid, tuple(comp_items)
    )
    if not _int_ok:
        notes_parts.append(f"Comp integrity guard tripped: {_int_msg}")

    dup_suppressed_n, visual_counts, visual_dom = enrich_accepted_comp_pool(
        accepted_comps,
        comp_items,
        target_title=title,
        target_item=target_listing_item,
        target_is_graded=_is_graded_listing(title),
        today=today,
    )
    _apply_mv_value_pool_tags(accepted_comps, comp_items, profile, title)
    man_ap_boost, learned_skewed = _apply_manual_review_weights(
        accepted_comps, comp_items, man_state, decisions
    )
    for c in accepted_comps:
        if getattr(c, "manual_decision", "") == "approve":
            c.counts_toward_value = True
            cur = getattr(c, "mv_selection_tags", "") or ""
            if "manual_promoted_mv" not in cur:
                c.mv_selection_tags = f"{cur}|manual_promoted_mv".strip("|")
    cond_issues_acc = condition_issue_count(accepted_comps)
    tier_cnt_map = tier_counts(accepted_comps)
    visual_summary = _format_visual_debug_summary(visual_dom, visual_counts)
    target_lane_signature = _build_card_identity_signature(profile)
    _strict_lane_titles = [
        c.title
        for c in accepted_comps
        if getattr(c, "counts_toward_value", False) or getattr(c, "comp_lane_tier", "") == "exact_lane"
    ]
    _lane_contaminated, _lane_contam_reason, _lane_contam_summary = _detect_comp_lane_contamination(
        profile,
        _strict_lane_titles or [c.title for c in accepted_comps],
    )
    comp_lane_status = "strict_lane_match"
    comp_lane_warning = ""
    if _lane_contaminated:
        comp_lane_status = "contaminated_lane"
        comp_lane_warning = _lane_contam_reason.replace("_", " ")
    elif any(getattr(c, "comp_lane_tier", "") in _PREMIUM_SUPPORT_LANE_TIERS for c in accepted_comps):
        comp_lane_status = "premium_support_lane"
        comp_lane_warning = ",".join(
            sorted(
                {
                    str(getattr(c, "comp_lane_tier", "") or "")
                    for c in accepted_comps
                    if str(getattr(c, "comp_lane_tier", "") or "") in _PREMIUM_SUPPORT_LANE_TIERS
                }
            )
        )[:160]
    elif any(getattr(c, "comp_lane_tier", "") == "near_lane" for c in accepted_comps):
        comp_lane_status = "near_lane_only"
    elif any(getattr(c, "comp_lane_tier", "") not in ("", "exact_lane") for c in accepted_comps):
        comp_lane_status = "fallback_family_only"

    accepted_n = len(accepted_comps)
    class_exact_count = sum(
        1
        for c in accepted_comps
        if str(getattr(c, "comp_lane_tier", "") or "") in {"", "exact_lane", "near_lane"}
    )
    class_support_count = sum(
        1
        for c in accepted_comps
        if str(getattr(c, "comp_lane_tier", "") or "") in _PREMIUM_SUPPORT_LANE_TIERS
    )
    _trusted_exact_comps = [
        c
        for c in accepted_comps
        if str(getattr(c, "comp_lane_tier", "") or "") in {"", "exact_lane", "near_lane"}
    ]
    _support_comps = [
        c
        for c in accepted_comps
        if str(getattr(c, "comp_lane_tier", "") or "") in _PREMIUM_SUPPORT_LANE_TIERS
    ]

    # ── PRICE_ECHO_BLOCK / TRUE_MV_CONTAMINATION_BLOCK ──────────────────────
    # If the trusted-exact comp set is thin (≤2) AND the median trusted-exact
    # price echoes the live current price within 1%, the comp pool is almost
    # certainly the active auction itself or a mirror listing leaking through
    # despite the fingerprint guards. Drop the trusted_exact set so true_mv /
    # target_bid cannot be derived from contaminated echoes. The row falls
    # back to support / review-only pricing downstream.
    try:
        _vc_current_price = _safe_float(
            (target_listing_item or {}).get("current_price")
            or (target_listing_item or {}).get("current_bid")
            or (target_listing_item or {}).get("source_current_bid")
        )
    except Exception:
        _vc_current_price = None
    if _vc_current_price is not None and _vc_current_price > 0 and _trusted_exact_comps and len(_trusted_exact_comps) <= 2:
        _vc_prices = sorted([float(getattr(c, "price", 0.0) or 0.0) for c in _trusted_exact_comps if float(getattr(c, "price", 0.0) or 0.0) > 0])
        _vc_median = _vc_prices[len(_vc_prices) // 2] if _vc_prices else 0.0
        _vc_diff_pct = (abs(_vc_median - float(_vc_current_price)) / float(_vc_current_price) * 100.0) if float(_vc_current_price) > 0 else 100.0
        if _vc_median > 0 and _vc_diff_pct <= 1.0:
            try:
                print(
                    f"[PRICE_ECHO_BLOCK] title={title[:160]} "
                    f"current_price={round(float(_vc_current_price), 2)} "
                    f"true_mv={round(float(_vc_median), 2)} "
                    f"diff_pct={round(float(_vc_diff_pct), 2)}"
                )
                print(
                    f"[TRUE_MV_CONTAMINATION_BLOCK] title={title[:160]} "
                    f"exact_count={len(_trusted_exact_comps)} "
                    f"reason=price_echo_within_1pct_thin_exact_set"
                )
            except Exception:
                pass
            # Hard reject: zero out trusted_exact so downstream cannot derive
            # true_mv from contaminated echoes. Support comps remain — the row
            # downgrades to review pricing or suppresses target bid.
            _trusted_exact_comps = []
            # [PRICE_ECHO_BROADER_STRIP] — Also remove contaminated comp(s) from
            # accepted_comps. Without this, _build_exact_true_mv_payload at the
            # publish step (called later in this function) reuses the same
            # contaminated comp from accepted_comps and re-derives a poisoned
            # pub_point. The MV_ECHO_TRACE evidence showed rows surfacing with
            # `trusted_exact_comp_count=1` AND `true_mv=current_price exactly`
            # AND empty evidence_pool — proving the count and value flowed
            # through accepted_comps even after _trusted_exact_comps was zeroed.
            # Stripping accepted_comps here closes that path; downstream counts
            # and medians become honest, the row drops to truth_tier=REVIEW or
            # NONE instead of fake-TRUE, and risk_block still fires (correctly,
            # for "no MV" rather than "echo-poisoned MV").
            try:
                _pre_strip_count = len(list(accepted_comps or []))
                _stripped_indices: List[int] = []
                _kept: List[Any] = []
                for _idx, _ac in enumerate(list(accepted_comps or [])):
                    try:
                        _ac_price = float(getattr(_ac, "price", 0.0) or 0.0)
                    except (TypeError, ValueError):
                        _ac_price = 0.0
                    if (
                        _ac_price > 0
                        and float(_vc_current_price) > 0
                        and abs(_ac_price - float(_vc_current_price)) / float(_vc_current_price) <= 0.01
                    ):
                        _stripped_indices.append(_idx)
                        continue
                    _kept.append(_ac)
                if _stripped_indices:
                    accepted_comps = _kept
                    print(
                        f"[PRICE_ECHO_BROADER_STRIP] title={title[:140]} "
                        f"pre_strip_count={_pre_strip_count} "
                        f"post_strip_count={len(accepted_comps)} "
                        f"stripped_count={len(_stripped_indices)} "
                        f"current={round(float(_vc_current_price), 2)}"
                    )
            except Exception as _pesb_exc:
                print(f"[PRICE_ECHO_BROADER_STRIP] error_type={type(_pesb_exc).__name__} msg={str(_pesb_exc)[:120]}")
    # ────────────────────────────────────────────────────────────────────────
    print(
        f"[SUPPORT_HANDOFF_OUT] title={title[:140]} "
        f"accepted_support_count={len(list(_support_comps or []))} "
        f"support_titles={[str(getattr(c, 'title', '') or '')[:100] for c in list(_support_comps or [])[:3]]}"
    )
    _comp_result_payload = {
        "trusted_exact_comps": [_accepted_comp_to_evidence_row(c) for c in _trusted_exact_comps],
        "support_comps": [_accepted_comp_to_evidence_row(c) for c in _support_comps],
    }
    print(
        f"[COMP_RESULT_PAYLOAD] title={title[:140]} "
        f"trusted_exact_count={len(list(_comp_result_payload.get('trusted_exact_comps') or []))} "
        f"support_count={len(list(_comp_result_payload.get('support_comps') or []))}"
    )
    if len(list(_support_comps or [])) > 0 and int(class_support_count or 0) == 0:
        class_support_count = len(list(_support_comps or []))
        print(
            f"[SUPPORT_COUNT_REPAIRED] title={title[:140]} "
            f"repaired_support_comp_count={class_support_count}"
        )
    print(f"[COMP_TRACE][PARSE] item={iid[:24]} parsed_comps={accepted_n} exact_kept={fingerprint_exact_kept} near_kept={fingerprint_near_kept}")
    operator_accept_profile = " | ".join(
        [
            f"{str(getattr(c, 'comp_lane_tier', '') or '')}:{str(getattr(c, 'exactness_tier', '') or '')}:{str(getattr(c, 'title', '') or '')[:52]}"
            for c in accepted_comps[:4]
        ]
    )
    if accepted_n > 0:
        print(
            f"[OPERATOR_ACCEPTED] item={str(iid or '')[:24]} "
            f"profile=\"{operator_accept_profile[:220]}\""
        )

    def _pipeline_blob(
        final_status: str,
        failure_reason: str,
        *,
        lane_n: Optional[int] = None,
        strength_label: str = "",
        mv_pool_mode: str = "",
        mv_strict_comp_count: int = 0,
        mv_relaxed_comp_count: int = 0,
        mv_strict_lane_comp_count: int = 0,
        mv_relaxed_fallback_used: bool = False,
        mv_fallback_reason: str = "",
        comp_lane_label: str = "",
        comp_lane_status: str = "",
        comp_lane_warning: str = "",
        comp_lane_signature: str = "",
    ) -> str:
        pl = {
            "final_value_status": final_status,
            "valuation_failure_reason": failure_reason,
            "query_passes": pass_logs,
            "primary_debug_query": query,
            "raw_listings_merged_unique": fetched,
            "sum_fetched_per_pass": total_raw_fetched,
            "accepted_after_strict_filters": accepted_n,
            "buffer_len_before_accepted_comp_objects": len(accepted_buffer),
            "duplicate_suppressed_count": dup_suppressed_n,
            "condition_flagged_accepted": cond_issues_acc,
            "top_rejection_buckets": reject_summary,
            "lane_selected_count": lane_n if lane_n is not None else 0,
            "valuation_strength_result": strength_label,
            "mv_pool_mode": mv_pool_mode,
            "mv_strict_comp_count": mv_strict_comp_count,
            "mv_relaxed_comp_count": mv_relaxed_comp_count,
            "mv_strict_lane_comp_count": mv_strict_lane_comp_count,
            "mv_relaxed_fallback_used": mv_relaxed_fallback_used,
            "mv_fallback_reason": mv_fallback_reason,
            "comp_lane_label": str(comp_lane_label or ""),
            "comp_lane_status": str(comp_lane_status or ""),
            "comp_lane_warning": str(comp_lane_warning or ""),
            "comp_lane_signature": str(comp_lane_signature or ""),
            "sold_candidates_fetched": int(recovery_diag.get("sold_candidates_fetched") or 0),
            "sold_candidates_after_norm": int(recovery_diag.get("sold_candidates_after_norm") or 0),
            "strict_lane_accept_count": int(recovery_diag.get("strict_lane_accept_count") or 0),
            "near_lane_accept_count": int(recovery_diag.get("near_lane_accept_count") or 0),
            "grade_bridge_accept_count": int(recovery_diag.get("grade_bridge_accept_count") or 0),
            "rejection_reason_counts": recovery_diag.get("rejection_reason_counts") or {},
            "recovery_mode": str(recovery_diag.get("recovery_mode") or ""),
            "recovery_note": str(recovery_diag.get("recovery_note") or ""),
        }
        try:
            return json.dumps(pl, ensure_ascii=False)[:8000]
        except (TypeError, ValueError):
            return str(pl)[:8000]

    def _debug_base(**kwargs) -> HybridValuation:
        base = {
            "debug_search_query": query,
            "debug_pool_kind": debug_pool_kind,
            "debug_fetched_count": fetched,
            "debug_accepted_count": accepted_n,
            "debug_rejections_top": reject_summary,
            "debug_comp_trace": comp_trace,
            "debug_comp_passes_json": passes_json,
            "comp_search_attempted": comp_search_attempted,
            "comps_pre_enrich_count": len(accepted_buffer),
            "comp_lane_label": target_lane_signature,
            "comp_lane_status": comp_lane_status,
            "comp_lane_warning": comp_lane_warning,
            "comp_lane_signature": target_lane_signature,
            "recovery_mode": str(recovery_diag.get("recovery_mode") or ""),
            "recovery_note": str(recovery_diag.get("recovery_note") or ""),
            "operator_plan_query": str(operator_plan.get("query_primary") or ""),
            "operator_plan_fingerprint": str(operator_plan.get("fingerprint_key") or ""),
            "operator_exact_kept": int(fingerprint_exact_kept),
            "operator_near_kept": int(fingerprint_near_kept),
            "operator_rejected": int(sum(int(v) for v in fingerprint_reject_counts.values())),
            "operator_accept_profile": operator_accept_profile[:500],
        }
        base.update(kwargs)
        return HybridValuation(**base)

    def _log_class_support(final_conf: str) -> None:
        print(
            f"[CLASS_SUPPORT] item={iid[:24] or '?'} exact={int(class_exact_count)} "
            f"support={int(class_support_count)} final_conf={str(final_conf or '')[:24]}"
        )

    def _build_support_target_row() -> Dict[str, Any]:
        _row = dict(target_row_for_class or {})
        if not str(_row.get("product_family") or "").strip():
            _row["product_family"] = str(
                getattr(profile, "product_family", "")
                or getattr(profile, "primary_set", "")
                or ""
            ).strip().lower()
        if not str(_row.get("parallel_family") or "").strip():
            _row["parallel_family"] = str(
                normalize_parallel_bucket(profile) or ""
            ).strip().lower()
        if not str(_row.get("serial_denominator") or _row.get("serial") or "").strip():
            _serial_seed = _extract_serial_denominator(title)
            if _serial_seed:
                _row["serial_denominator"] = str(_serial_seed).strip()
        if not str(_row.get("insert_family") or "").strip():
            _row["insert_family"] = str(
                premium_class_meta.get("subset_family")
                or ("auto" if bool(premium_class_meta.get("auto_flag")) else "")
                or ""
            ).strip().lower()
        if not str(_row.get("lane_type") or "").strip():
            _support_insert = str(_row.get("insert_family") or "").strip().lower()
            _support_parallel = str(_row.get("parallel_family") or "").strip().lower()
            _support_serial = str(_row.get("serial_denominator") or _row.get("serial") or "").strip().lower()
            if _support_insert and (_support_parallel or _support_serial):
                _row["lane_type"] = "insert_parallel"
            elif _support_parallel or _support_serial:
                _row["lane_type"] = "parallel_serial"
            elif _support_insert:
                _row["lane_type"] = "insert"
            else:
                _row["lane_type"] = "base"
        return _row

    def _support_truth_median(support_comps: List[AcceptedComp], cap_value: Optional[float] = None) -> Optional[float]:
        _support_prices = sorted(
            float(getattr(c, "price"))
            for c in support_comps
            if _safe_float(getattr(c, "price", None)) is not None and float(getattr(c, "price")) > 0
        )
        if not _support_prices:
            return None
        _mid = len(_support_prices) // 2
        _support_mv = (
            _support_prices[_mid]
            if len(_support_prices) % 2 == 1
            else (_support_prices[_mid - 1] + _support_prices[_mid]) / 2.0
        )
        if cap_value is not None and cap_value > 0:
            _support_mv = min(float(_support_mv), float(cap_value))
        return round(float(_support_mv), 2)

    _support_comps = [
        c
        for c in _support_comps
        if _safe_float(getattr(c, "price", None)) is not None
        and (_safe_float(getattr(c, "price", None)) or 0.0) > 0
    ]
    _support_target_row = _build_support_target_row()
    print(
        f"[SUPPORT_GATE_INPUT] title={title[:140]} "
        f"lane_type={_support_target_row.get('lane_type')} "
        f"product_family={_support_target_row.get('product_family')} "
        f"insert_family={_support_target_row.get('insert_family')} "
        f"parallel_family={_support_target_row.get('parallel_family')} "
        f"serial_denominator={_support_target_row.get('serial_denominator') or _support_target_row.get('serial')} "
        f"trusted_exact={len(list(_trusted_exact_comps or []))} "
        f"support_count={len(list(_support_comps or []))}"
    )
    print(
        f"[SUPPORT_HANDOFF_IN] title={title[:140]} "
        f"trusted_exact_in={len(list(_trusted_exact_comps or []))} "
        f"support_in={len(list(_support_comps or []))}"
    )
    print(
        f"[SUPPORT_IN_TITLES] title={title[:140]} "
        f"titles={[str(getattr(c, 'title', '') or '')[:100] for c in list(_support_comps or [])[:3]]}"
    )
    support_comp_count = int(len(list(_support_comps or [])))
    print(
        f"[SUPPORT_COUNT_FINAL] title={title[:140]} "
        f"support_comp_count={support_comp_count} "
        f"support_input_count={len(list(_support_comps or []))}"
    )
    if len(list(_support_comps or [])) > 0 and support_comp_count == 0:
        support_comp_count = len(list(_support_comps or []))
        print(
            f"[SUPPORT_COUNT_REPAIRED] title={title[:140]} "
            f"repaired_support_comp_count={support_comp_count}"
        )
    if support_comp_count > 0:
        print(
            f"[SUPPORT_GATE_READY] title={title[:140]} "
            f"support_comp_count={support_comp_count}"
        )
    _support_ok, _support_reason = _support_truth_eligible(_support_target_row, _support_comps)

    if fetched == 0:
        insuf_reason = "no_results_fetched"
    elif accepted_n == 0:
        insuf_reason = "all_comps_rejected_by_filters"
    else:
        insuf_reason = "insufficient_accepted_comps"

    if accepted_n < MIN_ACCEPTED_COMPS:
        man_cfg_ins = manual_comp_review.get_manual_mv_config(man_state, man_key)
        mv_ins = _safe_float(man_cfg_ins.get("manual_value"))
        if man_key and man_cfg_ins.get("use_manual_mv") and mv_ins and mv_ins > 0:
            mlo = _safe_float(man_cfg_ins.get("manual_low")) or mv_ins
            mhi = _safe_float(man_cfg_ins.get("manual_high")) or mv_ins
            _log_class_support("manual_override")
            return _debug_base(
                notes="Manual canonical MV (insufficient auto comps).",
                confidence="manual_override",
                comp_count=0,
                accepted_comp_count=accepted_n,
                last_comp_date=date.today().isoformat(),
                value=mv_ins,
                value_low=mlo,
                value_high=mhi,
                market_value_source="manual_canonical_override",
                cluster_method="none",
                valuation_basis="manual_canonical_override",
                valuation_flow_label="manual_mv_override",
                manual_review_audit=(
                    f"insufficient_auto_comps | rej={manual_reject_hits} "
                    f"boost={man_ap_boost} learn={'y' if learned_skewed else 'n'}"
                ),
                debug_accepted_comps_json="[]",
                debug_canonical_key=audit_canonical_key or man_key,
                valuation_failure_reason=insuf_reason,
                valuation_final_status="manual_override_published",
                debug_valuation_pipeline_json=_pipeline_blob(
                    "manual_override_published",
                    insuf_reason,
                ),
            )
        if support_comp_count > 0:
            if _support_ok:
                _support_pub_point = _support_truth_median(_support_comps)
                if _support_pub_point is not None and _support_pub_point > 0:
                    _support_true_mv, _support_review_mv, _support_truth_tier = _split_truth_market_value(
                        title=title,
                        value=_support_pub_point,
                        source="support_comp_engine",
                        accepted_count=accepted_n,
                        comp_lane_status=comp_lane_status,
                        confidence="low",
                        comp_lane_warning=comp_lane_warning,
                        serial_lane_summary={},
                        exact_comp_count=0,
                        exact_comp_value=None,
                    )
                    _support_contract = _enforce_true_mv_contract(
                        title=title,
                        stage="publish",
                        truth=_support_truth_tier,
                        source="support_comp_engine",
                        exact_comp_count=0,
                        true_mv=_support_true_mv,
                        review_estimate=_support_review_mv,
                        published_value=_support_pub_point,
                    )
                    _support_true_mv = _support_contract.get("true_mv")
                    _support_review_mv = _support_contract.get("review_estimate")
                    _support_truth_tier = str(_support_contract.get("truth") or _support_truth_tier or "NONE").upper()
                    _support_band_pct = 0.22 if support_comp_count == 1 else 0.18
                    if support_comp_count >= 3:
                        _support_band_pct = 0.14
                    _support_low = round(float(_support_pub_point) * (1.0 - _support_band_pct), 2)
                    _support_high = round(float(_support_pub_point) * (1.0 + _support_band_pct), 2)
                    notes_parts.append(
                        f"TRUE MV promoted from clean support comp lane (support_count={support_comp_count})."
                    )
                    print(
                        f"[SUPPORT_TRUTH_PROMOTE] title={title[:140]} "
                        f"support_count={support_comp_count} "
                        f"true_mv={_support_pub_point} "
                        f"reason=clean_support_lane"
                    )
                    _log_class_support("low")
                    return _debug_base(
                        notes=" ".join(notes_parts).strip(),
                        confidence="low",
                        comp_count=support_comp_count,
                        accepted_comp_count=accepted_n,
                        last_comp_date=date.today().isoformat(),
                        value=_support_pub_point,
                        true_market_value=_support_true_mv,
                        review_estimate_value=_support_review_mv,
                        value_low=_support_low,
                        value_high=_support_high,
                        dominant_range_low=_support_low,
                        dominant_range_high=_support_high,
                        dominant_comp_count=support_comp_count,
                        market_lane_low=_support_low,
                        market_lane_high=_support_high,
                        market_lane_comp_count=support_comp_count,
                        market_lane_recent_count=sum(
                            1
                            for c in _support_comps
                            if str(getattr(c, "recency_bucket", "") or "") in {"7d", "30d", "active_proxy"}
                        ),
                        market_lane_method="support_comp_engine",
                        market_lane_strength=0.0,
                        market_value_source="support_comp_engine",
                        cluster_method="support_comp_engine",
                        valuation_basis="support_comp_engine",
                        valuation_truth_tier=_support_truth_tier,
                        valuation_flow_label="support_comp_engine",
                        valuation_strength="provisional_estimate",
                        debug_confidence_rationale=f"support_comp_engine; support={support_comp_count}; exact=0",
                        manual_review_audit=(
                            f"rej={manual_reject_hits} boost={man_ap_boost} learn={'y' if learned_skewed else 'n'}"
                        ),
                        debug_accepted_comps_json="[]",
                        valuation_failure_reason="",
                        valuation_final_status="support_comp_published",
                        debug_valuation_pipeline_json=_pipeline_blob(
                            "support_comp_published",
                            "",
                            lane_n=support_comp_count,
                            strength_label="provisional_estimate",
                            mv_pool_mode="support_comp_engine",
                            mv_relaxed_comp_count=support_comp_count,
                            mv_relaxed_fallback_used=False,
                        ),
                        mv_pool_mode="support_comp_engine",
                        mv_strict_comp_count=0,
                        mv_relaxed_comp_count=support_comp_count,
                        mv_strict_lane_comp_count=0,
                        mv_relaxed_fallback_used=False,
                        mv_fallback_reason="",
                        exact_comp_count=0,
                        comp_lane_label=target_lane_signature,
                        comp_lane_status="premium_support_lane",
                        comp_lane_warning=comp_lane_warning or "support_comp_engine",
                        comp_lane_signature=target_lane_signature,
                        comp_evidence={
                            "used": [],
                            "trusted_exact_comps": [
                                _accepted_comp_to_evidence_row(c)
                                for c in _trusted_exact_comps
                                if _accepted_comp_to_evidence_row(c)
                            ],
                            "support_comps": [
                                _accepted_comp_to_evidence_row(c)
                                for c in _support_comps
                                if _accepted_comp_to_evidence_row(c)
                            ],
                            "rejected": [],
                        },
                    )
                print(
                    f"[SUPPORT_TRUTH_REJECT] title={title[:140]} "
                    f"reason=no_numeric_support_prices"
                )
            else:
                print(
                    f"[SUPPORT_TRUTH_REJECT] title={title[:140]} "
                    f"reason={_support_reason}"
                )
        single_comp = accepted_comps[0] if accepted_n == 1 and accepted_comps else None
        if single_comp and float(getattr(single_comp, "price", 0.0) or 0.0) > 0:
            single_price = round(float(single_comp.price), 2)
            single_tier = str(getattr(single_comp, "exactness_tier", "") or "")
            single_recent = str(getattr(single_comp, "recency_bucket", "") or "")
            single_qual = float(getattr(single_comp, "qual", 0.0) or 0.0)
            single_date = (
                single_comp.sale_date.isoformat()
                if getattr(single_comp, "sale_date", None)
                else date.today().isoformat()
            )
            publish_single = (
                single_qual >= 0.72
                and single_tier in ("exact_strict", "exact_synonym_normalized", "exact_grade_fallback")
            )
            if publish_single:
                band_pct = 0.12
                if single_recent == "7d" and single_tier == "exact_strict":
                    band_pct = 0.08
                elif single_recent in ("7d", "30d"):
                    band_pct = 0.10
                if single_tier == "exact_grade_fallback":
                    band_pct = max(band_pct, 0.14)
                vlow = round(single_price * (1.0 - band_pct), 2)
                vhigh = round(single_price * (1.0 + band_pct), 2)
                notes_parts.append(
                    "Thin exact comp pool; publishing conservative range from the strongest accepted comp."
                )
                notes_parts.append(
                    f"Single-comp lane: {single_tier} | qual={single_qual:.2f} | recency={single_recent or 'unknown'}."
                )
                _log_class_support("low")
                return _debug_base(
                    notes=" ".join(notes_parts).strip(),
                    confidence="low",
                    comp_count=1,
                    accepted_comp_count=accepted_n,
                    last_comp_date=single_date,
                    value=single_price,
                    value_low=vlow,
                    value_high=vhigh,
                    dominant_range_low=vlow,
                    dominant_range_high=vhigh,
                    dominant_comp_count=1,
                    market_lane_low=vlow,
                    market_lane_high=vhigh,
                    market_lane_comp_count=1,
                    market_lane_recent_count=(1 if single_recent in ("7d", "30d") else 0),
                    market_lane_method="single_comp_conservative",
                    market_lane_strength=single_qual,
                    market_value_source="single_comp_conservative",
                    cluster_method="single_comp_conservative",
                    valuation_basis="single_comp_conservative",
                    valuation_flow_label="thin_comp_published",
                    debug_confidence_rationale=(
                        f"single_comp_conservative; tier={single_tier}; qual={single_qual:.2f}; "
                        f"recency={single_recent or 'unknown'}"
                    ),
                    manual_review_audit=(
                        f"rej={manual_reject_hits} boost={man_ap_boost} learn={'y' if learned_skewed else 'n'}"
                    ),
                    debug_accepted_comps_json="[]",
                    valuation_failure_reason=insuf_reason,
                    valuation_final_status="thin_comp_estimate_published",
                    debug_valuation_pipeline_json=_pipeline_blob(
                        "thin_comp_estimate_published",
                        insuf_reason,
                    ),
                    mv_pool_mode="thin_exact",
                    mv_strict_comp_count=1,
                    mv_relaxed_comp_count=0,
                    mv_strict_lane_comp_count=1,
                    mv_relaxed_fallback_used=False,
                    mv_fallback_reason=f"single_comp_conservative:{single_tier}",
                )
        scarcity_support_plan = _premium_scarcity_bucket_publish_plan(
            target_title=title,
            item_id=iid,
            accepted_comps=accepted_comps,
            today=today,
        )
        if scarcity_support_plan:
            notes_parts.append(
                "Low-supply premium valuation published from same class/product scarcity-bucket support."
            )
            notes_parts.append(
                f"Scarcity bucket support: {scarcity_support_plan['bucket_label']} | "
                f"exact={int(scarcity_support_plan['exact_count'])} | "
                f"support={int(scarcity_support_plan['support_count'])}."
            )
            if bool(scarcity_support_plan.get("grade_downgraded")):
                notes_parts.append("Grade downgrade path used inside support lane.")
            _log_class_support(str(scarcity_support_plan.get("confidence") or "low"))
            return _debug_base(
                notes=" ".join(notes_parts).strip(),
                confidence=str(scarcity_support_plan.get("confidence") or "low"),
                comp_count=int(scarcity_support_plan.get("support_count") or 0),
                accepted_comp_count=accepted_n,
                last_comp_date=str(scarcity_support_plan.get("last_comp_date") or date.today().isoformat()),
                value=float(scarcity_support_plan.get("value") or 0.0),
                value_low=float(scarcity_support_plan.get("value_low") or 0.0),
                value_high=float(scarcity_support_plan.get("value_high") or 0.0),
                dominant_range_low=float(scarcity_support_plan.get("value_low") or 0.0),
                dominant_range_high=float(scarcity_support_plan.get("value_high") or 0.0),
                dominant_comp_count=int(scarcity_support_plan.get("support_count") or 0),
                market_lane_low=float(scarcity_support_plan.get("value_low") or 0.0),
                market_lane_high=float(scarcity_support_plan.get("value_high") or 0.0),
                market_lane_comp_count=int(scarcity_support_plan.get("support_count") or 0),
                market_lane_recent_count=int(scarcity_support_plan.get("recent_count") or 0),
                market_lane_method="scarcity_bucket_support_conservative",
                market_lane_strength=float(scarcity_support_plan.get("market_lane_strength") or 0.0),
                market_value_source="premium_scarcity_bucket_support",
                cluster_method="scarcity_bucket_support_conservative",
                valuation_basis="premium_scarcity_bucket_support",
                valuation_flow_label="premium_scarcity_bucket_support",
                valuation_strength="provisional_estimate",
                valuation_downgrade_reasons="scarcity_bucket_support_low_supply",
                debug_confidence_rationale=(
                    f"scarcity_bucket_support; bucket={scarcity_support_plan.get('bucket_label')}; "
                    f"exact={int(scarcity_support_plan.get('exact_count') or 0)}; "
                    f"support={int(scarcity_support_plan.get('support_count') or 0)}"
                ),
                manual_review_audit=(
                    f"rej={manual_reject_hits} boost={man_ap_boost} learn={'y' if learned_skewed else 'n'}"
                ),
                debug_accepted_comps_json="[]",
                valuation_failure_reason="",
                valuation_final_status="scarcity_bucket_support_published",
                debug_valuation_pipeline_json=_pipeline_blob(
                    "scarcity_bucket_support_published",
                    "",
                    lane_n=int(scarcity_support_plan.get("support_count") or 0),
                    strength_label="provisional_estimate",
                    mv_pool_mode="scarcity_bucket_support",
                    mv_strict_comp_count=int(scarcity_support_plan.get("exact_count") or 0),
                    mv_relaxed_comp_count=int(scarcity_support_plan.get("support_count") or 0),
                    mv_strict_lane_comp_count=int(scarcity_support_plan.get("exact_count") or 0),
                    mv_relaxed_fallback_used=False,
                    mv_fallback_reason=f"scarcity_bucket_support:{scarcity_support_plan.get('bucket') or ''}",
                ),
                mv_pool_mode="scarcity_bucket_support",
                mv_strict_comp_count=int(scarcity_support_plan.get("exact_count") or 0),
                mv_relaxed_comp_count=int(scarcity_support_plan.get("support_count") or 0),
                mv_strict_lane_comp_count=int(scarcity_support_plan.get("exact_count") or 0),
                mv_relaxed_fallback_used=False,
                mv_fallback_reason=f"scarcity_bucket_support:{scarcity_support_plan.get('bucket') or ''}",
                comp_lane_label=target_lane_signature,
                comp_lane_status="premium_support_lane",
                comp_lane_warning="scarcity_bucket_support",
                comp_lane_signature=target_lane_signature,
            )
        notes_parts.append(
            f"Too few quality comps after filtering (accepted={accepted_n}, need>={MIN_ACCEPTED_COMPS})."
        )
        if pool_kind == "sold_finding":
            notes_parts.append("Pool: sold (Finding API).")
        else:
            notes_parts.append(
                "Pool: active listings (auction+BIN). Add EBAY_FINDING_APP_ID for sold comps."
            )
        structured_fb = _structured_fallback_estimate(
            profile=profile,
            items=items,
            target_title=title,
            target_item_id=iid,
            target_item_url=item_url,
            target_listing_item=target_listing_item,
            today=today,
        )
        if structured_fb:
            notes_parts.append(str(structured_fb.get("notes") or ""))
            _log_class_support(str(structured_fb.get("confidence") or "low"))
            return _debug_base(
                notes=" ".join(x for x in notes_parts if x).strip(),
                confidence=str(structured_fb.get("confidence") or "low"),
                comp_count=int(structured_fb.get("comp_count") or 0),
                accepted_comp_count=accepted_n,
                last_comp_date=date.today().isoformat(),
                value=float(structured_fb.get("value_mid") or 0.0),
                value_low=float(structured_fb.get("value_low") or 0.0),
                value_high=float(structured_fb.get("value_high") or 0.0),
                dominant_range_low=float(structured_fb.get("value_low") or 0.0),
                dominant_range_high=float(structured_fb.get("value_high") or 0.0),
                dominant_comp_count=int(structured_fb.get("anchor_count") or 0),
                market_lane_low=float(structured_fb.get("value_low") or 0.0),
                market_lane_high=float(structured_fb.get("value_high") or 0.0),
                market_lane_comp_count=int(structured_fb.get("anchor_count") or 0),
                market_lane_recent_count=0,
                market_lane_method=str(structured_fb.get("market_lane_method") or "inferred_structured_fallback"),
                market_lane_strength=0.24,
                market_value_source=str(structured_fb.get("market_value_source") or "structured_fallback"),
                cluster_method=str(structured_fb.get("market_lane_method") or "inferred_structured_fallback"),
                valuation_basis=str(structured_fb.get("valuation_basis") or "structured_fallback_inferred"),
                manual_review_audit=(
                    f"rej={manual_reject_hits} boost={man_ap_boost} learn={'y' if learned_skewed else 'n'}"
                ),
                valuation_flow_label=str(structured_fb.get("valuation_flow_label") or "structured_fallback"),
                debug_accepted_comps_json="[]",
                valuation_failure_reason="",
                valuation_final_status=str(structured_fb.get("valuation_final_status") or "fallback_estimate_published"),
                debug_confidence_rationale=(
                    f"structured_fallback; anchor={structured_fb.get('anchor_type')}; "
                    f"anchors={int(structured_fb.get('anchor_count') or 0)}; no_direct_comps"
                ),
                debug_valuation_pipeline_json=_pipeline_blob("fallback_estimate_published", ""),
                mv_pool_mode="structured_fallback",
                mv_strict_comp_count=0,
                mv_relaxed_comp_count=0,
                mv_strict_lane_comp_count=0,
                mv_relaxed_fallback_used=True,
                mv_fallback_reason=str(structured_fb.get("anchor_type") or "structured_fallback"),
                comp_lane_label=str(structured_fb.get("comp_lane_label") or target_lane_signature),
                comp_lane_status=str(structured_fb.get("comp_lane_status") or "fallback_family_only"),
                comp_lane_warning=str(structured_fb.get("comp_lane_warning") or ""),
                comp_lane_signature=str(structured_fb.get("comp_lane_signature") or target_lane_signature),
            )
        _log_class_support("estimate_only")
        return _debug_base(
            notes=" ".join(notes_parts).strip(),
            confidence="estimate_only",
            comp_count=0,
            last_comp_date=date.today().isoformat(),
            market_value_source="none",
            cluster_method="none",
            valuation_basis="insufficient_comps",
            manual_review_audit=(
                f"rej={manual_reject_hits} boost={man_ap_boost} learn={'y' if learned_skewed else 'n'}"
            ),
            valuation_flow_label="auto",
            debug_accepted_comps_json="[]",
            valuation_failure_reason=insuf_reason,
            valuation_final_status="no_estimate",
            debug_valuation_pipeline_json=_pipeline_blob("no_estimate", insuf_reason),
        )

    raw_prices = [c.price for c in accepted_comps]
    full_lo = round(min(raw_prices), 2)
    full_hi = round(max(raw_prices), 2)
    n = len(raw_prices)
    med_all = _simple_median(raw_prices)

    if radar_trace:
        print("[RADAR][MV] step=cluster:start (internal)")
    pick = select_market_lane(accepted_comps, pool_kind, today)
    lane_list = [c for c in accepted_comps if c.idx in pick.lane_indices]
    if radar_trace:
        print(f"[RADAR][MV] step=cluster:done (internal) lane_n={len(lane_list)}")
    _lane_med_prices = [c.price for c in accepted_comps if c.idx in pick.pool_indices]
    med_lane_pool = _simple_median(_lane_med_prices) if _lane_med_prices else med_all
    rel_lane = (pick.hi - pick.lo) / max(med_lane_pool, 1e-6)
    wide_lane = n >= 5 and rel_lane > 0.68
    n7 = sum(1 for c in accepted_comps if c.recency_bucket == "7d")
    n30 = sum(1 for c in accepted_comps if c.recency_bucket in ("7d", "30d"))
    if pool_kind == "active_browse":
        n7 = 0
        n30 = n

    auction_comp_count = sum(
        1 for c in accepted_comps if c.sale_type in ("auction", "auction_or_bin")
    )
    fixed_price_comp_count = sum(
        1 for c in accepted_comps if c.sale_type in ("fixed_price", "fixed_or_offer")
    )
    exact_grade_comp_count = sum(1 for c in accepted_comps if c.gb_reason == "exact_grade")
    fallback_grade_comp_count = sum(
        1 for c in accepted_comps if c.gb_reason == "adjacent_grade" or c.grade_fallback
    )
    grade_fallback_used = any(c.grade_fallback for c in accepted_comps)

    _, _, mv_strict_n, mv_relaxed_n = resolve_mv_value_pools(accepted_comps)

    used_fallback = False
    fallback_reason = ""
    valuation_method = pick.method
    point: Optional[float] = None
    lane_weights: Dict[int, float] = {}
    median_relaxed = False
    median_relaxed_reason = ""

    if radar_trace:
        print("[RADAR][MV] step=scoring:start (internal)")
    if n <= 3:
        used_fallback = True
        fallback_reason = "small_n"
        valuation_method = "fallback_trimmed_weighted_median_strict_first"
        point, _, _, median_relaxed, median_relaxed_reason = _fallback_trimmed_weighted_median_strict_first(
            accepted_comps
        )
    elif wide_lane:
        used_fallback = True
        fallback_reason = "wide_lane_scatter"
        valuation_method = "fallback_trimmed_weighted_median_strict_first"
        point, _, _, median_relaxed, median_relaxed_reason = _fallback_trimmed_weighted_median_strict_first(
            accepted_comps
        )
    else:
        point, lane_weights = compute_lane_market_value(lane_list, accepted_n7=n7)
        if point is None:
            used_fallback = True
            fallback_reason = "lane_empty"
            valuation_method = "fallback_trimmed_weighted_median_strict_first"
            (
                point,
                _,
                _,
                median_relaxed,
                median_relaxed_reason,
            ) = _fallback_trimmed_weighted_median_strict_first(accepted_comps)

    if radar_trace:
        print(f"[RADAR][MV] step=scoring:done (internal) point={point!r}")

    lane_recent_ct = sum(
        1
        for c in lane_list
        if c.recency_bucket in ("7d", "30d", "active_proxy")
    )
    valuation_sale_mode = _lane_valuation_sale_mode(lane_list)
    auction_in_lane = sum(
        1 for c in lane_list if c.sale_type in ("auction", "auction_or_bin")
    )
    lane_n = len(lane_list)
    weak_lane_frac = lane_weaker_tier_weight_fraction(lane_list)
    cond_lane_n = sum(
        1
        for c in lane_list
        if (c.condition_flags or "").strip() and getattr(c, "condition_penalty_mult", 1.0) < 0.95
    )

    mv_relaxed_fallback_used = bool(
        getattr(pick, "lane_relaxed_beyond_strict", False) or median_relaxed
    )
    mv_fallback_fr_parts: List[str] = []
    if pick.mv_lane_pool_relax_reason:
        mv_fallback_fr_parts.append(f"lane:{pick.mv_lane_pool_relax_reason}")
    if median_relaxed_reason:
        mv_fallback_fr_parts.append(f"median:{median_relaxed_reason}")
    if used_fallback and fallback_reason:
        mv_fallback_fr_parts.append(f"fb:{fallback_reason}")
    mv_fallback_reason = ";".join(mv_fallback_fr_parts)[:220]
    if mv_strict_n == 0:
        mv_pool_mode = "relaxed_only"
    elif mv_relaxed_fallback_used:
        mv_pool_mode = "strict_with_relaxed_fallback"
    else:
        mv_pool_mode = "strict_only"
    mv_strict_lane_comp_count = sum(
        1 for c in lane_list if getattr(c, "counts_toward_value", True)
    )

    if point is None:
        lane_dbg_none = build_lane_debug_report(
            accepted_comps,
            pick,
            n7,
            n30,
            valuation_method,
            None,
            lane_weights=lane_weights,
            valuation_sale_mode=valuation_sale_mode,
            auction_n=auction_comp_count,
            fixed_n=fixed_price_comp_count,
            exact_grade_n=exact_grade_comp_count,
            fallback_grade_n=fallback_grade_comp_count,
            confidence_rationale="no_numeric_point",
        )
        audit_none = _build_valuation_audit_header(
            valuation_strength="no_reliable_value",
            downgrade_reasons=["no_numeric_point"],
            canonical_key=audit_canonical_key,
            profile_summary=audit_profile_summary,
            valuation_sale_mode=valuation_sale_mode,
            exact_grade_n=exact_grade_comp_count,
            fallback_grade_n=fallback_grade_comp_count,
            tier_counts_map=tier_cnt_map,
            n7=n7,
            n30=n30,
            dup_suppressed=dup_suppressed_n,
            cond_issues_accepted=cond_issues_acc,
            cond_issues_lane=cond_lane_n,
            lane_breakdown=getattr(pick, "lane_score_breakdown", "") or "",
            weak_lane_frac=weak_lane_frac,
            confidence="estimate_only",
            confidence_rationale="no_numeric_point",
            visual_summary=visual_summary,
            result_mv=None,
            withheld_mv=None,
            manual_audit_line=(
                f"canonical={man_key[:72] if man_key else '—'} | "
                f"rej={manual_reject_hits} boost={man_ap_boost} learn={'y' if learned_skewed else 'n'}"
            ),
        )
        _log_class_support("estimate_only")
        return _debug_base(
            notes="Could not compute market value from comps.",
            confidence="estimate_only",
            comp_count=0,
            last_comp_date=date.today().isoformat(),
            market_value_source="none",
            dominant_range_low=round(pick.lo, 2),
            dominant_range_high=round(pick.hi, 2),
            dominant_comp_count=len(pick.lane_indices),
            cluster_strength=pick.strength,
            cluster_method=valuation_method,
            valuation_basis="error",
            accepted_comp_count=n,
            full_comp_price_low=full_lo,
            full_comp_price_high=full_hi,
            market_lane_low=round(pick.lo, 2),
            market_lane_high=round(pick.hi, 2),
            market_lane_comp_count=len(pick.lane_indices),
            market_lane_recent_count=lane_recent_ct,
            market_lane_method=valuation_method,
            market_lane_strength=pick.strength,
            recent_comp_count_7d=n7,
            recent_comp_count_30d=n30,
            valuation_sale_mode=valuation_sale_mode,
            auction_comp_count=auction_comp_count,
            fixed_price_comp_count=fixed_price_comp_count,
            exact_grade_comp_count=exact_grade_comp_count,
            fallback_grade_comp_count=fallback_grade_comp_count,
            grade_fallback_used=grade_fallback_used,
            debug_lane_detail=audit_none + "\n" + lane_dbg_none,
            debug_audit_panel=audit_none,
            debug_comp_detail_only=lane_dbg_none,
            debug_audit_summary=(
                f"sale_mode={valuation_sale_mode} | auc={auction_comp_count} "
                f"fp={fixed_price_comp_count} | exact_g={exact_grade_comp_count} "
                f"fb_g={fallback_grade_comp_count}"
            ),
            valuation_strength="no_reliable_value",
            valuation_downgrade_reasons="no_numeric_point",
            duplicate_suppressed_count=dup_suppressed_n,
            condition_issue_accepted_count=cond_issues_acc,
            condition_issue_lane_count=cond_lane_n,
            exactness_tier_counts=str(tier_cnt_map),
            debug_visual_verification_summary=visual_summary,
            debug_accepted_comps_json=_build_accepted_comps_snapshot_json(
                accepted_comps,
                comp_items,
                pick,
                target_title=title,
                target_item_id=iid,
            ),
            manual_review_audit=(
                f"rej={manual_reject_hits} boost={man_ap_boost} learn={'y' if learned_skewed else 'n'}"
            ),
            valuation_flow_label="auto",
            valuation_failure_reason="lane_or_median_compute_failed",
            valuation_final_status="no_estimate",
            comps_lane_selected_count=len(pick.lane_indices),
            mv_pool_mode="no_reliable_value",
            mv_strict_comp_count=mv_strict_n,
            mv_relaxed_comp_count=mv_relaxed_n,
            mv_strict_lane_comp_count=mv_strict_lane_comp_count,
            mv_relaxed_fallback_used=mv_relaxed_fallback_used,
            mv_fallback_reason=mv_fallback_reason,
            debug_valuation_pipeline_json=_pipeline_blob(
                "no_estimate",
                "lane_or_median_compute_failed",
                lane_n=len(pick.lane_indices),
                strength_label="no_reliable_value",
                mv_pool_mode="no_reliable_value",
                mv_strict_comp_count=mv_strict_n,
                mv_relaxed_comp_count=mv_relaxed_n,
                mv_strict_lane_comp_count=mv_strict_lane_comp_count,
                mv_relaxed_fallback_used=mv_relaxed_fallback_used,
                mv_fallback_reason=mv_fallback_reason,
            ),
        )

    if pool_kind == "sold_finding":
        tier_name = "ebay_sold_proxy"
        mv_source = "hybrid_ebay_sold"
        notes_parts.append("Comps: eBay sold (Finding API).")
    else:
        tier_name = "ebay_active_proxy"
        mv_source = "hybrid_ebay_active"
        notes_parts.append(
            "Comps: active listings (not sold). Set EBAY_FINDING_APP_ID for sold results."
        )

    if cross_grade_used:
        tier_name = "ebay_cross_grade_proxy"
        notes_parts.append("Cross-grade only — verify with Card Ladder or exact-grade solds.")

    if used_fallback:
        notes_parts.append(
            f"MV pricing: {valuation_method} (fallback={fallback_reason}) — "
            f"lane window ${pick.lo:.2f}–${pick.hi:.2f} ({len(pick.lane_indices)}/{n} comps in lane)."
        )
        valuation_basis = f"fallback:{fallback_reason or valuation_method}"
    else:
        notes_parts.append(
            f"MV pricing: market lane ${pick.lo:.2f}–${pick.hi:.2f} "
            f"({len(pick.lane_indices)} comps, strength={pick.strength:.2f}, "
            f"recent7/30 accepted={n7}/{n30})."
        )
        valuation_basis = "market_lane_trimmed_weighted_median"

    if valuation_sale_mode == "fixed_price_lane":
        notes_parts.append("Sale-type lane: mostly fixed-price/BIN (auction comps thin).")
    elif valuation_sale_mode == "blended":
        notes_parts.append("Sale-type lane: auction + fixed-price blended.")
    if grade_fallback_used:
        notes_parts.append("PSA adjacent-grade comps included (downweighted).")
    if mv_relaxed_fallback_used:
        notes_parts.append(
            f"MV pool: strict={mv_strict_n} value-eligible comps; "
            f"relaxed_accepted={mv_relaxed_n}; fallback trace: {mv_fallback_reason[:160]}"
        )
    notes_parts.append(f"Comp lane: {target_lane_signature or 'unresolved card lane'}.")
    if _lane_contaminated:
        notes_parts.append(
            "Comp lane contaminated — "
            + (_lane_contam_reason or "mixed identity families").replace("_", " ")
            + (f" ({_lane_contam_summary})" if _lane_contam_summary else "")
            + "."
        )
    elif comp_lane_status == "near_lane_only":
        notes_parts.append("Comp lane: near-lane fallback only.")
    elif comp_lane_status == "premium_support_lane":
        notes_parts.append("Comp lane: premium support expansion.")
    elif comp_lane_status == "fallback_family_only":
        notes_parts.append("Comp lane: fallback family only.")
    else:
        notes_parts.append("Comp lane: strict lane match.")

    conf, confidence_rationale = _confidence_from_market_lane(
        n,
        pick,
        rel_lane,
        cross_grade_used,
        used_fallback,
        fallback_reason,
        n7,
        n30,
        exact_grade_n=exact_grade_comp_count,
        grade_fallback_used=grade_fallback_used,
        valuation_sale_mode=valuation_sale_mode,
        auction_in_lane=auction_in_lane,
        lane_n=lane_n,
        weak_lane_frac=weak_lane_frac,
        dup_downgraded=dup_suppressed_n,
        cond_issues_accepted=cond_issues_acc,
        cond_issues_lane=cond_lane_n,
        mv_relaxed_beyond_strict=mv_relaxed_fallback_used,
        strict_comp_count=mv_strict_n,
        mv_pool_mode=mv_pool_mode,
    )
    conf = _cap_confidence_for_relaxed_mv_pool(conf, mv_pool_mode, mv_relaxed_fallback_used)
    if _lane_contaminated:
        if conf == "high":
            conf = "low"
        elif conf == "medium":
            conf = "low"
        else:
            conf = "estimate_only"
        confidence_rationale = (
            f"{confidence_rationale};comp_lane_contaminated:{_lane_contam_reason}"
            if confidence_rationale
            else f"comp_lane_contaminated:{_lane_contam_reason}"
        )

    strength, downgrade_reasons = _decide_valuation_strength(
        point,
        n,
        lane_list,
        pick,
        dup_suppressed_n,
        cond_issues_acc,
        weak_lane_frac,
        rel_lane,
        used_fallback,
        grade_fallback_used,
        cross_grade_used,
        cond_lane_n,
        mv_relaxed_beyond_strict=mv_relaxed_fallback_used,
        strict_comp_count=mv_strict_n,
    )
    if _lane_contaminated:
        downgrade_reasons = list(downgrade_reasons) + [
            f"contaminated_comp_lane:{_lane_contam_reason}"
        ]
        if mv_strict_n < 2 or _lane_contam_reason in ("subset_family_mixed", "card_number_family_mixed"):
            strength = "no_reliable_value"
        elif strength == "strong_market_value":
            strength = "provisional_estimate"

    withheld_mv: Optional[float] = None
    pub_point: Optional[float] = point
    custom_range_lo: Optional[float] = None
    custom_range_hi: Optional[float] = None
    if strength == "no_reliable_value":
        withheld_mv = point
        pub_point = None
        conf = "estimate_only"
        confidence_rationale = (
            f"withheld_no_reliable_value;{confidence_rationale};"
            + ",".join(downgrade_reasons)
        )
        notes_parts.insert(
            0,
            "No reliable market value published — comp pool failed quality gates. "
            + "; ".join(downgrade_reasons),
        )
    elif strength == "provisional_estimate":
        if conf == "high":
            conf = "medium"
        elif conf == "medium" and len(downgrade_reasons) >= 2:
            conf = "low"
        gate_note = "provisional_gate:" + ",".join(downgrade_reasons)
        confidence_rationale = (
            f"{confidence_rationale};{gate_note}" if confidence_rationale else gate_note
        )
        notes_parts.append(
            "Valuation strength: provisional_estimate — " + "; ".join(downgrade_reasons)
            if downgrade_reasons
            else "Valuation strength: provisional_estimate (mixed comp context)."
        )
    else:
        notes_parts.append(
            "Valuation strength: strong_market_value (within internal gates)."
        )

    flow_label = "auto"
    mra_core = (
        f"reject_drops={manual_reject_hits} approve_boost={man_ap_boost} "
        f"learned_skew={'y' if learned_skewed else 'n'} decisions_saved={len(decisions)}"
    )
    if manual_reject_hits or man_ap_boost or learned_skewed:
        flow_label = "auto_with_manual_comp_influence"

    man_cfg = manual_comp_review.get_manual_mv_config(man_state, man_key)
    mv_over = _safe_float(man_cfg.get("manual_value"))
    if man_key and man_cfg.get("use_manual_mv") and mv_over and mv_over > 0:
        pub_point = mv_over
        withheld_mv = None
        custom_range_lo = _safe_float(man_cfg.get("manual_low"))
        custom_range_hi = _safe_float(man_cfg.get("manual_high"))
        conf = "manual_override"
        strength = "strong_market_value"
        confidence_rationale = (
            (confidence_rationale + ";manual_canonical_mv_override")
            if confidence_rationale
            else "manual_canonical_mv_override"
        )
        flow_label = "manual_mv_override"
        notes_parts.insert(0, "Manual canonical MV override is active.")

    serial_lane_summary: Dict[str, Any] = {}
    serial_source_override = ""
    if flow_label != "manual_mv_override":
        serial_lane_summary = _summarize_premium_serial_lane(
            title,
            accepted_comps,
            item_id=iid,
        )
        if pub_point is not None and pub_point > 0 and bool(serial_lane_summary.get("is_premium_serial")):
            _target_serial = str(serial_lane_summary.get("target_serial") or "").strip()
            _exact_same_denominator = int(serial_lane_summary.get("exact_same_denominator_count") or 0)
            _cross_serial = int(serial_lane_summary.get("cross_serial_count") or 0)
            _exact_anchor = _safe_float(serial_lane_summary.get("exact_anchor_value"))
            if _exact_same_denominator > 0 and _exact_anchor and _exact_anchor > 0:
                _old_pub_point = round(float(pub_point), 2)
                _old_source = str(mv_source or "").strip() or "none"
                pub_point = round(float(_exact_anchor), 2)
                point = pub_point
                _exact_lo = _safe_float(serial_lane_summary.get("exact_anchor_low"))
                _exact_hi = _safe_float(serial_lane_summary.get("exact_anchor_high"))
                if _exact_lo is not None and _exact_hi is not None and _exact_lo > 0 and _exact_hi > 0:
                    custom_range_lo = round(min(_exact_lo, _exact_hi), 2)
                    custom_range_hi = round(max(_exact_lo, _exact_hi), 2)
                serial_source_override = "exact_comp_engine"
                valuation_basis = "exact_serial_denominator_anchor"
                notes_parts.append(
                    f"Serial lane anchor: exact /{_target_serial} comp support kept before cross-serial family support "
                    f"(exact={_exact_same_denominator}, cross_rejected={_cross_serial})."
                )
                if abs(_old_pub_point - pub_point) >= 0.01 or serial_source_override != _old_source:
                    print(
                        f"[HERO_MV_REANCHOR] item={iid[:24] or '?'} target_serial=/{_target_serial} "
                        f"old_mv={_old_pub_point} new_mv={pub_point} old_source={_old_source} "
                        f"new_source={serial_source_override} exact_same_denominator={_exact_same_denominator} "
                        f"cross_serial_rejected={_cross_serial}"
                    )
            elif _cross_serial > 0:
                _discount = _safe_float(serial_lane_summary.get("cross_serial_discount_factor")) or 0.78
                _old_pub_point = round(float(pub_point), 2)
                _cross_conservative = _safe_float(serial_lane_summary.get("cross_serial_conservative_value"))
                if _cross_conservative and _cross_conservative > 0:
                    pub_point = round(min(float(pub_point), float(_cross_conservative)), 2)
                    point = pub_point
                _cross_lo = _safe_float(serial_lane_summary.get("cross_anchor_low"))
                _cross_hi = _safe_float(serial_lane_summary.get("cross_anchor_high"))
                if _cross_lo is not None and _cross_hi is not None and _cross_lo > 0 and _cross_hi > 0:
                    custom_range_lo = round(min(_cross_lo, _cross_hi) * float(_discount), 2)
                    custom_range_hi = round(max(_cross_lo, _cross_hi) * float(_discount), 2)
                serial_source_override = "hybrid_near_lane"
                if strength == "strong_market_value":
                    strength = "provisional_estimate"
                if conf == "high":
                    conf = "medium"
                elif conf == "medium":
                    conf = "low"
                _gate_note = f"cross_serial_discount:{float(_discount):.2f}"
                confidence_rationale = (
                    f"{confidence_rationale};{_gate_note}" if confidence_rationale else _gate_note
                )
                valuation_basis = "cross_serial_discounted_review"
                notes_parts.append(
                    f"Serial lane anchor: cross-serial support only - discounted x{float(_discount):.2f} "
                    "and blocked from hero-grade TRUE promotion."
                )
                print(
                    f"[HERO_MV_REANCHOR] item={iid[:24] or '?'} target_serial=/{_target_serial or '?'} "
                    f"old_mv={_old_pub_point} new_mv={round(pub_point, 2) if pub_point is not None else None} "
                    f"old_source={str(mv_source or '').strip() or 'none'} new_source={serial_source_override} "
                    f"reason=cross_serial_only discount={float(_discount):.2f}"
                )

    exact_true_mv_payload = _build_exact_true_mv_payload(title, accepted_comps)
    _exact_comp_count = int(exact_true_mv_payload.get("exact_comp_count") or 0)
    _exact_comp_median = _safe_float(exact_true_mv_payload.get("exact_median"))
    if flow_label != "manual_mv_override" and _exact_comp_count >= 2 and _exact_comp_median and _exact_comp_median > 0:
        pub_point = round(float(_exact_comp_median), 2)
        point = pub_point
        withheld_mv = None
        strength = "strong_market_value"
        if conf == "estimate_only":
            conf = "medium"
        notes_parts = [
            _note
            for _note in notes_parts
            if not str(_note).startswith("No reliable market value published")
            and not str(_note).startswith("Valuation strength:")
        ]
        _exact_lo = _safe_float(exact_true_mv_payload.get("exact_range_low"))
        _exact_hi = _safe_float(exact_true_mv_payload.get("exact_range_high"))
        if _exact_lo is not None and _exact_hi is not None and _exact_lo > 0 and _exact_hi > 0:
            custom_range_lo = round(min(_exact_lo, _exact_hi), 2)
            custom_range_hi = round(max(_exact_lo, _exact_hi), 2)
        serial_source_override = "exact_comp_engine"
        valuation_basis = "exact_comp_engine"
        notes_parts.append("Valuation strength: strong_market_value (exact comp lane only).")
        notes_parts.append(
            f"TRUE MV anchored only from exact comp lane matches (exact_used={_exact_comp_count})."
        )
    print(
        f"[MV_COMP_USED] item={iid[:24] or '?'} count={_exact_comp_count} "
        f"median={round(float(_exact_comp_median), 2) if _exact_comp_median is not None else None}"
    )
    print(
        f"[MV_COMP_REJECTED] item={iid[:24] or '?'} count={int(exact_true_mv_payload.get('rejected_count') or 0)} "
        f"reasons={exact_true_mv_payload.get('rejected_reason_counts') or {}}"
    )
    _support_truth_source_override = ""
    if _exact_comp_count == 0:
        if _support_ok and support_comp_count >= 1:
            _support_prices = sorted(
                float(getattr(c, "price"))
                for c in _support_comps
                if _safe_float(getattr(c, "price", None)) is not None and float(getattr(c, "price")) > 0
            )
            if _support_prices:
                _mid = len(_support_prices) // 2
                _support_mv = (
                    _support_prices[_mid]
                    if len(_support_prices) % 2 == 1
                    else (_support_prices[_mid - 1] + _support_prices[_mid]) / 2.0
                )
                if pub_point is not None and pub_point > 0:
                    _support_mv = min(float(_support_mv), float(pub_point))
                pub_point = round(float(_support_mv), 2)
                point = pub_point
                _support_truth_source_override = "support_comp_engine"
                if strength == "no_reliable_value":
                    strength = "provisional_estimate"
                if conf == "estimate_only":
                    conf = "low"
                valuation_basis = "support_comp_engine"
                notes_parts.append(
                    f"TRUE MV promoted from clean support comp lane (support_count={len(_support_comps)})."
                )
                print(
                    f"[SUPPORT_TRUTH_PROMOTE] title={title[:140]} "
                    f"support_count={len(_support_comps)} "
                    f"true_mv={pub_point} "
                    f"reason=clean_support_lane"
                )
            else:
                print(
                    f"[SUPPORT_TRUTH_REJECT] title={title[:140]} "
                    f"reason=no_numeric_support_prices"
                )
        else:
            print(
                f"[SUPPORT_TRUTH_REJECT] title={title[:140]} "
                f"reason={_support_reason}"
            )

    comp_snap_json = _build_accepted_comps_snapshot_json(
        accepted_comps,
        comp_items,
        pick,
        target_title=title,
        target_item_id=iid,
    )
    manual_audit_line = (
        f"canonical={man_key[:72] if man_key else '—'} | {mra_core} | flow={flow_label}"
    )
    manual_review_audit_full = manual_audit_line

    lw_for_debug = lane_weights if not used_fallback else {}
    lane_debug = build_lane_debug_report(
        accepted_comps,
        pick,
        n7,
        n30,
        valuation_method,
        point,
        lane_weights=lw_for_debug,
        valuation_sale_mode=valuation_sale_mode,
        auction_n=auction_comp_count,
        fixed_n=fixed_price_comp_count,
        exact_grade_n=exact_grade_comp_count,
        fallback_grade_n=fallback_grade_comp_count,
        confidence_rationale=confidence_rationale,
    )
    audit_hdr = _build_valuation_audit_header(
        valuation_strength=strength,
        downgrade_reasons=downgrade_reasons,
        canonical_key=audit_canonical_key,
        profile_summary=audit_profile_summary,
        valuation_sale_mode=valuation_sale_mode,
        exact_grade_n=exact_grade_comp_count,
        fallback_grade_n=fallback_grade_comp_count,
        tier_counts_map=tier_cnt_map,
        n7=n7,
        n30=n30,
        dup_suppressed=dup_suppressed_n,
        cond_issues_accepted=cond_issues_acc,
        cond_issues_lane=cond_lane_n,
        lane_breakdown=getattr(pick, "lane_score_breakdown", "") or "",
        weak_lane_frac=weak_lane_frac,
        confidence=conf,
        confidence_rationale=confidence_rationale,
        visual_summary=visual_summary,
        result_mv=pub_point,
        withheld_mv=withheld_mv,
        manual_audit_line=manual_audit_line,
    )
    full_lane_debug = audit_hdr + "\n" + lane_debug
    debug_audit_summary = (
        f"strength={strength} | sale_mode={valuation_sale_mode} | "
        f"auc={auction_comp_count} fp={fixed_price_comp_count} | "
        f"exact_g={exact_grade_comp_count} fb_g={fallback_grade_comp_count} | "
        f"grade_fb={'y' if grade_fallback_used else 'n'} | dups={dup_suppressed_n} | "
        f"basis={valuation_basis} | conf={conf} | {confidence_rationale}"
    )

    if ctx_psa:
        notes_parts.append(f"Listing PSA context: {ctx_psa}.")

    if pub_point is not None:
        pub_lo = (
            custom_range_lo
            if custom_range_lo is not None
            else full_lo
        )
        pub_hi = (
            custom_range_hi
            if custom_range_hi is not None
            else full_hi
        )
    else:
        pub_lo = None
        pub_hi = None

    if pub_point is not None and pub_point > 0:
        if strength == "strong_market_value":
            final_status = "published_strong"
        elif strength == "provisional_estimate":
            final_status = "published_provisional"
        else:
            final_status = "published_provisional"
        fail_reason = ""
    else:
        if strength == "no_reliable_value":
            final_status = "withheld_no_reliable_value"
            fail_reason = ";".join(downgrade_reasons) if downgrade_reasons else "quality_withhold"
        else:
            final_status = "no_estimate"
            fail_reason = ";".join(downgrade_reasons) if downgrade_reasons else "no_numeric_output"

    mv_pool_mode_out = mv_pool_mode
    if pub_point is None and strength == "no_reliable_value":
        mv_pool_mode_out = "no_reliable_value"

    succ_pipeline = _pipeline_blob(
        final_status,
        fail_reason,
        lane_n=lane_n,
        strength_label=strength,
        mv_pool_mode=mv_pool_mode_out,
        mv_strict_comp_count=mv_strict_n,
        mv_relaxed_comp_count=mv_relaxed_n,
        mv_strict_lane_comp_count=mv_strict_lane_comp_count,
        mv_relaxed_fallback_used=mv_relaxed_fallback_used,
        mv_fallback_reason=mv_fallback_reason,
        comp_lane_label=target_lane_signature,
        comp_lane_status=comp_lane_status,
        comp_lane_warning=comp_lane_warning,
        comp_lane_signature=target_lane_signature,
    )

    _res_mv_source = (
        "manual_canonical_override"
        if flow_label == "manual_mv_override"
        else (
            _support_truth_source_override
            or (serial_source_override or mv_source)
            if pub_point else "none"
        )
    )
    if not serial_source_override and pub_point and accepted_n == 1 and comp_lane_status == "near_lane_only" and _is_high_end_premium_title(title):
        _res_mv_source = "near_family_support"
    print(
        f"[SUPPORT_COUNT_FINAL] title={title[:140]} "
        f"support_comp_count={support_comp_count} "
        f"support_input_count={len(list(_support_comps or []))}"
    )
    if len(list(_support_comps or [])) > 0 and support_comp_count == 0:
        support_comp_count = len(list(_support_comps or []))
        print(
            f"[SUPPORT_COUNT_REPAIRED] title={title[:140]} "
            f"repaired_support_comp_count={support_comp_count}"
        )
    _true_mv_out, _review_mv_out, _truth_tier_out = _split_truth_market_value(
        title=title,
        value=pub_point,
        source=_res_mv_source,
        accepted_count=accepted_n,
        comp_lane_status=comp_lane_status,
        confidence=conf,
        comp_lane_warning=comp_lane_warning,
        serial_lane_summary=serial_lane_summary,
        exact_comp_count=_exact_comp_count,
        exact_comp_value=_exact_comp_median,
    )
    _publish_contract = _enforce_true_mv_contract(
        title=title,
        stage="publish",
        truth=_truth_tier_out,
        source=_res_mv_source,
        exact_comp_count=_exact_comp_count,
        true_mv=_true_mv_out,
        review_estimate=_review_mv_out,
        published_value=pub_point,
    )
    _true_mv_out = _publish_contract.get("true_mv")
    _review_mv_out = _publish_contract.get("review_estimate")
    _truth_tier_out = str(_publish_contract.get("truth") or _truth_tier_out or "NONE").upper()
    _current_price_for_clone = _safe_float(
        target_row_for_class.get("current_price")
        or target_row_for_class.get("current")
        or target_row_for_class.get("price")
    )
    if _is_single_comp_clone_case(_current_price_for_clone, _true_mv_out, _exact_comp_count):
        print(
            f"[SINGLE_COMP_CLONE_BLOCK] title={title[:140]} "
            f"current={_current_price_for_clone} true_mv={_true_mv_out} "
            f"trusted_exact={_exact_comp_count}"
        )
        # [MV_ECHO_TRACE] — surface the comp source(s) that produced the
        # contaminated MV. Tells us conclusively whether this is:
        #   (a) a legitimate thin-comp situation (1 historical sale that
        #       happens to match current — engine correctly demotes to WATCH)
        #   (b) self-reference contamination (the listing's own price is
        #       being used as a comp — bug; needs filter at comp ingest)
        #   (c) active-listing misclassified as sold (different bug class)
        # Compare the iid below against the current listing's iid; if they
        # match, that's case (b). If sold_iso is empty / future, that's (c).
        try:
            _trusted_for_log = list(_trusted_exact_comps or [])
            _comp_summaries: List[str] = []
            for _c in _trusted_for_log[:3]:
                _c_price = float(getattr(_c, "price", 0.0) or 0.0)
                _c_iid = str(
                    getattr(_c, "item_id", "")
                    or getattr(_c, "iid", "")
                    or getattr(_c, "listing_id", "")
                    or ""
                )[:24]
                _c_sold = str(
                    getattr(_c, "sold_iso", "")
                    or getattr(_c, "end_iso", "")
                    or getattr(_c, "sale_date", "")
                    or ""
                )[:24]
                _c_seller = str(
                    getattr(_c, "seller", "")
                    or getattr(_c, "seller_username", "")
                    or ""
                )[:32]
                _comp_summaries.append(
                    f"price={_c_price}|iid={_c_iid}|sold={_c_sold}|seller={_c_seller}"
                )
            try:
                _delta_pct = round(
                    abs(float(_true_mv_out or 0) - float(_current_price_for_clone or 0))
                    / max(float(_current_price_for_clone or 1), 1.0)
                    * 100.0,
                    2,
                )
            except Exception:
                _delta_pct = -1.0
            print(
                f"[MV_ECHO_TRACE] title={title[:120]} "
                f"current={_current_price_for_clone} true_mv={_true_mv_out} "
                f"delta_pct={_delta_pct} "
                f"trusted_exact={_exact_comp_count} "
                f"comps={_comp_summaries}"
            )
        except Exception as _met_exc:
            print(f"[MV_ECHO_TRACE] error_type={type(_met_exc).__name__} msg={str(_met_exc)[:120]}")
        _publish_contract["single_comp_clone_block"] = True
    else:
        _publish_contract["single_comp_clone_block"] = False
    _single_comp_clone_block = bool(_publish_contract.get("single_comp_clone_block"))
    print(
        f"[MV_PUBLISH_TRACE] title={title[:140]} truth={_truth_tier_out} "
        f"source={_res_mv_source or 'none'} true_mv={_true_mv_out} review_estimate={_review_mv_out} "
        f"exact_comp_count={_exact_comp_count} valuation_contract_version={TRUE_MV_CONTRACT_VERSION}"
    )
    print(f"[MV][RESOLUTION] item={iid[:24]} lane={mv_pool_mode_out} mv={round(pub_point, 2) if pub_point else None} conf={conf} comps={n if pub_point else 0} source={_res_mv_source}")
    print(
        f"[MV_SPLIT] title={title[:120]} true_mv={_true_mv_out} review_estimate={_review_mv_out} "
        f"source={_res_mv_source} comps={accepted_n}"
    )
    _log_class_support(conf)
    return HybridValuation(
        value=pub_point,
        true_market_value=_true_mv_out,
        review_estimate_value=_review_mv_out,
        value_low=pub_lo,
        value_high=pub_hi,
        tier=tier_name,
        market_value_source=(
            "manual_canonical_override"
            if flow_label == "manual_mv_override"
            else _res_mv_source
        ),
        valuation_truth_tier=_truth_tier_out,
        confidence=conf,
        comp_count=n if pub_point else 0,
        last_comp_date=date.today().isoformat(),
        notes=" ".join(notes_parts).strip(),
        debug_search_query=query,
        debug_pool_kind=debug_pool_kind,
        debug_fetched_count=fetched,
        debug_accepted_count=n,
        debug_rejections_top=reject_summary,
        debug_comp_trace=comp_trace,
        debug_comp_passes_json=passes_json,
        comp_search_attempted=comp_search_attempted,
        comps_pre_enrich_count=len(accepted_buffer),
        comps_lane_selected_count=lane_n,
        valuation_failure_reason=fail_reason,
        valuation_final_status=final_status,
        debug_valuation_pipeline_json=succ_pipeline,
        debug_lane_detail=full_lane_debug,
        debug_comp_detail_only=lane_debug,
        dominant_range_low=round(pick.lo, 2),
        dominant_range_high=round(pick.hi, 2),
        dominant_comp_count=len(pick.lane_indices),
        cluster_method=valuation_method,
        cluster_strength=pick.strength,
        valuation_basis=valuation_basis if pub_point else "withheld_no_reliable_value",
        accepted_comp_count=n,
        full_comp_price_low=full_lo,
        full_comp_price_high=full_hi,
        market_lane_low=round(pick.lo, 2),
        market_lane_high=round(pick.hi, 2),
        market_lane_comp_count=len(pick.lane_indices),
        market_lane_recent_count=lane_recent_ct,
        market_lane_method=valuation_method,
        market_lane_strength=pick.strength,
        recent_comp_count_7d=n7,
        recent_comp_count_30d=n30,
        valuation_sale_mode=valuation_sale_mode,
        auction_comp_count=auction_comp_count,
        fixed_price_comp_count=fixed_price_comp_count,
        exact_grade_comp_count=exact_grade_comp_count,
        fallback_grade_comp_count=fallback_grade_comp_count,
        grade_fallback_used=grade_fallback_used,
        debug_confidence_rationale=confidence_rationale,
        debug_audit_summary=debug_audit_summary,
        valuation_strength=strength,
        valuation_downgrade_reasons="; ".join(downgrade_reasons),
        duplicate_suppressed_count=dup_suppressed_n,
        condition_issue_accepted_count=cond_issues_acc,
        condition_issue_lane_count=cond_lane_n,
        exactness_tier_counts=str(tier_cnt_map),
        debug_visual_verification_summary=visual_summary,
        debug_audit_panel=audit_hdr,
        debug_accepted_comps_json=comp_snap_json,
        manual_review_audit=manual_review_audit_full,
        valuation_flow_label=flow_label,
        mv_pool_mode=mv_pool_mode_out,
        mv_strict_comp_count=mv_strict_n,
        mv_relaxed_comp_count=mv_relaxed_n,
        mv_strict_lane_comp_count=mv_strict_lane_comp_count,
        mv_relaxed_fallback_used=mv_relaxed_fallback_used,
        mv_fallback_reason=mv_fallback_reason,
        exact_comp_count=_exact_comp_count,
        valuation_contract_version=TRUE_MV_CONTRACT_VERSION,
        valuation_source_module=VALUATION_SOURCE_MODULE,
        valuation_publish_stage=VALUATION_PUBLISH_STAGE,
        valuation_apply_guard=VALUATION_APPLY_GUARD,
        single_comp_clone_block=_single_comp_clone_block,
        comp_evidence={
            "used": list(exact_true_mv_payload.get("used") or []),
            "trusted_exact_comps": [
                _accepted_comp_to_evidence_row(c)
                for c in _trusted_exact_comps
                if _accepted_comp_to_evidence_row(c)
            ],
            "support_comps": [
                _accepted_comp_to_evidence_row(c)
                for c in _support_comps
                if _accepted_comp_to_evidence_row(c)
            ],
            "rejected": list(exact_true_mv_payload.get("rejected") or []),
        },
    )


def apply_hybrid_result_to_watchlist_row(
    row: Dict[str, Any],
    result: HybridValuation,
    *,
    auto_target_enabled: bool,
    target_bid_ratio: float,
    set_timestamp: bool = True,
    update_target_bid: bool = True,
) -> None:
    """Mutate watchlist row dict in place when a numeric value exists."""
    _title = str(row.get("title") or row.get("card_name") or "").strip()
    _pre_true_mv = _safe_float(row.get("true_market_value") or row.get("market_value_true"))
    _pre_truth = str(row.get("_valuation_truth_tier") or row.get("valuation_truth_tier") or "").strip().upper()
    _pre_source = str(row.get("mv_source") or row.get("market_value_source") or row.get("source") or "").strip()
    _pre_exact_count = int(_safe_int(row.get("exact_comp_count"), 0) or 0)
    normalized = _normalize_hybrid_result_for_app(result)
    for k, v in normalized.items():
        row[k] = v
    row["comp_evidence"] = dict(getattr(result, "comp_evidence", {}) or {"used": [], "rejected": []})
    row["exact_comp_count"] = str(int(getattr(result, "exact_comp_count", 0) or 0))
    row["_valuation_contract_version"] = str(getattr(result, "valuation_contract_version", "") or TRUE_MV_CONTRACT_VERSION)
    row["_valuation_source_module"] = str(getattr(result, "valuation_source_module", "") or VALUATION_SOURCE_MODULE)
    row["_valuation_publish_stage"] = str(getattr(result, "valuation_publish_stage", "") or VALUATION_PUBLISH_STAGE)
    row["_valuation_apply_guard"] = str(getattr(result, "valuation_apply_guard", "") or VALUATION_APPLY_GUARD)
    row["single_comp_clone_block"] = "1" if bool(getattr(result, "single_comp_clone_block", False)) else ""
    row["source"] = row.get("mv_source") or row.get("market_value_source") or ""
    row["market_value_true"] = row.get("true_market_value", "")
    row["_valuation_truth_tier"] = row.get("valuation_truth_tier", "")
    _apply_contract = _enforce_true_mv_contract(
        title=_title,
        stage="apply",
        truth=row.get("valuation_truth_tier"),
        source=row.get("mv_source") or row.get("market_value_source"),
        exact_comp_count=int(getattr(result, "exact_comp_count", 0) or 0),
        true_mv=_safe_float(row.get("true_market_value") or row.get("market_value_true")),
        review_estimate=_safe_float(row.get("review_estimate_value")),
        published_value=result.value,
    )
    _final_truth = str(_apply_contract.get("truth") or row.get("valuation_truth_tier") or "NONE").upper()
    _final_true_mv = _safe_float(_apply_contract.get("true_mv"))
    _final_review = _safe_float(_apply_contract.get("review_estimate"))
    row["valuation_truth_tier"] = _final_truth
    row["_valuation_truth_tier"] = _final_truth
    row["true_market_value"] = f"{_final_true_mv:.2f}" if _final_true_mv and _final_true_mv > 0 else ""
    row["market_value_true"] = row["true_market_value"]
    row["market_value"] = row["true_market_value"]
    row["mv_mid"] = row["true_market_value"]
    row["review_estimate_value"] = f"{_final_review:.2f}" if _final_review and _final_review > 0 else ""
    if _apply_contract.get("blocked"):
        row["target_bid_mode"] = "review_estimate" if row["review_estimate_value"] else "none"
        row["bid_ceiling_source"] = "REVIEW_ESTIMATE" if row["review_estimate_value"] else "NONE"
        row["market_value_mode"] = "review_estimate" if row["review_estimate_value"] else "none"
        row["valuation_mode"] = row["market_value_mode"]
        row["mode"] = row["market_value_mode"]
        row["bid_mode"] = row["target_bid_mode"]
    elif _final_truth == "TRUE" and row["true_market_value"]:
        row["target_bid_mode"] = "strict"
        row["bid_ceiling_source"] = "STRICT"
        row["market_value_mode"] = "strict"
        row["valuation_mode"] = "strict"
        row["mode"] = "strict"
        row["bid_mode"] = "strict"
    print(
        f"[MV_APPLY_TRACE] title={_title[:140]} "
        f"pre_source={_pre_source or 'none'} pre_exact_comp_count={_pre_exact_count} pre_truth={_pre_truth or 'NONE'} "
        f"source={(row.get('source') or row.get('mv_source') or row.get('market_value_source') or 'none')} "
        f"exact_comp_count={row.get('exact_comp_count') or '0'} "
        f"true_mv_before_apply={round(float(_pre_true_mv), 2) if _pre_true_mv and _pre_true_mv > 0 else None} "
        f"true_mv_after_apply={row.get('true_market_value') or None} "
        f"review_estimate={row.get('review_estimate_value') or None} "
        f"final_truth={row.get('valuation_truth_tier') or 'NONE'} "
        f"valuation_contract_version={row.get('_valuation_contract_version') or TRUE_MV_CONTRACT_VERSION}"
    )
    if result.value is None or result.value <= 0:
        return
    if set_timestamp:
        row["market_value_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row["dominant_range_low"] = (
        f"{result.dominant_range_low:.2f}" if result.dominant_range_low is not None else ""
    )
    row["dominant_range_high"] = (
        f"{result.dominant_range_high:.2f}" if result.dominant_range_high is not None else ""
    )
    row["dominant_comp_count"] = str(result.dominant_comp_count) if result.dominant_comp_count else ""
    row["cluster_method"] = result.cluster_method or ""
    row["cluster_strength"] = f"{result.cluster_strength:.4f}" if result.cluster_strength else ""
    row["market_lane_low"] = (
        f"{result.market_lane_low:.2f}" if result.market_lane_low is not None else ""
    )
    row["market_lane_high"] = (
        f"{result.market_lane_high:.2f}" if result.market_lane_high is not None else ""
    )
    row["market_lane_comp_count"] = (
        str(result.market_lane_comp_count) if result.market_lane_comp_count else ""
    )
    row["market_lane_recent_count"] = (
        str(result.market_lane_recent_count) if result.market_lane_recent_count else ""
    )
    row["market_lane_strength"] = (
        f"{result.market_lane_strength:.4f}" if result.market_lane_strength else ""
    )
    row["recent_comp_count_7d"] = str(result.recent_comp_count_7d) if result.recent_comp_count_7d else ""
    row["recent_comp_count_30d"] = str(result.recent_comp_count_30d) if result.recent_comp_count_30d else ""
    row["valuation_sale_mode"] = getattr(result, "valuation_sale_mode", "") or ""
    row["auction_comp_count"] = (
        str(result.auction_comp_count) if getattr(result, "auction_comp_count", 0) else ""
    )
    row["fixed_price_comp_count"] = (
        str(result.fixed_price_comp_count) if getattr(result, "fixed_price_comp_count", 0) else ""
    )
    row["exact_grade_comp_count"] = (
        str(result.exact_grade_comp_count) if getattr(result, "exact_grade_comp_count", 0) else ""
    )
    row["fallback_grade_comp_count"] = (
        str(result.fallback_grade_comp_count) if getattr(result, "fallback_grade_comp_count", 0) else ""
    )
    row["grade_fallback_used"] = "1" if getattr(result, "grade_fallback_used", False) else ""
    row["valuation_strength"] = getattr(result, "valuation_strength", "") or ""
    row["valuation_flow_label"] = getattr(result, "valuation_flow_label", "") or ""
    row["valuation_downgrade_reasons"] = (
        (getattr(result, "valuation_downgrade_reasons", "") or "")[:500]
    )
    row["duplicate_suppressed_count"] = str(
        getattr(result, "duplicate_suppressed_count", 0) or 0
    )
    row["exactness_tier_counts"] = (getattr(result, "exactness_tier_counts", "") or "")[:400]
    row["mv_pool_mode"] = (getattr(result, "mv_pool_mode", "") or "")[:64]
    row["mv_strict_comp_count"] = str(getattr(result, "mv_strict_comp_count", 0) or 0)
    row["mv_relaxed_comp_count"] = str(getattr(result, "mv_relaxed_comp_count", 0) or 0)
    row["mv_strict_lane_comp_count"] = str(getattr(result, "mv_strict_lane_comp_count", 0) or 0)
    row["mv_relaxed_fallback_used"] = "1" if getattr(result, "mv_relaxed_fallback_used", False) else ""

    if auto_target_enabled and update_target_bid:
        row["target_bid"] = str(round(float(result.value) * float(target_bid_ratio), 2))
    cp = _safe_float(row.get("current_price"), 0.0) or 0.0
    row["max_buy_price"] = str(round(float(result.value) * 0.70, 2))
    row["estimated_profit"] = str(round(float(result.value) - cp, 2))


def _normalize_hybrid_result_for_app(result: HybridValuation) -> Dict[str, str]:
    if not result:
        return {}
    _true_mv = result.true_market_value if result.true_market_value is not None and result.true_market_value > 0 else None
    return {
        "market_value": f"{_true_mv:.2f}" if _true_mv is not None else "",
        "market_value_true": f"{result.true_market_value:.2f}" if result.true_market_value is not None and result.true_market_value > 0 else "",
        "true_market_value": f"{result.true_market_value:.2f}" if result.true_market_value is not None and result.true_market_value > 0 else "",
        "review_estimate_value": f"{result.review_estimate_value:.2f}" if result.review_estimate_value is not None and result.review_estimate_value > 0 else "",
        "mv_mid": f"{_true_mv:.2f}" if _true_mv is not None else "",
        "market_value_source": result.market_value_source or "",
        "mv_source": result.market_value_source or "",
        "source": result.market_value_source or "",
        "valuation_source_clean": result.market_value_source or "",
        "valuation_truth_tier": result.valuation_truth_tier or "",
        "_valuation_truth_tier": result.valuation_truth_tier or "",
        "exact_comp_count": str(int(getattr(result, "exact_comp_count", 0) or 0)),
        "_valuation_contract_version": str(getattr(result, "valuation_contract_version", "") or TRUE_MV_CONTRACT_VERSION),
        "_valuation_source_module": str(getattr(result, "valuation_source_module", "") or VALUATION_SOURCE_MODULE),
        "_valuation_publish_stage": str(getattr(result, "valuation_publish_stage", "") or VALUATION_PUBLISH_STAGE),
        "_valuation_apply_guard": str(getattr(result, "valuation_apply_guard", "") or VALUATION_APPLY_GUARD),
        "single_comp_clone_block": "1" if bool(getattr(result, "single_comp_clone_block", False)) else "",
        "market_value_confidence": result.confidence or "",
        "mv_confidence_adjusted": result.confidence or "",
        "comp_count": str(int(result.comp_count or 0)),
        "last_comp_date": result.last_comp_date or "",
        "valuation_notes": (result.notes or "")[:2000],
        "value_range_low": f"{result.value_low:.2f}" if result.value_low is not None else "",
        "value_range_high": f"{result.value_high:.2f}" if result.value_high is not None else "",
        "mv_low": f"{result.value_low:.2f}" if result.value_low is not None else "",
        "mv_high": f"{result.value_high:.2f}" if result.value_high is not None else "",
        "mv_method": result.market_lane_method or result.valuation_basis or "",
        "valuation_basis": result.valuation_basis or "",
        "debug_confidence_rationale": (getattr(result, "debug_confidence_rationale", "") or "")[:500],
        "debug_audit_summary": (getattr(result, "debug_audit_summary", "") or "")[:800],
        "valuation_final_status": (getattr(result, "valuation_final_status", "") or "")[:120],
        "valuation_failure_reason": (getattr(result, "valuation_failure_reason", "") or "")[:400],
        "mv_fallback_reason": (getattr(result, "mv_fallback_reason", "") or "")[:300],
        "comp_lane_label": (getattr(result, "comp_lane_label", "") or "")[:160],
        "comp_lane_status": (getattr(result, "comp_lane_status", "") or "")[:64],
        "comp_lane_warning": (getattr(result, "comp_lane_warning", "") or "")[:200],
        "comp_lane_signature": (getattr(result, "comp_lane_signature", "") or "")[:200],
        "recovery_mode": (getattr(result, "recovery_mode", "") or "")[:80],
        "recovery_note": (getattr(result, "recovery_note", "") or "")[:200],
        "comp_evidence_json": json.dumps(getattr(result, "comp_evidence", {}) or {"used": [], "rejected": []}, ensure_ascii=False)[:12000],
    }


def normalize_hybrid_result_schema(
    result: HybridValuation,
    *,
    row_key: str = "",
) -> Dict[str, Any]:
    normalized = _normalize_hybrid_result_for_app(result)
    return {
        "row_key": str(row_key or ""),
        "valuation_status": normalized.get("valuation_final_status") or "",
        "market_value": normalized.get("market_value") or "",
        "mv_mid": normalized.get("mv_mid") or "",
        "mv_low": normalized.get("mv_low") or "",
        "mv_high": normalized.get("mv_high") or "",
        "comp_count": normalized.get("comp_count") or "0",
        "confidence": normalized.get("market_value_confidence") or "",
        "source": normalized.get("market_value_source") or "",
        "mv_source": normalized.get("mv_source") or "",
        "mv_method": normalized.get("mv_method") or "",
        "recovery_mode": normalized.get("recovery_mode") or "",
        "recovery_note": normalized.get("recovery_note") or "",
        "failure_reason": normalized.get("valuation_failure_reason") or "",
        "comp_lane_status": normalized.get("comp_lane_status") or "",
        "comp_lane_warning": normalized.get("comp_lane_warning") or "",
        "comp_lane_signature": normalized.get("comp_lane_signature") or "",
    }


def legacy_estimate_tuple(result: HybridValuation) -> Tuple[Optional[float], int]:
    """Backward compat for callers expecting (value, comps_used)."""
    if result.value and result.value > 0:
        return result.value, result.comp_count
    return None, 0
