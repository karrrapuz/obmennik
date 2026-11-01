"""Local sample templates plus unpriced previews from an optional import."""

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .market_prices import load_market_prices
from .catalog_labels import load_labels, resolve_title
from .gift_presentation import decorative_presentation


DATA_PATH = Path(__file__).resolve().parents[1] / 'data'
SAMPLE_CATALOG_PATH = DATA_PATH / 'catalog-sample.json'
TELEGRAM_CATALOG_PATH = DATA_PATH / 'catalog-telegram.json'


@dataclass(frozen=True)
class LoadedCatalog:
    cards: tuple[dict, ...]
    halloween_catalog_ids: tuple[int, ...]
    collections: tuple[dict, ...] = ()


def load_showcase_extras():
    extras = json.loads((DATA_PATH / 'catalog-showcase-extra.json').read_text(encoding='utf-8'))
    if (len(extras) != 10 or {gift['id'] for gift in extras} != set(range(21, 31))
            or any(gift.get('demo') is not True or gift.get('priceSource') != 'sample' for gift in extras)):
        raise ValueError('Invalid presentation catalog')
    return tuple(extras)


def load_catalog(sample_path=None, telegram_path=None, *, showcase=False):
    sample = json.loads(Path(sample_path or SAMPLE_CATALOG_PATH).read_text(encoding='utf-8'))
    if showcase:
        sample.extend(load_showcase_extras())
    path = Path(telegram_path or TELEGRAM_CATALOG_PATH)
    if not path.exists():
        return LoadedCatalog(tuple(sample), ())
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if type(manifest.get('schema')) is not int or manifest['schema'] != 1:
        raise ValueError('Unsupported Telegram catalog schema')
    collections = manifest.get('collections')
    seasonal = manifest.get('halloweenCatalogIds', [])
    if not isinstance(collections, list) or not isinstance(seasonal, list):
        raise ValueError('Invalid Telegram catalog collections')
    ids = {gift['id'] for gift in sample}
    telegram_ids = set()
    imported_ids = set()
    cards = list(sample)
    normalized = []
    labels = load_labels()
    for collection in collections:
        catalog_id = collection.get('catalogId')
        telegram_id = collection.get('telegramId')
        title = collection.get('title')
        image = collection.get('image')
        if (type(catalog_id) is not int or catalog_id < 100000 or catalog_id in ids
                or not isinstance(telegram_id, str) or not telegram_id.isascii()
                or not telegram_id.isdigit() or telegram_id in telegram_ids
                or not isinstance(title, str) or not title.strip()
                or not isinstance(image, str) or (image != '' and not image.startswith('/gifts/telegram/'))
                or '..' in PurePosixPath(image).parts or any(c in image for c in ('\\', '?', '#'))):
            raise ValueError('Invalid Telegram catalog preview')
        ids.add(catalog_id)
        imported_ids.add(catalog_id)
        telegram_ids.add(telegram_id)
        title, title_kind = resolve_title(collection, labels)
        normalized.append({**collection, 'title': title, 'titleKind': title_kind})
        cards.append({'id': catalog_id, 'name': title, 'model': '\u2014', 'price': '0.000',
                      'image': image, 'collectionId': telegram_id, 'telegramCatalog': True,
                      'tradeSupported': False, 'pledgeSupported': False, 'priceSource': 'unpriced'})
        presentation = decorative_presentation(telegram_id)
        if presentation is not None:
            cards[-1]['presentation'] = presentation
    if (any(type(id) is not int or id not in imported_ids for id in seasonal)
            or len(seasonal) != len(set(seasonal))):
        raise ValueError('Invalid Halloween catalog IDs')
    observations = load_market_prices({(card['collectionId'], card['id']) for card in cards[len(sample):]})
    for card in cards[len(sample):]:
        if card['id'] in observations:
            card['marketPrice'] = observations[card['id']]
    return LoadedCatalog(tuple(cards), tuple(seasonal), tuple(normalized))
