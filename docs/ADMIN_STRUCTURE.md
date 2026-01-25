# Admin Panel Structure

Структура административной панели для AI-инженеров и администраторов.

## Навигация

```
/admin
├── /dashboard              — Дашборды и метрики
├── /users                  — Управление пользователями и департаментами
│   ├── /users              — Список пользователей
│   ├── /users/new          — Создание пользователя
│   ├── /users/:id          — Просмотр/редактирование пользователя
│   ├── /tenants            — Список департаментов
│   ├── /tenants/new        — Создание департамента
│   ├── /tenants/:id        — Просмотр/редактирование департамента
│   └── /defaults           — Общие настройки (default scope)
├── /ai                     — AI компоненты
│   ├── /models             — Модели (LLM, Embedding, Rerank)
│   ├── /models/:id         — Редактирование модели
│   ├── /prompts            — Реестр промптов
│   ├── /prompts/:slug      — Детальный вид промпта (все версии)
│   ├── /prompts/:slug/edit — Редактирование версии промпта
│   ├── /tools              — Инструменты (Tool registry)
│   ├── /agents             — Реестр агентов
│   ├── /agents/:slug       — Редактирование агента
│   └── /agents/:slug/test  — A/B тестирование промптов (TODO)
├── /integrations           — Интеграции
│   ├── /instances          — Инстансы инструментов
│   ├── /instances/new      — Создание инстанса
│   ├── /instances/:id      — Просмотр инстанса
│   ├── /collections        — Коллекции данных
│   ├── /collections/new    — Создание коллекции
│   └── /collections/:id    — Просмотр коллекции
└── /logs                   — Логирование
    ├── /agent-runs         — Запуски агентов
    ├── /agent-runs/:id     — Детальный просмотр запуска
    └── /audit              — Audit logs
```

---

## Dashboard

### Метрики по сущностям
- **Пользователи**: всего / активных / по ролям
- **Департаменты**: всего / активных
- **Агенты**: всего / активных / в draft
- **Промпты**: всего / активных / в draft
- **Инструменты**: всего / активных / с ошибками health check
- **Коллекции**: всего / с векторным поиском / процент векторизации

### Ошибки за последние 24 часа
- **Agent runs**: количество failed запусков
- **Tool calls**: количество ошибок по инструментам
- **Health checks**: инстансы с unhealthy статусом

### Графики (опционально)
- Запросы к агентам за последние 7 дней
- Топ-5 используемых агентов
- Топ-5 используемых инструментов

---

## Users Section

### /users — Список пользователей

**Компонент:** `<DataTable>`

**Колонки:**
- Login
- Email
- Role (admin | tenant_admin | user)
- Tenants (список департаментов)
- Status (active | inactive)
- Created At

**Фильтры:**
- По роли
- По статусу
- По департаменту
- Поиск по login/email

**Действия:**
- Создать пользователя
- Редактировать
- Деактивировать/Активировать
- Сбросить пароль

### /users/:id — Просмотр пользователя

**Layout:** 2 колонки

**Левая колонка:**
- Основная информация (login, email, role, status)
- Кнопки: Редактировать, Деактивировать, Сбросить пароль

**Правая колонка:**
- **Департаменты**: список с указанием дефолтного
- **Креды**: список credential sets (scope=user)
- **Политики доступа**: effective permissions (resolved)
- **История**: последние действия (audit log)

### /tenants — Список департаментов

**Компонент:** `<DataTable>`

**Колонки:**
- Name
- Description
- Users count
- Collections count
- Status (active | inactive)
- Created At

**Фильтры:**
- По статусу
- Поиск по name

**Действия:**
- Создать департамент
- Редактировать
- Деактивировать/Активировать

### /tenants/:id — Просмотр департамента

**Layout:** 2 колонки

**Левая колонка:**
- Основная информация (name, description, status)
- Настройки (embedding_model_alias, ocr, layout)
- Кнопки: Редактировать, Деактивировать

**Правая колонка:**
- **Пользователи**: список с ролями
- **Коллекции**: список коллекций департамента
- **Креды**: credential sets (scope=tenant)
- **Политики доступа**: tenant permissions

### /defaults — Общие настройки

**Layout:** Вертикальные секции

**Секции:**
1. **Default Baseline**: выбор baseline промпта для всех агентов
2. **Context Variables**: список ctx-переменных для промптов
   - Пример: `{{user.department}}`, `{{tenant.name}}`, `{{current_date}}`
3. **Default Permissions**: политики доступа по умолчанию
   - Таблица инструментов с чекбоксами (allowed/denied)
   - Таблица коллекций с чекбоксами (allowed/denied)
4. **Default Credentials**: креды для инстансов (scope=default)

---

## AI Section

### /models — Модели

**Компонент:** `<DataTable>`

**Колонки:**
- Alias
- Name
- Type (embedding | rerank | llm)
- Provider
- Status (available | unavailable)
- Default for type
- Actions

**Фильтры:**
- По типу
- По провайдеру
- По статусу

**Действия:**
- Добавить модель
- Редактировать
- Установить как default
- Деактивировать

