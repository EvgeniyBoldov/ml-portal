# STAGE 01 — Контракт и заведение урлов (`/api/v1`)

## Цель
Привести все эндпоинты к стабильному контракту **/api/v1** без магии прокси. Создать недостающие урлы, исправить рассинхроны, удалить хлам. Максимально переиспользуем текущие хэндлеры.

## Предусловия
- В репозитории есть `api/openapi.yaml` (контракт v1).  
- Приложение стартует через `apps/api/src/app/main.py`.
- Тесты запускаются в контейнере: `docker compose -f docker-compose.test.yml ...`

## 1. Создать все урлы по слоям (routers-only)
[ ] 1.1 Подключить префикс `/api/v1` единожды в `apps/api/src/app/main.py`.  
[ ] 1.2 Убедиться, что подключены (или создать, если нет) роутеры:
- `app.api.routers.auth` → `/api/v1/auth`
- `app.api.routers.users` → `/api/v1/users`
- `app.api.routers.tenants` → `/api/v1/tenants`
- `app.api.routers.models` → `/api/v1/models`
- `app.api.routers.chat` → `/api/v1/chat` и `/api/v1/chat/stream`
- `app.api.routers.rag` → `/api/v1/rag` (sources/documents/search/chat/stream)
- `app.api.routers.analyze` → `/api/v1/analyze` и `/api/v1/analyze/stream`
- `app.api.routers.jobs` → `/api/v1/jobs`
- `app.api.routers.artifacts` → `/api/v1/artifacts`
- `app.api.routers.health` → `/api/v1/health`
[ ] 1.3 Для каждого роутера создать заглушку `router = APIRouter()` и минимум один хэндлер (если пусто).

## 2. Исправить существующие урлы (old → new)
[ ] 2.1 Таблица соответствия (перерегистрировать хэндлеры, код не трогаем):
- `/api/chats` → `/api/v1/chat` (POST), `/api/v1/chat/stream` (POST SSE)
- `/api/rag_search` или `/api/rag/search*` → `/api/v1/rag/search` (POST)
- `/api/analyze*` без версии → `/api/v1/analyze` (POST), `/api/v1/analyze/stream` (POST)
- `/health` → `/api/v1/health` (GET)
- `/models` → `/api/v1/models/llm` и `/api/v1/models/embeddings` (GET)
- любые `/api/*` без `/v1` → добавить `/v1`
[ ] 2.2 Если хэндлеры в `controllers/*` — **не меняй логику**, импортируй функции в `routers/*` и регистрируй `router.add_api_route(...)`.

## 3. Удаление ненужных файлов (жёстко, из корня репо)
```bash
rm -rf apps/api/src/app/main_enhanced.py
rm -rf apps/api/src/app/api/routers/rag_search.py
```
[ ] 3.1 После переноса users в `routers/users.py` удалить `apps/api/src/app/api/controllers/users.py` (в STAGE 02).

## 4. Исправить тесты под новые урлы
[ ] 4.1 Найти все тесты со старыми путями и обновить под `/api/v1` и контракт.  
[ ] 4.2 Добавить smoke-тесты на существование ключевых эндпоинтов (200/405).

## 5. Недостающие тесты (минимум)
[ ] 5.1 Контрактные: `/api/v1/health`, `/api/v1/chat`, `/api/v1/rag/search`, `/api/v1/analyze` (200, 422/401/404/405).  
[ ] 5.2 SSE smoke: `/api/v1/chat/stream` — заголовок `text/event-stream` и первые события.

## 6. Прогон тестов
[ ] 6.1 Quick профиль в контейнере (см. STAGE 00).

## 7. Критерии завершения
- Роутеры для всех разделов подключены под `/api/v1/*`.
- Старые пути не используются.
- Quick тесты зелёные.
