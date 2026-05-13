"""
snipewins_estimate.py — Formula-based MV estimate for cards with no comps.

Used as a FALLBACK when the valuation engine returns no exact comp match
and no confident cross-grade estimate. Built for brand-new 2026 releases
(e.g. 2026 Topps Chrome Black Dual Auto Red /5) where there are literally
zero historical eBay sold listings.

Methodology (transparent on purpose):

    estimate = baseline[player_tier]
             × parallel_rarity_multiplier(serial_denominator)
             × auto_multiplier
             × patch_multiplier
             × grade_multiplier
             × product_tier_multiplier

Baselines are tuned to roughly match observed PSA 10 base-RC street
prices for each player tier. Multipliers reflect typical hobby ratios
(e.g. /5 numbering trades at ~8x base in raw form).

The output is ALWAYS labeled "≈ SnipeWins estimate (no comps)" on the
dashboard so the user knows it's formulaic, not market-derived.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional


# ── Player tier baselines (PSA 10 raw equivalent of base rookie) ──────────
# These are the floor — what a top base PSA 10 RC of a player at each tier
# trades at on eBay. Multipliers stack on top.
PLAYER_TIER_BASELINE: Dict[str, float] = {
    "S":        200.0,   # Apex anchors — LeBron, Mahomes, Ohtani, Judge, Wemby, SGA, etc.
    "1":        80.0,    # Hot movers — Caleb, Bo Nix, Skenes, Drake Maye, etc.
    "2":        35.0,    # Cooled / second tier — Marvin Harrison Jr., Bijan, etc.
    "VINTAGE":  120.0,   # Historic anchors — Jordan, Brady, Mantle, etc.
    "QB_LEGEND": 60.0,   # HOF QB legends — Favre, Marino, Elway, Young, Aikman
    "3":        12.0,    # Background — drop unless very rare
}


# ── Parallel rarity multipliers (based on /N denominator) ────────────────
# Standard hobby ratios for serial-numbered parallels. Higher = rarer.
# These match typical comp ratios for Bowman Chrome refractor cohorts.
def parallel_rarity_multiplier(serial_n: Optional[int]) -> float:
    """Return the multiplier for a /N numbering. None → 1.0 (base)."""
    if not serial_n or serial_n <= 0:
        return 1.0
    if serial_n == 1:
        return 25.0   # 1/1 — premium of premiums
    if serial_n <= 5:
        return 9.0    # /2 to /5 — case-hit tier
    if serial_n <= 10:
        return 5.5    # /6 to /10 — Gold Refractor tier
    if serial_n <= 25:
        return 3.0    # /11 to /25 — Orange/Tie-Dye tier
    if serial_n <= 50:
        return 2.2    # /26 to /50 — premium colored parallel
    if serial_n <= 99:
        return 1.7    # /51 to /99 — Blue Ice / Aqua tier
    if serial_n <= 150:
        return 1.4    # /100 to /150 — Blue Refractor tier
    if serial_n <= 199:
        return 1.25   # /151 to /199 — Red /199 tier
    if serial_n <= 250:
        return 1.15   # /200 to /250 — Purple /250 tier
    if serial_n <= 499:
        return 1.08
    return 1.0       # /500+ — barely above base


# ── Card-feature multipliers ─────────────────────────────────────────────
AUTO_MULTIPLIER         = 1.6   # +60% for autographs
PATCH_MULTIPLIER        = 1.3   # +30% for relics/patches (stacks with auto)
DUAL_AUTO_MULTIPLIER    = 1.4   # +40% extra for dual/triple autos
GRADE_PSA10_MULTIPLIER  = 1.8   # PSA 10 trades ~1.8x its raw equivalent
GRADE_PSA9_MULTIPLIER   = 1.05  # PSA 9 trades ~5% above raw (modest premium)


# ── Product tier multiplier ──────────────────────────────────────────────
# Topps Chrome Black, National Treasures, Immaculate, Flawless command
# significant premiums over standard Prizm/Optic/Select.
PRODUCT_TIER_MULTIPLIER: Dict[str, float] = {
    "topps chrome black":    1.6,
    "national treasures":    1.8,
    "immaculate":            1.7,
    "flawless":              1.9,
    "spectra":               1.4,
    "select":                1.0,
    "prizm":                 1.0,
    "donruss optic":         0.9,
    "optic":                 0.9,
    "mosaic":                0.7,
    "donruss":               0.6,
    "bowman chrome":         1.2,
    "topps chrome":          1.0,
    "bowman draft":          1.2,
}


def product_tier_multiplier(title_lc: str) -> float:
    """Pick the highest-matching product tier multiplier for a title."""
    matched: float = 1.0
    for product, mult in PRODUCT_TIER_MULTIPLIER.items():
        if product in title_lc:
            if mult > matched:
                matched = mult
    return matched


# ── Title parsing helpers ────────────────────────────────────────────────
_SERIAL_RE   = re.compile(r"(?:#?\s*\d{1,3}\s*)?/\s?(\d{1,4})\b")
_AUTO_RE     = re.compile(r"\b(auto|autograph|signed|sig|ssp\s*auto)\b", re.IGNORECASE)
_DUAL_RE     = re.compile(r"\b(dual|double|triple|quad)\s*(auto|autograph)\b", re.IGNORECASE)
_PATCH_RE    = re.compile(r"\b(patch|relic|jersey|swatch|prime)\b", re.IGNORECASE)
_PSA10_RE    = re.compile(r"\bpsa\s*10\b", re.IGNORECASE)
_PSA9_RE     = re.compile(r"\bpsa\s*9(?!\.\d)\b", re.IGNORECASE)


def _parse_serial_denominator(title: str) -> Optional[int]:
    """Extract the /N denominator if present in title."""
    if not title:
        return None
    m = _SERIAL_RE.search(title)
    if not m:
        return None
    try:
        return int(m.group(1))
    except (TypeError, ValueError):
        return None


# ── Public API ───────────────────────────────────────────────────────────

def estimate_card_value(
    title: str,
    player_tier: str = "3",
) -> Optional[Dict[str, Any]]:
    """Compute a formula-based ballpark MV for a card. Returns:
        {
            "estimated_mv":   float,    # the ballpark
            "target_bid":     float,    # 75% of estimated_mv
            "breakdown":      list[str],# human-readable explanation
            "method":         "snipewins_estimate_v1",
        }
    or None if we can't even produce a guess (missing title).

    Used as a fallback when the valuation engine returns no real comp
    match. The dashboard surfaces this with a "≈ SnipeWins estimate
    (no comps)" label.
    """
    if not title:
        return None
    title_lc = title.lower()

    breakdown: list[str] = []
    base = PLAYER_TIER_BASELINE.get(str(player_tier or "3").upper(), PLAYER_TIER_BASELINE["3"])
    value = base
    breakdown.append(f"Tier {player_tier} baseline: ${base:,.0f}")

    serial_n = _parse_serial_denominator(title)
    if serial_n:
        rarity_mult = parallel_rarity_multiplier(serial_n)
        value *= rarity_mult
        breakdown.append(f"/{serial_n} numbering: ×{rarity_mult:.2f}")

    has_auto = bool(_AUTO_RE.search(title_lc))
    if has_auto:
        value *= AUTO_MULTIPLIER
        breakdown.append(f"Auto: ×{AUTO_MULTIPLIER:.2f}")

    has_dual = bool(_DUAL_RE.search(title_lc))
    if has_dual:
        value *= DUAL_AUTO_MULTIPLIER
        breakdown.append(f"Dual/triple: ×{DUAL_AUTO_MULTIPLIER:.2f}")

    has_patch = bool(_PATCH_RE.search(title_lc))
    if has_patch:
        value *= PATCH_MULTIPLIER
        breakdown.append(f"Patch/relic: ×{PATCH_MULTIPLIER:.2f}")

    has_psa10 = bool(_PSA10_RE.search(title_lc))
    has_psa9  = bool(_PSA9_RE.search(title_lc))
    if has_psa10:
        value *= GRADE_PSA10_MULTIPLIER
        breakdown.append(f"PSA 10: ×{GRADE_PSA10_MULTIPLIER:.2f}")
    elif has_psa9:
        value *= GRADE_PSA9_MULTIPLIER
        breakdown.append(f"PSA 9: ×{GRADE_PSA9_MULTIPLIER:.2f}")

    pt_mult = product_tier_multiplier(title_lc)
    if pt_mult != 1.0:
        value *= pt_mult
        breakdown.append(f"Product tier: ×{pt_mult:.2f}")

    # Round to nearest dollar
    final_mv = round(value)
    target_bid = round(final_mv * 0.75)

    return {
        "estimated_mv":  float(final_mv),
        "target_bid":    float(target_bid),
        "breakdown":     breakdown,
        "method":        "snipewins_estimate_v1",
    }
