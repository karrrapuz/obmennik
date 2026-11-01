from sqlalchemy import event
from sqlalchemy.orm import Session

from app.ledger import CAP, REFERRAL_SEED, ensure_wallet, post_transfer
from app.models import User

from test_admin import authenticated, client, seed, settings


def test_overview_query_budget_and_counts(client, authenticated):
    seed(client)
    statements = []

    def capture(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith('SELECT'):
            statements.append(statement)

    engine = client.app.state.engine
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        response = client.get('/api/admin/overview', headers=authenticated)
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
    assert response.status_code == 200
    data = response.json()
    assert data['counts'] == {'users': 8, 'active_loans': 4, 'repaid_loans': 3,
                              'open_quotes': 3, 'executed_trades': 4, 'ledger_transactions': 14}
    assert data['account_balances_nano']['wallet'] == '28'
    # Two authorization queries plus one aggregate snapshot; each fact table once.
    assert len(statements) == 3
    overview = statements[-1]
    for table in ('demo_loans', 'trade_quotes', 'wallet_accounts'):
        assert overview.count('FROM ' + table) == 1


def test_overview_empty_financial_tables_still_returns_counts(client, authenticated):
    response = client.get('/api/admin/overview', headers=authenticated)
    assert response.status_code == 200
    data = response.json()
    assert data['counts']['users'] == 1
    assert all(value == 0 for key, value in data['counts'].items() if key != 'users')
    assert data['account_balances_nano'] == {}


def test_overview_large_sums_and_negative_treasury_remain_exact(client, authenticated):
    count = 100
    with Session(client.app.state.engine) as db:
        for identity in range(1000, 1000 + count):
            db.add(User(id=identity, first_name='Aggregate fixture', referral_code=f'aggregate-{identity}'))
        db.flush()
        for identity in range(1000, 1000 + count):
            ensure_wallet(db, identity)
            post_transfer(db, identity, 'large-fixture', 'fixture', 'topup', CAP,
                          'treasury', 'wallet', CAP)
        db.commit()
    response = client.get('/api/admin/overview', headers=authenticated)
    assert response.status_code == 200
    balances = response.json()['account_balances_nano']
    assert count * CAP > 2**53
    assert balances == {'wallet': str(count * CAP), 'referral': str(count * REFERRAL_SEED),
                        'treasury': str(-count * (CAP + REFERRAL_SEED))}
