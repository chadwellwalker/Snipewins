# SnipeWins Live Audit v4 — for Claude-in-Chrome

Re-audit after: (a) **clear-stale fix** — a card that re-prices to NO COMPS now
wipes its old value instead of leaving a stale "SnipeWins estimate", (b)
**shipping-aware deal math** — spread / STRIKE / target now use **bid + ~$5
shipping**, (c) confirming Bowman≠Topps and the serialized-estimate kill held.

Be a skeptic. Quote exact titles verbatim. Capture every failure title.
Site: https://app.snipewins.com (logged in as Chadwell)

---

## STOP — gate before starting
Don't start until Render shows the newest commit Live AND the board re-priced.
Re-price evidence: the serialized cards in Section E have CHANGED (estimates gone),
OR spreads are visibly ~$5 smaller than v3. If everything matches v3 exactly,
report "NOT RE-PRICED YET" and wait.

---

## Section E — Did the "SnipeWins estimate" cards go to NO COMPS? (the headline)
These 9 cards ALL showed a bogus estimate in v3. Each should now read **NO COMPS**
(no dollar value, no target). Find each, report `OLD v3 value → NEW value | PASS/FAIL`.
PASS = NO COMPS (or a real comp-backed value). FAIL = still shows "≈ SnipeWins estimate".

- **E1.** "2026 Topps Series 2 Paul Skenes #91A-PS Orange Chrome Mojo Refractor Auto /25" (was $200)
- **E2.** "2025 Topps Chrome Platinum Gunnar Henderson Pink Refractor Auto /15" (was $2)
- **E3.** "2026 Topps Chrome Black Elly De La Cruz Rose Gold Refractor Auto 10/10 REDS" (was $7)
- **E4.** "2025 Topps Chrome Ultra Violet All Stars Auto #Uvaps Paul Skenes 13/25 PSA 8" (was $7)
- **E5.** "2025 Topps Pristine Juan Soto Plated And Polished Auto Blue Refractor /75" (was $5)
- **E6.** "2025 Panini Prizm Auto-Blue Shimmer #187 Amon-Ra St. Brown /25 PSA 9 Dna Auto 10" (was $51)
- **E7.** "Bowman 2023 Bowman Chrome Prospects James Wood/25 #BDC-70 Washington Nationals" (was $3)
- **E8.** "2025 Topps Cosmic Chrome Lunar Star Clusters Francisco Lindor/Juan Soto /10 Mets" (was $2)
- **E9.** Scan the WHOLE board for ANY remaining "≈ SnipeWins estimate" on a serial-numbered
  card (/1–/50 in title). Copy every exact title. (Goal: zero.)

## Section S — Shipping-aware spread (the other headline)
Spreads/STRIKEs now include ~$5 shipping. Confirm the math moved.
- **S1.** "2024 Panini Spectra Brock Bowers #8 Neon Blue Prizm Die-Cut /50" — in v3 it
  showed "$20 BELOW MV · STRIKE" at bid $14.50. With +$5 shipping it should now show a
  SMALLER spread (~$15) and may have DROPPED off STRIKE. Report its current spread + badge.
- **S2.** Pick 5 cards showing a spread/STRIKE. For each report `bid | spread shown | badge`.
  Then open eBay, get actual shipping, and confirm: does `MV − (bid + shipping)` ≈ the
  spread shown? (It should now, within a dollar or two.) Flag any still ignoring shipping.
- **S3.** Any card where bid is low but shipping is high (>$10)? Those are where the flat
  $5 estimate is most wrong — copy title + real shipping so we can prioritize real-shipping capture.

## Section F — Worker health & freshness
- **F1.** Ending Soon "Updated … ago" and Steals "Updated … ago". Report both.
  (We expect discovery may still be stale until the daily budget resets — that's separate
  from valuations. Just report the numbers.)
- **F2.** Do the VALUES look fresh (changed from v3) even if the "Updated" label is old?
  YES/NO + one example of a changed value.
- **F3.** Steals tab: STRIKE / CLOSE / OFFER / PENDING counts. Did anything move off PENDING?

## Section B — Bowman ≠ Topps (regression hold)
- **B1.** "James Wood 2025 Bowman Chrome Adios! Orange Rookie #Ad-4 /25" — still ~$130 with
  a **Bowman** comp (NOT Topps)? PASS/FAIL.
- **B2.** Spot 3 Bowman cards + 3 Topps cards; open View Comps; confirm none cross brands.

## Section R — Regression check (don't trust, verify)
Confirm known-good values held:
- **R1.** Juan Soto Topps Chrome Platinum Gold /50 → ~$50, comp "[Gold] #200"
- **R2.** Any Panini auto (Jeanty / Caleb Williams) → Panini comp, sane value
- **R3.** Any high-value PSA-10 SSP (Ohtani Hobby Masters etc.) → unchanged ~$5,000-ish
Report anything that went to NO COMPS or moved wildly.

## Section X — Known-unfixed, harvest only
- **X1.** "Juan Soto 2025 Topps Chrome Black #6 /150" — in v3 this read **$3** off a base
  "Topps Logo" comp. Report its current value + comp. (Suspected: base Chrome Black cards
  undervalued — we may need to NOT strip the set color when there's no other parallel.)
- **X2.** "2024 Topps Chrome Update … Jackson Holliday … PSA 10" — in v3 a Topps Update card
  used a **Bowman Draft** comp. Report current comp set — is it still cross-product?
- **X3.** Cross-year inserts (Electric Sluggers, Mini Diamond, Lunar Star Clusters dual-player):
  report `title | MV | comp year/set`. Harvesting for which insert sets to load.

---

## Report format
```
DEPLOY AUDIT v4 — <date/time>
Re-priced? YES/NO (evidence)

E — SnipeWins estimates killed?
  E1 Skenes /25:  $200 -> <new>  PASS/FAIL
  ... E1–E8 ...
  E9 remaining serialized estimates: <exact titles or NONE>

S — Shipping math
  S1 Brock Bowers: spread <v3 $20> -> <new>, badge <new>  PASS/FAIL
  S2: <bid | spread | badge> x5, math checks? YES/NO
  S3 high-shipping cards: <titles or NONE>

F — Worker/freshness
  F1 board <t>, steals <t>
  F2 values fresh? YES/NO (example)
  F3 steals <strike/close/offer/pending>, moved? YES/NO

B1/B2 Bowman≠Topps: PASS/FAIL
R1–R3 regressions: PASS/FAIL
X1 Soto Chrome Black /150: $<v> comp <...>
X2 Holliday Update comp set: <...>
X3 cross-year inserts: <...>

NEW FAILURES (verbatim titles):
1. ...
```

The two things that matter most: **(E)** are the bogus "SnipeWins estimate" numbers
finally gone on serialized cards, and **(S)** does the spread now reflect bid+shipping
(Brock Bowers should no longer be a $20 STRIKE). Everything else is harvest.
