"""Read one publicly displayed unique gift from smekz. No custody or transfers."""
import asyncio
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from scripts.telegram_catalog import CREDENTIALS, SESSION, load_credentials
from scripts.telegram_import import rarity, color
from scripts.telegram_prices import ton_amounts


async def main():
    from telethon import TelegramClient, functions, types
    credentials = load_credentials(CREDENTIALS)
    from scripts.telegram_session_permissions import protect_session_storage

    protect_session_storage(SESSION)
    client = TelegramClient(str(SESSION), credentials.api_id, credentials.api_hash, receive_updates=False,
        request_retries=0, connection_retries=0, auto_reconnect=False, flood_sleep_threshold=0, timeout=20)
    client.session.save_entities = False
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise RuntimeError('Local session needs login; no login attempted')
        peer = await client.get_input_entity('smekz')
        saved = await client(functions.payments.GetSavedStarGiftsRequest(peer=peer, offset='', limit=50, exclude_unlimited=True))
        gift = next((item.gift for item in saved.gifts if isinstance(item.gift, types.StarGiftUnique)), None)
        if gift is None or not re.fullmatch(r'[A-Za-z0-9]+-[1-9][0-9]*', gift.slug):
            raise RuntimeError('No publicly displayed unique gift found')
        model = next(a for a in gift.attributes if isinstance(a, types.StarGiftAttributeModel))
        pattern = next(a for a in gift.attributes if isinstance(a, types.StarGiftAttributePattern))
        backdrop = next(a for a in gift.attributes if isinstance(a, types.StarGiftAttributeBackdrop))
        if model.document.size > 200_000:
            raise RuntimeError('Unexpected model size')
        target = ROOT / 'public/gifts/featured'
        target.mkdir(parents=True, exist_ok=True)
        await client.download_media(model.document, file=str(target / 'relayer-model.tgs'))
        if pattern.document.size > 200_000:
            raise RuntimeError('Unexpected pattern size')
        await client.download_media(pattern.document, file=str(target / 'relayer-pattern.tgs'))
        data = {'id': 90001, 'name': gift.title, 'model': f'#{gift.num}', 'modelName': model.name,
            'collectionId': str(gift.gift_id), 'image': '/gifts/featured/relayer-poster.svg',
            'price': '0.000', 'priceSource': 'unpriced', 'tradeSupported': False, 'pledgeSupported': False,
            'previewOnly': True, 'telegramSlug': gift.slug, 'publicOwner': '@smekz', 'modelRarity': rarity(model.rarity),
            'availabilityIssued': gift.availability_issued, 'availabilityTotal': gift.availability_total,
            'symbol': {'name': pattern.name, 'image': '/gifts/featured/relayer-pattern.svg', 'rarity': rarity(pattern.rarity)},
            'backdrop': {'name': backdrop.name, 'rarity': rarity(backdrop.rarity),
                'centerColor': color(backdrop.center_color), 'edgeColor': color(backdrop.edge_color),
                'patternColor': color(backdrop.pattern_color), 'textColor': color(backdrop.text_color)}}
        try:
            result = await client(functions.payments.GetResaleStarGiftsRequest(gift_id=gift.gift_id, offset='', limit=100, sort_by_price=True))
            amounts = ton_amounts(result.gifts, str(gift.gift_id))
            if amounts:
                checked = int(time.time())
                data['marketPrice'] = {'floorNano': str(min(amounts)), 'checkedAt': checked, 'validUntil': checked + 86400,
                    'source': 'telegram-resale', 'kind': 'lowest_observed_listing', 'sampleCount': len(amounts),
                    'hasMore': bool(result.next_offset)}
        except Exception as error:
            print('Collection floor unavailable:', type(error).__name__)
        output = ROOT / 'src/pages/ExchangePage/data/relayer-preview.json'
        output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'gift': gift.title, 'slug': gift.slug, 'model': model.name,
            'priced': 'marketPrice' in data, 'publicCount': saved.count}, ensure_ascii=False))
        bot = await client.get_entity('obmen_huikin_bot')
        print('Bot main Mini App configured:', bool(getattr(bot, 'bot_has_main_app', False)))
    finally:
        await client.disconnect()


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        asyncio.run(main())
    except Exception as error:
        print('Read-only import failed:', type(error).__name__)
        raise SystemExit(1)
