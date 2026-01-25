# Frontend Architecture

Архитектура фронтенда ML Portal.

## Технологический стек

- **React 18** + **TypeScript** + **Vite**
- **React Router** — маршрутизация
- **TanStack Query v5** — серверное состояние
- **Zustand** — локальное UI состояние
- **CSS Modules** — стилизация
- **SSE (EventSource)** — real-time обновления

## Структура проекта

```
apps/web/src/
├── app/                    — Корневой уровень приложения
│   ├── providers/          — Провайдеры (Query, Auth, SSE, Toast)
│   ├── router/             — Конфигурация роутинга
│   ├── layouts/            — Layout компоненты
│   └── store/              — Zustand stores
├── domains/                — Domain-first структура
│   ├── auth/               — Аутентификация
│   ├── chat/               — Чат с агентами
│   ├── rag/                — RAG документы
│   ├── admin/              — Админка
│   │   ├── pages/          — Страницы админки
│   │   ├── components/     — Компоненты админки
│   │   └── layouts/        — Layout'ы админки
│   ├── profile/            — Профиль пользователя
│   └── collections/        — Коллекции
├── shared/                 — Переиспользуемые модули
│   ├── api/                — API клиенты и хуки
│   │   ├── client.ts       — HTTP клиент
│   │   ├── keys.ts         — Query key factory
│   │   ├── hooks/          — React Query хуки
│   │   ├── auth.ts         — Auth API
│   │   ├── agents.ts       — Agents API
│   │   ├── prompts.ts      — Prompts API
│   │   └── ...             — Другие API модули
│   ├── ui/                 — UI компоненты
│   │   ├── Button/
│   │   ├── Input/
│   │   ├── Modal/
│   │   ├── DataTable/      — Переиспользуемая таблица
│   │   └── ...
│   ├── lib/                — Утилиты
│   ├── hooks/              — Переиспользуемые хуки
│   ├── config/             — Конфигурация
│   └── types/              — Общие типы
└── main.tsx                — Точка входа
```

---

## Провайдеры

### AppProviders (`app/providers/AppProviders.tsx`)

```tsx
export function AppProviders({ children }: { children: React.ReactNode }) {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <SSEManagerProvider>
            <ToastProvider>
              <GlobalConfirmDialog />
              {children}
            </ToastProvider>
          </SSEManagerProvider>
        </AuthProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
```

### QueryClientProvider

```tsx
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,        // 30 секунд
      gcTime: 5 * 60_000,       // 5 минут
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
});
```

### AuthProvider

```tsx
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { hydrate, isHydrated } = useAuthStore();

  useEffect(() => {
    hydrate(); // Загружаем пользователя из refresh token
  }, [hydrate]);

  if (!isHydrated) {
    return <LoadingScreen />;
  }

  return <>{children}</>;
}
```

### SSEManagerProvider

Глобальный менеджер SSE подписок.

```tsx
export function SSEManagerProvider({ children }: { children: React.ReactNode }) {
  const sseClient = useMemo(() => new SSEClient(config.sseBaseUrl), []);
  const queryClient = useQueryClient();

  useEffect(() => {
    // Подписываемся на события
    sseClient.on('rag.updated', (event) => {
      applyRagEvents(queryClient, [event]);
    });

    sseClient.on('chat.delta', (event) => {
      applyChatEvents(queryClient, [event]);
    });

    // Подключаемся
    sseClient.connect();

    return () => {
      sseClient.disconnect();
    };
  }, [sseClient, queryClient]);

  return (
    <SSEContext.Provider value={sseClient}>
      {children}
    </SSEContext.Provider>
  );
}
```

---

## Роутинг

### AppRouter (`app/router/AppRouter.tsx`)

