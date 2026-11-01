from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.gift_provider import create_gift_provider
from app.main import create_app
from test_auth import BOT_TOKEN, bearer, login


@pytest.fixture
def settings(tmp_path):
    return Settings(BOT_TOKEN, f"sqlite:///{(tmp_path / 'showcase.db').as_posix()}", (), showcase_mode=True)


def test_showcase_keeps_full_templates_and_real_transfers_disabled(monkeypatch):
    from app import catalog
    monkeypatch.setattr(catalog, 'TELEGRAM_CATALOG_PATH', Path(__file__).resolve().parents[1] / 'data/catalog-telegram.json')
    provider = create_gift_provider('demo', showcase=True)
    assert len(provider.catalog) == 181
    assert len(provider.collections) == 151
    assert provider.showcase_ids == tuple(range(1, 31))
    assert not provider.seasonal_gifts()
    assert provider.status()['real_transfers'] is False
    assert all(card['demo'] is True for card in provider.catalog[:30])


def test_thirty_priced_cards_and_new_card_exchange(settings):
    with TestClient(create_app(settings)) as client:
        headers = bearer(login(client)['access_token'])
        initial = client.get('/api/inventory', headers=headers).json()
        assert initial['showcase_mode'] is True
        assert len(initial['catalog']) == 30
        assert {card['id'] for card in initial['catalog']} == set(range(1, 31))
        assert all(float(card['price']) > 0 and card.get('tradeSupported') is not False for card in initial['catalog'])
        funded = client.post('/api/wallet/demo-topup', headers={**headers, 'Idempotency-Key': 'showcase-fund'},
                             json={'amount_nano': '20000000000', 'source': 'wallet'})
        assert funded.status_code == 200
        quote = client.post('/api/trades/quote', headers=headers,
                            json={'offered_ids': [initial['inventory'][0]['id']], 'received_ids': [30]})
        assert quote.status_code == 200
        assert quote.json()['asset'] == 'DEMO_TON'
        result = client.post('/api/trades/execute', headers={**headers, 'Idempotency-Key': 'showcase-trade'},
                             json={'quote_id': quote.json()['id']})
        assert result.status_code == 200
        refreshed = client.get('/api/inventory', headers=headers).json()
        owned = next(card for card in refreshed['inventory'] if card['catalogId'] == 30)
        assert owned['name'] == 'Mood Pack' and owned['price'] == '6.600'
        assert not owned['blockTradeGift']
        assert len(refreshed['catalog']) == 30
    with TestClient(create_app(replace(settings, showcase_mode=False))) as client:
        restored = client.get('/api/inventory', headers=headers)
        assert restored.status_code == 200
        assert len(restored.json()['catalog']) == 20
        kept = next(card for card in restored.json()['inventory'] if card['catalogId'] == 30)
        assert kept['id'] == owned['id'] and kept['price'] == owned['price']
        quote = client.post('/api/trades/quote', headers=headers,
                            json={'offered_ids': [kept['id']], 'received_ids': [2]})
        assert quote.status_code == 200


def test_default_catalog_unchanged(settings):
    with TestClient(create_app(replace(settings, showcase_mode=False))) as client:
        data = client.get('/api/inventory', headers=bearer(login(client)['access_token'])).json()
        assert len(data['catalog']) == 20
        assert not data.get('showcase_mode')
