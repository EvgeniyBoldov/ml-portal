"""Setup agents, prompts, and policies

Revision ID: 0051
Revises: 0050
Create Date: 2025-01-29

Creates:
- System prompts for agents (rag-assistant, data-analyst, general-assistant)
- Policies (standard, strict)
- Updates agents with proper bindings
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime


revision = "0051"
down_revision = "0050_tool_schema_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.utcnow()
    
    # =========================================================================
    # 1. CLEANUP OLD DATA
    # =========================================================================
    
    # Delete old test prompt
    conn.execute(sa.text("DELETE FROM prompts WHERE slug = 'agent.test'"))
    
    # =========================================================================
    # 2. CREATE SYSTEM PROMPTS (with versions)
    # =========================================================================
    
    # RAG Assistant prompt
    rag_prompt_id = uuid.uuid4()
    rag_version_id = uuid.uuid4()
    conn.execute(
        sa.text("""
            INSERT INTO prompts (id, slug, name, description, type, created_at, updated_at)
            VALUES (:id, :slug, :name, :description, :type, :created_at, :updated_at)
        """),
        {
            "id": rag_prompt_id,
            "slug": "system.rag-assistant",
            "name": "RAG Assistant System Prompt",
            "description": "Системный промт для RAG ассистента",
            "type": "system",
            "created_at": now,
            "updated_at": now,
        }
    )
    conn.execute(
        sa.text("""
            INSERT INTO prompt_versions (id, prompt_id, template, version, status, created_at, updated_at)
            VALUES (:id, :prompt_id, :template, :version, :status, :created_at, :updated_at)
        """),
        {
            "id": rag_version_id,
            "prompt_id": rag_prompt_id,
            "template": """Ты — интеллектуальный ассистент с доступом к базе знаний компании.

## Твои возможности
- Поиск информации в базе знаний с помощью инструмента rag.search
- Ответы на вопросы на основе найденных документов
- Цитирование источников

## Правила работы
1. ВСЕГДА используй rag.search для поиска релевантной информации перед ответом
2. Если информация не найдена — честно скажи об этом
3. Цитируй источники в формате [Документ: название]
4. Отвечай на языке пользователя
5. Будь точным и конкретным

## Формат ответа
- Краткий ответ на вопрос
- Детали из найденных документов
- Ссылки на источники""",
            "version": 1,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
    )
    
    # Data Analyst prompt
    data_prompt_id = uuid.uuid4()
    data_version_id = uuid.uuid4()
    conn.execute(
        sa.text("""
            INSERT INTO prompts (id, slug, name, description, type, created_at, updated_at)
            VALUES (:id, :slug, :name, :description, :type, :created_at, :updated_at)
        """),
        {
            "id": data_prompt_id,
            "slug": "system.data-analyst",
            "name": "Data Analyst System Prompt",
            "description": "Системный промт для аналитика данных",
            "type": "system",
            "created_at": now,
            "updated_at": now,
        }
    )
    conn.execute(
        sa.text("""
            INSERT INTO prompt_versions (id, prompt_id, template, version, status, created_at, updated_at)
            VALUES (:id, :prompt_id, :template, :version, :status, :created_at, :updated_at)
        """),
        {
            "id": data_version_id,
            "prompt_id": data_prompt_id,
            "template": """Ты — аналитик данных с доступом к структурированным коллекциям данных.

## Твои возможности
- Поиск записей: collection.search (с фильтрами и текстовым поиском)
- Получение записи по ID: collection.get
- Агрегации и статистика: collection.aggregate (count, sum, avg, min, max)

## Правила работы
1. Уточни, какую коллекцию использовать, если не указано
2. Используй фильтры для точного поиска
3. Для статистики используй collection.aggregate
4. Ограничивай выборки разумным лимитом (10-50 записей)
5. Форматируй данные в читаемом виде

## Формат фильтров DSL
```json
{
  "and": [
    {"field": "status", "op": "eq", "value": "open"},
    {"field": "priority", "op": "in", "value": ["high", "critical"]}
  ]
}
```

