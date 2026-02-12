/**
 * Tool Instances API v2
 */
import { apiRequest } from './http';

export interface ToolInstance {
  id: string;
  tool_group_id: string;
  slug: string;
  name: string;
  description?: string;
  instance_type: string;  // "local" | "remote"
  category?: string | null;  // "collection" | "rag" | "llm" | "dcbox" | "jira" | ...
  url: string;
  config?: Record<string, unknown>;
  is_active: boolean;
  health_status?: string;
  created_at: string;
  // joined fields
  tool_group_slug?: string;
  tool_group_name?: string;
}

export interface ToolInstanceCreate {
  tool_group_id: string;
  slug?: string;
  name: string;
  url?: string;
  description?: string;
  config?: Record<string, unknown>;
  category?: string;
}

export interface ToolInstanceUpdate {
  name?: string;
  description?: string;
  url?: string;
  config?: Record<string, unknown>;
  is_active?: boolean;
  category?: string;
}

export interface HealthCheckResult {
  status: string;
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
