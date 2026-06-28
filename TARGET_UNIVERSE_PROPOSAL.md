# SnipeWins Target Universe — Research & Proposal (for Chadwell to confirm/deny)

Goal: balance discovery across MLB / NFL / NBA so we can serve a 3-sport userbase,
and aim every scan at **liquid** cards (easy for a sniper to resell). Nothing is wired
yet — confirm/deny each section and I'll implement what you approve.

---

## Finding 1 — The player roster is NOT the bottleneck
`_PLAYER_MASTER` already has **134 players** and it's current (it includes 2025 NBA
rookies Cooper Flagg / Dylan Harper / VJ Edgecombe and the 2024 NFL QB class). Split:
**Baseball 35 · Football 61 · Basketball 38.** That's a solid, liquidity-weighted list.

## Finding 2 — NBA is starved structurally, not for lack of players
Last target build was **NFL 1,139 / MLB 560 / NBA 91**. NBA got crushed because:
1. Only **4 NBA sets** were ever configured as scan targets (Prizm, Select, Optic, Mosaic), and 5 NBA product-targets were auto-**suppressed** ("weak_product_no_premium_signal").
2. You just loaded **11 new NBA sets** (Prizm/Select/Mosaic/Optic/Donruss/Hoops/Court Kings/Revolution/Origins/Immaculate/National Treasures + 2023 Prizm/Select/Mosaic) — none are wired as targets yet.
3. The daily eBay call budget drains on baseball/football first, so NBA discovery rarely runs.

**So the fix is: more NBA (and balanced) SET targets + a per-sport budget floor — not more players.**

## Finding 3 — What "liquid" means (from current market research)
- **Autos are ~50% more liquid** than non-auto parallels.
- **Refractors / Prizms are the most liquid parallels** (MLB refractors especially).
- Liquidity concentrates in: established superstars, *hot* rookies (current/just-prior class), and vintage GOATs — across **Prizm, Chrome, Optic, Select** as the core liquid product lines.
- Implication for sniping: weight scans toward **Chrome/Prizm/Optic/Select base + refractor/prizm parallels + RC autos** of the names below. Skip thin oddball inserts (they don't resell fast).

---

## PROPOSAL A — Players to ADD (confirm/deny each; roster is already strong, these are gaps)

**Baseball — add (liquid, currently missing):**
Fernando Tatis Jr., Kyle Tucker, José Ramírez, Adley Rutschman, Corey Seager, Rafael Devers, Roki Sasaki *(already in)*. Vintage: Mickey Mantle, Ken Griffey Jr., Babe Ruth, Hank Aaron, Jackie Robinson.

**Football — add:**
A.J. Brown, Nico Collins, Brock Purdy, Matthew Stafford, DK Metcalf. Vintage: Jerry Rice, Barry Sanders, Joe Montana, Walter Payton, Randy Moss.

**Basketball — add:**
**Kevin Durant** (major liquidity miss), Kawhi Leonard, Jimmy Butler, Donovan Mitchell, De'Aaron Fox, Kyrie Irving. Vintage: Magic Johnson, Larry Bird, Shaquille O'Neal, Tim Duncan.

> Tell me which to add/cut. You're the expert on who's *actually* moving right now — I defaulted to broad-market liquidity.

---

## PROPOSAL B — Liquid SET universe per sport (the real lever)

Scan these sets (we now have SCP price data for almost all). Confirm/deny the list:

**Baseball:** Topps Chrome, Bowman Chrome, Bowman Draft Chrome, Bowman Chrome Sapphire, Topps Chrome Update, Topps Chrome Platinum, Topps Cosmic Chrome, Topps Chrome Black, Topps Finest, Panini Prizm (unlicensed but very liquid), Topps flagship (Series 1/2/Update). *Vintage Topps/Bowman for legends.*

**Football:** Panini Prizm, Select, Donruss Optic, Mosaic, Contenders (RC autos), Spectra, Phoenix, Absolute. *(Prizm + Optic = the liquidity core.)*

**Basketball:** Panini Prizm, Select, Donruss Optic, Mosaic, Court Kings, NBA Hoops, Revolution. *(Prizm is THE liquid NBA set — weight it heaviest.)*

> Anything here you'd drop as "doesn't resell fast," or any liquid set I missed?

---

## PROPOSAL C — Per-sport discovery budget (so NBA stops getting starved)

Today the ~4,500 daily eBay calls drain by whoever's searched first (baseball-heavy).
Proposed **floors** so each sport is guaranteed coverage every day:

| Sport | Share | Rationale |
|---|---|---|
| NFL | 40% | Biggest hobby + your deepest roster |
| MLB | 35% | Strong current coverage; keep it |
| NBA | 25% | Floor it so it actually runs daily (was ~5%) |

(Adjustable — if your userbase skews one way, we weight to it.)

---

## What I'll wire once you confirm
1. Add approved players to `_PLAYER_MASTER` (name, sport, tier, rookie_year).
2. Add approved sets to the per-sport scan set-lists.
3. Add a per-sport budget floor in the discovery scheduler so NBA/NFL/MLB each get their share.
4. Re-check the "weak_product_no_premium_signal" suppression so legit NBA sets aren't dropped.

Reply with edits (add/cut names, adjust sets, change the budget split) and I'll implement exactly what you approve.

Sources: [SI — Top PSA 10 Sales 2026](https://www.si.com/collectibles/top-psa-10-sales-of-sports-cards-in-2026), [Athlon — Most Valuable Cards 2026](https://athlonsports.com/collectibles/collectibles-top-10-most-valuable-sports-cards-2026), [Athlon — Most Hyped 2026 Releases](https://athlonsports.com/collectibles/top-10-valuable-hyped-sports-card-releases-2026)
