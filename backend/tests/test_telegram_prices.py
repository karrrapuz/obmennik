"""No network or personal session: TON-only, bounded public market observations."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from app.config import Settings
from scripts import telegram_prices as prices
from telethon.types import StarsAmount, StarsTonAmount


@pytest.fixture
def settings(tmp_path):
    return Settings(bot_token='12345:test', database_url=f'sqlite:///{(tmp_path / "prices.sqlite").as_posix()}', allowed_origins=())


def gift(*amounts, gift_id=123, **extra):
    return SimpleNamespace(gift_id=gift_id, resell_amount=list(amounts), burned=False, **extra)


def test_only_real_positive_ton_exact_integer_amounts():
    gifts = [gift(StarsAmount(amount=10000, nanos=0)), gift(StarsTonAmount(amount=1)),
             gift(StarsTonAmount(amount=prices.CAP - 1)), gift(StarsTonAmount(amount=0)),
             gift(StarsTonAmount(amount=-1)), gift(StarsTonAmount(amount=True)),
             gift(StarsTonAmount(amount=prices.CAP + 1)), gift(StarsTonAmount(amount=2), gift_id=456)]
    assert prices.ton_amounts(gifts, '123') == [1, prices.CAP - 1]


@pytest.fixture
def export_setup(tmp_path, monkeypatch):
    monkeypatch.setattr(prices, 'CATALOG', tmp_path / 'catalog.json')
    monkeypatch.setattr(prices, 'OUTPUT', tmp_path / 'backend/prices.json')
    monkeypatch.setattr(prices, 'PUBLIC', tmp_path / 'public/prices.json')
    monkeypatch.setattr(prices, 'CHECKPOINT', tmp_path / '.local/prices-progress.json')
    prices.CATALOG.write_text(json.dumps({'collections': [
        {'telegramId': '123', 'catalogId': 100000, 'title': 'Public', 'attributes': {'models': [{}]}},
        {'telegramId': '456', 'catalogId': 100001, 'title': 'Ordinary', 'attributes': {'models': []}},
    ]}), encoding='utf-8')

    async def no_sleep(_):
        pass

    monkeypatch.setattr(prices.asyncio, 'sleep', no_sleep)
    return tmp_path


def test_bounded_pages_minimum_and_allowlisted_export(export_setup):
    from telethon.tl.functions.payments import GetResaleStarGiftsRequest

    class Client:
        calls = 0

        async def __call__(self, request):
            assert isinstance(request, GetResaleStarGiftsRequest)
            assert request.gift_id == 123 and request.limit == 100 and request.sort_by_price
            self.calls += 1
            return SimpleNamespace(gifts=[gift(StarsTonAmount(amount=9 if self.calls == 1 else 1),
                owner_name='PRIVATE_OWNER', access_hash='PRIVATE_HASH')], next_offset=str(self.calls))

    client = Client()
    feed = asyncio.run(prices.collect(client, pages=2))
    assert client.calls == 2 and feed['complete'] is True
    ordinary, priced = feed['collections']
    assert ordinary['status'] == 'not_collectible' and ordinary['floorNano'] is None
    assert priced['floorNano'] == '1' and priced['sampleCount'] == 2
    assert priced['hasMore'] is True and priced['inspectedCount'] == 2
    assert feed['kind'] == 'lowest_observed_listing'
    assert feed['validUntil'] - feed['capturedAt'] == 86400
    assert prices.OUTPUT.read_bytes() == prices.PUBLIC.read_bytes()
    assert 'PRIVATE' not in prices.PUBLIC.read_text()
    assert 'owner_name' not in prices.PUBLIC.read_text()


def test_stars_only_means_no_ton_quote_not_zero(export_setup):
    async def client(_):
        return SimpleNamespace(gifts=[gift(StarsAmount(amount=999, nanos=0))], next_offset='')

    feed = asyncio.run(prices.collect(client))
    assert feed['collections'][-1]['status'] == 'no_ton_listings'
    assert feed['collections'][-1]['floorNano'] is None


def test_probe_never_publishes(export_setup):
    async def client(_):
        return SimpleNamespace(gifts=[], next_offset='')

    asyncio.run(prices.collect(client, probe=True))
    assert not prices.OUTPUT.exists() and not prices.PUBLIC.exists()


def test_failed_request_not_success_and_no_private_error_export(export_setup, capsys):
    async def client(_):
        raise RuntimeError('PRIVATE_API_PAYLOAD')

    feed = asyncio.run(prices.collect(client))
    assert not feed['complete']
    assert feed['collections'][-1]['status'] == 'error'
    assert 'PRIVATE_API_PAYLOAD' not in capsys.readouterr().out
    assert 'PRIVATE_API_PAYLOAD' not in prices.CHECKPOINT.read_text()
    assert not prices.PUBLIC.exists()


def test_large_flood_wait_preserves_checkpoint_without_retry(export_setup):
    from telethon.errors import FloodWaitError

    async def client(_):
        raise FloodWaitError(request=None, capture=121)

    with pytest.raises(FloodWaitError):
        asyncio.run(prices.collect(client))
    saved = json.loads(prices.CHECKPOINT.read_text())
    assert saved['complete'] is False


def test_failed_refresh_preserves_previous_published_snapshot(export_setup):
    previous = {'schema': 1, 'complete': True, 'collections': [{'public': 'previous'}]}
    prices.save_feed(previous, publish=True)

    async def client(_):
        raise RuntimeError('temporary failure')

    assert not asyncio.run(prices.collect(client))['complete']
    assert json.loads(prices.OUTPUT.read_text()) == previous
    assert json.loads(prices.PUBLIC.read_text()) == previous
    assert not json.loads(prices.CHECKPOINT.read_text())['complete']
