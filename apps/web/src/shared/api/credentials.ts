/**
 * Credentials API v2 - owner-based model
 */
import { apiRequest } from './http';

export interface Credential {
  id: string;
  instance_id: string;
  auth_type: string;
  is_active: boolean;
  has_payload?: boolean;
  masked_payload?: Record<string, string> | null;
  owner_user_id?: string | null;
  owner_tenant_id?: string | null;
  owner_platform: boolean;
  created_at: string;
}

export interface CredentialCreate {
  instance_id: string;
  auth_type: string;
  payload: Record<string, any>;
  owner_user_id?: string | null;
  owner_tenant_id?: string | null;
  owner_platform?: boolean;
}

export interface CredentialUpdate {
  auth_type?: string;
  payload?: Record<string, any>;
  is_active?: boolean;
}

export interface CredentialListParams {
  skip?: number;
  limit?: number;
  instance_id?: string;
  owner_user_id?: string;
  owner_tenant_id?: string;
  owner_platform?: boolean;
  is_active?: boolean;
}

export const credentialsApi = {
  async list(params: CredentialListParams = {}): Promise<Credential[]> {
    const sp = new URLSearchParams();
    if (params.skip) sp.set('skip', String(params.skip));
    if (params.limit) sp.set('limit', String(params.limit));
    if (params.instance_id) sp.set('instance_id', params.instance_id);
    if (params.owner_user_id) sp.set('owner_user_id', params.owner_user_id);
    if (params.owner_tenant_id) sp.set('owner_tenant_id', params.owner_tenant_id);
    if (params.owner_platform !== undefined) sp.set('owner_platform', String(params.owner_platform));
    if (params.is_active !== undefined) sp.set('is_active', String(params.is_active));
    return apiRequest(`/admin/credentials?${sp.toString()}`);
  },

  async get(id: string): Promise<Credential> {
    return apiRequest(`/admin/credentials/${id}`);
  },

  async create(data: CredentialCreate): Promise<Credential> {
    return apiRequest('/admin/credentials', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async update(id: string, data: CredentialUpdate): Promise<Credential> {
    return apiRequest(`/admin/credentials/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  async delete(id: string): Promise<void> {
    return apiRequest(`/admin/credentials/${id}`, { method: 'DELETE' });
  },
};
