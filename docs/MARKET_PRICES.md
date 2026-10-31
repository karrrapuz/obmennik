# Рыночные ориентиры Telegram

Источник: payments.getResaleStarGifts, только явные StarsTonAmount.amount
в nanoTON. Цена Stars не конвертируется в TON. Источник не обращается к
сообщениям, контактам, покупкам или переводам. Личная сессия остаётся локально.

```powershell
backend/.venv/Scripts/python.exe backend/scripts/telegram_prices.py --probe
backend/.venv/Scripts/python.exe backend/scripts/telegram_prices.py
```

Каждая коллекция с улучшенными моделями проверяется отдельно. По умолчанию
читаются две страницы по 100 предложений с sort_by_price. Параметр --pages
разрешает от одной до трёх страниц. Паузы и FloodWait соблюдаются; долгий
FloodWait останавливает импорт с сохранением неполного снимка в локальный
backend/.local/telegram/prices-progress.json. Публичный и серверный снимки
заменяются только после полного успешного прохода; ошибка не уничтожает
предыдущие цены. Повторный
запуск заново собирает текущие наблюдения, а не выдаёт старые за новые.

floorNano — минимальная найденная TON-цена в проверенных предложениях,
а не гарантированный минимум всего рынка, цена завершённой продажи или
точная оценка выбранной модели, фона и символа. kind всегда равен
lowest_observed_listing. hasMore отмечает оставшиеся страницы. У каждого
наблюдения есть checkedAt; общий validUntil ограничен 24 часами. Устаревшие
данные помечаются в интерфейсе и не используются как актуальная котировка.
Нет предложений в TON — нет цены: null, а не ноль или курс Stars.

Снимок сохраняется идентично в backend/data/market-prices.json и
public/gifts/telegram/prices.json. В нём только ID коллекций, суммы и
метаданные проверки. Владельцы предложений, access_hash, file_reference и
пользовательская сессия не экспортируются. После обновления снимок нужно
проверить, пересобрать и опубликовать вместе с приложением.

Обновление пока выполняется локальной командой, не скрытым постоянным
заданием на аккаунте пользователя. Для автоматического источника в
production нужен отдельный согласованный аккаунт/провайдер и расписание.

Эти цены справочные. Они не меняют цену 20 старых демонстрационных обменных
образцов и не открывают обмен или займ для импортированных коллекций.
Импортированная коллекция не является конкретным хранимым подарком:
для финансовой оценки нужны подтверждённое владение, реальные атрибуты,
ликвидность, комиссии и отдельная политика котировок/залогов.

