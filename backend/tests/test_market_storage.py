"""Authenticated public snapshot ingestion; no real network or secret files."""
import asyncio
import copy
import json
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select

from app.config import Settings
from app.catalog_index import CatalogIndex
from app.market_models import MarketSnapshot
from app.market_storage import SnapshotCache, InvalidSnapshot, save_snapshot, validate_snapshot
from app import market_valuation as market
from scripts import telegram_prices as collector

KEY = 'test-ingest-key-not-a-real-secret-' * 2
HEADERS = {'Authorization': 'Bearer ' + KEY, 'Content-Type': 'application/json'}


@pytest.fixture
def settings(tmp_path):
    return Settings(bot_token='12345:test', database_url=f'sqlite:///{(tmp_path / "snapshots.sqlite").as_posix()}', allowed_origins=())


@pytest.fixture
def context(settings, tmp_path, monkeypatch):
    collection = {'telegramId': '123', 'catalogId': 100000, 'title': 'Public', 'image': '',
                  'attributes': {'models': [{'id': '11', 'name': 'M', 'image': ''}],
                                 'symbols': [{'id': '22', 'name': 'S', 'image': ''}], 'backdrops': []}}
    engine = create_engine(settings.database_url, connect_args={'check_same_thread': False})
    now = int(time.time())
    envelope = {'schema': 1, 'source': 'telegram-resale', 'kind': 'lowest_observed_listing',
                'complete': True, 'capturedAt': now - 10, 'validUntil': now + 86390}
    payload = {'prices': {**envelope, 'collections': [{'telegramId': '123', 'catalogId': 100000,
        'checkedAt': now - 9, 'floorNano': '123', 'sampleCount': 1, 'inspectedCount': 1,
        'status': 'available', 'hasMore': False}]}, 'listings': {**envelope, 'listings': [{
            'telegramId': '123', 'catalogId': 100000, 'listingId': '99', 'priceNano': '123',
            'checkedAt': now - 8, 'modelId': 'tg:model:123:11', 'symbolId': 'tg:symbol:22'}]}}
    monkeypatch.setattr(market, 'MARKET_LISTINGS_PATH', tmp_path / 'absent-listings.json')
    provider = SimpleNamespace(collections=[collection])
    app = FastAPI()
    market.register_market_routes(app, provider, engine, KEY)
    yield SimpleNamespace(engine=engine, app=app, provider=provider, index=CatalogIndex([collection]),
                          payload=payload, now=now, tmp=tmp_path)
    engine.dispose()


def test_persist_restart_public_fresh_and_read_only(context):
    with TestClient(context.app) as client:
        response = client.post('/api/internal/market/snapshots', json=context.payload, headers=HEADERS)
        assert response.status_code == 200
        assert client.get('/api/market/prices').json() == context.payload['prices']
        quote = client.get('/api/market/valuation', params={
            'collection_id': '123', 'model_id': 'tg:model:123:11', 'symbol_id': 'tg:symbol:22'}).json()
        assert quote['floorNano'] == '123' and quote['status'] == 'available'
        assert quote['sampleCount'] == 1 and quote['ageSeconds'] >= 8
        assert not quote['tradeSupported'] and not quote['pledgeSupported'] and not quote['guaranteedValuation']
    context.engine.dispose()
    restarted_engine = create_engine(context.engine.url, connect_args={'check_same_thread': False})
    app = FastAPI()
    market.register_market_routes(app, context.provider, restarted_engine, KEY)
    with TestClient(app) as client:
        assert client.get('/api/market/prices').json() == context.payload['prices']
        assert client.get('/api/market/valuation?collection_id=123').json()['floorNano'] == '123'
    restarted_engine.dispose()


async def request_without_body(app, headers, *, body_chunks=None):
    sent, reads = [], []
    chunks = iter(body_chunks or [])

    async def receive():
        reads.append(True)
        if body_chunks is None:
            raise AssertionError('Unauthorized request read its body')
        return next(chunks)

    async def send(message):
        sent.append(message)

    await app({'type': 'http', 'http_version': '1.1', 'method': 'POST',
               'scheme': 'https', 'path': '/api/internal/market/snapshots',
               'raw_path': b'/api/internal/market/snapshots', 'query_string': b'',
               'root_path': '', 'headers': [(k.lower().encode(), v.encode()) for k, v in headers.items()],
               'server': ('test', 443), 'client': ('127.0.0.1', 1)}, receive, send)
    return next(m['status'] for m in sent if m['type'] == 'http.response.start'), reads


