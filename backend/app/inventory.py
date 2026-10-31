"""DEMO-only gifts: no payments, Telegram transfers, or external mutations."""

import hashlib
import json
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy import select
from sqlalchemy.orm import Session

from .inventory_models import InventoryGift, InventoryInit, InventoryReceipt
from .models import User
from .gift_provider import GiftProvider, create_gift_provider
from .ledger import lock_actor
from .grant_models import DemoSeasonalGrant

DEFAULT_GIFT_PROVIDER = create_gift_provider('demo')


GiftId = Annotated[StrictInt, Field(gt=0)]
GiftIds = Annotated[list[GiftId], Field(min_length=1, max_length=100)]


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WithdrawInput(EmptyInput):
    ids: GiftIds


class GiftInput(EmptyInput):
    id: GiftId


def ensure_inventory(db, user_id, provider: GiftProvider = DEFAULT_GIFT_PROVIDER):
    if provider.mode != 'demo':
        return
    changed = False
    if db.get(InventoryInit, user_id) is None:
        initial = provider.initial_gifts()
        if not initial:
            return
        db.add(InventoryInit(user_id=user_id))
        db.flush()
        for catalog_id, supported in initial:
            db.add(InventoryGift(user_id=user_id, catalog_id=catalog_id, pledged=False, pledge_supported=supported))
        changed = True
    granted = set(db.scalars(select(DemoSeasonalGrant.catalog_id).where(
        DemoSeasonalGrant.user_id == user_id)).all())
    for catalog_id in provider.seasonal_gifts():
        if catalog_id not in granted:
            db.add(DemoSeasonalGrant(user_id=user_id, catalog_id=catalog_id))
            db.add(InventoryGift(user_id=user_id, catalog_id=catalog_id,
                                 pledged=False, pledge_supported=False))
            changed = True
    if changed:
        db.get(User, user_id).state_revision += 1
        db.flush()


def inventory_snapshot(db, user_id, provider: GiftProvider = DEFAULT_GIFT_PROVIDER):
    catalog = provider.catalog
    templates = {gift['id']: gift for gift in catalog}
    result = {'revision': db.get(User, user_id).state_revision, 'inventory': [], 'pledged': [], 'catalog': [
        {**gift, 'blockTradeGift': gift['id'] == catalog[0]['id'] or gift.get('tradeSupported') is False}
        for gift in catalog]}
    for row in db.scalars(select(InventoryGift).where(InventoryGift.user_id == user_id).order_by(InventoryGift.id)).all():
        gift = {**templates[row.catalog_id], 'id': row.id, 'catalogId': row.catalog_id,
                'blockTradeGift': templates[row.catalog_id].get('tradeSupported') is False,
                'pledgeSupported': row.pledge_supported and templates[row.catalog_id].get('pledgeSupported', True)}
        result['pledged' if row.pledged else 'inventory'].append(gift)
    return result


def register_inventory_routes(app, database, current_session, provider: GiftProvider = DEFAULT_GIFT_PROVIDER):
    templates = {gift['id']: gift for gift in provider.catalog}
    def actor(db, session):
        return lock_actor(db, session)

    def seed(db, user_id):
        ensure_inventory(db, user_id, provider)

    def snapshot(db, user_id):
        return inventory_snapshot(db, user_id, provider)

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
        provider.require_available()
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
            db.add(InventoryGift(user_id=user_id, catalog_id=provider.deposit_catalog_id(),
                                 pledged=False, pledge_supported=True))
        elif operation == "withdraw":
            rows = owned(db, user_id, body.ids)
            for row in rows:
                db.delete(row)
        else:
            row = owned(db, user_id, [body.id], pledged=operation == "release")[0]
            if operation == 'release':
                from .loan_models import DemoLoan
                if db.scalar(select(DemoLoan.id).where(DemoLoan.gift_id == row.id, DemoLoan.status == 'active')):
                    raise HTTPException(409, 'Close the loan to release its gift')
            if operation == "pledge" and (not row.pledge_supported or
                    templates[row.catalog_id].get('pledgeSupported') is False):
                raise HTTPException(409, "Pledge unsupported")
            row.pledged = operation == "pledge"
        db.get(User, user_id).state_revision += 1
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
    def exchange(session=Depends(current_session)):
        raise HTTPException(410, 'Create and execute a server trade quote')

    @app.post("/api/inventory/demo-pledge")
    def pledge(body: GiftInput, key: Key, db: Session = Depends(database), session=Depends(current_session)):
        return mutate("pledge", body, key, db, session)

    @app.post("/api/inventory/demo-release")
    def release(body: GiftInput, key: Key, db: Session = Depends(database), session=Depends(current_session)):
        return mutate("release", body, key, db, session)
