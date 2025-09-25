# STAGE 03 — Единый формат ошибок и health

## 1. Общий обработчик ошибок
[ ] Модуль `app/api/errors.py` с фабрикой `problem(...)` и регистрацией обработчиков исключений.
[ ] Коды: VALIDATION_ERROR, AUTH_REQUIRED, FORBIDDEN, NOT_FOUND, CONFLICT, RATE_LIMITED, PROVIDER_ERROR, INTERNAL.

## 2. Health
[ ] `/api/v1/health` (GET) → `{status:"ok", version:"..."}`.

## 3. Тесты
[ ] Негативные на 401/403/404/409/429 → валидировать `Problem`.  
[ ] Smoke `/api/v1/health`.

## 4. Done
- Везде `Problem`, health 200, тесты зелёные.
