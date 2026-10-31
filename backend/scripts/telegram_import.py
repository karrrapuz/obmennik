"""Read-only Telegram catalog export. Private session never enters public exports."""
import argparse
import asyncio
import io
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
from scripts.telegram_catalog import CREDENTIALS, SESSION, load_credentials
from app.catalog_labels import load_labels, resolve_title

OUTPUT = BACKEND / 'data' / 'catalog-telegram.json'
PUBLIC = ROOT / 'public' / 'gifts' / 'telegram'


def timestamp(value):
    return int(value.timestamp()) if value is not None else None


def color(value):
    return f'#{value & 0xffffff:06x}'


def rarity(value):
    if hasattr(value, 'permille'):
        return f'{value.permille / 10:g}%'
    return type(value).__name__.removeprefix('StarGiftAttributeRarity')


def save_manifest(manifest):
    payload = json.dumps(manifest, ensure_ascii=False, separators=(',', ':')) + '\n'
    for path in (OUTPUT, PUBLIC / 'catalog.json'):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(payload, encoding='utf-8')
        replace_file(temporary, path)


def replace_file(source, target):
    for attempt in range(10):
        try:
            source.replace(target)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.1 * (attempt + 1))


def restore_attributes(entry, previous):
    if previous and previous.get('attributeStatus') in ('complete', 'not_available'):
        entry['refreshStatus'] = entry['attributeStatus']
        for key in ('attributes', 'attributeStatus', 'mediaComplete'):
            entry[key] = previous.get(key, False)


