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

Dev nginx resolves both API and frontend through Docker DNS (`127.0.0.11`,
30-second cache). Recreating either container may change its address; the proxy
refreshes that address automatically. After editing nginx configuration, run
`docker compose exec -T nginx nginx -t`, then
`docker compose exec -T nginx nginx -s reload`.

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
- Docling Serve API (локальный HTTP): `http://localhost:8016/docs`
- Docling playground: `http://localhost:8016/ui`

### Visual review in Chromium

The `chromium-review` container keeps a headless Chromium available over the
local DevTools port. To capture a page, run the helper from the frontend
container:

```bash
docker compose up -d chromium-review
docker compose exec -T frontend node scripts/visual-review.mjs \
  http://nginx:8080/gpt/collections collections
```

Screenshots are saved under `apps/web/test-results/visual-review/`. The helper
removes screenshots older than seven days and keeps at most 20 recent captures.
The DevTools endpoint is available only on the host at `127.0.0.1:9222`.
For the local visual-review environment, sign in with `admin` / `admin123`.
The Chromium profile is persistent, so the session remains available between
container restarts.

### Docling Serve

Сервис `docling` использует официальный CPU-образ
`quay.io/docling-project/docling-serve-cpu:v1.30.0` с включённым playground.
Модели уже входят в образ. Контейнер запускается вместе с dev-стеком и
production compose template. `DocumentExtractionService` использует Docling как
основной parser backend для поддерживаемых форматов; при недоступности сервиса,
ошибке или пустом результате применяются локальные экстракторы. Отдельный
запуск и проверка:

```bash
docker compose up -d --no-deps docling
docker compose ps docling
docker compose logs --tail=100 docling
curl --fail http://localhost:8016/ready
```

В Docker-сети API доступен по `http://docling:5001`, с хоста — только через
loopback на порту `DOCLING_PORT` (по умолчанию `8016`). `DOCLING_NUM_THREADS`
(по умолчанию `2`) задаёт `OMP_NUM_THREADS`. Healthcheck проверяет `/ready`,
включая готовность моделей и очереди конвертации; начальная загрузка может
занять до нескольких минут. Для загрузки файла используется
`POST /v1/convert/file`, контракт доступен в `/docs`.

`DOCLING_URL` задаёт внутренний URL сервиса (по умолчанию
`http://docling:5001`), а `DOCLING_TIMEOUT_SECONDS` — тайм-аут конвертации
(по умолчанию 180 секунд). Сервис не публикует порт в production compose;
API и workers обращаются к нему по внутренней сети. Для документации внешнего
API см. [Docling Serve](https://github.com/docling-project/docling-serve).

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

The release script builds and pushes every image service declared in
`docker-compose.build.yml`; it does not maintain a second image list.
`APPLICATION_SERVICES` and `STATEFUL_SERVICES` in `release.env` define which
production services are validated, pulled, stopped, and started. The release
job carries these values into each new release file, so rollback uses the service
groups associated with that release. Add a new runtime service to the appropriate
list in `release.env.example`; deploy functions use the release's values.

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

Расписание периодических задач выполняется в отдельном контейнере `beat` (Celery Beat), добавленном в `docker-compose.yml`. При `BEAT=1` запустите его командой `make dev-beat-up`; целевой контейнер включён в профиль `scheduler`:

```bash
make dev-beat-up
docker compose logs --tail=200 beat
```

Проверить, что Beat публикует задачи по расписанию:

```bash
docker compose logs --since=5m beat | rg 'Scheduler: Sending due task'
```

Задачи маршрутизируются в разные очереди. Убедитесь, что `worker` запущен и слушает очереди, заданные в `celery_app.py`.

### Подключение к мониторингу

| Endpoint | Назначение |
|---|---|
| `GET /api/v1/monitoring/health` | Liveness probe — без обращения к БД |
| `GET /api/v1/monitoring/health/detailed` | Admin-only readiness probe — счётчики коннекторов и моделей |
| `GET /api/v1/monitoring/metrics` | Admin-only Prometheus scrape endpoint |
| `GET /metrics` | Admin-only process metrics; дополнительно ограничен Nginx по IP |

Пример scrape-конфига для Prometheus:

```yaml
scrape_configs:
  - job_name: ml-portal
    static_configs:
      - targets: ['api:8000']
    metrics_path: /api/v1/monitoring/metrics
    scrape_interval: 60s
    authorization:
      type: Bearer
      credentials_file: /run/secrets/ml_portal_metrics_pat
```

Без Prometheus метрики можно читать напрямую:

```bash
curl --header "Authorization: Bearer $ML_PORTAL_ADMIN_PAT" http://localhost:8000/api/v1/monitoring/metrics
curl --header "Authorization: Bearer $ML_PORTAL_ADMIN_PAT" http://localhost:8000/api/v1/monitoring/health/detailed
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
