# Live integration handoff

## Current boundary

The deployed application uses `DEPLOYMENT_MODE=demo`. Its existing ledger,
wallet, trade and loan endpoints are simulations denominated in `DEMO_TON`.
They are not proof of custody or actual TON balances. Imported Telegram prices
are observations, not executable quotes or guaranteed collateral valuations.

`DEPLOYMENT_MODE=production` requires `GIFT_PROVIDER_MODE=disabled`, disables
the demo financial routes (including GETs that seed accounts) and stops the
demo autopay loop. Authentication, public catalog, market data and protected
administration remain available. This is a safe maintenance mode, NOT a switch
that enables real operations. A separate clean live ledger/database is required;
never relabel or migrate demo balances into real TON.

`GET /api/integrations/status` describes actual capabilities to an authenticated
user. `POST /api/webhooks/{provider}` intentionally returns 503 for every
provider. No supplied keys or a `paid=true` JSON body can credit money.
`app/integrations.py` contains the disabled payment adapter and exact nanoTON
receipt contract. Provider verification and live settlement are not implemented.

## Information to supply privately when connecting

| Integration | Required decisions / credentials |
| --- | --- |
| Telegram gift custody | Bot username/token through secret settings; whether Bot API business gifts or an MTProto custodian is used; supported transfer operations, ownership verification, transfer fees and holding periods; dedicated account if needed |
| Crypto Bot | Provider environment, API credential and documented webhook verification rules; supported TON payments, expiry, invoice fees and withdrawal policy |
| Direct TON | Mainnet/testnet, receiving wallet, signing/custody method, RPC/indexer access, confirmation threshold, memo/invoice routing and fee reserve |
| Loans | LTV and valuation policy, rates, principal limits, extension terms, grace/default/liquidation policy, partial repayment and notification rules |
| Operations | Named admins, separate live database, always-on worker budget, encrypted off-site backup destination and alert channel |

Never send seed phrases, personal Telegram sessions, login codes or tokens in a
Git commit, issue, screenshot or frontend environment variable. Use provider
secret storage. A bot token alone does not establish that gift custody/transfer
is technically available for the chosen account and gift type.

## Required implementation at activation

1. Add a provider-specific adapter. Verify signatures on the raw bounded body;
   TON adapters must independently verify network, transaction, recipient,
   asset, amount, confirmation/finality and invoice association. Client success
   screens and frontend balance values are never payment authority.
2. Persist invoices, provider transaction IDs, webhook inbox and transfer outbox.
   Deduplicate both events AND underlying payment/transfer IDs using unique DB
   constraints. Settle ledger, invoice and event atomically, with owner locks.
3. Reserve withdrawals/collateral before submission. On timeout keep the reserve
   and mark the result unknown; reconcile provider state before any retry. An
   accepted submission is not a successful delivery. Never retry an unknown
   outgoing transfer blindly.
4. Keep physical custody and logical ownership separate. Reject duplicate external
   gift IDs, unknown deposits, unsupported gifts, conflicting reservations and
   attempts to withdraw another user's asset. Quarantine unmatched deposits.
5. Use durable scheduled jobs for loan deadlines and reconciliation; recover on
   restart. Never sell, liquidate or release real collateral through demo code.
6. Add scoped operator actions only with an append-only audit trail, reason,
   permission checks and explicit confirmation. The current admin is read-only.

## Acceptance tests before enabling real users

- Replay one paid invoice 20 times with same/different callback event IDs: one
  credit. Wrong signature, network, amount, asset, recipient or owner: zero.
- Late/partial/out-of-order callbacks cannot roll a final payment backwards.
- Concurrent spends cannot exceed confirmed funds; one-nano precision preserved.
- Crash before/after provider accepts withdrawal: reconcile without double send.
- Concurrent exchange, pledge and withdrawal of one gift: one reservation wins.
- Loan expiry, autopay, extension and repayment racing: one valid final state.
- Provider outage/expired quote/stale price: fail closed, funds remain accounted.
- Restore an encrypted backup into an isolated DB; verify schema, row counts,
  ledger reconciliation and replay safety before resuming outgoing jobs.
- Separate-account end-to-end tests through the actual Telegram Mini App and
  test provider; then a small explicitly approved real transaction rehearsal.

These checks require the chosen live providers. Contract tests and a disabled
adapter are preparation, not certification of future integrations.
