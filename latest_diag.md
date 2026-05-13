# SNIPEWINS scan summary
  source: last_scan.log  (703487 lines)

## Engine death funnel
  [ENGINE_DEATH_FUNNEL] raw_fetched=406 auction_only=66 strict_window=45 title_clean=54 player_pass=53 product_pass=53 parallel_pass=53 target_pass=23 quality_pass=24 valuation_pass=22 final_candidates=5 return_rows=5

## Engine death reasons
  [ENGINE_DEATH_REASON_SUMMARY] reason_counts={'time_filter': 273, 'quality_reject': 50, 'valuation_failure': 2, 'contamination': 0, 'wrong_player': 0, 'wrong_product': 0, 'parallel_mismatch': 0, 'active_listing_block': 0, 'self_comp_block': 0, 'price_echo': 0, 'other': 0}

## Time bucket split
  [TIME_BUCKET_SPLIT] snipe=39 prepare=5 research=11 research_blocked_non_premium=5 discard=0

## Player routing summary
  [PLAYER_ROUTING_SUMMARY] input=53 successful_player_matches=53 wrong_player=0 soft_recovered=0 top_failed_name_patterns={}

## Post-player funnel
  [POST_PLAYER_FUNNEL] player_pass=53 product_pass=53 parallel_pass=53 target_pass=23 quality_pass=24 valuation_candidates=22 valued_rows=5 visible_rows=5 final_candidates=5 board_display=5

## Target route summary
  [TARGET_ROUTE_SUMMARY] parallel_input=53 target_pass=10 target_miss=29 reason_counts={'other_target_reject': 27, 'prepare_target_not_premium_shape': 2}

## Valuation handoff (final)
  [VALUATION_HANDOFF_GATE] stage=final_pre_valuation source_rows=66 candidate_rows=22 drop_reason={'all_auction_items': 66, 'window_rows': 55, 'title_rows': 55, 'player_rows': 53, 'product_rows': 53, 'parallel_rows': 53, 'target_rows': 23, 'candidate_drop_counts': {'jumbo': 1}, 'promoted_live_candidates': 0}

## Candidate funnel (UI)
  [CANDIDATE_FUNNEL_SUMMARY] fetched=406 normalized=5 valuation_rows=5 valued_rows=5 action_ready=0 watch_rows=5 pass_rows=0 research_rows=0 rare_exact_rows=0 suppressed_rows=0 display_rows=5 replacement_pool=0

## Board state
  [ES][BOARD_STATE] all=5 displayed=5 dropped=0

## Board mix
  [BOARD_MIX] sniper_board=0 watchlist=5 displayed=5

## Board replacement pool
  [BOARD_REPLACEMENT_POOL] actionable_total=5 actionable_pass_overpriced=0 actionable_recurring_from_prior_scans=5 dl_remainder_pool=0 commercial_hidden_pool=0 watchlist_hidden_pool=0 overflow_total=0 fresh_alternatives_in_remainder=0 loop_seen_recurring=5 loop_pass_overpriced=0

## Board drop reasons
  [BOARD_DROP_REASON_SUMMARY] reason_counts={}

## Live preserve summary
  [LIVE_PRESERVE_SUMMARY] preserved_rows=5 preserved_watch=5 preserved_sniper=0 bucket_fallbacks_blocked=5 downgrades_blocked=5 displayed_after_preserve=5


# Per-row drops (most recent)

