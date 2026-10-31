"""One public, display-only market snapshot; no credentials or financial state."""
from sqlalchemy import BigInteger, CheckConstraint, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class MarketSnapshot(Base):
    __tablename__ = 'market_snapshots'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    captured_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    prices_json: Mapped[str | None] = mapped_column(Text)
    listings_json: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint('id = 1', name='market_singleton'),
        CheckConstraint('captured_at >= 0', name='market_capture_positive'),
        CheckConstraint('(prices_json IS NULL AND listings_json IS NULL AND captured_at = 0) OR '
                        '(prices_json IS NOT NULL AND listings_json IS NOT NULL AND captured_at > 0)',
                        name='market_snapshot_pair'),
    )
