"""Permanent grant markers, independent of withdrawable gift instances."""

from sqlalchemy import BigInteger, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class DemoSeasonalGrant(Base):
    __tablename__ = 'demo_seasonal_grants'
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'), primary_key=True)
    catalog_id: Mapped[int] = mapped_column(Integer, primary_key=True)
