# ML Portal Monorepo Management

.PHONY: help build-local build-prod up-local up-prod down-local down-prod clean
.PHONY: install-frontend install-backend test-frontend test-backend lint-frontend lint-backend
.PHONY: format-frontend format-backend type-check-frontend type-check-backend

# Переменные
COMPOSE_LOCAL = infra/compose/docker-compose.local.yml
COMPOSE_PROD = infra/compose/docker-compose.prod.yml
FRONTEND_DIR = apps/web
BACKEND_DIR = apps/api
SCRIPTS_DIR = infra/scripts

help: ## Показать справку
	@echo "ML Portal Monorepo Management"
	@echo "============================="
	@echo ""
	@echo "🚀 Разработка:"
	@echo "  make install-all        - Установить все зависимости"
	@echo "  make dev                - Запустить dev серверы"
	@echo "  make build-all          - Собрать все приложения"
	@echo ""
	@echo "🐳 Docker:"
	@echo "  make build-local        - Собрать образы для локальной разработки"
	@echo "  make up-local           - Запустить локальный стек"
	@echo "  make down-local         - Остановить локальный стек"
	@echo "  make build-prod         - Собрать образы для продакшна"
	@echo "  make up-prod            - Запустить продакшн стек"
	@echo "  make down-prod          - Остановить продакшн стек"
	@echo ""
	@echo "🧪 Тестирование:"
	@echo "  make test-all           - Запустить все тесты"
	@echo "  make test-frontend      - Тесты фронтенда"
	@echo "  make test-backend       - Тесты бэкенда"
	@echo "  make test-e2e           - E2E тесты"
	@echo "  make test-quick         - Быстрый тест системы"
	@echo ""
	@echo "🔍 Качество кода:"
	@echo "  make lint-all           - Линтинг всего проекта"
	@echo "  make format-all         - Форматирование всего проекта"
	@echo "  make type-check-all     - Проверка типов"
	@echo ""
	@echo "🧹 Очистка:"
	@echo "  make clean              - Очистить все образы и volumes"
	@echo "  make clean-cache        - Очистить кэш и временные файлы"
	@echo "  make clean-all          - Полная очистка"
	@echo ""
	@echo "📊 Мониторинг:"
	@echo "  make logs               - Показать логи всех сервисов"
	@echo "  make status             - Показать статус сервисов"
	@echo ""
	@echo "🗄️ База данных:"
	@echo "  make run-migrations     - Запустить миграции БД"
	@echo "  make create-superuser   - Создать суперпользователя"
	@echo "  make reset-db           - Сбросить БД и создать суперпользователя"
	@echo ""
	@echo "🤖 Модели:"
	@echo "  make download-models    - Скачать модели из HuggingFace"
	@echo "  make list-models        - Показать скачанные модели"
	@echo ""
	@echo "🔧 Утилиты:"
	@echo "  make gen-openapi        - Генерировать OpenAPI SDK"
	@echo "  make gen-docs           - Генерировать документацию"

# Установка зависимостей
install-all: install-frontend install-backend ## Установить все зависимости

install-frontend: ## Установить зависимости фронтенда
	@echo "📦 Установка зависимостей фронтенда..."
	cd $(FRONTEND_DIR) && npm install

install-backend: ## Установить зависимости бэкенда
	@echo "📦 Установка зависимостей бэкенда..."
	cd $(BACKEND_DIR) && pip install -r requirements.txt
	cd $(BACKEND_DIR) && pip install -r requirements-test.txt

# Разработка
dev: ## Запустить dev серверы
	@echo "🚀 Запуск dev серверов..."
	@echo "Frontend: http://localhost:3000"
	@echo "Backend: http://localhost:8000"
	@echo "Используйте Ctrl+C для остановки"
	@echo ""
	@echo "Запуск фронтенда в фоне..."
	cd $(FRONTEND_DIR) && npm run dev &
	@echo "Запуск бэкенда в фоне..."
	cd $(BACKEND_DIR) && uvicorn src.app.main:app --reload --host 0.0.0.0 --port 8000 &
	@echo "✅ Dev серверы запущены"

