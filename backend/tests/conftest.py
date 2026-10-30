import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def migrate_test_database(settings, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', settings.database_url)
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', settings.bot_token)
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.upgrade(config, 'head')
