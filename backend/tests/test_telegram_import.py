"""Public export helpers never serialize private Telegram document fields."""
import asyncio
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import Settings
from scripts import telegram_import as importer


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setattr('app.config.load_dotenv', lambda *args, **kwargs: None)
    return Settings(bot_token='12345:test', database_url=f'sqlite:///{(tmp_path / "import.sqlite").as_posix()}', allowed_origins=())


def test_public_copies_identical_and_atomic(tmp_path, monkeypatch):
    output = tmp_path / 'backend' / 'catalog.json'
    public = tmp_path / 'public'
    monkeypatch.setattr(importer, 'OUTPUT', output)
    monkeypatch.setattr(importer, 'PUBLIC', public)
    value = {'schema': 1, 'collections': [{'telegramId': '9000000000000000001'}]}
    importer.save_manifest(value)
    assert output.read_bytes() == (public / 'catalog.json').read_bytes()
    assert json.loads(output.read_text()) == value
    assert not list(tmp_path.rglob('*.tmp'))


def test_failed_refresh_retains_good_attributes():
    old = {'attributes': {'models': [{'id': '1'}]}, 'attributeStatus': 'complete', 'mediaComplete': True}
    entry = {'attributeStatus': 'error', 'attributes': {}, 'image': '/gifts/new.webp'}
    importer.restore_attributes(entry, old)
    assert entry['attributes'] == old['attributes']
    assert entry['attributeStatus'] == 'complete'
    assert entry['refreshStatus'] == 'error'
    assert entry['image'] == '/gifts/new.webp'


def test_no_previous_success_is_not_faked():
    entry = {'attributeStatus': 'pending', 'attributes': {}}
    importer.restore_attributes(entry, {'attributeStatus': 'error'})
    assert entry == {'attributeStatus': 'pending', 'attributes': {}}


def test_public_color_and_percentage():
    assert importer.color(0xFFAABBCC) == '#aabbcc'
    assert importer.rarity(type('Rarity', (), {'permille': 24})()) == '2.4%'


@pytest.fixture
def export_setup(tmp_path, monkeypatch):
    from PIL import Image
    from telethon import functions, types

    monkeypatch.setattr(importer, 'OUTPUT', tmp_path / 'backend' / 'catalog.json')
    monkeypatch.setattr(importer, 'PUBLIC', tmp_path / 'public')

    async def no_sleep(_):
        pass

    monkeypatch.setattr(importer.asyncio, 'sleep', no_sleep)
    document = SimpleNamespace(id=77, thumbs=[], mime_type='image/png', size=100,
                               attributes=[], access_hash=987654321,
                               file_reference=b'PRIVATE_FILE_REFERENCE')
    gift = SimpleNamespace(id=123, title='Public gift', stars=50, sticker=document,
                           first_sale_date=None, last_sale_date=None, limited=True,
                           sold_out=False, upgrade_stars=25)
    image = io.BytesIO()
    Image.new('RGBA', (8, 8), 'red').save(image, format='PNG')

    class Model:
        def __init__(self):
            self.document = document
            self.name = 'Public model'
            self.rarity = SimpleNamespace(permille=24)
            self.crafted = False

    monkeypatch.setattr(types, 'StarGiftAttributeModel', Model)

    class Client:
        failure = None
        downloads = 0

        async def __call__(self, request):
            if isinstance(request, functions.payments.GetStarGiftsRequest):
                return SimpleNamespace(gifts=[gift])
            assert isinstance(request, functions.payments.GetStarGiftUpgradeAttributesRequest)
            if self.failure:
                raise self.failure
            return SimpleNamespace(attributes=[Model()])

        async def download_media(self, requested, **kwargs):
            assert requested is document
            assert kwargs == {'file': bytes}
            self.downloads += 1
            return image.getvalue()

    def seed_previous():
        previous = {'telegramId': '123', 'catalogId': 100009, 'title': 'Previous',
                    'image': '/gifts/telegram/media/77.webp', 'firstSaleAt': None,
                    'upgradeAvailable': False, 'attributeStatus': 'complete',
                    'mediaComplete': True,
                    'attributes': {'models': [{'id': '88', 'name': 'Old model',
                                              'image': '/gifts/telegram/media/88.webp'}],
                                   'symbols': [], 'backdrops': []}}
        importer.save_manifest({'schema': 1, 'collections': [previous],
                                'halloweenCatalogIds': [100009]})
        return previous

    return SimpleNamespace(client=Client(), seed_previous=seed_previous)


