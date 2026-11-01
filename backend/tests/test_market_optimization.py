"""Synthetic equivalence and operation counts for scoped catalog queries."""
import json
import threading
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.catalog_index import CatalogIndex, KINDS
from app import market_storage as storage
from app.market_valuation import valuation


@pytest.fixture(autouse=True)
def migrate_test_database():
    """These pure index tests need neither configuration nor a database."""


def catalog(count=100, models=10):
    return CatalogIndex([
        {'telegramId': str(i), 'catalogId': 100000 + i, 'title': f'Collection {i}',
         'attributes': {
             'models': [{'id': str(j + 1), 'name': f'Model {j}', 'rarity': '1%'}
                        for j in range(models)],
             'symbols': [{'id': '99', 'name': 'Shared',
                          'rarity': '1%' if i % 2 else '2%'}],
             'backdrops': [{'id': 0, 'name': 'Black', 'rarity': '3%',
                            'centerColor': '#000000', 'edgeColor': '#000000',
                            'patternColor': '#000000', 'textColor': '#ffffff'}]}}
        for i in range(1, count + 1)])


def full_scan(index, kind, identities=(), query='', offset=0, limit=60):
    """Pre-optimization algorithm retained as an independent output oracle."""
    selected = index.scope(identities)
    needle = query.strip().casefold()
    values = []
    for key, attribute in index.attributes[kind].items():
        matches = index.members[kind][key] & selected
        if not matches:
            continue
        titles = [index.collections[identity]['title'] for identity in sorted(matches)]
        if needle and not any(needle in text.casefold() for text in [attribute['name'], *titles]):
            continue
        rarities = {index.rarities[kind][key][identity] for identity in matches}
        values.append({**attribute, 'collectionCount': len(matches),
                       'rarity': next(iter(rarities)) if len(rarities) == 1 else None,
                       **({'collectionTitle': titles[0]} if kind == 'models' else {})})
    values.sort(key=lambda item: (item['name'].casefold(),
                                  item.get('collectionTitle', '').casefold(), item['value']))
    return index.page(values, offset, limit)


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('identities', [(), ['1'], ['2', '1', '1'], ['1', '2', '3']])
@pytest.mark.parametrize('query', ['', ' MODEL ', 'collection 2', 'shared', 'missing'])
def test_scoped_choices_match_full_scan(kind, identities, query):
    index = catalog(count=3, models=4)
    for offset in (0, 1, 10):
        assert index.choices(kind, identities, query, offset, 2) == full_scan(
            index, kind, identities, query, offset, 2)


class CountingDict(dict):
    def __init__(self, values):
        super().__init__(values)
        self.reads = 0

    def __getitem__(self, key):
        self.reads += 1
        return super().__getitem__(key)


def test_scoped_choices_operation_count():
    index = catalog()
    members = CountingDict(index.members['models'])
    index.members['models'] = members
    expected = full_scan(index, 'models', ['1'])
    before = members.reads
    members.reads = 0
    assert index.choices('models', ['1']) == expected
    after = members.reads
    assert (before, after) == (1000, 10)
    members.reads = 0
    index.choices('models')
    assert members.reads == 1000


def test_unknown_scope_still_rejected_and_shared_rarity_preserved():
    index = catalog(count=3)
    with pytest.raises(HTTPException) as error:
        index.choices('models', ['999'])
    assert error.value.status_code == 422
    assert index.choices('symbols', ['1'])['items'][0]['rarity'] == '1%'
    shared = index.choices('symbols', ['1', '2'])['items'][0]
    assert shared['rarity'] is None
    assert shared['collectionCount'] == 2


def snapshot_row(captured=1000, price='99999999999999'):
    envelope = {'schema': 1, 'source': 'telegram-resale',
                'kind': 'lowest_observed_listing', 'complete': True,
                'capturedAt': captured, 'validUntil': captured + 100}
    prices = {**envelope, 'collections': [
        {'telegramId': '1', 'catalogId': 100001, 'checkedAt': captured,
         'status': 'available', 'floorNano': price, 'sampleCount': 1,
         'inspectedCount': 1, 'hasMore': False}]}
    listings = {**envelope, 'listings': [
        {'telegramId': '1', 'catalogId': 100001, 'listingId': '9',
         'priceNano': price, 'checkedAt': captured, 'modelId': 'tg:model:1:1'}]}
    return SimpleNamespace(captured_at=captured, prices_json=json.dumps(prices),
                           listings_json=json.dumps(listings))


class FakeEngine:
    def __init__(self):
        self.row = snapshot_row()
        self.sql = 0
        self.active = 0

    def connect(self):
        engine = self

        class Connection:
            def __enter__(self):
                engine.active += 1
                return self

            def __exit__(self, *args):
                engine.active -= 1

            def scalar(self, statement):
                engine.sql += 1
                return engine.row.captured_at

            def execute(self, statement):
                engine.sql += 1
                return SimpleNamespace(first=lambda: engine.row)

        return Connection()


def test_cache_connection_release_and_sql_counts(monkeypatch):
    engine = FakeEngine()
    cache = storage.SnapshotCache(engine, catalog(count=1))
    tick = [0.0]
    monkeypatch.setattr(storage.time, 'monotonic', lambda: tick[0])
    original_decode = storage.decode_json

    def decode(raw):
        assert engine.active == 0
        return original_decode(raw)

    monkeypatch.setattr(storage, 'decode_json', decode)
    first = cache.get()
    assert engine.sql == 2
    assert first['prices']['collections'][0]['floorNano'] == '99999999999999'
    assert cache.get() is first
    assert engine.sql == 2  # warm: zero SQL
    tick[0] = 31
    assert cache.get() is first
    assert engine.sql == 3  # unchanged refresh: one SQL
    engine.row = snapshot_row(1001, '123')
    tick[0] = 62
    assert cache.get()['prices']['capturedAt'] == 1001
    assert engine.sql == 5  # changed refresh: two SQL


