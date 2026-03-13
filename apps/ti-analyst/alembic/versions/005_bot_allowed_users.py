"""Add bot_allowed_user_ids to agent_settings.

Revision ID: 005
Revises: 004
Create Date: 2026-03-09
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_settings",
        sa.Column("bot_allowed_user_ids", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_settings", "bot_allowed_user_ids")