```tsx
export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<LoginPage />} />

        {/* Main app */}
        <Route element={<RequireAuth />}>
          <Route element={<MainLayout />}>
            <Route path="/gpt" element={<ChatPage />} />
            <Route path="/gpt/rag" element={<RagPage />} />
            <Route path="/profile" element={<ProfilePage />} />
          </Route>

          {/* Admin */}
          <Route element={<AdminGuard />}>
            <Route path="/admin" element={<AdminLayout />}>
              <Route index element={<DashboardPage />} />
              
              {/* Users */}
              <Route path="users" element={<UsersPage />} />
              <Route path="users/new" element={<CreateUserPage />} />
              <Route path="users/:id" element={<UserDetailPage />} />
              
              <Route path="tenants" element={<TenantsPage />} />
              <Route path="tenants/new" element={<CreateTenantPage />} />
              <Route path="tenants/:id" element={<TenantDetailPage />} />
              
              <Route path="defaults" element={<DefaultsPage />} />
              
              {/* AI */}
              <Route path="models" element={<ModelsPage />} />
              <Route path="prompts" element={<PromptRegistryPage />} />
              <Route path="prompts/:slug" element={<PromptDetailPage />} />
              <Route path="prompts/:slug/edit" element={<PromptEditorPage />} />
              
              <Route path="tools" element={<ToolsPage />} />
              
              <Route path="agents" element={<AgentRegistryPage />} />
              <Route path="agents/:slug" element={<AgentEditorPage />} />
              
              {/* Integrations */}
              <Route path="instances" element={<InstancesPage />} />
              <Route path="instances/:id" element={<InstanceViewPage />} />
              
              <Route path="collections" element={<CollectionsPage />} />
              <Route path="collections/:id" element={<ViewCollectionPage />} />
              
              {/* Logs */}
              <Route path="agent-runs" element={<AgentRunsPage />} />
              <Route path="agent-runs/:id" element={<AgentRunDetailPage />} />
              
              <Route path="audit" element={<AuditPage />} />
            </Route>
          </Route>
        </Route>

        {/* 404 */}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  );
}
```

### Guards

```tsx
function RequireAuth() {
  const { user } = useAuthStore();
  const location = useLocation();

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <Outlet />;
}

function AdminGuard() {
  const { user, hasRole } = useAuthStore();

  if (!hasRole('admin') && !hasRole('tenant_admin')) {
    return <Navigate to="/gpt" replace />;
  }

  return <Outlet />;
}
```

---

## API Layer

### HTTP Client (`shared/api/client.ts`)

```typescript
interface RequestOptions {
  timeout?: number;
  idempotent?: boolean;
  signal?: AbortSignal;
}

export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit & RequestOptions = {}
): Promise<T> {
  const { timeout = 30000, idempotent = false, signal, ...fetchOptions } = options;

  // Add Authorization header
  const accessToken = getAccessToken();
  const headers = new Headers(fetchOptions.headers);
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`);
  }

  // Add Idempotency-Key for POST/PUT
  if (idempotent && (fetchOptions.method === 'POST' || fetchOptions.method === 'PUT')) {
    headers.set('Idempotency-Key', generateIdempotencyKey());
  }

  // Timeout
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(`${config.apiBaseUrl}${endpoint}`, {
      ...fetchOptions,
      headers,
      signal: signal || controller.signal,
      credentials: 'include', // Для httpOnly cookies
    });

    clearTimeout(timeoutId);

    // Handle 401 - try refresh
    if (response.status === 401) {
      const refreshed = await refreshAccessToken();
      if (refreshed) {
        // Retry request with new token
        return apiRequest<T>(endpoint, options);
      }
      // Redirect to login
      window.location.href = '/login';
      throw new Error('Unauthorized');
    }

    if (!response.ok) {
      const error = await response.json();
      throw new ApiError(error.detail || 'Request failed', response.status);
    }

    return response.json();
  } catch (error) {
    clearTimeout(timeoutId);
    throw error;
  }
}
```

### Query Key Factory (`shared/api/keys.ts`)

```typescript
export const qk = {
  auth: {
    me: () => ['auth', 'me'] as const,
  },
  users: {
    all: () => ['users'] as const,
    list: (filters?: UserFilters) => ['users', 'list', filters] as const,
    detail: (id: string) => ['users', 'detail', id] as const,
  },
  tenants: {
    all: () => ['tenants'] as const,
    list: (filters?: TenantFilters) => ['tenants', 'list', filters] as const,
    detail: (id: string) => ['tenants', 'detail', id] as const,
  },
  prompts: {
    all: () => ['prompts'] as const,
    list: (filters?: PromptFilters) => ['prompts', 'list', filters] as const,
    detail: (slug: string) => ['prompts', 'detail', slug] as const,
    versions: (slug: string) => ['prompts', 'versions', slug] as const,
  },
  agents: {
    all: () => ['agents'] as const,
    list: (filters?: AgentFilters) => ['agents', 'list', filters] as const,
    detail: (slug: string) => ['agents', 'detail', slug] as const,
  },
  agentRuns: {
    all: () => ['agent-runs'] as const,
    list: (filters?: AgentRunFilters) => ['agent-runs', 'list', filters] as const,
    detail: (id: string) => ['agent-runs', 'detail', id] as const,
  },
  // ... другие ключи
};
```

### API Modules

**Пример: `shared/api/prompts.ts`**

```typescript
export interface Prompt {
  id: string;
  slug: string;
  name: string;
  description?: string;
  template: string;
  input_variables: string[];
  generation_config: Record<string, any>;
  version: number;
  status: 'draft' | 'active' | 'archived';
  type: 'prompt' | 'baseline';
  created_at: string;
  updated_at: string;
}

