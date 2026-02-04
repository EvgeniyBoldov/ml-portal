# Admin Design System

## Принципы

1. **Переиспользование** — Всегда сначала ищи компонент в `@/shared/ui`
2. **Консистентность** — Все страницы используют одинаковую структуру
3. **Минимализм** — Не создавай новые стили, используй существующие
4. **Унификация** — Все entity страницы следуют единым паттернам

## Структура страницы

### Entity Pages (Prompt, Baseline, Policy)

```
PageContent
├── PageHeader (title, subtitle, actions)
└── BaseLayout
    ├── BaseLayout.Left
    │   ├── EntityInfoBlock
    │   └── VersionsBlock (для prompt/baseline)
    └── BaseLayout.Right
        ├── StatusBlock (для baseline)
        ├── TemplateEditor (для prompt)
        └── Tabs (для policy)
```

### Registry Pages (Users, Models, Tools, etc.)

```
PageContent
├── PageHeader (title, subtitle, actions)
├── FilterBar (filters, search)
└── DataTable
```

## Компоненты

### Layout

| Компонент | Путь | Описание |
|-----------|------|----------|
| `PageHeader` | `@/shared/ui/PageHeader` | Заголовок страницы с кнопками |
| `PageContent` | `@/shared/ui/PageContent` | Контейнер контента с padding |
| `BaseLayout` | `@/shared/ui/BaseLayout` | Унифицированный лейаут для entity страниц |
| `FilterBar` | `@/shared/ui/FilterBar` | Фильтры и поиск |

### Entity Blocks

| Компонент | Путь | Описание |
|-----------|------|----------|
| `EntityInfoBlock` | `@/shared/ui/EntityInfoBlock` | Информация о сущности (name, description, etc.) |
| `StatusBlock` | `@/shared/ui/StatusBlock` | Статус сущности с действиями |
| `VersionsBlock` | `@/shared/ui/VersionsBlock` | Таблица версий с действиями |

### Data Display

| Компонент | Путь | Описание |
|-----------|------|----------|
| `DataTable` | `@/shared/ui/DataTable` | Таблица с сортировкой, фильтрацией, пагинацией |
| `Badge` | `@/shared/ui/Badge` | Статус/тип в цветном овале |
| `StatusBadge` | `@/shared/ui/StatusBadge` | Статус с предустановленными цветами |
| `Card` | `@/shared/ui/Card` | Карточка контента |

### Forms

| Компонент | Путь | Описание |
|-----------|------|----------|
| `Input` | `@/shared/ui/Input` | Текстовое поле |
| `Textarea` | `@/shared/ui/Textarea` | Многострочное поле |
| `Select` | `@/shared/ui/Select` | Выпадающий список |
| `Toggle` | `@/shared/ui/Toggle` | Переключатель (НЕ Switch!) |
| `Checkbox` | `@/shared/ui/Checkbox` | Чекбокс |

### Actions

| Компонент | Путь | Описание |
|-----------|------|----------|
| `Button` | `@/shared/ui/Button` | Кнопка (primary, outline, ghost, danger) |
| `RowActions` | `@/shared/ui/RowActions` | Действия в строке таблицы |
| `DropdownMenu` | `@/shared/ui/DropdownMenu` | Выпадающее меню |

### Feedback

| Компонент | Путь | Описание |
|-----------|------|----------|
| `Modal` | `@/shared/ui/Modal` | Модальное окно |
| `Alert` | `@/shared/ui/Alert` | Уведомление |
| `Skeleton` | `@/shared/ui/Skeleton` | Загрузка |
| `EmptyState` | `@/shared/ui/EmptyState` | Пустое состояние |

## Хуки конфигурации

### useStatusConfig
```tsx
const statusConfig = useStatusConfig('prompt'); // 'prompt' | 'baseline' | 'policy'
// Возвращает: { labels, tones, options }
```

### useEntityActions
```tsx
const actions = useEntityActions(entity, type);
// Возвращает стандартизированные действия для сущности
```

## Примеры использования

### Entity страница (Prompt/Baseline)

```tsx
import { PageContent, PageHeader, BaseLayout, EntityInfoBlock, VersionsBlock, StatusBlock } from '@/shared/ui';
import { useStatusConfig } from '@/shared/hooks';

export function PromptEditorPage() {
  const statusConfig = useStatusConfig('prompt');
  
  return (
    <PageContent>
      <PageHeader 
        title="Промпт"
        subtitle="Управление промптом и версиями"
        actions={actions}
      />
      <BaseLayout type="split">
        <BaseLayout.Left>
          <EntityInfoBlock entity={prompt} editable={isEditable} />
          <VersionsBlock 
            versions={versions} 
            selectedVersion={selectedVersion}
            onVersionSelect={setVersion}
          />
        </BaseLayout.Left>
        <BaseLayout.Right>
          <TemplateEditor 
            template={selectedVersion?.template}
            onChange={updateTemplate}
          />
        </BaseLayout.Right>
      </BaseLayout>
    </PageContent>
  );
}
```

### Entity страница (Policy)

```tsx
import { PageContent, PageHeader, BaseLayout, Tabs, EntityInfoBlock } from '@/shared/ui';

export function PolicyEditorPage() {
  return (
    <PageContent>
      <PageHeader title="Policy" actions={actions} />
      <BaseLayout type="tabs">
        <Tabs activeTab={activeTab} onChange={setTab}>
          <TabPanel value="overview">
            <EntityInfoBlock entity={policy} />
          </TabPanel>
          <TabPanel value="versions">
            <VersionsBlock versions={versions} />
          </TabPanel>
        </Tabs>
      </BaseLayout>
    </PageContent>
  );
}
```

### Registry страница

```tsx
import { PageContent, PageHeader, FilterBar, DataTable, Badge } from '@/shared/ui';

export function UsersPage() {
  const columns = [
    { key: 'name', label: 'Имя' },
    { key: 'role', label: 'Роль', render: (row) => <Badge>{row.role}</Badge> },
    { key: 'actions', label: '', render: (row) => <RowActions ... /> },
  ];

  return (
    <PageContent>
      <PageHeader 
        title="Пользователи" 
        subtitle="Управление пользователями системы"
        actions={[{ label: 'Создать', onClick: () => navigate('/admin/users/new'), variant: 'primary' }]}
      />
      <FilterBar 
        searchValue={search}
        onSearchChange={setSearch}
        filters={[{ key: 'role', label: 'Роль', options: [...], value: roleFilter, onChange: setRoleFilter }]}
      />
      <DataTable columns={columns} data={users} keyField="id" />
    </PageContent>
  );
}
```

## CSS Variables

Используй переменные из `tokens.css` и тем:

```css
/* Цвета */
--bg-primary (НЕ --color-bg)
--bg-secondary
--text-primary (НЕ --color-text)
--text-secondary
--border-color (НЕ --border)

/* Семантические */
--color-primary
--color-success
--color-warning
--color-danger

/* Размеры */
--radius-sm
--radius-md
--radius-lg
--sp-1, --sp-2, --sp-3, --sp-4
```

## Правила

1. **НЕ создавай inline styles** — используй CSS modules
2. **НЕ дублируй компоненты** — ищи в `@/shared/ui`
3. **НЕ хардкодь цвета** — используй CSS variables
4. **НЕ импортируй стили других страниц** — каждая страница имеет свой .module.css
5. **Используй BaseLayout** для всех entity страниц
6. **Используй DataTable** для всех таблиц
7. **Используй useStatusConfig** для конфигурации статусов
8. **Используй EntityInfoBlock** для информации о сущностях
9. **Используй VersionsBlock** для управления версиями
