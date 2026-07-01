# Коллекция типа TEMPLATE (Шаблоны)

## 1. Назначение

Коллекция типа `template` предназначена для хранения и управления шаблонными документами (Word, Excel, текстовые файлы) с поддержкой структурированного заполнения. Шаблоны используются в инструменте `template.fill` для подстановки плейсхолдеров (`{{field_name}}`) на основе JSON-схемы.

**Ключевые отличия от `document`:**
- Шаблоны не используют векторный поиск по умолчанию — данные не чанкируются и не индексируются в Qdrant (векторизация опциональна и отключаемая).
- Каждая запись — это отдельный файл-шаблон с собственной JSON-схемой заполнения.
- Есть специальный пайплайн автоматического анализа загруженного шаблона (генерация description и schema через LLM).

---

## 2. Обязательные и опциональные поля

При создании коллекции типа `template` backend автоматически добавляет preset-поля. Админ может добавлять дополнительные `user`-поля.

### Preset-поля (системные, нередактируемые)

| Поле | Тип | Required | Описание |
|------|-----|----------|----------|
| `file` | `file` | ✅ | Файл шаблона (хранится в S3, метаданные в JSONB) |
| `title` | `text` | ✅ | Название шаблона |
| `source` | `string` | ✅ | Источник шаблона |
| `template_version` | `string` | ❌ | Версия шаблона (извлекается из заголовков при анализе) |
| `template_schema` | `json` | ✅ | JSON-схема заполнения (описание плейсхолдеров) |
| `semantic_description` | `text` | ❌ | Семантическое описание для поиска/дисскавери шаблона |

**Удалено:** поле `template_kind` (ранее предполагалось, но не востребовано).

---

## 3. Модель и классификация

### CollectionType
```python
class CollectionType(str, Enum):
    TABLE = "table"
    DOCUMENT = "document"
    SQL = "sql"
    API = "api"
    TEMPLATE = "template"
```

### is_local / is_remote
```python
@property
def is_local(self) -> bool:
    return self.collection_type in (
        CollectionType.TABLE.value,
        CollectionType.DOCUMENT.value,
        CollectionType.SQL.value,
        CollectionType.TEMPLATE.value,  # ← template считается локальной коллекцией
    )
```

TEMPLATE — **локальная** коллекция: платформа управляет хранением (PostgreSQL + S3), DDL генерируется автоматически, lifecycle контролируется внутренними сервисами.

---

## 4. Жизненный цикл документа (шаблона) в коллекции

Каждая строка (row) в таблице коллекции — это один шаблон. Статус строки проходит следующие этапы:

### 4.1 Статусы строки

| Статус | Описание | Переход |
|--------|----------|---------|
| `uploaded` | Файл загружен, но анализ не запущен/не завершен | → `analyzed` или `ready` |
| `analyzed` | LLM сгенерировала description или schema (частично) | → `ready` |
| `ready` | Есть и description, и schema — шаблон готов к использованию | → `archived` |
| `archived` | Шаблон архивирован (не участвует в поиске/выдаче) | — |

### 4.2 Пайплайн загрузки и анализа

```
Пользователь загружает файл
         ↓
POST /collections/{id}/templates/upload
         ↓
[TemplateUploadService] → сохраняет файл в S3
                          → создает row в PostgreSQL (status = "uploaded")
         ↓
[TemplateAnalysisOrchestrator] → ставит 2 Celery-задачи:
    1. generate_template_description
    2. generate_template_schema
         ↓
[Worker] Загружает файл из S3
    → LLM генерирует описание (title, description, version)
    → LLM генерирует JSON-схему (placeholder → тип/описание)
         ↓
Обновление row:
    - status переходит в "analyzed" (если готово что-то одно)
    - status переходит в "ready" (если готово и description, и schema)
         ↓
SSE-стриминг статуса в реальном времени (Redis pub/sub)
```

### 4.3 Автоматический переход статуса

Логика `_resolve_next_template_status`:
- Если есть `description` **и** `template_schema` → `ready`
- Если есть что-то одно → `analyzed`
- Иначе → остается текущий статус (или `uploaded`)

### 4.4 Жизненный цикл коллекции (верхний уровень)

