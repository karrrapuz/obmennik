# Dedicated Market Worker: Prepared, Not Activated

## Scope And Activation Gate

This package is deployment preparation only. No cloud service was created,
no paid plan was enabled, and no personal Telegram session was read, converted,
exported or uploaded. Activation is explicitly pending approval and provisioning
of a **separate, dedicated Telegram account**. Do not use the existing personal
catalog session. The dedicated account must not hold funds or customer gifts.

The worker only collects public gift metadata/resale observations and sends
validated public snapshots to the existing authenticated ingestion endpoint.
It does not implement admin routes, payments, deposits, gift custody, purchases,
loans or transfers. Other application owners control those modules. Production
mode or successful market ingestion must never be interpreted as permission to
enable real financial operations. Future integrations remain disabled until a
separate custody, authentication, audit and reconciliation review is complete.

## Current Repository Constraints

The existing `render.yaml` defines only the free Python API and installs
`requirements.txt`, not Telethon. Its start command runs database migrations and
Uvicorn. Adding an in-process scheduler there would duplicate work across API
workers/restarts and does not provide an always-on collector. The normal backend
Dockerfile likewise is not the market-worker image. Neither file is changed here.

The prepared worker requires no database password, bot token, admin IDs or payment
credentials. It publishes through `POST /api/internal/market/snapshots`; the API
remains responsible for validation and atomic database persistence. It needs the
same catalog identity/trait snapshot as the API. Deploy catalog changes to both
before starting collection. Fresh upgrade metadata expands collection candidacy,
but never invents missing catalog trait IDs. New base IDs still require a catalog
refresh. Public listing artifacts are runtime spool files, not image inputs.

## Files And Commands

`backend/scripts/market_worker.py` is the dedicated-account entrypoint.
`backend/Dockerfile.market` uses Python 3.12, the existing Telethon requirements,
an unprivileged UID, selective code/catalog copies, and an exec-form entrypoint
that receives SIGTERM directly. It does not copy dotenv files, SQLite databases,
sessions, generated listings, frontend media or the whole repository. Build
context must be `backend`, retaining its existing `.dockerignore`.

The following are preparation instructions, **not commands executed by this work**:

```sh
# From repository root; no secrets in build args, Dockerfile or image layers:
docker build -f backend/Dockerfile.market -t giftmoney-market-worker backend

# On the selected host with approved runtime secret injection already configured:
python -m scripts.market_worker --check-config
python -m scripts.market_worker --once
python -m scripts.market_worker
```

Native commands run with working directory `backend`. `--check-config` parses
configuration/session format without opening a session, writing files or making
network calls. `--once` performs one bounded attempt then exits; no argument runs
the hourly-or-slower loop. Never pass secrets in command-line arguments. The
existing local collector, watch and push-only commands remain available and do
not implicitly switch to this cloud account path.

## Runtime Configuration

The worker reads **only its process environment**, never `.env`, `.env.market`,
`.env.telegram` or `.local/telegram/catalog.session`. All gates default to off.

| Variable | Required value / bounds |
| --- | --- |
| `MARKET_WORKER_ENABLED` | Literal `true`, explicit operator enablement |
| `MARKET_ALLOW_CLOUD_SESSION` | Literal `true`, explicit permission for dedicated session hosting |
| `MARKET_SESSION_ACCOUNT` | Literal `dedicated`, operator attestation, not identity verification |
| `TELEGRAM_API_ID` | Dedicated app's positive integer, at most 2147483647 |
| `TELEGRAM_API_HASH` | Dedicated app's 32 hexadecimal characters; secret |
| `TELEGRAM_SESSION_STRING` | Authorized dedicated-account Telethon v1 StringSession; secret |
| `MARKET_API_URL` | HTTPS origin only, no userinfo, query, fragment or path |
| `MARKET_INGEST_KEY` | Same server ingest key, 32-512 non-whitespace ASCII characters; secret |
| `MARKET_WORK_DIR` | Absolute private writable spool; default OS temp directory plus `giftmoney-market-worker` |
| `MARKET_INTERVAL_SECONDS` | 3600-86400, default 3600, measured after each attempt |
| `MARKET_PAGES` | 1-3, default 2 |
| `MARKET_CYCLE_TIMEOUT_SECONDS` | 60-3600, default 1800, includes collection and upload |
| `MARKET_MAX_FAILURES` | 1-10 consecutive failed cycles, default 3, then exit 2 |

The Docker spool defaults to `/tmp/giftmoney-market-worker`. Mounting a shared
spool is optional, not a way to persist authorization. The StringSession stays in
memory and is never saved to disk. A StringSession is a powerful account secret,
not a read-only token: these environment gates do not restrict what a stolen
session could do. Use host secret management, least-privilege operator access,
secret masking and a dedicated account. Never attach the session to the API or
frontend environment. Provisioning/authorizing that separate account is an
operator task outside this worker; no exporter or browser/QR/SMS/2FA login is
implemented here. Unauthorized sessions cause exit 2 without any login attempt.

## Scheduling And Shutdown

Each cycle creates an in-memory Telethon client, makes the existing bounded
public requests, closes Telegram, and then sends the complete public pair. No
partial collection is uploaded. The existing collector checks fresh public
upgradeability, catalog allowlists, TON-only integer amounts, and exact listing
coverage. Request retries/connections are bounded, and a short FloodWait is
retried once by the collector. A longer FloodWait extends the next cycle's
delay to at least the requested wait plus one second.

