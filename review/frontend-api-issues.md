# Замечания по фронтенду - проблемы с API эндпоинтами

## Критические проблемы

### 1. Несоответствие API_BASE в разных файлах
- **Файл**: `apps/web/src/shared/api/index.ts` - использует `/api/v1`
- **Файл**: `apps/web/src/shared/config/env.ts` - использует `http://localhost:8000/api/v1`
- **Проблема**: Разные значения по умолчанию могут привести к неправильным запросам

**Решение**: Унифицировать API_BASE во всех файлах

### 2. Проблема с sendMessageStream в чате
- **Файл**: `apps/web/src/shared/api/chats.ts:52-97`
- **Проблема**: Функция `sendMessageStream` использует прямой `fetch` вместо `apiRequest`, что означает:
  - Не использует единую систему аутентификации
  - Не использует единую обработку ошибок
  - Не использует единую систему retry
  - Дублирует логику получения токена

**Решение**: Переписать `sendMessageStream` для использования `apiRequest` или создать специализированную функцию для streaming

### 3. Несоответствие эндпоинтов чата
- **Фронт ожидает**: `/chat/chats/{chat_id}/messages`
- **Бэк предоставляет**: `/chats/{chat_id}/messages` (без префикса `/chat`)
- **Проблема**: Все запросы к чату будут падать с 404

**Решение**: Исправить пути в `apps/web/src/shared/api/chats.ts`:
- `listChats`: `/chat/chats` → `/chats`
- `createChat`: `/chat/chats` → `/chats`
- `listMessages`: `/chat/chats/{chat_id}/messages` → `/chats/{chat_id}/messages`
- `sendMessage`: `/chat/chats/{chat_id}/messages` → `/chats/{chat_id}/messages`
- `renameChat`: `/chat/chats/{chat_id}` → `/chats/{chat_id}`
- `updateChatTags`: `/chat/chats/{chat_id}/tags` → `/chats/{chat_id}/tags`
- `deleteChat`: `/chat/chats/{chat_id}` → `/chats/{chat_id}`

### 4. Проблема с аутентификацией в sendMessageStream
- **Файл**: `apps/web/src/shared/api/chats.ts:60-65`
- **Проблема**: Дублированная логика получения токена:
  ```typescript
  const token = (window as any).__auth_tokens?.access_token || localStorage.getItem('access_token');
  ```
- **Проблема**: Не использует `getAccessToken()` из `http.ts`

**Решение**: Использовать единую систему получения токенов

### 5. Несоответствие структуры ответов
- **Фронт ожидает**: `ChatMessageResponse` с полями `id`, `content`, `created_at`
- **Бэк возвращает**: Простой объект с полями `id`, `content`, `created_at`
- **Проблема**: Возможны проблемы с типизацией

## Дополнительные проблемы

### 6. Отсутствие обработки ошибок в streaming
- **Файл**: `apps/web/src/shared/api/chats.ts:73`
- **Проблема**: Простая проверка `if (!res.ok) throw new Error(\`HTTP ${res.status}\`)` не предоставляет детальной информации об ошибке

### 7. Несоответствие параметров запросов
- **Фронт отправляет**: `{ content, use_rag, response_stream: true }`
- **Бэк ожидает**: `{ content, use_rag, response_stream }`
- **Проблема**: Возможны проблемы с булевыми значениями

### 8. Проблема с RAG эндпоинтами
- **Фронт ожидает**: `/rag/upload`, `/rag/`, `/rag/{doc_id}/tags`, etc.
- **Бэк предоставляет**: Только `/upload/presign` (с префиксом `/rag`)
- **Проблема**: Большинство RAG функций не реализованы в бэкенде

**Решение**: Либо реализовать недостающие эндпоинты в бэкенде, либо убрать их из фронтенда

### 9. Проблема с аутентификацией
- **Фронт использует**: `/auth/login`, `/auth/me`, `/auth/logout`
- **Бэк предоставляет**: `/auth/login`, `/auth/me`, `/auth/logout` (совпадает)
- **Проблема**: Структура ответов может не совпадать

### 10. Проблема с admin эндпоинтами
- **Фронт ожидает**: `/api/admin/users`, `/api/admin/audit-logs`, etc.
- **Бэк предоставляет**: `/admin/status`, `/admin/mode` (ограниченный набор)
- **Проблема**: Большинство admin функций не реализованы

## Рекомендации по исправлению

1. **Немедленно исправить пути эндпоинтов чата** - это критическая проблема, из-за которой чат не работает
2. **Унифицировать API_BASE** во всех файлах
3. **Переписать sendMessageStream** для использования единой системы API
4. **Проверить соответствие RAG эндпоинтов** - многие функции не реализованы в бэкенде
5. **Проверить соответствие admin эндпоинтов** - большинство функций отсутствуют
6. **Добавить детальную обработку ошибок** для streaming запросов
7. **Проверить типизацию** ответов API

## Приоритет исправлений
1. **Критический**: Исправление путей эндпоинтов чата
2. **Высокий**: Унификация API_BASE
3. **Высокий**: Проверка соответствия RAG и admin эндпоинтов
4. **Средний**: Переписывание sendMessageStream
5. **Низкий**: Улучшение обработки ошибок

## Дополнительные замечания для бэкенда

### RAG модуль
- Реализован только `/upload/presign`
- Отсутствуют: `/rag/`, `/rag/upload`, `/rag/{doc_id}/tags`, `/rag/{doc_id}/progress`, `/rag/stats`, `/rag/metrics`, `/rag/{doc_id}/download`, `/rag/{doc_id}/archive`, `/rag/{doc_id}`, `/rag/search`, `/rag/{doc_id}/reindex`, `/rag/reindex`

### Admin модуль  
- Реализованы только `/admin/status` и `/admin/mode`
- Отсутствуют: `/admin/users`, `/admin/users/{id}`, `/admin/users/{id}/tokens`, `/admin/tokens/{id}`, `/admin/audit-logs`, `/admin/system/status`

### Analyze модуль
- Реализованы `/ingest/presign` и `/stream`
- Отсутствует `/analyze` (который ожидает фронт)
