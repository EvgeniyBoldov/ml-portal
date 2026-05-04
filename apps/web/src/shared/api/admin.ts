/**
 * Admin API client
 */
import { apiRequest } from './http';
// import type { ApiResponse, PaginatedResponse } from './types';

// Types
export interface User {
  id: string;
  login: string;
  role: 'admin' | 'editor' | 'reader';
  email?: string;
  is_active: boolean;
  tenant_id: string;
  created_at: string;
  updated_at: string;
}

export interface OrchestrationSettings {
  id: string;
  executor_model?: string | null;
  executor_temperature?: number | null;
  executor_timeout_s?: number | null;
  executor_max_steps?: number | null;
  created_at: string;
  updated_at: string;
}

export type ExecutorSettingsUpdate = Partial<Pick<
  OrchestrationSettings,
  | 'executor_model'
  | 'executor_temperature'
  | 'executor_timeout_s'
  | 'executor_max_steps'
>>;

// === SystemLLMRole Types ===

export type SystemLLMRoleType =
  | 'planner'
  | 'synthesizer'
  | 'fact_extractor'
  | 'summary_compactor';
export type RetryBackoffType = 'none' | 'linear' | 'exp';

export interface SystemLLMRole {
  id: string;
  role_type: SystemLLMRoleType;
  identity?: string | null;
  mission?: string | null;
  rules?: string | null;
  safety?: string | null;
  output_requirements?: string | null;
  model?: string | null;
  temperature?: number | null;
  max_tokens?: number | null;
  timeout_s?: number | null;
  max_retries?: number | null;
  retry_backoff?: RetryBackoffType | null;
  is_active?: boolean | null;
  created_at: string;
  updated_at: string;
}

export interface SystemLLMRoleCreate {
  role_type: SystemLLMRoleType;
  identity?: string | null;
  mission?: string | null;
  rules?: string | null;
  safety?: string | null;
  output_requirements?: string | null;
  model?: string | null;
  temperature?: number | null;
  max_tokens?: number | null;
  timeout_s?: number | null;
  max_retries?: number | null;
  retry_backoff?: RetryBackoffType | null;
  is_active?: boolean | null;
}

export interface SystemLLMRoleUpdate {
  identity?: string | null;
  mission?: string | null;
  rules?: string | null;
  safety?: string | null;
  output_requirements?: string | null;
  model?: string | null;
  temperature?: number | null;
  max_tokens?: number | null;
  timeout_s?: number | null;
  max_retries?: number | null;
  retry_backoff?: RetryBackoffType | null;
  is_active?: boolean | null;
}

// Role-specific update types — all use same schema as SystemLLMRoleUpdate
// Fields: identity, mission, rules, safety, output_requirements, model, temperature, etc.
export type PlannerRoleUpdate = SystemLLMRoleUpdate;
export type SynthesizerRoleUpdate = SystemLLMRoleUpdate;
export type FactExtractorRoleUpdate = SystemLLMRoleUpdate;
export type SummaryCompactorRoleUpdate = SystemLLMRoleUpdate;

export interface UserCreate {
  login: string;
  email?: string;
  role: 'admin' | 'editor' | 'reader';
  is_active?: boolean;
  password?: string;
  send_email?: boolean;
  tenant_ids?: string[];
}

export interface UserUpdate {
  role?: 'admin' | 'editor' | 'reader';
  email?: string;
  is_active?: boolean;
  require_password_change?: boolean;
  tenant_ids?: string[];
}

export interface UserListResponse {
  users: User[];
  has_more: boolean;
  next_cursor?: string;
  total?: number;
}

export interface PasswordChange {
  new_password?: string;
  require_change?: boolean;
}

export interface TokenScope {
  scope: string;
  description: string;
}

export interface UserToken {
  id: string;
  name: string;
  scopes: TokenScope[];
  expires_at?: string;
  created_at: string;
  last_used_at?: string;
  revoked_at?: string;
}

export interface TokenCreate {
  name: string;
  scopes: string[];
  expires_at?: string;
}

export interface TokenResponse extends UserToken {
  token_plain_once?: string; // Only returned on creation
}

export interface TokenListResponse {
  tokens: UserToken[];
  total: number;
}

