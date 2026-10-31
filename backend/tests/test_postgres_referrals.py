"""Optional real-PostgreSQL coverage for cross-user reward locking and replay."""
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.models import User, LoginSession
from app.referral_models import ReferralBinding, ReferralReward
from app.trade_models import TradeQuote, TradeReceipt
from app.loan_models import DemoLoan, LoanReceipt
from app.wallet_models import WalletAccount, WalletPosting, WalletTransaction
from app.inventory_models import InventoryGift, InventoryInit, InventoryReceipt
from app.grant_models import DemoSeasonalGrant
from test_auth import BOT_TOKEN
from test_referrals import actor, prepared, execute, claim, summary

URL = os.getenv('GIFT_TEST_POSTGRES_URL')
pytestmark = pytest.mark.skipif(not URL, reason='GIFT_TEST_POSTGRES_URL is not set')


@pytest.fixture
def settings():
    return Settings(bot_token=BOT_TOKEN, database_url=URL, allowed_origins=(), telegram_bot_username='giftmoney_test_bot')


def test_shared_referrer_concurrent_trades_and_claims(settings):
    app = create_app(settings)
    start = secrets.randbelow(2**51) + 1
    identities = [start, start + 1, start + 2]
    with TestClient(app) as client:
        with Session(app.state.engine) as db:
            assert not db.scalars(select(User.id).where(User.id.in_(identities))).all()
        try:
            referrer_id = identities[1]
            referrer, code = actor(client, referrer_id)
            buyers = [actor(client, identity, code)[0] for identity in (identities[0], identities[2])]
            quotes = [prepared(client, buyer) for buyer in buyers]
            barrier = Barrier(2)
            def run(index):
                barrier.wait(timeout=10)
                return execute(client, buyers[index], quotes[index], f'pg-execute-{index}')
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(run, (0, 1)))
            assert [result.status_code for result in results] == [200, 200]
            expected = sum(min(int(q['received_nano']) * 200 // 10000, int(q['fee_nano'])) for q in quotes)
            assert int(summary(client, referrer)['available_nano']) == expected
            barrier = Barrier(2)
            with ThreadPoolExecutor(max_workers=2) as pool:
                replays = list(pool.map(run, (0, 1)))
            assert [result.status_code for result in replays] == [200, 200]
            assert int(summary(client, referrer)['available_nano']) == expected
            barrier = Barrier(2)
            def collect(_):
                barrier.wait(timeout=10)
                return claim(client, referrer, 'pg-shared-claim')
            with ThreadPoolExecutor(max_workers=2) as pool:
                claims = list(pool.map(collect, (0, 1)))
            assert [result.status_code for result in claims] == [200, 200]
            assert all(int(result.json()['wallet']['balance_nano']) == expected for result in claims)
            assert summary(client, referrer)['available_nano'] == '0'
            with Session(app.state.engine) as db:
                assert db.scalar(select(func.count()).select_from(ReferralReward).where(ReferralReward.referrer_id == referrer_id)) == 2
                assert db.scalar(select(func.count()).select_from(WalletTransaction).where(
                    WalletTransaction.user_id == referrer_id, WalletTransaction.source == 'earned')) == 1
                assert db.scalar(select(func.count()).select_from(WalletTransaction).where(
                    WalletTransaction.user_id == referrer_id, WalletTransaction.kind == 'referral_credit')) == 2
        finally:
            with Session(app.state.engine) as db:
                db.execute(delete(ReferralReward).where(ReferralReward.referrer_id.in_(identities)))
                db.execute(delete(ReferralBinding).where(ReferralBinding.user_id.in_(identities)))
                for model in (TradeReceipt, TradeQuote, LoanReceipt, DemoLoan, WalletPosting, WalletTransaction,
                              WalletAccount, InventoryReceipt, InventoryGift, InventoryInit, DemoSeasonalGrant, LoginSession):
                    db.execute(delete(model).where(model.user_id.in_(identities)))
                db.execute(delete(User).where(User.id.in_(identities)))
                db.commit()
