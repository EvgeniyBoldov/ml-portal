# AI Engineering Sandbox - Техническое Задание

## Общая концепция

**Sandbox** - изолированная среда для AI инженеров, позволяющая тестировать, сравнивать и отлаживать агентов, инструменты и роутинг в безопасном окружении с реальными данными из production.

### 🚨 КРИТИЧЕСКОЕ ТРЕБОВАНИЕ БЕЗОПАСНОСТИ

**ABSOLUTE READ-ONLY RULE:** Из песочницы **КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО** любое изменение данных в production базе данных.

**ЕДИНСТВЕННЫЙ ИСКЛЮЧЕНИЕ:** Создание **НОВОЙ ВЕРСИИ** сущности на основе успешных тестов в песочнице:
- Можно создать новую версию агента/инструмента/промпта с параметрами, которые показали лучший результат
- Нельзя изменять существующие версии или данные
- Нельзя удалять или модифицировать production данные
- Все операции создания версий логируются и требуют подтверждения

**Security Model:** Production DB → Read-Only Access → Sandbox Testing → New Version Creation (if approved)

## Целевая аудитория

- **AI Engineers** - разработка и отладка агентов
- **Prompt Engineers** - тестирование промптов и версий
- **DevOps Engineers** - тестирование инструментов и интеграций
- **System Architects** - анализ производительности и сравнение подходов

## Core функциональность

### 1. 🚀 Запуск агента (Single Run)
**Цель:** Тестирование отдельного агента с кастомными параметрами

**Интерфейс:** 2-колоночный layout
- **Левая колонка:** Форма запуска
  - Выбор агента (autocomplete с поиском)
  - Выбор версии (dropdown с версиями)
  - Текст запроса (textarea)
  - Дополнительные параметры (JSON editor)
  - Кнопка "Запустить"
- **Правая колонка:** Результат выполнения
  - Ответ агента
  - Метрики выполнения (latency, tokens, cost)
  - Лог выполнения (step-by-step)
  - Использованные инструменты

**API интеграция:**
```typescript
POST /sandbox/agents/run
{
  agent_id: UUID,
  version: string,
  request_text: string,
  parameters?: Record<string, any>
}
```

### 2. 🔧 Запуск инструмента (Tool Run)
**Цель:** Тестирование отдельных инструментов с параметрами

**Интерфейс:** 2-колоночный layout
- **Левая колонка:** Форма запуска
  - Выбор инструмента (autocomplete)
  - Выбор версии (dropdown)
  - Параметры инструмента (dynamic form based on schema)
  - Кнопка "Выполнить"
- **Правая колонка:** Результат
  - Ответ инструмента
  - Метрики (execution time, success/failure)
  - Error details (если есть)

**API интеграция:**
```typescript
POST /sandbox/tools/run
{
  tool_id: UUID,
  version: string,
  parameters: Record<string, any>
}
```

### 3. 🎯 Запуск роутера агентов (Agent Router)
**Цель:** Тестирование логики выбора агента

**Интерфейс:** 2-колоночный layout
- **Левая колонка:** Форма роутинга
  - Текст запроса (textarea)
  - Фильтры: категория, тег, tenant
  - Настройки роутинга (strict/flexible mode)
  - Кнопка "Найти агента"
- **Правая колонка:** Результат роутинга
  - Выбранный агент
  - Альтернативные кандидаты
  - Score breakdown
  - Reasoning логика

**API интеграция:**
```typescript
POST /sandbox/agents/route
{
  request_text: string,
  category?: string,
  tag?: string,
  routing_mode: 'strict' | 'flexible'
}
```

### 4. 🔍 Сравнение запусков (A/B Testing)
**Цель:** Сравнение двух сценариев выполнения

**Интерфейс:** 3-колоночный layout
- **Колонка 1:** Первый сценарий
  - Форма запуска (агент/инструмент/роутер)
  - Результат выполнения
  - Метрики
