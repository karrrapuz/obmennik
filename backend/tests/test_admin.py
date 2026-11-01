"""Read-only admin access uses real Telegram login/session dependencies."""
import time
from dataclasses import replace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.admin import HEADERS, register_admin_routes
from app.config import Settings
from app.ledger import ensure_wallet, post_transfer
from app.loan_models import DemoLoan
from app.main import create_app
from app.models import LoginSession, User
from app.trade_models import TradeQuote
from app.wallet_models import WalletAccount, WalletTransaction
from test_auth import BOT_TOKEN, USER, bearer, login


RESOURCES = ('overview', 'users', 'loans', 'trades', 'accounts', 'ledger')
TABLES = RESOURCES[1:]


@pytest.fixture
def settings(tmp_path):
    return Settings(bot_token=BOT_TOKEN, database_url=f'sqlite:///{(tmp_path / "admin.sqlite").as_posix()}',
                    allowed_origins=())


def admin_app(settings, identities=(USER['id'],)):
    app = create_app(replace(settings, admin_user_ids=identities))
    if any(getattr(route, 'path', None) == '/api/admin/overview' for route in app.routes):
        return app
    # main intentionally does not export these closures; reuse its actual auth
    # dependency graph so expiry/revocation/signature checks remain black-box.
    me = next(route for route in app.routes if getattr(route, 'path', None) == '/api/me')
    dependencies = {item.name: item.call for item in me.dependant.dependencies}
    register_admin_routes(app, dependencies['db'], dependencies['session'], identities)
    return app


@pytest.fixture
def client(settings):
    with TestClient(admin_app(settings)) as client:
        yield client


@pytest.fixture
def authenticated(client):
    return bearer(login(client)['access_token'])


def seed(client):
    now = int(time.time())
    with Session(client.app.state.engine) as db:
        for identity in range(1, 8):
            db.add(User(id=identity, first_name='PRIVATE_FIRST_NAME', last_name='PRIVATE_LAST_NAME',
                        username='PRIVATE_USERNAME', photo_url='https://private.example/avatar',
                        referral_code=f'PRIVATE_REFERRAL_{identity}'))
        db.flush()
        for identity in range(1, 8):
            ensure_wallet(db, identity)
            transaction = post_transfer(db, identity, f'PRIVATE_KEY_{identity}', 'PRIVATE_PAYLOAD_HASH',
                          'topup', identity, 'treasury', 'wallet', identity)
            # Deliberately keep destination PII in the DB to test projection redaction.
            if isinstance(transaction, WalletTransaction):
                transaction.destination = 'PRIVATE_DESTINATION'
            db.add(DemoLoan(id=f'{identity:032x}', user_id=identity, gift_id=identity, weeks=1,
                           principal=identity * 1000000000, repayment=identity * 1200000000,
                           created_at=now, due_at=now + 86400, autopay=False,
                           status='active' if identity % 2 else 'repaid', legacy=False))
            db.add(TradeQuote(id=f'{identity:032x}', user_id=identity, expires_at=now + 60,
                              status='executed' if identity % 2 else 'open',
                              payload={'PRIVATE_QUOTE_PAYLOAD': 'PRIVATE_GIFT_METADATA'}))
        db.commit()
        db.query(WalletTransaction).update({WalletTransaction.destination: 'PRIVATE_DESTINATION'})
        db.commit()


@pytest.mark.parametrize('resource', RESOURCES)
def test_anonymous_bad_token_and_url_token_rejected(client, resource):
    endpoint = f'/api/admin/{resource}'
    for headers in ({}, bearer('unknown'), {'Authorization': 'Basic abc'}):
        response = client.get(endpoint, headers=headers)
        assert response.status_code == 401
        assert response.headers['Cache-Control'] == 'no-store'
    token = login(client)['access_token']
    assert client.get(endpoint, params={'token': token, 'access_token': token}).status_code == 401


@pytest.mark.parametrize('resource', RESOURCES)
def test_authenticated_nonadmin_denied(client, resource):
    headers = bearer(login(client, {**USER, 'id': USER['id'] + 1})['access_token'])
    response = client.get(f'/api/admin/{resource}', headers=headers)
    assert response.status_code == 403
    assert response.json() == {'detail': 'Admin access denied'}
    assert response.headers['Cache-Control'] == 'no-store'


def test_default_empty_allowlist_fails_closed(settings):
    with TestClient(admin_app(settings, ())) as client:
        headers = bearer(login(client)['access_token'])
        for resource in RESOURCES:
            assert client.get(f'/api/admin/{resource}', headers=headers).status_code == 403


@pytest.mark.parametrize('identities', [(True,), ('9876543210',), (1.0,), (0,), (-1,), (2**63,),
                                        '9876543210', [9876543210], None])
def test_allowlist_requires_strict_numeric_tuple(identities):
    with pytest.raises(ValueError, match='positive numeric'):
        register_admin_routes(FastAPI(), lambda: None, lambda: None, identities)


@pytest.mark.parametrize('state', ['expired', 'revoked'])
def test_expired_or_revoked_admin_is_not_authorized(client, authenticated, state):
    with Session(client.app.state.engine) as db:
        session = db.scalar(select(LoginSession).where(LoginSession.user_id == USER['id']))
        if state == 'expired':
            session.expires_at = int(time.time()) - 1
        else:
            session.revoked = 1
        db.commit()
    for resource in RESOURCES:
        assert client.get(f'/api/admin/{resource}', headers=authenticated).status_code == 401


