.PHONY: build up down logs test lint

build:
	docker compose build --pull

up:
	docker compose up -d

down:
	docker compose down -v

logs:
	docker compose logs -f --tail=200 api worker beat

test:
	PYTHONPATH=.:backend pytest -q

lint:
	ruff . || true