# Сборка
build-all: build-frontend build-backend ## Собрать все приложения

build-frontend: ## Собрать фронтенд
	@echo "🔨 Сборка фронтенда..."
	cd $(FRONTEND_DIR) && npm run build

build-backend: ## Собрать бэкенд (проверка типов)
	@echo "🔨 Проверка типов бэкенда..."
	cd $(BACKEND_DIR) && mypy src/

# Docker
build-local: ## Собрать образы для локальной разработки
	@echo "🐳 Сборка образов для локальной разработки..."
	docker-compose -f $(COMPOSE_LOCAL) build

up-local: ## Запустить локальный стек
	@echo "🐳 Запуск локального стека..."
	docker-compose -f $(COMPOSE_LOCAL) up -d

down-local: ## Остановить локальный стек
	@echo "🐳 Остановка локального стека..."
	docker-compose -f $(COMPOSE_LOCAL) down

build-prod: ## Собрать образы для продакшна
	@echo "🐳 Сборка образов для продакшна..."
	docker-compose -f $(COMPOSE_PROD) build

up-prod: ## Запустить продакшн стек
	@echo "🐳 Запуск продакшн стека..."
	docker-compose -f $(COMPOSE_PROD) up -d

down-prod: ## Остановить продакшн стек
	@echo "🐳 Остановка продакшн стека..."
	docker-compose -f $(COMPOSE_PROD) down

# Тестирование
test-all: test-frontend test-backend ## Запустить все тесты

test-frontend: ## Тесты фронтенда
	@echo "🧪 Запуск тестов фронтенда..."
	cd $(FRONTEND_DIR) && npm test

test-backend: ## Тесты бэкенда
	@echo "🧪 Запуск тестов бэкенда..."
	cd $(BACKEND_DIR) && python -m pytest

test-e2e: ## E2E тесты
	@echo "🧪 Запуск E2E тестов..."
	cd $(BACKEND_DIR) && python -m pytest tests/e2e/ -v

test-quick: ## Быстрый тест системы
	@echo "🧪 Быстрый тест системы..."
	@echo "1. Проверка API..."
	@curl -f http://localhost:8000/healthz || echo "❌ API недоступен"
	@echo "2. Проверка фронтенда..."
	@curl -f http://localhost:3000 || echo "❌ Frontend недоступен"
	@echo "✅ Быстрый тест завершен"

# Качество кода
lint-all: lint-frontend lint-backend ## Линтинг всего проекта

lint-frontend: ## Линтинг фронтенда
	@echo "🔍 Линтинг фронтенда..."
	cd $(FRONTEND_DIR) && npm run lint

lint-backend: ## Линтинг бэкенда
	@echo "🔍 Линтинг бэкенда..."
	cd $(BACKEND_DIR) && flake8 src/
	cd $(BACKEND_DIR) && black --check src/
	cd $(BACKEND_DIR) && isort --check-only src/

format-all: format-frontend format-backend ## Форматирование всего проекта

format-frontend: ## Форматирование фронтенда
	@echo "🎨 Форматирование фронтенда..."
	cd $(FRONTEND_DIR) && npm run format

format-backend: ## Форматирование бэкенда
	@echo "🎨 Форматирование бэкенда..."
	cd $(BACKEND_DIR) && black src/
	cd $(BACKEND_DIR) && isort src/

type-check-all: type-check-frontend type-check-backend ## Проверка типов всего проекта

type-check-frontend: ## Проверка типов фронтенда
	@echo "🔍 Проверка типов фронтенда..."
	cd $(FRONTEND_DIR) && npm run type-check

type-check-backend: ## Проверка типов бэкенда
	@echo "🔍 Проверка типов бэкенда..."
	cd $(BACKEND_DIR) && mypy src/

# Очистка
clean: ## Очистить все образы и volumes
	@echo "🧹 Очистка образов и volumes..."
	docker-compose -f $(COMPOSE_LOCAL) down -v --remove-orphans
	docker-compose -f $(COMPOSE_PROD) down -v --remove-orphans
	docker system prune -f
	docker volume prune -f

