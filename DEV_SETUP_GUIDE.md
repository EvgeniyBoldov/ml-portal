# ML Portal Development Setup

## Системные требования

- **RAM**: Минимум 8GB (рекомендуется 16GB+)
- **CPU**: 4+ ядра
- **Диск**: 20GB+ свободного места
- **Docker**: 24.0+
- **Docker Compose**: 2.20+

## Быстрый запуск

### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd ml-portal
```

### 2. Переменные окружения

Создайте файл `.env` на основе `env.example`:

```bash
cp env.example .env
```

Минимальные настройки для dev:
```bash
# Скопировать содержимое env.dev в .env
cp env.dev .env
```

### 3. Подготовка моделей (опционально)

Если нужны ML модели:
```bash
# Скачать легкие модели для разработки
mkdir -p models
# Поместить модели в папку models/
```

### 4. Запуск всех сервисов

```bash
# Запуск с пересборкой
docker-compose -f docker-compose.dev.yml up --build

# Или в фоновом режиме
docker-compose -f docker-compose.dev.yml up --build -d
```

### 5. Проверка состояния

```bash
docker-compose -f docker-compose.dev.yml ps
```

## Доступные сервисы

После запуска будут доступны:

| Сервис | URL | Описание |
|--------|-----|----------|
| **Frontend** | http://localhost:5173 | React приложение (hot reload) |
| **API** | http://localhost:8000 | FastAPI backend |
| **Nginx** | http://localhost:80 | Прокси для удобства |
| **MinIO Console** | http://localhost:9001 | S3-compatible storage UI |
| **RabbitMQ Management** | http://localhost:15672 | Message queue UI |
| **PostgreSQL** | localhost:5432 | База данных |

## Переменные окружения для разработки

Основные настройки в `.env`:

```env
# Базы данных (не менять для совместимости)
DATABASE_URL=postgresql://ml_portal:ml_portal_password@postgres:5432/ml_portal
REDIS_URL=redis://redis:6379

# JWT секрет (можно сменить)
JWT_SECRET=dev-jwt-secret-minimum-256-bits-for-development-use-only

# MinIO настройки (не менять для совместимости)
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123

# Qdrant URL (не менять)
QDRANT_URL=http://qdrant:6333
```

## Структура объемов

```
./apps/api/src/app:/app:ro              # Backend код (read-only для контейнера)
./apps/web:/app                         # Frontend код (полная запись для hot reload)
./models:/app/models:ro                 # ML модели
./infra/scripts:/app/infra/scripts:ro   # Скрипты инициализации
```

## Управление сервисами

### Остановка всех сервисов
```bash
docker-compose -f docker-compose.dev.yml down
```

### Остановка с удалением данных
```bash
docker-compose -f docker-compose.dev.yml down -v
```

### Пересборка конкретного сервиса
```bash
docker-compose -f docker-compose.dev.yml up --build <service-name>
```

### Логи конкретного сервиса
```bash
docker-compose -f docker-compose.dev.yml logs <service-name> -f
```

## Тестирование

### Unit тесты (в контейнере)
```bash
docker-compose -f docker-compose.dev.yml exec api pytest tests/unit/ -v
```

### E2E тесты (отдельная команда)
```bash
# Запуск E2E тестов через pytest
docker-compose -f docker-compose.test.yml up --build
```

## Отладка

### Проблемы с ресурсами

Если контейнеры падают из-за нехватки памяти:

1. Отключить ненужные сервисы (comment в compose файле):
   - `worker` (Celery worker)
   - `emb` (Embeddings service) 
   - `llm` (LLM service)

2. Использовать профили Docker:
```bash
# Только основные сервисы
docker-compose -f docker-compose.dev.yml up postgres redis minio api frontend nginx
```

### Проблемы с моделями

Если нет моделей ML, сервисы будут работать, но функции с ML могут возвращать ошибки.

### Hot Reload фронтенда

Код в `apps/web/` автоматически обновляется без перезапуска контейнера.

### Подключение к контейнеру

```bash
# API контейнер
docker-compose -f docker-compose.dev.yml exec api bash

# Frontend контейнер  
docker-compose -f docker-compose.dev.yml exec frontend sh
```

## Пользователи по умолчанию

После запуска создается админ пользователь:
- **Login**: `admin`
- **Password**: `admin123`

## Обновление кода

После изменения кода:

1. **Backend изменения**: автоматическая перезагрузка благодаря `--reload`
2. **Frontend изменения**: автоматическая перезагрузка благодаря Vite HMR
3. **Новые зависимости**: перезапуск контейнера

```bash
# Перезапуск конкретного сервиса
docker-compose -f docker-compose.dev.yml restart <service-name>
```

## Производительность

### Минимальная конфигурация (4GB RAM)

Закомментировать в compose:
- `worker` 
- `emb`
- `llm`
- `nginx`

### Оптимизация сборки

```bash
# Использовать образы вместо сборки каждый раз
docker-compose -f docker-compose.dev.yml pull

# Переиспользовать layers Docker
export COMPOSE_DOCKER_CLI_BUILD=1
export DOCKER_BUILDKIT=1
```

## Troubleshooting

### Ошибка: "port already in use"
```bash
# Проверить какие процессы используют порты
lsof -i :8000
lsof -i :5173

# Остановить следующую команду и перезапустить
docker-compose -f docker-compose.dev.yml down
```

### Ошибка: "database connection failed"
```bash
# Проверить что PostgreSQL запущен
docker-compose -f docker-compose.dev.yml logs postgres

# Перезапуск базы данных
docker-compose -f docker-compose.dev.yml restart postgres
```

### Проблемы с MinIO

```bash
# Бутстрап MinIO заново
docker-compose -f docker-compose.dev.yml exec api python infra/scripts/bootstrap_minio.py
```