```python
_TEMPLATE_LIFECYCLE_STAGES = (
    CollectionStatus.CREATED.value,      # Коллекция создана, но нет шаблонов
    CollectionStatus.DISCOVERED.value,   # Есть шаблоны в процессе анализа
    CollectionStatus.READY.value,          # Все шаблоны готовы
    CollectionStatus.DEGRADED.value,     # Часть шаблонов в ошибке
    CollectionStatus.ERROR.value,          # Все шаблоны в ошибке анализа
)
```

| Коллекция статус | Условие |
|------------------|---------|
| `created` | `total_rows == 0` (нет загруженных шаблонов) |
| `discovered` | Есть шаблоны в статусе `uploaded` или `analyzed` |
| `ready` | Все активные шаблоны в статусе `ready` |
| `degraded` | Часть шаблонов имеет ошибку анализа, но есть и рабочие |
| `error` | Все шаблоны в ошибке анализа |

---

## 5. Функции, возложенные на коллекцию

### 5.1 Хранение файлов-шаблонов
- Загрузка через `POST /collections/{id}/templates/upload`
- Файл сохраняется в S3 (bucket + s3_key)
- Метаданные файла (filename, content_type, size, s3_key, bucket) хранятся в поле `file` типа `JSONB`

### 5.2 Генерация description и schema через LLM
- `generate_template_description` — извлекает title, semantic_description, version из содержимого файла.
- `generate_template_schema` — строит JSON-схему с описанием всех `{{placeholder}}` в файле.
- Оба процесса запускаются параллельно через Celery после загрузки.

### 5.3 Инструмент `template.fill`
Регистрация: `template.fill` (slug)

**Input:**
```json
{
  "collection_id": "uuid или slug коллекции",
  "row_id": "uuid строки-шаблона",
  "values": {"placeholder_name": "значение", ...}
}
```

**Output:**
```json
{
  "file_id": "chatatt_<uuid>",
  "filename": "filled_<original>.docx",
  "size_bytes": 12345,
  "format": "word | excel | text",
  "filled_placeholders": 5,
  "missing_placeholders": ["unfilled_key"]
}
```

**Поддерживаемые форматы:**
- `.docx` — Word (через `python-docx`)
- `.xlsx`, `.xls`, `.xlsm` — Excel (через `openpyxl`)
- Остальное — plain text (`{{key}}` → подстановка)

**Flow:**
1. Находит коллекцию типа `template`.
2. Получает row по `row_id`.
3. Читает `file.s3_key` и `file.bucket`.
4. Скачивает файл из S3.
5. Подставляет значения во все `{{placeholder}}`.
6. Вычисляет список незаполненных плейсхолдеров.
7. Сохраняет результат как downloadable artifact; при наличии чата артефакт может быть привязан к нему для UX.
8. Возвращает `file_id` для скачивания.

### 5.4 SSE-стриминг статуса анализа
- `GET /collections/{id}/templates/{row_id}/status/events`
- Возвращает `text/event-stream` с текущим графом статуса.
- Использует Redis pub/sub для real-time обновлений.

### 5.5 CRUD шаблонов
- `GET /collections/{id}/templates` — список с пагинацией
- `GET /collections/{id}/templates/{row_id}` — получить один шаблон
- `PATCH /collections/{id}/templates/{row_id}` — обновить metadata, schema, status
- `PATCH /collections/{id}/templates/{row_id}/schema` — обновить только schema
- `POST /collections/{id}/templates/analyze` — пере-запустить анализ выбранных шаблонов

---

## 6. Интеграция фронтенда

### 6.1 Создание коллекции
- В селекте типа добавлен пункт **"Шаблоны"** (`template`).
- При выборе `template` автоматически подставляются preset-поля из `TEMPLATE_PRESET_FIELDS`.
- Поля `file`, `title`, `source`, `template_schema` — обязательные и заблокированы для редактирования.
- Векторный поиск отключен для шаблонов.

### 6.2 Загрузка файла
- На странице коллекции показывается кнопка **"Загрузить шаблон"**.
- Используется API `uploadTemplate` (`POST /collections/{id}/templates/upload`).
- После загрузки запускается SSE-подписка на статус анализа.

