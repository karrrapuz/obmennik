"""Optional PostgreSQL integration smoke test, enabled explicitly by CI."""

import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.models import LoginSession, User
from app.inventory_models import InventoryGift, InventoryInit, InventoryReceipt
from app.wallet_models import WalletAccount, WalletPosting, WalletTransaction
from app.loan_models import DemoLoan, LoanReceipt
from app.loans import process_due_loans
from sqlalchemy.exc import DBAPIError
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier


POSTGRES_URL = os.environ.get("GIFT_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="GIFT_TEST_POSTGRES_URL is not set")
BOT_TOKEN = "123456789:POSTGRES_TEST_ONLY_NOT_A_SERVER_SECRET"


@pytest.fixture
def settings():
    # The shared autouse fixture migrates this database before the test runs.
    return Settings(
        bot_token=BOT_TOKEN,
        database_url=POSTGRES_URL,
        allowed_origins=("http://localhost:5173",),
    )


def test_postgres_new_user_retry_me_and_logout(settings):
    user_id = secrets.randbelow(2**52 - 1) + 1
    fields = {
        "query_id": secrets.token_hex(16),
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": user_id, "first_name": "Postgres Test"}),
    }
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    launch = urlencode(fields)
    app = create_app(settings)

    with TestClient(app) as client:
        try:
            with Session(app.state.engine) as db:
                assert db.get(User, user_id) is None

            response = client.post("/api/auth/telegram", json={"init_data": launch})
            assert response.status_code == 200
            payload = response.json()
            token = payload["access_token"]
            assert isinstance(token, str) and token
            assert payload["user"]["id"] == user_id
            assert payload["user"]["first_name"] == "Postgres Test"
            for private_value in (BOT_TOKEN, launch, fields["hash"], fields["query_id"]):
                assert private_value not in response.text

            repeated = client.post("/api/auth/telegram", json={"init_data": launch})
            assert repeated.status_code == 200
            assert repeated.json() == payload
            with Session(app.state.engine) as db:
                assert db.get(User, user_id).first_name == "Postgres Test"
                sessions = db.scalars(select(LoginSession).where(LoginSession.user_id == user_id)).all()
                assert len(sessions) == 1
                assert sessions[0].token_hash == hashlib.sha256(token.encode()).hexdigest()

            headers = {"Authorization": f"Bearer {token}"}
            me = client.get("/api/me", headers=headers)
            assert me.status_code == 200
            assert me.json() == payload["user"]
            assert token not in me.text
            initial = client.get('/api/inventory', headers=headers)
            assert initial.status_code == 200
            assert len(initial.json()['inventory']) == 5
            deposit_headers = {**headers, 'Idempotency-Key': 'pg-deposit'}
            deposited = client.post('/api/inventory/demo-deposit', json={}, headers=deposit_headers)
            assert deposited.status_code == 200
            assert len(deposited.json()['inventory']) == 6
            assert client.post('/api/inventory/demo-deposit', json={}, headers=deposit_headers).json() == deposited.json()
            gift_id = initial.json()['inventory'][0]['id']

            def competing_action(action):
                body = {'id': gift_id} if action == 'pledge' else {'ids': [gift_id]}
                return client.post('/api/inventory/demo-' + action, json=body,
                                   headers={**headers, 'Idempotency-Key': 'race-' + action}).status_code

            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(competing_action, ['pledge', 'withdraw']))
            assert sorted(outcomes) == [200, 409]
            final = client.get('/api/inventory', headers=headers).json()
            assert gift_id not in [g['id'] for g in final['inventory']]
            assert len(final['pledged']) == (1 if outcomes[0] == 200 else 0)
            wallet = client.get('/api/wallet', headers=headers)
            assert wallet.status_code == 200
            assert wallet.json()['balance_nano'] == '0'
            assert wallet.json()['referral_nano'] == '5000000000'
            topup_headers = {**headers, 'Idempotency-Key': 'pg-wallet-topup'}
            topup_body = {'amount_nano': '1000000000', 'source': 'wallet'}
            assert client.post('/api/wallet/demo-topup', json=topup_body, headers=topup_headers).status_code == 200
            assert client.post('/api/wallet/demo-topup', json=topup_body, headers=topup_headers).json()['balance_nano'] == '1000000000'

            def withdraw_test(index):
                return client.post('/api/wallet/demo-withdraw',
                    json={'amount_nano': '750000000', 'destination': 'demo-destination'},
                    headers={**headers, 'Idempotency-Key': f'pg-wallet-withdraw-{index}'}).status_code

            with ThreadPoolExecutor(max_workers=2) as pool:
                assert sorted(pool.map(withdraw_test, [1, 2])) == [200, 409]
            assert client.get('/api/wallet', headers=headers).json()['balance_nano'] == '250000000'

            def claim_test(index):
                return client.post('/api/wallet/demo-referral', json={},
                    headers={**headers, 'Idempotency-Key': f'pg-referral-{index}'}).status_code

            with ThreadPoolExecutor(max_workers=2) as pool:
                assert sorted(pool.map(claim_test, [1, 2])) == [200, 409]
            final_wallet = client.get('/api/wallet', headers=headers).json()
            assert final_wallet['balance_nano'] == '5250000000'
            assert final_wallet['referral_nano'] == '0'
            all_loans = client.get('/api/loans', headers=headers).json()
            eligible = [gift['id'] for gift in all_loans['inventory']['inventory'] if gift['pledgeSupported']]
            first_gift = eligible[0]
            create_body = {'gift_id': first_gift, 'weeks': 2}
            create_headers = {**headers, 'Idempotency-Key': 'pg-loan-create'}
            created = client.post('/api/loans/create', json=create_body, headers=create_headers)
            assert created.status_code == 200
            assert created.json()['wallet']['balance_nano'] == '6450000000'
            repeated_loan = client.post('/api/loans/create', json=create_body, headers=create_headers)
            assert repeated_loan.json()['wallet']['balance_nano'] == '6450000000'

            def repay_test(index):
                return client.post('/api/loans/repay', json={'gift_id': first_gift},
                    headers={**headers, 'Idempotency-Key': f'pg-repay-{index}'}).status_code

            with ThreadPoolExecutor(max_workers=2) as pool:
                assert sorted(pool.map(repay_test, [1, 2])) == [200, 409]
            assert client.get('/api/wallet', headers=headers).json()['balance_nano'] == '5170000000'
            second_gift = eligible[1]
            assert client.post('/api/loans/create', json={'gift_id': second_gift, 'weeks': 1},
                headers={**headers, 'Idempotency-Key': 'pg-auto-create'}).status_code == 200
            assert client.post('/api/loans/autopay', json={'gift_id': second_gift, 'enabled': True},
                headers={**headers, 'Idempotency-Key': 'pg-auto-enable'}).status_code == 200
            with Session(app.state.engine) as db:
                automatic = db.scalar(select(DemoLoan).where(DemoLoan.user_id == user_id,
                    DemoLoan.gift_id == second_gift, DemoLoan.status == 'active'))
                automatic.due_at = int(time.time()) - 1
                db.commit()
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(lambda _: process_due_loans(app.state.engine), [1, 2]))
            assert client.get('/api/wallet', headers=headers).json()['balance_nano'] == '5130000000'
            settled = client.get('/api/loans', headers=headers).json()
            assert next(loan for loan in settled['loans'] if loan['gift_id'] == second_gift)['status'] == 'repaid'

            assert client.post('/api/wallet/demo-topup',
                json={'amount_nano': '1000000000000', 'source': 'wallet'},
                headers={**headers, 'Idempotency-Key': 'pg-trade-fund'}).status_code == 200
            trade_inventory = client.get('/api/inventory', headers=headers).json()
            trade_gift = trade_inventory['inventory'][0]['id']
            received_id = trade_inventory['catalog'][1]['id']
            quoted = client.post('/api/trades/quote', json={
                'offered_ids': [trade_gift], 'received_ids': [received_id]}, headers=headers)
            assert quoted.status_code == 200, quoted.text
            quote_id = quoted.json()['id']
            before_trade_wallet = client.get('/api/wallet', headers=headers).json()
            barrier = Barrier(2)

            def execute_trade(index):
                barrier.wait(timeout=10)
                return client.post('/api/trades/execute', json={'quote_id': quote_id},
                    headers={**headers, 'Idempotency-Key': f'pg-trade-{index}'})

            with ThreadPoolExecutor(max_workers=2) as pool:
                executions = list(pool.map(execute_trade, [1, 2]))
            assert [response.status_code for response in executions] == [200, 200]
            assert executions[0].json() == executions[1].json()
            trade_state = executions[0].json()
            assert int(trade_state['wallet']['balance_nano']) == (
                int(before_trade_wallet['balance_nano']) + int(quoted.json()['wallet_delta_nano']))
            assert len([tx for tx in trade_state['wallet']['transactions']
                        if tx['kind'].startswith('trade_')]) == 1
            assert trade_gift not in [g['id'] for g in trade_state['inventory']['inventory']]
            assert len(trade_state['inventory']['inventory']) == len(trade_inventory['inventory'])

            for competing in ('withdraw', 'pledge'):
                current = client.get('/api/inventory', headers=headers).json()
                race_gift = next(g['id'] for g in current['inventory'] if g['pledgeSupported'])
                quoted = client.post('/api/trades/quote', json={
                    'offered_ids': [race_gift], 'received_ids': [received_id]}, headers=headers)
                assert quoted.status_code == 200, quoted.text
                race_quote = quoted.json()
                before_wallet = client.get('/api/wallet', headers=headers).json()
                barrier = Barrier(2)

                def race(action):
                    barrier.wait(timeout=10)
                    if action == 'execute':
                        return client.post('/api/trades/execute', json={'quote_id': race_quote['id']},
                            headers={**headers, 'Idempotency-Key': 'pg-race-trade-' + competing})
                    body = {'id': race_gift} if action == 'pledge' else {'ids': [race_gift]}
                    return client.post('/api/inventory/demo-' + action, json=body,
                        headers={**headers, 'Idempotency-Key': 'pg-trade-race-' + action})

                with ThreadPoolExecutor(max_workers=2) as pool:
                    responses = list(pool.map(race, ['execute', competing]))
                assert sorted(r.status_code for r in responses) == [200, 409]
                after_inventory = client.get('/api/inventory', headers=headers).json()
                after_wallet = client.get('/api/wallet', headers=headers).json()
                won = responses[0].status_code == 200
                assert int(after_wallet['balance_nano']) == int(before_wallet['balance_nano']) + (
                    int(race_quote['wallet_delta_nano']) if won else 0)
                assert race_gift not in [g['id'] for g in after_inventory['inventory']]
                assert (race_gift in [g['id'] for g in after_inventory['pledged']]) == (
                    competing == 'pledge' and not won)
                assert len(after_inventory['inventory']) == len(current['inventory']) - (0 if won else 1)
                stored_quote = client.get('/api/trades/quotes/' + race_quote['id'], headers=headers)
                assert stored_quote.status_code == 200
                assert stored_quote.json()['status'] == ('executed' if won else 'open')
            with Session(app.state.engine) as db:
                db.execute(delete(LoanReceipt).where(LoanReceipt.user_id == user_id))
                db.execute(delete(DemoLoan).where(DemoLoan.user_id == user_id))
                db.get(WalletAccount, (user_id, 'wallet')).balance += 1
                with pytest.raises(DBAPIError):
                    db.commit()
                db.rollback()
                db.add(WalletTransaction(id=secrets.token_hex(16), user_id=user_id,
                    key='unbalanced', payload_hash='test', kind='topup', amount_nano=1,
                    created_at=int(time.time())))
                with pytest.raises(DBAPIError):
                    db.commit()
                db.rollback()
            logout = client.post("/api/auth/logout", headers=headers)
            assert logout.status_code == 204
            assert logout.content == b""
            assert client.get("/api/me", headers=headers).status_code == 401
        finally:
            # Remove only this test's random identity, never shared database state.
            from app.trade_models import TradeQuote, TradeReceipt

            with Session(app.state.engine) as db:
                db.execute(delete(TradeReceipt).where(TradeReceipt.user_id == user_id))
                db.execute(delete(TradeQuote).where(TradeQuote.user_id == user_id))
                db.execute(delete(LoanReceipt).where(LoanReceipt.user_id == user_id))
                db.execute(delete(DemoLoan).where(DemoLoan.user_id == user_id))
                db.execute(delete(WalletPosting).where(WalletPosting.user_id == user_id))
                db.execute(delete(WalletTransaction).where(WalletTransaction.user_id == user_id))
                db.execute(delete(WalletAccount).where(WalletAccount.user_id == user_id))
                db.execute(delete(InventoryReceipt).where(InventoryReceipt.user_id == user_id))
                db.execute(delete(InventoryGift).where(InventoryGift.user_id == user_id))
                db.execute(delete(InventoryInit).where(InventoryInit.user_id == user_id))
                db.execute(delete(LoginSession).where(LoginSession.user_id == user_id))
                db.execute(delete(User).where(User.id == user_id))
                db.commit()
