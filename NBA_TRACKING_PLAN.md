# NBA Tracking Plan — products, case hits/autos, players (Chadwell to confirm/deny)

Context: **Topps holds the exclusive NBA license from 2025-26 onward** (Fanatics), releasing
monthly. Pre-2026 NBA = Panini (where current stars' rookie RCs live). Your confirmed scope:
**liquid-core Topps · case hits/autos for ALL tracked players · liquid Panini legacy.**

---

## ✅ ALREADY WIRED (this session) — NBA product universe is now 16 products

**Topps NBA (2026+, the new license — added):**
| Product | Why it's liquid | Top chases to watch |
|---|---|---|
| **Topps Chrome** | The flagship refractor set, highest volume | **Gold NBA Logoman /4 + 1/1 auto**, Superfractor 1/1, Gold Refractor /50, Rookie Debut Patch Auto 1/1, Stratospheric / SkyWrite / Chromographs autos |
| **Topps Chrome Sapphire** | Gem chromium, premium | Sapphire parallels, on-card autos |
| **Topps Finest** | Finest refractors | Finest auto refractors, Logoman |
| **Topps Basketball (Flagship)** | Base + inserts, casual volume | base RCs, insert autos |

**Panini legacy NBA (pre-2026 — already tracked):**
Prizm, Select, Mosaic, Donruss Optic, Hoops, Court Kings, **Donruss (added)**, plus high-end
**National Treasures, Immaculate** for stars/rookies. (Chronicles + Flux stay suppressed — low resale.)

**Case hits / autos now covered** (via the shared premium lanes that fire for these products,
for every tracked player): auto, superfractor/1-of-1, gold refractor, numbered parallels, RPAs.

---

## 📋 PROPOSAL — NBA player roster (confirm/deny each; current roster is 39)

The roster already has the stars + the full 2025 rookie class (Flagg, Harper, Edgecombe,
Maluach, Castle, Knueppel) + KD + WNBA (Clark, A'ja, Paige, Stewart, Collier, Ionescu).
Liquid names I think are **missing** — mark up freely:

**Veteran stars (high-liquidity, missing):**
Kyrie Irving, Jaylen Brown, Bam Adebayo, Kawhi Leonard, Jimmy Butler, De'Aaron Fox,
Donovan Mitchell, Paul George, Domantas Sabonis, Alperen Sengun.

**Vintage legends (modern cards, like the NFL ones you added):**
Magic Johnson, Larry Bird, Shaquille O'Neal, Allen Iverson, Tim Duncan, Kevin Garnett.

**Recent rookies worth tracking (2024 class):**
Zaccharie Risacher, Alex Sarr, Reed Sheppard, Stephon Castle *(already in)*.

**WNBA (very liquid right now):**
Angel Reese.

> You're the expert on who's actually moving — tell me which to add/cut and I'll wire them
> into `_PLAYER_MASTER` with the right tier.

---

## ⚠️ THE REAL BOTTLENECK — NBA generates too few scan targets per player

Even with 39 players × 16 products, the last build produced only **~91 NBA targets vs 1,139
NFL** — that's **~2.4 targets/player for NBA vs ~18.7 for NFL.** Adding the Topps products
helps, but something downstream is generating far fewer lanes per NBA player. I need to dig
into the lane-generation to find why (likely a per-sport cap, a premium-signal gate that's
stricter on NBA, or NBA players not all being "active" in the universe).

**This is the thing that actually fills the board with NBA** — more than players or products.
It's my next investigation after you confirm the roster above.

---

## What I'll do once you confirm
1. Add the approved players to `_PLAYER_MASTER` (sport=Basketball, tier, rookie_year).
2. Investigate + fix the NBA targets-per-player thinness (the ~2.4 vs ~18.7 gap).
3. Download the matching SCP price lists for any new Topps NBA sets so the new cards *value*
   as well as get discovered (Chrome NBA we have; Chrome Sapphire / Finest NBA I'll add to
   the next Chrome download list).

## Push for the product changes already made
```
git add player_hub.py scp_price_store.py supervisor.py valuation_worker.py scp_csv/
git commit -m "NBA: add Topps license products (Chrome/Sapphire/Finest/Flagship) + Donruss; rebuild-NUL hardening"
git push origin main
```
(This also carries today's rebuild-crash fix + the cleaned spectra CSV.)
