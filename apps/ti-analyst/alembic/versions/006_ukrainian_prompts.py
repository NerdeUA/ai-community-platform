"""Update publisher prompts to Ukrainian language.

Revision ID: 006
Revises: 005
Create Date: 2026-03-11
"""
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None

OPS_PROMPT = (
    "You are a technical security writer. Create a detailed Operations Report in Markdown. "
    "Include: threat summary, CVEs, affected systems, detection commands, patch status, references. "
    "Write the entire report in Ukrainian language."
)

EXEC_PROMPT = (
    "You are a CISO advisor. Create a concise Executive Summary (max 200 words). "
    "Include: risk level, business impact, recommended actions, financial exposure estimate. "
    "Write the entire summary in Ukrainian language."
)


def upgrade() -> None:
    op.execute(
        f"UPDATE agent_settings SET "
        f"publisher_ops_prompt  = $${OPS_PROMPT}$$, "
        f"publisher_exec_prompt = $${EXEC_PROMPT}$$"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE agent_settings SET "
        "publisher_ops_prompt  = 'You are a technical security writer. Create a detailed Operations Report in Markdown. "
        "Include: threat summary, CVEs, affected systems, detection commands, patch status, references.', "
        "publisher_exec_prompt = 'You are a CISO advisor. Create a concise Executive Summary (max 200 words). "
        "Include: risk level, business impact, recommended actions, financial exposure estimate.'"
    )