def test_unauthorized_never_reads_body(context):
    for headers in ({}, {'Authorization': 'Bearer wrong'}, {'Authorization': 'Bearer ' + KEY + 'x'}):
        status, reads = asyncio.run(request_without_body(context.app, headers))
        assert status == 401 and reads == []
    app = FastAPI()
    market.register_market_routes(app, context.provider, context.engine, 'short')
    assert asyncio.run(request_without_body(app, {})) == (503, [])


def test_huge_declared_and_streaming_body(context, monkeypatch):
    status, reads = asyncio.run(request_without_body(context.app,
        {**HEADERS, 'Content-Length': str(16 * 1024 * 1024 + 1)}))
    assert status == 413 and reads == []
    monkeypatch.setattr(market, 'MAX_BYTES', 100)
    status, reads = asyncio.run(request_without_body(context.app, HEADERS, body_chunks=[
        {'type': 'http.request', 'body': b'x' * 60, 'more_body': True},
        {'type': 'http.request', 'body': b'x' * 60, 'more_body': False}]))
    assert status == 413 and len(reads) == 2


@pytest.mark.parametrize('mutation', ['wrong_pair', 'unknown_collection', 'wrong_trait', 'stale', 'partial',
    'different_capture', 'negative_ton', 'boolean_schema', 'no_collections', 'duplicate_listing',
    'inconsistent_floor', 'future_capture', 'long_ttl'])
def test_invalid_ingress_no_write(context, mutation):
    payload = context.payload
    if mutation == 'wrong_pair':
        payload['prices']['collections'][0]['catalogId'] += 1
    elif mutation == 'unknown_collection':
        payload['listings']['listings'][0]['telegramId'] = '456'
    elif mutation == 'wrong_trait':
        payload['listings']['listings'][0]['modelId'] = 'tg:model:456:11'
    elif mutation == 'stale':
        for feed in payload.values():
            feed.update(capturedAt=context.now - 86410, validUntil=context.now - 10)
        payload['prices']['collections'][0]['checkedAt'] = context.now - 86409
        payload['listings']['listings'][0]['checkedAt'] = context.now - 86408
    elif mutation == 'partial':
        payload['prices']['complete'] = False
    elif mutation == 'different_capture':
        payload['listings']['capturedAt'] += 1
    elif mutation == 'negative_ton':
        payload['listings']['listings'][0]['priceNano'] = '-1'
    elif mutation == 'boolean_schema':
        payload['prices']['schema'] = True
    elif mutation == 'no_collections':
        payload['prices']['collections'] = []
    elif mutation == 'duplicate_listing':
        payload['listings']['listings'] *= 2
    elif mutation == 'inconsistent_floor':
        payload['listings']['listings'][0]['priceNano'] = '1'
    elif mutation == 'future_capture':
        payload['prices']['capturedAt'] = context.now + 61
    else:
        payload['prices']['validUntil'] += 1
    with TestClient(context.app) as client:
        assert client.post('/api/internal/market/snapshots', json=payload, headers=HEADERS).status_code == 400
    with context.engine.connect() as connection:
        assert connection.scalar(select(MarketSnapshot.captured_at)) == 0


