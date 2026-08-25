# Production Deploy Checklist

Короткий чеклист для первого выката в production.

## 1. Preflight (обязательно)

- [ ] Зафиксирован release commit в production GitLab и его `release.env`.
- [ ] `APP_IMAGE_TAG` и `BASE_IMAGE_TAG` являются immutable-тегами, не `latest`.
- [ ] `IMAGE_REPOSITORY` указывает на общий внутренний Docker Registry, не `127.0.0.1`.
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

## 2. Сборка и публикация образов

```bash
make update-source
make release-check
make release
```

Проверка:

```bash
docker compose -f docker-compose.build.yml config --images
```

## 3. Поставка в контур без интернета

Production VM получает образы только из внутреннего GitLab Container Registry.
После `make release` GitLab pipeline на production runner делает `pull` и
`up -d`; перенос tar-файлов не является штатным путём.

## 4. Применение миграций

Pipeline применяет только `alembic upgrade $DB_REVISION` из release-файла до
переключения сервисов. API-контейнер не выполняет миграции при каждом рестарте.

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

- [ ] Предыдущий успешный release pipeline доступен в GitLab.
- [ ] Старые image tags не были перезаписаны.
- [ ] Понятно, что retry старого pipeline откатывает код/compose/образы, но не БД.
