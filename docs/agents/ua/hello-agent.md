# Hello Agent

## Призначення
Hello Agent — мінімальний референсний агент, що демонструє повний цикл життя агента на платформі: клієнтський webview, конвенції Agent Card та health-ендпоінту, адмін-конфіг.

## Функціонал
- Webview на `/` — відображає текст привітання (за замовчуванням "Hello, World!")
- `GET /health` — стандартний health-check (`{"status": "ok"}`)
- `GET /api/v1/manifest` — Agent Card відповідно до платформних конвенцій
- Конфігурація через адмінку: поля `description` та `system_prompt`

## Технічний стек
- PHP 8.5 + Symfony 7
- Apache (Docker)
- Traefik routing на порті 8085

## Конфігурація
Адміністратор може налаштувати через сторінку `/admin/agents`:
- **Опис** (`description`) — текст, що відображається на головному екрані
- **Системний промт** (`system_prompt`) — базовий промт для агента

Конфігурація зберігається в таблиці `agent_registry` колонка `config` (JSONB).

## Makefile команди
- `make hello-setup` — збірка та встановлення залежностей
- `make hello-install` — встановлення PHP залежностей
- `make hello-test` — запуск Codeception тестів
- `make hello-analyse` — PHPStan аналіз
- `make hello-cs-check` / `make hello-cs-fix` — перевірка/фікс стилю коду
