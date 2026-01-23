import { apiRequest } from './http';

export type AuthType = 'token' | 'basic' | 'oauth' | 'api_key';
export type CredentialScope = 'tenant' | 'user';

export interface CredentialSet {
  id: string;
  tool_instance_id: string;
  scope: CredentialScope;
  tenant_id?: string;
  user_id?: string;
  auth_type: AuthType;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CredentialSetCreate {
  tool_instance_id: string;
  auth_type: AuthType;
  payload: Record<string, any>;
  scope: CredentialScope;
  tenant_id?: string;
  user_id?: string;
}

export interface CredentialSetUpdate {
  auth_type?: AuthType;
  payload?: Record<string, any>;
  is_active?: boolean;
}

export const credentialsApi = {
  async list(params: {
    skip?: number;
    limit?: number;
    tool_instance_id?: string;
    scope?: string;
    tenant_id?: string;
    is_active?: boolean;
  } = {}): Promise<CredentialSet[]> {
    const searchParams = new URLSearchParams();
    if (params.skip) searchParams.set('skip', String(params.skip));
    if (params.limit) searchParams.set('limit', String(params.limit));
    if (params.tool_instance_id) searchParams.set('tool_instance_id', params.tool_instance_id);
    if (params.scope) searchParams.set('scope', params.scope);
    if (params.tenant_id) searchParams.set('tenant_id', params.tenant_id);
    if (params.is_active !== undefined) searchParams.set('is_active', String(params.is_active));
    
    return apiRequest(`/admin/credentials?${searchParams.toString()}`);
  },

  async get(id: string): Promise<CredentialSet> {
    return apiRequest(`/admin/credentials/${id}`);
  },

  async create(data: CredentialSetCreate): Promise<CredentialSet> {
    return apiRequest('/admin/credentials', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async update(id: string, data: CredentialSetUpdate): Promise<CredentialSet> {
    return apiRequest(`/admin/credentials/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  async delete(id: string): Promise<void> {
    return apiRequest(`/admin/credentials/${id}`, {
      method: 'DELETE',
    });
  },
};