def test_same_old_and_failed_update_preserve_both_feeds(context):
    original = copy.deepcopy(context.payload)
    with TestClient(context.app) as client:
        assert client.post('/api/internal/market/snapshots', json=original, headers=HEADERS).status_code == 200
        for delta in (0, -1):
            changed = copy.deepcopy(original)
            for feed in changed.values():
                feed['capturedAt'] += delta
                feed['validUntil'] += delta
            changed['prices']['collections'][0]['floorNano'] = '1'
            changed['listings']['listings'][0]['priceNano'] = '1'
            validate_snapshot(changed, context.index)
            response = client.post('/api/internal/market/snapshots', json=changed, headers=HEADERS)
            assert response.status_code == 400 and 'newer' in response.json()['detail']
        broken = copy.deepcopy(original)
        for feed in broken.values():
            feed['capturedAt'] += 1
        broken['listings']['listings'][0]['symbolId'] = 'tg:symbol:999'
        assert client.post('/api/internal/market/snapshots', json=broken, headers=HEADERS).status_code == 400
        assert client.get('/api/market/prices').json() == original['prices']
        assert client.get('/api/market/valuation?collection_id=123').json()['floorNano'] == '123'


def test_transaction_failure_rolls_back_snapshot_pair(context):
    snapshot = validate_snapshot(context.payload, context.index)

    def fail_commit(connection):
        raise RuntimeError('simulated storage failure')

    event.listen(context.engine, 'commit', fail_commit)
    try:
        with pytest.raises(RuntimeError):
            save_snapshot(context.engine, snapshot)
    finally:
        event.remove(context.engine, 'commit', fail_commit)
    with context.engine.connect() as connection:
        row = connection.execute(select(MarketSnapshot)).first()
        assert row.captured_at == 0 and row.prices_json is None and row.listings_json is None


def test_cache_reads_large_columns_only_when_version_changes(context):
    save_snapshot(context.engine, validate_snapshot(context.payload, context.index))
    queries = []

    def record(connection, cursor, statement, parameters, context_, executemany):
        queries.append(statement)

    event.listen(context.engine, 'before_cursor_execute', record)
    cache = SnapshotCache(context.engine, context.index)
    first = cache.get()
    for _ in range(20):
        assert cache.get() is first
    cache.invalidate()
    assert cache.get() is first
    assert len(queries) == 3
    assert sum('prices_json' in statement for statement in queries) == 1
    event.remove(context.engine, 'before_cursor_execute', record)


def test_refresh_invalidation_public_and_strips_unknown_fields(context):
    with TestClient(context.app) as client:
        assert client.post('/api/internal/market/snapshots', json=context.payload, headers=HEADERS).status_code == 200
        assert client.get('/api/market/prices').json()['collections'][0]['floorNano'] == '123'
        for feed in context.payload.values():
            feed['capturedAt'] += 1
        context.payload['prices']['collections'][0].update(floorNano='456', owner='PRIVATE', tradeSupported=True)
        context.payload['listings']['listings'][0].update(priceNano='456', owner='PRIVATE', access_hash='PRIVATE')
        assert client.post('/api/internal/market/snapshots', json=context.payload, headers=HEADERS).status_code == 200
        prices = client.get('/api/market/prices').json()
        assert prices['collections'][0]['floorNano'] == '456' and 'PRIVATE' not in json.dumps(prices)
        assert client.get('/api/market/valuation?collection_id=123').json()['floorNano'] == '456'
    with context.engine.connect() as connection:
        assert 'PRIVATE' not in connection.scalar(select(MarketSnapshot.listings_json))


def test_price_file_fallback_and_invalid_file(context, monkeypatch):
    path = context.tmp / 'prices.json'
    monkeypatch.setattr(market.market_prices, 'MARKET_PRICES_PATH', path)
    path.write_text(json.dumps(context.payload['prices']))
    with TestClient(context.app) as client:
        assert client.get('/api/market/prices').json() == context.payload['prices']
        path.write_text('{')
        assert client.get('/api/market/prices').json()['collections'] == []


def test_duplicate_json_keys_and_non_json_rejected(context):
    with TestClient(context.app) as client:
        for raw in ('{"prices":{},"prices":{},"listings":{}}', '{', 'NaN'):
            assert client.post('/api/internal/market/snapshots', content=raw, headers=HEADERS).status_code == 400
        assert client.post('/api/internal/market/snapshots', content='{}', headers={
            **HEADERS, 'Content-Encoding': 'gzip'}).status_code == 415


