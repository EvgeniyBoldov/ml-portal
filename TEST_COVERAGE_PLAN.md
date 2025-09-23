# План улучшения покрытия тестами

## Анализ текущего состояния

**Текущее покрытие**: 50% (6485 строк, 3234 не покрыты) ✅ **+12%**
**Цель**: 80%+ покрытие

## Модули для удаления (Legacy/Duplicate)

### 1. Legacy модули (0% покрытие, можно удалить)
- `app/cli.py` - CLI команды, есть setup роутер
- `app/clients/http.py` - неиспользуемый HTTP клиент
- `app/clients/minio_signer.py` - неиспользуемый MinIO подписчик
- `app/core/cache.py` - неиспользуемый кэш
- `app/core/chat_rate_limiting.py` - дублирует rate_limiting
- `app/core/cookie_auth.py` - неиспользуемая cookie аутентификация
- `app/core/csrf.py` - неиспользуемая CSRF защита
- `app/core/env.py` - дублирует config.py
- `app/core/limiting.py` - дублирует rate_limiting
- `app/core/pagination.py` - неиспользуемая пагинация
- `app/core/passwords.py` - дублирует security.py
- `app/core/problem.py` - неиспользуемый problem handler
- `app/core/rate_limiting.py` - дублирует deps.py
- `app/core/s3_helpers.py` - дублирует s3.py
- `app/core/settings.py` - дублирует config.py
- `app/core/transactions.py` - неиспользуемые транзакции
- `app/core/upload_security.py` - неиспользуемая безопасность загрузки

### 2. Legacy задачи (0% покрытие, можно удалить)
- `app/tasks/normalize.py` - есть bg_tasks_enhanced
- `app/tasks/chunk.py` - есть bg_tasks_enhanced
- `app/tasks/embed.py` - есть bg_tasks_enhanced
- `app/tasks/index.py` - есть bg_tasks_enhanced
- `app/tasks/analyze.py` - есть bg_tasks_enhanced
- `app/tasks/upload_watch.py` - неиспользуемый watcher
- `app/tasks/ocr_tables.py` - неиспользуемый OCR
- `app/tasks/chat.py` - есть bg_tasks_enhanced
- `app/tasks/embedding_worker.py` - неиспользуемый worker
- `app/tasks/delete.py` - неиспользуемое удаление

### 3. Legacy клиенты (0% покрытие, можно удалить)
- `app/clients/qdrant_client.py` - неиспользуемый клиент
- `app/clients/emb_client.py` - есть в services
- `app/clients/llm_client.py` - есть в services

### 4. Legacy сервисы (0% покрытие, можно удалить)
- `app/services/adaptive_chunker.py` - неиспользуемый chunker
- `app/services/embedding_dispatcher.py` - неиспользуемый dispatcher
- `app/services/enhanced_text_extractor.py` - есть text_extractor
- `app/services/multi_index_search.py` - неиспользуемый поиск
- `app/services/permissions.py` - пустой модуль
- `app/services/reranker.py` - неиспользуемый reranker

## Модули для покрытия тестами (Приоритет)

### 1. Высокий приоритет (критические пути)
- `app/api/routers/auth.py` (25% → 80%)
- `app/api/routers/admin.py` (23% → 80%)
- `app/api/routers/rag.py` (22% → 80%)
- `app/api/routers/chats.py` (27% → 80%)
- `app/api/controllers/users.py` (45% → 80%)
- `app/api/controllers/chats.py` (56% → 80%)
- `app/api/controllers/rag.py` (51% → 80%)

### 2. Средний приоритет
- `app/services/users_service_enhanced.py` (42% → 80%)
- `app/services/chats_service_enhanced.py` (53% → 80%)
- `app/services/rag_service_enhanced.py` (49% → 80%)
- `app/repositories/users_repo_enhanced.py` (55% → 80%)
- `app/repositories/chats_repo_enhanced.py` (56% → 80%)
- `app/repositories/rag_repo_enhanced.py` (55% → 80%)

### 3. Низкий приоритет
- `app/tasks/bg_tasks_enhanced.py` (50% → 80%)
- `app/tasks/task_manager.py` (32% → 80%)
- `app/tasks/periodic_tasks.py` (50% → 80%)

## План действий

### Этап 1: Очистка legacy кода
1. Удалить все модули с 0% покрытием из списка выше
2. Обновить импорты в main_enhanced.py
3. Проверить что ничего не сломалось

### Этап 2: Покрытие критических путей
1. Добавить тесты для auth роутера
2. Добавить тесты для admin роутера
3. Добавить тесты для rag роутера
4. Добавить тесты для chats роутера

### Этап 3: Покрытие сервисов и репозиториев
1. Добавить тесты для users_service_enhanced
2. Добавить тесты для chats_service_enhanced
3. Добавить тесты для rag_service_enhanced
4. Добавить тесты для репозиториев

### Этап 4: Покрытие фоновых задач
1. Добавить тесты для bg_tasks_enhanced
2. Добавить тесты для task_manager
3. Добавить тесты для periodic_tasks

## Ожидаемый результат

После выполнения плана:
- **Покрытие**: 80%+ (с 38%)
- **Удалено**: ~2000 строк legacy кода
- **Добавлено**: ~1000 строк тестов
- **Чистота кода**: Убраны дубликаты и неиспользуемые модули
