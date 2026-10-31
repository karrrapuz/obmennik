"""Local import setup only; no Telegram connection or private file reads."""
import asyncio
from types import SimpleNamespace

import pytest

from app.config import Settings
from scripts import telegram_catalog as cli


@pytest.fixture
def settings(tmp_path):
    return Settings(bot_token='123456:CLI_TEST_ONLY',
                    database_url=f"sqlite:///{(tmp_path / 'cli.sqlite3').as_posix()}", allowed_origins=())


def test_missing_configuration_is_sanitized(tmp_path):
    with pytest.raises(ValueError, match='missing'):
        cli.load_credentials(tmp_path / 'missing')


@pytest.mark.parametrize('api_id,api_hash', [('', ''), ('abc', 'a' * 32),
    ('0', 'a' * 32), ('2147483648', 'a' * 32), ('123', 'secret-invalid'), ('123', 'a' * 31)])
def test_invalid_configuration_never_echoes_values(tmp_path, api_id, api_hash):
    path = tmp_path / '.env.telegram'
    path.write_text(f'TELEGRAM_API_ID={api_id}\nTELEGRAM_API_HASH={api_hash}\n', encoding='utf-8')
    with pytest.raises(ValueError) as error:
        cli.load_credentials(path)
    if api_hash:
        assert api_hash not in str(error.value)


def test_configuration_check_has_no_network_or_session(tmp_path, monkeypatch, capsys):
    path = tmp_path / '.env.telegram'
    api_hash = 'a' * 32
    path.write_text(f'TELEGRAM_API_ID=12345\nTELEGRAM_API_HASH={api_hash}\n', encoding='utf-8')
    monkeypatch.setattr(cli, 'CREDENTIALS', path)
    session = tmp_path / 'session' / 'test.session'
    monkeypatch.setattr(cli, 'SESSION', session)
    credentials = cli.load_credentials(path)
    assert credentials.api_id == 12345
    assert api_hash not in repr(credentials)
    assert cli.main(['check-config']) == 0
    assert api_hash not in capsys.readouterr().out
    assert not session.parent.exists()


class NeedPassword(Exception):
    pass


class Client:
    def __init__(self, authorized=False, need_password=False, bot=False):
        self.authorized = authorized
        self.need_password = need_password
        self.bot = bot
        self.calls = []

    async def connect(self): self.calls.append('connect')
    async def disconnect(self): self.calls.append('disconnect')
    async def is_user_authorized(self): return self.authorized
    async def get_me(self): return SimpleNamespace(bot=self.bot)

    async def send_code_request(self, phone):
        self.calls.append('send_code')
        return SimpleNamespace(phone_code_hash='NOT_PRINTED')

    async def sign_in(self, **kwargs):
        self.calls.append('password' if 'password' in kwargs else 'code')
        if self.need_password and 'password' not in kwargs:
            raise NeedPassword()

    async def __call__(self, request):
        self.calls.append(('request', request))
        return SimpleNamespace(gifts=[1, 2, 3])


def test_status_does_not_prompt_or_request_code():
    client = Client()
    def no_prompt(_): raise AssertionError('Unexpected secret prompt')
    assert asyncio.run(cli.run_client(client, 'status', NeedPassword, prompt=no_prompt)) == 2
    assert client.calls == ['connect', 'disconnect']


def test_login_with_two_factor_is_explicit_and_sanitized(capsys):
    client = Client(need_password=True)
    answers = iter(['+12345678901', '12345', 'PRIVATE_PASSWORD'])
    assert asyncio.run(cli.run_client(client, 'login', NeedPassword, prompt=lambda _: next(answers))) == 0
    assert client.calls == ['connect', 'send_code', 'code', 'password', 'disconnect']
    output = capsys.readouterr().out
    assert all(secret not in output for secret in ['12345678901', '12345', 'PRIVATE_PASSWORD', 'NOT_PRINTED'])


def test_existing_session_never_requests_another_code():
    client = Client(authorized=True)
    assert asyncio.run(cli.run_client(client, 'login', NeedPassword)) == 0
    assert client.calls == ['connect', 'disconnect']


def test_preview_only_calls_supplied_read_request(capsys):
    client = Client(authorized=True)
    request = object()
    assert asyncio.run(cli.run_client(client, 'preview', NeedPassword, request)) == 0
    assert client.calls == ['connect', ('request', request), 'disconnect']
    assert '3 gift types' in capsys.readouterr().out


def test_bot_session_is_rejected_and_disconnected():
    client = Client(authorized=True, bot=True)
    with pytest.raises(ValueError, match='user account'):
        asyncio.run(cli.run_client(client, 'preview', NeedPassword, object()))
    assert client.calls == ['connect', 'disconnect']


