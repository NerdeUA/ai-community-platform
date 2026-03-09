## ADDED Requirements

### Requirement: Threat Intelligence Ingestion
The system SHALL poll configured intelligence sources (RSS feeds, URLs) on a scheduled basis and ingest raw threat content for analysis.

#### Scenario: RSS feed polling
- **WHEN** a scheduled ingestion cycle runs
- **THEN** all enabled RSS sources are polled and new items are extracted

#### Scenario: Duplicate deduplication
- **WHEN** an item with the same content hash already exists in the database
- **THEN** the item is skipped without re-processing

### Requirement: LangGraph Analysis Pipeline
The system SHALL process threat content through a multi-agent LangGraph pipeline: Ingestor → Analyst → InfraGuard → Publisher.

#### Scenario: Relevant threat content
- **WHEN** raw content describes a vulnerability, software update, or network attack
- **THEN** the pipeline returns a structured threat profile with severity, CVEs, and affected vendors

#### Scenario: Irrelevant content filtering
- **WHEN** the Ingestor node determines content is not threat-relevant
- **THEN** the pipeline sets ignore=true and terminates early without creating a ThreatIntel record

#### Scenario: Optional deep research via OpenClaw
- **WHEN** openclaw_enabled is true and the Analyst node sets needs_deep_research=true
- **THEN** the ClawBridge node is invoked before InfraGuard

### Requirement: Asset Inventory Correlation
The system SHALL maintain an infrastructure asset inventory and correlate incoming threats against it to identify exposed assets.

#### Scenario: Asset match on vendor name
- **WHEN** a threat profile lists affected vendors
- **THEN** InfraGuard queries OpenSearch for matching assets and annotates the threat with affected_assets_count

#### Scenario: Asset import via CSV
- **WHEN** an operator uploads a CSV file with columns name, vendor, model, software_version, criticality
- **THEN** all rows are imported as Asset records and indexed in OpenSearch

### Requirement: Threat Report Generation
The system SHALL generate two report formats per analyzed threat: an Operations Report (Markdown, technical detail) and an Executive Summary (plain text, max 200 words).

#### Scenario: Reports stored on threat record
- **WHEN** the Publisher node completes
- **THEN** ops_report and exec_report are persisted on the ThreatIntel record

### Requirement: REST API for Analysis and Queries
The system SHALL expose a REST API for triggering on-demand analysis and querying stored threats.

#### Scenario: On-demand analysis trigger
- **WHEN** POST /api/v1/analyze is called with a content payload
- **THEN** the pipeline runs synchronously and returns threat_id, severity, and title

#### Scenario: Threat listing with severity filter
- **WHEN** GET /api/v1/threats?severity=critical is called
- **THEN** only threats with severity=critical are returned, ordered by created_at descending

### Requirement: Admin UI
The system SHALL provide an HTML admin interface for managing sources, assets, and agent model/prompt configuration.

#### Scenario: Source management
- **WHEN** an operator navigates to /admin/sources
- **THEN** all configured sources are listed with their enabled state, poll interval, and last polled timestamp

#### Scenario: Settings persistence
- **WHEN** an operator submits the settings form at /admin/settings
- **THEN** model names, cron schedule, and all prompts are persisted to the AgentSettings table

### Requirement: Telegram Alerting
The system SHALL send Telegram alerts for high and critical severity threats when bot credentials are configured.

#### Scenario: Critical threat alert
- **WHEN** a threat with severity=critical or severity=high is persisted
- **THEN** a Telegram message is sent to the configured chat ID with the threat title, CVEs, and affected asset count

#### Scenario: Telegram not configured
- **WHEN** TELEGRAM_BOT_TOKEN or TELEGRAM_ALERT_CHAT_ID is empty
- **THEN** no alert is sent and the pipeline continues without error

### Requirement: OpenSearch Integration
The system SHALL index assets and processed threats in OpenSearch for similarity search and deduplication.

#### Scenario: Asset indexed on creation
- **WHEN** a new asset is created via the admin UI or CSV import
- **THEN** the asset document is indexed in the ti_analyst_assets OpenSearch index

#### Scenario: Threat similarity search
- **WHEN** the Analyst node processes a threat
- **THEN** OpenSearch is queried for similar past threats to support deduplication

### Requirement: Startup Database Migration
The system SHALL run Alembic migrations automatically on container startup when MIGRATE_ON_START=1.

#### Scenario: Migration on startup
- **WHEN** the container starts with MIGRATE_ON_START=1
- **THEN** alembic upgrade head is executed before the application server starts

#### Scenario: Migration failure is non-fatal
- **WHEN** the migration command fails (e.g., database unavailable)
- **THEN** the container continues startup and the failure is logged
