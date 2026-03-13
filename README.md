# AI Community Platform - Threat Analysis Agent

Модульна платформа AI-агентів на основі PHP/Symfony-ядра та Python FastAPI-агентів. Кожен агент працює як окремий Docker-сервіс за Traefik, взаємодіє через протокол A2A (Agent-to-Agent) та використовує спільну інфраструктуру PostgreSQL + OpenSearch + LiteLLM.

---

## Зміст

- [Структура репозиторію](#структура-репозиторію)
- [Інфраструктура](#інфраструктура)
- [Швидкий старт](#швидкий-старт)
- [Агент TI Analyst](#агент-ti-analyst)
  - [Що він робить](#що-він-робить)
  - [Архітектура пайплайну](#архітектура-пайплайну)
  - [Конфігурація](#конфігурація)
  - [Запуск агента](#запуск-агента)
  - [Міграції бази даних](#міграції-бази-даних)
  - [Адмін-панель](#адмін-панель)
  - [REST API](#rest-api)
  - [Інтеграція з Telegram](#інтеграція-з-telegram)
  - [LLM-моделі](#llm-моделі)
  - [Індекси OpenSearch](#індекси-opensearch)
- [Інші агенти](#інші-агенти)
- [Нотатки для розробників](#нотатки-для-розробників)

---

## Структура репозиторію

```
ai-community-platform/
├── apps/
│   ├── ti-analyst/          # Sentinel-AI CTI агент (Python / FastAPI)
│   ├── core/                # Ядро платформи (PHP / Symfony)
│   ├── news-maker-agent/    # Агент підбору новин (Python / FastAPI)
│   ├── knowledge-agent/     # Агент бази знань (PHP / Symfony)
│   ├── hello-agent/         # Демо-агент (PHP / Symfony)
│   └── dev-reporter-agent/  # Агент спостережності (PHP / Symfony)
├── docker/
│   ├── ti-analyst/          # Dockerfile + entrypoint.sh
│   ├── traefik/             # traefik.yml
│   ├── litellm/             # config.yaml (маршрутизація моделей)
│   └── postgres/init/       # Скрипти ініціалізації БД для кожного агента
├── compose.yaml                    # Базова інфраструктура (Traefik, Postgres, OpenSearch, Redis, LiteLLM)
├── compose.agent-ti-analyst.yaml   # Overlay для TI Analyst
├── compose.core.yaml               # Overlay для ядра платформи
├── compose.langfuse.yaml           # Overlay для Langfuse (трасування LLM)
└── compose.openclaw.yaml           # Overlay для OpenClaw (глибокий аналіз загроз)
```

---

## Інфраструктура

| Сервіс        | Образ                              | Порт   | Призначення                        |
|---------------|------------------------------------|--------|------------------------------------|
| Traefik       | traefik:v3.3                       | 80, 8080 | Реверс-проксі + edge-auth        |
| PostgreSQL    | postgres:16                        | 5432   | БД для всіх агентів                |
| OpenSearch    | opensearchproject/opensearch:2.11  | 9200   | Векторний/повнотекстовий пошук + логи |
| Redis         | redis:7                            | 6379   | Кеш / брокер                       |
| RabbitMQ      | rabbitmq:3-management              | 5672   | Черга повідомлень                  |
| LiteLLM       | ghcr.io/berriai/litellm            | 4000   | Проксі LLM + маршрутизація моделей |

### Порти Traefik (Entrypoints)

| Порт     | Агент              |
|----------|--------------------|
| 80       | Core (web)         |
| 8081     | Admin              |
| 8082     | OpenClaw           |
| 8083     | Knowledge Agent    |
| 8084     | News Maker Agent   |
| 8085     | Hello Agent        |
| 8086     | Langfuse           |
| 8087     | Dev Reporter       |
| **8088** | **TI Analyst**     |

---

## Швидкий старт

### 1. Вимоги

- Docker ≥ 24 з Compose v2
- 8 ГБ RAM (OpenSearch потребує ~2 ГБ)

### 2. Налаштування секретів

```bash
make bootstrap
```

Скрипт читає `.env.local` і генерує необхідні секрети для всіх сервісів. Запускається один раз перед першим стартом.

### 3. Збірка образів та встановлення залежностей

```bash
make setup
```

Завантажує інфраструктурні образи, збирає Docker-образи всіх агентів та встановлює залежності (Composer / pip).

### 4. Запуск всього стеку

```bash
make up
```

### 5. (Опційно) Запуск Langfuse для трасування LLM

```bash
make up-observability
```

### 6. Перевірка роботи

```bash
make ps
curl http://localhost:8088/health
# → {"status":"ok","service":"ti-analyst"}
```

---

## Агент TI Analyst

### Що він робить

TI Analyst — агент кіберрозвідки (CTI), який:

1. **Опитує** RSS-стрічки, Telegram-канали, URL та Reddit за розкладом або вручну
2. **Попередньо фільтрує** контент через дешевий LLM-виклик (батчами по 25 елементів), відкидаючи нерелевантний контент перед запуском повного пайплайну
3. **Аналізує** загрози через багатоступеневий LangGraph-пайплайн: структурована екстракція → глибокий аналіз → кореляція з активами
4. **Публікує** Операційний звіт та Резюме для керівництва (українською мовою) лише для загроз, які стосуються ваших активів
5. **Сповіщає** через Telegram-бот про загрози рівня high/critical, які відповідають вашому реєстру активів
6. **Дедуплікує** весь контент через SHA-256 хеш ще до звернення до LLM — кожен елемент обробляється щонайбільше один раз

---

### Архітектура пайплайну

```
                    ┌───────────────────────────────────────────────────────────────┐
                    │                      LangGraph Pipeline                        │
                    │                                                               │
  Вхідний ──────► Ingestor ──► Analyst ──► InfraGuard ──► Publisher ──► Звіти     │
  контент      (ігнорувати?)           (немає активів?)                             │
                    │    └──► END             └──────────────────────► END          │
                    │               (openclaw_enabled=true?)                        │
                    │            Analyst ──► ClawBridge ──► Analyst                │
                    └───────────────────────────────────────────────────────────────┘
```

| Вузол           | Опис                                                                                 |
|-----------------|--------------------------------------------------------------------------------------|
| **Ingestor**    | Нормалізує сирий текст; витягує `title`, `threat_type`, `cve_ids`, `severity`, `affected_vendors`. Нерелевантний контент позначається як `ignored`. |
| **Analyst**     | Глибокий аналіз: `attack_vectors`, `detection_strategies`, `mitigation_steps`. Виконує пошук дублікатів в OpenSearch. |
| **ClawBridge**  | *(Опційно)* Делегує завдання OpenClaw для пошуку PoC-експлойтів, рекомендацій вендорів та патчів. Активується коли `OPENCLAW_ENABLED=true` та загроза потребує глибокого дослідження. |
| **InfraGuard**  | Зіставляє вендорів загрози з реєстром активів через повнотекстовий пошук OpenSearch. Визначає `exposure`, `overall_risk` та `remediation_priority`. |
| **Publisher**   | Генерує Операційний звіт (≤ 800 слів) та Резюме для керівництва (≤ 230 слів). Запускається лише коли є хоча б один відповідний актив. |

**Пакетна попередня фільтрація** — перед повним LangGraph-пайплайном елементи групуються по 25 і фільтруються одним дешевим LLM-викликом. Лише релевантні з точки зору безпеки елементи продовжують обробку, що економить 80–90% LLM-викликів для загальних RSS-стрічок.

---

### Конфігурація

Усі налаштування зчитуються зі змінних середовища або файлу `.env`.

#### Обов'язкові

| Змінна               | Опис                                                        |
|----------------------|-------------------------------------------------------------|
| `LITELLM_API_KEY`    | API-ключ для LiteLLM-проксі (задається у `compose.yaml`)   |
| `APP_INTERNAL_TOKEN` | Спільний секрет для внутрішніх міжсервісних запитів         |

#### База даних та інфраструктура

| Змінна             | За замовчуванням                                              | Опис                     |
|--------------------|---------------------------------------------------------------|--------------------------|
| `DATABASE_URL`     | `postgresql://ti_analyst:ti_analyst@postgres:5432/ti_analyst` | DSN PostgreSQL           |
| `OPENSEARCH_URL`   | `http://opensearch:9200`                                      | Адреса OpenSearch        |
| `LITELLM_BASE_URL` | `http://litellm:4000`                                         | Базова URL LiteLLM-проксі|
| `PLATFORM_CORE_URL`| `http://core`                                                 | Базова URL ядра платформи|

#### LLM-моделі

| Змінна          | За замовч. | Опис                                         |
|-----------------|------------|----------------------------------------------|
| `TRIAGE_MODEL`  | `cheap`    | Модель для тріажу та попередньої фільтрації  |
| `ANALYST_MODEL` | `cheap`    | Модель для аналізу та генерації звітів       |
| `INFRA_MODEL`   | `cheap`    | Модель для кореляції з інфраструктурою       |

Псевдоніми моделей визначаються у `docker/litellm/config.yaml`:

| Псевдонім | Модель(і)                                       |
|-----------|-------------------------------------------------|
| `cheap`   | minimax/minimax-m2.5                            |
| `free`    | llama-3.3-70b, mistral-small (Venice API)       |

Для використання інших моделей відредагуйте `docker/litellm/config.yaml` або перевизначте змінні `_MODEL`.

#### Розклад опитування

| Змінна            | За замовч.       | Опис                                  |
|-------------------|------------------|---------------------------------------|
| `INGESTION_CRON`  | `0 */1 * * *`    | Cron-вираз для автоматичного опитування |

Розклад також можна змінити в реальному часі через **Admin → Settings** без перезапуску агента.

#### Telegram (опційно)

| Змінна                      | Опис                                                         |
|-----------------------------|--------------------------------------------------------------|
| `TELEGRAM_BOT_TOKEN`        | Токен бота від [@BotFather](https://t.me/BotFather)         |
| `TELEGRAM_ALERT_CHAT_ID`    | ID чату/каналу для сповіщень про критичні загрози            |
| `TELEGRAM_BOT_ALLOWED_IDS`  | Список ID користувачів через кому, яким дозволено використовувати бота |
| `TELEGRAM_API_ID`           | API ID додатку з [my.telegram.org](https://my.telegram.org) — потрібен для читання каналів через MTProto |
| `TELEGRAM_API_HASH`         | API Hash додатку з [my.telegram.org](https://my.telegram.org) — потрібен для читання каналів через MTProto |

#### Розширені / опційні налаштування

| Змінна                  | За замовч.                          | Опис                                          |
|-------------------------|-------------------------------------|-----------------------------------------------|
| `OPENCLAW_URL`          | `http://openclaw:8000`              | URL сервісу OpenClaw для глибокого аналізу    |
| `OPENCLAW_ENABLED`      | `false`                             | Увімкнути вузол ClawBridge у пайплайні        |
| `ADMIN_PUBLIC_URL`      | `http://localhost:8088/admin/sources` | URL, який відображається у повідомленнях бота|
| `MIGRATE_ON_START`      | `1`                                 | Автоматично запускати міграції Alembic        |
| `ENABLE_TEST_ENDPOINTS` | `false`                             | Увімкнути `/web/trigger-ingestion` без авторизації |

#### Приклад `.env.local` (секція TI Analyst)

```dotenv
# Обов'язкові
LITELLM_API_KEY=sk-your-litellm-key
APP_INTERNAL_TOKEN=змініть-у-продакшн

# Telegram сповіщення (опційно)
TELEGRAM_BOT_TOKEN=123456:AAAA...
TELEGRAM_ALERT_CHAT_ID=-1001234567890
TELEGRAM_BOT_ALLOWED_IDS=100000001,100000002

# Увімкнути глибокий аналіз OpenClaw (опційно)
OPENCLAW_ENABLED=true
```

---

### Запуск агента

```bash
# Запустити або перезібрати лише TI Analyst (без зупинки решти стеку)
make agent-up name=ti-analyst-agent

# Зупинити агент
make agent-down name=ti-analyst-agent

# Запустити весь стек (усі агенти + інфраструктура)
make up

# Зупинити весь стек
make down

# Переглянути запущені сервіси
make ps

# Слідкувати за логами всіх сервісів
make logs

# Перевірка стану
curl http://localhost:8088/health
```

---

### Міграції бази даних

Міграції запускаються автоматично при старті, якщо `MIGRATE_ON_START=1` (за замовчуванням).

Для ручного запуску:

```bash
make ti-analyst-migrate
```

Історія міграцій:

| Ревізія | Опис                                                       |
|---------|------------------------------------------------------------|
| 001     | Початкова схема (sources, assets, threat_intel, runs, settings) |
| 002     | Поля для Telegram-джерел                                   |
| 003     | Назви LLM-моделей за замовчуванням                         |
| 004     | ID чату для Telegram-сповіщень                             |
| 005     | Список дозволених користувачів Telegram-бота               |
| 006     | Промпти українською мовою                                  |
| 007     | Відстеження останнього повідомлення Telegram (дедуплікація)|

---

### Адмін-панель

Адмін-панель доступна за адресою **`http://localhost:8088`**.

> У продакшн-середовищі всі маршрути `/admin/*` захищені middleware `edge-auth` у Traefik.

#### Джерела — `/admin/sources`

Управління джерелами розвідки. Підтримувані типи:

| Тип        | Опис                                                           |
|------------|----------------------------------------------------------------|
| `rss`      | RSS / Atom стрічка — потрібна URL-адреса, автоматично перевіряється при додаванні |
| `telegram` | Telegram-канал — розпізнається через Bot HTTP API              |
| `url`      | Будь-яка веб-сторінка                                          |
| `reddit`   | Reddit-стрічка (сумісний формат RSS)                           |

**Додавання RSS-джерела:**
1. Обрати тип `rss`, вставити URL стрічки
2. Натиснути **Verify Feed** — система отримує метадані та автоматично заповнює поле Name
3. Натиснути **Confirm & Add**

**Додавання Telegram-джерела:**
1. Обрати тип `telegram`, ввести username каналу (`@channel`), повну URL (`https://t.me/channel`) або числовий ID
2. Натиснути **Resolve Channel** — метадані завантажуються через Bot API
3. Натиснути **Confirm & Add**

**Імпорт / Експорт:**
- **↓ Export JSON** — завантажує всі налаштовані джерела у файл `ti-analyst-sources-YYYYMMDD.json`
- **↑ Import JSON** — завантажує раніше експортований файл; дублікати (за URL або Telegram ID) пропускаються автоматично

Формат файлу експорту:
```json
[
  {
    "name": "NVD CVE Feed",
    "source_type": "rss",
    "url": "https://nvd.nist.gov/feeds/xml/cve/misc/nvd-rss.xml",
    "poll_interval_minutes": 60,
    "enabled": true
  },
  {
    "name": "CyberSecUA",
    "source_type": "telegram",
    "telegram_id": -1001234567890,
    "telegram_username": "cybersecua",
    "telegram_title": "CyberSec Ukraine",
    "poll_interval_minutes": 30,
    "enabled": true
  }
]
```

#### Активи — `/admin/assets`

Управління реєстром активів інфраструктури. Активи зіставляються із загрозами на етапі InfraGuard.

Поля: **Назва**, **Вендор**, **Модель**, **Версія ПЗ**, **Критичність** (low / medium / high / critical), **Теги**, **Примітки**.

Активи синхронізуються з OpenSearch при запуску та після кожного збереження — для зіставлення у реальному часі.

#### Налаштування — `/admin/settings`

Зміни застосовуються без перезапуску агента:

- **LLM-моделі** — перевизначити `triage_model`, `analyst_model`, `infra_model` для поточного екземпляра
- **Власні промпти** — редагувати промпти для ingestor, analyst, infra-guard та publisher
- **Розклад опитування** — змінити cron-вираз (застосовується миттєво до запущеного планувальника)
- **Функціональні прапори** — увімкнути/вимкнути інтеграцію OpenClaw

#### Дашборд — `/`

Перегляд кіберрозвідки в реальному часі:

- **Статистичні картки** — кількість Critical / High загроз (клікабельні — фільтрують таблицю за рівнем)
- **Перемикач періоду** — Сьогодні / 24 год / 7 днів / 30 днів
- **Рядок пошуку** — одночасна фільтрація за Title, Severity, Type, Vendor, CVE
- **Таблиця загроз** — з пагінацією; клік по рядку відкриває повну картку загрози зі звітами
- **Модальне вікно загрози** — Резюме для керівництва + Операційний звіт; перемикач Raw / Preview; генерація звітів на вимогу

---

### REST API

Базова URL: `http://localhost:8088`

#### Стан сервісу

```
GET /health
→ {"status": "ok", "service": "ti-analyst"}
```

#### Аналіз загрози

```
POST /api/v1/analyze
Content-Type: application/json

{
  "content": "CVE-2025-1234 впливає на Windows 10...",
  "source_url": "https://example.com/advisory",
  "source_name": "Example Advisory"
}

→ {
    "status": "reported",
    "threat_id": "uuid",
    "severity": "high",
    "title": "CVE-2025-1234 Windows Privilege Escalation",
    "affected_assets": 3
  }
```

#### Список загроз

```
GET /api/v1/threats?severity=critical
→ [{"id": "...", "title": "...", "severity": "critical", ...}, ...]
```

#### Деталі загрози

```
GET /api/v1/threats/{threat_id}
→ {повний об'єкт загрози з ops_report та exec_report}
```

#### Генерація звітів на вимогу

```
POST /api/v1/threats/{threat_id}/generate-reports
→ {"ops_report": "...", "exec_report": "..."}
```

#### Маніфест агента (A2A)

```
GET /api/v1/manifest
```

Повертає метадані агента для реєстрації у платформі.

#### Між-агентні навички (A2A)

```
POST /api/v1/a2a
Content-Type: application/json
X-Internal-Token: <APP_INTERNAL_TOKEN>

{
  "skill": "ti.analyze",
  "params": {"content": "...", "source_name": "..."}
}
```

Доступні навички:

| Навичка        | Опис                                                 |
|----------------|------------------------------------------------------|
| `ti.analyze`   | Запустити повний LangGraph-пайплайн для контенту     |
| `ti.inventory` | Запит реєстру активів за вендором або ключовим словом|
| `ti.report`    | Отримати збережені звіти про загрози за ID або фільтром |

---

### Інтеграція з Telegram

Якщо задано `TELEGRAM_BOT_TOKEN`, агент запускає фоновий процес бота, який:

- **Надсилає сповіщення** на `TELEGRAM_ALERT_CHAT_ID` для кожної загрози рівня high/critical, яка відповідає хоча б одному активу
- **Відповідає на команди** від користувачів зі списку `TELEGRAM_BOT_ALLOWED_IDS` або налаштованих через Admin → Settings

Формат сповіщення:
```
🔴 [CRITICAL] CVE-2025-49760: Windows Storage Service LPE
CVEs: CVE-2025-49760
Affected assets: 4
```

**Команди бота** (лише для дозволених користувачів):

| Команда    | Опис                                   |
|------------|----------------------------------------|
| `/start`   | Показати довідку та поточний статус    |
| `/status`  | Статус пайплайну та інформація про останній запуск |
| `/threats` | Останні загрози рівня high/critical    |

**Підтримувані формати каналів** (при додаванні джерела):

| Формат                     | Приклад                            |
|----------------------------|------------------------------------|
| Username з @               | `@cybersecua`                      |
| Username без @             | `cybersecua`                       |
| t.me URL                   | `https://t.me/cybersecua`          |
| Числовий ID                | `-1001234567890`                   |

> Запрошувальні посилання (`t.me/+xxx`) **не підтримуються** через Bot API.

#### MTProto-сесія для читання Telegram-каналів

Агент підтримує два режими роботи з Telegram:

| Режим | Що потрібно | Для чого |
|-------|-------------|----------|
| **Bot API** | лише `TELEGRAM_BOT_TOKEN` | Сповіщення + розпізнавання каналів при додаванні джерела |
| **MTProto (Telethon)** | `TELEGRAM_API_ID` + `TELEGRAM_API_HASH` + активна сесія | Читання повідомлень із Telegram-каналів у пайплайні |

MTProto дозволяє читати повідомлення від імені звичайного акаунту (не бота), що необхідно для отримання контенту з каналів, де боти не є адміністраторами.

**Крок 1 — Отримати API-ключі**

1. Перейдіть на [my.telegram.org/auth](https://my.telegram.org/auth) та увійдіть у свій акаунт
2. Відкрийте розділ **API development tools**
3. Створіть новий додаток (назва та платформа — довільні)
4. Скопіюйте `App api_id` та `App api_hash`

**Крок 2 — Додати до `.env.local`**

```dotenv
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890
```

**Крок 3 — Створити сесію (один раз)**

Після запуску стеку (`make up`) виконайте інтерактивний логін:

```bash
docker compose exec ti-analyst-agent python3 -m app.services.telegram_login
```

Скрипт запитає номер телефону, код підтвердження та пароль 2FA (якщо увімкнено). Після успішного входу сесія зберігається у файл `/app/.telegram_session.session` всередині контейнера і більше не потребує повторного логіну.

**Перевірка сесії**

```bash
# Якщо команда не повертає помилку — сесія активна
docker compose exec ti-analyst-agent python3 -c "
from telethon.sync import TelegramClient
from app.config import settings
c = TelegramClient('/app/.telegram_session', settings.telegram_api_id, settings.telegram_api_hash)
c.connect()
print('Authorized:', c.is_user_authorized())
c.disconnect()
"
```

> **Важливо:** Сесія прив'язана до акаунту Telegram. Якщо акаунт завершить сеанс або буде заблоковано — потрібно повторити Крок 3. Для продакшн-середовища рекомендується використовувати окремий акаунт, а не особистий.

---

### LLM-моделі

Агент використовує LiteLLM як єдиний проксі для всіх LLM-викликів. Конфігурація моделей знаходиться у `docker/litellm/config.yaml`.

**LiteLLM UI**: `http://localhost:4000/ui/` — перегляд використання, витрат та логів.

**Трасування в Langfuse**: Усі LLM-виклики містять `request_id`, `trace_id` та теги фічі. Трасування доступні за адресою `http://localhost:8086/`.

**Таймаути та повторні спроби:**
- Таймаут одного виклику: 300 секунд
- `APITimeoutError`: без повторної спроби (швидка відмова)
- `RateLimitError` / `APIConnectionError`: 1 повторна спроба через 12 секунд
- `JSONDecodeError` (некоректна відповідь): 1 повторна спроба через 5 секунд

---

### Індекси OpenSearch

| Індекс                  | Призначення                                                 |
|-------------------------|-------------------------------------------------------------|
| `ti_analyst_assets`     | Реєстр активів для повнотекстового пошуку за вендором       |
| `ti_analyst_threats`    | Оброблені загрози для пошуку дублікатів за схожістю         |

Агент перевіряє наявність обох індексів при запуску. Дані активів синхронізуються з PostgreSQL в OpenSearch при старті та після кожного збереження/видалення.

---

## Інші агенти

| Агент                | Стек            | Порт | Опис                                        |
|----------------------|-----------------|------|---------------------------------------------|
| `core`               | PHP 8.5/Symfony | 80   | Ядро платформи, A2A-оркестратор, адмін-панель |
| `news-maker-agent`   | Python/FastAPI  | 8084 | Підбір новин + AI-рерайтинг                |
| `knowledge-agent`    | PHP/Symfony     | 8083 | Запити до бази знань                       |
| `hello-agent`        | PHP/Symfony     | 8085 | Демо / вітальний агент                     |
| `dev-reporter-agent` | PHP/Symfony     | 8087 | Спостережність пайплайну                   |

Кожен агент дотримується єдиного шаблону: власна база PostgreSQL, захищений Traefik entrypoint, маніфест-ендпоінт A2A за адресою `/api/v1/manifest`.

---

## Нотатки для розробників

### Логи

Усі логи надсилаються до OpenSearch (індекси `platform_logs_YYYY_MM_DD`) та у stdout.

```bash
# Слідкувати за логами всіх сервісів
make logs

# Пошук логів в OpenSearch
curl -s "http://localhost:9200/platform_logs_*/_search" \
  -H "Content-Type: application/json" \
  -d '{"query":{"match":{"source_app":"ti-analyst"}},"size":20,"sort":[{"@timestamp":"desc"}]}'
```

### Ручний запуск пайплайну (лише для розробки)

```bash
# З середини контейнера (без авторизації)
docker compose exec ti-analyst-agent curl -s -X POST http://localhost:8000/web/trigger-ingestion
```

### Запуск тестів

```bash
make ti-analyst-test
```

### Перевірка стилю коду

```bash
# Статичний аналіз (ruff check)
make ti-analyst-analyse

# Перевірка форматування
make ti-analyst-cs-check

# Автоматичне виправлення форматування
make ti-analyst-cs-fix
```

### Корисні запити до OpenSearch

```bash
# Кількість загроз за рівнем серйозності
curl -s "http://localhost:9200/ti_analyst_threats/_search" \
  -H "Content-Type: application/json" \
  -d '{"size":0,"aggs":{"by_sev":{"terms":{"field":"metadata.severity.keyword"}}}}'

# Список усіх записів активів
curl -s "http://localhost:9200/ti_analyst_assets/_search?size=50"
```
