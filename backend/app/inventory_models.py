"""Persistent DEMO inventory and per-user mutation receipts."""

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class InventoryInit(Base):
    __tablename__ = "inventory_init"
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), primary_key=True)


class InventoryGift(Base):
    __tablename__ = "inventory_gifts"
    __table_args__ = {"sqlite_autoincrement": True}
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    catalog_id: Mapped[int] = mapped_column(Integer)
    pledged: Mapped[bool] = mapped_column(Boolean, default=False)
    pledge_supported: Mapped[bool] = mapped_column(Boolean, default=True)


class InventoryReceipt(Base):
    __tablename__ = "inventory_receipts"
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
