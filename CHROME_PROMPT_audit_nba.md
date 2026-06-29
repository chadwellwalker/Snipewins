# Chrome Prompt — NBA Validation Audit (did the seed fix populate the board?)

Paste into Claude-in-Chrome. Audit **https://app.snipewins.com** (log in as Chadwell).
This audit has ONE primary job: confirm the NBA seed-sync actually put the star players on
the board. Run after the latest deploy is Live and a discovery cycle has run (give it a few
hours — discovery is budget-gated, so NBA fills over cycles, not instantly).

---

## 0 — The headline number
- **Sport mix of the Ending Soon board: MLB vs NFL vs NBA counts + rough %.**
  (Was ~3% NBA / 4 cards, all Anthony Edwards. Target is 25%. Did it move?)
- Total cards, # targeted, % NO COMPS, "Updated … ago".

## 1 — Are the NBA STARS finally showing? (the seed-fix test)
Use the NBA filter. List every distinct NBA **player** on the board. We specifically need to
see names that were missing from the target generator before:
**Jokić, Giannis, SGA, Kevin Durant, Devin Booker, Lillard, Ja Morant, Zion, Brunson, Trae
Young, LeBron, Curry, Wembanyama, Luka, Tatum.**
- Report: which of those star names now appear? (Even 1 card each is the win — it proves the
  seed sync worked.)
- If still only Anthony Edwards / a couple names → seed fix didn't take; say so loudly.

## 2 — Do NBA cards price, or NO COMPS?
For each NBA card on the board: `title | MV | badge | comp set | exact/proxy/NO COMPS`.
- Flag any that are **NO COMPS** and note the SET — especially anything that says
  **2025-26 Topps Chrome / Sapphire / Finest** (those need price lists; expected blank for now).
- Panini NBA cards (Prizm/Select/Mosaic/Optic 2020-2025) SHOULD price — flag any that don't.

## 3 — Premium-only vet stars (new gate)
Find any **Kyrie, Jaylen Brown, Bam Adebayo, Kawhi, Jimmy Butler, De'Aaron Fox, Donovan
Mitchell, Paul George, Sabonis, Sengun** cards. Confirm they only show **premium chase cards**
(autos, numbered /XX, SP) — NOT cheap base/common cards. If you see a $3 base Kyrie on the
board, the premium-only gate failed — flag it.

## 4 — SP/SSP chase tracking
Any card with **Helix, Ultra Violet, Fanatical, Home Court Advantage, Glass** in the title
(Topps SP/SSP chases)? Report `title | MV | exact/proxy`. (Confirms the new SSP lanes fire.)

## 5 — Dangerous-strike spot check (keep the pipeline honest)
Any NBA STRIKE with a wrong comp (wrong parallel/set/card #)? List `title | MV | bid | what's wrong`.

## 6 — Coverage harvest (the NBA download list)
Group every NBA NO-COMPS card by SET. This becomes the exact Topps/Panini NBA price-list
shopping order.

---

## Report format
```
NBA AUDIT — <date/time> | re-priced? Y/N
0 Sport mix: MLB <n> / NFL <n> / NBA <n> (<%>)  — was 3% NBA
1 NBA stars now on board: <list of star names appearing, or "still only Edwards">
2 NBA pricing: <rows> ; NO-COMPS sets: <list>
3 Premium-only vets: <only chases? Y/N — any base cards?>
4 SP/SSP chases seen: <titles or NONE>
5 NBA dangerous strikes: <list or NONE>
6 NBA coverage harvest (by set): <grouped>

VERDICT: did the seed fix populate NBA? YES/NO + evidence
```

The one thing that matters: **Section 1.** If Jokić / Giannis / SGA / Durant now appear on the
board, the seed sync worked and NBA is unblocked. Everything else is tuning.
