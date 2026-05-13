# Purchases — eBay OAuth integration design

Decision date: 2026-05-06
Status: Design only. No code in this commit.
Owner: Chadwell

## Goal

User connects their eBay account once. The app automatically pulls their
purchase history thereafter. No manual entry. Just like the eBay app itself.

## Why this matters

User quote: *"I'd prefer if they logged into their eBay account and we
had access to their purchases so they don't manually have to enter them.
I know I would not do that as a user because I'd expect it to be done
for me. Just like the eBay app already does."*

Manual purchase entry is the kind of friction that kills retention.
A user who has to log every win in a separate app is a user who stops
logging wins, then stops trusting your tracking, then leaves.

## Current state (what exists today)

```
ebay_auth.py
└── get_application_access_token()   ← APPLICATION token only
                                        (client_credentials grant)
                                        Used by ending_soon_engine for
                                        public Browse API. Cannot read
                                        any user-specific data.

tab_purchased.py
└── _load_all_purchases()            ← reads local CSVs (snipe_log,
                                        auto_log). No eBay API calls.
                                        No notion of "the user's eBay
                                        account."
```

The app currently has no concept of a logged-in eBay user. We need to add one.

## What we're building

```
1. "Connect eBay" button in Settings or Purchased tab
       │
       ▼
2. eBay OAuth Authorization Code flow
       │  (redirects user to eBay, user consents, eBay redirects back
       │   to our app with a one-time code)
       ▼
3. Exchange code → user_access_token + user_refresh_token (eBay)
       │
       ▼
4. Store user_refresh_token securely (encrypted at rest)
       │
       ▼
5. Background sync job: every 15-30 min
       │  (a) Use refresh token to get fresh user_access_token
       │  (b) Call eBay buyer-purchase endpoints
       │  (c) Diff against local store, persist new orders
       │
       ▼
6. Purchased tab reads from the local store, not from CSV
```

## eBay API choices

This is the part that needs real research. Three candidate approaches:

### Option 1 — Trading API `GetMyeBayBuying` (legacy, XML)

- **What it returns:** complete won-items + bidding-list + watching-list
- **Auth:** user OAuth token via "Auth'n'Auth" or modern OAuth user token
- **Pros:** the canonical answer. Returns exactly what we want.
- **Cons:** legacy XML/SOAP API. eBay deprecating it slowly. Has worked for years.
- **Verdict:** still the most reliable way as of 2026. Use unless eBay has formally pulled it.

### Option 2 — Buy → Order API `getPurchaseOrder` (modern REST)

- **What it returns:** single purchase order details by ID
- **Auth:** user OAuth token, scope `https://api.ebay.com/oauth/api_scope/buy.order.readonly`
- **Pros:** modern REST. JSON. Future-proof.
- **Cons:** **NO LIST ENDPOINT.** You need the orderId to call it. Useless for "show me all my purchases" UNLESS we get IDs from somewhere else first.
- **Verdict:** can't be the primary mechanism. Could be used to enrich items returned by Trading API.

### Option 3 — User Notification Webhooks

- **What it does:** eBay pushes a notification whenever the user buys an item.
- **Pros:** real-time, no polling, no scope to drift.
- **Cons:** requires public webhook endpoint (the app needs an internet-reachable URL). Streamlit running on a user's laptop doesn't have one. Backend changes required.
- **Verdict:** add later, after we have a hosted backend. Not for v1.

**Recommendation: Option 1 (Trading API GetMyeBayBuying) for v1.**
Add Option 3 (webhooks) after v1 if/when you host a backend.

## OAuth scopes we'll need

For `GetMyeBayBuying` and related buyer endpoints:

```
https://api.ebay.com/oauth/api_scope/buy.order.readonly
https://api.ebay.com/oauth/api_scope/buy.guest.order
https://api.ebay.com/oauth/api_scope/commerce.identity.readonly
```

(The exact list depends on which endpoints you settle on. Pull
requirements from each endpoint's docs at
https://developer.ebay.com/api-docs/buy/order/static/overview.html
when you write the code.)

## Token storage

This is the critical security part. eBay user tokens are bearer tokens
that, if leaked, let an attacker read someone's purchase history.

Required minimum:

