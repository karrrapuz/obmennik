"""Private, read-only operational checks; deliberately no financial mutations."""
import time
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, select, text

from .market_models import MarketSnapshot
from .market_storage import InvalidSnapshot, decode_json
from .models import Base
from .integrations import integration_status


def readiness(db, settings=None):
    checks = {}
    try:
        with db.no_autoflush:
            db.execute(text('SELECT 1'))
            checks['database'] = 'ok'
            config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
            heads = set(ScriptDirectory.from_config(config).get_heads())
            installed = set(db.execute(text('SELECT version_num FROM alembic_version')).scalars())
            inspector = inspect(db.connection())
            tables = set(inspector.get_table_names())
            schema_ok = all(table.name in tables and set(table.columns.keys()) <= {
                column['name'] for column in inspector.get_columns(table.name)
            } for table in Base.metadata.sorted_tables)
            checks['schema'] = 'ok' if installed == heads and schema_ok else 'mismatch'
            checks['market'] = 'unavailable'
            if checks['schema'] == 'ok':
                row = db.execute(select(MarketSnapshot.captured_at, MarketSnapshot.prices_json)
                                 .where(MarketSnapshot.id == 1)).first()
                if row and row.prices_json:
                    try:
                        feed = decode_json(row.prices_json)
                        captured, until = feed.get('capturedAt'), feed.get('validUntil')
                        now = int(time.time())
                        if (type(captured) is int and type(until) is int
                                and captured == row.captured_at and 0 < captured <= now + 60
                                and captured < until <= captured + 86400 and feed.get('complete') is True):
                            checks['market'] = 'fresh' if until > now else 'stale'
                    except (InvalidSnapshot, AttributeError):
                        pass
    except Exception:
        # Never return driver errors, URLs, SQL parameters or authentication material.
        checks['database'] = 'error'
    checks['ledger'] = 'not_checked_use_offline_audit'
    operational = (checks.get('database') == 'ok' and checks.get('schema') == 'ok'
                   and checks.get('market') == 'fresh')
    capabilities = integration_status(settings) if settings is not None else None
    mode = capabilities['deployment_mode'] if capabilities else 'unconfigured'
    live = bool(capabilities and all(capabilities.get(name) is True for name in
                ('real_payments', 'real_gift_transfers', 'real_loans')))
    checks['live_adapters'] = 'configured' if live else 'not_configured'
    return {'ready': operational and (mode == 'demo' or (mode == 'production' and live)),
            'operational_ready': operational, 'live_ready': operational and live and mode == 'production',
            'deployment_mode': mode, 'checks': checks}


def register_operations_routes(app, database, current_session, admin_user_ids, settings=None):
    admins = frozenset(admin_user_ids)
    if any(type(identity) is not int or identity <= 0 for identity in admins):
        raise ValueError('Admin IDs must be positive integers')

    def admin(session=Depends(current_session)):
        if session.user_id not in admins:
            raise HTTPException(403, 'Administrator access required')

    @app.get('/api/admin/readiness', include_in_schema=False, dependencies=[Depends(admin)])
    def get_readiness(db=Depends(database)):
        result = readiness(db, settings)
        return JSONResponse(result, status_code=200 if result['ready'] else 503,
                            headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