Документация: [метод перепродажи Telegram](https://core.telegram.org/method/payments.getResaleStarGifts).

---

# Public Market Observations

## Completed

The existing schema 1 collection feed remains unchanged. The read-only Telethon
collector optionally writes a separate `backend/data/market-listings.json` with
`--listings`, only after a complete successful non-probe collection run. Failed
refreshes preserve the previous listing snapshot. No seller, owner, session,
access hash or private fields are exported.

Each listing contains `telegramId`, `catalogId`, public `listingId`, exact positive
TON `priceNano` string and `checkedAt` Unix seconds. Actual Telethon model/pattern
document IDs and backdrop IDs are mapped to existing canonical catalog values
(`modelId`, `symbolId`, `backdropId`) only when catalog membership is verified.
Absent/ambiguous traits are omitted; names and rarity never manufacture identities
or premiums. Stars are not converted. Duplicate listing IDs count once. In
`--listings` mode, distinct listing counts and observed minimum prices must
exactly match the legacy collection feed. Duplicate-page samples, multiple TON
amounts per gift or missing identities that break this equality make the run
incomplete; neither public artifact is replaced. Collection-only mode preserves
the existing schema 1 collection counting behavior.

The separate schema 1 envelope has `source: telegram-resale`,
`kind: lowest_observed_listing`, `capturedAt`, `validUntil`, `complete: true`,
and `listings`. TTL is at most 24 hours. The loader reads at most 16 MiB and
45,300 listings, validates identities and timestamps, strips unknown fields,
and treats malformed/missing snapshots as unknown.

## Integration

Call `register_market_routes(app, provider, engine=None, ingest_key='')` from
`app.market_valuation`, using the same provider as catalog routes
(`provider.collections` is required). The original two-argument call still works.
Main supplies its engine and `settings.market_ingest_key`; migrations register
`app.market_models`. Migration `0008_market_snapshots` follows `0007_referrals`.
The catalog is indexed at route registration; catalog identity changes require
a restart. Without database data, bounded local artifacts remain the fallback.

Public GET `/api/market/valuation` accepts required `collection_id` and optional
`model_id`, `symbol_id`, `backdrop_id`. These are bounded canonical IDs matching
the catalog API; unknown IDs or traits outside the collection return 422.
All supplied traits must match the **same observed listing**. Missing traits
never match a supplied filter. Without filters, all valid collection listings
are eligible. No match is `unknown`, not a zero-price quote or collection fallback.

The response includes `floorNano`, distinct `sampleCount`, oldest matching
`checkedAt`, `ageSeconds`, `validUntil`, and `status` (`available`, `stale`,
`unknown`). Expired observations remain visible with `stale`; missing snapshots
have no age. This is the lowest asking price in a bounded sample, not a global
floor, completed-sale price, guaranteed valuation, executable offer or liquidity
promise. Trades and pledges remain unsupported. No loan/trade pricing is changed.
Real financial operations remain blocked until verified custody and a separate
approved financial valuation policy exist.

Python helpers: `load_market_listings(index, path=None, now=None)` and
`valuation(index, collection_id, model_id=None, symbol_id=None, backdrop_id=None,
*, path=None, now=None, snapshot=None)`, where `index` is the existing
`CatalogIndex`. A supplied snapshot is already validated by storage.

## Persistent Refresh API

Public GET `/api/market/prices` returns the validated latest schema 1 collection
feed. It prefers the database snapshot, falling back to the bounded local
`backend/data/market-prices.json`. Missing/invalid data returns an incomplete
envelope with an empty `collections` array and null timestamps. Expired stored
data keeps its original timestamps so clients can label it stale, never fresh.

POST `/api/internal/market/snapshots` accepts exactly
`{"prices": <schema1 collection feed>, "listings": <schema1 listing feed>}`
and `Authorization: Bearer <MARKET_INGEST_KEY>`. The configured key must contain
32-512 non-whitespace ASCII characters. Authentication uses constant-time digest
comparison and occurs before any request body is consumed. Missing/invalid
configuration disables ingestion (503); wrong credentials return 401.

Only uncompressed JSON is accepted. Content-Length and streamed bytes are capped
at 16 MiB; excess returns 413. Duplicate JSON keys and invalid numbers are rejected.
Both complete feeds must have identical fresh capture/expiry metadata. All catalog
identity pairs and supplied traits must exist, all collections must be represented,
and every collection's distinct listing count must equal its `sampleCount`.
For each available collection, its listing minimum must equal `floorNano` exactly.
Empty or truncated coverage cannot replace a complete snapshot; a collection
with no TON samples legitimately has no listing observations. Unknown
fields are discarded, never stored. Bad, expired, equal or older captures return
400. One seeded singleton row stores both cleaned feeds in one CAS transaction;
failed validation/transactions and racing older writers cannot replace newer data.
No histories, seller data, sessions or keys enter this table.

Each API instance caches one decoded snapshot. It checks only the small capture
version every 30 seconds and fetches the large feed columns only on version changes.
Successful ingestion invalidates the writer instance immediately; other instances
see it within 30 seconds of their next read. Responses use `Cache-Control: no-store`.
Database failures are not disguised as fresh data. Staleness is calculated at
response time even when the snapshot is cached. No snapshot changes financial prices.

## Requires Local Collection

Main performed an authorized local live collection: 151 collections and 23,911
distinct TON listings, each with actual model, symbol and backdrop IDs. Main's
audit found exact per-collection count agreement with the collection feed.
This worker did not open the personal session or read the ingest-key file.
Future current quotes require an authorized local operator to run from `backend`:

```powershell
.venv/Scripts/python.exe scripts/telegram_prices.py --pages 2 --listings
```

Runtime push configuration is read from the local ignored `backend/.env.market`
using `load_dotenv(..., override=False)`. Existing environment variables take
precedence. `MARKET_API_URL` must be an HTTPS origin without userinfo, path, query
or fragment; `MARKET_INGEST_KEY` is never accepted in command-line arguments.
HTTP, redirects and environment proxy inheritance are disabled. Tests inject a
mock HTTP client rather than enabling insecure HTTP transport. Only the two
validated public JSON feeds are sent, with a 30-second POST network timeout; no
Telethon session, catalog credentials, arbitrary files or dotenv contents are sent.
Before each POST, an unauthenticated streamed GET to the same origin's
`/api/health` wakes a sleeping backend. It has a 90-second network timeout and
90-second overall deadline, must return exactly 200, and sends no ingest key or
snapshot body. A failed, redirected or timed-out warm-up prevents the POST.
Neither health nor upload response bodies are consumed. Redirects and environment
proxies remain disabled for both requests.

From `backend`, opt-in local modes are:

```powershell
# Push the completed public files without opening Telegram at all:
.venv/Scripts/python.exe scripts/telegram_prices.py --push-only

# Collect once, disconnect Telegram, then push; --listings is required:
.venv/Scripts/python.exe scripts/telegram_prices.py --pages 2 --listings --push

# Keep this desktop process running, waiting an hour after each completed attempt:
.venv/Scripts/python.exe scripts/telegram_prices.py --pages 2 --listings --push --watch 3600
```

`--watch` alone defaults to 3600 seconds; allowed intervals are 3600-86400 seconds.
Each collection cycle opens and closes its own local session. Failed collection
cycles do not push older files; failed uploads do not mark a cycle successful.
Both failures wait the full interval before another attempt.
A Telegram FloodWait longer than that interval extends the next delay
to at least the requested wait plus one second. Ctrl+C stops the
process. `--probe` cannot watch/push. `--push-only` cannot watch, probe or collect.
Reusable async helper `scripts.telegram_prices.push_existing()` performs exactly
the push-only flow, with no Telegram connection. Each cycle is bounded; watch
continues only while the explicitly launched local process remains running.

Only the existing public resale request is used, with 100 results per page,
1-3 pages per collection, at most 151 catalog collections and bounded flood-wait
retry. `--probe` never publishes. Starting/stopping the opt-in desktop watcher and
deploying the backend/migration are operator tasks; no OS scheduler or hosted
Telethon process was installed. Collection
ordering can under-sample rare combinations, so missing combinations remain
unknown until actually observed. No generated snapshot is committed by this work.
