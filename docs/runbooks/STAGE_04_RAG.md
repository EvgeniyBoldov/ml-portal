# STAGE 04 — RAG: ingest/search/chat

## Роуты
[ ] `/api/v1/rag/sources` (GET/POST/DELETE {source_id})
[ ] `/api/v1/rag/documents` (POST file|json), `/api/v1/rag/documents/{doc_id}` (GET/DELETE)
[ ] `/api/v1/rag/search` (POST)
[ ] `/api/v1/rag/chat` (POST) и `/api/v1/rag/chat/stream` (POST SSE)

## Сервисы
[ ] `RagIngestService` (parse→chunk→embed→index)  
[ ] `RagSearchService` (BM25/Vector/Hybrid)  
[ ] `RagChatService` (retrieval + LLM)

## Чистка
[ ] Удалить старые RAG‑ручки вне `/api/v1/rag/*`.

## Тесты
[ ] e2e ingest (upload→ready), search hits, RAG‑чат stream/non‑stream.

## Done
- Единый пайплайн и зелёные тесты.
