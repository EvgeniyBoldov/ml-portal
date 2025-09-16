# ML Portal Docker Management

.PHONY: help build-local build-prod up-local up-prod down-local down-prod clean

help: ## Показать справку
	@echo "ML Portal Docker Management"
	@echo "=========================="
	@echo ""
	@echo "Локальная разработка:"
	@echo "  make build-local    - Собрать образы для локальной разработки"
	@echo "  make up-local       - Запустить локальный стек"
	@echo "  make down-local     - Остановить локальный стек"
	@echo ""
	@echo "Продакшн:"
	@echo "  make build-prod     - Собрать образы для продакшна"
	@echo "  make up-prod        - Запустить продакшн стек"
	@echo "  make down-prod      - Остановить продакшн стек"
	@echo ""
	@echo "Утилиты:"
	@echo "  make clean          - Очистить все образы и volumes"
	@echo "  make clean-cache    - Очистить кэш Python и временные файлы"
	@echo "  make clean-all      - Полная очистка (образы + кэш)"
	@echo "  make logs           - Показать логи всех сервисов"
	@echo ""
	@echo "Тестирование:"
	@echo "  make test-quick     - Быстрый тест системы"
	@echo "  make test-e2e       - Полные E2E тесты"
	@echo "  make test-local     - Тесты в контейнерах"
	@echo ""
	@echo "Система эмбеддингов:"
	@echo "  make init-models    - Инициализировать бакет моделей в MinIO"
	@echo "  make test-embedding - Тестировать систему эмбеддингов"
	@echo "  make demo-embedding - Демонстрация системы эмбеддингов"
	@echo "  make logs-embedding - Показать логи embedding worker"
	@echo ""
	@echo "Модели:"
	@echo "  make download-models      - Скачать модели из HuggingFace"
	@echo "  make download-model       - Скачать конкретную модель (например: BAAI/bge-3m)"
	@echo "  make list-models          - Показать скачанные модели"
	@echo ""
	@echo "Админка и RBAC:"
	@echo "  make create-superuser     - Создать суперпользователя"
	@echo "  make test-rbac           - Тестировать RBAC систему"
	@echo "  make run-migrations      - Запустить миграции БД"
	@echo "  make reset-db            - Сбросить БД и создать суперпользователя"
	@echo "  make test-security       - Тестировать улучшения безопасности"
	@echo "  make test-tz-compliance - Тестировать соответствие ТЗ"
	@echo ""
	@echo "Генерация кода:"
	@echo "  make gen-backend         - Код бэкенда"
	@echo "  make gen-frontend        - Код фронтенда"
	@echo "  make gen-devops          - DevOps код (Docker, Compose)"
	@echo "  make gen-all             - Весь код"
	@echo "  make gen-docs            - Документация"

# Локальная разработка
build-local: ## Собрать образы для локальной разработки
	@echo "Сборка образов для локальной разработки..."
	docker-compose -f docker-compose.local.yml build

up-local: ## Запустить локальный стек
	@echo "Запуск локального стека..."
	docker-compose -f docker-compose.local.yml up -d

down-local: ## Остановить локальный стек
	@echo "Остановка локального стека..."
	docker-compose -f docker-compose.local.yml down

# Продакшн
build-prod: ## Собрать образы для продакшна
	@echo "Сборка образов для продакшна..."
	docker build -f docker/api/Dockerfile.api -t ml-portal-api:latest .
	docker build -f docker/worker/Dockerfile.worker -t ml-portal-worker:latest .
	docker build -f docker/emb/Dockerfile.emb -t ml-portal-emb:latest .
	docker build -f docker/llm/Dockerfile.llm -t ml-portal-llm:latest .
	docker build -f frontend/Dockerfile -t ml-portal-frontend:latest ./frontend

up-prod: ## Запустить продакшн стек
	@echo "Запуск продакшн стека..."
	docker stack deploy -c docker-compose.prod.yml ml-portal

