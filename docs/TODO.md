# TODO & Roadmap

Список задач для развития проекта.

## 🔴 High Priority (Критично для работы)

### Backend

- [x] **Baseline Prompts**: Добавить поддержку merge baseline промптов (default + agent)
  - ✅ Реализован `PromptService.merge_baselines()`
  - ✅ Обновлен `AgentService` для резолва baseline
  - ✅ Добавлено поле `baseline_prompt_id` в Agent модель (nullable, FK на prompts.id)

- [x] **Auto-add Permissions**: Автоматическое добавление новых Tool/Collection в default permissions
  - ✅ Хук в `ToolSyncService._create_tool()` → `_add_tool_to_default_permissions()`
  - ✅ Хук в `CollectionService.create_collection()` → `_add_collection_to_default_permissions()`
  - ✅ Статус по умолчанию: `denied`

- [x] **Credential Resolution**: Улучшить логику выбора credential set
  - ✅ Добавлено поле `is_default` в CredentialSet (миграция 0044)
  - ✅ `CredentialService.resolve_credentials()` использует `is_default=true`
  - ✅ `CredentialSetRepository.get_default_for_scope()` с fallback логикой

- [x] **Partial Mode Warning**: Уведомление пользователя о недоступных инструментах
  - ✅ `ExecutionRequest.partial_mode_warning` генерируется в `AgentRouter`
  - ✅ `AgentRuntime.run_with_request()` выводит warning через `RuntimeEvent.status()`

### Frontend

- [x] **DataTable Component**: Создать переиспользуемый компонент таблицы
  - ✅ `shared/ui/DataTable/DataTable.tsx` с selection, search, pagination
  - ⚠️ Не использует TanStack Table (custom implementation)
  - ⚠️ Нужно заменить кастомные таблицы на DataTable

- [x] **Defaults Page**: Страница общих настроек
  - ✅ `DefaultsPage.tsx` создана с базовым функционалом
  - ⚠️ Нужно добавить: Default Baseline выбор
  - ⚠️ Нужно добавить: Context Variables
  - ⚠️ Нужно добавить: редактирование Default Permissions

- [ ] **Prompt Detail Page**: Рефакторинг детального вида промпта
  - 3-блочный layout (info + versions + history)
  - Таблица версий с переключением
  - Audit log в нижнем блоке

- [ ] **Agent Editor**: Улучшить редактор агента
  - Добавить выбор Baseline Prompt
  - Модальное окно "Просмотр промпта" (с merged baseline)
  - Валидация required инструментов

### Database

- [x] **Migration**: Добавить `baseline_prompt_id` в таблицу `agents`
  - ✅ Миграция 0043: nullable FK на `prompts.id`
  - ⚠️ Constraint на type='baseline' проверяется в service layer

---

## 🟡 Medium Priority (Важно, но не блокирует)

### Backend

- [ ] **Agent Versioning**: Версионирование агентов (как у промптов)
  - Добавить `version`, `status`, `parent_version_id` в Agent
  - Миграция для существующих агентов (version=1, status=active)
  - API endpoints для создания версий

- [ ] **Audit Trail**: Расширить audit_logs для отслеживания изменений
  - Логировать изменения промптов/агентов/политик
  - Добавить `entity_type` и `entity_id` в AuditLog
  - UI для просмотра истории изменений

- [ ] **Health Check Notifications**: Уведомления при падении health check
  - Celery task для периодической проверки
  - Email/Webhook уведомления админам
  - UI индикатор в админке

- [ ] **Rate Limiting per Tenant**: Ограничение запросов по департаментам
  - Добавить `rate_limit_config` в Tenant модель
  - Middleware для проверки лимитов
  - Dashboard с метриками использования

### Frontend

- [ ] **Dashboard Metrics**: Дашборд со статистикой
  - Подсчет сущностей по статусам
  - Ошибки за последние 24 часа
  - Графики (опционально)

- [ ] **Agent Runs Page**: Улучшить страницу логов запусков
  - Фильтры по агенту/пользователю/статусу/дате
  - Timeline шагов выполнения
  - Метрики (tokens, duration, tool calls)

- [ ] **Audit Page**: Страница audit logs
  - Фильтры по endpoint/методу/пользователю/статусу
  - Модальное окно с деталями (request/response)

- [ ] **RBAC на UI**: Скрывать элементы в зависимости от роли
  - `useRBAC()` hook
  - Компонент `<RequireRole role="admin">`
  - Скрывать кнопки/разделы для tenant_admin

### DevOps

- [ ] **Prometheus Metrics**: Экспорт метрик для мониторинга
  - Количество запросов к агентам
  - Latency LLM/Tool calls
  - Ошибки по типам

- [ ] **Loki Integration**: Интеграция логирования
  - Structured logging (JSON)
  - Correlation ID для трейсинга
  - UI для просмотра логов (опционально)

