# MEMORY.md - Durable Memory

## Stable Facts

- Platform: `AI Community Platform`
- Telegram bot: `@ai_toloka_bot`
- Core backend: `Symfony 7`
- OpenClaw is configured as `thin router/frontdesk`
- Canonical Core bridge endpoints:
  - `GET /api/v1/a2a/discovery`
  - `POST /api/v1/a2a/send-message`

## Active Tools (Current Baseline)

- `hello_greet`
- `knowledge_search`
- `knowledge_upload`
- `news_curate`
- `news_publish`

Important:

- Actual runtime list may differ depending on enabled agents.
- Never present this baseline as guaranteed active set.

## Operating Rules

- Delegate-first for non-trivial requests.
- Confirm before state-changing operations (`knowledge_upload`, `news_publish`).
- On errors, expose `request_id` when available and suggest one actionable retry.

## Update Policy

- Append only durable project facts and preferences.
- Remove stale entries when architecture or tool map changes.
- Never store secrets or sensitive personal data.
