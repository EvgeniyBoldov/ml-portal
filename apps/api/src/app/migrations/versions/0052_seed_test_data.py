"""Seed test collection and RAG document

Revision ID: 0052
Revises: 0051
Create Date: 2025-01-29

Creates:
- Test collection 'tickets' with sample data
- Test RAG document
- Tool instances for collection and RAG
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime, timezone


revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc)
    
    # Get tenant_id
    result = conn.execute(sa.text("SELECT id FROM tenants WHERE name = 'default' LIMIT 1"))
    tenant_id = result.scalar()
    if not tenant_id:
        return
    
    # Get tool_group_id for 'collection'
    result = conn.execute(sa.text("SELECT id FROM tool_groups WHERE slug = 'collection'"))
    collection_group_id = result.scalar()
    
    # Get tool_group_id for 'rag'
    result = conn.execute(sa.text("SELECT id FROM tool_groups WHERE slug = 'rag'"))
    rag_group_id = result.scalar()
    
    # =========================================================================
    # 1. CREATE TEST COLLECTION 'tickets'
    # =========================================================================
    
    collection_id = uuid.uuid4()
    table_name = f"coll_{str(collection_id).replace('-', '_')[:8]}_tickets"
    
    # Create collection record
    conn.execute(
        sa.text("""
            INSERT INTO collections (
                id, tenant_id, slug, name, description, fields, table_name,
                primary_key_field, entity_type, allow_unfiltered_search, max_limit,
                created_at, updated_at
            ) VALUES (
                :id, :tenant_id, :slug, :name, :description, :fields, :table_name,
                :primary_key_field, :entity_type, :allow_unfiltered_search, :max_limit,
                :created_at, :updated_at
            )
        """),
        {
            "id": collection_id,
            "tenant_id": tenant_id,
            "slug": "tickets",
            "name": "IT Tickets",
            "description": "Тестовая коллекция IT-тикетов для демонстрации",
            "fields": """[
                {"name": "id", "type": "text", "required": true, "search_modes": ["exact"], "description": "Уникальный ID тикета"},
                {"name": "title", "type": "text", "required": true, "search_modes": ["exact", "like"], "description": "Заголовок тикета"},
                {"name": "description", "type": "text", "required": false, "search_modes": ["like"], "description": "Описание проблемы"},
                {"name": "status", "type": "text", "required": true, "search_modes": ["exact"], "description": "Статус: open, in_progress, resolved, closed"},
                {"name": "priority", "type": "text", "required": true, "search_modes": ["exact"], "description": "Приоритет: low, medium, high, critical"},
                {"name": "assignee", "type": "text", "required": false, "search_modes": ["exact", "like"], "description": "Ответственный"},
                {"name": "created_date", "type": "datetime", "required": true, "search_modes": ["exact", "range"], "description": "Дата создания"},
                {"name": "resolved_date", "type": "datetime", "required": false, "search_modes": ["exact", "range"], "description": "Дата решения"}
            ]""",
            "table_name": table_name,
            "primary_key_field": "id",
            "entity_type": "ticket",
            "allow_unfiltered_search": True,
            "max_limit": 100,
            "created_at": now,
            "updated_at": now,
        }
    )
    
    # Create the actual SQL table for collection data
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id VARCHAR(100) PRIMARY KEY,
            title VARCHAR(500) NOT NULL,
            description TEXT,
            status VARCHAR(50) NOT NULL,
            priority VARCHAR(50) NOT NULL,
            assignee VARCHAR(200),
            created_date TIMESTAMP WITH TIME ZONE NOT NULL,
            resolved_date TIMESTAMP WITH TIME ZONE
        )
    """))
    
    # Create ToolInstance for collection
    collection_instance_id = uuid.uuid4()
    if collection_group_id:
        conn.execute(
            sa.text("""
                INSERT INTO tool_instances (
                    id, slug, name, description, tool_group_id,
                    connection_config, instance_metadata, is_active,
                    created_at, updated_at
                ) VALUES (
                    :id, :slug, :name, :description, :tool_group_id,
                    :connection_config, :instance_metadata, :is_active,
                    :created_at, :updated_at
                )
            """),
            {
                "id": collection_instance_id,
                "slug": "collection-tickets",
                "name": "IT Tickets Collection",
                "description": "Коллекция IT-тикетов",
                "tool_group_id": collection_group_id,
                "connection_config": f'{{"collection_id": "{collection_id}"}}',
                "instance_metadata": '{"entity_type": "ticket", "row_count": 0}',
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        )
        
        # Link collection to tool_instance
        conn.execute(
            sa.text("UPDATE collections SET tool_instance_id = :instance_id WHERE id = :collection_id"),
            {"instance_id": collection_instance_id, "collection_id": collection_id}
        )
    
    # Insert sample tickets
    sample_tickets = [
        ("TKT-001", "Не работает VPN", "При подключении к VPN выдает ошибку 'Connection timeout'", "open", "high", "Иванов И.И.", "2025-01-15 10:00:00+03", None),
        ("TKT-002", "Запрос на новый ноутбук", "Нужен ноутбук для нового сотрудника отдела разработки", "in_progress", "medium", "Петров П.П.", "2025-01-16 14:30:00+03", None),
        ("TKT-003", "Проблема с принтером", "Принтер HP на 3 этаже не печатает", "resolved", "low", "Сидоров С.С.", "2025-01-10 09:00:00+03", "2025-01-12 16:00:00+03"),
        ("TKT-004", "Сбой в работе CRM", "CRM система недоступна для всего отдела продаж", "open", "critical", "Иванов И.И.", "2025-01-20 08:00:00+03", None),
        ("TKT-005", "Настройка почты", "Настроить корпоративную почту для нового сотрудника", "closed", "low", "Петров П.П.", "2025-01-05 11:00:00+03", "2025-01-05 15:00:00+03"),
    ]
    
    for ticket in sample_tickets:
        conn.execute(
            sa.text(f"""
                INSERT INTO {table_name} (id, title, description, status, priority, assignee, created_date, resolved_date)
                VALUES (:id, :title, :description, :status, :priority, :assignee, :created_date, :resolved_date)
            """),
            {
                "id": ticket[0],
                "title": ticket[1],
                "description": ticket[2],
                "status": ticket[3],
                "priority": ticket[4],
                "assignee": ticket[5],
                "created_date": ticket[6],
                "resolved_date": ticket[7],
            }
        )
    
    # Update row count
    conn.execute(
        sa.text("UPDATE collections SET row_count = 5, total_rows = 5 WHERE id = :id"),
        {"id": collection_id}
    )
    
    # =========================================================================
    # 2. CREATE TEST RAG DOCUMENT
    # =========================================================================
    
    # Check if rag_documents table exists
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'rag_documents'
        )
    """))
    rag_table_exists = result.scalar()
    
    if rag_table_exists and rag_group_id:
        rag_doc_id = uuid.uuid4()
        
        # Create RAG document
        conn.execute(
            sa.text("""
                INSERT INTO rag_documents (
                    id, tenant_id, filename, title, description,
                    content_type, file_size, status, scope,
                    created_at, updated_at
                ) VALUES (
                    :id, :tenant_id, :filename, :title, :description,
                    :content_type, :file_size, :status, :scope,
                    :created_at, :updated_at
                )
            """),
            {
                "id": rag_doc_id,
                "tenant_id": tenant_id,
                "filename": "company_policy.md",
                "title": "Корпоративная политика",
                "description": "Основные правила и политики компании",
                "content_type": "text/markdown",
                "file_size": 2048,
                "status": "ready",
                "scope": "tenant",
                "created_at": now,
                "updated_at": now,
            }
        )
        
        # Create ToolInstance for RAG
        rag_instance_id = uuid.uuid4()
        conn.execute(
            sa.text("""
                INSERT INTO tool_instances (
                    id, slug, name, description, tool_group_id,
                    connection_config, instance_metadata, is_active,
                    created_at, updated_at
                ) VALUES (
                    :id, :slug, :name, :description, :tool_group_id,
                    :connection_config, :instance_metadata, :is_active,
                    :created_at, :updated_at
                )
            """),
            {
                "id": rag_instance_id,
                "slug": "rag-default",
                "name": "Default Knowledge Base",
                "description": "База знаний по умолчанию",
                "tool_group_id": rag_group_id,
                "connection_config": f'{{"tenant_id": "{tenant_id}"}}',
                "instance_metadata": '{"document_count": 1}',
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        )


def downgrade() -> None:
    conn = op.get_bind()
    
    # Delete tool instances
    conn.execute(sa.text("DELETE FROM tool_instances WHERE slug IN ('collection-tickets', 'rag-default')"))
    
    # Get collection table name and delete
    result = conn.execute(sa.text("SELECT table_name FROM collections WHERE slug = 'tickets'"))
    table_name = result.scalar()
    if table_name:
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {table_name}"))
    
    # Delete collection
    conn.execute(sa.text("DELETE FROM collections WHERE slug = 'tickets'"))
    
    # Delete RAG document
    conn.execute(sa.text("DELETE FROM rag_documents WHERE filename = 'company_policy.md'"))
