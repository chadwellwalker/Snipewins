# Chrome Prompt — Morning Baseline Audit (SnipeWins live)

Paste into Claude-in-Chrome. Audit **https://app.snipewins.com** (log in as Chadwell).
This is the first audit of the day — establish current state after a full overnight of
discovery + re-pricing, and pinpoint today's targets. Be a skeptic, quote titles verbatim,
judge each comp EXACT ✅ / substitute ❌ on the 7 attributes (player, year, set, card #,
parallel, print run, grade).

---

## 0 — Snapshot (the morning state)
- Ending Soon: "Updated … ago", total cards, # targeted, % NO COMPS.
- **Sport mix: count MLB vs NFL vs NBA.** This is the #1 question — after a full night,
  did the 40/35/25 rebalance fill in? Report exact counts + rough %.
- Steals: STRIKE / CLOSE / OFFER / PENDING.
- Overall tally: exact ___ / proxy ___ / no-comps ___ of ___ judged. (Was 54% exact last night.)

## 1 — Are last night's two dangerous STRIKEs still live?
Find each (board or Steals search). Report MV + comp + still-dangerous? Y/N:
- **1a.** `Bo Nix 2024 Select Premier Level Rookie Tri-Color Prizm /249 #117` — was $6,200
  off a **Cosmic Prizm** comp (wrong parallel, same #). Still STRIKE at a fake high MV?
- **1b.** `2024 Panini Donruss Rated Rookie Caleb Williams Red Wave Prizm PSA 10` — was
  $1,228 off a **2024 Panini Prizm** comp (wrong set). Still STRIKE?

## 2 — Fresh dangerous-STRIKE sweep (most important)
Scan EVERY STRIKE on the Ending Soon board + the top 20 Steals strikes. For each, is the
comp truly the same card? List every STRIKE whose comp is wrong on set / card # / parallel /
insert-vs-base / dual-vs-solo / patch-vs-plain. Format: `title | MV | bid | what's wrong`.
Call out anything NEW that appeared overnight. (Goal: a complete list of money-losing strikes.)

## 3 — Did the wins hold overnight?
- **3a. Proxy ≠ STRIKE:** any `scp_proxy`/ESTIMATE card flashing STRIKE? (Should be none.)
- **3b. Card-# discipline:** any `scp_exact` whose comp # ≠ listing #? (Should be none.)
- **3c. Distinct sets:** any Chrome Platinum / Update / Cosmic / Sapphire / Chrome Black card
  comped to plain Topps Chrome? List them.
- **3d. Parallel mismatch (the new theme):** any `scp_exact` where the listing names one
  parallel (e.g. "Tri-Color", "X-Fractor", "Black Refractor") but the comp is a DIFFERENT
  named parallel of the same card #. List every one — this is what we're fixing today.

## 4 — NBA reality check
- How many NBA cards are on the board total? List them with `title | MV | EXACT?`.
- Do NBA cards that DO appear price correctly (now that Prizm/Select/Mosaic/Hoops/Court
  Kings/Revolution are loaded), or are they NO COMPS / proxy?

## 5 — Coverage harvest (today's downloads)
Group every NO-COMPS / cross-set card by SET, e.g. `2020 Panini Prizm Basketball — 2 NO COMPS`.

---

## Report format
```
MORNING AUDIT — <date/time> | re-priced? Y/N
Snapshot: <n> cards (MLB <n>/NFL <n>/NBA <n>), <%> NO COMPS · Steals <S/C/O/P>
Tally: exact __ / proxy __ / no-comps __ of __  (was 54% exact)

1 Last night's dangerous strikes:
  1a Bo Nix Tri-Color: $<v> comp <...> still dangerous? Y/N
  1b Caleb Donruss→Prizm: $<v> comp <...> still dangerous? Y/N

2 DANGEROUS STRIKES (full list, verbatim): <title | MV | bid | what's wrong> ...

3 Wins held?
  3a proxy≠strike: PASS/FAIL
  3b card-#: PASS/FAIL
  3c distinct sets: PASS/FAIL — <exceptions>
  3d parallel mismatch: <list of exact-but-wrong-parallel cards>

4 NBA: <count> cards — <rows>

5 COVERAGE HARVEST (by set): <grouped>

TODAY'S TARGETS (verbatim titles, priority order): ...
```

The two things that matter most this morning: **Section 2** (the complete list of dangerous
STRIKEs, so I can fix the parallel-must-match rule against real cases) and **Section 0/4**
(did NBA finally fill in overnight, or do we need to dig into discovery).
