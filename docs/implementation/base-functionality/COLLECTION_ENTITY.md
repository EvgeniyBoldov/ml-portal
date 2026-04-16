# Collection Entity — Collection-Centric Architecture

## Core Principle

**Collection описывает scope данных. Агент работает с collections.**

Collection — first-class data asset: schema + semantic layer + metadata.
Instance — backend infra config: где лежит, как авторизоваться, через какой provider подключаться.

Локальные коллекции — частный случай удалённых.
Для них платформа auto-creates data + service instances, чтобы runtime flow был единым.

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    AGENT / RUNTIME LAYER                    │
│  Агент видит: Collection (data asset) + Operations (tools)  │
│  Агент НЕ видит: instances, URLs, credentials, providers    │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────┼────────────────────────────────┐
│                    COLLECTION LAYER                          │
│  Collection = schema + semantic layer + metadata             │
│  - что за данные (entity_type, description)                  │
│  - какие поля (fields, categories, capabilities)             │
│  - как искать и фильтровать (semantic profile)               │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────┼────────────────────────────────┐
│                    INSTANCE LAYER (infra)                     │
│  Data Instance = "где лежат данные"                           │
│    - url, config, placement (local/remote)                    │
│    - access_via_instance_id → Service Instance                │
│                                                               │
│  Service Instance = "через что подключаться к данным"         │
│    - MCP gateway URL, local-runtime                           │
│    - discovered_tools (capabilities of the service)           │
│                                                               │
│  Credentials = auth config для remote instances               │
└─────────────────────────────────────────────────────────────┘
```

## Entity Relationships

```
Collection (data asset)
├── schema (fields + categories + capabilities)
├── semantic layer (derived from schema + metadata)
├── versions (semantic profile + retrieval params)
└── data_instance_id → ToolInstance (kind=data)
                        ├── placement: local | remote
                        ├── url, config
                        ├── access_via_instance_id → ToolInstance (kind=service)
                        │                            ├── discovered_tools[]
                        │                            └── url (MCP/local-runtime)
                        └── credentials (for remote)
