# API Contract v1 — Summary & Rationale

- **Prefix**: `/api/v1` (no proxy rewriting). All endpoints live under this prefix.
- **Auth**: JWT Bearer + optional PAT (`X-API-Key`). Tenancy via `X-Tenant-Id` header (falls back to default tenant in token).
- **Errors**: RFC7807-like `Problem` with `code` (VALIDATION_ERROR, AUTH_REQUIRED, FORBIDDEN, NOT_FOUND, CONFLICT, RATE_LIMITED, PROVIDER_ERROR, INTERNAL) and `trace_id`.
- **Idempotency**: `Idempotency-Key` for POSTs that create side effects (`/chat`, `/rag/*`, `/jobs`, `/analyze`).
- **Pagination**: cursor-based (`limit`, `cursor`, `next_cursor` in response).
- **Streaming**: SSE endpoints for chat and analyze (`/chat/stream`, `/rag/chat/stream`, `/analyze/stream`) with `text/event-stream`.
- **Multi-tenancy**: enforced via header + RBAC. Admin CRUD for tenants/users is under the same prefix.
- **Models**: `/models/llm`, `/models/embeddings` — provider-agnostic metadata (name/version/context_window/etc.).
- **RAG**: Sources, Documents, Search, RAG Chat. Single ingest path handles both RAG and Analyze use-cases.
- **Jobs**: generic `/jobs` for long-running operations (ingest/reindex/analyze-large) with `/jobs/{id}` status polling.
- **Artifacts**: `/artifacts/{artifact_id}` returns a signed URL or streams the artifact.

This structure maps cleanly to MVP scenarios and minimizes churn while keeping room for growth (tools, functions, batch jobs, admin).
