# Миграция страниц на AdminPage

## Статус миграции

### ✅ Готово (4 страницы)
- `DashboardPage.tsx` - Dashboard с карточками статистики
- `ModelsPage.tsx` - Реестр моделей с поиском и health check
- `PromptsListPage.tsx` - Реестр промптов с фильтром типа
- `UsersPage.tsx` - Реестр пользователей с поиском

### 🔄 Требуют конвертации (7 страниц)
- `AgentRegistryPage.tsx` - Реестр агентов
- `ToolsPage.tsx` - Реестр инструментов
- `InstancesPage.tsx` - Реестр инстансов
- `CollectionsPage.tsx` - Реестр коллекций
- `PoliciesPage.tsx` - Реестр политик
- `AuditPage.tsx` - Журнал аудита
- `RoutingLogsPage.tsx` - Логи маршрутизации

### ⊘ Не требуют (Editor/View страницы)
Editor и View страницы используют другую структуру (PageContent + PageHeader) и не нуждаются в конвертации на AdminPage.

## Паттерн конвертации

### Было (старая структура)
```tsx
import Button from '@shared/ui/Button';
import Input from '@shared/ui/Input';
import styles from './RegistryPage.module.css';

export function SomePage() {
  const [q, setQ] = useState('');
  
  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <h1 className={styles.title}>Заголовок</h1>
            <p className={styles.subtitle}>Описание</p>
          </div>
          <div className={styles.controls}>
            <Input
              placeholder="Поиск..."
              value={q}
              onChange={e => setQ(e.target.value)}
              className={styles.search}
            />
            <Link to="/admin/something/new">
              <Button>Создать</Button>
            </Link>
          </div>
        </div>

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            {/* ... */}
          </table>
        </div>
      </div>
    </div>
  );
}
```

### Стало (AdminPage)
```tsx
import { AdminPage } from '@/shared/ui';
import Button from '@shared/ui/Button';
import styles from './RegistryPage.module.css';

export function SomePage() {
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  
  return (
    <AdminPage
      title="Заголовок"
      subtitle="Описание"
      searchValue={q}
      onSearchChange={setQ}
      searchPlaceholder="Поиск..."
      actions={[
        {
          label: 'Создать',
          onClick: () => navigate('/admin/something/new'),
          variant: 'primary',
        },
      ]}
    >
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          {/* ... */}
        </table>
      </div>
    </AdminPage>
  );
}
```

## Шаги конвертации

### 1. Обновить импорты
```tsx
// Добавить
import { AdminPage } from '@/shared/ui';

// Удалить (если не используется в теле)
import Input from '@shared/ui/Input';
```

### 2. Заменить структуру
- Удалить `<div className={styles.wrap}>` и `<div className={styles.card}>`
- Заменить на `<AdminPage>`
- Перенести title/subtitle в props
- Перенести поиск в `searchValue`/`onSearchChange`
- Перенести кнопки в `actions`

### 3. Опциональные props AdminPage
```tsx
<AdminPage
  title="Заголовок"              // Обязательно
  subtitle="Описание"            // Опционально
  searchValue={q}                // Опционально (только если нужен поиск)
  onSearchChange={setQ}          // Опционально
  searchPlaceholder="Поиск..."   // Опционально
  controls={<Select ... />}      // Опционально (фильтры)
  actions={[...]}                // Опционально (кнопки)
  backTo="/admin/something"      // Опционально (кнопка назад)
>
  {/* Контент */}
</AdminPage>
```

## Преимущества AdminPage

1. **Единый интерфейс** — все реестры выглядят одинаково
2. **Меньше кода** — не нужно дублировать структуру header/controls
3. **Гибкость** — опциональные элементы (поиск, фильтры, кнопки)
4. **Правильная архитектура** — header + content в одной рамке
5. **Не показываем пустые элементы** — controls рендерятся только если переданы

## Примеры

### С поиском и кнопкой
```tsx
<AdminPage
  title="Модели"
  subtitle="Управление LLM и Embedding моделями"
  searchValue={search}
  onSearchChange={setSearch}
  actions={[{ label: 'Добавить', onClick: ..., variant: 'primary' }]}
>
  <DataTable ... />
</AdminPage>
```

### С фильтрами
```tsx
<AdminPage
  title="Промпты"
  subtitle="Управление системными промптами"
  searchValue={search}
  onSearchChange={setSearch}
  controls={<Select value={type} onChange={...} options={...} />}
  actions={[{ label: 'Создать', onClick: ... }]}
>
  <DataTable ... />
</AdminPage>
```

### Без поиска
```tsx
<AdminPage
  title="Дашборд"
  subtitle="Обзор системы"
  actions={[{ label: 'Обновить', onClick: ..., variant: 'outline' }]}
>
  <div className={styles.content}>
    {/* Карточки статистики */}
  </div>
</AdminPage>
```

## Что НЕ конвертировать

- **Editor страницы** (Create/Edit) — используют PageContent + PageHeader
- **View страницы** (Detail) — используют PageContent + PageHeader
- **Entity страницы** (View/Edit/Create в одной) — используют PromptEntityPage паттерн

Конвертируем только **реестровые страницы** (List/Registry) с таблицами.
