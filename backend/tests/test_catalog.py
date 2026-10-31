"""Local Telegram previews and once-only unpriced seasonal DEMO grants."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import catalog
from app.config import Settings
from app.gift_provider import create_gift_provider
from app.grant_models import DemoSeasonalGrant
from app.inventory_models import InventoryGift, InventoryInit
from app.main import create_app
from app.models import User
from app.pricing import SamplePriceProvider
from app.gift_presentation import decorative_presentation
from test_auth import BOT_TOKEN, USER, bearer, login


@pytest.fixture
def settings(tmp_path):
    return Settings(bot_token=BOT_TOKEN,
                    database_url=f"sqlite:///{(tmp_path / 'catalog.sqlite3').as_posix()}",
                    allowed_origins=())


@pytest.fixture
def manifest(tmp_path, monkeypatch):
    path = tmp_path / 'catalog-telegram.json'
    monkeypatch.setattr(catalog, 'TELEGRAM_CATALOG_PATH', path)
    data = {
        'schema': 1, 'importedAt': '2026-10-31T00:00:00Z',
        'collections': [{
            'telegramId': str(9000000000000000000 + index), 'catalogId': 100000 + index,
            'title': f'Imported Collection {index}',
            'image': f'/gifts/telegram/{100000 + index}/preview.webp',
            'stars': '500', 'firstSaleAt': None, 'upgradeAvailable': True,
            'attributes': {'models': [{'name': 'Halloween', 'rarity': 10}],
                           'symbols': [], 'backdrops': []},
        } for index in range(151)],
        'halloweenCatalogIds': [100000, 100001], 'stats': {'collections': 151},
    }
    path.write_text(json.dumps(data), encoding='utf-8')
    return path, data


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def authenticate(client, user=USER):
    client.headers.update(bearer(login(client, user)['access_token']))


def inventory(client):
    return ok(client.get('/api/inventory'))


def state(client):
    inventory(client)
    wallet = ok(client.get('/api/wallet'))
    return inventory(client), wallet


def test_all_previews_append_without_changing_twenty_samples(settings, manifest):
    samples = json.loads(catalog.SAMPLE_CATALOG_PATH.read_text(encoding='utf-8'))
    loaded = catalog.load_catalog()
    assert len(samples) == 20
    assert loaded.cards[:20] == tuple(samples)
    assert len(loaded.cards) == 171
    assert len({gift['id'] for gift in loaded.cards}) == 171
    assert loaded.halloween_catalog_ids == (100000, 100001)
    for preview, collection in zip(loaded.cards[20:], manifest[1]['collections']):
        assert preview == {
            'id': collection['catalogId'], 'name': collection['title'], 'model': '\u2014',
            'price': '0.000', 'image': collection['image'], 'collectionId': collection['telegramId'],
            'telegramCatalog': True, 'tradeSupported': False,
            'pledgeSupported': False, 'priceSource': 'unpriced',
            'presentation': decorative_presentation(collection['telegramId']),
        }
    provider = create_gift_provider('demo')
    assert provider.initial_gifts() == tuple((gift['id'], index < 3) for index, gift in enumerate(samples[:5]))
    assert provider.seasonal_gifts() == (100000, 100001)
    assert create_gift_provider('disabled').seasonal_gifts() == ()


def test_absent_import_preserves_sample_only(settings):
    loaded = catalog.load_catalog()
    assert len(loaded.cards) == 20
    assert loaded.halloween_catalog_ids == ()


def test_sample_prices_skip_all_unpriced_collections(settings, manifest):
    baseline = SamplePriceProvider(catalog.load_catalog(telegram_path=manifest[0].parent / 'absent.json').cards)
    prices = SamplePriceProvider(catalog.load_catalog().cards)
    assert prices.version == baseline.version
    for gift in catalog.load_catalog().cards[:20]:
        assert prices.price(gift['id']) == baseline.price(gift['id'])
    for collection in manifest[1]['collections']:
        with pytest.raises(KeyError):
            prices.price(collection['catalogId'])


@pytest.mark.parametrize('change', [
    {'schema': True}, {'schema': 2}, {'halloweenCatalogIds': [100000, 100000]},
    {'halloweenCatalogIds': [1]}, {'halloweenCatalogIds': [True]},
])
def test_invalid_manifest_rejected(settings, manifest, change):
    path, data = manifest
    path.write_text(json.dumps({**data, **change}), encoding='utf-8')
    with pytest.raises(ValueError):
        catalog.load_catalog()


@pytest.mark.parametrize('change', [
    {'catalogId': 1}, {'catalogId': True}, {'catalogId': 100001},
    {'telegramId': 123}, {'telegramId': 'not-an-id'}, {'telegramId': '9000000000000000001'},
    {'image': 'https://remote.example/gift.png'}, {'image': '/gifts/telegram/../secret.png'},
    {'title': ''},
])
def test_invalid_preview_identity_or_asset_rejected(settings, manifest, change):
    path, data = manifest
    data['collections'][0].update(change)
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError):
        catalog.load_catalog()


def test_seasonal_grants_once_per_actor_restart_and_withdrawal(settings, manifest):
    with TestClient(create_app(settings)) as client:
        authenticate(client)
        initial = inventory(client)
        assert [g['catalogId'] for g in initial['inventory']] == [1, 2, 3, 4, 5, 100000, 100001]
        seasonal = initial['inventory'][-2:]
        assert all(g['pledgeSupported'] is False and g['blockTradeGift'] is True for g in seasonal)
        assert inventory(client) == initial
        auth = client.headers['Authorization']
        removed = ok(client.post('/api/inventory/demo-withdraw',
            json={'ids': [g['id'] for g in seasonal]}, headers={'Idempotency-Key': 'withdraw-seasonal'}))
        assert inventory(client) == removed
        with Session(client.app.state.engine) as db:
            grants = db.scalars(select(DemoSeasonalGrant).where(DemoSeasonalGrant.user_id == USER['id'])).all()
            assert {grant.catalog_id for grant in grants} == {100000, 100001}
        authenticate(client, {**USER, 'id': USER['id'] + 1})
        assert [g['catalogId'] for g in inventory(client)['inventory']][-2:] == [100000, 100001]
    with TestClient(create_app(settings)) as reopened:
        reopened.headers['Authorization'] = auth
        assert inventory(reopened) == removed


def test_existing_empty_user_gets_only_new_grants_once(settings, manifest, monkeypatch):
    monkeypatch.setattr(catalog, 'TELEGRAM_CATALOG_PATH', manifest[0].parent / 'absent.json')
    with TestClient(create_app(settings)) as client:
        authenticate(client)
        original = inventory(client)
        ok(client.post('/api/inventory/demo-withdraw', json={'ids': [g['id'] for g in original['inventory']]},
                       headers={'Idempotency-Key': 'empty'}))
        auth = client.headers['Authorization']
    monkeypatch.setattr(catalog, 'TELEGRAM_CATALOG_PATH', manifest[0])
    with TestClient(create_app(settings)) as client:
        client.headers['Authorization'] = auth
        granted = inventory(client)
        assert [g['catalogId'] for g in granted['inventory']] == [100000, 100001]
        assert inventory(client) == granted
        path, data = manifest
        data['halloweenCatalogIds'].append(100002)
        path.write_text(json.dumps(data), encoding='utf-8')
    with TestClient(create_app(settings)) as client:
        client.headers['Authorization'] = auth
        extended = inventory(client)
        assert [g['catalogId'] for g in extended['inventory']] == [100000, 100001, 100002]
        assert extended['inventory'][:2] == granted['inventory']
        assert extended['revision'] > granted['revision']
        assert inventory(client) == extended


def test_disabled_mode_never_seeds_grants_or_consumes_marker(settings, manifest):
    with TestClient(create_app(replace(settings, gift_provider_mode='disabled'))) as client:
        authenticate(client)
        before = inventory(client)
        assert before['inventory'] == before['pledged'] == []
        assert len(before['catalog']) == 171
        assert inventory(client) == before
        auth = client.headers['Authorization']
        with Session(client.app.state.engine) as db:
            assert db.get(InventoryInit, USER['id']) is None
            assert db.scalars(select(DemoSeasonalGrant)).all() == []
    with TestClient(create_app(settings)) as client:
        client.headers['Authorization'] = auth
        assert len(inventory(client)['inventory']) == 7


def test_disabled_existing_user_does_not_grant_new_seasonal_gifts(settings, manifest, monkeypatch):
    monkeypatch.setattr(catalog, 'TELEGRAM_CATALOG_PATH', manifest[0].parent / 'absent.json')
    with TestClient(create_app(settings)) as client:
        authenticate(client)
        before = inventory(client)
        auth = client.headers['Authorization']
    monkeypatch.setattr(catalog, 'TELEGRAM_CATALOG_PATH', manifest[0])
    with TestClient(create_app(replace(settings, gift_provider_mode='disabled'))) as client:
        client.headers['Authorization'] = auth
        disabled = inventory(client)
        assert disabled['revision'] == before['revision']
        assert disabled['inventory'] == before['inventory']
        with Session(client.app.state.engine) as db:
            assert db.scalars(select(DemoSeasonalGrant)).all() == []


def test_unpriced_previews_cannot_trade_or_mint_loan_credit(settings, manifest, monkeypatch):
    with TestClient(create_app(settings)) as client:
        authenticate(client)
        before = state(client)
        sample, seasonal = before[0]['inventory'][0], before[0]['inventory'][-1]

        def unexpected_price(catalog_id):
            raise AssertionError('Unpriced preview reached the price provider')

        monkeypatch.setattr(client.app.state.price_provider, 'price', unexpected_price)
        for offered, received in (([seasonal['id']], [2]), ([sample['id']], [100000]),
                                  ([sample['id'], seasonal['id']], [2]),
                                  ([sample['id']], [2, 100000])):
            assert client.post('/api/trades/quote', json={
                'offered_ids': offered, 'received_ids': received}).status_code == 409
            assert state(client) == before
        for endpoint, body in (('/api/loans/create', {'gift_id': seasonal['id'], 'weeks': 1}),
                               ('/api/inventory/demo-pledge', {'id': seasonal['id']})):
            assert client.post(endpoint, json=body, headers={'Idempotency-Key': 'no-credit'}).status_code == 409
            assert state(client) == before
        with Session(client.app.state.engine) as db:
            db.get(InventoryGift, seasonal['id']).pledge_supported = True
            db.commit()
        for endpoint, body in (('/api/loans/create', {'gift_id': seasonal['id'], 'weeks': 1}),
                               ('/api/inventory/demo-pledge', {'id': seasonal['id']})):
            assert client.post(endpoint, json=body, headers={'Idempotency-Key': 'flag-bypass'}).status_code == 409
            assert state(client) == before


def test_concurrent_initial_reads_grant_each_collection_once(settings, manifest):
    with TestClient(create_app(settings)) as client:
        authenticate(client)
        barrier = Barrier(2)

        def read(_):
            barrier.wait(timeout=10)
            return inventory(client)

        with ThreadPoolExecutor(max_workers=2) as pool:
            states = list(pool.map(read, [0, 1]))
        assert states[0] == states[1]
        assert len(states[0]['inventory']) == 7
        with Session(client.app.state.engine) as db:
            assert len(db.scalars(select(DemoSeasonalGrant)).all()) == 2
