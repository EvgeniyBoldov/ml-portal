# Makefile for ML Portal API tests

.PHONY: help test test-unit test-integration test-e2e test-api test-performance test-all test-coverage test-lint clean

# Default target
help:
	@echo "Available targets:"
	@echo "  test-unit        - Run unit tests"
	@echo "  test-integration - Run integration tests"
	@echo "  test-e2e         - Run end-to-end tests"
	@echo "  test-api         - Run API tests"
	@echo "  test-performance - Run performance tests"
	@echo "  test-all         - Run all tests"
	@echo "  test-coverage    - Run tests with coverage report"
	@echo "  test-lint        - Run linting checks"
	@echo "  clean            - Clean test artifacts"

# Unit tests
test-unit:
	@echo "Running unit tests..."
	pytest tests/unit/ -m unit --tb=short -v

# Integration tests
test-integration:
	@echo "Running integration tests..."
	pytest tests/integration/ -m integration --tb=short -v

# E2E tests
test-e2e:
	@echo "Running E2E tests..."
	pytest tests/e2e/ -m e2e --tb=short -v

# API tests
test-api:
	@echo "Running API tests..."
	pytest tests/api/ -m api --tb=short -v

# Performance tests
test-performance:
	@echo "Running performance tests..."
	pytest tests/performance/ -m performance --tb=short -v

# All tests
test-all:
	@echo "Running all tests..."
	pytest tests/ --tb=short -v

# Tests with coverage
test-coverage:
	@echo "Running tests with coverage..."
	pytest tests/ --cov=app --cov-report=html:htmlcov --cov-report=term-missing --cov-fail-under=80

# Linting
test-lint:
	@echo "Running linting checks..."
	flake8 app/ --max-line-length=100 --exclude=__pycache__,migrations
	black --check app/
	isort --check-only app/

# Clean test artifacts
clean:
	@echo "Cleaning test artifacts..."
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf .pytest_cache/
	rm -rf __pycache__/
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete

# Quick test (unit + api)
test-quick:
	@echo "Running quick tests..."
	pytest tests/unit/ tests/api/ -m "unit or api" --tb=short -v

# Test specific module
test-module:
	@echo "Running tests for module: $(MODULE)"
	pytest tests/$(MODULE)/ --tb=short -v

# Test with specific marker
test-marker:
	@echo "Running tests with marker: $(MARKER)"
	pytest tests/ -m $(MARKER) --tb=short -v

# Test in Docker
test-docker:
	@echo "Running tests in Docker..."
	docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit

# Test specific file
test-file:
	@echo "Running tests for file: $(FILE)"
	pytest $(FILE) --tb=short -v

# Test with verbose output
test-verbose:
	@echo "Running tests with verbose output..."
	pytest tests/ --tb=long -vv

# Test with parallel execution
test-parallel:
	@echo "Running tests in parallel..."
	pytest tests/ -n auto --tb=short -v

# Test specific pattern
test-pattern:
	@echo "Running tests matching pattern: $(PATTERN)"
	pytest tests/ -k $(PATTERN) --tb=short -v
