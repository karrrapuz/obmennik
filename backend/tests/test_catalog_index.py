"""All public attribute identities, bounded search, and display-name safety."""
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import catalog, catalog_labels
from app.catalog_index import CatalogIndex, public_attribute, register_catalog_routes
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
    for kind in ('models', 'symbols', 'backdrops'):
        expected = index.choices(kind, limit=10000)['items']
        actual, offset = [], 0
        while offset is not None:
            page = index.choices(kind, offset=offset, limit=100)
            assert page['version'] == index.version
            assert page['total'] == len(expected)
            actual.extend(page['items'])
            offset = page['nextOffset']
        assert actual == expected
        assert len({item['value'] for item in actual}) == len(expected)


@pytest.mark.parametrize('identity', [None, True, 123, '0', '0123', '-123', '+123', ' 123',
                                     '123\n', '\u0661\u0662\u0663', str(2 ** 63), '9' * 20])
def test_index_rejects_noncanonical_collection_ids(settings, data, identity):
    data[0]['telegramId'] = identity
    with pytest.raises(ValueError, match='Invalid catalog identity'):
        CatalogIndex(data)


@pytest.mark.parametrize('identity', [None, True, '100000', 99999, 2 ** 31])
def test_index_rejects_out_of_range_internal_catalog_ids(settings, data, identity):
    data[0]['catalogId'] = identity
    with pytest.raises(ValueError, match='Invalid catalog identity'):
        CatalogIndex(data)


@pytest.mark.parametrize('field', ['telegramId', 'catalogId'])
def test_index_rejects_duplicate_collection_identities(settings, data, field):
    data[1][field] = data[0][field]
    with pytest.raises(ValueError, match='Duplicate catalog'):
        CatalogIndex(data)


@pytest.mark.parametrize('kind', ['models', 'symbols'])
@pytest.mark.parametrize('identity', [None, True, 123, '0', '0123', '-123', '+123', ' 123',
                                     '123\n', '\u0661\u0662\u0663', str(2 ** 63), '9' * 20])
def test_invalid_document_ids_are_omitted_not_rewritten(settings, data, kind, identity):
    data[0]['attributes'][kind][0]['id'] = identity
    index = CatalogIndex(data)
    assert index.omitted_attributes == 1
    assert index.collections['123']['attributeCounts'][kind] == 0


@pytest.mark.parametrize('identity', [None, True, '7', -(2 ** 31) - 1, 2 ** 31])
def test_invalid_backdrop_ids_are_omitted_not_rewritten(settings, data, identity):
    data[0]['attributes']['backdrops'][0]['id'] = identity
    index = CatalogIndex(data)
    assert index.omitted_attributes == 1
    assert index.collections['123']['attributeCounts']['backdrops'] == 0


@pytest.mark.parametrize('identity', [-(2 ** 31), 0, 2 ** 31 - 1])
def test_backdrop_signed_integer_boundaries_are_preserved(settings, data, identity):
    attribute = {**data[0]['attributes']['backdrops'][0], 'id': identity}
    public = public_attribute('backdrops', '123', attribute)
    assert public['id'] == identity
    assert public['value'] == f'tg:backdrop:{identity}'


@pytest.mark.parametrize(('path', 'parameter', 'value'), [
    ('/api/catalog/attributes?kind=models', 'collection_ids', '0123'),
    ('/api/catalog/attributes?kind=models', 'collection_ids', '9' * 1000),
    ('/api/catalog/collections', 'collection_ids', str(2 ** 63)),
    ('/api/catalog/collections', 'collection_ids', '123\n'),
    ('/api/catalog/collections', 'model_ids', 'tg:model:0123:1231'),
    ('/api/catalog/collections', 'model_ids', f'tg:model:123:{2 ** 63}'),
    ('/api/catalog/collections', 'model_ids', f'tg:model:{2 ** 63}:1231'),
    ('/api/catalog/collections', 'model_ids', 'tg:model:123:' + '9' * 1000),
    ('/api/catalog/collections', 'model_ids', 'tg:symbol:999'),
    ('/api/catalog/collections', 'symbol_ids', 'tg:symbol:0999'),
    ('/api/catalog/collections', 'symbol_ids', f'tg:symbol:{2 ** 63}'),
    ('/api/catalog/collections', 'symbol_ids', 'tg:symbol:' + '9' * 1000),
    ('/api/catalog/collections', 'symbol_ids', 'tg:symbol:\u0661'),
    ('/api/catalog/collections', 'backdrop_ids', 'tg:backdrop:07'),
    ('/api/catalog/collections', 'backdrop_ids', 'tg:backdrop:-0'),
    ('/api/catalog/collections', 'backdrop_ids', f'tg:backdrop:{2 ** 31}'),
    ('/api/catalog/collections', 'backdrop_ids', f'tg:backdrop:{-(2 ** 31) - 1}'),
    ('/api/catalog/collections', 'backdrop_ids', 'tg:backdrop:' + '9' * 1000),
])
def test_malformed_query_ids_rejected_before_index_lookup(client, monkeypatch, path, parameter, value):
    def unexpected_lookup(*args, **kwargs):
        pytest.fail('Malformed ID reached catalog lookup')
    monkeypatch.setattr(CatalogIndex, 'scope', unexpected_lookup)
    response = client.get(path, params={parameter: value})
    assert response.status_code == 422
    assert response.json() == {'detail': 'Invalid request'}


@pytest.mark.parametrize('backdrop_id', [-(2 ** 31), 0, 2 ** 31 - 1])
@pytest.mark.parametrize(('collection_id', 'document_id', 'catalog_id'), [
    ('1', '1', 100000), (str(2 ** 63 - 1), str(2 ** 63 - 1), 2 ** 31 - 1),
])
def test_public_api_preserves_valid_boundary_ids(settings, data, collection_id, document_id, catalog_id, backdrop_id):
    collection = deepcopy(data[0])
    collection.update(telegramId=collection_id, catalogId=catalog_id)
    collection['attributes']['models'][0]['id'] = document_id
    collection['attributes']['symbols'][0]['id'] = document_id
    collection['attributes']['backdrops'][0]['id'] = backdrop_id
    app = FastAPI()
    register_catalog_routes(app, SimpleNamespace(collections=[collection]))
    expected_version = CatalogIndex([collection]).version
    assert CatalogIndex(deepcopy([collection])).version == expected_version
    with TestClient(app) as client:
        response = client.get('/api/catalog/collections', params={
            'collection_ids': collection_id, 'model_ids': f'tg:model:{collection_id}:{document_id}',
            'symbol_ids': f'tg:symbol:{document_id}', 'backdrop_ids': f'tg:backdrop:{backdrop_id}', 'limit': 1})
        assert response.status_code == 200
        page = response.json()
        assert page['total'] == 1 and page['nextOffset'] is None
        assert page['items'][0]['telegramId'] == collection_id
        assert page['items'][0]['catalogId'] == catalog_id
        assert page['version'] == expected_version
        response = client.get('/api/catalog/attributes', params={'kind': 'models', 'collection_ids': collection_id})
        assert response.status_code == 200
        assert response.json()['items'][0]['value'] == f'tg:model:{collection_id}:{document_id}'
