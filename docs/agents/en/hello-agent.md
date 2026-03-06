# Hello Agent

## Purpose
Hello Agent is a minimal reference agent demonstrating the full agent lifecycle on the platform: client webview, Agent Card and health endpoint conventions, and admin configuration.

## Features
- Webview at `/` — displays a greeting message (default: "Hello, World!")
- `GET /health` — standard health check (`{"status": "ok"}`)
- `GET /api/v1/manifest` — Agent Card per platform conventions
- Configuration via admin panel: `description` and `system_prompt` fields

## Tech Stack
- PHP 8.5 + Symfony 7
- Apache (Docker)
- Traefik routing on port 8085

## Configuration
An administrator can configure via `/admin/agents` page:
- **Description** (`description`) — text displayed on the main screen
- **System Prompt** (`system_prompt`) — base prompt for the agent

Configuration is stored in the `agent_registry` table, `config` column (JSONB).

## Makefile Commands
- `make hello-setup` — build and install dependencies
- `make hello-install` — install PHP dependencies
- `make hello-test` — run Codeception tests
- `make hello-analyse` — PHPStan analysis
- `make hello-cs-check` / `make hello-cs-fix` — check/fix code style
