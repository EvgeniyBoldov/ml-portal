# =============================================================================
# ML Portal Makefile
# =============================================================================
# Все команды запускаются в контейнерах через docker compose (v2).
# Базовый образ ml-portal-base-ml пересобираем
# только при изменении зависимостей — они не пересобираются автоматически.

COMPOSE        = docker compose
COMPOSE_FILE   = docker-compose.yml
COMPOSE_BUILD  = docker-compose.build.yml
COMPOSE_PROD   = docker-compose.prod.yml

BASE_IMAGE_NAME ?= ml-portal-base-ml
BASE_IMAGE_DEV  ?= $(BASE_IMAGE_NAME):latest

# Base image tag — versioned independently from services.
# Rebuild base only when system deps / requirements.ml.txt change.
# Example: BASE_IMAGE_TAG=base-1.2 make build-base
BASE_IMAGE_TAG  ?= latest
BASE_IMAGE_PROD  = $(BASE_IMAGE_NAME):$(BASE_IMAGE_TAG)

# Docker registry prefix. Set to your registry, e.g.:
#   REGISTRY=registry.example.com/ml-portal make build-prod
#   REGISTRY=ghcr.io/myorg make push-prod
# Leave empty to use local images only (no push/pull from remote).
REGISTRY       ?=

# Service image tag — one per release, independent from base.
# Example: IMAGE_TAG=v1.2.3 make build-prod
IMAGE_TAG      ?= latest

# Internal helper: prefix image name with registry if set
_reg_prefix = $(if $(REGISTRY),$(REGISTRY)/,)

.PHONY: help \
        env \
        build-base build-base-ml \
        up down restart logs ps \
        build build-dev build-prod push-prod pull-prod prod-up prod-down prod-migrate build-no-cache \
        migrate \
        test test-api test-backend test-frontend test-unit test-integration test-runtime-core test-runtime-integration test-runtime-eval test-backend-10-10-gate \
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
	@echo "    make build-base-ml     Build $(BASE_IMAGE_DEV)"
	@echo "    make build-base        Build base with both dev/prod tags"
	@echo ""
	@echo "  Dev (docker-compose.yml):"
	@echo "    make up                Start all dev services (detached)"
	@echo "    make down              Stop all dev services"
	@echo "    make restart           Restart all services"
	@echo "    make logs              Follow logs (all services)"
	@echo "    make ps                Show running services"
	@echo "    make build             Build dev service images (no base rebuild)"
	@echo "    make build-dev         Same as make build"
	@echo "    make build-no-cache    Build service images without cache"
	@echo "    make migrate           Run alembic migrations"
	@echo ""
	@echo "  Prod images:"
	@echo "    make build-base        Build base image  (BASE_IMAGE_TAG=$(BASE_IMAGE_TAG))"
	@echo "    make build-prod        Build service images (IMAGE_TAG=$(IMAGE_TAG))"
	@echo "                           Uses BASE_IMAGE_TAG=$(BASE_IMAGE_TAG) as base"
	@echo "                           REGISTRY=$(if $(REGISTRY),$(REGISTRY),(local))"
	@echo "    make push-prod         Push service images to REGISTRY"
	@echo "    make pull-prod         Pull service images from REGISTRY to this host"
	@echo "    make prod-up           Start prod stack (docker-compose.prod.yml)"
	@echo "    make prod-down         Stop prod stack"
	@echo "    make prod-migrate      Run alembic migrations on prod stack"
	@echo ""
	@echo "  Tests:"
	@echo "    make test              Run all tests"
	@echo "    make test-api          All API tests (pytest tests/)"
	@echo "    make test-backend      Backend unit tests (pytest)"
	@echo "    make test-runtime-core Runtime-focused backend unit tests"
	@echo "    make test-runtime-integration Runtime-focused integration tests"
	@echo "    make test-frontend     Frontend unit tests (vitest)"
	@echo "    make test-unit         Backend + frontend unit tests"
	@echo "    make test-integration  Integration tests (running api container)"
	@echo "    make test-runtime-eval Runtime eval harness tests (pytest tests/eval)"
	@echo "    make test-backend-10-10-gate Full backend 10/10 quality gate"
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

build-base-ml:
	@echo "→ Building $(BASE_IMAGE_DEV)..."
	docker build --no-cache -t $(BASE_IMAGE_DEV) -f infra/docker/base/Dockerfile.ml .
	@echo "✓ $(BASE_IMAGE_DEV) ready"

build-base:
	@echo "→ Building base image (BASE_IMAGE_TAG=$(BASE_IMAGE_TAG))..."
	docker build --no-cache \
		-t $(BASE_IMAGE_DEV) \
		-t $(BASE_IMAGE_PROD) \
		-f infra/docker/base/Dockerfile.ml .
	@echo "✓ Base image tags ready: $(BASE_IMAGE_DEV), $(BASE_IMAGE_PROD)"

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

build-dev: build

build-no-cache:
	@[ -f .env ] || (echo "❌ .env not found — run: make env"; exit 1)
	$(COMPOSE) -f $(COMPOSE_FILE) build --no-cache

