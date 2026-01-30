import { apiRequest } from './http';

export interface Policy {
  id: string;
  slug: string;
  name: string;
  description?: string;
  max_steps?: number;
  max_tool_calls?: number;
  max_wall_time_ms?: number;
  tool_timeout_ms?: number;
  max_retries?: number;
  budget_tokens?: number;
  budget_cost_cents?: number;
  extra_config: Record<string, any>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PolicyCreate {
  slug: string;
  name: string;
  description?: string;
  max_steps?: number;
  max_tool_calls?: number;
  max_wall_time_ms?: number;
  tool_timeout_ms?: number;
  max_retries?: number;
  budget_tokens?: number;
  budget_cost_cents?: number;
  extra_config?: Record<string, any>;
}

export interface PolicyUpdate {
  name?: string;
  description?: string;
  max_steps?: number;
  max_tool_calls?: number;
  max_wall_time_ms?: number;
  tool_timeout_ms?: number;
  max_retries?: number;
  budget_tokens?: number;
  budget_cost_cents?: number;
  extra_config?: Record<string, any>;
  is_active?: boolean;
}

export const policiesApi = {
  async list(params: {
    skip?: number;
    limit?: number;
    is_active?: boolean;
  } = {}): Promise<Policy[]> {
    const searchParams = new URLSearchParams();
    if (params.skip) searchParams.set('skip', String(params.skip));
    if (params.limit) searchParams.set('limit', String(params.limit));
    if (params.is_active !== undefined) searchParams.set('is_active', String(params.is_active));
    
    return apiRequest(`/admin/policies?${searchParams.toString()}`);
  },

  async get(id: string): Promise<Policy> {
    return apiRequest(`/admin/policies/${id}`);
  },

  async create(data: PolicyCreate): Promise<Policy> {
    return apiRequest('/admin/policies', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async update(id: string, data: PolicyUpdate): Promise<Policy> {
    return apiRequest(`/admin/policies/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  async delete(id: string): Promise<void> {
    return apiRequest(`/admin/policies/${id}`, {
      method: 'DELETE',
    });
  },
};
