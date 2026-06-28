# Chrome Prompt — Test SnipeWins (live)

Paste into Claude-in-Chrome. You're auditing the live SnipeWins app at
**https://app.snipewins.com** (log in as Chadwell). Be a skeptic, quote exact card
titles verbatim, and capture every failure so the engineer can reproduce it.

Run only after the latest deploy is Live (the Steals fix + coverage changes).

---

## 1 — STEALS TAB (the big one this round)
Until now the Steals tab showed "0 strikes / 2,840 PENDING" for every audit. A bug was
just fixed so BIN cards compute a live target (70% of market value) + shipping.
- **1a.** Open the Steals tab. Report the counts: **STRIKE / CLOSE / OFFER / PENDING**.
  We expect STRIKE/CLOSE/OFFER to now be **> 0** (not all PENDING).
- **1b.** Open 5 individual BIN cards. For each report: `title | BIN price | market value shown | target | badge`.
  Confirm cards now show a real $ market value and a target (not "computing…").
- **1c.** For any STRIKE, sanity-check: is BIN price + ~$5 shipping actually ≤ target? If a
  card is flagged STRIKE but price+shipping is clearly above market, copy its title.

## 2 — EXACT-MATCH ACCURACY (our north star)
For each card below, open "View comps" and report whether the comp is the **EXACT variant**
(same set, card #, parallel, print run, grade) or a substitute. Flag substitutes.
- **2a.** Any card whose comp comes from a **different set** than the listing (e.g. listing
  says "Topps Chrome Platinum" but comp says "Topps Chrome"; listing "Bowman Chrome" but
  comp "Topps Chrome"). Copy `listing title | comp set used`.
- **2b.** Any serial-numbered card (/10, /25, /50) whose comp is a **different print run or a
  base/non-serial parallel**. Copy it.
- **2c.** Any card showing **"≈ SnipeWins estimate"** or a `scp_proxy` / "comparable parallel"
  basis. List the titles — these are the cards that need exact data loaded.

## 3 — REGRESSION HOLD (should still be correct)
- Juan Soto Topps Chrome Platinum Gold /50 → ~$50 (note the comp's set — is it Platinum or plain Chrome?)
- Any Panini auto (Caleb Williams / Ashton Jeanty) → Panini comp, sane value
- A high-end PSA-10 SSP (Ohtani) → unchanged big number
- Confirm NO serialized card shows a fake "SnipeWins estimate" (Skenes /25, Gunnar /15, etc. should be NO COMPS or a real comp)

## 4 — COVERAGE HARVEST (drives the download list)
Scan the whole board + Steals. Make a list of every card showing **NO COMPS** or a
**cross-set / proxy** comp, and for each note the **set name** in the listing title. We use
this to decide which SportsCardsPro lists to download next. Group by set, e.g.:
```
2025 Topps Chrome Platinum — 4 cards NO COMPS
2026 Bowman Chrome — 3 cards proxy/cross-year
2024 Panini Instant — 2 cards NO COMPS
```

## 5 — FRESHNESS (just report, don't alarm)
- Ending Soon "Updated … ago" and Steals "Updated … ago". (These track DISCOVERY, which is
  budget-gated and refreshes at the UTC reset — separate from valuations. Just report the numbers.)
- Board: total cards / # with a target / % NO COMPS.

---

## Report format
```
SNIPEWINS TEST — <date/time>
1 Steals: STRIKE __ / CLOSE __ / OFFER __ / PENDING __   (was 0/0/0/2840)
  5 BIN cards: <title | price | MV | target | badge> ...
2 Exact-match issues:
  2a cross-set comps: <listing | comp set> ...
  2b wrong print-run/parallel: <titles> ...
  2c proxy/estimate cards: <titles> ...
3 Regressions: PASS/FAIL — <detail>
4 Coverage harvest (by set):
  <set name — N cards NO COMPS/proxy> ...
5 Freshness: board <t>, steals <t>; <n> cards / <n> targeted / <%> NO COMPS

TOP FAILURES (verbatim titles):
1. ...
```

The two things that matter most: **(1)** did the Steals tab finally light up with real
strikes, and **(4)** the by-set coverage harvest — that's the shopping list for which
SportsCardsPro price guides to download next.
