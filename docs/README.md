# ML Portal Documentation

Open work and unresolved architectural questions are tracked in the [root TODO](../TODO.md).
Documents below describe current behavior and contracts. For a cross-domain technical orientation, start with the [Architecture Map](architecture/ARCHITECTURE_MAP.md); read the linked owning contract for details.


## Start Here
- [Platform Overview](PLATFORM_OVERVIEW.md) — обзор платформы и бизнес-контуров
- [Корпоративный глоссарий](GLOSSARY.md) — определения из документов
- [Термины разработки](DEVELOPER_TERMS.md) — понятия реализации портала

## Admin Guides
- [Admin Docs Index](admin/README.md) — навигация для администраторов
- [Environment Setup](admin/ENV.md) — как подготовить `.env`
- [Build Guide](admin/BUILD.md) — как собрать сервисы
- [Run Guide](admin/RUN.md) — как запускать и останавливать стенд

## Role-based Guides
- [User Guide](guides/USER_GUIDE.md) — работа пользователя в системе
- [Admin Guide](guides/ADMIN_GUIDE.md) — управление доступами и эксплуатацией
- [AI Engineer Guide](guides/AI_ENGINEER_GUIDE.md) — runtime/data/tool контуры

## Architecture

### Orientation and core model
- [Architecture Map](architecture/ARCHITECTURE_MAP.md) — system boundaries, invariants and source-of-truth map
- [Data Model](architecture/DATA_MODEL.md) — canonical entities and relationships
- [Flows](architecture/FLOWS.md) — lifecycle, routing and integration flows
- [ADR: TurnPreflight Routing](architecture/ADR_TURN_PREFLIGHT_ROUTING.md) — accepted routing decision
- [ADR: RootRoutePolicy Recommendation](architecture/ADR_ROOT_ROUTE_RECOMMENDATION.md) — proposed advisory policy contract; TurnPreflight remains final router
- [ADR: Runtime Trace Entity Tree](architecture/ADR_RUNTIME_TRACE_ENTITY_TREE.md) — accepted trace hierarchy decision

### Runtime and chat
- [Agent Runtime](architecture/AGENT_RUNTIME.md)
- [Runtime Interactions](architecture/RUNTIME_INTERACTIONS.md) — clarification, confirmation and resume contract
- [Runtime Tool Results and Data Workspace](architecture/RUNTIME_TOOL_RESULTS.md)
- [Runtime Trace Specification](architecture/RUNTIME_TRACE_SPEC.md)
- [Sandbox Trace Architecture Review](architecture/SANDBOX_TRACE_ARCHITECTURE_REVIEW.md) — findings, contract gaps and acceptance criteria for the sandbox trace/inspectors
- [Chat Context Memory](architecture/CHAT_CONTEXT_MEMORY.md)
- [Chat File Attachments](architecture/CHAT_FILE_ATTACHMENTS.md)
- [Chat Runtime Error Contract](architecture/CHAT_RUNTIME_ERROR_CONTRACT.md)
- [SSE Status Streams](architecture/SSE_STATUS_STREAMS.md)
- [Sandbox Runtime](architecture/SANDBOX_RUNTIME.md)

### Identity, data and integrations
- [Authentication and Sessions](architecture/AUTHENTICATION.md)
- [Memory](architecture/MEMORY.md) — document LongMemory and dialog memory boundaries
- [Runtime Memory](architecture/RUNTIME_MEMORY.md)
- [Memory Risks and Accepted Decisions](architecture/MEMORY_RISKS.md)
- [File Data: Document-local Search](architecture/FILE_DATA.md)
- [MCP Credential Flow](architecture/MCP_CREDENTIAL_FLOW.md)
- [DCBox MCP](architecture/DCBOX_MCP.md)
- [ML Inference MCP](architecture/ML_INFERENCE_MCP.md)
- [Health Monitoring](architecture/HEALTH_MONITORING.md)
- [Collection Asset Refactor](architecture/COLLECTION_ASSET_REFACTOR.md)

## Development Rules
- [Repository Guidelines](../AGENTS.md) — руководство для участников и coding agents; команды, границы архитектуры и ссылки на правила
- [Testing](TESTING.md) — уровни тестов, размещение и обычный цикл проверки
- [Backend Rules](backend/RULES.md)
- [Backend Patterns](backend/PATTERNS.md)
- [Tool Developer Guide](backend/TOOL_DEVELOPER_GUIDE.md)
- [Tool Developer Rules](backend/TOOL_DEVELOPER_RULES.md)
- [Frontend Rules](frontend/RULES.md)
- [Frontend Patterns](frontend/PATTERNS.md)

## Implementation Notes
- [Base Functionality](implementation/base-functionality/)
