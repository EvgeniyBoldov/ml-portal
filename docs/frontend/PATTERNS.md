# Frontend Patterns

Практические шаблоны реализации.  
RULES.md отвечает на вопрос «что обязательно», этот файл — «как именно делаем».

## 1) Архитектурный скелет

### App composition

```tsx
<ErrorBoundary>
  <ThemeProvider>
    <QueryClientProvider>
      <AuthProvider>
        <SSEProvider>
          <ToastProvider>{children}</ToastProvider>
        </SSEProvider>
      </AuthProvider>
    </QueryClientProvider>
  </ThemeProvider>
</ErrorBoundary>
```

### Routing

- `'/gpt/*'` — user app
- `'/admin/*'` — admin app
- Admin защищен через `AdminGuard`
- Страницы грузим lazy + `Suspense`

## 2) API pattern

### Один HTTP client

Используем только `shared/api/http.ts`:

- access token в памяти
- refresh через httpOnly cookie
- единый timeout/error/idempotency flow

### Query keys

Только через `qk`:

```tsx
const detail = useQuery({
  queryKey: qk.policies.detail(slug),
  queryFn: () => policiesApi.get(slug),
});
```

## 3) Admin page pattern (целевой)

Используем `EntityPageV2` + `Tab` и собираем страницу из готовых блоков.

```tsx
export function PolicyPage() {
  return (
    <EntityPageV2
      title={policy.name}
      mode={mode}
      onEdit={handleEdit}
      onSave={handleSave}
      onCancel={handleCancel}
      breadcrumbs={breadcrumbs}
    >
      <Tab title="Обзор" layout="grid">
        <EntityInfoBlock entity={policy} fields={fields} />
        <ShortEntityBlock entity={policy} />
      </Tab>

      <Tab title="Версии" layout="full" badge={versions.length}>
        <VersionsBlock versions={versions} onSelect={handleSelectVersion} />
      </Tab>
    </EntityPageV2>
  );
}
```

### Layout choice

- `grid` — overview
- `full` — data tables
- `single` — create/edit forms
- `custom` — сложные исключения

## 4) List page pattern

```tsx
export function PoliciesListPage() {
  const { data, isLoading } = useQuery({
    queryKey: qk.policies.list(filters),
    queryFn: () => policiesApi.list(filters),
  });

  if (isLoading) return <Skeleton />;

  return (
    <DataTable
      data={data?.items ?? []}
      columns={columns}
      onRowClick={(row) => navigate(`/admin/policies/${row.slug}`)}
    />
  );
}
```

## 5) Form pattern

```tsx
const [form, setForm] = useState(initialForm);

const handleChange = (field: keyof FormState, value: string) => {
  setForm((prev) => ({ ...prev, [field]: value }));
};

<Input value={form.name} onChange={(e) => handleChange('name', e.target.value)} />
<Textarea value={form.description} onChange={(e) => handleChange('description', e.target.value)} />
```

Правило: большие формы — page-level, не modal-first.

## 6) Styling pattern

### Variables

Используем:

- `--bg-primary`
- `--text-primary`
- `--border-color`
- токены `--sp-*`, `--radius-*`, `--font-size-*`

### CSS module skeleton

```css
.container {}
.header {}
.content {}

.button--primary {}

@media (max-width: 768px) {}
```

## 7) State boundary pattern

### React Query

- server data: query/mutation/invalidation

### Zustand

- UI state only (sidebar, toggles, local selections)

## 8) Legacy migration pattern

Если страница на legacy layout:

1. Не переписывать всё сразу.
2. Сначала вынести повторяемые блоки в `shared/ui`.
3. Затем перевести страницу на `EntityPageV2`.
4. После миграции удалить legacy-specific стили/разметку.

## 9) Anti-patterns

- новый кастомный UI при наличии блока в `shared/ui`
- server entities в Zustand
- hardcoded query keys
- shared CSS между admin pages
- бесконечные «временные» EditorPage без плана миграции
