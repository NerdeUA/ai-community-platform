# Dev Reporter Agent

## Призначення
Dev Reporter Agent отримує результати виконання пайплайну через A2A, зберігає їх у PostgreSQL та надсилає Telegram-сповіщення через бота OpenClaw. Надає адмін-панель для перегляду історії запусків пайплайну з фільтрацією за статусом.

## Функціонал
- `POST /api/v1/a2a` — A2A-ендпоінт, що приймає 3 скіли
- `GET /health` — стандартний health-check (`{"status": "ok", "service": "dev-reporter-agent"}`)
- `GET /api/v1/manifest` — Agent Card відповідно до платформних конвенцій
- `GET /admin/pipeline` — адмін-панель з історією запусків пайплайну та фільтром за статусом

## Скіли

| Skill ID | Опис | Ключові вхідні дані |
|---|---|---|
| `devreporter.ingest` | Зберегти результат запуску пайплайну в БД та надіслати Telegram-сповіщення | `task`, `status`, `branch`, `pipeline_id`, `duration_seconds`, `agent_results` |
| `devreporter.status` | Запитати останні запуски пайплайну та агреговану статистику | `limit`, `days`, `status_filter` |
| `devreporter.notify` | Надіслати довільне повідомлення через Core A2A → OpenClaw Telegram | `message` |

### Payload для `devreporter.ingest`

```json
{
  "intent": "devreporter.ingest",
  "payload": {
    "pipeline_id": "20260308_120000",
    "task": "Add streaming support",
    "branch": "pipeline/add-streaming",
    "status": "completed",
    "duration_seconds": 2700,
    "failed_agent": null,
    "agent_results": [
      { "agent": "Coder", "status": "pass", "duration": 900 },
      { "agent": "Validator", "status": "pass", "duration": 600 }
    ],
    "report_content": "Опціональний повний текст звіту"
  }
}
```

`status` має бути `"completed"` або `"failed"`. `task` — обов'язкове поле.

### Відповідь `devreporter.status`

```json
{
  "status": "completed",
  "result": {
    "runs": [...],
    "stats": {
      "total": 42,
      "passed": 38,
      "failed": 4,
      "pass_rate": 90.5,
      "avg_duration": 1800.0
    }
  }
}
```

## База даних

Таблиця: `pipeline_runs`

| Колонка | Тип | Примітки |
|---|---|---|
| `id` | SERIAL PK | Автоінкремент |
| `pipeline_id` | VARCHAR(100) | Ідентифікатор запуску пайплайну |
| `task` | TEXT | Опис завдання |
| `branch` | VARCHAR(255) | Git-гілка |
| `status` | VARCHAR(20) | `completed` або `failed` |
| `failed_agent` | VARCHAR(100) | Nullable — який агент впав |
| `duration_seconds` | INTEGER | Загальна тривалість пайплайну |
| `agent_results` | JSONB | Масив результатів по агентах |
| `report_content` | TEXT | Опціональний повний звіт |
| `created_at` | TIMESTAMPTZ | Встановлюється автоматично при вставці |

Індекси: `idx_pipeline_runs_status`, `idx_pipeline_runs_created_at`

## Технічний стек
- PHP 8.5 + Symfony 7
- Doctrine DBAL 4 (PostgreSQL)
- Apache (Docker)
- Traefik routing на порті **8087**

## Telegram-сповіщення
При `devreporter.ingest` агент формує повідомлення та відправляє його на A2A-ендпоінт Core (`openclaw.send_message`). Це best-effort, неблокуюча операція — якщо Core недоступний, логується попередження, а ingest все одно завершується успішно.

## Makefile команди
- `make dev-reporter-setup` — збірка контейнера та встановлення залежностей
- `make dev-reporter-install` — встановлення PHP залежностей
- `make dev-reporter-migrate` — запуск Doctrine міграцій
- `make dev-reporter-test` — запуск Codeception тестів
- `make dev-reporter-analyse` — PHPStan аналіз (рівень 8)
- `make dev-reporter-cs-check` / `make dev-reporter-cs-fix` — перевірка/фікс стилю коду

## Адмін-панель
Доступна за адресою `http://localhost:8087/admin/pipeline` (або через Traefik на налаштованому admin entrypoint).

Відображає:
- Рядок статистики: всього запусків, пройшли, впали, відсоток успіху, середня тривалість (за останні 7 днів)
- Таблиця з фільтрацією: Всі / Пройшли / Впали
- По рядку: дата, завдання, гілка, бейдж статусу, тривалість, кількість агентів
