# ML Portal Documentation

## Quick Start
- [Project Overview](0.DESCRIPTION.md) — что это и как работает
- [Platform Overview](PLATFORM_OVERVIEW.md) — бизнес-логика и архитектура крупными мазками
- [Project Concept](CONCEPT.md) — продуктовый и технический концепт развития
- [Backend Architecture](2.ARCHITECTURE.md) — техническая архитектура backend (FastAPI, SQLAlchemy, agents runtime)
- [Frontend Architecture](2.FRONTEND_ARCHITECTURE.md) — техническая архитектура frontend (React, TanStack Query, SSE)
- [Admin Panel](ADMIN_STRUCTURE.md) — структура админки
- [Glossary](GLOSSARY.md) — термины и определения

## Role-based Guides
- [User Guide](guides/USER_GUIDE.md) — что может пользователь и как эффективно работать
- [Admin Guide](guides/ADMIN_GUIDE.md) — как управлять платформой и доступами
- [AI Engineer Guide](guides/AI_ENGINEER_GUIDE.md) — runtime/data flow/contracts для инженерного контура

## Development  
- [Backend Rules](backend/RULES.md) — правила разработки бэкенда
- [Backend Patterns](backend/PATTERNS.md) — паттерны и лучшие практики
- [Tool Developer Guide](backend/TOOL_DEVELOPER_GUIDE.md) — как добавлять новые backend tools
- [Tool Developer Rules](backend/TOOL_DEVELOPER_RULES.md) — обязательные требования для tool-разработки
- [Frontend Rules](frontend/RULES.md) — правила разработки фронтенда
- [Frontend Patterns](frontend/PATTERNS.md) — паттерны и лучшие практики

## Deployment
- [DevOps Guide](1.DEVOPS.md) — развертывание и инфраструктура

## Architecture Deep Dive
- [Data Model](architecture/DATA_MODEL.md) — модели данных
- [Collection Asset Refactor](architecture/COLLECTION_ASSET_REFACTOR.md) — целевая модель collection/instance/runtime binding
- [Agent Runtime](architecture/AGENT_RUNTIME.md) — система выполнения агентов
- [Flows](architecture/FLOWS.md) — связывающие runtime-флоу
- [Chat File Attachments](architecture/CHAT_FILE_ATTACHMENTS.md) — файловый контур чата и генерации файлов ответа
