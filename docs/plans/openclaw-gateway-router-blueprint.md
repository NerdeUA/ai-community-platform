# Plan: OpenClaw as Thin Gateway/Router for Community Platform

## 1. Target Architecture

### Principle

`OpenClaw` is a frontdesk runtime only.  
`Core (Symfony 7)` remains source of truth for routing policy, agent registry, auth, audit, and orchestration outcomes.

### Request Flow (MVP)

1. Telegram user sends message to `@ai_toloka_bot`.
2. OpenClaw receives the update and performs lightweight intent classification.
3. OpenClaw calls Core discovery/invoke API only:
   - `GET /api/v1/a2a/discovery`
   - `POST /api/v1/a2a/send-message`
4. Core resolves tool -> enabled agent -> A2A endpoint.
5. Core calls agent, collects result, logs trace/audit, returns normalized response.
6. OpenClaw formats concise response and sends it back to Telegram.

### Ownership Boundaries

- Core owns:
  - business routing rules
  - tool/agent eligibility
  - async task lifecycle and retries
  - queueing/concurrency policies
  - observability and compliance logs
- OpenClaw owns:
  - Telegram session UX
  - clarification turn before invocation
  - delegation to Core bridge

## 2. Best Practices to Restrict OpenClaw

1. Delegate-first policy: OpenClaw should only answer directly for greeting/clarification/meta-help.
2. No direct agent calls: OpenClaw must not call `hello-agent`, `knowledge-agent`, etc. directly.
3. Disable native ad-hoc tools but keep policy skills loading in frontdesk profile (`commands.native=false`, `nativeSkills=auto`), and add plugin tools additively (`tools.profile=messaging`, `tools.alsoAllow=["platform-tools"]`).
4. Use strict routing docs (`SOUL.md`, `AGENTS.md`, `TOOLS.md`) as runtime instructions.
5. Enforce idempotency via `request_id` for retries and duplicate Telegram updates.
6. Keep OpenClaw stateless for platform facts; all stateful decisions go through Core.
7. Treat unknown/ambiguous intent as clarification request, not a fabricated answer.

## 3. Queue + Concurrency Model (Core)

### Suggested Queues

- `openclaw_inbound` - ingest/update normalization, dedup by message id.
- `agent_invoke` - routed A2A calls to agents.
- `telegram_outbound` - response delivery and retry-safe send/edit operations.

### Concurrency Strategy

- Per-chat serialization key: process one active command per `(bot_id, chat_id, thread_id)`.
- Agent queue workers scaled independently from inbound workers.
- Short timeout budget for frontdesk path; long-running tasks should switch to async task mode.
- Use dead-letter handling for repeated downstream failures.

See template: `docs/templates/openclaw/frontdesk/symfony.messenger.openclaw.example.yaml`.

## 4. Multi-Agent / Multi-Bot Strategy

### Multi-Agent

- Single Core registry for all agents.
- OpenClaw discovers only enabled skills from Core.
- Core decides eligibility, canary rollout, and disabled-state behavior.

### Multi-Bot (Recommended)

- Run one OpenClaw runtime per Telegram bot persona/community.
- Separate state directory and env/token per bot.
- Shared Core bridge with bot identifier headers/metadata for policy partitioning.

See template: `docs/templates/openclaw/frontdesk/compose.openclaw.multi-bot.example.yaml`.

## 5. Step-by-Step Setup

1. Bootstrap stack and secrets (`make bootstrap`, `make up`).
2. Ensure OpenClaw bridge targets A2A routes in Core:
   - discovery: `/api/v1/a2a/discovery`
   - invoke: `/api/v1/a2a/send-message`
3. Install full frontdesk policy pack from templates:
   - `IDENTITY.md`
   - `USER.md`
   - `SOUL.md`
   - `AGENTS.md`
   - `TOOLS.md`
   - `HEARTBEAT.md`
   - `BOOTSTRAP.md`
   - `MEMORY.md`
4. Configure Telegram channel:
   - `dmPolicy=pairing`
   - `groupPolicy=open`
   - `requireMention=true`
   - `streaming=partial`
5. Approve pairing and validate end-to-end route using one known tool (`hello.greet`).
6. Enable queue workers for inbound/invoke/outbound paths in Core.
7. Add observability checks for `trace_id`, `request_id`, `x-agent-run-id`, `x-a2a-hop`.
8. Roll out additional bots or agents progressively (enable in registry, then verify discovery snapshot).

## 6. Files to Start From

- `docs/templates/openclaw/frontdesk/SOUL.md`
- `docs/templates/openclaw/frontdesk/AGENTS.md`
- `docs/templates/openclaw/frontdesk/TOOLS.md`
- `docs/templates/openclaw/frontdesk/IDENTITY.md`
- `docs/templates/openclaw/frontdesk/USER.md`
- `docs/templates/openclaw/frontdesk/HEARTBEAT.md`
- `docs/templates/openclaw/frontdesk/BOOTSTRAP.md`
- `docs/templates/openclaw/frontdesk/MEMORY.md`
- `docs/templates/openclaw/frontdesk/openclaw.frontdesk.example.json`
- `docs/templates/openclaw/frontdesk/compose.openclaw.multi-bot.example.yaml`
- `docs/templates/openclaw/frontdesk/symfony.messenger.openclaw.example.yaml`
