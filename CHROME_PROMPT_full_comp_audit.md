# Chrome Prompt — Full Comp Audit (SnipeWins live)

Paste into Claude-in-Chrome. Audit the **comps currently on screen** at
**https://app.snipewins.com** (log in as Chadwell). Be a skeptic. Quote every card
title verbatim. For each comp, your job is to judge whether it's the **EXACT variant**
or a substitute, using these 7 attributes: player, year, set, card #, parallel/finish,
print run, grade. A different set, card #, or parallel = NOT exact.

Run after the latest deploy is Live and the board has re-priced (values changed from last audit).

---

## 0 — Snapshot
Report up top:
- Ending Soon: "Updated … ago", total cards, # with a target bid, % NO COMPS.
- Steals: STRIKE / CLOSE / OFFER / PENDING counts + "Updated … ago".
- **Sport mix of the Ending Soon board**: roughly how many cards are MLB vs NFL vs NBA?
  (We just rebalanced discovery to NFL 40 / MLB 35 / NBA 25 — confirm NBA and NFL are
  actually showing now, not just baseball.)

## 1 — Go card-by-card through the visible board (top ~25 cards)
For EACH card on screen, make one row:

`"<exact title>" | MV $ | badge (STRIKE/WAIT/ESTIMATE/NO COMPS) | basis (scp_exact/scp_proxy) | comp used (title + set) | EXACT? ✅/❌`

Mark ❌ when the comp differs from the listing on **set, card #, parallel, or print run.**
For ❌ rows, say in 3-4 words what's wrong (e.g., "wrong parallel", "diff card #",
"insert vs base", "cross-set", "cross-year").

## 2 — Targeted checks on the recent fixes
Confirm these specific behaviors:
- **2a. Card-number discipline:** any card whose comp has a DIFFERENT card # than the
  listing should be `scp_proxy`/ESTIMATE, NOT a confident `scp_exact` STRIKE. Flag any
  exact match where the numbers differ.
- **2b. Parallel discipline:** a base card must NOT be priced off a rarer parallel of the
  same number (no base→Blue Refractor inflation), and a "Green Refractor" must not comp to
  a "Blue Refractor". Flag any parallel mismatch.
- **2c. Proxy ≠ STRIKE:** any `scp_proxy`/ESTIMATE value should show as ESTIMATE/NEEDS
  COMPS, NOT STRIKE. Flag any proxy still flashing STRIKE.
- **2d. Distinct sets:** Chrome Platinum / Chrome Update / Cosmic / Sapphire cards should
  comp to their OWN set, never plain Topps Chrome. Flag any that don't.

## 3 — Sport balance + legends
- **3a.** Find at least 3 NBA cards and 3 NFL cards on the board. For each, report
  `title | MV | comp set | EXACT?`. (Confirming the 3-sport expansion produced real,
  priced cards — not just baseball.)
- **3b.** If any **Joe Montana / Jerry Rice / Barry Sanders / Randy Moss** modern cards
  appear, confirm they price as exact (they should — those legends are loaded).
- **3c.** Flag any **Walter Payton** card — it will be NO COMPS (known gap, expected).

## 4 — Dangerous-STRIKE scan (most important)
Scan every STRIKE on the board AND the top 20 Steals strikes. A STRIKE tells the user
"this is a real deal." For each STRIKE, sanity-check: is the comp genuinely the same card?
List any STRIKE where the comp is wrong-set / wrong-#/ wrong-parallel — these are the
dangerous ones that could make a user overbid. Title + what's wrong + MV + bid.

## 5 — Coverage harvest (drives next downloads)
Group every NO-COMPS or proxy/cross-set card by SET, e.g.:
```
2018 Bowman Chrome — 2 cards NO COMPS
2026 Topps Dynasty — 3 cards proxy (auto inserts)
2025 Panini Prizm Basketball — 1 card NO COMPS
```
This is the shopping list for what to load next.

---

## Report format
```
FULL COMP AUDIT — <date/time>  | re-priced? YES/NO
Snapshot: board <n> cards (<MLB%>/<NFL%>/<NBA%>), <%> NO COMPS · Steals <S/C/O/P>

1. BOARD CARD-BY-CARD (top 25):
   "<title>" | $MV | badge | basis | comp (title/set) | EXACT ✅/❌ (<why>)
   ... 25 rows ...

2. Fix checks:
   2a card-# discipline: PASS/FAIL — <exceptions>
   2b parallel discipline: PASS/FAIL — <exceptions>
   2c proxy≠strike: PASS/FAIL — <exceptions>
   2d distinct sets: PASS/FAIL — <exceptions>

3. Sport/legends:
   3a NBA x3 + NFL x3: <rows>
   3b legends exact? <detail>
   3c Payton: <NO COMPS / titles>

4. DANGEROUS STRIKES (verbatim): <list or NONE>

5. COVERAGE HARVEST (by set): <grouped list>

TALLY: exact ___ / proxy ___ / no-comps ___ of ___ cards judged
```

The two things that matter most: **Section 4** (any STRIKE built on a wrong comp — those
are the ones that lose money) and **Section 1's EXACT ✅/❌ tally** (what fraction of the
board is now a true exact match vs an estimate).
