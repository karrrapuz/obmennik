# Operations

All balances, trades and referral rewards are DEMO_TON. These checks do not
certify real payments, external delivery or financial solvency.

## Integration

The module is wired into `create_app` in `backend/app/main.py`, using the
server-side settings allowlist and existing database/session dependencies:

```python
register_operations_routes(app, database, current_session, settings.admin_user_ids, settings=settings)
```

The confirmed operator ID is 1649969295; configure it in the server allowlist,
not as a hard-coded fallback. Supply a server-controlled collection of positive integer Telegram
user IDs. An empty collection denies everyone. Never take this allowlist from
a request, frontend state or a referral code. Use the existing authenticated
session dependency; it checks expiration and revocation. Never publish bearer
tokens or pass them in URL query strings.

`GET /api/admin/readiness` is excluded from OpenAPI and requires an allowed
authenticated user. It returns 200 only when database connectivity, migration
heads/model table-column presence, and stored market freshness pass; otherwise
503. `operational_ready` describes those infrastructure checks independently.
`live_ready` remains false until production mode and all live payment, gift
transfer and loan capabilities are implemented. Production `ready` also requires
those capabilities; demo readiness is never permission to process real funds.
Missing settings fail closed. Responses are no-store and contain fixed status labels, not SQL errors or
credentials. Authentication/database dependency failures can precede this
handler and follow the application's existing error policy.

Schema inspection does not prove constraint/trigger definitions or detect all
schema drift. Market checks inspect the stored envelope, not every listing;
ingestion remains responsible for full validation. Missing DB snapshots fail
readiness even if a display-only file fallback exists. A stale market does not
make sample-priced demo trades executable at market prices.

Ledger status is explicitly `not_checked_use_offline_audit`. Do not interpret
readiness as ledger reconciliation. The existing `app.ledger_audit.audit_ledger`
does a full aggregate scan; run `backend/scripts/audit_ledger.py` separately
under controlled load. Do not put an unbounded ledger scan on every probe.
This endpoint is for low-frequency authenticated operator checks, not public
load-balancer probes. Leave public `/api/health` as the minimal connectivity probe.

## Backup

No scheduled backups, retention service, off-site uploads or restore verification
are configured by these files. Assign an owner, recovery point objective and
recovery time objective before claiming backup coverage.
No encrypted off-site backup destination is currently configured. The backup
CLI and its mocked subprocess tests are not evidence of an actual backup or
successful restore.

Install a PostgreSQL `pg_dump` version compatible with the source server
(prefer the same major version). Use a direct, approved database endpoint rather
than a transaction pooler. Inject DATABASE_URL through a protected process
environment, not command history, argv, source control or chat. Then run:

```powershell
python backend/scripts/backup_database.py --output D:\ProtectedBackups\giftmoney-2026-11-01.dump
```

Choose a new path outside the repository in an existing restricted directory.
The script refuses overwrite, creates a custom archive, suppresses raw tool
errors and removes newly created partial files on failure. Connection credentials
are passed through libpq environment variables, never command arguments.
Inherited PG settings are cleared. TLS defaults to verify-full; explicit require
or verify-ca are supported. Do not weaken TLS to disable/prefer/allow. Configure
trusted certificates where needed. The script does not load dotenv files.

Archives contain sensitive user/session data and are NOT encrypted by pg_dump.
Use OS encryption and restricted directory ACLs (especially on Windows, where
POSIX mode 0600 does not establish a private ACL), encrypted transport and an
approved encrypted off-site store. Never commit archives. Limit access to child
process environments; privileged local users can inspect them. Use dedicated
least-privilege backup credentials. Schema-level dumps do not include cluster
roles or provider configuration; inventory those separately without exporting
secrets. Monitor exit codes, archive size, last success and off-site delivery.

## Isolated Restore Drill

