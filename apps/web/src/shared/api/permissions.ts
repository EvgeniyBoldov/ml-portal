import { apiRequest } from './http';

export type PermissionScope = 'default' | 'tenant' | 'user';

export interface PermissionSet {
  id: string;
  scope: PermissionScope;
  tenant_id?: string;
  user_id?: string;
  allowed_tools: string[];
  denied_tools: string[];
  allowed_collections: string[];
  denied_collections: string[];
  created_at: string;
  updated_at: string;
}

export interface PermissionSetCreate {
  scope: PermissionScope;
  tenant_id?: string;
  user_id?: string;
  allowed_tools?: string[];
  denied_tools?: string[];
  allowed_collections?: string[];
  denied_collections?: string[];
}

export interface PermissionSetUpdate {
  allowed_tools?: string[];
  denied_tools?: string[];
  allowed_collections?: string[];
  denied_collections?: string[];
}

export interface EffectivePermissions {
  allowed_tools: string[];
  denied_tools: string[];
  allowed_collections: string[];
  denied_collections: string[];
}

export const permissionsApi = {
  async list(params: {
    skip?: number;
    limit?: number;
    scope?: string;
    tenant_id?: string;
  } = {}): Promise<PermissionSet[]> {
    const searchParams = new URLSearchParams();
    if (params.skip) searchParams.set('skip', String(params.skip));
    if (params.limit) searchParams.set('limit', String(params.limit));
    if (params.scope) searchParams.set('scope', params.scope);
    if (params.tenant_id) searchParams.set('tenant_id', params.tenant_id);
    
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
