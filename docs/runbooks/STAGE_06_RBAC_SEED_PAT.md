# STAGE 06 — RBAC, seed суперпользователя, PAT

## Seed
[ ] Команда `seed-admin` (env-параметры), документация запуска.

## RBAC
[ ] Роли viewer/editor/admin/tenant_admin, ограничить админ‑ручки.

## PAT
[ ] `/api/v1/tokens/pat` (GET/POST/DELETE), auth по `X-API-Key`

## Тесты
[ ] e2e: seed → login → whoami → admin‑ручка (403/200), PAT сценарии.

## Done
- Онбординг без БД‑костылей, роли работают.
