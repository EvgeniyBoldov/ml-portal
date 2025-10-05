# Отчет о наведении порядка с Docker Compose файлами

## Проблема
Docker Compose файлы использовали старые пути к Dockerfile:
- `infra/docker/prod/api/Dockerfile.api` вместо `infra/docker/api/Dockerfile.prod`
- `infra/docker/prod/worker/Dockerfile.worker` вместо `infra/docker/worker/Dockerfile.prod`
- И так далее для всех сервисов

## Решение
Приведены все компосы к единому стандарту:

### Структура Dockerfile:
```
infra/docker/{service}/
├── Dockerfile.prod    # Продакшн контейнер
├── Dockerfile.test    # Тестовый контейнер
└── requirements.txt   # Зависимости сервиса
```

## Выполненные изменения

### ✅ docker-compose.yml (основной):
- `backend`: `infra/docker/api/Dockerfile.api` → `infra/docker/api/Dockerfile.prod`
- `frontend`: `infra/docker/frontend/Dockerfile` → `infra/docker/frontend/Dockerfile.prod`

### ✅ docker-compose.dev.yml (разработка):
- Уже использовал правильные пути к `Dockerfile.prod`
- Никаких изменений не требовалось

### ✅ docker-compose.test.yml (тесты):
- Уже использовал правильные пути к `Dockerfile.test`
- Никаких изменений не требовалось

### ✅ docker-compose.prod.yml (продакшн):
- `api`: `infra/docker/prod/api/Dockerfile.api` → `infra/docker/api/Dockerfile.prod`
- `worker-rag`: `infra/docker/prod/worker/Dockerfile.worker` → `infra/docker/worker/Dockerfile.prod`
- `worker-mixed`: `infra/docker/prod/worker/Dockerfile.worker` → `infra/docker/worker/Dockerfile.prod`
- `emb`: `infra/docker/prod/emb/Dockerfile.emb` → `infra/docker/emb/Dockerfile.prod`
- `llm`: `infra/docker/prod/llm/Dockerfile.llm` → `infra/docker/llm/Dockerfile.prod`
- `frontend`: `infra/docker/prod/frontend/Dockerfile` → `infra/docker/frontend/Dockerfile.prod`
- `nginx`: `infra/docker/prod/nginx/Dockerfile` → `infra/docker/nginx/Dockerfile.prod`

### ✅ Переименование файлов:
- `infra/docker/frontend/Dockerfile` → `infra/docker/frontend/Dockerfile.prod`
- `infra/docker/nginx/Dockerfile` → `infra/docker/nginx/Dockerfile.prod`

### ✅ Очистка:
- Удален `apps/api/requirements.txt`
- Удален `apps/api/Makefile`
- Удален `apps/api/pyproject.toml`
- Удален `apps/api/pytest.ini`

## Результат

### ✅ Единообразие:
Все компосы теперь используют единую структуру:
- **Dev/Prod**: `infra/docker/{service}/Dockerfile.prod`
- **Test**: `infra/docker/{service}/Dockerfile.test`

### ✅ Компосы:
1. **docker-compose.yml** - базовый стек для разработки
2. **docker-compose.dev.yml** - полный стек для разработки с hot reload
3. **docker-compose.test.yml** - тестовый стек с изолированными БД
4. **docker-compose.prod.yml** - продакшн стек для Docker Swarm

### ✅ Структура:
```
infra/docker/
├── api/
│   ├── Dockerfile.prod
│   ├── Dockerfile.test
│   └── requirements.txt
├── emb/
│   ├── Dockerfile.prod
│   ├── Dockerfile.test
│   ├── requirements.txt
│   └── entrypoint.sh
├── llm/
│   ├── Dockerfile.prod
│   ├── Dockerfile.test
│   ├── requirements.txt
│   └── entrypoint.sh
├── worker/
│   ├── Dockerfile.prod
│   ├── Dockerfile.test
│   └── requirements.txt
├── frontend/
│   ├── Dockerfile.prod
│   └── Dockerfile.test
└── nginx/
    └── Dockerfile.prod
```

## Статус
**ПОРЯДОК НАВЕДЕН!** 

Все компосы теперь используют единую структуру Dockerfile и корректные пути к файлам.
