"""Read-only, bounded Telegram resale observations. Never purchases or values Stars."""
import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from scripts.telegram_catalog import CREDENTIALS, SESSION, load_credentials
from scripts.telegram_import import replace_file

CATALOG = BACKEND / 'data/catalog-telegram.json'
OUTPUT = BACKEND / 'data/market-prices.json'
PUBLIC = BACKEND.parent / 'public/gifts/telegram/prices.json'
CHECKPOINT = BACKEND / '.local/telegram/prices-progress.json'
LISTINGS = BACKEND / 'data/market-listings.json'
MARKET_ENV = BACKEND / '.env.market'
CAP = 100_000_000_000_000
TTL = 86400


def listing_observations(gifts, collection, checked):
    from telethon.types import StarGiftAttributeModel, StarGiftAttributePattern, StarGiftAttributeBackdrop
    from app.catalog_index import option_value, is_telegram_id
    result = []
    for gift in gifts[:100]:
        amounts = ton_amounts([gift], collection['telegramId'])
        identity = str(getattr(gift, 'id', ''))
        if not amounts or not is_telegram_id(identity):
            continue
        entry = {'telegramId': collection['telegramId'], 'catalogId': collection['catalogId'],
                 'listingId': identity, 'priceNano': str(min(amounts)), 'checkedAt': checked}
        traits = {}
        for attribute in (getattr(gift, 'attributes', None) or [])[:100]:
            if isinstance(attribute, StarGiftAttributeModel):
                kind, raw = 'models', str(attribute.document.id)
            elif isinstance(attribute, StarGiftAttributePattern):
                kind, raw = 'symbols', str(attribute.document.id)
            elif isinstance(attribute, StarGiftAttributeBackdrop):
                kind, raw = 'backdrops', attribute.backdrop_id
            else:
                continue
            traits.setdefault(kind, []).append(raw)
        for kind, values in traits.items():
            if len(values) == 1 and any(a.get('id') == values[0] for a in collection['attributes'].get(kind, [])):
                entry[{'models': 'modelId', 'symbols': 'symbolId', 'backdrops': 'backdropId'}[kind]] = option_value(kind, collection['telegramId'], values[0])
        result.append(entry)
    return result


def ton_amounts(gifts, telegram_id):
    from telethon.types import StarsTonAmount
    return [amount.amount for gift in gifts
            if str(getattr(gift, 'gift_id', '')) == telegram_id and not getattr(gift, 'burned', False)
            for amount in getattr(gift, 'resell_amount', None) or []
            if isinstance(amount, StarsTonAmount) and type(amount.amount) is int and 0 < amount.amount <= CAP]


def save_feed(feed, publish=False):
    payload = json.dumps(feed, separators=(',', ':'), ensure_ascii=True) + '\n'
    for path in ((OUTPUT, PUBLIC, CHECKPOINT) if publish else (CHECKPOINT,)):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(payload, encoding='utf-8')
        replace_file(temporary, path)


