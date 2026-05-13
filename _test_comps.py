import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

tests = [
    "2023 Panini Prizm Patrick Mahomes Silver Prizm #1",
    "2022 Topps Chrome Mike Trout Gold Refractor /50",
    "2021 Panini Select Luka Doncic Concourse Silver PSA 10",
    "2023 Bowman Chrome Jackson Holliday Blue Refractor /150",
    "2024 Panini Prizm Josh Allen Purple Prizm /49",
]

print("=== LIVE COMP TESTS — comp_engine_v2.get_comp_value ===")
import comp_engine_v2 as cev2
for i, t in enumerate(tests, 1):
    print(f"--- Card {i}: {t} ---")
    try:
        result = cev2.get_comp_value(t)
        print(f"  tier={result.match_tier} conf={result.confidence} comps={result.comp_count}")
        print(f"  mv={result.final_market_value} raw_avg={result.raw_average} cv={result.price_cv}%")
        print(f"  insufficient={result.insufficient_data} error={result.error or None}")
        if result.comps_used:
            print(f"  Comps used ({len(result.comps_used)}):")
            for c in result.comps_used[:5]:
                age = f"{c.age_days:.0f}d" if c.age_days is not None else "?d"
                print(f"    ${c.total:.2f} ({age}) w={c.weight:.2f} | {c.title[:70]}")
        if result.comps_rejected:
            by_reason = {}
            for c in result.comps_rejected:
                by_reason[c.reject_reason] = by_reason.get(c.reject_reason, 0) + 1
            print(f"  Rejected ({len(result.comps_rejected)}):")
            for reason, cnt in sorted(by_reason.items(), key=lambda x: -x[1])[:5]:
                print(f"    {cnt}x {reason}")
        p = result.parsed_card
        if p:
            print(f"  Parsed: player=[{p.player_name}] year={p.year} product={p.product}")
            print(f"          parallel={p.parallel} print_run={p.print_run} graded={p.is_graded} grade={p.grade}")
    except Exception as e:
        import traceback
        print(f"  ERROR: {e}")
        traceback.print_exc()
    print()

print()
print("=== LIVE COMP TESTS — market_value_engine.get_market_value_for_item ===")
import market_value_engine as mve
for i, t in enumerate(tests, 1):
    print(f"--- Card {i}: {t} ---")
    try:
        result = mve.get_market_value_for_item(t, limit=15)
        print(f"  mv={result.get('market_value')} conf={result.get('confidence')} comps={result.get('comp_count')}")
        print(f"  pool={result.get('comp_pool')} low_conf={result.get('low_confidence')}")
        print(f"  recency={result.get('comp_recency')} raw_vs_graded={result.get('raw_vs_graded')}")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()