### 6.3 Отображение в списках
- `CollectionListPage`, `CollectionsListPage`, `CollectionDataPage` — везде добавлен badge **"Шаблоны"** (зеленый `success`).

---

## 7. Схема БД (DDL)

Для каждой коллекции `template` создается динамическая таблица:

```sql
CREATE TABLE <tenant_slug> (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file JSONB,           -- {s3_key, bucket, filename, content_type, size}
    title TEXT,
    source VARCHAR,
    template_version VARCHAR,
    template_schema JSONB,
    semantic_description TEXT,
    status VARCHAR DEFAULT 'uploaded',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    -- + пользовательские поля
    -- + system поля (vector embeddings, etc. при необходимости)
);
```

**Типы PostgreSQL:**
- `file`, `template_schema` → `JSONB`
- `title`, `semantic_description` → `TEXT`
- `source`, `template_version`, `status` → `VARCHAR`

---

## 8. Tool Instance

Каждая `template` коллекция привязана к локальному `ToolInstance` с типом `data`.

```python
def resolve_local_service_for_collection_type(self, collection_type: str) -> DiscoveredTool:
    if collection_type == CollectionType.TEMPLATE.value:
        return self.template_instance  # ← свой instance для шаблонов
```

Это позволяет агентам обращаться к шаблонам через инструмент `collection.template.*`.

---

## 9. Валидация и контракт

### SchemaContractService
- `validate_admin_defined_fields` — проверяет, что админ не добавил preset-поля с неверными типами.
- `ensure_template_preset_fields` — гарантирует наличие всех preset-полей при создании/обновлении коллекции.
- `get_type_specific_field_presets` — возвращает `TEMPLATE_SPECIFIC_FIELD_DEFS` для UI и API.

### CreateCollectionRequest (Pydantic)
```python
collection_type: str = Field(
    default=CollectionType.TABLE.value,
    pattern=r"^(table|document|sql|api|template)$",
)
```

---

## 10. Отличия от DOCUMENT

| Аспект | DOCUMENT | TEMPLATE |
|--------|----------|----------|
| Векторный поиск | Обязателен (Qdrant) | Отключен |
| Чанкирование | Да (параграфы/токены) | Нет |
| Поле `file` | Хранит ссылку на документ | Хранит шаблон для заполнения |
| Анализ контента | OCR + эмбеддинги | LLM-генерация description + schema |
| Инструмент | `collection.document.search` | `template.fill` |
| Статус строки | `uploaded/processing/ready/failed` | `uploaded/analyzed/ready/archived` |
| Назначение | RAG / knowledge base | Шаблонная генерация документов |

---

## 11. Архитектура сервисов

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (React)                      │
│  CollectionPage → FieldsEditor → TEMPLATE_PRESET_FIELDS      │
│  UploadButton → collectionsApi.uploadTemplate()               │
└──────────────────────┬────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                      API (FastAPI)                           │
│  /collections/{id}/templates/upload                          │
│  /collections/{id}/templates/{row_id}/status/events (SSE)    │
│  /admin/collections (CRUD)                                   │
└──────────────────────┬────────────────────────────────────────┘
                       │
         ┌─────────────┴──────────────┐
         ▼                            ▼
┌─────────────────┐       ┌──────────────────────┐
│ TemplateUpload   │       │ TemplateAnalysis      │
│ Service          │       │ Orchestrator          │
│ (S3 + row insert)│       │ (Celery tasks enqueue)│
└────────┬─────────┘       └──────────┬───────────┘
         │                              │
         ▼                              ▼
┌─────────────────┐       ┌──────────────────────┐
│ S3 (MinIO)       │       │ Celery Worker         │
│                  │       │  • generate_template  │
│  template files  │       │    _description      │
│                  │       │  • generate_template  │
└──────────────────┘       │    _schema            │
                           └──────────┬───────────┘
                                      │
                                      ▼
                           ┌──────────────────────┐
                           │ TemplateAnalyzeService│
                           │ (LLM calls)         │
                           └──────────────────────┘
                                      │
                                      ▼
                           ┌──────────────────────┐
                           │ PostgreSQL           │
                           │ (row + status graph) │
                           └──────────────────────┘
```
