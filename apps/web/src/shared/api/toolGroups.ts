import { apiRequest } from './http';

export interface ToolGroup {
  id: string;
  slug: string;
  name: string;
  description?: string;
  created_at: string;
  updated_at: string;
}

export interface ToolGroupCreate {
  slug: string;
  name: string;
  description?: string;
}

export interface ToolGroupUpdate {
  name?: string;
  description?: string;
}

export const toolGroupsApi = {
  async list(params: {
    skip?: number;
    limit?: number;
  } = {}): Promise<ToolGroup[]> {
    const searchParams = new URLSearchParams();
    if (params.skip) searchParams.set('skip', String(params.skip));
    if (params.limit) searchParams.set('limit', String(params.limit));
    
    return apiRequest(`/admin/tool-groups?${searchParams.toString()}`);
  },

  async get(id: string): Promise<ToolGroup> {
    return apiRequest(`/admin/tool-groups/${id}`);
  },

  async create(data: ToolGroupCreate): Promise<ToolGroup> {
    return apiRequest('/admin/tool-groups', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async update(id: string, data: ToolGroupUpdate): Promise<ToolGroup> {
    return apiRequest(`/admin/tool-groups/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  async delete(id: string): Promise<void> {
    return apiRequest(`/admin/tool-groups/${id}`, {
      method: 'DELETE',
    });
  },
};
