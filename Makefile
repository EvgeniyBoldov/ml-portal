# =============================================================================
# ML Portal Makefile
# =============================================================================
# Все команды запускаются в контейнерах через docker compose (v2).
# Базовые образы (ml-portal-base-api, ml-portal-base-ml) пересобираем
# только при изменении зависимостей — они не пересобираются автоматически.

COMPOSE        = docker compose
COMPOSE_FILE   = docker-compose.yml
COMPOSE_TEST   = docker-compose.test.yml

.PHONY: help \
        env \
        build-base-api build-base-ml build-base \
        up up-prod down restart logs ps \
        build build-prod build-no-cache \
        migrate \
        test test-backend test-frontend test-unit \
        test-integration test-integration-up test-integration-run test-integration-down \
        test-e2e test-e2e-ui \
        clean clean-images clean-base clean-all

# =============================================================================
# Help
# =============================================================================
help:
	@echo ""
	@echo "  ML Portal — Make Commands"
	@echo ""
	@echo "  Setup:"
	@echo "    make env               Copy env.example → .env (first time only)"
	@echo ""
	@echo "  Base Images (rebuild only when deps change):"
	@echo "    make build-base-api    Build ml-portal-base-api"
	@echo "    make build-base-ml     Build ml-portal-base-ml"
	@echo "    make build-base        Build both base images"
	@echo ""
	@echo "  Dev (docker-compose.yml):"
	@echo "    make up                Start all dev services (detached)"
	@echo "    make down              Stop all dev services"
	@echo "    make restart           Restart all services"
	@echo "    make logs              Follow logs (all services)"
	@echo "    make ps                Show running services"
	@echo "    make build             Build service images (no base rebuild)"
	@echo "    make build-no-cache    Build service images without cache"
	@echo "    make migrate           Run alembic migrations"
	@echo ""
	@echo "  Tests:"
	@echo "    make test              Run all tests"
	@echo "    make test-backend      Backend unit tests (pytest)"
	@echo "    make test-frontend     Frontend unit tests (vitest)"
	@echo "    make test-unit         Backend + frontend unit tests"
	@echo "    make test-integration  Integration tests (running api container)"
	@echo "    make test-integration-up    Start isolated test infra"
	@echo "    make test-integration-run   Run tests against test infra"
	@echo "    make test-integration-down  Stop test infra"
	@echo "    make test-e2e          Playwright e2e tests"
	@echo ""
	@echo "  Cleanup:"
	@echo "    make clean-images      Remove service images (keep base)"
	@echo "    make clean-base        Remove base images"
	@echo "    make clean-all         Full docker system prune"
	@echo ""

# =============================================================================
# Setup
# =============================================================================

env:
	@if [ -f .env ]; then \
		echo ".env already exists — skipping (delete it first if you want to reset)"; \
	else \
		cp env.example .env; \
		echo "Created .env from env.example. Fill in REQUIRED values before running."; \
	fi

# =============================================================================
# Base Images
# =============================================================================

build-base-api:
	@echo "→ Building ml-portal-base-api..."
	docker build --no-cache -t ml-portal-base-api -f infra/docker/base/Dockerfile.api .
	@echo "✓ ml-portal-base-api ready"

build-base-ml:
	@echo "→ Building ml-portal-base-ml..."
	docker build --no-cache -t ml-portal-base-ml -f infra/docker/base/Dockerfile.ml .
	@echo "✓ ml-portal-base-ml ready"

build-base: build-base-api build-base-ml
	@echo "✓ All base images built"

# =============================================================================
# Dev Stack
# =============================================================================

up:
	@[ -f .env ] || (echo "❌ .env not found — run: make env"; exit 1)
	$(COMPOSE) -f $(COMPOSE_FILE) up -d
	@echo "✓ Dev stack started. API: http://localhost:8000  Frontend: http://localhost:5173"

down:
	$(COMPOSE) -f $(COMPOSE_FILE) down

restart:
	$(COMPOSE) -f $(COMPOSE_FILE) restart

logs:
	$(COMPOSE) -f $(COMPOSE_FILE) logs -f

ps:
	$(COMPOSE) -f $(COMPOSE_FILE) ps

build:
	@[ -f .env ] || (echo "❌ .env not found — run: make env"; exit 1)
	$(COMPOSE) -f $(COMPOSE_FILE) build

build-no-cache:
	@[ -f .env ] || (echo "❌ .env not found — run: make env"; exit 1)
	$(COMPOSE) -f $(COMPOSE_FILE) build --no-cache

migrate:
	$(COMPOSE) -f $(COMPOSE_FILE) exec api alembic upgrade heads

# =============================================================================
# Testing
# =============================================================================

# All tests
test: test-unit test-integration
	@echo "✓ All tests completed"

# Backend unit tests (runs inside the running api container)
test-backend:
	@echo "→ Backend unit tests..."
	$(COMPOSE) -f $(COMPOSE_FILE) exec api pytest tests/unit/ -v --tb=short --maxfail=10
	@echo "✓ Backend unit tests done"

# Frontend unit tests (Vitest)
test-frontend:
	@echo "→ Frontend unit tests..."
	$(COMPOSE) -f $(COMPOSE_FILE) exec frontend npm run test -- --run
	@echo "✓ Frontend unit tests done"

test-unit: test-backend test-frontend

# Integration tests — requires running api container (make up first)
test-integration:
	@echo "→ Integration tests..."
	$(COMPOSE) -f $(COMPOSE_FILE) exec api pytest tests/integration/ -v --tb=short
	@echo "✓ Integration tests done"

# Isolated test infrastructure (separate postgres/redis/qdrant/minio)
test-integration-up:
	@echo "→ Starting isolated test infra..."
	$(COMPOSE) -f $(COMPOSE_TEST) up -d postgres-test redis-test qdrant-test minio-test
	@sleep 5
	@echo "✓ Test infra ready"

test-integration-run:
	@echo "→ Running integration tests against test infra..."
	$(COMPOSE) -f $(COMPOSE_TEST) exec api-test pytest tests/integration/ -v --tb=short
	@echo "✓ Done"

test-integration-down:
	$(COMPOSE) -f $(COMPOSE_TEST) down

# E2E tests with Playwright
test-e2e:
	@echo "→ Playwright e2e tests..."
	@$(COMPOSE) -f $(COMPOSE_FILE) ps api | grep -q "running" || $(MAKE) up
	$(COMPOSE) -f $(COMPOSE_FILE) exec frontend npm run test:e2e
	@echo "✓ E2E tests done"

test-e2e-ui:
	$(COMPOSE) -f $(COMPOSE_FILE) exec frontend npm run test:e2e:ui

# =============================================================================
# Cleanup
# =============================================================================

clean-images:
	@echo "→ Removing service images (base images kept)..."
	$(COMPOSE) -f $(COMPOSE_FILE) down --rmi local
	docker image prune -f
	@echo "✓ Done"

clean-base:
	@echo "→ Removing base images..."
	docker rmi ml-portal-base-api ml-portal-base-ml 2>/dev/null || true
	docker image prune -f
	@echo "✓ Done"

clean-all: clean-images clean-base
	@echo "→ Full docker system prune..."
	docker system prune -f --volumes
	@echo "✓ Done"
