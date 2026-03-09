# AI Agent Specification: Sentinel-AI

## 1. Об’єкт стану (State Management)

Для роботи в **LangGraph** ми визначаємо `AgentState`, який зберігає контекст протягом усього життєвого циклу обробки загрози.

```python
from typing import TypedDict, List, Dict, Optional

class AgentState(TypedDict):
    raw_content: str               # Вхідний текст (пост, стаття, лог)
    metadata: Dict                 # Джерело, дата, автор
    threat_profile: Dict           # CVE, тип загрози, критичність
    research_data: Optional[Dict]  # Результати від OpenClaw
    affected_assets: List[Dict]    # Збіги з нашою інфраструктурою
    reports: Dict[str, str]        # Згенеровані звіти (Ops/Exec)
    model_config: Dict             # Обрані моделі для кожного етапу
    status: str                    # Поточний статус (triage, research, correlation, reporting)

```

---

## 2. Специфікація вузлів (Node Definition)

### A. Вузол "Ingestor" (The Watcher)

* **Мета:** Нормалізація неструктурованих даних.
* **LLM Поведінка:** Виділення ключової інформації з шумного тексту.
* **Модель:** Легка (напр., GPT-4o-mini або Llama 3.1 8B via LiteLLM).
* **Prompt:** *"Ти — OSINT-аналітик. Очисти вхідний текст від реклами. Якщо текст містить опис вразливості, оновлення ПЗ або мережеву атаку — структуруй його в JSON. Якщо це сміття — поверни 'ignore'."*

### B. Вузол "Analyst" (The Brain)

* **Мета:** Глибокий аналіз та дедуплікація.
* **LLM Поведінка:** Пошук закономірностей через RAG.
* **Модель:** Потужна (напр., Claude 3.5 Sonnet або GPT-4o via OpenRouter).
* **Tools:** `opensearch_vector_search` (пошук схожих загроз у минулому).

### C. Вузол "ClawBridge" (The Researcher)

* **Мета:** Делегування автономного дослідження.
* **Логіка:** Якщо рівень впевненості `Analyst` низький або загроза нова (0-day) — звертаємося до **OpenClaw**.
* **Integration:** Виклик зовнішнього агента OpenClaw через асинхронний Tool.

### D. Вузол "InfraGuard" (The Auditor)

* **Мета:** Кореляція з активами.
* **Конфіденційність:** **Обов'язкове використання локальної моделі** (напр., Mistral Nemo через LiteLLM/Ollama) для роботи з внутрішньою базою активів.
* **Tools:** `inventory_lookup` (запит до OpenSearch індексу `inventory`).

### E. Вузол "Publisher" (The Journalist)

* **Мета:** Фіналізація.
* **LLM Поведінка:** Адаптація тону під аудиторію.
* **Output:** Два документи: технічний (Markdown) та управлінський (Summary).

---

## 3. Схема логічних переходів (Graph Topology)

1. **START** -> `Ingestor`
2. `Ingestor` -> `Analyst` (якщо не 'ignore')
3. **Conditional Edge** (Decision):
* *Якщо загроза потребує глибокого аналізу* -> `ClawBridge` -> (повернення в) `Analyst`.
* *Якщо дані достатні* -> `InfraGuard`.


4. `InfraGuard` -> `Publisher`.
5. `Publisher` -> **END** (відправка в Telegram API).

---

## 4. Специфікація інструментів (Tools)

Кожен інструмент реалізується як Python-функція з декоратором `@tool` від LangChain.

| Tool Name | Input Parameters | Description |
| --- | --- | --- |
| `dispatch_openclaw` | `task_description`, `depth` | Ініціалізує автономне дослідження в OpenClaw. |
| `query_assets` | `vendor`, `model`, `version` | Шукає збіги в OpenSearch. Використовує семантичний пошук для версій ПЗ. |
| `litellm_router` | `prompt`, `model_alias` | Уніфікована обгортка для перемикання між OpenRouter та локальним сервером. |
| `guardrails_check` | `text`, `rules` | Валідація на відсутність конфіденційних даних у публічних звітах. |

---

## 5. Конфігурація LiteLLM & OpenRouter

Система використовує `litellm` для управління різноманітними провайдерами.

**Приклад конфігурації (yaml):**

```yaml
model_list:
  - model_name: high-reasoning
    litellm_params:
      model: openrouter/anthropic/claude-3.5-sonnet
      api_key: os.environ/OPENROUTER_API_KEY
  - model_name: privacy-local
    litellm_params:
      model: ollama/llama3.1:8b
      api_base: http://localhost:11434

```

---

## 6. Механізм зворотного зв'язку (Self-Correction)

Завдяки **LangGraph**, ми впроваджуємо "цикл роздумів": якщо `InfraGuard` знаходить критичний збіг, але `Analyst` надав недостатньо деталей для виправлення, система може автоматично повернути стан на вузол `Analyst` з вимогою "Уточнити методи мітигації для даної версії ОС".