clean-cache: ## Очистить кэш и временные файлы
	@echo "🧹 Очистка кэша и временных файлов..."
	@echo "Очистка Python кэша..."
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -type f -delete 2>/dev/null || true
	find . -name "*.pyo" -type f -delete 2>/dev/null || true
	find . -name "*.pyd" -type f -delete 2>/dev/null || true
	@echo "Очистка Node.js кэша..."
	cd $(FRONTEND_DIR) && rm -rf node_modules/.cache 2>/dev/null || true
	cd $(FRONTEND_DIR) && rm -rf dist 2>/dev/null || true
	@echo "Очистка TypeScript кэша..."
	find . -name "*.tsbuildinfo" -type f -delete 2>/dev/null || true
	@echo "✅ Кэш очищен"

clean-all: clean clean-cache ## Полная очистка
	@echo "✅ Полная очистка завершена"

# Мониторинг
logs: ## Показать логи всех сервисов
	@echo "📊 Логи сервисов:"
	docker-compose -f $(COMPOSE_LOCAL) logs -f

status: ## Показать статус сервисов
	@echo "📊 Статус сервисов:"
	docker-compose -f $(COMPOSE_LOCAL) ps

# База данных
run-migrations: ## Запустить миграции БД
	@echo "🗄️ Запуск миграций БД..."
	docker-compose -f $(COMPOSE_LOCAL) exec api python -m alembic upgrade head

create-superuser: ## Создать суперпользователя
	@echo "🔐 Создание суперпользователя..."
	@read -p "Введите логин: " login; \
	read -s -p "Введите пароль (мин. 12 символов): " password; \
	echo; \
	read -p "Введите email (опционально): " email; \
	cd $(BACKEND_DIR) && python scripts/create_superuser.py --login "$$login" --password "$$password" --email "$$email"

reset-db: run-migrations create-superuser ## Сбросить БД и создать суперпользователя
	@echo "✅ БД сброшена и суперпользователь создан"

# Модели
download-models: ## Скачать модели из HuggingFace
	@echo "🤖 Скачивание моделей из HuggingFace..."
	@echo "Используйте: python $(SCRIPTS_DIR)/download_models.py <model_id> [опции]"
	@echo "Примеры:"
	@echo "  python $(SCRIPTS_DIR)/download_models.py sentence-transformers/all-MiniLM-L6-v2 --test"
	@echo "  python $(SCRIPTS_DIR)/download_models.py sentence-transformers/all-mpnet-base-v2 --info"

download-model: ## Скачать конкретную модель
	@echo "🤖 Скачивание конкретной модели..."
	@if [ -z "$(MODEL_ID)" ]; then \
		echo "❌ Не указан MODEL_ID"; \
		echo "Используйте: make download-model MODEL_ID=<model_id>"; \
		echo "Например: make download-model MODEL_ID=BAAI/bge-3m"; \
	else \
		python3 $(SCRIPTS_DIR)/download_model.py $(MODEL_ID) $(ARGS); \
	fi

list-models: ## Показать скачанные модели
	@echo "🤖 Скачанные модели:"
	@if [ -d "models" ]; then \
		echo "📁 Директория models:"; \
		ls -la models/ 2>/dev/null || echo "  (пустая)"; \
	else \
		echo "❌ Директория models не найдена"; \
		echo "Используйте: make download-models"; \
	fi

# Утилиты
gen-openapi: ## Генерировать OpenAPI SDK
	@echo "🔧 Генерация OpenAPI SDK..."
	@echo "TODO: Реализовать генерацию OpenAPI SDK"
	@echo "Будущий путь: packages/openapi-sdk/"

gen-docs: ## Генерировать документацию
	@echo "📚 Генерация документации..."
	@echo "TODO: Реализовать генерацию документации"
	@echo "Будущий путь: docs/"

# Развертывание
deploy: build-prod up-prod ## Полное развертывание (сборка + запуск)
	@echo "🚀 Развертывание завершено!"

# Откат
rollback: ## Откат к предыдущей версии
	@echo "🔄 Откат к предыдущей версии..."
	docker service update --rollback ml-portal_api
	docker service update --rollback ml-portal_worker-mixed
	docker service update --rollback ml-portal_worker-rag