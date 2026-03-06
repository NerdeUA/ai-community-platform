# Agent Platform Conventions

Every service that participates in the AI Community Platform agent ecosystem MUST implement the
conventions described here. These are the minimum contracts that allow `core` to discover,
register, verify, and manage agents automatically — without any agent-specific code in core.

---

## 1. Docker Compose Naming & Labels

Every agent service in `compose.yaml` MUST:

| Requirement | Value |
|---|---|
| Service name | End with `-agent` (e.g., `knowledge-agent`, `news-maker-agent`) |
| Docker label | `ai.platform.agent=true` |
| Docker label | `ai.platform.manifest.path=/api/v1/manifest` *(optional override, default assumed)* |

**Example:**
```yaml
services:
  knowledge-agent:
    build: ...
    labels:
      - "ai.platform.agent=true"
    networks:
      - platform
```

Core discovers agents by querying the Traefik API for services matching the `*-agent` naming
pattern. The Docker label provides an explicit opt-in for non-standard service names.

---

## 2. Agent Card Endpoint

**`GET /api/v1/manifest`** — REQUIRED, no authentication.

Returns the Agent Card — agent metadata used by core for registration, skill routing, and the A2A Gateway skill catalog.

### Minimum valid response (HTTP 200):

```json
{
  "name": "knowledge-agent",
  "version": "1.2.0",
  "url": "http://knowledge-agent/api/v1/knowledge/a2a",
  "skills": [
    { "id": "knowledge.search", "name": "Knowledge Search", "description": "Search the knowledge base" }
  ]
}
```

### Full response schema (aligned with official A2A AgentCard):

```json
{
  "name":               "string (required) — stable slug, kebab-case",
  "version":            "string (required) — semver e.g. 1.0.0",
  "description":        "string (recommended)",
  "url":                "string (URL) — A2A Server endpoint (replaces deprecated a2a_endpoint)",
  "provider":           { "organization": "string", "url": "string (URL)" },
  "capabilities":       { "streaming": false, "pushNotifications": false },
  "defaultInputModes":  ["text"],
  "defaultOutputModes": ["text"],
  "skills": [
    {
      "id":          "skill.name",
      "name":        "Human-Readable Name",
      "description": "What this skill does",
      "tags":        ["tag1"],
      "examples":    ["Example prompt"]
    }
  ],
  "skill_schemas": { "<skill-id>": { "input_schema": {} } },
  "permissions":        ["admin"],
  "commands":           ["/wiki"],
  "events":             ["message.created"],
  "health_url":         "string (URL, optional)",
  "admin_url":          "string (optional)",
  "storage":            { "postgres": {}, "redis": {}, "opensearch": {} }
}
```

### Field rules:

| Field | Required | Notes |
|---|---|---|
| `name` | ✅ | Stable identifier. Changing it creates a new agent in registry |
| `version` | ✅ | Must follow semver `MAJOR.MINOR.PATCH` |
| `url` | if skills ≠ [] | A2A Server endpoint URL (official A2A field). Legacy `a2a_endpoint` accepted |
| `skills` | recommended | Array of `AgentSkill` objects or legacy string IDs |
| `capabilities` | recommended | A2A protocol capabilities: `{ streaming, pushNotifications }` |
| `provider` | optional | `{ organization }` — service provider info |
| `health_url` | optional | Defaults to `http://<service-hostname>/health` |
| `admin_url` | optional | Shown as link in core admin panel |
| `skill_schemas` | deprecated | Fold input schemas into structured skills instead |

### Validation behavior in core:

| Manifest state | Core behavior | Agent status |
|---|---|---|
| Valid, all required fields | Full registration | `healthy` |
| Valid but missing optional fields | Partial registration with warnings | `degraded` |
| `name` or `version` missing | Registration blocked | `error` |
| Connection refused / timeout | Not registered (or previous registration kept) | `unavailable` |
| Invalid JSON | Error stored, raw response saved | `error` |

---

## 3. Health Endpoint

**`GET /health`** — REQUIRED, no authentication.

```json
{"status": "ok"}
```

HTTP 200 always (even during degraded state — the agent is responsible for its own health logic).
Core uses this endpoint for liveness polling every 60 seconds.

---

## 4. A2A Endpoint

**`POST /api/v1/a2a`** — REQUIRED if `skills` is non-empty.

Standard request envelope:

```json
{
  "tool":       "search_knowledge",
  "input":      { "query": "..." },
  "trace_id":   "uuid",
  "request_id": "uuid"
}
```

Standard response envelope:

```json
{
  "status":  "completed | failed | needs_clarification",
  "output":  { ... },
  "error":   "string or null"
}
```

Rules:
- MUST return HTTP 200 even for business-level errors (use `status: "failed"`)
- MUST return HTTP 400/422 for malformed request envelopes
- MUST NOT return unstructured plain text as the primary response
- MUST handle unknown `tool` values with `status: "failed"` + descriptive `error`
- MUST be idempotent for the same `request_id`

---

## 5. Convention Verification in Core

Core includes `AgentConventionVerifier` which checks all registered agents on demand and
on every discovery cycle. It reports violations per-agent:

```
VIOLATION [knowledge-agent]: url (or a2a_endpoint) missing but skills declared
VIOLATION [news-maker-agent]: version "1.0" does not match semver pattern
```

Violations are stored in the agent registry row and shown in the admin panel.
Admins can click a badge to view the full violation list.

---

## 6. State Model In Admin UI

Admin state rendering (runtime `enabled/disabled` + health/convention states) is defined in:

- `docs/agent-requirements/agent-state-model.md`

This state model is a contract for:

- operator-facing hint text,
- badge semantics,
- and stable selectors used by automated tests.

---

## 7. Adding a New Agent — Checklist

1. Add service to `compose.yaml` with name ending `-agent` and label `ai.platform.agent=true`
2. Implement `GET /api/v1/manifest` returning valid JSON
3. Implement `GET /health` returning `{"status": "ok"}`
4. If skills declared: implement `POST /api/v1/a2a`
5. Run `make conventions-test` — all checks must pass
6. Core auto-discovers on next discovery cycle (up to 60s) or via "Run Discovery" in admin panel

No manual registration required. No code changes in core needed.
