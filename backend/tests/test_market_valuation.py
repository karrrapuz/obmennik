"""Public fixture observations only; never connects to Telegram."""
import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from telethon.types import (StarsTonAmount, StarsAmount, StarGiftAttributeModel,
                            StarGiftAttributePattern, StarGiftAttributeBackdrop)

from app.catalog_index import CatalogIndex
from app.config import Settings
from app import market_valuation as market
from scripts import telegram_prices as collector
from telethon.tl.functions.payments import GetStarGiftsRequest


@pytest.fixture
def settings(tmp_path):
    return Settings(bot_token='12345:test', database_url=f'sqlite:///{(tmp_path / "valuation.sqlite").as_posix()}', allowed_origins=())


@pytest.fixture
def setup(tmp_path):
    collection = {'telegramId': '123', 'catalogId': 100000, 'title': 'Public', 'image': '',
                  'attributes': {
                      'models': [{'id': '11', 'name': 'M', 'image': ''}],
                      'symbols': [{'id': '22', 'name': 'S', 'image': ''}],
                      'backdrops': [{'id': -3, 'name': 'B', **{key: '#112233' for key in
                          ('centerColor', 'edgeColor', 'patternColor', 'textColor')}}]}}
    path = tmp_path / 'listings.json'
    feed = {'schema': 1, 'source': 'telegram-resale', 'kind': 'lowest_observed_listing',
            'complete': True, 'capturedAt': 1000, 'validUntil': 87400,
            'listings': [{'telegramId': '123', 'catalogId': 100000, 'listingId': '99',
                          'priceNano': '12345678901', 'checkedAt': 1001,
                          'modelId': 'tg:model:123:11', 'symbolId': 'tg:symbol:22',
                          'backdropId': 'tg:backdrop:-3'}]}
    return collection, CatalogIndex([collection]), path, feed


def write(setup):
    setup[2].write_text(json.dumps(setup[3]), encoding='utf-8')


def test_actual_trait_combination_and_no_synthetic_premium(setup):
    write(setup)
    result = market.valuation(setup[1], '123', 'tg:model:123:11', 'tg:symbol:22',
                              'tg:backdrop:-3', path=setup[2], now=1002)
    assert result['floorNano'] == '12345678901'
    assert result['sampleCount'] == 1 and result['ageSeconds'] == 1
    assert result['status'] == 'available' and not result['guaranteedValuation']
    assert not result['tradeSupported'] and not result['pledgeSupported']


def test_missing_attributes_do_not_match(setup):
    setup[3]['listings'][0].pop('modelId')
    write(setup)
    result = market.valuation(setup[1], '123', 'tg:model:123:11', path=setup[2], now=1002)
    assert result['status'] == 'unknown' and result['floorNano'] is None
    assert market.valuation(setup[1], '123', path=setup[2], now=1002)['sampleCount'] == 1


def test_stale_snapshot_and_missing_snapshot(setup):
    write(setup)
    assert market.valuation(setup[1], '123', path=setup[2], now=87400)['status'] == 'stale'
    setup[2].unlink()
    assert market.valuation(setup[1], '123', path=setup[2], now=1002)['status'] == 'unknown'


@pytest.mark.parametrize('field,value', [('modelId', 'tg:model:456:11'), ('symbolId', 'tg:symbol:999'),
    ('priceNano', '01'), ('priceNano', '0'), ('priceNano', '100000000000001'),
    ('priceNano', 10), ('checkedAt', True), ('catalogId', 100001), ('listingId', '01')])
def test_forged_snapshot_is_unknown(setup, field, value):
    setup[3]['listings'][0][field] = value
    write(setup)
    assert market.load_market_listings(setup[1], setup[2], 1002) is None


def test_exact_combination_not_independent_trait_floors(setup):
    first = setup[3]['listings'][0]
    second = dict(first, listingId='98', priceNano='1')
    first.pop('symbolId')
    second.pop('modelId')
    setup[3]['listings'].append(second)
    write(setup)
    result = market.valuation(setup[1], '123', 'tg:model:123:11', 'tg:symbol:22', path=setup[2], now=1002)
    assert result['sampleCount'] == 0 and result['floorNano'] is None


def test_route_public_bounded_and_forged_ids(setup, monkeypatch):
    monkeypatch.setattr(market, 'MARKET_LISTINGS_PATH', setup[2])
    app = FastAPI()
    market.register_market_routes(app, SimpleNamespace(collections=[setup[0]]))
    with TestClient(app) as client:
        assert client.get('/api/market/valuation', params={'collection_id': '123'}).status_code == 200
        for params in ({'collection_id': '0123'}, {'collection_id': '9' * 200},
                       {'collection_id': '456'}, {'collection_id': '123', 'model_id': 'tg:model:456:11'},
                       {'collection_id': '123', 'symbol_id': 'tg:symbol:999'}):
            assert client.get('/api/market/valuation', params=params).status_code == 422


