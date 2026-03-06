# A2A Protocol For Agents

## Purpose

This document defines how the platform aligns with the official A2A protocol while documenting the current implementation profile used in this repository.

It is intentionally explicit about:

- official A2A concepts we follow
- platform-specific transport choices used today
- migration path toward closer protocol alignment

## Normative References

- Official A2A topics (fetched snapshot in this repo):
  - `docs/fetched/a2a-protocol-org/en/key-concepts.md`
  - `docs/fetched/a2a-protocol-org/en/life-of-a-task.md`
  - `docs/fetched/a2a-protocol-org/en/streaming-and-async.md`
  - `docs/fetched/a2a-protocol-org/en/agent-discovery.md`

## Alignment Strategy

- We align to official A2A domain concepts: `Agent Card`, `Task`, `Message`, `Part`, `Artifact`.
- We keep explicit correlation across hops: `trace_id`, `request_id`, and step-level metadata.
- For MVP and current rollout, we use a platform-specific HTTP JSON envelope instead of full JSON-RPC 2.0.
- Async capabilities are phased:
  - R1: `SendStreamingMessage` + `GetTask`-style polling
  - R2: push notifications via webhook

Async work is tracked in:
`openspec/changes/add-a2a-streaming-and-push`.

## Official Model vs Current Platform Profile

| Area | Official A2A Model | Current Platform Profile |
|---|---|---|
| Payload format | JSON-RPC 2.0 over HTTP(S) | REST-style JSON envelope (`tool`/`input` and downstream `intent`/`payload`) |
| Core interaction object | `Message` or `Task` | Normalized response with `status`, optional `result`, optional `error` |
| Discovery location | Agent Card via well-known URI is recommended | Agent Card exposed via `GET /api/v1/manifest` |
| Agent invocation | RPC methods such as `SendMessage` | `POST /api/v1/a2a/send-message` at gateway, then HTTP POST to agent A2A endpoint |
| Async transport | Polling + SSE + Push | Sync request/response in production path today; SSE/polling/push are staged via OpenSpec change |
| Capability declaration | Agent Card declares async support (`capabilities.streaming`, `capabilities.pushNotifications`) and skills | Skills are declared in agent card profile; async flags are planned in streaming/push rollout |
| Security metadata | Agent Card `security` + HTTP auth mechanisms | HTTP token-based auth in gateway and internal platform headers/tokens |

## Interaction Modes

| Mode | Official A2A | Platform Status (2026-03-06) |
|---|---|---|
| Request/Response | Supported | Implemented and primary |
| Polling for task updates | Supported | Planned as explicit `GetTask`-style endpoint in R1 |
| SSE streaming | Supported | Planned in R1 (`send-streaming-message`) |
| Push notifications | Supported | Planned in R2 |

## Task Lifecycle Profile

The platform task/status model is aligned conceptually with official task lifecycle semantics:

- non-terminal states are tracked explicitly during execution
- terminal states are immutable once persisted
- follow-up interactions should preserve correlation and context continuity

Current and planned statuses in platform profile:

- `submitted`
- `working`
- `input_required`
- `completed`
- `failed`
- `canceled`
- `rejected`

## Correlation and Observability Contract

Every critical A2A step MUST emit structured telemetry with:

- `event_name`
- `step`
- `source_app`
- `target_app` (when available)
- `trace_id`
- `request_id`
- `status`
- `duration_ms` (for terminal steps)
- `sequence_order`

Sanitized diagnostic context SHOULD include:

- `step_input`
- `step_output`
- `request_headers`
- `capture_meta`

Secrets (`token`, `authorization`, `api_key`, `secret`, `password`, `cookie`) MUST be redacted before persistence.

## Compatibility Rules For New Changes

- New A2A-facing features SHOULD use official terminology (`Agent Card`, `Task`, `Skill`, `A2A Client`, `A2A Server`).
- Existing synchronous clients of `POST /api/v1/a2a/send-message` MUST remain backward compatible during R1.
- Any new async behavior MUST preserve polling recovery semantics (stream/push are not the only source of truth).
- If implementation diverges from official A2A transport semantics, the divergence MUST be documented in this file and in the related OpenSpec change.

## Out Of Scope For Current Release (R1)

- inter-cluster agent federation
- arbitrary incompatible agent-specific transport models
