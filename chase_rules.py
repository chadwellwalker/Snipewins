"""
chase_rules.py — Consolidated source of truth for what counts as a
"premium target" in the SnipeWins engine.

EDIT THIS FILE TO EVOLVE THE SCOPE OF WHAT THE ENGINE TARGETS.
The engine (ending_soon_engine.py, daily_pool.py, parallel_vocab.py) imports
from this module at runtime. Changes here take effect on the next scan.

DECISION TREE for whether a row qualifies as a target:

    1. Is it an auto? → YES (always qualifies, any sport / product / player)
    2. Is it numbered /50 or lower? → YES (auto-premium, the rarity carries it)
    3. Is it on the CHASE_ENDGAME list? → YES (case hits, no grade needed)
    4. Is the player Tier 1?
         → AND parallel is on CHASE_STRONG list → YES (raw or any grade)
         → AND base / common parallel → YES if PSA 10, otherwise NO
    5. Is the player Tier 2?
         → AND auto OR /N numbered → YES
         → AND parallel is on CHASE_STRONG list AND PSA 10 → YES
         → otherwise → NO
    6. Tier 3 or untracked player → NO unless /5 or lower or PSA 10 + endgame

GRADE RULE:
    "PSA 10 + selective PSA 9s for ultra-rare cards" — PSA 10 is the default
    requirement when a grade is needed; PSA 9 qualifies only when the card
    is /50 or lower OR has an endgame parallel.

NOTES:
    Player keys use the engine's existing snake_case slug convention (used
    in player_hub_state.json). Always lowercase, underscores between words,
    no Jr/Sr suffixes unless ambiguous.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Set, Tuple


# ── Player tier framework ────────────────────────────────────────────────────
# Tiers reflect HOBBY WEIGHT (eBay sales velocity, PSA submission volume,
# auction performance), not draft pedigree or on-field stats. Updated based
# on May 2026 hobby state.
#
# TIER S (apex_anchor): cards always move. Any era, any product, any parallel
#     qualifies raw. These are the structural hobby names — generational
#     rookies, perennial superstars, and the few names whose vintage cards
#     also command premiums. Demand is non-seasonal.
#
# TIER 1 (hot_mover): current rookie with confirmed hobby velocity, OR
#     established star whose cards are actively being bid up. Raw qualifies
#     for chase parallels; base needs PSA 10.
#
# TIER 2 (cooled_speculative): real player with name recognition but cards
#     are flat or volatile. PSA 10 + chase parallel required, OR /50 lower
#     OR auto.
#
# TIER 3 (default): everyone not listed below. Drop unless /5 or lower,
#     case hit, OR PSA 10 + endgame parallel.
#
# VINTAGE (apex_vintage): iconic names from past eras with their own
#     scarcity-driven valuation curve. Treated like Tier S but only for
#     pre-2010 cards. Their modern-product appearances (e.g., Jordan in
#     2024 Topps Chrome All-Time) get Tier 1 treatment.

PLAYER_TIER_S: Set[str] = {
    # ── NBA — perennial superstars (verified May 2026 hobby state) ────────
    "lebron_james",           # No Prizm rookie (predates 2012 Panini Prizm)
                              # but any Prizm PSA 10 flies
    "stephen_curry",          # PSA's #4 most-collected NBA player
    "nikola_jokic",           # 3x MVP, hobby liquidity at every level
    "luka_doncic",            # Hobby chase even via Panini exclusive
    "victor_wembanyama",      # 2024 ROY, MVP candidate, hobby anchor
    "shai_gilgeous_alexander",  # -7000 MVP favorite 2026 (back-to-back),
                              # 31.1 PPG / 55.3% FG / 64-18 OKC record

    # ── NFL — perennial superstars (Ja'Marr Chase demoted per user) ───────
    "patrick_mahomes",        # 2x MVP, 3x SB, single-name hobby driver
    "josh_allen",             # Bills, every Prizm parallel moves
    "joe_burrow",             # Bengals, top-3 hobby QB

    # ── MLB — perennial superstars ────────────────────────────────────────
    "shohei_ohtani",          # Dethroned Trout as #1 MLB hobby anchor 2023
    "aaron_judge",            # Yankees power, 75th anniversary Topps cover

    # NOTE: Mike Trout REMOVED from Tier S per user — "Trout is not in the
    # any-number-sells category." His PSA 10 rookies still anchor but his
    # modern cards have declined ~20% in 2026. Moved to Tier 1 below.
}

PLAYER_TIER_T1: Set[str] = {
    # ── NFL 2025 award winners ────────────────────────────────────────────
    "jaxon_smith_njigba",     # 2025 AP OPOY — 1,793 yds, Seahawks record
    "tetairoa_mcmillan",      # 2025 AP Offensive ROY — Panthers WR
    "sam_darnold",            # Took Seahawks to Super Bowl LX; 2018 Optic
                              # Downtown PSA 10 hit $1,800 in Jan 2026

    # ── NFL 2025 rookies ──────────────────────────────────────────────────
    "cam_ward",               # 2025 #1 overall, hottest rookie card 2026
    "travis_hunter",          # 2025 #2 overall, two-way unicorn
    "shedeur_sanders",        # 2025 first-round QB, hobby spotlight
    "ashton_jeanty",          # 2025 rookie RB, top RB chase
    "jaxson_dart",            # 2025 rookie QB
    "cam_skattebo",           # 2025 Giants rookie RB — ankle dislocation
                              # ended season but workhorse; buy-low window

    # ── NFL 2024 sophomores who held / grew their value ───────────────────
    "jayden_daniels",         # 2024 OPOY, Commanders QB
    "bo_nix",                 # 2024 Pro Bowl, year-2 ascendant
    "drake_maye",             # 2024 Patriots QB — $164K patch sales
    "brock_bowers",           # 2024 TE record-holder
    "caleb_williams",         # Year 2 — Black Finite 1/1 at $122K
    "puka_nacua",             # Rams WR — best in the game per user

    # ── NFL established stars (T1 blue chips, not S-tier) ─────────────────
    "ja_marr_chase",          # Bengals WR, demoted from S per user
    "christian_mccaffrey",
    "justin_jefferson",
    "ceedee_lamb",
    "saquon_barkley",
    "lamar_jackson",
    "jalen_hurts",
    "george_kittle",
    "dak_prescott",
    "george_pickens",         # Cowboys WR (traded from Steelers), per user
    "davante_adams",          # Rams WR, per user
    "brock_purdy",            # 49ers QB, per user
    "jordan_love",            # Packers QB, per user
    "amon_ra_st_brown",       # Lions WR, top-5 fantasy WR multi-year; per user
    "justin_herbert",         # Chargers QB; per user
    "trevor_lawrence",        # Jaguars QB; per user
    "myles_garrett",          # Browns DE, perennial DPOY; per user
    "tj_watt",                # Steelers LB, perennial DPOY; per user
    "calvin_johnson",         # Megatron — retired but T1 per user
                              # (Lions WR HOF, vintage moves)
    "derrick_henry",          # Ravens RB, 2K-yard season 2024, postseason
                              # hobby moment; per user
    "de_von_achane",          # Dolphins RB, speed-back breakout; per user

    # ── NBA — current All-Stars and rising rookies ────────────────────────
    "cooper_flagg",           # 2025 #1 overall pick, generational chase
    "giannis_antetokounmpo",
    "jayson_tatum",
    "kevin_durant",
    "anthony_edwards",        # Wolves star, hobby rising
    "joel_embiid",            # added per user
    "devin_booker",           # added per user
    "jamal_murray",           # added per user
    "tyrese_haliburton",      # Pacers, All-NBA, per user
    "jalen_brunson",          # Knicks, hobby-aware market, per user

    # ── MLB — Cy Young + current top stars ────────────────────────────────
    "paul_skenes",            # 2025 NL Cy Young (unanimous), Pirates ace
    "tarik_skubal",           # 2024+2025 AL Cy Young back-to-back; $36K
                              # logoman auto; added per user
    "roman_anthony",          # Red Sox top prospect, 2025 debut
    "elly_de_la_cruz",        # Reds, sticking power/speed phenom
    "bobby_witt_jr",          # Royals MVP candidate
    "juan_soto",              # Yankees/Mets — perennial big name
    "ronald_acuna_jr",        # Braves, MVP-tier
    "fernando_tatis_jr",      # Padres
    "mike_trout",             # Demoted from S; modern cards down ~20% but
                              # PSA 10 rookies still gold standard; on pace
                              # for 50 HRs in 2026, hobby attention back
    "bryce_harper",           # Phillies, perennial star, per user
    "mookie_betts",           # Dodgers, perennial star, per user
    "freddie_freeman",        # Dodgers, perennial star, per user
    "jose_ramirez",           # Guardians, perennial 3B star, per user
    "jackson_merrill",        # Padres OF, strong 2024 / 2025, per user

    # ── MLB 2025 ROY winner + 2026 ROY race ──────────────────────────────
    "nick_kurtz",             # 2025 AL ROY (unanimous), A's 1B
    "kevin_mcgonigle",        # +145 AL ROY 2026 favorite, Tigers SS; PSA 10
                              # Bowman Chrome auto at $850
    "trey_yesavage",          # +190 AL ROY 2026, Blue Jays pitcher; PSA 10
                              # prospect auto at $713
    "sal_stewart",            # +180 NL ROY 2026 favorite, Reds 1B
    "konnor_griffin",         # NL ROY 2026 contender, #1 prospect, Pirates
                              # 19yo SS; Bowman Draft Chrome auto PSA 10
                              # at $2,000-2,500
    "nolan_mclean",           # +340 NL ROY 2026, Mets pitcher
    "munetaka_murakami",      # AL ROY 2026 race, White Sox 1B
    "colt_emerson",           # MLB Pipeline #7 prospect, Mariners
    "jesus_made",              # 2026 ROY contender, prospect chase

    # ── MLB current/recent stars added in audit ───────────────────────────
    "yoshinobu_yamamoto",     # 2025 WS MVP, $325M Dodgers, back-to-back
                              # complete games in postseason; per user
    "julio_rodriguez",        # Mariners CF, top-9 fantasy 2026; per user
    "vladimir_guerrero_jr",   # Toronto 1B, perennial; per user
    "junior_caminero",        # Rays 3B, 2025 breakout; per user

    # ── NBA T1 additions (audit round) ───────────────────────────────────
    "cade_cunningham",        # Pistons, All-Star breakout; per user

    # ── WNBA — only Caitlin Clark + Paige Bueckers per user ──────────────
    # Rule: WNBA premium cards only qualify when chase parallel / numbered /
    # PSA 10. Caitlin Clark Prizm Silver PSA 10 = $3K; common base = noise.
    # T1 logic already handles this — base raw drops, chase + numbered +
    # graded qualify.
    "caitlin_clark",          # Indiana Fever, generational hobby moment
    "paige_bueckers",         # Dallas Wings, 2025 WNBA #1 pick
}

PLAYER_TIER_T2: Set[str] = {
    # ── NFL cooled rookies / second-tier 2024 class ───────────────────────
    "marvin_harrison_jr",     # Cooled — flat sales despite good season
    "malik_nabers",           # Good year, not blue chip
    "rome_odunze",            # Behind DJ Moore in Bears WR room
    "brian_thomas_jr",        # Jaguars WR — solid not elite
    "bijan_robinson",         # Cooled — RB position discount
    "treveyon_henderson",     # 2025 rookie RB
    "michael_penix",          # Falcons QB, future starter
    "cj_stroud",              # 2023 ROY but cooled fast
    "drake_london",           # Falcons WR
    "tyreek_hill",            # Demoted per user — off-field issues
    "travis_kelce",           # Chiefs TE, vintage-era anchor; per user
    "garrett_wilson",         # Jets WR, 2022 OROY; per user
    "patrick_surtain_ii",     # Broncos CB, 2024 DPOY; per user
    "aaron_rodgers",          # Steelers QB, veteran; per user
    "aj_brown",               # Eagles WR1; per user
    "tee_higgins",            # Bengals WR (paired with Chase); per user
    "dk_metcalf",             # Steelers WR (traded from Seattle); per user
    "mike_evans",              # Bucs WR, 1K-yard streak; per user
    "dj_moore",               # Bears WR; per user
    "aidan_hutchinson",       # Lions DE, Comeback POY candidate; per user
    "nick_bosa",              # 49ers DE; per user
    "aaron_donald",           # Retired LA Rams DT, GOAT; per user
                              # (T2 per user — vintage anchor era)
    "drew_brees",             # Retired Saints QB; per user
    "bryce_young",            # Panthers QB, 2023 #1 overall; per user
    "bucky_irving",           # Bucs RB, 2024 rookie breakout; per user
    "james_cook",             # Bills RB, Pro Bowl; per user

    # ── MLB cooled prospects / mid-tier names ─────────────────────────────
    "gunnar_henderson",       # Cooled some, still solid
    "jackson_chourio",        # Brewers — held value, not anchor
    "francisco_lindor",       # Mets — name brand, modest hobby pull
    "pete_crow_armstrong",    # Cubs CF — breakout candidate
    "corbin_carroll",         # 2023 NL ROY — cooled
    "yordan_alvarez",         # Astros DH/OF, Beckett April 2026 surge, per user
    "pete_alonso",            # Orioles 1B (was Mets); per user — flagged
                              # to revisit when he produces with new team
    "manny_machado",          # Padres 3B vet; per user
    "garrett_crochet",        # Red Sox young ace (was White Sox); per user
    "trea_turner",            # Phillies SS; per user
    "bo_bichette",            # Blue Jays SS; per user

    # ── NBA second tier ────────────────────────────────────────────────────
    "paolo_banchero",         # 2023 ROY, Magic — solid not elite
    "chet_holmgren",          # Thunder rising — not blue chip yet
    "scoot_henderson",
    "amen_thompson",
    "ausar_thompson",
    "kon_knueppel",           # 2025 NBA rookie, Hornets
    "tyrese_maxey",           # 76ers PG, per user
    "donovan_mitchell",       # Cavs, perennial All-Star; per user
    "jaylen_brown",           # Celtics, 2024 Finals MVP; per user
    "stephon_castle",         # Spurs, 2024 NBA ROY; per user
    "allen_iverson",          # Retired 76ers PG, vintage anchor;
                              # T2 per user (lives across vintage + modern)
}

# REMOVED from any tier per user (treated as Tier 3 / drop):
#   - Jackson Holliday   — disappointing MLB debut, off the list
#   - Spencer Strider    — cooled with injury, off the list
#   - Anthony Davis      — unsellable in current state
#   - Anthony Richardson — Colts QB, demoted out of T2 per user
#   - Wyatt Langford     — not at T1 yet (was wrongly added)
# CONSIDERED FOR T2/T1 BUT EXPLICITLY KEPT T3 BY USER (May 2026 audit):
#   NFL:
#     - Kyren Williams     — Rams RB
#     - Colston Loveland   — Bears TE 2025 rookie
#     - Tyler Warren       — Colts TE 2025 rookie
#     - Tank Bigsby        — Eagles RB
#     - Cooper Kupp        — Veteran WR
#     - Stefon Diggs       — Veteran WR
#     - Sam LaPorta        — Lions TE (only big cards qualify)
#     - DeVonta Smith      — Eagles WR
#     - Kyler Murray       — "QB of the Vikings" per user (verify trade)
#     - Cooper DeJean      — Eagles DB
#     - JJ Watt            — Retired DE
#     - Alvin Kamara       — Saints vet
#     - Najee Harris       — "maybe next year" per user
#     - Reggie White       — Retired DE (vintage candidate, not added)
#   NBA:
#     - Kawhi Leonard      — Clippers, cooled
#     - De'Aaron Fox       — Spurs (post-trade)
#     - Jimmy Butler       — Heat
#     - Reed Sheppard      — Rockets, 2024 rookie
#     - Zach Edey          — Grizzlies, 2024 rookie
#     - Trae Young         — Hawks, polarizing
#     - LaMelo Ball        — Hornets
#     - Karl-Anthony Towns — Knicks, post-trade
#     - Evan Mobley        — Cavs
#     - Bam Adebayo        — Heat
#     - Ja Morant          — Grizzlies (polarizing)
#     - Zion Williamson    — health concerns
#     - Domantas Sabonis   — Kings
#     - Pascal Siakam      — Pacers
#     - Mikal Bridges      — Knicks
#     - Franz Wagner       — Magic
#     - Jared McCain       — 76ers
#     - Alperen Sengun     — Rockets
#     - Brandon Miller     — Hornets (potential but only T3 for now)
#     - Carmelo Anthony    — Retired
#     - Tracy McGrady      — Retired
#     - Klay Thompson      — Mavericks vet
#     - Russell Westbrook  — vet
#     - Chris Paul         — vet
#     - Damian Lillard     — "Not right now. He's returning to the
#                            Trail Blazers next year" — revisit then.
#   MLB:
#     - Corbin Burnes      — D-Backs pitcher
#     - Adley Rutschman    — Orioles catcher
#     - Roki Sasaki        — Dodgers, Topps Chrome cover but T3 per user
#     - Shota Imanaga      — Cubs pitcher
#     - Anthony Volpe      — Yankees SS
#     - Riley Greene       — Tigers OF
#     - Walker Buehler     — too injury-riddled
#     - Chris Sale         — Braves Cy Young vet
#     - Marcelo Mayer      — Red Sox prospect
#     - Jasson Domínguez   — Yankees prospect
#     - Spencer Schwellenbach — Braves pitcher
#     - Jung Hoo Lee       — Giants CF
#     - Triston Casas      — Red Sox 1B
#     - Albert Pujols      — Retired 1B
#     - Miguel Cabrera     — Retired DH
#     - Corey Seager       — Rangers SS, 2023 WS MVP (T3 per user)
#     - Carlos Correa      — Twins SS
#     - Spencer Torkelson  — Tigers 1B (cooled)
#     - Christian Yelich   — Brewers vet
#     - Cole Ragans        — Royals LHP
#     - Tyler Glasnow      — Dodgers LHP
#     - Logan Webb         — Giants RHP
#     - George Kirby       — Mariners RHP
#
# NOT ADDED — UNSELLABLE OR EXPLICIT NO (per user May 2026 audit):
#   NBA:
#     - Tyler Herro          — "not sellable"
#     - Brandon Ingram       — "not sellable"
#     - Tari Eason           — no
#     - Trayce Jackson-Davis — no
#     - Bradley Beal         — no
#     - Khris Middleton      — no
#     - Devin Vassell        — no
#     - Andrew Wiggins       — no
#   MLB:
#     - Pete Rose            — no
#     - Joey Votto           — no
#     - Matt McLain          — no
#     - Adolis García        — no
#     - Salvador Pérez       — no
#     - Lawrence Butler      — no
#     - Hunter Brown         — no
#     - Justin Steele        — no
#   NBA vintage:
#     - Vince Carter         — no
#   NFL — all the "cooked QBs":
#     - Tua Tagovailoa       — no
#     - Geno Smith           — no
#     - Justin Fields        — no
#     - Russell Wilson       — no
#     - Cam Newton           — not addressed (skip)
#     - Joe Mixon            — "not anymore"
#     - Tony Pollard         — "not anymore"
#
# NOT ADDED (whole categories deferred per user):
#   - NHL (Connor McDavid, Macklin Celebrini): not seen at shows
#   - Soccer (Messi, Mbappé, Bellingham, Yamal): not seen at shows
#   - WNBA beyond Clark + Bueckers (A'ja Wilson, Angel Reese, etc.):
#     not yet enough hobby weight at shows per user
# These default to Tier 3 via the player_tier() lookup.
# T3 rule: only super-rare cards (/50 lower numbered, autos, case hits,
# or PSA 10 + endgame chase) qualify for these players. Confirmed by user.

# ── QB Legends — stricter filter than vintage tier ──────────────────────────
# Per user (May 2026): "all the legends do casehits and autos only for qbs."
# For these names the engine only flags AUTO + CASE HIT + /5-or-lower
# numbered cards. PSA 10 base, regular numbered /N parallels, and chase
# parallel raws are DROPPED for QB legends — the bar is higher than vintage.
#
# Why: these names have such enormous card universes (every Topps Chrome
# era, every Panini insert subset) that without a strict filter the
# dashboard would flood with mid-grade base cards. The user wants only
# the genuine collectible chase to surface.
QB_LEGENDS_HOF: Set[str] = {
    "brett_favre",            # Packers/Jets HOF QB
    "dan_marino",             # Dolphins HOF QB
    "john_elway",             # Broncos HOF QB
    "steve_young",            # 49ers HOF QB
    "troy_aikman",            # Cowboys HOF QB
    # NOTE: Tom Brady and Peyton Manning are intentionally kept in
    # PLAYER_TIER_VINTAGE (broader vintage rules) — their modern hobby
    # is broader than the "legacy HOF QB" cohort and they still anchor
    # all-product card universes.
}


PLAYER_TIER_VINTAGE: Set[str] = {
    # ── Iconic names whose pre-2010 cards have their own market ───────────
    "michael_jordan",          # The all-time NBA anchor
    "kobe_bryant",             # Top-3 NBA vintage
    "tom_brady",               # NFL GOAT vintage
    "peyton_manning",
    "ken_griffey_jr",          # MLB iconic
    "derek_jeter",
    "mickey_mantle",           # 1952 Topps record holder
    "babe_ruth",
    "wayne_gretzky",           # NHL vintage anchor
    "magic_johnson",
    "larry_bird",
    "shaquille_oneal",
    "joe_montana",
    "jerry_rice",
    "barry_sanders",
    "emmitt_smith",
    "walter_payton",
    "willie_mays",
    "hank_aaron",
    "ted_williams",
    "sandy_koufax",
    "nolan_ryan",
    "cal_ripken_jr",
}


def player_tier(player_slug: Optional[str]) -> str:
    """Return 'S', '1', '2', '3', 'VINTAGE', or 'QB_LEGEND' for a player slug.
    Default '3' when unknown. QB_LEGEND has a stricter filter than VINTAGE."""
    if not player_slug:
        return "3"
    key = str(player_slug).strip().lower().replace("-", "_").replace(" ", "_")
    # Check QB_LEGENDS_HOF first — these names take precedence over VINTAGE.
    if key in QB_LEGENDS_HOF:
        return "QB_LEGEND"
    if key in PLAYER_TIER_S:
        return "S"
    if key in PLAYER_TIER_T1:
        return "1"
    if key in PLAYER_TIER_T2:
        return "2"
    if key in PLAYER_TIER_VINTAGE:
        return "VINTAGE"
    return "3"


# ── Chase parallels — endgame ────────────────────────────────────────────────
# Cards bearing these tokens in the title are ALWAYS premium, no grade or
# player tier required. These are the genuine case hits and 1/1-tier parallels.

CHASE_ENDGAME: Set[str] = {
    # ── Cross-product Panini case hits ────────────────────────────────────
    "kaboom",
    "downtown",
    "uptown",
    "color blast",
    "color wheel",
    "color burst",
    "stained glass",
    "manga",
    "prizmania",
    "razzle dazzle",
    "logoman",
    "gold vinyl",
    "superfractor",
    "en fuego",
    "hieroglyphics",
    "iridescent",

    # ── Topps Baseball case hits ──────────────────────────────────────────
    "fanatical",
    "home field advantage",
    "celebration",
    "planetary pursuit",
    "stratospheric stars",
    "all aces",
    "helix",
    "radiating rookies",
    "night terrors",
    "alter egos",
    "heavy lumber",
    "gladiators of the diamond",
    "sapphire selections",
    "fabled phenoms",
    "beam team",
    "savage sluggers",
    "wicked curves",
    "raw power",

    # ── Topps Basketball case hits ────────────────────────────────────────
    "ultra violet",
    "hardwood stars",
    "rock stars",
    "hypernova",
    "cosmic dust",
    "geocentric",
    "starfractor",
    "galaxy greats",
    "high fidelity",
    "monarchs of the game",
    "leviathans",
    "aristocrat",
    "pressure points",
    "patented",                # 2025-26 Topps Chrome Basketball case hit
                               # (1:933 blaster, 1:466 mega), per user
    "glass canvas",            # 2025-26 Topps Chrome Basketball case hit,
                               # screw-down case design, per user
    "advisory",                # 2025-26 Topps Chrome Basketball case hit
    "paradox",                 # 2025-26 Topps Chrome Basketball case hit

    # ── Topps Football case hits (2025-26 NFL Topps return) ───────────────
    "tecmo bowl",
    "kaiju",
    "lightning leaders",
    "game genies",
    "shadow etch",
    "urban legends",
    "fortune 15",
    "finest landmark",
    "1992 finest",
    "centurions",
    "nightmare fuel",
    "hall of chrome",
    "fluidity",
    "rookie premiere",

    # ── Premium SSP subsets ───────────────────────────────────────────────
    # NOTE: field_level and premier_level moved to CHASE_STRONG per user —
    # they aren't true case hits, just rare base levels of Select. Same
    # for club_level / suite_level which were removed entirely.
    "zebra",                  # Select case hit (~1 per case)
    "cracked ice",            # Contenders chase
    "tie dye",                # Select Tie-Dye /25
    "genesis",                # Mosaic chase
    "honeycomb",              # Mosaic chase
    "stained glass",          # Mosaic chase
    "rated rookie auto",      # Donruss / Optic chase
    "rookie kings",           # Donruss Optic case hit SSP, per user
    "sunday kings",           # Donruss Optic case hit SSP, per user
    "blank slate",            # Court Kings case hit SSP, per user
                              # (was previously miscategorized in PSA10)

    # ── Topps Chrome / Bowman refractor parallels ────────────────────────
    "orange refractor",       # /25
    "black refractor",        # /299 baseball, varies
    "red refractor",          # /5
    "atomic refractor",       # case hit
    "gold refractor",         # /50

    # ── Material / patch-auto SSPs ────────────────────────────────────────
    "rookie patch auto",
    "rpa",
    "shimmer autograph",
    "rookie debut patch autograph",
    "shield",                 # NT
    "colossal patch",         # NT
    "booklet patch",
    "diamond signatures",
    "precious metals",
    "american metal",
}


# ── Chase parallels — strong (require player tier OR PSA 10) ─────────────────
# These are real chase parallels in their context but not endgame. Tier 1
# player can hold them raw; Tier 2 needs PSA 10; Tier 3 drops them.

CHASE_STRONG: Set[str] = {
    # ── Prizm Football ────────────────────────────────────────────────────
    "silver prizm",            # Football only — see SPORT_SUPPRESSED
    "blue ice",
    "purple power",
    "purple pulsar",
    "neon green pulsar",
    "red sparkle",
    "snakeskin",
    "disco prizm",
    "lazer",
    "hyper",
    "no huddle",

    # ── Optic Football ────────────────────────────────────────────────────
    "holo",                    # Tier 1 only — Optic chase base parallel
    "pink velocity",
    "aqua",
    "orange",                  # Optic Orange numbered
    "purple shock",
    "blue scope",
    "lazer",
    "black pandora",
    "nebula",

    # ── Mosaic Football ───────────────────────────────────────────────────
    "peacock",                 # Choice
    "no huddle silver",        # Hobby exclusive

    # ── Select Football ───────────────────────────────────────────────────
    # Field/Premier moved here from CHASE_ENDGAME per user — they're rare
    # base tiers but not case hits. Club/Suite removed entirely — not chases.
    "field level",            # Select base tier 5 (rarest), rookie-required
    "premier level",          # Select base tier 4
    "snake skin",
    "dragon scale",

    # ── Topps Chrome / Bowman ─────────────────────────────────────────────
    "refractor",               # Top-tier player only
    "x-fractor",
    "x fractor",
    "mojo refractor",
    "blue refractor",
    "purple refractor",
    "green refractor",
}


# ── Sport-specific case hit promotion ────────────────────────────────────────
# Tokens that ARE case hits in some sports but common inserts in others.
# Read: when (sport, token) is here, treat as CHASE_ENDGAME for that sport.
# Falls back to PSA10_REQUIRED elsewhere.
#
# Example: Kaleidoscopic in Prizm Football is a case hit SSP. In Prizm
# Basketball it's a regular insert (sits alongside Fireworks, Fractal,
# Luck of the Lottery — none of which are case hits).
CHASE_ENDGAME_BY_SPORT: Dict[str, Set[str]] = {
    "NFL": {
        "kaleidoscopic",       # Prizm Football case hit, per user
    },
}


# ── Parallels that require ROOKIE designation OR PSA 10 ─────────────────────
# Per user (May 2026 audit): "silver prizm, blue ice are only good if
# they're rookie. same with no huddle silver." Same logic applies to
# Topps Chrome refractors + Mojo refractors with one exception below.
#
# Detection: title must contain 'rookie' or 'rc' (with word boundaries).
# Without that token AND without PSA 10, the parallel doesn't qualify
# even for Tier 1 players.
CHASE_STRONG_ROOKIE_REQUIRED: Set[str] = {
    "silver prizm",
    "blue ice",
    "no huddle silver",
    "refractor",
    "mojo refractor",
    "mojo",
}


# ── Player-specific bypasses for rookie-required parallels ──────────────────
# Per user: "topps chrome refractors only sellable in ohtani and judge if
# they are not rookie. same with mojo." So for these two players, the
# rookie requirement on refractor/mojo doesn't apply — any year qualifies.
CHASE_STRONG_PLAYER_EXCEPTIONS: Dict[str, Set[str]] = {
    "refractor":       {"shohei_ohtani", "aaron_judge"},
    "mojo refractor":  {"shohei_ohtani", "aaron_judge"},
    "mojo":            {"shohei_ohtani", "aaron_judge"},
}


_ROOKIE_TOKEN_RE = re.compile(r"\b(rookie|rc|1st\s+bowman)\b", re.IGNORECASE)


def title_has_rookie_signal(title: Optional[str]) -> bool:
    """True when the title indicates a rookie card (RC, Rookie, 1st Bowman
    for Bowman Chrome prospects). Used by rookie-required parallel gate."""
    if not title:
        return False
    return bool(_ROOKIE_TOKEN_RE.search(title))


# ── Subsets that ALWAYS require PSA 10 ───────────────────────────────────────
# These are common "fun art" insert subsets that print in the thousands and
# only carry value at gem-mint grade. Show them on the dashboard only when
# already PSA 10 (or PSA 9 + low-pop check).

PSA10_REQUIRED_SUBSETS: Set[str] = {
    # ── Prizm common inserts ──────────────────────────────────────────────
    "prizmatic",
    "contours",
    "fireworks",
    "stellar rookies",
    "rookie gear",
    "future tools",
    "rookie effect",
    "all day",
    "all pro",
    "rookie wave",
    "emergent",
    "visionary",
    "rookie premiere",
    "fireworks insert",
    "color burst",            # Color Burst sometimes — careful, can be chase
    "phenomenon",

    # ── Optic common inserts ──────────────────────────────────────────────
    "rookie kings",
    "rated rookie holo",       # Just "holo" of common rookies
    "purple shock",            # Without numbering = needs grade
    "freedom",
    "fire",

    # ── Mosaic common inserts (non-chase) ─────────────────────────────────
    "stained glass",           # When un-numbered (Mosaic context)
    # NOTE: blank_slate REMOVED — that's a Court Kings case hit, moved to
    # CHASE_ENDGAME per user.
    "national pride",

    # ── Select common inserts ─────────────────────────────────────────────
    "concourse",               # Lowest Select tier — needs grade

    # ── Cross-product low-value inserts ───────────────────────────────────
    # NOTE: kaleidoscopic REMOVED here — it's basketball-tier insert
    # (PSA 10 default) but football case hit (CHASE_ENDGAME via sport
    # override). Handled in CHASE_ENDGAME_BY_SPORT below.
    # NOTE: deca REMOVED — Prizm Deca is its own product line, not an
    # insert subset. Filtering it as "PSA10-required" was incorrect.
    "global reach",
    "touchdown masters",
    "notoriety",
    "epic performers",
    "groovy",
    "prizmatix",
}


# ── Brand blacklist ──────────────────────────────────────────────────────────
# Per user (May 2026): "wild card or leaf listings should not show up in our
# searches." Wild Card Trading Cards and Leaf Trading Cards are secondary
# brands the hobby treats one tier below Panini / Topps / Bowman. Their cards
# do show up in player searches (e.g. "Paul Skenes" returns Wild Card Haunted
# Hits) so we filter post-fetch. Add tokens here when other low-tier brands
# need filtering; matching is case-insensitive substring against the title.

BRAND_BLACKLIST_TOKENS: Set[str] = {
    # Wild Card Trading Cards products
    "wild card",
    "haunted hits",
    # Leaf Trading Cards product lines
    "leaf metal",
    "leaf trinity",
    "leaf draft",
    "leaf best",
    "leaf valiant",
    "leaf inception",
    "leaf certified",
    "leaf chronicles",
    "leaf signature",
    "leaf perfect",
    "leaf flash",
    "in the game",          # Leaf "In The Game" sub-brand
}

# Conservative catch for bare "20XX Leaf" patterns where the product line
# hasn't been listed above. Only matches when a 4-digit year is immediately
# followed by "leaf" as a brand token, so player surnames like "DeShaun
# Watson Leaf" won't false-positive (year doesn't precede the surname).
_LEAF_PREFIX_RE = re.compile(r"\b(19|20)\d{2}\s+leaf\b", re.IGNORECASE)


def is_blacklisted_brand(title: Optional[str]) -> Optional[str]:
    """Return the matched brand token (for logging) or None if the title is
    clean. Case-insensitive substring match against BRAND_BLACKLIST_TOKENS,
    plus a year-prefix regex for bare 'Leaf' product names."""
    if not title:
        return None
    title_lc = title.lower()
    for token in BRAND_BLACKLIST_TOKENS:
        if token in title_lc:
            return token
    if _LEAF_PREFIX_RE.search(title):
        return "leaf_year_prefix"
    return None


# ── Sport-specific demotions ─────────────────────────────────────────────────
# Tokens that are real chase parallels in one sport but base/cheap in another.
# Reads as: (sport_upper, parallel_token_lower) → reason string.

SPORT_SUPPRESSED: Dict[Tuple[str, str], str] = {
    # ── Baseball: Silver / Reactive / Camo Pink are essentially base ──────
    ("MLB", "silver prizm"):     "base_pricing_in_baseball",
    ("MLB", "silver"):           "base_pricing_in_baseball",
    ("MLB", "true silver"):      "base_pricing_in_baseball",
    ("MLB", "mosaic silver"):    "base_pricing_in_baseball",
    ("MLB", "no huddle silver"): "base_pricing_in_baseball",
    ("MLB", "camo pink"):        "base_pricing_in_baseball",
    ("MLB", "reactive"):         "base_pricing_in_baseball",
    ("MLB", "reactive blue"):    "base_pricing_in_baseball",
    ("MLB", "reactive yellow"):  "base_pricing_in_baseball",
    # ── Select "Silver" doesn't exist as chase in ANY sport ────────────────
    ("NFL", "select silver"):    "select_silver_not_a_chase_parallel",
    ("MLB", "select silver"):    "select_silver_not_a_chase_parallel",
    ("NBA", "select silver"):    "select_silver_not_a_chase_parallel",
}


# ── Title-based sport inference ──────────────────────────────────────────────
# When the row's `sport` field is missing (common on wide_window_premium_
# pool_admit rows captured before the engine could stamp identity), we
# fall back to scanning the title for sport-specific insert/subset names.
# Conservative list — only tokens that exist in exactly one sport.
TITLE_SPORT_HINTS: Dict[str, str] = {
    # MLB-only Topps Chrome / Bowman Chrome / Panini Prizm Baseball
    "future tools":            "MLB",
    "all aces":                "MLB",
    "celebration":             "MLB",
    "stratospheric stars":     "MLB",
    "fanatical":               "MLB",
    "home field advantage":    "MLB",
    "wicked curves":           "MLB",
    "savage sluggers":         "MLB",
    "heavy lumber":            "MLB",
    "1st bowman":              "MLB",
    "first bowman":            "MLB",
    "bowman draft":            "MLB",
    "topps chrome black":      "MLB",
    "topps cosmic chrome":     "MLB",
    "bowman chrome":           "MLB",
    "topps finest":            "MLB",
    # NFL-only inserts/products
    "tecmo bowl":              "NFL",
    "kaiju":                   "NFL",
    "lightning leaders":       "NFL",
    "game genies":             "NFL",
    "hall of chrome":          "NFL",
    "rookie premiere":         "NFL",
    "national treasures rpa":  "NFL",
    "colossal patch":          "NFL",
    # NBA-only inserts/products
    "hardwood stars":          "NBA",
    "rock stars":              "NBA",
    "court kings":             "NBA",
    "ultra violet":            "NBA",
    "high fidelity":           "NBA",
}


def infer_sport_from_title(title: Optional[str]) -> Optional[str]:
    """Best-effort sport inference when the row's `sport` field is missing.
    Scans the title for sport-specific insert/subset names. Returns None
    when no confident match — caller must handle that case."""
    if not title:
        return None
    t = title.lower()
    for token, sport in TITLE_SPORT_HINTS.items():
        if token in t:
            return sport
    return None


# ── Numbering thresholds ─────────────────────────────────────────────────────
# Two thresholds, plus a Tier-S-only relaxed threshold.
#
#   NUMBERED_PRIORITY_THRESHOLD (5) — /5 or lower is dashboard HERO tier.
#       Any player, any product. Even Tier 3 nobody. These are too scarce
#       to ignore regardless of who's pictured.
#
#   NUMBERED_PREMIUM_THRESHOLD (50) — /50 or lower is auto-premium for
#       any tier. The user's "/50 or less" rule from yesterday's audit.
#
#   NUMBERED_TIER_S_THRESHOLD (199) — for Tier S apex anchors (LeBron,
#       Wemby, Ohtani, Mahomes, etc.), ANYTHING numbered up to /199
#       qualifies, per the user note: "lower number /150 or lower are
#       good for players like him wemby ohtani. anything thats numbered
#       sells of those guys."

NUMBERED_PREMIUM_THRESHOLD  = 50    # any /50 or lower = auto-premium
NUMBERED_PRIORITY_THRESHOLD = 5     # /5 or lower = dashboard hero tier
NUMBERED_TIER_S_THRESHOLD   = 199   # Tier S relaxed — anything /199 or lower

# Regex to extract the denominator from a card title (e.g., "/25" → 25,
# "33/50" → 50, "PSA 9 #/199" → 199). Returns None if no serial found.
_SERIAL_RE = re.compile(r"(?:#?\s*\d{1,3}\s*)?/\s?(\d{1,4})\b")


def serial_denominator(title: Optional[str]) -> Optional[int]:
    """Extract the serial denominator (the N in /N) from a title. Returns
    None when no serial pattern is found."""
    if not title:
        return None
    match = _SERIAL_RE.search(title)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


# ── PSA grade detection ──────────────────────────────────────────────────────
_PSA10_RE  = re.compile(r"\bpsa\s*10\b",     re.IGNORECASE)
_PSA9_RE   = re.compile(r"\bpsa\s*9(?!\.\d)\b", re.IGNORECASE)
_BGS_10_RE = re.compile(r"\b(?:bgs|sgc|cgc)\s*10\b", re.IGNORECASE)
_BGS_95_RE = re.compile(r"\bbgs\s*9\.5\b",   re.IGNORECASE)


def title_grade(title: Optional[str]) -> Optional[str]:
    """Return 'gem_mint' (PSA 10 / BGS 10 / SGC 10 / CGC 10 / BGS 9.5),
    'mint' (PSA 9), or None."""
    if not title:
        return None
    if _PSA10_RE.search(title) or _BGS_10_RE.search(title) or _BGS_95_RE.search(title):
        return "gem_mint"
    if _PSA9_RE.search(title):
        return "mint"
    return None


# ── Public decision API ──────────────────────────────────────────────────────

def evaluate_card_target(
    title: str,
    sport: Optional[str] = None,
    player_slug: Optional[str] = None,
    parallel_family: Optional[str] = None,
    product_family: Optional[str] = None,
) -> Dict[str, Any]:
    """Decide whether a card qualifies as a SnipeWins target.

    Returns a dict with:
        qualifies:    bool   — final decision
        reason:       str    — human-readable reason
        priority:     int    — 0 (drop) ... 100 (hero); higher floats to top
        player_tier:  int    — 1, 2, or 3
        signals:      dict   — what triggered (auto, numbered, endgame, etc.)
    """
    title_lc = (title or "").lower()
    sport_u  = (sport or "").upper()
    parallel_lc = (parallel_family or "").lower()
    product_lc  = (product_family or "").lower()

    # When the row didn't carry a sport tag (common on wide_window_premium_
    # pool_admit rows), try to infer it from the title. Without this,
    # sport-suppression checks skip and noise like baseball Silver Prizm
    # leaks through.
    if not sport_u:
        inferred = infer_sport_from_title(title)
        if inferred:
            sport_u = inferred.upper()

    signals: Dict[str, Any] = {}
    signals["sport_resolved"] = sport_u or "?"

    # 0a. Brand blacklist — drop low-tier brands (Wild Card, Leaf) before any
    # other check. These titles surface in player searches but represent a tier
    # of the hobby we deliberately don't track.
    blacklisted_brand = is_blacklisted_brand(title)
    if blacklisted_brand:
        return {
            "qualifies":   False,
            "reason":      f"brand_blacklisted:{blacklisted_brand}",
            "priority":    0,
            "player_tier": player_tier(player_slug),
            "signals":     {"brand_blacklisted": blacklisted_brand},
        }

    # 0. Hard sport-suppression first — drop irrespective of everything else.
    suppress_key_pf = (sport_u, parallel_lc)
    if suppress_key_pf in SPORT_SUPPRESSED:
        return {
            "qualifies":   False,
            "reason":      SPORT_SUPPRESSED[suppress_key_pf],
            "priority":    0,
            "player_tier": player_tier(player_slug),
            "signals":     {"sport_suppressed": SPORT_SUPPRESSED[suppress_key_pf]},
        }
    # Also check sport-suppressed tokens in title (for when parallel_family is empty)
    for (s_sport, token), reason in SPORT_SUPPRESSED.items():
        if s_sport != sport_u:
            continue
        if token in title_lc:
            return {
                "qualifies":   False,
                "reason":      reason,
                "priority":    0,
                "player_tier": player_tier(player_slug),
                "signals":     {"sport_suppressed_title": reason},
            }

    has_auto = bool(re.search(r"\b(auto|autograph|signed)\b", title_lc))
    serial   = serial_denominator(title)
    grade    = title_grade(title)
    tier     = player_tier(player_slug)

    signals.update({
        "has_auto":         has_auto,
        "serial":           serial,
        "grade":            grade,
        "player_tier":      tier,
    })

    # ── Universal admits (apply to all tiers) ─────────────────────────────

    # 1. Autograph — always qualifies. Even Tier 3 auto of a no-name rookie
    # is worth flagging because the auto pool is small enough that ROI on
    # graded breakouts is real.
    if has_auto:
        return {
            "qualifies":   True,
            "reason":      "auto_premium",
            "priority":    90 if tier in {"S", "1"} else 78 if tier == "2" else 65,
            "player_tier": tier,
            "signals":     signals,
        }

    # 2. Ultra-rare numbering — always qualifies, dashboard hero priority.
    # /5 or lower bypasses tier and grade entirely.
    if serial is not None and serial <= NUMBERED_PRIORITY_THRESHOLD:
        return {
            "qualifies":   True,
            "reason":      f"numbered_priority_/{serial}",
            "priority":    100,
            "player_tier": tier,
            "signals":     signals,
        }
    if serial is not None and serial <= NUMBERED_PREMIUM_THRESHOLD:
        return {
            "qualifies":   True,
            "reason":      f"numbered_premium_/{serial}",
            "priority":    85 if tier in {"S", "1"} else 70,
            "player_tier": tier,
            "signals":     signals,
        }

    # 3. Endgame chase — always qualifies for Tier S/1/2; Tier 3 only with PSA 10.
    # Check the universal CHASE_ENDGAME list AND the sport-specific override
    # list (e.g. kaleidoscopic is football-only endgame).
    endgame_tokens = set(CHASE_ENDGAME) | CHASE_ENDGAME_BY_SPORT.get(sport_u, set())
    for chase in endgame_tokens:
        if chase in title_lc:
            signals["chase_endgame"] = chase
            if tier in {"S", "1", "2", "VINTAGE"}:
                return {
                    "qualifies":   True,
                    "reason":      f"chase_endgame:{chase}",
                    "priority":    95 if tier == "S" else 88,
                    "player_tier": tier,
                    "signals":     signals,
                }
            # Tier 3 endgame chase — qualifies only at PSA 10 (small-name
            # case hits still have ROI when graded)
            if grade == "gem_mint":
                return {
                    "qualifies":   True,
                    "reason":      f"tier3_endgame_psa10:{chase}",
                    "priority":    70,
                    "player_tier": tier,
                    "signals":     signals,
                }
            return {
                "qualifies":   False,
                "reason":      f"tier3_endgame_needs_psa10:{chase}",
                "priority":    0,
                "player_tier": tier,
                "signals":     signals,
            }

    # ── QB Legends — strict filter, before vintage ────────────────────────
    # Per user (May 2026): for HOF QB legends, only auto + case hit + /5
    # qualify. We've ALREADY handled auto + /5-lower + endgame chase in the
    # universal admits above (they return early). So if we reach here with
    # tier == "QB_LEGEND", nothing in our admit list matched — drop.
    # PSA 10 base, regular /N numbered, chase-strong-only raw all fail
    # this filter intentionally.
    if tier == "QB_LEGEND":
        return {
            "qualifies":   False,
            "reason":      "qb_legend_needs_auto_or_casehit_or_5_lower",
            "priority":    0,
            "player_tier": tier,
            "signals":     signals,
        }

    # ── Tier S apex anchors ───────────────────────────────────────────────
    # Per user: "anything thats numbered sells of those guys."
    # Per user: "any Prizm PSA 10 of him flies" (re LeBron).
    # Rules:
    #   1. Any /N numbered up to /199 → qualifies (relaxed threshold)
    #   2. Any PSA 10 → qualifies
    #   3. CHASE_STRONG parallel raw → qualifies
    #   4. Bare base raw → DROP (too noisy)
    # NOTE: /5-lower numbered + auto + endgame chase already qualified above.
    if tier == "S":
        # Numbered /6 through /199 — Tier S only, more generous than the
        # /50 universal threshold.
        if serial is not None and serial <= NUMBERED_TIER_S_THRESHOLD:
            return {
                "qualifies":   True,
                "reason":      f"tier_S_numbered_/{serial}",
                "priority":    82,
                "player_tier": tier,
                "signals":     signals,
            }
        # PSA 10 of a Tier S player — qualify regardless of product
        if grade == "gem_mint":
            return {
                "qualifies":   True,
                "reason":      "tier_S_psa10",
                "priority":    80,
                "player_tier": tier,
                "signals":     signals,
            }
        # Raw CHASE_STRONG parallel of Tier S — qualify, with the rookie
        # gate for parallels in CHASE_STRONG_ROOKIE_REQUIRED. Ohtani/Judge
        # have the refractor/mojo player bypass.
        player_slug_norm = (player_slug or "").strip().lower().replace("-", "_").replace(" ", "_")
        for strong in CHASE_STRONG:
            if strong in title_lc:
                signals["chase_strong"] = strong
                if strong in CHASE_STRONG_ROOKIE_REQUIRED:
                    is_rookie = title_has_rookie_signal(title_lc)
                    has_player_bypass = player_slug_norm in CHASE_STRONG_PLAYER_EXCEPTIONS.get(strong, set())
                    if not is_rookie and not has_player_bypass:
                        signals["rookie_required_blocked"] = strong
                        continue
                return {
                    "qualifies":   True,
                    "reason":      f"tier_S_strong_parallel:{strong}",
                    "priority":    78,
                    "player_tier": tier,
                    "signals":     signals,
                }
        # Bare base Tier S raw — drop. Even LeBron, Mahomes etc. — raw base
        # without grade or numbering is too low-margin to flood the dashboard.
        return {
            "qualifies":   False,
            "reason":      "tier_S_base_raw_not_targeted",
            "priority":    0,
            "player_tier": tier,
            "signals":     signals,
        }

    # ── Vintage — pre-2010 cards of historic anchors ──────────────────────
    # Vintage rules differ — even base 1980s/1990s cards of Jordan/Mantle
    # can move at the right grade. Default to qualify; downstream MV will
    # decide if it's a real deal.
    if tier == "VINTAGE":
        # Auto-include but at moderate priority; let MV/comp tell the truth
        return {
            "qualifies":   True,
            "reason":      "vintage_anchor",
            "priority":    75,
            "player_tier": tier,
            "signals":     signals,
        }

    # ── Tier 1 hot mover — raw chase parallel OR PSA 10 base qualifies ────
    if tier == "1":
        # PSA 10 base of T1 hot mover — qualifies
        if grade == "gem_mint":
            return {
                "qualifies":   True,
                "reason":      "tier1_psa10_base",
                "priority":    75,
                "player_tier": tier,
                "signals":     signals,
            }
        # T1 with a CHASE_STRONG parallel — qualifies raw, with rookie gate
        # for the parallels in CHASE_STRONG_ROOKIE_REQUIRED.
        for strong in CHASE_STRONG:
            if strong in title_lc:
                signals["chase_strong"] = strong
                # Rookie-required parallel gate: silver prizm, blue ice,
                # no huddle silver, refractor, mojo only qualify raw when
                # the card is a rookie. Ohtani/Judge get a player bypass
                # for refractor/mojo specifically.
                player_slug_norm = (player_slug or "").strip().lower().replace("-", "_").replace(" ", "_")
                if strong in CHASE_STRONG_ROOKIE_REQUIRED:
                    is_rookie = title_has_rookie_signal(title_lc)
                    has_player_bypass = player_slug_norm in CHASE_STRONG_PLAYER_EXCEPTIONS.get(strong, set())
                    if not is_rookie and not has_player_bypass:
                        # Doesn't pass rookie gate — drop and let the loop
                        # check for any OTHER strong parallel match before
                        # giving up. (rare in practice but possible.)
                        signals["rookie_required_blocked"] = strong
                        continue
                return {
                    "qualifies":   True,
                    "reason":      f"tier1_strong_parallel:{strong}",
                    "priority":    72,
                    "player_tier": tier,
                    "signals":     signals,
                }
        # T1 common-insert subset that requires PSA 10 — drop unless graded
        for subset in PSA10_REQUIRED_SUBSETS:
            if subset in title_lc:
                signals["psa10_required_subset"] = subset
                return {
                    "qualifies":   False,
                    "reason":      f"tier1_insert_subset_needs_psa10:{subset}",
                    "priority":    0,
                    "player_tier": tier,
                    "signals":     signals,
                }
        # T1 bare base raw — ADMIT at low priority. Previously dropped to
        # keep the dashboard tight, but felt-abundance is the conversion
        # lever during trials. A raw Cooper Flagg base is still interesting
        # to someone shopping for sub-$30 starter cards. Time-sort on the
        # Ending Soon page means these don't crowd out higher-tier signals
        # — they just fill the feed.
        return {
            "qualifies":   True,
            "reason":      "tier1_base_raw_speculative",
            "priority":    20,
            "player_tier": tier,
            "signals":     signals,
        }

    # ── Tier 2 cooled / speculative — PSA 10 + chase parallel required ────
    if tier == "2":
        if grade == "gem_mint":
            # PSA 10 of a T2 player — check if it has a chase parallel
            for strong in CHASE_STRONG:
                if strong in title_lc:
                    signals["chase_strong"] = strong
                    return {
                        "qualifies":   True,
                        "reason":      f"tier2_psa10_strong_parallel:{strong}",
                        "priority":    65,
                        "player_tier": tier,
                        "signals":     signals,
                    }
            # PSA 10 base of T2 — lower priority but still qualifies
            return {
                "qualifies":   True,
                "reason":      "tier2_psa10_base",
                "priority":    55,
                "player_tier": tier,
                "signals":     signals,
            }
        # T2 raw with PSA10-required subset — drop
        for subset in PSA10_REQUIRED_SUBSETS:
            if subset in title_lc:
                signals["psa10_required_subset"] = subset
                return {
                    "qualifies":   False,
                    "reason":      f"tier2_insert_subset_needs_psa10:{subset}",
                    "priority":    0,
                    "player_tier": tier,
                    "signals":     signals,
                }
        # T2 raw chase parallel — ADMIT at low priority (previously dropped
        # because "needs PSA 10"). A raw Caleb Williams chase parallel still
        # has bid value even ungraded; the user can decide.
        for strong in CHASE_STRONG:
            if strong in title_lc:
                signals["chase_strong"] = strong
                return {
                    "qualifies":   True,
                    "reason":      f"tier2_strong_parallel_raw:{strong}",
                    "priority":    30,
                    "player_tier": tier,
                    "signals":     signals,
                }
        # Nothing else matched — keep dropping bare T2 raw base since those
        # are genuinely too noisy. (The line we just relaxed catches the
        # "raw with chase parallel" sweet spot.)
        return {
            "qualifies":   False,
            "reason":      "tier2_no_premium_signal",
            "priority":    0,
            "player_tier": tier,
            "signals":     signals,
        }

    # ── Tier 3 default — admit graded PSA 10 at low priority ────────────
    # ABUNDANCE-2026-05-12: previously this dropped T3 PSA 10 base ("too
    # noisy unless other signals"). Reversing — a graded gem-mint of even
    # a tier-3 player has real market value to the right buyer, and the
    # whole point of the trial dashboard is that the user sees enough
    # inventory to feel the curation depth. /5-lower and endgame-chase
    # cards are already handled higher up at their proper high priority.
    if grade == "gem_mint":
        return {
            "qualifies":   True,
            "reason":      "tier3_psa10_speculative",
            "priority":    25,
            "player_tier": tier,
            "signals":     signals,
        }
    return {
        "qualifies":   False,
        "reason":      "no_premium_signal_matched",
        "priority":    0,
        "player_tier": tier,
        "signals":     signals,
    }
