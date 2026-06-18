# SnipeWins Audit v5 — end-of-session (run the APP section and/or the LOGS section)

Run after the latest commit is Live and re-priced (~15 min). This round verifies
the brand-word fix (X1/X2) and re-checks the few known stragglers. It also includes
a LOGS section so you can sanity-check the worker without me.

Be a skeptic. Quote exact titles. Capture failures verbatim.
Site: https://app.snipewins.com (logged in)

═══════════════════════════════════════════════════════════════
## PART A — APP AUDIT
═══════════════════════════════════════════════════════════════

### A1 — Brand-word / cross-product fixes
- **"2024 Topps Chrome Update … Jackson Holliday 60/125 PSA 10"** — in v4 it pulled a
  **2023 Bowman Draft** comp. Expected now: **NO COMPS** (or a Topps comp), NOT Bowman.
- **"Juan Soto 2025 Topps Chrome Black #6 /150"** — was $3 off a "[Topps Logo]" comp.
  Report new value + comp. (Known weak spot — the 2025 Chrome Black base data may need
  loading; just report what it shows now.)
- Spot-check 3 Topps cards + 3 Bowman cards: confirm none pull a comp from the other brand.

### A2 — Estimates still gone (regression hold)
Re-confirm these stay **NO COMPS** (they were fixed in v4):
- Paul Skenes Orange Mojo /25, Gunnar Pink /15, Elly Rose Gold 10/10, Skenes UV /25,
  Soto Pristine /75, Amon-Ra Shimmer /25.
- Scan for ANY serial-numbered card (/1–/50) still showing "≈ SnipeWins estimate". List them.

### A3 — Dual-player insert (known-unfixed)
- **"2025 Topps Cosmic Chrome Lunar Star Clusters Francisco Lindor/Juan Soto /10"** — still
  ~$2 off a solo Lindor comp? Report value + comp. (This dual-player case isn't fixed yet.)

### A4 — Shipping (regression hold)
- Pick 4 STRIKE cards. For each: `bid | spread shown`. Confirm spread = MV − (bid + ~$5).
  Should still hold from v4.

### A5 — Board / Steals state
- Ending Soon "Updated … ago" + Steals "Updated … ago".
- Board: card count / # targeted / % NO COMPS.
- Steals: STRIKE / CLOSE / OFFER / PENDING. (If still 0 strikes, note whether ANY BIN
  shows a real $ MV when you open it — that tells us if BINs are being valued at all.)

### A6 — Regression sweep
- Juan Soto Gold /50 → ~$50; Caleb Williams Panini auto → Panini comp; a big PSA-10 SSP
  (Ohtani) → unchanged. Flag anything that broke.

═══════════════════════════════════════════════════════════════
## PART B — LOGS AUDIT (Render logs, paste to Claude next session)
═══════════════════════════════════════════════════════════════

These are the patterns that actually matter — most log noise is normal.

### B1 — Worker is looping (GOOD signs, expect to see these)
- `[valuation_worker] batch done in Xs — AUC valued=.. · BIN valued=.. queue_remaining=0`
  repeating every ~1–2 min → worker healthy.
- `[SCP_HIT] mv=$.. src=scp_exact|scp_proxy` lines → valuations working.
- `[VALUATION_CONTRACT_VERSION]` / `VALUATION_VERSION=scp_2026_06_19_brandword` → newest code live.

### B2 — IGNORE these (they are BY DESIGN, not bugs)
- `pool=comps_disabled raw_rows=0` → eBay comps are intentionally OFF. Only appears for
  cards with NO SCP match; those correctly become NO COMPS. **Not a problem.**
- `final_conf=estimate_only` on a card that ALSO has no SCP_HIT → that card is a NO-COMPS
  card; expected.

### B3 — REAL things to copy out if you see them
- **Duplicate item lines**: the same `valuing BIN v1|<id>` logged many times at the SAME
  timestamp. If this is real (not just log echo), it means >1 worker instance racing on
  the pool file. Copy 5–6 of the duplicated lines + their timestamps.
- **Player misID**: e.g. `Chuba Hubbard … strict_query="… Christian McCaffrey …"`. The
  legacy query-builder maps some players to a teammate. Only bites NO-COMPS cards (which
  show NO COMPS anyway), but copy any you see so I can fix the player map.
- **`cycle error` / traceback** in a `[WORKER]` line → copy the whole stack.
- **`BUDGET_PULSE … near_end=NNNN`** → if `near_end` is still > 1000 the day AFTER this
  deploy + a UTC reset, the cap isn't holding; copy the line.

### B4 — Freshness check
- `[BUDGET_PULSE] … pct=…%` — if pct is ~100%+, discovery is budget-capped (why "Updated
  Xh ago" stays stale until the daily reset). Valuations still run (they're free). Note the %.

═══════════════════════════════════════════════════════════════
## Known-unfixed going into next session (so we don't re-litigate)
═══════════════════════════════════════════════════════════════
1. **Chrome Black /150 base cards** undervalue (e.g. Soto #6 /150 → low) — needs the 2025
   Topps Chrome Black base data verified/loaded, not a logic fix.
2. **Dual-player inserts** (Lindor/Soto /10) — matcher picks one player; needs dual-name
   detection → NO COMPS.
3. **Steals/BIN** — confirm whether bin_view reads the freshly-valued pool; Steals shipping
   not yet applied; steals_engine not in the supervisor.
4. **Duplicate worker** — confirm single instance (B3).
5. **Real per-listing shipping** — currently a flat $5; capture actual `shippingCost` at
   discovery for precision.
6. **Player misID** (Hubbard→McCaffrey) in the legacy query builder.

The big wins this session: SCP valuation live, board populates, Bowman≠Topps, autos
matched as autos, rarity guard, serialized estimates killed, stale-value clearing,
shipping-aware spreads, and pool/budget persistence. The list above is the cleanup tail.