```

**Ключевая связка:**
- `Collection` → описывает ЧТО (data scope, schema, semantics)
- `Data Instance` → описывает ГДЕ (url, config, placement)
- `Service Instance` → описывает ЧЕРЕЗ ЧТО (MCP provider, local-runtime)
- `Discovered Tools` → описывает ЧЕМ (operations/capabilities provider)
- `Operations` → runtime-ready actions = discovered_tools + collection semantics

## Resolver Contract

`CollectionResolver` is the only place where collection data becomes agent-facing.

It must assemble the prompt/runtime view from:
- `Collection` container metadata,
- `CollectionSchema` field contract,
- effective `CollectionVersion` semantic layer.

If a field is already derivable from schema, it should not be duplicated in the version unless the version needs an override or semantic exception.

## Instance Auto-Create Rules

Каждая локальная коллекция при создании **обязана** получить:
1. **Data Instance** (`kind=data, placement=local`) — привязан к коллекции через `config.binding_type=collection_asset`
2. **Service Instance** (`kind=service, placement=local`) — подбирается по типу коллекции

Service instances — **shared per collection type**:
- `local-table-tools` — для всех `table` коллекций
- `local-document-tools` — для всех `document` коллекций

Data instances — **one per collection**:
- `collection-{slug}` — уникальный для каждой коллекции

Это сохраняет единый flow: `Collection → Data Instance → Service Instance → Discovered Tools → Operations`.

Для **remote** коллекций data instance и service instance уже существуют (созданы admin'ом).
Collection привязывается к ним через `data_instance_id`.

## Collection Types

### `table` — Local Structured Records

Платформа владеет storage (PostgreSQL dynamic table).

**Примеры:** IT tickets, device registry, user registry, sales.

**Specific fields:** нет (все поля — user fields).
Все user fields поддерживают vector search если `used_in_retrieval=True`.

**Schema = Storage:** schema совпадает со структурой таблицы в БД.
Schema evolution (add/alter/rename/remove fields) мигрирует и данные и таблицу.

**Lifecycle:** created → ingesting (data load) → ready → degraded/error

### `document` — Local Document Registry

Платформа владеет storage (PostgreSQL + Qdrant + file storage).

**Примеры:** contracts, policies, manuals, switch configs.

**Specific fields (immutable, auto-created):**
- `file_ref` — ссылка на файл в storage
- `file_name` — имя файла
- `file_size` — размер
- `file_content_type` — MIME type
- `vectorization_status` — статус индексации

**User fields (preset, мутабельные):** `title`, `source`, `scope`, `tags`

**Обязательные vs авто-заполняемые поля (document):**
- Обязательные при upload: бинарный файл + `file_name` (из payload) и `file_ref` (storage key).
- Авто-заполняемые платформой: `file_content_type`, `file_size`, `vectorization_status`.
- Опциональные user metadata: `title`, `source`, `scope`, `tags`.

**Lifecycle:** created → ingesting (upload + vectorize) → ready → degraded/error

### `remote.sql` — Remote SQL Database

Данные живут во внешней SQL базе. Platform НЕ владеет storage.

**Примеры:** PostgreSQL analytics DB, MySQL legacy system.

**Specific fields (описывают structure remote DB):**
- Каждая таблица в remote DB = field category `specific` с:
  - `table_name` — имя таблицы
  - `table_schema` — JSON schema таблицы (columns, types)

**Или упрощённо:** schema коллекции = список таблиц remote DB с их columns.
Schema может быть обнаружена автоматически (introspect через MCP `search_objects`) или задана вручную.

**Lifecycle:** created → discovered (schema introspected) → ready → degraded/error

### `remote.api` — Remote API Scope (future)

Данные доступны через REST/GraphQL API. Platform НЕ владеет storage.

**Примеры:** Jira project, NetBox site, ServiceNow instance.

**Specific fields (описывают API entities):**
- `entity_type` — тип сущности (issue, device, etc.)
- `entity_description` — описание
- `entity_schema` — JSON schema сущности

**Lifecycle:** created → discovered → ready → degraded/error

### Type Immutability

`collection_type` is immutable after creation.
Future types are added as new explicit enum values.

## Collection Structure

### 1. Metadata

```
id, tenant_id, slug, name, description,
collection_type, is_active, status,
data_instance_id,       -- link to infra Data Instance
entity_type,            -- LLM context hint (e.g. "ticket", "document", "sql_database")
created_at, updated_at
```

### 2. Schema (CollectionSchema)

Schema описывает поля данных коллекции.

Для **local** (`table`, `document`): schema = полная структура, совпадает со storage.
Для **remote** (`remote.sql`, `remote.api`): schema = контракт описания внешних данных.

Каждое поле:
- `name`, `category` (system | specific | user), `data_type`, `description`
- `required`, `filterable`, `sortable`, `used_in_retrieval`, `used_in_prompt_context`

### 3. Semantic Layer (CollectionVersion)

Semantic layer строится из schema + metadata. Объясняет агенту:
- что за данные (summary, entity_types)
- какие поля полезны для фильтрации и prompt context
- use cases и limitations

Semantic layer **одинаков по структуре** для всех типов коллекций.

Semantic layer **не содержит**: system fields, operational fields, infra details.
Resolver merges schema + version into the agent-facing collection view.

### 4. Operational State (type-dependent)

| Field | table | document | remote.sql | remote.api |
|-------|-------|----------|------------|------------|
| table_name | ✅ PG table | ✅ PG table | ❌ | ❌ |
| row_count | ✅ | ✅ | ❌ | ❌ |
| vector_config | ✅ optional | ✅ always | ❌ | ❌ |
| qdrant_collection_name | ✅ optional | ✅ always | ❌ | ❌ |
| vectorized_rows | ✅ | ✅ | ❌ | ❌ |
| total_chunks | ✅ | ✅ | ❌ | ❌ |
| failed_rows | ✅ | ✅ | ❌ | ❌ |
| discovered_schema | ❌ | ❌ | ✅ introspected | ✅ introspected |
| last_sync_at | ❌ | ❌ | ✅ | ✅ |

## Versions

```
CollectionVersion:
  - version (int)
  - status: draft | published | archived
  - semantic_profile (JSONB): summary, entity_types, use_cases, limitations, examples
  - policy_hints (JSONB): prompt/runtime limits and safety hints
  - notes (text)
