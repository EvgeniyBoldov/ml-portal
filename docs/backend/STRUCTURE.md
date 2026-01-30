# Структура Backend

## Общая структура

```
apps/api/src/app/
├── __init__.py
├── main.py              # FastAPI app entry point
├── celery_app.py        # Celery configuration
├── alembic.ini          # Alembic config
│
├── core/                # Configuration, middleware, errors
│   ├── config.py        # Settings from env
│   ├── database.py      # SQLAlchemy setup
│   ├── security.py      # JWT, password hashing
│   ├── middleware.py    # Request logging, CORS
│   └── exceptions.py    # Custom exceptions
│
├── models/              # SQLAlchemy models
│   ├── __init__.py      # All models export
│   ├── base.py          # Base model class
│   ├── user.py
│   ├── tenant.py
│   ├── agent.py
│   ├── prompt.py
│   ├── chat.py
│   ├── rag.py
│   ├── collection.py
│   ├── tool.py
│   ├── tool_instance.py
│   ├── permission_set.py
│   ├── credential_set.py
│   └── ...
│
├── schemas/             # Pydantic schemas
│   ├── __init__.py
│   ├── auth.py
│   ├── users.py
│   ├── agents.py
│   ├── prompts.py
│   ├── rag.py
│   └── ...
│
├── repositories/        # Data access layer
│   ├── __init__.py
│   ├── base.py          # BaseRepository
│   ├── user_repository.py
│   ├── agent_repository.py
│   └── ...
│
├── services/            # Business logic
│   ├── __init__.py
│   ├── _base.py         # BaseService
│   ├── agent_service.py
│   ├── prompt_service.py
│   ├── permission_service.py
│   ├── rag_upload_service.py
│   ├── rag_ingest_service.py
│   ├── rag_search_service.py
│   ├── chat_stream_service.py
│   └── ...
│
├── api/                 # FastAPI routers
│   ├── deps.py          # Dependencies (get_db, get_user)
│   ├── deps_authz.py    # Authorization deps
│   ├── v1/              # API v1 endpoints
│   │   ├── __init__.py
│   │   ├── router.py    # Main router
│   │   ├── auth.py
│   │   ├── users.py
│   │   ├── agents.py
│   │   ├── prompts.py
│   │   ├── rag.py
│   │   ├── chats.py
│   │   └── admin/       # Admin endpoints
│   └── mcp/             # MCP protocol
│
├── agents/              # Agent Runtime
│   ├── __init__.py
│   ├── runtime.py       # AgentRuntime
│   ├── router.py        # AgentRouter
│   ├── context.py       # ToolContext
│   ├── registry.py      # ToolRegistry
│   ├── handlers/        # Tool handlers base
│   └── builtins/        # Built-in tools
│       ├── __init__.py
│       └── rag_search.py
│
├── workers/             # Celery tasks
│   ├── __init__.py
│   ├── rag_tasks.py     # RAG pipeline tasks
│   ├── collection_tasks.py
│   └── maintenance_tasks.py
│
├── adapters/            # External clients
│   ├── __init__.py
│   ├── llm_client.py    # LLM API client
│   ├── emb_client.py    # Embedding service client
│   ├── qdrant_client.py # Qdrant client
│   ├── s3_client.py     # MinIO/S3 client
│   └── redis_client.py  # Redis client
│
├── storage/             # File storage
│   └── s3.py
│
├── migrations/          # Alembic migrations
│   ├── env.py
│   └── versions/
│       ├── 0001_initial.py
│       ├── 0002_...py
│       └── ...
│
└── scripts/             # CLI scripts
    └── seed.py          # Initial data seeding
```

## Слои приложения

```
┌─────────────────────────────────────────────────────────────┐
│                         API Layer                            │
│                    (FastAPI Routers)                         │
│              Validation, Auth, Response formatting           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       Service Layer                          │
│                    (Business Logic)                          │
│           Orchestration, Transactions, Events                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Repository Layer                         │
│                    (Data Access)                             │
│              CRUD, Queries, flush() only                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       Model Layer                            │
│                   (SQLAlchemy Models)                        │
│              Schema, Relationships, Enums                    │
└─────────────────────────────────────────────────────────────┘
```

## Naming Conventions

| Тип | Формат | Пример |
|-----|--------|--------|
| Файлы | snake_case | `agent_service.py` |
| Классы | PascalCase | `AgentService` |
| Функции | snake_case | `get_agent_by_slug` |
| Константы | UPPER_SNAKE | `DEFAULT_PAGE_SIZE` |
| Модели | PascalCase singular | `Agent`, `User` |
| Таблицы | snake_case plural | `agents`, `users` |

## Импорты

```python
# Стандартная библиотека
import uuid
from datetime import datetime
from typing import Optional

# Сторонние библиотеки
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Локальные модули
from app.models import Agent, User
from app.services import AgentService
from app.api.deps import get_db, get_current_user
```