export interface AuditLog {
  id: string;
  user_id?: string | null;
  tenant_id?: string | null;
  action: string;
  resource?: string | null;
  request_data?: Record<string, any> | null;
  response_status: string;
  response_data?: Record<string, any> | null;
  error_message?: string | null;
  duration_ms?: number | null;
  tokens_in?: number | null;
  tokens_out?: number | null;
  ip_address?: string | null;
  user_agent?: string;
  request_id?: string;
  created_at: string;
  ts?: string;
  actor_user_id?: string | null;
  actor_login?: string | null;
  object_type?: string | null;
  object_id?: string | null;
  meta?: Record<string, any> | null;
  ip?: string | null;
}

export interface AuditLogListResponse {
  items: AuditLog[];
  total: number;
  page: number;
  page_size: number;
}

export interface AuditFilters {
  user_id?: string;
  action?: string;
  status?: string;
  from_date?: string;
  to_date?: string;
}

export interface Tenant {
  id: string;
  name: string;
  description?: string;
  is_active: boolean;
  extra_embed_model?: string | null;
  embed_models?: string[];
  rerank_model?: string | null;
  ocr?: boolean;
  layout?: boolean;
  default_agent_slug?: string;
  created_at: string;
  updated_at: string;
}

export type TenantCreate = {
  name: string;
  description?: string;
  is_active?: boolean;
  extra_embed_model?: string | null;
  ocr?: boolean;
  layout?: boolean;
  default_agent_slug?: string;
};

export type TenantUpdate = Partial<TenantCreate>;

// New Model architecture
export type ModelType = 'llm_chat' | 'embedding' | 'reranker';
export type ModelConnector = 'openai_http' | 'azure_openai_http' | 'local_emb_http' | 'local_rerank_http' | 'local_llm_http' | 'grpc';
export type ModelStatus = 'available' | 'unavailable' | 'deprecated' | 'maintenance';
export type HealthStatus = 'healthy' | 'degraded' | 'unavailable';

export interface Model {
  id: string;
  alias: string;
  name: string;
  type: ModelType;
  provider: string;                   // deprecated, use connector
  connector: ModelConnector;
  provider_model_name: string;
  base_url?: string | null;
  instance_id?: string | null;
  instance_name?: string | null;
  extra_config?: Record<string, any> | null;
  status: ModelStatus;
  enabled: boolean;
  is_system: boolean;
  default_for_type: boolean;
  model_version?: string | null;
  description?: string | null;
  last_health_check_at?: string | null;
  health_status?: HealthStatus | null;
  health_error?: string | null;
  health_latency_ms?: number | null;
  created_at: string;
  updated_at: string;
  deleted_at?: string | null;
}

export interface ModelCreate {
  alias: string;
  name: string;
  type: ModelType;
  connector: ModelConnector;
  provider?: string;
  provider_model_name: string;
  base_url?: string;
  instance_id?: string;
  extra_config?: Record<string, any>;
  status?: ModelStatus;
  enabled?: boolean;
  default_for_type?: boolean;
  model_version?: string;
  description?: string;
}

export interface ModelUpdate {
  name?: string;
  connector?: ModelConnector;
  provider?: string;
  provider_model_name?: string;
  base_url?: string;
  instance_id?: string;
  extra_config?: Record<string, any>;
  status?: ModelStatus;
  enabled?: boolean;
  default_for_type?: boolean;
  model_version?: string;
  description?: string;
}

export interface ModelListResponse {
  items: Model[];
  total: number;
  page: number;
  size: number;
  has_more: boolean;
}

export interface HealthCheckRequest {
  force?: boolean;
}

export interface HealthCheckResponse {
  model_id: string;
  alias: string;
  status: HealthStatus;
  latency_ms?: number;
  error?: string;
  checked_at: string;
}

export interface HealthCheckAllResponse {
  total: number;
  healthy: number;
  unhealthy: number;
  results: Array<{
    model_id: string;
    alias: string;
    status: string;
    latency_ms?: number;
    error?: string;
  }>;
}

export interface ModelProbeInfoResponse {
  provider_model_name: string;
  model_version: string;
  model_type?: 'llm_chat' | 'embedding' | 'reranker';
  health_status?: 'healthy' | 'degraded' | 'unavailable';
  raw?: Record<string, unknown>;
}

export interface EmbeddingUsageTenantRow {
  tenant_id: string;
  tenant_name: string;
  tenant_active: boolean;
  collection_count: number;
  total_docs: number;
  vectorized_docs: number;
  not_vectorized_docs: number;
}

export interface EmbeddingUsageCollectionRow {
  collection_id: string;
  collection_name: string;
  collection_slug: string;
  tenant_id: string;
  tenant_name: string;
  total_docs: number;
  vectorized_docs: number;
  not_vectorized_docs: number;
}

