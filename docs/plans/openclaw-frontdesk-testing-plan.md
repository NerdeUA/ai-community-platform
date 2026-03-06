# Plan: OpenClaw Frontdesk Testing Plan

## 1. Goal

Підтвердити, що OpenClaw працює як thin router/frontdesk для community platform:

- не відповідає самостійно там, де потрібні агенти
- викликає Core тільки через A2A gateway
- стабільно обробляє Telegram потік та помилки
- зберігає трасування і коректну деградацію

## 2. Scope

У межах плану:

- OpenClaw runtime config (`openclaw.json`, workspace policy files)
- Core endpoints:
  - `GET /api/v1/a2a/discovery`
  - `POST /api/v1/a2a/send-message`
- `platform-tools` plugin у OpenClaw gateway
- Symfony Messenger базовий runtime config
- Telegram binding для `@ai_toloka_bot`

Поза scope:

- навантажувальне тестування > 1k RPS
- production TLS/webhook hardening
- повний e2e suite усіх бізнес-фіч платформи

## 3. Preconditions

1. Стек піднятий (`make up`), `openclaw-gateway` у статусі `healthy`.
2. Core міграції застосовані (`make migrate`).
3. Telegram bot token і pairing активні.
4. У workspace OpenClaw присутні:
   - `IDENTITY.md`
   - `USER.md`
   - `SOUL.md`
   - `AGENTS.md`
   - `TOOLS.md`
   - `HEARTBEAT.md`
   - `BOOTSTRAP.md`
   - `MEMORY.md`

## 4. Work Breakdown

### Phase 1: Config And Contract Smoke

- [ ] 1.1 Перевірити, що OpenClaw config валідний (`openclaw config get` працює без config errors).
- [ ] 1.2 Перевірити `commands.native=false`, `commands.nativeSkills=auto`, `tools.profile=messaging`, `tools.alsoAllow` включає `platform-tools`.
- [ ] 1.3 Перевірити, що plugin `platform-tools` ініціалізується та реєструє tools.
- [ ] 1.3.1 Перевірити runtime naming tools (`hello_greet`, `news_curate`, `news_publish`) і відсутність мапінг-помилок `dot->underscore`.
- [ ] 1.4 Перевірити `GET /api/v1/a2a/discovery` з валідним токеном (200, непорожній `tools`).
- [ ] 1.5 Перевірити `GET /api/v1/a2a/discovery` без токена (401).

### Phase 2: Core Routing Integration

- [ ] 2.1 Викликати `hello.greet` через `POST /api/v1/a2a/send-message`, очікувати `status=completed`.
- [ ] 2.1 Викликати runtime tool `hello_greet` (або `hello.greet` якщо саме так повертається discovery), очікувати `status=completed`.
- [ ] 2.2 Викликати невідомий tool, очікувати `status=failed`, `reason=unknown_tool`.
- [ ] 2.3 Вимкнути агента в registry, викликати його tool, очікувати `reason=agent_disabled`.
- [ ] 2.4 Перевірити, що OpenClaw не робить прямих викликів в agent service URL (тільки Core gateway path).
- [ ] 2.5 Перевірити ідемпотентний retry з тим самим `request_id` для transport failure сценарію.

### Phase 3: Telegram UX Flow

- [ ] 3.1 DM flow: `/start`, pairing, перший user message -> валідна відповідь.
- [ ] 3.2 Group flow: бот відповідає тільки на `@mention`.
- [ ] 3.3 Для state-changing intent (`knowledge.upload`, `news.publish`) бот просить explicit confirmation.
- [ ] 3.4 При помилці tool user отримує коротке повідомлення + `request_id` (якщо доступний).

### Phase 4: Messenger Runtime Checks

- [ ] 4.1 `php bin/console lint:yaml config/packages/messenger.yaml` — OK.
- [ ] 4.2 `php bin/console lint:container` — OK.
- [ ] 4.3 Перевірити створення/використання transport queues (`openclaw_inbound`, `agent_invoke`, `telegram_outbound`, `failed`) у Doctrine transport.
- [ ] 4.4 Перевірити, що помилкове повідомлення потрапляє у `failed` після вичерпання retry.

### Phase 5: Observability And Security Baseline

- [ ] 5.1 У логах OpenClaw є `discovery fetch` і `tool execute` події з кореляцією.
- [ ] 5.2 У Core логах на invoke присутні `trace_id`, `request_id`, `x-agent-run-id`, `x-a2a-hop`.
- [ ] 5.2.1 У LiteLLM `Request Logs` поле `End User` заповнене для OpenClaw LLM-викликів (через `x-litellm-end-user-id`).
- [ ] 5.3 Перевірити redaction: токени/секрети не потрапляють у лог payload.
- [ ] 5.4 Зафіксувати актуальні security warnings OpenClaw і створити follow-up hardening задачі.

## 5. Suggested Command Set

```bash
# Stack status
docker compose ps
docker compose logs --tail 100 openclaw-gateway

# OpenClaw config checks
docker compose exec -T openclaw-cli openclaw config get commands.native
docker compose exec -T openclaw-cli openclaw config get commands.nativeSkills
docker compose exec -T openclaw-cli openclaw config get tools.profile
docker compose exec -T openclaw-cli openclaw config get tools.alsoAllow.0

# Core endpoint checks (tokenized)
curl -H "Authorization: Bearer $OPENCLAW_GATEWAY_TOKEN" \
  http://localhost/api/v1/a2a/discovery

curl -X POST -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENCLAW_GATEWAY_TOKEN" \
  -d '{"tool":"hello.greet","input":{"name":"Nazar"},"trace_id":"trace_test_1","request_id":"req_test_1"}' \
  http://localhost/api/v1/a2a/send-message

# Symfony config checks
docker compose exec -T core php bin/console lint:yaml config/packages/messenger.yaml
docker compose exec -T core php bin/console lint:container
```

## 6. Exit Criteria

1. Усі пункти Phase 1-3 виконані без блокуючих дефектів.
2. Усі пункти Phase 4 виконані, Messenger config валідний і працездатний.
3. Критичні observability/security пункти Phase 5 виконані або мають зафіксовані follow-up задачі.
4. Для кожного дефекту є severity, reproduction steps, і owner.

## 7. Defect Severity Guide

- `S1` - повний outage маршрутизації або витік секретів.
- `S2` - некоректний routing/failed delegation для основних сценаріїв.
- `S3` - UX або observability деградація без функціонального блокеру.

## 8. Deliverables

1. Заповнений чекліст цього плану.
2. Короткий test report (pass/fail + defects).
3. Список hardening/follow-up задач для production rollout.
