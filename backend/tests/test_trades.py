"""Frozen server-priced trades and atomic gift/wallet settlement contracts."""

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.ledger import CAP
from app.main import create_app
from test_auth import BOT_TOKEN, USER, bearer, login


@pytest.fixture
def settings(tmp_path):
    return Settings(bot_token=BOT_TOKEN,
                    database_url=f"sqlite:///{(tmp_path / 'trades.sqlite3').as_posix()}",
                    allowed_origins=())


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        client.headers.update(bearer(login(client)["access_token"]))
        yield client


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def state(client):
    ok(client.get('/api/inventory'))
    wallet = ok(client.get('/api/wallet'))
    return (ok(client.get('/api/inventory')), wallet)


def quote(client, offered=None, received=None):
    inventory = ok(client.get('/api/inventory'))
    return ok(client.post('/api/trades/quote', json={
        'offered_ids': offered if offered is not None else [inventory['inventory'][0]['id']],
        'received_ids': received if received is not None else [inventory['catalog'][1]['id']],
    }))


def execute(client, quote_id, key='trade'):
    return client.post('/api/trades/execute', json={'quote_id': quote_id},
                       headers={'Idempotency-Key': key})


def fund(client, amount='1000000000000'):
    return ok(client.post('/api/wallet/demo-topup',
                         json={'amount_nano': amount, 'source': 'wallet'},
                         headers={'Idempotency-Key': 'fund'}))


