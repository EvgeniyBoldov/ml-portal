import { apiRequest } from './http';

export type PermissionScope = 'default' | 'tenant' | 'user';
export type PermissionValue = 'allowed' | 'denied' | 'undefined';

export interface PermissionSet {
  id: string;
  scope: PermissionScope;
  tenant_id?: string;
  user_id?: string;
  instance_permissions: Record<string, PermissionValue>;
  agent_permissions: Record<string, PermissionValue>;
  created_at: string;
  updated_at: string;
}

export interface PermissionSetCreate {
  scope: PermissionScope;
  tenant_id?: string;
  user_id?: string;
  instance_permissions?: Record<string, PermissionValue>;
  agent_permissions?: Record<string, PermissionValue>;
}

export interface PermissionSetUpdate {
  instance_permissions?: Record<string, PermissionValue>;
  agent_permissions?: Record<string, PermissionValue>;
}

export interface EffectivePermissions {
  instance_permissions: Record<string, boolean>;
  agent_permissions: Record<string, boolean>;
  allowed_instances: string[];
  denied_instances: string[];
  allowed_agents: string[];
  denied_agents: string[];
}

export const permissionsApi = {
  async list(params: {
    skip?: number;
    limit?: number;
    scope?: string;
    tenant_id?: string;
    user_id?: string;
  } = {}): Promise<PermissionSet[]> {
    const searchParams = new URLSearchParams();
    if (params.skip) searchParams.set('skip', String(params.skip));
    if (params.limit) searchParams.set('limit', String(params.limit));
    if (params.scope) searchParams.set('scope', params.scope);
    if (params.tenant_id) searchParams.set('tenant_id', params.tenant_id);
    if (params.user_id) searchParams.set('user_id', params.user_id);
    
    return apiRequest(`/admin/permissions?${searchParams.toString()}`);
  },

  async get(id: string): Promise<PermissionSet> {
    return apiRequest(`/admin/permissions/${id}`);
  },

  async getEffective(params: {
    user_id?: string;
    tenant_id?: string;
  } = {}): Promise<EffectivePermissions> {
    const searchParams = new URLSearchParams();
    if (params.user_id) searchParams.set('user_id', params.user_id);
    if (params.tenant_id) searchParams.set('tenant_id', params.tenant_id);
    
    return apiRequest(`/admin/permissions/effective?${searchParams.toString()}`);
  },

  async create(data: PermissionSetCreate): Promise<PermissionSet> {
    return apiRequest('/admin/permissions', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async update(id: string, data: PermissionSetUpdate): Promise<PermissionSet> {
    return apiRequest(`/admin/permissions/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  async delete(id: string): Promise<void> {
    return apiRequest(`/admin/permissions/${id}`, {
      method: 'DELETE',
    });
  },
};
