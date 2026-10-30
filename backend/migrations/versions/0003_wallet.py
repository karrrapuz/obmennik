"""Accounts and double-entry ledger for DEMO_TON only."""
from alembic import op
import sqlalchemy as sa

revision = '0003_wallet'
down_revision = '0002_inventory'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('wallet_accounts',
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('kind', sa.String(16), primary_key=True),
        sa.Column('balance', sa.BigInteger(), nullable=False),
        sa.CheckConstraint("kind IN ('wallet','referral','treasury')", name='wallet_account_kind'),
        sa.CheckConstraint("kind = 'treasury' OR (balance >= 0 AND balance <= 100000000000000)", name='wallet_account_balance'))
    op.create_table('wallet_transactions',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('key', sa.String(128), nullable=False),
        sa.Column('payload_hash', sa.String(64), nullable=False),
        sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('amount_nano', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('source', sa.String(16)),
        sa.Column('destination', sa.String(256)),
        sa.UniqueConstraint('user_id', 'key', name='wallet_request_unique'),
        sa.UniqueConstraint('id', 'user_id', name='wallet_transaction_owner'),
        sa.CheckConstraint("kind IN ('seed','topup','withdraw','referral')", name='wallet_transaction_kind'))
    op.create_index('ix_wallet_transactions_user_id', 'wallet_transactions', ['user_id'])
    op.create_table('wallet_postings',
        sa.Column('transaction_id', sa.String(32), primary_key=True),
        sa.Column('account_kind', sa.String(16), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('amount', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['transaction_id', 'user_id'], ['wallet_transactions.id', 'wallet_transactions.user_id']),
        sa.ForeignKeyConstraint(['user_id', 'account_kind'], ['wallet_accounts.user_id', 'wallet_accounts.kind']),
        sa.CheckConstraint('amount <> 0', name='wallet_posting_nonzero'))
    if op.get_bind().dialect.name == 'postgresql':
        # Deferred checks see the entire atomic transfer, including both postings.
        op.execute("""
        CREATE FUNCTION check_demo_ledger() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE tx_id text; owner_id bigint; total numeric; entries bigint;
        BEGIN
          IF TG_TABLE_NAME = 'wallet_transactions' THEN
            IF TG_OP = 'DELETE' THEN tx_id := OLD.id; owner_id := OLD.user_id;
            ELSE tx_id := NEW.id; owner_id := NEW.user_id; END IF;
          ELSIF TG_TABLE_NAME = 'wallet_postings' THEN
            IF TG_OP = 'DELETE' THEN tx_id := OLD.transaction_id; owner_id := OLD.user_id;
            ELSE tx_id := NEW.transaction_id; owner_id := NEW.user_id; END IF;
          ELSE
            IF TG_OP = 'DELETE' THEN owner_id := OLD.user_id;
            ELSE owner_id := NEW.user_id; END IF;
          END IF;
          IF tx_id IS NOT NULL AND EXISTS (SELECT 1 FROM wallet_transactions WHERE id = tx_id) THEN
            SELECT COALESCE(SUM(amount), 0), COUNT(*) INTO total, entries
              FROM wallet_postings WHERE transaction_id = tx_id;
            IF total <> 0 OR entries < 2 THEN
              RAISE EXCEPTION 'Unbalanced demo ledger transaction';
            END IF;
          END IF;
          IF EXISTS (
            SELECT 1 FROM wallet_accounts a WHERE a.user_id = owner_id
            AND a.balance <> COALESCE((SELECT SUM(p.amount) FROM wallet_postings p
              WHERE p.user_id = a.user_id AND p.account_kind = a.kind), 0)
          ) THEN RAISE EXCEPTION 'Demo account balance disagrees with postings'; END IF;
          RETURN NULL;
        END $$;
        """)
        for table in ('wallet_transactions', 'wallet_postings', 'wallet_accounts'):
            op.execute(f'CREATE CONSTRAINT TRIGGER {table}_balanced AFTER INSERT OR UPDATE OR DELETE ON {table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_demo_ledger()')


def downgrade():
    for table in ('wallet_postings', 'wallet_transactions', 'wallet_accounts'):
        op.drop_table(table)
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('DROP FUNCTION check_demo_ledger()')
