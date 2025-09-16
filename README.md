# ML Portal

Полнофункциональная платформа для работы с LLM, включающая чат, RAG, анализ документов и администрирование.

## 🏗️ Архитектура

Проект следует принципам **Feature-Sliced Design** (FSD) для фронтенда и **Clean Architecture** для бэкенда.

```
ml-portal/
├── apps/                    # Приложения
│   ├── api/                # Backend (FastAPI)
│   │   ├── src/app/
│   │   │   ├── api/        # HTTP endpoints
│   │   │   ├── core/       # Конфигурация, логирование, безопасность
│   │   │   ├── domain/     # Доменные модели
│   │   │   ├── services/   # Бизнес-логика
│   │   │   ├── repos/      # Доступ к данным
│   │   │   ├── adapters/   # Внешние сервисы
│   │   │   └── workers/    # Celery задачи
│   │   └── migrations/     # Alembic миграции
│   └── web/                # Frontend (React/Vite)
│       ├── src/
│       │   ├── pages/      # Страницы (admin, gpt)
│       │   ├── widgets/    # Составные компоненты
│       │   ├── features/   # Бизнес-фичи
│       │   ├── entities/   # Доменные сущности
│       │   └── shared/     # Общие компоненты
│       └── public/
├── packages/               # Общие пакеты
│   ├── shared-types/      # Общие TypeScript типы
│   └── openapi-sdk/       # Автогенерированный API клиент
├── infra/                 # Инфраструктура
│   ├── docker/           # Docker файлы
│   ├── compose/          # Docker Compose конфигурации
│   ├── k8s/              # Kubernetes манифесты
│   └── nginx/            # Nginx конфигурации
└── docs/                 # Документация
```

## 🚀 Быстрый старт

### Локальная разработка

```bash
# Установка зависимостей
npm install

# Запуск всех сервисов (с nginx)
make up-local

# Или только фронтенд
make dev
```

### Доступ к приложению

После запуска `make up-local`:

- **Frontend**: http://localhost (через nginx)
- **API**: http://localhost/api (через nginx)
- **Health Check**: http://localhost/health

Прямой доступ (без nginx):
- **Frontend**: http://localhost:3000
- **API**: http://localhost:8000

### Доступные команды

```bash
# Фронтенд
npm run dev          # Запуск в режиме разработки
npm run build        # Сборка для продакшена
npm run test         # Запуск тестов
npm run lint         # Проверка кода
npm run format       # Форматирование кода

# Docker
npm run docker:up    # Запуск всех сервисов
npm run docker:down  # Остановка сервисов
npm run docker:prod  # Запуск в продакшен режиме
```

## 🔧 Технологии

### Frontend
- **React 18** + **TypeScript**
- **Vite** для сборки
- **React Router** для маршрутизации
- **Zustand** для управления состоянием
- **CSS Modules** для стилизации
- **Vitest** для тестирования

### Backend
- **FastAPI** + **Python 3.8+**
- **SQLAlchemy** + **PostgreSQL**
- **Redis** для кэширования
- **Celery** для фоновых задач
- **Qdrant** для векторного поиска
- **MinIO** для хранения файлов

### Инфраструктура
- **Docker** + **Docker Compose**
- **Nginx** reverse proxy (HTTP/HTTPS)
- **PostgreSQL** база данных
- **Redis** кэш и очереди
- **Qdrant** векторная БД
- **MinIO** S3-совместимое хранилище

## 📁 Структура проекта

### Frontend (apps/web)

```
src/
├── pages/              # Страницы приложения
│   ├── admin/         # Админ-панель
│   └── gpt/           # GPT интерфейс
├── widgets/           # Составные компоненты
├── features/          # Бизнес-фичи
├── entities/          # Доменные сущности
├── shared/            # Общие компоненты
│   ├── api/          # HTTP клиент
│   ├── ui/           # UI компоненты
│   ├── lib/          # Утилиты
│   └── config/       # Конфигурация
└── app/              # Инициализация приложения
```

### Backend (apps/api)

```
src/app/
├── api/              # HTTP API
│   ├── routers/     # Маршруты
│   └── deps/        # Зависимости
├── core/            # Ядро приложения
├── domain/          # Доменные модели
├── services/        # Бизнес-логика
├── repos/           # Репозитории
├── adapters/        # Внешние адаптеры
└── workers/         # Celery задачи
```

## 🧪 Тестирование

```bash
# Фронтенд тесты
npm run test

# Бэкенд тесты
cd apps/api
pytest

# E2E тесты
npm run test:e2e
```

## 📝 Разработка

### Алиасы импортов

```typescript
// Вместо относительных путей
import Button from '../../../shared/ui/Button';

// Используйте алиасы
import Button from '@shared/ui/Button';
import { UsersPage } from '@pages/admin/UsersPage';
import { useAuth } from '@entities/auth';
```

### Правила архитектуры

1. **Слои не могут импортировать "вниз"**:
   - `pages` не может импортировать из `widgets`
   - `features` не может импортировать из `pages`

2. **Общие компоненты в `shared`**:
   - UI компоненты в `shared/ui`
   - API клиент в `shared/api`
   - Утилиты в `shared/lib`

3. **Бизнес-логика в `features`**:
   - Хуки для API вызовов
   - Логика форм
   - Состояние фич

## 🚀 Деплой

### Локальный деплой

```bash
npm run docker:prod
```

### Продакшен

```bash
# Сборка образов
docker-compose -f infra/compose/docker-compose.prod.yml build

# Запуск
docker-compose -f infra/compose/docker-compose.prod.yml up -d
```

## 📚 Документация

- [API документация](docs/API.md)
- [Архитектура](docs/architecture/README.md)
- [Руководства](docs/guides/README.md)

## 🤝 Участие в разработке

1. Форкните репозиторий
2. Создайте ветку для фичи (`git checkout -b feature/amazing-feature`)
3. Зафиксируйте изменения (`git commit -m 'Add amazing feature'`)
4. Отправьте в ветку (`git push origin feature/amazing-feature`)
5. Откройте Pull Request

## 📄 Лицензия

Этот проект лицензирован под MIT License.