### /prompts — Реестр промптов

**Компонент:** `<DataTable>`

**Колонки:**
- Slug
- Name
- Type (prompt | baseline)
- Active version
- Total versions
- Status (draft | active | archived)
- Updated At

**Фильтры:**
- По типу
- По статусу
- Поиск по slug/name

**Действия:**
- Создать промпт
- Просмотреть детали

### /prompts/:slug — Детальный вид промпта

**Layout:** 3 блока (вертикально)

**Блок 1: Основная информация**
- Slug, Name, Description, Type
- Кнопки: Создать новую версию, Архивировать

**Блок 2: Версии**
- **Левая часть**: Таблица версий
  - Version number
  - Status (draft | active | archived)
  - Created At
  - Actions (Редактировать, Активировать, Архивировать)
- **Правая часть**: Превью выбранной версии
  - Template (Jinja2)
  - Input variables
  - Generation config

**Блок 3: История изменений**
- Audit log для этого промпта (кто, когда, что изменил)
- Скролируемый список

### /prompts/:slug/edit — Редактирование версии

**Layout:** 2 колонки

**Левая колонка:**
- Version info (number, status)
- Template editor (Monaco/CodeMirror)
- Input variables (список)
- Generation config (JSON editor)
- Кнопки: Сохранить, Отмена, Активировать

**Правая колонка:**
- **Preview**: рендер промпта с тестовыми данными
- **Variables help**: описание доступных ctx-переменных
- **Validation**: ошибки в template/config

### /tools — Инструменты

**Компонент:** `<DataTable>`

**Колонки:**
- Slug
- Name
- Type (api | function | database)
- Instances count
- Status (active | inactive)
- Actions

**Фильтры:**
- По типу
- По статусу
- Поиск по slug/name

**Действия:**
- Просмотреть детали (read-only, синхронизируется из кода)

### /agents — Реестр агентов

**Компонент:** `<DataTable>`

**Колонки:**
- Slug
- Name
- System Prompt
- Baseline
- Tools count
- Status (active | inactive)
- Actions

**Фильтры:**
- По статусу
- По промпту
- Поиск по slug/name

**Действия:**
- Создать агента
- Редактировать
- Дублировать
- Деактивировать

### /agents/:slug — Редактирование агента

**Layout:** 2 колонки

**Левая колонка:**
- Основная информация
  - Slug, Name, Description
  - System Prompt (выбор из списка активных)
  - Baseline Prompt (опционально, выбор из baseline промптов)
  - Generation config (JSON editor)
  - Capabilities (список тегов)
  - Supports partial mode (чекбокс)
  - Enable logging (чекбокс)
- Кнопки: Сохранить, Отмена, Просмотреть промпт

**Правая колонка:**
- **Инструменты**: таблица с чекбоксами
  - Tool slug
  - Required (чекбокс)
  - Recommended (чекбокс)
- **Коллекции**: таблица с чекбоксами
  - Collection slug
  - Required (чекбокс)
  - Recommended (чекбокс)
- **Policy**: JSON editor для execution policy
  - max_steps, max_tool_calls_total, max_wall_time_ms
  - retry config
  - output config

**Модальное окно "Просмотр промпта":**
- Показывает финальный промпт с учетом:
  - System prompt template
  - Merged baseline (default + agent)
  - Tools instructions
  - Collections context

### /agents/:slug/test — A/B тестирование (TODO)

**Layout:** 2 колонки

**Левая колонка:**
- Выбор 2 версий промпта для сравнения
- Тестовый запрос (textarea)
- Кнопка: Запустить тест

**Правая колонка:**
- **Результаты**: side-by-side сравнение
  - Ответ версии A
  - Ответ версии B
  - Метрики (tokens, duration, tool calls)
- **История тестов**: список предыдущих запусков

---

## Integrations Section

### /instances — Инстансы инструментов

**Компонент:** `<DataTable>`

**Колонки:**
- Slug
- Name
- Tool
- Health status (healthy | unhealthy | unknown)
- Credentials count
- Last health check
- Actions

**Фильтры:**
- По инструменту
- По health status
- Поиск по slug/name

**Действия:**
- Создать инстанс
- Редактировать
- Health check
- Деактивировать

### /instances/:id — Просмотр инстанса

**Layout:** 2 колонки

**Левая колонка:**
- Основная информация
  - Slug, Name, Tool
  - Connection config (JSON, без кредов)
  - Health status
  - Last health check
- Кнопки: Редактировать, Health check, Деактивировать

**Правая колонка:**
- **Креды**: список credential sets
  - Scope (default | tenant | user)
  - Auth type
  - Status (active | inactive)
  - Is default (для scope)
  - Actions (Редактировать, Деактивировать)
- **Использование**: агенты, использующие этот инстанс
- **Метрики**: количество вызовов, ошибки (если есть)

### /collections — Коллекции

**Компонент:** `<DataTable>`

**Колонки:**
- Slug
- Name
- Tenant
- Row count
- Vector search (да/нет)
- Vectorization progress (%)
- Status (active | inactive)
- Actions

