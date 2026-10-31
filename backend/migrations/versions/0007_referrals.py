"""Verified referral attribution and commission-backed DEMO_TON rewards."""
from alembic import op
import sqlalchemy as sa

revision = '0007_referrals'
down_revision = '0006_seasonal_grants'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('wallet_transactions') as batch:
        batch.drop_constraint('wallet_transaction_kind', type_='check')
        batch.create_check_constraint('wallet_transaction_kind', "kind IN ('seed','topup','withdraw','referral','referral_credit','loan_credit','loan_repay','loan_interest','loan_extend','trade_credit','trade_debit')")
    op.create_table('referral_bindings',
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('referrer_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.CheckConstraint('user_id <> referrer_id', name='referral_not_self'),
        sa.UniqueConstraint('user_id', 'referrer_id', name='referral_binding_pair'))
    op.create_index('ix_referral_bindings_referrer_id', 'referral_bindings', ['referrer_id'])
    op.create_table('referral_rewards',
        sa.Column('quote_id', sa.String(32), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('referrer_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('turnover_nano', sa.BigInteger(), nullable=False),
        sa.Column('fee_nano', sa.BigInteger(), nullable=False),
        sa.Column('amount_nano', sa.BigInteger(), nullable=False),
        sa.Column('rate_bps', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['quote_id', 'user_id'], ['trade_quotes.id', 'trade_quotes.user_id']),
        sa.ForeignKeyConstraint(['user_id', 'referrer_id'], ['referral_bindings.user_id', 'referral_bindings.referrer_id']),
        sa.CheckConstraint('user_id <> referrer_id', name='reward_not_self'),
        sa.CheckConstraint('turnover_nano > 0 AND fee_nano >= 0 AND amount_nano >= 0 AND amount_nano <= fee_nano', name='reward_amount'),
        sa.CheckConstraint('rate_bps >= 0 AND rate_bps <= 10000', name='reward_rate'),
        sa.CheckConstraint('turnover_nano <= 100000000000000 AND fee_nano <= turnover_nano AND amount_nano <= turnover_nano * rate_bps / 10000', name='reward_turnover_limit'),
        sa.CheckConstraint("status IN ('credited','held')", name='reward_status'))
    op.create_index('ix_referral_rewards_referrer_id', 'referral_rewards', ['referrer_id'])


def downgrade():
    raise RuntimeError('Referral earnings require an explicit data-preserving rollback')
