"""Allowlisted, read-only DEMO_TON operations view; not a money-control console."""
import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .loan_models import DemoLoan
from .models import LoginSession, User
from .trade_models import TradeQuote
from .wallet_models import WalletAccount, WalletPosting, WalletTransaction


STATIC = Path(__file__).resolve().parents[1] / 'static'
HEADERS = {
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
    'X-Frame-Options': 'DENY',
    'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
}
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=10000)]


def register_admin_routes(app, database, current_session, admin_user_ids: tuple[int, ...] = ()):
    """Pass the same database/current_session dependencies used by /api/me.

    admin_user_ids must be a tuple of positive signed-64-bit Telegram user IDs.
    An empty tuple deliberately denies every data request. No writes or seeding.
    """
    if not isinstance(admin_user_ids, tuple) or any(
        type(identity) is not int or not 0 < identity <= 9223372036854775807
        for identity in admin_user_ids
    ):
        raise ValueError('admin_user_ids must be a tuple of positive numeric Telegram user IDs')
    allowed = frozenset(admin_user_ids)

    def admin_session(response: Response, session=Depends(current_session), db: Session = Depends(database)):
        # current_session authenticates Telegram-issued bearer sessions; also fail closed
        # if a stale/revoked object is ever passed by an alternative dependency.
        if (not isinstance(session, LoginSession) or session.revoked
                or session.expires_at <= int(time.time())):
            raise HTTPException(401, 'Authentication required', headers=HEADERS)
        if type(session.user_id) is not int or session.user_id not in allowed or db.get(User, session.user_id) is None:
            raise HTTPException(403, 'Admin access denied', headers=HEADERS)
        response.headers.update(HEADERS)
        return session

    router = APIRouter(prefix='/api/admin', dependencies=[Depends(admin_session)])

    def page(db, statement, fields, limit, offset, *, nano_fields=(), id_fields=()):
        rows = db.execute(statement.offset(offset).limit(limit + 1)).all()
        items = []
        for row in rows[:limit]:
            item = dict(zip(fields, row))
            for field in (*nano_fields, *id_fields):
                item[field] = str(item[field])
            items.append(item)
        has_more = len(rows) > limit
        return {'asset': 'DEMO_TON', 'amount_unit': 'nano_DEMO_TON', 'items': items,
                'limit': limit, 'offset': offset, 'has_more': has_more,
                'next_offset': offset + limit if has_more and offset + limit <= 10000 else None}

    @router.get('/overview')
    def overview(db: Session = Depends(database), session=Depends(admin_session)):
        def count(model, *criteria):
            return db.scalar(select(func.count()).select_from(model).where(*criteria))

        balances = db.execute(select(WalletAccount.kind, func.sum(WalletAccount.balance)).group_by(WalletAccount.kind)).all()
        return {'asset': 'DEMO_TON', 'amount_unit': 'nano_DEMO_TON', 'read_only': True,
                'admin_user_id': str(session.user_id),
                'counts': {'users': count(User), 'active_loans': count(DemoLoan, DemoLoan.status == 'active'),
                           'repaid_loans': count(DemoLoan, DemoLoan.status == 'repaid'),
                           'open_quotes': count(TradeQuote, TradeQuote.status == 'open'),
                           'executed_trades': count(TradeQuote, TradeQuote.status == 'executed'),
                           'ledger_transactions': count(WalletTransaction)},
                'account_balances_nano': {kind: str(amount) for kind, amount in balances}}

    @router.get('/users')
    def users(limit: Limit = 25, offset: Offset = 0, db: Session = Depends(database)):
        return page(db, select(User.id, User.state_revision).order_by(User.id),
                    ('user_id', 'revision'), limit, offset, id_fields=('user_id',))

    @router.get('/loans')
    def loans(limit: Limit = 25, offset: Offset = 0, db: Session = Depends(database)):
        return page(db, select(DemoLoan.id, DemoLoan.user_id, DemoLoan.gift_id, DemoLoan.status,
                    DemoLoan.principal, DemoLoan.repayment, DemoLoan.created_at, DemoLoan.due_at, DemoLoan.autopay)
                    .order_by(DemoLoan.created_at.desc(), DemoLoan.id),
                    ('id', 'user_id', 'gift_id', 'status', 'principal_nano', 'repayment_nano', 'created_at', 'due_at', 'autopay'),
                    limit, offset, nano_fields=('principal_nano', 'repayment_nano'), id_fields=('user_id',))

    @router.get('/trades')
    def trades(limit: Limit = 25, offset: Offset = 0, db: Session = Depends(database)):
        return page(db, select(TradeQuote.id, TradeQuote.user_id, TradeQuote.status, TradeQuote.expires_at)
                    .order_by(TradeQuote.expires_at.desc(), TradeQuote.id),
                    ('id', 'user_id', 'status', 'expires_at'), limit, offset, id_fields=('user_id',))

    @router.get('/accounts')
    def accounts(limit: Limit = 25, offset: Offset = 0, db: Session = Depends(database)):
        return page(db, select(WalletAccount.user_id, WalletAccount.kind, WalletAccount.balance)
                    .order_by(WalletAccount.user_id, WalletAccount.kind),
                    ('user_id', 'kind', 'balance_nano'), limit, offset, nano_fields=('balance_nano',), id_fields=('user_id',))

    @router.get('/ledger')
    def ledger(limit: Limit = 25, offset: Offset = 0, db: Session = Depends(database)):
        result = page(db, select(WalletTransaction.id, WalletTransaction.user_id, WalletTransaction.kind,
                    WalletTransaction.amount_nano, WalletTransaction.created_at)
                    .order_by(WalletTransaction.created_at.desc(), WalletTransaction.id),
                    ('id', 'user_id', 'kind', 'amount_nano', 'created_at_ns'), limit, offset,
                    nano_fields=('amount_nano',), id_fields=('user_id', 'created_at_ns'))
        ids = [item['id'] for item in result['items']]
        postings = {}
        if ids:
            for transaction_id, kind, amount in db.execute(select(WalletPosting.transaction_id,
                    WalletPosting.account_kind, WalletPosting.amount).where(WalletPosting.transaction_id.in_(ids))
                    .order_by(WalletPosting.transaction_id, WalletPosting.account_kind)):
                postings.setdefault(transaction_id, []).append({'account_kind': kind, 'amount_nano': str(amount)})
        for item in result['items']:
            item['postings'] = postings.get(item['id'], [])
        return result

    app.include_router(router)

    # Only these fixed local assets are served; no user-controlled filesystem path.
    @app.get('/admin', include_in_schema=False)
    def shell():
        return FileResponse(STATIC / 'admin.html', media_type='text/html', headers=HEADERS)

    @app.get('/admin/admin.js', include_in_schema=False)
    def script():
        return FileResponse(STATIC / 'admin.js', media_type='text/javascript', headers=HEADERS)

    @app.get('/admin/admin.css', include_in_schema=False)
    def style():
        return FileResponse(STATIC / 'admin.css', media_type='text/css', headers=HEADERS)
