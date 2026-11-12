"""Read-only snapshots explicitly shared by an authenticated user."""
import hashlib
import json
import secrets
import time
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy import BigInteger, ForeignKey, JSON, String, select
from sqlalchemy.orm import Mapped, mapped_column, Session

from .models import Base
from .inventory import catalog_gift, ensure_inventory, owned_gift
from .inventory_models import InventoryGift
from .ledger import lock_actor


class SharedGift(Base):
    __tablename__ = 'shared_gifts'
    token: Mapped[str] = mapped_column(String(48), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'), index=True)
    snapshot: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[int] = mapped_column(BigInteger)


class ShareInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    source: Literal['inventory', 'exchange']
    gift_id: StrictInt = Field(gt=0)


def register_gift_link_routes(app, database, current_session, provider):
    templates = {gift['id']: gift for gift in provider.catalog}

    @app.post('/api/gifts/share')
    def prepare(body: ShareInput, db: Session = Depends(database), session=Depends(current_session)):
        user_id = lock_actor(db, session)
        provider.require_available()
        ensure_inventory(db, user_id, provider)
        if body.source == 'exchange':
            template = templates.get(body.gift_id)
            gift = catalog_gift(template, provider) if template is not None else None
        else:
            row = db.scalar(select(InventoryGift).where(
                InventoryGift.id == body.gift_id, InventoryGift.user_id == user_id))
            gift = owned_gift(row, templates[row.catalog_id]) if row is not None else None
        if gift is None:
            raise HTTPException(404, 'Gift unavailable')
        fingerprint = hashlib.sha256(json.dumps([user_id, body.source, gift], sort_keys=True).encode()).hexdigest()
        shared = db.scalar(select(SharedGift).where(SharedGift.fingerprint == fingerprint))
        now = int(time.time())
        if shared is None:
            shared = SharedGift(token=secrets.token_urlsafe(24), fingerprint=fingerprint,
                user_id=user_id, snapshot=gift, expires_at=now + 30 * 86400)
            db.add(shared)
        elif shared.expires_at <= now:
            shared.expires_at = now + 30 * 86400
        result = {'share_ref': shared.token, 'expires_at': shared.expires_at}
        db.commit()
        return result

    @app.get('/api/gifts/shared/{token}')
    def resolve(token: str, db: Session = Depends(database)):
        if len(token) != 32 or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-' for c in token):
            raise HTTPException(404, 'Gift link unavailable')
        shared = db.get(SharedGift, token)
        if shared is None or shared.expires_at <= int(time.time()):
            raise HTTPException(404, 'Gift link unavailable')
        return {'gift': {**shared.snapshot, 'sharedReadOnly': True, 'shareToken': token}}
