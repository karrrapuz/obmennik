"""Dedicated cloud packaging tests; synthetic session only, no network or secret files."""
import asyncio
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from telethon.crypto import AuthKey
from telethon.sessions import StringSession

from app.config import Settings
from scripts import market_worker as worker


@pytest.fixture
def settings(tmp_path):
    return Settings(bot_token='12345:test', database_url=f'sqlite:///{(tmp_path / "worker.sqlite").as_posix()}', allowed_origins=())


@pytest.fixture
def worker_env(tmp_path):
    session = StringSession()
    session.set_dc(2, '149.154.167.51', 443)
    session.auth_key = AuthKey(bytes(range(256)))
    return {'MARKET_WORKER_ENABLED': 'true', 'MARKET_ALLOW_CLOUD_SESSION': 'true',
            'MARKET_SESSION_ACCOUNT': 'dedicated', 'TELEGRAM_API_ID': '12345',
            'TELEGRAM_API_HASH': 'a' * 32, 'TELEGRAM_SESSION_STRING': session.save(),
            'MARKET_API_URL': 'https://test.invalid', 'MARKET_INGEST_KEY': 'fake-ingest-secret-' * 3,
            'MARKET_WORK_DIR': str(tmp_path / 'spool')}


@pytest.fixture
def worker_settings(worker_env):
    return worker.WorkerSettings.from_env(worker_env)


def test_valid_env_never_loads_local_files(worker_env, monkeypatch):
    monkeypatch.setattr('dotenv.load_dotenv', lambda *a, **k: pytest.fail('Local dotenv read'))
    monkeypatch.setattr(worker.collector, 'load_credentials', lambda *a: pytest.fail('Local credentials read'))
    result = worker.WorkerSettings.from_env(worker_env)
    assert result.interval == 3600 and result.pages == 2 and result.cycle_timeout == 1800
    assert result.max_failures == 3
    assert result.push_configuration[0] == 'https://test.invalid/api/internal/market/snapshots'
    assert worker_env['TELEGRAM_SESSION_STRING'] not in repr(result)
    assert worker_env['MARKET_INGEST_KEY'] not in repr(result)


@pytest.mark.parametrize('name,value', [
    ('MARKET_WORKER_ENABLED', ''), ('MARKET_ALLOW_CLOUD_SESSION', 'false'),
    ('MARKET_SESSION_ACCOUNT', 'personal'), ('TELEGRAM_API_ID', '2147483648'),
    ('TELEGRAM_API_HASH', 'not-a-hash'), ('TELEGRAM_SESSION_STRING', '1' + 'A' * 101),
    ('TELEGRAM_SESSION_STRING', ''), ('MARKET_INTERVAL_SECONDS', '3599'), ('MARKET_PAGES', '4'),
    ('MARKET_CYCLE_TIMEOUT_SECONDS', '3601'), ('MARKET_MAX_FAILURES', '11'),
    ('MARKET_API_URL', 'http://test.invalid'), ('MARKET_API_URL', 'https://secret@test.invalid'),
    ('MARKET_API_URL', 'https://test.invalid?'), ('MARKET_INGEST_KEY', 'short'),
    ('MARKET_WORK_DIR', 'relative-directory')])
def test_invalid_env_fails_closed(worker_env, name, value):
    worker_env[name] = value
    with pytest.raises(worker.WorkerConfigurationError):
        worker.WorkerSettings.from_env(worker_env)


def test_worker_disabled_without_any_configuration():
    with pytest.raises(worker.WorkerConfigurationError):
        worker.WorkerSettings.from_env({})


class FakeClient:
    def __init__(self, events, authorized=True):
        self.events, self.authorized = events, authorized

    async def connect(self):
        self.events.append('connect')

    async def is_user_authorized(self):
        self.events.append('authorized')
        return self.authorized

    async def disconnect(self):
        self.events.append('disconnect')


def test_once_disconnects_before_upload_and_restores_local_paths(worker_settings, monkeypatch):
    events = []
    original = worker.collector.OUTPUT

    async def collect(client, *, pages, listings):
        events.append('collect')
        assert pages == 2 and listings is True
        assert worker.collector.OUTPUT.parent == worker_settings.work_dir
        return {'complete': True}

    async def push(feed, configuration):
        events.append('push')
        assert feed == {'complete': True} and configuration == worker_settings.push_configuration

    monkeypatch.setattr(worker.collector, 'collect', collect)
    assert asyncio.run(worker.run_worker(worker_settings, once=True,
        client_factory=lambda _: FakeClient(events), push=push)) == 0
    assert events == ['connect', 'authorized', 'collect', 'disconnect', 'push']
    assert worker.collector.OUTPUT == original


def test_unauthorized_stops_without_login_or_collect(worker_settings, monkeypatch):
    events = []
    monkeypatch.setattr(worker.collector, 'collect', lambda *a, **k: pytest.fail('Unauthorized collection'))
    assert asyncio.run(worker.run_worker(worker_settings,
        client_factory=lambda _: FakeClient(events, authorized=False))) == 2
    assert events == ['connect', 'authorized', 'disconnect']


def test_incomplete_feed_never_uploads(worker_settings, monkeypatch):
    async def collect(*a, **k):
        return {'complete': False}

    monkeypatch.setattr(worker.collector, 'collect', collect)
    assert asyncio.run(worker.run_worker(worker_settings, once=True,
        client_factory=lambda _: FakeClient([]), push=lambda *a: pytest.fail('Partial upload'))) == 2


