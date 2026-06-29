# Chrome Prompt — End-of-Day Audit (SnipeWins live)

Paste into Claude-in-Chrome. Audit **https://app.snipewins.com** (log in as Chadwell).
Goal: confirm today's fixes landed and leave a clean to-do list for tomorrow. Be a
skeptic, quote titles verbatim. Judge each comp as EXACT ✅ or substitute ❌ on the
7 attributes (player, year, set, card #, parallel, print run, grade).

**Run only after the latest deploy is Live AND the board re-priced** (values changed,
"Updated" is recent). If unchanged from the last audit, report "NOT RE-PRICED" and stop.

---

## 0 — Snapshot
- Ending Soon: "Updated … ago", total cards, # targeted, % NO COMPS.
- **Sport mix of the board: MLB vs NFL vs NBA counts.** (We rebalanced discovery to
  NFL 40 / MLB 35 / NBA 25 — did it take effect, or is it still ~96% baseball?)
- Steals: STRIKE / CLOSE / OFFER / PENDING.

## 1 — Today's fixes: did they land? (PASS/FAIL each)
- **1a. The $29K bug.** Find any `2018 Bowman Chrome Shohei Ohtani #1` (PSA 10 or SGC 10).
  Expected: base now ≈ **$4,777 / $2,857** off the `[Batting]` base — NOT $29,250 off
  `[Batting Refractor]`. Report MV + comp parallel.
- **1b. Plainest-product preference.** Any base/plain card (no parallel word in the title)
  should match the plainest product of that #, not a rarer named variant. Flag any base
  card still priced off a refractor/variant of the same number.
- **1c. Proxy ≠ STRIKE.** Any `scp_proxy`/ESTIMATE card must show ESTIMATE, never STRIKE.
  Flag any proxy still flashing STRIKE.
- **1d. Card-number discipline.** Any `scp_exact` whose comp card # differs from the
  listing # is a failure — list them.
- **1e. Distinct sets.** Chrome Platinum / Update / Cosmic / Sapphire / Chrome Black cards
  must comp to their OWN set. Flag any matched to plain Topps Chrome.

## 2 — Dangerous-STRIKE sweep (most important)
Scan EVERY STRIKE on the board + the top 20 Steals strikes. For each, is the comp truly
the same card? List any STRIKE whose comp is wrong-set / wrong-# / wrong-parallel / insert-
vs-base / dual-vs-solo / patch-vs-plain. Format: `title | MV | bid | what's wrong`.
(Goal: confirm the only wrong STRIKEs left are the known dual-auto / patch-auto cases.)

## 3 — Known unfixed (confirm they're ESTIMATE, not STRIKE — tomorrow's list)
For each, report `MV | badge | comp`:
- Insert subsets: any "Meteoric Rise", "Titans", "Sights on September", "Night Terrors",
  "Sterling", "Power Chords", "Talent Pipeline" card. (Should be ESTIMATE.)
- Dual auto: any "Dual Auto" / two-player auto. (Bijan/Roschon was a wrong STRIKE.)
- Patch/jersey auto: any "Patch Auto" / "Jersey Auto" / "Rookie Phenoms". (Jeanty was wrong.)

## 4 — Sport balance + spot accuracy
- **4a.** Find 5 NFL and 5 NBA cards (if the rebalance worked, there should be plenty).
  For each: `title | MV | comp set | EXACT ✅/❌`.
- **4b.** Tally the visible board: exact ___ / proxy ___ / no-comps ___ of ___ judged.
  (Last audit was ~18% exact — did it improve?)

## 5 — Quick UX check
- On the My Snipes tab, find an ENDED snipe. Confirm **"Mark Lost" is now a single click**
  (no "what did it sell for?" box), and **"Mark Won" still asks "What did you pay?"**. PASS/FAIL.

## 6 — Coverage harvest (tomorrow's downloads)
Group every NO-COMPS / cross-set card by SET, e.g. `2013 Bowman Chrome — 2 NO COMPS`.

---

## Report format
```
END-OF-DAY AUDIT — <date/time> | re-priced? Y/N
Snapshot: <n> cards (<MLB>/<NFL>/<NBA>), <%> NO COMPS · Steals <S/C/O/P>

1 Today's fixes:
  1a $29K Ohtani: $<v> comp <parallel>  PASS/FAIL
  1b plainest-product: PASS/FAIL — <exceptions>
  1c proxy≠strike: PASS/FAIL — <exceptions>
  1d card-#: PASS/FAIL — <exceptions>
  1e distinct sets: PASS/FAIL — <exceptions>

2 DANGEROUS STRIKES (verbatim): <list or NONE>

3 Known-unfixed (ESTIMATE confirm): <rows>

4a NFL x5 / NBA x5: <rows>
4b tally: exact __ / proxy __ / no-comps __ of __

5 Mark Lost one-click / Mark Won price: PASS/FAIL

6 COVERAGE HARVEST (by set): <grouped>

TOMORROW'S TOP 5 (verbatim titles): ...
```

The two things that matter most: **Section 2** (are there any dangerous STRIKEs left
beyond the known dual/patch-auto cases?) and **0/4a** (did the 3-sport rebalance finally
populate the board with NFL and NBA?). Everything else is the tomorrow list.
