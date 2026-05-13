# 24-hour scheduler soak — runbook

Goal: prove that `scan_scheduler` keeps producing deals for 24 hours without
intervention. This is the gate before you let beta users run the app —
nobody stays in a deal-finder that goes silent overnight.

## Setup (one-time)

You already have everything needed:

- `scan_scheduler.py` — the scheduler itself, runs scans on a 15-minute
  interval (configurable via `scheduler_settings.json`).
- `scheduler_heartbeat.json` — written at the end of every successful scan
  (added in Phase 2).
- `healthcheck.py` — tripwire that reads the heartbeat and tells you if the
  scheduler is still alive. Exit code 0 = healthy, non-zero = problem.

## Run the soak

Open a terminal in the `Python Coding` folder and start the scheduler in
"normal-app" mode. The simplest path is:

```
python run_app.py
```

That launches Streamlit and the scheduler in one process and tees all output
to `last_scan.log`. Click the "Auto-scan: ON" toggle in the UI (or whatever
you usually click to enable scheduled scans). Leave the terminal running.
Walk away.

If you'd rather run headless without Streamlit, use this instead:

```
python -c "import scan_scheduler as s; s.start(); import time; time.sleep(86400)"
```

That runs the scheduler thread for exactly 24 hours and exits.

## Watch the soak from another terminal (or your phone)

Every 5 minutes, run:

```
python healthcheck.py
```

You should see something like:

```
[HEALTHCHECK] HEALTHY — last scan 8.3m ago; 42 deals; 47s duration; threshold 22.5m
```

If you ever see one of these:

- `[HEALTHCHECK] STALE — no scan for 47.2m ...` — scheduler is dead. Note
  the time, kill the terminal, restart, file a bug.
- `[HEALTHCHECK] RATE_LIMITED — ...` — eBay throttled you. Reduce
  `interval_secs` in `scheduler_settings.json` or shrink your player set.
- `[HEALTHCHECK] ERROR — last scan errored: ...` — engine crashed during a
  scan. Capture the message, find the matching traceback in `last_scan.log`,
  fix it.
- `[HEALTHCHECK] NEVER_RUN — ...` — the scheduler hasn't completed a scan
  yet. If it's been more than 30 minutes since you started, something's wrong.

## Pass criteria

After 24 hours, the soak passes if:

1. `healthcheck.py` returned HEALTHY at every check.
2. `scheduler_heartbeat.json` shows `last_scan_ts` within the last 30 minutes.
3. The scan history has at least ~80 successful scans (24h × 4 scans/h).
4. No tracebacks in `last_scan.log` (`grep "Traceback" last_scan.log`
   should be empty).
5. `smoke_test.py` still passes when run on the side.

## If the soak fails

The most common failures and what they usually mean:

| Symptom | Likely cause |
| --- | --- |
| STALE for ~hour, then back HEALTHY | Single bad scan or transient eBay outage |
| STALE permanently | Scheduler thread crashed; restart Streamlit |
| Recurring RATE_LIMITED | Player set too large, interval too short, or eBay quota tier too low |
| ERROR with valuation message | New comp data tripped the engine; check the recent edit |
| Tracebacks in log but app still runs | Background task failure; not fatal but worth investigating |

## After the soak passes

Move on to Phase 3 (`PHASE 3 — Wire LiveDealFeed to real backend`). The
soak is your foundation — everything user-facing depends on the engine
staying alive.