build-prod:
	@echo "→ Building production images (IMAGE_TAG=$(IMAGE_TAG), BASE_IMAGE_TAG=$(BASE_IMAGE_TAG), REGISTRY=$(if $(REGISTRY),$(REGISTRY),(local)))..."
	IMAGE_TAG=$(IMAGE_TAG) BASE_IMAGE=$(BASE_IMAGE_PROD) $(COMPOSE) -f $(COMPOSE_BUILD) build
	@if [ -n "$(REGISTRY)" ]; then \
		for svc in api worker emb rerank frontend mcp-netbox mcp-sql nginx; do \
			docker tag ml-portal/$$svc:$(IMAGE_TAG) $(REGISTRY)/$$svc:$(IMAGE_TAG); \
		done; \
		echo "✓ Images tagged as $(REGISTRY)/<svc>:$(IMAGE_TAG)"; \
	fi
	@echo "✓ Production images built: ml-portal/<svc>:$(IMAGE_TAG)"

push-prod:
	@[ -n "$(REGISTRY)" ] || (echo "❌ REGISTRY is not set. Example: REGISTRY=registry.example.com/ml-portal make push-prod"; exit 1)
	@echo "→ Pushing images to $(REGISTRY) (tag: $(IMAGE_TAG))..."
	@for svc in api worker emb rerank frontend mcp-netbox mcp-sql nginx; do \
		echo "  pushing $(REGISTRY)/$$svc:$(IMAGE_TAG)"; \
		docker push $(REGISTRY)/$$svc:$(IMAGE_TAG); \
	done
	@echo "✓ All images pushed to $(REGISTRY)"

pull-prod:
	@[ -n "$(REGISTRY)" ] || (echo "❌ REGISTRY is not set. Example: REGISTRY=registry.example.com/ml-portal make pull-prod"; exit 1)
	@echo "→ Pulling images from $(REGISTRY) (tag: $(IMAGE_TAG))..."
	@for svc in api worker emb rerank frontend mcp-netbox mcp-sql nginx; do \
		echo "  pulling $(REGISTRY)/$$svc:$(IMAGE_TAG)"; \
		docker pull $(REGISTRY)/$$svc:$(IMAGE_TAG); \
		docker tag $(REGISTRY)/$$svc:$(IMAGE_TAG) ml-portal/$$svc:$(IMAGE_TAG); \
	done
	@echo "✓ All images pulled and tagged locally as ml-portal/<svc>:$(IMAGE_TAG)"

prod-up:
	@[ -f .env ] || (echo "❌ .env not found — run: make env"; exit 1)
	IMAGE_TAG=$(IMAGE_TAG) $(COMPOSE) -f $(COMPOSE_PROD) up -d
	@echo "✓ Prod stack started (IMAGE_TAG=$(IMAGE_TAG))"

prod-down:
	IMAGE_TAG=$(IMAGE_TAG) $(COMPOSE) -f $(COMPOSE_PROD) down

prod-migrate:
	IMAGE_TAG=$(IMAGE_TAG) $(COMPOSE) -f $(COMPOSE_PROD) exec api alembic upgrade heads

migrate:
	$(COMPOSE) -f $(COMPOSE_FILE) exec api alembic upgrade heads

# =============================================================================
# Testing
# =============================================================================

# All tests
test: test-unit test-integration
	@echo "✓ All tests completed"

# All API tests (unit + integration + migrations tests under apps/api/tests)
test-api:
	@echo "→ All API tests..."
	$(COMPOSE) -f $(COMPOSE_FILE) exec api pytest tests/ -v --tb=short
	@echo "✓ All API tests done"

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

test-runtime-core:
	@echo "→ Runtime core unit tests..."
	$(COMPOSE) -f $(COMPOSE_FILE) exec api pytest tests/unit/ -q --tb=short --maxfail=5 \
		--cov=app.runtime \
		--cov=app.agents.contracts \
		--cov=app.agents.credential_resolver \
		--cov=app.agents.execution_preflight \
		--cov=app.agents.operation_router \
		--cov=app.agents.runtime_rbac_resolver \
		--cov-report=term-missing \
		--cov-fail-under=70
	@echo "✓ Runtime core unit tests done"

test-runtime-integration:
	@echo "→ Runtime integration tests..."
	$(COMPOSE) -f $(COMPOSE_FILE) exec api pytest tests/integration/ -q --tb=short --maxfail=5 -k "runtime or mcp or credential or collection or confirmation"
	@echo "✓ Runtime integration tests done"

test-runtime-eval:
	@echo "→ Runtime eval tests..."
	$(COMPOSE) -f $(COMPOSE_FILE) exec api pytest tests/eval/ -q --tb=short
	@echo "✓ Runtime eval tests done"

test-backend-10-10-gate:
	@echo "→ Backend 10/10 gate..."
	$(COMPOSE) -f $(COMPOSE_FILE) exec api alembic current
	$(COMPOSE) -f $(COMPOSE_FILE) exec api alembic upgrade head
	$(MAKE) test-runtime-core
	$(MAKE) test-runtime-integration
	$(MAKE) test-runtime-eval
	@echo "✓ Backend 10/10 gate passed"

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
	docker rmi $(BASE_IMAGE_DEV) $(BASE_IMAGE_PROD) 2>/dev/null || true
	docker image prune -f
	@echo "✓ Done"

clean-all: clean-images clean-base
	@echo "→ Full docker system prune..."
	docker system prune -f --volumes
	@echo "✓ Done"
