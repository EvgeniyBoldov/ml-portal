# UI Компоненты

## Обзор

Все компоненты находятся в `shared/ui/`. Перед созданием нового компонента — проверь, нет ли подходящего.

## Базовые компоненты

### Button

```tsx
import { Button } from '@shared/ui';

<Button variant="primary" onClick={handleClick}>
  Сохранить
</Button>

<Button variant="outline" disabled={isLoading}>
  Отмена
</Button>

<Button variant="ghost" size="small">
  <Icon name="edit" />
</Button>
```

**Props:**
- `variant`: `'primary'` | `'outline'` | `'ghost'` | `'danger'`
- `size`: `'small'` | `'medium'` | `'large'`
- `disabled`: boolean
- `loading`: boolean

### Input

```tsx
import { Input } from '@shared/ui';

<Input
  label="Название"
  value={name}
  onChange={(e) => setName(e.target.value)}
  error={errors.name}
  required
/>
```

**Props:**
- `label`: string
- `error`: string
- `hint`: string
- `required`: boolean

### Textarea

```tsx
import { Textarea } from '@shared/ui';

<Textarea
  label="Описание"
  value={description}
  onChange={(e) => setDescription(e.target.value)}
  rows={4}
/>
```

### Select

```tsx
import { Select } from '@shared/ui';

<Select
  label="Статус"
  value={status}
  onChange={(value) => setStatus(value)}
  options={[
    { value: 'active', label: 'Активный' },
    { value: 'draft', label: 'Черновик' },
  ]}
/>
```

### Badge

```tsx
import { Badge } from '@shared/ui';

<Badge variant="success">Активен</Badge>
<Badge variant="warning">Черновик</Badge>
<Badge variant="danger">Ошибка</Badge>
<Badge variant="info">Обработка</Badge>
```

**Props:**
- `variant`: `'default'` | `'success'` | `'warning'` | `'danger'` | `'info'`

### Switch

```tsx
import { Switch } from '@shared/ui';

<Switch
  label="Активен"
  checked={isActive}
  onChange={(checked) => setIsActive(checked)}
/>
```

## Layout компоненты

### Modal

```tsx
import { Modal } from '@shared/ui';

<Modal
  isOpen={isOpen}
  onClose={() => setIsOpen(false)}
  title="Подтверждение"
>
  <p>Вы уверены?</p>
  <div className={styles.actions}>
    <Button variant="outline" onClick={() => setIsOpen(false)}>
      Отмена
    </Button>
    <Button variant="danger" onClick={handleDelete}>
      Удалить
    </Button>
  </div>
</Modal>
```

### Popover

```tsx
import { Popover } from '@shared/ui';

<Popover
  trigger={<Button>Фильтры</Button>}
  content={<FilterForm />}
/>
```

**Когда использовать:**
- Небольшие формы/фильтры
- Короткие списки действий
- Tooltips с интерактивом

### DropdownMenu

```tsx
import { DropdownMenu } from '@shared/ui';

<DropdownMenu
  trigger={<Button variant="ghost"><Icon name="more" /></Button>}
  items={[
    { label: 'Редактировать', onClick: handleEdit },
    { label: 'Удалить', onClick: handleDelete, danger: true },
  ]}
/>
```

**Когда использовать:**
- Список действий без дополнительного UI
- Контекстные меню

## Составные компоненты

### DataTable

```tsx
import { DataTable } from '@shared/ui';

<DataTable
  data={agents}
  columns={[
    { key: 'name', title: 'Название', sortable: true },
    { key: 'status', title: 'Статус', render: (row) => <Badge>{row.status}</Badge> },
    { key: 'actions', title: '', render: (row) => <ActionsMenu row={row} /> },
  ]}
  onRowClick={(row) => navigate(`/admin/agents/${row.slug}`)}
  selectable
  onSelectionChange={setSelectedIds}
  pagination={{
    page,
    pageSize,
    total,
    onPageChange: setPage,
  }}
/>
```

### EntityPage

