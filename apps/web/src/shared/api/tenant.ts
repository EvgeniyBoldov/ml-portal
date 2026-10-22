/**
 * Tenant API client
 */
import { apiRequest } from './http';
export type { Tenant, TenantCreate, TenantUpdate, TenantListResponse } from './admin';
import type { Tenant, TenantCreate, TenantUpdate, TenantListResponse } from './admin';

export const tenantApi = {
  // List tenants
  async getTenants(
    params: {
      page?: number;
      size?: number;
      search?: string;
      is_active?: boolean;
      include_deprecated?: boolean;
    } = {}
  ): Promise<TenantListResponse> {
    const searchParams = new URLSearchParams();
    if (params.page) searchParams.set('page', String(params.page));
    if (params.size) searchParams.set('size', String(params.size));
    if (params.search) searchParams.set('search', params.search);
    if (params.is_active !== undefined)
      searchParams.set('is_active', String(params.is_active));
    if (params.include_deprecated !== undefined)
      searchParams.set('include_deprecated', String(params.include_deprecated));

    return apiRequest(`/admin/tenants?${searchParams.toString()}`);
  },

  // Get tenant by ID
  async getTenant(id: string): Promise<Tenant> {
    return apiRequest(`/admin/tenants/${id}`);
  },

  // Create tenant
  async createTenant(tenant: TenantCreate): Promise<Tenant> {
    return apiRequest('/admin/tenants', {
      method: 'POST',
      body: JSON.stringify(tenant),
    });
  },

  // Update tenant
  async updateTenant(id: string, tenant: TenantUpdate): Promise<Tenant> {
    return apiRequest(`/admin/tenants/${id}`, {
      method: 'PUT',
      body: JSON.stringify(tenant),
    });
  },

};
