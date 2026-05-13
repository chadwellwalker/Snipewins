# SnipeWins — beta tester setup guide

Welcome. This is the 10-minute setup. If something goes wrong, message Chadwell directly with the error you saw and what step you were on.

## What you need before you start

- A Windows, Mac, or Linux computer (the app runs locally on your machine)
- ~500 MB free disk space
- An eBay developer account (free) — we'll set this up in step 3
- A working internet connection (the engine pulls live auction data from eBay every 15 min)

## Step 1 — Install Python 3.12 or newer

The engine uses Python 3.12+ syntax. Check what you have:

```
python --version
```

If you see `Python 3.12.x` or higher, skip to step 2.

If you see anything older (or a "command not found"):

- **Windows:** download from https://www.python.org/downloads/, run the installer, check the box "Add Python to PATH" before clicking install.
- **Mac:** install via Homebrew with `brew install python@3.12`.
- **Linux:** `sudo apt install python3.12 python3.12-venv` (Ubuntu/Debian) or your distro's equivalent.

## Step 2 — Get the project files

Chadwell will share a `.zip` of the project folder. Unzip it somewhere you'll remember (Desktop is fine). Open a terminal and `cd` into that folder.

Verify you're in the right place:

```
cd "path/to/Python Coding"
ls
```

You should see files including `streamlit_app.py`, `ending_soon_engine.py`, `run_app.py`, and a `snipewins-landing/` folder.

## Step 3 — Get an eBay API key

The engine talks to eBay through their official API. You need a free developer account.

1. Go to https://developer.ebay.com/
2. Click "Get Started" → "Sign Up" (use your real email)
3. After verification, navigate to **My Account → Application Keysets**
4. Click "Create a Production keyset"
5. Copy two values:
   - **App ID (Client ID)**
   - **Cert ID (Client Secret)**

## Step 4 — Save your eBay credentials

In the project folder, create a file named `.env` (just `.env`, no extension). Open it in a text editor and paste:

```
EBAY_CLIENT_ID=paste-your-app-id-here
EBAY_CLIENT_SECRET=paste-your-cert-id-here
```

Save and close. **Never share this file or commit it to git.** It's your eBay account access.

## Step 5 — Install Python dependencies

In the terminal, in the project folder, run:

```
pip install streamlit pandas requests python-dotenv
```

This pulls in the libraries the app uses. Should take 1-2 minutes.

## Step 6 — Quick smoke test

Verify the engine works before launching the full app:

```
python smoke_test.py
```

You should see a series of `[SMOKE] [OK]` lines and end with `[SMOKE] [SUMMARY] PASS`. If it fails, copy the FAIL line and message Chadwell.

## Step 7 — Launch the app

```
python run_app.py
```

Streamlit opens in your default browser at `http://localhost:8501`.

The first scan will start ~30 seconds after launch. You'll see "Ending Soon" populate with auctions ending in the next 3 hours. **The first scan can take 1-2 minutes** — that's normal; the engine queries eBay across many player lanes.

## Step 8 — What you should see

A four-tab nav: **Ending Soon · Purchased · Buying Radar · Settings**.

- **Ending Soon** is the main board. Click "Run Scan" to refresh.
- **Purchased** shows cards you've bought via the engine (empty until you start using it).
- **Buying Radar** shows the urgent 30-min-ending feed. Most useful Sun/Mon evenings PT.
- **Settings** has the configuration knobs.

The page also shows a peak-times advisory banner. If you see "OFF-PEAK" you'll get fewer results — that's expected, eBay auction volume cycles with the day of week.

## Step 9 — Healthcheck (run in a second terminal anytime)

```
python healthcheck.py
```

Tells you whether the background scheduler is alive, when the last scan ran, and whether the API quota is healthy. Run this if the page seems stale.

## Common issues

**"python: command not found"**
Python isn't on your PATH. On Windows, reinstall Python with the "Add to PATH" box checked.

**"streamlit: command not found"**
The `pip install` failed silently. Re-run it. If it still fails, you may need `pip install --break-system-packages streamlit pandas requests python-dotenv`.

**Streamlit opens but the page is blank**
First load takes ~10 seconds. If still blank after 30s, check the terminal for a stack trace and message Chadwell.

**"Missing EBAY_CLIENT_ID in .env"**
The `.env` file isn't where the app expects it. It needs to be in the same folder as `streamlit_app.py`. Double-check the filename — it's `.env`, not `env.txt` or `env`.

**The scan starts but never finishes**
The engine logs every step to `last_scan.log` in the project folder. Open that file in a text editor. If you see a Python traceback near the end, send the last 30 lines to Chadwell. If it just stops mid-scan with no error, you may have lost connection to eBay; restart the app.

**Auction-end-time appears wrong**
The app uses your computer's local time. If your clock is wrong, fix that first.

## Limits

- This is **beta software**. Things will break. Send screenshots of what broke and what you were doing.
- The eBay API has a daily quota (~5,000 calls). You won't hit it under normal use, but if you trigger 50+ scans in a day you may see a "rate limited" message — wait an hour.
- The app stores your eBay credentials and scan history locally on your machine. Don't share screenshots of your `.env` file.

## How to give feedback

Anything you notice — confusing UI, missing features, broken pages, suggestions — message Chadwell directly. Include:

- What you were trying to do
- What happened instead
- Screenshot if visual
- The last 20 lines of `last_scan.log` if it's an engine issue

Thanks for testing.
