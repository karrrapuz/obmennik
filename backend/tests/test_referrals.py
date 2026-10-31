from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.referral_models import ReferralBinding, ReferralReward
from app.trade_models import TradeQuote
from app.wallet_models import WalletAccount
from app.ledger import CAP, post_transfer
from app.ledger_audit import audit_ledger
from test_auth import BOT_TOKEN, USER, bearer, fields_for, signed


@pytest.fixture
def settings(tmp_path):
    return Settings(bot_token=BOT_TOKEN, database_url=f'sqlite:///{(tmp_path / "referrals.sqlite").as_posix()}',
                    allowed_origins=(), telegram_bot_username='giftmoney_test_bot')


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def actor(client, identity, code=None):
    fields = fields_for({**USER, 'id': identity})
    if code is not None:
        fields['start_param'] = 'ref_' + code
    data = ok(client.post('/api/auth/telegram', json={'init_data': signed(fields)}))
    return bearer(data['access_token']), data['user']['referral_code']


def summary(client, headers):
    return ok(client.get('/api/referrals', headers=headers))


def prepared(client, headers):
    inventory = ok(client.get('/api/inventory', headers=headers))
    ok(client.post('/api/wallet/demo-topup', headers={**headers, 'Idempotency-Key': 'fund'},
                   json={'amount_nano': '1000000000000', 'source': 'wallet'}))
    return ok(client.post('/api/trades/quote', headers=headers, json={
        'offered_ids': [inventory['inventory'][0]['id']], 'received_ids': [inventory['catalog'][1]['id']]}))


def execute(client, headers, quote, key='execute'):
    return client.post('/api/trades/execute', headers={**headers, 'Idempotency-Key': key}, json={'quote_id': quote['id']})


def claim(client, headers, key='claim'):
    return client.post('/api/referrals/claim', headers={**headers, 'Idempotency-Key': key}, json={})


def test_signed_first_launch_binding_is_immutable_and_private(client):
    first, code = actor(client, 1)
    actor(client, 2, code)
    second, second_code = actor(client, 3)
    actor(client, 2, second_code)
    actor(client, 3, code)  # Existing unbound accounts cannot be assigned later.
    actor(client, 1, code)  # Self referral is ignored.
    value = summary(client, first)
    assert value['invited_count'] == 1
    assert value['available_nano'] == '0'
    assert value['invite_url'] == f'https://t.me/giftmoney_test_bot?startapp=ref_{code}'
    assert summary(client, second)['invited_count'] == 0
    assert client.get('/api/referrals').status_code == 401
    assert claim(client, first).status_code == 409  # The legacy 5 TON seed is not earned income.
    with Session(client.app.state.engine) as db:
        assert db.get(ReferralBinding, 2).referrer_id == 1
        assert db.get(ReferralBinding, 3) is None


def test_referral_requires_signed_parameter(client):
    referrer, code = actor(client, 1)
    raw = signed(fields_for({**USER, 'id': 2})) + '&start_param=ref_' + code
    assert client.post('/api/auth/telegram', json={'init_data': raw}).status_code == 401
    ok(client.post('/api/auth/telegram?ref=' + code, json={'init_data': signed(fields_for({**USER, 'id': 2}))}))
    assert summary(client, referrer)['invited_count'] == 0


@pytest.mark.parametrize('promo_first', [False, True])
def test_confirmed_turnover_rewards_once_and_claims_exclude_promo(client, promo_first):
    referrer, code = actor(client, 1)
    buyer, _ = actor(client, 2, code)
    quote = prepared(client, buyer)
    assert summary(client, referrer)['earned_nano'] == '0'
    expected = min(int(quote['received_nano']) * 200 // 10000, int(quote['fee_nano']))
    ok(execute(client, buyer, quote))
    ok(execute(client, buyer, quote, 'retry-with-new-key'))
    assert summary(client, referrer)['available_nano'] == str(expected)
    assert summary(client, referrer)['turnover_nano'] == quote['received_nano']
    promo = lambda: ok(client.post('/api/wallet/demo-referral', headers={**referrer, 'Idempotency-Key': 'promo'}, json={}))
    if promo_first:
        assert promo()['balance_nano'] == '5000000000'
        assert summary(client, referrer)['available_nano'] == str(expected)
    result = ok(claim(client, referrer))
    assert result['referral']['available_nano'] == '0'
    assert result['wallet']['balance_nano'] == str(expected + (5000000000 if promo_first else 0))
    replay = ok(claim(client, referrer))
    assert replay == result
    assert claim(client, referrer, 'new-key').status_code == 409
    if not promo_first:
        assert promo()['balance_nano'] == str(expected + 5000000000)
    with Session(client.app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(ReferralReward)) == 1
    with client.app.state.engine.connect() as connection:
        assert audit_ledger(connection)['ok']


@pytest.mark.parametrize('markup,rate', [(0, 200), (100, 200), (500, 300), (500, 0)])
def test_reward_is_capped_by_frozen_fee_and_rate(settings, markup, rate):
    with TestClient(create_app(replace(settings, trade_markup_bps=markup, referral_rate_bps=rate))) as client:
        referrer, code = actor(client, 1)
        buyer, _ = actor(client, 2, code)
        quote = prepared(client, buyer)
        expected = min(int(quote['received_nano']) * rate // 10000, int(quote['fee_nano']))
        ok(execute(client, buyer, quote))
        assert int(summary(client, referrer)['earned_nano']) == expected
        assert expected <= int(quote['fee_nano'])
        assert summary(client, referrer)['turnover_nano'] == quote['received_nano']


def test_late_failure_rolls_back_buyer_and_referrer_atomically(client, monkeypatch):
    from app import trades
    referrer, code = actor(client, 1)
    buyer, _ = actor(client, 2, code)
    before = summary(client, referrer)
    quote = prepared(client, buyer)
    original = trades.inventory_snapshot
    monkeypatch.setattr(trades, 'inventory_snapshot', lambda *args: (_ for _ in ()).throw(RuntimeError('snapshot failed')))
    assert execute(client, buyer, quote).status_code == 500
    monkeypatch.setattr(trades, 'inventory_snapshot', original)
    assert summary(client, referrer) == before
    with Session(client.app.state.engine) as db:
        assert db.get(ReferralReward, quote['id']) is None
        assert db.get(TradeQuote, quote['id']).status == 'open'
    ok(execute(client, buyer, quote))
    assert int(summary(client, referrer)['earned_nano']) > 0


def test_full_referral_account_holds_reward_without_rejecting_trade(client):
    referrer, code = actor(client, 1)
    buyer, _ = actor(client, 2, code)
    summary(client, referrer)
    with Session(client.app.state.engine) as db:
        post_transfer(db, 1, '__test_fill__', 'test', 'seed', 0, 'treasury', 'referral', CAP - 5000000000)
        db.commit()
    quote = prepared(client, buyer)
    ok(execute(client, buyer, quote))
    value = summary(client, referrer)
    assert value['available_nano'] == '0'
    assert int(value['held_nano']) > 0
    with Session(client.app.state.engine) as db:
        assert db.get(TradeQuote, quote['id']).status == 'executed'
        assert db.get(ReferralReward, quote['id']).status == 'held'
        assert db.get(WalletAccount, (1, 'referral')).balance == CAP
