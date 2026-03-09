# TI Analyst Agent (Sentinel-AI)

## Purpose

TI Analyst is an automated Cyber Threat Intelligence (CTI) analysis agent. It monitors configured intelligence sources (RSS feeds, Telegram channels, URLs), runs ingested content through a multi-stage LangGraph pipeline, correlates threats against the infrastructure asset inventory, and alerts on high/critical findings via Telegram.

## Features

- `GET /health` — standard health check (`{"status": "ok", "service": "ti-analyst"}`)
- `GET /api/v1/manifest` — Agent Card per platform conventions
- `POST /api/v1/analyze` — analyze a raw text snippet through the CTI pipeline
- `GET /api/v1/threats` — list processed threat intelligence items (supports `limit`, `severity` filters)
- `GET /api/v1/threats/{id}` — full threat detail with ops/exec reports
- `GET /admin/sources` — manage intelligence sources (RSS, Telegram, URL, Reddit)
- `GET /admin/assets` — manage infrastructure asset inventory (supports CSV import)
- `GET /admin/settings` — configure LLM models, prompts, and ingestion schedule

## Skills

| Skill ID | Description | Key Inputs |
|---|---|---|
| `ti.analyze` | Analyze a text snippet for cyber threat intelligence | `content`, `source_url`, `source_name` |
| `ti.inventory` | Manage infrastructure asset inventory for threat correlation | — |
| `ti.report` | Retrieve generated threat intelligence reports | `limit`, `severity` |

## Pipeline Architecture

```
Ingestor → Analyst → [ClawBridge?] → InfraGuard → Publisher
```

| Node | Model | Role |
|---|---|---|
| **Ingestor** | `triage_model` | Classifies content as threat or noise, extracts CVEs/severity |
| **Analyst** | `analyst_model` | Deep analysis, attack vectors, detection strategies |
| **ClawBridge** | — | Optional deep research via OpenClaw (if `needs_deep_research`) |
| **InfraGuard** | `infra_model` | Correlates threat with asset inventory, calculates exposure |
| **Publisher** | `analyst_model` | Generates Operations Report (Markdown) and Executive Summary |

## Source Types

| Type | Description |
|---|---|
| `rss` | RSS/Atom feed, polled every N minutes via feedparser |
| `telegram` | Telegram public channel, resolved by username/URL/ID via Bot API |
| `url` | Raw URL, fetched and truncated to 8 000 chars |
| `reddit` | URL-based (future: dedicated Reddit client) |

### Adding a Telegram Channel

The admin UI supports automatic channel resolution. Enter any of:
- `@channelname`
- `https://t.me/channelname`
- `-1001234567890` (numeric ID)

The system calls Telegram Bot API (`getChat`) to resolve metadata and stores the permanent channel ID.

**Requires:** `TELEGRAM_BOT_TOKEN` environment variable.

## Storage

| Store | Details |
|---|---|
| PostgreSQL | DB: `ti_analyst`, user: `ti_analyst`, auto-migrated on startup |
| OpenSearch | Indices: `ti_analyst_assets`, `ti_analyst_threats` |

### Migrations

| ID | Description |
|---|---|
| 001 | Initial schema (threat_sources, assets, threat_intel, analysis_runs, agent_settings) |
| 002 | Telegram source fields (telegram_id, telegram_title, telegram_username; url nullable) |
| 003 | Fix default model names to match local LiteLLM aliases |

## Configuration

All settings are environment variables (loaded via Pydantic `BaseSettings`):

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://ti_analyst:ti_analyst@postgres:5432/ti_analyst` | PostgreSQL connection |
| `LITELLM_BASE_URL` | `http://litellm:4000` | LiteLLM proxy URL |
| `TRIAGE_MODEL` | `free` | Model alias for ingestor node |
| `ANALYST_MODEL` | `cheap` | Model alias for analyst/publisher nodes |
| `INFRA_MODEL` | `free` | Model alias for InfraGuard node |
| `TELEGRAM_BOT_TOKEN` | — | Bot token for channel resolution and alerts |
| `TELEGRAM_ALERT_CHAT_ID` | — | Chat ID to send high/critical alerts |
| `OPENCLAW_ENABLED` | `false` | Enable OpenClaw deep research integration |
| `INGESTION_CRON` | `0 */1 * * *` | Cron expression for scheduled ingestion |
| `OPENSEARCH_URL` | `http://opensearch:9200` | OpenSearch endpoint |

## Observability

- Structured logs to OpenSearch index `ti-analyst-logs` via `OpenSearchHandler`
- `X-Trace-Id` / `X-Request-Id` propagated on all requests
- LLM calls log: model name, duration (ms), prompt/completion token counts
- `AnalysisRun` records track pipeline executions with start/end time, trigger, and counts
