"""Bounded public asking-price observations, not executable financial valuations."""
import json
import hashlib
import hmac
import re
import time
from pathlib import Path
from typing import Annotated

from fastapi import HTTPException, Query, Request, Response
from starlette.concurrency import run_in_threadpool
from .catalog_index import CatalogIndex, CollectionId, ModelId, SymbolId, BackdropId, is_telegram_id
from . import market_prices
from .market_storage import (InvalidSnapshot, SnapshotCache, decode_json, read_json,
                             save_snapshot, validate_prices, validate_snapshot)

MARKET_LISTINGS_PATH = Path(__file__).resolve().parents[1] / 'data/market-listings.json'
MAX_BYTES = 16 * 1024 * 1024
MAX_LISTINGS = 45300
DAY = 86400
FIELDS = {'modelId': 'models', 'symbolId': 'symbols', 'backdropId': 'backdrops'}


def load_market_listings(index, path=None, now=None):
    now = int(time.time()) if now is None else now
    try:
        with Path(path if path is not None else MARKET_LISTINGS_PATH).open('rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return None
        data = json.loads(raw)
        if (not isinstance(data, dict) or type(data.get('schema')) is not int or data['schema'] != 1
                or data.get('source') != 'telegram-resale' or data.get('kind') != 'lowest_observed_listing'
                or data.get('complete') is not True or not isinstance(data.get('listings'), list)
                or len(data['listings']) > MAX_LISTINGS):
            return None
        captured, until = data.get('capturedAt'), data.get('validUntil')
        if (type(captured) is not int or not 0 < captured <= now + 60
                or type(until) is not int or not captured < until <= captured + DAY):
            return None
        entries, seen = [], set()
        for item in data['listings']:
            if not isinstance(item, dict):
                return None
            collection, identity = item.get('telegramId'), item.get('listingId')
            price, checked = item.get('priceNano'), item.get('checkedAt')
            if (not is_telegram_id(collection) or not is_telegram_id(identity) or identity in seen
                    or not isinstance(price, str) or not re.fullmatch(r'[1-9][0-9]{0,14}', price)
                    or int(price) > 100_000_000_000_000
                    or type(checked) is not int or not captured <= checked <= now + 60 or checked >= until):
                return None
            seen.add(identity)
            descriptor = index.collections.get(collection)
            if descriptor is None:
                continue
            if type(item.get('catalogId')) is not int or item['catalogId'] != descriptor['catalogId']:
                return None
            clean = {key: item[key] for key in ('telegramId', 'listingId', 'priceNano', 'checkedAt')}
            for field, kind in FIELDS.items():
                value = item.get(field)
                if value is not None:
                    if not isinstance(value, str) or value not in index.by_collection[collection][kind]:
                        return None
                    clean[field] = value
            entries.append(clean)
        return {'capturedAt': captured, 'validUntil': until, 'listings': entries}
    except (OSError, ValueError, TypeError, RecursionError):
        return None


def valuation(index, collection_id, model_id=None, symbol_id=None, backdrop_id=None, *, path=None, now=None, snapshot=None):
    now = int(time.time()) if now is None else now
    if collection_id not in index.collections:
        raise HTTPException(422, 'Unknown collection ID')
    filters = dict(zip(FIELDS, (model_id, symbol_id, backdrop_id)))
    for field, value in filters.items():
        if value is not None and value not in index.by_collection[collection_id][FIELDS[field]]:
            raise HTTPException(422, 'Unknown attribute for collection')
    feed = snapshot if snapshot is not None else load_market_listings(index, path, now)
    matches = [] if feed is None else [item for item in feed['listings']
        if item['telegramId'] == collection_id and all(value is None or item.get(field) == value for field, value in filters.items())]
    checked = min((item['checkedAt'] for item in matches), default=None)
    return {'collectionId': collection_id, **filters, 'source': 'telegram-resale',
            'kind': 'lowest_observed_listing', 'readOnly': True, 'guaranteedValuation': False,
            'tradeSupported': False, 'pledgeSupported': False,
            'status': 'unknown' if not matches else ('stale' if now >= feed['validUntil'] else 'available'),
            'floorNano': str(min(int(item['priceNano']) for item in matches)) if matches else None,
            'sampleCount': len(matches), 'checkedAt': checked,
            'ageSeconds': max(0, now - checked) if checked is not None else None,
            'validUntil': feed['validUntil'] if feed else None}


def register_market_routes(app, provider, engine=None, ingest_key=''):
    index = CatalogIndex(provider.collections)
    cache = SnapshotCache(engine, index) if engine is not None else None

    def current():
        return cache.get() if cache is not None else None

    def authenticate(request):
        if (not isinstance(ingest_key, str) or not 32 <= len(ingest_key) <= 512
                or not ingest_key.isascii() or any(c.isspace() for c in ingest_key) or cache is None):
            raise HTTPException(503, 'Market ingestion is not configured')
        header = request.headers.get('authorization', '')
        token = header[7:] if header.startswith('Bearer ') and len(header) <= 1024 else ''
        if not hmac.compare_digest(hashlib.sha256(token.encode()).digest(),
                                   hashlib.sha256(ingest_key.encode()).digest()):
            raise HTTPException(401, 'Invalid market ingestion credentials')

    def persist(raw):
        try:
            snapshot = validate_snapshot(decode_json(raw), index)
            version = save_snapshot(engine, snapshot)
        except InvalidSnapshot as error:
            raise HTTPException(400, str(error)) from None
        cache.invalidate()
        return {'capturedAt': version, 'readOnly': True, 'stored': True}

    @app.post('/api/internal/market/snapshots')
    async def ingest(request: Request):
        # No body parameters/dependencies: authentication happens before the first receive.
        authenticate(request)
        if request.headers.get('content-encoding', 'identity').lower() != 'identity':
            raise HTTPException(415, 'Compressed snapshots are not accepted')
        if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json':
            raise HTTPException(415, 'JSON snapshot required')
        declared = request.headers.get('content-length')
        if declared is not None:
            if not declared.isascii() or not declared.isdecimal() or len(declared) > 10:
                raise HTTPException(400, 'Invalid content length')
            if int(declared) > MAX_BYTES:
                raise HTTPException(413, 'Snapshot exceeds size limit')
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > MAX_BYTES:
                raise HTTPException(413, 'Snapshot exceeds size limit')
            raw.extend(chunk)
        return await run_in_threadpool(persist, raw)

    @app.get('/api/market/prices')
    def prices(response: Response):
        response.headers['Cache-Control'] = 'no-store'
        snapshot = current()
        if snapshot is not None:
            return snapshot['prices']
        try:
            return validate_prices(read_json(market_prices.MARKET_PRICES_PATH), index)
        except InvalidSnapshot:
            return {'schema': 1, 'source': 'telegram-resale', 'kind': 'lowest_observed_listing',
                    'complete': False, 'capturedAt': None, 'validUntil': None, 'collections': []}

    @app.get('/api/market/valuation')
    def observe(response: Response, collection_id: Annotated[CollectionId, Query()],
                model_id: Annotated[ModelId | None, Query()] = None,
                symbol_id: Annotated[SymbolId | None, Query()] = None,
                backdrop_id: Annotated[BackdropId | None, Query()] = None):
        response.headers['Cache-Control'] = 'no-store'
        snapshot = current()
        return valuation(index, collection_id, model_id, symbol_id, backdrop_id,
                         snapshot=snapshot['listings'] if snapshot else None)
