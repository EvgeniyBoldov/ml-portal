# Collection Tools Architecture

> **Статус: РЕАЛИЗОВАНО** (миграции 0049, 0050)

## Реализованные компоненты

### Collection Model (расширен)
- `Collection` хранит метаданные коллекции (slug, name, fields, table_name)
- `fields` — JSONB с описанием полей: name, type, search_modes, description
- **Новые типы:** string, text, integer, float, boolean, datetime, date, enum, json
- Поддерживаемые search_modes: exact, like, contains, range, vector
- При создании коллекции автоматически создаётся SQL-таблица и ToolInstance

### Новые поля Collection (миграция 0049)
- `primary_key_field` — поле первичного ключа (default: "id")
- `time_column` — поле времени для time-based запросов
- `default_sort` — сортировка по умолчанию (JSONB: {field, order})
- `entity_type` — тип сущности для LLM контекста
- `allow_unfiltered_search` — разрешить поиск без фильтров (default: false)
- `max_limit` — максимальный лимит записей (default: 100)
- `query_timeout_seconds` — таймаут запроса (default: 10)
- `tool_instance_id` — FK на автоматически созданный ToolInstance

### Инструменты (миграция 0050)
- `collection.get` — получение записи по ключу
- `collection.search` — поиск с DSL фильтрами и guardrails
- `collection.aggregate` — агрегации (count, sum, avg, min, max)

## Новая архитектура: Collection = ToolInstance

### Концепция
**1 коллекция = 1 ToolInstance** в группе `collection`

При создании коллекции автоматически создаётся:
1. `ToolInstance` с `slug = collection-{collection_slug}`
2. `connection_config` содержит ссылку на коллекцию

### Преимущества
- Унифицированный подход к привязке инструментов в агентах
- Можно привязать конкретную коллекцию к агенту через bindings
- RBAC будет работать через стандартный механизм tool instances
- Креды не нужны (внутренняя БД)

## Новые инструменты для коллекций

### 1. collection.get
**Назначение:** Точное получение записи по ключу

```json
{
  "type": "object",
  "properties": {
    "id": {
      "type": "string",
      "description": "Record ID (UUID or primary key value)"
    },
    "id_field": {
      "type": "string",
      "description": "Primary key field name (default: 'id')"
    }
  },
  "required": ["id"]
}
```

### 2. collection.search
**Назначение:** Фильтрация + текстовый поиск

```json
{
  "type": "object",
  "properties": {
    "filters": {
      "type": "object",
      "description": "Structured filter conditions",
      "properties": {
        "and": { "type": "array" },
        "or": { "type": "array" }
      }
    },
    "query": {
      "type": "string",
      "description": "Text search query (ILIKE on text fields)"
    },
    "sort": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "field": { "type": "string" },
          "order": { "enum": ["asc", "desc"] }
        }
      }
    },
    "limit": {
      "type": "integer",
      "default": 50,
      "maximum": 100
    },
    "offset": {
      "type": "integer",
      "default": 0,
      "maximum": 1000
    }
  }
}
```

### 3. collection.aggregate
**Назначение:** Статистика и агрегации

```json
{
  "type": "object",
  "properties": {
    "metrics": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "function": { "enum": ["count", "count_distinct", "sum", "avg", "min", "max"] },
          "field": { "type": "string" },
          "alias": { "type": "string" }
        }
      }
    },
    "group_by": {
      "type": "array",
      "items": { "type": "string" },
      "maxItems": 3
    },
    "filters": {
      "type": "object",
      "description": "Required for large tables"
    },
    "time_bucket": {
      "type": "object",
      "properties": {
        "field": { "type": "string" },
        "interval": { "enum": ["hour", "day", "week", "month", "year"] }
      }
    }
  },
  "required": ["metrics", "filters"]
}
```

## DSL для фильтров

### Структура фильтра
```json
{
  "and": [
    {"field": "site", "op": "eq", "value": "MSK-1"},
    {"field": "created_at", "op": "range", "value": {"gte": "2025-01-01", "lt": "2026-01-01"}},
    {"field": "status", "op": "in", "value": ["resolved", "closed"]}
  ]
}
```

### Поддерживаемые операторы

