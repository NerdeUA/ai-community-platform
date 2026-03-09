"""fix default model names to match local LiteLLM aliases

Revision ID: 003
Revises: 002
Create Date: 2026-03-09

"""
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

_OLD_TRIAGE = "openrouter/anthropic/claude-3.5-haiku"
_OLD_ANALYST = "openrouter/anthropic/claude-3.5-sonnet"
_OLD_INFRA = "ollama/llama3.1:8b"

_NEW_TRIAGE = "free"
_NEW_ANALYST = "cheap"
_NEW_INFRA = "free"


def upgrade() -> None:
    # Update any existing agent_settings rows that still have the old openrouter defaults
    op.execute(
        f"""
        UPDATE agent_settings
        SET triage_model = '{_NEW_TRIAGE}',
            analyst_model = '{_NEW_ANALYST}',
            infra_model = '{_NEW_INFRA}'
        WHERE triage_model = '{_OLD_TRIAGE}'
          AND analyst_model = '{_OLD_ANALYST}'
          AND infra_model = '{_OLD_INFRA}'
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE agent_settings
        SET triage_model = '{_OLD_TRIAGE}',
            analyst_model = '{_OLD_ANALYST}',
            infra_model = '{_OLD_INFRA}'
        WHERE triage_model = '{_NEW_TRIAGE}'
          AND analyst_model = '{_NEW_ANALYST}'
          AND infra_model = '{_NEW_INFRA}'
        """
    )