async def collect(client, pages=2, probe=False, listings=False):
    from telethon import functions, errors
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))['collections']
    captured = int(time.time())
    if type(pages) is not int or not 1 <= pages <= 3 or len(catalog) > 151:
        raise ValueError('Collection/page bound exceeded')
    observations = {}
    feed = {'schema': 1, 'source': 'telegram-resale', 'kind': 'lowest_observed_listing',
            'capturedAt': captured, 'validUntil': captured + TTL, 'complete': False, 'collections': []}
    candidates = [c for c in catalog if c['attributes']['models']]
    if probe:
        candidates = candidates[:1]
    else:
        for collection in catalog:
            if not collection['attributes']['models']:
                feed['collections'].append({'telegramId': collection['telegramId'], 'catalogId': collection['catalogId'],
                    'checkedAt': captured, 'status': 'not_collectible', 'floorNano': None,
                    'sampleCount': 0, 'inspectedCount': 0, 'hasMore': False})
    seen = set()
    try:
        for index, collection in enumerate(candidates):
            entry = {'telegramId': collection['telegramId'], 'catalogId': collection['catalogId'],
                     'checkedAt': int(time.time()), 'status': 'error', 'floorNano': None,
                     'sampleCount': 0, 'inspectedCount': 0, 'hasMore': False}
            amounts = []
            offset = ''
            offsets = set()
            try:
                for _ in range(pages):
                    request = functions.payments.GetResaleStarGiftsRequest(
                        gift_id=int(collection['telegramId']), offset=offset, limit=100, sort_by_price=True)
                    try:
                        result = await client(request)
                    except errors.FloodWaitError as error:
                        if error.seconds > 120:
                            raise
                        print(f'Telegram pacing: waiting {error.seconds + 1}s', flush=True)
                        await asyncio.sleep(error.seconds + 1)
                        result = await client(request)
                    entry['inspectedCount'] += len(result.gifts)
                    amounts.extend(ton_amounts(result.gifts, collection['telegramId']))
                    if listings:
                        for item in listing_observations(result.gifts, collection, int(time.time())):
                            observations.setdefault(item['listingId'], item)
                    next_offset = getattr(result, 'next_offset', None) or ''
                    entry['hasMore'] = bool(next_offset)
                    if not next_offset or next_offset in offsets:
                        break
                    offsets.add(next_offset)
                    offset = next_offset
                    await asyncio.sleep(0.25)
                entry.update(status='available' if amounts else 'no_ton_listings',
                             floorNano=str(min(amounts)) if amounts else None, sampleCount=len(amounts))
            except errors.FloodWaitError:
                raise
            except Exception as error:
                print(f'Public collection {collection["telegramId"]}: {type(error).__name__}; no private details logged', flush=True)
            finally:
                feed['collections'].append(entry)
                seen.add(collection['telegramId'])
                if not probe:
                    save_feed(feed)
            print(f'{index + 1}/{len(candidates)} {collection["title"]}: {entry["status"]}, '
                  f'TON nano {entry["floorNano"]}, inspected {entry["inspectedCount"]}', flush=True)
            await asyncio.sleep(0.4)
    finally:
        if not probe:
            feed['complete'] = len(seen) == len(candidates) and all(c['status'] != 'error' for c in feed['collections'])
            if listings and feed['complete']:
                from app.market_storage import InvalidSnapshot, validate_listing_coverage
                try:
                    validate_listing_coverage(feed, {'listings': list(observations.values())})
                except InvalidSnapshot:
                    feed['complete'] = False
                    print('Listing coverage differs from collection TON samples; previous public snapshots preserved.', flush=True)
            save_feed(feed, publish=feed['complete'])
            if listings and feed['complete']:
                payload = {key: feed[key] for key in ('schema', 'source', 'kind', 'capturedAt', 'validUntil', 'complete')}
                payload['listings'] = list(observations.values())
                LISTINGS.parent.mkdir(parents=True, exist_ok=True)
                temporary = LISTINGS.with_suffix('.json.tmp')
                temporary.write_text(json.dumps(payload, separators=(',', ':')) + '\n', encoding='utf-8')
                replace_file(temporary, LISTINGS)
    return feed


async def run(args):
    from telethon import TelegramClient
    credentials = load_credentials(CREDENTIALS)
    client = TelegramClient(str(SESSION), credentials.api_id, credentials.api_hash,
        receive_updates=False, request_retries=1, connection_retries=1, auto_reconnect=False,
        flood_sleep_threshold=0, raise_last_call_error=True, timeout=20,
        device_model='GiftMoney Local Market Reader')
    client.session.save_entities = False
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise RuntimeError('Local login required')
        return await collect(client, args.pages, args.probe, args.listings)
    finally:
        await client.disconnect()


def push_configuration():
    """Only public snapshots leave this machine; secrets never belong in argv."""
    from dotenv import load_dotenv
    load_dotenv(MARKET_ENV, override=False)
    key = os.environ.get('MARKET_INGEST_KEY', '')
    origin = os.environ.get('MARKET_API_URL', '')
    parsed = urlsplit(origin)
    if (not 32 <= len(key) <= 512 or not key.isascii() or any(c.isspace() for c in key)
            or not parsed.hostname or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or parsed.path not in ('', '/')
            or parsed.scheme != 'https'):
        raise ValueError('Configure MARKET_API_URL HTTPS origin and MARKET_INGEST_KEY (32-512 ASCII characters)')
    return origin.rstrip('/') + '/api/internal/market/snapshots', key


