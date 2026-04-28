# Environment Setup

Этот документ описывает переменные из `env.example` и их назначение.

## 1. Как подготовить `.env`

```bash
make env
```

После этого отредактируй `.env`.

## 2. Минимум для старта dev

Обязательно задать валидные значения:
- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `ASYNC_DB_URL`
- `JWT_SECRET`
- `DEFAULT_ADMIN_LOGIN`
- `DEFAULT_ADMIN_PASSWORD`
- `MINIO_ROOT_PASSWORD`

## 3. Переменные по группам

## General
- `ENV` — окружение (`development`/`production`).
- `DEBUG` — debug-режим backend.
- `LOG_LEVEL` — уровень логирования.

## Postgres (primary)
- `POSTGRES_DB` — имя основной БД контейнера `postgres`.
- `POSTGRES_USER` — пользователь основной БД.
- `POSTGRES_PASSWORD` — пароль основной БД.
- `DATABASE_URL` — sync SQLAlchemy DSN для API/воркера.
- `ASYNC_DB_URL` — async SQLAlchemy DSN.

## Postgres Remote (demo external DB)
- `REMOTE_POSTGRES_HOST` — host удаленной demo-БД для `dbhub-mcp`.
- `REMOTE_POSTGRES_DB` — имя удаленной demo-БД.
- `REMOTE_POSTGRES_USER` — пользователь удаленной demo-БД.
- `REMOTE_POSTGRES_PASSWORD` — пароль удаленной demo-БД.

## Redis / Celery
- `REDIS_URL` — Redis для runtime-хранилищ.
- `CELERY_BROKER_URL` — брокер Celery.
- `CELERY_RESULT_BACKEND` — backend результатов Celery.
- `BEAT` — флаг для планировщика задач (если используется).

## Auth / JWT / PAT / Confirmation
- `JWT_SECRET` — основной секрет для JWT (обязательно заменить в prod).
- `JWT_ALGORITHM` — алгоритм подписи JWT.
- `JWT_ISSUER` — issuer токенов.
- `JWT_AUDIENCE` — audience токенов.
- `JWT_ACCESS_TTL_MINUTES` — TTL access токена.
- `JWT_REFRESH_TTL_DAYS` — TTL refresh токена.
- `JWT_JWKS_JSON` — optional JWKS JSON (если используется внешняя подпись/ротация).
- `JWT_KID` — key id для JWT/JWKS.
- `PAT_ENABLED` — разрешены ли Personal Access Tokens.
- `CREDENTIALS_MASTER_KEY` — ключ шифрования/подписи credential-уровня.
- `CONFIRMATION_SECRET` — секрет confirmation-token (рекомендуется отдельный от JWT).
- `CONFIRMATION_TTL_SECONDS` — TTL confirmation-токена в секундах.

## Password policy
- `PASSWORD_MIN_LENGTH` — минимальная длина пароля.
- `PASSWORD_REQUIRE_UPPERCASE` — требовать uppercase.
- `PASSWORD_REQUIRE_LOWERCASE` — требовать lowercase.
- `PASSWORD_REQUIRE_DIGITS` — требовать цифры.
- `PASSWORD_REQUIRE_SPECIAL` — требовать спецсимволы.
- `PASSWORD_PEPPER` — дополнительный pepper для хеширования.

## Default admin bootstrap
- `DEFAULT_ADMIN_LOGIN` — логин bootstrap-админа.
- `DEFAULT_ADMIN_PASSWORD` — пароль bootstrap-админа.
- `DEFAULT_ADMIN_EMAIL` — email bootstrap-админа.

## Runtime / RBAC
- `RUNTIME_RBAC_ENFORCE_RULES` — жесткий режим RBAC в runtime.
- `RUNTIME_RBAC_ALLOW_UNDEFINED` — поведение для неописанных правил.

## LLM
- `LLM_PROVIDER` — провайдер LLM.
- `LLM_BASE_URL` — endpoint OpenAI-compatible API.
- `LLM_API_KEY` — ключ провайдера.
- `LLM_DEFAULT_MODEL` — модель по умолчанию.
- `LLM_TIMEOUT` — timeout запроса LLM.
- `HTTP_TIMEOUT_SECONDS` — базовый HTTP timeout.
- `HTTP_MAX_RETRIES` — число повторов HTTP.
- `TIMEOUT_SECONDS` — общий fallback timeout.
- `CB_LLM_FAILURES_THRESHOLD` — threshold circuit-breaker LLM.
- `CB_LLM_OPEN_TIMEOUT_SECONDS` — open interval circuit-breaker LLM.
- `CB_LLM_HALF_OPEN_MAX_CALLS` — half-open calls LLM.
- `CB_EMB_FAILURES_THRESHOLD` — threshold circuit-breaker embedding.
- `CB_EMB_OPEN_TIMEOUT_SECONDS` — open interval circuit-breaker embedding.
- `CB_EMB_HALF_OPEN_MAX_CALLS` — half-open calls embedding.

