# Cleanup & Refactoring - November 2024

## 🎯 Цель
Упростить архитектуру статусов, удалить легаси код и исправить проблемы безопасности.

---

## ✅ Что сделано

### 1. **Унифицирована система статусов**

**Проблема:** Было 4 параллельные системы статусов:
- `RAGDocument.status` (основной)
- `Source.status` (дубликат)
- `RAGStatus` (детальные узлы)
- `Job`, `StatusHistory`, `DocumentVersion`, `ModelProgress` (не использовались)

**Решение:** Оставлены только 2 системы:
- ✅ **`RAGDocument.status`** — основной статус документа для UI/API
- ✅ **`RAGStatus`** — детальные узлы pipeline и embedding для SSE

**Удалено:**
- ❌ `Source.status` field + constraint
- ❌ `Job`, `StatusHistory`, `DocumentVersion`, `ModelProgress` таблицы
- ❌ `StateEngine` сервис (избыточная валидация)
- ❌ `JobManager` сервис (не использовался)
- ❌ `rag_jobs` роутер (зависел от удалённых таблиц)

**Файлы:**
- ✏️ `models/rag_ingest.py` — удалён `Source.status`
- ✏️ `models/events.py` — создан для `EventOutbox` (используется в SSE)
- ✏️ `services/outbox_helper.py` — переписан без `StateEngine`
- 🗑️ `models/state_engine.py.del`
- 🗑️ `services/state_engine.py.del`
- 🗑️ `services/job_manager.py.del`
- 🗑️ `api/v1/routers/rag_jobs.py.del`
- 📝 `migrations/versions/0016_cleanup_legacy_status_systems.py` — новая миграция

---

### 2. **Исправлена безопасность SSE auth**

**Проблема:** Токен передавался через query param `?token=...`, что небезопасно:
- Логируется в access logs
- Сохраняется в browser history
- Передаётся в referrer headers

**Решение:** Убран query param, оставлены только безопасные методы:
1. Authorization header (`Bearer token`)
2. httpOnly cookie (`access_token`)

**Файлы:**
- ✏️ `api/deps.py` — `get_current_user_sse()` без query param

---

### 3. **Удалён легаси LLM конфиг**

**Проблема:** Deprecated переменные создавали путаницу:
- `GROQ_BASE_URL`, `GROQ_API_KEY`, `GROQ_DEFAULT_MODEL`
- `LLM_TOKEN`

**Решение:** Удалены все deprecated переменные, оставлены только:
- `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_DEFAULT_MODEL`, `LLM_TIMEOUT`

**Файлы:**
- ✏️ `core/config.py` — упрощён валидатор `LLM_API_KEY`

---

### 4. **Очищен код от TODO и мусора**

**Удалено:**
- ❌ Закомментированные middleware (`TracingMiddleware`, `IdempotencyMiddleware`, `TenantMiddleware`)
- ❌ TODO комментарии в `main.py`, `router.py`, `rag.py`
- ❌ Маркеры `#ПРОВЕРЕНО` и `#ПРОВЕРЕН`

**Файлы:**
- ✏️ `main.py` — удалены закомментированные middleware
- ✏️ `api/v1/router.py` — удалён TODO про health endpoint
- ✏️ `models/rag.py` — удалён TODO про `current_version_id`
- ✏️ `core/db.py` — удалён маркер `#ПРОВЕРЕНО`

---

## 📊 Статистика

**Удалено:**
- 🗑️ 4 модели (`Job`, `StatusHistory`, `DocumentVersion`, `ModelProgress`)
- 🗑️ 2 сервиса (`StateEngine`, `JobManager`)
- 🗑️ 1 роутер (`rag_jobs`)
- 🗑️ 1 поле (`Source.status`)
- 🗑️ 6 deprecated переменных конфига
- 🗑️ ~800 строк кода

**Создано:**
- ✨ 1 миграция (`0016_cleanup_legacy_status_systems.py`)
- ✨ 1 модель (`models/events.py` для `EventOutbox`)

**Изменено:**
- ✏️ 10 файлов

---

## 🚀 Миграция

### Применить миграцию:
```bash
cd apps/api
alembic upgrade head
```

### Откатить (если нужно):
```bash
alembic downgrade -1
```

---

## ⚠️ Breaking Changes

### 1. **Удалён роутер `/api/v1/rag/jobs`**
Если фронтенд использовал эти endpoints, нужно удалить вызовы:
- `POST /api/v1/rag/{doc_id}/cancel`
- `POST /api/v1/rag/jobs/kill`
- `GET /api/v1/rag/jobs`
- `POST /api/v1/rag/{doc_id}/reset`
- `POST /api/v1/rag/{doc_id}/restart`

### 2. **SSE auth без query param**
Фронтенд должен использовать только:
- httpOnly cookie (автоматически отправляется с `credentials: 'include'`)
- Authorization header (если нужно)

**Удалить из фронтенда:**
```typescript
// ❌ Старый код
const eventSource = new EventSource(`/api/v1/rag/events?token=${token}`);

// ✅ Новый код
const eventSource = new EventSource('/api/v1/rag/events', {
  withCredentials: true  // Автоматически отправляет cookies
});
```

### 3. **Удалены env переменные**
Удалить из `.env` файлов:
- `GROQ_BASE_URL`
- `GROQ_API_KEY`
- `GROQ_DEFAULT_MODEL`
- `LLM_TOKEN`

Использовать только:
- `LLM_PROVIDER`
- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_DEFAULT_MODEL`

---

## 🎬 Итог

**До рефакторинга:**
- 4 системы статусов (путаница)
- Небезопасная SSE auth
- Легаси конфиг
- TODO и закомментированный код

**После рефакторинга:**
- 2 чёткие системы статусов
- Безопасная SSE auth
- Чистый конфиг
- Нет мусора в коде

**Результат:** Код стал проще, безопаснее и понятнее 🚀
