import os
import sqlite3
import stat

import pytest

from scripts.telegram_session_permissions import protect_session_storage


@pytest.fixture(autouse=True)
def migrate_test_database():
    # These tests use only their own temporary SQLite file.
    pass


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")
def test_telethon_sqlite_modes(tmp_path):
    session = tmp_path / "private" / "catalog.session"
    old_mask = os.umask(0o022)
    try:
        protect_session_storage(session)
        with sqlite3.connect(session) as db:
            db.execute("CREATE TABLE example (id INTEGER)")
        assert stat.S_IMODE(session.stat().st_mode) == 0o600
        session.chmod(0o644)
        session.parent.chmod(0o755)
        protect_session_storage(session)
        assert stat.S_IMODE(session.stat().st_mode) == 0o600
        assert stat.S_IMODE(session.parent.stat().st_mode) == 0o700
    finally:
        os.umask(old_mask)


def test_storage_parent_is_created(tmp_path):
    session = tmp_path / "private" / "catalog.session"
    old_mask = os.umask(0o022)
    try:
        protect_session_storage(session)
        assert session.parent.is_dir()
        assert not session.exists()
    finally:
        os.umask(old_mask)
