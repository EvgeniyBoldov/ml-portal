# Production Deploy Checklist

Короткий чеклист для первого выката в production.

## 1. Preflight (обязательно)

- [ ] Зафиксирован релизный тег: `vX`.
- [ ] Зафиксирован base-образ: `ml-portal-base-ml:vX` (не `latest`).
- [ ] Все критичные секреты заданы и не `CHANGE_ME`:
  - [ ] `POSTGRES_PASSWORD`
  - [ ] `JWT_SECRET`
  - [ ] `MINIO_ROOT_PASSWORD`
  - [ ] `S3_SECRET_KEY`
  - [ ] `CREDENTIALS_MASTER_KEY`
  - [ ] `CONFIRMATION_SECRET`
- [ ] `ENV=production`, `DEBUG=false`.
- [ ] `CORS_ALLOW_ORIGINS` ограничен (не `*`).
- [ ] Проверены `DATABASE_URL` и `ASYNC_DB_URL` на прод-БД.

## 2. Сборка образов

```bash
make build-base BASE_IMAGE_PROD=ml-portal-base-ml:vX
make build-prod BASE_IMAGE_PROD=ml-portal-base-ml:vX PROD_IMAGE_TAG=vX
```

Проверка:

```bash
docker image ls | rg 'ml-portal|base-ml'
```

## 3. Поставка в контур без интернета (если air-gapped)

```bash
docker save \
  ml-portal-base-ml:vX \
  ml-portal-api:vX \
  ml-portal-worker:vX \
  ml-portal-emb:vX \
  ml-portal-rerank:vX \
  ml-portal-frontend:vX \
  ml-portal-nginx:vX \
  -o ml-portal-vX-images.tar
```

На production-хосте:

```bash
docker load -i ml-portal-vX-images.tar
```

## 4. Применение миграций

До переключения трафика:

```bash
alembic upgrade heads
```

- [ ] Миграции прошли без ошибок.
- [ ] Нет "pending" миграций.

## 5. Запуск и smoke

После старта сервисов проверить:

- [ ] API health: `/api/v1/healthz` отвечает 200.
- [ ] Frontend открывается.
- [ ] Логин под админом проходит.
- [ ] Worker подключен к Redis и берёт задачи.
- [ ] Embedding и rerank health-эндпоинты отвечают.
- [ ] MinIO и Qdrant доступны приложению.

Логи:

```bash
docker logs <api>
docker logs <worker>
```

## 6. Runtime/безопасность smoke

- [ ] Операция с `requires_confirmation=true` реально требует подтверждение.
- [ ] Рискованные операции без user creds не исполняются (strict credentials).
- [ ] Нет fallback-секретов в runtime-логах.

## 7. Post-deploy контроль (первые 30-60 минут)

- [ ] Ошибки API/worker не растут.
- [ ] Нет всплеска 5xx.
- [ ] Нет деградации latency на ключевых сценариях.
- [ ] Очереди Celery не накапливаются аномально.

## 8. Rollback plan (до релиза должен быть готов)

- [ ] Сохранены образы предыдущей версии `v(X-1)`.
- [ ] Подготовлен rollback `.env`/конфигов при необходимости.
- [ ] Понятен порядок отката: образы -> конфиг -> миграции (если поддерживают downgrade).

