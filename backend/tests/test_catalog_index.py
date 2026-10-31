"""All public attribute identities, bounded search, and display-name safety."""
import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app import catalog, catalog_labels
from app.catalog_index import CatalogIndex
from app.config import Settings
from app.main import create_app
from test_auth import BOT_TOKEN


@pytest.fixture
def settings(tmp_path):
    return Settings(bot_token=BOT_TOKEN, database_url=f'sqlite:///{(tmp_path / "index.sqlite").as_posix()}', allowed_origins=())


@pytest.fixture
def data():
    def collection(identity, catalog_id, title, rarity):
        return {'telegramId': identity, 'catalogId': catalog_id, 'title': title, 'sourceTitle': title,
            'image': '/gifts/telegram/media/1.webp', 'access_hash': 'PRIVATE', 'owner_name': 'PRIVATE',
            'attributes': {
                'models': [{'id': identity + '1', 'name': 'Same Name', 'image': '/gifts/telegram/media/1.webp', 'rarity': '1%', 'crafted': False}],
                'symbols': [{'id': '999', 'name': 'Shared Symbol', 'image': '/gifts/telegram/media/2.webp', 'rarity': rarity}],
                'backdrops': [{'id': 7, 'name': 'Shared Backdrop', 'rarity': '2%', 'centerColor': '#112233',
                               'edgeColor': '#223344', 'patternColor': '#334455', 'textColor': '#ffffff'}]}}
    return [collection('123', 100000, 'First', '1%'), collection('456', 100001, 'Second', '5%')]


def test_identity_union_does_not_collapse_same_name_models(settings, data):
    index = CatalogIndex(data)
    assert {k: len(v) for k, v in index.attributes.items()} == {'models': 2, 'symbols': 1, 'backdrops': 1}
    models = index.choices('models')['items']
    assert {m['value'] for m in models} == {'tg:model:123:1231', 'tg:model:456:4561'}
    assert {m['name'] for m in models} == {'Same Name'}
    assert {m['collectionTitle'] for m in models} == {'First', 'Second'}
    assert index.choices('symbols')['items'][0]['rarity'] is None
    assert index.choices('symbols', ['123'])['items'][0]['rarity'] == '1%'
    assert index.choices('backdrops')['items'][0]['collectionCount'] == 2


def test_combined_criteria_and_scoped_choices(settings, data):
    index = CatalogIndex(data)
    assert index.choices('models', ['123'])['total'] == 1
    assert index.choices('models', query='second')['items'][0]['collectionId'] == '456'
    page = index.find_collections(models=['tg:model:123:1231'], symbols=['tg:symbol:999'], backdrops=['tg:backdrop:7'])
    assert [item['telegramId'] for item in page['items']] == ['123']
    assert index.find_collections(identities=['456'], models=['tg:model:123:1231'])['total'] == 0
    assert index.find_collections(models=['tg:model:123:1231', 'tg:model:456:4561'])['total'] == 2


def test_pagination_exhaustive_and_version_deterministic(settings, data):
    index = CatalogIndex(data)
    first = index.choices('models', offset=0, limit=1)
    second = index.choices('models', offset=first['nextOffset'], limit=1)
    assert first['total'] == 2 and second['nextOffset'] is None
    assert first['items'][0]['value'] != second['items'][0]['value']
    assert CatalogIndex(deepcopy(data)).version == index.version
    data[0]['title'] = 'Changed'
    assert CatalogIndex(data).version != index.version


def test_bad_optional_attribute_never_replaces_valid_identity(settings, data):
    data[1]['attributes']['symbols'][0]['name'] = 'Conflict'
    data[1]['attributes']['models'].append({'name': 'No ID'})
    index = CatalogIndex(data)
    assert index.omitted_attributes == 2
    assert index.collections['456']['attributeCounts']['symbols'] == 0
    assert index.choices('symbols')['items'][0]['name'] == 'Shared Symbol'


