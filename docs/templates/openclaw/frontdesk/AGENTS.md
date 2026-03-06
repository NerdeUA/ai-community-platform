# AGENTS.md - Routing Matrix

## Goal

Map user intents to concrete platform tools discovered from Core.

## Active Tool Map

| Intent Cluster | Primary Tool | Optional Secondary | Notes |
|---|---|---|---|
| Greeting / onboarding | `hello_greet` | none | Must call tool when available |
| Knowledge lookup / Q&A | `knowledge_search` | none | Prefer tool over direct answer |
| Knowledge ingestion / extract | `knowledge_upload` | none | Requires explicit user intent |
| News curation | `news_curate` | none | Use for summarize/prepare requests |
| News publishing | `news_publish` | none | Confirm before publish action |

Note:

- Runtime tool names come from OpenClaw registration and may use underscores.
- Do not rewrite tool ids during invocation.

## Selection Rules

1. Pick one tool per user turn unless the user explicitly asks for multi-step workflow.
2. If two intents overlap, choose the tool with stricter schema and clearer action verb.
3. If no valid tool exists in discovery payload, return "capability unavailable".
4. Never substitute missing tools with invented internal logic.

## Confirmation Rules

Require explicit confirmation before calling:

- `knowledge_upload`
- `news_publish`

Confirmation format:

- "Підтвердьте дію: виконати `<tool>` з поточними параметрами?"

## Safety Rules

1. Preserve `request_id` for retries and follow-ups.
2. Do not retry more than once on transport errors.
3. If Core returns `agent_disabled` or `unknown_tool`, stop and explain limitation.
