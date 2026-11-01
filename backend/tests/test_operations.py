import subprocess
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.operations import readiness, register_operations_routes
from scripts.backup_database import backup_database
from test_auth import settings  # Shared isolated migration fixture.


def test_backup_rejects_repository_destination():
    from pathlib import Path
    repository = Path(__file__).resolve().parents[2]
    with pytest.raises(ValueError, match='outside the repository'):
        backup_database('postgresql://test:test@example.com/test?sslmode=require', repository / 'unsafe.dump')


def test_admin_auth_precedes_operations_database_access():
    app = FastAPI()
    accessed = []

    def database():
        accessed.append(True)
        raise AssertionError('Unauthorized database access')

    def current_session(authorization: str | None = Header(default=None)):
        if authorization is None:
            raise HTTPException(401, 'Authentication required')
        return SimpleNamespace(user_id=int(authorization))

    register_operations_routes(app, database, current_session, {1})
    with TestClient(app) as client:
        assert client.get('/api/admin/readiness').status_code == 401
        assert client.get('/api/admin/readiness', headers={'Authorization': '2'}).status_code == 403
        assert not accessed
        assert '/api/admin/readiness' not in client.get('/openapi.json').json()['paths']


def test_readiness_schema_and_freshness_are_read_only(settings):
    import json
    from app.main import create_app
    engine = create_app(settings).state.engine
    try:
        with Session(engine) as db:
            report = readiness(db)
            assert not report['ready'] and report['checks']['schema'] == 'ok'
            assert report['checks']['ledger'] == 'not_checked_use_offline_audit'
            assert not db.new and not db.dirty and not db.deleted
        now = int(time.time())
        with engine.begin() as connection:
            connection.execute(text('UPDATE market_snapshots SET captured_at=:now, prices_json=:feed, listings_json=:listings'),
                               {'now': now, 'feed': json.dumps({'capturedAt': now, 'validUntil': now + 60, 'complete': True}), 'listings': '{}'})
        with Session(engine) as db:
            assert readiness(db, settings)['ready']
            assert not readiness(db, settings)['live_ready']
            production = SimpleNamespace(deployment_mode='production')
            report = readiness(db, production)
            assert report['operational_ready'] and not report['ready'] and not report['live_ready']
            assert not readiness(db)['ready']  # Missing mode is fail-closed.
        with engine.begin() as connection:
            connection.execute(text('UPDATE market_snapshots SET captured_at=:now, prices_json=:feed'),
                               {'now': now - 120, 'feed': json.dumps({'capturedAt': now - 120, 'validUntil': now - 60, 'complete': True})})
        with Session(engine) as db:
            report = readiness(db)
            assert not report['ready'] and report['checks']['market'] == 'stale'
        with engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num='unknown'"))
        with Session(engine) as db:
            assert readiness(db)['checks']['schema'] == 'mismatch'
    finally:
        engine.dispose()


@pytest.mark.parametrize('ready,status', [(True, 200), (False, 503)])
def test_admin_response_status_and_private_headers(monkeypatch, ready, status):
    app = FastAPI()
    monkeypatch.setattr('app.operations.readiness', lambda db, settings: {'ready': ready, 'checks': {}})
    register_operations_routes(app, lambda: None, lambda: SimpleNamespace(user_id=1), {1})
    with TestClient(app) as client:
        response = client.get('/api/admin/readiness')
    assert response.status_code == status
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'


@pytest.mark.parametrize('admins', [{True}, {'1'}, {0}, {-1}])
def test_invalid_admin_allowlist_rejected(admins):
    with pytest.raises(ValueError):
        register_operations_routes(FastAPI(), lambda: None, lambda: None, admins)


def test_readiness_redacts_driver_errors():
    engine = create_engine('sqlite://')
    try:
        with Session(engine) as db:
            report = readiness(db)
        assert not report['ready']
        assert 'SELECT' not in str(report) and 'sqlite' not in str(report)
    finally:
        engine.dispose()


def test_backup_credentials_only_in_environment_and_exclusive_output(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv('PGSERVICE', 'untrusted-service')

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        kwargs['stdout'].write(b'PGDMP-test')

    monkeypatch.setattr(subprocess, 'run', run)
    output = tmp_path / 'backup.dump'
    backup_database('postgresql://operator:secret@db.example/test?sslmode=require', output)
    argv, kwargs = calls[0]
    assert argv == ['pg_dump', '--format=custom', '--no-password']
    assert kwargs['env']['PGPASSWORD'] == 'secret'
    assert kwargs['env']['PGSSLMODE'] == 'require'
    assert 'PGSERVICE' not in kwargs['env']
    assert kwargs['stderr'] == subprocess.DEVNULL and kwargs['timeout'] == 3600
    with pytest.raises(FileExistsError):
        backup_database('postgresql://operator:secret@db.example/test', output)
    assert output.read_bytes() == b'PGDMP-test' and len(calls) == 1


@pytest.mark.parametrize('failure', [subprocess.TimeoutExpired('pg_dump', 1), subprocess.CalledProcessError(1, 'pg_dump')])
def test_failed_backup_removes_only_new_partial_file(tmp_path, monkeypatch, failure):
    def run(*args, **kwargs):
        kwargs['stdout'].write(b'partial')
        raise failure
    monkeypatch.setattr(subprocess, 'run', run)
    output = tmp_path / 'failed.dump'
    with pytest.raises(type(failure)):
        backup_database('postgresql://user:secret@db.example/test', output)
    assert not output.exists()


@pytest.mark.parametrize('url', ['sqlite:///test', 'postgresql://db/test?sslmode=disable',
                                 'postgresql://db/test?options=unsafe', 'postgresql://db/host%3Devil'])
def test_backup_rejects_unsafe_connection_configuration(tmp_path, url):
    with pytest.raises(ValueError):
        backup_database(url, tmp_path / 'never.dump')
    assert not (tmp_path / 'never.dump').exists()