**Фильтры:**
- По департаменту
- По наличию векторного поиска
- По статусу
- Поиск по slug/name

**Действия:**
- Создать коллекцию
- Редактировать
- Векторизовать
- Деактивировать

### /collections/:id — Просмотр коллекции

**Layout:** 2 колонки

**Левая колонка:**
- Основная информация
  - Slug, Name, Tenant, Description
  - Table name
  - Row count
  - Status
- Кнопки: Редактировать, Векторизовать, Деактивировать

**Правая колонка:**
- **Схема полей**: таблица
  - Field name
  - Type
  - Required
  - Search modes
- **Векторизация**: прогресс-бар
  - Total rows / Vectorized rows / Failed rows
  - Total chunks
  - Qdrant collection name
- **Данные**: превью первых 10 строк (таблица)
- **Использование**: агенты, использующие эту коллекцию

---

## Logs Section

### /agent-runs — Запуски агентов

**Компонент:** `<DataTable>`

**Колонки:**
- Agent
- User
- Tenant
- Status (running | completed | failed | cancelled)
- Duration (ms)
- Tool calls
- Tokens used
- Created At
- Actions

**Фильтры:**
- По агенту
- По пользователю
- По департаменту
- По статусу
- По дате (date range picker)

**Действия:**
- Просмотреть детали
- Экспорт (TODO)

### /agent-runs/:id — Детальный просмотр запуска

**Layout:** Вертикальные секции

**Секция 1: Основная информация**
- Agent, User, Tenant, Chat ID
- Status, Duration, Tokens used
- Input text, Output text

**Секция 2: Шаги выполнения**
- Timeline с шагами (step_number, step_type, status, duration)
- Для каждого шага:
  - **LLM call**: input/output
  - **Tool call**: tool_slug, input, output
  - **Final answer**: финальный ответ

**Секция 3: Метрики**
- Total steps, Total tool calls
- Tokens breakdown (по шагам)
- Error message (если failed)

### /audit — Audit logs

**Компонент:** `<DataTable>`

**Колонки:**
- Endpoint
- Method
- User
- Tenant
- Status code
- Duration (ms)
- Created At
- Actions

**Фильтры:**
- По endpoint
- По методу
- По пользователю
- По статус коду
- По дате (date range picker)

**Действия:**
- Просмотреть детали (модальное окно с request/response data)

---

## UI Components

### DataTable (переиспользуемый компонент)

**Props:**
```typescript
interface DataTableProps<T> {
  data: T[];
  columns: ColumnDef<T>[];
  filters?: FilterConfig[];
  searchPlaceholder?: string;
  onRowClick?: (row: T) => void;
  actions?: ActionConfig[];
  pagination?: PaginationConfig;
  sorting?: SortingConfig;
  // CSV export пока заблокирован (TODO)
}
```

**Features:**
- Сортировка по колонкам
- Фильтры (dropdown, checkbox, date range)
- Поиск (debounced)
- Пагинация (client-side или server-side)
- Row actions (dropdown menu)
- Responsive (скрывает колонки на мобильных)

**Технологии:**
- TanStack Table v8
- CSS Modules
- Shared UI components (Button, Input, Dropdown, etc.)

### Layout Patterns

**2-column layout:**
```
┌─────────────────────────────────────────────┐
│  Left (40%)         │  Right (60%)          │
│  - Main info        │  - Related entities   │
│  - Actions          │  - Nested tables      │
│                     │  - History            │
└─────────────────────────────────────────────┘
```

**3-block vertical layout:**
```
┌─────────────────────────────────────────────┐
│  Block 1: Main info + Actions               │
├─────────────────────────────────────────────┤
│  Block 2: Content (2 columns)               │
│  - Left: List/Table                         │
│  - Right: Preview/Details                   │
├─────────────────────────────────────────────┤
│  Block 3: History (scrollable)              │
└─────────────────────────────────────────────┘
```

---

## Access Control

### Роли и доступ

**admin:**
- Полный доступ ко всем разделам
- Может создавать/редактировать/удалять любые сущности
- Видит данные всех департаментов

**tenant_admin:**
- Доступ к своему департаменту
- Может создавать/редактировать:
  - Пользователей своего департамента
  - Коллекции своего департамента
  - Креды (scope=tenant и scope=user для своих пользователей)
  - Политики доступа (scope=tenant)
- Не может:
  - Создавать агентов/промпты (только admin)
  - Редактировать общие настройки
  - Видеть данные других департаментов (если нет политики доступа)

**user:**
- Доступ только к своему ЛК
- Может создавать/редактировать:
  - Свои креды (scope=user)
- Видит:
  - Список доступных агентов
  - Свою историю запусков
- Не имеет доступа к админке

---

## TODO Features

- [ ] A/B тестирование промптов
- [ ] Экспорт CSV из таблиц
- [ ] Notifications для health checks
- [ ] Rate limiting dashboard
- [ ] Advanced analytics (графики, тренды)
- [ ] Bulk actions в таблицах
- [ ] Template marketplace