- **Колонка 2:** Второй сценарий
  - Форма запуска (агент/инструмент/роутер)
  - Результат выполнения
  - Метрики
- **Колонка 3:** Дифф анализ
  - Сравнение ответов (diff view)
  - Сравнение метрик (chart)
  - Сравнение использованных инструментов
  - Cost/Performance анализ

**API интеграция:**
```typescript
POST /sandbox/compare
{
  scenario1: { type: 'agent'|'tool'|'router', ... },
  scenario2: { type: 'agent'|'tool'|'router', ... }
}
```

### 5. 📦 Версионирование и управление

**Цель:** Работа с разными версиями компонентов

**Функциональность:**
- **Version Switcher:** Выбор любой версии агента/инструмента
- **Version Comparison:** Сравнение версий side-by-side
- **Rollback Testing:** Тестирование откатов версий
- **Version Metrics:** История производительности по версиям

**Интерфейс компонента:**
```tsx
<VersionSelector
  entityType="agent" | "tool" | "collection"
  entityId={UUID}
  selectedVersion={string}
  onVersionChange={(version) => {}}
  showMetrics={boolean}
/>
```

### 6. 🔗 Интеграция с основными сущностями

**Цель:** Бесшовная интеграция с production данными

**Интегрируемые сущности:**
- **Агенты** (agents + versions + bindings)
- **Инструменты** (tools + versions + instances)
- **Коллекции** (collections + documents)
- **Промпты** (prompts + versions)
- **Политики** (policies + limits)
- **Инстансы** (instances + credentials)

**Точки входа в песочницу:**
- **Admin Layout:** Кнопка "🧪 Песочница"
- **Entity Pages:** Кнопка "Открыть в песочнице" на страницах:
  - Agent detail page
  - Tool detail page
  - Collection detail page
  - Prompt detail page

**🚨 SECURITY FLOW:**
```
Production Entity (Read-Only) → Sandbox Testing → Compare Results → Create New Version (Optional)
```

**Version Creation из песочницы:**
- Только после успешного A/B тестирования
- Кнопка "Создать версию" появляется только при улучшении метрик
- Требует подтверждения и комментария почему версия лучше
- Автоматически переносит успешные параметры в новую версию

## Архитектура решения

### Frontend Architecture

**Domain Structure:**
```
src/domains/sandbox/
├── layouts/
│   ├── SandboxLayout.tsx          # Основной лейаут
│   └── components/
│       ├── RunPanel.tsx           # Панель запуска
│       ├── ResultPanel.tsx        # Панель результатов
│       ├── ComparePanel.tsx       # Панель сравнения
│       └── VersionSelector.tsx    # Селектор версий
├── pages/
│   ├── AgentRunPage.tsx           # Запуск агента
│   ├── ToolRunPage.tsx            # Запуск инструмента
│   ├── RouterPage.tsx             # Тестирование роутера
│   └── ComparePage.tsx            # Сравнение сценариев
├── components/
│   ├── RunForm.tsx                # Форма запуска
│   ├── ResultView.tsx             # View результата
│   ├── DiffView.tsx               # Diff сравнение
│   └── MetricsChart.tsx           # Графики метрик
└── hooks/
    ├── useSandboxRun.ts           # Хук запуска
    ├── useSandboxCompare.ts       # Хук сравнения
    └── useVersionSelector.ts      # Хук версий
```

**Progressive Loading Strategy:**
```typescript
// Lazy loading по доменам
const SandboxLayout = lazy(() => import('@/domains/sandbox/layouts/SandboxLayout'));
const AgentRunPage = lazy(() => import('@/domains/sandbox/pages/AgentRunPage'));
const ToolRunPage = lazy(() => import('@/domains/sandbox/pages/ToolRunPage'));
const RouterPage = lazy(() => import('@/domains/sandbox/pages/RouterPage'));
const ComparePage = lazy(() => import('@/domains/sandbox/pages/ComparePage'));
```

### Backend Architecture

