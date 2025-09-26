# STAGE 05 — Analyze поверх retrieval

## Роуты
[ ] `/api/v1/analyze` (POST), `/api/v1/analyze/stream` (POST SSE)

## Логика
[ ] `AnalyzeService` использует `RagSearchService` + LLM

## Тесты
[ ] e2e: upload → ready → analyze; stream‑smoke

## Done
- Ответ с цитатами, тесты зелёные.
