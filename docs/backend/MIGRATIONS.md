# Миграции

## Alembic

Используем Alembic для управления миграциями.

## Структура

```
apps/api/src/app/migrations/
├── env.py              # Alembic environment
├── script.py.mako      # Template for new migrations
└── versions/
    ├── 0001_initial.py
    ├── 0002_add_tenants.py
    ├── 0003_add_agents.py
    └── ...
```

## Naming Convention

```
XXXX_description.py
```

- `XXXX` — порядковый номер (0001, 0002, ...)
- `description` — краткое описание изменений

## Создание миграции

```bash
# Автогенерация
docker compose exec api alembic revision --autogenerate -m "add_new_field"

# Пустая миграция
docker compose exec api alembic revision -m "custom_migration"
```

## Применение миграций

```bash
# Применить все
docker compose exec api alembic upgrade head

# Применить до конкретной
docker compose exec api alembic upgrade 0042

# Откатить одну
docker compose exec api alembic downgrade -1

# Откатить до конкретной
docker compose exec api alembic downgrade 0040
```

## Шаблон миграции

```python
"""Add agent_permissions to permission_sets

Revision ID: 0053
Revises: 0052
Create Date: 2024-01-30 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '0053'
down_revision = '0052'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add column
    op.add_column(
        'permission_sets',
        sa.Column(
            'agent_permissions',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default='{}'
        )
    )
    
    # Remove server default after data migration
    op.alter_column(
        'permission_sets',
        'agent_permissions',
        server_default=None
    )


def downgrade() -> None:
    op.drop_column('permission_sets', 'agent_permissions')
```

## Best Practices

### Добавление NOT NULL колонки

1. Добавить как nullable
2. Заполнить данные
3. Изменить на NOT NULL

```python
def upgrade() -> None:
    # Step 1: Add nullable column
    op.add_column(
        'agents',
        sa.Column('new_field', sa.String(100), nullable=True)
    )
    
    # Step 2: Fill data
    op.execute("UPDATE agents SET new_field = 'default_value'")
    
    # Step 3: Make NOT NULL
    op.alter_column(
        'agents',
        'new_field',
        nullable=False
    )
```

### Удаление колонки

1. Пометить как deprecated в коде
2. Удалить через N релизов

```python
# Migration 1: Mark deprecated (add comment)
# Migration 2 (later): Actually drop
def upgrade() -> None:
    op.drop_column('agents', 'deprecated_field')
```

### Изменение типа колонки

Через промежуточную колонку:

```python
def upgrade() -> None:
    # Add new column
    op.add_column('table', sa.Column('field_new', sa.Integer()))
    
    # Copy data with conversion
    op.execute("UPDATE table SET field_new = CAST(field_old AS INTEGER)")
    
    # Drop old column
    op.drop_column('table', 'field_old')
    
    # Rename new to old
    op.alter_column('table', 'field_new', new_column_name='field_old')
```

### Добавление индекса

```python
def upgrade() -> None:
    op.create_index(
        'ix_agents_slug',
        'agents',
        ['slug'],
        unique=True
    )

def downgrade() -> None:
    op.drop_index('ix_agents_slug', table_name='agents')
```

### Добавление FK

```python
def upgrade() -> None:
    op.add_column(
        'agents',
        sa.Column('policy_id', sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        'fk_agents_policy_id',
        'agents', 'policies',
        ['policy_id'], ['id'],
        ondelete='SET NULL'
    )

def downgrade() -> None:
    op.drop_constraint('fk_agents_policy_id', 'agents', type_='foreignkey')
    op.drop_column('agents', 'policy_id')
```

## Data Migrations

### Seed данные

```python
def upgrade() -> None:
    # Create table
    op.create_table(...)
    
    # Seed initial data
    op.execute("""
        INSERT INTO tool_groups (id, slug, name, description)
        VALUES 
            (gen_random_uuid(), 'builtin', 'Built-in Tools', 'System tools'),
            (gen_random_uuid(), 'http', 'HTTP Tools', 'External API tools'),
            (gen_random_uuid(), 'collection', 'Collections', 'Data collections')
    """)
```

### Миграция существующих данных

```python
def upgrade() -> None:
    # Add new enum value
    op.execute("ALTER TYPE instance_type ADD VALUE 'custom'")
    
    # Update existing records
    op.execute("""
        UPDATE tool_instances 
        SET instance_type = 'local' 
        WHERE instance_type IS NULL
    """)
```

## Проверки перед деплоем

- [ ] Миграция применяется без ошибок
- [ ] Миграция откатывается без ошибок
- [ ] Данные не теряются
- [ ] Индексы созданы для новых FK
- [ ] Нет блокирующих операций на больших таблицах
