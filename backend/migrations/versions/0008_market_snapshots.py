"""Atomic singleton public market observations."""
from alembic import op
import sqlalchemy as sa

revision = '0008_market_snapshots'
down_revision = '0007_referrals'
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table('market_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column('captured_at', sa.BigInteger(), nullable=False),
        sa.Column('prices_json', sa.Text(), nullable=True),
        sa.Column('listings_json', sa.Text(), nullable=True),
        sa.CheckConstraint('id = 1', name='market_singleton'),
        sa.CheckConstraint('captured_at >= 0', name='market_capture_positive'),
        sa.CheckConstraint('(prices_json IS NULL AND listings_json IS NULL AND captured_at = 0) OR '
                           '(prices_json IS NOT NULL AND listings_json IS NOT NULL AND captured_at > 0)',
                           name='market_snapshot_pair'))
    op.bulk_insert(table, [{'id': 1, 'captured_at': 0, 'prices_json': None, 'listings_json': None}])


def downgrade():
    op.drop_table('market_snapshots')
