"""Public, bounded catalog queries. No ownership, prices or private Telegram fields."""
import hashlib
import json
import re
from typing import Annotated, Literal

from fastapi import HTTPException, Query, Response
from pydantic import AfterValidator, Field

Kind = Literal['models', 'symbols', 'backdrops']
KINDS = ('models', 'symbols', 'backdrops')
PARTS = {'models': 'model', 'symbols': 'symbol', 'backdrops': 'backdrop'}
INT32_MIN = -(2 ** 31)
INT32_MAX = 2 ** 31 - 1
INT64_MAX = 2 ** 63 - 1


def is_telegram_id(value):
    return (isinstance(value, str) and re.fullmatch(r'[1-9][0-9]{0,18}', value) is not None
            and int(value) <= INT64_MAX)


def collection_query_id(value):
    if not is_telegram_id(value):
        raise ValueError('Invalid collection ID')
    return value


def attribute_query_id(value):
    parts = value.split(':')
    if (len(parts) == 4 and parts[:2] == ['tg', 'model']
            and all(is_telegram_id(part) for part in parts[2:])):
        return value
    if len(parts) == 3 and parts[:2] == ['tg', 'symbol'] and is_telegram_id(parts[2]):
        return value
    if (len(parts) == 3 and parts[:2] == ['tg', 'backdrop']
            and re.fullmatch(r'0|-?[1-9][0-9]{0,9}', parts[2])
            and INT32_MIN <= int(parts[2]) <= INT32_MAX):
        return value
    raise ValueError('Invalid attribute ID')


CollectionId = Annotated[str, Field(min_length=1, max_length=19, pattern=r'^[1-9][0-9]{0,18}$'),
                         AfterValidator(collection_query_id)]
ModelId = Annotated[str, Field(max_length=48, pattern=r'^tg:model:[1-9][0-9]{0,18}:[1-9][0-9]{0,18}$'),
                    AfterValidator(attribute_query_id)]
SymbolId = Annotated[str, Field(max_length=29, pattern=r'^tg:symbol:[1-9][0-9]{0,18}$'),
                     AfterValidator(attribute_query_id)]
BackdropId = Annotated[str, Field(max_length=23, pattern=r'^tg:backdrop:(0|-?[1-9][0-9]{0,9})$'),
                       AfterValidator(attribute_query_id)]


def option_value(kind, collection_id, attribute_id):
    return (f'tg:model:{collection_id}:{attribute_id}' if kind == 'models'
            else f'tg:{PARTS[kind]}:{attribute_id}')


def public_attribute(kind, collection_id, attribute):
    identity, name = attribute.get('id'), attribute.get('name')
    if (not isinstance(name, str) or not name.strip() or len(name) > 200
            or (kind == 'backdrops' and (type(identity) is not int or not INT32_MIN <= identity <= INT32_MAX))
            or (kind != 'backdrops' and not is_telegram_id(identity))):
        raise ValueError('Invalid catalog attribute')
    value = {'id': identity, 'value': option_value(kind, collection_id, identity), 'name': name}
    if kind == 'backdrops':
        for field in ('centerColor', 'edgeColor', 'patternColor', 'textColor'):
            color = attribute.get(field)
            if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
                raise ValueError('Invalid backdrop color')
            value[field] = color
    else:
        image = attribute.get('image', '')
        if (not isinstance(image, str) or (image and not re.fullmatch(r'/gifts/telegram/media/[0-9]+\.webp', image))):
            raise ValueError('Invalid catalog media')
        value['image'] = image
        if kind == 'models':
            value['crafted'] = attribute.get('crafted') is True
            value['collectionId'] = collection_id
    return value


