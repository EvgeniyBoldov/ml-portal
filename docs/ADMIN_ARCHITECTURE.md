# Admin Portal Architecture

## Термины

**Entity** — бизнес-сущность (Agent, User, Tenant, Model, Instance)

**List** — список сущностей (таблица)

**Entity Page** — страница конкретной сущности (View / Edit / Create)

**Domain Block** — переиспользуемый бизнес-блок (`InstancesBlock`, `ToolsBlock`, `ModelsAccessBlock`)

---

## 1. Таблицы (List View)

### Назначение
Таблица — **только список и навигация**.

### Правила
- ✅ Клик по строке = переход в View Entity Page
- ❌ НЕ редактирует
- ❌ НЕ содержит сложные формы
- ❌ НЕ является основным местом взаимодействия

### Действия
- **Primary action:** клик по строке (View)
- **Secondary actions:** через `Actions / …`
  - Edit
  - Duplicate
  - Delete
  - Enable / Disable

---

## 2. Entity Page (View / Edit / Create)

### Принцип
**Одна страница = три режима:**
- View (по умолчанию)
- Edit
- Create

❌ НЕ три разных экрана
❌ НЕ модалки для сложных сущностей

---

## 3. View Mode (по умолчанию)

### Назначение
View Mode — **безопасный режим просмотра**

Пользователь должен чувствовать:
- я ничего не ломаю
- я просто смотрю

### UI-правила
- Все поля readonly
- Нет input / select
- Есть кнопка **Редактировать**
- Допустимы **атомарные inline-действия**

### Inline-действия
Разрешены **только если действие**:
- Атомарное
- Обратимое
- Сразу сохраняется

**Примеры:**
- ✅ Активен / Неактивен
- ✅ Включить логирование
- ✅ Подключить / отключить инстанс

**Запрещено:**
- ❌ Менять промпты
- ❌ Менять модели
- ❌ Менять сложные связи

---

## 4. Edit Mode

### Вход в Edit Mode
Только через явное действие:
- Кнопка **Редактировать**
- Или `Actions → Edit`

### Визуальные правила
Edit Mode **обязан быть визуально очевидным**:
- Бейдж `Режим редактирования`
- Sticky header / footer
- Подсветка editable секций

### Save / Cancel — только глобально
> 👉 Save и Cancel существуют только на уровне Entity Page

- ❌ Никаких Save внутри блоков
- ❌ Никаких auto-save для сложных сущностей

**Рекомендуемый паттерн:** sticky footer
```
[ Отмена ]        [ Сохранить ]
```

### Cancel = откат всего
- Cancel всегда отменяет **все изменения**
- Если есть unsaved changes → confirm
- Логика как у модалки

---

## 5. Create Mode

### Create = Edit с другим входом
- Маршрут: `/admin/entities/new`
- Сразу Edit Mode
- Пустые данные

### Поведение кнопок
| Действие | Результат |
|----------|-----------|
| Save | Create entity → View |
| Cancel | Возврат в List |

---

## 6. Domain Blocks

### Что такое Domain Block
Domain Block — это:
- Бизнес-блок
- С фиксированной структурой
- Фиксированными колонками
- Фиксированными действиями
- Одинаковой логикой

**Примеры:**
- `InstancesBlock`
- `ToolsBlock`
- `AgentToolsBlock`

Он **одинаковый** у Tenant, User, Agent. Меняется только **context / data source**.

### Domain Block ≠ UI Component
**Domain Block:**
- Знает бизнес-логику
- Знает правила редактирования
- Имеет View / Edit поведение
- Переиспользуется целиком

Это **уровень выше таблицы**.

### Контракт Domain Block
```ts
interface DomainBlockProps<T> {
  mode: 'view' | 'edit';
  value: T[];
  onChange: (value: T[]) => void;
  context: 'tenant' | 'user' | 'agent';
}
```

Block:
- ❌ НЕ сохраняет данные сам
- ❌ НЕ делает API-коммиты
- ✅ Работает с внешним state

### Поведение Domain Block по режимам

#### View Mode
- Readonly
- Inline-actions допустимы, если атомарны

#### Edit Mode
- Редактируемые элементы
- Изменения только в form state
- Никаких side-effects

---

## 7. Единая форма (Form State)

### Главное правило
> 👉 **Одна Entity Page = один form state**

- Domain Blocks — просто части формы
- Save — один API-запрос
- Cancel — сброс формы

---

## 8. Модалки — строго ограничены

Модалки допустимы **только для:**
- Простых CRUD (2–5 полей)
- Подтверждений
- Quick attach / detach

**Запрещено:**
- ❌ Сложные сущности
- ❌ Много секций
- ❌ Важные конфигурации

---

## 9. Decision Tree

```
Это сущность?
→ Да → Entity Page

Это часть сущности?
→ Да → Domain Block

Нужно сохранить сразу?
→ Да → inline action
→ Нет → Edit Mode

Много полей / секций?
→ Да → НЕ модалка
```

---

## Структура файлов

```
domains/admin/
├── layouts/
│   └── AdminLayout.tsx          # Хедер + сайдбар
├── pages/
│   ├── PromptsListPage.tsx      # List View
│   ├── PromptEntityPage.tsx     # View/Edit/Create в одном
│   └── ...
├── blocks/                       # Domain Blocks
│   ├── InstancesBlock.tsx
│   ├── ToolsBlock.tsx
│   └── ModelsAccessBlock.tsx
└── components/
    └── AdminSidebar.tsx
```

---

## Примеры

### List Page
```tsx
// PromptsListPage.tsx
<PageContent>
  <PageHeader title="Промпты" actions={[{ label: 'Создать', onClick: () => navigate('/admin/prompts/new') }]} />
  <DataTable 
    data={prompts} 
    onRowClick={(row) => navigate(`/admin/prompts/${row.slug}`)} // View
  />
</PageContent>
```

### Entity Page (View/Edit/Create)
```tsx
// PromptEntityPage.tsx
const [mode, setMode] = useState<'view' | 'edit'>('view');
const [formData, setFormData] = useState(initialData);

return (
  <PageContent>
    <PageHeader 
      title={prompt.name}
      actions={mode === 'view' ? [
        { label: 'Редактировать', onClick: () => setMode('edit') }
      ] : []}
    />
    
    {mode === 'edit' && <Badge>Режим редактирования</Badge>}
    
    <PromptForm 
      mode={mode} 
      value={formData} 
      onChange={setFormData} 
    />
    
    {mode === 'edit' && (
      <StickyFooter>
        <Button onClick={() => setMode('view')}>Отмена</Button>
        <Button onClick={handleSave}>Сохранить</Button>
      </StickyFooter>
    )}
  </PageContent>
);
```

### Domain Block
```tsx
// InstancesBlock.tsx
interface InstancesBlockProps {
  mode: 'view' | 'edit';
  value: ToolInstance[];
  onChange: (value: ToolInstance[]) => void;
  context: 'tenant' | 'user' | 'agent';
}

export function InstancesBlock({ mode, value, onChange, context }: InstancesBlockProps) {
  if (mode === 'view') {
    return <InstancesTable data={value} readonly />;
  }
  
  return (
    <div>
      <InstancesTable data={value} onSelect={onChange} />
      <Button onClick={handleAdd}>Добавить инстанс</Button>
    </div>
  );
}
```
