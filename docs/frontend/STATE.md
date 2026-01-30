# State Management

## Обзор

Разделение состояния на серверное (React Query) и UI (Zustand).

```
┌─────────────────────────────────────────────────────────────┐
│                     State Management                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Server State (React Query)     UI State (Zustand)          │
│  ─────────────────────────     ────────────────────          │
│  • Agents                       • Sidebar open/closed       │
│  • Prompts                      • Selected items            │
│  • Documents                    • Modal visibility          │
│  • Users                        • Filters                   │
│  • Permissions                  • Search query              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## React Query

### Query Client

```tsx
// app/providers/QueryProvider.tsx
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,        // 30 seconds
      gcTime: 5 * 60_000,       // 5 minutes  
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
});
```

### Query Key Factory

```tsx
// shared/api/keys.ts
export const qk = {
  agents: {
    all: ['agents'] as const,
    list: (params?: AgentListParams) => ['agents', 'list', params] as const,
    detail: (slug: string) => ['agents', 'detail', slug] as const,
  },
  prompts: {
    all: ['prompts'] as const,
    list: (params?: PromptListParams) => ['prompts', 'list', params] as const,
    detail: (slug: string) => ['prompts', 'detail', slug] as const,
    versions: (slug: string) => ['prompts', 'versions', slug] as const,
  },
  rag: {
    all: ['rag'] as const,
    list: (params?: RagListParams) => ['rag', 'list', params] as const,
    detail: (id: string) => ['rag', 'detail', id] as const,
  },
  permissions: {
    all: ['permissions'] as const,
    list: (params?: PermissionListParams) => ['permissions', 'list', params] as const,
    effective: (params?: EffectiveParams) => ['permissions', 'effective', params] as const,
  },
  // ...
};
```

### Использование

```tsx
// Fetch list
const { data: agents, isLoading } = useQuery({
  queryKey: qk.agents.list({ status: 'active' }),
  queryFn: () => agentsApi.list({ status: 'active' }),
});

// Fetch detail
const { data: agent } = useQuery({
  queryKey: qk.agents.detail(slug),
  queryFn: () => agentsApi.get(slug),
  enabled: !!slug,
});

// Mutation with invalidation
const createMutation = useMutation({
  mutationFn: agentsApi.create,
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: qk.agents.all });
  },
});
```

### Optimistic Updates

```tsx
const updateMutation = useMutation({
  mutationFn: agentsApi.update,
  onMutate: async (newAgent) => {
    // Cancel outgoing refetches
    await queryClient.cancelQueries({ queryKey: qk.agents.detail(newAgent.slug) });
    
    // Snapshot previous value
    const previous = queryClient.getQueryData(qk.agents.detail(newAgent.slug));
    
    // Optimistically update
    queryClient.setQueryData(qk.agents.detail(newAgent.slug), newAgent);
    
    return { previous };
  },
  onError: (err, newAgent, context) => {
    // Rollback on error
    queryClient.setQueryData(qk.agents.detail(newAgent.slug), context?.previous);
  },
  onSettled: () => {
    queryClient.invalidateQueries({ queryKey: qk.agents.all });
  },
});
```

## Zustand

### App Store

```tsx
// app/store/app.store.ts
interface AppState {
  // Sidebar
  sidebarOpen: boolean;
  toggleSidebar: () => void;
  
  // Selection
  selectedItems: string[];
  selectItem: (id: string) => void;
  deselectItem: (id: string) => void;
  clearSelection: () => void;
  
  // Filters
  filters: Record<string, unknown>;
  setFilter: (key: string, value: unknown) => void;
  clearFilters: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  // Sidebar
  sidebarOpen: true,
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  
  // Selection
  selectedItems: [],
  selectItem: (id) => set((s) => ({ 
    selectedItems: [...s.selectedItems, id] 
  })),
  deselectItem: (id) => set((s) => ({ 
    selectedItems: s.selectedItems.filter((i) => i !== id) 
  })),
  clearSelection: () => set({ selectedItems: [] }),
  
  // Filters
  filters: {},
  setFilter: (key, value) => set((s) => ({ 
    filters: { ...s.filters, [key]: value } 
  })),
  clearFilters: () => set({ filters: {} }),
}));
```

### Chat Store

```tsx
// app/store/useChatStore.ts
interface ChatState {
  // UI state only!
  activeChatId: string | null;
  searchQuery: string;
  isComposing: boolean;
  
  setActiveChat: (id: string | null) => void;
  setSearchQuery: (query: string) => void;
  setComposing: (value: boolean) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  activeChatId: null,
  searchQuery: '',
  isComposing: false,
  
  setActiveChat: (id) => set({ activeChatId: id }),
  setSearchQuery: (query) => set({ searchQuery: query }),
  setComposing: (value) => set({ isComposing: value }),
}));
```

### Auth Store

```tsx
// entities/auth/model/auth.store.ts
interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  
  setUser: (user: User | null) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  
  setUser: (user) => set({ 
    user, 
    isAuthenticated: !!user,
    isLoading: false,
  }),
  logout: () => set({ 
    user: null, 
    isAuthenticated: false,
  }),
}));
```

## SSE и Cache Updates

### applyRagEvents

```tsx
// app/providers/applyRagEvents.ts
export function applyRagEvents(
  queryClient: QueryClient,
  event: RagEvent
) {
  switch (event.type) {
    case 'document.status_changed':
      // Update detail cache
      queryClient.setQueryData(
        qk.rag.detail(event.document_id),
        (old: RagDocument | undefined) => 
          old ? { ...old, status: event.status } : old
      );
      
      // Invalidate list
      queryClient.invalidateQueries({ queryKey: qk.rag.list() });
      break;
      
    case 'document.deleted':
      // Remove from cache
      queryClient.removeQueries({ queryKey: qk.rag.detail(event.document_id) });
      queryClient.invalidateQueries({ queryKey: qk.rag.list() });
      break;
  }
}
```

### SSE Provider Integration

```tsx
// app/providers/SSEProvider.tsx
export function SSEProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  
  useEffect(() => {
    const sse = new SSEClient(config.sseUrl, {
      getAccessToken: () => getAccessToken(),
    });
    
    sse.on('message', (event) => {
      applyRagEvents(queryClient, event);
    });
    
    sse.connect();
    
    return () => sse.disconnect();
  }, [queryClient]);
  
  return <>{children}</>;
}
```

## Правила

### DO

- ✅ Серверные данные в React Query
- ✅ UI состояние в Zustand
- ✅ Query keys через фабрику `qk`
- ✅ Invalidate после mutations
- ✅ SSE обновляет кэш через `setQueryData`

### DON'T

- ❌ Серверные данные в Zustand
- ❌ Hardcoded query keys
- ❌ Прямое изменение кэша без invalidation
- ❌ Дублирование данных между stores
