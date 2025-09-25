# STAGE 09 — Наблюдаемость (Observability)

## Health/Ready/Liveness
[ ] Добавить `/api/v1/health` (уже), `/readyz` и `/livez` при необходимости (простые проверки).

## Метрики
[ ] Экспортер Prometheus (HTTP requests, latency, errors by code, SSE connections, job durations).  
[ ] Метрики ключевых сценариев: chat, rag.search, rag.ingest, analyze.

## Логи
[ ] Структурированные JSON‑логи (уровень, ts, trace_id, path, user/tenant).  
[ ] Присваивать `trace_id` на каждый запрос (если нет — генерировать).

## Тесты
[ ] Smoke метрик (эндпоинт отдаёт), логирование ошибок в Problem.

## Done
- Базовые метрики и структурные логи включены.