async def push_snapshot(feed, configuration, *, client_factory=None):
    import httpx
    from app.catalog_index import CatalogIndex
    from app.market_storage import MAX_BYTES, read_json, validate_snapshot

    catalog = read_json(CATALOG)
    payload = validate_snapshot({'prices': feed, 'listings': read_json(LISTINGS)},
                                CatalogIndex(catalog['collections']))
    raw = json.dumps(payload, separators=(',', ':'), ensure_ascii=True).encode('ascii')
    if len(raw) > MAX_BYTES:
        raise ValueError('Snapshot exceeds upload limit')
    url, key = configuration
    # No proxy inheritance or redirect can forward the ingest secret elsewhere.
    factory = httpx.AsyncClient if client_factory is None else client_factory
    async with factory(timeout=30, follow_redirects=False, trust_env=False) as client:
        parsed = urlsplit(url)
        health_url = urlunsplit((parsed.scheme, parsed.netloc, '/api/health', '', ''))
        # Wake a sleeping API without disclosing the ingest key or consuming its body.
        async with asyncio.timeout(90):
            async with client.stream('GET', health_url, timeout=90) as health:
                if health.status_code != 200:
                    raise RuntimeError('Market API warm-up rejected')
        async with client.stream('POST', url, content=raw,
                headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}) as response:
            if response.status_code != 200:
                raise RuntimeError('Market snapshot upload rejected')
    print('Public market snapshot uploaded; no session or credentials exported.', flush=True)


async def push_existing(*, client_factory=None):
    """Upload already-complete public files without ever opening a Telegram session."""
    from app.market_storage import read_json
    configuration = push_configuration()
    await push_snapshot(read_json(OUTPUT), configuration, client_factory=client_factory)


async def run_cycles(args):
    if args.push_only:
        if args.watch is not None or args.push or args.probe:
            raise ValueError('Push-only cannot collect, probe or watch')
        await push_existing()
        return 0
    if args.watch is not None and not 3600 <= args.watch <= 86400:
        raise ValueError('Watch interval must be 3600-86400 seconds')
    if args.probe and (args.push or args.watch is not None):
        raise ValueError('Probe cannot watch or push')
    if args.push and not args.listings:
        raise ValueError('Push requires --listings')
    configuration = push_configuration() if args.push else None
    while True:
        result = 2
        delay = args.watch
        try:
            feed = await run(args)
            if args.probe or feed['complete']:
                if args.push:
                    await push_snapshot(feed, configuration)
                result = 0
        except Exception as error:
            from telethon.errors import FloodWaitError
            if isinstance(error, FloodWaitError) and delay is not None:
                delay = max(delay, error.seconds + 1)
            print(f'Market cycle stopped: {type(error).__name__}. Private details omitted.', flush=True)
        if args.watch is None:
            return result
        print(f'Market cycle finished ({"success" if result == 0 else "failed"}); next attempt after {delay}s.', flush=True)
        await asyncio.sleep(delay)


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', action='store_true', help='Read one collection without writing a feed')
    parser.add_argument('--pages', type=int, choices=range(1, 4), default=2)
    parser.add_argument('--listings', action='store_true', help='Also publish public listing/trait observations after full success')
    parser.add_argument('--watch', type=int, metavar='SECONDS', nargs='?', const=3600,
                        help='Repeat locally after each run, interval 3600-86400 seconds (default 3600)')
    parser.add_argument('--push', action='store_true', help='Upload public feeds using runtime .env.market; requires --listings')
    parser.add_argument('--push-only', action='store_true', help='Upload existing complete public files without opening Telegram')
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:
        return asyncio.run(run_cycles(args))
    except (Exception, KeyboardInterrupt) as error:
        print(f'Market import stopped: {type(error).__name__}. Private details omitted.', flush=True)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