export interface EmbeddingUsageResponse {
  model_id: string;
  model_alias: string;
  tenants: EmbeddingUsageTenantRow[];
  collections: EmbeddingUsageCollectionRow[];
}

export interface TenantListResponse {
  items: Tenant[];
  total: number;
  page: number;
  size: number;
  has_more: boolean;
}

// API functions
export const adminApi = {
  // Users
  async getUsers(
    params: {
      query?: string;
      role?: string;
      is_active?: boolean;
      limit?: number;
      cursor?: string;
    } = {}
  ): Promise<UserListResponse> {
    const searchParams = new URLSearchParams();
    if (params.query) searchParams.set('query', params.query);
    if (params.role) searchParams.set('role', params.role);
    if (params.is_active !== undefined)
      searchParams.set('is_active', String(params.is_active));
    if (params.limit) searchParams.set('limit', String(params.limit));
    if (params.cursor) searchParams.set('cursor', params.cursor);

    return apiRequest(`/admin/users?${searchParams.toString()}`);
  },

  async getUser(id: string): Promise<User> {
    return apiRequest(`/admin/users/${id}`);
  },

  async createUser(
    user: UserCreate
  ): Promise<{ user: User; password?: string }> {
    return apiRequest('/admin/users', {
      method: 'POST',
      body: JSON.stringify(user),
    });
  },

  async updateUser(id: string, user: UserUpdate): Promise<User> {
    return apiRequest(`/admin/users/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(user),
    });
  },

  async deleteUser(id: string): Promise<void> {
    return apiRequest(`/admin/users/${id}`, {
      method: 'DELETE',
    });
  },

  async resetUserPassword(
    id: string,
    passwordData: PasswordChange
  ): Promise<{ password?: string }> {
    return apiRequest(`/admin/users/${id}/password`, {
      method: 'POST',
      body: JSON.stringify(passwordData),
    });
  },

  // Tokens
  async getUserTokens(userId: string): Promise<TokenListResponse> {
    return apiRequest(`/admin/users/${userId}/tokens`);
  },

  async createUserToken(
    userId: string,
    token: TokenCreate
  ): Promise<TokenResponse> {
    return apiRequest(`/admin/users/${userId}/tokens`, {
      method: 'POST',
      body: JSON.stringify(token),
    });
  },

  async revokeToken(tokenId: string): Promise<void> {
    return apiRequest(`/admin/tokens/${tokenId}`, {
      method: 'DELETE',
    });
  },

  // Audit
  async getAuditLogs(
    params: {
      page?: number;
      page_size?: number;
      user_id?: string;
      action?: string;
      status?: string;
      from_date?: string;
      to_date?: string;
    } = {}
  ): Promise<AuditLogListResponse> {
    const searchParams = new URLSearchParams();
    if (params.page) searchParams.set('page', String(params.page));
    if (params.page_size) searchParams.set('page_size', String(params.page_size));
    if (params.user_id) searchParams.set('user_id', params.user_id);
    if (params.action) searchParams.set('action', params.action);
    if (params.status) searchParams.set('status', params.status);
    if (params.from_date) searchParams.set('from_date', params.from_date);
    if (params.to_date) searchParams.set('to_date', params.to_date);

    const response = await apiRequest<AuditLogListResponse>(`/admin/audit-logs?${searchParams.toString()}`);
    return response;
  },

  // Password reset
  async requestPasswordReset(
    loginOrEmail: string
  ): Promise<{ message: string }> {
    return apiRequest('/auth/password/forgot', {
      method: 'POST',
      body: JSON.stringify({ login_or_email: loginOrEmail }),
    });
  },

  async resetPassword(
    token: string,
    newPassword: string
  ): Promise<{ message: string }> {
    return apiRequest('/auth/password/reset', {
      method: 'POST',
      body: JSON.stringify({ token, new_password: newPassword }),
    });
  },

  // Models (New Architecture)
  async getModels(
    params: {
      type?: string;          // Changed: modality → type
      status?: string;        // Changed: state → status
      enabled_only?: boolean; // New
      search?: string;
      page?: number;
      size?: number;
    } = {}
  ): Promise<ModelListResponse> {
    const searchParams = new URLSearchParams();
    if (params.type) searchParams.set('type', params.type);
    if (params.status) searchParams.set('status', params.status);
    if (params.enabled_only === true) searchParams.set('enabled_only', 'true');
    if (params.search) searchParams.set('search', params.search);
    if (params.page) searchParams.set('page', String(params.page));
    if (params.size) searchParams.set('size', String(params.size));

    return apiRequest(`/admin/models?${searchParams.toString()}`);
  },

  async getModel(id: string): Promise<Model> {
    return apiRequest(`/admin/models/${id}`);
  },

  async createModel(data: ModelCreate): Promise<Model> {
    return apiRequest('/admin/models', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async updateModel(id: string, data: ModelUpdate): Promise<Model> {
    return apiRequest(`/admin/models/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  async deleteModel(id: string): Promise<void> {
    return apiRequest(`/admin/models/${id}`, {
      method: 'DELETE',
    });
  },

  async healthCheckModel(id: string, force = false): Promise<HealthCheckResponse> {
    return apiRequest(`/admin/models/${id}/health-check`, {
      method: 'POST',
      body: JSON.stringify({ force }),
    });
  },

  async healthCheckAllModels(): Promise<HealthCheckAllResponse> {
    return apiRequest('/admin/models/health-check-all', {
      method: 'POST',
    });
  },

  async probeModelInfo(base_url: string): Promise<ModelProbeInfoResponse> {
    return apiRequest('/admin/models/probe-info', {
      method: 'POST',
      body: JSON.stringify({ base_url }),
    });
  },

  async verifyModel(id: string): Promise<Model & { manifest?: Record<string, unknown>; resolved_type_from_manifest?: string | null }> {
    return apiRequest(`/admin/models/${id}/verify`, {
      method: 'POST',
    });
  },

  async getEmbeddingUsage(id: string): Promise<EmbeddingUsageResponse> {
    return apiRequest(`/admin/models/${id}/embedding-usage`);
  },

  // Tenants
  async getTenants(params: {
    page?: number;
    size?: number;
    search?: string;
    is_active?: boolean;
  } = {}): Promise<TenantListResponse> {
    const searchParams = new URLSearchParams();
    if (params.page) searchParams.set('page', String(params.page));
    if (params.size) searchParams.set('size', String(params.size));
    if (params.search) searchParams.set('search', params.search);
    if (params.is_active !== undefined) searchParams.set('is_active', String(params.is_active));
    return apiRequest(`/admin/tenants${searchParams.toString() ? `?${searchParams.toString()}` : ''}`);
  },

  async getTenant(id: string): Promise<Tenant> {
    return apiRequest(`/admin/tenants/${id}`);
  },

  async createTenant(data: TenantCreate): Promise<Tenant> {
    return apiRequest('/admin/tenants', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async updateTenant(id: string, data: TenantUpdate): Promise<Tenant> {
    return apiRequest(`/admin/tenants/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  async getTenantActiveModels(id: string): Promise<{
    embed_models: Array<{
      model: string;
      version: string;
      vector_dim?: number;
    }>;
    rerank_model?: { model: string; version: string };
    ocr: boolean;
    layout: boolean;
  }> {
    return apiRequest(`/admin/tenants/${id}/models/resolve`);
  },

};

// Token scopes configuration
export const TOKEN_SCOPES: TokenScope[] = [
  { scope: 'api:read', description: 'Read API access' },
  { scope: 'api:write', description: 'Write API access' },
  { scope: 'api:admin', description: 'Admin API access' },
  { scope: 'rag:read', description: 'Read RAG documents' },
  { scope: 'rag:write', description: 'Write RAG documents' },
  { scope: 'rag:admin', description: 'Admin RAG operations' },
  { scope: 'chat:read', description: 'Read chat history' },
  { scope: 'chat:write', description: 'Send messages' },
  { scope: 'chat:admin', description: 'Admin chat operations' },
  { scope: 'users:read', description: 'Read user data' },
  { scope: 'users:write', description: 'Write user data' },
  { scope: 'users:admin', description: 'Admin user operations' },
];

// Role hierarchy for scope expansion
export const SCOPE_HIERARCHY: Record<string, string[]> = {
  'api:admin': ['api:read', 'api:write'],
  'api:write': ['api:read'],
  'rag:admin': ['rag:read', 'rag:write'],
  'rag:write': ['rag:read'],
  'chat:admin': ['chat:read', 'chat:write'],
  'chat:write': ['chat:read'],
  'users:admin': ['users:read', 'users:write'],
  'users:write': ['users:read'],
};

export function expandScopes(scopes: string[]): string[] {
  const expanded = new Set(scopes);
  for (const scope of scopes) {
    if (SCOPE_HIERARCHY[scope]) {
      SCOPE_HIERARCHY[scope].forEach(s => expanded.add(s));
    }
  }
  return Array.from(expanded).sort();
}

// ─── Platform Settings ─────────────────────────────────────────────────────

export interface PlatformSettings {
  id: string;
  // Global Policy Settings
  policies_text?: string;
  require_confirmation_for_write?: boolean;
  require_confirmation_for_destructive?: boolean;
  forbid_destructive?: boolean;
  forbid_write_in_prod?: boolean;
  require_backup_before_write?: boolean;
  // Global Caps / Rails
  abs_max_timeout_s?: number;
  abs_max_retries?: number;
  abs_max_steps?: number;
  abs_max_plan_steps?: number;
  abs_max_concurrency?: number;
  abs_max_task_runtime_s?: number;
  abs_max_tool_calls_per_step?: number;
  chat_upload_max_bytes?: number;
  chat_upload_allowed_extensions?: string;
  created_at: string;
  updated_at: string;
}

export interface PlatformSettingsUpdate {
  policies_text?: string;
  require_confirmation_for_write?: boolean;
  require_confirmation_for_destructive?: boolean;
  forbid_destructive?: boolean;
  forbid_write_in_prod?: boolean;
  require_backup_before_write?: boolean;
  abs_max_timeout_s?: number;
  abs_max_retries?: number;
  abs_max_steps?: number;
  abs_max_plan_steps?: number;
  abs_max_concurrency?: number;
  abs_max_task_runtime_s?: number;
  abs_max_tool_calls_per_step?: number;
  chat_upload_max_bytes?: number;
  chat_upload_allowed_extensions?: string;
}

// Platform Settings API
export const platformSettingsApi = {
  get: (): Promise<PlatformSettings> =>
    apiRequest('/admin/settings', { method: 'GET' }),
  
  update: (data: PlatformSettingsUpdate): Promise<PlatformSettings> =>
    apiRequest('/admin/settings', { 
      method: 'PATCH', 
      body: JSON.stringify(data),
    }),
};

export const orchestrationApi = {
  get: (): Promise<OrchestrationSettings> =>
    apiRequest('/admin/orchestration', { method: 'GET' }),

  updateExecutor: (data: ExecutorSettingsUpdate): Promise<OrchestrationSettings> =>
    apiRequest('/admin/orchestration/executor', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
};

export const systemLLMRolesApi = {
  // CRUD operations
  list: (roleType?: SystemLLMRoleType): Promise<SystemLLMRole[]> =>
    apiRequest(roleType ? `/admin/system-llm-roles?role_type=${roleType}` : '/admin/system-llm-roles', {
      method: 'GET',
    }),

  get: (id: string): Promise<SystemLLMRole> =>
    apiRequest(`/admin/system-llm-roles/${id}`, {
      method: 'GET',
    }),

  getActive: (roleType: SystemLLMRoleType): Promise<SystemLLMRole> =>
    apiRequest(`/admin/system-llm-roles/active/${roleType}`, {
      method: 'GET',
    }),

  create: (data: SystemLLMRoleCreate): Promise<SystemLLMRole> =>
    apiRequest('/admin/system-llm-roles', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: string, data: SystemLLMRoleUpdate): Promise<SystemLLMRole> =>
    apiRequest(`/admin/system-llm-roles/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (id: string): Promise<{ message: string }> =>
    apiRequest(`/admin/system-llm-roles/${id}`, {
      method: 'DELETE',
    }),

  activate: (id: string): Promise<SystemLLMRole> =>
    apiRequest(`/admin/system-llm-roles/${id}/activate`, {
      method: 'POST',
    }),

  // Role-specific update methods
  updatePlanner: (data: PlannerRoleUpdate): Promise<SystemLLMRole> =>
    apiRequest('/admin/system-llm-roles/planner', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  updateSynthesizer: (data: SynthesizerRoleUpdate): Promise<SystemLLMRole> =>
    apiRequest('/admin/system-llm-roles/synthesizer', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  updateFactExtractor: (data: FactExtractorRoleUpdate): Promise<SystemLLMRole> =>
    apiRequest('/admin/system-llm-roles/fact-extractor', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  updateSummaryCompactor: (data: SummaryCompactorRoleUpdate): Promise<SystemLLMRole> =>
    apiRequest('/admin/system-llm-roles/summary-compactor', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  ensureDefaults: (): Promise<{ message: string; roles: Record<string, string> }> =>
    apiRequest('/admin/system-llm-roles/ensure-defaults', {
      method: 'POST',
    }),
};
