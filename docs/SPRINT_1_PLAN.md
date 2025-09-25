# Sprint 1 — API Handlers & Thin Routers

## Goal
Consolidate all HTTP handlers under routers, add missing endpoints from contract, keep handlers thin (delegate to services).

## Scope (Issues)
- S1.1 Users: move `controllers/users.py` under routers, preserve behaviour
- S1.2 RAG: merge search under `rag` router, keep `analyze` separate
- S1.3 SSE endpoints: `/chat/stream`, `/rag/chat/stream`, `/analyze/stream`
- S1.4 Idempotency-Key support for POST endpoints (chat/rag/analyze/jobs)
- S1.5 Pagination: cursor pattern across list endpoints (users/tenants)
- S1.6 Error normalization across handlers
- S1.7 API tests: contract and negative cases (no heavy)

## Acceptance Criteria (DoD)
- All endpoints exist per `api/openapi.yaml`, mounted once under `/api/v1`
- No imports from `api/controllers/*` in the app entrypoint
- Handlers ≤ ~50 LOC each, business logic in services
- API contract tests green; implemented_routes snapshot up-to-date

## Test Plan
- Contract tests per endpoint per method
- Mock services in router tests
- Idempotency functional tests (repeat POSTs)
