/**
 * Admin API client
 */
import { apiFetch } from '../lib/apiFetch';
// import type { ApiResponse, PaginatedResponse } from './types';

// Types
export interface User {
  id: string;
  login: string;
  role: 'admin' | 'editor' | 'reader';
  email?: string;
  is_active: boolean;
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

    return apiFetch(`/admin/users?${searchParams.toString()}`);
  },

  async getUser(id: string): Promise<User> {
    return apiFetch(`/admin/users/${id}`);
  },

  async createUser(
    user: UserCreate
  ): Promise<{ user: User; password?: string }> {
    return apiFetch('/admin/users', {
      method: 'POST',
      body: JSON.stringify(user),
    });
  },

  async updateUser(id: string, user: UserUpdate): Promise<User> {
    return apiFetch(`/admin/users/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(user),
    });
  },

  async deleteUser(id: string): Promise<void> {
    return apiFetch(`/admin/users/${id}`, {
      method: 'DELETE',
    });
  },

  async resetUserPassword(
    id: string,
    passwordData: PasswordChange
  ): Promise<{ password?: string }> {
    return apiFetch(`/admin/users/${id}/password`, {
      method: 'POST',
      body: JSON.stringify(passwordData),
    });
  },

  // Tokens
  async getUserTokens(userId: string): Promise<TokenListResponse> {
    return apiFetch(`/admin/users/${userId}/tokens`);
  },

  async createUserToken(
    userId: string,
    token: TokenCreate
  ): Promise<TokenResponse> {
    return apiFetch(`/admin/users/${userId}/tokens`, {
      method: 'POST',
      body: JSON.stringify(token),
    });
  },

  async revokeToken(tokenId: string): Promise<void> {
    return apiFetch(`/admin/tokens/${tokenId}`, {
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

    return apiFetch(`/admin/audit-logs?${searchParams.toString()}`);
  },

  // System status
  async getSystemStatus(): Promise<SystemStatus> {
    return apiFetch('/admin/status');
  },

  // Password reset
  async requestPasswordReset(
    loginOrEmail: string
  ): Promise<{ message: string }> {
    return apiFetch('/auth/password/forgot', {
      method: 'POST',
      body: JSON.stringify({ login_or_email: loginOrEmail }),
    });
  },

  async resetPassword(
    token: string,
    newPassword: string
  ): Promise<{ message: string }> {
    return apiFetch('/auth/password/reset', {
      method: 'POST',
      body: JSON.stringify({ token, new_password: newPassword }),
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
