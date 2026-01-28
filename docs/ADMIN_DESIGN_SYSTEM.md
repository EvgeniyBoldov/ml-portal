# Admin Design System

## Принципы

1. **Переиспользование** — Всегда сначала ищи компонент в `@/shared/ui`
2. **Консистентность** — Все страницы используют одинаковую структуру
3. **Минимализм** — Не создавай новые стили, используй существующие

## Структура страницы

```
AdminLayout
└── PageContent
    ├── PageHeader (title, subtitle, actions)
    ├── FilterBar (filters, search)
    └── Content (DataTable / Form / Cards)
```

## Компоненты

### Layout

| Компонент | Путь | Описание |
|-----------|------|----------|
| `PageHeader` | `@/shared/ui/PageHeader` | Заголовок страницы с кнопками |
| `PageContent` | `@/shared/ui/PageContent` | Контейнер контента с padding |
| `FilterBar` | `@/shared/ui/FilterBar` | Фильтры и поиск |

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
| `Switch` | `@/shared/ui/Switch` | Переключатель |
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

## Примеры использования

### Страница списка (Registry)

```tsx
import { PageHeader, PageContent, FilterBar, DataTable, Badge } from '@/shared/ui';

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

### Страница создания/редактирования

```tsx
import { PageHeader, PageContent, Input, Textarea, Button, Card } from '@/shared/ui';

export function UserEditorPage() {
  return (
    <PageContent>
      <PageHeader 
        title="Создать пользователя" 
        backTo="/admin/users"
      />
      <form>
        <Card>
          <Input label="Email" value={email} onChange={...} />
          <Select label="Роль" options={...} value={role} onChange={...} />
          <div className={styles.actions}>
            <Button variant="outline" onClick={() => navigate(-1)}>Отмена</Button>
            <Button variant="primary" type="submit">Создать</Button>
          </div>
        </Card>
      </form>
    </PageContent>
  );
}
```

## CSS Variables

Используй переменные из `tokens.css`:

```css
/* Цвета */
--color-primary
--color-text
--color-text-muted
--color-border
--color-danger
--color-success
--color-warning

/* Фоны */
--bg-primary
--bg-secondary
--panel

/* Размеры */
--radius
--radius-lg
```

## Правила

1. **НЕ создавай inline styles** — используй CSS modules
2. **НЕ дублируй компоненты** — ищи в `@/shared/ui`
3. **НЕ хардкодь цвета** — используй CSS variables
4. **Используй PageHeader** для всех страниц
5. **Используй DataTable** для всех таблиц
6. **Используй Badge** для статусов и типов
