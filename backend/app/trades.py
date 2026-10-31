"""Server-priced atomic demo exchanges. No external gift delivery."""
import hashlib
import time
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy import select
from sqlalchemy.orm import Session

from .gift_provider import GiftProvider
from .inventory import ensure_inventory, inventory_snapshot
from .inventory_models import InventoryGift
from .ledger import CAP, ensure_wallet, lock_actor, post_transfer, wallet_snapshot
from .models import User
from .pricing import PriceProvider, ask_price
from .trade_models import TradeQuote, TradeReceipt

Ids = Annotated[list[Annotated[StrictInt, Field(gt=0)]], Field(min_length=1, max_length=100)]


class QuoteInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    offered_ids: Ids
    received_ids: Ids


class ExecuteInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    quote_id: str = Field(pattern=r'^[a-f0-9]{32}$')


def register_trade_routes(app, database, current_session, provider: GiftProvider,
                          prices: PriceProvider, markup_bps: int, quote_ttl: int):
    if type(markup_bps) is not int or not 0 <= markup_bps <= 10_000:
        raise ValueError('TRADE_MARKUP_BPS must be an integer from 0 to 10000')
    if type(quote_ttl) is not int or not 30 <= quote_ttl <= 600:
        raise ValueError('TRADE_QUOTE_TTL must be an integer from 30 to 600')
    templates = {gift['id']: gift for gift in provider.catalog}
    blocked_id = provider.catalog[0]['id']

    def base_price(catalog_id):
        try:
            value = prices.price(catalog_id)
        except (KeyError, ValueError):
            raise HTTPException(503, 'Price unavailable') from None
        if type(value) is not int or not 0 < value <= CAP:
            raise HTTPException(503, 'Invalid source price')
        return value

    def owned(db, user_id, ids):
        if len(ids) != len(set(ids)):
            raise HTTPException(422, 'Duplicate gift IDs')
        rows = db.scalars(select(InventoryGift).where(InventoryGift.user_id == user_id,
            InventoryGift.id.in_(ids), InventoryGift.pledged.is_(False))).all()
        if len(rows) != len(ids):
            raise HTTPException(409, 'Offered gifts unavailable')
        if any(templates[row.catalog_id].get('tradeSupported') is False for row in rows):
            raise HTTPException(409, 'Offered gifts are unpriced previews')
        return {row.id: row for row in rows}

    def received_available(ids):
        if len(ids) != len(set(ids)):
            raise HTTPException(422, 'Duplicate gift IDs')
        if any(id not in templates or id == blocked_id or templates[id].get('tradeSupported') is False for id in ids):
            raise HTTPException(409, 'Catalog gifts unavailable')

    def public_quote(quote):
        return {**quote.payload, 'id': quote.id, 'expires_at': quote.expires_at, 'status': quote.status}

    def find_quote(db, user_id, quote_id):
        quote = db.get(TradeQuote, quote_id)
        if quote is None or quote.user_id != user_id:
            raise HTTPException(404, 'Quote not found')
        return quote

    def snapshot(db, user_id, quote):
        return {'revision': db.get(User, user_id).state_revision, 'quote': public_quote(quote),
                'inventory': inventory_snapshot(db, user_id, provider), 'wallet': wallet_snapshot(db, user_id)}

    @app.post('/api/trades/quote')
    def create_quote(body: QuoteInput, db: Session = Depends(database), session=Depends(current_session)):
        user_id = lock_actor(db, session)
        provider.require_available()
        now = int(time.time())
        expires_at = now + quote_ttl
        if prices.valid_until is not None:
            if type(prices.valid_until) is not int:
                raise HTTPException(503, 'Invalid price freshness')
            expires_at = min(expires_at, prices.valid_until)
        elif prices.source != 'sample':
            raise HTTPException(503, 'Price freshness unavailable')
        if expires_at <= now:
            raise HTTPException(503, 'Price source expired')
        if not isinstance(prices.source, str) or not 1 <= len(prices.source) <= 64 or not isinstance(prices.version, str) or not 1 <= len(prices.version) <= 128:
            raise HTTPException(503, 'Invalid price provenance')
        ensure_inventory(db, user_id, provider)
        ensure_wallet(db, user_id)
        rows = owned(db, user_id, body.offered_ids)
        received_available(body.received_ids)
        offered = [{'gift_id': id, 'catalog_id': rows[id].catalog_id,
                    'unit_nano': str(base_price(rows[id].catalog_id))} for id in body.offered_ids]
        received = [{'catalog_id': id, 'unit_nano': str(ask_price(base_price(id), markup_bps))}
                    for id in body.received_ids]
        offer = sum(int(item['unit_nano']) for item in offered)
        receive = sum(int(item['unit_nano']) for item in received)
        if offer > CAP or receive > CAP:
            raise HTTPException(422, 'Trade amount exceeds limit')
        delta = offer - receive
        quote = TradeQuote(id=uuid4().hex, user_id=user_id, expires_at=expires_at,
            status='open', payload={'asset': 'DEMO_TON', 'source': prices.source, 'source_version': prices.version,
                'markup_bps': markup_bps, 'offered': offered, 'received': received,
                'offered_nano': str(offer), 'received_nano': str(receive),
                'wallet_delta_nano': str(delta), 'required_balance_nano': str(max(-delta, 0))})
        db.add(quote)
        db.commit()
        return public_quote(quote)

    @app.get('/api/trades/quotes/{quote_id}')
    def get_quote(quote_id: str, db: Session = Depends(database), session=Depends(current_session)):
        return public_quote(find_quote(db, session.user_id, quote_id))

    Key = Annotated[str, Header(alias='Idempotency-Key', min_length=1, max_length=128, pattern=r'^[!-~]+$')]

    @app.post('/api/trades/execute')
    def execute(body: ExecuteInput, key: Key, db: Session = Depends(database), session=Depends(current_session)):
        user_id = lock_actor(db, session)
        digest = hashlib.sha256(body.quote_id.encode()).hexdigest()
        receipt = db.get(TradeReceipt, (user_id, key))
        if receipt and receipt.payload_hash != digest:
            raise HTTPException(409, 'Idempotency key already used')
        quote = find_quote(db, user_id, body.quote_id)
        if quote.status != 'executed':
            provider.require_available()
            if quote.expires_at <= int(time.time()):
                raise HTTPException(409, 'Quote expired')
            frozen = quote.payload
            offered = frozen['offered']
            rows = owned(db, user_id, [item['gift_id'] for item in offered])
            if any(rows[item['gift_id']].catalog_id != item['catalog_id'] for item in offered):
                raise HTTPException(409, 'Offered gifts changed')
            received_available([item['catalog_id'] for item in frozen['received']])
            ensure_wallet(db, user_id)
            delta = int(frozen['wallet_delta_nano'])
            if delta:
                post_transfer(db, user_id, f'trade:{quote.id}', digest,
                    'trade_credit' if delta > 0 else 'trade_debit', delta,
                    'treasury' if delta > 0 else 'wallet', 'wallet' if delta > 0 else 'treasury', abs(delta))
            for row in rows.values():
                db.delete(row)
            for item in frozen['received']:
                db.add(InventoryGift(user_id=user_id, catalog_id=item['catalog_id'], pledged=False, pledge_supported=True))
            db.get(User, user_id).state_revision += 1
            quote.status = 'executed'
            db.flush()
        if receipt is None:
            db.add(TradeReceipt(user_id=user_id, key=key, payload_hash=digest, quote_id=quote.id))
        result = snapshot(db, user_id, quote)
        db.commit()
        return result
