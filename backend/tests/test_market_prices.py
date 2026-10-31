"""Reference listing metadata stays separate from DEMO financial valuation."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from app import catalog, market_prices
from app.config import Settings
from app.main import create_app
from app.pricing import SamplePriceProvider
from test_auth import BOT_TOKEN, bearer, login


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setattr('app.config.load_dotenv', lambda *args, **kwargs: None)
    return Settings(bot_token=BOT_TOKEN,
                    database_url=f'sqlite:///{(tmp_path / "market.sqlite").as_posix()}',
                    allowed_origins=())


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    now = int(time.time())
    path = tmp_path / 'market-prices.json'
    monkeypatch.setattr(market_prices, 'MARKET_PRICES_PATH', path)
    imported = tmp_path / 'catalog.json'
    monkeypatch.setattr(catalog, 'TELEGRAM_CATALOG_PATH', imported)
    imported.write_text(json.dumps({'schema': 1, 'collections': [
        {'telegramId': '9000000000000000001', 'catalogId': 100000,
         'title': 'Reference preview', 'image': ''}], 'halloweenCatalogIds': [100000]}), encoding='utf-8')
    data = {'schema': 1, 'source': 'telegram-resale', 'kind': 'lowest_observed_listing',
            'capturedAt': now, 'validUntil': now + 86400, 'complete': True,
            'collections': [{'telegramId': '9000000000000000001', 'catalogId': 100000,
                             'checkedAt': now, 'status': 'available', 'floorNano': '12345678901234',
                             'sampleCount': 2, 'hasMore': True, 'inspectedCount': 5}]}
    return path, data, now


def write(snapshot):
    path, data, _ = snapshot
    path.write_text(json.dumps(data), encoding='utf-8')


def test_exact_metadata_and_unchanged_samples(settings, snapshot):
    baseline = catalog.load_catalog()
    write(snapshot)
    loaded = catalog.load_catalog()
    assert loaded.cards[:20] == baseline.cards[:20]
    card = loaded.cards[-1]
    assert card['marketPrice'] == {
        'floorNano': '12345678901234', 'checkedAt': snapshot[2],
        'validUntil': snapshot[2] + 86400, 'source': 'telegram-resale',
        'kind': 'lowest_observed_listing', 'sampleCount': 2, 'hasMore': True}
    assert card['price'] == '0.000' and card['priceSource'] == 'unpriced'
    assert card['tradeSupported'] is False and card['pledgeSupported'] is False
    assert SamplePriceProvider(loaded.cards).version == SamplePriceProvider(baseline.cards).version
    with pytest.raises(KeyError):
        SamplePriceProvider(loaded.cards).price(100000)


@pytest.mark.parametrize('floor', ['1', '100000000000000'])
def test_integer_boundaries(settings, snapshot, floor):
    snapshot[1]['collections'][0]['floorNano'] = floor
    write(snapshot)
    assert catalog.load_catalog().cards[-1]['marketPrice']['floorNano'] == floor


@pytest.mark.parametrize('change', [
    {'floorNano': '0'}, {'floorNano': '-1'}, {'floorNano': '1.5'},
    {'floorNano': '1e9'}, {'floorNano': '01'}, {'floorNano': 123},
    {'floorNano': True}, {'floorNano': None}, {'floorNano': '100000000000001'},
    {'checkedAt': True}, {'checkedAt': 0}, {'sampleCount': True},
    {'sampleCount': 0}, {'sampleCount': -1}, {'hasMore': 1},
    {'catalogId': True}, {'catalogId': 20}, {'telegramId': 123},
    {'status': 'stars'}, {'inspectedCount': 1},
])
def test_invalid_entry_is_fail_soft(settings, snapshot, change):
    snapshot[1]['collections'][0].update(change)
    write(snapshot)
    assert 'marketPrice' not in catalog.load_catalog().cards[-1]


@pytest.mark.parametrize('change', [
    {'schema': True}, {'schema': 2}, {'source': 'stars'}, {'kind': 'valuation'},
    {'complete': 1}, {'collections': {}}, {'capturedAt': True}, {'validUntil': 0},
])
def test_invalid_envelope_is_fail_soft(settings, snapshot, change):
    snapshot[1].update(change)
    write(snapshot)
    assert 'marketPrice' not in catalog.load_catalog().cards[-1]


@pytest.mark.parametrize('mutation', ['future_capture', 'future_check', 'long_ttl', 'old_check', 'expired', 'partial'])
def test_time_and_partial_semantics(settings, snapshot, mutation):
    _, data, now = snapshot
    if mutation == 'future_capture':
        data.update(capturedAt=now + 61, validUntil=now + 86400)
    elif mutation == 'future_check':
        data['collections'][0]['checkedAt'] = now + 61
    elif mutation == 'long_ttl':
        data['validUntil'] += 1
    elif mutation == 'old_check':
        data['collections'][0]['checkedAt'] -= 1
    elif mutation == 'expired':
        data.update(capturedAt=now - 86401, validUntil=now - 1)
        data['collections'][0]['checkedAt'] = now - 86401
    else:
        data['complete'] = False
    write(snapshot)
    attached = catalog.load_catalog().cards[-1].get('marketPrice')
    assert bool(attached) is (mutation in ('expired', 'partial'))


@pytest.mark.parametrize('status', ['no_ton_listings', 'not_collectible', 'error'])
def test_stars_are_never_converted(settings, snapshot, status):
    entry = snapshot[1]['collections'][0]
    entry.update(status=status, floorNano=None, sampleCount=0, stars='999999999')
    write(snapshot)
    assert 'marketPrice' not in catalog.load_catalog().cards[-1]


def test_unknown_fields_not_exposed(settings, snapshot):
    snapshot[1]['collections'][0].update(stars='999999', access_hash='PRIVATE', price='500', tradeSupported=True)
    write(snapshot)
    card = catalog.load_catalog().cards[-1]
    assert 'stars' not in card['marketPrice'] and 'access_hash' not in card['marketPrice']
    assert card['price'] == '0.000' and card['tradeSupported'] is False


@pytest.mark.parametrize('change', [{'catalogId': 100001}, {'telegramId': '9000000000000000002'}])
def test_identity_pair_must_match(settings, snapshot, change):
    snapshot[1]['collections'][0].update(change)
    write(snapshot)
    assert 'marketPrice' not in catalog.load_catalog().cards[-1]


def test_duplicate_or_malformed_files_are_optional(settings, snapshot):
    path, data, _ = snapshot
    for content in ('{', '[]', 'null', '\ufffd'):
        path.write_text(content, encoding='utf-8')
        assert 'marketPrice' not in catalog.load_catalog().cards[-1]
    path.write_bytes(b'\xff')
    assert 'marketPrice' not in catalog.load_catalog().cards[-1]
    data['collections'].append(dict(data['collections'][0]))
    write(snapshot)
    assert 'marketPrice' not in catalog.load_catalog().cards[-1]
    path.unlink()
    assert 'marketPrice' not in catalog.load_catalog().cards[-1]


def test_market_metadata_cannot_enable_financial_operations(settings, snapshot):
    write(snapshot)
    manually_set = dict(catalog.load_catalog().cards[-1], marketPrice={
        'floorNano': str(100000000000000), 'source': 'manual'})
    with pytest.raises(KeyError):
        SamplePriceProvider([manually_set]).price(100000)
    app = create_app(settings)
    with TestClient(app) as client:
        client.headers.update(bearer(login(client)['access_token']))
        before = client.get('/api/inventory').json()
        preview = next(g for g in before['inventory'] if g['catalogId'] == 100000)
        assert preview['marketPrice']['floorNano'] == '12345678901234'
        offered = before['inventory'][0]['id']
        for body in ({'offered_ids': [preview['id']], 'received_ids': [2]},
                     {'offered_ids': [offered], 'received_ids': [100000]}):
            assert client.post('/api/trades/quote', json=body).status_code == 409
        for endpoint, body in (('/api/loans/create', {'gift_id': preview['id'], 'weeks': 1}),
                               ('/api/inventory/demo-pledge', {'id': preview['id']})):
            assert client.post(endpoint, json=body, headers={'Idempotency-Key': 'reference-only'}).status_code == 409
        assert client.get('/api/inventory').json() == before
