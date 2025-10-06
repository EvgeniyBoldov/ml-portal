/**
 * Tenant API client
 */
import { apiFetch } from '../lib/apiFetch';

// Types
export interface Tenant {
  id: string;
  name: string;
  description?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface TenantCreate {
  name: string;
  description?: string;
  is_active?: boolean;
}

export interface TenantUpdate {
  name?: string;
  description?: string;
  is_active?: boolean;
}

export interface TenantListResponse {
  tenants: Tenant[];
  total: number;
  page: number;
  size: number;
  has_more: boolean;
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

    return apiFetch(`/tenants?${searchParams.toString()}`);
  },

  // Get tenant by ID
  async getTenant(id: string): Promise<Tenant> {
    return apiFetch(`/tenants/${id}`);
  },

  // Create tenant
  async createTenant(tenant: TenantCreate): Promise<Tenant> {
    return apiFetch('/tenants', {
      method: 'POST',
      body: JSON.stringify(tenant),
    });
  },

  // Update tenant
  async updateTenant(id: string, tenant: TenantUpdate): Promise<Tenant> {
    return apiFetch(`/tenants/${id}`, {
      method: 'PUT',
      body: JSON.stringify(tenant),
    });
  },

  // Delete tenant
  async deleteTenant(id: string): Promise<void> {
    return apiFetch(`/tenants/${id}`, {
      method: 'DELETE',
    });
  },
};