1. Provision a disposable isolated PostgreSQL database with no production routes,
   credentials, integrations, workers or outbound financial side effects. Never
   point a restore test at production. Prefer synthetic data for ordinary tests;
   protect production-derived data to the same standard as production.
2. Verify the archive hash against a separately stored checksum, and use
   `pg_restore --list` to confirm readability. This alone is not a restore test.
3. Set libpq environment variables to the verified isolated target. Restore with
   `pg_restore --no-owner --no-acl --exit-on-error --single-transaction --dbname TARGET_DB ARCHIVE`.
   TARGET_DB must be the isolated database name, not a credential URI. Do not use
   `--clean` against any shared database. Inspect the actual target host/name
   before executing, without printing passwords.
4. Check row counts against the captured source baseline, Alembic heads, foreign
   keys, checks, indexes and deferred PostgreSQL ledger triggers. Run the ledger
   audit and isolated authentication/referral/trade replay tests. Disable loan
   autopay and other app startup workers during initial inspection.
5. Record backup timestamp, restore duration, validation results and operator;
   compare measured data loss/duration with recovery objectives. Securely retire
   the test database and archive copies using approved retention procedures.
6. Production recovery requires explicit approval, a write/worker freeze, a
   preserved incident copy, a verified restore target and a documented cutover
   and rollback plan. Never improvise by editing the Alembic version stamp.

## Monitoring And Launch Checklist

The `.github/workflows/availability.yml` workflow defines a read-only public API
smoke check every six hours and on manual dispatch. This is not continuous
monitoring, authenticated readiness, a backup job or proof that alert delivery
is configured. Verify workflow execution and notification ownership separately.
The scheduled invocation also requires a complete, non-empty, unexpired market
envelope (`--require-fresh`); this is not per-listing valuation validation.

The profile exposes the embedded admin only after `/api/admin/overview` grants
access for the current Telegram session. The token stays in React memory, not a
URL or persistent browser store. Standalone `/admin` is an operator/developer
fallback requiring an existing valid session token; it is not a separate login.

- Assign ownership and alerts for availability/5xx, latency, connection saturation,
  disk/storage growth, migration failures, market age, backup age/failure and
  failed ledger reconciliation. Baseline expected values before choosing limits.
- Verify real migration upgrade and rollback/recovery procedures on an isolated
  populated database. Check financial constraints/triggers, not only table names.
- Verify signed Telegram login, admin denial/allow, referral attribution, trade
  idempotency and earned/promo claim separation on the intended deployment.
- Push a validated public market snapshot after migration/deploy and verify
  freshness. Local hourly watch is opt-in and machine-dependent; do not claim
  server-side scheduling or upload personal Telegram sessions/credentials.
- Confirm CORS origins and TLS settings; configure edge rate limits, request-body
  limits, upload deadlines and concurrency limits. Application auth is not rate
  limiting. Include login, public valuation/catalog and authenticated mutation
  routes in abuse protection. An admin-only probe still needs modest polling.
- Existing middleware sets request IDs and no-store and suppresses raw request/DB
  details in its own error logs. Verify hosting/proxy/access logs independently:
  redact Authorization, init_data, cookies, database URLs and ingestion keys.
  Do not add query-string tokens. Request IDs support correlation, not audit trails.
- Missing authentication rate limiting is an explicit launch blocker. The
  current body limiter caps covered API POST/PUT/PATCH requests at 65,536 bytes
  (64 KiB); market ingestion has its own authenticated 16 MiB cap. Byte limits
  are not request-rate, upload-duration or concurrent-connection limits.
  No application-wide rate limiter was identified in main.py. Its current
  middleware supplies nosniff and no-referrer, with stricter framing/CSP for
  admin pages. Review frontend CSP and HSTS at the serving layer; account for
  Telegram embedding before enabling frame restrictions. This module does not
  configure those policies.
- Verify backup scheduling, encryption, retention, restore-drill evidence and
  alert delivery before stating that automated recoverability exists.