def test_push_existing_does_not_open_telegram_and_only_sends_public_data(context, monkeypatch):
    path = context.tmp / 'listings.json'
    output = context.tmp / 'prices.json'
    catalog = context.tmp / 'catalog.json'
    path.write_text(json.dumps(context.payload['listings']))
    output.write_text(json.dumps(context.payload['prices']))
    catalog.write_text(json.dumps({'collections': context.provider.collections}))
    monkeypatch.setattr(collector, 'LISTINGS', path)
    monkeypatch.setattr(collector, 'OUTPUT', output)
    monkeypatch.setattr(collector, 'CATALOG', catalog)
    # Never load the user's actual local dotenv in tests.
    dotenv_calls = []
    monkeypatch.setattr('dotenv.load_dotenv', lambda *a, **k: dotenv_calls.append((a, k)))
    monkeypatch.setenv('MARKET_API_URL', 'https://test.invalid')
    monkeypatch.setenv('MARKET_INGEST_KEY', KEY)
    monkeypatch.setattr(collector, 'run', lambda _: pytest.fail('Telegram run was called'))
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == 'GET':
            assert request.url == 'https://test.invalid/api/health'
            assert 'authorization' not in request.headers and request.content == b''
            assert request.extensions['timeout']['read'] == 90
            return httpx.Response(200)
        assert request.url == 'https://test.invalid/api/internal/market/snapshots'
        assert request.method == 'POST' and len(requests) == 2
        assert request.extensions['timeout']['read'] == 30
        assert request.headers['authorization'] == HEADERS['Authorization']
        assert json.loads(request.content) == context.payload
        return httpx.Response(200, json={'stored': True})

    def factory(**kwargs):
        assert kwargs['follow_redirects'] is False and kwargs['trust_env'] is False
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    asyncio.run(collector.push_existing(client_factory=factory))
    assert len(requests) == 2 and dotenv_calls[0][1] == {'override': False}


@pytest.mark.parametrize('url', ['http://example.com', 'http://localhost', 'https://key@example.com',
    'https://example.com?key=x', 'https://example.com#x', 'https://example.com/path'])
def test_push_rejects_unsafe_origin_without_network(monkeypatch, url):
    monkeypatch.setattr('dotenv.load_dotenv', lambda *a, **k: None)
    monkeypatch.setenv('MARKET_API_URL', url)
    monkeypatch.setenv('MARKET_INGEST_KEY', KEY)
    with pytest.raises(ValueError):
        collector.push_configuration()


def test_watch_interval_and_failure_backoff_no_session(monkeypatch):
    calls, delays = [], []

    async def fake_run(args):
        calls.append(args)
        raise RuntimeError('PRIVATE')

    async def sleep(seconds):
        delays.append(seconds)
        raise asyncio.CancelledError()

    monkeypatch.setattr(collector, 'run', fake_run)
    monkeypatch.setattr(collector.asyncio, 'sleep', sleep)
    args = SimpleNamespace(watch=3600, push=False, push_only=False, probe=False, listings=True)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(collector.run_cycles(args))
    assert len(calls) == 1 and delays == [3600]
    args.watch = 3599
    with pytest.raises(ValueError):
        asyncio.run(collector.run_cycles(args))
    assert len(calls) == 1


def test_push_only_cli_branch_never_calls_telegram(monkeypatch):
    calls = []

    async def push_existing():
        calls.append('push')

    monkeypatch.setattr(collector, 'push_existing', push_existing)
    monkeypatch.setattr(collector, 'run', lambda _: pytest.fail('Telegram run was called'))
    args = SimpleNamespace(push_only=True, watch=None, push=False, probe=False, listings=False)
    assert asyncio.run(collector.run_cycles(args)) == 0
    assert calls == ['push']


def test_push_requires_listings_and_incomplete_run_never_pushes(monkeypatch):
    monkeypatch.setattr(collector, 'push_configuration', lambda: ('https://test.invalid', KEY))
    monkeypatch.setattr(collector, 'push_snapshot', lambda *a: pytest.fail('Incomplete snapshot pushed'))

    async def incomplete(args):
        return {'complete': False}

    monkeypatch.setattr(collector, 'run', incomplete)
    args = SimpleNamespace(push_only=False, watch=None, push=True, probe=False, listings=False)
    with pytest.raises(ValueError):
        asyncio.run(collector.run_cycles(args))
    args.listings = True
    assert asyncio.run(collector.run_cycles(args)) == 2