**API Endpoints:**
```python
# Sandbox API routes (READ-ONLY)
@router.post("/sandbox/agents/run")
async def run_agent_sandbox(request: AgentRunRequest) -> AgentRunResponse

@router.post("/sandbox/tools/run") 
async def run_tool_sandbox(request: ToolRunRequest) -> ToolRunResponse

@router.post("/sandbox/agents/route")
async def route_agents_sandbox(request: AgentRouteRequest) -> AgentRouteResponse

@router.post("/sandbox/compare")
async def compare_scenarios(request: CompareRequest) -> CompareResponse

@router.get("/sandbox/entities/{entity_type}/{entity_id}/versions")
async def get_entity_versions(entity_type: str, entity_id: UUID) -> List[Version]

# 🚨 ЕДИНСТВЕННЫЙ WRITE ENDPOINT - создание новой версии
@router.post("/sandbox/entities/{entity_type}/{entity_id}/versions")
async def create_entity_version(
    entity_type: str, 
    entity_id: UUID, 
    request: CreateVersionRequest
) -> VersionResponse:
    # ТОЛЬКО если sandbox testing показал улучшение
    # Audit logging + approval required
    pass
```

**Services Layer:**
```python
# Sandbox services
class SandboxAgentService:
    async def run_agent(self, request: AgentRunRequest) -> AgentRunResponse
    async def get_agent_versions(self, agent_id: UUID) -> List[AgentVersion]

class SandboxToolService:
    async def run_tool(self, request: ToolRunRequest) -> ToolRunResponse
    async def get_tool_versions(self, tool_id: UUID) -> List[ToolVersion]

class SandboxCompareService:
    async def compare_scenarios(self, request: CompareRequest) -> CompareResponse
    async def generate_diff(self, result1: Any, result2: Any) -> DiffResult
```

### Database Integration

**Read-Only Access:**
```python
# Sandbox использует production DB в read-only режиме
class SandboxRepository:
    async def get_agent(self, agent_id: UUID) -> Agent
    async def get_agent_version(self, agent_id: UUID, version: str) -> AgentVersion
    async def get_tool(self, tool_id: UUID) -> Tool
    async def get_tool_version(self, tool_id: UUID, version: str) -> ToolVersion
    # ... другие сущности
```

## UI/UX Design Principles

### Layout Patterns

**Single Run Layout (2 columns):**
```
┌─────────────────┬─────────────────┐
│   Run Form      │   Result View   │
│   (400px)       │   (flex)        │
│                 │                 │
│ • Entity Select │ • Response      │
│ • Version       │ • Metrics       │
│ • Parameters    │ • Execution Log │
│ • Run Button    │ • Tools Used    │
└─────────────────┴─────────────────┘
```

**Compare Layout (3 columns):**
```
┌─────────┬─────────┬─────────────────┐
│ Scenario│ Scenario│   Diff Analysis │
│   1     │   2     │                 │
│ (350px) │ (350px) │   (flex)        │
│         │         │                 │
│ • Form  │ • Form  │ • Response Diff │
│ • Result│ • Result│ • Metrics Chart │
│ • Metrics│ • Metrics│ • Cost Analysis│
└─────────┴─────────┴─────────────────┘
```

### Design System Integration

**Используемые компоненты:**
- `EntityPageV2` - для layout страниц
- `ContentBlock` - для секций
- `DataTable` - для списков сущностей
- `FormField` - для форм параметров
- `Badge` - для статусов и меток
- `Button` - для действий
- `Input/Textarea/Select` - для форм

**Новые компоненты:**
- `VersionSelector` - выбор версий
- `DiffView` - сравнение текстов
- `MetricsChart` - графики метрик
- `RunPanel` - панель запуска
- `ResultPanel` - панель результатов

## Security & Permissions

### Access Control

**Role-based Access:**
```typescript
// Только пользователи с правами admin/sandbox
const SandboxGuard = ({ children }) => {
  const { user } = useAuth();
  
  if (!hasRole(user, ['admin', 'sandbox_engineer'])) {
    return <Navigate to="/admin" />;
  }
  
  return children;
};
```

