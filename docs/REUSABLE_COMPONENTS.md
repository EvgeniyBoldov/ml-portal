# Переиспользуемые UI Компоненты

Руководство по использованию переиспользуемых компонентов в ML Portal.

## 📋 DataTable

**Расположение:** `apps/web/src/shared/ui/DataTable`

Универсальный компонент таблицы с поддержкой выбора строк, поиска, пагинации и кастомных рендереров.

### Основные возможности

- ✅ Выбор строк (single/multiple) с правильной логикой чекбоксов
- 🔍 Поиск и фильтрация
- 📄 Пагинация с настраиваемым размером страницы
- 🎨 Кастомные рендереры ячеек
- 🔧 Bulk actions для выбранных строк
- 📱 Адаптивный дизайн

### Пример использования

```tsx
import DataTable, { DataTableColumn } from '@shared/ui/DataTable';

interface User {
  id: string;
  name: string;
  email: string;
  role: string;
}

const columns: DataTableColumn<User>[] = [
  { 
    key: 'name', 
    label: 'Имя',
    width: 200,
  },
  { 
    key: 'email', 
    label: 'Email',
    render: (user) => <a href={`mailto:${user.email}`}>{user.email}</a>
  },
  { 
    key: 'role', 
    label: 'Роль',
    render: (user) => <Badge>{user.role}</Badge>
  },
];

function UsersTable() {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState('');
  
  return (
    <DataTable
      columns={columns}
      data={users}
      keyField="id"
      
      // Selection
      selectable
      selectedKeys={selectedIds}
      onSelectionChange={setSelectedIds}
      
      // Search
      searchable
      searchValue={searchQuery}
      onSearchChange={setSearchQuery}
      searchPlaceholder="Поиск пользователей..."
      
      // Pagination
      paginated
      pageSize={50}
      pageSizeOptions={[25, 50, 100]}
      
      // Bulk actions
      bulkActions={
        <Button 
          variant="danger" 
          onClick={() => handleDelete(Array.from(selectedIds))}
        >
          Удалить выбранные
        </Button>
      }
      
      // Empty state
      emptyText="Пользователи не найдены"
    />
  );
}
```

### Props

#### Основные

- `columns: DataTableColumn[]` - Конфигурация колонок
- `data: T[]` - Массив данных для отображения
- `keyField: string` - Поле для уникального ключа строки

#### Selection (Выбор строк)

- `selectable?: boolean` - Включить выбор строк
- `selectedKeys?: Set<string | number>` - Контролируемое состояние выбранных ключей
- `onSelectionChange?: (keys: Set<string | number>) => void` - Callback при изменении выбора

#### Search (Поиск)

- `searchable?: boolean` - Включить поиск
- `searchValue?: string` - Контролируемое значение поиска
- `onSearchChange?: (value: string) => void` - Callback при изменении поиска
- `searchPlaceholder?: string` - Placeholder для поля поиска
- `searchFilter?: (row: T, query: string) => boolean` - Кастомная функция фильтрации

#### Pagination (Пагинация)

- `paginated?: boolean` - Включить пагинацию
- `pageSize?: number` - Размер страницы (default: 50)
- `currentPage?: number` - Текущая страница
- `totalItems?: number` - Общее количество элементов (для серверной пагинации)
- `onPageChange?: (page: number) => void` - Callback при смене страницы
- `onPageSizeChange?: (size: number) => void` - Callback при смене размера страницы
- `pageSizeOptions?: number[]` - Опции размера страницы (default: [25, 50, 100])

#### Дополнительно

- `bulkActions?: React.ReactNode` - Компоненты для массовых действий
- `emptyState?: React.ReactNode` - Кастомное состояние пустой таблицы
- `emptyText?: string` - Текст для пустой таблицы
- `loading?: boolean` - Состояние загрузки
- `className?: string` - Дополнительные CSS классы
- `rowClassName?: (row: T, index: number) => string` - Функция для кастомных классов строк
- `onRowClick?: (row: T, index: number) => void` - Callback при клике на строку

### DataTableColumn

```tsx
interface DataTableColumn<T> {
  key: string;                    // Ключ поля в данных
  label: string;                  // Заголовок колонки
  width?: number | string;        // Ширина колонки
  align?: 'left' | 'center' | 'right'; // Выравнивание
  sortable?: boolean;             // Сортируемая колонка (будет реализовано)
  render?: (row: T, index: number) => React.ReactNode; // Кастомный рендер
  className?: string;             // CSS класс для ячейки
}
```

### Режимы работы

#### Контролируемый режим

Полный контроль над состоянием извне:

```tsx
const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
const [searchValue, setSearchValue] = useState('');
const [currentPage, setCurrentPage] = useState(1);

<DataTable
  selectedKeys={selectedKeys}
  onSelectionChange={setSelectedKeys}
  searchValue={searchValue}
  onSearchChange={setSearchValue}
  currentPage={currentPage}
  onPageChange={setCurrentPage}
  // ...
/>
```

#### Неконтролируемый режим

Компонент управляет состоянием сам:

```tsx
<DataTable
  selectable
  searchable
  paginated
  // Не передаем selectedKeys, searchValue, currentPage
  // ...
/>
```

### Особенности выбора строк

DataTable правильно обрабатывает выбор строк:

- ✅ Выбор всех строк **на текущей странице**
- ✅ Indeterminate состояние чекбокса "Выбрать все" (когда выбраны не все)
- ✅ Сохранение выбора при переключении страниц
- ✅ Правильная работа при фильтрации

### Стилизация

DataTable использует CSS модули. Основные классы:

