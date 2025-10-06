# ML Portal Makefile

.PHONY: help build up down test test-backend test-unit test-integration test-frontend test-frontend-local test-frontend-watch test-frontend-e2e test-frontend-type-check build-frontend install-frontend test-functional test-all test-build test-run clean clean-all logs git-push git-auto gen-all

# Default target
help:
	@echo "ML Portal - Available commands:"
	@echo ""
	@echo "Development:"
	@echo "  build          - Build all Docker images"
	@echo "  build-ml       - Build ML services image only"
	@echo "  dev            - Start development environment"
	@echo "  dev-frontend   - Start dev environment without ML services (for frontend work)"
	@echo "  prod           - Start production environment"
	@echo "  down           - Stop all services"
	@echo "  logs           - Show logs for all services"
	@echo ""
	@echo "Testing:"
	@echo "  test           - Run all tests"
	@echo "  test-backend   - Run backend tests only"
	@echo "  test-unit      - Run unit tests only"
	@echo "  test-integration-database - Run database integration tests"
	@echo "  test-integration-redis   - Run Redis integration tests"
	@echo "  test-integration-minio   - Run MinIO integration tests"
	@echo "  test-integration-qdrant  - Run Qdrant integration tests"
	@echo "  test-integration-api     - Run API integration tests"
	@echo "  test-integration-rag     - Run RAG system integration tests"
	@echo "  test-frontend  - Run frontend tests only"
	@echo "  test-frontend-local - Run frontend tests locally"
	@echo "  test-frontend-type-check - Check TypeScript types"
	@echo "  test-functional - Run functional tests with ML models"
	@echo "  test-all       - Run backend + frontend tests together"
	@echo "  test-build     - Build test images"
	@echo "  test-run       - Run tests with auto-cleanup"
	@echo ""
	@echo "Frontend:"
	@echo "  build-frontend - Build frontend for production"
	@echo "  install-frontend - Install frontend dependencies"
	@echo ""
	@echo "Maintenance:"
	@echo "  clean          - Clean up containers and volumes"
	@echo "  clean-all      - Clean up everything including images"
	@echo ""
	@echo "Git:"
	@echo "  git-push MSG   - Quick git add, commit and push (MSG=commit message)"
	@echo "  git-auto       - Auto commit with smart message based on changes"
	@echo ""
	@echo "Models:"
	@echo "  models-download MODEL - Download model from HuggingFace (MODEL=model-id)"
	@echo "  models-list          - List downloaded models"
	@echo "  models-test          - Test downloaded models"
	@echo "  models-clean         - Clean downloaded models"
	@echo "  models-download-llm  - Download common LLM models"
	@echo "  models-download-embeddings - Download common embedding models"
	@echo "  models-download-all  - Download all common models"
	@echo ""
	@echo "Documentation:"
	@echo "  gen-all        - Generate code documentation files (backend, frontend, infrastructure)"

# Build all images
build:
	docker-compose -f docker-compose.dev.yml build

# Build ML services image only
build-ml:
	docker-compose -f docker-compose.dev.yml build emb llm worker

# Start development environment
dev:
	docker-compose -f docker-compose.dev.yml up -d

# Start dev environment without ML services (for frontend work)
dev-frontend:
	docker-compose -f docker-compose.dev.yml up -d postgres redis minio qdrant rabbitmq api frontend nginx

# Start production environment
prod:
	docker-compose -f docker-compose.prod.yml up -d

# Stop all services
down:
	docker-compose -f docker-compose.dev.yml down
	docker-compose -f docker-compose.prod.yml down

# Show logs
logs:
	docker-compose -f docker-compose.dev.yml logs -f

# Run all tests
test: test-backend test-frontend

# Build test images
test-build:
	docker-compose -f docker-compose.test.yml build

# Run tests with auto-cleanup
test-run:
	docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit
	docker-compose -f docker-compose.test.yml down