def test_invalidation_during_validation_is_not_suppressed(monkeypatch):
    engine = FakeEngine()
    cache = storage.SnapshotCache(engine, catalog(count=1))
    entered, release, invalidating = threading.Event(), threading.Event(), threading.Event()
    errors = []
    original_validate = storage.validate_snapshot

    def validate(*args, **kwargs):
        assert engine.active == 0
        entered.set()
        assert release.wait(5)
        return original_validate(*args, **kwargs)

    monkeypatch.setattr(storage, 'validate_snapshot', validate)

    def read():
        try:
            cache.get()
        except BaseException as error:
            errors.append(error)

    def ingest():
        engine.row = snapshot_row(1001, '123')
        invalidating.set()
        cache.invalidate()

    reader = threading.Thread(target=read)
    writer = threading.Thread(target=ingest)
    reader.start()
    try:
        assert entered.wait(5)
        writer.start()
        assert invalidating.wait(5)
    finally:
        release.set()
        reader.join(5)
        if writer.ident is not None:
            writer.join(5)
    assert not reader.is_alive() and not writer.is_alive()
    assert not errors
    assert cache.get()['prices']['capturedAt'] == 1001
    assert engine.sql == 4  # B is fetched immediately, without waiting 30 seconds.


class CountingListings(list):
    def __iter__(self):
        for item in super().__iter__():
            self.visits += 1
            yield item


def test_collection_lookup_built_once_and_bounded(monkeypatch):
    index = catalog(count=151, models=1)
    listings = CountingListings([
        {'telegramId': str(i), 'catalogId': 100000 + i,
         'listingId': str((i - 1) * 300 + j + 1), 'priceNano': str(100 + j),
         'checkedAt': 1000 + j % 2, 'modelId': f'tg:model:{i}:1',
         'symbolId': 'tg:symbol:99', 'backdropId': 'tg:backdrop:0'}
        for i in range(1, 152) for j in range(300)])
    listings.visits = 0
    feed = {'capturedAt': 1000, 'validUntil': 1100, 'listings': listings}
    snapshot = {'prices': {'capturedAt': 1000}, 'listings': feed}
    engine = FakeEngine()
    cache = storage.SnapshotCache(engine, index)
    # The real validator remains covered by the cache tests above and market tests.
    monkeypatch.setattr(storage, 'validate_snapshot', lambda *args, **kwargs: snapshot)
    stored, bucket = cache.get_collection('1')
    assert stored is snapshot and set(stored) == {'prices', 'listings'}
    assert listings.visits == 45300  # one build for this version
    assert isinstance(bucket, tuple) and len(bucket) == 300
    with pytest.raises(TypeError):
        bucket[0]['priceNano'] = '1'
    for _ in range(3):
        assert cache.get_collection('1')[1] is bucket
    assert listings.visits == 45300
    assert cache.get_collection('999')[1] == ()

    listings.visits = 0
    expected = valuation(index, '1', now=1002, snapshot=feed)
    assert listings.visits == 45300
    candidates = CountingListings(bucket)
    candidates.visits = 0
    assert valuation(index, '1', now=1002, snapshot=feed, candidates=candidates) == expected
    assert candidates.visits == 300
    assert listings.visits == 45300  # fast path did not read the global list
    assert expected['sampleCount'] == 300 and expected['floorNano'] == '100'
    assert expected['checkedAt'] == 1000
    snapshot = {'prices': {'capturedAt': 1001},
                'listings': {'validUntil': 1101, 'listings': []}}
    engine.row = snapshot_row(1001)
    cache.invalidate()
    replacement, empty = cache.get_collection('1')
    assert replacement is snapshot and empty == ()
    assert len(bucket) == 300  # prior readers retain their own immutable version


@pytest.mark.parametrize('now,status', [(1005, 'available'), (1100, 'stale')])
def test_indexed_valuation_combined_filters_and_dynamic_status(now, status):
    index = catalog(count=2, models=2)
    base = {'telegramId': '1', 'priceNano': '99999999999999', 'checkedAt': 1003,
            'modelId': 'tg:model:1:1', 'symbolId': 'tg:symbol:99',
            'backdropId': 'tg:backdrop:0'}
    bucket = (base, dict(base, priceNano='99999999999998', checkedAt=1004),
              dict(base, modelId='tg:model:1:2', priceNano='1', checkedAt=1000),
              {key: value for key, value in dict(base, priceNano='2').items()
               if key != 'symbolId'})
    feed = {'validUntil': 1100, 'listings': [*bucket, dict(base, telegramId='2')]}
    args = (index, '1', 'tg:model:1:1', 'tg:symbol:99', 'tg:backdrop:0')
    expected = valuation(*args, now=now, snapshot=feed)
    actual = valuation(*args, now=now, snapshot=feed, candidates=bucket)
    assert actual == expected
    assert actual['floorNano'] == '99999999999998' and actual['sampleCount'] == 2
    assert actual['checkedAt'] == 1003 and actual['ageSeconds'] == now - 1003
    assert actual['status'] == status
    missing = valuation(index, '1', 'tg:model:1:2', now=now, snapshot=feed, candidates=())
    assert missing['status'] == 'unknown' and missing['sampleCount'] == 0


def test_invalid_replacement_clears_collection_lookup():
    engine = FakeEngine()
    cache = storage.SnapshotCache(engine, catalog(count=1))
    first, bucket = cache.get_collection('1')
    assert first is not None and len(bucket) == 1
    engine.row = snapshot_row(1001, '01')
    cache.invalidate()
    assert cache.get_collection('1') == (None, ())
