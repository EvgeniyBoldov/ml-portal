/**
 * Tenant API client
 */
import { apiRequest } from './http';

// Types
export interface Tenant {
  id: string;
  name: string;
  description?: string;
  is_active: boolean;
  embed_models?: string[];
  rerank_model?: string;
  ocr?: boolean;
  layout?: boolean;
  created_at: string;
  updated_at: string;
}

export interface TenantCreate {
  name: string;
  description?: string;
  is_active?: boolean;
  extra_embed_model?: string;
  ocr?: boolean;
  layout?: boolean;
}

export interface TenantUpdate {
  name?: string;
  description?: string;
  is_active?: boolean;
  extra_embed_model?: string | null;
  ocr?: boolean;
  layout?: boolean;
}

export interface TenantListResponse {
  items: Tenant[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export const tenantApi = {
  // List tenants
  async getTenants(
    params: {
      page?: number;
      size?: number;
      search?: string;
      is_active?: boolean;
    } = {}
  ): Promise<TenantListResponse> {
    const searchParams = new URLSearchParams();
    if (params.page) searchParams.set('page', String(params.page));
    if (params.size) searchParams.set('size', String(params.size));
    if (params.search) searchParams.set('search', params.search);
    if (params.is_active !== undefined)
      searchParams.set('is_active', String(params.is_active));

    return apiRequest(`/tenants?${searchParams.toString()}`);
  },

  // Get tenant by ID
  async getTenant(id: string): Promise<Tenant> {
    return apiRequest(`/tenants/${id}`);
  },

  // Create tenant
  async createTenant(tenant: TenantCreate): Promise<Tenant> {
    return apiRequest('/tenants', {
      method: 'POST',
      body: JSON.stringify(tenant),
    });
  },

  // Update tenant
  async updateTenant(id: string, tenant: TenantUpdate): Promise<Tenant> {
    return apiRequest(`/tenants/${id}`, {
      method: 'PUT',
      body: JSON.stringify(tenant),
    });
  },

  // Delete tenant
  async deleteTenant(id: string): Promise<void> {
    return apiRequest(`/tenants/${id}`, {
      method: 'DELETE',
    });
  },
};
