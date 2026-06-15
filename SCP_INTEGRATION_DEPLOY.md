# SnipeWins — SportsCardsPro Valuation: Deploy & Operations

## What changed (and why)
eBay's sold-comp APIs are dead (Finding decommissioned, Marketplace Insights
partner-gated). Market value now comes from **SportsCardsPro's Legendary CSV
price guides** (full graded ladder), loaded into a local SQLite store. eBay's
API budget is now spent **only on discovery** (finding auctions/BIN listings).

### New files
- `scp_price_store.py` — SQLite price store + eBay-title→product matcher (grade-aware, set-aware).
- `scp_sync.py` — imports downloaded set CSVs into `scp_csv/` and rebuilds the store.
- `scp_validate.py` — coverage check against `daily_pool.json` (dev tool).
- `scp_csv/` — the per-set CSVs (the data). `scp_prices.db` — the built store.

### Modified files (backups saved as *.PRE_SCP_backup.YYYYMMDD.py)
- `valuation_engine.py` — `run_hybrid_valuation` now returns SCP value first (after Card Ladder), before any eBay comps.
- `comp_engine_v2.py` — `get_market_value_for_item` returns SCP value first.
- `market_value_engine.py` — `get_market_value_for_item` returns SCP value first.
- `ebay_search.py` — comp fetchers (`search_comp_pool`, `search_market_comps_browse`,
  `search_completed_items_finding`) are OFF by default; discovery scans untouched.

## Environment variables
| Var | Default | Purpose |
|-----|---------|---------|
| `SNIPEWINS_SCP_DB_PATH` | `./scp_prices.db` | Built price store. On Render point to the persistent disk, e.g. `/data/scp_prices.db`. |
| `SNIPEWINS_SCP_CSV_DIR` | `./scp_csv` | Folder of per-set CSVs. On Render: `/data/scp_csv`. |
| `SNIPEWINS_ENABLE_EBAY_COMPS` | `0` (off) | Set to `1` only if you ever want eBay comp calls back. |

## Local: see it work now
1. `python scp_sync.py`     # loads scp_csv/ → scp_prices.db
2. Restart the app (so new code loads): `python run_app.py`
3. Run a scan in the UI. Pool rows should show market value with source `sportscardspro_csv`.

## Deploy to snipewins.com (Render)
1. Commit & push the new + modified `.py` files.
2. Get the data onto the persistent disk (the store is NOT in git):
   - Easiest: upload `scp_csv/*.csv` to `/data/scp_csv` and run `python scp_sync.py`
     once on the server (rebuilds `/data/scp_prices.db`), OR upload a prebuilt `scp_prices.db` to `/data`.
   - Set `SNIPEWINS_SCP_DB_PATH=/data/scp_prices.db` and `SNIPEWINS_SCP_CSV_DIR=/data/scp_csv`.
3. Redeploy / restart the service so it loads the new code + store.
4. Trigger a scan. The live pool will re-value from SCP.

> Until the data + code are on the server and a scan runs, snipewins.com keeps
> showing the old "no recent comps". It does not update on its own.

## Weekly price refresh
Graded prices drift slowly, so weekly is plenty:
1. Open each set page on SportsCardsPro and click **Download Price List**
   (manual clicks; Chrome blocks scripted bulk downloads). Set list is in
   `SCP_SET_LIST.md` (or your saved links).
2. `python scp_sync.py`   # re-imports newest CSVs (overwrites by set) + rebuilds
3. Redeploy the refreshed `scp_prices.db`/`scp_csv` to the server.

## Coverage today (validated)
16 sets, ~179k products, ~78k with PSA 10 values. On a real `daily_pool`
sample: 95% matched the right product, 79% priced at the exact grade. Misses
fail safe (return nothing) rather than mispricing.
