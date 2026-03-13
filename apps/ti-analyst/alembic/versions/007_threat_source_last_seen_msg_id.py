"""Add last_seen_msg_id to threat_sources for incremental Telegram polling.

Revision ID: 007
Revises: 006
Create Date: 2026-03-11
"""
import sqlalchemy as sa
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "threat_sources",
        sa.Column("last_seen_msg_id", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("threat_sources", "last_seen_msg_id")
