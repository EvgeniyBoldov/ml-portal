# Product Vision

## Назначение

**ML Portal** — локальный корпоративный AI-ассистент для департаментов компании.

### Ключевая идея
Каждый департамент (отдел) работает как отдельный тенант со своими настройками, но имеет доступ к общим ресурсам и данным других департаментов через систему политик доступа.

### Целевая аудитория
- **Конечные пользователи**: сотрудники департаментов, использующие AI-агентов для решения задач
- **Админы департаментов**: настраивают агентов, инструменты и доступы для своего отдела
- **AI-инженеры**: создают промпты, агентов, интеграции, проводят A/B тестирование
- **Системные администраторы**: управляют общими настройками, политиками, инфраструктурой

## Основные сценарии

### 1. Cross-department collaboration
Сетевой инженер может запросить данные у виртуализации через агента, если политики доступа это разрешают.

### 2. Hierarchical access
Руководитель департамента имеет доступ ко всем данным подчиненных отделов.

### 3. Flexible tooling
Агент для анализа Jira-тикетов использует креды с более высокими правами (tenant/default), чем личные креды пользователя.

### 4. Graceful degradation
Если у пользователя нет доступа к рекомендованному инструменту, агент продолжает работу с предупреждением о возможных неточностях.

## Архитектурные принципы

### 1. Scope-based isolation
Все сущности (инстансы, креды, политики) имеют scope: `default` → `tenant` → `user`.

### 2. Policy-driven access
Доступ к инструментам и коллекциям определяется политиками с приоритетом: User > Tenant > Default.

### 3. Composable agents
Агент = Prompt + Baseline + Tools + Collections + Policy.

### 4. Credential resolution
Для каждого инструмента система выбирает креды по приоритету: user → tenant → default.

### 5. Versioned prompts
Промпты и Baseline версионируются (draft/active/archived) для контроля изменений.

## Технологический стек

### Backend
- **FastAPI** — API layer
- **PostgreSQL** — основная БД
- **Qdrant** — векторное хранилище
- **Redis** — кэш и очереди
- **Celery** — фоновые задачи
- **MinIO/S3** — хранение файлов

### Frontend
- **React 18 + TypeScript + Vite**
- **React Router** — маршрутизация
- **TanStack Query** — серверное состояние
- **Zustand** — локальное UI состояние
- **CSS Modules** — стилизация
- **SSE** — real-time обновления

### Infrastructure
- **Docker + Docker Compose** — локальная разработка
- **Kubernetes** — production deployment
- **Prometheus + Grafana** — мониторинг
- **Loki** — логирование

## Roadmap

### Phase 1: Foundation (Current)
- ✅ Базовая мультитенантность
- ✅ Agent Runtime с tool-call loop
- ✅ RAG pipeline
- ✅ Permission system
- ⚠️ Baseline prompts
- ⚠️ Cross-tenant access policies

### Phase 2: Admin Experience
- 🔲 Unified DataTable component
- 🔲 Dashboard с метриками
- 🔲 A/B testing промптов
- 🔲 Audit trail UI
- 🔲 Agent versioning

### Phase 3: Advanced Features
- 🔲 RBAC на UI level
- 🔲 Notifications для health checks
- 🔲 Rate limiting per tenant
- 🔲 Template marketplace
- 🔲 Advanced analytics

## Метрики успеха

### User adoption
- Количество активных пользователей в день
- Количество запросов к агентам
- Retention rate

### System health
- Uptime агентов
- Success rate tool calls
- P95 latency ответов

### Business value
- Время решения задач (до/после AI)
- Количество автоматизированных процессов
- User satisfaction score