export async function listPrompts(filters?: {
  type?: 'prompt' | 'baseline';
  status?: 'draft' | 'active' | 'archived';
}): Promise<Prompt[]> {
  const params = new URLSearchParams();
  if (filters?.type) params.set('type', filters.type);
  if (filters?.status) params.set('status', filters.status);

  return apiRequest(`/api/v1/prompts?${params}`);
}

export async function getPromptVersions(slug: string): Promise<Prompt[]> {
  return apiRequest(`/api/v1/prompts/${slug}`);
}

export async function createPromptVersion(
  slug: string,
  data: {
    template: string;
    input_variables: string[];
    generation_config: Record<string, any>;
  }
): Promise<Prompt> {
  return apiRequest(`/api/v1/prompts/${slug}/versions`, {
    method: 'POST',
    body: JSON.stringify(data),
    headers: { 'Content-Type': 'application/json' },
  });
}

export async function activatePromptVersion(promptId: string): Promise<Prompt> {
  return apiRequest(`/api/v1/prompts/${promptId}/activate`, {
    method: 'POST',
  });
}
```

### React Query Hooks

**Пример: `shared/api/hooks/usePrompts.ts`**

```typescript
export function usePrompts(filters?: PromptFilters) {
  return useQuery({
    queryKey: qk.prompts.list(filters),
    queryFn: () => listPrompts(filters),
  });
}

export function usePromptVersions(slug: string) {
  return useQuery({
    queryKey: qk.prompts.versions(slug),
    queryFn: () => getPromptVersions(slug),
    enabled: !!slug,
  });
}

export function useCreatePromptVersion() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ slug, data }: { slug: string; data: any }) =>
      createPromptVersion(slug, data),
    onSuccess: (_, { slug }) => {
      // Invalidate versions list
      queryClient.invalidateQueries({ queryKey: qk.prompts.versions(slug) });
      queryClient.invalidateQueries({ queryKey: qk.prompts.list() });
    },
  });
}

export function useActivatePromptVersion() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (promptId: string) => activatePromptVersion(promptId),
    onSuccess: (prompt) => {
      // Invalidate versions list
      queryClient.invalidateQueries({ queryKey: qk.prompts.versions(prompt.slug) });
      queryClient.invalidateQueries({ queryKey: qk.prompts.list() });
    },
  });
}
```

---

## State Management

### Zustand Stores

**Auth Store (`app/store/auth.store.ts`):**

```typescript
interface AuthState {
  user: User | null;
  isHydrated: boolean;
  hydrate: () => Promise<void>;
  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => Promise<void>;
  hasRole: (role: string) => boolean;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  isHydrated: false,

