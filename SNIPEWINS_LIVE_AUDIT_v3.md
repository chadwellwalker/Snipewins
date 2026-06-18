# SnipeWins Live Audit v3 — for Claude-in-Chrome

Re-audit after: (a) persistent disk wired (`SNIPEWINS_DATA_DIR=/data`) so the pool
no longer wipes on deploy, (b) `near_end` budget capped, (c) Bowman≠Topps fix,
(d) "SnipeWins estimate" killed on serialized cards. Plus a NEW area to
investigate: **shipping cost**.

Be a skeptic. Quote exact titles verbatim. Capture every failure title so the
engineer can reproduce it.

Site: https://app.snipewins.com (logged in as Chadwell)

---

## STOP — gate before starting
Don't start until Render shows the newest commit Live AND the board has re-priced.
Evidence of re-price: dollar values differ from audit v2, OR "Updated … ago" is recent.
If values are unchanged from v2, report "NOT RE-PRICED YET" and wait.

---

## Section P — Persistence & freshness (the operational fixes)
- **P1.** Ending Soon "Updated … ago" and Steals "Updated … ago". Report both.
  (v2 was 9h 39m / 13h 29m — we want these FRESH now, minutes not hours.)
- **P2.** Steals tab counts: STRIKE / CLOSE / OFFER / PENDING. (v2 was 0/0/0/2,840.)
  Did BINs move OUT of PENDING into valued states? Report new numbers.
- **P3.** Board card count + how many have a target bid + rough % NO COMPS.

## Section B — Bowman ≠ Topps (cross-product fix)
- **B1.** Find "James Wood 2025 Bowman Chrome Adios! Orange Rookie #Ad-4 /25".
  - v2 = **$406** (matched a Topps Chrome card). Expected now: **~$129** and the
    comp's set should say **Bowman Chrome**, NOT "2025 Topps Chrome".
  - Open View Comps and report the comp's set/year. PASS if Bowman, FAIL if Topps.
- **B2.** Find any other **Bowman** card (Bowman Chrome, Bowman Draft, Bowman Sapphire).
  Open View Comps. Every comp's set should be a **Bowman** set, never "Topps Chrome"
  or "Topps" flagship. Harvest any that pull a Topps comp → exact title.
- **B3.** Inverse: any **Topps Chrome / Topps** card whose comp says **Bowman** → harvest it.

## Section E — "SnipeWins estimate" should be gone on serialized cards
- **E1.** Find "2026 Topps Series 2 Paul Skenes Orange Chrome Mojo Refractor Auto /25".
  - v2 = **$200 "SnipeWins estimate"** (basis no_scp_match_serialized). Expected now:
    **NO COMPS** (no dollar value, no estimate).
- **E2.** Scan the board for ANY card still showing "≈ SnipeWins estimate" as its MV
  basis on a **serial-numbered** card (/1–/50 in the title). Each one is a failure —
  copy the exact title. (Non-serial commons showing an estimate are OK for now.)

## Section S — SHIPPING (new — investigate, don't expect a fix yet)
We do NOT yet factor shipping into the spread/target. I want data to size the fix.
- **S1.** Pick 6 cards on the board that show a "BELOW MV / spread" badge or STRIKE.
  For each, open the eBay listing (View on eBay) and report:
  `title | current bid | shipping cost | SnipeWins MV | SnipeWins target | spread badge`
- **S2.** For each, compute **bid + shipping** and compare to the spread badge. Does the
  "steal" still look like a steal once shipping is added? Flag any where shipping
  erases the margin (e.g. "$8 below MV" but $5+ shipping). This tells us how often
  the missing-shipping bug creates fake steals.
- **S3.** Note any listings with unusually high shipping (>$10) or free shipping, so we
  know the range we're dealing with.

## Section R — Regression check (don't trust, verify)
Confirm these known-good values did NOT break (re-price shouldn't move them):
- **R1.** Juan Soto Topps Chrome Platinum Gold /50 → ~$50 (comp "Juan Soto [Gold] #200")
- **R2.** Jackson Holliday Rookie Auto /499 → ~$200 (auto comp, NOT base #88 ~$15)
- **R3.** Any Juan Soto Black Refractor /10 → should be a high value (~$400+), comp "[Black]"
- **R4.** Ashton Jeanty / Caleb Williams Panini autos → Panini comps, sane values
Report any that went to NO COMPS or changed wildly.

## Section X — Insert coverage (harvest only)
Cards that are INSERTS (named subsets like "Adios!", "Electric Sluggers", "Stars",
"All-Stars") often aren't in the store and fall to a base parallel (over/under-valued).
- **X1.** Find 5 insert cards on the board. Report `title | MV | comp used`. We're
  collecting which insert sets to load next — copy exact titles.

---

## Report format
```
DEPLOY AUDIT v3 — <date/time>
Re-priced? YES/NO (evidence)
P1 freshness: board <t>, steals <t>   (v2: 9h39m / 13h29m)
P2 steals: <strike/close/offer/pending>  moved from PENDING? YES/NO
P3 board: <n> cards / <n> targeted / <%> NO COMPS

B1 James Wood: $406 -> $<new>  comp set=<...>  PASS/FAIL
B2 Bowman cards pull only Bowman comps: PASS/FAIL — <failures>
B3 Topps cards pull only Topps comps: PASS/FAIL — <failures>

E1 Skenes /25: $200 -> <NO COMPS/?>  PASS/FAIL
E2 serialized cards still estimating: <exact titles or NONE>

S1 shipping table:
   "<title>" | bid $<x> | ship $<y> | MV $<z> | target $<t> | <badge>
   ... (6 rows)
S2 fake steals once shipping added: <titles or NONE>
S3 shipping range observed: <low>–<high>

R1–R4 regressions: PASS/FAIL — <detail>
X1 insert cards (harvest): <title | MV | comp> x5

NEW FAILURES TO FIX (verbatim titles):
1. ...
```

The two things that matter most this round: **(1)** did persistence make the board/Steals
go FRESH and start clearing PENDING (P1/P2), and **(2)** the shipping table (S1/S2) — that
data decides how we build the shipping-aware spread.