@pytest.fixture
def client(settings, data, monkeypatch, tmp_path):
    source = tmp_path / 'catalog.json'
    source.write_text(json.dumps({'schema': 1, 'collections': data, 'halloweenCatalogIds': []}), encoding='utf-8')
    monkeypatch.setattr(catalog, 'TELEGRAM_CATALOG_PATH', source)
    with TestClient(create_app(settings)) as client:
        yield client


def test_public_api_bounded_and_no_private_or_ownership_data(client):
    response = client.get('/api/catalog')
    assert response.status_code == 200
    assert response.json()['attributes'] == {'models': 2, 'symbols': 1, 'backdrops': 1}
    assert response.json()['readOnly'] is True
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-catalog-version'] == response.json()['version']
    for path in ['/api/catalog/collections', '/api/catalog/attributes?kind=models']:
        response = client.get(path)
        assert response.status_code == 200
        assert 'PRIVATE' not in response.text and 'access_hash' not in response.text
        assert 'user_id' not in response.text and 'price' not in response.text
    response = client.get('/api/catalog/collections', params=[('model_ids', 'tg:model:123:1231'), ('symbol_ids', 'tg:symbol:999')])
    assert response.json()['total'] == 1


@pytest.mark.parametrize('path', [
    '/api/catalog/attributes?kind=bad', '/api/catalog/attributes?kind=models&limit=101',
    '/api/catalog/attributes?kind=symbols&offset=-1', '/api/catalog/collections?limit=0',
    '/api/catalog/attributes?kind=models&collection_ids=unknown',
    '/api/catalog/collections?model_ids=tg:model:456:1231',
    '/api/catalog/collections?symbol_ids=Shared%20Symbol',
    '/api/catalog/collections?q=' + 'x' * 129,
    '/api/catalog/collections?' + '&'.join('model_ids=x' for _ in range(101)),
])
def test_invalid_or_unbounded_requests_rejected(client, path):
    assert client.get(path).status_code == 422


def test_optional_labels_preserve_official_names_and_financial_ids(settings, data, monkeypatch, tmp_path):
    path = tmp_path / 'labels.json'
    labels = {'schema': 1, 'labels': [
        {'telegramId': '123', 'displayTitle': 'Override official?', 'kind': 'descriptive'},
        {'telegramId': '456', 'displayTitle': 'Readable gift', 'kind': 'descriptive'}]}
    path.write_text(json.dumps(labels), encoding='utf-8')
    monkeypatch.setattr(catalog_labels, 'LABELS_PATH', path)
    source = tmp_path / 'catalog.json'
    data[1].update(title='Gift emoji', sourceTitle=None)
    source.write_text(json.dumps({'schema': 1, 'collections': data, 'halloweenCatalogIds': [100001]}), encoding='utf-8')
    loaded = catalog.load_catalog(telegram_path=source)
    assert [card['name'] for card in loaded.cards[-2:]] == ['First', 'Readable gift']
    assert [card['id'] for card in loaded.cards[-2:]] == [100000, 100001]
    assert loaded.halloween_catalog_ids == (100001,)
    assert all(card['tradeSupported'] is False and card['price'] == '0.000' for card in loaded.cards[-2:])
    assert loaded.collections[-1]['titleKind'] == 'descriptive'
    labels['labels'].append(labels['labels'][0])
    path.write_text(json.dumps(labels), encoding='utf-8')
    assert catalog_labels.load_labels() == {}


def test_real_artifact_all_choices_and_named_untitled_types(settings):
    root = catalog.DATA_PATH
    manifest = json.loads((root / 'catalog-telegram.json').read_text(encoding='utf-8'))
    index = CatalogIndex(manifest['collections'])
    assert index.omitted_attributes == 0
    assert {k: len(v) for k, v in index.attributes.items()} == {'models': 7808, 'symbols': 717, 'backdrops': 80}
    assert (root / 'catalog-labels.json').read_bytes() == (root.parents[1] / 'public/gifts/telegram/labels.json').read_bytes()
    labels = catalog_labels.load_labels()
    assert len(labels) == 26
    assert all(c['sourceTitle'] or c['telegramId'] in labels for c in manifest['collections'])
