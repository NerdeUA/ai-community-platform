"""initial

Revision ID: 001
Revises:
Create Date: 2026-03-08

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "threat_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("poll_interval_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("vendor", sa.String(128), nullable=False),
        sa.Column("model", sa.String(256), nullable=False),
        sa.Column("software_version", sa.String(128), nullable=True),
        sa.Column("criticality", sa.String(32), nullable=False, server_default="medium"),
        sa.Column("tags", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "analysis_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trigger", sa.String(64), nullable=False, server_default="manual"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("threats_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("threats_critical", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_runs_status", "analysis_runs", ["status"])

    op.create_table(
        "threat_intel",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_url", sa.String(1024), nullable=True),
        sa.Column("source_name", sa.String(128), nullable=True),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("cve_ids", sa.String(512), nullable=True),
        sa.Column("threat_type", sa.String(64), nullable=True),
        sa.Column("severity", sa.String(32), nullable=True),
        sa.Column("confidence", sa.String(32), nullable=True),
        sa.Column("affected_vendors", sa.Text(), nullable=True),
        sa.Column("ops_report", sa.Text(), nullable=True),
        sa.Column("exec_report", sa.Text(), nullable=True),
        sa.Column("affected_assets_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="new"),
        sa.Column("dedup_hash", sa.String(64), nullable=True),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedup_hash"),
    )
    op.create_index("ix_threat_intel_status", "threat_intel", ["status"])
    op.create_index("ix_threat_intel_dedup_hash", "threat_intel", ["dedup_hash"])
    op.create_index("ix_threat_intel_analysis_run_id", "threat_intel", ["analysis_run_id"])

    op.create_table(
        "agent_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("triage_model", sa.String(128), nullable=False, server_default="openrouter/anthropic/claude-3.5-haiku"),
        sa.Column("analyst_model", sa.String(128), nullable=False, server_default="openrouter/anthropic/claude-3.5-sonnet"),
        sa.Column("infra_model", sa.String(128), nullable=False, server_default="ollama/llama3.1:8b"),
        sa.Column("openclaw_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ingestion_cron", sa.String(64), nullable=False, server_default="0 */1 * * *"),
        sa.Column("triage_prompt", sa.Text(), nullable=False),
        sa.Column("analyst_prompt", sa.Text(), nullable=False),
        sa.Column("infra_prompt", sa.Text(), nullable=False),
        sa.Column("publisher_ops_prompt", sa.Text(), nullable=False),
        sa.Column("publisher_exec_prompt", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("agent_settings")
    op.drop_index("ix_threat_intel_analysis_run_id")
    op.drop_index("ix_threat_intel_dedup_hash")
    op.drop_index("ix_threat_intel_status")
    op.drop_table("threat_intel")
    op.drop_index("ix_analysis_runs_status")
    op.drop_table("analysis_runs")
    op.drop_table("assets")
    op.drop_table("threat_sources")
