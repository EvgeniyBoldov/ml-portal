# Backend Audit Gaps (BAG)

## Контекст
Промежуточное ревью backend'а выявило ряд критичных и средних по важности проблем. Ниже собраны основные из них с ссылками на места в коде. Документ служит чек-листом для последующей доработки.

## Проблемы

### 1. Несоответствие типов поля `scope`
- **Файлы:** `apps/api/src/app/models/rag.py`, миграция `20250118_100007_change_scope_back_to_string.py`
- **Описание:** модель `RAGDocument` хранит `scope` как ENUM, но миграция перевела столбец в `String(20)`. В результате ORM и схема расходятся, что грозит ошибками при синхронизации и работе Alembic.
- **Действие:** унифицировать тип (предпочтительно `String(20)` в модели) и добавить тест/миграцию для подтверждения.

### 2. Несогласованные имена полей для chunk'ов
- **Файлы:** `apps/api/src/app/models/rag.py`, `apps/api/src/app/repositories/documents_repo.py`
- **Описание:** модель использует `chunk_idx`, в репозитории применяется `chunk_index`. Любой вызов `get_by_chunk_index` упадёт с `AttributeError`.
- **Действие:** выбрать единое имя (`chunk_idx`), обновить репозитории и связанные запросы.

### 3. RAG репозитории вызываются с неверными аргументами
- **Файл:** `apps/api/src/app/repositories/factory.py`
- **Описание:** методы `get_rag_documents` / `count_rag_documents` передают `tenant_id` как первый позиционный аргумент в `get_user_documents`, хотя сигнатура не предполагает это. На проде приводит к TypeError.
- **Действие:** скорректировать вызовы и покрыть тестом.

### 4. Сервисы RAG смешивают sync/async и ссылаются на несуществующие фабрики
- **Файл:** `apps/api/src/app/services/rag_service.py`
- **Описание:** используются `create_async_rag_documents_repository(...)`, которых нет. Сервисы наследуются от sync-базы, но работают с async репозиториями и не прокидывают `tenant_id`, что ломает UoW и типизацию.
- **Действие:** вынести чисто async сервис поверх `AsyncRepositoryFactory` и удалить/переписать sync-наследников.

### 5. Статусы RAG не изолированы по тенанту
- **Файл:** `apps/api/src/app/repositories/rag_status_repo.py`
- **Описание:** запросы фильтруют только по `doc_id`, без проверки `tenant_id`. Любой, узнавший UUID документа, может получить чужие статусы.
- **Действие:** добавлять фильтр (join к `ragdocuments` + `tenant_id`) либо валидировать принадлежность документа текущему тенанту перед выдачей.

### 6. SSE выбирает неверный tenant
- **Файл:** `apps/api/src/app/api/v1/routers/rag_status_stream.py`
- **Описание:** для non-admin берётся `user.tenant_id`, хотя в `UserCtx` хранится массив `tenant_ids`. В итоге `tenant_id` становится `None`, подписка получает события всех тенантов.
- **Действие:** использовать первый допустимый tenant из `tenant_ids` (или поддержать множественный фильтр).

### 7. Методы статистики чанков вызывают несуществующий API
- **Файл:** `apps/api/src/app/services/rag_service.py`
- **Описание:** `get_chunk_stats` обращается к `count_document_chunks` и `get_chunks_without_embeddings`, которых нет в `AsyncRAGChunksRepository`.
- **Действие:** реализовать нужные методы или удалить вызовы.

### 8. Опциональный auth возвращает фейкового админа
- **Файл:** `apps/api/src/app/api/deps.py`
- **Описание:** `get_current_user_optional` при отсутствии токена возвращает `UserCtx` с ролью admin и `tenant_ids=["*"]`, что даёт полный доступ в проде (например, для SSE).
- **Действие:** в production-режиме возвращать 401/None; dev-режим - ограничить права.

### 9. Репозитории совершают `commit`
- **Файл:** `apps/api/src/app/repositories/rag_ingest_repos.py` (`AsyncEmbStatusRepository.update_done_count`)
- **Описание:** внутри репозитория вызывается `await self.session.commit()`. Это нарушает UoW и может привести к частичным коммитам.
- **Действие:** убрать `commit` из репозиториев, оставить на уровене сервиса/UoW.

### 10. JWKS раскрывает симметричный секрет
- **Файл:** `apps/api/src/app/core/security.py`
- **Описание:** `get_jwks` публикует HMAC-secret в формате JWKS, фактически выдавая ключ.
- **Действие:** перейти на асимметричные ключи (RSA/EC) и публиковать только публичную часть; для dev - скрывать секрет.

### 11. Heartbeat SSE ничего не отправляет
- **Файл:** `apps/api/src/app/api/v1/routers/rag_status_stream.py`
- **Описание:** `_send_heartbeat` лишь спит; соединение может рваться за прокси/Nginx.
- **Действие:** отдавать keep-alive комментарии `yield "\n"` или удалить таск.

### 12. Валидность статусов `Source`
- **Файл:** `apps/api/src/app/models/rag_ingest.py`
- **Описание:** CheckConstraint допускает только `uploaded, normalized, chunked, embedding, ready, failed, reindexing`. Исторические worker'ы писали `extracted` → IntegrityError.
- **Действие:** убедиться, что Celery-тasks используют разрешённые значения; при необходимости расширить constraint.

## Чек-лист исправлений
- [ ] Унифицировать тип `scope` в модели и БД.
- [ ] Привести `chunk_idx`/`chunk_index` к единому стилю и обновить запросы.
- [ ] Исправить вызовы RAG-репозиториев в `AsyncRepositoryFactory`.
- [ ] Переписать RAG-сервисы на корректный async-подход с `tenant_id`.
- [ ] Добавить фильтрацию по `tenant_id` в `AsyncRAGStatusRepository`.
- [ ] Починить выбор tenant'а в SSE и подписку `RAGEventSubscriber`.
- [ ] Удалить/переиспользовать методы статистики чанков или реализовать их в репозитории.
- [ ] Ограничить `get_current_user_optional`, чтобы не выдавал «админа без токена».
- [ ] Убрать `commit` из репозиториев (`AsyncEmbStatusRepository` и др.).
- [ ] Обновить `get_jwks`, внедрить асимметричные ключи.
- [ ] Настроить heartbeat SSE (отправка keep-alive).
- [ ] Согласовать статусы `Source` с используемыми задачами.