down-prod: ## Остановить продакшн стек
	@echo "Остановка продакшн стека..."
	docker stack rm ml-portal

# Утилиты
clean: ## Очистить все образы и volumes
	@echo "Очистка образов и volumes..."
	docker-compose -f docker-compose.local.yml down -v --remove-orphans
	docker system prune -f
	docker volume prune -f

clean-cache: ## Очистить кэш Python и временные файлы
	@echo "Очистка кэша Python и временных файлов..."
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -type f -delete 2>/dev/null || true
	find . -name "*.pyo" -type f -delete 2>/dev/null || true
	find . -name "*.pyd" -type f -delete 2>/dev/null || true
	rm -f back.txt front.txt 2>/dev/null || true
	@echo "✅ Кэш очищен"

clean-all: clean clean-cache ## Полная очистка (образы + кэш)
	@echo "✅ Полная очистка завершена"

logs: ## Показать логи всех сервисов
	@echo "Логи сервисов:"
	docker-compose -f docker-compose.local.yml logs -f

# Генерация кода
gen-backend: ## Сгенерировать код бэкенда
	@echo "Генерация кода бэкенда..."
	python3 scripts/generate_code.py backend

gen-frontend: ## Сгенерировать код фронтенда
	@echo "Генерация кода фронтенда..."
	python3 scripts/generate_code.py frontend

gen-devops: ## Сгенерировать DevOps код (Docker, Compose)
	@echo "Генерация DevOps кода..."
	python3 scripts/generate_code.py devops

gen-all: ## Сгенерировать весь код проекта
	@echo "Генерация всего кода проекта..."
	python3 scripts/generate_code.py all

gen-docs: ## Сгенерировать документацию проекта
	@echo "Генерация документации проекта..."
	python3 scripts/generate_code.py docs

gen-testing: ## Сгенерировать документацию по тестированию
	@echo "Генерация документации по тестированию..."
	python3 scripts/generate_code.py testing

# Тестирование
test-local: ## Запустить тесты в локальном окружении
	@echo "Запуск тестов..."
	docker-compose -f docker-compose.local.yml exec api python -m pytest

test-system: ## Тестировать локальную систему
	@echo "🧪 Тестирование локальной системы..."
	python3 test_local_system.py

test-e2e: ## Запустить E2E тесты всей системы
	@echo "Запуск E2E тестов..."
	python3 scripts/run_e2e_tests.py

test-quick: ## Быстрый тест системы (без полного E2E)
	@echo "Быстрый тест системы..."
	@echo "1. Проверка API..."
	@curl -f http://localhost:8000/healthz || echo "❌ API недоступен"
	@echo "2. Проверка эмбеддингов..."
	@curl -f http://localhost:8001/healthz || echo "❌ Эмбеддинги недоступны"
	@echo "3. Проверка LLM..."
	@curl -f http://localhost:8002/healthz || echo "❌ LLM недоступен"
	@echo "✅ Быстрый тест завершен"

# Мониторинг
status: ## Показать статус сервисов
	@echo "Статус сервисов:"
	docker-compose -f docker-compose.local.yml ps

# Развертывание
deploy: build-prod up-prod ## Полное развертывание (сборка + запуск)
	@echo "Развертывание завершено!"

# Откат
rollback: ## Откат к предыдущей версии
	@echo "Откат к предыдущей версии..."
	docker service update --rollback ml-portal_api
	docker service update --rollback ml-portal_worker-mixed
	docker service update --rollback ml-portal_worker-rag

# Система эмбеддингов
init-models: ## Инициализировать бакет моделей в MinIO
	@echo "Инициализация бакета моделей..."
	python3 backend/scripts/bootstrap_models_bucket.py

test-embedding: ## Тестировать систему эмбеддингов
	@echo "Тестирование системы эмбеддингов..."
	python3 backend/scripts/test_embedding_system.py

