# OpenClaw Frontdesk Templates

Reference templates for configuring OpenClaw as a thin gateway/router ("frontdesk") for the AI Community Platform.

## Files

- `IDENTITY.md` - Stable identity and role boundaries for the frontdesk agent.
- `USER.md` - Human preferences and collaboration context.
- `SOUL.md` - Runtime behavior policy for the frontdesk agent.
- `AGENTS.md` - Routing matrix and eligibility rules for downstream agents.
- `TOOLS.md` - Tool-call contract used by OpenClaw when delegating through Core.
- `HEARTBEAT.md` - Optional periodic checks policy (disabled by default).
- `BOOTSTRAP.md` - Cold-start checklist for first run and restart recovery.
- `MEMORY.md` - Durable, non-secret project memory.
- `openclaw.frontdesk.example.json` - Sanitized OpenClaw runtime config example.
- `compose.openclaw.multi-bot.example.yaml` - Example topology for running multiple Telegram bots.
- `symfony.messenger.openclaw.example.yaml` - Queue and concurrency baseline for Symfony Messenger.

## Usage Notes

- Keep OpenClaw stateless regarding platform truth: no direct DB ownership and no direct agent service calls.
- OpenClaw should call Core only via:
  - `GET /api/v1/a2a/discovery`
  - `POST /api/v1/a2a/send-message`
- Keep `tools.profile=messaging` and enable bridge plugin tools through `tools.alsoAllow=["platform-tools"]`.
- Set `models.providers.<provider>.headers.x-litellm-end-user-id` so LiteLLM request logs clearly identify OpenClaw-originated calls.
- Place secrets in env files, not in JSON templates.