1. **Never** put tokens in `.env`, in the git repo, or in any file the
   user can email someone.
2. Store the **refresh token** encrypted at rest. Use the OS keychain
   if possible (`keyring` Python lib for cross-platform).
3. Store the **access token** in memory only. Re-fetch it from refresh
   each session.
4. Per-user token isolation. Don't mix tokens across users.

## OAuth redirect URI

eBay requires you register a fixed redirect URI at app registration time.

For local Streamlit dev: `http://localhost:8501/oauth/callback`
For hosted prod: `https://yourdomain.com/oauth/callback`

eBay's quirk: redirect URIs cannot include query strings. We'll need a
small handler that catches the `code` parameter eBay appends.

Streamlit doesn't natively handle OAuth callbacks (no routing). Two
workarounds:

- **Workaround A — manual paste.** User clicks "Connect eBay," gets
  redirected to eBay, eBay redirects back to a static page that displays
  the code. User copy-pastes the code into the Streamlit app. Ugly but
  works for v1 alpha.
- **Workaround B — separate Flask handler on the same machine.** Run a
  tiny Flask app on port 5000 alongside Streamlit, use `localhost:5000`
  as the redirect URI, Flask handles the callback and writes the token
  to a shared file/keychain that Streamlit reads. Clean.

Recommendation: ship Workaround A for the first 10 paying users to
prove demand exists. Switch to Workaround B once you have a hosted
backend.

## Implementation steps (when we're ready to write code)

1. **Register OAuth app** at https://developer.ebay.com/my/keys for
   user-token flow. Get client_id (production), client_secret, set
   redirect URI.
2. **Extend ebay_auth.py** with three new functions:
   - `build_user_consent_url(state) -> str`
   - `exchange_code_for_user_token(auth_code) -> dict` (returns access + refresh)
   - `refresh_user_access_token(refresh_token) -> str`
3. **New module `ebay_purchases.py`** with:
   - `fetch_my_ebay_buying(access_token) -> List[Dict]` (Trading API call)
   - `parse_purchase_xml(xml_text) -> List[Order]`
   - `merge_into_local_store(orders, user_id) -> int` (returns count_new)
4. **New token store `user_credentials.py`**:
   - `save_refresh_token(user_id, refresh_token) -> None` (encrypted)
   - `load_refresh_token(user_id) -> Optional[str]`
5. **Settings tab → Account section**:
   - "Connect eBay" button → opens consent URL in new tab
   - Code input field → POSTs back to backend → stored
   - Connection status badge ("Connected" / "Not connected")
   - "Disconnect" button → clears token from store
6. **Background sync** (in scan_scheduler or separate thread):
   - Every 15 min, refresh access token + fetch purchases
   - Write new orders to a SQLite or JSON store
   - Emit `[EBAY_PURCHASE_SYNC]` log line
7. **Refactor tab_purchased.py** to read from the new store, not CSVs.
   Keep CSV reads as fallback so existing data doesn't disappear.

## Estimated effort

- OAuth flow with Workaround A: 1 day
- Trading API call + XML parsing: 1 day
- Local store + sync loop: 0.5 day
- Settings UI: 0.5 day
- Migration of tab_purchased to new store: 0.5 day
- Testing with a real eBay account: 1 day

**Total: ~4-5 working days for a clean v1.**

## Risks

- **eBay deprecates Trading API mid-build.** Fallback: switch to whatever
  REST endpoint is current. Recheck https://developer.ebay.com/develop/get-started/
  before starting code.
- **Refresh token revocation by user.** Handle gracefully — show
  "reconnect" prompt, don't crash sync.
- **Rate limits on Trading API.** GetMyeBayBuying is fine at 15-min
  cadence per user; don't poll faster.
- **Streamlit OAuth callback awkwardness.** See Workaround A/B above.

## Open questions for Chadwell before we write code

1. Self-hosted (user runs the Streamlit app on their laptop) vs hosted
   (we run a server users connect to)? This decides A vs B above.
2. Multi-account support? Some flippers run 2-3 eBay accounts.
3. Sync cadence: 15 min, 30 min, 1 hour? More frequent = more API calls
   per user; eBay quotas matter.
4. Show buy-it-now BIN history alongside auction wins, or split into
   tabs? Both come from the same Trading API call.
