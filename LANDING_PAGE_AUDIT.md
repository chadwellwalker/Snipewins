# Landing page audit — what's real, what's not, and what to do before launch

Audit date: 2026-05-06
Status: **DO NOT LAUNCH the landing page in current state.**

## Executive summary

The marketing landing page (`snipewins-landing/`) appears to show:

- A live-deal rotator with current opportunities
- A social-proof feed of "real users winning real cards"
- A backend deal API at `localhost:5000/api/deals`

**Every one of those is mock data.** No real eBay integration. No real users. No real comps. The numbers are random multipliers. The names are made up. The cards are static placeholders.

If you launch as-is, the FTC truth-in-advertising rules (16 CFR Part 255) and basic platform-trust hygiene make this a brand-ending risk. One screenshot of "Chris in CA locked Joe Burrow" next to a Reddit thread asking "is this site legit" and the company is over.

The good news: you have a real engine producing real deals every 15 minutes (the Streamlit scanner). Wiring its output into the landing page is straightforward.

## What's mocked, where, and what it claims

### `src/components/LiveDealFeed.jsx`

```js
const socialProofEvents = [
  { name: "Chris", state: "CA", card: "Joe Burrow Genesis", buy: 67, mv: 106 },
  { name: "Jake",  state: "TX", card: "Julio Rodriguez Sapphire", buy: 52, mv: 84 },
  ... 18 more
];
```

**Implication on the page:** "real users are winning real cards right now."
**Reality:** zero of these are real users. Zero of these purchases happened.
**Risk:** FTC §255.5 violation (false consumer testimonials).
**Verdict:** **DELETE before launch.** Replace with one of the three patterns under "Honest replacements" below.

### `src/components/FeaturedOpportunityRotator.jsx`

```js
const featuredRadarDeals = [
  { title: "Panini Mosaic Justin Jefferson Zebra Shock", price: 64,
    marketValue: 108, profit: 44, confidence: 87, ends: "11m 27s", ... },
  ... 4 more
];
```

**Implication on the page:** "these are live deals our engine is surfacing right now."
**Reality:** five hardcoded objects. Auctions don't actually end in 11m 27s — that string is hardcoded forever and changes only when someone edits the file.
**Risk:** less severe than fake testimonials, but still misleading. The "ends in" countdowns imply real-time data the page isn't actually fetching.
**Verdict:** Replace with real data from the Streamlit engine OR clearly label as DEMO.

### `server/services/ebayService.js`

```js
async function fetchListings(query) {
  return [ /* 7 hardcoded card objects */ ];
}
```

**Implication of the file name:** "this calls eBay."
**Reality:** returns the same 7 fake cards every time, regardless of query. Never makes a real API call.
**Verdict:** delete or rewrite to call the real Python engine's output.

### `server/services/compEngine.js`

```js
function estimateMarketValue(listing) {
  const multiplier = randomBetween(1.5, 2.2);
  return { marketValue: Math.round(listing.price * multiplier),
           confidence: randomInt(70, 95),
           compCount:  randomInt(5, 25) };
}
```

**Implication of the file name:** "this is the comp engine — it estimates market value."
**Reality:** market value = listing price × `Math.random()`. Confidence and comp count are also random integers.
**Verdict:** **delete this file entirely.** The real comp engine is in Python (`market_value_engine.py`, `comp_engine_v2.py`). The JS file is misleading even to other developers reading the codebase.

### `server/server.js`

```js
app.get("/api/deals", async (_req, res) => {
  const payload = await getDeals();   // returns the mock chain above
  res.json(payload);
});
```

**Reality:** the endpoint exists but nothing in `src/` calls it. The React components use the inline mock arrays directly.

## Honest replacements

Three patterns, in order of effort:

### Pattern A — Honest scaffolding (zero data, fastest)