- `.container` - Контейнер таблицы
- `.toolbar` - Панель инструментов (поиск, bulk actions)
- `.table` - Сама таблица
- `.selected` - Выбранная строка
- `.pagination` - Панель пагинации

Для кастомизации можно передать `className` или использовать `rowClassName`.

---

## 🎨 Другие UI компоненты

### Button

**Расположение:** `apps/web/src/shared/ui/Button`

```tsx
<Button variant="primary">Сохранить</Button>
<Button variant="secondary">Отмена</Button>
<Button variant="danger">Удалить</Button>
<Button variant="outline">Назад</Button>
```

**Props:**
- `variant?: 'primary' | 'secondary' | 'danger' | 'outline'`
- `size?: 'small' | 'medium' | 'large'`
- `disabled?: boolean`

### Badge

**Расположение:** `apps/web/src/shared/ui/Badge`

```tsx
<Badge tone="success">Активен</Badge>
<Badge tone="info">v1.2.3</Badge>
<Badge tone="neutral">Неактивен</Badge>
<Badge tone="danger">Ошибка</Badge>
```

**Props:**
- `tone?: 'success' | 'info' | 'neutral' | 'danger' | 'warning'`
- `size?: 'small' | 'medium'`

### Input

**Расположение:** `apps/web/src/shared/ui/Input`

```tsx
<Input 
  placeholder="Введите текст..."
  value={value}
  onChange={(e) => setValue(e.target.value)}
  disabled={false}
/>
```

### Textarea

**Расположение:** `apps/web/src/shared/ui/Textarea`

```tsx
<Textarea 
  rows={5}
  placeholder="Описание..."
  value={value}
  onChange={(e) => setValue(e.target.value)}
/>
```

### Modal

**Расположение:** `apps/web/src/shared/ui/Modal`

```tsx
<Modal
  open={isOpen}
  onClose={() => setIsOpen(false)}
  title="Подтверждение"
>
  <p>Вы уверены?</p>
  <Button onClick={handleConfirm}>Да</Button>
</Modal>
```

### Alert

**Расположение:** `apps/web/src/shared/ui/Alert`

```tsx
<Alert
  variant="danger"
  title="Ошибка"
  description="Не удалось выполнить операцию"
/>
```

**Props:**
- `variant?: 'info' | 'success' | 'warning' | 'danger'`
- `title?: string`
- `description?: string`

### Icon

**Расположение:** `apps/web/src/shared/ui/Icon`

```tsx
<Icon name="check" size={20} />
<Icon name="trash" size={16} />
```

Использует Lucide icons.

---

## 📝 Best Practices

### 1. Всегда используйте переиспользуемые компоненты

❌ **Плохо:**
```tsx
<button className="custom-button">Кнопка</button>
```

✅ **Хорошо:**
```tsx
<Button variant="primary">Кнопка</Button>
```

### 2. Используйте DataTable для всех таблиц

❌ **Плохо:**
```tsx
<table>
  <thead>...</thead>
  <tbody>
    {data.map(item => <tr>...</tr>)}
  </tbody>
</table>
```

✅ **Хорошо:**
```tsx
<DataTable
  columns={columns}
  data={data}
  keyField="id"
  searchable
  paginated
/>
```

### 3. Контролируйте состояние когда нужно

Используйте контролируемый режим когда:
- Нужно синхронизировать состояние с URL
- Нужно сохранять состояние в localStorage
- Нужно реагировать на изменения извне

Используйте неконтролируемый режим для простых случаев.

### 4. Используйте кастомные рендереры

```tsx
const columns: DataTableColumn<User>[] = [
  {
    key: 'status',
    label: 'Статус',
    render: (user) => (
      <Badge tone={user.isActive ? 'success' : 'neutral'}>
        {user.isActive ? 'Активен' : 'Неактивен'}
      </Badge>
    )
  }
];
```

### 5. Добавляйте bulk actions

```tsx
<DataTable
  selectable
  bulkActions={
    <>
      <Button onClick={handleExport}>Экспорт</Button>
      <Button variant="danger" onClick={handleDelete}>
        Удалить
      </Button>
    </>
  }
/>
```

---

## 🔧 Расширение компонентов

Если нужна дополнительная функциональность:

1. Проверьте, можно ли решить через props
2. Используйте `className` и `rowClassName` для стилизации
3. Используйте `render` для кастомного содержимого
4. Если нужно больше - создайте обертку или расширьте компонент

---

## 📚 Примеры использования в проекте

### CollectionDataPage

Использует DataTable с:
- Выбором строк
- Поиском
- Пагинацией
- Bulk delete

**Файл:** `apps/web/src/domains/collections/pages/CollectionDataPage.tsx`

### PromptRegistryPage

Использует стандартную таблицу с кастомными ячейками.

**TODO:** Рефакторить на DataTable

**Файл:** `apps/web/src/domains/admin/pages/PromptRegistryPage.tsx`

---

## 🚀 Roadmap

Планируемые улучшения DataTable:

- [ ] Сортировка колонок
- [ ] Фильтры по колонкам
- [ ] Экспорт в CSV/Excel
- [ ] Виртуализация для больших данных
- [ ] Drag & drop для переупорядочивания
- [ ] Группировка строк
- [ ] Expandable rows

---

## 💡 Советы

1. **Производительность:** Для больших таблиц (>1000 строк) используйте серверную пагинацию
2. **Доступность:** DataTable поддерживает keyboard navigation (Tab, Enter, Esc)
3. **Мобильные устройства:** Таблица адаптивна, но для очень маленьких экранов рассмотрите альтернативный вид (карточки)
4. **Тестирование:** Используйте `data-testid` для тестирования выбора и действий

---

Обновлено: 21.01.2026
