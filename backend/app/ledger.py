"""Shared transactional ledger for demo wallet and loans."""
import time
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select, update
from .models import User
from .wallet_models import WalletAccount, WalletPosting, WalletTransaction

CAP = 100_000_000_000_000
SINGLE_LIMIT = 10_000_000_000_000
REFERRAL_SEED = 5_000_000_000

def lock_user(db, user_id):
    # SQLite has no row locks: acquire its write lock before reading mutable state.
    if db.get_bind().dialect.name == 'sqlite':
        db.execute(update(User).where(User.id == user_id).values(state_revision=User.state_revision),
                   execution_options={'synchronize_session': False})
    return db.scalar(select(User).where(User.id == user_id).with_for_update())


def lock_actor(db, session):
    user = lock_user(db, session.user_id)
    if user is None:
        raise HTTPException(401, 'Authentication required')
    return user.id

def post_transfer(db, user_id, key, digest, kind, wallet_delta, debit, credit, amount, source=None, destination=None):
    if amount <= 0 or debit == credit:
        raise ValueError('A transfer requires a positive amount and distinct accounts')
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
    db.get(User, user_id).state_revision += 1
    db.flush()

def ensure_wallet(db, user_id):
    if db.get(WalletAccount, (user_id, 'wallet')) is None:
        db.add_all([WalletAccount(user_id=user_id, kind=kind, balance=0)
                    for kind in ('wallet', 'referral', 'treasury')])
        db.flush()
        post_transfer(db, user_id, '__wallet_seed_v1__', 'seed-v1', 'seed', 0,
               'treasury', 'referral', REFERRAL_SEED)

def wallet_snapshot(db, user_id):
    transactions = db.scalars(select(WalletTransaction).where(
        WalletTransaction.user_id == user_id).order_by(
            WalletTransaction.created_at.desc(), WalletTransaction.id.desc()).limit(50)).all()
    return {
        'revision': db.get(User, user_id).state_revision,
        'asset': 'DEMO_TON',
        'balance_nano': str(db.get(WalletAccount, (user_id, 'wallet')).balance),
        'referral_nano': str(db.get(WalletAccount, (user_id, 'referral')).balance),
        'transactions': [{'id': tx.id, 'kind': tx.kind, 'amount_nano': str(tx.amount_nano),
                          'created_at': tx.created_at // 1_000_000_000} for tx in transactions],
    }
