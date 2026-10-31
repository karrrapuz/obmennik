"""Decoration has no collectible identity, rarity, price or ownership meaning."""
import json

import pytest

from app import catalog
from app.config import Settings
from app.gift_presentation import decorative_presentation


@pytest.fixture
def settings(tmp_path):
    return Settings(bot_token='12345:test', database_url=f'sqlite:///{(tmp_path / "presentation.sqlite").as_posix()}', allowed_origins=())


@pytest.mark.parametrize('identity', [None, 123, True, '', '0123', '-1', '1e9', '9223372036854775808', 'x' * 100])
def test_invalid_identity_has_no_decoration(identity):
    assert decorative_presentation(identity) is None


@pytest.mark.parametrize('identity,center', [
    ('1234', '#ca70c6'), ('5775966332847654507', '#adb070'),
    ('5776227780391864916', '#ca70c6'), ('5775955135867913556', '#ca70c6'),
])
def test_hash_matches_frontend_control_vectors(identity, center):
    value = decorative_presentation(identity)
    assert value == decorative_presentation(identity)
    assert value['backdrop']['centerColor'] == center
    assert set(value) == {'kind', 'backdrop'}
    assert value['kind'] == 'decorative'
    assert set(value['backdrop']) == {'centerColor', 'edgeColor', 'patternColor', 'textColor'}
    value['backdrop']['centerColor'] = '#000000'
    assert decorative_presentation(identity)['backdrop']['centerColor'] == center


def test_decoration_never_enters_actual_attributes_or_prices(settings, tmp_path):
    data = {'schema': 1, 'collections': [{'telegramId': '1234', 'catalogId': 100000, 'title': 'Preview',
            'image': '', 'attributes': {'models': [], 'symbols': [], 'backdrops': []}}], 'halloweenCatalogIds': [100000]}
    source = tmp_path / 'catalog.json'
    source.write_text(json.dumps(data), encoding='utf-8')
    loaded = catalog.load_catalog(telegram_path=source)
    card = loaded.cards[-1]
    assert card['presentation']['kind'] == 'decorative'
    assert not {'backdrop', 'symbol', 'modelFilterId', 'rarity'} & card.keys()
    assert card['price'] == '0.000' and card['priceSource'] == 'unpriced'
    assert not card['tradeSupported'] and not card['pledgeSupported']
    assert loaded.collections[0]['attributes'] == data['collections'][0]['attributes']
    assert json.loads(source.read_text()) == data
    assert loaded.cards[:20] == catalog.load_catalog(telegram_path=tmp_path / 'absent.json').cards
