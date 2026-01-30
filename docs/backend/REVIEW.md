# Backend Review List

Список того, что требует рефакторинга или удаления.

## 🔴 Критично

### Нарушение паттерна Repository (commit в репозиториях)

**Репозитории НЕ должны делать commit() — только flush()!**

- [ ] `agent_repository.py:15,32,38` — `commit()` в create/update/delete
- [ ] `tool_repository.py:15,32,38` — `commit()` в create/update/delete

**Исправление:** заменить `await self.session.commit()` на `await self.session.flush()`

### Мусор и дубликаты

- [ ] `apps/api/src/app/services/_base.py` — большой файл (9.6KB), возможно содержит неиспользуемый код
- [ ] Проверить неиспользуемые импорты во всех файлах
- [ ] Удалить закомментированный код

### Несоответствие паттернам

- [ ] Унифицировать error handling — использовать кастомные exceptions везде

## 🟡 Важно

### Структура

- [ ] `chat_stream_service.py` — 20KB, слишком большой, разбить на части
- [ ] `collection_service.py` — 24KB, разбить на CollectionCRUD и CollectionVector
- [ ] `rag_status_manager.py` — 23KB, вынести StatusGraph в отдельный модуль
- [ ] `rag_search_service.py` — 17KB, вынести rerank логику

### Типизация

- [ ] Добавить return types ко всем публичным методам
- [ ] Заменить `dict` на TypedDict где возможно
- [ ] Использовать `Annotated` для сложных типов

### Логирование

- [ ] Перейти на structlog везде
- [ ] Добавить correlation_id во все логи
- [ ] Убрать print statements

## 🟢 Улучшения

### Тесты

- [ ] Добавить unit тесты для PermissionService
- [ ] Добавить unit тесты для CredentialService
- [ ] Добавить integration тесты для RAG pipeline

### Документация

- [ ] Добавить docstrings ко всем публичным методам
- [ ] Обновить OpenAPI descriptions

### Performance

- [ ] Добавить индексы для частых запросов
- [ ] Использовать `selectinload` для связанных сущностей
- [ ] Кэшировать часто запрашиваемые данные (prompts, agents)

## Файлы для проверки

| Файл | Размер | Проблема |
|------|--------|----------|
| `chat_stream_service.py` | 20KB | Слишком большой |
| `collection_service.py` | 24KB | Слишком большой |
| `rag_status_manager.py` | 23KB | Слишком большой |
| `rag_search_service.py` | 17KB | Слишком большой |
| `permission_service.py` | 14KB | Нормально, но проверить |
| `rag_ingest_service.py` | 15KB | Нормально, но проверить |
| `credential_service.py` | 12KB | Нормально |
| `agent_service.py` | 11KB | Нормально |
| `prompt_service.py` | 11KB | Нормально |

## Deprecated код

- [ ] Проверить использование `extra_embed_model` vs `embedding_model_alias`
- [ ] Проверить старые enum значения в миграциях
- [ ] Удалить неиспользуемые schemas

## Безопасность

- [ ] Проверить все endpoints на tenant isolation
- [ ] Аудит использования raw SQL queries
- [ ] Проверить валидацию входных данных