class CatalogIndex:
    def __init__(self, collections):
        self.collections = {}
        self.attributes = {kind: {} for kind in KINDS}
        self.members = {kind: {} for kind in KINDS}
        self.rarities = {kind: {} for kind in KINDS}
        self.by_collection = {}
        self.omitted_attributes = 0
        catalog_ids = set()
        for collection in collections:
            if not isinstance(collection, dict):
                raise ValueError('Invalid catalog collection')
            identity, catalog_id = collection.get('telegramId'), collection.get('catalogId')
            if (not is_telegram_id(identity) or type(catalog_id) is not int
                    or not 100000 <= catalog_id <= INT32_MAX):
                raise ValueError('Invalid catalog identity')
            if identity in self.collections:
                raise ValueError('Duplicate catalog identity')
            if catalog_id in catalog_ids:
                raise ValueError('Duplicate catalog ID')
            catalog_ids.add(catalog_id)
            descriptor = {key: collection.get(key) for key in ('telegramId', 'catalogId', 'title', 'image', 'sourceTitle', 'titleKind')}
            descriptor['attributeCounts'] = {}
            self.collections[identity] = descriptor
            self.by_collection[identity] = {}
            for kind in KINDS:
                values = set()
                for attribute in collection.get('attributes', {}).get(kind, []):
                    try:
                        public = public_attribute(kind, identity, attribute)
                    except (ValueError, TypeError, AttributeError):
                        self.omitted_attributes += 1
                        continue
                    key = public['value']
                    if key in values:
                        self.omitted_attributes += 1
                        continue
                    previous = self.attributes[kind].get(key)
                    if previous is not None and previous != public:
                        self.omitted_attributes += 1
                        continue
                    values.add(key)
                    self.attributes[kind][key] = public
                    self.members[kind].setdefault(key, set()).add(identity)
                    rarity = attribute.get('rarity')
                    self.rarities[kind].setdefault(key, {})[identity] = rarity if isinstance(rarity, str) else None
                self.by_collection[identity][kind] = values
                descriptor['attributeCounts'][kind] = len(values)
        snapshot = {'collections': list(self.collections.values()), 'attributes': self.attributes,
                    'rarities': self.rarities, 'omittedAttributes': self.omitted_attributes}
        self.version = hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    def scope(self, identities):
        selected = set(identities or [])
        if not selected <= self.collections.keys():
            raise HTTPException(422, 'Unknown collection ID')
        return selected or set(self.collections)

    def choices(self, kind, identities=(), query='', offset=0, limit=60):
        selected = self.scope(identities)
        needle = query.strip().casefold()
        values = []
        for key, attribute in self.attributes[kind].items():
            matches = self.members[kind][key] & selected
            if not matches:
                continue
            titles = [self.collections[identity]['title'] for identity in sorted(matches)]
            if needle and not any(needle in text.casefold() for text in [attribute['name'], *titles]):
                continue
            rarities = {self.rarities[kind][key][identity] for identity in matches}
            values.append({**attribute, 'collectionCount': len(matches),
                           'rarity': next(iter(rarities)) if len(rarities) == 1 else None,
                           **({'collectionTitle': titles[0]} if kind == 'models' else {})})
        values.sort(key=lambda item: (item['name'].casefold(), item.get('collectionTitle', '').casefold(), item['value']))
        return self.page(values, offset, limit)

    def find_collections(self, identities=(), models=(), symbols=(), backdrops=(), query='', offset=0, limit=60):
        selected = self.scope(identities)
        filters = dict(zip(KINDS, (models, symbols, backdrops)))
        for kind, options in filters.items():
            if any(key not in self.attributes[kind] for key in options):
                raise HTTPException(422, 'Unknown attribute ID')
            if options:
                # OR within one attribute kind; AND between attribute kinds.
                selected &= set().union(*(self.members[kind][key] for key in options))
        needle = query.strip().casefold()
        values = [self.collections[identity] for identity in selected
                  if not needle or needle in self.collections[identity]['title'].casefold()]
        values.sort(key=lambda item: (item['title'].casefold(), item['telegramId']))
        return self.page(values, offset, limit)

    def page(self, items, offset, limit):
        end = offset + limit
        return {'items': items[offset:end], 'total': len(items), 'offset': offset, 'limit': limit,
                'nextOffset': end if end < len(items) else None, 'version': self.version}


def register_catalog_routes(app, provider):
    index = CatalogIndex(provider.collections)

    def mark_version(response):
        response.headers['X-Catalog-Version'] = index.version

    @app.get('/api/catalog')
    def summary(response: Response):
        mark_version(response)
        return {'version': index.version, 'collections': len(index.collections),
                'attributes': {kind: len(index.attributes[kind]) for kind in KINDS},
                'omittedAttributes': index.omitted_attributes, 'readOnly': True}

    @app.get('/api/catalog/attributes')
    def attributes(response: Response, kind: Kind,
                   collection_ids: Annotated[list[CollectionId] | None, Query(max_length=151)] = None,
                   q: Annotated[str, Query(max_length=128)] = '',
                   offset: Annotated[int, Query(ge=0, le=100000)] = 0,
                   limit: Annotated[int, Query(ge=1, le=100)] = 60):
        result = index.choices(kind, collection_ids, q, offset, limit)
        mark_version(response)
        return result

    @app.get('/api/catalog/collections')
    def collections(response: Response,
                    collection_ids: Annotated[list[CollectionId] | None, Query(max_length=151)] = None,
                    model_ids: Annotated[list[ModelId] | None, Query(max_length=100)] = None,
                    symbol_ids: Annotated[list[SymbolId] | None, Query(max_length=100)] = None,
                    backdrop_ids: Annotated[list[BackdropId] | None, Query(max_length=100)] = None,
                    q: Annotated[str, Query(max_length=128)] = '',
                    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
                    limit: Annotated[int, Query(ge=1, le=100)] = 60):
        result = index.find_collections(collection_ids, model_ids or (), symbol_ids or (), backdrop_ids or (), q, offset, limit)
        mark_version(response)
        return result
