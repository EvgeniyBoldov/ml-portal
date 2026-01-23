import { apiRequest } from './http';

export type InstanceScope = 'default' | 'tenant' | 'user';
export type ToolInstanceHealthStatus = 'healthy' | 'unhealthy' | 'unknown';

export interface ToolInstance {
  id: string;
  tool_id: string;
  slug: string;
  name: string;
  description?: string;
  scope: InstanceScope;
  tenant_id?: string;
  user_id?: string;
  connection_config: Record<string, any>;
  is_default: boolean;
  is_active: boolean;
  health_status: ToolInstanceHealthStatus;
  last_health_check_at?: string;
  health_check_error?: string;
  created_at: string;
  updated_at: string;
}

export interface ToolInstanceCreate {
  tool_slug: string;
  slug: string;
  name: string;
  description?: string;
  scope: InstanceScope;
  tenant_id?: string;
  user_id?: string;
  connection_config: Record<string, any>;
  is_default?: boolean;
}

export interface ToolInstanceUpdate {
  name?: string;
  description?: string;
  connection_config?: Record<string, any>;
  is_default?: boolean;
  is_active?: boolean;
}

export interface HealthCheckResult {
  status: ToolInstanceHealthStatus;
  message?: string;
  details?: Record<string, any>;
}

export const toolInstancesApi = {
  async list(params: {
    skip?: number;
    limit?: number;
    tool_slug?: string;
    scope?: string;
    tenant_id?: string;
    is_active?: boolean;
  } = {}): Promise<ToolInstance[]> {
    const searchParams = new URLSearchParams();
    if (params.skip) searchParams.set('skip', String(params.skip));
    if (params.limit) searchParams.set('limit', String(params.limit));
    if (params.tool_slug) searchParams.set('tool_slug', params.tool_slug);
    if (params.scope) searchParams.set('scope', params.scope);
    if (params.tenant_id) searchParams.set('tenant_id', params.tenant_id);
    if (params.is_active !== undefined) searchParams.set('is_active', String(params.is_active));
    
    return apiRequest(`/admin/tool-instances?${searchParams.toString()}`);
  },

  async get(id: string): Promise<ToolInstance> {
    return apiRequest(`/admin/tool-instances/${id}`);
  },

  async create(data: ToolInstanceCreate): Promise<ToolInstance> {
    return apiRequest('/admin/tool-instances', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async update(id: string, data: ToolInstanceUpdate): Promise<ToolInstance> {
    return apiRequest(`/admin/tool-instances/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  async delete(id: string): Promise<void> {
    return apiRequest(`/admin/tool-instances/${id}`, {
      method: 'DELETE',
    });
  },

  async healthCheck(id: string): Promise<HealthCheckResult> {
    return apiRequest(`/admin/tool-instances/${id}/health-check`, {
      method: 'POST',
    });
  },
};