  hydrate: async () => {
    try {
      const user = await getCurrentUser();
      set({ user, isHydrated: true });
    } catch {
      set({ user: null, isHydrated: true });
    }
  },

  login: async (credentials) => {
    const { access_token, user } = await loginUser(credentials);
    setAccessToken(access_token);
    set({ user });
  },

  logout: async () => {
    await logoutUser();
    clearAccessToken();
    set({ user: null });
  },

  hasRole: (role) => {
    const { user } = get();
    return user?.role === role || user?.role === 'admin';
  },
}));
```

**App Store (`app/store/app.store.ts`):**

```typescript
interface AppState {
  // Modals
  confirmDialog: {
    isOpen: boolean;
    title: string;
    message: string;
    onConfirm: () => void;
  } | null;
  openConfirmDialog: (config: ConfirmDialogConfig) => void;
  closeConfirmDialog: () => void;

  // Filters (для таблиц)
  filters: Record<string, any>;
  setFilter: (key: string, value: any) => void;
  clearFilters: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  confirmDialog: null,
  openConfirmDialog: (config) => set({ confirmDialog: { ...config, isOpen: true } }),
  closeConfirmDialog: () => set({ confirmDialog: null }),

  filters: {},
  setFilter: (key, value) =>
    set((state) => ({ filters: { ...state.filters, [key]: value } })),
  clearFilters: () => set({ filters: {} }),
}));
```

---

## UI Components

### DataTable (`shared/ui/DataTable/`)

Переиспользуемый компонент таблицы на базе TanStack Table v8.

```tsx
interface DataTableProps<T> {
  data: T[];
  columns: ColumnDef<T>[];
  filters?: FilterConfig[];
  searchPlaceholder?: string;
  onRowClick?: (row: T) => void;
  actions?: ActionConfig[];
  isLoading?: boolean;
}