def test_invalid_phone_disconnects_without_requesting_code():
    client = Client()
    with pytest.raises(ValueError, match='Phone is empty or invalid'):
        asyncio.run(cli.run_client(client, 'login', NeedPassword, prompt=lambda _: 'bad-phone'))
    assert client.calls == ['connect', 'disconnect']


def test_phone_prompt_can_be_visible_separately_from_secrets(capsys):
    client = Client()
    phone_calls = []
    def phone_input(message):
        phone_calls.append(message)
        return '+1 (234) 567-8901'
    assert asyncio.run(cli.run_client(client, 'login', NeedPassword,
        prompt=lambda _: '12345', phone_prompt=phone_input)) == 0
    assert len(phone_calls) == 1 and 'visible' in phone_calls[0]
    assert client.calls == ['connect', 'send_code', 'code', 'disconnect']
    assert '12345678901' not in capsys.readouterr().out


@pytest.mark.parametrize('name', list(cli.ERROR_MESSAGES))
def test_known_errors_use_constant_messages_without_payload(name):
    error = type(name, (Exception,), {})('PRIVATE_HASH_PHONE_CODE_PASSWORD')
    assert cli.safe_failure(error) == cli.ERROR_MESSAGES[name]
    assert 'PRIVATE' not in cli.safe_failure(error)


def test_unknown_error_never_echoes_payload():
    assert 'PRIVATE' not in cli.safe_failure(ValueError('PRIVATE_HASH_PHONE_CODE_PASSWORD'))


class QR:
    url = 'tg://login?token=TEST_ONLY_NOT_A_REAL_TOKEN'

    def __init__(self, results):
        self.results = iter(results)
        self.waiting = False
        self.refreshes = 0

    async def wait(self):
        self.waiting = True
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result

    async def recreate(self):
        self.refreshes += 1
        self.waiting = False


class QRClient(Client):
    def __init__(self, qr):
        super().__init__()
        self.qr = qr

    async def qr_login(self):
        self.calls.append('qr_login')
        return self.qr

    async def set_receive_updates(self, value):
        self.calls.append(('updates', value))


def test_qr_login_never_requests_phone_or_code(capsys):
    qr = QR([object()])
    client = QRClient(qr)
    shown, cleared = [], []
    def show(url):
        assert qr.waiting
        shown.append(url)
    def no_prompt(_): raise AssertionError('Unexpected phone/code prompt')
    assert asyncio.run(cli.run_client(client, 'qr-login', NeedPassword, prompt=no_prompt,
        show_qr=show, clear_qr=lambda: cleared.append(True))) == 0
    assert shown == [qr.url] and cleared
    assert client.calls == ['connect', 'qr_login', ('updates', False), 'disconnect']
    assert qr.url not in capsys.readouterr().out


def test_qr_refreshes_after_token_timeout_and_cleans_up():
    qr = QR([TimeoutError(), object()])
    client = QRClient(qr)
    shown, cleared = [], []
    asyncio.run(cli.qr_sign_in(client, NeedPassword, lambda _: '', shown.append, lambda: cleared.append(True)))
    assert len(shown) == 2 and qr.refreshes == 1 and cleared


def test_qr_two_factor_is_hidden_and_cleans_up(capsys):
    qr = QR([NeedPassword()])
    client = QRClient(qr)
    cleared = []
    asyncio.run(cli.qr_sign_in(client, NeedPassword, lambda _: 'PRIVATE_2FA', lambda _: None,
                              lambda: cleared.append(True)))
    assert client.calls == ['qr_login', 'password']
    assert cleared and 'PRIVATE_2FA' not in capsys.readouterr().out


def test_qr_render_failure_still_cleans_up():
    qr = QR([object()])
    cleared = []
    def fail(_): raise OSError('TEST_ONLY')
    with pytest.raises(OSError):
        asyncio.run(cli.qr_sign_in(QRClient(qr), NeedPassword, lambda _: '', fail,
                                  lambda: cleared.append(True)))
    assert cleared


def test_qr_page_is_self_contained_and_removed(tmp_path):
    pytest.importorskip('qrcode')
    path = tmp_path / 'local' / 'login-qr.html'
    cli.write_qr_page(QR.url, path)
    content = path.read_text(encoding='utf-8')
    assert 'data:image/png;base64,' in content
    assert 'default-src' in content
    assert 'https://' not in content and QR.url not in content
    cli.close_qr_page(path)
    assert not path.exists()