| Тип поля | Операторы |
|----------|-----------|
| string/text | eq, in, like, contains, is_null |
| integer/float | eq, in, range, gt, gte, lt, lte, is_null |
| datetime/date | eq, range, gt, gte, lt, lte, is_null |
| boolean | eq, is_null |
| enum | eq, in |

### Валидация
- `allowed_ops` задаются в метаданных поля
- Бэкенд валидирует каждый фильтр против метаданных

## Расширенные метаданные коллекции

### Новая структура поля
```json
{
  "name": "status",
  "type": "text",
  "required": true,
  "description": "Ticket status",
  "search_modes": ["exact"],
  "allowed_ops": ["eq", "in"],
  "is_text_searchable": false,
  "is_enum": true,
  "enum_values": ["open", "in_progress", "resolved", "closed"],
  "aliases": ["state", "ticket_status"]
}
```

### Новые поля Collection
```python
class Collection(Base):
    # ... existing fields ...
    
    # Primary key configuration
    primary_key_field: Mapped[str] = mapped_column(String(100), default="id")
    
    # Time column for aggregations
    time_column: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Default sort
    default_sort: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Example: {"field": "created_at", "order": "desc"}
    
    # Guardrails
    allow_unfiltered_search: Mapped[bool] = mapped_column(Boolean, default=False)
    max_limit: Mapped[int] = mapped_column(Integer, default=100)
    query_timeout_seconds: Mapped[int] = mapped_column(Integer, default=10)
    
    # Entity type for LLM context
    entity_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Example: "ticket", "device", "user"
```

## Guardrails

### Обязательные ограничения
1. **limit**: default=50, max=100
2. **offset**: max=1000 (требует фильтры для больших offset)
3. **aggregate**: требует хотя бы один фильтр или time_range
4. **group_by**: max 3 поля
5. **max результатов групп**: 100
6. **query timeout**: 5-10 секунд
7. **allow_unfiltered_search**: флаг в метаданных (default=false для больших таблиц)

### Валидация запросов
```python
class QueryValidator:
    def validate(self, collection: Collection, query: dict) -> None:
        # 1. Validate all fields exist
        # 2. Validate ops are allowed for each field
        # 3. Validate value types
        # 4. Check guardrails (limit, offset, filters required)
        # 5. Check timeout settings
```

## SQL Generator

### Принципы
1. **Whitelist only**: таблица и колонки только из метаданных
2. **Parameterized queries**: никаких f-strings для значений
3. **AST-based**: строим SQL через AST, не строки

### Псевдокод
```python
class SQLGenerator:
    def __init__(self, collection: Collection):
        self.collection = collection
        self.table_name = collection.table_name
        self.allowed_fields = {f["name"] for f in collection.fields}
    
    def build_select(self, filters: dict, limit: int, offset: int) -> tuple[str, dict]:
        # Validate all fields
        # Build WHERE clause from filters AST
        # Add LIMIT/OFFSET
        # Return (sql, params)
        pass
    
    def build_aggregate(self, metrics: list, group_by: list, filters: dict) -> tuple[str, dict]:
        # Validate metrics and group_by fields
        # Build SELECT with aggregations
        # Build GROUP BY
        # Return (sql, params)
        pass
```

## Автоматическое создание ToolInstance

### При создании коллекции
```python
async def create_collection(self, ...) -> Collection:
    # 1. Create collection (existing logic)
    collection = Collection(...)
    
    # 2. Auto-create ToolInstance
    tool_instance = ToolInstance(
        tool_group_id=collection_group_id,  # "collection" group
        slug=f"collection-{collection.slug}",
        name=f"Collection: {collection.name}",
        description=collection.description,
        connection_config={
            "collection_id": str(collection.id),
            "collection_slug": collection.slug,
            "tenant_id": str(tenant_id),
        },
        instance_metadata={
            "entity_type": collection.entity_type,
            "row_count": 0,
            "has_vector_search": collection.has_vector_search,
        },
        is_active=True,
    )
    
    # 3. Save both
    session.add(collection)
    session.add(tool_instance)
    await session.flush()
    
    return collection
```

### При удалении коллекции
- Автоматически удалять связанный ToolInstance
- Каскадное удаление через FK или явно в сервисе

## Миграции