## Доступные операторы
- eq, neq — равно / не равно
- in, not_in — в списке / не в списке
- gt, gte, lt, lte — сравнение
- like, contains — текстовый поиск
- range — диапазон {"gte": 10, "lt": 100}
- is_null — проверка на null""",
            "version": 1,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
    )
    
    # General Assistant prompt
    general_prompt_id = uuid.uuid4()
    general_version_id = uuid.uuid4()
    conn.execute(
        sa.text("""
            INSERT INTO prompts (id, slug, name, description, type, created_at, updated_at)
            VALUES (:id, :slug, :name, :description, :type, :created_at, :updated_at)
        """),
        {
            "id": general_prompt_id,
            "slug": "system.general-assistant",
            "name": "General Assistant System Prompt",
            "description": "Базовый системный промт",
            "type": "system",
            "created_at": now,
            "updated_at": now,
        }
    )
    conn.execute(
        sa.text("""
            INSERT INTO prompt_versions (id, prompt_id, template, version, status, created_at, updated_at)
            VALUES (:id, :prompt_id, :template, :version, :status, :created_at, :updated_at)
        """),
        {
            "id": general_version_id,
            "prompt_id": general_prompt_id,
            "template": """Ты — универсальный ассистент.

## Правила
1. Отвечай кратко и по существу
2. Используй язык пользователя
3. Если не знаешь ответ — скажи об этом
4. Будь вежливым и профессиональным""",
            "version": 1,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
    )
    
    # =========================================================================
    # 3. UPDATE POLICIES
    # =========================================================================
    
    # Standard policy (update existing default)
    conn.execute(
        sa.text("""
            UPDATE policies SET
                name = 'Standard Policy',
                description = 'Стандартная политика для большинства агентов',
                max_steps = 10,
                max_tool_calls = 20,
                max_wall_time_ms = 60000,
                tool_timeout_ms = 30000,
                max_retries = 2,
                updated_at = :updated_at
            WHERE slug = 'default'
        """),
        {"updated_at": now}
    )
    
    # Strict policy
    strict_policy_id = uuid.uuid4()
    conn.execute(
        sa.text("""
            INSERT INTO policies (id, slug, name, description, max_steps, max_tool_calls, max_wall_time_ms, tool_timeout_ms, max_retries, created_at, updated_at)
            VALUES (:id, :slug, :name, :description, :max_steps, :max_tool_calls, :max_wall_time_ms, :tool_timeout_ms, :max_retries, :created_at, :updated_at)
        """),
        {
            "id": strict_policy_id,
            "slug": "strict",
            "name": "Strict Policy",
            "description": "Строгая политика с ограничениями для production",
            "max_steps": 5,
            "max_tool_calls": 10,
            "max_wall_time_ms": 30000,
            "tool_timeout_ms": 15000,
            "max_retries": 1,
            "created_at": now,
            "updated_at": now,
        }
    )
    
    # =========================================================================
    # 4. GET POLICY ID
    # =========================================================================
    
    result = conn.execute(sa.text("SELECT id FROM policies WHERE slug = 'default'"))
    default_policy_id = result.scalar()
    
    # =========================================================================
    # 5. UPDATE AGENTS (bindings will be created via admin after tool_instances exist)
    # =========================================================================
    
    # Update chat-simple (no tools, just general assistant)
    conn.execute(
        sa.text("""
            UPDATE agents SET
                name = 'Простой чат',
                description = 'Базовый чат без инструментов',
                system_prompt_slug = 'system.general-assistant',
                policy_id = :policy_id,
                updated_at = :updated_at
            WHERE slug = 'chat-simple'
        """),
        {"policy_id": default_policy_id, "updated_at": now}
    )
    
    # Update chat-rag (RAG assistant)
    conn.execute(
        sa.text("""
            UPDATE agents SET
                name = 'RAG Ассистент',
                description = 'Ассистент с доступом к базе знаний',
                system_prompt_slug = 'system.rag-assistant',
                policy_id = :policy_id,
                updated_at = :updated_at
            WHERE slug = 'chat-rag'
        """),
        {"policy_id": default_policy_id, "updated_at": now}
    )
    
    # Update chat-collections (Data Analyst)
    conn.execute(
        sa.text("""
            UPDATE agents SET
                name = 'Аналитик данных',
                description = 'Ассистент для работы с коллекциями данных',
                system_prompt_slug = 'system.data-analyst',
                policy_id = :policy_id,
                updated_at = :updated_at
            WHERE slug = 'chat-collections'
        """),
        {"policy_id": default_policy_id, "updated_at": now}
    )


def downgrade() -> None:
    conn = op.get_bind()
    
    # Delete agent bindings
    conn.execute(sa.text("DELETE FROM agent_bindings"))
    
    # Delete new prompts
    conn.execute(sa.text("""
        DELETE FROM prompts WHERE slug IN (
            'system.rag-assistant',
            'system.data-analyst', 
            'system.general-assistant'
        )
    """))
    
    # Delete strict policy
    conn.execute(sa.text("DELETE FROM policies WHERE slug = 'strict'"))
    
    # Restore default policy name
    conn.execute(sa.text("""
        UPDATE policies SET name = 'Default Policy', config = '{}' WHERE slug = 'default'
    """))
