/**
 * Query key factory for TanStack Query
 * Centralized query keys prevent hardcoding and ensure consistency
 * 
 * Usage:
 * - useQuery({ queryKey: qk.rag.list({ page: 1 }) })
 * - queryClient.invalidateQueries({ queryKey: qk.rag.list() })
 */

export const qk = {
  rag: {
    all: () => ['rag'] as const,
    list: (params?: { page?: number; size?: number; status?: string; q?: string }) =>
      ['rag', 'list', params] as const,
    detail: (id: string) => ['rag', 'detail', id] as const,
    statusGraph: (id: string) => ['rag', 'status-graph', id] as const,
  },
  admin: {
    all: () => ['admin'] as const,
    users: (params?: { page?: number; q?: string }) =>
      ['admin', 'users', params] as const,
    user: (id: string) => ['admin', 'user', id] as const,
    tenants: (params?: { page?: number }) => ['admin', 'tenants', params] as const,
    tenant: (id: string) => ['admin', 'tenant', id] as const,
    models: () => ['admin', 'models'] as const,
    model: (id: string) => ['admin', 'model', id] as const,
    audit: (params?: { page?: number }) => ['admin', 'audit', params] as const,
  },
  agents: {
    all: () => ['agents'] as const,
    list: (params?: { q?: string }) => ['agents', 'list', params] as const,
    detail: (slug: string) => ['agents', 'detail', slug] as const,
  },
  prompts: {
    all: () => ['prompts'] as const,
    list: (params?: { type?: string; q?: string }) => ['prompts', 'list', params] as const,
    detail: (slug: string) => ['prompts', 'detail', slug] as const,
  },
  tools: {
    all: () => ['tools'] as const,
    list: (params?: { q?: string }) => ['tools', 'list', params] as const,
    detail: (slug: string) => ['tools', 'detail', slug] as const,
  },
  chats: {
    all: () => ['chats'] as const,
    list: (q?: string) => ['chats', 'list', q] as const,
    detail: (id: string) => ['chats', 'detail', id] as const,
    messages: (chatId: string) => ['chats', 'messages', chatId] as const,
  },
  auth: {
    me: () => ['auth', 'me'] as const,
  },
};
