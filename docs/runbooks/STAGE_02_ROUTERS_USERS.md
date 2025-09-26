# STAGE 02 — Users под routers и чистка контроллеров

## Цель
Перенести все пользовательские эндпоинты под `app.api.routers.users`, затем удалить `controllers/users.py`. Поведение не меняем.

## 1. Перенос регистрации эндпоинтов
[ ] Создать/обновить `apps/api/src/app/api/routers/users.py`, импортировать функции из `app.api.controllers.users` и зарегистрировать маршруты (`add_api_route`).

## 2. Проверка импортов
[ ] Найти прямые импорты `app.api.controllers.users` и устранить.

## 3. Тесты
[ ] Контрактные `/api/v1/users*` (GET/POST/PATCH/DELETE), негативные 401/403/404/409, PAT‑токены.

## 4. Удаление контроллера
[ ] Удалить `apps/api/src/app/api/controllers/users.py` и прогнать тесты.

## 5. Критерии завершения
- Ручки `/api/v1/users*` регистрируются только из routers.
- Контроллер удалён, тесты зелёные.