## Post-player row drops (showing 12 of 48)
  [POST_PLAYER_DROP] title=James Wood Topps Chrome RC 35th Anniversary Black Mojo Refractor 10/10  stage=filtered_auctions reason=post_valuation_quality_suppression player=james wood product=Topps Chrome parallel= current_price=na target_bid=na time_bucket=RESEARCH
  [POST_PLAYER_DROP] title=2024 Panini Prizm - Pete Crow-Armstrong #203 (RC) stage=filtered_auctions reason=post_valuation_quality_suppression player=pete crow-armstrong product=Panini Prizm parallel= current_price=na target_bid=na time_bucket=PREPARE
  [POST_PLAYER_DROP] title=2024 Topps Chrome - Jackson Holliday #USC200 (RC) Baltimore Orioles ROOKIE CARD  stage=filtered_auctions reason=post_valuation_quality_suppression player=jackson holliday product=Topps Chrome parallel= current_price=na target_bid=na time_bucket=PREPARE
  [POST_PLAYER_DROP] title=2024 Topps Chrome Update Series - Rookie Debut #USC89 Jackson Holliday (RC) stage=filtered_auctions reason=post_valuation_quality_suppression player=jackson holliday product=Topps Chrome parallel= current_price=na target_bid=na time_bucket=PREPARE
  [POST_PLAYER_DROP] title=JACKSON HOLLIDAY 2024 Topps Chrome Logofractor Orange 1/25 #88 PSA 10Color Match stage=filtered_auctions reason=post_valuation_quality_suppression player=jackson holliday product=Topps Chrome parallel= current_price=na target_bid=na time_bucket=RESEARCH
  [POST_PLAYER_DROP] title=2024 Topps Chrome - Summertime in the Park Jackson Holliday #SITP-8 (RC) stage=filtered_auctions reason=post_valuation_quality_suppression player=jackson holliday product=Topps Chrome parallel= current_price=na target_bid=na time_bucket=RESEARCH
  [POST_PLAYER_DROP] title=JACKSON HOLLIDAY 2026 TOPPS FLAGSHIP 9 COSTCO EXCLUSIVE CHROME BALTIMORE ORIOLES stage=target reason=target_route_miss player=jackson holliday product=Topps parallel= current_price=na target_bid=na time_bucket=RESEARCH
  [POST_PLAYER_DROP] title=2024 Topps Chrome Update Jackson Holliday Rookie Debut USC89 Baltimore Orioles stage=filtered_auctions reason=post_valuation_quality_suppression player=jackson holliday product=Topps Chrome parallel= current_price=na target_bid=na time_bucket=RESEARCH
  [POST_PLAYER_DROP] title=Jackson Holliday Rookie 2024 Topps Chrome #88. PSA Graded-GEM MT 10 stage=filtered_auctions reason=post_valuation_quality_suppression player=jackson holliday product=Topps Chrome parallel= current_price=na target_bid=na time_bucket=RESEARCH
  [POST_PLAYER_DROP] title=2025 Topps Chrome - Future Stars Jackson Holliday #FS-1 stage=target reason=target_route_miss player=jackson holliday product=Topps Chrome parallel= current_price=na target_bid=na time_bucket=RESEARCH
  [POST_PLAYER_DROP] title=2024 Topps Chrome Update Jackson Holliday Xfractor RC #USC200 Baltimore Orioles stage=filtered_auctions reason=post_valuation_quality_suppression player=jackson holliday product=Topps Chrome parallel= current_price=na target_bid=na time_bucket=RESEARCH
  [POST_PLAYER_DROP] title=2024 Topps Chrome Update Series - Rookie Debut Jackson Holliday X-Fractor PSA 10 stage=filtered_auctions reason=post_valuation_quality_suppression player=jackson holliday product=Topps Chrome parallel= current_price=na target_bid=na time_bucket=RESEARCH

