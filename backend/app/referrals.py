"""Signed first-launch attribution and commission-backed DEMO_TON earnings."""
import hashlib
import re
import time
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .ledger import CAP, ensure_wallet, lock_actor, lock_user, post_transfer, wallet_snapshot
from .models import User
from .referral_models import ReferralBinding, ReferralReward
from .wallet_models import WalletAccount, WalletTransaction


def bind_first_launch(db, user_id, start_param):
    if not isinstance(start_param, str) or not re.fullmatch(r'ref_[A-Za-z0-9_-]{1,60}', start_param):
        return
    referrer = db.scalar(select(User).where(User.referral_code == start_param[4:]))
    if referrer is not None and referrer.id != user_id:
        db.add(ReferralBinding(user_id=user_id, referrer_id=referrer.id, created_at=int(time.time())))


def lock_trade_participants(db, session):
    # SQLite serializes writers before any participant lookup; PostgreSQL uses sorted row locks.
    if db.get_bind().dialect.name == 'sqlite':
        lock_actor(db, session)
    binding = db.get(ReferralBinding, session.user_id)
    identities = {session.user_id}
    if binding:
        identities.add(binding.referrer_id)
    for identity in sorted(identities):
        user = lock_user(db, identity)
        if user is None:
            raise HTTPException(401, 'Authentication required')
    return session.user_id


def earned_available(db, user_id):
    earned = db.scalar(select(func.coalesce(func.sum(ReferralReward.amount_nano), 0)).where(
        ReferralReward.referrer_id == user_id, ReferralReward.status == 'credited'))
    claimed = db.scalar(select(func.coalesce(func.sum(WalletTransaction.amount_nano), 0)).where(
        WalletTransaction.user_id == user_id, WalletTransaction.kind == 'referral', WalletTransaction.source == 'earned'))
    return max(0, int(earned) - int(claimed))


def _credit(db, reward):
    account = db.get(WalletAccount, (reward.referrer_id, 'referral'))
    if account.balance + reward.amount_nano > CAP:
        reward.status = 'held'
        return
    if reward.amount_nano:
        post_transfer(db, reward.referrer_id, f'__referral:{reward.quote_id}',
                      hashlib.sha256(reward.quote_id.encode()).hexdigest(), 'referral_credit', 0,
                      'treasury', 'referral', reward.amount_nano, source='exchange_fee')
    reward.status = 'credited'


def accrue_trade_reward(db, quote):
    if db.get(ReferralReward, quote.id) is not None:
        return
    binding = db.get(ReferralBinding, quote.user_id)
    if binding is None:
        return
    rate = quote.payload.get('referral_rate_bps', 0)
    fee = int(quote.payload.get('fee_nano', '0'))
    turnover = int(quote.payload['received_nano'])
    amount = min(turnover * rate // 10_000, fee)
    ensure_wallet(db, binding.referrer_id)
    reward = ReferralReward(quote_id=quote.id, user_id=quote.user_id, referrer_id=binding.referrer_id,
        turnover_nano=turnover, fee_nano=fee, amount_nano=amount, rate_bps=rate,
        status='held', created_at=int(time.time()))
    db.add(reward)
    _credit(db, reward)
    db.flush()


def release_held(db, user_id):
    rewards = db.scalars(select(ReferralReward).where(ReferralReward.referrer_id == user_id,
        ReferralReward.status == 'held').order_by(ReferralReward.created_at, ReferralReward.quote_id).limit(100)).all()
    for reward in rewards:
        _credit(db, reward)
    db.flush()


def register_referral_routes(app, database, current_session, rate_bps, bot_username):
    if type(rate_bps) is not int or not 0 <= rate_bps <= 10_000:
        raise ValueError('REFERRAL_RATE_BPS must be an integer from 0 to 10000')
    if bot_username and not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{4,31}', bot_username):
        raise ValueError('Invalid TELEGRAM_BOT_USERNAME')

    def summary(db, user_id):
        user = db.get(User, user_id)
        totals = db.execute(select(func.coalesce(func.sum(ReferralReward.turnover_nano), 0),
            func.coalesce(func.sum(ReferralReward.amount_nano), 0)).where(ReferralReward.referrer_id == user_id)).one()
        held = db.scalar(select(func.coalesce(func.sum(ReferralReward.amount_nano), 0)).where(
            ReferralReward.referrer_id == user_id, ReferralReward.status == 'held'))
        invited = db.scalar(select(func.count()).select_from(ReferralBinding).where(ReferralBinding.referrer_id == user_id))
        return {'asset': 'DEMO_TON', 'invited_count': invited, 'turnover_nano': str(totals[0]),
            'earned_nano': str(totals[1]), 'available_nano': str(earned_available(db, user_id)),
            'held_nano': str(held), 'rate_bps': rate_bps,
            'invite_url': f'https://t.me/{bot_username}?startapp=ref_{user.referral_code}' if bot_username else None}

    @app.get('/api/referrals')
    def get_referrals(db: Session = Depends(database), session=Depends(current_session)):
        user_id = lock_actor(db, session)
        ensure_wallet(db, user_id)
        release_held(db, user_id)
        result = summary(db, user_id)
        db.commit()
        return result

    class ClaimInput(BaseModel):
        model_config = ConfigDict(extra='forbid', strict=True)

    Key = Annotated[str, Header(alias='Idempotency-Key', min_length=1, max_length=128, pattern=r'^[!-~]+$')]

    @app.post('/api/referrals/claim')
    def claim(body: ClaimInput, key: Key, db: Session = Depends(database), session=Depends(current_session)):
        user_id = lock_actor(db, session)
        ensure_wallet(db, user_id)
        ledger_key = 'referral:' + hashlib.sha256(key.encode()).hexdigest()
        previous = db.scalar(select(WalletTransaction).where(WalletTransaction.user_id == user_id,
            WalletTransaction.key == ledger_key))
        if previous is None:
            release_held(db, user_id)
            amount = earned_available(db, user_id)
            if amount <= 0:
                raise HTTPException(409, 'No earned referral reward available')
            post_transfer(db, user_id, ledger_key, 'referral-claim-v1', 'referral', amount,
                          'referral', 'wallet', amount, source='earned')
            release_held(db, user_id)
        result = {'wallet': wallet_snapshot(db, user_id), 'referral': summary(db, user_id)}
        db.commit()
        return result