def test_bounded_optional_file_and_duplicate(setup, monkeypatch):
    setup[3]['listings'].append(dict(setup[3]['listings'][0]))
    write(setup)
    assert market.load_market_listings(setup[1], setup[2], 1002) is None
    monkeypatch.setattr(market, 'MAX_BYTES', 10)
    assert market.load_market_listings(setup[1], setup[2], 1002) is None


def test_telethon_trait_extraction_allowlists_only_public_fields(setup):
    attributes = [StarGiftAttributeModel('M', SimpleNamespace(id=11), None),
                  StarGiftAttributePattern('S', SimpleNamespace(id=22), None),
                  StarGiftAttributeBackdrop('B', -3, 0, 0, 0, 0, None)]
    gift = SimpleNamespace(id=99, gift_id=123, burned=False, attributes=attributes,
                           owner_name='PRIVATE', access_hash='PRIVATE',
                           resell_amount=[StarsAmount(999, 0), StarsTonAmount(123)])
    items = collector.listing_observations([gift], setup[0], 1001)
    assert items[0]['modelId'] == 'tg:model:123:11'
    assert items[0]['symbolId'] == 'tg:symbol:22'
    assert items[0]['backdropId'] == 'tg:backdrop:-3'
    assert items[0]['priceNano'] == '123'
    assert 'PRIVATE' not in json.dumps(items)
    gift.resell_amount = [StarsAmount(999, 0)]
    assert collector.listing_observations([gift], setup[0], 1001) == []


def test_optional_artifact_full_success_only(setup, monkeypatch):
    collection, _, path, _ = setup
    catalog = path.parent / 'catalog.json'
    catalog.write_text(json.dumps({'collections': [collection]}))
    monkeypatch.setattr(collector, 'CATALOG', catalog)
    monkeypatch.setattr(collector, 'LISTINGS', path)
    monkeypatch.setattr(collector, 'save_feed', lambda *args, **kwargs: None)

    async def no_sleep(_):
        pass

    async def client(request):
        if isinstance(request, GetStarGiftsRequest):
            return SimpleNamespace(gifts=[SimpleNamespace(id=123, upgrade_stars=None)])
        return SimpleNamespace(gifts=[SimpleNamespace(id=99, gift_id=123, attributes=[],
            resell_amount=[StarsTonAmount(1)], burned=False)], next_offset='')

    monkeypatch.setattr(collector.asyncio, 'sleep', no_sleep)
    asyncio.run(collector.collect(client, probe=True, listings=True))
    assert not path.exists()
    asyncio.run(collector.collect(client, listings=True))
    previous = path.read_bytes()

    async def broken(request):
        if isinstance(request, GetStarGiftsRequest):
            return SimpleNamespace(gifts=[SimpleNamespace(id=123, upgrade_stars=None)])
        raise RuntimeError('PRIVATE')

    asyncio.run(collector.collect(broken, listings=True))
    assert path.read_bytes() == previous


@pytest.mark.parametrize('case', ['duplicate_page', 'multiple_ton_amounts'])
def test_listing_mode_preserves_previous_snapshots_on_count_mismatch(setup, monkeypatch, case):
    collection, _, path, _ = setup
    catalog = path.parent / 'catalog.json'
    catalog.write_text(json.dumps({'collections': [collection]}))
    monkeypatch.setattr(collector, 'CATALOG', catalog)
    monkeypatch.setattr(collector, 'LISTINGS', path)
    monkeypatch.setattr(collector, 'OUTPUT', path.parent / 'prices.json')
    monkeypatch.setattr(collector, 'PUBLIC', path.parent / 'public.json')
    monkeypatch.setattr(collector, 'CHECKPOINT', path.parent / 'checkpoint.json')
    previous = {'schema': 1, 'complete': True, 'previous': True}
    collector.save_feed(previous, publish=True)
    path.write_text(json.dumps(previous))
    before = [target.read_bytes() for target in (path, collector.OUTPUT, collector.PUBLIC)]

    async def no_sleep(_):
        pass

    async def client(request):
        if isinstance(request, GetStarGiftsRequest):
            return SimpleNamespace(gifts=[SimpleNamespace(id=123, upgrade_stars=None)])
        amounts = [StarsTonAmount(1)] if case == 'duplicate_page' else [StarsTonAmount(1), StarsTonAmount(2)]
        return SimpleNamespace(gifts=[SimpleNamespace(id=99, gift_id=123, attributes=[],
            resell_amount=amounts, burned=False)], next_offset='again' if case == 'duplicate_page' else '')

    monkeypatch.setattr(collector.asyncio, 'sleep', no_sleep)
    result = asyncio.run(collector.collect(client, pages=2, listings=True))
    assert result['complete'] is False
    assert result['collections'][0]['sampleCount'] == 2
    assert [target.read_bytes() for target in (path, collector.OUTPUT, collector.PUBLIC)] == before
    assert json.loads(collector.CHECKPOINT.read_text())['complete'] is False