## Target route traces (showing 6 of 27)
  [TARGET_ROUTE_TRACE] title=2024 Topps Chrome - Jackson Holliday #88 Pink Refractor (RC)  Orioles /399 player=none product=none parallel=none serial=none insert_family=none card_number=none lane_type=collector_heat target_player=none target_product=none target_parallel=none target_serial=none target_card_number=none target_route_reason=other_target_reject matched_fields=none failed_fields=none
  [TARGET_ROUTE_TRACE] title=2024 Topps Chrome Jackson Holliday Rookie Refractor Baltimore Orioles #88 Rookie player=none product=none parallel=none serial=none insert_family=none card_number=none lane_type=collector_heat target_player=none target_product=none target_parallel=none target_serial=none target_card_number=none target_route_reason=other_target_reject matched_fields=none failed_fields=none
  [TARGET_ROUTE_TRACE] title=JACKSON HOLLIDAY 2024 TOPPS CHROME YOUTHQUAKE ROOKIE REFRACTOR  ORIOLES Q4244 player=none product=none parallel=none serial=none insert_family=none card_number=none lane_type=collector_heat target_player=none target_product=none target_parallel=none target_serial=none target_card_number=none target_route_reason=other_target_reject matched_fields=none failed_fields=none
  [TARGET_ROUTE_TRACE] title=2024 Topps Chrome Jackson Holliday RC Refractor Rookie #88 Orioles PSA 10 player=none product=none parallel=none serial=none insert_family=none card_number=none lane_type=collector_heat target_player=none target_product=none target_parallel=none target_serial=none target_card_number=none target_route_reason=other_target_reject matched_fields=none failed_fields=none
  [TARGET_ROUTE_TRACE] title=2024 Topps Chrome Update JACKSON HOLLIDAY RC Rookie Debut Card #USC89 Orioles player=none product=none parallel=none serial=none insert_family=none card_number=none lane_type=collector_heat target_player=none target_product=none target_parallel=none target_serial=none target_card_number=none target_route_reason=other_target_reject matched_fields=none failed_fields=none
  [TARGET_ROUTE_TRACE] title=2024 Topps Chrome Pete Crow-Armstrong LOGOFRACTOR BLACK ROOKIE #01/10 - CGC AUTH player=none product=none parallel=none serial=none insert_family=none card_number=none lane_type=lane_subset target_player=none target_product=none target_parallel=none target_serial=none target_card_number=none target_route_reason=other_target_reject matched_fields=none failed_fields=none

## Valued row traces (showing 5 of 5)
  [VALUED_ROW_TRACE] title=2024 Panini Select Paul Skenes Pirates Rookie Premier Level Blue Prizm #10 /199 current_price=25.0 target_bid=16.0 final_decision=WATCH bucket=actionable visible=1 drop_reason=none
  [VALUED_ROW_TRACE] title=2024 Topps Chrome - Jackson Holliday #88 Gold Refractor /50 (RC) current_price=20.7 target_bid=13.25 final_decision=WATCH bucket=actionable visible=1 drop_reason=none
  [VALUED_ROW_TRACE] title=2026 Topps Chrome Black Autographs #CBAPS Paul Skenes AUTO PIRATES current_price=305.0 target_bid=195.2 final_decision=WATCH bucket=actionable visible=1 drop_reason=none
  [VALUED_ROW_TRACE] title=2020 Panini Prizm Draft Picks Pete Crow-Armstrong Auto Tiger Stripes /25 AP6 current_price=102.5 target_bid=65.6 final_decision=WATCH bucket=actionable visible=1 drop_reason=none
  [VALUED_ROW_TRACE] title=2024 TOPPS CHROME BLACK GOLD MINI DIAMOND #5 GUNNAR HENDERSON 39/50 PSA 10 current_price=49.99 target_bid=31.99 final_decision=WATCH bucket=actionable visible=1 drop_reason=none