## Embeddings
- `EMB_BASE_URL` — base URL embedding-сервиса для API.
- `EMB_MODEL_ALIAS` — алиас embedding модели.
- `EMB_MODEL_PATH` — путь к локальной модели.
- `EMB_MODEL_DIMENSIONS` — размерность embedding.
- `EMB_MODEL_MAX_TOKENS` — max tokens embedding-модели.
- `EMB_MODEL_VERSION` — версия embedding-модели.
- `EMB_MODEL_PARALLELISM` — параллелизм в embedding-сервисе.
- `EMB_BATCH_SIZE` — размер батча embedding.
- `EMB_MAX_WAIT_MS` — max wait для батчинга.
- `EMB_OFFLINE` — offline-режим загрузки моделей.

## Qdrant
- `QDRANT_URL` — URL Qdrant.
- `QDRANT_API_KEY` — API key Qdrant (если включен).

## MinIO / S3
- `MINIO_ROOT_USER` — root user MinIO.
- `MINIO_ROOT_PASSWORD` — root password MinIO.
- `S3_ENDPOINT` — endpoint S3-совместимого хранилища.
- `S3_ACCESS_KEY` — access key.
- `S3_SECRET_KEY` — secret key.
- `S3_SECURE` — использовать HTTPS для S3.
- `S3_BUCKET_RAG` — бакет под RAG-артефакты.
- `S3_BUCKET_ARTIFACTS` — бакет под прочие артефакты.
- `UPLOAD_MAX_BYTES` — лимит загрузки файла.
- `UPLOAD_ALLOWED_MIME` — разрешенные MIME-типы.

## Idempotency
- `IDEMPOTENCY_ENABLED` — включить idempotency.
- `IDEMP_TTL_HOURS` — TTL idempotency ключей.
- `IDEMPOTENCY_MAX_BYTES` — лимит размера payload для idempotency.

## CORS
- `CORS_ALLOW_ORIGINS` — разрешенные origins.

## Frontend (Vite)
- `VITE_API_BASE_URL` — API base URL, обычно относительный `/api/v1`.
- `VITE_API_PROXY_TARGET` — target dev-proxy фронта.
- `VITE_APP_NAME` — имя приложения в UI.
- `VITE_APP_ENV` — окружение фронта.
- `VITE_PORT` — порт Vite.

## Nginx
- `NGINX_PORT_HTTP` — внешний HTTP порт nginx.
- `NGINX_CLIENT_MAX_BODY_SIZE` — max body size.
- `NGINX_PROXY_TIMEOUT` — timeout прокси.

## MCP
- `NETBOX_URL` — URL NetBox для `netbox-mcp-custom`.

## MCP / Runtime Security
- `MCP_CREDENTIAL_BROKER_ENABLED` — включить broker-flow для MCP credentials.
- `MCP_CREDENTIAL_BROKER_REQUIRED` — требовать broker token в production-like runtime.
- `MCP_ALLOW_RAW_CREDENTIAL_FALLBACK` — legacy raw credential fallback (только local/dev).
- `MCP_CREDENTIAL_TOKEN_TTL_SECONDS` — TTL broker access token.
- `MCP_CREDENTIAL_BROKER_BASE_URL` — base URL credential broker endpoint.
- `MCP_CREDENTIAL_BROKER_RESOLVE_PATH` — path resolve endpoint для MCP side.
- `SQL_MCP_REQUIRE_READONLY` — запрет write SQL в SQL MCP shim по умолчанию.

## Collections Runtime
- `COLLECTION_SCHEMA_STALE_HOURS` — через сколько часов SQL schema sync считается stale в runtime readiness contract.

## 4. Prod baseline

Для первого production-релиза минимум:

- `ENV=production`
- `DEBUG=false`
- сложные секреты: `POSTGRES_PASSWORD`, `JWT_SECRET`, `MINIO_ROOT_PASSWORD`, `S3_SECRET_KEY`, `CREDENTIALS_MASTER_KEY`, `CONFIRMATION_SECRET`
- ограниченный `CORS_ALLOW_ORIGINS` (не `*`)
- рабочие `DATABASE_URL`/`ASYNC_DB_URL` на production БД

## 5. Проверка после изменения `.env`

```bash
make down
make up
make ps
docker compose logs --tail=200 api
```
