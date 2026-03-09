# Change: Add ti-analyst Agent (Sentinel-AI CTI)

## Why
Security teams need automated cyber threat intelligence processing. The ti-analyst agent ingests threat feeds, correlates them against asset inventory, and produces actionable reports.

## What Changes
- New `ti-analyst` agent under `apps/ti-analyst/`
- FastAPI service with LangGraph multi-agent pipeline (Ingestor → Analyst → InfraGuard → Publisher)
- OpenSearch integration for asset inventory and threat vector storage
- Admin UI for source management, asset inventory, and model configuration
- REST API for triggering analysis and querying threats
- Postgres DB for relational data (sources, assets, threats, runs)
- Docker compose integration at port 8088

## Impact
- Affected specs: ti-analyst (new capability)
- Affected code: docker/postgres/init/*.sql, docker/traefik/traefik.yml, compose.yaml, new compose.agent-ti-analyst.yaml
