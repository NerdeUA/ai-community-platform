"""telegram source fields

Revision ID: 002
Revises: 001
Create Date: 2026-03-09

"""
import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make url nullable (Telegram sources don't have a URL)
    op.alter_column("threat_sources", "url", existing_type=sa.String(1024), nullable=True)
    # Add Telegram-specific columns
    op.add_column("threat_sources", sa.Column("telegram_id", sa.BigInteger(), nullable=True))
    op.add_column("threat_sources", sa.Column("telegram_title", sa.String(256), nullable=True))
    op.add_column("threat_sources", sa.Column("telegram_username", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("threat_sources", "telegram_username")
    op.drop_column("threat_sources", "telegram_title")
    op.drop_column("threat_sources", "telegram_id")
    op.alter_column("threat_sources", "url", existing_type=sa.String(1024), nullable=False)