---

## 🟢 Low Priority (Хорошо бы иметь)

### Backend

- [ ] **Template Marketplace**: Библиотека готовых промптов/агентов
  - Таблица `prompt_templates` с категориями
  - API для импорта шаблонов
  - UI галерея шаблонов

- [ ] **Cost Tracking**: Отслеживание затрат на токены
  - Добавить `tokens_cost` в AgentRun
  - Pricing config для моделей
  - Dashboard с расходами по департаментам

- [ ] **Webhook Notifications**: Webhook для событий
  - Настройка webhook URL в Tenant
  - События: agent_run.completed, health_check.failed
  - Retry logic для failed webhooks

### Frontend

- [ ] **A/B Testing Prompts**: Инструмент для сравнения промптов
  - Страница `/admin/agents/:slug/test`
  - Side-by-side сравнение ответов
  - Метрики (tokens, duration, качество)
  - История тестов

- [ ] **CSV Export**: Экспорт данных из таблиц
  - Кнопка "Export CSV" в DataTable
  - Экспорт с учетом фильтров
  - Client-side генерация CSV

- [ ] **Bulk Actions**: Массовые действия в таблицах
  - Чекбоксы для выбора строк
  - Действия: Activate, Deactivate, Delete
  - Confirmation dialog

- [ ] **Advanced Filters**: Расширенные фильтры
  - Date range picker
  - Multi-select для статусов
  - Сохранение фильтров в URL

- [ ] **Dark Mode**: Темная тема
  - CSS variables для цветов
  - Переключатель в профиле
  - Сохранение в localStorage

### Testing

- [ ] **E2E Tests Coverage**: Расширить покрытие E2E тестов
  - Smoke test: login → create agent → chat → logout
  - Admin flow: create prompt → create agent → test
  - RAG flow: upload → ingest → search

- [ ] **Performance Tests**: Нагрузочное тестирование
  - Locust для API endpoints
  - Проверка latency при 100+ concurrent users
  - Проверка memory leaks

---

## 📝 Documentation

- [x] **Product Vision**: Общее видение продукта
- [x] **Data Model**: Описание моделей данных
- [x] **Admin Structure**: Структура админки
- [x] **Backend Architecture**: Архитектура бэкенда
- [x] **Frontend Architecture**: Архитектура фронтенда
- [ ] **API Documentation**: OpenAPI спецификация
- [ ] **Deployment Guide**: Инструкция по деплою
- [ ] **User Guide**: Руководство пользователя

---

## 🐛 Known Issues

### Backend

- [ ] **RAG Status Transitions**: Исправить валидацию переходов статусов
  - Проблема: IntegrityError при обновлении status
  - Решение: Использовать только валидные значения из StageStatus enum

- [ ] **Credential Encryption**: Ротация мастер-ключа
  - Добавить `CryptoService.rotate_key()`
  - CLI команда для ротации
  - Документация процесса

### Frontend

- [ ] **SSE Reconnection**: Улучшить логику переподключения
  - Exponential backoff
  - Максимум 5 попыток
  - UI индикатор состояния подключения

- [ ] **Query Cache Invalidation**: Оптимизировать инвалидацию кэша
  - Избегать лишних invalidateQueries
  - Использовать setQueryData где возможно
  - Проверить race conditions

---

## 💡 Ideas (Для обсуждения)

- **Multi-language Support**: i18n для интерфейса
- **Voice Input**: Голосовой ввод для чата
- **Mobile App**: React Native приложение
- **Plugin System**: Расширяемость через плагины
- **Collaborative Editing**: Совместное редактирование промптов
- **Version Diff**: Визуальное сравнение версий промптов
- **Prompt Suggestions**: AI-ассистент для написания промптов
- **Auto-optimization**: Автоматическая оптимизация промптов на основе метрик

---

## 📅 Milestones

### Q1 2026: Foundation Complete
- ✅ Agent Runtime с tool-call loop
- ✅ Permission system
- ✅ RAG pipeline
- ✅ Baseline prompts
- ✅ DataTable component
- ✅ Defaults page (базовая версия)

### Q2 2026: Admin Experience
- 🔲 A/B testing промптов
- 🔲 Dashboard с метриками
- 🔲 Audit trail UI
- 🔲 Agent versioning
- 🔲 Health check notifications

### Q3 2026: Advanced Features
- 🔲 RBAC на UI level
- 🔲 Rate limiting per tenant
- 🔲 Template marketplace
- 🔲 Cost tracking
- 🔲 Advanced analytics

### Q4 2026: Polish & Scale
- 🔲 Performance optimization
- 🔲 E2E tests coverage
- 🔲 Documentation complete
- 🔲 Production hardening
- 🔲 Multi-region deployment
