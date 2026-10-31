"""Persistent test wallet. No blockchain/provider calls or real money credits."""
import hashlib
import json
from typing import Annotated, Literal

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .wallet_models import WalletAccount, WalletTransaction
from .ledger import CAP, SINGLE_LIMIT, lock_actor as actor, post_transfer as record, ensure_wallet as seed, wallet_snapshot as snapshot
from .referrals import earned_available



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
    def mutate(kind, body, key, db, session):
        if key.startswith(('trade:', 'loan:', 'auto:', 'referral:', '__')):
            raise HTTPException(422, 'Reserved operation key prefix')
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
            amount = db.get(WalletAccount, (user_id, 'referral')).balance - earned_available(db, user_id)
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
