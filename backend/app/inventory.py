"""DEMO-only gifts: no payments, Telegram transfers, or external mutations."""

import hashlib
import json
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy import select
from sqlalchemy.orm import Session

from .inventory_models import InventoryGift, InventoryInit, InventoryReceipt
from .models import User


GiftId = Annotated[StrictInt, Field(gt=0)]
GiftIds = Annotated[list[GiftId], Field(min_length=1, max_length=100)]


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WithdrawInput(EmptyInput):
    ids: GiftIds


class ExchangeInput(EmptyInput):
    offered_ids: GiftIds
    received_ids: GiftIds


class GiftInput(EmptyInput):
    id: GiftId


def register_inventory_routes(app, database, current_session):
    path = Path(__file__).resolve().parents[1] / "data/catalog-sample.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    templates = {gift["id"]: gift for gift in catalog}
    blocked_id = catalog[0]["id"]

    def actor(db, session):
        user = db.scalar(select(User).where(User.id == session.user_id).with_for_update())
        if user is None:
            raise HTTPException(401, "Authentication required")
        return user.id

    def seed(db, user_id):
        if db.get(InventoryInit, user_id) is None:
            db.add(InventoryInit(user_id=user_id))
            db.flush()
            for index, template in enumerate(catalog[:5]):
                db.add(InventoryGift(user_id=user_id, catalog_id=template["id"],
                                     pledged=False, pledge_supported=index < 3))
            db.flush()

    def snapshot(db, user_id):
        result = {"inventory": [], "pledged": [], "catalog": [
            {**gift, "blockTradeGift": gift["id"] == blocked_id} for gift in catalog]}
        rows = db.scalars(select(InventoryGift).where(
            InventoryGift.user_id == user_id).order_by(InventoryGift.id)).all()
        for row in rows:
            gift = {**templates[row.catalog_id], "id": row.id, "catalogId": row.catalog_id,
                    "blockTradeGift": False, "pledgeSupported": row.pledge_supported}
            result["pledged" if row.pledged else "inventory"].append(gift)
        return result

    def unique(ids):
        if len(ids) != len(set(ids)):
            raise HTTPException(422, "Duplicate gift IDs")

    def owned(db, user_id, ids, pledged=False):
        unique(ids)
        rows = db.scalars(select(InventoryGift).where(
            InventoryGift.user_id == user_id, InventoryGift.id.in_(ids),
            InventoryGift.pledged == pledged)).all()
        if len(rows) != len(ids):
            raise HTTPException(409, "Gifts unavailable")
        return rows

    def mutate(operation, body, key, db, session):
        user_id = actor(db, session)
        digest = hashlib.sha256(json.dumps(
            {"operation": operation, "payload": body.model_dump()},
            sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        receipt = db.get(InventoryReceipt, (user_id, key))
        if receipt is not None:
            if receipt.payload_hash != digest:
                raise HTTPException(409, "Idempotency key already used")
            # Idempotent business effect, but always return current canonical state.
            return snapshot(db, user_id)
        seed(db, user_id)
        if operation == "deposit":
            db.add(InventoryGift(user_id=user_id, catalog_id=catalog[1]["id"],
                                 pledged=False, pledge_supported=True))
        elif operation in {"withdraw", "exchange"}:
            ids = body.ids if operation == "withdraw" else body.offered_ids
            rows = owned(db, user_id, ids)
            if operation == "exchange":
                unique(body.received_ids)
                if any(id not in templates or id == blocked_id for id in body.received_ids):
                    raise HTTPException(409, "Catalog gifts unavailable")
                for id in body.received_ids:
                    db.add(InventoryGift(user_id=user_id, catalog_id=id,
                                         pledged=False, pledge_supported=True))
            for row in rows:
                db.delete(row)
        else:
            row = owned(db, user_id, [body.id], pledged=operation == "release")[0]
            if operation == "pledge" and not row.pledge_supported:
                raise HTTPException(409, "Pledge unsupported")
            row.pledged = operation == "pledge"
        db.flush()
        result = snapshot(db, user_id)
        db.add(InventoryReceipt(user_id=user_id, key=key, payload_hash=digest, result=result))
        db.commit()
        return result

    Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128,
                                pattern=r"^[!-~]+$")]

    @app.get("/api/inventory")
    def inventory(db: Session = Depends(database), session=Depends(current_session)):
        user_id = actor(db, session)
        seed(db, user_id)
        result = snapshot(db, user_id)
        db.commit()
        return result

    @app.post("/api/inventory/demo-deposit")
    def deposit(body: EmptyInput, key: Key, db: Session = Depends(database), session=Depends(current_session)):
        return mutate("deposit", body, key, db, session)

    @app.post("/api/inventory/demo-withdraw")
    def withdraw(body: WithdrawInput, key: Key, db: Session = Depends(database), session=Depends(current_session)):
        return mutate("withdraw", body, key, db, session)

    @app.post("/api/inventory/demo-exchange")
    def exchange(body: ExchangeInput, key: Key, db: Session = Depends(database), session=Depends(current_session)):
        return mutate("exchange", body, key, db, session)

    @app.post("/api/inventory/demo-pledge")
    def pledge(body: GiftInput, key: Key, db: Session = Depends(database), session=Depends(current_session)):
        return mutate("pledge", body, key, db, session)

    @app.post("/api/inventory/demo-release")
    def release(body: GiftInput, key: Key, db: Session = Depends(database), session=Depends(current_session)):
        return mutate("release", body, key, db, session)