def test_expired_persisted_snapshot_is_not_fresh(context):
    for feed in context.payload.values():
        feed.update(capturedAt=context.now - 86410, validUntil=context.now - 10)
    context.payload['prices']['collections'][0]['checkedAt'] = context.now - 86409
    context.payload['listings']['listings'][0]['checkedAt'] = context.now - 86408
    save_snapshot(context.engine, validate_snapshot(context.payload, context.index, fresh=False))
    with TestClient(context.app) as client:
        assert client.get('/api/market/valuation?collection_id=123').json()['status'] == 'stale'
        assert client.get('/api/market/prices').json()['validUntil'] < context.now


def test_watch_respects_long_telegram_flood_wait(monkeypatch):
    from telethon.errors import FloodWaitError
    delays = []

    async def flood(args):
        raise FloodWaitError(request=None, capture=7200)

    async def sleep(seconds):
        delays.append(seconds)
        raise asyncio.CancelledError()

    monkeypatch.setattr(collector, 'run', flood)
    monkeypatch.setattr(collector.asyncio, 'sleep', sleep)
    args = SimpleNamespace(watch=3600, push=False, push_only=False, probe=False, listings=True)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(collector.run_cycles(args))
    assert delays == [7201]


@pytest.mark.parametrize('mutation', ['empty', 'truncated', 'minimum_mismatch'])
def test_incomplete_listing_coverage_cannot_replace_snapshot(context, mutation):
    original = copy.deepcopy(context.payload)
    with TestClient(context.app) as client:
        assert client.post('/api/internal/market/snapshots', json=original, headers=HEADERS).status_code == 200
        changed = copy.deepcopy(original)
        for feed in changed.values():
            feed['capturedAt'] += 1
        if mutation == 'empty':
            changed['listings']['listings'] = []
        elif mutation == 'truncated':
            changed['prices']['collections'][0].update(sampleCount=2, inspectedCount=2)
        else:
            changed['listings']['listings'][0]['priceNano'] = '456'
        with pytest.raises(InvalidSnapshot):
            validate_snapshot(changed, context.index)
        assert client.post('/api/internal/market/snapshots', json=changed, headers=HEADERS).status_code == 400
        assert client.get('/api/market/prices').json() == original['prices']
        quote = client.get('/api/market/valuation?collection_id=123').json()
        assert quote['sampleCount'] == 1 and quote['floorNano'] == '123'
    with context.engine.connect() as connection:
        row = connection.execute(select(MarketSnapshot)).first()
        assert row.captured_at == original['prices']['capturedAt']
        assert json.loads(row.listings_json) == original['listings']


def test_zero_ton_samples_allow_empty_coverage(context):
    context.payload['prices']['collections'][0].update(status='no_ton_listings', sampleCount=0, floorNano=None)
    context.payload['listings']['listings'] = []
    assert validate_snapshot(context.payload, context.index) == context.payload


@pytest.mark.parametrize('status', [301, 302, 303, 307, 308, 500])
def test_push_rejects_redirect_and_failure_without_following(context, monkeypatch, status):
    catalog = context.tmp / 'catalog.json'
    listings = context.tmp / 'listings.json'
    catalog.write_text(json.dumps({'collections': context.provider.collections}))
    listings.write_text(json.dumps(context.payload['listings']))
    monkeypatch.setattr(collector, 'CATALOG', catalog)
    monkeypatch.setattr(collector, 'LISTINGS', listings)
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == 'GET':
            assert request.url.path == '/api/health' and 'authorization' not in request.headers
            return httpx.Response(200)
        return httpx.Response(status, headers={'Location': 'https://other.invalid/secret-target'})

    def factory(**kwargs):
        assert kwargs['follow_redirects'] is False
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    with pytest.raises(RuntimeError, match='Market snapshot upload rejected'):
        asyncio.run(collector.push_snapshot(context.payload['prices'],
            ('https://test.invalid/api/internal/market/snapshots', KEY), client_factory=factory))
    assert len(requests) == 2 and all(request.url.host == 'test.invalid' for request in requests)


