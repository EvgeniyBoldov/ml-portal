/**
 * Query key factory for TanStack Query
 * Centralized query keys prevent hardcoding and ensure consistency
 * 
 * Usage:
 * - useQuery({ queryKey: qk.collections.list() })
 * - queryClient.invalidateQueries({ queryKey: qk.collections.all() })
 */

export const qk = {
  sandbox: {
    sessions: {
      all: () => ['sandbox', 'sessions'] as const,
      list: (params?: { status?: string }) =>
        ['sandbox', 'sessions', 'list', params] as const,
      detail: (id: string) => ['sandbox', 'sessions', id] as const,
    },
    branches: {
      list: (sessionId: string) =>
        ['sandbox', 'branches', sessionId] as const,
    },
    branchOverrides: {
      list: (sessionId: string, branchId: string) =>
        ['sandbox', 'branch-overrides', sessionId, branchId] as const,
    },
    runs: {
      list: (sessionId: string, branchId?: string) =>
        ['sandbox', 'runs', sessionId, branchId ?? 'all'] as const,
      detail: (sessionId: string, runId: string) =>
        ['sandbox', 'runs', sessionId, runId] as const,
    },
    catalog: {
      detail: (sessionId: string) =>
        ['sandbox', 'catalog', sessionId] as const,
    },
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
      list: (params?: { page?: number; size?: number; type?: string; enabled_only?: boolean; status?: string; search?: string }) => ['admin', 'models', 'list', params] as const,
      detail: (id: string) => ['admin', 'models', id] as const,
      embeddingUsage: (id: string) => ['admin', 'models', id, 'embedding-usage'] as const,
    },
    orchestration: {
      all: () => ['admin', 'orchestration'] as const,
      settings: () => ['admin', 'orchestration', 'settings'] as const,
    },
    systemLlmRoles: {
      all: () => ['admin', 'system-llm-roles'] as const,
      active: (role: 'planner' | 'synthesizer' | 'fact_extractor' | 'summary_compactor') =>
        ['admin', 'system-llm-roles', 'active', role] as const,
    },
    audit: (params?: {
      page?: number;
      page_size?: number;
      user_id?: string;
      action?: string;
      status?: string;
      from_date?: string;
      to_date?: string;
    }) => ['admin', 'audit', params] as const,
  },
  agents: {
    all: () => ['agents'] as const,
    list: (params?: { q?: string }) => ['agents', 'list', params] as const,
    detail: (slug: string) => ['agents', 'detail', slug] as const,
    versions: (slug: string) => ['agents', 'versions', slug] as const,
    version: (slug: string, version: number) => ['agents', 'version', slug, version] as const,
  },
  discoveredTools: {
    all: () => ['discovered-tools'] as const,
    list: (params?: { source?: string; domain?: string; is_active?: boolean }) =>
      ['discovered-tools', 'list', params] as const,
    detail: (id: string) => ['discovered-tools', 'detail', id] as const,
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
    detail: (id: string) => ['tools', 'detail', id] as const,
  },
  toolInstances: {
    all: () => ['connectors'] as const,
    list: (params?: { is_active?: boolean; instance_kind?: string; connector_type?: string; connector_subtype?: string; placement?: string; limit?: number; skip?: number }) =>
      ['connectors', 'list', params] as const,
    detail: (id: string) => ['connectors', 'detail', id] as const,
  },
  credentials: {
    all: () => ['credentials'] as const,
    list: (params?: Record<string, unknown>) =>
      ['credentials', 'list', params] as const,
    detail: (id: string) => ['credentials', 'detail', id] as const,
  },
  agentRuns: {
    all: () => ['agent-runs'] as const,
    list: (params?: { page?: number; page_size?: number; agent_slug?: string; status?: string }) =>
      ['agent-runs', 'list', params] as const,
    detail: (id: string) => ['agent-runs', 'detail', id] as const,
    stats: (params?: { tenant_id?: string; from_date?: string; to_date?: string }) =>
      ['agent-runs', 'stats', params] as const,
  },
  rbac: {
    all: () => ['rbac'] as const,
    list: (params?: Record<string, unknown>) => ['rbac', 'list', params] as const,
    detail: (id: string) => ['rbac', 'detail', id] as const,
    enrichedRules: (params?: Record<string, unknown>) =>
      ['rbac', 'enriched-rules', params] as const,
  },
  platform: {
    all: () => ['platform'] as const,
    settings: () => ['platform', 'settings'] as const,
  },
  chats: {
    all: () => ['chats'] as const,
    list: (q?: string) => ['chats', 'list', q] as const,
    detail: (id: string) => ['chats', 'detail', id] as const,
    messages: (chatId: string) => ['chats', 'messages', chatId] as const,
  },
  plans: {
    all: () => ['plans'] as const,
    detail: (id: string) => ['plans', 'detail', id] as const,
    chatPlans: (chatId: string, status?: string) =>
      ['plans', 'chat', chatId, status ?? 'all'] as const,
    runPlans: (runId: string, status?: string) =>
      ['plans', 'run', runId, status ?? 'all'] as const,
  },
  collections: {
    all: () => ['collections'] as const,
    list: (params?: { tenant_id?: string; is_active?: boolean }) =>
      ['collections', 'list', params] as const,
    presets: () => ['collections', 'type-presets'] as const,
    detail: (slug: string) => ['collections', 'detail', slug] as const,
    versions: (id: string) => ['collections', 'versions', id] as const,
    version: (id: string, version: number) => ['collections', 'version', id, version] as const,
    data: (slug: string, params?: { limit?: number; offset?: number; search?: string; tenant_id?: string }) =>
      ['collections', 'data', slug, params] as const,
    documents: (id: string, params?: { page?: number; size?: number; status?: string }) =>
      ['collections', 'documents', id, params] as const,
  },
  auth: {
    me: () => ['auth', 'me'] as const,
  },
};