@pytest.mark.parametrize('resource', TABLES)
def test_pagination_stable_bounded_and_empty(client, authenticated, resource):
    seed(client)
    first = client.get(f'/api/admin/{resource}?limit=2', headers=authenticated).json()
    second = client.get(f'/api/admin/{resource}?limit=2&offset=2', headers=authenticated).json()
    assert first['asset'] == 'DEMO_TON' and first['amount_unit'] == 'nano_DEMO_TON'
    assert first['limit'] == 2 and first['offset'] == 0
    assert len(first['items']) == 2 and first['has_more'] is True and first['next_offset'] == 2
    assert len(second['items']) == 2
    assert first['items'] != second['items']
    assert first == client.get(f'/api/admin/{resource}?limit=2', headers=authenticated).json()
    empty = client.get(f'/api/admin/{resource}?offset=10000', headers=authenticated).json()
    assert empty['items'] == [] and empty['has_more'] is False and empty['next_offset'] is None
    maximum = client.get(f'/api/admin/{resource}?limit=100', headers=authenticated)
    assert maximum.status_code == 200 and len(maximum.json()['items']) <= 100


@pytest.mark.parametrize('query', ['limit=0', 'limit=101', 'limit=-1', 'limit=abc', 'limit=1.5',
                                  'limit=true', 'offset=-1', 'offset=10001', 'offset=NaN', 'offset=1.5'])
@pytest.mark.parametrize('resource', TABLES)
def test_invalid_pagination_rejected(client, authenticated, resource, query):
    assert client.get(f'/api/admin/{resource}?{query}', headers=authenticated).status_code == 422


def test_readonly_projection_units_overview_and_balanced_ledger(client, authenticated):
    seed(client)
    statements = []

    def observe(connection, cursor, statement, parameters, context, many):
        statements.append(statement.lstrip().upper())

    event.listen(client.app.state.engine, 'before_cursor_execute', observe)
    try:
        responses = {resource: client.get(f'/api/admin/{resource}?limit=100', headers=authenticated)
                     for resource in RESOURCES}
    finally:
        event.remove(client.app.state.engine, 'before_cursor_execute', observe)
    assert all(statement.startswith('SELECT') for statement in statements)
    forbidden = ('PRIVATE_', BOT_TOKEN, authenticated['Authorization'].removeprefix('Bearer '),
                 'token_hash', 'init_hash', 'payload_hash', 'first_name', 'last_name', 'username',
                 'photo_url', 'referral_code', 'destination', 'expires_at_session')
    for response in responses.values():
        assert response.status_code == 200, response.text
        assert response.headers['Cache-Control'] == 'no-store'
        assert response.headers['X-Content-Type-Options'] == 'nosniff'
        assert all(secret not in response.text for secret in forbidden)
        assert response.json()['asset'] == 'DEMO_TON'
    overview = responses['overview'].json()
    assert overview['read_only'] is True and overview['admin_user_id'] == str(USER['id'])
    assert overview['counts']['users'] == 8
    assert overview['counts']['active_loans'] == 4 and overview['counts']['repaid_loans'] == 3
    assert overview['counts']['executed_trades'] == 4 and overview['counts']['open_quotes'] == 3
    assert overview['account_balances_nano']['wallet'] == '28'
    for item in responses['users'].json()['items']:
        assert set(item) == {'user_id', 'revision'} and isinstance(item['user_id'], str)
    for item in responses['loans'].json()['items']:
        assert isinstance(item['principal_nano'], str) and isinstance(item['repayment_nano'], str)
    for item in responses['accounts'].json()['items']:
        assert isinstance(item['balance_nano'], str)
    for item in responses['ledger'].json()['items']:
        assert isinstance(item['amount_nano'], str) and isinstance(item['created_at_ns'], str)
        assert sum(int(posting['amount_nano']) for posting in item['postings']) == 0


@pytest.mark.parametrize('resource', RESOURCES)
def test_no_write_admin_routes(client, authenticated, resource):
    for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        assert client.request(method, f'/api/admin/{resource}', headers=authenticated, json={}).status_code == 405


def test_public_shell_fixed_assets_security_headers_and_tab_scoped_token_only(client):
    for route, content_type in [('/admin', 'text/html'), ('/admin/admin.js', 'text/javascript'),
                                ('/admin/admin.css', 'text/css')]:
        response = client.get(route)
        assert response.status_code == 200 and content_type in response.headers['content-type']
        for name, expected in HEADERS.items():
            if name != 'Content-Security-Policy':
                assert response.headers[name] == expected
        policy = response.headers['Content-Security-Policy']
        for directive in ("script-src 'self'", "style-src 'self'", "connect-src 'self'",
                          "frame-ancestors 'none'", "base-uri 'none'"):
            assert directive in policy
        assert "'unsafe-inline'" not in policy and "'unsafe-eval'" not in policy
    script = client.get('/admin/admin.js').text
    for unsafe in ('localStorage', 'innerHTML', 'location.search', 'location.hash', 'document.cookie'):
        assert unsafe not in script
    assert "credentials: 'omit'" in script and "redirect: 'error'" in script
    assert 'textContent' in script and "el('token').value = ''" in script
    assert 'sessionStorage.setItem(storageKey, token)' in script
    assert 'sessionStorage.removeItem(storageKey)' in script
    assert client.get('/admin/not-a-file').status_code == 404