### 0049_collection_extended_metadata.py
```python
def upgrade():
    # Add new columns to collections
    op.add_column('collections', sa.Column('primary_key_field', sa.String(100), default='id'))
    op.add_column('collections', sa.Column('time_column', sa.String(100), nullable=True))
    op.add_column('collections', sa.Column('default_sort', JSONB, nullable=True))
    op.add_column('collections', sa.Column('allow_unfiltered_search', sa.Boolean, default=False))
    op.add_column('collections', sa.Column('max_limit', sa.Integer, default=100))
    op.add_column('collections', sa.Column('query_timeout_seconds', sa.Integer, default=10))
    op.add_column('collections', sa.Column('entity_type', sa.String(100), nullable=True))
```

### 0050_collection_tool_instances.py
```python
def upgrade():
    # Create ToolInstances for existing collections
    # Get "collection" tool group
    # For each collection, create ToolInstance
    pass
```

## План реализации

### Phase 1: Модели и миграции
1. [ ] Расширить модель Collection новыми полями
2. [ ] Создать миграцию для новых полей
3. [ ] Добавить связь Collection -> ToolInstance

### Phase 2: Автоматическое создание ToolInstance
1. [ ] Обновить CollectionService.create_collection()
2. [ ] Добавить удаление ToolInstance при удалении коллекции
3. [ ] Создать миграцию для существующих коллекций

### Phase 3: Новые инструменты
1. [ ] Реализовать collection.get
2. [ ] Обновить collection.search с DSL фильтрами
3. [ ] Реализовать collection.aggregate

### Phase 4: SQL Generator и Guardrails
1. [ ] Реализовать QueryValidator
2. [ ] Реализовать SQLGenerator
3. [ ] Добавить guardrails

### Phase 5: Интеграция с агентами
1. [ ] Обновить AgentRuntime для работы с collection instances
2. [ ] Обновить UI для привязки коллекций через bindings

## Типы данных (финальный список)

| Тип | PostgreSQL | Описание |
|-----|------------|----------|
| string | VARCHAR(255) | Короткий текст (имя, hostname) |
| text | TEXT | Длинный текст (body, description) |
| integer | INTEGER | Целое число |
| float | DOUBLE PRECISION | Дробное число |
| boolean | BOOLEAN | true/false |
| datetime | TIMESTAMPTZ | Дата и время с timezone |
| date | DATE | Только дата |
| enum | VARCHAR(100) | Ограниченный список значений |
| json | JSONB | Произвольный JSON (избегать на MVP) |
| vector | - | Для kNN поиска (через Qdrant) |

## Примеры использования

### Создание коллекции "tickets"
```json
{
  "slug": "tickets",
  "name": "IT Tickets",
  "entity_type": "ticket",
  "primary_key_field": "ticket_number",
  "time_column": "created_at",
  "default_sort": {"field": "created_at", "order": "desc"},
  "fields": [
    {
      "name": "ticket_number",
      "type": "string",
      "required": true,
      "search_modes": ["exact"],
      "allowed_ops": ["eq", "in"]
    },
    {
      "name": "title",
      "type": "text",
      "required": true,
      "search_modes": ["like"],
      "is_text_searchable": true
    },
    {
      "name": "status",
      "type": "string",
      "required": true,
      "search_modes": ["exact"],
      "allowed_ops": ["eq", "in"],
      "is_enum": true,
      "enum_values": ["open", "in_progress", "resolved", "closed"]
    },
    {
      "name": "created_at",
      "type": "datetime",
      "required": true,
      "search_modes": ["range"],
      "allowed_ops": ["range", "gt", "gte", "lt", "lte"]
    }
  ]
}
```

### Поиск с DSL фильтрами
```json
{
  "filters": {
    "and": [
      {"field": "status", "op": "in", "value": ["open", "in_progress"]},
      {"field": "created_at", "op": "range", "value": {"gte": "2025-01-01"}}
    ]
  },
  "query": "network error",
  "sort": [{"field": "created_at", "order": "desc"}],
  "limit": 20
}
```

### Агрегация
```json
{
  "metrics": [
    {"function": "count", "alias": "total"},
    {"function": "count_distinct", "field": "assignee", "alias": "unique_assignees"}
  ],
  "group_by": ["status"],
  "filters": {
    "and": [
      {"field": "created_at", "op": "range", "value": {"gte": "2025-01-01", "lt": "2025-02-01"}}
    ]
  }
}
```
