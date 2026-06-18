# SnipeWins Live Audit — for Claude-in-Chrome

**You are auditing the live site after a deploy. Your job is to verify the fixes,
and — most importantly — to HARVEST the exact title of every card that fails so
the engineer can reproduce it.** Be a skeptic. Report what you actually see, not
what you expect. Quote exact card titles verbatim (copy them) so they can be
re-tested in the price store.

Site: https://app.snipewins.com
Logged-in account required (Chadwell's). If you hit a login wall, stop and say so.

---

## What just changed (context for your audit)

1. **Empty-board fix** — the matcher couldn't read messy eBay titles (a dash glued
   to the player name like `-Caleb Williams` killed the match). Now fixed. The
   board should POPULATE with cards that have dollar values.
2. **Rarity guard** — a serial /1–/25 card (e.g. "Black Refractor /10") must NOT be
   priced off a plain base parallel. It should use a tier-matched estimate instead.
3. **Source** — all values come from SportsCardsPro price guides, NOT eBay sold comps.

---

## Pre-flight (do this first, report before continuing)

- **PF1.** Load the Ending Soon page. Read the "Updated … ago" timestamp. Report it.
- **PF2.** Count how many cards are visible on the board. Report the number.
  - If **0 cards**, the board is still empty → jump to "If the board is empty" below.

---

## Section A — Board populates (the headline fix)

- **A1.** Ending Soon board shows ≥1 card with a dollar market value. PASS/FAIL + count.
- **A2.** Pick the 10 cards with the messiest titles you can see (dashes, ALL CAPS,
  emojis, card numbers jammed mid-title, words like "Preview/Pandora/Lava"). For
  EACH, report: `exact title | market value shown | badge (ESTIMATE / NO COMPS)`.
  - **This is the most important data.** Any card showing **NO COMPS** or **$0** or
    blank → copy its EXACT title into the "Failures to fix" list at the bottom.
- **A3.** What fraction of visible cards show **NO COMPS**? (rough %). Report it.

## Section B — Comp accuracy spot-checks

For each card you can find on the board (or search), open **View Comps** and report
`title | MV | the comps it used`. Flag anything that looks wrong.

- **B1.** Any **Juan Soto** card → comps must be Juan Soto cards, NOT his team ("Mets",
  "Nationals", etc.). FAIL if a team name is used as the comp.
- **B2.** Any **serial-numbered /10, /15, or /25** card (look for "/10" etc. in title)
  → the value should NOT be a couple of dollars, and the comps should be other
  low-serial/colored parallels — NOT a plain base "Refractor". Report MV + comps.
- **B3.** Any **Panini** card (Prizm/Select/Optic/Mosaic) → comps should be Panini,
  not Topps/Bowman. And vice-versa. FAIL on cross-brand comps.
- **B4.** Any **digital / Bunt / NFT** card should NOT appear with a value (should be
  excluded). If you see one priced, copy its title.

## Section C — Target bid & badges

- **C1.** Each valued card shows a target bid. Confirm it's ~**70%** of the market
  value (do the math on 3 cards) and shows a "70% of market value" label. PASS/FAIL.
- **C2.** Badges read clearly: cards with a real value say **ESTIMATE**; cards
  without say **NO COMPS**. No card should be both/blank. PASS/FAIL.

## Section D — Account page (separate fix)

- **D1.** Click the Account link. It must open an **account page** (email, password,
  membership/billing) — it must NOT redirect to the sign-up page. PASS/FAIL.

## Section E — Steals tab (if present)

- **E1.** Open the Steals tab. Does it show BIN deals with values? PASS/FAIL + count.
- **E2.** Same messy-title harvest as A2 for any NO-COMPS cards → copy titles.

---

## If the board is empty (PF2 = 0)

Report these so the engineer can tell pool-vs-valuation apart:
- Is there a "scanning…" spinner, an empty-state message, or just nothing?
- Does the page say anything about budget / "daily limit"?
- Check the Steals tab and My Snipes — are THOSE empty too, or just Ending Soon?
- Report the "Updated … ago" time again.

---

## Report back in THIS format

```
DEPLOY AUDIT — <date/time>
Board updated: <timestamp> | Cards visible: <n>

A1 board populates: PASS/FAIL (<n> cards, <%> NO COMPS)
A2 messy-title cards:
   "<exact title>" | $<mv> | <badge>
   ... (10 rows)
B1 Juan Soto comps: PASS/FAIL — <detail>
B2 serial /10–/25: PASS/FAIL — <title> $<mv>, comps: <...>
B3 brand match: PASS/FAIL — <detail>
B4 digital excluded: PASS/FAIL
C1 target = 70%: PASS/FAIL — <math on 3 cards>
C2 badges clear: PASS/FAIL
D1 account page: PASS/FAIL — <what happened>
E1/E2 steals: PASS/FAIL — <detail>

FAILURES TO FIX (exact titles, copy verbatim — these go straight back to the engineer):
1. "<exact title>"  — <what's wrong: NO COMPS / wrong value / bad comp>
2. ...
```

**The "Failures to fix" list is the whole point.** Every exact title you capture
there, the engineer will paste into the price store, reproduce the failure, fix
the matcher or load the missing set, redeploy, and you'll re-run this audit. Keep
each other honest: if something looks off, capture it — don't round up to PASS.
