"""Server-owned loan terms and idempotent lifecycle commands, DEMO_TON only."""
from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Integer, JSON, String, Index, text
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base


class DemoLoan(Base):
    __tablename__ = 'demo_loans'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'), index=True)
    # Historical loans survive withdrawal of a repaid gift instance.
    gift_id: Mapped[int] = mapped_column(Integer)
    weeks: Mapped[int] = mapped_column(Integer)
    principal: Mapped[int] = mapped_column(BigInteger)
    repayment: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[int] = mapped_column(BigInteger)
    due_at: Mapped[int] = mapped_column(BigInteger)
    autopay: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default='active')
    legacy: Mapped[bool] = mapped_column(Boolean, default=False)
    last_autopay_attempt: Mapped[int | None] = mapped_column(BigInteger)
    __table_args__ = (
        CheckConstraint('weeks IN (1,2)', name='loan_weeks'),
        CheckConstraint('principal >= 0 AND repayment >= principal', name='loan_amounts'),
        CheckConstraint("status IN ('active','repaid')", name='loan_status'),
        Index('ix_demo_loans_active_gift', 'gift_id', unique=True,
              postgresql_where=text("status = 'active'"), sqlite_where=text("status = 'active'")),
    )


class LoanReceipt(Base):
    __tablename__ = 'loan_receipts'
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