async def export(client, inspect_only=False, metadata_only=False, base_only=False, refresh=False):
    from PIL import Image
    from telethon import functions, types, errors
    from telethon.errors import FloodWaitError

    async def rpc(request):
        try:
            return await client(request)
        except FloodWaitError as error:
            if error.seconds > 180:
                print(f'Telegram wait required: {error.seconds}s. Progress is saved; resume later.', flush=True)
                raise
            print(f'Telegram pacing: waiting {error.seconds + 1}s.', flush=True)
            await asyncio.sleep(error.seconds + 1)
            return await client(request)

    response = await rpc(functions.payments.GetStarGiftsRequest(hash=0))
    base_gifts = response.gifts
    if inspect_only:
        for gift in sorted(base_gifts, key=lambda item: timestamp(item.first_sale_date) or 0, reverse=True)[:20]:
            print(json.dumps({'id': str(gift.id), 'title': gift.title, 'stars': str(gift.stars),
                'firstSaleAt': timestamp(gift.first_sale_date), 'upgradeStars': gift.upgrade_stars,
                'thumbnailKinds': [type(item).__name__ for item in gift.sticker.thumbs or []]}, ensure_ascii=True))
        print(f'Public catalog types: {len(base_gifts)}', flush=True)
        return

    previous = json.loads(OUTPUT.read_text(encoding='utf-8')) if OUTPUT.exists() else {}
    prior = {item['telegramId']: item for item in previous.get('collections', [])}
    labels = load_labels()
    next_id = max([99_999, *[item['catalogId'] for item in prior.values()]]) + 1
    collections = []
    imported_at = datetime.now(timezone.utc).isoformat()
    manifest = {'schema': 1, 'importedAt': imported_at, 'collections': collections,
                'halloweenCatalogIds': previous.get('halloweenCatalogIds', []),
                'stats': {'complete': False, 'source': 'Telegram MTProto', 'realOwnership': False}}
    media_cache = {}
    media_limit = asyncio.Semaphore(3)

    async def media(document):
        key = str(document.id)
        if key in media_cache:
            return media_cache[key]
        path = PUBLIC / 'media' / f'{key}.webp'
        url = f'/gifts/telegram/media/{key}.webp'
        if path.is_file() and path.stat().st_size:
            try:
                with Image.open(path) as cached:
                    cached.verify()
                media_cache[key] = url
                return url
            except (OSError, ValueError):
                pass
        if metadata_only:
            return ''
        thumbs = [thumb for thumb in document.thumbs or []
                  if isinstance(thumb, (types.PhotoSize, types.PhotoCachedSize))]
        thumb = max(thumbs, key=lambda item: item.w * item.h) if thumbs else None
        try:
            async with media_limit:
                if thumb is not None:
                    data = await client.download_media(document, file=bytes, thumb=thumb)
                elif document.mime_type.startswith('image/') and document.size <= 4_000_000:
                    data = await client.download_media(document, file=bytes)
                else:
                    return ''
            if not data or len(data) > 4_000_000:
                return ''
            with Image.open(io.BytesIO(data)) as image:
                if image.width * image.height > 4_000_000:
                    return ''
                image = image.convert('RGBA')
                image.thumbnail((256, 256))
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix('.webp.tmp')
                image.save(temporary, format='WEBP', quality=90)
                replace_file(temporary, path)
            media_cache[key] = url
            return url
        except FloodWaitError:
            raise
        except Exception:
            return ''

    try:
        for index, gift in enumerate(base_gifts):
            external_id = str(gift.id)
            old = prior.get(external_id)
            catalog_id = old['catalogId'] if old else next_id
            if old is None:
                next_id += 1
            emoji = next((getattr(item, 'alt', '') for item in gift.sticker.attributes if getattr(item, 'alt', '')), '')
            title = gift.title or (old or {}).get('title') or (f'Gift {emoji}' if emoji else f'Gift {external_id}')
            title, title_kind = resolve_title({'telegramId': external_id, 'sourceTitle': gift.title, 'title': title}, labels)
            entry = {'telegramId': external_id, 'catalogId': catalog_id, 'title': title,
                'sourceTitle': gift.title, 'titleKind': title_kind, 'emoji': emoji,
                'stars': str(gift.stars), 'image': await media(gift.sticker) or (old or {}).get('image', ''),
                'firstSaleAt': timestamp(gift.first_sale_date), 'lastSaleAt': timestamp(gift.last_sale_date),
                'limited': bool(gift.limited), 'soldOut': bool(gift.sold_out),
                'upgradeAvailable': gift.upgrade_stars is not None,
                'attributes': {'models': [], 'symbols': [], 'backdrops': []}, 'attributeStatus': 'pending'}
            collections.append(entry)
            if base_only:
                if old:
                    entry.update(attributes=old['attributes'], attributeStatus=old['attributeStatus'],
                                 mediaComplete=old.get('mediaComplete', False))
            elif not refresh and old and old.get('refreshStatus') not in ('error', 'pending') and old.get('attributeStatus') in ('complete', 'not_available') and old.get('mediaComplete') and old.get('upgradeAvailable') == entry['upgradeAvailable']:
                entry.update(attributes=old['attributes'], attributeStatus=old['attributeStatus'], mediaComplete=True)
            else:
                try:
                    attributes = await rpc(functions.payments.GetStarGiftUpgradeAttributesRequest(gift_id=gift.id))
                    documents = []
                    previews = []
                    for attribute in attributes.attributes:
                        if isinstance(attribute, types.StarGiftAttributeModel):
                            item = {'id': str(attribute.document.id), 'name': attribute.name,
                                'image': '', 'rarity': rarity(attribute.rarity), 'crafted': bool(attribute.crafted)}
                            entry['attributes']['models'].append(item)
                            documents.append(attribute.document)
                            previews.append(item)
                        elif isinstance(attribute, types.StarGiftAttributePattern):
                            item = {'id': str(attribute.document.id), 'name': attribute.name,
                                'image': '', 'rarity': rarity(attribute.rarity)}
                            entry['attributes']['symbols'].append(item)
                            documents.append(attribute.document)
                            previews.append(item)
                        elif isinstance(attribute, types.StarGiftAttributeBackdrop):
                            entry['attributes']['backdrops'].append({'id': attribute.backdrop_id, 'name': attribute.name,
                                'rarity': rarity(attribute.rarity), 'centerColor': color(attribute.center_color),
                                'edgeColor': color(attribute.edge_color), 'patternColor': color(attribute.pattern_color),
                                'textColor': color(attribute.text_color)})
                    images = await asyncio.gather(*(media(document) for document in documents))
                    for item, image in zip(previews, images):
                        item['image'] = image
                    entry['attributeStatus'] = 'complete'
                except FloodWaitError:
                    restore_attributes(entry, old)
                    raise
                except errors.RPCError as error:
                    entry['attributeStatus'] = ('not_available' if error.message in
                        {'STARGIFT_INVALID', 'STARGIFT_UPGRADE_UNAVAILABLE', 'STARGIFT_NOT_FOUND'} else 'error')
                    if entry['attributeStatus'] == 'error':
                        print(f'Attribute read incomplete for public gift {external_id}: {type(error).__name__}', flush=True)
                except Exception as error:
                    entry['attributeStatus'] = 'error'
                    print(f'Attribute read incomplete for public gift {external_id}: {type(error).__name__}', flush=True)
                if entry['attributeStatus'] == 'error':
                    restore_attributes(entry, old)
                entry['mediaComplete'] = bool(entry['image']) and all(item['image']
                    for group in ('models', 'symbols') for item in entry['attributes'][group])
            # Keep unprocessed entries during an interrupted refresh, including stable IDs.
            manifest['collections'] = collections + [item for id, item in prior.items()
                if id not in {current['telegramId'] for current in collections}]
            save_manifest(manifest)
            print(f'{index + 1}/{len(base_gifts)} {entry["title"]}: '
                  f'{len(entry["attributes"]["models"])} models, '
                  f'{len(entry["attributes"]["symbols"])} symbols, '
                  f'{len(entry["attributes"]["backdrops"])} backdrops', flush=True)
            await asyncio.sleep(0.05 if base_only else 0.35)
    finally:
        manifest['collections'] = collections + [item for id, item in prior.items()
            if id not in {current['telegramId'] for current in collections}]
        all_entries = manifest['collections']
        halloween = [item for item in all_entries if item['firstSaleAt'] is not None and
            ((datetime.fromtimestamp(item['firstSaleAt'], timezone.utc).month == 10 and datetime.fromtimestamp(item['firstSaleAt'], timezone.utc).day >= 25)
             or (datetime.fromtimestamp(item['firstSaleAt'], timezone.utc).month == 11 and datetime.fromtimestamp(item['firstSaleAt'], timezone.utc).day <= 2))]
        if halloween:
            year = max(datetime.fromtimestamp(item['firstSaleAt'], timezone.utc).year for item in halloween)
            manifest['halloweenCatalogIds'] = [item['catalogId'] for item in halloween
                if datetime.fromtimestamp(item['firstSaleAt'], timezone.utc).year == year]
            manifest['halloweenYear'] = year
        manifest['stats'].update(collections=len(all_entries), models=sum(len(c['attributes']['models']) for c in all_entries),
            symbols=sum(len(c['attributes']['symbols']) for c in all_entries),
            backdrops=sum(len(c['attributes']['backdrops']) for c in all_entries),
            missingMedia=sum(not bool(c.get('image')) for c in all_entries) + sum(not bool(a.get('image'))
                for c in all_entries for group in ('models', 'symbols') for a in c['attributes'][group]),
            metadataComplete=len(collections) == len(base_gifts) and all(c['attributeStatus'] in ('complete', 'not_available') and c.get('refreshStatus') not in ('error', 'pending') for c in collections),
            complete=False)
        manifest['stats']['complete'] = manifest['stats']['metadataComplete'] and manifest['stats']['missingMedia'] == 0
        save_manifest(manifest)
    return manifest['stats']['complete'] or (base_only and len(collections) == len(base_gifts))


