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
    users: {
      all: () => ['admin', 'users'] as const,
      list: (params?: { page?: number; q?: string; limit?: number }) =>
        ['admin', 'users', 'list', params] as const,
      detail: (id: string) => ['admin', 'users', id] as const,
    },
    tenants: {
      all: () => ['admin', 'tenants'] as const,
      list: (params?: { page?: number }) => ['admin', 'tenants', 'list', params] as const,
      detail: (id: string) => ['admin', 'tenants', id] as const,
    },
    models: {
      all: () => ['admin', 'models'] as const,
      list: (params?: { page?: number; size?: number }) => ['admin', 'models', 'list', params] as const,
      detail: (id: string) => ['admin', 'models', id] as const,
    },
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
    versions: (slug: string) => ['prompts', 'versions', slug] as const,
    version: (slug: string, version: number) => ['prompts', 'version', slug, version] as const,
    agents: (slug: string) => ['prompts', 'agents', slug] as const,
  },
  tools: {
    all: () => ['tools'] as const,
    list: (params?: { q?: string }) => ['tools', 'list', params] as const,
    detail: (slug: string) => ['tools', 'detail', slug] as const,
  },
  toolInstances: {
    all: () => ['tool-instances'] as const,
    list: (params?: { tool_group_id?: string; is_active?: boolean }) =>
      ['tool-instances', 'list', params] as const,
    detail: (id: string) => ['tool-instances', 'detail', id] as const,
  },
  toolGroups: {
    all: () => ['tool-groups'] as const,
    list: (params?: { skip?: number; limit?: number }) =>
      ['tool-groups', 'list', params] as const,
    detail: (id: string) => ['tool-groups', 'detail', id] as const,
  },
  credentials: {
    all: () => ['credentials'] as const,
    list: (params?: { toolInstanceId?: string; scope?: string; tenantId?: string }) =>
      ['credentials', 'list', params] as const,
    detail: (id: string) => ['credentials', 'detail', id] as const,
  },
  permissions: {
    all: () => ['permissions'] as const,
    list: (params?: { scope?: string; tenant_id?: string; user_id?: string }) =>
      ['permissions', 'list', params] as const,
    detail: (id: string) => ['permissions', 'detail', id] as const,
    effective: (params?: { user_id?: string; tenant_id?: string }) =>
      ['permissions', 'effective', params] as const,
  },
  policies: {
    all: () => ['policies'] as const,
    list: (params?: { is_active?: boolean }) => ['policies', 'list', params] as const,
    detail: (slug: string) => ['policies', 'detail', slug] as const,
    versions: (slug: string, params?: { status?: string }) => ['policies', 'versions', slug, params] as const,
    version: (slug: string, version: number) => ['policies', 'version', slug, version] as const,
    recommended: (slug: string) => ['policies', 'recommended', slug] as const,
  },
  baselines: {
    all: () => ['baselines'] as const,
    list: (params?: { scope?: string; tenant_id?: string; user_id?: string; is_active?: boolean }) =>
      ['baselines', 'list', params] as const,
    detail: (slug: string) => ['baselines', 'detail', slug] as const,
    versions: (slug: string) => ['baselines', 'versions', slug] as const,
    effective: (params?: { tenant_id?: string; user_id?: string }) =>
      ['baselines', 'effective', params] as const,
  },
  routingLogs: {
    all: () => ['routing-logs'] as const,
    list: (params?: { agentSlug?: string; status?: string; tenantId?: string }) =>
      ['routing-logs', 'list', params] as const,
    detail: (id: string) => ['routing-logs', 'detail', id] as const,
    stats: (params?: { tenantId?: string }) => ['routing-logs', 'stats', params] as const,
  },
  chats: {
    all: () => ['chats'] as const,
    list: (q?: string) => ['chats', 'list', q] as const,
    detail: (id: string) => ['chats', 'detail', id] as const,
    messages: (chatId: string) => ['chats', 'messages', chatId] as const,
  },
  collections: {
    all: () => ['collections'] as const,
    list: (params?: { tenant_id?: string; is_active?: boolean }) =>
      ['collections', 'list', params] as const,
    detail: (slug: string) => ['collections', 'detail', slug] as const,
    data: (slug: string, params?: { limit?: number; offset?: number }) =>
      ['collections', 'data', slug, params] as const,
  },
  auth: {
    me: () => ['auth', 'me'] as const,
  },
};
