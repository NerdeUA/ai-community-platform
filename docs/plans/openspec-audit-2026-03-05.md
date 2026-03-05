# OpenSpec Audit — 2026-03-05

## Scope

Аудит усіх активних `openspec/changes/*` з трьома цілями:

1. Заархівувати зміни зі статусом `✓ Complete`.
2. Зафіксувати поточний стан у документації.
3. Оцінити актуальність незавершених proposals відносно поточних `docs/` і `openspec/project.md`.

## Archived Today

Наступні changes заархівовано через `openspec archive <change-id> --yes`:

- `2026-03-05-add-admin-web-login`
- `2026-03-05-add-centralized-logging`
- `2026-03-05-add-hello-world-agent`
- `2026-03-05-add-langfuse-observability`
- `2026-03-05-add-local-dev-compose-topology`
- `2026-03-05-agent-storage-provisioning`
- `2026-03-05-bootstrap-platform-foundation`

Результат архівації:

- Створені актуальні `openspec/specs/*` для частини capability-спеків.
- `openspec validate --all --strict` пройшов успішно (0 помилок).

## Active Changes Audit

| Change | Tasks | Актуальність | Висновок |
|---|---:|---|---|
| `add-admin-agent-registry` | 30/38 | Висока | Залишити активним; добити UI/E2E та незавершені integration-task-и |
| `add-openclaw-agent-discovery` | 19/30 | Висока | Залишити активним; закрити тести, мережеві обмеження, доки для sync/polling |
| `add-knowledge-base-agent` | 46/79 | Висока | Залишити активним; пріоритет на стабілізацію API/worker/docs перед roadmap-фічами |
| `add-knowledge-base-agent-roadmap` | 0/20 | Середня | Тримати як backlog після завершення базового knowledge-agent |
| `add-ai-news-maker-agent` | 0/42 | Середня/низька | Потребує рескоупу під MVP (зараз занадто широкий і частково конфліктує з поточними MVP-обмеженнями) |
| `add-telegram-bot-integration` | 0/5 | Середня | Частково вже покрито `docs/local-dev.md` і `docs/plans/telegram-openclaw-integration-plan.md`; варто оновити tasks або змерджити з discovery/OpenClaw потоком |
| `refactor-agent-discovery` | 0/43 | Низька (частково superseded) | Багато пунктів вже реалізовано іншим потоком; рекомендується окремий cleanup-change для закриття дублювань |

## Relevance Notes (Docs-Based)

1. `refactor-agent-discovery` фактично частково реалізований у коді та доках:
   - є `agent:discovery`, `AgentConventionVerifier`, `make conventions-test`, `docs/agent-requirements/*`;
   - тому статус `0/43` не відображає реальний стан і виглядає застарілим.

2. `add-telegram-bot-integration` документно частково закритий:
   - у `docs/local-dev.md` вже є BotFather/polling/pairing workflow;
   - у `docs/plans/telegram-openclaw-integration-plan.md` уже описаний webhook/polling контур.

3. `add-knowledge-base-agent` залишається стратегічно актуальним:
   - відповідає `docs/product/ua/platform-mvp-prd.md` та архітектурним матеріалам;
   - але треба синхронізувати naming у документах (`knowledge-extractor` -> `knowledge-base`).

4. `add-ai-news-maker-agent` має високий обсяг і архітектурне розширення (окрема DB + повний editorial pipeline):
   - це варто узгодити з поточним MVP-фокусом перед стартом повної реалізації.

## Recommended Next Actions

1. Завершити та заархівувати в цьому порядку:
   - `add-admin-agent-registry`
   - `add-openclaw-agent-discovery`
   - `add-knowledge-base-agent`

2. Для `refactor-agent-discovery` створити cleanup-change:
   - або рознести залишки по активних change,
   - або формально позначити superseded і заархівувати без дублювання робіт.

3. Для `add-ai-news-maker-agent` зробити окремий scope-review:
   - визначити MVP-lite версію (мінімальний ingestion + publish flow),
   - решту перенести у roadmap.

4. Оновити планові документи під фактичний стан (насамперед knowledge/news/registry), щоб `docs/plans/*` не відставали від OpenSpec change-статусів.
