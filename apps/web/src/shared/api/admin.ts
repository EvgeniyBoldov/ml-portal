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
  ts: string;
  actor_user_id?: string;
  actor_login?: string;
  action: string;
  object_type?: string;
  object_id?: string;
  meta?: Record<string, any>;
  ip?: string;
  user_agent?: string;
  request_id?: string;
}

export interface AuditLogListResponse {
  logs: AuditLog[];
  has_more: boolean;
  next_cursor?: string;
  total?: number;
}

export interface AuditFilters {
  actor_user_id?: string;
  action?: string;
  object_type?: string;
  start_date?: string;
  end_date?: string;
}

export interface SystemStatus {
  email_enabled: boolean;
  email_status: 'ok' | 'error' | 'disabled';
  total_users: number;
  active_users: number;
  total_tokens: number;
  active_tokens: number;
}

export interface Tenant {
  id: string;
  name: string;
  description?: string;
  is_active: boolean;
  embedding_model_alias?: string;  // Updated: FK to models.alias
  ocr?: boolean;
  layout?: boolean;
  created_at: string;
  updated_at: string;
}

export type TenantCreate = {
  name: string;
  description?: string;
  is_active?: boolean;
  embedding_model_alias?: string;  // Updated
  ocr?: boolean;
  layout?: boolean;
};

export type TenantUpdate = Partial<TenantCreate>;

export interface EmailSettings {
  smtp_host?: string | null;
  smtp_port?: number | null;
  smtp_user?: string | null;
  smtp_password?: string | null;
  from_email?: string | null;
  from_name?: string | null;
  smtp_enabled?: boolean;
}

export type EmailSettingsUpdate = Partial<EmailSettings>;

// New Model architecture
export type ModelType = 'llm_chat' | 'embedding';
export type ModelStatus = 'available' | 'unavailable' | 'deprecated' | 'maintenance';
export type HealthStatus = 'healthy' | 'degraded' | 'unavailable';

export interface Model {
  id: string;
  alias: string;                      // e.g. "llm.chat.default"
  name: string;                       // Human-readable name
  type: ModelType;                    // llm_chat | embedding
  provider: string;                   // openai, groq, local, etc.
  provider_model_name: string;        // Model name at provider
  base_url: string;                   // API base URL
  api_key_ref?: string | null;        // Reference to secret
  extra_config?: Record<string, any> | null;  // Provider-specific config
  status: ModelStatus;                // Availability status
  enabled: boolean;
  default_for_type: boolean;          // Is this the default model for its type?
  model_version?: string | null;      // For tracking changes
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
  provider: string;
  provider_model_name: string;
  base_url: string;
  api_key_ref?: string;
  extra_config?: Record<string, any>;
  status?: ModelStatus;
  enabled?: boolean;
  default_for_type?: boolean;
  model_version?: string;
  description?: string;
}

export interface ModelUpdate {
  name?: string;
  provider?: string;
  provider_model_name?: string;
  base_url?: string;
  api_key_ref?: string;
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

// Backward compatibility (will be removed)
export type ModelRegistry = Model;
export type ModelRegistryListResponse = ModelListResponse;

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
      actor_user_id?: string;
      action?: string;
      object_type?: string;
      start_date?: string;
      end_date?: string;
      limit?: number;
      cursor?: string;
    } = {}
  ): Promise<AuditLogListResponse> {
    const searchParams = new URLSearchParams();
    if (params.actor_user_id)
      searchParams.set('actor_user_id', params.actor_user_id);
    if (params.action) searchParams.set('action', params.action);
    if (params.object_type) searchParams.set('object_type', params.object_type);
    if (params.start_date) searchParams.set('start_date', params.start_date);
    if (params.end_date) searchParams.set('end_date', params.end_date);
    if (params.limit) searchParams.set('limit', String(params.limit));
    if (params.cursor) searchParams.set('cursor', params.cursor);

    return apiRequest(`/admin/audit-logs?${searchParams.toString()}`);
  },

  // System status
  async getSystemStatus(): Promise<SystemStatus> {
    return apiRequest('/admin/status');
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
    if (params.enabled_only) searchParams.set('enabled_only', 'true');
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

  // Tenants
  async getTenants(): Promise<TenantListResponse> {
    const response = await apiRequest<{ items?: Tenant[]; total?: number }>(
      '/tenants'
    );
    // API возвращает {items: [...], total: N}, оборачиваем в правильный формат
    return {
      items: response.items || [],
      total: response.total || 0,
      page: 1,
      size: response.items?.length || 0,
      has_more: false,
    };
  },

  async getTenant(id: string): Promise<Tenant> {
    return apiRequest(`/tenants/${id}`);
  },

  async createTenant(data: TenantCreate): Promise<Tenant> {
    return apiRequest('/tenants', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async updateTenant(id: string, data: TenantUpdate): Promise<Tenant> {
    return apiRequest(`/tenants/${id}`, {
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
    return apiRequest(`/tenants/${id}/models/resolve`);
  },

  async getEmailSettings(): Promise<EmailSettings> {
    return apiRequest('/admin/settings/email');
  },

  async updateEmailSettings(data: EmailSettingsUpdate): Promise<EmailSettings> {
    return apiRequest('/admin/settings/email', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
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