# Run backend tests
test-backend:
	docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit backend-test
	docker-compose -f docker-compose.test.yml down

# Run frontend tests
test-frontend:
	docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit frontend-test
	docker-compose -f docker-compose.test.yml down

# Run frontend tests locally (for development)
test-frontend-local:
	cd apps/web && npm test -- --run

test-frontend-watch:
	cd apps/web && npm test

test-frontend-e2e:
	cd apps/web && npx playwright test

test-frontend-type-check:
	cd apps/web && npm run type-check

# Build frontend
build-frontend:
	cd apps/web && npm run build

# Install frontend dependencies
install-frontend:
	cd apps/web && npm install

# Run unit tests only
test-unit:
	docker-compose -f docker-compose.test.yml run --rm backend-test pytest tests/unit/ -v --tb=short

# Run integration tests only
test-integration:
	docker-compose -f docker-compose.test.yml run --rm backend-test pytest tests/integration/ -v --tb=short -c tests/pytest-integration.ini

test-integration-database:
	docker-compose -f docker-compose.test.yml run --rm backend-test pytest tests/integration/test_database.py -v --tb=short -c tests/pytest-integration.ini

test-integration-redis:
	docker-compose -f docker-compose.test.yml run --rm backend-test pytest tests/integration/test_redis.py -v --tb=short -c tests/pytest-integration.ini

test-integration-minio:
	docker-compose -f docker-compose.test.yml run --rm backend-test pytest tests/integration/test_minio.py -v --tb=short -c tests/pytest-integration.ini

test-integration-qdrant:
	docker-compose -f docker-compose.test.yml run --rm backend-test pytest tests/integration/test_qdrant.py -v --tb=short -c tests/pytest-integration.ini

test-integration-api:
	docker-compose -f docker-compose.test.yml run --rm backend-test pytest tests/integration/test_api.py -v --tb=short -c tests/pytest-integration.ini

test-integration-rag:
	docker-compose -f docker-compose.test.yml run --rm backend-test pytest tests/integration/test_rag_system.py -v --tb=short -c tests/pytest-integration.ini

# Run functional tests with ML models
test-functional:
	docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit functional-test
	docker-compose -f docker-compose.test.yml down

# Run all tests (backend + frontend)
test-all:
	docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit backend-test frontend-test
	docker-compose -f docker-compose.test.yml down

# Clean up containers and volumes
clean:
	docker-compose -f docker-compose.dev.yml down -v
	docker-compose -f docker-compose.prod.yml down -v
	docker-compose -f docker-compose.test.yml down -v
	docker system prune -f

# Clean up everything including images
clean-all: clean
	docker-compose -f docker-compose.dev.yml down --rmi all
	docker-compose -f docker-compose.prod.yml down --rmi all
	docker-compose -f docker-compose.test.yml down --rmi all
	docker system prune -af

# Development helpers
dev-backend:
	docker-compose -f docker-compose.dev.yml up -d postgres redis qdrant minio rabbitmq
	cd apps/api && python -m uvicorn src.app.main:app --reload --host 0.0.0.0 --port 8000

# Database management
db-migrate:
	docker-compose -f docker-compose.dev.yml exec api python infra/scripts/run_migrations.py

db-reset:
	docker-compose -f docker-compose.dev.yml exec api python infra/scripts/run_migrations.py

# Health checks
health:
	@echo "Checking service health..."
	@curl -f http://localhost:8000/health || echo "Backend not healthy"
	@curl -f http://localhost:3000 || echo "Frontend not healthy"
	@curl -f http://localhost:80 || echo "Nginx not healthy"

# Git quick push
git-push:
	@if [ -z "$(MSG)" ]; then \
		echo "❌ Error: Please provide commit message"; \
		echo "Usage: make git-push MSG=\"your commit message\""; \
		exit 1; \
	fi
	@echo "🚀 Quick Git Push..."
	@./scripts/git-quick-push.sh "$(MSG)"

