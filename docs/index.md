# AI Community Platform — Agent Index

## Deployed Agents

| Agent | Stack | Status | Manifest | PRD |
|-------|-------|--------|----------|-----|
| [hello-agent](../apps/hello-agent/) | PHP 8.5 / Symfony 7 | Active | `/api/v1/manifest` | [EN](agents/en/hello-agent.md) · [UA](agents/ua/hello-agent.md) |
| [knowledge-agent](../apps/knowledge-agent/) | PHP 8.5 / Symfony 7 | Active | `/api/v1/manifest` | — |
| [news-maker-agent](../apps/news-maker-agent/) | Python / FastAPI | Active | `/api/v1/manifest` | — |
| [dev-reporter-agent](../apps/dev-reporter-agent/) | PHP 8.5 / Symfony 7 | Active | `/api/v1/manifest` | [EN](agents/en/dev-reporter-agent.md) · [UA](agents/ua/dev-reporter-agent.md) |

## Planned Agents (PRD only)

| Agent | PRD |
|-------|-----|
| anti-fraud-signals | [EN](agents/en/anti-fraud-signals-prd.md) · [UA](agents/ua/anti-fraud-signals-prd.md) |
| knowledge-extractor | [EN](agents/en/knowledge-extractor-prd.md) · [UA](agents/ua/knowledge-extractor-prd.md) |
| locations-catalog | [EN](agents/en/locations-catalog-prd.md) · [UA](agents/ua/locations-catalog-prd.md) |
| news-digest | [EN](agents/en/news-digest-prd.md) · [UA](agents/ua/news-digest-prd.md) |

## Platform Core

| Component | Path | Description |
|-----------|------|-------------|
| [core](../apps/core/) | `apps/core/` | Admin UI, A2A gateway, agent registry, log viewer |

## Key Links

- [Agent conventions](agent-requirements/conventions.md)
- [Agent Card schema](../apps/core/config/agent-card.schema.json)
- [Local dev guide](local-dev.md)
- [A2A terminology mapping (EN)](specs/en/a2a-terminology-mapping.md)
