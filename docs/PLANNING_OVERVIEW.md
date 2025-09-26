# Planning Overview — Governance & Workflow

## Source of Truth
- API contract: `api/openapi.yaml` (changes only via PRs; FE client regenerates from it).
- PRD/SRS + Delivery Plan: `docs/PRD_SRS.md`, `docs/DELIVERY_PLAN.md`, `docs/DELIVERY_TASKS.md`, `docs/DELIVERY_CHECKLISTS.md`.
- Component Registry: single place to register new modules/components.

## Project Board
Columns: Backlog → Ready → In Progress → Review → Test → Done.  
WIP rule: ≤ 3 concurrent tasks per dev.

## Labels
- Type: `type/feature`, `type/refactor`, `type/bug`, `type/docs`, `type/test`
- Area: `area/api`, `area/services`, `area/connectors`, `area/rag`, `area/analyze`, `area/auth`, `area/fe`, `area/devops`
- Risk: `risk/high`, `risk/medium`, `risk/low`
- Priority: `P0`, `P1`, `P2`

## Branch & PR Policy
- Branches: `feat/*`, `fix/*`, `refactor/*`, `chore/*`
- Small PRs (≤ 300 LOC net change). Link to issue + section “Test Plan”.
- CI profiles: quick (no heavy), full (heavy) gated by label `run:full`.

## DoR (Definition of Ready) for an Issue
- [ ] Linked to PRD/SRS section and API endpoint (if relevant)
- [ ] Acceptance criteria clear & testable
- [ ] Risks/rollback noted
- [ ] Dependencies listed (env, data, secrets)

## DoD (Definition of Done) for an Issue
- [ ] All acceptance tests pass (unit/int/e2e as applicable)
- [ ] API schemas updated & FE client regenerated (if applicable)
- [ ] Docs updated (CHANGELOG, README snippets)
- [ ] Component Registry updated
