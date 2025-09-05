.PHONY: test lint compose-up compose-down stack-deploy stack-rm

test:
	pytest -q

lint:
	ruff . || true

compose-up:
	docker compose -f docker-compose.yml up -d --build

compose-down:
	docker compose -f docker-compose.yml down -v

stack-deploy:
	docker stack deploy -c stack.yml llm

stack-rm:
	docker stack rm llm
