import hashlib
import asyncio
import hmac
import logging
import secrets
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import Settings
from .models import LoginSession, User
from .telegram_auth import InvalidInitData, validate_init_data
from .inventory import register_inventory_routes
from .wallet import register_wallet_routes
from .loans import register_loan_routes, process_due_loans
from .gift_provider import create_gift_provider
from .pricing import SamplePriceProvider
from .trades import register_trade_routes
from .catalog_index import register_catalog_routes
from .referrals import bind_first_launch, register_referral_routes
from .market_valuation import register_market_routes
from .integrations import demo_route, register_integration_routes
from .request_limits import RequestBodyLimit
from .admin import register_admin_routes
from .operations import register_operations_routes


class AuthInput(BaseModel):
    init_data: str = Field(min_length=1, max_length=16384)


def create_app(settings: Settings):
    gift_provider = create_gift_provider(settings.gift_provider_mode)
    price_provider = SamplePriceProvider(gift_provider.catalog)
    engine = create_engine(settings.database_url, pool_pre_ping=True,
                           connect_args={'check_same_thread': False} if settings.database_url.startswith('sqlite') else {})
    if settings.database_url.startswith('sqlite'):
        @event.listens_for(engine, 'connect')
        def foreign_keys(connection, record):
            connection.execute('PRAGMA foreign_keys=ON')

    @asynccontextmanager
    async def lifespan(app):
        stop = asyncio.Event()

        async def autopay_loop():
            while not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), timeout=60)
                except TimeoutError:
                    try:
                        await asyncio.to_thread(process_due_loans, engine)
                    except Exception:
                        logging.getLogger('giftmoney').error('Autopay tick failed; next tick remains scheduled')

        task = asyncio.create_task(autopay_loop()) if settings.deployment_mode == 'demo' else None
        try:
            yield
        finally:
            stop.set()
            if task is not None:
                await task
            engine.dispose()

    app = FastAPI(title='GiftMoney API', lifespan=lifespan)
    app.state.engine = engine
    app.state.price_provider = price_provider
    app.add_middleware(RequestBodyLimit)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins),
                       allow_methods=['GET', 'POST'], allow_headers=['Authorization', 'Content-Type', 'Idempotency-Key'])
    bearer = HTTPBearer(auto_error=False)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse({'detail': 'Invalid request'}, status_code=422)

    @app.middleware('http')
    async def request_id(request, call_next):
        rid = uuid4().hex
        try:
            if settings.deployment_mode == 'production' and demo_route(request.url.path):
                response = JSONResponse({'detail': 'Live financial integrations are not configured'}, status_code=503)
            else:
                response = await call_next(request)
        except Exception:
            # Do not log request bodies, headers, DB parameters or secrets.
            logging.getLogger('giftmoney').error('Unhandled request error id=%s', rid)
            response = JSONResponse({'detail': 'Internal server error'}, status_code=500)
        response.headers['X-Request-ID'] = rid
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        if request.url.path.startswith('/admin'):
            response.headers['X-Frame-Options'] = 'DENY'
            response.headers['Content-Security-Policy'] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
            )
        return response

    def database():
        with Session(engine) as db:
            yield db

    def current_session(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(database)):
        if credentials is None:
            raise HTTPException(401, 'Authentication required')
        digest = hashlib.sha256(credentials.credentials.encode()).hexdigest()
        session = db.get(LoginSession, digest)
        if session is None or session.revoked or session.expires_at <= int(time.time()):
            raise HTTPException(401, 'Session expired')
        return session

    def public_user(user):
        return {key: getattr(user, key) for key in ('id', 'first_name', 'last_name', 'username', 'photo_url', 'referral_code')}

    @app.get('/api/health')
    def health(db: Session = Depends(database)):
        db.execute(text('SELECT 1'))
        return {'status': 'ok'}

    @app.post('/api/auth/telegram')
    def login(body: AuthInput, db: Session = Depends(database)):
        try:
            identity, init_hash, auth_date, start_param = validate_init_data(body.init_data, settings.bot_token,
                settings.init_data_max_age, include_start_param=True)
        except InvalidInitData:
            raise HTTPException(401, 'Invalid or expired Telegram data') from None
        # Stable token for a signed launch makes retries/StrictMode idempotent.
        access_token = hmac.new(settings.bot_token.encode(), ('session-v1:' + init_hash).encode(), hashlib.sha256).hexdigest()
        digest = hashlib.sha256(access_token.encode()).hexdigest()
        now = int(time.time())
        existing = db.get(LoginSession, digest)
        if existing and (existing.revoked or existing.expires_at <= now):
            raise HTTPException(401, 'Reopen the Mini App to sign in')
        user = db.get(User, identity.id)
        new_user = user is None
        if user is None:
            user = User(id=identity.id, first_name=identity.first_name, referral_code=secrets.token_urlsafe(18))
            db.add(user)
        for key in ('first_name', 'last_name', 'username', 'photo_url'):
            setattr(user, key, getattr(identity, key))
        try:
            # Persist the parent first; both writes still commit atomically.
            db.flush()
            if new_user:
                bind_first_launch(db, identity.id, start_param)
            if existing is None:
                db.add(LoginSession(token_hash=digest, user_id=identity.id, init_hash=init_hash,
                                    created_at=now, expires_at=auth_date + settings.session_ttl, revoked=0))
            db.commit()
        except IntegrityError:
            db.rollback()
            # Concurrent login of the same launch/user; retry safely on client.
            raise HTTPException(409, 'Login in progress, retry') from None
        return {'access_token': access_token, 'token_type': 'bearer', 'user': public_user(user)}

    @app.get('/api/me')
    def me(session=Depends(current_session), db: Session = Depends(database)):
        return public_user(db.get(User, session.user_id))

    @app.post('/api/auth/logout', status_code=204)
    def logout(session=Depends(current_session), db: Session = Depends(database)):
        session.revoked = 1
        db.commit()
        return Response(status_code=204)

    @app.get('/api/integrations/gifts')
    def gift_integration(session=Depends(current_session)):
        return gift_provider.status()

    register_inventory_routes(app, database, current_session, gift_provider)
    register_catalog_routes(app, gift_provider)
    register_market_routes(app, gift_provider, engine, settings.market_ingest_key)
    register_integration_routes(app, settings, current_session)
    register_admin_routes(app, database, current_session, settings.admin_user_ids)
    register_operations_routes(app, database, current_session, settings.admin_user_ids, settings)
    register_referral_routes(app, database, current_session, settings.referral_rate_bps, settings.telegram_bot_username)
    register_wallet_routes(app, database, current_session)
    register_loan_routes(app, database, current_session, gift_provider)
    register_trade_routes(app, database, current_session, gift_provider,
                          price_provider, settings.trade_markup_bps, settings.trade_quote_ttl, settings.referral_rate_bps)
    return app


def application():
    return create_app(Settings.from_env())