async def run(args):
    from telethon import TelegramClient
    credentials = load_credentials(CREDENTIALS)
    client = TelegramClient(str(SESSION), credentials.api_id, credentials.api_hash, receive_updates=False,
        request_retries=2, connection_retries=1, auto_reconnect=False, flood_sleep_threshold=0,
        raise_last_call_error=True, timeout=20, device_model='GiftMoney Local Catalog Reader')
    client.session.save_entities = False
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise RuntimeError('Local login is required')
        return await export(client, args.inspect, args.metadata_only, args.base_only, args.refresh)
    finally:
        await client.disconnect()


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect', action='store_true')
    parser.add_argument('--metadata-only', action='store_true')
    parser.add_argument('--base-only', action='store_true')
    parser.add_argument('--refresh', action='store_true', help='Re-read attributes and repair cached media without changing stable IDs')
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:
        complete = asyncio.run(run(args))
        return 0 if complete or args.inspect else 2
    except KeyboardInterrupt:
        print('Stopped. Import can be resumed.', flush=True)
    except Exception as error:
        print(f'Import stopped: {type(error).__name__}. Private details are not logged.', flush=True)
        frame = error.__traceback__
        while frame:
            print(f'Location: {Path(frame.tb_frame.f_code.co_filename).name}:{frame.tb_lineno}', flush=True)
            frame = frame.tb_next
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
