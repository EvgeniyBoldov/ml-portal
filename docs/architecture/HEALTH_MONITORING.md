# Health Monitoring System

Система периодической диагностики компонентов платформы: MCP-коннекторов, моделей (embedding/rerank/LLM) и discovery инструментов. Результаты хранятся в PostgreSQL и экспортируются в Prometheus.

## Архитектура

```
Celery Beat (schedule)
       │
       ├── probe_mcp_connectors    (every 1m)
       ├── probe_embedding_models  (every 1m)
       ├── probe_rerank_models     (every 1m)
       ├── probe_llm_models        (every 10m)
       └── rescan_discovery        (every 10m)
              │
              ▼
       HealthCheckEngine
              │
              ├── MCPHealthAdapter      → mcp_initialize() RPC call
              ├── EmbeddingHealthAdapter → embed_text("health check")
              ├── RerankHealthAdapter   → GET {endpoint}/health
              └── LLMHealthAdapter      → GET {endpoint}/health
              │
              ▼
       PostgreSQL
       tool_instances.health_status / consecutive_failures / next_check_at / last_error
       models.health_status / consecutive_failures / next_check_at / last_error
              │
              ▼
       GET /api/v1/monitoring/metrics  (Prometheus exposition format)
       GET /api/v1/monitoring/health
       GET /api/v1/monitoring/health/detailed
```

## Компоненты

### `services/health/base.py`
Базовые контракты:
- **`HealthStatus`** — enum: `healthy | unhealthy | unknown`
- **`HealthProbeResult`** — результат пробы: `status`, `latency_ms`, `error`, `details`
- **`HealthCheckAdapter`** — Protocol с методом `async probe(target) → HealthProbeResult`
- **`BackoffPolicy`** — алгоритм расчёта следующей проверки с экспоненциальным backoff

### `services/health/engine.py`
**`HealthCheckEngine`** — оркестратор, использует зарегистрированные адаптеры:
- `check_tool_instances(connector_type, limit)` — проверяет экземпляры, у которых `next_check_at <= now`
- `check_models(model_type, limit)` — проверяет модели со статусом `AVAILABLE`
- После каждой пробы обновляет поля в БД и пересчитывает `next_check_at`

Утилиты для runtime push (когда ошибка случается не по расписанию, а во время выполнения):
- `mark_instance_unhealthy(session, instance_id, error)` — немедленно помечает unhealthy, `next_check_at = now + 1m`
- `mark_model_unhealthy(session, model_id, error)` — аналогично для модели

### `services/health/adapters.py`

| Адаптер | Тип цели | Метод проверки | Timeout |
|---|---|---|---|
| `MCPHealthAdapter` | `ToolInstance` (connector_type=mcp) | MCP `initialize` RPC | 10s |
| `EmbeddingHealthAdapter` | `Model` (type=embedding) | `embed_text("health check")` | — |
| `RerankHealthAdapter` | `Model` (type=rerank) | `GET {endpoint}/health` | 10s |
| `LLMHealthAdapter` | `Model` (type=llm) | `GET {endpoint}/health` | 10s |

### `services/health/metrics.py`
**`MetricsCollector`** — собирает агрегированные метрики из БД и генерирует Prometheus-формат.

## Backoff Policy

Две преднастроенные политики (`BACKOFF_POLICY_1M`, `BACKOFF_POLICY_10M`):

| Политика | Base interval | Max interval | Failure threshold |
|---|---|---|---|
| `BACKOFF_POLICY_1M` | 1 мин | 5 мин | 10 подряд |
| `BACKOFF_POLICY_10M` | 10 мин | 30 мин | 3 подряд |

Алгоритм:
1. При `healthy` — следующая проверка через `base_interval`
2. При `unhealthy`, пока `consecutive_failures < threshold` — тот же `base_interval`
3. После превышения threshold — экспоненциальный backoff: `base * 2^(failures - threshold)`, не больше `max_interval`
4. К результату добавляется случайный jitter ±25% для предотвращения thundering herd

## Периодичность задач

| Задача | Расписание | Очередь | Политика |
|---|---|---|---|
| `probe_mcp_connectors` | каждую 1 мин | `health` | `BACKOFF_POLICY_1M` |
| `probe_embedding_models` | каждую 1 мин | `health` | `BACKOFF_POLICY_1M` |
| `probe_rerank_models` | каждую 1 мин | `health` | `BACKOFF_POLICY_1M` |
| `probe_llm_models` | каждые 10 мин | `health` | `BACKOFF_POLICY_10M` |
| `rescan_discovery` | каждые 10 мин | `health` | — |

