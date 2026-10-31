"""Validated public snapshot persistence with bounded, version-aware DB egress."""
import json
import re
import threading
import time
from pathlib import Path

from sqlalchemy import select, update

from .market_models import MarketSnapshot
from .catalog_index import is_telegram_id

MAX_BYTES = 16 * 1024 * 1024
MAX_COLLECTIONS = 151
MAX_LISTINGS = 45300
DAY = 86400
CAP = 100_000_000_000_000
FIELDS = {'modelId': 'models', 'symbolId': 'symbols', 'backdropId': 'backdrops'}
ENVELOPE = ('schema', 'source', 'kind', 'capturedAt', 'validUntil', 'complete')


class InvalidSnapshot(ValueError):
    pass


def _fail():
    raise InvalidSnapshot('Invalid public market snapshot')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail()
        result[key] = value
    return result


def decode_json(raw):
    if len(raw) > MAX_BYTES:
        _fail()
    try:
        return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=lambda _: _fail())
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise InvalidSnapshot('Invalid public market snapshot') from None


def read_json(path):
    try:
        with Path(path).open('rb') as stream:
            return decode_json(stream.read(MAX_BYTES + 1))
    except (OSError, InvalidSnapshot):
        return None


def _envelope(data, now, fresh):
    if (not isinstance(data, dict) or type(data.get('schema')) is not int or data['schema'] != 1
            or data.get('source') != 'telegram-resale' or data.get('kind') != 'lowest_observed_listing'
            or data.get('complete') is not True):
        _fail()
    captured, until = data.get('capturedAt'), data.get('validUntil')
    if (type(captured) is not int or not 0 < captured <= now + 60 or type(until) is not int
            or not captured < until <= captured + DAY or (fresh and until <= now)):
        _fail()
    return {key: data[key] for key in ENVELOPE}


def _nano(value):
    return isinstance(value, str) and re.fullmatch(r'[1-9][0-9]{0,14}', value) is not None and int(value) <= CAP


def validate_prices(data, index, now=None, *, fresh=False):
    """Same strict price/time/identity rules as load_market_prices, plus hard bounds.

    Unlike the optional legacy file loader, ingestion rejects unknown identities,
    partial runs and failed collections instead of silently skipping them.
    """
    now = int(time.time()) if now is None else now
    clean = _envelope(data, now, fresh)
    entries = data.get('collections')
    if not isinstance(entries, list) or not 0 < len(entries) <= MAX_COLLECTIONS:
        _fail()
    seen, cleaned = set(), []
    for item in entries:
        if not isinstance(item, dict):
            _fail()
        identity, catalog_id = item.get('telegramId'), item.get('catalogId')
        if not is_telegram_id(identity):
            _fail()
        descriptor = index.collections.get(identity)
        if (descriptor is None or identity in seen or type(catalog_id) is not int
                or catalog_id != descriptor['catalogId']):
            _fail()
        seen.add(identity)
        checked, count = item.get('checkedAt'), item.get('sampleCount')
        inspected = item.get('inspectedCount', count)
        status, floor = item.get('status'), item.get('floorNano')
        if (type(checked) is not int or not clean['capturedAt'] <= checked <= now + 60
                or not checked < clean['validUntil'] <= checked + DAY
                or type(count) is not int or type(inspected) is not int or not 0 <= count <= inspected <= 300
                or type(item.get('hasMore')) is not bool
                or status not in ('available', 'no_ton_listings', 'not_collectible')):
            _fail()
        if status == 'available':
            if not _nano(floor) or count == 0:
                _fail()
        elif floor is not None or count != 0:
            _fail()
        cleaned.append({'telegramId': identity, 'catalogId': catalog_id, 'checkedAt': checked,
                        'status': status, 'floorNano': floor, 'sampleCount': count,
                        'inspectedCount': inspected, 'hasMore': item['hasMore']})
    if seen != index.collections.keys():
        _fail()
    return {**clean, 'collections': cleaned}


