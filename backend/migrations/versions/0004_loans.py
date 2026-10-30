"""Persist loan terms, collateral state and lifecycle receipts."""
from alembic import op
import sqlalchemy as sa

revision = '0004_loans'
down_revision = '0003_wallet'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('state_revision', sa.BigInteger(), nullable=False, server_default='0'))
    with op.batch_alter_table('wallet_transactions') as batch:
        batch.drop_constraint('wallet_transaction_kind', type_='check')
        batch.create_check_constraint('wallet_transaction_kind', "kind IN ('seed','topup','withdraw','referral','loan_credit','loan_repay','loan_interest','loan_extend')")
    op.create_table('demo_loans',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('gift_id', sa.Integer(), nullable=False),
        sa.Column('weeks', sa.Integer(), nullable=False),
        sa.Column('principal', sa.BigInteger(), nullable=False),
        sa.Column('repayment', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('due_at', sa.BigInteger(), nullable=False),
        sa.Column('autopay', sa.Boolean(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('legacy', sa.Boolean(), nullable=False),
        sa.Column('last_autopay_attempt', sa.BigInteger()),
        sa.CheckConstraint('weeks IN (1,2)', name='loan_weeks'),
        sa.CheckConstraint('principal >= 0 AND repayment >= principal', name='loan_amounts'),
        sa.CheckConstraint("status IN ('active','repaid')", name='loan_status'))
    op.create_index('ix_demo_loans_user_id', 'demo_loans', ['user_id'])
    op.create_index('ix_demo_loans_active_gift', 'demo_loans', ['gift_id'], unique=True,
        postgresql_where=sa.text("status = 'active'"), sqlite_where=sa.text("status = 'active'"))
    op.create_table('loan_receipts',
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('key', sa.String(128), primary_key=True),
        sa.Column('payload_hash', sa.String(64), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False))


def downgrade():
    op.drop_table('loan_receipts')
    op.drop_table('demo_loans')
    # Keep extended journal kinds: dropping historical financial rows is unsafe.
