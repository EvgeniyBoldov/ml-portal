
# ML-Portal — PRD/SRS v1 (Draft)

## Vision
Internal knowledge-base **consultant** powered by LLM + RAG. MVP scope for 5 users (target 100–200). Average load: ~100 LLM requests/hour (5–10 doc-analysis via RAG, 20–30 chat+RAG).

## Tenancy
- Multi-tenant from day 1 (departments/units).
- Tenant ID must be part of every API write/read and audit records.

## Core Use-Cases (MVP)
1. **Classic Chat with LLM** (no RAG): synchronous & streaming (SSE).
2. **Chat with RAG**: hybrid retrieval (BM25/Vector) + LLM synthesis; streaming.
3. **RAG Ingestion**: add/update/delete sources (files/urls), chunking, embedding, indexing, re-index.
4. **Document Analysis (RAG)**: upload/attach document → extract → answer Q&A over doc; export result.

## Models
- Multiple **LLM models** selectable per tenant and per request.
- Multiple **Embedding models**, with versioning.
- Local **HF models directory** used in dev/prod; **no internet** on prod nodes (offline cache only).

## NFR
- Priorities for **streaming vs non-streaming** operations.
- Observability: logs per request/job, metrics per endpoint, basic traces.
- Security: .env not in VCS; secrets in env/CI vault; audit log for admin actions.
- Availability: no formal SLA; aim for graceful degradation (queues/retries).

## Roles
- Viewer, Editor, Admin (minimum viable RBAC).
- Optional: Project/Tenant admin subset.

## Data
- Artifacts & vectors locally (volume) or external (S3-compatible). TTL for large artifacts (configurable).
- No PII by default; if present, redact on ingest path.

## UI MVP
- Tabs: **Chat**, **RAG Chat**, **Documents**, **Sources**, **Settings**.
- Live status for streaming chats and ingest jobs.