There are no rapid retry loops: one full attempt per interval, at most the
configured consecutive failures before stopping. A supervisor's restart policy
is outside this process: configure backoff and alerting, not rapid unconditional
restarts that defeat these limits. With `--once`, a failed attempt exits 2
immediately; the external scheduler must respect Telegram cooldowns, especially
if a FloodWait exceeds its normal schedule. A continuous worker is preferable
when enforcing such cooldowns across attempts without external scheduler state.

The existing upload performs an unauthenticated same-origin health warm-up
(90-second deadline) before the authenticated snapshot POST (30-second network
timeout); it consumes neither response body and follows no redirects or proxies.
The overall cycle has its own configured timeout. No secret/error payloads are
logged; generic class names and public cycle results are sufficient for alerts.

SIGTERM/SIGINT on Linux stop idle waits immediately, cancel the current cycle,
and allow up to 10 seconds for Telegram disconnect. Cancellation does not start
a new upload. An already-sent POST can have committed before cancellation or a
lost acknowledgement: check the server capture timestamp instead of assuming
it failed. A hard kill cannot guarantee cleanup; atomic server snapshots protect
the previous complete database state. Windows falls back to Ctrl+C cancellation.

An OS lock prevents simultaneous processes using the same spool directory on
one host/shared filesystem and is released on process exit. It is **not a
distributed account lease**. Run exactly one scheduler/replica for the account;
stop the desktop watcher before activating cloud collection. Use stop-before-start
deployments, or an external distributed lease before considering rolling/multi-
instance deployment. Render can overlap old/new instances during deploy; merely
setting instance count to one is not an overlap guarantee. The server's monotonic
CAS protects snapshots but cannot prevent duplicate Telegram account activity.

## Workable Hosting Options And Costs

Official references were checked during preparation; confirm current pricing
before authorizing spend. Dynamic compute prices were not exposed in the
retrievable pricing page, so no specific monthly worker estimate is promised.

- **Dedicated Linux host/VPS or an existing always-on machine:** run the container
  or native worker under a supervisor, one process, with secret injection and
  restart backoff. Hosting cost depends on the selected provider; an existing
  machine still has power, connectivity, maintenance and uptime costs. No cloud
  session leaves the local machine when the existing local watcher is used.
- **Render background worker:** separate continuously running outbound process;
  no public URL or HTTP health endpoint is required. Select and approve paid
  worker compute in the dashboard, not the current API's free plan. Use this
  image, runtime secrets and a no-overlap deployment strategy. See
  [worker behavior](https://render.com/docs/background-workers),
  [service types](https://render.com/docs/service-types),
  [available free service types](https://render.com/docs/free), and
  [current pricing](https://render.com/pricing).
- **Render hourly cron:** configure this image with command
  `python -m scripts.market_worker --once`, e.g. `0 * * * *` UTC. The scheduler
  guarantees at most one active run of that job, cannot mount a persistent disk,
  and limits a run to 12 hours. Billing is per active second with a **$1 minimum
  monthly charge per cron service**, not a flat $1 guarantee. Dedicated session
  injection remains required each run. See
  [cron semantics and billing](https://render.com/docs/cronjobs). Use only when
  external cooldown handling is acceptable; the always-on loop retains its
  in-process FloodWait delay more naturally.

Do not use browser tabs, a frontend timer, public keep-alive traffic or a sleeping
free API process as the collector scheduler. The checked Render docs describe
SIGTERM and a default 30-second shutdown window; this worker targets cleanup
within that window. Workers have no platform HTTP health-check path: use logs
and persisted data freshness, not a fake listening HTTP server. See
[deploy shutdown behavior](https://render.com/docs/deploys#graceful-shutdown) and
[health-check service scope](https://render.com/docs/health-checks).

## Release And Operations Checklist

1. Obtain explicit separate-account approval; keep this package disabled until then.
2. Review account/session secret handling and provision dedicated credentials
   separately. Do not convert or upload the personal session already on this PC.
3. Ensure backend market migrations, ingest key, catalog version and deployment
   mode/admin configuration are supplied by the application owner. This worker
   never runs schema migrations or enables future financial integrations.
4. Select a cost-approved host and no-overlap scheduling/restart policy. Do not
   run desktop and cloud collectors simultaneously for the same account.
5. Validate configuration, then authorize one `--once` run. Check the public
   `/api/market/prices` capture timestamp advanced, and spot-check a real trait
   combination through `/api/market/valuation` before enabling a schedule.
6. Alert on worker exit 2, repeated cycle failures, server snapshots older than
   two expected intervals, and the feed's `validUntil` expiry. A running process
   or successful health GET alone does not mean ingestion succeeded.
7. Test SIGTERM and restart with a test account. Confirm the original local
   credentials/session files remain unchanged. Use `--check-config` for validation,
   not a live collection merely to check that the process starts.
8. On compromise or retirement, stop all schedulers, revoke the dedicated Telegram
   authorization in Telegram, rotate the ingest key on both ends, and remove
   cloud secrets. Never print session strings or credentials to diagnose failure.

Verification in this task uses synthetic session bytes, fake Telethon clients,
mock upload functions and temporary SQLite/spool files only. No container was
built or deployed, and no real dedicated/personal account was connected.
