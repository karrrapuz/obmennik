"""Read-only, bounded Telegram resale observations. Never purchases or values Stars."""
import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from scripts.telegram_catalog import CREDENTIALS, SESSION, load_credentials
from scripts.telegram_import import replace_file

CATALOG = BACKEND / 'data/catalog-telegram.json'
OUTPUT = BACKEND / 'data/market-prices.json'
PUBLIC = BACKEND.parent / 'public/gifts/telegram/prices.json'
CHECKPOINT = BACKEND / '.local/telegram/prices-progress.json'
CAP = 100_000_000_000_000
TTL = 86400


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


async def collect(client, pages=2, probe=False):
    from telethon import functions, errors
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))['collections']
    captured = int(time.time())
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
            save_feed(feed, publish=feed['complete'])
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
        return await collect(client, args.pages, args.probe)
    finally:
        await client.disconnect()


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', action='store_true', help='Read one collection without writing a feed')
    parser.add_argument('--pages', type=int, choices=range(1, 4), default=2)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:
        feed = asyncio.run(run(args))
        return 0 if args.probe or feed['complete'] else 2
    except (Exception, KeyboardInterrupt) as error:
        print(f'Market import stopped: {type(error).__name__}. Private details omitted.', flush=True)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
