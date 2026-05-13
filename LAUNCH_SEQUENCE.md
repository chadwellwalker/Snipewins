# SnipeWins — launch sequence

The plan to get from "working locally for one person" to "10 paying users" without burning anything down. Run sequentially. Don't skip.

## Stage 0 — Pre-flight (today)

Before you tell anyone the product exists.

- [ ] Run `python smoke_test.py`. Must show `[SMOKE] [SUMMARY] PASS`.
- [ ] Run `python run_app.py`. Confirm the four-tab nav (Ending Soon, Purchased, Buying Radar, Settings).
- [ ] Click "Run Scan" on Ending Soon. Confirm deals load.
- [ ] Click each remaining tab. Confirm none crash. Settings can show TODO content.
- [ ] Skim `LANDING_PAGE_AUDIT.md`. Confirm `LiveDealFeed.jsx` and `FeaturedOpportunityRotator.jsx` are the honest Pattern A versions, not the fake-data backups.
- [ ] Read `MONETIZATION_PLAN.md`. Confirm tier pricing is locked.
- [ ] Read `BETA_SETUP.md`. Walk a friend through the setup over the phone — if they get stuck, fix the doc, don't blame them.

## Stage 1 — 24-hour soak (this week)

Prove the engine doesn't die overnight.

- [ ] Follow `SOAK_RUNBOOK.md` — start scheduler, leave running 24 h.
- [ ] Run `python healthcheck.py` every few hours. Should report HEALTHY.
- [ ] At 24h mark: confirm `scheduler_heartbeat.json` shows last_scan_ts within 30 min, no errors.
- [ ] If anything failed, fix it, restart the soak. Don't move on until 24 h clean.

## Stage 2 — 5-user closed alpha (next week)

Real humans you trust running the product.

- [ ] Recruit five flippers from communities you're already in (Discord, Twitter, Reddit). Don't post publicly. DM only.
- [ ] Send each one: a zip of the `Python Coding` folder, plus `BETA_SETUP.md`, plus your phone number for support.
- [ ] **You will personally walk each one through setup.** 30 minutes per user. This is where you learn what the doc gets wrong.
- [ ] Set a 1:1 weekly check-in with each — ask one question: *"What did you try to do that the app didn't do?"*
- [ ] Track every bug, friction point, and feature gap in a single doc. Don't trust your memory.

**Do not move past Stage 2 until at least 3 of 5 users are running the app weekly without your help.**

## Stage 3 — Hosting + payments (week 3-4)

Stage 2 is everyone running locally. Stage 3 is hosting it so users don't need their own Python install.

- [ ] Decision: hosted on a single VPS (DigitalOcean, $20/mo droplet) or one-instance-per-user on a managed platform (Streamlit Community Cloud, free but rate-limited)?
- [ ] **Recommendation:** start with Streamlit Community Cloud for free, switch to a paid VPS once you hit 20 users.
- [ ] Set up payments. Stripe Checkout is fastest (one day of work). Pricing: $29/mo or $19/mo annual-equivalent. Same product as the monetization plan.
- [ ] Add a paywall component to the Streamlit app. Free users hit the wall after 3 scans/week. Pro users don't. (See `MONETIZATION_PLAN.md`.)
- [ ] Wire up the eBay-OAuth Purchases flow per `PURCHASES_OAUTH_DESIGN.md` so users see their wins automatically.

## Stage 4 — Landing page goes live (week 4-5)

Once you have a hosted product and a payment flow.

- [ ] Build Pattern B from `LANDING_PAGE_AUDIT.md` — wire the React landing page to real engine output. Estimated 4 hours.
- [ ] Add a sign-up form to the landing page. Email + first name + which sport. Stash in a simple Google Sheet for now.
- [ ] Pick a domain. `snipewins.com`, `snipewins.app`, etc. Buy on Namecheap or Cloudflare.
- [ ] Deploy the React app to Vercel (free tier). Connect the domain.
- [ ] Add a "Connect eBay" button on the dashboard once a user signs up.

## Stage 5 — 25-user paid beta (week 5-7)

First paid users. Prices test.

- [ ] Open paid beta to 25 users. Cap at 25 to keep support manageable.
- [ ] Different price for first 10 ($19), next 15 ($29), to A/B test elasticity.
- [ ] Watch retention. **The single number that matters: do they come back next week?**
- [ ] If <50% week-over-week retention, the product isn't ready. Don't scale yet. Find out why.

## Stage 6 — Public launch (week 7+)

Only after Stage 5 retention is confirmed.

- [ ] Write a launch post for one community you're already trusted in (Reddit r/sportscards, a Discord, etc.). Personal, not corporate.
- [ ] Open the waitlist publicly.
- [ ] Add 50-100 users at the announced price.
- [ ] Hire an asynchronous support contractor (Upwork, $20/hr, 5 hrs/week) so support tickets don't eat your engineering time.

## What can go wrong

| Failure mode | What you do |
| --- | --- |
| Soak fails — scheduler dies overnight | Don't move past Stage 1. Fix the failure mode. Probably an unhandled exception in the engine. Check `last_scan.log` last 50 lines. |
| Stage 2 alpha users can't get through setup | Fix the doc. The product isn't broken, the on-ramp is. |
| eBay rate-limits you on 5 users | Quota math: each user runs ~4 scans/day × 27 specs each = 108 calls/day. 5 users = 540/day. Quota is 5,000/day so you're fine. If still hitting limits, audit `_record_api_calls`. |
| First paid users don't come back week 2 | The product isn't producing wins fast enough. Look at scan frequency. Look at deal quality. Talk to every churned user. |
| Refund requests mid-month | Refund without argument. Ask why. Use the answer. |

## How to know you're winning

- 7 of 10 alpha users renew
- Word-of-mouth signups outpace paid acquisition
- Users send you screenshots of wins unprompted

That's the leading indicator that the product works. Everything else is noise.
