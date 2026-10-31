"""Once-only seasonal DEMO gifts; no priced financial entitlement."""

from alembic import op
import sqlalchemy as sa


revision = '0006_seasonal_grants'
down_revision = '0005_trades'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('demo_seasonal_grants',
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('catalog_id', sa.Integer(), primary_key=True))


def downgrade():
    raise RuntimeError('Seasonal grant history requires an explicit data-preserving rollback')