def test_quote_exact_nano_frozen_and_read_only(client, monkeypatch):
    now = int(time.time())
    monkeypatch.setattr(time, 'time', lambda: now)
    before = state(client)
    inventory = before[0]
    gifts = inventory['inventory'][:2]
    received = inventory['catalog'][1:4]
    result = quote(client, [g['id'] for g in gifts], [g['id'] for g in received])
    prices = {g['id']: int(Decimal(g['price']) * 10**9) for g in inventory['catalog']}
    assert result['status'] == 'open'
    assert result['asset'] == 'DEMO_TON'
    assert result['source'] == 'sample'
    assert result['source_version']
    assert result['markup_bps'] == 500
    assert result['expires_at'] == now + 120
    assert result['offered'] == [
        {'gift_id': g['id'], 'catalog_id': g['catalogId'],
         'unit_nano': str(prices[g['catalogId']])} for g in gifts]
    assert result['received'] == [
        {'catalog_id': g['id'], 'unit_nano': str((prices[g['id']] * 10500 + 9999) // 10000)}
        for g in received]
    offered = sum(prices[g['catalogId']] for g in gifts)
    cost = sum((prices[g['id']] * 10500 + 9999) // 10000 for g in received)
    assert result['offered_nano'] == str(offered)
    assert result['received_nano'] == str(cost)
    assert result['wallet_delta_nano'] == str(offered - cost)
    assert result['required_balance_nano'] == str(max(cost - offered, 0))
    monkeypatch.setattr(time, 'time', lambda: now + 30)
    assert ok(client.get('/api/trades/quotes/' + result['id'])) == result
    assert state(client) == before


@pytest.mark.parametrize('credit', [False, True])
def test_execute_exact_settlement_and_current_snapshot_replays(client, settings, credit):
    fund(client)
    inventory = state(client)[0]
    gift = inventory['inventory'][-1 if credit else 0]
    result = quote(client, [gift['id']])
    before = state(client)
    delta = int(result['wallet_delta_nano'])
    assert (delta > 0) is credit
    settled = ok(execute(client, result['id']))
    assert settled['quote']['status'] == 'executed'
    assert settled['quote']['id'] == result['id']
    assert settled['revision'] > before[0]['revision']
    assert settled['revision'] == settled['inventory']['revision'] == settled['wallet']['revision']
    assert int(settled['wallet']['balance_nano']) == int(before[1]['balance_nano']) + delta
    remaining = [g for g in settled['inventory']['inventory'] if g['id'] in {x['id'] for x in before[0]['inventory']}]
    assert remaining == [g for g in before[0]['inventory'] if g['id'] != gift['id']]
    added = [g for g in settled['inventory']['inventory'] if g not in remaining]
    assert len(added) == 1 and added[0]['catalogId'] == result['received'][0]['catalog_id']
    entries = [tx for tx in settled['wallet']['transactions'] if tx['kind'].startswith('trade_')]
    assert len(entries) == 1
    assert entries[0]['kind'] == ('trade_credit' if credit else 'trade_debit')
    assert int(entries[0]['amount_nano']) == delta
    assert ok(execute(client, result['id'])) == settled
    assert ok(execute(client, result['id'], 'new-key')) == settled
    other = quote(client)
    assert execute(client, other['id']).status_code == 409
    ok(client.post('/api/inventory/demo-withdraw', json={'ids': [added[0]['id']]},
                   headers={'Idempotency-Key': 'later'}))
    current = state(client)
    with TestClient(create_app(settings)) as reopened:
        reopened.headers['Authorization'] = client.headers['Authorization']
        for key in ('trade', 'new-key', 'after-restart'):
            replay = ok(execute(reopened, result['id'], key))
            assert (replay['inventory'], replay['wallet']) == current
        assert ok(reopened.get('/api/trades/quotes/' + result['id']))['status'] == 'executed'


def test_insufficient_balance_is_atomic_and_does_not_consume_key(client):
    result = quote(client)
    assert int(result['required_balance_nano']) > 0
    before = state(client)
    assert execute(client, result['id']).status_code == 409
    assert state(client) == before
    assert ok(client.get('/api/trades/quotes/' + result['id'])) == result
    fund(client, result['required_balance_nano'])
    settled = ok(execute(client, result['id']))
    assert settled['wallet']['balance_nano'] == '0'


@pytest.mark.parametrize('elapsed', [120, 121])
def test_expired_quote_is_atomic(client, monkeypatch, elapsed):
    fund(client)
    now = int(time.time())
    monkeypatch.setattr(time, 'time', lambda: now)
    result = quote(client)
    before = state(client)
    monkeypatch.setattr(time, 'time', lambda: now + elapsed)
    assert execute(client, result['id']).status_code == 409
    assert state(client) == before


def test_executed_quote_replays_after_expiry(client, monkeypatch):
    fund(client)
    result = quote(client)
    settled = ok(execute(client, result['id']))
    monkeypatch.setattr(time, 'time', lambda: result['expires_at'] + 1)
    assert ok(execute(client, result['id'])) == settled
    assert ok(execute(client, result['id'], 'expired-retry')) == settled


@pytest.mark.parametrize('body', [{}, {'quote_id': None}, {'quote_id': True},
                                  {'quote_id': 1}, {'quote_id': ''}, {'quote_id': 'invalid'}])
def test_execute_strict_quote_identifier(client, body):
    before = state(client)
    response = client.post('/api/trades/execute', json=body,
                           headers={'Idempotency-Key': 'trade'})
    assert response.status_code == 422
    assert state(client) == before


def test_unknown_quote_hidden_and_key_not_consumed(client):
    before = state(client)
    unknown = '0' * 32
    assert client.get('/api/trades/quotes/' + unknown).status_code == 404
    assert execute(client, unknown).status_code == 404
    assert state(client) == before
    fund(client)
    ok(execute(client, quote(client)['id']))


@pytest.mark.parametrize('action', ['pledge', 'withdraw'])
def test_offered_gift_revalidated_at_execution(client, action):
    fund(client)
    gift = state(client)[0]['inventory'][0]['id']
    result = quote(client, [gift])
    body = {'id': gift} if action == 'pledge' else {'ids': [gift]}
    ok(client.post('/api/inventory/demo-' + action, json=body,
                   headers={'Idempotency-Key': 'invalidate'}))
    before = state(client)
    assert execute(client, result['id']).status_code == 409
    assert state(client) == before
    assert client.post('/api/trades/quote', json={
        'offered_ids': [gift], 'received_ids': [2]}).status_code == 409


def test_actor_ownership_and_hidden_quotes(client):
    first = state(client)
    result = quote(client)
    auth = client.headers['Authorization']
    client.headers.update(bearer(login(client, {**USER, 'id': USER['id'] + 1})['access_token']))
    before = state(client)
    assert client.get('/api/trades/quotes/' + result['id']).status_code == 404
    assert execute(client, result['id']).status_code == 404
    assert client.post('/api/trades/quote', json={
        'offered_ids': [first[0]['inventory'][0]['id']], 'received_ids': [2]}).status_code == 409
    assert state(client) == before
    fund(client)
    ok(execute(client, quote(client)['id']))
    client.headers['Authorization'] = auth
    assert state(client) == first
    fund(client)
    ok(execute(client, result['id']))


def test_receipt_cannot_reference_another_actors_quote(client):
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session

    from app.trade_models import TradeReceipt

    result = quote(client)
    other_id = USER['id'] + 1
    login(client, {**USER, 'id': other_id})
    with Session(client.app.state.engine) as db:
        db.add(TradeReceipt(user_id=other_id, key='forged-owner',
                            payload_hash='0' * 64, quote_id=result['id']))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.get(TradeReceipt, (other_id, 'forged-owner')) is None


def test_execution_revalidates_offered_catalog_identity(client):
    from sqlalchemy.orm import Session

    from app.inventory_models import InventoryGift

    fund(client)
    result = quote(client)
    offered = result['offered'][0]
    with Session(client.app.state.engine) as db:
        db.get(InventoryGift, offered['gift_id']).catalog_id = result['received'][0]['catalog_id']
        db.commit()
    before = state(client)
    assert execute(client, result['id']).status_code == 409
    assert state(client) == before
    assert ok(client.get('/api/trades/quotes/' + result['id'])) == result


@pytest.mark.parametrize('field', ['offered_ids', 'received_ids'])
@pytest.mark.parametrize('invalid', [[], [1, 1], [True], ['1'], [1.0], [0], [-1], [None], list(range(1, 102))])
def test_strict_unique_bounded_lists(client, field, invalid):
    before = state(client)
    body = {'offered_ids': [before[0]['inventory'][0]['id']], 'received_ids': [2], field: invalid}
    assert client.post('/api/trades/quote', json=body).status_code == 422
    assert state(client) == before


@pytest.mark.parametrize('extra', [
    {'user_id': 999}, {'markup_bps': 0}, {'unit_nano': '1'},
    {'wallet_delta_nano': '999999999999'}, {'expires_at': 9999999999},
])
def test_client_cannot_override_quote_or_execute_terms(client, extra):
    result = quote(client)
    before = state(client)
    assert client.post('/api/trades/quote', json={
        'offered_ids': [before[0]['inventory'][0]['id']], 'received_ids': [2], **extra}).status_code == 422
    assert client.post('/api/trades/execute', json={'quote_id': result['id'], **extra},
                       headers={'Idempotency-Key': 'trade'}).status_code == 422
    assert state(client) == before
    fund(client)
    ok(execute(client, result['id']))


def test_blocked_and_unknown_catalog_are_atomic(client):
    before = state(client)
    for received in ([before[0]['catalog'][0]['id']], [2, 999999999]):
        assert client.post('/api/trades/quote', json={
            'offered_ids': [before[0]['inventory'][0]['id']], 'received_ids': received}).status_code == 409
        assert state(client) == before


def test_authentication_and_execute_key_required(client, settings):
    result = quote(client)
    before = state(client)
    assert client.post('/api/trades/execute', json={'quote_id': result['id']}).status_code == 422
    assert state(client) == before
    with TestClient(create_app(settings)) as anonymous:
        assert anonymous.post('/api/trades/quote', json={'offered_ids': [1], 'received_ids': [2]}).status_code == 401
        assert execute(anonymous, result['id']).status_code == 401
        assert anonymous.get('/api/trades/quotes/' + result['id']).status_code == 401


def test_open_quote_persists_and_disabled_provider_cannot_settle(client, settings):
    fund(client)
    result = quote(client)
    before = state(client)
    with TestClient(create_app(replace(settings, gift_provider_mode='disabled'))) as disabled:
        disabled.headers['Authorization'] = client.headers['Authorization']
        assert disabled.post('/api/trades/quote', json={
            'offered_ids': [before[0]['inventory'][0]['id']], 'received_ids': [2]}).status_code == 503
        assert execute(disabled, result['id']).status_code == 503
    with TestClient(create_app(settings)) as reopened:
        reopened.headers['Authorization'] = client.headers['Authorization']
        assert state(reopened) == before
        assert ok(reopened.get('/api/trades/quotes/' + result['id'])) == result
        ok(execute(reopened, result['id']))


def test_each_received_price_rounds_up_and_execution_uses_frozen_prices(client, settings, monkeypatch):
    from app.pricing import SamplePriceProvider

    fund(client)
    gift = state(client)[0]['inventory'][0]['id']
    monkeypatch.setattr(SamplePriceProvider, 'price', lambda self, catalog_id: {
        1: 1_000_000_001, 2: 1, 3: 21,
    }[catalog_id])
    result = quote(client, [gift], [2, 3])
    assert [item['unit_nano'] for item in result['received']] == ['2', '23']
    assert result['offered_nano'] == '1000000001'
    assert result['received_nano'] == '25'
    assert result['wallet_delta_nano'] == '999999976'
    before = state(client)
    monkeypatch.setattr(SamplePriceProvider, 'price', lambda self, catalog_id: 999_999_999_999)
    with TestClient(create_app(replace(settings, trade_markup_bps=10000))) as reopened:
        reopened.headers['Authorization'] = client.headers['Authorization']
        assert ok(reopened.get('/api/trades/quotes/' + result['id'])) == result
        executed = ok(execute(reopened, result['id']))
        assert executed['quote'] == {**result, 'status': 'executed'}
        assert int(executed['wallet']['balance_nano']) == int(before[1]['balance_nano']) + 999_999_976


@pytest.mark.parametrize('value,expected', [
    ('0.000000001', 1), ('2.750', 2_750_000_000),
    ('90000.000000001', 90_000_000_000_001),
])
def test_decimal_price_conversion_is_exact(settings, value, expected):
    from app.pricing import ton_to_nano

    assert ton_to_nano(value) == expected


@pytest.mark.parametrize('value', [
    'NaN', 'Infinity', '-1', '0', '0.0000000001', 'not-a-price',
    '0.0000000010000000000000000000000000000000000000000000001',
    1, 1.0, True, None, '1' * 65,
])
def test_invalid_sample_prices_fail_closed(settings, value):
    from app.pricing import ton_to_nano

    with pytest.raises(ValueError):
        ton_to_nano(value)


@pytest.mark.parametrize('field,value', [
    ('trade_markup_bps', -1), ('trade_markup_bps', 10001),
    ('trade_markup_bps', True), ('trade_markup_bps', '500'),
    ('trade_quote_ttl', 29), ('trade_quote_ttl', 601),
    ('trade_quote_ttl', True), ('trade_quote_ttl', '120'),
])
def test_invalid_trade_settings_rejected(settings, field, value):
    with pytest.raises(ValueError):
        create_app(replace(settings, **{field: value}))


@pytest.mark.parametrize('markup,ttl', [(0, 30), (10000, 600)])
def test_trade_settings_valid_boundaries(client, settings, monkeypatch, markup, ttl):
    now = int(time.time())
    monkeypatch.setattr(time, 'time', lambda: now)
    with TestClient(create_app(replace(settings, trade_markup_bps=markup, trade_quote_ttl=ttl))) as configured:
        configured.headers['Authorization'] = client.headers['Authorization']
        result = quote(configured)
        assert result['markup_bps'] == markup
        assert result['expires_at'] == now + ttl
        base = 2_750_000_000
        assert result['received_nano'] == str((base * (10000 + markup) + 9999) // 10000)


@pytest.mark.parametrize('source,offset', [
    ('live-test', None), ('live-test', -1), ('live-test', 0),
    ('sample', -1), ('sample', 0),
])
def test_stale_or_undated_live_prices_reject_without_seeding(client, monkeypatch, source, offset):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.inventory_models import InventoryInit
    from app.models import User
    from app.trade_models import TradeQuote, TradeReceipt
    from app.wallet_models import WalletAccount

    now = int(time.time())
    monkeypatch.setattr(time, 'time', lambda: now)
    prices = client.app.state.price_provider
    monkeypatch.setattr(prices, 'source', source)
    monkeypatch.setattr(prices, 'valid_until', None if offset is None else now + offset)
    with Session(client.app.state.engine) as db:
        revision = db.get(User, USER['id']).state_revision
        assert db.get(InventoryInit, USER['id']) is None
        assert db.scalars(select(WalletAccount).where(WalletAccount.user_id == USER['id'])).all() == []
    response = client.post('/api/trades/quote', json={'offered_ids': [1], 'received_ids': [2]})
    assert response.status_code == 503, response.text
    with Session(client.app.state.engine) as db:
        assert db.get(User, USER['id']).state_revision == revision
        assert db.get(InventoryInit, USER['id']) is None
        for model in (WalletAccount, TradeQuote, TradeReceipt):
            assert db.scalars(select(model).where(model.user_id == USER['id'])).all() == []


@pytest.mark.parametrize('valid_for', [1, 45, 120, 600])
def test_future_live_prices_shorten_quote_expiry(client, monkeypatch, valid_for):
    now = int(time.time())
    monkeypatch.setattr(time, 'time', lambda: now)
    fund(client)
    prices = client.app.state.price_provider
    monkeypatch.setattr(prices, 'source', 'live-test')
    monkeypatch.setattr(prices, 'version', 'future-feed-v1')
    monkeypatch.setattr(prices, 'valid_until', now + valid_for)
    result = quote(client)
    assert result['source'] == 'live-test'
    assert result['source_version'] == 'future-feed-v1'
    assert result['expires_at'] == now + min(valid_for, 120)
    before = state(client)
    monkeypatch.setattr(time, 'time', lambda: result['expires_at'])
    assert execute(client, result['id']).status_code == 409
    assert state(client) == before


def assert_provider_rejection_atomic(client, body, before):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.trade_models import TradeQuote, TradeReceipt

    response = client.post('/api/trades/quote', json=body)
    assert response.status_code == 503, response.text
    assert state(client) == before
    with Session(client.app.state.engine) as db:
        for model in (TradeQuote, TradeReceipt):
            assert db.scalars(select(model).where(model.user_id == USER['id'])).all() == []


@pytest.mark.parametrize('invalid', [-1, 0, True, 1.5, '1', CAP + 1])
@pytest.mark.parametrize('side', ['offered', 'received'])
def test_invalid_provider_price_rejected_atomically(client, monkeypatch, invalid, side):
    before = state(client)
    gift = before[0]['inventory'][0]
    received_id = before[0]['catalog'][1]['id']
    prices = client.app.state.price_provider
    original_price = prices.price
    bad_id = gift['catalogId'] if side == 'offered' else received_id
    monkeypatch.setattr(prices, 'price', lambda catalog_id: (
        invalid if catalog_id == bad_id else original_price(catalog_id)))
    assert_provider_rejection_atomic(client, {
        'offered_ids': [gift['id']], 'received_ids': [received_id],
    }, before)


@pytest.mark.parametrize('error', [KeyError, ValueError])
@pytest.mark.parametrize('side', ['offered', 'received'])
def test_missing_provider_price_rejected_atomically(client, monkeypatch, error, side):
    before = state(client)
    gift = before[0]['inventory'][0]
    received_id = before[0]['catalog'][1]['id']
    prices = client.app.state.price_provider
    original_price = prices.price
    bad_id = gift['catalogId'] if side == 'offered' else received_id

    def missing_price(catalog_id):
        if catalog_id == bad_id:
            raise error('provider price unavailable')
        return original_price(catalog_id)

    monkeypatch.setattr(prices, 'price', missing_price)
    assert_provider_rejection_atomic(client, {
        'offered_ids': [gift['id']], 'received_ids': [received_id],
    }, before)


@pytest.mark.parametrize('invalid', [True, False, 1.5, '9999999999', [], {}])
def test_invalid_provider_freshness_type_rejected_atomically(client, monkeypatch, invalid):
    before = state(client)
    monkeypatch.setattr(client.app.state.price_provider, 'valid_until', invalid)
    assert_provider_rejection_atomic(client, {
        'offered_ids': [before[0]['inventory'][0]['id']], 'received_ids': [2],
    }, before)


@pytest.mark.parametrize('field,invalid', [
    ('source', ''), ('source', 's' * 65), ('source', None),
    ('source', True), ('source', 1),
    ('version', ''), ('version', 'v' * 129), ('version', None),
    ('version', True), ('version', 1),
])
def test_invalid_provider_provenance_rejected_atomically(client, monkeypatch, field, invalid):
    before = state(client)
    prices = client.app.state.price_provider
    monkeypatch.setattr(prices, 'valid_until', int(time.time()) + 60)
    monkeypatch.setattr(prices, field, invalid)
    assert_provider_rejection_atomic(client, {
        'offered_ids': [before[0]['inventory'][0]['id']], 'received_ids': [2],
    }, before)


@pytest.mark.parametrize('same_quote', [False, True])
def test_sqlite_concurrent_trade_executions_settle_gift_once(client, same_quote):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.trade_models import TradeQuote, TradeReceipt

    fund(client)
    before = state(client)
    gift = before[0]['inventory'][0]['id']
    quotes = [quote(client, [gift], [2])]
    quotes.append(quotes[0] if same_quote else quote(client, [gift], [3]))
    barrier = Barrier(2)

    def attempt(index):
        barrier.wait(timeout=10)
        return execute(client, quotes[index]['id'], f'sqlite-execute-{index}')

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(attempt, [0, 1]))
    assert sorted(r.status_code for r in responses) == ([200, 200] if same_quote else [200, 409])
    winner = next(index for index, response in enumerate(responses) if response.status_code == 200)
    winning_quote = quotes[winner]
    after = state(client)
    assert gift not in [g['id'] for g in after[0]['inventory']]
    original_ids = {g['id'] for g in before[0]['inventory']}
    added = [g for g in after[0]['inventory'] if g['id'] not in original_ids]
    assert len(added) == 1
    assert added[0]['catalogId'] == winning_quote['received'][0]['catalog_id']
    assert len(after[0]['inventory']) == len(before[0]['inventory'])
    assert after[0]['pledged'] == before[0]['pledged']
    assert int(after[1]['balance_nano']) == int(before[1]['balance_nano']) + int(winning_quote['wallet_delta_nano'])
    entries = [tx for tx in after[1]['transactions'] if tx['kind'].startswith('trade_')]
    assert len(entries) == 1
    assert int(entries[0]['amount_nano']) == int(winning_quote['wallet_delta_nano'])
    if same_quote:
        assert responses[0].json() == responses[1].json()
    with Session(client.app.state.engine) as db:
        receipts = db.scalars(select(TradeReceipt).where(TradeReceipt.user_id == USER['id'])).all()
        assert len(receipts) == (2 if same_quote else 1)
        assert {receipt.quote_id for receipt in receipts} == {winning_quote['id']}
        assert db.get(TradeQuote, winning_quote['id']).status == 'executed'
        if not same_quote:
            assert db.get(TradeQuote, quotes[1 - winner]['id']).status == 'open'


@pytest.mark.parametrize('competing', ['withdraw', 'pledge'])
def test_sqlite_trade_races_inventory_mutation_atomically(client, competing):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.trade_models import TradeReceipt

    fund(client)
    before = state(client)
    gift = before[0]['inventory'][0]['id']
    result = quote(client, [gift])
    barrier = Barrier(2)

    def attempt(action):
        barrier.wait(timeout=10)
        if action == 'execute':
            return execute(client, result['id'], 'sqlite-trade-race')
        body = {'id': gift} if action == 'pledge' else {'ids': [gift]}
        return client.post('/api/inventory/demo-' + action, json=body,
                           headers={'Idempotency-Key': 'sqlite-inventory-race'})

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(attempt, ['execute', competing]))
    assert sorted(r.status_code for r in responses) == [200, 409]
    traded = responses[0].status_code == 200
    after = state(client)
    assert gift not in [g['id'] for g in after[0]['inventory']]
    assert (gift in [g['id'] for g in after[0]['pledged']]) == (competing == 'pledge' and not traded)
    original_ids = {g['id'] for g in before[0]['inventory']}
    added = [g for g in after[0]['inventory'] if g['id'] not in original_ids]
    assert len(added) == int(traded)
    if traded:
        assert added[0]['catalogId'] == result['received'][0]['catalog_id']
    assert len(after[0]['inventory']) == len(before[0]['inventory']) - (0 if traded else 1)
    assert int(after[1]['balance_nano']) == int(before[1]['balance_nano']) + (
        int(result['wallet_delta_nano']) if traded else 0)
    entries = [tx for tx in after[1]['transactions'] if tx['kind'].startswith('trade_')]
    assert len(entries) == int(traded)
    assert ok(client.get('/api/trades/quotes/' + result['id']))['status'] == ('executed' if traded else 'open')
    with Session(client.app.state.engine) as db:
        receipts = db.scalars(select(TradeReceipt).where(TradeReceipt.user_id == USER['id'])).all()
        assert len(receipts) == int(traded)


@pytest.mark.parametrize('prefix', ['trade:', 'loan:', 'auto:', '__'])
@pytest.mark.parametrize('action,body', [
    ('topup', {'amount_nano': '1', 'source': 'wallet'}),
    ('withdraw', {'amount_nano': '1', 'destination': 'demo'}),
    ('referral', {}),
])
def test_reserved_wallet_keys_reject_before_seeding(client, prefix, action, body):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.inventory_models import InventoryGift, InventoryInit, InventoryReceipt
    from app.models import User
    from app.trade_models import TradeQuote, TradeReceipt
    from app.wallet_models import WalletAccount, WalletPosting, WalletTransaction

    with Session(client.app.state.engine) as db:
        revision = db.get(User, USER['id']).state_revision
    response = client.post('/api/wallet/demo-' + action, json=body,
                           headers={'Idempotency-Key': prefix + 'reserved'})
    assert response.status_code == 422, response.text
    with Session(client.app.state.engine) as db:
        assert db.get(User, USER['id']).state_revision == revision
        for model in (InventoryGift, InventoryInit, InventoryReceipt, WalletAccount,
                      WalletPosting, WalletTransaction, TradeQuote, TradeReceipt):
            assert db.scalars(select(model).where(model.user_id == USER['id'])).all() == []


@pytest.mark.parametrize('action,body', [
    ('topup', {'amount_nano': '1', 'source': 'wallet'}),
    ('withdraw', {'amount_nano': '1', 'destination': 'demo'}),
    ('referral', {}),
])
def test_wallet_cannot_preempt_or_replay_internal_trade_ledger_key(client, action, body):
    fund(client)
    result = quote(client)
    internal_key = 'trade:' + result['id']
    before = state(client)
    for settled in (False, True):
        if settled:
            ok(execute(client, result['id']))
            before = state(client)
        response = client.post('/api/wallet/demo-' + action, json=body,
                               headers={'Idempotency-Key': internal_key})
        assert response.status_code == 422, response.text
        assert state(client) == before
    assert len([tx for tx in before[1]['transactions'] if tx['kind'].startswith('trade_')]) == 1