```tsx
import { EntityPage } from '@shared/ui';

<EntityPage
  mode={isCreate ? 'create' : 'edit'}
  title={isCreate ? 'Новый агент' : agent.name}
  breadcrumbs={[
    { label: 'Агенты', href: '/admin/agents' },
    { label: agent?.name || 'Новый' },
  ]}
  actions={
    <>
      <Button variant="outline" onClick={() => navigate(-1)}>
        Отмена
      </Button>
      <Button variant="primary" onClick={handleSave}>
        Сохранить
      </Button>
    </>
  }
>
  {/* Content */}
</EntityPage>
```

### ContentBlock

```tsx
import { ContentBlock, ContentGrid } from '@shared/ui';

<ContentGrid>
  <ContentBlock
    title="Основная информация"
    icon="info"
    width="2/3"
  >
    <Input label="Название" ... />
    <Textarea label="Описание" ... />
  </ContentBlock>
  
  <ContentBlock
    title="Статус"
    icon="activity"
    width="1/3"
  >
    <Switch label="Активен" ... />
  </ContentBlock>
</ContentGrid>
```

**Width options:**
- `'full'` — 100%
- `'2/3'` — 66%
- `'1/2'` — 50%
- `'1/3'` — 33%

### RbacRulesEditor

```tsx
import { RbacRulesEditor } from '@shared/ui';

<RbacRulesEditor
  scope="user"
  permissions={{
    instance_permissions: { 'rag-search': 'allowed' },
    agent_permissions: { 'assistant': 'denied' },
  }}
  onChange={setPermissions}
  editable={true}
/>
```

## Feedback компоненты

### Toast

```tsx
import { useSuccessToast, useErrorToast } from '@shared/ui/Toast';

const showSuccess = useSuccessToast();
const showError = useErrorToast();

// Usage
showSuccess('Агент создан');
showError('Ошибка сохранения');
```

### Skeleton

```tsx
import { Skeleton } from '@shared/ui';

{isLoading ? (
  <Skeleton height={200} />
) : (
  <Content />
)}
```

### Spinner

```tsx
import { Spinner } from '@shared/ui';

<Spinner size="small" />
<Spinner size="medium" />
<Spinner size="large" />
```

## Icons

```tsx
import { Icon } from '@shared/ui';

<Icon name="edit" />
<Icon name="trash" />
<Icon name="plus" />
<Icon name="search" />
```

**Доступные иконки:** см. Lucide icons.

## Паттерны использования

### Форма создания/редактирования

```tsx
function AgentEditorPage() {
  const { id } = useParams();
  const isCreate = !id;
  
  const { data: agent, isLoading } = useQuery({
    queryKey: qk.agents.detail(id!),
    queryFn: () => agentsApi.get(id!),
    enabled: !isCreate,
  });
  
  const [formData, setFormData] = useState<AgentForm>({
    name: '',
    description: '',
  });
  
  useEffect(() => {
    if (agent) {
      setFormData({
        name: agent.name,
        description: agent.description,
      });
    }
  }, [agent]);
  
  if (!isCreate && isLoading) {
    return <Skeleton />;
  }
  
  return (
    <EntityPage
      mode={isCreate ? 'create' : 'edit'}
      title={isCreate ? 'Новый агент' : formData.name}
    >
      <ContentGrid>
        <ContentBlock title="Основное" width="2/3">
          <Input
            label="Название"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          />
        </ContentBlock>
      </ContentGrid>
    </EntityPage>
  );
}
```

### Таблица с действиями

```tsx
function AgentsPage() {
  const { data, isLoading } = useQuery({
    queryKey: qk.agents.list(),
    queryFn: agentsApi.list,
  });
  
  const columns = [
    { key: 'name', title: 'Название' },
    { key: 'status', title: 'Статус', render: (row) => (
      <Badge variant={row.is_active ? 'success' : 'default'}>
        {row.is_active ? 'Активен' : 'Неактивен'}
      </Badge>
    )},
    { key: 'actions', title: '', render: (row) => (
      <DropdownMenu
        trigger={<Button variant="ghost"><Icon name="more" /></Button>}
        items={[
          { label: 'Редактировать', onClick: () => navigate(`/admin/agents/${row.slug}`) },
          { label: 'Удалить', onClick: () => handleDelete(row.id), danger: true },
        ]}
      />
    )},
  ];
  
  return (
    <DataTable
      data={data || []}
      columns={columns}
      isLoading={isLoading}
    />
  );
}
```
