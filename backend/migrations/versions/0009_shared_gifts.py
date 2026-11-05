"""Immutable public gift snapshots behind unguessable share tokens."""
from alembic import op
import sqlalchemy as sa

revision = '0009_shared_gifts'
down_revision = '0008_market_snapshots'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('shared_gifts',
        sa.Column('token', sa.String(48), primary_key=True),
        sa.Column('fingerprint', sa.String(64), nullable=False, unique=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.Column('expires_at', sa.BigInteger(), nullable=False))
    op.create_index('ix_shared_gifts_user_id', 'shared_gifts', ['user_id'])


def downgrade():
    op.drop_table('shared_gifts')