Beat-расписание активируется при `BEAT=1` в env (см. `celery_app.py`).

## Distributed Lock

Каждая задача использует **Postgres advisory lock** (`pg_try_advisory_lock`) перед запуском. Если другой воркер уже держит блокировку — задача возвращает `{"status": "skipped", "reason": "locked"}`. Это предотвращает дублирующиеся проверки при нескольких репликах воркера.

## Health Transitions для MCP

При смене `health_status` у MCP-коннектора выполняются side-эффекты:
- **`healthy → unhealthy`**: все `discovered_tools` этого провайдера помечаются `is_active=False`
- **`unhealthy → healthy`**: у инстанса выставляется `next_check_at = now`, что немедленно запускает discovery rescan в следующем цикле `rescan_discovery`

## DB Schema (migration 0018)

Поля добавлены в таблицы `tool_instances` и `models`:

| Колонка | Тип | Описание |
|---|---|---|
| `health_status` | существующее поле | `healthy / unhealthy / unknown` |
| `consecutive_failures` | `integer DEFAULT 0` | Счётчик подряд идущих неудач |
| `next_check_at` | `timestamptz` | Когда делать следующую проверку |
| `last_error` | `text` | Последнее сообщение об ошибке |

Индексы: `ix_tool_instances_next_check_at`, `ix_models_next_check_at` для эффективной выборки кандидатов.

## API Endpoints

### `GET /api/v1/monitoring/metrics`
Метрики в Prometheus exposition format. Выполняет свежий `collect_all()` при каждом запросе.

```
# HELP ml_portal_connectors_total Total number of MCP connectors
# TYPE ml_portal_connectors_total gauge
ml_portal_connectors_total 3.0

# HELP ml_portal_connectors_healthy Number of healthy MCP connectors
ml_portal_connectors_healthy 2.0

# HELP ml_portal_models_healthy Number of healthy models
ml_portal_models_healthy 4.0

# HELP ml_portal_discovered_tools_active Number of active discovered tools
ml_portal_discovered_tools_active 17.0

# HELP ml_portal_documents_by_status Number of documents by status
ml_portal_documents_by_status{status="done"} 142.0
ml_portal_documents_by_status{status="pending"} 3.0
```

Полный список метрик:

| Метрика | Тип | Описание |
|---|---|---|
| `ml_portal_connectors_total` | gauge | Всего MCP-коннекторов |
| `ml_portal_connectors_healthy` | gauge | Здоровых |
| `ml_portal_connectors_unhealthy` | gauge | Нездоровых |
| `ml_portal_models_total` | gauge | Всего моделей (status=AVAILABLE) |
| `ml_portal_models_healthy` | gauge | Здоровых |
| `ml_portal_models_unhealthy` | gauge | Нездоровых |
| `ml_portal_discovered_tools_total` | gauge | Всего найденных инструментов |
| `ml_portal_discovered_tools_active` | gauge | Активных |
| `ml_portal_collections_total` | gauge | Всего коллекций |
| `ml_portal_documents_total` | gauge | Всего документов |
| `ml_portal_documents_by_status` | gauge | Документы по статусам (multi-label) |

### `GET /api/v1/monitoring/health`
Простой liveness probe для load balancer. Не обращается к БД.

```json
{"status": "healthy", "service": "ml-portal-api"}
```

### `GET /api/v1/monitoring/health/detailed`
Readiness probe с актуальными счётчиками из БД.

```json
{
  "status": "healthy",
  "service": "ml-portal-api",
  "metrics": {
    "connectors": {"total": 3, "healthy": 2, "unhealthy": 1},
    "models": {"total": 5, "healthy": 4, "unhealthy": 1},
    "discovery": {"total_tools": 22, "active_tools": 17}
  }
}
```

## Файловая структура

```
apps/api/src/app/
├── services/health/
│   ├── __init__.py        — публичный API модуля
│   ├── base.py            — HealthStatus, HealthProbeResult, BackoffPolicy, HealthCheckAdapter
│   ├── engine.py          — HealthCheckEngine, mark_instance_unhealthy, mark_model_unhealthy
│   ├── adapters.py        — MCPHealthAdapter, EmbeddingHealthAdapter, RerankHealthAdapter, LLMHealthAdapter
│   ├── metrics.py         — MetricsCollector (Prometheus)
│   └── tests/
│       ├── test_adapters.py
│       └── test_engine.py
├── workers/
│   └── tasks_health.py    — Celery задачи (probe_*, rescan_discovery)
└── api/v1/routers/
    └── monitoring.py      — /monitoring/metrics, /monitoring/health[/detailed]
```