**Data Isolation:**
- **STRICT READ-ONLY** доступ к production данным
- **КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО** любые write операции в production
- **ЕДИНСТВЕННОЕ ИСКЛЮЧЕНИЕ:** создание новой версии через специальный endpoint
- Изолированная execution environment
- Audit логирование всех sandbox операций
- **Double confirmation** для любой операции создания версии

**Version Creation Security:**
```python
class VersionCreationService:
    async def create_version_from_sandbox(
        self, 
        entity_type: str,
        entity_id: UUID,
        sandbox_result: SandboxResult,
        user: User
    ) -> Version:
        # 1. Verify sandbox testing showed improvement
        if not sandbox_result.is_improvement:
            raise SecurityException("No improvement detected")
        
        # 2. Require double confirmation
        if not user.confirmed_twice:
            raise SecurityException("Double confirmation required")
        
        # 3. Audit log
        await audit_service.log_version_creation(
            entity_type, entity_id, sandbox_result, user
        )
        
        # 4. Create new version (ONLY operation)
        return await version_service.create_new_version(...)
```

### Rate Limiting

**Limits:**
```python
# Ограничения для sandbox API
SANDBOX_RATE_LIMITS = {
    "agent_run": "10/minute",
    "tool_run": "20/minute", 
    "router_test": "15/minute",
    "compare": "5/minute",
    "version_creation": "1/hour"  # 🚨 СТРОГО ОГРАНИЧЕНО
}
```

## Performance Requirements

### Loading Performance

**Bundle Sizes:**
- Sandbox domain: ~1.8MB (lazy loaded)
- Individual pages: ~300KB each
- Total cached: ~2.5MB after first use

**Loading Strategy:**
```typescript
// Progressive loading
const preloadSandbox = () => {
  import('@/domains/sandbox/layouts/SandboxLayout');
};

// Preload на hover
<Button 
  onMouseEnter={preloadSandbox}
  onClick={() => navigate('/sandbox')}
>
  🧪 Песочница
</Button>
```

### Runtime Performance

**Response Times:**
- Agent run: < 5 seconds
- Tool execution: < 2 seconds  
- Router test: < 1 second
- Compare analysis: < 3 seconds

**Caching Strategy:**
- Entity metadata: 5 minutes cache
- Version lists: 10 minutes cache
- Run results: 30 minutes cache
- Compare results: 15 minutes cache

## Implementation Phases

### Phase 1: Foundation (Week 1-2)
- [x] Создание sandbox домена
- [x] Progressive loading setup
- [ ] Basic SandboxLayout
- [ ] AgentRunPage (single run)
- [ ] Integration с агентами

### Phase 2: Core Features (Week 3-4)
- [ ] ToolRunPage
- [ ] RouterPage  
- [ ] VersionSelector component
- [ ] Basic metrics collection

### Phase 3: Advanced Features (Week 5-6)
- [ ] ComparePage (A/B testing)
- [ ] DiffView component
- [ ] MetricsChart component
- [ ] Advanced filtering

### Phase 4: Integration & Polish (Week 7-8)
- [ ] Integration buttons в admin pages
- [ ] Performance optimization
- [ ] Error handling & edge cases
- [ ] Documentation & testing

## Success Metrics

### User Experience
- **Loading Time:** Sandbox < 3 seconds
- **Run Execution:** Agent run < 5 seconds
- **User Satisfaction:** > 4.5/5 rating

### Business Impact
- **Development Speed:** 30% faster agent testing
- **Quality Improvement:** 25% fewer bugs in production
- **Cost Optimization:** 20% better prompt efficiency

### Technical Metrics
- **Bundle Size:** Sandbox domain < 2MB
- **API Response:** 95% < 1 second
- **Uptime:** 99.9% availability

---

**Status:** Ready for implementation  
**Priority:** P1 (High)  
**Estimated Effort:** 8 weeks  
**Team:** 1-2 developers
