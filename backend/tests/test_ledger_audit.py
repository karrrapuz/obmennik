import pytest
from sqlalchemy import create_engine, event, text

from app.ledger_audit import audit_ledger
from app.config import Settings
from test_auth import BOT_TOKEN


@pytest.fixture
def settings(tmp_path):
    return Settings(bot_token=BOT_TOKEN, database_url=f'sqlite:///{(tmp_path / "audit.sqlite").as_posix()}', allowed_origins=())


@pytest.fixture
def db():
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE wallet_accounts (user_id INTEGER, kind TEXT, balance BIGINT)'))
        connection.execute(text('CREATE TABLE wallet_transactions (id TEXT, amount_nano BIGINT)'))
        connection.execute(text('CREATE TABLE wallet_postings (transaction_id TEXT, user_id INTEGER, account_kind TEXT, amount BIGINT)'))
        yield connection
    engine.dispose()


def seed(db):
    db.execute(text("INSERT INTO wallet_accounts VALUES (1, 'wallet', 1000000001), (1, 'treasury', -1000000001)"))
    db.execute(text("INSERT INTO wallet_transactions VALUES ('transfer', 1000000001)"))
    db.execute(text("INSERT INTO wallet_postings VALUES ('transfer', 1, 'wallet', 1000000001), ('transfer', 1, 'treasury', -1000000001)"))


def test_empty_and_balanced_are_clean_and_single_read(db):
    assert audit_ledger(db)['ok']
    seed(db)
    statements = []
    event.listen(db, 'before_cursor_execute', lambda *args: statements.append(args[2]))
    assert audit_ledger(db) == {'ok': True, 'issues': {'account_balance': 0, 'transaction_balance': 0}}
    assert len(statements) == 1 and statements[0].lstrip().startswith('WITH')


@pytest.mark.parametrize('sql,kind', [
    ("UPDATE wallet_accounts SET balance=balance+1 WHERE kind='wallet'", 'account_balance'),
    ("UPDATE wallet_transactions SET amount_nano=1", 'transaction_balance'),
    ("DELETE FROM wallet_postings WHERE account_kind='treasury'", 'transaction_balance'),
    ("INSERT INTO wallet_transactions VALUES ('missing', 1)", 'transaction_balance'),
])
def test_detects_corruption_without_repairing_it(db, sql, kind):
    seed(db)
    db.execute(text(sql))
    report = audit_ledger(db)
    assert not report['ok'] and report['issues'][kind] > 0
    assert audit_ledger(db) == report


def test_real_wallet_seed_and_transfers_reconcile(settings):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from test_auth import bearer, login
    app = create_app(settings)
    with TestClient(app) as client:
        client.headers.update(bearer(login(client)['access_token']))
        assert client.get('/api/wallet').status_code == 200
        assert client.post('/api/wallet/demo-topup', json={'amount_nano': '1000000001', 'source': 'wallet'},
                           headers={'Idempotency-Key': 'audit-topup'}).status_code == 200
        with app.state.engine.connect() as connection:
            assert audit_ledger(connection)['ok']