def read_export():
    assert importer.OUTPUT.read_bytes() == (importer.PUBLIC / 'catalog.json').read_bytes()
    return json.loads(importer.OUTPUT.read_text(encoding='utf-8'))


def test_interrupted_export_preserves_old_attributes_and_stable_id(export_setup):
    from telethon.errors import FloodWaitError

    previous = export_setup.seed_previous()
    export_setup.client.failure = FloodWaitError(request=None, capture=181)
    with pytest.raises(FloodWaitError):
        asyncio.run(importer.export(export_setup.client))
    saved = read_export()
    entry = saved['collections'][0]
    assert entry['catalogId'] == previous['catalogId']
    assert entry['attributes'] == previous['attributes']
    assert entry['attributeStatus'] == 'complete'
    assert entry['refreshStatus'] == 'pending'
    # A propagated interruption must not silently discard the old checkpoint.
    assert len(saved['collections']) == 1
    assert saved['stats']['metadataComplete'] is False


def test_failed_new_export_is_incomplete(export_setup):
    export_setup.client.failure = RuntimeError('PRIVATE_ERROR_DETAILS')
    assert asyncio.run(importer.export(export_setup.client)) is False
    saved = read_export()
    assert saved['collections'][0]['attributeStatus'] == 'error'
    assert saved['stats']['metadataComplete'] is False
    assert saved['stats']['complete'] is False
    assert 'PRIVATE_ERROR_DETAILS' not in importer.OUTPUT.read_text()


def test_main_returns_nonzero_for_incomplete_export(monkeypatch, capsys):
    async def incomplete(_):
        return False

    monkeypatch.setattr(importer, 'run', incomplete)
    monkeypatch.setattr(importer.sys, 'argv', ['telegram_import.py'])
    monkeypatch.setattr(importer.sys, 'stdout', SimpleNamespace(reconfigure=lambda **kwargs: None))
    assert importer.main() == 2


def test_export_public_fields_exclude_document_secrets(export_setup):
    assert asyncio.run(importer.export(export_setup.client)) is True
    saved = read_export()
    assert saved['stats']['complete'] is True
    assert saved['collections'][0]['attributes']['models'][0]['id'] == '77'
    for path in (importer.OUTPUT, importer.PUBLIC / 'catalog.json'):
        payload = path.read_text(encoding='utf-8')
        for forbidden in ('access_hash', 'file_reference', '987654321', 'PRIVATE_FILE_REFERENCE'):
            assert forbidden not in payload


def test_export_repairs_nonempty_corrupt_media(export_setup):
    from PIL import Image

    path = importer.PUBLIC / 'media' / '77.webp'
    path.parent.mkdir(parents=True)
    path.write_bytes(b'corrupt but nonempty image')
    assert asyncio.run(importer.export(export_setup.client)) is True
    assert export_setup.client.downloads == 1
    with Image.open(path) as repaired:
        assert repaired.format == 'WEBP'
        repaired.verify()
    assert not list(importer.PUBLIC.rglob('*.tmp'))
    assert read_export()['stats']['missingMedia'] == 0


def test_failed_refresh_cannot_report_complete(export_setup):
    previous = export_setup.seed_previous()
    export_setup.client.failure = RuntimeError('refresh failed')
    complete = asyncio.run(importer.export(export_setup.client))
    saved = read_export()
    assert saved['collections'][0]['attributes'] == previous['attributes']
    assert saved['collections'][0]['refreshStatus'] == 'error'
    assert complete is False
    assert saved['stats']['complete'] is False


def test_resume_retries_failed_refresh_instead_of_clearing_marker(export_setup):
    previous = export_setup.seed_previous()
    previous.update(upgradeAvailable=True, refreshStatus='error')
    importer.save_manifest({'schema': 1, 'collections': [previous], 'halloweenCatalogIds': []})
    export_setup.client.failure = RuntimeError('still unavailable')
    assert asyncio.run(importer.export(export_setup.client)) is False
    saved = read_export()
    assert saved['collections'][0]['refreshStatus'] == 'error'
    assert saved['stats']['metadataComplete'] is False
