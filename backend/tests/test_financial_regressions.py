"""Cross-feature settlement boundaries not covered by validation-only tests."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import loans, trades
from app.config import Settings
from app.inventory_models import InventoryGift
from app.loan_models import DemoLoan, LoanReceipt
from app.main import create_app
from app.trade_models import TradeQuote, TradeReceipt
from app.wallet_models import WalletAccount, WalletPosting, WalletTransaction
from test_auth import BOT_TOKEN, USER, bearer, login


@pytest.fixture
def settings(tmp_path):
    return Settings(
        bot_token=BOT_TOKEN,
        database_url=f"sqlite:///{(tmp_path / 'financial-regressions.sqlite3').as_posix()}",
        allowed_origins=(),
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        client.headers.update(bearer(login(client)['access_token']))
        yield client


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def post(client, endpoint, body, key):
    return client.post('/api/' + endpoint, json=body,
                       headers={'Idempotency-Key': key})


def state(client):
    return ok(client.get('/api/loans'))


def ledger_rows(client):
    with Session(client.app.state.engine) as db:
        return (
            db.execute(select(WalletAccount.kind, WalletAccount.balance).where(
                WalletAccount.user_id == USER['id']).order_by(WalletAccount.kind)).all(),
            db.execute(select(WalletTransaction.id, WalletTransaction.key,
                              WalletTransaction.kind, WalletTransaction.amount_nano).where(
                WalletTransaction.user_id == USER['id']).order_by(WalletTransaction.id)).all(),
            db.execute(select(WalletPosting.transaction_id, WalletPosting.account_kind,
                              WalletPosting.amount).where(WalletPosting.user_id == USER['id'])
                       .order_by(WalletPosting.transaction_id, WalletPosting.account_kind)).all(),
        )


def make_quote(client, gift_id):
    return ok(client.post('/api/trades/quote', json={
        'offered_ids': [gift_id], 'received_ids': [2],
    }))


def test_zero_delta_trade_exchanges_once_without_zero_value_ledger_entries(client, monkeypatch):
    before = state(client)
    gift = before['inventory']['inventory'][0]
    # 20 nanoTON plus the 5% ask markup exactly equals the 21-nanoTON offer.
    monkeypatch.setattr(client.app.state.price_provider, 'price',
                        lambda catalog_id: {gift['catalogId']: 21, 2: 20}[catalog_id])
    quote = make_quote(client, gift['id'])
    assert quote['wallet_delta_nano'] == quote['required_balance_nano'] == '0'
    ledger_before = ledger_rows(client)

    settled = ok(post(client, 'trades/execute', {'quote_id': quote['id']}, 'even-trade'))
    after = state(client)
    assert settled['quote']['status'] == 'executed'
    assert after['revision'] == before['revision'] + 1
    assert after['wallet']['balance_nano'] == '0'
    assert after['wallet']['transactions'] == before['wallet']['transactions']
    assert ledger_rows(client) == ledger_before
    original_ids = {item['id'] for item in before['inventory']['inventory']}
    remaining = after['inventory']['inventory']
    assert gift['id'] not in {item['id'] for item in remaining}
    added = [item for item in remaining if item['id'] not in original_ids]
    assert len(added) == 1 and added[0]['catalogId'] == 2
    assert len(remaining) == len(before['inventory']['inventory'])
    assert after['inventory']['pledged'] == before['inventory']['pledged']
    assert after['loans'] == before['loans']
    for key in ('even-trade', 'even-trade-retry'):
        assert ok(post(client, 'trades/execute', {'quote_id': quote['id']}, key)) == settled
        assert state(client) == after
        assert ledger_rows(client) == ledger_before
    with Session(client.app.state.engine) as db:
        receipts = db.scalars(select(TradeReceipt).where(
            TradeReceipt.user_id == USER['id'])).all()
        assert len(receipts) == 2
        assert {receipt.quote_id for receipt in receipts} == {quote['id']}


def test_late_trade_failure_rolls_back_gifts_ledger_quote_and_retry_key(client, monkeypatch):
    ok(post(client, 'wallet/demo-topup', {'amount_nano': '10000000000', 'source': 'wallet'}, 'fund'))
    before = state(client)
    gift = before['inventory']['inventory'][0]
    quote = make_quote(client, gift['id'])
    ledger_before = ledger_rows(client)
    key = 'late-trade-retry'
    checked = []

    def fail_after_settlement(db, user_id, provider):
        # Force pending receipts to SQL too, so the failure occurs after all writes.
        db.flush()
        assert db.get(TradeQuote, quote['id']).status == 'executed'
        assert db.get(InventoryGift, gift['id']) is None
        assert db.get(TradeReceipt, (user_id, key)) is not None
        assert db.get(WalletAccount, (user_id, 'wallet')).balance == (
            int(before['wallet']['balance_nano']) + int(quote['wallet_delta_nano']))
        checked.append(True)
        raise HTTPException(503, 'Injected response snapshot failure')

    with monkeypatch.context() as patch:
        patch.setattr(trades, 'inventory_snapshot', fail_after_settlement)
        assert post(client, 'trades/execute', {'quote_id': quote['id']}, key).status_code == 503
    assert checked == [True]
    assert state(client) == before
    assert ledger_rows(client) == ledger_before
    assert ok(client.get('/api/trades/quotes/' + quote['id'])) == quote
    with Session(client.app.state.engine) as db:
        assert db.get(TradeReceipt, (USER['id'], key)) is None

    settled = ok(post(client, 'trades/execute', {'quote_id': quote['id']}, key))
    assert settled['quote']['status'] == 'executed'
    after = state(client)
    assert int(after['wallet']['balance_nano']) == (
        int(before['wallet']['balance_nano']) + int(quote['wallet_delta_nano']))
    assert len([tx for tx in after['wallet']['transactions'] if tx['kind'].startswith('trade_')]) == 1
    ledger_after = ledger_rows(client)
    assert ok(post(client, 'trades/execute', {'quote_id': quote['id']}, key)) == settled
    assert state(client) == after
    assert ledger_rows(client) == ledger_after


def test_late_repayment_failure_preserves_debt_collateral_funds_and_retry_key(client, monkeypatch):
    initial = state(client)
    gift = next(item for item in initial['inventory']['inventory'] if item['pledgeSupported'])
    ok(post(client, 'loans/create', {'gift_id': gift['id'], 'weeks': 1}, 'create-loan'))
    ok(post(client, 'wallet/demo-topup', {'amount_nano': '10000000000', 'source': 'wallet'}, 'fund'))
    before = state(client)
    loan = next(item for item in before['loans'] if item['gift_id'] == gift['id'])
    ledger_before = ledger_rows(client)
    key = 'late-repayment-retry'
    checked = []

    def fail_after_repayment(db, user_id, provider):
        db.flush()
        assert db.get(DemoLoan, loan['id']).status == 'repaid'
        assert db.get(InventoryGift, gift['id']).pledged is False
        assert db.get(LoanReceipt, (user_id, key)) is not None
        assert db.get(WalletAccount, (user_id, 'wallet')).balance == (
            int(before['wallet']['balance_nano']) - int(loan['repayment_nano']))
        checked.append(True)
        raise HTTPException(503, 'Injected response snapshot failure')

    with monkeypatch.context() as patch:
        patch.setattr(loans, 'inventory_snapshot', fail_after_repayment)
        assert post(client, 'loans/repay', {'gift_id': gift['id']}, key).status_code == 503
    assert checked == [True]
    assert state(client) == before
    assert ledger_rows(client) == ledger_before
    with Session(client.app.state.engine) as db:
        assert db.get(LoanReceipt, (USER['id'], key)) is None

    settled = ok(post(client, 'loans/repay', {'gift_id': gift['id']}, key))
    after = state(client)
    assert next(item for item in after['loans'] if item['id'] == loan['id'])['status'] == 'repaid'
    assert gift['id'] in {item['id'] for item in after['inventory']['inventory']}
    assert int(after['wallet']['balance_nano']) == (
        int(before['wallet']['balance_nano']) - int(loan['repayment_nano']))
    assert len([tx for tx in after['wallet']['transactions'] if tx['kind'] == 'loan_repay']) == 1
    ledger_after = ledger_rows(client)
    assert ok(post(client, 'loans/repay', {'gift_id': gift['id']}, key)) == settled
    assert state(client) == after
    assert ledger_rows(client) == ledger_after