# Git auto commit with smart message
git-auto:
	@echo "🤖 Auto Git Commit..."
	@./scripts/git-auto-commit.sh
	@ git push

# Models management
models-download:
	@if [ -z "$(MODEL)" ]; then \
		echo "❌ Error: Please provide model ID"; \
		echo "Usage: make models-download MODEL=microsoft/DialoGPT-small"; \
		echo "Available models:"; \
		echo "  - microsoft/DialoGPT-small (LLM)"; \
		echo "  - sentence-transformers/all-MiniLM-L6-v2 (Embeddings)"; \
		echo "  - microsoft/DialoGPT-medium (LLM)"; \
		echo "  - sentence-transformers/all-mpnet-base-v2 (Embeddings)"; \
		exit 1; \
	fi
	@echo "📥 Downloading model: $(MODEL)"
	@if [ -f "venv-models/bin/activate" ]; then \
		source venv-models/bin/activate && python3 infra/scripts/download_models.py $(MODEL) --output-dir models --test --info; \
	else \
		echo "⚠️  Virtual environment not found. Installing dependencies..."; \
		python3 -m venv venv-models && source venv-models/bin/activate && pip install huggingface_hub transformers safetensors tokenizers numpy && python3 infra/scripts/download_models.py $(MODEL) --output-dir models --test --info; \
	fi

models-list:
	@echo "📋 Downloaded models:"
	@if [ -d "models" ]; then \
		for model_dir in models/*/; do \
			if [ -d "$$model_dir" ]; then \
				model_name=$$(basename "$$model_dir"); \
				echo "  📦 $$model_name"; \
				if [ -f "$$model_dir/metadata.json" ]; then \
					echo "    📊 $$(python3 -c "import json; data=json.load(open('$$model_dir/metadata.json')); print(f\"Size: {data.get('total_size_mb', 0):.1f} MB, Files: {data.get('total_files', 0)}\")")"; \
				fi; \
			fi; \
		done; \
	else \
		echo "  No models directory found"; \
	fi

models-test:
	@echo "🧪 Testing downloaded models..."
	@if [ -d "models" ]; then \
		for model_dir in models/*/; do \
			if [ -d "$$model_dir" ]; then \
				model_name=$$(basename "$$model_dir"); \
				echo "  Testing $$model_name..."; \
				python3 infra/scripts/download_models.py --test "$$model_name" --output-dir models || true; \
			fi; \
		done; \
	else \
		echo "  No models directory found"; \
	fi

models-clean:
	@echo "🧹 Cleaning downloaded models..."
	@if [ -d "models" ]; then \
		echo "  Removing models directory..."; \
		rm -rf models; \
		echo "  ✅ Models cleaned"; \
	else \
		echo "  No models directory found"; \
	fi

# Quick model downloads for common models
models-download-llm:
	@echo "📥 Downloading common LLM models..."
	@make models-download MODEL=microsoft/DialoGPT-small
	@make models-download MODEL=microsoft/DialoGPT-medium

models-download-embeddings:
	@echo "📥 Downloading common embedding models..."
	@make models-download MODEL=sentence-transformers/all-MiniLM-L6-v2
	@make models-download MODEL=sentence-transformers/all-mpnet-base-v2

models-download-all:
	@echo "📥 Downloading all common models..."
	@make models-download-llm
	@make models-download-embeddings

# Generate code documentation files
gen-all:
	@echo "📚 Generating code documentation files..."
	@python3 scripts/generate-code-docs.py
	@echo "✅ Generated files:"
	@echo "  📄 code-docs-backend.txt - Backend code (Python)"
	@echo "  📄 code-docs-frontend.txt - Frontend code (TypeScript/React)"
	@echo "  📄 code-docs-infrastructure.txt - Infrastructure (Docker, configs)"
	@echo "  📄 code-docs-tests.txt - Test code"