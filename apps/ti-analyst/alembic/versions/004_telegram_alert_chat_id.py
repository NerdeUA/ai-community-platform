"""add telegram_alert_chat_id to agent_settings

Revision ID: 004
Revises: 003
Create Date: 2026-03-09

"""
import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_settings",
        sa.Column("telegram_alert_chat_id", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_settings", "telegram_alert_chat_id")
