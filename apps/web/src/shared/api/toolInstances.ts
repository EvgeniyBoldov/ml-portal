import { apiRequest } from './http';

export type ToolInstanceHealthStatus = 'healthy' | 'unhealthy' | 'unknown';
export type ToolInstanceType = 'local' | 'http' | 'custom';

export interface ToolInstance {
  id: string;
  tool_group_id: string;
  slug: string;
  name: string;
  description?: string;
  connection_config: Record<string, unknown>;
  instance_metadata: Record<string, unknown>;
  is_active: boolean;
  instance_type: ToolInstanceType;
  health_status: ToolInstanceHealthStatus;
  last_health_check_at?: string;
  health_check_error?: string;
  created_at: string;
  updated_at: string;
  // Optional joined fields
  tool_group_slug?: string;
  tool_group_name?: string;
}

export interface ToolInstanceCreate {
  tool_group_id: string;
  slug: string;
  name: string;
  description?: string;
  connection_config: Record<string, unknown>;
  instance_metadata?: Record<string, unknown>;
  instance_type?: ToolInstanceType;
}

export interface ToolInstanceUpdate {
  name?: string;
  description?: string;
  connection_config?: Record<string, unknown>;
  instance_metadata?: Record<string, unknown>;
  is_active?: boolean;
}

export interface HealthCheckResult {
  status: ToolInstanceHealthStatus;
  message?: string;
  details?: Record<string, unknown>;
}

export const toolInstancesApi = {
  async list(params: {
    skip?: number;
    limit?: number;
    tool_group_id?: string;
    is_active?: boolean;
  } = {}): Promise<ToolInstance[]> {
    const searchParams = new URLSearchParams();
    if (params.skip) searchParams.set('skip', String(params.skip));
    if (params.limit) searchParams.set('limit', String(params.limit));
    if (params.tool_group_id) searchParams.set('tool_group_id', params.tool_group_id);
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
