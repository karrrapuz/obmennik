from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.integrations import (DisabledPaymentProvider, IntegrationUnavailable,
                              PaymentState, VerifiedPayment, demo_route)
from app.main import create_app
from test_auth import BOT_TOKEN, bearer, login


@pytest.fixture
def settings(tmp_path):
    return Settings(BOT_TOKEN, f"sqlite:///{(tmp_path / 'integration.db').as_posix()}", ())


def test_live_status_and_webhooks_fail_closed(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/integrations/status').status_code == 401
        auth = bearer(login(client)['access_token'])
        payload = client.get('/api/integrations/status', headers=auth).json()
        assert payload['financial_asset'] == 'DEMO_TON'
        assert not any(payload[key] for key in ('real_payments', 'real_gift_transfers', 'real_loans'))
        for provider in ('ton', 'cryptobot', 'telegram', 'unknown'):
            assert client.post(f'/api/webhooks/{provider}', json={'paid': True}).status_code == 503


def test_production_does_not_seed_or_mutate_demo_finances(settings):
    settings = replace(settings, deployment_mode='production', gift_provider_mode='disabled')
    with TestClient(create_app(settings)) as client:
        auth = bearer(login(client)['access_token'])
        for path in ('wallet', 'inventory', 'loans', 'referrals', 'trades/quotes/anything'):
            assert client.get('/api/' + path, headers=auth).status_code == 503
        for path in ('wallet/demo-topup', 'inventory/demo-deposit', 'loans/create', 'trades/execute', 'referrals/claim'):
            assert client.post('/api/' + path, headers=auth, json={}).status_code == 503
        assert client.get('/api/me', headers=auth).status_code == 200
        assert client.get('/api/integrations/status', headers=auth).json()['financial_asset'] is None
        from sqlalchemy import text
        with client.app.state.engine.connect() as db:
            for table in ('wallet_accounts', 'wallet_transactions', 'inventory_gifts'):
                assert db.execute(text(f'SELECT count(*) FROM {table}')).scalar() == 0


@pytest.mark.parametrize('mode', ['live', '', 'Demo'])
def test_unknown_deployment_modes_rejected(settings, mode):
    with pytest.raises(ValueError):
        replace(settings, deployment_mode=mode)


def test_production_requires_disabled_custody(settings):
    with pytest.raises(ValueError):
        replace(settings, deployment_mode='production')


@pytest.mark.parametrize('ids', [(0,), (-1,), (True,), ('123',), (2**63,)])
def test_admin_ids_strict(settings, ids):
    with pytest.raises(ValueError):
        replace(settings, admin_user_ids=ids)


def test_disabled_adapter_cannot_verify_any_callback():
    with pytest.raises(IntegrationUnavailable):
        DisabledPaymentProvider().verify_webhook(b'{"paid":true}', {})


@pytest.mark.parametrize('amount', [True, 0, -1, 1.5, '1', 2**63])
def test_receipts_require_exact_bounded_amount(amount):
    with pytest.raises(ValueError):
        VerifiedPayment('cryptobot', 'evt1', 'invoice1', 'TON', amount, PaymentState.CONFIRMED)


def test_receipt_and_route_boundaries():
    receipt = VerifiedPayment('cryptobot', 'evt1', 'invoice1', 'TON', 1, PaymentState.CONFIRMED)
    assert receipt.amount_nano == 1
    assert demo_route('/api/wallet/demo-topup')
    assert not demo_route('/api/wallets')
    assert not demo_route('/api/admin/wallet')


def test_security_headers(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get('/api/health')
        assert response.headers['X-Content-Type-Options'] == 'nosniff'
        assert response.headers['Referrer-Policy'] == 'no-referrer'


def test_request_body_limit_and_encoding(settings):
    with TestClient(create_app(settings)) as client:
        response = client.post('/api/auth/telegram', content=b'x' * 65537)
        assert response.status_code == 413
        assert response.headers['X-Content-Type-Options'] == 'nosniff'
        assert client.post('/api/auth/telegram', content=b'abc', headers={'Content-Encoding': 'gzip'}).status_code == 415
        assert client.post('/api/auth/telegram', json={}).status_code == 422


def test_chunked_request_limit(settings):
    with TestClient(create_app(settings)) as client:
        def chunks():
            for _ in range(70):
                yield b'x' * 1000
        assert client.post('/api/auth/telegram', content=chunks()).status_code == 413
