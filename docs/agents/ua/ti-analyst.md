# TI Analyst Agent (Sentinel-AI)

## Призначення

TI Analyst — агент автоматизованого аналізу кіберзагроз (CTI). Відстежує налаштовані джерела розвідки (RSS-стрічки, Telegram-канали, URL), обробляє контент через багатоетапний LangGraph-пайплайн, корелює загрози з інвентарем інфраструктурних активів і надсилає сповіщення про високі/критичні загрози через Telegram.

## Функції

- `GET /health` — стандартна перевірка стану (`{"status": "ok", "service": "ti-analyst"}`)
- `GET /api/v1/manifest` — Agent Card за конвенціями платформи
- `POST /api/v1/analyze` — аналіз довільного тексту через CTI-пайплайн
- `GET /api/v1/threats` — список оброблених загроз (параметри: `limit`, `severity`)
- `GET /api/v1/threats/{id}` — повна деталізація загрози з ops/exec-звітами
- `GET /admin/sources` — управління джерелами розвідки (RSS, Telegram, URL, Reddit)
- `GET /admin/assets` — управління інвентарем активів (підтримка імпорту CSV)
- `GET /admin/settings` — налаштування LLM-моделей, промтів і розкладу інгестії

## Скіли

| Skill ID | Опис | Ключові входи |
|---|---|---|
| `ti.analyze` | Аналіз тексту для розвідки кіберзагроз | `content`, `source_url`, `source_name` |
| `ti.inventory` | Управління інвентарем активів для кореляції загроз | — |
| `ti.report` | Отримання звітів про загрози | `limit`, `severity` |

## Архітектура пайплайну

```
Ingestor → Analyst → [ClawBridge?] → InfraGuard → Publisher
```

| Вузол | Модель | Роль |
|---|---|---|
| **Ingestor** | `triage_model` | Класифікує контент як загрозу або шум, витягує CVE/серйозність |
| **Analyst** | `analyst_model` | Глибокий аналіз, вектори атак, стратегії виявлення |
| **ClawBridge** | — | Опціональне дослідження через OpenClaw (якщо `needs_deep_research`) |
| **InfraGuard** | `infra_model` | Кореляція загрози з інвентарем активів, розрахунок впливу |
| **Publisher** | `analyst_model` | Генерація Operations Report (Markdown) та Executive Summary |

## Типи джерел

| Тип | Опис |
|---|---|
| `rss` | RSS/Atom-стрічка, опитується кожні N хвилин через feedparser |
| `telegram` | Публічний Telegram-канал, резолвиться за username/URL/ID через Bot API |
| `url` | Сирий URL, завантажується та обрізається до 8 000 символів |
| `reddit` | URL-подібний (майбутнє: окремий Reddit-клієнт) |

### Додавання Telegram-каналу

Адмін-UI підтримує автоматичне резолвення каналу. Введіть будь-який з форматів:
- `@channelname`
- `https://t.me/channelname`
- `-1001234567890` (числовий ID)

Система викликає Telegram Bot API (`getChat`), отримує метадані та зберігає постійний ID каналу.

**Потрібно:** змінна середовища `TELEGRAM_BOT_TOKEN`.

## Сховище

| Сховище | Деталі |
|---|---|
| PostgreSQL | БД: `ti_analyst`, користувач: `ti_analyst`, автоміграція при старті |
| OpenSearch | Індекси: `ti_analyst_assets`, `ti_analyst_threats` |

### Міграції

| ID | Опис |
|---|---|
| 001 | Початкова схема (threat_sources, assets, threat_intel, analysis_runs, agent_settings) |
| 002 | Поля для Telegram-джерел (telegram_id, telegram_title, telegram_username; url nullable) |
| 003 | Виправлення назв моделей за замовчуванням під локальні аліаси LiteLLM |

## Конфігурація

Всі налаштування — змінні середовища (Pydantic `BaseSettings`):

| Змінна | За замовчуванням | Опис |
|---|---|---|
| `DATABASE_URL` | `postgresql://ti_analyst:ti_analyst@postgres:5432/ti_analyst` | Підключення PostgreSQL |
| `LITELLM_BASE_URL` | `http://litellm:4000` | URL проксі LiteLLM |
| `TRIAGE_MODEL` | `free` | Аліас моделі для вузла Ingestor |
| `ANALYST_MODEL` | `cheap` | Аліас моделі для вузлів Analyst/Publisher |
| `INFRA_MODEL` | `free` | Аліас моделі для вузла InfraGuard |
| `TELEGRAM_BOT_TOKEN` | — | Токен бота для резолвення каналів і сповіщень |
| `TELEGRAM_ALERT_CHAT_ID` | — | Chat ID для надсилання сповіщень про загрози |
| `OPENCLAW_ENABLED` | `false` | Увімкнути інтеграцію з OpenClaw для глибокого дослідження |
| `INGESTION_CRON` | `0 */1 * * *` | Cron-вираз для планової інгестії |
| `OPENSEARCH_URL` | `http://opensearch:9200` | Адреса OpenSearch |

## Спостережуваність

- Структуровані логи в індекс OpenSearch `ti-analyst-logs` через `OpenSearchHandler`
- `X-Trace-Id` / `X-Request-Id` на всіх запитах
- LLM-виклики логують: назву моделі, тривалість (мс), кількість токенів
- Записи `AnalysisRun` відстежують запуски пайплайну з часом старту/завершення і лічильниками
