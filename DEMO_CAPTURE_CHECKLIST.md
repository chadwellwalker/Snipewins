# Demo capture — what to record before launch

You need: 3 hero screenshots, a 60-second screen recording. That's it. This doc is the shot list and the QA criteria.

## When to capture

**Best time: Sunday 7-9pm PT or Monday 7-9pm PT.** Auction volume is at peak. The engine surfaces 80-150+ deals across all classes. Off-peak captures look thin and the marketing site will look weak forever.

If you record at 3pm Tuesday, scrap it and re-shoot Sunday.

## Shot list

### Shot 1 — The Live Board (hero screenshot)

Open `python run_app.py`. Click "Run Scan." Wait for completion.

You want a screenshot showing:
- The peak-times banner at the top reading **PEAK HOURS** (green) — this is why timing matters
- 5+ visible deals on the Live Board with non-empty `target_bid`, `market_value`, and `edge` columns
- At least one ELITE-class deal in the top three
- Player names and card descriptions are visible (not cropped)
- No scary error states, no debug expander open

**Capture:** Windows: `Win + Shift + S`. Mac: `Cmd + Shift + 4`. Save as `demo_hero_live_board.png`.

**QA check:** Show the screenshot to a stranger. Can they tell what the product does in 5 seconds without you explaining? If no, retake until yes.

### Shot 2 — The Buying Radar / 30-min ending feed (hero screenshot)

Click the **Buying Radar** tab. Wait for content. You want:
- 3+ cards visible with end-times in the next 60 minutes
- Confidence percentages visible
- Profit margins visible

**Capture:** save as `demo_hero_radar.png`.

If the Buying Radar is empty, you're not in peak hours. Wait for peak.

### Shot 3 — A single deal close-up (detail screenshot)

From the Live Board, click into any one deal. You want a close-up showing:
- The card title (full)
- The target bid (the paywall element)
- The current price, market value, and computed edge
- The auction end time

This is the screenshot for marketing copy that explains *what you actually get for the subscription*.

**Capture:** save as `demo_hero_deal_detail.png`.

## 60-second screen recording

Tools: OBS Studio (free, Win/Mac/Linux), Loom (free, browser-based), QuickTime (Mac built-in).

**Recording resolution:** 1920×1080 minimum. Anything smaller looks unprofessional.

### The script (rehearse twice before recording)

```
0:00–0:05   Cold open: the running app, peak-times banner visible.
0:05–0:15   Click "Run Scan." Voice-over: "I open SnipeWins, hit scan,
            and the engine starts pulling under-market auctions across
            every player I track."
0:15–0:25   Scan completes. Hover over the top deal.
            Voice-over: "Here's a Bo Nix Lazer Prizm rookie ending in
            18 minutes — current bid $34, market value $87. The engine
            tells me to bid up to $54 to keep a $33 margin."
0:25–0:40   Switch to Buying Radar.
            Voice-over: "If I'd missed it on the main board, the
            Buying Radar surfaces the same deals 30 minutes before they
            end so I never miss a window."
0:40–0:55   Cut to the Purchased tab (with at least one win logged).
            Voice-over: "And every win I lock through the engine gets
            tracked here automatically."
0:55–1:00   End card with subscription pitch.
            Voice-over: "Free tier gets you three scans a week.
            Pro is $29/month — one card pays for it."
```

### QA criteria for the recording

- No mouse hesitation. Smooth movement. (Practice the run twice before hitting record.)
- No personal info on screen — close every other window first. Check the browser tabs in the background.
- No fake data anywhere. The peak-times banner, the deal data, the radar — all real.
- Audio clean. Headset mic, not laptop mic. Quiet room.
- Final cut delivered as `demo_60s.mp4`, H.264, 1080p.

## Where these go

- **Landing page hero:** `demo_hero_live_board.png` above the fold, `demo_60s.mp4` autoplay-muted below the fold.
- **Twitter / X launch post:** `demo_60s.mp4` (Twitter favors video).
- **Reddit launch post (r/sportscards):** `demo_hero_live_board.png` plus written walkthrough.
- **Email signups:** all three screenshots in the welcome sequence.

## What NOT to capture

- Any screenshot showing a Python traceback.
- Any screenshot with `last_scan.log` open.
- Any screenshot with the `OFF-PEAK` banner.
- Any view of the hidden Auto-Buyer / Search eBay / Player Hub / Products tabs (they're disabled but if you somehow open them, don't capture).
- Anything showing your real eBay credentials.
- Anything from before the LiveDealFeed / FeaturedOpportunityRotator were replaced with honest copy. The pre-launch landing page is for screenshotting only after Pattern A is confirmed in place.
