# Chrome Prompt — Afternoon Audit (did the fixes land + keep working the pipeline)

Paste into Claude-in-Chrome. Audit **https://app.snipewins.com** (log in as Chadwell).
Two jobs: (1) confirm this morning's matcher fixes + round-3 coverage actually landed,
and (2) harvest the next round of comp problems. Be a skeptic, quote titles verbatim,
judge each comp EXACT ✅ / substitute ❌ on the 7 attributes.

**Run only after the latest deploy is Live AND the board re-priced** (values changed). If
unchanged, report "NOT RE-PRICED" and stop.

---

## 0 — Snapshot
- Ending Soon: "Updated … ago", total cards, # targeted, % NO COMPS.
- **Sport mix: MLB vs NFL vs NBA counts.** Did NBA grow now that 2020-22 Prizm/Mosaic/
  Select/Optic basketball loaded? (Was ~3% / 4 cards this morning.)
- Steals: STRIKE / CLOSE / OFFER / PENDING.
- Tally: exact ___ / proxy ___ / no-comps ___ of ___ judged.

## 1 — Did this morning's matcher fixes land? (PASS/FAIL each)
- **1a. Parallel-name discipline.** Find any 2025 Topps Chrome Platinum card with a specific
  parallel (Blue Mini Diamond, Gold Wave, Blue Lava). Each must comp to its OWN parallel
  name, not just the color. Specifically: **Blue Mini Diamond → "[Blue Mini-Diamond Refractor]"**
  (NOT Blue Lava), **Gold Wave → "[Gold Wave]"** (NOT Gold Refractor). Report MV + comp.
- **1b. The Bo Nix $6,200.** If `Bo Nix … Tri-Color Prizm /249 #117` is still on the board,
  it must now be ~**$160** off a "[Tri-Color Prizm]" comp, NOT $6,200 off Cosmic. (May have
  expired — note if gone.)
- **1c. Patch / dual / RPA gate.** Find any patch auto, RPA, dual auto, or combo card. It must
  show **NO COMPS or ESTIMATE** — never a confident STRIKE off a plain solo/base comp. List
  each `title | MV | badge | comp`. Flag any patch/dual still flashing STRIKE off a solo comp.

## 2 — Did round-3 coverage fill the gaps? (the new sets)
For each, report whether it now prices (exact/proxy) or still NO COMPS:
- **2a.** Any **2020-21 / 2021-22 / 2022-23 Panini Prizm/Mosaic/Select Basketball** card
  (Anthony Edwards, LaMelo Ball, etc.) — do they price now? (Were NO COMPS this morning.)
- **2b.** Any **2018 Topps Chrome Update** (Juan Soto / Acuna RC auto), **2021 Gypsy Queen**,
  **2019 Bowman Draft Chrome** — price now?
- **2c.** Any **National Treasures / Flawless / Immaculate** patch auto or RPA — do the
  high-end football/basketball cards now find their patch product, or still NO COMPS?

## 3 — Fresh dangerous-STRIKE sweep (most important — keep working the pipeline)
Scan EVERY STRIKE on the board + top 20 Steals strikes. For each, is the comp truly the same
card? List every STRIKE whose comp is wrong on set / # / parallel / insert-vs-base /
dual-vs-solo / patch-vs-plain. Format: `title | MV | bid | what's wrong`. Call out anything
NEW. (Goal: the complete list of money-losing strikes that remain.)

## 4 — Parallel-name spot check (the rule we just shipped)
Pick 8 cards that name a SPECIFIC parallel (any sport). For each, does the comp's parallel
name match exactly? `title | listing parallel | comp parallel | match ✅/❌`. This tells us how
well the design-word rule generalizes beyond the cards we tested.

## 5 — Coverage harvest (next downloads)
Group every NO-COMPS / cross-set card by SET. Flag especially any set that SHOULD be loaded
now (from round 3) but still shows NO COMPS — that means a sync/naming issue to investigate.

---

## Report format
```
AFTERNOON AUDIT — <date/time> | re-priced? Y/N
Snapshot: <n> cards (MLB <n>/NFL <n>/NBA <n>), <%> NO COMPS · Steals <S/C/O/P>
Tally: exact __ / proxy __ / no-comps __ of __

1 Matcher fixes:
  1a parallel-name (Mini-Diamond/Gold Wave): PASS/FAIL — <detail>
  1b Bo Nix $6,200: <new value or GONE>
  1c patch/dual/RPA gate: PASS/FAIL — <any wrong strikes>

2 Round-3 coverage:
  2a NBA 2020-22 Prizm/Mosaic/Select: <prices now? Y/N + examples>
  2b vintage baseball gaps: <Y/N>
  2c NT/Flawless/Immaculate patch: <Y/N>

3 DANGEROUS STRIKES (full list, verbatim): <list or NONE>

4 Parallel-name spot check (8 cards): <rows>

5 COVERAGE HARVEST (by set): <grouped + flag should-be-loaded-but-blank>

TODAY'S NEXT TARGETS (priority order): ...
```

The two things that matter most: **Section 1c + 3** (are patch/dual cards safe now, and what
dangerous strikes remain) and **Section 0/2a** (did NBA finally fill in with the new basketball
sets — the real test of the 3-sport push).