- **LiveDealFeed:** replace with a single CTA: *"Be one of the first 100 to lock a deal — Pro members get priority access to under-market auctions."*
- **FeaturedOpportunityRotator:** replace with one static card labeled `DEMO — your dashboard will look like this` with sample numbers.
- **Remove the server entirely** or move it to `snipewins-landing/server-mock/` so no one mistakes it for production.

This is what most pre-launch SaaS sites do. The page sells the *promise* of the product, not invented results.

### Pattern B — Real engine, anonymized social proof

- **FeaturedOpportunityRotator** pulls from a JSON file the Python engine writes after every scan. Real cards, real prices, real market values. The numbers are honest. (Implementation detail below.)
- **LiveDealFeed** replaced with an aggregated counter: *"42 deals surfaced in the last 24h · 7 ELITE-class · $3,847 in margin identified"* — these are real metrics from the engine, no fake users involved.
- This requires ~2 hours of bridge code (Python writes JSON; Node reads JSON; React fetches and renders).

### Pattern C — Real engine, real users (post-launch only)

- After 30+ paying users have logged real wins via the eBay-OAuth Purchases integration (designed in `PURCHASES_OAUTH_DESIGN.md`), replace LiveDealFeed with anonymized real wins: *"User in TX locked Julio Rodriguez Sapphire — $52 → $84 (+$32)"*.
- Get explicit consent in Terms of Service for using anonymized win data as social proof.
- Maintain a moderation queue so you don't accidentally publish someone's identifying info.

## Recommended path

**Today:** Pattern A. Strip the fake social proof. Label the rotator as DEMO.
**Within 2 weeks:** Pattern B. Bridge real engine output to the landing page.
**Within 2 months of launch:** Pattern C. Upgrade social proof to real anonymized wins once you have data.

## Implementation sketch for Pattern B

```
┌─ Python (Streamlit) ────────────────────────────┐
│ scan_scheduler runs every 15 min                │
│   → ending_soon_engine.fetch_ending_soon_deals()│
│   → returns deals (list) + meta (dict)          │
│                                                 │
│ NEW: after every scan, also write top-5 deals   │
│      to landing_page_feed.json                  │
└─────────────────────────────────────────────────┘
                       │
                       ▼ writes JSON file
                       │
┌─ Node (server.js) ──────────────────────────────┐
│ GET /api/deals                                  │
│   reads landing_page_feed.json                  │
│   returns the same deals to the browser         │
└─────────────────────────────────────────────────┘
                       │
                       ▼ HTTP GET on page load + every 30s
                       │
┌─ React (src/) ──────────────────────────────────┐
│ FeaturedOpportunityRotator                      │
│   useEffect → fetch("/api/deals")               │
│   render the real titles, prices, MVs           │
│ LiveDealFeed                                    │
│   Pattern A scaffolding (no fake users)         │
└─────────────────────────────────────────────────┘
```

Estimated effort:

- Python writer (10 lines added to scan_scheduler): 30 min
- Node read-from-file change (10 lines edited in dealEngine.js): 15 min
- React fetch wiring in Rotator (replace static array with `useEffect`): 1 hour
- Strip LiveDealFeed mock data, replace with aggregated counter: 1 hour
- Wire counter to the same JSON: 30 min
- Test end-to-end with a real scan: 1 hour

**Total: ~4 hours. One session.**

## Open questions before we wire Pattern B

1. **Hosting:** when launched, Node `server.js` runs where? On the user's laptop with Streamlit? On a tiny DigitalOcean droplet? Heroku? Vercel? This decides whether the JSON file is on the same filesystem or needs a real DB.
2. **Caching:** how stale is "live enough"? My instinct: write JSON every scan (15 min), poll React every 30s. Card auctions ending mid-poll are fine — the next scan catches them.
3. **What does the page show during off-peak hours when the engine has no deals?** Empty state matters. "No live deals at this exact moment — the scanner runs every 15 min" is honest. "Check back in 10 min" is friendly.

Tell me which path (A, B, or C) you want to pursue and I'll implement it.