def test_cached_snapshot_expires_without_database_reload(context, monkeypatch):
    for feed in context.payload.values():
        feed['validUntil'] = context.now + 10
    clock = [context.now]
    monkeypatch.setattr(market, 'time', SimpleNamespace(time=lambda: clock[0]))
    queries = []

    def record(connection, cursor, statement, parameters, context_, executemany):
        queries.append(statement)

    with TestClient(context.app) as client:
        assert client.post('/api/internal/market/snapshots', json=context.payload, headers=HEADERS).status_code == 200
        event.listen(context.engine, 'before_cursor_execute', record)
        try:
            first = client.get('/api/market/valuation?collection_id=123').json()
            assert first['status'] == 'available'
            assert len(queries) == 2
            clock[0] = context.now + 11
            expired = client.get('/api/market/valuation?collection_id=123').json()
            assert expired['status'] == 'stale'
            assert expired['ageSeconds'] == first['ageSeconds'] + 11
            assert expired['floorNano'] == first['floorNano']
            assert client.get('/api/market/prices').json()['validUntil'] < clock[0]
            assert len(queries) == 2
        finally:
            event.remove(context.engine, 'before_cursor_execute', record)


@pytest.mark.parametrize('failure', [301, 302, 303, 307, 308, 503, 'timeout'])
def test_failed_warmup_never_sends_ingest_key_or_snapshot(context, monkeypatch, failure):
    catalog = context.tmp / 'catalog.json'
    listings = context.tmp / 'listings.json'
    catalog.write_text(json.dumps({'collections': context.provider.collections}))
    listings.write_text(json.dumps(context.payload['listings']))
    monkeypatch.setattr(collector, 'CATALOG', catalog)
    monkeypatch.setattr(collector, 'LISTINGS', listings)
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == 'GET' and request.url == 'https://test.invalid/api/health'
        assert 'authorization' not in request.headers and request.content == b''
        assert request.extensions['timeout'] == {'connect': 90, 'read': 90, 'write': 90, 'pool': 90}
        if failure == 'timeout':
            raise httpx.ReadTimeout('Simulated cold-start timeout', request=request)
        return httpx.Response(failure, headers={'Location': 'https://other.invalid/health'})

    def factory(**kwargs):
        assert kwargs == {'timeout': 30, 'follow_redirects': False, 'trust_env': False}
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    expected = httpx.ReadTimeout if failure == 'timeout' else RuntimeError
    with pytest.raises(expected):
        asyncio.run(collector.push_snapshot(context.payload['prices'],
            ('https://test.invalid/api/internal/market/snapshots', KEY), client_factory=factory))
    assert len(requests) == 1


def test_health_and_upload_response_bodies_are_closed_without_reading(context, monkeypatch):
    catalog = context.tmp / 'catalog.json'
    listings = context.tmp / 'listings.json'
    catalog.write_text(json.dumps({'collections': context.provider.collections}))
    listings.write_text(json.dumps(context.payload['listings']))
    monkeypatch.setattr(collector, 'CATALOG', catalog)
    monkeypatch.setattr(collector, 'LISTINGS', listings)
    streams, requests = [], []

    class UnreadBody(httpx.AsyncByteStream):
        closed = False

        def __aiter__(self):
            raise AssertionError('Response body must not be read')

        async def aclose(self):
            self.closed = True

    def handler(request):
        requests.append(request)
        if request.method == 'GET':
            assert 'authorization' not in request.headers
        else:
            assert request.headers['authorization'] == HEADERS['Authorization']
        stream = UnreadBody()
        streams.append(stream)
        return httpx.Response(200, stream=stream)

    def factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    asyncio.run(collector.push_snapshot(context.payload['prices'],
        ('https://test.invalid/api/internal/market/snapshots', KEY), client_factory=factory))
    assert [request.method for request in requests] == ['GET', 'POST']
    assert len(streams) == 2 and all(stream.closed for stream in streams)
