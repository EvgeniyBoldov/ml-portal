# Sprint 0 — Stabilization & Frames

## Goal
Freeze the API surface for MVP, enforce routers-only, unify error format, make tests runnable and green in container.

## Scope (Issues)
- A0.1 Align implemented routes ↔ `api/openapi.yaml` (no URL rewrites in proxy)
- A0.2 Single entrypoint, remove duplicates (routers-only)
- A0.3 Standardize errors to RFC7807-like `Problem`
- A0.4 Seed superuser (no manual DB writes), minimal RBAC paths
- A0.5 Test profiles in compose: quick vs full (with heavy)
- A0.6 Makefile/Docs: test targets, developer quickstart

## Acceptance Criteria (DoD)
- Implemented routes snapshot matches contract (no controllers paths)
- `/health` and `/metrics` exposed once
- Error responses follow `{type,title,status,code,detail,trace_id}`
- `seed-admin` works; protected endpoints require auth
- `pytest -m "not heavy and not e2e"` green in container
- Docs updated (CHANGELOG_API, Delivery Checklists K/L)

## Test Plan
- Contract tests for health/auth/basic endpoints
- Negative tests: 401/403/404/409/429
- Container-only CI quick profile enabled