```

`Collection.current_version_id` → published primary version.

## Runtime Flow

```
1. Runtime loads Collections (active, с data_instance_id)
2. CollectionResolver builds prompt-facing collection view from schema + current_version
3. Collection.data_instance_id → Data Instance
4. Data Instance.access_via_instance_id → Service Instance (provider)
5. Provider → discovered tools (raw capabilities)
6. ToolResolver combines discovered tool + effective tool release + sandbox overlay
7. Runtime assembles operations and collection context only from resolver outputs
8. Agent получает только resolved collection context + available operations
```

### Semantic Source Priority

| Source | Local | Remote |
|--------|-------|--------|
| Schema | Collection.schema (manages storage) | Collection.schema (describes remote) |
| Resolver | CollectionResolver | CollectionResolver |
| Semantic | CollectionVersion (semantic overrides) | CollectionVersion (semantic overrides) |
| Operations | ToolResolver + collection context | ToolResolver + collection context |

## Field Categories

### System Fields
Platform-owned: `id`, `_created_at`, `_updated_at`.
Not agent-facing. Immutable. Not stored in schema (derived).

### Specific Fields
Type-dependent, auto-created per collection type.
Immutable from admin perspective.

| Type | Specific Fields |
|------|----------------|
| `document` | file_ref, file_name, file_size, file_content_type, vectorization_status |
| `table` | (none) |
| `remote.sql` | per-table entries: table_name, table_schema |
| `remote.api` | entity_type, entity_description, entity_schema |

### User Fields
Business fields added by admin. Main semantic extension surface.

For `table`: all schema is user fields (full control).
For `document`: preset user fields (title, source, scope, tags) + custom.
For `remote.sql`: admin-added semantic descriptions of tables/columns.
For `remote.api`: admin-added descriptions of entities.

## Mutability Rules

### Collection-Level
- **Mutable**: name, description, is_active
- **Immutable**: collection_type, tenant_id, slug

### Schema-Level
- **Immutable**: system fields, specific fields
- **Mutable**: user fields (for local: with data migration; for remote: descriptive only)

## Semantic Construction

Generated from: collection_type, metadata (name, description, entity_type),
field descriptions and categories, field capabilities.

EXCLUDES: system fields, operational fields, infra details.

---

## GAP Analysis: Current → Target

### What works

| Aspect | Status |
|--------|--------|
| Local table collections | ✅ Collection + auto-instance + semantic profile |
| Local document collections | ✅ Collection + auto-instance + semantic profile |
| Local service instances per type | ✅ `local-table-tools`, `local-document-tools` |
| Auto-create data instance per collection | ✅ `_create_tool_instance_for_collection()` |
| Remote SQL via MCP runtime | ✅ Works end-to-end (tested) |

### What is missing

1. **No Collection entity for remote data.**
   `sql-analytics` data instance may exist as infra, but still needs explicit Collection as data asset.
   Need: Collection entity describing the remote SQL scope.

2. **Collection model is local-only.**
   `table_name` NOT NULL, `row_count` NOT NULL — breaks for remote.
   Need: nullable local-specific fields, new remote-specific fields.

3. **No `remote.sql` collection type.**
   `CollectionType` enum only has `table` and `document`.

4. **operation_router starts from Instance, not Collection.**
   Need: resolve from Collections → instances (Phase 2, later).

### Implementation Plan

#### Phase 1: Data model (this session)

1. Add `CollectionType.REMOTE_SQL = "remote.sql"` to enum
2. Make local-specific fields nullable: `table_name`, `row_count`, `total_rows`, `vectorized_rows`, `total_chunks`, `failed_rows`, `vector_config`, `qdrant_collection_name`, `primary_key_field`, `time_column`, `default_sort`, `allow_unfiltered_search`, `max_limit`, `query_timeout_seconds`
3. Add remote-specific optional fields: `discovered_schema` (JSONB), `last_sync_at` (DateTime)
4. Rename `tool_instance_id` → `data_instance_id` (semantic clarity)
5. Alembic migration

#### Phase 2: Service — create remote.sql collection

1. `CollectionService.create_remote_sql_collection()` — creates Collection linked to existing data instance
2. Schema introspection via MCP `search_objects` → populate `discovered_schema`
3. Auto-create initial CollectionVersion with semantic profile
4. Admin API endpoint: `POST /admin/collections` with `collection_type=remote.sql`

#### Phase 3: Runtime — collection-aware operation_router (later)

1. `resolve()` starts from Collections, not Instances
2. Semantic profile from Collection.current_version for all types
3. raw contracts come from discovered capabilities, curated semantics come from effective `ToolRelease`

## Summary

| Layer | Owns | Does NOT own |
|-------|------|--------------|
| **Collection** | data scope, schema, semantic layer | URLs, credentials, provider config |
| **Instance** | connection config, placement, health | data meaning, schema, semantics |
| **Service Provider** | capabilities, discovered tools | data scope, business meaning |

Local collections — частный случай с auto-created instances.
Remote collections — полноценные data assets, привязанные к existing instances.
Runtime flow единый для всех: Collection → Instance → Provider → Operations.