## Final action decisions (showing 6 of 15)
  [FINAL_ACTION_DECISION] title=2024 Topps Chrome - Jackson Holliday #88 Gold Refractor /50 (RC) current_price=20.7 target_bid=13.25 research_low=None research_high=None exploratory_max_bid=None decision=PASS_OVERPRICED path=verified edge_dollars=-7.45 edge_pct=-35.99 reason=pass_overpriced_no_mv:cp(20.70)>tb*1.05(13.91)
  [FINAL_ACTION_DECISION] title=2020 Panini Prizm Draft Picks Pete Crow-Armstrong Auto Tiger Stripes /25 AP6 current_price=102.5 target_bid=65.6 research_low=None research_high=None exploratory_max_bid=None decision=PASS_OVERPRICED path=verified edge_dollars=-36.9 edge_pct=-36.0 reason=pass_overpriced_no_mv:cp(102.50)>tb*1.05(68.88)
  [FINAL_ACTION_DECISION] title=2024 Panini Select Paul Skenes Pirates Rookie Premier Level Blue Prizm #10 /199 current_price=25.0 target_bid=16.0 research_low=None research_high=None exploratory_max_bid=None decision=PASS_OVERPRICED path=verified edge_dollars=-9.0 edge_pct=-36.0 reason=pass_overpriced_no_mv:cp(25.00)>tb*1.05(16.80)
  [FINAL_ACTION_DECISION] title=2024 Topps Chrome - Jackson Holliday #88 Gold Refractor /50 (RC) current_price=20.7 target_bid=13.25 research_low=None research_high=None exploratory_max_bid=None decision=PASS_OVERPRICED path=verified edge_dollars=-7.45 edge_pct=-35.99 reason=pass_overpriced_no_mv:cp(20.70)>tb*1.05(13.91)
  [FINAL_ACTION_DECISION] title=2026 Topps Chrome Black Autographs #CBAPS Paul Skenes AUTO PIRATES current_price=305.0 target_bid=195.2 research_low=None research_high=None exploratory_max_bid=None decision=PASS_OVERPRICED path=verified edge_dollars=-109.8 edge_pct=-36.0 reason=pass_overpriced_no_mv:cp(305.00)>tb*1.05(204.96)
  [FINAL_ACTION_DECISION] title=2024 TOPPS CHROME BLACK GOLD MINI DIAMOND #5 GUNNAR HENDERSON 39/50 PSA 10 current_price=49.99 target_bid=31.99 research_low=None research_high=None exploratory_max_bid=None decision=PASS_OVERPRICED path=verified edge_dollars=-18.0 edge_pct=-36.01 reason=pass_overpriced_no_mv:cp(49.99)>tb*1.05(33.59)

## Strict window blocks (showing 4 of 25)
  [STRICT_WINDOW_RESCUE_BLOCKED] item_id=v1|366383912356|0 title=2024 Panini Donruss - Rated Rookie Bo Nix Optic Preview Red Wave Prizm PSA 10 reason=outside_selected_window remaining_seconds=64616.81 window_seconds=21600
  [STRICT_WINDOW_RESCUE_BLOCKED] item_id=v1|168338845473|0 title=Jackson Holliday 2025 Topps Chrome Black Gold Mini Diamond Auto #CBA-JH  19/50 reason=outside_selected_window remaining_seconds=85097.74 window_seconds=21600
  [STRICT_WINDOW_RESCUE_BLOCKED] item_id=v1|277936012808|0 title=2021 Panini Prizm Draft Picks - Thunderstruck James Wood Autograph #T-JW (RC) reason=outside_selected_window remaining_seconds=28020.97 window_seconds=21600
  [STRICT_WINDOW_RESCUE_BLOCKED] item_id=v1|137263601645|0 title=James Wood Topps Chrome RC 35th Anniversary Black Mojo Refractor 10/10 reason=outside_selected_window remaining_seconds=59880.84 window_seconds=21600


# Tag tally over the whole log

  [DISCOVERY_QUALITY_DROP]        50
  [POST_PLAYER_DROP]              48
  [EXECUTION_PROMOTION_BLOCK]     35
  [TARGET_ROUTE_TRACE]            27
  [STRICT_WINDOW_RESCUE_BLOCKED]  25
  [TIME_BUCKET_ASSIGN]            21
  [PREPARE_BUCKET]                16
  [FINAL_ACTION_PASS]             15


# Quick read — biggest stage cliffs (>=30% drop)
  - raw_fetched → auction_only: 406 → 66 (lost 340, 84% of stage)
  - auction_only → strict_window: 66 → 45 (lost 21, 32% of stage)
  - parallel_pass → target_pass: 53 → 23 (lost 30, 57% of stage)
  - valuation_pass → final_candidates: 22 → 5 (lost 17, 77% of stage)