def validate_listings(data, index, now=None, *, fresh=False):
    now = int(time.time()) if now is None else now
    clean = _envelope(data, now, fresh)
    items = data.get('listings')
    if not isinstance(items, list) or len(items) > MAX_LISTINGS:
        _fail()
    entries, seen, counts = [], set(), {}
    for item in items:
        if not isinstance(item, dict):
            _fail()
        collection, identity = item.get('telegramId'), item.get('listingId')
        if not is_telegram_id(collection) or not is_telegram_id(identity) or identity in seen:
            _fail()
        descriptor = index.collections.get(collection)
        checked = item.get('checkedAt')
        if (descriptor is None or type(item.get('catalogId')) is not int
                or item['catalogId'] != descriptor['catalogId'] or not _nano(item.get('priceNano'))
                or type(checked) is not int or not clean['capturedAt'] <= checked <= now + 60
                or checked >= clean['validUntil']):
            _fail()
        seen.add(identity)
        counts[collection] = counts.get(collection, 0) + 1
        if counts[collection] > 300:
            _fail()
        entry = {key: item[key] for key in ('telegramId', 'catalogId', 'listingId', 'priceNano', 'checkedAt')}
        for field, kind in FIELDS.items():
            if field in item:
                value = item[field]
                if not isinstance(value, str) or value not in index.by_collection[collection][kind]:
                    _fail()
                entry[field] = value
        entries.append(entry)
    return {**clean, 'listings': entries}


def validate_listing_coverage(prices, listings):
    """A complete pair must account for every TON sample and its observed minimum."""
    by_collection = {item['telegramId']: item for item in prices['collections']}
    counts, minima = {}, {}
    for item in listings['listings']:
        collection = item['telegramId']
        reference = by_collection[collection]
        amount = int(item['priceNano'])
        counts[collection] = counts.get(collection, 0) + 1
        minima[collection] = min(minima.get(collection, amount), amount)
        if (reference['status'] != 'available' or amount < int(reference['floorNano'])
                or item['checkedAt'] < reference['checkedAt'] or counts[collection] > reference['sampleCount']):
            _fail()
    for collection, reference in by_collection.items():
        if counts.get(collection, 0) != reference['sampleCount']:
            _fail()
        if reference['status'] == 'available' and minima.get(collection) != int(reference['floorNano']):
            _fail()


def validate_snapshot(payload, index, now=None, *, fresh=True):
    if not isinstance(payload, dict) or set(payload) != {'prices', 'listings'}:
        _fail()
    prices = validate_prices(payload['prices'], index, now, fresh=fresh)
    listings = validate_listings(payload['listings'], index, now, fresh=fresh)
    if any(prices[key] != listings[key] for key in ENVELOPE):
        _fail()
    validate_listing_coverage(prices, listings)
    return {'prices': prices, 'listings': listings}


def save_snapshot(engine, payload):
    """CAS update of a migration-seeded singleton is atomic across concurrent writers."""
    captured = payload['prices']['capturedAt']
    prices = json.dumps(payload['prices'], separators=(',', ':'), ensure_ascii=True)
    listings = json.dumps(payload['listings'], separators=(',', ':'), ensure_ascii=True)
    if len(prices.encode()) + len(listings.encode()) > MAX_BYTES:
        _fail()
    with engine.begin() as connection:
        result = connection.execute(update(MarketSnapshot).where(
            MarketSnapshot.id == 1, MarketSnapshot.captured_at < captured).values(
                captured_at=captured, prices_json=prices, listings_json=listings))
        if result.rowcount != 1:
            raise InvalidSnapshot('Snapshot must be newer than the stored capture')
    return captured


class SnapshotCache:
    """One decoded object per API instance; unchanged versions never fetch large text."""
    def __init__(self, engine, index):
        self.engine, self.index = engine, index
        self._lock = threading.Lock()
        self._next_check = 0.0
        self._version = None
        self._snapshot = None

    def invalidate(self):
        with self._lock:
            self._next_check = 0.0

    def get(self):
        with self._lock:
            tick = time.monotonic()
            if tick < self._next_check:
                return self._snapshot
            with self.engine.connect() as connection:
                version = connection.scalar(select(MarketSnapshot.captured_at).where(MarketSnapshot.id == 1))
                if version != self._version:
                    row = connection.execute(select(MarketSnapshot.captured_at, MarketSnapshot.prices_json,
                        MarketSnapshot.listings_json).where(MarketSnapshot.id == 1)).first() if version else None
                    snapshot = None
                    if row and row.prices_json is not None and row.listings_json is not None:
                        try:
                            if len(row.prices_json) + len(row.listings_json) > MAX_BYTES:
                                _fail()
                            snapshot = validate_snapshot({'prices': decode_json(row.prices_json),
                                'listings': decode_json(row.listings_json)}, self.index, fresh=False)
                            if snapshot['prices']['capturedAt'] != row.captured_at:
                                _fail()
                        except InvalidSnapshot:
                            snapshot = None
                    self._snapshot = snapshot
                    self._version = row.captured_at if row else version
            self._next_check = time.monotonic() + 30
            return self._snapshot