export function DataTable<T>({
  data,
  columns,
  filters,
  searchPlaceholder,
  onRowClick,
  actions,
  isLoading,
}: DataTableProps<T>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [globalFilter, setGlobalFilter] = useState('');

  const table = useReactTable({
    data,
    columns,
    state: {
      sorting,
      columnFilters,
      globalFilter,
    },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  return (
    <div className={s.wrap}>
      {/* Toolbar */}
      <div className={s.toolbar}>
        {/* Search */}
        <Input
          placeholder={searchPlaceholder}
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
          className={s.search}
        />

        {/* Filters */}
        {filters?.map((filter) => (
          <FilterDropdown
            key={filter.id}
            filter={filter}
            value={columnFilters.find((f) => f.id === filter.id)?.value}
            onChange={(value) => {
              setColumnFilters((prev) =>
                value
                  ? [...prev.filter((f) => f.id !== filter.id), { id: filter.id, value }]
                  : prev.filter((f) => f.id !== filter.id)
              );
            }}
          />
        ))}

        {/* Actions */}
        {actions?.map((action) => (
          <Button key={action.label} onClick={action.onClick} variant={action.variant}>
            {action.label}
          </Button>
        ))}
      </div>

      {/* Table */}
      {isLoading ? (
        <TableSkeleton />
      ) : (
        <table className={s.table}>
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th key={header.id} onClick={header.column.getToggleSortingHandler()}>
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    {header.column.getIsSorted() && (
                      <span>{header.column.getIsSorted() === 'asc' ? ' ↑' : ' ↓'}</span>
                    )}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                onClick={() => onRowClick?.(row.original)}
                className={onRowClick ? s.clickable : undefined}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Pagination */}
      <div className={s.pagination}>
        <Button
          onClick={() => table.previousPage()}
          disabled={!table.getCanPreviousPage()}
          variant="ghost"
        >
          Previous
        </Button>
        <span>
          Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount()}
        </span>
        <Button
          onClick={() => table.nextPage()}
          disabled={!table.getCanNextPage()}
          variant="ghost"
        >
          Next
        </Button>
      </div>
    </div>
  );
}
```

### Другие UI компоненты

- **Button** — кнопки с вариантами (primary, secondary, ghost, danger)
- **Input** — текстовые поля
- **Textarea** — многострочные поля
- **Select** — выпадающие списки
- **Checkbox** — чекбоксы
- **Modal** — модальные окна
- **Drawer** — боковые панели
- **Popover** — всплывающие меню
- **DropdownMenu** — выпадающие меню действий
- **Badge** — бейджи статусов
- **Skeleton** — скелетоны загрузки
- **Toast** — уведомления

---

## SSE Integration

### SSE Client (`shared/lib/sse.ts`)

```typescript
export class SSEClient {
  private eventSource: EventSource | null = null;
  private listeners: Map<string, Set<(event: any) => void>> = new Map();

  constructor(private baseUrl: string) {}

  connect() {
    if (this.eventSource) return;

    const token = getAccessToken();
    const url = `${this.baseUrl}/stream?token=${token}`;

    this.eventSource = new EventSource(url, { withCredentials: true });

    this.eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.emit(data.type, data);
    };

    this.eventSource.onerror = () => {
      console.error('SSE connection error');
      this.reconnect();
    };
  }

  disconnect() {
    this.eventSource?.close();
    this.eventSource = null;
  }

  on(eventType: string, callback: (event: any) => void) {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, new Set());
    }
    this.listeners.get(eventType)!.add(callback);
  }

  off(eventType: string, callback: (event: any) => void) {
    this.listeners.get(eventType)?.delete(callback);
  }

  private emit(eventType: string, event: any) {
    this.listeners.get(eventType)?.forEach((callback) => callback(event));
  }

  private reconnect() {
    setTimeout(() => {
      this.disconnect();
      this.connect();
    }, 5000);
  }
}
```

### Event Handlers

**RAG Events (`app/providers/applyRagEvents.ts`):**

```typescript
export function applyRagEvents(queryClient: QueryClient, events: RagEvent[]) {
  events.forEach((event) => {
    switch (event.type) {
      case 'rag.created':
        // Invalidate list
        queryClient.invalidateQueries({ queryKey: qk.rag.list() });
        break;

      case 'rag.updated':
        // Update detail cache
        queryClient.setQueryData(
          qk.rag.detail(event.data.tenant_id, event.data.doc_id),
          (old: any) => ({
            ...old,
            ...event.data,
          })
        );
        // Update list cache
        queryClient.setQueryData(qk.rag.list(), (old: any) =>
          old?.map((doc: any) =>
            doc.id === event.data.doc_id ? { ...doc, ...event.data } : doc
          )
        );
        break;

      case 'rag.deleted':
        // Remove from cache
        queryClient.removeQueries({
          queryKey: qk.rag.detail(event.data.tenant_id, event.data.doc_id),
        });
        queryClient.invalidateQueries({ queryKey: qk.rag.list() });
        break;
    }
  });
}
```

---

## Styling

### CSS Modules

Все стили в `.module.css` файлах.

**Naming convention:**
- Классы в `dash-case`: `.my-component`, `.button-primary`
- Файлы в `PascalCase.module.css`: `Button.module.css`

**Пример:**

```css
/* Button.module.css */
.button {
  padding: 0.5rem 1rem;
  border-radius: 0.375rem;
  font-weight: 500;
  transition: all 0.2s;
}

.button-primary {
  background: var(--color-primary);
  color: white;
}

.button-primary:hover {
  background: var(--color-primary-dark);
}

.button-secondary {
  background: var(--color-secondary);
  color: var(--color-text);
}
```

```tsx
import s from './Button.module.css';

