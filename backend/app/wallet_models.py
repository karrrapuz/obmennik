"""DEMO_TON accounts and append-only application ledger (not custody of real TON)."""
from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class WalletAccount(Base):
    __tablename__ = 'wallet_accounts'
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    balance: Mapped[int] = mapped_column(BigInteger, default=0)
    __table_args__ = (
        CheckConstraint("kind IN ('wallet','referral','treasury')", name='wallet_account_kind'),
        CheckConstraint("kind = 'treasury' OR (balance >= 0 AND balance <= 100000000000000)", name='wallet_account_balance'),
    )


class WalletTransaction(Base):
    __tablename__ = 'wallet_transactions'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'), index=True)
    key: Mapped[str] = mapped_column(String(128))
    payload_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    amount_nano: Mapped[int] = mapped_column(BigInteger)
    # Internal nanoseconds preserve ordering of actions within one second.
    created_at: Mapped[int] = mapped_column(BigInteger)
    source: Mapped[str | None] = mapped_column(String(16))
    destination: Mapped[str | None] = mapped_column(String(256))
    __table_args__ = (
        UniqueConstraint('user_id', 'key', name='wallet_request_unique'),
        UniqueConstraint('id', 'user_id', name='wallet_transaction_owner'),
        CheckConstraint("kind IN ('seed','topup','withdraw','referral')", name='wallet_transaction_kind'),
    )


class WalletPosting(Base):
    __tablename__ = 'wallet_postings'
    transaction_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    account_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    amount: Mapped[int] = mapped_column(BigInteger)
    __table_args__ = (
        ForeignKeyConstraint(['transaction_id', 'user_id'], ['wallet_transactions.id', 'wallet_transactions.user_id']),
        ForeignKeyConstraint(['user_id', 'account_kind'], ['wallet_accounts.user_id', 'wallet_accounts.kind']),
        CheckConstraint('amount <> 0', name='wallet_posting_nonzero'),
    )
