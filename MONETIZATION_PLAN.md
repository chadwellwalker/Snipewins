# SnipeWins — monetization & tier architecture

Decision date: 2026-05-06
Owner: Chadwell

## Tier model

Two tiers. Same product. Same data. Same speed. Differentiator is volume.

```
                FREE                    PRO ($29-99/mo, TBD by test)
─────────────────────────────────────────────────────────────────────
Scans / week    3                       Unlimited
Snipes / week   5 reveals               Unlimited reveals
BIN alerts      5 reveals / week        Unlimited reveals
Watchlist size  5 players               Unlimited
Deal quality    All classes (ELITE/STRONG/GOOD)   ← same
Speed           Real-time                          ← same
Data            Full feed                          ← same
```

## The paywall mechanic

Free users see real opportunities. The actionable number is gated.

```
Snipe card displays for FREE user:
┌─────────────────────────────────────────┐
│ Bo Nix · 2024 Prizm Lazer Prizm RC      │
│ Current: $42 · Ends in 14m              │
│ Class: ELITE                            │
│                                         │
│ Target bid: ▒▒▒▒▒▒▒                     │
│ [Upgrade to Pro to see target bid]      │
└─────────────────────────────────────────┘
```

Same card for PRO user shows `Target bid: $87` directly.

The blur is on the dollar amount only — never on the existence of the
opportunity. This is what drives conversion: free users *watch deals
they could have won* slip away.

## Why this beats every other tier model we considered

| Model | Why we passed |
| --- | --- |
| Threshold-based (Free sees ≥30% under MV) | Most deals cluster at 5-15% under MV; free tier sees nothing → churn |
| Coverage-based (Free = 1 sport) | Flippers who specialize in one sport gain nothing by upgrading |
| Time-priority (Pro sees deals first) | Artificial delay feels like punishment, kills word-of-mouth |
| Quality-tier (Free sees GOOD only) | ELITE is rare; Pro tier feels cheated. Also makes free product feel broken |
| Watchlist-size only | Soft constraint; most users won't notice or care |

The usage-cap model wins because:

1. **Honest pricing.** Free isn't a deliberately-broken product, it's a sample. The free user gets the full experience just bounded.
2. **Conversion at the moment of value realization.** Users who burn 3 scans and saw something good are the easiest sale.
3. **One product code path.** No tier-aware filtering in the scanner. Massive engineering simplicity.
4. **Repeated exposure via weekly reset.** Users come back, see new opportunities, hit the wall again. Each cycle is a conversion shot.

## The two product surfaces

The same business, two alert types:

### Auction Snipes
- Engine: existing `ending_soon_engine.py` (the live work in progress)
- Paywall element: target bid (max profitable price)
- Primary value claim: "we tell you exactly how high to go"

### BIN Alerts (separate build, future)
- Engine: needs a continuous BIN scanner watching for underpriced listings
- Paywall element: deal verdict ("this is X% under market — buy now")
- Primary value claim: "we tell you when a Buy-It-Now is mispriced"
- Same tier caps. Same paywall mechanic. Different alert shape.

## Renames before launch

- "Snipe" → consider "Target Bid" or "Recommendation" — eBay culture uses "snipe" to mean automated last-second bidding, which we DO NOT do (Auto-Buyer was removed for ToS reasons). Avoid the confusion.
- Internal code can keep `snipe_*` names; user-facing UI should rename.

## Open questions / decisions deferred

- Exact price point: test $29 / $49 / $99
- Free reset cadence: assume weekly; verify with conversion data
- Whether BIN reveals share a cap with snipe reveals or have a separate one
- Annual pricing discount (default: 20% off if billed annually)
- Free trial vs. true free tier — start with true free tier, add 7-day Pro trial after first 100 paying users for word-of-mouth

## Implementation footprint (rough)

- Free/Pro state per user → goes in user profile / settings
- Weekly scan/reveal counters with rolling reset → simple SQLite or JSON store, NOT in-memory (must survive restart)
- Paywall modal + blur component → Streamlit-side UI work
- "Reveal" event capture for billing → log every blur-removal so we know what users are paying for
- Stripe (or similar) integration for subscription → standard SaaS plumbing
