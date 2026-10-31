"""Read-only reconciliation in a single database statement/snapshot."""
from sqlalchemy import text


def audit_ledger(connection):
    rows = connection.execute(text('''
        WITH account_totals AS (
            SELECT user_id, account_kind, SUM(amount) AS total
            FROM wallet_postings GROUP BY user_id, account_kind
        ), transaction_totals AS (
            SELECT transaction_id, COUNT(*) AS entries, SUM(amount) AS total,
                   SUM(CASE WHEN account_kind = 'wallet' THEN amount ELSE 0 END) AS wallet_delta
            FROM wallet_postings GROUP BY transaction_id
        )
        SELECT 'account_balance' AS issue, COUNT(*) AS count
        FROM wallet_accounts a LEFT JOIN account_totals p
          ON a.user_id = p.user_id AND a.kind = p.account_kind
        WHERE a.balance <> COALESCE(p.total, 0)
        UNION ALL
        SELECT 'transaction_balance', COUNT(*)
        FROM wallet_transactions t LEFT JOIN transaction_totals p ON t.id = p.transaction_id
        WHERE COALESCE(p.entries, 0) <> 2 OR COALESCE(p.total, 0) <> 0
           OR COALESCE(p.wallet_delta, 0) <> t.amount_nano
    ''' )).mappings().all()
    issues = {row['issue']: int(row['count']) for row in rows}
    return {'ok': not any(issues.values()), 'issues': issues}
