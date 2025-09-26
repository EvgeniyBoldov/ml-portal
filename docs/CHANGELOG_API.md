# CHANGELOG_API.md (v1)

## Added
- Explicit `/api/v1` prefix; no Nginx path rewriting.
- Auth flows (`/auth/login`, `/auth/refresh`), PATs (`/tokens/pat`), and `/users/*` admin endpoints.
- Multi-tenancy header `X-Tenant-Id` used across tenant-scoped endpoints.
- SSE streaming endpoints for chat and analyze.
- RAG ingestion (`/rag/sources`, `/rag/documents`) and hybrid search (`/rag/search`).
- Generic `/jobs` for long-running tasks (ingest/reindex/analyze).

## Standardized
- RFC7807-like `Problem` errors with `code` and `trace_id`.
- Cursor pagination (`limit`, `cursor`, `next_cursor`).
- `Idempotency-Key` for POSTs.

## Kept stable
- Classic chat (`/chat`, `/chat/stream`).
- RAG chat (`/rag/chat`, `/rag/chat/stream`).
- Models discovery (`/models/llm`, `/models/embeddings`).

## Notes
- Tenant can be inferred from JWT; `X-Tenant-Id` overrides for multi-tenant users.
- Admin-only operations guarded by role; public/internal/admin separation recommended at router level.
