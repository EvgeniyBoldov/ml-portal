# =============================================================================
# ML Portal Makefile
# =============================================================================
# Все команды запускаются в контейнерах через docker-compose
# Базовые образы пересобираются только в крайних случаях

.PHONY: help build-base build-base-api build-base-ml build-dev test clean clean-images clean-base create-superuser generate-code download-models

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
	@echo "Development Commands:"
	@echo "  test               - Run tests in containers"
	@echo "  test-integration   - Run integration tests (full cycle)"
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
# Development Commands
# =============================================================================

test:
	@echo "Running tests in containers..."
	docker-compose -f docker-compose.dev.yml exec api python -m pytest apps/api/tests/ -v
	docker-compose -f docker-compose.dev.yml exec worker python -m pytest apps/api/tests/ -v

test-integration:
	@echo "Running integration tests..."
	@echo "Starting dev services..."
	docker-compose -f docker-compose.dev.yml up -d
	@echo "Waiting for services to be ready..."
	@sleep 30
	@echo "Running tests..."
	cd e2e-tests && source venv/bin/activate && pytest -v --tb=short
	@echo "Tests completed. Services remain running for inspection."

create-superuser:
	@echo "Creating superuser..."
	docker-compose -f docker-compose.dev.yml exec api python infra/scripts/create_superuser.py

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
