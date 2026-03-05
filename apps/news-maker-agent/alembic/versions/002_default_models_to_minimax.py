"""switch default llm models to minimax via litellm

Revision ID: 002
Revises: 001
Create Date: 2026-03-06

"""

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "agent_settings",
        "ranker_model",
        existing_type=sa.String(length=128),
        server_default="minimax/minimax-m2.5",
    )
    op.alter_column(
        "agent_settings",
        "rewriter_model",
        existing_type=sa.String(length=128),
        server_default="minimax/minimax-m2.5",
    )
    op.execute(
        "UPDATE agent_settings "
        "SET ranker_model = 'minimax/minimax-m2.5' "
        "WHERE ranker_model = 'gpt-4o-mini'"
    )
    op.execute(
        "UPDATE agent_settings "
        "SET rewriter_model = 'minimax/minimax-m2.5' "
        "WHERE rewriter_model = 'gpt-4o-mini'"
    )


def downgrade() -> None:
    op.alter_column(
        "agent_settings",
        "ranker_model",
        existing_type=sa.String(length=128),
        server_default="gpt-4o-mini",
    )
    op.alter_column(
        "agent_settings",
        "rewriter_model",
        existing_type=sa.String(length=128),
        server_default="gpt-4o-mini",
    )
    op.execute(
        "UPDATE agent_settings "
        "SET ranker_model = 'gpt-4o-mini' "
        "WHERE ranker_model = 'minimax/minimax-m2.5'"
    )
    op.execute(
        "UPDATE agent_settings "
        "SET rewriter_model = 'gpt-4o-mini' "
        "WHERE rewriter_model = 'minimax/minimax-m2.5'"
    )
