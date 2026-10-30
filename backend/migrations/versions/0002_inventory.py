"""Persistent DEMO inventory."""
from alembic import op
import sqlalchemy as sa

revision = "0002_inventory"
down_revision = "0001_auth"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("inventory_init",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), primary_key=True))
    op.create_table("inventory_gifts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("catalog_id", sa.Integer(), nullable=False),
        sa.Column("pledged", sa.Boolean(), nullable=False),
        sa.Column("pledge_supported", sa.Boolean(), nullable=False),
        sqlite_autoincrement=True)
    op.create_index("ix_inventory_gifts_user_id", "inventory_gifts", ["user_id"])
    op.create_table("inventory_receipts",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False))


def downgrade():
    op.drop_table("inventory_receipts")
    op.drop_table("inventory_gifts")
    op.drop_table("inventory_init")
