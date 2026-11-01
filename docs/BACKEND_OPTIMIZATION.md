# Backend Optimization Review

## Two Passes

The optimization worker and independent critic reviewed read-only backend paths.
No financial settlement, loan terms, authentication policy, template prices,
database schema or public response fields were changed.

| Path | Before | After | Evidence |
| --- | --- | --- | --- |
| Admin overview | 9 SELECT statements including 2 authorization queries | Pass 1: 4; pass 2: 3, of which 1 is the entire metrics snapshot | `test_admin_optimization.py` counts executed SQL and checks exact totals |
| Scoped catalog choices | Scanned every attribute membership | Visits only attributes belonging to selected collections | Synthetic 100 collections x 10 models: 1,000 membership lookups become 10 for one collection, identical sorted/paginated output |
| Market snapshot refresh | DB connection retained during JSON decoding/validation | Connection returned before CPU validation; locked single-flight publication retained | Connection-lifetime, metadata/payload query-count and invalidation race tests |
| Collection valuation | Scanned up to 45,300 listings per request | Immutable per-collection bucket, built once per loaded version; at most 300 candidates | Synthetic maximum-size snapshot equivalence and iteration counters |

These are operation-count improvements, not claims about production latency or
maximum user capacity. Admin queries remain aggregates rather than cached data;
permission revocation and expired sessions are checked for every request.

## Correctness Boundaries

- Admin joins only aggregate subqueries, never raw loans/trades/wallet facts.
  Empty wallet tables still return counts. Amounts remain decimal strings;
  tests include totals above 2^53 and negative treasury balances. A separate
  read-only PostgreSQL transaction compared the new statement with independent
  counts and grouped sums on an isolated database.
- The market cache still holds its refresh lock during validation. This avoids
  losing an ingestion invalidation. Readers may wait during version refresh,
  but no pooled DB connection is held for that CPU work.
- Warm cache reads issue zero SQL; an unchanged timed refresh issues one small
  version query; a changed refresh issues version plus payload queries.
- The collection index costs additional O(N) bounded memory per snapshot. It
  contains only validated public fields, has no per-user/search-key growth,
  and is replaced atomically with the corresponding snapshot. In-flight readers
  may briefly retain an old immutable bucket.
- Valuations preserve the exact matching minimum, count, oldest matching check
  timestamp and combined filters. Age and expiration are recomputed at request
  time; an empty match remains unknown, never a fabricated zero price.
- Existing capped admin pagination semantics were not changed. No full-table
  count was added to paginated resources.

## Regression Commands

```sh
python -m pytest backend/tests/test_admin.py backend/tests/test_admin_optimization.py backend/tests/test_operations.py backend/tests/test_showcase.py -q
python -m pytest backend/tests/test_catalog_index.py backend/tests/test_market_storage.py backend/tests/test_market_valuation.py backend/tests/test_market_optimization.py -q
```
