"""Atomic demo loans; no real custody, price feed, or liquidation policy."""
import hashlib
import json
import logging
import time
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .inventory import ensure_inventory, inventory_snapshot, DEFAULT_GIFT_PROVIDER
from .gift_provider import GiftProvider
from .inventory_models import InventoryGift
from .ledger import ensure_wallet, lock_actor, lock_user, post_transfer, wallet_snapshot
from .loan_models import DemoLoan, LoanReceipt
from .models import User
from .wallet_models import WalletAccount

DAY = 86400
PRINCIPAL = 1_200_000_000
REPAYMENTS = {1: 1_240_000_000, 2: 1_280_000_000}
EXTEND_FEE = 10_000_000


class GiftInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    gift_id: StrictInt = Field(gt=0)


class CreateInput(GiftInput):
    weeks: StrictInt = Field(ge=1, le=2)


class AutopayInput(GiftInput):
    enabled: bool


class BatchInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    gift_ids: list[Annotated[StrictInt, Field(gt=0)]] = Field(min_length=1, max_length=100)


def import_legacy_reservations(db, user_id):
    gifts = db.scalars(select(InventoryGift).where(InventoryGift.user_id == user_id, InventoryGift.pledged.is_(True))).all()
    active = set(db.scalars(select(DemoLoan.gift_id).where(DemoLoan.user_id == user_id, DemoLoan.status == 'active')).all())
    now = int(time.time())
    for gift in gifts:
        if gift.id not in active:
            db.add(DemoLoan(id=uuid4().hex, user_id=user_id, gift_id=gift.id, weeks=1,
                principal=0, repayment=0, created_at=now, due_at=now + 7 * DAY,
                status='active', legacy=True, autopay=False))
            db.get(User, user_id).state_revision += 1
    db.flush()


def active_loans(db, user_id, ids):
    if len(ids) != len(set(ids)):
        raise HTTPException(422, 'Duplicate gift IDs')
    loans = db.scalars(select(DemoLoan).where(DemoLoan.user_id == user_id,
        DemoLoan.gift_id.in_(ids), DemoLoan.status == 'active')).all()
    if len(loans) != len(ids):
        raise HTTPException(409, 'Loans unavailable')
    return loans


def quote_for(loans):
    if any(loan.legacy for loan in loans):
        raise HTTPException(409, 'Legacy reservations can only be returned')
    interest = sum(loan.repayment - loan.principal for loan in loans)
    return {'interest_nano': str(interest), 'fee_nano': str(EXTEND_FEE), 'total_nano': str(interest + EXTEND_FEE)}


def settle(db, loan, key, digest):
    gift = db.get(InventoryGift, loan.gift_id)
    if not gift or gift.user_id != loan.user_id or not gift.pledged:
        raise HTTPException(409, 'Collateral unavailable')
    if loan.repayment:
        post_transfer(db, loan.user_id, key, digest, 'loan_repay', -loan.repayment,
                      'wallet', 'treasury', loan.repayment)
    else:
        db.get(User, loan.user_id).state_revision += 1
    loan.status = 'repaid'
    loan.autopay = False
    gift.pledged = False
    db.flush()


def process_user_autopay(db, user_id):
    now = int(time.time())
    loans = db.scalars(select(DemoLoan).where(DemoLoan.user_id == user_id,
        DemoLoan.status == 'active', DemoLoan.autopay.is_(True), DemoLoan.legacy.is_(False),
        DemoLoan.due_at <= now).order_by(DemoLoan.due_at, DemoLoan.id)).all()
    for loan in loans:
        if loan.last_autopay_attempt is not None and now - loan.last_autopay_attempt < 60:
            continue
        loan.last_autopay_attempt = now
        if db.get(WalletAccount, (user_id, 'wallet')).balance >= loan.repayment:
            settle(db, loan, f'auto:{loan.id}:{loan.due_at}', 'autopay')


def process_due_loans(engine):
    try:
        with Session(engine) as db:
            now = int(time.time())
            users = db.scalars(select(DemoLoan.user_id).where(DemoLoan.status == 'active',
                DemoLoan.autopay.is_(True), DemoLoan.legacy.is_(False), DemoLoan.due_at <= now,
                or_(DemoLoan.last_autopay_attempt.is_(None), DemoLoan.last_autopay_attempt <= now - 60))
                .group_by(DemoLoan.user_id)
                .order_by(func.min(func.coalesce(DemoLoan.last_autopay_attempt, 0)), DemoLoan.user_id)
                .limit(100)).all()
    except Exception:
        logging.getLogger('giftmoney').error('Autopay discovery failed; retry on next tick')
        return
    for user_id in users:
        try:
            with Session(engine) as db:
                if lock_user(db, user_id) is None:
                    continue
                ensure_wallet(db, user_id)
                process_user_autopay(db, user_id)
                db.commit()
        except Exception:
            logging.getLogger('giftmoney').error('Autopay attempt failed; retry on next tick')


