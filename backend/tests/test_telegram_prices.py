"""No network or personal session: TON-only, bounded public market observations."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from app.config import Settings
from scripts import telegram_prices as prices
from telethon.types import StarsAmount, StarsTonAmount
from telethon.tl.functions.payments import GetStarGiftsRequest


def public_metadata(request):
    if isinstance(request, GetStarGiftsRequest):
        assert request.hash == 0
        return SimpleNamespace(gifts=[SimpleNamespace(id=123, upgrade_stars=None),
                                      SimpleNamespace(id=456, upgrade_stars=None)])


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
    monkeypatch.setattr(prices, 'LISTINGS', tmp_path / 'backend/listings.json')
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
            if isinstance(request, GetStarGiftsRequest):
                return public_metadata(request)
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
    async def client(request):
        if isinstance(request, GetStarGiftsRequest):
            return public_metadata(request)
        return SimpleNamespace(gifts=[gift(StarsAmount(amount=999, nanos=0))], next_offset='')

    feed = asyncio.run(prices.collect(client))
    assert feed['collections'][-1]['status'] == 'no_ton_listings'
    assert feed['collections'][-1]['floorNano'] is None


def test_probe_never_publishes(export_setup):
    async def client(request):
        if isinstance(request, GetStarGiftsRequest):
            return public_metadata(request)
        return SimpleNamespace(gifts=[], next_offset='')

    asyncio.run(prices.collect(client, probe=True))
    assert not prices.OUTPUT.exists() and not prices.PUBLIC.exists()


def test_failed_request_not_success_and_no_private_error_export(export_setup, capsys):
    async def client(request):
        if isinstance(request, GetStarGiftsRequest):
            return public_metadata(request)
        raise RuntimeError('PRIVATE_API_PAYLOAD')

    feed = asyncio.run(prices.collect(client))
    assert not feed['complete']
    assert feed['collections'][-1]['status'] == 'error'
    assert 'PRIVATE_API_PAYLOAD' not in capsys.readouterr().out
    assert 'PRIVATE_API_PAYLOAD' not in prices.CHECKPOINT.read_text()
    assert not prices.PUBLIC.exists()


def test_large_flood_wait_preserves_checkpoint_without_retry(export_setup):
    from telethon.errors import FloodWaitError

    async def client(request):
        if isinstance(request, GetStarGiftsRequest):
            return public_metadata(request)
        raise FloodWaitError(request=None, capture=121)

    with pytest.raises(FloodWaitError):
        asyncio.run(prices.collect(client))
    saved = json.loads(prices.CHECKPOINT.read_text())
    assert saved['complete'] is False


def test_failed_refresh_preserves_previous_published_snapshot(export_setup):
    previous = {'schema': 1, 'complete': True, 'collections': [{'public': 'previous'}]}
    prices.save_feed(previous, publish=True)

    async def client(request):
        if isinstance(request, GetStarGiftsRequest):
            return public_metadata(request)
        raise RuntimeError('temporary failure')

    assert not asyncio.run(prices.collect(client))['complete']
    assert json.loads(prices.OUTPUT.read_text()) == previous
    assert json.loads(prices.PUBLIC.read_text()) == previous
    assert not json.loads(prices.CHECKPOINT.read_text())['complete']


@pytest.mark.parametrize('upgrade_stars', [0, 25])
def test_fresh_metadata_prices_newly_upgradeable_without_cached_traits(export_setup, upgrade_stars):
    from telethon.tl.functions.payments import GetResaleStarGiftsRequest
    from telethon.types import StarGiftAttributeModel

    catalog = json.loads(prices.CATALOG.read_text())
    catalog['collections'].append({'telegramId': '789', 'catalogId': 100002, 'title': 'Still ordinary',
                                   'attributes': {'models': []}})
    prices.CATALOG.write_text(json.dumps(catalog))
    before = prices.CATALOG.read_bytes()
    requests = []

    async def client(request):
        requests.append(request)
        if isinstance(request, GetStarGiftsRequest):
            assert request.hash == 0 and len(requests) == 1
            return SimpleNamespace(gifts=[
                SimpleNamespace(id=123, upgrade_stars=None),
                SimpleNamespace(id=456, upgrade_stars=upgrade_stars),
                SimpleNamespace(id=789, upgrade_stars=None),
                SimpleNamespace(id=999, upgrade_stars=1)])
        assert isinstance(request, GetResaleStarGiftsRequest) and request.gift_id in (123, 456)
        return SimpleNamespace(gifts=[gift(StarsTonAmount(17), gift_id=request.gift_id,
            id=1000 + request.gift_id,
            attributes=[StarGiftAttributeModel('Uncached actual model', SimpleNamespace(id=919), None)])], next_offset='')

    feed = asyncio.run(prices.collect(client, listings=True))
    by_id = {item['telegramId']: item for item in feed['collections']}
    assert feed['complete'] is True
    assert set(by_id) == {'123', '456', '789'}
    assert by_id['456']['status'] == 'available' and by_id['456']['floorNano'] == '17'
    assert by_id['456']['sampleCount'] == 1
    assert by_id['789']['status'] == 'not_collectible' and by_id['789']['floorNano'] is None
    assert [r.gift_id for r in requests if isinstance(r, GetResaleStarGiftsRequest)] == [123, 456]
    observations = json.loads(prices.LISTINGS.read_text())['listings']
    newly_upgradeable = next(item for item in observations if item['telegramId'] == '456')
    assert newly_upgradeable['priceNano'] == '17'
    assert not {'modelId', 'symbolId', 'backdropId'} & newly_upgradeable.keys()
    assert prices.CATALOG.read_bytes() == before


@pytest.mark.parametrize('failure', ['rpc', 'missing_gifts', 'empty', 'oversized'])
def test_metadata_failure_aborts_before_resale_and_preserves_all_snapshots(export_setup, failure):
    previous = {'schema': 1, 'complete': True, 'previous': True}
    prices.save_feed(previous, publish=True)
    prices.LISTINGS.write_text(json.dumps(previous))
    paths = (prices.OUTPUT, prices.PUBLIC, prices.LISTINGS, prices.CHECKPOINT, prices.CATALOG)
    before = [path.read_bytes() for path in paths]
    requests = []

    async def client(request):
        requests.append(request)
        assert isinstance(request, GetStarGiftsRequest) and request.hash == 0
        if failure == 'rpc':
            raise RuntimeError('metadata unavailable')
        if failure == 'missing_gifts':
            return SimpleNamespace()
        return SimpleNamespace(gifts=[] if failure == 'empty' else [None] * 1001)

    with pytest.raises(RuntimeError if failure == 'rpc' else ValueError):
        asyncio.run(prices.collect(client, listings=True))
    assert len(requests) == 1
    assert [path.read_bytes() for path in paths] == before
