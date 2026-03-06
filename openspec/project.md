# Project Context

## Purpose
`AI Community Platform` is an MVP for a modular agent platform built on top of a single community chat, starting with Telegram.

The product goal is to reduce chaos in community chats by adding structured, optional agent modules that can be enabled or disabled per community. The core platform provides shared infrastructure, while each agent solves a focused problem.

Initial MVP value areas:

- preserving useful knowledge from chat discussions
- building a searchable catalog of locations, services, and trusted contacts
- generating digest summaries of important updates
- surfacing explainable anti-fraud risk signals

The project is currently documentation-first. Product scope, architecture, and agent definitions are being formalized before implementation.

## Tech Stack
The core-platform stack is fixed for the initial implementation:

- `PHP 8.5`
- `Symfony 7`
- `Codeception` for testing
- `PHPStan` for static analysis
- `PHP CS Fixer` for code style enforcement
- `GitLab CI` for CI pipelines
- `glab` for GitLab CLI workflows

Current platform assumptions:

- a backend bot service that integrates with Telegram
- Postgres as the primary storage
- basic full-text search in MVP scope
- a single runtime process for the initial version
- OpenClaw is an optional runtime candidate for the `core-agent` layer only, not for platform ownership

Implementation assumptions already documented:

- one Telegram integration
- one database
- no separate web admin panel in MVP
- no complex async infrastructure in the first release
- if OpenClaw is used in MVP, it should remain replaceable and bounded behind platform-owned interfaces

## Project Conventions

### Documentation Language
- Human-facing product and planning documents under `docs/` should keep a Ukrainian canonical version
- The `docs/` directory is the primary source of truth for product context, MVP scope, agent PRDs, and delivery planning
- Bilingual documents use **folder-based** language separation: `ua/` for Ukrainian canonical, `en/` for English mirror
  - Example: `docs/agents/ua/hello-agent.md` (Ukrainian) + `docs/agents/en/hello-agent.md` (English)
  - The `ua/` and `en/` folders sit inside the relevant section folder (e.g., `docs/agents/`, `docs/specs/`)
- **Deprecated**: the `.en.md` suffix convention (`docs/foo.md` + `docs/foo.en.md`) is superseded by the folder convention above; existing files may still use it until migrated
- Coding-oriented artifacts should remain in English (no `ua/en` split needed)
- OpenSpec documents, technical specifications, contracts, implementation-facing notes, and code-adjacent documentation should remain in English
- When a document is primarily for clients, operators, or product stakeholders, default to Ukrainian
- When a document is primarily for developers or AI coding agents, default to English

### Code Style
- Prefer simple, explicit, readable code over abstraction-heavy designs
- Keep the first implementation small and aligned with MVP scope
- Use stable, descriptive naming for agents, events, commands, and database entities
- Prefer modular boundaries that map directly to product concepts: `core`, `adapters`, `agents`, `shared services`
- Avoid introducing large speculative frameworks before the core contracts are stable

### Architecture Patterns
The intended architecture is modular and event-driven.

Core patterns:

- `Telegram Adapter` receives platform events and normalizes them into internal events
- `Event Bus` dispatches normalized events to platform core and enabled agents
- `Agent Registry` stores available agents, manifests, config, and enabled/disabled state
- `Command Router` handles chat commands and routes them to platform handlers or agent handlers
- `Shared Services` provide storage, search, scheduling, logging, and common infra

Platform ownership should remain inside this repository's architecture. If OpenClaw is adopted, it should sit inside the `core-agent/orchestrator` layer rather than replacing the platform boundary.

Recommended boundary:

- platform owns chat gateway, data, permissions, moderation, registry, and product APIs
- core-agent owns orchestration, intent routing, clarification, and response composition
- OpenClaw may serve as the runtime shell for the core-agent

Agent contract expectations:

- every agent has a `manifest`
- every agent has a `config schema`
- every agent declares supported commands and subscribed events
- agents expose one or more handlers such as `onMessage`, `onCommand`, `onSchedule`

MVP architecture boundaries:

- single-chat scope
- single runtime process
- single database
- no marketplace or plugin distribution system yet
- no advanced RBAC/ACL model beyond `admin`, `moderator`, `user`

### Testing Strategy
The project is still in specification and planning phase, but the testing/tooling stack is already fixed.

When implementation starts, testing should follow these priorities:

- verify core command flows: `/help`, `/agents`, `/agent enable`, `/agent disable`
- verify that disabled agents do not receive events
- verify agent happy paths and failure modes independently
- validate database write paths for `messages`, `knowledge`, `locations`, `digests`, and `fraud_signals`
- prioritize behavior tests around event routing, permissions, and agent command UX
- use `Codeception` as the primary test framework for the core-platform
- run `PHPStan` in CI as a required static analysis step
- run `PHP CS Fixer` in CI or pre-merge checks to enforce formatting expectations

For OpenSpec changes:

- proposal and spec changes should be validated with OpenSpec before implementation
- architecture and data model changes should be reflected in specs before coding

### Git Workflow
Git workflow is not formally defined yet.

Current expectation:

- use small, focused changes
- keep documentation, specs, and implementation aligned
- MVP conflict policy: if contracts, docs, or implementation conflict, the team MAY perform breaking rewrites/refactors to restore a coherent architecture
- for this MVP phase, EVERY change starts with an OpenSpec proposal in `openspec/changes/<change-id>/` before implementation
- avoid implementing any change before the relevant proposal is reviewed
- use `GitLab CI` as the default CI system
- use `glab` as the preferred CLI for GitLab-native workflows when working with merge requests and pipelines

If the team formalizes branch naming or commit message rules later, this section should be updated.

## Domain Context
This product targets community-driven chat environments where valuable information is otherwise trapped in message history.

Primary domain problems:

- useful answers disappear in long chat streams
- important updates are repeated or lost
- trusted recommendations for places and services are not structured
- fraud, spam, and manipulative behavior reduce trust

The product model is "WordPress + plugins for community chats":

- the platform has a shared core
- each need is implemented as an independent agent/module
- communities can enable or disable agents based on their own culture and needs

Current MVP agents:

- `Knowledge Extractor / Community Wiki`
- `Locations Catalog`
- `News Digest`
- `Anti-fraud Signals`

Core user roles:

- `admin` / `owner`
- `moderator`
- `member`

## Important Constraints
- MVP is limited to one Telegram community/chat
- No multi-tenant support in the initial release
- A minimal web admin panel is included in MVP scope: login + protected dashboard; full management UI is out of scope for MVP
- Anti-fraud in MVP must be advisory only; no automatic bans
- Agent actions should be explainable, especially risk-related signals
- Basic command responses should complete within roughly 2-3 seconds
- The implementation should avoid overbuilding before validating real usage in the first pilot
- Several product decisions remain intentionally open, including final runtime language and whether LLM features are included in MVP
- If OpenClaw is used, third-party skills/extensions must not be trusted by default and should be reviewed before use
- Any OpenClaw-based runtime should be isolated and granted only the minimum required tool access

## External Dependencies
- Telegram Bot API is the primary external integration for MVP
- Postgres is the planned storage dependency
- OpenSpec is used for spec-driven planning and change management within the repository

Potential future dependencies, not yet committed:

- LLM provider(s) for summarization, extraction, or classification
- embedding/vector search infrastructure if search evolves beyond basic full-text
