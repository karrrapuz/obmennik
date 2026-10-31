"""Frozen trade quotes and exact ledger settlement."""
from alembic import op
import sqlalchemy as sa

revision = '0005_trades'
down_revision = '0004_loans'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('wallet_transactions') as batch:
        batch.drop_constraint('wallet_transaction_kind', type_='check')
        batch.create_check_constraint('wallet_transaction_kind', "kind IN ('seed','topup','withdraw','referral','loan_credit','loan_repay','loan_interest','loan_extend','trade_credit','trade_debit')")
    op.create_table('trade_quotes',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('expires_at', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.CheckConstraint("status IN ('open','executed')", name='trade_quote_status'),
        sa.UniqueConstraint('id', 'user_id', name='trade_quote_owner'))
    op.create_index('ix_trade_quotes_user_id', 'trade_quotes', ['user_id'])
    op.create_table('trade_receipts',
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('key', sa.String(128), primary_key=True),
        sa.Column('payload_hash', sa.String(64), nullable=False),
        sa.Column('quote_id', sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(['quote_id', 'user_id'], ['trade_quotes.id', 'trade_quotes.user_id']))


def downgrade():
    raise RuntimeError('Trade settlement history requires an explicit data-preserving rollback')