export function Button({ variant = 'primary', children, ...props }) {
  return (
    <button className={`${s.button} ${s[`button-${variant}`]}`} {...props}>
      {children}
    </button>
  );
}
```

### Theme Variables

```css
:root {
  /* Colors */
  --color-primary: #3b82f6;
  --color-primary-dark: #2563eb;
  --color-secondary: #64748b;
  --color-success: #10b981;
  --color-warning: #f59e0b;
  --color-danger: #ef4444;
  
  /* Text */
  --color-text: #1e293b;
  --color-text-muted: #64748b;
  
  /* Background */
  --color-bg: #ffffff;
  --color-bg-secondary: #f8fafc;
  --color-bg-tertiary: #f1f5f9;
  
  /* Border */
  --color-border: #e2e8f0;
  
  /* Spacing */
  --spacing-xs: 0.25rem;
  --spacing-sm: 0.5rem;
  --spacing-md: 1rem;
  --spacing-lg: 1.5rem;
  --spacing-xl: 2rem;
  
  /* Border radius */
  --radius-sm: 0.25rem;
  --radius-md: 0.375rem;
  --radius-lg: 0.5rem;
  
  /* Shadows */
  --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
  --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1);
  --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1);
}
```

---

## Performance

### Code Splitting

```tsx
// Lazy load admin routes
const AdminLayout = lazy(() => import('./domains/admin/layouts/AdminLayout'));
const DashboardPage = lazy(() => import('./domains/admin/pages/DashboardPage'));
// ... другие страницы

// Wrap in Suspense
<Suspense fallback={<LoadingScreen />}>
  <AdminLayout />
</Suspense>
```

### Memoization

```tsx
// Memo для тяжелых компонентов
export const DataTable = memo(DataTableComponent);

// useMemo для вычислений
const filteredData = useMemo(
  () => data.filter((item) => item.status === filter),
  [data, filter]
);

// useCallback для функций
const handleClick = useCallback(() => {
  // ...
}, [deps]);
```

### Virtual Scrolling

Для больших списков используем `@tanstack/react-virtual`.

---

## Testing

### Unit Tests (Vitest + RTL)

```tsx
import { render, screen } from '@testing-library/react';
import { Button } from './Button';

describe('Button', () => {
  it('renders with text', () => {
    render(<Button>Click me</Button>);
    expect(screen.getByText('Click me')).toBeInTheDocument();
  });

  it('calls onClick handler', async () => {
    const handleClick = vi.fn();
    render(<Button onClick={handleClick}>Click me</Button>);
    
    await userEvent.click(screen.getByText('Click me'));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });
});
```

### E2E Tests (Playwright)

```typescript
test('admin can create prompt', async ({ page }) => {
  // Login
  await page.goto('/login');
  await page.fill('[name="login"]', 'admin');
  await page.fill('[name="password"]', 'password');
  await page.click('button[type="submit"]');

  // Navigate to prompts
  await page.goto('/admin/prompts');
  await page.click('text=Create Prompt');

  // Fill form
  await page.fill('[name="slug"]', 'test-prompt');
  await page.fill('[name="name"]', 'Test Prompt');
  await page.fill('[name="template"]', 'You are a helpful assistant.');
  await page.click('button:has-text("Create")');

  // Verify
  await expect(page.locator('text=Test Prompt')).toBeVisible();
});
```

---

## Best Practices

### 1. Component Structure
- Один компонент на файл
- Максимум 250 строк
- Выносить сложную логику в хуки

### 2. State Management
- Серверное состояние → React Query
- Локальное UI состояние → Zustand
- Форма → React Hook Form

### 3. API Calls
- Всегда через query keys factory
- Не дублировать запросы
- Использовать optimistic updates осторожно

### 4. Styling
- Только CSS Modules
- Переиспользовать UI компоненты из `shared/ui`
- Не использовать inline styles

### 5. Accessibility
- Все интерактивные элементы доступны с клавиатуры
- Используем `aria-*` атрибуты
- Модалки с focus trap и Esc для закрытия

### 6. Performance
- Lazy load страниц
- Memo для тяжелых компонентов
- Virtual scrolling для больших списков
- Debounce для поиска