demo-embedding: ## Демонстрация системы эмбеддингов
	@echo "Демонстрация системы эмбеддингов..."
	python3 backend/scripts/demo_embedding_system.py

logs-embedding: ## Показать логи embedding worker
	@echo "Логи embedding worker:"
	docker-compose -f docker-compose.local.yml logs -f embedding-worker

# Модели
download-models: ## Скачать модели из HuggingFace
	@echo "Скачивание моделей из HuggingFace..."
	@echo "Используйте: python scripts/download_models.py <model_id> [опции]"
	@echo "Примеры:"
	@echo "  python scripts/download_models.py sentence-transformers/all-MiniLM-L6-v2 --test"
	@echo "  python scripts/download_models.py sentence-transformers/all-mpnet-base-v2 --info"
	@echo "  python scripts/download_models.py intfloat/e5-large-v2 --include '*.safetensors'"

download-model: ## Скачать конкретную модель (например: BAAI/bge-3m)
	@echo "Скачивание конкретной модели из HuggingFace..."
	@echo "Используйте: make download-model MODEL_ID=<model_id> [опции]"
	@echo "Примеры:"
	@echo "  make download-model MODEL_ID=BAAI/bge-3m"
	@echo "  make download-model MODEL_ID=sentence-transformers/all-MiniLM-L6-v2 --test"
	@echo "  make download-model MODEL_ID=intfloat/e5-large-v2 --info"
	@if [ -z "$(MODEL_ID)" ]; then \
		echo ""; \
		echo "❌ Не указан MODEL_ID"; \
		echo "Используйте: make download-model MODEL_ID=<model_id>"; \
		echo "Например: make download-model MODEL_ID=BAAI/bge-3m"; \
	else \
		python3 scripts/download_model.py $(MODEL_ID) $(ARGS); \
	fi

list-models: ## Показать скачанные модели
	@echo "Скачанные модели:"
	@if [ -d "models" ]; then \
		echo "📁 Директория models:"; \
		ls -la models/ 2>/dev/null || echo "  (пустая)"; \
		if [ -f "models/download_report.json" ]; then \
			echo ""; \
			echo "📊 Отчет о скачивании:"; \
			python3 -c "import json; report=json.load(open('models/download_report.json')); print(f'Моделей: {report[\"total_models\"]}, Файлов: {report[\"total_files\"]}, Размер: {report[\"total_size_mb\"]:.1f} MB')" 2>/dev/null || echo "  (отчет недоступен)"; \
		fi; \
	else \
		echo "❌ Директория models не найдена"; \
		echo "Используйте: make download-models"; \
	fi

# Админка и RBAC
create-superuser: ## Создать суперпользователя
	@echo "🔐 Создание суперпользователя..."
	@read -p "Введите логин: " login; \
	read -s -p "Введите пароль (мин. 12 символов): " password; \
	echo; \
	read -p "Введите email (опционально): " email; \
	cd backend && python scripts/create_superuser.py --login "$$login" --password "$$password" --email "$$email"

test-rbac: ## Тестировать RBAC систему
	@echo "🧪 Тестирование RBAC системы..."
	@echo "Убедитесь, что сервер запущен на http://localhost:8000"
	@cd backend && python scripts/test_rbac_system.py

run-migrations: ## Запустить миграции БД
	@echo "🗄️ Запуск миграций БД..."
	docker-compose -f docker-compose.local.yml exec api python -m alembic upgrade head

reset-db: run-migrations create-superuser ## Сбросить БД и создать суперпользователя
	@echo "✅ БД сброшена и суперпользователь создан"

test-security: ## Тестировать улучшения безопасности
	@echo "🔒 Тестирование улучшений безопасности..."
	docker-compose -f docker-compose.local.yml exec api python scripts/test_security_improvements.py

test-tz-compliance: ## Тестировать соответствие техническому заданию
	@echo "📋 Тестирование соответствия ТЗ..."
	docker-compose -f docker-compose.local.yml exec api python -m pytest tests/test_tz_compliance.py -v