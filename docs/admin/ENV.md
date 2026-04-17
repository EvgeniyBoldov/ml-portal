# Environment Setup

## 1. Создание `.env`
В корне репозитория:

```bash
make env
```

Команда копирует [env.example](../../env.example) в `.env`, если файла ещё нет.

## 2. Обязательный минимум для локального запуска
Проверьте в `.env`:

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `ASYNC_DB_URL`
- `JWT_SECRET`
- `DEFAULT_ADMIN_LOGIN`
- `DEFAULT_ADMIN_PASSWORD`
- `DEFAULT_ADMIN_EMAIL`

## 3. Интеграционные и ML-параметры
При необходимости настройте:

- `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_DEFAULT_MODEL`
- `EMB_BASE_URL` и параметры `EMB_*`
- `RERANK_SERVICE_URL`, `RERANK_ENABLED`
- `NETBOX_URL`
- `REMOTE_POSTGRES_*` (для `postgres-remote` / SQL MCP)

## 4. Проверка согласованности БД
Параметры контейнера `postgres` и URL API/worker должны совпадать:

- `POSTGRES_DB` ↔ DB в `DATABASE_URL` / `ASYNC_DB_URL`
- `POSTGRES_USER` ↔ user в `DATABASE_URL` / `ASYNC_DB_URL`
- `POSTGRES_PASSWORD` ↔ password в `DATABASE_URL` / `ASYNC_DB_URL`

## 5. Рекомендации для prod
- Замените все dev-пароли (`POSTGRES_PASSWORD`, `MINIO_ROOT_PASSWORD`, `DEFAULT_ADMIN_PASSWORD`).
- Используйте длинный секрет в `JWT_SECRET` или ключи `JWT_PRIVATE_KEY`/`JWT_PUBLIC_KEY`.
- Заполните `CREDENTIALS_MASTER_KEY`.
- Ограничьте `CORS_ALLOW_ORIGINS` и выключите `DEBUG`.
