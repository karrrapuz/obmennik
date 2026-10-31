# Referral Accounting

The current asset is `DEMO_TON`. These entries are not real TON payments.
Real custody and payment adapters remain separate integration work.

- Attribution is accepted only from the verified Telegram `start_param`,
  `ref_<code>`, when the invited user is first created. Existing accounts cannot
  be rebound. Self-referrals and unsigned URL parameters are ignored.
- `REFERRAL_RATE_BPS=200` means 2% of the server-priced received gift value,
  not both sides of the exchange and not a percentage of the wallet top-up.
- The exact rate and actual markup are frozen with the quote. The reward is
  `min(received_nano * rate_bps // 10000, fee_nano)`. There is no reward above
  the collected markup. Old quotes without these fields earn zero.
- Only a successfully executed quote accrues the reward. Its unique quote ID
  prevents duplicate rewards across retries and different idempotency keys.
- Reward credit, gift ownership and buyer settlement commit together. Any
  late failure rolls them all back. PostgreSQL participant locks are sorted
  by user ID; claims serialize on the same user row.
- Legacy 5 TON promotional balances remain historical demo funds. The new
  earned-only claim route cannot claim them; the old promotional claim route
  cannot consume earned rewards.
- A full referral account holds the entitlement instead of rejecting the
  buyer's exchange. Held rewards are retried when the owner refreshes or claims.

## API

`GET /api/referrals` requires the current user's bearer token. It returns
invited count, lifetime turnover/earnings, available/held nano amounts, rate,
and a Telegram invitation URL. It does not expose invited users' identities.

`POST /api/referrals/claim` accepts `{}` and an `Idempotency-Key`. It transfers
only available earned rewards to the wallet and returns `wallet` and `referral`.
Clients persist the key before sending and reuse it after an uncertain response.

`TELEGRAM_BOT_USERNAME` configures the public `https://t.me/<bot>?startapp=...`
link. No bot token or user session is exposed to the frontend.

Before enabling real assets, define reversal/chargeback policy, fraud controls,
verified custody and confirmed net-fee accounting. Demo credit must never become
a real withdrawal entitlement merely by changing the displayed currency label.