@pytest.mark.parametrize('flood_wait', [False, True])
def test_failure_retries_are_capped_and_respect_interval(worker_settings, monkeypatch, capsys, flood_wait):
    from telethon.errors import FloodWaitError
    events, delays = [], []

    async def collect(*a, **k):
        if flood_wait:
            raise FloodWaitError(request=None, capture=7200)
        raise RuntimeError('PRIVATE_SESSION_AND_KEY')

    async def wait(awaitable, *, timeout):
        awaitable.close()
        delays.append(timeout)
        raise TimeoutError()

    monkeypatch.setattr(worker.collector, 'collect', collect)
    monkeypatch.setattr(worker.asyncio, 'wait_for', wait)
    assert asyncio.run(worker.run_worker(worker_settings, client_factory=lambda _: FakeClient(events))) == 2
    assert events.count('connect') == 3 and events.count('disconnect') == 3
    assert delays == ([7201, 7201] if flood_wait else [3600, 3600])
    assert 'PRIVATE_SESSION_AND_KEY' not in capsys.readouterr().out


def test_active_cycle_stops_and_disconnects_without_upload(worker_settings, monkeypatch):
    events = []

    async def exercise():
        stop = asyncio.Event()

        async def collect(*a, **k):
            stop.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(worker.collector, 'collect', collect)
        return await worker.run_worker(worker_settings, stop,
            client_factory=lambda _: FakeClient(events), push=lambda *a: pytest.fail('Upload after stop'))

    assert asyncio.run(exercise()) == 0
    assert events[-1] == 'disconnect'
    with worker.spool_lock(worker_settings.work_dir):
        pass


def test_timeout_closes_session(worker_settings, monkeypatch):
    events = []
    actual_timeout = asyncio.timeout

    async def collect(*a, **k):
        await asyncio.Event().wait()

    monkeypatch.setattr(worker.collector, 'collect', collect)
    monkeypatch.setattr(worker.asyncio, 'timeout', lambda delay: actual_timeout(0.01 if delay == 60 else delay))
    assert asyncio.run(worker.run_worker(replace(worker_settings, cycle_timeout=60), once=True,
        client_factory=lambda _: FakeClient(events))) == 2
    assert events[-1] == 'disconnect'


def test_already_stopped_worker_opens_no_session(worker_settings):
    async def exercise():
        stop = asyncio.Event()
        stop.set()
        return await worker.run_worker(worker_settings, stop,
            client_factory=lambda _: pytest.fail('Session opened after stop'))

    assert asyncio.run(exercise()) == 0


def test_spool_lock_prevents_overlap_and_releases(worker_settings):
    with worker.spool_lock(worker_settings.work_dir):
        with pytest.raises(worker.WorkerConfigurationError):
            with worker.spool_lock(worker_settings.work_dir):
                pytest.fail('Overlapping worker acquired spool')
    with worker.spool_lock(worker_settings.work_dir):
        pass


def test_client_uses_only_in_memory_string_session(worker_settings, monkeypatch):
    captured = {}

    def client(session, api_id, api_hash, **kwargs):
        assert isinstance(session, StringSession)
        captured.update(kwargs)
        return SimpleNamespace(session=session)

    monkeypatch.setattr('telethon.TelegramClient', client)
    result = worker.make_client(worker_settings)
    assert result.session.save_entities is False
    assert captured['receive_updates'] is False and captured['auto_reconnect'] is False
    assert captured['request_retries'] == 1 and captured['connection_retries'] == 1


def test_signal_handlers_set_stop_and_are_removed(worker_settings, monkeypatch):
    async def exercise():
        loop = asyncio.get_running_loop()
        installed, removed = {}, []
        monkeypatch.setattr(loop, 'add_signal_handler', lambda sig, fn: installed.update({sig: fn}))
        monkeypatch.setattr(loop, 'remove_signal_handler', lambda sig: removed.append(sig))

        async def run(settings, stop, *, once):
            installed[worker.signal.SIGTERM]()
            assert stop.is_set() and once
            return 0

        monkeypatch.setattr(worker, 'run_worker', run)
        assert await worker.serve(worker_settings, once=True) == 0
        assert set(installed) == set(removed) == {worker.signal.SIGINT, worker.signal.SIGTERM}

    asyncio.run(exercise())


def test_image_has_no_broad_copy_or_secret_arguments():
    dockerfile = (Path(__file__).resolve().parents[1] / 'Dockerfile.market').read_text()
    assert 'COPY . ' not in dockerfile and 'COPY ./' not in dockerfile
    assert 'ARG TELEGRAM' not in dockerfile and 'ENV TELEGRAM' not in dockerfile
    assert 'USER 10001:10001' in dockerfile
    assert 'COPY data/catalog-telegram.json' in dockerfile
    assert 'ENTRYPOINT ["python", "-m", "scripts.market_worker"]' in dockerfile


def test_check_config_does_not_start_worker_or_write_files(worker_settings, monkeypatch, capsys):
    monkeypatch.setattr(worker.WorkerSettings, 'from_env', lambda: worker_settings)
    monkeypatch.setattr(worker, 'serve', lambda *a: pytest.fail('Check-config activated worker'))
    monkeypatch.setattr(worker.os, 'umask', lambda _: None)
    monkeypatch.setattr(worker.logging, 'disable', lambda _: None)
    assert worker.main(['--check-config']) == 0
    assert not worker_settings.work_dir.exists()
    assert 'activation not performed' in capsys.readouterr().out


def test_main_error_never_echoes_secret_or_exception_message(monkeypatch, capsys):
    def invalid():
        raise RuntimeError('PRIVATE_SESSION_KEY_VALUE')

    monkeypatch.setattr(worker.WorkerSettings, 'from_env', invalid)
    monkeypatch.setattr(worker.os, 'umask', lambda _: None)
    monkeypatch.setattr(worker.logging, 'disable', lambda _: None)
    assert worker.main(['--check-config']) == 2
    assert 'PRIVATE_SESSION_KEY_VALUE' not in capsys.readouterr().out
