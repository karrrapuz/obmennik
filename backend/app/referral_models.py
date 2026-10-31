"""First-launch attribution and immutable per-exchange referral entitlements."""
from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class ReferralBinding(Base):
    __tablename__ = 'referral_bindings'
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'), primary_key=True)
    referrer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'), index=True)
    created_at: Mapped[int] = mapped_column(BigInteger)
    __table_args__ = (
        CheckConstraint('user_id <> referrer_id', name='referral_not_self'),
        UniqueConstraint('user_id', 'referrer_id', name='referral_binding_pair'),
    )


class ReferralReward(Base):
    __tablename__ = 'referral_rewards'
    quote_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'))
    referrer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'), index=True)
    turnover_nano: Mapped[int] = mapped_column(BigInteger)
    fee_nano: Mapped[int] = mapped_column(BigInteger)
    amount_nano: Mapped[int] = mapped_column(BigInteger)
    rate_bps: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[int] = mapped_column(BigInteger)
    __table_args__ = (
        ForeignKeyConstraint(['quote_id', 'user_id'], ['trade_quotes.id', 'trade_quotes.user_id']),
        ForeignKeyConstraint(['user_id', 'referrer_id'], ['referral_bindings.user_id', 'referral_bindings.referrer_id']),
        CheckConstraint('user_id <> referrer_id', name='reward_not_self'),
        CheckConstraint('turnover_nano > 0 AND fee_nano >= 0 AND amount_nano >= 0 AND amount_nano <= fee_nano', name='reward_amount'),
        CheckConstraint('rate_bps >= 0 AND rate_bps <= 10000', name='reward_rate'),
        CheckConstraint('turnover_nano <= 100000000000000 AND fee_nano <= turnover_nano AND amount_nano <= turnover_nano * rate_bps / 10000', name='reward_turnover_limit'),
        CheckConstraint("status IN ('credited','held')", name='reward_status'),
    )
