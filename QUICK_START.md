# 🚀 ML Portal - Quick Start

## Полнофункциональная dev-среда

Быстрый запуск всех сервисов для разработки на любой машине.

### 1. Проверка готовности

```bash
chmod +x check-dev-setup.sh
./check-dev-setup.sh
```

### 2. Запуск всех сервисов

```bash
docker-compose -f docker-compose.dev.yml up --build -d
```

### 3. Доступные сервисы

| Сервис | URL | Логин/Пароль |
|--------|-----|--------------|
| **🌐 Frontend** | http://localhost:5173 | Hot reload React |
| **⚙️ API** | http://localhost:8000 | FastAPI backend |
| **🔀 Proxy** | http://localhost:80 | Nginx прокси |
| **📁 MinIO** | http://localhost:9001 | minioadmin/minioadmin123 |
| **🐰 RabbitMQ** | http://localhost:15672 | admin/admin123 |
| **📊 PostgreSQL** | localhost:5432 | ml_portal/ml_portal_password |

### 4. Админ пользователь

- **Login**: `admin`
- **Password**: `admin123`

## Что включено

✅ **PostgreSQL 15** - Основная БД  
✅ **Redis** - Кеш и сессии  
✅ **Qdrant** - Векторная БД  
✅ **MinIO** - S3-совместимое хранилище  
✅ **RabbitMQ** - Message queue  
✅ **API** - FastAPI с hot reload  
✅ **Embedding Service** - Сервис эмбеддингов  
✅ **LLM Service** - Сервис языковой модели  
✅ **Frontend** - React с Vite HMR  
✅ **Celery Worker** - Фоновая обработка  
✅ **Nginx** - Reverse proxy  

## Управление

```bash
# Просмотр статуса
docker-compose -f docker-compose.dev.yml ps

# Логи всех сервисов
docker-compose -f docker-compose.dev.yml logs -f

# Логи конкретного сервиса
docker-compose -f docker-compose.dev.yml logs -f api

# Остановка
docker-compose -f docker-compose.dev.yml down

# Пересборка сервиса
docker-compose -f docker-compose.dev.yml up --build <service-name>
```

## Системные требования

- **RAM**: 8GB+ (рекомендуется 16GB)
- **CPU**: 4+ ядер
- **Диск**: 20GB+ свободного места
- **Docker**: 24.0+
- **Docker Compose**: 2.20+

## Hot Reload

🗑️ **Код фронтенда** (`apps/web/`) обновляется без перезапуска
🗑️ **Код бэкенда** (`apps/api/src/app/`) перезагружается автоматически

## Минимальная конфигурация (если мало ресурсов)

Закомментировать в `docker-compose.dev.yml`:
- `worker` (Celery)
- `emb` (Embeddings)
- `llm` (LLM Service)
- `nginx` (Proxy)

## Troubleshooting

**Порты заняты?**
```bash
lsof -i :8000  # Проверить какой процесс использует
docker-compose -f docker-compose.dev.yml down
```

**Не хватает RAM?**
```bash
# Остановка ненужных сервисов
docker-compose -f docker-compose.dev.yml stop worker emb llm
```

**Проблемы с моделями?**
- Сервисы работают без ML моделей
- ML функции могут возвращать ошибки
- Поместите модели в папку `models/`

---

📖 **Документация**: `DEV_SETUP_GUIDE.md`  
🔧 **Проверка**: `check-dev-setup.sh`
