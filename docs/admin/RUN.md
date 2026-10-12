# Run Guide

## 1. Dev запуск

```bash
make up
```

Стартует весь стек из `docker-compose.yml`.

## 2. Проверка состояния

```bash
make ps
make logs
```

Точечно:

```bash
docker compose logs --tail=200 api
docker compose logs --tail=200 worker
docker compose logs --tail=200 emb
docker compose logs --tail=200 rerank
```

## 3. Основные адреса (dev)

- API: `http://localhost:8000`
- API health: `http://localhost:8000/api/v1/healthz`
- Frontend (Vite): `http://localhost:5173`
- Nginx: `http://localhost:${NGINX_PORT_HTTP}`
- MinIO API: `http://localhost:9000`
- MinIO Console: `http://localhost:9001`
- Qdrant: `http://localhost:6333`
- Flower: `http://localhost:5555`
- HippoRAG worker (локальный HTTP): `http://localhost:8015/docs`

Постоянные dev-сервисы `hipporag` и `memory-experiment` запускаются из основного
compose. Индексы живут в отдельном volume, экспериментальные документы и SQLite —
в игнорируемой `.long-memory-experiment`. HippoRAG подключён к документной памяти
приложения; экспериментальный API остаётся отдельным. Команды и ограничения описаны в
[руководстве HippoRAG worker](../../mcp/hipporag/README.md).

Production templates include the `hipporag` service and `hipporag_data` volume;
`docker-compose.build.yml` publishes its release image and the deployment script
starts it with application services. Transfer the production-template changes
to the actual `docker-compose.prod.yml` in the production GitLab checkout and
the `HIPPO_*` block from `env.example` to the root-owned production env file.
The deployment controller reads that env file for Compose interpolation as well
as container environments. Native memory uses registry-default models via API
callbacks, so production does not need the dev Qwen IP in worker settings.
Keep `hipporag_data` across deployments and include it in backups; the volume
stores the corpus, graph and extraction caches. See [Environment Setup](ENV.md).

Локальные модели для русских документов: `emb-bge` обслуживает `BAAI/bge-m3`
(1024 измерения, 8192 токена), `rerank-bge` — `BAAI/bge-reranker-v2-m3`
(пары query/document ограничены 1024 токенами для CPU). Модели лежат в
`models_llm/BAAI--bge-m3` и `models_llm/BAAI--bge-reranker-v2-m3`.

Document search uses the selected reranker model's `request_timeout_s` from the
registry. An unset per-tool timeout is bounded by the remaining agent wall-time,
not a fixed 30-second default. CPU reranking is serialized outside the event
loop in batches (`RERANK_BATCH_SIZE`, default 4), grouped by document length.
Health checks remain responsive; disconnected/expired requests stop between
batches, after any already-running CPU batch finishes. Queue wait counts toward
the forwarded request deadline. Changing the service code requires rebuilding
and recreating `rerank` / `rerank-bge` containers.

`collection.doc_search` returns complete results directly to the agent, as does
`collection.list_documents`. Both commit newly registered chat file references
before returning `artifact_id`, so a later `file.read` can resolve them.
После запуска сервисов команда
`docker compose exec -T api python - --reindex < scripts/configure_local_bge.py`
проверяет реальный inference, назначает модели дефолтными в реестре и запускает
переиндексацию документов. При изменении размерности скрипт переключает физический
индекс документной коллекции, сохраняя старый. Для переиндексации нужны существующие
артефакты chunks; сама смена дефолта не восстанавливает отсутствующие файлы в S3.
Без `--reindex` команда меняет только дефолты. MiniLM-сервисы сохранены.

## 4. Миграции

При обычном `make up` для `api` уже вызывается `alembic upgrade heads`.

Отдельно вручную:

```bash
make migrate
```

## 5. Первый вход

Используются значения из `.env`:

- `DEFAULT_ADMIN_LOGIN`
- `DEFAULT_ADMIN_PASSWORD`

## 6. Перезапуск и остановка

```bash
make restart
make down
```

## 7. Production запуск

Production runtime хранится в production GitLab repository: настоящий
`docker-compose.prod.yml`, `release.env` и `.gitlab-ci.yml` там отделены от
локальной разработки. После release GitLab Runner на production VM через
root-owned controller применяет конкретный commit как immutable bundle в
`/opt/ml-portal/releases`; вручную запускать dev-compose на production нельзя.

Полный процесс: [Release Workflow](RELEASE_WORKFLOW.md).

## 8. Health monitoring

### Контейнер `beat`

Расписание периодических задач выполняется в отдельном контейнере `beat` (Celery Beat), добавленном в `docker-compose.yml`. Он запускается той же точкой входа, что и `worker`, но с командой `celery beat`:

```bash
docker compose logs --tail=200 beat
```

Beat активирует расписание только при наличии переменной окружения `BEAT=1`. Проверить, что планировщик работает:

```bash
docker compose exec beat celery -A app.celery_app inspect scheduled
```

Задачи выполняются воркерами из очереди `health` (приоритет 3). Убедитесь, что `worker` запущен и слушает эту очередь.

### Подключение к мониторингу

| Endpoint | Назначение |
|---|---|
| `GET /api/v1/monitoring/health` | Liveness probe — без обращения к БД |
| `GET /api/v1/monitoring/health/detailed` | Readiness probe — счётчики коннекторов и моделей |
| `GET /api/v1/monitoring/metrics` | Prometheus scrape endpoint |

Пример scrape-конфига для Prometheus:

```yaml
scrape_configs:
  - job_name: ml-portal
    static_configs:
      - targets: ['api:8000']
    metrics_path: /api/v1/monitoring/metrics
    scrape_interval: 60s
```

Без Prometheus метрики можно читать напрямую:

```bash
curl http://localhost:8000/api/v1/monitoring/metrics
curl http://localhost:8000/api/v1/monitoring/health/detailed
```

Подробная документация по всей системе мониторинга: `docs/architecture/HEALTH_MONITORING.md`.

## 9. Runtime diagnostics (admin)

Ключевые admin endpoints для диагностики runtime без container logs:

- `GET /api/v1/admin/agent-runs/{run_id}/trace-pack`
- `GET /api/v1/admin/agent-runs/{run_id}/diagnostics-summary`
- `GET /api/v1/admin/collections/{collection_id}/runtime-readiness`
- `GET /api/v1/admin/agent-runs/capability-graph`
- `GET /api/v1/admin/agent-runs/hitl-policy`

Payloads redacted по runtime policy (secrets/tokens/passwords не должны светиться).

## 9. Backend runtime quality gates

Локально для backend runtime 10/10 используйте:

```bash
make test-runtime-core
make test-runtime-integration
make test-runtime-eval
make test-backend-10-10-gate
```
