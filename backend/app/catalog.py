"""Local sample templates plus unpriced previews from an optional import."""

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


DATA_PATH = Path(__file__).resolve().parents[1] / 'data'
SAMPLE_CATALOG_PATH = DATA_PATH / 'catalog-sample.json'
TELEGRAM_CATALOG_PATH = DATA_PATH / 'catalog-telegram.json'


@dataclass(frozen=True)
class LoadedCatalog:
    cards: tuple[dict, ...]
    halloween_catalog_ids: tuple[int, ...]


def load_catalog(sample_path=None, telegram_path=None):
    sample = json.loads(Path(sample_path or SAMPLE_CATALOG_PATH).read_text(encoding='utf-8'))
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
        cards.append({'id': catalog_id, 'name': title, 'model': '\u2014', 'price': '0.000',
                      'image': image, 'collectionId': telegram_id, 'telegramCatalog': True,
                      'tradeSupported': False, 'pledgeSupported': False, 'priceSource': 'unpriced'})
    if (any(type(id) is not int or id not in imported_ids for id in seasonal)
            or len(seasonal) != len(set(seasonal))):
        raise ValueError('Invalid Halloween catalog IDs')
    return LoadedCatalog(tuple(cards), tuple(seasonal))
