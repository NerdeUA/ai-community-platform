import json
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ThreatSource(Base):
    """Monitored intelligence sources (RSS, Telegram, blog URLs)."""
    __tablename__ = "threat_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # rss | telegram | url | reddit
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Telegram-specific fields (populated for source_type='telegram')
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    telegram_username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_seen_msg_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    poll_interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Asset(Base):
    """Infrastructure asset inventory."""
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    vendor: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str] = mapped_column(String(256), nullable=False)
    software_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    criticality: Mapped[str] = mapped_column(String(32), default="medium")  # low | medium | high | critical
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)  # comma-separated
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ThreatIntel(Base):
    """Processed threat intelligence items."""
    __tablename__ = "threat_intel"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    cve_ids: Mapped[str | None] = mapped_column(String(512), nullable=True)  # comma-separated CVEs
    threat_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)  # low | medium | high | critical
    confidence: Mapped[str | None] = mapped_column(String(32), nullable=True)  # low | medium | high
    affected_vendors: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def affected_vendors_label(self) -> str:
        """First two items from the affected_vendors JSON array, joined by ', '."""
        try:
            items = json.loads(self.affected_vendors or "[]")
            return ", ".join(str(i) for i in items[:2]) if items else ""
        except Exception:
            return ""

    ops_report: Mapped[str | None] = mapped_column(Text, nullable=True)
    exec_report: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_assets_count: Mapped[int] = mapped_column(Integer, default=0)
    # new | triaged | analyzed | reported | ignored
    status: Mapped[str] = mapped_column(String(32), default="new", index=True)
    dedup_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AnalysisRun(Base):
    """Tracks individual analysis pipeline executions."""
    __tablename__ = "analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trigger: Mapped[str] = mapped_column(String(64), default="manual")  # manual | scheduled | api
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    threats_processed: Mapped[int] = mapped_column(Integer, default=0)
    threats_critical: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentSettings(Base):
    """Per-agent model and pipeline configuration."""
    __tablename__ = "agent_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    triage_model: Mapped[str] = mapped_column(String(128), default="free")
    analyst_model: Mapped[str] = mapped_column(String(128), default="cheap")
    infra_model: Mapped[str] = mapped_column(String(128), default="free")
    openclaw_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    telegram_alert_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bot_allowed_user_ids: Mapped[str | None] = mapped_column(Text, nullable=True)  # comma-separated Telegram user IDs
    ingestion_cron: Mapped[str] = mapped_column(String(64), default="0 */1 * * *")
    triage_prompt: Mapped[str] = mapped_column(
        Text,
        default=(
            "You are an OSINT analyst. Analyze the input text. "
            "If it describes a vulnerability, software update, or network attack — return a JSON object with: "
            "title, threat_type, cve_ids (array), severity (low|medium|high|critical), confidence (low|medium|high), "
            "affected_vendors (array), summary. "
            "If the content is irrelevant noise — return {\"ignore\": true}."
        ),
    )
    analyst_prompt: Mapped[str] = mapped_column(
        Text,
        default=(
            "You are a senior CTI analyst. Given the threat profile, provide a deep analysis: "
            "assess the real-world impact, identify attack vectors, recommend detection strategies, "
            "and rate overall severity. Return JSON with: severity, confidence, attack_vectors (array), "
            "detection_strategies (array), mitigation_steps (array), needs_deep_research (bool)."
        ),
    )
    infra_prompt: Mapped[str] = mapped_column(
        Text,
        default=(
            "You are an infrastructure security auditor. Given the threat profile and the list of matched assets, "
            "determine which assets are at risk and their exposure level. "
            "Return JSON with: exposed_assets (array of {asset_id, asset_name, exposure_level}), "
            "overall_risk (low|medium|high|critical), remediation_priority."
        ),
    )
    publisher_ops_prompt: Mapped[str] = mapped_column(
        Text,
        default=(
            "You are a technical security writer. Create a detailed Operations Report in Markdown. "
            "Include: threat summary, CVEs, affected systems, detection commands, patch status, references. "
            "Write the entire report in Ukrainian language."
        ),
    )
    publisher_exec_prompt: Mapped[str] = mapped_column(
        Text,
        default=(
            "You are a CISO advisor. Create a concise Executive Summary (max 200 words). "
            "Include: risk level, business impact, recommended actions, financial exposure estimate. "
            "Write the entire summary in Ukrainian language."
        ),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
