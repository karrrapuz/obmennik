"""Frozen demo trade quotes and user-scoped execution receipts."""
from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, ForeignKeyConstraint, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class TradeQuote(Base):
    __tablename__ = 'trade_quotes'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'), index=True)
    expires_at: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        CheckConstraint("status IN ('open','executed')", name='trade_quote_status'),
        UniqueConstraint('id', 'user_id', name='trade_quote_owner'),
    )


class TradeReceipt(Base):
    __tablename__ = 'trade_receipts'
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    quote_id: Mapped[str] = mapped_column(String(32))
    __table_args__ = (ForeignKeyConstraint(['quote_id', 'user_id'], ['trade_quotes.id', 'trade_quotes.user_id']),)
