# ML Portal Concept

## 1) Что мы строим

**ML Portal** — корпоративная AI-платформа с управляемыми агентами, где каждый тенант получает изолированную среду, но может безопасно использовать общие возможности платформы.

Ключевая идея: дать бизнес-командам не «еще один чат», а **настраиваемый слой автоматизации**:

- агент + инструменты + данные + политики,
- с контролем прав, версий и наблюдаемостью,
- с предсказуемым поведением в production.

## 2) Продуктовые принципы

1. **Safety first**: tenant isolation, RBAC, audit, encrypted credentials.
2. **Config over code**: максимум через админку/модели, минимум хардкода.
3. **Composable platform**: система собирается из стандартных блоков (агенты, промпты, tools, policies, limits).
4. **Graceful degradation**: агент может работать в partial-mode, если часть инструментов недоступна.
5. **Observable by default**: метрики, structured logs, routing/execution traces.

## 3) Технический концепт

### Ядро платформы

- **Agent Runtime**: tool-call loop + pre-runtime router.
- **RAG Pipeline**: ingestion/indexing/search как отдельный управляемый контур.
- **Policy Engine**: scope-based resolution (`User > Tenant > Default`).
- **Tool Connectivity**: tool instances + encrypted credential sets + health checks.

### Архитектурный контракт

- Backend: `API -> Service -> Repository`.
- Frontend: `Domain pages + shared/ui constructor`.
- Server state: TanStack Query, local UI state: Zustand.
- Единый API-client на фронте и единый transaction policy на бэке.

## 4) Ценность для бизнеса

1. Быстрый запуск новых AI-сценариев без релизов кода.
2. Контроль рисков (кто, что, когда, с какими правами и данными).
3. Снижение стоимости изменений за счет унифицированных паттернов.
4. Прозрачность эксплуатации (health, latency, errors, audit).

## 5) Ключевые ставки развития

1. **Платформенная зрелость**: стабильность, миграции, тесты, observability.
2. **Управляемость агентов**: версия/rollout/quality loop.
3. **Data + Tools reliability**: устойчивый ingestion и tool integrations.
4. **Admin UX как конструктор**: меньше кастомного кода, больше стандартных блоков.
5. **Enterprise readiness**: безопасность, SLO, эксплуатационные процедуры.

## 6) North Star и KPI

### North Star

**Доля задач, успешно завершенных агентами в рамках политики и SLA.**

### KPI (минимальный набор)

- Agent success rate (% успешных run).
- p95 latency (chat/tool/rag search).
- Tool availability (% аптайма инстансов).
- Error rate по типам (4xx/5xx/domain).
- Time-to-configure нового агента (от идеи до production).
- MTTR для инцидентов на critical flows.

## 7) Границы MVP и ближайшего этапа

В ближайшем цикле фокус не на «еще фичах», а на:

- стабилизации архитектурных контрактов,
- закрытии техдолга по транзакциям/миграциям/тестам,
- доведении admin UX до конструктора,
- измеримости качества через метрики и журналирование.
