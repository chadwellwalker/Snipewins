# SnipeWins Live Audit v2 — for Claude-in-Chrome

**This is a re-audit after a deploy that (a) bumped the valuation version to force
EVERY card to re-price, and (b) fixed the premium-serial rarity bugs.** Your job:
confirm the known failures from audit v1 actually flipped, verify the new rarity
behavior, and harvest any NEW exact titles that fail. Be a skeptic — quote exact
titles verbatim. Report what you see, not what you expect.

Site: https://app.snipewins.com (logged in as Chadwell)

---

## STOP — do not start until the re-price has happened

The version bump re-prices all ~100 auctions + ~2,840 BINs. This takes time.
- **Gate 1:** Render shows the newest commit as "Live."
- **Gate 2:** The Ending Soon "Updated … ago" timestamp is RECENT (minutes, not hours),
  OR the dollar values have visibly changed from audit v1.
- If values still match audit v1 exactly (e.g. Juan Soto Gold /50 still shows $4),
  the re-price hasn't run yet — **wait and recheck.** Report "NOT RE-PRICED YET" and stop.

---

## Section R — Did the known v1 failures flip? (the whole point)

Find each card (use the board; search by player if needed). Report
`exact title | OLD v1 value | NEW value | comps used | PASS/FAIL`.
PASS = it changed to the expected behavior below.

- **R1.** Juan Soto Topps Chrome Platinum Gold Refractor /50 (the "New York Mets" one)
  - v1 = **$4** with Mets team-card comps. Expected now: **~$50**, comp = "Juan Soto [Gold] #200".
  - FAIL if comps still say "New York Mets [Black Border/Green Holo] #291".
- **R2.** Juan Soto Black Refractor /10 (Topps Chrome Black)
  - v1 = **$5** matched to plain "[Refractor] #130". Expected now: **~$45**, basis = scp_proxy
    (tier-matched estimate), NOT a plain base Refractor.
- **R3.** James Wood Black Lava 7/10 PSA 9
  - v1 = **$32**. Expected now: **~$50**, basis = scp_proxy, comps = Gold/Rose-Gold tier parallels.

## Section N — New rarity behavior (these SHOULD now be NO COMPS, not a wrong cheap $)

The fix deliberately refuses to price an ultra-rare serial card off a plain base
parallel. Confirm these show **NO COMPS** (or an honest estimate) — NOT a wrong low value.

- **N1.** "Gunnar Henderson Pink Refractor Auto /15" (Topps Chrome Platinum)
  - v1 = **$2** (priced as plain Refractor). Expected now: **NO COMPS** (no wrong $2).
- **N2.** "Elly De La Cruz Rose Gold Refractor Auto 10/10" (Topps Chrome Black)
  - v1 = **$7** (priced as plain "[Gold]"). Expected now: **NO COMPS** (no wrong $7).
- **N3.** Scan for any other card with a **color + "Refractor/Auto" + low serial (/5–/25)**
  that shows a suspiciously low value (under ~$10) with a plain base-parallel comp.
  Copy its exact title → that's a rarity-guard miss to harvest.

## Section A — Board health (regression check)

- **A1.** Card count + how many have a target bid + rough % NO COMPS. Compare to v1
  (was 100 / 81 / ~19%). Big jump in NO COMPS would mean the rarity guard is over-firing —
  flag it.
- **A2.** Pick 8 cards that had GOOD values in v1 (e.g. Ashton Jeanty Auto $113, Brock
  Bowers $29, Shohei Ohtani Gold /50 $657). Confirm they STILL have sane values — the
  version bump shouldn't have broken working cards. Report any that went to NO COMPS or
  changed wildly.

## Section X — Cross-year / cross-set (known-unfixed, just harvest)

These were NOT fixed yet — I just want the exact titles + what comps they pull, to size
the problem. Report `title | MV | comp set/year used`.

- **X1.** "Juan Soto 2026 Bowman Chrome Electric Sluggers Orange /25" — does it still pull
  2025 Topps/Bowman comps?
- **X2.** "Juan Soto 2020 Topps Stadium Club Chrome" — still priced off a 2025 Topps Chrome parallel?
- **X3.** Any card where the comp's YEAR clearly differs from the listing's year → copy it.

## Section S — Staleness & Steals

- **S1.** Ending Soon "Updated … ago" and Steals "Updated … ago". Report both. (v1 was 9h / 13h.)
- **S2.** Steals tab: strike/close/offer/pending counts. (v1 was 0/0/0/2,840 pending.)
  Did any BINs move out of PENDING into a valued state? Report the new numbers.

---

## Report back in THIS format

```
DEPLOY AUDIT v2 — <date/time>
Re-priced? YES/NO (evidence: <timestamp or changed values>)
Board: <n> cards / <n> targeted / <%> NO COMPS  (v1 was 100/81/19%)

R1 Juan Soto Gold /50:  $4 -> $<new>  PASS/FAIL  comps: <...>
R2 Juan Soto Black /10: $5 -> $<new>  PASS/FAIL  basis: <...>
R3 James Wood Lava /10: $32 -> $<new> PASS/FAIL  comps: <...>
N1 Gunnar Pink /15:  $2 -> <NO COMPS / $?>  PASS/FAIL
N2 Elly Rose Gold /10: $7 -> <NO COMPS / $?> PASS/FAIL
N3 new rarity misses: <exact titles or NONE>
A1 board health: <counts> — over-firing? YES/NO
A2 good cards still good: PASS/FAIL — <any that broke>
X1/X2/X3 cross-year (harvest): <title | MV | comp year>
S1 staleness: board <t>, steals <t>
S2 steals: <strike/close/offer/pending> — moved from PENDING? YES/NO

NEW FAILURES TO FIX (exact titles, verbatim):
1. "<title>" — <what's wrong>
2. ...
```

**The two things that matter most:** (1) did R1–R3 flip — proving the re-price actually
reached the board — and (2) the NEW failures list. If R1–R3 did NOT flip, the re-price
didn't run; say so loudly so we fix the worker before anything else.
