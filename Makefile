# =============================================================================
# ML Portal
#
# Local developers use only the dev-* and test-* targets. Release targets are
# for a DevOps workstation cloned from the production GitLab repository, where
# release.env and docker-compose.prod.yml are maintained.
# =============================================================================

COMPOSE_DEV := docker compose -f docker-compose.yml

.PHONY: help env \
	dev-base dev-up dev-down dev-restart dev-logs dev-ps dev-build dev-build-no-cache dev-migrate dev-beat-up dev-beat-down \
	base-hash \
	up down restart logs ps build build-no-cache migrate \
	test test-api test-backend test-frontend test-unit test-integration \
	test-runtime-core test-runtime-integration test-runtime-eval test-backend-10-10-gate test-e2e test-e2e-ui \
	update-source release-preview release-check release

help:
	@echo ""
	@echo "ML Portal"
	@echo ""
	@echo "  Local development:"
	@echo "    make env                 Create local .env from env.example"
	@echo "    make dev-base            Build the local ML dependency base image"
	@echo "    make dev-up              Start the local development stack"
	@echo "    make dev-down            Stop the local development stack"
	@echo "    make dev-logs            Follow local development logs"
	@echo "    make dev-build           Build local development images"
	@echo "    make dev-migrate         Apply migrations in the local stack"
	@echo "    make dev-beat-up         Start the optional local Celery scheduler"
	@echo "    make base-hash            Calculate the base input hash"
	@echo ""
	@echo "  Tests (require make dev-up):"
	@echo "    make test                Backend + frontend unit and integration tests"
	@echo "    make test-api            All API tests"
	@echo "    make test-backend        Backend unit tests"
	@echo "    make test-frontend       Frontend unit tests"
	@echo "    make test-e2e            Playwright end-to-end tests"
	@echo ""
	@echo "  Production release (only in the production GitLab clone):"
	@echo "    make update-source       Merge source/main from GitHub into local main"
	@echo "    make release-preview     Show current and next release versions"
	@echo "    make release-check       Validate release.env and release prerequisites"
	@echo "    make release             Build, push, version, commit and push a release"
	@echo ""
	@echo "  Legacy local aliases: up down restart logs ps build build-no-cache migrate"

env:
	@if [ -f .env ]; then \
		echo ".env already exists — skipping"; \
	else \
		cp env.example .env; \
		echo "Created .env from env.example. Fill in required local values."; \
	fi

# =============================================================================
# Local development
# =============================================================================

dev-base:
	docker build -t ml-portal-base-ml:latest -f infra/docker/base/Dockerfile.ml .

dev-up:
	@[ -f .env ] || (echo "ERROR: .env not found — run: make env"; exit 1)
	$(COMPOSE_DEV) up -d

dev-down:
	$(COMPOSE_DEV) down

dev-restart:
	$(COMPOSE_DEV) restart

dev-logs:
	$(COMPOSE_DEV) logs -f

dev-ps:
	$(COMPOSE_DEV) ps

dev-build:
	@[ -f .env ] || (echo "ERROR: .env not found — run: make env"; exit 1)
	$(COMPOSE_DEV) build

dev-build-no-cache:
	@[ -f .env ] || (echo "ERROR: .env not found — run: make env"; exit 1)
	$(COMPOSE_DEV) build --no-cache

dev-migrate:
	$(COMPOSE_DEV) exec api alembic upgrade head

dev-beat-up:
	$(COMPOSE_DEV) --profile scheduler up -d beat

dev-beat-down:
	$(COMPOSE_DEV) stop beat

base-hash:
	@bash -c 'source scripts/release/common.sh; base_input_sha'

up: dev-up
down: dev-down
restart: dev-restart
logs: dev-logs
ps: dev-ps
build: dev-build
build-no-cache: dev-build-no-cache
migrate: dev-migrate

# =============================================================================
# Local tests
# =============================================================================

test: test-unit test-integration

test-api:
	$(COMPOSE_DEV) exec api pytest tests/ -v --tb=short

test-backend:
	$(COMPOSE_DEV) exec api pytest tests/unit/ -v --tb=short --maxfail=10

test-frontend:
	$(COMPOSE_DEV) exec frontend npm run test -- --run

test-unit: test-backend test-frontend

test-integration:
	$(COMPOSE_DEV) exec api pytest tests/integration/ -v --tb=short

test-runtime-core:
	$(COMPOSE_DEV) exec api pytest tests/unit/ -q --tb=short --maxfail=5 \
		--cov=app.runtime \
		--cov=app.agents.contracts \
		--cov=app.agents.credential_resolver \
		--cov=app.agents.execution_preflight \
		--cov=app.agents.operation_router \
		--cov=app.agents.runtime_rbac_resolver \
		--cov-report=term-missing \
		--cov-fail-under=70

test-runtime-integration:
	$(COMPOSE_DEV) exec api pytest tests/integration/ -q --tb=short --maxfail=5 -k "runtime or mcp or credential or collection or confirmation"

test-runtime-eval:
	$(COMPOSE_DEV) exec api pytest tests/eval/ -q --tb=short

test-backend-10-10-gate:
	$(COMPOSE_DEV) exec api alembic current
	$(COMPOSE_DEV) exec api alembic upgrade head
	$(MAKE) test-runtime-core
	$(MAKE) test-runtime-integration
	$(MAKE) test-runtime-eval

test-e2e:
	@$(COMPOSE_DEV) ps api | grep -q "running" || $(MAKE) dev-up
	$(COMPOSE_DEV) exec frontend npm run test:e2e

test-e2e-ui:
	$(COMPOSE_DEV) exec frontend npm run test:e2e:ui

# =============================================================================
# Production release — DevOps workstation only
# =============================================================================

update-source:
	bash scripts/release/update-source.sh

release-preview:
	bash scripts/release/release-preview.sh

release-check:
	bash scripts/release/release-check.sh

release:
	bash scripts/release/release.sh
