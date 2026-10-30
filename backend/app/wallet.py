"""Persistent test wallet. No blockchain/provider calls or real money credits."""
import hashlib
import json
import time
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import User
from .wallet_models import WalletAccount, WalletPosting, WalletTransaction

CAP = 100_000_000_000_000
SINGLE_LIMIT = 10_000_000_000_000
REFERRAL_SEED = 5_000_000_000


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class AmountInput(EmptyInput):
    amount_nano: str = Field(pattern=r'^[1-9][0-9]{0,13}$', max_length=14)

    @field_validator('amount_nano')
    @classmethod
    def amount_limit(cls, value):
        if int(value) > SINGLE_LIMIT:
            raise ValueError('Demo amount limit exceeded')
        return value


class TopupInput(AmountInput):
    source: Literal['wallet', 'cryptobot']


class WithdrawInput(AmountInput):
    destination: str = Field(min_length=1, max_length=256)

    @field_validator('destination')
    @classmethod
    def nonempty_destination(cls, value):
        if not value.strip():
            raise ValueError('Demo destination is required')
        return value


def register_wallet_routes(app, database, current_session):
    def actor(db, session):
        user = db.scalar(select(User).where(User.id == session.user_id).with_for_update())
        if user is None:
            raise HTTPException(401, 'Authentication required')
        return user.id

    def record(db, user_id, key, digest, kind, wallet_delta, debit, credit, amount, source=None, destination=None):
        accounts = {kind: db.get(WalletAccount, (user_id, kind)) for kind in (debit, credit)}
        if debit != 'treasury' and accounts[debit].balance < amount:
            raise HTTPException(409, 'Insufficient test balance')
        if credit != 'treasury' and accounts[credit].balance + amount > CAP:
            raise HTTPException(409, 'Test balance limit exceeded')
        transaction = WalletTransaction(id=uuid4().hex, user_id=user_id, key=key,
            payload_hash=digest, kind=kind, amount_nano=wallet_delta, created_at=time.time_ns(),
            source=source, destination=destination)
        db.add(transaction)
        db.flush()
        accounts[debit].balance -= amount
        accounts[credit].balance += amount
        db.add_all([
            WalletPosting(transaction_id=transaction.id, user_id=user_id, account_kind=debit, amount=-amount),
            WalletPosting(transaction_id=transaction.id, user_id=user_id, account_kind=credit, amount=amount),
        ])
        db.flush()

    def seed(db, user_id):
        if db.get(WalletAccount, (user_id, 'wallet')) is None:
            db.add_all([WalletAccount(user_id=user_id, kind=kind, balance=0)
                        for kind in ('wallet', 'referral', 'treasury')])
            db.flush()
            record(db, user_id, '__wallet_seed_v1__', 'seed-v1', 'seed', 0,
                   'treasury', 'referral', REFERRAL_SEED)

    def snapshot(db, user_id):
        transactions = db.scalars(select(WalletTransaction).where(
            WalletTransaction.user_id == user_id).order_by(
                WalletTransaction.created_at.desc(), WalletTransaction.id.desc()).limit(50)).all()
        return {
            'asset': 'DEMO_TON',
            'balance_nano': str(db.get(WalletAccount, (user_id, 'wallet')).balance),
            'referral_nano': str(db.get(WalletAccount, (user_id, 'referral')).balance),
            'transactions': [{'id': tx.id, 'kind': tx.kind, 'amount_nano': str(tx.amount_nano),
                              'created_at': tx.created_at // 1_000_000_000} for tx in transactions],
        }

    def mutate(kind, body, key, db, session):
        user_id = actor(db, session)
        seed(db, user_id)
        digest = hashlib.sha256(json.dumps({'kind': kind, 'body': body.model_dump()},
            sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        previous = db.scalar(select(WalletTransaction).where(
            WalletTransaction.user_id == user_id, WalletTransaction.key == key))
        if previous is not None:
            if previous.payload_hash != digest:
                raise HTTPException(409, 'Idempotency key already used')
            result = snapshot(db, user_id)
            db.commit()
            return result
        if kind == 'referral':
            amount = db.get(WalletAccount, (user_id, 'referral')).balance
            if amount <= 0:
                raise HTTPException(409, 'No test referral reward available')
            record(db, user_id, key, digest, kind, amount, 'referral', 'wallet', amount)
        else:
            amount = int(body.amount_nano)
            if kind == 'topup':
                record(db, user_id, key, digest, kind, amount, 'treasury', 'wallet', amount, source=body.source)
            else:
                record(db, user_id, key, digest, kind, -amount, 'wallet', 'treasury', amount, destination=body.destination)
        result = snapshot(db, user_id)
        db.commit()
        return result

    Key = Annotated[str, Header(alias='Idempotency-Key', min_length=1, max_length=128, pattern=r'^[!-~]+$')]

    @app.get('/api/wallet')
    def get_wallet(db: Session = Depends(database), session=Depends(current_session)):
        user_id = actor(db, session)
        seed(db, user_id)
        result = snapshot(db, user_id)
        db.commit()
        return result

    @app.post('/api/wallet/demo-topup')
    def topup(body: TopupInput, key: Key, db: Session = Depends(database), session=Depends(current_session)):
        return mutate('topup', body, key, db, session)

    @app.post('/api/wallet/demo-withdraw')
    def withdraw(body: WithdrawInput, key: Key, db: Session = Depends(database), session=Depends(current_session)):
        return mutate('withdraw', body, key, db, session)

    @app.post('/api/wallet/demo-referral')
    def referral(body: EmptyInput, key: Key, db: Session = Depends(database), session=Depends(current_session)):
        return mutate('referral', body, key, db, session)
