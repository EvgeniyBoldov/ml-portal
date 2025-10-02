# План достижения 100% покрытия кода тестами

## 📊 Текущее состояние
- **Проходящие тесты**: 14/26 (54%)
- **Цель**: 100% покрытие кода

## 🎯 Этапы выполнения

### Этап 1: Исправление существующих ошибок
1. **UsersService** - исправить инициализацию с tenant_id
2. **Repositories** - исправить сигнатуры методов
3. **API endpoints** - найти правильные пути

### Этап 2: Покрытие всех сервисов
- [ ] `analyze_service.py` - AnalyzeService
- [ ] `audit_service.py` - AuditService  
- [ ] `chats_service.py` - ChatsService
- [ ] `clients.py` - Clients
- [ ] `idempotency_service.py` - IdempotencyService
- [ ] `jobs_service.py` - JobsService
- [ ] `model_catalog.py` - ModelCatalog
- [ ] `rag_ingest_service.py` - RagIngestService
- [ ] `rag_search_service.py` - RagSearchService
- [ ] `rag_service.py` - RagService
- [ ] `service_with_idempotency.py` - ServiceWithIdempotency
- [ ] `tenants_service.py` - TenantsService
- [ ] `text_extractor.py` - TextExtractor
- [ ] `text_normalizer.py` - TextNormalizer

### Этап 3: Покрытие всех репозиториев
- [ ] `analyze_repo.py` - AnalyzeRepository
- [ ] `chats_repo.py` - ChatsRepository
- [ ] `documents_repo.py` - DocumentsRepository
- [ ] `factory.py` - RepositoryFactory
- [ ] `idempotency_repo.py` - IdempotencyRepository
- [ ] `jobs_repo.py` - JobsRepository
- [ ] `tenants_repo.py` - TenantsRepository

### Этап 4: Покрытие всех API endpoints
- [ ] `admin.py` - Admin endpoints
- [ ] `analyze.py` - Analyze endpoints
- [ ] `artifacts.py` - Artifacts endpoints
- [ ] `auth.py` - Auth endpoints
- [ ] `chat.py` - Chat endpoints
- [ ] `models.py` - Models endpoints
- [ ] `rag.py` - RAG endpoints
- [ ] `security.py` - Security endpoints
- [ ] `users.py` - Users endpoints

### Этап 5: Покрытие всех утилит и адаптеров
- [ ] `adapters/` - Все адаптеры
- [ ] `core/` - Все core модули
- [ ] `utils/` - Все утилиты
- [ ] `workers/` - Все воркеры

### Этап 6: Покрытие моделей и схем
- [ ] `models/` - Все модели
- [ ] `schemas/` - Все схемы

## 🚀 Начинаем выполнение
