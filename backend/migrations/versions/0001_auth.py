"""Users and revocable login sessions."""
from alembic import op
import sqlalchemy as sa

revision = '0001_auth'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('users',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column('first_name', sa.String(256), nullable=False),
        sa.Column('last_name', sa.String(256)),
        sa.Column('username', sa.String(64)),
        sa.Column('photo_url', sa.String(2048)),
        sa.Column('referral_code', sa.String(64), nullable=False, unique=True))
    op.create_table('login_sessions',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('init_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('expires_at', sa.BigInteger(), nullable=False),
        sa.Column('revoked', sa.Integer(), nullable=False))
    op.create_index('ix_login_sessions_user_id', 'login_sessions', ['user_id'])


def downgrade():
    op.drop_table('login_sessions')
    op.drop_table('users')
