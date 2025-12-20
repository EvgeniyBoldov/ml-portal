# =============================================================================
# ML Portal Makefile
# =============================================================================
# Все команды запускаются в контейнерах через docker-compose
# Базовые образы пересобираются только в крайних случаях

.PHONY: help build-base build-base-api build-base-ml build-dev test test-unit test-integration test-e2e test-full-cycle test-all clean clean-images clean-base create-superuser generate-code download-models seed-test-data

# Default target
help:
	@echo "ML Portal - Available Commands:"
	@echo ""
	@echo "Build Commands:"
	@echo "  build-base-api     - Build API base image"
	@echo "  build-base-ml      - Build ML base image"
	@echo "  build-base         - Build all base images"
	@echo "  build-dev          - Build all dev services"
	@echo ""
	@echo "Testing Commands:"
	@echo "  test               - Run all tests (unit + integration + e2e)"
	@echo "  test-unit          - Run unit tests (backend + frontend)"
	@echo "  test-integration   - Run integration tests (API)"
	@echo "  test-e2e           - Run e2e tests (Playwright)"
	@echo "  test-full-cycle    - Run full cycle integration test"
	@echo "  test-backend       - Run backend tests only"
	@echo "  test-frontend      - Run frontend tests only"
	@echo "  seed-test-data     - Seed test data for integration tests"
	@echo ""
	@echo "Development Commands:"
	@echo "  create-superuser   - Create superuser in container"
	@echo ""
	@echo "Utility Commands:"
	@echo "  generate-code       - Generate code archive"
	@echo "  download-models     - Download models from HuggingFace"
	@echo ""
	@echo "Cleanup Commands:"
	@echo "  clean-images       - Clean all service images (keep base)"
	@echo "  clean-base         - Clean base images"
	@echo "  clean              - Clean everything"

# =============================================================================
# Build Commands
# =============================================================================

build-base-api:
	@echo "Building API base image..."
	docker build --no-cache -t ml-portal-base-api -f infra/docker/base/Dockerfile.api .

build-base-ml:
	@echo "Building ML base image..."
	docker build --no-cache -t ml-portal-base-ml -f infra/docker/base/Dockerfile.ml .

build-base: build-base-api build-base-ml
	@echo "All base images built successfully!"

build-dev:
	@echo "Building dev services..."
	@if [ ! -f .env ]; then \
		echo "Creating .env from .env.dev..."; \
		cp .env.dev .env; \
	fi
	docker-compose -f docker-compose.dev.yml up -d --build

# =============================================================================
# Testing Commands
# =============================================================================

# Run all tests
test: test-unit test-integration test-e2e
	@echo "✅ All tests completed!"

# Backend unit tests
test-backend:
	@echo "🧪 Running backend unit tests..."
	docker-compose exec api pytest tests/unit/ -v --tb=short --maxfail=5
	@echo "✅ Backend unit tests completed!"

# Frontend unit tests
test-frontend:
	@echo "🧪 Running frontend unit tests..."
	docker-compose exec frontend npm run test -- --run
	@echo "✅ Frontend unit tests completed!"

# All unit tests
test-unit: test-backend test-frontend
	@echo "✅ All unit tests completed!"

# Backend integration tests
test-integration:
	@echo "🧪 Running backend integration tests..."
	@echo "Seeding test data..."
	@$(MAKE) seed-test-data
	@echo "Running integration tests..."
	docker-compose exec api pytest tests/integration/ -v --tb=short
	@echo "✅ Integration tests completed!"

# Full cycle integration test
test-full-cycle:
	@echo "🧪 Running full cycle integration test..."
	@echo "This will test: tenant → user → login → chat → RAG → agents → prompts"
	@$(MAKE) seed-test-data
	docker-compose exec api pytest tests/integration/test_full_cycle.py -v --tb=short -s
	@echo "✅ Full cycle test completed!"

# E2E tests with Playwright
test-e2e:
	@echo "🧪 Running e2e tests with Playwright..."
	@echo "Ensuring services are running..."
	@docker-compose ps | grep -q "api.*Up" || docker-compose up -d
	@echo "Waiting for services to be ready..."
	@sleep 10
	@echo "Running e2e tests..."
	docker-compose exec frontend npm run test:e2e
	@echo "✅ E2E tests completed!"

# E2E tests with UI
test-e2e-ui:
	@echo "🧪 Running e2e tests with Playwright UI..."
	docker-compose exec frontend npm run test:e2e:ui

# Seed test data
seed-test-data:
	@echo "🌱 Seeding test data..."
	@echo "Note: Test data will be created during integration tests"
	@echo "✅ Skipping manual seed (data created automatically in tests)"

# =============================================================================
# Development Commands
# =============================================================================

create-superuser:
	@echo "Creating superuser..."
	docker-compose exec api python infra/scripts/create_superuser.py

# =============================================================================
# Utility Commands
# =============================================================================

generate-code:
	@echo "Generating code archive..."
	@tar -cvf apps.tar apps/
	@tar -cvf infra.tar infra/

download-models:
	@echo "Downloading models from HuggingFace..."
	@if [ ! -d "venv" ]; then \
		echo "Creating virtual environment..."; \
		python3 -m venv venv; \
	fi
	@echo "Activating virtual environment and installing dependencies..."
	. venv/bin/activate && pip install -r infra/scripts/requirements-models.txt
	@echo "Downloading models..."
	. venv/bin/activate && python infra/scripts/download_models.py


# =============================================================================
# Cleanup Commands
# =============================================================================

clean-images:
	@echo "Cleaning service images (keeping base images)..."
	docker-compose -f docker-compose.dev.yml down --rmi all
	docker image prune -f

clean-base:
	@echo "Cleaning base images..."
	docker rmi ml-portal-base-api ml-portal-base-ml 2>/dev/null || true
	docker image prune -f

clean: clean-images clean-base
	@echo "Cleaning everything..."
	docker system prune -f