def register_loan_routes(app, database, current_session, provider: GiftProvider = DEFAULT_GIFT_PROVIDER):
    templates = {gift['id']: gift for gift in provider.catalog}
    def snapshot(db, user_id):
        loans = db.scalars(select(DemoLoan).where(DemoLoan.user_id == user_id).order_by(DemoLoan.created_at, DemoLoan.id)).all()
        return {'revision': db.get(User, user_id).state_revision, 'loans': [{'id': loan.id, 'gift_id': loan.gift_id, 'weeks': loan.weeks,
            'principal_nano': str(loan.principal), 'repayment_nano': str(loan.repayment),
            'due_at': loan.due_at, 'autopay': loan.autopay, 'status': loan.status, 'legacy': loan.legacy}
            for loan in loans],
            'terms': [{'weeks': weeks, 'principal_nano': str(PRINCIPAL), 'repayment_nano': str(repayment)}
                      for weeks, repayment in REPAYMENTS.items()],
            'wallet': wallet_snapshot(db, user_id), 'inventory': inventory_snapshot(db, user_id, provider)}

    def prepare(db, session):
        user_id = lock_actor(db, session)
        ensure_wallet(db, user_id)
        ensure_inventory(db, user_id, provider)
        import_legacy_reservations(db, user_id)
        return user_id

    @app.get('/api/loans')
    def get_loans(db: Session = Depends(database), session=Depends(current_session)):
        user_id = prepare(db, session)
        process_user_autopay(db, user_id)
        result = snapshot(db, user_id)
        db.commit()
        return result

    @app.post('/api/loans/quote')
    def quote(body: BatchInput, db: Session = Depends(database), session=Depends(current_session)):
        user_id = prepare(db, session)
        result = quote_for(active_loans(db, user_id, body.gift_ids))
        db.commit()
        return result

    def mutate(operation, body, key, db, session):
        user_id = prepare(db, session)
        payload = {'operation': operation, 'payload': body.model_dump()}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        receipt = db.get(LoanReceipt, (user_id, key))
        if receipt:
            if receipt.payload_hash != digest:
                raise HTTPException(409, 'Idempotency key already used')
            result = snapshot(db, user_id)
            db.commit()
            return result
        ledger_key = 'loan:' + hashlib.sha256(key.encode()).hexdigest()
        if operation == 'create':
            provider.require_available()
            gift = db.get(InventoryGift, body.gift_id)
            if (not gift or gift.user_id != user_id or gift.pledged or not gift.pledge_supported
                    or templates[gift.catalog_id].get('pledgeSupported') is False):
                raise HTTPException(409, 'Gift unavailable for loan')
            now = int(time.time())
            loan = DemoLoan(id=uuid4().hex, user_id=user_id, gift_id=gift.id, weeks=body.weeks,
                principal=PRINCIPAL, repayment=REPAYMENTS[body.weeks], created_at=now,
                due_at=now + body.weeks * 7 * DAY, autopay=False, status='active', legacy=False)
            db.add(loan)
            gift.pledged = True
            post_transfer(db, user_id, ledger_key, digest, 'loan_credit', PRINCIPAL,
                          'treasury', 'wallet', PRINCIPAL)
        elif operation == 'extend':
            loans = active_loans(db, user_id, body.gift_ids)
            total = int(quote_for(loans)['total_nano'])
            post_transfer(db, user_id, ledger_key, digest, 'loan_extend', -total, 'wallet', 'treasury', total)
            for loan in loans:
                loan.due_at = max(int(time.time()), loan.due_at) + 14 * DAY
                loan.last_autopay_attempt = None
        else:
            loan = active_loans(db, user_id, [body.gift_id])[0]
            if operation == 'repay':
                settle(db, loan, ledger_key, digest)
            elif loan.legacy:
                raise HTTPException(409, 'Legacy reservations can only be returned')
            elif operation == 'autopay':
                loan.autopay = body.enabled
                loan.last_autopay_attempt = None
                db.get(User, user_id).state_revision += 1
            else:
                interest = loan.repayment - loan.principal
                post_transfer(db, user_id, ledger_key, digest, 'loan_interest', -interest,
                              'wallet', 'treasury', interest)
                loan.due_at = max(int(time.time()), loan.due_at) + loan.weeks * 7 * DAY
                loan.last_autopay_attempt = None
        db.flush()
        db.add(LoanReceipt(user_id=user_id, key=key, payload_hash=digest, payload=payload))
        result = snapshot(db, user_id)
        db.commit()
        return result

    Key = Annotated[str, Header(alias='Idempotency-Key', min_length=1, max_length=128, pattern=r'^[!-~]+$')]

    @app.post('/api/loans/create')
    def create(body: CreateInput, key: Key, db: Session = Depends(database), session=Depends(current_session)):
        return mutate('create', body, key, db, session)

    @app.post('/api/loans/repay')
    def repay(body: GiftInput, key: Key, db: Session = Depends(database), session=Depends(current_session)):
        return mutate('repay', body, key, db, session)

    @app.post('/api/loans/pay-interest')
    def pay_interest(body: GiftInput, key: Key, db: Session = Depends(database), session=Depends(current_session)):
        return mutate('interest', body, key, db, session)

    @app.post('/api/loans/extend')
    def extend(body: BatchInput, key: Key, db: Session = Depends(database), session=Depends(current_session)):
        return mutate('extend', body, key, db, session)

    @app.post('/api/loans/autopay')
    def autopay(body: AutopayInput, key: Key, db: Session = Depends(database), session=Depends(current_session)):
        return mutate('autopay', body, key, db, session)
