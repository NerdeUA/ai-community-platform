# Agent Storage Provisioning

## Overview

Each agent declares its storage requirements in the Agent Card's `storage` section. When an admin enables an agent, the platform provisions the required resources (database, Redis DB, OpenSearch indices) before the agent is marked as installed/enabled.

## Manifest `storage` Section

The `storage` key is optional. If present, it declares what infrastructure the agent needs:

```json
{
  "name": "my-agent",
  "version": "1.0.0",
  "storage": {
    "postgres": {
      "db_name": "my_agent",
      "user": "my_agent",
      "password": "my_agent"
    },
    "redis": {
      "db_number": 1
    },
    "opensearch": {
      "collections": ["chunks", "pages"]
    }
  }
}
```

### Postgres

| Field | Type | Required | Constraint |
|-------|------|----------|------------|
| `db_name` | string | yes | `/^[a-z][a-z0-9_]*$/` |
| `user` | string | yes | `/^[a-z][a-z0-9_]*$/` |
| `password` | string | yes | non-empty |

Provisioning creates: user (CREATE USER), database (CREATE DATABASE), GRANT ALL PRIVILEGES.

### Redis

| Field | Type | Required | Constraint |
|-------|------|----------|------------|
| `db_number` | integer | yes | 0-15 |

Redis databases exist implicitly. Provisioning verifies connectivity and records the assignment.

### OpenSearch

| Field | Type | Required | Constraint |
|-------|------|----------|------------|
| `collections` | string[] | yes | non-empty, each `/^[a-z][a-z0-9_-]*$/` |

Index names are prefixed with the agent name: `{agent_name}_{collection}` (e.g., `knowledge_agent_chunks`).

## Provisioning Lifecycle

1. Admin clicks **Enable** on the agent
2. Core checks `installed_at` — if null and manifest has `storage`:
   - **PostgresInstallStrategy**: CREATE USER + CREATE DATABASE (idempotent)
   - **RedisInstallStrategy**: verify DB number reachable
   - **OpenSearchInstallStrategy**: PUT index for each collection (idempotent)
3. Core calls agent's `POST /api/v1/internal/migrate` endpoint
4. Agent runs its Doctrine migrations (schema + seed data)
5. Core marks `installed_at = now()` in registry
6. Agent is enabled and synced with OpenClaw

Discovery/registration alone does **not** provision storage. Provisioning is intentionally deferred to the **Enable** action to avoid side effects from passive discovery.

Re-enabling a previously installed agent **skips provisioning** (installed_at already set).

## Agent Migration Endpoint

Agents that declare `storage.postgres` **must** expose:

```
POST /api/v1/internal/migrate
Header: X-Platform-Internal-Token: {token}
Response: {"status": "ok", "output": "..."} or {"status": "error", "error": "..."}
```

This endpoint runs `doctrine:migrations:migrate --no-interaction` (or equivalent).

## Docker Compose Environment Variables

Agent storage credentials come from compose.yaml environment vars:

```yaml
my-agent:
  environment:
    DATABASE_URL: postgresql://my_agent:my_agent@postgres:5432/my_agent
    REDIS_URL: redis://redis:6379/1
    OPENSEARCH_URL: http://opensearch:9200
    OPENSEARCH_INDEX: my_agent_chunks
```

This enables multi-instance deployments with different credentials per environment.

## No Deletion Strategy

Storage is **never deleted** when an agent is disabled. This is by design — data preservation is the safe default. Cleanup, if needed, is a manual operation.
