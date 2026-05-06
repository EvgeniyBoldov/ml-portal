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

## 7. Prod запуск

В репозитории сейчас зафиксирован процесс сборки prod-образов (`make build-prod`),
но нет отдельного `docker-compose.prod.yml` как единого стандартизованного рантайма.

Рекомендация:
- использовать собранные образы в отдельном production deployment (compose/k8s/nomad) в infra-репозитории,
- не запускать prod напрямую из dev `docker-compose.yml`.

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
